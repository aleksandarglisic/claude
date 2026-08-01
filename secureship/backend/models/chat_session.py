import uuid
import enum
from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import String, Integer, ForeignKey, Enum as SAEnum, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from db.session import Base

if TYPE_CHECKING:
    from models.customer import Customer


class SessionState(str, enum.Enum):
    anonymous = "anonymous"
    collecting_identity = "collecting_identity"
    code_sent = "code_sent"
    awaiting_code = "awaiting_code"
    verified = "verified"
    escalated_to_human = "escalated_to_human"


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    customer_id: Mapped[str | None] = mapped_column(String, ForeignKey("customers.id"), nullable=True)
    pending_customer_id: Mapped[str | None] = mapped_column(String, nullable=True)
    state: Mapped[SessionState] = mapped_column(SAEnum(SessionState), nullable=False, default=SessionState.anonymous)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    transcript: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    verification_code: Mapped[str | None] = mapped_column(String(6), nullable=True)
    code_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    code_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    customer: Mapped["Customer | None"] = relationship("Customer", back_populates="chat_sessions")
