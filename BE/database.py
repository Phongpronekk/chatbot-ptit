"""MongoDB-backed storage for conversations, messages, and feedback (with RAM fallback for offline tests).

No SQLite (`sqlite3`) is used. In production (`use_mongo=True` when `MONGODB_URI` is configured),
all conversations, messages, and user feedback (Like/Dislike) are persisted in MongoDB Atlas:
- `conversations` collection
- `messages` collection
- `feedback` collection
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import logging
import os
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4

if __package__:
    from .mongo_store import get_mongo_client, get_mongo_db_name, is_mongo_configured
else:
    from mongo_store import get_mongo_client, get_mongo_db_name, is_mongo_configured

logger = logging.getLogger(__name__)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_conversations_collection_name() -> str:
    return os.getenv("MONGODB_CONVERSATIONS_COLLECTION", "conversations").strip() or "conversations"


def get_messages_collection_name() -> str:
    return os.getenv("MONGODB_MESSAGES_COLLECTION", "messages").strip() or "messages"


def get_feedback_collection_name() -> str:
    return os.getenv("MONGODB_FEEDBACK_COLLECTION", "feedback").strip() or "feedback"


# Shared in-memory store for offline unit tests (keyed by logical store name so simulated restarts share state)
_MEMORY_STORES: dict[str, dict[str, Any]] = {}
_MEMORY_LOCK = RLock()


def _get_memory_store(key: str) -> dict[str, Any]:
    with _MEMORY_LOCK:
        if key not in _MEMORY_STORES:
            _MEMORY_STORES[key] = {
                "conversations": {},  # id -> dict
                "messages": [],       # list of message dicts in insertion order
                "feedback": {},       # message_id -> feedback dict
                "seq": 0,
            }
        return _MEMORY_STORES[key]


class Database:
    def __init__(self, path: Path | str | None = None, use_mongo: bool | None = None):
        self.path = Path(path) if path is not None else None
        if use_mongo is None:
            self.use_mongo = (self.path is None) and is_mongo_configured()
        else:
            self.use_mongo = use_mongo and is_mongo_configured()
        self._store_key = str(self.path.resolve()) if self.path is not None else "default"
        self._indexes_ensured = False

    def _with_mongo(self, fn):
        client = get_mongo_client(timeout_ms=5000)
        db = client[get_mongo_db_name()]
        return fn(
            db[get_conversations_collection_name()],
            db[get_messages_collection_name()],
            db[get_feedback_collection_name()],
        )

    def initialize(self):
        if self.use_mongo and is_mongo_configured():
            if self._indexes_ensured:
                return
            try:
                def _init_indexes(convs, msgs, fbs):
                    convs.create_index([("owner", 1), ("updated_at", -1)], name="idx_conv_owner_updated")
                    msgs.create_index([("conversation_id", 1), ("sequence", 1)], name="idx_msg_conv_seq")
                    msgs.create_index(
                        [("conversation_id", 1), ("request_id", 1), ("role", 1)],
                        unique=True,
                        name="uniq_conv_req_role",
                    )
                    fbs.create_index([("conversation_id", 1), ("created_at", -1)], name="idx_fb_conv_created")
                    fbs.create_index([("rating", 1), ("created_at", -1)], name="idx_fb_rating")

                self._with_mongo(_init_indexes)
                self._indexes_ensured = True
            except Exception as exc:
                logger.warning("Không thể khởi tạo index MongoDB cho hội thoại (dùng RAM fallback): %s", exc)
                self.use_mongo = False
        _get_memory_store(self._store_key)

    def list(self, owner: str) -> list[dict[str, Any]]:
        if self.use_mongo and is_mongo_configured():
            try:
                def _list(convs, _msgs, _fbs):
                    cursor = convs.find(
                        {"owner": owner},
                        {"_id": 0, "id": 1, "title": 1, "created_at": 1, "updated_at": 1},
                    ).sort([("updated_at", -1), ("id", 1)])
                    return list(cursor)

                return self._with_mongo(_list)
            except Exception as exc:
                logger.warning("Lỗi đọc danh sách hội thoại từ MongoDB: %s", exc)

        with _MEMORY_LOCK:
            store = _get_memory_store(self._store_key)
            items = [
                {
                    "id": c["id"],
                    "title": c["title"],
                    "created_at": c["created_at"],
                    "updated_at": c["updated_at"],
                }
                for c in store["conversations"].values()
                if c["owner"] == owner
            ]
            items.sort(key=lambda x: x["id"])
            items.sort(key=lambda x: x["updated_at"], reverse=True)
            return items

    def create(self, owner: str) -> dict[str, Any]:
        identifier, timestamp = str(uuid4()), now()
        doc = {
            "_id": identifier,
            "id": identifier,
            "owner": owner,
            "title": "Cuộc trò chuyện mới",
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        if self.use_mongo and is_mongo_configured():
            try:
                self._with_mongo(lambda convs, _msgs, _fbs: convs.replace_one({"_id": identifier}, doc, upsert=True))
                return {
                    "id": identifier,
                    "title": "Cuộc trò chuyện mới",
                    "created_at": timestamp,
                    "updated_at": timestamp,
                    "messages": [],
                }
            except Exception as exc:
                logger.warning("Lỗi tạo hội thoại trên MongoDB: %s", exc)

        with _MEMORY_LOCK:
            store = _get_memory_store(self._store_key)
            store["conversations"][identifier] = deepcopy(doc)
        return self.get(identifier, owner)

    def get(self, identifier: str, owner: str) -> dict[str, Any] | None:
        if self.use_mongo and is_mongo_configured():
            try:
                def _get(convs, msgs, fbs):
                    conv = convs.find_one(
                        {"_id": identifier, "owner": owner},
                        {"_id": 0, "id": 1, "title": 1, "created_at": 1, "updated_at": 1},
                    )
                    if conv is None:
                        return None
                    raw_msgs = list(
                        msgs.find({"conversation_id": identifier}, {"_id": 0}).sort("sequence", 1)
                    )
                    msg_ids = [m["id"] for m in raw_msgs]
                    fb_map = {}
                    if msg_ids:
                        for fb in fbs.find({"_id": {"$in": msg_ids}}, {"_id": 1, "rating": 1}):
                            fb_map[fb["_id"]] = fb.get("rating")
                    messages = []
                    for m in raw_msgs:
                        messages.append({
                            "id": m["id"],
                            "role": m["role"],
                            "text": m["text"],
                            "created_at": m["created_at"],
                            "mode": m["mode"],
                            "sources": list(m.get("sources") or []),
                            "attachments": list(m.get("attachments") or []),
                            "feedback": fb_map.get(m["id"], m.get("feedback")),
                        })
                    return {**conv, "messages": messages}

                return self._with_mongo(_get)
            except Exception as exc:
                logger.warning("Lỗi đọc hội thoại từ MongoDB: %s", exc)

        with _MEMORY_LOCK:
            store = _get_memory_store(self._store_key)
            conv = store["conversations"].get(identifier)
            if conv is None or conv["owner"] != owner:
                return None
            messages = []
            for m in store["messages"]:
                if m["conversation_id"] == identifier:
                    fb = store["feedback"].get(m["id"])
                    messages.append({
                        "id": m["id"],
                        "role": m["role"],
                        "text": m["text"],
                        "created_at": m["created_at"],
                        "mode": m["mode"],
                        "sources": deepcopy(m.get("sources") or []),
                        "attachments": deepcopy(m.get("attachments") or []),
                        "feedback": fb["rating"] if fb else m.get("feedback"),
                    })
            return {
                "id": conv["id"],
                "title": conv["title"],
                "created_at": conv["created_at"],
                "updated_at": conv["updated_at"],
                "messages": messages,
            }

    def has_request(self, identifier: str, request_id: str) -> bool:
        if self.use_mongo and is_mongo_configured():
            try:
                return self._with_mongo(
                    lambda _convs, msgs, _fbs: msgs.find_one(
                        {"conversation_id": identifier, "request_id": request_id, "role": "assistant"},
                        {"_id": 1},
                    ) is not None
                )
            except Exception as exc:
                logger.warning("Lỗi kiểm tra request_id trên MongoDB: %s", exc)

        with _MEMORY_LOCK:
            store = _get_memory_store(self._store_key)
            return any(
                m["conversation_id"] == identifier and m["request_id"] == request_id and m["role"] == "assistant"
                for m in store["messages"]
            )

    def save_turn(
        self,
        identifier: str,
        owner: str,
        request_id: str,
        question: str,
        answer: str,
        mode: str,
        sources: list[dict[str, Any]],
        attachments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        if self.use_mongo and is_mongo_configured():
            try:
                def _save(convs, msgs, _fbs):
                    conv = convs.find_one({"_id": identifier, "owner": owner})
                    if conv is None:
                        return False
                    exists = msgs.find_one({"conversation_id": identifier, "request_id": request_id})
                    if not exists:
                        first = msgs.find_one({"conversation_id": identifier}) is None
                        last_msg = msgs.find_one(
                            {"conversation_id": identifier},
                            sort=[("sequence", -1)],
                            projection={"sequence": 1},
                        )
                        base_seq = int(last_msg["sequence"]) if last_msg and "sequence" in last_msg else 0
                        timestamp = now()
                        for offset, (role, content, message_mode, refs, files) in enumerate(
                            (
                                ("user", question, "user", [], attachments or []),
                                ("assistant", answer, mode, sources, []),
                            ),
                            start=1,
                        ):
                            msg_id = str(uuid4())
                            msgs.insert_one({
                                "_id": msg_id,
                                "id": msg_id,
                                "sequence": base_seq + offset,
                                "conversation_id": identifier,
                                "request_id": request_id,
                                "role": role,
                                "text": content,
                                "created_at": timestamp,
                                "mode": message_mode,
                                "sources": list(refs),
                                "attachments": list(files),
                                "feedback": None,
                            })
                        update_fields: dict[str, Any] = {"updated_at": timestamp}
                        if first:
                            update_fields["title"] = question[:60]
                        convs.update_one({"_id": identifier}, {"$set": update_fields})
                    return True

                ok = self._with_mongo(_save)
                if not ok:
                    return None
                return self.get(identifier, owner)
            except Exception as exc:
                logger.warning("Lỗi lưu lượt hội thoại lên MongoDB: %s", exc)

        with _MEMORY_LOCK:
            store = _get_memory_store(self._store_key)
            conv = store["conversations"].get(identifier)
            if conv is None or conv["owner"] != owner:
                return None
            exists = any(
                m["conversation_id"] == identifier and m["request_id"] == request_id
                for m in store["messages"]
            )
            if not exists:
                first = not any(m["conversation_id"] == identifier for m in store["messages"])
                timestamp = now()
                for role, content, message_mode, refs, files in (
                    ("user", question, "user", [], attachments or []),
                    ("assistant", answer, mode, sources, []),
                ):
                    store["seq"] += 1
                    store["messages"].append({
                        "id": str(uuid4()),
                        "sequence": store["seq"],
                        "conversation_id": identifier,
                        "request_id": request_id,
                        "role": role,
                        "text": content,
                        "created_at": timestamp,
                        "mode": message_mode,
                        "sources": deepcopy(refs),
                        "attachments": deepcopy(files),
                        "feedback": None,
                    })
                conv["updated_at"] = timestamp
                if first:
                    conv["title"] = question[:60]
        return self.get(identifier, owner)

    def delete(self, identifier: str, owner: str) -> bool:
        if self.use_mongo and is_mongo_configured():
            try:
                def _delete(convs, msgs, fbs):
                    res = convs.delete_one({"_id": identifier, "owner": owner})
                    if res.deleted_count > 0:
                        msgs.delete_many({"conversation_id": identifier})
                        fbs.delete_many({"conversation_id": identifier})
                        return True
                    return False

                return self._with_mongo(_delete)
            except Exception as exc:
                logger.warning("Lỗi xóa hội thoại trên MongoDB: %s", exc)

        with _MEMORY_LOCK:
            store = _get_memory_store(self._store_key)
            conv = store["conversations"].get(identifier)
            if conv is None or conv["owner"] != owner:
                return False
            del store["conversations"][identifier]
            removed_msg_ids = {m["id"] for m in store["messages"] if m["conversation_id"] == identifier}
            store["messages"] = [m for m in store["messages"] if m["conversation_id"] != identifier]
            for mid in removed_msg_ids:
                store["feedback"].pop(mid, None)
            return True

    def save_feedback(self, message_id: str, owner: str, rating: int, comment: str | None = None) -> bool:
        timestamp = now()
        if self.use_mongo and is_mongo_configured():
            try:
                def _save_fb(convs, msgs, fbs):
                    msg = msgs.find_one({"_id": message_id})
                    if msg is None:
                        return False
                    conv = convs.find_one({"_id": msg["conversation_id"], "owner": owner})
                    if conv is None:
                        return False
                    user_msg = msgs.find_one({
                        "conversation_id": msg["conversation_id"],
                        "request_id": msg.get("request_id"),
                        "role": "user",
                    })
                    fb_doc = {
                        "_id": message_id,
                        "message_id": message_id,
                        "conversation_id": msg["conversation_id"],
                        "owner": owner,
                        "rating": rating,
                        "comment": comment,
                        "question": user_msg["text"] if user_msg else "",
                        "answer": msg["text"],
                        "mode": msg.get("mode", ""),
                        "sources": msg.get("sources", []),
                        "created_at": timestamp,
                    }
                    fbs.replace_one({"_id": message_id}, fb_doc, upsert=True)
                    msgs.update_one({"_id": message_id}, {"$set": {"feedback": rating}})
                    return True

                return self._with_mongo(_save_fb)
            except Exception as exc:
                logger.warning("Lỗi lưu feedback lên MongoDB: %s", exc)

        with _MEMORY_LOCK:
            store = _get_memory_store(self._store_key)
            target_msg = next((m for m in store["messages"] if m["id"] == message_id), None)
            if target_msg is None:
                return False
            conv = store["conversations"].get(target_msg["conversation_id"])
            if conv is None or conv["owner"] != owner:
                return False
            user_msg = next(
                (
                    m for m in store["messages"]
                    if m["conversation_id"] == target_msg["conversation_id"]
                    and m.get("request_id") == target_msg.get("request_id")
                    and m["role"] == "user"
                ),
                None,
            )
            target_msg["feedback"] = rating
            store["feedback"][message_id] = {
                "message_id": message_id,
                "conversation_id": target_msg["conversation_id"],
                "owner": owner,
                "rating": rating,
                "comment": comment,
                "question": user_msg["text"] if user_msg else "",
                "answer": target_msg["text"],
                "mode": target_msg.get("mode", ""),
                "sources": deepcopy(target_msg.get("sources", [])),
                "created_at": timestamp,
            }
            return True

    def list_feedback(self, rating: int | None = None, limit: int = 50) -> list[dict[str, Any]]:
        if self.use_mongo and is_mongo_configured():
            try:
                def _list_fb(_convs, _msgs, fbs):
                    flt: dict[str, Any] = {}
                    if rating in (-1, 1):
                        flt["rating"] = rating
                    return list(fbs.find(flt, {"_id": 0}).sort("created_at", -1).limit(limit))

                return self._with_mongo(_list_fb)
            except Exception as exc:
                logger.warning("Lỗi đọc feedback từ MongoDB: %s", exc)

        with _MEMORY_LOCK:
            store = _get_memory_store(self._store_key)
            items = list(store["feedback"].values())
            if rating in (-1, 1):
                items = [item for item in items if item["rating"] == rating]
            items.sort(key=lambda x: x["created_at"], reverse=True)
            return deepcopy(items[:limit])
