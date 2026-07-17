# tools/move_selection_tool.py
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QPainterPath
from i18n import t
from tools.base_tool import BaseTool, best_snap


class MoveSelectionTool(BaseTool):
    """Mueve SOLO la marquesina de la selección (su contorno), sin tocar ningún
    píxel de la imagen. Arrastra para reposicionarla; las FLECHAS la mueven
    píxel a píxel (Shift = ×10), con la ráfaga fusionada en una sola entrada
    del historial.

    A diferencia de 'Mover selección' (que levanta y reubica el contenido,
    dejando hueco y tapando el destino), esta herramienta solo desplaza la
    región seleccionada: la imagen queda intacta y a partir de ahí pintas,
    rellenas o copias dentro de la nueva posición. Si no hay selección activa,
    no hace nada."""

    NUDGE_KEYS = {
        Qt.Key_Left:  QPoint(-1, 0),
        Qt.Key_Right: QPoint(1, 0),
        Qt.Key_Up:    QPoint(0, -1),
        Qt.Key_Down:  QPoint(0, 1),
    }

    def __init__(self, canvas):
        super().__init__(canvas)
        self.tool_id = "move_selection"
        self._dragging = False
        self._last = None
        self._nudging = False
        self._nudge_orig = None   # Selección al iniciar la ráfaga (para deshacer)

    def _has_selection(self):
        sel = self.canvas.selection
        return sel is not None and not sel.isEmpty()

    def mouse_press(self, event):
        if event.button() != Qt.LeftButton:
            return
        if not self._has_selection():
            return
        self._dragging = True
        self._press = event.position() / self.canvas.zoom_factor
        # Copia de la selección original; cada movimiento se recalcula desde aquí
        # para poder imantar los bordes a las guías sin acumular deriva.
        self._orig = QPainterPath(self.canvas.selection)
        self._orig_bbox = self._orig.boundingRect()

    def mouse_move(self, event):
        if not self._dragging or not self._has_selection():
            return
        pt = event.position() / self.canvas.zoom_factor
        dx = pt.x() - self._press.x()
        dy = pt.y() - self._press.y()
        # 📏 Imantar los bordes del rectángulo de la selección a las guías
        c = self.canvas
        b = self._orig_bbox
        left, right = b.left() + dx, b.right() + dx
        top, bottom = b.top() + dy, b.bottom() + dy
        dx += best_snap((c.snap_x(left) - left, c.snap_x(right) - right))
        dy += best_snap((c.snap_y(top) - top, c.snap_y(bottom) - bottom))
        new_sel = QPainterPath(self._orig)
        new_sel.translate(dx, dy)
        self.canvas.selection = new_sel
        cb = getattr(self.canvas, 'selection_changed_callback', None)
        if cb:
            cb()
        self.canvas.update()

    def mouse_release(self, event):
        # 📜 Registrar el desplazamiento como paso de deshacer (era la única
        # operación de selección que no pasaba por el historial). El redo()
        # reasigna la selección ya vigente: inofensivo.
        if self._dragging and self._orig is not None:
            nueva = self.canvas.selection
            if nueva is not None and nueva.boundingRect() != self._orig.boundingRect():
                from tools.commands import SelectionChangeCommand
                self.canvas.undo_stack.push(SelectionChangeCommand(
                    self.canvas, self._orig, QPainterPath(nueva),
                    t("hist.move_marquee", default="Mover marquesina"),
                    tool_id="select"))
        self._dragging = False
        self._press = None
        self._orig = None

    # =========================================================================
    # ⌨️ FLECHAS: mover la marquesina píxel a píxel (Shift = ×10); la ráfaga
    # mantenida se fusiona en UNA entrada del historial (NudgeSelectionCommand).
    # =========================================================================

    def key_press(self, event):
        delta = self.NUDGE_KEYS.get(event.key())
        if delta is None:
            return False
        if self._dragging:
            return True  # No mezclar con un arrastre de ratón en curso
        if not self._has_selection():
            return False  # Sin selección, las flechas siguen haciendo scroll

        if event.modifiers() & Qt.ShiftModifier:
            delta = QPoint(delta.x() * 10, delta.y() * 10)

        if not self._nudging:
            self._nudge_orig = QPainterPath(self.canvas.selection)
            self._nudging = True

        nueva = QPainterPath(self.canvas.selection)
        nueva.translate(delta.x(), delta.y())
        self.canvas.selection = nueva
        cb = getattr(self.canvas, 'selection_changed_callback', None)
        if cb:
            cb()
        self.canvas.update()
        return True

    def key_release(self, event):
        if event.key() not in self.NUDGE_KEYS:
            return False
        if event.isAutoRepeat() or not self._nudging:
            return True
        self._nudging = False
        from tools.commands import NudgeSelectionCommand
        self.canvas.undo_stack.push(NudgeSelectionCommand(
            self.canvas, self._nudge_orig, QPainterPath(self.canvas.selection),
            t("hist.move_marquee", default="Mover marquesina"),
            tool_id="select"))
        self._nudge_orig = None
        return True