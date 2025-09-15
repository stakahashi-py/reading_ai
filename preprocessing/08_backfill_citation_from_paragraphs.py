#!/usr/bin/env python3
"""
Backfill books.citation from the last paragraph when it contains "底本：".

超簡易版: 条件に合うものだけを一括更新します。

判定基準:
- 各 book の paragraphs の最後の id（id 降順で1件）の text に「底本：」が含まれる。
- かつ books.citation が NULL または空文字。

使い方:
  python preprocessing/08_backfill_citation_from_paragraphs.py

接続情報は apps/api/db/session.py と .env を利用します。
"""
from __future__ import annotations

from sqlalchemy import text

# reuse engine that loads .env inside
from apps.api.db.session import engine  # type: ignore


def main() -> None:
    select_sql = text(
        """
        SELECT b.id AS book_id, p.id AS last_para_id, p.text AS para_text
        FROM books b
        JOIN LATERAL (
          SELECT id, text
          FROM paragraphs
          WHERE book_id = b.id
          ORDER BY id DESC
          LIMIT 1
        ) p ON TRUE
        WHERE (b.citation IS NULL OR b.citation = '')
          AND p.text LIKE '%底本：%'
        ORDER BY b.id
        """
    )

    update_sql = text(
        """
        UPDATE books
        SET citation = :citation
        WHERE id = :book_id
        """
    )

    total = 0
    updated = 0

    with engine.begin() as conn:
        rows = list(conn.execute(select_sql))
        total = len(rows)
        for r in rows:
            book_id = r[0]
            last_para_id = r[1]
            para_text = r[2] or ""

            # そのまま全文を citation へ。極力単純化。
            citation = para_text.strip()
            conn.execute(update_sql, {"citation": citation, "book_id": book_id})
            updated += 1
            print(f"updated book_id={book_id} using para_id={last_para_id}")

    print(f"done: candidates={total}, updated={updated}")


if __name__ == "__main__":
    main()

