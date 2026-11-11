# Luồng tải tệp và xử lý ảnh trong chatbot PTIT

Chatbot trả lời theo tệp bằng cách trích văn bản, tìm đoạn liên quan và đưa các đoạn đó vào ngữ cảnh của mô hình. Tính năng hiện hỗ trợ PDF có lớp chữ, Word `.docx`, Excel `.xlsx` và `.xls`.

## Từ lúc chọn tệp đến lúc gửi câu hỏi

1. Người dùng nhấn **+** để chọn tệp. Giao diện giữ tệp ở trạng thái **Chờ gửi**. Khi người dùng nhấn **Gửi**, giao diện mới tải tệp lên.
2. Giao diện tạo hoặc dùng lại cuộc trò chuyện rồi gọi `POST /api/conversations/{id}/documents` cho từng tệp. Mỗi yêu cầu gửi một trường `file` bằng `multipart/form-data`.
3. Backend kiểm tra quyền truy cập cuộc trò chuyện, phần mở rộng và kích thước tệp. Giới hạn là **10 MB mỗi tệp** và **5 tệp còn hiệu lực mỗi cuộc trò chuyện**.
4. Sau khi trích xuất thành công, backend trả mã định danh, tên tệp, số ký tự, số đoạn và thời điểm hết hạn. Giao diện gửi câu hỏi cùng `document_ids` (tệp được dùng làm ngữ cảnh) và `attachment_ids` (tệp đính kèm mới của tin nhắn).

Mã liên quan nằm trong [chat.store.ts](../FE/src/features/chat/chat.store.ts), [chat.service.ts](../FE/src/features/chat/chat.service.ts) và [main.py](../BE/main.py).

## Backend đọc và chia nội dung

| Định dạng | Cách đọc | Vị trí trích dẫn |
|---|---|---|
| PDF | `pypdf` lấy chữ có sẵn trên từng trang | Số trang |
| DOCX | `python-docx` đọc đoạn văn và dòng trong bảng | Số đoạn hoặc bảng và dòng |
| XLSX | `openpyxl` đọc ô, giữ công thức dưới dạng văn bản | Tên sheet và số dòng |
| XLS | `xlrd` đọc dữ liệu ô | Tên sheet và số dòng |

Backend gom các đoạn hoặc dòng liền nhau, rồi chia nội dung thành các đoạn khoảng 1.200 ký tự, có phần chồng lấn 150 ký tự khi cần chia. Các đoạn và vị trí trích dẫn được giữ tạm trong **2 giờ**, gắn với phiên người dùng và cuộc trò chuyện. Tệp gốc không được lưu. Khi bật MongoDB, backend có thể lưu tạm metadata và các đoạn đã trích để phục hồi ngữ cảnh tệp còn hiệu lực. [attachments.py](../BE/attachments.py)

## Chatbot dùng tệp để trả lời

- Tin nhắn có tệp đính kèm mới được chuyển sang nhánh **File đã tải lên**. Với câu hỏi tiếp theo, người dùng có thể chọn nguồn trên giao diện. Chế độ tự động xét câu hỏi và các lượt liên quan để chọn kho PTIT hoặc tệp.
- Backend tìm đoạn liên quan bằng BM25 trong các tệp đã chọn của cuộc trò chuyện. Chỉ lịch sử liên quan đến những tệp đó được dùng làm ngữ cảnh cho câu hỏi tiếp nối.
- Các đoạn tìm được được đưa vào prompt dưới dạng dữ liệu tham khảo. Câu trả lời có thể dẫn tên tệp và trang, đoạn hoặc dòng tương ứng. Giao diện nhận nội dung qua luồng streaming và hiển thị nguồn khi lượt trả lời hoàn tất.

Mã liên quan nằm trong [message_routing.py](../BE/message_routing.py), [attachments.py](../BE/attachments.py), [knowledge.py](../BE/knowledge.py) và [main.py](../BE/main.py).

## Ảnh và PDF scan

**Chatbot hiện chưa nhận ảnh trực tiếp và chưa chạy OCR.** Ảnh JPG hoặc PNG nằm ngoài danh sách định dạng tải lên. Với PDF, backend chỉ đọc lớp văn bản mà `pypdf` trích được. Vì vậy:

- **PDF có cả chữ và ảnh** vẫn có thể tải lên. Chatbot dùng phần chữ trích được. Chữ, công thức hoặc sơ đồ nằm trong ảnh có thể bị thiếu.
- **PDF scan đã chạy OCR** có thể dùng được nếu kết quả có lớp chữ để trích xuất.
- **PDF scan chỉ chứa ảnh** bị báo không tìm thấy nội dung chữ. Để hỏi về nội dung đó, hãy chạy OCR rồi tải lại PDF có lớp chữ, hoặc đưa phần văn bản đã nhận dạng vào DOCX.

Ví dụ, với câu hỏi “Công thức Heron là gì?”, hãy thử chọn và sao chép dòng công thức trong PDF. Nếu dòng đó là ảnh, hãy nhận dạng hoặc chép lại công thức thành văn bản trước khi tải. Khi chatbot trả lời, kiểm tra trang trích dẫn và đối chiếu các ký hiệu toán học với bản gốc. [attachments.py](../BE/attachments.py)

