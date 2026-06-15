"""Identificador estable del equipo, usado para atar la sesión guardada
(token) y la configuración cifrada a la máquina donde se inició sesión."""

import uuid
import hashlib
import platform


def get_hardware_id():
    raw = f"{uuid.getnode()}{platform.node()}{platform.processor()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]
