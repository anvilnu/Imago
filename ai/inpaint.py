# ai/inpaint.py
"""Borrado inteligente de objetos (inpainting) con LaMa.

El usuario marca una máscara sobre lo que quiere borrar; LaMa reconstruye esa
zona a partir del contexto de alrededor. Este modelo ONNX (Carve/LaMa-ONNX) tiene
entrada FIJA de 512x512 (image + mask) y salida 512x512 en 0..255.

NOTA (GPU): LaMa usa convoluciones de Fourier (FFC) que DirectML no soporta (da un
error de operación); por eso, en GPUs por DirectML (AMD/Intel) esta función CAE A CPU
automáticamente (ver ai/subproc.py). Como se trabaja sobre un recorte de 512x512, la
CPU es rápida de sobra. En NVIDIA (CUDA) sí corre en GPU. Se prefirió LaMa a MI-GAN
porque reconstruye el fondo mucho mejor en borrados grandes (MI-GAN deja una mancha).

Para no perder resolución en imágenes grandes, NO redimensionamos toda la imagen:
recortamos un cuadro alrededor de la máscara (con margen de contexto), lo llevamos
a 512, reconstruimos y lo devolvemos a su sitio, sustituyendo SOLO los píxeles de
la máscara (el resto queda pixel-perfecto).

Todo el trabajo es SINCRONO: pensado para el hilo secundario del InferenceRunner.
"""

import numpy as np
from scipy import ndimage

from ai import imgproc
from ai.runner import get_session, run_session

MODEL_KEY = "lama"
_SIZE = 512    # entrada fija del modelo
_DILATE = 8    # px de dilatación de la máscara (en el espacio 512): imprescindible.
               # Al reducir la máscara a 512 con suavizado, su borde encoge y deja
               # un anillo del objeto SIN enmascarar que LaMa tomaría como contexto
               # (rellenaría con el propio objeto). Dilatarla lo cubre por completo.


def _resize_rgb(rgb, out_w, out_h):
    """Redimensiona un rgb (H, W, 3) uint8 usando el escalado suave de QImage."""
    h, w = rgb.shape[:2]
    rgba = imgproc.merge_rgb_alpha(rgb, np.full((h, w), 255, np.uint8))
    return imgproc.resize_rgba(rgba, out_w, out_h)[:, :, :3]


def _square_crop_box(mask, pad_ratio=0.6, min_pad=24):
    """Cuadro (x0, y0, x1, y1) alrededor de la máscara, con margen de contexto y
    tendencia cuadrada (para no distorsionar al llevarlo a 512x512). None si la
    máscara está vacía."""
    h, w = mask.shape[:2]
    ys, xs = np.where(mask >= 128)
    if xs.size == 0:
        return None
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    pad = int(max(min_pad, pad_ratio * max(x1 - x0, y1 - y0)))
    x0, y0 = max(0, x0 - pad), max(0, y0 - pad)
    x1, y1 = min(w, x1 + pad), min(h, y1 + pad)

    # Expandir el lado corto para acercarlo a un cuadrado (clampado al lienzo).
    side = max(x1 - x0, y1 - y0)
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    half = side // 2 + 1
    x0, y0 = max(0, cx - half), max(0, cy - half)
    x1, y1 = min(w, x0 + side), min(h, y0 + side)
    x0, y0 = max(0, x1 - side), max(0, y1 - side)
    return x0, y0, x1, y1


def inpaint(rgb, mask, model_path):
    """rgb (H, W, 3) uint8 + mask (H, W) uint8 (>=128 = borrar) -> rgb (H, W, 3)
    uint8 con la zona de la máscara reconstruida. Síncrono."""
    box = _square_crop_box(mask)
    if box is None:
        return rgb.copy()
    x0, y0, x1, y1 = box
    crop = rgb[y0:y1, x0:x1]
    cmask = mask[y0:y1, x0:x1]
    ch, cw = crop.shape[:2]

    # A la entrada fija del modelo (512x512), con la máscara DILATADA.
    img512 = _resize_rgb(crop, _SIZE, _SIZE)
    m512 = ndimage.binary_dilation(
        imgproc.resize_mask(cmask, _SIZE, _SIZE) >= 128, iterations=_DILATE)
    x_img = np.ascontiguousarray(
        (img512.astype(np.float32) / 255.0).transpose(2, 0, 1)[None])
    x_mask = np.ascontiguousarray(m512.astype(np.float32)[None, None])

    session = get_session(model_path)
    out = run_session(session, {"image": x_img, "mask": x_mask})[0]
    inpainted512 = np.clip(out[0].transpose(1, 2, 0), 0, 255).astype(np.uint8)

    # De vuelta al tamaño del recorte y composición en la zona reconstruida (la
    # máscara dilatada, llevada a la resolución del recorte). El resto intacto.
    inpainted_crop = _resize_rgb(inpainted512, cw, ch)
    sel = imgproc.resize_mask((m512 * 255).astype(np.uint8), cw, ch) >= 128
    out_crop = crop.copy()
    out_crop[sel] = inpainted_crop[sel]

    result = rgb.copy()
    result[y0:y1, x0:x1] = out_crop
    return result
