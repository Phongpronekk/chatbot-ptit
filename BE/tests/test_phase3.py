import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from BE.main import create_app


class Phase3Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "chat.sqlite3"
        self.data_dir = Path(self.tmp.name) / "data"
        self.data_dir.mkdir()
        (self.data_dir / "ktx.md").write_text(
            "---\nsource_url: https://ptit.edu.vn/ktx\nfetched_date: '2026-01-01'\n"
            "topic_group: Ký túc xá\n---\n"
            "# Ký túc xá cơ sở Hà Đông\nKTX B1, B2, B5 có mức phí nội trú từ 250.000đ đến 900.000đ/tháng.\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_sse_stream_endpoint_saves_turn_and_emits_deltas(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "google", "GOOGLE_API_KEY": "", "RETRIEVAL_BACKEND": "lexical"}):
            app = create_app(db_path=self.db_path, data_dir=self.data_dir)
            with TestClient(app) as client:
                conv = client.post("/api/conversations").json()
                conv_id = conv["id"]
                req_id = str(uuid4())
                res = client.post(
                    f"/api/conversations/{conv_id}/messages/stream",
                    json={"message": "KTX B2 mức phí bao nhiêu?", "request_id": req_id},
                )
                self.assertEqual(res.status_code, 200)
                self.assertIn("text/event-stream", res.headers.get("content-type", ""))
                body = res.text
                self.assertIn("event: delta", body)
                self.assertIn("event: done", body)

                # Verify turn was persisted in SQLite
                fetched = client.get(f"/api/conversations/{conv_id}").json()
                self.assertEqual(len(fetched["messages"]), 2)
                self.assertEqual(fetched["messages"][0]["role"], "user")
                self.assertEqual(fetched["messages"][1]["role"], "assistant")

    def test_feedback_like_dislike_and_ownership(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "google", "GOOGLE_API_KEY": "", "RETRIEVAL_BACKEND": "lexical"}):
            app = create_app(db_path=self.db_path, data_dir=self.data_dir)
            with TestClient(app) as client:
                conv = client.post("/api/conversations").json()
                conv_id = conv["id"]
                msg_res = client.post(
                    f"/api/conversations/{conv_id}/messages",
                    json={"message": "KTX B2 mức phí bao nhiêu?", "request_id": str(uuid4())},
                ).json()
                assistant_msg_id = msg_res["messages"][1]["id"]

                # Like (+1)
                fb_res = client.put(
                    f"/api/messages/{assistant_msg_id}/feedback",
                    json={"rating": 1, "comment": "Rất hữu ích"},
                )
                self.assertEqual(fb_res.status_code, 204)

                updated = client.get(f"/api/conversations/{conv_id}").json()
                self.assertEqual(updated["messages"][1]["feedback"], 1)

                # Update to Dislike (-1)
                fb_res2 = client.put(
                    f"/api/messages/{assistant_msg_id}/feedback",
                    json={"rating": -1},
                )
                self.assertEqual(fb_res2.status_code, 204)
                updated2 = client.get(f"/api/conversations/{conv_id}").json()
                self.assertEqual(updated2["messages"][1]["feedback"], -1)

                # Different session owner cannot rate another user's message
                with TestClient(app) as other_client:
                    other_res = other_client.put(
                        f"/api/messages/{assistant_msg_id}/feedback",
                        json={"rating": 1},
                    )
                    self.assertEqual(other_res.status_code, 404)

    def test_admin_reindex_hot_reload(self):
        with patch.dict(
            os.environ,
            {"LLM_PROVIDER": "google", "GOOGLE_API_KEY": "", "RETRIEVAL_BACKEND": "lexical", "ADMIN_TOKEN": "secret-admin-123"},
        ):
            app = create_app(db_path=self.db_path, data_dir=self.data_dir)
            with TestClient(app) as client:
                # Missing or wrong token -> 403
                self.assertEqual(client.post("/api/admin/reindex").status_code, 403)
                self.assertEqual(
                    client.post("/api/admin/reindex", headers={"X-Admin-Token": "wrong"}).status_code,
                    403,
                )

                # Add a new markdown file while app is running
                (self.data_dir / "clb.md").write_text(
                    "---\nsource_url: https://ptit.edu.vn/clb\nfetched_date: '2026-01-02'\n"
                    "topic_group: Câu lạc bộ\n---\n"
                    "# CLB Lập trình PTIT\nITPTIT là câu lạc bộ học thuật lập trình.\n",
                    encoding="utf-8",
                )

                ok_res = client.post("/api/admin/reindex", headers={"X-Admin-Token": "secret-admin-123"})
                self.assertEqual(ok_res.status_code, 200)
                self.assertEqual(ok_res.json()["source_count"], 2)


if __name__ == "__main__":
    unittest.main()

