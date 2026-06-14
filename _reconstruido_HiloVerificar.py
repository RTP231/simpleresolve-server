# Clase HiloVerificar reconstruida desde bytecode (interfaz.pyc)
# Se integrará en interfaz.py en el paso final.
# NOTA: usa create_session() y SERVER_URL, definidos en otro lugar de interfaz.py (revisar al integrar).

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
