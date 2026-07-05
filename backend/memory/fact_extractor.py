from __future__ import annotations

import json
import re
from datetime import datetime

from sqlalchemy import func

from db.database import SessionLocal
from db.models import Message, MemoryEntry
from providers.claude_provider import ClaudeProvider

# Trigger interval — extract facts every N new messages
FACT_EXTRACTION_INTERVAL = 30

# Allowed categories — extracted facts not in this list are discarded
ALLOWED_CATEGORIES = {"identity", "family", "preferences", "projects", "context", "knowledge"}

EXTRACTION_SYSTEM_PROMPT = """You are extracting structured facts about a user from conversation history. These facts will be stored in a memory database for an AI companion named Caelo.

Return ONLY a JSON array of fact objects. No prose, no explanation, just JSON.

Each fact object has this shape:
{"category": "<one of: identity, family, preferences, projects, context>", "content": "<short factual statement>"}

Rules:
- Only extract facts that are explicitly stated or strongly implied by the user
- Each fact should be ONE specific thing — split compound facts into separate entries
- Use third-person factual phrasing: "User's name is Michael" not "My name is Michael"
- Skip generic small talk, AI testing patterns, and anything that isn't really about the user
- Skip facts that would be embarrassing or sensitive unless directly stated
- If you can't find clear facts, return an empty array []
- Do NOT include markdown code fences in your response — just the raw JSON array

Categories:
- identity: name, location, job, demographics, identity-defining attributes
- family: people in their life, pets, relationships
- preferences: likes, dislikes, favorites, opinions
- projects: things they're building, working on, learning
- context: ongoing situations, current state, things they're navigating"""


def _should_run_extraction(session) -> tuple[bool, int]:
    """Decide whether to run extraction based on message count vs last extraction marker."""
    msg_count = session.query(func.count(Message.id)).scalar() or 0
    # Use the most recent MemoryEntry's created_at as a rough marker via Setting? Simpler: check Setting.
    # For now, use a settings-like approach: track last_extraction_count in MemoryEntry weight=0.0 archive=True
    # Simpler approach: always look at the highest-id MemoryEntry's "created_at" against most recent message count.
    last_marker = (
        session.query(MemoryEntry)
        .order_by(MemoryEntry.id.desc())
        .first()
    )
    if last_marker is None:
        return msg_count >= 6, msg_count
    # We use the count stored at last extraction; we'll persist this via a sentinel approach.
    # Simpler: rely on count of facts vs message count. If we have very few facts and many messages, run.
    # For trigger logic, use the time since last MemoryEntry was created vs message growth.
    # Cleanest: use the count of messages since the last fact's last_used_at update.
    return msg_count - _last_run_message_count(session) >= FACT_EXTRACTION_INTERVAL, msg_count


def _last_run_message_count(session) -> int:
    """Read the persisted message count from the last extraction run, stored in a settings-like row."""
    from db.models import Setting
    row = session.query(Setting).filter_by(key="last_fact_extraction_msg_count").first()
    if row and row.value:
        try:
            return int(row.value)
        except ValueError:
            return 0
    return 0


def _set_last_run_message_count(session, count: int) -> None:
    from db.models import Setting
    row = session.query(Setting).filter_by(key="last_fact_extraction_msg_count").first()
    if row:
        row.value = str(count)
    else:
        session.add(Setting(key="last_fact_extraction_msg_count", value=str(count)))


def _fetch_recent_messages_for_extraction(session, limit: int = 50) -> list[dict]:
    rows = (
        session.query(Message)
        .order_by(Message.created_at.desc())
        .limit(limit)
        .all()
    )
    rows.reverse()
    return [
        {"role": m.role, "content": m.content}
        for m in rows
        if m.role in ("user", "assistant") and (m.content or "").strip()
    ]


def _format_messages_for_extraction(messages: list[dict]) -> str:
    lines = []
    for m in messages:
        role_label = "User" if m["role"] == "user" else "Caelo"
        lines.append(f"{role_label}: {m['content']}")
    return "\n\n".join(lines)


def _parse_extraction_response(text: str) -> list[dict]:
    """Parse Claude's JSON response into a list of fact dicts. Returns [] on any error."""
    if not text or not text.strip():
        return []
    cleaned = text.strip()
    # Strip markdown code fences if Claude added them despite instructions — the fence
    # may not be the very first thing if a short preamble sneaks in before it.
    fence_match = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL)
    if fence_match:
        cleaned = fence_match.group(1).strip()
    elif not cleaned.startswith("["):
        # No fences and the response doesn't start clean — fall back to the first
        # top-level JSON array anywhere in the text (handles a stray sentence of prose).
        bracket_match = re.search(r"\[.*\]", cleaned, re.DOTALL)
        if bracket_match:
            cleaned = bracket_match.group(0)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    valid = []
    for item in data:
        if not isinstance(item, dict):
            continue
        cat = (item.get("category") or "").strip().lower()
        content = (item.get("content") or "").strip()
        if cat not in ALLOWED_CATEGORIES:
            continue
        if not content:
            continue
        valid.append({"category": cat, "content": content})
    return valid


def _merge_facts(session, new_facts: list[dict]) -> int:
    """Smart merge: update existing facts with same category+similar content, otherwise insert new. Returns count saved/updated."""
    saved = 0
    now = datetime.utcnow()
    for fact in new_facts:
        cat = fact["category"]
        content = fact["content"]
        # Look for existing fact in same category with very similar content
        existing = (
            session.query(MemoryEntry)
            .filter(MemoryEntry.category == cat)
            .filter(MemoryEntry.archived == False)  # noqa: E712
            .all()
        )
        # Naive dedup: skip if exact match exists
        is_duplicate = any(
            (e.content or "").strip().lower() == content.strip().lower()
            for e in existing
        )
        if is_duplicate:
            # Touch last_used_at on the matching entry
            for e in existing:
                if (e.content or "").strip().lower() == content.strip().lower():
                    e.last_used_at = now
            continue
        # Insert new fact
        new_entry = MemoryEntry(
            category=cat,
            content=content,
            state="observed",
            weight=0.5,
            sensitivity="low",
            created_at=now,
            last_used_at=now,
            archived=False,
        )
        session.add(new_entry)
        saved += 1
    return saved


def maybe_extract_facts() -> None:
    """Run fact extraction if enough new messages have accumulated. Failures are swallowed."""
    session = SessionLocal()
    try:
        should_run, msg_count = _should_run_extraction(session)
        if not should_run:
            return
        messages = _fetch_recent_messages_for_extraction(session)
        if not messages:
            return
        formatted = _format_messages_for_extraction(messages)
        provider = ClaudeProvider()
        response = provider.generate_messages([
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": f"Conversation history:\n\n{formatted}\n\nReturn the JSON array of facts now."},
        ])
        new_facts = _parse_extraction_response(response)
        if new_facts:
            _merge_facts(session, new_facts)
        _set_last_run_message_count(session, msg_count)
        session.commit()
    except Exception as e:
        session.rollback()
        print(f"[fact_extractor] maybe_extract_facts failed: {e}")
    finally:
        session.close()
