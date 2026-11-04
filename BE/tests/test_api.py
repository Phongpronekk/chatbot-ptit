import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import httpx

from fastapi.testclient import TestClient

from BE.knowledge import Knowledge
from BE.main import ROOT, create_app, normalize_conversation_modes


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=ROOT / "BE")
        self.path = Path(self.directory.name) / "chat.sqlite3"
        self.data = Path(self.directory.name) / 'data'
        self.data.mkdir()
        (self.data / 'ktx.md').write_text(
            '---\nsource_url: https://ptit.edu.vn/test-ktx\nfetched_date: 2026-01-01\n'
            'topic_group: Ký túc xá\n---\n# KTX B2\nMức thu KTX B2: 250.000 đồng/sinh viên/tháng.\n', encoding='utf-8')
        (self.data / 'thuc_tap_viec_lam.md').write_text(
            '---\nsource_url: https://giaovu.ptit.edu.vn/test-internship\nfetched_date: 2026-01-01\n'
            'topic_group: Thực tập / Việc làm\nnote: >\n  Áp dụng khóa 2022-2027.\n'
            '  Kiểm tra kế hoạch từng năm.\n---\n# Thực tập\nLiên hệ khoa phụ trách.\n', encoding='utf-8')
        self.env = patch.dict(os.environ, {"ANTHROPIC_API_KEY": "", "GOOGLE_API_KEY": "", "LLM_PROVIDER": "anthropic", "RETRIEVAL_BACKEND": "lexical"})
        self.env.start()
        self.app = create_app(db_path=self.path, data_dir=self.data)
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
        expected_count = len(list(self.data.glob('*.md')))
        self.assertEqual(health["source_count"], expected_count)
        self.assertFalse(health["llm_configured"])
        self.assertEqual(len(self.client.get("/api/knowledge/sources").json()), expected_count)

    def test_rag_status_exposes_configuration_without_credentials(self):
        response = self.client.get('/api/rag/status')
        self.assertEqual(response.status_code, 200)
        info = response.json()
        self.assertEqual(info['retrieval_mode'], 'lexical')
        self.assertEqual(sum(info['topic_groups'].values()), info['document_count'])
        self.assertNotIn('GOOGLE_API_KEY', response.text)
        self.assertNotIn('ANTHROPIC_API_KEY', response.text)

    def test_rag_search_does_not_generate_or_save_messages(self):
        with patch.object(self.app.state.knowledge, 'answer') as generate:
            response = self.client.post('/api/rag/search', json={'question': 'KTX B2 mức thu bao nhiêu?', 'limit': 2})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertFalse(response.json()['llm_called'])
            self.assertTrue(response.json()['sources'])
            self.assertLessEqual(len(response.json()['sources']), 2)
            generate.assert_not_called()
        self.assertEqual(self.client.get('/api/conversations').json(), [])
        for invalid in ({'question': '  '}, {'question': 'test', 'limit': 11}):
            self.assertEqual(self.client.post('/api/rag/search', json=invalid).status_code, 422)

    def test_direct_ollama_test_mode_remains_available(self):
        with patch.dict(os.environ, {'DIRECT_OLLAMA_CHAT': 'true', 'LLM_PROVIDER': 'ollama'}), \
                patch.object(Knowledge, 'prepare') as prepare, \
                patch('BE.main.ask_ollama_direct', return_value='Xin chào từ model local'), \
                TestClient(create_app(db_path=self.path)) as client:
            self.assertEqual(client.get('/api/health').json()['retrieval'], 'disabled')
            self.assertEqual(client.get('/api/rag/status').json()['retrieval_mode'], 'disabled')
            self.assertEqual(client.post('/api/rag/search', json={'question': 'test'}).status_code, 503)
            cid = client.post('/api/conversations').json()['id']
            response = client.post(f'/api/conversations/{cid}/messages', json={'message': 'Xin chào', 'request_id': str(uuid4())})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['messages'][-1]['mode'], 'llm')
            prepare.assert_not_called()

    def test_legacy_general_mode_is_normalized_without_mutation(self):
        original = {'id': 'example', 'messages': [{'mode': 'general', 'text': 'old answer'}]}
        normalized = normalize_conversation_modes(original)
        self.assertEqual(normalized['messages'][0]['mode'], 'llm')
        self.assertEqual(original['messages'][0]['mode'], 'general')

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
        with TestClient(create_app(db_path=self.path, data_dir=self.data)) as restarted:
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
        sources = Knowledge(self.data).sources()
        internship = next(source for source in sources if source["source_file"] == "thuc_tap_viec_lam.md")
        self.assertIn("2022-2027", internship["note"])

    def test_ollama_answer_is_saved_without_api_keys(self):
        identifier = self.create()
        response = httpx.Response(200, json={"message": {"content": "Mức thu 250.000 đồng [1]."}},
                                  request=httpx.Request("POST", "http://127.0.0.1:11434/api/chat"))
        with patch.dict(os.environ, {"LLM_PROVIDER": "ollama", "MODEL_NAME": "qwen2.5-coder:3b"}), \
                patch("BE.knowledge.httpx.Client") as client:
            client.return_value.__enter__.return_value.post.return_value = response
            result = self.send(identifier)
            self.assertEqual(result.status_code, 200, result.text)
            answer = result.json()["messages"][1]
            self.assertEqual(answer["mode"], "llm")
            self.assertIn("250.000", answer["text"])
            self.assertTrue(answer["sources"])
            call = client.return_value.__enter__.return_value.post.call_args
            self.assertTrue(call.args[0].endswith("/api/chat"))
            self.assertFalse(call.kwargs["json"]["stream"])
            self.assertEqual(call.kwargs["json"]["options"]["num_ctx"], 4096)
            self.assertTrue(self.client.get("/api/health").json()["llm_configured"])

    def test_ollama_failure_does_not_save_turn(self):
        identifier = self.create()
        with patch.dict(os.environ, {"LLM_PROVIDER": "ollama", "MODEL_NAME": "qwen2.5-coder:3b"}), \
                patch("BE.knowledge.httpx.Client") as client:
            client.return_value.__enter__.return_value.post.side_effect = httpx.ConnectError("offline")
            self.assertEqual(self.send(identifier).status_code, 503)
        self.assertEqual(self.client.get(f"/api/conversations/{identifier}").json()["messages"], [])

    def test_cloud_model_is_rejected_in_local_provider(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "ollama", "MODEL_NAME": "gpt-oss:20b-cloud"}), \
                patch("BE.knowledge.httpx.Client") as client:
            self.assertFalse(self.client.get("/api/health").json()["llm_configured"])
            self.assertEqual(self.send(self.create()).status_code, 503)
            client.assert_not_called()


if __name__ == "__main__":
    unittest.main()
