import os, requests

from dotenv import load_dotenv

load_dotenv()

def require_env(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise RuntimeError(f"環境変数 {key} が設定されていません")
    return value

token = require_env("NOTION_TOKEN")


r = requests.get(
    "https://api.notion.com/v1/users/me",
    headers={
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28",
    },
    timeout=30,
)
print("status:", r.status_code)
print(r.text)
