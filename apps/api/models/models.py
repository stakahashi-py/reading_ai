from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON, Numeric, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import ARRAY

from ..db.base import Base


class Book(Base):
    __tablename__ = "books"
    id = Column(Integer, primary_key=True)
    slug = Column(String(255), unique=True, nullable=True)
    title = Column(String(255), nullable=False)
    author = Column(String(255), nullable=False)
    era = Column(String(64), nullable=True)
    length_chars = Column(Integer, nullable=True)
    tags = Column(ARRAY(String), nullable=True)
    aozora_source_url = Column(String(1024), nullable=True)
    citation = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    paragraphs = relationship("Paragraph", back_populates="book")


class Paragraph(Base):
    __tablename__ = "paragraphs"
    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    idx = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    # embed: vector(768) -> created by migration; represented as JSON here for ORM placeholder
    # In runtime, prefer pgvector type via sqlalchemy-pgvector
    embed = Column(JSON, nullable=True)
    char_start = Column(Integer, nullable=True)
    char_end = Column(Integer, nullable=True)

    book = relationship("Book", back_populates="paragraphs")


class Highlight(Base):
    __tablename__ = "highlights"
    id = Column(Integer, primary_key=True)
    user_id = Column(String(128), nullable=False)
    book_id = Column(Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    para_id = Column(Integer, ForeignKey("paragraphs.id", ondelete="CASCADE"), nullable=False)
    span_start = Column(Integer, nullable=False)
    span_end = Column(Integer, nullable=False)
    text_snippet = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Taste(Base):
    __tablename__ = "tastes"
    user_id = Column(String(128), primary_key=True)
    # vector(256) -> created by migration
    vector = Column(JSON, nullable=True)
    last_updated = Column(DateTime, default=datetime.utcnow, nullable=False)


class Gallery(Base):
    __tablename__ = "gallery"
    id = Column(Integer, primary_key=True)
    user_id = Column(String(128), nullable=False)
    book_id = Column(Integer, ForeignKey("books.id", ondelete="SET NULL"), nullable=True)
    asset_url = Column(String(1024), nullable=False)
    thumb_url = Column(String(1024), nullable=True)
    type = Column(String(16), nullable=False)  # image or video
    prompt = Column(Text, nullable=True)
    meta = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ReadingProgress(Base):
    __tablename__ = "reading_progress"
    user_id = Column(String(128), primary_key=True)
    book_id = Column(Integer, primary_key=True)
    scroll_percent = Column(Numeric(5, 2), nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)


class Feedback(Base):
    __tablename__ = "feedback"
    id = Column(Integer, primary_key=True)
    user_id = Column(String(128), nullable=False)
    book_id = Column(Integer, ForeignKey("books.id", ondelete="SET NULL"), nullable=True)
    text = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class RecommendationLog(Base):
    __tablename__ = "recommendations_log"
    id = Column(Integer, primary_key=True)
    user_id = Column(String(128), nullable=False)
    book_id = Column(Integer, ForeignKey("books.id", ondelete="SET NULL"), nullable=True)
    quote = Column(Text, nullable=True)
    one_liner = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    clicked = Column(Boolean, default=False, nullable=False)


class QALog(Base):
    __tablename__ = "qa_logs"
    id = Column(Integer, primary_key=True)
    user_id = Column(String(128), nullable=False)
    book_id = Column(Integer, ForeignKey("books.id", ondelete="SET NULL"), nullable=True)
    para_id = Column(Integer, ForeignKey("paragraphs.id", ondelete="SET NULL"), nullable=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=True)
    citations = Column(JSON, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class GenerationJob(Base):
    __tablename__ = "generation_jobs"
    id = Column(Integer, primary_key=True)
    user_id = Column(String(128), nullable=False)
    job_type = Column(String(16), nullable=False)  # image | video
    status = Column(String(16), nullable=False, default="queued")
    book_id = Column(Integer, ForeignKey("books.id", ondelete="SET NULL"), nullable=True)
    prompt = Column(Text, nullable=True)
    payload = Column(JSON, nullable=True)
    result = Column(JSON, nullable=True)
    attempts = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
