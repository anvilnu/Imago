# ai/imgproc.py
"""Helpers de pre/postproceso de imagen para las funciones de IA.

Reglas de oro (ver propuesta_ia.md):
  - La conversion QImage <-> NumPy SIEMPRE pasa por qimage_to_array /
    array_to_qimage de adjustments.py (fuerzan Format_RGBA8888 y respetan el
    padding de fila). NO usar el truco qimage.bits().reshape(h, w, 4).
  - El escalado suave se hace con QImage (Qt.SmoothTransformation), sin OpenCV.

Aqui viven solo primitivas GENERICAS y reutilizables (separar/mezclar canales,
redimensionar, normalizar, pasar a tensor NCHW/NHWC). El pre/postproceso
especifico de cada modelo (medias, desviaciones, tamano de entrada) lo fija la
funcion que use el modelo, apoyandose en estas piezas.
"""

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage

# Reutilizamos las conversiones YA existentes (no reimplementar: respetan el
# padding de fila de QImage).
from adjustments import qimage_to_array, array_to_qimage


# --------------------------------------------------------------- canales RGBA
def split_rgb_alpha(arr):
    """Separa un array RGBA (H, W, 4) en (rgb (H, W, 3), alpha (H, W)) uint8."""
    return arr[:, :, :3].copy(), arr[:, :, 3].copy()


def merge_rgb_alpha(rgb, alpha):
    """Combina rgb (H, W, 3) y alpha (H, W) en un RGBA (H, W, 4) uint8."""
    h, w = rgb.shape[:2]
    out = np.empty((h, w, 4), dtype=np.uint8)
    out[:, :, :3] = rgb[:, :, :3]
    out[:, :, 3] = alpha
    return out


# ------------------------------------------------------------- redimensionado
def resize_rgba(arr, out_w, out_h, smooth=True):
    """Redimensiona un RGBA (H, W, 4) uint8 a (out_h, out_w) usando el escalado
    de QImage (suave por defecto). Devuelve un RGBA (out_h, out_w, 4) uint8."""
    h, w = arr.shape[:2]
    qimg = array_to_qimage(np.ascontiguousarray(arr[:, :, :4]), w, h)
    mode = Qt.SmoothTransformation if smooth else Qt.FastTransformation
    scaled = qimg.scaled(int(out_w), int(out_h),
                         Qt.IgnoreAspectRatio, mode)
    return qimage_to_array(scaled)


def resize_mask(mask, out_w, out_h, smooth=True):
    """Redimensiona una mascara de un canal (H, W) uint8 a (out_h, out_w). La
    envolvemos como escala de grises RGBA para reaprovechar resize_rgba."""
    h, w = mask.shape[:2]
    rgba = np.empty((h, w, 4), dtype=np.uint8)
    rgba[:, :, 0] = rgba[:, :, 1] = rgba[:, :, 2] = mask
    rgba[:, :, 3] = 255
    out = resize_rgba(rgba, out_w, out_h, smooth=smooth)
    return out[:, :, 0].copy()


# ---------------------------------------------------------- tensor de entrada
def to_tensor(rgb, mean=None, std=None, layout="NCHW", scale=1.0 / 255.0):
    """Convierte un rgb (H, W, 3) uint8 en un tensor float32 listo para ONNX.

    - scale: factor para pasar de 0..255 a 0..1 (por defecto 1/255).
    - mean/std: normalizacion opcional por canal (secuencias de 3 valores en el
      mismo rango que 'scale' ya aplicado). Si son None no se normaliza.
    - layout: "NCHW" (por canales, lo habitual en ONNX) o "NHWC".
    Devuelve un array con la dimension de lote N=1 ya anadida.
    """
    x = rgb.astype(np.float32) * scale
    if mean is not None:
        x = x - np.asarray(mean, dtype=np.float32)
    if std is not None:
        x = x / np.asarray(std, dtype=np.float32)
    if layout == "NCHW":
        x = np.transpose(x, (2, 0, 1))          # HWC -> CHW
    return np.ascontiguousarray(x[np.newaxis, ...])   # anade N=1


def from_tensor(x, layout="NCHW"):
    """Inverso aproximado de to_tensor para SALIDAS de imagen: quita el lote y
    devuelve un array (H, W, C) float32 (sin desnormalizar; eso lo hace quien
    conozca mean/std del modelo)."""
    x = np.asarray(x)
    if x.ndim == 4:
        x = x[0]                                  # quita N
    if layout == "NCHW":
        x = np.transpose(x, (1, 2, 0))            # CHW -> HWC
    return x


def to_uint8(arr):
    """Recorta a 0..255 y convierte a uint8 (para volcar salidas de modelo a
    pixeles). Acepta arrays en 0..1 (los escala) o ya en 0..255."""
    a = np.asarray(arr, dtype=np.float32)
    if a.size and a.max() <= 1.0 + 1e-6:
        a = a * 255.0
    return np.clip(a, 0, 255).astype(np.uint8)
