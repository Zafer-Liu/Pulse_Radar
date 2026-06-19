@echo off
setlocal
cd /d "%~dp0"

echo ========================================
echo   Shenglang Radar - Build + Start
echo ========================================
echo.

rem Always rebuild frontend to pick up latest source changes
if exist "frontend\package.json" (
    echo Building Vue frontend...
    pushd frontend
    call npm run build
    if errorlevel 1 (
        echo [WARN] Frontend build failed, using existing dist if any.
    )
    popd
    echo.
)

echo Starting backend server...
echo Open: http://127.0.0.1:8088
echo.

rem Use project venv (with jieba) if available, else system python
if exist ".venv\Scripts\python.exe" (
    echo Using project venv (.venv^).
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt --quiet --disable-pip-version-check
    ".venv\Scripts\python.exe" server.py
) else (
    echo [INFO] .venv not found, using system python.
    echo [INFO] server.py will auto pip install missing deps from requirements.txt.
    echo.
    python -m pip install -r requirements.txt --quiet --disable-pip-version-check
    python server.py
)

echo.
pause
