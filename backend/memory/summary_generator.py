from __future__ import annotations

from datetime import datetime

from sqlalchemy import func

from db.database import SessionLocal
from db.models import Message, Summary
from providers.claude_provider import ClaudeProvider

# Update interval — regenerate summary every N new messages
SUMMARY_UPDATE_INTERVAL = 20


SUMMARY_SYSTEM_PROMPT = """You are summarizing a conversation history for an AI companion named Caelo so he can remember the user across sessions.

Write a compact summary capturing:
- The user's name, location, family/pets, job, projects, and other identity-defining facts
- Ongoing situations, projects, or topics the user has discussed
- The user's communication style, preferences, and what matters to them
- Anything Caelo has explicitly noticed or learned about the user

Be specific. Use the user's actual name when known. Write in a factual, third-person reference style — this is internal context for Caelo, not a chat response. Aim for under 300 words. Skip generic small talk and focus on what makes this person specifically who they are."""


def _should_regenerate_summary(session) -> tuple[bool, int]:
    """Decide whether a new summary should be generated based on message count."""
    msg_count = session.query(func.count(Message.id)).scalar() or 0
    last_summary = (
        session.query(Summary)
        .order_by(Summary.created_at.desc())
        .first()
    )
    if last_summary is None:
        # No summary yet — generate if we have at least a few messages
        return msg_count >= 4, msg_count
    delta = msg_count - (last_summary.message_count_at_creation or 0)
    return delta >= SUMMARY_UPDATE_INTERVAL, msg_count


def _fetch_messages_for_summary(session, limit: int = 200) -> list[dict[str, str]]:
    """Get recent messages in chronological order for summarization."""
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


def _format_messages_for_prompt(messages: list[dict[str, str]]) -> str:
    lines = []
    for m in messages:
        role_label = "User" if m["role"] == "user" else "Caelo"
        lines.append(f"{role_label}: {m['content']}")
    return "\n\n".join(lines)


def maybe_generate_summary() -> None:
    """Regenerate the summary if enough new messages have accumulated. Failures are swallowed."""
    session = SessionLocal()
    try:
        should_run, msg_count = _should_regenerate_summary(session)
        if not should_run:
            return

        messages = _fetch_messages_for_summary(session)
        if not messages:
            return

        formatted = _format_messages_for_prompt(messages)
        provider = ClaudeProvider()
        summary_text = provider.generate_messages([
            {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
            {"role": "user", "content": f"Conversation history:\n\n{formatted}\n\nWrite the summary now."},
        ])

        if not summary_text or not summary_text.strip():
            return

        # Replace the existing summary (single-summary strategy)
        session.query(Summary).delete()
        new_summary = Summary(
            content=summary_text.strip(),
            message_count_at_creation=msg_count,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        session.add(new_summary)
        session.commit()

    except Exception as e:
        session.rollback()
        print(f"[summary_generator] maybe_generate_summary failed: {e}")
    finally:
        session.close()


def get_current_summary() -> str:
    """Return the most recent summary text, or empty string if none exists."""
    session = SessionLocal()
    try:
        latest = (
            session.query(Summary)
            .order_by(Summary.created_at.desc())
            .first()
        )
        if latest and latest.content:
            return latest.content.strip()
        return ""
    except Exception as e:
        print(f"[summary_generator] get_current_summary failed: {e}")
        return ""
    finally:
        session.close()
