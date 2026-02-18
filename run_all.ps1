# 仮想環境が有効であることを前提
# 失敗したら即止まる、安全運用版

Write-Host "=== 1. Notion API ping ==="
python notion_ping.py
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host "=== 2. Ingest Notion -> PostgreSQL ==="
python notion_to_postgres_step1.py
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host "=== 3. Make chunks ==="
python make_chunks_step2.py
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host "=== DONE ==="
