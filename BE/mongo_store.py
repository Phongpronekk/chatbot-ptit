"""MongoDB Atlas connection and source document repository.

Only source documents (data/*.md) are persisted to MongoDB.
Configuration is read from BE/.env:
- MONGODB_URI
- MONGODB_DB_NAME (default: ptit_chatbot)
- MONGODB_COLLECTION (default: source_documents)
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import re
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
logger = logging.getLogger(__name__)


def get_mongo_uri() -> str:
    return os.getenv("MONGODB_URI", "").strip()


def get_mongo_db_name() -> str:
    return os.getenv("MONGODB_DB_NAME", "ptit_chatbot").strip() or "ptit_chatbot"


def get_mongo_collection_name() -> str:
    return os.getenv("MONGODB_COLLECTION", "source_documents").strip() or "source_documents"


def get_temp_collection_name() -> str:
    return os.getenv("MONGODB_TEMP_COLLECTION", "temp_attachments").strip() or "temp_attachments"


def is_mongo_configured() -> bool:
    return bool(get_mongo_uri())


_CLIENT_POOL: dict[str, Any] = {}


def get_mongo_client(timeout_ms: int = 5000):
    uri = get_mongo_uri()
    if not uri:
        raise ValueError("Chưa cấu hình MONGODB_URI trong BE/.env")
    client = _CLIENT_POOL.get(uri)
    if client is None:
        import pymongo
        client = pymongo.MongoClient(
            uri,
            serverSelectionTimeoutMS=timeout_ms,
            connectTimeoutMS=timeout_ms,
            socketTimeoutMS=timeout_ms,
            maxPoolSize=20,
            retryWrites=True,
        )
        _CLIENT_POOL[uri] = client
    return client


def check_mongo_connection() -> dict[str, Any]:
    """Test connection and return collection health/status."""
    if not is_mongo_configured():
        return {
            "configured": False,
            "connected": False,
            "message": "Chưa cấu hình MONGODB_URI trong BE/.env",
        }
    client = None
    try:
        client = get_mongo_client()
        client.admin.command("ping")
        db = client[get_mongo_db_name()]
        col = db[get_mongo_collection_name()]
        count = col.count_documents({})
        conv_col_name = os.getenv("MONGODB_CONVERSATIONS_COLLECTION", "conversations").strip() or "conversations"
        msg_col_name = os.getenv("MONGODB_MESSAGES_COLLECTION", "messages").strip() or "messages"
        fb_col_name = os.getenv("MONGODB_FEEDBACK_COLLECTION", "feedback").strip() or "feedback"
        temp_col_name = get_temp_collection_name()
        return {
            "configured": True,
            "connected": True,
            "database": get_mongo_db_name(),
            "collection": get_mongo_collection_name(),
            "source_document_count": count,
            "conversation_count": db[conv_col_name].count_documents({}),
            "message_count": db[msg_col_name].count_documents({}),
            "feedback_count": db[fb_col_name].count_documents({}),
            "temp_attachment_count": db[temp_col_name].count_documents({}),
        }
    except Exception as exc:
        logger.warning("MongoDB ping failed: %s", exc)
        return {
            "configured": True,
            "connected": False,
            "error": f"{type(exc).__name__}: {exc}",
        }


def parse_source_file(path: Path) -> dict[str, Any]:
    """Read a data/*.md file, parse YAML front-matter, articles, and checksum."""
    text = path.read_text(encoding="utf-8-sig")
    match = re.match(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", text, re.S)
    if not match:
        raise ValueError(f"Thiếu front-matter: {path.name}")
    try:
        front = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        # Compatibility for handwritten single-line notes containing ': '
        front_text = match.group(1)
        repaired = re.sub(
            r"^note:[ \t]+([^\r\n]+)$",
            lambda m: 'note: ' + json.dumps(m.group(1), ensure_ascii=False) if ': ' in m.group(1) else m.group(0),
            front_text,
            flags=re.M,
        )
        front = yaml.safe_load(repaired) or {}

    articles: list[dict[str, Any]] = []
    for line in text.splitlines():
        marker = re.fullmatch(r"<!-- source_metadata: (.+) -->", line.strip())
        if marker:
            try:
                article = json.loads(marker.group(1))
                if isinstance(article, dict):
                    articles.append(article)
            except json.JSONDecodeError:
                pass

    return {
        "_id": path.name,
        "filename": path.name,
        "topic_group": str(front.get("topic_group", "")),
        "source_url": str(front.get("source_url", "")),
        "fetched_date": str(front.get("fetched_date", "")),
        "collection_year": front.get("collection_year", 2026),
        "note": str(front.get("note", "")),
        "metadata": {k: str(v) if v is not None else "" for k, v in front.items()},
        "article_count": len(articles) or int(front.get("article_count", 0)),
        "articles": articles,
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "file_size_bytes": path.stat().st_size,
        "character_count": len(text),
        "raw_content": text,
        "synced_at": datetime.now(timezone.utc).isoformat(),
    }


def sync_source_documents(data_dir: Path | None = None) -> dict[str, Any]:
    """Store copies of all source data files (data/*.md) into MongoDB Atlas."""
    if not is_mongo_configured():
        return {
            "success": False,
            "message": "Chưa cấu hình MONGODB_URI trong BE/.env",
            "synced_count": 0,
        }

    target_dir = Path(data_dir or (ROOT / "data")).resolve()
    if not target_dir.exists():
        raise FileNotFoundError(f"Không tìm thấy thư mục dữ liệu: {target_dir}")

    client = get_mongo_client()
    try:
        db = client[get_mongo_db_name()]
        col = db[get_mongo_collection_name()]

        synced_files: list[dict[str, Any]] = []
        total_bytes = 0

        for path in sorted(target_dir.glob("*.md")):
            doc = parse_source_file(path)
            col.replace_one({"_id": doc["_id"]}, doc, upsert=True)
            synced_files.append({
                "filename": doc["filename"],
                "topic_group": doc["topic_group"],
                "article_count": doc["article_count"],
                "size_bytes": doc["file_size_bytes"],
                "sha256": doc["sha256"],
            })
            total_bytes += doc["file_size_bytes"]

        logger.info("Đã đồng bộ %d file nguồn (%d bytes) lên MongoDB Atlas", len(synced_files), total_bytes)
        return {
            "success": True,
            "database": get_mongo_db_name(),
            "collection": get_mongo_collection_name(),
            "synced_count": len(synced_files),
            "total_bytes": total_bytes,
            "files": synced_files,
            "synced_at": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        pass


def get_source_documents(include_content: bool = False) -> list[dict[str, Any]]:
    """List all source documents stored in MongoDB."""
    if not is_mongo_configured():
        return []
    client = get_mongo_client()
    db = client[get_mongo_db_name()]
    col = db[get_mongo_collection_name()]
    projection = None if include_content else {"raw_content": 0}
    return list(col.find({}, projection).sort("filename", 1))


def get_source_document(filename: str) -> dict[str, Any] | None:
    """Fetch a single source document including full raw content from MongoDB."""
    if not is_mongo_configured():
        return None
    client = get_mongo_client()
    db = client[get_mongo_db_name()]
    col = db[get_mongo_collection_name()]
    return col.find_one({"_id": filename})


_ttl_index_initialized = False


def _ensure_temp_indexes(col) -> None:
    """Ensure MongoDB Native TTL index (`expireAfterSeconds=0`) on `expires_at`."""
    global _ttl_index_initialized
    if _ttl_index_initialized:
        return
    try:
        col.create_index("expires_at", expireAfterSeconds=0, name="ttl_expires_at")
        col.create_index([("owner", 1), ("conversation", 1)], name="idx_owner_conversation")
        _ttl_index_initialized = True
    except Exception as exc:
        logger.debug("Không thể tạo TTL index cho temp_attachments: %s", exc)


def save_temp_attachment(
    identifier: str,
    owner: str,
    conversation: str,
    metadata: dict[str, Any],
    chunks: list[dict[str, Any]],
    created_at: datetime,
    expires_at: datetime,
) -> bool:
    """Save temporary extracted file content to MongoDB with Native TTL index."""
    if not is_mongo_configured():
        return False
    client = None
    try:
        client = get_mongo_client(timeout_ms=3000)
        db = client[get_mongo_db_name()]
        col = db[get_temp_collection_name()]
        _ensure_temp_indexes(col)
        doc = {
            "_id": identifier,
            "owner": owner,
            "conversation": conversation,
            "metadata": dict(metadata),
            "chunks": list(chunks),
            "created_at": created_at,
            "expires_at": expires_at,
        }
        col.replace_one({"_id": identifier}, doc, upsert=True)
        return True
    except Exception as exc:
        logger.debug("Lưu file tạm lên MongoDB thất bại (dùng RAM fallback): %s", exc)
        return False


def get_temp_attachments_for_conversation(owner: str, conversation: str) -> list[dict[str, Any]]:
    """Load active (non-expired) temporary attachments for a conversation from MongoDB."""
    if not is_mongo_configured():
        return []
    try:
        client = get_mongo_client(timeout_ms=3000)
        db = client[get_mongo_db_name()]
        col = db[get_temp_collection_name()]
        now_utc = datetime.now(timezone.utc)
        cursor = col.find({
            "owner": owner,
            "conversation": conversation,
            "expires_at": {"$gt": now_utc},
        }).sort("created_at", 1)
        return list(cursor)
    except Exception as exc:
        logger.debug("Đọc file tạm từ MongoDB thất bại (dùng RAM fallback): %s", exc)
        return []


def delete_temp_attachments(owner: str, conversation: str, identifier: str | None = None) -> int:
    """Delete temporary attachment(s) from MongoDB."""
    if not is_mongo_configured():
        return 0
    try:
        client = get_mongo_client(timeout_ms=3000)
        db = client[get_mongo_db_name()]
        col = db[get_temp_collection_name()]
        query: dict[str, Any] = {"owner": owner, "conversation": conversation}
        if identifier is not None:
            query["_id"] = identifier
        res = col.delete_many(query)
        return res.deleted_count
    except Exception as exc:
        logger.debug("Xóa file tạm trên MongoDB thất bại: %s", exc)
        return 0


