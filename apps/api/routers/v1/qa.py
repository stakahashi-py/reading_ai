from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ...security.auth import get_current_user
from ...db.session import get_db
from ...models.models import Book
from ...services import llm

router = APIRouter()


@router.post("/qa")
def qa(payload: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    book_id = payload.get("book_id")
    question = payload.get("question")
    if not (book_id and question):
        raise HTTPException(status_code=400, detail="book_id and question are required")
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="book not found")
    text, latency_ms = llm.answer_question(book.title, question)
    return {"answer": text, "citations": [], "model": llm.LLM_MODEL, "latency_ms": latency_ms, "confidence": 0.5}


@router.post("/qa/stream")
def qa_stream(payload: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    book_id = payload.get("book_id")
    question = payload.get("question")
    if not (book_id and question):
        raise HTTPException(status_code=400, detail="book_id and question are required")
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="book not found")

    def gen():
        yield "event: start\n\n"
        for chunk in llm.stream_answer_question(book.title, question):
            if chunk:
                # SSE形式でdataを送出
                yield f"data: {chunk}\n\n"
        yield "event: end\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")
