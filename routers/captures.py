import os
import base64
import anthropic
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from schemas import AnalyzeResponse, StatusResponse
from database import supabase
from dependencies import get_current_user

router = APIRouter()

ALLOWED_MEDIA_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/gif", "image/webp"}

_claude = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


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

    try:
        with _claude.messages.stream(
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
    except anthropic.APIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Error en la API de Claude: {exc.message}",
        )

    answer = next(
        (block.text for block in message.content if block.type == "text"), ""
    )

    new_count = current_user["captures_remaining"] - 1
    supabase.table("users").update({"captures_remaining": new_count}).eq(
        "id", current_user["id"]
    ).execute()

    return {"answer": answer, "captures_remaining": new_count}


@router.get("/status", response_model=StatusResponse)
async def captures_status(current_user: dict = Depends(get_current_user)):
    remaining = current_user["captures_remaining"]
    return {"captures_remaining": remaining, "has_captures": remaining > 0}
