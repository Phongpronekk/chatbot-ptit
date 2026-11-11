"""Storage contracts against the current RAM/Mongo implementation, never a real DB."""
from copy import deepcopy
from unittest.mock import Mock, patch
from uuid import uuid4

from BE import database as storage
from BE.database import Database
from BE.tests.qa_support import OfflineCase, case


class DatabaseExtraTests(OfflineCase):
    def setUp(self):
        super().setUp()
        self.db = Database(self.path / "isolated-store", use_mongo=False)
        self.db.initialize()
        self.addCleanup(storage._MEMORY_STORES.pop, self.db._store_key, None)
        self.owner = str(uuid4())
        with patch("BE.database.now", return_value="2026-11-11T00:00:00+00:00"):
            self.conv = self.db.create(self.owner)["id"]

    def save(self, request_id=None, question="Câu hỏi kiểm thử", sources=None):
        return self.db.save_turn(self.conv, self.owner, request_id or str(uuid4()), question,
                                 "Nội dung trả lời kiểm thử", "retrieval_only", sources or [])

    @case("DB-001", "CRUD trực tiếp và xóa lần hai", "Owner UUID; tạo/lấy/liệt kê/xóa", "Có hội thoại rỗng; xóa lần một True, lần hai False")
    def test_direct_crud_and_missing_conversation(self):
        self.assertEqual([c["id"] for c in self.db.list(self.owner)], [self.conv])
        self.assertEqual(self.db.get(self.conv, self.owner)["messages"], [])
        self.assertTrue(self.db.delete(self.conv, self.owner))
        self.assertFalse(self.db.delete(self.conv, self.owner))
        self.assertIsNone(self.db.get(self.conv, self.owner))
        self.assertEqual(self.db.list(self.owner), [])

    @case("DB-002", "Cách ly owner ngay tại lớp lưu trữ", "Owner khác gọi get/save_turn/delete", "Không đọc, sửa, xóa được; bản gốc nguyên vẹn")
    def test_storage_owner_checks_reject_mutation(self):
        other = str(uuid4())
        before = self.db.get(self.conv, self.owner)
        self.assertIsNone(self.db.get(self.conv, other))
        self.assertEqual(self.db.list(other), [])
        self.assertIsNone(self.db.save_turn(self.conv, other, str(uuid4()), "x", "y", "llm", []))
        self.assertFalse(self.db.delete(self.conv, other))
        self.assertEqual(self.db.get(self.conv, self.owner), before)

    @case("DB-003", "Retry cùng request_id giữ nguyên nội dung và thời gian", "Lưu lại request_id với câu hỏi khác", "Không thêm/sửa lượt cũ; has_request=True")
    def test_duplicate_request_does_not_overwrite_original_or_timestamp(self):
        request = str(uuid4())
        first = self.save(request)
        self.assertTrue(self.db.has_request(self.conv, request))
        self.assertEqual(self.save(request, "Nội dung thay đổi"), first)
        self.assertFalse(self.db.has_request(self.conv, str(uuid4())))

    @case("DB-004", "request_id chỉ duy nhất trong một hội thoại", "Hai hội thoại dùng chung UUID request", "Mỗi hội thoại có đúng 2 tin nhắn")
    def test_same_request_is_independent_between_conversations(self):
        request = str(uuid4())
        self.save(request)
        second = self.db.create(self.owner)["id"]
        self.assertEqual(len(self.db.save_turn(second, self.owner, request, "x", "y", "llm", [])["messages"]), 2)
        self.assertEqual(len(self.db.get(self.conv, self.owner)["messages"]), 2)

    @case("DB-005", "Tiêu đề cắt đúng 60 ký tự Unicode và giữ sau lượt hai", "Câu hỏi 80 ký tự có dấu, sau đó câu khác", "title=question[:60], không đổi theo lượt tiếp theo")
    def test_unicode_title_boundary_and_first_question_only(self):
        question = "Đường dẫn kiểm thử có dấu " * 4
        result = self.save(question=question)
        self.assertEqual(result["title"], question[:60])
        self.assertEqual(len(result["title"]), 60)
        self.assertEqual(self.save(question="Câu hỏi tiếp theo")["title"], question[:60])

    @case("DB-006", "Thứ tự cặp tin nhắn khi timestamp giống nhau", "3 lượt, mock now() thành cùng timestamp", "user/assistant đúng thứ tự chèn, ID duy nhất")
    def test_message_sequence_does_not_depend_on_timestamp(self):
        with patch("BE.database.now", return_value="2026-11-11T00:00:00+00:00"):
            for question in ("một", "hai", "ba"):
                result = self.save(question=question)
        self.assertEqual([m["role"] for m in result["messages"]], ["user", "assistant"] * 3)
        self.assertEqual([m["text"] for m in result["messages"]][::2], ["một", "hai", "ba"])
        self.assertEqual(len({m["id"] for m in result["messages"]}), 6)

    @case("DB-007", "Danh sách xếp updated_at giảm dần, ID tăng khi hòa", "3 hội thoại có thời gian xác định", "Đúng thứ tự cập nhật và thứ tự phụ theo ID")
    def test_list_sorting_and_tie_breaker(self):
        with patch("BE.database.now", return_value="2026-11-12T00:00:00+00:00"):
            newer = [self.db.create(self.owner)["id"] for _ in range(2)]
        self.assertEqual([c["id"] for c in self.db.list(self.owner)], sorted(newer) + [self.conv])

    @case("DB-008", "Cascade xóa tin nhắn và feedback, giữ hội thoại khác", "2 hội thoại, mỗi hội thoại có lượt và feedback", "Chỉ dữ liệu của hội thoại bị xóa biến mất")
    def test_delete_cascades_messages_and_feedback_without_touching_other_conversation(self):
        result = self.save()
        assistant = result["messages"][1]["id"]
        self.assertTrue(self.db.save_feedback(assistant, self.owner, 1))
        second = self.db.create(self.owner)["id"]
        other = self.db.save_turn(second, self.owner, str(uuid4()), "khác", "đáp", "llm", [])
        self.assertTrue(self.db.delete(self.conv, self.owner))
        store = storage._MEMORY_STORES[self.db._store_key]
        self.assertFalse(any(m["conversation_id"] == self.conv for m in store["messages"]))
        self.assertNotIn(assistant, store["feedback"])
        self.assertEqual(self.db.get(second, self.owner), other)

    @case("DB-009", "Không để caller sửa dữ liệu sources/attachments đã lưu", "Sửa input và kết quả get() sau save_turn", "Dữ liệu đọc lại giữ nguyên")
    def test_sources_and_attachments_are_defensive_copies(self):
        sources, attachments = [{"content": "fixture"}], [{"id": "test-file", "filename": "fixture.pdf", "size": 1}]
        result = self.db.save_turn(self.conv, self.owner, str(uuid4()), "hỏi", "đáp", "llm", sources, attachments)
        expected = deepcopy(result)
        sources[0]["content"] = "changed"
        attachments[0]["filename"] = "changed"
        result["messages"][1]["sources"].clear()
        result["messages"][0]["attachments"].clear()
        self.assertEqual(self.db.get(self.conv, self.owner), expected)

    @case("DB-010", "Rollback khi lỗi trước lúc ghi lượt", "now() ném RuntimeError", "Lỗi được truyền ra và trạng thái không đổi")
    def test_failure_before_insert_keeps_store_unchanged(self):
        before = self.db.get(self.conv, self.owner)
        with patch("BE.database.now", side_effect=RuntimeError("injected clock failure")):
            with self.assertRaises(RuntimeError):
                self.save()
        self.assertEqual(self.db.get(self.conv, self.owner), before)

    @case("DB-011", "Rollback khi lỗi giữa user và assistant ở RAM", "deepcopy(sources) lỗi lúc tạo assistant", "Không lưu nửa lượt; snapshot trước/sau giống nhau")
    def test_failure_on_assistant_insert_rolls_back_entire_memory_turn(self):
        before = self.db.get(self.conv, self.owner)
        sources = [{"content": "fixture"}]
        def injected(value):
            if value is sources:
                raise RuntimeError("injected assistant serialization failure")
            return deepcopy(value)
        with patch("BE.database.deepcopy", side_effect=injected):
            with self.assertRaises(RuntimeError):
                self.save(sources=sources)
        after = self.db.get(self.conv, self.owner)
        self.observed = f"Trước lỗi: {len(before['messages'])}; sau lỗi: {len(after['messages'])} tin nhắn."
        self.assertEqual(after, before, self.observed)

    @case("DB-012", "Mongo mock: lỗi ghi assistant phải rollback user", "insert_one thứ hai ném RuntimeError; không Mongo thật", "Không còn tin nhắn trong collection mock")
    def test_mongo_partial_write_is_atomic_under_second_insert_failure(self):
        convs, msgs, feedback = Mock(), Mock(), Mock()
        convs.find_one.return_value = {"id": self.conv, "owner": self.owner}
        msgs.find_one.return_value = None
        inserted = []
        def insert(doc):
            if doc["role"] == "assistant":
                raise RuntimeError("injected mongo second insert failure")
            inserted.append(doc)
        msgs.insert_one.side_effect = insert
        # Separate logical namespace: a Mongo conversation is not mirrored in RAM.
        mongo = Database(self.path / "mock-mongo", use_mongo=False)
        mongo.use_mongo = True
        self.addCleanup(storage._MEMORY_STORES.pop, mongo._store_key, None)
        with patch("BE.database.is_mongo_configured", return_value=True), \
                patch.object(mongo, "_with_mongo", side_effect=lambda fn: fn(convs, msgs, feedback)):
            mongo.save_turn(self.conv, self.owner, str(uuid4()), "hỏi", "đáp", "llm", [])
        self.observed = f"Collection mock còn {len(inserted)} tin nhắn: {[m['role'] for m in inserted]}."
        self.assertEqual(inserted, [], self.observed)

