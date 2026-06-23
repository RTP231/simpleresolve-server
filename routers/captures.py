import os
from google import genai
from google.genai import types
from google.genai.errors import APIError, ClientError
from datetime import datetime, date, timezone
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from schemas import AnalyzeResponse, StatusResponse
from database import supabase
from dependencies import get_current_user

load_dotenv()

router = APIRouter()

GEMINI_MODEL = "gemini-2.5-pro"

ALLOWED_MEDIA_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/gif", "image/webp"}

SYSTEM_PROMPT = """You are a precise answer extraction system with expert-level mathematics. Look at the image, identify the question, and solve it with full mathematical rigor. Respond with ONLY the final answer.

For calculus and math problems, apply rules correctly before answering:
- Derivatives: use chain rule, product rule, quotient rule as needed
- Logarithmic differentiation: ln(uv)=ln(u)+ln(v), ln(u/v)=ln(u)-ln(v), ln(u^n)=n·ln(u)
- Integrals: apply substitution, integration by parts, or standard forms correctly
- Simplify fully before giving the answer

Examples:
- Math/calculus result → just the expression or number: '3x²+2' or '3961.92'
- Multiple choice → just the letter: 'B'
- True/false → one word: 'True'
- Fill in blank → the word/phrase only
- Any question → direct answer, max 5 words, no explanation

Never show steps. Never explain. Never add text before or after the answer."""


def _get_gemini():
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GEMINI_API_KEY no configurada en el servidor.",
        )
    return genai.Client(api_key=api_key)


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    request: Request,
    image: UploadFile = File(...),
    prompt: str = Form(default=""),  # ignorado — el prompt vive en SYSTEM_PROMPT
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
            detail=f"Tipo de imagen no soportado: {media_type}.",
        )

    image_bytes = await image.read()

    gemini = _get_gemini()

    try:
        response = gemini.models.generate_content(
            model=GEMINI_MODEL,
            contents=[types.Part.from_bytes(data=image_bytes, mime_type=media_type)],
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                max_output_tokens=256,
            ),
        )
    except ClientError as exc:
        mensaje = getattr(exc, "message", None) or str(exc)
        if "api key" in mensaje.lower():
            raise HTTPException(status_code=500, detail="GEMINI_API_KEY inválida o revocada.")
        raise HTTPException(status_code=502, detail=f"Error en la API de Gemini: {mensaje}")
    except APIError as exc:
        raise HTTPException(status_code=503, detail=f"No se pudo conectar a Gemini: {exc}")

    answer = (response.text or "").strip()

    now_utc = datetime.now(timezone.utc)
    today = now_utc.date()
    forwarded = request.headers.get("X-Forwarded-For")
    ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host or "unknown")
    app_version = request.headers.get("X-App-Version", "unknown")

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

    try:
        supabase.table("usage_logs").insert({
            "user_id": current_user["id"],
            "event_type": "capture",
            "timestamp": now_utc.isoformat(),
            "ip": ip,
            "app_version": app_version,
        }).execute()
    except Exception:
        pass

    return {"answer": answer, "captures_remaining": new_count}


@router.get("/status", response_model=StatusResponse)
async def captures_status(current_user: dict = Depends(get_current_user)):
    remaining = current_user["captures_remaining"]
    return {"captures_remaining": remaining, "has_captures": remaining > 0}
