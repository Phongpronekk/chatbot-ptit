"""Serve the PTIT chatbot demo, user authentication, chat history, and admin document management."""

import argparse
from contextlib import closing, suppress
from dataclasses import asdict
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
from pathlib import Path
import threading
from time import perf_counter
from urllib.parse import unquote, urlsplit

from conversation import (
    MAX_QUESTION_CHARS, is_follow_up, is_greeting_only, is_immediate_summary, passage_id, read_history,
    resolve_person_reference,
)
from database import AuthStore, HistoryStore
from gemini import ContextResolution, Gemini, GenerationError, IncompleteGenerationError
from knowledge_manager import KnowledgeManager
from retrieval import KnowledgeBase
from uploads import MAX_UPLOAD_BYTES, UploadError, UploadStore, index_upload, is_document_overview

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/admin": ("admin.html", "text/html; charset=utf-8"),
    "/admin.html": ("admin.html", "text/html; charset=utf-8"),
    "/admin/accounts": ("admin-accounts.html", "text/html; charset=utf-8"),
    "/admin.css": ("admin.css", "text/css; charset=utf-8"),
    "/admin.js": ("admin.js", "text/javascript; charset=utf-8"),
    "/admin-accounts.js": ("admin-accounts.js", "text/javascript; charset=utf-8"),
    "/admin-session.js": ("admin-session.js", "text/javascript; charset=utf-8"),
}
ADMIN_PAGES = {"/admin", "/admin/accounts"}
MAX_BODY = 10 * 1024 * 1024  # 10 MB for admin uploads
MAX_CHAT_BODY = 131_072
LOGGER = logging.getLogger(__name__)


