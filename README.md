# PTIT Chatbot - RAG Demo (Person C)

Demo nhánh RAG cho domain: CLB, Quy chế chung, Ký túc xá, Thư viện, Thực tập/Việc làm.

## Kiến trúc

Theo đúng RAG Workflow chuẩn:

```
Knowledge Base (data/*.md)
      │ chunking (chunk_size=400, overlap=60)
      ▼
   Chunks
      │ embedding (bkai-foundation-models/vietnamese-bi-encoder)
      ▼
Vector Database (ChromaDB, persist tại ./chroma_db)

User Query ──► embed query ──► similarity search trong Vector DB ──► Context
                                                                        │
                                                    Context + Query ──► Prompt
                                                                        │
                                                                        ▼
                                                                       LLM (Claude)
                                                                        │
                                                                        ▼
                                                              Response cho User
```

## Cấu trúc thư mục

```
ptit_rag_demo/
├── data/
│   ├── ktx.md        # Ký túc xá (nguồn: ptit.edu.vn)
│   ├── thu_vien.md   # Thư viện (nguồn: lib.ptit.edu.vn)
│   └── clb.md         # Câu lạc bộ (nguồn: ptit.edu.vn)
├── rag_demo.py
├── requirements.txt
└── README.md
```

Mỗi file trong `data/` có front-matter YAML (`source_url`, `fetched_date`,
`topic_group`, ...) theo quy ước snapshot thủ công của nhóm.

## Cài đặt

```bash
pip install -r requirements.txt --break-system-packages
```

## Chạy demo

Script hỗ trợ 2 LLM provider, chọn qua biến môi trường `LLM_PROVIDER`
(mặc định: `anthropic`).

```bash
# Không set API key - vẫn chạy đủ pipeline chunking -> embedding -> retrieval,
# chỉ dừng trước bước gọi LLM
python rag_demo.py

# Dùng Claude (Anthropic)
export LLM_PROVIDER=anthropic
export ANTHROPIC_API_KEY=sk-ant-...
python rag_demo.py

# Dùng Gemini (Google) - phù hợp để test bằng gói Gemini cho sinh viên
export LLM_PROVIDER=google
export GOOGLE_API_KEY=...     # lấy free tại aistudio.google.com
python rag_demo.py
```

Trên Windows (PyCharm), set các biến này trong **Run → Edit Configurations →
Environment variables** thay vì `export`.

Không set API key tương ứng, script vẫn chạy hết chunking, embedding, và in ra
các chunk được retrieve cho từng câu hỏi mẫu — đủ để kiểm tra chất lượng
retrieval mà không cần gọi LLM.

Muốn đổi model cụ thể trong từng provider, set thêm biến `MODEL_NAME` (xem
mục "Chọn model Gemini" bên dưới).

## Chọn model Gemini

Mặc định script dùng `gemini-3.5-flash` (cân bằng giá/chất lượng, còn hỗ trợ
lâu dài). Có thể đổi qua biến `MODEL_NAME`:

| Model | Khi nào dùng |
|---|---|
| `gemini-3.5-flash` | Mặc định, phù hợp cho hầu hết việc test RAG QA |
| `gemini-3.1-flash-lite` hoặc `gemini-3.5-flash-lite` | Rẻ/nhanh nhất, dùng khi test lặp lại nhiều lần |
| `gemini-3.5-pro` (nếu gói sinh viên cho phép) | Chất lượng cao hơn, dùng khi so sánh với Claude Sonnet |

**Tránh dùng** `gemini-2.5-flash` / `gemini-2.5-pro` — theo thông báo chính
thức của Google, các model Gemini 2.5 sẽ ngừng hoạt động vào tháng 10/2026,
có thể gây gián đoạn giữa lúc làm đồ án. Luôn kiểm tra danh sách model hiện
hành tại `aistudio.google.com` hoặc `ai.google.dev/gemini-api/docs/models`
trước khi chốt model dùng cho bản demo cuối, vì Google đổi tên/ngừng model khá
thường xuyên.

```bash
export LLM_PROVIDER=google
export GOOGLE_API_KEY=...
export MODEL_NAME=gemini-3.1-flash-lite
python rag_demo.py
```

## Thêm dữ liệu mới

1. Thêm file `.md` mới vào `data/`, theo đúng format front-matter như file
   hiện có (bắt buộc có `source_url`, `fetched_date`, `topic_group`).
2. Xóa thư mục `chroma_db/` (nếu muốn tránh dữ liệu cũ trùng lặp).
3. Chạy lại `python rag_demo.py`.

## So sánh embedding model

Đổi biến `EMBEDDING_MODEL_NAME` trong `rag_demo.py`:

```python
EMBEDDING_MODEL_NAME = "intfloat/multilingual-e5-large"
```

rồi chạy lại để so sánh chất lượng retrieval với
`bkai-foundation-models/vietnamese-bi-encoder` trên cùng bộ câu hỏi mẫu.

## Lưu ý

- Dữ liệu là snapshot thủ công tại thời điểm `fetched_date` ghi trong mỗi
  file — không tự động cập nhật. Cần re-fetch định kỳ nếu nguồn PTIT thay đổi.
- Đây là nhánh RAG độc lập; sẽ được ghép vào `RunnableBranch` tổng cùng nhánh
  SQL khi nhóm hoàn thiện router.