"""SimpleDownloader - ventana independiente para descargar videos detectados
en un navegador embebido (Chrome real vía Selenium), usando yt-dlp como
motor de descarga.

Uso desde la app principal:

    from simple_downloader import SimpleDownloaderWindow
    self.downloader = SimpleDownloaderWindow()
    self.downloader.show()
"""
import os
import sys
import shutil
import subprocess
import time

import json
import re
import uuid
from datetime import datetime
from urllib.parse import urlparse, quote_plus

from PyQt6.QtCore import (
    Qt, QUrl, pyqtSignal, pyqtProperty, QThread, QPointF, QRectF,
    QPropertyAnimation, QEasingCurve, QSequentialAnimationGroup, QSettings, QTimer,
)
from PyQt6.QtGui import QColor, QPainter, QBrush, QPixmap, QLinearGradient, QPainterPath, QIcon
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLineEdit,
    QPushButton, QLabel, QButtonGroup, QProgressBar, QFileDialog, QScrollArea,
    QFrame, QMessageBox, QTabBar, QStackedWidget, QGraphicsOpacityEffect,
)

from webview2_browser import WebView2BrowserWidget, IGNORE_URL_PATTERNS

import yt_dlp
import requests

try:
    import imageio_ffmpeg
    _FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    _FFMPEG_PATH = None

from interfaz import PanelGlass, PanelPersonalizacion
from fondo_animado import AnimacionFondoWidget, FondoVideoWidget
import personalizacion
import auth_manager
import marcadores

if getattr(sys, 'frozen', False):
    marcadores.crear_marcador('SimpleDownloader.exe')


_VIDEO_EXT_RE = re.compile(r'\.(mp4|m3u8|ts|webm|mkv)(?:[?#]|$)', re.IGNORECASE)

# Paleta de colores fija del rediseño visual de SimpleDownloader.
_C_BG_APP = '#0d0d0d'
_C_BG_PANEL = '#111111'
_C_BG_EL = '#1a1a1a'
_C_BORDER = '#222222'
_C_TEXT = '#ffffff'
_C_TEXT_SEC = '#888888'
_C_TEXT_HINT = '#555555'
_C_RED = '#ff4444'
_C_PURPLE = '#8b5cf6'
_C_GREEN = '#00ff88'
_C_YELLOW = '#f59e0b'
_C_BLUE = '#2563eb'

_QUALITY_HEIGHT = {
    'Mejor (4K)': 2160,
    '1080p': 1080,
    '720p': 720,
    '480p': 480,
    '360p': 360,
}

_QUALITY_SUBTITLES = {
    'Mejor (4K)': '3840×2160',
    '1080p': '1920×1080',
    '720p': '1280×720',
    '480p': '854×480',
    '360p': '640×360',
    'Solo audio': 'MP3 / M4A',
}

_FORMAT_EXT = {'MP4': 'mp4', 'MKV': 'mkv', 'WEBM': 'webm'}
_AUDIO_FORMATS = {'MP3': 'mp3', 'M4A': 'm4a'}

_INVALID_VIDEO_EXTENSIONS = (
    '.svg', '.png', '.jpg', '.jpeg', '.gif', '.webp',
    '.ico', '.css', '.js', '.json', '.xml', '.html',
)
_MIN_VIDEO_SIZE_BYTES = 1024 * 1024  # 1 MB

_SITIOS_CONOCIDOS = (
    'youtube.com', 'youtu.be', 'tiktok.com', 'instagram.com',
    'twitter.com', 'x.com', 'facebook.com', 'vimeo.com',
    'twitch.tv', 'dailymotion.com',
)

_CHROME_USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
)
_ACCEPT_LANGUAGE = 'es-GT,es;q=0.9,en;q=0.8'

_TIKTOK_HTTP_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Linux; Android 12; SM-G998B) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36'
    ),
    'Referer': 'https://www.tiktok.com/',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': _ACCEPT_LANGUAGE,
    'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120"',
    'sec-ch-ua-mobile': '?1',
    'sec-ch-ua-platform': '"Android"',
}

if getattr(sys, 'frozen', False):
    _APP_DIR = os.path.dirname(sys.executable)
else:
    _APP_DIR = os.path.dirname(os.path.abspath(__file__))

_YOUTUBE_COOKIES_PATH = os.path.join(_APP_DIR, 'youtube_cookies.txt')
_TIKTOK_COOKIES_PATH = os.path.join(_APP_DIR, 'temp_tiktok_cookies.txt')
_FACEBOOK_COOKIES_PATH = os.path.join(_APP_DIR, 'temp_facebook_cookies.txt')


def _get_cookies_file():
    """Devuelve la ruta del archivo de cookies a usar (importado manualmente)."""
    if os.path.exists(_YOUTUBE_COOKIES_PATH):
        return _YOUTUBE_COOKIES_PATH
    return None


def _escribir_cookies_netscape(cookies, path):
    """Escribe una lista de cookies (dicts con name/value/domain/path/expires/
    secure) en formato Netscape, el que espera yt-dlp para `cookiefile`."""
    lineas = ["# Netscape HTTP Cookie File"]
    for c in cookies:
        dominio = c.get('domain') or ''
        incluir_subdominios = 'TRUE' if dominio.startswith('.') else 'FALSE'
        ruta = c.get('path') or '/'
        seguro = 'TRUE' if c.get('secure') else 'FALSE'
        expira = int(c.get('expires') or 0)
        if expira < 0:
            expira = 0
        nombre = c.get('name') or ''
        valor = c.get('value') or ''
        lineas.append('\t'.join([
            dominio, incluir_subdominios, ruta, seguro, str(expira), nombre, valor,
        ]))
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lineas) + '\n')


def _apply_tiktok_opts(opts, url, cookies_file=None):
    """Aplica cabeceras y opciones específicas para que yt-dlp pueda
    descargar de TikTok (evita el error 'generic Unable to do')."""
    if 'tiktok.com' not in url.lower():
        return opts
    opts['http_headers'] = dict(_TIKTOK_HTTP_HEADERS)
    opts['extractor_args'] = {
        'tiktok': {
            'webpage_download': True,
            'api_hostname': 'api22-normal-c-useast2a.tiktokv.com',
        }
    }
    if cookies_file:
        opts['cookiefile'] = cookies_file
    return opts


_FACEBOOK_HTTP_HEADERS = {
    'User-Agent': _CHROME_USER_AGENT,
}


def _apply_facebook_opts(opts, url, cookies_file=None):
    """Aplica cabeceras y cookies para que yt-dlp pueda descargar videos de
    Facebook (muchos requieren estar logueado, aunque sean públicos)."""
    if 'facebook.com' not in url.lower() and 'fb.watch' not in url.lower():
        return opts
    opts['http_headers'] = dict(_FACEBOOK_HTTP_HEADERS)
    if cookies_file:
        opts['cookiefile'] = cookies_file
    return opts


_AUTH_ERROR_RE = re.compile(
    r'sign in|login|cookies|private video|members-only|age[- ]restricted|forbidden|403',
    re.IGNORECASE,
)

# Errores que indican un problema de conectividad (no de la URL/video en
# sí), candidatos a reintentar automáticamente en vez de fallar de una vez.
_ERRORES_RED = ('network', 'connection', 'timeout', 'reset', 'refused', 'unreachable')


def _es_error_de_red(mensaje):
    m = mensaje.lower()
    return any(err in m for err in _ERRORES_RED)


def _mensaje_error_legible(mensaje):
    """Traduce errores técnicos de yt-dlp/red a un texto que el usuario
    entienda. Si no coincide ningún patrón conocido, se devuelve el
    mensaje técnico completo (para poder diagnosticar)."""
    m = mensaje.lower()

    if _es_error_de_red(mensaje):
        return "Sin conexión a internet - reintentando automáticamente"
    if 'private video' in m:
        return "Video privado - no se puede descargar"
    if 'sign in' in m:
        return "Necesitas iniciar sesión en YouTube en el navegador"
    if 'geo' in m and ('restrict' in m or 'block' in m):
        return "Video no disponible en tu región"
    if '403' in mensaje:
        return "Acceso denegado - inicia sesión en el sitio e intenta de nuevo"
    if '404' in mensaje:
        return "Video no encontrado - puede haber sido eliminado"
    if '410' in mensaje:
        return "Video expirado - navega al video e intenta de nuevo"
    return mensaje


_FORMAT_FALLBACK = {
    'Mejor (4K)': 'bestvideo[height<=2160]+bestaudio/bestvideo+bestaudio/best',
    '1080p': 'bestvideo[height<=1080]+bestaudio/bestvideo[height<=720]+bestaudio/best',
    '720p': 'bestvideo[height<=720]+bestaudio/bestvideo[height<=480]+bestaudio/best',
    '480p': 'bestvideo[height<=480]+bestaudio/best',
    '360p': 'bestvideo[height<=360]+bestaudio/best',
}


def _build_ydl_opts(quality, fmt, dest_folder, url='', tiktok_cookies_file=None,
                     facebook_cookies_file=None):
    """Construye las opciones de yt-dlp según calidad, formato y URL elegidos."""
    opts = {
        'outtmpl': os.path.join(dest_folder, '%(title)s.%(ext)s'),
        'noplaylist': True,
        'quiet': True,
        'no_warnings': False,
        'ignoreerrors': False,
        'concurrent_fragment_downloads': 16,
        'http_chunk_size': 10485760,  # 10MB por chunk
        'retries': 10,
        'fragment_retries': 10,
        'file_access_retries': 5,
    }
    if _FFMPEG_PATH:
        opts['ffmpeg_location'] = _FFMPEG_PATH

    # Para videos con muchos fragmentos (HLS/DASH) aria2c es bastante más
    # rápido que el descargador nativo. Si no está instalado, se sigue de
    # largo con concurrent_fragment_downloads (ver Aria2cInstallerWorker,
    # que intenta instalarlo en segundo plano al iniciar la app).
    if shutil.which('aria2c'):
        opts['external_downloader'] = 'aria2c'
        opts['external_downloader_args'] = {
            'aria2c': [
                '--max-connection-per-server=16',
                '--split=16',
                '--min-split-size=1M',
                '--max-concurrent-downloads=16',
                '--continue=true',
            ]
        }

    cookies_file = _get_cookies_file()
    url_lower = url.lower()

    if 'tiktok.com' in url_lower:
        _apply_tiktok_opts(opts, url, tiktok_cookies_file or cookies_file)
    elif 'facebook.com' in url_lower or 'fb.watch' in url_lower:
        _apply_facebook_opts(opts, url, facebook_cookies_file or cookies_file)
    else:
        if cookies_file:
            opts['cookiefile'] = cookies_file
        if 'youtube.com' in url.lower() or 'youtu.be' in url.lower():
            opts['extractor_args'] = {
                'youtube': {
                    'player_client': ['web', 'android', 'ios'],
                    'player_skip': ['webpage', 'configs'],
                }
            }

    postprocessors = []

    if quality == 'Solo audio' or fmt in _AUDIO_FORMATS:
        codec = _AUDIO_FORMATS.get(fmt, 'mp3')
        opts['format'] = 'bestaudio/best'
        postprocessors.append({
            'key': 'FFmpegExtractAudio',
            'preferredcodec': codec,
            'preferredquality': '192',
        })
    else:
        merge_fmt = _FORMAT_EXT.get(fmt, 'mp4')
        opts['format'] = _FORMAT_FALLBACK.get(quality, _FORMAT_FALLBACK['Mejor (4K)'])
        opts['merge_output_format'] = merge_fmt

    opts['postprocessors'] = postprocessors
    return opts


def _get_fresh_url(page_url):
    """Resuelve una URL de stream "fresca" a partir de la URL de la página,
    para evitar enlaces directos expirados (error 410 Gone)."""
    cookies_file = _get_cookies_file()
    opts = {
        'quiet': True,
        'no_warnings': True,
        'http_headers': {'User-Agent': _CHROME_USER_AGENT},
    }
    if 'tiktok.com' in page_url.lower():
        _apply_tiktok_opts(opts, page_url, cookies_file)
    elif cookies_file:
        opts['cookiefile'] = cookies_file
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(page_url, download=False)
        if info is None:
            return None
        url = info.get('url')
        if url:
            return url
        formatos = info.get('formats') or []
        if formatos:
            return formatos[-1].get('url')
    except Exception:
        return None
    return None


def _es_url_valida(url):
    try:
        p = urlparse(url)
        return p.scheme in ('http', 'https') and bool(p.netloc)
    except ValueError:
        return False


def _es_busqueda(texto):
    """True si el texto escrito en la barra parece una búsqueda y no una URL."""
    if ' ' in texto:
        return True
    if '.' not in texto:
        return True
    return False


def _format_size(num_bytes):
    """Convierte bytes a una cadena legible (KB/MB/GB)."""
    if not num_bytes:
        return ""
    valor = float(num_bytes)
    for unidad in ('B', 'KB', 'MB', 'GB'):
        if valor < 1024 or unidad == 'GB':
            if unidad == 'B':
                return f"{valor:.0f} {unidad}"
            return f"{valor:.1f} {unidad}"
        valor /= 1024
    return f"{valor:.1f} TB"


def _estimar_filesize(info, quality):
    """Obtiene el peso del video; si no está directo, lo estima a partir de los formatos."""
    filesize = info.get('filesize') or info.get('filesize_approx')
    if filesize:
        return int(filesize)

    formatos = info.get('formats') or []
    if quality == 'Solo audio':
        candidatos = [f for f in formatos if f.get('vcodec') in (None, 'none')]
    else:
        height = _QUALITY_HEIGHT.get(quality, 2160)
        candidatos = [f for f in formatos if (f.get('height') or 0) <= height]
        if not candidatos:
            candidatos = formatos

    mejor = 0
    for f in candidatos:
        tam = f.get('filesize') or f.get('filesize_approx') or 0
        if tam > mejor:
            mejor = tam
    return int(mejor)


_STREAM_URL_EXTS = ('.mp4', '.m3u8', '.webm', '.ts', '.mov')


