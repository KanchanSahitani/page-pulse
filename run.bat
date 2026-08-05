@echo off
title Page Pulse Launcher
echo Starting Page Pulse...

:: Check if virtual environment exists and activate it
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
) else if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
)

:: Launch browser after a 2-second delay to let the server start
start /b cmd /c "timeout /t 2 >nul && start http://localhost:8000"

:: Start the FastAPI server
python -m uvicorn backend.main:app --port 8000
pause
