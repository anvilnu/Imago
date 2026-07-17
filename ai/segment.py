# ai/segment.py
"""Segmentacion semantica con DeepLabV3+ MobileNetV2 (Pascal VOC, Apache-2.0).

Clasifica cada pixel en una de 21 clases (fondo + 20 objetos: persona, coche,
perro...). Sirve para "seleccionar por objeto": el usuario elige una clase y se
crea una seleccion con esos pixeles.

Entrada FIJA 513x513, normalizada a [-1, 1]; salida (1, 21, 520, 520) de logits
-> argmax = clase por pixel. Trabajo SINCRONO (hilo secundario del runner).
"""

import numpy as np

from i18n import current_language
from ai import imgproc
from ai.runner import get_session, run_session

MODEL_KEY = "deeplab"
_SIZE = 513

# Nombres de las 21 clases de Pascal VOC (indice = clase).
_NAMES_ES = ["fondo", "avión", "bicicleta", "pájaro", "barco", "botella",
             "autobús", "coche", "gato", "silla", "vaca", "mesa", "perro",
             "caballo", "moto", "persona", "planta", "oveja", "sofá", "tren",
             "televisor"]
_NAMES_EN = ["background", "aeroplane", "bicycle", "bird", "boat", "bottle",
             "bus", "car", "cat", "chair", "cow", "table", "dog", "horse",
             "motorbike", "person", "plant", "sheep", "sofa", "train", "tv"]


def class_name(idx):
    names = _NAMES_ES if current_language() == "es" else _NAMES_EN
    return names[idx] if 0 <= idx < len(names) else str(idx)


def segment(rgb, model_path):
    """rgb (H, W, 3) uint8 -> mapa de etiquetas (H, W) uint8 (0..20). Sincrono."""
    h, w = rgb.shape[:2]
    small = imgproc.resize_rgba(
        imgproc.merge_rgb_alpha(rgb, np.full((h, w), 255, np.uint8)),
        _SIZE, _SIZE)[:, :, :3]
    x = (small.astype(np.float32) / 127.5 - 1.0).transpose(2, 0, 1)[None]

    session = get_session(model_path)
    out = run_session(session, {session.get_inputs()[0].name:
                                np.ascontiguousarray(x)})[0][0]   # (21, S, S)
    label = out.argmax(0).astype(np.uint8)                        # (S, S)

    # Reescalado a tamano original por VECINO MAS PROXIMO (no interpolar
    # etiquetas: mezclar clases 15 y 7 no daria la clase 11).
    sh, sw = label.shape
    ys = np.clip((np.arange(h) * sh / h).astype(np.int64), 0, sh - 1)
    xs = np.clip((np.arange(w) * sw / w).astype(np.int64), 0, sw - 1)
    return label[ys][:, xs]
