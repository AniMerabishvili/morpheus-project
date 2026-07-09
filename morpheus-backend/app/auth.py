from types import SimpleNamespace
from typing import Any, Optional

from fastapi import Header, HTTPException, status

from app.database import supabase_auth


# Run this SQL in Supabase SQL Editor before enabling authenticated dream access:
#
# alter table dreams
# add column if not exists user_id uuid references auth.users(id) on delete cascade;
#
# alter table dreams enable row level security;
#
# drop policy if exists "Users see own dreams" on dreams;
# create policy "Users see own dreams" on dreams
# for all
# using (auth.uid() = user_id)
# with check (auth.uid() = user_id);


def get_current_user(authorization: Optional[str] = Header(default=None)) -> Any:
    """Validate a Supabase Auth bearer token and return the authenticated user."""
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

    return SimpleNamespace(
        id=user.id,
        email=getattr(user, "email", None),
        access_token=token,
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
