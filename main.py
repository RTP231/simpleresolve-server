import sys
from PyQt6.QtWidgets import QApplication
from interfaz import SimpleResolve
import auth_manager


def _aplicar_token_cli():
    if '--token' in sys.argv:
        idx = sys.argv.index('--token')
        if idx + 1 < len(sys.argv):
            auth_manager.guardar_token(sys.argv[idx + 1])
            auth_manager.limpiar_marca_sesion_invalida()


def main():
    _aplicar_token_cli()
    app = QApplication(sys.argv)
    ventana = SimpleResolve()
    ventana.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
