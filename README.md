# PTIT Chatbot — Backend RAG

Bộ dữ liệu được cập nhật theo phạm vi bài đăng năm 2026, gộp vào năm file có sẵn và giữ nguồn riêng từng bài. Xem [danh mục và giới hạn thu thập](docs/ptit_2026_five_files/README.md). Sau khi ingest, khởi động lại BE để nạp collection mới.

Hệ thống dùng FastAPI + Vue, SQLite lưu hội thoại và ChromaDB lưu vector tài liệu.
Cấu hình chính: `BE/.env`; backend tự đọc file này, ưu tiên hơn process environment.

## Luồng RAG

Offline: `data/*.md` → chia heading + RecursiveCharacterTextSplitter → embedding → Chroma persist.
Online: câu hỏi → chuẩn hóa Unicode/khoảng trắng/từ viết tắt → embedding + BM25 không dấu → Chroma cosine và ứng viên từ khóa → lọc bằng chứng và hợp nhất thứ hạng RRF → ghép nguồn vào prompt → LLM → FE.
Nếu vector search lỗi, backend tự dùng BM25 lexical. Không tìm được bằng chứng phù hợp thì trả thiếu thông tin.

Mặc định `RETRIEVAL_HYBRID=true`. Có dấu/không dấu, thừa khoảng trắng và các thuật ngữ như BHYT/bảo hiểm y tế, KTX/ký túc xá, CLB/câu lạc bộ dùng chung cơ chế xử lý. BM25 còn hỗ trợ các cụm không dấu ngoài danh sách thuật ngữ. Danh sách từ viết tắt không bao phủ mọi từ hoặc tự sửa mọi lỗi chính tả.

## Cấu hình RAG

```dotenv
RETRIEVAL_BACKEND=vector
EMBEDDING_MODEL_NAME=intfloat/multilingual-e5-small
CHROMA_DIR=BE/chroma_db
CHUNK_SIZE=400
CHUNK_OVERLAP=60
RAG_TOP_K=4
RAG_MIN_SCORE=0.80
```

E5 dùng cùng model cho tài liệu và câu hỏi, prefix `passage: ` / `query: `, mean pooling và L2 normalization.
LLM độc lập với embedding; giữ `LLM_PROVIDER`, `MODEL_NAME` và API key tương ứng trong `.env`.
`score_type` cho biết thang điểm của nguồn: `cosine_similarity` là `1 - cosine_distance`, `bm25` là điểm từ khóa. `fusion_score` dùng hợp nhất thứ hạng RRF; không so sánh trực tiếp BM25 với cosine. `RAG_MIN_SCORE` chỉ lọc nhánh vector; kết quả từ khóa có bằng chứng mạnh vẫn có thể được chọn. Các điểm này không phải xác suất đúng.

## Chuẩn bị môi trường

Dùng Python 3.11 và Node.js `^22.18.0` hoặc `>=24.12.0` theo `FE/package.json`.
Nếu chưa có môi trường Python, chạy `python -m venv .venv` tại thư mục gốc.
Nếu chưa có `BE/.env`, sao chép từ `BE/.env.example`; không ghi đè file đang dùng.
Lần đầu tải model embedding cần mạng; những lần sau dùng cache local.

## Chuyển model trong BE/.env

`BE/.env` là cấu hình chính. Sau mỗi lần sửa phải khởi động lại BE.

### Gemini API

Cấu hình hiện tại:

```dotenv
LLM_PROVIDER=google
MODEL_NAME=gemini-3.5-flash
GOOGLE_API_KEY=dien_api_key_cua_ban
DIRECT_OLLAMA_CHAT=false
```

Model phải khả dụng với API key của bạn. Không đưa API key lên Git.
Embedding và Chroma vẫn chạy local; chỉ câu hỏi và các đoạn tài liệu liên quan được gửi tới Google.
Khi chưa có key, backend chỉ trả kết quả tra cứu nguồn, chưa tổng hợp bằng Gemini.
Kết nối Gemini dùng kho chứng chỉ hệ điều hành qua truststore, vẫn xác thực HTTPS.

### Ollama local

Sửa các dòng sau trong cùng file:

```dotenv
LLM_PROVIDER=ollama
MODEL_NAME=qwen2.5-coder:3b
OLLAMA_BASE_URL=http://127.0.0.1:11434
DIRECT_OLLAMA_CHAT=false
```

Kiểm tra model:

```powershell
ollama list
# Chỉ tải nếu chưa có model:
ollama pull qwen2.5-coder:3b
ollama run qwen2.5-coder:3b
```

Giữ ứng dụng/dịch vụ Ollama chạy; dùng `ollama serve` nếu chưa chạy.
Không chạy thêm server nếu cổng 11434 đã có Ollama. `ollama ps` cho biết model đang dùng GPU hay CPU.
Không dùng model hậu tố `-cloud` cho nhánh local. Không cần xóa Google API key khi chuyển sang Ollama.

