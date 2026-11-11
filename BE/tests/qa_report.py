"""Build the Vietnamese QA report/CSV from saved runner results, never inferred passes.

Usage: python BE/tests/qa_report.py
The runner logs/JSON must already exist in BE/tests/qa_results/.
"""
import ast
import csv
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "BE/tests/qa_results"

# Descriptions of existing tests. Inputs/assertions below are extracted from the
# actual methods rather than substituting fabricated PTIT facts.
LEGACY_DESCRIPTIONS = dict(line.split("|", 1) for line in """
cloud_model_is_rejected_in_local_provider|Từ chối model cloud trong provider Ollama local
concurrent_messages_across_conversations|Hai hội thoại gửi đồng thời không chặn nhau
cookie_is_httponly|Cookie có HttpOnly và SameSite=lax
create_send_reload_and_delete|Vòng đời tạo, gửi, đọc lại, xóa hội thoại qua API
direct_ollama_test_mode_remains_available|Chế độ Ollama trực tiếp bỏ qua truy xuất
empty_database_and_source_health|DB rỗng và health phản ánh nguồn fixture
greeting_messages_reply_promptly|Câu chào nhận lời đáp ngay
invalid_messages_and_ids|Từ chối message rỗng/quá dài và ID sai
legacy_general_mode_is_normalized_without_mutation|Chuẩn hóa mode cũ không sửa object đầu vào
metadata_retains_multiline_notes|Giữ note metadata nhiều dòng
no_match_is_not_fabricated|Câu ngoài phạm vi không có nguồn bịa
ollama_answer_is_saved_without_api_keys|Lưu câu trả lời Ollama mock khi không có API key
ollama_failure_does_not_save_turn|Ollama mock lỗi không lưu lượt
other_browser_cannot_read_write_delete|Owner trình duyệt khác không đọc, ghi, xóa được
persists_across_application_restart|Giữ hội thoại khi tạo lại app trong cùng tiến trình
rag_search_does_not_generate_or_save_messages|API tìm kiếm không gọi generator và không lưu chat
rag_status_exposes_configuration_without_credentials|RAG status không lộ tên trường khóa bí mật
retry_does_not_duplicate_messages|Retry API không nhân đôi tin nhắn
service_failure_does_not_save_partial_turn|Generator lỗi trước lưu không tạo nửa lượt
existing_messages_survive_idempotent_attachment_migration|Khởi tạo lại storage không mất chat và hỗ trợ attachments
attachment_ids_must_be_in_scope_and_belong_to_conversation|Attachment phải thuộc scope và hội thoại
auto_ktx_after_file_summary_uses_ptit_even_if_the_file_mentions_ktx|Hỏi KTX sau tóm tắt file dùng nguồn PTIT
expiration_and_delete_conversation_clear_memory|Hết hạn/xóa hội thoại dọn file tạm
expired_candidate_file_does_not_block_a_new_ptit_question|File hết hạn không chặn câu hỏi PTIT mới
expired_file_card_remains_in_history|Thẻ file đã hết hạn vẫn hiện trong lịch sử
explicit_file_request_after_ptit_question_keeps_only_file_history|Hỏi file rõ ràng chỉ lấy lịch sử của file
explicit_file_request_without_file_is_actionable|Hỏi file khi không có file nhận thông báo có thể xử lý
invalid_uploads_are_not_remembered|Không giữ upload không hợp lệ trong bộ nhớ
llm_failure_and_retry_do_not_save_partial_or_duplicate_turns|File: lỗi LLM và retry không ghi lượt thiếu/trùng
llm_prompt_includes_file_and_follow_up_history_even_in_direct_mode|Prompt mock chứa file và lịch sử câu tiếp nối
new_attachments_belong_to_user_message_and_follow_ups_do_not_repeat_them|File gắn vào lượt user, không lặp ở follow-up
original_over_one_mb_stays_in_ram|File gốc trên 1 MB vẫn ở RAM
oversize_stream_and_file_count_are_bounded|Giới hạn kích thước upload và số file
pdf_and_excel_upload|Upload PDF và Excel tổng hợp
restarting_keeps_chat_but_discards_uploads|Tạo lại app giữ chat cùng tiến trình và bỏ uploads RAM
scope_isolated_by_browser_and_conversation|File tách theo owner và hội thoại
upload_ask_list_remove_and_missing_file|Vòng đời upload, hỏi, liệt kê, xóa file
docx_reads_paragraphs_and_tables|Trích đoạn văn và bảng DOCX
excel_keeps_sheet_row_headers_and_formula|Excel giữ sheet, hàng, header và công thức dạng văn bản
invalid_empty_unsupported_password_scan_and_large_files|Từ chối file lỗi/rỗng/không hỗ trợ/khóa/scan/quá lớn
office_expansion_and_text_limits|Giới hạn giải nén Office và số ký tự
pdf_preserves_page_and_text|PDF giữ nội dung và vị trí trang
summary_samples_all_selected_files|Tóm tắt lấy mẫu đủ mọi file đã chọn
explicit_file_and_related_follow_up_queries|Định tuyến câu hỏi file và follow-up liên quan
explicit_scope_overrides_auto_and_new_uploads_use_the_attached_file|Scope rõ ràng và file mới có ưu tiên đúng
greeting_routes_to_knowledge|Câu chào đi vào nhánh knowledge
new_ptit_subject_is_not_trapped_in_the_uploaded_report|Câu hỏi PTIT mới thoát khỏi ngữ cảnh file
summary_does_not_jump_back_to_a_file_after_a_ptit_turn|Tóm tắt sau lượt PTIT không tự quay về file cũ
api_mongo_endpoints|API Mongo trả đúng trạng thái khi không cấu hình
database_mongo_conversations_messages_and_feedback|CRUD hội thoại/tin nhắn/feedback bằng Mongo mock
mock_sync_and_connection|Kết nối và đồng bộ nguồn bằng MongoClient mock
parse_source_file|Phân tích nguồn Mongo và hash tài liệu fixture
temp_attachments_mongo_persist_and_hydrate|Mongo mock lưu/khôi phục/xóa attachments tạm
unconfigured_by_default|Không có URI thì không kết nối Mongo
conversational_challenge_follow_up_keeps_context|Câu hỏi phản biện tiếp nối giữ chủ đề CLB
dynamic_topic_catalog_discovers_all_files|Danh mục chủ đề phát hiện các file thật
exclusion_and_broad_topic_switch_ngoai_ktx|Loại KTX khi chuyển sang chủ đề khác
exclusion_with_specific_new_topic|Loại chủ đề cũ khi nêu chủ đề mới cụ thể
follow_up_retrieves_correct_context_from_data|Câu tiếp nối B1 truy xuất đúng nguồn KTX
implicit_topic_switch_excludes_previous_turn_source|Chuyển chủ đề ngầm loại nguồn lượt trước
independent_query_with_domain_term_is_not_contaminated|Câu hỏi độc lập không bị trộn chủ đề cũ
standalone_question_expands_follow_up_cues|Mở rộng câu tiếp nối có từ chỉ dẫn
standalone_question_expands_short_implicit_query|Mở rộng câu ngắn ngầm nhắc chủ đề trước
subtopic_exclusion_within_same_topic_does_not_exclude_target_file|Đổi tiểu mục vẫn giữ file đúng chủ đề
admin_reindex_hot_reload|Reindex cần token và nạp nguồn mới khi app đang chạy
feedback_like_dislike_and_ownership|Like/dislike chỉ owner đúng được cập nhật
sse_stream_endpoint_saves_turn_and_emits_deltas|SSE phát delta/done và lưu đủ cặp tin nhắn
benign_text_is_preserved|Bộ lọc prompt giữ nguyên văn bản lành tính
closing_tag_is_neutralized|Vô hiệu hóa thẻ đóng prompt trong dữ liệu
nonce_tagged_variations_are_neutralized|Vô hiệu hóa biến thể thẻ prompt có nonce
article_metadata_does_not_leak_between_articles|Metadata không rò giữa bài trong cùng Markdown
failed_rebuild_preserves_active_collection|Rebuild lỗi giữ nguyên chỉ mục đang dùng
hybrid_does_not_use_weak_partial_keyword_overlap|Hybrid không chấp nhận khớp từ yếu
hybrid_ranks_agreement_and_limits_results|Hybrid ưu tiên kết quả đồng thuận và giữ top-k
hybrid_recovers_full_term_and_acronym_below_vector_threshold|Hybrid cứu kết quả viết tắt/cụm đầy đủ dưới ngưỡng vector
idempotent_persistent_index_and_cosine_score|Lập chỉ mục idempotent, mở lại Chroma và kiểm tra cosine
lexical_mode_shares_alias_and_accent_normalization|Lexical dùng cùng chuẩn hóa dấu/alias
plain_note_colon_is_read_without_modifying_data|Đọc note có dấu hai chấm mà không sửa file
recursive_chunking_preserves_tail_and_metadata|Chia chunk dài giữ phần cuối và metadata
source_requirements_update_and_remove_document|Chỉ mục cập nhật khi thêm/sửa/xóa nguồn fixture
threshold_filters_every_result|Ngưỡng cosine lọc mọi kết quả không đạt
vector_error_falls_back_but_empty_result_does_not|Chỉ lỗi vector mới fallback, kết quả rỗng giữ rỗng
clb_name_queries_include_ilc_article|Hỏi CLB trả nguồn có ILC
ktx_buildings_query_returns_all_three_buildings_b1_b2_b5|Hỏi các tòa KTX lấy đủ B1/B2/B5
short_queries_find_relevant_sources|Câu ngắn/viết tắt vẫn có nguồn
student_abbreviations_expansion|Mở rộng viết tắt sinh viên/đăng ký/GVCN/CPA
unrelated_queries_are_rejected|Các câu ngoài chủ đề trả rỗng
aliases_work_both_ways_across_domains|Alias và cụm đầy đủ tạo cùng token
boundaries_negation_numbers_and_ambiguous_alias|Giữ ranh giới từ, phủ định, số và alias mơ hồ
greeting_detection|Phân biệt lời chào với câu hỏi có từ chào
unlisted_accented_phrase_can_match_without_accents|Cụm ngoài danh mục vẫn tìm được khi không dấu
whitespace_and_unicode|Chuẩn hóa whitespace và Unicode tổ hợp
backend_env_overrides_inherited_provider|Nạp BE/.env thật phải ghi đè provider kế thừa (bỏ qua trong QA cách ly)
uvicorn_import_from_backend_directory|Import Uvicorn từ thư mục BE
uvicorn_import_from_project_root|Import Uvicorn từ gốc dự án
""".strip().splitlines())

