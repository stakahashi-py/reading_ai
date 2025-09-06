from fastapi import APIRouter, Depends

from ...security.auth import get_current_user

router = APIRouter()


@router.post("/translate")
def translate(payload: dict, user=Depends(get_current_user)):
    # TODO: call low-latency LLM (Gemma) with caching
    return {"translation": "", "model": "gemma-2-9b", "latency_ms": 0}

