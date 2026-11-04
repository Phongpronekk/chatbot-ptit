# Cấu trúc thực tế của hệ thống PTIT Chatbot

```text
BE/
  .env                 Cấu hình chính
  main.py              FastAPI, lifespan, health, Swagger RAG, API hội thoại
  knowledge.py         Đọc metadata, heading chunks, chunks(), retrieve(), fallback lexical, prompt/LLM
  rag_store.py         E5/BKAI embeddings, Chroma persist, fingerprint, ingest idempotent, cosine score
  scripts/ingest.py    CLI tạo/cập nhật chỉ mục
  build_index.py       Alias tương thích cho CLI ingest
  schemas.py           Request/response
  database.py          SQLite lưu trọn lượt hội thoại
  chroma_db/           Chroma + cache embedding, gitignored
  storage/             Hội thoại, cache model, gitignored
  tests/               Kiểm thử API, vector store, fallback, startup
FE/src/features/chat/  Giao diện, store, dịch vụ API
data/*.md              Nguồn có front-matter
docs/                  Bộ thu thập dữ liệu và báo cáo
rag_demo.py            Demo CLI dùng pipeline BE thực tế
```

## Cấu hình duy nhất

`BE/.env` → `RETRIEVAL_BACKEND`, `EMBEDDING_MODEL_NAME`, `CHROMA_DIR`, `CHUNK_SIZE`,
`CHUNK_OVERLAP`, `RAG_TOP_K`, `RAG_MIN_SCORE`. Mặc định code: lexical, E5-small, 400/60, k=4.
Không dùng các biến cũ `RETRIEVAL_MODE`/`EMBEDDING_MODEL` cho BE.

E5 chạy qua ONNX CPU int8 để tránh dependency PyTorch nặng.
BKAI và các HuggingFace encoder khác dùng requirements-embedding-hf.txt; BKAI tách từ PyVi cả hai phía.
Chỉ mục được build offline bằng `python -m BE.scripts.ingest`; startup kiểm tra fingerprint và cập nhật nếu cần.
Fingerprint tính từ model, cấu hình và toàn bộ chunk/metadata. Lần chạy thứ hai không thêm trùng.
Build dùng collection mới và chỉ đổi manifest sau khi thành công; cache vector giúp tiếp tục lần bị gián đoạn.

## Các bước online

1. Embedding câu hỏi bằng cùng encoder.
2. Chroma tìm top-k theo cosine distance.
3. Đổi thành similarity = 1 - distance, lọc mọi kết quả dưới RAG_MIN_SCORE.
4. Nếu vector lỗi: lexical fallback. Nếu vector trả rỗng hợp lệ: giữ rỗng, không cố ghép nguồn khác.
5. Ghép context + URL + phạm vi/ngày áp dụng vào prompt, gọi LLM.
6. Lưu nguyên lượt hỏi/đáp atomically rồi trả JSON cho FE. Streaming SSE là phần tùy chọn chưa triển khai.
