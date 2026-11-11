"""Additional boundary/cookie/CORS tests, complementing test_api.py."""
import os
import shutil
from unittest.mock import patch
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from BE.tests.qa_support import DATA, OfflineCase, SAFE_SETTINGS, case

# Safe even when this file is run on its own, before BE.main has been imported.
with patch.dict(os.environ, SAFE_SETTINGS), patch("dotenv.load_dotenv", return_value=False):
    from BE.main import create_app


class ApiExtraTests(OfflineCase):
    def setUp(self):
        super().setUp()
        self.data = self.path / "data"
        self.data.mkdir()
        shutil.copyfile(DATA / "ktx.md", self.data / "ktx.md")
        self.app = create_app(db_path=self.path / "isolated-store", data_dir=self.data)
        self.client = self.enterContext(TestClient(self.app))
        self.identifier = self.client.post("/api/conversations").json()["id"]
        self.url = f"/api/conversations/{self.identifier}/messages"

    def send(self, message="Lệ phí nội trú KTX tháng 1/2026?", request_id=None, **extra):
        return self.client.post(self.url, json={"message": message, "request_id": request_id or str(uuid4()), **extra})

    @case("APIX-001", "Validation request_id và kiểu body còn thiếu trong test cũ", "UUID sai/None/số; thiếu field; message None/list/int; JSON lỗi", "422; không lưu; không gọi knowledge.answer")
    def test_request_uuid_missing_fields_types_and_malformed_json(self):
        bodies = [{"message": "hỏi", "request_id": value} for value in ("invalid", None, 123)]
        bodies += [{"message": "hỏi"}, {"request_id": str(uuid4())}, {}]
        bodies += [{"message": value, "request_id": str(uuid4())} for value in (None, [], 123)]
        with patch.object(self.app.state.knowledge, "answer") as answer:
            for body in bodies:
                with self.subTest(body=body):
                    self.assertEqual(self.client.post(self.url, json=body).status_code, 422)
            self.assertEqual(self.client.post(self.url, content="{", headers={"Content-Type": "application/json"}).status_code, 422)
            answer.assert_not_called()
        self.assertEqual(self.app.state.database.get(self.identifier, self.client.cookies["ptit_session"])["messages"], [])

    @case("APIX-002", "Biên hợp lệ 1 và 4000 ký tự và trim trước lưu", "'x', 4000 ký tự, '\t  nội dung  \n'", "200; model nhận và DB lưu câu hỏi đã strip")
    def test_valid_length_boundaries_and_trimming_before_storage(self):
        with patch.object(self.app.state.knowledge, "answer", return_value=("Đáp án fixture", "retrieval_only", [])) as answer:
            for message in ("x", "x" * 4000, "\t  nội dung  \n"):
                with self.subTest(length=len(message)):
                    response = self.send(message)
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(response.json()["messages"][-2]["text"], message.strip())
                    self.assertEqual(answer.call_args.args[0], message.strip())

    @case("APIX-003", "404 trên gửi/xóa UUID chưa tồn tại", "UUID hợp lệ nhưng không tồn tại", "404; không gọi knowledge; không tạo dữ liệu mới")
    def test_missing_conversation_post_and_delete_do_not_generate(self):
        missing = str(uuid4())
        with patch.object(self.app.state.knowledge, "answer") as answer:
            self.assertEqual(self.client.post(f"/api/conversations/{missing}/messages", json={"message": "hỏi", "request_id": str(uuid4())}).status_code, 404)
            self.assertEqual(self.client.delete(f"/api/conversations/{missing}").status_code, 404)
            answer.assert_not_called()

    @case("APIX-004", "Retry idempotent bỏ qua generator và giữ payload cũ", "Request thành công, retry UUID cũ với message khác và generator lỗi", "200, kết quả giống hệt lần đầu, không gọi lại generator")
    def test_retry_uses_saved_turn_even_if_generator_is_now_unavailable(self):
        request_id = str(uuid4())
        with patch.object(self.app.state.knowledge, "answer", return_value=("Đáp fixture", "retrieval_only", [])):
            first = self.send(request_id=request_id)
        self.assertEqual(first.status_code, 200)
        with patch.object(self.app.state.knowledge, "answer", side_effect=RuntimeError("must not run")) as answer:
            retry = self.send("Nội dung retry khác", request_id=request_id)
            answer.assert_not_called()
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(retry.json(), first.json())

    @case("APIX-005", "503 khi schema nguồn không hợp lệ sau khi đã có một lượt", "Lượt 1 thành công; lượt 2 generator trả nguồn thiếu field; retry sau sửa mock", "503 giữ nguyên lượt 1; retry cùng UUID chỉ thêm đúng một cặp")
    def test_invalid_generated_sources_preserve_prior_turn_and_allow_same_id_retry(self):
        with patch.object(self.app.state.knowledge, "answer", return_value=("Đáp fixture", "retrieval_only", [])):
            before = self.send().json()
        request = str(uuid4())
        with patch.object(self.app.state.knowledge, "answer", return_value=("Đáp fixture", "llm", [{"source_file": "ktx.md"}])):
            self.assertEqual(self.send(request_id=request).status_code, 503)
        self.assertEqual(self.client.get(f"/api/conversations/{self.identifier}").json(), before)
        with patch.object(self.app.state.knowledge, "answer", return_value=("Đáp fixture", "retrieval_only", [])):
            retried = self.send(request_id=request)
        self.assertEqual(retried.status_code, 200)
        self.assertEqual(len(retried.json()["messages"]), 4)

    @case("APIX-006", "Cookie sai định dạng được cấp lại và tách owner cũ", "ptit_session=not-a-uuid", "UUID mới; HttpOnly/SameSite=lax; không thấy hội thoại owner cũ")
    def test_malformed_cookie_is_rotated_without_access_to_previous_owner(self):
        owner = self.client.cookies["ptit_session"]
        cookie = next(c for c in self.client.cookies.jar if c.name == "ptit_session")
        self.client.cookies.clear()
        self.client.cookies.set("ptit_session", "not-a-uuid", domain=cookie.domain, path=cookie.path)
        response = self.client.get("/api/conversations")
        new_owner = self.client.cookies["ptit_session"]
        self.assertEqual(str(UUID(new_owner)), new_owner)
        self.assertNotEqual(owner, new_owner)
        self.assertEqual(response.json(), [])
        self.assertIn("HttpOnly", response.headers["set-cookie"])
        self.assertIn("SameSite=lax", response.headers["set-cookie"])
        self.assertEqual(self.client.get(f"/api/conversations/{self.identifier}").status_code, 404)

    @case("APIX-007", "Cookie UUID hợp lệ ở dạng viết hoa được chuẩn hóa", "ptit_session=UUID(owner).upper()", "Giữ cùng owner/dữ liệu; cấp cookie canonical")
    def test_uppercase_uuid_cookie_is_normalized_without_losing_owner(self):
        owner = self.client.cookies["ptit_session"]
        cookie = next(c for c in self.client.cookies.jar if c.name == "ptit_session")
        self.client.cookies.clear()
        self.client.cookies.set("ptit_session", owner.upper(), domain=cookie.domain, path=cookie.path)
        response = self.client.get("/api/conversations")
        self.assertEqual(response.json()[0]["id"], self.identifier)
        self.assertEqual(self.client.cookies["ptit_session"], owner)

    @case("APIX-008", "Health degraded và sources 503 khi Markdown lỗi", "Thay bản sao tạm ktx.md bằng Markdown không metadata", "health HTTP 200/status degraded/count 0; sources HTTP 503")
    def test_invalid_data_degrades_health_and_unavailable_sources(self):
        (self.data / "ktx.md").write_text("# Invalid fixture", encoding="utf-8")
        health = self.client.get("/api/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["status"], "degraded")
        self.assertEqual(health.json()["source_count"], 0)
        self.assertFalse(health.json()["llm_configured"])
        self.assertEqual(self.client.get("/api/knowledge/sources").status_code, 503)

    @case("APIX-009", "CORS preflight origin cho phép", "OPTIONS từ http://localhost:5173; POST + Content-Type", "200; allow-origin chính xác; allow-credentials=true")
    def test_cors_preflight_allowed_origin(self):
        response = self.client.options(self.url, headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "Content-Type"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["access-control-allow-origin"], "http://localhost:5173")
        self.assertEqual(response.headers["access-control-allow-credentials"], "true")
        self.assertIn("POST", response.headers["access-control-allow-methods"])

    @case("APIX-010", "CORS preflight origin không được phép", "OPTIONS từ https://untrusted.example", "400; không có access-control-allow-origin")
    def test_cors_preflight_disallowed_origin(self):
        response = self.client.options(self.url, headers={"Origin": "https://untrusted.example", "Access-Control-Request-Method": "POST"})
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("access-control-allow-origin", response.headers)

    @case("APIX-011", "CORS chặn method/header không cho phép", "Origin hợp lệ nhưng PATCH hoặc X-Unapproved", "Preflight 400")
    def test_cors_preflight_rejects_unapproved_method_and_header(self):
        for method, header in (("PATCH", "Content-Type"), ("POST", "X-Unapproved")):
            with self.subTest(method=method, header=header):
                response = self.client.options(self.url, headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": method, "Access-Control-Request-Headers": header})
                self.assertEqual(response.status_code, 400)

