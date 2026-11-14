from fastapi import APIRouter, Depends

from app.auth import get_current_user
from app.services.library import get_library

router = APIRouter(prefix="/library", tags=["library"])


@router.get("")
def list_library(current_user=Depends(get_current_user)) -> list[dict]:
    """Books in Morpheus's knowledge base that a dream can be read through."""
    return get_library()
