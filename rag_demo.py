# %% [markdown]
# # PTIT Chatbot - RAG Demo (Person C: CLB / Quy chế chung / KTX / Thư viện / Thực tập-Việc làm)
#
# Kiến trúc theo đúng sơ đồ RAG Workflow chuẩn:
#
#   Bước tiền xử lý (offline, chạy 1 lần khi có dữ liệu mới):
#     Knowledge Base (data/*.md) --chunking--> Chunks --embedding--> Vector Database (Chroma)
#
#   Bước phục vụ truy vấn (online, mỗi lần user hỏi):
#     User Query --embed query--> tìm Similar Vectors trong Vector DB --> Context
#     Context + Query --> Prompt --> LLM --> Streamed response --> User
#
# Dữ liệu: snapshot thủ công 3 nguồn chính thức PTIT (cơ sở Hà Nội), xem front-matter
# trong từng file data/*.md để biết source_url + fetched_date.

# %%
import os
import sys
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
CHROMA_DIR = Path(__file__).parent / "chroma_db"

# %% [markdown]
# ## Bước 1: Load Knowledge Base
#
# Đọc toàn bộ file .md trong data/. Mỗi file có front-matter YAML (source_url,
# fetched_date, topic_group...) — ta tách phần front-matter ra làm metadata,
# phần còn lại là nội dung thật sẽ được chunk.

# %%
from langchain_core.documents import Document


def load_markdown_with_frontmatter(path: Path) -> Document:
    """Đọc 1 file .md, tách front-matter YAML (--- ... ---) thành metadata."""
    text = path.read_text(encoding="utf-8")
    metadata = {"source_file": path.name}

    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            front_matter_raw = parts[1].strip()
            body = parts[2].strip()
            for line in front_matter_raw.splitlines():
                if ":" in line:
                    key, _, value = line.partition(":")
                    metadata[key.strip()] = value.strip()
            text = body

    return Document(page_content=text, metadata=metadata)


def load_knowledge_base(data_dir: Path) -> list[Document]:
    docs = []
    for path in sorted(data_dir.glob("*.md")):
        docs.append(load_markdown_with_frontmatter(path))
    return docs


raw_docs = load_knowledge_base(DATA_DIR)
print(f"[Knowledge Base] Đã load {len(raw_docs)} file:")
for d in raw_docs:
    print(f"  - {d.metadata.get('source_file')} | topic_group={d.metadata.get('topic_group')} "
          f"| {len(d.page_content)} ký tự")

# %% [markdown]
# ## Bước 2: Chunking
#
# chunk_size=400, chunk_overlap=60 (đã thống nhất trong nhóm). Dùng
# RecursiveCharacterTextSplitter với separators ưu tiên theo cấu trúc Markdown
# (##, \n\n, \n) để chunk không cắt ngang giữa các mục/điều.

# %%
from langchain_text_splitters import RecursiveCharacterTextSplitter

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=600,
    chunk_overlap=100,
    separators=["\n## ", "\n### ", "\n\n", "\n", ". ", " ", ""],
)

chunks = text_splitter.split_documents(raw_docs)
print(f"\n[Chunking] {len(raw_docs)} tài liệu -> {len(chunks)} chunks")
print("Ví dụ chunk đầu tiên:")
print("-" * 60)
print(chunks[0].page_content[:300])
print("-" * 60)

# %% [markdown]
# ## Bước 3: Embedding + Vector Database
#
# Dùng embedding model tiếng Việt: bkai-foundation-models/vietnamese-bi-encoder.
# (Có thể đổi sang intfloat/multilingual-e5-large để so sánh chất lượng retrieval
# - xem ghi chú cuối file.)
#
# Vector DB: ChromaDB, lưu persistent tại ./chroma_db để không phải embed lại
# mỗi lần chạy.

# %%
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma

EMBEDDING_MODEL_NAME = "bkai-foundation-models/vietnamese-bi-encoder"

print(f"\n[Embedding] Đang load model: {EMBEDDING_MODEL_NAME} ...")
embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL_NAME)

