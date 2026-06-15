@echo off
cd /d "%~dp0"
echo Iniciando SimpleHub...
echo.
"C:\Users\rkpst\AppData\Local\Programs\Python\Python311\python.exe" SimpleHub.py > simplehub_log.txt 2>&1
echo.
echo --- El programa termino (codigo %errorlevel%) ---
echo.
echo Mostrando el log:
echo ----------------------------------------
type simplehub_log.txt
echo ----------------------------------------
pause
