"""Sistema de auto-actualización de SimpleHub.

Comprueba si hay una versión más nueva publicada en GitHub (rama "cliente"),
y si el usuario lo confirma descarga los archivos nuevos y relanza la app
mediante update_helper para poder reemplazar incluso los archivos que están
en uso (como el propio SimpleHub).

En modo desarrollo (ejecutado como .py) se descargan los .py listados en
version.json desde GITHUB_RAW. En modo compilado (.exe, PyInstaller) se
descargan los .exe de SimpleHub/SimpleResolver/SimpleDownloader desde la
última GitHub Release.
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

from integrity import ARCHIVOS_CRITICOS_EXE


ES_COMPILADO = getattr(sys, 'frozen', False)

if ES_COMPILADO:
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

GITHUB_RAW = "https://raw.githubusercontent.com/RTP231/simpleresolve-server/cliente"
GITHUB_RELEASES = "https://github.com/RTP231/simpleresolve-server/releases/latest/download"
VERSION_FILE = os.path.join(BASE_DIR, 'version.json')

# Exes que se reemplazan en una actualización compilada.
ARCHIVOS_EXE = ARCHIVOS_CRITICOS_EXE

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
            archivos = [(nombre, f"{GITHUB_RELEASES}/{nombre}") for nombre in ARCHIVOS_EXE]
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

        lanzar_update_helper()
        self.accept()
        sys.exit(0)


def lanzar_update_helper():
    """Lanza el update_helper (que espera a que SimpleHub se cierre, instala
    los archivos .new y reinicia la app) y deja correr el proceso aparte."""
    if ES_COMPILADO:
        helper = os.path.join(BASE_DIR, 'update_helper.exe')
        subprocess.Popen([helper], cwd=BASE_DIR)
    else:
        helper = os.path.join(BASE_DIR, 'update_helper.py')
        subprocess.Popen([sys.executable, helper], cwd=BASE_DIR)


def mostrar_dialogo_actualizacion(info_remota, accent='#7c3aed', parent=None):
    """Muestra el diálogo de actualización. Devuelve True si el usuario
    confirmó (en cuyo caso la app ya está saliendo), False si lo descartó."""
    dlg = DialogoActualizacion(info_remota, accent, parent)
    resultado = dlg.exec()
    return resultado == QDialog.DialogCode.Accepted
