# menu_ver.py
"""Acciones del menú Ver, zoom y barra de estado (mixin de MainWindow).

Extraído de main.py TAL CUAL (sin cambios de comportamiento): cuadrícula,
reglas (con unidad px/cm) y guías; la construcción de la barra de estado
(_build_status_bar, llamada desde __init__ de MainWindow, con sus lecturas de
tamaño/cursor/zoom y la ayuda de herramienta); y todo el zoom (acercar/alejar,
deslizador, ajustar a pantalla, tamaño real, restauración por pestaña), además
de los tooltips con miniatura de las pestañas. MainWindow hereda de
AccionesMenuVer, así que menús y barra siguen conectando con self.* igual."""
from PySide6.QtCore import Qt, QSize, QFile
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QLabel, QPushButton,
                               QProgressBar, QSizePolicy, QSlider, QStatusBar,
                               QToolButton)

from i18n import t
from utilidades import crear_icono, _canvas_thumb_pixmap
import theme


class AccionesMenuVer:
    def toggle_grid(self):
        # Estado GLOBAL: se aplica a todas las pestañas (abiertas y futuras)
        self.global_show_grid = self.grid_action.isChecked()
        for i in range(self.tabs.count()):
            marker = self.tabs.widget(i)
            if marker and hasattr(marker, 'canvas'):
                marker.canvas.set_show_grid(self.global_show_grid)

    def set_grid_tile_global(self, paso):
        """Tamaño del mosaico de la cuadrícula (línea maestra cada `paso` px;
        0 = sin mosaico). Estado GLOBAL, como la propia cuadrícula: se aplica
        a todas las pestañas abiertas y a las futuras (create_new_tab_canvas)."""
        self.global_grid_tile = int(paso)
        for i in range(self.tabs.count()):
            marker = self.tabs.widget(i)
            if marker and hasattr(marker, 'canvas'):
                marker.canvas.set_grid_tile(self.global_grid_tile)

    def toggle_rulers(self):
        # Estado GLOBAL: se aplica a todas las pestañas (abiertas y futuras)
        self.global_show_rulers = self.rulers_action.isChecked()
        for i in range(self.tabs.count()):
            marker = self.tabs.widget(i)
            if marker and hasattr(marker, 'canvas'):
                marker.canvas.set_show_rulers(self.global_show_rulers)
        self._sync_ruler_overlay_geometry()

    def toggle_guides(self):
        # Por DOCUMENTO: el botón/menú actúa sobre el lienzo activo.
        #   Activar  = mostrar y permitir crear guías (arrastrando desde las reglas).
        #   Desactivar = BORRAR las guías de este documento (deshacible).
        on = self.guides_action.isChecked()
        self.global_show_guides = on  # preferencia para las pestañas nuevas
        canvas = self.get_current_canvas()
        if canvas is None:
            return
        if on:
            canvas.show_guides = True
            canvas.update()
        else:
            canvas.disable_guides()

    def _on_guides_changed(self, canvas):
        """Sincroniza el botón/menú de Guías cuando cambian por deshacer/rehacer
        (o al desactivarlas). Solo aplica si es el documento activo."""
        if canvas is self.get_current_canvas():
            self.guides_action.blockSignals(True)
            self.guides_action.setChecked(getattr(canvas, 'show_guides', True))
            self.guides_action.blockSignals(False)

    def set_ruler_unit(self, unit):
        """Cambia la unidad de las reglas (px / cm / in). Afecta a la unidad
        mostrada y a la etiqueta de la esquina; las posiciones internas
        siguen siendo siempre en píxeles."""
        if hasattr(self, 'ruler_overlay'):
            self.ruler_overlay.set_unit(unit)

    def _make_zoom_button(self, icon_path, fallback_text, tooltip, slot):
        """Botón de la barra fija para el zoom: icono si existe; si no, texto."""
        btn = QToolButton()
        if QFile.exists(icon_path):
            btn.setIcon(crear_icono(icon_path))
            btn.setIconSize(QSize(20, 20))
        else:
            btn.setText(fallback_text)
        btn.setToolTip(tooltip)
        btn.setFocusPolicy(Qt.NoFocus)
        btn.setStyleSheet(theme.toolbutton_flat_qss())
        btn.clicked.connect(slot)
        return btn

    def _make_status_readout(self, icon_filename):
        """Lectura de la barra de estado: [icono opcional][valor]. El icono solo
        aparece si existe el PNG en icons/; si no, queda un hueco oculto listo
        para añadirlo en el futuro."""
        box = QWidget()
        lay = QHBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        icon_label = QLabel()
        path = ":/icons/" + icon_filename
        if QFile.exists(path):
            icon_label.setPixmap(QPixmap(path).scaled(14, 14, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            icon_label.hide()
        lay.addWidget(icon_label)
        value_label = QLabel("")
        value_label.setStyleSheet(f"color: {theme.TEXT_BRIGHT};")
        lay.addWidget(value_label)
        return box, icon_label, value_label

    def _build_status_bar(self):
        """Barra de estado con widgets: ayuda contextual a la izquierda; a la
        derecha tamaño, posición del cursor, un hueco, zoom y los controles de
        zoom (ajustar, -, barra, +)."""
        self.status_bar = QStatusBar(self)
        self.status_bar.setSizeGripEnabled(False)
        self.status_bar.setStyleSheet(theme.statusbar_qss())
        self.setStatusBar(self.status_bar)

        # Ayudas por herramienta (gris itálico, como las de selección)
        self._tool_help = {
            "pen": t("help.tool.pen"),
            "pencil": t("help.tool.pencil"),
            "eraser": t("help.tool.eraser"),
            "bucket": t("help.tool.bucket"),
            "eyedropper": t("help.tool.eyedropper"),
            "replace_color": t("help.tool.replace_color"),
            "clone": t("help.tool.clone"),
            "text": t("help.tool.text"),
            "pen_path": t("help.tool.pen_path"),
            "line_curve": t("help.tool.line_curve"),
            "measure": t("help.tool.measure"),
            "airbrush": t("help.tool.airbrush"),
            "gradient": t("help.tool.gradient"),
            "smudge": t("help.tool.smudge"),
            "dodge_burn": t("help.tool.dodge_burn"),
            "sponge": t("help.tool.sponge"),
            "liquify": t("help.tool.liquify"),
            "heal": t("help.tool.heal"),
            "select_rect": t("help.tool.select_rect"),
            "select_ellipse": t("help.tool.select_ellipse"),
            "select_lasso": t("help.tool.select_lasso"),
            "magic_wand": t("help.tool.magic_wand"),
            "move": t("help.tool.move"),
            "hand": t("help.tool.hand"),
            "crop": t("help.tool.crop"),
        }

        # Ayudas específicas de cada forma (herramienta "Formas"). Las claves son
        # los nombres internos ESTABLES de la forma (no se traducen).
        self._shape_help = {
            "Línea Recta": t("help.shape.line"),
            "Rectángulo": t("help.shape.rect"),
            "Elipse": t("help.shape.ellipse"),
        }
        # Claves = valores internos estables de modo de Mover (current_move_mode).
        self._move_help = {
            "selection": t("help.move.selection"),
            "outline": t("help.move.outline"),
            "copy": t("help.move.copy"),
        }

        # IZQUIERDA: ayuda contextual
        help_container = QWidget()
        help_container.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        help_layout = QHBoxLayout(help_container)
        help_layout.setContentsMargins(3, 0, 0, 0)
        help_layout.setSpacing(6)

        self.tool_help_icon = QLabel()
        self.tool_help_icon.setFixedSize(14, 14)
        help_layout.addWidget(self.tool_help_icon)

        # La etiqueta se dimensiona por su CONTENIDO (así la barra de progreso
        # queda pegada detrás del texto), pero con mínimo 0 para que un texto
        # largo no fuerce el ancho mínimo de la ventana (se recorta sin más,
        # que es lo que conseguía la antigua política Ignored).
        self.tool_help_label = QLabel("")
        self.tool_help_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.tool_help_label.setMinimumWidth(0)
        help_layout.addWidget(self.tool_help_label)

        # Barra de progreso de las operaciones de IA: aparece JUSTO DETRÁS del
        # mensaje mientras hay trabajo. En modo "actividad" (rango 0,0) si el
        # efecto no reporta porcentaje; con % real (0..100) si lo reporta
        # (tiles, caras, descargas). Va DENTRO del contenedor de ayuda para no
        # alterar el stretch de la barra de estado.
        self.ai_progress_bar = QProgressBar()
        self.ai_progress_bar.setStyleSheet(theme.progressbar_qss())
        self.ai_progress_bar.setFixedWidth(150)
        # 16 px: el mismo min-height que fija theme.progressbar_qss() (un alto
        # distinto aquí entra en conflicto con el QSS y descoloca la barra).
        self.ai_progress_bar.setFixedHeight(16)
        self.ai_progress_bar.setTextVisible(True)
        self.ai_progress_bar.setVisible(False)
        # Centrada VERTICALMENTE en la barra de estado (sin esto queda caída
        # hacia abajo respecto al texto de ayuda).
        help_layout.addWidget(self.ai_progress_bar, 0, Qt.AlignVCenter)

        # Botón para CANCELAR el efecto de IA en curso (cualquiera): aparece junto a la
        # barra de progreso mientras hay trabajo y lo detiene (token de cancelación; si
        # va por subproceso y no responde pronto, se termina el proceso). Lo muestra/
        # oculta _ai_set_busy junto con la barra.
        self.ai_cancel_btn = QPushButton(t("ai.cancel", default="Cancelar"))
        # Estilo estándar de Imago (borde gris en reposo, azul al pasar el ratón), pero
        # con padding vertical reducido para que quepa compacto en la barra de estado
        # (el padding 5px del original lo haría demasiado alto); el horizontal (14px) da
        # aire al texto. La regla posterior gana sobre el padding de dialog_button_plain_qss.
        self.ai_cancel_btn.setStyleSheet(
            theme.dialog_button_plain_qss() + "\nQPushButton { padding: 2px 14px; }")
        self.ai_cancel_btn.setToolTip(t("ai.cancel.tip",
                                        default="Cancelar la operación de IA en curso"))
        self.ai_cancel_btn.setCursor(Qt.PointingHandCursor)
        self.ai_cancel_btn.setFixedHeight(20)
        self.ai_cancel_btn.setVisible(False)
        self.ai_cancel_btn.clicked.connect(self._cancel_current_status_operation)
        help_layout.addWidget(self.ai_cancel_btn, 0, Qt.AlignVCenter)

        help_layout.addStretch(1)   # absorbe el sobrante a la derecha del par texto+barra

        self.status_bar.addWidget(help_container, 1)

        # DERECHA: lecturas + controles de zoom (un único contenedor)
        right = QWidget()
        rl = QHBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(8)

        self.status_autosave_value = QLabel("")
        self.status_autosave_value.setToolTip(t("status.autosave.pending.tip"))
        rl.addWidget(self.status_autosave_value)
        self.actualizar_estado_autoguardado("pendiente")

        rl.addSpacing(12)

        size_box, self.status_size_icon, self.status_size_value = self._make_status_readout("status_size.png")
        size_box.setToolTip(t("status.tt.size"))
        rl.addWidget(size_box)

        rl.addSpacing(16)  # separación extra entre tamaño y posición del cursor

        cursor_box, self.status_cursor_icon, self.status_cursor_value = self._make_status_readout("status_cursor.png")
        cursor_box.setToolTip(t("status.tt.cursor"))
        rl.addWidget(cursor_box)

        rl.addSpacing(28)  # hueco generoso

        zoom_box, self.status_zoom_icon, self.status_zoom_value = self._make_status_readout("status_zoom.png")
        zoom_box.setToolTip(t("status.tt.zoom"))
        rl.addWidget(zoom_box)

        self.btn_zoom_fit = self._make_zoom_button(
            ":/icons/zoom_fit.png", t("zoom.fit"), t("zoom.fit_tt"), self.fit_canvas_to_screen)
        rl.addWidget(self.btn_zoom_fit)

        self.btn_zoom_out = self._make_zoom_button(
            ":/icons/zoom_out.png", "−", t("zoom.out_tt"), self.zoom_out)
        rl.addWidget(self.btn_zoom_out)

        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setRange(0, 100)
        self.zoom_slider.setValue(50)          # centro = 100%
        self.zoom_slider.setFixedWidth(130)
        self.zoom_slider.setFocusPolicy(Qt.NoFocus)
        self.zoom_slider.setToolTip(t("status.tt.zoom_slider"))
        self.zoom_slider.setStyleSheet(theme.slider_qss())
        self.zoom_slider.valueChanged.connect(self.on_zoom_slider_changed)
        rl.addWidget(self.zoom_slider)

        self.btn_zoom_in = self._make_zoom_button(
            ":/icons/zoom_in.png", "+", t("zoom.in_tt"), self.zoom_in)
        rl.addWidget(self.btn_zoom_in)

        self.status_bar.addPermanentWidget(right)

    def actualizar_estado_autoguardado(self, estado, hora=None):
        """Refleja eventos del autoguardado sin temporizadores ni sondeos.

        ``guardado`` solo llega después de publicar atómicamente el manifiesto
        de recuperación; por eso la hora visible siempre representa una copia
        completa y verificable.
        """
        label = getattr(self, "status_autosave_value", None)
        if label is None:
            return
        if estado == "guardando":
            texto = t("status.autosave.saving")
            tooltip = t("status.autosave.saving.tip")
            color = theme.WARNING
        elif estado == "guardado" and hora:
            texto = t("status.autosave.saved", time=hora)
            tooltip = t("status.autosave.saved.tip", time=hora)
            color = theme.TEXT_BRIGHT
        elif estado == "error":
            texto = t("status.autosave.error")
            tooltip = t("status.autosave.error.tip")
            color = theme.DANGER
        else:
            texto = t("status.autosave.pending")
            tooltip = t("status.autosave.pending.tip")
            color = theme.TEXT_DIM
        label.setText(texto)
        label.setToolTip(tooltip)
        label.setStyleSheet(f"color: {color};")

    def _cancel_current_status_operation(self):
        """El botón compartido cancela la operación que posee el indicador."""
        if getattr(self, "_ai_busy", False):
            self._ai_cancel_current()
        elif getattr(self, "_io_handle", None) is not None:
            self._io_cancel_current()

    def _refresh_tool_help(self):
        """Muestra la ayuda de la herramienta activa. Para 'Formas' usa la ayuda
        de la forma concreta (línea / rectángulo / elipse)."""
        if not hasattr(self, 'tool_help_label'):
            return
        name = getattr(self, 'current_tool_name', None)
        
        icon_path = f":/icons/{name}.png"
        if QFile.exists(icon_path):
            self.tool_help_icon.setPixmap(theme.tintar_pixmap(QPixmap(icon_path)).scaled(14, 14, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self.tool_help_icon.show()
        else:
            self.tool_help_icon.hide()

        if name == "shapes":
            text = t("help.tool.shapes")
        elif name == "move":
            mode = getattr(self, 'current_move_mode', "selection")
            text = self._move_help.get(mode, "")
        else:
            text = self._tool_help.get(name, "")
        self.tool_help_label.setText(text)

    def _update_status_readouts(self):
        """Refresca tamaño real y zoom (la posición del cursor se actualiza al
        mover el ratón)."""
        if not hasattr(self, 'status_size_value'):
            return
        canvas = self.get_current_canvas()
        if not canvas:
            self.status_size_value.setText("")
            self.status_zoom_value.setText("")
            self.status_cursor_value.setText("")
            return
        self.status_size_value.setText(f"{canvas.base_width} x {canvas.base_height}")
        self.status_zoom_value.setText(f"{int(canvas.zoom_factor * 100)}%")

    def update_cursor_position(self, point):
        """Actualiza la posición del cursor. Si point es None (el cursor sale del
        lienzo) se conserva la última lectura para evitar el parpadeo; se vuelve
        a actualizar en cuanto el cursor regresa."""
        if not hasattr(self, 'status_cursor_value'):
            return
        if point is None:
            return  # cursor fuera: mantener la última posición mostrada
        self.status_cursor_value.setText(f"{point.x()}, {point.y()}")

    def _apply_zoom(self, new_zoom):
        """Aplica un zoom concreto al lienzo activo (mismo flujo que la rueda:
        tamaño de vista, márgenes de la herramienta y repintado) y refresca
        barra de estado, cursor y la barra deslizante de zoom."""
        canvas = self.get_current_canvas()
        if not canvas:
            return
        if hasattr(canvas, 'apply_zoom_anchored'):
            # Ancla en el CENTRO del viewport (botones, menú y barra deslizante)
            canvas.apply_zoom_anchored(new_zoom)
            self.update_status_bar_zoom()
            return
        canvas.zoom_factor = max(0.1, min(new_zoom, 64.0))
        if hasattr(canvas, '_apply_view_size'):
            canvas._apply_view_size()
        else:
            canvas.setFixedSize(int(canvas.base_width * canvas.zoom_factor),
                                int(canvas.base_height * canvas.zoom_factor))
        if hasattr(canvas.current_tool, '_update_view_margins'):
            canvas.current_tool._update_view_margins()
        canvas.update()
        self.update_status_bar_zoom()

    def zoom_in(self):
        canvas = self.get_current_canvas()
        if canvas:
            self._apply_zoom(canvas.zoom_factor * 1.15)

    def zoom_out(self):
        canvas = self.get_current_canvas()
        if canvas:
            self._apply_zoom(canvas.zoom_factor / 1.15)

    def on_zoom_slider_changed(self, value):
        """Arrastrar la barra cambia el zoom. Mapeo LOGARÍTMICO simétrico:
        el centro (50) es 100%, y a cada lado va de 10% a 1000%."""
        ZMIN, ZMAX = 0.1, 10.0
        z = ZMIN * (ZMAX / ZMIN) ** (value / 100.0)
        self._zoom_from_slider = True
        self._apply_zoom(z)
        self._zoom_from_slider = False

    def _sync_zoom_slider(self):
        """Coloca el tirador según el zoom actual (no durante el propio arrastre,
        para que no 'pelee' con el ratón)."""
        if getattr(self, '_zoom_from_slider', False):
            return
        if not hasattr(self, 'zoom_slider'):
            return
        canvas = self.get_current_canvas()
        if not canvas:
            return
        import math
        ZMIN, ZMAX = 0.1, 10.0
        z = max(ZMIN, min(canvas.zoom_factor, ZMAX))
        value = round(100 * math.log(z / ZMIN) / math.log(ZMAX / ZMIN))
        value = max(0, min(100, value))
        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(value)
        self.zoom_slider.blockSignals(False)

    def _compute_fit_zoom(self):
        """Zoom con el que la imagen 'ajusta a la ventana', o None si no se
        puede calcular (sin lienzo o área todavía sin tamaño)."""
        scroll_area = self.get_current_scroll()
        canvas = self.get_current_canvas()
        if not scroll_area or not canvas:
            return None
        width, height = canvas.base_width, canvas.base_height
        max_width, max_height = scroll_area.width() - 30, scroll_area.height() - 30
        if max_width <= 0 or max_height <= 0:
            return None
        optimal = 1.0
        if width > max_width or height > max_height:
            optimal = max(0.1, min(max_width / width, max_height / height))
        return optimal

    def _update_fit_button_state(self):
        """Apaga el botón y el menú 'Ajustar a la ventana' cuando la imagen YA
        está ajustada; los ilumina en cuanto el zoom deja de coincidir con el de
        ajuste. El estado apagado reutiliza el icono atenuado de crear_icono."""
        optimal = self._compute_fit_zoom()
        if optimal is None:
            enabled = False  # sin lienzo: nada que ajustar
        else:
            canvas = self.get_current_canvas()
            enabled = abs(canvas.zoom_factor - optimal) >= 0.005
        if hasattr(self, 'btn_zoom_fit'):
            self.btn_zoom_fit.setEnabled(enabled)
        if hasattr(self, 'zoom_fit_action'):
            self.zoom_fit_action.setEnabled(enabled)

    def actual_size(self):
        """Tamaño real: zoom al 100% (1 px de imagen = 1 px de pantalla)."""
        self._apply_zoom(1.0)

    def fit_canvas_to_screen(self):
        optimal_zoom = self._compute_fit_zoom()
        if optimal_zoom is None:
            return
        canvas = self.get_current_canvas()
        width, height = canvas.base_width, canvas.base_height
        canvas.zoom_factor = optimal_zoom
        canvas._last_fit_zoom = optimal_zoom
        canvas.setFixedSize(int(width * optimal_zoom), int(height * optimal_zoom))
        canvas.update()
        self._update_status_readouts()
        self.update_canvas_cursor()
        self._sync_zoom_slider()
        self._update_fit_button_state()

    def _fit_if_zoom_mode(self):
        """Re-ajusta solo si el usuario no ha cambiado el zoom manualmente:
        si el zoom actual coincide con el último zoom de ajuste, seguimos en
        modo 'ajustar a ventana' y hay que recalcular al nuevo tamaño."""
        canvas = self.get_current_canvas()
        if canvas is None:
            self.fit_canvas_to_screen()
            return
        last = getattr(canvas, '_last_fit_zoom', None)
        if last is None or abs(canvas.zoom_factor - last) < 0.005:
            self.fit_canvas_to_screen()

    def _restore_or_fit_canvas_zoom(self, canvas):
        """Al cambiar de pestaña: si el lienzo YA se mostró antes, conserva su
        zoom (no reajusta); si es la primera vez que se muestra, lo ajusta a la
        ventana. Así un lienzo al 600% sigue al 600% al volver a su pestaña."""
        if canvas is None:
            return
        if getattr(canvas, '_zoom_initialized', False):
            # Restaurar el zoom guardado del propio lienzo (reaplicar su tamaño;
            # si ya lo tiene, es no-op y conserva también la posición de scroll).
            z = getattr(canvas, 'zoom_factor', 1.0)
            canvas.setFixedSize(int(canvas.base_width * z), int(canvas.base_height * z))
            canvas.update()
            self._update_status_readouts()
            self.update_canvas_cursor()
            self._sync_zoom_slider()
            self._update_fit_button_state()
        else:
            # Primera vez que se muestra este lienzo: ajustar a la ventana.
            self.fit_canvas_to_screen()
            canvas._zoom_initialized = True

    def update_status_bar_zoom(self):
        """Actualiza tamaño y porcentaje de zoom en la barra de estado."""
        canvas = self.get_current_canvas()
        if canvas:
            self._update_status_readouts()
            self.update_canvas_cursor()
            self._sync_zoom_slider()
            self._update_fit_button_state()

    def update_tab_tooltip(self, index, thumb=None):
        """Actualiza un tooltip reutilizando la caché reducida de su pestaña."""
        if not 0 <= index < self.tabs.count():
            return
        marker = self.tabs.widget(index)
        if marker is None or not hasattr(marker, 'canvas'):
            return
        canvas = marker.canvas
        if thumb is None and hasattr(self, "thumbnail_bar"):
            thumb = self.thumbnail_bar.preview_for_canvas(canvas)
        if thumb is None:
            # Respaldo para llamadas anteriores a la construcción de la barra.
            thumb = _canvas_thumb_pixmap(canvas, 150, 110)
        if thumb is None:
            return
        preview_img = thumb.toImage()

        from PySide6.QtCore import QByteArray, QBuffer, QIODevice
        ba = QByteArray()
        buffer = QBuffer(ba)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        preview_img.save(buffer, "PNG")
        b64_data = ba.toBase64().data().decode("utf-8")

        nombre_archivo = self.tabs.tabText(index)
        html_tooltip = f"""
                <div style='background-color: {theme.BG_WINDOW}; color: {theme.TEXT}; padding: 6px; border: 1px solid {theme.BORDER_SOFT}; border-radius: 4px;'>
                    <b style='font-size: 11px; color: {theme.ACCENT};'>{nombre_archivo}</b><br/>
                    <div style='margin-top: 4px; border-top: 1px solid {theme.BORDER_SOFT}; padding-top: 4px;'>
                        <img src='data:image/png;base64,{b64_data}' />
                    </div>
                </div>
                """
        self.tabs.setTabToolTip(index, html_tooltip)

    def update_tab_tooltips(self):
        """Sincroniza los tooltips sin volver a componer los documentos."""
        for i in range(self.tabs.count()):
            self.update_tab_tooltip(i)