class Handler(BaseHTTPRequestHandler):
    def send_bytes(self, status, data, content_type, headers=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        if headers:
            for k, v in headers.items():
                self.send_header(k, v)
        if content_type.startswith("application/json"):
            self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, status, data, headers=None):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_bytes(status, body, "application/json; charset=utf-8", headers=headers)

    def get_token(self):
        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:].strip()
        cookie_header = self.headers.get("Cookie", "")
        for item in cookie_header.split(";"):
            parts = item.strip().split("=", 1)
            if len(parts) == 2 and parts[0] == "session_token":
                return parts[1]
        return None

    def get_current_user(self):
        token = self.get_token()
        if not token:
            return None
        return self.server.auth.get_session(token)

    def require_auth(self):
        user = self.get_current_user()
        if not user:
            self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "Cần đăng nhập để thực hiện thao tác này."})
            return None
        return user

    def require_admin(self):
        user = self.require_auth()
        if not user:
            return None
        if user.get("role") != "admin":
            self.send_json(HTTPStatus.FORBIDDEN, {"error": "Chỉ tài khoản Quản trị viên (Admin) mới có quyền truy cập."})
            return None
        return user

    def allow_chat(self, user):
        if user and user["role"] == "admin":
            self.close_connection = True
            # Windows can reset the connection before delivering the response if the body remains unread.
            with suppress(ValueError, OSError):
                size = int(self.headers.get("Content-Length", "0"))
                if 0 < size <= MAX_BODY:
                    self.connection.settimeout(1)
                    self.rfile.read(size)
            self.send_json(HTTPStatus.FORBIDDEN, {"error": "Tài khoản quản trị chỉ có quyền quản lý."})
            return False
        return True

    def require_chat_user(self):
        user = self.require_auth()
        if user and self.allow_chat(user):
            return user
        return None

    def read_json_body(self):
        size = int(self.headers.get("Content-Length", "0"))
        if not 0 < size <= 65536:
            raise ValueError("Kích thước dữ liệu không hợp lệ.")
        raw = self.rfile.read(size)
        return json.loads(raw.decode("utf-8"))

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/api/status":
            generator = self.server.generator
            vs = getattr(self.server.index, "vector", None)
            self.send_json(HTTPStatus.OK, {
                "documents": self.server.index.document_count,
                "retrieval": getattr(self.server, "retrieval_mode", "keyword"),
                "embedding_model": vs.model_name if vs else None,
                "model": generator.model if generator else None,
            })
            return

        if path == "/api/auth/me":
            user = self.get_current_user()
            if not user:
                self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "Chưa đăng nhập."})
            else:
                self.send_json(HTTPStatus.OK, {"user": user})
            return

        if path == "/api/conversations":
            user = self.require_chat_user()
            if not user:
                return
            convs = self.server.history.get_conversations(user["user_id"])
            self.send_json(HTTPStatus.OK, {"conversations": convs})
            return

        if path.startswith("/api/conversations/"):
            user = self.require_chat_user()
            if not user:
                return
            conv_id = path.split("/api/conversations/", 1)[1]
            messages = self.server.history.get_messages(user["user_id"], conv_id)
            if messages is None:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "Không tìm thấy cuộc trò chuyện."})
                return
            self.send_json(HTTPStatus.OK, {"messages": messages})
            return

        if path == "/api/admin/documents":
            if not self.require_admin():
                return
            docs = self.server.knowledge_manager.list_documents()
            self.send_json(HTTPStatus.OK, {"documents": docs})
            return

        if path == "/api/admin/users":
            if not self.require_admin():
                return
            users = self.server.auth.get_all_users()
            self.send_json(HTTPStatus.OK, {"users": users})
            return

        if path in STATIC:
            headers = None
            if path in ADMIN_PAGES or path in {"/", "/admin.html"}:
                headers = {"Cache-Control": "no-store"}
                user = self.get_current_user()
                destination = "/"
                if user and user["role"] == "admin":
                    destination = path if path in ADMIN_PAGES else "/admin"
                if destination != path:
                    self.send_bytes(HTTPStatus.FOUND, b"", "text/plain", {**headers, "Location": destination})
                    return
            file, media_type = STATIC[path]
            self.send_bytes(HTTPStatus.OK, (FRONTEND / file).read_bytes(), media_type, headers=headers)
            return

        self.send_json(HTTPStatus.NOT_FOUND, {"error": "Không tìm thấy địa chỉ."})

    def do_POST(self):
        path = urlsplit(self.path).path
        if path == "/api/auth/register":
            self.auth_register()
        elif path == "/api/auth/login":
            self.auth_login()
        elif path == "/api/auth/logout":
            self.auth_logout()
        elif path == "/api/conversations":
            self.create_conversation()
        elif path == "/api/admin/documents":
            self.admin_upload_document()
        elif path == "/api/admin/reindex":
            self.admin_reindex()
        elif path == "/api/uploads":
            self.upload_document()
        elif path == "/api/chat":
            self.chat()
        elif path == "/api/transcribe":
            self.transcribe_audio()
        else:
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "Không tìm thấy địa chỉ."})

    def do_DELETE(self):
        path = urlsplit(self.path).path
        if path.startswith("/api/admin/users/"):
            self.admin_change_user(path, delete=True)
            return
        if path.startswith("/api/conversations/"):
            user = self.require_chat_user()
            if not user:
                return
            conv_id = path.split("/api/conversations/", 1)[1]
            self.server.history.delete_conversation(user["user_id"], conv_id)
            self.send_json(HTTPStatus.OK, {"deleted": conv_id})
            return

        if path.startswith("/api/admin/documents/"):
            if not self.require_admin():
                return
            filename = unquote(path.split("/api/admin/documents/", 1)[1])
            try:
                res = self.server.knowledge_manager.delete_document(filename)
                self.send_json(HTTPStatus.OK, res)
            except Exception as e:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(e)})
            return

        self.send_json(HTTPStatus.NOT_FOUND, {"error": "Không tìm thấy địa chỉ."})

    def do_PATCH(self):
        path = urlsplit(self.path).path
        if path.startswith("/api/admin/users/"):
            self.admin_change_user(path)
            return
        if path.startswith("/api/conversations/"):
            user = self.require_chat_user()
            if not user:
                return
            conv_id = path.split("/api/conversations/", 1)[1]
            try:
                data = self.read_json_body()
                title = data.get("title", "").strip()
                if not title:
                    raise ValueError("Tiêu đề không được để trống.")
                self.server.history.update_title(user["user_id"], conv_id, title)
                self.send_json(HTTPStatus.OK, {"id": conv_id, "title": title})
            except Exception as e:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(e)})
            return
        self.send_json(HTTPStatus.NOT_FOUND, {"error": "Không tìm thấy địa chỉ."})

    # --- Auth Handlers ---

    def auth_register(self):
        try:
            data = self.read_json_body()
            username = data.get("username", "")
            password = data.get("password", "")
            if data.get("role", "user") != "user":
                raise ValueError("Đăng ký chỉ dành cho tài khoản người dùng.")
            user = self.server.auth.register_user(username, password)
            token = self.server.auth.create_session(user["id"], user["username"], user["role"])
            cookie = f"session_token={token}; Path=/; SameSite=Lax; Max-Age=604800"
            self.send_json(HTTPStatus.CREATED, {"user": user, "token": token}, headers={"Set-Cookie": cookie})
        except ValueError as e:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(e)})
        except Exception as e:
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Không thể đăng ký lúc này."})

    def auth_login(self):
        try:
            data = self.read_json_body()
            username = data.get("username", "")
            password = data.get("password", "")
            user = self.server.auth.authenticate_user(username, password)
            if not user:
                self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "Tài khoản hoặc mật khẩu không chính xác."})
                return
            token = self.server.auth.create_session(user["id"], user["username"], user["role"], password=password)
            cookie = f"session_token={token}; Path=/; SameSite=Lax; Max-Age=604800"
            self.send_json(HTTPStatus.OK, {"user": user, "token": token}, headers={"Set-Cookie": cookie})
        except Exception as e:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Dữ liệu đăng nhập không hợp lệ."})

    def auth_logout(self):
        token = self.get_token()
        if token:
            self.server.auth.delete_session(token)
        cookie = "session_token=; Path=/; SameSite=Lax; Max-Age=0"
        self.send_json(HTTPStatus.OK, {"message": "Đã đăng xuất."}, headers={"Set-Cookie": cookie})

    def create_conversation(self):
        user = self.require_chat_user()
        if not user:
            return
        try:
            data = self.read_json_body()
            conv_id = data.get("id")
            title = data.get("title", "Cuộc trò chuyện mới")
            if not conv_id:
                raise ValueError("Thiếu mã cuộc trò chuyện.")
            res = self.server.history.create_conversation(user["user_id"], conv_id, title)
            self.send_json(HTTPStatus.CREATED, res)
        except Exception as e:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(e)})

    # --- Admin Handlers ---

    def admin_change_user(self, path, *, delete=False):
        if not self.require_admin():
            return
        try:
            user_id = path.removeprefix("/api/admin/users/")
            if not user_id.isascii() or not user_id.isdigit():
                raise LookupError("Không tìm thấy tài khoản.")
            if delete:
                self.server.auth.delete_user(int(user_id))
            else:
                self.server.auth.update_user(int(user_id), self.read_json_body())
            self.send_json(HTTPStatus.OK, {"success": True})
        except PermissionError as error:
            self.send_json(HTTPStatus.FORBIDDEN, {"error": str(error)})
        except LookupError as error:
            self.send_json(HTTPStatus.NOT_FOUND, {"error": str(error)})
        except (ValueError, UnicodeError) as error:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})

    def admin_upload_document(self):
        if not self.require_admin():
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= MAX_BODY:
                raise ValueError("Tệp không có nội dung hoặc vượt quá giới hạn 10 MB.")
            filename = unquote(self.headers.get("X-File-Name", ""), errors="strict")
            if not filename:
                raise ValueError("Thiếu tên tệp (X-File-Name).")
            data = self.rfile.read(size)
            result = self.server.knowledge_manager.add_document(filename, data)
            self.send_json(HTTPStatus.CREATED, result)
        except ValueError as e:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(e)})
        except Exception as e:
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": f"Lỗi xử lý tài liệu: {str(e)}"})

    def admin_reindex(self):
        if not self.require_admin():
            return
        try:
            result = self.server.knowledge_manager.reindex_all()
            self.send_json(HTTPStatus.OK, result)
        except Exception as e:
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(e)})

    # --- Existing Chat & Upload Functions ---

    def transcribe_audio(self):
        if not self.allow_chat(self.get_current_user()):
            return
        generator = self.server.generator
        if not generator:
            with suppress(Exception):
                self.server.generator = Gemini.from_config(ROOT / ".env")
                generator = self.server.generator
        if not generator:
            self.send_json(HTTPStatus.SERVICE_UNAVAILABLE, {
                "error": "Chưa cấu hình GEMINI_API_KEY trong file .env để nhận diện giọng nói qua máy chủ."
            })
            return

        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            size = 0

        max_audio_bytes = 10 * 1024 * 1024
        if size > max_audio_bytes:
            self.send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "Bản ghi âm vượt quá 10 MB."})
            return
        if size <= 0:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Chưa có dữ liệu âm thanh."})
            return

        raw_content_type = self.headers.get("Content-Type", "audio/webm")
        data = self.rfile.read(size)
        if len(data) != size:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Chưa nhận đủ dữ liệu âm thanh."})
            return

        try:
            text = generator.transcribe_audio(data, mime_type=raw_content_type)
            self.send_json(HTTPStatus.OK, {"text": text})
        except GenerationError as error:
            self.send_json(HTTPStatus.BAD_GATEWAY, {"error": str(error)})
        except Exception as error:
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Không thể nhận diện giọng nói lúc này."})

    def upload_document(self):
        if not self.allow_chat(self.get_current_user()):
            return
        if self.headers.get_content_type() != "application/octet-stream":
            self.send_json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": "Cần gửi nội dung tệp."})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            size = 0
        if size > MAX_UPLOAD_BYTES:
            self.send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "Tệp vượt quá 10 MB."})
            return
        if size <= 0:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Tệp chưa có nội dung."})
            return
        try:
            name = unquote(self.headers.get("X-Upload-Name", ""), errors="strict")
            data = self.rfile.read(size)
            if len(data) != size:
                raise UploadError("Chưa nhận đủ dữ liệu của tệp. Hãy tải lại.")
            document = index_upload(name, data)
        except UnicodeError:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Tên tệp không hợp lệ."})
            return
        except UploadError as error:
            self.send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(error)})
            return
        upload_id = self.server.uploads.add(document)
        self.send_json(HTTPStatus.CREATED, {"upload_id": upload_id, "name": document.name})

    def chat(self):
        user = self.get_current_user()
        if not self.allow_chat(user):
            return
        if self.headers.get_content_type() != "application/json":
            self.send_json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": "Cần gửi dữ liệu JSON."})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= MAX_CHAT_BODY:
                raise ValueError
            payload = json.loads(self.rfile.read(size))
            question = payload.get("question", "") if isinstance(payload, dict) else ""
            if not isinstance(question, str) or not 0 < len(question.strip()) <= MAX_QUESTION_CHARS:
                raise ValueError
        except (ValueError, UnicodeError):
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Nhập câu hỏi từ 1 đến 500 ký tự."})
            return
        try:
            history = read_history(payload.get("history", []))
        except ValueError:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Lịch sử câu hỏi không hợp lệ."})
            return

        conversation_id = payload.get("conversation_id")

        upload_id = payload.get("upload_id")
        if upload_id is not None and (not isinstance(upload_id, str) or len(upload_id) != 32):
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Mã tệp không hợp lệ."})
            return
        question = question.strip()
        if is_greeting_only(question):
            self.send_json(HTTPStatus.OK, {
                "intent": "greeting", "answer": "Chào bạn!", "passages": [],
            })
            return
        document = self.server.uploads.get(upload_id) if upload_id is not None else None
        if upload_id is not None and document is None:
            self.send_json(HTTPStatus.NOT_FOUND, {
                "error": "Tệp không còn sẵn sàng. Hãy tải lại tệp hoặc chọn không dùng tệp.",
                "code": "upload_unavailable",
            })
            return
        def clarify(answer, *, error=None):
            result = {"intent": "clarification", "answer": answer,
                      "passages": [], "source_ids": []}
            if error:
                result["context_error"] = error
            if document is not None:
                result["document"] = document.name
            self.send_json(HTTPStatus.OK, result)

        original_question = question
        generator = self.server.generator
        index = document if document is not None else self.server.index
        passages = []
        context_person = None
        operation = "document_overview" if document and is_document_overview(question) else "question"
        answer_history = []
        person = resolve_person_reference(question, history) if document else None
        context_started = perf_counter()
        if generator and history and operation != "document_overview":
            previous = history[-1]
            try:
                if (is_immediate_summary(question) and previous.get("source_ids")
                        and not previous.get("answer_truncated")
                        and previous.get("intent") != "clarification"):
                    resolution = ContextResolution(
                        "transform", question, history_index=len(history) - 1,
                    )
                else:
                    resolution = generator.resolve_context(question, history)
            except GenerationError as error:
                LOGGER.warning("Context resolution failed after %.0f ms: %s",
                               (perf_counter() - context_started) * 1000, error)
                clarify(
                    "Mình chưa làm rõ được ngữ cảnh. Bạn hãy gửi lại câu hỏi "
                    "kèm chủ đề, đối tượng hoặc tên người đang nhắc tới nhé.",
                    error=str(error),
                )
                return
            if resolution.intent == "clarification":
                clarify(resolution.clarification)
                return
            question = resolution.question
            if resolution.intent == "transform":
                target = history[resolution.history_index]
                if target.get("intent") == "clarification" or target.get("answer_truncated"):
                    clarify("Lượt đó chưa có câu trả lời đầy đủ để tóm tắt hoặc giải thích. "
                            "Bạn hãy gửi lại câu hỏi gốc nhé.")
                    return
                # Resolve IDs only against the active corpus/file; never trust browser source text.
                source_index = document.index if document is not None else getattr(index, "keyword", index)
                available = {passage_id(passage): passage for passage in source_index.passages}
                source_ids = target.get("source_ids", [])
                if not source_ids or any(key not in available for key in source_ids):
                    clarify("Mình chưa có đủ nguồn của lượt đó để tóm tắt hoặc giải thích. "
                            "Bạn hãy gửi lại câu hỏi đầy đủ để mình tra cứu nhé.")
                    return
                passages = [available[key] for key in source_ids]
                answer_history = [target]
                operation = "transform"
        search_started = perf_counter()
        if operation in {"question", "document_overview"}:
            if person and (not generator or question == person[0]):
                resolved, name = person
                passages = document.search(resolved, required_phrase=name)
                if passages:
                    question = resolved
                    context_person = name
            if not passages:
                if history and not generator and operation == "question" and is_follow_up(question):
                    clarify("Mình chưa làm rõ được câu hỏi tiếp nối. Bạn hãy ghi đầy đủ "
                            "chủ đề, đối tượng hoặc tên người muốn tra cứu nhé.",
                            error="Chưa bật Gemini để xử lý ngữ cảnh.")
                    return
                passages = index.search(question)
        timing = (
            f"context;dur={(search_started - context_started) * 1000:.1f}, "
            f"retrieval;dur={(perf_counter() - search_started) * 1000:.1f}"
        )
        # Save user question to DB in background
        if user and conversation_id:
            threading.Thread(
                target=self.server.history.add_message,
                args=(user["user_id"], conversation_id, "user", original_question),
                daemon=True,
            ).start()

        result = {"intent": "question" if operation == "document_overview" else operation,
                  "passages": [asdict(passage) for passage in passages],
                  "source_ids": [passage_id(passage) for passage in passages]}
        if question != original_question:
            result["resolved_question"] = question
        if context_person is not None:
            result["context_person"] = context_person
        if document is not None:
            result["document"] = document.name

        if generator and passages and self.headers.get("Accept") == "application/x-ndjson":
            with suppress(ConnectionError):
                self.stream_answer(question, passages, result, generator,
                                   history=answer_history, operation=operation,
                                   user=user, conversation_id=conversation_id, timing=timing)
            return

        if generator and passages:
            try:
                answer = generator.answer(question, passages, history=answer_history,
                                          operation=operation, require_complete=True)
                result["answer"] = answer
                result["model"] = generator.model
                if user and conversation_id:
                    threading.Thread(
                        target=self.server.history.add_message,
                        args=(
                            user["user_id"],
                            conversation_id,
                            "bot",
                            answer,
                            [asdict(p) for p in passages],
                            generator.model,
                        ),
                        daemon=True,
                    ).start()
            except GenerationError as error:
                result["generation_error"] = str(error)
        elif not passages and generator:
            # Fallback when no passages found
            answer = "Không tìm thấy thông tin phù hợp trong kho tài liệu hiện tại."
            result["answer"] = answer
            if user and conversation_id:
                threading.Thread(
                    target=self.server.history.add_message,
                    args=(
                        user["user_id"],
                        conversation_id,
                        "bot",
                        answer,
                        [],
                    ),
                    daemon=True,
                ).start()

        self.send_json(HTTPStatus.OK, result, headers={"Server-Timing": timing})

    def stream_answer(self, question, passages, result, generator, *, history=(),
                      operation="question", user=None, conversation_id=None, timing):
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Server-Timing", timing)
        self.send_header("Connection", "close")
        self.close_connection = True
        self.end_headers()

        def send_event(event):
            self.wfile.write((json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8"))
            self.wfile.flush()

        collected_answer = []

        try:
            send_event({**result, "model": generator.model})
            with closing(generator.stream_answer(question, passages, history=history,
                                                 operation=operation)) as stream:
                for delta in stream:
                    collected_answer.append(delta)
                    send_event({"delta": delta})
        except IncompleteGenerationError:
            try:
                answer = generator.answer(question, passages, history=history, operation=operation,
                                          require_complete=True)
                collected_answer = [answer]
            except GenerationError as error:
                send_event({"generation_error": str(error), "done": True})
            else:
                send_event({"answer": answer, "done": True})
        except GenerationError as error:
            send_event({"generation_error": str(error), "done": True})
        else:
            send_event({"done": True})
        finally:
            full_text = "".join(collected_answer).strip()
            if full_text and user and conversation_id:
                threading.Thread(
                    target=self.server.history.add_message,
                    args=(
                        user["user_id"],
                        conversation_id,
                        "bot",
                        full_text,
                        [asdict(p) for p in passages],
                        generator.model,
                    ),
                    daemon=True,
                ).start()


def main():
    parser = argparse.ArgumentParser(description="PTIT chatbot demo")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--keyword-only", action="store_true")
    args = parser.parse_args()

    index = KnowledgeBase(ROOT / "knowledge_base")
    mode = "keyword"
    vector_directory = ROOT / ".chroma"

    if not args.keyword_only:
        try:
            from vector_search import HybridSearch, VectorSearch
            vector = VectorSearch(vector_directory)
            if vector.collection.count() == 0:
                print("Vector index rỗng. Đang tự động lập chỉ mục...", flush=True)
                vector.rebuild_index(ROOT / "knowledge_base")
            index = HybridSearch(index, vector)
            mode = "hybrid"
        except Exception as error:
            print(f"Không thể khởi động tìm kiếm vector: {error}. Chạy chế độ từ khóa.", flush=True)

    try:
        generator = Gemini.from_config(ROOT / ".env")
    except ValueError as error:
        parser.error(str(error))

    with ThreadingHTTPServer(("127.0.0.1", args.port), Handler) as server:
        server.index = index
        server.uploads = UploadStore()
        server.generator = generator
        server.retrieval_mode = mode
        server.auth = AuthStore()
        server.history = HistoryStore()
        server.knowledge_manager = KnowledgeManager(server)

        print(f"PTIT chatbot | {index.document_count} tài liệu | {mode} | "
              f"http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
