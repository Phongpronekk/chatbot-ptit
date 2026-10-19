# PTIT Chatbot – Cấu trúc thư mục (Feature-based)

Mục tiêu: thay giao diện terminal của `rag_demo.py` bằng web UI Vue 3, giao tiếp với nhánh RAG qua HTTP API.

## 1. Quyết định kiến trúc

| Hạng mục | Lựa chọn | Lý do |
|---|---|---|
| Frontend | Vue 3 + Vite + TypeScript + Pinia + Vue Router | Chuẩn hiện tại, `<script setup>` gọn |
| Backend | **FastAPI** (Python) | `rag_demo.py` đã là Python (ChromaDB, sentence-transformers, LangChain) nên **gộp luôn vào BE**, không viết lại |
| Giao tiếp | REST + SSE (streaming câu trả lời) | Chat cần hiển thị chữ chạy dần |
| Tổ chức code | Feature-based ở cả FE lẫn BE | Mỗi tính năng nằm gọn trong 1 thư mục |

> Thư mục `ptit_rag_demo/` hiện tại **được gộp vào `be/`**: `data/` giữ nguyên, `rag_demo.py` được tách thành các module nhỏ trong `features/rag/`.

## 2. Cây thư mục tổng

```
ptit-chatbot/
├── be/                              # Backend (gộp ptit_rag_demo)
├── fe/                              # Frontend Vue 3
├── docker-compose.yml               # (tuỳ chọn) chạy FE + BE cùng lúc
├── .gitignore
└── README.md
```

## 3. Backend (`be/`)

```
be/
├── data/                            # GIỮ NGUYÊN từ ptit_rag_demo
│   ├── ktx.md
│   ├── thu_vien.md
│   └── clb.md
├── chroma_db/                       # Vector DB (gitignore)
├── app/
│   ├── main.py                      # Khởi tạo FastAPI, CORS, include routers
│   ├── core/
│   │   ├── config.py                # Đọc env: LLM_PROVIDER, API keys, MODEL_NAME, EMBEDDING_MODEL_NAME
│   │   └── logging.py
│   │
│   ├── features/
│   │   ├── chat/                    # Endpoint chat cho FE gọi
│   │   │   ├── chat.router.py       # POST /api/chat, POST /api/chat/stream (SSE)
│   │   │   ├── chat.schemas.py      # ChatRequest, ChatResponse, SourceChunk
│   │   │   └── chat.service.py      # Điều phối: retrieve -> build prompt -> gọi LLM
│   │   │
│   │   ├── rag/                     # Tách từ rag_demo.py
│   │   │   ├── chunking.py          # chunk_size=400, overlap=60 + đọc front-matter YAML
│   │   │   ├── embedding.py         # bkai-foundation-models/vietnamese-bi-encoder
│   │   │   ├── vector_store.py      # ChromaDB: add / persist / query
│   │   │   ├── retriever.py         # embed query -> similarity search -> context
│   │   │   ├── prompt.py            # Template Context + Query -> Prompt
│   │   │   └── rag.schemas.py
│   │   │
│   │   ├── llm/                     # Provider LLM (chọn qua LLM_PROVIDER)
│   │   │   ├── base.py              # Interface chung: generate(), stream()
│   │   │   ├── anthropic_provider.py
│   │   │   ├── google_provider.py
│   │   │   └── llm.factory.py       # Trả provider theo env; không có API key -> chế độ retrieval-only
│   │   │
│   │   ├── knowledge/               # Quản lý dữ liệu nguồn
│   │   │   ├── knowledge.router.py  # GET /api/knowledge/sources, POST /api/knowledge/reindex
│   │   │   ├── knowledge.schemas.py # SourceInfo (source_url, fetched_date, topic_group)
│   │   │   └── knowledge.service.py # Liệt kê file data/, re-ingest vào ChromaDB
│   │   │
│   │   ├── health/
│   │   │   └── health.router.py     # GET /api/health (trạng thái LLM, số chunk trong DB)
│   │   │
│   │   └── auth/                    # (tuỳ chọn, làm sau)
│   │       ├── auth.router.py
│   │       ├── auth.schemas.py
│   │       └── auth.service.py
│   │
│   └── scripts/
│       └── rag_cli.py               # Giữ bản chạy terminal cũ để test nhanh retrieval
│
├── tests/
│   ├── test_chunking.py
│   └── test_retriever.py
├── requirements.txt
├── .env.example
└── README.md
```

