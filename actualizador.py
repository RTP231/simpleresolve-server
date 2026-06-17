"""Sistema de auto-actualización de SimpleHub.

Comprueba si hay una versión más nueva publicada en GitHub (rama "cliente"),
y si el usuario lo confirma descarga la actualización y relanza la app.

En modo desarrollo (ejecutado como .py) se descargan los .py listados en
version.json desde GITHUB_RAW y se aplica mediante update_helper.py.

En modo compilado (.exe) se descarga el instalador SimpleSetup.exe (Inno
Setup) desde la última GitHub Release y se ejecuta en modo silencioso
(/verysilent /norestart) sobre la misma carpeta de instalación
(%LOCALAPPDATA%\\SimpleSuite, sin privilegios de administrador, así que no
pide UAC). Como el instalador no relanza SimpleHub por sí mismo cuando
corre en silencioso (su [Run] postinstall tiene skipifsilent, pensado para
una instalación manual interactiva), _lanzar_instalador() se encarga de
relanzarlo después desde un .bat temporal.
"""

import os
import sys
import json
import subprocess

import requests

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

ES_COMPILADO = getattr(sys, 'frozen', False)

if ES_COMPILADO:
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

GITHUB_RAW = "https://raw.githubusercontent.com/RTP231/simpleresolve-server/cliente"
GITHUB_RELEASES = "https://github.com/RTP231/simpleresolve-server/releases/latest/download"
VERSION_FILE = os.path.join(BASE_DIR, 'version.json')

# En modo compilado, la actualización es un solo archivo: el instalador.
INSTALADOR_NOMBRE = 'SimpleSetup.exe'

_C_BG = '#0d0d0d'
_C_CARD = '#1a1a1a'
_C_BORDER = '#2a2a2a'
_C_TEXT = '#eaeaf5'
_C_TEXT_SEC = '#888888'


