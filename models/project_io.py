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
import math
import struct
import zipfile
from atomic_io import ReemplazoAtomico
from i18n import t
from PySide6.QtCore import QByteArray, QBuffer, QIODevice, Qt
from PySide6.QtGui import QImage
from models.layer import Layer, LayerGroup, visible_efectiva

PROJECT_VERSION = 1
MAX_CANVAS_DIMENSION = 32_768
MAX_CANVAS_PIXELS = 100_000_000
MAX_LAYERS = 512
MAX_GROUPS = 512
MAX_GUIDES = 10_000
MAX_MANIFEST_BYTES = 8 * 1024 * 1024
MAX_ENTRY_BYTES = 512 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED_BYTES = 8 * 1024 * 1024 * 1024
MAX_DOCUMENT_IMAGE_BYTES = 2 * 1024 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 1 + 2 * MAX_LAYERS


class ErrorCargaProyecto(ValueError):
    """Proyecto .imago ilegible, incompatible o que excede límites seguros."""


def _fallo_proyecto(clave, **kwargs):
    raise ErrorCargaProyecto(t(clave, **kwargs))


def _es_entero(valor):
    return isinstance(valor, int) and not isinstance(valor, bool)


def _validar_entero(valor, campo, minimo=None, maximo=None):
    if (not _es_entero(valor)
            or (minimo is not None and valor < minimo)
            or (maximo is not None and valor > maximo)):
        _fallo_proyecto("err.project.invalid_field", field=campo)
    return valor


def _validar_numero(valor, campo, minimo=None, maximo=None):
    if (isinstance(valor, bool) or not isinstance(valor, (int, float))
            or not math.isfinite(float(valor))
            or (minimo is not None and valor < minimo)
            or (maximo is not None and valor > maximo)):
        _fallo_proyecto("err.project.invalid_field", field=campo)
    return valor


def _validar_bool_opcional(datos, clave, campo):
    if clave in datos and not isinstance(datos[clave], bool):
        _fallo_proyecto("err.project.invalid_field", field=campo)


def _validar_texto(valor, campo, maximo=1024):
    if not isinstance(valor, str) or len(valor) > maximo:
        _fallo_proyecto("err.project.invalid_field", field=campo)
    return valor


def _validar_claves(datos, permitidas, campo):
    desconocidas = set(datos) - set(permitidas)
    if desconocidas:
        clave = sorted(str(k) for k in desconocidas)[0]
        _fallo_proyecto("err.project.unknown_field", field=f"{campo}.{clave}")


def _validar_ruta_zip(valor, campo):
    _validar_texto(valor, campo, 512)
    partes = valor.split("/")
    if (not valor or valor.startswith("/") or "\\" in valor
            or any(p in ("", ".", "..") for p in partes)
            or not valor.lower().endswith(".png")):
        _fallo_proyecto("err.project.invalid_field", field=campo)
    return valor


def _valor_enum(valor):
    return valor.value if hasattr(valor, "value") else int(valor)


def _modos_fusion_validos():
    from PySide6.QtGui import QPainter
    m = QPainter.CompositionMode
    return {_valor_enum(v) for v in (
        m.CompositionMode_SourceOver, m.CompositionMode_Darken,
        m.CompositionMode_Multiply, m.CompositionMode_ColorBurn,
        m.CompositionMode_Lighten, m.CompositionMode_Screen,
        m.CompositionMode_ColorDodge, m.CompositionMode_Plus,
        m.CompositionMode_Overlay, m.CompositionMode_SoftLight,
        m.CompositionMode_HardLight, m.CompositionMode_Difference,
        m.CompositionMode_Exclusion,
    )}


def _leer_entrada(zf, nombre, limite=MAX_ENTRY_BYTES):
    try:
        info = zf.getinfo(nombre)
    except KeyError:
        _fallo_proyecto("err.project.missing_entry", file=nombre)
    if info.is_dir() or info.file_size > limite:
        _fallo_proyecto("err.project.entry_limit", file=nombre)
    with zf.open(info, "r") as entrada:
        datos = entrada.read(limite + 1)
    if len(datos) > limite or len(datos) != info.file_size:
        _fallo_proyecto("err.project.entry_limit", file=nombre)
    return datos


def _dimensiones_png(datos, nombre):
    firma = b"\x89PNG\r\n\x1a\n"
    if (len(datos) < 24 or datos[:8] != firma
            or datos[12:16] != b"IHDR"):
        _fallo_proyecto("err.project.corrupt_png", file=nombre)
    ancho, alto = struct.unpack(">II", datos[16:24])
    return ancho, alto


