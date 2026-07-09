from supabase import create_client, Client
from app.config import settings

supabase_admin: Client = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_SERVICE_ROLE_KEY,
)

supabase_auth: Client = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_ANON_KEY,
)

# Existing database code imports `supabase`; keep it as the admin client.
supabase: Client = supabase_admin


def get_user_supabase(access_token: str) -> Client:
    """Return a Supabase client scoped to the authenticated user's RLS context."""
    client: Client = create_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_ANON_KEY,
    )
    client.postgrest.auth(access_token)
    return client
