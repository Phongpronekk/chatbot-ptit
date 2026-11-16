"""Serve the PTIT chatbot demo and its local retrieval API."""

import argparse
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import urlsplit

from gemini import Gemini, GenerationError
from retrieval import KnowledgeBase

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
}
MAX_BODY = 16_384


class Handler(BaseHTTPRequestHandler):
    def send_bytes(self, status, data, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
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
                "model": generator.model if generator else None,
            })
            return
        if path in STATIC:
            file, media_type = STATIC[path]
            self.send_bytes(HTTPStatus.OK, (FRONTEND / file).read_bytes(), media_type)
            return
        self.send_json(HTTPStatus.NOT_FOUND, {"error": "Không tìm thấy địa chỉ."})

    def do_POST(self):
        if urlsplit(self.path).path != "/api/chat":
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "Không tìm thấy địa chỉ."})
            return
        if self.headers.get_content_type() != "application/json":
            self.send_json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": "Cần gửi dữ liệu JSON."})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= MAX_BODY:
                raise ValueError
            payload = json.loads(self.rfile.read(size))
            question = payload.get("question", "") if isinstance(payload, dict) else ""
            if not isinstance(question, str) or not 0 < len(question.strip()) <= 500:
                raise ValueError
        except (ValueError, UnicodeError):
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Nhập câu hỏi từ 1 đến 500 ký tự."})
            return
        question = question.strip()
        passages = self.server.index.search(question)
        result = {"passages": [asdict(passage) for passage in passages]}
        generator = self.server.generator
        if generator and passages:
            try:
                result["answer"] = generator.answer(question, passages)
                result["model"] = generator.model
            except GenerationError as error:
                result["generation_error"] = str(error)
        self.send_json(HTTPStatus.OK, result)


def main():
    parser = argparse.ArgumentParser(description="PTIT chatbot demo")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    index = KnowledgeBase(ROOT / "knowledge_base")
    try:
        generator = Gemini.from_config(ROOT / ".env")
    except ValueError as error:
        parser.error(str(error))
    with ThreadingHTTPServer(("127.0.0.1", args.port), Handler) as server:
        server.index = index
        server.generator = generator
        print(f"PTIT chatbot | {index.document_count} tai lieu | http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
