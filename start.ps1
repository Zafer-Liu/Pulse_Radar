$OutputEncoding = [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Set-Location $PSScriptRoot

Write-Host "========================================"
Write-Host "  Shenglang Radar - Build + Start"
Write-Host "========================================"
Write-Host ""

# Build frontend only if dist is missing
if (-not (Test-Path "frontend\dist\index.html")) {
    if (Test-Path "frontend\package.json") {
        Write-Host "Building Vue frontend..."
        Push-Location frontend
        npm run build
        if (-not $?) { Write-Host "[WARN] Frontend build failed, using existing dist if any." }
        Pop-Location
        Write-Host ""
    }
} else {
    Write-Host "Frontend dist found, skip build."
    Write-Host ""
}

Write-Host "Starting backend server..."
Write-Host "Open: http://127.0.0.1:8088"
Write-Host ""

# Use project venv (with jieba) if available, else system python
if (Test-Path ".venv\Scripts\python.exe") {
    Write-Host "Using project venv (.venv)."
    & ".venv\Scripts\python.exe" -m pip install -r requirements.txt --quiet --disable-pip-version-check
    & ".venv\Scripts\python.exe" server.py
} else {
    Write-Host "[INFO] .venv not found, using system python."
    Write-Host "[INFO] server.py will auto pip install missing deps from requirements.txt."
    Write-Host ""
    python -m pip install -r requirements.txt --quiet --disable-pip-version-check
    python server.py
}

Read-Host "Press Enter to exit"
