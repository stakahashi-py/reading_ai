#!/usr/bin/env python3
"""
web/books_html の各HTMLの「最後のdiv」に底本を追記します。
"""

from pathlib import Path
import glob

from bs4 import BeautifulSoup  # type: ignore


def _get_last_content_div(soup: BeautifulSoup):
    """最終段落のコンテンツdiv（.leading-relaxed）を返す。無ければ最後のdiv。"""
    paras = soup.find_all("div", class_="para")
    if paras:
        last_para = paras[-1]
        inner = last_para.find("div", class_="leading-relaxed")
        return inner or last_para
    # フォールバック: 最後のdiv
    divs = soup.find_all("div")
    return divs[-1] if divs else None


# def find_books_without_citation_in_html(html_dir: Path = HTML_DIR) -> List[str]:
#     """最後のdivに「底本：」が含まれていないHTMLのslug一覧を返す。"""
#     missing: List[str] = []
#     for p in sorted(html_dir.glob("*.html")):
#         try:
#             soup = BeautifulSoup(p.read_text(encoding="utf-8"), "html.parser")
#             target = _get_last_content_div(soup)
#             if not target:
#                 continue
#             txt = target.get_text("\n")
#             if "底本：" not in txt:
#                 missing.append(p.stem)
#         except Exception:
#             # 壊れたHTMLは無視
#             continue
#     return missing


def get_citation(path: str):
    path = Path(path)
    raw = path.read_bytes()
    for enc in ("cp932", "shift_jis", "utf-8"):  # 順に試す
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        # すべて失敗
        print("=====")
        print(path)
        print("[DECODE ERROR]")
        return

    soup = BeautifulSoup(text, "html.parser")

    # id でも class でも拾えるように
    info_div = soup.find("div", id="bibliographical_information") or soup.find(
        "div", class_="bibliographical_information"
    )

    if info_div:

        # <br> を改行に変換しつつテキスト化
        for br in info_div.select("br"):
            br.replace_with("")
        content = info_div.get_text("\n")
        # 連続空行を1行に圧縮
        lines = [ln.rstrip() for ln in content.splitlines()]
        # 前後の空行除去しつつ内部はそのまま(空行1つは残す)
        cleaned = []
        prev_blank = False
        for ln in lines:
            if ln.strip() == "":
                if not prev_blank:
                    cleaned.append("")
                prev_blank = True
            else:
                cleaned.append(ln)
                prev_blank = False
        cleaned_text = (
            "\n".join(l for l in cleaned if l is not None)
            .strip("\n")
            .replace("\n\n", "\n")
        )
        return cleaned_text
    else:
        print("=====")
        print(path)
        print("[NOT FOUND bibliographical_information]")


def append_citation(html_path, citation):
    """HTMLの最後のdivに citation を追記する。"""
    path = Path(html_path)
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    target = _get_last_content_div(soup)
    if not target:
        # print("=====")
        print(path)
        print("[NOT FOUND last div]")
        return False
    txt = target.get_text("\n")
    if "底本：" in txt:
        # すでにある場合、既存のHTMLの最後のdivを新しい底本に置き換えるため削除
        target.clear()

    # 追記
    new_div = soup.new_tag("div")
    new_div.string = citation
    target.parent.append(new_div)

    # 保存
    path.write_text(str(soup), encoding="utf-8")
    return True


def main():

    # missing = find_books_without_citation_in_html(HTML_DIR)
    # print(f"missing={len(missing)}")
    # print(missing[0].split("-")[0] + "-")

    # aozora_html以下のHTMLをすべて処理する
    paths = glob.glob("aozora_html/*.html")
    print(f"Found {len(paths)} HTML files.")
    for path in paths:
        citation = get_citation(path)
        if not citation:
            print(f"Failed to get citation: {path}")
            continue
        # 本のタイトルから、web/books_html 以下のHTMLを探す
        slug = Path(path).stem.split("_")[0] + "-"
        # print(f"Processing: {slug}")
        # 該当するHTMLを探す
        html_files = glob.glob(f"web/books_html/{slug}*.html")
        if not html_files:
            print(f"No matching HTML file for slug: {slug}")
            continue
        if len(html_files) > 1:
            print(
                f"Multiple matching HTML files for slug: {slug}, using the first one."
            )
        html_file = html_files[0]
        success = append_citation(html_file, citation)
        if not success:
            print(f"Failed to patch: {slug}")


if __name__ == "__main__":
    main()
