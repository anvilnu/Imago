# tools/bucket_tool.py
import math
import numpy as np
from scipy import ndimage
from PySide6.QtGui import QPainter, QImage, QColor, QBrush
from PySide6.QtCore import Qt, QPoint
from i18n import t
from tools.base_tool import BaseTool
from tools.numpy_utils import build_flood_fill_mask
from tools.commands import PaintCommand
from tools import pattern_tiles


class BucketTool(BaseTool):
    """Cubo de pintura (relleno por inundación).

    Motor numpy + scipy: la máscara de píxeles similares se calcula de forma
    vectorizada y la región contigua con scipy.ndimage.label (4-conectividad),
    en vez de recorrer píxel a píxel en Python. Si por lo que fuera fallara la
    conversión de buffers, recurre al método clásico (más lento) sin romperse.

    Opciones (en el lienzo): tolerancia, modo Local/Global (contigua o todos los
    píxeles similares), suavizado de bordes (antialiasing) y muestrear todas las
    capas (toma el color de lo visible, pero rellena en la capa activa)."""

    def __init__(self, canvas):
        super().__init__(canvas)
        self.tool_id = "bucket"
        self.history_name = t("tool.name.bucket")
        self.tolerance = 32   # respaldo si el lienzo no trae bucket_tolerance

    def _opts(self):
        c = self.canvas
        return (int(getattr(c, "bucket_tolerance", self.tolerance)),
                bool(getattr(c, "bucket_contiguous", True)),
                bool(getattr(c, "bucket_antialias", False)),
                bool(getattr(c, "bucket_sample_all", False)),
                int(getattr(c, "bucket_expand", 0)))

    def mouse_press(self, event):
        if event.button() not in (Qt.LeftButton, Qt.RightButton):
            return
        fill_color = (self.canvas.brush_color if event.button() == Qt.LeftButton
                      else self.canvas.brush_color_secondary)

        zoom = self.canvas.zoom_factor
        pos = event.position() / zoom
        # floor: el píxel bajo el cursor es el que lo CONTIENE (mismo criterio
        # que la varita mágica)
        start_point = QPoint(math.floor(pos.x()), math.floor(pos.y()))

        # 🎭 Destino: máscara (Grayscale8) o píxeles de la capa.
        on_mask = self.canvas.paint_on_mask()
        image = self.canvas.paint_target()
        width, height = image.width(), image.height()
        if not (0 <= start_point.x() < width and 0 <= start_point.y() < height):
            return

        tol, contiguous, antialias, sample_all, expand = self._opts()

        # Imagen de la que se TOMA el color de muestra. Sobre la máscara se
        # muestrea la propia máscara (no la composición de capas).
        if sample_all and not on_mask and hasattr(self.canvas, "render_flat_image"):
            sample = self.canvas.render_flat_image(Qt.transparent)
        else:
            sample = image

        image_before = QImage(image)
        pattern_style = getattr(self.canvas, "bucket_pattern", Qt.BrushStyle.SolidPattern)

        dirty = self.execute_flood_fill(
            image, sample, start_point, fill_color,
            pattern_style, tol, contiguous, antialias, expand)

        image_after = QImage(image)
        self.canvas.undo_stack.push(PaintCommand(
            self.canvas, self.canvas.active_layer_index,
            image_before, image_after, self.history_name, tool_id=self.tool_id,
            target=("mask" if on_mask else "image"), confine=True,
            dirty_rect=dirty))
        self.canvas.update()

    # ------------------------------------------------------------------
    def _make_fill_brush(self, fill_color, pattern_raw):
        """QBrush del relleno: azulejo de textura procedural si el patrón es
        personalizado (tablero, ladrillo...), o estilo nativo de Qt si no."""
        if isinstance(pattern_raw, str) and pattern_raw in pattern_tiles.CUSTOM_PATTERN_IDS:
            bg = (pattern_tiles.other_color(fill_color, self.canvas.brush_color,
                                            self.canvas.brush_color_secondary)
                  if pattern_tiles.is_two_tone(pattern_raw) else None)
            return QBrush(pattern_tiles.make_tile(pattern_raw, fill_color, bg))
        return QBrush(fill_color, self._resolve_pattern_style(pattern_raw))

    def _resolve_pattern_style(self, pattern_style):
        """Convierte el patrón a enum de Qt venga como enum o como string."""
        if isinstance(pattern_style, Qt.BrushStyle):
            return pattern_style
        if isinstance(pattern_style, str):
            mapping = {
                "solid": Qt.BrushStyle.SolidPattern,
                "horizontal": Qt.BrushStyle.HorPattern,
                "vertical": Qt.BrushStyle.VerPattern,
                "fdiag": Qt.BrushStyle.FDiagPattern,
                "bdiag": Qt.BrushStyle.BDiagPattern,
                "cross": Qt.BrushStyle.CrossPattern,
                "diagcross": Qt.BrushStyle.DiagCrossPattern,
            }
            return mapping.get(pattern_style, Qt.BrushStyle.SolidPattern)
        return Qt.BrushStyle.SolidPattern

    def execute_flood_fill(self, image, sample, start_pt, fill_color,
                           pattern_style, tol=32, contiguous=True, antialias=False,
                           expand=0):
        """Genera la máscara de relleno (numpy) y compone el color/patrón sobre
        la capa activa, respetando la selección. Si algo falla, usa el clásico."""
        try:
            return self._flood_fill_numpy(
                image, sample, start_pt, fill_color,
                pattern_style, tol, contiguous, antialias, expand)
        except Exception:
            # Red de seguridad: relleno clásico (contiguo, capa activa, sin AA
            # ni expansión). Se REGISTRA el motivo en imago_crash.log: sin esto,
            # un bug del motor numpy pasaría desapercibido (solo se notaría
            # que el cubo va lento y sin opciones).
            import traceback, datetime
            try:
                from main import _log_crash
                _log_crash("\n===== Cubo: fallo del motor numpy %s =====\n%s"
                           % (datetime.datetime.now().isoformat(),
                              traceback.format_exc()))
            except Exception:
                pass
            target_rgba = image.pixel(start_pt)
            return self._flood_fill_dfs(
                image, start_pt, target_rgba, fill_color, pattern_style, tol)

    def _flood_fill_numpy(self, image, sample, start_pt, fill_color,
                          pattern_style, tol, contiguous, antialias, expand=0):
        W, H = image.width(), image.height()

        region = build_flood_fill_mask(sample, start_pt, tol, contiguous)

        # Expansión: ensancha el relleno N px bajo el contorno, para que no
        # quede el halo claro pegado a las líneas antialiasadas (colorear
        # dibujos). Distancia euclídea: crece parejo en todas direcciones.
        if expand > 0 and region.any():
            region = ndimage.distance_transform_edt(~region) <= expand

        # Cobertura (canal alfa de la máscara): dura o suavizada en el borde
        if antialias:
            cov = ndimage.gaussian_filter(region.astype(np.float32), sigma=0.7)
            cov = np.maximum(cov, region.astype(np.float32))  # interior siempre opaco
            alpha = np.clip(cov * 255.0, 0, 255).astype(np.uint32)
        else:
            alpha = np.where(region, np.uint32(255), np.uint32(0))

        # Caja sin materializar dos vectores de coordenadas por cada píxel
        # relleno (np.nonzero sobre 20 MP podría añadir cientos de MB).
        rows = np.flatnonzero(alpha.any(axis=1))
        if rows.size == 0:
            dirty = None
        else:
            y0, y1 = int(rows[0]), int(rows[-1])
            cols = np.flatnonzero(alpha[y0:y1 + 1].any(axis=0))
            dirty = (int(cols[0]), y0, int(cols[-1]) + 1, y1 + 1)

        # Máscara ARGB32: negro con alfa = cobertura (0xAA000000)
        mask_u32 = np.ascontiguousarray((alpha << 24).astype(np.uint32))
        mask_img = QImage(mask_u32.data, W, H, W * 4, QImage.Format.Format_ARGB32)

        # Capa con el color/patrón, recortada por la máscara (DestinationIn)
        pattern_layer = QImage(W, H, QImage.Format.Format_ARGB32)
        pattern_layer.fill(Qt.GlobalColor.transparent)
        pp = QPainter(pattern_layer)
        pp.setBrush(self._make_fill_brush(fill_color, pattern_style))
        pp.setPen(Qt.PenStyle.NoPen)
        pp.drawRect(0, 0, W, H)
        pp.setCompositionMode(QPainter.CompositionMode_DestinationIn)
        pp.drawImage(0, 0, mask_img)
        pp.end()

        # Volcar sobre la capa activa, respetando la selección
        lp = QPainter(image)
        self.canvas.apply_selection_clip(lp)
        lp.drawImage(0, 0, pattern_layer)
        lp.end()
        return dirty

    # ------------------------------------------------------------------
    # Respaldo clásico (sin numpy): relleno por inundación píxel a píxel
    # ------------------------------------------------------------------
    def _flood_fill_dfs(self, image, start_pt, target_rgba, fill_color, pattern_style, tol):
        width, height = image.width(), image.height()
        opaque_black = QColor(0, 0, 0, 255).rgba()

        stack = [(start_pt.x(), start_pt.y())]
        visited = bytearray(width * height)
        mask = QImage(width, height, QImage.Format.Format_ARGB32)
        mask.fill(Qt.GlobalColor.transparent)
        min_x, min_y, max_x, max_y = width, height, -1, -1

        while stack:
            cx, cy = stack.pop()
            idx = cy * width + cx
            if visited[idx]:
                continue
            visited[idx] = 1
            if self.is_pixel_similar(image.pixel(cx, cy), target_rgba, tol):
                mask.setPixel(cx, cy, opaque_black)
                min_x = min(min_x, cx); min_y = min(min_y, cy)
                max_x = max(max_x, cx); max_y = max(max_y, cy)
                if cx > 0: stack.append((cx - 1, cy))
                if cx < width - 1: stack.append((cx + 1, cy))
                if cy > 0: stack.append((cx, cy - 1))
                if cy < height - 1: stack.append((cx, cy + 1))

        pattern_layer = QImage(width, height, QImage.Format.Format_ARGB32)
        pattern_layer.fill(Qt.GlobalColor.transparent)
        p_painter = QPainter(pattern_layer)
        p_painter.setBrush(self._make_fill_brush(fill_color, pattern_style))
        p_painter.setPen(Qt.PenStyle.NoPen)
        p_painter.drawRect(0, 0, width, height)
        p_painter.setCompositionMode(QPainter.CompositionMode_DestinationIn)
        p_painter.drawImage(0, 0, mask)
        p_painter.end()

        layer_painter = QPainter(image)
        self.canvas.apply_selection_clip(layer_painter)
        layer_painter.drawImage(0, 0, pattern_layer)
        layer_painter.end()
        if max_x < min_x or max_y < min_y:
            return None
        return (min_x, min_y, max_x + 1, max_y + 1)

    def is_pixel_similar(self, current_rgba, target_rgba, tolerance):
        """Distancia Chebyshev por canal RGBA (incluye alfa para no desbordar
        sobre negros). Misma métrica que build_flood_fill_mask."""
        if current_rgba == target_rgba:
            return True
        if tolerance == 0:
            return False
        a1 = (current_rgba >> 24) & 0xFF
        r1, g1, b1 = (current_rgba >> 16) & 0xFF, (current_rgba >> 8) & 0xFF, current_rgba & 0xFF
        a2 = (target_rgba >> 24) & 0xFF
        r2, g2, b2 = (target_rgba >> 16) & 0xFF, (target_rgba >> 8) & 0xFF, target_rgba & 0xFF
        return max(abs(r1 - r2), abs(g1 - g2), abs(b1 - b2), abs(a1 - a2)) <= tolerance
