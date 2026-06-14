from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QWidget
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QPoint
from PyQt6.QtGui import QPainter, QBrush, QColor, QPen, QLinearGradient, QPainterPath, QFont
from config import SERVER_URL
from security import create_session
import auth_manager


class HiloLogin(QThread):
    terminado = pyqtSignal(bool, str, str)

    def __init__(self, email, password, parent=None):
        super().__init__(parent)
        self.email = email
        self.password = password

    def run(self):
        try:
            r = create_session().post(
                f"{SERVER_URL}/auth/login",
                json={'email': self.email, 'password': self.password},
                timeout=15,
            )
            if r.status_code == 200:
                self.terminado.emit(True, r.json().get('access_token', ''), '')
                return
            detail = r.json().get('detail', 'Credenciales incorrectas')
            self.terminado.emit(False, '', detail)
            return
        except Exception as e:
            self.terminado.emit(False, '', f'Sin conexión: {e}')
            return


class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.token = None
        self._drag_pos = QPoint()
        self._hilo = None
        self._initUI()

    def _initUI(self):
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(280)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.glass = QWidget()
        outer.addWidget(self.glass)

        lay = QVBoxLayout(self.glass)
        lay.setContentsMargins(20, 16, 20, 20)
        lay.setSpacing(10)

        lbl_titulo = QLabel("SimpleResolve")
        lbl_titulo.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        lbl_titulo.setStyleSheet("color: #eaeaf5; background: transparent;")
        lay.addWidget(lbl_titulo)

        lbl_sub = QLabel("Inicia sesión para continuar")
        lbl_sub.setStyleSheet("color: #7c7ca0; font-size: 10px; background: transparent;")
        lay.addWidget(lbl_sub)

        lay.addSpacing(4)

        QLabel_email = QLabel("Email")
        QLabel_email.setStyleSheet("color: #9898b8; font-size: 10px; background: transparent;")
        lay.addWidget(QLabel_email)

        self.inp_email = QLineEdit()
        self.inp_email.setPlaceholderText("correo@ejemplo.com")
        self.inp_email.setObjectName("inputField")
        lay.addWidget(self.inp_email)

        QLabel_pass = QLabel("Contraseña")
        QLabel_pass.setStyleSheet("color: #9898b8; font-size: 10px; background: transparent;")
        lay.addWidget(QLabel_pass)

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

        self.glass.setStyleSheet("""
            QWidget { background: transparent; }
            QLineEdit#inputField {
                background: rgba(255,255,255,0.07);
                border: 1px solid rgba(124,111,255,0.35);
                border-radius: 7px;
                padding: 6px 10px;
                color: #eaeaf5;
                font-size: 12px;
                selection-background-color: rgba(124,111,255,0.4);
            }
            QLineEdit#inputField:focus {
                border: 1px solid rgba(124,111,255,0.8);
                background: rgba(255,255,255,0.1);
            }
            QPushButton#btnSubmit {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #7c6fff,stop:1 #5a4fcf);
                color: white;
                border: none;
                border-radius: 7px;
                padding: 8px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton#btnSubmit:hover {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #9d97ff,stop:1 #7c6fff);
            }
            QPushButton#btnSubmit:disabled {
                background: rgba(42,41,64,180);
                color: #55547a;
            }
        """)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()
        path = QPainterPath()
        path.addRoundedRect(r.x(), r.y(), r.width(), r.height(), 16, 16)

        grad = QLinearGradient(0, 0, r.width(), r.height())
        grad.setColorAt(0.0, QColor(18, 16, 32, 240))
        grad.setColorAt(0.5, QColor(22, 20, 40, 230))
        grad.setColorAt(1.0, QColor(14, 12, 28, 240))
        p.fillPath(path, QBrush(grad))

        p.setPen(QPen(QColor(124, 111, 255, 80), 1))
        p.drawPath(path)

        shine = QLinearGradient(0, 0, r.width(), 0)
        shine.setColorAt(0.0, QColor(255, 255, 255, 0))
        shine.setColorAt(0.3, QColor(255, 255, 255, 25))
        shine.setColorAt(0.7, QColor(255, 255, 255, 25))
        shine.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setPen(QPen(QBrush(shine), 1))
        p.drawLine(20, 1, r.width() - 20, 1)

        p.end()

    def _on_submit(self):
        email = self.inp_email.text().strip()
        password = self.inp_pass.text()

        if not (email and password):
            self._set_error("Completa todos los campos.")
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
            auth_manager.guardar_token(token)
            self.token = token
            self.accept()
            return
        self._set_error(error)

    def _set_error(self, msg):
        if msg:
            self.lbl_error.setText(msg)
            self.lbl_error.setVisible(True)
            return
        self.lbl_error.setVisible(False)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            return None
        return None

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            return None
        return None
