from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request, status, Depends
from schemas import RegisterRequest, LoginRequest, Token, UserResponse
from database import supabase
from security import verify_password, hash_password, create_access_token
from dependencies import get_current_user

router = APIRouter()


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    return forwarded.split(",")[0].strip() if forwarded else (request.client.host or "unknown")


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest):
    existing = supabase.table("users").select("id").eq("email", body.email).execute()
    if existing.data:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email ya registrado")

    result = supabase.table("users").insert({
        "email": body.email,
        "hashed_password": hash_password(body.password),
        "captures_remaining": 200,
    }).execute()
    return result.data[0]


@router.post("/login", response_model=Token)
async def login(body: LoginRequest, request: Request):
    result = supabase.table("users").select("*").eq("email", body.email).execute()
    user = result.data[0] if result.data else None
    ip = _get_client_ip(request)

    if not user or not verify_password(body.password, user["hashed_password"]):
        try:
            supabase.table("failed_logins").insert({
                "email": body.email,
                "ip": ip,
                "attempted_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
        except Exception:
            pass
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email o contraseña incorrectos")

    now = datetime.now(timezone.utc).isoformat()
    token_ver = user.get("token_version", 1)
    try:
        supabase.table("login_logs").insert({
            "user_id": user["id"],
            "logged_at": now,
            "ip": ip,
        }).execute()
        supabase.table("users").update({"last_seen": now}).eq("id", user["id"]).execute()
    except Exception:
        pass

    return {"access_token": create_access_token(user["id"], token_ver), "token_type": "bearer"}


@router.get("/me", response_model=UserResponse)
async def me(current_user: dict = Depends(get_current_user)):
    return current_user


@router.get("/verify", status_code=status.HTTP_200_OK)
async def verify(current_user: dict = Depends(get_current_user)):
    try:
        supabase.table("users").update(
            {"last_seen": datetime.now(timezone.utc).isoformat()}
        ).eq("id", current_user["id"]).execute()
    except Exception:
        pass
    return {"valid": True}
