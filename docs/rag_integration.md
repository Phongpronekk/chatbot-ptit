# Hướng dẫn: BE gọi RAG theo sơ đồ RAG Workflow

Mục tiêu: `BE/knowledge.py` hiện đang **tìm kiếm từ khoá (lexical)** rồi gọi LLM. Cần đổi thành đúng sơ đồ RAG:

```
Offline (1 lần / khi data đổi):
  data/*.md ──chunking──► Chunks ──embedding model──► ChromaDB (persist)

Online (mỗi câu hỏi):
  Query ──embed──► similarity search (ChromaDB) ──► Context
  Context + Query ──► Prompt ──► LLM ──► Response ──► FE
```

## 1. Hiện trạng và khoảng cách so với sơ đồ

| Bước trong sơ đồ | Hiện tại trong BE | Cần làm |
|---|---|---|
| Chunking | Cắt theo heading Markdown, nằm lẫn trong `retrieve()` | Tách thành hàm riêng `chunks()`; chunk dài thì cắt tiếp bằng `RecursiveCharacterTextSplitter` |
| Embedding model | Chưa có | Thêm `bkai-foundation-models/vietnamese-bi-encoder` (hoặc e5) |
| Vector DB | Chưa có | ChromaDB persist ở `BE/chroma_db/` |
| Retriever | Điểm TF-IDF tự viết | Similarity search trên ChromaDB, trả về `score` |
| Prompt + LLM | Đã có trong `answer()` | Giữ nguyên |
| Streamed response | Chưa (trả JSON 1 lần) | Tuỳ chọn, xem mục 8 |

Điểm tốt: `answer(question) -> (text, mode, sources)` đã là ranh giới sạch. Chỉ cần thay phần **retrieve**, `main.py`, `schemas.py`, `database.py` gần như không đổi.

## 2. Các điểm không nhất quán cần chốt trước

1. **Chunk size**: `README.md` và `proj_structure.md` ghi 400/60, nhưng `rag_demo.py` đang chạy 600/100. Chọn một bộ số và ghi vào `.env`/hằng số duy nhất.
2. **k**: comment trong `rag_demo.py` ghi k=4 nhưng code là k=5. BE đang dùng limit=3. Chọn một giá trị (gợi ý bắt đầu với 4).
3. **Ingest lặp**: `Chroma.from_documents(...)` mỗi lần chạy sẽ **thêm trùng** chunk (README cũng tự nhắc xoá `chroma_db/`). Trong BE phải làm ingest idempotent (mục 5).
4. **`score` trong `schemas.Source`** là `float` kiểu "càng cao càng giống". Chroma mặc định trả **khoảng cách** (càng thấp càng giống), phải đổi (mục 4).

## 3. Cấu trúc file đề xuất (giữ cấu trúc phẳng hiện tại của BE)

```
BE/
├── knowledge.py       # SỬA: tách chunks(), retrieve() gọi vector store, fallback lexical
├── rag_store.py       # MỚI: embedding + ChromaDB (ingest, search)
├── scripts/
│   └── ingest.py      # MỚI: chạy tay để build/rebuild index
├── main.py            # SỬA NHỎ: khởi tạo store trong lifespan, health báo "vector"
└── chroma_db/         # sinh ra khi chạy (thêm vào .gitignore)
```

Thêm vào `requirements.txt`:

```
chromadb
langchain-chroma
langchain-huggingface
langchain-text-splitters
sentence-transformers
pyvi            # tách từ tiếng Việt, xem mục 6
```

## 4. `BE/rag_store.py` (mới)

```python
import hashlib
import logging
import os
import shutil
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings

logger = logging.getLogger(__name__)
COLLECTION = "ptit_person_c"


def build_embeddings(model_name: str):
    # normalize_embeddings=True để cosine hoạt động ổn định
    return HuggingFaceEmbeddings(
        model_name=model_name,
        encode_kwargs={"normalize_embeddings": True},
    )


class RagStore:
    def __init__(self, persist_dir: Path, model_name: str):
        self.persist_dir = persist_dir
        self.model_name = model_name
        self.embeddings = build_embeddings(model_name)   # load 1 lần, nặng
        self.store = Chroma(
            collection_name=COLLECTION,
            embedding_function=self.embeddings,
            persist_directory=str(persist_dir),
            collection_metadata={"hnsw:space": "cosine"},
        )

    # ---------- Offline: ingest ----------
    @staticmethod
    def fingerprint(chunks: list[dict], model_name: str) -> str:
        h = hashlib.sha256(model_name.encode())
        for c in chunks:
            h.update(c["source_file"].encode())
            h.update(c["content"].encode())
        return h.hexdigest()

    def ensure_index(self, chunks: list[dict]) -> bool:
        """Build lại index nếu data hoặc embedding model đổi. Trả về True nếu đã build lại."""
        marker = self.persist_dir / ".fingerprint"
        current = self.fingerprint(chunks, self.model_name)
        if marker.exists() and marker.read_text() == current and self.store._collection.count() > 0:
            return False
        self.store.delete_collection()
        self.store = Chroma(
            collection_name=COLLECTION,
            embedding_function=self.embeddings,
            persist_directory=str(self.persist_dir),
            collection_metadata={"hnsw:space": "cosine"},
        )
        docs = [
            Document(
                page_content=f'{c["title"]}\n{c["content"]}' if c["title"] else c["content"],
                metadata={k: c[k] for k in
                          ("source_file", "source_url", "fetched_date", "topic_group", "title", "note")},
            )
            for c in chunks
        ]
        ids = [hashlib.sha1(f'{c["source_file"]}|{i}|{c["content"]}'.encode()).hexdigest()
               for i, c in enumerate(chunks)]
        self.store.add_documents(docs, ids=ids)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        marker.write_text(current)
        logger.info("Đã index %d chunks", len(docs))
        return True

    # ---------- Online: retrieve ----------
    def search(self, query: str, limit: int = 4) -> list[dict]:
        results = self.store.similarity_search_with_score(query, k=limit)
        out = []
        for doc, distance in results:
            m = doc.metadata
            out.append({
                **m,
                "content": doc.page_content,
                "score": round(1 - float(distance), 5),   # cosine distance -> similarity
            })
        return out
```

