import math
import numpy as np
from scipy import ndimage
from PySide6.QtGui import QImage

# Cache global para kernels de pincel
_KERNEL_CACHE = {}

# Aspect ratio para formas de pincel caligráficas
CALLIG_ASPECT = 3.0
SHAPES = ("round", "square", "diamond", "horizontal", "vertical", "fdiag", "bdiag")

def shape_field(nx, ny, shape):
    """Campo de forma normalizado: 0 en el centro, 1 en el borde de la punta."""
    a = CALLIG_ASPECT
    if shape == "square":
        return np.maximum(np.abs(nx), np.abs(ny))
    if shape == "diamond":
        return np.abs(nx) + np.abs(ny)
    if shape == "horizontal":
        return np.hypot(nx, ny * a)
    if shape == "vertical":
        return np.hypot(nx * a, ny)
    if shape == "fdiag":          # barra a lo largo de la diagonal "\"
        s = math.sqrt(2.0)
        u = (nx + ny) / s
        v = (nx - ny) / s
        return np.hypot(u, v * a)
    if shape == "bdiag":          # barra a lo largo de la diagonal "/"
        s = math.sqrt(2.0)
        u = (nx - ny) / s
        v = (nx + ny) / s
        return np.hypot(u, v * a)
    return np.hypot(nx, ny)       # round (por defecto)


def get_kernel(radius, hardness, shape, antialias=True):
    """Kernel [0..1] con forma de punta, dureza cúbica y borde suave (AA) o duro.
    Se cachea globalmente para evitar recálculos en todas las herramientas.
    Con antialias=False el borde es DENTADO (paso duro 0/1 en el perímetro)."""
    key = (round(radius, 2), int(hardness), shape, bool(antialias))
    cached = _KERNEL_CACHE.get(key)
    if cached is not None:
        return cached
    R = int(math.ceil(radius)) + 1
    size = 2 * R + 1
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    inv_r = 1.0 / max(radius, 1e-6)
    nx = (xx - R) * inv_r
    ny = (yy - R) * inv_r
    sf = shape_field(nx, ny, shape).astype(np.float32)
    h = hardness / 100.0
    if h >= 1.0:
        core = np.ones_like(sf)
    else:
        k = np.clip((sf - h) / (1.0 - h), 0.0, 1.0)
        # Usar curva de coseno en lugar de cúbica para retener más grosor visual
        core = np.where(sf <= h, 1.0, (np.cos(k * np.pi) + 1.0) / 2.0)
    if antialias:
        aa = np.clip((1.0 - sf) * radius + 0.5, 0.0, 1.0)  # cobertura suave del borde
    else:
        aa = (sf <= 1.0).astype(np.float32)                # borde duro (dentado)
    kernel = (core * aa).astype(np.float32)
    _KERNEL_CACHE[key] = kernel
    return kernel


def qimage_to_bgra(img):
    """QImage (Format_ARGB32) -> numpy array (H, W, 4) con BGRA uint8"""
    w, h = img.width(), img.height()
    bpl = img.bytesPerLine()
    buf = bytes(img.constBits())
    arr = np.frombuffer(buf, dtype=np.uint8).reshape(h, bpl)[:, :w * 4]
    return arr.reshape(h, w, 4)


def bgra_to_qimage(arr):
    """numpy array (H, W, 4) BGRA uint8 -> QImage"""
    h, w, _ = arr.shape
    arr = np.ascontiguousarray(arr, dtype=np.uint8)
    return QImage(arr.tobytes(), w, h, 4 * w, QImage.Format.Format_ARGB32).copy()


def qimage_to_u32(img):
    """QImage (Format_ARGB32) -> numpy array (H, W) con enteros uint32 0xAARRGGBB"""
    if img.format() != QImage.Format.Format_ARGB32:
        img = img.convertToFormat(QImage.Format.Format_ARGB32)
    W, H = img.width(), img.height()
    ptr = img.constBits()
    arr = np.frombuffer(ptr, dtype=np.uint32, count=W * H).reshape(H, W)
    return arr.copy()


def recompose_alpha(bg_bgra, coverage_mask, qcolor):
    """
    Combina la capa base (bg_bgra, en formato float32) con una máscara
    de cobertura y un color de dibujo (qcolor), y devuelve la imagen ARGB32
    en array uint8. (SourceOver vectorizado).
    """
    o = bg_bgra
    cov = coverage_mask
    c = qcolor

    B, G, Rr, A = c.blue(), c.green(), c.red(), c.alpha()
    oa = o[..., 3] / 255.0
    sa = cov * (A / 255.0)
    inv = 1.0 - sa
    out_a = sa + oa * inv

    res = np.empty_like(o)
    with np.errstate(divide='ignore', invalid='ignore'):
        for idx, cv in ((0, B), (1, G), (2, Rr)):
            premult = cv * sa + o[..., idx] * oa * inv
            res[..., idx] = np.where(out_a > 1e-6, premult / out_a, 0.0)
    res[..., 3] = out_a * 255.0
    out8 = np.clip(res + 0.5, 0, 255).astype(np.uint8)
    return out8


