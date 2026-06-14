import os
import sys
import threading

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QLabel, QSlider, QColorDialog, QGraphicsBlurEffect,
                             QDialog, QFileDialog, QMenu, QMessageBox, QApplication)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QPoint, QTimer, QMetaObject, Q_ARG
from PyQt6.QtGui import (QFont, QColor, QPainter, QPen, QBrush, QLinearGradient,
                         QPainterPath, QPixmap, QIcon, QRegion)
from pynput import mouse as pynput_mouse, keyboard as pynput_kb
from pynput.keyboard import Key
from captura import tomar_captura
from ia import preguntar_ia, AUTH_ERROR
import auth_manager
import personalizacion
from fondo_animado import AnimacionFondoWidget, FondoVideoWidget, SeccionFondoAnimado
import self_destruct
from security import create_session
from config import SERVER_URL


PRESETS_FONDO = ['#121020', '#1a1a2e', '#0f3443', '#1f1c2c', '#2c1e3f', '#16213e']
PRESETS_BOTONES = ['#7c6fff', '#00d4aa', '#ff6b8a', '#ffa500', '#3a86ff', '#e63946']


def _resource(filename):
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, filename)


def _log_event(event_type):
    def _send():
        try:
            token = auth_manager.cargar_token()
            if not token:
                return
            create_session().post(
                f"{SERVER_URL}/events/log",
                data={'event_type': event_type, 'app_version': '2.0'},
                headers={'Authorization': f'Bearer {token}'},
                timeout=5,
            )
        except Exception:
            return
    threading.Thread(target=_send, daemon=True).start()


class HiloCaptura(QThread):
    resultado = pyqtSignal(str, int)

    def run(self):
        try:
            img = tomar_captura()
            respuesta, capturas = preguntar_ia(img)
        except Exception as e:
            respuesta = f"Error: {str(e)}"
            capturas = -1
        self.resultado.emit(respuesta, capturas)


class HiloVerificar(QThread):
    resultado = pyqtSignal(bool)

    def run(self):
        token = auth_manager.cargar_token()
        if not token:
            self.resultado.emit(False)
            return
        try:
            r = create_session().get(
                f"{SERVER_URL}/auth/verify",
                headers={'Authorization': f'Bearer {token}'},
                timeout=10,
            )
            self.resultado.emit(r.status_code == 200)
        except Exception:
            self.resultado.emit(False)


