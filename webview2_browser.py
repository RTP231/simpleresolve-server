"""Widget de navegador embebido usando Microsoft Edge WebView2.

Reemplaza al anterior enfoque basado en Selenium + Chrome real incrustado vía
win32gui (que causaba bloqueos de teclado/mouse y, con QWindow.fromWinId,
renderizaba en blanco). WebView2 es un control de WinForms diseñado desde el
inicio para ser embebido como control hijo, por lo que `SetParent` funciona
correctamente: renderiza el contenido y recibe foco de teclado/mouse sin
necesidad de AttachThreadInput ni timers de foco.

El control WebView2 se crea y se administra en un hilo STA de .NET (requerido
por WebView2/COM); el widget de Qt sólo incrusta su HWND y reenvía
navegación/eventos mediante `Form.Invoke` (marshaling de hilo de WinForms).
"""
import os
import re
import sys
import shutil
import tempfile
import threading

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QProgressBar

try:
    import win32gui
    import win32con
    _WIN32_OK = True
except ImportError:
    _WIN32_OK = False


_VIDEO_EXT_RE = re.compile(r'\.(mp4|m3u8|ts|webm|mkv)(?:[?#]|$)', re.IGNORECASE)

# URLs internas (segmentos de stream, telemetría, recursos estáticos) que
# nunca deben tratarse como "video detectado": p.ej. videoplayback de
# googlevideo.com son fragmentos internos de YouTube, no el video completo.
IGNORE_URL_PATTERNS = [
    'videoplayback',
    'googlevideo.com',
    'youtube.com/s/',
    'youtube.com/generate_',
    'ytimg.com',
    'doubleclick.net',
    'googleapis.com',
]

_SDK_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'webview2_sdk', 'assemblies')

_WEBVIEW2_OK = True
_WEBVIEW2_IMPORT_ERROR = ''

try:
    import clr
    clr.AddReference("System.Windows.Forms")
    clr.AddReference("System.Drawing")
    if _SDK_DIR not in sys.path:
        sys.path.insert(0, _SDK_DIR)
    clr.AddReference(os.path.join(_SDK_DIR, "Microsoft.Web.WebView2.Core.dll"))
    clr.AddReference(os.path.join(_SDK_DIR, "Microsoft.Web.WebView2.WinForms.dll"))

    from System import Action, String
    from System.Threading import Thread as NetThread, ApartmentState, ThreadStart
    from System.Threading.Tasks import Task
    from System.Windows.Forms import Form, Application, FormBorderStyle, FormStartPosition, Timer as WinFormsTimer
    from System.Drawing import Size, Point
    from Microsoft.Web.WebView2.WinForms import WebView2, CoreWebView2CreationProperties
    from Microsoft.Web.WebView2.Core import CoreWebView2WebResourceContext
except Exception as exc:  # pragma: no cover - entorno sin WebView2 SDK
    _WEBVIEW2_OK = False
    _WEBVIEW2_IMPORT_ERROR = str(exc)


