# tools/shape_geometry.py
"""Geometría de las formas dibujables (estilo Paint.NET).

Cada forma se construye como un QPainterPath inscrito en el rectángulo que el
usuario define al arrastrar. Los polígonos y estrellas se calculan por vértices;
el resto son paths directos (líneas, arcos o curvas Bézier).

SHAPE_CATEGORIES define el catálogo (categoría -> [(id, nombre)]), usado por el
selector de formas y por el generador de iconos."""

import math
from PySide6.QtCore import QRectF
from PySide6.QtGui import QPainterPath


def get_shape_categories():
    from i18n import t
    return [
        (t("shape.cat.basic", default="Básico"), [
        ("rectangle",      t("shape.rectangle", default="Rectángulo")),
        ("rounded_rect",   t("shape.rounded_rect", default="Rectángulo redondeado")),
        ("ellipse",        t("shape.ellipse", default="Elipse")),
        ("diamond",        t("shape.diamond", default="Diamante")),
        ("trapezoid",      t("shape.trapezoid", default="Trapezoide")),
        ("parallelogram",  t("shape.parallelogram", default="Paralelogramo")),
        ("triangle",       t("shape.triangle", default="Triángulo")),
        ("right_triangle", t("shape.right_triangle", default="Triángulo rectángulo")),
    ]),
        (t("shape.cat.poly", default="Polígonos y estrellas"), [
        ("pentagon", t("shape.pentagon", default="Pentágono")),
        ("hexagon",  t("shape.hexagon", default="Hexágono")),
        ("heptagon", t("shape.heptagon", default="Heptágono")),
        ("octagon",  t("shape.octagon", default="Octágono")),
        ("star_3",   t("shape.star_3", default="Estrella de tres puntas")),
        ("star_4",   t("shape.star_4", default="Estrella de cuatro puntas")),
        ("star_5",   t("shape.star_5", default="Estrella de cinco puntas")),
        ("star_6",   t("shape.star_6", default="Estrella de seis puntas")),
    ]),
        (t("shape.cat.arrows", default="Flechas"), [
        ("arrow",          t("shape.arrow", default="Flecha")),
        ("arrow_notched",  t("shape.arrow_notched", default="Flecha dentada")),
        ("pentagon_arrow", t("shape.pentagon_arrow", default="Flecha del pentágono")),
        ("chevron",        t("shape.chevron", default="Chevron")),
    ]),
        (t("shape.cat.callouts", default="Rótulos"), [
        ("callout_rect",    t("shape.callout_rect", default="Llamada rectangular")),
        ("callout_rounded", t("shape.callout_rounded", default="Llamada rectangular redondeada")),
        ("callout_ellipse", t("shape.callout_ellipse", default="Llamada elíptica")),
        ("speech_cloud",    t("shape.speech_cloud", default="Nube de diálogo")),
    ]),
        (t("shape.cat.symbols", default="Símbolos"), [
        ("lightning", t("shape.lightning", default="Rayo")),
        ("check",     t("shape.check", default="Marca de verificación")),
        ("multiply",  t("shape.multiply", default="Multiplicar")),
        ("gear",      t("shape.gear", default="Engranaje")),
        ("heart",     t("shape.heart", default="Corazón")),
        ]),
    ]

# Funciones para obtener nombres de formas traducidos dinámicamente
def get_shape_name(shape_id):
    for _, items in get_shape_categories():
        for sid, name in items:
            if sid == shape_id:
                return name
    return ""

def get_shape_id_by_name(shape_name):
    for _, items in get_shape_categories():
        for sid, name in items:
            if name == shape_name:
                return sid
    return DEFAULT_SHAPE
DEFAULT_SHAPE = "rectangle"


# ----------------------------------------------------------------------------
# Generadores de VÉRTICES (puros: solo math y tuplas -> validables sin Qt)
# ----------------------------------------------------------------------------
def regular_polygon_vertices(cx, cy, rx, ry, n, rot_deg=-90.0):
    """n vértices de un polígono regular inscrito en la elipse (rx, ry)."""
    out = []
    base = math.radians(rot_deg)
    for i in range(n):
        a = base + 2.0 * math.pi * i / n
        out.append((cx + rx * math.cos(a), cy + ry * math.sin(a)))
    return out


