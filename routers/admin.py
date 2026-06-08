import base64
import io
import os
import secrets
import string
import time
import httpx
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


class NotesBody(BaseModel):
    notes: str


class PriceBody(BaseModel):
    price: float


class WelcomeEmailBody(BaseModel):
    email_destino: EmailStr
    temp_password: str


class ReloadCapturesBody(BaseModel):
    amount:         int
    email_destino:  EmailStr | None = None  # email real del cliente (distinto al email de cuenta)


class CreateWithWelcomeBody(BaseModel):
    email_destino:   EmailStr
    email_cuenta:    EmailStr
    password_cuenta: str
    captures_limite: int = 200
    dias_acceso:     int = 30


# ── Email helpers ─────────────────────────────────────────────────────────────
async def _send_resend_email(to: str, subject: str, html: str) -> str:
    api_key = os.environ.get("BREVO_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "BREVO_API_KEY no configurada en Railway.",
        )
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={"api-key": api_key, "Content-Type": "application/json"},
            json={
                "sender":      {"name": "SimpleResolve", "email": "simpleresolveht@gmail.com"},
                "to":          [{"email": to}],
                "subject":     subject,
                "htmlContent": html,
            },
        )
    if not resp.is_success:
        try:
            err_msg = resp.json().get("message", resp.text[:200])
        except Exception:
            err_msg = resp.text[:200]
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Error Brevo ({resp.status_code}): {err_msg}")
    return resp.json().get("messageId", "")


def _fmt_dt(iso_str: str | None) -> str:
    if not iso_str:
        return datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%Y %H:%M UTC")
    except Exception:
        return datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")


def _welcome_html(email: str, password: str, purchase_iso: str | None, sent_iso: str | None = None) -> str:
    download_url = os.environ.get("DOWNLOAD_URL", "#")
    purchase_str = _fmt_dt(purchase_iso)
    sent_str     = _fmt_dt(sent_iso) if sent_iso else datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<meta name="color-scheme" content="dark light">
