import os
import hashlib
import requests
import psycopg2
from dotenv import load_dotenv

# どこから実行しても .env を見つけられるようにする（VSCodeでcwdがズレても安全）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

def require_env(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise RuntimeError(f"環境変数 {key} が設定されていません（.env を確認）")
    return value

# ===== Notion =====
NOTION_TOKEN = require_env("NOTION_TOKEN")
NOTION_DATABASE_ID = require_env("NOTION_DATABASE_ID")

# ===== Postgres =====
PG_DB = require_env("PG_DB")
PG_USER = require_env("PG_USER")
PG_PASS = require_env("PG_PASS")
PG_HOST = os.getenv("PG_HOST", "localhost")   # ここだけはデフォルトOK
PG_PORT = int(os.getenv("PG_PORT", "5433"))

NOTION_VERSION = "2022-06-28"
MIN_LEN = 50          # 短すぎるものはスキップ（必要なら調整）
FETCH_LIMIT = 10      # まずは10件

def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def notion_query_database(limit: int = 10):
    url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }
    payload = {
        "page_size": limit,
        "sorts": [
            {"timestamp": "created_time", "direction": "descending"}
        ]
    }
    r = requests.post(url, headers=headers, json=payload, timeout=30)
    r.raise_for_status()
    return r.json()["results"]

def extract_title(props: dict) -> str:
    t = props.get("Title", {}).get("title", [])
    if not t:
        return ""
    return "".join([x.get("plain_text", "") for x in t]).strip()

def extract_rich_text(props: dict, key: str) -> str:
    arr = props.get(key, {}).get("rich_text", [])
    if not arr:
        return ""
    return "".join([x.get("plain_text", "") for x in arr]).strip()

def connect_pg():
    return psycopg2.connect(
        dbname=PG_DB,
        user=PG_USER,
        password=PG_PASS,
        host=PG_HOST,
        port=PG_PORT,
        options="-c client_encoding=UTF8",
    )

def upsert_raw_document(cur, raw_text: str):
    """
    raw_documents: content_hash で一意化し、必ず id を返す。
    """
    content_hash = sha256_text(raw_text)
    sql = """
    INSERT INTO plaud.raw_documents (raw_text, content_hash, ingested_at)
    VALUES (%s, %s, now())
    ON CONFLICT (content_hash) DO UPDATE
    SET ingested_at = EXCLUDED.ingested_at
    RETURNING id;
    """
    cur.execute(sql, (raw_text, content_hash))
    return cur.fetchone()[0], content_hash

def insert_raw_source(cur, raw_document_id: int, notion_page_id: str, notion_created_time: str, title: str):
    sql = """
    INSERT INTO plaud.raw_sources (raw_document_id, notion_page_id, notion_created_time, title)
    VALUES (%s, %s, %s, %s)
    ON CONFLICT (notion_page_id) DO NOTHING;
    """
    cur.execute(sql, (raw_document_id, notion_page_id, notion_created_time, title))

def main():
    pages = notion_query_database(FETCH_LIMIT)

    prepared = 0
    skipped_short = 0

    with connect_pg() as conn:
        with conn.cursor() as cur:
            for p in pages:
                page_id = p["id"]
                created_time = p.get("created_time")
                props = p.get("properties", {})

                title = extract_title(props)
                raw_text = extract_rich_text(props, "content")  # あなたのDBは content が rich_text

                if len(raw_text) < MIN_LEN:
                    skipped_short += 1
                    continue

                raw_document_id, _ = upsert_raw_document(cur, raw_text)
                insert_raw_source(cur, raw_document_id, page_id, created_time, title)

                prepared += 1

    print(f"Inserted/linked: {prepared} (skipped_short: {skipped_short})")

if __name__ == "__main__":
    main()
