import os
import requests
from dotenv import load_dotenv

# どこから実行しても .env を読む（VSCode事故防止）
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
}

url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}"

r = requests.get(url, headers=headers, timeout=20)

print("status:", r.status_code)

if r.status_code != 200:
    print("ERROR RESPONSE:")
    print(r.text[:1000])
else:
    data = r.json()
    print("DB name:", data.get("title", [{}])[0].get("plain_text"))
    print("Properties:")
    for name, meta in data.get("properties", {}).items():
        print(f"- {name} ({meta.get('type')})")
