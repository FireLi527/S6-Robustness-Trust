@echo off
setlocal
cd /d "%~dp0"
set "PYTHON=%~dp0.venv-bipia\Scripts\python.exe"
if not exist "%PYTHON%" (
    echo [ERROR] Python environment missing: %PYTHON%
    pause
    exit /b 1
)
"%PYTHON%" "%~dp0frontend.py" %*
if errorlevel 1 pause
endlocal
