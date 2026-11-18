# PTIT Chat

PTIT Chat là chatbot tra cứu chương trình đào tạo, thủ tục sinh viên và thông báo học vụ cho sinh viên ngành Công nghệ thông tin tại PTIT cơ sở phía Bắc. Bạn có thể hỏi bằng tiếng Việt về kho tài liệu có sẵn hoặc về tệp tải lên.

## 1. Chạy giao diện lần đầu

Các lệnh bên dưới dùng **PowerShell trên Windows**. Cần **Python 3.10 trở lên** và một trình duyệt web. Máy chủ Python phục vụ cả giao diện lẫn phần tra cứu. Chế độ từ khóa chạy ngay với thư viện chuẩn của Python và kho tài liệu có sẵn, kể cả khi chưa cấu hình Gemini.

1. Tải hoặc clone dự án về máy. Nếu tải ZIP, hãy giải nén trước. Mở PowerShell và chuyển vào thư mục có `README.md`, `backend/` và `knowledge_base/`. Đoạn lệnh dưới đây dùng đường dẫn `D:\BTL_HTTM`.

   ~~~powershell
   Set-Location "D:\BTL_HTTM"
   python --version
   ~~~

   Nếu PowerShell báo không nhận lệnh `python`, thử `py --version`. Nếu lệnh `py` hiện Python 3.10 trở lên, bạn có thể thay `python` bằng `py` trong các lệnh khởi động và tạo môi trường ảo. Nếu cả hai lệnh đều không chạy, cài Python, thêm Python vào PATH và mở lại PowerShell.

2. Khởi động máy chủ ở chế độ tìm theo từ khóa.

   ~~~powershell
   python -X utf8 backend/server.py --keyword-only
   ~~~

   Đợi dòng `PTIT chatbot | … tai lieu | keyword | http://127.0.0.1:8000` xuất hiện. Giữ cửa sổ PowerShell này mở trong lúc dùng chatbot.

