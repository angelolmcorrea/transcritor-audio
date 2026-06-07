@echo off
REM Inicia o Transcritor localmente (http://127.0.0.1:8000).
cd /d "%~dp0"

REM Se ja houver algo na porta 8000, avisa e sai.
netstat -ano | findstr ":8000" | findstr LISTENING >nul
if %errorlevel%==0 (
    echo Ja existe algo rodando na porta 8000. Rode parar.bat antes.
    pause
    exit /b 1
)

echo Iniciando Transcritor...
start "Transcritor" "%~dp0.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
ping -n 4 127.0.0.1 >nul
start "" "http://127.0.0.1:8000"
echo.
echo Transcritor rodando em http://127.0.0.1:8000
echo O servidor ficou numa janela separada chamada "Transcritor".
echo Para parar: rode parar.bat (ou feche aquela janela).
