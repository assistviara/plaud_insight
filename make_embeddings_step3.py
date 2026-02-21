import os
import json
import math
from datetime import datetime, timezone

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

from sentence_transformers import SentenceTransformer


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

def require_env(key: str) -> str:
    v = os.getenv(key)
    if not v:
        raise RuntimeError(f"環境変数 {key} が設定されていません（.env を確認）")
    return v

PG_DB = require_env("PG_DB")
PG_USER = require_env("PG_USER")
PG_PASS = require_env("PG_PASS")
PG_HOST = os.getenv("PG_HOST", "localhost")
PG_PORT = int(os.getenv("PG_PORT", "5433"))

# ===== 設定（まずはこれで十分）=====
MODEL_NAME = os.getenv("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
BATCH = int(os.getenv("EMBED_BATCH", "64"))       # CPUなら 32〜128 あたり
MAX_CHUNKS = int(os.getenv("EMBED_MAX", "0"))     # 0なら制限なし（テスト時は100など）

def connect_pg():
    return psycopg2.connect(
        dbname=PG_DB,
        user=PG_USER,
        password=PG_PASS,
        host=PG_HOST,
        port=PG_PORT,
        options="-c client_encoding=UTF8",
    )

def create_run(cur, model_name: str, dim: int, params: dict) -> int:
    cur.execute(
        """
        INSERT INTO plaud.embedding_runs (model_name, dim, params_json)
        VALUES (%s, %s, %s::jsonb)
        RETURNING id;
        """,
        (model_name, dim, json.dumps(params)),
    )
    return cur.fetchone()[0]

def fetch_target_chunks(cur, run_id: int):
    # まだembeddingが無いchunkだけを対象にする
    cur.execute(
        """
        SELECT c.id, c.text
        FROM plaud.chunks c
        LEFT JOIN plaud.chunk_embeddings e
          ON e.chunk_id = c.id AND e.run_id = %s
        WHERE e.chunk_id IS NULL
        ORDER BY c.id;
        """,
        (run_id,)
    )
    return cur.fetchall()

def insert_embeddings(cur, run_id: int, rows):
    sql = """
        INSERT INTO plaud.chunk_embeddings (run_id, chunk_id, embedding)
        VALUES %s
        ON CONFLICT (run_id, chunk_id) DO NOTHING;
    """
    execute_values(cur, sql, rows, page_size=500)

def main():
    # CPUでOK。device指定なしで大丈夫（勝手にcpu）
    model = SentenceTransformer(MODEL_NAME)
    dim = model.get_sentence_embedding_dimension()

    params = {
        "normalize_embeddings": True,   # 距離が扱いやすくなるので最初はTrue推奨
        "batch_size": BATCH,
    }

    with connect_pg() as conn:
        with conn.cursor() as cur:
            run_id = create_run(cur, MODEL_NAME, dim, params)

            targets = fetch_target_chunks(cur, run_id)
            if MAX_CHUNKS > 0:
                targets = targets[:MAX_CHUNKS]

            total = len(targets)
            if total == 0:
                print("No chunks to embed.")
                conn.commit()
                return

            print(f"run_id={run_id} model={MODEL_NAME} dim={dim} targets={total}")

            # バッチで回す
            inserted = 0
            for i in range(0, total, BATCH):
                batch = targets[i:i+BATCH]
                chunk_ids = [r[0] for r in batch]
                texts = [r[1] or "" for r in batch]

                vecs = model.encode(
                    texts,
                    batch_size=BATCH,
                    show_progress_bar=False,
                    normalize_embeddings=params["normalize_embeddings"],
                )

                rows = []
                for chunk_id, v in zip(chunk_ids, vecs):
                    # numpy array -> python list（psycopg2がreal[]として入れてくれる）
                    rows.append((run_id, chunk_id, list(map(float, v))))

                insert_embeddings(cur, run_id, rows)
                inserted += len(rows)
                print(f"embedded {min(i+BATCH, total)}/{total}")

        conn.commit()

    print(f"DONE. inserted={inserted} run_id={run_id}")

if __name__ == "__main__":
    main()