Ghi chú:
- Metadata trong Chroma chỉ nhận kiểu đơn giản (str/int/float/bool), nên `note`, `title` phải là chuỗi (không `None`). `knowledge.py` hiện đã ép về `str`.
- Text đem đi embed có ghép thêm `title` (đường dẫn heading) để chunk ngắn vẫn mang ngữ cảnh. Khi trả về FE, nên hiển thị phần `content` đã bỏ dòng title nếu muốn gọn.

## 5. Sửa `BE/knowledge.py`

### 5.1 Tách `chunks()` ra khỏi `retrieve()`

Đưa đoạn gom heading hiện nằm trong `retrieve()` thành method riêng, và cắt tiếp chunk quá dài:

```python
from langchain_text_splitters import RecursiveCharacterTextSplitter

CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "400"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "60"))

def chunks(self):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    result = []
    for chunk in self._heading_chunks():          # chính là đoạn append_chunk() cũ
        if len(chunk["content"]) <= CHUNK_SIZE:
            result.append(chunk)
        else:
            for part in splitter.split_text(chunk["content"]):
                result.append({**chunk, "content": part})
    return result
```

`_heading_chunks()` = phần vòng lặp `for filename, metadata, body in self.documents(): ...` trong `retrieve()` hiện tại (giữ nguyên logic, chỉ đổi thành method trả về list).

### 5.2 `retrieve()` ưu tiên vector, fallback lexical

```python
def __init__(self, data_dir: Path, rag_store=None):
    self.data_dir = data_dir
    self.rag_store = rag_store

def retrieve(self, query: str, limit: int = 4):
    if self.rag_store is not None:
        try:
            return self.rag_store.search(query, limit)
        except Exception:
            logger.exception("Vector search lỗi, dùng lexical")
    return self._lexical_retrieve(query, limit)   # code retrieve() cũ, đổi tên
```

Giữ lexical làm fallback và làm baseline để so sánh trong báo cáo đồ án.

### 5.3 Ngưỡng "không tìm thấy"

Lexical trả `[]` khi không khớp từ nào, nhờ vậy `answer()` nói "chưa tìm thấy". Vector search **luôn** trả k kết quả, kể cả câu hỏi ngoài phạm vi. Cần ngưỡng:

```python
MIN_SCORE = float(os.getenv("RAG_MIN_SCORE", "0.35"))
results = [r for r in results if r["score"] >= MIN_SCORE]
```

Giá trị 0.35 chỉ là điểm khởi đầu. Hiệu chỉnh bằng cách in `score` của bộ câu hỏi mẫu (trong phạm vi) và vài câu ngoài phạm vi, rồi chọn ngưỡng nằm giữa hai nhóm.

## 6. Embedding tiếng Việt: hai chỗ dễ sai

1. **Tách từ**: `bkai-foundation-models/vietnamese-bi-encoder` dựa trên PhoBERT, nên chất lượng tốt hơn khi văn bản đầu vào đã tách từ (`sinh_viên`, `ký_túc_xá`). Dùng `pyvi`:

   ```python
   from pyvi import ViTokenizer

   class SegmentedEmbeddings(HuggingFaceEmbeddings):
       def embed_documents(self, texts):
           return super().embed_documents([ViTokenizer.tokenize(t) for t in texts])
       def embed_query(self, text):
           return super().embed_query(ViTokenizer.tokenize(text))
   ```

   Dùng class này trong `build_embeddings`. Phải áp dụng **cả khi index lẫn khi query**, nếu không vector lệch nhau. Nên A/B có/không tách từ trên bộ câu hỏi mẫu.
2. **Độ dài tối đa**: nhiều bi-encoder kiểu này cắt ở 128 token. Kiểm tra `model.max_seq_length` (qua `embeddings._client.max_seq_length`). Nếu chunk 400 ký tự vượt quá, phần đuôi bị bỏ khi embed, lúc đó hạ `CHUNK_SIZE`.
3. Nếu đổi sang `intfloat/multilingual-e5-large`: thêm tiền tố `"passage: "` khi index và `"query: "` khi hỏi, không cần tách từ. Đổi model thì fingerprint tự đổi và index được build lại.

