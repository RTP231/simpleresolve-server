"""Marcadores ocultos de instalación de cada exe de la suite.

Cada exe (SimpleResolver, SimpleDownloader, update_helper, SimpleHub) crea
su propio marcador al arrancar, y update_helper.py los vuelve a crear tras
instalar una actualización. Permiten saber qué apps están instaladas en la
carpeta sin depender de que el usuario las haya abierto.
"""

import os
import sys

MARCADORES = {
    'SimpleResolver.exe': '.sr_app',
    'SimpleDownloader.exe': '.sd_app',
    'update_helper.exe': '.uh_app',
    'SimpleHub.exe': '.sh_app',
}

_FILE_ATTRIBUTE_HIDDEN = 0x02


def _directorio_actual():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _ocultar(ruta):
    if sys.platform != 'win32':
        return
    try:
        import ctypes
        ctypes.windll.kernel32.SetFileAttributesW(str(ruta), _FILE_ATTRIBUTE_HIDDEN)
    except Exception:
        pass


def crear_marcador(nombre_exe, directorio=None):
    """Crea (si no existe) el marcador oculto correspondiente a nombre_exe."""
    marcador = MARCADORES.get(nombre_exe)
    if not marcador:
        return
    directorio = directorio or _directorio_actual()
    ruta = os.path.join(directorio, marcador)
    if not os.path.exists(ruta):
        try:
            open(ruta, 'w').close()
        except OSError:
            return
    _ocultar(ruta)
