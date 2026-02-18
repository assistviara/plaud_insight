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
NOTION_VERSION = "2022-06-28"

headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": NOTION_VERSION,
    "Content-Type": "application/json",
}

def rich_text_to_plain(rt_list):
    return "".join(x.get("plain_text", "") for x in (rt_list or []))

def get_title(properties, title_prop_name="Title"):
    prop = properties.get(title_prop_name)
    if not prop:
        return ""  # タイトル列が無い
    if prop.get("type") == "title":
        return rich_text_to_plain(prop.get("title"))
    return ""

def get_rich_text(properties, prop_name):
    """rich_text型のプロパティをplain_textとして取り出す"""
    prop = properties.get(prop_name)
    if not prop:
        return ""  # 列が無い
    if prop.get("type") == "rich_text":
        return rich_text_to_plain(prop.get("rich_text"))
    return ""

def fetch_pages(page_size=10):
    url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query"
    payload = {"page_size": page_size}
    res = requests.post(url, headers=headers, json=payload, timeout=30)
    res.raise_for_status()
    return res.json().get("results", [])

if __name__ == "__main__":
    pages = fetch_pages(page_size=10)
    print(f"Fetched: {len(pages)} pages")

    for p in pages:
        page_id = p.get("id")
        created_time = p.get("created_time")
        props = p.get("properties", {})

        title = get_title(props, "Title")
        content = get_rich_text(props, "content")
        summary = get_rich_text(props, "summary")  # あなたのDBにあるので追加（任意）

        print("-" * 40)
        print("page_id:", page_id)
        print("created_time:", created_time)
        print("title:", title[:60])
        print("content_len:", len(content))
        if len(content) == 0:
            # ここが0だと「プロパティ名違い」か「まだcontentが空」の切り分けが必要
            print("NOTE: contentが空です（Notionのcontent列が空 or プロパティ名違い）")
        print("summary_len:", len(summary))
