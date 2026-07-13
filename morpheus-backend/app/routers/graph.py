from fastapi import APIRouter, Depends

from app.auth import get_current_user
from app.security import client_safe_error
from app.services.graph_logic import build_graph_data

router = APIRouter(prefix="/graph")


@router.get("/data")
def get_graph_data(current_user=Depends(get_current_user)) -> dict:
    """Return dream-keyword graph data."""
    try:
        return build_graph_data(current_user.supabase, current_user.id)
    except Exception as exc:
        raise client_safe_error("Failed to load graph data.") from exc
