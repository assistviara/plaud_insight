````markdown
# PLAUD → Notion → PostgreSQL（plaudスキーマ）取り込み＆チャンク化パイプライン README

## 目的
PLAUDの録音生成物が Zapier 経由で Notion DB（`PLAUD_DATA`）へ蓄積される前提で、以下を実現するための最小かつ堅牢な構成である。

- Notionの「生テキスト（content）」を PostgreSQL に取り込む
- 同一の生テキストは **重複保存しない**（`content_hash` による一意化）
- Notion側で「要約を変えると別ページになる」場合でも、**履歴としてページIDを保持**する
- 生テキストを固定長で分割し、後工程（検索・クラスタ・埋め込み等）の入力単位を作る

---

## TL;DR（最短ルート）

初回セットアップ後は、以下だけ覚えればよい。

```powershell
python notion_ping.py
python notion_to_postgres_step1.py
python make_chunks_step2.py
````

---

## 全体像（データフロー）

1. **Notion DB（PLAUD_DATA）** にページが追加される（Zapierトリガー）
2. `notion_to_postgres_step1.py` が Notion API からページを取得し、

   * `plaud.raw_documents` に生テキストを保存（hashで一意化）
   * `plaud.raw_sources` に NotionページIDを保存（履歴）
3. `make_chunks_step2.py` が未チャンク化文書を対象に固定長分割し、`plaud.chunks` に格納する

---

## 前提環境

* OS: Windows（PowerShell / VSCode）
* Python: venv 使用（`.venv`）
* PostgreSQL: ローカル稼働（例：ポート `5433`）
* Notion: インテグレーション（Bot）作成済み、DBに共有済み
* Notion DB: `PLAUD_DATA`

  * `Title`（title）
  * `content`（rich_text）

---

## ディレクトリ構成（例）

`C:\Users\knigh\Documents\plaud_ingest\`

```text
plaud_ingest/
├─ .env
├─ make_chunks_step2.py
├─ notion_check_db.py
├─ notion_count_all.py
├─ notion_fetch_10.py
├─ notion_find_db.py
├─ notion_list_props.py
├─ notion_ping.py
├─ notion_to_postgres_step1.py
├─ .venv/
```

---

## セットアップ

### 1. venv 有効化

```powershell
cd C:\Users\knigh\Documents\plaud_ingest
.\.venv\Scripts\activate
```

### 2. 必要パッケージ

```powershell
pip install requests python-dotenv psycopg2-binary
```

---

## `.env` の作成（入力ミス根絶）

プロジェクト直下に `.env` を作成する。

> ⚠️ `.env` は **Gitにコミットしない**
> `.gitignore` に `.env` を必ず追加すること。

### `.env` テンプレ

```ini
# ===== Notion =====
NOTION_TOKEN=ntn_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
NOTION_DATABASE_ID=2f4ef00e-d1f1-8071-b025-c24ab739cf02

# ===== Postgres =====
PG_DB=bizforecast
PG_USER=plaud_app
PG_PASS=plaud_pass_2026
PG_HOST=localhost
PG_PORT=5433
```

---

## PostgreSQL 側の構造（概要）

### plaud.raw_documents

* 生テキスト本体
* `content_hash` で一意化（重複防止）

### plaud.raw_sources

* Notionページ履歴
* `notion_page_id` を UNIQUE として保存

### plaud.chunks

* 固定長チャンク（size=1000 / stride=800）
* 検索・類似・埋め込みの基本単位

---

## 実行手順（推奨順）

### Step A. Notion API 疎通確認

#### notion_ping.py

```powershell
python notion_ping.py
```

* `status: 200` → OK
* `401` → トークン誤り
* `403` → DB共有・権限の問題

---

### Step B. DB確認

#### notion_find_db.py

```powershell
python notion_find_db.py
```

#### notion_check_db.py

```powershell
python notion_check_db.py
```

---

### Step C. プロパティ確認

#### notion_list_props.py

```powershell
python notion_list_props.py
```

---

### Step D. 取得テスト

#### notion_fetch_10.py

```powershell
python notion_fetch_10.py
```

#### notion_count_all.py

```powershell
python notion_count_all.py
```

---

### Step E. PostgreSQL 取り込み

#### notion_to_postgres_step1.py

```powershell
python notion_to_postgres_step1.py
```

出力例：

```
Inserted/linked: 5 (skipped_short: 5)
```

---

### Step F. チャンク化

#### make_chunks_step2.py

```powershell
python make_chunks_step2.py
```

出力例：

```
Inserted chunks: 58 (skipped_short_docs: 0)
```

---

## 各スクリプトの役割一覧

| ファイル                        | 役割                     |
| --------------------------- | ---------------------- |
| notion_ping.py              | Notionトークン疎通確認         |
| notion_find_db.py           | DB検索・DB_ID確認           |
| notion_check_db.py          | DB取得可否確認               |
| notion_list_props.py        | プロパティ一覧                |
| notion_fetch_10.py          | 取得テスト                  |
| notion_count_all.py         | 全件数カウント                |
| notion_to_postgres_step1.py | Notion → Postgres 取り込み |
| make_chunks_step2.py        | チャンク生成                 |

---

## よくあるエラー

### 401 Unauthorized

* トークン誤り・途中欠損

### Provided ID is a page

* DB_ID ではなくページIDを指定している

### Postgres connection refused

* ポート・起動状態・認証情報を確認

---

## 現時点でできること

* PLAUDログの永続保存
* 生テキストの重複排除
* Notionページ履歴の保持
* 分析前段としてのチャンク化完了

---

## 次フェーズ候補

* チャンクの埋め込みベクトル化
* 類似検索・話題クラスタリング
* 時系列でのテーマ変化分析
* 自分自身の思考ログ分析

---

## 運用ルール（最小）

* データ追加後：`notion_to_postgres_step1.py`
* 新規raw_documents後：`make_chunks_step2.py`
* 異常時：`notion_ping.py` から確認

以上。

```

---

