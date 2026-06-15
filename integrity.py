"""Verificación de integridad de los archivos críticos.

En desarrollo (sin hashes.json) no hace nada. Antes de publicar una build
hay que ejecutar generar_hashes.py:

  - `python generar_hashes.py`        -> hashes.json para los .py (proyecto)
  - `python generar_hashes.py --exe`  -> dist/hashes.json para los .exe

Al iniciar, verificar_integridad_o_salir() recalcula los hashes de los
archivos relevantes (.py en modo desarrollo, .exe en modo compilado) y
cierra la app si algo fue modificado respecto al hashes.json cifrado.
"""

import hashlib
import json
import os
import sys

from cryptography.fernet import Fernet
from _keys import OBFUSCATION_KEY

ARCHIVOS_CRITICOS_PY = [
    'SimpleHub.py',
    'auth_manager.py',
    'security.py',
    'config.py',
    'hardware_id.py',
    'anti_debug.py',
]

# update_helper.exe queda fuera: corre como proceso aparte mientras
# SimpleHub.exe está cerrado y no se autoactualiza (ver actualizador.py).
ARCHIVOS_CRITICOS_EXE = [
    'SimpleHub.exe',
    'SimpleResolver.exe',
    'SimpleDownloader.exe',
]

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
    ARCHIVOS_CRITICOS = ARCHIVOS_CRITICOS_EXE
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    ARCHIVOS_CRITICOS = ARCHIVOS_CRITICOS_PY

HASHES_PATH = os.path.join(BASE_DIR, 'hashes.json')


def calcular_hashes(directorio=None, archivos=None):
    directorio = directorio or BASE_DIR
    archivos = archivos or ARCHIVOS_CRITICOS
    hashes = {}
    for archivo in archivos:
        ruta = os.path.join(directorio, archivo)
        if os.path.exists(ruta):
            with open(ruta, 'rb') as f:
                hashes[archivo] = hashlib.sha256(f.read()).hexdigest()
    return hashes


def _cargar_hashes_originales():
    if not os.path.exists(HASHES_PATH):
        return None
    try:
        with open(HASHES_PATH, 'rb') as f:
            data = Fernet(OBFUSCATION_KEY).decrypt(f.read())
        return json.loads(data.decode())
    except Exception:
        return None


def verificar_integridad(hashes_originales=None):
    if hashes_originales is None:
        hashes_originales = _cargar_hashes_originales()
    if hashes_originales is None:
        # Sin hashes.json (modo desarrollo / portable sin firma): no se verifica.
        return True

    actuales = calcular_hashes()
    for archivo, hash_original in hashes_originales.items():
        if actuales.get(archivo) != hash_original:
            return False
    return True


def verificar_integridad_o_salir():
    if not verificar_integridad():
        sys.exit(0)
