@echo off
setlocal

set "BASE_DIR=%~dp0"
set "PROJECT_ROOT=%BASE_DIR%..\..\"
set "PYTHON=%PROJECT_ROOT%.venv-bipia\Scripts\python.exe"
set "APP=%BASE_DIR%app.py"

title S6 Email Prompt Injection Base

if not exist "%PYTHON%" (
    echo [ERROR] Python environment not found: %PYTHON%
    pause
    exit /b 1
)

echo Starting the email prompt-injection base at http://127.0.0.1:8765
echo Press Ctrl+C to stop the backend.
"%PYTHON%" "%APP%" %*

if errorlevel 1 (
    echo [ERROR] The application stopped unexpectedly.
    pause
)

endlocal
