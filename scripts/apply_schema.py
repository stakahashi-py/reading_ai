#!/usr/bin/env python3
"""
Apply db/schema.sql using SQLAlchemy/psycopg so psql is not required.
Uses DATABASE_URL if present, otherwise PSQL_URL (normalized to SQLAlchemy URL).
"""
import os
import re
import sqlalchemy
from google.cloud.sql.connector import Connector, IPTypes
import dotenv

dotenv.load_dotenv()

connector = Connector()


def getconn():
    # Public IP優先（Privateにしたければ IPTypes.PRIVATE）
    return connector.connect(
        os.getenv("CONNECTION_NAME"),
        "pg8000",
        user=os.getenv("DB_USER"),
        db=os.getenv("DB_NAME"),
        password=os.getenv("DB_PASS"),
        # IAM DB 認証を使う場合:
        enable_iam_auth=True,
        ip_type=IPTypes.PUBLIC,
    )


def split_sql_statements(sql: str):
    """
    ; で区切るが、'…' や $tag$…$tag$（ドル引用）の内部にある ; は区切らない。
    /* … */ ブロックコメント と -- 行コメント も除去する。
    """
    # 1) ブロックコメント除去
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.S)

    out, buf = [], []
    in_single = False
    dollar_tag = None  # 例: None or 'tag' or ''（$$ のときは空文字）

    i, n = 0, len(sql)
    while i < n:
        ch = sql[i]

        # 行コメント -- ... 改行まで
        if (
            not in_single
            and dollar_tag is None
            and ch == "-"
            and i + 1 < n
            and sql[i + 1] == "-"
        ):
            # 改行までスキップ
            j = sql.find("\n", i)
            if j == -1:
                break
            i = j
            continue

        # ドル引用の開始/終了検出: $tag$
        if not in_single:
            if dollar_tag is None and ch == "$":
                # $[A-Za-z0-9_]*$
                m = re.match(r"\$([A-Za-z0-9_]*)\$", sql[i:])
                if m:
                    dollar_tag = m.group(1)  # '' の可能性あり
                    # タグごと書き込んで進める
                    taglen = len(m.group(0))
                    buf.append(sql[i : i + taglen])
                    i += taglen
                    continue
            elif dollar_tag is not None and ch == "$":
                # 終了タグ $tag$
                tag = dollar_tag
                tag_pat = f"${tag}$"
                if sql.startswith(tag_pat, i):
                    buf.append(tag_pat)
                    i += len(tag_pat)
                    dollar_tag = None
                    continue

        # シングルクォート文字列の開始/終了
        if dollar_tag is None and ch == "'":
            buf.append(ch)
            i += 1
            # トグル（エスケープ '' に注意）
            if in_single:
                in_single = False
            else:
                in_single = True
            # 直後のもう一個 ' があれば文字列中のエスケープなので継続
            if in_single and i < n and sql[i] == "'":
                # 連続 '' をそのまま書き込み
                buf.append("'")
                i += 1
            continue

        # セミコロン：外側にいるときだけステートメント区切り
        if ch == ";" and not in_single and dollar_tag is None:
            stmt = "".join(buf).strip()
            if stmt:
                out.append(stmt)
            buf = []
            i += 1
            continue

        buf.append(ch)
        i += 1

    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return out


def apply_schema(engine, schema_path: str):
    """schema.sql を上から順に実行（; で分割、コメントは無視）"""
    with open(schema_path, "r", encoding="utf-8") as f:
        sql = f.read()

    # ; 区切りでステートメントに分割（単純法。PL/pgSQL などの複雑なスクリプトは別対応が必要）
    statements = split_sql_statements(sql)

    # 実行
    with engine.begin() as conn:  # トランザクションでまとめて実行
        for stmt in statements:
            # ドライバに生SQLを渡す（DDLに強い）
            conn.exec_driver_sql(stmt)


def main():

    engine = sqlalchemy.create_engine(
        "postgresql+pg8000://",  # ユーザー/パスは creator で供給するので空でOK
        creator=getconn,
        pool_pre_ping=True,
    )

    # ここで schema.sql を適用
    apply_schema(engine, "db/schema.sql")


if __name__ == "__main__":
    main()
