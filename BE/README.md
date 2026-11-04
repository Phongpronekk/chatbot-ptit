# PTIT Chatbot API

Chạy lệnh từ thư mục gốc `D:\chatbot-ptit`:

```powershell
python -m pip install -r BE/requirements.txt
python -m uvicorn BE.main:app --host 127.0.0.1 --port 8000 --reload
```

Hoặc, nếu terminal đang đứng trong `D:\chatbot-ptit\BE`:

```powershell
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

Trong thư mục BE cũng có thể chạy `python main.py` (không tự reload).
Không dùng `BE.main:app` khi đứng trong BE, và không dùng `app.main:app` vì dự án
hiện chưa có thư mục `BE/app`. Nếu FE báo `ECONNREFUSED`, kiểm tra terminal BE
đã có dòng `Application startup complete` và giữ terminal đó hoạt động.

Swagger: http://127.0.0.1:8000/docs. Frontend Vite chuyển tiếp `/api` tới cổng
8000 nên trình duyệt dùng cùng origin, không phải cấu hình URL trong component.
Không cần khởi chạy `rag_demo.py`.

## API

| Method | Path | Dữ liệu/kết quả |
|---|---|---|
| GET | `/api/health` | status, source_count, retrieval, llm_configured |
| GET | `/api/knowledge/sources` | Metadata từ các file Markdown thật |
| GET | `/api/conversations` | Danh sách id, title, created_at, updated_at |
| POST | `/api/conversations` | Tạo hội thoại trống, trả 201 và hội thoại |
| GET | `/api/conversations/{id}` | Hội thoại và toàn bộ messages |
| POST | `/api/conversations/{id}/messages` | Nhận message, request_id; trả hội thoại đã cập nhật |
| DELETE | `/api/conversations/{id}` | Xóa hội thoại và tin nhắn, trả 204 |

Ví dụ body gửi tin:

```json
{
  "message": "KTX B2 mức thu bao nhiêu?",
  "request_id": "9bc080ce-cdd7-4a27-8365-fd727e63ecdf"
}
```

`request_id` là UUID do client tạo cho một lượt gửi. Gửi lại cùng ID trên cùng
hội thoại trả dữ liệu đã lưu, không thêm cặp tin trùng. Khi dịch vụ trả lời lỗi,
trả 503 và không lưu nửa lượt hội thoại; FE giữ nội dung nhập để gửi lại.

Message trả về có id, role, text, created_at (ISO UTC), mode và sources.
Nguồn có URL, ngày thu thập, chủ đề, tiêu đề, nội dung gốc, ghi chú và điểm khớp.
Sai dữ liệu đầu vào: 422; hội thoại không tồn tại hoặc thuộc phiên khác: 404.

## Dữ liệu và chế độ trả lời

- Không seed lịch sử/tin nhắn. SQLite tạo tại `BE/storage/chat.sqlite3` và được
  gitignore; dữ liệu vẫn còn sau khi khởi động lại backend.
- Kho tri thức đọc trực tiếp `data/*.md`, dùng YAML safe loader. Chia theo mục
  Markdown và giữ tiêu đề cha, URL, thời điểm/phạm vi áp dụng của nguồn.
- Truy xuất hiện dùng từ khóa có chuẩn hóa dấu tiếng Việt, trọng số tần suất
  và độ dài; `retrieval=lexical`. Đây chưa phải pipeline embedding/Chroma của
  script demo. Điểm số chỉ để xếp hạng, không phải xác suất đúng.
- Không có API key: `mode=retrieval_only`, trả các trích đoạn thực để người dùng
  mở xem. Không tạo câu trả lời mẫu để giả lập LLM.
- Có API key và MODEL_NAME: dùng provider LangChain để tổng hợp trên các đoạn
  được tìm thấy. Nhánh này chưa được gọi tới dịch vụ thật trong kiểm thử.
- Snapshot có thể cũ; xem ngày, khóa/cơ sở trong source trước khi áp dụng.
- Hiện mỗi câu hỏi được tìm kiếm độc lập; chưa có cơ chế viết lại câu hỏi dựa
  trên lịch sử cho những câu tiếp nối như “còn chỗ đó thì sao?”.

## Cấu hình tùy chọn

```powershell
# Cài cả dependency provider nếu cần tổng hợp bằng LLM
python -m pip install -r requirements.txt
$env:LLM_PROVIDER = 'anthropic' # hoặc google
$env:ANTHROPIC_API_KEY = '...'
# Với Google dùng GOOGLE_API_KEY
$env:MODEL_NAME = 'ten-model-ma-tai-khoan-co-quyen-su-dung'
```

Biến môi trường khác: CHAT_DB_PATH, DATA_DIR, CORS_ORIGINS (phân cách bằng dấu
phẩy), COOKIE_SECURE=true khi triển khai HTTPS. Cấu hình được đọc từ process env;
không tự load file `.env`.

Cookie `ptit_session` HttpOnly/SameSite=Lax tách lịch sử theo trình duyệt, có hạn
30 ngày. Đây là định danh phiên cục bộ, chưa phải đăng nhập tài khoản; mất/xóa
cookie sẽ không truy cập được lịch sử cũ. Triển khai nhiều người dùng chính thức
cần đăng nhập và quản lý quyền/lưu trữ theo tài khoản. Không mở public bằng
cấu hình phát triển mặc định.

## Kiểm thử

```powershell
python -m unittest discover -s BE/tests -v
```

Test dùng DB tạm, không ghi vào DB người dùng và không gọi LLM thật.
