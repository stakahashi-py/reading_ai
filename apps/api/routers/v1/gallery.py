from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...security.auth import get_current_user
from ...db.session import get_db
from ...models.models import Gallery

router = APIRouter()


@router.get("/gallery")
def list_gallery(book_id: int | None = None, user=Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(Gallery).filter(Gallery.user_id == user["uid"])
    if book_id is not None:
        q = q.filter(Gallery.book_id == book_id)
    rows = q.order_by(Gallery.created_at.asc()).all()
    items = [
        {
            "id": g.id,
            "book_id": g.book_id,
            "asset_url": g.asset_url,
            "thumb_url": g.thumb_url,
            "type": g.type,
            "prompt": g.prompt,
            "meta": g.meta,
            "created_at": g.created_at.isoformat(),
        }
        for g in rows
    ]
    return {"items": items}


@router.delete("/gallery/{gallery_id}")
def delete_gallery(gallery_id: int, user=Depends(get_current_user), db: Session = Depends(get_db)):
    g = db.get(Gallery, gallery_id)
    if not g or g.user_id != user["uid"]:
        return {"error": "not found"}
    db.delete(g)
    db.commit()
    return {"ok": True}
