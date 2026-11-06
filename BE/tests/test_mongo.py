import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from BE.main import create_app
from BE.mongo_store import (
    is_mongo_configured,
    get_mongo_uri,
    get_mongo_db_name,
    get_mongo_collection_name,
    parse_source_file,
    check_mongo_connection,
    sync_source_documents,
    get_source_documents,
)

ROOT = Path(__file__).resolve().parents[2]


class MongoStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.tmp.name) / "data"
        self.data_dir.mkdir()
        (self.data_dir / "test.md").write_text(
            "---\nsource_url: https://ptit.edu.vn/test\nfetched_date: '2026-01-01'\n"
            "topic_group: Test Topic\n---\n"
            "<!-- source_metadata: {\"title\": \"Test Article\", \"publish_date\": \"2026-01-01\", \"source_url\": \"https://ptit.edu.vn/test\"} -->\n"
            "# Test Article\nNội dung bài viết thử nghiệm.\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_unconfigured_by_default(self):
        with patch.dict(os.environ, {"MONGODB_URI": ""}):
            self.assertFalse(is_mongo_configured())
            status = check_mongo_connection()
            self.assertFalse(status["configured"])
            self.assertFalse(status["connected"])
            result = sync_source_documents(self.data_dir)
            self.assertFalse(result["success"])
            self.assertEqual(get_source_documents(), [])

    def test_parse_source_file(self):
        doc = parse_source_file(self.data_dir / "test.md")
        self.assertEqual(doc["_id"], "test.md")
        self.assertEqual(doc["filename"], "test.md")
        self.assertEqual(doc["topic_group"], "Test Topic")
        self.assertEqual(doc["article_count"], 1)
        self.assertEqual(doc["articles"][0]["title"], "Test Article")
        self.assertTrue(doc["sha256"])
        self.assertIn("Nội dung bài viết", doc["raw_content"])

    @patch("BE.mongo_store.get_mongo_client")
    def test_mock_sync_and_connection(self, mock_client_factory):
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_col = MagicMock()
        mock_client.__getitem__.return_value = mock_db
        mock_db.__getitem__.return_value = mock_col
        mock_col.count_documents.return_value = 1
        mock_col.find.return_value.sort.return_value = [{"_id": "test.md", "topic_group": "Test Topic"}]
        mock_client_factory.return_value = mock_client

        with patch.dict(os.environ, {"MONGODB_URI": "mongodb://localhost:27017"}):
            self.assertTrue(is_mongo_configured())
            status = check_mongo_connection()
            self.assertTrue(status["configured"])
            self.assertTrue(status["connected"])
            self.assertEqual(status["source_document_count"], 1)

            result = sync_source_documents(self.data_dir)
            self.assertTrue(result["success"])
            self.assertEqual(result["synced_count"], 1)
            mock_col.replace_one.assert_called_once()

            docs = get_source_documents()
            self.assertEqual(len(docs), 1)

    def test_api_mongo_endpoints(self):
        db_path = Path(self.tmp.name) / "chat.sqlite3"
        with patch.dict(os.environ, {"MONGODB_URI": "", "RETRIEVAL_BACKEND": "lexical"}):
            app = create_app(db_path=db_path, data_dir=self.data_dir)
            with TestClient(app) as client:
                status_res = client.get("/api/mongodb/status")
                self.assertEqual(status_res.status_code, 200)
                self.assertFalse(status_res.json()["configured"])

                sync_res = client.post("/api/mongodb/sync")
                self.assertEqual(sync_res.status_code, 400)

                health_res = client.get("/api/health")
                self.assertFalse(health_res.json()["mongodb_configured"])

    @patch("BE.mongo_store.get_mongo_client")
    def test_temp_attachments_mongo_persist_and_hydrate(self, mock_client_factory):
        from BE.attachments import DocumentMemory

        stored_docs = {}
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_col = MagicMock()
        mock_client.__getitem__.return_value = mock_db
        mock_db.__getitem__.return_value = mock_col

        def fake_replace_one(flt, doc, upsert=False):
            stored_docs[flt["_id"]] = dict(doc)

        def fake_find(flt):
            result = []
            for doc in stored_docs.values():
                if doc.get("owner") == flt.get("owner") and doc.get("conversation_id") == flt.get("conversation_id"):
                    result.append(dict(doc))
            mock_cursor = MagicMock()
            mock_cursor.sort.return_value = result
            return mock_cursor

        def fake_delete_many(flt):
            to_delete = [
                k for k, v in stored_docs.items()
                if v.get("owner") == flt.get("owner")
                and v.get("conversation_id") == flt.get("conversation_id")
                and ("_id" not in flt or k == flt["_id"])
            ]
            for k in to_delete:
                stored_docs.pop(k, None)
            res = MagicMock()
            res.deleted_count = len(to_delete)
            return res

        mock_col.replace_one.side_effect = fake_replace_one
        mock_col.find.side_effect = fake_find
        mock_col.delete_many.side_effect = fake_delete_many
        mock_client_factory.return_value = mock_client

        with patch.dict(os.environ, {"MONGODB_URI": "mongodb://localhost:27017"}):
            mem1 = DocumentMemory(use_mongo=True)
            chunks = [{"location": "Trang 1", "content": "Nội dung học bổng PTIT 2026"}]
            meta = mem1.add("owner-1", "conv-1", "hoc_bong.pdf", 1024, chunks)
            self.assertIn(meta["id"], stored_docs)
            mock_col.create_index.assert_called()

            # Simulate server restart / second worker with empty RAM cache
            mem2 = DocumentMemory(use_mongo=True)
            listed = mem2.list("owner-1", "conv-1")
            self.assertEqual(len(listed), 1)
            self.assertEqual(listed[0]["id"], meta["id"])
            self.assertEqual(listed[0]["filename"], "hoc_bong.pdf")

            retrieved = mem2.retrieve("owner-1", "conv-1", [meta["id"]], "học bổng PTIT")
            self.assertTrue(len(retrieved) >= 1)

            # Delete from mem2 should also remove from MongoDB
            self.assertTrue(mem2.delete("owner-1", "conv-1", meta["id"]))
            self.assertNotIn(meta["id"], stored_docs)

    @patch("BE.database.get_mongo_client")
    def test_database_mongo_conversations_messages_and_feedback(self, mock_client_factory):
        from BE.database import Database

        collections = {
            "conversations": {},
            "messages": {},
            "feedback": {},
        }
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_client.__getitem__.return_value = mock_db

        def get_col(name):
            col = MagicMock()

            def replace_one(flt, doc, upsert=False):
                collections[name][flt["_id"]] = dict(doc)

            def insert_one(doc):
                collections[name][doc["_id"]] = dict(doc)

            def find_one(flt, projection=None, sort=None):
                matches = []
                for doc in collections[name].values():
                    if all(doc.get(k) == v for k, v in flt.items()):
                        matches.append(dict(doc))
                if not matches:
                    return None
                if sort:
                    field, direction = sort[0]
                    matches.sort(key=lambda x: x.get(field, 0), reverse=(direction == -1))
                return matches[0]

            def find(flt=None, projection=None):
                flt = flt or {}
                matches = []
                for doc in collections[name].values():
                    ok = True
                    for k, v in flt.items():
                        if isinstance(v, dict) and "$in" in v:
                            if doc.get(k) not in v["$in"]:
                                ok = False
                        elif doc.get(k) != v:
                            ok = False
                    if ok:
                        item = dict(doc)
                        if projection and projection.get("_id") == 0:
                            item.pop("_id", None)
                        matches.append(item)
                cursor = MagicMock()
                cursor.sort.return_value = cursor
                cursor.limit.return_value = matches
                cursor.__iter__.return_value = iter(matches)
                return cursor

            def update_one(flt, upd):
                if flt["_id"] in collections[name]:
                    collections[name][flt["_id"]].update(upd.get("$set", {}))

            def delete_one(flt):
                res = MagicMock()
                if flt["_id"] in collections[name] and collections[name][flt["_id"]].get("owner") == flt.get("owner"):
                    del collections[name][flt["_id"]]
                    res.deleted_count = 1
                else:
                    res.deleted_count = 0
                return res

            col.replace_one.side_effect = replace_one
            col.insert_one.side_effect = insert_one
            col.find_one.side_effect = find_one
            col.find.side_effect = find
            col.update_one.side_effect = update_one
            col.delete_one.side_effect = delete_one
            return col

        mock_db.__getitem__.side_effect = get_col
        mock_client_factory.return_value = mock_client

        with patch.dict(os.environ, {"MONGODB_URI": "mongodb://localhost:27017"}):
            db = Database(use_mongo=True)
            db.initialize()
            created = db.create("owner-1")
            conv_id = created["id"]
            self.assertIn(conv_id, collections["conversations"])

            updated = db.save_turn(conv_id, "owner-1", "req-1", "KTX ở đâu?", "Ở Hà Đông", "llm", [])
            self.assertEqual(len(updated["messages"]), 2)
            assistant_id = updated["messages"][1]["id"]

            self.assertTrue(db.save_feedback(assistant_id, "owner-1", 1, "Chuẩn xác"))
            self.assertIn(assistant_id, collections["feedback"])
            self.assertEqual(collections["feedback"][assistant_id]["question"], "KTX ở đâu?")
            self.assertEqual(collections["feedback"][assistant_id]["answer"], "Ở Hà Đông")
            self.assertEqual(collections["feedback"][assistant_id]["rating"], 1)

            fb_list = db.list_feedback(rating=1)
            self.assertEqual(len(fb_list), 1)
            self.assertEqual(fb_list[0]["message_id"], assistant_id)


if __name__ == "__main__":
    unittest.main()

