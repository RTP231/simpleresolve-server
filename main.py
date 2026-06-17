import anti_debug  # noqa: F401  (verifica al importar; debe ir primero)

import sys

import integrity
integrity.verificar_integridad_o_salir()

from PyQt6.QtWidgets import QApplication
from interfaz import SimpleResolve
import auth_manager
import marcadores


def _aplicar_token_cli():
    if '--token' in sys.argv:
        idx = sys.argv.index('--token')
        if idx + 1 < len(sys.argv):
            auth_manager.guardar_token(sys.argv[idx + 1])
            auth_manager.limpiar_marca_sesion_invalida()


def main():
    if getattr(sys, 'frozen', False):
        marcadores.crear_marcador('SimpleResolver.exe')
    _aplicar_token_cli()
    app = QApplication(sys.argv)
    ventana = SimpleResolve()
    ventana.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
