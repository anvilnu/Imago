# models/layer.py
import uuid

from PySide6.QtGui import QImage, QPainter
from PySide6.QtCore import Qt


def render_doc_supersampled(doc):
    """Rasteriza un QTextDocument con SUPERSAMPLING: lo dibuja a 3x resolución
    y lo reduce con filtrado suave. El antialias directo del rasterizador de
    fuentes (con el hinting del sistema) deja escalones visibles en los bordes
    de las letras, que efectos como Trazo o Bisel realzan; promediando desde
    3x los bordes salen limpios (misma técnica que los efectos de contorno).
    Devuelve la QImage ARGB32 premultiplicada al tamaño del documento."""
    size = doc.size()
    w = max(1, int(size.width()) + 1)
    h = max(1, int(size.height()) + 1)
    # Factor según el área, para no disparar la memoria con textos enormes
    area = w * h
    f = 3 if area <= 2_000_000 else (2 if area <= 8_000_000 else 1)
    big = QImage(w * f, h * f, QImage.Format_ARGB32_Premultiplied)
    big.fill(0)
    p = QPainter(big)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.TextAntialiasing, True)
    p.scale(f, f)
    doc.drawContents(p)
    p.end()
    if f == 1:
        return big
    return big.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio,
                      Qt.TransformationMode.SmoothTransformation)


class LayerGroup:
    """Grupo (carpeta) de capas del panel: SOLO organización (v1). No participa
    en la composición por sí mismo: su visibilidad se combina con la de cada
    capa miembro (visible_efectiva), sin buffers intermedios ni coste extra de
    render. No hay registro central de grupos: un grupo 'existe' mientras
    alguna capa lo referencie en su cadena layer.group→parent, así los
    comandos de deshacer solo mueven referencias y los grupos vacíos
    desaparecen solos. INVARIANTE: las capas de un mismo grupo van CONTIGUAS
    en canvas.layers (y los subgrupos anidados dentro del tramo del padre);
    lo garantizan los comandos de grupo y la regla de reasignación del panel.
    'expanded' es solo estado de UI (plegado en el panel, no deshacible)."""

    def __init__(self, name="Grupo", parent=None):
        self.name = name
        self.visible = True
        self.expanded = True
        self.parent = parent   # LayerGroup contenedor, o None (raíz)

    def chain(self):
        """El propio grupo y sus ancestros, de dentro hacia fuera."""
        g, out = self, []
        while g is not None:
            out.append(g)
            g = g.parent
        return out


def visible_efectiva(layer):
    """Visibilidad REAL de una capa al componer: la suya Y la de todos los
    grupos que la contienen (ocultar una carpeta oculta sus capas sin tocar
    la casilla individual de cada una)."""
    if not layer.visible:
        return False
    g = getattr(layer, "group", None)
    while g is not None:
        if not g.visible:
            return False
        g = g.parent
    return True


def base_de_recorte(layers, idx):
    """Capa BASE de una capa con máscara de recorte: la primera capa NO
    recortada por debajo (varias recortadas consecutivas comparten base,
    como en Photoshop). Devuelve None si la capa no está recortada o no
    tiene base (es la del fondo). Coste O(nº de capas), sin tocar píxeles."""
    if not getattr(layers[idx], "clipped", False):
        return None
    for j in range(idx - 1, -1, -1):
        if not getattr(layers[j], "clipped", False):
            return layers[j]
    return None


def visible_para_fusion(layers, idx):
    """Indica si una capa aporta pixeles al compuesto y puede fusionarse.

    Además de la visibilidad propia y la de sus grupos, una capa recortada no
    aporta nada cuando su base está oculta. Centralizar esta comprobación evita
    que el menu, el panel y el comando acepten pares que el lienzo no dibuja.
    """
    layer = layers[idx]
    if not visible_efectiva(layer):
        return False
    base = base_de_recorte(layers, idx)
    return not (getattr(layer, "clipped", False) and base is not None
                and not visible_efectiva(base))


