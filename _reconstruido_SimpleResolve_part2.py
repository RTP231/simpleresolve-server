# Métodos reconstruidos (parte 2) de la clase SimpleResolve (desde bytecode interfaz.pyc)
# Se integrarán en interfaz.py en el paso final, reemplazando a los métodos
# del mismo nombre en la versión vieja (salvo que se indique lo contrario).
#
# IMPORTS / CONSTANTES NUEVOS REQUERIDOS EN interfaz.py:
#   - from ia import preguntar_ia, AUTH_ERROR   (ia.py debe reconstruirse aparte:
#     ahora preguntar_ia devuelve (respuesta, capturas_restantes) y expone AUTH_ERROR)
#   - from PyQt6.QtWidgets import QApplication  (usado en closeEvent)
#   - HiloCaptura.resultado debe pasar a pyqtSignal(str, int)  (ver HiloCaptura.run)
#   - Atributo de clase _DURACION_AUTODESTRUCCION_MS (usado por _iniciar_cuenta_autodestruccion,
#     ya en _reconstruido_SimpleResolve.py) -- valor exacto desconocido, placeholder sugerido: 3000
#   - initUI debe crear self.btn_edit_autodestruccion y self.lbl_key_autodestruccion
#     (fila nueva en el panel de atajos) -- pendiente de Task #12
#   - Eliminar: self.tema_oscuro, toggle_tema, _css_light, btn_tema (ya no se usan)
#   - PENDIENTE (no incluido en los dumps analizados): set_opacidad_ventana() en
#     fondo_animado/fondo_video (AnimacionFondoWidget / FondoVideoWidget)


# ════════════════════════════════
#  __init__
# ════════════════════════════════
    def __init__(self):
        super().__init__()
        self.drag_pos = QPoint()
        self.capturas_restantes = None
        self.grabando = None
        self.atajo_cap = Key.f9
        self.atajo_close = Key.f10
        self.atajo_ocultar = Key.f8
        self.atajo_cap_mouse = None
        self.atajo_close_mouse = None
        self.atajo_autodestruccion = Key.pause
        self._autodestruccion_armada = False
        self._timer_autodestruccion = None
        self.oculto = False
        self.color_texto = "#00d4aa"
        self.font_size = 14
        self.modo_horizontal = False
        self._opacity_timer = None
        self.listener_mouse = None
        self.listener_kb = None
        self._grab_mouse = None
        self._grab_kb = None
        self._hilo_verificar = None
        self._timer_sesion = None
        self.ventana_download = None
        self.ventana_pdf = None
        self.cerrado = False
        self.config_personalizacion = personalizacion.cargar_config()
        self.initUI()
        self.iniciar_listeners()
        QTimer.singleShot(30000, self._iniciar_verificacion_periodica)
        _log_event('app_open')


# ════════════════════════════════
#  TRANSPARENCIA (actualizado: ahora también ajusta la opacidad
#  de los fondos animado/video)
# ════════════════════════════════
    def _aplicar_opacidad(self):
        self._opacity_timer = None
        valor = getattr(self, '_opacity_valor', self.barra.slider.value())
        if valor == 0:
            self.w_header.setVisible(False)
            self.w_btns.setVisible(False)
            self.btn_atajos.setVisible(False)
            self.panel.setVisible(False)
            self.w_footer.setVisible(False)
            self.barra.btn_color.setVisible(False)
            self.glass.set_transparente(True)
            self.resp_panel.set_transparente(True)
            self.barra.set_transparente(True)
            self.setWindowOpacity(1.0)
            self.glass.fondo_animado.set_opacidad_ventana(0)
            self.glass.fondo_video.set_opacidad_ventana(0)
            self.adjustSize()
        else:
            if not self.w_header.isVisible():
                self.w_header.setVisible(True)
                self.w_btns.setVisible(True)
                self.btn_atajos.setVisible(True)
                self.w_footer.setVisible(True)
                self.barra.btn_color.setVisible(True)
                self.glass.set_transparente(False)
                self.resp_panel.set_transparente(False)
                self.barra.set_transparente(False)
                self.glass.setStyleSheet("")
                self.aplicar_tema()
                self.adjustSize()
            self.setWindowOpacity(max(0.15, valor / 100))
            self.glass.fondo_animado.set_opacidad_ventana(valor)
            self.glass.fondo_video.set_opacidad_ventana(valor)


