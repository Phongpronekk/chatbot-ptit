import logging
import os
from collections import Counter
import time
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID, uuid4

import httpx

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# The backend's .env is the authoritative configuration, independent of cwd.
load_dotenv(Path(__file__).resolve().parent / ".env", override=True, encoding="utf-8-sig")

from dotenv import load_dotenv

# Load các biến từ file .env vào môi trường
load_dotenv()

if __package__:
    from .database import Database
    from .knowledge import Knowledge
    from .schemas import Conversation, ConversationSummary, SendMessage, Source, RagSearch
else:
    # `uvicorn main:app` / `python main.py` from inside BE.
    from database import Database
    from knowledge import Knowledge
    from schemas import Conversation, ConversationSummary, SendMessage, Source, RagSearch

ROOT = Path(__file__).resolve().parents[1]
logger = logging.getLogger(__name__)


def direct_ollama_enabled() -> bool:
    """Test mode: call Ollama without loading the knowledge index."""
    return os.getenv("DIRECT_OLLAMA_CHAT", "false").strip().lower() in ("1", "true", "yes")


def ask_ollama_direct(message: str) -> str:
    model = os.getenv("MODEL_NAME", "qwen2.5-coder:3b").strip()
    base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    if not model or model.endswith("-cloud"):
        raise RuntimeError("DIRECT_OLLAMA_CHAT requires a local Ollama model")
    with httpx.Client(timeout=httpx.Timeout(180.0, connect=5.0)) as client:
        response = client.post(
            f"{base_url}/api/chat",
            json={
                "model": model,
                "stream": False,
                "messages": [
                    {"role": "system", "content": "Bạn là trợ lý Chatbot PTIT. Trả lời bằng tiếng Việt. Khi thiếu dữ liệu chính thức, nói rõ bạn chưa xác minh được; không bịa quy định PTIT."},
                    {"role": "user", "content": message},
                ],
            },
        )
        response.raise_for_status()
        answer = response.json().get("message", {}).get("content", "").strip()
        if not answer:
            raise RuntimeError("Ollama returned an empty chat response")
        return answer



def normalize_conversation_modes(conversation):
    """Adapt legacy stored messages without modifying the SQLite database.

    Older direct-chat builds stored assistant messages with mode='general',
    while the public Conversation schema accepts 'llm' instead.
    """
    if conversation is None:
        return None
    data = conversation.model_dump() if hasattr(conversation, "model_dump") else dict(conversation)
    messages = []
    for item in data.get("messages", []):
        msg = item.model_dump() if hasattr(item, "model_dump") else dict(item)
        if msg.get("mode") == "general":
            msg["mode"] = "llm"
        messages.append(msg)
    data["messages"] = messages
    return data


def retrieval_disabled() -> bool:
    return direct_ollama_enabled()


