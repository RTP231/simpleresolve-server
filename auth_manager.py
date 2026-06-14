import os
import json
from personalizacion import _CONFIG_DIR

_TOKEN_PATH = os.path.join(_CONFIG_DIR, 'auth.json')
_SESION_INVALIDA_PATH = os.path.join(_CONFIG_DIR, 'session_invalid.flag')


def cargar_token():
    try:
        with open(_TOKEN_PATH, 'r', encoding='utf-8') as f:
            return json.load(f).get('token')
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return None


def guardar_token(token):
    os.makedirs(_CONFIG_DIR, exist_ok=True)
    with open(_TOKEN_PATH, 'w', encoding='utf-8') as f:
        json.dump({'token': token}, f)


def borrar_token():
    try:
        os.remove(_TOKEN_PATH)
    except FileNotFoundError:
        pass


def marcar_sesion_invalida():
    """Señala a las demás apps abiertas (SimpleResolve, SimpleDownloader)
    que deben cerrar sesión. Se usa cuando SimpleHub detecta que la cuenta
    fue desactivada o la sesión expiró."""
    os.makedirs(_CONFIG_DIR, exist_ok=True)
    open(_SESION_INVALIDA_PATH, 'w').close()


def hay_sesion_invalida():
    return os.path.exists(_SESION_INVALIDA_PATH)


def limpiar_marca_sesion_invalida():
    try:
        os.remove(_SESION_INVALIDA_PATH)
    except FileNotFoundError:
        pass
