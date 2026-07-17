# models/layer_effects.py
# Efectos de capa NO DESTRUCTIVOS (sombra paralela, y en el futuro trazo,
# resplandor, etc.). Cada efecto es un objeto pequeño con parámetros pegado a la
# capa; el compositor lo recalcula a partir de los píxeles de ESA MISMA capa.
#
# REGLA DE ORO (rendimiento): un efecto SOLO puede leer su propia capa, nunca el
# compuesto inferior. Así su resultado se cachea por capa (ver
# Layer.render_with_effects) y solo se recalcula cuando esa capa cambia — no en
# cada repintado ni cuando se toca otra capa. En cuanto un efecto dependa del
# fondo (knockout, blend-if) reaparece la lentitud de las capas de ajuste.
#
# Los efectos "por debajo" (render_below) se pintan bajo los píxeles de la capa
# (sombra, resplandor exterior, parte externa del trazo). Los "por dentro"
# (render_above, futuro) se recortan al alfa de la capa (sombra interior, etc.).
import math
import sys
from PySide6.QtGui import QImage, QPainter, QColor, QLinearGradient
from PySide6.QtCore import QPoint, QRect


def _alpha_view(qimage):
    """Devuelve (arr HxWx4 uint8 RGBA, W, H) del QImage dado. Convierte a
    RGBA8888 (alfa recto); para leer el alfa la premultiplicación da igual.
    IMPORTANTE: se COPIA el array — sin la copia sería una vista sobre el QImage
    temporal `src`, que al liberarse dejaría el buffer apuntando a basura."""
    import numpy as np
    src = qimage.convertToFormat(QImage.Format_RGBA8888)
    W, H = src.width(), src.height()
    bpl = src.bytesPerLine()
    arr = np.frombuffer(src.constBits(), np.uint8).reshape(H, bpl)[:, :W * 4]
    return arr.reshape(H, W, 4).copy(), W, H


def _alpha_bbox_qimage(qimage):
    """Caja del alfa no nulo sin copiar los cuatro canales de todo el lienzo.

    ARGB32 es el formato habitual de las capas. Su orden de bytes depende del
    endian de la maquina; RGBA8888, en cambio, siempre deja el alfa en el cuarto
    byte. Los formatos menos comunes se convierten solo como respaldo.
    """
    import numpy as np

    W, H = qimage.width(), qimage.height()
    if W <= 0 or H <= 0:
        return None
    fmt = qimage.format()
    argb = (QImage.Format_ARGB32, QImage.Format_ARGB32_Premultiplied,
            QImage.Format_RGB32)
    rgba = (QImage.Format_RGBA8888, QImage.Format_RGBA8888_Premultiplied)
    if fmt in argb:
        src = qimage
        alpha_byte = 3 if sys.byteorder == "little" else 0
    elif fmt in rgba:
        src = qimage
        alpha_byte = 3
    else:
        src = qimage.convertToFormat(QImage.Format_RGBA8888)
        alpha_byte = 3
    raw = np.frombuffer(src.constBits(), np.uint8).reshape(
        H, src.bytesPerLine())[:, :W * 4]
    alpha = raw.reshape(H, W, 4)[:, :, alpha_byte]
    return _alpha_bbox(alpha)


def _alpha_bbox(alpha):
    """Rectángulo (x0, y0, x1, y1) que envuelve el alfa > 0, o None si está
    todo transparente. Acota el cómputo del efecto al contenido real."""
    import numpy as np
    rows = np.any(alpha > 0, axis=1)
    if not rows.any():
        return None
    cols = np.any(alpha > 0, axis=0)
    ys = np.where(rows)[0]
    xs = np.where(cols)[0]
    return int(xs[0]), int(ys[0]), int(xs[-1]) + 1, int(ys[-1]) + 1


