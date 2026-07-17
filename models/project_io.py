# models/project_io.py
# Guardado y carga de proyectos .imago — el formato nativo del editor.
#
# Un archivo .imago es un ZIP que contiene:
#   manifest.json       → dimensiones, metadatos y orden de las capas
#   layers/layer_0.png  → píxeles de cada capa en PNG (conserva transparencia)
#   layers/layer_1.png
#   ...
#
# Mismo enfoque que formatos reales como .ora (OpenRaster) o .pdn (Paint.NET).

import json
import zipfile
from atomic_io import ReemplazoAtomico
from i18n import t
from PySide6.QtCore import QByteArray, QBuffer, QIODevice, Qt
from PySide6.QtGui import QImage
from models.layer import Layer, LayerGroup, visible_efectiva

PROJECT_VERSION = 1


def _png_bytes(img):
    """Convierte un QImage a bytes PNG en memoria (sin archivos temporales)."""
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    buf.close()
    return ba.data()


def _ora_composite_op(blend):
    """Modo de fusión de Imago (QPainter.CompositionMode) -> composite-op de
    OpenRaster (los svg:* que entienden GIMP y Krita)."""
    from PySide6.QtGui import QPainter
    M = QPainter.CompositionMode
    tabla = {
        M.CompositionMode_SourceOver: "svg:src-over",
        M.CompositionMode_Multiply: "svg:multiply",
        M.CompositionMode_Screen: "svg:screen",
        M.CompositionMode_Overlay: "svg:overlay",
        M.CompositionMode_Darken: "svg:darken",
        M.CompositionMode_Lighten: "svg:lighten",
        M.CompositionMode_ColorDodge: "svg:color-dodge",
        M.CompositionMode_ColorBurn: "svg:color-burn",
        M.CompositionMode_HardLight: "svg:hard-light",
        M.CompositionMode_SoftLight: "svg:soft-light",
        M.CompositionMode_Difference: "svg:difference",
        M.CompositionMode_Exclusion: "svg:exclusion",
        M.CompositionMode_Plus: "svg:plus",
    }
    try:
        blend = QPainter.CompositionMode(blend) if blend is not None else M.CompositionMode_SourceOver
    except ValueError:
        return "svg:src-over"
    return tabla.get(blend, "svg:src-over")


