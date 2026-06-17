"""Limpieza total de Simple Suite.

Borra únicamente los archivos y carpetas que pertenecen a esta suite, para
dejar el equipo listo para una instalación desde cero. Es deliberadamente
muy específico (nombres exactos, carpetas exactas) para no tocar nunca
archivos del sistema o de otras aplicaciones.

Qué borra:
  1) En el Escritorio y sus subcarpetas: los archivos de Simple Suite por
     nombre exacto (SimpleHub.exe, hashes.json, marcadores ocultos, etc.)
     y sus variantes *.new / *.backup / *.old.
  2) La carpeta de configuración %APPDATA%\\SimpleResolve\\ completa.
  3) Las carpetas temporales de PyInstaller (%TEMP%\\_MEI*) que haya
     dejado cualquiera de los exe de la suite al ejecutarse en modo
     onefile.

Antes de borrar nada se muestra el listado completo y se pide
confirmación explícita.
"""

import os
import sys
import shutil

if sys.platform == 'win32':
    try:
        import ctypes
        # cmd.exe usa por defecto un codepage OEM que no entiende UTF-8 y
        # muestra acentos rotos; forzarlo a UTF-8 arregla el listado.
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        ctypes.windll.kernel32.SetConsoleCP(65001)
    except Exception:
        pass

# Nombres exactos de archivos de Simple Suite. Nada que no coincida con
# uno de estos nombres (o con uno de ellos más una extensión de
# _EXTENSIONES_RELACIONADAS) se considera para borrar.
_ARCHIVOS_EXACTOS = {
    'SimpleHub.exe',
    'SimpleResolver.exe',
    'SimpleDownloader.exe',
    'update_helper.exe',
    'limpiar_instalacion.exe',
    'hashes.json',
    'version.json',
    'LEEME.txt',
    '.sr_app',
    '.sd_app',
    '.sh_app',
    '.uh_app',
    '_cleanup.bat',
    'update_log.txt',
    'simplehub_log.txt',
}

_EXTENSIONES_RELACIONADAS = ('.new', '.backup', '.old')

_CARPETA_APPDATA_NOMBRE = 'SimpleResolve'
_PREFIJO_TEMP_PYINSTALLER = '_MEI'


def _es_archivo_de_la_suite(nombre):
    if nombre in _ARCHIVOS_EXACTOS:
        return True
    for ext in _EXTENSIONES_RELACIONADAS:
        if nombre.endswith(ext) and nombre[:-len(ext)] in _ARCHIVOS_EXACTOS:
            return True
    return False


def _carpetas_escritorio():
    """Rutas de Escritorio existentes: la normal y, si existe, la
    redirigida a OneDrive (algunas cuentas de Windows usan esa)."""
    candidatos = [os.path.join(os.path.expanduser('~'), 'Desktop')]
    onedrive = os.environ.get('OneDrive')
    if onedrive:
        candidatos.append(os.path.join(onedrive, 'Desktop'))

    vistas = set()
    rutas = []
    for candidato in candidatos:
        clave = os.path.normcase(os.path.normpath(candidato))
        if clave not in vistas and os.path.isdir(candidato):
            vistas.add(clave)
            rutas.append(candidato)
    return rutas


def _buscar_archivos_suite():
    encontrados = []
    for carpeta in _carpetas_escritorio():
        for raiz, _carpetas, archivos in os.walk(carpeta):
            for nombre in archivos:
                if _es_archivo_de_la_suite(nombre):
                    encontrados.append(os.path.join(raiz, nombre))
    return encontrados


def _carpeta_appdata():
    appdata = os.environ.get('APPDATA')
    if not appdata:
        return None
    ruta = os.path.join(appdata, _CARPETA_APPDATA_NOMBRE)
    return ruta if os.path.isdir(ruta) else None


def _carpetas_temp_pyinstaller():
    temp = os.environ.get('TEMP') or os.environ.get('TMP')
    if not temp or not os.path.isdir(temp):
        return []
    encontradas = []
    try:
        for nombre in os.listdir(temp):
            if nombre.startswith(_PREFIJO_TEMP_PYINSTALLER):
                ruta = os.path.join(temp, nombre)
                if os.path.isdir(ruta):
                    encontradas.append(ruta)
    except OSError:
        pass
    return encontradas


def _mostrar_listado(archivos, carpeta_appdata, carpetas_temp):
    print()
    print("=== Simple Suite - Limpieza de instalación ===")
    print()
    print("Se encontraron estos elementos:")

    if archivos:
        print(f"\nArchivos en el Escritorio ({len(archivos)}):")
        for ruta in archivos:
            print(f"  - {ruta}")

    if carpeta_appdata:
        print("\nCarpeta de configuración:")
        print(f"  - {carpeta_appdata}")

    if carpetas_temp:
        print(f"\nCarpetas temporales de PyInstaller ({len(carpetas_temp)}):")
        for ruta in carpetas_temp:
            print(f"  - {ruta}")
    print()


def _confirmar():
    try:
        respuesta = input("Se borrarán estos archivos. ¿Continuar? [Sí/No]: ").strip().lower()
    except EOFError:
        return False
    return respuesta in ('s', 'si', 'sí', 'y', 'yes')


def _pausar():
    try:
        input("\nPresiona Enter para salir...")
    except EOFError:
        pass


def _borrar_archivo(ruta, errores):
    try:
        os.remove(ruta)
        return True
    except OSError as e:
        errores.append(f"{ruta}: {e}")
        return False


def _borrar_carpeta(ruta, errores):
    try:
        shutil.rmtree(ruta)
        return True
    except OSError as e:
        errores.append(f"{ruta}: {e}")
        return False


def main():
    archivos = _buscar_archivos_suite()
    carpeta_appdata = _carpeta_appdata()
    carpetas_temp = _carpetas_temp_pyinstaller()

    if not archivos and not carpeta_appdata and not carpetas_temp:
        print("No se encontró ningún archivo de Simple Suite. No hay nada que borrar.")
        _pausar()
        return

    _mostrar_listado(archivos, carpeta_appdata, carpetas_temp)

    if not _confirmar():
        print("\nCancelado. No se borró nada.")
        _pausar()
        return

    eliminados = 0
    errores = []

    for ruta in archivos:
        if _borrar_archivo(ruta, errores):
            eliminados += 1

    if carpeta_appdata and _borrar_carpeta(carpeta_appdata, errores):
        eliminados += 1

    for ruta in carpetas_temp:
        if _borrar_carpeta(ruta, errores):
            eliminados += 1

    print()
    print(f"Eliminados {eliminados} archivos. Listo para instalar desde cero.")

    if errores:
        print(f"\nNo se pudieron borrar {len(errores)} elemento(s):")
        for error in errores:
            print(f"  - {error}")

    _pausar()


if __name__ == '__main__':
    main()
