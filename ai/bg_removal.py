# ai/bg_removal.py
"""Eliminacion automatica de fondo (segmentacion del sujeto).

Dada una imagen RGBA, un modelo de segmentacion (isnet-general-use por defecto,
u2net como alternativa) estima una mascara del sujeto (255=sujeto, 0=fondo). Esa
mascara se aplica al canal ALFA para recortar el fondo.

Todo el trabajo pesado (redimensionar + inferencia) es SINCRONO y esta pensado
para ejecutarse dentro de la funcion de trabajo del InferenceRunner (hilo
secundario). El pre/postproceso reutiliza ai/imgproc.py (que a su vez reutiliza
qimage_to_array / array_to_qimage).

Los parametros de pre/proceso (tamano de entrada y normalizacion) se derivaron
inspeccionando el propio .onnx y las convenciones de cada familia de modelos.
"""

import numpy as np

from ai import imgproc
from ai.runner import get_session, run_session


# Modelo por defecto de la funcion (ver ai/model_manager.CATALOG).
DEFAULT_MODEL_KEY = "isnet-general-use"

# Pre/postproceso por familia de modelo.
#   size: lado de la entrada cuadrada del modelo.
#   mean/std: normalizacion por canal (tras escalar a 0..1).
_PARAMS = {
    "isnet-general-use": {"size": 1024, "mean": (0.5, 0.5, 0.5),
                          "std": (1.0, 1.0, 1.0)},
    "u2net":             {"size": 320,  "mean": (0.485, 0.456, 0.406),
                          "std": (0.229, 0.224, 0.225)},
}


def params_for(model_key):
    return _PARAMS.get(model_key, _PARAMS[DEFAULT_MODEL_KEY])


def compute_alpha_mask(rgb, model_path, model_key=DEFAULT_MODEL_KEY):
    """rgb (H, W, 3) uint8 -> mascara (H, W) uint8 (255=sujeto). Sincrono."""
    h, w = rgb.shape[:2]
    p = params_for(model_key)
    size = p["size"]

    # A la entrada cuadrada del modelo (escalado suave de QImage).
    rgba = imgproc.merge_rgb_alpha(rgb, np.full((h, w), 255, np.uint8))
    small = imgproc.resize_rgba(rgba, size, size)[:, :, :3]
    x = imgproc.to_tensor(small, mean=p["mean"], std=p["std"])

    session = get_session(model_path)
    in_name = session.get_inputs()[0].name
    outputs = run_session(session, {in_name: x})

    # La PRIMERA salida es el mapa de segmentacion (1, 1, size, size).
    pred = imgproc.from_tensor(outputs[0])[:, :, 0].astype(np.float32)
    mi, ma = float(pred.min()), float(pred.max())
    pred = (pred - mi) / (ma - mi) if ma > mi else np.zeros_like(pred)

    mask_small = (pred * 255.0).astype(np.uint8)
    return imgproc.resize_mask(mask_small, w, h)   # de vuelta al tamano original


def apply_alpha_mask(rgba, mask):
    """Devuelve una copia de `rgba` (H, W, 4) con su alfa MULTIPLICADO por la
    mascara (255=opaco). Preserva la transparencia previa del sujeto."""
    out = rgba.copy()
    a = out[:, :, 3].astype(np.uint16)
    m = mask.astype(np.uint16)
    out[:, :, 3] = ((a * m + 127) // 255).astype(np.uint8)
    return out
