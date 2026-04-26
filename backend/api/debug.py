from fastapi import APIRouter
from sqlalchemy import func

from db.database import SessionLocal
from db.models import Conversation, Message, Summary

router = APIRouter()


@router.get("/stats")
def stats():
    session = SessionLocal()
    try:
        conv_count = session.query(func.count(Conversation.id)).scalar() or 0
        msg_count = session.query(func.count(Message.id)).scalar() or 0
        latest_msg = (
            session.query(Message)
            .order_by(Message.created_at.desc())
            .first()
        )
        latest = None
        if latest_msg:
            latest = {
                "conversation_id": latest_msg.conversation_id,
                "role": latest_msg.role,
                "created_at": latest_msg.created_at.isoformat() if latest_msg.created_at else None,
            }
        latest_summary = (
            session.query(Summary)
            .order_by(Summary.created_at.desc())
            .first()
        )
        summary_info = None
        if latest_summary:
            summary_info = {
                "content_preview": (latest_summary.content or "")[:500],
                "message_count_at_creation": latest_summary.message_count_at_creation,
                "created_at": latest_summary.created_at.isoformat() if latest_summary.created_at else None,
                "updated_at": latest_summary.updated_at.isoformat() if latest_summary.updated_at else None,
            }
        return {
            "conversations": conv_count,
            "messages": msg_count,
            "latest_message": latest,
            "summary": summary_info,
        }
    finally:
        session.close()
