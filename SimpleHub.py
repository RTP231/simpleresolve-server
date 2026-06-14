import sys
import os
import json
import base64
import subprocess

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QMessageBox, QDialog,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont

from config import SERVER_URL
from security import create_session
from login import LoginDialog
import auth_manager

try:
    import keyring
except ImportError:
    keyring = None


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_SERVICE_NAME = "SimpleHub"

_C_BG = '#0d0d0d'
_C_PANEL = '#15131f'
_C_BORDER = '#2a2840'
_C_TEXT = '#eaeaf5'
_C_TEXT_SEC = '#9898b8'
_C_ACCENT = '#7c6fff'


# ----------------------------------------------------------------------
# Manejo de sesión: el token se guarda con keyring (si está disponible) y
# también con auth_manager (archivo en %APPDATA%) para que Simple Resolver
# y Simple Downloader -que ya leen ese archivo- reconozcan la sesión.
# ----------------------------------------------------------------------
def _guardar_token(token):
    auth_manager.guardar_token(token)
    auth_manager.limpiar_marca_sesion_invalida()
    if keyring is not None:
        try:
            keyring.set_password(_SERVICE_NAME, "token", token)
        except Exception:
            pass


def _cargar_token():
    if keyring is not None:
        try:
            token = keyring.get_password(_SERVICE_NAME, "token")
            if token:
                return token
        except Exception:
            pass
    return auth_manager.cargar_token()


def _borrar_token_local():
    auth_manager.borrar_token()
    if keyring is not None:
        try:
            keyring.delete_password(_SERVICE_NAME, "token")
        except Exception:
            pass


def _decodificar_email(token):
    """Lee el campo 'email' (o 'sub') del payload del JWT sin verificar
    la firma; solo se usa para mostrar quién inició sesión."""
    try:
        payload = token.split('.')[1]
        payload += '=' * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload))
        return data.get('email') or data.get('sub') or ''
    except Exception:
        return ''


def _verificar_token_sync(token):
    if not token:
        return False, ''
    try:
        r = create_session().get(
            f"{SERVER_URL}/auth/verify",
            headers={'Authorization': f'Bearer {token}'},
            timeout=10,
        )
        if r.status_code == 200:
            return True, ''
        if r.status_code == 403:
            return False, 'Tu cuenta ha sido desactivada.'
        return False, 'Tu sesión ha expirado, vuelve a iniciar sesión.'
    except Exception:
        return False, 'Sin conexión con el servidor.'


class HiloVerificarSesion(QThread):
    resultado = pyqtSignal(bool, str)

    def __init__(self, token, parent=None):
        super().__init__(parent)
        self.token = token

    def run(self):
        valido, mensaje = _verificar_token_sync(self.token)
        self.resultado.emit(valido, mensaje)


class AppCard(QFrame):
    abrir = pyqtSignal()

    def __init__(self, titulo, descripcion, version, emoji, parent=None):
        super().__init__(parent)
        self.setObjectName("appCard")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(6)

        top = QHBoxLayout()
        lbl_emoji = QLabel(emoji)
        lbl_emoji.setStyleSheet("font-size: 28px; background: transparent;")
        top.addWidget(lbl_emoji)
        top.addStretch()
        self.lbl_estado = QLabel("✓ Actualizado")
        self.lbl_estado.setStyleSheet("color: #22c55e; font-size: 10px; background: transparent;")
        top.addWidget(self.lbl_estado)
        lay.addLayout(top)

        lbl_titulo = QLabel(titulo)
        lbl_titulo.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        lbl_titulo.setStyleSheet(f"color: {_C_TEXT}; background: transparent;")
        lay.addWidget(lbl_titulo)

        lbl_desc = QLabel(descripcion)
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet(f"color: {_C_TEXT_SEC}; font-size: 10px; background: transparent;")
        lay.addWidget(lbl_desc)

        lbl_version = QLabel(f"Versión {version}")
        lbl_version.setStyleSheet(f"color: {_C_TEXT_SEC}; font-size: 9px; background: transparent;")
        lay.addWidget(lbl_version)

        lay.addStretch()

        self.btn_abrir = QPushButton("Abrir")
        self.btn_abrir.setObjectName("btnAbrir")
        self.btn_abrir.clicked.connect(self.abrir.emit)
        lay.addWidget(self.btn_abrir)

        self.setStyleSheet(f"""
            QFrame#appCard {{
                background-color: {_C_PANEL};
                border: 1px solid {_C_BORDER};
                border-radius: 12px;
            }}
            QPushButton#btnAbrir {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #7c6fff, stop:1 #5a4fcf);
                color: white;
                border: none;
                border-radius: 7px;
                padding: 8px;
                font-weight: bold;
            }}
            QPushButton#btnAbrir:disabled {{
                background: {_C_BORDER};
                color: #55547a;
            }}
        """)


