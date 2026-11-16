"""Serve the PTIT chatbot demo and its local retrieval API."""

import argparse
from contextlib import closing, suppress
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit

from conversation import MAX_QUESTION_CHARS, is_follow_up, read_history, resolve_person_reference
from gemini import Gemini, GenerationError, IncompleteGenerationError
from retrieval import KnowledgeBase
from uploads import MAX_UPLOAD_BYTES, UploadError, UploadStore, index_upload

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
}
MAX_BODY = 32_768


class Handler(BaseHTTPRequestHandler):
    def send_bytes(self, status, data, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        if content_type.startswith("application/json"):
            self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_bytes(status, body, "application/json; charset=utf-8")

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/api/status":
            generator = self.server.generator
            self.send_json(HTTPStatus.OK, {
                "documents": self.server.index.document_count,
                "retrieval": getattr(self.server, "retrieval_mode", "keyword"),
                "model": generator.model if generator else None,
            })
            return
        if path in STATIC:
            file, media_type = STATIC[path]
            self.send_bytes(HTTPStatus.OK, (FRONTEND / file).read_bytes(), media_type)
            return
        self.send_json(HTTPStatus.NOT_FOUND, {"error": "Không tìm thấy địa chỉ."})

    def do_POST(self):
        path = urlsplit(self.path).path
        if path == "/api/uploads":
            self.upload_document()
        elif path == "/api/chat":
            self.chat()
        else:
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "Không tìm thấy địa chỉ."})

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
            if not 0 < size <= MAX_BODY:
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
        result = {"passages": [asdict(passage) for passage in passages]}
        if question != original_question:
            result["resolved_question"] = question
        if context_person is not None:
            result["context_person"] = context_person
        if document is not None:
            result["document"] = document.name
        if generator and passages and self.headers.get("Accept") == "application/x-ndjson":
            with suppress(ConnectionError):
                self.stream_answer(question, passages, result, generator)
            return
        if generator and passages:
            try:
                result["answer"] = generator.answer(question, passages)
                result["model"] = generator.model
            except GenerationError as error:
                result["generation_error"] = str(error)
        self.send_json(HTTPStatus.OK, result)

    def stream_answer(self, question, passages, result, generator):
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

        try:
            send_event({**result, "model": generator.model})
            with closing(generator.stream_answer(question, passages)) as stream:
                for delta in stream:
                    send_event({"delta": delta})
        except IncompleteGenerationError:
            try:
                answer = generator.answer(question, passages, require_complete=True)
            except GenerationError as error:
                send_event({"generation_error": str(error), "done": True})
            else:
                send_event({"answer": answer, "done": True})
        except GenerationError as error:
            send_event({"generation_error": str(error), "done": True})
        else:
            send_event({"done": True})


def main():
    parser = argparse.ArgumentParser(description="PTIT chatbot demo")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--keyword-only", action="store_true")
    args = parser.parse_args()
    index = KnowledgeBase(ROOT / "knowledge_base")
    mode = "keyword"
    vector_directory = ROOT / ".chroma"
    if not args.keyword_only and (vector_directory / "chroma.sqlite3").is_file():
        try:
            from vector_search import HybridSearch, VectorSearch
            vector = VectorSearch(vector_directory)
        except (ImportError, OSError, ValueError) as error:
            parser.error(f"Cannot open vector index: {error}. Try --keyword-only.")
        index = HybridSearch(index, vector)
        mode = "hybrid"
    try:
        generator = Gemini.from_config(ROOT / ".env")
    except ValueError as error:
        parser.error(str(error))
    with ThreadingHTTPServer(("127.0.0.1", args.port), Handler) as server:
        server.index = index
        server.uploads = UploadStore()
        server.generator = generator
        server.retrieval_mode = mode
        print(f"PTIT chatbot | {index.document_count} tai lieu | {mode} | "
              f"http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
