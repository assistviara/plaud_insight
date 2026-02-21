# run_all.ps1
# 仮想環境が有効であることを前提
# 失敗したら即止まる、安全運用版

$ErrorActionPreference = "Stop"

Write-Host "=== 0. Python check ==="
python --version
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host "=== 1. Ingest Gmail -> PostgreSQL ==="
python gmail_to_pg.py
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host "=== 2. Make chunks ==="
python make_chunks_step2.py
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host "=== DONE ==="