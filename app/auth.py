from datetime import datetime, timedelta
from typing import Optional
import jwt
from jwt.exceptions import PyJWTError as JWTError
import bcrypt
from fastapi import HTTPException, status
from config import settings


def _prep_password(password: str) -> bytes:
    """Encode and truncate password to 72 bytes for bcrypt."""
    pw = password.encode("utf-8")
    return pw[:72] if len(pw) > 72 else pw


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(_prep_password(plain_password), hashed_password.encode("utf-8"))


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(_prep_password(password), bcrypt.gensalt()).decode("utf-8")

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def verify_token(token: str):
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials"
            )
        return username
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials"
        )