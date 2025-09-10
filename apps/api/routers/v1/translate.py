from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...security.auth import get_current_user
from ...db.session import get_db
from ...models.models import Book, Paragraph, Translation
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
    # 永続化（同一ユーザー×段落は最新を1件保持）
    tr = Translation(
        user_id=user["uid"],
        book_id=book.id,
        para_id=para.id,
        text=text,
        model=getattr(llm, "LLM_MODEL", None),
    )
    try:
        # 既存があれば削除して差し替え（簡易）
        db.query(Translation).filter(
            Translation.user_id == user["uid"],
            Translation.para_id == para.id,
        ).delete()
    except Exception:
        pass
    db.add(tr)
    db.commit()
    return {"translation": text, "model": llm.LLM_MODEL, "latency_ms": latency_ms}
