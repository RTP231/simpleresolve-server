"""Helper de actualización de SimpleHub.

Se lanza como proceso separado desde actualizador.py (en modo compilado,
como update_helper.exe). Espera a que SimpleHub se cierre, reemplaza los
archivos descargados (*.new, ya sean .py o .exe) por los originales,
actualiza version.json y vuelve a lanzar SimpleHub.
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


def main():
    time.sleep(2)

    for nuevo in glob.glob(os.path.join(BASE_DIR, '*.new')):
        original = nuevo[:-len('.new')]
        _reemplazar_archivo(nuevo, original)

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