def save_ora(canvas, file_path):
    """Exporta el lienzo a OpenRaster (.ora), el formato de capas que abren
    GIMP y Krita: un ZIP con 'mimetype' + stack.xml + un PNG por capa + la
    imagen aplanada (mergedimage.png) y una miniatura. Las máscaras se APLICAN
    al alfa del PNG (ORA no tiene máscaras) y el texto se rasteriza: es un
    export de interoperabilidad; el proyecto nativo con todo sigue siendo el
    .imago. Devuelve True si tuvo éxito."""
    from xml.sax.saxutils import quoteattr

    W, H = canvas.base_width, canvas.base_height
    dpi = int(round(float(getattr(canvas, "dpi", 96.0)) or 96.0))

    lineas = ['<?xml version="1.0" encoding="UTF-8"?>',
              f'<image version="0.0.3" w="{W}" h="{H}" xres="{dpi}" yres="{dpi}">',
              '  <stack>']
    entradas = []
    # stack.xml lista las capas de ARRIBA hacia abajo; canvas.layers va de
    # abajo (índice 0) hacia arriba -> se recorre invertido.
    total = len(canvas.layers)
    for pos, layer in enumerate(reversed(canvas.layers)):
        idx = total - 1 - pos
        ruta = f"data/layer{idx}.png"
        # render_image() entrega la capa lista para componer (máscara aplicada
        # al alfa y texto rasterizado). ✂️ ORA no tiene máscara de recorte: si
        # la capa está recortada, el recorte se HORNEA en su alfa al exportar.
        from models.layer import base_de_recorte, render_recortada
        base_clip = base_de_recorte(canvas.layers, idx)
        entradas.append((ruta, _png_bytes(
            render_recortada(layer, base_clip, con_efectos=False))))
        lineas.append(
            '    <layer name=%s src="%s" x="0" y="0" opacity="%.4f" '
            'visibility="%s" composite-op="%s"/>'
            % (quoteattr(layer.name or f"Capa {idx + 1}"), ruta,
               max(0, min(100, int(layer.opacity))) / 100.0,
               # ORA exporta una pila PLANA: se hornea la visibilidad EFECTIVA
               # (capa Y sus grupos), que es lo que el usuario ve.
               "visible" if visible_efectiva(layer) else "hidden",
               _ora_composite_op(getattr(layer, "blend_mode", None))))
    lineas += ['  </stack>', '</image>', '']

    plana = canvas.render_flat_image(background=Qt.transparent)
    if plana.width() > 256 or plana.height() > 256:
        thumb = plana.scaled(256, 256, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
    else:
        thumb = plana

    reemplazo = None
    try:
        reemplazo = ReemplazoAtomico(file_path)
        with zipfile.ZipFile(reemplazo.ruta, "w", zipfile.ZIP_DEFLATED) as zf:
            # La espec exige 'mimetype' como PRIMERA entrada y SIN comprimir.
            zf.writestr("mimetype", "image/openraster",
                        compress_type=zipfile.ZIP_STORED)
            zf.writestr("stack.xml", "\n".join(lineas))
            for ruta, datos in entradas:
                zf.writestr(ruta, datos)
            zf.writestr("mergedimage.png", _png_bytes(plana))
            zf.writestr("Thumbnails/thumbnail.png", _png_bytes(thumb))
        return reemplazo.confirmar()
    except OSError:
        return False
    finally:
        if reemplazo is not None:
            reemplazo.cancelar()


def save_project(canvas, file_path):
    """Guarda el lienzo completo (todas las capas y sus propiedades) en un .imago.
    Devuelve True si tuvo éxito."""
    manifest = {
        "version": PROJECT_VERSION,
        "width": canvas.base_width,
        "height": canvas.base_height,
        "active_layer_index": canvas.active_layer_index,
        "layer_counter": getattr(canvas, "layer_counter", len(canvas.layers)),
        "guides": [dict(g) for g in getattr(canvas, "guides", [])],
        "layers": []
    }

    # 📁 Grupos de capas (carpetas): se serializan con un id por grupo y cada
    # capa referencia el suyo. Un .imago antiguo simplemente no trae "groups"
    # (y un Imago antiguo que abra este archivo ignora las claves y carga las
    # capas planas: retrocompatible en ambos sentidos).
    from models.layer import grupos_del_lienzo
    grupos = grupos_del_lienzo(canvas.layers)
    gid = {id(g): i for i, g in enumerate(grupos)}
    if grupos:
        manifest["groups"] = [{
            "id": gid[id(g)],
            "name": g.name,
            "visible": g.visible,
            "expanded": g.expanded,
            "parent": gid[id(g.parent)] if g.parent is not None else None,
        } for g in grupos]

    reemplazo = None
    try:
        reemplazo = ReemplazoAtomico(file_path)
        with zipfile.ZipFile(reemplazo.ruta, "w", zipfile.ZIP_DEFLATED) as zf:
            for i, layer in enumerate(canvas.layers):
                layer_file = f"layers/layer_{i}.png"
                blend = getattr(layer, "blend_mode", 0)
                blend_val = blend.value if hasattr(blend, "value") else int(blend)
                
                entry = {
                    "name": layer.name,
                    "visible": layer.visible,
                    "opacity": layer.opacity,
                    "blend_mode": blend_val,
                    "alpha_locked": getattr(layer, "alpha_locked", False),
                    "file": layer_file
                }
                # 🔒✂️ Bloqueos y máscara de recorte: solo si están activos
                # (manifests compactos y retrocompatibles: el cargador usa
                # get con False por defecto).
                if getattr(layer, "pixels_locked", False):
                    entry["pixels_locked"] = True
                if getattr(layer, "position_locked", False):
                    entry["position_locked"] = True
                if getattr(layer, "clipped", False):
                    entry["clipped"] = True
                
                # Duración del fotograma (capas importadas de un GIF/WebP
                # animado): se conserva para poder reexportar la animación.
                if getattr(layer, "frame_delay", None):
                    entry["frame_delay"] = int(layer.frame_delay)

                if getattr(layer, "is_text", False):
                    entry["is_text"] = True
                    entry["text_html"] = layer.text_html
                    entry["text_origin_x"] = layer.text_origin.x()
                    entry["text_origin_y"] = layer.text_origin.y()
                    if getattr(layer, "text_angle", 0):
                        entry["text_angle"] = float(layer.text_angle)
                    if getattr(layer, "text_vertical", False):
                        entry["text_vertical"] = True
                    if getattr(layer, "text_spacing", 0):
                        entry["text_spacing"] = int(layer.text_spacing)
                    if getattr(layer, "text_box_width", 0):
                        entry["text_box_width"] = int(layer.text_box_width)

                # ✨ Efectos de capa NO destructivos (sombra...): como JSON en el
                # manifest. Los píxeles de la capa se guardan SIN el efecto; se
                # re-aplica al abrir (ver models/layer_effects).
                if getattr(layer, "effects", None):
                    entry["effects"] = [e.to_dict() for e in layer.effects]

                # 📁 Grupo al que pertenece la capa (id del manifest).
                if getattr(layer, "group", None) is not None:
                    entry["group"] = gid[id(layer.group)]

                # Convertir el QImage a bytes PNG en memoria (sin archivos temporales).
                # En las capas de texto, layer.image es un dummy 1x1: se guarda el
                # RENDER real, para que el PNG sirva de respaldo si el proyecto lo
                # abre algo que no entienda "is_text" (o una versión antigua).
                img_out = (layer.render_image() if getattr(layer, "is_text", False)
                           else layer.image)
                ba = QByteArray()
                buf = QBuffer(ba)
                buf.open(QIODevice.OpenModeFlag.WriteOnly)
                img_out.save(buf, "PNG")
                buf.close()
                zf.writestr(layer_file, ba.data())

                # 🎭 Máscara de capa (si la tiene): PNG en escala de grises aparte.
                if getattr(layer, "mask", None) is not None:
                    mask_file = f"layers/mask_{i}.png"
                    entry["mask"] = mask_file
                    mba = QByteArray()
                    mbuf = QBuffer(mba)
                    mbuf.open(QIODevice.OpenModeFlag.WriteOnly)
                    layer.mask.save(mbuf, "PNG")
                    mbuf.close()
                    zf.writestr(mask_file, mba.data())

                manifest["layers"].append(entry)

            zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        return reemplazo.confirmar()
    except (OSError, zipfile.BadZipFile):
        return False
    finally:
        if reemplazo is not None:
            reemplazo.cancelar()


def load_project(file_path):
    """Carga un proyecto .imago y devuelve un diccionario con todos los datos
    listos para aplicar al lienzo con canvas.apply_project_data().
    Lanza ValueError si el archivo está corrupto o no es un proyecto válido."""
    try:
        with zipfile.ZipFile(file_path, "r") as zf:
            manifest = json.loads(zf.read("manifest.json").decode("utf-8"))

            width = manifest["width"]
            height = manifest["height"]

            # 📁 Grupos (carpetas): reconstruirlos primero (dos pasadas: crear
            # y luego enlazar padres, que pueden aparecer en cualquier orden).
            grupos = {}
            for g in manifest.get("groups", []):
                grupo = LayerGroup(str(g.get("name", "Grupo")))
                grupo.visible = bool(g.get("visible", True))
                grupo.expanded = bool(g.get("expanded", True))
                grupos[g["id"]] = grupo
            for g in manifest.get("groups", []):
                pid = g.get("parent")
                if pid is not None and pid in grupos and pid != g["id"]:
                    grupos[g["id"]].parent = grupos[pid]

            layers = []
            for meta in manifest["layers"]:
                img = QImage.fromData(zf.read(meta["file"]), "PNG")
                if img.isNull():
                    raise ValueError(t("err.corrupt_layer", file=meta['file']))
                if meta.get("is_text", False):
                    from models.layer import TextLayer
                    from PySide6.QtCore import QPointF
                    layer = TextLayer(width, height, name=meta["name"])
                    layer.set_text(
                        meta.get("text_html", ""),
                        QPointF(meta.get("text_origin_x", 0.0), meta.get("text_origin_y", 0.0)),
                        angle=meta.get("text_angle", 0.0),
                        vertical=meta.get("text_vertical", False),
                        spacing=meta.get("text_spacing", 0),
                        box_width=meta.get("text_box_width", 0)
                    )
                else:
                    layer = Layer(width, height, name=meta["name"])
                    layer.image = img.convertToFormat(QImage.Format_ARGB32)
                layer.visible = bool(meta.get("visible", True))
                layer.opacity = int(meta.get("opacity", 100))
                if meta.get("frame_delay"):
                    layer.frame_delay = int(meta["frame_delay"])

                from PySide6.QtGui import QPainter
                # En PySide6 6.x los enums de Qt ya no son int: usar .value (no
                # int(enum), que lanza TypeError). El default se evalúa SIEMPRE
                # aunque 'blend_mode' esté en meta, así que también debe ser seguro.
                _src_over = QPainter.CompositionMode.CompositionMode_SourceOver
                _default_blend = _src_over.value if hasattr(_src_over, "value") else int(_src_over)
                layer.blend_mode = QPainter.CompositionMode(int(meta.get("blend_mode", _default_blend)))
                layer.alpha_locked = bool(meta.get("alpha_locked", False))
                layer.pixels_locked = bool(meta.get("pixels_locked", False))
                layer.position_locked = bool(meta.get("position_locked", False))
                layer.clipped = bool(meta.get("clipped", False))

                # 🎭 Máscara de capa (si el manifiesto la referencia).
                mask_file = meta.get("mask")
                if mask_file:
                    mimg = QImage.fromData(zf.read(mask_file), "PNG")
                    if not mimg.isNull():
                        layer.mask = mimg.convertToFormat(QImage.Format_Grayscale8)

                # ✨ Efectos de capa (reconstruidos desde el manifest). Los tipos
                # desconocidos de un .imago más nuevo se ignoran sin romper.
                efectos = meta.get("effects")
                if efectos:
                    from models.layer_effects import crear_efecto
                    layer.effects = [e for e in (crear_efecto(d) for d in efectos)
                                     if e is not None]

                # 📁 Grupo de la capa (si el manifest lo trae y existe).
                g_id = meta.get("group")
                if g_id is not None and g_id in grupos:
                    layer.group = grupos[g_id]

                layers.append(layer)

            if not layers:
                raise ValueError(t("err.no_layers"))

    except (zipfile.BadZipFile, KeyError, json.JSONDecodeError) as e:
        raise ValueError(t("err.invalid_project", e=e))

    return {
        "width": width,
        "height": height,
        "layers": layers,
        "active_layer_index": manifest.get("active_layer_index", 0),
        "layer_counter": manifest.get("layer_counter", len(layers)),
        "guides": [g for g in manifest.get("guides", [])
                   if isinstance(g, dict) and g.get("orient") in ("h", "v")],
    }
