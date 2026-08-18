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
    IDENTITY_TOOLS,
    handle_request_identity_info,
    handle_verify_identity,
    handle_send_verification_code,
    handle_check_verification_code,
)
from tools.shipments import SHIPMENT_TOOLS, handle_lookup_shipments, handle_get_shipment_details

router = APIRouter(prefix="/chat", tags=["chat"])

# Tool calls whose arguments are redacted in the transcript (PII).
_PII_TOOLS = frozenset({"verify_identity"})

# Shipment tool results are NOT replayed into conversation history.
# Their data changes (admin edits packages/status), so replaying a stale result
# causes the model to answer from old data instead of calling the tool again.
# The assistant's text reply already carries the summary; omitting the raw
# tool result here forces a fresh DB query on every new question.
_NO_REPLAY_TOOLS = frozenset({"lookup_shipments", "get_shipment_details"})

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
            "A 6-digit verification code has been sent. Direct the user to the verification box "
            "that appeared on screen — that is the preferred way to enter the code.\n"
            "If the user types a 6-digit code directly in this chat, call check_verification_code() with it.\n"
            "If they didn't receive the code, the code expired, or they were locked out after too many "
            "attempts, call send_verification_code() to issue a fresh code."
        )

    if state == SessionState.verified:
        name_part = f" {first_name}" if first_name else ""
        return base + (
            f"\n\nIMPORTANT: The user{name_part} has already completed identity verification. "
            "Do NOT ask for their name, address, phone number, or any verification code again. "
            "Treat them as fully verified for this entire session.\n\n"
            "You have two tools for shipment data:\n"
            "• lookup_shipments() — call this for general questions ('where are my packages?', "
            "'what shipments do I have?'). Returns all shipments with status and estimated delivery.\n"
            "• get_shipment_details(tracking_number) — call this when the user asks about a specific "
            "tracking number or wants full detail on one shipment, including package contents.\n\n"
            "CRITICAL: You MUST call the appropriate tool every single time the user asks about "
            "shipments or packages — even if you answered a similar question earlier in this "
            "conversation. Do NOT answer from previous messages; the data may have changed. "
            "Never fabricate or guess shipment data. "
            "If the user asks about a tracking number that belongs to someone else, the tool will "
            "return not-found — report that honestly without explaining why."
        )

    if state == SessionState.escalated_to_human:
        if first_name:
            return base + (
                f"\n\nThis session has been escalated to human support. You are now acting as Melany, "
                f"a human support agent. Be warm and empathetic.\n\n"
                f"{first_name} was already verified before escalating. You have two tools:\n"
                f"• lookup_shipments() — for an overview of their shipments.\n"
                f"• get_shipment_details(tracking_number) — for detail on a specific shipment.\n"
                f"CRITICAL: Call the tool every time — never answer from earlier messages in this conversation."
            )
        return base + (
            "\n\nThis session has been escalated to human support. You are now acting as Melany, "
            "a human support agent. Be warm and empathetic. The customer has NOT been verified — "
            "you cannot provide shipment data. The same identity gate applies."
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
        # customer_id argument is accepted but intentionally ignored
        return await handle_send_verification_code(session, db)
    if name == "check_verification_code":
        return await handle_check_verification_code(session, db, code=arguments.get("code", ""))
    if name == "lookup_shipments":
        return await handle_lookup_shipments(session, db)
    if name == "get_shipment_details":
        return await handle_get_shipment_details(session, db, tracking_number=arguments.get("tracking_number", ""))
    return {"error": f"Unknown tool: {name}"}


def _tools_for_state(state: SessionState, customer_id: str | None = None) -> list[dict]:
    """Return the tool list appropriate for the current session state.
    lookup_shipments is only offered to verified sessions (or escalated sessions
    where the customer was verified before escalating) to keep the model
    from attempting data retrieval before the identity gate is cleared."""
    can_look_up = state == SessionState.verified or (
        state == SessionState.escalated_to_human and customer_id is not None
    )
    return IDENTITY_TOOLS + SHIPMENT_TOOLS if can_look_up else IDENTITY_TOOLS


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


class TranscriptMessage(BaseModel):
    role: str
    content: str


class SessionStateResponse(BaseModel):
    session_id: str
    session_state: str
    known_first_name: str | None = None
    show_modal: bool = False
    messages: list[TranscriptMessage] = []


@router.get("/{session_id}/state", response_model=SessionStateResponse)
async def get_session_state(session_id: str, db: AsyncSession = Depends(get_db)) -> SessionStateResponse:
    """Return current session state and visible message history without triggering an LLM call.
    Used by the frontend on page load to restore the full chat UI after a refresh."""
    result = await db.execute(select(ChatSession).where(ChatSession.id == session_id))
    chat_session = result.scalar_one_or_none()

    if chat_session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    known_first_name: str | None = None
    if chat_session.customer_id:
        cust = await db.execute(select(Customer).where(Customer.id == chat_session.customer_id))
        customer = cust.scalar_one_or_none()
        if customer:
            known_first_name = customer.first_name

    show_modal = chat_session.state in (SessionState.code_sent, SessionState.awaiting_code)

    # Build visible message list from transcript — skip entries with no displayable content
    # (pure tool-call turns) and system-role entries (internal state signals).
    messages: list[TranscriptMessage] = [
        TranscriptMessage(role=entry["role"], content=entry["content"])
        for entry in (chat_session.transcript or [])
        if entry.get("role") in ("user", "assistant") and entry.get("content", "").strip()
    ]

    return SessionStateResponse(
        session_id=session_id,
        session_state=chat_session.state.value,
        known_first_name=known_first_name,
        show_modal=show_modal,
        messages=messages,
    )


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

    # Rebuild conversation from persisted transcript, reconstructing tool call chains so the
    # model has access to raw tool results when answering follow-up questions.
    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    for entry in chat_session.transcript:
        if entry["role"] == "user":
            messages.append({"role": "user", "content": entry.get("content", "")})
        elif entry["role"] == "assistant":
            tool_calls = entry.get("tool_calls") or []
            # Reconstruct non-PII, non-stale tool calls as assistant-request + tool-result pairs.
            # Shipment tools are excluded so the model re-queries on every new message
            # rather than answering from a potentially stale cached result.
            replayable = [tc for tc in tool_calls if tc["name"] not in _PII_TOOLS | _NO_REPLAY_TOOLS]
            for tc in replayable:
                messages.append({
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {"function": {"name": tc["name"], "arguments": tc.get("arguments") or {}}}
                    ],
                })
                messages.append({"role": "tool", "content": str(tc.get("result", ""))})
            # Append the final text reply if present.
            if entry.get("content"):
                messages.append({"role": "assistant", "content": entry["content"]})
            elif not replayable:
                messages.append({"role": "assistant", "content": ""})
    messages.append({"role": "user", "content": body.message})

    executed_tool_calls: list[dict] = []
    reply = ""

    # Tool execution loop — max 5 rounds to prevent runaway recursion
    for _ in range(5):
        # Rebuild system prompt each iteration so state transitions are reflected immediately
        messages[0] = {"role": "system", "content": _build_system_prompt(chat_session.state, known_first_name)}

        result_llm = await ollama_chat(messages=messages, tools=_tools_for_state(chat_session.state, chat_session.customer_id))
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

    # Scrub PII from verify_identity arguments before persisting — the transcript is permanent storage.
    # The outcome (verified/not) is what matters; the raw name/address/phone are not needed after the call.
    transcript_tool_calls = [
        {**tc, "arguments": {"_redacted": True}} if tc["name"] in _PII_TOOLS else tc
        for tc in executed_tool_calls
    ]

    # Persist both turns
    now = datetime.now(timezone.utc).isoformat()
    chat_session.transcript = chat_session.transcript + [
        {"role": "user", "content": body.message, "timestamp": now},
        {
            "role": "assistant",
            "content": reply,
            "timestamp": now,
            "tool_calls": transcript_tool_calls,
        },
    ]
    await db.commit()

    # show_modal is true whenever the session is waiting for a code — handles page-refresh resilience
    show_modal = chat_session.state in (SessionState.code_sent, SessionState.awaiting_code)

    return ChatResponse(
        reply=reply,
        session_id=session_id,
        tool_calls=[ToolCall(name=tc["name"], arguments=tc["arguments"]) for tc in executed_tool_calls],
        show_modal=show_modal,
        session_state=chat_session.state.value,
        escalated=False,
        known_first_name=known_first_name,
    )