Giữ `DIRECT_OLLAMA_CHAT=false` để dùng RAG. Giá trị `true` chỉ để thử Ollama trực tiếp, bỏ qua RAG.
Chuyển Gemini ↔ Ollama không cần sửa FE hoặc tạo lại embedding.

## Khởi động

```powershell
cd D:\chatbot-ptit
.\.venv\Scripts\python.exe -m pip install -r BE/requirements.txt
.\.venv\Scripts\python.exe -m BE.scripts.ingest
.\.venv\Scripts\python.exe -m uvicorn BE.main:app --host 127.0.0.1 --port 8000
```

Terminal khác:

```powershell
cd D:\chatbot-ptit\FE
npm install
npm run dev
```

Mở địa chỉ FE do Vite in ra, thường là [http://localhost:5173](http://localhost:5173).
Vite proxy chuyển `/api` tới `http://127.0.0.1:8000`.
Có thể chạy BE bằng `powershell -ExecutionPolicy Bypass -File .\start-local.ps1`; script không tự chạy FE.

## Kiểm tra hệ thống và RAG

| API | Chức năng |
| --- | --- |
| [Swagger](http://127.0.0.1:8000/docs#/RAG) | Xem và thử API, mở nhóm RAG |
| [GET /api/health](http://127.0.0.1:8000/api/health) | Provider/model, trạng thái truy xuất, số tài liệu và chunk |
| [GET /api/rag/status](http://127.0.0.1:8000/api/rag/status) | Cấu hình embedding, chỉ mục và nhóm dữ liệu |
| POST /api/rag/search | Chi tiết truy xuất, nguồn và điểm; không gọi LLM hoặc lưu hội thoại |

Trong Swagger, thử `/api/rag/search` với:

```json
{"question": "KTX B2 mức thu bao nhiêu một tháng?", "limit": 4}
```

`llm_configured=true` chỉ xác nhận đã có cấu hình, không đảm bảo API key/quota/model đang hoạt động.
Thử hỏi trên FE để kiểm tra toàn bộ luồng. FE hiển thị tin nhắn ngay và `Thinking...` trong khi chờ;
hiện câu trả lời chỉ hiển thị sau khi BE nhận đầy đủ kết quả, chưa có streaming.

## Cập nhật dữ liệu

Sau khi thêm, sửa hoặc xóa tài liệu trong `data/`, chạy lại:

```powershell
.\.venv\Scripts\python.exe -m BE.scripts.ingest
```

Sau đó khởi động lại BE. Ingest chỉ dùng dữ liệu hiện có, không tự thu thập hay khôi phục tài liệu đã xóa.
Chỉ mục được tái sử dụng nếu dữ liệu và cấu hình không đổi.
Ngưỡng `RAG_MIN_SCORE=0.80` hiện tại mới được thử trên một số câu hỏi; cần đánh giá lại khi đổi dữ liệu/model embedding.
File `.env.example` có giá trị khởi đầu khác; `.env` hiện tại mới quyết định hành vi triển khai.

## Lỗi thường gặp

- **Errno 10048 / cổng 8000 đã được dùng:** kiểm tra `/api/health`. Muốn chạy lại thì Ctrl+C ở terminal BE cũ trước. Dùng `Get-NetTCPConnection -LocalPort 8000 -State Listen` để xác định tiến trình; không dừng tiến trình chưa xác minh.
- **Dịch vụ trả lời chưa sẵn sàng:** xem traceback ở terminal BE. Với Gemini, kiểm tra key, quyền dùng model, quota và mạng; thông báo trên FE là lỗi chung.
- **Không gọi được Ollama:** kiểm tra dịch vụ đang chạy, `ollama list`, `MODEL_NAME` và `OLLAMA_BASE_URL`.
- **Không tìm thấy nguồn:** thử `/api/rag/search`, kiểm tra chỉ mục và ngưỡng. Không hạ ngưỡng tùy tiện vì có thể lấy nguồn không liên quan.
- **Trả lời chậm:** phân biệt thời gian tìm kiếm và thời gian LLM sinh câu trả lời. Local phụ thuộc CPU/GPU, độ dài prompt và đầu ra.

## Công nghệ

| Thành phần | Công nghệ |
| --- | --- |
| FE | Vue 3, TypeScript, Pinia, Vue Router, Vite |
| BE | FastAPI, Uvicorn, Pydantic, HTTPX |
| Hội thoại | SQLite, mặc định `BE/storage/chat.sqlite3` |
| RAG | RecursiveCharacterTextSplitter, FastEmbed/ONNX, ChromaDB |
| Embedding | E5-small, vector 384 chiều, chạy local |
| LLM | Gemini API hoặc Ollama |

## Kiểm tra mã nguồn

```powershell
cd D:\chatbot-ptit
.\.venv\Scripts\python.exe -m unittest discover -s BE/tests -v
cd FE
npm run build
```

`rag_demo.py` dùng cùng Knowledge/config với BE; không còn pipeline riêng có chunk size/k khác nhau.

Xem [BE/README.md](BE/README.md) và [docs/proj_structure.md](docs/proj_structure.md).
