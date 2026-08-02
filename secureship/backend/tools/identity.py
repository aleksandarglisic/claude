import random
import string
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from models.customer import Customer
from models.chat_session import ChatSession, SessionState

CODE_EXPIRY_MINUTES = 10
MAX_CODE_ATTEMPTS = 3

# Tools sent to Ollama for every session state except verified.
# Backend executes each tool call; the model only requests them.
IDENTITY_TOOLS = [
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
            "description": (
                "Generate and send a new 6-digit verification code to the customer. "
                "Use this if the user didn't receive their code, the code expired, or they were locked out."
            ),
            "parameters": {
                "type": "object",
                # customer_id is accepted for API compatibility but the backend always
                # uses session.pending_customer_id — never the model-supplied value.
                "properties": {
                    "customer_id": {
                        "type": "string",
                        "description": "Customer ID (ignored — backend uses the session's verified customer).",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_verification_code",
            "description": (
                "Verify a 6-digit code that the user has typed directly in this chat. "
                "Use this only when the user provides their code in the conversation; "
                "the verification modal is the preferred entry point."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "The 6-digit code the user provided."},
                },
                "required": ["code"],
            },
        },
    },
]

# Keep a backwards-compatible alias used by older import sites
TOOL_DEFINITIONS = IDENTITY_TOOLS


_ADDR_STOP_WORDS = {"st", "ave", "rd", "dr", "ln", "blvd", "way", "ct", "pl", "the", "and", "of", "a"}


def _normalize_phone(phone: str) -> str:
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    return f"+{digits}"


def _match_address(user_addr: str, db_addr: str) -> bool:
    """
    Flexible address match that handles partial user input (no zip, abbreviated state, etc.).
    Rules: house number must match AND at least one meaningful street keyword must match.
    """
    user_lower = user_addr.strip().lower()
    db_lower = db_addr.strip().lower()

    if user_lower in db_lower or db_lower in user_lower:
        return True

    user_tokens = [t.strip(".,") for t in user_lower.split()]
    db_tokens = set(t.strip(".,") for t in db_lower.split())

    user_num = next((t for t in user_tokens if t.isdigit()), None)
    if not user_num or user_num not in db_tokens:
        return False

    meaningful = {
        t for t in user_tokens
        if not t.isdigit() and len(t) > 2 and t not in _ADDR_STOP_WORDS
    }
    return bool(meaningful & db_tokens)


def _generate_code() -> str:
    return "".join(random.choices(string.digits, k=6))


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

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

    result = await db.execute(
        select(Customer).where(
            func.lower(Customer.first_name) == first_name.strip().lower(),
            func.lower(Customer.last_name) == last_name.strip().lower(),
            Customer.phone_number == normalized_phone,
        )
    )
    customer = result.scalar_one_or_none()

    if customer is None:
        result = await db.execute(
            select(Customer).where(
                func.lower(Customer.first_name) == first_name.strip().lower(),
                func.lower(Customer.last_name) == last_name.strip().lower(),
            )
        )
        candidates = result.scalars().all()
        for c in candidates:
            if _match_address(address, c.address):
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
    """customer_id argument is intentionally ignored — backend always uses session.pending_customer_id."""
    if not session.pending_customer_id:
        return {"status": "error", "message": "No pending identity verification found."}

    code = _generate_code()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=CODE_EXPIRY_MINUTES)

    session.verification_code = code
    session.code_expires_at = expires_at
    session.code_attempts = 0
    session.state = SessionState.code_sent
    await db.commit()

    print(f"\n[2FA CODE] Session {session.id} → new code: {code}\n", flush=True)

    return {"status": "sent", "message": "A new verification code has been sent."}


async def handle_check_verification_code(
    session: ChatSession,
    db: AsyncSession,
    code: str,
) -> dict:
    """Verify a code typed directly in chat. Enforces expiry and attempt limits identically to /verify-code."""
    if session.state not in (SessionState.code_sent, SessionState.awaiting_code):
        return {"verified": False, "message": "No verification code is currently pending."}

    now = datetime.now(timezone.utc)

    if session.code_expires_at and now > _aware(session.code_expires_at):
        return {
            "verified": False,
            "message": "The verification code has expired. Please request a new one.",
        }

    if code != session.verification_code:
        session.code_attempts += 1
        session.state = SessionState.awaiting_code
        remaining = max(MAX_CODE_ATTEMPTS - session.code_attempts, 0)
        await db.commit()
        if remaining > 0:
            return {
                "verified": False,
                "message": f"Incorrect code. {remaining} attempt{'s' if remaining != 1 else ''} remaining.",
                "attempts_remaining": remaining,
            }
        return {
            "verified": False,
            "message": "Too many failed attempts. Please request a new verification code.",
            "attempts_remaining": 0,
        }

    session.state = SessionState.verified
    session.customer_id = session.pending_customer_id
    session.verification_code = None
    session.code_attempts = 0
    await db.commit()

    return {"verified": True, "message": "Identity verified successfully."}
