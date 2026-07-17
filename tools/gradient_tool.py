# tools/gradient_tool.py
from i18n import t
import math
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QImage
from tools.base_tool import BaseTool
from tools.commands import PaintCommand


class GradientTool(BaseTool):
    """Degradado. Arrastra para aplicarlo según el patrón elegido: Lineal,
    Lineal reflejado, Radial, Rombo, Cuadrado (caja), Cónico, Espiral (horario)
    y Espiral (antihorario).

    - Del color primario al secundario. Botón derecho: invertido.
    - Si hay selección, se limita a ella; si no, a toda la capa activa.
    - EDITABLE EN VIVO: tras soltar, el degradado sigue activo; cambiar patrón,
      color o modo lo recalcula al instante. Un nuevo arrastre lo recoloca.
      Enter o cambiar de herramienta confirma; Esc cancela.
    - Modo Color (primario→secundario) o Transparencia (primario→transparente).
    - Opción de suavizar bandas (dithering) para degradados largos.
    """

    SPINS = 2.0   # número de vueltas de las espirales

    def __init__(self, canvas):
        super().__init__(canvas)
        self.tool_id = "gradient"
        self._dragging = False
        self._live = False           # degradado aplicado y aún editable
        self._start = None
        self._end = None
        self._before = None
        self._button = None          # botón usado (orden de color)
        self._W = self._H = 0
        self._px = None
        self._py = None
        self._buf = None             # mantiene viva la memoria del array para QImage
        self._on_mask = False        # 🎭 True si el degradado se aplica a la máscara

    # ------------------------------------------------------------- ratón
    def mouse_press(self, event):
        if event.button() not in (Qt.LeftButton, Qt.RightButton):
            return
        img = self.canvas.paint_target()
        if img is None:
            return
        self._on_mask = self.canvas.paint_on_mask()
        self._button = event.button()
        self._start = event.position() / self.canvas.zoom_factor
        self._end = self._start
        self._W, self._H = img.width(), img.height()
        ys, xs = np.mgrid[0:self._H, 0:self._W]
        self._px = (xs - self._start.x()).astype(np.float32)
        self._py = (ys - self._start.y()).astype(np.float32)
        # Solo capturamos la base si no hay un degradado vivo (así un nuevo
        # arrastre recoloca sobre la MISMA base, sin acumular).
        if not self._live:
            self._before = QImage(img)
        self._dragging = True

    def mouse_move(self, event):
        if self._dragging:
            self._end = event.position() / self.canvas.zoom_factor
            self._render()

    def mouse_release(self, event):
        if not self._dragging:
            return
        self._dragging = False
        self._end = event.position() / self.canvas.zoom_factor
        dist = math.hypot(self._end.x() - self._start.x(),
                          self._end.y() - self._start.y())
        if dist < 1.0:
            # Clic sin arrastre: si no había degradado vivo, no hacer nada;
            # si lo había, se mantiene el actual.
            if not self._live:
                self._restore()
                self._cleanup()
            return
        self._render()
        self._live = True

    def finish_editing(self):
        # Cambio de herramienta: confirmar lo que haya en curso.
        if self._dragging or self._live:
            self._dragging = False
            self._commit()

    def key_press(self, event):
        if not (self._live or self._dragging):
            return False
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._dragging = False
            self._commit()
            return True
        if event.key() == Qt.Key_Escape:
            self._dragging = False
            self._restore()
            self._cleanup()
            return True
        return False

    def refresh_live(self):
        """Re-renderiza si el degradado está activo (cambio de patrón/color/modo)."""
        if (self._dragging or self._live) and self._start is not None and self._end is not None:
            self._render()

    # --------------------------------------------------------- internos
    def _commit(self):
        after = QImage(self.canvas.paint_target())
        if self._before is not None:
            dirty = self.canvas._selection_dirty_rect()
            if dirty is None:
                dirty = (0, 0, after.width(), after.height())
            self.canvas.undo_stack.push(PaintCommand(
                self.canvas, self.canvas.active_layer_index,
                self._before, after, t("hist.gradient"), tool_id="gradient",
                target=("mask" if self._on_mask else "image"), confine=True,
                dirty_rect=dirty))
        self._cleanup()

    def _write_target(self, img):
        """Escribe el resultado en la máscara o en los píxeles de la capa."""
        layer = self.canvas.layers[self.canvas.active_layer_index]
        if self._on_mask:
            layer.mask = img
        else:
            layer.image = img

    def _cleanup(self):
        self._dragging = False
        self._live = False
        self._before = None
        self._start = self._end = None
        self._px = self._py = self._buf = None

    def _restore(self):
        if self._before is not None:
            self._write_target(QImage(self._before))
            self.canvas.update()

    def _rgba(self, c):
        return (c.red(), c.green(), c.blue(), c.alpha())

    def _colors(self):
        prim = self._rgba(self.canvas.brush_color)
        sec = self._rgba(self.canvas.brush_color_secondary)
        return (prim, sec) if self._button == Qt.LeftButton else (sec, prim)

    def _pattern(self):
        return getattr(self.canvas, 'gradient_pattern', "Lineal")

    def _mode(self):
        return getattr(self.canvas, 'gradient_mode', "Color")

    def _dither(self):
        return bool(getattr(self.canvas, 'gradient_dither', False))

    def _render(self):
        if self._start is None or self._end is None or self._before is None:
            return
        grad = self._build_qimage()
        result = QImage(self._before)
        p = QPainter(result)
        sel = getattr(self.canvas, 'selection', None)
        if sel is not None and not sel.isEmpty():
            p.setClipPath(sel)
        # Transparencia: Source ESCRIBE el alfa (la zona se vuelve realmente
        # transparente y revela lo que hay debajo). Color: SourceOver normal.
        # Sobre la máscara (sin alfa) no aplica: se compone como Color.
        if self._mode() == "Transparencia" and not self._on_mask:
            p.setCompositionMode(QPainter.CompositionMode_Source)
        p.drawImage(0, 0, grad)
        p.end()
        self._write_target(result)
        self.canvas.update()

    def _build_qimage(self):
        c0, c1 = self._colors()
        arr = self._gradient_array(self._px, self._py,
                                   self._end.x() - self._start.x(),
                                   self._end.y() - self._start.y(),
                                   c0, c1, self._pattern(), self.SPINS,
                                   self._mode(), self._dither())
        self._buf = np.ascontiguousarray(arr)
        qimg = QImage(self._buf.data, self._W, self._H, 4 * self._W,
                      QImage.Format_RGBA8888)
        return qimg.copy()

    @staticmethod
    def _gradient_array(px, py, dx, dy, c0, c1, pattern, spins, mode, dither):
        """Devuelve un array (H, W, 4) uint8 RGBA con el patrón pedido."""
        L = math.hypot(dx, dy) or 1e-6
        ux, uy = dx / L, dy / L
        a = px * ux + py * uy             # componente a lo largo del arrastre
        b = -px * uy + py * ux            # componente perpendicular
        r = np.sqrt(px * px + py * py) / L

        if pattern == "Lineal":
            t = a / L
        elif pattern == "Lineal reflejado":
            t = np.abs(a) / L
        elif pattern == "Radial":
            t = r
        elif pattern == "Rombo":
            t = (np.abs(a) + np.abs(b)) / L
        elif pattern == "Cuadrado (caja)":
            t = np.maximum(np.abs(a), np.abs(b)) / L
        elif pattern == "Cónico":
            t = (np.arctan2(b, a) / (2 * np.pi)) % 1.0
        elif pattern == "Espiral (horario)":
            t = (np.arctan2(b, a) / (2 * np.pi) + spins * r) % 1.0
        elif pattern == "Espiral (antihorario)":
            t = (-np.arctan2(b, a) / (2 * np.pi) + spins * r) % 1.0
        else:
            t = a / L

        t = np.clip(t, 0.0, 1.0)[..., None]
        c0 = np.array(c0, np.float32)
        c1 = np.array(c1, np.float32)
        # Modo Transparencia: del color c0 (con su alfa) a totalmente transparente
        if mode == "Transparencia":
            c1 = np.array([c0[0], c0[1], c0[2], 0.0], np.float32)

        out = c0 * (1.0 - t) + c1 * t
        if dither:
            # Ruido ±0.5 niveles: rompe el banding al cuantizar a 8 bits
            out = out + np.random.uniform(-0.5, 0.5, out.shape).astype(np.float32)
        return np.clip(np.rint(out), 0.0, 255.0).astype(np.uint8)
