"""Document upload → text extraction → knowledge memory ingestion."""

from __future__ import annotations

import io

from db.database import SessionLocal
from db.persistence import save_message
from memory.fact_extractor import _merge_facts, _parse_extraction_response
from providers.claude_provider import ClaudeProvider

SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx"}
MAX_FILE_BYTES = 15 * 1024 * 1024  # 15 MB
MAX_CHARS_FOR_EXTRACTION = 20000  # keep the extraction prompt within a reasonable token budget

# Uploads have no conversation_id of their own; recent-message lookups are global
# (see db.persistence.get_recent_messages_from_db), so any fixed id surfaces here.
DOCUMENT_UPLOAD_CONVERSATION_ID = "document-uploads"

DOCUMENT_EXTRACTION_SYSTEM_PROMPT = """You are extracting useful, reusable facts from a document a user uploaded to an AI companion named Caelo, so Caelo can recall this information in future conversations.

Return ONLY a JSON array of fact objects. No prose, no explanation, just JSON.

Each fact object has this shape:
{"category": "<one of: identity, family, preferences, projects, context, knowledge>", "content": "<short factual statement>"}

Rules:
- Use "knowledge" for facts/information from the document itself (definitions, decisions, data points, plans, reference info)
- Use identity/family/preferences/projects/context only if the document clearly states something about the user
- Each fact should be ONE specific, self-contained statement — split compound facts into separate entries
- Skip boilerplate, formatting artifacts, and anything too vague to be useful later
- If you can't find clear facts, return an empty array []
- Do NOT include markdown code fences in your response — just the raw JSON array"""


class UnsupportedFileType(ValueError):
    pass


class EmptyDocument(ValueError):
    pass


def extract_text(filename: str, data: bytes) -> str:
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFileType(
            f"Unsupported file type {ext or '(none)'!r}. Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    if ext in (".txt", ".md"):
        text = data.decode("utf-8", errors="replace")
    elif ext == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
    elif ext == ".docx":
        from docx import Document

        doc = Document(io.BytesIO(data))
        text = "\n".join(p.text for p in doc.paragraphs)
    else:  # pragma: no cover - guarded by the check above
        raise UnsupportedFileType(ext)

    text = text.strip()
    if not text:
        raise EmptyDocument("No extractable text found in this document.")
    return text


def ingest_document(filename: str, data: bytes) -> dict:
    """Extract text from an uploaded document and store distilled facts in long-term memory."""
    text = extract_text(filename, data)
    excerpt = text[:MAX_CHARS_FOR_EXTRACTION]

    provider = ClaudeProvider()
    response = provider.generate_messages(
        [
            {"role": "system", "content": DOCUMENT_EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": f"Document: {filename}\n\n{excerpt}\n\nReturn the JSON array of facts now."},
        ]
    )
    facts = _parse_extraction_response(response)
    facts = [{**f, "content": f"From {filename}: {f['content']}"} for f in facts]

    session = SessionLocal()
    try:
        saved = _merge_facts(session, facts) if facts else 0
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    save_message(
        DOCUMENT_UPLOAD_CONVERSATION_ID,
        "user",
        f"[Uploaded document: {filename} — Caelo extracted {saved} facts from it into memory]",
    )

    return {
        "filename": filename,
        "chars_extracted": len(text),
        "facts_saved": saved,
    }
