from sqlalchemy.ext.asyncio import AsyncSession
from models.chat_session import ChatSession, SessionState

# Tools sent to Ollama only for verified sessions.
SHIPMENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "lookup_shipments",
            "description": (
                "Retrieve all shipments for the verified customer. "
                "Call this when the user asks about their packages or delivery status."
            ),
            # No customer_id parameter — backend always uses session.customer_id.
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


async def handle_lookup_shipments(session: ChatSession, db: AsyncSession) -> dict:
    """
    Identity gate: only executes for verified sessions.
    The check here is the single authoritative enforcement point (Epic F3).
    Week 3 will replace the stub body with the real DB query.
    """
    can_access = (
        session.state == SessionState.verified
        or (session.state == SessionState.escalated_to_human and session.customer_id is not None)
    )
    if not can_access:
        # Return an error result — never the data — so the model cannot relay it.
        return {
            "error": "Access denied. The session is not verified.",
            "data": None,
        }

    # --- Week 3: replace this stub with the real shipment query ---
    # result = await db.execute(
    #     select(Shipment).where(Shipment.customer_id == session.customer_id)
    # )
    # shipments = result.scalars().all()
    # return {"shipments": [s.to_dict() for s in shipments]}
    return {
        "shipments": [],
        "note": "Shipment data will be available in the next update.",
    }
