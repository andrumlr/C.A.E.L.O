from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from db.database import SessionLocal
from db.models import Conversation, Message


def _get_or_create_conversation(session: Session, conversation_id: str) -> Conversation:
    existing = session.query(Conversation).filter_by(id=conversation_id).first()
    if existing:
        return existing
    convo = Conversation(
        id=conversation_id,
        title=None,
        created_at=datetime.utcnow(),
    )
    session.add(convo)
    session.flush()
    return convo


def save_exchange(
    conversation_id: str,
    user_message: str,
    assistant_message: str,
    mode: str,
) -> None:
    """Persist a user+assistant exchange to SQLite. Failures are logged, not raised."""
    if not conversation_id:
        return
    session = SessionLocal()
    try:
        _get_or_create_conversation(session, conversation_id)
        now = datetime.utcnow()
        session.add(
            Message(
                conversation_id=conversation_id,
                role="user",
                content=user_message,
                mode_used=mode,
                created_at=now,
            )
        )
        session.add(
            Message(
                conversation_id=conversation_id,
                role="assistant",
                content=assistant_message,
                mode_used=mode,
                created_at=now,
            )
        )
        session.commit()
    except Exception as e:
        session.rollback()
        # Swallow — persistence failures should never break chat responses
        print(f"[persistence] save_exchange failed: {e}")
    finally:
        session.close()
