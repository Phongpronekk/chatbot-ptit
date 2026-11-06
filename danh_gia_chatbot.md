# Báo cáo đánh giá hệ thống Chatbot PTIT

Đánh giá kỹ thuật độc lập dựa trên mã nguồn và dữ liệu thực tế tại `D:\chatbot-ptit`.

---

## 1. Lỗi sai

1. **Mất ngữ cảnh đa lượt cho kho dữ liệu PTIT**
   - *Mức độ*: Nghiêm trọng.
   - *Vị trí*: `BE/main.py:374` và `BE/knowledge.py:195-203`.
   - *Bằng chứng*: `main.py` gọi `knowledge.answer(payload.message)` không truyền `history`; `knowledge.py:203` mặc định `history=None`. Hỏi tiếp *"Thế còn B1 thì sao?"* sau câu hỏi KTX, RAG không hiểu đại từ thay thế và trả về 0 nguồn (`sources=[]`).

2. **Heuristic lọc từ khóa ngắn quá khắt khe gây từ chối sai (False Rejection)**
   - *Mức độ*: Nghiêm trọng.
   - *Vị trí*: `BE/rag_store.py:246-249`, `BE/search_text.py:23, 84-88`.
   - *Bằng chứng*: `search_text.py:23` thiếu từ dừng "co". `rag_store.py:247` ép `coverage == 1.0` nếu câu ≤ 5 từ; `search_text.py:87` đòi cụm từ liên tiếp `phrase in text_terms`. Hỏi *"co clb nao"*, *"danh sach cau lac bo"* dù `clb.md` có sẵn và cosine đạt 0.84 vẫn bị loại sạch, trả về 0 kết quả.

3. **Lỗ hổng Prompt Injection qua thẻ đóng `</tai_lieu>`**
   - *Mức độ*: Trung bình.
   - *Vị trí*: `BE/knowledge.py:235, 245`.
   - *Bằng chứng*: Prompt dùng `<tai_lieu>\n{context}\n</tai_lieu>\n\nCâu hỏi: {question}` không escape chuỗi `</tai_lieu>`, cho phép nội dung file hoặc câu hỏi đóng sớm thẻ ngữ cảnh để chèn chỉ thị độc hại.

4. **Mất tài liệu tạm khi chạy đa worker hoặc restart**
   - *Mức độ*: Trung bình.
   - *Vị trí*: `BE/attachments.py:186-189`, `BE/main.py:101-102`.
   - *Bằng chứng*: `DocumentMemory` lưu file trong RAM. Chạy Uvicorn đa worker (`--workers > 1`), lượt hỏi đáp rơi vào worker khác sẽ báo lỗi `410 Gone`. Restart BE cũng xóa sạch file.

5. **Nạp cấu hình trùng lặp và không đồng bộ**
   - *Mức độ*: Nhẹ.
   - *Vị trí*: `BE/main.py:20-25`.
   - *Bằng chứng*: Gọi `load_dotenv` 2 lần liên tiếp (dòng 20, 25). Import độc lập `BE.knowledge` không tự nạp `.env`, âm thầm fallback về `lexical`.

---

## 2. Hạn chế

- **Kiến trúc**: Chưa hỗ trợ streaming (SSE/WebSocket), FE phải chờ trọn JSON; lưu file trong RAM ngăn scale ngang; thiếu cross-encoder reranker.
- **Dữ liệu**: 126/160 bài dồn ở `quy_che_chung.md`, `clb.md` và `ktx.md` chỉ 3 bài/nhóm. Toàn bộ là tin tức 2026, thiếu quy chế gốc (đào tạo tín chỉ, học phí). File đính kèm chỉ lưu URL, chưa bóc tách hay OCR.
- **Hiểu tiếng Việt**: `TERMS` (`search_text.py`) chỉ có 15 cụm từ, thiếu từ viết tắt phổ biến (`sv`, `tc`, `hp`, `dki`, `cpa/gpa`, `k21-k26`, `gvcn`). BM25 bắt buộc cụm từ liên tục làm trượt câu không dấu hoặc đảo ngữ tự nhiên.
- **Bảo mật và quyền riêng tư**: `BE/.env` lưu plain text API key. Phiên làm việc chỉ qua cookie ẩn danh `ptit_session`, không có tài khoản (SSO/OAuth2); mất cookie là mất lịch sử.
- **Khả năng mở rộng**: Ingest tách rời: chỉ mục mới yêu cầu restart backend mới nhận collection mới.
- **Trải nghiệm người dùng**: Thiếu nút Like/Dislike; thiếu gợi ý câu hỏi mẫu; chờ lâu do không có streaming.

