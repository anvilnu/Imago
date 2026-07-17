# tools/clone_tool.py
from i18n import t
import numpy as np
from PySide6.QtGui import QPainter, QImage, QColor, QPen
from PySide6.QtCore import Qt, QPoint, QLineF
from tools.draw_tools import PenTool
from tools.numpy_utils import SHAPES, get_kernel, qimage_to_bgra, bgra_to_qimage
from tools.commands import PaintCommand
from tools.roi_buffers import CoberturaDispersa


class CloneTool(PenTool):
    """Sello de clonar (tampón) con MOTOR DE COBERTURA (numpy).

    Uso (estilo Paint.NET / Photoshop):
      1. Ctrl + clic izquierdo  → fija el punto de ORIGEN.
      2. Clic izquierdo y arrastra → clona desde el origen al destino.

    El trazo acumula por teselas su cobertura (máximo por estampa, con forma y dureza del
    pincel) y se compone UNA sola vez copiando los píxeles del origen desplazado:
    así no hay costuras ni dobles bordes en los solapes (a diferencia del estampado
    repetido). Muestrea la foto de la capa (o de todas, según opción) tomada al
    EMPEZAR el trazo, evitando el emborronado por realimentación.

    Modos:
      - Alineado (por defecto): el desfase origen→destino se fija una vez y persiste
        entre trazos (el origen acompaña al pincel) hasta fijar un nuevo origen.
      - No alineado: cada trazo vuelve a clonar desde el origen fijo.
    """

    def __init__(self, canvas):
        super().__init__(canvas)
        self.tool_id = "clone"
        self.history_name = t("tool.name.clone")
        self.source_point = None    # Origen (coords de lienzo) o None
        self.offset = None          # Desfase persistente (modo alineado) o None
        self.cursor_point = None    # Última posición del ratón
        self._stroke_offset = None  # Desfase activo durante el trazo en curso
        self._stroking = False
        self._before = None         # Foto de la capa activa al empezar el trazo
        self._src_img = None        # Imagen de muestreo (capa o composición)
        self._coverage = None
        self._kernel_cache = {}
        self._dirty_rect = None
        self.distance_carried = 0.0

    # ------------------------------------------------------------- ratón
    def mouse_press(self, event):
        zoom = self.canvas.zoom_factor

        # 1) Ctrl + clic izquierdo: fijar el ORIGEN (no clona en este gesto)
        if (event.modifiers() & Qt.ControlModifier) and event.button() == Qt.LeftButton:
            self.source_point = (event.position() / zoom).toPoint()
            self.offset = None     # nuevo origen → se vuelve a fijar el desfase
            self.canvas.update()
            return

        # 2) Solo clonamos con el botón izquierdo
        if event.button() != Qt.LeftButton:
            return

        # 3) Sin origen definido: avisar y salir
        if self.source_point is None:
            from widgets.custom_titlebar import imago_warning
            imago_warning(
                self.canvas.window(), t("msg.clone.no_source.title"),
                t("msg.clone.no_source.body"))
            return

        dest = (event.position() / zoom).toPoint()
        aligned = getattr(self.canvas, 'clone_aligned', True)
        if aligned:
            if self.offset is None:
                self.offset = dest - self.source_point
            self._stroke_offset = self.offset
        else:
            self._stroke_offset = dest - self.source_point   # cada trazo desde el origen

        self._begin_stroke()
        self.cursor_point = dest
        self.last_point = dest
        self._clone_stamp(dest)        # primer punto
        self.canvas.update()

    def mouse_move(self, event):
        self.cursor_point = (event.position() / self.canvas.zoom_factor).toPoint()
        if self._stroking:
            self._clone_stroke(self.last_point, self.cursor_point)
            self.last_point = self.cursor_point
        # En reposo, refrescar para que el marcador de origen siga al ratón
        self.canvas.update()

    def mouse_release(self, event):
        self._commit()

    def finish_editing(self):
        # Si se cambia de herramienta con el ratón aún pulsado, cerramos limpio.
        self._commit()

    def _commit(self):
        if not self._stroking:
            return
        self._stroking = False
        after = QImage(self.canvas.get_active_layer())
        self.canvas.undo_stack.push(PaintCommand(
            self.canvas, self.canvas.active_layer_index, self._before, after,
            self.history_name, tool_id="clone", confine=True,
            dirty_rect=self._dirty_rect))
        self._before = None
        self._src_img = None
        self._coverage = None
        self._kernel_cache = {}
        self._dirty_rect = None

    # ------------------------------------------------------------- motor
    def _begin_stroke(self):
        layer = self.canvas.get_active_layer()
        self._before = QImage(layer)
        if getattr(self.canvas, 'clone_sample_all', False) and hasattr(self.canvas, 'render_flat_image'):
            # Fondo TRANSPARENTE (como varita/cubo): con el blanco por defecto,
            # clonar zonas transparentes estampaba píxeles blanqueados.
            self._src_img = self.canvas.render_flat_image(Qt.transparent)
        else:
            self._src_img = self._before
        self._coverage = CoberturaDispersa(
            self._before.width(), self._before.height())
        self._kernel_cache = {}
        self.distance_carried = 0.0
        self._dirty_rect = None
        self._stroking = True

    def _clone_stroke(self, p1, p2):
        size = self.canvas.brush_size
        spacing = getattr(self.canvas, 'brush_spacing', 10)
        line = QLineF(p1, p2)
        length = line.length()
        if length == 0:
            rect = self._clone_stamp(p2)
            if rect: self._recompose(*rect)
            return
        step = max(1.0, size * (spacing / 100.0))
        d = step - self.distance_carried
        bx0, by0, bx1, by1 = 999999, 999999, -999999, -999999
        while d <= length:
            rect = self._clone_stamp(line.pointAt(d / length).toPoint())
            if rect:
                x0, y0, x1, y1 = rect
                bx0 = min(bx0, x0); by0 = min(by0, y0)
                bx1 = max(bx1, x1); by1 = max(by1, y1)
            d += step
        self.distance_carried = length - (d - step)
        if bx0 < bx1 and by0 < by1:
            self._recompose(bx0, by0, bx1, by1)

    def _clone_stamp(self, point):
        radius = max(0.6, self.canvas.brush_size / 2.0)
        hardness = getattr(self.canvas, 'brush_hardness', 100)
        shape = getattr(self.canvas, 'clone_shape', 'round')
        if shape not in SHAPES:
            shape = 'round'
        kernel = get_kernel(radius, hardness, shape)
        R = (kernel.shape[0] - 1) // 2
        px, py = point.x(), point.y()
        H, W = self._coverage.alto, self._coverage.ancho
        x0, y0 = px - R, py - R
        cx0, cy0 = max(0, x0), max(0, y0)
        cx1, cy1 = min(W, px + R + 1), min(H, py + R + 1)
        if cx1 <= cx0 or cy1 <= cy0:
            return None
        ksub = kernel[cy0 - y0:cy1 - y0, cx0 - x0:cx1 - x0]
        self._coverage.maximo(cx0, cy0, ksub)
        if self._dirty_rect is None:
            self._dirty_rect = [cx0, cy0, cx1, cy1]
        else:
            rect = self._dirty_rect
            rect[0] = min(rect[0], cx0); rect[1] = min(rect[1], cy0)
            rect[2] = max(rect[2], cx1); rect[3] = max(rect[3], cy1)
        return (cx0, cy0, cx1, cy1)

    def _recompose(self, x0, y0, x1, y1):
        """capa = destino-original SOBRE origen·cobertura (vectorizado). El origen
        es la imagen de muestreo desplazada por el offset del trazo; lo que caiga
        fuera de ella no se clona."""
        w, h = x1 - x0, y1 - y0
        o = qimage_to_bgra(
            self._before.copy(x0, y0, w, h).convertToFormat(QImage.Format.Format_ARGB32)
        ).astype(np.float32)

        ox, oy = self._stroke_offset.x(), self._stroke_offset.y()
        sx0, sy0 = x0 - ox, y0 - oy
        src = np.zeros((h, w, 4), dtype=np.float32)
        SW, SH = self._src_img.width(), self._src_img.height()
        vx0, vy0 = max(0, sx0), max(0, sy0)
        vx1, vy1 = min(SW, sx0 + w), min(SH, sy0 + h)
        if vx1 > vx0 and vy1 > vy0:
            sub = qimage_to_bgra(
                self._src_img.copy(vx0, vy0, vx1 - vx0, vy1 - vy0).convertToFormat(QImage.Format.Format_ARGB32)
            ).astype(np.float32)
            dx, dy = vx0 - sx0, vy0 - sy0
            src[dy:dy + (vy1 - vy0), dx:dx + (vx1 - vx0), :] = sub

        cov = self._coverage.region(x0, y0, x1, y1)
        src_a = src[..., 3] / 255.0
        sa = cov * src_a                 # alfa efectivo del clon (cobertura × alfa origen)
        oa = o[..., 3] / 255.0
        # 🔒 Bloqueo de transparencia (SourceAtop a mano; el modo Source del
        # volcado pisa el de apply_selection_clip): el clon se pesa por el alfa
        # original de la capa, que se conserva sin cambios.
        lock = self.canvas.alpha_lock_active()
        if lock:
            sa = sa * oa
        inv = 1.0 - sa
        out_a = sa + oa * inv

        res = np.empty_like(o)
        with np.errstate(divide='ignore', invalid='ignore'):
            for idx in (0, 1, 2):
                premult = src[..., idx] * sa + o[..., idx] * oa * inv
                res[..., idx] = np.where(out_a > 1e-6, premult / out_a, 0.0)
        res[..., 3] = o[..., 3] if lock else out_a * 255.0
        out8 = np.clip(res + 0.5, 0, 255).astype(np.uint8)
        out_img = bgra_to_qimage(out8)

        layer = self.canvas.get_active_layer()
        painter = QPainter(layer)
        self.canvas.apply_selection_clip(painter)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.drawImage(x0, y0, out_img)
        painter.end()

    # ------------------------------------------------------------- marcador
    def draw_preview(self, painter):
        """Marca la zona de ORIGEN (forma del pincel + cruz). Sigue al ratón
        (cursor − desfase) una vez fijado; si no, muestra el origen recién fijado."""
        if self.source_point is None:
            return
        shape = getattr(self.canvas, 'clone_shape', 'round')
        if shape not in SHAPES:
            shape = 'round'
        aligned = getattr(self.canvas, 'clone_aligned', True)
        if self._stroking and self._stroke_offset is not None and self.cursor_point is not None:
            center = self.cursor_point - self._stroke_offset
        elif aligned and self.offset is not None and self.cursor_point is not None:
            center = self.cursor_point - self.offset
        else:
            center = self.source_point

        r = max(0.6, self.canvas.brush_size / 2.0)
        ext = r + 3
        cx, cy = center.x(), center.y()
        path = self._shape_path(QPoint(int(cx), int(cy)), r, shape)

        painter.save()
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(255, 255, 255), 0))         # halo blanco
        painter.drawPath(path)
        painter.drawLine(int(cx - ext), int(cy), int(cx + ext), int(cy))
        painter.drawLine(int(cx), int(cy - ext), int(cx), int(cy + ext))
        painter.setPen(QPen(QColor(0, 0, 0), 0, Qt.DotLine))   # negro punteado
        painter.drawPath(path)
        painter.drawLine(int(cx - ext), int(cy), int(cx + ext), int(cy))
        painter.drawLine(int(cx), int(cy - ext), int(cx), int(cy + ext))
        painter.restore()
