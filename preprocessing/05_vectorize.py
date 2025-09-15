#!/usr/bin/env python3
"""
Book summaries and paragraphs vectorization and store into pgvector.
Simple pipeline only: fetch -> batch embed -> update. No args, no branching.

Environment:
- CONNECTION_NAME, DB_USER, DB_NAME, DB_PASS (Cloud SQL Connector; IAMなし)
- PROJECT_ID(+VERTEX_LOCATION) or GOOGLE_API_KEY for embeddings (google-genai)

Run:
  python preprocessing/05_vectorize_paragraph.py
"""
from __future__ import annotations

import os
import sys
import time
from typing import List, Tuple
import time
import numpy as np
from numpy.linalg import norm

import dotenv

from google import genai  # type: ignore

from google.cloud.sql.connector import Connector, IPTypes  # type: ignore


MODEL = "gemini-embedding-001"
FETCH_SIZE = 1000
EMBED_BATCH = 250


def load_env():
    dotenv.load_dotenv()


def make_db_conn():
    conn_name = os.getenv("CONNECTION_NAME")
    db_user = os.getenv("DB_USER")
    db_name = os.getenv("DB_NAME")
    db_pass = os.getenv("DB_PASS")
    if not (conn_name and db_user and db_name):
        print(
            "Set CONNECTION_NAME, DB_USER, DB_NAME (and DB_PASS if needed)",
            file=sys.stderr,
        )
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
    return conn, connector


def make_embed_client():
    project = os.getenv("PROJECT_ID")
    location = os.getenv("VERTEX_LOCATION", "asia-northeast1")
    api_key = os.getenv("GOOGLE_API_KEY")
    if project:
        return genai.Client(vertexai=True, project=project, location=location)
    elif api_key:
        return genai.Client(api_key=api_key)
    else:
        print(
            "Set PROJECT_ID (+VERTEX_LOCATION) or GOOGLE_API_KEY for embeddings.",
            file=sys.stderr,
        )
        sys.exit(2)


def embed_batch(client, texts: List[str]) -> List[List[float]]:
    resp = client.models.embed_content(
        model=MODEL, contents=texts, config={"output_dimensionality": 768}
    )
    if hasattr(resp, "embeddings"):
        out: List[List[float]] = []
        for e in resp.embeddings:
            v = e.values
            normed = np.array(v) / norm(np.array(v))
            out.append(normed.tolist())
        return out
    else:
        raise RuntimeError("Unexpected embedding response shape")


def to_vector_literal(vec: List[float]) -> str:
    # pgvector textual representation: [v1,v2,...]
    # Keep compact to reduce payload
    return "[" + ",".join(f"{x:.16f}" for x in vec) + "]"


def fetch_batch(table, cur, after_id: int, limit: int) -> List[Tuple[int, str]]:
    # embed が NULL の行のみ。『底本：/底本:』を含む行は除外。
    if table == "books":
        # booksは要約のみ
        sql = (
            f"SELECT id, summary FROM {table} "
            "WHERE id > %s AND embed IS NULL AND summary IS NOT NULL "
            "ORDER BY id ASC LIMIT %s"
        )
    elif table == "paragraphs":
        sql = (
            f"SELECT id, text FROM {table} "
            "WHERE id > %s AND embed IS NULL AND text !~ '底本\\s*[：:]' "
            "ORDER BY id ASC LIMIT %s"
        )
    cur.execute(sql, [after_id, limit])
    return [(r[0], r[1]) for r in cur.fetchall()]


def vectorize(table):
    load_env()
    client = make_embed_client()
    conn, connector = make_db_conn()
    cur = conn.cursor()
    cur.execute("SET LOCAL synchronous_commit = off")
    cur.execute("SET LOCAL statement_timeout = '600s'")

    # 総件数（embedがNULL かつ 底本行を除外）
    if table == "books":
        cur.execute(
            f"SELECT COUNT(*) FROM {table} WHERE embed IS NULL AND summary IS NOT NULL"
        )
    elif table == "paragraphs":
        cur.execute(
            f"SELECT COUNT(*) FROM {table} WHERE embed IS NULL AND text !~ '底本\\s*[：:]'"
        )
    total = cur.fetchone()[0]
    print(f"target rows: {total}")

    processed = 0
    after_id = 0
    t0 = time.time()
    while True:
        rows = fetch_batch(table, cur, after_id, FETCH_SIZE)
        if not rows:
            break
        ids, texts = zip(*rows)
        for i in range(0, len(texts), EMBED_BATCH):
            chunk_ids = ids[i : i + EMBED_BATCH]
            chunk_texts = list(texts[i : i + EMBED_BATCH])
            embs = embed_batch(client, chunk_texts)
            placeholders = []
            params: List[object] = []
            for pid, vec in zip(chunk_ids, embs):
                placeholders.append("(%s::vector, %s::int)")
                params.append(to_vector_literal(vec))
                params.append(int(pid))
            sql = (
                f"UPDATE {table} AS p SET embed = v.embed "
                "FROM (VALUES " + ",".join(placeholders) + ") AS v(embed, id) "
                "WHERE p.id = v.id"
            )
            cur.execute(sql, params)
            processed += len(chunk_ids)
            if processed % 500 == 0:
                conn.commit()
                dt = time.time() - t0
                print(
                    f"processed {processed}/{total} ({processed/total*100:.1f}%) in {dt:.1f}s"
                )
        after_id = rows[-1][0]
    conn.commit()
    dt = time.time() - t0
    print(f"Done. processed={processed}/{total} in {dt:.1f}s")
    conn.close()
    connector.close()


def main():
    print("Vectorizing book summaries...")
    vectorize("books")
    print("Vectorizing paragraphs...")
    vectorize("paragraphs")


if __name__ == "__main__":
    main()
