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
import json
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any
from pydantic import BaseModel

try:
    from dotenv import load_dotenv
except Exception:  # 実行環境に dotenv が無くても動作させる

    def load_dotenv():
        return None


from bs4 import BeautifulSoup  # type: ignore

try:
    from google import genai  # type: ignore
except Exception:
    genai = None  # type: ignore
import sqlalchemy
from google.cloud.sql.connector import Connector, IPTypes


# Tunables
MAX_CHARS = 5000  # paragraph chunk upper bound
RUBY_MODE = "base"  # 'base' or 'annotate'


# 構造化出力用のPydanticモデル
class Metadata(BaseModel):
    title: str
    author: str
    era: str
    tags: list[str]
    summary: str


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
    if genai is None or not env.get("PROJECT_ID"):
        return None
    return genai.Client(
        vertexai=True, project=env["PROJECT_ID"], location=env["VERTEX_LOCATION"]
    )


def generate_meta(
    title: str, author: str, sample_text: Optional[str], client
) -> Dict[str, Any]:
    """Generate metadata including summary. citation is fixed to 青空文庫."""
    system = (
        "あなたは図書の書誌メタデータ整備を行う司書です。与えられた『作品タイトル』と『著者名』から、"
        "JSONだけを返してください。フィールド: title(入力そのまま), author(著者名: 不明なら空), "
        "era(明治/大正/昭和/平成/不明), tags(小説/短編/随筆/詩/童話、明るい,暗い,友情,恋愛,苦悩, など。), summary(作品の概要。例・芥川龍之介「あばばばば」: 主人公はまだ言葉を覚え始めたばかりの赤ん坊で、「あばばばば」と意味のない発声を繰り返すが、その内心では哲学的・観念的なことを考えているという、ユーモラスで風刺的な短編小説。芥川の数ある短編の中でも、「ナンセンス文学」や「戯作的な掌編」として知られる)。"
        "解答の際はWeb検索を行い、情報を補完してください。"
    )
    sample = (sample_text or "").strip()
    if len(sample) > 1500:
        sample = sample[:1500]
    prompt = f"{system}\n\nタイトル: {title}\n著者名: {author}\n本文抜粋:\n{sample}\n\nJSONのみで返答してください。"
    if client is None:
        return {
            "title": title,
            "author": author or "",
            "era": "",
            "tags": [],
            "summary": "",
            "citation": "青空文庫",
        }
    # Web検索
    grounding_tool = genai.types.Tool(google_search=genai.types.GoogleSearch())
    retry_num = 5
    while retry_num > 0:
        try:
            resp = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[prompt],
                config={
                    "response_mime_type": "application/json",
                    "response_schema": Metadata,
                    "tools": [grounding_tool],
                },
            )
            out = resp.text
            data = json.loads(out)
            break
        except Exception as e:
            print(f"{title}でエラー、{6 - retry_num}回目", file=sys.stderr)
            retry_num -= 1
            continue
    data["citation"] = "青空文庫"
    return data


AOZORA_NOTE = re.compile(r"［＃.*?］")
JA_SENT_END = "。"