def _silueta_desenfocada(arr, sigma, color, opacidad, dx=0, dy=0):
    """Silueta del alfa desenfocada (gaussiana) y teñida, acotada a la bbox del
    contenido + margen para las colas. Devuelve (QImage RGBA, px, py) o None. La
    comparten la Sombra (con desplazamiento dx/dy) y el Resplandor exterior
    (centrado, dx=dy=0)."""
    import numpy as np
    from scipy.ndimage import gaussian_filter

    alpha = arr[:, :, 3]
    bbox = _alpha_bbox(alpha)
    if bbox is None:
        return None
    x0, y0, x1, y1 = bbox

    sigma = max(0.1, float(sigma))
    pad = int(math.ceil(sigma * 3)) + 1
    sub = alpha[y0:y1, x0:x1].astype(np.float32)
    sub = np.pad(sub, pad, mode="constant")
    if sigma >= 0.5:
        sub = gaussian_filter(sub, sigma=sigma)

    a = np.clip(sub * (opacidad / 100.0), 0, 255).astype(np.uint8)
    H, W = a.shape
    col = QColor(color)
    out = np.empty((H, W, 4), np.uint8)
    out[:, :, 0] = col.red()
    out[:, :, 1] = col.green()
    out[:, :, 2] = col.blue()
    out[:, :, 3] = a
    out = np.ascontiguousarray(out)
    qimg = QImage(out.data, W, H, 4 * W, QImage.Format_RGBA8888).copy()
    return qimg, x0 - pad + dx, y0 - pad + dy


class Sombra:
    """Sombra paralela: silueta desenfocada del alfa de la capa, desplazada y
    teñida, pintada DEBAJO de los píxeles de la capa."""
    tipo = "sombra"

    def __init__(self, dx=6, dy=6, radio=8.0, color="#000000",
                 opacidad=75, activo=True):
        self.dx = int(dx)
        self.dy = int(dy)
        self.radio = float(radio)   # ~sigma del desenfoque gaussiano
        self.color = color
        self.opacidad = int(opacidad)
        self.activo = bool(activo)

    def fingerprint(self):
        """Tupla hashable de todos los parámetros: clave de invalidación de la
        caché de efectos de la capa."""
        return ("sombra", self.dx, self.dy, self.radio, self.color,
                self.opacidad, self.activo)

    def render_below(self, arr):
        """Contribución de la sombra: silueta del alfa desenfocada, teñida y
        DESPLAZADA (dx, dy). Debajo de la capa."""
        return _silueta_desenfocada(arr, self.radio, self.color, self.opacidad,
                                    self.dx, self.dy)

    # --- Serialización (para el .imago) ---
    def to_dict(self):
        return {"tipo": "sombra", "dx": self.dx, "dy": self.dy,
                "radio": self.radio, "color": self.color,
                "opacidad": self.opacidad, "activo": self.activo}


class Resplandor:
    """Resplandor exterior: silueta del alfa desenfocada y teñida alrededor del
    contenido (como la sombra, pero SIN desplazamiento). Debajo de la capa."""
    tipo = "resplandor"

    def __init__(self, radio=8.0, color="#ffffff", opacidad=75, activo=True):
        self.radio = float(radio)
        self.color = color
        self.opacidad = int(opacidad)
        self.activo = bool(activo)

    def fingerprint(self):
        return ("resplandor", self.radio, self.color, self.opacidad, self.activo)

    def render_below(self, arr):
        return _silueta_desenfocada(arr, self.radio, self.color, self.opacidad)

    def to_dict(self):
        return {"tipo": "resplandor", "radio": self.radio, "color": self.color,
                "opacidad": self.opacidad, "activo": self.activo}


