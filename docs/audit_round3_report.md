# FTSM-RAG 第三轮审计报告

审计时间：2026-10-17 ~ 2026-10-18
范围：Python 后端（web_app.py / rag / services / utils / model / agent）、Java（ftsm-gateway / ftsm-knowledge / ftsm-common / ftsm-user）、桌面端（desktop/）、网页前端（web/templates/guide.html + web/static/guide.js）。
所有结论均基于实际读到的代码，标注 `文件:行号`。前两轮"已修复"项逐项复核通过（见文末清单）。

---

## P0（数据丢失 / 安全）

**本轮未发现新的 P0 级问题。** 前两轮的 P0 修复（上传隔离、官方语料防删、admin key）复核全部有效，且经行为验证。

---

## P1（功能缺陷 / 竞态）

### P1-1 `/api/knowledge/update` 缺少服务端管理员密钥自校验 —— 纵深防御不对称，Docker 部署下可被未认证调用

**证据**
- `web_app.py:935-943`：`update_knowledge_from_website` 直接调 `trigger_manual_crawl`，无任何密钥校验；
- 对比 `web_app.py:447-453`：`/api/settings` 有自校验，注释明确写着 *"P0-3 纵深防御：除网关 ADMIN_PATHS 外，服务本身也校验管理员密钥（直连 8104 端口绕过网关的场景也被挡住）"*；
- `SessionAuthFilter.java:48-51,71-81`：网关确实对 `/api/knowledge/update`（非 GET）要求 `X-Admin-Api-Key`；
- 但 `scripts/stack_docker.sh:18` `-p 8104:8104`、`scripts/stack_docker.sh:42` `uvicorn web_app:app --host 0.0.0.0 --port 8104`：Docker 部署下 8104 直接发布到宿主机所有网卡，可完全绕过网关。

**影响**：Docker/LAN 部署下，任何同网段主机可未认证触发全站 Playwright 爬取 + 全量重索引（重量级操作）；同理直连 8104 时 `/api/chat`、`/api/upload`、`/api/voice/*`、`DELETE /api/documents/uploads/**` 也无认证（这些在网关侧有会话保护，Python 侧没有）。Origin 中间件（`web_app.py:178-183`）只拦浏览器跨域——无 Origin 头的 curl 直连实测放行（验证 #8）。

**修复建议**
1. `/api/knowledge/update` 复制 `/api/settings` 的 `X-Admin-Api-Key` 自校验（最低成本、与既有 P0-3 模式一致）；
2. 中期：`stack_docker.sh` 去掉 `-p 8104:8104`（或改 `127.0.0.1:8104:8104`），让 8104 只走内部网络；
3. 可选：chat/upload/voice/documents 在 Python 侧校验网关注入的可信头（如共享 secret）。

**验证**：POST /api/settings 无/错 key → 401（实测）；`/api/knowledge/update` 无校验为代码证据，未实测 POST（会触发真实爬取与重索引，产生副作用，已标注）。

---

### P1-2 BM25 无锁读的撕裂竞态可致整次检索抛 IndexError

**证据**：`rag/rag_service.py:885-898`
```python
def _bm25_retrieve(self, query, top_k):
    self._ensure_bm25()                       # 887
    if self._bm25 is None or not self._bm25_docs:   # 888  ← 无锁读
    ...
    scores = self._bm25.get_scores(tokens)    # 896  ← 无锁读 self._bm25
    return [self._bm25_docs[i] for i in top_indices if scores[i] > 0]  # 898
```
而 `_ensure_bm25`（867-880）在锁内执行：先 `self._bm25 = None; self._bm25_docs = []`（867-868）→ 拉全量 → 先赋 `self._bm25_docs`（873）再赋 `self._bm25`（879）。

