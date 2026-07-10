import base64
import binascii

from fastapi import APIRouter
from pydantic import BaseModel, Field
from core.errors import safe_error_response
from services.conversation_service import run_chat
from services.document_service import MAX_IMAGE_BYTES

router = APIRouter()


class ChatImage(BaseModel):
    """An image shared alongside a chat message. ``data`` is base64 (no data: prefix)."""

    media_type: str
    data: str
    filename: str | None = None


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = Field(
        default=None,
        max_length=256,
        description="Optional id to keep short-term chat continuity across turns (in-memory).",
    )
    image: ChatImage | None = Field(
        default=None,
        description="Optional image to share with the message (base64). Empty = text-only chat.",
    )


@router.post("/")
def chat(input: ChatRequest):
    try:
        user_input = input.message.strip()

        image_payload = None
        if input.image is not None and (input.image.data or "").strip():
            try:
                raw = base64.b64decode(input.image.data, validate=True)
            except (binascii.Error, ValueError):
                return {
                    "error_type": "ValueError",
                    "error_message": "Image data is not valid base64.",
                }
            if len(raw) > MAX_IMAGE_BYTES:
                return {
                    "error_type": "ValueError",
                    "error_message": f"Image is too large. Max size is {MAX_IMAGE_BYTES // (1024 * 1024)} MB.",
                }
            image_payload = {
                "media_type": input.image.media_type,
                "data": input.image.data,
                "bytes": raw,
                "filename": input.image.filename or "image",
            }

        # An image can carry the turn on its own, so only require text when there's no image.
        if not user_input and image_payload is None:
            return {
                "error_type": "ValueError",
                "error_message": "Message cannot be empty.",
            }

        return run_chat(
            user_input,
            conversation_id=input.conversation_id,
            image=image_payload,
        )
    except Exception as e:
        return safe_error_response(e, log_prefix="chat")
