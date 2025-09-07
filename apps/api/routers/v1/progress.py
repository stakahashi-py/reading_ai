from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...security.auth import get_current_user
from ...db.session import get_db
from ...models.models import ReadingProgress

router = APIRouter()


@router.post("/progress")
def save_progress(payload: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    book_id = payload.get("book_id")
    scroll_percent = payload.get("scroll_percent")
    if book_id is None or scroll_percent is None:
        raise HTTPException(status_code=400, detail="book_id and scroll_percent are required")
    rp = (
        db.query(ReadingProgress)
        .filter(ReadingProgress.user_id == user["uid"], ReadingProgress.book_id == book_id)
        .one_or_none()
    )
    if rp:
        rp.scroll_percent = scroll_percent
    else:
        rp = ReadingProgress(user_id=user["uid"], book_id=book_id, scroll_percent=scroll_percent)
        db.add(rp)
    db.commit()
    return {"ok": True}


@router.post("/complete")
def complete(payload: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    from datetime import datetime

    book_id = payload.get("book_id")
    if book_id is None:
        raise HTTPException(status_code=400, detail="book_id is required")
    rp = (
        db.query(ReadingProgress)
        .filter(ReadingProgress.user_id == user["uid"], ReadingProgress.book_id == book_id)
        .one_or_none()
    )
    if not rp:
        rp = ReadingProgress(user_id=user["uid"], book_id=book_id, scroll_percent=100)
        db.add(rp)
    rp.completed_at = datetime.utcnow()
    db.commit()
    return {"ok": True}


@router.get("/progress")
def get_progress(book_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    rp = (
        db.query(ReadingProgress)
        .filter(ReadingProgress.user_id == user["uid"], ReadingProgress.book_id == book_id)
        .one_or_none()
    )
    if not rp:
        return {"book_id": book_id, "scroll_percent": 0}
    return {
        "book_id": book_id,
        "scroll_percent": float(rp.scroll_percent),
        "completed_at": rp.completed_at.isoformat() if rp.completed_at else None,
        "updated_at": rp.updated_at.isoformat() if rp.updated_at else None,
    }