**竞态窗口**：线程 B 在 888 行读到旧 `_bm25`（N 个文档）非 None，随后线程 A 在锁内把 `_bm25_docs` 换成 M 个文档的新列表（M<N），B 在 898 行用基于 N 的 `top_indices` 索引 M 长度列表 → `IndexError`。`retriever_docs`（1039-1041）的 `bm25_future.result()` 不捕获该异常 → 该次聊天请求整体失败。聊天流跑在 FastAPI 线程池，多线程并发是常态。

**修复建议**：在 `_bm25_retrieve` 里持锁取快照：
```python
with self._bm25_lock:
    bm25, docs = self._bm25, list(self._bm25_docs)
if bm25 is None or not docs: return []
```
（或 `_ensure_bm25` 重建时先构造局部新对象，最后一次性原子赋值两个字段。）

**验证**：未实际复现（需要并发时序窗口；静态推演成立，标注为推演结论）。

---

## P2（健壮性 / 性能）

### P2-1 `_ensure_bm25` 失败静默降级 + 每查询重试全量拉取
`rag/rag_service.py:881-883`：except 分支**无日志**、`_bm25_sig` 不更新且 `_bm25` 置 None → Chroma 抖动后每次 `_bm25_retrieve` 都会重新尝试全量 `.get()`（870 行，拉全部 chunk 文本），同时 BM25 路静默失效（混合检索退化为纯向量，无任何观测手段）。修复：except 中 `logger.warning` + 失败退避（N 秒内不重试）。

### P2-2 `_HASH_CACHE` 无上限增长
`services/document_service.py:121-132`：只增不减；文件被非 API 方式移除后条目残留。当前 41 文件无碍，长期运行无界。修复：超阈值（如 1024）时整体重建，或改 LRU。

### P2-3 `save_uploads` TOCTOU + 全量读内存
`services/document_service.py:39-46`：`await file.read()` 先整读进内存再检查大小（>50MB 的恶意上传同样先占满内存）；`target.exists()`（43）→ `write_bytes`（46）非原子，两个并发同名上传都可通过检查、后者覆盖前者，违背"禁止覆盖"语义。修复：分块读+累计超限即断；用 `open(target, "xb")` 独占创建替代 exists 检查。

### P2-4 `list_knowledge_documents` 不跳隐藏目录，与索引器语义不一致
`services/document_service.py:65-70`（`data_dir.rglob("*")`）vs `utils/file_handler.py:51-58`（os.walk 跳过隐藏目录/文件）。DATA_DIR 下若出现隐藏目录（如 `.trash/x.txt`），列表会展示（source=official、API 不可删、索引器也永不收录）→ 永久 "Not indexed" 噪音。修复：rglob 循环里补 `if any(p.startswith(".") for p in path.relative_to(data_dir).parts): continue`。

### P2-5 docker-compose MySQL 弱默认口令且端口全发布
`docker-compose.yml:7-9`：`MYSQL_ROOT_PASSWORD` 默认 `ftsm123456`，`3306:3306` 发布到 0.0.0.0。与 P1-1 同属部署暴露面。修复：`127.0.0.1:3306:3306` + 强制显式 env 密码。

### P2-6 网关路径匹配用 `startsWith` 而非精确匹配
`SessionAuthFilter.java:71-72,83-85`：`ADMIN_PATHS.stream().anyMatch(path::startsWith)`、`STUDENT_EXACT...anyMatch(path::startsWith)` —— `/api/settingsfoo`、`/api/chatXYZ` 这类前缀碰撞路径会带上错误语义。当前路由表无此类路径，无实际漏洞，属契约健壮性问题。

### P2-7 `client.ts` delete 返回类型与后端不符；guide.js 注释陈旧
`desktop/src/api/client.ts:189` 声明返回 `{ok: boolean}`，后端实际返回 `{deleted, doc_id, manifest_found, vector_delete_ok, deleted_chunks}`（`web_app.py:830` + `document_service.py:190`）。当前无消费方读 `ok`，无功能影响（tsc 亦通过，因为运行时多余字段不报错），但类型失真。另 `guide.js:1322-1323` 注释写 `/api/knowledge/stats`，实际调用 `/api/kb/stats`（1381）。

