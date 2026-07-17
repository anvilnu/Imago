# tools/crop_tool.py
# Herramienta de RECORTE con caja ajustable (estilo Photoshop).
#
# - Arrastrar sobre el lienzo crea la caja (Mayús = cuadrada); arrastrar
#   FUERA de la caja empieza una nueva; un clic suelto fuera la quita.
# - 8 tiradores para redimensionar; arrastrar DENTRO mueve la caja entera;
#   las flechas del teclado la desplazan 1 px (ajuste fino).
# - Enter o doble clic dentro APLICAN el recorte (deshacible, CropCommand);
#   Esc quita la caja sin tocar nada.
# - Lo de fuera de la caja se OSCURECE para previsualizar el resultado y
#   dentro se insinúa la regla de los tercios. El contorno usa las mismas
#   "hormigas" que la selección.
# - La caja se imanta a las guías (snap_x/snap_y del canvas) al crearla o
#   redimensionarla, igual que las herramientas de selección.

import math

from PySide6.QtGui import QColor, QPen, QBrush, QPainterPath
from PySide6.QtCore import Qt, QRect, QRectF, QPoint, QPointF
from i18n import t
from tools.base_tool import BaseTool


class CropTool(BaseTool):

    HANDLE_SCREEN_SIZE = 8   # lado de los tiradores, en píxeles de PANTALLA

    NUDGE_KEYS = {
        Qt.Key_Left:  QPoint(-1, 0),
        Qt.Key_Right: QPoint(1, 0),
        Qt.Key_Up:    QPoint(0, -1),
        Qt.Key_Down:  QPoint(0, 1),
    }

    def __init__(self, canvas):
        super().__init__(canvas)
        self.tool_id = "crop"
        self.rect = None      # QRect de la caja (coords de lienzo) o None
        self._mode = None     # 'create' | 'move' | ('resize', hid) | None
        self._start = None    # punto de inicio del gesto (crear)
        self._press = None    # punto de agarre (mover)
        self._orig = None     # copia de la caja al empezar el gesto
        self._constrain = False   # Mayús al crear: caja cuadrada
        # 🧲 Si hay una selección activa, la caja arranca ajustada a su
        # rectángulo envolvente: conserva el viejo flujo "recortar a la
        # selección" (menú Imagen → Recortar + Enter) ahora que es herramienta.
        sel = getattr(canvas, 'selection', None)
        if sel is not None and not sel.isEmpty():
            self._set_rect(sel.boundingRect().toAlignedRect())

    # ------------------------------------------------------------ utilidades
    def _canvas_point(self, event):
        """Posición del evento en coords de lienzo (float), recortada al lienzo."""
        z = max(self.canvas.zoom_factor, 0.0001)
        p = event.position() / z
        return QPointF(max(0.0, min(float(self.canvas.base_width), p.x())),
                       max(0.0, min(float(self.canvas.base_height), p.y())))

    def _snap(self, p):
        """Imanta el punto a las guías cercanas (si las hay)."""
        return QPointF(self.canvas.snap_x(p.x()), self.canvas.snap_y(p.y()))

    def _ratio(self):
        """Relación de aspecto fija (rw, rh) del panel, o None (libre)."""
        r = getattr(self.canvas, 'crop_ratio', None)
        if r and r[0] > 0 and r[1] > 0:
            return (float(r[0]), float(r[1]))
        return None

    def apply_ratio_to_box(self):
        """Reencaja la caja ACTUAL a la relación del panel (al cambiar el
        combo con una caja ya dibujada): conserva la esquina superior
        izquierda y el ancho, y recalcula el alto."""
        ratio = self._ratio()
        if ratio is None or self.rect is None:
            return
        rw, rh = ratio
        w = self.rect.width()
        h = max(1, int(round(w * rh / rw)))
        # Si no cabe hacia abajo, se acorta el ancho para mantener la proporción
        alto_max = self.canvas.base_height - self.rect.top()
        if h > alto_max:
            h = alto_max
            w = max(1, int(round(h * rw / rh)))
        self._set_rect(QRect(self.rect.left(), self.rect.top(), w, h))

    def _handles(self):
        """Los 8 tiradores: id -> posición en coords de lienzo."""
        r = QRectF(self.rect)
        cx, cy = r.center().x(), r.center().y()
        return {
            'lt': QPointF(r.left(), r.top()), 't': QPointF(cx, r.top()),
            'rt': QPointF(r.right(), r.top()), 'l': QPointF(r.left(), cy),
            'r': QPointF(r.right(), cy), 'lb': QPointF(r.left(), r.bottom()),
            'b': QPointF(cx, r.bottom()), 'rb': QPointF(r.right(), r.bottom()),
        }

    def _zone_at(self, p):
        """Qué hay bajo el punto: ('resize', hid) | 'move' | None (fuera)."""
        if self.rect is None:
            return None
        radius = (self.HANDLE_SCREEN_SIZE + 4) / max(self.canvas.zoom_factor, 0.0001)
        for hid, pos in self._handles().items():
            if math.hypot(p.x() - pos.x(), p.y() - pos.y()) <= radius:
                return ('resize', hid)
        if QRectF(self.rect).contains(p):
            return 'move'
        return None

    _CURSOR_POR_TIRADOR = {
        'lt': Qt.SizeFDiagCursor, 'rb': Qt.SizeFDiagCursor,
        'rt': Qt.SizeBDiagCursor, 'lb': Qt.SizeBDiagCursor,
        'l': Qt.SizeHorCursor, 'r': Qt.SizeHorCursor,
        't': Qt.SizeVerCursor, 'b': Qt.SizeVerCursor,
    }

    def _set_rect(self, rect):
        """Fija la caja (QRect normalizado, mínimo 1x1, dentro del lienzo) y
        avisa a la barra de opciones (dimensiones en vivo)."""
        if rect is not None:
            rect = rect.normalized().intersected(
                QRect(0, 0, self.canvas.base_width, self.canvas.base_height))
            if rect.width() < 1 or rect.height() < 1:
                rect = None
        self.rect = rect
        cb = getattr(self.canvas, 'crop_changed_callback', None)
        if cb is not None:
            cb(self.rect)
        self.canvas.update()

    # ------------------------------------------------------------ ratón
    def mouse_press(self, event):
        if event.button() != Qt.LeftButton:
            return
        p = self._canvas_point(event)
        zona = self._zone_at(p)
        if isinstance(zona, tuple):        # agarrar un tirador
            self._mode = zona
            self._orig = QRect(self.rect)
        elif zona == 'move':               # arrastrar la caja entera
            self._mode = 'move'
            self._press = p
            self._orig = QRect(self.rect)
        else:                              # crear una caja nueva
            self._mode = 'create'
            self._start = self._snap(p)
            self._constrain = bool(event.modifiers() & Qt.ShiftModifier)
            self._set_rect(None)

    def mouse_move(self, event):
        p = self._canvas_point(event)
        if not (event.buttons() & Qt.LeftButton):
            # Sobrevolar: cursor según lo que haya debajo
            zona = self._zone_at(p)
            if isinstance(zona, tuple):
                self.canvas.setCursor(self._CURSOR_POR_TIRADOR[zona[1]])
            elif zona == 'move':
                self.canvas.setCursor(Qt.SizeAllCursor)
            else:
                self.canvas.setCursor(Qt.CrossCursor)
            return

        if self._mode == 'create' and self._start is not None:
            self._constrain = bool(event.modifiers() & Qt.ShiftModifier)
            q = self._snap(p)
            dx, dy = q.x() - self._start.x(), q.y() - self._start.y()
            ratio = self._ratio()
            if ratio is not None:          # 📐 Relación fija del panel (manda
                rw, rh = ratio             # sobre Mayús): dirige el eje que
                k = max(abs(dx) / rw, abs(dy) / rh)   # más avanza en proporción
                dx = math.copysign(k * rw, dx if dx else 1)
                dy = math.copysign(k * rh, dy if dy else 1)
            elif self._constrain:          # Mayús: caja CUADRADA
                lado = min(abs(dx), abs(dy))
                dx = math.copysign(lado, dx if dx else 1)
                dy = math.copysign(lado, dy if dy else 1)
            r = QRectF(self._start, self._start + QPointF(dx, dy)).normalized()
            self._set_rect(r.toAlignedRect())
        elif self._mode == 'move' and self._orig is not None:
            delta = p - self._press
            nuevo = QRect(self._orig)
            nuevo.translate(int(round(delta.x())), int(round(delta.y())))
            # La caja no sale del lienzo al moverla (se desliza por los bordes)
            nuevo.moveLeft(max(0, min(nuevo.left(),
                                      self.canvas.base_width - nuevo.width())))
            nuevo.moveTop(max(0, min(nuevo.top(),
                                     self.canvas.base_height - nuevo.height())))
            self._set_rect(nuevo)
        elif isinstance(self._mode, tuple) and self._orig is not None:
            hid = self._mode[1]
            q = self._snap(p)
            r = QRectF(self._orig)
            if hid in ('lt', 'l', 'lb'): r.setLeft(q.x())
            if hid in ('rt', 'r', 'rb'): r.setRight(q.x())
            if hid in ('lt', 't', 'rt'): r.setTop(q.y())
            if hid in ('lb', 'b', 'rb'): r.setBottom(q.y())
            r = r.normalized()
            ratio = self._ratio()
            if ratio is not None:
                r = self._constrain_resize_to_ratio(r, hid, ratio)
            self._set_rect(r.toAlignedRect())

    @staticmethod
    def _constrain_resize_to_ratio(r, hid, ratio):
        """Reencaja el rectángulo redimensionado a la relación fija: en las
        esquinas manda el eje que más avanza (anclando la esquina opuesta);
        en los lados, el eje arrastrado dirige y el otro se centra."""
        rw, rh = ratio
        if hid in ('lt', 'rt', 'lb', 'rb'):
            k = max(r.width() / rw, r.height() / rh)
            w, h = k * rw, k * rh
            x = r.left() if hid in ('rt', 'rb') else r.right() - w
            y = r.top() if hid in ('lb', 'rb') else r.bottom() - h
            return QRectF(x, y, w, h)
        if hid in ('l', 'r'):
            h = r.width() * rh / rw
            return QRectF(r.left(), r.center().y() - h / 2.0, r.width(), h)
        # 't' / 'b'
        w = r.height() * rw / rh
        return QRectF(r.center().x() - w / 2.0, r.top(), w, r.height())

    def mouse_release(self, event):
        if event.button() != Qt.LeftButton:
            return
        # Un clic suelto fuera de la caja (sin arrastre) la quita
        self._mode = None
        self._start = None
        self._press = None
        self._orig = None

    def mouse_double_click(self, event):
        if event.button() == Qt.LeftButton and self.rect is not None:
            p = self._canvas_point(event)
            if QRectF(self.rect).contains(p):
                self.apply()

    # ------------------------------------------------------------ teclado
    def key_press(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and self.rect is not None:
            self.apply()
            return True
        if event.key() == Qt.Key_Escape and self.rect is not None:
            self.cancel()
            return True
        delta = self.NUDGE_KEYS.get(event.key())
        if delta is not None and self.rect is not None:
            nuevo = QRect(self.rect)
            nuevo.translate(delta)
            nuevo.moveLeft(max(0, min(nuevo.left(),
                                      self.canvas.base_width - nuevo.width())))
            nuevo.moveTop(max(0, min(nuevo.top(),
                                     self.canvas.base_height - nuevo.height())))
            self._set_rect(nuevo)
            return True
        return False

    # ------------------------------------------------------------ acciones
    def apply(self):
        """Aplica el recorte de la caja actual (deshacible) y la retira."""
        if self.rect is None:
            return False
        rect = QRect(self.rect)
        self._set_rect(None)
        # Recortar al lienzo completo no cambia nada
        if (rect.width() == self.canvas.base_width
                and rect.height() == self.canvas.base_height):
            return False
        from models.layer_commands import CropCommand
        self.canvas.undo_stack.push(CropCommand(self.canvas, rect))
        # Reencuadrar la vista al nuevo tamaño (lo pone main, como el menú)
        cb = getattr(self.canvas, 'crop_applied_callback', None)
        if cb is not None:
            cb()
        return True

    def cancel(self):
        """Quita la caja sin recortar nada."""
        self._mode = None
        self._set_rect(None)

    # ------------------------------------------------------------ dibujo
    def draw_preview(self, painter):
        if self.rect is None:
            return
        r = QRectF(self.rect)
        W, H = self.canvas.base_width, self.canvas.base_height

        # 1) Oscurecer lo de FUERA de la caja (previsualiza el resultado)
        fuera = QPainterPath()
        fuera.addRect(QRectF(0, 0, W, H))
        dentro = QPainterPath()
        dentro.addRect(r)
        painter.fillPath(fuera.subtracted(dentro), QColor(0, 0, 0, 110))

        # 2) Regla de los TERCIOS, sutil, dentro de la caja
        pen_tercios = QPen(QColor(255, 255, 255, 70))
        pen_tercios.setWidth(0)          # cosmético: 1 px en pantalla
        painter.setPen(pen_tercios)
        for i in (1, 2):
            x = r.left() + r.width() * i / 3.0
            y = r.top() + r.height() * i / 3.0
            painter.drawLine(QPointF(x, r.top()), QPointF(x, r.bottom()))
            painter.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))

        # 3) Contorno con las mismas "hormigas" que la selección
        self.canvas.draw_selection_outline(painter, dentro)

        # 4) Tiradores: cuadraditos blancos con borde negro (como MoveTool)
        zoom = max(self.canvas.zoom_factor, 0.0001)
        lado = self.HANDLE_SCREEN_SIZE / zoom
        pen_h = QPen(QColor(0, 0, 0))
        pen_h.setWidth(0)
        painter.setPen(pen_h)
        painter.setBrush(QBrush(QColor("#ffffff")))
        for pos in self._handles().values():
            painter.drawRect(QRectF(pos.x() - lado / 2, pos.y() - lado / 2,
                                    lado, lado))
