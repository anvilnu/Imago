# tools/selection_tools.py
# Herramientas de selección: rectangular, elíptica y lazo.
# Las tres generan un QPainterPath que se guarda en canvas.selection.
# Usar QPainterPath unifica todo: el recorte de copiar/cortar, el dibujo
# del contorno y cualquier forma futura funcionan exactamente igual.

from PySide6.QtGui import QPainterPath, QPolygonF
from PySide6.QtCore import Qt, QRect, QRectF, QPoint
from i18n import t
from tools.base_tool import BaseTool
from tools.commands import SelectionChangeCommand


class BaseSelectionTool(BaseTool):
    """Mecánica común: arrastrar para definir la forma; al soltar,
    la selección queda guardada en el canvas. Cada nueva selección
    reemplaza a la anterior."""

    def __init__(self, canvas):
        super().__init__(canvas)
        self.start_point = None
        self.current_point = None
        self.prev_selection = None  # La selección previa, para el deshacer
        self._drag_mode = 'replace'   # modo efectivo de ESTE arrastre
        self._constrain = False       # Mayús: cuadrado / círculo
        self._from_center = False     # Ctrl: dibujar desde el centro
        self._space_held = False      # ␣ mantenida: reposicionar la caja en curso

    def _snap(self, pt):
        """Imanta un punto a las guías cercanas (si las hay)."""
        return QPoint(int(round(self.canvas.snap_x(pt.x()))),
                      int(round(self.canvas.snap_y(pt.y()))))

    def _mode_from_modifiers(self, mods):
        """Modo efectivo según teclas: Mayús=añadir, Alt=restar,
        Mayús+Alt=intersecar; sin modificadores, el modo del botón."""
        shift = bool(mods & Qt.ShiftModifier)
        alt = bool(mods & Qt.AltModifier)
        if shift and alt:
            return 'intersect'
        if shift:
            return 'add'
        if alt:
            return 'subtract'
        return getattr(self.canvas, 'selection_mode', 'replace')

    def mouse_press(self, event):
        if event.button() == Qt.LeftButton:
            zoom = self.canvas.zoom_factor
            self.start_point = self._snap((event.position() / zoom).toPoint())
            self.current_point = self.start_point
            # Modo efectivo de ESTE arrastre (los modificadores mandan sobre el botón)
            self._drag_mode = self._mode_from_modifiers(event.modifiers())
            self._constrain = False
            self._from_center = False
            self._space_held = False
            # Selección previa (para deshacer). En Reemplazar la ocultamos
            # durante el arrastre; en el resto la dejamos visible.
            self.prev_selection = self.canvas.selection
            if self._drag_mode == 'replace':
                self.canvas.selection = None
                self.canvas.notify_selection_changed()
            self.canvas.live_marquee = None
            # ✚ Durante el arrastre, cruz sola (sin la forma del cursor de reposo)
            if getattr(self, 'cross_while_dragging', False):
                self.canvas.setCursor(Qt.CrossCursor)
            self.canvas.update()

    def mouse_move(self, event):
        # OJO: 'is not None', no la veracidad del QPoint ((0,0) es falsy)
        if event.buttons() & Qt.LeftButton and self.start_point is not None:
            zoom = self.canvas.zoom_factor
            new_cp = self._snap((event.position() / zoom).toPoint())
            if self._space_held and self.current_point is not None:
                # ␣ Espacio mantenido: REPOSICIONAR la caja en curso sin
                # soltarla (clásico de Photoshop): el origen se desplaza con
                # el ratón y la forma conserva su tamaño.
                self.start_point += new_cp - self.current_point
                self.current_point = new_cp
            else:
                self.current_point = new_cp
                mods = event.modifiers()
                self._constrain = bool(mods & Qt.ShiftModifier)      # cuadrado / círculo
                self._from_center = bool(mods & Qt.ControlModifier)  # desde el centro
            self._update_live_marquee()
            self.canvas.update()

    def mouse_release(self, event):
        if event.button() == Qt.LeftButton and self.start_point is not None:
            zoom = self.canvas.zoom_factor
            if not self._space_held:
                self.current_point = self._snap((event.position() / zoom).toPoint())

            path = self.build_path()
            self._finish_selection(path)
            self.canvas.live_marquee = None
            self._clear_live_status()
            self.start_point = None
            self.current_point = None
            # Restaurar el cursor de reposo (cruz+forma) tras el arrastre
            if getattr(self, 'cross_while_dragging', False):
                cb = getattr(self.canvas, 'cursor_restore_callback', None)
                if cb:
                    cb()
            self.canvas.update()

    # =========================================================================
    # ␣ ESPACIO: reposicionar la selección EN CURSO. El canvas nos consulta
    # (wants_space_key) para no activar la mano temporal durante el arrastre.
    # =========================================================================

    def wants_space_key(self):
        """True mientras hay un arrastre en curso: Espacio reposiciona la caja
        que se está dibujando en vez de activar la mano temporal."""
        return self.start_point is not None

    def key_press(self, event):
        if event.key() == Qt.Key_Space and self.start_point is not None:
            self._space_held = True
            return True
        return False

    def key_release(self, event):
        if event.key() == Qt.Key_Space and self._space_held:
            if not event.isAutoRepeat():
                self._space_held = False
            return True
        return False

    def _finish_selection(self, path):
        """Registra el cambio de selección en el historial:
        - Arrastre válido → comando 'Selección X' (previa → nueva).
        - Clic suelto sobre una selección existente → comando 'Deseleccionar'.
        - Clic suelto sin selección previa → nada que registrar."""
        mode = getattr(self, '_drag_mode', 'replace')
        prev = self.prev_selection
        if path is not None and not path.isEmpty():
            if mode == 'add':
                # Unión con la selección previa (o nueva si no había)
                if prev is not None and not prev.isEmpty():
                    result = QPainterPath(prev).united(path)
                else:
                    result = path
                self.canvas.undo_stack.push(SelectionChangeCommand(
                    self.canvas, prev, result, t("hist.sel_add"), tool_id=self.tool_id))
            elif mode == 'subtract':
                # Resta de la selección previa; sin previa, no hay nada que restar
                if prev is not None and not prev.isEmpty():
                    result = QPainterPath(prev).subtracted(path)
                    if result.isEmpty():
                        result = None
                    self.canvas.undo_stack.push(SelectionChangeCommand(
                        self.canvas, prev, result, t("hist.sel_sub"), tool_id=self.tool_id))
            elif mode == 'intersect':
                # Intersección con la previa; sin previa, equivale a una nueva
                if prev is not None and not prev.isEmpty():
                    result = QPainterPath(prev).intersected(path)
                    if result.isEmpty():
                        result = None
                    self.canvas.undo_stack.push(SelectionChangeCommand(
                        self.canvas, prev, result, t("hist.sel_int"), tool_id=self.tool_id))
                else:
                    self.canvas.undo_stack.push(SelectionChangeCommand(
                        self.canvas, prev, path, self.history_name, tool_id=self.tool_id))
            else:
                self.canvas.undo_stack.push(SelectionChangeCommand(
                    self.canvas, prev, path, self.history_name, tool_id=self.tool_id))
        elif mode == 'replace' and prev is not None:
            # Clic suelto en modo Reemplazar → deseleccionar
            self.canvas.undo_stack.push(SelectionChangeCommand(
                self.canvas, prev, None, t("hist.deselect"), tool_id="deselect"))
        self.prev_selection = None

    def _status_bar(self):
        win = self.canvas.window() if hasattr(self.canvas, "window") else None
        return getattr(win, 'status_bar', None)

    def _clear_live_status(self):
        bar = self._status_bar()
        if bar is not None:
            bar.clearMessage()

    def _update_live_marquee(self):
        """Publica el rectángulo EN CURSO (caja de la forma que se está
        dibujando) para que la franja azul de las reglas lo siga en vivo,
        y muestra su tamaño (ancho × alto px) en la barra de estado."""
        path = self.build_path()
        if path is not None and not path.isEmpty():
            br = path.boundingRect()
            self.canvas.live_marquee = br
            bar = self._status_bar()
            if bar is not None:
                bar.showMessage(t("status.live.size",
                                  w=int(round(br.width())), h=int(round(br.height()))))
        else:
            self.canvas.live_marquee = None

    def draw_preview(self, painter):
        """Dibuja el contorno elástico mientras arrastras (con el mismo velo
        azulado que la marquesina definitiva)."""
        if self.start_point is not None and self.current_point is not None:
            path = self.build_path()
            if path is not None and not path.isEmpty():
                self.canvas.draw_selection_outline(painter, path, fill=True)

    def _size_params(self):
        """Modo de tamaño del panel de selección (el combo escribe en el
        canvas): 'normal', 'ratio' (proporción W:H) o 'fixed' (px). Cada modo
        tiene su propia pareja de valores en el canvas."""
        c = self.canvas
        mode = getattr(c, 'selection_size_mode', 'normal')
        if mode == 'ratio':
            return (mode,
                    max(1, int(getattr(c, 'selection_ratio_w', 1))),
                    max(1, int(getattr(c, 'selection_ratio_h', 1))))
        return (mode,
                max(1, int(getattr(c, 'selection_fixed_w', 100))),
                max(1, int(getattr(c, 'selection_fixed_h', 100))))

    def _drag_rect(self):
        """Rectángulo del arrastre con restricciones: Mayús = cuadrado
        (lado = mayor delta), Ctrl = dibujar desde el centro. Un clic SIN
        arrastre devuelve None (deseleccionar); ojo: un QRect entre dos puntos
        iguales mide 1x1, no 0x0, así que hay que compararlos explícitamente.
        Con el modo del panel 'Relación fija' la caja respeta la proporción
        W:H, y con 'Tamaño fijo' mide exactamente W×H px (basta un clic; el
        arrastre solo decide hacia qué lado crece)."""
        if self.start_point is None or self.current_point is None:
            return None
        sp, cp = self.start_point, self.current_point
        mode, fw, fh = self._size_params()

        if mode == 'fixed':
            dx = cp.x() - sp.x()
            dy = cp.y() - sp.y()
            if self._from_center:
                rect = QRect(sp.x() - fw // 2, sp.y() - fh // 2, fw, fh)
            else:
                # El píxel del clic queda dentro de la caja (esquina de anclaje)
                x = sp.x() - fw + 1 if dx < 0 else sp.x()
                y = sp.y() - fh + 1 if dy < 0 else sp.y()
                rect = QRect(x, y, fw, fh)
            return rect.normalized()

        if sp == cp:
            return None
        dx = cp.x() - sp.x()
        dy = cp.y() - sp.y()
        if mode == 'ratio':
            # 📐 Relación fija W:H: manda el eje que más avanza en proporción.
            # La caja se construye con tamaño EXACTO w×h (el QRect entre dos
            # puntos es inclusivo y su +1 por eje rompería la proporción).
            k = max(abs(dx) / fw, abs(dy) / fh)
            w = max(1, round(k * fw))
            h = max(1, round(k * fh))
            if self._from_center:
                rect = QRect(sp.x() - w // 2, sp.y() - h // 2, w, h)
            else:
                x = sp.x() - w + 1 if dx < 0 else sp.x()
                y = sp.y() - h + 1 if dy < 0 else sp.y()
                rect = QRect(x, y, w, h)
            return rect.normalized()
        if self._constrain:
            side = max(abs(dx), abs(dy))
            dx = side if dx >= 0 else -side
            dy = side if dy >= 0 else -side
        if self._from_center:
            rect = QRect(QPoint(sp.x() - abs(dx), sp.y() - abs(dy)),
                         QPoint(sp.x() + abs(dx), sp.y() + abs(dy)))
        else:
            rect = QRect(sp, QPoint(sp.x() + dx, sp.y() + dy))
        return rect.normalized()

    def build_path(self):
        """Cada subclase construye su forma. Devuelve un QPainterPath o None."""
        return None


class RectSelectTool(BaseSelectionTool):
    """Selección rectangular."""

    def __init__(self, canvas):
        super().__init__(canvas)
        self.tool_id = "select_rect"
        self.history_name = t("tool.name.select_rect")
        self.cross_while_dragging = True  # Cruz+rectángulo en reposo, cruz al arrastrar

    def build_path(self):
        # Mínimo 1 px: permite seleccionar una fila o columna suelta (pixel art)
        rect = self._drag_rect()
        if rect is None or rect.width() < 1 or rect.height() < 1:
            return None
        path = QPainterPath()
        path.addRect(QRectF(rect))
        return path


class EllipseSelectTool(BaseSelectionTool):
    """Selección elíptica/circular."""

    def __init__(self, canvas):
        super().__init__(canvas)
        self.tool_id = "select_ellipse"
        self.history_name = t("tool.name.select_ellipse")
        self.cross_while_dragging = True  # Cruz+círculo en reposo, cruz al arrastrar

    def build_path(self):
        rect = self._drag_rect()
        if rect is None or rect.width() < 1 or rect.height() < 1:
            return None
        path = QPainterPath()
        path.addEllipse(QRectF(rect))
        return path


class LassoSelectTool(BaseSelectionTool):
    """Selección a mano alzada (lazo): el camino sigue al ratón y se cierra
    automáticamente al soltar. Con el modo 'Poligonal' del panel
    (canvas.lasso_polygonal) se dibuja clic a clic: cada clic añade un
    vértice, doble clic o Intro cierra el polígono y Esc lo cancela."""

    def __init__(self, canvas):
        super().__init__(canvas)
        self.tool_id = "select_lasso"
        self.history_name = t("tool.name.select_lasso")
        self.points = []
        self._poly_active = False   # polígono en construcción (clic a clic)

    def _polygonal(self):
        return bool(getattr(self.canvas, 'lasso_polygonal', False))

    def wants_space_key(self):
        # Construyendo un polígono NO hay arrastre: Espacio puede seguir
        # activando la mano temporal para desplazarse por el lienzo.
        if self._poly_active:
            return False
        return super().wants_space_key()

    def mouse_press(self, event):
        if event.button() != Qt.LeftButton:
            return
        if self._polygonal():
            zoom = self.canvas.zoom_factor
            pt = self._snap((event.position() / zoom).toPoint())
            if not self._poly_active:
                # Primer vértice: misma preparación que un arrastre normal
                self._drag_mode = self._mode_from_modifiers(event.modifiers())
                self.prev_selection = self.canvas.selection
                if self._drag_mode == 'replace':
                    self.canvas.selection = None
                    self.canvas.notify_selection_changed()
                self.canvas.live_marquee = None
                self.start_point = pt
                self.points = [pt]
                self._poly_active = True
            else:
                self.points.append(pt)
            self.current_point = pt
            self._update_live_marquee()
            self.canvas.update()
            return
        super().mouse_press(event)
        self.points = [self.start_point]

    def mouse_move(self, event):
        zoom = self.canvas.zoom_factor
        raw = (event.position() / zoom).toPoint()
        if self._poly_active:
            # Sin botón: el segmento elástico sigue al cursor
            self.current_point = self._snap(raw)
            self._update_live_marquee()
            self.canvas.update()
            return
        if event.buttons() & Qt.LeftButton and self.start_point is not None:
            if self._space_held and self.current_point is not None:
                # ␣ Reposicionar el lazo entero en curso
                delta = raw - self.current_point
                self.points = [p + delta for p in self.points]
                self.start_point += delta
                self.current_point = raw
            else:
                self.current_point = raw
                self.points.append(self.current_point)
            self._update_live_marquee()
            self.canvas.update()

    def mouse_release(self, event):
        if self._poly_active:
            return   # en poligonal, los clics se gestionan en mouse_press
        if event.button() == Qt.LeftButton and self.start_point is not None:
            path = self.build_path()
            self._finish_selection(path)
            self.canvas.live_marquee = None
            self._clear_live_status()
            self.start_point = None
            self.current_point = None
            self.points = []
            self.canvas.update()

    def mouse_double_click(self, event):
        if self._poly_active:
            self._close_polygon()

    def key_press(self, event):
        if self._poly_active:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                self._close_polygon()
                return True
            if event.key() == Qt.Key_Escape:
                self._cancel_polygon()
                return True
        return super().key_press(event)

    def _close_polygon(self):
        """Cierra el polígono en curso y lo registra como selección."""
        path = self.build_path()
        self._finish_selection(path)
        self._reset_polygon()

    def _cancel_polygon(self):
        """Esc: abandona el polígono y repone la selección que se ocultó al
        empezar (nada pasó por el historial, así que se restaura a mano)."""
        if self._drag_mode == 'replace' and self.prev_selection is not None:
            self.canvas.selection = self.prev_selection
            self.canvas.notify_selection_changed()
        self.prev_selection = None
        self._reset_polygon()

    def _reset_polygon(self):
        self._poly_active = False
        self.canvas.live_marquee = None
        self._clear_live_status()
        self.start_point = None
        self.current_point = None
        self.points = []
        self.canvas.update()

    def draw_preview(self, painter):
        if self._poly_active and self.points:
            # Polilínea de los vértices + segmento elástico hasta el cursor
            pts = list(self.points)
            if self.current_point is not None:
                pts.append(self.current_point)
            path = QPainterPath()
            path.addPolygon(QPolygonF(pts))
            # fillPath rellena el polígono como si estuviera cerrado: anticipa
            # el área que quedará seleccionada al cerrar.
            self.canvas.draw_selection_outline(painter, path, fill=True)
            return
        super().draw_preview(painter)

    def build_path(self):
        # Hacen falta al menos 3 puntos para encerrar un área
        if len(self.points) < 3:
            return None
        path = QPainterPath()
        path.addPolygon(QPolygonF(self.points))
        path.closeSubpath()  # Cierra el lazo uniendo el final con el inicio
        return path