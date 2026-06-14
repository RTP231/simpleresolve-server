# PanelGlass.__init__ y paintEvent reconstruidos desde bytecode (interfaz.pyc)
# Reemplazan a los métodos viejos del mismo nombre en PanelGlass.
# Se integrarán en interfaz.py en el paso final, junto con los métodos
# nuevos de _reconstruido_PanelGlass.py (resizeEvent, set_color_fondo, etc.)

    def __init__(self, oscuro, parent=None):
        super().__init__(parent)
        self.oscuro = oscuro
        self.transparente = False
        self.color_fondo = None
        self.pixmap_fondo = None
        self.opacidad_imagen = 50
        self.fondo_animado = AnimacionFondoWidget(self)
        self.fondo_video = FondoVideoWidget(self)
        self.fondo_animado.lower()
        self.fondo_video.lower()

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

        if self.oscuro:
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
