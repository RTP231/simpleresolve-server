import os
import bcrypt
from datetime import datetime, timedelta, timezone
from jose import jwt
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.environ["JWT_SECRET_KEY"]
ALGORITHM = "HS256"
TOKEN_EXPIRE_DAYS = 7


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def create_access_token(user_id: str, version: int = 1) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=TOKEN_EXPIRE_DAYS)
    return jwt.encode(
        {"sub": user_id, "exp": expire, "ver": version},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


def decode_token(token: str) -> tuple[str, int]:
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    user_id: str = payload.get("sub")
    if not user_id:
        raise ValueError("Token sin subject")
    return user_id, payload.get("ver", 1)
