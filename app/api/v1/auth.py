import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from jwt.exceptions import InvalidTokenError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_active_user, get_db
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest, TokenResponse
from app.schemas.user import UserResponse
from app.services.auth_service import authenticate_user, get_user_by_id, register_user
from app.main import limiter

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account"
)
@limiter.limit("10/minute")
async def register(request: Request, data: RegisterRequest, db: AsyncSession = Depends(get_db)):
    try:
        user = await register_user(db, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return user


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login and receive JWT tokens"
)
@limiter.limit("5/minute")
async def login(request: Request, data: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await authenticate_user(db, data.email, data.password)

    # Use a single generic message - don't reveal whether email or password is wrong
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid email or password"
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated"
        )
    
    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id)
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Exchange a refresh token for a new access token"
)
async def refresh(data: RefreshRequest, db: AsyncSession = Depends(get_db)):
    invalid_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token"
    )

    try:
        payload = decode_token(data.refresh_token)
    except InvalidTokenError:
        raise invalid_exc
    
    # Reject access tokens submitted to this endpoint
    if payload.get("type") != "refresh":
        raise invalid_exc
    
    user_id_str: str | None = payload.get("sub")
    if not user_id_str:
        raise invalid_exc
    
    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise invalid_exc
    
    user = await get_user_by_id(db, user_id)
    if user is None or not user.is_active:
        raise invalid_exc
    
    # Issue both tokens so the client can restart its refresh cycle
    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id)
    )


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get the currently authenticated user"
)
async def get_me(current_user=Depends(get_current_active_user)):
    return current_user