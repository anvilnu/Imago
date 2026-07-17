# menu_imagen_capas.py
"""Acciones de los menús Imagen y Capas (mixin de MainWindow).

Extraído de main.py TAL CUAL (sin cambios de comportamiento): recortar a la
selección, cambiar tamaño de imagen/lienzo, voltear y girar la imagen; y de
capas: visibilidad, voltear/girar la capa, modo de fusión (con sincronía del
submenú) y máscaras (crear/desde selección/aplicar/quitar). MainWindow hereda
de AccionesMenuImagenCapas, así que los menús siguen conectando con self.*
igual que antes."""
from i18n import t


class AccionesMenuImagenCapas:
    def image_crop_to_selection(self):
        canvas = self.get_current_canvas()
        if not canvas:
            return
        if canvas.crop_to_selection():
            self.fit_canvas_to_screen()  # Reencuadrar la vista al nuevo tamaño
        else:
            self.status_bar.showMessage(t("status.no_crop"), 4000)

    def image_resize(self):
        """Imagen → Cambiar tamaño: escala todas las capas al nuevo tamaño y/o
        cambia la resolución de impresión (PPP). Usa el mismo diálogo que 'Nuevo'."""
        canvas = self.get_current_canvas()
        if not canvas:
            return
        from new_dialog import ImageSizeDialog
        dialog = ImageSizeDialog(self, width=canvas.base_width, height=canvas.base_height,
                                 dpi=getattr(canvas, 'dpi', 96.0),
                                 title=t("dlg.resize.title", default="Cambiar tamaño de imagen"))
        if dialog.exec():
            new_w, new_h = dialog.get_values()
            canvas.dpi = float(dialog.get_dpi())
            if (new_w, new_h) != (canvas.base_width, canvas.base_height):
                if canvas.resize_image(new_w, new_h):
                    self.fit_canvas_to_screen()

    def image_canvas_size(self):
        """Imagen → Tamaño del lienzo: cambia el lienzo sin escalar (con anclaje)."""
        canvas = self.get_current_canvas()
        if not canvas:
            return
        from new_dialog import CanvasSizeDialog
        dialog = CanvasSizeDialog(canvas.base_width, canvas.base_height, self)
        if dialog.exec():
            nw, nh, ax, ay, fill_id = dialog.get_values()
            fill_color = self._resolve_canvas_fill(canvas, fill_id)
            if canvas.resize_canvas(nw, nh, ax, ay, fill_color):
                self.fit_canvas_to_screen()

    def _resolve_canvas_fill(self, canvas, fill_id):
        """Traduce la opcion de Relleno del dialogo a un QColor (o None
        para transparente) para el margen nuevo del lienzo."""
        from PySide6.QtGui import QColor
        from PySide6.QtCore import Qt as _Qt
        if fill_id == "primary":
            return QColor(canvas.brush_color)
        if fill_id == "secondary":
            return QColor(canvas.brush_color_secondary)
        if fill_id == "white":
            return QColor(_Qt.white)
        if fill_id == "black":
            return QColor(_Qt.black)
        return None

    def image_flip(self, horizontal):
        """Imagen → Voltear horizontalmente/verticalmente."""
        canvas = self.get_current_canvas()
        if canvas:
            canvas.flip_image(horizontal)

    def image_rotate(self, degrees):
        """Imagen → Girar 90°/180°. Las de 90° cambian las dimensiones, así
        que reencuadramos la vista al nuevo tamaño."""
        canvas = self.get_current_canvas()
        if not canvas:
            return
        if canvas.rotate_image(degrees):
            self.fit_canvas_to_screen()

    def image_rotate_free(self):
        """Imagen → Rotación libre: panel overlay con dial de ángulo y vista
        previa en vivo; al Aceptar gira todas las capas (FreeRotateCommand),
        ampliando el lienzo al envolvente si la casilla está marcada."""
        if not self.get_current_canvas():
            return
        from adjustments import FreeRotateDialog
        self._open_ai_overlay(FreeRotateDialog(self))

    def layer_toggle_visibility(self):
        """Capas → Alternar visibilidad de la capa activa."""
        canvas = self.get_current_canvas()
        if not canvas:
            return
        from models.layer_commands import ToggleVisibilityCommand
        idx = canvas.active_layer_index
        cmd = ToggleVisibilityCommand(canvas, idx, not canvas.layers[idx].visible)
        canvas.undo_stack.push(cmd)

    def layer_flip(self, horizontal):
        """Capas → Voltear la capa activa (no afecta al resto de capas)."""
        canvas = self.get_current_canvas()
        if canvas:
            canvas.flip_layer(horizontal)

    def layer_set_blend_mode(self, modo):
        """Capas → Modo de fusión: aplica el modo a la capa activa como paso de
        deshacer (el MISMO comando que el combo del panel de Capas, que se
        re-sincroniza solo vía layers_changed_callback)."""
        canvas = self.get_current_canvas()
        if not canvas or canvas.get_active_layer_obj() is None:
            return
        index = canvas.active_layer_index
        layer = canvas.layers[index]
        if modo == layer.blend_mode:
            return
        from models.layer_commands import LayerPropertiesCommand
        canvas.undo_stack.push(LayerPropertiesCommand(
            canvas, index,
            layer.name, layer.name,
            layer.opacity, layer.opacity,
            layer.blend_mode, modo,
            layer.alpha_locked, layer.alpha_locked))

    def _sync_blend_menu(self):
        """Marca en el submenú Capas → Modo de fusión el modo de la capa activa
        (se llama en su aboutToShow)."""
        canvas = self.get_current_canvas()
        layer = canvas.get_active_layer_obj() if canvas else None
        modo = layer.blend_mode if layer is not None else None
        for act, m in getattr(self, '_blend_menu_actions', []):
            act.setChecked(m == modo)

    def layer_merge_effects(self):
        """Capas → Fusionar los efectos en la capa: HORNEA los efectos no
        destructivos de la capa activa en sus píxeles (el aspecto no cambia y
        la sublista fx queda vacía). Con una capa de TEXTO además rasteriza,
        previa confirmación (el texto deja de ser editable como texto)."""
        canvas = self.get_current_canvas()
        if not canvas:
            return
        layer = canvas.get_active_layer_obj()
        if layer is None or not getattr(layer, "effects", None):
            return
        if getattr(layer, "is_text", False):
            from widgets.custom_titlebar import imago_question
            from PySide6.QtWidgets import QMessageBox
            if imago_question(self, t("msg.merge_fx_text.title"),
                              t("msg.merge_fx_text.body")) != QMessageBox.Yes:
                return
        canvas.merge_layer_effects()

    def layer_toggle_clipped(self):
        """Capas → Máscara de recorte: la capa activa pasa a verse solo donde
        su capa BASE (la primera no recortada por debajo) tiene píxeles, o
        deja de estar recortada. Deshacible por parámetro (ClipLayerCommand);
        el estado de la marca del menú lo repone update_layer_menu_state."""
        canvas = self.get_current_canvas()
        if not canvas or canvas.get_active_layer_obj() is None:
            return
        index = canvas.active_layer_index
        if index <= 0:
            return   # la capa del fondo no tiene debajo a quien recortarse
        from models.layer_commands import ClipLayerCommand
        nuevo = not getattr(canvas.layers[index], "clipped", False)
        canvas.undo_stack.push(ClipLayerCommand(canvas, index, nuevo))

    # --- Máscara de capa ---
    def layer_mask_create(self):
        """Capas → Máscara → Mostrar todo (máscara blanca)."""
        canvas = self.get_current_canvas()
        if canvas:
            canvas.create_mask(from_selection=False)

    def layer_mask_from_selection(self):
        """Capas → Máscara → Desde la selección."""
        canvas = self.get_current_canvas()
        if canvas:
            canvas.create_mask(from_selection=True)

    def layer_mask_apply(self):
        """Capas → Máscara → Aplicar (hornea en los píxeles y la quita)."""
        canvas = self.get_current_canvas()
        if canvas:
            canvas.apply_mask()

    def layer_mask_remove(self):
        """Capas → Máscara → Eliminar (descarta sin tocar la capa)."""
        canvas = self.get_current_canvas()
        if canvas:
            canvas.remove_mask()

    def layer_rotate(self, degrees):
        """Capas → Girar la capa activa (el lienzo no cambia de tamaño)."""
        canvas = self.get_current_canvas()
        if canvas:
            canvas.rotate_layer(degrees)

