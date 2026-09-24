@echo off
setlocal

set "BASE_DIR=%~dp0"
set "PROJECT_ROOT=%BASE_DIR%..\..\"
set "PYTHON=%PROJECT_ROOT%.venv-bipia\Scripts\python.exe"
set "APP=%BASE_DIR%app.py"
set "TRUSTED=%PROJECT_ROOT%data\fruitfly_poisoning\manifests\clean_subset.csv"

title S6 Fruit-fly Data Poisoning Base

if not exist "%PYTHON%" (
    echo [ERROR] Python environment not found: %PYTHON%
    pause
    exit /b 1
)

if not exist "%TRUSTED%" (
    echo [ERROR] Fruit-fly manifests are missing. Prepare and verify the experiment first.
    pause
    exit /b 1
)

echo Starting the Fruit-fly data-poisoning base at http://127.0.0.1:8766
echo Press Ctrl+C to stop the backend.
"%PYTHON%" "%APP%" %*

if errorlevel 1 (
    echo [ERROR] The application stopped unexpectedly.
    pause
)

endlocal
