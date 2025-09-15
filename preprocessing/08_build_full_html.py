#!/usr/bin/env python3
"""
paragraphs.csv から書籍ごとの段落HTMLを事前生成します。
出力先: web/books_html/<slug>.html
 - 各段落を <div class="para" id="p-<idx>" data-idx="<idx>">...</div> の形で出力
 - テキスト内の改行は <br/> に変換
 - HTML特殊文字はエスケープ
使い方:
  python preprocessing/06_build_full_html.py
前提:
  preprocessing/books.csv, preprocessing/paragraphs.csv が存在すること。
"""
from __future__ import annotations
import csv
import html
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOOKS_CSV = ROOT / "preprocessing" / "books.csv"
PARAS_CSV = ROOT / "preprocessing" / "paragraphs.csv"
OUT_DIR = ROOT / "web" / "books_html"


def ensure_outdir() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)


def load_titles() -> dict[str, dict]:
    titles: dict[str, dict] = {}
    if BOOKS_CSV.exists():
        with BOOKS_CSV.open("r", encoding="utf-8") as f:
            r = csv.DictReader(f)
            for row in r:
                slug = row.get("slug") or ""
                if not slug:
                    continue
                titles[slug] = {
                    "title": row.get("title") or "",
                    "author": row.get("author") or "",
                    "era": row.get("era") or "",
                }
    return titles


def generate() -> None:
    ensure_outdir()
    titles = load_titles()
    by_slug: dict[str, list[dict]] = defaultdict(list)
    if not PARAS_CSV.exists():
        raise FileNotFoundError("preprocessing/paragraphs.csv not found")
    with PARAS_CSV.open("r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            slug = row.get("slug") or ""
            if not slug:
                continue
            try:
                idx = int(row.get("idx") or 0)
            except Exception:
                idx = 0
            text = row.get("text") or ""
            by_slug[slug].append({"idx": idx, "text": text})
    for slug, items in by_slug.items():
        items.sort(key=lambda x: x["idx"])
        parts: list[str] = []
        # 先頭にコメント（識別用）
        meta = titles.get(slug, {})
        parts.append(
            f"<!-- book: {html.escape(slug)} | {html.escape(meta.get('title',''))} -->"
        )
        for it in items:
            idx = it["idx"]
            # 改行を <br/> に。またHTML特殊文字をエスケープ。
            body = html.escape(it["text"]).replace("\n", "<br/>")
            parts.append(
                f'<div class="para rounded hover:bg-gray-50 p-2" id="p-{idx}" data-idx="{idx}">\n'
                f'  <div class="leading-relaxed">{body}</div>\n'
                f"</div>"
            )
        out = OUT_DIR / f"{slug}.html"
        out.write_text("\n".join(parts) + "\n", encoding="utf-8")
        print(f"wrote {out.relative_to(ROOT)} ({len(items)} paras)")


if __name__ == "__main__":
    generate()
