# ai/cv_effects.py
"""Funciones de vision clasica (OpenCV) del menu IA: sin modelos ni descargas.

  - detect_horizon_angle(): angulo del horizonte (Canny + HoughLinesP) para
    "Enderezar horizonte".
  - fix_red_eyes(): correccion de ojos rojos; sobre la SELECCION si la hay, o
    con deteccion automatica de ojos (cascada Haar) si no.

cv2 se importa PEREZOSAMENTE (la app arranca sin OpenCV instalado; comprobar
antes con cv_available()). Trabajo SINCRONO: pensado para el hilo secundario.
"""

import numpy as np


def cv_available():
    """True si opencv esta instalado (no se importa al arrancar Imago)."""
    try:
        import cv2  # noqa: F401
        return True
    except Exception:
        return False


def _cv2():
    """Importa cv2 con OpenCL DESACTIVADO. Motivo: con la app en un locale de
    coma decimal (es_ES), los kernels OpenCL que OpenCV genera al vuelo llevan
    "0,04f" en vez de "0.04f" y NO COMPILAN (fallo real visto en el stitcher del
    panorama, que usa OpenCL internamente). La via CPU no depende del locale."""
    import cv2
    try:
        cv2.ocl.setUseOpenCL(False)
    except Exception:
        pass
    return cv2


# ------------------------------------------------------- enderezar horizonte
def detect_horizon_angle(rgb, max_angle=30.0):
    """Devuelve el angulo (grados, positivo = horizonte caido hacia la derecha)
    que hay que corregir, o None si no se detecta un horizonte fiable.

    Canny + HoughLinesP sobre una version reducida; se quedan las lineas CASI
    horizontales (|angulo| <= max_angle) y se pondera por longitud (mediana
    ponderada), para que un horizonte largo mande sobre detalles cortos."""
    cv2 = _cv2()
    h, w = rgb.shape[:2]
    scale = min(1.0, 1000.0 / max(h, w))
    small = cv2.resize(rgb, (max(1, int(w * scale)), max(1, int(h * scale)))) \
        if scale < 1.0 else rgb
    gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
    # Umbrales de Canny ADAPTATIVOS a partir de la mediana (umbrales fijos se
    # pierden los horizontes de contraste moderado: cielo/mar brumosos, etc.).
    v = float(np.median(gray))
    low = int(max(20, 0.66 * v))
    high = int(max(60, 1.33 * v))
    edges = cv2.Canny(gray, low, high)
    min_len = int(small.shape[1] * 0.20)          # lineas de al menos 20% del ancho
    lines = cv2.HoughLinesP(edges, 1, np.pi / 360.0, threshold=60,
                            minLineLength=min_len, maxLineGap=8)
    if lines is None:
        return None
    angles, weights = [], []
    for x1, y1, x2, y2 in lines[:, 0]:
        ang = np.degrees(np.arctan2(y2 - y1, x2 - x1))
        if ang > 90:
            ang -= 180
        elif ang < -90:
            ang += 180
        if abs(ang) <= max_angle:                 # solo candidatas a horizonte
            angles.append(ang)
            weights.append(np.hypot(x2 - x1, y2 - y1))
    if not angles:
        return None
    # Mediana ponderada por longitud (robusta frente a lineas espureas).
    order = np.argsort(angles)
    a = np.asarray(angles, np.float64)[order]
    wgt = np.asarray(weights, np.float64)[order]
    cum = np.cumsum(wgt)
    angle = float(a[np.searchsorted(cum, cum[-1] / 2.0)])
    return angle


# ------------------------------------------------- correccion de perspectiva
def detect_document_quad(rgb):
    """Busca el CUADRILATERO dominante (documento, pantalla, fachada plana...)
    para rectificarlo a vista frontal. Devuelve (quad, (w, h)) o None.

    - quad: array (4, 2) float32 con las esquinas ORDENADAS (TL, TR, BR, BL) en
      coordenadas de la imagen original.
    - (w, h): tamano de destino, tomado de las longitudes de los lados (asi el
      rectificado apenas cambia la escala del contenido).

    Metodo: Canny adaptativo + dilatacion (cierra huecos) + contornos; el mayor
    contorno convexo que aproxime a 4 vertices y ocupe entre el 8% y el 95% del
    area (100% seria el marco de la propia imagen: nada que corregir)."""
    cv2 = _cv2()
    h, w = rgb.shape[:2]
    scale = min(1.0, 1000.0 / max(h, w))
    small = cv2.resize(rgb, (max(1, int(w * scale)), max(1, int(h * scale)))) \
        if scale < 1.0 else rgb
    sh, sw = small.shape[:2]
    gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    v = float(np.median(gray))
    edges = cv2.Canny(gray, int(max(20, 0.66 * v)), int(max(60, 1.33 * v)))
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    total = float(sh * sw)
    best = None
    best_area = 0.0
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 0.08 * total or area > 0.95 * total or area <= best_area:
            continue
        approx = cv2.approxPolyDP(cnt, 0.02 * cv2.arcLength(cnt, True), True)
        if len(approx) == 4 and cv2.isContourConvex(approx):
            best = approx.reshape(4, 2).astype(np.float32)
            best_area = area
    if best is None:
        return None

    # Ordenar TL, TR, BR, BL (suma minima = TL, maxima = BR; resta x-y maxima = TR).
    s = best.sum(axis=1)
    d = best[:, 0] - best[:, 1]
    quad = np.array([best[np.argmin(s)], best[np.argmax(d)],
                     best[np.argmax(s)], best[np.argmin(d)]], np.float32)
    quad /= scale                                   # a coordenadas originales
    tl, tr, br, bl = quad
    out_w = int(round(max(np.hypot(*(tr - tl)), np.hypot(*(br - bl)))))
    out_h = int(round(max(np.hypot(*(bl - tl)), np.hypot(*(br - tr)))))
    if out_w < 8 or out_h < 8:
        return None
    return quad, (out_w, out_h)