def star_vertices(cx, cy, rx, ry, points, inner_ratio, rot_deg=-90.0):
    """2*points vértices alternando radio externo (1.0) e interno (inner_ratio)."""
    out = []
    base = math.radians(rot_deg)
    for i in range(points * 2):
        a = base + math.pi * i / points
        r = 1.0 if (i % 2 == 0) else inner_ratio
        out.append((cx + rx * r * math.cos(a), cy + ry * r * math.sin(a)))
    return out


def diamond_vertices(x, y, w, h):
    return [(x + w / 2, y), (x + w, y + h / 2), (x + w / 2, y + h), (x, y + h / 2)]


def trapezoid_vertices(x, y, w, h, inset=0.25):
    dx = w * inset
    return [(x + dx, y), (x + w - dx, y), (x + w, y + h), (x, y + h)]


def parallelogram_vertices(x, y, w, h, skew=0.25):
    dx = w * skew
    return [(x + dx, y), (x + w, y), (x + w - dx, y + h), (x, y + h)]


def triangle_vertices(x, y, w, h):
    return [(x + w / 2, y), (x + w, y + h), (x, y + h)]


def right_triangle_vertices(x, y, w, h):
    return [(x, y), (x, y + h), (x + w, y + h)]


def arrow_vertices(x, y, w, h, shaft=0.40, head=0.45):
    """Flecha de bloque apuntando a la derecha."""
    sh = h * shaft
    hw = w * head
    cy = y + h / 2
    top = cy - sh / 2
    bot = cy + sh / 2
    xh = x + w - hw
    return [(x, top), (xh, top), (xh, y), (x + w, cy),
            (xh, y + h), (xh, bot), (x, bot)]


def notched_arrow_vertices(x, y, w, h, shaft=0.40, head=0.45, notch=0.12):
    sh = h * shaft
    hw = w * head
    nx = w * notch
    cy = y + h / 2
    top = cy - sh / 2
    bot = cy + sh / 2
    xh = x + w - hw
    return [(x, top), (xh, top), (xh, y), (x + w, cy),
            (xh, y + h), (xh, bot), (x, bot), (x + nx, cy)]


def pentagon_arrow_vertices(x, y, w, h, tip=0.35):
    tx = w * tip
    cy = y + h / 2
    return [(x, y), (x + w - tx, y), (x + w, cy), (x + w - tx, y + h), (x, y + h)]


def chevron_vertices(x, y, w, h, tip=0.35):
    tx = w * tip
    cy = y + h / 2
    return [(x, y), (x + w - tx, y), (x + w, cy), (x + w - tx, y + h),
            (x, y + h), (x + tx, cy)]


def callout_rect_vertices(x, y, w, h, body=0.72, tail_x=0.22, tail_w=0.16):
    by = y + h * body
    tx = x + w * tail_x
    return [(x, y), (x + w, y), (x + w, by),
            (tx + w * tail_w, by), (x + w * (tail_x - 0.02), y + h),
            (tx, by), (x, by)]


def lightning_vertices(x, y, w, h):
    """Rayo (zigzag) inscrito en el rect, en coordenadas relativas 0..1."""
    rel = [(0.55, 0.00), (0.18, 0.55), (0.45, 0.55),
           (0.30, 1.00), (0.82, 0.40), (0.52, 0.40), (0.72, 0.00)]
    return [(x + rx * w, y + ry * h) for rx, ry in rel]


def check_vertices(x, y, w, h):
    """Marca de verificación gruesa (relleno)."""
    rel = [(0.05, 0.55), (0.20, 0.42), (0.40, 0.62), (0.80, 0.12),
           (0.95, 0.27), (0.40, 0.92), (0.05, 0.55)]
    return [(x + rx * w, y + ry * h) for rx, ry in rel[:-1]]


