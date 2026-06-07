from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Form, Request
from database import supabase
from dependencies import get_current_user

router = APIRouter()

_VALID_EVENTS = {"app_open", "app_close", "capture"}


@router.post("/log")
async def log_event(
    request: Request,
    event_type: str = Form(...),
    app_version: str = Form(default="unknown"),
    current_user: dict = Depends(get_current_user),
):
    if event_type not in _VALID_EVENTS:
        return {"ok": False, "detail": "Evento no reconocido"}

    forwarded = request.headers.get("X-Forwarded-For")
    ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host or "unknown")

    try:
        supabase.table("usage_logs").insert({
            "user_id": current_user["id"],
            "event_type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ip": ip,
            "app_version": app_version,
        }).execute()
    except Exception:
        pass

    return {"ok": True}
