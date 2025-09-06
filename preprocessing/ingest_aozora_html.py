#!/usr/bin/env python3
"""
Single-file Aozora HTML ingestor.

How it works (no CLI args):
- Loads `.env` for PROJECT_ID, VERTEX_LOCATION, GOOGLE_API_KEY, DATABASE_URL
- Globs `aozora_html/*.html`
- For each file:
  1) Derive title from filename
  2) Generate metadata from the title via Gemini (Vertex AI if PROJECT_ID provided, else API key)
  3) Extract body text from HTML and chunk into paragraphs (<= MAX_CHARS; prefer split at '。')
  4) Upsert into DB tables `books` and `paragraphs`, computing char_start/char_end and length_chars

Run:  python ingest_aozora_html.py
Dependencies: python-dotenv, psycopg[binary], beautifulsoup4, google-genai (optional; if missing, metadata is minimally filled)
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any

from dotenv import load_dotenv
from bs4 import BeautifulSoup  # type: ignore
from google import genai  # type: ignore
import sqlalchemy
from google.cloud.sql.connector import Connector, IPTypes


# Tunables
MAX_CHARS = 1200  # paragraph chunk upper bound
RUBY_MODE = "base"  # 'base' or 'annotate'


def load_env() -> Dict[str, Optional[str]]:
    load_dotenv()
    env = {
        "PROJECT_ID": os.getenv("PROJECT_ID"),
        "VERTEX_LOCATION": os.getenv("VERTEX_LOCATION", "asia-northeast1"),
        # Cloud SQL connector params (apply_schema.py と同様の記法)
        "CONNECTION_NAME": os.getenv("CONNECTION_NAME"),
        "DB_USER": os.getenv("DB_USER"),
        "DB_NAME": os.getenv("DB_NAME"),
        "DB_PASS": os.getenv("DB_PASS"),
    }
    missing = [
        k
        for k, v in env.items()
        if v in (None, "") and k in ("CONNECTION_NAME", "DB_USER", "DB_NAME")
    ]
    if missing:
        print(f"Missing required DB envs: {', '.join(missing)}", file=sys.stderr)
        sys.exit(2)
    return env


_connector: Optional[Connector] = None


def get_connector() -> Connector:
    global _connector
    if _connector is None:
        _connector = Connector()
    return _connector


def getconn(env: Dict[str, Optional[str]]):
    return get_connector().connect(
        env["CONNECTION_NAME"],
        "pg8000",
        user=env["DB_USER"],
        db=env["DB_NAME"],
        password=env.get("DB_PASS"),
        enable_iam_auth=True,
        ip_type=IPTypes.PUBLIC,
    )


def create_engine(env: Dict[str, Optional[str]]):
    return sqlalchemy.create_engine(
        "postgresql+pg8000://",
        creator=lambda: getconn(env),
        pool_pre_ping=True,
    )


def derive_title_author_from_filename(path: Path) -> Tuple[str, Optional[str]]:
    """Derive (title, author) from filename.
    Preferred format: "作品名_著者名.html".
    Backward-compat: if suffix is only digits, treat as card number and no author.
    """
    stem = path.stem
    # If ends with _12345, drop the numeric suffix
    m = re.match(r"(.+?)_(\d+)$", stem)
    if m:
        title = m.group(1)
        author = None
    else:
        if "_" in stem:
            # Split at the last underscore to allow underscores in title
            title, author = stem.rsplit("_", 1)
        else:
            title, author = stem, None

    # Clean quotes and spaces
    def clean(s: str) -> str:
        s = s.strip().strip("「」『』“”\"'()[]")
        s = re.sub(r"[_\s]+", " ", s).strip()
        return s

    title = clean(title)
    author = clean(author) if author else None
    return title, author


def make_slug(title: str, author: Optional[str], fallback: Optional[str] = None) -> str:
    base = f"{title}-{author}" if author else title
    base = base.strip()
    # Allow Unicode; just normalize whitespace -> hyphen
    slug = re.sub(r"\s+", "-", base)
    slug = slug.strip("-")
    if not slug and fallback:
        slug = fallback
    if not slug:
        slug = f"book-{abs(hash(base))%100000000}"
    return slug[:255]


def gemini_client(env: Dict[str, Optional[str]]):
    return genai.Client(
        vertexai=True, project=env["PROJECT_ID"], location=env["VERTEX_LOCATION"]
    )


def generate_meta_from_title(title: str, author: str, client) -> Dict[str, Any]:
    """Generate metadata from title only. citation is fixed to 青空文庫."""
    system = (
        "あなたは図書の書誌メタデータ整備を行う司書です。与えられた『作品タイトル』と『著者名』から、"
        "可能な範囲で JSON だけを返してください。フィールド: title(入力そのまま), author(著者名: 不明なら空), "
        "era(明治/大正/昭和/平成/不明), tags(小説/短編/随筆/詩/童話、明るい,暗い,友情,恋愛,苦悩, など。)。"
        "本文は提供しないため、確信が持てない場合は空文字や空配列で返してください。"
    )
    prompt = f"{system}\n\nタイトル: {title}\n著者名: {author}\n\nJSONのみで返答してください。"
    resp = client.models.generate_content(model="gemini-2.5-flash", contents=[prompt])
    out = (resp.text or "").strip()
    if out.startswith("```"):
        out = out.strip("`\n ")
        if out.lower().startswith("json"):
            out = out[4:].lstrip("\n")
    import json

    data = json.loads(out)
    if not isinstance(data.get("tags"), list):
        data["tags"] = [str(data.get("tags", ""))] if data.get("tags") else []
    data["title"] = data.get("title") or title
    data["citation"] = "青空文庫"
    return data


AOZORA_NOTE = re.compile(r"［＃.*?］")
JA_SENT_END = "。"


def html_to_text(html: str) -> Tuple[str, Optional[str], Optional[str]]:
    soup = BeautifulSoup(html, "html.parser")
    title = None
    if soup.title and soup.title.text:
        title = re.sub(r"\s*[（\(].*?青空文庫.*?[）\)]\s*", "", soup.title.text.strip())
    author = None
    # main node candidates
    node = None
    for name, attrs in [
        ("div", {"id": "main_text"}),
        ("div", {"class": "main_text"}),
        ("div", {"id": "text"}),
        ("article", {}),
        ("div", {"id": "contents"}),
    ]:
        node = soup.find(name, attrs=attrs)
        if node:
            break
    if not node:
        node = soup.body or soup
    # remove footers
    for sel in [
        "div.bibliographical_information",
        "div#bibliographical_information",
        "div.footnote",
        "footer",
        "div#footer",
    ]:
        for el in node.select(sel) if hasattr(node, "select") else []:
            el.decompose()
    # ruby
    for rb in node.find_all("ruby") if hasattr(node, "find_all") else []:
        base = "".join(x.get_text() for x in rb.find_all("rb")) or rb.get_text()
        rt = "".join(x.get_text() for x in rb.find_all("rt"))
        repl = base if RUBY_MODE == "base" or not rt else f"{base}({rt})"
        rb.replace_with(repl)
    for br in node.find_all("br") if hasattr(node, "find_all") else []:
        br.replace_with("\n")
    for p in node.find_all("p") if hasattr(node, "find_all") else []:
        p.insert_before("\n\n")
    text = node.get_text("\n") if hasattr(node, "get_text") else str(node)
    return post_cleanup(text), title, author


def html_to_text_regex(html: str) -> Tuple[str, Optional[str], Optional[str]]:
    title = None
    m = re.search(r"<title>(.*?)</title>", html, flags=re.S | re.I)
    if m:
        title = re.sub(r"<.*?>", "", m.group(1)).strip()
        title = re.sub(r"\s*[（\(].*?青空文庫.*?[）\)]\s*", "", title)
    bodym = re.search(r"<body.*?>(.*)</body>", html, flags=re.S | re.I)
    body = bodym.group(1) if bodym else html
    body = re.split(r"底本[：:]", body)[0]
    # drop ruby tags
    body = re.sub(r"<rt.*?>.*?</rt>", "", body, flags=re.S | re.I)
    body = re.sub(r"</?ruby.*?>", "", body, flags=re.S | re.I)
    body = re.sub(r"</?rb.*?>", "", body, flags=re.S | re.I)
    body = re.sub(r"<\s*br\s*/?\s*>", "\n", body, flags=re.I)
    body = re.sub(r"<\s*/p\s*>", "\n\n", body, flags=re.I)
    body = re.sub(r"<\s*p\s*[^>]*>", "", body, flags=re.I)
    text = re.sub(r"<.*?>", "", body)
    return post_cleanup(text), title, None


def post_cleanup(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = AOZORA_NOTE.sub("", text)
    text = re.sub(r"[ \t\u3000]+\n", "\n", text)
    text = re.sub(r"[ \t]+$", "", text, flags=re.M)
    text = re.split(r"\n底本[：:]", text)[0]
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_text(text: str, max_chars: int = MAX_CHARS) -> List[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paras:
        paras = [text]
    out: List[str] = []
    for p in paras:
        if len(p) <= max_chars:
            out.append(p)
            continue
        start = 0
        n = len(p)
        while start < n:
            end = min(start + max_chars, n)
            # try to cut at last '。' within the window
            window = p[start:end]
            cut = window.rfind(JA_SENT_END)
            if cut != -1 and (start + cut + 1 - start) >= max_chars * 0.6:
                end = start + cut + 1
            chunk = p[start:end].strip()
            if chunk:
                out.append(chunk)
            start = end
    return out


def extract_and_chunk(
    html_path: Path,
) -> Tuple[List[str], Optional[str], Optional[str]]:
    html = html_path.read_text(encoding="utf-8", errors="ignore")
    text, title_in_doc, author_in_doc = html_to_text(html)
    chunks = chunk_text(text, MAX_CHARS)
    return chunks, title_in_doc, author_in_doc


def upsert_book_and_paragraphs(
    engine,
    meta: Dict[str, Any],
    paragraphs: List[str],
    aozora_url: Optional[str] = None,
) -> int:
    title = meta.get("title") or ""
    author = meta.get("author") or None
    era = meta.get("era") or None
    tags = meta.get("tags") or None
    citation = meta.get("citation") or "青空文庫"
    slug = make_slug(title, author)
    length_chars = sum(len(p) for p in paragraphs) + max(0, 2 * (len(paragraphs) - 1))

    with engine.begin() as conn:
        res = conn.exec_driver_sql(
            """
            INSERT INTO books (slug, title, author, era, length_chars, tags, aozora_source_url, citation)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (slug) DO UPDATE SET
              title=EXCLUDED.title,
              author=EXCLUDED.author,
              era=EXCLUDED.era,
              length_chars=EXCLUDED.length_chars,
              tags=EXCLUDED.tags,
              aozora_source_url=EXCLUDED.aozora_source_url,
              citation=EXCLUDED.citation
            RETURNING id
            """,
            (slug, title, author, era, length_chars, tags, aozora_url, citation),
        )
        book_id = res.scalar_one()

        conn.exec_driver_sql("DELETE FROM paragraphs WHERE book_id = %s", (book_id,))
        offset = 0
        for idx, text in enumerate(paragraphs):
            start = offset
            end = start + len(text)
            conn.exec_driver_sql(
                """
                INSERT INTO paragraphs (book_id, idx, text, char_start, char_end)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (book_id, idx, text, start, end),
            )
            offset = end + 2
        return book_id


def main():
    env = load_env()
    client = gemini_client(env)
    engine = create_engine(env)
    html_dir = Path("aozora_html")
    files = sorted(html_dir.glob("*.html"))
    if not files:
        print("No HTML files found in aozora_html")
        return
    print(f"Found {len(files)} HTML files. Starting ingest…")
    ok = 0
    for i, path in enumerate(files, 1):
        base_title, author_from_name = derive_title_author_from_filename(path)
        meta = generate_meta_from_title(base_title, author_from_name, client)
        paras, title_in_doc, _author_in_doc = extract_and_chunk(path)
        if not meta.get("title"):
            meta["title"] = title_in_doc or base_title
        # Author is definitive from filename format: override any model output
        meta["author"] = author_from_name or meta.get("author") or ""
        book_id = upsert_book_and_paragraphs(engine, meta, paras)
        print(
            f"[{i}/{len(files)}] OK {path.name} -> book_id={book_id}, paras={len(paras)}, title={meta.get('title')}, "
        )
        ok += 1
    get_connector().close()
    print(f"Done. processed={ok}/{len(files)}")


if __name__ == "__main__":
    main()