def _extract_biblio_text(soup) -> Optional[str]:
    """div.bibliographical_information/#bibliographical_information をテキスト抽出→整形して返す。"""
    try:
        el = None
        if hasattr(soup, "find"):
            el = soup.find("div", class_="bibliographical_information") or soup.find(
                id="bibliographical_information"
            )
        if el and hasattr(el, "get_text"):
            txt = el.get_text("\n")
            txt = AOZORA_NOTE.sub("", txt)
            txt = re.sub(r"\n{3,}", "\n\n", txt).strip()
            return txt if txt else None
    except Exception:
        pass
    return None


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
    # 書誌ブロック抽出→本文から除去
    biblio_text = _extract_biblio_text(soup)
    for el in [
        (
            node.find("div", class_="bibliographical_information")
            if hasattr(node, "find")
            else None
        ),
        node.find(id="bibliographical_information") if hasattr(node, "find") else None,
    ]:
        if el:
            try:
                el.decompose()
            except Exception:
                pass
    # remove footers（書誌以外）
    for sel in ["div.footnote", "footer", "div#footer"]:
        for el in node.select(sel) if hasattr(node, "select") else []:
            el.decompose()
    # ruby: ルビは基底のみ残し、rt/rpを削除（括弧も削除）
    for rb in node.find_all("ruby") if hasattr(node, "find_all") else []:
        for t in rb.find_all(["rt", "rp"]):
            t.decompose()
        base = rb.get_text()
        rb.replace_with(base)
    for br in node.find_all("br") if hasattr(node, "find_all") else []:
        br.replace_with("\n")
    for p in node.find_all("p") if hasattr(node, "find_all") else []:
        p.insert_before("\n\n")
    # インライン境界の改行を防ぐため separator なし
    text = node.get_text() if hasattr(node, "get_text") else str(node)
    text = post_cleanup(text)
    if biblio_text:
        text = text + "\n\n" + biblio_text
    return text, title, author


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
    body = re.sub(r"<rp.*?>.*?</rp>", "", body, flags=re.S | re.I)
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
    # ここでは『底本：』以降は切り落とさない（後段で書誌ブロックとして付与するため）
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _ascend_to_main_child(main, el):
    """main 直下の子要素になるまで祖先を遡る。"""
    cur = el
    from bs4.element import Tag

    while isinstance(cur, Tag) and cur.parent is not None and cur.parent is not main:
        cur = cur.parent
    return cur


def html_to_paragraphs_with_poem(
    html: str,
) -> Tuple[List[str], Optional[str], Optional[str]]:
    """HTML→段落配列。ルビは基底のみ。詩ブロックは見出しごとに1段落。
    詩判定: ブロック内の非空行のうち、句読点を含まない行が閾値以上（0.6）
    """
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

    # 書誌ブロック抽出→本文からは除去（最後に1段落で付与）
    biblio_text = _extract_biblio_text(soup)
    for el in [
        (
            node.find("div", class_="bibliographical_information")
            if hasattr(node, "find")
            else None
        ),
        node.find(id="bibliographical_information") if hasattr(node, "find") else None,
    ]:
        if el:
            try:
                el.decompose()
            except Exception:
                pass
    # remove footers（書誌以外）
    for sel in [
        "div.footnote",
        "footer",
        "div#footer",
    ]:
        for el in node.select(sel) if hasattr(node, "select") else []:
            el.decompose()

    # gaiji alt を残す
    for img in node.find_all("img") if hasattr(node, "find_all") else []:
        cls = img.get("class") or []
        if "gaiji" in cls:
            alt = img.get("alt") or ""
            img.replace_with(alt)

    # ruby: rt/rp 除去、基底のみ
    for rb in node.find_all("ruby") if hasattr(node, "find_all") else []:
        for t in rb.find_all(["rt", "rp"]):
            t.decompose()
        rb.replace_with(rb.get_text())

    # <br>→\n, <p>の前に空行
    for br in node.find_all("br") if hasattr(node, "find_all") else []:
        br.replace_with("\n")
    for p in node.find_all("p") if hasattr(node, "find_all") else []:
        p.insert_before("\n\n")

    # 見出しコンテナを抽出（h1-6 を含む main 直下の子）
    headings = (
        node.find_all([f"h{i}" for i in range(1, 7)])
        if hasattr(node, "find_all")
        else []
    )
    containers = []
    if headings:
        for hx in headings:
            containers.append(_ascend_to_main_child(node, hx))
        # main 直下の順序で一意化
        seen = set()
        ordered_children = list(node.children)
        unique_containers = []
        for ch in ordered_children:
            if ch in containers and id(ch) not in seen:
                unique_containers.append(ch)
                seen.add(id(ch))
        containers = unique_containers

    parts: List[str] = []

    def collect_text(elements) -> str:
        from bs4.element import NavigableString, Tag

        buf: List[str] = []
        for el in elements:
            if isinstance(el, NavigableString):
                buf.append(str(el))
            elif hasattr(el, "get_text"):
                buf.append(el.get_text())
        return post_cleanup("".join(buf))

    children = list(node.children)
    if not containers:
        # 見出しが無い場合は従来処理相当
        text = collect_text(children)
        paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        return paras, title, author

    # プレリュード（最初の見出しまで）
    first_idx = children.index(containers[0])
    prelude = collect_text(children[:first_idx])
    if prelude:
        parts.extend([p.strip() for p in re.split(r"\n\s*\n", prelude) if p.strip()])

    # 各見出しブロック
    def is_poem_block(s: str) -> bool:
        lines = [ln.strip() for ln in s.split("\n") if ln.strip()]
        if len(lines) < 3:
            return False
        no_punct = sum(
            1 for ln in lines if not re.search(r"[。．！？?!、，；;：:]", ln)
        )
        return (no_punct / max(1, len(lines))) >= 0.6

    for idx, cont in enumerate(containers):
        start = children.index(cont) + 1
        end = (
            children.index(containers[idx + 1])
            if idx + 1 < len(containers)
            else len(children)
        )
        block_elems = children[start:end]
        block_text = collect_text(block_elems)
        # 見出しそのもの（タイトル）は別段落として保持
        # タイトル抽出
        hx = cont.find([f"h{i}" for i in range(1, 7)])
        if hx and hx.get_text(strip=True):
            parts.append(hx.get_text(strip=True))
        if not block_text.strip():
            continue
        if is_poem_block(block_text):
            # 詩はブロック全体を1段落（内部の空行は1改行に縮約）
            para = re.sub(r"\n{2,}", "\n", block_text).strip()
            parts.append(para)
        else:
            parts.extend(
                [p.strip() for p in re.split(r"\n\s*\n", block_text) if p.strip()]
            )

    # 書誌ブロックがあれば末尾に追加
    if biblio_text:
        parts.append(biblio_text)
    return parts, title, author


