from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=15)
        try:
            with connection:
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA foreign_keys = ON")
                yield connection
        finally:
            connection.close()

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript("""
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, title TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS conversations_owner ON conversations(owner);
                CREATE TABLE IF NOT EXISTS messages (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    id TEXT UNIQUE NOT NULL,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    request_id TEXT NOT NULL, role TEXT NOT NULL, text TEXT NOT NULL,
                    created_at TEXT NOT NULL, mode TEXT NOT NULL, sources TEXT NOT NULL,
                    UNIQUE(conversation_id, request_id, role)
                );
            """)

    def list(self, owner: str):
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(
                "SELECT id,title,created_at,updated_at FROM conversations WHERE owner=? ORDER BY updated_at DESC,id",
                (owner,),
            )]

    def create(self, owner: str):
        identifier, timestamp = str(uuid4()), now()
        with self.connect() as connection:
            connection.execute("INSERT INTO conversations VALUES (?,?,?,?,?)",
                               (identifier, owner, "Cuộc trò chuyện mới", timestamp, timestamp))
        return self.get(identifier, owner)

    def get(self, identifier: str, owner: str):
        with self.connect() as connection:
            row = connection.execute(
                "SELECT id,title,created_at,updated_at FROM conversations WHERE id=? AND owner=?",
                (identifier, owner),
            ).fetchone()
            if row is None:
                return None
            messages = []
            for message in connection.execute(
                "SELECT id,role,text,created_at,mode,sources FROM messages WHERE conversation_id=? ORDER BY sequence",
                (identifier,),
            ):
                item = dict(message)
                item["sources"] = json.loads(item["sources"])
                messages.append(item)
            return {**dict(row), "messages": messages}

    def has_request(self, identifier: str, request_id: str):
        with self.connect() as connection:
            return connection.execute(
                "SELECT 1 FROM messages WHERE conversation_id=? AND request_id=? AND role='assistant'",
                (identifier, request_id),
            ).fetchone() is not None

    def save_turn(self, identifier: str, owner: str, request_id: str, question: str,
                  answer: str, mode: str, sources: list[dict]):
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT 1 FROM conversations WHERE id=? AND owner=?",
                                     (identifier, owner)).fetchone()
            if row is None:
                return None
            exists = connection.execute(
                "SELECT 1 FROM messages WHERE conversation_id=? AND request_id=?", (identifier, request_id)
            ).fetchone()
            if not exists:
                first = connection.execute("SELECT 1 FROM messages WHERE conversation_id=?", (identifier,)).fetchone() is None
                timestamp = now()
                for role, content, message_mode, refs in (
                    ("user", question, "user", []), ("assistant", answer, mode, sources)
                ):
                    connection.execute(
                        "INSERT INTO messages (id,conversation_id,request_id,role,text,created_at,mode,sources) VALUES (?,?,?,?,?,?,?,?)",
                        (str(uuid4()), identifier, request_id, role, content, timestamp, message_mode,
                         json.dumps(refs, ensure_ascii=False)),
                    )
                connection.execute("UPDATE conversations SET updated_at=? WHERE id=?", (timestamp, identifier))
                if first:
                    connection.execute("UPDATE conversations SET title=? WHERE id=?", (question[:60], identifier))
        return self.get(identifier, owner)

    def delete(self, identifier: str, owner: str):
        with self.connect() as connection:
            return connection.execute("DELETE FROM conversations WHERE id=? AND owner=?", (identifier, owner)).rowcount > 0