class RealStreamResolverWorker(QThread):
    """Resuelve las URLs reales de stream (video/audio) de la página actual
    usando yt-dlp -g, para sitios que solo expongan blob:// en el navegador
    embebido."""

    resolved = pyqtSignal(list)

    def __init__(self, page_url, parent=None):
        super().__init__(parent)
        self.page_url = page_url

    def _get_real_video_url(self, page_url):
        result = subprocess.run(
            ['yt-dlp', '-f', 'all', '-g', '-q', '--ignore-errors', '--no-warnings', page_url],
            capture_output=True, text=True, timeout=20,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        urls = []
        for line in result.stdout.split('\n'):
            line = line.strip()
            if line.startswith('http') and any(ext in line for ext in _STREAM_URL_EXTS):
                urls.append(line)
        return urls

    def run(self):
        try:
            urls = self._get_real_video_url(self.page_url)
        except (OSError, subprocess.SubprocessError):
            urls = []
        self.resolved.emit(urls)


class VideoCardSizeResolverWorker(QThread):
    """Obtiene el peso estimado de un video detectado para mostrarlo en su
    tarjeta: para URLs directas de stream hace un HEAD request y lee
    Content-Length; para URLs de página usa yt-dlp (extract_info)."""

    resolved = pyqtSignal(str, int)             # url, filesize en bytes
    title_resolved = pyqtSignal(str, str)       # url, título real
    thumbnail_resolved = pyqtSignal(str, bytes)  # url, bytes de la miniatura

    def __init__(self, url, parent=None):
        super().__init__(parent)
        self.url = url

    def run(self):
        size = 0
        try:
            path = urlparse(self.url).path
            if _VIDEO_EXT_RE.search(path) or _VIDEO_EXT_RE.search(self.url):
                resp = requests.head(
                    self.url, timeout=6, allow_redirects=True,
                    headers={'User-Agent': _CHROME_USER_AGENT},
                )
                size = int(resp.headers.get('Content-Length') or 0)
            else:
                opts = {'quiet': True, 'no_warnings': True}
                cookies_file = _get_cookies_file()
                if 'tiktok.com' in self.url.lower():
                    _apply_tiktok_opts(opts, self.url, cookies_file)
                else:
                    if cookies_file:
                        opts['cookiefile'] = cookies_file
                    if 'youtube.com' in self.url.lower() or 'youtu.be' in self.url.lower():
                        opts['extractor_args'] = {
                            'youtube': {
                                'player_client': ['web', 'android', 'ios'],
                                'player_skip': ['webpage', 'configs'],
                            }
                        }
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(self.url, download=False)
                if info:
                    formatos = info.get('formats') or []
                    if formatos:
                        mejor = max(
                            formatos,
                            key=lambda f: f.get('filesize') or f.get('filesize_approx') or 0,
                        )
                        size = mejor.get('filesize') or mejor.get('filesize_approx') or 0
                    if not size:
                        size = _estimar_filesize(info, 'Mejor (4K)')
                    titulo = info.get('title')
                    if titulo:
                        self.title_resolved.emit(self.url, titulo)
                    thumb_url = info.get('thumbnail')
                    if thumb_url:
                        try:
                            resp_thumb = requests.get(thumb_url, timeout=6)
                            if resp_thumb.status_code == 200:
                                self.thumbnail_resolved.emit(self.url, resp_thumb.content)
                        except Exception:
                            pass
        except Exception:
            size = 0
        self.resolved.emit(self.url, size)


class YtDlpUpdaterWorker(QThread):
    """Actualiza yt-dlp en segundo plano y en silencio al iniciar la app,
    para que el extractor de TikTok (y otros) esté siempre al día."""

    def run(self):
        try:
            subprocess.run(
                ['pip', 'install', '-U', '--pre', 'yt-dlp', '--quiet'],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except (OSError, subprocess.SubprocessError):
            pass


class Aria2cInstallerWorker(QThread):
    """Instala aria2c en segundo plano si no está disponible, para que las
    descargas con muchos fragmentos (HLS/DASH) vayan más rápido. Si ya está
    instalado, o si falla la instalación, no hace nada: _build_ydl_opts cae
    de vuelta al descargador nativo de yt-dlp con descargas concurrentes."""

    def run(self):
        if shutil.which('aria2c'):
            return
        try:
            subprocess.run(
                [
                    'winget', 'install', 'aria2.aria2', '--silent',
                    '--accept-package-agreements', '--accept-source-agreements',
                ],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=180,
            )
        except (OSError, subprocess.SubprocessError):
            pass


class ThumbnailDownloadWorker(QThread):
    """Descarga la miniatura de una URL (usada para mostrar la miniatura
    del historial al iniciar la app o al guardar un nuevo elemento)."""

    resolved = pyqtSignal(bytes)

    def __init__(self, url, parent=None):
        super().__init__(parent)
        self.url = url

    def run(self):
        data = b''
        try:
            resp = requests.get(self.url, timeout=6, headers={'User-Agent': _CHROME_USER_AGENT})
            if resp.status_code == 200:
                data = resp.content
        except Exception:
            data = b''
        self.resolved.emit(data)


class InfoResolverWorker(QThread):
    """Obtiene título, miniatura y peso de un video antes de descargarlo."""

    resolved = pyqtSignal(str, str, str, int, bytes)  # item_id, titulo, thumb_url, filesize, thumb_bytes
    failed = pyqtSignal(str)                          # item_id

    def __init__(self, item_id, url, quality, parent=None):
        super().__init__(parent)
        self.item_id = item_id
        self.url = url
        self.quality = quality

    def run(self):
        opts = {'quiet': True, 'no_warnings': True, 'extract_flat': False}
        cookies_file = _get_cookies_file()
        if 'tiktok.com' in self.url.lower():
            _apply_tiktok_opts(opts, self.url, cookies_file)
        elif cookies_file:
            opts['cookiefile'] = cookies_file
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(self.url, download=False)

            if info is None:
                self.failed.emit(self.item_id)
                return

            titulo = info.get('title') or 'Video desconocido'
            thumb_url = info.get('thumbnail') or ''
            filesize = _estimar_filesize(info, self.quality)

            thumb_bytes = b''
            if thumb_url:
                try:
                    resp = requests.get(thumb_url, timeout=5)
                    if resp.status_code == 200:
                        thumb_bytes = resp.content
                except Exception:
                    thumb_bytes = b''

            self.resolved.emit(self.item_id, titulo, thumb_url, filesize, thumb_bytes)
        except Exception:
            self.failed.emit(self.item_id)


def _crear_icono_logo():
    """Dibuja un logo minimalista con una 'D' estilizada (degradado azul/púrpura)."""
    pix = QPixmap(24, 24)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    gradiente = QLinearGradient(0, 0, 24, 24)
    gradiente.setColorAt(0, QColor('#5b8dff'))
    gradiente.setColorAt(1, QColor('#9b6fff'))

    path = QPainterPath()
    path.moveTo(3, 2)
    path.arcTo(QRectF(3, 2, 18, 20), 90, -180)
    path.lineTo(3, 22)
    path.closeSubpath()

    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(gradiente))
    p.drawPath(path)
    p.end()
    return QIcon(pix)


def _crear_icono_emoji(emoji, size=16):
    """Dibuja un emoji/símbolo en un QPixmap para usarlo como QIcon
    (p.ej. el candado de la barra de URL o el fantasma de incógnito)."""
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    font = p.font()
    font.setPointSize(int(size * 0.7))
    p.setFont(font)
    p.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, emoji)
    p.end()
    return QIcon(pix)


_YOUTUBE_WATCH_RE = re.compile(r'(youtube\.com/watch\?[^#]*\bv=|youtu\.be/)', re.IGNORECASE)
_YOUTUBE_ID_RE = re.compile(r'(?:[?&]v=|youtu\.be/|/shorts/)([A-Za-z0-9_-]{11})')


def _extraer_id_youtube(url):
    m = _YOUTUBE_ID_RE.search(url)
    return m.group(1) if m else None

_VIDEO_PAGE_SITES = [
    'tiktok.com/',
    'instagram.com/reel', 'instagram.com/p/',
    'twitter.com/i/status', 'x.com/i/status',
    'facebook.com/watch', 'facebook.com/reel',
    'vimeo.com/', 'twitch.tv/', 'dailymotion.com/video',
]

_SITE_DISPLAY_NAMES = {
    'youtube.com': 'YouTube', 'youtu.be': 'YouTube',
    'tiktok.com': 'TikTok',
    'instagram.com': 'Instagram',
    'twitter.com': 'Twitter/X', 'x.com': 'Twitter/X',
    'facebook.com': 'Facebook',
    'vimeo.com': 'Vimeo', 'twitch.tv': 'Twitch', 'dailymotion.com': 'Dailymotion',
}


def _site_display_name(url):
    host = urlparse(url).netloc.lower()
    for domain, name in _SITE_DISPLAY_NAMES.items():
        if domain in host:
            return name
    return host


class PulsingIndicator(QWidget):
    """Punto indicador que pulsa en verde cuando se detecta un video."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(18, 18)
        self._radius = 4.0
        self._color = QColor('#555566')

        grow = QPropertyAnimation(self, b"radius")
        grow.setStartValue(4.0)
        grow.setEndValue(8.0)
        grow.setDuration(600)
        grow.setEasingCurve(QEasingCurve.Type.InOutQuad)

        shrink = QPropertyAnimation(self, b"radius")
        shrink.setStartValue(8.0)
        shrink.setEndValue(4.0)
        shrink.setDuration(600)
        shrink.setEasingCurve(QEasingCurve.Type.InOutQuad)

        self._group = QSequentialAnimationGroup(self)
        self._group.addAnimation(grow)
        self._group.addAnimation(shrink)
        self._group.setLoopCount(-1)

    def getRadius(self):
        return self._radius

    def setRadius(self, value):
        self._radius = value
        self.update()

    radius = pyqtProperty(float, getRadius, setRadius)

    def set_active(self, activo):
        if hasattr(self, '_blink_timer') and self._blink_timer.isActive():
            self._blink_timer.stop()
        if activo:
            self._color = QColor('#00ff88')
            self._group.start()
        else:
            self._group.stop()
            self._radius = 4.0
            self._color = QColor('#555566')
            self.update()

    def blink_then_activate(self):
        """Parpadea en verde 3 veces rápido y luego queda fijo (pulsando)."""
        self._group.stop()
        self._radius = 4.0
        self._blink_count = 0
        self._blink_timer = QTimer(self)
        self._blink_timer.timeout.connect(self._do_blink)
        self._blink_timer.start(120)

    def _do_blink(self):
        if self._blink_count >= 6:
            self._blink_timer.stop()
            self.set_active(True)
            return
        self._color = QColor('#00ff88') if self._blink_count % 2 == 0 else QColor('#555566')
        self.update()
        self._blink_count += 1

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(self._color))
        cx, cy = self.width() / 2, self.height() / 2
        p.drawEllipse(QPointF(cx, cy), self._radius, self._radius)
        p.end()


class DetectedVideoCard(QFrame):
    """Fila horizontal para un video detectado en la página actual:
    miniatura a la izquierda, nombre/dominio/peso a la derecha. Al hacer
    click se selecciona/pone en el campo URL."""

    selected = pyqtSignal(str)

    ROW_HEIGHT = 70
    THUMB_W = 100
    THUMB_H = 60

    def __init__(self, url, label, ext='', parent=None):
        super().__init__(parent)
        self.url = url
        self.ext = ext
        self._is_selected = False
        self.setFixedHeight(self.ROW_HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(10)

        self.lbl_thumb = QLabel("🎬")
        self.lbl_thumb.setFixedSize(self.THUMB_W, self.THUMB_H)
        self.lbl_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_thumb.setStyleSheet(
            f"background-color: {_C_BG_EL}; border-radius: 6px; font-size: 22px;"
        )
        lay.addWidget(self.lbl_thumb)

        info = QVBoxLayout()
        info.setContentsMargins(0, 0, 0, 0)
        info.setSpacing(4)

        self._full_label = label
        self.lbl_name = QLabel(label)
        self.lbl_name.setStyleSheet(f"color: {_C_TEXT}; font-size: 12px; background: transparent;")
        info.addWidget(self.lbl_name)

        meta_row = QHBoxLayout()
        meta_row.setContentsMargins(0, 0, 0, 0)
        meta_row.setSpacing(6)

        self.lbl_domain = QLabel(self._dominio_texto())
        self.lbl_domain.setStyleSheet("color: #555555; font-size: 10px; background: transparent;")
        meta_row.addWidget(self.lbl_domain)
        meta_row.addStretch()

        self.lbl_size = QLabel("")
        self.lbl_size.setStyleSheet("color: #888888; font-size: 10px; background: transparent;")
        meta_row.addWidget(self.lbl_size)

        info.addLayout(meta_row)
        info.addStretch()
        lay.addLayout(info, 1)

        self._apply_style()

    def _dominio_texto(self):
        dominio = urlparse(self.url).netloc.replace('www.', '')
        if self.ext:
            dominio = f"{dominio} · {self.ext.upper().lstrip('.')}"
        return dominio

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_label_elide()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.selected.emit(self.url)
        super().mousePressEvent(event)

    def set_label(self, label):
        self._full_label = label
        self._update_label_elide()

    def _update_label_elide(self):
        metrics = self.lbl_name.fontMetrics()
        width = self.lbl_name.width() or 200
        elided = metrics.elidedText(self._full_label, Qt.TextElideMode.ElideRight, width)
        self.lbl_name.setText(elided)

    def set_thumbnail_bytes(self, data):
        if not data:
            return
        pix = QPixmap()
        if not pix.loadFromData(data):
            return
        escalado = pix.scaled(
            self.THUMB_W, self.THUMB_H,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        recortado = QPixmap(self.THUMB_W, self.THUMB_H)
        recortado.fill(Qt.GlobalColor.transparent)
        p = QPainter(recortado)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.THUMB_W, self.THUMB_H, 6, 6)
        p.setClipPath(path)
        x = (self.THUMB_W - escalado.width()) // 2
        y = (self.THUMB_H - escalado.height()) // 2
        p.drawPixmap(x, y, escalado)
        p.end()
        self.lbl_thumb.setPixmap(recortado)
        self.lbl_thumb.setText("")

    def set_thumbnail(self, manager, url):
        if not url:
            return
        self._net_manager = manager
        reply = manager.get(QNetworkRequest(QUrl(url)))
        self._thumb_reply = reply
        reply.finished.connect(lambda: self._on_thumb_loaded(reply))

    def _on_thumb_loaded(self, reply):
        try:
            data = bytes(reply.readAll())
            self.set_thumbnail_bytes(data)
        finally:
            reply.deleteLater()

    def set_size(self, num_bytes):
        texto = _format_size(num_bytes) or "~ desconocido"
        self.lbl_size.setText(texto)

    def set_selected(self, selected):
        self._is_selected = selected
        self._apply_style()

    def _apply_style(self):
        if self._is_selected:
            bg = "#252525"
            border_left = f"3px solid {_C_PURPLE}"
        else:
            bg = "#1a1a1a"
            border_left = "3px solid transparent"
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {bg};
                border: none;
                border-left: {border_left};
                border-bottom: 1px solid rgba(255,255,255,13);
            }}
            QFrame:hover {{
                background-color: #252525;
            }}
        """)


