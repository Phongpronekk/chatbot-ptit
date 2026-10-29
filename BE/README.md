# PTIT Chatbot API — Chroma RAG

## Chạy hệ thống

`BE/.env` là cấu hình chính và được nạp bằng đường dẫn tuyệt đối khi BE khởi động.
Không cần export provider/model trong terminal. Sau khi sửa `.env`, khởi động lại BE.

Cấu hình hiện tại dùng Gemini (`LLM_PROVIDER=google`, `MODEL_NAME=gemini-3.5-flash`,
`DIRECT_OLLAMA_CHAT=false`). Điền `GOOGLE_API_KEY` trong `BE/.env` rồi khởi động lại BE.
Embedding và Chroma vẫn chạy local; chỉ câu hỏi và các đoạn tài liệu liên quan được gửi tới Gemini.
Khi chưa có API key, hệ thống chỉ trả kết quả tra cứu nguồn, chưa tổng hợp bằng Gemini.

```powershell
cd D:\chatbot-ptit
.\.venv\Scripts\python.exe -m pip install -r BE/requirements.txt
.\.venv\Scripts\python.exe -m BE.scripts.ingest
.\.venv\Scripts\python.exe -m uvicorn BE.main:app --host 127.0.0.1 --port 8000
```

Hoặc `powershell -ExecutionPolicy Bypass -File .\start-local.ps1`; script chỉ chạy BE theo `.env`,
không ép dùng Ollama. Nếu muốn local: `LLM_PROVIDER=ollama`, `MODEL_NAME=qwen2.5-coder:3b`, giữ Ollama mở.
Nếu muốn Gemini: `LLM_PROVIDER=google`, model/key Google có quyền truy cập.

## RAG theo rag_integration.md

```dotenv
RETRIEVAL_BACKEND=vector
EMBEDDING_MODEL_NAME=intfloat/multilingual-e5-small
CHROMA_DIR=BE/chroma_db
CHUNK_SIZE=400
CHUNK_OVERLAP=60
RAG_TOP_K=4
RAG_MIN_SCORE=0.35
EMBEDDING_THREADS=4
```

- `Knowledge.chunks()` giữ heading/metadata và dùng RecursiveCharacterTextSplitter cắt đoạn dài.
- `RagStore.ensure_index()` fingerprint toàn bộ chunk, metadata, model và config.
- Chroma persist dùng cosine; RAG_MIN_SCORE lọc nhánh vector. Hybrid mặc định bật: BM25 không dấu, chuẩn hóa Unicode/khoảng trắng, thuật ngữ tên đầy đủ/viết tắt và hợp nhất thứ hạng RRF. Từ khóa khớp mạnh có thể bổ sung kết quả dưới ngưỡng vector.
- Xem `Source.score_type` để biết `score` là cosine_similarity hay bm25. Các trường semantic_score, lexical_score và fusion_score tách riêng ba thang điểm; không phải xác suất đúng. `/api/rag/search` có query_processing và hybrid_search để kiểm tra từng nhánh. `RETRIEVAL_HYBRID=false` trả về nhánh vector đơn; lexical fallback vẫn dùng BM25 không dấu.
- Mặc định lexical để test không tải model. `.env` triển khai bật vector.
- Model được nạp một lần trong lifespan; startup kiểm tra chỉ mục, dùng cache và cập nhật khi khác fingerprint.
- Khi vector lỗi (kể cả startup lỗi), báo warning và tự fallback lexical. Vector trả rỗng hợp lệ không fallback.
- Lệnh ingest lần thứ hai báo `up-to-date`; dữ liệu đổi thì tạo collection mới, không tăng trùng collection đang dùng.
- Collection cũ được giữ để không mất chỉ mục tốt nếu lần build sau lỗi; không ghi đè hội thoại.
- `BE.build_index` chỉ còn là alias cho `BE.scripts.ingest`. Kho NumPy/BM25 cũ không còn được BE sử dụng.

## Embedding model

E5-small mặc định dùng ONNX, prefix `passage: ` cho tài liệu và `query: ` cho câu hỏi,
mean pooling + L2 normalization, tối đa 512 token; cả hai phía dùng cùng tokenizer/model.
Không cần PyVi cho E5. Khi muốn BKAI/PhoBERT, cài dependency tùy chọn:

```powershell
.\.venv\Scripts\python.exe -m pip install -r BE/requirements-embedding-hf.txt
```

Đặt `EMBEDDING_MODEL_NAME=bkai-foundation-models/vietnamese-bi-encoder`. Wrapper sẽ tách từ
bằng PyVi cả khi index và query. Model HuggingFace khác dùng HuggingFaceEmbeddings. Đổi model thì ingest lại.

Cấu hình hiện tại dùng CPU int8; không cần CUDA/DirectML và không tranh VRAM với Ollama.
Embedding không dùng API tính phí; lần tải model cần Internet, các lần phục vụ dùng cache local.
Ngưỡng 0.35 chỉ là điểm khởi đầu; phải hiệu chỉnh trên câu hỏi đúng miền/ngoài miền, không coi là confidence.
Với 5 tài liệu hiện tại, thử một số câu về KTX/thư viện/CLB đạt khoảng 0.84–0.90,
câu ngoài miền thử nghiệm khoảng 0.75–0.78; `.env` thực tế đặt `RAG_MIN_SCORE=0.80`.
Đây chỉ là hiệu chỉnh sơ bộ trên ít câu hỏi, không bảo đảm loại mọi câu ngoài phạm vi.

`DIRECT_OLLAMA_CHAT=false` để chat đi qua RAG. Có thể bật `true` khi chỉ muốn thử
model Ollama trực tiếp; khi đó Swagger báo retrieval disabled và không tải chỉ mục.

## Swagger

