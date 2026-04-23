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
        return conv

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

    # ── 内部实现 ──────────────────────────────────────────

    def _conv_path(self, conversation_id: str) -> Path | None:
        safe = _SAFE_ID_RE.sub("", conversation_id or "")[:64]
        if not safe:
            return None
        return self.dir / f"{safe}.json"

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
