import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware

if __package__:
    from .database import Database
    from .knowledge import Knowledge
    from .schemas import Conversation, ConversationSummary, SendMessage, Source
else:
    # `uvicorn main:app` / `python main.py` from inside BE.
    from database import Database
    from knowledge import Knowledge
    from schemas import Conversation, ConversationSummary, SendMessage, Source

ROOT = Path(__file__).resolve().parents[1]
logger = logging.getLogger(__name__)


def create_app(db_path: Path | None = None, data_dir: Path | None = None) -> FastAPI:
    database = Database(db_path or Path(os.getenv("CHAT_DB_PATH", str(ROOT / "BE/storage/chat.sqlite3"))))
    knowledge = Knowledge(data_dir or Path(os.getenv("DATA_DIR", str(ROOT / "data"))))

    @asynccontextmanager
    async def lifespan(app):
        database.initialize()
        yield

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
            count = len(knowledge.sources())
        except (ValueError, OSError):
            return {"status": "degraded", "source_count": 0, "retrieval": "lexical", "llm_configured": False}
        provider = os.getenv("LLM_PROVIDER", "anthropic").strip().lower()
        key = "GOOGLE_API_KEY" if provider == "google" else "ANTHROPIC_API_KEY"
        configured = provider in ("google", "anthropic") and bool(os.getenv(key, "").strip() and os.getenv("MODEL_NAME", "").strip())
        return {"status": "ok" if count else "degraded", "source_count": count, "retrieval": "lexical", "llm_configured": configured}

    @app.get("/api/knowledge/sources")
    def list_sources():
        try:
            return knowledge.sources()
        except (ValueError, OSError):
            raise HTTPException(503, "Kho dữ liệu chưa sẵn sàng")

    @app.get("/api/conversations", response_model=list[ConversationSummary])
    def list_conversations(request: Request):
        return database.list(request.state.owner)

    @app.post("/api/conversations", response_model=Conversation, status_code=201)
    def create_conversation(request: Request):
        return database.create(request.state.owner)

    def require_conversation(identifier: UUID, request: Request):
        conversation = database.get(str(identifier), request.state.owner)
        if conversation is None:
            raise HTTPException(404, "Không tìm thấy cuộc trò chuyện")
        return conversation

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
            answer, mode, sources = knowledge.answer(payload.message)
            # Validate response before persisting a complete turn atomically.
            sources = [Source.model_validate(source).model_dump() for source in sources]
        except Exception:
            logger.exception("Không thể trả lời tin nhắn")
            raise HTTPException(503, "Dịch vụ trả lời chưa sẵn sàng. Vui lòng kiểm tra dữ liệu/cấu hình LLM hoặc thử lại sau.")
        conversation = database.save_turn(str(identifier), request.state.owner, request_id,
                                          payload.message, answer, mode, sources)
        if conversation is None:
            raise HTTPException(404, "Cuộc trò chuyện đã bị xóa")
        return conversation

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
