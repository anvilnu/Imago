# tools/liquify_tool.py
from i18n import t
import math
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from tools.base_tool import BaseTool
from tools.commands import PaintCommand
from tools.roi_buffers import (ImagenPremultiplicadaDispersa,
                               escribir_rgba_region, imagen_rgba_region,
                               mascara_seleccion_region)


class LiquifyTool(BaseTool):
    """Licuar (warp push): pincel que EMPUJA los píxeles en la dirección del
    trazo, deformando la imagen como pintura líquida (el Forward Warp básico
    de otros editores). Hermano mayor de SmudgeTool: en vez de mezclar color,
    re-muestrea la imagen con un campo de desplazamiento numpy.

    - Tamaño: compartido con el pincel. Dureza: caída del empuje hacia el borde.
    - Fuerza: cuánto siguen los píxeles al cursor (100% = el centro va pegado).
    - Cada paso del trazo aplica un desplazamiento PEQUEÑO (≤ el espaciado del
      estampado) con muestreo BILINEAL sobre el estado actual: las
      deformaciones se acumulan suaves, sin roturas.
    - Trabaja en alfa PREMULTIPLICADO (los bordes transparentes se deforman
      sin halos). Con la transparencia bloqueada solo se deforma el color.
    - Respeta la selección activa. Vista previa en vivo y un paso de deshacer.
    """

    def __init__(self, canvas):
        super().__init__(canvas)
        self.tool_id = "liquify"
        self._active = False
        self._before = None
        self._buf = None          # float32 premultiplicado por teselas tocadas
        self._mask = None         # punta del pincel (D,D) 0..1
        self._D = 0
        self._W = self._H = 0
        self._last = None
        self._strength = 0.5
        self._orig_fmt = None
        self._lock = False        # bloqueo de transparencia del trazo en curso
        self._work = None         # QImage de trabajo del trazo (parches in place)
        self._dirty = False       # hubo cambios pendientes de repintar
        self._stroke_dirty = None # caja semiabierta de todo el trazo

    # ------------------------------------------------------------- ratón
    def mouse_press(self, event):
        if event.button() != Qt.LeftButton:
            return
        img = self.canvas.get_active_layer()
        if img is None:
            return
        self._orig_fmt = img.format()
        self._before = QImage(img)
        self._lock = self.canvas.alpha_lock_active()
        self._H, self._W = img.height(), img.width()
        # 🚀 Imagen de TRABAJO del trazo: se asigna UNA vez y durante el trazo
        # solo se le pintan los PARCHES modificados (in place, como el pincel).
        # Antes cada movimiento des-premultiplicaba y copiaba la imagen ENTERA
        # (~1 s por evento en 4000×5000); ahora el coste va con el pincel.
        self._work = img.convertToFormat(QImage.Format_RGBA8888)
        self._buf = ImagenPremultiplicadaDispersa(img)
        self.canvas.layers[self.canvas.active_layer_index].image = self._work
        self._dirty = False
        self._stroke_dirty = None
        self._build_mask()
        self._strength = max(1, min(100, getattr(self.canvas, 'liquify_strength', 50))) / 100.0
        pos = event.position() / self.canvas.zoom_factor
        self._last = (pos.x(), pos.y())
        self._active = True

    def mouse_move(self, event):
        if not self._active:
            return
        pos = event.position() / self.canvas.zoom_factor
        x1, y1 = pos.x(), pos.y()
        x0, y0 = self._last
        dist = math.hypot(x1 - x0, y1 - y0)
        # Pasos CORTOS a propósito: cada estampado desplaza como mucho el
        # espaciado, así el warp acumulado queda continuo (sin desgarros).
        step = max(1.0, self._D * 0.15)
        n = max(1, int(math.ceil(dist / step)))
        dx = (x1 - x0) / n
        dy = (y1 - y0) / n
        for i in range(1, n + 1):
            self._warp_at(x0 + dx * i, y0 + dy * i, dx, dy)
        self._last = (x1, y1)
        self._flush_preview()

    def mouse_release(self, event):
        if self._active:
            self._active = False
            self._commit()

    def finish_editing(self):
        if self._active:
            self._active = False
            self._commit()

    # --------------------------------------------------------- premultiplicado
    @staticmethod
    def _premultiply(u8):
        f = u8.astype(np.float32)
        a = f[..., 3:4] / 255.0
        f[..., :3] *= a
        return f

    @staticmethod
    def _unpremultiply(f):
        out = f.copy()
        a = out[..., 3:4] / 255.0
        np.divide(out[..., :3], a, out=out[..., :3], where=(a > 0))
        return np.clip(out, 0, 255).astype(np.uint8)

    # --------------------------------------------------------- máscaras
    def _build_mask(self):
        size = max(3, int(round(self.canvas.brush_size)))
        self._D = size
        R = size / 2.0
        hardness = max(0, min(100, getattr(self.canvas, 'liquify_hardness', 50))) / 100.0
        yy, xx = np.mgrid[0:size, 0:size]
        c = (size - 1) / 2.0
        d = np.sqrt((xx - c) ** 2 + (yy - c) ** 2) / (R if R > 0 else 1)
        if hardness < 1.0:
            k = np.clip((d - hardness) / (1.0 - hardness), 0, 1)
            m = np.where(d > hardness, (1 - k) ** 3, 1.0)
        else:
            m = np.ones_like(d)
        m[d > 1.0] = 0.0
        self._mask = m.astype(np.float32)

    # --------------------------------------------------------- deformado
    def _warp_at(self, cx, cy, dx, dy):
        """Un estampado del warp: los píxeles de la región del pincel se
        re-muestrean HACIA ATRÁS ((x,y) toma su color de (x-m·dx, y-m·dy))
        con interpolación bilineal sobre el estado actual del trazo."""
        D = self._D
        x0 = int(round(cx - D / 2.0)); y0 = int(round(cy - D / 2.0))
        bx0 = max(0, x0); by0 = max(0, y0)
        bx1 = min(self._W, x0 + D); by1 = min(self._H, y0 + D)
        if bx1 <= bx0 or by1 <= by0:
            return
        mx0 = bx0 - x0; my0 = by0 - y0
        ms = self._mask[my0:my0 + (by1 - by0), mx0:mx0 + (bx1 - bx0)]
        clip = mascara_seleccion_region(
            self.canvas, bx0, by0, bx1, by1)
        if clip is not None:
            ms = ms * clip
        m = ms * self._strength
        if not m.any():
            return
        yy, xx = np.mgrid[by0:by1, bx0:bx1]
        sx = np.clip(xx - m * dx, 0.0, self._W - 1.001)
        sy = np.clip(yy - m * dy, 0.0, self._H - 1.001)
        x0i = sx.astype(np.int32); y0i = sy.astype(np.int32)
        fx = (sx - x0i)[..., None].astype(np.float32)
        fy = (sy - y0i)[..., None].astype(np.float32)
        x1i = np.minimum(x0i + 1, self._W - 1)
        y1i = np.minimum(y0i + 1, self._H - 1)
        # Materializar solo la caja que contiene las cuatro muestras bilineales.
        sx0, sy0 = int(x0i.min()), int(y0i.min())
        sx1, sy1 = int(x1i.max()) + 1, int(y1i.max()) + 1
        fuente = self._buf.region(sx0, sy0, sx1, sy1)
        lx0, ly0 = x0i - sx0, y0i - sy0
        lx1, ly1 = x1i - sx0, y1i - sy0
        muestra = ((fuente[ly0, lx0] * (1 - fx)
                    + fuente[ly0, lx1] * fx) * (1 - fy)
                   + (fuente[ly1, lx0] * (1 - fx)
                      + fuente[ly1, lx1] * fx) * fy)
        self._buf.escribir_region(bx0, by0, muestra)
        salida = self._unpremultiply(muestra)
        if self._lock:
            original = imagen_rgba_region(
                self._before, bx0, by0, bx1, by1)
            salida[..., 3] = original[..., 3]
        escribir_rgba_region(self._work, bx0, by0, salida)
        self._dirty = True
        self._marcar_sucio_trazo(bx0, by0, bx1, by1)

    def _marcar_sucio_trazo(self, x0, y0, x1, y1):
        if self._stroke_dirty is None:
            self._stroke_dirty = [x0, y0, x1, y1]
        else:
            rect = self._stroke_dirty
            rect[0] = min(rect[0], x0); rect[1] = min(rect[1], y0)
            rect[2] = max(rect[2], x1); rect[3] = max(rect[3], y1)

    # --------------------------------------------------------- volcado
    def _flush_preview(self):
        """Solicita un repintado si algún ROI se volcó desde el último evento."""
        if not self._dirty:
            return
        self._dirty = False
        self.canvas.update()

    def _commit(self):
        # La imagen de TRABAJO ya lleva todos los parches del trazo aplicados
        # (mismos valores que reconvertir el buffer float entero, que costaba
        # ~1 s en 4000×5000): se vuelca el último pendiente y se usa tal cual.
        self._flush_preview()
        out = self._work.convertToFormat(self._orig_fmt)
        self.canvas.layers[self.canvas.active_layer_index].image = out
        after = QImage(out)
        if self._before is not None:
            self.canvas.undo_stack.push(PaintCommand(
                self.canvas, self.canvas.active_layer_index,
                self._before, after, t("hist.liquify"), tool_id="liquify",
                confine=True, dirty_rect=self._stroke_dirty))
        self._before = self._buf = self._mask = None
        self._lock = False
        self._work = None
        self._dirty = False
        self._stroke_dirty = None
