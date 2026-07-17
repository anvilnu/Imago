# ai/face_restore.py
"""Restauración de caras con GFPGAN (Apache-2.0) + detección YuNet (Apache-2.0).

Pipeline (todo sin OpenCV; los warps se hacen con QTransform):
  1. YuNet detecta las caras y sus 5 puntos (ojos, nariz, comisuras).
  2. Cada cara se ALINEA a la plantilla FFHQ de 512x512 (transformación de
     similitud por mínimos cuadrados, umeyama) y se recorta.
  3. GFPGAN reconstruye la cara alineada (512x512, normalizada a [-1, 1]).
  4. La cara restaurada se PEGA de vuelta con la transformación inversa y un
     borde difuminado (feather) para fundirla con la imagen.

Trabajo SINCRONO: se ejecuta en el hilo secundario del InferenceRunner.
"""

import numpy as np
from PySide6.QtGui import QImage, QPainter, QTransform

from ai import imgproc
from ai.runner import get_session, run_session

YUNET_SIZE = 640
GFPGAN_SIZE = 512

# Plantilla FFHQ de 5 puntos a 512 (facexlib/GFPGAN), en coordenadas de imagen:
# ojo izquierdo, ojo derecho, nariz, comisura izquierda, comisura derecha. El
# orden de los puntos de YuNet coincide (izquierda->derecha en la imagen).
_FACE_TEMPLATE = np.array([
    [192.98138, 239.94708],
    [318.90277, 240.19360],
    [256.63416, 314.01935],
    [201.26117, 371.41043],
    [313.08905, 371.15118],
], dtype=np.float32)


# --------------------------------------------------------------- deteccion
def _decode_yunet(session, outs, thr):
    d = {o.name: v for o, v in zip(session.get_outputs(), outs)}
    dets = []
    for stride in (8, 16, 32):
        cls = d[f"cls_{stride}"][0, :, 0]
        obj = d[f"obj_{stride}"][0, :, 0]
        bbox = d[f"bbox_{stride}"][0]
        kps = d[f"kps_{stride}"][0]
        score = np.clip(cls * obj, 0.0, 1.0)
        cols = YUNET_SIZE // stride
        for idx in np.where(score > thr)[0]:
            r, c = idx // cols, idx % cols
            cx = (c + bbox[idx, 0]) * stride
            cy = (r + bbox[idx, 1]) * stride
            bw = np.exp(bbox[idx, 2]) * stride
            bh = np.exp(bbox[idx, 3]) * stride
            pts = np.array([[(c + kps[idx, 2 * k]) * stride,
                             (r + kps[idx, 2 * k + 1]) * stride] for k in range(5)],
                           dtype=np.float32)
            dets.append((float(score[idx]), cx - bw / 2, cy - bh / 2, bw, bh, pts))
    return dets


def _nms(dets, iou_thr=0.3):
    dets = sorted(dets, key=lambda t: t[0], reverse=True)

    def iou(a, b):
        ax0, ay0, aw, ah = a[1:5]
        bx0, by0, bw, bh = b[1:5]
        ix0, iy0 = max(ax0, bx0), max(ay0, by0)
        ix1, iy1 = min(ax0 + aw, bx0 + bw), min(ay0 + ah, by0 + bh)
        inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
        return inter / (aw * ah + bw * bh - inter + 1e-6)

    keep = []
    for det in dets:
        if all(iou(det, k) < iou_thr for k in keep):
            keep.append(det)
    return keep


def detect_faces(rgb, yunet_path, thr=0.6):
    """Devuelve una lista de landmarks (5, 2) en coordenadas de la imagen original."""
    h, w = rgb.shape[:2]
    inp = imgproc.resize_rgba(
        imgproc.merge_rgb_alpha(rgb, np.full((h, w), 255, np.uint8)),
        YUNET_SIZE, YUNET_SIZE)[:, :, :3]
    x = np.ascontiguousarray(inp.astype(np.float32).transpose(2, 0, 1)[None])
    session = get_session(yunet_path)
    outs = session.run(None, {session.get_inputs()[0].name: x})
    dets = _nms(_decode_yunet(session, outs, thr))
    sx, sy = w / YUNET_SIZE, h / YUNET_SIZE
    faces = []
    for det in dets:
        pts = det[5].copy()
        pts[:, 0] *= sx
        pts[:, 1] *= sy
        faces.append(pts)
    return faces