class WebView2BrowserWidget(QWidget):
    """Navegador embebido: control WebView2 (Microsoft Edge) real."""

    url_changed = pyqtSignal(str)
    title_changed = pyqtSignal(str)
    load_started = pyqtSignal()
    load_finished = pyqtSignal()
    video_detected = pyqtSignal(str)

    HOME_URL = "https://www.google.com"

    def __init__(self, incognito=False, parent=None, initial_url=None):
        super().__init__(parent)
        self._incognito = incognito
        self._current_url = ''
        self._current_title = ''
        self._seen_videos = set()
        self._embedded_hwnd = 0
        self._net_thread = None
        self._state = {}
        self._profile_dir = None
        self._loading_widget = None
        self._container = None
        self._pending_url = initial_url

        self.setMinimumSize(200, 200)
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(80)
        self._resize_timer.timeout.connect(self._do_resize_embedded)

        self._ready_timer = QTimer(self)
        self._ready_timer.setInterval(100)
        self._ready_timer.timeout.connect(self._check_ready)

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(150)
        self._poll_timer.timeout.connect(self._poll)
        self._nav_start_count = 0
        self._nav_done_count = 0

        self._build_loading_ui()
        self._dots_timer = QTimer(self)
        self._dots_timer.setInterval(500)
        self._dots_timer.timeout.connect(self._animate_dots)
        self._dots_timer.start()

        self._start_browser()

    # ------------------------------------------------------------------
    # UI de carga
    # ------------------------------------------------------------------
    def _build_loading_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._loading_widget = QWidget(self)
        self._loading_widget.setStyleSheet("background-color: #1e1e1e;")
        lay = QVBoxLayout(self._loading_widget)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._loading_dots = 0
        self._loading_label = QLabel("Iniciando navegador")
        self._loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._loading_label.setStyleSheet(
            "color: #ddd; font-size: 14px; background: transparent;"
        )

        self._loading_bar = QProgressBar()
        self._loading_bar.setRange(0, 0)
        self._loading_bar.setFixedWidth(220)
        self._loading_bar.setTextVisible(False)

        lay.addWidget(self._loading_label)
        lay.addWidget(self._loading_bar, alignment=Qt.AlignmentFlag.AlignCenter)

        outer.addWidget(self._loading_widget)

    def _animate_dots(self):
        self._loading_dots = (self._loading_dots + 1) % 4
        self._loading_label.setText("Iniciando navegador" + "." * self._loading_dots)

    def _hide_loading_ui(self):
        self._dots_timer.stop()
        if self._loading_widget is not None:
            self._loading_widget.hide()
            self.layout().removeWidget(self._loading_widget)
            self._loading_widget.deleteLater()
            self._loading_widget = None

    def _show_message(self, mensaje):
        self._hide_loading_ui()
        if self.layout() is None:
            QVBoxLayout(self)
        lbl = QLabel(mensaje)
        lbl.setWordWrap(True)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("color: #aaa; background: transparent; padding: 20px;")
        self.layout().addWidget(lbl)

    # ------------------------------------------------------------------
    # Arranque del control WebView2 (hilo STA de .NET)
    # ------------------------------------------------------------------
    def _start_browser(self):
        if not _WIN32_OK:
            self._show_message(
                "pywin32 no está disponible.\n"
                "Instala 'pywin32' para embeber el navegador."
            )
            return
        if not _WEBVIEW2_OK:
            self._show_message(
                "Microsoft Edge WebView2 no está disponible:\n"
                f"{_WEBVIEW2_IMPORT_ERROR}\n\n"
                "Instala 'pythonnet' y asegúrate de que el SDK de WebView2 "
                "esté presente en 'webview2_sdk/assemblies'."
            )
            return

        if self._incognito:
            self._profile_dir = tempfile.mkdtemp(prefix='SimpleResolve_WV2_')
        else:
            self._profile_dir = os.path.join(
                os.environ.get('LOCALAPPDATA', ''), 'SimpleResolve', 'WebView2Profile'
            )
            os.makedirs(self._profile_dir, exist_ok=True)

        state = self._state

        def net_worker():
            form = Form()
            form.FormBorderStyle = getattr(FormBorderStyle, 'None')
            form.ShowInTaskbar = False
            form.Size = Size(1, 1)
            form.StartPosition = FormStartPosition.Manual
            form.Location = Point(-32000, -32000)

            wv = WebView2()
            wv.Size = Size(1280, 800)
            wv.Location = Point(0, 0)

            props = CoreWebView2CreationProperties()
            props.UserDataFolder = self._profile_dir
            wv.CreationProperties = props

            form.Controls.Add(wv)

            hwnd = int(wv.Handle.ToInt64())
            state['form'] = form
            state['wv'] = wv

            def on_init(sender, args):
                if not args.IsSuccess:
                    state['init_error'] = str(args.InitializationException.Message)
                    state['core_ready'] = True
                    return

                core = wv.CoreWebView2
                state['core'] = core

                # IMPORTANTE: estos callbacks corren en el hilo STA de .NET.
                # Emitir señales de Qt directamente desde aquí puede causar
                # deadlocks entre el GIL de Python y el message loop de
                # WinForms. En su lugar solo se escriben datos simples en
                # `state`/listas; un QTimer en el hilo de Qt (_poll) los lee
                # y emite las señales correspondientes.

                def on_nav_start(s, a):
                    state['nav_start_count'] = state.get('nav_start_count', 0) + 1

                def on_source_changed(s, a):
                    try:
                        state['url'] = str(core.Source)
                    except Exception:
                        pass

                def on_title_changed(s, a):
                    try:
                        state['title'] = str(core.DocumentTitle)
                    except Exception:
                        pass

                def on_nav_completed(s, a):
                    state['nav_done_count'] = state.get('nav_done_count', 0) + 1

                def on_resource_response(s, a):
                    try:
                        uri = str(a.Request.Uri)
                    except Exception:
                        return
                    if not uri:
                        return
                    uri_lower = uri.lower()
                    if any(pat in uri_lower for pat in IGNORE_URL_PATTERNS):
                        return
                    content_type = ''
                    try:
                        content_type = str(a.Response.Headers.GetHeader("Content-Type") or '')
                    except Exception:
                        content_type = ''
                    if 'video' in content_type.lower() or _VIDEO_EXT_RE.search(uri):
                        state.setdefault('video_queue', []).append(uri)

                def on_new_window_requested(s, a):
                    # Los links que intentan abrir una ventana nueva (target="_blank")
                    # o un popup se navegan en el mismo navegador embebido, en vez
                    # de abrir una ventana externa de WebView2/Edge.
                    try:
                        uri = str(a.Uri)
                    except Exception:
                        uri = ''
                    try:
                        a.Handled = True
                    except Exception:
                        pass
                    if uri:
                        core.Navigate(uri)

                core.NavigationStarting += on_nav_start
                core.SourceChanged += on_source_changed
                core.DocumentTitleChanged += on_title_changed
                core.NavigationCompleted += on_nav_completed
                try:
                    core.NewWindowRequested += on_new_window_requested
                except Exception:
                    pass
                try:
                    core.AddWebResourceRequestedFilter("*", CoreWebView2WebResourceContext.All)
                    core.WebResourceResponseReceived += on_resource_response
                except Exception:
                    pass

                # Aplica también a `window.open(...)`: en vez de abrir una
                # ventana nueva, navega la página actual a esa URL. Se inyecta
                # en cada documento (incluye iframes) antes de que su script
                # se ejecute.
                try:
                    core.AddScriptToExecuteOnDocumentCreatedAsync(
                        "window.open = function(url) { "
                        "if (url) { window.location.href = url; } "
                        "return null; };"
                        "window.alert = function() {};"
                        "window.confirm = function() { return false; };"
                        "window.prompt = function() { return null; };"
                    )
                except Exception:
                    pass

                url_to_load = self._pending_url or self.HOME_URL
                core.Navigate(url_to_load)

                state['core_ready'] = True

            wv.CoreWebView2InitializationCompleted += on_init

            # Sólo publicamos el HWND (para que Qt pueda hacer SetParent) y
            # llamamos a EnsureCoreWebView2Async una vez que el message loop
            # de .NET está realmente bombeando mensajes. Durante el Show()
            # inicial el hilo .NET puede bombear mensajes anidados (incluido
            # WM_TIMER) sin haber llegado a Application.Run todavía y
            # mientras retiene el GIL: si Qt llama a SetParent/SendMessage en
            # ese momento, ambos hilos quedan en deadlock. Por eso se usa un
            # retraso fijo (500ms, generoso frente a la duración típica de
            # Show()) en lugar de depender de un Tick/Shown que podría
            # disparar de forma anidada.
            def publish_hwnd():
                import time
                time.sleep(0.5)
                state['hwnd'] = hwnd

            threading.Thread(target=publish_hwnd, daemon=True).start()

            ensure_timer = WinFormsTimer()
            ensure_timer.Interval = 500

            def on_ensure_tick(sender, args):
                ensure_timer.Stop()
                wv.EnsureCoreWebView2Async(None)

            ensure_timer.Tick += on_ensure_tick
            ensure_timer.Start()

            form.Show()
            Application.Run(form)

        self._net_thread = NetThread(ThreadStart(net_worker))
        self._net_thread.SetApartmentState(ApartmentState.STA)
        self._net_thread.IsBackground = True
        self._net_thread.Start()

        self._ready_timer.start()

    def _check_ready(self):
        state = self._state

        if 'init_error' in state and not self._embedded_hwnd:
            self._ready_timer.stop()
            self._show_message(
                "No se pudo iniciar WebView2:\n" + state['init_error']
            )
            return

        # No incrustar (SetParent/SetWindowLong) hasta que CoreWebView2
        # haya terminado de inicializarse. Si se hace mientras el hilo
        # .NET está dentro de la parte síncrona de
        # EnsureCoreWebView2Async, el SendMessage de SetWindowLong hacia
        # esa ventana puede colisionar con esa llamada y producir un
        # deadlock entre el hilo de Qt y el hilo .NET.
        if state.get('hwnd') and state.get('core_ready') and not self._embedded_hwnd:
            self._embed_window(state['hwnd'])

        if self._embedded_hwnd and state.get('core_ready'):
            self._ready_timer.stop()
            self._hide_loading_ui()
            self._poll_timer.start()

    def _poll(self):
        state = self._state

        nav_start = state.get('nav_start_count', 0)
        if nav_start != self._nav_start_count:
            self._nav_start_count = nav_start
            self.load_started.emit()

        url = state.get('url')
        if url is not None and url != self._current_url:
            self._current_url = url
            self.url_changed.emit(url)

        title = state.get('title')
        if title is not None and title != self._current_title:
            self._current_title = title
            self.title_changed.emit(title)

        nav_done = state.get('nav_done_count', 0)
        if nav_done != self._nav_done_count:
            self._nav_done_count = nav_done
            self.load_finished.emit()

        videos = state.get('video_queue')
        if videos:
            state['video_queue'] = []
            for uri in videos:
                if uri in self._seen_videos:
                    continue
                self._seen_videos.add(uri)
                self.video_detected.emit(uri)

    # ------------------------------------------------------------------
    # Incrustado del control WebView2 dentro del QWidget
    # ------------------------------------------------------------------
    def _embed_window(self, hwnd):
        if self._container is None:
            self._container = QWidget(self)
            self._container.setGeometry(0, 0, self.width(), self.height())
            self._container.show()

        try:
            hwnd_container = int(self._container.winId())
            win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, win32con.WS_CHILD | win32con.WS_VISIBLE)
            win32gui.SetParent(hwnd, hwnd_container)
            win32gui.SetWindowPos(
                hwnd, 0, 0, 0, self._container.width(), self._container.height(),
                win32con.SWP_FRAMECHANGED | win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE,
            )
            self._embedded_hwnd = hwnd
        except Exception:
            QTimer.singleShot(200, lambda: self._embed_window(hwnd))

    def _do_resize_embedded(self):
        if not self._embedded_hwnd or self._container is None:
            return
        self._container.setGeometry(0, 0, self.width(), self.height())
        try:
            win32gui.MoveWindow(
                self._embedded_hwnd, 0, 0, self._container.width(), self._container.height(), True
            )
        except Exception:
            self._embedded_hwnd = 0

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._container is not None:
            self._container.setGeometry(0, 0, self.width(), self.height())
        self._resize_timer.start()

    # ------------------------------------------------------------------
    # Ejecución marshalled al hilo STA de .NET
    # ------------------------------------------------------------------
    def _invoke(self, callback):
        form = self._state.get('form')
        if form is None:
            return False
        try:
            form.Invoke(Action(callback))
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Navegación
    # ------------------------------------------------------------------
    def navigate(self, url):
        core = self._state.get('core')
        if core is None:
            self._pending_url = url
            return
        self.load_started.emit()
        self._invoke(lambda: core.Navigate(url))

    def back(self):
        core = self._state.get('core')
        if core is None:
            return
        self.load_started.emit()
        self._invoke(lambda: core.GoBack() if core.CanGoBack else None)

    def forward(self):
        core = self._state.get('core')
        if core is None:
            return
        self.load_started.emit()
        self._invoke(lambda: core.GoForward() if core.CanGoForward else None)

    def reload(self):
        core = self._state.get('core')
        if core is None:
            return
        self.load_started.emit()
        self._invoke(lambda: core.Reload())

    def current_url(self):
        return self._current_url

    def current_title(self):
        return self._current_title

    def run_script(self, script):
        core = self._state.get('core')
        if core is None:
            return
        self._invoke(lambda: core.ExecuteScriptAsync(script))

    def page_source(self):
        core = self._state.get('core')
        if core is None:
            return ''

        import threading
        result = {}
        done = threading.Event()

        def on_done(task):
            try:
                result['html'] = task.Result
            except Exception:
                result['html'] = ''
            done.set()

        def run():
            try:
                task = core.ExecuteScriptAsync("document.documentElement.outerHTML")
                task.ContinueWith(Action[Task[String]](on_done))
            except Exception:
                done.set()

        if not self._invoke(run):
            return ''

        done.wait(3.0)
        html = result.get('html', '') or ''
        # ExecuteScriptAsync devuelve el resultado como literal JSON (con comillas)
        if html.startswith('"') and html.endswith('"'):
            try:
                import json
                html = json.loads(html)
            except Exception:
                pass
        return html

    def get_cookies(self, uri):
        """Devuelve las cookies almacenadas para `uri` como lista de dicts
        (name, value, domain, path, expires, secure, http_only), usando el
        CookieManager de WebView2. Bloquea hasta 3s esperando el resultado."""
        core = self._state.get('core')
        if core is None:
            return []

        import threading
        result = {'cookies': []}
        done = threading.Event()

        def on_done(task):
            try:
                for c in task.Result:
                    result['cookies'].append({
                        'name': c.Name,
                        'value': c.Value,
                        'domain': c.Domain,
                        'path': c.Path,
                        'expires': c.Expires,
                        'secure': c.IsSecure,
                        'http_only': c.IsHttpOnly,
                    })
            except Exception:
                pass
            done.set()

        def run():
            try:
                task = core.CookieManager.GetCookiesAsync(uri)
                task.ContinueWith(Action[Task](on_done))
            except Exception:
                done.set()

        if not self._invoke(run):
            return []

        done.wait(3.0)
        return result['cookies']

    def reset_detection(self):
        self._seen_videos = set()

    # ------------------------------------------------------------------
    def shutdown(self):
        self._ready_timer.stop()
        self._poll_timer.stop()
        self._resize_timer.stop()
        if getattr(self, '_dots_timer', None) is not None:
            self._dots_timer.stop()

        form = self._state.get('form')
        if form is not None:
            try:
                form.Invoke(Action(form.Close))
            except Exception:
                pass

        if self._net_thread is not None:
            try:
                self._net_thread.Join(5000)
            except Exception:
                pass

        if self._incognito and self._profile_dir and os.path.isdir(self._profile_dir):
            shutil.rmtree(self._profile_dir, ignore_errors=True)