### P2-8 ConversationStore 每回合双写 index.json
`utils/conversation_store.py:214-224`（`_save_conv` 内已做 index upsert）+ `append_turn:131` 又调 `_upsert_index` → 每回合 index.json 全量读写×2。功能正确（锁内、原子写），仅效率问题。

---

## 前两轮修复复核结果（全部通过）

| # | 修复项 | 证据 | 验证方式 |
|---|---|---|---|
| 1 | 上传隔离 uploads/ + 禁覆盖 | document_service.py:20-46 | 代码 + 行为（官方语料删除 403） |
| 2 | 官方语料 API 不可删 | document_service.py:156-162 | 行为：DELETE academic_calendar… → 403 |
| 3 | 路径穿越防护 | document_service.py:135-143 | 行为：`../../web_app.py` 与 `..%2F..%2F` 均 400 |
| 4 | POST /api/settings 需 admin key | web_app.py:449-453 | 行为：无/错 key → 401；GET 返回掩码 `sk-****1796` |
| 5 | listdir 递归 + 跳隐藏 + 大小写不敏感 | file_handler.py:36-60 | 代码（`f.lower().endswith(allowed)`，allowed 已归一小写） |
| 6 | BM25 模块级分词 + 双检锁 | rag_service.py:720-734, 858-880 | 代码 |
| 7 | `_manifest_signature` = (mtime_ns, size) | rag_service.py:841-856 | 代码 |
| 8 | 删除链路持 indexing_lock + 清 _HASH_CACHE | document_service.py:168-189 | 代码（两种 key 形态均弹出） |
| 9 | MQ 消费者索引整体持锁 + filePath 包含性校验 | index_consumer.py:52-63, 103-120 | 代码 |
| 10 | 桌面端契约（source / 分段 encode / adminHeaders / 删除钮 / Admin Key 输入框） | client.ts:55,146-149,186-192,204-208; Manage.tsx:327-337; Settings.tsx:31-33,133-139 | 代码 + `tsc --noEmit` 通过 |
| 11 | Java listDocuments 补 source 字段 | KnowledgeController.java:54 | 代码 + `mvn compile` 通过 |
| 12 | MQ 拓扑双侧对齐（exchange/queue/routing/DLQ/TTL） | mq_events.py:27-34 vs DocEvents.java:13-25 + RabbitTopology.java:26-36 | 逐项比对一致 |
| 13 | markReady `.in(INDEXING, FAILED)`；migrate 原子迁移 | InternalDocController.java:138-147; KnowledgeEventListeners.java:60-77 | 代码 |
| 14 | 同步路由去 async（list_models 保留 async 正确） | web_app.py:328-330,797-830,833-848 vs 472,547 | 代码 + py_compile |
| 15 | coursework_timetable PDF 已恢复 | data/ukm_ftsm/ 下 465,616 字节（2026-10-17） | ls + /api/documents 列表确认 |
| 16 | 三语 i18n 字典完整 | 56 个 data-i18n 键 + composer.ph 在 I18N_ZH/I18N_MS 全存在，两字典键集 57=57 | 脚本比对，零缺键 |

## 已验证无误的其他方面

