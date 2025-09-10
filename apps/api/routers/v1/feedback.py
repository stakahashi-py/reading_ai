from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...security.auth import get_current_user
from ...db.session import get_db
from ...models.models import Feedback

router = APIRouter()


@router.post("/feedback")
def post_feedback(payload: dict, user=Depends(get_current_user), db: Session = Depends(get_db)):
    text = (payload.get("text") or "").strip()
    book_id = payload.get("book_id")
    fb = Feedback(user_id=user["uid"], book_id=book_id, text=text)
    db.add(fb)
    db.commit()
    return {"ok": True}


@router.get("/feedback")
def get_feedback(book_id: int, user=Depends(get_current_user), db: Session = Depends(get_db)):
    row = (
        db.query(Feedback)
        .filter(Feedback.user_id == user["uid"], Feedback.book_id == book_id)
        .order_by(Feedback.created_at.desc())
        .first()
    )
    if not row:
        return {"item": None}
    return {
        "item": {
            "id": row.id,
            "book_id": row.book_id,
            "text": row.text,
            "created_at": row.created_at.isoformat(),
        }
    }


@router.put("/feedback/{feedback_id}")
def update_feedback(feedback_id: int, payload: dict, user=Depends(get_current_user), db: Session = Depends(get_db)):
    text = (payload.get("text") or "").strip()
    row = db.get(Feedback, feedback_id)
    if not row or row.user_id != user["uid"]:
        return {"error": "not found"}
    row.text = text
    db.add(row)
    db.commit()
    return {"ok": True}
