from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...security.auth import get_current_user
from ...db.session import get_db
from ...models.models import Translation

router = APIRouter()


@router.get("/translations")
def list_translations(book_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    rows = (
        db.query(Translation)
        .filter(Translation.user_id == user["uid"], Translation.book_id == book_id)
        .order_by(Translation.created_at.asc())
        .all()
    )
    items = [
        {
            "id": r.id,
            "book_id": r.book_id,
            "para_id": r.para_id,
            "text": r.text,
            "model": r.model,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]
    return {"items": items}