def multiply_vertices(x, y, w, h, t=0.18):
    """Aspa (✕) como polígono de 12 vértices."""
    rel = [(0.0, t), (t, 0.0), (0.5, 0.5 - t), (1 - t, 0.0), (1.0, t),
           (0.5 + t, 0.5), (1.0, 1 - t), (1 - t, 1.0), (0.5, 0.5 + t),
           (t, 1.0), (0.0, 1 - t), (0.5 - t, 0.5)]
    return [(x + rx * w, y + ry * h) for rx, ry in rel]


def gear_outer_vertices(cx, cy, rx, ry, teeth=8, tooth_depth=0.28, tooth_frac=0.5):
    """Contorno exterior del engranaje (dientes rectangulares)."""
    out = []
    n = teeth
    inner = 1.0 - tooth_depth
    half = (math.pi / n) * tooth_frac
    for i in range(n):
        a = -math.pi / 2 + 2.0 * math.pi * i / n
        # meseta exterior del diente
        out.append((cx + rx * math.cos(a - half), cy + ry * math.sin(a - half)))
        out.append((cx + rx * math.cos(a + half), cy + ry * math.sin(a + half)))
        # valle hasta el siguiente diente
        a2 = -math.pi / 2 + 2.0 * math.pi * (i + 0.5) / n
        out.append((cx + rx * inner * math.cos(a2 - half), cy + ry * inner * math.sin(a2 - half)))
        out.append((cx + rx * inner * math.cos(a2 + half), cy + ry * inner * math.sin(a2 + half)))
    return out


# ----------------------------------------------------------------------------
# Ensamblado en QPainterPath
# ----------------------------------------------------------------------------
def _path_from(verts, close=True):
    p = QPainterPath()
    p.moveTo(verts[0][0], verts[0][1])
    for vx, vy in verts[1:]:
        p.lineTo(vx, vy)
    if close:
        p.closeSubpath()
    return p


def _heart_path(x, y, w, h):
    p = QPainterPath()
    cx = x + w / 2
    p.moveTo(cx, y + h * 0.95)
    p.cubicTo(x + w * 0.02, y + h * 0.58,  x + w * 0.05, y + h * 0.12,  x + w * 0.28, y + h * 0.12)
    p.cubicTo(x + w * 0.43, y + h * 0.12,  cx,            y + h * 0.27,  cx,            y + h * 0.36)
    p.cubicTo(cx,            y + h * 0.27,  x + w * 0.57, y + h * 0.12,  x + w * 0.72, y + h * 0.12)
    p.cubicTo(x + w * 0.95, y + h * 0.12,  x + w * 0.98, y + h * 0.58,  cx,            y + h * 0.95)
    p.closeSubpath()
    return p


def _cloud_path(x, y, w, h):
    """Nube de diálogo: unión de varios lóbulos elípticos + cola de burbujas."""
    body_top = y + h * 0.10
    body_h = h * 0.66
    path = QPainterPath()
    path.addEllipse(QRectF(x + w * 0.10, body_top + body_h * 0.20, w * 0.80, body_h * 0.80))
    lobes = [
        (0.04, 0.34, 0.34, 0.42), (0.20, 0.06, 0.34, 0.42),
        (0.46, 0.00, 0.36, 0.42), (0.66, 0.10, 0.32, 0.40),
        (0.04, 0.30, 0.30, 0.46),
    ]
    for rx, ry, rw, rh in lobes:
        e = QPainterPath()
        e.addEllipse(QRectF(x + w * rx, y + h * ry, w * rw, h * rh))
        path = path.united(e)
    # Cola: tres burbujas decrecientes hacia abajo-izquierda
    for cxr, cyr, cr in [(0.26, 0.72, 0.10), (0.18, 0.86, 0.07), (0.12, 0.96, 0.045)]:
        b = QPainterPath()
        b.addEllipse(QRectF(x + w * (cxr - cr), y + h * (cyr - cr), w * cr * 2, h * cr * 2))
        path = path.united(b)
    return path.simplified()


