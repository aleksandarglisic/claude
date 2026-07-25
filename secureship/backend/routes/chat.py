import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from db.session import get_db
from llm.ollama_client import chat as ollama_chat, health_check
from models.chat_session import ChatSession, SessionState

router = APIRouter(prefix="/chat", tags=["chat"])

SYSTEM_PROMPT = """You are a helpful customer support assistant for SecureShip, a parcel delivery service.
You help customers check on their shipments and answer general shipping questions.
Be friendly, concise, and professional.

Note: Identity verification is not yet active. You may answer general shipping questions freely.
"""


class MessageIn(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    history: list[MessageIn] = []


class ToolCall(BaseModel):
    name: str
    arguments: dict


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    tool_calls: list[ToolCall] = []


@router.post("", response_model=ChatResponse)
async def send_message(body: ChatRequest, db: AsyncSession = Depends(get_db)) -> ChatResponse:
    if not await health_check():
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="LLM service unavailable")

    # Load or create ChatSession
    session_id = body.session_id or str(uuid.uuid4())
    result = await db.execute(select(ChatSession).where(ChatSession.id == session_id))
    chat_session = result.scalar_one_or_none()

    if chat_session is None:
        chat_session = ChatSession(
            id=session_id,
            state=SessionState.anonymous,
            transcript=[],
        )
        db.add(chat_session)

    # Build message list for Ollama from persisted transcript
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for entry in chat_session.transcript:
        messages.append({"role": entry["role"], "content": entry["content"]})
    messages.append({"role": "user", "content": body.message})

    result_llm = await ollama_chat(messages=messages)

    msg = result_llm.get("message", {})
    reply = msg.get("content", "")
    raw_tool_calls = msg.get("tool_calls", [])

    tool_calls = [
        ToolCall(
            name=tc["function"]["name"],
            arguments=tc["function"].get("arguments", {}),
        )
        for tc in raw_tool_calls
    ]

    # Persist both turns to transcript
    now = datetime.now(timezone.utc).isoformat()
    new_entries = [
        {"role": "user", "content": body.message, "timestamp": now},
        {
            "role": "assistant",
            "content": reply,
            "timestamp": now,
            "tool_calls": [{"name": tc.name, "arguments": tc.arguments} for tc in tool_calls],
        },
    ]
    # JSONB column requires reassignment to trigger SQLAlchemy change detection
    chat_session.transcript = chat_session.transcript + new_entries
    await db.commit()

    return ChatResponse(reply=reply, session_id=session_id, tool_calls=tool_calls)
