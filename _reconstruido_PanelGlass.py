# Métodos nuevos de la clase PanelGlass reconstruidos desde bytecode (interfaz.pyc)
# Se integrarán en interfaz.py en el paso final.

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

    def set_pixmap_fondo(self, pixmap):
        self.pixmap_fondo = pixmap
        self.update()

    def set_opacidad_imagen(self, valor):
        self.opacidad_imagen = valor
        self.update()
