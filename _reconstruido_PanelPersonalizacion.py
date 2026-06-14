# Clase PanelPersonalizacion reconstruida desde bytecode (interfaz.pyc)
# Se integrará en interfaz.py en el paso final.

class PanelPersonalizacion(QWidget):
    """Panel de personalización: colores y fondo personalizado."""

    def __init__(self, ventana, parent=None):
        super().__init__(parent)
        self.ventana = ventana
        self.setWindowTitle('Personalización')
        self.setFixedWidth(280)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

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
        for color in PRESETS_BOTONES:
            fila_botones.addWidget(self._swatch(color, self._set_color_botones))
        lay.addLayout(fila_botones)

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

    def _swatch(self, color, callback):
        b = QPushButton()
        b.setFixedSize(28, 28)
        b.setStyleSheet(f'background-color: {color}; border-radius: 4px; border: 1px solid rgba(128,128,128,0.5);')
        b.clicked.connect(lambda c=color: callback(c))
        return b

    def _set_color_fondo(self, color_hex):
        self.ventana.set_color_fondo(color_hex)

    def _elegir_color_fondo_custom(self):
        actual = self.ventana.config_personalizacion.get('color_fondo') or '#121020'
        color = QColorDialog.getColor(QColor(actual), self, 'Color de fondo')
        if color.isValid():
            self.ventana.set_color_fondo(color.name())

    def _set_color_botones(self, color_hex):
        self.ventana.set_color_botones(color_hex)

    def _elegir_color_botones_custom(self):
        actual = self.ventana.config_personalizacion.get('color_botones') or '#7c6fff'
        color = QColorDialog.getColor(QColor(actual), self, 'Color de botones')
        if color.isValid():
            self.ventana.set_color_botones(color.name())

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
        self.seccion_fondo_animado.actualizar(self.ventana.config_personalizacion)
