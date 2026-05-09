# FastAPI dependencies - injected into route handlers via Depends().
# These are the reusable building blocks for authentication and DB access.

import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.session import get_db

# HTTPBearer extracts the token from "Authorization: Bearer <token>" header.
# auto_error=True means FastAPI returns 403 automatically if header is missing.
_bearer_scheme = HTTPBearer(auto_error=True)

# Reusable 401 exception - defined once, referrenced in both deps below.
_CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"}
)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db)
):
    """
    Decode the Bearer token and return the authenticated User object.
    Imported here to avoid circular imports (auth_service imports deps, deps imports auth_service).
    """
    # Late import to avoid circular: deps <- auth_service <- deps
    from app.services.auth_service import get_user_by_id

    try:
        payload = decode_token(credentials.credentials)
    except InvalidTokenError:
        raise _CREDENTIALS_EXCEPTION
    
    # Reject refresh tokens used on protected endpoints
    if payload.get("type") != "access":
        raise _CREDENTIALS_EXCEPTION
    
    user_id_str: str | None = payload.get("sub")
    if not user_id_str:
        raise _CREDENTIALS_EXCEPTION
    
    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        # sub claim is not a valid UUID
        raise _CREDENTIALS_EXCEPTION
    
    user = await get_user_by_id(db, user_id)
    if user is None:
        raise _CREDENTIALS_EXCEPTION
    
    return user


async def get_current_active_user(
    current_user = Depends(get_current_user)
):
    """
    Extends get_current_user with an is_active check.
    Use this instead of get_current_user on all protected routes.
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated"
        )
    return current_user