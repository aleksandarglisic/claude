import re
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from db.session import get_db
from llm.ollama_client import chat as ollama_chat, health_check
from models.chat_session import ChatSession, SessionState
from models.customer import Customer
from tools.identity import (
    TOOL_DEFINITIONS,
    handle_request_identity_info,
    handle_verify_identity,
    handle_send_verification_code,
)

router = APIRouter(prefix="/chat", tags=["chat"])

ESCALATION_KEYWORDS = [
    "talk to a human",
    "speak to a human",
    "real person",
    "human agent",
    "live agent",
    "live support",
    "speak to someone",
    "talk to someone",
    "connect me to",
    "transfer me",
    "get a human",
    "need a human",
    "want a human",
    "escalate",
    "supervisor",
]


def _is_escalation(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in ESCALATION_KEYWORDS)


def _strip_thinking(text: str) -> str:
    """Remove qwen3 <think>…</think> reasoning blocks that Ollama may include in content."""
    return re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL).strip()


def _build_system_prompt(state: SessionState, first_name: str | None = None) -> str:
    base = (
        "You are SecureShip, a friendly customer support assistant for a parcel delivery service. "
        "Be warm, concise, and natural. Never fabricate tracking numbers or shipment data."
    )

    if state == SessionState.anonymous:
        return base + (
            "\n\n"
            "You can freely answer general shipping questions (policies, delivery timeframes, carriers) "
            "without any verification.\n\n"
            "If the user asks about their specific shipments or account data, you must verify their "
            "identity first. Two ways to proceed:\n"
            "• If the user has already provided their full name, home address, AND phone number in this "
            "message — call verify_identity() immediately with those details.\n"
            "• Otherwise call request_identity_info() first (this signals the backend), then ask them "
            "in a single natural sentence for their full name, home address, and phone number. "
            "Do NOT list the fields as a form — just ask conversationally."
        )

    if state == SessionState.collecting_identity:
        return base + (
            "\n\n"
            "You are currently verifying this user's identity. You need four pieces of information: "
            "first name, last name, home address (street number + name, city, state), and phone number.\n\n"
            "Guidelines:\n"
            "• The user may give some or all details in a single message — extract whatever they've "
            "provided and ask only for what's still missing.\n"
            "• Do NOT prompt for one field at a time. Invite them to share everything at once.\n"
            "• Once you have all four pieces, call verify_identity() immediately — no confirmation needed.\n"
            "• If verification fails, say plainly that you couldn't verify their information and invite "
            "them to try again. Never hint which specific field was wrong."
        )

    if state in (SessionState.code_sent, SessionState.awaiting_code):
        return base + (
            "\n\n"
            "A 6-digit verification code has been sent. Tell the user to enter it in the verification "
            "box that appeared on screen — do NOT ask them to type the code in this chat.\n"
            "If they say they didn't receive it, call send_verification_code() to issue a new one."
        )

    if state == SessionState.verified:
        name_part = f" {first_name}" if first_name else ""
        return base + (
            f"\n\nThe user{name_part} is fully verified. Help them with any shipment questions. "
            "Shipment lookup tools will be wired in the next phase — for now acknowledge their "
            "questions and let them know you're looking into it."
        )

    if state == SessionState.escalated_to_human:
        return base + (
            "\n\nThis session has been escalated to human support. You are now acting as Melany, "
            "a human support agent. Be warm and empathetic. You still cannot provide shipment "
            "data to an unverified visitor — the same identity gate applies."
        )

    return base


async def _execute_tool(name: str, arguments: dict, session: ChatSession, db: AsyncSession) -> dict:
    if name == "request_identity_info":
        return await handle_request_identity_info(session, db)
    if name == "verify_identity":
        return await handle_verify_identity(
            session,
            db,
            first_name=arguments.get("first_name", ""),
            last_name=arguments.get("last_name", ""),
            address=arguments.get("address", ""),
            phone_number=arguments.get("phone_number", ""),
        )
    if name == "send_verification_code":
        return await handle_send_verification_code(session, db)
    return {"error": f"Unknown tool: {name}"}


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
    show_modal: bool = False
    session_state: str = "anonymous"
    escalated: bool = False
    known_first_name: str | None = None


