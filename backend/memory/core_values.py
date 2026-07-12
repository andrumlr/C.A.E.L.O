"""Caelo's self-authored core values.

A separate store from the user-facing MemoryEntry table: these are commitments
Caelo writes about himself, stored verbatim. He proposes them (status "pending");
the user approves them into "active" or dismisses them into "removed". Only
"active" values are injected back into his prompt.
"""

from __future__ import annotations

from datetime import datetime

from db.database import SessionLocal
from db.models import CoreValue


def _row_to_dict(v: CoreValue) -> dict:
    return {
        "id": v.id,
        "content": v.content,
        "status": v.status,
        "created_at": v.created_at.isoformat() if v.created_at else None,
        "activated_at": v.activated_at.isoformat() if v.activated_at else None,
    }


def propose_core_value(content: str) -> bool:
    """Insert a new pending value, storing ``content`` verbatim (surrounding
    whitespace stripped only). Returns False without inserting if an identical
    content string already exists in any status, or on any database failure.
    """
    text = (content or "").strip()
    if not text:
        return False
    session = SessionLocal()
    try:
        existing = session.query(CoreValue).filter(CoreValue.content == text).first()
        if existing is not None:
            return False
        session.add(CoreValue(content=text, status="pending", created_at=datetime.utcnow()))
        session.commit()
        return True
    except Exception as e:
        session.rollback()
        print(f"[core_values] propose_core_value failed: {e}")
        return False
    finally:
        session.close()


def get_active_core_values() -> list[dict]:
    """Return active values, oldest first. Empty list on failure."""
    session = SessionLocal()
    try:
        rows = (
            session.query(CoreValue)
            .filter(CoreValue.status == "active")
            .order_by(CoreValue.created_at.asc())
            .all()
        )
        return [_row_to_dict(v) for v in rows]
    except Exception as e:
        print(f"[core_values] get_active_core_values failed: {e}")
        return []
    finally:
        session.close()


def get_pending_core_values() -> list[dict]:
    """Return pending values, oldest first. Empty list on failure."""
    session = SessionLocal()
    try:
        rows = (
            session.query(CoreValue)
            .filter(CoreValue.status == "pending")
            .order_by(CoreValue.created_at.asc())
            .all()
        )
        return [_row_to_dict(v) for v in rows]
    except Exception as e:
        print(f"[core_values] get_pending_core_values failed: {e}")
        return []
    finally:
        session.close()


def activate_core_value(value_id: int) -> bool:
    """Mark a value active and stamp activated_at. Returns False if missing or on failure."""
    session = SessionLocal()
    try:
        v = session.query(CoreValue).filter_by(id=value_id).first()
        if v is None:
            return False
        v.status = "active"
        v.activated_at = datetime.utcnow()
        session.commit()
        return True
    except Exception as e:
        session.rollback()
        print(f"[core_values] activate_core_value failed: {e}")
        return False
    finally:
        session.close()


def remove_core_value(value_id: int) -> bool:
    """Mark a value removed. Returns False if missing or on failure."""
    session = SessionLocal()
    try:
        v = session.query(CoreValue).filter_by(id=value_id).first()
        if v is None:
            return False
        v.status = "removed"
        session.commit()
        return True
    except Exception as e:
        session.rollback()
        print(f"[core_values] remove_core_value failed: {e}")
        return False
    finally:
        session.close()
