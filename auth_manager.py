import os
import json
import time
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from personalizacion import _CONFIG_DIR
from hardware_id import get_hardware_id

_TOKEN_PATH = os.path.join(_CONFIG_DIR, 'auth.dat')
_LEGACY_TOKEN_PATH = os.path.join(_CONFIG_DIR, 'auth.json')
_SESION_INVALIDA_PATH = os.path.join(_CONFIG_DIR, 'session_invalid.flag')
_INTENTOS_PATH = os.path.join(_CONFIG_DIR, 'login_attempts.dat')

MAX_INTENTOS_FALLIDOS = 5
BLOQUEO_SEGUNDOS = 30 * 60


def _get_fernet():
    """Clave derivada del hardware del equipo: el token cifrado solo puede
    leerse en la misma máquina donde se guardó."""
    hw = get_hardware_id()
    key = base64.urlsafe_b64encode(hashlib.sha256(hw.encode()).digest())
    return Fernet(key)


# ----------------------------------------------------------------------
# Token de sesión
# ----------------------------------------------------------------------
def cargar_token():
    try:
        with open(_TOKEN_PATH, 'rb') as fh:
            data = json.loads(_get_fernet().decrypt(fh.read()).decode())
        if data.get('hardware_id') != get_hardware_id():
            return None
        return data.get('token')
    except (FileNotFoundError, InvalidToken, json.JSONDecodeError, KeyError, ValueError):
        return _migrar_token_legacy()


def _migrar_token_legacy():
    """Compatibilidad con el formato anterior (auth.json en texto plano)."""
    try:
        with open(_LEGACY_TOKEN_PATH, 'r', encoding='utf-8') as fh:
            token = json.load(fh).get('token')
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return None

    if token:
        guardar_token(token)
        try:
            os.remove(_LEGACY_TOKEN_PATH)
        except FileNotFoundError:
            pass
    return token


def guardar_token(token):
    os.makedirs(_CONFIG_DIR, exist_ok=True)
    payload = json.dumps({'token': token, 'hardware_id': get_hardware_id()}).encode()
    with open(_TOKEN_PATH, 'wb') as fh:
        fh.write(_get_fernet().encrypt(payload))


def borrar_token():
    for path in (_TOKEN_PATH, _LEGACY_TOKEN_PATH):
        try:
            os.remove(path)
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


# ----------------------------------------------------------------------
# Rate limiting de intentos de login (local, por equipo)
# ----------------------------------------------------------------------
def _cargar_intentos():
    try:
        with open(_INTENTOS_PATH, 'rb') as fh:
            return json.loads(_get_fernet().decrypt(fh.read()).decode())
    except (FileNotFoundError, InvalidToken, json.JSONDecodeError, ValueError):
        return {'fallidos': 0, 'bloqueado_hasta': 0}


def _guardar_intentos(data):
    os.makedirs(_CONFIG_DIR, exist_ok=True)
    with open(_INTENTOS_PATH, 'wb') as fh:
        fh.write(_get_fernet().encrypt(json.dumps(data).encode()))


def verificar_bloqueo():
    """Devuelve (bloqueado, segundos_restantes)."""
    data = _cargar_intentos()
    restante = data.get('bloqueado_hasta', 0) - time.time()
    if restante > 0:
        return True, int(restante)
    return False, 0


def registrar_intento_fallido():
    data = _cargar_intentos()
    if data.get('bloqueado_hasta', 0) > time.time():
        return
    data['fallidos'] = data.get('fallidos', 0) + 1
    if data['fallidos'] >= MAX_INTENTOS_FALLIDOS:
        data['fallidos'] = 0
        data['bloqueado_hasta'] = time.time() + BLOQUEO_SEGUNDOS
    _guardar_intentos(data)


def registrar_intento_exitoso():
    _guardar_intentos({'fallidos': 0, 'bloqueado_hasta': 0})
