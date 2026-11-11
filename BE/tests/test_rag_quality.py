"""Frozen, source-grounded top-3 golden questions; no model or network used."""
import json
import os
from pathlib import Path
from unittest.mock import patch

from BE.knowledge import Knowledge
from BE.tests.qa_support import DATA, OfflineCase, SAFE_SETTINGS, case

GOLDEN = json.loads(Path(__file__).with_name("golden_set.json").read_text(encoding="utf-8"))


def evidence_hit(results, evidence):
    for target in evidence:
        contents = [s["content"].casefold() for s in results if s["source_file"] == target["source_file"]]
        if not contents or not all(any(text.casefold() in content for content in contents)
                                   for text in target["expected_strings"]):
            return False
        if not all(any(text.casefold() in content for text in group for content in contents)
                   for group in target.get("expected_any_strings", [])):
            return False
    return True


class RagQualityTests(OfflineCase):
    @classmethod
    def setUpClass(cls):
        cls.records = []
        with patch.dict(os.environ, SAFE_SETTINGS):
            cls.knowledge = Knowledge(DATA)

    @classmethod
    def tearDownClass(cls):
        positives = [r for r in cls.records if not r["negative"]]
        negatives = [r for r in cls.records if r["negative"]]
        print("\nRAG GOLDEN SET | file + substring evidence (case-insensitive) | lexical | top-3")
        print("ID       | hit@1 | hit@3 | sources(top-3) | question")
        for row in cls.records:
            print(f"{row['id']:8} | {str(row['hit1']):5} | {str(row['hit3']):5} | "
                  f"{','.join(s['source_file'] for s in row['retrieved']) or '(empty)'} | {row['question']}")
        if positives:
            print(f"hit@1 = {sum(r['hit1'] for r in positives)}/{len(positives)}; "
                  f"hit@3 = {sum(r['hit3'] for r in positives)}/{len(positives)}")
        print(f"Out-of-scope empty sources = {sum(r['passed'] for r in negatives)}/{len(negatives)}")
        output = os.environ.get("PTIT_QA_OUTPUT")
        if output:
            Path(output).with_name("rag_results.json").write_text(json.dumps(
                {"config": {k: GOLDEN[k] for k in ("retrieval_backend", "limit", "chunk_size", "chunk_overlap")},
                 "records": cls.records}, ensure_ascii=False, indent=2), encoding="utf-8")


def golden_test(item):
    def test(self):
        # Verify every asserted fact against the actual source body, independently
        # of retrieval. A typo in the golden fixture is a test error, not a miss.
        for target in item["evidence"]:
            source_text = (DATA / target["source_file"]).read_text(encoding="utf-8-sig")
            for expected in target["expected_strings"]:
                self.assertIn(expected, source_text, "Golden fixture does not match source data")
            for group in target.get("expected_any_strings", []):
                for expected in group:
                    self.assertIn(expected, source_text, "Golden alternative does not match source data")
        sources = self.knowledge.retrieve(item["question"], limit=GOLDEN["limit"])
        negative = not item["evidence"]
        answer_sources = None
        if negative:
            text, mode, answer_sources = self.knowledge.answer(item["question"])
            passed = sources == [] and answer_sources == [] and mode == "retrieval_only" and "chưa tìm thấy" in text
        else:
            passed = evidence_hit(sources[:3], item["evidence"])
        hit1 = None if negative else evidence_hit(sources[:1], item["evidence"])
        hit3 = None if negative else evidence_hit(sources[:3], item["evidence"])
        row = {**item, "negative": negative, "hit1": hit1, "hit3": hit3, "passed": passed,
               "retrieved": sources, "answer_sources": answer_sources}
        self.records.append(row)
        self.observed = json.dumps({"hit@1": hit1, "hit@3": hit3,
            "top3": [{"file": s["source_file"], "title": s["title"], "content": s["content"]} for s in sources]}, ensure_ascii=False)
        self.assertLessEqual(len(sources), 3)
        self.assertTrue(passed, self.observed)
    expected = "retrieve và answer đều sources=[]; retrieval_only; chưa tìm thấy" if not item["evidence"] else json.dumps(item["evidence"], ensure_ascii=False) + " trong top-3"
    return case(item["id"], "Golden RAG: " + item["category"], item["question"], expected)(test)


for _item in GOLDEN["cases"]:
    setattr(RagQualityTests, "test_" + _item["id"].lower().replace("-", "_") + "_" + (
        "out_of_scope" if not _item["evidence"] else "evidence_in_top_three"), golden_test(_item))