class QueueItemWidget(QFrame):
    """Tarjeta compacta de la cola de descargas: thumbnail, título, progreso,
    peso y porcentaje en una sola fila. No muestra la URL."""

    cancel_requested = pyqtSignal(str)
    goto_tiktok_requested = pyqtSignal()
    retry_requested = pyqtSignal(str)

    _COLORS = {
        'queued': _C_BLUE,
        'downloading': _C_YELLOW,
        'completed': _C_GREEN,
        'error': '#ef4444',
        'cancelled': _C_TEXT_HINT,
    }

    CARD_HEIGHT = 56
    TITLE_MAX_CHARS = 35

    def __init__(self, item_id, title, dest_folder='', source_url='', parent=None):
        super().__init__(parent)
        self.item_id = item_id
        self.status = 'queued'
        self._full_title = self._truncate_title(title)
        self._dest_folder = dest_folder
        self.source_url = source_url
        self.setFixedHeight(self.CARD_HEIGHT)
        self._net_manager = None
        self._thumb_reply = None
        self.final_filepath = ''
        self.thumb_url = ''

        root = QHBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(8)

        self.lbl_thumb = QLabel("🎬")
        self.lbl_thumb.setFixedSize(44, 44)
        self.lbl_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_thumb.setStyleSheet(
            f"background-color: {_C_BG_EL}; border-radius: 4px; font-size: 14px;"
        )
        root.addWidget(self.lbl_thumb)

        col = QVBoxLayout()
        col.setSpacing(3)

        self.lbl_title = QLabel(title)
        self.lbl_title.setWordWrap(False)
        self.lbl_title.setStyleSheet(
            f"color: {_C_TEXT}; font-weight: bold; font-size: 11px; background: transparent;"
        )
        col.addWidget(self.lbl_title)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFixedHeight(3)
        self.progress.setTextVisible(False)
        col.addWidget(self.progress)

        bottom = QHBoxLayout()
        bottom.setSpacing(4)
        self.lbl_size = QLabel("")
        self.lbl_size.setStyleSheet(f"color: {_C_TEXT_SEC}; font-size: 10px; background: transparent;")
        self.lbl_percent = QLabel("")
        self.lbl_percent.setStyleSheet(f"color: {_C_TEXT_SEC}; font-size: 10px; background: transparent;")
        self.lbl_percent.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        bottom.addWidget(self.lbl_percent)
        bottom.addStretch()

        self.btn_tiktok_login = QPushButton("Ir a TikTok")
        self.btn_tiktok_login.setFixedHeight(18)
        self.btn_tiktok_login.setStyleSheet(f"""
            QPushButton {{
                background-color: #1a0d2e;
                border: 1px solid {_C_PURPLE};
                border-radius: 4px;
                color: #a78bfa;
                font-size: 9px;
                padding: 0px 6px;
            }}
            QPushButton:hover {{ background-color: #2a1a4e; }}
        """)
        self.btn_tiktok_login.setVisible(False)
        self.btn_tiktok_login.clicked.connect(self.goto_tiktok_requested.emit)
        bottom.addWidget(self.btn_tiktok_login)

        bottom.addWidget(self.lbl_size)
        col.addLayout(bottom)

        root.addLayout(col, 1)

        self.btn_folder = QPushButton("📁")
        self.btn_folder.setFixedSize(22, 22)
        self.btn_folder.setToolTip("Abrir carpeta")
        self.btn_folder.setVisible(False)
        self.btn_folder.setStyleSheet(f"""
            QPushButton {{ color: {_C_TEXT_SEC}; background: transparent; border: none; }}
            QPushButton:hover {{ color: {_C_PURPLE}; }}
        """)
        self.btn_folder.clicked.connect(self._abrir_carpeta)
        root.addWidget(self.btn_folder)

        self.btn_retry = QPushButton("↻")
        self.btn_retry.setFixedSize(22, 22)
        self.btn_retry.setToolTip("Reintentar")
        self.btn_retry.setVisible(False)
        self.btn_retry.setStyleSheet(f"""
            QPushButton {{ color: {_C_TEXT_SEC}; background: transparent; border: none; font-size: 13px; }}
            QPushButton:hover {{ color: {_C_BLUE}; }}
        """)
        self.btn_retry.clicked.connect(lambda: self.retry_requested.emit(self.item_id))
        root.addWidget(self.btn_retry)

        self.btn_cancel = QPushButton("✕")
        self.btn_cancel.setFixedSize(22, 22)
        self.btn_cancel.setStyleSheet(f"""
            QPushButton {{ color: {_C_TEXT_SEC}; background: transparent; border: none; }}
            QPushButton:hover {{ color: {_C_RED}; }}
        """)
        self.btn_cancel.clicked.connect(lambda: self.cancel_requested.emit(self.item_id))
        root.addWidget(self.btn_cancel)

        self._apply_status_style()
        self._update_title_elide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_title_elide()

    def _truncate_title(self, title):
        if len(title) > self.TITLE_MAX_CHARS:
            return title[:self.TITLE_MAX_CHARS - 3] + "..."
        return title

    def _update_title_elide(self):
        metrics = self.lbl_title.fontMetrics()
        elided = metrics.elidedText(
            self._full_title, Qt.TextElideMode.ElideRight, self.lbl_title.width()
        )
        self.lbl_title.setText(elided)

    def _abrir_carpeta(self):
        carpeta = os.path.dirname(self.final_filepath) if self.final_filepath else self._dest_folder
        if carpeta and os.path.isdir(carpeta):
            os.startfile(carpeta)

    def set_filepath(self, ruta):
        if ruta and os.path.exists(ruta):
            self.final_filepath = ruta
            self.btn_folder.setVisible(True)
            self.set_size(os.path.getsize(ruta))

    def set_title(self, title):
        self._full_title = self._truncate_title(title)
        self._update_title_elide()

    def set_size(self, num_bytes):
        texto = _format_size(num_bytes)
        self.lbl_size.setText(texto)

    def set_size_text(self, texto):
        self.lbl_size.setText(texto)

    def set_obteniendo_info(self):
        self.set_title("Obteniendo información...")
        self.lbl_size.setText("")

    def set_thumbnail_bytes(self, data):
        if not data:
            return
        pix = QPixmap()
        if pix.loadFromData(data):
            escalado = pix.scaled(
                44, 44,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.lbl_thumb.setPixmap(escalado)
            self.lbl_thumb.setText("")

    def set_thumbnail(self, manager, url):
        if not url:
            return
        self._net_manager = manager
        reply = manager.get(QNetworkRequest(QUrl(url)))
        self._thumb_reply = reply
        reply.finished.connect(lambda: self._on_thumb_loaded(reply))

    def _on_thumb_loaded(self, reply):
        try:
            data = bytes(reply.readAll())
            self.set_thumbnail_bytes(data)
        finally:
            reply.deleteLater()

    def set_progress(self, percent, extra=''):
        percent = max(0, min(100, percent))
        self.progress.setValue(percent)
        texto = f"{percent}%"
        if extra:
            texto += f" · {extra}"
        self.lbl_percent.setText(texto)
        self.lbl_percent.setStyleSheet(f"color: {_C_TEXT_SEC}; font-size: 10px; background: transparent;")

    def set_retrying(self, mensaje):
        texto = mensaje.strip().splitlines()[0]
        if len(texto) > 40:
            texto = texto[:37] + "..."
        self.lbl_percent.setText(texto)
        self.lbl_percent.setToolTip(mensaje)
        self.lbl_percent.setStyleSheet(f"color: {_C_YELLOW}; font-size: 10px; background: transparent;")

    def set_status(self, status, detail=None):
        self.status = status
        terminado = status in ('completed', 'error', 'cancelled')
        self.btn_cancel.setEnabled(not terminado)
        self.btn_cancel.setVisible(not terminado)
        self.btn_retry.setVisible(status == 'error')
        if status != 'error':
            self.btn_tiktok_login.setVisible(False)
        if status == 'completed':
            self.progress.setValue(100)
            self.lbl_percent.setText("100%")
        if status == 'error':
            texto_error = "Error"
            if detail:
                detalle_limpio = detail.strip().splitlines()[0]
                texto_error = (
                    detalle_limpio if len(detalle_limpio) <= 50
                    else detalle_limpio[:47] + "..."
                )
                self.lbl_percent.setToolTip(detail)
            self.lbl_percent.setText(texto_error)
            self.lbl_percent.setStyleSheet("color: #ef4444; font-size: 10px; background: transparent;")
            if 'tiktok.com' in self.source_url.lower():
                self.lbl_percent.setText("TikTok bloqueó la descarga")
                self.lbl_percent.setToolTip(
                    "TikTok bloqueó la descarga. Intenta iniciar sesión en "
                    "TikTok en el navegador de arriba"
                )
                self.btn_tiktok_login.setVisible(True)
        if status == 'cancelled':
            self.lbl_percent.setText("Cancelado")
        self._apply_status_style()

    def _apply_status_style(self):
        color = self._COLORS.get(self.status, _C_BLUE)
        lighter = QColor(color).lighter(140).name()
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {_C_BG_EL};
                border: none;
                border-left: 4px solid {color};
                border-radius: 5px;
            }}
            QProgressBar {{
                background-color: {_C_BG_APP};
                border: none;
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {color}, stop:1 {lighter});
                border-radius: 2px;
            }}
        """)


class HistoryItemWidget(QFrame):
    """Tarjeta de un elemento del historial de descargas: thumbnail,
    nombre, peso final, fecha y botón para abrir la carpeta contenedora."""

    CARD_HEIGHT = 56
    TITLE_MAX_CHARS = 35

    def __init__(self, title, filepath, size_bytes=0, fecha='', parent=None):
        super().__init__(parent)
        self.filepath = filepath or ''
        self.setFixedHeight(self.CARD_HEIGHT)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {_C_BG_EL};
                border: none;
                border-radius: 5px;
            }}
        """)

        root = QHBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(8)

        self.lbl_thumb = QLabel("🎬")
        self.lbl_thumb.setFixedSize(44, 44)
        self.lbl_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_thumb.setStyleSheet(
            f"background-color: {_C_BG_PANEL}; border-radius: 4px; font-size: 14px;"
        )
        root.addWidget(self.lbl_thumb)

        col = QVBoxLayout()
        col.setSpacing(3)

        titulo = title if len(title) <= self.TITLE_MAX_CHARS else title[:self.TITLE_MAX_CHARS - 3] + "..."
        self.lbl_title = QLabel(titulo)
        self.lbl_title.setWordWrap(False)
        self.lbl_title.setStyleSheet(
            f"color: {_C_TEXT}; font-weight: bold; font-size: 11px; background: transparent;"
        )
        col.addWidget(self.lbl_title)

        info_texto = _format_size(size_bytes)
        if fecha:
            info_texto = f"{info_texto} · {fecha}" if info_texto else fecha
        self.lbl_info = QLabel(info_texto)
        self.lbl_info.setStyleSheet(f"color: {_C_TEXT_SEC}; font-size: 10px; background: transparent;")
        col.addWidget(self.lbl_info)

        root.addLayout(col, 1)

        self.btn_folder = QPushButton("📁")
        self.btn_folder.setFixedSize(22, 22)
        self.btn_folder.setToolTip("Abrir carpeta")
        self.btn_folder.setStyleSheet(f"""
            QPushButton {{ color: {_C_TEXT_SEC}; background: transparent; border: none; }}
            QPushButton:hover {{ color: {_C_PURPLE}; }}
        """)
        self.btn_folder.clicked.connect(self._abrir_carpeta)
        root.addWidget(self.btn_folder)

    def set_thumbnail_pixmap(self, pixmap):
        if pixmap is None or pixmap.isNull():
            return
        self.lbl_thumb.setPixmap(pixmap)
        self.lbl_thumb.setText("")

    def set_thumbnail_bytes(self, data):
        if not data:
            return
        pix = QPixmap()
        if pix.loadFromData(data):
            escalado = pix.scaled(
                44, 44,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.lbl_thumb.setPixmap(escalado)
            self.lbl_thumb.setText("")

    def _abrir_carpeta(self):
        carpeta = os.path.dirname(self.filepath) if self.filepath else ''
        if carpeta and os.path.isdir(carpeta):
            os.startfile(carpeta)


class DownloadWorker(QThread):
    """Descarga un video usando la API de Python de yt-dlp en su propio hilo.

    La resolución de metadatos (título/miniatura/peso) se hace por separado
    en InfoResolverWorker; este hilo solo se encarga de la descarga real."""

    progress = pyqtSignal(str, int, str)             # item_id, percent, extra
    finished_ok = pyqtSignal(str, str)               # item_id, ruta_archivo
    failed = pyqtSignal(str, str)                    # item_id, mensaje
    retrying = pyqtSignal(str, str)                  # item_id, mensaje

    MAX_RETRIES_EXPIRADA = 3
    MAX_RETRIES_RED = 5
    ESPERA_RED_SEGUNDOS = 10

    def __init__(self, item_id, url, ydl_opts, parent=None, page_url=None):
        super().__init__(parent)
        self.item_id = item_id
        self.url = url
        self.ydl_opts = ydl_opts
        self.page_url = page_url
        self._cancelled = False
        self._final_path = ''

    def cancel(self):
        self._cancelled = True

    def _reintentar_por_red(self, mensaje, intentos_red):
        """Si `mensaje` indica un problema de conexión (no de la URL/video),
        espera y devuelve ('retry', intentos_red) para que el bucle de
        run() reintente la descarga. Si ya se agotaron los reintentos,
        emite el fallo final y devuelve ('failed', intentos_red). Si no es
        un error de red, devuelve ('no', intentos_red) sin tocar nada."""
        if not _es_error_de_red(mensaje):
            return 'no', intentos_red

        if intentos_red >= self.MAX_RETRIES_RED:
            self.failed.emit(
                self.item_id,
                f"Error de red después de {self.MAX_RETRIES_RED} intentos - "
                "haz click para reintentar"
            )
            return 'failed', intentos_red

        intentos_red += 1
        self.retrying.emit(
            self.item_id,
            f"Sin conexión, reintentando en {self.ESPERA_RED_SEGUNDOS}s... "
            f"({intentos_red}/{self.MAX_RETRIES_RED})"
        )
        time.sleep(self.ESPERA_RED_SEGUNDOS)
        if self._cancelled:
            self.failed.emit(self.item_id, "Cancelado por el usuario")
            return 'failed', intentos_red
        self.retrying.emit(self.item_id, "Reconectado - continuando descarga")
        return 'retry', intentos_red

    def _progress_hook(self, d):
        if self._cancelled:
            raise yt_dlp.utils.DownloadError("Cancelado por el usuario")
        status = d.get('status')
        if status == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            downloaded = d.get('downloaded_bytes', 0)
            percent = int(downloaded * 100 / total) if total else 0
            speed = d.get('speed')
            extra = f"{speed / 1024 / 1024:.2f} MB/s" if speed else ""
            self.progress.emit(self.item_id, percent, extra)
        elif status == 'finished':
            ruta = d.get('filename', '')
            if ruta and os.path.exists(ruta):
                self._final_path = ruta
            self.progress.emit(self.item_id, 100, "Procesando...")

    def _postprocessor_hook(self, d):
        if d.get('status') == 'finished':
            info = d.get('info_dict') or {}
            ruta = info.get('filepath') or info.get('_filename')
            if ruta and os.path.exists(ruta):
                self._final_path = ruta

    def _intentar_descarga(self, opts, url):
        self._final_path = ''
        opts = dict(opts)
        opts['progress_hooks'] = [self._progress_hook]
        opts['postprocessor_hooks'] = [self._postprocessor_hook]
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])

    def run(self):
        url = self.url
        opts = dict(self.ydl_opts)
        intentos = 0
        intentos_red = 0
        sin_cookies_intentado = False
        while True:
            try:
                self._intentar_descarga(opts, url)
                self.finished_ok.emit(self.item_id, self._final_path)
                return
            except yt_dlp.utils.DownloadError as e:
                if self._cancelled:
                    self.failed.emit(self.item_id, "Cancelado por el usuario")
                    return

                mensaje = str(e)

                resultado, intentos_red = self._reintentar_por_red(mensaje, intentos_red)
                if resultado == 'retry':
                    continue
                if resultado == 'failed':
                    return

                es_expirada = '410' in mensaje
                if es_expirada and self.page_url and intentos < self.MAX_RETRIES_EXPIRADA:
                    intentos += 1
                    self.retrying.emit(
                        self.item_id, "URL expirada - intentando obtener nueva URL..."
                    )
                    fresca = _get_fresh_url(self.page_url)
                    url = fresca or self.page_url
                    continue

                if (opts.get('cookiefile') and not sin_cookies_intentado
                        and _AUTH_ERROR_RE.search(mensaje)):
                    sin_cookies_intentado = True
                    self.retrying.emit(
                        self.item_id, "Reintentando sin cookies..."
                    )
                    opts = dict(opts)
                    opts.pop('cookiefile', None)
                    continue

                if sin_cookies_intentado and _AUTH_ERROR_RE.search(mensaje):
                    self.failed.emit(
                        self.item_id, "Cookies expiradas, reimporta las cookies"
                    )
                    return

                self.failed.emit(self.item_id, mensaje)
                return
            except Exception as e:
                if self._cancelled:
                    self.failed.emit(self.item_id, "Cancelado por el usuario")
                    return

                mensaje = str(e)
                resultado, intentos_red = self._reintentar_por_red(mensaje, intentos_red)
                if resultado == 'retry':
                    continue
                if resultado == 'failed':
                    return

                self.failed.emit(self.item_id, mensaje)
                return


