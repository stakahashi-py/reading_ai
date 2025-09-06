from fastapi import APIRouter, Depends

from ...security.auth import get_current_user

router = APIRouter()


@router.post("/feedback")
def post_feedback(payload: dict, user=Depends(get_current_user)):
    # TODO: persist feedback and trigger recommendation refresh
    return {"ok": True}

