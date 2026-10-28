# Tìm kiếm tiếng Việt và thuật ngữ tương đương

Đợt kiểm tra ngày 29/10/2026 trên kho 1.459 chunk. Không sửa dữ liệu hoặc embedding đã lưu.

## Nguyên nhân và mức tái hiện

Trước thay đổi, backend đang chạy vẫn trả 4 nguồn cho cả `bao hiem  y te` và `bhyt`; chưa tái hiện được trường hợp không có kết quả mà người dùng báo. Tuy nhiên, E5 tạo vector khác nhau cho tên đầy đủ, không dấu và viết tắt. Điểm cao nhất của `bao hiem  y te` khoảng 0,836, còn `bảo hiểm y tế` khoảng 0,896. Truy xuất chỉ dùng vector và ngưỡng cố định dễ thay đổi thứ hạng hoặc mất kết quả khi đổi cách viết, dữ liệu hoặc ngưỡng. Không quy kết khác biệt này cho Gemini vì bước truy xuất không gọi Gemini.

## Cơ chế đã bổ sung

1. Chuẩn hóa Unicode NFC và khoảng trắng, giữ nguyên câu hỏi gốc cho LLM.
2. Ánh xạ thuật ngữ đã xác định rõ theo hai chiều tên đầy đủ/viết tắt trong `BE/search_text.py`, như BHYT, KTX, CLB, TTTN, ĐHCQ, CNTT, ATTT. Không tự mở rộng các từ viết tắt mơ hồ như TV. Không thay một phần bên trong mã hoặc từ dài hơn.
3. BM25 trên văn bản không dấu, áp dụng cho cả truy vấn và tài liệu. Cụm không nằm trong danh sách thuật ngữ vẫn có thể khớp không dấu. Đây không phải bộ sửa chính tả hay phục hồi dấu tổng quát.
4. Truy xuất tập ứng viên vector và từ khóa, hợp nhất bằng Reciprocal Rank Fusion. Không cộng trực tiếp điểm BM25 với cosine. Chỉ trả tối đa Top-K.
5. Khớp từ khóa ngắn cần đủ từ và đúng cụm sau chuẩn hóa, tránh gom từ rải rác ở các câu không liên quan. Nhánh vector vẫn giữ được paraphrase đủ mạnh. Các cổng lọc là heuristic, cần đánh giá tiếp trên tập độc lập; không bảo đảm đúng mọi truy vấn hoặc xử lý đầy đủ các phủ định, năm học và mâu thuẫn.
6. Khi vector lỗi/tắt, BM25 dự phòng dùng cùng cơ chế chuẩn hóa. Chỉ mục từ khóa được cache trong RAM theo collection đang dùng và làm nóng lúc khởi động BE.

`RETRIEVAL_HYBRID=true` bật cơ chế mới. `RAG_MIN_SCORE` tiếp tục là ngưỡng cosine; nguồn có khớp từ khóa mạnh có thể được chọn dù vector dưới ngưỡng. `RAG_SEMANTIC_ONLY_MARGIN=0.08` tăng yêu cầu cho ứng viên chỉ được hỗ trợ bởi ngữ nghĩa. Không hạ ngưỡng 0,80 đang dùng.

API trả `score_type` là `cosine_similarity` hoặc `bm25`, cùng `semantic_score`, `lexical_score`, `fusion_score`. Chúng không phải xác suất đúng. `/api/rag/search` có `query_processing`, `hybrid_search`; trạng thái API có `search_strategy` để xác nhận mã mới đã được nạp.

## Kết quả kiểm chứng

- 36/36 kiểm thử BE đạt; FE type-check/build thành công.
- `bao hiem  y te`, `bảo hiểm y tế`, `bhyt`: cùng nguồn đầu về gia hạn thẻ BHYT năm học 2026–2027.
- `ky tuc xa` và `ktx`: cùng nguồn đầu về đăng ký nội trú Hà Đông tháng 1/2026.
- Cả `thuc tap tot nghiep` và `tttn` có kết quả; vẫn cần điều kiện khóa/ngành để chọn thông báo cụ thể.
- Các câu thử pizza, quasar và bảo hiểm thất nghiệp trả rỗng; không suy rộng cho mọi câu ngoài phạm vi.
- Thời gian truy xuất trung bình các lượt sau khởi tạo khoảng 54 ms trong 10 mẫu; lần đầu xây cache RAM khoảng 1,5 giây trên phép đo trực tiếp RagStore. BE làm nóng cache khi khởi động. Không gồm thời gian sinh câu trả lời hoặc mạng/hiển thị FE.
- Test API dùng kho vector thật và SQLite tạm, không gọi LLM, không lưu hội thoại; SHA256 năm file dữ liệu không đổi.

Chi tiết: `docs/search_normalization_evaluation.json`, `docs/search_api_validation.json`; log test/build trong `logs/search-normalization-*.log`. Đây là kiểm tra phát triển trên tập nhỏ, không phải benchmark độ chính xác độc lập.

Khởi động lại BE đang chạy để nạp thay đổi. Không cần ingest hoặc tạo lại embedding.