def _callout_rounded_path(x, y, w, h, body=0.72):
    by = y + h * body
    r = min(w, h) * 0.16
    body_path = QPainterPath()
    body_path.addRoundedRect(QRectF(x, y, w, by - y), r, r)
    tail = _path_from([(x + w * 0.22, by - 1), (x + w * 0.38, by - 1),
                       (x + w * 0.20, y + h)])
    return body_path.united(tail).simplified()


def _callout_ellipse_path(x, y, w, h, body=0.74):
    by = y + h * body
    body_path = QPainterPath()
    body_path.addEllipse(QRectF(x, y, w, by - y))
    tail = _path_from([(x + w * 0.28, y + (by - y) * 0.78),
                       (x + w * 0.50, y + (by - y) * 0.92),
                       (x + w * 0.24, y + h)])
    return body_path.united(tail).simplified()


def build_shape_path(shape_id, rect):
    """Devuelve el QPainterPath de la forma inscrito en `rect` (QRect/QRectF)."""
    r = QRectF(rect).normalized()
    x, y, w, h = r.x(), r.y(), r.width(), r.height()
    cx, cy = x + w / 2.0, y + h / 2.0
    rx, ry = w / 2.0, h / 2.0

    if shape_id == "rectangle":
        p = QPainterPath(); p.addRect(r); return p
    if shape_id == "rounded_rect":
        rad = min(w, h) * 0.20
        p = QPainterPath(); p.addRoundedRect(r, rad, rad); return p
    if shape_id == "ellipse":
        p = QPainterPath(); p.addEllipse(r); return p
    if shape_id == "diamond":
        return _path_from(diamond_vertices(x, y, w, h))
    if shape_id == "trapezoid":
        return _path_from(trapezoid_vertices(x, y, w, h))
    if shape_id == "parallelogram":
        return _path_from(parallelogram_vertices(x, y, w, h))
    if shape_id == "triangle":
        return _path_from(triangle_vertices(x, y, w, h))
    if shape_id == "right_triangle":
        return _path_from(right_triangle_vertices(x, y, w, h))

    polys = {"pentagon": 5, "hexagon": 6, "heptagon": 7, "octagon": 8}
    if shape_id in polys:
        return _path_from(regular_polygon_vertices(cx, cy, rx, ry, polys[shape_id]))

    stars = {"star_3": (3, 0.42), "star_4": (4, 0.40),
             "star_5": (5, 0.38), "star_6": (6, 0.52)}
    if shape_id in stars:
        n, inner = stars[shape_id]
        return _path_from(star_vertices(cx, cy, rx, ry, n, inner))

    if shape_id == "arrow":
        return _path_from(arrow_vertices(x, y, w, h))
    if shape_id == "arrow_notched":
        return _path_from(notched_arrow_vertices(x, y, w, h))
    if shape_id == "pentagon_arrow":
        return _path_from(pentagon_arrow_vertices(x, y, w, h))
    if shape_id == "chevron":
        return _path_from(chevron_vertices(x, y, w, h))

    if shape_id == "callout_rect":
        return _path_from(callout_rect_vertices(x, y, w, h))
    if shape_id == "callout_rounded":
        return _callout_rounded_path(x, y, w, h)
    if shape_id == "callout_ellipse":
        return _callout_ellipse_path(x, y, w, h)
    if shape_id == "speech_cloud":
        return _cloud_path(x, y, w, h)

    if shape_id == "lightning":
        return _path_from(lightning_vertices(x, y, w, h))
    if shape_id == "check":
        return _path_from(check_vertices(x, y, w, h))
    if shape_id == "multiply":
        return _path_from(multiply_vertices(x, y, w, h))
    if shape_id == "gear":
        outer = _path_from(gear_outer_vertices(cx, cy, rx, ry))
        hole = QPainterPath()
        hole.addEllipse(QRectF(cx - rx * 0.32, cy - ry * 0.32, rx * 0.64, ry * 0.64))
        return outer.subtracted(hole)
    if shape_id == "heart":
        return _heart_path(x, y, w, h)

    # Por defecto: rectángulo
    p = QPainterPath(); p.addRect(r); return p