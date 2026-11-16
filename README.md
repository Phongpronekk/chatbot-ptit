# Chatbot PTIT

Demo tra cứu học vụ dành cho sinh viên CNTT cơ sở phía Bắc. Kho tài liệu đặt trong **knowledge_base/** và do máy chủ Python đọc khi khởi động.

## Chạy demo

Cần Python 3.10 trở lên. Tại thư mục dự án, chạy:

~~~powershell
python backend/server.py
~~~

Mở [http://127.0.0.1:8000](http://127.0.0.1:8000). Nếu cổng 8000 đang được dùng, chạy lệnh với **--port 8001** và mở địa chỉ máy chủ in ra. Dùng **Ctrl+C** để dừng. Khi kho Markdown thay đổi, khởi động lại máy chủ để lập chỉ mục mới.

## Bật Gemini và đổi model

Trong PowerShell tại thư mục dự án:

~~~powershell
Copy-Item .env.example .env
notepad .env
~~~

Điền key sau **GEMINI_API_KEY=** trong file **.env**. Giữ **GEMINI_MODEL=gemini-3.5-flash-lite** hoặc đổi thành ID model Gemini sinh văn bản mà dự án Google của bạn có quyền dùng, ví dụ **gemini-3.5-flash**. Lưu file và khởi động lại máy chủ. Biến môi trường **GEMINI_API_KEY** và **GEMINI_MODEL** được ưu tiên nếu đã đặt.

API key chỉ được backend đọc, và **.env** nằm trong **.gitignore**. Khi bật Gemini, backend gửi câu hỏi hiện tại và các trích đoạn liên quan đến Gemini API để viết câu trả lời có số nguồn. Giao diện hiển thị link gốc từ kho Markdown. Nếu thiếu key hoặc API gặp lỗi, demo vẫn hiển thị các trích đoạn tìm được.

## Cấu trúc

~~~text
BTL_HTTM/
├── backend/
│   ├── server.py       # HTTP, API chat và phục vụ giao diện
│   ├── retrieval.py    # Đọc Markdown, chia đoạn và xếp hạng từ khóa
│   └── gemini.py       # Tổng hợp câu trả lời từ các trích đoạn
├── frontend/
│   ├── index.html
│   ├── styles.css
│   └── app.js          # Chat, lịch sử trong phiên và nguồn trích dẫn
├── knowledge_base/    # Tài liệu PTIT và metadata nguồn
├── RAGworkflow.webp
└── README.md
~~~

Backend và frontend có thư mục riêng, dùng chung một tiến trình và địa chỉ trong giai đoạn demo. Giao diện gửi **POST /api/chat** với JSON **{"question":"..."}**. API trả các đoạn liên quan và URL gốc, cùng câu trả lời nếu Gemini hoạt động. **GET /api/status** trả số tài liệu và model đã cấu hình.

## Câu hỏi thử

- CNTT khóa 2025 có bao nhiêu tín chỉ?
- Mất thẻ sinh viên thì làm lại như thế nào?
- Học phí học lại lớp riêng kỳ I môn INT1313 là bao nhiêu?

Chế độ truy xuất từ khóa có chuẩn hóa dấu tiếng Việt và trích đoạn từ tài liệu. Chế độ này chạy cục bộ và có thể trả trích đoạn khi chưa có API key Gemini. Các câu hỏi về thông báo theo đợt nên kèm học kỳ và năm học.


## Thử truy xuất theo vector

Tại thư mục dự án, chạy:

~~~powershell
python -m pip install -r backend/requirements-vector.txt
python -X utf8 backend/build_vector_index.py --build
python -X utf8 backend/build_vector_index.py --query "Em làm rơi thẻ, xin thẻ mới ở đâu?"
~~~

Lần đầu cần Internet để tải model embedding. Script lưu chỉ mục Chroma vào **.chroma/** và in ba kết quả gần nhất kèm nguồn. Chạy lại **--build** sau khi cập nhật kho Markdown. Khởi động lại server sau khi lập chỉ mục để bật truy xuất kết hợp. API ưu tiên tối đa hai đoạn theo từ khóa và bổ sung đoạn theo vector, tối đa ba mục. **GET /api/status** trả **retrieval: hybrid** khi kho vector đang được dùng. Dùng **--keyword-only** hoặc chạy khi chưa có kho Chroma để tra cứu từ khóa.

Khi Gemini được bật, giao diện hiển thị câu trả lời theo từng phần. Client API có thể yêu cầu luồng NDJSON bằng header **Accept: application/x-ndjson**. Mặc định **POST /api/chat** trả JSON.
