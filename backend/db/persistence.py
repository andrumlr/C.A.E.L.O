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


def save_message(conversation_id: str, role: str, content: str, mode: str | None = None) -> None:
    """Persist a single message to SQLite. Failures are logged, not raised."""
    if not conversation_id:
        return
    session = SessionLocal()
    try:
        _get_or_create_conversation(session, conversation_id)
        session.add(
            Message(
                conversation_id=conversation_id,
                role=role,
                content=content,
                mode_used=mode,
                created_at=datetime.utcnow(),
            )
        )
        session.commit()
    except Exception as e:
        session.rollback()
        # Swallow — persistence failures should never break chat responses
        print(f"[persistence] save_message failed: {e}")
    finally:
        session.close()


def get_recent_messages_from_db(limit: int = 20) -> list[dict[str, str]]:
    """
    Return the most recent messages globally, in chronological order.
    Cross-session memory — pulls from any conversation, not just the current one.
    Returns a list of {"role": ..., "content": ...} dicts ready for the LLM.
    """
    session = SessionLocal()
    try:
        rows = (
            session.query(Message)
            .order_by(Message.created_at.desc())
            .limit(limit)
            .all()
        )
        # DB returned newest-first; reverse into chronological (oldest-first) order
        rows.reverse()
        return [
            {"role": m.role, "content": m.content}
            for m in rows
            if m.role in ("user", "assistant") and (m.content or "").strip()
        ]
    except Exception as e:
        print(f"[persistence] get_recent_messages_from_db failed: {e}")
        return []
    finally:
        session.close()


def list_conversations(limit: int = 50) -> list[dict]:
    """Return recent conversations, newest first, each with a preview of its first message."""
    session = SessionLocal()
    try:
        convos = (
            session.query(Conversation)
            .order_by(Conversation.created_at.desc())
            .limit(limit)
            .all()
        )
        result = []
        for c in convos:
            first_message = (
                session.query(Message)
                .filter_by(conversation_id=c.id, role="user")
                .order_by(Message.created_at.asc())
                .first()
            )
            preview = (first_message.content or "").strip() if first_message else ""
            result.append(
                {
                    "id": c.id,
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                    "preview": preview[:120],
                }
            )
        return result
    except Exception as e:
        print(f"[persistence] list_conversations failed: {e}")
        return []
    finally:
        session.close()


def get_conversation_messages(conversation_id: str) -> list[dict]:
    """Return every message in a single conversation, in chronological order."""
    session = SessionLocal()
    try:
        rows = (
            session.query(Message)
            .filter_by(conversation_id=conversation_id)
            .order_by(Message.created_at.asc())
            .all()
        )
        return [
            {
                "role": m.role,
                "content": m.content,
                "mode": m.mode_used,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in rows
        ]
    except Exception as e:
        print(f"[persistence] get_conversation_messages failed: {e}")
        return []
    finally:
        session.close()
