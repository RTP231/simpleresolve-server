import base64
import io
import os
import time
import pyotp
import qrcode
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr
from database import supabase
from security import hash_password, SECRET_KEY, ALGORITHM

load_dotenv()

router = APIRouter()
_bearer = HTTPBearer()

# ── Rate limiting (en memoria, se reinicia con el proceso) ────────────────────
_rate_limits: dict[str, dict] = {}
_MAX_ATTEMPTS = 5
_BLOCK_SECONDS = 900  # 15 minutos


def _get_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    return forwarded.split(",")[0].strip() if forwarded else (request.client.host or "unknown")


def _check_rate_limit(ip: str) -> None:
    entry = _rate_limits.get(ip)
    if not entry:
        return
    if entry["blocked_until"] > time.time():
        secs = int(entry["blocked_until"] - time.time())
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"IP bloqueada. Intenta en {secs // 60}m {secs % 60}s.",
        )


def _record_fail(ip: str) -> None:
    entry = _rate_limits.get(ip, {"attempts": 0, "blocked_until": 0})
    entry["attempts"] += 1
    if entry["attempts"] >= _MAX_ATTEMPTS:
        entry["blocked_until"] = time.time() + _BLOCK_SECONDS
        entry["attempts"] = 0
    _rate_limits[ip] = entry


def _reset_rate_limit(ip: str) -> None:
    _rate_limits.pop(ip, None)


# ── TOTP ──────────────────────────────────────────────────────────────────────
def _get_totp_secret() -> tuple[str, bool]:
    """Devuelve (secret, es_primera_vez)."""
    env_secret = os.environ.get("ADMIN_TOTP_SECRET", "").strip()
    if env_secret:
        return env_secret, False

    result = supabase.table("admin_config").select("value").eq("key", "totp_secret").execute()
    if result.data:
        return result.data[0]["value"], False

    new_secret = pyotp.random_base32()
    supabase.table("admin_config").insert({"key": "totp_secret", "value": new_secret}).execute()
    return new_secret, True


# ── JWT admin ─────────────────────────────────────────────────────────────────
def _make_step1_token() -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=5)
    return jwt.encode({"sub": "admin", "type": "admin_step1", "exp": exp}, SECRET_KEY, algorithm=ALGORITHM)


def _make_admin_token() -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=2)
    return jwt.encode({"sub": "admin", "type": "admin", "exp": exp}, SECRET_KEY, algorithm=ALGORITHM)


def _decode_admin_token(token: str, expected_type: str) -> None:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token inválido o expirado")
    if payload.get("type") != expected_type or payload.get("sub") != "admin":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token inválido")


async def _require_step1(creds: HTTPAuthorizationCredentials = Depends(_bearer)) -> None:
    _decode_admin_token(creds.credentials, "admin_step1")


async def _require_admin(creds: HTTPAuthorizationCredentials = Depends(_bearer)) -> None:
    _decode_admin_token(creds.credentials, "admin")


# ── Schemas ───────────────────────────────────────────────────────────────────
class PasswordBody(BaseModel):
    password: str


class TotpBody(BaseModel):
    code: str


class CreateUserBody(BaseModel):
    email: EmailStr
    password: str
    captures_limite: int = 200
    dias_acceso: int = 30


class UpdateUserBody(BaseModel):
    captures_remaining: int | None = None
    captures_limite: int | None = None
    dias_acceso: int | None = None
    activo: bool | None = None


# ── Endpoints de autenticación ────────────────────────────────────────────────
@router.post("/auth/password")
async def auth_password(body: PasswordBody, request: Request):
    ip = _get_ip(request)
    _check_rate_limit(ip)

    admin_password = os.environ.get("ADMIN_PASSWORD", "").strip()
    if not admin_password:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                            "ADMIN_PASSWORD no configurada en el servidor.")

    if body.password != admin_password:
        _record_fail(ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Contraseña incorrecta.")

    _reset_rate_limit(ip)

    secret, is_new = _get_totp_secret()
    step1_token = _make_step1_token()

    response: dict = {"step1_token": step1_token, "totp_setup": is_new}
    if is_new:
        totp = pyotp.TOTP(secret)
        uri = totp.provisioning_uri(name="Admin", issuer_name="SimpleResolve")
        img = qrcode.make(uri)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        response["qr_image"] = base64.b64encode(buf.getvalue()).decode()
        response["totp_secret"] = secret

    return response


@router.post("/auth/totp", dependencies=[Depends(_require_step1)])
async def auth_totp(body: TotpBody, request: Request):
    ip = _get_ip(request)
    _check_rate_limit(ip)

    secret, _ = _get_totp_secret()
    totp = pyotp.TOTP(secret)

    if not totp.verify(body.code.strip(), valid_window=1):
        _record_fail(ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Código incorrecto.")

    _reset_rate_limit(ip)
    return {"access_token": _make_admin_token(), "token_type": "bearer"}


# ── Gestión de usuarios ───────────────────────────────────────────────────────
@router.get("/users", dependencies=[Depends(_require_admin)])
async def list_users():
    result = supabase.table("users").select(
        "id,email,captures_remaining,captures_limite,fecha_vencimiento,activo,created_at"
    ).order("created_at", desc=True).execute()
    return result.data


@router.post("/users", status_code=201, dependencies=[Depends(_require_admin)])
async def create_user(body: CreateUserBody):
    existing = supabase.table("users").select("id").eq("email", body.email).execute()
    if existing.data:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email ya registrado.")

    fecha_venc = (datetime.now(timezone.utc) + timedelta(days=body.dias_acceso)).isoformat()
    result = supabase.table("users").insert({
        "email": body.email,
        "hashed_password": hash_password(body.password),
        "captures_remaining": body.captures_limite,
        "captures_limite": body.captures_limite,
        "fecha_vencimiento": fecha_venc,
        "activo": True,
    }).execute()
    return result.data[0]


@router.patch("/users/{user_id}", dependencies=[Depends(_require_admin)])
async def update_user(user_id: str, body: UpdateUserBody):
    updates: dict = {}

    if body.captures_remaining is not None:
        updates["captures_remaining"] = body.captures_remaining
    if body.captures_limite is not None:
        updates["captures_limite"] = body.captures_limite
    if body.activo is not None:
        updates["activo"] = body.activo

    if body.dias_acceso is not None:
        user_result = supabase.table("users").select("fecha_vencimiento").eq("id", user_id).single().execute()
        if not user_result.data:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado.")
        raw = user_result.data.get("fecha_vencimiento")
        try:
            base = datetime.fromisoformat(raw.replace("Z", "+00:00")) if raw else None
        except (ValueError, AttributeError):
            base = None
        # Si ya venció o no tiene fecha, extender desde hoy
        now = datetime.now(timezone.utc)
        if not base or base < now:
            base = now
        updates["fecha_vencimiento"] = (base + timedelta(days=body.dias_acceso)).isoformat()

    if not updates:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Sin cambios que aplicar.")

    result = supabase.table("users").update(updates).eq("id", user_id).execute()
    if not result.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado.")
    return result.data[0]


@router.delete("/users/{user_id}", dependencies=[Depends(_require_admin)])
async def delete_user(user_id: str):
    result = supabase.table("users").delete().eq("id", user_id).execute()
    if not result.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado.")
    return {"ok": True}
