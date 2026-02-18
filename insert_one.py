import os
import psycopg2
import hashlib
from dotenv import load_dotenv
from datetime import datetime

# ---------- utils ----------
def make_plaud_uid(transcript: str) -> str:
    return hashlib.sha256(transcript.encode("utf-8")).hexdigest()[:16]

# ---------- main ----------
load_dotenv()

conn = psycopg2.connect(
    dbname=os.getenv("PG_DB"),
    user=os.getenv("PG_USER"),
    password=os.getenv("PG_PASS"),
    host=os.getenv("PG_HOST"),
    port=int(os.getenv("PG_PORT")),
)

cur = conn.cursor()

title = "02-04 薬に関する問い合わせと病院への直接連絡の提案"
recorded_at = datetime(2026, 2, 4, 15, 36)

transcript = """ここにPLAUDの全文を貼る"""
summary = """ここにPLAUDの要約を貼る"""

# ★ ここで生成
plaud_uid = make_plaud_uid(transcript)

cur.execute("""
INSERT INTO plaud.plaud_logs
(plaud_uid, title, recorded_at, transcript, summary)
VALUES (%s, %s, %s, %s, %s)
ON CONFLICT (plaud_uid) DO NOTHING
RETURNING id;
""", (plaud_uid, title, recorded_at, transcript, summary))

result = cur.fetchone()
conn.commit()

cur.close()
conn.close()

if result:
    print("inserted id:", result[0])
else:
    print("already exists (skipped)")