# ════════════════════════════════
#  LISTENERS (actualizado: incluye soporte de autodestrucción
#  con on_release además de on_press)
# ════════════════════════════════
    def iniciar_listeners(self):
        def on_press(key):
            if self.grabando: return
            if key == self.atajo_cap:
                QTimer.singleShot(0, self.capturar)
            elif key == self.atajo_close:
                QTimer.singleShot(0, self.close)
            elif key == self.atajo_ocultar:
                QTimer.singleShot(0, self.toggle_visibilidad)
            elif key == self.atajo_autodestruccion:
                if not self._autodestruccion_armada:
                    self._autodestruccion_armada = True
                    QTimer.singleShot(0, self._iniciar_cuenta_autodestruccion)

        def on_release(key):
            if key == self.atajo_autodestruccion:
                self._autodestruccion_armada = False
                QTimer.singleShot(0, self._cancelar_cuenta_autodestruccion)

        def on_click(x, y, button, pressed):
            if not pressed or self.grabando: return
            if self.atajo_cap_mouse and button == self.atajo_cap_mouse:
                QTimer.singleShot(0, self.capturar)
            if self.atajo_close_mouse and button == self.atajo_close_mouse:
                QTimer.singleShot(0, self.close)

        self.listener_kb    = pynput_kb.Listener(on_press=on_press, on_release=on_release, daemon=True)
        self.listener_mouse = pynput_mouse.Listener(on_click=on_click, daemon=True)
        self.listener_kb.start()
        self.listener_mouse.start()


# ════════════════════════════════
#  GRABACIÓN UNIVERSAL (actualizado: incluye atajo "autodestruccion")
# ════════════════════════════════
    def iniciar_grabacion(self, tipo):
        self.grabando = tipo
        btns = {"cap": self.btn_edit_cap, "close": self.btn_edit_close, "ocultar": self.btn_edit_ocultar, "autodestruccion": self.btn_edit_autodestruccion}
        lbls = {"cap": self.lbl_key_cap,  "close": self.lbl_key_close,  "ocultar": self.lbl_key_ocultar,  "autodestruccion": self.lbl_key_autodestruccion}
        btns[tipo].setText("⏺")
        lbls[tipo].setText("...")

        for l in [self._grab_mouse, self._grab_kb]:
            try:
                if l: l.stop()
            except: pass

        def on_kb(key):
            if not self.grabando: return False
            nombre = self._nombre_tecla(key)
            self._asignar(nombre, False, key, None)
            return False

        def on_click(x, y, button, pressed):
            if not pressed or not self.grabando: return False
            if self.grabando == "autodestruccion":
                return None
            nombre = str(button).replace("Button.", "").upper()
            if nombre in ("LEFT", "RIGHT", "MIDDLE"): return None
            self._asignar(f"M-{nombre}", True, None, button)
            return False

        self._grab_kb    = pynput_kb.Listener(on_press=on_kb, daemon=True)
        self._grab_mouse = pynput_mouse.Listener(on_click=on_click, daemon=True)
        self._grab_kb.start()
        self._grab_mouse.start()

    def _asignar(self, nombre, es_mouse, key_obj, boton):
        tipo = self.grabando
        self.grabando = None
        btns = {"cap": self.btn_edit_cap, "close": self.btn_edit_close, "ocultar": self.btn_edit_ocultar, "autodestruccion": self.btn_edit_autodestruccion}
        lbls = {"cap": self.lbl_key_cap,  "close": self.lbl_key_close,  "ocultar": self.lbl_key_ocultar,  "autodestruccion": self.lbl_key_autodestruccion}
        btns[tipo].setText("✎")
        lbls[tipo].setText(nombre)
        if tipo == "cap":
            self.atajo_cap_mouse = boton if es_mouse else None
            if not es_mouse: self.atajo_cap = key_obj
        elif tipo == "close":
            self.atajo_close_mouse = boton if es_mouse else None
            if not es_mouse: self.atajo_close = key_obj
        elif tipo == "ocultar":
            if not es_mouse: self.atajo_ocultar = key_obj
        elif tipo == "autodestruccion":
            if not es_mouse: self.atajo_autodestruccion = key_obj


