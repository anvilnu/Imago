# tools/dodge_burn_tool.py
from i18n import t
import math
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from tools.base_tool import BaseTool
from tools.commands import PaintCommand
from tools.roi_buffers import (CoberturaDispersa, escribir_rgba_region,
                               imagen_rgba_region, mascara_seleccion_region)


class DodgeBurnTool(BaseTool):
    """Sobreexponer / Subexponer (Dodge & Burn). Pincel que aclara (dodge) u
    oscurece (burn) la zona pintada, pesando el efecto por el rango tonal
    elegido (sombras / medios tonos / luces).

    - Tamaño: compartido con el pincel. Dureza: difuminado del borde.
    - Exposición: intensidad del efecto en cada pasada.
    - Modo: Sobreexponer (aclarar) o Subexponer (oscurecer); mantener Ctrl al
      empezar el trazo INVIERTE el modo temporalmente (como en otros editores).
    - Dentro de un mismo trazo el efecto NO se acumula al repasar la misma zona
      (máscara de trazo acumulada por máximo, estilo GIMP): cada pasada nueva
      (soltar y volver a pintar) sí suma. Así el resultado es predecible.
    - Respeta la selección activa. Vista previa en vivo y un paso de deshacer.
    """

    def __init__(self, canvas):
        super().__init__(canvas)
        self.tool_id = "dodge_burn"
        self._active = False
        self._before = None
        self._coverage = None     # cobertura float32 por teselas tocadas
        self._mask = None         # punta del pincel (D,D) 0..1
        self._D = 0
        self._W = self._H = 0
        self._last = None
        self._dirty = None        # rect sucio (x0, y0, x1, y1) pendiente de recomputar
        self._stroke_dirty = None # rect acumulado de todo el trazo
        self._mode = "dodge"
        self._range = "midtones"
        self._exposure = 0.25
        self._orig_fmt = None
        self._work = None         # QImage de trabajo del trazo (parches in place)

    # ------------------------------------------------------------- ratón
    def mouse_press(self, event):
        if event.button() != Qt.LeftButton:
            return
        img = self.canvas.get_active_layer()
        if img is None:
            return
        self._orig_fmt = img.format()
        self._before = QImage(img)
        self._H, self._W = img.height(), img.width()
        self._coverage = CoberturaDispersa(self._W, self._H)
        # 🚀 Imagen de TRABAJO del trazo: se asigna UNA vez y durante el trazo
        # solo se le pintan los PARCHES modificados (in place, como el pincel):
        # el coste por movimiento va con el tamaño del pincel, no de la imagen.
        self._work = img.convertToFormat(QImage.Format_RGBA8888)
        self.canvas.layers[self.canvas.active_layer_index].image = self._work
        self._build_mask()

        self._mode = getattr(self.canvas, 'dodge_mode', 'dodge')
        # Ctrl al empezar el trazo: modo contrario temporal
        if event.modifiers() & Qt.ControlModifier:
            self._mode = "burn" if self._mode == "dodge" else "dodge"
        self._range = getattr(self.canvas, 'dodge_range', 'midtones')
        self._exposure = max(1, min(100, getattr(self.canvas, 'dodge_exposure', 25))) / 100.0

        pos = event.position() / self.canvas.zoom_factor
        self._last = (pos.x(), pos.y())
        self._dirty = None
        self._stroke_dirty = None
        self._stamp(pos.x(), pos.y())
        self._active = True
        self._flush_preview()

    def mouse_move(self, event):
        if not self._active:
            return
        pos = event.position() / self.canvas.zoom_factor
        x1, y1 = pos.x(), pos.y()
        x0, y0 = self._last
        dist = math.hypot(x1 - x0, y1 - y0)
        step = max(1.0, self._D * 0.25)
        n = max(1, int(dist / step))
        for i in range(1, n + 1):
            f = i / n
            self._stamp(x0 + (x1 - x0) * f, y0 + (y1 - y0) * f)
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

    # --------------------------------------------------------- máscaras
    def _build_mask(self):
        size = max(1, int(round(self.canvas.brush_size)))
        self._D = size
        R = size / 2.0
        hardness = max(0, min(100, getattr(self.canvas, 'dodge_hardness', 50))) / 100.0
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

    # --------------------------------------------------------- estampado
    def _region(self, cx, cy):
        D = self._D
        x0 = int(round(cx - D / 2.0)); y0 = int(round(cy - D / 2.0))
        bx0 = max(0, x0); by0 = max(0, y0)
        bx1 = min(self._W, x0 + D); by1 = min(self._H, y0 + D)
        if bx1 <= bx0 or by1 <= by0:
            return None
        mx0 = bx0 - x0; my0 = by0 - y0
        return bx0, by0, bx1, by1, mx0, my0, mx0 + (bx1 - bx0), my0 + (by1 - by0)

    def _stamp(self, cx, cy):
        reg = self._region(cx, cy)
        if not reg:
            return
        bx0, by0, bx1, by1, mx0, my0, mx1, my1 = reg
        ms = self._mask[my0:my1, mx0:mx1]
        clip = mascara_seleccion_region(
            self.canvas, bx0, by0, bx1, by1)
        if clip is not None:
            ms = ms * clip
        self._coverage.maximo(bx0, by0, ms)
        self._marcar_sucio(bx0, by0, bx1, by1)

    def _recompute(self, bx0, by0, bx1, by1):
        """Recalcula la región desde el ORIGINAL con la máscara acumulada: el
        efecto de un trazo es uniforme aunque se repase la misma zona."""
        original = imagen_rgba_region(
            self._before, bx0, by0, bx1, by1)
        v = original[..., :3].astype(np.float32) / 255.0
        s = self._coverage.region(
            bx0, by0, bx1, by1) * self._exposure               # fuerza 0..1
        s = s * (original[..., 3] > 0)                          # solo píxeles con alfa
        s = s[..., None]
        if self._range == "shadows":
            w = 1.0 - v
        elif self._range == "highlights":
            w = v
        else:  # medios tonos
            w = 1.0 - np.abs(2.0 * v - 1.0)
        if self._mode == "dodge":
            out = v + s * w * (1.0 - v)      # empuja hacia el blanco
        else:
            out = v - s * w * v              # empuja hacia el negro
        original[..., :3] = np.clip(
            out * 255.0 + 0.5, 0, 255).astype(np.uint8)
        escribir_rgba_region(self._work, bx0, by0, original)

    # --------------------------------------------------------- volcado
    def _marcar_sucio(self, x0, y0, x1, y1):
        if self._dirty is None:
            self._dirty = [x0, y0, x1, y1]
        else:
            d = self._dirty
            d[0] = min(d[0], x0); d[1] = min(d[1], y0)
            d[2] = max(d[2], x1); d[3] = max(d[3], y1)
        if self._stroke_dirty is None:
            self._stroke_dirty = [x0, y0, x1, y1]
        else:
            d = self._stroke_dirty
            d[0] = min(d[0], x0); d[1] = min(d[1], y0)
            d[2] = max(d[2], x1); d[3] = max(d[3], y1)

    def _flush_preview(self):
        """Vuelca a la imagen de trabajo SOLO el parche modificado desde el
        último volcado (copiar la imagen entera crecía con el documento).
        Pintar in place sobre layer.image, como el pincel, invalida la caché
        de composición por cacheKey."""
        if self._dirty is None:
            return
        x0, y0, x1, y1 = self._dirty
        self._dirty = None
        self._recompute(x0, y0, x1, y1)
        self.canvas.update()

    def _commit(self):
        # La imagen de TRABAJO ya lleva todos los parches del trazo aplicados:
        # se vuelca el último pendiente y se usa tal cual (sin otra copia entera).
        self._flush_preview()
        out = self._work.convertToFormat(self._orig_fmt)
        self.canvas.layers[self.canvas.active_layer_index].image = out
        after = QImage(out)
        if self._before is not None:
            texto = t("hist.dodge") if self._mode == "dodge" else t("hist.burn")
            self.canvas.undo_stack.push(PaintCommand(
                self.canvas, self.canvas.active_layer_index,
                self._before, after, texto, tool_id="dodge_burn", confine=True,
                dirty_rect=self._stroke_dirty))
        self._before = self._coverage = self._mask = None
        self._work = None
        self._dirty = None
        self._stroke_dirty = None
