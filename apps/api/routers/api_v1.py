from fastapi import APIRouter

from .v1 import books, search, recommendations, translate, qa, highlights, generate, gallery, progress, feedback, translations, librarian_proxy

router = APIRouter()

router.include_router(books.router, prefix="/books", tags=["books"])
router.include_router(search.router, prefix="/search", tags=["search"])
router.include_router(recommendations.router, prefix="", tags=["recommendations"])
router.include_router(translate.router, prefix="", tags=["translate"])
router.include_router(translations.router, prefix="", tags=["translations"])
router.include_router(qa.router, prefix="", tags=["qa"])
router.include_router(highlights.router, prefix="", tags=["highlights"])
router.include_router(generate.router, prefix="/generate", tags=["generate"])
router.include_router(gallery.router, prefix="", tags=["gallery"])
router.include_router(progress.router, prefix="", tags=["progress"])
router.include_router(feedback.router, prefix="", tags=["feedback"])
router.include_router(librarian_proxy.router, prefix="", tags=["librarian_proxy"])