# ════════════════════════════════
#  CAPTURAR (actualizado: usa capturas_restantes en vez de capturas,
#  texto "Analizando..." + repaint(), delay 200ms en vez de 300ms)
# ════════════════════════════════
    def capturar(self):
        if self.capturas_restantes is not None and self.capturas_restantes <= 0:
            self.lbl_resp.setText("Límite alcanzado.")
            return
        if hasattr(self, 'hilo') and self.hilo is not None and self.hilo.isRunning():
            return
        self.btn_cap.setEnabled(False)
        self.lbl_resp.setText("Analizando...")
        self.repaint()
        self.hide()
        QTimer.singleShot(200, self._tomar_captura)

    # _tomar_captura no cambió respecto a la versión vieja:
    # def _tomar_captura(self): ... (sin cambios)


# ════════════════════════════════
#  MOSTRAR RESPUESTA (actualizado: nuevo parámetro `capturas`,
#  manejo de AUTH_ERROR con LoginDialog, actualización de
#  "Capturas restantes")
# ════════════════════════════════
    def mostrar_respuesta(self, texto, capturas=-1):
        self.show()
        self.raise_()
        self.activateWindow()

        if texto == AUTH_ERROR:
            from login import LoginDialog
            from PyQt6.QtWidgets import QDialog
            dlg = LoginDialog()
            if dlg.exec() == QDialog.DialogCode.Accepted:
                self.lbl_resp.setText('Sesión renovada.')
                self.btn_cap.setEnabled(True)
            else:
                self.close()
            QTimer.singleShot(50, self.adjustSize)
            return

        texto_limpio = self.limpiar_respuesta(texto)
        if self.modo_horizontal:
            self.lbl_resp.setText(self._aplicar_modo(texto_limpio))
        else:
            self.lbl_resp.setText(texto_limpio)
        QTimer.singleShot(50, self.adjustSize)
        self.btn_cap.setEnabled(True)

        if capturas >= 0:
            self.capturas_restantes = capturas
            self.lbl_uso.setText(f'Capturas restantes: {capturas}')


# ════════════════════════════════
#  TEMA (actualizado: ya no hay tema claro/oscuro alternable;
#  siempre usa _css_dark() + estilo de botones personalizado si
#  el usuario configuró un color_botones)
# ════════════════════════════════
    def aplicar_tema(self):
        self.lbl_resp.setStyleSheet(
            f"color: {self.color_texto}; background: transparent; font-size: {self.font_size}px;"
        )
        css = self._css_dark()
        color_botones = self.config_personalizacion.get('color_botones')
        if color_botones:
            opacidad_botones = self.config_personalizacion.get('opacidad_botones', 100)
            css += self._css_botones_custom(color_botones, opacidad_botones)
        self.glass.setStyleSheet(css)

    def _css_dark(self):
        return """
            QPushButton {
                background: rgba(124,111,255,0.12);
                color: #eaeaf5;
                border: 1px solid rgba(124,111,255,0.3);
                border-radius: 8px;
                padding: 6px 10px;
            }
            QPushButton:hover { background: rgba(124,111,255,0.22); }
            QPushButton:checked { background: rgba(124,111,255,0.35); font-weight: bold; }
            QPushButton:disabled { background: rgba(255,255,255,0.04); color: #55547a; border-color: rgba(255,255,255,0.06); }
            QLabel       { color: #eaeaf5; font-size: 11px; background: transparent; }
            #lblUso      { color: #55547a; font-size: 10px; }
            #lblAtajo    { color: #9898b8; font-size: 11px; }
            #keyBadge    { color: #7c6fff; background: rgba(124,111,255,0.15); border: 1px solid rgba(124,111,255,0.35); border-radius: 4px; padding: 1px 6px; font-size: 10px; font-weight: bold; }
            #btnCap      { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #7c6fff,stop:1 #5a4fcf); color: white; border: none; border-radius: 7px; padding: 5px; font-weight: bold; font-size: 11px; }
            #btnCap:hover    { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #9d97ff,stop:1 #7c6fff); }
            #btnCap:disabled { background: rgba(42,41,64,180); color: #55547a; border: none; }
            #btnCerrar   { background: rgba(255,77,106,0.1); color: #ff4d6a; border: 1px solid rgba(255,77,106,0.25); border-radius: 7px; font-size: 11px; padding: 5px; }
            #btnCerrar:hover { background: rgba(255,77,106,0.2); }
            #btnAtalos   { background: rgba(255,255,255,0.05); color: #9898b8; border: 1px solid rgba(255,255,255,0.1); border-radius: 7px; padding: 3px; font-size: 10px; }
            #btnAtalos:hover { background: rgba(124,111,255,0.15); color: #7c6fff; border-color: rgba(124,111,255,0.4); }
            #panelAtalos { background: rgba(10,9,22,0.6); border: 1px solid rgba(124,111,255,0.15); border-radius: 9px; }
            #btnCambiar  { background: transparent; color: #55547a; border: 1px solid rgba(255,255,255,0.1); border-radius: 5px; padding: 2px; font-size: 11px; }
            #btnCambiar:hover { border-color: #7c6fff; color: #7c6fff; background: rgba(124,111,255,0.1); }
            #btnHeader   { background: transparent; border: none; color: #55547a; font-size: 12px; border-radius: 5px; padding: 0; }
            #btnHeader:hover { background: rgba(255,255,255,0.08); color: #eaeaf5; }
            QSlider::groove:horizontal { height: 3px; background: transparent; border-radius: 2px; }
            QSlider::handle:horizontal { background: #7c6fff; width: 10px; height: 10px; margin: -4px 0; border-radius: 5px; }
            QSlider::sub-page:horizontal { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #7c6fff,stop:1 #00d4aa); border-radius: 2px; }
            QSlider::add-page:horizontal { background: transparent; border-radius: 2px; }
            #btnOpToggle { background: transparent; color: #eaeaf5; border: 1px solid rgba(124,111,255,0.3); border-radius: 4px; font-size: 11px; padding: 0px; }
            #btnOpToggle:hover { background: rgba(124,111,255,0.2); border-color: rgba(124,111,255,0.7); }
        """

    # ELIMINAR: _css_light (ya no se usa, no hay tema claro)


