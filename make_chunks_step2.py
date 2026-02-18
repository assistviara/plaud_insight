import os
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

# どこから実行しても .env を拾えるようにする（VSCode事故防止）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

def require_env(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise RuntimeError(f"環境変数 {key} が設定されていません（.env を確認）")
    return value

PG_DB = require_env("PG_DB")
PG_USER = require_env("PG_USER")
PG_PASS = require_env("PG_PASS")
PG_HOST = os.getenv("PG_HOST", "localhost")
PG_PORT = int(os.getenv("PG_PORT", "5433"))

CHUNK_SIZE = 1000     # 固定長チャンク
CHUNK_STRIDE = 800    # 200文字オーバーラップ（1000-800）
MIN_LEN = 50          # 短すぎるraw_textはスキップ（念のため）
BATCH = 200           # insertバッチ

def connect_pg():
    return psycopg2.connect(
        dbname=PG_DB,
        user=PG_USER,
        password=PG_PASS,
        host=PG_HOST,
        port=PG_PORT,
        options="-c client_encoding=UTF8",
    )

def iter_chunks(text: str, size: int, stride: int):
    n = len(text)
    idx = 0
    start = 0
    while start < n:
        end = min(start + size, n)
        yield idx, start, end, text[start:end]
        idx += 1
        if end == n:
            break
        start += stride

def bulk_insert(cur, to_insert):
    sql = """
        INSERT INTO plaud.chunks
            (raw_document_id, chunk_index, start_char, end_char, text)
        VALUES %s
        ON CONFLICT (raw_document_id, chunk_index) DO NOTHING;
    """
    execute_values(cur, sql, to_insert)
    return len(to_insert)

def main():
    inserted_total = 0
    skipped_short = 0

    with connect_pg() as conn:
        with conn.cursor() as cur:
            # chunks未生成のraw_documentsだけ対象にする（強い）
            cur.execute("""
                SELECT rd.id, rd.raw_text
                FROM plaud.raw_documents rd
                LEFT JOIN plaud.chunks c ON c.raw_document_id = rd.id
                WHERE c.raw_document_id IS NULL
                ORDER BY rd.id;
            """)
            rows = cur.fetchall()

            if not rows:
                print("No new raw_documents to chunk. (already done)")
                return

            for raw_document_id, raw_text in rows:
                if raw_text is None or len(raw_text) < MIN_LEN:
                    skipped_short += 1
                    continue

                to_insert = []
                for chunk_index, start_char, end_char, chunk_text in iter_chunks(raw_text, CHUNK_SIZE, CHUNK_STRIDE):
                    to_insert.append((
                        raw_document_id,
                        chunk_index,
                        start_char,
                        end_char,
                        chunk_text,
                    ))

                    if len(to_insert) >= BATCH:
                        inserted_total += bulk_insert(cur, to_insert)
                        to_insert = []

                if to_insert:
                    inserted_total += bulk_insert(cur, to_insert)

        conn.commit()

    print(f"Inserted chunks: {inserted_total} (skipped_short_docs: {skipped_short})")

if __name__ == "__main__":
    main()