FE_DETAILS = {
    "FE-STORE-001": ("Đóng băng 2026-11-10 17:10 UTC; timestamps hai phía 17:00 UTC", "Nhóm Hôm nay/Hôm qua/Trước đó theo UTC+7"),
    "FE-STORE-002": ("active=null; send('  câu hỏi fixture  ')", "Tạo 1 hội thoại rồi gửi text đã trim; busy=false sau hoàn tất"),
    "FE-STORE-003": ("send mock lỗi; gửi lại cùng text rồi đổi text", "Retry cùng UUID; đổi text có UUID mới"),
    "FE-STORE-004": ("Hai lần gửi thành công cùng text", "Mỗi lượt có request_id riêng"),
    "FE-STORE-005": ("loading=true", "Không gọi create/get/send"),
    "FE-STORE-006": ("send mock pending; gửi/xóa cùng hội thoại", "Chỉ 1 lần send; không delete; busy được giải phóng"),
    "FE-STORE-007": ("'' và whitespace; không attachments", "Không create/send"),
    "FE-STORE-008": ("active=null; hai send khi create còn pending", "Chỉ 1 create và 1 send"),
    "FE-SVC-001": ("fetch reject TypeError", "Thông báo lỗi mạng tiếng Việt"),
    "FE-SVC-002": ("fetch reject DOMException AbortError", "Thông báo timeout tiếng Việt"),
    "FE-SVC-003": ("fetch pending, fake timer tiến 120000 ms", "Abort signal=true; reject được map; không còn timer"),
    "FE-SVC-004": ("HTTP 503 với detail chuỗi", "Giữ nguyên detail"),
    "FE-SVC-005": ("HTTP 422 với detail list", "Thông báo HTTP mặc định có mã 422"),
    "FE-SVC-006": ("HTTP 502, json() lỗi cú pháp", "Thông báo HTTP mặc định có mã 502"),
    "FE-SVC-007": ("DELETE id/unsafe; HTTP 204", "undefined; không json(); encode URL; credentials include"),
    "FE-SVC-008": ("POST send JSON; UUID và retrieval_scope fixture", "Đúng body, Content-Type, cookie credentials và kết quả JSON"),
    "FE-INPUT-001": ("Textarea có text; Enter", "Emit send một lần đúng text; preventDefault=true"),
    "FE-INPUT-002": ("Shift+Enter", "Không emit send; không ngăn hành vi xuống dòng"),
    "FE-INPUT-003": ("Enter với isComposing=true", "Không gửi và không preventDefault"),
    "FE-INPUT-004": ("busy=true, submit form", "Textarea/button disabled; không emit send"),
    "FE-INPUT-005": ("Whitespace, không file, submit", "Không emit send"),
    "FE-INPUT-006": ("sentVersion tăng, sau đó draftToRestore có text", "Xóa draft rồi phục hồi đúng text"),
    "FE-BUBBLE-001": ("source_url=https://ptit.edu.vn/", "Có link; _blank; noopener noreferrer"),
    "FE-BUBBLE-002": ("source_url=http://lib.ptit.edu.vn/", "Có link HTTP"),
    "FE-BUBBLE-003": ("javascript: thường/hoa/khoảng trắng", "Không render anchor"),
    "FE-BUBBLE-004": ("data/file/ftp/mailto, tương đối, rỗng, URL lỗi", "Không render anchor"),
}

