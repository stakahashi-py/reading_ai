from fastapi import APIRouter, Depends, HTTPException
from typing import Optional, List, Dict, Any
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


@router.get("/highlights")
def list_highlights(
    book_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    q = db.query(Highlight).filter(Highlight.user_id == user["uid"])
    if book_id is not None:
        q = q.filter(Highlight.book_id == book_id)
    q = q.order_by(Highlight.created_at.asc())
    rows: List[Highlight] = q.all()
    items: List[Dict[str, Any]] = []
    for h in rows:
        items.append(
            {
                "id": h.id,
                "book_id": h.book_id,
                "para_id": h.para_id,
                "span_start": h.span_start,
                "span_end": h.span_end,
                "text_snippet": h.text_snippet,
                "created_at": h.created_at.isoformat(),
            }
        )
    return {"items": items}


@router.delete("/highlights/{highlight_id}")
def delete_highlight(
    highlight_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)
):
    h = db.get(Highlight, highlight_id)
    if not h or h.user_id != user["uid"]:
        raise HTTPException(status_code=404, detail="highlight not found")
    db.delete(h)
    db.commit()
    return {"ok": True}
