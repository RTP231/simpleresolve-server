# URL del backend (simpleresolve-server). Deploy real en Railway.
# Guardada cifrada para que no quede como texto plano en el ejecutable
# (ver _keys.py para una nota sobre el alcance real de esta protección).
from cryptography.fernet import Fernet
from _keys import OBFUSCATION_KEY

_ENC_SERVER_URL = (
    b"gAAAAABqMGksPZ4svOVkEO1uAzXE4-_mC7Sykd56uYjDMNW6-fkdRr-si8A0Cr5rrFxLQeYgsnuxlqP-"
    b"MdynUIpeFSB67-6YHdjI8LcNjKKJCjXOjsng-LKlWXzFgqKYFmi6GsoQ8SImnOykd17q9qzEaPzFklk4Lg=="
)

SERVER_URL = Fernet(OBFUSCATION_KEY).decrypt(_ENC_SERVER_URL).decode()

API_KEY = "Key Borrada "

MODELO = "claude-sonnet-4-6"

PROMPT = """Look at the image. Answer EVERY question. One answer per line.

FORMAT — each answer on its OWN LINE:
1. B
2. x = 7
3. C

RULES:
- Multiple choice → letter only (A, B, C or D)
- Equation/blank → only the value or expression
- Each number on a SEPARATE LINE, never on the same line
- NO explanations, NO words, NOTHING extra
- Start directly with: 1."""

MAX_CAPTURAS = 100
