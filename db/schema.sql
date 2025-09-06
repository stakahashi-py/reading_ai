-- PostgreSQL schema for AI Bunko Reader (MVP)
-- Uses pgvector/pg_trgm extensions and creates all required tables and indexes.

-- Extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Tables
CREATE TABLE IF NOT EXISTS books (
  id               SERIAL PRIMARY KEY,
  slug             VARCHAR(255) UNIQUE,
  title            VARCHAR(255) NOT NULL,
  author           VARCHAR(255) NOT NULL,
  era              VARCHAR(64),
  length_chars     INTEGER,
  tags             TEXT[],
  aozora_source_url VARCHAR(1024),
  citation         TEXT,
  created_at       TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS paragraphs (
  id          SERIAL PRIMARY KEY,
  book_id     INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  idx         INTEGER NOT NULL,
  text        TEXT NOT NULL,
  char_start  INTEGER,
  char_end    INTEGER
);

-- vector column for paragraphs (768 dims)
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name='paragraphs' AND column_name='embed'
  ) THEN
    EXECUTE 'ALTER TABLE paragraphs ADD COLUMN embed vector(768)';
  END IF;
END
$$ LANGUAGE plpgsql;

CREATE TABLE IF NOT EXISTS highlights (
  id            SERIAL PRIMARY KEY,
  user_id       VARCHAR(128) NOT NULL,
  book_id       INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  para_id       INTEGER NOT NULL REFERENCES paragraphs(id) ON DELETE CASCADE,
  span_start    INTEGER NOT NULL,
  span_end      INTEGER NOT NULL,
  text_snippet  TEXT,
  created_at    TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tastes (
  user_id      VARCHAR(128) PRIMARY KEY,
  last_updated TIMESTAMP NOT NULL DEFAULT now()
);

-- vector column for tastes (256 dims)
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name='tastes' AND column_name='vector'
  ) THEN
    EXECUTE 'ALTER TABLE tastes ADD COLUMN vector vector(256)';
  END IF;
END
$$ LANGUAGE plpgsql;

CREATE TABLE IF NOT EXISTS gallery (
  id         SERIAL PRIMARY KEY,
  user_id    VARCHAR(128) NOT NULL,
  book_id    INTEGER REFERENCES books(id) ON DELETE SET NULL,
  asset_url  VARCHAR(1024) NOT NULL,
  thumb_url  VARCHAR(1024),
  type       VARCHAR(16) NOT NULL, -- image | video
  prompt     TEXT,
  meta       JSONB,
  created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS reading_progress (
  user_id        VARCHAR(128) NOT NULL,
  book_id        INTEGER NOT NULL,
  scroll_percent NUMERIC(5,2) NOT NULL,
  updated_at     TIMESTAMP NOT NULL DEFAULT now(),
  completed_at   TIMESTAMP,
  PRIMARY KEY (user_id, book_id)
);

CREATE TABLE IF NOT EXISTS feedback (
  id         SERIAL PRIMARY KEY,
  user_id    VARCHAR(128) NOT NULL,
  book_id    INTEGER REFERENCES books(id) ON DELETE SET NULL,
  text       TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS recommendations_log (
  id         SERIAL PRIMARY KEY,
  user_id    VARCHAR(128) NOT NULL,
  book_id    INTEGER REFERENCES books(id) ON DELETE SET NULL,
  quote      TEXT,
  one_liner  TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT now(),
  clicked    BOOLEAN NOT NULL DEFAULT false
);

CREATE TABLE IF NOT EXISTS qa_logs (
  id         SERIAL PRIMARY KEY,
  user_id    VARCHAR(128) NOT NULL,
  book_id    INTEGER REFERENCES books(id) ON DELETE SET NULL,
  para_id    INTEGER REFERENCES paragraphs(id) ON DELETE SET NULL,
  question   TEXT NOT NULL,
  answer     TEXT,
  citations  JSONB,
  latency_ms INTEGER,
  created_at TIMESTAMP NOT NULL DEFAULT now()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_paragraphs_book_idx ON paragraphs (book_id, idx);
CREATE INDEX IF NOT EXISTS idx_paragraphs_embed_ivfflat ON paragraphs USING ivfflat (embed);
CREATE INDEX IF NOT EXISTS idx_books_tags_gin ON books USING gin (tags);
CREATE INDEX IF NOT EXISTS idx_books_title_trgm ON books USING gin (title gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_books_author_trgm ON books USING gin (author gin_trgm_ops);