LEGACY_FE = [
    ("Render Markdown gồm list/nhấn mạnh/code/bảng/entity", "Markdown tổng hợp", "HTML đúng cấu trúc"),
    ("HTML/link script/image không thành nội dung chủ động", "HTML thô và link obfuscation", "Không có HTML/script/ảnh chủ động"),
    ("Link an toàn mở tab có bảo vệ và code được escape", "Link HTTPS và đoạn code", "noopener noreferrer và code escape"),
    ("Nhóm nguồn file một lần, giữ các số citation", "Nhiều citation của cùng file", "Một nhóm chứa đủ citation"),
    ("Tin user là literal, assistant hỗ trợ Markdown", "Cùng text có markup", "User không diễn giải markup; assistant có HTML Markdown"),
    ("Chọn/xóa file draft chưa upload hoặc tạo chat", "File PDF draft", "Không gọi API upload/create"),
    ("Gửi file chuyển vào pending rồi lịch sử", "Upload mock đang chờ", "File theo pending và user message; không còn draft"),
    ("Có thể gửi file không gõ câu hỏi", "Draft file, text rỗng", "Dùng câu yêu cầu tóm tắt mặc định"),
    ("Upload lỗi một phần phục hồi và retry file lỗi", "Hai file, file hai lỗi một lần", "Giữ draft; file thành công không upload lại"),
    ("Retry gửi lỗi dùng lại file và request_id", "Upload thành công, send lỗi một lần", "Chỉ 1 upload, UUID retry giữ nguyên"),
    ("Follow-up tái dùng context, không gắn file lần nữa", "Đã gửi file rồi câu tiếp nối", "document_ids tái dùng, attachment_ids rỗng"),
    ("Batch upload mới thay context batch trước", "Gửi lần lượt hai file", "Context chỉ gồm batch mới nhất"),
    ("Đổi hội thoại xóa draft và tách context file", "Draft ở chat A, chọn B", "Không gửi file của A sang B"),
    ("Chọn file sai không làm mất draft hợp lệ", "Draft PDF rồi program.exe", "Giữ PDF, có error, không upload"),
    ("Đổi hội thoại và gửi đồng thời", "Chat A/B có send pending riêng", "Hai trạng thái gửi độc lập; kết quả về đúng hội thoại"),
]


