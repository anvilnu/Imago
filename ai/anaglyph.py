# ai/anaglyph.py
"""Efecto 3D anaglifo (gafas rojo/cian) a partir de la profundidad de MiDaS.

Con el mapa de profundidad (255=cerca, 0=lejos) se sintetizan las vistas de los
dos ojos desplazando cada pixel HORIZONTALMENTE segun su cercania (paralaje: lo
cercano se desplaza mas) y se combinan a la manera anaglifo clasica: canal ROJO
de la vista izquierda + VERDE y AZUL de la derecha. Con gafas rojo/cian cada ojo
ve su vista y el cerebro percibe volumen.

El plano de convergencia (paralaje cero) se situa en la profundidad MEDIA: lo
cercano "sale" de la pantalla y lo lejano "entra". Sin modelo aqui (la
profundidad llega ya calculada): remapeo vectorizado, rapido, apto para preview.
"""

import numpy as np


def anaglyph(rgba, depth, max_shift):
    """rgba (H, W, 4) uint8 + depth (H, W) uint8 (255=cerca) -> RGBA anaglifo.
    `max_shift` es el paralaje maximo en pixeles (intensidad del 3D)."""
    h, w = rgba.shape[:2]
    if max_shift <= 0:
        return rgba.copy()
    d = depth.astype(np.float32) / 255.0
    disp = (d - 0.5) * float(max_shift)     # plano cero en la profundidad media
    rows = np.arange(h)[:, None]
    xs = np.arange(w, dtype=np.float32)[None, :]
    xl = np.clip(np.rint(xs - disp * 0.5).astype(np.int32), 0, w - 1)
    xr = np.clip(np.rint(xs + disp * 0.5).astype(np.int32), 0, w - 1)
    left = rgba[rows, xl]                   # vista del ojo izquierdo
    right = rgba[rows, xr]                  # vista del ojo derecho
    out = rgba.copy()
    out[:, :, 0] = left[:, :, 0]            # rojo  <- izquierda
    out[:, :, 1] = right[:, :, 1]           # verde <- derecha
    out[:, :, 2] = right[:, :, 2]           # azul  <- derecha
    return out
