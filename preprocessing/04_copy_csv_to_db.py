#!/usr/bin/env python3
"""
Cloud SQL Connector(pg8000)のみで、preprocessing/books.csv と preprocessing/paragraphs.csv を一括投入。
IAMは使いません。引数不要で `python preprocessing/04_copy_csv_to_db.py` で実行できます。
"""
import os
import sys
import csv
from pathlib import Path
import dotenv
from google.cloud.sql.connector import Connector, IPTypes  # type: ignore


def main():
    dotenv.load_dotenv()

    books_csv = Path("preprocessing/books.csv")
    paras_csv = Path("preprocessing/paragraphs.csv")
    if not books_csv.exists() or not paras_csv.exists():
        print("CSV not found: preprocessing/books.csv / preprocessing/paragraphs.csv", file=sys.stderr)
        sys.exit(2)

    conn_name = os.getenv("CONNECTION_NAME")
    db_user = os.getenv("DB_USER")
    db_name = os.getenv("DB_NAME")
    db_pass = os.getenv("DB_PASS")
    if not (conn_name and db_user and db_name):
        print("Set CONNECTION_NAME, DB_USER, DB_NAME (and DB_PASS if needed)", file=sys.stderr)
        sys.exit(2)

    connector = Connector()
    conn = connector.connect(
        conn_name,
        "pg8000",
        user=db_user,
        db=db_name,
        password=db_pass,
        enable_iam_auth=False,
        ip_type=IPTypes.PUBLIC,
    )
    try:
        cur = conn.cursor()
        cur.execute("SET LOCAL synchronous_commit = off")
        # 既存データをクリア（依存関係も含めて初期化）
        cur.execute("TRUNCATE TABLE paragraphs, books RESTART IDENTITY CASCADE;")

        cur.execute(
            """
            CREATE TEMP TABLE stage_books (
              slug TEXT,
              title TEXT,
              author TEXT,
              era TEXT,
              summary TEXT,
              length_chars INTEGER,
              tags_json JSONB,
              aozora_source_url TEXT,
              citation TEXT
            ) ON COMMIT DROP;
            CREATE TEMP TABLE stage_paragraphs (
              slug TEXT,
              idx INTEGER,
              text TEXT,
              char_start INTEGER,
              char_end INTEGER
            ) ON COMMIT DROP;
            """
        )

        # stage_books へ投入（マルチVALUES）
        with books_csv.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            batch = []
            BATCH = 1000
            def flush_books(rows):
                if not rows:
                    return
                placeholders = ",".join(["(%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s)"] * len(rows))
                sql = (
                    "INSERT INTO stage_books (slug,title,author,era,summary,length_chars,tags_json,aozora_source_url,citation) VALUES "
                    + placeholders
                )
                params = []
                for r in rows:
                    params.extend([
                        r.get("slug"),
                        r.get("title"),
                        r.get("author"),
                        r.get("era") or None,
                        r.get("summary") or None,
                        int(r["length_chars"]) if r.get("length_chars") else None,
                        r.get("tags_json") or "[]",
                        r.get("aozora_source_url") or None,
                        r.get("citation") or None,
                    ])
                cur.execute(sql, params)
            for row in reader:
                batch.append(row)
                if len(batch) >= BATCH:
                    flush_books(batch)
                    batch.clear()
            flush_books(batch)

        # stage_paragraphs へ投入（マルチVALUES）
        with paras_csv.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            batch = []
            BATCH = 2000
            def flush_paras(rows):
                if not rows:
                    return
                placeholders = ",".join(["(%s,%s,%s,%s,%s)"] * len(rows))
                sql = (
                    "INSERT INTO stage_paragraphs (slug,idx,text,char_start,char_end) VALUES "
                    + placeholders
                )
                params = []
                for r in rows:
                    params.extend([
                        r.get("slug"),
                        int(r["idx"]) if r.get("idx") else 0,
                        r.get("text") or "",
                        int(r["char_start"]) if r.get("char_start") else None,
                        int(r["char_end"]) if r.get("char_end") else None,
                    ])
                cur.execute(sql, params)
            for row in reader:
                batch.append(row)
                if len(batch) >= BATCH:
                    flush_paras(batch)
                    batch.clear()
            flush_paras(batch)

        # books UPSERT, paragraphs 差し替え
        cur.execute(
            """
            INSERT INTO books (slug, title, author, era, summary, length_chars, tags, aozora_source_url, citation)
            SELECT
              b.slug,
              b.title,
              b.author,
              b.era,
              b.summary,
              b.length_chars,
              CASE WHEN b.tags_json IS NULL THEN NULL
                   ELSE ARRAY(SELECT jsonb_array_elements_text(b.tags_json)) END AS tags,
              b.aozora_source_url,
              b.citation
            FROM stage_books b
            ON CONFLICT (slug) DO UPDATE SET
              title=EXCLUDED.title,
              author=EXCLUDED.author,
              era=EXCLUDED.era,
              summary=EXCLUDED.summary,
              length_chars=EXCLUDED.length_chars,
              tags=EXCLUDED.tags,
              aozora_source_url=EXCLUDED.aozora_source_url,
              citation=EXCLUDED.citation;
            """
        )

        cur.execute(
            """
            DELETE FROM paragraphs
            WHERE book_id IN (
              SELECT id FROM books WHERE slug IN (SELECT DISTINCT slug FROM stage_paragraphs)
            );
            INSERT INTO paragraphs (book_id, idx, text, char_start, char_end)
            SELECT b.id, p.idx, p.text, p.char_start, p.char_end
            FROM stage_paragraphs p
            JOIN books b ON b.slug = p.slug
            ORDER BY b.id, p.idx;
            """
        )

        conn.commit()
        print("OK: imported via Cloud SQL Connector (pg8000).")
    finally:
        try:
            conn.close()
        except Exception:
            pass
        connector.close()


if __name__ == "__main__":
    main()
