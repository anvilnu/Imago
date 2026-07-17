# menu_ia.py
"""Acciones del menú IA de la ventana principal (mixin de MainWindow).

Extraído de main.py TAL CUAL (sin cambios de comportamiento) para aligerarlo:
aquí viven todos los handlers ai_* del menú IA y sus auxiliares _ai_*/_cv_*
(prechequeos, descarga de modelos, máscaras/profundidad compartidas, commit
de píxeles al historial, indicador de ocupado...). MainWindow hereda de
AccionesMenuIA, así que los menús siguen conectando con self.ai_* igual que
antes. El trabajo pesado va SIEMPRE por InferenceRunner (ai/runner.py)."""
import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPainter

from i18n import t


class AccionesMenuIA:
    def open_ai_models(self):
        from ai.model_manager import ModelManagerDialog
        ModelManagerDialog(self).exec()

    # ------------------------------------------------------------------ IA
    def _ai_get_runner(self):
        """Runner de inferencia compartido (se crea la primera vez, en el hilo GUI)."""
        if getattr(self, "_ai_runner", None) is None:
            from ai.runner import InferenceRunner
            self._ai_runner = InferenceRunner(self)
        return self._ai_runner

    def _ai_status(self, text, timeout=0):
        """Muestra un estado de IA en la barra SIN usar showMessage(): escribe en la
        etiqueta de ayuda de herramienta. Motivo: showMessage() oculta ese
        contenedor (que lleva el stretch de la barra) y descuadra las lecturas de
        la derecha (tamaño/cursor/zoom). Con timeout>0, restaura la ayuda después."""
        if hasattr(self, "tool_help_label"):
            self.tool_help_label.setText(text)
        # Junto al texto, el icono propio del efecto de IA en curso (no el del
        # pincel): se recuerda en self._ai_active_icon al lanzar la acción.
        self._ai_set_status_icon()
        if timeout > 0:
            QTimer.singleShot(timeout, self._ai_status_clear)

    def _ai_set_status_icon(self):
        """Pone en la barra de estado el icono del efecto de IA en curso
        (self._ai_active_icon), en lugar del icono de la herramienta activa."""
        icon = getattr(self, "_ai_active_icon", None)
        if not icon or not hasattr(self, "tool_help_icon"):
            return
        from PySide6.QtGui import QPixmap
        from PySide6.QtCore import QFile
        import theme
        ruta = ":/icons/" + icon
        if QFile.exists(ruta):
            self.tool_help_icon.setPixmap(theme.tintar_pixmap(QPixmap(ruta)).scaled(
                14, 14, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self.tool_help_icon.show()

    def _ai_tag(self, cmd):
        """Marca un comando de deshacer con el icono del efecto de IA en curso
        (history_icon) para que el panel de Historial muestre el icono propio del
        efecto, no el del pincel. Devuelve el mismo comando (encadenable en push)."""
        icon = getattr(self, "_ai_active_icon", None)
        if icon:
            cmd.history_icon = icon
        return cmd

    def _ai_status_clear(self):
        """Restaura la ayuda de la herramienta activa tras un estado de IA."""
        if hasattr(self, "_refresh_tool_help"):
            self._refresh_tool_help()

    def _ai_set_busy(self, busy):
        """Deshabilita las acciones de IA mientras hay un trabajo en curso y
        muestra el cursor de ESPERA (reloj) sobre toda la app. Idempotente: el
        override del cursor se pone/quita UNA sola vez aunque se llame varias
        veces con el mismo estado (evita dejarlo pegado en cadenas descarga→
        inferencia o en caminos de error/cancelación)."""
        self._ai_busy = busy
        if busy:
            for act in getattr(self, "_ai_actions", []):
                act.setEnabled(False)
        elif hasattr(self, "update_ai_menu_state"):
            # Al terminar, restaurar respetando el CONTEXTO (capa activa; el
            # panorama no requiere lienzo), no reactivar todo a ciegas.
            self.update_ai_menu_state()
        else:
            for act in getattr(self, "_ai_actions", []):
                act.setEnabled(True)
        from PySide6.QtWidgets import QApplication
        active = getattr(self, "_ai_cursor_active", False)
        if busy and not active:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            self._ai_cursor_active = True
        elif not busy and active:
            QApplication.restoreOverrideCursor()
            self._ai_cursor_active = False
        # Barra de progreso de la barra de estado: al empezar, en modo "actividad"
        # (rango 0,0 = animación continua); si el efecto reporta %, _ai_progress la
        # pasa a 0..100. Al terminar se oculta.
        bar = getattr(self, "ai_progress_bar", None)
        if bar is not None:
            if busy:
                bar.setRange(0, 0)
                bar.setVisible(True)
            else:
                bar.setVisible(False)
                bar.setRange(0, 100)
                bar.setValue(0)
        # Botón de cancelar: visible solo mientras hay trabajo de IA (junto a la barra).
        btn = getattr(self, "ai_cancel_btn", None)
        if btn is not None:
            btn.setVisible(bool(busy))
        if not busy:
            self._ai_notify_gpu_fallback()

    def _ai_notify_gpu_fallback(self):
        """Si una operacion se cayo en la GPU y se reintento en CPU (ver ai/subproc.py),
        avisa al usuario UNA vez por sesion. Se llama al terminar cada trabajo (hilo
        GUI). El aviso se difiere con un timer 0 para que salga tras verse el resultado."""
        from ai.subproc import pop_gpu_fallback
        if pop_gpu_fallback() is None:
            return
        if getattr(self, "_ai_gpu_fallback_warned", False):
            return
        self._ai_gpu_fallback_warned = True
        QTimer.singleShot(0, self._ai_show_gpu_fallback)

    def _ai_show_gpu_fallback(self):
        from widgets.custom_titlebar import imago_warning
        imago_warning(self, t("ai.gpu_fallback.title"), t("ai.gpu_fallback.msg"))

    def _ai_cancel_current(self):
        """Cancela el trabajo de IA en curso (cualquiera: efecto o descarga). El token
        hace que el trabajo salga cuanto antes (entre tiles/pasos); si va por subproceso
        y no responde en unos segundos, ai/subproc.py termina el proceso. Como una tarea
        cancelada NO invoca on_done/on_error, aquí restauramos la UI (busy off) a mano."""
        h = getattr(self, "_ai_handle", None)
        if h is None:
            return
        h.cancel()
        self._ai_handle = None
        self._ai_target_canvas = None
        self._ai_set_busy(False)
        self._ai_status(t("ai.cancelled"), 3000)

    def _ai_cancel_for_canvas(self, canvas):
        """Cancela el trabajo en curso si su documento acaba de cerrarse."""
        if getattr(self, "_ai_handle", None) is not None and \
                getattr(self, "_ai_target_canvas", None) is canvas:
            self._ai_cancel_current()

    def _ai_progress(self, pct):
        """Progreso (0..100) de la operación de IA en curso: pasa la barra de la
        barra de estado del modo 'actividad' al porcentaje real."""
        bar = getattr(self, "ai_progress_bar", None)
        if bar is not None:
            if bar.maximum() == 0:          # venía en modo actividad
                bar.setRange(0, 100)
            bar.setValue(int(pct))

    def _ai_precheck(self, need_onnx=True):
        """Comprobaciones comunes a todas las funciones de IA. Devuelve
        (canvas, idx) si se puede continuar, o None (ya se avisó al usuario).
        Las funciones de visión clásica (OpenCV) pasan need_onnx=False."""
        from widgets.custom_titlebar import imago_warning
        if getattr(self, "_ai_handle", None) is not None:
            imago_warning(self, t("ai.bg.title"), t("ai.bg.busy"))
            return None
        canvas = self.get_current_canvas()
        if canvas is None:
            return None
        self._ai_target_canvas = canvas
        idx = canvas.active_layer_index
        if idx < 0 or idx >= len(canvas.layers):
            imago_warning(self, t("ai.bg.title"), t("ai.bg.no_layer"))
            return None
        if getattr(canvas.layers[idx], "is_text", False):
            imago_warning(self, t("ai.bg.title"), t("ai.bg.is_text"))
            return None
        if need_onnx:
            from ai.runner import onnx_available
            if not onnx_available():
                imago_warning(self, t("ai.bg.title"), t("ai.bg.no_onnx"))
                return None
        return canvas, idx

    def _cv_precheck(self):
        """Precheck de las funciones CV: lo común + OpenCV disponible."""
        pc = self._ai_precheck(need_onnx=False)
        if not pc:
            return None
        from ai.cv_effects import cv_available
        if not cv_available():
            from widgets.custom_titlebar import imago_warning
            imago_warning(self, t("ai.bg.title"), t("ai.cv.no_opencv"))
            return None
        return pc

    def _ai_indice_destino(self, destino, exigir_activo=True):
        """Índice actual de una capa si identidad, revisión y documento coinciden."""
        index = destino.indice_actual(
            self, exigir_revision=True, exigir_activo=exigir_activo)
        if index is None:
            self._ai_status(t("ai.target_changed"), 6000)
        return index

    def _ai_with_subject_mask(self, canvas, idx, then, destino=None):
        """Asegura el modelo de segmentación (descarga bajo demanda) y obtiene la
        máscara del sujeto CACHEADA por capa (se recalcula solo si la capa cambió).
        Llama then(mask, destino) —array uint8 (H, W) + identidad estable— en
        el hilo GUI."""
        from ai import model_manager as mm
        from ai.bg_removal import DEFAULT_MODEL_KEY
        from models.destino_edicion import DestinoCapa

        destino = destino or DestinoCapa(canvas, idx)
        layer = destino.layer
        cached = getattr(layer, "_ai_mask", None)
        if cached is not None and getattr(layer, "_ai_mask_key", None) == layer.image.cacheKey():
            then(cached, destino)   # cache válida: sin inferencia
            return

        model = mm.get_model(DEFAULT_MODEL_KEY)
        self._ai_ensure_model(
            model, lambda: self._ai_compute_mask(destino, model, then))

    def _ai_ensure_model(self, model, cont):
        """Asegura que `model` esté descargado (bajo demanda: pregunta y descarga
        la primera vez) y, cuando esté disponible, llama cont(). Común a todas las
        funciones de IA."""
        from ai import model_manager as mm
        from widgets.custom_titlebar import imago_question, imago_warning
        from PySide6.QtWidgets import QMessageBox
        if mm.is_installed(model):
            cont()
            return
        if not model.configurado:
            imago_warning(self, t("ai.bg.title"), t("ai.models.pending"))
            return
        resp = imago_question(
            self, t("ai.bg.title"),
            t("ai.bg.need_model", name=model.nombre,
              size=mm.format_size(model.size_bytes)))
        if resp != QMessageBox.Yes:
            return
        self._ai_download_then(model, cont)

    def _ai_download_then(self, model, cont):
        """Descarga `model` bajo demanda con progreso en la barra de estado y, al
        terminar bien, llama cont()."""
        from ai import model_manager as mm
        from widgets.custom_titlebar import imago_warning
        runner = self._ai_get_runner()
        self._ai_set_busy(True)
        self._ai_status(t("ai.bg.downloading", pct=0))

        def done(path):
            self._ai_handle = None
            self._ai_set_busy(False)
            if path is None:                       # cancelada
                self._ai_status_clear()
                return
            cont()

        def err(msg):
            self._ai_handle = None
            self._ai_set_busy(False)
            self._ai_status_clear()
            imago_warning(self, t("ai.bg.title"), t("ai.bg.dl_error", err=msg))

        def progress(p):
            self._ai_status(t("ai.bg.downloading", pct=p))
            self._ai_progress(p)

        self._ai_handle = runner.submit(
            mm.make_download_task(model), on_done=done, on_error=err,
            on_progress=progress)

    def _ai_compute_mask(self, destino, model, then):
        """Ejecuta la segmentación en un hilo secundario, cachea la máscara en la
        capa y llama then(mask) en el hilo GUI."""
        from ai import model_manager as mm, imgproc, bg_removal, subproc
        from widgets.custom_titlebar import imago_warning
        runner = self._ai_get_runner()
        idx = self._ai_indice_destino(destino)
        if idx is None:
            return
        canvas = destino.canvas
        layer = destino.layer
        cache_key = layer.image.cacheKey()
        rgb = imgproc.qimage_to_array(layer.image)[:, :, :3].copy()
        path = mm.path_for(model)
        key = model.key

        self._ai_set_busy(True)
        self._ai_status(t("ai.bg.working"))

        def work(report, token):
            mask = subproc.run_model("ai.bg_removal", "compute_alpha_mask",
                                     rgb, path, key, report=report, token=token)
            return None if token.cancelled else mask

        def done(mask):
            self._ai_handle = None
            self._ai_set_busy(False)
            if mask is None:
                self._ai_status_clear()
                return
            current = self._ai_indice_destino(destino)
            if current is None:
                return
            layer._ai_mask = mask               # cache por capa
            layer._ai_mask_key = cache_key
            then(mask, destino)

        def err(msg):
            self._ai_handle = None
            self._ai_set_busy(False)
            self._ai_status_clear()
            imago_warning(self, t("ai.bg.title"), t("ai.bg.error", err=msg))

        self._ai_handle = runner.submit(work, on_done=done, on_error=err)

    def _ai_commit_pixels(self, destino, new_rgba, old_image, hist_key,
                          done_key="ai.bg.done"):
        """Empuja el resultado (array RGBA) como un PaintCommand: un solo paso de
        deshacer sobre la capa idx. `done_key` es el mensaje de la barra de estado
        al terminar (propio de cada efecto: no todos son 'Fondo eliminado')."""
        from ai import imgproc
        from tools.commands import PaintCommand
        idx = self._ai_indice_destino(destino)
        if idx is None:
            return False
        canvas = destino.canvas
        W, H = old_image.width(), old_image.height()
        new_q = imgproc.array_to_qimage(new_rgba, W, H).convertToFormat(
            QImage.Format_ARGB32)
        canvas.undo_stack.push(self._ai_tag(PaintCommand(
            canvas, idx, old_image, new_q, description=t(hist_key), tool_id="ai_bg")))
        self._ai_status(t(done_key), 4000)
        return True

    # -- funciones concretas ---------------------------------------------
    def ai_remove_background(self):
        """Elimina el fondo de la capa activa escribiendo su canal alfa."""
        pc = self._ai_precheck()
        if not pc:
            return
        canvas, idx = pc

        def apply(mask, destino):
            from ai import imgproc, bg_removal
            old_image = destino.layer.image.copy()
            rgba = imgproc.qimage_to_array(old_image)
            cut = bg_removal.apply_alpha_mask(rgba, mask)
            self._ai_commit_pixels(destino, cut, old_image, "hist.remove_bg")

        self._ai_with_subject_mask(canvas, idx, apply)

    def ai_select_object(self):
        """Segmenta la imagen (DeepLab) y deja elegir qué clase(s) seleccionar
        (persona, coche, perro...), creando una selección con esos píxeles."""
        pc = self._ai_precheck()
        if not pc:
            return
        canvas, idx = pc
        from models.destino_edicion import DestinoCapa
        destino = DestinoCapa(canvas, idx)
        from ai import model_manager as mm
        model = mm.get_model("deeplab")
        self._ai_ensure_model(model, lambda: self._ai_run_segment(destino, model))

    def _ai_run_segment(self, destino, model):
        import numpy as np
        from ai import model_manager as mm, imgproc, segment, subproc
        from widgets.custom_titlebar import imago_warning, imago_information
        runner = self._ai_get_runner()
        idx = self._ai_indice_destino(destino)
        if idx is None:
            return
        canvas = destino.canvas
        rgb = imgproc.qimage_to_array(destino.layer.image)[:, :, :3].copy()
        path = mm.path_for(model)

        self._ai_set_busy(True)
        self._ai_status(t("ai.seg.working"))

        def work(report, token):
            label = subproc.run_model("ai.segment", "segment",
                                      rgb, path, report=report, token=token)
            return None if token.cancelled else label

        def done(label):
            self._ai_handle = None
            self._ai_set_busy(False)
            if label is None:
                self._ai_status_clear()
                return
            if self._ai_indice_destino(destino) is None:
                return
            self._ai_status_clear()
            classes, counts = np.unique(label, return_counts=True)
            total = float(label.size)
            present = sorted(((int(c), int(n)) for c, n in zip(classes, counts)
                              if n / total > 0.005), key=lambda t: -t[1])
            if not present:
                imago_information(self, t("ai.seg.title"), t("ai.seg.none"))
                return
            items = [(f"{segment.class_name(c)}  ({int(100 * n / total)}%)", c)
                     for c, n in present]
            from new_dialog import SegmentPickerDialog
            from PySide6.QtWidgets import QDialog
            dlg = SegmentPickerDialog(items, self)
            if dlg.exec() != QDialog.Accepted:
                return
            sel = dlg.get_selected()
            if not sel:
                return
            mask = (np.isin(label, sel).astype(np.uint8)) * 255
            from ai import bg_effects
            from tools.commands import SelectionChangeCommand
            path_sel = bg_effects.subject_path(mask)
            if path_sel is None:
                imago_information(self, t("ai.seg.title"), t("ai.seg.none"))
                return
            canvas.undo_stack.push(self._ai_tag(SelectionChangeCommand(
                canvas, canvas.selection, path_sel,
                t("hist.select_object"), tool_id="magic_wand")))
            canvas.update()
            self._ai_status(t("ai.seg.done"), 4000)

        def err(msg):
            self._ai_handle = None
            self._ai_set_busy(False)
            self._ai_status_clear()
            imago_warning(self, t("ai.seg.title"), t("ai.bg.error", err=msg))

        self._ai_handle = runner.submit(work, on_done=done, on_error=err)

    def ai_select_subject(self):
        """Convierte la máscara del sujeto en una SELECCIÓN, para aplicar cualquier
        ajuste/efecto confinado al sujeto (o al fondo, invirtiéndola con Ctrl+I)."""
        pc = self._ai_precheck()
        if not pc:
            return
        canvas, idx = pc

        def apply(mask, destino):
            from ai import bg_effects
            from tools.commands import SelectionChangeCommand
            from widgets.custom_titlebar import imago_warning
            path = bg_effects.subject_path(mask)
            if path is None:
                imago_warning(self, t("ai.bg.title"), t("ai.bg.empty_mask"))
                return
            canvas.undo_stack.push(self._ai_tag(SelectionChangeCommand(
                canvas, canvas.selection, path, t("hist.select_subject"),
                tool_id="magic_wand")))
            canvas.update()
            self._ai_status(t("ai.bg.selected"), 4000)

        self._ai_with_subject_mask(canvas, idx, apply)

    def ai_blur_background(self):
        """Desenfoca el fondo (modo retrato) dejando el sujeto nítido. Abre un
        PANEL OVERLAY con preview en vivo (no un diálogo modal: así no atenúa la
        ventana en KDE/Wayland)."""
        pc = self._ai_precheck()
        if not pc:
            return
        canvas, idx = pc

        def apply(mask, destino):
            from ai.effect_panels import AIBackgroundBlurPanel
            self._open_ai_overlay(self._ai_tag(
                AIBackgroundBlurPanel(self, mask, destino=destino)))

        self._ai_with_subject_mask(canvas, idx, apply)

    def ai_color_pop(self):
        """Desatura el fondo (realce de color): el sujeto mantiene su color."""
        pc = self._ai_precheck()
        if not pc:
            return
        canvas, idx = pc

        def apply(mask, destino):
            from ai import imgproc, bg_effects
            old_image = destino.layer.image.copy()
            rgba = imgproc.qimage_to_array(old_image)
            out = bg_effects.color_pop(rgba, mask)
            self._ai_commit_pixels(destino, out, old_image, "hist.color_pop",
                                   done_key="ai.colorpop.done")

        self._ai_with_subject_mask(canvas, idx, apply)

    def ai_replace_background_color(self):
        """Sustituye el fondo por un color liso."""
        pc = self._ai_precheck()
        if not pc:
            return
        canvas, idx = pc
        from widgets.colors_panel import imago_pick_color
        from PySide6.QtGui import QColor
        from models.destino_edicion import DestinoCapa
        destino_inicial = DestinoCapa(canvas, idx)

        # El selector es un overlay hijo del lienzo (Wayland-safe): al Aceptar un
        # color, se ejecuta la sustitucion de fondo (patron por callback).
        def _picked(color):
            rgb = (color.red(), color.green(), color.blue())

            def apply(mask, destino):
                from ai import imgproc, bg_effects
                old_image = destino.layer.image.copy()
                rgba = imgproc.qimage_to_array(old_image)
                out = bg_effects.replace_background_solid(rgba, mask, rgb)
                self._ai_commit_pixels(destino, out, old_image, "hist.replace_bg",
                                       done_key="ai.replacebg.done")

            if self._ai_indice_destino(destino_inicial) is None:
                return
            self._ai_with_subject_mask(
                canvas, idx, apply, destino=destino_inicial)

        imago_pick_color(QColor(255, 255, 255), self,
                         t("ai.bg.pick_color", default="Color de fondo"),
                         on_accept=_picked)

    def ai_replace_background_image(self):
        """Sustituye el fondo por una imagen (escalada al tamaño del lienzo)."""
        pc = self._ai_precheck()
        if not pc:
            return
        canvas, idx = pc
        from PySide6.QtWidgets import QFileDialog
        from widgets.custom_titlebar import imago_warning
        fname, _ = QFileDialog.getOpenFileName(
            self, t("ai.bg.pick_image", default="Imagen de fondo"), "",
            "Imagenes (*.png *.jpg *.jpeg *.bmp *.webp)")
        if not fname:
            return
        bg_img = QImage(fname)
        if bg_img.isNull():
            imago_warning(self, t("ai.bg.title"), t("ai.bg.bad_image"))
            return

        def apply(mask, destino):
            from ai import imgproc, bg_effects
            from PySide6.QtCore import Qt as _Qt
            old_image = destino.layer.image.copy()
            W, H = old_image.width(), old_image.height()
            scaled = bg_img.scaled(W, H, _Qt.IgnoreAspectRatio, _Qt.SmoothTransformation)
            bg_rgb = imgproc.qimage_to_array(scaled)[:, :, :3].copy()
            rgba = imgproc.qimage_to_array(old_image)
            out = bg_effects.replace_background_image(rgba, mask, bg_rgb)
            self._ai_commit_pixels(destino, out, old_image, "hist.replace_bg",
                                   done_key="ai.replacebg.done")

        self._ai_with_subject_mask(canvas, idx, apply)

    def ai_inpaint_selection(self):
        """Borra el contenido de la SELECCIÓN reconstruyéndolo con LaMa (relleno
        inteligente a partir del contexto). El usuario marca la zona con cualquier
        herramienta de selección (lazo, varita, rectángulo...)."""
        pc = self._ai_precheck()
        if not pc:
            return
        canvas, idx = pc
        from widgets.custom_titlebar import imago_warning
        if canvas.selection is None or canvas.selection.isEmpty():
            imago_warning(self, t("ai.inpaint.title"), t("ai.inpaint.no_selection"))
            return
        from ai import model_manager as mm
        from models.destino_edicion import DestinoCapa
        destino = DestinoCapa(canvas, idx)
        model = mm.get_model("lama")
        self._ai_ensure_model(model, lambda: self._ai_run_inpaint(destino, model))

    def _ai_run_inpaint(self, destino, model):
        import numpy as np
        from ai import model_manager as mm, imgproc, inpaint, subproc
        from widgets.custom_titlebar import imago_warning
        runner = self._ai_get_runner()
        idx = self._ai_indice_destino(destino)
        if idx is None:
            return
        canvas = destino.canvas
        old_image = destino.layer.image.copy()
        rgba = imgproc.qimage_to_array(old_image)
        rgb = rgba[:, :, :3].copy()
        mask = (canvas._selection_mask() * 255).astype(np.uint8)   # 255 = borrar
        path = mm.path_for(model)

        self._ai_set_busy(True)
        self._ai_status(t("ai.inpaint.working"))

        def work(report, token):
            out = subproc.run_model("ai.inpaint", "inpaint",
                                    rgb, mask, path, report=report, token=token)
            return None if token.cancelled else out

        def done(out_rgb):
            self._ai_handle = None
            self._ai_set_busy(False)
            if out_rgb is None:
                self._ai_status_clear()
                return
            if self._ai_indice_destino(destino) is None:
                return
            new_rgba = rgba.copy()
            new_rgba[:, :, :3] = out_rgb            # conserva el alfa original
            # La selección ya cumplió su papel (era la máscara del borrado): se descarta
            # para no dejar la marquesina activa sobre el hueco. Se hace ANTES del commit
            # de píxeles para que el primer deshacer restaure el objeto y el segundo la
            # selección (ambos pasos son deshacibles).
            canvas.clear_selection()
            self._ai_commit_pixels(destino, new_rgba, old_image, "hist.inpaint",
                                   done_key="ai.inpaint.done")

        def err(msg):
            self._ai_handle = None
            self._ai_set_busy(False)
            self._ai_status_clear()
            imago_warning(self, t("ai.inpaint.title"), t("ai.bg.error", err=msg))

        self._ai_handle = runner.submit(work, on_done=done, on_error=err)

    def ai_colorize(self):
        """Coloriza la capa activa (foto en blanco y negro) con DDColor."""
        pc = self._ai_precheck()
        if not pc:
            return
        canvas, idx = pc
        from ai import model_manager as mm
        from models.destino_edicion import DestinoCapa
        destino = DestinoCapa(canvas, idx)
        model = mm.get_model("ddcolor")
        self._ai_ensure_model(model, lambda: self._ai_run_colorize(destino, model))

    def _ai_run_colorize(self, destino, model):
        from ai import model_manager as mm, imgproc, colorize, subproc
        from widgets.custom_titlebar import imago_warning
        runner = self._ai_get_runner()
        if self._ai_indice_destino(destino) is None:
            return
        old_image = destino.layer.image.copy()
        rgba = imgproc.qimage_to_array(old_image)
        rgb = rgba[:, :, :3].copy()
        path = mm.path_for(model)

        self._ai_set_busy(True)
        self._ai_status(t("ai.color.working"))

        def work(report, token):
            out = subproc.run_model("ai.colorize", "colorize",
                                    rgb, path, report=report, token=token)
            return None if token.cancelled else out

        def done(out_rgb):
            self._ai_handle = None
            self._ai_set_busy(False)
            if out_rgb is None:
                self._ai_status_clear()
                return
            new_rgba = rgba.copy()
            new_rgba[:, :, :3] = out_rgb            # conserva el alfa original
            self._ai_commit_pixels(destino, new_rgba, old_image, "hist.colorize",
                                   done_key="ai.color.done")

        def err(msg):
            self._ai_handle = None
            self._ai_set_busy(False)
            self._ai_status_clear()
            imago_warning(self, t("ai.color.title"), t("ai.bg.error", err=msg))

        self._ai_handle = runner.submit(work, on_done=done, on_error=err)

    def ai_upscale(self, scale):
        """Aumenta la resolución de la imagen ×2 o ×4 (Real-ESRGAN). La capa activa
        se reconstruye con IA; las demás se escalan con suavizado."""
        pc = self._ai_precheck()
        if not pc:
            return
        canvas, idx = pc
        from models.destino_edicion import DestinoCapa, DestinoDocumento
        destino = DestinoCapa(canvas, idx)
        documento = DestinoDocumento(canvas)
        new_w, new_h = canvas.base_width * scale, canvas.base_height * scale
        if max(new_w, new_h) > 8000:
            from widgets.custom_titlebar import imago_question
            from PySide6.QtWidgets import QMessageBox
            if imago_question(self, t("ai.upscale.title"),
                              t("ai.upscale.too_big", w=new_w, h=new_h)) != QMessageBox.Yes:
                return
        from ai import model_manager as mm
        model = mm.get_model("realesrgan")
        self._ai_ensure_model(
            model, lambda: self._ai_run_upscale(destino, documento, model, scale))

    def _ai_run_upscale(self, destino, documento, model, scale):
        from ai import model_manager as mm, imgproc, upscale, subproc
        from models.layer_commands import SuperResolutionCommand
        from widgets.custom_titlebar import imago_warning
        runner = self._ai_get_runner()
        idx = self._ai_indice_destino(destino)
        if idx is None or not documento.vigente(self, exigir_activo=True):
            self._ai_status(t("ai.target_changed"), 6000)
            return
        canvas = destino.canvas
        old_image = destino.layer.image.copy()
        rgba = imgproc.qimage_to_array(old_image)
        rgb = rgba[:, :, :3].copy()
        alpha = rgba[:, :, 3].copy()
        path = mm.path_for(model)

        self._ai_set_busy(True)
        self._ai_status(t("ai.upscale.working"))

        def work(report, token):
            up = subproc.run_model("ai.upscale", "upscale",
                                   rgb, path, scale=scale, report=report, token=token)
            if up is None:
                return None
            hn, wn = up.shape[:2]
            a_up = imgproc.resize_mask(alpha, wn, hn)   # alfa por suavizado
            return imgproc.merge_rgb_alpha(up, a_up)

        def done(rgba_up):
            self._ai_handle = None
            self._ai_set_busy(False)
            if rgba_up is None:
                self._ai_status_clear()
                return
            idx = self._ai_indice_destino(destino)
            if idx is None or not documento.vigente(self, exigir_activo=True):
                self._ai_status(t("ai.target_changed"), 6000)
                return
            hn, wn = rgba_up.shape[:2]
            active_q = imgproc.array_to_qimage(rgba_up, wn, hn).convertToFormat(
                QImage.Format_ARGB32)
            canvas.undo_stack.push(self._ai_tag(SuperResolutionCommand(canvas, scale, idx, active_q)))
            self.fit_canvas_to_screen()
            self._ai_status(t("ai.upscale.done", w=wn, h=hn), 4000)

        def err(msg):
            self._ai_handle = None
            self._ai_set_busy(False)
            self._ai_status_clear()
            imago_warning(self, t("ai.upscale.title"), t("ai.bg.error", err=msg))

        self._ai_handle = runner.submit(work, on_done=done, on_error=err,
                                        on_progress=self._ai_progress)

    def ai_restore_faces(self):
        """Restaura/mejora las caras de la foto (YuNet detecta + GFPGAN restaura)."""
        pc = self._ai_precheck()
        if not pc:
            return
        canvas, idx = pc
        from models.destino_edicion import DestinoCapa
        destino = DestinoCapa(canvas, idx)
        from ai import model_manager as mm
        yunet = mm.get_model("yunet")
        gfpgan = mm.get_model("gfpgan")
        # Se necesitan AMBOS modelos: se aseguran encadenados (descarga bajo demanda).
        self._ai_ensure_model(yunet, lambda: self._ai_ensure_model(
            gfpgan, lambda: self._ai_run_faces(destino, yunet, gfpgan)))

    def _ai_run_faces(self, destino, yunet, gfpgan):
        from ai import model_manager as mm, imgproc, face_restore, subproc
        from widgets.custom_titlebar import imago_warning, imago_information
        runner = self._ai_get_runner()
        if self._ai_indice_destino(destino) is None:
            return
        old_image = destino.layer.image.copy()
        rgba = imgproc.qimage_to_array(old_image)
        rgb = rgba[:, :, :3].copy()
        yp, gp = mm.path_for(yunet), mm.path_for(gfpgan)

        self._ai_set_busy(True)
        self._ai_status(t("ai.faces.working"))

        def work(report, token):
            out, n = subproc.run_model("ai.face_restore", "restore",
                                       rgb, yp, gp, report=report, token=token)
            return None if out is None else (out, n)

        def done(res):
            self._ai_handle = None
            self._ai_set_busy(False)
            if res is None:
                self._ai_status_clear()
                return
            out, n = res
            if n == 0:                       # no se detectó ninguna cara
                self._ai_status_clear()
                imago_information(self, t("ai.faces.title"), t("ai.faces.none"))
                return
            new_rgba = rgba.copy()
            new_rgba[:, :, :3] = out         # conserva el alfa original
            self._ai_commit_pixels(destino, new_rgba, old_image, "hist.faces")
            self._ai_status(t("ai.faces.done", n=n), 4000)

        def err(msg):
            self._ai_handle = None
            self._ai_set_busy(False)
            self._ai_status_clear()
            imago_warning(self, t("ai.faces.title"), t("ai.bg.error", err=msg))

        self._ai_handle = runner.submit(work, on_done=done, on_error=err,
                                        on_progress=self._ai_progress)

    def ai_depth_bokeh(self):
        """Desenfoque por PROFUNDIDAD (bokeh): MiDaS estima la profundidad y el
        sujeto cercano queda nítido mientras el fondo se difumina gradualmente.
        Abre un panel overlay con preview (radio del desenfoque)."""
        pc = self._ai_precheck()
        if not pc:
            return
        canvas, idx = pc

        def open_panel(weight, destino):
            from ai.effect_panels import AIBokehPanel
            self._open_ai_overlay(self._ai_tag(
                AIBokehPanel(self, weight, destino=destino)))

        self._ai_with_depth(canvas, idx, open_panel)

    def ai_anaglyph(self):
        """Efecto 3D anaglifo (gafas rojo/cian): desplaza los píxeles según la
        profundidad (MiDaS) para simular la vista de cada ojo. Abre un panel
        overlay con preview (intensidad del paralaje)."""
        pc = self._ai_precheck()
        if not pc:
            return
        canvas, idx = pc

        def open_panel(weight, destino):
            from ai.effect_panels import AIAnaglyphPanel
            self._open_ai_overlay(self._ai_tag(
                AIAnaglyphPanel(self, weight, destino=destino)))

        self._ai_with_depth(canvas, idx, open_panel)

    def _ai_with_depth(self, canvas, idx, then):
        """Asegura el modelo MiDaS (descarga bajo demanda) y obtiene el mapa de
        profundidad CACHEADO por capa (se recalcula solo si la capa cambió).
        Llama then(depth, destino) —uint8 (H, W), 255=cerca + identidad
        estable— en el hilo GUI. Compartido por el bokeh y el anaglifo 3D."""
        from ai import model_manager as mm
        from models.destino_edicion import DestinoCapa
        destino = DestinoCapa(canvas, idx)
        layer = destino.layer
        cached = getattr(layer, "_ai_depth", None)
        if cached is not None and getattr(layer, "_ai_depth_key", None) == layer.image.cacheKey():
            then(cached, destino)   # cache válida: sin inferencia
            return
        model = mm.get_model("midas-small")
        self._ai_ensure_model(
            model, lambda: self._ai_compute_depth(destino, model, then))

    def _ai_compute_depth(self, destino, model, then):
        from ai import model_manager as mm, imgproc, depth, subproc
        from widgets.custom_titlebar import imago_warning
        runner = self._ai_get_runner()
        idx = self._ai_indice_destino(destino)
        if idx is None:
            return
        canvas = destino.canvas
        layer = destino.layer
        cache_key = layer.image.cacheKey()
        rgb = imgproc.qimage_to_array(layer.image)[:, :, :3].copy()
        path = mm.path_for(model)

        self._ai_set_busy(True)
        self._ai_status(t("ai.bokeh.working"))

        def work(report, token):
            w = subproc.run_model("ai.depth", "sharpness_weight",
                                  rgb, path, report=report, token=token)
            return None if token.cancelled else w

        def done(weight):
            self._ai_handle = None
            self._ai_set_busy(False)
            if weight is None:
                self._ai_status_clear()
                return
            self._ai_status_clear()
            current = self._ai_indice_destino(destino)
            if current is None:
                return
            layer._ai_depth = weight            # cache por capa
            layer._ai_depth_key = cache_key
            then(weight, destino)

        def err(msg):
            self._ai_handle = None
            self._ai_set_busy(False)
            self._ai_status_clear()
            imago_warning(self, t("ai.bokeh.title"), t("ai.bg.error", err=msg))

        self._ai_handle = runner.submit(work, on_done=done, on_error=err)

    # -- funciones de visión clásica (OpenCV, sin modelos) -----------------
    def _composed_rgb(self, canvas):
        """RGB (H, W, 3) de la imagen COMPUESTA (todas las capas visibles), para
        las funciones que analizan lo que se ve (p. ej. detectar el horizonte)."""
        from ai import imgproc
        flat = QImage(canvas.base_width, canvas.base_height, QImage.Format_ARGB32)
        flat.fill(0)
        painter = QPainter(flat)
        for layer in canvas.layers:
            if layer.visible:
                painter.setOpacity(layer.opacity / 100.0)
                painter.drawImage(0, 0, layer.render_image())
        painter.end()
        return imgproc.qimage_to_array(flat)[:, :, :3].copy()

    def ai_straighten_horizon(self):
        """Detecta la inclinación del horizonte (Canny+Hough) y, previa
        confirmación con el ángulo, gira TODAS las capas para nivelarla."""
        pc = self._cv_precheck()
        if not pc:
            return
        canvas, idx = pc
        from models.destino_edicion import DestinoDocumento
        documento = DestinoDocumento(canvas)
        from widgets.custom_titlebar import imago_information, imago_question
        from PySide6.QtWidgets import QMessageBox
        runner = self._ai_get_runner()
        rgb = self._composed_rgb(canvas)

        self._ai_set_busy(True)
        self._ai_status(t("ai.horizon.working"))

        def work(report, token):
            from ai.cv_effects import detect_horizon_angle
            return detect_horizon_angle(rgb)

        def done(angle):
            self._ai_handle = None
            self._ai_set_busy(False)
            self._ai_status_clear()
            if not documento.vigente(self, exigir_activo=True):
                self._ai_status(t("ai.target_changed"), 6000)
                return
            if angle is None:
                imago_information(self, t("ai.horizon.title"), t("ai.horizon.none"))
                return
            if abs(angle) < 0.15:
                imago_information(self, t("ai.horizon.title"), t("ai.horizon.level"))
                return
            # Confirmar con el ángulo (la detección puede fallar en fotos sin
            # horizonte real); deshacible en cualquier caso.
            if imago_question(self, t("ai.horizon.title"),
                              t("ai.horizon.ask", d=round(abs(angle), 1))) != QMessageBox.Yes:
                return
            from models.layer_commands import StraightenCommand
            canvas.undo_stack.push(self._ai_tag(StraightenCommand(canvas, -angle)))
            self._ai_status(t("ai.horizon.done", d=round(abs(angle), 1)), 4000)

        def err(msg):
            self._ai_handle = None
            self._ai_set_busy(False)
            self._ai_status_clear()
            from widgets.custom_titlebar import imago_warning
            imago_warning(self, t("ai.horizon.title"), t("ai.bg.error", err=msg))

        self._ai_handle = runner.submit(work, on_done=done, on_error=err)

    def ai_fix_perspective(self):
        """Detecta el plano dominante (documento, pantalla, fachada...) y, previa
        confirmación, lo rectifica a vista frontal (todas las capas; el lienzo
        pasa a medir el rectángulo resultante)."""
        pc = self._cv_precheck()
        if not pc:
            return
        canvas, idx = pc
        from models.destino_edicion import DestinoDocumento
        documento = DestinoDocumento(canvas)
        from widgets.custom_titlebar import imago_information, imago_question
        from PySide6.QtWidgets import QMessageBox
        runner = self._ai_get_runner()
        rgb = self._composed_rgb(canvas)

        self._ai_set_busy(True)
        self._ai_status(t("ai.persp.working"))

        def work(report, token):
            from ai.cv_effects import detect_document_quad
            return detect_document_quad(rgb)

        def done(res):
            self._ai_handle = None
            self._ai_set_busy(False)
            self._ai_status_clear()
            if not documento.vigente(self, exigir_activo=True):
                self._ai_status(t("ai.target_changed"), 6000)
                return
            if res is None:
                imago_information(self, t("ai.persp.title"), t("ai.persp.none"))
                return
            quad, (w, h) = res
            if imago_question(self, t("ai.persp.title"),
                              t("ai.persp.ask", w=w, h=h)) != QMessageBox.Yes:
                return
            from models.layer_commands import PerspectiveCommand
            canvas.undo_stack.push(self._ai_tag(PerspectiveCommand(canvas, quad, w, h)))
            self.fit_canvas_to_screen()
            self._ai_status(t("ai.persp.done", w=w, h=h), 4000)

        def err(msg):
            self._ai_handle = None
            self._ai_set_busy(False)
            self._ai_status_clear()
            from widgets.custom_titlebar import imago_warning
            imago_warning(self, t("ai.persp.title"), t("ai.bg.error", err=msg))

        self._ai_handle = runner.submit(work, on_done=done, on_error=err)

    def ai_panorama(self):
        """Une varias fotos solapadas en un panorama (cv2.Stitcher) y lo abre
        como DOCUMENTO NUEVO. No necesita lienzo abierto ni entra en el deshacer."""
        from widgets.custom_titlebar import imago_warning
        if getattr(self, "_ai_handle", None) is not None:
            imago_warning(self, t("ai.pano.title"), t("ai.bg.busy"))
            return
        from ai.cv_effects import cv_available
        if not cv_available():
            imago_warning(self, t("ai.pano.title"), t("ai.cv.no_opencv"))
            return
        from PySide6.QtWidgets import QFileDialog
        files, _ = QFileDialog.getOpenFileNames(
            self, t("ai.pano.pick", default="Elige las fotos del panorama"), "",
            "Imagenes (*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff)")
        if not files:
            return
        if len(files) < 2:
            imago_warning(self, t("ai.pano.title"), t("ai.pano.need2"))
            return
        runner = self._ai_get_runner()
        self._ai_target_canvas = None
        self._ai_set_busy(True)
        self._ai_status(t("ai.pano.working"))

        def work(report, token):
            from ai import imgproc
            from ai.cv_effects import stitch_panorama
            arrays = []
            for f in files:
                img = QImage(f)
                if img.isNull():
                    raise RuntimeError(t("ai.pano.bad_file", name=os.path.basename(f)))
                arrays.append(imgproc.qimage_to_array(
                    img.convertToFormat(QImage.Format_ARGB32))[:, :, :3].copy())
            return stitch_panorama(arrays, token=token)

        def done(res):
            self._ai_handle = None
            self._ai_set_busy(False)
            self._ai_status_clear()
            pano, error = res
            if error == "cancelado":
                return
            if pano is None:
                imago_warning(self, t("ai.pano.title"), t("ai.pano.fail"))
                return
            import numpy as np
            from ai import imgproc
            h, w = pano.shape[:2]
            rgba = imgproc.merge_rgb_alpha(pano, np.full((h, w), 255, np.uint8))
            img = imgproc.array_to_qimage(rgba, w, h).convertToFormat(
                QImage.Format_ARGB32)
            self.create_new_tab_canvas(w, h, t("ai.pano.doc", default="Panorama"),
                                       image_to_load=img)
            QTimer.singleShot(20, self.fit_canvas_to_screen)
            self._ai_status(t("ai.pano.done", w=w, h=h), 4000)

        def err(msg):
            self._ai_handle = None
            self._ai_set_busy(False)
            self._ai_status_clear()
            imago_warning(self, t("ai.pano.title"), t("ai.bg.error", err=msg))

        self._ai_handle = runner.submit(work, on_done=done, on_error=err)

    def ai_red_eyes(self):
        """Corrige ojos rojos en la capa activa: dentro de la SELECCIÓN si la
        hay; si no, detectando los ojos automáticamente (cascada de OpenCV)."""
        pc = self._cv_precheck()
        if not pc:
            return
        canvas, idx = pc
        from ai import imgproc
        from models.destino_edicion import DestinoCapa
        from widgets.custom_titlebar import imago_information
        runner = self._ai_get_runner()
        destino = DestinoCapa(canvas, idx)
        old_image = destino.layer.image.copy()
        rgba = imgproc.qimage_to_array(old_image)
        sel_mask = None
        if canvas.selection is not None and not canvas.selection.isEmpty():
            sel_mask = canvas._selection_mask()

        self._ai_set_busy(True)
        self._ai_status(t("ai.redeye.working"))

        def work(report, token):
            from ai.cv_effects import fix_red_eyes
            return fix_red_eyes(rgba, sel_mask)

        def done(res):
            self._ai_handle = None
            self._ai_set_busy(False)
            out, n = res
            if n == 0:
                self._ai_status_clear()
                imago_information(self, t("ai.redeye.title"), t("ai.redeye.none"))
                return
            self._ai_commit_pixels(destino, out, old_image, "hist.redeye",
                                   done_key="ai.redeye.done")

        def err(msg):
            self._ai_handle = None
            self._ai_set_busy(False)
            self._ai_status_clear()
            from widgets.custom_titlebar import imago_warning
            imago_warning(self, t("ai.redeye.title"), t("ai.bg.error", err=msg))

        self._ai_handle = runner.submit(work, on_done=done, on_error=err)

    def ai_denoise(self):
        """Reduce el ruido de la capa activa (SCUNet)."""
        pc = self._ai_precheck()
        if not pc:
            return
        canvas, idx = pc
        # SCUNet es lento (en GPUs por DirectML cae a CPU): avisar de que puede tardar
        # varios minutos y dar opción a cancelar antes de empezar.
        from widgets.custom_titlebar import imago_question
        from PySide6.QtWidgets import QMessageBox
        if imago_question(self, t("ai.denoise.title"),
                          t("ai.denoise.slow_warn")) != QMessageBox.Yes:
            return
        from ai import model_manager as mm
        from models.destino_edicion import DestinoCapa
        destino = DestinoCapa(canvas, idx)
        model = mm.get_model("scunet-denoise")
        self._ai_ensure_model(model, lambda: self._ai_run_denoise(destino, model))

    def _ai_run_denoise(self, destino, model):
        from ai import model_manager as mm, imgproc, denoise, subproc
        from widgets.custom_titlebar import imago_warning
        runner = self._ai_get_runner()
        if self._ai_indice_destino(destino) is None:
            return
        old_image = destino.layer.image.copy()
        rgba = imgproc.qimage_to_array(old_image)
        rgb = rgba[:, :, :3].copy()
        path = mm.path_for(model)

        self._ai_set_busy(True)
        self._ai_status(t("ai.denoise.working"))

        def work(report, token):
            out = subproc.run_model("ai.denoise", "denoise",
                                    rgb, path, report=report, token=token)
            if out is None:
                return None
            new_rgba = rgba.copy()
            new_rgba[:, :, :3] = out                # conserva el alfa original
            return new_rgba

        def done(new_rgba):
            self._ai_handle = None
            self._ai_set_busy(False)
            if new_rgba is None:
                self._ai_status_clear()
                return
            self._ai_commit_pixels(destino, new_rgba, old_image, "hist.denoise",
                                   done_key="ai.denoise.done")

        def err(msg):
            self._ai_handle = None
            self._ai_set_busy(False)
            self._ai_status_clear()
            imago_warning(self, t("ai.denoise.title"), t("ai.bg.error", err=msg))

        self._ai_handle = runner.submit(work, on_done=done, on_error=err,
                                        on_progress=self._ai_progress)

    def ai_ocr(self):
        """Extrae el texto de la imagen COMPUESTA (lo que se ve) con PP-OCR y lo
        copia al portapapeles. No toca los pixeles ni el historial."""
        from widgets.custom_titlebar import imago_warning
        if getattr(self, "_ai_handle", None) is not None:
            imago_warning(self, t("ai.ocr.title"), t("ai.bg.busy"))
            return
        canvas = self.get_current_canvas()
        if canvas is None:
            return
        self._ai_target_canvas = canvas
        from models.destino_edicion import DestinoDocumento
        documento = DestinoDocumento(canvas)
        from ai.runner import onnx_available
        if not onnx_available():
            imago_warning(self, t("ai.ocr.title"), t("ai.bg.no_onnx"))
            return
        from ai.cv_effects import cv_available
        if not cv_available():
            imago_warning(self, t("ai.ocr.title"), t("ai.cv.no_opencv"))
            return
        from ai import model_manager as mm
        det = mm.get_model("ocr-det")
        rec = mm.get_model("ocr-rec-latin")
        # Se necesitan AMBOS modelos: se aseguran encadenados (como las caras).
        self._ai_ensure_model(det, lambda: self._ai_ensure_model(
            rec, lambda: self._ai_run_ocr(documento, det, rec)))

    def _ai_run_ocr(self, documento, det, rec):
        from ai import model_manager as mm, ocr, subproc
        from widgets.custom_titlebar import imago_warning, imago_information
        runner = self._ai_get_runner()
        if not documento.vigente(self, exigir_activo=True):
            self._ai_status(t("ai.target_changed"), 6000)
            return
        canvas = documento.canvas
        rgb = self._composed_rgb(canvas)
        dp, rp = mm.path_for(det), mm.path_for(rec)

        self._ai_set_busy(True)
        self._ai_status(t("ai.ocr.working"))

        def work(report, token):
            res = subproc.run_model("ai.ocr", "extract_text",
                                    rgb, dp, rp, report=report, token=token)
            return None if token.cancelled else res

        def done(res):
            self._ai_handle = None
            self._ai_set_busy(False)
            self._ai_status_clear()
            if res is None:
                return
            if not documento.vigente(self, exigir_activo=True):
                self._ai_status(t("ai.target_changed"), 6000)
                return
            text, n = res
            if not text:
                imago_information(self, t("ai.ocr.title"), t("ai.ocr.none"))
                return
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText(text)
            self._ai_status(t("ai.ocr.done", n=n), 4000)
            preview = text if len(text) <= 1200 else text[:1200] + "…"
            imago_information(self, t("ai.ocr.title"),
                              t("ai.ocr.copied") + "\n\n" + preview)

        def err(msg):
            self._ai_handle = None
            self._ai_set_busy(False)
            self._ai_status_clear()
            imago_warning(self, t("ai.ocr.title"), t("ai.bg.error", err=msg))

        self._ai_handle = runner.submit(work, on_done=done, on_error=err,
                                        on_progress=self._ai_progress)