- **索引互斥**：四条索引写入路径（training worker `web_app.py:109-111`、MQ 消费者 `index_consumer.py:60-63`、调度器 `scheduler.py:159-160`、删除 `document_service.py:173`）全部持同一把 `indexing_lock`，无竞态窗口；定时任务与 MQ 消费者不冲突。
- **训练状态机**：`running` 在持锁期间置位（web_app.py:134-147），POST 返回即 True，pending 链路（96-131）正确。
- **上传→注册→MQ/本地兜底**：`_mq_consumer_live` 确认消费者在线才走事件链路，否则本地训练并回写 READY（web_app.py:738-749, knowledge_client.py:61-90），INDEXING 不会永久卡死。
- **会话安全**：HMAC-SHA256 + 常时比较（SessionTokens.java:49）、HttpOnly + SameSite=Lax（SessionCookieWriter.java:28-31）、网关剥离客户端伪造的 X-Student-Id（SessionAuthFilter.java:95-99）。
- **CORS/Origin**：tauri.localhost 白名单 + localhost 正则（web_app.py:152-183）；恶意 Origin 实测 403。
- **绑定地址**：launcher.py:47 与 lib.rs:78 均为 127.0.0.1（桌面模式无暴露；暴露仅存在于 docker 模式，见 P1-1/P2-5）。
- **guide.js XSS**：动态内容经 `escapeHtml`（guide.js:362 起，renderAnswer/renderMarkdown 内应用）；TOPICS/topic_answers 为项目内静态资源。
- **删除 URL 编码**：desktop client.ts:190 与 guide.js:1423 均按段 `encodeURIComponent`，与 FastAPI `{filename:path}` 匹配一致。
- **ChromaDB↔manifest 写序**：先向量后 manifest（vector_store.py:265→294-301），失败回滚已加 chunk（307-308），断电中断不会留下 manifest 指向不存在向量的记录（反向：向量存在但 manifest 缺失只造成重复，幂等 chunk_id 使重嵌覆盖）。
- **语音链路**：TTS 文本清洗限长 2500 字符（voice_service.py:139）、STT 15MB/MIME 白名单（web_app.py:662-666）、均 `asyncio.to_thread` 不阻塞事件循环。

## 执行过的验证命令与结果

```
1. /Users/houzhengbo/.workbuddy/binaries/python/versions/3.13.12/bin/python3 -m py_compile \
   web_app.py launcher.py rag/*.py(6) services/*.py(6) utils/*.py(8) model/factory.py agent/... (26 个文件)
   → PY_COMPILE_OK

2. cd desktop && npx tsc --noEmit          → exit 0，无类型错误

3. cd ftsm-java && JAVA_HOME=$HOME/Library/Java/JavaVirtualMachines/temurin-17.jdk/Contents/Home \
   /opt/homebrew/bin/mvn -q compile -pl ftsm-knowledge -am    → exit 0

4. 行为验证（临时实例 127.0.0.1:8188，FTSM_MQ_ENABLED=0，未触碰运行中的 8080~8104 栈）：
   POST /api/settings 无 key / 错 key          → 401 / 401
   DELETE /api/documents/academic_calendar….txt → 403（官方语料受保护）
   DELETE /api/documents/../../web_app.py       → 400（path-as-is）
   DELETE /api/documents/..%2F..%2Fweb_app.py   → 400（编码穿越）
   GET /api/documents (Origin: evil.example.com)→ 403
   GET /api/documents（无 Origin）              → 200（41 文档，source 字段齐全，uploads=0）
   DELETE /api/documents/uploads/ghost.txt      → 404
   GET /api/settings                           → {"dashscope_api_key":"sk-****1796",…}（掩码）

5. i18n 键比对脚本（python3 + re，guide.html data-i18n ↔ I18N_ZH/I18N_MS）
   → HTML 56 键全部命中；ZH/MS 键集 57=57，无缺键
```

## 未验证项（明确标注）

- **P1-2 竞态**：未并发复现（时序窗口窄）；结论为基于代码的推演，已标注。
- **POST /api/knowledge/update 行为**：未实测（会触发真实爬取 + 全量重索引 + 写共享 chroma_db，副作用不可接受）；"无密钥校验"为直接代码证据。
- **chat / voice / upload 端到端**：未实测（消耗 Vertex 配额、写共享 ChromaDB，会干扰正在运行的 8104 实例）。
- **RabbitMQ 消息流（register→requested→succeeded→READY）**：未实测（会污染 doc.index.request.queue 与 MySQL doc 表）；契约正确性以双侧代码比对为准。
