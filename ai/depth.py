# ai/depth.py
"""Estimación de profundidad con MiDaS (v21 small, MIT) para BOKEH real.

MiDaS predice la profundidad INVERSA (valor mayor = más cerca). Se normaliza a un
"peso de nitidez" (255 = cerca/enfocado, 0 = lejos/desenfocar) del tamaño de la
imagen. Ese peso alimenta directamente bg_effects.blur_background: el sujeto
cercano queda nítido y el fondo se difumina de forma GRADUAL según la distancia
(desenfoque de profundidad de campo), no con un corte binario.

Entrada del modelo: 256x256, normalización ImageNet. Trabajo SINCRONO (hilo
secundario del InferenceRunner).
"""

import numpy as np

from ai import imgproc
from ai.runner import get_session, run_session

MODEL_KEY = "midas-small"
_SIZE = 256
_MEAN = np.array([0.485, 0.456, 0.406], np.float32)
_STD = np.array([0.229, 0.224, 0.225], np.float32)


def sharpness_weight(rgb, model_path):
    """rgb (H, W, 3) uint8 -> peso de nitidez (H, W) uint8: 255 = cerca (nítido),
    0 = lejos (desenfocar). Es la profundidad inversa de MiDaS normalizada."""
    h, w = rgb.shape[:2]
    small = imgproc.resize_rgba(
        imgproc.merge_rgb_alpha(rgb, np.full((h, w), 255, np.uint8)),
        _SIZE, _SIZE)[:, :, :3]
    x = (small.astype(np.float32) / 255.0 - _MEAN) / _STD
    x = np.ascontiguousarray(x.transpose(2, 0, 1)[None])

    session = get_session(model_path)
    out = run_session(session, {session.get_inputs()[0].name: x})[0][0]   # (256, 256)
    mi, ma = float(out.min()), float(out.max())
    dn = (out - mi) / (ma - mi) if ma > mi else np.zeros_like(out)         # 0..1, 1=cerca

    d8 = (dn * 255.0 + 0.5).astype(np.uint8)
    return imgproc.resize_mask(d8, w, h)     # de vuelta al tamaño original (suave)
