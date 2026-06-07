from datetime import datetime, timezone
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError
from database import supabase
from security import decode_token

bearer = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
) -> dict:
    try:
        user_id, token_ver = decode_token(credentials.credentials)
    except (JWTError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
        )

    result = supabase.table("users").select("*").eq("id", user_id).single().execute()
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no encontrado",
        )

    user = result.data

    # Fuerza-logout: el admin incrementó token_version, el token actual queda inválido
    if token_ver != user.get("token_version", 1):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesión cerrada por el administrador",
        )

    if not user.get("activo", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cuenta bloqueada",
        )

    fecha = user.get("fecha_vencimiento")
    if fecha:
        try:
            exp = datetime.fromisoformat(fecha.replace("Z", "+00:00"))
            if exp < datetime.now(timezone.utc):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Cuenta vencida",
                )
        except (ValueError, AttributeError):
            pass

    return user
