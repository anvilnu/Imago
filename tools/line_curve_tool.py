# tools/line_curve_tool.py
import math
from i18n import t
from PySide6.QtGui import (QPainter, QPen, QColor, QBrush, QImage,
                           QPainterPath, QPolygonF)
from PySide6.QtCore import Qt, QPointF, QRectF
from tools.base_tool import BaseTool
from tools.commands import PaintCommand


class LineCurveTool(BaseTool):
    """Herramienta Línea / Curva (estilo Paint.NET).

    1) Dibujo: arrastrar traza una línea recta elástica (Shift = ángulos de 15°).
    2) Edición: al soltar, la línea queda FLOTANTE con 4 nudos equiespaciados;
       arrastrar cualquiera la deforma según el modo del panel
       (canvas.line_curve_mode):
         - 'spline': la curva PASA por los 4 nudos (Catmull-Rom).
         - 'bezier': los 2 nudos interiores son puntos de CONTROL Bézier.
         - 'direct': segmentos rectos articulados (polilínea).
       Además, un ASA central (cuadrado con flechas) mueve la línea ENTERA, y
       arrastrar con el BOTÓN DERECHO la GIRA alrededor de su centro (Shift =
       pasos de 15°), como en Paint.NET. El modo, el grosor, el estilo y el
       color pueden cambiarse EN VIVO desde el panel.
    3) Confirmar: Enter, clic izquierdo fuera de los nudos (y empieza otra
       línea) o cambiar de herramienta. Cancelar: Esc.

    Izquierdo = contorno con el color primario; derecho = con el secundario.
    Mientras flota, se recompone sobre la capa partiendo de image_before (mismo
    patrón que ShapeTool) y al confirmar se consolida con un PaintCommand."""

    NODE_HIT = 9              # radio de agarre de un nudo (px de PANTALLA)
    HANDLE_SCREEN_SIZE = 7    # lado del cuadradito de los nudos (px de pantalla)
    MOVE_HANDLE_SIZE = 14     # lado del asa de mover (px de pantalla)
    MOVE_HANDLE_HIT = 11      # radio de agarre del asa de mover (px de pantalla)
    MOVE_HANDLE_OFFSET = 30   # separación del asa respecto a la línea (px pantalla)
    MIN_LEN_SCREEN = 3        # arrastre mínimo para que cuente como línea

    def __init__(self, canvas):
        super().__init__(canvas)
        self.tool_id = "line_curve"
        # Dibujo inicial (recta elástica)
        self.start_point = None
        self.current_point = None
        # Edición (línea flotante con nudos)
        self.editing = False
        self.nodes = []            # 4 QPointF: extremos + 2 interiores
        self.image_before = None
        self._on_mask = False      # 🎭 True si se pinta sobre la máscara
        self.stroke_color = canvas.brush_color
        self._used_left_button = True
        self._gesture = None       # ('node', i) | ('move',) | ('rotate',) | None
        self._hover = None         # ('node', i) | ('move',) | None
        self._press_pt = None      # posición lógica al iniciar el gesto
        self._orig_nodes = None    # copia de los nudos al iniciar el gesto
        self._rot_center = None    # centro de giro (centroide al pulsar)
        self._press_angle = 0.0    # ángulo ratón-centro al pulsar (radianes)
        self._last_margins = None  # última petición de márgenes (evita relayouts)
        self._written_img = None   # QImage escrito por el último _recompose
        self._finishing = False

    # ---------------------------------------------------------------- puntos
    def _logical(self, event):
        """Centro del píxel bajo el cursor (floor + 0,5), como la Pluma: el
        trazo pasa por el píxel pulsado y sale nítido, no entre dos filas."""
        pos = event.position() / self.canvas.zoom_factor
        return QPointF(math.floor(pos.x()) + 0.5, math.floor(pos.y()) + 0.5)

    def _snap(self, p):
        """Imanta el punto a las guías cercanas (si las hay)."""
        return QPointF(self.canvas.snap_x(p.x()), self.canvas.snap_y(p.y()))

    @staticmethod
    def _constrain_angle(start, cur):
        """Shift: fuerza la recta a ángulos múltiplos de 15° (como Paint.NET)."""
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
        """Distancia entre dos puntos lógicos, en píxeles de PANTALLA."""
        return math.hypot(a.x() - b.x(), a.y() - b.y()) * self.canvas.zoom_factor

    def _hit_node(self, p):
        """Índice del nudo bajo 'p' (el más cercano dentro del radio), o None."""
        best = None
        bestd = self.NODE_HIT
        for i, nd in enumerate(self.nodes):
            d = self._dist_screen(p, nd)
            if d <= bestd:
                bestd = d
                best = i
        return best

    def _centroid(self):
        """Centro de la línea (media de los 4 nudos): ancla del asa de mover
        y del giro con el botón derecho."""
        cx = sum(nd.x() for nd in self.nodes) / len(self.nodes)
        cy = sum(nd.y() for nd in self.nodes) / len(self.nodes)
        return QPointF(cx, cy)

    def _move_handle_pos(self):
        """Posición del asa de mover: SEPARADA de la línea (perpendicular a la
        dirección extremo-extremo, hacia abajo, o a la derecha si la línea es
        vertical), para no estorbar sobre líneas cortas."""
        c = self._centroid()
        dx = self.nodes[3].x() - self.nodes[0].x()
        dy = self.nodes[3].y() - self.nodes[0].y()
        largo = math.hypot(dx, dy)
        if largo < 1e-6:
            px, py = 0.0, 1.0
        else:
            px, py = -dy / largo, dx / largo
            if py < 0 or (abs(py) < 1e-9 and px < 0):
                px, py = -px, -py
        off = self.MOVE_HANDLE_OFFSET / max(self.canvas.zoom_factor, 0.0001)
        return QPointF(c.x() + px * off, c.y() + py * off)

    def _zone_at(self, p):
        """Qué hay bajo 'p' en modo edición: ('node', i) | ('move',) | None.
        Los nudos tienen prioridad sobre el asa de mover."""
        idx = self._hit_node(p)
        if idx is not None:
            return ('node', idx)
        if self._dist_screen(p, self._move_handle_pos()) <= self.MOVE_HANDLE_HIT:
            return ('move',)
        return None

    # ---------------------------------------------------------------- ratón
    def mouse_press(self, event):
        if event.button() not in (Qt.LeftButton, Qt.RightButton):
            return
        p = self._snap(self._logical(event))

        # 🛡️ Si la capa cambió por FUERA con la línea viva (deshacer desde el
        # panel de historial...), su estado es obsoleto: se descarta sin
        # escribir, para no resucitar contenido ya deshecho.
        if self.editing and self._externally_modified():
            self._end_edit()

        if self.editing:
            if event.button() == Qt.RightButton:
                # Botón derecho: GIRAR la línea entera alrededor de su centro
                self._gesture = ('rotate',)
                self._rot_center = self._centroid()
                self._orig_nodes = [QPointF(nd) for nd in self.nodes]
                self._press_angle = math.atan2(p.y() - self._rot_center.y(),
                                               p.x() - self._rot_center.x())
                return
            zone = self._zone_at(p)
            if zone is not None:
                self._gesture = zone
                self._press_pt = QPointF(p)
                self._orig_nodes = [QPointF(nd) for nd in self.nodes]
                return
            # Clic izquierdo fuera: confirmar y empezar otra línea desde aquí
            self.finish_editing()

        self.stroke_color = (self.canvas.brush_color
                             if event.button() == Qt.LeftButton
                             else self.canvas.brush_color_secondary)
        self._used_left_button = (event.button() == Qt.LeftButton)
        self.start_point = p
        self.current_point = QPointF(p)
        # 🎭 Destino fijado al empezar: máscara o píxeles de la capa
        self._on_mask = self.canvas.paint_on_mask()
        self.image_before = QImage(self._read_target())
        self.canvas.update()

    def mouse_move(self, event):
        p = self._snap(self._logical(event))
        dragging = bool(event.buttons() & (Qt.LeftButton | Qt.RightButton))

        if self.editing:
            if self._externally_modified():
                self._end_edit()   # la capa cambió por fuera: línea obsoleta
                return
            if dragging and self._gesture is not None:
                self._update_gesture(p, event.modifiers())
            elif not dragging:
                zone = self._zone_at(p)
                if zone != self._hover:
                    self._hover = zone
                    self.canvas.update()
                if zone is None:
                    self.canvas.setCursor(Qt.CrossCursor)
                elif zone[0] == 'move':
                    self.canvas.setCursor(Qt.SizeAllCursor)
                else:
                    self.canvas.setCursor(Qt.PointingHandCursor)
            return

        if dragging and self.start_point is not None:
            if event.modifiers() & Qt.ShiftModifier:
                self.current_point = self._constrain_angle(self.start_point, p)
            else:
                self.current_point = p
            self.canvas.update()

    def _update_gesture(self, p, modifiers):
        """Aplica el gesto en curso (nudo, mover o girar) y recompone en vivo.
        Los márgenes de vista se amplían DURANTE el arrastre para que los
        nudos que salen del lienzo sigan visibles y agarrables."""
        kind = self._gesture[0]
        if kind == 'node':
            self.nodes[self._gesture[1]] = QPointF(p)
        elif kind == 'move':
            dx = p.x() - self._press_pt.x()
            dy = p.y() - self._press_pt.y()
            self.nodes = [QPointF(o.x() + dx, o.y() + dy)
                          for o in self._orig_nodes]
        elif kind == 'rotate':
            c = self._rot_center
            ang = math.atan2(p.y() - c.y(), p.x() - c.x()) - self._press_angle
            if modifiers & Qt.ShiftModifier:
                paso = math.radians(15.0)
                ang = round(ang / paso) * paso
            cos_a, sin_a = math.cos(ang), math.sin(ang)
            self.nodes = [QPointF(c.x() + (o.x() - c.x()) * cos_a
                                  - (o.y() - c.y()) * sin_a,
                                  c.y() + (o.x() - c.x()) * sin_a
                                  + (o.y() - c.y()) * cos_a)
                          for o in self._orig_nodes]
        self._recompose()
        self._update_view_margins()

    def mouse_release(self, event):
        if self.editing:
            if self._gesture is not None:
                self._gesture = None
                self._press_pt = None
                self._orig_nodes = None
                self._rot_center = None
                self._update_view_margins()
                self.canvas.update()
            return
        if self.start_point is not None and event.button() in (Qt.LeftButton, Qt.RightButton):
            if event.modifiers() & Qt.ShiftModifier:
                self.current_point = self._constrain_angle(
                    self.start_point, self._snap(self._logical(event)))
            else:
                self.current_point = self._snap(self._logical(event))
            self._enter_edit_mode()

    # ------------------------------------------- entrada/salida de la edición
    def _enter_edit_mode(self):
        a, b = self.start_point, self.current_point
        self.start_point = None
        self.current_point = None
        if a is None or b is None or self._dist_screen(a, b) < self.MIN_LEN_SCREEN:
            # Arrastre demasiado corto: no hay línea (la capa sigue intacta)
            self.image_before = None
            self.canvas.update()
            return
        # 4 nudos equiespaciados sobre la recta (extremos + 1/3 y 2/3)
        self.nodes = [QPointF(a),
                      QPointF(a.x() + (b.x() - a.x()) / 3.0,
                              a.y() + (b.y() - a.y()) / 3.0),
                      QPointF(a.x() + (b.x() - a.x()) * 2.0 / 3.0,
                              a.y() + (b.y() - a.y()) * 2.0 / 3.0),
                      QPointF(b)]
        self.editing = True
        self._gesture = None
        self._hover = None
        self._recompose()
        self._update_view_margins()

    def finish_editing(self):
        """Consolida la línea como comando deshacible y cierra la edición.
        La llama también set_tool al cambiar de herramienta."""
        if not self.editing or self._finishing:
            return
        if self._externally_modified():
            # La pila cambió con la línea viva: descartarla sin escribir NI
            # apilar (recomponer resucitaría contenido ya deshecho).
            self._end_edit()
            return
        self._finishing = True
        try:
            self._recompose()
            image_after = QImage(self._read_target())
            path = self._build_path()
            pad = max(float(self.canvas.brush_size) / 2.0 + 2.0,
                      self._cap_width() * 3.0 + 2.0)
            dirty = path.boundingRect().adjusted(
                -pad, -pad, pad, pad).toAlignedRect()
            self.canvas.undo_stack.push(PaintCommand(
                self.canvas, self.canvas.active_layer_index,
                self.image_before, image_after, t("hist.line_curve"),
                tool_id=self.tool_id,
                target=("mask" if self._on_mask else "image"), confine=True,
                dirty_rect=dirty))
        finally:
            self._end_edit()
            self._finishing = False

    def _cancel_edit(self):
        if not self.editing:
            return
        if not self._externally_modified():
            self._write_target(QImage(self.image_before))
        self._end_edit()

    def _externally_modified(self):
        """True si la capa cambió por FUERA mientras la línea flota (deshacer/
        rehacer, salto en el panel de historial...). Basta comparar IDENTIDAD:
        el undo/redo de los comandos REEMPLAZA el objeto layer.image (invariante
        del proyecto), así que si el destino ya no es lo último que escribimos,
        alguien más tocó la capa e image_before está obsoleto."""
        return (self._written_img is not None
                and self._read_target() is not self._written_img)

    def _end_edit(self):
        self.editing = False
        self.nodes = []
        self.image_before = None
        self._gesture = None
        self._hover = None
        self._press_pt = None
        self._orig_nodes = None
        self._rot_center = None
        self._last_margins = None
        self._written_img = None
        self.canvas.reset_view_margins()
        self.canvas.setCursor(Qt.CrossCursor)
        self.canvas.update()

    # -------------------------------------------------------------- destino
    def _read_target(self):
        """Imagen destino actual (máscara o píxeles de la capa activa)."""
        layer = self.canvas.layers[self.canvas.active_layer_index]
        return layer.mask if self._on_mask else layer.image

    def _write_target(self, img):
        """Escribe el resultado en la máscara o en los píxeles de la capa."""
        layer = self.canvas.layers[self.canvas.active_layer_index]
        if self._on_mask:
            layer.mask = img
        else:
            layer.image = img

    # -------------------------------------------------------------- teclado
    def key_press(self, event):
        if not self.editing:
            return False
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.finish_editing()
            return True
        if event.key() == Qt.Key_Escape:
            self._cancel_edit()
            return True
        return False

    # ------------------------------------------------------------- geometría
    def _mode(self):
        return getattr(self.canvas, 'line_curve_mode', 'spline')

    def _build_path(self):
        """QPainterPath de la línea según el modo de curvado activo."""
        path = QPainterPath()
        n = self.nodes
        if len(n) < 4:
            return path
        mode = self._mode()
        path.moveTo(n[0])
        if mode == 'bezier':
            # Los nudos interiores son puntos de control (no se pasa por ellos)
            path.cubicTo(n[1], n[2], n[3])
        elif mode == 'direct':
            # Segmentos rectos articulados (polilínea)
            path.lineTo(n[1])
            path.lineTo(n[2])
            path.lineTo(n[3])
        else:
            # Spline Catmull-Rom: pasa por los 4 nudos (extremos duplicados
            # como tangentes de borde), convertida a Béziers cúbicas.
            pts = [n[0]] + n + [n[3]]
            for i in range(1, 4):
                p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
                c1 = QPointF(p1.x() + (p2.x() - p0.x()) / 6.0,
                             p1.y() + (p2.y() - p0.y()) / 6.0)
                c2 = QPointF(p2.x() - (p3.x() - p1.x()) / 6.0,
                             p2.y() - (p3.y() - p1.y()) / 6.0)
                path.cubicTo(c1, c2, p2)
        return path

    def _make_pen(self):
        style = getattr(self.canvas, 'line_curve_style', Qt.SolidLine)
        return QPen(self.stroke_color, self.canvas.brush_size, style,
                    Qt.RoundCap, Qt.RoundJoin)

    # ------------------------------------------------ terminaciones (puntas)
    def _cap_width(self):
        """Grosor base de las puntas: canvas.line_curve_cap_size en px, o el
        grosor de la línea si vale 0 ('Auto', el valor por defecto)."""
        w = float(getattr(self.canvas, 'line_curve_cap_size', 0) or 0)
        if w <= 0:
            w = float(self.canvas.brush_size)
        return max(1.0, w)

    def _draw_caps(self, painter, path):
        """Dibuja la terminación de cada extremo (canvas.line_curve_cap_start /
        line_curve_cap_end: 'none' | 'arrow' | 'circle' | 'bar'), orientada con
        la TANGENTE real del trazado (angleAtPercent) y escalada con el tamaño
        de punta (o el grosor de la línea en 'Auto')."""
        if path.isEmpty() or path.length() < 1e-3:
            return
        w = self._cap_width()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(self.stroke_color))
        # angleAtPercent da grados antihorarios (eje Y hacia arriba): en
        # coordenadas de pantalla el ángulo se niega. 'giro' orienta la punta
        # hacia FUERA de la línea en cada extremo.
        for attr, pct, giro in (('line_curve_cap_start', 0.0, math.pi),
                                ('line_curve_cap_end', 1.0, 0.0)):
            forma = getattr(self.canvas, attr, 'none')
            if forma not in ('arrow', 'circle', 'bar'):
                continue
            pos = path.pointAtPercent(pct)
            ang = -math.radians(path.angleAtPercent(pct)) + giro
            if forma == 'arrow':
                painter.drawPolygon(self._arrow_poly(
                    pos, ang, max(6.0, w * 3.0), max(2.5, w * 1.25)))
            elif forma == 'circle':
                r = max(2.5, w * 1.25)
                painter.drawEllipse(pos, r, r)
            else:  # 'bar': barra perpendicular desde el extremo hacia fuera
                semi = max(2.5, w * 1.5)     # semilargo (perpendicular)
                esp = max(2.0, w)            # espesor (a lo largo de la línea)
                cx, cy = math.cos(ang), math.sin(ang)
                px, py = -math.sin(ang), math.cos(ang)
                painter.drawPolygon(QPolygonF([
                    QPointF(pos.x() + px * semi, pos.y() + py * semi),
                    QPointF(pos.x() + cx * esp + px * semi,
                            pos.y() + cy * esp + py * semi),
                    QPointF(pos.x() + cx * esp - px * semi,
                            pos.y() + cy * esp - py * semi),
                    QPointF(pos.x() - px * semi, pos.y() - py * semi)]))

    @staticmethod
    def _arrow_poly(base, ang, largo, semi):
        """Triángulo con la BASE en el extremo de la línea y el vértice hacia
        fuera (la punta alarga la línea, como en Paint.NET; así el remate
        redondo del trazo queda siempre tapado)."""
        tip = QPointF(base.x() + largo * math.cos(ang),
                      base.y() + largo * math.sin(ang))
        px, py = -math.sin(ang), math.cos(ang)
        return QPolygonF([tip,
                          QPointF(base.x() + px * semi, base.y() + py * semi),
                          QPointF(base.x() - px * semi, base.y() - py * semi)])

    # ---------------------------------------------------------------- render
    def refresh_live(self):
        """Llamado al cambiar color, grosor, estilo o modo para refrescar."""
        if not self.editing:
            return
        if self._externally_modified():
            self._end_edit()
            return
        self.stroke_color = (self.canvas.brush_color if self._used_left_button
                             else self.canvas.brush_color_secondary)
        self._recompose()

    def _recompose(self):
        """Redibuja la línea sobre la capa partiendo del estado previo
        (image_before), sin tocar el historial."""
        img = QImage(self.image_before)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing, True)
        self.canvas.apply_selection_clip(p)
        path = self._build_path()
        p.setPen(self._make_pen())
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        self._draw_caps(p, path)
        p.end()
        self._write_target(img)
        self._written_img = img
        self.canvas.update()

    def _update_view_margins(self):
        """Pide márgenes de vista si algún nudo queda fuera del lienzo, para
        que siga VISIBLE y agarrable sobre el fondo oscuro. Se llama también
        DURANTE los gestos (el canvas ya compensa las coordenadas del ratón);
        la caché evita relayouts cuando los márgenes no cambian."""
        if not self.editing:
            self.canvas.reset_view_margins()
            return
        zoom = max(self.canvas.zoom_factor, 0.0001)
        pad = (self.NODE_HIT + self.MOVE_HANDLE_SIZE) / zoom
        asa = self._move_handle_pos()
        xs = [nd.x() for nd in self.nodes] + [asa.x()]
        ys = [nd.y() for nd in self.nodes] + [asa.y()]
        left = max(0, math.ceil(-(min(xs) - pad)))
        top = max(0, math.ceil(-(min(ys) - pad)))
        right = max(0, math.ceil(max(xs) + pad - self.canvas.base_width))
        bottom = max(0, math.ceil(max(ys) + pad - self.canvas.base_height))
        margenes = (left, top, right, bottom)
        if margenes != self._last_margins:
            self._last_margins = margenes
            self.canvas.set_view_margins(*margenes)

    def draw_preview(self, painter):
        import theme
        blue = QColor(theme.ACCENT)   # azul de acento del tema (no hardcodeado)
        z = max(self.canvas.zoom_factor, 0.0001)

        # Dibujando: recta elástica con la pluma real (y sus flechas)
        if not self.editing:
            if self.start_point is not None and self.current_point is not None:
                painter.setRenderHint(QPainter.Antialiasing, True)
                painter.setPen(self._make_pen())
                painter.setBrush(Qt.NoBrush)
                painter.drawLine(self.start_point, self.current_point)
                recta = QPainterPath(self.start_point)
                recta.lineTo(self.current_point)
                self._draw_caps(painter, recta)
            return

        # Edición: la línea ya está pintada en la capa; aquí solo los nudos
        if self._mode() == 'bezier':
            # Guías punteadas extremo -> punto de control (como en la Pluma)
            guide = QPen(blue)
            guide.setWidth(0)
            guide.setStyle(Qt.DashLine)
            painter.setPen(guide)
            painter.drawLine(self.nodes[0], self.nodes[1])
            painter.drawLine(self.nodes[3], self.nodes[2])

        # Asa de MOVER: cuadrado blanco con flechas en cruz, SEPARADO de la
        # línea (arrastrarlo la traslada entera). Los nudos tienen prioridad.
        c = self._move_handle_pos()
        mh = (self.MOVE_HANDLE_SIZE / 2.0) / z
        move_hover = (self._hover == ('move',)
                      or (self._gesture is not None and self._gesture[0] == 'move'))
        painter.setPen(QPen(blue, 0))
        painter.setBrush(QBrush(blue if move_hover else QColor(255, 255, 255)))
        painter.drawRect(QRectF(c.x() - mh, c.y() - mh, 2 * mh, 2 * mh))
        glifo = QPen(QColor(255, 255, 255) if move_hover else blue, 0)
        painter.setPen(glifo)
        a = mh * 0.62      # brazos de la cruz
        f = mh * 0.28      # puntas de flecha
        painter.drawLine(QPointF(c.x() - a, c.y()), QPointF(c.x() + a, c.y()))
        painter.drawLine(QPointF(c.x(), c.y() - a), QPointF(c.x(), c.y() + a))
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            tip = QPointF(c.x() + dx * a, c.y() + dy * a)
            painter.drawLine(tip, QPointF(tip.x() - dx * f + dy * f,
                                          tip.y() - dy * f + dx * f))
            painter.drawLine(tip, QPointF(tip.x() - dx * f - dy * f,
                                          tip.y() - dy * f - dx * f))

        half = (self.HANDLE_SCREEN_SIZE / 2.0) / z
        for i, nd in enumerate(self.nodes):
            hovered = (self._hover == ('node', i) or self._gesture == ('node', i))
            painter.setPen(QPen(blue, 0))
            painter.setBrush(QBrush(blue if hovered else QColor(255, 255, 255)))
            painter.drawRect(QRectF(nd.x() - half, nd.y() - half,
                                    2 * half, 2 * half))
