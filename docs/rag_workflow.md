# Luồng RAG trong dự án PTIT Chatbot

## Chuẩn bị dữ liệu và tạo chỉ mục

| Bước | File và hàm | Vai trò |
|---|---|---|
| Kho tài liệu | [data/](../data/) | Chứa 5 file Markdown dùng để hỏi đáp về PTIT. |
| Chunking | [BE/knowledge.py](../BE/knowledge.py) · `_heading_chunks()`, `chunks()` | Tách nội dung theo tiêu đề, rồi dùng `RecursiveCharacterTextSplitter` để chia thành các đoạn nhỏ có phần chồng lấn. |
| Embedding | [BE/rag_store.py](../BE/rag_store.py) · `build_embeddings()`, `embed_documents()`, `embed_query()` | Chuyển các đoạn tài liệu và câu hỏi thành vector khi dùng chế độ vector. |
| Lưu chỉ mục vector | [BE/scripts/ingest.py](../BE/scripts/ingest.py) · `main()` → [BE/rag_store.py](../BE/rag_store.py) · `RagStore.ensure_index()` | Lấy các đoạn, tạo embedding và lưu chỉ mục vào ChromaDB. |

## Xử lý một câu hỏi

| Bước | File và hàm | Vai trò |
|---|---|---|
| Gửi và nhận tin nhắn | [chat.service.ts](../FE/src/features/chat/chat.service.ts) → [BE/main.py](../BE/main.py) · `stream_message()` | Vue gửi câu hỏi đến FastAPI và nhận phản hồi qua luồng streaming. |
| Chọn cách truy xuất | [BE/knowledge.py](../BE/knowledge.py) · `retrieve()` | Điều phối tìm kiếm bằng BM25 hoặc vector, rồi xếp lại các đoạn để chọn nguồn. |
| Tìm kiếm BM25 | [BE/knowledge.py](../BE/knowledge.py) · `_lexical_retrieve()` → [BE/search_text.py](../BE/search_text.py) · `KeywordIndex.search()` | Chuẩn hóa tiếng Việt và xếp hạng đoạn trích theo mức khớp từ khóa. |
| Tìm kiếm vector | [BE/rag_store.py](../BE/rag_store.py) · `RagStore.search()` | Tạo embedding cho câu hỏi và tìm các đoạn tương tự trong ChromaDB khi bật chế độ vector. |
| Ghép prompt và gọi LLM | [BE/knowledge.py](../BE/knowledge.py) · `stream_answer_from_sources()` | Đưa câu hỏi và các đoạn trích vào prompt để mô hình sinh câu trả lời. |
| Hiển thị câu trả lời | [chat.store.ts](../FE/src/features/chat/chat.store.ts) → [ChatView.vue](../FE/src/features/chat/ChatView.vue) | Cập nhật và hiển thị nội dung nhận được cùng các nguồn trích dẫn. |

## Luồng BM25 đang dùng

Đối với câu hỏi tra kho PTIT, có thể đọc mã theo thứ tự:

`stream_message()` → `stream_answer()` → `retrieve()` → `_lexical_retrieve()` → `KeywordIndex.search()`

Sau khi tìm kiếm, `_rank_and_deduplicate_chunks()` trong [BE/knowledge.py](../BE/knowledge.py) xếp lại các đoạn trước khi đưa vào prompt. Với câu hỏi về lịch hè thư viện, đây là nơi ưu tiên đoạn có giờ mở cửa trong bài đã tìm được.

