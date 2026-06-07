from fastapi import APIRouter, HTTPException, status, Depends
from schemas import RegisterRequest, LoginRequest, Token, UserResponse
from database import supabase
from security import verify_password, hash_password, create_access_token
from dependencies import get_current_user

router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest):
    existing = supabase.table("users").select("id").eq("email", body.email).execute()
    if existing.data:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email ya registrado",
        )

    result = supabase.table("users").insert({
        "email": body.email,
        "hashed_password": hash_password(body.password),
        "captures_remaining": 200,
    }).execute()
    return result.data[0]


@router.post("/login", response_model=Token)
async def login(body: LoginRequest):
    result = supabase.table("users").select("*").eq("email", body.email).execute()
    user = result.data[0] if result.data else None

    if not user or not verify_password(body.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos",
        )
    return {"access_token": create_access_token(user["id"]), "token_type": "bearer"}


@router.get("/me", response_model=UserResponse)
async def me(current_user: dict = Depends(get_current_user)):
    return current_user


@router.get("/verify", status_code=status.HTTP_200_OK)
async def verify(current_user: dict = Depends(get_current_user)):
    return {"valid": True}