## 7. Sửa `BE/main.py`

Nạp model **một lần** lúc khởi động, không nạp trong từng request:

```python
def create_app(db_path=None, data_dir=None, rag_store=None):
    ...
    knowledge = Knowledge(data_dir or Path(...), rag_store=rag_store)

    @asynccontextmanager
    async def lifespan(app):
        database.initialize()
        if os.getenv("RETRIEVAL_BACKEND", "lexical") == "vector" and knowledge.rag_store is None:
            from rag_store import RagStore            # hoặc .rag_store khi chạy như package
            store = RagStore(Path(os.getenv("CHROMA_DIR", str(ROOT / "BE/chroma_db"))),
                             os.getenv("EMBEDDING_MODEL_NAME", "bkai-foundation-models/vietnamese-bi-encoder"))
            store.ensure_index(knowledge.chunks())
            knowledge.rag_store = store
        yield
```

Và trong `/api/health` đổi `"retrieval": "lexical"` thành `"vector" if knowledge.rag_store else "lexical"`.

Biến môi trường mới (thêm vào `.env.example`, không để key thật):

```
RETRIEVAL_BACKEND=vector          # vector | lexical (mặc định lexical, để test không phải tải model)
EMBEDDING_MODEL_NAME=bkai-foundation-models/vietnamese-bi-encoder
CHROMA_DIR=BE/chroma_db
CHUNK_SIZE=400
CHUNK_OVERLAP=60
RAG_MIN_SCORE=0.35
```

Mặc định `lexical` để các test hiện có (dùng `create_app(db_path, data_dir)`) không bị kéo model về.

## 8. Streaming (bước 5 trong sơ đồ, làm sau)

Hiện `POST /api/conversations/{id}/messages` trả về cả `Conversation`. Để có "Streamed response":
- Thêm endpoint SSE (`sse-starlette`) gọi `llm.stream(...)` thay cho `llm.invoke(...)`, gửi lần lượt event `token`, rồi `sources`, rồi `done`.
- Chỉ lưu vào SQLite **sau khi stream xong** (giữ đúng tính atomic của `save_turn`).
- FE cần thêm helper đọc SSE.

Đề nghị làm xong retrieval vector trước, streaming là bước riêng.

## 9. Lệnh build index thủ công (`BE/scripts/ingest.py`)

```python
from pathlib import Path
from knowledge import Knowledge
from rag_store import RagStore
import os

root = Path(__file__).resolve().parents[2]
k = Knowledge(Path(os.getenv("DATA_DIR", root / "data")))
store = RagStore(Path(os.getenv("CHROMA_DIR", root / "BE/chroma_db")),
                 os.getenv("EMBEDDING_MODEL_NAME", "bkai-foundation-models/vietnamese-bi-encoder"))
print("rebuilt" if store.ensure_index(k.chunks()) else "up-to-date")
```

Chạy trước khi demo để lần khởi động server không phải chờ embed. Trên Windows/PyCharm đặt biến môi trường trong Run Configuration.

## 10. Thứ tự làm và cách kiểm tra

1. Chốt chunk size / k (mục 2).
2. Tách `chunks()`, chạy lại như cũ, kiểm tra số chunk hợp lý (không có chunk rỗng, không chunk quá dài).
3. Thêm `rag_store.py` + `scripts/ingest.py`, chạy ingest, kiểm tra `chroma_db/` được tạo và chạy lần 2 báo `up-to-date`.
4. Viết script in top-k + score cho `SAMPLE_QUESTIONS` của `rag_demo.py`, so với kết quả lexical hiện tại.
5. Hiệu chỉnh `RAG_MIN_SCORE` bằng cả câu trong và ngoài phạm vi.
6. Nối vào `knowledge.retrieve()`, bật `RETRIEVAL_BACKEND=vector`, test qua Swagger `/docs`.
7. Cập nhật `/api/health`, FE hiển thị `score` nếu cần.
8. (Tuỳ chọn) A/B hai embedding model, A/B có/không tách từ, rồi mới làm streaming.

## 11. Lỗi thường gặp

| Triệu chứng | Nguyên nhân |
|---|---|
| Kết quả trùng lặp / số chunk tăng mỗi lần chạy | Dùng `from_documents` lặp lại; dùng `ensure_index` + `ids` cố định |
| `score` âm hoặc tăng khi kết quả càng tệ | Quên đổi khoảng cách thành độ tương đồng, hoặc không đặt `hnsw:space=cosine` |
| Câu ngoài phạm vi vẫn được trả lời kiểu "có vẻ liên quan" | Chưa có `RAG_MIN_SCORE` |
| Retrieval kém dù data đúng | Chưa tách từ, chunk vượt max token, hoặc index và query xử lý khác nhau |
| Đổi model nhưng kết quả lạ | Index cũ còn dùng vector của model trước; fingerprint đã gắn model name để tự rebuild |
| Khởi động server rất chậm | Model đang load hoặc đang embed lần đầu; chạy `ingest.py` trước |
