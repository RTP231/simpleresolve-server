# URL del backend (simpleresolve-server). Apuntar al deploy real del servidor.
SERVER_URL = "http://127.0.0.1:8000"

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