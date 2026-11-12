"""Authentication and account service."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.security import create_access_token, create_refresh_token, decode_token, hash_password, verify_password
from backend.app.models.user import Household, HouseholdMember, User
from backend.app.schemas.auth import UserRegister, UserLogin


class AuthError(Exception):
    pass


async def register_user(db: AsyncSession, data: UserRegister) -> dict[str, Any]:
    existing = await db.scalar(select(User).where(User.email == data.email))
    if existing:
        raise AuthError("email_already_registered")

    user = User(
        email=data.email,
        hashed_password=hash_password(data.password),
        full_name=data.full_name,
        role="owner",
    )
    db.add(user)
    await db.flush()

    household = Household(name=data.household_name or f"{data.email}'s household", owner_id=user.id)
    db.add(household)
    await db.flush()

    member = HouseholdMember(household_id=household.id, user_id=user.id, role="owner")
    db.add(member)
    await db.commit()
    await db.refresh(user)
    await db.refresh(household)

    token = create_access_token(user.id, extra={"household_id": household.id, "role": user.role})
    refresh = create_refresh_token(user.id)
    return {"user": user, "household": household, "access_token": token, "refresh_token": refresh}


async def authenticate_user(db: AsyncSession, data: UserLogin) -> User:
    user = await db.scalar(select(User).where(User.email == data.email))
    if not user or not verify_password(data.password, user.hashed_password):
        raise AuthError("invalid_credentials")
    if not user.is_active:
        raise AuthError("account_inactive")
    return user


async def login_user(db: AsyncSession, user: User) -> dict[str, str]:
    membership = await db.scalar(
        select(HouseholdMember).where(HouseholdMember.user_id == user.id)
    )
    household_id = membership.household_id if membership else None
    token = create_access_token(
        user.id, extra={"household_id": household_id, "role": user.role}
    )
    refresh = create_refresh_token(user.id)
    return {"access_token": token, "refresh_token": refresh}


def decode_access_token(token: str) -> dict[str, Any]:
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise AuthError("invalid_token_type")
    return payload
