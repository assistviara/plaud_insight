import os
import requests
from dotenv import load_dotenv

# 実行場所に依存しない .env 読み込み
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

def require_env(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise RuntimeError(f"環境変数 {key} が設定されていません（.env を確認）")
    return value

NOTION_TOKEN = require_env("NOTION_TOKEN")
NOTION_VERSION = "2022-06-28"

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": NOTION_VERSION,
}

QUERY = "PLAUD_DATA"  # 探したいDB名（必要ならここだけ変える）

payload = {
    "query": QUERY,
    "filter": {"property": "object", "value": "database"},
    "page_size": 10
}

r = requests.post(
    "https://api.notion.com/v1/search",
    headers=HEADERS,
    json=payload,      # ← ここが安全（data=json.dumps より事故らない）
    timeout=30
)

print("status:", r.status_code)

if r.status_code != 200:
    print("ERROR RESPONSE:")
    print(r.text[:1000])
    raise SystemExit(1)

data = r.json()
results = data.get("results", [])
print("found:", len(results))

for db in results:
    title = "".join(t.get("plain_text", "") for t in db.get("title", []))
    print("-" * 60)
    print("title:", title)
    print("db_id:", db.get("id"))
