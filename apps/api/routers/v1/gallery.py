from fastapi import APIRouter, Depends

from ...security.auth import get_current_user

router = APIRouter()


@router.get("/gallery")
def list_gallery(user=Depends(get_current_user)):
    # TODO: list user gallery assets
    return {"items": []}

