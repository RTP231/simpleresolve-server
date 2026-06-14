import os
import sys

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QIcon

from interfaz import PanelGlass, _resource
import simplepdf_config as config


class SimplePDF(QWidget):
    """Ventana de SimplePDF (versión simplificada — próximamente funcionalidad completa)."""

    def __init__(self, ventana_resolve=None):
        super().__init__()
        self.ventana_resolve = ventana_resolve
        self.cerrado = False
        self.drag_pos = QPoint()
        self.config_personalizacion = config.cargar_config()
        self._initUI()

    def _initUI(self):
        self.setWindowTitle("SimplePDF")
        self.setWindowIcon(QIcon(_resource('icon.ico')))
        self.setFixedSize(360, 200)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        pos_x = self.config_personalizacion.get('pos_x')
        pos_y = self.config_personalizacion.get('pos_y')
        if pos_x is not None and pos_y is not None:
            self.move(pos_x, pos_y)

        lay = QVBoxLayout()
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.setLayout(lay)

        self.glass = PanelGlass(oscuro=True)
        lay.addWidget(self.glass)

        c = QVBoxLayout()
        c.setContentsMargins(12, 8, 12, 12)
        c.setSpacing(8)
        self.glass.setLayout(c)

        header = QHBoxLayout()
        titulo = QLabel("📄 SimplePDF")
        titulo.setStyleSheet("color: #f0f0ff; font-size: 14px; font-weight: bold; background: transparent;")
        header.addWidget(titulo)
        header.addStretch()

        btn_cerrar = QPushButton("✕")
        btn_cerrar.setFixedSize(24, 24)
        btn_cerrar.setStyleSheet("""
            QPushButton { color: #f0f0ff; background: transparent; border: none; font-size: 14px; }
            QPushButton:hover { color: #ff6b8a; }
        """)
        btn_cerrar.clicked.connect(self.close)
        header.addWidget(btn_cerrar)
        c.addLayout(header)

        info = QLabel("Próximamente: edición y conversión de PDF directamente desde SimpleResolve.")
        info.setWordWrap(True)
        info.setStyleSheet("color: #c8c8e0; font-size: 12px; background: transparent;")
        c.addWidget(info)
        c.addStretch()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_pos)

    def closeEvent(self, event):
        self.cerrado = True
        self.config_personalizacion['pos_x'] = self.x()
        self.config_personalizacion['pos_y'] = self.y()
        config.guardar_config(self.config_personalizacion)
        super().closeEvent(event)
