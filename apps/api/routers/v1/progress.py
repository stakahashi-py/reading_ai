from fastapi import APIRouter, Depends

from ...security.auth import get_current_user

router = APIRouter()


@router.post("/progress")
def save_progress(payload: dict, user=Depends(get_current_user)):
    # TODO: upsert reading progress
    return {"ok": True}


@router.post("/complete")
def complete(payload: dict, user=Depends(get_current_user)):
    # TODO: mark as completed and timestamp
    return {"ok": True}

