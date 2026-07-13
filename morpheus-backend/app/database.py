from supabase import Client, create_client

from app.config import settings


supabase_admin_only: Client = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_SERVICE_ROLE_KEY,
)
"""Service-role client.

Use only in small, explicitly named helpers for operations that truly require
elevated privileges. User-owned reads and writes must use `get_user_supabase`.
"""

supabase_auth: Client = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_ANON_KEY,
)


def get_user_supabase(access_token: str) -> Client:
    """Return a Supabase client scoped to the authenticated user's RLS context."""
    client: Client = create_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_ANON_KEY,
    )
    client.postgrest.auth(access_token)
    return client