<title>Bienvenido a SimpleResolve</title>
</head>
<body style="margin:0;padding:0;background-color:#0f0f1a;font-family:Arial,'Helvetica Neue',Helvetica,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#0f0f1a;">
<tr><td align="center" style="padding:40px 16px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:580px;background-color:#141424;border-radius:16px;border:1px solid rgba(99,89,255,0.15);">
  <tr>
    <td align="center" bgcolor="#2d1f7a" style="background:linear-gradient(135deg,#6c47ff,#3b82f6);border-radius:16px 16px 0 0;padding:28px 36px;">
      <div style="font-size:26px;font-weight:700;color:#ffffff;letter-spacing:-0.5px;font-family:Arial,sans-serif;">SimpleResolve</div>
    </td>
  </tr>
  <tr>
    <td style="padding:32px 36px;">
      <h2 style="color:#ffffff;font-size:20px;font-weight:700;margin:0 0 10px;font-family:Arial,sans-serif;">¡Bienvenido!</h2>
      <p style="color:#a0a0c0;font-size:14px;line-height:1.7;margin:0 0 26px;font-family:Arial,sans-serif;">Tu acceso ha sido activado. Aquí están tus credenciales para iniciar sesión:</p>
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#0a0a18;border:1px solid rgba(74,222,128,0.2);border-radius:12px;margin-bottom:24px;">
      <tr><td style="padding:22px 24px;">
        <div style="margin-bottom:18px;">
          <div style="font-size:10px;font-weight:700;color:#55547a;text-transform:uppercase;letter-spacing:1.2px;margin-bottom:6px;font-family:Arial,sans-serif;">Email de acceso</div>
          <div style="font-size:15px;color:#e8e8f5;font-weight:600;font-family:Arial,sans-serif;">{email}</div>
        </div>
        <div style="border-top:1px solid rgba(74,222,128,0.1);padding-top:16px;">
          <div style="font-size:10px;font-weight:700;color:#55547a;text-transform:uppercase;letter-spacing:1.2px;margin-bottom:8px;font-family:Arial,sans-serif;">Contraseña</div>
          <table role="presentation" cellpadding="0" cellspacing="0" border="0">
          <tr><td style="background-color:#060610;border:1px solid rgba(74,222,128,0.15);border-radius:8px;padding:10px 16px;">
            <span style="font-size:18px;font-weight:700;color:#4ade80;font-family:'Courier New',Courier,monospace;letter-spacing:3px;">{password}</span>
          </td></tr>
          </table>
        </div>
      </td></tr>
      </table>
      <div style="margin-bottom:24px;">
        <div style="font-size:10px;font-weight:700;color:#6c47ff;text-transform:uppercase;letter-spacing:1px;margin-bottom:14px;font-family:Arial,sans-serif;">Cómo empezar</div>
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
          <tr><td style="padding:8px 0;border-bottom:1px solid rgba(99,89,255,0.08);">
            <span style="font-size:12px;font-weight:800;color:#6c47ff;font-family:Arial,sans-serif;margin-right:14px;">01</span>
            <span style="font-size:13px;color:#a0a0c0;font-family:Arial,sans-serif;">Descarga e instala la aplicación</span>
          </td></tr>
          <tr><td style="padding:8px 0;border-bottom:1px solid rgba(99,89,255,0.08);">
            <span style="font-size:12px;font-weight:800;color:#6c47ff;font-family:Arial,sans-serif;margin-right:14px;">02</span>
            <span style="font-size:13px;color:#a0a0c0;font-family:Arial,sans-serif;">Inicia sesión con tu email y contraseña</span>
          </td></tr>
          <tr><td style="padding:8px 0;">
            <span style="font-size:12px;font-weight:800;color:#6c47ff;font-family:Arial,sans-serif;margin-right:14px;">03</span>
            <span style="font-size:13px;color:#a0a0c0;font-family:Arial,sans-serif;">¡Listo! Ya puedes usar SimpleResolve</span>
          </td></tr>
        </table>
      </div>
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:24px;">
      <tr><td align="center">
        <a href="{download_url}" style="display:inline-block;background:linear-gradient(135deg,#6c47ff,#3b82f6);color:#ffffff;font-size:15px;font-weight:700;text-decoration:none;padding:14px 40px;border-radius:10px;font-family:Arial,sans-serif;">Descargar SimpleResolve &rarr;</a>
      </td></tr>
      </table>
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#0d0d1a;border:1px solid rgba(99,89,255,0.08);border-radius:8px;margin-bottom:22px;">
      <tr><td style="padding:14px 18px;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
          <tr>
            <td style="font-size:11px;color:#55547a;font-family:Arial,sans-serif;padding-bottom:5px;">Fecha de compra</td>
            <td align="right" style="font-size:11px;color:#8080a0;font-weight:600;font-family:Arial,sans-serif;padding-bottom:5px;">{purchase_str}</td>
          </tr>
          <tr>
            <td style="font-size:11px;color:#55547a;font-family:Arial,sans-serif;border-top:1px solid rgba(99,89,255,0.06);padding-top:5px;">Email enviado</td>
            <td align="right" style="font-size:11px;color:#8080a0;font-weight:600;font-family:Arial,sans-serif;border-top:1px solid rgba(99,89,255,0.06);padding-top:5px;">{sent_str}</td>
          </tr>
        </table>
      </td></tr>
      </table>
      <div style="background-color:#0d0d1a;border:1px solid rgba(99,89,255,0.08);border-radius:8px;padding:14px 18px;margin-bottom:20px;">
        <div style="font-size:10px;font-weight:700;color:#6c47ff;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;font-family:Arial,sans-serif;">Términos de uso</div>
        <p style="font-size:11px;color:#6a6a8a;line-height:1.7;margin:0;font-family:Arial,sans-serif;">Al usar SimpleResolve aceptas que: (1) el software es para uso estrictamente personal; (2) queda prohibido compartir credenciales con terceros; (3) el desarrollador no se hace responsable del uso que el usuario final dé a la aplicación; (4) cualquier uso indebido o ilegal es responsabilidad exclusiva del usuario; (5) el uso fuera de estos términos resultará en suspensión inmediata sin reembolso; (6) cada captura descuenta del saldo mensual disponible; (7) SimpleResolve no ofrece reembolsos bajo ninguna circunstancia una vez activado el acceso.</p>
      </div>
      <p style="font-size:11px;color:#44445a;text-align:center;line-height:1.6;margin:0;font-family:Arial,sans-serif;">¿Problemas con tu acceso? Responde a este correo.<br>Generado automáticamente por SimpleResolve.</p>
    </td>
  </tr>
  <tr>
    <td style="background-color:#0d0d1a;border-top:1px solid rgba(99,89,255,0.08);border-radius:0 0 16px 16px;padding:14px 36px;text-align:center;">
      <span style="font-size:11px;color:#44445a;font-family:Arial,sans-serif;">&copy; 2025 SimpleResolve &middot; Todos los derechos reservados</span>
    </td>
  </tr>
