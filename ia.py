import base64
from config import SERVER_URL
from security import create_session
import auth_manager

AUTH_ERROR = "__AUTH_ERROR__"


def preguntar_ia(img_base64):
    token = auth_manager.cargar_token()
    if not token:
        return AUTH_ERROR, -1

    try:
        img_bytes = base64.b64decode(img_base64)
        r = create_session().post(
            f"{SERVER_URL}/captures/analyze",
            files={'image': ('captura.png', img_bytes, 'image/png')},
            headers={'Authorization': f'Bearer {token}'},
            timeout=60,
        )
        if r.status_code in (401, 403):
            return AUTH_ERROR, -1
        if r.status_code != 200:
            detail = r.json().get('detail', 'Error del servidor')
            return f"Error: {detail}", -1

        data = r.json()
        return data.get('answer', ''), data.get('captures_remaining', -1)
    except Exception as e:
        return f"Error: {str(e)}", -1