def render_recortada(layer, base, con_efectos=True):
    """Render de la capa RECORTADO al alfa de su base (los píxeles de la base
    con su máscara, SIN sus efectos: se recorta a lo que la base pinta de
    verdad, no a su sombra). `con_efectos=False` recorta el render pelado
    (lo usa el export ORA, que por capa no hornea efectos). Para usos de una
    sola pasada (aplanar, fusionar, exportar); el compositor del canvas hace
    lo mismo acotado al rect sucio, sin pasar por aquí."""
    img = layer.render_with_effects() if con_efectos else layer.render_image()
    if base is None:
        return img
    out = QImage(img.size(), QImage.Format_ARGB32_Premultiplied)
    out.fill(0)
    p = QPainter(out)
    p.drawImage(0, 0, img)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
    p.drawImage(0, 0, base.render_image())
    p.end()
    return out


def cadena_de_grupos(layer):
    """Grupos que contienen a la capa, del más interno al más externo
    (lista vacía si no está en ninguno)."""
    g = getattr(layer, "group", None)
    return g.chain() if g is not None else []


def miembros_de_grupo(layers, group):
    """Índices ASCENDENTES de las capas que cuelgan de 'group' (directamente
    o dentro de un subgrupo suyo)."""
    return [i for i, l in enumerate(layers) if group in cadena_de_grupos(l)]


def grupo_comun(layer_a, layer_b):
    """El grupo MÁS PROFUNDO que contiene a AMBAS capas, o None. Es la regla
    con la que el panel decide a qué grupo pasa una capa soltada entre dos
    filas (mantiene el invariante de contigüidad por construcción)."""
    if layer_a is None or layer_b is None:
        return None
    cadena_b = cadena_de_grupos(layer_b)
    for g in cadena_de_grupos(layer_a):
        if g in cadena_b:
            return g
    return None


def grupos_del_lienzo(layers):
    """Todos los grupos vivos (referenciados por alguna capa), en orden de
    primera aparición recorriendo la pila; los padres antes que sus hijos."""
    vistos = []
    for l in layers:
        for g in reversed(cadena_de_grupos(l)):   # de fuera hacia dentro
            if g not in vistos:
                vistos.append(g)
    return vistos


class Layer:
    def __init__(self, width, height, name="Capa"):
        # Identidad estable durante toda la vida de la capa. No se persiste: al
        # abrir un documento comienza una nueva sesion de objetos y destinos.
        self.uid = uuid.uuid4().hex
        self.image = QImage(width, height, QImage.Format_ARGB32)
        self.image.fill(0) # Transparente por defecto
        self.name = name
        self.visible = True
        self.opacity = 100 # Porcentaje
        self.blend_mode = QPainter.CompositionMode.CompositionMode_SourceOver
        self.alpha_locked = False
        # 🔒 Bloqueos por capa (Propiedades de capa): píxeles = no se puede
        # pintar/ajustar sobre ella; posición = no se puede mover con Mover.
        # Son PUERTAS en los puntos de entrada (canvas/menús): coste cero en
        # el pintado y la composición.
        self.pixels_locked = False
        self.position_locked = False
        # ✂️ Máscara de recorte (clipping mask): la capa solo se ve donde la
        # capa BASE (la primera no recortada por debajo) tiene píxeles. El
        # recorte se aplica al COMPONER, acotado al rect sucio (ver canvas);
        # aquí solo vive la marca.
        self.clipped = False
        # 📁 Grupo (carpeta) al que pertenece la capa en el panel, o None.
        # Es una referencia a un LayerGroup; viaja con la capa en los
        # comandos de deshacer (pop/insert conservan el objeto intacto).
        self.group = None

        # 🎭 Máscara de capa NO destructiva (escala de grises): blanco = visible,
        # negro = oculto, grises = semitransparente. None = la capa no tiene
        # máscara. Modula el alfa de la capa al componer, sin tocar self.image.
        self.mask = None
        # Caché del compuesto capa×máscara, validada por las cacheKey() de la
        # imagen y la máscara (que cambian al modificarlas), para no recalcular
        # en cada repintado.
        self._mask_cache = None
        self._mask_cache_key = None

        # ✨ Efectos de capa NO destructivos (sombra, trazo...): lista de objetos
        # de models/layer_effects. Se recalculan a partir de los píxeles de ESTA
        # capa y se cachean por capa (ver render_with_effects). Vacía = sin
        # efectos, coste cero.
        self.effects = []
        self._fx_cache = None
        self._fx_cache_key = None

    def has_mask(self):
        return self.mask is not None

    def render_with_effects(self):
        """Imagen de la capa lista para componer CON sus efectos aplicados. Si no
        hay efectos activos, devuelve el render base tal cual (coste cero). El
        resultado se cachea por capa y solo se recalcula cuando cambia el render
        base (cacheKey) o algún parámetro de los efectos — nunca por cambios en
        otras capas ni en cada repintado."""
        base = self.render_image()
        activos = [e for e in self.effects if getattr(e, "activo", False)]
        if not activos:
            return base

        key = (base.cacheKey(), tuple(e.fingerprint() for e in activos))
        if self._fx_cache is not None and self._fx_cache_key == key:
            return self._fx_cache

        from models.layer_effects import render_effects
        self._fx_cache = render_effects(base, activos)
        self._fx_cache_key = key
        return self._fx_cache

    def render_sin_mascara(self):
        """Contenido base de la capa, antes de aplicar su mascara."""
        return self.image

    def render_image(self):
        """Imagen de la capa lista para componer: si tiene máscara, devuelve una
        copia con el alfa multiplicado por ella; si no, la imagen tal cual.
        El resultado se cachea hasta que cambie la imagen o la máscara."""
        base = self.render_sin_mascara()
        if self.mask is None:
            return base
        key = (base.cacheKey(), self.mask.cacheKey())
        if self._mask_cache is not None and self._mask_cache_key == key:
            return self._mask_cache
        self._mask_cache = _apply_mask_to_image(base, self.mask)
        self._mask_cache_key = key
        return self._mask_cache