@router.post("", response_model=ChatResponse)
async def send_message(body: ChatRequest, db: AsyncSession = Depends(get_db)) -> ChatResponse:
    if not await health_check():
        raise HTTPException(status_code=503, detail="LLM service unavailable")

    session_id = body.session_id or str(uuid.uuid4())
    result = await db.execute(select(ChatSession).where(ChatSession.id == session_id))
    chat_session = result.scalar_one_or_none()

    if chat_session is None:
        chat_session = ChatSession(id=session_id, state=SessionState.anonymous, transcript=[])
        db.add(chat_session)
        await db.flush()

    # Resolve known first name for system prompt personalisation
    known_first_name: str | None = None
    cust_id = chat_session.customer_id or chat_session.pending_customer_id
    if cust_id:
        cust_result = await db.execute(select(Customer).where(Customer.id == cust_id))
        customer = cust_result.scalar_one_or_none()
        if customer:
            known_first_name = customer.first_name

    # Handle escalation before touching Ollama
    if _is_escalation(body.message) and chat_session.state != SessionState.escalated_to_human:
        chat_session.state = SessionState.escalated_to_human
        reply = "Thank you for your patience. Connecting you with a human agent now."
        now = datetime.now(timezone.utc).isoformat()
        chat_session.transcript = chat_session.transcript + [
            {"role": "user", "content": body.message, "timestamp": now},
            {"role": "assistant", "content": reply, "timestamp": now, "tool_calls": []},
        ]
        await db.commit()
        return ChatResponse(
            reply=reply,
            session_id=session_id,
            session_state=SessionState.escalated_to_human.value,
            escalated=True,
            known_first_name=known_first_name,
        )

    system_prompt = _build_system_prompt(chat_session.state, known_first_name)

    # Rebuild conversation from persisted transcript (skip tool_calls — content is enough for history)
    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    for entry in chat_session.transcript:
        messages.append({"role": entry["role"], "content": entry.get("content", "")})
    messages.append({"role": "user", "content": body.message})

    show_modal = False
    executed_tool_calls: list[dict] = []
    reply = ""
    state_before = chat_session.state

    # Tool execution loop — max 5 rounds to prevent runaway recursion
    for _ in range(5):
        # Rebuild system prompt each iteration so state transitions are reflected immediately
        messages[0] = {"role": "system", "content": _build_system_prompt(chat_session.state, known_first_name)}

        result_llm = await ollama_chat(messages=messages, tools=TOOL_DEFINITIONS)
        msg = result_llm.get("message", {})
        reply = _strip_thinking(msg.get("content", "") or "")
        raw_tool_calls = msg.get("tool_calls", [])

        if not raw_tool_calls:
            break

        # Execute every tool the model requested
        tool_results = []
        for tc in raw_tool_calls:
            fn = tc.get("function", {})
            name = fn.get("name", "")
            args = fn.get("arguments", {})
            tool_result = await _execute_tool(name, args, chat_session, db)
            tool_results.append(tool_result)
            executed_tool_calls.append({"name": name, "arguments": args, "result": tool_result})

        # Detect code_sent transition for modal trigger
        if chat_session.state == SessionState.code_sent and state_before != SessionState.code_sent:
            show_modal = True
        state_before = chat_session.state

        # Refresh known_first_name if a customer was just resolved
        if not known_first_name and chat_session.pending_customer_id:
            cust_result2 = await db.execute(select(Customer).where(Customer.id == chat_session.pending_customer_id))
            cust2 = cust_result2.scalar_one_or_none()
            if cust2:
                known_first_name = cust2.first_name

        # Feed assistant tool-call message + tool results back into the conversation
        messages.append(msg)
        for i, tc in enumerate(raw_tool_calls):
            messages.append({"role": "tool", "content": str(tool_results[i])})

    # Persist both turns
    now = datetime.now(timezone.utc).isoformat()
    chat_session.transcript = chat_session.transcript + [
        {"role": "user", "content": body.message, "timestamp": now},
        {
            "role": "assistant",
            "content": reply,
            "timestamp": now,
            "tool_calls": executed_tool_calls,
        },
    ]
    await db.commit()

    return ChatResponse(
        reply=reply,
        session_id=session_id,
        tool_calls=[ToolCall(name=tc["name"], arguments=tc["arguments"]) for tc in executed_tool_calls],
        show_modal=show_modal,
        session_state=chat_session.state.value,
        escalated=False,
        known_first_name=known_first_name,
    )
