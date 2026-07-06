from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse
from core.errors import safe_error_response
from services.document_service import (
    MAX_FILE_BYTES,
    get_document_file,
    ingest_document,
    list_documents,
)

router = APIRouter()


@router.get("/")
def get_documents():
    return list_documents()


@router.get("/{document_id}/file")
def download_document(document_id: int):
    doc = get_document_file(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    file_path = Path(doc["file_path"])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Document not found.")
    return FileResponse(
        path=file_path,
        media_type=doc["content_type"] or "application/octet-stream",
        filename=doc["filename"],
    )


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
