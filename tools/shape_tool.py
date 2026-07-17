# tools/shape_tool.py
import math
from PySide6.QtGui import (QPainter, QPen, QImage, QBrush, QColor, QTransform,
                           QPainterPath, QPolygonF)
from PySide6.QtCore import Qt, QRect, QRectF, QPoint, QPointF
from i18n import t
from tools.base_tool import BaseTool, best_snap
from tools.commands import PaintCommand
from tools.shape_geometry import build_shape_path, get_shape_name, DEFAULT_SHAPE
from tools import pattern_tiles


class ShapeTool(BaseTool):
    """Herramienta unificada de Formas (vectorial).

    1) Dibujo: arrastrar define el rectángulo de la forma (Shift = 1:1).
    2) Edición: al soltar, la forma queda flotante con una caja de
       transformación idéntica a la de "Mover selección":
         - interior: mover
         - 8 tiradores: escalar (Shift = proporcional en esquinas)
         - corona alrededor: girar (Shift = pasos de 15°)
       Como es vectorial, girar/escalar NO pierde nitidez.
    3) Confirmar: Enter, clic fuera de la caja, o cambiar de herramienta/forma.
       Cancelar: Esc.

    Izquierdo: contorno=primario, relleno=secundario | Derecho: al revés."""

    HANDLE_SCREEN_SIZE = 8
    ROTATE_OFFSET_SCREEN = 28
    ROTATE_RING_SCREEN = 60
    MIN_SCALE = 0.02
    MAX_SCALE = 80.0

    def __init__(self, canvas, shape_id=DEFAULT_SHAPE):
        super().__init__(canvas)
        self.shape_id = shape_id or DEFAULT_SHAPE
        self.tool_id = "shape"
        # Dibujo inicial
        self.start_point = None
        self.current_point = None
        self.image_before = None
        self.fill_color = None
        self._on_mask = False       # 🎭 True si la forma se aplica a la máscara
        # Edición (transformación)
        self.editing = False
        self._base_path = None
        self.fw = 0.0
        self.fh = 0.0
        self.orig_center = QPointF(0, 0)
        self.sx = 1.0
        self.sy = 1.0
        self.angle = 0.0
        self.tx = 0.0
        self.ty = 0.0
        # Gesto en curso
        self.mode = None            # None | 'move' | 'scale' | 'rotate'
        self.active_handle = None
        self.press_canvas = QPointF(0, 0)
        self.press_sx = 1.0
        self.press_sy = 1.0
        self.press_tx = 0.0
        self.press_ty = 0.0
        self.press_angle = 0.0
        self.press_mouse_angle = 0.0
        self.press_obj = QPointF(0, 0)
        self.press_inv = None       # Marco (inverso) FIJADO al iniciar el escalado

    # ==================================================================
    # Utilidades de píxel y cambios de estado
    # ==================================================================

    def _request_update(self, full=False):
        if full:
            self.canvas.update()
            self._last_update_rect = None
            return
        
        zoom = max(self.canvas.zoom_factor, 0.0001)
        if getattr(self, 'editing', False):
            disp = self._display_transform()
            rect = disp.mapRect(QRectF(0, 0, self.fw, self.fh))
        elif getattr(self, 'start_point', None) and getattr(self, 'current_point', None):
            rect = QRectF(self.start_point, self.current_point).normalized()
        else:
            self.canvas.update()
            return

        ml = self.canvas.margin_left + getattr(self.canvas, 'view_margin_left', 0)
        mt = self.canvas.margin_top + getattr(self.canvas, 'view_margin_top', 0)
        
        pad = int(getattr(self.canvas, 'brush_size', 10) * zoom + 80)
        r = QRect(
            int((rect.left() + ml) * zoom),
            int((rect.top() + mt) * zoom),
            int(rect.width() * zoom),
            int(rect.height() * zoom)
        ).adjusted(-pad, -pad, pad, pad)
        
        if getattr(self, '_last_update_rect', None):
            self.canvas.update(self._last_update_rect.united(r))
        else:
            self.canvas.update(r)
        self._last_update_rect = r

    def change_shape(self, new_shape_id):
        self.shape_id = new_shape_id
        if self.editing:
            self._base_path = build_shape_path(self.shape_id, QRectF(0, 0, self.fw, self.fh))
            self._recompose()
            self._request_update()

    def _floor_point(self, event):
        pos = event.position() / self.canvas.zoom_factor
        return QPoint(math.floor(pos.x()), math.floor(pos.y()))

    def _snap(self, pt):
        """Imanta un punto a las guías cercanas (si las hay)."""
        return QPoint(int(round(self.canvas.snap_x(pt.x()))),
                      int(round(self.canvas.snap_y(pt.y()))))

    def constrain_to_square(self, start, current):
        dx = current.x() - start.x()
        dy = current.y() - start.y()
        side = max(abs(dx), abs(dy))
        sx = 1 if dx >= 0 else -1
        sy = 1 if dy >= 0 else -1
        return QPoint(start.x() + side * sx, start.y() + side * sy)

    # ==================================================================
    # RATÓN
    # ==================================================================
    def mouse_press(self, event):
        if event.button() not in (Qt.LeftButton, Qt.RightButton):
            return
        p = QPointF(event.position() / self.canvas.zoom_factor)

        if self.editing:
            zone = self._zone_at(p)
            if zone is not None:
                self._begin_gesture(zone, p)
                return
            # Clic fuera de la caja: confirmar la forma y permitir dibujar otra
            self.finish_editing()

        if event.button() == Qt.LeftButton:
            self.stroke_color = self.canvas.brush_color
            self.fill_color = self.canvas.brush_color_secondary
        else:
            self.stroke_color = self.canvas.brush_color_secondary
            self.fill_color = self.canvas.brush_color
        self._used_left_button = (event.button() == Qt.LeftButton)
        self.start_point = self._snap(self._floor_point(event))
        self.current_point = self.start_point
        # 🎭 Destino de la forma: máscara o píxeles (fijado al empezar a dibujar).
        self._on_mask = self.canvas.paint_on_mask()
        self.image_before = QImage(self._read_target())
        self._request_update()

    def mouse_move(self, event):
        p = QPointF(event.position() / self.canvas.zoom_factor)
        dragging = bool(event.buttons() & (Qt.LeftButton | Qt.RightButton))

        if self.editing:
            if dragging and self.mode:
                self._update_gesture(p, event.modifiers())
            elif not dragging:
                self._update_hover_cursor(p)
            return

        if dragging and self.start_point:
            raw = self._snap(self._floor_point(event))
            if event.modifiers() & Qt.ShiftModifier:
                self.current_point = self.constrain_to_square(self.start_point, raw)
            else:
                self.current_point = raw
            self._request_update()

    def mouse_release(self, event):
        if self.editing:
            if self.mode:
                self.mode = None
                self.active_handle = None
                self._request_update()
            return
        if self.start_point and event.button() in (Qt.LeftButton, Qt.RightButton):
            raw = self._snap(self._floor_point(event))
            if event.modifiers() & Qt.ShiftModifier:
                self.current_point = self.constrain_to_square(self.start_point, raw)
            else:
                self.current_point = raw
            self._enter_edit_mode()

    # ==================================================================
    # Entrada / salida del modo edición
    # ==================================================================
    def _enter_edit_mode(self):
        rect = QRect(self.start_point, self.current_point).normalized()
        self.start_point = None
        self.current_point = None
        if rect.width() < 2 or rect.height() < 2:
            self.image_before = None
            self._request_update()
            return
        self.fw = float(rect.width())
        self.fh = float(rect.height())
        self.orig_center = QPointF(rect.x() + self.fw / 2.0, rect.y() + self.fh / 2.0)
        self._base_path = build_shape_path(self.shape_id, QRectF(0, 0, self.fw, self.fh))
        self.sx = self.sy = 1.0
        self.angle = 0.0
        self.tx = self.ty = 0.0
        self.editing = True
        self._recompose()
        self._update_view_margins()
        self._request_update()

    def finish_editing(self):
        """Consolida la forma como comando deshacible y cierra la edición."""
        if not self.editing:
            return
        self._recompose()
        image_after = QImage(self._read_target())
        name = get_shape_name(self.shape_id) or t("tool.name.shapes")
        pad = float(self.canvas.brush_size) / 2.0 + 2.0
        dirty = self._display_path().boundingRect().adjusted(
            -pad, -pad, pad, pad).toAlignedRect()
        self.canvas.undo_stack.push(PaintCommand(
            self.canvas, self.canvas.active_layer_index,
            self.image_before, image_after, name, tool_id=self.tool_id,
            target=("mask" if self._on_mask else "image"), confine=True,
            dirty_rect=dirty))
        self._end_edit()

    def _cancel_edit(self):
        if not self.editing:
            return
        self._write_target(QImage(self.image_before))
        self._end_edit()

    def _read_target(self):
        """Imagen destino actual (máscara o píxeles de la capa)."""
        layer = self.canvas.layers[self.canvas.active_layer_index]
        return layer.mask if self._on_mask else layer.image

    def _write_target(self, img):
        """Escribe el resultado en la máscara o en los píxeles de la capa."""
        layer = self.canvas.layers[self.canvas.active_layer_index]
        if self._on_mask:
            layer.mask = img
        else:
            layer.image = img

    def _end_edit(self):
        self.editing = False
        self.mode = None
        self.active_handle = None
        self.image_before = None
        self._base_path = None
        self.canvas.reset_view_margins()
        self.canvas.setCursor(Qt.CrossCursor)
        self._request_update()

    # ==================================================================
    # TECLADO: Enter confirma, Esc cancela
    # ==================================================================
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

    # ==================================================================
    # GESTOS DE TRANSFORMACIÓN
    # ==================================================================
    def _begin_gesture(self, zone, p):
        self.press_canvas = p
        self.press_sx, self.press_sy = self.sx, self.sy
        self.press_tx, self.press_ty = self.tx, self.ty
        self.press_angle = self.angle
        if zone == 'rotate':
            self.mode = 'rotate'
            c = self._center()
            self.press_mouse_angle = math.degrees(math.atan2(p.y() - c.y(), p.x() - c.x()))
        elif isinstance(zone, tuple) and zone[0] == 'scale':
            self.mode = 'scale'
            self.active_handle = zone[1]
            inv = self._unrotated_frame()
            self.press_obj = inv.map(p)
            # ⚓ Marco FIJO del gesto: al anclar el lado opuesto, el centro se
            # desplaza durante el arrastre; medir siempre en el marco del press
            # evita que ese desplazamiento realimente la escala.
            self.press_inv = inv
        elif zone == 'move':
            self.mode = 'move'
        else:
            self.mode = None

    def _snap_move_to_guides(self):
        """Imanta los bordes de la forma (en modo edición, al moverla) a las guías.
        Solo con traslación pura sin rotar, para no deformar."""
        c = self.canvas
        if not getattr(c, 'show_guides', False) or not c.guides or self.angle != 0:
            return
        cx = self.orig_center.x() + self.tx
        cy = self.orig_center.y() + self.ty
        hw = abs(self.sx) * self.fw / 2.0
        hh = abs(self.sy) * self.fh / 2.0
        left, right = cx - hw, cx + hw
        top, bottom = cy - hh, cy + hh
        self.tx += best_snap((c.snap_x(left) - left, c.snap_x(right) - right))
        self.ty += best_snap((c.snap_y(top) - top, c.snap_y(bottom) - bottom))

    def _update_gesture(self, p, modifiers):
        shift = bool(modifiers & Qt.ShiftModifier)
        if self.mode == 'move':
            delta = p - self.press_canvas
            self.tx = self.press_tx + delta.x()
            self.ty = self.press_ty + delta.y()
            self._snap_move_to_guides()
        elif self.mode == 'rotate':
            c = self._center()
            ang = math.degrees(math.atan2(p.y() - c.y(), p.x() - c.x()))
            new_angle = self.press_angle + (ang - self.press_mouse_angle)
            if shift:
                new_angle = round(new_angle / 15.0) * 15.0
            self.angle = new_angle
        elif self.mode == 'scale':
            m = self.press_inv.map(p)
            alt = bool(modifiers & Qt.AltModifier)
            self._apply_scale_drag(m, shift, alt)
        self._recompose()
        self._request_update()

    def _apply_scale_drag(self, m, proportional, from_center):
        """Escala respecto a un ANCLA: por defecto el lado/esquina opuesta al
        tirador queda clavada (estilo Paint.NET/Photoshop); con Alt se escala
        desde el centro (comportamiento simétrico clásico). Cruzar el ancla
        vuelve la escala negativa y VOLTEA la forma (espejo). Como la forma es
        vectorial, el volteo no pierde nitidez. Todo se calcula desde el estado
        del press (sin acumular deriva)."""
        h = self.active_handle
        eps = 1e-6
        sign_x = -1 if 'l' in h else (1 if 'r' in h else 0)
        sign_y = -1 if 't' in h else (1 if 'b' in h else 0)
        hw0 = abs(self.press_sx) * self.fw / 2.0
        hh0 = abs(self.press_sy) * self.fh / 2.0
        # ⚓ Ancla en el marco del press (0,0 = centro con Alt)
        ax = 0.0 if from_center else -sign_x * hw0
        ay = 0.0 if from_center else -sign_y * hh0

        if proportional and h in ('lt', 'rt', 'lb', 'rb'):
            d0 = math.hypot(self.press_obj.x() - ax, self.press_obj.y() - ay)
            d1 = math.hypot(m.x() - ax, m.y() - ay)
            if d0 <= eps:
                return
            factor = d1 / d0
            self.sx = self._clamp(self.press_sx * factor)
            self.sy = self._clamp(self.press_sy * factor)
        else:
            if sign_x and abs(self.press_obj.x() - ax) > eps:
                self.sx = self._clamp(self.press_sx * (m.x() - ax) / (self.press_obj.x() - ax))
            if sign_y and abs(self.press_obj.y() - ay) > eps:
                self.sy = self._clamp(self.press_sy * (m.y() - ay) / (self.press_obj.y() - ay))

        if from_center:
            # Alt puede pulsarse/soltarse A MITAD de gesto: volver al centro
            self.tx, self.ty = self.press_tx, self.press_ty
            return

        # 🧭 Compensar tx/ty para que el ancla no se mueva: el centro queda
        # siempre a mitad de camino entre el ancla y el borde arrastrado.
        dx = dy = 0.0
        if sign_x:
            dx = sign_x * math.copysign(1.0, self.press_sx) * (self.fw / 2.0) * (self.sx - self.press_sx)
        if sign_y:
            dy = sign_y * math.copysign(1.0, self.press_sy) * (self.fh / 2.0) * (self.sy - self.press_sy)
        rad = math.radians(self.angle)
        cos_a, sin_a = math.cos(rad), math.sin(rad)
        self.tx = self.press_tx + dx * cos_a - dy * sin_a
        self.ty = self.press_ty + dx * sin_a + dy * cos_a

    def _clamp(self, s):
        # Conserva el SIGNO: una escala negativa voltea (espejo) la forma
        mag = max(self.MIN_SCALE, min(abs(s), self.MAX_SCALE))
        return -mag if s < 0 else mag

    # ==================================================================
    # TRANSFORMACIÓN Y GEOMETRÍA DE LA CAJA
    # ==================================================================
    def _center(self):
        return QPointF(self.orig_center.x() + self.tx, self.orig_center.y() + self.ty)

    def _display_transform(self):
        c = self._center()
        t = QTransform()
        t.translate(c.x(), c.y())
        t.rotate(self.angle)
        t.scale(self.sx, self.sy)
        t.translate(-self.fw / 2.0, -self.fh / 2.0)
        return t

    def _display_path(self):
        return self._display_transform().map(self._base_path)

    def _unrotated_frame(self):
        c = self._center()
        t = QTransform()
        t.translate(c.x(), c.y())
        t.rotate(self.angle)
        inv, _ = t.inverted()
        return inv

    def _half_extents(self):
        return (abs(self.sx) * self.fw / 2.0, abs(self.sy) * self.fh / 2.0)

    def _handles(self):
        hw, hh = self._half_extents()
        return {
            'lt': QPointF(-hw, -hh), 't': QPointF(0, -hh), 'rt': QPointF(hw, -hh),
            'l':  QPointF(-hw, 0),                          'r':  QPointF(hw, 0),
            'lb': QPointF(-hw, hh),  'b': QPointF(0, hh),  'rb': QPointF(hw, hh),
        }

    def _rotate_handle_pos(self):
        hw, hh = self._half_extents()
        offset = self.ROTATE_OFFSET_SCREEN / max(self.canvas.zoom_factor, 0.0001)
        return QPointF(0, -hh - offset)

    def _zone_at(self, canvas_point):
        m = self._unrotated_frame().map(QPointF(canvas_point))
        radius = (self.HANDLE_SCREEN_SIZE + 4) / max(self.canvas.zoom_factor, 0.0001)
        rp = self._rotate_handle_pos()
        if math.hypot(m.x() - rp.x(), m.y() - rp.y()) <= radius:
            return 'rotate'
        for hid, pos in self._handles().items():
            if math.hypot(m.x() - pos.x(), m.y() - pos.y()) <= radius:
                return ('scale', hid)
        hw, hh = self._half_extents()
        if abs(m.x()) <= hw and abs(m.y()) <= hh:
            return 'move'
        ring = self.ROTATE_RING_SCREEN / max(self.canvas.zoom_factor, 0.0001)
        if abs(m.x()) <= hw + ring and abs(m.y()) <= hh + ring:
            return 'rotate'
        return None

    def _update_hover_cursor(self, p):
        zone = self._zone_at(p)
        if zone == 'rotate':
            self.canvas.setCursor(Qt.OpenHandCursor)
        elif isinstance(zone, tuple):
            self.canvas.setCursor(Qt.PointingHandCursor)
        elif zone == 'move':
            self.canvas.setCursor(Qt.SizeAllCursor)
        else:
            self.canvas.setCursor(Qt.CrossCursor)

    def _update_view_margins(self):
        """Pide márgenes de vista si la caja (con tiradores y asa) sobresale del
        lienzo, para poder agarrarla sobre el fondo oscuro."""
        if not self.editing:
            self.canvas.reset_view_margins()
            return
        zoom = max(self.canvas.zoom_factor, 0.0001)
        disp = self._display_transform()
        pts = [disp.map(QPointF(0, 0)), disp.map(QPointF(self.fw, 0)),
               disp.map(QPointF(self.fw, self.fh)), disp.map(QPointF(0, self.fh))]
        c = self._center()
        frame = QTransform(); frame.translate(c.x(), c.y()); frame.rotate(self.angle)
        pts.append(frame.map(self._rotate_handle_pos()))
        pad = (self.HANDLE_SCREEN_SIZE + self.ROTATE_RING_SCREEN) / zoom
        xs = [q.x() for q in pts]; ys = [q.y() for q in pts]
        left = max(0, math.ceil(-(min(xs) - pad)))
        top = max(0, math.ceil(-(min(ys) - pad)))
        right = max(0, math.ceil(max(xs) + pad - self.canvas.base_width))
        bottom = max(0, math.ceil(max(ys) + pad - self.canvas.base_height))
        self.canvas.set_view_margins(left, top, right, bottom)

    # ==================================================================
    # RENDER
    # ==================================================================
    def refresh_live(self):
        """Llamado al cambiar color, grosor o estilo para refrescar en vivo."""
        if self.editing:
            if getattr(self, '_used_left_button', True):
                self.stroke_color = self.canvas.brush_color
                self.fill_color = self.canvas.brush_color_secondary
            else:
                self.stroke_color = self.canvas.brush_color_secondary
                self.fill_color = self.canvas.brush_color
            self._recompose()
            self._request_update()

    def _recompose(self):
        """Dibuja la forma transformada sobre la capa (partiendo del estado
        previo a la forma), sin tocar el historial."""
        img = QImage(self.image_before)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing, True)
        self.canvas.apply_selection_clip(p)
        p.setPen(self._make_pen())
        self._set_fill_brush(p)
        p.drawPath(self._display_path())
        p.end()
        self._write_target(img)

    def draw_preview(self, painter):
        # En edición: caja de transformación (la forma ya está en la capa)
        if self.editing:
            zoom = max(self.canvas.zoom_factor, 0.0001)
            disp = self._display_transform()
            corners = [disp.map(QPointF(0, 0)), disp.map(QPointF(self.fw, 0)),
                       disp.map(QPointF(self.fw, self.fh)), disp.map(QPointF(0, self.fh))]
            box = QPainterPath()
            box.addPolygon(QPolygonF(corners))
            box.closeSubpath()
            self.canvas.draw_selection_outline(painter, box)
            c = self._center()
            frame = QTransform(); frame.translate(c.x(), c.y()); frame.rotate(self.angle)
            size = self.HANDLE_SCREEN_SIZE / zoom
            pen_h = QPen(QColor(0, 0, 0)); pen_h.setWidth(0)
            painter.setPen(pen_h)
            painter.setBrush(QBrush(QColor("#ffffff")))
            for pos in self._handles().values():
                pt = frame.map(pos)
                painter.drawRect(QRectF(pt.x() - size / 2, pt.y() - size / 2, size, size))
            return
        # Dibujando: forma elástica
        if self.start_point and self.current_point:
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setPen(self._make_pen())
            self._set_fill_brush(painter)
            rect = QRect(self.start_point, self.current_point)
            painter.drawPath(build_shape_path(self.shape_id, rect))

    # ==================================================================
    # Pluma y relleno
    # ==================================================================
    def _make_pen(self):
        style = getattr(self.canvas, 'shape_line_style', Qt.SolidLine)
        return QPen(getattr(self, 'stroke_color', self.canvas.brush_color),
                    self.canvas.brush_size, style, Qt.RoundCap, Qt.RoundJoin)

    def _set_fill_brush(self, painter):
        pattern = getattr(self.canvas, 'shape_fill_pattern', None)
        if pattern is None:
            painter.setBrush(Qt.NoBrush)
            return
        fill = getattr(self, 'fill_color', None) or self.canvas.brush_color_secondary
        if isinstance(pattern, str) and pattern in pattern_tiles.CUSTOM_PATTERN_IDS:
            # Patrón procedural (azulejo de textura): los de dos tonos usan el
            # color de relleno + su opuesto; los de un tono dejan fondo transparente.
            bg = (pattern_tiles.other_color(fill, self.canvas.brush_color,
                                            self.canvas.brush_color_secondary)
                  if pattern_tiles.is_two_tone(pattern) else None)
            painter.setBrush(QBrush(pattern_tiles.make_tile(pattern, fill, bg)))
        else:
            painter.setBrush(QBrush(fill, pattern))