def chunk_paragraphs(paras: List[str], max_chars: int = MAX_CHARS) -> List[str]:
    out: List[str] = []
    for p in paras:
        if len(p) <= max_chars:
            out.append(p)
            continue
        start = 0
        n = len(p)
        while start < n:
            end = min(start + max_chars, n)
            window = p[start:end]
            # 直前の改行 or 句読点で切る
            candidates = []
            for ch in (
                "\n",
                "。",
                "．",
                "！",
                "!",
                "？",
                "?",
                "、",
                "，",
                ",",
                "；",
                ";",
                "：",
                ":",
            ):
                pos = window.rfind(ch)
                if pos != -1:
                    candidates.append(pos)
            if candidates:
                cut = max(candidates)
                end = start + cut + 1
            else:
                m = re.search(r"[ \t\u3000]+(?!.*[ \t\u3000])", window)
                if m:
                    end = start + m.end()
            chunk = p[start:end].strip()
            if chunk:
                out.append(chunk)
            start = end
    return out


def extract_and_chunk(
    html_path: Path,
) -> Tuple[List[str], Optional[str], Optional[str]]:
    html = html_path.read_text(encoding="utf-8", errors="ignore")
    paras, title_in_doc, author_in_doc = html_to_paragraphs_with_poem(html)
    chunks = chunk_paragraphs(paras, MAX_CHARS)
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
    summary = meta.get("summary") or None
    slug = make_slug(title, author)
    length_chars = sum(len(p) for p in paragraphs) + max(0, 2 * (len(paragraphs) - 1))

    with engine.begin() as conn:
        res = conn.exec_driver_sql(
            """
            INSERT INTO books (slug, title, author, era, summary, length_chars, tags, aozora_source_url, citation)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (slug) DO UPDATE SET
              title=EXCLUDED.title,
              author=EXCLUDED.author,
              era=EXCLUDED.era,
              summary=EXCLUDED.summary,
              length_chars=EXCLUDED.length_chars,
              tags=EXCLUDED.tags,
              aozora_source_url=EXCLUDED.aozora_source_url,
              citation=EXCLUDED.citation
            RETURNING id
            """,
            (
                slug,
                title,
                author,
                era,
                summary,
                length_chars,
                tags,
                aozora_url,
                citation,
            ),
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


def to_json_array(tags: Optional[List[str]]) -> str:
    import json

    return json.dumps(tags or [], ensure_ascii=False)


def write_csv(
    out_dir: Path, books_rows: List[Dict[str, Any]], paras_rows: List[Dict[str, Any]]
):
    import csv

    out_dir.mkdir(parents=True, exist_ok=True)
    books_path = out_dir / "books.csv"
    paras_path = out_dir / "paragraphs.csv"

    with books_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "slug",
                "title",
                "author",
                "era",
                "summary",
                "length_chars",
                "tags_json",
                "aozora_source_url",
                "citation",
            ]
        )
        for r in books_rows:
            w.writerow(
                [
                    r.get("slug"),
                    r.get("title"),
                    r.get("author"),
                    r.get("era"),
                    r.get("summary"),
                    r.get("length_chars"),
                    to_json_array(r.get("tags")),
                    r.get("aozora_source_url"),
                    r.get("citation"),
                ]
            )

    with paras_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["slug", "idx", "text", "char_start", "char_end"])
        for r in paras_rows:
            w.writerow(
                [
                    r.get("slug"),
                    r.get("idx"),
                    r.get("text"),
                    r.get("char_start"),
                    r.get("char_end"),
                ]
            )


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Extract Aozora XHTML and write CSV for COPY"
    )
    parser.add_argument(
        "paths", nargs="*", help="HTML file paths or glob patterns under aozora_html/"
    )
    parser.add_argument("--limit", type=int, default=0, help="Process at most N files")
    parser.add_argument(
        "--max-chars", type=int, default=MAX_CHARS, help="Chunk upper bound"
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Disable LLM metadata generation even if available",
    )
    parser.add_argument(
        "--out-dir",
        default="preprocessing/out_csv",
        help="Directory to write books.csv and paragraphs.csv",
    )
    args = parser.parse_args()

    html_dir = Path("aozora_html")
    files: List[Path] = []
    if args.paths:
        for p in args.paths:
            pth = Path(p)
            if pth.is_file():
                files.append(pth)
            else:
                files.extend(sorted(html_dir.glob(p)))
    else:
        files = sorted(html_dir.glob("*.html"))
    if args.limit and len(files) > args.limit:
        files = files[: args.limit]
    if not files:
        print("No HTML files found (aozora_html)")
        return

    env = load_env()
    client = None if args.no_llm else gemini_client(env)

    books_rows: List[Dict[str, Any]] = []
    paras_rows: List[Dict[str, Any]] = []

    for i, path in enumerate(files, 1):
        base_title, author_from_name = derive_title_author_from_filename(path)
        chunks, title_in_doc, _author_in_doc = extract_and_chunk(path)
        sample = "\n\n".join(chunks[:3])
        meta = generate_meta(
            title_in_doc or base_title, author_from_name or "", sample, client
        )
        # タイトルは常にファイル名起点（著者混入を防ぐ）
        meta["title"] = base_title
        meta["author"] = author_from_name or meta.get("author") or ""

        title = meta.get("title") or base_title
        author = meta.get("author") or ""
        era = meta.get("era") or None
        summary = meta.get("summary") or None
        tags = meta.get("tags") or []
        citation = meta.get("citation") or "青空文庫"
        slug = make_slug(base_title, author_from_name)
        length_chars = sum(len(p) for p in chunks) + max(0, 2 * (len(chunks) - 1))

        books_rows.append(
            {
                "slug": slug,
                "title": title,
                "author": author,
                "era": era,
                "summary": summary,
                "length_chars": length_chars,
                "tags": tags,
                "aozora_source_url": None,
                "citation": citation,
            }
        )

        offset = 0
        for idx, text in enumerate(chunks):
            start = offset
            end = start + len(text)
            paras_rows.append(
                {
                    "slug": slug,
                    "idx": idx,
                    "text": text,
                    "char_start": start,
                    "char_end": end,
                }
            )
            offset = end + 2

        print(f"[{i}/{len(files)}] {path.name} -> slug={slug}, paras={len(chunks)}")

    out_dir = Path(args.out_dir)
    write_csv(out_dir, books_rows, paras_rows)
    print(f"CSV written: {out_dir}/books.csv and {out_dir}/paragraphs.csv")


if __name__ == "__main__":
    main()
