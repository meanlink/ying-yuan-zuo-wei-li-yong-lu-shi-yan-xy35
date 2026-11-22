import hashlib
import hmac
from datetime import datetime, timedelta, timezone
import jwt
from .config import JWT_SECRET, JWT_ALGORITHM

def hash_password(password: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), b"cinema-seat", 120_000).hex()

def verify_password(password: str, expected: str) -> bool:
    return hmac.compare_digest(hash_password(password), expected)

def create_token(user_id: int, role: str, name: str) -> str:
    payload = {"sub": str(user_id), "role": role, "name": name, "exp": datetime.now(timezone.utc) + timedelta(hours=8)}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def decode_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