class SuperposicionColor:
    """Superposición de color: tiñe el contenido con un color sólido recortado al
    alfa de la capa, ENCIMA de los píxeles (estrena la vía render_above). A
    opacidad 100 el interior opaco queda del color plano; en los bordes con
    antialias se mezcla con el contenido."""
    tipo = "superposicion"

    def __init__(self, color="#ff0000", opacidad=100, activo=True):
        self.color = color
        self.opacidad = int(opacidad)
        self.activo = bool(activo)

    def fingerprint(self):
        return ("superposicion", self.color, self.opacidad, self.activo)

    def render_above(self, arr):
        import numpy as np
        alpha = arr[:, :, 3]
        bbox = _alpha_bbox(alpha)
        if bbox is None:
            return None
        x0, y0, x1, y1 = bbox
        sub = alpha[y0:y1, x0:x1].astype(np.uint16)
        # Alfa del tinte = alfa del contenido * opacidad -> recortado a la forma.
        a = ((sub * self.opacidad) // 100).astype(np.uint8)
        H, W = a.shape
        col = QColor(self.color)
        out = np.empty((H, W, 4), np.uint8)
        out[:, :, 0] = col.red()
        out[:, :, 1] = col.green()
        out[:, :, 2] = col.blue()
        out[:, :, 3] = a
        out = np.ascontiguousarray(out)
        qimg = QImage(out.data, W, H, 4 * W, QImage.Format_RGBA8888).copy()
        return qimg, x0, y0

    def to_dict(self):
        return {"tipo": "superposicion", "color": self.color,
                "opacidad": self.opacidad, "activo": self.activo}


class Trazo:
    """Trazo/contorno EXTERIOR: engorda la silueta del alfa 'grosor' píxeles y la
    tiñe, pintándola DEBAJO de la capa. Como el contenido tapa el interior, solo
    se ve el anillo alrededor (y, en los huecos internos, su borde). El grosor se
    mide con la transformada de distancia, así el borde sale limpio y a la anchura
    exacta, con antialias en el filo."""
    tipo = "trazo"

    def __init__(self, grosor=3, color="#000000", opacidad=100, activo=True):
        self.grosor = int(grosor)
        self.color = color
        self.opacidad = int(opacidad)
        self.activo = bool(activo)

    def fingerprint(self):
        return ("trazo", self.grosor, self.color, self.opacidad, self.activo)

    # Umbral de grosor: por debajo se dilata en escala de grises (más liso pero
    # O(g²)); por encima, transformada de distancia (rápida) — en trazos gruesos
    # el ligero dentado del filo no se aprecia.
    _GD_MAX = 20

    def render_below(self, arr):
        import numpy as np

        alpha = arr[:, :, 3]
        bbox = _alpha_bbox(alpha)
        if bbox is None:
            return None
        x0, y0, x1, y1 = bbox

        g = max(1, int(self.grosor))
        pad = g + 2
        sub = alpha[y0:y1, x0:x1]
        sub = np.pad(sub, pad, mode="constant")
        if not (sub > 0).any():
            return None

        if g <= self._GD_MAX:
            # Engordar la silueta 'g' px con DILATACIÓN EN ESCALA DE GRISES (máximo
            # del alfa sobre un disco de radio g). A diferencia de binarizar + la
            # transformada de distancia, CONSERVA el antialias del borde (el filo
            # original se copia hacia fuera), así el contorno sale liso en curvas
            # y diagonales en vez de dentado.
            from scipy.ndimage import grey_dilation
            yy, xx = np.ogrid[-g:g + 1, -g:g + 1]
            footprint = (xx * xx + yy * yy) <= (g + 0.5) * (g + 0.5)
            dilated = grey_dilation(sub, footprint=footprint).astype(np.float32)
        else:
            # Trazos gruesos: distancia desde el borde al 50% (rápida), con 1 px
            # de antialias en el filo exterior.
            from scipy.ndimage import distance_transform_edt
            shape = sub >= 128
            dist = distance_transform_edt(~shape)
            cov = np.clip(g + 0.5 - dist, 0.0, 1.0)
            cov[shape] = 1.0
            dilated = cov * 255.0

        a = np.clip(dilated * (self.opacidad / 100.0), 0, 255).astype(np.uint8)
        H, W = a.shape
        col = QColor(self.color)
        out = np.empty((H, W, 4), np.uint8)
        out[:, :, 0] = col.red()
        out[:, :, 1] = col.green()
        out[:, :, 2] = col.blue()
        out[:, :, 3] = a
        out = np.ascontiguousarray(out)
        qimg = QImage(out.data, W, H, 4 * W, QImage.Format_RGBA8888).copy()
        return qimg, x0 - pad, y0 - pad

    def to_dict(self):
        return {"tipo": "trazo", "grosor": self.grosor, "color": self.color,
                "opacidad": self.opacidad, "activo": self.activo}


class SombraInterior:
    """Sombra interior: oscurece el borde INTERNO de la forma, desplazada (dx,dy)
    y desenfocada. Es la forma menos la forma desplazada+difuminada, recortada al
    alfa: sombra = forma · (1 − desplazada_difuminada). render_above."""
    tipo = "sombra_interior"

    def __init__(self, dx=6, dy=6, radio=8.0, color="#000000", opacidad=75, activo=True):
        self.dx = int(dx)
        self.dy = int(dy)
        self.radio = float(radio)
        self.color = color
        self.opacidad = int(opacidad)
        self.activo = bool(activo)

    def fingerprint(self):
        return ("sombra_interior", self.dx, self.dy, self.radio, self.color,
                self.opacidad, self.activo)

    def render_above(self, arr):
        import numpy as np
        from scipy.ndimage import gaussian_filter, shift as nd_shift

        alpha = arr[:, :, 3]
        bbox = _alpha_bbox(alpha)
        if bbox is None:
            return None
        x0, y0, x1, y1 = bbox

        sigma = max(0.1, self.radio)
        pad = int(math.ceil(sigma * 3)) + max(abs(self.dx), abs(self.dy)) + 1
        sub = alpha[y0:y1, x0:x1].astype(np.float32) / 255.0   # cobertura 0..1
        sub = np.pad(sub, pad, mode="constant")

        # Banda del borde interior: donde HAY forma pero la forma desplazada y
        # difuminada NO llega (filo opuesto al desplazamiento).
        shifted = nd_shift(sub, (self.dy, self.dx), order=1, mode="constant", cval=0.0)
        if sigma >= 0.5:
            shifted = gaussian_filter(shifted, sigma=sigma)
        inner = sub * np.clip(1.0 - shifted, 0.0, 1.0)

        a = np.clip(inner * (self.opacidad / 100.0) * 255.0, 0, 255).astype(np.uint8)
        H, W = a.shape
        col = QColor(self.color)
        out = np.empty((H, W, 4), np.uint8)
        out[:, :, 0] = col.red()
        out[:, :, 1] = col.green()
        out[:, :, 2] = col.blue()
        out[:, :, 3] = a
        out = np.ascontiguousarray(out)
        qimg = QImage(out.data, W, H, 4 * W, QImage.Format_RGBA8888).copy()
        return qimg, x0 - pad, y0 - pad

    def to_dict(self):
        return {"tipo": "sombra_interior", "dx": self.dx, "dy": self.dy,
                "radio": self.radio, "color": self.color,
                "opacidad": self.opacidad, "activo": self.activo}


class SuperposicionDegradado:
    """Superposición de degradado: pinta un degradado lineal (color1→color2 a un
    ángulo) recortado al alfa de la capa, ENCIMA del contenido. render_above."""
    tipo = "degradado"

    def __init__(self, color1="#000000", color2="#ffffff", angulo=0,
                 opacidad=100, activo=True):
        self.color1 = color1
        self.color2 = color2
        self.angulo = int(angulo)
        self.opacidad = int(opacidad)
        self.activo = bool(activo)

    def fingerprint(self):
        return ("degradado", self.color1, self.color2, self.angulo,
                self.opacidad, self.activo)

    def render_above(self, arr):
        import numpy as np
        alpha = arr[:, :, 3]
        bbox = _alpha_bbox(alpha)
        if bbox is None:
            return None
        x0, y0, x1, y1 = bbox
        w, h = x1 - x0, y1 - y0

        # Pintar el degradado lineal en toda la bbox (premultiplicado para pintar).
        grad_img = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
        grad_img.fill(0)
        p = QPainter(grad_img)
        rad = math.radians(self.angulo)
        dxx, dyy = math.cos(rad), math.sin(rad)
        cx, cy = w / 2.0, h / 2.0
        half = (abs(dxx) * w + abs(dyy) * h) / 2.0
        g = QLinearGradient(cx - dxx * half, cy - dyy * half,
                            cx + dxx * half, cy + dyy * half)
        g.setColorAt(0.0, QColor(self.color1))
        g.setColorAt(1.0, QColor(self.color2))
        p.fillRect(0, 0, w, h, g)
        p.end()

        # RGB del degradado, con alfa = alfa del contenido * opacidad (recorte).
        gi = grad_img.convertToFormat(QImage.Format_RGBA8888)
        buf = np.frombuffer(gi.constBits(), np.uint8).reshape(h, gi.bytesPerLine())[:, :w * 4]
        buf = buf.reshape(h, w, 4).copy()
        sub = alpha[y0:y1, x0:x1].astype(np.uint16)
        buf[:, :, 3] = ((sub * self.opacidad) // 100).astype(np.uint8)
        buf = np.ascontiguousarray(buf)
        qimg = QImage(buf.data, w, h, 4 * w, QImage.Format_RGBA8888).copy()
        return qimg, x0, y0

    def to_dict(self):
        return {"tipo": "degradado", "color1": self.color1, "color2": self.color2,
                "angulo": self.angulo, "opacidad": self.opacidad, "activo": self.activo}


class Bisel:
    """Bisel/relieve: da volumen al borde interno. Construye un mapa de ALTURA a
    partir de la distancia al borde (rampa de 'grosor' px) e ILUMINA su pendiente
    desde un ángulo: la cara que mira a la luz sale con el color de luz, la
    opuesta con el de sombra. Recortado al alfa. render_above."""
    tipo = "bisel"

    def __init__(self, grosor=5, angulo=135, opacidad=75,
                 color_luz="#ffffff", color_sombra="#000000", activo=True):
        self.grosor = int(grosor)
        self.angulo = int(angulo)
        self.opacidad = int(opacidad)
        self.color_luz = color_luz
        self.color_sombra = color_sombra
        self.activo = bool(activo)

    def fingerprint(self):
        return ("bisel", self.grosor, self.angulo, self.opacidad,
                self.color_luz, self.color_sombra, self.activo)

    def render_above(self, arr):
        import numpy as np
        from scipy.ndimage import distance_transform_edt

        alpha = arr[:, :, 3]
        bbox = _alpha_bbox(alpha)
        if bbox is None:
            return None
        x0, y0, x1, y1 = bbox

        g = max(1, int(self.grosor))
        pad = g + 2
        sub_a = alpha[y0:y1, x0:x1].astype(np.float32) / 255.0
        sub_a = np.pad(sub_a, pad, mode="constant")
        shape = sub_a > 0
        if not shape.any():
            return None

        # Altura: rampa de 0 en el borde hasta 'g' hacia dentro (luego meseta).
        dist = distance_transform_edt(shape)
        height = np.clip(dist, 0, g).astype(np.float32)
        gy, gx = np.gradient(height)
        rad = math.radians(self.angulo)
        lx, ly = math.cos(rad), -math.sin(rad)       # y de pantalla hacia abajo
        # La normal de la superficie de altura es (-gx, -gy): el filo que MIRA a
        # la luz (normal·luz > 0) se aclara; el opuesto se oscurece.
        shade = np.clip(-(gx * lx + gy * ly), -1.0, 1.0)

        a = np.clip(np.abs(shade) * (self.opacidad / 100.0) * 255.0, 0, 255)
        a = (a * sub_a).astype(np.uint8)             # recorte suave al alfa
        H, W = a.shape
        pos = shade > 0
        colL = QColor(self.color_luz)
        colS = QColor(self.color_sombra)
        out = np.empty((H, W, 4), np.uint8)
        out[:, :, 0] = np.where(pos, colL.red(), colS.red())
        out[:, :, 1] = np.where(pos, colL.green(), colS.green())
        out[:, :, 2] = np.where(pos, colL.blue(), colS.blue())
        out[:, :, 3] = a
        out = np.ascontiguousarray(out)
        qimg = QImage(out.data, W, H, 4 * W, QImage.Format_RGBA8888).copy()
        return qimg, x0 - pad, y0 - pad

    def to_dict(self):
        return {"tipo": "bisel", "grosor": self.grosor, "angulo": self.angulo,
                "opacidad": self.opacidad, "color_luz": self.color_luz,
                "color_sombra": self.color_sombra, "activo": self.activo}


class Satinado:
    """Satinado: brillo suave y ondulado dentro de la forma. Superpone la silueta
    desplazada en DOS sentidos opuestos (a un ángulo y distancia), toma su
    diferencia (interferencia), la difumina y la recorta al alfa. render_above."""
    tipo = "satinado"

    def __init__(self, angulo=45, distancia=12, radio=8.0,
                 color="#000000", opacidad=50, activo=True):
        self.angulo = int(angulo)
        self.distancia = int(distancia)
        self.radio = float(radio)
        self.color = color
        self.opacidad = int(opacidad)
        self.activo = bool(activo)

    def fingerprint(self):
        return ("satinado", self.angulo, self.distancia, self.radio,
                self.color, self.opacidad, self.activo)

    def render_above(self, arr):
        import numpy as np
        from scipy.ndimage import gaussian_filter, shift as nd_shift

        alpha = arr[:, :, 3]
        bbox = _alpha_bbox(alpha)
        if bbox is None:
            return None
        x0, y0, x1, y1 = bbox

        sigma = max(0.1, self.radio)
        rad = math.radians(self.angulo)
        dx = self.distancia * math.cos(rad)
        dy = -self.distancia * math.sin(rad)
        pad = int(math.ceil(sigma * 3)) + abs(int(self.distancia)) + 2
        sub = alpha[y0:y1, x0:x1].astype(np.float32) / 255.0
        sub = np.pad(sub, pad, mode="constant")

        s1 = nd_shift(sub, (dy, dx), order=1, mode="constant", cval=0.0)
        s2 = nd_shift(sub, (-dy, -dx), order=1, mode="constant", cval=0.0)
        diff = np.abs(s1 - s2)
        if sigma >= 0.5:
            diff = gaussian_filter(diff, sigma=sigma)
        inner = diff * sub                            # recorte a la forma

        a = np.clip(inner * (self.opacidad / 100.0) * 255.0, 0, 255).astype(np.uint8)
        H, W = a.shape
        col = QColor(self.color)
        out = np.empty((H, W, 4), np.uint8)
        out[:, :, 0] = col.red()
        out[:, :, 1] = col.green()
        out[:, :, 2] = col.blue()
        out[:, :, 3] = a
        out = np.ascontiguousarray(out)
        qimg = QImage(out.data, W, H, 4 * W, QImage.Format_RGBA8888).copy()
        return qimg, x0 - pad, y0 - pad

    def to_dict(self):
        return {"tipo": "satinado", "angulo": self.angulo, "distancia": self.distancia,
                "radio": self.radio, "color": self.color,
                "opacidad": self.opacidad, "activo": self.activo}


# Registro tipo -> clase (para reconstruir desde .imago).
TIPOS = {"sombra": Sombra, "trazo": Trazo, "resplandor": Resplandor,
         "superposicion": SuperposicionColor, "sombra_interior": SombraInterior,
         "degradado": SuperposicionDegradado, "bisel": Bisel, "satinado": Satinado}


def crear_efecto(datos):
    """Reconstruye un efecto desde su dict serializado (to_dict)."""
    cls = TIPOS.get(datos.get("tipo"))
    if cls is None:
        return None
    params = {k: v for k, v in datos.items() if k != "tipo"}
    return cls(**params)


def clonar_efectos(effects):
    """Copia PROFUNDA de una lista de efectos (vía to_dict/crear_efecto): la usa
    el overlay de edición para snapshots de deshacer/cancelar, sin que mutar el
    efecto en vivo afecte a la copia guardada."""
    out = []
    for e in effects:
        clon = crear_efecto(e.to_dict())
        if clon is not None:
            out.append(clon)
    return out


# Z-ORDER CANÓNICO de composición dentro de cada grupo (de abajo arriba), FIJO
# e independiente del orden de aplicación/lista, como en Photoshop: debajo de la
# capa, la sombra queda al fondo, el resplandor sobre ella y el trazo pegado a
# los píxeles (así el trazo NUNCA queda tapado por la sombra); encima, las
# superposiciones al fondo y satinado/sombra interior/bisel sobre ellas (una
# superposición al 100% no debe ocultar la sombra interior ni el bisel). Los
# tipos que no figuren (futuros/plugins) van al final del grupo en su orden de
# lista (el sort es estable).
_Z_DEBAJO = {"sombra": 0, "resplandor": 1, "trazo": 2}
_Z_ENCIMA = {"degradado": 0, "superposicion": 1, "satinado": 2,
             "sombra_interior": 3, "bisel": 4}


def render_effects_patch(base, effects):
    """Compone los efectos en un parche ajustado al contenido y sus halos.

    Devuelve ``(imagen, posicion)``. La imagen no ocupa el lienzo completo:
    contiene la caja de alfa de la capa y las contribuciones que sobresalen
    (sombra, resplandor y trazo), recortadas a los limites del documento. Esto
    permite cachear una capa dispersa sin reservar cuatro bytes por cada pixel
    transparente del lienzo.
    """
    activos = [e for e in effects if getattr(e, "activo", False)]
    if not activos:
        return base, QPoint(0, 0)

    bbox = _alpha_bbox_qimage(base)
    if bbox is None:
        return QImage(), QPoint(0, 0)
    x0, y0, x1, y1 = bbox
    recorte_base = base.copy(QRect(x0, y0, x1 - x0, y1 - y0))
    arr, _W, _H = _alpha_view(recorte_base)

    debajo = [e for e in activos if getattr(e, "render_below", None) is not None]
    encima = [e for e in activos if getattr(e, "render_above", None) is not None]

    contrib_debajo = []
    for e in sorted(debajo, key=lambda e: _Z_DEBAJO.get(getattr(e, "tipo", None),
                                                        len(_Z_DEBAJO))):
        contrib = e.render_below(arr)
        if contrib is not None:
            qimg, px, py = contrib
            contrib_debajo.append((qimg, x0 + px, y0 + py))

    contrib_encima = []
    for e in sorted(encima, key=lambda e: _Z_ENCIMA.get(getattr(e, "tipo", None),
                                                        len(_Z_ENCIMA))):
        contrib = e.render_above(arr)
        if contrib is not None:
            qimg, px, py = contrib
            contrib_encima.append((qimg, x0 + px, y0 + py))

    caja = QRect(x0, y0, x1 - x0, y1 - y0)
    for qimg, px, py in contrib_debajo + contrib_encima:
        caja = caja.united(QRect(px, py, qimg.width(), qimg.height()))
    caja = caja.intersected(QRect(0, 0, base.width(), base.height()))
    if caja.isEmpty():
        return QImage(), QPoint(0, 0)

    out = QImage(caja.size(), QImage.Format_ARGB32_Premultiplied)
    out.fill(0)
    p = QPainter(out)
    origen = caja.topLeft()

    # Efectos POR DEBAJO, del fondo hacia la capa (sombra → resplandor → trazo).
    for qimg, px, py in contrib_debajo:
        p.drawImage(QPoint(px, py) - origen, qimg)

    # Píxeles de la propia capa, encima de los efectos por debajo.
    p.drawImage(QPoint(x0, y0) - origen, recorte_base)

    # Efectos POR ENCIMA / recortados al contenido, de la capa hacia arriba
    # (degradado → superposición → satinado → sombra interior → bisel).
    for qimg, px, py in contrib_encima:
        p.drawImage(QPoint(px, py) - origen, qimg)

    p.end()
    return out, caja.topLeft()


def render_effects(base, effects):
    """Compone efectos y devuelve una QImage del mismo tamaño que ``base``.

    Es la API de compatibilidad para exportar, rasterizar y generar miniaturas.
    El compositor interactivo usa directamente :func:`render_effects_patch`
    para no materializar un lienzo transparente completo.
    """
    activos = [e for e in effects if getattr(e, "activo", False)]
    if not activos:
        return base
    patch, posicion = render_effects_patch(base, activos)
    out = QImage(base.size(), QImage.Format_ARGB32_Premultiplied)
    out.fill(0)
    if not patch.isNull():
        p = QPainter(out)
        p.drawImage(posicion, patch)
        p.end()
    return out