---

## 3. Điểm tốt

- **Chuẩn hóa Unicode và từ viết tắt hai chiều**: `BE/search_text.py:8-47` chuẩn hóa NFC, fold NFD, map hai chiều (BHYT ↔ Bảo hiểm y tế, KTX ↔ Ký túc xá).
- **Hybrid Search kết hợp RRF chuẩn xác**: `BE/rag_store.py:230-266` kết hợp vector cosine và BM25 không dấu qua Reciprocal Rank Fusion `1/(60 + rank)` tránh xung đột điểm thô.
- **Toàn vẹn giao dịch và chống ghi trùng**: `BE/database.py:34, 93-118` dùng SQLite WAL, transaction `BEGIN IMMEDIATE`, kiểm tra `has_request` chống ghi đúp khi retry.
- **Kiểm soát an toàn file tải lên**: `BE/attachments.py:41-149` giới hạn file 10MB, PDF 300 trang, Excel 20.000 dòng, chặn Zip Bomb (giải nén tối đa 40MB).
- **Chống XSS ở Frontend**: `FE/src/features/chat/chat.markdown.ts:4-16` tắt HTML thô, lọc protocol URL, tự gắn `rel="noopener noreferrer"`.
- **Độ bao phủ test cao**: Đạt 64/64 test backend (`logs/collection-2026-tests.log`) và 14/14 test frontend (`FE/tests/*.test.mjs`).

---

## 4. Điểm xấu

- **Mất ngữ cảnh câu hỏi nối tiếp**: Hỏi câu tiếp (*"thế còn B1?"*) bot không hiểu đại từ, trả lời sai/rỗng, sinh viên phải gõ lại từ đầu.
- **Bị từ chối oan do bộ lọc cứng**: Câu ngắn tự nhiên (*"co clb nao"*, *"dki hoc phan the nao"*) bị từ chối, gây ức chế và tưởng nhầm trường không có dịch vụ.
- **Chờ đợi lâu do thiếu streaming**: Phải chờ 5-15 giây nhìn spinner tĩnh, dễ tưởng bot bị treo.
- **Thiếu thông tin quy chế gốc**: Dữ liệu chỉ gồm thông báo 2026, sinh viên hỏi về rèn luyện, tốt nghiệp dễ nhận thông tin chắp vá.
- **Phân mảnh lịch sử theo máy**: Không có tài khoản, đổi máy hay xóa cookie là mất sạch lịch sử tư vấn.

---

## 5. Chấm điểm thang 10

| Tiêu chí | Trọng số | Điểm | Lý do |
| :--- | :---: | :---: | :--- |
| **Độ chính xác** | 25% | 7.0 | RAG trích nguồn chuẩn, RRF tốt khi trúng từ khóa; heuristic khắt khe làm rớt nhiều câu đúng; chưa có reranker. |
| **Hiểu tiếng Việt và ngữ cảnh** | 20% | 5.5 | Xử lý tốt không dấu, viết tắt cơ bản; mất ngữ cảnh đa lượt ở kho PTIT; thiếu từ điển slang/teencode sinh viên. |
| **Độ phủ và tính cập nhật kiến thức** | 15% | 6.0 | Cập nhật 160 bài năm 2026; thiếu quy chế gốc; CLB/KTX chỉ 3 bài/nhóm; file đính kèm chưa bóc tách nội dung. |
| **Trải nghiệm người dùng** | 15% | 6.5 | Giao diện gọn, đọc file tốt; thiếu streaming (chờ lâu), không có gợi ý câu hỏi mẫu, thiếu nút Like/Dislike. |
| **Bảo mật và quyền riêng tư** | 10% | 6.5 | Cookie HttpOnly tốt, chống XSS; API key lưu dạng plain text trong `.env`, prompt chưa escape thẻ `<tai_lieu>`. |
| **Ổn định và tốc độ** | 10% | 7.5 | Truy xuất local nhanh (~30-50ms), SQLite WAL tin cậy, retry chống trùng; tốc độ sinh LLM chậm do thiếu streaming. |
| **Khả năng mở rộng và bảo trì** | 5% | 6.0 | Phân mô-đun tốt, test tự động đầy đủ; lưu file trong RAM cản trở scale đa worker; ingest cần restart server. |