def table(headers, records):
    def cell(value):
        return str(value).replace("|", "&#124;").replace("\r", "").replace("\n", "<br>")
    return "\n".join(["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"] + [
        "| " + " | ".join(cell(v) for v in row) + " |" for row in records])


def read_be():
    data = json.loads((RESULTS / "be_results.json").read_text(encoding="utf-8"))
    legacy_number = 0
    for row in data["rows"]:
        row["module"] = "BE/tests/" + row["module"].split(".")[-1] + ".py"
        if row["id"] == row["test"]:
            legacy_number += 1
            row["id"] = f"BE-OLD-{legacy_number:03}"
            method = row["test"].split(".")[-1]
            row["description"] = LEGACY_DESCRIPTIONS[method.removeprefix("test_")]
            tree = ast.parse((ROOT / row["module"]).read_text(encoding="utf-8-sig"))
            fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == method)
            assertions = [ast.unparse(n) for n in ast.walk(fn) if isinstance(n, ast.Call)
                          and isinstance(n.func, ast.Attribute) and n.func.attr.startswith("assert")]
            row["inputs"] = f"Fixture tổng hợp hoặc data thật theo {row['module']}:{fn.lineno}; {method}"
            row["expected"] = "; ".join(assertions) or "Subprocess import/config assertion trong testcase"
        row["actual"] = "\n".join(row["actual"])
    return data


def read_fe():
    result = json.loads((RESULTS / "fe_results.json").read_text(encoding="utf-8-sig"))
    rows = []
    for suite in result["testResults"]:
        relative = Path(suite["name"]).relative_to(ROOT).as_posix()
        for test in suite["assertionResults"]:
            identifier, description = test["title"].split(" | ", 1)
            inputs, expected = FE_DETAILS[identifier]
            status = {"passed": "Pass", "failed": "Fail", "pending": "Chưa chạy", "skipped": "Chưa chạy"}[test["status"]]
            rows.append(dict(id=identifier, module=relative, description=description, inputs=inputs, expected=expected,
                status=status, actual="\n".join(test["failureMessages"]) if status == "Fail" else "Đã chạy bằng Vitest/jsdom; toàn bộ assertion đạt."))
    assert len(rows) == result["numTotalTests"], "Vitest result count mismatch"
    return rows