class SimpleDownloaderWindow(QWidget):
    """Ventana independiente: navegador con pestañas + panel de descargas con cola."""

    MAX_CONCURRENT = 3

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cerrado = False
        self.setWindowTitle("SimpleDownloader")
        self.setWindowIcon(_crear_icono_logo())
        self.resize(1150, 720)
        self.setMinimumSize(900, 600)

        self._dest_folder = os.path.join(os.path.expanduser('~'), 'Downloads')
        self._pending_queue = []      # ids en espera
        self._workers = {}            # item_id -> DownloadWorker
        self._widgets = {}            # item_id -> QueueItemWidget
        self._download_args = {}      # item_id -> (url, ydl_opts, page_url), para "Reintentar"
        self._active_count = 0
        self._thumb_manager = QNetworkAccessManager(self)

        self._incognito = False
        self._historial_descargas = []
        self._historial_widgets = []
        self._historial_thumb_workers = []
        self._info_workers = {}       # item_id -> InfoResolverWorker

        self._stream_resolver = None
        self._streams_resolved_for_url = None
        self._size_workers = []
        self._stream_page_map = {}
        self._captura_descargadas = set()
        self._detected_pages = {}     # url de recurso -> URL de la página donde se detectó
        self._current_page_url = ''
        self._favicon_cache = {}      # dominio -> QIcon
        self._favicon_replies = []
        self._indicator_blinked = False
        self._item_progress = {}      # item_id -> porcentaje de progreso

        self.config_personalizacion = personalizacion.cargar_config()

        self._init_ui()
        self.aplicar_tema()
        self._aplicar_personalizacion_visual()
        self._cargar_historial()

        self._updater_worker = YtDlpUpdaterWorker(self)
        self._updater_worker.start()

        self._aria2c_worker = Aria2cInstallerWorker(self)
        self._aria2c_worker.start()

        # Si SimpleHub invalida la sesión (cuenta desactivada o cierre de
        # sesión global), esta app también debe cerrarse.
        self._timer_flag_sesion = QTimer(self)
        self._timer_flag_sesion.timeout.connect(self._chequear_sesion_invalida)
        self._timer_flag_sesion.start(60000)

    def _chequear_sesion_invalida(self):
        if auth_manager.hay_sesion_invalida():
            self._forzar_cierre_sesion()

    def _forzar_cierre_sesion(self):
        self._timer_flag_sesion.stop()
        auth_manager.borrar_token()
        auth_manager.limpiar_marca_sesion_invalida()
        QMessageBox.warning(self, "Sesión cerrada", "Tu sesión fue cerrada desde SimpleHub.")
        self.close()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _init_ui(self):
        self.setObjectName("mainWindow")
        self.setStyleSheet("background-color: #0a0918;")
        self.setContentsMargins(0, 0, 0, 0)

        # Fondo animado/video global de la ventana principal (detrás de
        # los paneles de navegador y control, que no llevan fondo propio).
        self.fondo_animado_global = AnimacionFondoWidget(self)
        self.fondo_video_global = FondoVideoWidget(self)
        self.fondo_animado_global.setObjectName("fondoAnimadoGlobal")
        self.fondo_video_global.setObjectName("fondoVideoGlobal")
        self.fondo_animado_global.setGeometry(self.rect())
        self.fondo_video_global.setGeometry(self.rect())
        self.fondo_animado_global.lower()
        self.fondo_video_global.lower()
        self.fondo_video_global.calidad_cambiada.connect(self._on_fondo_video_calidad_cambiada)

        outer_lay = QVBoxLayout(self)
        outer_lay.setContentsMargins(0, 0, 0, 0)
        outer_lay.setSpacing(0)

        main_lay = QHBoxLayout()
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)

        main_lay.addWidget(self._build_browser_panel(), 2)
        main_lay.addWidget(self._build_control_panel())

        outer_lay.addLayout(main_lay, 1)

        # Barra de progreso global: muestra el avance promedio de todas las
        # descargas activas en la parte inferior de la ventana.
        self.global_progress_bar = QProgressBar()
        self.global_progress_bar.setObjectName("globalProgressBar")
        self.global_progress_bar.setRange(0, 100)
        self.global_progress_bar.setValue(0)
        self.global_progress_bar.setFixedHeight(4)
        self.global_progress_bar.setTextVisible(False)
        self.global_progress_bar.setVisible(False)
        outer_lay.addWidget(self.global_progress_bar)

        # Efectos de opacidad para el panel derecho y la barra de navegación,
        # usados para dejar ver el fondo de video a través de ellos. El área
        # del navegador embebido (Chrome real) no se incluye porque es una
        # ventana nativa y no admite transparencia.
        self._panel_opacity_effect = QGraphicsOpacityEffect(self.glass_control)
        self._panel_opacity_effect.setEnabled(False)
        self.glass_control.setGraphicsEffect(self._panel_opacity_effect)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        r = self.rect()
        self.fondo_animado_global.setGeometry(r)
        self.fondo_video_global.setGeometry(r)
        self.fondo_animado_global.lower()
        self.fondo_video_global.lower()

    def _build_browser_panel(self):
        self.glass_browser = PanelGlass(oscuro=True)
        lay = QVBoxLayout()
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(6)
        self.glass_browser.setLayout(lay)

        tabs_row = QHBoxLayout()
        tabs_row.setSpacing(4)
        self.tab_bar = QTabBar()
        self.tab_bar.setTabsClosable(True)
        self.tab_bar.setExpanding(False)
        self.tab_bar.setMovable(False)
        self.tab_bar.setDrawBase(False)
        self.tab_bar.setElideMode(Qt.TextElideMode.ElideRight)
        self.tab_bar.currentChanged.connect(self._on_tab_changed)
        self.tab_bar.tabCloseRequested.connect(self._on_tab_close_requested)
        tabs_row.addWidget(self.tab_bar, 1)

        self.btn_new_tab = QPushButton("+")
        self.btn_new_tab.setFixedSize(28, 28)
        self.btn_new_tab.setObjectName("navBtn")
        self.btn_new_tab.setToolTip("Nueva pestaña")
        self.btn_new_tab.clicked.connect(lambda: self._add_tab())
        tabs_row.addWidget(self.btn_new_tab)

        lay.addLayout(tabs_row)

        nav = QHBoxLayout()
        nav.setSpacing(6)
        self.btn_back = QPushButton("←")
        self.btn_forward = QPushButton("→")
        self.btn_reload = QPushButton("↻")
        for b in (self.btn_back, self.btn_forward, self.btn_reload):
            b.setFixedSize(32, 28)
            b.setObjectName("navBtn")
        self.url_bar = QLineEdit()
        self.url_bar.setObjectName("urlBar")
        self.url_bar.setPlaceholderText("Escribe una URL o búsqueda y presiona Enter...")
        self.url_bar.addAction(_crear_icono_emoji('🔒'), QLineEdit.ActionPosition.LeadingPosition)
        self.url_bar.returnPressed.connect(self._navigate_to_url_bar)

        self.btn_save_page = QPushButton("💾 Guardar página")
        self.btn_save_page.setObjectName("navBtn")
        self.btn_save_page.clicked.connect(self._guardar_pagina)

        self.btn_incognito = QPushButton()
        self.btn_incognito.setIcon(_crear_icono_emoji('👻'))
        self.btn_incognito.setFixedSize(32, 28)
        self.btn_incognito.setCheckable(True)
        self.btn_incognito.setObjectName("incognitoBtn")
        self.btn_incognito.setToolTip("Modo incógnito")
        self.btn_incognito.clicked.connect(self._toggle_incognito)

        self.lbl_incognito_badge = QLabel("👻 Incógnito")
        self.lbl_incognito_badge.setStyleSheet(
            "color: #a78bfa; font-weight: bold; background: transparent; padding: 0 6px;"
        )
        self.lbl_incognito_badge.setVisible(False)

        self.btn_personalizar = QPushButton("🎨")
        self.btn_personalizar.setFixedSize(32, 28)
        self.btn_personalizar.setObjectName("navBtn")
        self.btn_personalizar.setToolTip("Personalizar")
        self.btn_personalizar.clicked.connect(self.abrir_personalizacion)

        self.btn_back.clicked.connect(lambda: self.browser.back())
        self.btn_forward.clicked.connect(lambda: self.browser.forward())
        self.btn_reload.clicked.connect(lambda: self.browser.reload())

        nav.addWidget(self.btn_back)
        nav.addWidget(self.btn_forward)
        nav.addWidget(self.btn_reload)
        nav.addWidget(self.url_bar)
        nav.addWidget(self.btn_save_page)
        nav.addWidget(self.btn_incognito)
        nav.addWidget(self.lbl_incognito_badge)
        nav.addWidget(self.btn_personalizar)

        self.nav_bar_widget = QWidget()
        self.nav_bar_widget.setObjectName("navBar")
        self.nav_bar_widget.setLayout(nav)
        lay.addWidget(self.nav_bar_widget)

        self._browser_layout = lay
        self._browser_stack = QStackedWidget()
        lay.addWidget(self._browser_stack)

        self._add_tab()

        return self.glass_browser

    def _conectar_browser(self, browser):
        browser.url_changed.connect(lambda u, b=browser: self._on_browser_url_changed(b, u))
        browser.title_changed.connect(lambda t, b=browser: self._on_browser_title_changed(b, t))
        browser.load_started.connect(lambda b=browser: self._on_browser_load_started(b))
        browser.load_finished.connect(lambda b=browser: self._on_browser_load_finished(b))
        browser.video_detected.connect(lambda u, b=browser: self._on_browser_video_detected(b, u))

    # ------------------------------------------------------------------
    # Pestañas: cada pestaña tiene su propio WebView2BrowserWidget (sesión
    # independiente). Sólo la pestaña activa actualiza el panel de
    # navegación, el detector de video y el panel "Videos en esta página".
    # ------------------------------------------------------------------
    def _add_tab(self, url=None):
        browser = WebView2BrowserWidget(incognito=self._incognito, parent=self, initial_url=url)
        self._conectar_browser(browser)
        self._browser_stack.addWidget(browser)
        idx = self.tab_bar.addTab("Nueva pestaña")
        self.tab_bar.setCurrentIndex(idx)
        self.browser = browser
        self._browser_stack.setCurrentWidget(browser)
        return browser

    def _on_tab_changed(self, index):
        if index < 0:
            return
        browser = self._browser_stack.widget(index)
        if browser is None:
            return
        self._browser_stack.setCurrentWidget(browser)
        self.browser = browser
        if not hasattr(self, '_video_card_widgets'):
            # La pestaña inicial se crea durante la construcción de la UI,
            # antes de que exista el panel "Videos en esta página".
            return
        self._on_load_started()
        url = browser.current_url()
        if url:
            self.url_bar.setText(url)
            self.url_field.setText(url)
            self._current_page_url = url
            if _YOUTUBE_WATCH_RE.search(url) or any(site in url for site in _VIDEO_PAGE_SITES):
                self._on_url_changed(url)
        else:
            self.url_bar.setText('')
            self.url_field.setText('')

    def _on_tab_close_requested(self, index):
        if self.tab_bar.count() <= 1:
            return
        browser = self._browser_stack.widget(index)
        self.tab_bar.removeTab(index)
        self._browser_stack.removeWidget(browser)
        if browser is not None:
            browser.shutdown()
            browser.deleteLater()

    def _on_browser_url_changed(self, browser, url_str):
        idx = self._browser_stack.indexOf(browser)
        if idx >= 0:
            self.tab_bar.setTabToolTip(idx, url_str)
            self._actualizar_favicon_pestana(idx, url_str)
        if browser is not self.browser:
            return
        self._on_url_changed(url_str)

    def _actualizar_favicon_pestana(self, idx, url_str):
        dominio = urlparse(url_str).netloc
        if not dominio:
            return
        if dominio in self._favicon_cache:
            self.tab_bar.setTabIcon(idx, self._favicon_cache[dominio])
            return

        favicon_url = f"https://www.google.com/s2/favicons?domain={dominio}&sz=16"
        reply = self._thumb_manager.get(QNetworkRequest(QUrl(favicon_url)))
        self._favicon_replies.append(reply)

        def _on_loaded(reply=reply, dominio=dominio, idx=idx):
            try:
                data = bytes(reply.readAll())
                pix = QPixmap()
                if data and pix.loadFromData(data):
                    icono = QIcon(pix)
                    self._favicon_cache[dominio] = icono
                    if 0 <= idx < self.tab_bar.count():
                        self.tab_bar.setTabIcon(idx, icono)
            finally:
                if reply in self._favicon_replies:
                    self._favicon_replies.remove(reply)
                reply.deleteLater()

        reply.finished.connect(_on_loaded)

    def _on_browser_title_changed(self, browser, title):
        idx = self._browser_stack.indexOf(browser)
        if idx < 0:
            return
        texto = title.strip() or "Nueva pestaña"
        if len(texto) > 15:
            texto = texto[:14] + "…"
        self.tab_bar.setTabText(idx, texto)

    def _on_browser_load_started(self, browser):
        if browser is not self.browser:
            return
        self._on_load_started()

    def _on_browser_load_finished(self, browser):
        if browser is not self.browser:
            return
        self._on_load_finished()

    def _on_browser_video_detected(self, browser, url):
        if browser is not self.browser:
            return
        self._on_video_detected(url)

    def _build_control_panel(self):
        self.glass_control = PanelGlass(oscuro=True)
        self.glass_control.setFixedWidth(380)
        # PanelPersonalizacion / SeccionFondoAnimado actúan sobre self.glass
        self.glass = self.glass_control

        lay = QVBoxLayout()
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(9)
        self.glass_control.setLayout(lay)

        # Indicador de video detectado
        ind_row = QHBoxLayout()
        self.indicator = PulsingIndicator()
        self.lbl_indicator = QLabel("Sin video detectado")
        self.lbl_indicator.setStyleSheet(f"color: {_C_TEXT_SEC}; background: transparent;")
        self.lbl_indicator.setWordWrap(True)
        ind_row.addWidget(self.indicator)
        ind_row.addWidget(self.lbl_indicator, 1)
        lay.addLayout(ind_row)

        # Banner de autenticación (oculto por defecto)
        self.auth_banner = QFrame()
        self.auth_banner.setVisible(False)
        self.auth_banner.setStyleSheet(
            "background-color: rgba(255, 183, 3, 25); border: 1px solid #f59e0b; "
            "border-radius: 8px; padding: 4px;"
        )
        banner_lay = QVBoxLayout(self.auth_banner)
        lbl_auth = QLabel("Inicia sesión en el navegador de arriba para descargar este contenido")
        lbl_auth.setWordWrap(True)
        lbl_auth.setStyleSheet("color: #f59e0b; font-weight: bold; background: transparent;")
        banner_lay.addWidget(lbl_auth)
        btn_login = QPushButton("Iniciar sesión en YouTube")
        btn_login.clicked.connect(self._abrir_login_youtube)
        banner_lay.addWidget(btn_login)
        lay.addWidget(self.auth_banner)

        # Panel de videos detectados en la página actual
        videos_header = QHBoxLayout()
        self.lbl_videos_panel = self._lbl("Videos en esta página")
        self.lbl_videos_panel.setVisible(False)
        videos_header.addWidget(self.lbl_videos_panel, 1)
        self.btn_buscar_streams = QPushButton("🔍 Buscar streams")
        self.btn_buscar_streams.setStyleSheet("font-size: 10px; padding: 2px 6px;")
        self.btn_buscar_streams.setToolTip("Buscar las URLs reales de video/audio de esta página")
        self.btn_buscar_streams.setVisible(False)
        self.btn_buscar_streams.clicked.connect(self._resolve_real_streams)
        videos_header.addWidget(self.btn_buscar_streams)
        lay.addLayout(videos_header)

        self.videos_scroll = QScrollArea()
        self.videos_scroll.setObjectName("videosScroll")
        self.videos_scroll.setWidgetResizable(True)
        self.videos_scroll.setMaximumHeight(280)
        self.videos_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.videos_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.videos_scroll.setVisible(False)

        self._video_cards_container = QWidget()
        self._video_cards_container.setStyleSheet("background: transparent;")
        self._video_cards_layout = QVBoxLayout(self._video_cards_container)
        self._video_cards_layout.setContentsMargins(0, 0, 0, 0)
        self._video_cards_layout.setSpacing(0)
        self.videos_scroll.setWidget(self._video_cards_container)
        lay.addWidget(self.videos_scroll)

        self._video_card_widgets = []

        self.btn_captura_reproduccion = QPushButton("📹 Capturar mientras reproduce (descarga automática)")
        self.btn_captura_reproduccion.setCheckable(True)
        self.btn_captura_reproduccion.setStyleSheet("font-size: 10px; padding: 4px;")
        self.btn_captura_reproduccion.setToolTip(
            "Descarga automáticamente cualquier video detectado en cuanto empiece a reproducirse"
        )
        lay.addWidget(self.btn_captura_reproduccion)

        lay.addWidget(self._lbl("URL del video:"))
        self.url_field = QLineEdit()
        self.url_field.setPlaceholderText("https://...")
        self.url_field.setToolTip("URL del video a descargar")
        lay.addWidget(self.url_field)

        lay.addWidget(self._lbl("Calidad:"))
        self.quality_group = QButtonGroup(self)
        self.quality_group.setExclusive(True)
        self.quality_buttons = {}
        quality_grid = QGridLayout()
        quality_grid.setSpacing(6)
        quality_options = [
            ('Mejor (4K)', 0, 0), ('1080p', 0, 1),
            ('720p', 1, 0), ('480p', 1, 1),
            ('360p', 2, 0), ('Solo audio', 2, 1),
        ]
        for text, row, col in quality_options:
            cell = QVBoxLayout()
            cell.setSpacing(1)
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setObjectName("qualityBtn")
            btn.setToolTip(f"Descargar en calidad {text}")
            self.quality_group.addButton(btn)
            cell.addWidget(btn)
            lbl_sub = QLabel(_QUALITY_SUBTITLES.get(text, ''))
            lbl_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_sub.setStyleSheet(f"color: {_C_TEXT_HINT}; font-size: 9px; background: transparent;")
            cell.addWidget(lbl_sub)
            quality_grid.addLayout(cell, row, col)
            self.quality_buttons[text] = btn
        self.quality_buttons['Mejor (4K)'].setChecked(True)
        self.quality_group.buttonClicked.connect(self._update_download_button_text)
        lay.addLayout(quality_grid)

        lay.addWidget(self._lbl("Formato:"))
        self.format_group = QButtonGroup(self)
        self.format_group.setExclusive(True)
        self.format_buttons = {}
        format_row = QHBoxLayout()
        format_row.setSpacing(6)
        for text in ('MP4', 'MKV', 'WEBM', 'MP3', 'M4A'):
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setObjectName("formatChip")
            btn.setToolTip(f"Guardar como archivo {text}")
            self.format_group.addButton(btn)
            format_row.addWidget(btn)
            self.format_buttons[text] = btn
        self.format_buttons['MP4'].setChecked(True)
        lay.addLayout(format_row)

        lay.addWidget(self._lbl("Carpeta destino:"))
        dest_row = QHBoxLayout()
        self.dest_field = QLineEdit(self._dest_folder)
        self.dest_field.setReadOnly(True)
        self.dest_field.setToolTip("Carpeta donde se guardarán las descargas")
        btn_browse = QPushButton("⋯")
        btn_browse.setFixedWidth(36)
        btn_browse.setObjectName("navBtn")
        btn_browse.setToolTip("Elegir carpeta de destino")
        btn_browse.clicked.connect(self._choose_folder)
        dest_row.addWidget(self.dest_field)
        dest_row.addWidget(btn_browse)
        lay.addLayout(dest_row)

        btn_row = QGridLayout()
        btn_row.setSpacing(8)
        btn_row.setColumnStretch(0, 1)
        btn_row.setColumnStretch(1, 1)
        self.btn_add_queue = QPushButton("Cola")
        self.btn_add_queue.setObjectName("btnQueue")
        self.btn_add_queue.setToolTip("Agregar a la cola de descargas sin iniciarla de inmediato")
        self.btn_add_queue.clicked.connect(lambda: self._agregar_descarga(prioridad=False))
        self.btn_download_now = QPushButton("Descargar")
        self.btn_download_now.setObjectName("btnPrimary")
        self.btn_download_now.setToolTip("Descargar ahora, con prioridad sobre la cola")
        self.btn_download_now.clicked.connect(lambda: self._agregar_descarga(prioridad=True))
        btn_row.addWidget(self.btn_add_queue, 0, 0)
        btn_row.addWidget(self.btn_download_now, 0, 1)
        lay.addLayout(btn_row)
        self._update_download_button_text()

        lay.addWidget(self._lbl("Cola de descargas:"))
        self.queue_scroll = QScrollArea()
        self.queue_scroll.setWidgetResizable(True)
        self.queue_scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.queue_container = QWidget()
        self.queue_container.setStyleSheet("background: transparent;")
        self.queue_layout = QVBoxLayout(self.queue_container)
        self.queue_layout.setContentsMargins(0, 0, 0, 0)
        self.queue_layout.setSpacing(6)
        self.queue_layout.addStretch()
        self.queue_scroll.setWidget(self.queue_container)
        lay.addWidget(self.queue_scroll, 1)

        self.btn_historial_toggle = QPushButton("▸ Historial (0)")
        self.btn_historial_toggle.setCheckable(True)
        self.btn_historial_toggle.setToolTip("Mostrar u ocultar el historial de descargas")
        self.btn_historial_toggle.setStyleSheet(
            "text-align: left; font-size: 10px; padding: 4px 8px;"
        )
        self.btn_historial_toggle.clicked.connect(self._toggle_historial)
        lay.addWidget(self.btn_historial_toggle)

        self.historial_scroll = QScrollArea()
        self.historial_scroll.setWidgetResizable(True)
        self.historial_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.historial_scroll.setMaximumHeight(180)
        self.historial_scroll.setVisible(False)

        self.historial_container = QWidget()
        self.historial_container.setStyleSheet("background: transparent;")
        self.historial_layout = QVBoxLayout(self.historial_container)
        self.historial_layout.setContentsMargins(0, 0, 0, 0)
        self.historial_layout.setSpacing(6)
        self.historial_layout.addStretch()
        self.historial_scroll.setWidget(self.historial_container)
        lay.addWidget(self.historial_scroll)

        return self.glass_control

    def _lbl(self, texto):
        l = QLabel(texto.upper())
        l.setStyleSheet(
            f"color: {_C_TEXT_HINT}; background: transparent; "
            "font-size: 9px; font-weight: 600; letter-spacing: 0.7px;"
        )
        return l

    # ------------------------------------------------------------------
    # Personalización (compartida con SimpleResolve / personalizacion.py)
    # ------------------------------------------------------------------
    def aplicar_tema(self):
        cfg = self.config_personalizacion
        color_fondo = cfg.get('color_fondo') or _C_BG_APP
        color_acento = cfg.get('color_botones') or _C_RED

        c = QColor(color_acento)
        rgb = f"{c.red()},{c.green()},{c.blue()}"
        opacidad_botones = max(10, min(100, cfg.get('opacidad_botones', 100))) / 100
        # Nota: rgba() en QSS espera el canal alfa como entero 0-255, no como
        # fracción 0-1. Usar fracciones (p.ej. "0.180") hace que Qt lo
        # interprete como alfa ~0 y el color de acento deja de verse en los
        # botones.
        btn_bg = f"rgba({rgb},{round(opacidad_botones * 0.18 * 255)})"
        btn_bg_hover = f"rgba({rgb},{round(min(1.0, opacidad_botones * 0.32) * 255)})"
        luminancia = 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
        texto_primary = '#1a1a2e' if luminancia > 140 else '#ffffff'

        # Si hay un video de fondo activo, la ventana principal y todos los
        # widgets que la cubren deben ser transparentes para que se vea el
        # fondo de video detrás de los paneles.
        video_activo = bool(
            cfg.get('fondo_animado_activo')
            and cfg.get('video_fondo')
            and cfg.get('fondo_video_calidad', 'alta') != 'desactivar'
        )
        fondo_ventana = 'transparent' if video_activo else color_fondo
        fondo_widgets = 'transparent' if video_activo else color_fondo

        self.setStyleSheet(f"""
            QWidget#mainWindow {{
                background-color: {fondo_ventana};
            }}
            QWidget#fondoAnimadoGlobal, QWidget#fondoVideoGlobal {{
                background: transparent;
            }}
            QWidget {{
                color: {_C_TEXT};
                background-color: {fondo_widgets};
                font-family: 'Segoe UI', sans-serif;
            }}
            QWidget#navBar {{
                background-color: #111111;
                border-bottom: 0.5px solid #222;
            }}
            QLineEdit#urlBar {{
                background-color: #1a1a1a;
                border: 0.5px solid #2a2a2a;
                border-radius: 6px;
                color: #aaaaaa;
                padding: 4px 8px;
            }}
            QProgressBar#globalProgressBar {{
                background-color: {_C_BG_EL};
                border: none;
            }}
            QProgressBar#globalProgressBar::chunk {{
                background-color: {color_acento};
            }}
            QLabel {{ background: transparent; }}
            QScrollArea {{ border: none; background: transparent; }}
            QScrollArea > QWidget > QWidget {{ background: transparent; }}
            QTabWidget::pane {{
                border: 1px solid {_C_BORDER};
                border-radius: 6px;
                background: {_C_BG_PANEL};
            }}
            QTabBar::tab {{
                background: {_C_BG_EL};
                border: 1px solid {_C_BORDER};
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                padding: 4px 10px;
                margin-right: 2px;
                color: {_C_TEXT_SEC};
            }}
            QTabBar::tab:selected {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1e1e2e, stop:1 {_C_BG_PANEL});
                border: 1px solid {color_acento};
                border-bottom: 3px solid {color_acento};
                color: {color_acento};
                font-weight: bold;
            }}
            QLineEdit {{
                background-color: {_C_BG_EL};
                border: 1px solid {_C_BORDER};
                border-radius: 6px;
                padding: 5px 8px;
                color: {_C_TEXT};
            }}
            QLineEdit:focus {{
                border: 1px solid {color_acento};
                outline: none;
            }}
            QPushButton {{
                background-color: {btn_bg};
                border: 1px solid {_C_BORDER};
                border-radius: 6px;
                padding: 6px 10px;
                color: {_C_TEXT};
                outline: none;
            }}
            QPushButton:hover {{
                background-color: {btn_bg_hover};
            }}
            QPushButton:focus {{
                outline: none;
            }}
            QPushButton#navBtn {{
                background-color: {btn_bg};
                border: 1px solid {_C_BORDER};
                border-radius: 6px;
                color: {_C_TEXT};
            }}
            QPushButton#navBtn:hover {{
                background-color: {btn_bg_hover};
            }}
            QPushButton#btnQueue {{
                background-color: {btn_bg};
                border: 1px solid {_C_BORDER};
                color: #aaaaaa;
            }}
            QPushButton#btnPrimary {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {color_acento}, stop:1 {c.lighter(130).name()});
                border: none;
                font-weight: bold;
                color: {texto_primary};
            }}
            QPushButton#btnPrimary:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {c.lighter(115).name()}, stop:1 {c.lighter(140).name()});
            }}
            QPushButton#qualityBtn {{
                background-color: {btn_bg};
                border: 1px solid {_C_BORDER};
                border-radius: 6px;
                padding: 10px 6px;
                color: {_C_TEXT};
            }}
            QPushButton#qualityBtn:checked {{
                background-color: {color_acento};
                border: 2px solid {c.lighter(160).name()};
                color: {texto_primary};
                font-weight: bold;
            }}
            QPushButton#formatChip {{
                background-color: {btn_bg};
                border: 1px solid {_C_BORDER};
                border-radius: 14px;
                padding: 6px 14px;
                color: {_C_TEXT_HINT};
            }}
            QPushButton#formatChip:checked {{
                background-color: {color_acento};
                border: 2px solid {c.lighter(160).name()};
                color: {texto_primary};
                font-weight: bold;
            }}
            QPushButton#incognitoBtn:checked {{
                background-color: rgba({rgb},{round(0.18 * 255)});
                border: 1px solid {color_acento};
                color: {color_acento};
            }}
            QProgressBar {{
                background-color: {color_fondo};
                border: none;
                border-radius: 2px;
                height: 3px;
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {color_acento}, stop:1 {c.lighter(130).name()});
                border-radius: 2px;
            }}
            QScrollArea {{
                border: none;
                background: transparent;
            }}
            QScrollArea > QWidget > QWidget {{
                background: transparent;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 3px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: {_C_BORDER};
                border-radius: 1px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {_C_TEXT_HINT};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
                background: transparent;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: transparent;
            }}
        """)

        # Forzar re-evaluación inmediata del QSS en toda la jerarquía, para
        # que los cambios de color se vean al instante (sin esperar a que
        # otro diálogo modal fuerce un repintado).
        self.style().unpolish(self)
        self.style().polish(self)
        for w in self.findChildren(QWidget):
            w.style().unpolish(w)
            w.style().polish(w)
            w.update()
        self.update()

        self._aplicar_color_contenedores()

    def _aplicar_color_contenedores(self):
        """Evita que el área del navegador (QStackedWidget) muestre un
        fondo gris distinto al color de fondo elegido en personalización,
        o que tape el video de fondo cuando está activo."""
        cfg = self.config_personalizacion
        color_fondo = cfg.get('color_fondo') or _C_BG_PANEL
        video_activo = bool(
            cfg.get('fondo_animado_activo')
            and cfg.get('video_fondo')
            and cfg.get('fondo_video_calidad', 'alta') != 'desactivar'
        )
        if video_activo:
            self._browser_stack.setStyleSheet(
                "QStackedWidget { background: transparent; border: none; }"
            )
        else:
            self._browser_stack.setStyleSheet(
                f"QStackedWidget {{ background-color: {color_fondo}; border: none; }}"
            )

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, video_activo)
        self._browser_stack.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, video_activo)

        # El navegador embebido (Chrome real) no admite transparencia: el
        # panel que lo contiene se vacía igualmente para que el fondo se
        # vea detrás de la barra de navegación, ya que el navegador en sí
        # cubre por completo su propia área de todos modos.
        self.glass_browser.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, video_activo)
        self.glass_browser.set_transparente(video_activo)

        # El panel derecho conserva su fondo "glass" pero se vuelve
        # translúcido según el slider "Opacidad del panel", dejando ver el
        # fondo de video a través de él.
        panel_opacidad = max(10, min(100, cfg.get('fondo_panel_opacidad', 85)))
        self.glass_control.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, video_activo)
        self._panel_opacity_effect.setOpacity(panel_opacidad / 100)
        self._panel_opacity_effect.setEnabled(video_activo)

    def _aplicar_personalizacion_visual(self):
        cfg = self.config_personalizacion
        for glass in (self.glass_browser, self.glass_control):
            glass.set_color_fondo(cfg.get('color_fondo'))
            glass.set_color_borde(cfg.get('color_marco'))
            glass.set_opacidad_imagen(cfg.get('opacidad_imagen', 50))
            ruta = cfg.get('imagen_fondo')
            pixmap = None
            if ruta:
                pix = QPixmap(ruta)
                if not pix.isNull():
                    pixmap = pix
            glass.set_pixmap_fondo(pixmap)
        self._aplicar_fondo_animado()

    def _aplicar_fondo_animado(self):
        cfg = self.config_personalizacion
        color = cfg.get('color_botones') or '#7c6fff'
        opacidad = cfg.get('fondo_animado_opacidad', 30)
        activo = cfg.get('fondo_animado_activo', False)
        video = cfg.get('video_fondo')
        rendimiento = cfg.get('fondo_animado_rendimiento', False)

        fondo_animado = self.fondo_animado_global
        fondo_video = self.fondo_video_global

        fondo_animado.set_color(color)
        fondo_animado.set_velocidad(cfg.get('fondo_animado_velocidad', 'normal'))
        fondo_animado.set_opacidad(opacidad)
        fondo_video.set_opacidad(cfg.get('fondo_video_opacidad', 40))
        fondo_video.set_calidad(cfg.get('fondo_video_calidad', 'alta'))
        fondo_animado.set_rendimiento(rendimiento)
        fondo_video.set_rendimiento(rendimiento)
        if activo and video:
            fondo_animado.set_activo(False)
            fondo_video.set_video(video)
        elif activo:
            fondo_video.set_video(None)
            fondo_animado.set_tipo(cfg.get('fondo_animado_tipo', 'particulas'))
            fondo_animado.set_activo(True)
        else:
            fondo_animado.set_activo(False)
            fondo_video.set_video(None)

        self.aplicar_tema()

    def abrir_personalizacion(self):
        dlg = PanelPersonalizacion(self, self)
        dlg.exec()

    def set_color_fondo(self, color_hex):
        self.config_personalizacion['color_fondo'] = color_hex
        personalizacion.guardar_config(self.config_personalizacion)
        for glass in (self.glass_browser, self.glass_control):
            glass.set_color_fondo(color_hex)
        self.aplicar_tema()

    def set_color_botones(self, color_hex):
        self.config_personalizacion['color_botones'] = color_hex
        personalizacion.guardar_config(self.config_personalizacion)
        self.aplicar_tema()
        self._aplicar_fondo_animado()

    def set_opacidad_botones(self, valor):
        self.config_personalizacion['opacidad_botones'] = valor
        personalizacion.guardar_config(self.config_personalizacion)
        self.aplicar_tema()

    def set_opacidad_pestanas(self, valor):
        self.config_personalizacion['opacidad_pestanas'] = valor
        personalizacion.guardar_config(self.config_personalizacion)
        self.aplicar_tema()

    def set_color_marco(self, color_hex):
        self.config_personalizacion['color_marco'] = color_hex
        personalizacion.guardar_config(self.config_personalizacion)
        for glass in (self.glass_browser, self.glass_control):
            glass.set_color_borde(color_hex)

    def set_imagen_fondo(self, ruta):
        self.config_personalizacion['imagen_fondo'] = ruta
        personalizacion.guardar_config(self.config_personalizacion)
        pixmap = None
        if ruta:
            pix = QPixmap(ruta)
            if not pix.isNull():
                pixmap = pix
        for glass in (self.glass_browser, self.glass_control):
            glass.set_pixmap_fondo(pixmap)

    def set_opacidad_imagen(self, valor):
        self.config_personalizacion['opacidad_imagen'] = valor
        personalizacion.guardar_config(self.config_personalizacion)
        for glass in (self.glass_browser, self.glass_control):
            glass.set_opacidad_imagen(valor)

    def set_fondo_animado_activo(self, activo):
        self.config_personalizacion['fondo_animado_activo'] = activo
        personalizacion.guardar_config(self.config_personalizacion)
        self._aplicar_fondo_animado()

    def set_fondo_animado_tipo(self, tipo):
        self.config_personalizacion['fondo_animado_tipo'] = tipo
        personalizacion.guardar_config(self.config_personalizacion)
        self._aplicar_fondo_animado()

    def set_fondo_animado_velocidad(self, velocidad):
        self.config_personalizacion['fondo_animado_velocidad'] = velocidad
        personalizacion.guardar_config(self.config_personalizacion)
        self._aplicar_fondo_animado()

    def set_fondo_animado_opacidad(self, valor):
        self.config_personalizacion['fondo_animado_opacidad'] = valor
        personalizacion.guardar_config(self.config_personalizacion)
        self._aplicar_fondo_animado()

    def set_fondo_animado_rendimiento(self, activo):
        self.config_personalizacion['fondo_animado_rendimiento'] = activo
        personalizacion.guardar_config(self.config_personalizacion)
        self._aplicar_fondo_animado()

    def set_video_fondo(self, ruta):
        self.config_personalizacion['video_fondo'] = ruta
        personalizacion.guardar_config(self.config_personalizacion)
        self._aplicar_fondo_animado()

    def set_fondo_video_opacidad(self, valor):
        self.config_personalizacion['fondo_video_opacidad'] = valor
        personalizacion.guardar_config(self.config_personalizacion)
        self.fondo_video_global.set_opacidad(valor)

    def set_fondo_video_calidad(self, calidad):
        self.config_personalizacion['fondo_video_calidad'] = calidad
        personalizacion.guardar_config(self.config_personalizacion)
        self.fondo_video_global.set_calidad(calidad)

    def set_fondo_panel_opacidad(self, valor):
        self.config_personalizacion['fondo_panel_opacidad'] = valor
        personalizacion.guardar_config(self.config_personalizacion)
        self._aplicar_color_contenedores()

    def _on_fondo_video_calidad_cambiada(self, calidad):
        # El widget de video bajó la calidad automáticamente por bajo rendimiento.
        self.config_personalizacion['fondo_video_calidad'] = calidad
        personalizacion.guardar_config(self.config_personalizacion)

    def restaurar_personalizacion_defaults(self):
        self.config_personalizacion = personalizacion.DEFAULTS.copy()
        personalizacion.guardar_config(self.config_personalizacion)
        for glass in (self.glass_browser, self.glass_control):
            glass.set_color_fondo(None)
            glass.set_color_borde(None)
            glass.set_pixmap_fondo(None)
            glass.set_opacidad_imagen(self.config_personalizacion['opacidad_imagen'])
        self.aplicar_tema()
        self._aplicar_fondo_animado()

    # ------------------------------------------------------------------
    # Pestañas del navegador
    # ------------------------------------------------------------------
    def _current_webview(self):
        return self.browser

    def _get_download_url(self):
        """Devuelve la URL a descargar: siempre la URL actual del navegador
        (nunca una URL interceptada o cacheada del detector)."""
        try:
            view = self._current_webview()
            if view is not None:
                current = view.current_url()
                if current:
                    return current
        except Exception:
            pass
        return self.url_field.text().strip()

    def _toggle_incognito(self, checked):
        self._incognito = checked
        self.lbl_incognito_badge.setVisible(checked)
        if checked:
            for glass in (self.glass_browser, self.glass_control):
                glass.set_color_borde('#cbb8ff')
        else:
            color_marco = self.config_personalizacion.get('color_marco')
            for glass in (self.glass_browser, self.glass_control):
                glass.set_color_borde(color_marco)

        current_index = self.tab_bar.currentIndex()
        urls = []
        for i in range(self._browser_stack.count()):
            b = self._browser_stack.widget(i)
            urls.append(b.current_url() or None)
            b.shutdown()
            self._browser_stack.removeWidget(b)
            b.deleteLater()

        for url in urls:
            browser = WebView2BrowserWidget(incognito=self._incognito, parent=self, initial_url=url)
            self._conectar_browser(browser)
            self._browser_stack.addWidget(browser)

        self.tab_bar.setCurrentIndex(current_index)
        self.browser = self._browser_stack.widget(current_index)
        self._browser_stack.setCurrentWidget(self.browser)
        self._on_load_started()

    def _abrir_login_youtube(self):
        view = self._current_webview()
        if view is not None:
            view.navigate("https://accounts.google.com/signin")

    # ------------------------------------------------------------------
    # Navegador / detección de video
    # ------------------------------------------------------------------
    def _ir_a_tiktok(self):
        view = self._current_webview()
        if view is not None:
            view.navigate("https://www.tiktok.com/")

    def _exportar_cookies_sitio(self, dominio, url_cookies, ruta_destino):
        """Si el usuario está logueado en `dominio` en el navegador embebido,
        exporta esas cookies en formato Netscape para que yt-dlp pueda
        descargar videos privados/restringidos. Devuelve la ruta del
        archivo de cookies o None si no hay sesión iniciada."""
        view = self._current_webview()
        if view is None:
            return None
        try:
            cookies = view.get_cookies(url_cookies)
        except Exception:
            cookies = []
        cookies_sitio = [c for c in cookies if dominio in (c.get('domain') or '').lower()]
        if not cookies_sitio:
            return None
        try:
            _escribir_cookies_netscape(cookies_sitio, ruta_destino)
            return ruta_destino
        except OSError:
            return None

    def _exportar_cookies_tiktok(self):
        return self._exportar_cookies_sitio(
            'tiktok', 'https://www.tiktok.com', _TIKTOK_COOKIES_PATH
        )

    def _exportar_cookies_facebook(self):
        return self._exportar_cookies_sitio(
            'facebook', 'https://www.facebook.com', _FACEBOOK_COOKIES_PATH
        )

    def _navigate_to_url_bar(self):
        view = self._current_webview()
        if view is None:
            return
        texto = self.url_bar.text().strip()
        if not texto:
            return

        if _es_busqueda(texto):
            url = "https://www.google.com/search?q=" + quote_plus(texto)
        else:
            if not re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*://', texto):
                texto = "https://" + texto
            url = texto

        view.navigate(url)

    def _on_url_changed(self, url_str):
        self.url_bar.setText(url_str)
        self.url_field.setText(url_str)
        self._current_page_url = url_str
        if _YOUTUBE_WATCH_RE.search(url_str):
            self._add_youtube_video_card(url_str)
            return
        for site in _VIDEO_PAGE_SITES:
            if site in url_str:
                self._add_video_card(url_str, is_principal=True)
                self._resolve_real_streams()
                break

    def _on_load_started(self):
        """Al navegar a una nueva página se reinicia el detector de video."""
        if hasattr(self, 'browser'):
            self.browser.reset_detection()
        self._clear_video_cards()
        self._indicator_blinked = False
        self.indicator.set_active(False)
        self.lbl_indicator.setText("Sin video detectado")
        self.lbl_indicator.setStyleSheet(f"color: {_C_TEXT_SEC}; background: transparent;")

    def _on_load_finished(self):
        self.browser.run_script("""
            document.querySelectorAll('video').forEach(v => {
                v.muted = false;
                v.play().catch(() => {});
            });
        """)

    def _activar_indicador(self):
        """Activa el indicador verde; si es la primera vez para esta página
        lo hace parpadear 3 veces rápido antes de dejarlo fijo."""
        if self._indicator_blinked:
            self.indicator.set_active(True)
            return
        self._indicator_blinked = True
        self.indicator.blink_then_activate()

    def _clear_video_cards(self):
        """Limpia el panel de videos detectados (al navegar a una nueva página)."""
        for card in self._video_card_widgets:
            card.setParent(None)
            card.deleteLater()
        self._video_card_widgets = []
        self.lbl_videos_panel.setVisible(False)
        self.videos_scroll.setVisible(False)
        self.btn_buscar_streams.setVisible(False)
        self._streams_resolved_for_url = None
        self._stream_page_map = {}
        self._captura_descargadas = set()
        self._detected_pages = {}

    def _rebuild_video_cards_list(self):
        """Reordena las tarjetas en una lista vertical según el orden
        actual de `_video_card_widgets`."""
        while self._video_cards_layout.count():
            self._video_cards_layout.takeAt(0)
        for card in self._video_card_widgets:
            self._video_cards_layout.addWidget(card)

    def _video_card_label(self, url):
        parsed = urlparse(url)
        nombre = os.path.basename(parsed.path) or parsed.netloc
        return nombre[:24] or parsed.netloc

    def _video_card_ext(self, url):
        m = _VIDEO_EXT_RE.search(urlparse(url).path) or _VIDEO_EXT_RE.search(url)
        return ('.' + m.group(1).lower()) if m else ''

    def _add_video_card(self, url, is_principal=False, label_override=None):
        """Agrega una tarjeta al panel 'Videos en esta página'. Si solo hay
        una tarjeta se autoselecciona; si hay varias se muestra el panel
        para que el usuario elija."""
        existing = next((c for c in self._video_card_widgets if c.url == url), None)
        if existing is not None:
            if label_override:
                existing.set_label(label_override)
            return

        if label_override is not None:
            label = label_override
        elif is_principal:
            label = f"Video principal - {_site_display_name(url)}"
        else:
            label = self._video_card_label(url)
        ext = self._video_card_ext(url)

        card = DetectedVideoCard(url, label, ext)
        card.selected.connect(self._on_video_card_selected)

        if is_principal:
            self._video_card_widgets.insert(0, card)
        else:
            self._video_card_widgets.append(card)
        self._rebuild_video_cards_list()

        self.lbl_videos_panel.setVisible(True)
        self.videos_scroll.setVisible(True)
        self.btn_buscar_streams.setVisible(True)

        if len(self._video_card_widgets) == 1:
            self._on_video_card_selected(url)

        size_worker = VideoCardSizeResolverWorker(url, self)
        self._size_workers.append(size_worker)
        size_worker.resolved.connect(self._on_video_card_size)
        size_worker.title_resolved.connect(self._on_video_card_title)
        size_worker.thumbnail_resolved.connect(self._on_video_card_thumbnail)
        size_worker.finished.connect(lambda w=size_worker: self._size_workers.remove(w) if w in self._size_workers else None)
        size_worker.start()

    def _on_video_card_size(self, url, size):
        for card in self._video_card_widgets:
            if card.url == url:
                card.set_size(size)
                break

    def _on_video_card_title(self, url, titulo):
        for card in self._video_card_widgets:
            if card.url == url:
                card.set_label(titulo)
                break

    def _on_video_card_thumbnail(self, url, data):
        for card in self._video_card_widgets:
            if card.url == url:
                card.set_thumbnail_bytes(data)
                break

    def _add_youtube_video_card(self, url):
        """Para YouTube se muestra una única tarjeta con la URL de la página
        (nunca segmentos interceptados tipo videoplayback), su título real
        (tomado de la pestaña activa) y la miniatura oficial de YouTube."""
        self._activar_indicador()

        existing = next((c for c in self._video_card_widgets if c.url == url), None)
        if existing is not None:
            return

        view = self._current_webview()
        titulo = (view.current_title().strip() if view is not None else '') or "Video de YouTube"

        card = DetectedVideoCard(url, titulo, '')
        card.selected.connect(self._on_video_card_selected)
        self._video_card_widgets.insert(0, card)
        self._rebuild_video_cards_list()

        self.lbl_videos_panel.setVisible(True)
        self.videos_scroll.setVisible(True)
        self.btn_buscar_streams.setVisible(False)

        self._on_video_card_selected(url)

        self.lbl_indicator.setText("¡Video detectado! (YouTube)")
        self.lbl_indicator.setStyleSheet("color: #22c55e; font-weight: bold; background: transparent;")

        video_id = _extraer_id_youtube(url)
        if video_id:
            thumb_url = f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg"
            card.set_thumbnail(self._thumb_manager, thumb_url)

        size_worker = VideoCardSizeResolverWorker(url, self)
        self._size_workers.append(size_worker)
        size_worker.resolved.connect(self._on_video_card_size)
        size_worker.title_resolved.connect(self._on_video_card_title)
        size_worker.thumbnail_resolved.connect(self._on_video_card_thumbnail)
        size_worker.finished.connect(lambda w=size_worker: self._size_workers.remove(w) if w in self._size_workers else None)
        size_worker.start()

    def _resolve_real_streams(self):
        """Resuelve las URLs reales de stream (útil para sitios que solo
        exponen blob:// en el navegador embebido) usando yt-dlp -g."""
        view = self._current_webview()
        page_url = view.current_url() if view is not None else self.url_field.text().strip()
        if not page_url or not _es_url_valida(page_url):
            return
        if self._streams_resolved_for_url == page_url:
            return
        self._streams_resolved_for_url = page_url

        self.btn_buscar_streams.setVisible(True)
        self.btn_buscar_streams.setEnabled(False)
        self.btn_buscar_streams.setText("Buscando...")

        self._stream_resolver = RealStreamResolverWorker(page_url, self)
        self._stream_resolver.resolved.connect(
            lambda urls, pagina=page_url: self._on_streams_resolved(urls, pagina)
        )
        self._stream_resolver.start()

    def _on_streams_resolved(self, urls, page_url):
        self.btn_buscar_streams.setEnabled(True)
        self.btn_buscar_streams.setText("🔍 Buscar streams")

        if not urls:
            # No se encontraron streams reales: se usa la URL de la página
            # directamente con yt-dlp normal (ya está agregada como tarjeta
            # principal si corresponde).
            return

        if len(urls) == 2:
            self._add_video_card(
                page_url, label_override="Video + Audio (se mezclarán automáticamente)"
            )
            return

        for i, stream_url in enumerate(urls, start=1):
            self._stream_page_map[stream_url] = page_url
            self._add_video_card(stream_url, label_override=f"Stream {i}")

    def _on_video_card_selected(self, url):
        self.url_field.setText(url)
        for card in self._video_card_widgets:
            card.set_selected(card.url == url)

    def _on_video_detected(self, url):
        url_lower = url.lower()
        if any(pat in url_lower for pat in IGNORE_URL_PATTERNS):
            return
        if _YOUTUBE_WATCH_RE.search(self._current_page_url):
            # En YouTube la tarjeta se maneja por separado (_add_youtube_video_card)
            # con el título real y la URL de la página, no segmentos interceptados.
            return

        self._activar_indicador()
        self._detected_pages[url] = self._current_page_url
        self._add_video_card(url)

        # "Capturar mientras reproduce": descarga inmediata del recurso de
        # video detectado en cuanto se reproduce, sin esperar a que el
        # usuario presione Descargar (la URL es válida en ese momento).
        if (self.btn_captura_reproduccion.isChecked() and self._video_card_ext(url)
                and url not in self._captura_descargadas):
            self._captura_descargadas.add(url)
            self.url_field.setText(url)
            self._agregar_descarga(prioridad=True)

        if '.m3u8' in url.lower():
            self.lbl_indicator.setText(
                "Video HLS detectado — no se puede previsualizar pero puedes "
                "descargarlo con el botón Descargar"
            )
            self.lbl_indicator.setStyleSheet("color: #f59e0b; font-weight: bold; background: transparent;")
            return

        view = self._current_webview()
        referencia = ''
        if view is not None:
            referencia = view.current_title().strip()
        if not referencia:
            pagina = view.current_url() if view is not None else url
            referencia = urlparse(pagina).netloc

        if referencia:
            self.lbl_indicator.setText(f"¡Video detectado! ({referencia})")
        else:
            self.lbl_indicator.setText("¡Video detectado!")
        self.lbl_indicator.setStyleSheet("color: #22c55e; font-weight: bold; background: transparent;")

    def _guardar_pagina(self):
        view = self._current_webview()
        if view is None:
            return
        sugerido = "pagina.html"
        titulo = view.current_title()
        if titulo:
            sugerido = re.sub(r'[\\/:*?"<>|]', '_', titulo) + ".html"
        ruta, _ = QFileDialog.getSaveFileName(
            self, "Guardar página", os.path.join(self._dest_folder, sugerido),
            "Página web completa (*.html)"
        )
        if not ruta:
            return
        try:
            with open(ruta, 'w', encoding='utf-8') as f:
                f.write(view.page_source())
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Cola de descargas
    # ------------------------------------------------------------------
    def _current_quality(self):
        for text, btn in self.quality_buttons.items():
            if btn.isChecked():
                return text
        return 'Mejor (4K)'

    def _update_download_button_text(self, *args):
        self.btn_download_now.setText(f"Descargar · {self._current_quality()}")

    def _current_format(self):
        for text, btn in self.format_buttons.items():
            if btn.isChecked():
                return text
        return 'MP4'

    def _choose_folder(self):
        carpeta = QFileDialog.getExistingDirectory(self, "Elegir carpeta destino", self._dest_folder)
        if carpeta:
            self._dest_folder = carpeta
            self.dest_field.setText(carpeta)

    def _is_valid_video_url(self, url):
        """Rechaza URLs que claramente apuntan a recursos estáticos
        (íconos SVG/PNG, hojas de estilo, etc.) y no a un video."""
        url_lower = url.lower().split('?')[0]
        return not url_lower.endswith(_INVALID_VIDEO_EXTENSIONS)

    def _es_sitio_conocido(self, url):
        host = urlparse(url).netloc.lower()
        return any(sitio in host for sitio in _SITIOS_CONOCIDOS)

    def _resolver_url_real(self, page_url):
        """Para sitios no reconocidos explícitamente, resuelve con yt-dlp la
        URL real del video a partir de la URL de la página actual,
        descartando recursos estáticos (SVG/PNG/ícono) y archivos
        demasiado pequeños para ser un video. Devuelve None si no se
        encuentra nada descargable."""
        if not page_url or not _es_url_valida(page_url):
            return None

        cookies_file = _get_cookies_file()
        opts = {
            'quiet': True, 'no_warnings': True,
            'http_headers': {'User-Agent': _CHROME_USER_AGENT},
        }
        if cookies_file:
            opts['cookiefile'] = cookies_file

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(page_url, download=False)
        except Exception:
            return None
        if info is None:
            return None

        candidatos = []
        if info.get('url'):
            candidatos.append((info['url'], info.get('filesize') or info.get('filesize_approx') or 0))
        for f in reversed(info.get('formats') or []):
            if f.get('url'):
                candidatos.append((f['url'], f.get('filesize') or f.get('filesize_approx') or 0))

        for cand_url, size in candidatos:
            if not self._is_valid_video_url(cand_url):
                continue
            if size and size < _MIN_VIDEO_SIZE_BYTES:
                continue
            return cand_url

        return None

    def _agregar_descarga(self, prioridad=False):
        self.auth_banner.setVisible(False)

        url = self._get_download_url()
        if not url:
            url = self.url_bar.text().strip()

        if not _es_url_valida(url):
            QMessageBox.warning(self, "URL inválida", "Ingresa una URL válida (http:// o https://).")
            return

        # Para sitios no reconocidos (o si la URL elegida apunta directamente
        # a un recurso estático como un ícono SVG/PNG), no se le pasa la URL
        # de la página a yt-dlp tal cual: se resuelve primero la URL real del
        # video y se valida antes de poner la descarga en cola.
        if not self._is_valid_video_url(url) or not self._es_sitio_conocido(url):
            resuelto = self._resolver_url_real(url)
            if resuelto is None:
                QMessageBox.warning(
                    self, "Video no encontrado",
                    "No se encontró video descargable en esta página. "
                    "Navega directamente al video e inténtalo de nuevo."
                )
                return
            self._detected_pages.setdefault(resuelto, url)
            url = resuelto

        # Algunos sitios generan URLs de stream temporales que expiran (410
        # Gone). Si la URL elegida proviene de un recurso detectado o de un
        # "Stream N" resuelto, se intenta obtener una URL fresca con yt-dlp -g
        # justo antes de descargar; si falla, se usa la URL original como
        # respaldo.
        page_url = self._stream_page_map.get(url) or self._detected_pages.get(url)
        if page_url:
            fresca = _get_fresh_url(page_url)
            if fresca:
                url = fresca

        quality = self._current_quality()
        fmt = self._current_format()

        if not _FFMPEG_PATH:
            necesita_ffmpeg = quality != 'Solo audio' or fmt in _AUDIO_FORMATS or fmt not in ('MP4',)
            if necesita_ffmpeg:
                QMessageBox.warning(
                    self, "ffmpeg no disponible",
                    "No se encontró ffmpeg. La conversión/combinación de formatos puede fallar.\n"
                    "Instala 'imageio-ffmpeg' o ffmpeg en el sistema."
                )

        url_lower = url.lower()
        tiktok_cookies_file = None
        if 'tiktok.com' in url_lower:
            tiktok_cookies_file = self._exportar_cookies_tiktok()

        facebook_cookies_file = None
        if 'facebook.com' in url_lower or 'fb.watch' in url_lower:
            facebook_cookies_file = self._exportar_cookies_facebook()

        item_id = uuid.uuid4().hex
        ydl_opts = _build_ydl_opts(
            quality, fmt, self._dest_folder, url=url,
            tiktok_cookies_file=tiktok_cookies_file,
            facebook_cookies_file=facebook_cookies_file,
        )

        widget = QueueItemWidget(item_id, url, dest_folder=self._dest_folder, source_url=url)
        widget.set_obteniendo_info()
        self._widgets[item_id] = widget
        self.queue_layout.insertWidget(self.queue_layout.count() - 1, widget)
        widget.cancel_requested.connect(self._cancelar_descarga)
        widget.goto_tiktok_requested.connect(self._ir_a_tiktok)
        widget.retry_requested.connect(self._reintentar_descarga)

        self._download_args[item_id] = (url, ydl_opts, page_url)
        if prioridad:
            self._pending_queue.insert(0, (item_id, url, ydl_opts, page_url))
        else:
            self._pending_queue.append((item_id, url, ydl_opts, page_url))

        self._resolver_info(item_id, url, quality)
        self._procesar_cola()

    def _resolver_info(self, item_id, url, quality):
        worker = InfoResolverWorker(item_id, url, quality, parent=self)
        self._info_workers[item_id] = worker
        worker.resolved.connect(self._on_info_ready)
        worker.failed.connect(self._on_info_failed)
        worker.finished.connect(lambda: self._info_workers.pop(item_id, None))
        worker.start()

    def _on_info_ready(self, item_id, titulo, thumb_url, filesize, thumb_bytes):
        widget = self._widgets.get(item_id)
        if widget is None:
            return
        widget.set_title(titulo)
        widget.set_size(filesize)
        widget.thumb_url = thumb_url or ''
        if thumb_bytes:
            widget.set_thumbnail_bytes(thumb_bytes)
        elif thumb_url:
            widget.set_thumbnail(self._thumb_manager, thumb_url)

    def _on_info_failed(self, item_id):
        widget = self._widgets.get(item_id)
        if widget is None:
            return
        widget.set_title("Video desconocido")
        widget.set_size_text("")

    def _procesar_cola(self):
        while self._active_count < self.MAX_CONCURRENT and self._pending_queue:
            item_id, url, ydl_opts, page_url = self._pending_queue.pop(0)
            self._iniciar_descarga(item_id, url, ydl_opts, page_url)

    def _iniciar_descarga(self, item_id, url, ydl_opts, page_url=None):
        widget = self._widgets.get(item_id)
        if widget is None:
            return

        worker = DownloadWorker(item_id, url, ydl_opts, parent=self, page_url=page_url)
        self._workers[item_id] = worker
        self._active_count += 1

        widget.set_status('downloading')
        worker.progress.connect(self._on_progress)
        worker.finished_ok.connect(self._on_finished_ok)
        worker.failed.connect(self._on_failed)
        worker.retrying.connect(self._on_retrying)
        worker.finished.connect(lambda: self._cleanup_worker(item_id))
        worker.start()

    def _cancelar_descarga(self, item_id):
        worker = self._workers.get(item_id)
        if worker is not None:
            worker.cancel()
            return

        for i, (pid, _, _, _) in enumerate(self._pending_queue):
            if pid == item_id:
                del self._pending_queue[i]
                break

        widget = self._widgets.get(item_id)
        if widget is not None:
            widget.set_status('cancelled')

    def _reintentar_descarga(self, item_id):
        """Vuelve a encolar una descarga que quedó en error, con la misma
        URL/opciones originales (ver _download_args, guardado al crear la
        tarjeta)."""
        args = self._download_args.get(item_id)
        widget = self._widgets.get(item_id)
        if args is None or widget is None:
            return
        url, ydl_opts, page_url = args
        widget.set_status('queued')
        widget.set_progress(0)
        self._pending_queue.append((item_id, url, ydl_opts, page_url))
        self._procesar_cola()

    def _on_progress(self, item_id, percent, extra):
        widget = self._widgets.get(item_id)
        if widget is not None:
            widget.set_progress(percent, extra)
        self._item_progress[item_id] = percent
        self._actualizar_progreso_global()

    def _actualizar_progreso_global(self):
        if not self._item_progress:
            self.global_progress_bar.setVisible(False)
            self.global_progress_bar.setValue(0)
            return
        promedio = sum(self._item_progress.values()) / len(self._item_progress)
        self.global_progress_bar.setVisible(True)
        self.global_progress_bar.setValue(int(promedio))

    def _on_retrying(self, item_id, mensaje):
        widget = self._widgets.get(item_id)
        if widget is not None:
            widget.set_retrying(mensaje)

    def _on_finished_ok(self, item_id, ruta):
        self._download_args.pop(item_id, None)
        widget = self._widgets.pop(item_id, None)
        titulo = ''
        pixmap = None
        thumb_url = ''
        source_url = ''
        if widget is not None:
            titulo = widget._full_title
            pixmap = widget.lbl_thumb.pixmap()
            thumb_url = widget.thumb_url
            source_url = widget.source_url
            self.queue_layout.removeWidget(widget)
            widget.setParent(None)
            widget.deleteLater()

        if titulo == "Obteniendo información...":
            titulo = ''

        if not thumb_url and source_url:
            video_id = _extraer_id_youtube(source_url)
            if video_id:
                thumb_url = f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg"

        if not self._incognito:
            if not titulo and ruta:
                titulo = os.path.splitext(os.path.basename(ruta))[0]
            titulo = titulo or os.path.basename(ruta) or 'Video descargado'
            size_bytes = os.path.getsize(ruta) if ruta and os.path.exists(ruta) else 0
            fecha = datetime.now().strftime('%d/%m/%Y %H:%M')
            self._agregar_a_historial(titulo, ruta, size_bytes, fecha, pixmap, thumb_url)

        carpeta = os.path.dirname(ruta) if ruta else self._dest_folder
        if os.path.isdir(carpeta):
            try:
                os.startfile(carpeta)
            except OSError:
                pass

    # ------------------------------------------------------------------
    # Historial de descargas
    # ------------------------------------------------------------------
    HISTORIAL_MAX = 50

    def _toggle_historial(self, checked):
        self.historial_scroll.setVisible(checked)
        self._actualizar_texto_historial()

    def _actualizar_texto_historial(self):
        flecha = "▾" if self.btn_historial_toggle.isChecked() else "▸"
        hoy = datetime.now().strftime('%d/%m/%Y')
        descargas_hoy = sum(
            1 for entry in self._historial_descargas
            if entry.get('fecha', '').startswith(hoy)
        )
        self.btn_historial_toggle.setText(f"{flecha} Historial ({descargas_hoy} hoy)")

    def _agregar_widget_historial(self, entry, pixmap=None, al_inicio=True):
        widget = HistoryItemWidget(
            entry.get('titulo', ''), entry.get('ruta', ''),
            entry.get('size', 0), entry.get('fecha', ''),
        )
        if pixmap is not None and not pixmap.isNull():
            widget.set_thumbnail_pixmap(pixmap)
        else:
            thumb_url = entry.get('url_thumbnail') or ''
            if thumb_url:
                worker = ThumbnailDownloadWorker(thumb_url, self)
                self._historial_thumb_workers.append(worker)
                worker.resolved.connect(widget.set_thumbnail_bytes)
                worker.finished.connect(
                    lambda w=worker: self._historial_thumb_workers.remove(w)
                    if w in self._historial_thumb_workers else None
                )
                worker.start()
        if al_inicio:
            self.historial_layout.insertWidget(0, widget)
            self._historial_widgets.insert(0, widget)
        else:
            pos = max(0, self.historial_layout.count() - 1)
            self.historial_layout.insertWidget(pos, widget)
            self._historial_widgets.append(widget)
        self._actualizar_texto_historial()

    def _agregar_a_historial(self, titulo, ruta, size_bytes, fecha, pixmap=None, url_thumbnail=''):
        entry = {
            'titulo': titulo, 'ruta': ruta, 'size': size_bytes, 'fecha': fecha,
            'url_thumbnail': url_thumbnail,
        }
        self._historial_descargas.insert(0, entry)
        if len(self._historial_descargas) > self.HISTORIAL_MAX:
            self._historial_descargas = self._historial_descargas[:self.HISTORIAL_MAX]
            if self._historial_widgets:
                viejo = self._historial_widgets.pop()
                viejo.setParent(None)
                viejo.deleteLater()
        self._guardar_historial()
        self._agregar_widget_historial(entry, pixmap, al_inicio=True)

    def _guardar_historial(self):
        settings = QSettings('SimpleResolve', 'SimpleDownloader')
        settings.setValue('historial_descargas', json.dumps(self._historial_descargas))

    def _cargar_historial(self):
        settings = QSettings('SimpleResolve', 'SimpleDownloader')
        raw = settings.value('historial_descargas', '')
        if not raw:
            self._actualizar_texto_historial()
            return
        try:
            self._historial_descargas = json.loads(raw)
        except (TypeError, ValueError):
            self._historial_descargas = []
        for entry in self._historial_descargas:
            self._agregar_widget_historial(entry, al_inicio=False)

    def _on_failed(self, item_id, mensaje):
        widget = self._widgets.get(item_id)
        if widget is None:
            return
        if mensaje == "Cancelado por el usuario":
            widget.set_status('cancelled')
        else:
            if 'ffmpeg' in mensaje.lower():
                texto = "ffmpeg no encontrado"
            else:
                if _AUTH_ERROR_RE.search(mensaje):
                    if not os.path.exists(_YOUTUBE_COOKIES_PATH):
                        self.auth_banner.setVisible(True)
                texto = _mensaje_error_legible(mensaje)
            widget.set_status('error', detail=texto)

    def _cleanup_worker(self, item_id):
        self._workers.pop(item_id, None)
        self._active_count = max(0, self._active_count - 1)
        self._item_progress.pop(item_id, None)
        self._actualizar_progreso_global()
        self._procesar_cola()

    # ------------------------------------------------------------------
    def closeEvent(self, event):
        for worker in list(self._workers.values()):
            worker.cancel()
        self.cerrado = True
        if hasattr(self, '_browser_stack'):
            for i in range(self._browser_stack.count()):
                self._browser_stack.widget(i).shutdown()
        if hasattr(self, 'fondo_video_global'):
            self.fondo_video_global.detener()
        super().closeEvent(event)


if __name__ == '__main__':
    # Punto de entrada cuando este archivo se ejecuta directamente, que es
    # lo que pasa en modo compilado (SimpleDownloader.exe se compila desde
    # este script, ver SimpleDownloader.spec). En modo desarrollo se usa en
    # cambio _run_downloader.py, que hace exactamente esto mismo.
    if '--token' in sys.argv:
        idx = sys.argv.index('--token')
        if idx + 1 < len(sys.argv):
            auth_manager.guardar_token(sys.argv[idx + 1])
            auth_manager.limpiar_marca_sesion_invalida()

    app = QApplication(sys.argv)
    w = SimpleDownloaderWindow()
    w.show()
    sys.exit(app.exec())
