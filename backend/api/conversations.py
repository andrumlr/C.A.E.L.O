from fastapi import APIRouter
from db.persistence import get_conversation_messages, list_conversations
from services.document_service import DOCUMENT_UPLOAD_CONVERSATION_ID

router = APIRouter()


@router.get("/")
def get_conversations():
    return [c for c in list_conversations() if c["id"] != DOCUMENT_UPLOAD_CONVERSATION_ID]


@router.get("/{conversation_id}/messages")
def get_conversation(conversation_id: str):
    return {"conversation_id": conversation_id, "messages": get_conversation_messages(conversation_id)}