def path_from_mask(mask):
    """QPainterPath de selección (simplificado: solo perímetros) a partir de
    una máscara booleana (H, W). None si la máscara está vacía.

    Sustituye al viejo patrón `region += QRegion(tramo)` fila a fila +
    simplified(), que se disparaba en imágenes grandes. Las dos claves:
    1) Los tramos por fila se extraen VECTORIZADOS (un solo diff de numpy
       para toda la máscara, sin bucle por fila).
    2) Los tramos idénticos de filas consecutivas se FUSIONAN en rectángulos
       máximos antes de llamar a simplified(), que es lo realmente caro:
       su coste depende del nº de subtrazados (una selección de franjas en
       3000x2000 pasaba de 750.000 tramos / 35 s a 375 rects / 0,1 s)."""
    from PySide6.QtGui import QPainterPath
    H, W = mask.shape
    padded = np.zeros((H, W + 2), np.int8)
    padded[:, 1:-1] = mask
    d = np.diff(padded, axis=1)
    ys, x0s = np.nonzero(d == 1)      # inicios de tramo (por filas)
    _, x1s = np.nonzero(d == -1)      # finales (exclusivos), alineados 1:1
    if len(ys) == 0:
        return None
    # Orden por (x0, x1, y): un tramo continúa el rectángulo del anterior si
    # comparte columnas y su fila es exactamente la siguiente.
    order = np.lexsort((ys, x1s, x0s))
    ys, x0s, x1s = ys[order], x0s[order], x1s[order]
    new_rect = np.ones(len(ys), bool)
    new_rect[1:] = ((x0s[1:] != x0s[:-1]) | (x1s[1:] != x1s[:-1])
                    | (ys[1:] != ys[:-1] + 1))
    starts = np.flatnonzero(new_rect)
    ends = np.r_[starts[1:], len(ys)] - 1
    path = QPainterPath()
    for i, j in zip(starts, ends):
        path.addRect(float(x0s[i]), float(ys[i]),
                     float(x1s[i] - x0s[i]), float(ys[j] - ys[i] + 1))
    # simplified() fusiona los rectángulos que comparten borde y deja solo el
    # PERÍMETRO exterior limpio (sin él, las hormigas pintarían cada rect).
    return path.simplified()


def build_similar_mask(image, sel_mask, tol):
    """Máscara booleana (H, W) de los píxeles 'parecidos' a los colores de una
    selección: por canal (A, R, G, B), dentro del rango [mín−tol, máx+tol] de
    los valores presentes bajo sel_mask (misma semántica que el Crecer /
    Seleccionar parecido de Photoshop). Los píxeles ya seleccionados siempre
    cumplen el criterio (están dentro de su propio rango)."""
    arr = qimage_to_u32(image)
    result = np.ones(arr.shape, bool)
    for shift in (24, 16, 8, 0):
        ch = ((arr >> shift) & 0xFF).astype(np.int32)
        vals = ch[sel_mask]
        result &= (ch >= int(vals.min()) - tol) & (ch <= int(vals.max()) + tol)
    return result


def build_flood_fill_mask(image, start_pt, tol, contiguous):
    """
    Devuelve un array booleano (H, W) con los píxeles similares (flood fill).
    """
    sx, sy = start_pt.x(), start_pt.y()

    arr = qimage_to_u32(image)
    target = int(arr[sy, sx])
    
    a = ((arr >> 24) & 0xFF).astype(np.int32)
    r = ((arr >> 16) & 0xFF).astype(np.int32)
    g = ((arr >> 8) & 0xFF).astype(np.int32)
    b = (arr & 0xFF).astype(np.int32)
    
    ta = (target >> 24) & 0xFF
    tr = (target >> 16) & 0xFF
    tg = (target >> 8) & 0xFF
    tb = target & 0xFF
    
    # Distancia Chebyshev por canal (|Δ| <= tol en CADA canal), como el
    # borrador de color y Reemplazar color, y como GIMP/Photoshop. La antigua
    # SUMA de los 4 canales era ~4 veces más estricta que otros editores y
    # dejaba "puntitos" de ruido/antialiasing sin seleccionar.
    dist = np.maximum(np.maximum(np.abs(r - tr), np.abs(g - tg)),
                      np.maximum(np.abs(b - tb), np.abs(a - ta)))
    similar = dist <= tol

    if contiguous:
        labels, n = ndimage.label(similar)
        seed = labels[sy, sx]
        region = (labels == seed) if seed != 0 else np.zeros_like(similar)
    else:
        region = similar

    return region
