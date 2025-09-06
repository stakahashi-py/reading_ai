from fastapi import APIRouter, Depends

from ...security.auth import get_current_user

router = APIRouter()


@router.get("/recommendations")
def get_recommendations(user=Depends(get_current_user)):
    # TODO: compute recommendations from tastes vector and diversity constraints
    return {"items": []}

