from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...security.auth import get_current_user
from ...db.session import get_db
from ...models.models import Highlight, Paragraph

router = APIRouter()


@router.post("/highlights")
def add_highlight(payload: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    para_id = payload.get("para_id")
    book_id = payload.get("book_id")
    span_start = payload.get("span_start", 0)
    span_end = payload.get("span_end")
    if not (para_id and book_id and span_end is not None):
        raise HTTPException(status_code=400, detail="book_id, para_id, span_start, span_end are required")
    para = db.get(Paragraph, para_id)
    if not para or para.book_id != book_id:
        raise HTTPException(status_code=404, detail="paragraph not found")
    snippet = para.text[span_start:span_end]
    h = Highlight(
        user_id=user["uid"],
        book_id=book_id,
        para_id=para_id,
        span_start=span_start,
        span_end=span_end,
        text_snippet=snippet,
    )
    db.add(h)
    db.commit()
    db.refresh(h)
    return {"id": h.id}
