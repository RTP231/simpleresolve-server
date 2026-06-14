# Métodos reconstruidos de la clase SimpleResolve (desde bytecode interfaz.pyc)
# Se integrarán en interfaz.py en el paso final.

    def set_color_botones(self, color_hex):
        self.config_personalizacion['color_botones'] = color_hex
        personalizacion.guardar_config(self.config_personalizacion)
        self.aplicar_tema()
        self._aplicar_fondo_animado()

    def set_color_fondo(self, color_hex):
        self.config_personalizacion['color_fondo'] = color_hex
        personalizacion.guardar_config(self.config_personalizacion)
        self.glass.set_color_fondo(color_hex)

    def set_opacidad_botones(self, valor):
        self.config_personalizacion['opacidad_botones'] = valor
        personalizacion.guardar_config(self.config_personalizacion)
        self.aplicar_tema()

    def set_imagen_fondo(self, ruta):
        self.config_personalizacion['imagen_fondo'] = ruta
        personalizacion.guardar_config(self.config_personalizacion)
        pixmap = None
        if ruta:
            pix = QPixmap(ruta)
            if not pix.isNull():
                pixmap = pix
        self.glass.set_pixmap_fondo(pixmap)

    def set_opacidad_imagen(self, valor):
        self.config_personalizacion['opacidad_imagen'] = valor
        personalizacion.guardar_config(self.config_personalizacion)
        self.glass.set_opacidad_imagen(valor)

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

    def _iniciar_cuenta_autodestruccion(self):
        if self.grabando or self._timer_autodestruccion is not None:
            return
        self._timer_autodestruccion = QTimer(self)
        self._timer_autodestruccion.setSingleShot(True)
        self._timer_autodestruccion.timeout.connect(self._confirmar_autodestruccion)
        self._timer_autodestruccion.start(self._DURACION_AUTODESTRUCCION_MS)

    def _cancelar_cuenta_autodestruccion(self):
        if self._timer_autodestruccion is not None:
            self._timer_autodestruccion.stop()
            self._timer_autodestruccion = None

    def _confirmar_autodestruccion(self):
        self._timer_autodestruccion = None
        if not self._autodestruccion_armada:
            return
        if self.oculto:
            self.toggle_visibilidad()
        respuesta = QMessageBox.warning(
            self,
            'Autodestrucción',
            'Esto eliminará SimpleResolve, SimpleDownload y SimplePDF de este equipo: configuración, caché, accesos directos y entradas de inicio automático.\n\nEsta acción NO se puede deshacer. ¿Continuar?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if respuesta != QMessageBox.StandardButton.Yes:
            return
        if self.ventana_download is not None and not self.ventana_download.cerrado:
            self.ventana_download.close()
        if self.ventana_pdf is not None and not self.ventana_pdf.cerrado:
            self.ventana_pdf.close()
        try:
            self_destruct.ejecutar_autodestruccion(dry_run=False)
        except Exception as e:
            QMessageBox.critical(self, 'Autodestrucción', f'Ocurrió un error durante la autodestrucción:\n{e}')
            return
        QApplication.quit()

    # NOTA: dentro de iniciar_listeners(), la función interna on_release debe incluir:
    #
    # def on_release(key):
    #     if key == self.atajo_autodestruccion:
    #         self._autodestruccion_armada = False
    #         QTimer.singleShot(0, self._cancelar_cuenta_autodestruccion)
    #
    # (revisar el on_release existente en la versión vieja y fusionar esta lógica)

    def abrir_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #16142a; color: #eaeaf5; border: 1px solid rgba(124,111,255,0.35); border-radius: 6px; padding: 4px; }
            QMenu::item { padding: 6px 16px; border-radius: 4px; }
            QMenu::item:selected { background-color: rgba(124,111,255,0.25); }
        """)
        accion_download = menu.addAction('⬇ SimpleDownload')
        accion_download.triggered.connect(self.abrir_simpledownload)
        accion_pdf = menu.addAction('📄 SimplePDF')
        accion_pdf.triggered.connect(self.abrir_simplepdf)
        menu.exec(self.btn_menu.mapToGlobal(QPoint(0, self.btn_menu.height())))

    def abrir_simpledownload(self):
        if self.ventana_download is None or self.ventana_download.cerrado:
            from simpledownload import SimpleDownload
            self.ventana_download = SimpleDownload(ventana_resolve=self)
            self.ventana_download.show()
            return
        self.ventana_download.show()
        self.ventana_download.raise_()
        self.ventana_download.activateWindow()

    def abrir_simplepdf(self):
        if self.ventana_pdf is None or self.ventana_pdf.cerrado:
            from simplepdf import SimplePDF
            self.ventana_pdf = SimplePDF(ventana_resolve=self)
            self.ventana_pdf.show()
            return
        self.ventana_pdf.show()
        self.ventana_pdf.raise_()
        self.ventana_pdf.activateWindow()

    def _iniciar_verificacion_periodica(self):
        self._verificar_sesion()
        self._timer_sesion = QTimer(self)
        self._timer_sesion.timeout.connect(self._verificar_sesion)
        self._timer_sesion.start(180000)

    def _verificar_sesion(self):
        if self._hilo_verificar and self._hilo_verificar.isRunning():
            return
        self._hilo_verificar = HiloVerificar()
        self._hilo_verificar.resultado.connect(self._on_verificacion)
        self._hilo_verificar.start()

    def _on_verificacion(self, valido):
        if valido:
            return
        if self._timer_sesion:
            self._timer_sesion.stop()
        auth_manager.borrar_token()
        if self.oculto:
            self.toggle_visibilidad()
        self.btn_cap.setEnabled(False)
        self.lbl_resp.setStyleSheet('color: #ff6b8a; background: transparent; font-size: 14px;')
        self.lbl_resp.setText('Sesión expirada.')
        if self.ventana_download is not None and not self.ventana_download.cerrado:
            self.ventana_download.close()
        if self.ventana_pdf is not None and not self.ventana_pdf.cerrado:
            self.ventana_pdf.close()
        QTimer.singleShot(2000, self.close)

    def _restaurar_posicion(self):
        x = self.config_personalizacion.get('pos_x')
        y = self.config_personalizacion.get('pos_y')
        if x is not None and y is not None:
            self.move(x, y)

    def abrir_personalizacion(self):
        dlg = PanelPersonalizacion(self, self)
        dlg.exec()

    def restaurar_personalizacion_defaults(self):
        self.config_personalizacion = personalizacion.DEFAULTS.copy()
        personalizacion.guardar_config(self.config_personalizacion)
        self.glass.set_color_fondo(None)
        self.glass.set_pixmap_fondo(None)
        self.glass.set_opacidad_imagen(self.config_personalizacion['opacidad_imagen'])
        self.aplicar_tema()
        self._aplicar_fondo_animado()

    def _aplicar_personalizacion_visual(self):
        cfg = self.config_personalizacion
        self.glass.set_color_fondo(cfg.get('color_fondo'))
        self.glass.set_opacidad_imagen(cfg.get('opacidad_imagen', 50))
        ruta = cfg.get('imagen_fondo')
        pixmap = None
        if ruta:
            pix = QPixmap(ruta)
            if not pix.isNull():
                pixmap = pix
        self.glass.set_pixmap_fondo(pixmap)
        self._aplicar_fondo_animado()

    def _aplicar_fondo_animado(self):
        cfg = self.config_personalizacion
        color = cfg.get('color_botones') or '#7c6fff'
        opacidad = cfg.get('fondo_animado_opacidad', 30)
        self.glass.fondo_animado.set_color(color)
        self.glass.fondo_animado.set_velocidad(cfg.get('fondo_animado_velocidad', 'normal'))
        self.glass.fondo_animado.set_opacidad(opacidad)
        self.glass.fondo_video.set_opacidad(opacidad)
        rendimiento = cfg.get('fondo_animado_rendimiento', False)
        self.glass.fondo_animado.set_rendimiento(rendimiento)
        self.glass.fondo_video.set_rendimiento(rendimiento)
        activo = cfg.get('fondo_animado_activo', False)
        video = cfg.get('video_fondo')
        if activo and video:
            self.glass.fondo_animado.set_activo(False)
            self.glass.fondo_video.set_video(video)
            return
        if activo:
            self.glass.fondo_video.set_video(None)
            self.glass.fondo_animado.set_tipo(cfg.get('fondo_animado_tipo', 'particulas'))
            self.glass.fondo_animado.set_activo(True)
            return
        self.glass.fondo_animado.set_activo(False)
        self.glass.fondo_video.set_video(None)

    def _css_botones_custom(self, color_hex, opacidad):
        c = QColor(color_hex)
        rgb = f"{c.red()},{c.green()},{c.blue()}"
        alpha = max(0.1, min(100, opacidad)) / 100
        alpha_hover = min(1.0, alpha + 0.15)
        luminancia = 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
        texto = '#1a1a2e' if luminancia > 140 else '#ffffff'
        return f"""
            #btnCap, #btnCerrar, #btnAtalos, #btnCambiar, #btnHeader, #btnOpToggle {{
                background: rgba({rgb},{alpha});
                color: {texto};
                border: 1px solid rgba({rgb},0.6);
            }}
            #btnCap:hover, #btnCerrar:hover, #btnAtalos:hover, #btnCambiar:hover, #btnHeader:hover, #btnOpToggle:hover {{
                background: rgba({rgb},{alpha_hover});
            }}
            #btnCap:disabled {{ background: rgba({rgb},0.25); color: rgba(255,255,255,0.4); }}
            #keyBadge {{ color: {texto}; background: rgba({rgb},{alpha}); border: 1px solid rgba({rgb},0.6); }}
        """
