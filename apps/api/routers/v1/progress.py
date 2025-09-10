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
    last_para_idx = payload.get("last_paragraph_index")
    if book_id is None or scroll_percent is None:
        raise HTTPException(status_code=400, detail="book_id and scroll_percent are required")
    rp = (
        db.query(ReadingProgress)
        .filter(ReadingProgress.user_id == user["uid"], ReadingProgress.book_id == book_id)
        .one_or_none()
    )
    if rp:
        rp.scroll_percent = scroll_percent
        if last_para_idx is not None:
            rp.last_para_idx = int(last_para_idx)
    else:
        rp = ReadingProgress(user_id=user["uid"], book_id=book_id, scroll_percent=scroll_percent, last_para_idx=last_para_idx)
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
        "last_paragraph_index": rp.last_para_idx,
    }


@router.post("/progress/list")
def list_progress(payload: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """指定book_id群の進捗を一括取得。未指定なら全件を返す。"""
    book_ids = payload.get("book_ids") or []
    q = db.query(ReadingProgress).filter(ReadingProgress.user_id == user["uid"])
    if book_ids:
        q = q.filter(ReadingProgress.book_id.in_(book_ids))
    rows = q.all()
    items = [
        {
            "book_id": r.book_id,
            "scroll_percent": float(r.scroll_percent),
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            "last_paragraph_index": r.last_para_idx,
        }
        for r in rows
    ]
    return {"items": items}
