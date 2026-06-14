import os
import shutil
import sys
import winreg

_APPS = ('SimpleResolve', 'SimpleDownload', 'SimplePDF')

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _borrar_config(dry_run):
    appdata = os.environ.get('APPDATA', os.path.expanduser('~'))
    for nombre in _APPS:
        ruta = os.path.join(appdata, nombre)
        if os.path.isdir(ruta) and not dry_run:
            shutil.rmtree(ruta, ignore_errors=True)


def _borrar_accesos_directos(dry_run):
    escritorio = os.path.join(os.path.expanduser('~'), 'Desktop')
    menu_inicio = os.path.join(
        os.environ.get('APPDATA', ''), r'Microsoft\Windows\Start Menu\Programs'
    )
    for carpeta in (escritorio, menu_inicio):
        if not os.path.isdir(carpeta):
            continue
        for nombre in os.listdir(carpeta):
            if nombre.endswith('.lnk') and any(app.lower() in nombre.lower() for app in _APPS):
                ruta = os.path.join(carpeta, nombre)
                if not dry_run:
                    try:
                        os.remove(ruta)
                    except OSError:
                        pass


def _borrar_inicio_automatico(dry_run):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_ALL_ACCESS) as key:
            i = 0
            valores = []
            while True:
                try:
                    nombre, _, _ = winreg.EnumValue(key, i)
                    valores.append(nombre)
                    i += 1
                except OSError:
                    break
            for nombre in valores:
                if any(app.lower() in nombre.lower() for app in _APPS):
                    if not dry_run:
                        winreg.DeleteValue(key, nombre)
    except OSError:
        pass


def _borrar_cache(dry_run):
    local = os.environ.get('LOCALAPPDATA', os.path.expanduser('~'))
    for nombre in _APPS:
        ruta = os.path.join(local, nombre)
        if os.path.isdir(ruta) and not dry_run:
            shutil.rmtree(ruta, ignore_errors=True)


def ejecutar_autodestruccion(dry_run=False):
    _borrar_config(dry_run)
    _borrar_cache(dry_run)
    _borrar_accesos_directos(dry_run)
    if sys.platform == 'win32':
        _borrar_inicio_automatico(dry_run)
