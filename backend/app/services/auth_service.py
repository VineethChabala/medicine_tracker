import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from jose import JWTError, jwt

from app.config import settings

# In-memory store for 6-digit numeric codes: code -> (subject, expire_time)
_link_codes = {}


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())


def create_access_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": subject, "exp": expire, "type": "access"}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.algorithm)


def create_refresh_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    payload = {"sub": subject, "exp": expire, "type": "refresh"}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.algorithm)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.algorithm])
    except JWTError:
        return None


def create_link_token(subject: str) -> str:
    """Short-lived token for Telegram account linking (30 minutes)."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=30)
    payload = {"sub": subject, "exp": expire, "type": "telegram_link"}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.algorithm)


def generate_short_link_code(subject: str) -> str:
    """Generates a short 6-digit code valid for 10 minutes."""
    # Garbage collection of expired codes
    now = datetime.now(timezone.utc)
    expired = [code for code, data in _link_codes.items() if data[1] < now]
    for code in expired:
        _link_codes.pop(code, None)

    # Generate unique 6-digit code
    while True:
        code = "".join(secrets.choice("0123456789") for _ in range(6))
        if code not in _link_codes:
            break

    expire = now + timedelta(minutes=10)
    _link_codes[code] = (subject, expire)
    return code


def verify_short_link_code(code: str) -> Optional[str]:
    """Verifies and returns subject if code is valid and not expired. Deletes code upon verify."""
    now = datetime.now(timezone.utc)
    if code in _link_codes:
        subject, expire = _link_codes[code]
        if expire > now:
            _link_codes.pop(code, None)
            return subject
        else:
            _link_codes.pop(code, None)
    return None
