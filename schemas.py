from pydantic import BaseModel, EmailStr


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: str
    email: str
    captures_remaining: int


class AnalyzeResponse(BaseModel):
    answer: str
    captures_remaining: int


class StatusResponse(BaseModel):
    captures_remaining: int
    has_captures: bool
