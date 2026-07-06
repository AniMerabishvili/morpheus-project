from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_user
from app.services.graph_logic import build_graph_data

router = APIRouter(prefix="/graph")


@router.get("/data")
def get_graph_data(current_user=Depends(get_current_user)) -> dict:
    """Return dream-keyword graph data."""
    try:
        return build_graph_data(current_user.id)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load graph data: {str(exc)}",
        ) from exc