# --------------------------------------------------------------- panorama
def stitch_panorama(images_rgb, token=None):
    """Une varias fotos SOLAPADAS en un panorama (cv2.Stitcher: deteccion de
    caracteristicas, homografias, costuras y fusion). `images_rgb` = lista de
    arrays (H, W, 3) uint8. Devuelve (pano_rgb, None) si va bien, o
    (None, "sin_coincidencias") si las fotos no casan.

    Cada foto se limita a 2500 px de lado mayor: el remapeo de varias fotos
    grandes dispara memoria y tiempo, y para un panorama la resolucion final
    sigue siendo enorme."""
    cv2 = _cv2()
    imgs = []
    for im in images_rgb:
        if token is not None and token.cancelled:
            return None, "cancelado"
        h, w = im.shape[:2]
        s = min(1.0, 2500.0 / max(h, w))
        if s < 1.0:
            im = cv2.resize(im, (int(w * s), int(h * s)))
        imgs.append(np.ascontiguousarray(im[:, :, ::-1]))     # RGB -> BGR
    # PANORAMA (cámara giratoria, proyeccion esferica) y, si no converge, SCANS
    # (afin, para contenido PLANO: documentos, capturas, tiras escaneadas...).
    for mode in (cv2.Stitcher_PANORAMA, cv2.Stitcher_SCANS):
        if token is not None and token.cancelled:
            return None, "cancelado"
        stitcher = cv2.Stitcher_create(mode)
        try:
            status, pano = stitcher.stitch(imgs)
        except cv2.error:
            continue
        if status == cv2.Stitcher_OK and pano is not None:
            return np.ascontiguousarray(pano[:, :, ::-1]), None   # BGR -> RGB
    return None, "sin_coincidencias"


# ----------------------------------------------------------- ojos rojos
def _redness_fix(rgba, region_mask):
    """Corrige los pixeles ROJOS dentro de region_mask (bool): donde el rojo
    domina claramente sobre verde/azul, se sustituye por su luminancia neutra.
    Devuelve (rgba_nuevo, n_pixeles_corregidos)."""
    out = rgba.copy()
    r = rgba[:, :, 0].astype(np.int32)
    g = rgba[:, :, 1].astype(np.int32)
    b = rgba[:, :, 2].astype(np.int32)
    gb = (g + b) // 2
    # Rojo de flash: canal R claramente por encima del resto y con brillo minimo.
    red = region_mask & (r > 60) & (r * 2 > 3 * gb)
    n = int(red.sum())
    if n:
        neutral = np.clip(gb, 0, 255).astype(np.uint8)
        out[:, :, 0][red] = neutral[red]
        out[:, :, 1][red] = np.clip(g, 0, 255).astype(np.uint8)[red]
        out[:, :, 2][red] = np.clip(b, 0, 255).astype(np.uint8)[red]
    return out, n


def fix_red_eyes(rgba, selection_mask=None):
    """Corrige ojos rojos. Con `selection_mask` (bool H, W) actua SOLO ahi; sin
    ella, detecta los ojos automaticamente (cascada Haar de OpenCV) y corrige
    dentro de cada ojo detectado. Devuelve (rgba_nuevo, n_pixeles_corregidos)."""
    cv2 = _cv2()
    h, w = rgba.shape[:2]
    if selection_mask is not None:
        return _redness_fix(rgba, selection_mask.astype(bool))

    gray = cv2.cvtColor(rgba[:, :, :3], cv2.COLOR_RGB2GRAY)
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_eye.xml")
    eyes = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=6,
                                    minSize=(max(12, w // 60), max(12, h // 60)))
    if len(eyes) == 0:
        return rgba.copy(), 0
    region = np.zeros((h, w), bool)
    for ex, ey, ew, eh in eyes:
        # Elipse inscrita en el rectangulo del ojo (evita tocar cejas/piel).
        yy, xx = np.mgrid[0:h, 0:w]
        cx, cy = ex + ew / 2.0, ey + eh / 2.0
        region |= (((xx - cx) / (ew / 2.0)) ** 2 + ((yy - cy) / (eh / 2.0)) ** 2) <= 1.0
    return _redness_fix(rgba, region)
