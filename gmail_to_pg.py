import os
import re
import json
import base64
import hashlib
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import DictCursor, Json

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# --------------------
# Gmail auth
# --------------------
def get_gmail_service():
    load_dotenv()
    token_path = os.getenv("GMAIL_TOKEN_JSON", "token.json")
    cred_path = os.getenv("GMAIL_CREDENTIALS_JSON", "credentials.json")

    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(cred_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w", encoding="utf-8") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)

# --------------------
# PostgreSQL
# --------------------
def get_pg_conn():
    load_dotenv()
    return psycopg2.connect(
        dbname=os.getenv("PG_DB"),
        user=os.getenv("PG_USER"),
        password=os.getenv("PG_PASS"),
        host=os.getenv("PG_HOST"),
        port=os.getenv("PG_PORT"),
        cursor_factory=DictCursor,
    )

# --------------------
# Helpers
# --------------------
def header_value(headers, name):
    target = name.lower()
    for h in headers:
        if (h.get("name") or "").lower() == target:
            return h.get("value")
    return None

def parse_date_to_utc(date_str: str):
    if not date_str:
        return None
    dt = parsedate_to_datetime(date_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def sha256_text(s: str) -> str:
    return hashlib.sha256((s or "").encode("utf-8")).hexdigest()

def b64url_decode(data: str) -> bytes:
    # Gmail は base64url ( - と _ ) を返す
    if not data:
        return b""
    return base64.urlsafe_b64decode(data.encode("utf-8"))

def html_to_text(html: str) -> str:
    # style/script は中身ごと消す（ここが重要）
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.IGNORECASE | re.DOTALL)

    # 改行っぽいものだけ整形
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    html = re.sub(r"</p\s*>", "\n\n", html, flags=re.IGNORECASE)
    html = re.sub(r"</div\s*>", "\n", html, flags=re.IGNORECASE)

    # 残りタグ除去
    html = re.sub(r"<[^>]+>", "", html)

    # 余分な空行を軽く整理
    text = html.strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text

def walk_parts(part):
    # payload の parts を再帰で全部集める
    parts = []
    if not part:
        return parts
    parts.append(part)
    for p in part.get("parts", []) or []:
        parts.extend(walk_parts(p))
    return parts

def extract_body_text(payload) -> str:
    """
    text/plain を最優先。なければ text/html をテキスト化して使う。
    """
    all_parts = walk_parts(payload)

    plain_chunks = []
    html_chunks = []

    for p in all_parts:
        mime = (p.get("mimeType") or "").lower()
        body = p.get("body", {}) or {}
        data = body.get("data")

        if mime == "text/plain" and data:
            plain_chunks.append(b64url_decode(data).decode("utf-8", errors="replace"))
        elif mime == "text/html" and data:
            html = b64url_decode(data).decode("utf-8", errors="replace")
            html_chunks.append(html_to_text(html))

    if plain_chunks:
        return "\n\n".join([c.strip() for c in plain_chunks if c.strip()]).strip()
    if html_chunks:
        return "\n\n".join([c.strip() for c in html_chunks if c.strip()]).strip()
    return ""

def fetch_txt_attachments(gmail, msg_id: str, payload):
    """
    .txt 添付を取り出して返す:
    - attachments: [{"filename":..., "mimeType":..., "text":...}, ...]
    - summary_text: 要約.txt があればそこだけ別取り
    """
    attachments = []
    summary_text = ""

    all_parts = walk_parts(payload)
    for p in all_parts:
        filename = (p.get("filename") or "").strip()
        if not filename:
            continue

        mime = (p.get("mimeType") or "").lower()
        body = p.get("body", {}) or {}
        att_id = body.get("attachmentId")

        # 今回は .txt だけ対象（必要なら later で pdf/docx も）
        if not filename.lower().endswith(".txt"):
            continue
        if not att_id:
            continue

        att = gmail.users().messages().attachments().get(
            userId="me",
            messageId=msg_id,
            id=att_id,
        ).execute()

        data = att.get("data")
        text = b64url_decode(data).decode("utf-8", errors="replace").strip()

        attachments.append({
            "filename": filename,
            "mimeType": mime,
            "text_len": len(text),
        })

        # 要約.txt は summary_text に格納、それ以外は raw_text に混ぜる
        if "要約" in filename:
            summary_text = text

        else:
            # 「文字起こし.txt」等はこちらへ
            attachments[-1]["text"] = text  # 後で結合用に保持

    return attachments, summary_text

# --------------------
# Main
# --------------------
def main():
    load_dotenv()
    query = os.getenv("GMAIL_QUERY", 'from:no-reply@plaud.ai subject:"Plaud-AutoFlow" newer_than:30d')

    gmail = get_gmail_service()
    pg = get_pg_conn()
    cur = pg.cursor()

    res = gmail.users().messages().list(userId="me", q=query, maxResults=50).execute()
    msgs = res.get("messages", [])
    print(f"hit={len(msgs)} query={query}")

    for m in msgs:
        msg_id = m["id"]

        # ★ここがポイント：full で取る
        full = gmail.users().messages().get(
            userId="me",
            id=msg_id,
            format="full",
        ).execute()

        payload = full.get("payload", {}) or {}
        headers = payload.get("headers", []) or []

        subject = header_value(headers, "Subject") or ""
        from_ = header_value(headers, "From") or ""
        to_ = header_value(headers, "To") or ""
        date_ = header_value(headers, "Date") or ""
        recorded_at = parse_date_to_utc(date_)

        body_text = extract_body_text(payload)

        attachments_meta, summary_text = fetch_txt_attachments(gmail, msg_id, payload)

        # 添付本文（要約以外）を raw_text に混ぜる
        attachment_texts = []
        for a in attachments_meta:
            t = a.pop("text", None)  # metaからは外す
            if t:
                attachment_texts.append(f"--- attachment: {a['filename']} ---\n{t}")

        combined_raw = "\n\n".join([x for x in [body_text, *attachment_texts] if x]).strip()

        ingested_at = datetime.now(timezone.utc)
        gmail_received_at = recorded_at
        content_hash = sha256_text(combined_raw)

        meta = {
            "from": from_,
            "to": to_,
            "threadId": full.get("threadId"),
            "attachments": attachments_meta,
        }

        # ★既存行を育てる：DO UPDATE にする

        # 念のため（raw_text が NOT NULL 対策）
        combined_raw = combined_raw or ""

        cur.execute(
            """
            INSERT INTO plaud.raw_documents
            (source_type, source_id, recorded_at, gmail_received_at, title, raw_text,
            summary_text, content_hash, ingested_at, meta_json)
            VALUES
            (%s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s)
            ON CONFLICT (source_type, source_id)
            DO UPDATE SET
            recorded_at       = EXCLUDED.recorded_at,
            gmail_received_at = EXCLUDED.gmail_received_at,
            title             = EXCLUDED.title,
            raw_text          = EXCLUDED.raw_text,
            summary_text      = EXCLUDED.summary_text,
            content_hash      = EXCLUDED.content_hash,
            ingested_at       = EXCLUDED.ingested_at,
            meta_json         = EXCLUDED.meta_json
            """,
            (
                "gmail",
                msg_id,
                recorded_at,
                gmail_received_at,
                subject,
                combined_raw,
                summary_text,
                content_hash,
                ingested_at,
                Json(meta),
            ),
        )

        print("upserted:", msg_id, subject)

    pg.commit()
    cur.close()
    pg.close()

if __name__ == "__main__":
    main()