### Chuẩn bị cho tương lai
Khi nhóm ghép nhánh SQL + `RunnableBranch`, thêm 2 feature mới vào `features/` mà không đụng code cũ:

```
features/
├── sql_branch/        # Nhánh SQL của thành viên khác
└── router/            # RunnableBranch: phân loại câu hỏi -> RAG hay SQL
```

`chat.service.py` sau đó chỉ cần gọi `router` thay vì gọi thẳng `rag`.

### API contract (BE ↔ FE)

```
POST /api/chat
  req:  { "message": string, "session_id"?: string, "top_k"?: number }
  res:  { "answer": string | null,
          "sources": [{ "content": string, "source_url": string,
                        "topic_group": string, "score": number }],
          "mode": "llm" | "retrieval_only" }

POST /api/chat/stream      -> text/event-stream (token, rồi event "sources", rồi "done")
GET  /api/knowledge/sources
POST /api/knowledge/reindex
GET  /api/health
```

`mode = "retrieval_only"` tương ứng trường hợp chưa set API key (README: chỉ chạy đến bước retrieve) – FE hiển thị các chunk thay cho câu trả lời.

## 4. Frontend (`fe/`)

```
fe/
├── public/
│   └── favicon.ico
├── src/
│   ├── main.ts
│   ├── App.vue
│   │
│   ├── app/                         # Cấu hình toàn cục
│   │   ├── router/
│   │   │   └── index.ts             # Gom route từ các feature
│   │   ├── store/
│   │   │   └── index.ts             # Khởi tạo Pinia
│   │   ├── layouts/
│   │   │   ├── MainLayout.vue       # Sidebar + header + <RouterView>
│   │   │   └── AuthLayout.vue
│   │   └── styles/
│   │       └── main.css
│   │
│   ├── features/
│   │   ├── chat/                    # Tính năng chính
│   │   │   ├── ChatView.vue         # Trang chat
│   │   │   ├── chat.types.ts        # Message, ChatRequest, ChatResponse, SourceChunk
│   │   │   ├── chat.service.ts      # Gọi /api/chat, /api/chat/stream
│   │   │   ├── chat.store.ts        # Pinia: danh sách message, loading, session
│   │   │   ├── chat.routes.ts
│   │   │   ├── components/
│   │   │   │   ├── MessageList.vue
│   │   │   │   ├── MessageBubble.vue
│   │   │   │   ├── ChatInput.vue
│   │   │   │   ├── SourceCard.vue   # Hiển thị chunk + link nguồn PTIT
│   │   │   │   ├── SuggestedQuestions.vue  # Câu hỏi mẫu (CLB, KTX, Thư viện...)
│   │   │   │   └── TypingIndicator.vue
│   │   │   └── composables/
│   │   │       ├── useChat.ts       # Gửi tin, xử lý lỗi
│   │   │       └── useStreamingReply.ts  # Đọc SSE, nối token
│   │   │
│   │   ├── knowledge/               # Xem nguồn dữ liệu, reindex (dành cho nhóm dev/admin)
│   │   │   ├── KnowledgeView.vue
│   │   │   ├── knowledge.types.ts
│   │   │   ├── knowledge.service.ts
│   │   │   ├── knowledge.store.ts
│   │   │   ├── knowledge.routes.ts
│   │   │   └── components/
│   │   │       ├── SourceTable.vue  # source_url, fetched_date, topic_group
│   │   │       └── ReindexButton.vue
│   │   │
│   │   ├── retrieval-debug/         # So sánh chất lượng retrieval (README mục so sánh embedding)
│   │   │   ├── RetrievalDebugView.vue
│   │   │   ├── retrievalDebug.types.ts
│   │   │   ├── retrievalDebug.service.ts
│   │   │   └── components/
│   │   │       └── ChunkScoreList.vue
│   │   │
│   │   └── auth/                    # (tuỳ chọn, làm sau)
│   │       ├── AuthView.vue
│   │       ├── auth.types.ts
│   │       ├── auth.service.ts
│   │       ├── auth.store.ts
│   │       ├── auth.routes.ts
│   │       └── components/
│   │           └── LoginForm.vue
│   │
│   └── shared/                      # Dùng chung nhiều feature
│       ├── api/
│       │   ├── httpClient.ts        # Axios/fetch instance, baseURL, interceptor
│       │   └── sse.ts               # Helper đọc Server-Sent Events
│       ├── components/
│       │   ├── BaseButton.vue
│       │   ├── BaseModal.vue
│       │   └── LoadingSpinner.vue
│       ├── composables/
│       │   └── useLocalStorage.ts
│       ├── types/
│       │   └── api.types.ts         # ApiError, Pagination...
│       └── utils/
│           ├── formatDate.ts
│           └── markdown.ts          # Render markdown trong câu trả lời
│
├── .env.development                 # VITE_API_BASE_URL=http://localhost:8000
├── .env.production
├── index.html
├── package.json
├── tsconfig.json
└── vite.config.ts                   # Proxy /api -> http://localhost:8000
```

