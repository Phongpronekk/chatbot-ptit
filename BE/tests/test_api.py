import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from BE.knowledge import Knowledge
from BE.main import ROOT, create_app


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=ROOT / "BE")
        self.path = Path(self.directory.name) / "chat.sqlite3"
        self.env = patch.dict(os.environ, {"ANTHROPIC_API_KEY": "", "GOOGLE_API_KEY": "", "LLM_PROVIDER": "anthropic"})
        self.env.start()
        self.app = create_app(db_path=self.path)
        self.client = TestClient(self.app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.env.stop()
        self.directory.cleanup()

    def create(self):
        response = self.client.post("/api/conversations")
        self.assertEqual(response.status_code, 201)
        return response.json()["id"]

    def send(self, identifier, message="KTX B2 mức thu bao nhiêu?", request_id=None):
        return self.client.post(f"/api/conversations/{identifier}/messages", json={
            "message": message, "request_id": request_id or str(uuid4()),
        })

    def test_empty_database_and_source_health(self):
        self.assertEqual(self.client.get("/api/conversations").json(), [])
        health = self.client.get("/api/health").json()
        self.assertEqual(health["source_count"], 5)
        self.assertFalse(health["llm_configured"])
        self.assertEqual(len(self.client.get("/api/knowledge/sources").json()), 5)

    def test_create_send_reload_and_delete(self):
        identifier = self.create()
        self.assertEqual(self.client.get(f"/api/conversations/{identifier}").json()["messages"], [])
        response = self.send(identifier)
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(len(data["messages"]), 2)
        self.assertEqual(data["messages"][1]["mode"], "retrieval_only")
        refs = data["messages"][1]["sources"]
        self.assertTrue(any("250.000" in item["content"] for item in refs), refs)
        self.assertTrue(all(item["source_url"].startswith("https://") for item in refs))
        self.assertEqual(self.client.get(f"/api/conversations/{identifier}").json(), data)
        self.assertEqual(self.client.get("/api/conversations").json()[0]["title"], "KTX B2 mức thu bao nhiêu?")
        self.assertEqual(self.client.delete(f"/api/conversations/{identifier}").status_code, 204)
        self.assertEqual(self.client.get(f"/api/conversations/{identifier}").status_code, 404)

    def test_persists_across_application_restart(self):
        identifier = self.create()
        self.assertEqual(self.send(identifier).status_code, 200)
        with TestClient(create_app(db_path=self.path)) as restarted:
            restarted.cookies.update(self.client.cookies)
            response = restarted.get(f"/api/conversations/{identifier}")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.json()["messages"]), 2)

    def test_other_browser_cannot_read_write_delete(self):
        identifier = self.create()
        with TestClient(self.app) as other:
            self.assertEqual(other.get("/api/conversations").json(), [])
            self.assertEqual(other.get(f"/api/conversations/{identifier}").status_code, 404)
            self.assertEqual(other.post(f"/api/conversations/{identifier}/messages", json={"message": "hello", "request_id": str(uuid4())}).status_code, 404)
            self.assertEqual(other.delete(f"/api/conversations/{identifier}").status_code, 404)

    def test_invalid_messages_and_ids(self):
        identifier = self.create()
        for text in ("", "   ", "a" * 4001):
            self.assertEqual(self.send(identifier, text).status_code, 422)
        self.assertEqual(self.client.get("/api/conversations/invalid").status_code, 422)
        self.assertEqual(self.client.get(f"/api/conversations/{uuid4()}").status_code, 404)

    def test_retry_does_not_duplicate_messages(self):
        identifier, request_id = self.create(), str(uuid4())
        self.assertEqual(self.send(identifier, request_id=request_id).status_code, 200)
        self.assertEqual(len(self.send(identifier, request_id=request_id).json()["messages"]), 2)

    def test_no_match_is_not_fabricated(self):
        response = self.send(self.create(), "quasar supernova astrophysics")
        self.assertEqual(response.status_code, 200)
        answer = response.json()["messages"][1]
        self.assertEqual(answer["sources"], [])
        self.assertIn("chưa tìm thấy", answer["text"])

    def test_service_failure_does_not_save_partial_turn(self):
        identifier = self.create()
        with patch.object(self.app.state.knowledge, "answer", side_effect=RuntimeError("test outage")):
            self.assertEqual(self.send(identifier).status_code, 503)
        self.assertEqual(self.client.get(f"/api/conversations/{identifier}").json()["messages"], [])

    def test_cookie_is_httponly(self):
        response = self.client.get("/api/conversations")
        self.assertIn("HttpOnly", response.headers["set-cookie"])
        self.assertIn("SameSite=lax", response.headers["set-cookie"])

    def test_metadata_retains_multiline_notes(self):
        sources = Knowledge(ROOT / "data").sources()
        internship = next(source for source in sources if source["source_file"] == "thuc_tap_viec_lam.md")
        self.assertIn("2022-2027", internship["note"])


if __name__ == "__main__":
    unittest.main()
