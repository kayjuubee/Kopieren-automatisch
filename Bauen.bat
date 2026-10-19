@echo off
cd /d "%~dp0"
py -3 -m venv .venv
if errorlevel 1 goto error
.venv\Scripts\python -m pip install -r requirements-build.txt
if errorlevel 1 goto error
.venv\Scripts\python -m unittest discover -s tests -v
if errorlevel 1 goto error
.venv\Scripts\python -m PyInstaller --noconfirm --clean --onefile --windowed --name kayjuubee-USB --add-data "assets;assets" app.py
if errorlevel 1 goto error
start /wait "" dist\kayjuubee-USB.exe --self-test
if errorlevel 1 goto error
if not exist self-test-report.json goto error
echo Fertig: dist\kayjuubee-USB.exe
pause
exit /b 0
:error
echo Erstellung fehlgeschlagen. Siehe Fehlermeldung oben.
pause
exit /b 1
