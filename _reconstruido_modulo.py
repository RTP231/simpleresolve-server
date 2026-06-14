# Funciones a nivel de módulo reconstruidas desde bytecode (interfaz.pyc)
# Se integrarán al inicio de interfaz.py en el paso final.
# NOTA: requieren imports adicionales: sys, os, threading, y create_session/SERVER_URL
# (verificar si create_session/SERVER_URL ya existen en config.py o auth_manager.py).

def _resource(filename):
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, filename)


def _log_event(event_type: str) -> None:
    """Envía un evento de uso al servidor en hilo separado (fire-and-forget)."""
    def _send():
        try:
            token = auth_manager.cargar_token()
            if not token:
                return
            create_session().post(
                f"{SERVER_URL}/events/log",
                data={'event_type': event_type, 'app_version': '2.0'},
                headers={'Authorization': f'Bearer {token}'},
                timeout=5,
            )
        except Exception:
            return
    threading.Thread(target=_send, daemon=True).start()