</table>
</td></tr>
</table>
</body>
</html>"""


def _reload_html(email: str, amount: int, total_after: int, sent_iso: str | None = None) -> str:
    reload_str = _fmt_dt(sent_iso) if sent_iso else datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<meta name="color-scheme" content="dark light">
<title>Capturas recargadas – SimpleResolve</title>
</head>
<body style="margin:0;padding:0;background-color:#0f0f1a;font-family:Arial,'Helvetica Neue',Helvetica,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#0f0f1a;">
<tr><td align="center" style="padding:40px 16px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:580px;background-color:#141424;border-radius:16px;border:1px solid rgba(99,89,255,0.15);">
  <tr>
    <td align="center" bgcolor="#2d1f7a" style="background:linear-gradient(135deg,#6c47ff,#3b82f6);border-radius:16px 16px 0 0;padding:28px 36px;">
      <div style="font-size:26px;font-weight:700;color:#ffffff;letter-spacing:-0.5px;font-family:Arial,sans-serif;">SimpleResolve</div>
    </td>
  </tr>
  <tr>
    <td style="padding:32px 36px;">
      <h2 style="color:#ffffff;font-size:20px;font-weight:700;margin:0 0 10px;font-family:Arial,sans-serif;">&#x26A1; ¡Capturas recargadas!</h2>
      <p style="color:#a0a0c0;font-size:14px;line-height:1.7;margin:0 0 26px;font-family:Arial,sans-serif;">Hola <strong style="color:#e8e8f5;">{email}</strong>, tu saldo ha sido actualizado.</p>
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:24px;">
      <tr>
        <td width="48%" align="center" style="background-color:#0d1a0d;border:1px solid rgba(74,222,128,0.2);border-radius:12px;padding:20px 16px;">
          <div style="font-size:10px;font-weight:700;color:#3a6a3a;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;font-family:Arial,sans-serif;">Capturas agregadas</div>
          <div style="font-size:42px;font-weight:800;color:#4ade80;line-height:1;font-family:Arial,sans-serif;">+{amount}</div>
        </td>
        <td width="4%"></td>
        <td width="48%" align="center" style="background-color:#0d0d1a;border:1px solid rgba(99,89,255,0.2);border-radius:12px;padding:20px 16px;">
          <div style="font-size:10px;font-weight:700;color:#4a4a7a;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;font-family:Arial,sans-serif;">Total disponible</div>
          <div style="font-size:42px;font-weight:800;color:#8b7cf8;line-height:1;font-family:Arial,sans-serif;">{total_after}</div>
        </td>
      </tr>
      </table>
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#0d0d1a;border:1px solid rgba(99,89,255,0.08);border-radius:8px;margin-bottom:22px;">
      <tr><td style="padding:14px 18px;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
          <tr>
            <td style="font-size:11px;color:#55547a;font-family:Arial,sans-serif;">Fecha y hora de recarga</td>
            <td align="right" style="font-size:11px;color:#8080a0;font-weight:600;font-family:Arial,sans-serif;">{reload_str}</td>
          </tr>
        </table>
      </td></tr>
      </table>
      <p style="font-size:13px;color:#a0a0c0;text-align:center;line-height:1.6;margin:0 0 20px;font-family:Arial,sans-serif;">Tus capturas ya están disponibles. Abre SimpleResolve y sigue resolviendo.</p>
      <p style="font-size:11px;color:#44445a;text-align:center;line-height:1.6;margin:0;font-family:Arial,sans-serif;">Generado automáticamente por SimpleResolve.</p>
    </td>
  </tr>
  <tr>
    <td style="background-color:#0d0d1a;border-top:1px solid rgba(99,89,255,0.08);border-radius:0 0 16px 16px;padding:14px 36px;text-align:center;">
      <span style="font-size:11px;color:#44445a;font-family:Arial,sans-serif;">&copy; 2025 SimpleResolve &middot; Todos los derechos reservados</span>
    </td>
  </tr>
</table>
</td></tr>
</table>
</body>
</html>"""


