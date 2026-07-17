# ai/colorize.py
"""Colorización automática de fotos en blanco y negro con DDColor.

El modelo (Qualcomm/DDColor, Apache-2.0) toma una imagen GRIS de 256x256 en 0..1
y predice los canales de color 'ab' del espacio Lab (salida (1, 2, 256, 256)).
Se combinan esos ab (reescalados) con la LUMINOSIDAD ORIGINAL a resolución
completa y se vuelve a RGB: así la nitidez del original se conserva y solo se
inventa el color.

Las conversiones sRGB<->Lab van en numpy (sin OpenCV). Trabajo SINCRONO: se
ejecuta en el hilo secundario del InferenceRunner.
"""

import numpy as np
from scipy import ndimage

from ai import imgproc
from ai.runner import get_session, run_session

MODEL_KEY = "ddcolor"
_SIZE = 256

# Blanco de referencia D65.
_XN, _YN, _ZN = 0.95047, 1.0, 1.08883


# ----------------------------------------------------------------- sRGB<->Lab
def rgb_to_lab(rgb):
    """rgb (H, W, 3) float 0..1 -> Lab (L 0..100, a/b ~-128..127)."""
    c = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    r, g, b = c[..., 0], c[..., 1], c[..., 2]
    x = (r * 0.4124 + g * 0.3576 + b * 0.1805) / _XN
    y = (r * 0.2126 + g * 0.7152 + b * 0.0722) / _YN
    z = (r * 0.0193 + g * 0.1192 + b * 0.9505) / _ZN

    def f(t):
        return np.where(t > 0.008856, np.cbrt(t), 7.787 * t + 16.0 / 116.0)

    fx, fy, fz = f(x), f(y), f(z)
    L = 116.0 * fy - 16.0
    a = 500.0 * (fx - fy)
    bb = 200.0 * (fy - fz)
    return np.stack([L, a, bb], axis=-1)


def lab_to_rgb(lab):
    """Lab -> rgb (H, W, 3) float 0..1 (recortado)."""
    L, a, b = lab[..., 0], lab[..., 1], lab[..., 2]
    fy = (L + 16.0) / 116.0
    fx = fy + a / 500.0
    fz = fy - b / 200.0

    def fi(t):
        t3 = t ** 3
        return np.where(t3 > 0.008856, t3, (t - 16.0 / 116.0) / 7.787)

    x = fi(fx) * _XN
    y = fi(fy) * _YN
    z = fi(fz) * _ZN
    r = x * 3.2406 + y * -1.5372 + z * -0.4986
    g = x * -0.9689 + y * 1.8758 + z * 0.0415
    bb = x * 0.0557 + y * -0.2040 + z * 1.0570
    rgb = np.stack([r, g, bb], axis=-1)

    def gamma(ch):
        ch = np.clip(ch, 0.0, None)
        return np.where(ch <= 0.0031308, 12.92 * ch, 1.055 * np.power(ch, 1.0 / 2.4) - 0.055)

    return np.clip(gamma(rgb), 0.0, 1.0)


# ------------------------------------------------------------------- pipeline
def colorize(rgb, model_path):
    """rgb (H, W, 3) uint8 -> rgb (H, W, 3) uint8 colorizado. La luminosidad se
    conserva (solo se inventa el color); si la entrada tiene color, se re-colorea."""
    h, w = rgb.shape[:2]
    rgbf = rgb.astype(np.float32) / 255.0
    l_orig = rgb_to_lab(rgbf)[..., 0]        # luminosidad a resolución completa

    # Entrada del modelo: versión GRIS de 256x256 (L con ab=0).
    small = imgproc.resize_rgba(
        imgproc.merge_rgb_alpha(rgb, np.full((h, w), 255, np.uint8)),
        _SIZE, _SIZE)[:, :, :3]
    l_small = rgb_to_lab(small.astype(np.float32) / 255.0)[..., 0]
    gray_lab = np.stack([l_small, np.zeros_like(l_small), np.zeros_like(l_small)], -1)
    gray_rgb = lab_to_rgb(gray_lab)
    x = np.ascontiguousarray(gray_rgb.transpose(2, 0, 1)[None].astype(np.float32))

    session = get_session(model_path)
    in_name = session.get_inputs()[0].name
    out = run_session(session, {in_name: x})[0]      # (1, 2, 256, 256)
    ab_small = out[0].transpose(1, 2, 0)             # (256, 256, 2)

    # Reescalar ab a resolución completa (bilineal) y combinar con L original.
    ab = ndimage.zoom(ab_small, (h / _SIZE, w / _SIZE, 1), order=1)
    out_lab = np.dstack([l_orig, ab])
    out_rgb = lab_to_rgb(out_lab)
    return (out_rgb * 255.0 + 0.5).astype(np.uint8)
