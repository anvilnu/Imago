# ai/upscale.py
"""Super-resolución (aumentar resolución) con Real-ESRGAN (realesr-general-x4v3).

El modelo es x4 y totalmente convolucional (entrada de tamaño LIBRE). Para no
quedarnos sin memoria con fotos grandes, la imagen se procesa por TILES con un
solape que evita costuras (el modelo es fully-conv, así que el solape basta para
que los bordes casen). Entrada/salida en 0..1.

Trabajo SINCRONO: se ejecuta en el hilo secundario del InferenceRunner.
"""

import numpy as np

from ai import imgproc
from ai.runner import get_session, run_session

MODEL_KEY = "realesrgan"
NATIVE_SCALE = 4      # factor nativo del modelo


def _run_tile(session, in_name, tile_rgb):
    """Sube x4 un tile (h, w, 3) uint8 -> (h*4, w*4, 3) uint8."""
    x = np.ascontiguousarray(
        (tile_rgb.astype(np.float32) / 255.0).transpose(2, 0, 1)[None])
    out = run_session(session, {in_name: x})[0]
    up = np.clip(out[0].transpose(1, 2, 0), 0.0, 1.0)
    return (up * 255.0 + 0.5).astype(np.uint8)


def upscale_x4(rgb, model_path, tile=256, overlap=16, report=None, token=None):
    """Sube x4 un rgb (H, W, 3) uint8 por tiles. Devuelve (H*4, W*4, 3) uint8, o
    None si se cancela."""
    h, w = rgb.shape[:2]
    s = NATIVE_SCALE
    session = get_session(model_path)
    in_name = session.get_inputs()[0].name
    out = np.empty((h * s, w * s, 3), np.uint8)

    import math
    nx = max(1, math.ceil(w / tile))
    ny = max(1, math.ceil(h / tile))
    total = nx * ny
    done = 0
    for ty in range(ny):
        for tx in range(nx):
            if token is not None and token.cancelled:
                return None
            x0, y0 = tx * tile, ty * tile
            x1, y1 = min(x0 + tile, w), min(y0 + tile, h)
            # Región con solape (contexto) para evitar costuras.
            px0, py0 = max(0, x0 - overlap), max(0, y0 - overlap)
            px1, py1 = min(w, x1 + overlap), min(h, y1 + overlap)
            up = _run_tile(session, in_name, rgb[py0:py1, px0:px1])
            # Recortar el núcleo (el tile sin solape) del resultado escalado.
            cx0, cy0 = (x0 - px0) * s, (y0 - py0) * s
            cw, ch = (x1 - x0) * s, (y1 - y0) * s
            out[y0 * s:y1 * s, x0 * s:x1 * s] = up[cy0:cy0 + ch, cx0:cx0 + cw]
            done += 1
            if report is not None:
                report(min(99, done * 100 // total))
    return out


def upscale(rgb, model_path, scale=4, report=None, token=None):
    """Sube el rgb (H, W, 3) uint8 al factor pedido (2 o 4). Para x2 se sube x4 y
    se reduce a la mitad con suavizado (mejor calidad que un x2 directo)."""
    up4 = upscale_x4(rgb, model_path, report=report, token=token)
    if up4 is None:
        return None
    if scale == NATIVE_SCALE:
        return up4
    h, w = rgb.shape[:2]
    tw, th = w * scale, h * scale
    rgba = imgproc.merge_rgb_alpha(up4, np.full(up4.shape[:2], 255, np.uint8))
    return imgproc.resize_rgba(rgba, tw, th)[:, :, :3]
