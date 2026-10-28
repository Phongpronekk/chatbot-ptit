from typing import Literal
import os
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class Source(BaseModel):
    source_file: str
    source_url: str
    fetched_date: str
    publish_date: str = ""
    topic_group: str
    title: str
    content: str
    note: str = ""
    score: float
    score_type: str = 'cosine_similarity'
    semantic_score: float | None = None
    lexical_score: float | None = None
    fusion_score: float | None = None


class Message(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    text: str
    created_at: str
    mode: Literal["user", "retrieval_only", "llm"]
    sources: list[Source] = Field(default_factory=list)


class ConversationSummary(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str


class Conversation(ConversationSummary):
    messages: list[Message]


class SendMessage(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    request_id: UUID

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Tin nhắn không được để trống")
        return value.strip()


class RagSearch(BaseModel):
    question: str = Field(min_length=1, max_length=4000, examples=['KTX B2 mức thu bao nhiêu?'])
    limit: int = Field(default_factory=lambda: int(os.getenv('RAG_TOP_K', '4')), ge=1, le=10, description='Số đoạn tài liệu trả về, mặc định RAG_TOP_K')

    @field_validator('question')
    @classmethod
    def nonempty_question(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('Câu hỏi không được để trống')
        return value.strip()
