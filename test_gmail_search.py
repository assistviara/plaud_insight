import os
from dotenv import load_dotenv

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

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

import os
import base64
from dotenv import load_dotenv

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

def search_message_ids(service, query: str, max_results: int = 5):
    res = service.users().messages().list(
        userId="me", q=query, maxResults=max_results
    ).execute()
    return [m["id"] for m in res.get("messages", [])]

def list_attachments(service, msg_id: str):
    msg = service.users().messages().get(userId="me", id=msg_id, format="full").execute()
    payload = msg.get("payload", {})
    parts = payload.get("parts", []) or []

    found = []
    # Gmailは多層partsになるので再帰で掘る
    def walk(parts_):
        for p in parts_:
            filename = p.get("filename")
            body = p.get("body", {})
            if filename and body.get("attachmentId"):
                found.append({
                    "filename": filename,
                    "mimeType": p.get("mimeType"),
                    "attachmentId": body.get("attachmentId"),
                    "size": body.get("size"),
                })
            # ネストがあればさらに掘る
            if p.get("parts"):
                walk(p["parts"])

    walk(parts)
    return found

def download_attachment(service, msg_id: str, attachment_id: str, save_path: str):
    att = service.users().messages().attachments().get(
        userId="me", messageId=msg_id, id=attachment_id
    ).execute()
    data = att.get("data", "")
    raw = base64.urlsafe_b64decode(data.encode("utf-8"))
    with open(save_path, "wb") as f:
        f.write(raw)

def main():
    load_dotenv()
    service = get_gmail_service()

    query = os.getenv("GMAIL_QUERY", 'from:no-reply@plaud.ai subject:"Plaud-AutoFlow" newer_than:30d')
    msg_ids = search_message_ids(service, query, max_results=3)
    print(f"hit={len(msg_ids)} query={query}")

    if not msg_ids:
        return

    target_id = msg_ids[0]
    atts = list_attachments(service, target_id)

    print(f"\nmessageId={target_id}")
    print(f"attachments={len(atts)}")
    for i, a in enumerate(atts, 1):
        print(f"{i}. {a['filename']} ({a['mimeType']}, size={a['size']})")

    # 添付を保存（downloads/ 配下）
    os.makedirs("downloads", exist_ok=True)
    for a in atts:
        out = os.path.join("downloads", a["filename"])
        download_attachment(service, target_id, a["attachmentId"], out)
        print(f"saved: {out}")

if __name__ == "__main__":
    main()