### Quy ước feature-based (FE)
- Mỗi feature tự chứa: `View` + `types` + `service` + `store` + `routes` + `components/` + `composables/`.
- Feature **không import trực tiếp** từ feature khác; thứ gì dùng chung thì đưa xuống `shared/`.
- Route do từng feature tự khai báo (`*.routes.ts`), `app/router/index.ts` chỉ gom lại.
- Đặt tên: `<feature>.<vai trò>.ts` (ví dụ `chat.service.ts`, `chat.store.ts`).

## 5. Ánh xạ từ `rag_demo.py` hiện tại sang cấu trúc mới

| Phần trong `rag_demo.py` | Chuyển sang |
|---|---|
| Đọc `data/*.md` + front-matter | `features/rag/chunking.py` |
| Chunking (400 / 60) | `features/rag/chunking.py` |
| Embedding model (`EMBEDDING_MODEL_NAME`) | `features/rag/embedding.py` + `core/config.py` |
| ChromaDB persist `./chroma_db` | `features/rag/vector_store.py` |
| Similarity search | `features/rag/retriever.py` |
| Ghép Context + Query | `features/rag/prompt.py` |
| Gọi Claude / Gemini, `LLM_PROVIDER`, `MODEL_NAME` | `features/llm/*` |
| Vòng lặp câu hỏi mẫu + `print` | `scripts/rag_cli.py` (CLI) và `SuggestedQuestions.vue` (FE) |

## 6. Biến môi trường

**`be/.env`**
```
LLM_PROVIDER=anthropic            # hoặc google
ANTHROPIC_API_KEY=
GOOGLE_API_KEY=
MODEL_NAME=
EMBEDDING_MODEL_NAME=bkai-foundation-models/vietnamese-bi-encoder
CORS_ORIGINS=http://localhost:5173
```

**`fe/.env.development`**
```
VITE_API_BASE_URL=http://localhost:8000
```

## 7. Chạy dự án

```bash
# Backend
cd be
pip install -r requirements.txt            # thêm fastapi, uvicorn[standard], sse-starlette
uvicorn app.main:app --reload --port 8000

# Frontend
cd fe
npm install
npm run dev                                 # http://localhost:5173
```

## 8. Thứ tự triển khai gợi ý

1. **BE**: tách `rag_demo.py` thành `features/rag/*`, chạy lại `rag_cli.py` để chắc kết quả không đổi.
2. **BE**: viết `features/chat` với `POST /api/chat` (chưa stream), test bằng Swagger tại `/docs`.
3. **FE**: dựng `shared/api/httpClient.ts` + `features/chat` (gửi/nhận tin, hiển thị `SourceCard`).
4. **BE + FE**: thêm streaming SSE.
5. **FE/BE**: thêm `knowledge` và `retrieval-debug` để kiểm tra chất lượng retrieval.
6. Sau cùng: `auth`, rồi ghép `sql_branch` + `router` khi nhóm hoàn thiện `RunnableBranch`.

## 9. Lưu ý

- Python không import được tên file có dấu chấm như `chat.router.py` theo kiểu thông thường. Nếu thấy vướng, đổi sang `router.py`, `schemas.py`, `service.py` bên trong từng thư mục feature (vẫn giữ nguyên tinh thần feature-based). Phía FE thì giữ nguyên kiểu `chat.service.ts`.
- Lần chạy đầu BE sẽ tải embedding model nên khởi động chậm; nên load model một lần lúc startup (FastAPI `lifespan`), không load lại mỗi request.
- Dữ liệu vẫn là snapshot thủ công theo `fetched_date`; `knowledge` feature giúp thấy rõ dữ liệu nào đã cũ.
