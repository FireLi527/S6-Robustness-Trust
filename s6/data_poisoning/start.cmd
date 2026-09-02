@echo off
setlocal

set "BASE_DIR=%~dp0"
set "PROJECT_ROOT=%BASE_DIR%..\..\"
set "PYTHON=%PROJECT_ROOT%.venv-bipia\Scripts\python.exe"
set "PREPARE=%BASE_DIR%prepare_ip102_poisoning.py"
set "APP=%BASE_DIR%app.py"
set "TRUSTED=%PROJECT_ROOT%data\ip102_poisoning\manifests\clean_subset.csv"

title S6 IP102 Data Poisoning Base

if not exist "%PYTHON%" (
    echo [ERROR] Python environment not found: %PYTHON%
    pause
    exit /b 1
)

if not exist "%TRUSTED%" (
    echo Preparing IP102 experiment manifests for the first run...
    "%PYTHON%" "%PREPARE%"
    if errorlevel 1 (
        echo [ERROR] Manifest preparation failed.
        pause
        exit /b 1
    )
)

echo Starting the IP102 data-poisoning base at http://127.0.0.1:8766
echo Press Ctrl+C to stop the backend.
"%PYTHON%" "%APP%" %*

if errorlevel 1 (
    echo [ERROR] The application stopped unexpectedly.
    pause
)

endlocal
