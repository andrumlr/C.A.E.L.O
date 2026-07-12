from fastapi import APIRouter
from memory.core_values import (
    activate_core_value,
    get_active_core_values,
    get_pending_core_values,
    remove_core_value,
)

router = APIRouter()


@router.get("/")
def get_core_values():
    return {
        "active": get_active_core_values(),
        "pending": get_pending_core_values(),
    }


@router.post("/{value_id}/activate")
def activate(value_id: int):
    return {"ok": activate_core_value(value_id)}


@router.post("/{value_id}/remove")
def remove(value_id: int):
    return {"ok": remove_core_value(value_id)}