# ------------------------------------------------------- alineacion / warp
def _umeyama(src, dst):
    """Transformación de similitud 2x3 (escala+rotación+traslación) que lleva
    `src` a `dst` por mínimos cuadrados (algoritmo de Umeyama)."""
    n = src.shape[0]
    src_mean = src.mean(0)
    dst_mean = dst.mean(0)
    src_d = src - src_mean
    dst_d = dst - dst_mean
    cov = (dst_d.T @ src_d) / n
    u, s, vt = np.linalg.svd(cov)
    dd = np.ones(2)
    if np.linalg.det(u @ vt) < 0:
        dd[-1] = -1.0
    rot = u @ np.diag(dd) @ vt
    var = (src_d ** 2).sum() / n
    scale = (s * dd).sum() / var
    t = dst_mean - scale * rot @ src_mean
    m = np.zeros((2, 3), np.float32)
    m[:2, :2] = scale * rot
    m[:, 2] = t
    return m


def _qtransform(m):
    """QTransform desde una afín 2x3 (x,y)->(m00 x+m01 y+m02, m10 x+m11 y+m12)."""
    return QTransform(float(m[0, 0]), float(m[1, 0]),
                      float(m[0, 1]), float(m[1, 1]),
                      float(m[0, 2]), float(m[1, 2]))


def _feather_mask(size, border):
    """Máscara cuadrada (size, size) uint8: 255 en el centro, baja a 0 en el
    borde a lo largo de `border` px (para fundir la cara pegada)."""
    r = np.ones(size, np.float32)
    ramp = (np.arange(border, dtype=np.float32) + 1.0) / (border + 1.0)
    r[:border] = ramp
    r[-border:] = ramp[::-1]
    m = np.outer(r, r)
    return (m * 255.0 + 0.5).astype(np.uint8)


def _run_gfpgan(session, in_name, aligned_rgb):
    """Cara alineada (512, 512, 3) uint8 -> cara restaurada (512, 512, 3) uint8."""
    x = ((aligned_rgb.astype(np.float32) / 255.0 - 0.5) / 0.5).transpose(2, 0, 1)[None]
    out = run_session(session, {in_name: np.ascontiguousarray(x)})[0]
    o = out[0].transpose(1, 2, 0) * 0.5 + 0.5
    return (np.clip(o, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)


def restore(rgb, yunet_path, gfpgan_path, report=None, token=None):
    """rgb (H, W, 3) uint8 -> (rgb restaurado (H, W, 3) uint8, nº de caras). El
    array es None si se canceló; nº de caras 0 si no se detectó ninguna."""
    h, w = rgb.shape[:2]
    faces = detect_faces(rgb, yunet_path)
    if not faces:
        return rgb.copy(), 0

    full_q = imgproc.array_to_qimage(
        imgproc.merge_rgb_alpha(rgb, np.full((h, w), 255, np.uint8)), w, h)
    result_q = full_q.convertToFormat(QImage.Format_ARGB32)

    session = get_session(gfpgan_path)
    in_name = session.get_inputs()[0].name
    feather = _feather_mask(GFPGAN_SIZE, 48)

    for i, lms in enumerate(faces):
        if token is not None and token.cancelled:
            return None, 0
        m = _umeyama(lms, _FACE_TEMPLATE)
        # Alinear: warp de la imagen completa a 512x512 con la similitud.
        aligned_q = QImage(GFPGAN_SIZE, GFPGAN_SIZE, QImage.Format_RGBA8888)
        aligned_q.fill(0)
        p = QPainter(aligned_q)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        p.setTransform(_qtransform(m))
        p.drawImage(0, 0, full_q)
        p.end()
        aligned = imgproc.qimage_to_array(aligned_q)[:, :, :3]

        restored = _run_gfpgan(session, in_name, aligned)

        # Pegar de vuelta con la inversa y el borde difuminado.
        a = m[:2, :2]
        a_inv = np.linalg.inv(a)
        t_inv = -a_inv @ m[:, 2]
        m_inv = np.concatenate([a_inv, t_inv[:, None]], axis=1).astype(np.float32)
        face_q = imgproc.array_to_qimage(
            imgproc.merge_rgb_alpha(restored, feather), GFPGAN_SIZE, GFPGAN_SIZE)
        p = QPainter(result_q)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        p.setTransform(_qtransform(m_inv))
        p.drawImage(0, 0, face_q)
        p.end()

        if report is not None:
            report(min(99, (i + 1) * 100 // len(faces)))

    return imgproc.qimage_to_array(result_q)[:, :, :3], len(faces)
