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
Mỗi câu hỏi độc lập, chưa rewrite theo lịch sử; API trả JSON, chưa có SSE streaming (mục tùy chọn trong tài liệu).

## Kiểm thử

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s BE/tests -v
```

Test dùng DB/index tạm và embedding giả, không gọi API model thật.
