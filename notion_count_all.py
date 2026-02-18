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
NOTION_DATABASE_ID = require_env("NOTION_DATABASE_ID")

headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query"

count = 0
has_more = True
start_cursor = None

while has_more:
    payload = {"page_size": 100}
    if start_cursor:
        payload["start_cursor"] = start_cursor

    r = requests.post(url, headers=headers, json=payload, timeout=30)
    r.raise_for_status()
    data = r.json()

    batch = len(data.get("results", []))
    count += batch

    has_more = data.get("has_more", False)
    start_cursor = data.get("next_cursor")

print("TOTAL_PAGES_IN_DB:", count)
