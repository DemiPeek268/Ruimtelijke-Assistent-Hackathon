import uuid

from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    model: str = "gpt-5-chat"
    session_id: uuid.UUID | None = None
