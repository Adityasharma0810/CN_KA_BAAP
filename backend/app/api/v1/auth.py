"""Authentication routes: register, login, refresh."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.v1.deps import get_current_user, get_session
from backend.app.core.settings import settings
from backend.app.schemas.auth import (
    UserLogin,
    UserOut,
    UserRegister,
    Token,
    TokenRefresh,
    HouseholdOut,
)
from backend.app.services.auth_service import (
    AuthError,
    authenticate_user,
    login_user,
    register_user,
    decode_access_token,
)

_LOGGER = logging.getLogger(__name__)

router = APIRouter()


@router.post("/auth/register", response_model=Token, status_code=201)
async def register(data: UserRegister, session: AsyncSession = Depends(get_session)):
    try:
        result = await register_user(session, data)
    except AuthError as error:
        message = str(error)
        if message == "email_already_registered":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email_already_registered")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
    except Exception as error:  # pragma: no cover - defensive
        _LOGGER.exception("registration failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="registration_failed")
    return {
        "access_token": result["access_token"],
        "refresh_token": result["refresh_token"],
        "token_type": "bearer",
        "expires_in": settings.access_token_expire_minutes * 60,
    }


@router.post("/auth/login", response_model=Token)
async def login(data: UserLogin, session: AsyncSession = Depends(get_session)):
    try:
        user = await authenticate_user(session, data)
    except AuthError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_credentials")
    tokens = await login_user(session, user)
    return {
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "token_type": "bearer",
        "expires_in": settings.access_token_expire_minutes * 60,
    }


@router.post("/auth/refresh", response_model=Token)
async def refresh(body: TokenRefresh):
    try:
        payload = decode_access_token(body.refresh_token)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_refresh_token")
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_token_type")
    from backend.app.core.security import create_access_token, create_refresh_token

    user_id = payload["sub"]
    access = create_access_token(user_id, extra={"role": payload.get("role", "member")})
    refresh_token = create_refresh_token(user_id)
    return {
        "access_token": access,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.access_token_expire_minutes * 60,
    }


@router.get("/auth/me", response_model=UserOut)
async def me(user = Depends(get_current_user)):
    return user


@router.get("/auth/household", response_model=HouseholdOut)
async def household(user = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    from backend.app.models.user import HouseholdMember, Household
    from sqlalchemy import select
    membership = await session.scalar(select(HouseholdMember).where(HouseholdMember.user_id == user.id))
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no_household")
    household = await session.scalar(select(Household).where(Household.id == membership.household_id))
    if not household:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="household_not_found")
    return household
