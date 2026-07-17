# ai/denoise.py
"""Reducción de ruido con IA (SCUNet real, Apache-2.0).

SCUNet (Swin-Conv-UNet) exige que el alto y el ancho sean MÚLTIPLO DE 64 (por las
ventanas del transformer y el submuestreo del UNet). Se rellena la imagen por
reflexión hasta el múltiplo de 64 y, tras inferir, se recorta al tamaño original.
Las imágenes grandes se procesan por TILES (512, múltiplo de 64) con solape, para
acotar la memoria. Entrada/salida en 0..1.

NOTA (GPU): SCUNet usa atención de transformer (Swin) que provoca un access violation
en DirectML; por eso, en GPUs por DirectML (AMD/Intel) esta función CAE A CPU
automáticamente (ver ai/subproc.py), donde es LENTA pero da resultados excelentes. Por
eso ai_denoise avisa antes de que puede tardar varios minutos. En NVIDIA (CUDA) corre
en GPU. Se prefiere su calidad a alternativas ligeras (NAFNet dejaba costuras/menor
calidad).

Trabajo SINCRONO: se ejecuta en el hilo secundario del InferenceRunner.
"""

import math
import numpy as np

from ai.runner import get_session, run_session

_MULT = 64
_TILE = 512
_OVERLAP = 64


def _run(session, in_name, rgb_tile):
    """Denoisa un tile (h, w, 3) uint8 con h,w múltiplos de 64 -> (h, w, 3) uint8."""
    x = np.ascontiguousarray((rgb_tile.astype(np.float32) / 255.0).transpose(2, 0, 1)[None])
    out = run_session(session, {in_name: x})[0]
    return (np.clip(out[0].transpose(1, 2, 0), 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)


def _positions(length, tile, stride):
    if length <= tile:
        return [0]
    ps = list(range(0, length - tile + 1, stride))
    if ps[-1] != length - tile:
        ps.append(length - tile)
    return ps


def denoise(rgb, model_path, report=None, token=None):
    """rgb (H, W, 3) uint8 -> rgb (H, W, 3) uint8 con menos ruido. Sincrono."""
    h, w = rgb.shape[:2]
    session = get_session(model_path)
    in_name = session.get_inputs()[0].name

    # Relleno por reflexión hasta múltiplo de 64 (SCUNet lo exige).
    ph = math.ceil(h / _MULT) * _MULT
    pw = math.ceil(w / _MULT) * _MULT
    pad = np.pad(rgb, ((0, ph - h), (0, pw - w), (0, 0)), mode="reflect")

    if ph <= _TILE and pw <= _TILE:
        out = _run(session, in_name, pad)      # una sola pasada
        return out[:h, :w]

    # Tiles de 512 (múltiplo de 64) con solape; núcleo sin solape a la salida.
    stride = _TILE - _OVERLAP
    xs = _positions(pw, _TILE, stride)
    ys = _positions(ph, _TILE, stride)
    out = np.empty((ph, pw, 3), np.uint8)
    total = len(xs) * len(ys)
    done = 0
    for y in ys:
        for x in xs:
            if token is not None and token.cancelled:
                return None
            up = _run(session, in_name, pad[y:y + _TILE, x:x + _TILE])
            # Recortar el núcleo (descartar medio solape salvo en los bordes).
            ox0 = 0 if x == 0 else _OVERLAP // 2
            oy0 = 0 if y == 0 else _OVERLAP // 2
            ox1 = _TILE if (x + _TILE) >= pw else _TILE - _OVERLAP // 2
            oy1 = _TILE if (y + _TILE) >= ph else _TILE - _OVERLAP // 2
            out[y + oy0:y + oy1, x + ox0:x + ox1] = up[oy0:oy1, ox0:ox1]
            done += 1
            if report is not None:
                report(min(99, done * 100 // total))
    return out[:h, :w]