print("[Vector DB] Đang tạo/nạp ChromaDB ...")
vectorstore = Chroma.from_documents(
    documents=chunks,
    embedding=embeddings,
    persist_directory=str(CHROMA_DIR),
    collection_name="ptit_person_c",
)
print(f"[Vector DB] Đã lưu {len(chunks)} vectors vào {CHROMA_DIR}")

# %% [markdown]
# ## Bước 4: Retriever
#
# Retriever tìm k=4 chunks gần nhất về mặt ngữ nghĩa với câu hỏi (Similar Vectors
# trong sơ đồ). Đây là bước "Retriever fetches information relevant to the query".

# %%
retriever = vectorstore.as_retriever(search_kwargs={"k": 5})


def demo_retrieval(query: str):
    """Chạy thử riêng bước retrieval để xem context được lấy ra là gì
    (hữu ích khi chưa có API key, hoặc khi cần debug chất lượng retrieval)."""
    results = retriever.invoke(query)
    print(f"\n>>> Query: {query}")
    print(f"Tìm được {len(results)} chunks liên quan:")
    for i, doc in enumerate(results, 1):
        source = doc.metadata.get("source_file", "?")
        print(f"\n  [{i}] (nguồn: {source})")
        print(f"      {doc.page_content[:200]}...")
    return results


# %% [markdown]
# ## Bước 5: Augment prompt + LLM (Prompt = Context + Query)
#
# Đây chính là bước 3-4 trong sơ đồ: "Relevant information is augmented to the
# prompt as context" rồi "LLM generates a response to the prompt".
#
# Chain LCEL: retriever | format context -> prompt -> LLM -> output parser

# %%
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

PROMPT_TEMPLATE = """Bạn là trợ lý ảo hỗ trợ sinh viên PTIT (Học viện Công nghệ Bưu chính Viễn thông), \
trả lời các câu hỏi về CLB, Quy chế chung, Ký túc xá, Thư viện, Thực tập/Việc làm.

Chỉ trả lời dựa trên phần "Ngữ cảnh" dưới đây. Nếu ngữ cảnh không có đủ thông tin để trả lời, \
hãy nói rõ là chưa có thông tin, không được bịa đặt.

Ngữ cảnh:
{context}

Câu hỏi: {question}

Trả lời (ngắn gọn, chính xác, bằng tiếng Việt):"""

prompt = ChatPromptTemplate.from_template(PROMPT_TEMPLATE)


def format_docs(docs: list[Document]) -> str:
    parts = []
    for doc in docs:
        source = doc.metadata.get("source_file", "?")
        parts.append(f"[Nguồn: {source}]\n{doc.page_content}")
    return "\n\n---\n\n".join(parts)


def build_llm():
    """Chọn LLM provider qua biến môi trường LLM_PROVIDER (mặc định: anthropic).

    - LLM_PROVIDER=anthropic (mặc định): cần ANTHROPIC_API_KEY.
      MODEL_NAME mặc định: claude-sonnet-4-6
    - LLM_PROVIDER=google: cần GOOGLE_API_KEY (lấy free tại aistudio.google.com,
      dùng được với gói Gemini cho sinh viên).
      MODEL_NAME mặc định: gemini-3.5-flash
      (Gemini 2.5 sẽ ngừng hoạt động 10/2026, không dùng để tránh gián đoạn giữa đồ án.)
    """
    provider = os.environ.get("LLM_PROVIDER", "anthropic").lower()

    if provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI

        model_name = os.environ.get("MODEL_NAME", "gemini-3.5-flash")
        print(f"[LLM] Dùng Google Gemini: {model_name}")
        return ChatGoogleGenerativeAI(model=model_name, temperature=0)

    from langchain_anthropic import ChatAnthropic

    model_name = os.environ.get("MODEL_NAME", "claude-sonnet-4-6")
    print(f"[LLM] Dùng Anthropic Claude: {model_name}")
    return ChatAnthropic(model=model_name, temperature=0)


