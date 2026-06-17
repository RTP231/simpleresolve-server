"""Helper de actualización de SimpleHub.

Se lanza como proceso separado desde actualizador.py (en modo compilado,
como update_helper.exe). Orden de trabajo:

  a) Cierra SimpleResolver/SimpleDownloader si están abiertos (psutil).
  b) Borra cualquier .exe de la carpeta salvo SimpleHub.exe y
     update_helper.exe (versiones viejas que ya no se usan).
  c) Instala los .exe.new descargados en orden: SimpleResolver,
     SimpleDownloader, update_helper (a un nombre temporal, ver más abajo)
     y SimpleHub al final.
  d) Recrea los marcadores .sr_app / .sd_app y refresca version.json y
     hashes.json (el hash de los exe recién instalados no coincide con el
     hashes.json viejo, y SimpleHub usa ese archivo para verificar su propia
     integridad al arrancar; si no se refresca, SimpleHub se cierra solo
     nada más abrir).
  e) Relanza SimpleHub.exe y comprueba que efectivamente arrancó. Si no
     (proceso corrupto/incompatible), restaura el respaldo tomado en (a.1)
     y reintenta.
  f) Completa su propio reemplazo y se autoelimina mediante un .bat
     invisible para el usuario.

Cada paso se registra en update_log.txt (en la carpeta de instalación) para
poder diagnosticar una actualización fallida.

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
import shutil
import subprocess
from datetime import datetime

import psutil
import requests

import marcadores

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

GITHUB_RAW = "https://raw.githubusercontent.com/RTP231/simpleresolve-server/cliente"
GITHUB_RELEASES = "https://github.com/RTP231/simpleresolve-server/releases/latest/download"

LOG_PATH = os.path.join(BASE_DIR, 'update_log.txt')

# update_helper.exe se gestiona aparte (ver _instalar_nuevas_versiones).
_EXE_PROTEGIDOS = {'SimpleHub.exe', 'update_helper.exe'}
_ORDEN_INSTALACION = ['SimpleResolver.exe', 'SimpleDownloader.exe']

# Conjunto que se respalda antes de tocar nada y se restaura si SimpleHub.exe
# no llega a arrancar: los tres exe que verifica integrity.py más el propio
# hashes.json contra el que se comparan (deben restaurarse juntos, si no la
# versión "restaurada" seguiría fallando la verificación de integridad).
_ARCHIVOS_RESPALDO = ['SimpleHub.exe', 'SimpleResolver.exe', 'SimpleDownloader.exe', 'hashes.json']


def _log(mensaje):
    try:
        with open(LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {mensaje}\n")
    except OSError:
        pass


def _log_reset():
    try:
        with open(LOG_PATH, 'w', encoding='utf-8') as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] === Iniciando actualización ===\n")
    except OSError:
        pass


def _validar_exe(ruta, tam_minimo=100_000):
    """Comprobación barata de que un .exe no quedó truncado/corrupto:
    existe, pesa más que tam_minimo y empieza con la cabecera MZ de un PE."""
    try:
        if not os.path.exists(ruta):
            return False, "no existe"
        tam = os.path.getsize(ruta)
        if tam < tam_minimo:
            return False, f"tamaño sospechosamente pequeño ({tam} bytes)"
        with open(ruta, 'rb') as f:
            cabecera = f.read(2)
        if cabecera != b'MZ':
            return False, "cabecera de ejecutable inválida (descarga corrupta)"
        return True, ""
    except OSError as e:
        return False, str(e)


def _cerrar_proceso(nombre):
    for proc in psutil.process_iter(['name']):
        try:
            if nombre.lower() in (proc.info['name'] or '').lower():
                proc.terminate()
                proc.wait(timeout=5)
                _log(f"Proceso cerrado: {proc.info['name']}")
        except Exception as e:
            _log(f"No se pudo cerrar un proceso de '{nombre}': {e}")


def _reemplazar_archivo(nuevo, original, intentos=10, espera=1):
    """Reemplaza original por nuevo, reintentando si el archivo todavía
    está bloqueado (p. ej. un .exe que recién se cerró)."""
    ultimo_error = None
    for _ in range(intentos):
        try:
            if os.path.exists(original):
                os.remove(original)
            os.rename(nuevo, original)
            return True
        except OSError as e:
            ultimo_error = e
            time.sleep(espera)
    _log(f"ERROR: no se pudo instalar {os.path.basename(original)}: {ultimo_error}")
    return False


def _crear_respaldo():
    for nombre in _ARCHIVOS_RESPALDO:
        origen = os.path.join(BASE_DIR, nombre)
        if os.path.exists(origen):
            try:
                shutil.copy2(origen, origen + '.backup')
                _log(f"Respaldo creado: {nombre}.backup")
            except OSError as e:
                _log(f"ERROR creando respaldo de {nombre}: {e}")


def _restaurar_respaldo():
    for nombre in _ARCHIVOS_RESPALDO:
        backup = os.path.join(BASE_DIR, nombre + '.backup')
        destino = os.path.join(BASE_DIR, nombre)
        if os.path.exists(backup):
            try:
                os.replace(backup, destino)
                _log(f"Restaurado desde respaldo: {nombre}")
            except OSError as e:
                _log(f"ERROR restaurando {nombre} desde el respaldo: {e}")
        else:
            _log(f"No hay respaldo de {nombre} para restaurar")


def _borrar_respaldo():
    for nombre in _ARCHIVOS_RESPALDO:
        backup = os.path.join(BASE_DIR, nombre + '.backup')
        if os.path.exists(backup):
            try:
                os.remove(backup)
            except OSError:
                pass


def _borrar_exes_viejos():
    try:
        for archivo in os.listdir(BASE_DIR):
            if archivo.endswith('.exe') and archivo not in _EXE_PROTEGIDOS:
                try:
                    os.remove(os.path.join(BASE_DIR, archivo))
                    _log(f"Borrado exe viejo: {archivo}")
                except OSError as e:
                    _log(f"No se pudo borrar {archivo}: {e}")
    except OSError as e:
        _log(f"ERROR listando la carpeta para borrar exes viejos: {e}")


def _instalar_nuevas_versiones():
    """Instala SimpleResolver/SimpleDownloader y, por separado, SimpleHub
    (ver _instalar_simplehub). update_helper.exe se deja preparado en
    update_helper.exe.new2 para instalarse al final (ver _autoeliminarse)."""
    helper_nuevo = os.path.join(BASE_DIR, 'update_helper.exe.new')
    helper_temp = os.path.join(BASE_DIR, 'update_helper.exe.new2')
    if os.path.exists(helper_nuevo):
        try:
            os.replace(helper_nuevo, helper_temp)
        except OSError as e:
            _log(f"ERROR preparando update_helper.exe.new2: {e}")
            helper_temp = None
    else:
        helper_temp = None

    for nombre in _ORDEN_INSTALACION:
        nuevo = os.path.join(BASE_DIR, f'{nombre}.new')
        if not os.path.exists(nuevo):
            continue
        destino = os.path.join(BASE_DIR, nombre)
        if _reemplazar_archivo(nuevo, destino):
            ok, motivo = _validar_exe(destino)
            if ok:
                _log(f"{nombre} instalado y validado correctamente")
            else:
                _log(f"ERROR: {nombre} instalado pero parece corrupto ({motivo})")

    return helper_temp


def _instalar_simplehub():
    """Instala SimpleHub.exe.new -> SimpleHub.exe. El respaldo previo ya
    se tomó en _crear_respaldo(); aquí solo se instala y valida."""
    nuevo = os.path.join(BASE_DIR, 'SimpleHub.exe.new')
    actual = os.path.join(BASE_DIR, 'SimpleHub.exe')
    if not os.path.exists(nuevo):
        _log("SimpleHub.exe.new no encontrado; se conserva la versión actual")
        return

    if _reemplazar_archivo(nuevo, actual):
        ok, motivo = _validar_exe(actual)
        if ok:
            _log("SimpleHub.exe instalado y validado correctamente")
        else:
            _log(f"ERROR: SimpleHub.exe instalado pero parece corrupto ({motivo})")


def _actualizar_version_json():
    try:
        r = requests.get(f"{GITHUB_RAW}/version.json", timeout=10)
        r.raise_for_status()
        with open(os.path.join(BASE_DIR, 'version.json'), 'w', encoding='utf-8') as f:
            json.dump(r.json(), f, indent=4, ensure_ascii=False)
        _log("version.json actualizado")
    except Exception as e:
        _log(f"ERROR actualizando version.json: {e}")


def _actualizar_hashes_json():
    """Refresca hashes.json con el de la nueva versión. Es imprescindible:
    integrity.py compara los exe recién instalados contra este archivo al
    arrancar SimpleHub, y si queda desactualizado la verificación falla
    siempre y SimpleHub se cierra solo sin avisar. Si no se puede descargar
    el nuevo, se borra el viejo para no bloquear el arranque (sin
    hashes.json, integrity.py simplemente no verifica)."""
    destino = os.path.join(BASE_DIR, 'hashes.json')
    try:
        r = requests.get(f"{GITHUB_RELEASES}/hashes.json", timeout=10)
        r.raise_for_status()
        with open(destino, 'wb') as f:
            f.write(r.content)
        _log("hashes.json actualizado")
    except Exception as e:
        _log(f"ERROR descargando hashes.json nuevo ({e}); se borra el viejo para no bloquear el arranque")
        try:
            if os.path.exists(destino):
                os.remove(destino)
        except OSError:
            pass


def _crear_marcadores_nuevos():
    marcadores.crear_marcador('SimpleResolver.exe', BASE_DIR)
    marcadores.crear_marcador('SimpleDownloader.exe', BASE_DIR)
    _log("Marcadores .sr_app / .sd_app recreados")


def _lanzar_y_verificar(espera=3):
    """Lanza SimpleHub.exe y comprueba que el proceso sigue vivo unos
    segundos después. Si se cierra solo casi de inmediato (típico de un
    .exe corrupto o de una verificación de integridad fallida), se
    considera que falló."""
    simplehub_exe = os.path.join(BASE_DIR, 'SimpleHub.exe')
    if not os.path.exists(simplehub_exe):
        _log("ERROR: SimpleHub.exe no existe, no se puede lanzar")
        return False

    proc = subprocess.Popen([simplehub_exe], cwd=BASE_DIR)
    time.sleep(espera)
    if proc.poll() is None:
        return True
    _log(f"SimpleHub.exe terminó casi de inmediato (código {proc.returncode})")
    return False


def _relanzar_simplehub():
    """Intenta arrancar la versión recién instalada; si falla, restaura el
    respaldo (SimpleHub/SimpleResolver/SimpleDownloader.exe + hashes.json)
    y reintenta. Devuelve True si SimpleHub terminó arrancando, sea con la
    versión nueva o con la restaurada."""
    ok, motivo = _validar_exe(os.path.join(BASE_DIR, 'SimpleHub.exe'))
    if not ok:
        _log(f"SimpleHub.exe no pasa la validación previa ({motivo}); se restaura el respaldo")
        _restaurar_respaldo()
        if _lanzar_y_verificar():
            _log("SimpleHub.exe restaurado desde el respaldo arrancó correctamente")
            return True
        _log("ERROR: SimpleHub.exe restaurado tampoco arrancó")
        return False

    if _lanzar_y_verificar():
        _log("SimpleHub.exe arrancó correctamente")
        return True

    _log("Restaurando respaldo tras fallo de arranque")
    _restaurar_respaldo()
    if _lanzar_y_verificar():
        _log("SimpleHub.exe restaurado desde el respaldo arrancó correctamente")
        return True
    _log("ERROR: SimpleHub.exe restaurado tampoco arrancó")
    return False


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
        except OSError as e:
            _log(f"ERROR reemplazando update_helper.exe: {e}")
            objetivo_borrar = None

    if objetivo_borrar is None:
        # No había versión nueva de update_helper (o el reemplazo falló):
        # no tocamos el ejecutable en uso, solo limpiamos el .bat.
        return

    marcadores.crear_marcador('update_helper.exe', BASE_DIR)
    _log("update_helper.exe actualizado")

    bat_content = f'timeout /t 2 & del "{objetivo_borrar}"\r\ndel "%~f0"\r\n'
    bat_path = os.path.join(BASE_DIR, '_cleanup.bat')
    try:
        with open(bat_path, 'w', encoding='utf-8') as f:
            f.write(bat_content)
        subprocess.Popen(bat_path, shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
    except OSError as e:
        _log(f"ERROR programando la autolimpieza: {e}")


def main():
    _log_reset()

    _cerrar_proceso('SimpleResolver')
    _cerrar_proceso('SimpleDownloader')
    time.sleep(2)

    _crear_respaldo()
    _borrar_exes_viejos()

    helper_temp = _instalar_nuevas_versiones()
    _instalar_simplehub()
    _actualizar_version_json()
    _actualizar_hashes_json()
    _crear_marcadores_nuevos()

    exito = _relanzar_simplehub()
    if exito:
        _borrar_respaldo()
    else:
        _log("La actualización falló: se deja el respaldo en la carpeta para diagnóstico")

    _autoeliminarse(helper_temp)
    _log("=== Actualización finalizada ===")
    sys.exit()


if __name__ == '__main__':
    main()
