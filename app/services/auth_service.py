# Business logic for authentication.
# Routers call services - services call DB. No SQLAlchemy in routers.

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.db.models.user import User
from app.schemas.auth import RegisterRequest


async def register_user(db: AsyncSession, data: RegisterRequest) -> User:
    """
    Create a new user user account.
    Raises ValueError on duplicate email or username - router converts to HTTP 400.
    """
    # Check duplicate email
    result = await db.execute(select(User).where(User.email == data.email))
    if result.scalar_one_or_none() is not None:
        raise ValueError("Email already registered")
    
    # Check duplicate username
    result = await db.execute(select(User).where(User.username == data.username))
    if result.scalar_one_or_none() is not None:
        raise ValueError("Username already registered")
    
    user = User(
        email=data.email,
        username=data.username,     # Alrady lowercased by validator
        hashed_password=hash_password(data.password)
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)      # Populate server-generated fields (id, created_at)
    return user


async def authenticate_user(
    db: AsyncSession,
    email: str,
    password: str
) -> User | None:
    """
    Verify credentials and return the User, or None if invalid.
    Returning None (not raising) lets the router control the HTTP response.
    """
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None:
        # Run verify_password anyway to prevent timing attacks
        # (attacker can't tell if email exists based on response time)
        hash_password("dummy_prevent_timing_attack")
        return None
    
    if not verify_password(password, user.hashed_password):
        return None
    
    return user


async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    """Fetch a user by primary key. Returns None if not found."""
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()