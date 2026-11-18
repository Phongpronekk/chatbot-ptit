"""Serve the PTIT chatbot demo, user authentication, chat history, and admin document management."""

import argparse
from contextlib import closing, suppress
from dataclasses import asdict
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit

from conversation import MAX_QUESTION_CHARS, is_follow_up, read_history, resolve_person_reference
from database import AuthStore, HistoryStore
from gemini import Gemini, GenerationError, IncompleteGenerationError
from knowledge_manager import KnowledgeManager
from retrieval import KnowledgeBase
from uploads import MAX_UPLOAD_BYTES, UploadError, UploadStore, index_upload

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/admin": ("admin.html", "text/html; charset=utf-8"),
    "/admin.html": ("admin.html", "text/html; charset=utf-8"),
    "/admin.css": ("admin.css", "text/css; charset=utf-8"),
    "/admin.js": ("admin.js", "text/javascript; charset=utf-8"),
}
MAX_BODY = 10 * 1024 * 1024  # 10 MB for admin uploads


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
            user = self.require_auth()
            if not user:
                return
            convs = self.server.history.get_conversations(user["user_id"])
            self.send_json(HTTPStatus.OK, {"conversations": convs})
            return

        if path.startswith("/api/conversations/"):
            user = self.require_auth()
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
            file, media_type = STATIC[path]
            self.send_bytes(HTTPStatus.OK, (FRONTEND / file).read_bytes(), media_type)
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
        if path.startswith("/api/conversations/"):
            user = self.require_auth()
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
        if path.startswith("/api/conversations/"):
            user = self.require_auth()
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
            role = data.get("role", "user")
            user = self.server.auth.register_user(username, password, role=role)
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
            token = self.server.auth.create_session(user["id"], user["username"], user["role"])
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
        user = self.require_auth()
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
        if self.headers.get_content_type() != "application/json":
            self.send_json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": "Cần gửi dữ liệu JSON."})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 65536:
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
        user = self.get_current_user()

        upload_id = payload.get("upload_id")
        if upload_id is not None and (not isinstance(upload_id, str) or len(upload_id) != 32):
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Mã tệp không hợp lệ."})
            return
        document = self.server.uploads.get(upload_id) if upload_id is not None else None
        if upload_id is not None and document is None:
            self.send_json(HTTPStatus.NOT_FOUND, {
                "error": "Tệp không còn sẵn sàng. Hãy tải lại tệp hoặc chọn không dùng tệp.",
                "code": "upload_unavailable",
            })
            return
        question = question.strip()
        original_question = question
        generator = self.server.generator
        passages = []
        context_person = None
        if document and (person := resolve_person_reference(question, history)):
            resolved, name = person
            passages = document.search(resolved, required_phrase=name)
            if passages:
                question = resolved
                context_person = name
        if not passages:
            if generator and history and is_follow_up(question):
                with suppress(GenerationError):
                    question = generator.rewrite_question(question, history)
            index = document if document is not None else self.server.index
            passages = index.search(question)

        # Save user question to DB if user & conversation_id
        if user and conversation_id:
            self.server.history.add_message(
                user["user_id"],
                conversation_id,
                "user",
                original_question,
            )

        result = {"passages": [asdict(passage) for passage in passages]}
        if question != original_question:
            result["resolved_question"] = question
        if context_person is not None:
            result["context_person"] = context_person
        if document is not None:
            result["document"] = document.name

        if generator and passages and self.headers.get("Accept") == "application/x-ndjson":
            with suppress(ConnectionError):
                self.stream_answer(question, passages, result, generator, user=user, conversation_id=conversation_id)
            return

        if generator and passages:
            try:
                answer = generator.answer(question, passages)
                result["answer"] = answer
                result["model"] = generator.model
                if user and conversation_id:
                    self.server.history.add_message(
                        user["user_id"],
                        conversation_id,
                        "bot",
                        answer,
                        passages=[asdict(p) for p in passages],
                        model=generator.model,
                    )
            except GenerationError as error:
                result["generation_error"] = str(error)
        elif not passages and generator:
            # Fallback when no passages found
            answer = "Không tìm thấy thông tin phù hợp trong kho tài liệu hiện tại."
            result["answer"] = answer
            if user and conversation_id:
                self.server.history.add_message(
                    user["user_id"],
                    conversation_id,
                    "bot",
                    answer,
                    passages=[],
                )

        self.send_json(HTTPStatus.OK, result)

    def stream_answer(self, question, passages, result, generator, user=None, conversation_id=None):
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Connection", "close")
        self.close_connection = True
        self.end_headers()

        def send_event(event):
            self.wfile.write((json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8"))
            self.wfile.flush()

        collected_answer = []

        try:
            send_event({**result, "model": generator.model})
            with closing(generator.stream_answer(question, passages)) as stream:
                for delta in stream:
                    collected_answer.append(delta)
                    send_event({"delta": delta})
        except IncompleteGenerationError:
            try:
                answer = generator.answer(question, passages, require_complete=True)
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
                self.server.history.add_message(
                    user["user_id"],
                    conversation_id,
                    "bot",
                    full_text,
                    passages=[asdict(p) for p in passages],
                    model=generator.model,
                )


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
