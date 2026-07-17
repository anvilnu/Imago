# tools/magic_wand_tool.py
from PySide6.QtGui import QPainterPath
from PySide6.QtCore import Qt
from i18n import t
from tools.base_tool import BaseTool
from tools.commands import SelectionChangeCommand
from tools.numpy_utils import build_flood_fill_mask, path_from_mask


class MagicWandTool(BaseTool):
    """Varita mágica: selecciona regiones de color similar al píxel pulsado.

    Reutiliza la misma lógica de tolerancia de color del Cubo de Pintura,
    pero en vez de rellenar, construye un QPainterPath de selección. Así se
    integra con TODO el sistema de selección existente (copiar, cortar,
    mover, transformar, recortar...) sin ninguna fricción.

    Dos modos:
    - Contigua (casilla del panel, por defecto): solo la mancha conectada al clic.
    - Global: todos los píxeles de color similar. Mayúsculas INVIERTE la casilla.
    El clic DERECHO siempre RESTA de la selección (como el pincel de selección).
    Muestrea la capa ACTIVA, o la composición visible con "Todas las capas"
    (como el cubo). Tolerancia y casillas se leen del canvas EN VIVO."""

    def __init__(self, canvas):
        super().__init__(canvas)
        self.tool_id = "magic_wand"
        self.history_name = t("tool.name.magic_wand")
        self.tolerance = 32  # Mismo umbral por defecto que el cubo

    def _floor_point(self, event):
        """Píxel EXACTO bajo el cursor (floor, no redondeo): la celda real
        sobre la que está el ratón, sin desfase de medio píxel al ampliar."""
        import math
        from PySide6.QtCore import QPoint
        pos = event.position() / self.canvas.zoom_factor
        return QPoint(math.floor(pos.x()), math.floor(pos.y()))

    def mouse_press(self, event):
        if event.button() not in (Qt.LeftButton, Qt.RightButton):
            return

        point = self._floor_point(event)

        # Muestra: capa activa, o composición visible con "Todas las capas"
        sample_all = bool(getattr(self.canvas, 'magic_wand_sample_all', False))
        if sample_all and hasattr(self.canvas, 'render_flat_image'):
            image = self.canvas.render_flat_image(Qt.transparent)
        else:
            layer_obj = self.canvas.layers[self.canvas.active_layer_index]
            image = layer_obj.image
        width, height = image.width(), image.height()

        # Clic fuera del lienzo: no hacemos nada
        if not (0 <= point.x() < width and 0 <= point.y() < height):
            return

        target_rgba = image.pixel(point)
        # Opciones EN VIVO del canvas (el panel escribe ahí); Mayús invierte
        # la casilla "Contigua" para alternar al vuelo sin ir al panel.
        self.tolerance = int(getattr(self.canvas, 'magic_wand_tolerance', self.tolerance))
        contiguous = bool(getattr(self.canvas, 'magic_wand_contiguous', True))
        if event.modifiers() & Qt.ShiftModifier:
            contiguous = not contiguous

        # Construir la selección (QPainterPath ya simplificado: solo el
        # perímetro) a partir de la máscara booleana del relleno por tolerancia.
        path = self._path_from_selected(image, point, target_rgba, contiguous)
        prev_selection = self.canvas.selection

        if path is None:
            # Nada seleccionable: si había selección previa, se deselecciona.
            # Con el botón DERECHO (restar) no: un fallo al restar no debe
            # tirar toda la selección.
            if prev_selection is not None and event.button() != Qt.RightButton:
                self.canvas.undo_stack.push(SelectionChangeCommand(
                    self.canvas, prev_selection, None, t("hist.deselect"), tool_id="deselect"))
            return

        # Combinar con la selección previa según el MODO activo (botones del panel:
        # Reemplazar / Añadir / Restar / Intersecar). Mayús ya se usa aquí para
        # 'no contigua', así que el modo se toma del botón, no de modificadores.
        # El clic DERECHO siempre RESTA (como el pincel de selección).
        mode = getattr(self.canvas, 'selection_mode', 'replace')
        if event.button() == Qt.RightButton:
            mode = 'subtract'
        has_prev = prev_selection is not None and not prev_selection.isEmpty()
        if mode == 'add' and has_prev:
            result = QPainterPath(prev_selection).united(path)
            name = t("hist.sel_add")
        elif mode == 'subtract':
            if not has_prev:
                return   # nada de lo que restar
            result = QPainterPath(prev_selection).subtracted(path)
            result = None if result.isEmpty() else result
            name = t("hist.sel_sub")
        elif mode == 'intersect' and has_prev:
            result = QPainterPath(prev_selection).intersected(path)
            result = None if result.isEmpty() else result
            name = t("hist.sel_int")
        else:
            result = path
            name = self.history_name

        self.canvas.undo_stack.push(SelectionChangeCommand(
            self.canvas, prev_selection, result, name, tool_id="magic_wand"))

    def _path_from_selected(self, image, start_pt, target_rgba, contiguous):
        """Devuelve el QPainterPath de los píxeles seleccionados (o None si no
        hay ninguno) usando numpy y scipy. Antes construía un QRegion tramo a
        tramo en un bucle Python que tardaba segundos en fotos grandes."""
        mask = build_flood_fill_mask(image, start_pt, self.tolerance, contiguous)
        return path_from_mask(mask)