def build_rag_chain():
    llm = build_llm()

    chain = (
        {"context": retriever | format_docs, "question": RunnablePassthrough()}
        | prompt
        | llm
        | StrOutputParser()
    )
    return chain


# %% [markdown]
# ## Chạy demo
#
# LLM_PROVIDER quyết định dùng Claude hay Gemini (xem docstring build_llm()).
# Nếu API key tương ứng chưa được set: chỉ chạy tới bước Retriever, in ra
# context tìm được, để vẫn kiểm chứng được chất lượng chunking + embedding +
# vector search mà không cần gọi LLM.

# %%
SAMPLE_QUESTIONS = [
    "Sinh viên năm nhất ở KTX B2 phải đóng bao nhiêu tiền một tháng?",
    "Em làm mất thẻ thư viện thì phải làm gì?",
    "PTIT có CLB nào về lập trình hoặc công nghệ thông tin không?",
    "Sinh viên chính quy được mượn tối đa bao nhiêu cuốn sách ở phòng mượn?",
]

REQUIRED_KEY_BY_PROVIDER = {
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GOOGLE_API_KEY",
}

if __name__ == "__main__":
    provider = os.environ.get("LLM_PROVIDER", "anthropic").lower()
    required_key_name = REQUIRED_KEY_BY_PROVIDER.get(provider, "ANTHROPIC_API_KEY")
    api_key = os.environ.get(required_key_name)
    has_llm = bool(api_key)

    if not has_llm:
        print("\n" + "=" * 70)
        print(f"LLM_PROVIDER={provider} nhưng không tìm thấy {required_key_name}.")
        print("-> Chỉ chạy tới bước Retriever (không gọi LLM).")
        print("=" * 70)
    else:
        print("\n" + "=" * 70)
        print(f"LLM_PROVIDER={provider}, đã tìm thấy {required_key_name} -> full RAG pipeline.")
        print("=" * 70)
        rag_chain = build_rag_chain()

    # --- Chạy bộ câu hỏi mẫu trước (để có baseline tham khảo) ---
    print("\n>>> CHẠY BỘ CÂU HỎI MẪU <<<")
    for q in SAMPLE_QUESTIONS:
        if has_llm:
            print(f"\n>>> Câu hỏi: {q}")
            answer = rag_chain.invoke(q)
            print(f"Trả lời: {answer}")
        else:
            demo_retrieval(q)

    # --- Chế độ nhập câu hỏi tự do từ bàn phím ---
    print("\n" + "=" * 70)
    print("CHẾ ĐỘ NHẬP CÂU HỎI TỰ DO")
    print("Gõ câu hỏi rồi Enter. Gõ 'exit', 'quit' hoặc để trống rồi Enter để thoát.")
    print("=" * 70)

    while True:
        try:
            user_question = input("\nCâu hỏi của bạn: ").strip()
        except EOFError:
            # Một số môi trường (ví dụ chạy không có stdin tương tác) sẽ raise EOFError
            print("\n(Không có input tương tác - dừng vòng lặp.)")
            break

        if not user_question or user_question.lower() in ("exit", "quit", "q"):
            print("Kết thúc.")
            break

        if has_llm:
            answer = rag_chain.invoke(user_question)
            print(f"Trả lời: {answer}")
        else:
            demo_retrieval(user_question)

# %% [markdown]
# ## Ghi chú mở rộng
#
# - **So sánh embedding model**: đổi `EMBEDDING_MODEL_NAME` thành
#   `"intfloat/multilingual-e5-large"` để so sánh chất lượng retrieval trên
#   cùng bộ câu hỏi mẫu ở trên.
# - **Thêm dữ liệu mới**: chỉ cần thêm file .md vào thư mục `data/` (đúng format
#   front-matter như các file hiện có) rồi chạy lại script - Chroma sẽ tự thêm
#   (embed lại) — nếu muốn tránh trùng lặp khi rerun, có thể xóa thư mục
#   `chroma_db/` trước khi chạy lại.
# - **Router / nhánh SQL**: script này là nhánh RAG độc lập, sẽ được ghép vào
#   RunnableBranch tổng khi nhóm hoàn thiện router.