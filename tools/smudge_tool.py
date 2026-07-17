# tools/smudge_tool.py
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


class SmudgeTool(BaseTool):
    """Dedo / Emborronar. Arrastra para empujar el color como pintura fresca:
    el pincel recoge los píxeles de debajo y los arrastra en la dirección del
    trazo, mezclándolos poco a poco.

    - Tamaño: compartido con el pincel. Dureza: difuminado del borde.
    - Fuerza: cuánto se arrastra el color (más fuerza = estelas más largas).
    - Espaciado: separación entre estampados del trazo (menor = más suave).
    - Pintar con color: el trazo arranca con el color primario (finger painting).
    - La mezcla se hace en alfa PREMULTIPLICADO (bordes transparentes correctos)
      y solo el parche bajo el pincel se procesa en float32.
    - Respeta la selección activa. Vista previa en vivo y un paso de deshacer.
    """

    def __init__(self, canvas):
        super().__init__(canvas)
        self.tool_id = "smudge"
        self._active = False
        self._before = None
        self._buf = None          # float32 premultiplicado por teselas tocadas
        self._carry = None        # float32 (D,D,4) premultiplicado
        self._mask = None
        self._D = 0
        self._W = self._H = 0
        self._last = None
        self._strength = 0.5
        self._spacing = 0.12
        self._finger = False
        self._primary = None      # color primario premultiplicado (4,)
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
        # 🔒 Bloqueo de transparencia: el dedo arrastra solo el COLOR y el alfa
        # original se restaura en cada parche (aquí no hay painter cuyo modo
        # ajustar, porque el cálculo se hace en NumPy).
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
        self._strength = max(0.0, min(0.99,
                            getattr(self.canvas, 'smudge_strength', 50) / 100.0))
        self._spacing = max(0.02, min(1.0,
                            getattr(self.canvas, 'smudge_spacing', 12) / 100.0))
        self._finger = bool(getattr(self.canvas, 'smudge_finger_paint', False))
        self._primary = self._primary_premult()
        pos = event.position() / self.canvas.zoom_factor
        self._last = (pos.x(), pos.y())
        self._init_carry(pos.x(), pos.y())
        self._active = True

    def mouse_move(self, event):
        if not self._active:
            return
        pos = event.position() / self.canvas.zoom_factor
        x1, y1 = pos.x(), pos.y()
        x0, y0 = self._last
        dist = math.hypot(x1 - x0, y1 - y0)
        step = max(1.0, self._D * self._spacing)
        n = max(1, int(dist / step))
        for i in range(1, n + 1):
            t = i / n
            self._smudge_at(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)
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

    def _primary_premult(self):
        c = self.canvas.brush_color
        v = np.array([c.red(), c.green(), c.blue(), c.alpha()], np.float32)
        v[:3] *= v[3] / 255.0
        return v

    # --------------------------------------------------------- máscaras
    def _build_mask(self):
        size = max(1, int(round(self.canvas.brush_size)))
        self._D = size
        R = size / 2.0
        hardness = max(0, min(100, getattr(self.canvas, 'smudge_hardness', 50))) / 100.0
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

    # --------------------------------------------------------- emborronar
    def _region(self, cx, cy):
        D = self._D
        x0 = int(round(cx - D / 2.0)); y0 = int(round(cy - D / 2.0))
        bx0 = max(0, x0); by0 = max(0, y0)
        bx1 = min(self._W, x0 + D); by1 = min(self._H, y0 + D)
        if bx1 <= bx0 or by1 <= by0:
            return None
        mx0 = bx0 - x0; my0 = by0 - y0
        return bx0, by0, bx1, by1, mx0, my0, mx0 + (bx1 - bx0), my0 + (by1 - by0)

    def _init_carry(self, cx, cy):
        self._carry = np.zeros((self._D, self._D, 4), np.float32)
        if self._finger:
            # Finger painting: el trazo arranca con el color primario
            self._carry[:] = self._primary
        else:
            reg = self._region(cx, cy)
            if reg:
                bx0, by0, bx1, by1, mx0, my0, mx1, my1 = reg
                self._carry[my0:my1, mx0:mx1] = self._buf.region(
                    bx0, by0, bx1, by1)

    def _smudge_at(self, cx, cy):
        reg = self._region(cx, cy)
        if not reg:
            return
        bx0, by0, bx1, by1, mx0, my0, mx1, my1 = reg
        under = self._buf.region(bx0, by0, bx1, by1)
        carry_sub = self._carry[my0:my1, mx0:mx1]
        ms = self._mask[my0:my1, mx0:mx1]
        clip = mascara_seleccion_region(
            self.canvas, bx0, by0, bx1, by1)
        if clip is not None:
            ms = ms * clip
        m = (ms * self._strength)[..., None]
        salida = under * (1 - m) + carry_sub * m
        self._buf.escribir_region(bx0, by0, salida)
        # la pintura arrastrada evoluciona hacia el color nuevo
        self._carry[my0:my1, mx0:mx1] = under * (1 - self._strength) + carry_sub * self._strength
        sub = self._unpremultiply(salida)
        if self._lock:
            original = imagen_rgba_region(
                self._before, bx0, by0, bx1, by1)
            sub[..., 3] = original[..., 3]
        escribir_rgba_region(self._work, bx0, by0, sub)
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
                self._before, after, t("hist.smudge"), tool_id="smudge",
                confine=True, dirty_rect=self._stroke_dirty))
        self._before = self._buf = self._carry = self._mask = None
        self._lock = False
        self._work = None
        self._dirty = False
        self._stroke_dirty = None
