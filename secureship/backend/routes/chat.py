from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from llm.ollama_client import chat as ollama_chat, health_check

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
async def send_message(body: ChatRequest) -> ChatResponse:
    if not await health_check():
        raise HTTPException(status_code=503, detail="LLM service unavailable")

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in body.history:
        messages.append({"role": m.role, "content": m.content})
    messages.append({"role": "user", "content": body.message})

    result = await ollama_chat(messages=messages)

    msg = result.get("message", {})
    reply = msg.get("content", "")
    raw_tool_calls = msg.get("tool_calls", [])

    tool_calls = [
        ToolCall(
            name=tc["function"]["name"],
            arguments=tc["function"].get("arguments", {}),
        )
        for tc in raw_tool_calls
    ]

    import uuid
    session_id = body.session_id or str(uuid.uuid4())

    return ChatResponse(reply=reply, session_id=session_id, tool_calls=tool_calls)