def _cargar_version_local():
    # En frozen, si aún no existe version.json junto al exe (primer arranque),
    # copiar el embebido en sys._MEIPASS para que futuras comparaciones funcionen.
    if ES_COMPILADO and not os.path.exists(VERSION_FILE):
        import shutil
        bundled = os.path.join(sys._MEIPASS, 'version.json')
        if os.path.exists(bundled):
            try:
                shutil.copy2(bundled, VERSION_FILE)
            except OSError:
                pass

    try:
        with open(VERSION_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def verificar_actualizacion():
    """Devuelve la info remota (dict) si hay una versión nueva, o None."""
    try:
        r = requests.get(f"{GITHUB_RAW}/version.json", timeout=5)
        r.raise_for_status()
        remoto = r.json()
        local = _cargar_version_local()
        if local and remoto.get('version') != local.get('version'):
            return remoto
    except Exception:
        pass
    return None


class HiloDescargaActualizacion(QThread):
    progreso = pyqtSignal(int)
    terminado = pyqtSignal(bool, str)

    def __init__(self, archivos, parent=None):
        super().__init__(parent)
        # archivos: lista de tuplas (nombre, url)
        self.archivos = archivos

    def run(self):
        try:
            total = len(self.archivos)
            for i, (nombre, url) in enumerate(self.archivos):
                r = requests.get(url, timeout=120, stream=True)
                if r.status_code != 200:
                    self.terminado.emit(False, f"No se pudo descargar {nombre} (HTTP {r.status_code})")
                    return
                destino = os.path.join(BASE_DIR, f"{nombre}.new")
                with open(destino, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            f.write(chunk)
                self.progreso.emit(int((i + 1) / total * 100))
            self.terminado.emit(True, '')
        except Exception as e:
            self.terminado.emit(False, str(e))


class DialogoActualizacion(QDialog):
    # Evita que se muestren dos diálogos de actualización a la vez (p. ej.
    # si el chequeo automático y el manual responden casi al mismo tiempo).
    _dialog_activo = None

    def __init__(self, info_remota, accent='#7c3aed', parent=None):
        super().__init__(parent)
        self.info_remota = info_remota
        self._accent = accent
        self._hilo = None

        self.setWindowTitle("Actualización disponible")
        self.setFixedWidth(380)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {_C_CARD};
                border: 0.5px solid {_C_BORDER};
                border-radius: 10px;
            }}
            QLabel {{ color: {_C_TEXT}; }}
            QPushButton {{
                background-color: {_C_BORDER};
                color: {_C_TEXT};
                border: none;
                border-radius: 6px;
                padding: 8px 14px;
            }}
            QPushButton:hover {{
                background-color: #3a3a3a;
            }}
            QPushButton:disabled {{
                color: #666666;
            }}
            QPushButton#btnActualizar {{
                background-color: {accent};
                color: white;
                font-weight: bold;
            }}
            QPushButton#btnActualizar:hover {{
                background-color: {accent};
            }}
            QProgressBar {{
                background-color: {_C_BG};
                border: 0.5px solid {_C_BORDER};
                border-radius: 4px;
                text-align: center;
                color: {_C_TEXT};
            }}
            QProgressBar::chunk {{
                background-color: {accent};
                border-radius: 4px;
            }}
        """)

        lay = QVBoxLayout(self)
        lay.setSpacing(12)

        lbl_titulo = QLabel("¡Nueva versión disponible!")
        lbl_titulo.setStyleSheet("font-size: 14px; font-weight: bold; background: transparent;")
        lay.addWidget(lbl_titulo)

        lbl_desc = QLabel(
            "Hay una actualización lista para instalar.\n"
            "La aplicación se reiniciará automáticamente."
        )
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet(f"color: {_C_TEXT_SEC}; font-size: 11px; background: transparent;")
        lay.addWidget(lbl_desc)

        self.barra = QProgressBar()
        self.barra.setRange(0, 100)
        self.barra.setValue(0)
        self.barra.setVisible(False)
        lay.addWidget(self.barra)

        self.lbl_error = QLabel("")
        self.lbl_error.setStyleSheet("color: #ff6b8a; font-size: 10px; background: transparent;")
        self.lbl_error.setWordWrap(True)
        self.lbl_error.setVisible(False)
        lay.addWidget(self.lbl_error)

        fila_botones = QHBoxLayout()
        self.btn_despues = QPushButton("Recordar después")
        self.btn_despues.clicked.connect(self.reject)
        fila_botones.addWidget(self.btn_despues)

        self.btn_actualizar = QPushButton("Actualizar ahora")
        self.btn_actualizar.setObjectName("btnActualizar")
        self.btn_actualizar.clicked.connect(self._iniciar_descarga)
        fila_botones.addWidget(self.btn_actualizar)

        lay.addLayout(fila_botones)

    def _iniciar_descarga(self):
        self.lbl_error.setVisible(False)
        self.btn_actualizar.setEnabled(False)
        self.btn_despues.setEnabled(False)
        self.barra.setVisible(True)
        self.barra.setValue(0)

        if ES_COMPILADO:
            archivos = [(INSTALADOR_NOMBRE, f"{GITHUB_RELEASES}/{INSTALADOR_NOMBRE}")]
        else:
            archivos = [(archivo, f"{GITHUB_RAW}/{archivo}") for archivo in self.info_remota.get('archivos', [])]

        self._hilo = HiloDescargaActualizacion(archivos, self)
        self._hilo.progreso.connect(self.barra.setValue)
        self._hilo.terminado.connect(self._on_descarga_terminada)
        self._hilo.start()

    def _on_descarga_terminada(self, exito, error):
        if not exito:
            self.lbl_error.setText("No se pudo descargar la actualización. Comprueba tu conexión.")
            self.lbl_error.setVisible(True)
            self.btn_actualizar.setEnabled(True)
            self.btn_despues.setEnabled(True)
            self.barra.setVisible(False)
            return

        if ES_COMPILADO:
            _lanzar_instalador()
        else:
            lanzar_update_helper()
        self.accept()
        sys.exit(0)


def lanzar_update_helper():
    """Modo desarrollo: lanza update_helper.py, que espera a que SimpleHub
    se cierre, instala los .py descargados y reinicia la app."""
    helper = os.path.join(BASE_DIR, 'update_helper.py')
    subprocess.Popen([sys.executable, helper], cwd=BASE_DIR)


def _lanzar_instalador():
    """Modo compilado: corre el instalador descargado (SimpleSetup.exe) en
    silencioso sobre la misma carpeta de instalación, y relanza SimpleHub al
    terminar. Se hace desde un .bat temporal (no directamente) por dos
    motivos: dar un par de segundos para que SimpleHub libere su propio exe
    antes de que el instalador intente reemplazarlo, y porque el instalador
    en /verysilent no relanza nada (su [Run] postinstall tiene skipifsilent,
    pensado para una instalación manual interactiva)."""
    nuevo = os.path.join(BASE_DIR, f'{INSTALADOR_NOMBRE}.new')
    instalador = os.path.join(BASE_DIR, INSTALADOR_NOMBRE)
    try:
        if os.path.exists(instalador):
            os.remove(instalador)
        os.rename(nuevo, instalador)
    except OSError:
        return

    simplehub = os.path.join(BASE_DIR, 'SimpleHub.exe')
    bat_content = (
        'timeout /t 2 /nobreak >nul\r\n'
        f'"{instalador}" /verysilent /norestart /suppressmsgboxes\r\n'
        f'start "" "{simplehub}"\r\n'
        'del "%~f0"\r\n'
    )
    bat_path = os.path.join(BASE_DIR, '_instalar_actualizacion.bat')
    try:
        with open(bat_path, 'w', encoding='utf-8') as f:
            f.write(bat_content)
        subprocess.Popen(bat_path, shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
    except OSError:
        pass


def mostrar_dialogo_actualizacion(info_remota, accent='#7c3aed', parent=None, al_cerrar=None):
    """Muestra el diálogo de actualización, sin bloquear, y evita abrir uno
    nuevo si ya hay otro abierto (ver DialogoActualizacion._dialog_activo).
    Si el usuario confirma y la descarga termina bien, el propio diálogo
    sale de la app (sys.exit). `al_cerrar`, si se da, se llama cuando el
    diálogo se cierra (aceptado o descartado)."""
    if DialogoActualizacion._dialog_activo is not None:
        return

    dlg = DialogoActualizacion(info_remota, accent, parent)
    DialogoActualizacion._dialog_activo = dlg

    def _liberar():
        DialogoActualizacion._dialog_activo = None
        if al_cerrar:
            al_cerrar()

    dlg.finished.connect(_liberar)
    dlg.setModal(True)
    dlg.show()