**Tổng điểm: 6.5/10**

---

## 6. Hướng cải tiến

1. **Khôi phục ngữ cảnh hội thoại đa lượt**
   - *Vấn đề*: Mất ngữ cảnh ở câu hỏi tiếp nối về quy chế trường.
   - *Cách làm*: Truyền `history` vào `knowledge.answer()`; dùng LLM nhỏ viết lại câu hỏi nối tiếp trước khi đưa vào RAG.
   - *Độ khó*: Vừa | *Ưu tiên*: Cao.

2. **Nới lỏng bộ lọc heuristic và sửa Stopwords**
   - *Vấn đề*: Heuristic từ chối sai các câu hỏi ngắn tự nhiên (*"co clb nao"*).
   - *Cách làm*: Thêm "co", "nhung" vào `STOP` (`search_text.py`); giảm `supported` ở `rag_store.py:247` xuống 0.5 cho câu ≤ 5 từ; bỏ ràng buộc `phrase in text_terms` ở BM25.
   - *Độ khó*: Dễ | *Ưu tiên*: Cao.

3. **Triển khai streaming phản hồi (SSE)**
   - *Vấn đề*: Phản hồi chậm (5-15s), giao diện tĩnh gây sốt ruột.
   - *Cách làm*: Dùng `StreamingResponse` FastAPI kết hợp stream token từ LLM; FE dùng `EventSource` hiển thị chữ chạy thời gian thực.
   - *Độ khó*: Vừa | *Ưu tiên*: Cao.

4. **Bổ sung quy chế gốc và bóc tách tệp đính kèm**
   - *Vấn đề*: Thiếu quy chế đào tạo gốc, dữ liệu CLB/KTX nghèo nàn (3 bài/nhóm).
   - *Cách làm*: Nạp Sổ tay sinh viên, Quy chế đào tạo tín chỉ vào `data/`; tự động tải và trích xuất file PDF/Word đính kèm.
   - *Độ khó*: Vừa | *Ưu tiên*: Cao.

5. **Mở rộng từ điển viết tắt sinh viên PTIT**
   - *Vấn đề*: Không nhận diện được từ viết tắt học đường thông dụng.
   - *Cách làm*: Thêm vào `TERMS` (`search_text.py`): `sv`, `tc`, `hp`, `dki/dk`, `cpa/gpa`, `gvcn`, `ha dong`, `man thien`.
   - *Độ khó*: Dễ | *Ưu tiên*: Trung bình.

6. **Chuyển DocumentMemory sang bộ nhớ dùng chung**
   - *Vấn đề*: Không chạy được đa worker Uvicorn do lưu file trong RAM.
   - *Cách làm*: Lưu file tạm vào Redis hoặc SQLite tạm thời có TTL thay vì RAM tiến trình.
   - *Độ khó*: Vừa | *Ưu tiên*: Trung bình.

7. **Bổ sung tính năng đánh giá phản hồi (User Feedback)**
   - *Vấn đề*: Thiếu dữ liệu người dùng để đo lường và cải tiến RAG.
   - *Cách làm*: Thêm nút Like/Dislike dưới câu trả lời trên FE và API lưu phản hồi vào SQLite.
   - *Độ khó*: Dễ | *Ưu tiên*: Trung bình.

8. **Vá Prompt Injection và bảo vệ cấu hình**
   - *Vấn đề*: Nguy cơ injection qua thẻ `<tai_lieu>` và lộ API key trong `.env`.
   - *Cách làm*: Escape chuỗi `</tai_lieu>` trong input và file upload; chuyển API key sang biến môi trường hệ thống.
   - *Độ khó*: Dễ | *Ưu tiên*: Thấp.
