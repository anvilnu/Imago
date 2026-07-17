# opciones_herramientas.py
"""Handlers de la barra de opciones de herramienta (mixin de MainWindow).

Extraído de main.py TAL CUAL (sin cambios de comportamiento): aquí viven los
~60 handlers update_*/set_* que la barra de opciones dinámica
(widgets/options_bar.py) invoca al tocar un control y que escriben los
parámetros de la herramienta activa como ATRIBUTOS del canvas
(p. ej. canvas.eraser_color_tolerance), más sus auxiliares de sincronización
(_sync_selection_options, _sync_move_text_state, sync_text_panel...).
MainWindow hereda de OpcionesHerramientas, así que la barra de opciones sigue
conectando con self.update_* igual que antes."""
from PySide6.QtCore import Qt

from tools.move_tool import MoveTool
from tools.move_selection_tool import MoveSelectionTool
from tools.move_copy_tool import MoveCopyTool


class OpcionesHerramientas:
    def update_active_shape(self, shape_text):
        self.current_shape_text = shape_text
        canvas = self.get_current_canvas()
        if not canvas:
            self._refresh_tool_help()
            return
        from tools.shape_geometry import get_shape_id_by_name
        shape_id = get_shape_id_by_name(shape_text)
        # Si había una forma en edición, cambiar su tipo en vivo si es posible
        old = getattr(canvas, 'current_tool', None)
        if old is not None and getattr(old, 'tool_id', None) == 'shape':
            old.change_shape(shape_id)
        else:
            if old is not None and hasattr(old, 'finish_editing'):
                old.finish_editing()
            from tools.shape_tool import ShapeTool
            canvas.current_tool = ShapeTool(canvas, shape_id)
        # Empujar al lienzo el relleno y el estilo de línea actuales del panel
        if hasattr(self, 'options_bar') and hasattr(self.options_bar, '_set_shape_fill_enabled'):
            self.options_bar._set_shape_fill_enabled(True)
            self.update_shape_fill(self.options_bar.shape_fill_combo.currentData())
        if hasattr(self, 'options_bar') and hasattr(self.options_bar, 'shape_style_combo'):
            self.update_shape_line_style(self.options_bar.shape_style_combo.currentData())
        self._refresh_tool_help()

    def update_active_move_mode(self, mode_text):
        """Modalidad de la herramienta de mover (patrón Formas): mover el
        contenido (cortar), mover solo el contorno, o mover una copia."""
        self.current_move_mode = mode_text
        canvas = self.get_current_canvas()
        if not canvas:
            self._refresh_tool_help()
            return
        if mode_text == "outline":
            canvas.current_tool = MoveSelectionTool(canvas)
        elif mode_text == "copy":
            canvas.current_tool = MoveCopyTool(canvas)
        else:
            canvas.current_tool = MoveTool(canvas)
        canvas.setCursor(Qt.SizeAllCursor)
        self._refresh_tool_help()
        self._sync_move_text_state()

    def _on_active_layer_changed(self):
        """Lo llama el panel de Capas cuando cambia la capa activa (clic del
        usuario o refresco tras un comando): sincroniza el estado que depende
        del TIPO de capa (desplegable Modo de mover, acción Deseleccionar)."""
        self._sync_move_text_state()
        self.update_edit_actions_state()

    def _sync_move_text_state(self):
        """Con la herramienta de mover y una capa de TEXTO activa, el
        desplegable Modo no aplica (el texto se mueve/gira por su vía propia,
        no por marquesina/copia): se desactiva y, si la modalidad actual no
        maneja texto (Mover marquesina), se pasa temporalmente a la estándar.
        Al volver a una capa normal se restaura la modalidad del desplegable."""
        if not hasattr(self, 'options_bar'):
            return
        combo = getattr(self.options_bar, 'move_mode_selector', None)
        if combo is None:
            return
        canvas = self.get_current_canvas()
        es_mover = getattr(self, 'current_tool_name', None) == 'move'
        layer = canvas.get_active_layer_obj() if canvas else None
        es_texto = bool(layer is not None and getattr(layer, 'is_text', False))
        if es_mover and es_texto:
            combo.setEnabled(False)
            tool = getattr(canvas, 'current_tool', None)
            if not isinstance(tool, MoveTool):   # MoveSelectionTool no maneja texto
                canvas.current_tool = MoveTool(canvas)
                canvas.setCursor(Qt.SizeAllCursor)
        else:
            combo.setEnabled(True)
            if es_mover and canvas is not None:
                # Si el texto forzó la modalidad estándar, reponer la del combo
                # (solo si difieren: no perder una sesión de flotado en curso)
                mode = combo.currentData()
                esperado = {"outline": MoveSelectionTool,
                            "copy": MoveCopyTool}.get(mode, MoveTool)
                if type(getattr(canvas, 'current_tool', None)) is not esperado:
                    self.update_active_move_mode(mode)

    def update_gradient_pattern(self, name):
        """Patrón activo del degradado. Si hay uno en curso, se recalcula."""
        canvas = self.get_current_canvas()
        if canvas:
            canvas.gradient_pattern = name
            self._gradient_refresh(canvas)

    def update_gradient_mode(self, mode):
        """Modo del degradado: Color o Transparencia."""
        canvas = self.get_current_canvas()
        if canvas:
            canvas.gradient_mode = mode
            self._gradient_refresh(canvas)

    def update_gradient_dither(self, on):
        """Suavizado anti-bandas (dithering) del degradado."""
        canvas = self.get_current_canvas()
        if canvas:
            canvas.gradient_dither = bool(on)
            self._gradient_refresh(canvas)

    def _gradient_refresh(self, canvas):
        """Re-renderiza el degradado si está activo (cambios en vivo)."""
        tool = getattr(canvas, 'current_tool', None)
        if hasattr(tool, 'refresh_live'):
            tool.refresh_live()

    def update_smudge_strength(self, value):
        canvas = self.get_current_canvas()
        if canvas: canvas.smudge_strength = value

    def update_smudge_hardness(self, value):
        canvas = self.get_current_canvas()
        if canvas: canvas.smudge_hardness = value

    def update_smudge_spacing(self, value):
        canvas = self.get_current_canvas()
        if canvas: canvas.smudge_spacing = value

    def update_smudge_finger_paint(self, on):
        canvas = self.get_current_canvas()
        if canvas: canvas.smudge_finger_paint = bool(on)

    def update_dodge_mode(self, mode):
        canvas = self.get_current_canvas()
        if canvas: canvas.dodge_mode = mode

    def update_dodge_range(self, rango):
        canvas = self.get_current_canvas()
        if canvas: canvas.dodge_range = rango

    def update_dodge_exposure(self, value):
        canvas = self.get_current_canvas()
        if canvas: canvas.dodge_exposure = value

    def update_dodge_hardness(self, value):
        canvas = self.get_current_canvas()
        if canvas: canvas.dodge_hardness = value

    def update_sponge_mode(self, mode):
        canvas = self.get_current_canvas()
        if canvas: canvas.sponge_mode = mode

    def update_sponge_flow(self, value):
        canvas = self.get_current_canvas()
        if canvas: canvas.sponge_flow = value

    def update_sponge_hardness(self, value):
        canvas = self.get_current_canvas()
        if canvas: canvas.sponge_hardness = value

    def update_liquify_strength(self, value):
        canvas = self.get_current_canvas()
        if canvas: canvas.liquify_strength = value

    def update_liquify_hardness(self, value):
        canvas = self.get_current_canvas()
        if canvas: canvas.liquify_hardness = value

    def update_shape_fill(self, pattern):
        """Patrón de relleno para las formas (None = transparente, solo bordes)."""
        canvas = self.get_current_canvas()
        if canvas:
            canvas.shape_fill_pattern = pattern
            tool = getattr(canvas, 'current_tool', None)
            if hasattr(tool, 'refresh_live'):
                tool.refresh_live()

    def update_shape_line_style(self, style):
        """Estilo del contorno de las formas (Qt.PenStyle: sólido, guiones...)."""
        canvas = self.get_current_canvas()
        if canvas and style is not None:
            canvas.shape_line_style = style
            tool = getattr(canvas, 'current_tool', None)
            if hasattr(tool, 'refresh_live'):
                tool.refresh_live()

    def set_pen_path_fill_pattern(self, pattern):
        """Patrón de relleno de la Pluma (modo 'Contorno + relleno').
        None/Sólido = relleno liso; el resto, patrón nativo de Qt."""
        canvas = self.get_current_canvas()
        if canvas:
            canvas.pen_path_fill_pattern = pattern

    def set_pen_path_output(self, mode):
        """Qué hace la Pluma al confirmar el trazo: 'stroke' (solo contorno),
        'fill' (contorno + relleno del área cerrada) o 'selection'
        (convierte el área cerrada en selección)."""
        canvas = self.get_current_canvas()
        if canvas:
            canvas.pen_path_output = mode

    def set_pen_path_line_style(self, style):
        """Estilo del contorno de la Pluma (Qt.PenStyle: sólido, guiones...)."""
        canvas = self.get_current_canvas()
        if canvas and style is not None:
            canvas.pen_path_line_style = style

    def set_line_curve_mode(self, mode):
        """Modo de curvado de Línea/Curva ('spline', 'bezier' o 'direct').
        Actúa EN VIVO sobre la línea flotante si la hay."""
        canvas = self.get_current_canvas()
        if canvas and mode is not None:
            canvas.line_curve_mode = mode
            tool = getattr(canvas, 'current_tool', None)
            if hasattr(tool, 'refresh_live'):
                tool.refresh_live()

    def set_line_curve_style(self, style):
        """Estilo del trazo de Línea/Curva (Qt.PenStyle: sólido, guiones...)."""
        canvas = self.get_current_canvas()
        if canvas and style is not None:
            canvas.line_curve_style = style
            tool = getattr(canvas, 'current_tool', None)
            if hasattr(tool, 'refresh_live'):
                tool.refresh_live()

    def set_line_curve_cap_start(self, forma):
        """Terminación del INICIO de Línea/Curva: 'none', 'arrow', 'circle'
        o 'bar'. Actúa EN VIVO sobre la línea flotante."""
        canvas = self.get_current_canvas()
        if canvas and forma is not None:
            canvas.line_curve_cap_start = forma
            tool = getattr(canvas, 'current_tool', None)
            if hasattr(tool, 'refresh_live'):
                tool.refresh_live()

    def set_line_curve_cap_end(self, forma):
        """Terminación del FINAL de Línea/Curva: 'none', 'arrow', 'circle'
        o 'bar'. Actúa EN VIVO sobre la línea flotante."""
        canvas = self.get_current_canvas()
        if canvas and forma is not None:
            canvas.line_curve_cap_end = forma
            tool = getattr(canvas, 'current_tool', None)
            if hasattr(tool, 'refresh_live'):
                tool.refresh_live()

    def set_measure_unit(self, unidad):
        """Unidad de la herramienta Medición ('px', 'cm' o 'in'); reformatea
        EN VIVO la medición en pantalla si la hay."""
        canvas = self.get_current_canvas()
        if canvas and unidad is not None:
            canvas.measure_unit = unidad
            tool = getattr(canvas, 'current_tool', None)
            if hasattr(tool, 'refresh_info'):
                tool.refresh_info()

    def set_line_curve_cap_size(self, tam):
        """Tamaño de las puntas de Línea/Curva en px (0 = 'Auto': el grosor
        de la propia línea). Actúa EN VIVO sobre la línea flotante."""
        canvas = self.get_current_canvas()
        if canvas and tam is not None:
            canvas.line_curve_cap_size = int(tam)
            tool = getattr(canvas, 'current_tool', None)
            if hasattr(tool, 'refresh_live'):
                tool.refresh_live()

    def update_airbrush_hardness(self, value):
        canvas = self.get_current_canvas()
        if canvas: canvas.airbrush_hardness = value

    def update_airbrush_flow(self, value):
        canvas = self.get_current_canvas()
        if canvas: canvas.airbrush_flow = value

    def update_airbrush_shape(self, shape):
        canvas = self.get_current_canvas()
        if canvas:
            canvas.airbrush_shape = shape
            self.update_canvas_cursor()

    def update_airbrush_texture(self, texture):
        canvas = self.get_current_canvas()
        if canvas: canvas.airbrush_texture = texture

    def update_clone_shape(self, shape):
        canvas = self.get_current_canvas()
        if canvas:
            canvas.clone_shape = shape
            self.update_canvas_cursor()

    def update_clone_aligned(self, checked):
        canvas = self.get_current_canvas()
        if canvas: canvas.clone_aligned = bool(checked)

    def update_clone_sample_all(self, checked):
        canvas = self.get_current_canvas()
        if canvas: canvas.clone_sample_all = bool(checked)

    def update_brush_size(self, value):
        canvas = self.get_current_canvas()
        if canvas:
            canvas.brush_size = value
            tool = getattr(canvas, 'current_tool', None)
            if hasattr(tool, 'refresh_live'):
                tool.refresh_live()
        if hasattr(self, 'options_bar'): self.options_bar.sync_spin_boxes(value)
        self.update_canvas_cursor() # ← AÑADIDO

    def update_brush_hardness(self, value):
        """Recibe la dureza de la barra de opciones y la guarda de forma segura en el lienzo"""
        # Si usas self.canvas directamente
        if hasattr(self, 'canvas') and self.canvas is not None:
            self.canvas.brush_hardness = value
        # Si usas un método para obtener el lienzo activo (por ejemplo, con pestañas)
        elif hasattr(self, 'get_current_canvas'):
            canvas = self.get_current_canvas()
            if canvas:
                canvas.brush_hardness = value

    def update_brush_opacity(self, value):
        """Opacidad del trazo del pincel (independiente del alfa del color)."""
        canvas = self.get_current_canvas()
        if canvas: canvas.brush_opacity = int(value)

    def update_pen_selection_mode(self, on):
        """Activa/desactiva el modo SELECCIÓN del pincel en el lienzo activo."""
        canvas = self.get_current_canvas()
        if canvas:
            canvas.pen_selection_mode = bool(on)
            self.update_canvas_cursor()

    def update_brush_antialias(self, on):
        """Suavizado del pincel (bordes suaves) o dentado, en el lienzo activo."""
        canvas = self.get_current_canvas()
        if canvas:
            canvas.brush_antialias = bool(on)

    def update_eraser_hardness(self, value):
        canvas = self.get_current_canvas()
        if canvas: canvas.eraser_hardness = value

    def update_eraser_spacing(self, value):
        canvas = self.get_current_canvas()
        if canvas: canvas.eraser_spacing = value

    def update_eraser_color_mode(self, value):
        canvas = self.get_current_canvas()
        if canvas: canvas.eraser_color_mode = bool(value)

    def update_eraser_bg_mode(self, value):
        """Activa/desactiva el 'Borrador de fondos': muestrea el color del centro
        de la brocha en cada paso y borra lo parecido dentro de la tolerancia."""
        canvas = self.get_current_canvas()
        if canvas: canvas.eraser_bg_mode = bool(value)

    def update_eraser_color_tolerance(self, value):
        canvas = self.get_current_canvas()
        if canvas: canvas.eraser_color_tolerance = value

    def update_eraser_bg_one_shot(self, value):
        canvas = self.get_current_canvas()
        if canvas: canvas.eraser_bg_one_shot = bool(value)

    def update_eraser_bg_protect_primary(self, value):
        canvas = self.get_current_canvas()
        if canvas: canvas.eraser_bg_protect_primary = bool(value)

    def update_replace_color_tolerance(self, value):
        canvas = self.get_current_canvas()
        if canvas: canvas.replace_tolerance = value

    def update_replace_color_shape(self, shape):
        canvas = self.get_current_canvas()
        if canvas:
            canvas.replace_shape = shape
            self.update_canvas_cursor()

    def update_replace_color_hardness(self, value):
        canvas = self.get_current_canvas()
        if canvas: canvas.replace_hardness = int(value)

    def update_replace_color_contiguous(self, checked):
        canvas = self.get_current_canvas()
        if canvas: canvas.replace_contiguous = bool(checked)

    def update_replace_color_sample_all(self, checked):
        canvas = self.get_current_canvas()
        if canvas: canvas.replace_sample_all = bool(checked)

    # ----- Cubo de pintura -----
    def update_bucket_tolerance(self, value):
        canvas = self.get_current_canvas()
        if canvas: canvas.bucket_tolerance = int(value)

    def update_bucket_expand(self, value):
        canvas = self.get_current_canvas()
        if canvas: canvas.bucket_expand = int(value)

    def update_bucket_contiguous(self, checked):
        canvas = self.get_current_canvas()
        if canvas: canvas.bucket_contiguous = bool(checked)

    def update_bucket_antialias(self, checked):
        canvas = self.get_current_canvas()
        if canvas: canvas.bucket_antialias = bool(checked)

    def update_bucket_sample_all(self, checked):
        canvas = self.get_current_canvas()
        if canvas: canvas.bucket_sample_all = bool(checked)

    # ----- Selector de color (cuentagotas) -----
    def update_eyedropper_sample_size(self, size):
        canvas = self.get_current_canvas()
        if canvas: canvas.eyedropper_sample_size = int(size)

    def update_eyedropper_sample_all(self, all_layers):
        canvas = self.get_current_canvas()
        if canvas: canvas.eyedropper_sample_all = bool(all_layers)

    def set_selection_mode(self, mode):
        """Modo de combinación de las herramientas de selección:
        'replace' (reemplazar), 'add' (unión) o 'subtract' (restar)."""
        canvas = self.get_current_canvas()
        if canvas: canvas.selection_mode = mode

    def _sync_selection_options(self, canvas):
        """Vuelca las opciones del panel de selección en el canvas (las
        herramientas las leen de ahí EN VIVO, como la varita)."""
        if hasattr(self, 'options_bar') and hasattr(self.options_bar, 'sel_size_mode_combo'):
            ob = self.options_bar
            canvas.selection_size_mode = ob.sel_size_mode_combo.currentData()
            canvas.selection_ratio_w, canvas.selection_ratio_h = ob.current_selection_ratio()
            canvas.selection_fixed_w, canvas.selection_fixed_h = ob.current_selection_fixed()
            canvas.lasso_polygonal = (ob.lasso_mode_combo.currentData() == "polygon")

    def update_selection_size_mode(self, mode):
        canvas = self.get_current_canvas()
        if canvas: canvas.selection_size_mode = mode

    def update_selection_ratio(self, w, h):
        canvas = self.get_current_canvas()
        if canvas:
            canvas.selection_ratio_w = int(w)
            canvas.selection_ratio_h = int(h)

    def update_selection_fixed_w(self, value):
        canvas = self.get_current_canvas()
        if canvas: canvas.selection_fixed_w = int(value)

    def update_selection_fixed_h(self, value):
        canvas = self.get_current_canvas()
        if canvas: canvas.selection_fixed_h = int(value)

    def update_lasso_polygonal(self, polygonal):
        canvas = self.get_current_canvas()
        if canvas: canvas.lasso_polygonal = bool(polygonal)

    def update_wand_tolerance(self, value):
        canvas = self.get_current_canvas()
        if canvas: canvas.magic_wand_tolerance = int(value)

    def update_wand_contiguous(self, checked):
        canvas = self.get_current_canvas()
        if canvas: canvas.magic_wand_contiguous = bool(checked)

    def _crop_tool(self):
        """La herramienta de Recorte activa del lienzo actual, o None."""
        canvas = self.get_current_canvas()
        tool = getattr(canvas, 'current_tool', None) if canvas else None
        if tool is not None and getattr(tool, 'tool_id', '') == "crop":
            return tool
        return None

    def update_crop_ratio(self, ratio):
        """Relación de aspecto fija del recorte (None = libre). Si ya hay una
        caja dibujada, se reencaja a la nueva relación en el acto."""
        canvas = self.get_current_canvas()
        if canvas:
            canvas.crop_ratio = ratio
        tool = self._crop_tool()
        if tool is not None:
            tool.apply_ratio_to_box()

    def update_crop_apply(self):
        tool = self._crop_tool()
        if tool is not None:
            tool.apply()

    def update_crop_cancel(self):
        tool = self._crop_tool()
        if tool is not None:
            tool.cancel()

    def update_wand_sample_all(self, checked):
        canvas = self.get_current_canvas()
        if canvas: canvas.magic_wand_sample_all = bool(checked)

    def update_brush_pattern(self, pattern_id):
        canvas = self.get_current_canvas()
        if canvas:
            canvas.brush_pattern = pattern_id

    def update_bucket_pattern(self, pattern_id):
        # El relleno del Cubo es INDEPENDIENTE del relleno del Pincel.
        canvas = self.get_current_canvas()
        if canvas:
            canvas.bucket_pattern = pattern_id

    def update_pencil_size(self, value):
        canvas = self.get_current_canvas()
        if canvas: canvas.pencil_size = int(value)
        self.update_canvas_cursor()

    def update_pencil_shape(self, shape):
        canvas = self.get_current_canvas()
        if canvas: canvas.pencil_shape = shape or 'round'

    def update_brush_shape(self, shape):
        canvas = self.get_current_canvas()
        if canvas: canvas.brush_shape = shape or 'round'
        self.update_canvas_cursor()

    def update_eraser_shape(self, shape):
        canvas = self.get_current_canvas()
        if canvas: canvas.eraser_shape = shape or 'round'
        self.update_canvas_cursor()

    # ----- Texto -----
    def _text_tool_editing(self):
        """Devuelve la herramienta de texto SOLO si tiene un cuadro abierto."""
        canvas = self.get_current_canvas()
        tool = getattr(canvas, 'current_tool', None) if canvas else None
        if (tool is not None and getattr(tool, 'tool_id', '') == 'text'
                and getattr(tool, 'editor', None) is not None):
            return tool
        return None

    def _refresh_text_editor(self):
        tool = self._text_tool_editing()
        if tool is not None:
            tool.apply_format_from_canvas()

    def sync_text_panel(self, info):
        """El editor informa del formato bajo el cursor; lo reflejamos en el
        panel sin disparar sus señales (para no reaplicar en bucle)."""
        bar = getattr(self, 'options_bar', None)
        if bar is not None and hasattr(bar, 'set_text_panel_from_format'):
            bar.set_text_panel_from_format(info)

    def update_text_family(self, family):
        canvas = self.get_current_canvas()
        if canvas: canvas.text_family = family
        tool = self._text_tool_editing()
        if tool is not None: tool.apply_family(family)

    def update_text_size(self, value):
        canvas = self.get_current_canvas()
        if canvas: canvas.text_size = value
        tool = self._text_tool_editing()
        if tool is not None: tool.apply_size(value)

    def update_text_bold(self, value):
        canvas = self.get_current_canvas()
        if canvas: canvas.text_bold = bool(value)
        tool = self._text_tool_editing()
        if tool is not None: tool.apply_bold(bool(value))

    def update_text_italic(self, value):
        canvas = self.get_current_canvas()
        if canvas: canvas.text_italic = bool(value)
        tool = self._text_tool_editing()
        if tool is not None: tool.apply_italic(bool(value))

    def update_text_underline(self, value):
        canvas = self.get_current_canvas()
        if canvas: canvas.text_underline = bool(value)
        tool = self._text_tool_editing()
        if tool is not None: tool.apply_underline(bool(value))

    def update_text_strike(self, value):
        canvas = self.get_current_canvas()
        if canvas: canvas.text_strike = bool(value)
        tool = self._text_tool_editing()
        if tool is not None: tool.apply_strike(bool(value))

    def update_text_align(self, value):
        canvas = self.get_current_canvas()
        if canvas: canvas.text_align = value
        tool = self._text_tool_editing()
        if tool is not None: tool.apply_align(value)

    def update_text_vertical(self, value):
        # Orientación de la CAPA de texto (apilado vertical): NO es un formato de
        # carácter (en el editor se sigue escribiendo en horizontal), pero al
        # reeditar una capa el resultado se ve EN VIVO en el lienzo.
        canvas = self.get_current_canvas()
        if canvas: canvas.text_vertical = bool(value)
        tool = self._text_tool_editing()
        if tool is not None: tool.apply_vertical(bool(value))

    def update_text_spacing(self, value):
        # Interletraje de la CAPA de texto (el toHtml no lo conserva): se guarda
        # en el lienzo; el editor lo enseña visualmente y, al reeditar una capa,
        # el lienzo lo muestra además con su render real EN VIVO.
        canvas = self.get_current_canvas()
        if canvas: canvas.text_spacing = int(value)
        tool = self._text_tool_editing()
        if tool is not None: tool.apply_spacing(int(value))

    def update_text_color(self, color):
        """Color primario aplicado al texto en edición: a la parte seleccionada,
        o a todo el texto si no hay selección (lo llama el panel de colores)."""
        tool = self._text_tool_editing()
        if tool is not None:
            tool.apply_color(color)

    def update_brush_spacing(self, value):
        """Recibe el espaciado de la barra de opciones y lo guarda de forma segura en el lienzo"""
        if hasattr(self, 'canvas') and self.canvas is not None:
            self.canvas.brush_spacing = value
        elif hasattr(self, 'get_current_canvas'):
            canvas = self.get_current_canvas()
            if canvas:
                canvas.brush_spacing = value

