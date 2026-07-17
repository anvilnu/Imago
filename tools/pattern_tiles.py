# tools/pattern_tiles.py
"""Patrones de relleno PROCEDURALES (azulejos repetibles) que van más allá de
los estilos nativos de Qt (Qt.BrushStyle). Cada patrón se genera por código como
un QPixmap pequeño y "sin costuras" (tileable) que se usa como pincel de textura
(QBrush(pixmap)). Las zonas transparentes del azulejo dejan ver lo que hay debajo.

De momento solo lo usa el PINCEL. Los azulejos se cachean por (id, color de
frente, color de fondo) para no regenerarlos en cada estampa.

Patrones de DOS tonos ('two_tone'): usan color de frente + color de fondo
(primario/secundario). Los de un tono usan frente sobre fondo TRANSPARENTE."""

import math
from PySide6.QtGui import (QPixmap, QPainter, QColor, QIcon, QBrush, QPainterPath,
                           QPolygonF)
from PySide6.QtCore import Qt, QPointF

# (id, etiqueta, dos_tonos). Solo el PINCEL los muestra (combo de "Relleno").
CUSTOM_BRUSH_PATTERNS = [
    ("checker_fill", "Tablero (relleno)",      True),
    ("checker_open", "Tablero (sin relleno)",  False),
    ("rombo_fill",   "Rombo (relleno)",        True),
    ("rombo_open",   "Rombo (sin relleno)",    False),
    ("brick",        "Ladrillo",               False),
    ("tejida",       "Tejida",                 True),
    ("tartan",       "Tartán",                 True),
    ("lunares",      "Lunares",                False),
    ("confeti",      "Confeti",                True),
    ("onda",         "Onda",                   False),
    ("zigzag",       "Zigzag",                 False),
    ("escamas",      "Escamas",                False),
]

CUSTOM_PATTERN_IDS = frozenset(pid for pid, _lbl, _tt in CUSTOM_BRUSH_PATTERNS)
_TWO_TONE = frozenset(pid for pid, _lbl, tt in CUSTOM_BRUSH_PATTERNS if tt)

_tile_cache = {}


def is_two_tone(pattern_id):
    return pattern_id in _TWO_TONE


def other_color(fg, primary, secondary):
    """Color de fondo para los patrones de DOS tonos: el opuesto al de frente.
    Si se pinta con el primario, el fondo es el secundario, y viceversa."""
    return primary if fg.rgba() == secondary.rgba() else secondary


def _key(pattern_id, fg, bg):
    return (pattern_id, fg.rgba(), bg.rgba() if bg is not None else None)


def make_tile(pattern_id, fg, bg=None):
    """Devuelve el QPixmap repetible del patrón en los colores dados (cacheado).
    'bg=None' => fondo transparente."""
    key = _key(pattern_id, fg, bg)
    cached = _tile_cache.get(key)
    if cached is not None:
        return cached

    if pattern_id.startswith("checker"):
        pm = _tile_checker(fg, bg)
    elif pattern_id.startswith("rombo"):
        pm = _tile_rombo(fg, bg)
    elif pattern_id == "brick":
        pm = _tile_brick(fg)
    elif pattern_id == "tejida":
        pm = _tile_tejida(fg, bg)
    elif pattern_id == "tartan":
        pm = _tile_tartan(fg, bg)
    elif pattern_id == "lunares":
        pm = _tile_lunares(fg)
    elif pattern_id == "confeti":
        pm = _tile_confeti(fg, bg)
    elif pattern_id == "onda":
        pm = _tile_onda(fg)
    elif pattern_id == "zigzag":
        pm = _tile_zigzag(fg)
    elif pattern_id == "escamas":
        pm = _tile_escamas(fg)
    else:
        # Identificador desconocido: azulejo sólido del color de frente.
        pm = QPixmap(8, 8)
        pm.fill(fg)

    _tile_cache[key] = pm
    return pm


