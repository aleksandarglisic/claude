from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from db.session import get_db
from models.chat_session import ChatSession, SessionState
from tools.identity import MAX_CODE_ATTEMPTS

router = APIRouter(prefix="/verify-code", tags=["verify"])


class VerifyCodeRequest(BaseModel):
    code: str
    session_id: str


class VerifyCodeResponse(BaseModel):
    success: bool
    message: str
    session_state: str


@router.post("", response_model=VerifyCodeResponse)
async def verify_code(body: VerifyCodeRequest, db: AsyncSession = Depends(get_db)) -> VerifyCodeResponse:
    result = await db.execute(select(ChatSession).where(ChatSession.id == body.session_id))
    session = result.scalar_one_or_none()

    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.state not in (SessionState.code_sent, SessionState.awaiting_code):
        raise HTTPException(status_code=400, detail="Session is not awaiting code verification")

    now = datetime.now(timezone.utc)

    # Check expiry
    if session.code_expires_at and now > session.code_expires_at.replace(tzinfo=timezone.utc):
        await db.commit()
        return VerifyCodeResponse(
            success=False,
            message="Verification code has expired. Please request a new one.",
            session_state=session.state.value,
        )

    # Check attempt limit
    if session.code_attempts >= MAX_CODE_ATTEMPTS:
        await db.commit()
        return VerifyCodeResponse(
            success=False,
            message="Too many failed attempts. Please request a new verification code.",
            session_state=session.state.value,
        )

    # Wrong code
    if body.code != session.verification_code:
        session.code_attempts += 1
        session.state = SessionState.awaiting_code
        remaining = MAX_CODE_ATTEMPTS - session.code_attempts
        await db.commit()
        if remaining > 0:
            msg = f"Incorrect code. {remaining} attempt{'s' if remaining != 1 else ''} remaining."
        else:
            msg = "Too many failed attempts. Please request a new verification code."
        return VerifyCodeResponse(success=False, message=msg, session_state=session.state.value)

    # Success
    session.state = SessionState.verified
    session.customer_id = session.pending_customer_id
    session.verification_code = None
    session.code_attempts = 0
    await db.commit()

    return VerifyCodeResponse(
        success=True,
        message="Identity verified. You're all set!",
        session_state=SessionState.verified.value,
    )
