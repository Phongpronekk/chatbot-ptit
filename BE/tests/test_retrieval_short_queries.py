import os
from pathlib import Path
import unittest
from unittest.mock import patch

from BE.knowledge import Knowledge
from BE.search_text import canonical, terms, normalize_query, fold


class ShortQueryAndAbbreviationTests(unittest.TestCase):
    def setUp(self):
        self.data_dir = Path(__file__).resolve().parents[2] / "data"
        self.knowledge = Knowledge(self.data_dir)

    def test_short_queries_find_relevant_sources(self):
        queries = [
            "co clb nao",
            "danh sach cau lac bo",
            "danh sach clb",
            "neu ten tat ca clb",
            "neu ten tat ca clbb",
            "KTX B2 muc thu bao nhieu",
            "sv ptit",
            "thuc tap tot nghiep",
            "dki hoc phan",
        ]
        for q in queries:
            with self.subTest(query=q):
                results = self.knowledge.retrieve(q)
                self.assertTrue(len(results) > 0, f"Query '{q}' returned no results")

    def test_unrelated_queries_are_rejected(self):
        unrelated = [
            "quasar supernova astrophysics",
            "giá bitcoin hôm nay",
            "cách làm bánh pizza hải sản",
            "thời tiết ngày mai tại paris",
        ]
        for q in unrelated:
            with self.subTest(query=q):
                results = self.knowledge.retrieve(q)
                self.assertEqual(results, [], f"Query '{q}' should be rejected but got {results}")

    def test_ktx_buildings_query_returns_all_three_buildings_b1_b2_b5(self):
        results = self.knowledge.retrieve("co bao nhieu toa ktx")
        self.assertTrue(len(results) > 0)
        combined = "\n".join(r["content"] for r in results)
        self.assertIn("B1", combined)
        self.assertIn("B2", combined)
        self.assertIn("B5", combined)

    def test_clb_name_queries_include_ilc_article(self):
        for q in ["neu ten tat ca clb", "neu ten tat ca clbb", "neu ten tat clb dang co", "gom co clb nao"]:
            with self.subTest(query=q):
                results = self.knowledge.retrieve(q)
                self.assertTrue(len(results) > 0)
                self.assertEqual(results[0]["source_file"], "clb.md")
                self.assertTrue(any("ILC" in r["content"] for r in results), f"Query '{q}' missed ILC chunk")

    def test_student_abbreviations_expansion(self):
        self.assertIn("sinh viên", canonical("sv ptit"))
        self.assertIn("đăng ký", canonical("dki hoc phan"))
        self.assertIn("giảng viên chủ nhiệm", canonical("gvcn lop toi"))
        self.assertIn("điểm trung bình tích lũy", canonical("cpa ra truong"))


if __name__ == "__main__":
    unittest.main()

