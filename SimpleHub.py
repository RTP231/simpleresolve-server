import anti_debug  # noqa: F401  (verifica al importar; debe ir primero)

import sys
import os
import json
import base64
import subprocess

import requests
import integrity
integrity.verificar_integridad_o_salir()

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QMessageBox, QLineEdit, QProgressBar, QDialog, QColorDialog,
    QGraphicsDropShadowEffect,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QPropertyAnimation, QEasingCurve, QPoint
from PyQt6.QtGui import QFont, QColor

from config import SERVER_URL
from security import create_session
from login import HiloLogin
from fondo_animado import AnimacionFondoWidget, FondoVideoWidget, SeccionFondoAnimado
import auth_manager
import personalizacion
import actualizador

try:
    import keyring
except ImportError:
    keyring = None


if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_SERVICE_NAME = "SimpleHub"

_C_BG = '#0d0d0d'
_C_CARD = '#1a1a1a'
_C_BORDER = '#2a2a2a'
_C_TEXT = '#eaeaf5'
_C_TEXT_SEC = '#888888'
_C_ACCENT_DEFAULT = '#7c3aed'

# Compatibilidad con nombres usados por el panel de login.
_C_PANEL = _C_CARD

PRESETS_ACCENT = ['#7c3aed', '#7c6fff', '#22c55e', '#eab308', '#ef4444', '#06b6d4']


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


class HiloBuscarActualizacion(QThread):
    resultado = pyqtSignal(object)  # None o dict con info remota

    def run(self):
        self.resultado.emit(actualizador.verificar_actualizacion())


class AppCard(QFrame):
    abrir = pyqtSignal()

    def __init__(self, titulo, descripcion, emoji, accent, actualizado=True, parent=None):
        super().__init__(parent)
        self.setObjectName("appCard")
        self._accent = accent

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(8)

        lbl_emoji = QLabel(emoji)
        lbl_emoji.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_emoji.setStyleSheet("font-size: 40px; background: transparent;")
        lay.addWidget(lbl_emoji)

        lbl_titulo = QLabel(titulo)
        lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_titulo.setStyleSheet(
            f"color: {_C_TEXT}; font-size: 18px; font-weight: bold; background: transparent;"
        )
        lay.addWidget(lbl_titulo)

        lbl_desc = QLabel(descripcion)
        lbl_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet(f"color: {_C_TEXT_SEC}; font-size: 10px; background: transparent;")
        lay.addWidget(lbl_desc)

        if actualizado:
            self.lbl_estado = QLabel("✓ Actualizado")
            self.lbl_estado.setStyleSheet(
                "color: #22c55e; background: rgba(34,197,94,0.12); "
                "border-radius: 8px; padding: 2px 10px; font-size: 9px;"
            )
        else:
            self.lbl_estado = QLabel("⬆ Update disponible")
            self.lbl_estado.setStyleSheet(
                "color: #eab308; background: rgba(234,179,8,0.12); "
                "border-radius: 8px; padding: 2px 10px; font-size: 9px;"
            )
        self.lbl_estado.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fila_estado = QHBoxLayout()
        fila_estado.addStretch()
        fila_estado.addWidget(self.lbl_estado)
        fila_estado.addStretch()
        lay.addLayout(fila_estado)

        lay.addStretch()

        self.btn_abrir = QPushButton("Abrir")
        self.btn_abrir.setObjectName("btnAbrir")
        self.btn_abrir.clicked.connect(self.abrir.emit)
        lay.addWidget(self.btn_abrir)

        sombra = QGraphicsDropShadowEffect(self)
        sombra.setBlurRadius(24)
        sombra.setOffset(0, 6)
        sombra.setColor(QColor(0, 0, 0, 160))
        self.setGraphicsEffect(sombra)

        self._aplicar_estilo()

    def _aplicar_estilo(self):
        accent_hover = QColor(self._accent).lighter(120).name()
        self.setStyleSheet(f"""
            QFrame#appCard {{
                background-color: {_C_CARD};
                border: 0.5px solid {_C_BORDER};
                border-radius: 12px;
            }}
            QPushButton#btnAbrir {{
                background-color: {self._accent};
                color: white;
                border: none;
                border-radius: 7px;
                padding: 9px;
                font-weight: bold;
            }}
            QPushButton#btnAbrir:hover {{
                background-color: {accent_hover};
            }}
            QPushButton#btnAbrir:disabled {{
                background-color: {_C_BORDER};
                color: #666666;
            }}
        """)

    def set_accent(self, accent):
        self._accent = accent
        self._aplicar_estilo()