def _welcome_html_full(
    email_cuenta: str,
    password: str,
    captures_limite: int,
    dias_acceso: int,
    fecha_venc_iso: str,
    created_iso: str,
) -> str:
    download_url = os.environ.get("DOWNLOAD_URL", "#")
    created_str  = _fmt_dt(created_iso)
    venc_str     = _fmt_dt(fecha_venc_iso)
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<meta name="color-scheme" content="dark light">
<title>Bienvenido a SimpleResolve</title>
</head>
<body style="margin:0;padding:0;background-color:#0f0f1a;font-family:Arial,'Helvetica Neue',Helvetica,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#0f0f1a;">
<tr><td align="center" style="padding:40px 16px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:580px;background-color:#141424;border-radius:16px;border:1px solid rgba(99,89,255,0.15);">
  <tr>
    <td align="center" bgcolor="#2d1f7a" style="background:linear-gradient(135deg,#6c47ff,#3b82f6);border-radius:16px 16px 0 0;padding:28px 36px;">
      <div style="font-size:26px;font-weight:700;color:#ffffff;letter-spacing:-0.5px;font-family:Arial,sans-serif;">SimpleResolve</div>
    </td>
  </tr>
  <tr>
    <td style="padding:32px 36px;">
      <h2 style="color:#ffffff;font-size:20px;font-weight:700;margin:0 0 10px;font-family:Arial,sans-serif;">¡Bienvenido!</h2>
      <p style="color:#a0a0c0;font-size:14px;line-height:1.7;margin:0 0 26px;font-family:Arial,sans-serif;">Tu acceso ha sido activado. Aquí están tus credenciales para iniciar sesión:</p>
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#0a0a18;border:1px solid rgba(74,222,128,0.2);border-radius:12px;margin-bottom:24px;">
      <tr><td style="padding:22px 24px;">
        <div style="margin-bottom:18px;">
          <div style="font-size:10px;font-weight:700;color:#55547a;text-transform:uppercase;letter-spacing:1.2px;margin-bottom:6px;font-family:Arial,sans-serif;">Email de acceso</div>
          <div style="font-size:15px;color:#e8e8f5;font-weight:600;font-family:Arial,sans-serif;">{email_cuenta}</div>
        </div>
        <div style="border-top:1px solid rgba(74,222,128,0.1);padding-top:16px;">
          <div style="font-size:10px;font-weight:700;color:#55547a;text-transform:uppercase;letter-spacing:1.2px;margin-bottom:8px;font-family:Arial,sans-serif;">Contraseña</div>
          <table role="presentation" cellpadding="0" cellspacing="0" border="0">
          <tr><td style="background-color:#060610;border:1px solid rgba(74,222,128,0.15);border-radius:8px;padding:10px 16px;">
            <span style="font-size:18px;font-weight:700;color:#4ade80;font-family:'Courier New',Courier,monospace;letter-spacing:3px;">{password}</span>
          </td></tr>
          </table>
        </div>
      </td></tr>
      </table>
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:24px;">
      <tr>
        <td width="48%" valign="top" style="background-color:#0d1a0d;border:1px solid rgba(74,222,128,0.15);border-radius:10px;padding:16px 18px;">
          <div style="font-size:10px;font-weight:700;color:#3a6a3a;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px;font-family:Arial,sans-serif;">Capturas mensuales</div>
          <div style="font-size:30px;font-weight:800;color:#4ade80;line-height:1;margin-bottom:6px;font-family:Arial,sans-serif;">{captures_limite}</div>
          <div style="font-size:10px;color:#3a5a3a;line-height:1.5;font-family:Arial,sans-serif;">Se reinician a {captures_limite} cada mes.<br>Puedes recargar si se agotan.</div>
        </td>
        <td width="4%"></td>
        <td width="48%" valign="top" style="background-color:#0d0d1a;border:1px solid rgba(99,89,255,0.15);border-radius:10px;padding:16px 18px;">
          <div style="font-size:10px;font-weight:700;color:#4a4a7a;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px;font-family:Arial,sans-serif;">Vigencia</div>
          <div style="font-size:30px;font-weight:800;color:#8b7cf8;line-height:1;margin-bottom:6px;font-family:Arial,sans-serif;">{dias_acceso}d</div>
          <div style="font-size:10px;color:#4a4a6a;line-height:1.5;font-family:Arial,sans-serif;">Vence el:<br>{venc_str}</div>
        </td>
      </tr>
      </table>
      <div style="margin-bottom:24px;">
        <div style="font-size:10px;font-weight:700;color:#6c47ff;text-transform:uppercase;letter-spacing:1px;margin-bottom:14px;font-family:Arial,sans-serif;">Cómo empezar</div>
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
          <tr><td style="padding:8px 0;border-bottom:1px solid rgba(99,89,255,0.08);">
            <span style="font-size:12px;font-weight:800;color:#6c47ff;font-family:Arial,sans-serif;margin-right:14px;">01</span>
            <span style="font-size:13px;color:#a0a0c0;font-family:Arial,sans-serif;">Descarga e instala la aplicación</span>
          </td></tr>
          <tr><td style="padding:8px 0;border-bottom:1px solid rgba(99,89,255,0.08);">
            <span style="font-size:12px;font-weight:800;color:#6c47ff;font-family:Arial,sans-serif;margin-right:14px;">02</span>
            <span style="font-size:13px;color:#a0a0c0;font-family:Arial,sans-serif;">Inicia sesión con tu email y contraseña</span>
          </td></tr>
          <tr><td style="padding:8px 0;">
            <span style="font-size:12px;font-weight:800;color:#6c47ff;font-family:Arial,sans-serif;margin-right:14px;">03</span>
            <span style="font-size:13px;color:#a0a0c0;font-family:Arial,sans-serif;">¡Listo! Ya puedes usar SimpleResolve</span>
          </td></tr>
        </table>
      </div>
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:24px;">
      <tr><td align="center">
        <a href="{download_url}" style="display:inline-block;background:linear-gradient(135deg,#6c47ff,#3b82f6);color:#ffffff;font-size:15px;font-weight:700;text-decoration:none;padding:14px 40px;border-radius:10px;font-family:Arial,sans-serif;">Descargar SimpleResolve &rarr;</a>
      </td></tr>
      </table>
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#0d0d1a;border:1px solid rgba(99,89,255,0.08);border-radius:8px;margin-bottom:22px;">
      <tr><td style="padding:14px 18px;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
          <tr>
            <td style="font-size:11px;color:#55547a;font-family:Arial,sans-serif;padding-bottom:5px;">Fecha y hora de activación</td>
            <td align="right" style="font-size:11px;color:#8080a0;font-weight:600;font-family:Arial,sans-serif;padding-bottom:5px;">{created_str}</td>
          </tr>
          <tr>
            <td style="font-size:11px;color:#55547a;font-family:Arial,sans-serif;border-top:1px solid rgba(99,89,255,0.06);padding-top:5px;">Vencimiento de cuenta</td>
            <td align="right" style="font-size:11px;color:#8080a0;font-weight:600;font-family:Arial,sans-serif;border-top:1px solid rgba(99,89,255,0.06);padding-top:5px;">{venc_str}</td>
          </tr>
        </table>
      </td></tr>
      </table>
      <div style="background-color:#0d0d1a;border:1px solid rgba(99,89,255,0.08);border-radius:8px;padding:14px 18px;margin-bottom:20px;">
        <div style="font-size:10px;font-weight:700;color:#6c47ff;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;font-family:Arial,sans-serif;">Términos de uso</div>
        <p style="font-size:11px;color:#6a6a8a;line-height:1.7;margin:0;font-family:Arial,sans-serif;">Al usar SimpleResolve aceptas que: (1) el software es para uso estrictamente personal; (2) queda prohibido compartir credenciales con terceros; (3) el desarrollador no se hace responsable del uso que el usuario final dé a la aplicación; (4) cualquier uso indebido o ilegal es responsabilidad exclusiva del usuario; (5) el uso fuera de estos términos resultará en suspensión inmediata sin reembolso; (6) cada captura descuenta del saldo mensual disponible; (7) SimpleResolve no ofrece reembolsos bajo ninguna circunstancia una vez activado el acceso.</p>
      </div>
      <p style="font-size:11px;color:#44445a;text-align:center;line-height:1.6;margin:0;font-family:Arial,sans-serif;">¿Problemas con tu acceso? Responde a este correo.<br>Generado automáticamente por SimpleResolve.</p>
    </td>
  </tr>
  <tr>
    <td style="background-color:#0d0d1a;border-top:1px solid rgba(99,89,255,0.08);border-radius:0 0 16px 16px;padding:14px 36px;text-align:center;">
      <span style="font-size:11px;color:#44445a;font-family:Arial,sans-serif;">&copy; 2025 SimpleResolve &middot; Todos los derechos reservados</span>
    </td>
  </tr>
