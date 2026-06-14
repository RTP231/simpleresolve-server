"""Fondos animados para los paneles de SimpleResolve.

Versión simplificada (reconstrucción funcional): animaciones preestablecidas
dibujadas con QTimer + QPainter (partículas, ondas, estrellas, matrix, lluvia),
reproducción de video en loop como fondo, y la sección de UI reutilizable
para el panel de personalización.
"""
import math
import random
import time

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSlider,
    QButtonGroup, QFileDialog,
)
from PyQt6.QtCore import Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen, QBrush, QFont
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput, QVideoSink


ANIMACIONES_PRESET = [
    ('particulas', 'Partículas'),
    ('ondas', 'Ondas'),
    ('estrellas', 'Estrellas'),
    ('matrix', 'Matrix'),
    ('lluvia', 'Lluvia'),
]

VELOCIDADES = ['lento', 'normal', 'rapido']

FACTOR_VELOCIDAD = {'lento': 0.5, 'normal': 1.0, 'rapido': 2.0}

_MATRIX_CHARS = "アイウエオカキクケコサシスセソ0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

_INTERVALO_MS = 40
_INTERVALO_RENDIMIENTO_MS = 80

# Presets de calidad del fondo de video: (ancho_max, alto_max, fps_max)
CALIDAD_VIDEO = {
    'alta': (1280, 720, 24),
    'media': (854, 480, 15),
    'baja': (480, 270, 10),
    'desactivar': None,
}

_ORDEN_CALIDAD = ['alta', 'media', 'baja', 'desactivar']

CALIDADES_FONDO = [
    ('alta', 'Alta'),
    ('media', 'Media'),
    ('baja', 'Baja'),
    ('desactivar', 'Desactivar'),
]

_INTERVALO_MEDICION_FPS_MS = 2000


class AnimacionFondoWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.color = QColor('#7c6fff')
        self.opacidad = 30
        self.opacidad_ventana = 100
        self.velocidad = 'normal'
        self.tipo = 'particulas'
        self.rendimiento = False
        self.activo = False
        self._t = 0.0
        self._elementos = []
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def set_color(self, color):
        self.color = QColor(color) if color else QColor('#7c6fff')
        self.update()

    def set_opacidad(self, valor):
        self.opacidad = valor
        self.update()

    def set_opacidad_ventana(self, valor):
        self.opacidad_ventana = valor
        self.update()

    def set_velocidad(self, velocidad):
        self.velocidad = velocidad if velocidad in FACTOR_VELOCIDAD else 'normal'

    def set_tipo(self, tipo):
        self.tipo = tipo
        self._inicializar_elementos()
        self.update()

    def set_rendimiento(self, activo):
        self.rendimiento = activo
        if self.activo:
            self._timer.start(_INTERVALO_RENDIMIENTO_MS if activo else _INTERVALO_MS)

    def set_activo(self, activo):
        self.activo = activo
        if activo:
            self._inicializar_elementos()
            self._timer.start(_INTERVALO_RENDIMIENTO_MS if self.rendimiento else _INTERVALO_MS)
        else:
            self._timer.stop()
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.activo:
            self._inicializar_elementos()

    def _factor(self):
        return FACTOR_VELOCIDAD.get(self.velocidad, 1.0)

    def _inicializar_elementos(self):
        w = max(self.width(), 1)
        h = max(self.height(), 1)
        self._elementos = []

        if self.tipo == 'particulas':
            n = 40
            for _ in range(n):
                self._elementos.append({
                    'x': random.uniform(0, w),
                    'y': random.uniform(0, h),
                    'r': random.uniform(1, 3),
                    'vx': random.uniform(-0.4, 0.4),
                    'vy': random.uniform(-0.4, 0.4),
                })
        elif self.tipo == 'estrellas':
            n = 60
            for _ in range(n):
                self._elementos.append({
                    'x': random.uniform(0, w),
                    'y': random.uniform(0, h),
                    'r': random.uniform(0.5, 2),
                    'fase': random.uniform(0, math.tau),
                    'vel': random.uniform(0.5, 2.0),
                })
        elif self.tipo == 'matrix':
            cols = max(int(w / 16), 1)
            for i in range(cols):
                self._elementos.append({
                    'x': i * 16,
                    'y': random.uniform(-h, 0),
                    'vel': random.uniform(2, 6),
                    'char': random.choice(_MATRIX_CHARS),
                })
        elif self.tipo == 'lluvia':
            n = 80
            for _ in range(n):
                self._elementos.append({
                    'x': random.uniform(0, w),
                    'y': random.uniform(0, h),
                    'len': random.uniform(8, 20),
                    'vel': random.uniform(4, 10),
                })
        elif self.tipo == 'ondas':
            for i in range(4):
                self._elementos.append({'fase': i * math.pi / 4, 'amp': 12 + i * 6})

    def _tick(self):
        if not self._elementos:
            self._inicializar_elementos()
        factor = self._factor()
        w = max(self.width(), 1)
        h = max(self.height(), 1)
        self._t += 0.05 * factor

        if self.tipo == 'particulas':
            for p in self._elementos:
                p['x'] = (p['x'] + p['vx'] * factor) % w
                p['y'] = (p['y'] + p['vy'] * factor) % h
        elif self.tipo == 'estrellas':
            for s in self._elementos:
                s['fase'] += 0.05 * factor * s['vel']
        elif self.tipo == 'matrix':
            for c in self._elementos:
                c['y'] += c['vel'] * factor
                if c['y'] > h:
                    c['y'] = random.uniform(-h * 0.3, 0)
                    c['char'] = random.choice(_MATRIX_CHARS)
        elif self.tipo == 'lluvia':
            for d in self._elementos:
                d['y'] += d['vel'] * factor
                if d['y'] > h:
                    d['y'] = -d['len']
                    d['x'] = random.uniform(0, w)

        self.update()

    def paintEvent(self, event):
        if not self.activo or self.opacidad <= 0 or self.opacidad_ventana <= 0:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        op = (self.opacidad / 100) * (self.opacidad_ventana / 100)
        p.setOpacity(op)

        if self.tipo == 'particulas':
            self._dibujar_particulas(p)
        elif self.tipo == 'ondas':
            self._dibujar_ondas(p)
        elif self.tipo == 'estrellas':
            self._dibujar_estrellas(p)
        elif self.tipo == 'matrix':
            self._dibujar_matrix(p)
        elif self.tipo == 'lluvia':
            self._dibujar_lluvia(p)

        p.end()

    def _dibujar_particulas(self, p):
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(self.color))
        for part in self._elementos:
            p.drawEllipse(int(part['x']), int(part['y']), int(part['r'] * 2), int(part['r'] * 2))

    def _dibujar_ondas(self, p):
        w = self.width()
        h = self.height()
        pen = QPen(self.color)
        pen.setWidth(2)
        p.setPen(pen)
        for onda in self._elementos:
            path_y = []
            for x in range(0, w, 4):
                y = h / 2 + onda['amp'] * math.sin(x * 0.02 + self._t + onda['fase'])
                path_y.append((x, y))
            for i in range(len(path_y) - 1):
                x1, y1 = path_y[i]
                x2, y2 = path_y[i + 1]
                p.drawLine(int(x1), int(y1), int(x2), int(y2))

    def _dibujar_estrellas(self, p):
        p.setPen(Qt.PenStyle.NoPen)
        for s in self._elementos:
            brillo = (math.sin(s['fase']) + 1) / 2
            color = QColor(self.color)
            color.setAlphaF(max(0.1, brillo))
            p.setBrush(QBrush(color))
            r = s['r'] * (1 + brillo)
            p.drawEllipse(int(s['x']), int(s['y']), int(r * 2), int(r * 2))

    def _dibujar_matrix(self, p):
        font = QFont("Consolas", 12)
        p.setFont(font)
        p.setPen(QPen(self.color))
        for c in self._elementos:
            p.drawText(int(c['x']), int(c['y']), c['char'])

    def _dibujar_lluvia(self, p):
        pen = QPen(self.color)
        pen.setWidth(1)
        p.setPen(pen)
        for d in self._elementos:
            p.drawLine(int(d['x']), int(d['y']), int(d['x']), int(d['y'] + d['len']))


