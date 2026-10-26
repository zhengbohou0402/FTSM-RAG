"""
对话存储：每个对话一个 JSON 文件 + 一个 index.json 索引。

相较于把所有对话放在一个大 JSON 里：
- 单次追加消息只重写一个小文件，O(1) 而非 O(N)
- 列表接口只读 index.json，不加载全部消息
- 原子写（tmp + replace）避免崩溃导致文件损坏
- 自动迁移旧版本 data/ukm_ftsm/conversations.json

目录结构：
    data/ukm_ftsm/conversations/
        index.json
        <uuid>.json
        <uuid>.json
        ...
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any

from utils.logger_handler import logger

# 索引最多保留条数；超出自动按 updated_at 淘汰
MAX_CONVERSATIONS = 200
# 单个对话保留的消息数（用户+助手 各一条算 2 条）
MAX_MESSAGES_PER_CONVERSATION = 40

# 仅接受 UUID 风格的字符，避免目录穿越
_SAFE_ID_RE = re.compile(r"[^0-9a-fA-F-]")


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


class ConversationStore:
    def __init__(self, base_dir: Path) -> None:
        self.dir = base_dir / "conversations"
        self.index_file = self.dir / "index.json"
        self._lock = threading.RLock()
        self._migrate_legacy(base_dir)
        self._rebuild_index()

    # ── 公共 API ──────────────────────────────────────────

    def list_items(self, limit: int | None = None) -> list[dict[str, Any]]:
        """返回索引项（只含 id/title/updated_at），按最近更新倒序。"""
        items = self._load_index()
        items.sort(key=lambda x: x.get("updated_at", 0), reverse=True)
        return items[:limit] if limit else items

    def get(self, conversation_id: str) -> dict[str, Any] | None:
        p = self._conv_path(conversation_id)
        if p is None or not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None

    def recent_messages(self, conversation_id: str, max_turns: int) -> list[dict[str, str]]:
        conv = self.get(conversation_id)
        if not conv:
            return []
        limit = max_turns * 2
        return [
            {"role": m["role"], "content": m["content"]}
            for m in conv.get("messages", [])[-limit:]
        ]

    def create(self, conversation_id: str) -> dict[str, Any]:
        conv = {
            "id": conversation_id,
            "title": "New chat",
            "updated_at": int(time.time()),
            "messages": [],
        }
        with self._lock:
            self._save_conv(conv)
            self._upsert_index(conv["id"], conv["title"], conv["updated_at"])
        return conv

    def delete(self, conversation_id: str) -> bool:
        """删除一个对话文件及其索引项。返回 True 表示成功，False 表示未找到。"""
        with self._lock:
            path = self._conv_path(conversation_id)
            found = path is not None and path.exists()
            if path and path.exists():
                try:
                    path.unlink()
                except OSError:
                    pass
            index = self._load_index()
            new_index = [i for i in index if i.get("id") != conversation_id]
            if len(new_index) != len(index):
                self._save_index(new_index)
        return found

    def append_turn(
        self,
        conversation_id: str,
        user_content: str,
        assistant_content: str,
        title: str | None = None,
    ) -> None:
        """在锁内完成 读→追加→写 一个原子回合。"""
        now = int(time.time())
        with self._lock:
            conv = self.get(conversation_id) or {
                "id": conversation_id,
                "title": title or "New chat",
                "updated_at": now,
                "messages": [],
            }
            msgs = conv.get("messages", [])
            msgs.append({"role": "user", "content": user_content, "created_at": now})
            msgs.append({"role": "assistant", "content": assistant_content, "created_at": now})
            conv["messages"] = msgs[-MAX_MESSAGES_PER_CONVERSATION:]
            conv["title"] = title or conv.get("title") or "New chat"
            conv["updated_at"] = now
            self._save_conv(conv)
            self._upsert_index(conv["id"], conv["title"], conv["updated_at"])

    # ── 内部实现 ──────────────────────────────────────────

    def _conv_path(self, conversation_id: str) -> Path | None:
        safe = _SAFE_ID_RE.sub("", conversation_id or "")[:64]
        if not safe:
            return None
        return self.dir / f"{safe}.json"

    def _rebuild_index(self) -> None:
        """把磁盘上存在但不在 index.json 里的对话补回索引（一次性自愈）。

        历史 bug：append_turn 只写对话文件不更新索引，导致列表接口看不到
        已存在的对话。启动时全量扫描一次目录即可找回。
        """
        known = {i.get("id") for i in self._load_index()}
        found: list[dict[str, Any]] = []
        for path in self.dir.glob("*.json"):
            if path.name == self.index_file.name:
                continue
            try:
                conv = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            conv_id = str(conv.get("id") or path.stem)
            if conv_id in known:
                continue
            found.append({
                "id": conv_id,
                "title": conv.get("title") or "New chat",
                "updated_at": int(conv.get("updated_at") or 0),
            })
        if not found:
            return
        index = self._load_index()
        index.extend(found)
        index.sort(key=lambda x: x.get("updated_at", 0), reverse=True)
        if len(index) > MAX_CONVERSATIONS:
            index = index[:MAX_CONVERSATIONS]
        self._save_index(index)
        logger.warning(
            "[conversation_store] Rebuilt index: recovered %d orphaned conversation(s)",
            len(found),
        )

    def _upsert_index(self, conversation_id: str, title: str, updated_at: int) -> None:
        """把对话 upsert 进 index.json（append_turn/create 之后调用）。

        必须与 _save_conv 在同一把锁内调用；超出 MAX_CONVERSATIONS 时按
        updated_at 淘汰最旧条目。
        """
        index = self._load_index()
        new_index = [i for i in index if i.get("id") != conversation_id]
        new_index.append({"id": conversation_id, "title": title, "updated_at": updated_at})
        new_index.sort(key=lambda x: x.get("updated_at", 0), reverse=True)
        if len(new_index) > MAX_CONVERSATIONS:
            new_index = new_index[:MAX_CONVERSATIONS]
        self._save_index(new_index)

    def _load_index(self) -> list[dict[str, Any]]:
        if not self.index_file.exists():
            return []
        try:
            data = json.loads(self.index_file.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save_index(self, items: list[dict[str, Any]]) -> None:
        _atomic_write(
            self.index_file,
            json.dumps(items, ensure_ascii=False, indent=2),
        )

    def _save_conv(self, conv: dict[str, Any]) -> None:
        """写一个对话文件 + 更新索引 + 执行 LRU 淘汰。必须在锁内调用。"""
        cid = conv["id"]
        path = self._conv_path(cid)
        if path is None:
            return
        _atomic_write(path, json.dumps(conv, ensure_ascii=False, indent=2))

        index = self._load_index()
        index = [i for i in index if i.get("id") != cid]
        index.append(
            {
                "id": cid,
                "title": conv.get("title", "New chat"),
                "updated_at": conv.get("updated_at", int(time.time())),
            }
        )
        self._prune(index)
        self._save_index(index)

    def _prune(self, index: list[dict[str, Any]]) -> None:
        """超过上限时，删除最老的对话文件 + 索引项。"""
        if len(index) <= MAX_CONVERSATIONS:
            return
        index.sort(key=lambda x: x.get("updated_at", 0), reverse=True)
        to_delete = index[MAX_CONVERSATIONS:]
        del index[MAX_CONVERSATIONS:]
        for item in to_delete:
            p = self._conv_path(item.get("id", ""))
            if p and p.exists():
                try:
                    p.unlink()
                except OSError:
                    pass

    def _migrate_legacy(self, base_dir: Path) -> None:
        """把旧版 conversations.json 拆分迁移到新结构，仅迁移一次。"""
        legacy = base_dir / "conversations.json"
        if not legacy.exists() or self.index_file.exists():
            return
        try:
            data = json.loads(legacy.read_text(encoding="utf-8"))
        except Exception:
            return
        if not isinstance(data, dict):
            return
        with self._lock:
            for cid, conv in data.items():
                if not isinstance(conv, dict):
                    continue
                conv.setdefault("id", cid)
                conv.setdefault("title", "New chat")
                conv.setdefault("updated_at", int(time.time()))
                conv.setdefault("messages", [])
                self._save_conv(conv)
        # 保留原文件作为备份，重命名
        try:
            legacy.rename(legacy.with_suffix(".legacy.json"))
        except OSError:
            pass