</table>
</td></tr>
</table>
</body>
</html>"""


def _log_email(user_id: str, email_type: str, brevo_id: str = "", metadata: dict | None = None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    try:
        supabase.table("email_logs").insert({
            "user_id":  user_id,
            "type":     email_type,
            "sent_at":  now,
            "status":   "sent",
            "metadata": metadata or {},
            "brevo_id": brevo_id,
        }).execute()
        supabase.table("users").update({"last_email_at": now}).eq("id", user_id).execute()
    except Exception:
        pass


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
@router.get("/stats", dependencies=[Depends(_require_admin)])
async def get_stats():
    now = datetime.now(timezone.utc)
    seven_days_ago = now - timedelta(days=7)
    yesterday = now - timedelta(hours=24)

    # Capturas por día (últimos 7 días)
    cap_logs = supabase.table("usage_logs").select("timestamp").eq(
        "event_type", "capture"
    ).gte("timestamp", seven_days_ago.isoformat()).execute()

    daily: dict[str, int] = {}
    for i in range(7):
        day = (now - timedelta(days=6 - i)).strftime("%Y-%m-%d")
        daily[day] = 0
    for log in cap_logs.data or []:
        day = (log.get("timestamp") or "")[:10]
        if day in daily:
            daily[day] += 1

    # Actividad últimas 24h
    events_24h = supabase.table("usage_logs").select(
        "event_type,user_id"
    ).gte("timestamp", yesterday.isoformat()).execute()
    ev = events_24h.data or []
    opens_24h   = sum(1 for e in ev if e["event_type"] == "app_open")
    caps_24h    = sum(1 for e in ev if e["event_type"] == "capture")
    unique_24h  = len(set(e["user_id"] for e in ev if e.get("user_id")))

    # Usuarios activos
    all_users = supabase.table("users").select("activo,fecha_vencimiento").execute()
    active_count = sum(
        1 for u in (all_users.data or [])
        if u.get("activo", True) and (
            not u.get("fecha_vencimiento") or
            u["fecha_vencimiento"] > now.isoformat()
        )
    )

    # Precio configurado
    price_r = supabase.table("admin_config").select("value").eq("key", "price").execute()
    price = float(price_r.data[0]["value"]) if price_r.data else 0.0

    return {
        "chart": [{"date": d, "count": c} for d, c in daily.items()],
        "activity_24h": {"opens": opens_24h, "captures": caps_24h, "unique_users": unique_24h},
        "active_users": active_count,
        "price": price,
        "revenue": round(active_count * price, 2),
    }


@router.get("/anthropic-usage", dependencies=[Depends(_require_admin)])
async def get_anthropic_usage():
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "ANTHROPIC_API_KEY no configurada.")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.anthropic.com/v1/usage",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
            )
        if resp.status_code == 401:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "API key de Anthropic inválida.")
        if not resp.is_success:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Anthropic respondió {resp.status_code}.")
        data = resp.json()
        input_tokens  = int(data.get("input_tokens")  or 0)
        output_tokens = int(data.get("output_tokens") or 0)
        cost_raw      = data.get("cost_usd") or data.get("total_cost") or data.get("cost") or 0
        return {
            "input_tokens":  input_tokens,
            "output_tokens": output_tokens,
            "total_tokens":  input_tokens + output_tokens,
            "cost_usd":      round(float(cost_raw), 4),
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "No se pudo conectar con Anthropic.")


@router.post("/config/price", dependencies=[Depends(_require_admin)])
async def set_price(body: PriceBody):
    existing = supabase.table("admin_config").select("key").eq("key", "price").execute()
    if existing.data:
        supabase.table("admin_config").update({"value": str(body.price)}).eq("key", "price").execute()
    else:
        supabase.table("admin_config").insert({"key": "price", "value": str(body.price)}).execute()
    return {"price": body.price}


@router.get("/users", dependencies=[Depends(_require_admin)])
async def list_users():
    result = supabase.table("users").select(
        "id,email,captures_remaining,captures_limite,fecha_vencimiento,activo,created_at,last_seen,"
        "captures_used_today,welcome_sent_at,welcome_opened_at,last_email_at"
    ).order("created_at", desc=True).execute()
    return result.data


@router.get("/users/{user_id}/details", dependencies=[Depends(_require_admin)])
async def user_details(user_id: str):
    user_result = supabase.table("users").select(
        "id,email,captures_remaining,captures_limite,created_at,last_seen,activo,"
        "captures_used_today,last_capture_date,notes,token_version"
    ).eq("id", user_id).single().execute()

    if not user_result.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado.")

    user = user_result.data

    login_logs = supabase.table("login_logs").select(
        "logged_at,ip"
    ).eq("user_id", user_id).order("logged_at", desc=True).limit(10).execute()

    timeline = supabase.table("usage_logs").select(
        "event_type,timestamp,ip,app_version"
    ).eq("user_id", user_id).order("timestamp", desc=True).limit(20).execute()

    failed = supabase.table("failed_logins").select(
        "attempted_at,ip"
    ).eq("email", user.get("email", "")).order("attempted_at", desc=True).limit(5).execute()

    # Anomalía IP: 2 IPs distintas en los últimos 10 minutos
    now = datetime.now(timezone.utc)
    recent_logs = [
        l for l in (login_logs.data or [])
        if l.get("logged_at") and
        (now - datetime.fromisoformat(l["logged_at"].replace("Z", "+00:00"))).seconds < 600
    ]
    ip_anomaly = len(set(l["ip"] for l in recent_logs)) > 1

    limite    = user.get("captures_limite") or 0
    remaining = user.get("captures_remaining") or 0

    return {
        "user": user,
        "captures_used_total": max(0, limite - remaining),
        "captures_used_today": user.get("captures_used_today") or 0,
        "login_logs": login_logs.data,
        "timeline": timeline.data,
        "failed_logins": failed.data,
        "failed_count": len(failed.data or []),
        "ip_anomaly": ip_anomaly,
    }


@router.patch("/users/{user_id}/notes", dependencies=[Depends(_require_admin)])
async def update_notes(user_id: str, body: NotesBody):
    result = supabase.table("users").update(
        {"notes": body.notes}
    ).eq("id", user_id).execute()
    if not result.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado.")
    return {"ok": True}


@router.post("/users/{user_id}/force-logout", dependencies=[Depends(_require_admin)])
async def force_logout(user_id: str):
    user_r = supabase.table("users").select("token_version").eq("id", user_id).single().execute()
    if not user_r.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado.")
    new_ver = (user_r.data.get("token_version") or 1) + 1
    supabase.table("users").update({"token_version": new_ver}).eq("id", user_id).execute()
    return {"ok": True, "token_version": new_ver}


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


@router.post("/users/create-with-welcome", status_code=201, dependencies=[Depends(_require_admin)])
async def create_with_welcome(body: CreateWithWelcomeBody, request: Request):
    # Verificar Brevo antes de tocar la DB
    if not os.environ.get("BREVO_API_KEY", "").strip():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "BREVO_API_KEY no configurada en Railway.",
        )

    # Verificar que el email de cuenta no exista
    existing = supabase.table("users").select("id").eq("email", str(body.email_cuenta)).execute()
    if existing.data:
        raise HTTPException(status.HTTP_409_CONFLICT, "El email de cuenta ya está en uso. Regenera las credenciales.")

    ip  = _get_ip(request)
    now = datetime.now(timezone.utc)
    fecha_venc = (now + timedelta(days=body.dias_acceso)).isoformat()
    now_iso    = now.isoformat()

    # Crear usuario en Supabase
    insert_r = supabase.table("users").insert({
        "email":              str(body.email_cuenta),
        "hashed_password":    hash_password(body.password_cuenta),
        "captures_remaining": body.captures_limite,
        "captures_limite":    body.captures_limite,
        "fecha_vencimiento":  fecha_venc,
        "activo":             True,
        "created_by_ip":      ip,
    }).execute()

    if not insert_r.data:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Error al crear el usuario.")

    user_id = insert_r.data[0]["id"]

    # Enviar email de bienvenida completo (rollback si falla)
    try:
        html = _welcome_html_full(
            email_cuenta    = str(body.email_cuenta),
            password        = body.password_cuenta,
            captures_limite = body.captures_limite,
            dias_acceso     = body.dias_acceso,
            fecha_venc_iso  = fecha_venc,
            created_iso     = now_iso,
        )
        email_id = await _send_resend_email(
            to      = str(body.email_destino),
            subject = "¡Bienvenido a SimpleResolve! Tus credenciales de acceso",
            html    = html,
        )
    except HTTPException as exc:
        supabase.table("users").delete().eq("id", user_id).execute()
        raise exc

    # Guardar tracking del email
    supabase.table("users").update({
        "welcome_sent_at":   now_iso,
        "welcome_resend_id": email_id,
    }).eq("id", user_id).execute()
    _log_email(user_id, "welcome", email_id)

    return {
        "id":               user_id,
        "email_cuenta":     str(body.email_cuenta),
        "password_cuenta":  body.password_cuenta,
        "email_destino":    str(body.email_destino),
        "fecha_vencimiento": fecha_venc,
        "captures_limite":  body.captures_limite,
        "welcome_sent_at":  now_iso,
    }


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


# ── Email: bienvenida ─────────────────────────────────────────────────────────
@router.post("/users/{user_id}/send-welcome", dependencies=[Depends(_require_admin)])
async def send_welcome(user_id: str, body: WelcomeEmailBody):
    user_r = supabase.table("users").select("id,email,created_at").eq("id", user_id).single().execute()
    if not user_r.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado.")
    user = user_r.data

    html = _welcome_html(body.email_destino, body.temp_password, user.get("created_at"))
    email_id = await _send_resend_email(
        to=body.email_destino,
        subject="¡Bienvenido a SimpleResolve! Tus credenciales de acceso",
        html=html,
    )

    now = datetime.now(timezone.utc).isoformat()
    supabase.table("users").update({
        "welcome_sent_at": now,
        "welcome_resend_id": email_id,
        "welcome_opened_at": None,
    }).eq("id", user_id).execute()
    _log_email(user_id, "welcome", email_id)

    return {"ok": True, "sent_at": now}


# ── Recargas de capturas ──────────────────────────────────────────────────────
@router.post("/users/{user_id}/reload-captures", dependencies=[Depends(_require_admin)])
async def reload_captures(user_id: str, body: ReloadCapturesBody):
    if body.amount < 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La cantidad debe ser al menos 1.")

    user_r = supabase.table("users").select("id,email,captures_remaining").eq("id", user_id).single().execute()
    if not user_r.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado.")
    user = user_r.data

    new_remaining = (user.get("captures_remaining") or 0) + body.amount
    supabase.table("users").update({"captures_remaining": new_remaining}).eq("id", user_id).execute()
    supabase.table("capture_reloads").insert({
        "user_id": user_id,
        "amount": body.amount,
        "captures_total_after": new_remaining,
    }).execute()

    email_sent  = False
    email_error = None
    to_addr     = body.email_destino if getattr(body, "email_destino", None) else user["email"]
    print(f"[reload_captures] Enviando email a: {to_addr!r} | capturas: +{body.amount} → {new_remaining}", flush=True)
    try:
        html     = _reload_html(to_addr, body.amount, new_remaining)
        brevo_id = await _send_resend_email(
            to      = to_addr,
            subject = f"SimpleResolve · Recarga de {body.amount} capturas",
            html    = html,
        )
        _log_email(user_id, "reload", brevo_id, {"amount": body.amount, "total_after": new_remaining})
        email_sent = True
        print(f"[reload_captures] Email enviado OK. messageId={brevo_id!r}", flush=True)
    except Exception as exc:
        email_error = str(exc)
        print(f"[reload_captures] ERROR al enviar email: {email_error}", flush=True)

    return {"ok": True, "new_remaining": new_remaining, "email_sent": email_sent, "email_error": email_error}


@router.get("/users/{user_id}/reload-history", dependencies=[Depends(_require_admin)])
async def reload_history(user_id: str):
    result = supabase.table("capture_reloads").select(
        "id,amount,captures_total_after,created_at"
    ).eq("user_id", user_id).order("created_at", desc=True).limit(50).execute()
    return result.data or []


@router.get("/users/{user_id}/email-history", dependencies=[Depends(_require_admin)])
async def email_history(user_id: str):
    result = supabase.table("email_logs").select(
        "id,type,sent_at,status,metadata,brevo_id"
    ).eq("user_id", user_id).order("sent_at", desc=True).limit(100).execute()
    return result.data or []


@router.get("/email-logs/{log_id}/preview", dependencies=[Depends(_require_admin)])
async def email_log_preview(log_id: str):
    log_r = supabase.table("email_logs").select(
        "id,user_id,type,sent_at,metadata"
    ).eq("id", log_id).single().execute()
    if not log_r.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Registro de email no encontrado.")
    log = log_r.data

    user_r = supabase.table("users").select(
        "email,captures_limite,fecha_vencimiento,created_at"
    ).eq("id", log["user_id"]).single().execute()
    if not user_r.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado.")
    user     = user_r.data
    metadata = log.get("metadata") or {}
    sent_iso = log.get("sent_at")

    if log["type"] == "welcome":
        html    = _welcome_html(user["email"], "[ contraseña oculta ]", sent_iso, sent_iso)
        subject = "¡Bienvenido a SimpleResolve! Tus credenciales de acceso"
    elif log["type"] == "reload":
        amount      = metadata.get("amount", 0)
        total_after = metadata.get("total_after", 0)
        html    = _reload_html(user["email"], amount, total_after, sent_iso)
        subject = f"SimpleResolve · Recarga de {amount} capturas"
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tipo de email no reconocido.")

    return {"subject": subject, "html": html, "type": log["type"], "sent_at": sent_iso}


# ── Webhook Resend (email.opened) ─────────────────────────────────────────────
@router.post("/email/webhook")
async def email_webhook(request: Request):
    try:
        body = await request.json()
    except Exception:
        return {"ok": True}

    if body.get("type") == "email.opened":
        email_id = (body.get("data") or {}).get("email_id")
        if email_id:
            try:
                supabase.table("users").update({
                    "welcome_opened_at": datetime.now(timezone.utc).isoformat()
                }).eq("welcome_resend_id", email_id).execute()
            except Exception:
                pass

    return {"ok": True}
