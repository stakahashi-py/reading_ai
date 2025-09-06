from fastapi import APIRouter, Depends

from ...security.auth import get_current_user

router = APIRouter()


@router.post("/qa")
def qa(payload: dict, user=Depends(get_current_user)):
    # TODO: stream answer; here returns a stub
    return {"answer": "", "citations": [], "model": "gemma-2-9b", "latency_ms": 0, "confidence": 0.0}

