"""SQLite database management for user authentication, sessions, and chat history."""

from contextlib import closing
from datetime import datetime, timedelta
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import sqlite3

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = ROOT / "chat_data.db"


def get_db(db_path=DEFAULT_DB_PATH):
    conn = sqlite3.connect(str(db_path), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
    return f"{salt}${key.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt, expected = stored_hash.split("$", 1)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000).hex()
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def init_db(db_path=DEFAULT_DB_PATH):
    with closing(get_db(db_path)) as conn:
        with conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    username TEXT NOT NULL,
                    role TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    sender TEXT NOT NULL,
                    text TEXT NOT NULL,
                    passages TEXT,
                    model TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_conversations_user ON conversations(user_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, id ASC);
                CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token);
            """)

            # Create default admin if no admin exists
            cursor = conn.cursor()
            conn.execute("BEGIN IMMEDIATE")
            # Preserve existing accounts when upgrading databases created before account suspension.
            columns = {row["name"] for row in cursor.execute("PRAGMA table_info(users)")}
            if "is_active" not in columns:
                cursor.execute("ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
            cursor.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
            if not cursor.fetchone():
                admin_hash = hash_password("admin123")
                cursor.execute(
                    "INSERT OR IGNORE INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                    ("admin", admin_hash, "admin"),
                )


class AuthStore:
    def __init__(self, db_path=DEFAULT_DB_PATH):
        self.db_path = db_path
        init_db(self.db_path)

    def register_user(self, username, password, role="user"):
        username = username.strip()
        if not username or len(username) < 3 or len(username) > 50:
            raise ValueError("Tên đăng nhập phải từ 3 đến 50 ký tự.")
        if not password or len(password) < 6:
            raise ValueError("Mật khẩu phải từ 6 ký tự trở lên.")
        if role not in ("user", "admin"):
            role = "user"

        pw_hash = hash_password(password)
        with closing(get_db(self.db_path)) as conn:
            with conn:
                try:
                    cursor = conn.cursor()
                    cursor.execute(
                        "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                        (username, pw_hash, role),
                    )
                    user_id = cursor.lastrowid
                    return {"id": user_id, "username": username, "role": role}
                except sqlite3.IntegrityError:
                    raise ValueError(f"Tài khoản '{username}' đã tồn tại.")

    def authenticate_user(self, username, password):
        username = username.strip()
        with closing(get_db(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, username, password_hash, role FROM users WHERE username = ? AND is_active = 1", (username,))
            row = cursor.fetchone()
            if not row:
                return None
            if not verify_password(password, row["password_hash"]):
                return None
            return {"id": row["id"], "username": row["username"], "role": row["role"]}

    def create_session(self, user_id, username, role, days=7, *, password=None):
        token = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(days=days)
        with closing(get_db(self.db_path)) as conn:
            with conn:
                cursor = conn.cursor()
                conn.execute("BEGIN IMMEDIATE")
                account = cursor.execute(
                    "SELECT username, role, password_hash FROM users WHERE id = ? AND is_active = 1", (user_id,),
                ).fetchone()
                if not account or account["username"] != username or account["role"] != role:
                    raise ValueError("Tài khoản đã thay đổi hoặc ngừng hoạt động. Hãy đăng nhập lại.")
                if password is not None and not verify_password(password, account["password_hash"]):
                    raise ValueError("Thông tin đăng nhập đã thay đổi. Hãy đăng nhập lại.")
                cursor.execute(
                    "INSERT INTO sessions (token, user_id, username, role, expires_at) VALUES (?, ?, ?, ?, ?)",
                    (token, user_id, username, role, expires_at.isoformat()),
                )
        return token

    def get_session(self, token):
        if not token:
            return None
        with closing(get_db(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT s.user_id, u.username, u.role, s.expires_at FROM sessions s "
                "JOIN users u ON u.id = s.user_id WHERE s.token = ? AND u.is_active = 1", (token,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            try:
                expires_at = datetime.fromisoformat(row["expires_at"])
                if expires_at < datetime.utcnow():
                    with conn:
                        cursor.execute("DELETE FROM sessions WHERE token = ?", (token,))
                    return None
            except Exception:
                return None
            return {"user_id": row["user_id"], "username": row["username"], "role": row["role"]}

    def delete_session(self, token):
        if not token:
            return
        with closing(get_db(self.db_path)) as conn:
            with conn:
                conn.execute("DELETE FROM sessions WHERE token = ?", (token,))

    def get_all_users(self):
        with closing(get_db(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, username, role, created_at, is_active FROM users ORDER BY id ASC")
            return [dict(row) for row in cursor.fetchall()]

    def update_user(self, user_id, changes):
        if not isinstance(changes, dict) or not changes or changes.keys() - {"username", "password", "is_active"}:
            raise ValueError("Thông tin cập nhật không hợp lệ.")
        values = dict(changes)
        if "username" in values:
            username = values["username"]
            if not isinstance(username, str) or not 3 <= len(username.strip()) <= 50:
                raise ValueError("Tên đăng nhập phải từ 3 đến 50 ký tự.")
            values["username"] = username.strip()
        if "password" in values:
            password = values.pop("password")
            if not isinstance(password, str) or len(password) < 6:
                raise ValueError("Mật khẩu phải từ 6 ký tự trở lên.")
            values["password_hash"] = hash_password(password)
        if "is_active" in values and type(values["is_active"]) is not bool:
            raise ValueError("Trạng thái hoạt động không hợp lệ.")
        with closing(get_db(self.db_path)) as conn:
            with conn:
                conn.execute("BEGIN IMMEDIATE")
                account = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
                if not account:
                    raise LookupError("Không tìm thấy tài khoản.")
                if account["role"] == "admin":
                    raise PermissionError("Chỉ có thể thao tác trên tài khoản người dùng.")
                assignments = ", ".join(f"{field} = ?" for field in values)
                try:
                    conn.execute(f"UPDATE users SET {assignments} WHERE id = ?", (*values.values(), user_id))
                except sqlite3.IntegrityError:
                    raise ValueError("Tên đăng nhập đã tồn tại.") from None
                conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))

    def delete_user(self, user_id):
        with closing(get_db(self.db_path)) as conn:
            with conn:
                conn.execute("BEGIN IMMEDIATE")
                account = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
                if not account:
                    raise LookupError("Không tìm thấy tài khoản.")
                if account["role"] == "admin":
                    raise PermissionError("Chỉ có thể thao tác trên tài khoản người dùng.")
                conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
                conn.execute("DELETE FROM messages WHERE conversation_id IN "
                             "(SELECT id FROM conversations WHERE user_id = ?)", (user_id,))
                conn.execute("DELETE FROM conversations WHERE user_id = ?", (user_id,))
                conn.execute("DELETE FROM users WHERE id = ?", (user_id,))


class HistoryStore:
    def __init__(self, db_path=DEFAULT_DB_PATH):
        self.db_path = db_path
        init_db(self.db_path)

    def get_conversations(self, user_id):
        with closing(get_db(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, title, created_at, updated_at FROM conversations WHERE user_id = ? ORDER BY updated_at DESC",
                (user_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def create_conversation(self, user_id, conv_id, title="Cuộc trò chuyện mới"):
        now = datetime.utcnow().isoformat()
        with closing(get_db(self.db_path)) as conn:
            with conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT OR REPLACE INTO conversations (id, user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (conv_id, user_id, title, now, now),
                )
        return {"id": conv_id, "user_id": user_id, "title": title, "updated_at": now}

    def update_title(self, user_id, conv_id, title):
        with closing(get_db(self.db_path)) as conn:
            with conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                    (title, datetime.utcnow().isoformat(), conv_id, user_id),
                )

    def delete_conversation(self, user_id, conv_id):
        with closing(get_db(self.db_path)) as conn:
            with conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM messages WHERE conversation_id = ? AND conversation_id IN (SELECT id FROM conversations WHERE user_id = ?)", (conv_id, user_id))
                cursor.execute("DELETE FROM conversations WHERE id = ? AND user_id = ?", (conv_id, user_id))

    def get_messages(self, user_id, conv_id):
        with closing(get_db(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id FROM conversations WHERE id = ? AND user_id = ?",
                (conv_id, user_id),
            )
            if not cursor.fetchone():
                return None
            cursor.execute(
                "SELECT id, sender, text, passages, model, created_at FROM messages WHERE conversation_id = ? ORDER BY id ASC",
                (conv_id,),
            )
            rows = cursor.fetchall()
            messages = []
            for r in rows:
                item = dict(r)
                if item.get("passages"):
                    try:
                        item["passages"] = json.loads(item["passages"])
                    except Exception:
                        item["passages"] = []
                messages.append(item)
            return messages

    def add_message(self, user_id, conv_id, sender, text, passages=None, model=None, conv_title=None):
        now = datetime.utcnow().isoformat()
        passages_json = json.dumps(passages, ensure_ascii=False) if passages else None
        with closing(get_db(self.db_path)) as conn:
            with conn:
                cursor = conn.cursor()
                # Verify or create conversation
                cursor.execute("SELECT id FROM conversations WHERE id = ? AND user_id = ?", (conv_id, user_id))
                if not cursor.fetchone():
                    title = conv_title or (text[:40] + "..." if len(text) > 40 else text)
                    cursor.execute(
                        "INSERT INTO conversations (id, user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                        (conv_id, user_id, title, now, now),
                    )
                else:
                    cursor.execute(
                        "UPDATE conversations SET updated_at = ? WHERE id = ? AND user_id = ?",
                        (now, conv_id, user_id),
                    )

                cursor.execute(
                    "INSERT INTO messages (conversation_id, sender, text, passages, model, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (conv_id, sender, text, passages_json, model, now),
                )
                return cursor.lastrowid
