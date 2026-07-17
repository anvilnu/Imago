# models/anim_io.py
# Exportación de animaciones GIF/WebP: las CAPAS visibles del lienzo son los
# fotogramas (de abajo hacia arriba). Escribe con Pillow (import PEREZOSO,
# como en exif_utils: Qt no trae escritor animado); si falta, se avisa y no
# se rompe nada.

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter
from atomic_io import escribir_atomico


def _qimage_a_pil(img):
    """QImage -> PIL.Image (RGBA), pasando por los bytes RGBA8888 crudos."""
    from PIL import Image
    img = img.convertToFormat(QImage.Format_RGBA8888)
    W, H = img.width(), img.height()
    bpl = img.bytesPerLine()
    datos = bytes(img.constBits())
    # .copy() desliga la PIL.Image del buffer temporal de Qt.
    return Image.frombuffer("RGBA", (W, H), datos, "raw", "RGBA", bpl, 1).copy()


def frames_de_capas(canvas):
    """Fotogramas de la animación: una imagen RGBA por capa VISIBLE, de abajo
    hacia arriba, cada una compuesta SUELTA (con su opacidad y máscara) sobre
    transparente a tamaño de lienzo. Devuelve (frames, delays), con el
    frame_delay de cada capa (o None si no lo trae)."""
    frames, delays = [], []
    for layer in canvas.layers:
        if not layer.visible:
            continue
        base = QImage(canvas.base_width, canvas.base_height,
                      QImage.Format_ARGB32_Premultiplied)
        base.fill(Qt.transparent)
        p = QPainter(base)
        p.setOpacity(max(0, min(100, int(layer.opacity))) / 100.0)
        p.drawImage(0, 0, layer.render_image())
        p.end()
        frames.append(base)
        delays.append(getattr(layer, "frame_delay", None))
    return frames, delays


def save_animation(canvas, file_path, duration_ms, loop=True, use_original=False):
    """Exporta las capas visibles como GIF o WebP animado (según la extensión
    de file_path). duration_ms vale para todos los fotogramas, salvo que
    use_original sea True y las capas traigan frame_delay (importadas de un
    animado). Devuelve (ok, error), con error None, "pillow" (falta Pillow),
    "frames" (menos de 2 fotogramas) o "write" (fallo al escribir)."""
    try:
        from PIL import Image
    except ImportError:
        return False, "pillow"

    frames, delays = frames_de_capas(canvas)
    if len(frames) < 2:
        return False, "frames"

    if use_original and any(delays):
        dur = [int(d) if d else int(duration_ms) for d in delays]
    else:
        dur = int(duration_ms)

    es_gif = file_path.lower().endswith(".gif")
    pils = []
    for f in frames:
        pil = _qimage_a_pil(f)
        if es_gif:
            # GIF no tiene alfa parcial: se compone sobre blanco (la
            # cuantización a paleta la hace Pillow al guardar).
            fondo = Image.new("RGB", pil.size, (255, 255, 255))
            fondo.paste(pil, mask=pil.getchannel("A"))
            pil = fondo
        pils.append(pil)

    extra = {}
    if loop:
        extra["loop"] = 0            # 0 = bucle infinito (GIF y WebP)
    elif not es_gif:
        extra["loop"] = 1            # WebP: una sola pasada
    # GIF sin 'loop': sin extensión de bucle = se reproduce una vez.
    def _escribir(ruta_temporal):
        pils[0].save(ruta_temporal, save_all=True, append_images=pils[1:],
                     duration=dur, optimize=es_gif, **extra)
        return True

    try:
        if escribir_atomico(file_path, _escribir):
            return True, None
        return False, "write"
    except (OSError, ValueError):
        return False, "write"
