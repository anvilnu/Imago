# models/psd_io.py
"""Importador de archivos de Photoshop (.psd/.psb) -> proyecto de Imago.

Solo LECTURA: Imago nunca escribe PSD; al guardar, el proyecto va a .imago.
Usa psd-tools con import PEREZOSO (Imago arranca aunque no este instalado;
solo hace falta al abrir un PSD).

load_psd() devuelve un dict con el MISMO formato que project_io.load_project()
(listo para canvas.apply_project_data), mas tres extras: 'dpi' (PPP del PSD o
None), 'omitidas' (nombres de las capas sin equivalente) y 'aplanado' (True si
no se pudo importar ninguna capa y se abrio el compuesto plano del PSD).

Correspondencia y limites (aproximaciones asumidas):
- Capas de pixeles, y las de texto/forma que traen raster -> Layer con su
  offset, opacidad, visibilidad, modo de fusion (mapeado a QPainter) y
  mascara de capa NO destructiva. El texto llega RASTERIZADO (el motor de
  texto de Photoshop no es reproducible).
- Rellenos/degradados sin raster propio -> se rasterizan con psd-tools a
  tamano lienzo (su mascara queda ya aplicada dentro del raster).
- Grupos -> se APLANAN: sus capas se importan sueltas heredando visibilidad
  y opacidad del grupo (el modo de fusion DEL GRUPO no es reproducible).
- Capas de ajuste (curvas, niveles...) -> se OMITEN (son parametricas, sin
  equivalente); van en 'omitidas' para avisar al usuario.
- CMYK y 16/32 bits -> se convierten a RGB de 8 bits al importar.
"""
from PySide6.QtGui import QImage, QPainter, qRgb

from i18n import t
from models.layer import Layer


def _mapa_fusion():
    """BlendMode de Photoshop -> CompositionMode de QPainter. Los modos sin
    equivalente en Qt caen al pariente mas cercano o a Normal."""
    from psd_tools.constants import BlendMode as B
    M = QPainter.CompositionMode
    return {
        B.NORMAL:        M.CompositionMode_SourceOver,
        B.DISSOLVE:      M.CompositionMode_SourceOver,
        B.DARKEN:        M.CompositionMode_Darken,
        B.MULTIPLY:      M.CompositionMode_Multiply,
        B.COLOR_BURN:    M.CompositionMode_ColorBurn,
        B.LINEAR_BURN:   M.CompositionMode_ColorBurn,
        B.DARKER_COLOR:  M.CompositionMode_Darken,
        B.LIGHTEN:       M.CompositionMode_Lighten,
        B.SCREEN:        M.CompositionMode_Screen,
        B.COLOR_DODGE:   M.CompositionMode_ColorDodge,
        B.LINEAR_DODGE:  M.CompositionMode_Plus,
        B.LIGHTER_COLOR: M.CompositionMode_Lighten,
        B.OVERLAY:       M.CompositionMode_Overlay,
        B.SOFT_LIGHT:    M.CompositionMode_SoftLight,
        B.HARD_LIGHT:    M.CompositionMode_HardLight,
        B.VIVID_LIGHT:   M.CompositionMode_HardLight,
        B.LINEAR_LIGHT:  M.CompositionMode_HardLight,
        B.PIN_LIGHT:     M.CompositionMode_HardLight,
        B.HARD_MIX:      M.CompositionMode_HardLight,
        B.DIFFERENCE:    M.CompositionMode_Difference,
        B.EXCLUSION:     M.CompositionMode_Exclusion,
        B.SUBTRACT:      M.CompositionMode_Difference,
    }


def _pil_a_qimage(pil):
    """Imagen PIL (cualquier modo: RGBA, RGB, CMYK, L...) -> QImage ARGB32."""
    if pil.mode != "RGBA":
        try:
            pil = pil.convert("RGBA")
        except Exception:
            pil = pil.convert("RGB").convert("RGBA")
    datos = pil.tobytes("raw", "RGBA")
    qimg = QImage(datos, pil.width, pil.height, pil.width * 4,
                  QImage.Format_RGBA8888)
    return qimg.copy().convertToFormat(QImage.Format_ARGB32)


def _iterar(grupo, visible=True, opacidad=1.0):
    """Recorre el arbol de capas de ABAJO ARRIBA (mismo orden que
    canvas.layers), aplanando los grupos: cada hoja llega con la visibilidad
    y la opacidad ACUMULADAS de sus grupos padres."""
    for capa in grupo:
        if capa.is_group():
            yield from _iterar(capa, visible and capa.visible,
                               opacidad * capa.opacity / 255.0)
        else:
            yield capa, visible, opacidad


def _convertir_mascara(capa, W, H):
    """Mascara raster del PSD -> QImage Grayscale8 a tamano lienzo, o None si
    no hay mascara util. El fondo (zona fuera del bbox de la mascara) usa el
    background_color del PSD (255 = visible, 0 = oculto)."""
    m = capa.mask
    if m is None or m.disabled:
        return None
    bg = max(0, min(255, int(m.background_color)))
    x1, y1, x2, y2 = m.bbox
    vacia = (x2 - x1 <= 0) or (y2 - y1 <= 0)
    if vacia and bg >= 255:
        return None  # sin datos y todo visible: como no tener mascara
    lienzo = QImage(W, H, QImage.Format_ARGB32)
    lienzo.fill(qRgb(bg, bg, bg))
    if not vacia:
        pil = m.topil()
        if pil is not None:
            if pil.mode != "L":
                pil = pil.convert("L")
            datos = pil.tobytes("raw", "L")
            qm = QImage(datos, pil.width, pil.height, pil.width,
                        QImage.Format_Grayscale8)
            p = QPainter(lienzo)
            p.drawImage(x1, y1, qm)
            p.end()
    return lienzo.convertToFormat(QImage.Format_Grayscale8)


