import sys
from PyQt6.QtWidgets import QApplication
from simple_downloader import SimpleDownloaderWindow
import auth_manager

if '--token' in sys.argv:
    idx = sys.argv.index('--token')
    if idx + 1 < len(sys.argv):
        auth_manager.guardar_token(sys.argv[idx + 1])
        auth_manager.limpiar_marca_sesion_invalida()

app = QApplication(sys.argv)
w = SimpleDownloaderWindow()
w.show()
sys.exit(app.exec())