def make_icon(pattern_id, fg, bg=None, size=64):
    """Icono de previsualización para el combo. Se dibuja a alta resolución y con
    un margen transparente (~12%, como los iconos nativos) para que, una vez
    escalado al tamaño del combo, su peso visual coincida con los demás."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    m = int(round(size * 0.12))
    inner = size - 2 * m
    p.fillRect(m, m, inner, inner, QBrush(make_tile(pattern_id, fg, bg)))
    p.end()
    return QIcon(pm)


# --------------------------------------------------------------------------
# Generadores de azulejo (todos sin costuras al repetir)
# --------------------------------------------------------------------------
def _tile_checker(fg, bg):
    """Tablero de ajedrez 2x2 celdas de 8 px. Con 'bg' es de dos tonos; sin él,
    cuadros de frente sobre transparente."""
    size, cell = 16, 8
    pm = QPixmap(size, size)
    pm.fill(bg if bg is not None else Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.fillRect(0, 0, cell, cell, fg)
    p.fillRect(cell, cell, cell, cell, fg)
    p.end()
    return pm


def _tile_brick(fg):
    """Muro de ladrillo en aparejo a soga: líneas de junta (mortero) del color de
    frente sobre fondo transparente, con desfase de media pieza por hilada."""
    size = 16
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    # Juntas horizontales (1 px) en y=0 e y=8.
    p.fillRect(0, 0, size, 1, fg)
    p.fillRect(0, 8, size, 1, fg)
    # Juntas verticales, desfasadas entre hiladas.
    p.fillRect(0, 0, 1, 8, fg)   # hilada superior: junta en x=0
    p.fillRect(8, 8, 1, 8, fg)   # hilada inferior: junta en x=8
    p.end()
    return pm


def _tile_zigzag(fg):
    """Galón (chevron) de líneas en zigzag del color de frente sobre transparente."""
    w, h = 16, 8
    pm = QPixmap(w, h)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = p.pen()
    pen.setColor(fg)
    pen.setWidthF(1.6)
    p.setPen(pen)
    path = QPainterPath()
    path.moveTo(0, h - 1)
    path.lineTo(w * 0.25, 1)
    path.lineTo(w * 0.5, h - 1)
    path.lineTo(w * 0.75, 1)
    path.lineTo(w, h - 1)
    p.drawPath(path)
    p.end()
    return pm


def _tile_rombo(fg, bg):
    """Rombo (diamante). Con 'bg' es un damero DIAGONAL de dos tonos; sin él, solo
    el contorno del rombo del color de frente sobre transparente. El diamante
    central + las cuatro esquinas encajan al repetir para formar la retícula."""
    size = 16
    pm = QPixmap(size, size)
    diamante = QPolygonF([QPointF(8, 0), QPointF(16, 8), QPointF(8, 16), QPointF(0, 8)])
    p = QPainter()
    if bg is not None:
        pm.fill(bg)
        p.begin(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(fg)
        p.drawPolygon(diamante)
    else:
        pm.fill(Qt.GlobalColor.transparent)
        p.begin(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = p.pen()
        pen.setColor(fg)
        pen.setWidthF(1.4)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPolygon(diamante)
    p.end()
    return pm


def _tile_tejida(fg, bg):
    """Cestería/tejido: cuadrantes alternos de frente/fondo con estrías (horizontales
    en los de frente, verticales en los de fondo) para dar sensación de trama."""
    size, h = 16, 8
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.fillRect(0, 0, h, h, fg)        # TL
    p.fillRect(h, h, h, h, fg)        # BR
    p.fillRect(h, 0, h, h, bg)        # TR
    p.fillRect(0, h, h, h, bg)        # BL
    estria = QColor(0, 0, 0, 45)
    for gy in (2, 5):                 # estrías horizontales en cuadrantes de frente
        p.fillRect(0, gy, h, 1, estria)
        p.fillRect(h, h + gy, h, 1, estria)
    for gx in (2, 5):                 # estrías verticales en cuadrantes de fondo
        p.fillRect(h + gx, 0, 1, h, estria)
        p.fillRect(gx, h, 1, h, estria)
    p.end()
    return pm


def _tile_tartan(fg, bg):
    """Tartán/cuadros escoceses: fondo del color secundario con bandas anchas
    semitransparentes del color de frente (los cruces se oscurecen al solaparse) y
    finas líneas de acento."""
    size = 24
    pm = QPixmap(size, size)
    pm.fill(bg)
    p = QPainter(pm)
    banda = QColor(fg)
    banda.setAlpha(110)
    p.fillRect(5, 0, 7, size, banda)   # banda vertical
    p.fillRect(0, 5, size, 7, banda)   # banda horizontal (cruce más oscuro)
    linea = QColor(fg)
    linea.setAlpha(210)
    p.fillRect(1, 0, 2, size, linea)   # acento vertical
    p.fillRect(0, 1, size, 2, linea)   # acento horizontal
    p.end()
    return pm


def _tile_lunares(fg):
    """Lunares/topos: puntos del color de frente en retícula al tresbolillo (el
    punto central más los cuartos de las esquinas, que encajan al repetir)."""
    size = 16
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(fg)
    r = 3.2
    p.drawEllipse(QPointF(8, 8), r, r)
    for cx, cy in ((0, 0), (16, 0), (0, 16), (16, 16)):
        p.drawEllipse(QPointF(cx, cy), r, r)
    p.end()
    return pm


def _tile_confeti(fg, bg):
    """Confeti: pequeños trozos dispersos alternando frente y fondo sobre
    transparente. Posiciones fijas (todas dentro del azulejo, sin tocar bordes)
    para que repita sin costuras."""
    size = 24
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    specks = [(3, 4), (9, 2), (16, 5), (19, 9), (5, 11), (12, 9),
              (18, 15), (2, 17), (10, 17), (15, 20), (20, 20), (7, 21)]
    for i, (x, y) in enumerate(specks):
        p.fillRect(x, y, 3, 3, fg if i % 2 == 0 else bg)
    p.end()
    return pm


def _tile_onda(fg):
    """Onda: línea sinusoidal del color de frente sobre transparente; el periodo
    coincide con el ancho del azulejo para que repita sin saltos."""
    w, h = 24, 12
    pm = QPixmap(w, h)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = p.pen()
    pen.setColor(fg)
    pen.setWidthF(1.6)
    p.setPen(pen)
    path = QPainterPath()
    cy, amp = h / 2.0, 3.0
    path.moveTo(0, cy)
    x = 0
    while x <= w:
        path.lineTo(x, cy + amp * math.sin(2 * math.pi * x / w))
        x += 2
    p.drawPath(path)
    p.end()
    return pm


def _tile_escamas(fg):
    """Escamas: círculos del color de frente solapados al tresbolillo (anillos),
    como escamas o cota de malla. Sobre transparente."""
    size = 16
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = p.pen()
    pen.setColor(fg)
    pen.setWidthF(1.4)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    r = 6.0
    p.drawEllipse(QPointF(8, 8), r, r)
    for cx, cy in ((0, 0), (16, 0), (0, 16), (16, 16)):
        p.drawEllipse(QPointF(cx, cy), r, r)
    p.end()
    return pm