class LoginPanel(QFrame):
    """Formulario de login embebido (sin red al construirse), con el mismo
    estilo glassmorphism oscuro de Simple Resolver. La verificación con el
    servidor corre en un QThread (HiloLogin) para no bloquear la UI."""

    login_exitoso = pyqtSignal(str)

    def __init__(self, accent=_C_ACCENT_DEFAULT, parent=None):
        super().__init__(parent)
        self.setObjectName("loginPanel")
        self._hilo = None
        self._accent = accent

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addStretch()

        card = QFrame()
        card.setObjectName("loginCard")
        card.setFixedWidth(280)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(10)

        lbl_titulo = QLabel("SimpleHub")
        lbl_titulo.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        lbl_titulo.setStyleSheet(f"color: {_C_TEXT}; background: transparent;")
        lay.addWidget(lbl_titulo)

        lbl_sub = QLabel("Inicia sesión para continuar")
        lbl_sub.setStyleSheet(f"color: {_C_TEXT_SEC}; font-size: 10px; background: transparent;")
        lay.addWidget(lbl_sub)

        lay.addSpacing(4)

        lbl_email = QLabel("Email")
        lbl_email.setStyleSheet(f"color: {_C_TEXT_SEC}; font-size: 10px; background: transparent;")
        lay.addWidget(lbl_email)

        self.inp_email = QLineEdit()
        self.inp_email.setPlaceholderText("correo@ejemplo.com")
        self.inp_email.setObjectName("inputField")
        lay.addWidget(self.inp_email)

        lbl_pass = QLabel("Contraseña")
        lbl_pass.setStyleSheet(f"color: {_C_TEXT_SEC}; font-size: 10px; background: transparent;")
        lay.addWidget(lbl_pass)

        self.inp_pass = QLineEdit()
        self.inp_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.inp_pass.setPlaceholderText("••••••••")
        self.inp_pass.setObjectName("inputField")
        self.inp_pass.returnPressed.connect(self._on_submit)
        lay.addWidget(self.inp_pass)

        self.lbl_error = QLabel("")
        self.lbl_error.setStyleSheet("color: #ff6b8a; font-size: 10px; background: transparent;")
        self.lbl_error.setWordWrap(True)
        self.lbl_error.setVisible(False)
        lay.addWidget(self.lbl_error)

        self.btn_login = QPushButton("Iniciar sesión")
        self.btn_login.setObjectName("btnSubmit")
        self.btn_login.clicked.connect(self._on_submit)
        lay.addWidget(self.btn_login)

        self._card = card
        self._aplicar_estilo()

        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(card)
        row.addStretch()
        outer.addLayout(row)
        outer.addStretch()

    def _aplicar_estilo(self):
        accent_hover = QColor(self._accent).lighter(120).name()
        self._card.setStyleSheet(f"""
            QFrame#loginCard {{
                background-color: {_C_CARD};
                border: 0.5px solid {_C_BORDER};
                border-radius: 12px;
            }}
            QLineEdit#inputField {{
                background: rgba(255,255,255,0.07);
                border: 1px solid rgba(124,111,255,0.35);
                border-radius: 7px;
                padding: 6px 10px;
                color: {_C_TEXT};
                font-size: 12px;
                selection-background-color: rgba(124,111,255,0.4);
            }}
            QLineEdit#inputField:focus {{
                border: 1px solid {self._accent};
                background: rgba(255,255,255,0.1);
            }}
            QPushButton#btnSubmit {{
                background-color: {self._accent};
                color: white;
                border: none;
                border-radius: 7px;
                padding: 8px;
                font-weight: bold;
                font-size: 12px;
            }}
            QPushButton#btnSubmit:hover {{
                background-color: {accent_hover};
            }}
            QPushButton#btnSubmit:disabled {{
                background-color: {_C_BORDER};
                color: #55547a;
            }}
        """)

    def _on_submit(self):
        email = self.inp_email.text().strip()
        password = self.inp_pass.text()

        if not (email and password):
            self._set_error("Completa todos los campos.")
            return

        bloqueado, restante = auth_manager.verificar_bloqueo()
        if bloqueado:
            minutos = max(1, restante // 60)
            self._set_error(f"Demasiados intentos fallidos. Intenta de nuevo en {minutos} min.")
            return

        self._set_error('')
        self.btn_login.setEnabled(False)
        self.btn_login.setText("Conectando...")

        self._hilo = HiloLogin(email, password)
        self._hilo.terminado.connect(self._on_done)
        self._hilo.start()

    def _on_done(self, exito, token, error):
        self.btn_login.setEnabled(True)
        self.btn_login.setText("Iniciar sesión")
        if exito:
            auth_manager.registrar_intento_exitoso()
            self.login_exitoso.emit(token)
            return
        auth_manager.registrar_intento_fallido()
        self._set_error(error)

    def _set_error(self, msg):
        if msg:
            self.lbl_error.setText(msg)
            self.lbl_error.setVisible(True)
            return
        self.lbl_error.setVisible(False)


class PersonalizacionPanel(QDialog):
    """Panel ligero de personalización: color de acento y fondo animado.
    Comparte el archivo de configuración (personalizacion.json) con Simple
    Resolver, así ambas apps usan el mismo tema."""

    def __init__(self, ventana, parent=None):
        super().__init__(parent)
        self.ventana = ventana
        self.setWindowTitle("Personalización")
        self.setFixedWidth(280)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {_C_CARD};
                border: 0.5px solid {_C_BORDER};
                border-radius: 10px;
            }}
            QLabel {{ color: {_C_TEXT_SEC}; }}
            QPushButton#btnHeader {{
                background: transparent;
                border: none;
                color: {_C_TEXT_SEC};
                font-size: 12px;
                border-radius: 5px;
                padding: 4px;
            }}
            QPushButton#btnHeader:hover {{
                background: rgba(255,255,255,0.08);
                color: {_C_TEXT};
            }}
            QPushButton#btnHeader:checked {{
                background: rgba(124,58,237,0.25);
                color: {_C_TEXT};
            }}
            QPushButton {{
                background-color: {_C_BORDER};
                color: {_C_TEXT};
                border: none;
                border-radius: 6px;
                padding: 6px;
            }}
            QPushButton:hover {{
                background-color: #3a3a3a;
            }}
            QSlider::groove:horizontal {{
                background-color: {_C_BORDER};
                height: 4px;
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background-color: {_C_ACCENT_DEFAULT};
                width: 14px;
                height: 14px;
                margin: -5px 0;
                border-radius: 7px;
            }}
            QSlider::sub-page:horizontal {{
                background-color: {_C_ACCENT_DEFAULT};
                border-radius: 2px;
            }}
        """)

        lay = QVBoxLayout(self)
        lay.setSpacing(8)

        lay.addWidget(self._titulo("Color de acento"))
        fila = QHBoxLayout()
        for color in PRESETS_ACCENT:
            fila.addWidget(self._swatch(color))
        lay.addLayout(fila)

        btn_custom = QPushButton("Personalizado...")
        btn_custom.clicked.connect(self._elegir_color_custom)
        lay.addWidget(btn_custom)

        self.seccion_fondo = SeccionFondoAnimado(ventana, ventana.config_personalizacion)
        lay.addWidget(self.seccion_fondo)

        btn_restaurar = QPushButton("Restaurar valores predeterminados")
        btn_restaurar.clicked.connect(self._restaurar)
        lay.addWidget(btn_restaurar)

    def _titulo(self, texto):
        l = QLabel(texto)
        l.setStyleSheet(f"font-weight: bold; color: {_C_TEXT};")
        return l

    def _swatch(self, color):
        b = QPushButton()
        b.setFixedSize(28, 28)
        b.setStyleSheet(f"background-color: {color}; border-radius: 4px; border: 1px solid rgba(128,128,128,0.5);")
        b.clicked.connect(lambda _checked=False, c=color: self.ventana.set_color_botones(c))
        return b

    def _elegir_color_custom(self):
        actual = self.ventana.config_personalizacion.get('color_botones') or _C_ACCENT_DEFAULT
        color = QColorDialog.getColor(QColor(actual), self, "Color de acento")
        if color.isValid():
            self.ventana.set_color_botones(color.name())

    def _restaurar(self):
        self.ventana.restaurar_personalizacion_defaults()
        self.seccion_fondo.actualizar(self.ventana.config_personalizacion)


class HiloDescargaExe(QThread):
    """Descarga un único exe con progreso por chunk."""
    progreso = pyqtSignal(int, str)   # (porcentaje, "X MB / Y MB")
    terminado = pyqtSignal(bool, str)

    def __init__(self, url, destino_tmp, parent=None):
        super().__init__(parent)
        self.url = url
        self.destino_tmp = destino_tmp

    def run(self):
        try:
            r = requests.get(self.url, stream=True, timeout=60)
            if r.status_code != 200:
                self.terminado.emit(False, f"HTTP {r.status_code}")
                return
            total = int(r.headers.get('content-length', 0))
            descargado = 0
            with open(self.destino_tmp, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        descargado += len(chunk)
                        if total > 0:
                            pct = int(descargado / total * 100)
                            mb_d = descargado // (1024 * 1024)
                            mb_t = total // (1024 * 1024)
                            self.progreso.emit(pct, f"{mb_d} MB / {mb_t} MB")
            self.terminado.emit(True, '')
        except Exception as e:
            self.terminado.emit(False, str(e))


class DialogoDescargaExe(QDialog):
    """Descarga un .exe desde GitHub Releases con barra de progreso.
    Se cierra automáticamente al terminar (accept = éxito, reject = error).
    No se puede cerrar manualmente mientras descarga."""

    def __init__(self, nombre_exe, accent=_C_ACCENT_DEFAULT, parent=None):
        super().__init__(parent)
        self.nombre_exe = nombre_exe
        self._error_msg = ''
        self._hilo = None

        self.setWindowTitle("Descargando componente")
        self.setFixedWidth(340)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
        )
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {_C_CARD};
                border: 0.5px solid {_C_BORDER};
                border-radius: 10px;
            }}
            QLabel {{ color: {_C_TEXT}; background: transparent; }}
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
        lay.setContentsMargins(20, 20, 20, 20)

        lbl_titulo = QLabel(f"Descargando {nombre_exe}")
        lbl_titulo.setStyleSheet("font-size: 13px; font-weight: bold;")
        lay.addWidget(lbl_titulo)

        lbl_desc = QLabel(
            "Este componente se descarga automáticamente\n"
            "la primera vez. Por favor, espere..."
        )
        lbl_desc.setStyleSheet(f"color: {_C_TEXT_SEC}; font-size: 11px;")
        lay.addWidget(lbl_desc)

        self.barra = QProgressBar()
        self.barra.setRange(0, 100)
        self.barra.setValue(0)
        lay.addWidget(self.barra)

        self.lbl_estado = QLabel("Iniciando descarga...")
        self.lbl_estado.setStyleSheet(f"color: {_C_TEXT_SEC}; font-size: 10px;")
        lay.addWidget(self.lbl_estado)

        QTimer.singleShot(0, self._iniciar)

    def _iniciar(self):
        url = f"{actualizador.GITHUB_RELEASES}/{self.nombre_exe}"
        destino_tmp = os.path.join(actualizador.BASE_DIR, f"{self.nombre_exe}.new")
        self._hilo = HiloDescargaExe(url, destino_tmp, self)
        self._hilo.progreso.connect(self._on_progreso)
        self._hilo.terminado.connect(self._on_terminado)
        self._hilo.start()

    def _on_progreso(self, pct, texto):
        self.barra.setValue(pct)
        self.lbl_estado.setText(texto)

    def _on_terminado(self, exito, error):
        if not exito:
            self._error_msg = error
            self.reject()
            return

        nuevo = os.path.join(actualizador.BASE_DIR, f"{self.nombre_exe}.new")
        destino = os.path.join(actualizador.BASE_DIR, self.nombre_exe)
        try:
            if os.path.exists(destino):
                os.remove(destino)
            os.rename(nuevo, destino)
            self.lbl_estado.setText("Completado.")
            self.accept()
        except OSError as e:
            self._error_msg = str(e)
            self.reject()

    def closeEvent(self, event):
        if self._hilo and self._hilo.isRunning():
            event.ignore()
        else:
            super().closeEvent(event)


class SimpleHub(QWidget):
    ANCHO = 600
    ALTO = 400

    def __init__(self):
        super().__init__()
        self.token = None
        self._hilo_verificar = None
        self._hilo_abrir = None
        self._fade_hecho = False
        self._anims = []

        self.config_personalizacion = personalizacion.cargar_config()
        self._accent = self.config_personalizacion.get('color_botones') or _C_ACCENT_DEFAULT

        self.setWindowTitle("SimpleHub")
        self.setMinimumSize(self.ANCHO, self.ALTO)

        self.setStyleSheet(
            f"QWidget {{ color: {_C_TEXT}; font-family: 'Segoe UI', sans-serif; }}"
            f"#simpleHubRoot {{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            f" stop:0 #111111, stop:1 #0a0a0a); }}"
        )
        self.setObjectName("simpleHubRoot")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        # Fondo animado liviano (mismo módulo que Simple Resolver), siempre
        # en modo rendimiento (<=24fps aprox.) para no afectar el resto de la app.
        self.fondo_animado = AnimacionFondoWidget(self)
        self.fondo_video = FondoVideoWidget(self)
        self.fondo_animado.lower()
        self.fondo_video.lower()
        self._aplicar_fondo_animado()

        self.resize(self.ANCHO, self.ALTO)
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.ANCHO) // 2
        y = (screen.height() - self.ALTO) // 2
        self.move(x, y)

        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(24, 24, 24, 24)
        self._lay.setSpacing(16)

        self._timer_sesion = QTimer(self)
        self._timer_sesion.setInterval(30 * 60 * 1000)
        self._timer_sesion.timeout.connect(self._verificar_sesion_periodica)

        self._hilo_actualizacion = None
        self._btn_actualizar = None
        # Verificar actualizaciones 5 s después de arrancar para dar tiempo a
        # que la CDN de GitHub actualice el version.json cacheado.
        QTimer.singleShot(5000, self._verificar_actualizacion_silenciosa)

        # Fade-in de 300ms al mostrar la ventana.
        self.setWindowOpacity(0.0)

        # Sin token guardado -> login inmediato, sin esperar nada.
        # Con token guardado -> pantalla "Verificando sesión..." mientras
        # la verificación (red) corre en un QThread después de mostrar la ventana.
        self.token = _cargar_token()
        if self.token:
            self._mostrar_verificando()
            QTimer.singleShot(0, self._verificar_inicial)
        else:
            self._mostrar_login()

    def showEvent(self, event):
        super().showEvent(event)
        if not self._fade_hecho:
            self._fade_hecho = True
            anim = QPropertyAnimation(self, b"windowOpacity", self)
            anim.setDuration(300)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.start()
            self._anims.append(anim)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        r = self.rect()
        self.fondo_animado.setGeometry(r)
        self.fondo_video.setGeometry(r)
        self.fondo_animado.lower()
        self.fondo_video.lower()

    # ------------------------------------------------------------------
    # Personalización (compartida con Simple Resolver vía personalizacion.json)
    # ------------------------------------------------------------------
    def _aplicar_fondo_animado(self):
        cfg = self.config_personalizacion
        self.fondo_animado.set_color(self._accent)
        self.fondo_animado.set_velocidad(cfg.get('fondo_animado_velocidad', 'normal'))
        self.fondo_animado.set_opacidad(cfg.get('fondo_animado_opacidad', 30))
        # SimpleHub: siempre en modo rendimiento (intervalo mayor -> <=24fps).
        self.fondo_animado.set_rendimiento(True)
        self.fondo_video.set_opacidad(cfg.get('fondo_video_opacidad', 40))
        self.fondo_video.set_calidad(cfg.get('fondo_video_calidad', 'alta'))
        self.fondo_video.set_rendimiento(True)

        activo = cfg.get('fondo_animado_activo', False)
        video = cfg.get('video_fondo')
        if activo and video:
            self.fondo_animado.set_activo(False)
            self.fondo_video.set_video(video)
            return
        if activo:
            self.fondo_video.set_video(None)
            self.fondo_animado.set_tipo(cfg.get('fondo_animado_tipo', 'particulas'))
            self.fondo_animado.set_activo(True)
            return
        self.fondo_animado.set_activo(False)
        self.fondo_video.set_video(None)

    def set_color_botones(self, color_hex):
        self.config_personalizacion['color_botones'] = color_hex
        personalizacion.guardar_config(self.config_personalizacion)
        self._accent = color_hex or _C_ACCENT_DEFAULT
        self._aplicar_fondo_animado()
        self._refrescar_vista()

    def set_fondo_animado_activo(self, activo):
        self.config_personalizacion['fondo_animado_activo'] = activo
        personalizacion.guardar_config(self.config_personalizacion)
        self._aplicar_fondo_animado()

    def set_fondo_animado_tipo(self, tipo):
        self.config_personalizacion['fondo_animado_tipo'] = tipo
        personalizacion.guardar_config(self.config_personalizacion)
        self._aplicar_fondo_animado()

    def set_fondo_animado_velocidad(self, velocidad):
        self.config_personalizacion['fondo_animado_velocidad'] = velocidad
        personalizacion.guardar_config(self.config_personalizacion)
        self._aplicar_fondo_animado()

    def set_fondo_animado_opacidad(self, valor):
        self.config_personalizacion['fondo_animado_opacidad'] = valor
        personalizacion.guardar_config(self.config_personalizacion)
        self._aplicar_fondo_animado()

    def set_fondo_animado_rendimiento(self, activo):
        self.config_personalizacion['fondo_animado_rendimiento'] = activo
        personalizacion.guardar_config(self.config_personalizacion)
        self._aplicar_fondo_animado()

    def set_video_fondo(self, ruta):
        self.config_personalizacion['video_fondo'] = ruta
        personalizacion.guardar_config(self.config_personalizacion)
        self._aplicar_fondo_animado()

    def set_fondo_video_opacidad(self, valor):
        self.config_personalizacion['fondo_video_opacidad'] = valor
        personalizacion.guardar_config(self.config_personalizacion)
        self.fondo_video.set_opacidad(valor)

    def set_fondo_video_calidad(self, calidad):
        self.config_personalizacion['fondo_video_calidad'] = calidad
        personalizacion.guardar_config(self.config_personalizacion)
        self.fondo_video.set_calidad(calidad)

    def set_fondo_panel_opacidad(self, valor):
        self.config_personalizacion['fondo_panel_opacidad'] = valor
        personalizacion.guardar_config(self.config_personalizacion)

    def restaurar_personalizacion_defaults(self):
        self.config_personalizacion = personalizacion.DEFAULTS.copy()
        personalizacion.guardar_config(self.config_personalizacion)
        self._accent = _C_ACCENT_DEFAULT
        self._aplicar_fondo_animado()
        self._refrescar_vista()

    def _refrescar_vista(self):
        if self.token:
            self._mostrar_principal()
        elif hasattr(self, 'login_panel'):
            self._mostrar_login()

    def _abrir_personalizacion(self):
        dlg = PersonalizacionPanel(self, self)
        dlg.exec()

    # ------------------------------------------------------------------
    # Sesión
    # ------------------------------------------------------------------
    def _verificar_inicial(self):
        self._hilo_verificar = HiloVerificarSesion(self.token, self)
        self._hilo_verificar.resultado.connect(self._on_verificacion_inicial)
        self._hilo_verificar.start()

    def _on_verificacion_inicial(self, valido, mensaje):
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

    def _mostrar_verificando(self):
        self._limpiar_layout()
        self._lay.addStretch()

        lbl = QLabel("Verificando sesión...")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(f"color: {_C_TEXT_SEC}; font-size: 12px; background: transparent;")
        self._lay.addWidget(lbl)

        spinner = QProgressBar()
        spinner.setRange(0, 0)
        spinner.setTextVisible(False)
        spinner.setFixedWidth(220)
        spinner.setFixedHeight(8)
        spinner.setStyleSheet(f"""
            QProgressBar {{
                background-color: {_C_CARD};
                border: 0.5px solid {_C_BORDER};
                border-radius: 4px;
            }}
            QProgressBar::chunk {{
                background-color: {self._accent};
                border-radius: 4px;
            }}
        """)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(spinner)
        row.addStretch()
        self._lay.addLayout(row)

        self._lay.addStretch()

    def _mostrar_login(self):
        self._limpiar_layout()
        self.login_panel = LoginPanel(self._accent, self)
        self.login_panel.login_exitoso.connect(self._on_login_exitoso)
        self._lay.addWidget(self.login_panel)

    def _on_login_exitoso(self, token):
        self.token = token
        _guardar_token(self.token)
        self._mostrar_principal()
        self._timer_sesion.start()

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
            f"background-color: {self._accent}; color: white; border-radius: 20px; "
            "font-weight: bold; font-size: 16px;"
        )
        header.addWidget(avatar)

        info = QVBoxLayout()
        info.setSpacing(0)
        lbl_usuario = QLabel(_decodificar_email(self.token) or "Usuario")
        lbl_usuario.setStyleSheet(f"color: {_C_TEXT}; font-size: 13px; font-weight: bold; background: transparent;")
        info.addWidget(lbl_usuario)
        lbl_sub = QLabel("SimpleHub")
        lbl_sub.setStyleSheet(f"color: {_C_TEXT_SEC}; font-size: 10px; background: transparent;")
        info.addWidget(lbl_sub)
        header.addLayout(info)
        header.addStretch()

        btn_personalizar = QPushButton("🎨")
        btn_personalizar.setFixedSize(34, 34)
        btn_personalizar.setToolTip("Personalizar")
        btn_personalizar.setStyleSheet(
            f"background-color: transparent; border: 0.5px solid {_C_BORDER}; "
            "border-radius: 7px; font-size: 14px;"
        )
        btn_personalizar.clicked.connect(self._abrir_personalizacion)
        header.addWidget(btn_personalizar)

        self._btn_actualizar = QPushButton("🔄 Buscar actualizaciones")
        self._btn_actualizar.setStyleSheet(
            f"background-color: transparent; color: {_C_TEXT_SEC}; "
            f"border: 0.5px solid {_C_BORDER}; border-radius: 7px; padding: 6px 12px;"
        )
        self._btn_actualizar.clicked.connect(self._buscar_actualizaciones_manual)
        header.addWidget(self._btn_actualizar)

        btn_logout = QPushButton("Cerrar sesión")
        btn_logout.setStyleSheet(
            f"background-color: transparent; color: {_C_TEXT_SEC}; "
            f"border: 0.5px solid {_C_BORDER}; border-radius: 7px; padding: 6px 12px;"
        )
        btn_logout.clicked.connect(lambda: self._cerrar_sesion())
        header.addWidget(btn_logout)

        self._lay.addLayout(header)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(16)

        self.card_resolver = AppCard(
            "Simple Resolver",
            "Asistente de respuestas con IA mediante captura de pantalla.",
            "🧠", self._accent,
        )
        self.card_resolver.abrir.connect(lambda: self._abrir_app('resolver'))
        cards_row.addWidget(self.card_resolver)

        self.card_downloader = AppCard(
            "Simple Downloader",
            "Navegador con descargador de videos integrado.",
            "⬇️", self._accent,
        )
        self.card_downloader.abrir.connect(lambda: self._abrir_app('downloader'))
        cards_row.addWidget(self.card_downloader)

        self._lay.addLayout(cards_row)
        self._lay.addStretch()

        QTimer.singleShot(0, self._animar_cards)

    def _animar_cards(self):
        self._anims = [a for a in self._anims if a.state() == QPropertyAnimation.State.Running]
        for card in (self.card_resolver, self.card_downloader):
            destino = card.pos()
            card.move(destino.x(), destino.y() + 24)
            anim = QPropertyAnimation(card, b"pos", self)
            anim.setDuration(300)
            anim.setStartValue(QPoint(destino.x(), destino.y() + 24))
            anim.setEndValue(destino)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.start()
            self._anims.append(anim)

    def _inicial_usuario(self):
        email = _decodificar_email(self.token)
        return (email[:1] or "?").upper()

    # ------------------------------------------------------------------
    # Actualizaciones
    # ------------------------------------------------------------------
    def _verificar_actualizacion_silenciosa(self):
        if self._hilo_actualizacion and self._hilo_actualizacion.isRunning():
            return
        self._hilo_actualizacion = HiloBuscarActualizacion(self)
        self._hilo_actualizacion.resultado.connect(self._on_resultado_actualizacion)
        self._hilo_actualizacion.start()

    def _on_resultado_actualizacion(self, info):
        if info:
            actualizador.mostrar_dialogo_actualizacion(info, self._accent, self)

    def _buscar_actualizaciones_manual(self):
        if self._hilo_actualizacion and self._hilo_actualizacion.isRunning():
            return
        if self._btn_actualizar:
            self._btn_actualizar.setEnabled(False)
            self._btn_actualizar.setText("Buscando...")
        self._hilo_actualizacion = HiloBuscarActualizacion(self)
        self._hilo_actualizacion.resultado.connect(self._on_resultado_manual)
        self._hilo_actualizacion.start()

    def _on_resultado_manual(self, info):
        if self._btn_actualizar:
            try:
                self._btn_actualizar.setEnabled(True)
                self._btn_actualizar.setText("🔄 Buscar actualizaciones")
            except RuntimeError:
                pass
        if info:
            actualizador.mostrar_dialogo_actualizacion(info, self._accent, self)
        else:
            version_local = actualizador._cargar_version_local()
            v = (version_local or {}).get('version', '?')
            QMessageBox.information(
                self, "Sin actualizaciones",
                f"Ya tenés la versión más reciente ({v})."
            )

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

        if getattr(sys, 'frozen', False):
            nombre_exe = 'SimpleResolver.exe' if app_key == 'resolver' else 'SimpleDownloader.exe'
            ruta = os.path.join(BASE_DIR, nombre_exe)

            if not os.path.exists(ruta):
                dlg = DialogoDescargaExe(nombre_exe, self._accent, self)
                if dlg.exec() != QDialog.DialogCode.Accepted:
                    err = dlg._error_msg or 'Descarga cancelada o fallida.'
                    QMessageBox.critical(
                        self, "Error al descargar",
                        f"No se pudo descargar {nombre_exe}:\n{err}"
                    )
                    return

            try:
                subprocess.Popen([ruta, '--token', self.token], cwd=BASE_DIR)
            except FileNotFoundError:
                QMessageBox.critical(
                    self, "Archivo no encontrado",
                    f"No se encontró {nombre_exe} en:\n{BASE_DIR}"
                )
            except Exception as e:
                QMessageBox.critical(
                    self, "Error al iniciar",
                    f"No se pudo abrir {nombre_exe}:\n{e}"
                )
            return

        if app_key == 'resolver':
            script = os.path.join(BASE_DIR, 'main.py')
        else:
            script = os.path.join(BASE_DIR, '_run_downloader.py')
        try:
            subprocess.Popen([sys.executable, script, '--token', self.token], cwd=BASE_DIR)
        except Exception as e:
            QMessageBox.critical(self, "Error al iniciar", f"No se pudo abrir la app:\n{e}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    try:
        hub = SimpleHub()
        hub.show()
        hub.raise_()
        hub.activateWindow()
        sys.exit(app.exec())
    except SystemExit:
        raise
    except Exception:
        import traceback
        QMessageBox.critical(None, "Error en SimpleHub", traceback.format_exc())
        raise
