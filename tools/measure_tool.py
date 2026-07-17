# tools/measure_tool.py
import math
from i18n import t
from PySide6.QtGui import QPen, QColor, QBrush, QPainter
from PySide6.QtCore import Qt, QPointF, QRectF
from tools.base_tool import BaseTool


class MeasureTool(BaseTool):
    """Herramienta de Medición (regla): distancia y ángulo entre dos puntos.

    - Arrastrar traza la medición (Shift = ángulos de 15°).
    - Al soltar, la medición queda en pantalla y sus dos EXTREMOS se pueden
      arrastrar para ajustarla. Esc (o empezar otra) la borra.
    - Los datos (distancia, ángulo, ΔX, ΔY) se muestran EN VIVO en la barra
      de opciones y en la barra de estado, en px, cm o pulgadas según
      canvas.measure_unit (misma convención de 96 PPP que las reglas).

    NO pinta ni toca el historial: es puramente informativa."""

    NODE_HIT = 9              # radio de agarre de un extremo (px de PANTALLA)
    HANDLE_SCREEN_SIZE = 7    # lado del cuadradito de los extremos
    TICK_SCREEN = 7           # semilargo de la rayita perpendicular de cada extremo
    MIN_LEN_SCREEN = 3        # arrastre mínimo para que cuente como medición

    def __init__(self, canvas):
        super().__init__(canvas)
        self.tool_id = "measure"
        self.p0 = None             # extremos de la medición (QPointF) o None
        self.p1 = None
        self._dragging_new = False # arrastre inicial en curso
        self._drag_index = None    # extremo agarrado al reajustar (0 | 1)
        self._hover_index = None
        self._push_info()          # etiqueta inicial ("arrastra para medir")

    # ---------------------------------------------------------------- puntos
    def _logical(self, event):
        """Centro del píxel bajo el cursor (floor + 0,5), como Línea/Curva."""
        pos = event.position() / self.canvas.zoom_factor
        return QPointF(math.floor(pos.x()) + 0.5, math.floor(pos.y()) + 0.5)

    def _snap(self, p):
        return QPointF(self.canvas.snap_x(p.x()), self.canvas.snap_y(p.y()))

    @staticmethod
    def _constrain_angle(start, cur):
        """Shift: fuerza la medición a ángulos múltiplos de 15°."""
        dx = cur.x() - start.x()
        dy = cur.y() - start.y()
        d = math.hypot(dx, dy)
        if d < 1e-6:
            return QPointF(cur)
        paso = math.radians(15.0)
        ang = round(math.atan2(dy, dx) / paso) * paso
        return QPointF(start.x() + d * math.cos(ang),
                       start.y() + d * math.sin(ang))

    def _dist_screen(self, a, b):
        return math.hypot(a.x() - b.x(), a.y() - b.y()) * self.canvas.zoom_factor

    def _hit_end(self, p):
        """Índice del extremo bajo 'p' (0 | 1), o None."""
        if self.p0 is None or self.p1 is None:
            return None
        best, bestd = None, self.NODE_HIT
        for i, e in enumerate((self.p0, self.p1)):
            d = self._dist_screen(p, e)
            if d <= bestd:
                bestd, best = d, i
        return best

    # ---------------------------------------------------------------- ratón
    def mouse_press(self, event):
        if event.button() != Qt.LeftButton:
            return
        p = self._snap(self._logical(event))
        idx = self._hit_end(p)
        if idx is not None:
            self._drag_index = idx      # reajustar un extremo existente
            return
        # Empezar una medición nueva (borra la anterior)
        self.p0 = p
        self.p1 = QPointF(p)
        self._dragging_new = True
        self._push_info()
        self.canvas.update()

    def mouse_move(self, event):
        p = self._snap(self._logical(event))
        dragging = bool(event.buttons() & Qt.LeftButton)

        if dragging and self._dragging_new:
            if event.modifiers() & Qt.ShiftModifier:
                self.p1 = self._constrain_angle(self.p0, p)
            else:
                self.p1 = p
            self._push_info()
            self.canvas.update()
            return
        if dragging and self._drag_index is not None:
            otro = self.p1 if self._drag_index == 0 else self.p0
            if event.modifiers() & Qt.ShiftModifier:
                p = self._constrain_angle(otro, p)
            if self._drag_index == 0:
                self.p0 = p
            else:
                self.p1 = p
            self._push_info()
            self.canvas.update()
            return
        if not dragging:
            idx = self._hit_end(p)
            if idx != self._hover_index:
                self._hover_index = idx
                self.canvas.update()
            self.canvas.setCursor(
                Qt.PointingHandCursor if idx is not None else Qt.CrossCursor)

    def mouse_release(self, event):
        if event.button() != Qt.LeftButton:
            return
        if self._dragging_new:
            self._dragging_new = False
            # Arrastre demasiado corto: no hay medición
            if self.p0 is not None and self._dist_screen(self.p0, self.p1) < self.MIN_LEN_SCREEN:
                self._clear()
                return
        self._drag_index = None
        self._push_info()
        self.canvas.update()

    # -------------------------------------------------------------- teclado
    def key_press(self, event):
        if event.key() == Qt.Key_Escape and self.p0 is not None:
            self._clear()
            return True
        return False

    def _clear(self):
        self.p0 = None
        self.p1 = None
        self._dragging_new = False
        self._drag_index = None
        self._hover_index = None
        self._push_info()
        self.canvas.update()

    # ------------------------------------------------------------- medición
    def _unit(self):
        return getattr(self.canvas, 'measure_unit', 'px')

    def _formatear(self, px):
        """Convierte una longitud en píxeles a la unidad activa (misma
        convención de 96 PPP que las reglas: RulerOverlay.DPI/PX_PER_CM)."""
        from widgets.ruler_overlay import RulerOverlay
        u = self._unit()
        if u == "cm":
            return f"{px / RulerOverlay.PX_PER_CM:.2f} cm"
        if u == "in":
            return f"{px / RulerOverlay.DPI:.2f} in"
        return f"{px:.1f} px"

    def _push_info(self):
        """Publica distancia/ángulo/ΔX/ΔY en la barra de opciones y la de
        estado. Sin medición, muestra la invitación a arrastrar."""
        win = self.canvas.window() if hasattr(self.canvas, "window") else None
        ob = getattr(win, 'options_bar', None)
        bar = getattr(win, 'status_bar', None)
        if self.p0 is None or self.p1 is None:
            texto = t("measure.empty")
            if ob is not None and hasattr(ob, 'set_measure_info'):
                ob.set_measure_info(texto)
            if bar is not None:
                bar.clearMessage()
            return
        dx = self.p1.x() - self.p0.x()
        dy = self.p1.y() - self.p0.y()
        dist = math.hypot(dx, dy)
        # Ángulo en convención matemática (0° = este, positivo antihorario),
        # como la regla de Photoshop; el eje Y de pantalla crece hacia abajo.
        ang = math.degrees(math.atan2(-dy, dx))
        if abs(ang) < 0.05:
            ang = 0.0        # evita el "-0.0°" en mediciones horizontales
        texto = t("measure.info",
                  d=self._formatear(dist), a=f"{ang:.1f}",
                  dx=self._formatear(abs(dx)), dy=self._formatear(abs(dy)))
        if ob is not None and hasattr(ob, 'set_measure_info'):
            ob.set_measure_info(texto)
        if bar is not None:
            bar.showMessage(texto)

    def refresh_info(self):
        """Reformatea la medición actual (lo llama el cambio de unidad)."""
        self._push_info()

    # --------------------------------------------------------------- previa
    def draw_preview(self, painter):
        if self.p0 is None or self.p1 is None:
            return
        import theme
        blue = QColor(theme.ACCENT)
        z = max(self.canvas.zoom_factor, 0.0001)
        painter.setRenderHint(QPainter.Antialiasing, True)

        # Línea de medición (cosmética: 1 px de pantalla a cualquier zoom)
        pen = QPen(blue)
        pen.setWidth(0)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawLine(self.p0, self.p1)

        # Rayitas perpendiculares en los extremos (aspecto de regla)
        dx = self.p1.x() - self.p0.x()
        dy = self.p1.y() - self.p0.y()
        d = math.hypot(dx, dy)
        if d > 1e-6:
            px, py = -dy / d, dx / d
            tick = self.TICK_SCREEN / z
            for e in (self.p0, self.p1):
                painter.drawLine(QPointF(e.x() + px * tick, e.y() + py * tick),
                                 QPointF(e.x() - px * tick, e.y() - py * tick))

        # Extremos agarrables (cuadradito blanco; azul con hover/arrastre)
        half = (self.HANDLE_SCREEN_SIZE / 2.0) / z
        for i, e in enumerate((self.p0, self.p1)):
            hovered = (i == self._hover_index or i == self._drag_index)
            painter.setPen(QPen(blue, 0))
            painter.setBrush(QBrush(blue if hovered else QColor(255, 255, 255)))
            painter.drawRect(QRectF(e.x() - half, e.y() - half, 2 * half, 2 * half))
