from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...security.auth import get_current_user
from ...db.session import get_db
from ...models.models import Book, Paragraph
from ...services import llm

router = APIRouter()


@router.post("/translate")
def translate(payload: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    book_id = payload.get("book_id")
    para_id = payload.get("para_id")
    if not (book_id and para_id):
        raise HTTPException(status_code=400, detail="book_id and para_id are required")
    book = db.get(Book, book_id)
    para = db.get(Paragraph, para_id)
    if not book or not para or para.book_id != book.id:
        raise HTTPException(status_code=404, detail="book/paragraph not found")
    text, latency_ms = llm.translate_paragraph(book.title, para.text)
    return {"translation": text, "model": llm.LLM_MODEL, "latency_ms": latency_ms}
