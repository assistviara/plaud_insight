import os
import requests
from dotenv import load_dotenv

# このファイルの場所を基準に .env を読む
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

def require_env(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise RuntimeError(f"環境変数 {key} が設定されていません（.env を確認）")
    return value

NOTION_TOKEN = require_env("NOTION_TOKEN")
NOTION_DATABASE_ID = require_env("NOTION_DATABASE_ID")

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
}

url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}"
r = requests.get(url, headers=HEADERS, timeout=20)
r.raise_for_status()

db = r.json()
props = db.get("properties", {})

print("=== PROPERTY NAMES (columns) ===")
for name, meta in props.items():
    print(f"- {name}  | type={meta.get('type')}")