# ════════════════════════════════
#  EVENTOS DE VENTANA
# ════════════════════════════════
    # mousePressEvent y mouseMoveEvent NO cambiaron respecto a la versión vieja.

    def closeEvent(self, event):
        _log_event('app_close')
        self.cerrado = True
        self.config_personalizacion['pos_x'] = self.x()
        self.config_personalizacion['pos_y'] = self.y()
        personalizacion.guardar_config(self.config_personalizacion)

        if self._timer_sesion:
            self._timer_sesion.stop()

        if self._hilo_verificar and self._hilo_verificar.isRunning():
            self._hilo_verificar.quit()
            self._hilo_verificar.wait(500)

        if hasattr(self, 'hilo') and self.hilo is not None and self.hilo.isRunning():
            self.hilo.quit()
            self.hilo.wait(1000)

        for l in [self.listener_mouse, self.listener_kb, self._grab_mouse, self._grab_kb]:
            try:
                if l: l.stop()
            except: pass

        event.accept()

        from PyQt6.QtWidgets import QApplication
        descarga_abierta = self.ventana_download is not None and not self.ventana_download.cerrado
        pdf_abierto = self.ventana_pdf is not None and not self.ventana_pdf.cerrado
        if not descarga_abierta and not pdf_abierto:
            QApplication.instance().quit()


# ════════════════════════════════
#  HiloCaptura.run (actualizado: ahora preguntar_ia devuelve una
#  tupla (respuesta, capturas_restantes); en error, capturas = -1)
#  -> resultado debe redeclararse como: resultado = pyqtSignal(str, int)
# ════════════════════════════════
#    def run(self):
#        try:
#            img = tomar_captura()
#            respuesta, capturas = preguntar_ia(img)
#        except Exception as e:
#            respuesta = f"Error: {str(e)}"
#            capturas = -1
#        self.resultado.emit(respuesta, capturas)


# ════════════════════════════════
#  BarraFlotante.paintEvent (actualizado: ya no dibuja nada;
#  el fondo/borde redondeado ahora se maneja por otro medio,
#  posiblemente QSS o el propio glass). Reemplaza al método viejo
#  que dibujaba un QPainter con drawRoundedRect.
# ════════════════════════════════
#    def paintEvent(self, event):
#        pass
