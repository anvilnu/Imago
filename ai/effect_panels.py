# ai/effect_panels.py
"""Paneles OVERLAY (no modales) para efectos de IA con vista previa en vivo.

Igual que los Ajustes/Efectos (AdjustmentDialog), son QWidget HIJOS de la ventana
—no diálogos del sistema— para que el compositor NO atenúe la ventana principal
(el "atenuar ventanas inactivas" de KDE/Wayland) y la preview se vea bien en
cualquier SO. Ver migrar_dialogos_a_overlay.md.

REGLA para nuevos efectos de IA con parámetros: heredar de AdjustmentDialog (como
aquí) en lugar de abrir un FramelessDialog modal. Así se reutiliza toda la
fontanería (preview en vivo, confirmar como un PaintCommand, bloqueo del lienzo)
y no se atenúa el fondo.

Los efectos confinados por la máscara del sujeto hacen la mezcla DENTRO de
compute(): reciben el array de la capa (o el parche de la selección) y devuelven
el resultado ya combinado; la base lo compone y lo previsualiza.
"""

from i18n import t
from adjustments import AdjustmentDialog
from ai import bg_effects, anaglyph
from ai.imgproc import resize_mask


class AIBackgroundBlurPanel(AdjustmentDialog):
    """Desenfoque de fondo (modo retrato) con preview en vivo. La máscara del
    sujeto se pasa ya calculada (la misma que 'Eliminar fondo'): el sujeto queda
    nítido y solo se difumina el fondo."""

    title = t("ai.blur.title")
    heavy = True   # el blur es pesado -> preview con debounce (al soltar el slider)
    preview_downscale = True   # y la previa sobre versión reducida (el blur es lo caro)

    def __init__(self, main_window, mask, default_radius=12, destino=None):
        # Se fija ANTES de super().__init__: la base llama a build_controls() y a
        # la primera preview (compute) durante su propia inicialización.
        self._mask = mask
        self._default_radius = default_radius
        super().__init__(main_window, destino=destino)

    def build_controls(self):
        self.add_slider_row("radius", t("ai.blur.radius"), 1, 80, self._default_radius)

    def compute(self, arr):
        # Máscara del sujeto recortada a la región activa (parche) a resolución
        # COMPLETA. Si la previa va en versión reducida (preview_downscale), la
        # reducimos a las dimensiones del array y escalamos el radio en la misma
        # proporción (self._cur_scale), para que la previa coincida con el final.
        ox, oy = self._patch_offset
        m = self._mask[oy:oy + self._H, ox:ox + self._W]
        hh, ww = arr.shape[:2]
        if (hh, ww) != m.shape[:2]:
            m = resize_mask(m, ww, hh)
        return bg_effects.blur_background(arr, m, self.val("radius") * self._cur_scale)


class AIBokehPanel(AIBackgroundBlurPanel):
    """Bokeh por PROFUNDIDAD (MiDaS): idéntico al desenfoque de fondo, pero la
    máscara es un peso de nitidez CONTINUO derivado de la profundidad (255=cerca,
    0=lejos), así el desenfoque crece gradualmente con la distancia. Solo cambia
    el título (el motor es el mismo blur ponderado por máscara)."""

    title = t("ai.bokeh.title")


class AIAnaglyphPanel(AdjustmentDialog):
    """Efecto 3D anaglifo (gafas rojo/cian) con preview en vivo: desplaza los
    píxeles según la profundidad (MiDaS, ya calculada) para simular la vista de
    cada ojo. El slider controla el paralaje máximo en píxeles (intensidad).
    El remapeo es rápido (sin modelo), así que la preview va en vivo."""

    title = t("ai.anaglyph.title")

    def __init__(self, main_window, depth, default_shift=10, destino=None):
        # Se fija ANTES de super().__init__ (la base llama a build_controls y a
        # la primera preview durante su propia inicialización).
        self._depth = depth
        self._default_shift = default_shift
        super().__init__(main_window, destino=destino)

    def build_controls(self):
        self.add_slider_row("shift", t("ai.anaglyph.strength"),
                            0, 30, self._default_shift)

    def compute(self, arr):
        # arr es la capa completa (o el parche de la selección): recortamos la
        # profundidad a esa misma región con el offset del parche.
        h, w = arr.shape[:2]
        ox, oy = self._patch_offset
        d = self._depth[oy:oy + h, ox:ox + w]
        return anaglyph.anaglyph(arr, d, self.val("shift"))
