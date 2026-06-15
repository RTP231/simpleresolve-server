@echo off
cd /d "%~dp0"
set /p version="Nueva version (ej: 1.0.1): "
if "%version%"=="" (
    echo No se ingreso version, cancelando.
    pause
    exit /b 1
)
python -c "import json; d=json.load(open('version.json', encoding='utf-8')); d['version']='%version%'; json.dump(d, open('version.json', 'w', encoding='utf-8'), indent=4, ensure_ascii=False)"
git add .
git commit -m "v%version% - actualizacion"
git push origin cliente
echo Actualizacion v%version% subida a GitHub (rama cliente)

where gh >nul 2>nul
if errorlevel 1 (
    echo.
    echo [AVISO] GitHub CLI no esta instalado, no se publico la release con los .exe.
    echo Instalar con: winget install GitHub.cli
    pause
    exit /b 0
)

if not exist "dist\SimpleHub.exe" (
    echo.
    echo [AVISO] No se encontraron los .exe en dist\, no se publico la release.
    pause
    exit /b 0
)

python generar_hashes.py --exe
gh release create v%version% dist\SimpleHub.exe dist\SimpleResolver.exe dist\SimpleDownloader.exe dist\update_helper.exe dist\hashes.json --title "v%version%"
echo Release v%version% publicada en GitHub con los .exe
pause