Mở http://127.0.0.1:8000/docs#/RAG:

- GET `/api/rag/status`: backend thực dùng, warning fallback, model, số chunk, nhóm, config Chroma.
- POST `/api/rag/search`: Try it out → question/limit → Execute; xem vector preview, cosine distance/similarity,
  ngưỡng chấp nhận, thời gian và nguồn. Cùng retriever với chat, không gọi LLM, không lưu hội thoại.
- GET `/api/health`: retrieval=vector nếu Chroma sẵn sàng, lexical nếu đang fallback.

## Hội thoại

Các API `/api/conversations`, `/api/conversations/{id}`, `/api/conversations/{id}/messages`
được giữ nguyên. Tin nhắn gửi gồm `message` và UUID `request_id`. Retry cùng ID không tạo trùng.
SQLite mặc định `BE/storage/chat.sqlite3`; lưu trọn lượt sau khi trả lời thành công, lỗi LLM trả 503.
Cookie HttpOnly/SameSite=Lax tách lịch sử theo trình duyệt; chưa có đăng nhập tài khoản.
Nguồn giữ URL, thời điểm thu thập, chủ đề, nội dung, ghi chú phạm vi. Snapshot không chứng minh còn hiệu lực.
Tra cứu kho PTIT vẫn xử lý từng câu hỏi độc lập. Hỏi đáp theo file dùng thêm bốn tin nhắn gần nhất
để hiểu câu hỏi tiếp nối; API trả JSON, chưa có SSE streaming.

## File trong bộ nhớ tạm

FE có nút **+** để tải PDF, DOCX, XLSX, XLS. API cùng cookie/kiểm tra quyền với hội thoại:

| API | Chức năng |
| --- | --- |
| POST `/api/conversations/{id}/documents` | Multipart, đúng một trường `file`; đọc file và trả metadata, không trả toàn bộ nội dung |
| GET `/api/conversations/{id}/documents` | Danh sách file còn trong bộ nhớ tạm |
| DELETE `/api/conversations/{id}/documents/{document_id}` | Xóa nội dung khỏi bộ nhớ tạm |
| POST `/api/conversations/{id}/messages` | `document_ids` là file ứng viên, `attachment_ids` gắn file mới; `retrieval_scope`: `auto` (mặc định), `knowledge`, `documents` |

FE chỉ chọn file vào bản nháp khi nhấn **+**; nhấn **Gửi** mới upload rồi gửi tin nhắn.
GET hội thoại và POST tin nhắn trả thêm `documents`; mỗi tin nhắn có `attachments` gồm `id`, `filename`, `size`.
Metadata đính kèm được lấy từ bộ nhớ đã kiểm tra quyền, lưu cùng lượt chat trong SQLite;
các câu hỏi tiếp nối chỉ gửi `document_ids`, không gắn lại thẻ file vào tin nhắn mới.
`attachment_ids` phải thuộc `document_ids` và cuộc trò chuyện. File mới gửi luôn dùng nhánh file.
`message_routing.py` chọn nguồn từng câu: câu mới về PTIT như `ktx`/`BHYT` dùng kho PTIT;
câu nhắc rõ file hoặc nối tiếp lượt file dùng nhánh file. Không giữ chế độ file chỉ vì chat từng tải file.
Chọn `knowledge`/`documents` để yêu cầu nguồn cụ thể. File không còn hiệu lực trong nhánh file trả 410,
còn câu mới về PTIT không bị chặn chỉ vì file ứng viên đã hết hạn. Lịch sử nhánh file chỉ lấy các lượt
có nguồn thuộc file được chọn; lượt trả lời PTIT không được đưa vào ngữ cảnh file.
Cột `messages.attachments` được bổ sung tự động khi khởi động, giữ nguyên tin nhắn cũ.
Nguồn từ file có `document_id`, `location`,
`source_file`, `content`, URL trống; FE hiển thị vị trí thay vì liên kết nguồn chính thức.
File hết hạn/bị xóa/không thuộc hội thoại trả 410, không chuyển ngầm sang kho PTIT và không lưu lượt lỗi.
Retry cùng `request_id` vẫn trả lượt đã lưu, kể cả file sau đó đã hết hạn.

`BE/attachments.py` giữ văn bản trong RAM hai giờ kể từ lúc tải; cleanup mỗi phút và trước truy cập,
xóa khi xóa hội thoại hoặc shutdown. Parser multipart giữ file trong RAM và chặn body quá giới hạn,
không spool file gốc ra đĩa. Không persist file hoặc index vào Chroma.
Lịch sử và đoạn trích đã dùng trong câu trả lời vẫn lưu SQLite; xóa hội thoại để xóa lịch sử.
Kho tạm chỉ dùng trong **một process/worker**; restart làm mất file nhưng giữ hội thoại.

Giới hạn: 10 MB/file, 5 file/hội thoại, 20 file/trình duyệt, 100 file/toàn process và tổng văn bản đã chia đoạn
10 triệu ký tự. Giới hạn nội dung mỗi file 500.000 ký tự, Office giải nén 40 MB, PDF 300 trang,
Excel 50 sheet × tối đa 20.000 dòng/200 cột. PDF scan cần OCR, không nhận file có mật khẩu;
`.doc` cần chuyển `.docx`. XLSX giữ công thức như văn bản, không tính lại hay mở liên kết ngoài.
Truy xuất BM25 không dấu; tóm tắt lấy đoạn mẫu theo file, không hứa đọc toàn bộ bảng lớn để tính tổng.
Các đoạn được chọn và lịch sử ngắn dùng cùng provider/model; chưa có API key thì trả đoạn trích.

## Kiểm thử

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s BE/tests -v
```

Test dùng DB/index tạm và embedding giả, không gọi API model thật.
