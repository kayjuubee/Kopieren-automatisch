@echo off
cd /d "%~dp0"
if exist .venv\Scripts\pythonw.exe (
 start "" .venv\Scripts\pythonw.exe app.py
) else (
 pyw -3 app.py
 if errorlevel 1 (
  echo Bitte zuerst Bauen.bat ausfuehren oder requirements.txt installieren.
  pause
 )
)
