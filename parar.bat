@echo off
REM Para o Transcritor (mata o processo que escuta na porta 8000).
echo Parando Transcritor...

set "found="
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000" ^| findstr LISTENING') do (
    taskkill /F /PID %%a >nul 2>&1
    set "found=1"
)

if defined found (
    echo Transcritor parado.
) else (
    echo Nada estava rodando na porta 8000.
)
ping -n 3 127.0.0.1 >nul