class FondoVideoWidget(QWidget):
    # Emitida cuando la calidad se baja automáticamente por bajo rendimiento.
    calidad_cambiada = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.opacidad = 30
        self.opacidad_ventana = 100
        self.rendimiento = False
        self._ruta = None

        self.calidad = 'alta'
        self._max_w, self._max_h, self._fps_limit = CALIDAD_VIDEO['alta']
        self._ultimo_frame_ts = 0.0
        self._frames_contados = 0

        self._sink = QVideoSink(self)
        self._audio = QAudioOutput(self)
        self._audio.setMuted(True)
        self._player = QMediaPlayer(self)
        self._player.setAudioOutput(self._audio)
        self._player.setVideoSink(self._sink)
        # No usar QMediaPlayer.Loops.Infinite: con el backend FFmpeg de Qt
        # provoca que el decodificador se reabra en cada vuelta del loop,
        # generando los avisos repetidos "Late SEI is not implemented" y un
        # crecimiento de memoria sin límite hasta colgar la app. En su lugar
        # se reinicia manualmente la posición al llegar al final.
        self._player.mediaStatusChanged.connect(self._on_media_status)

        self._frame = None
        self._sink.videoFrameChanged.connect(self._on_frame)

        self._fps_timer = QTimer(self)
        self._fps_timer.setInterval(_INTERVALO_MEDICION_FPS_MS)
        self._fps_timer.timeout.connect(self._medir_rendimiento)

    def _on_media_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._player.setPosition(0)
            self._player.play()

    def _on_frame(self, frame):
        if not frame.isValid():
            return
        ahora = time.monotonic()
        if self._fps_limit and (ahora - self._ultimo_frame_ts) < (1.0 / self._fps_limit):
            return
        img = frame.toImage()
        if img.isNull():
            return
        if self._max_w and self._max_h and (img.width() > self._max_w or img.height() > self._max_h):
            img = img.scaled(
                self._max_w, self._max_h,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        from PyQt6.QtGui import QPixmap
        self._frame = QPixmap.fromImage(img)
        self._ultimo_frame_ts = ahora
        self._frames_contados += 1
        self.update()

    def _medir_rendimiento(self):
        fps_medido = self._frames_contados * 1000 / _INTERVALO_MEDICION_FPS_MS
        self._frames_contados = 0
        if self._ruta is None or self.calidad == 'desactivar':
            return
        if self._fps_limit and fps_medido < self._fps_limit * 0.5:
            idx = _ORDEN_CALIDAD.index(self.calidad)
            if idx < len(_ORDEN_CALIDAD) - 1:
                nueva = _ORDEN_CALIDAD[idx + 1]
                self.set_calidad(nueva)
                self.calidad_cambiada.emit(nueva)

    def set_calidad(self, calidad):
        if calidad not in CALIDAD_VIDEO:
            calidad = 'alta'
        self.calidad = calidad
        preset = CALIDAD_VIDEO[calidad]
        if preset is None:
            self._max_w = self._max_h = self._fps_limit = None
            self.set_video(None)
        else:
            self._max_w, self._max_h, self._fps_limit = preset
            if self._ruta and self._player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                self._player.play()

    def set_opacidad(self, valor):
        self.opacidad = valor
        self.update()

    def set_opacidad_ventana(self, valor):
        self.opacidad_ventana = valor
        self.update()

    def set_rendimiento(self, activo):
        self.rendimiento = activo

    def set_video(self, ruta):
        self._ruta = ruta
        if ruta and self.calidad != 'desactivar':
            self._player.setSource(QUrl.fromLocalFile(ruta))
            self._player.play()
            self._frames_contados = 0
            self._fps_timer.start()
        else:
            self._player.stop()
            self._player.setSource(QUrl())
            self._frame = None
            self._fps_timer.stop()
            self.update()

    def detener(self):
        self._player.stop()
        self._fps_timer.stop()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update()

    def paintEvent(self, event):
        if self._ruta is None or self._frame is None:
            return
        if self.opacidad <= 0 or self.opacidad_ventana <= 0:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        op = (self.opacidad / 100) * (self.opacidad_ventana / 100)
        p.setOpacity(op)
        r = self.rect()
        escalado = self._frame.scaled(
            r.size(),
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = (r.width() - escalado.width()) // 2
        y = (r.height() - escalado.height()) // 2
        p.drawPixmap(x, y, escalado)
        p.end()


class SeccionFondoAnimado(QWidget):
    def __init__(self, ventana, config):
        super().__init__()
        self.ventana = ventana

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        self.btn_toggle = QPushButton()
        self.btn_toggle.setObjectName("btnHeader")
        self.btn_toggle.clicked.connect(self._on_toggle)
        lay.addWidget(self.btn_toggle)

        self.w_opciones = QWidget()
        opciones = QVBoxLayout(self.w_opciones)
        opciones.setContentsMargins(0, 4, 0, 0)
        opciones.setSpacing(6)

        fila_tipos = QHBoxLayout()
        self.grupo_tipos = QButtonGroup(self)
        self.grupo_tipos.setExclusive(True)
        self._botones_tipo = {}
        for clave, etiqueta in ANIMACIONES_PRESET:
            btn = QPushButton(etiqueta)
            btn.setCheckable(True)
            btn.setObjectName("btnHeader")
            btn.clicked.connect(lambda _checked, c=clave: self._on_tipo(c))
            self.grupo_tipos.addButton(btn)
            self._botones_tipo[clave] = btn
            fila_tipos.addWidget(btn)
        opciones.addLayout(fila_tipos)

        fila_velocidad = QHBoxLayout()
        fila_velocidad.addWidget(QLabel("Velocidad:"))
        self.grupo_velocidad = QButtonGroup(self)
        self.grupo_velocidad.setExclusive(True)
        self._botones_velocidad = {}
        for vel in VELOCIDADES:
            btn = QPushButton(vel.capitalize())
            btn.setCheckable(True)
            btn.setObjectName("btnHeader")
            btn.clicked.connect(lambda _checked, v=vel: self._on_velocidad(v))
            self.grupo_velocidad.addButton(btn)
            self._botones_velocidad[vel] = btn
            fila_velocidad.addWidget(btn)
        opciones.addLayout(fila_velocidad)

        fila_opacidad = QHBoxLayout()
        fila_opacidad.addWidget(QLabel("Opacidad:"))
        self.slider_opacidad = QSlider(Qt.Orientation.Horizontal)
        self.slider_opacidad.setRange(0, 100)
        self.slider_opacidad.valueChanged.connect(self._on_opacidad)
        fila_opacidad.addWidget(self.slider_opacidad)
        opciones.addLayout(fila_opacidad)

        self.btn_rendimiento = QPushButton()
        self.btn_rendimiento.setObjectName("btnHeader")
        self.btn_rendimiento.setCheckable(True)
        self.btn_rendimiento.clicked.connect(self._on_rendimiento)
        opciones.addWidget(self.btn_rendimiento)

        self.btn_video = QPushButton("🎬 Elegir video de fondo...")
        self.btn_video.setObjectName("btnHeader")
        self.btn_video.clicked.connect(self._seleccionar_video)
        opciones.addWidget(self.btn_video)

        self.btn_quitar_video = QPushButton("✕ Quitar video de fondo")
        self.btn_quitar_video.setObjectName("btnHeader")
        self.btn_quitar_video.clicked.connect(lambda: self.ventana.set_video_fondo(None))
        opciones.addWidget(self.btn_quitar_video)

        fila_opacidad_video = QHBoxLayout()
        fila_opacidad_video.addWidget(QLabel("Opacidad del video:"))
        self.slider_opacidad_video = QSlider(Qt.Orientation.Horizontal)
        self.slider_opacidad_video.setRange(0, 100)
        self.slider_opacidad_video.valueChanged.connect(self._on_opacidad_video)
        fila_opacidad_video.addWidget(self.slider_opacidad_video)
        opciones.addLayout(fila_opacidad_video)

        fila_calidad = QHBoxLayout()
        fila_calidad.addWidget(QLabel("Calidad del fondo:"))
        self.grupo_calidad = QButtonGroup(self)
        self.grupo_calidad.setExclusive(True)
        self._botones_calidad = {}
        for clave, etiqueta in CALIDADES_FONDO:
            btn = QPushButton(etiqueta)
            btn.setCheckable(True)
            btn.setObjectName("btnHeader")
            btn.clicked.connect(lambda _checked, c=clave: self._on_calidad(c))
            self.grupo_calidad.addButton(btn)
            self._botones_calidad[clave] = btn
            fila_calidad.addWidget(btn)
        opciones.addLayout(fila_calidad)

        fila_opacidad_panel = QHBoxLayout()
        fila_opacidad_panel.addWidget(QLabel("Opacidad del panel:"))
        self.slider_opacidad_panel = QSlider(Qt.Orientation.Horizontal)
        self.slider_opacidad_panel.setRange(10, 100)
        self.slider_opacidad_panel.valueChanged.connect(self._on_opacidad_panel)
        fila_opacidad_panel.addWidget(self.slider_opacidad_panel)
        opciones.addLayout(fila_opacidad_panel)

        lbl_aviso = QLabel("El área del navegador no puede ser transparente")
        lbl_aviso.setStyleSheet("color: #888888; font-size: 9px;")
        lbl_aviso.setWordWrap(True)
        opciones.addWidget(lbl_aviso)

        lay.addWidget(self.w_opciones)

        self.actualizar(config)

    def _titulo(self, activo):
        return "🌌 Fondo animado: " + ("ON ▲" if activo else "OFF ▼")

    def _actualizar_texto_toggle(self, activo):
        self.btn_toggle.setText(self._titulo(activo))
        self.w_opciones.setVisible(activo)

    def _actualizar_texto_rendimiento(self, activo):
        self.btn_rendimiento.setText("⚡ Modo rendimiento: " + ("ON" if activo else "OFF"))

    def _on_toggle(self):
        cfg = self.ventana.config_personalizacion
        activo = not cfg.get('fondo_animado_activo', False)
        self._actualizar_texto_toggle(activo)
        self.ventana.set_fondo_animado_activo(activo)

    def _on_tipo(self, tipo):
        self.ventana.set_fondo_animado_tipo(tipo)

    def _on_velocidad(self, velocidad):
        self.ventana.set_fondo_animado_velocidad(velocidad)

    def _on_opacidad(self, valor):
        self.ventana.set_fondo_animado_opacidad(valor)

    def _on_rendimiento(self):
        cfg = self.ventana.config_personalizacion
        activo = not cfg.get('fondo_animado_rendimiento', False)
        self._actualizar_texto_rendimiento(activo)
        self.ventana.set_fondo_animado_rendimiento(activo)

    def _on_opacidad_video(self, valor):
        self.ventana.set_fondo_video_opacidad(valor)

    def _on_opacidad_panel(self, valor):
        self.ventana.set_fondo_panel_opacidad(valor)

    def _on_calidad(self, calidad):
        self.ventana.set_fondo_video_calidad(calidad)

    def _seleccionar_video(self):
        ruta, _ = QFileDialog.getOpenFileName(
            self, "Elegir video de fondo", "", "Video (*.mp4 *.avi *.mov *.mkv *.webm)"
        )
        if ruta:
            self.ventana.set_video_fondo(ruta)

    def actualizar(self, config):
        activo = config.get('fondo_animado_activo', False)
        tipo = config.get('fondo_animado_tipo', 'particulas')
        velocidad = config.get('fondo_animado_velocidad', 'normal')
        opacidad = config.get('fondo_animado_opacidad', 30)
        rendimiento = config.get('fondo_animado_rendimiento', False)
        opacidad_video = config.get('fondo_video_opacidad', 40)
        calidad = config.get('fondo_video_calidad', 'alta')
        opacidad_panel = config.get('fondo_panel_opacidad', 85)

        self._actualizar_texto_toggle(activo)

        boton_tipo = self._botones_tipo.get(tipo)
        if boton_tipo is not None:
            boton_tipo.setChecked(True)

        boton_velocidad = self._botones_velocidad.get(velocidad)
        if boton_velocidad is not None:
            boton_velocidad.setChecked(True)

        self.slider_opacidad.blockSignals(True)
        self.slider_opacidad.setValue(opacidad)
        self.slider_opacidad.blockSignals(False)

        self.btn_rendimiento.setChecked(rendimiento)
        self._actualizar_texto_rendimiento(rendimiento)

        self.slider_opacidad_video.blockSignals(True)
        self.slider_opacidad_video.setValue(opacidad_video)
        self.slider_opacidad_video.blockSignals(False)

        boton_calidad = self._botones_calidad.get(calidad)
        if boton_calidad is not None:
            boton_calidad.setChecked(True)

        self.slider_opacidad_panel.blockSignals(True)
        self.slider_opacidad_panel.setValue(opacidad_panel)
        self.slider_opacidad_panel.blockSignals(False)
