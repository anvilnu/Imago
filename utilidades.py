# utilidades.py
"""Utilidades compartidas de Imago (extraídas de main.py TAL CUAL, sin cambios
de comportamiento): creación de iconos temados, carga de imágenes de disco
aplicando la orientación EXIF (con fallback Pillow OPCIONAL para AVIF/HEIC/JXL)
y miniaturas de lienzo con tablero de transparencia. Viven en un módulo propio
para que los mixins de MainWindow (menu_archivo, opciones_herramientas...)
puedan importarlas sin crear un import circular con main.py."""
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap

import theme


def crear_icono(ruta):
    """Crea un QIcon con versión ATENUADA propia para el estado desactivado.
    La versión automática de Qt apenas se nota con iconos claros sobre fondo
    oscuro; esta deja el icono a un cuarto de opacidad: un fantasma tenue
    que se distingue a primera vista de los botones activos.
    En tema claro, la silueta se tinta a oscuro (theme.tintar_pixmap), salvo
    el logo de marca."""
    pixmap = QPixmap(ruta)
    if not pixmap.isNull() and theme.ICON_TINT and not theme.es_logo(ruta):
        pixmap = theme.tintar_pixmap(pixmap)
    icono = QIcon(pixmap) if not pixmap.isNull() else QIcon(ruta)
    if not pixmap.isNull():
        apagado = QPixmap(pixmap.size())
        apagado.fill(Qt.transparent)
        painter = QPainter(apagado)
        painter.setOpacity(0.25)
        painter.drawPixmap(0, 0, pixmap)
        painter.end()
        icono.addPixmap(apagado, QIcon.Disabled)
    return icono

def crear_icono_checkable(ruta):
    """Para acciones CHECKABLES (cuadrícula, reglas): el estado Off (sin
    marcar) se ve atenuado y el On (marcada) brillante. Así se distingue de
    un vistazo si está activa, sin depender solo del fondo azul del botón.
    En tema claro, la silueta se tinta a oscuro (salvo el logo de marca)."""
    icono = QIcon()
    pixmap = QPixmap(ruta)
    if not pixmap.isNull():
        if theme.ICON_TINT and not theme.es_logo(ruta):
            pixmap = theme.tintar_pixmap(pixmap)
        # Estado On: brillante (el original)
        icono.addPixmap(pixmap, QIcon.Normal, QIcon.On)
        # Estado Off: atenuado a un cuarto de opacidad
        apagado = QPixmap(pixmap.size())
        apagado.fill(Qt.transparent)
        painter = QPainter(apagado)
        painter.setOpacity(0.25)
        painter.drawPixmap(0, 0, pixmap)
        painter.end()
        icono.addPixmap(apagado, QIcon.Normal, QIcon.Off)
    return icono

def cargar_imagen_orientada(ruta):
    """Carga una imagen de disco APLICANDO la rotación EXIF que traiga
    (setAutoTransform): las fotos de móvil hechas en vertical se abren
    derechas. QImage(ruta) a secas ignora esa etiqueta y las tumbaría.
    Si Qt no conoce el formato (AVIF/HEIC/JXL), prueba el fallback de Pillow.
    Devuelve un QImage (nulo si el archivo no es una imagen válida)."""
    from PySide6.QtGui import QImageReader
    reader = QImageReader(ruta)
    reader.setAutoTransform(True)
    img = reader.read()
    if img.isNull():
        img = _cargar_via_pillow(ruta)
    return img


# Formatos que Qt no trae y cubre el fallback de Pillow, con su plugin
# OPCIONAL (import perezoso, como onnxruntime: sin él, Imago funciona igual).
_PILLOW_EXTRA = {"avif": "pillow-heif", "heic": "pillow-heif",
                 "heif": "pillow-heif", "jxl": "pillow-jxl-plugin"}


def _cargar_via_pillow(ruta):
    """Fallback para AVIF/HEIC/JXL: los abre Pillow con sus plugins opcionales
    (pillow-heif / pillow-jxl-plugin), aplicando la orientación EXIF. Devuelve
    un QImage nulo si no hay plugin o el archivo no es válido."""
    ext = os.path.splitext(ruta)[1].lower().lstrip(".")
    if ext not in _PILLOW_EXTRA:
        return QImage()
    try:
        if ext == "jxl":
            import pillow_jxl  # noqa: F401  (registra el plugin al importarse)
        else:
            import pillow_heif
            pillow_heif.register_heif_opener()
            if hasattr(pillow_heif, "register_avif_opener"):
                pillow_heif.register_avif_opener()
        from PIL import Image, ImageOps
        with Image.open(ruta) as im:
            im = ImageOps.exif_transpose(im)
            im = im.convert("RGBA")
            qimg = QImage(im.tobytes("raw", "RGBA"), im.width, im.height,
                          im.width * 4, QImage.Format_RGBA8888)
            return qimg.copy()   # desliga del buffer temporal
    except Exception:
        return QImage()

def png8_bytes(qimg, colores=256, dither=False, nivel=6, dpi=None):
    """PNG INDEXADO (paleta de hasta `colores`, alfa incluido) como bytes,
    cuantizado con Pillow: FASTOCTREE (admite RGBA, así el pixel-art con
    transparencia conserva su paleta exacta si cabe) y difuminado
    Floyd-Steinberg opcional para fotos. `nivel` es la compresión zlib (0-9)
    y `dpi` una tupla (x, y) que viaja en el pHYs. Devuelve None si Pillow no
    está o algo falla: el llamante cae al Indexed8 de Qt (el guardado clásico,
    que con >256 colores tramaba a una paleta fija con peor calidad)."""
    try:
        import io
        from PIL import Image
        img = qimg.convertToFormat(QImage.Format_RGBA8888)
        w, h, bpl = img.width(), img.height(), img.bytesPerLine()
        datos = bytes(img.constBits())
        if bpl != w * 4:   # quitar el relleno de fin de fila
            datos = b"".join(datos[y * bpl: y * bpl + w * 4] for y in range(h))
        im = Image.frombytes("RGBA", (w, h), datos)
        pal = im.quantize(colors=max(2, min(256, int(colores))),
                          method=Image.Quantize.FASTOCTREE,
                          dither=(Image.Dither.FLOYDSTEINBERG if dither
                                  else Image.Dither.NONE))
        salida = io.BytesIO()
        extras = {"optimize": True,
                  "compress_level": max(0, min(9, int(nivel)))}
        if dpi:
            extras["dpi"] = (float(dpi[0]), float(dpi[1]))
        pal.save(salida, "PNG", **extras)
        return salida.getvalue()
    except Exception:
        return None


def _canvas_thumb_pixmap(canvas, w, h):
    """Miniatura del lienzo que muestra la transparencia como tablero (igual
    que el lienzo), en vez de un fondo blanco. Funcion de modulo: la usan tanto
    la barra de pestanas como los tooltips."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QPixmap, QPainter, QColor
    img = canvas.render_flat_image(Qt.transparent)
    if img is None or img.isNull():
        return None
    scaled = QPixmap.fromImage(img).scaled(
        w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    out = QPixmap(scaled.size())
    out.fill(Qt.transparent)
    p = QPainter(out)
    tile = 4
    light = QColor(200, 200, 200)
    dark = QColor(160, 160, 160)
    yy = 0
    while yy < scaled.height():
        xx = 0
        while xx < scaled.width():
            p.fillRect(xx, yy, tile, tile,
                       light if ((xx // tile + yy // tile) % 2 == 0) else dark)
            xx += tile
        yy += tile
    p.drawPixmap(0, 0, scaled)
    p.end()
    return out
