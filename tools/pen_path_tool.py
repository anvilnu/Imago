# tools/pen_path_tool.py
from i18n import t
from PySide6.QtGui import QPainter, QPen, QColor, QBrush, QImage, QPainterPath
from PySide6.QtCore import Qt, QPointF, QRectF
from tools.base_tool import BaseTool
from tools.commands import PaintCommand, SelectionChangeCommand


class PenPathTool(BaseTool):
    """Herramienta Pluma: trazado Bezier por puntos de ancla, editable en vivo.

    Crear:
    - Clic en vacio: punto 'esquina' -> segmento recto desde el anterior.
    - Clic + arrastrar en vacio: punto 'suave' -> saca tiradores Bezier simetricos.
    - Clic sobre el primer ancla (si hay >= 2): CIERRA el trazo (sin confirmar).

    Editar (mientras el trazo esta vivo):
    - Arrastrar un ancla: la mueve junto con sus tiradores.
    - Alt + arrastrar un ancla: le saca/curva los tiradores (la vuelve suave).
    - Alt + clic en un ancla suave: la vuelve esquina (le quita los tiradores).
    - Arrastrar un tirador: curva el segmento. El tirador opuesto se refleja
      (simetrico); con Alt se mueve solo ese lado (rompe la simetria -> pico).

    Confirmar / cancelar:
    - Enter / doble clic / cambiar de herramienta: confirma (rasteriza o
      convierte en seleccion, segun el panel).
    - Esc: cancela.  Retroceso: borra el ultimo ancla.

    La salida (contorno / contorno+relleno / seleccion) y el patron de relleno
    se eligen en el panel. Queda en el historial (deshacible).
    """

    # Umbrales en pixeles de PANTALLA (independientes del zoom)
    CLOSE_THRESHOLD = 10   # distancia para "clic sobre el primer ancla"
    DRAG_THRESHOLD = 3     # minimo arrastre para distinguir clic de arrastre
    ANCHOR_HIT = 9         # radio de agarre de un ancla
    HANDLE_HIT = 9         # radio de agarre de un tirador
    SEGMENT_HIT = 6        # radio para insertar ancla sobre la curva

    def __init__(self, canvas):
        super().__init__(canvas)
        self.tool_id = "pen_path"
        self.anchors = []          # lista de {'pt','in','out','smooth'}
        self.closed = False
        self.stroke_color = canvas.brush_color
        self.fill_color = canvas.brush_color_secondary
        self._cursor_pt = None
        self._cursor_near_first = False
        self._press_pt = None
        self._press_index = None
        self._finishing = False
        # --- edicion en vivo ---
        self._drag = None          # ('new'|'anchor'|'close', i) | ('handle', i, lado)
        self._moved = False        # se ha superado el umbral de arrastre?
        self._press_logical = None # posicion logica al pulsar (delta y clic/arrastre)
        self._orig = None          # copia del ancla al empezar a moverla
        self._hover = None         # ('anchor', i) | ('handle', i, lado) | None
        self._insert_hover = None  # (prev_i, cur_i, t, QPointF) sobre la curva

    # ---------------------------------------------------------------- raton
    def mouse_press(self, event):
        if event.button() not in (Qt.LeftButton, Qt.RightButton):
            return
        pt = self._logical(event)

        # El primer punto fija los colores (izq = contorno primario / relleno
        # secundario; der = al reves, como en rectangulo y elipse).
        if not self.anchors:
            if event.button() == Qt.LeftButton:
                self.stroke_color = self.canvas.brush_color
                self.fill_color = self.canvas.brush_color_secondary
            else:
                self.stroke_color = self.canvas.brush_color_secondary
                self.fill_color = self.canvas.brush_color

        # Prioridad de agarre: tirador > ancla > espacio vacio
        hh = self._hit_handle(pt)
        if hh is not None:
            self._drag = ('handle', hh[0], hh[1])
            self._moved = False
            self._press_logical = QPointF(pt)
            self.canvas.update()
            return

        ai = self._hit_anchor(pt)
        if ai is not None:
            # Primer ancla, trazo abierto y con >=2 puntos -> posible CIERRE
            # (si no se arrastra). Si se arrastra, mueve ese ancla.
            if ai == 0 and len(self.anchors) >= 2 and not self.closed:
                self._drag = ('close', 0)
            else:
                self._drag = ('anchor', ai)
            a = self.anchors[ai]
            self._orig = {'pt': QPointF(a['pt']), 'in': QPointF(a['in']),
                          'out': QPointF(a['out'])}
            self._moved = False
            self._press_logical = QPointF(pt)
            self.canvas.update()
            return

        # Clic sobre un SEGMENTO (no sobre ancla/tirador) -> insertar ancla
        # subdividiendo la curva sin alterar su forma (De Casteljau).
        seg = self._hit_segment(pt)
        if seg is not None:
            ni = self._insert_at_segment(seg[0], seg[1], seg[2])
            a = self.anchors[ni]
            self._drag = ('anchor', ni)
            self._orig = {'pt': QPointF(a['pt']), 'in': QPointF(a['in']),
                          'out': QPointF(a['out'])}
            self._moved = False
            self._press_logical = QPointF(pt)
            self._insert_hover = None
            self.canvas.update()
            return

        # Trazo ya cerrado: no se anaden mas puntos (solo se editan)
        if self.closed:
            self.canvas.update()
            return

        # Espacio vacio -> nuevo ancla (esquina; si se arrastra, se hace suave)
        self.anchors.append({'pt': QPointF(pt), 'in': QPointF(pt),
                             'out': QPointF(pt), 'smooth': False})
        self._drag = ('new', len(self.anchors) - 1)
        self._press_pt = QPointF(pt)
        self._press_index = len(self.anchors) - 1
        self._press_logical = QPointF(pt)
        self._moved = False
        self.canvas.update()

    def mouse_move(self, event):
        pt = self._logical(event)
        self._cursor_pt = QPointF(pt)
        self._cursor_near_first = (len(self.anchors) >= 2 and not self.closed
                                   and self._near_first(pt))

        dragging = (bool(event.buttons() & (Qt.LeftButton | Qt.RightButton))
                    and self._drag is not None)
        if not dragging:
            # Sin arrastrar: realce de lo que hay bajo el cursor; si no hay
            # ancla ni tirador, comprobar si el cursor esta sobre la curva.
            hh = self._hit_handle(pt)
            if hh is not None:
                self._hover = ('handle', hh[0], hh[1]); self._insert_hover = None
            else:
                ai = self._hit_anchor(pt)
                if ai is not None:
                    self._hover = ('anchor', ai); self._insert_hover = None
                else:
                    self._hover = None
                    self._insert_hover = self._hit_segment(pt)
            self.canvas.update()
            return

        # Se ha superado el umbral para considerar 'arrastre'?
        if self._dist_screen(pt, self._press_logical) >= self.DRAG_THRESHOLD:
            self._moved = True

        kind = self._drag[0]
        if kind == 'new':
            if self._moved:
                a = self.anchors[self._drag[1]]
                a['smooth'] = True
                dx = pt.x() - self._press_pt.x()
                dy = pt.y() - self._press_pt.y()
                a['out'] = QPointF(self._press_pt.x() + dx, self._press_pt.y() + dy)
                a['in'] = QPointF(self._press_pt.x() - dx, self._press_pt.y() - dy)
        elif kind in ('anchor', 'close'):
            if self._moved:
                a = self.anchors[self._drag[1]]
                o = self._orig
                if event.modifiers() & Qt.AltModifier:
                    # Alt + arrastrar un ancla: saca/curva sus tiradores (la
                    # convierte en suave). El ancla en si no se mueve.
                    a['smooth'] = True
                    a['pt'] = QPointF(o['pt'])
                    a['out'] = QPointF(pt)
                    a['in'] = QPointF(2 * o['pt'].x() - pt.x(),
                                      2 * o['pt'].y() - pt.y())
                else:
                    # Mover el ancla con sus tiradores
                    dx = pt.x() - self._press_logical.x()
                    dy = pt.y() - self._press_logical.y()
                    a['pt'] = QPointF(o['pt'].x() + dx, o['pt'].y() + dy)
                    a['in'] = QPointF(o['in'].x() + dx, o['in'].y() + dy)
                    a['out'] = QPointF(o['out'].x() + dx, o['out'].y() + dy)
        elif kind == 'handle':
            i, which = self._drag[1], self._drag[2]
            a = self.anchors[i]
            a['smooth'] = True
            a[which] = QPointF(pt)
            # Simetria: el tirador opuesto se refleja (con Alt se rompe -> pico)
            if not (event.modifiers() & Qt.AltModifier):
                other = 'in' if which == 'out' else 'out'
                a[other] = QPointF(2 * a['pt'].x() - pt.x(),
                                   2 * a['pt'].y() - pt.y())
        self.canvas.update()

    def mouse_release(self, event):
        if self._drag is not None and not self._moved:
            kind = self._drag[0]
            alt = bool(event.modifiers() & Qt.AltModifier)
            if kind == 'close' and not alt:
                # Clic (sin arrastre) sobre el primer ancla -> cerrar el trazo
                self.closed = True
            elif kind in ('anchor', 'close') and alt:
                # Alt + clic (sin arrastre) en un ancla suave -> volverla esquina
                a = self.anchors[self._drag[1]]
                if a['smooth']:
                    a['smooth'] = False
                    a['in'] = QPointF(a['pt'])
                    a['out'] = QPointF(a['pt'])
        self._drag = None
        self._orig = None
        self._press_pt = None
        self._press_index = None
        self._moved = False
        self.canvas.update()

    def mouse_double_click(self, event):
        # El doble clic confirma el trazo (equivalente a Enter).
        self.finish_editing()

    # -------------------------------------------------------------- teclado
    def key_press(self, event):
        k = event.key()
        if k in (Qt.Key_Return, Qt.Key_Enter):
            self.finish_editing()
            return True
        if k == Qt.Key_Escape:
            self._clear()
            self.canvas.update()
            return True
        if k == Qt.Key_Backspace:
            if self.anchors:
                self.anchors.pop()
                self._press_index = None
                self._drag = None
                self._hover = None
                if len(self.anchors) < 2:
                    self.closed = False
            self.canvas.update()
            return True
        if k == Qt.Key_Delete:
            idx = self._hover[1] if (self._hover and self._hover[0] == 'anchor') else None
            if idx is not None:
                self.anchors.pop(idx)
                self._hover = None
                self._drag = None
                self._insert_hover = None
                if len(self.anchors) < 2:
                    self.closed = False
                self.canvas.update()
            return True
        return False

    # ------------------------------------------------------------ confirmar
    def finish_editing(self):
        """Confirma el trazo segun el modo de salida (canvas.pen_path_output):
        'stroke' = solo contorno, 'fill' = contorno + relleno del area cerrada,
        'selection' = convierte el area cerrada en seleccion (no pinta).
        Lo llama set_tool al cambiar de herramienta, Enter y el doble clic."""
        if self._finishing:
            return
        self._finishing = True
        try:
            mode = getattr(self.canvas, 'pen_path_output', 'stroke')
            if mode == 'selection':
                if len(self.anchors) >= 3:   # hace falta area para seleccionar
                    self._make_selection()
            elif len(self.anchors) >= 2:
                self._rasterize(fill=(mode == 'fill'))
        finally:
            self._clear()
            self._finishing = False
            self.canvas.update()

    def _rasterize(self, fill=False):
        # En modo relleno cerramos el contorno aunque no se cerrara a mano
        path = self._build_path(force_close=fill)
        # 🎭 Destino: máscara (en modo edición de máscara) o píxeles de la
        # capa, como el resto de herramientas de pintura (paint_target).
        on_mask = self.canvas.paint_on_mask()
        active_layer = self.canvas.paint_target()
        before = QImage(active_layer)

        painter = QPainter(active_layer)
        painter.setRenderHint(QPainter.Antialiasing)
        self.canvas.apply_selection_clip(painter)   # respetar seleccion
        if fill:
            # Relleno con el color opuesto al del contorno, usando el patron
            # elegido en el panel de la pluma (liso por defecto).
            fcol = getattr(self, 'fill_color', self.canvas.brush_color_secondary)
            pat = getattr(self.canvas, 'pen_path_fill_pattern', None)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(fcol, pat) if pat is not None else QBrush(fcol))
            painter.drawPath(path)
        style = getattr(self.canvas, 'pen_path_line_style', Qt.SolidLine)
        pen = QPen(getattr(self, 'stroke_color', self.canvas.brush_color),
                   self.canvas.brush_size, style, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
        painter.end()

        after = QImage(active_layer)
        pad = float(self.canvas.brush_size) / 2.0 + 2.0
        dirty = path.boundingRect().adjusted(
            -pad, -pad, pad, pad).toAlignedRect()
        self.canvas.undo_stack.push(PaintCommand(
            self.canvas, self.canvas.active_layer_index, before, after,
            t("hist.pen_path"), tool_id="pen_path",
            target=("mask" if on_mask else "image"), confine=True,
            dirty_rect=dirty))

    def _make_selection(self):
        """Convierte el trazo (cerrado) en seleccion, integrandolo con todo
        el sistema (mover, recortar, copiar, ajustes...). Reemplaza la
        seleccion actual."""
        path = self._build_path(force_close=True)
        if path.isEmpty():
            return
        prev = self.canvas.selection
        self.canvas.undo_stack.push(SelectionChangeCommand(
            self.canvas, prev, path, t("hist.pen_path_sel")))

    # --------------------------------------------------------------- previa
    def draw_preview(self, painter):
        if not self.anchors:
            return
        z = self.canvas.zoom_factor
        import theme
        blue = QColor(theme.ACCENT)   # azul de acento del tema (no hardcodeado)
        white = QColor(255, 255, 255)

        # 1) Geometria del trazado en azul fino (pen cosmetico = 1px en pantalla)
        path = self._build_path()
        pen_path = QPen(blue)
        pen_path.setWidth(0)
        painter.setPen(pen_path)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)

        # 2) Banda elastica del ultimo ancla al cursor (solo si esta abierto,
        #    creando, y sin estar sobre un elemento que se vaya a editar)
        if (self._cursor_pt is not None and not self.closed
                and self._drag is None and self._hover is None):
            rubber = QPen(blue)
            rubber.setWidth(0)
            rubber.setStyle(Qt.DashLine)
            painter.setPen(rubber)
            painter.drawLine(self.anchors[-1]['pt'], self._cursor_pt)

        # 3) Tiradores de los puntos suaves (linea + punta; punta mayor si hover)
        r = 3.0 / z
        for idx, a in enumerate(self.anchors):
            if a['smooth']:
                hp = QPen(blue)
                hp.setWidth(0)
                painter.setPen(hp)
                painter.setBrush(Qt.NoBrush)
                painter.drawLine(a['pt'], a['in'])
                painter.drawLine(a['pt'], a['out'])
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(blue))
                for which in ('in', 'out'):
                    hovered = (self._hover == ('handle', idx, which))
                    rr = (r * 1.7) if hovered else r
                    painter.drawEllipse(a[which], rr, rr)

        # 4) Anclas: cuadradito (relleno azul si esta bajo el cursor)
        half = 3.5 / z
        for idx, a in enumerate(self.anchors):
            hovered = (self._hover == ('anchor', idx))
            painter.setPen(QPen(blue, 0))
            painter.setBrush(QBrush(blue if hovered else white))
            p = a['pt']
            painter.drawRect(QRectF(p.x() - half, p.y() - half, 2 * half, 2 * half))

        # 5) Indicador de cierre sobre el primer ancla
        if self._cursor_near_first and len(self.anchors) >= 2:
            painter.setPen(QPen(blue, 0))
            painter.setBrush(Qt.NoBrush)
            rr = 6.0 / z
            f = self.anchors[0]['pt']
            painter.drawEllipse(f, rr, rr)

        # 6) Resalte del punto de insercion (cursor sobre la curva)
        if self._insert_hover is not None and self._drag is None:
            ip = self._insert_hover[3]
            rr = 4.0 / z
            painter.setPen(QPen(blue, 0))
            painter.setBrush(QBrush(white))
            painter.drawEllipse(ip, rr, rr)
            painter.setPen(QPen(blue, 0))
            painter.drawLine(QPointF(ip.x() - rr * 0.6, ip.y()), QPointF(ip.x() + rr * 0.6, ip.y()))
            painter.drawLine(QPointF(ip.x(), ip.y() - rr * 0.6), QPointF(ip.x(), ip.y() + rr * 0.6))

    # --------------------------------------------------------------- helpers
    def _logical(self, event):
        """Coordenadas del pixel BAJO el cursor, enganchadas a la rejilla.
        floor (celda real, sin desfase de medio pixel al ampliar) + 0,5 para
        caer en el CENTRO de ese pixel: asi el trazo rasterizado pasa por el
        pixel que has pulsado y sale nitido, no a caballo entre dos filas."""
        import math
        pos = event.position() / self.canvas.zoom_factor
        return QPointF(math.floor(pos.x()) + 0.5, math.floor(pos.y()) + 0.5)

    def _near_first(self, pt):
        if not self.anchors:
            return False
        f = self.anchors[0]['pt']
        d = ((pt.x() - f.x()) ** 2 + (pt.y() - f.y()) ** 2) ** 0.5
        return d * self.canvas.zoom_factor <= self.CLOSE_THRESHOLD

    def _dist_screen(self, a, b):
        """Distancia entre dos puntos logicos, medida en pixeles de pantalla."""
        return (((a.x() - b.x()) ** 2 + (a.y() - b.y()) ** 2) ** 0.5
                * self.canvas.zoom_factor)

    def _hit_handle(self, pt):
        """(indice, lado) del tirador bajo 'pt', o None. Solo los puntos suaves
        tienen tiradores. Devuelve el mas cercano dentro del radio de agarre."""
        best = None
        bestd = self.HANDLE_HIT
        for i, a in enumerate(self.anchors):
            if not a['smooth']:
                continue
            for which in ('in', 'out'):
                d = self._dist_screen(pt, a[which])
                if d <= bestd:
                    bestd = d
                    best = (i, which)
        return best

    def _hit_anchor(self, pt):
        """Indice del ancla bajo 'pt' (la mas cercana dentro del radio), o None."""
        best = None
        bestd = self.ANCHOR_HIT
        for i, a in enumerate(self.anchors):
            d = self._dist_screen(pt, a['pt'])
            if d <= bestd:
                bestd = d
                best = i
        return best

    @staticmethod
    def _cubic_point(p0, p1, p2, p3, t):
        u = 1 - t
        x = u*u*u*p0.x() + 3*u*u*t*p1.x() + 3*u*t*t*p2.x() + t*t*t*p3.x()
        y = u*u*u*p0.y() + 3*u*u*t*p1.y() + 3*u*t*t*p2.y() + t*t*t*p3.y()
        return QPointF(x, y)

    def _segments(self):
        # (prev_i, cur_i) de cada segmento, incluido el de cierre si esta cerrado
        segs = [(i - 1, i) for i in range(1, len(self.anchors))]
        if self.closed and len(self.anchors) >= 2:
            segs.append((len(self.anchors) - 1, 0))
        return segs

    def _hit_segment(self, pt):
        # Punto de la curva mas cercano al cursor dentro del radio de agarre.
        # Devuelve (prev_i, cur_i, t, punto) o None.
        best = None
        bestd = self.SEGMENT_HIT
        N = 24
        for prev_i, cur_i in self._segments():
            a = self.anchors[prev_i]; b = self.anchors[cur_i]
            for j in range(N + 1):
                t = j / N
                cp = self._cubic_point(a['pt'], a['out'], b['in'], b['pt'], t)
                d = self._dist_screen(pt, cp)
                if d < bestd:
                    bestd = d
                    best = (prev_i, cur_i, t, cp)
        return best

    def _insert_at_segment(self, prev_i, cur_i, t):
        # Inserta un ancla subdividiendo el segmento con De Casteljau (la forma
        # no cambia). Devuelve el indice del nuevo ancla.
        def lerp(p, q):
            return QPointF(p.x() + (q.x() - p.x()) * t, p.y() + (q.y() - p.y()) * t)
        prev = self.anchors[prev_i]; cur = self.anchors[cur_i]
        P0, P1, P2, P3 = prev['pt'], prev['out'], cur['in'], cur['pt']
        A = lerp(P0, P1); B = lerp(P1, P2); C = lerp(P2, P3)
        D = lerp(A, B); E = lerp(B, C); F = lerp(D, E)
        straight = (not prev['smooth']) and (not cur['smooth'])
        if straight:
            new = {'pt': F, 'in': QPointF(F), 'out': QPointF(F), 'smooth': False}
        else:
            prev['out'] = A
            cur['in'] = C
            new = {'pt': F, 'in': D, 'out': E, 'smooth': True}
        insert_pos = cur_i if cur_i > prev_i else len(self.anchors)
        self.anchors.insert(insert_pos, new)
        return insert_pos

    def _build_path(self, force_close=False):
        path = QPainterPath()
        if not self.anchors:
            return path
        path.moveTo(self.anchors[0]['pt'])
        for i in range(1, len(self.anchors)):
            prev, cur = self.anchors[i - 1], self.anchors[i]
            path.cubicTo(prev['out'], cur['in'], cur['pt'])
        if (self.closed or force_close) and len(self.anchors) >= 2:
            last, first = self.anchors[-1], self.anchors[0]
            path.cubicTo(last['out'], first['in'], first['pt'])
            path.closeSubpath()
        return path

    def _clear(self):
        self.anchors = []
        self.closed = False
        self._cursor_pt = None
        self._cursor_near_first = False
        self._press_pt = None
        self._press_index = None
        self._drag = None
        self._orig = None
        self._moved = False
        self._hover = None
        self._insert_hover = None