def _convertir_capa(psd, capa, W, H, visible_padre, opacidad_padre, fusion):
    """Una capa hoja del PSD -> Layer de Imago (a tamano lienzo), o None si
    no tiene equivalente (capa de ajuste o sin nada rasterizable)."""
    from psd_tools.api.layers import AdjustmentLayer
    if isinstance(capa, AdjustmentLayer):
        return None  # parametrica (curvas, niveles...): sin equivalente

    layer = Layer(W, H, name=capa.name)

    pil = None
    try:
        pil = capa.topil()
    except Exception:
        pil = None
    if pil is not None and pil.width > 0 and pil.height > 0:
        # Raster propio: se coloca en su offset y la mascara se conserva
        # aparte (no destructiva), como en el PSD.
        qimg = _pil_a_qimage(pil)
        p = QPainter(layer.image)
        p.drawImage(capa.left, capa.top, qimg)
        p.end()
        mascara = _convertir_mascara(capa, W, H)
        if mascara is not None:
            layer.mask = mascara
    else:
        # Sin raster (relleno, degradado, forma vectorial pura): se rasteriza
        # SOLO esta capa componiendo el documento con un layer_filter (asi la
        # conversion de color ICC/CMYK es la misma que el render de Photoshop;
        # el composite por capa con viewport daba colores distintos). El
        # filtro debe incluir a los grupos padres o psd-tools no la recorre;
        # la mascara queda ya aplicada dentro del raster resultante.
        objetivo = {id(capa)}
        padre = getattr(capa, "parent", None)
        while padre is not None and padre is not psd:
            objetivo.add(id(padre))
            padre = getattr(padre, "parent", None)
        try:
            pil = psd.composite(layer_filter=lambda l: id(l) in objetivo)
        except Exception:
            pil = None
        if pil is None or pil.width <= 0 or pil.height <= 0:
            return None
        qimg = _pil_a_qimage(pil)
        p = QPainter(layer.image)
        p.drawImage(0, 0, qimg)
        p.end()

    layer.visible = bool(capa.visible and visible_padre)
    layer.opacity = max(0, min(100, int(round(
        capa.opacity / 255.0 * opacidad_padre * 100))))
    layer.blend_mode = fusion.get(
        capa.blend_mode, QPainter.CompositionMode.CompositionMode_SourceOver)
    return layer


def _leer_dpi(psd):
    """PPP del documento (recurso RESOLUTION_INFO), o None si no lo trae.
    El valor viene en PUNTO FIJO de 16.16 bits: PPP reales = valor / 65536."""
    try:
        from psd_tools.constants import Resource
        info = psd.image_resources.get_data(Resource.RESOLUTION_INFO)
        if info is not None:
            dpi = float(info.horizontal) / 65536.0
            if dpi > 0:
                return round(dpi, 2)
    except Exception:
        pass
    return None


def load_psd(file_path):
    """Carga un .psd/.psb y devuelve el dict de proyecto (ver docstring del
    modulo). Lanza ImportError si falta psd-tools y ValueError si el archivo
    no se puede leer."""
    from psd_tools import PSDImage  # PEREZOSO: puede lanzar ImportError

    try:
        psd = PSDImage.open(file_path)
    except Exception as e:
        raise ValueError(t("err.psd_invalid", e=e))

    W, H = psd.width, psd.height
    fusion = _mapa_fusion()
    capas, omitidas = [], []
    for capa, visible, opacidad in _iterar(psd):
        try:
            layer = _convertir_capa(psd, capa, W, H, visible, opacidad, fusion)
        except Exception:
            layer = None
        if layer is None:
            omitidas.append(f"{capa.name} ({capa.kind})")
        else:
            capas.append(layer)

    aplanado = False
    if not capas:
        # Fallback: el compuesto plano. Primero la vista previa que el propio
        # PSD embebe (render exacto de Photoshop, si se guardo con
        # "Maximizar compatibilidad"); si no, el render de psd-tools.
        plano = None
        try:
            plano = psd.topil()
        except Exception:
            plano = None
        if plano is None:
            try:
                plano = psd.composite()
            except Exception:
                plano = None
        if plano is None:
            raise ValueError(t("err.psd_no_layers"))
        layer = Layer(W, H, name=t("psd.flat_layer"))
        qimg = _pil_a_qimage(plano)
        p = QPainter(layer.image)
        p.drawImage(0, 0, qimg)
        p.end()
        capas = [layer]
        omitidas = []  # ya no aplica: se abre aplanado y se avisa aparte
        aplanado = True

    return {
        "width": W,
        "height": H,
        "layers": capas,
        "active_layer_index": len(capas) - 1,
        "layer_counter": len(capas),
        "guides": [],
        "dpi": _leer_dpi(psd),
        "omitidas": omitidas,
        "aplanado": aplanado,
    }
