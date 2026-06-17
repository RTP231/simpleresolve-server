"""Helper de actualización de SimpleHub.

Se lanza como proceso separado desde actualizador.py (en modo compilado,
como update_helper.exe). Orden de trabajo:

  a) Cierra SimpleResolver/SimpleDownloader si están abiertos (psutil).
  b) Borra cualquier .exe de la carpeta salvo SimpleHub.exe y
     update_helper.exe (versiones viejas que ya no se usan).
  c) Instala los .exe.new descargados en orden: SimpleResolver,
     SimpleDownloader, update_helper (a un nombre temporal, ver más abajo)
     y SimpleHub al final.
  d) Recrea los marcadores .sr_app / .sd_app.
  e) Relanza SimpleHub.exe.
  f) Completa su propio reemplazo y se autoelimina mediante un .bat
     invisible para el usuario.

update_helper.exe no puede sobreescribirse a sí mismo de forma directa
mientras sigue corriendo desde ese mismo archivo, así que su .new se
renombra primero a update_helper.exe.new2; al final, el ejecutable en
curso se renombra a update_helper.exe.old (Windows permite renombrar un
.exe en ejecución) para dejar el nombre original libre, se instala ahí la
versión nueva, y el .bat borra el .old sobrante.
"""

import os
import sys
import time
import json
import subprocess

import psutil
import requests

import marcadores

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

GITHUB_RAW = "https://raw.githubusercontent.com/RTP231/simpleresolve-server/cliente"

# update_helper.exe se gestiona aparte (ver _instalar_nuevas_versiones).
_EXE_PROTEGIDOS = {'SimpleHub.exe', 'update_helper.exe'}
_ORDEN_INSTALACION = ['SimpleResolver.exe', 'SimpleDownloader.exe', 'SimpleHub.exe']


def _cerrar_proceso(nombre):
    for proc in psutil.process_iter(['name']):
        try:
            if nombre.lower() in (proc.info['name'] or '').lower():
                proc.terminate()
                proc.wait(timeout=5)
        except Exception:
            pass


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


def _borrar_exes_viejos():
    try:
        for archivo in os.listdir(BASE_DIR):
            if archivo.endswith('.exe') and archivo not in _EXE_PROTEGIDOS:
                try:
                    os.remove(os.path.join(BASE_DIR, archivo))
                except OSError:
                    pass
    except OSError:
        pass


def _instalar_nuevas_versiones():
    """Instala SimpleResolver/SimpleDownloader/SimpleHub. update_helper.exe
    se deja preparado en update_helper.exe.new2 para instalarse al final."""
    helper_nuevo = os.path.join(BASE_DIR, 'update_helper.exe.new')
    helper_temp = os.path.join(BASE_DIR, 'update_helper.exe.new2')
    if os.path.exists(helper_nuevo):
        try:
            os.replace(helper_nuevo, helper_temp)
        except OSError:
            helper_temp = None
    else:
        helper_temp = None

    for nombre in _ORDEN_INSTALACION:
        nuevo = os.path.join(BASE_DIR, f'{nombre}.new')
        if os.path.exists(nuevo):
            _reemplazar_archivo(nuevo, os.path.join(BASE_DIR, nombre))

    return helper_temp


def _actualizar_version_json():
    try:
        r = requests.get(f"{GITHUB_RAW}/version.json", timeout=10)
        r.raise_for_status()
        with open(os.path.join(BASE_DIR, 'version.json'), 'w', encoding='utf-8') as f:
            json.dump(r.json(), f, indent=4, ensure_ascii=False)
    except Exception:
        pass


def _crear_marcadores_nuevos():
    marcadores.crear_marcador('SimpleResolver.exe', BASE_DIR)
    marcadores.crear_marcador('SimpleDownloader.exe', BASE_DIR)


def _relanzar_simplehub():
    simplehub_exe = os.path.join(BASE_DIR, 'SimpleHub.exe')
    if os.path.exists(simplehub_exe):
        subprocess.Popen([simplehub_exe], cwd=BASE_DIR)


def _autoeliminarse(helper_temp):
    """Completa el reemplazo de update_helper.exe (si había una versión
    nueva descargada) y se borra a sí mismo de forma invisible."""
    actual = os.path.join(BASE_DIR, 'update_helper.exe')
    viejo = os.path.join(BASE_DIR, 'update_helper.exe.old')

    objetivo_borrar = None
    if helper_temp and os.path.exists(helper_temp):
        try:
            os.replace(actual, viejo)
            os.replace(helper_temp, actual)
            objetivo_borrar = viejo
        except OSError:
            objetivo_borrar = None

    if objetivo_borrar is None:
        # No había versión nueva de update_helper (o el reemplazo falló):
        # no tocamos el ejecutable en uso, solo limpiamos el .bat.
        return

    marcadores.crear_marcador('update_helper.exe', BASE_DIR)

    bat_content = f'timeout /t 2 & del "{objetivo_borrar}"\r\ndel "%~f0"\r\n'
    bat_path = os.path.join(BASE_DIR, '_cleanup.bat')
    try:
        with open(bat_path, 'w', encoding='utf-8') as f:
            f.write(bat_content)
        subprocess.Popen(bat_path, shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
    except OSError:
        pass


def main():
    _cerrar_proceso('SimpleResolver')
    _cerrar_proceso('SimpleDownloader')
    time.sleep(2)

    _borrar_exes_viejos()

    helper_temp = _instalar_nuevas_versiones()
    _actualizar_version_json()
    _crear_marcadores_nuevos()

    _relanzar_simplehub()
    _autoeliminarse(helper_temp)
    sys.exit()


if __name__ == '__main__':
    main()
