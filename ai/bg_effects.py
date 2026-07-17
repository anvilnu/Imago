# ai/bg_effects.py
"""Efectos que reutilizan la mascara del sujeto de la eliminacion de fondo
(la fase "casi gratis" de propuesta_ia.md). Todos reciben:

    rgba: array (H, W, 4) uint8 de la capa.
    mask: array (H, W) uint8 de la segmentacion (255=sujeto, 0=fondo). Sus bordes
          suaves permiten mezclar sin escalones.

y devuelven un RGBA nuevo (no modifican el original). Trabajan con numpy/scipy,
sin dependencias extra. Sincronos: pensados para el hilo secundario.

Ademas hay utilidades para convertir la mascara en una SELECCION (QRegion/
QPainterPath), reutilizando el mismo enfoque que la varita magica (tramos de
fila + simplified()), para que los ajustes/efectos existentes se confinen a ella.
"""

import numpy as np
from scipy import ndimage
from PySide6.QtGui import QRegion, QPainterPath


def _subject_weight(mask):
    """Peso del sujeto por pixel: float (H, W, 1) en 0..1 (1 = sujeto)."""
    return (mask.astype(np.float32) / 255.0)[..., None]


def _blend(front, back, weight):
    """front donde weight=1 (sujeto), back donde weight=0 (fondo)."""
    return front * weight + back * (1.0 - weight)


# --------------------------------------------------------------- desenfoque
def blur_background(rgba, mask, radius):
    """Desenfoca SOLO el fondo (modo retrato); el sujeto queda nitido."""
    out = rgba.copy()
    rgb = rgba[:, :, :3].astype(np.float32)
    sigma = max(0.1, float(radius))
    blurred = np.empty_like(rgb)
    for c in range(3):
        blurred[:, :, c] = ndimage.gaussian_filter(rgb[:, :, c], sigma=sigma)
    res = _blend(rgb, blurred, _subject_weight(mask))
    out[:, :, :3] = np.clip(res + 0.5, 0, 255).astype(np.uint8)
    return out


# ------------------------------------------------------------- color pop
def color_pop(rgba, mask, amount=1.0):
    """Desatura el fondo (realce de color): el sujeto mantiene su color."""
    out = rgba.copy()
    rgb = rgba[:, :, :3].astype(np.float32)
    lum = 0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]
    gray = np.repeat(lum[:, :, None], 3, axis=2)
    desat = rgb * (1.0 - amount) + gray * amount
    res = _blend(rgb, desat, _subject_weight(mask))
    out[:, :, :3] = np.clip(res + 0.5, 0, 255).astype(np.uint8)
    return out


# -------------------------------------------------------- reemplazo de fondo
def _replace_background(rgba, mask, back_rgb):
    """Sustituye el fondo por `back_rgb` (H, W, 3 float): el sujeto conserva sus
    pixeles y su alfa; el fondo pasa a ser OPACO con el nuevo color/imagen."""
    out = rgba.copy()
    rgb = rgba[:, :, :3].astype(np.float32)
    a = rgba[:, :, 3].astype(np.float32)
    w = _subject_weight(mask)
    res = _blend(rgb, back_rgb, w)
    out[:, :, :3] = np.clip(res + 0.5, 0, 255).astype(np.uint8)
    m = w[:, :, 0]
    out[:, :, 3] = np.clip(a * m + 255.0 * (1.0 - m) + 0.5, 0, 255).astype(np.uint8)
    return out


def replace_background_solid(rgba, mask, color_rgb):
    """Fondo -> color liso. `color_rgb` = (r, g, b) 0..255."""
    h, w = rgba.shape[:2]
    back = np.empty((h, w, 3), np.float32)
    back[:, :] = np.asarray(color_rgb[:3], np.float32)
    return _replace_background(rgba, mask, back)


def replace_background_image(rgba, mask, bg_rgb):
    """Fondo -> imagen. `bg_rgb` = array (H, W, 3) uint8 ya del tamano del lienzo."""
    return _replace_background(rgba, mask, bg_rgb[:, :, :3].astype(np.float32))


# ------------------------------------------------- mascara -> seleccion
def subject_region(mask, threshold=128):
    """QRegion de los pixeles del sujeto (mask >= threshold), acumulando los
    tramos horizontales de cada fila (mismo metodo que la varita magica:
    inequivoco y sin depender del formato de bits de una QImage)."""
    binary = (mask >= threshold)
    region = QRegion()
    for y in range(binary.shape[0]):
        row = binary[y].astype(np.int8)
        changes = np.diff(np.concatenate(([0], row, [0])))
        starts = np.where(changes == 1)[0]
        ends = np.where(changes == -1)[0]
        for s, e in zip(starts, ends):
            region += QRegion(int(s), y, int(e - s), 1)
    return region


def subject_path(mask, threshold=128):
    """QPainterPath del sujeto (contorno externo limpio) o None si esta vacio.
    simplified() fusiona los rectangulos y deja solo el perimetro."""
    region = subject_region(mask, threshold)
    if region.isEmpty():
        return None
    path = QPainterPath()
    path.addRegion(region)
    return path.simplified()
