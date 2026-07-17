# tools/draw_tools.py
import math
import numpy as np

from PySide6.QtGui import (QPainter, QColor, QImage, QRadialGradient, QBrush, QPainterPath,
                           QTransform, QPolygonF, QPen, QRegion)
from PySide6.QtCore import Qt, QPoint, QLineF, QRectF, QPointF

from i18n import t
from tools.base_tool import BaseTool
from tools.commands import PaintCommand
from tools import pattern_tiles
from tools.roi_buffers import CoberturaDispersa
from tools.numpy_utils import shape_field, SHAPES, get_kernel, qimage_to_bgra, bgra_to_qimage, recompose_alpha, CALLIG_ASPECT


class PenTool(BaseTool):
    def __init__(self, canvas):
        super().__init__(canvas)
        self.last_point = None
        self.image_before_stroke = None
        self.distance_carried = 0.0
        self.tool_id = "pen"
        self.history_name = t("tool.name.pen")  # 📝 Texto con el que aparece en el Historial
        # 🧮 Buffers del MOTOR DE COBERTURA (solo Pincel sólido; ver _use_coverage).
        # El trazo se acumula por teselas en una máscara float [0..1] tomando el
        # MÁXIMO por estampa (no SourceOver), así el solapamiento no infla la
        # opacidad ni reserva una matriz del tamaño completo del documento.
        self._coverage = None
        self._kernel_cache = {}
        self._coverage_active = False
        self._dirty_rect = None   # caja semiabierta conocida de todo el trazo
        # 📐 Último punto pintado (persiste entre trazos): con Mayúsculas pulsada,
        # el siguiente clic traza una LÍNEA RECTA desde aquí hasta el nuevo punto.
        self._last_end_point = None

    # ------------------------------------------------------------------
    # Selección del motor de trazo
    # ------------------------------------------------------------------
    def _stroke_antialias(self):
        """Suavizado del trazo: configurable en el Pincel puro (canvas.brush_antialias,
        suavizado por defecto); el resto de subclases (Goma…) pintan siempre suave."""
        if type(self) is PenTool:
            return bool(getattr(self.canvas, 'brush_antialias', True))
        return True

    def _pattern_is_solid(self):
        p = getattr(self.canvas, 'brush_pattern', 'solid')
        return p in (None, 'solid', Qt.BrushStyle.SolidPattern)

    def _use_coverage(self):
        """Solo el Pincel PURO con relleno sólido usa el motor de cobertura.
        Goma y Sustituir-color (subclases) y los patrones geométricos siguen
        por el camino clásico, intactos."""
        return type(self) is PenTool and self._pattern_is_solid()

    def _brush_shape(self):
        sh = getattr(self.canvas, 'brush_shape', 'round')
        return sh if sh in SHAPES else 'round'

    def _pattern_bg_color(self, fg):
        """Color de fondo para patrones de relleno de DOS tonos: el opuesto al de
        frente (si se pinta con el primario, el fondo es el secundario y al revés)."""
        return pattern_tiles.other_color(
            fg, self.canvas.brush_color, self.canvas.brush_color_secondary)

    # ------------------------------------------------------------------
    # Ratón
    # ------------------------------------------------------------------
    def mouse_press(self, event):
        # 🎨 Alt+clic: cuentagotas temporal, no inicia trazo. Solo el Pincel
        # puro (el Lápiz y el Aerógrafo lo gestionan en su propio mouse_press;
        # en la Goma, Alt no captura: no se pinta con color).
        if type(self) is PenTool and self._alt_pick_color(event):
            return
        # 🎯 Modo SELECCIÓN del pincel: pinta una selección, no píxeles.
        if self._sel_active():
            return self._sel_press(event)
        # 🖱️ Botón izquierdo = color primario | Botón derecho = color secundario
        if event.button() not in (Qt.LeftButton, Qt.RightButton):
            return
        if event.button() == Qt.LeftButton:
            self.stroke_color = self.canvas.brush_color
        else:
            self.stroke_color = self.canvas.brush_color_secondary

        zoom = self.canvas.zoom_factor
        click = (event.position() / zoom).toPoint()
        # 📐 Con Mayúsculas y un punto previo, el trazo arranca en LÍNEA RECTA desde
        # ese punto; si no, arranca donde se pulsa (un punto).
        straight = (type(self) is PenTool
                    and bool(event.modifiers() & Qt.ShiftModifier)
                    and self._last_end_point is not None)
        start = self._last_end_point if straight else click
        self.last_point = click
        # 🎭 Destino del trazo: máscara (Grayscale8) o píxeles de la capa. Se fija
        # al pulsar y no cambia durante el trazo.
        self._paint_on_mask = self.canvas.paint_on_mask()
        target = self.canvas.paint_target()
        self.image_before_stroke = QImage(target)
        self.distance_carried = 0.0
        self._dirty_rect = None

        # El motor de cobertura (BGRA) no aplica al pintar en la máscara.
        self._coverage_active = self._use_coverage() and not self._paint_on_mask
        if self._coverage_active:
            self._coverage = CoberturaDispersa(target.width(), target.height())
            self._kernel_cache = {}
            if straight:
                self._coverage_stroke(start, click)   # línea recta desde el último punto
            else:
                # Estampar Y recomponer: sin el _recompose, un clic suelto acumulaba
                # la estampa en la máscara de cobertura pero no la volcaba a la capa,
                # así que el clic no pintaba (solo empezaba a verse al arrastrar).
                rect = self._coverage_stamp(click)
                if rect:
                    self._recompose(*rect)
        else:
            painter = QPainter(target)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, self._stroke_antialias())
            self.canvas.apply_selection_clip(painter)  # ✂️ Pintar solo dentro de la selección
            self.draw_stroke(painter, start, click)
            painter.end()
        self.canvas.update()

    def mouse_move(self, event):
        if self._sel_active():
            return self._sel_move(event)
        if not (event.buttons() & (Qt.LeftButton | Qt.RightButton)):
            return
        # 🛡️ Si el trazo no empezó con un botón de dibujo, no hay nada que continuar
        if self.image_before_stroke is None:
            return
        zoom = self.canvas.zoom_factor
        current_point = (event.position() / zoom).toPoint()

        if self._coverage_active:
            self._coverage_stroke(self.last_point, current_point)
        else:
            painter = QPainter(self.canvas.paint_target())
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, self._stroke_antialias())
            self.canvas.apply_selection_clip(painter)
            self.draw_stroke(painter, self.last_point, current_point)
            painter.end()

        self.last_point = current_point
        self.canvas.update()

    def mouse_release(self, event):
        if self._sel_active():
            return self._sel_release(event)
        # 🛡️ Solo registramos el comando si realmente hubo un trazo en curso.
        if self.image_before_stroke is None:
            return

        # 🟢 COPIA, no referencia (si no, trazos futuros mutarían esta "foto").
        image_after_stroke = QImage(self.canvas.paint_target())

        comando = PaintCommand(
            self.canvas,
            self.canvas.active_layer_index,
            self.image_before_stroke,
            image_after_stroke,
            self.history_name,   # 📝 "Pincel", "Borrador"... según la herramienta
            tool_id=self.tool_id,
            target=("mask" if getattr(self, "_paint_on_mask", False) else "image"),
            confine=True,        # 🪶 respeta el calado de la selección (borde suave)
            dirty_rect=self._dirty_rect,
        )
        self.canvas.undo_stack.push(comando)

        # 📐 Recordar el final del trazo: el siguiente clic con Mayúsculas trazará
        # una línea recta desde aquí.
        self._last_end_point = self.last_point

        # Cerramos el trazo y liberamos los buffers de cobertura.
        self.image_before_stroke = None
        self._coverage = None
        self._kernel_cache = {}
        self._coverage_active = False
        self._dirty_rect = None

    def _marcar_rect_sucio(self, x0, y0, x1, y1):
        """Acumula una caja semiabierta conservadora, limitada al destino."""
        if self.image_before_stroke is None:
            return
        ancho = self.image_before_stroke.width()
        alto = self.image_before_stroke.height()
        x0 = max(0, int(math.floor(x0)))
        y0 = max(0, int(math.floor(y0)))
        x1 = min(ancho, int(math.ceil(x1)))
        y1 = min(alto, int(math.ceil(y1)))
        if x1 <= x0 or y1 <= y0:
            return
        if self._dirty_rect is None:
            self._dirty_rect = [x0, y0, x1, y1]
        else:
            rect = self._dirty_rect
            rect[0] = min(rect[0], x0)
            rect[1] = min(rect[1], y0)
            rect[2] = max(rect[2], x1)
            rect[3] = max(rect[3], y1)

    # ------------------------------------------------------------------
    # PINCEL DE SELECCIÓN (checkbox del panel del pincel)
    # ------------------------------------------------------------------
    # Color del trazo de selección en curso: el azul de acento del tema,
    # semitransparente (el mismo lenguaje que el resaltado del Pincel corrector).
    @property
    def _SEL_COLOR(self):
        import theme
        c = QColor(theme.ACCENT)
        c.setAlpha(110)
        return c

    def _sel_active(self):
        """Solo el PINCEL puro (no goma/lápiz/sustituir-color) actúa como pincel
        de selección, y solo con el modo activado en su panel."""
        return type(self) is PenTool and getattr(self.canvas, "pen_selection_mode", False)

    def _sel_stamp(self, p1, p2):
        """Marca el trazo (círculo de diámetro = tamaño del pincel) en el overlay."""
        painter = QPainter(self._sel_overlay)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)  # borde nítido
        w = max(1, int(self.canvas.brush_size))
        painter.setPen(QPen(self._SEL_COLOR, w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        if p1 == p2:
            painter.drawPoint(p1)
        else:
            painter.drawLine(p1, p2)
        painter.end()

    def _sel_press(self, event):
        if event.button() not in (Qt.LeftButton, Qt.RightButton):
            return
        # Izquierdo = añade a la selección; derecho = resta.
        self._sel_add = (event.button() == Qt.LeftButton)
        self._sel_overlay = QImage(self.canvas.base_width, self.canvas.base_height,
                                   QImage.Format_ARGB32)
        self._sel_overlay.fill(0)
        self._sel_last = (event.position() / self.canvas.zoom_factor).toPoint()
        self._sel_stamp(self._sel_last, self._sel_last)
        self.canvas.update()

    def _sel_move(self, event):
        if getattr(self, "_sel_overlay", None) is None:
            return
        if not (event.buttons() & (Qt.LeftButton | Qt.RightButton)):
            return
        cur = (event.position() / self.canvas.zoom_factor).toPoint()
        self._sel_stamp(self._sel_last, cur)
        self._sel_last = cur
        self.canvas.update()

    def _sel_release(self, event):
        overlay = getattr(self, "_sel_overlay", None)
        self._sel_overlay = None
        if overlay is None:
            return
        path = self._path_from_overlay(overlay)
        self.canvas.update()   # retirar el overlay del trazo
        if path is None or path.isEmpty():
            return
        prev = self.canvas.selection
        has_prev = prev is not None and not prev.isEmpty()
        if not self._sel_add:                       # restar
            if not has_prev:
                return
            new = QPainterPath(prev).subtracted(path)
            new = None if new.isEmpty() else new
        else:                                       # añadir (o crear)
            new = QPainterPath(prev).united(path) if has_prev else path
        from tools.commands import SelectionChangeCommand
        self.canvas.undo_stack.push(SelectionChangeCommand(
            self.canvas, prev, new,
            t("hist.sel_brush", default="Selección (pincel)"), tool_id="select"))

    def _path_from_overlay(self, overlay):
        """Convierte el trazo pintado (alfa del overlay) en un QPainterPath de
        contorno limpio con path_from_mask (vectorizado + fusión de rectángulos,
        igual que la varita mágica; el viejo patrón QRegion fila a fila tardaba
        decenas de segundos en imágenes grandes)."""
        from tools.numpy_utils import path_from_mask
        W, H = overlay.width(), overlay.height()
        g = overlay.convertToFormat(QImage.Format_ARGB32)
        bpl = g.bytesPerLine()
        arr = np.frombuffer(g.constBits(), np.uint8).reshape(H, bpl)[:, :W * 4].reshape(H, W, 4)
        return path_from_mask(arr[:, :, 3] > 0)

    def draw_preview(self, painter):
        """Mientras se pinta una selección, muestra el trazo en curso (overlay
        azul) sobre el lienzo. El painter ya viene escalado a coords de imagen."""
        overlay = getattr(self, "_sel_overlay", None)
        if overlay is not None:
            painter.drawImage(0, 0, overlay)

    # ------------------------------------------------------------------
    # MOTOR DE COBERTURA (numpy) — pincel sólido
    # ------------------------------------------------------------------
    def _get_kernel(self, radius, hardness, shape):
        """Kernel de estampa [0..1] con la FORMA de punta elegida, perfil de
        dureza CONTINUO (cúbico) y antialias de ~1px en el perímetro. Se cachea
        por (radio, dureza, forma): en un trazo normal se calcula una sola vez."""
        key = (round(radius, 2), int(hardness), shape)
        cached = self._kernel_cache.get(key)
        if cached is not None:
            return cached
        R = int(math.ceil(radius)) + 1
        size = 2 * R + 1
        yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
        inv_r = 1.0 / max(radius, 1e-6)
        nx = (xx - R) * inv_r
        ny = (yy - R) * inv_r
        sf = shape_field(nx, ny, shape).astype(np.float32)
        h = hardness / 100.0
        if h >= 1.0:
            core = np.ones_like(sf)
        else:
            k = np.clip((sf - h) / (1.0 - h), 0.0, 1.0)
            # Usar curva de coseno en lugar de cúbica para retener más grosor visual
            core = np.where(sf <= h, 1.0, (np.cos(k * np.pi) + 1.0) / 2.0)
        aa = np.clip((1.0 - sf) * radius + 0.5, 0.0, 1.0)  # cobertura suave del borde
        kernel = (core * aa).astype(np.float32)
        self._kernel_cache[key] = kernel
        return kernel

    def _coverage_stroke(self, p1, p2):
        """Recorre el segmento estampando con el espaciado del pincel, igual que
        draw_stroke pero acumulando en la máscara de cobertura."""
        size = self.canvas.brush_size
        spacing_percent = getattr(self.canvas, 'brush_spacing', 10)
        line = QLineF(p1, p2)
        length = line.length()
        if length == 0:
            rect = self._coverage_stamp(p2)
            if rect: self._recompose(*rect)
            return
        step = max(1.0, size * (spacing_percent / 100.0))
        distance_to_next = step - self.distance_carried
        
        bx0, by0, bx1, by1 = 999999, 999999, -999999, -999999
        while distance_to_next <= length:
            t = distance_to_next / length
            rect = self._coverage_stamp(line.pointAt(t).toPoint())
            if rect:
                x0, y0, x1, y1 = rect
                bx0 = min(bx0, x0); by0 = min(by0, y0)
                bx1 = max(bx1, x1); by1 = max(by1, y1)
            distance_to_next += step
        self.distance_carried = length - (distance_to_next - step)
        
        if bx0 < bx1 and by0 < by1:
            self._recompose(bx0, by0, bx1, by1)

    def _coverage_stamp(self, point):
        """Acumula una estampa (MÁXIMO) en la máscara y recompone en vivo solo
        el rectángulo afectado."""
        size = self.canvas.brush_size
        radius = max(0.6, size / 2.0)
        hardness = getattr(self.canvas, 'brush_hardness', 100)
        kernel = get_kernel(radius, hardness, self._brush_shape(),
                            antialias=self._stroke_antialias())
        R = (kernel.shape[0] - 1) // 2
        px, py = point.x(), point.y()
        H, W = self._coverage.alto, self._coverage.ancho

        x0, y0 = px - R, py - R
        cx0, cy0 = max(0, x0), max(0, y0)
        cx1, cy1 = min(W, px + R + 1), min(H, py + R + 1)
        if cx1 <= cx0 or cy1 <= cy0:
            return None  # estampa completamente fuera del lienzo

        ksub = kernel[cy0 - y0:cy1 - y0, cx0 - x0:cx1 - x0]
        self._coverage.maximo(cx0, cy0, ksub)
        self._marcar_rect_sucio(cx0, cy0, cx1, cy1)
        return (cx0, cy0, cx1, cy1)

    def _recompose(self, x0, y0, x1, y1):
        """Recompone capa = original + color·cobertura en el rectángulo dado
        (SourceOver no premultiplicado, vectorizado) y lo vuelca en la capa con
        modo Source, respetando la selección activa como clip."""
        w, h = x1 - x0, y1 - y0
        sub = self.image_before_stroke.copy(x0, y0, w, h).convertToFormat(QImage.Format.Format_ARGB32)
        o = qimage_to_bgra(sub).astype(np.float32)  # H×W×4 (B,G,R,A) 0..255
        cov = self._coverage.region(x0, y0, x1, y1)
        # 🌫️ Opacidad del trazo (solo el Pincel puro, independiente del alfa
        # del color): escala la cobertura al recomponer, así es UNIFORME en
        # todo el trazo (el solapado de estampas no acumula opacidad).
        if type(self) is PenTool:
            op = int(getattr(self.canvas, 'brush_opacity', 100)) / 100.0
            if op < 1.0:
                cov = cov * op

        # 🔒 Bloqueo de transparencia: SourceAtop hecho a mano (el volcado con
        # modo Source pisa el SourceAtop que fija apply_selection_clip): la
        # cobertura se pesa por el alfa original y este NO cambia.
        if self.canvas.alpha_lock_active():
            cov = cov * (o[..., 3] / 255.0)
            out8 = recompose_alpha(o, cov, self.stroke_color)
            out8[..., 3] = o[..., 3].astype(np.uint8)
        else:
            out8 = recompose_alpha(o, cov, self.stroke_color)
        out_img = bgra_to_qimage(out8)

        layer_obj = self.canvas.layers[self.canvas.active_layer_index]
        painter = QPainter(layer_obj.image)
        self.canvas.apply_selection_clip(painter)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.drawImage(x0, y0, out_img)
        painter.end()

    @staticmethod
    def _qimage_to_bgra(img):
        w, h = img.width(), img.height()
        bpl = img.bytesPerLine()
        buf = bytes(img.constBits())
        arr = np.frombuffer(buf, dtype=np.uint8).reshape(h, bpl)[:, :w * 4]
        return arr.reshape(h, w, 4)

    @staticmethod
    def _bgra_to_qimage(arr):
        h, w, _ = arr.shape
        arr = np.ascontiguousarray(arr, dtype=np.uint8)
        # .copy() para que el QImage NO dependa del buffer numpy temporal
        return QImage(arr.tobytes(), w, h, 4 * w, QImage.Format.Format_ARGB32).copy()

    # ------------------------------------------------------------------
    # Geometría de la punta (para el camino clásico de patrones)
    # ------------------------------------------------------------------
    def _shape_path(self, point, radius, shape):
        """QPainterPath de la punta centrada en 'point' (coherente con shape_field)."""
        cx, cy = point.x(), point.y()
        r = radius
        a = CALLIG_ASPECT
        path = QPainterPath()
        if shape == "square":
            path.addRect(QRectF(cx - r, cy - r, 2 * r, 2 * r))
        elif shape == "diamond":
            poly = QPolygonF([QPointF(cx, cy - r), QPointF(cx + r, cy),
                              QPointF(cx, cy + r), QPointF(cx - r, cy)])
            path.addPolygon(poly)
            path.closeSubpath()
        elif shape == "horizontal":
            path.addEllipse(QRectF(cx - r, cy - r / a, 2 * r, 2 * r / a))
        elif shape == "vertical":
            path.addEllipse(QRectF(cx - r / a, cy - r, 2 * r / a, 2 * r))
        elif shape in ("fdiag", "bdiag"):
            base = QPainterPath()
            base.addEllipse(QRectF(-r, -r / a, 2 * r, 2 * r / a))  # barra horizontal en el origen
            t = QTransform()
            t.translate(cx, cy)
            t.rotate(45 if shape == "fdiag" else -45)
            path = t.map(base)
        else:  # round
            path.addEllipse(QRectF(cx - r, cy - r, 2 * r, 2 * r))
        return path

    # ------------------------------------------------------------------
    # CAMINO CLÁSICO (patrones del pincel, y heredado por Goma/Sustituir-color)
    # ------------------------------------------------------------------
    def draw_stroke(self, painter, p1, p2):
        """Dibuja el trazo continuo leyendo el espaciado dinámico según la herramienta activa"""
        size = self.canvas.brush_size
        radius = size / 2.0
        color = getattr(self, 'stroke_color', self.canvas.brush_color)

        # 🔄 Lee la propiedad correcta según la herramienta en uso
        is_eraser = isinstance(self, EraserTool)
        hardness_attr = 'eraser_hardness' if is_eraser else 'brush_hardness'
        spacing_attr = 'eraser_spacing' if is_eraser else 'brush_spacing'
        hardness = getattr(self.canvas, hardness_attr, 100)
        spacing_percent = getattr(self.canvas, spacing_attr, 10)

        line = QLineF(p1, p2)
        length = line.length()
        if length == 0:
            self.draw_stamp(painter, p2, radius, color, hardness)
            return

        step = max(1.0, size * (spacing_percent / 100.0))
        distance_to_next_stamp = step - self.distance_carried
        while distance_to_next_stamp <= length:
            t = distance_to_next_stamp / length
            pt = line.pointAt(t).toPoint()
            self.draw_stamp(painter, pt, radius, color, hardness)
            distance_to_next_stamp += step
        self.distance_carried = length - (distance_to_next_stamp - step)

    def draw_stamp(self, painter, point, radius, color, hardness):
        """Dibuja la punta aplicando la curva de dureza o un patrón de relleno nativo.
        La FORMA se aplica vía _shape_path (la Goma sobrescribe este método)."""
        if radius <= 0:
            return
        if radius < 0.6:
            radius = 0.6
        # Un píxel adicional cubre el antialias del borde de QPainter.
        self._marcar_rect_sucio(point.x() - radius - 1,
                                point.y() - radius - 1,
                                point.x() + radius + 2,
                                point.y() + radius + 2)

        pattern_type = getattr(self.canvas, 'brush_pattern', 'solid')
        shape = self._brush_shape()

        if pattern_type in (None, 'solid', Qt.BrushStyle.SolidPattern):
            # --- Relleno estándar con dureza ---
            gradient = QRadialGradient(point.x(), point.y(), radius)
            hardness_factor = hardness / 100.0
            gradient.setColorAt(0, color)
            if hardness_factor < 1.0:
                if hardness_factor > 0:
                    gradient.setColorAt(hardness_factor, color)
                steps = 8
                for i in range(1, steps + 1):
                    k = i / steps
                    pos = hardness_factor + (1.0 - hardness_factor) * k
                    alpha_multiplier = (1.0 - k) ** 3
                    step_color = QColor(
                        color.red(), color.green(), color.blue(),
                        int(color.alpha() * alpha_multiplier)
                    )
                    gradient.setColorAt(pos, step_color)
            else:
                gradient.setColorAt(1.0, color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(gradient))
        elif pattern_type in pattern_tiles.CUSTOM_PATTERN_IDS:
            # --- Patrón PROCEDURAL (azulejo de textura repetible) ---
            # Los de dos tonos usan frente (color activo) + fondo (color opuesto);
            # los de un tono dejan el fondo transparente.
            bg = (self._pattern_bg_color(color)
                  if pattern_tiles.is_two_tone(pattern_type) else None)
            tile = pattern_tiles.make_tile(pattern_type, color, bg)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(tile))
        else:
            # --- Rellenos de patrones geométricos nativos de Qt ---
            style = pattern_type if isinstance(pattern_type, Qt.BrushStyle) else Qt.BrushStyle.SolidPattern
            if pattern_type == "horizontal": style = Qt.BrushStyle.HorPattern
            elif pattern_type == "vertical": style = Qt.BrushStyle.VerPattern
            elif pattern_type == "fdiag": style = Qt.BrushStyle.FDiagPattern
            elif pattern_type == "bdiag": style = Qt.BrushStyle.BDiagPattern
            elif pattern_type == "cross": style = Qt.BrushStyle.CrossPattern
            elif pattern_type == "diagcross": style = Qt.BrushStyle.DiagCrossPattern
            pattern_brush = QBrush(color, style)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(pattern_brush)

        # La punta se dibuja como path (el patrón/gradiente rellena su interior)
        painter.drawPath(self._shape_path(point, radius, shape))


class PencilTool(PenTool):
    """Lápiz: trazo DURO y sin suavizado (aliased), de tamaño N px y forma de
    punta configurables (las mismas que el pincel). A 1 px es el lápiz de
    precisión píxel a píxel estilo Paint.NET; a tamaños mayores estampa un bloque
    duro de la forma elegida. Tamaño y forma son propios (independientes del pincel)."""

    def __init__(self, canvas):
        super().__init__(canvas)
        self.tool_id = "pencil"
        self.history_name = t("tool.name.pencil")
        self._offsets_cache = {}
        self._stamp_cache = {}

    def _pixel_under(self, event):
        """Píxel EXACTO bajo el cursor: floor de la coordenada lógica (no
        redondeo), como el pixel art de Paint.NET."""
        zoom = self.canvas.zoom_factor
        pos = event.position() / zoom
        return QPoint(math.floor(pos.x()), math.floor(pos.y()))

    def _pencil_shape(self):
        sh = getattr(self.canvas, 'pencil_shape', 'round')
        return sh if sh in SHAPES else 'round'

    def mouse_press(self, event):
        # 🎨 Alt+clic: cuentagotas temporal, no inicia trazo
        if self._alt_pick_color(event):
            return
        if event.button() not in (Qt.LeftButton, Qt.RightButton):
            return
        if event.button() == Qt.LeftButton:
            self.stroke_color = self.canvas.brush_color
        else:
            self.stroke_color = self.canvas.brush_color_secondary

        click = self._pixel_under(event)
        # 📐 Con Mayúsculas y un punto previo, LÍNEA RECTA desde el final del
        # último trazo (como el pincel; en pixel art es donde más se usa).
        straight = (bool(event.modifiers() & Qt.ShiftModifier)
                    and self._last_end_point is not None)
        start = self._last_end_point if straight else click
        self.last_point = click
        self._paint_on_mask = self.canvas.paint_on_mask()
        target = self.canvas.paint_target()
        self.image_before_stroke = QImage(target)
        self.distance_carried = 0.0
        self._dirty_rect = None

        painter = QPainter(target)
        self.canvas.apply_selection_clip(painter)
        self.draw_stroke(painter, start, click, skip_first=False)
        painter.end()
        self.canvas.update()

    def mouse_move(self, event):
        if not (event.buttons() & (Qt.LeftButton | Qt.RightButton)):
            return
        if self.image_before_stroke is None:
            return
        current_point = self._pixel_under(event)

        painter = QPainter(self.canvas.paint_target())
        self.canvas.apply_selection_clip(painter)
        # skip_first=True: el píxel de unión ya se pintó como final del segmento
        # anterior; repintarlo doblaría la opacidad con colores translúcidos.
        self.draw_stroke(painter, self.last_point, current_point, skip_first=True)
        painter.end()

        self.last_point = current_point
        self.canvas.update()

    def _shape_offsets(self, size, shape):
        """Offsets (dx,dy) de una punta DURA de diámetro 'size' con la forma dada.
        Centrado de píxel +0.5 para que el patrón sea simétrico (pixel art)."""
        key = (size, shape)
        offs = self._offsets_cache.get(key)
        if offs is not None:
            return offs
        half = size // 2
        inv_r = 1.0 / (size / 2.0)
        offs = []
        for dy in range(-half, size - half):
            for dx in range(-half, size - half):
                nx = (dx + 0.5) * inv_r
                ny = (dy + 0.5) * inv_r
                if float(shape_field(nx, ny, shape)) <= 1.0:
                    offs.append((dx, dy))
        self._offsets_cache[key] = offs
        return offs

    def _hard_stamp(self, size, shape, color):
        """QImage de la punta dura coloreada (cacheada por tamaño/forma/color).
        Se construye una vez por configuración; cada celda del trazo es un blit."""
        key = (size, shape, color.rgba())
        img = self._stamp_cache.get(key)
        if img is not None:
            return img
        img = QImage(size, size, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        half = size // 2
        for dx, dy in self._shape_offsets(size, shape):
            img.setPixelColor(half + dx, half + dy, color)
        self._stamp_cache[key] = img
        return img

    def _stamp_pixel(self, painter, x, y, color, size, shape):
        half = size // 2
        self._marcar_rect_sucio(x - half, y - half,
                                x - half + size, y - half + size)
        if size <= 1:
            painter.fillRect(x, y, 1, 1, color)
        elif shape == "square":
            painter.fillRect(x - half, y - half, size, size, color)
        else:
            stamp = self._hard_stamp(size, shape, color)
            half = size // 2
            painter.drawImage(x - half, y - half, stamp)

    def draw_stroke(self, painter, p1, p2, skip_first=False):
        """Línea de Bresenham píxel a píxel, sin suavizado. Estampa una punta
        dura (1×1, cuadrado, o la forma elegida) en cada celda."""
        color = getattr(self, 'stroke_color', self.canvas.brush_color)
        size = max(1, int(getattr(self.canvas, 'pencil_size', 1)))
        shape = self._pencil_shape()

        if p1 == p2:
            if not skip_first:
                self._stamp_pixel(painter, p1.x(), p1.y(), color, size, shape)
            return

        x0, y0 = p1.x(), p1.y()
        x1, y1 = p2.x(), p2.y()
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        first = True
        while True:
            if not (skip_first and first):
                self._stamp_pixel(painter, x0, y0, color, size, shape)
            first = False
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy


class EraserTool(PenTool):
    """Borrador: resta alfa (DestinationOut) con dureza y forma de punta. En modo
    'borrador de color' solo borra donde el color coincide con el objetivo (primario
    o secundario segun el boton). La mascara de borrado para formas/color se genera
    con numpy (perfil de dureza + forma + AA, vectorizado); la goma redonda normal
    conserva el camino rapido con gradiente radial."""

    def __init__(self, canvas):
        super().__init__(canvas)
        self.tool_id = "eraser"
        self.history_name = t("tool.name.eraser")
        self._bg_fixed_target = None       # color fijo en modo "muestra única"
        self._bg_one_shot_sampled = False   # indica si ya se tomó la muestra

    def mouse_press(self, event):
        layer = self.canvas.get_active_layer_obj()
        if layer and getattr(layer, "alpha_locked", False) and not self.canvas.mask_edit_active:
            # En bloqueo de transparencia, el borrador se desactiva (o en PS
            # pintaría fondo, aquí ignoramos). AVISAR en la barra de estado:
            # antes fallaba en silencio y parecía que la goma estaba rota.
            win = self.canvas.window() if hasattr(self.canvas, "window") else None
            bar = getattr(win, 'status_bar', None)
            if bar is not None:
                bar.showMessage(t("status.eraser_alpha_lock"), 4000)
            self.image_before_stroke = None
            return

        self._bg_one_shot_sampled = False
        self._bg_fixed_target = None
        self._layer_buf = None
        bg_mode = getattr(self.canvas, 'eraser_bg_mode', False)
        one_shot = getattr(self.canvas, 'eraser_bg_one_shot', False)
        color_mode = getattr(self.canvas, 'eraser_color_mode', False)
        # En la máscara no hay borrador de fondos (opera sobre los píxeles de la capa).
        if bg_mode and one_shot and not self.canvas.paint_on_mask():
            zoom = self.canvas.zoom_factor
            pt = (event.position() / zoom).toPoint()
            self._bg_fixed_target = self._sample_layer_color(pt)
            self._bg_one_shot_sampled = True
        
        super().mouse_press(event)
        
        if (color_mode or bg_mode) and not getattr(self, '_paint_on_mask', False):
            layer = self.canvas.layers[self.canvas.active_layer_index].image
            self._layer_buf = qimage_to_bgra(layer).astype(np.int16)

    def mouse_release(self, event):
        super().mouse_release(event)
        self._bg_fixed_target = None
        self._bg_one_shot_sampled = False
        self._layer_buf = None

    def _eraser_shape(self):
        sh = getattr(self.canvas, 'eraser_shape', 'round')
        return sh if sh in SHAPES else 'round'

    def draw_stamp(self, painter, point, radius, color, hardness):
        if radius <= 0:
            return
        if radius < 0.6:
            radius = 0.6
        self._marcar_rect_sucio(point.x() - radius - 1,
                                point.y() - radius - 1,
                                point.x() + radius + 2,
                                point.y() + radius + 2)

        color_mode = getattr(self.canvas, 'eraser_color_mode', False)
        bg_mode = getattr(self.canvas, 'eraser_bg_mode', False)
        # Sobre la máscara, el borrador es siempre "normal" (resta gris); los
        # modos de color/fondos leen los píxeles de la capa y no aplican aquí.
        if getattr(self, '_paint_on_mask', False):
            color_mode = False
            bg_mode = False
        shape = self._eraser_shape()

        # Camino rapido para el caso comun (redondo, sin borrador de color ni
        # de fondos): gradiente radial con DestinationOut, como siempre.
        if not color_mode and not bg_mode and shape == 'round':
            painter.setCompositionMode(QPainter.CompositionMode_DestinationOut)
            erase_color = QColor(0, 0, 0, 255)
            gradient = QRadialGradient(point.x(), point.y(), radius)
            hf = hardness / 100.0
            gradient.setColorAt(0, erase_color)
            if hf < 1.0:
                if hf > 0:
                    gradient.setColorAt(hf, erase_color)
                steps = 8
                for i in range(1, steps + 1):
                    k = i / steps
                    pos = hf + (1.0 - hf) * k
                    gradient.setColorAt(pos, QColor(0, 0, 0, int(255 * ((1.0 - k) ** 3))))
            else:
                gradient.setColorAt(1.0, erase_color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(gradient))
            painter.drawEllipse(point, radius, radius)
            return

        # Camino numpy: formas no redondas y/o borrador de color/fondos.
        if bg_mode:
            # Borrador de FONDOS: muestrea el color del "punto caliente".
            # En modo "muestra única" se usa el color fijado al pulsar;
            # en el modo continuo se re-muestrea en cada estampa.
            one_shot = getattr(self.canvas, 'eraser_bg_one_shot', False)
            if one_shot and self._bg_one_shot_sampled:
                target = self._bg_fixed_target
            else:
                target = self._sample_layer_color(point)
            if target is None:
                return
        elif color_mode:
            # Borrador de COLOR: objetivo fijo (primario/secundario via stroke_color).
            target = getattr(self, 'stroke_color', self.canvas.brush_color)
        else:
            target = None
        self._erase_stamp(painter, point, radius, hardness, shape, target)

    def _erase_stamp(self, painter, point, radius, hardness, shape, target):
        """Estampa de borrado vectorizada: mascara = kernel(forma, dureza) [x match de
        color]. Se aplica con DestinationOut respetando la seleccion (clip del painter)."""
        kernel = get_kernel(radius, hardness, shape)   # KxK [0..1]
        R = (kernel.shape[0] - 1) // 2
        layer = self.canvas.layers[self.canvas.active_layer_index].image
        W, H = layer.width(), layer.height()
        px, py = point.x(), point.y()
        x0, y0 = px - R, py - R
        cx0, cy0 = max(0, x0), max(0, y0)
        cx1, cy1 = min(W, px + R + 1), min(H, py + R + 1)
        if cx1 <= cx0 or cy1 <= cy0:
            return
        ksub = kernel[cy0 - y0:cy1 - y0, cx0 - x0:cx1 - x0].astype(np.float32)

        if target is not None and getattr(self, '_layer_buf', None) is not None:
            # Anular la fuerza de borrado donde el color NO coincide (Chebyshev RGB,
            # ignorando alfa para borrar tambien los bordes suavizados del color).
            arr = self._layer_buf[cy0:cy1, cx0:cx1]
            tol = int(getattr(self.canvas, 'eraser_color_tolerance', 32))
            tr, tg, tb = target.red(), target.green(), target.blue()
            match = ((np.abs(arr[..., 2] - tr) <= tol) &
                     (np.abs(arr[..., 1] - tg) <= tol) &
                     (np.abs(arr[..., 0] - tb) <= tol))
            # "Proteger primario": en modo borrador de fondos, no borrar los
            # píxeles cuyo color coincide con el color primario.
            if (getattr(self.canvas, 'eraser_bg_mode', False) and
                    getattr(self.canvas, 'eraser_bg_protect_primary', False)):
                pc = self.canvas.brush_color
                protect = ((np.abs(arr[..., 2] - pc.red()) <= tol) &
                           (np.abs(arr[..., 1] - pc.green()) <= tol) &
                           (np.abs(arr[..., 0] - pc.blue()) <= tol))
                match = match & ~protect
            ksub = ksub * match

        a = np.clip(ksub * 255.0 + 0.5, 0, 255).astype(np.uint8)
        mask = np.zeros((a.shape[0], a.shape[1], 4), dtype=np.uint8)
        mask[..., 3] = a
        erase_img = bgra_to_qimage(mask)

        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
        painter.drawImage(cx0, cy0, erase_img)

    def _sample_layer_color(self, point):
        """Color de la capa activa bajo el centro de la brocha (el 'punto
        caliente' del borrador de fondos). Devuelve None si ese pixel ya es
        transparente: en ese caso no hay fondo que borrar y el trazo se salta
        esa estampa (no convertirlo en borrado normal)."""
        try:
            layer = self.canvas.layers[self.canvas.active_layer_index].image
        except (IndexError, AttributeError):
            return None
        w, h = layer.width(), layer.height()
        if w <= 0 or h <= 0:
            return None
        x = min(max(int(point.x()), 0), w - 1)
        y = min(max(int(point.y()), 0), h - 1)
        col = layer.pixelColor(x, y)
        if col.alpha() == 0:
            return None
        return col


class ReplaceColorTool(PenTool):
    """Sustituir color: reemplaza el color muestreado bajo el PRIMER clic por el
    color primario (o el secundario con el botón derecho), SOLO en los píxeles
    cuyo color coincide con el objetivo dentro de la tolerancia.

    Motor de COBERTURA vectorizado (numpy), igual que el Pincel: el trazo acumula
    su cobertura (máximo por estampa) RESTRINGIDA a los píxeles coincidentes
    -calculados una sola vez sobre la imagen original- y se recompone una sola vez
    desde el original. Así el reemplazo es uniforme, sin bordes ni "serpiente de
    círculos", sea cual sea la dureza, y respeta forma de punta y selección.

    Tamaño y Espaciado se comparten con el Pincel; Tolerancia, Forma, Dureza,
    "Contigua" (solo la mancha conectada) y "Todas las capas" son propias y viven
    en el canvas (replace_*)."""

    def __init__(self, canvas):
        super().__init__(canvas)
        self.tool_id = "replace_color"
        self.history_name = t("tool.name.replace_color")
        self.replace_target = None
        self._match = None
        self._press_point = None

    # ---- ratón ----
    def mouse_press(self, event):
        if event.button() not in (Qt.LeftButton, Qt.RightButton):
            return
        self.stroke_color = (self.canvas.brush_color if event.button() == Qt.LeftButton
                             else self.canvas.brush_color_secondary)

        zoom = self.canvas.zoom_factor
        pos = event.position() / zoom
        point = QPoint(math.floor(pos.x()), math.floor(pos.y()))
        self.last_point = point
        self._press_point = point

        layer_obj = self.canvas.layers[self.canvas.active_layer_index]
        self.image_before_stroke = QImage(layer_obj.image)
        self.distance_carried = 0.0
        self._kernel_cache = {}
        self._dirty_rect = None

        # Imagen de muestreo: capa activa o composición de todas las capas
        # (fondo TRANSPARENTE, como varita/cubo: el blanco por defecto
        # falseaba el color de las zonas semitransparentes)
        sample_all = getattr(self.canvas, "replace_sample_all", False)
        if sample_all and hasattr(self.canvas, "render_flat_image"):
            src = self.canvas.render_flat_image(Qt.transparent)
        else:
            src = self.image_before_stroke
        x, y = point.x(), point.y()
        if not (0 <= x < src.width() and 0 <= y < src.height()):
            self.replace_target = None
            self.image_before_stroke = None   # no se inicia trazo
            return
        self.replace_target = QColor(src.pixel(x, y))

        H, W = self.image_before_stroke.height(), self.image_before_stroke.width()
        self._coverage = CoberturaDispersa(W, H)
        self._match = self._build_match_mask(src)
        self._rc_stamp(point)
        self.canvas.update()

    def mouse_move(self, event):
        if not (event.buttons() & (Qt.LeftButton | Qt.RightButton)):
            return
        if self.image_before_stroke is None or self._match is None:
            return
        zoom = self.canvas.zoom_factor
        current = (event.position() / zoom).toPoint()
        self._rc_stroke(self.last_point, current)
        self.last_point = current
        self.canvas.update()

    def mouse_release(self, event):
        super().mouse_release(event)   # registra el PaintCommand y limpia buffers
        self._match = None
        self.replace_target = None

    # ---- matching de color (vectorizado) ----
    def _build_match_mask(self, src):
        """Máscara float (0/1) de píxeles cuyo color coincide con el objetivo
        dentro de la tolerancia (Chebyshev RGB). Con "Contigua", se queda solo
        con la mancha conectada al punto pulsado (4-conectividad, scipy)."""
        arr = qimage_to_bgra(src.convertToFormat(QImage.Format.Format_ARGB32))
        b = arr[..., 0].astype(np.int16)
        g = arr[..., 1].astype(np.int16)
        r = arr[..., 2].astype(np.int16)
        t = self.replace_target
        tol = int(getattr(self.canvas, "replace_tolerance", 32))
        match = ((np.abs(r - t.red()) <= tol) &
                 (np.abs(g - t.green()) <= tol) &
                 (np.abs(b - t.blue()) <= tol))

        if getattr(self.canvas, "replace_contiguous", False):
            from scipy import ndimage
            struct = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=np.uint8)
            labels, _ = ndimage.label(match, structure=struct)
            sx, sy = self._press_point.x(), self._press_point.y()
            inside = (0 <= sy < labels.shape[0] and 0 <= sx < labels.shape[1])
            comp = labels[sy, sx] if inside else 0
            match = (labels == comp) if comp != 0 else np.zeros_like(match)

        return match.astype(np.float32)

    # ---- trazo por cobertura (restringida al matching) ----
    def _rc_stroke(self, p1, p2):
        size = self.canvas.brush_size
        spacing_percent = getattr(self.canvas, "brush_spacing", 10)
        line = QLineF(p1, p2)
        length = line.length()
        if length == 0:
            self._rc_stamp(p2)
            return
        step = max(1.0, size * (spacing_percent / 100.0))
        d = step - self.distance_carried
        while d <= length:
            self._rc_stamp(line.pointAt(d / length).toPoint())
            d += step
        self.distance_carried = length - (d - step)

    def _rc_stamp(self, point):
        size = self.canvas.brush_size
        radius = max(0.6, size / 2.0)
        hardness = getattr(self.canvas, "replace_hardness", 100)
        shape = getattr(self.canvas, "replace_shape", "round")
        if shape not in SHAPES:
            shape = "round"
        kernel = self._get_kernel(radius, hardness, shape)
        R = (kernel.shape[0] - 1) // 2
        px, py = point.x(), point.y()
        H, W = self._coverage.alto, self._coverage.ancho
        x0, y0 = px - R, py - R
        cx0, cy0 = max(0, x0), max(0, y0)
        cx1, cy1 = min(W, px + R + 1), min(H, py + R + 1)
        if cx1 <= cx0 or cy1 <= cy0:
            return
        ksub = kernel[cy0 - y0:cy1 - y0, cx0 - x0:cx1 - x0]
        msub = self._match[cy0:cy1, cx0:cx1]
        self._coverage.maximo(cx0, cy0, ksub * msub)
        self._marcar_rect_sucio(cx0, cy0, cx1, cy1)
        self._recompose(cx0, cy0, cx1, cy1)
