# Centralized auth utilities: password hashing (argon2) and JWT (PyJWT).
# All other modules import from here - never call argon2/jwt directly elsewhere.

import uuid
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import settings

# PasswordHasher singleton - instantiated once, reused across requests.
# Defaults: argon2id, time_cost=3, memory_cost=65536 (64MB), parallelism=4.
# These are the PHC recommended parameters as of 2024.
_ph = PasswordHasher()


# --- Password Hashing -----------------------------------------------------------

def hash_password(password: str) -> str:
    """Hash a plaintext password using argon2id. Returns the full hash string."""
    return _ph.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plaintext password against its argon2 hash.

    IMPORTANT: argon2-cffi argument order is verify(hash, password),
    NOT verify(password, hash). This is a common mistake.

    Returns False instead of raising on mismatch - callers get a simple bool.
    """
    try:
        return _ph.verify(hashed_password, plain_password)
    except VerifyMismatchError:
        # Wrong password
        return False
    except InvalidHashError:
        # Corrupted or non-argon2 hash in DB - treat as failure
        return False
    

def needs_rehash(hashed_password):
    """
    Check if a stored hash needs to be rehashed (e.g., after parameter upgrade).
    Call this after a successful login and rehash if true.
    Not used but available for future use.
    """
    return _ph.check_needs_rehash(hashed_password)


# --- JWT ------------------------------------------------------------------------

def create_access_token(user_id: uuid.UUID) -> str:
    """
    Create a short-lived access token.
    Claim 'type'='access' prevents this token from being used as a refresh token.
    """
    payload = {
        "sub": str(user_id),        # Subject - who this token belongs to
        "type": "access",           # Token type guard
        "exp": datetime.now(timezone.utc) + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        ),
        "iat": datetime.now(timezone.utc)   # Issued at
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(user_id: uuid.UUID) -> str:
    """
    Create a long-lived refresh token.
    Only used to obtain new access tokens, never to access resources directly.
    """
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "exp": datetime.now(timezone.utc) + timedelta(
            minutes=settings.REFRESH_TOKEN_EXPIRE_DAYS
        ),
        "iat": datetime.now(timezone.utc)   # Issued at
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> str:
    """
    Decode and validate a JWT token.
    Raises jwt.exceptions.InvalidTokenError (and subclasses) on failure.
    Callers are responsible for catching and converting to HTTPException.
    """
    return jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM]
    )