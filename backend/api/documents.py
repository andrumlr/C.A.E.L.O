from fastapi import APIRouter, UploadFile
from core.errors import safe_error_response
from services.document_service import MAX_FILE_BYTES, ingest_document, list_documents

router = APIRouter()


@router.get("/")
def get_documents():
    return list_documents()


@router.post("/")
async def upload_document(file: UploadFile):
    try:
        data = await file.read()
        if len(data) > MAX_FILE_BYTES:
            return {
                "error_type": "ValueError",
                "error_message": f"File is too large. Max size is {MAX_FILE_BYTES // (1024 * 1024)} MB.",
            }
        return ingest_document(file.filename or "upload", data)
    except Exception as e:
        return safe_error_response(e, log_prefix="documents")