class SimpleHub(QWidget):
    def __init__(self):
        super().__init__()
        self.token = None
        self._hilo_verificar = None
        self._hilo_abrir = None

        self.setWindowTitle("SimpleHub")
        self.setMinimumSize(480, 360)
        self.setStyleSheet(
            f"QWidget {{ background-color: {_C_BG}; color: {_C_TEXT}; "
            "font-family: 'Segoe UI', sans-serif; }"
        )

        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(24, 24, 24, 24)
        self._lay.setSpacing(16)

        self._timer_sesion = QTimer(self)
        self._timer_sesion.setInterval(30 * 60 * 1000)
        self._timer_sesion.timeout.connect(self._verificar_sesion_periodica)

        self._iniciar()

    # ------------------------------------------------------------------
    # Sesión
    # ------------------------------------------------------------------
    def _iniciar(self):
        self.token = _cargar_token()
        if self.token:
            valido, mensaje = _verificar_token_sync(self.token)
            if valido:
                auth_manager.limpiar_marca_sesion_invalida()
                self._mostrar_principal()
                self._timer_sesion.start()
                return
            _borrar_token_local()
            self.token = None
            if mensaje:
                QMessageBox.warning(self, "Sesión cerrada", mensaje)
        self._mostrar_login()

    def _mostrar_login(self):
        self._limpiar_layout()
        dlg = LoginDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.token:
            self.token = dlg.token
            _guardar_token(self.token)
            self._mostrar_principal()
            self._timer_sesion.start()
        else:
            self.token = None

    def _verificar_sesion_periodica(self):
        if self._hilo_verificar and self._hilo_verificar.isRunning():
            return
        self._hilo_verificar = HiloVerificarSesion(self.token, self)
        self._hilo_verificar.resultado.connect(self._on_verificacion_periodica)
        self._hilo_verificar.start()

    def _on_verificacion_periodica(self, valido, mensaje):
        if valido:
            return
        self._cerrar_sesion(mensaje or "Tu sesión ha expirado.")

    def _cerrar_sesion(self, mensaje=None):
        self._timer_sesion.stop()
        _borrar_token_local()
        # Avisa a Simple Resolver / Simple Downloader (si están abiertos)
        # que deben cerrar su sesión también.
        auth_manager.marcar_sesion_invalida()
        self.token = None
        if mensaje:
            QMessageBox.warning(self, "Sesión cerrada", mensaje)
        self._mostrar_login()
        if not self.token:
            self.close()

    # ------------------------------------------------------------------
    # Interfaz
    # ------------------------------------------------------------------
    def _limpiar_layout(self):
        while self._lay.count():
            item = self._lay.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
            layout = item.layout()
            if layout is not None:
                self._limpiar_sublayout(layout)

    def _limpiar_sublayout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
            sublayout = item.layout()
            if sublayout is not None:
                self._limpiar_sublayout(sublayout)

    def _mostrar_principal(self):
        self._limpiar_layout()

        header = QHBoxLayout()

        avatar = QLabel(self._inicial_usuario())
        avatar.setFixedSize(40, 40)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setStyleSheet(
            f"background-color: {_C_ACCENT}; color: white; border-radius: 20px; "
            "font-weight: bold; font-size: 16px;"
        )
        header.addWidget(avatar)

        info = QVBoxLayout()
        info.setSpacing(0)
        lbl_titulo = QLabel("SimpleHub")
        lbl_titulo.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        lbl_titulo.setStyleSheet("background: transparent;")
        info.addWidget(lbl_titulo)
        lbl_usuario = QLabel(_decodificar_email(self.token) or "Usuario")
        lbl_usuario.setStyleSheet(f"color: {_C_TEXT_SEC}; font-size: 10px; background: transparent;")
        info.addWidget(lbl_usuario)
        header.addLayout(info)
        header.addStretch()

        btn_logout = QPushButton("Cerrar sesión")
        btn_logout.setStyleSheet(
            f"background-color: transparent; color: {_C_TEXT_SEC}; "
            f"border: 1px solid {_C_BORDER}; border-radius: 7px; padding: 6px 12px;"
        )
        btn_logout.clicked.connect(lambda: self._cerrar_sesion())
        header.addWidget(btn_logout)

        self._lay.addLayout(header)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(16)

        self.card_resolver = AppCard(
            "Simple Resolver",
            "Asistente de respuestas con IA mediante captura de pantalla.",
            "2.0", "🧠",
        )
        self.card_resolver.abrir.connect(lambda: self._abrir_app('resolver'))
        cards_row.addWidget(self.card_resolver)

        self.card_downloader = AppCard(
            "Simple Downloader",
            "Navegador con descargador de videos integrado.",
            "2.0", "⬇️",
        )
        self.card_downloader.abrir.connect(lambda: self._abrir_app('downloader'))
        cards_row.addWidget(self.card_downloader)

        self._lay.addLayout(cards_row)
        self._lay.addStretch()

    def _inicial_usuario(self):
        email = _decodificar_email(self.token)
        return (email[:1] or "?").upper()

    # ------------------------------------------------------------------
    # Apertura de apps
    # ------------------------------------------------------------------
    def _abrir_app(self, app_key):
        card = self.card_resolver if app_key == 'resolver' else self.card_downloader
        card.btn_abrir.setEnabled(False)
        card.btn_abrir.setText("Verificando...")

        hilo = HiloVerificarSesion(self.token, self)
        hilo.resultado.connect(
            lambda valido, msg: self._on_verificacion_abrir(valido, msg, app_key, card)
        )
        self._hilo_abrir = hilo
        hilo.start()

    def _on_verificacion_abrir(self, valido, mensaje, app_key, card):
        card.btn_abrir.setEnabled(True)
        card.btn_abrir.setText("Abrir")
        if not valido:
            self._cerrar_sesion(mensaje or "Tu sesión ha expirado.")
            return

        if app_key == 'resolver':
            script = os.path.join(BASE_DIR, 'main.py')
        else:
            script = os.path.join(BASE_DIR, '_run_downloader.py')
        subprocess.Popen([sys.executable, script, '--token', self.token], cwd=BASE_DIR)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    hub = SimpleHub()
    if not hub.token:
        sys.exit(0)
    hub.show()
    sys.exit(app.exec())