def _apply_mask_to_image(image, mask):
    """Copia de `image` (ARGB) con su canal alfa multiplicado por la máscara en
    escala de grises `mask` (mismo tamaño): blanco=opaco, negro=transparente."""
    import numpy as np
    img = image.convertToFormat(QImage.Format_RGBA8888)
    W, H = img.width(), img.height()
    bpl = img.bytesPerLine()
    arr = np.frombuffer(img.constBits(), np.uint8).reshape(H, bpl)[:, :W * 4]
    arr = arr.reshape(H, W, 4).copy()

    m = mask
    if m.width() != W or m.height() != H:
        m = m.scaled(W, H)
    m = m.convertToFormat(QImage.Format_Grayscale8)
    mbpl = m.bytesPerLine()
    marr = np.frombuffer(m.constBits(), np.uint8).reshape(H, mbpl)[:, :W]

    alpha = arr[:, :, 3].astype(np.uint16)
    arr[:, :, 3] = ((alpha * marr + 127) // 255).astype(np.uint8)
    arr = np.ascontiguousarray(arr)
    return QImage(arr.data, W, H, 4 * W, QImage.Format_RGBA8888).copy()

class TextLayer(Layer):
    """Capa vectorial para texto. Renderiza el texto 'al vuelo' a la
    resolución del lienzo. Almacena el código HTML del texto y su posición
    para que pueda ser reeditado en el futuro."""
    def __init__(self, width, height, name="Texto"):
        super().__init__(width, height, name)
        self.is_text = True
        self.text_html = ""
        from PySide6.QtCore import QPointF
        self.text_origin = QPointF(0, 0)
        # 🔄 Ángulo de rotación del texto (grados, horario), alrededor del CENTRO
        # de su caja. El texto sigue vectorial y reeditable; solo el render sale
        # girado. 0 = horizontal.
        self.text_angle = 0.0
        # ⬍ Texto VERTICAL apilado: cada carácter recto, centrado, uno debajo de
        # otro (se maqueta al vuelo; el html sigue siendo el mismo). El "de lado"
        # se consigue con text_angle=90, no con esto.
        self.text_vertical = False
        # ↔ Interletraje (px): en HORIZONTAL, separación entre letras (absoluta,
        # admite negativo); en VERTICAL, hueco entre caracteres apilados. Como el
        # toHtml NO conserva el letter-spacing, se guarda aparte y se aplica al
        # renderizar. 0 = normal.
        self.text_spacing = 0
        # ⇲ Ancho FIJO del cuadro (px de lienzo): 0 = automático (el cuadro mide
        # lo que el texto, como siempre); >0 = el texto REFLUYE envolviéndose en
        # ese ancho (modo "texto pegado": se activa al pegar del portapapeles y
        # se ajusta con el tirador del cuadro). En vertical se ignora.
        self.text_box_width = 0

        # Imagen dummy para que Canvas._check_cache vea que cambió (cacheKey)
        self.image = QImage(1, 1, QImage.Format_ARGB32)
        self.image.fill(0)

        self.base_width = width
        self.base_height = height

        self._text_cache = None
        self._text_cache_html = None
        self._text_cache_origin = None
        self._text_cache_angle = None
        self._text_cache_vertical = None
        self._text_cache_spacing = None
        self._text_cache_boxw = None

    def set_text(self, html, origin, angle=None, vertical=None, spacing=None,
                 box_width=None):
        self.text_html = html
        self.text_origin = origin
        if angle is not None:
            self.text_angle = float(angle)
        if vertical is not None:
            self.text_vertical = bool(vertical)
        if spacing is not None:
            self.text_spacing = int(spacing)
        if box_width is not None:
            self.text_box_width = max(0, int(box_width))
        # Forzamos nueva cacheKey para que canvas re-componga
        self.image = QImage(1, 1, QImage.Format_ARGB32)
        self.image.fill(0)

    def _to_vertical(self, src):
        """Reconstruye el documento con cada carácter en su propio bloque
        CENTRADO (apilado vertical), conservando el formato (fuente, tamaño,
        color, negrita...) de cada carácter."""
        from PySide6.QtGui import QTextDocument, QTextCursor, QTextBlockFormat
        from PySide6.QtCore import Qt
        # 1) recolectar los caracteres visibles con su formato, saltando los
        #    separadores de PÁRRAFO/LÍNEA (U+2029/U+2028, \n, \r); el texto
        #    multilínea se apila continuo.
        chars = []
        total = src.characterCount()
        pos = 0
        while pos < total - 1:
            c = QTextCursor(src)
            c.setPosition(pos)
            c.setPosition(pos + 1, QTextCursor.KeepAnchor)
            ch = c.selectedText()
            if ch not in ("\u2029", "\u2028", "\n", "\r"):
                from PySide6.QtGui import QTextCharFormat
                chars.append((ch, QTextCharFormat(c.charFormat())))
            pos += 1

        # 2) apilarlos centrados; el hueco (line-distance, tipo 4) va en todos
        #    MENOS el último (positivo separa, negativo aprieta), para que la caja
        #    no deje hueco sobrante ni recorte el último carácter.
        dst = QTextDocument()
        dst.setDefaultFont(src.defaultFont())
        cur = QTextCursor(dst)
        n = len(chars)
        for idx, (ch, cf) in enumerate(chars):
            bf = QTextBlockFormat()
            bf.setAlignment(Qt.AlignHCenter)
            if self.text_spacing and idx < n - 1:
                bf.setLineHeight(float(self.text_spacing), 4)
            if idx == 0:
                cur.setBlockFormat(bf)
            else:
                cur.insertBlock(bf)
            cur.insertText(ch, cf)
        return dst

    def _apply_letter_spacing(self, doc):
        """Aplica el interletraje HORIZONTAL (letter-spacing absoluto). No va en el
        html (toHtml no lo conserva): se aplica al vuelo. Se pone a todos los
        caracteres MENOS al último: el letter-spacing se añade DESPUÉS de cada
        carácter, así que ponerlo también al último dejaría un hueco sobrante (y,
        con espaciado negativo, la caja recortaba la última letra)."""
        if not self.text_spacing:
            return
        total = doc.characterCount()
        if total <= 2:   # 0-1 caracteres visibles: no hay separación entre letras
            return
        from PySide6.QtGui import QTextCursor, QTextCharFormat, QFont
        fmt = QTextCharFormat()
        fmt.setFontLetterSpacingType(QFont.AbsoluteSpacing)
        fmt.setFontLetterSpacing(float(self.text_spacing))
        cur = QTextCursor(doc)
        cur.setPosition(0)
        cur.setPosition(total - 2, QTextCursor.KeepAnchor)   # todos menos el último
        cur.mergeCharFormat(fmt)

    def _build_doc(self):
        """QTextDocument maquetado del texto (horizontal o vertical apilado),
        con su ancho ya fijado al ideal para que la alineación funcione."""
        from PySide6.QtGui import QTextDocument
        doc = QTextDocument()
        doc.setHtml(self.text_html)
        if self.text_vertical:
            doc = self._to_vertical(doc)     # el interletraje va como hueco vertical
        else:
            self._apply_letter_spacing(doc)  # interletraje horizontal
        doc.setTextWidth(-1)
        if self.text_box_width > 0 and not self.text_vertical:
            # ⇲ Ancho fijo: el texto refluye envolviéndose en el cuadro.
            doc.setTextWidth(float(self.text_box_width))
        else:
            doc.setTextWidth(doc.idealWidth())
        return doc

    def get_text_rect(self):
        """Rectángulo del texto SIN girar (en coords de lienzo)."""
        from PySide6.QtCore import QRectF
        return QRectF(self.text_origin, self._build_doc().size())

    def get_text_transform(self):
        """QTransform que gira el texto 'text_angle' grados alrededor del CENTRO
        de su caja (identidad si el ángulo es 0)."""
        from PySide6.QtGui import QTransform
        t = QTransform()
        if self.text_angle:
            c = self.get_text_rect().center()
            t.translate(c.x(), c.y())
            t.rotate(self.text_angle)
            t.translate(-c.x(), -c.y())
        return t

    def contains_point(self, pt):
        """¿El punto (coords de lienzo) cae dentro de la caja del texto, teniendo
        en cuenta el giro? Se usa para el hit-test de 'clic para editar'."""
        rect = self.get_text_rect()
        if not self.text_angle:
            return rect.contains(pt)
        inv, ok = self.get_text_transform().inverted()
        return ok and rect.contains(inv.map(pt))

    def render_sin_mascara(self):
        """Renderiza y cachea el texto sin hornear la máscara de la capa.
        (Durante la reedición la capa ya NO se oculta: la herramienta de texto
        vuelca los cambios EN VIVO con set_text y este render es el preview.)"""
        if (self._text_cache is None or
            self._text_cache_html != self.text_html or
            self._text_cache_origin != self.text_origin or
            self._text_cache_angle != self.text_angle or
            self._text_cache_vertical != self.text_vertical or
            self._text_cache_spacing != self.text_spacing or
            self._text_cache_boxw != self.text_box_width):

            self._text_cache = QImage(self.base_width, self.base_height, QImage.Format_ARGB32_Premultiplied)
            self._text_cache.fill(0)

            from PySide6.QtGui import QPainter

            # Texto (horizontal o vertical apilado) rasterizado con supersampling
            # (bordes sin dientes).
            texto = render_doc_supersampled(self._build_doc())
            p = QPainter(self._text_cache)
            # 🔄 Girado alrededor del centro de la caja (si hay ángulo). El
            # SmoothPixmapTransform evita dientes al rotar el raster.
            if self.text_angle:
                p.setRenderHint(QPainter.SmoothPixmapTransform, True)
                p.setRenderHint(QPainter.Antialiasing, True)
                p.setTransform(self.get_text_transform())
            p.drawImage(self.text_origin, texto)
            p.end()

            self._text_cache_html = self.text_html
            self._text_cache_origin = self.text_origin
            self._text_cache_angle = self.text_angle
            self._text_cache_vertical = self.text_vertical
            self._text_cache_spacing = self.text_spacing
            self._text_cache_boxw = self.text_box_width

        return self._text_cache
