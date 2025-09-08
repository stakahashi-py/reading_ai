import time, csv, os, re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

BASE = "https://www.aozora.gr.jp/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AozoraCollector/1.2)"}

RANK_URLS = [
    # "https://www.aozora.gr.jp/access_ranking/2020_xhtml.html",
    "https://www.aozora.gr.jp/access_ranking/2022_xhtml.html",
]
TARGET_COUNT = 200
os.makedirs("aozora_html", exist_ok=True)


def get_top_cards(rank_url, limit=500):
    r = requests.get(rank_url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.content, "html.parser")
    card_urls = []
    for a in soup.select("a[href*='/cards/'][href*='card']"):
        href = urljoin(BASE, a.get("href"))
        if href not in card_urls:
            card_urls.append(href)
        if len(card_urls) >= limit:
            break
    return card_urls


def fetch_card(card_url):
    r = requests.get(card_url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    html = r.text
    return html, BeautifulSoup(html, "html.parser")


def is_copyrighted_card(card_html_text):
    # 図書カード本文に「著作権存続」が含まれていたら除外
    return "著作権存続" in card_html_text


def resolve_xhtml_url(card_url, soup):
    """
    図書カードの『ファイルのダウンロード』表から
    ・アンカー文字列に「XHTML」を含む
    ・hrefが .html で終わる
    ・hrefに 'card' が含まれない（図書カード自身の誤取得を防ぐ）
    を満たすリンクだけを採用
    """
    # 1) “XHTML”表記を優先
    for a in soup.select("a[href$='.html']"):
        label = (a.get_text() or "").strip()
        href = a.get("href") or ""
        if "XHTML" in label and "card" not in href:
            return urljoin(card_url, href)

    # 2) ラベルが取れない場合、.html かつ 'files/' 配下など本文らしいものを候補に
    for a in soup.select("a[href$='.html']"):
        href = a.get("href") or ""
        if "card" in href:
            continue
        if any(seg in href for seg in ("/files/", "/orig/", "/aozorabunko/")):
            return urljoin(card_url, href)

    # 3) 予備：「いますぐXHTML版で読む」等
    a = soup.find("a", string=lambda s: s and "XHTML" in s)
    if a and a.get("href"):
        href = a.get("href")
        if "card" not in href:
            return urljoin(card_url, href)

    return None


def extract_meta_from_card(card_url, soup):
    def cell_after(label):
        el = soup.find(string=re.compile(rf"^{label}"))
        return el.parent.find_next().get_text(strip=True) if el else ""

    title = cell_after("作品名")
    author = cell_after("著者名")
    card_no_match = re.search(r"card(\d+)\.html", card_url)
    card_no = card_no_match.group(1) if card_no_match else "unknown"
    return {"title": title, "author": author, "card_no": card_no, "card_url": card_url}


def download_xhtml_as_utf8(xhtml_url, out_path):
    r = requests.get(xhtml_url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    # 多くは Shift_JIS。apparent_encoding に倒しつつ UTF-8 保存
    r.encoding = r.apparent_encoding or "shift_jis"
    text = r.text
    # 念のため、図書カード誤保存の検出（タイトルに「図書カード」が入っていたら弾く）
    if "図書カード" in text[:2000]:
        raise ValueError("This looks like a card page, not body XHTML.")
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def safe_filename(title: str, card_no: str, ext: str = ".html") -> str:
    # 禁止文字をアンダースコアに
    fname = re.sub(r'[\\/:*?"<>|]', "_", title)
    # スペースや全角スペースも統一
    fname = re.sub(r"\s+", "_", fname)
    # 長すぎる場合は切る
    if len(fname) > 80:
        fname = fname[:80]
    # カード番号を必ず付与して重複防止
    return f"{fname}_{card_no}{ext}"


def make_body_filename(card_no, xhtml_url):
    # 本文URL末尾のファイル名を活かしつつカード番号を先頭に
    tail = os.path.basename(urlparse(xhtml_url).path) or "body.html"
    return f"{card_no}_{tail}"


seen = set()
selected = []

for rank in RANK_URLS:
    for card in get_top_cards(rank, limit=500):
        if card in seen:
            continue
        seen.add(card)

        # 図書カード取得＆著作権存続チェック（本文DL前に判定）
        card_html, soup = fetch_card(card)
        if is_copyrighted_card(card_html):
            print("skip copyrighted (card note):", card)
            time.sleep(0.8)
            continue

        # 本文(XHTML)の直リンクを解決
        xhtml = resolve_xhtml_url(card, soup)
        if not xhtml:
            print("no xhtml link:", card)
            time.sleep(0.8)
            continue

        meta = extract_meta_from_card(card, soup)
        meta["xhtml_url"] = xhtml

        # 本文をUTF-8で保存
        fname = safe_filename(meta["title"], meta["author"])
        out_path = os.path.join("aozora_html", fname)
        try:
            download_xhtml_as_utf8(xhtml, out_path)
        except Exception as e:
            print("download failed:", xhtml, e)
            time.sleep(0.8)
            continue

        meta["file_path"] = out_path
        selected.append(meta)
        print(f"saved BODY: {meta['title']} / {meta['author']} -> {fname}")
        time.sleep(1)

        if len(selected) >= TARGET_COUNT:
            break
    if len(selected) >= TARGET_COUNT:
        break

# 監査用メタCSV
with open("aozora_selection.csv", "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(
        f,
        fieldnames=["title", "author", "card_no", "card_url", "xhtml_url", "file_path"],
    )
    w.writeheader()
    w.writerows(selected)

print("total:", len(selected))
