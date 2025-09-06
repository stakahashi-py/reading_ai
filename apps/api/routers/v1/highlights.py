from fastapi import APIRouter, Depends

from ...security.auth import get_current_user

router = APIRouter()


@router.post("/highlights")
def add_highlight(payload: dict, user=Depends(get_current_user)):
    # TODO: persist highlight and update taste vector
    return {"ok": True}