def _validar_png(datos, nombre, width, height):
    if _dimensiones_png(datos, nombre) != (width, height):
        _fallo_proyecto("err.project.png_dimensions", file=nombre,
                        width=width, height=height)


def _cargar_json_manifest(datos):
    def _constante_invalida(valor):
        raise ValueError(valor)

    return json.loads(datos.decode("utf-8"), parse_constant=_constante_invalida)


def _validar_manifest(manifest):
    if not isinstance(manifest, dict):
        _fallo_proyecto("err.project.invalid_field", field="manifest")
    _validar_claves(manifest, {
        "version", "width", "height", "active_layer_index",
        "layer_counter", "guides", "layers", "groups", "dpi",
    }, "manifest")

    version = manifest.get("version")
    if not _es_entero(version):
        _fallo_proyecto("err.project.invalid_version")
    if version > PROJECT_VERSION:
        _fallo_proyecto("err.project.future_version", version=version,
                        supported=PROJECT_VERSION)
    if version != PROJECT_VERSION:
        _fallo_proyecto("err.project.unsupported_version", version=version)

    width = _validar_entero(manifest.get("width"), "width", 1,
                            MAX_CANVAS_DIMENSION)
    height = _validar_entero(manifest.get("height"), "height", 1,
                             MAX_CANVAS_DIMENSION)
    area = width * height
    if area > MAX_CANVAS_PIXELS:
        _fallo_proyecto("err.project.canvas_limit")
    dpi = float(_validar_numero(manifest.get("dpi", 96.0), "dpi", 1.0))

    metas = manifest.get("layers")
    if not isinstance(metas, list) or not 1 <= len(metas) <= MAX_LAYERS:
        _fallo_proyecto("err.project.layers_limit", max=MAX_LAYERS)
    active = _validar_entero(manifest.get("active_layer_index"),
                             "active_layer_index", 0, len(metas) - 1)
    counter = _validar_entero(manifest.get("layer_counter", len(metas)),
                              "layer_counter", 0)

    groups_meta = manifest.get("groups", [])
    if not isinstance(groups_meta, list) or len(groups_meta) > MAX_GROUPS:
        _fallo_proyecto("err.project.groups_limit", max=MAX_GROUPS)
    group_ids = set()
    parents = {}
    group_fields = {"id", "name", "visible", "expanded", "parent"}
    for pos, grupo in enumerate(groups_meta):
        campo = f"groups[{pos}]"
        if not isinstance(grupo, dict):
            _fallo_proyecto("err.project.invalid_field", field=campo)
        _validar_claves(grupo, group_fields, campo)
        gid = _validar_entero(grupo.get("id"), f"{campo}.id", 0)
        if gid in group_ids:
            _fallo_proyecto("err.project.invalid_field", field=f"{campo}.id")
        group_ids.add(gid)
        _validar_texto(grupo.get("name", "Grupo"), f"{campo}.name")
        _validar_bool_opcional(grupo, "visible", f"{campo}.visible")
        _validar_bool_opcional(grupo, "expanded", f"{campo}.expanded")
        parent = grupo.get("parent")
        if parent is not None:
            parent = _validar_entero(parent, f"{campo}.parent", 0)
        parents[gid] = parent
    for gid, parent in parents.items():
        if parent is not None and parent not in group_ids:
            _fallo_proyecto("err.project.invalid_field", field="groups.parent")
        vistos = set()
        actual = gid
        while actual is not None:
            if actual in vistos:
                _fallo_proyecto("err.project.group_cycle")
            vistos.add(actual)
            actual = parents.get(actual)

    layer_fields = {
        "name", "visible", "opacity", "blend_mode", "alpha_locked",
        "pixels_locked", "position_locked", "clipped", "file", "mask",
        "frame_delay", "is_text", "text_html", "text_origin_x",
        "text_origin_y", "text_angle", "text_vertical", "text_spacing",
        "text_box_width", "effects", "group",
    }
    rutas = set()
    mask_count = 0
    group_ids_referenciados = set()
    modos = _modos_fusion_validos()
    for pos, meta in enumerate(metas):
        campo = f"layers[{pos}]"
        if not isinstance(meta, dict):
            _fallo_proyecto("err.project.invalid_field", field=campo)
        _validar_claves(meta, layer_fields, campo)
        _validar_texto(meta.get("name"), f"{campo}.name")
        ruta = _validar_ruta_zip(meta.get("file"), f"{campo}.file")
        if ruta in rutas:
            _fallo_proyecto("err.project.invalid_field", field=f"{campo}.file")
        rutas.add(ruta)
        _validar_bool_opcional(meta, "visible", f"{campo}.visible")
        _validar_bool_opcional(meta, "alpha_locked", f"{campo}.alpha_locked")
        _validar_bool_opcional(meta, "pixels_locked", f"{campo}.pixels_locked")
        _validar_bool_opcional(meta, "position_locked", f"{campo}.position_locked")
        _validar_bool_opcional(meta, "clipped", f"{campo}.clipped")
        _validar_bool_opcional(meta, "is_text", f"{campo}.is_text")
        _validar_bool_opcional(meta, "text_vertical", f"{campo}.text_vertical")
        _validar_entero(meta.get("opacity", 100), f"{campo}.opacity", 0, 100)
        blend = _validar_entero(meta.get("blend_mode", 0),
                                f"{campo}.blend_mode")
        if blend not in modos:
            _fallo_proyecto("err.project.invalid_field", field=f"{campo}.blend_mode")
        if "frame_delay" in meta:
            _validar_entero(meta["frame_delay"], f"{campo}.frame_delay",
                            1, 3_600_000)
        es_texto = meta.get("is_text", False)
        campos_texto = {
            "text_html", "text_origin_x", "text_origin_y", "text_angle",
            "text_vertical", "text_spacing", "text_box_width",
        }
        if es_texto:
            _validar_texto(meta.get("text_html"), f"{campo}.text_html",
                           MAX_MANIFEST_BYTES)
        elif campos_texto.intersection(meta):
            _fallo_proyecto("err.project.invalid_field", field=f"{campo}.is_text")
        for clave in ("text_origin_x", "text_origin_y", "text_angle"):
            if clave in meta:
                _validar_numero(meta[clave], f"{campo}.{clave}")
        if "text_spacing" in meta:
            _validar_entero(meta["text_spacing"], f"{campo}.text_spacing",
                            -10_000, 10_000)
        if "text_box_width" in meta:
            _validar_entero(meta["text_box_width"], f"{campo}.text_box_width",
                            0, MAX_CANVAS_DIMENSION)
        if "mask" in meta:
            mask = _validar_ruta_zip(meta["mask"], f"{campo}.mask")
            if mask in rutas:
                _fallo_proyecto("err.project.invalid_field", field=f"{campo}.mask")
            rutas.add(mask)
            mask_count += 1
        if "group" in meta:
            gid = _validar_entero(meta["group"], f"{campo}.group", 0)
            if gid not in group_ids:
                _fallo_proyecto("err.project.invalid_field", field=f"{campo}.group")
            group_ids_referenciados.add(gid)
        efectos = meta.get("effects")
        if efectos is not None:
            if not isinstance(efectos, list) or len(efectos) > 64:
                _fallo_proyecto("err.project.invalid_field", field=f"{campo}.effects")
            for epos, efecto in enumerate(efectos):
                if not isinstance(efecto, dict) or not isinstance(efecto.get("tipo"), str):
                    _fallo_proyecto("err.project.invalid_field",
                                    field=f"{campo}.effects[{epos}]")

    grupos_vivos = set()
    for gid in group_ids_referenciados:
        actual = gid
        while actual is not None and actual not in grupos_vivos:
            grupos_vivos.add(actual)
            actual = parents[actual]
    if grupos_vivos != group_ids:
        _fallo_proyecto("err.project.invalid_field", field="groups")

    memoria = area * (4 * len(metas) + mask_count)
    if memoria > MAX_DOCUMENT_IMAGE_BYTES:
        _fallo_proyecto("err.project.memory_limit")

    guides_meta = manifest.get("guides", [])
    if not isinstance(guides_meta, list) or len(guides_meta) > MAX_GUIDES:
        _fallo_proyecto("err.project.guides_limit", max=MAX_GUIDES)
    guides = []
    for pos, guide in enumerate(guides_meta):
        campo = f"guides[{pos}]"
        if not isinstance(guide, dict):
            _fallo_proyecto("err.project.invalid_field", field=campo)
        _validar_claves(guide, {"orient", "pos"}, campo)
        orient = guide.get("orient")
        if orient not in ("h", "v"):
            _fallo_proyecto("err.project.invalid_field", field=f"{campo}.orient")
        limite = height if orient == "h" else width
        pos_val = _validar_numero(guide.get("pos"), f"{campo}.pos", 0, limite)
        guides.append({"orient": orient, "pos": pos_val})

    return width, height, dpi, metas, groups_meta, active, counter, guides, rutas


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
        "dpi": float(getattr(canvas, "dpi", 96.0) or 96.0),
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
    Lanza ErrorCargaProyecto si está corrupto, es incompatible o excede los
    límites seguros del formato."""
    try:
        with zipfile.ZipFile(file_path, "r") as zf:
            infos = zf.infolist()
            if len(infos) > MAX_ARCHIVE_ENTRIES:
                _fallo_proyecto("err.project.archive_limit")
            nombres = [info.filename for info in infos]
            if len(nombres) != len(set(nombres)):
                _fallo_proyecto("err.project.duplicate_entries")
            if sum(info.file_size for info in infos) > MAX_TOTAL_UNCOMPRESSED_BYTES:
                _fallo_proyecto("err.project.archive_limit")

            manifest_bytes = _leer_entrada(
                zf, "manifest.json", MAX_MANIFEST_BYTES)
            manifest = _cargar_json_manifest(manifest_bytes)
            (width, height, dpi, metas, groups_meta, active, counter,
             guides, rutas) = _validar_manifest(manifest)

            esperadas = set(rutas)
            esperadas.add("manifest.json")
            extras = set(nombres) - esperadas
            if extras:
                _fallo_proyecto("err.project.extra_entry",
                                file=sorted(extras)[0])
            faltantes = esperadas - set(nombres)
            if faltantes:
                _fallo_proyecto("err.project.missing_entry",
                                file=sorted(faltantes)[0])

            # 📁 Grupos (carpetas): reconstruirlos primero (dos pasadas: crear
            # y luego enlazar padres, que pueden aparecer en cualquier orden).
            grupos = {}
            for g in groups_meta:
                grupo = LayerGroup(g.get("name", "Grupo"))
                grupo.visible = g.get("visible", True)
                grupo.expanded = g.get("expanded", True)
                grupos[g["id"]] = grupo
            for g in groups_meta:
                pid = g.get("parent")
                if pid is not None:
                    grupos[g["id"]].parent = grupos[pid]

            layers = []
            for pos, meta in enumerate(metas):
                png_bytes = _leer_entrada(zf, meta["file"])
                _validar_png(png_bytes, meta["file"], width, height)
                img = QImage.fromData(png_bytes, "PNG")
                if img.isNull():
                    _fallo_proyecto("err.project.corrupt_png", file=meta["file"])
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
                layer.opacity = meta.get("opacity", 100)
                if "frame_delay" in meta:
                    layer.frame_delay = meta["frame_delay"]

                from PySide6.QtGui import QPainter
                _src_over = QPainter.CompositionMode.CompositionMode_SourceOver
                layer.blend_mode = QPainter.CompositionMode(
                    meta.get("blend_mode", _valor_enum(_src_over)))
                layer.alpha_locked = meta.get("alpha_locked", False)
                layer.pixels_locked = meta.get("pixels_locked", False)
                layer.position_locked = meta.get("position_locked", False)
                layer.clipped = meta.get("clipped", False)

                # 🎭 Máscara de capa (si el manifiesto la referencia).
                mask_file = meta.get("mask")
                if mask_file:
                    mask_bytes = _leer_entrada(zf, mask_file)
                    _validar_png(mask_bytes, mask_file, width, height)
                    mimg = QImage.fromData(mask_bytes, "PNG")
                    if mimg.isNull():
                        _fallo_proyecto("err.project.corrupt_png", file=mask_file)
                    layer.mask = mimg.convertToFormat(QImage.Format_Grayscale8)

                # ✨ Efectos de capa. Un tipo desconocido no se ignora: volver a
                # guardar el documento lo perdería silenciosamente.
                efectos = meta.get("effects")
                if efectos:
                    from models.layer_effects import crear_efecto
                    reconstruidos = []
                    for epos, datos_efecto in enumerate(efectos):
                        try:
                            efecto = crear_efecto(datos_efecto)
                        except (TypeError, ValueError):
                            efecto = None
                        if efecto is None:
                            _fallo_proyecto(
                                "err.project.unknown_effect",
                                field=f"layers[{pos}].effects[{epos}]")
                        reconstruidos.append(efecto)
                    layer.effects = reconstruidos

                # 📁 Grupo de la capa (ya validado contra la tabla de grupos).
                g_id = meta.get("group")
                if g_id is not None:
                    layer.group = grupos[g_id]

                layers.append(layer)

    except ErrorCargaProyecto:
        raise
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile,
            json.JSONDecodeError, UnicodeDecodeError, KeyError, TypeError,
            ValueError, RuntimeError, NotImplementedError, EOFError,
            OverflowError, RecursionError) as e:
        detalle = str(e) or type(e).__name__
        raise ErrorCargaProyecto(t("err.invalid_project", e=detalle)) from e

    return {
        "width": width,
        "height": height,
        "dpi": dpi,
        "layers": layers,
        "active_layer_index": active,
        "layer_counter": counter,
        "guides": guides,
    }
