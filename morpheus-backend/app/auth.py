from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Optional

from fastapi import Header, HTTPException, status
from supabase import Client

from app.database import get_user_supabase, supabase_auth


@dataclass(frozen=True)
class AuthenticatedUser:
    id: str
    email: Optional[str]
    access_token: str
    supabase: Client


def get_current_user(authorization: Optional[str] = Header(default=None)) -> AuthenticatedUser:
    """Validate a Supabase Auth token and attach an RLS-scoped DB client."""
    if not authorization:
        raise_unauthorized()

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise_unauthorized()

    try:
        response = supabase_auth.auth.get_user(token)
    except Exception as exc:
        raise_unauthorized(exc)

    user = getattr(response, "user", None)
    if not user and isinstance(response, dict):
        user = response.get("user")

    if isinstance(user, dict):
        user = SimpleNamespace(**user)

    if not user or not getattr(user, "id", None):
        raise_unauthorized()

    return AuthenticatedUser(
        id=user.id,
        email=getattr(user, "email", None),
        access_token=token,
        supabase=get_user_supabase(token),
    )


def raise_unauthorized(exc: Optional[Exception] = None) -> None:
    error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing or invalid authentication token.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if exc:
        raise error from exc
    raise error
