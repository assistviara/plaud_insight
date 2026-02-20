import os
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

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

CHUNK_SIZE = 1000
CHUNK_STRIDE = 800
MIN_LEN = 50
BATCH = 200

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

# def ensure_chunked_hash_column(cur):
#     cur.execute("""
#         ALTER TABLE plaud.raw_documents
#         ADD COLUMN IF NOT EXISTS chunked_hash text;
#     """)

def main():
    inserted_total = 0
    skipped_short = 0
    rebuilt_docs = 0

    with connect_pg() as conn:
        with conn.cursor() as cur:
            # 1回だけ（無ければ追加）
            # ensure_chunked_hash_column(cur)

            # ✅ chunk未作成 or 内容更新（hash差分）を対象にする
            cur.execute("""
                SELECT rd.id, rd.raw_text, rd.content_hash, rd.chunked_hash
                FROM plaud.raw_documents rd
                WHERE rd.raw_text IS NOT NULL
                AND rd.content_hash IS NOT NULL
                AND length(rd.raw_text) >= %s
                AND (rd.chunked_hash IS NULL OR rd.chunked_hash <> rd.content_hash)
                ORDER BY rd.id;
            """, (MIN_LEN,))
            rows = cur.fetchall()

            if not rows:
                print("No raw_documents to (re)chunk. (already up to date)")
                return

            for raw_document_id, raw_text, content_hash, chunked_hash in rows:
                if raw_text is None or len(raw_text) < MIN_LEN:
                    skipped_short += 1
                    continue

                # ✅ 既にchunked_hashがある＝作り直し対象なので、古いchunkを削除
                if chunked_hash is not None:
                    cur.execute("DELETE FROM plaud.chunks WHERE raw_document_id = %s;", (raw_document_id,))
                    rebuilt_docs += 1

                to_insert = []
                for chunk_index, start_char, end_char, chunk_text in iter_chunks(raw_text, CHUNK_SIZE, CHUNK_STRIDE):
                    to_insert.append((raw_document_id, chunk_index, start_char, end_char, chunk_text))

                    if len(to_insert) >= BATCH:
                        inserted_total += bulk_insert(cur, to_insert)
                        to_insert = []

                if to_insert:
                    inserted_total += bulk_insert(cur, to_insert)

                # ✅ chunk完了の印としてchunked_hashを更新
                cur.execute(
                    "UPDATE plaud.raw_documents SET chunked_hash = %s WHERE id = %s;",
                    (content_hash, raw_document_id)
                )

        conn.commit()

    print(
        f"Inserted chunks: {inserted_total} "
        f"(rebuilt_docs: {rebuilt_docs}, skipped_short_docs: {skipped_short})"
    )

if __name__ == "__main__":
    main()