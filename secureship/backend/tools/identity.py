import random
import string
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from models.customer import Customer
from models.chat_session import ChatSession, SessionState

CODE_EXPIRY_MINUTES = 10
MAX_CODE_ATTEMPTS = 3

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "request_identity_info",
            "description": (
                "Signal that you need the user's identity to proceed. "
                "Call this when the user asks about their shipments and has not been verified yet."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "verify_identity",
            "description": (
                "Attempt to verify the user's identity using information they provided. "
                "Call this once you have collected first_name, last_name, address, and phone_number."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "first_name": {"type": "string"},
                    "last_name": {"type": "string"},
                    "address": {"type": "string"},
                    "phone_number": {"type": "string"},
                },
                "required": ["first_name", "last_name", "address", "phone_number"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_verification_code",
            "description": "Generate and send a new 6-digit verification code. Use this if the user says they did not receive their code.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


def _normalize_phone(phone: str) -> str:
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    return f"+{digits}"


def _generate_code() -> str:
    return "".join(random.choices(string.digits, k=6))


async def handle_request_identity_info(session: ChatSession, db: AsyncSession) -> dict:
    if session.state == SessionState.anonymous:
        session.state = SessionState.collecting_identity
        await db.commit()
    return {"status": "collecting_identity", "message": "Ready to collect identity information."}


async def handle_verify_identity(
    session: ChatSession,
    db: AsyncSession,
    first_name: str,
    last_name: str,
    address: str,
    phone_number: str,
) -> dict:
    normalized_phone = _normalize_phone(phone_number)

    # Try exact match on name + phone first
    result = await db.execute(
        select(Customer).where(
            func.lower(Customer.first_name) == first_name.strip().lower(),
            func.lower(Customer.last_name) == last_name.strip().lower(),
            Customer.phone_number == normalized_phone,
        )
    )
    customer = result.scalar_one_or_none()

    # Fallback: name + address substring match
    if customer is None:
        result = await db.execute(
            select(Customer).where(
                func.lower(Customer.first_name) == first_name.strip().lower(),
                func.lower(Customer.last_name) == last_name.strip().lower(),
            )
        )
        candidates = result.scalars().all()
        addr_lower = address.strip().lower()
        for c in candidates:
            if addr_lower in c.address.lower() or c.address.lower() in addr_lower:
                customer = c
                break

    if customer is None:
        return {
            "verified": False,
            "message": "We couldn't verify that information. Please check your details and try again.",
        }

    code = _generate_code()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=CODE_EXPIRY_MINUTES)

    session.pending_customer_id = str(customer.id)
    session.verification_code = code
    session.code_expires_at = expires_at
    session.code_attempts = 0
    session.state = SessionState.code_sent
    await db.commit()

    print(f"\n[2FA CODE] Session {session.id} → code: {code}\n", flush=True)

    return {
        "verified": True,
        "message": "Identity matched. A 6-digit verification code has been sent.",
    }


async def handle_send_verification_code(session: ChatSession, db: AsyncSession) -> dict:
    if not session.pending_customer_id:
        return {"status": "error", "message": "No pending identity verification found."}

    code = _generate_code()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=CODE_EXPIRY_MINUTES)

    session.verification_code = code
    session.code_expires_at = expires_at
    session.code_attempts = 0
    await db.commit()

    print(f"\n[2FA CODE] Session {session.id} → new code: {code}\n", flush=True)

    return {"status": "sent", "message": "A new verification code has been sent."}