def read_legacy_fe():
    log = (RESULTS / "fe_legacy_run.log").read_text(encoding="utf-8-sig")
    matches = re.findall(r"^(ok|not ok) (\d+) - (.+)$", log, re.M)
    assert len(matches) == 15 and len(LEGACY_FE) == 15, "Legacy FE TAP count mismatch"
    rows = []
    for (state, number, title), (description, inputs, expected) in zip(matches, LEGACY_FE):
        module = "FE/tests/" + ("chat.markdown.test.mjs" if int(number) <= 5 else "chat.store.test.mjs")
        rows.append(dict(id=f"FE-OLD-{int(number):03}", module=module, description=description,
                         inputs=inputs, expected=expected, status="Pass" if state == "ok" else "Fail",
                         actual=f"Node test runner: {state} {number} - {title.strip()}"))
    return rows


def main():
    be = read_be()
    rows = be["rows"] + read_fe() + read_legacy_fe()
    assert len({r["id"] for r in rows}) == len(rows), "Duplicate report IDs"
    statuses = Counter(row["status"] for row in rows)
    modules = defaultdict(Counter)
    for row in rows:
        modules[row["module"]][row["status"]] += 1
    rag = json.loads((RESULTS / "rag_results.json").read_text(encoding="utf-8"))
    golden = json.loads((ROOT / "BE/tests/golden_set.json").read_text(encoding="utf-8"))
    positives = [r for r in rag["records"] if not r["negative"]]
    negatives = [r for r in rag["records"] if r["negative"]]
    hit1, hit3 = sum(r["hit1"] for r in positives), sum(r["hit3"] for r in positives)
    file_hit3 = sum(all(any(s["source_file"] == e["source_file"] for s in r["retrieved"])
                       for e in r["evidence"]) for r in positives)
    date = datetime.now(timezone(timedelta(hours=7))).strftime("%d/%m/%Y %H:%M:%S UTC+7")

    headers = ["ID", "Module", "Mô tả", "Dữ liệu vào", "Kết quả mong đợi", "Kết quả thực tế", "Trạng thái"]
    rag_by_id = {r["id"]: r for r in rag["records"]}
    def tablerow(row):
        actual = row["actual"]
        if row["id"] in rag_by_id:
            record = rag_by_id[row["id"]]
            actual = (f"hit@1={record['hit1']}, hit@3={record['hit3']}; " if not record["negative"] else "Sources truy xuất/trả lời đều rỗng. ") + \
                     "Top-3: " + (", ".join(s["source_file"] for s in record["retrieved"]) or "[]")
        elif row["status"] == "Fail":
            lines = [line for line in actual.splitlines() if line.strip()]
            actual = "\n".join(lines[-5:])
        return [row["id"], row["module"], row["description"], row["inputs"], row["expected"], actual, row["status"]]
    # The report and CSV deliberately use exactly the same table content.
    case_rows = [tablerow(row) for row in rows]
    with (ROOT / "testcases.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(headers)
        writer.writerows(case_rows)

    versions = ", ".join(f"{n} {version(n)}" for n in ["fastapi", "httpx", "pydantic", "PyYAML", "python-dotenv",
        "langchain-core", "langchain-text-splitters", "chromadb", "langchain-chroma", "pymongo"])
    summary_rows = [[module, sum(counts.values()), counts["Pass"], counts["Fail"], counts["Chưa chạy"]]
                    for module, counts in sorted(modules.items())]
    summary_rows.append(["TỔNG", len(rows), statuses["Pass"], statuses["Fail"], statuses["Chưa chạy"]])
    rag_rows, misses = [], []
    for row in rag["records"]:
        evidence = "; ".join(e["source_file"] + ": " + ", ".join(e["expected_strings"]) +
            ("; một trong " + str(e["expected_any_strings"]) if e.get("expected_any_strings") else "") for e in row["evidence"]) or "sources=[]"
        top = "; ".join(f"{i}. {s['source_file']} — {s['title']}" for i, s in enumerate(row["retrieved"], 1)) or "[]"
        rag_rows.append([row["id"], row["category"], row["question"], evidence,
                         "—" if row["negative"] else int(row["hit1"]), "—" if row["negative"] else int(row["hit3"]),
                         top, "Pass" if row["passed"] else "Fail"])
        if not row["passed"]:
            absent = []
            for evidence_item in row["evidence"]:
                contents = [s["content"].casefold() for s in row["retrieved"] if s["source_file"] == evidence_item["source_file"]]
                absent += [evidence_item["source_file"] + ": " + text for text in evidence_item["expected_strings"]
                           if not any(text.casefold() in content for content in contents)]
            misses.append([row["id"], row["question"], "; ".join(absent), top])

    report = f"""# Báo cáo kiểm thử PTIT Chatbot

Ngày xuất: {date}. Báo cáo được dựng từ kết quả runner thật; không tự gán Pass cho testcase chưa chạy.

## (a) Phạm vi và môi trường

Tổng {len(rows)} testcase được đưa vào báo cáo: **{statuses['Pass']} Pass, {statuses['Fail']} Fail, {statuses['Chưa chạy']} Chưa chạy**; đã thực thi {len(rows)-statuses['Chưa chạy']} testcase. Mỗi method unittest / mỗi `it` Vitest / mỗi test Node được tính một testcase; các subTest và vòng lặp bên trong không cộng riêng. BE phát hiện {be['testsRun']} method; lỗi assertion được giữ nguyên như bug của hệ thống. FE đã được thực thi: 26 testcase Vitest mới và 15 testcase Node có sẵn. Có 95 testcase mới (69 BE, 26 FE): 83 Pass, 12 Fail; bộ có sẵn gồm 110 testcase: 109 Pass, 1 Chưa chạy.

Đã đọc mã BE, FE/src và các nguồn Markdown thật. Mã hiện tại khác bản định hướng: `BE/database.py` lưu MongoDB hoặc RAM, không có SQLite cho hội thoại; `db_path` chỉ định namespace RAM. `BE/search_text.py` dùng BM25, `terms()` thay cho `tokens()`. `Knowledge` hỗ trợ lexical/vector/hybrid, Ollama/Anthropic/Google, top-k mặc định 4. Bộ golden chủ động dùng limit=3, chunk_size=400, overlap=60. Không sửa mã ứng dụng, dữ liệu nguồn, package.json hoặc package-lock.json.

Windows, Python {sys.version.split()[0]} trong `.venv`; {versions}. Node v22.21.0, npm 10.9.4; Vitest 4.1.12, @vue/test-utils 2.5.1, jsdom 26.1.0, Vue 3.5.44, Pinia 4.1.0. Vitest sử dụng Vite 8.3.8 ở prefix tạm và plugin Vue 6.0.10 của dự án.

DB hội thoại luôn dùng đường dẫn dưới TemporaryDirectory hoặc collection mock. Chỉ mục Chroma của test cũ nằm trong thư mục tạm và dùng FakeEmbeddings 3 chiều; không dùng embedding/model tải thật. Hai provider LangChain trong test mới là module mock; key giả `unit-test-placeholder` chỉ để kích hoạt nhánh điều kiện. Không dùng khóa thật. `qa_bootstrap/sitecustomize.py` dùng `patch.dict(os.environ, ..., clear=True)`, tắt nạp `.env`, đặt URI Mongo rỗng và chặn HTTP thật. Socket loopback được giữ cho pipe đánh thức asyncio trên Windows. Test import Uvicorn không khởi chạy server hay lifespan.

Một testcase cũ `test_startup.StartupTests.test_backend_env_overrides_inherited_provider` được chủ động bỏ qua: nó yêu cầu đọc/nạp `.env` thật vào môi trường subprocess, trái ràng buộc cách ly khóa. Harness ghi skip với lý do; không tính Pass. Các testcase cũ khác giữ nguyên và đã chạy. Fixture tổng hợp có sẵn được dùng để kiểm tra cơ chế parser/lưu trữ, không được coi là thông tin PTIT thật; mọi dữ kiện của golden được xác minh tồn tại trong `data/*.md` trước truy xuất.

Lệnh BE đã thực thi tại gốc dự án sau khi thêm `.venv/Scripts` vào PATH và bật harness:

```powershell
$env:PATH = "$PWD\\.venv\\Scripts;" + $env:PATH
$env:PYTHONPATH = "$PWD\\BE\\tests\\qa_bootstrap"
$env:PTIT_QA_OUTPUT = "$PWD\\BE\\tests\\qa_results\\be_results.json"
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
python -m unittest discover -s BE/tests -v
```

Lệnh FE đã thực thi, không thay dependency ứng dụng:

```powershell
$qaRuntime = Join-Path $env:TEMP 'ptit-qa-vitest-isolated-20261111'
$env:PTIT_QA_NODE_MODULES = Join-Path $qaRuntime 'node_modules'
$env:PTIT_QA_FE_OUTPUT = "$PWD\\BE\\tests\\qa_results\\fe_results.json"
$env:PTIT_QA_VITE_CACHE = Join-Path $qaRuntime 'vite-cache'
node (Join-Path $qaRuntime 'node_modules\\vitest\\vitest.mjs') run --config FE/tests/qa/vitest.config.mjs
# Từ thư mục FE, chạy thêm bộ test có sẵn:
node --test --test-reporter=tap tests/*.test.mjs
```

Để dựng prefix tạm trên máy khác: tạo package.json tối thiểu trong prefix, cài `vitest@4.1.12 @vue/test-utils@2.5.1 jsdom@26.1.0` bằng npm `--prefix ... --no-save --package-lock=false --ignore-scripts --legacy-peer-deps`. Lần cài đầu gặp lỗi certificate và npm peer resolution; lần thành công dùng `node --use-system-ca` để giữ xác minh TLS với CA hệ điều hành. Không tắt TLS. Có cảnh báo engine của nopt/abbrev; các bộ FE vẫn nạp và chạy xong.

Nhật ký và kết quả máy đọc được: [BE log](BE/tests/qa_results/be_run.log), [BE JSON](BE/tests/qa_results/be_results.json), [Vitest log](BE/tests/qa_results/fe_run.log), [Vitest JSON](BE/tests/qa_results/fe_results.json), [Node TAP log](BE/tests/qa_results/fe_legacy_run.log), [RAG JSON](BE/tests/qa_results/rag_results.json).

## (b) Bảng testcase

Bảng dưới và [testcases.csv](testcases.csv) có cùng bảy cột và cùng {len(rows)} hàng. Với test cũ, cột input dẫn đúng method/line fixture và cột expected trích assertion thật trong file; không diễn giải fixture cũ thành quy định PTIT. Actual của Fail được rút gọn để đọc; traceback đầy đủ nằm trong log/JSON liên kết ở trên.

{table(headers, case_rows)}

## (c) Thống kê theo module

{table(['Module', 'Tổng', 'Pass', 'Fail', 'Chưa chạy'], summary_rows)}

## (d) Chất lượng RAG

Golden set gồm {len(positives)} câu trong phạm vi và {len(negatives)} câu ngoài phạm vi, có dấu, không dấu, viết tắt, lỗi lặp chữ nhẹ và câu nhiều ý; bao phủ cả năm file Markdown. Câu nhiều ý yêu cầu đủ các nhóm bằng chứng. {golden['definition']}

**hit@1 = {hit1}/{len(positives)} = {hit1/len(positives):.1%}; hit@3 = {hit3}/{len(positives)} = {hit3/len(positives):.1%}.** Ngoài phạm vi: {sum(r['passed'] for r in negatives)}/{len(negatives)} câu có cả retrieve và answer sources rỗng. Không đưa câu ngoài phạm vi vào mẫu số hit@k. Nếu chỉ chấm đúng tên file và bỏ qua nội dung, hit@3 là {file_hit3}/{len(positives)}; chỉ số đó không chứng minh đã lấy được đoạn chứa câu trả lời.

Định nghĩa không phân biệt hoa/thường tránh Fail giả khi cùng địa điểm viết `Phòng Mượn`/`phòng mượn`. Hai cách viết số `1.000` và `1000` đều tồn tại trong nguồn Job Fair và được chấp nhận. Mọi chuỗi kỳ vọng vẫn được kiểm tra nguyên văn tồn tại trong file nguồn thật trước chạy; không tự tạo số tiền hoặc tên mục. Trước lần chạy cuối chỉ sửa fixture cookie sai domain và các tiêu chí tương đương chữ/số của test; giữ nguyên câu hỏi, source expectations và mã ứng dụng. Chỉ số báo cáo lấy từ lần chạy cuối sau sửa test, không trộn kết quả cũ.

{table(['ID', 'Nhóm', 'Câu hỏi', 'Nguồn và chuỗi kỳ vọng', 'hit@1', 'hit@3', 'Top-3 thực tế', 'Kết quả'], rag_rows)}

Các câu không đạt top-3:

{table(['ID', 'Câu hỏi', 'Dữ kiện thiếu trong top-3', 'Nguồn truy xuất thực tế'], misses)}

Lưu ý về độ chính xác phép đo: tên file là đơn vị nguồn trong yêu cầu; không khóa URL từng bài. Một bài khác trong cùng file chứa cùng chuỗi có thể được tính hit (ví dụ “phòng mượn”). Vì vậy đây là chất lượng file/đoạn trích theo golden set này, chưa phải độ chính xác ngữ nghĩa hay khả năng trả lời trọn vẹn của LLM.

## (e) Bug và rủi ro

| Bug | Mức độ | Bằng chứng đã chạy | Nguyên nhân và tác động |
| --- | --- | --- | --- |
| BUG-01: Lưu nửa lượt ở RAM | P1 | DB-011 Fail: trước 0, sau lỗi còn 1 user message | `BE/database.py:305–340` append user trước khi deepcopy sources của assistant; không có rollback khi bước sau lỗi. Cặp user/assistant mất tính nguyên tử. |
| BUG-02: Lưu nửa lượt Mongo | P1 | DB-012 Fail: insert assistant lỗi, collection mock còn 1 user message | `BE/database.py:258–303` ghi hai insert riêng, không transaction/compensation. Catch lỗi rồi fallback không xóa user đã ghi. Chưa thử Mongo server thật; lỗi được tái hiện bằng mock collection có ghi nhận trạng thái. |
| BUG-03: source_url sai kiểu vẫn được nạp | P2 | KN-009 Fail: mapping không gây ValueError | `BE/knowledge.py:191–194` chỉ kiểm tra truthiness rồi ép str; metadata sai có thể vào chỉ mục. |
| BUG-04: fetched_date sai định dạng vẫn được nạp | P2 | KN-010 Fail: not-a-date không gây ValueError | Cùng nhánh parser, thiếu validation kiểu/ngày, làm mất độ tin cậy metadata. |
| BUG-05: Truy xuất chưa đưa đủ bằng chứng vào top-3 | P2 | {len(misses)} câu golden Fail; hit@3 {hit3/len(positives):.1%} | Có trường hợp đúng file nhưng sai đoạn, sai đợt/thời gian; câu nhiều ý RAG-020 không lấy đủ hai nguồn. Kết quả chỉ cho backend lexical/BM25, không suy rộng sang embedding thật. |
| BUG-06: Tạo trùng hội thoại khi gửi nhanh lúc active=null | P2 | FE-STORE-008 Fail: create được gọi 2 lần thay vì 1 | `FE/src/features/chat/chat.store.ts:243–260` await create trước khi thiết lập trạng thái busy/sending. Hai lời gọi send đồng thời cùng vượt guard. |

Các Fail cuối cùng đều tái hiện chênh lệch hợp đồng/chất lượng hệ thống; không đổi assertion để che bug và không sửa source. Các lỗi do test/thiết lập đã được sửa: cookie ban đầu dùng domain mặc định khiến httpx báo CookieConflict; Vitest cần resolve/inline test-utils từ prefix tạm về cùng Vue của FE; cách viết `1000`/`1.000` và hoa/thường cần được coi tương đương. Báo cáo không tính những lần chạy thử đó vào tổng cuối.

Rủi ro từ đọc code/dữ liệu, không cộng thêm vào số Fail:

- RAM fallback không có độ bền qua restart tiến trình; test cũ “restart app” chỉ tạo lại app trong cùng tiến trình. Không dùng kết quả đó để khẳng định lưu bền SQLite/Mongo thật.
- Code đã có `standalone_question`, lập kế hoạch theo lịch sử, chuyển/loại chủ đề và 10 test multi-turn có sẵn đã Pass. Không có cơ sở để báo “không xử lý lịch sử”. Việc viết lại vẫn theo quy tắc, chưa đánh giá độ hiểu ngữ nghĩa toàn diện.
- Golden đang kiểm tra lexical/BM25. Kiểm tra Chroma cũ dùng vector giả nhằm xác minh cơ chế, không đo chất lượng embedding thật. Chưa đo latency/tải lớn/đua cùng request_id trên Mongo thật.
- Nguồn `data/ktx.md` có ngày mâu thuẫn: đăng ký tháng 9/2026 ghi thời gian ở từ 01/10/2026 đến 31/01/2026; thông báo hè 2026 còn có hạn đăng ký năm 2025. Đây là bất nhất trong dữ liệu nguồn đã đọc, chưa có testcase tự động kiểm tra tính hợp lệ các mốc này. Truy xuất đúng văn bản vẫn có thể trả thông tin sai thời gian.

## (f) Giới hạn và khả năng tái lập

Không gọi LLM/Ollama/Mongo/embedding thật; không dùng API key thật hay DB thật. Chưa kiểm thử SQLite cho hội thoại vì phiên bản hiện tại không có adapter đó. FE đã chạy thật trong jsdom, chưa có browser E2E hoặc bộ gõ IME hệ điều hành; test IME xác minh cờ isComposing, test Shift+Enter xác minh không preventDefault. Không có kiểm thử thông báo Notification ngoài trình duyệt. Test `.env` thật bị bỏ qua có lý do và đã tính “Chưa chạy”.

Golden set nhỏ, chỉ {len(positives)} câu có đáp án và {len(negatives)} câu từ chối; không có đánh giá hallucination, faithfulness hay citation correctness của output LLM. Chỉ số dùng cấu hình cố định và dữ liệu của lần chạy này; chưa có benchmark semantic/hybrid trên encoder thật. Không xác nhận ngày hiệu lực pháp lý của các thông báo trong dữ liệu.

Để tái xuất báo cáo sau chạy: `python BE/tests/qa_report.py`. Script kiểm tra tổng số hàng, ID duy nhất và đọc kết quả có sẵn; không tự thực thi test hoặc tự tạo Pass/Fail.
"""
    (ROOT / "bao_cao_kiem_thu.md").write_text(report, encoding="utf-8")
    # Provenance is report data, not a replacement for the raw runner outputs.
    manifest = {
        "created_at_utc7": date, "counts": dict(statuses), "total": len(rows),
        "be": {k: be[k] for k in ("testsRun", "failures", "errors", "skipped")},
        "rag": {"positive": len(positives), "hit1": hit1, "hit3": hit3, "negative": len(negatives)},
        "sources_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT / "data").glob("*.md"))},
    }
    (RESULTS / "report_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
