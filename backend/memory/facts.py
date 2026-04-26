from __future__ import annotations

from sqlalchemy import desc

from db.database import SessionLocal
from db.models import MemoryEntry


def get_active_facts(limit: int = 100) -> list[dict]:
    """Return non-archived MemoryEntry rows, ordered by most recently used."""
    session = SessionLocal()
    try:
        rows = (
            session.query(MemoryEntry)
            .filter(MemoryEntry.archived == False)  # noqa: E712
            .order_by(desc(MemoryEntry.last_used_at))
            .limit(limit)
            .all()
        )
        return [
            {
                "id": r.id,
                "category": r.category,
                "content": r.content,
                "state": r.state,
                "weight": r.weight or 0.0,
                "sensitivity": r.sensitivity or "low",
            }
            for r in rows
            if r.content and r.content.strip()
        ]
    except Exception as e:
        print(f"[facts] get_active_facts failed: {e}")
        return []
    finally:
        session.close()


def format_facts_for_prompt(facts: list[dict]) -> str:
    """Format a list of fact dicts into compact text for prompt injection."""
    if not facts:
        return ""
    lines = []
    by_category: dict[str, list[str]] = {}
    for f in facts:
        cat = f.get("category") or "general"
        content = (f.get("content") or "").strip()
        if not content:
            continue
        by_category.setdefault(cat, []).append(content)
    for cat, items in by_category.items():
        lines.append(f"{cat}: " + "; ".join(items))
    return "\n".join(lines)