def create_app(db_path: Path | None = None, data_dir: Path | None = None, rag_store=None) -> FastAPI:
    database = Database(db_path or Path(os.getenv("CHAT_DB_PATH", str(ROOT / "BE/storage/chat.sqlite3"))))
    knowledge = Knowledge(data_dir or Path(os.getenv("DATA_DIR", str(ROOT / "data"))), rag_store=rag_store)

    @asynccontextmanager
    async def lifespan(app):
        database.initialize()
        if direct_ollama_enabled():
            logger.warning("DIRECT_OLLAMA_CHAT enabled: skipping knowledge.prepare() and indexing")
        else:
            knowledge.prepare()
        yield
        if not direct_ollama_enabled():
            knowledge.close()

    app = FastAPI(title="PTIT Chatbot API", version="1.0.0", lifespan=lifespan)
    app.state.database = database
    app.state.knowledge = knowledge
    origins = [item.strip() for item in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://127.0.0.1:5174").split(",") if item.strip()]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True,
                       allow_methods=["GET", "POST", "DELETE"], allow_headers=["Content-Type"])

    @app.middleware("http")
    async def browser_session(request: Request, call_next):
        session = request.cookies.get("ptit_session", "")
        try:
            session = str(UUID(session))
        except (ValueError, AttributeError):
            session = str(uuid4())
        request.state.owner = session
        response = await call_next(request)
        if request.cookies.get("ptit_session") != session:
            response.set_cookie("ptit_session", session, httponly=True, samesite="lax",
                                secure=os.getenv("COOKIE_SECURE", "false").lower() == "true", max_age=60 * 60 * 24 * 30)
        return response

    @app.get("/api/health")
    def health_check():
        try:
            count = 0 if direct_ollama_enabled() else len(knowledge.sources())
        except (ValueError, OSError):
            return {"status": "degraded", "source_count": 0, "retrieval": knowledge.mode, "llm_configured": False}
        provider = os.getenv("LLM_PROVIDER", "ollama").strip().lower()
        key = "GOOGLE_API_KEY" if provider == "google" else "ANTHROPIC_API_KEY"
        configured = provider in ("google", "anthropic") and bool(os.getenv(key, "").strip() and os.getenv("MODEL_NAME", "").strip())
        if provider == "ollama":
            configured = not os.getenv("MODEL_NAME", "qwen2.5-coder:3b").strip().endswith("-cloud")
        model = os.getenv("MODEL_NAME", "").strip() or ("qwen2.5-coder:3b" if provider == "ollama" else "")
        active_vector = knowledge.rag_store is not None and knowledge.rag_store.store is not None
        return {"status": "ok" if (count or direct_ollama_enabled()) else "degraded", "source_count": count, "retrieval": 'disabled' if direct_ollama_enabled() else 'vector' if active_vector else 'lexical', "llm_configured": configured,
                "llm_provider": provider, "llm_model": model,
                "embedding_model": knowledge.rag_store.model_name if active_vector else None,
                "indexed_chunks": knowledge.rag_store.manifest['chunk_count'] if active_vector else 0,
                "search_strategy": 'disabled' if direct_ollama_enabled() else 'hybrid' if active_vector and os.getenv('RETRIEVAL_HYBRID', 'true').lower() in ('true', '1', 'yes') else 'vector' if active_vector else 'bm25',
                'retrieval_warning': knowledge.last_retrieval_error}

    @app.get("/api/knowledge/sources")
    def list_sources():
        if retrieval_disabled():
            return []
        try:
            return knowledge.sources()
        except (ValueError, OSError):
            raise HTTPException(503, "Kho dữ liệu chưa sẵn sàng")

    @app.get('/api/rag/status', tags=['RAG'], summary='Xem cấu hình và chỉ mục RAG')
    def rag_status():
        """Thông tin thực tế của backend: model embedding, chia đoạn, số vector,
        nhóm tài liệu và model tạo câu trả lời. Không hiển thị API key.
        """
        if retrieval_disabled():
            return {
                "retrieval_mode": "disabled", "requested_backend": knowledge.mode,
                "fallback_warning": "Direct Ollama mode: RAG indexing disabled",
                "document_count": 0, "topic_groups": {},
                "index": {"ready": False, "chunk_count": 0, "embedding_model": None,
                          "dimensions": None, "chunk_size_characters": None,
                          "overlap_characters": None, "built_at": None,
                          "collection": None, "storage": "ChromaDB (cosine)"},
                "generation": {"provider": os.getenv("LLM_PROVIDER", "ollama"),
                               "model": os.getenv("MODEL_NAME", "")},
                "pipeline": ["Direct Ollama chat (RAG disabled)"],
            }
        try:
            sources = knowledge.sources()
            search = knowledge.rag_store
            manifest = search.manifest if search else None
            return {
                'retrieval_mode': 'vector' if search and search.store else 'lexical',
                'requested_backend': knowledge.mode,
                'fallback_warning': knowledge.last_retrieval_error,
                'document_count': len(sources),
                'topic_groups': dict(Counter(s['topic_group'] for s in sources)),
                'index': {
                    'ready': bool(search and search.store),
                    'chunk_count': manifest['chunk_count'] if manifest else 0,
                    'embedding_model': manifest['config']['model'] if manifest else None,
                    'dimensions': manifest.get('embedding_dimensions') if manifest else None,
                    'chunk_size_characters': manifest['config']['chunk_size'] if manifest else None,
                    'overlap_characters': manifest['config']['overlap'] if manifest else None,
                    'built_at': manifest['built_at'] if manifest else None,
                    'collection': manifest['collection'] if manifest else None,
                    'storage': 'ChromaDB (cosine)',
                    'min_score': float(os.getenv('RAG_MIN_SCORE', '0.35')),
                    'top_k': int(os.getenv('RAG_TOP_K', '4')),
                },
                'generation': {'provider': os.getenv('LLM_PROVIDER', 'ollama'),
                               'model': os.getenv('MODEL_NAME', '')},
                'search_strategy': 'hybrid' if os.getenv('RETRIEVAL_HYBRID', 'true').lower() in ('true', '1', 'yes') and search and search.store else 'single_backend',
                'pipeline': ['Đọc và chia tài liệu', 'Embedding tài liệu (offline)',
                             'Chuẩn hóa Unicode, khoảng trắng và thuật ngữ viết tắt',
                             'Embedding câu hỏi (local)', 'Chroma cosine + BM25 không dấu khi bật hybrid',
                             'Lọc bằng chứng; hợp nhất thứ hạng RRF khi bật hybrid; lấy top-k',
                             'Ghép tài liệu vào prompt', 'LLM tạo câu trả lời có nguồn'],
            }
        except (ValueError, OSError):
            raise HTTPException(503, 'Kho dữ liệu RAG chưa sẵn sàng')

    @app.post('/api/rag/search', tags=['RAG'], summary='Thử tìm kiếm và xem chi tiết từng bước')
    def rag_search(payload: RagSearch):
        """Bấm **Try it out**, nhập question và limit rồi Execute.

        Trả truy vấn đã chuẩn hóa, preview vector, thời gian từng bước,
        ứng viên cosine/BM25, hợp nhất thứ hạng và đoạn được chọn cùng URL nguồn.
        Đây là cùng bộ tìm kiếm dùng trong chat; không gọi LLM, không lưu hội thoại.
        Kiểm tra score_type: cosine_similarity hoặc bm25; fusion_score là điểm RRF.
        Các thang điểm này không phải xác suất đúng và không so sánh trực tiếp với nhau.
        """
        if retrieval_disabled():
            raise HTTPException(503, "RAG đang tắt trong chế độ DIRECT_OLLAMA_CHAT")
        started = time.perf_counter()
        trace = {}
        try:
            sources = knowledge.retrieve(payload.question, payload.limit, trace=trace)
            return {'question': payload.question, 'retrieval_mode': trace['backend_used'],
                    'elapsed_ms': round((time.perf_counter() - started) * 1000, 3),
                    'llm_called': False, 'diagnostics': trace,
                    'sources': sources}
        except (ValueError, OSError, RuntimeError):
            logger.exception('RAG search failed')
            raise HTTPException(503, 'Không tìm kiếm được. Kiểm tra chỉ mục RAG và dữ liệu.')

    @app.get("/api/conversations", response_model=list[ConversationSummary])
    def list_conversations(request: Request):
        return database.list(request.state.owner)

    @app.post("/api/conversations", response_model=Conversation, status_code=201)
    def create_conversation(request: Request):
        return normalize_conversation_modes(database.create(request.state.owner))

    def require_conversation(identifier: UUID, request: Request):
        conversation = database.get(str(identifier), request.state.owner)
        if conversation is None:
            raise HTTPException(404, "Không tìm thấy cuộc trò chuyện")
        return normalize_conversation_modes(conversation)

    @app.get("/api/conversations/{identifier}", response_model=Conversation)
    def get_conversation(identifier: UUID, request: Request):
        return require_conversation(identifier, request)

    @app.delete("/api/conversations/{identifier}", status_code=204)
    def delete_conversation(identifier: UUID, request: Request):
        if not database.delete(str(identifier), request.state.owner):
            raise HTTPException(404, "Không tìm thấy cuộc trò chuyện")
        return Response(status_code=204)

    @app.post("/api/conversations/{identifier}/messages", response_model=Conversation)
    def send_message(identifier: UUID, payload: SendMessage, request: Request):
        require_conversation(identifier, request)
        request_id = str(payload.request_id)
        if database.has_request(str(identifier), request_id):
            return require_conversation(identifier, request)
        try:
            if direct_ollama_enabled():
                answer, mode, sources = ask_ollama_direct(payload.message), "llm", []
            else:

                answer, mode, sources = knowledge.answer(payload.message)
            # Validate response before persisting a complete turn atomically.
            sources = [Source.model_validate(source).model_dump() for source in sources]
        except Exception as exc:
            logger.exception("Không thể trả lời tin nhắn (%s): %s", type(exc).__name__, exc)
            raise HTTPException(503, "Dịch vụ trả lời chưa sẵn sàng. Vui lòng kiểm tra dữ liệu/cấu hình LLM hoặc thử lại sau.")
        conversation = database.save_turn(str(identifier), request.state.owner, request_id,
                                          payload.message, answer, mode, sources)
        if conversation is None:
            raise HTTPException(404, "Cuộc trò chuyện đã bị xóa")
        return normalize_conversation_modes(conversation)

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
