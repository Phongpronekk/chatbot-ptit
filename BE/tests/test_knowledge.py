"""Parser/retrieval/generation branches; LangChain providers are module mocks."""
import json
import os
import shutil
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

import yaml

from BE.knowledge import Knowledge
from BE.search_text import terms
from BE.tests.qa_support import DATA, OfflineCase, case


class KnowledgeExtraTests(OfflineCase):
    def setUp(self):
        super().setUp()
        self.data = self.path / "data"
        self.data.mkdir()
        self.front = yaml.safe_load((DATA / "ktx.md").read_text(encoding="utf-8-sig").split("---", 2)[1])

    def document(self, front=None, body="# Fixture\nNội dung kiểm thử cấu trúc.", raw=None):
        text = raw if raw is not None else "---\n" + yaml.safe_dump(
            self.front if front is None else front, allow_unicode=True) + "---\n" + body
        (self.data / "fixture.md").write_text(text, encoding="utf-8")
        return Knowledge(self.data)

    def real_knowledge_and_source(self):
        shutil.copyfile(DATA / "ktx.md", self.data / "ktx.md")
        knowledge = Knowledge(self.data)
        source = next(c for c in knowledge.chunks() if "250.000" in c["content"])
        return knowledge, {**source, "score": 1.0, "score_type": "bm25"}

    def llm_modules(self, provider, content=None, error=None):
        name, constructor = ("langchain_anthropic", "ChatAnthropic") if provider == "anthropic" else (
            "langchain_google_genai", "ChatGoogleGenerativeAI")
        module = ModuleType(name)
        factory = Mock()
        setattr(module, constructor, factory)
        factory.return_value.invoke.return_value = SimpleNamespace(content=content)
        factory.return_value.invoke.side_effect = error
        truststore = ModuleType("truststore")
        truststore.SSLContext = Mock()
        return {name: module, "truststore": truststore}, factory

    @case("KN-001", "Token hóa dấu tiếng Việt, đ/Đ và chữ hoa", "ĐƯỜNG ĐIỆN, điện tử", "['duong','dien','dien','tu']")
    def test_terms_fold_d_stroke_and_accents_with_repeated_tokens(self):
        self.assertEqual(terms("ĐƯỜNG ĐIỆN, điện tử"), ["duong", "dien", "dien", "tu"])

    @case("KN-002", "Token hóa chuỗi rỗng và dấu câu", "'', khoảng trắng, !!!", "Danh sách token rỗng")
    def test_empty_whitespace_and_punctuation_have_no_terms(self):
        for value in ("", " \t\n", "!?…"):
            with self.subTest(value=value):
                self.assertEqual(terms(value), [])

    @case("KN-003", "Bỏ stop word tiếng Việt", "tôi mình em bạn xin hỏi cho biết về của là và", "Danh sách token rỗng")
    def test_stopword_only_question_has_no_terms(self):
        self.assertEqual(terms("tôi mình em bạn xin hỏi cho biết về của là và"), [])

    @case("KN-004", "Front-matter BOM/CRLF và ngày YAML", "Metadata lấy từ data/ktx.md; BOM, CRLF", "Parse đúng; fetched_date chuyển thành chuỗi ISO")
    def test_frontmatter_accepts_bom_crlf_and_yaml_date(self):
        front = {**self.front, "fetched_date": yaml.safe_load("2026-10-29")}
        raw = "\ufeff---\n" + yaml.safe_dump(front, allow_unicode=True) + "---\n# Fixture\nNội dung."
        knowledge = self.document(raw=raw.replace("\n", "\r\n"))
        meta = knowledge.sources()[0]
        self.assertEqual(meta["source_url"], self.front["source_url"])
        self.assertEqual(meta["fetched_date"], self.front["fetched_date"])

    @case("KN-005", "Thiếu khối front-matter", "Markdown chỉ có heading/body", "ValueError nêu tên file")
    def test_missing_frontmatter_raises_value_error(self):
        with self.assertRaisesRegex(ValueError, "front-matter.*fixture.md"):
            self.document(raw="# Fixture\nBody").documents()

    @case("KN-006", "YAML lỗi cú pháp", "source_url: [ chưa đóng", "ValueError YAML không hợp lệ")
    def test_malformed_yaml_is_reported_as_value_error(self):
        with self.assertRaisesRegex(ValueError, "YAML không hợp lệ"):
            self.document(raw="---\nsource_url: [\n---\n# Fixture\nBody").documents()

    @case("KN-007", "YAML không phải mapping", "Front-matter là list", "ValueError Metadata không hợp lệ")
    def test_frontmatter_list_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Metadata không hợp lệ"):
            self.document(raw="---\n- one\n- two\n---\n# Fixture\nBody").documents()

    @case("KN-008", "Các metadata bắt buộc thiếu hoặc rỗng", "Lần lượt thiếu/None/'' ở source_url, fetched_date, topic_group", "Mỗi trường hợp đều ValueError")
    def test_required_metadata_rejects_missing_and_empty_values(self):
        for key in ("source_url", "fetched_date", "topic_group"):
            for value in (None, "", "missing"):
                with self.subTest(key=key, value=value):
                    front = dict(self.front)
                    if value == "missing":
                        del front[key]
                    else:
                        front[key] = value
                    with self.assertRaisesRegex(ValueError, "Metadata không hợp lệ"):
                        self.document(front).documents()

    @case("KN-009", "Từ chối sai kiểu metadata nguồn", "source_url là mapping thay vì chuỗi URL", "ValueError trước khi metadata vào index")
    def test_mapping_source_url_is_invalid_metadata(self):
        with self.assertRaises(ValueError):
            self.document({**self.front, "source_url": {"unexpected": "mapping"}}).documents()

    @case("KN-010", "Từ chối ngày metadata sai định dạng", "fetched_date='not-a-date'", "ValueError")
    def test_invalid_fetched_date_is_rejected(self):
        with self.assertRaises(ValueError):
            self.document({**self.front, "fetched_date": "not-a-date"}).documents()

    @case("KN-011", "Chia heading lồng nhau và reset heading ngang cấp", "# Root / ## A / ### Child / ## B, mỗi phần có body", "4 chunk đúng title; B không kế thừa A/Child")
    def test_heading_hierarchy_and_sibling_reset(self):
        knowledge = self.document(body="# Root\nroot body\n## A\nalpha body\n### Child\nchild body\n## B\nbeta body")
        chunks = knowledge.chunks()
        self.assertEqual([c["title"] for c in chunks], ["Root", "Root / A", "Root / A / Child", "Root / B"])
        self.assertEqual([c["content"] for c in chunks], ["root body", "alpha body", "child body", "beta body"])
        self.assertTrue(all(c["source_url"] == self.front["source_url"] for c in chunks))

    @case("KN-012", "Heading không body không sinh chunk rỗng", "Heading liền nhau, cuối file chỉ heading", "Chỉ phần có nội dung thành chunk")
    def test_heading_only_sections_do_not_create_empty_chunks(self):
        chunks = self.document(body="# Root\n## Empty\n### Filled\nbody\n## Tail").chunks()
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["title"], "Root / Empty / Filled")

    @case("KN-013", "Giới hạn truy xuất top-k được truyền rõ", "6 heading có từ khóa chung; limit=1,3,5", "Trả đúng limit, không lặp nội dung")
    def test_explicit_retrieval_limits_are_respected(self):
        knowledge = self.document(body="\n".join(f"# Mục {i}\nTừ khóa xenon nội dung riêng {i}." for i in range(6)))
        for limit in (1, 3, 5):
            with self.subTest(limit=limit):
                result = knowledge.retrieve("xenon", limit=limit)
                self.assertEqual(len(result), limit)
                self.assertEqual(len({c["content"] for c in result}), limit)

    @case("KN-014", "answer khi thư mục dữ liệu rỗng", "Thư mục tạm không có Markdown", "ValueError Kho dữ liệu chưa có tài liệu")
    def test_answer_rejects_empty_document_directory(self):
        with self.assertRaisesRegex(ValueError, "chưa có tài liệu"):
            Knowledge(self.data).answer("KTX")

    @case("KN-015", "Không khớp thì không khởi tạo LLM", "Câu hỏi thiên văn ngoài phạm vi", "chưa tìm thấy; retrieval_only; sources=[]; không gọi LLM")
    def test_no_match_short_circuits_generation(self):
        knowledge, _ = self.real_knowledge_and_source()
        with patch.object(knowledge, "answer_from_sources") as generate:
            text, mode, sources = knowledge.answer("quasar supernova astrophysics")
        self.assertIn("chưa tìm thấy", text)
        self.assertEqual((mode, sources), ("retrieval_only", []))
        generate.assert_not_called()

    @case("KN-016", "Không key cloud trả nguồn và retrieval_only", "anthropic/google, key rỗng hoặc toàn khoảng trắng", "Giữ nguồn thật; không khởi tạo model")
    def test_missing_or_whitespace_keys_return_retrieval_sources(self):
        knowledge, source = self.real_knowledge_and_source()
        for provider, key in (("anthropic", "ANTHROPIC_API_KEY"), ("google", "GOOGLE_API_KEY")):
            for value in ("", "  "):
                with self.subTest(provider=provider, value=value), patch.dict(os.environ, {"LLM_PROVIDER": provider, key: value}):
                    with patch.object(knowledge, "_resolve_sources_for_question", return_value=([source], False)):
                        _, mode, sources = knowledge.answer("Lệ phí nội trú?")
                    self.assertEqual((mode, sources), ("retrieval_only", [source]))

    @case("KN-017", "Provider ngoài danh sách code hiện tại", "LLM_PROVIDER=unsupported", "ValueError; code hiện hỗ trợ anthropic/google/ollama")
    def test_unsupported_provider_is_rejected(self):
        knowledge, source = self.real_knowledge_and_source()
        with patch.dict(os.environ, {"LLM_PROVIDER": "unsupported"}), self.assertRaisesRegex(ValueError, "LLM_PROVIDER"):
            knowledge.answer_from_sources("hỏi", [source])

    @case("KN-018", "Key giả nhưng thiếu MODEL_NAME", "anthropic/google; key unit-test-placeholder; model trắng", "ValueError MODEL_NAME trước khi import provider")
    def test_cloud_key_requires_model_name(self):
        knowledge, source = self.real_knowledge_and_source()
        for provider, key in (("anthropic", "ANTHROPIC_API_KEY"), ("google", "GOOGLE_API_KEY")):
            with self.subTest(provider=provider), patch.dict(os.environ, {"LLM_PROVIDER": provider, key: "unit-test-placeholder", "MODEL_NAME": " "}):
                with self.assertRaisesRegex(ValueError, "MODEL_NAME"):
                    knowledge.answer_from_sources("hỏi", [source])

    @case("KN-019", "Anthropic mock trả văn bản có căn cứ", "Module LangChain giả; nội dung lấy từ ktx.md", "mode=llm; nội dung/nguồn giữ nguyên; invoke đúng một lần")
    def test_anthropic_mock_generates_text_with_original_sources(self):
        knowledge, source = self.real_knowledge_and_source()
        content = source["content"]
        modules, factory = self.llm_modules("anthropic", content)
        with patch.dict(sys.modules, modules), patch.dict(os.environ, {"ANTHROPIC_API_KEY": "unit-test-placeholder", "MODEL_NAME": "qa-model"}), \
                patch.object(knowledge, "_resolve_sources_for_question", return_value=([source], False)):
            answer = knowledge.answer("Lệ phí nội trú?")
        self.assertEqual(answer, (content, "llm", [source]))
        factory.assert_called_once()
        factory.return_value.invoke.assert_called_once()
        prompt = str(factory.return_value.invoke.call_args.args[0])
        self.assertIn(source["source_url"], prompt)

    @case("KN-020", "Google mock hỗ trợ content list block", "Hai text block từ nguồn thật và một non-text block", "Ghép text bằng newline; mode llm; giữ sources")
    def test_google_mock_joins_list_blocks_and_ignores_missing_text(self):
        knowledge, source = self.real_knowledge_and_source()
        blocks = [{"type": "text", "text": source["title"]}, {"type": "image"}, {"type": "text", "text": source["content"]}]
        modules, factory = self.llm_modules("google", blocks)
        with patch.dict(sys.modules, modules), patch.dict(os.environ, {"LLM_PROVIDER": "google", "GOOGLE_API_KEY": "unit-test-placeholder", "MODEL_NAME": "qa-model"}):
            text, mode, sources = knowledge.answer_from_sources("hỏi", [source])
        self.assertEqual(text, source["title"] + "\n\n" + source["content"])
        self.assertEqual((mode, sources), ("llm", [source]))
        factory.return_value.invoke.assert_called_once()

    @case("KN-021", "LLM trả nội dung rỗng hoặc sai kiểu", "'', whitespace, [], [{}], None, số nguyên", "Mỗi trường hợp RuntimeError LLM không trả về nội dung")
    def test_empty_llm_content_variants_raise_runtime_error(self):
        knowledge, source = self.real_knowledge_and_source()
        for content in ("", " \n", [], [{}], None, 17):
            modules, _ = self.llm_modules("anthropic", content)
            with self.subTest(content=content), patch.dict(sys.modules, modules), patch.dict(os.environ, {"ANTHROPIC_API_KEY": "unit-test-placeholder", "MODEL_NAME": "qa-model"}):
                with self.assertRaisesRegex(RuntimeError, "không trả về nội dung"):
                    knowledge.answer_from_sources("hỏi", [source])

    @case("KN-022", "Provider mock lỗi thì dùng nhánh fallback hiện tại", "invoke ném RuntimeError", "retrieval_only, vẫn giữ nguồn; không gọi provider thật")
    def test_cloud_invoke_failure_falls_back_to_sources(self):
        knowledge, source = self.real_knowledge_and_source()
        modules, _ = self.llm_modules("anthropic", error=RuntimeError("injected provider outage"))
        with patch.dict(sys.modules, modules), patch.dict(os.environ, {"ANTHROPIC_API_KEY": "unit-test-placeholder", "MODEL_NAME": "qa-model"}):
            text, mode, sources = knowledge.answer_from_sources("hỏi", [source])
        self.assertTrue(text)
        self.assertEqual((mode, sources), ("retrieval_only", [source]))

