from pathlib import Path
import unittest
from unittest.mock import patch

from BE.knowledge import Knowledge, standalone_question


class MultiTurnContextTests(unittest.TestCase):
    def setUp(self):
        self.data_dir = Path(__file__).resolve().parents[2] / "data"
        self.knowledge = Knowledge(self.data_dir)

    def test_standalone_question_expands_follow_up_cues(self):
        history = [
            {"role": "user", "text": "Ký túc xá PTIT có những tòa nào?"},
            {"role": "assistant", "text": "Học viện có các tòa ký túc xá B1, B2, B5..."},
        ]
        result = standalone_question("Thế còn B1 thì sao?", history)
        self.assertIn("ký túc xá", result.lower())
        self.assertIn("B1", result)

    def test_standalone_question_expands_short_implicit_query(self):
        history = [
            {"role": "user", "text": "Ký túc xá PTIT có những tòa nào?"},
            {"role": "assistant", "text": "Học viện có các tòa KTX..."},
        ]
        result = standalone_question("Toà B1 bao nhiêu tiền?", history)
        self.assertIn("ký túc xá", result.lower())
        self.assertIn("B1", result)

    def test_independent_query_with_domain_term_is_not_contaminated(self):
        history = [
            {"role": "user", "text": "Ký túc xá PTIT có những tòa nào?"},
            {"role": "assistant", "text": "Học viện có các tòa KTX..."},
        ]
        result = standalone_question("Học phí ngành CNTT bao nhiêu?", history)
        self.assertEqual(result, "Học phí ngành CNTT bao nhiêu?")
        self.assertNotIn("Ký túc xá", result)

    def test_follow_up_retrieves_correct_context_from_data(self):
        history = [
            {"role": "user", "text": "Ký túc xá PTIT có những tòa nào?"},
            {"role": "assistant", "text": "Có các tòa B1, B2, B5..."},
        ]
        # Follow-up question without direct mention of "Ký túc xá"
        search_q = standalone_question("Thế còn B1 thì sao?", history)
        sources = self.knowledge.retrieve(search_q)
        self.assertTrue(len(sources) > 0, "Câu hỏi nối tiếp 'Thế còn B1 thì sao?' phải tìm thấy nguồn")
        self.assertEqual(sources[0]["source_file"], "ktx.md")
        self.assertTrue(any("B1" in s["content"] for s in sources), "Nguồn trả về phải chứa thông tin tòa B1")

    def test_exclusion_and_broad_topic_switch_ngoai_ktx(self):
        history = [
            {"role": "user", "text": "KTX B2 mức thu bao nhiêu?"},
            {
                "role": "assistant",
                "text": "Mức thu KTX B2 là 250.000đ/tháng.",
                "sources": [{"source_file": "ktx.md", "topic_group": "Ký túc xá"}],
            },
        ]
        plan = self.knowledge.plan_retrieval("thong tin khac ngoai ktx", history)
        self.assertIn("ktx.md", plan["exclude_files"])
        self.assertTrue(plan["broad_overview"])
        self.assertTrue(plan["diversify"])

        sources = self.knowledge.sample_diverse_sources(exclude_files=plan["exclude_files"])
        self.assertTrue(len(sources) >= 3)
        source_files = {s["source_file"] for s in sources}
        self.assertNotIn("ktx.md", source_files)
        # Phải lấy đa dạng từ nhiều nhóm chủ đề khác nhau
        self.assertEqual(len(source_files), len(sources))

    def test_implicit_topic_switch_excludes_previous_turn_source(self):
        history = [
            {"role": "user", "text": "KTX B2 mức thu bao nhiêu?"},
            {
                "role": "assistant",
                "text": "Mức thu KTX B2 là 250.000đ/tháng.",
                "sources": [{"source_file": "ktx.md", "topic_group": "Ký túc xá"}],
            },
        ]
        plan = self.knowledge.plan_retrieval("còn thông tin gì khác không?", history)
        self.assertIn("ktx.md", plan["exclude_files"])
        self.assertTrue(plan["broad_overview"])

    def test_exclusion_with_specific_new_topic(self):
        history = [
            {"role": "user", "text": "KTX B2 mức thu bao nhiêu?"},
            {
                "role": "assistant",
                "text": "Mức thu KTX B2 là 250.000đ/tháng.",
                "sources": [{"source_file": "ktx.md", "topic_group": "Ký túc xá"}],
            },
        ]
        plan = self.knowledge.plan_retrieval("ngoài ktx thì thực tập tốt nghiệp thế nào?", history)
        self.assertIn("ktx.md", plan["exclude_files"])
        self.assertFalse(plan["broad_overview"])
        sources = self.knowledge.retrieve(
            plan["search_query"],
            exclude_files=plan["exclude_files"],
            diversify=plan["diversify"],
        )
        self.assertTrue(len(sources) > 0)
        self.assertNotIn("ktx.md", {s["source_file"] for s in sources})
        self.assertIn("thuc_tap_viec_lam.md", {s["source_file"] for s in sources})

    def test_subtopic_exclusion_within_same_topic_does_not_exclude_target_file(self):
        history = [
            {"role": "user", "text": "KTX B2 mức thu bao nhiêu?"},
            {
                "role": "assistant",
                "text": "Mức thu KTX B2 là 250.000đ/tháng.",
                "sources": [{"source_file": "ktx.md", "topic_group": "Ký túc xá"}],
            },
        ]
        q = "ngoai thong tin ve cho o, ktx con thong tin quan trong nao khac"
        plan = self.knowledge.plan_retrieval(q, history)
        self.assertNotIn("ktx.md", plan["exclude_files"])
        self.assertFalse(plan["broad_overview"])
        sources = self.knowledge.retrieve(
            plan["search_query"],
            exclude_files=plan["exclude_files"],
            diversify=plan["diversify"],
        )
        self.assertTrue(len(sources) > 0)
        self.assertIn("ktx.md", {s["source_file"] for s in sources})

    def test_conversational_challenge_follow_up_keeps_context(self):
        history = [
            {"role": "user", "text": "co nhung clb nao"},
            {
                "role": "assistant",
                "text": "Có Câu lạc bộ Thư viện PTIT (ILC).",
                "sources": [{"source_file": "clb.md", "topic_group": "Câu lạc bộ (CLB)"}],
            },
        ]
        for q in ["the tai sao b lai bao k co ten clb nao", "the tai sao b lai bao k co"]:
            sources, broad = self.knowledge._resolve_sources_for_question(q, history)
            self.assertFalse(broad)
            self.assertTrue(len(sources) > 0, f"Follow-up '{q}' must resolve sources")
            self.assertEqual(sources[0]["source_file"], "clb.md")
            self.assertTrue(any("ILC" in s["content"] for s in sources))

    def test_dynamic_topic_catalog_discovers_all_files(self):
        catalog = self.knowledge.topic_catalog()
        files = {item["source_file"] for item in catalog}
        self.assertIn("ktx.md", files)
        self.assertIn("clb.md", files)
        self.assertIn("thuc_tap_viec_lam.md", files)
        summary = self.knowledge.catalog_summary()
        self.assertIn("Ký túc xá", summary)
        self.assertIn("Thực tập", summary)


if __name__ == "__main__":
    unittest.main()

