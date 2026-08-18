@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo.
echo  ========================================================
echo   🩺 Network Doctor - Diagnóstico Inteligente de Rede
echo  ========================================================
echo.

where python >nul 2>nul
if %errorlevel%==0 (
    python main.py %*
    goto fim
)
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 main.py %*
    goto fim
)

rem Fallback: usa o bootstrap PowerShell (run.ps1) para baixar e rodar o Python portátil
echo  Python não encontrado no PATH. Iniciando via launcher PowerShell...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" %*

:fim
echo.
pause
