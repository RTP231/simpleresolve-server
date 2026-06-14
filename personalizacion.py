import os
import json

_CONFIG_DIR = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'SimpleResolve')
_CONFIG_PATH = os.path.join(_CONFIG_DIR, 'personalizacion.json')

DEFAULTS = {
    'color_fondo': None,
    'color_botones': None,
    'opacidad_botones': 100,
    'imagen_fondo': None,
    'opacidad_imagen': 50,
    'pos_x': None,
    'pos_y': None,
    'fondo_animado_activo': False,
    'fondo_animado_tipo': 'particulas',
    'fondo_animado_velocidad': 'normal',
    'fondo_animado_opacidad': 30,
    'fondo_animado_rendimiento': False,
    'video_fondo': None,
    'fondo_video_opacidad': 40,
    'fondo_video_calidad': 'alta',
    'fondo_panel_opacidad': 85,
    'opacidad_pestanas': 100,
    'color_marco': None,
}


def cargar_config():
    try:
        with open(_CONFIG_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        cfg = DEFAULTS.copy()
        cfg.update(data)
        return cfg
    except (FileNotFoundError, json.JSONDecodeError):
        return DEFAULTS.copy()


def guardar_config(config):
    os.makedirs(_CONFIG_DIR, exist_ok=True)
    with open(_CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f)
