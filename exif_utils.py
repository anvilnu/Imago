"""Conservación de metadatos EXIF al reescribir un JPEG.

Imago no recomprime la imagen para conservar los metadatos: el JPEG lo sigue
escribiendo el codificador de Qt (QImageWriter) y aquí sólo se INCRUSTA el
bloque EXIF del archivo original como un segmento APP1, byte a byte (sin volver
a comprimir los píxeles). Así se conservan fecha, cámara/objetivo, GPS, la
miniatura embebida, etc.

CLAVE: se inyecta el EXIF CRUDO original tal cual (parcheado IN SITU, sin
cambiar de tamaño), NO una re-serialización con Pillow. Pillow (Image.Exif.
tobytes) reescribe el TIFF de una forma que los lectores estrictos como exiv2
—el que usan KDE/Dolphin, Gwenview, etc.— RECHAZAN ("no parece imagen TIFF"),
además de descartar la miniatura. Parcheando los bytes originales se conserva un
TIFF válido idéntico al de la cámara.

Dos retoques in situ (mismo número de bytes, offsets intactos):
- Orientación (tag 0x0112 de IFD0) -> 1: cargar_imagen_orientada() ya aplicó la
  rotación a los píxeles al abrir; dejar la orientación original haría que los
  visores volvieran a girar la foto.
- Si no se quiere conservar el GPS, se neutraliza el puntero al IFD de GPS (tag
  0x8825 de IFD0) convirtiéndolo en un tag "Padding" inofensivo: los datos de
  ubicación quedan huérfanos (sin referencia) y ningún lector los muestra.

El EXIF se coloca justo tras el marcador SOI (antes del APP0/JFIF que escribe
Qt), que es como lo ponen las cámaras. Pillow sólo se usa para LEER el bloque
del original (import perezoso: si faltara, el guardado sigue, sólo que sin EXIF).
"""
from __future__ import annotations

import struct
from atomic_io import escribir_atomico


def leer_exif(ruta):
    """Devuelve los bytes EXIF crudos de una imagen de disco, o None si no los
    tiene o no se pueden leer. No decodifica los píxeles (Pillow es perezoso)."""
    try:
        from PIL import Image
        with Image.open(ruta) as im:
            return im.info.get("exif")
    except Exception:
        return None


def _patch_exif_raw(raw, quitar_gps=False):
    """Devuelve los bytes EXIF crudos ('Exif\\x00\\x00' + TIFF) con la Orientación
    forzada a 1 y, si quitar_gps, el puntero al IFD de GPS neutralizado. Todo IN
    SITU (mismo tamaño): conserva miniatura, maker notes y offsets intactos, y
    mantiene un TIFF válido para lectores estrictos. None si no reconoce la
    cabecera EXIF/TIFF."""
    try:
        if not raw or raw[:6] != b"Exif\x00\x00":
            return None
        buf = bytearray(raw)
        t = 6  # inicio del bloque TIFF dentro de buf
        orden = bytes(buf[t:t + 2])
        if orden == b"II":
            fmt = "<"
        elif orden == b"MM":
            fmt = ">"
        else:
            return None
        ifd_off = struct.unpack_from(fmt + "I", buf, t + 4)[0]
        p = t + ifd_off
        if p + 2 > len(buf):
            return None
        n = struct.unpack_from(fmt + "H", buf, p)[0]
        p += 2
        # Sólo IFD0: tanto Orientation (0x0112) como el puntero GPS (0x8825) viven ahí.
        for _ in range(n):
            if p + 12 > len(buf):
                break
            tag = struct.unpack_from(fmt + "H", buf, p)[0]
            if tag == 0x0112:  # Orientation = 1 (los píxeles ya vienen derechos)
                struct.pack_into(fmt + "H", buf, p + 8, 1)
            elif tag == 0x8825 and quitar_gps:
                # La entrada pasa a ser un tag "Padding" (0xEA1C, BYTE, valor 0):
                # deja de apuntar al IFD de GPS y ningún lector muestra ubicación.
                struct.pack_into(fmt + "H", buf, p, 0xEA1C)   # tag
                struct.pack_into(fmt + "H", buf, p + 2, 1)    # tipo = BYTE
                struct.pack_into(fmt + "I", buf, p + 4, 4)    # count = 4
                struct.pack_into(fmt + "I", buf, p + 8, 0)    # valor inline = 0
            p += 12
        return bytes(buf)
    except Exception:
        return None


def incrustar_exif_jpeg(ruta_jpeg, exif_bytes, incluir_gps=True):
    """Inserta el EXIF del original (orientación normalizada y, opcionalmente, sin
    GPS) en un JPEG ya escrito, como segmento APP1 tras el SOI, SIN recomprimir.
    Devuelve True si lo incrustó.

    No hace nada (devuelve False) si no hay EXIF, si no reconoce la cabecera, si
    el archivo no es un JPEG válido, si ya trae un APP1 'Exif' o si el bloque no
    cabe en un único segmento (límite de 64 KB del formato)."""
    if not exif_bytes:
        return False
    payload = _patch_exif_raw(exif_bytes, quitar_gps=not incluir_gps)
    if not payload:
        return False
    # APP1 = FFE1 | longitud(2 bytes, se incluye a sí misma) | payload('Exif\0\0'+TIFF)
    if len(payload) + 2 > 0xFFFF:  # no cabe en un solo segmento: no se incrusta
        return False
    app1 = b"\xff\xe1" + (len(payload) + 2).to_bytes(2, "big") + payload
    try:
        with open(ruta_jpeg, "rb") as f:
            datos = f.read()
    except OSError:
        return False
    if datos[:2] != b"\xff\xd8":          # no es un JPEG (falta el marcador SOI)
        return False
    if b"Exif\x00\x00" in datos[:4096]:   # ya trae EXIF: no duplicar el segmento
        return False
    # Justo tras el SOI, antes del APP0/JFIF (como lo colocan las cámaras).
    nuevo = datos[:2] + app1 + datos[2:]
    def _escribir(ruta_temporal):
        with open(ruta_temporal, "wb") as f:
            f.write(nuevo)
        return True

    return escribir_atomico(ruta_jpeg, _escribir)