3. Mở [http://127.0.0.1:8000](http://127.0.0.1:8000) trong trình duyệt. Khi thấy màn hình **Bạn cần tra cứu gì?** và trạng thái **… tài liệu sẵn sàng**, bạn có thể gửi câu hỏi. Hãy mở địa chỉ do máy chủ in ra để giao diện kết nối được với API.

Để dừng máy chủ, quay lại cửa sổ PowerShell đang chạy và nhấn **Ctrl+C**. Khi muốn dùng lại, chạy lại lệnh ở bước 2.

## 2. Gửi câu hỏi và xem nguồn

1. Bấm một câu gợi ý để gửi ngay, hoặc nhập câu hỏi vào ô **Nhập câu hỏi của bạn…** ở cuối trang rồi nhấn **Enter** hoặc nút **↑**. Mỗi câu hỏi dài tối đa 500 ký tự.
2. Đợi PTIT Chat trả kết quả. Nếu đã bật Gemini và API trả lời thành công, bạn sẽ thấy câu trả lời tổng hợp hiện dần. Ở chế độ tra cứu cục bộ, kết quả hiện dưới dạng trích đoạn từ tài liệu.
3. Bấm vào mục nguồn có số **[1]**, **[2]** hoặc **[3]** bên dưới kết quả để xem trích đoạn. Nếu có liên kết nguồn, bấm tên tài liệu để mở trang gốc và kiểm tra học kỳ, đối tượng áp dụng hoặc thời hạn.

Bạn có thể thử ba câu hỏi sau.

- CNTT khóa 2025 có bao nhiêu tín chỉ?
- Mất thẻ sinh viên thì làm lại như thế nào?
- Học phí học lại lớp riêng kỳ I năm học 2025–2026 môn INT1313 là bao nhiêu?

Nếu kết quả quá rộng, hãy thêm mã học phần, khóa tuyển sinh, học kỳ hoặc năm học. Với thông báo theo đợt, ngày tháng trong câu hỏi giúp phân biệt các thông báo cùng chủ đề.

Để thử hỏi tiếp theo ngữ cảnh, gửi “Thủ tục cấp lại thẻ sinh viên như thế nào?” rồi hỏi “Cần giấy tờ gì?” trong cùng cuộc trò chuyện. Backend chuẩn bị ngữ cảnh và truy vấn cục bộ, sau đó gọi Gemini **tối đa một lần cho mỗi câu hỏi văn bản** để tạo đáp án. Câu độc lập giữ nguyên chủ đề mới; câu tiếp nối thông dụng được bổ sung chủ đề trước khi tìm nguồn. Khi người dùng đổi khóa hoặc năm học, điều kiện mới thay điều kiện cũ trong truy vấn. “Tóm tắt lại” hoặc “Giải thích thêm” dùng câu trả lời và các nguồn đã kiểm tra của lượt được nhắc đến.

Hệ thống giữ tối đa **6 lượt gần nhất**, tối đa **10.000 ký tự mỗi câu trả lời** và **24.000 ký tự cho tổng câu hỏi/câu trả lời trong ngữ cảnh**. Khi vượt giới hạn tổng, các lượt cũ nhất được bỏ trước. Với câu tiếp nối thông thường, prompt chỉ gửi tối đa hai lượt liên quan gần nhất, giới hạn 1.200 ký tự mỗi đáp án và đánh dấu phần bị cắt. Khi tóm tắt hoặc diễn đạt lại, prompt giữ đầy đủ lượt được chọn; lượt vốn đã bị cắt sẽ được yêu cầu hỏi lại. Nguồn của lượt trước được giữ bằng mã tham chiếu và kiểm tra lại trong kho tài liệu hoặc tệp đang dùng. Lịch sử chỉ là gợi ý ngữ cảnh; thông tin học vụ phải dựa trên các trích đoạn nguồn hiện tại.

Các tham chiếu người hoặc đối tượng quá mơ hồ được hỏi lại cục bộ. Các cách diễn đạt phức tạp ngoài quy tắc có thể cần người dùng ghi câu hỏi đầy đủ. Khi chưa bật Gemini, phần chuẩn bị truy vấn vẫn hoạt động và kết quả là các trích đoạn tìm được. Nếu Gemini hoặc streaming gặp lỗi, backend trả thông báo lỗi và **không tự gọi lại**, kể cả khi chạm giới hạn token. Phần đáp án chưa hoàn tất không được lưu thành tin nhắn bot hoàn chỉnh trong CSDL. Trạng thái `/api/status` có `context_mode: "local"`, `max_generation_calls: 1`; trường `generation_metrics.calls` của kết quả cho biết số lượt gọi thực tế.

Nút **Cuộc trò chuyện mới** đặt lại nội dung đang hiển thị, ngữ cảnh và lựa chọn tệp. Bạn có thể bấm một câu trong **Câu hỏi gần đây** để gửi lại. Tải lại trang sẽ làm mất lịch sử của tab đó.

Tin nhắn chỉ có lời chào như “Xin chào”, “chao ban a” hoặc “Hi!” nhận câu trả lời “Chào bạn!”, không tìm tài liệu hay gọi Gemini. Tin nhắn có cả lời chào và câu hỏi như “Chào bạn, học phí kỳ này bao nhiêu?” vẫn được tra cứu bình thường. Lượt chào không được dùng làm ngữ cảnh viết lại câu hỏi và giữ nguyên lựa chọn tệp, ngữ cảnh tra cứu trước đó.

## 3. Bật Gemini để nhận câu trả lời tổng hợp

Bạn cần kết nối Internet và một khóa Gemini API. Đăng nhập, chọn dự án và tạo khóa trong [Google AI Studio](https://aistudio.google.com/apikey).

1. Trong PowerShell tại thư mục dự án, tạo `.env` từ tệp mẫu nếu chưa có rồi mở tệp bằng Notepad.

   ~~~powershell
   if (-not (Test-Path -LiteralPath ".env")) {
       Copy-Item -LiteralPath ".env.example" -Destination ".env"
   }
   notepad .env
   ~~~

2. Điền khóa thật sau dấu `=` của `GEMINI_API_KEY`. Giữ mã model trong mẫu hoặc điền mã model tạo văn bản mà dự án Google của bạn có quyền sử dụng. Mẫu bên dưới minh họa hai dòng cấu hình.

   ~~~dotenv
   GEMINI_API_KEY=khoa_api_cua_ban
   GEMINI_MODEL=gemini-3.5-flash-lite
   ~~~

3. Lưu tệp, nhấn **Ctrl+C** ở cửa sổ máy chủ và chạy lại lệnh khởi động. Mở [trạng thái máy chủ](http://127.0.0.1:8000/api/status) để kiểm tra trường `model`, rồi gửi một câu hỏi về kho PTIT để thử tạo câu trả lời. Trường `model` cho biết cấu hình máy chủ đã đọc. Gửi câu hỏi mới kiểm tra được khóa và model có gọi API thành công hay không.

Biến môi trường `GEMINI_API_KEY` và `GEMINI_MODEL` được ưu tiên hơn giá trị trong `.env`. Backend đọc khóa và tệp `.env` được Git bỏ qua. Khi Gemini hoạt động, backend gửi câu hỏi và các trích đoạn liên quan đến Gemini để tổng hợp, kể cả trích đoạn của tệp nếu bạn chọn hỏi về tệp đó. Hệ thống có thể gửi các lượt gần đây cùng nguồn để diễn giải câu hỏi nối tiếp. Nếu thiếu khóa hoặc Gemini gặp lỗi, giao diện vẫn hiển thị các đoạn tìm được.

## 4. Tải tệp và đặt câu hỏi về nội dung tệp

Markdown UTF-8 có thể dùng ngay ở chế độ chạy nhanh. Để đọc Word, PDF hoặc Excel, hãy dừng máy chủ và cài thư viện của dự án vào môi trường ảo. Bước cài đặt này cũng chuẩn bị thư viện cho tìm kiếm vector ở mục 5.

~~~powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -X utf8 backend/server.py --keyword-only
~~~

1. Trên giao diện, bấm **biểu tượng kẹp giấy** cạnh ô nhập câu hỏi và chọn tệp. Định dạng hỗ trợ gồm `.docx`, `.pdf`, `.md`, `.markdown`, `.xlsx` và `.xls`.
2. Đợi thông báo **Tệp đã sẵn sàng cho câu hỏi tiếp theo.** Tệp vừa tải được tự chọn cho câu hỏi đầu tiên.
3. Nhập câu hỏi có từ khóa xuất hiện trong tên mục, tiêu đề cột hoặc nội dung tệp. Ví dụ, nếu tệp Excel có cột “Mã học phần” và “Học phí”, bạn có thể hỏi “Học phí của mã học phần INT1313 trong bảng là bao nhiêu?”. Gửi câu hỏi và mở mục nguồn để xem phần, trang hoặc dòng dữ liệu được dùng.
4. Tệp đầu tiên được chọn mặc định và tiếp tục dùng cho các câu hỏi sau. Dùng danh sách **Tệp sử dụng** để chọn tệp đã tải hoặc **Không dùng tệp** để tra cứu kho PTIT. Nút **Tải tệp mới** thêm tệp vào danh sách. Đổi nguồn tra cứu sẽ bắt đầu lại ngữ cảnh.

Mỗi tệp được hỗ trợ tối đa **10 MB** và **500.000 ký tự** sau khi trích xuất. PDF cần có lớp văn bản có thể chọn hoặc sao chép. Với Excel, hệ thống đọc giá trị công thức đã lưu nếu có. Nếu tệp hết hạn sau hai giờ không dùng hoặc trở nên không khả dụng sau khi khởi động lại máy chủ, hãy tải lại tệp.

## 5. Bật tìm kiếm kết hợp từ khóa và vector

Chế độ này tìm thêm các đoạn tương đồng về ngữ nghĩa trong kho PTIT. Hãy chạy phần cài đặt môi trường ảo và thư viện ở mục 4 trước. Bạn cần Internet để tải mô hình embedding `intfloat/multilingual-e5-small` trong lần lập chỉ mục đầu tiên.

1. Dừng máy chủ bằng **Ctrl+C** rồi lập chỉ mục. Đợi đến khi thấy dòng `Indexed … chunks from … documents.`.

   ~~~powershell
   .\.venv\Scripts\python.exe -X utf8 backend/build_vector_index.py --build
   ~~~

2. Khởi động máy chủ với lệnh sau để dùng chỉ mục trong `.chroma/`.

   ~~~powershell
   .\.venv\Scripts\python.exe -X utf8 backend/server.py
   ~~~

3. Kiểm tra dòng khởi động có chữ `hybrid` hoặc mở [trạng thái máy chủ](http://127.0.0.1:8000/api/status) và xem trường `retrieval`. Mở lại giao diện và thử hỏi “Em làm rơi thẻ, xin thẻ mới ở đâu?”.

Khi sửa tài liệu trong `knowledge_base/`, hãy khởi động lại máy chủ để nạp lại chỉ mục từ khóa. Nếu dùng chế độ kết hợp, chạy lại lệnh `--build` trước khi khởi động. Để thử riêng tìm kiếm vector, bạn có thể chạy lệnh sau ở cửa sổ PowerShell khác tại thư mục dự án.

~~~powershell
.\.venv\Scripts\python.exe -X utf8 backend/build_vector_index.py --query "Em làm rơi thẻ, xin thẻ mới ở đâu?"
~~~

## Xử lý lỗi thường gặp

| Hiện tượng | Cách xử lý |
| --- | --- |
| Lệnh báo không tìm thấy `backend/server.py`. | Chạy `Get-Location` và chuyển về thư mục chứa `README.md` và `backend/`. |
| Cổng 8000 đang được dùng. | Thêm `--port 8001` vào lệnh khởi động đang dùng, ví dụ `python -X utf8 backend/server.py --keyword-only --port 8001`. Sau đó mở [http://127.0.0.1:8001](http://127.0.0.1:8001). |
| Trình duyệt không mở được trang hoặc hiện **Mất kết nối máy chủ**. | Kiểm tra PowerShell còn chạy và mở đúng địa chỉ máy chủ in ra. Sau khi khởi động lại máy chủ, tải lại trang. |
| Giao diện chỉ hiện trích đoạn hoặc báo lỗi Gemini. | Nếu muốn dùng Gemini, kiểm tra kết nối Internet, khóa API, mã model và hạn mức của dự án Google. Khởi động lại máy chủ sau khi sửa `.env`. |
| Máy chủ báo thiếu thư viện đọc tệp. | Cài thư viện theo mục 4 và dùng chính `.venv\Scripts\python.exe` để khởi động lại máy chủ. |
| Không đọc được nội dung PDF. | Thử chọn hoặc sao chép chữ trong PDF. Với PDF chỉ có ảnh scan, hãy nhận dạng văn bản trước hoặc tải lên bản PDF có lớp văn bản. |
| Máy chủ báo `Cannot open vector index` hoặc không tải được mô hình embedding. | Thử lại bước cài thư viện và lập chỉ mục ở mục 5. Để mở giao diện ngay, thêm `--keyword-only` vào lệnh khởi động. |

## Cấu trúc dự án

| Đường dẫn | Nội dung |
| --- | --- |
| [`frontend/`](frontend/) | Giao diện chat bằng HTML, CSS và JavaScript. |
| [`backend/`](backend/) | Máy chủ HTTP, tra cứu từ khóa và vector, đọc tệp, xử lý ngữ cảnh và gọi Gemini. |
| [`knowledge_base/`](knowledge_base/) | Tài liệu Markdown về PTIT và thông tin nguồn. |
| [`docs/`](docs/) | Phạm vi dữ liệu, danh mục nguồn và [sơ đồ luồng RAG](docs/RAGworkflow.webp). |
| [`requirements.txt`](requirements.txt) | Thư viện đọc tệp và tìm kiếm vector. |
| [`.env.example`](.env.example) | Mẫu cấu hình Gemini. |

Giao diện dùng `GET /api/status` để xem số tài liệu, chế độ tra cứu và model đã cấu hình, `POST /api/uploads` để tải tệp và `POST /api/chat` để gửi câu hỏi. API chat nhận JSON có trường `question`, cùng các trường tùy chọn `upload_id` và `history`. Trường `history` chứa tối đa sáu lượt cùng nguồn theo thứ tự từ cũ đến mới, mỗi lượt có `question` và `answer`; có thể kèm `intent` (`question`, `transform`, `clarification`), `source_ids`, `person` và cờ `answer_truncated`. Phản hồi tra cứu có `source_ids` theo đúng thứ tự `passages`; gửi lại các mã này trong lượt lịch sử tương ứng để hỗ trợ tóm tắt hoặc giải thích nguồn cũ. Client không cần gửi lại nội dung trích đoạn. API giới hạn thân yêu cầu ở 128 KiB. API mặc định trả JSON. Client có thể gửi header `Accept: application/x-ndjson` để nhận câu trả lời theo luồng khi Gemini được bật và có trích đoạn phù hợp.

Với lời chào thuần túy, API luôn trả JSON `{"intent":"greeting","answer":"Chào bạn!","passages":[]}`, kể cả khi client yêu cầu NDJSON.

Khi cần làm rõ, API trả JSON với `intent: clarification`, câu hỏi bổ sung trong `answer`, `passages: []` và `source_ids: []`. Trường `context_error` xuất hiện nếu bước làm rõ lỗi; frontend hiển thị câu hỏi bổ sung thay cho thông báo thiếu tài liệu. Lượt làm rõ được giữ để câu tiếp theo như “Đúng rồi” có thể xác nhận chủ đề, nhưng không được dùng làm nguồn thông tin học vụ. Câu trả lời sinh lỗi hoặc luồng bị ngắt không được lưu vào ngữ cảnh.

## Kiểm thử

Các kiểm thử dùng mô phỏng HTTP/Gemini và DOM, không gọi API thật hoặc cần cài thêm thư viện:

~~~powershell
python -X utf8 -m unittest discover -s backend -p 'test_*.py' -v
node --test frontend/test_context.cjs
~~~
