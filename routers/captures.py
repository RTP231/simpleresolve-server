import os
import base64
import anthropic
from datetime import datetime, date, timezone
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from schemas import AnalyzeResponse, StatusResponse
from database import supabase
from dependencies import get_current_user

load_dotenv()

router = APIRouter()

ALLOWED_MEDIA_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/gif", "image/webp"}


def _get_claude():
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="ANTHROPIC_API_KEY no configurada en el servidor.",
        )
    return anthropic.Anthropic(api_key=api_key)


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    image: UploadFile = File(...),
    prompt: str = Form(default="Analiza esta imagen y proporciona una respuesta detallada."),
    current_user: dict = Depends(get_current_user),
):
    if current_user["captures_remaining"] <= 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sin capturas disponibles. Límite alcanzado.",
        )

    media_type = image.content_type
    if media_type not in ALLOWED_MEDIA_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tipo de imagen no soportado: {media_type}. Usa JPEG, PNG, GIF o WebP.",
        )

    image_bytes = await image.read()
    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    claude = _get_claude()

    try:
        with claude.messages.stream(
            model="claude-opus-4-8",
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_b64,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }],
        ) as stream:
            message = stream.get_final_message()
    except anthropic.AuthenticationError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="ANTHROPIC_API_KEY inválida o revocada. Revisa la variable en Railway.",
        )
    except anthropic.APIConnectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"No se pudo conectar a la API de Anthropic: {exc}",
        )
    except anthropic.APIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Error en la API de Claude: {exc.message}",
        )

    answer = next(
        (block.text for block in message.content if block.type == "text"), ""
    )

    now_utc = datetime.now(timezone.utc)
    today = now_utc.date()

    last_date_str = current_user.get("last_capture_date")
    try:
        last_date = date.fromisoformat(last_date_str) if last_date_str else None
    except (ValueError, TypeError):
        last_date = None

    used_today = ((current_user.get("captures_used_today") or 0) + 1) if last_date == today else 1
    new_count = current_user["captures_remaining"] - 1

    supabase.table("users").update({
        "captures_remaining": new_count,
        "last_seen": now_utc.isoformat(),
        "captures_used_today": used_today,
        "last_capture_date": today.isoformat(),
    }).eq("id", current_user["id"]).execute()

    return {"answer": answer, "captures_remaining": new_count}


@router.get("/status", response_model=StatusResponse)
async def captures_status(current_user: dict = Depends(get_current_user)):
    remaining = current_user["captures_remaining"]
    return {"captures_remaining": remaining, "has_captures": remaining > 0}
