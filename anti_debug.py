"""Comprobación anti-debugging básica para Windows.

Se importa al principio de los puntos de entrada (SimpleHub.py, main.py):
si detecta que el proceso está siendo depurado, cierra la app en silencio.
Solo tiene efecto en Windows; en otros sistemas no hace nada.
"""

import ctypes
import sys


def check_debugger():
    try:
        kernel32 = ctypes.windll.kernel32

        if kernel32.IsDebuggerPresent():
            sys.exit(0)

        is_debugged = ctypes.c_bool(False)
        kernel32.CheckRemoteDebuggerPresent(
            kernel32.GetCurrentProcess(),
            ctypes.byref(is_debugged),
        )
        if is_debugged.value:
            sys.exit(0)
    except Exception:
        pass


check_debugger()
