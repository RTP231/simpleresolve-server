"""Genera hashes.json (cifrado) a partir de los archivos críticos actuales.

  python generar_hashes.py        -> hashes.json para los .py del proyecto
  python generar_hashes.py --exe  -> dist/hashes.json para los .exe compilados

Ejecutar antes de empaquetar (sin --exe) y de nuevo después de compilar con
PyInstaller (con --exe), para que integrity.verificar_integridad_o_salir()
pueda detectar modificaciones en cada modo.
"""

import json
import os
import sys

from cryptography.fernet import Fernet
from _keys import OBFUSCATION_KEY
import integrity


def main():
    if '--exe' in sys.argv:
        directorio = os.path.join(integrity.BASE_DIR, 'dist')
        archivos = integrity.ARCHIVOS_CRITICOS_EXE
    else:
        directorio = integrity.BASE_DIR
        archivos = integrity.ARCHIVOS_CRITICOS_PY

    hashes = integrity.calcular_hashes(directorio, archivos)
    hashes_path = os.path.join(directorio, 'hashes.json')
    data = Fernet(OBFUSCATION_KEY).encrypt(json.dumps(hashes).encode())
    with open(hashes_path, 'wb') as f:
        f.write(data)
    print(f"{hashes_path} generado con {len(hashes)} archivo(s):")
    for archivo in hashes:
        print(f"  - {archivo}")


if __name__ == '__main__':
    main()
