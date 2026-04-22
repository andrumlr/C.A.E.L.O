from fastapi import APIRouter
from pydantic import BaseModel, Field
from services.conversation_service import run_chat

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = Field(
        default=None,
        max_length=256,
        description="Optional id to keep short-term chat continuity across turns (in-memory).",
    )


@router.post("/")
def chat(input: ChatRequest):
    try:
        user_input = input.message.strip()
        if not user_input:
            return {
                "error_type": "ValueError",
                "error_message": "Message cannot be empty.",
            }

        return run_chat(user_input, conversation_id=input.conversation_id)
    except Exception as e:
        return {
            "error_type": type(e).__name__,
            "error_message": str(e),
        }