class PanelGlass(QWidget):
    """Panel con efecto glassmorphism — fondo degradado con borde brillante."""
    def __init__(self, oscuro=True, parent=None):
        super().__init__(parent)
        self.oscuro = oscuro
        self.transparente = False
        self.color_fondo = None
        self.color_borde = None
        self.pixmap_fondo = None
        self.opacidad_imagen = 50
        self.fondo_animado = AnimacionFondoWidget(self)
        self.fondo_video = FondoVideoWidget(self)
        self.fondo_animado.lower()
        self.fondo_video.lower()

    def set_tema(self, oscuro):
        self.oscuro = oscuro
        self.update()

    def set_transparente(self, valor):
        self.transparente = valor
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        r = self.rect()
        self.fondo_animado.setGeometry(r)
        self.fondo_video.setGeometry(r)
        self.fondo_animado.lower()
        self.fondo_video.lower()

        path = QPainterPath()
        path.addRoundedRect(0, 0, r.width(), r.height(), 16, 16)
        region = QRegion(path.toFillPolygon().toPolygon())
        self.fondo_animado.setMask(region)
        self.fondo_video.setMask(region)

    def set_color_fondo(self, color_hex):
        self.color_fondo = QColor(color_hex) if color_hex else None
        self.update()

    def set_color_borde(self, color_hex):
        self.color_borde = QColor(color_hex) if color_hex else None
        self.update()

    def set_pixmap_fondo(self, pixmap):
        self.pixmap_fondo = pixmap
        self.update()

    def set_opacidad_imagen(self, valor):
        self.opacidad_imagen = valor
        self.update()

    def paintEvent(self, event):
        if self.transparente:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()
        path = QPainterPath()
        path.addRoundedRect(r.x(), r.y(), r.width(), r.height(), 16, 16)

        if self.color_fondo is not None:
            p.fillPath(path, QBrush(self.color_fondo))
        elif self.oscuro:
            grad = QLinearGradient(0, 0, r.width(), r.height())
            grad.setColorAt(0.0, QColor(18, 16, 32, 230))
            grad.setColorAt(0.5, QColor(22, 20, 40, 220))
            grad.setColorAt(1.0, QColor(14, 12, 28, 230))
            p.fillPath(path, QBrush(grad))
        else:
            grad = QLinearGradient(0, 0, r.width(), r.height())
            grad.setColorAt(0.0, QColor(255, 255, 255, 230))
            grad.setColorAt(0.5, QColor(240, 238, 255, 220))
            grad.setColorAt(1.0, QColor(230, 228, 255, 230))
            p.fillPath(path, QBrush(grad))

        if self.pixmap_fondo is not None and self.opacidad_imagen > 0:
            p.save()
            p.setClipPath(path)
            p.setOpacity(self.opacidad_imagen / 100)
            escalado = self.pixmap_fondo.scaled(
                r.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (r.width() - escalado.width()) // 2
            y = (r.height() - escalado.height()) // 2
            p.drawPixmap(x, y, escalado)
            p.setOpacity(1.0)
            p.restore()

        if self.color_borde is not None:
            p.setPen(QPen(self.color_borde, 1))
        elif self.oscuro:
            p.setPen(QPen(QColor(124, 111, 255, 80), 1))
        else:
            p.setPen(QPen(QColor(91, 79, 255, 60), 1))
        p.drawPath(path)

        if self.oscuro:
            shine = QLinearGradient(0, 0, r.width(), 0)
            shine.setColorAt(0.0, QColor(255, 255, 255, 0))
            shine.setColorAt(0.3, QColor(255, 255, 255, 30))
            shine.setColorAt(0.7, QColor(255, 255, 255, 30))
            shine.setColorAt(1.0, QColor(255, 255, 255, 0))
            p.setPen(QPen(QBrush(shine), 1))
            p.drawLine(20, 1, r.width() - 20, 1)

        p.end()


class RespPanel(QWidget):
    """Panel de respuesta con fondo glass más oscuro."""
    def __init__(self, oscuro=True, parent=None):
        super().__init__(parent)
        self.oscuro = oscuro
        self.transparente = False
        self.setMinimumHeight(0)

    def set_tema(self, oscuro):
        self.oscuro = oscuro
        self.update()

    def set_transparente(self, valor):
        self.transparente = valor
        self.update()

    def paintEvent(self, event):
        if self.transparente:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        r = self.rect()
        path.addRoundedRect(r.x(), r.y(), r.width(), r.height(), 10, 10)

        if self.oscuro:
            p.fillPath(path, QBrush(QColor(8, 7, 18, 220)))
            p.setPen(QPen(QColor(0, 212, 170, 60), 1))
        else:
            p.fillPath(path, QBrush(QColor(245, 244, 255, 220)))
            p.setPen(QPen(QColor(91, 79, 255, 60), 1))

        p.drawPath(path)
        p.end()


class BarraFlotante(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.slider_visible = False
        self.transparente = False
        self.setFixedHeight(24)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 2, 6, 2)
        lay.setSpacing(5)

        self.btn_color = QPushButton()
        self.btn_color.setFixedSize(14, 14)
        self.btn_color.setObjectName("btnColorMini")

        # Botón transparencia
        self.btn_op = QPushButton("🔆")
        self.btn_op.setFixedSize(20, 20)
        self.btn_op.setObjectName("btnOpToggle")
        self.btn_op.setToolTip("Transparencia")
        self.btn_op.clicked.connect(self.toggle_slider_op)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setMinimum(0)
        self.slider.setMaximum(100)
        self.slider.setValue(100)
        self.slider.setObjectName("sliderOp")
        self.slider.setFixedWidth(80)
        self.slider.setVisible(False)

        # Botón tamaño de letra
        self.btn_font = QPushButton("𝐀")
        self.btn_font.setFixedSize(20, 20)
        self.btn_font.setObjectName("btnOpToggle")
        self.btn_font.setToolTip("Tamaño de letra")
        self.btn_font.clicked.connect(self.toggle_slider_font)

        self.slider_font = QSlider(Qt.Orientation.Horizontal)
        self.slider_font.setMinimum(8)
        self.slider_font.setMaximum(40)
        self.slider_font.setValue(14)
        self.slider_font.setObjectName("sliderOp")
        self.slider_font.setFixedWidth(80)
        self.slider_font.setVisible(False)

        # Botón modo horizontal/vertical
        self.btn_modo = QPushButton("≡")
        self.btn_modo.setFixedSize(20, 20)
        self.btn_modo.setObjectName("btnOpToggle")
        self.btn_modo.setToolTip("Cambiar disposición del texto")

        lay.addWidget(self.btn_color)
        lay.addStretch()
        lay.addWidget(self.btn_modo)
        lay.addWidget(self.btn_font)
        lay.addWidget(self.slider_font)
        lay.addWidget(self.btn_op)
        lay.addWidget(self.slider)

    def toggle_slider_op(self):
        vis = not self.slider.isVisible()
        self.slider.setVisible(vis)
        self.btn_op.setText("🔅" if vis else "🔆")

    def toggle_slider_font(self):
        vis = not self.slider_font.isVisible()
        self.slider_font.setVisible(vis)

    def set_transparente(self, valor):
        self.transparente = valor
        self.update()

    def paintEvent(self, event):
        pass


class PanelPersonalizacion(QDialog):
    """Panel de personalización: colores y fondo personalizado."""

    def __init__(self, ventana, parent=None):
        super().__init__(parent)
        self.ventana = ventana
        self.setWindowTitle('Personalización')
        self.setFixedWidth(280)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet("""
            QDialog {
                background-color: #1a1a1a;
                border: 0.5px solid #333;
                border-radius: 10px;
            }
            QLabel {
                color: #cccccc;
            }
            QSlider::groove:horizontal {
                background-color: #333;
                height: 4px;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background-color: #7c3aed;
                width: 14px;
                height: 14px;
                margin: -5px 0;
                border-radius: 7px;
            }
            QSlider::sub-page:horizontal {
                background-color: #7c3aed;
                border-radius: 2px;
            }
        """)

        lay = QVBoxLayout(self)
        lay.setSpacing(8)

        lay.addWidget(self._titulo('Color de fondo'))
        fila_fondo = QHBoxLayout()
        for color in PRESETS_FONDO:
            fila_fondo.addWidget(self._swatch(color, self._set_color_fondo))
        lay.addLayout(fila_fondo)

        btn_fondo_custom = QPushButton('Personalizado...')
        btn_fondo_custom.clicked.connect(self._elegir_color_fondo_custom)
        lay.addWidget(btn_fondo_custom)

        lay.addWidget(self._titulo('Color de botones'))
        fila_botones = QHBoxLayout()
        self._swatches_botones = []
        for color in PRESETS_BOTONES:
            swatch = self._swatch(color, self._set_color_botones)
            self._swatches_botones.append((color, swatch))
            fila_botones.addWidget(swatch)
        lay.addLayout(fila_botones)
        self._actualizar_seleccion_botones()

        btn_botones_custom = QPushButton('Personalizado...')
        btn_botones_custom.clicked.connect(self._elegir_color_botones_custom)
        lay.addWidget(btn_botones_custom)

        lay.addWidget(self._titulo('Opacidad de los botones'))
        self.slider_botones_op = QSlider(Qt.Orientation.Horizontal)
        self.slider_botones_op.setMinimum(10)
        self.slider_botones_op.setMaximum(100)
        self.slider_botones_op.setValue(self.ventana.config_personalizacion.get('opacidad_botones', 100))
        self.slider_botones_op.valueChanged.connect(self.ventana.set_opacidad_botones)
        lay.addWidget(self.slider_botones_op)

        self.slider_pestanas_op = None
        if hasattr(self.ventana, 'set_opacidad_pestanas'):
            lay.addWidget(self._titulo('Opacidad de las pestañas'))
            self.slider_pestanas_op = QSlider(Qt.Orientation.Horizontal)
            self.slider_pestanas_op.setMinimum(10)
            self.slider_pestanas_op.setMaximum(100)
            self.slider_pestanas_op.setValue(self.ventana.config_personalizacion.get('opacidad_pestanas', 100))
            self.slider_pestanas_op.valueChanged.connect(self.ventana.set_opacidad_pestanas)
            lay.addWidget(self.slider_pestanas_op)

        if hasattr(self.ventana, 'set_color_marco'):
            lay.addWidget(self._titulo('Color del marco'))
            fila_marco = QHBoxLayout()
            for color in PRESETS_FONDO:
                fila_marco.addWidget(self._swatch(color, self._set_color_marco))
            lay.addLayout(fila_marco)

            btn_marco_custom = QPushButton('Personalizado...')
            btn_marco_custom.clicked.connect(self._elegir_color_marco_custom)
            lay.addWidget(btn_marco_custom)

        lay.addWidget(self._titulo('Imagen de fondo'))
        fila_img = QHBoxLayout()
        btn_sel_img = QPushButton('Seleccionar imagen')
        btn_sel_img.clicked.connect(self._seleccionar_imagen)
        btn_quitar_img = QPushButton('Quitar imagen')
        btn_quitar_img.clicked.connect(self._quitar_imagen)
        fila_img.addWidget(btn_sel_img)
        fila_img.addWidget(btn_quitar_img)
        lay.addLayout(fila_img)

        lay.addWidget(self._titulo('Opacidad de la imagen'))
        self.slider_img_op = QSlider(Qt.Orientation.Horizontal)
        self.slider_img_op.setMinimum(0)
        self.slider_img_op.setMaximum(100)
        self.slider_img_op.setValue(self.ventana.config_personalizacion.get('opacidad_imagen', 50))
        self.slider_img_op.valueChanged.connect(self.ventana.set_opacidad_imagen)
        lay.addWidget(self.slider_img_op)

        self.seccion_fondo_animado = SeccionFondoAnimado(self.ventana, self.ventana.config_personalizacion)
        lay.addWidget(self.seccion_fondo_animado)

        btn_restaurar = QPushButton('Restaurar defaults')
        btn_restaurar.clicked.connect(self._restaurar_defaults)
        lay.addWidget(btn_restaurar)

    def _titulo(self, texto):
        l = QLabel(texto)
        l.setStyleSheet('font-weight: bold;')
        return l

    def _swatch(self, color, callback, seleccionado=False):
        b = QPushButton()
        b.setFixedSize(28, 28)
        self._estilizar_swatch(b, color, seleccionado)
        # clicked emite un bool (checked); sin el parámetro _checked ese bool
        # pisa el valor por defecto "c=color" y el color real nunca llega.
        b.clicked.connect(lambda _checked=False, c=color: callback(c))
        return b

    def _estilizar_swatch(self, boton, color, seleccionado):
        borde = '2px solid #ffffff' if seleccionado else '1px solid rgba(128,128,128,0.5)'
        boton.setStyleSheet(f'background-color: {color}; border-radius: 4px; border: {borde};')

    def _actualizar_seleccion_botones(self):
        actual = self.ventana.config_personalizacion.get('color_botones')
        for color, swatch in self._swatches_botones:
            self._estilizar_swatch(swatch, color, color == actual)

    def _set_color_fondo(self, color_hex):
        self.ventana.set_color_fondo(color_hex)

    def _elegir_color_fondo_custom(self):
        actual = self.ventana.config_personalizacion.get('color_fondo') or '#121020'
        color = QColorDialog.getColor(QColor(actual), self, 'Color de fondo')
        if color.isValid():
            self.ventana.set_color_fondo(color.name())

    def _set_color_botones(self, color_hex):
        self.ventana.set_color_botones(color_hex)
        self._actualizar_seleccion_botones()

    def _elegir_color_botones_custom(self):
        actual = self.ventana.config_personalizacion.get('color_botones') or '#7c6fff'
        color = QColorDialog.getColor(QColor(actual), self, 'Color de botones')
        if color.isValid():
            self.ventana.set_color_botones(color.name())
            self._actualizar_seleccion_botones()

    def _set_color_marco(self, color_hex):
        self.ventana.set_color_marco(color_hex)

    def _elegir_color_marco_custom(self):
        actual = self.ventana.config_personalizacion.get('color_marco') or '#7c6fff'
        color = QColorDialog.getColor(QColor(actual), self, 'Color del marco')
        if color.isValid():
            self.ventana.set_color_marco(color.name())

    def _seleccionar_imagen(self):
        dlg = QFileDialog(self, 'Seleccionar imagen', '', 'Imágenes (*.png *.jpg *.jpeg)')
        dlg.setFileMode(QFileDialog.FileMode.ExistingFile)
        dlg.setWindowFlags(dlg.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        if dlg.exec() and dlg.selectedFiles():
            self.ventana.set_imagen_fondo(dlg.selectedFiles()[0])

    def _quitar_imagen(self):
        self.ventana.set_imagen_fondo(None)

    def _restaurar_defaults(self):
        self.ventana.restaurar_personalizacion_defaults()
        self.slider_img_op.setValue(self.ventana.config_personalizacion['opacidad_imagen'])
        self.slider_botones_op.setValue(self.ventana.config_personalizacion['opacidad_botones'])
        if self.slider_pestanas_op is not None:
            self.slider_pestanas_op.setValue(self.ventana.config_personalizacion.get('opacidad_pestanas', 100))
        self.seccion_fondo_animado.actualizar(self.ventana.config_personalizacion)


class SimpleResolve(QWidget):
    def __init__(self):
        super().__init__()
        self.drag_pos = QPoint()
        self.capturas_restantes = None
        self.grabando = None
        self.atajo_cap = Key.f9
        self.atajo_close = Key.f10
        self.atajo_ocultar = Key.f8
        self.atajo_cap_mouse = None
        self.atajo_close_mouse = None
        self.atajo_autodestruccion = Key.pause
        self._autodestruccion_armada = False
        self._timer_autodestruccion = None
        self.oculto = False
        self.color_texto = "#00d4aa"
        self.font_size = 14
        self.modo_horizontal = False
        self._opacity_timer = None
        self.listener_mouse = None
        self.listener_kb = None
        self._grab_mouse = None
        self._grab_kb = None
        self._hilo_verificar = None
        self._timer_sesion = None
        self.ventana_download = None
        self.ventana_pdf = None
        self.cerrado = False
        self.config_personalizacion = personalizacion.cargar_config()
        self.initUI()
        self.iniciar_listeners()
        QTimer.singleShot(30000, self._iniciar_verificacion_periodica)
        _log_event('app_open')

        # Si SimpleHub invalida la sesión (cuenta desactivada o cierre de
        # sesión global), esta app también debe cerrarse.
        self._timer_flag_sesion = QTimer(self)
        self._timer_flag_sesion.timeout.connect(self._chequear_sesion_invalida)
        self._timer_flag_sesion.start(60000)

    def initUI(self):
        self.setWindowTitle("SimpleResolve")
        self.setWindowIcon(QIcon(_resource('icon.ico')))
        self.setFixedWidth(320)
        self._aplicar_flags()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        lay = QVBoxLayout()
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.setLayout(lay)

        # Panel glass principal
        self.glass = PanelGlass(oscuro=True)
        lay.addWidget(self.glass)
        self.glass.fondo_video.calidad_cambiada.connect(self._on_fondo_video_calidad_cambiada)

        c = QVBoxLayout()
        c.setContentsMargins(8, 6, 8, 6)
        c.setSpacing(4)
        self.glass.setLayout(c)

        # ── Header ──
        self.w_header = QWidget()
        self.w_header.setStyleSheet("background: transparent;")
        hl = QHBoxLayout(self.w_header)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(4)

        self.lbl_logo = QLabel()
        self.lbl_logo.setStyleSheet("background: transparent;")
        self.lbl_logo.setPixmap(QIcon(_resource('icon.ico')).pixmap(18, 18))

        self.lbl_titulo = QLabel("SimpleResolve")
        self.lbl_titulo.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.lbl_titulo.setStyleSheet("color: #eaeaf5; background: transparent;")

        self.btn_personalizar = QPushButton("🎨")
        self.btn_personalizar.setFixedSize(20, 20)
        self.btn_personalizar.setToolTip("Personalizar")
        self.btn_personalizar.clicked.connect(self.abrir_personalizacion)
        self.btn_personalizar.setObjectName("btnHeader")

        self.btn_menu = QPushButton("≡")
        self.btn_menu.setFixedSize(20, 20)
        self.btn_menu.setToolTip("Menú")
        self.btn_menu.clicked.connect(self.abrir_menu)
        self.btn_menu.setObjectName("btnHeader")

        self.btn_min = QPushButton("─")
        self.btn_min.setFixedSize(20, 20)
        self.btn_min.clicked.connect(self.showMinimized)
        self.btn_min.setObjectName("btnHeader")

        hl.addWidget(self.lbl_logo)
        hl.addWidget(self.lbl_titulo)
        hl.addStretch()
        hl.addWidget(self.btn_personalizar)
        hl.addWidget(self.btn_menu)
        hl.addWidget(self.btn_min)
        c.addWidget(self.w_header)

        # ── Barra flotante SIEMPRE VISIBLE ──
        self.barra = BarraFlotante()
        self.barra.btn_color.clicked.connect(self.elegir_color)
        self.barra.slider.valueChanged.connect(self.cambiar_opacidad)
        self.barra.slider_font.valueChanged.connect(self.cambiar_font_size)
        self.barra.btn_modo.clicked.connect(self.toggle_modo_texto)
        self._actualizar_btn_color()
        c.addWidget(self.barra)

        # ── Respuesta ──
        self.resp_panel = RespPanel(oscuro=True)
        rl = QVBoxLayout(self.resp_panel)
        rl.setContentsMargins(10, 5, 8, 5)
        self.lbl_resp = QLabel("Respuesta...")
        self.lbl_resp.setObjectName("lblResp")
        self.lbl_resp.setWordWrap(True)
        self.lbl_resp.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.lbl_resp.setFont(QFont("Consolas", 13, QFont.Weight.Bold))
        self.lbl_resp.setStyleSheet(f"color: {self.color_texto}; background: transparent;")
        rl.addWidget(self.lbl_resp)
        c.addWidget(self.resp_panel)

        # ── Botones ──
        self.w_btns = QWidget()
        self.w_btns.setStyleSheet("background: transparent;")
        bl = QHBoxLayout(self.w_btns)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(5)
        self.btn_cap = QPushButton("📸 Capturar")
        self.btn_cap.clicked.connect(self.capturar)
        self.btn_cap.setObjectName("btnCap")
        self.btn_x = QPushButton("✕")
        self.btn_x.setFixedWidth(36)
        self.btn_x.clicked.connect(self.close)
        self.btn_x.setObjectName("btnCerrar")
        bl.addWidget(self.btn_cap)
        bl.addWidget(self.btn_x)
        c.addWidget(self.w_btns)

        # ── Atajos ──
        self.btn_atajos = QPushButton("⌨️ Atajos ▼")
        self.btn_atajos.setObjectName("btnAtalos")
        self.btn_atajos.clicked.connect(self.toggle_atajos)
        c.addWidget(self.btn_atajos)

        self.panel = QWidget()
        self.panel.setObjectName("panelAtalos")
        self.panel.setVisible(False)
        self.panel.setStyleSheet("background: transparent;")
        pl = QVBoxLayout()
        pl.setContentsMargins(5, 5, 5, 5)
        pl.setSpacing(3)
        self.panel.setLayout(pl)

        fila1 = QHBoxLayout()
        fila1.addWidget(self._lbl("📸 Capturar", "lblAtajo"))
        fila1.addStretch()
        self.lbl_key_cap = self._lbl("F9", "keyBadge")
        fila1.addWidget(self.lbl_key_cap)
        self.btn_edit_cap = self._btn_edit()
        self.btn_edit_cap.clicked.connect(lambda: self.iniciar_grabacion("cap"))
        fila1.addWidget(self.btn_edit_cap)
        pl.addLayout(fila1)

        fila2 = QHBoxLayout()
        fila2.addWidget(self._lbl("✕ Cerrar", "lblAtajo"))
        fila2.addStretch()
        self.lbl_key_close = self._lbl("F10", "keyBadge")
        fila2.addWidget(self.lbl_key_close)
        self.btn_edit_close = self._btn_edit()
        self.btn_edit_close.clicked.connect(lambda: self.iniciar_grabacion("close"))
        fila2.addWidget(self.btn_edit_close)
        pl.addLayout(fila2)

        fila3 = QHBoxLayout()
        fila3.addWidget(self._lbl("👁 Ocultar/Mostrar", "lblAtajo"))
        fila3.addStretch()
        self.lbl_key_ocultar = self._lbl("F8", "keyBadge")
        fila3.addWidget(self.lbl_key_ocultar)
        self.btn_edit_ocultar = self._btn_edit()
        self.btn_edit_ocultar.clicked.connect(lambda: self.iniciar_grabacion("ocultar"))
        fila3.addWidget(self.btn_edit_ocultar)
        pl.addLayout(fila3)

        fila4 = QHBoxLayout()
        fila4.addWidget(self._lbl("💀 Autodestrucción (mantener)", "lblAtajo"))
        fila4.addStretch()
        self.lbl_key_autodestruccion = self._lbl(self._nombre_tecla(self.atajo_autodestruccion), "keyBadge")
        fila4.addWidget(self.lbl_key_autodestruccion)
        self.btn_edit_autodestruccion = self._btn_edit()
        self.btn_edit_autodestruccion.clicked.connect(lambda: self.iniciar_grabacion("autodestruccion"))
        fila4.addWidget(self.btn_edit_autodestruccion)
        pl.addLayout(fila4)

        c.addWidget(self.panel)

        # ── Footer ──
        self.w_footer = QWidget()
        self.w_footer.setStyleSheet("background: transparent;")
        fl = QHBoxLayout(self.w_footer)
        fl.setContentsMargins(0, 0, 0, 0)
        self.lbl_uso = QLabel("Capturas restantes: --")
        self.lbl_uso.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_uso.setObjectName("lblUso")
        fl.addWidget(self.lbl_uso)
        c.addWidget(self.w_footer)

        self.aplicar_tema()
        self._aplicar_personalizacion_visual()
        self._restaurar_posicion()

    def _restaurar_posicion(self):
        x = self.config_personalizacion.get('pos_x')
        y = self.config_personalizacion.get('pos_y')
        if x is not None and y is not None:
            self.move(x, y)

    def _lbl(self, texto, obj):
        l = QLabel(texto); l.setObjectName(obj)
        l.setStyleSheet("background: transparent;")
        return l

    def _btn_edit(self):
        b = QPushButton("✎"); b.setObjectName("btnCambiar"); b.setFixedWidth(28); return b

    def _aplicar_flags(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )

    # ════════════════════════════════
    #  COLOR TEXTO
    # ════════════════════════════════
    def elegir_color(self):
        color = QColorDialog.getColor(QColor(self.color_texto), self, "Color del texto")
        if color.isValid():
            self.color_texto = color.name()
            self._actualizar_btn_color()
            self.lbl_resp.setStyleSheet(
                f"color: {self.color_texto}; background: transparent; font-size: {self.font_size}px;"
            )

    def _actualizar_btn_color(self):
        self.barra.btn_color.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.color_texto};
                border-radius: 7px;
                border: 1px solid rgba(255,255,255,0.4);
            }}
            QPushButton:hover {{ border: 1px solid white; }}
        """)

    # ════════════════════════════════
    #  PERSONALIZACIÓN / MENÚ
    # ════════════════════════════════
    def abrir_personalizacion(self):
        dlg = PanelPersonalizacion(self, self)
        dlg.exec()

    def abrir_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #16142a; color: #eaeaf5; border: 1px solid rgba(124,111,255,0.35); border-radius: 6px; padding: 4px; }
            QMenu::item { padding: 6px 16px; border-radius: 4px; }
            QMenu::item:selected { background-color: rgba(124,111,255,0.25); }
        """)
        accion_download = menu.addAction('⬇ SimpleDownload')
        accion_download.triggered.connect(self.abrir_simpledownload)
        accion_pdf = menu.addAction('📄 SimplePDF')
        accion_pdf.triggered.connect(self.abrir_simplepdf)
        menu.exec(self.btn_menu.mapToGlobal(QPoint(0, self.btn_menu.height())))

    def abrir_simpledownload(self):
        if self.ventana_download is None or self.ventana_download.cerrado:
            from simple_downloader import SimpleDownloaderWindow
            self.ventana_download = SimpleDownloaderWindow()
            self.ventana_download.show()
            return
        self.ventana_download.show()
        self.ventana_download.raise_()
        self.ventana_download.activateWindow()

    def abrir_simplepdf(self):
        if self.ventana_pdf is None or self.ventana_pdf.cerrado:
            from simplepdf import SimplePDF
            self.ventana_pdf = SimplePDF(ventana_resolve=self)
            self.ventana_pdf.show()
            return
        self.ventana_pdf.show()
        self.ventana_pdf.raise_()
        self.ventana_pdf.activateWindow()

    # ════════════════════════════════
    #  PERSONALIZACIÓN VISUAL (fondo, imagen, fondo animado/video)
    # ════════════════════════════════
    def _aplicar_personalizacion_visual(self):
        cfg = self.config_personalizacion
        self.glass.set_color_fondo(cfg.get('color_fondo'))
        self.glass.set_color_borde(cfg.get('color_marco'))
        self.glass.set_opacidad_imagen(cfg.get('opacidad_imagen', 50))
        ruta = cfg.get('imagen_fondo')
        pixmap = None
        if ruta:
            pix = QPixmap(ruta)
            if not pix.isNull():
                pixmap = pix
        self.glass.set_pixmap_fondo(pixmap)
        self._aplicar_fondo_animado()

    def _aplicar_fondo_animado(self):
        cfg = self.config_personalizacion
        color = cfg.get('color_botones') or '#7c6fff'
        opacidad = cfg.get('fondo_animado_opacidad', 30)
        self.glass.fondo_animado.set_color(color)
        self.glass.fondo_animado.set_velocidad(cfg.get('fondo_animado_velocidad', 'normal'))
        self.glass.fondo_animado.set_opacidad(opacidad)
        self.glass.fondo_video.set_opacidad(cfg.get('fondo_video_opacidad', 40))
        self.glass.fondo_video.set_calidad(cfg.get('fondo_video_calidad', 'alta'))
        rendimiento = cfg.get('fondo_animado_rendimiento', False)
        self.glass.fondo_animado.set_rendimiento(rendimiento)
        self.glass.fondo_video.set_rendimiento(rendimiento)
        activo = cfg.get('fondo_animado_activo', False)
        video = cfg.get('video_fondo')
        if activo and video:
            self.glass.fondo_animado.set_activo(False)
            self.glass.fondo_video.set_video(video)
            return
        if activo:
            self.glass.fondo_video.set_video(None)
            self.glass.fondo_animado.set_tipo(cfg.get('fondo_animado_tipo', 'particulas'))
            self.glass.fondo_animado.set_activo(True)
            return
        self.glass.fondo_animado.set_activo(False)
        self.glass.fondo_video.set_video(None)

    def set_color_fondo(self, color_hex):
        self.config_personalizacion['color_fondo'] = color_hex
        personalizacion.guardar_config(self.config_personalizacion)
        self.glass.set_color_fondo(color_hex)

    def set_color_marco(self, color_hex):
        self.config_personalizacion['color_marco'] = color_hex
        personalizacion.guardar_config(self.config_personalizacion)
        self.glass.set_color_borde(color_hex)

    def set_color_botones(self, color_hex):
        self.config_personalizacion['color_botones'] = color_hex
        personalizacion.guardar_config(self.config_personalizacion)
        self.aplicar_tema()
        self._aplicar_fondo_animado()

    def set_opacidad_botones(self, valor):
        self.config_personalizacion['opacidad_botones'] = valor
        personalizacion.guardar_config(self.config_personalizacion)
        self.aplicar_tema()

    def set_imagen_fondo(self, ruta):
        self.config_personalizacion['imagen_fondo'] = ruta
        personalizacion.guardar_config(self.config_personalizacion)
        pixmap = None
        if ruta:
            pix = QPixmap(ruta)
            if not pix.isNull():
                pixmap = pix
        self.glass.set_pixmap_fondo(pixmap)

    def set_opacidad_imagen(self, valor):
        self.config_personalizacion['opacidad_imagen'] = valor
        personalizacion.guardar_config(self.config_personalizacion)
        self.glass.set_opacidad_imagen(valor)

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
        self.glass.fondo_video.set_opacidad(valor)

    def set_fondo_video_calidad(self, calidad):
        self.config_personalizacion['fondo_video_calidad'] = calidad
        personalizacion.guardar_config(self.config_personalizacion)
        self.glass.fondo_video.set_calidad(calidad)

    def _on_fondo_video_calidad_cambiada(self, calidad):
        # El widget de video bajó la calidad automáticamente por bajo rendimiento.
        self.config_personalizacion['fondo_video_calidad'] = calidad
        personalizacion.guardar_config(self.config_personalizacion)

    def restaurar_personalizacion_defaults(self):
        self.config_personalizacion = personalizacion.DEFAULTS.copy()
        personalizacion.guardar_config(self.config_personalizacion)
        self.glass.set_color_fondo(None)
        self.glass.set_color_borde(None)
        self.glass.set_pixmap_fondo(None)
        self.glass.set_opacidad_imagen(self.config_personalizacion['opacidad_imagen'])
        self.aplicar_tema()
        self._aplicar_fondo_animado()

    # ════════════════════════════════
    #  TRANSPARENCIA
    # ════════════════════════════════
    def cambiar_opacidad(self, valor):
        self._opacity_valor = valor
        # Throttle: solo procesar si no hay un timer pendiente
        if self._opacity_timer is not None:
            return
        self._opacity_timer = QTimer()
        self._opacity_timer.setSingleShot(True)
        self._opacity_timer.timeout.connect(self._aplicar_opacidad)
        self._opacity_timer.start(30)

    def _aplicar_opacidad(self):
        self._opacity_timer = None
        valor = getattr(self, '_opacity_valor', self.barra.slider.value())
        if valor == 0:
            self.w_header.setVisible(False)
            self.w_btns.setVisible(False)
            self.btn_atajos.setVisible(False)
            self.panel.setVisible(False)
            self.w_footer.setVisible(False)
            self.barra.btn_color.setVisible(False)
            self.glass.set_transparente(True)
            self.resp_panel.set_transparente(True)
            self.barra.set_transparente(True)
            self.setWindowOpacity(1.0)
            self.glass.fondo_animado.set_opacidad_ventana(0)
            self.glass.fondo_video.set_opacidad_ventana(0)
            self.adjustSize()
        else:
            if not self.w_header.isVisible():
                self.w_header.setVisible(True)
                self.w_btns.setVisible(True)
                self.btn_atajos.setVisible(True)
                self.w_footer.setVisible(True)
                self.barra.btn_color.setVisible(True)
                self.glass.set_transparente(False)
                self.resp_panel.set_transparente(False)
                self.barra.set_transparente(False)
                self.glass.setStyleSheet("")
                self.aplicar_tema()
                self.adjustSize()
            self.setWindowOpacity(max(0.15, valor / 100))
            self.glass.fondo_animado.set_opacidad_ventana(valor)
            self.glass.fondo_video.set_opacidad_ventana(valor)

    def cambiar_font_size(self, valor):
        self.font_size = valor
        # Throttle para no recalcular en cada tick
        if hasattr(self, '_font_timer') and self._font_timer is not None:
            self._font_pending = valor
            return
        self._font_pending = valor
        self._font_timer = QTimer()
        self._font_timer.setSingleShot(True)
        self._font_timer.timeout.connect(self._aplicar_font_size)
        self._font_timer.start(40)

    def _aplicar_font_size(self):
        self._font_timer = None
        valor = self._font_pending
        self.font_size = valor
        self.lbl_resp.setFont(QFont("Consolas", valor, QFont.Weight.Bold))
        self.lbl_resp.setStyleSheet(
            f"color: {self.color_texto}; background: transparent; font-size: {valor}px;"
        )

    def toggle_modo_texto(self):
        self.modo_horizontal = not self.modo_horizontal
        self.barra.btn_modo.setText("☰" if self.modo_horizontal else "≡")
        # Re-formatear la respuesta actual con el nuevo modo
        texto_actual = self.lbl_resp.text()
        if texto_actual and texto_actual not in ("Respuesta...", "..."):
            # Guardar texto raw y reformatear
            self.lbl_resp.setText(self._aplicar_modo(texto_actual))
        self.lbl_resp.setWordWrap(not self.modo_horizontal)
        QTimer.singleShot(30, self.adjustSize)

    def _aplicar_modo(self, texto):
        """Convierte entre modo horizontal y vertical."""
        sep = '  ·  '
        nl = '\n'
        if self.modo_horizontal:
            partes = [p.strip() for p in texto.replace(sep, nl).split(nl) if p.strip()]
            return sep.join(partes)
        else:
            partes = [p.strip() for p in texto.replace(sep, '·').split('·') if p.strip()]
            return nl.join(partes)

    # ════════════════════════════════
    #  OCULTAR / MOSTRAR
    # ════════════════════════════════
    def toggle_visibilidad(self):
        if self.oculto:
            self._aplicar_flags()
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.show()
            self.raise_()
            self.activateWindow()
            self.oculto = False
            # Restaurar estado correcto según valor actual del slider
            QTimer.singleShot(50, lambda: self._aplicar_opacidad())
        else:
            self.hide()
            self.oculto = True

    # ════════════════════════════════
    #  LISTENERS
    # ════════════════════════════════
    def iniciar_listeners(self):
        def on_press(key):
            if self.grabando: return
            # CRÍTICO: pynput corre en hilo externo, usar singleShot para
            # ejecutar en el hilo principal de Qt y evitar crashes
            if key == self.atajo_cap:
                QTimer.singleShot(0, self.capturar)
            elif key == self.atajo_close:
                QTimer.singleShot(0, self.close)
            elif key == self.atajo_ocultar:
                QTimer.singleShot(0, self.toggle_visibilidad)
            elif key == self.atajo_autodestruccion:
                if not self._autodestruccion_armada:
                    self._autodestruccion_armada = True
                    QTimer.singleShot(0, self._iniciar_cuenta_autodestruccion)

        def on_release(key):
            if key == self.atajo_autodestruccion:
                self._autodestruccion_armada = False
                QTimer.singleShot(0, self._cancelar_cuenta_autodestruccion)

        def on_click(x, y, button, pressed):
            if not pressed or self.grabando: return
            if self.atajo_cap_mouse and button == self.atajo_cap_mouse:
                QTimer.singleShot(0, self.capturar)
            if self.atajo_close_mouse and button == self.atajo_close_mouse:
                QTimer.singleShot(0, self.close)

        self.listener_kb    = pynput_kb.Listener(on_press=on_press, on_release=on_release, daemon=True)
        self.listener_mouse = pynput_mouse.Listener(on_click=on_click, daemon=True)
        self.listener_kb.start()
        self.listener_mouse.start()

    # ════════════════════════════════
    #  AUTODESTRUCCIÓN
    # ════════════════════════════════
    _DURACION_AUTODESTRUCCION_MS = 3000

    def _iniciar_cuenta_autodestruccion(self):
        if self.grabando or self._timer_autodestruccion is not None:
            return
        self._timer_autodestruccion = QTimer(self)
        self._timer_autodestruccion.setSingleShot(True)
        self._timer_autodestruccion.timeout.connect(self._confirmar_autodestruccion)
        self._timer_autodestruccion.start(self._DURACION_AUTODESTRUCCION_MS)

    def _cancelar_cuenta_autodestruccion(self):
        if self._timer_autodestruccion is not None:
            self._timer_autodestruccion.stop()
            self._timer_autodestruccion = None

    def _confirmar_autodestruccion(self):
        self._timer_autodestruccion = None
        if not self._autodestruccion_armada:
            return
        if self.oculto:
            self.toggle_visibilidad()
        respuesta = QMessageBox.warning(
            self,
            'Autodestrucción',
            'Esto eliminará SimpleResolve, SimpleDownload y SimplePDF de este equipo: configuración, caché, accesos directos y entradas de inicio automático.\n\nEsta acción NO se puede deshacer. ¿Continuar?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if respuesta != QMessageBox.StandardButton.Yes:
            return
        if self.ventana_download is not None and not self.ventana_download.cerrado:
            self.ventana_download.close()
        if self.ventana_pdf is not None and not self.ventana_pdf.cerrado:
            self.ventana_pdf.close()
        try:
            self_destruct.ejecutar_autodestruccion(dry_run=False)
        except Exception as e:
            QMessageBox.critical(self, 'Autodestrucción', f'Ocurrió un error durante la autodestrucción:\n{e}')
            return
        QApplication.quit()

    # ════════════════════════════════
    #  GRABACIÓN UNIVERSAL
    # ════════════════════════════════
    def iniciar_grabacion(self, tipo):
        self.grabando = tipo
        btns = {"cap": self.btn_edit_cap, "close": self.btn_edit_close, "ocultar": self.btn_edit_ocultar, "autodestruccion": self.btn_edit_autodestruccion}
        lbls = {"cap": self.lbl_key_cap,  "close": self.lbl_key_close,  "ocultar": self.lbl_key_ocultar,  "autodestruccion": self.lbl_key_autodestruccion}
        btns[tipo].setText("⏺")
        lbls[tipo].setText("...")

        for l in [self._grab_mouse, self._grab_kb]:
            try:
                if l: l.stop()
            except: pass

        def on_kb(key):
            if not self.grabando: return False
            nombre = self._nombre_tecla(key)
            self._asignar(nombre, False, key, None)
            return False

        def on_click(x, y, button, pressed):
            if not pressed or not self.grabando: return False
            if self.grabando == "autodestruccion":
                return None
            nombre = str(button).replace("Button.", "").upper()
            if nombre in ("LEFT", "RIGHT", "MIDDLE"): return None
            self._asignar(f"M-{nombre}", True, None, button)
            return False

        self._grab_kb    = pynput_kb.Listener(on_press=on_kb, daemon=True)
        self._grab_mouse = pynput_mouse.Listener(on_click=on_click, daemon=True)
        self._grab_kb.start()
        self._grab_mouse.start()

    def _nombre_tecla(self, key):
        try:
            if hasattr(key, 'char') and key.char: return key.char.upper()
            return str(key).replace("Key.", "").upper()
        except: return str(key).upper()

    def _asignar(self, nombre, es_mouse, key_obj, boton):
        tipo = self.grabando
        self.grabando = None
        btns = {"cap": self.btn_edit_cap, "close": self.btn_edit_close, "ocultar": self.btn_edit_ocultar, "autodestruccion": self.btn_edit_autodestruccion}
        lbls = {"cap": self.lbl_key_cap,  "close": self.lbl_key_close,  "ocultar": self.lbl_key_ocultar,  "autodestruccion": self.lbl_key_autodestruccion}
        btns[tipo].setText("✎")
        lbls[tipo].setText(nombre)
        if tipo == "cap":
            self.atajo_cap_mouse = boton if es_mouse else None
            if not es_mouse: self.atajo_cap = key_obj
        elif tipo == "close":
            self.atajo_close_mouse = boton if es_mouse else None
            if not es_mouse: self.atajo_close = key_obj
        elif tipo == "ocultar":
            if not es_mouse: self.atajo_ocultar = key_obj
        elif tipo == "autodestruccion":
            if not es_mouse: self.atajo_autodestruccion = key_obj

    # ════════════════════════════════
    #  CAPTURAR
    # ════════════════════════════════
    def capturar(self):
        if self.capturas_restantes is not None and self.capturas_restantes <= 0:
            self.lbl_resp.setText("Límite alcanzado.")
            return
        # Evitar doble captura si ya hay una en curso
        if hasattr(self, 'hilo') and self.hilo is not None and self.hilo.isRunning():
            return
        self.btn_cap.setEnabled(False)
        self.lbl_resp.setText("Analizando...")
        self.repaint()
        self.hide()
        QTimer.singleShot(200, self._tomar_captura)

    def _tomar_captura(self):
        # Evitar múltiples hilos simultáneos
        if hasattr(self, 'hilo') and self.hilo is not None and self.hilo.isRunning():
            self.show()
            self.btn_cap.setEnabled(True)
            return
        self.hilo = HiloCaptura()
        self.hilo.resultado.connect(self.mostrar_respuesta, Qt.ConnectionType.QueuedConnection)
        self.hilo.finished.connect(lambda: setattr(self, 'hilo', None))
        self.hilo.start()

    def limpiar_respuesta(self, texto):
        import re
        texto = texto.strip()
        # Detectar si hay múltiples respuestas numeradas: "1. X" o "**1.** X" o "1) X"
        # Limpiar asteriscos markdown primero
        texto_limpio = re.sub(r'[*_]+', '', texto)
        # Buscar patrones tipo "1. B) 56" o "1) B) 56"
        items = re.findall(r'\d+[\.\)]\s*[A-Da-d][\)\.]?\s*\)?[\w\s\-áéíóúÁÉÍÓÚñÑüÜ,\.]+', texto_limpio)
        if len(items) >= 2:
            # Múltiples respuestas: compactar en una sola línea
            partes = []
            for item in items:
                item = item.strip().rstrip('.,')
                # Normalizar a "1. B) Ottawa"
                item = re.sub(r'^(\d+)[\.)]', r'\1.', item)
                partes.append(item.strip())
            return '   ·   '.join(partes)
        # Respuesta simple: solo limpiar markdown
        texto_limpio = re.sub(r'#{1,6}\s*', '', texto_limpio)
        texto_limpio = re.sub(r'\n+', '  ', texto_limpio)
        return texto_limpio.strip()

    def mostrar_respuesta(self, texto, capturas=-1):
        self.show()
        self.raise_()
        self.activateWindow()

        if texto == AUTH_ERROR:
            from login import LoginDialog
            from PyQt6.QtWidgets import QDialog
            dlg = LoginDialog()
            if dlg.exec() == QDialog.DialogCode.Accepted:
                self.lbl_resp.setText('Sesión renovada.')
                self.btn_cap.setEnabled(True)
            else:
                self.close()
            QTimer.singleShot(50, self.adjustSize)
            return

        texto_limpio = self.limpiar_respuesta(texto)
        if self.modo_horizontal:
            self.lbl_resp.setText(self._aplicar_modo(texto_limpio))
        else:
            self.lbl_resp.setText(texto_limpio)
        QTimer.singleShot(50, self.adjustSize)
        self.btn_cap.setEnabled(True)

        if capturas >= 0:
            self.capturas_restantes = capturas
            self.lbl_uso.setText(f'Capturas restantes: {capturas}')

    # ════════════════════════════════
    #  VERIFICACIÓN DE SESIÓN
    # ════════════════════════════════
    def _iniciar_verificacion_periodica(self):
        self._verificar_sesion()
        self._timer_sesion = QTimer(self)
        self._timer_sesion.timeout.connect(self._verificar_sesion)
        self._timer_sesion.start(180000)

    def _verificar_sesion(self):
        if self._hilo_verificar and self._hilo_verificar.isRunning():
            return
        self._hilo_verificar = HiloVerificar()
        self._hilo_verificar.resultado.connect(self._on_verificacion)
        self._hilo_verificar.start()

    def _on_verificacion(self, valido):
        if valido:
            return
        if self._timer_sesion:
            self._timer_sesion.stop()
        auth_manager.borrar_token()
        if self.oculto:
            self.toggle_visibilidad()
        self.btn_cap.setEnabled(False)
        self.lbl_resp.setStyleSheet('color: #ff6b8a; background: transparent; font-size: 14px;')
        self.lbl_resp.setText('Sesión expirada.')
        if self.ventana_download is not None and not self.ventana_download.cerrado:
            self.ventana_download.close()
        if self.ventana_pdf is not None and not self.ventana_pdf.cerrado:
            self.ventana_pdf.close()
        QTimer.singleShot(2000, self.close)

    def _chequear_sesion_invalida(self):
        if auth_manager.hay_sesion_invalida():
            self._forzar_cierre_sesion()

    def _forzar_cierre_sesion(self):
        self._timer_flag_sesion.stop()
        if self._timer_sesion:
            self._timer_sesion.stop()
        auth_manager.borrar_token()
        auth_manager.limpiar_marca_sesion_invalida()
        if self.oculto:
            self.toggle_visibilidad()
        QMessageBox.warning(self, "Sesión cerrada", "Tu sesión fue cerrada desde SimpleHub.")
        if self.ventana_download is not None and not self.ventana_download.cerrado:
            self.ventana_download.close()
        if self.ventana_pdf is not None and not self.ventana_pdf.cerrado:
            self.ventana_pdf.close()
        self.close()

    def toggle_atajos(self):
        v = not self.panel.isVisible()
        self.panel.setVisible(v)
        self.btn_atajos.setText("⌨️ Atajos ▲" if v else "⌨️ Atajos ▼")
        QTimer.singleShot(50, self.adjustSize)

    # ════════════════════════════════
    #  TEMA
    # ════════════════════════════════
    def aplicar_tema(self):
        self.lbl_resp.setStyleSheet(
            f"color: {self.color_texto}; background: transparent; font-size: {self.font_size}px;"
        )
        css = self._css_dark()
        color_botones = self.config_personalizacion.get('color_botones')
        if color_botones:
            opacidad_botones = self.config_personalizacion.get('opacidad_botones', 100)
            css += self._css_botones_custom(color_botones, opacidad_botones)
        self.glass.setStyleSheet(css)

    def _css_botones_custom(self, color_hex, opacidad=100):
        c = QColor(color_hex)
        rgb = f"{c.red()},{c.green()},{c.blue()}"
        alpha = max(0.1, min(100, opacidad)) / 100
        alpha_hover = min(1.0, alpha + 0.15)
        luminancia = 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
        texto = '#1a1a2e' if luminancia > 140 else '#ffffff'
        return f"""
            #btnCap, #btnCerrar, #btnAtalos, #btnCambiar, #btnHeader, #btnOpToggle {{
                background: rgba({rgb},{alpha});
                color: {texto};
                border: 1px solid rgba({rgb},0.6);
            }}
            #btnCap:hover, #btnCerrar:hover, #btnAtalos:hover, #btnCambiar:hover, #btnHeader:hover, #btnOpToggle:hover {{
                background: rgba({rgb},{alpha_hover});
            }}
            #btnCap:disabled {{ background: rgba({rgb},0.25); color: rgba(255,255,255,0.4); }}
            #keyBadge {{ color: {texto}; background: rgba({rgb},{alpha}); border: 1px solid rgba({rgb},0.6); }}
        """

    def _css_dark(self):
        return """
            QPushButton {
                background: rgba(124,111,255,0.12);
                color: #eaeaf5;
                border: 1px solid rgba(124,111,255,0.3);
                border-radius: 8px;
                padding: 6px 10px;
            }
            QPushButton:hover { background: rgba(124,111,255,0.22); }
            QPushButton:checked { background: rgba(124,111,255,0.35); font-weight: bold; }
            QPushButton:disabled { background: rgba(255,255,255,0.04); color: #55547a; border-color: rgba(255,255,255,0.06); }
            QLabel       { color: #eaeaf5; font-size: 11px; background: transparent; }
            #lblUso      { color: #55547a; font-size: 10px; }
            #lblAtajo    { color: #9898b8; font-size: 11px; }
            #keyBadge    { color: #7c6fff; background: rgba(124,111,255,0.15); border: 1px solid rgba(124,111,255,0.35); border-radius: 4px; padding: 1px 6px; font-size: 10px; font-weight: bold; }
            #btnCap      { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #7c6fff,stop:1 #5a4fcf); color: white; border: none; border-radius: 7px; padding: 5px; font-weight: bold; font-size: 11px; }
            #btnCap:hover    { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #9d97ff,stop:1 #7c6fff); }
            #btnCap:disabled { background: rgba(42,41,64,180); color: #55547a; border: none; }
            #btnCerrar   { background: rgba(255,77,106,0.1); color: #ff4d6a; border: 1px solid rgba(255,77,106,0.25); border-radius: 7px; font-size: 11px; padding: 5px; }
            #btnCerrar:hover { background: rgba(255,77,106,0.2); }
            #btnAtalos   { background: rgba(255,255,255,0.05); color: #9898b8; border: 1px solid rgba(255,255,255,0.1); border-radius: 7px; padding: 3px; font-size: 10px; }
            #btnAtalos:hover { background: rgba(124,111,255,0.15); color: #7c6fff; border-color: rgba(124,111,255,0.4); }
            #panelAtalos { background: rgba(10,9,22,0.6); border: 1px solid rgba(124,111,255,0.15); border-radius: 9px; }
            #btnCambiar  { background: transparent; color: #55547a; border: 1px solid rgba(255,255,255,0.1); border-radius: 5px; padding: 2px; font-size: 11px; }
            #btnCambiar:hover { border-color: #7c6fff; color: #7c6fff; background: rgba(124,111,255,0.1); }
            #btnHeader   { background: transparent; border: none; color: #55547a; font-size: 12px; border-radius: 5px; padding: 0; }
            #btnHeader:hover { background: rgba(255,255,255,0.08); color: #eaeaf5; }
            QSlider::groove:horizontal { height: 3px; background: transparent; border-radius: 2px; }
            QSlider::handle:horizontal { background: #7c6fff; width: 10px; height: 10px; margin: -4px 0; border-radius: 5px; }
            QSlider::sub-page:horizontal { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #7c6fff,stop:1 #00d4aa); border-radius: 2px; }
            QSlider::add-page:horizontal { background: transparent; border-radius: 2px; }
            #btnOpToggle { background: transparent; color: #eaeaf5; border: 1px solid rgba(124,111,255,0.3); border-radius: 4px; font-size: 11px; padding: 0px; }
            #btnOpToggle:hover { background: rgba(124,111,255,0.2); border-color: rgba(124,111,255,0.7); }
        """

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_pos)

    def closeEvent(self, event):
        _log_event('app_close')
        self.cerrado = True
        self.config_personalizacion['pos_x'] = self.x()
        self.config_personalizacion['pos_y'] = self.y()
        personalizacion.guardar_config(self.config_personalizacion)

        if self._timer_sesion:
            self._timer_sesion.stop()

        if self._hilo_verificar and self._hilo_verificar.isRunning():
            self._hilo_verificar.quit()
            self._hilo_verificar.wait(500)

        if hasattr(self, 'hilo') and self.hilo is not None and self.hilo.isRunning():
            self.hilo.quit()
            self.hilo.wait(1000)

        for l in [self.listener_mouse, self.listener_kb, self._grab_mouse, self._grab_kb]:
            try:
                if l: l.stop()
            except: pass

        event.accept()

        descarga_abierta = self.ventana_download is not None and not self.ventana_download.cerrado
        pdf_abierto = self.ventana_pdf is not None and not self.ventana_pdf.cerrado
        if not descarga_abierta and not pdf_abierto:
            QApplication.instance().quit()
