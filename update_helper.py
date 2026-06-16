"""Helper de actualización de SimpleHub.

Se lanza como proceso separado desde actualizador.py (en modo compilado,
como update_helper.exe). Espera a que SimpleHub se cierre, reemplaza los
archivos descargados (*.new, ya sean .py o .exe) por los originales,
limpia archivos viejos, actualiza version.json y vuelve a lanzar SimpleHub.
"""

import os
import sys
import time
import glob
import json
import subprocess

import requests

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

GITHUB_RAW = "https://raw.githubusercontent.com/RTP231/simpleresolve-server/cliente"

# Únicos archivos que deben existir en la carpeta de instalación.
ARCHIVOS_PERMITIDOS = {
    'SimpleHub.exe',
    'SimpleResolver.exe',
    'SimpleDownloader.exe',
    'update_helper.exe',
    'version.json',
    'hashes.json',
    'LEEME.txt',
}

_LEEME = """\
=== SimpleResolve - Carpeta de instalación ===

Archivos en esta carpeta:
  SimpleHub.exe        - Aplicación principal
  SimpleResolver.exe   - Módulo de resolución
  SimpleDownloader.exe - Módulo de descargas
  update_helper.exe    - Instalador de actualizaciones (no borrar)
  version.json         - Versión actual
  hashes.json          - Verificación de integridad

ACCESOS DIRECTOS (.lnk)
  Windows puede crear accesos directos en esta carpeta al anclar
  la aplicación al menú Inicio o a la barra de tareas. Esos archivos
  .lnk son gestionados por Windows y no afectan al funcionamiento
  de SimpleResolve; puedes moverlos o eliminarlos libremente.

PERSONALIZACIÓN (fondo, colores, video)
  La configuración personal se guarda en:
    %APPDATA%\\SimpleResolve\\config\\personalizacion.json
  Esa carpeta NO se toca durante las actualizaciones, por lo que
  tu fondo y colores se conservan siempre.
"""


def _reemplazar_archivo(nuevo, original, intentos=10, espera=1):
    """Reemplaza original por nuevo, reintentando si el archivo todavía
    está bloqueado (p. ej. un .exe que recién se cerró)."""
    for _ in range(intentos):
        try:
            if os.path.exists(original):
                os.remove(original)
            os.rename(nuevo, original)
            return True
        except OSError:
            time.sleep(espera)
    return False


def _limpiar_archivos_viejos():
    """Elimina de BASE_DIR cualquier archivo que no esté en ARCHIVOS_PERMITIDOS."""
    try:
        for nombre in os.listdir(BASE_DIR):
            ruta = os.path.join(BASE_DIR, nombre)
            if os.path.isfile(ruta) and nombre not in ARCHIVOS_PERMITIDOS:
                try:
                    os.remove(ruta)
                except OSError:
                    pass
    except OSError:
        pass


def _crear_leeme():
    ruta = os.path.join(BASE_DIR, 'LEEME.txt')
    try:
        with open(ruta, 'w', encoding='utf-8') as f:
            f.write(_LEEME)
    except OSError:
        pass


def main():
    time.sleep(2)

    for nuevo in glob.glob(os.path.join(BASE_DIR, '*.new')):
        original = nuevo[:-len('.new')]
        _reemplazar_archivo(nuevo, original)

    _limpiar_archivos_viejos()
    _crear_leeme()

    try:
        r = requests.get(f"{GITHUB_RAW}/version.json", timeout=10)
        r.raise_for_status()
        with open(os.path.join(BASE_DIR, 'version.json'), 'w', encoding='utf-8') as f:
            json.dump(r.json(), f, indent=4, ensure_ascii=False)
    except Exception:
        pass

    simplehub_exe = os.path.join(BASE_DIR, 'SimpleHub.exe')
    if os.path.exists(simplehub_exe):
        subprocess.Popen([simplehub_exe], cwd=BASE_DIR)
    else:
        subprocess.Popen([sys.executable, os.path.join(BASE_DIR, 'SimpleHub.py')], cwd=BASE_DIR)


if __name__ == '__main__':
    main()
