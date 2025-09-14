import re
import os
import dotenv
from sqlalchemy import text
from google.adk.agents import Agent
import numpy as np
from numpy.linalg import norm
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from google import genai


dotenv.load_dotenv()

PROJECT_ID = os.getenv("PROJECT_ID", "")
LOCATION = os.getenv("LOCATION", "")
BUCKET_NAME = os.getenv("CHARACTERS_BUCKET", "")

CONNECTION_NAME = os.getenv("CONNECTION_NAME")
DB_USER = os.getenv("DB_USER")
DB_NAME = os.getenv("DB_NAME")
DB_PASS = os.getenv("DB_PASS")
ENABLE_IAM_AUTH = os.getenv("ENABLE_IAM_AUTH", "false").lower() == "true"
CLOUD_SQL_IP_TYPE = (os.getenv("CLOUD_SQL_IP_TYPE", "PUBLIC") or "PUBLIC").upper()
DATABASE_URL = os.getenv("DATABASE_URL")

VERTEX_LOCATION = os.getenv("VERTEX_LOCATION", "us-central1")
EMBED_MODEL = os.getenv("EMBED_MODEL", "gemini-embedding-001")


# DBの作成
def _create_engine():
    if CONNECTION_NAME and DB_USER and DB_NAME:
        # Cloud SQL connector via pg8000
        def getconn():
            from google.cloud.sql.connector import Connector, IPTypes  # lazy import

            connector = Connector()
            kwargs = {
                "driver": "pg8000",
                "user": DB_USER,
                "db": DB_NAME,
                "enable_iam_auth": ENABLE_IAM_AUTH,
                "ip_type": (
                    IPTypes.PRIVATE
                    if CLOUD_SQL_IP_TYPE == "PRIVATE"
                    else IPTypes.PUBLIC
                ),
            }
            # Use password only when IAM auth is disabled
            if not ENABLE_IAM_AUTH and DB_PASS:
                kwargs["password"] = DB_PASS
            return connector.connect(CONNECTION_NAME, **kwargs)

        return create_engine(
            "postgresql+pg8000://",
            creator=getconn,
            pool_pre_ping=True,
            future=True,
        )
    # Fallback to DATABASE_URL
    url = DATABASE_URL or "postgresql+psycopg://user:pass@localhost:5432/reading"
    return create_engine(url, pool_pre_ping=True, future=True)


engine = _create_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
db = SessionLocal()

# embedding関連の定義
client = genai.Client(vertexai=True, project=PROJECT_ID, location=VERTEX_LOCATION)


def embed_text(text):
    resp = client.models.embed_content(
        model=EMBED_MODEL, contents=[text], config={"output_dimensionality": 768}
    )
    return list(resp.embeddings[0].values)


# ツールの定義
def run_select_sql(sql: str) -> dict:
    """Run a SELECT SQL query and return the results as a JSON.
    利用できるDBのSchemaは以下の通り。
    books (id integer, title varchar, author varchar, era varchar, length_chars integer, tags text[], summary text)
    paragraphs (id integer, book_id integer, idx integer, text text)
    # Schema補足説明
    - authorは著者名で、苗字・名前の間にスペースが入る場合があります。苗字または名前を「含む」での検索を推奨。
    - eraはその小説が書かれた時代。明治、大正、昭和、不明の4種類。
    - length_charsは小説の文字数。
    - tagsは小説のジャンルを表すタグ。小説、文学といった種類から、明るい、暗い、恋愛、平和、など多様なタグがある。
    """
    q = sql.strip()
    if not re.match(r"(?is)^\s*select\b", q):
        return {"status": "error", "message": "Only SELECT queries are allowed."}
    result = db.execute(text(sql))
    return {"status": "success", "rows": [dict(row._mapping) for row in result]}


def vector_search_paragraphs(query: str, top_k: int = 10) -> dict:
    """Perform a vector search on the paragraphs table and return the top K titles, book_id, contents, and scores.
    各行に保存されているのは、各物語の段落1文です。
    物語の段落のような文章をクエリとして生成し、本関数を呼び出してください。"""
    # クエリのベクトル化
    query_embedding = embed_text(query)
    # 正規化
    query_embedding = np.array(query_embedding) / norm(np.array(query_embedding))
    # np.ndarray -> List[float] に変換
    query_embedding = query_embedding.astype(float).tolist()

    sql = f"""
    SELECT books.title, books.book_id, paragraphs.text, paragraphs.embed <=> :qvec AS score
    FROM paragraphs
    JOIN books ON paragraphs.book_id = books.id
    ORDER BY score
    LIMIT {top_k};
    """

    result = db.execute(text(sql), {"qvec": str(query_embedding)})
    return {"status": "success", "rows": [dict(row._mapping) for row in result]}


# エージェントの定義
SYSTEM_INSTRUCTION = """
あなたは「AI司書」エージェントです。
ユーザーからの質問と、ユーザーの過去の読書履歴を鑑みて、おすすめの本を提示してください。
# 指示
- 本の推奨前には、必ずいずれかのツールを使って、DBから本の情報を取得してください。
- 推奨する本のタイトルは、正しいbook_idを持つaタグで囲んでください。
例: <a href="1">本のタイトル</a>
book_idは、booksテーブルのidカラム、paragraphsテーブルのbook_idカラムに対応しています。**検索実施の上、必ず正しい値を付与してください。**
- ユーザーの過去の読書履歴から、次にユーザーが興味を持ちそうな本を推薦してください。文字数・時代・タグ・チャプターのベクトル検索が利用できます。
"""

root_agent = Agent(
    name="AI_librarian",
    model="gemini-2.5-pro",
    instruction=SYSTEM_INSTRUCTION,
    tools=[run_select_sql, vector_search_paragraphs],
)
sample_history = """
# ユーザーの読書履歴
## 読了済みの本
### あばばばば 芥川龍之介
感想: 大正時代の時代背景がよくわかった。短くて読みやすく、クスリとできるのが良かった。
### 銀河鉄道の夜 宮沢賢治
感想: 夢のような世界観が素晴らしかった。登場人物の心情描写が深く、感動的だった。
## ハイライトした文章
### 銀河鉄道の夜 宮沢賢治
> ほんとうの幸いは、他人の不幸を見て、自分の幸いを知ることだ。
> ほんとうの幸福は、他人の幸福を願うことだ。
"""
