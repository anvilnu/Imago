from i18n import t
# models/layer_commands.py
# Comandos deshacibles (QUndoCommand) para todas las operaciones de capas.
# Al pasar por el QUndoStack, aparecen en el panel de Historial y se pueden
# deshacer/rehacer con Ctrl+Z / Ctrl+Y igual que los trazos de dibujo.

from PySide6.QtGui import QUndoCommand, QPainter, QImage
from PySide6.QtCore import QRect, QPointF, Qt
from models.layer import Layer


def _copiar_mascara(mask):
    """Copia una mascara sin compartir el objeto mutable con el historial."""
    return QImage(mask) if mask is not None else None


def _mascara_en_grises(mask):
    """Conserva el formato canonico de las mascaras tras transformarlas."""
    if mask is None:
        return None
    if mask.format() == QImage.Format_Grayscale8:
        return QImage(mask)
    return mask.convertToFormat(QImage.Format_Grayscale8)


def _reubicar_imagen_y_mascara(image, mask, width, height, x, y,
                                fill_color=None):
    """Reubica juntos los pixeles y su mascara en un lienzo nuevo."""
    nueva_imagen = QImage(width, height, QImage.Format_ARGB32)
    nueva_imagen.fill(fill_color if fill_color is not None else 0)
    painter = QPainter(nueva_imagen)
    if fill_color is not None:
        painter.setCompositionMode(QPainter.CompositionMode_Source)
    painter.drawImage(x, y, image)
    painter.end()

    if mask is None:
        return nueva_imagen, None

    # QPainter no admite todos los formatos grises como superficie de pintado.
    # Se compone en ARGB y se vuelve al formato canonico al terminar.
    mascara_argb = QImage(width, height, QImage.Format_ARGB32)
    mascara_argb.fill(0xff000000)
    painter = QPainter(mascara_argb)
    painter.drawImage(x, y, mask)
    painter.end()
    return nueva_imagen, mascara_argb.convertToFormat(QImage.Format_Grayscale8)


def _escalar_imagen_y_mascara(image, mask, width, height):
    """Escala una imagen y su mascara con la misma geometria y suavizado."""
    nueva_imagen = image.scaled(
        width, height, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    nueva_mascara = None if mask is None else _mascara_en_grises(mask.scaled(
        width, height, Qt.IgnoreAspectRatio, Qt.SmoothTransformation))
    return nueva_imagen, nueva_mascara


def _reflejar_imagen_y_mascara(image, mask, horizontal):
    """Refleja una imagen y su mascara en el mismo eje."""
    orientation = Qt.Horizontal if horizontal else Qt.Vertical

    def reflejar(source):
        # flipped() sustituyo a mirrored() en Qt 6.9. El fallback mantiene
        # compatibilidad con las versiones anteriores de PySide6.
        if hasattr(source, "flipped"):
            return source.flipped(orientation)
        return source.mirrored(horizontal, not horizontal)

    nueva_imagen = reflejar(image)
    nueva_mascara = None if mask is None else _mascara_en_grises(reflejar(mask))
    return nueva_imagen, nueva_mascara


def _girar_imagen_y_mascara(image, mask, degrees):
    """Gira una imagen y su mascara con una unica transformacion exacta."""
    from PySide6.QtGui import QTransform
    transform = QTransform().rotate(degrees)
    nueva_imagen = image.transformed(transform)
    nueva_mascara = None if mask is None else _mascara_en_grises(
        mask.transformed(transform))
    return nueva_imagen, nueva_mascara


def _texto_html_escalado(html, factor):
    """HTML de una capa de texto con TODOS los tamaños de fuente (en px)
    escalados por 'factor' (mínimo 1 px). Los tramos sin tamaño en píxeles
    se dejan tal cual. Mantiene el resto del formato."""
    from PySide6.QtGui import QTextDocument, QTextCursor, QTextCharFormat, QTextFormat
    doc = QTextDocument()
    doc.setHtml(html)
    total = doc.characterCount()
    pos = 0
    while pos < total - 1:
        c = QTextCursor(doc)
        c.setPosition(pos)
        c.setPosition(pos + 1, QTextCursor.KeepAnchor)
        ps = c.charFormat().font().pixelSize()
        if ps > 0:
            nf = QTextCharFormat()
            # INT obligatorio (con float, toHtml() exporta "font-size:0px")
            nf.setProperty(QTextFormat.FontPixelSize, int(max(1, round(ps * factor))))
            c.mergeCharFormat(nf)
        pos += 1
    return doc.toHtml()


class _LayerCommand(QUndoCommand):
    """Base común: identifica el comando como operación de capa
    para que el panel de historial pueda asignarle un icono propio."""
    tool_id = "layer"

    def __init__(self, canvas, text):
        super().__init__(text)
        self.canvas = canvas

    def _notify(self):
        """Repinta el lienzo y refresca el panel de capas."""
        self.canvas.notify_layers_changed()


def _copiar_propiedades_de_capa(src, dst):
    """Clona metadatos editables sin compartir mascara ni efectos mutables."""
    dst.visible = src.visible
    dst.opacity = src.opacity
    dst.blend_mode = getattr(src, "blend_mode", dst.blend_mode)
    dst.alpha_locked = getattr(src, "alpha_locked", False)
    dst.pixels_locked = getattr(src, "pixels_locked", False)
    dst.position_locked = getattr(src, "position_locked", False)
    dst.clipped = getattr(src, "clipped", False)
    dst.group = getattr(src, "group", None)
    dst.mask = src.mask.copy() if src.mask is not None else None

    from models.layer_effects import clonar_efectos
    dst.effects = clonar_efectos(getattr(src, "effects", ()))
    dst.frame_delay = getattr(src, "frame_delay", None)


class AddLayerCommand(_LayerCommand):
    def __init__(self, canvas, layer=None, text=None):
        super().__init__(canvas, text or t("hist.add_layer", default="Nueva capa"))
        self.layer = layer  # Puede proveerse una capa prefabricada
        # La capa nueva se inserta ENCIMA de la ACTIVA (como en otros editores
        # y como PasteLayerCommand), no arriba del todo de la pila.
        self.insert_index = canvas.active_layer_index + 1
        self.prev_active = canvas.active_layer_index
        # 📁 La capa nueva entra en el MISMO grupo que la activa (si lo hay):
        # insertar dentro de una carpeta mantiene la contigüidad del grupo.
        self.group = (getattr(canvas.layers[self.prev_active], "group", None)
                      if 0 <= self.prev_active < len(canvas.layers) else None)

    def redo(self):
        if self.layer is None:
            self.layer = self.canvas._create_layer()
        self.layer.group = self.group
        self.canvas.layers.insert(self.insert_index, self.layer)
        self.canvas.active_layer_index = self.insert_index
        self._notify()

    def undo(self):
        self.canvas.layers.pop(self.insert_index)
        self.canvas.active_layer_index = min(self.prev_active, len(self.canvas.layers) - 1)
        self._notify()

class EditTextLayerCommand(_LayerCommand):
    """Actualiza el texto, posición y orientación (vertical) de una TextLayer."""
    def __init__(self, canvas, index, old_html, old_origin, new_html, new_origin,
                 old_vertical=None, new_vertical=None,
                 old_spacing=None, new_spacing=None,
                 old_box_width=None, new_box_width=None):
        super().__init__(canvas, t("hist.edit_text"))
        self.index = index
        self.old_html = old_html
        self.old_origin = old_origin
        self.new_html = new_html
        self.new_origin = new_origin
        self.old_vertical = old_vertical
        self.new_vertical = new_vertical
        self.old_spacing = old_spacing
        self.new_spacing = new_spacing
        self.old_box_width = old_box_width
        self.new_box_width = new_box_width

    def redo(self):
        layer = self.canvas.layers[self.index]
        layer.set_text(self.new_html, self.new_origin,
                       vertical=self.new_vertical, spacing=self.new_spacing,
                       box_width=self.new_box_width)
        self._notify()

    def undo(self):
        layer = self.canvas.layers[self.index]
        layer.set_text(self.old_html, self.old_origin,
                       vertical=self.old_vertical, spacing=self.old_spacing,
                       box_width=self.old_box_width)
        self._notify()


class TextTransformCommand(_LayerCommand):
    """Gira/mueve una capa de TEXTO de forma NO destructiva (ángulo + origen);
    el texto sigue vectorial y editable. Deshacer/rehacer solo intercambia esos
    dos valores — nada de píxeles."""
    def __init__(self, canvas, index, old_angle, old_origin, new_angle, new_origin, text=None):
        super().__init__(canvas, text or t("hist.transform", default="Transformar"))
        self.index = index
        self.old_angle = old_angle
        self.old_origin = QPointF(old_origin)
        self.new_angle = new_angle
        self.new_origin = QPointF(new_origin)

    def _apply(self, angle, origin):
        layer = self.canvas.layers[self.index]
        layer.text_angle = angle
        layer.text_origin = QPointF(origin)
        # Nueva cacheKey del dummy -> el compositor recompone.
        layer.image = QImage(1, 1, QImage.Format_ARGB32)
        layer.image.fill(0)
        self._notify()

    def redo(self):
        self._apply(self.new_angle, self.new_origin)

    def undo(self):
        self._apply(self.old_angle, self.old_origin)


class LayerEffectsCommand(_LayerCommand):
    """Añade/edita/quita EFECTOS de capa no destructivos (sombra, trazo...).
    Guarda la lista de efectos ANTES y DESPUÉS (copias profundas); deshacer y
    rehacer solo intercambian parámetros — nada de píxeles. La caché de efectos
    de la capa se invalida sola por la huella (fingerprint), pero se limpia por
    seguridad."""
    def __init__(self, canvas, index, before, after, text=None):
        super().__init__(canvas, text or t("hist.layer_effects", default="Efecto de capa"))
        self.index = index
        self.before = before   # lista de efectos (clones)
        self.after = after

    def _set(self, effects):
        from models.layer_effects import clonar_efectos
        layer = self.canvas.layers[self.index]
        # Copia al asignar: los clones guardados no quedan aliasados a la capa.
        layer.effects = clonar_efectos(effects)
        layer._fx_cache = None
        layer._fx_cache_key = None
        self._notify()

    def redo(self):
        self._set(self.after)

    def undo(self):
        self._set(self.before)


class RasterizeLayerCommand(_LayerCommand):
    """Convierte una capa de texto en una capa de píxeles normal."""
    def __init__(self, canvas, index):
        layer = canvas.layers[index]
        super().__init__(canvas, t("hist.rasterize_text", name=layer.name))
        self.index = index
        self.old_layer = layer

        self.new_layer = Layer(canvas.base_width, canvas.base_height, name=layer.name)
        # La mascara se conserva editable y se aplica despues, al componer. Usar
        # render_image() aqui la hornearia en los pixeles y luego se aplicaria de
        # nuevo desde new_layer.mask, oscureciendo dos veces sus zonas grises.
        # Conservar también el formato premultiplicado evita redondeos de color
        # innecesarios en los bordes antialias del texto.
        self.new_layer.image = layer.render_sin_mascara().copy()
        _copiar_propiedades_de_capa(layer, self.new_layer)
        # ✨ Los efectos de capa NO se pierden al rasterizar: se traspasan VIVOS
        # (clonados, para que deshacer no comparta objetos con la capa de texto)
        # a la capa de píxeles — misma silueta, mismo aspecto — y siguen
        # editables en la sublista fx. El grupo (carpeta) y la duración de
        # fotograma también viajan con la capa.

    def redo(self):
        self.canvas.layers[self.index] = self.new_layer
        self._notify()

    def undo(self):
        self.canvas.layers[self.index] = self.old_layer
        self._notify()


class MergeEffectsCommand(_LayerCommand):
    """Fusiona (HORNEA) los efectos de capa no destructivos de una capa en sus
    píxeles: el aspecto no cambia, pero la sublista fx queda vacía. Con una
    capa de TEXTO además la rasteriza (los píxeles horneados ya no se pueden
    re-renderizar desde el vector). La máscara también se hornea, igual que al
    fusionar hacia abajo (render_with_effects parte del render CON máscara).
    Deshacer restaura la capa original entera (texto/efectos/máscara)."""
    def __init__(self, canvas, index):
        layer = canvas.layers[index]
        super().__init__(canvas, t("hist.merge_fx", name=layer.name))
        self.index = index
        self.old_layer = layer

        self.new_layer = Layer(canvas.base_width, canvas.base_height, name=layer.name)
        self.new_layer.image = layer.render_with_effects().convertToFormat(
            QImage.Format_ARGB32)
        self.new_layer.visible = layer.visible
        self.new_layer.opacity = layer.opacity
        self.new_layer.blend_mode = getattr(layer, "blend_mode", 0)
        self.new_layer.alpha_locked = getattr(layer, "alpha_locked", False)
        self.new_layer.pixels_locked = getattr(layer, "pixels_locked", False)
        self.new_layer.position_locked = getattr(layer, "position_locked", False)
        self.new_layer.clipped = getattr(layer, "clipped", False)
        self.new_layer.group = getattr(layer, "group", None)
        self.new_layer.frame_delay = getattr(layer, "frame_delay", None)
        # mask=None y effects=[] a propósito: ya van horneados en los píxeles.

    def redo(self):
        self.canvas.layers[self.index] = self.new_layer
        self._notify()

    def undo(self):
        self.canvas.layers[self.index] = self.old_layer
        self._notify()


class RemoveLayerCommand(_LayerCommand):
    def __init__(self, canvas, index):
        layer_name = canvas.layers[index].name
        super().__init__(canvas, f"{t('hist.del_layer', default='Eliminar capa')} ({layer_name})")
        self.index = index
        self.layer = canvas.layers[index]  # Guardamos la capa entera para restaurarla

    def redo(self):
        self.canvas.layers.pop(self.index)
        self.canvas.active_layer_index = max(0, self.index - 1)
        self._notify()

    def undo(self):
        self.canvas.layers.insert(self.index, self.layer)
        self.canvas.active_layer_index = self.index
        self._notify()


def _copia_de_capa(canvas, src):
    """Copia independiente de una capa (de píxeles o de texto): nombre con el
    sufijo 'copia', mismos metadatos y contenido mutable duplicado."""
    if getattr(src, "is_text", False):
        from models.layer import TextLayer
        copia = TextLayer(canvas.base_width, canvas.base_height, name=f"{src.name} {t('layer.copy_suffix')}")
        # Con TODOS sus atributos de texto (antes solo html+origen: el giro, el
        # vertical, el interletraje y el ancho fijo se perdían al duplicar).
        copia.set_text(src.text_html, src.text_origin,
                       angle=getattr(src, "text_angle", 0.0),
                       vertical=getattr(src, "text_vertical", False),
                       spacing=getattr(src, "text_spacing", 0),
                       box_width=getattr(src, "text_box_width", 0))
    else:
        copia = Layer(canvas.base_width, canvas.base_height, name=f"{src.name} {t('layer.copy_suffix')}")
        copia.image = src.image.copy()

    # La copia queda en el mismo grupo (contigua al original), pero mascara y
    # efectos se clonan para que editar cualquiera de las dos capas no afecte a
    # la otra. frame_delay conserva la temporizacion de fotogramas importados.
    _copiar_propiedades_de_capa(src, copia)
    return copia


class DuplicateLayerCommand(_LayerCommand):
    def __init__(self, canvas, index):
        src = canvas.layers[index]
        super().__init__(canvas, f"{t('hist.dup_layer', default='Duplicar capa')} ({src.name})")
        self.index = index

        # Creamos la copia una sola vez; redo/undo solo la insertan o quitan
        self.copy_layer = _copia_de_capa(canvas, src)

    def redo(self):
        self.canvas.layers.insert(self.index + 1, self.copy_layer)
        self.canvas.active_layer_index = self.index + 1
        self._notify()

    def undo(self):
        self.canvas.layers.pop(self.index + 1)
        self.canvas.active_layer_index = self.index
        self._notify()


class MergeDownCommand(_LayerCommand):
    def __init__(self, canvas, index):
        top_name = canvas.layers[index].name
        bottom_name = canvas.layers[index - 1].name
        super().__init__(canvas, t("hist.merge_pair", top=top_name, bottom=bottom_name))
        self.index = index
        self.top_layer = canvas.layers[index]
        # 📸 Foto de la imagen, la máscara y los efectos inferiores ANTES de la
        # fusión: la clave para poder deshacer. Las máscaras Y los efectos de
        # capa (de arriba y de abajo) se HORNEAN al fusionar — el resultado se
        # ve igual que antes de fusionar —, así que la inferior queda sin
        # máscara y sin efectos.
        self.bottom_image_before = canvas.layers[index - 1].image.copy()
        self.bottom_mask_before = canvas.layers[index - 1].mask
        self.bottom_effects_before = list(canvas.layers[index - 1].effects)
        self.bottom_opacity_before = canvas.layers[index - 1].opacity
        self.bottom_blend_before = canvas.layers[index - 1].blend_mode
        self.bottom_clipped_before = getattr(
            canvas.layers[index - 1], "clipped", False)
        self.selected_before = list(getattr(canvas, "selected_layer_indices", [index]))
        self.merged_image = None

    def _crear_imagen_fusionada(self):
        """Compone el par igual que el lienzo, sobre transparencia.

        Máscara, efectos, opacidad, modo de fusión y recorte quedan horneados
        exactamente una vez. La capa resultante se normaliza después para que
        ninguna de esas propiedades vuelva a aplicarse sobre los píxeles.
        """
        from models.layer import base_de_recorte, render_recortada

        merged = QImage(self.canvas.base_width, self.canvas.base_height,
                        QImage.Format_ARGB32_Premultiplied)
        merged.fill(Qt.transparent)
        painter = QPainter(merged)
        for idx in (self.index - 1, self.index):
            layer = self.canvas.layers[idx]
            base_clip = base_de_recorte(self.canvas.layers, idx)
            painter.setOpacity(layer.opacity / 100.0)
            painter.setCompositionMode(getattr(
                layer, "blend_mode",
                QPainter.CompositionMode.CompositionMode_SourceOver))
            painter.drawImage(0, 0, render_recortada(layer, base_clip))
        painter.end()
        return merged.convertToFormat(QImage.Format_ARGB32)

    def redo(self):
        bottom = self.canvas.layers[self.index - 1]
        if self.merged_image is None:
            self.merged_image = self._crear_imagen_fusionada()
        bottom.image = self.merged_image.copy()
        bottom.mask = None
        bottom.effects = []
        bottom.opacity = 100
        bottom.blend_mode = QPainter.CompositionMode.CompositionMode_SourceOver
        # El recorte de ambas capas ya se calculó contra sus bases originales.
        # Conservar la marca volvería a recortar el resultado (y también la
        # parte superior que antes podía no estar recortada).
        bottom.clipped = False

        self.canvas.layers.pop(self.index)
        self.canvas.active_layer_index = self.index - 1
        self.canvas.selected_layer_indices = [self.index - 1]
        self._notify()

    def undo(self):
        # Restaurar los píxeles, la máscara y los efectos originales de la
        # capa inferior
        bottom = self.canvas.layers[self.index - 1]
        bottom.image = self.bottom_image_before.copy()
        bottom.mask = self.bottom_mask_before
        bottom.effects = list(self.bottom_effects_before)
        bottom.opacity = self.bottom_opacity_before
        bottom.blend_mode = self.bottom_blend_before
        bottom.clipped = self.bottom_clipped_before
        # Devolver la capa superior a su sitio
        self.canvas.layers.insert(self.index, self.top_layer)
        self.canvas.active_layer_index = self.index
        self.canvas.selected_layer_indices = list(self.selected_before)
        self._notify()


# (MoveLayerCommand se retiró al llegar los grupos de capas: un swap ciego
# rompería la contigüidad de las carpetas. Subir/bajar pasa SIEMPRE por
# comando_mover_capas, que reasigna el grupo según los vecinos nuevos.)


class ReorderLayerCommand(_LayerCommand):
    def __init__(self, canvas, from_index, to_index):
        layer_name = canvas.layers[from_index].name
        super().__init__(canvas, f"{t('hist.reorder_layer', default='Reordenar capa')} ({layer_name})")
        self.from_index = from_index
        self.to_index = to_index

    def _move(self, start, end):
        item = self.canvas.layers.pop(start)
        self.canvas.layers.insert(end, item)

    def redo(self):
        self._move(self.from_index, self.to_index)
        self.canvas.active_layer_index = self.to_index
        self._notify()

    def undo(self):
        self._move(self.to_index, self.from_index)
        self.canvas.active_layer_index = self.from_index
        self._notify()


# =====================================================================
# Comandos de SELECCIÓN MÚLTIPLE de capas (panel de capas con Ctrl/Shift)
# =====================================================================
class ReorderLayersCommand(_LayerCommand):
    """Reordena VARIAS capas a la vez (subir/bajar en bloque o arrastre con
    selección múltiple). 'new_order[j]' es el índice ANTIGUO de la capa que
    queda en la posición j. Recuerda la selección múltiple para reponerla en
    sus nuevas posiciones (y en las originales al deshacer).

    📁 Grupos: 'group_changes' ([(capa, grupo_nuevo), ...]) reasigna el grupo
    de las capas movidas (meterlas/sacarlas de una carpeta al soltar) y
    'parent_changes' ([(grupo, padre_nuevo), ...]) recuelga un grupo entero de
    otro padre (mover la carpeta completa). Ambos se aplican con el reorden y
    se revierten juntos al deshacer."""

    def __init__(self, canvas, new_order, text, group_changes=None, parent_changes=None):
        super().__init__(canvas, text)
        self.new_order = list(new_order)
        self.old_active = canvas.active_layer_index
        self.new_active = self.new_order.index(self.old_active)
        old_sel = [i for i in getattr(canvas, 'selected_layer_indices', [])
                   if 0 <= i < len(self.new_order)]
        self.old_selected = sorted(old_sel) or [self.old_active]
        self.new_selected = sorted(self.new_order.index(i) for i in self.old_selected)
        # (capa, grupo_viejo, grupo_nuevo) — el viejo se captura aquí
        self.group_changes = [(l, getattr(l, "group", None), g)
                              for l, g in (group_changes or [])]
        self.parent_changes = [(gr, gr.parent, p)
                               for gr, p in (parent_changes or [])]

    def redo(self):
        capas = self.canvas.layers
        self.canvas.layers = [capas[i] for i in self.new_order]
        for layer, _viejo, nuevo in self.group_changes:
            layer.group = nuevo
        for grupo, _viejo, nuevo in self.parent_changes:
            grupo.parent = nuevo
        self.canvas.active_layer_index = self.new_active
        self.canvas.selected_layer_indices = list(self.new_selected)
        self._notify()

    def undo(self):
        capas = self.canvas.layers
        originales = [None] * len(capas)
        for pos, idx in enumerate(self.new_order):
            originales[idx] = capas[pos]
        self.canvas.layers = originales
        for layer, viejo, _nuevo in self.group_changes:
            layer.group = viejo
        for grupo, viejo, _nuevo in self.parent_changes:
            grupo.parent = viejo
        self.canvas.active_layer_index = self.old_active
        self.canvas.selected_layer_indices = list(self.old_selected)
        self._notify()


def comando_mover_capas(canvas, indices, delta, text=None):
    """ReorderLayersCommand que sube (delta=+1) o baja (-1) UNA posición las
    capas dadas, en bloque: cada una avanza un puesto si tiene hueco (las que
    topan con el borde o con otra seleccionada se quedan). 📁 Con grupos, cada
    capa movida se reasigna al grupo COMÚN de sus vecinos nuevos (así subir o
    bajar también entra y sale de las carpetas manteniendo la contigüidad).
    Devuelve None si nada puede moverse."""
    from models.layer import grupo_comun
    n = len(canvas.layers)
    selset = {i for i in indices if 0 <= i < n}
    if not selset:
        return None
    orden = list(range(n))
    posiciones = range(n - 2, -1, -1) if delta > 0 else range(1, n)
    for pos in posiciones:
        vecino = pos + (1 if delta > 0 else -1)
        if orden[pos] in selset and orden[vecino] not in selset:
            orden[pos], orden[vecino] = orden[vecino], orden[pos]
    if orden == list(range(n)):
        return None

    pos_de = {viejo: j for j, viejo in enumerate(orden)}
    cambios = []
    for i in selset:
        j = pos_de[i]
        arriba = abajo = None
        for jj in range(j + 1, n):
            if orden[jj] not in selset:
                arriba = canvas.layers[orden[jj]]
                break
        for jj in range(j - 1, -1, -1):
            if orden[jj] not in selset:
                abajo = canvas.layers[orden[jj]]
                break
        destino = grupo_comun(arriba, abajo)
        if destino is not getattr(canvas.layers[i], "group", None):
            cambios.append((canvas.layers[i], destino))

    if text is None:
        if len(selset) == 1:
            nombre = canvas.layers[next(iter(selset))].name
            clave = "hist.move_layer_up" if delta > 0 else "hist.move_layer_down"
            text = f"{t(clave)} ({nombre})"
        else:
            clave = "hist.move_layers_up" if delta > 0 else "hist.move_layers_down"
            text = t(clave, n=len(selset))
    return ReorderLayersCommand(canvas, orden, text, group_changes=cambios)


class RemoveLayersCommand(_LayerCommand):
    """Elimina VARIAS capas a la vez (selección múltiple del panel o un grupo
    entero). Deshacer las reinserta todas en sus posiciones originales (con su
    grupo intacto: viaja dentro de cada objeto capa)."""

    def __init__(self, canvas, indices, text=None):
        super().__init__(canvas, text or t("hist.del_layers", n=len(indices)))
        self.indices = sorted(indices)
        self.removed = [canvas.layers[i] for i in self.indices]
        self.old_active = canvas.active_layer_index

    def redo(self):
        for i in reversed(self.indices):
            self.canvas.layers.pop(i)
        # Activa: la capa superviviente más cercana por debajo de la primera borrada
        nueva = min(max(0, self.indices[0] - 1), len(self.canvas.layers) - 1)
        self.canvas.active_layer_index = nueva
        self.canvas.selected_layer_indices = [nueva]
        self._notify()

    def undo(self):
        for i, layer in zip(self.indices, self.removed):
            self.canvas.layers.insert(i, layer)
        self.canvas.active_layer_index = self.old_active
        self.canvas.selected_layer_indices = list(self.indices)
        self._notify()


class DuplicateLayersCommand(_LayerCommand):
    """Duplica VARIAS capas a la vez: cada copia queda justo encima de su
    original y las copias quedan seleccionadas."""

    def __init__(self, canvas, indices):
        super().__init__(canvas, t("hist.dup_layers", n=len(indices)))
        self.indices = sorted(indices)
        self.copies = [_copia_de_capa(canvas, canvas.layers[i]) for i in self.indices]
        self.old_active = canvas.active_layer_index
        # Posición final de cada copia: encima de su original, más el corrimiento
        # de las copias ya insertadas por debajo de ella.
        self.copy_positions = [i + 1 + rank for rank, i in enumerate(self.indices)]

    def redo(self):
        # De arriba a abajo: insertar por encima no mueve los índices inferiores
        for i, copia in zip(reversed(self.indices), reversed(self.copies)):
            self.canvas.layers.insert(i + 1, copia)
        self.canvas.active_layer_index = self.copy_positions[-1]
        self.canvas.selected_layer_indices = list(self.copy_positions)
        self._notify()

    def undo(self):
        for pos in reversed(self.copy_positions):
            self.canvas.layers.pop(pos)
        self.canvas.active_layer_index = self.old_active
        self.canvas.selected_layer_indices = list(self.indices)
        self._notify()


class SetLayersVisibilityCommand(_LayerCommand):
    """Muestra u oculta VARIAS capas a la vez (casilla de visibilidad pulsada
    sobre una capa de la selección múltiple)."""

    def __init__(self, canvas, indices, visible):
        clave = "hist.show_layers" if visible else "hist.hide_layers"
        super().__init__(canvas, t(clave, n=len(indices)))
        self.indices = list(indices)
        self.new_visible = visible
        self.old_visible = [canvas.layers[i].visible for i in self.indices]

    def redo(self):
        for i in self.indices:
            self.canvas.layers[i].visible = self.new_visible
        self._notify()

    def undo(self):
        for i, v in zip(self.indices, self.old_visible):
            self.canvas.layers[i].visible = v
        self._notify()


# =====================================================================
# 📁 GRUPOS DE CAPAS (carpetas del panel; solo organización, v1)
# Los grupos no tienen registro central: viven en las referencias
# layer.group / group.parent, así que estos comandos solo mueven
# referencias y permutan la lista plana (nada de píxeles).
# =====================================================================
class GroupLayersCommand(ReorderLayersCommand):
    """Crea un grupo (carpeta) con las capas dadas: las hace CONTIGUAS (el
    bloque queda donde estaba la más alta) y las cuelga del grupo nuevo. Si la
    selección incluye un subgrupo COMPLETO, ese subgrupo se recuelga entero
    (conserva su estructura interna). El padre del grupo nuevo es el grupo
    común más profundo de toda la selección (anidamiento natural)."""

    def __init__(self, canvas, indices, name):
        from models.layer import (LayerGroup, cadena_de_grupos,
                                  miembros_de_grupo)
        sel = sorted(set(indices))
        selset = set(sel)
        n = len(canvas.layers)

        # Padre del grupo nuevo: el grupo común más profundo de la selección.
        cadenas = [cadena_de_grupos(canvas.layers[i]) for i in sel]
        padre = None
        for g in cadenas[0]:
            if all(g in c for c in cadenas[1:]):
                padre = g
                break

        self.group = LayerGroup(name, parent=padre)

        # Permutación de contigüidad: el bloque queda donde estaba la más alta.
        others = [i for i in range(n) if i not in selset]
        below = [i for i in others if i < sel[-1]]
        above = [i for i in others if i > sel[-1]]
        new_order = below + sel + above

        # Reasignaciones: cada capa pasa al grupo nuevo, salvo que su subgrupo
        # inmediatamente bajo 'padre' esté COMPLETO en la selección — entonces
        # se recuelga el subgrupo entero y la capa no cambia de grupo.
        cambios_capa, cambios_padre, recolgados = [], [], set()
        for i in sel:
            capa = canvas.layers[i]
            sub = None
            for g in cadena_de_grupos(capa):
                if g.parent is padre and g is not padre:
                    sub = g
                    break
            if (sub is not None
                    and set(miembros_de_grupo(canvas.layers, sub)) <= selset):
                if id(sub) not in recolgados:
                    cambios_padre.append((sub, self.group))
                    recolgados.add(id(sub))
            else:
                cambios_capa.append((capa, self.group))

        super().__init__(canvas, new_order,
                         t("hist.group_layers", name=name),
                         group_changes=cambios_capa,
                         parent_changes=cambios_padre)


class UngroupCommand(_LayerCommand):
    """Disuelve un grupo: sus capas directas pasan al grupo padre y sus
    subgrupos directos se recuelgan del padre. El orden no cambia (siguen
    contiguas), solo desaparece la carpeta."""

    def __init__(self, canvas, group):
        from models.layer import grupos_del_lienzo
        super().__init__(canvas, t("hist.ungroup", name=group.name))
        self.group = group
        self.layer_changes = [(l, l.group) for l in canvas.layers
                              if getattr(l, "group", None) is group]
        self.child_changes = [(g, g.parent)
                              for g in grupos_del_lienzo(canvas.layers)
                              if g.parent is group]

    def redo(self):
        for capa, _viejo in self.layer_changes:
            capa.group = self.group.parent
        for g, _viejo in self.child_changes:
            g.parent = self.group.parent
        self._notify()

    def undo(self):
        for capa, viejo in self.layer_changes:
            capa.group = viejo
        for g, viejo in self.child_changes:
            g.parent = viejo
        self._notify()


class RenameGroupCommand(_LayerCommand):
    """Cambia el nombre de un grupo (deshacible)."""

    def __init__(self, canvas, group, new_name):
        super().__init__(canvas, t("hist.rename_group", name=new_name))
        self.group = group
        self.old_name = group.name
        self.new_name = new_name

    def redo(self):
        self.group.name = self.new_name
        self._notify()

    def undo(self):
        self.group.name = self.old_name
        self._notify()


class GroupVisibilityCommand(_LayerCommand):
    """Muestra u oculta un grupo entero (el ojo de la carpeta). No toca la
    casilla individual de cada capa: la composición usa la visibilidad
    EFECTIVA (capa Y sus grupos), así que al volver a mostrar el grupo cada
    capa recupera su estado propio."""

    def __init__(self, canvas, group, visible):
        clave = "hist.show_group" if visible else "hist.hide_group"
        super().__init__(canvas, t(clave, name=group.name))
        self.group = group
        self.new_visible = bool(visible)
        self.old_visible = group.visible

    def redo(self):
        self.group.visible = self.new_visible
        self._notify()

    def undo(self):
        self.group.visible = self.old_visible
        self._notify()


class DuplicateGroupCommand(_LayerCommand):
    """Duplica un grupo entero: copia sus capas (y las de sus subgrupos, que
    se clonan conservando la estructura) y las inserta justo encima del grupo
    original, colgadas de la carpeta nueva."""

    def __init__(self, canvas, group):
        from models.layer import LayerGroup, miembros_de_grupo
        super().__init__(canvas, t("hist.dup_group", name=group.name))
        self.indices = miembros_de_grupo(canvas.layers, group)   # contiguos

        mapa = {}
        def clonar_grupo(g):
            if g not in mapa:
                if g is group:
                    c = LayerGroup(f"{g.name} {t('layer.copy_suffix')}",
                                   parent=g.parent)
                else:
                    c = LayerGroup(g.name, parent=clonar_grupo(g.parent))
                c.visible = g.visible
                c.expanded = g.expanded
                mapa[g] = c
            return mapa[g]

        self.copies = []
        for i in self.indices:
            src = canvas.layers[i]
            copia = _copia_de_capa(canvas, src)
            copia.group = clonar_grupo(src.group)
            self.copies.append(copia)

        self.insert_at = self.indices[-1] + 1
        self.old_active = canvas.active_layer_index
        self.old_selected = list(self.indices)

    def redo(self):
        for k, copia in enumerate(self.copies):
            self.canvas.layers.insert(self.insert_at + k, copia)
        nuevos = list(range(self.insert_at, self.insert_at + len(self.copies)))
        self.canvas.active_layer_index = nuevos[-1]
        self.canvas.selected_layer_indices = nuevos
        self._notify()

    def undo(self):
        for k in reversed(range(len(self.copies))):
            self.canvas.layers.pop(self.insert_at + k)
        self.canvas.active_layer_index = self.old_active
        self.canvas.selected_layer_indices = list(self.old_selected)
        self._notify()


class FlattenLayersCommand(_LayerCommand):
    """Fusiona TODAS las capas visibles en una sola capa 'Fondo'.
    Las capas ocultas se descartan (comportamiento estándar de aplanado).
    Totalmente deshacible: guarda la lista completa de capas originales."""

    def __init__(self, canvas):
        super().__init__(canvas, t("hist.merge_all", default="Fusionar todas las capas"))
        # 📸 Guardamos la lista completa de capas (referencias) y el índice activo
        self.old_layers = list(canvas.layers)
        self.old_active = canvas.active_layer_index
        self.flat_layer = None  # Se construye en el primer redo()

    def redo(self):
        if self.flat_layer is None:
            flat = Layer(self.canvas.base_width, self.canvas.base_height, name=t("layer.bg"))
            # MISMA composición que exportar y que el pintado en pantalla
            # (opacidad + modo de fusión), sobre fondo transparente para
            # conservar el alfa. Antes ignoraba el modo de fusión y aplanar
            # daba una imagen distinta de la que se veía.
            flat.image = self.canvas.render_flat_image(Qt.transparent).convertToFormat(
                QImage.Format_ARGB32)
            self.flat_layer = flat

        self.canvas.layers = [self.flat_layer]
        self.canvas.active_layer_index = 0
        self._notify()

    def undo(self):
        self.canvas.layers = list(self.old_layers)
        self.canvas.active_layer_index = self.old_active
        self._notify()


class PasteLayerCommand(_LayerCommand):
    """Pega una imagen del portapapeles como capa nueva, centrada en el
    lienzo. Deshacer elimina la capa pegada; rehacer la vuelve a insertar."""

    def __init__(self, canvas, image):
        super().__init__(canvas, t("hist.paste"))
        # Construimos la capa UNA vez; redo/undo solo la insertan o quitan
        self.layer = Layer(canvas.base_width, canvas.base_height, name=t("layer.pasted"))
        px = (canvas.base_width - image.width()) // 2
        py = (canvas.base_height - image.height()) // 2
        painter = QPainter(self.layer.image)
        painter.drawImage(px, py, image)
        painter.end()

        self.insert_index = canvas.active_layer_index + 1
        self.prev_active = canvas.active_layer_index
        # 📁 Como AddLayerCommand: la capa pegada entra en el grupo de la activa.
        self.layer.group = (getattr(canvas.layers[self.prev_active], "group", None)
                            if 0 <= self.prev_active < len(canvas.layers) else None)

    def redo(self):
        self.canvas.layers.insert(self.insert_index, self.layer)
        self.canvas.active_layer_index = self.insert_index
        self._notify()

    def undo(self):
        self.canvas.layers.pop(self.insert_index)
        self.canvas.active_layer_index = self.prev_active
        self._notify()


class CropCommand(_LayerCommand):
    tool_id = "crop"
    """Recorta el lienzo completo (todas las capas) al rectángulo dado.
    Deshacer restaura las dimensiones originales y los píxeles de todas
    las capas, además de la selección que originó el recorte."""

    def __init__(self, canvas, rect):
        super().__init__(canvas, f"{t('hist.crop_image')} ({rect.width()}x{rect.height()})")
        self.rect = QRect(rect)
        self.old_width = canvas.base_width
        self.old_height = canvas.base_height
        # 📸 Foto de TODAS las capas antes del recorte: imágenes Y MÁSCARAS
        # (las máscaras se recortan igual que las imágenes; si no, quedaban
        # desalineadas con el tamaño viejo). Las capas de TEXTO guardan además
        # su origen y tamaño base para desplazarlas con el recorte.
        self.old_images = [QImage(layer.image) for layer in canvas.layers]
        self.old_masks = [QImage(layer.mask) if layer.mask is not None else None
                          for layer in canvas.layers]
        self.old_text = [(QPointF(l.text_origin), l.base_width, l.base_height)
                         if getattr(l, "is_text", False) else None
                         for l in canvas.layers]
        self.old_selection = canvas.selection
        # 📏 Las guías se desplazan con el recorte (las que queden fuera del
        # lienzo nuevo se descartan); deshacer las repone todas.
        self.old_guides = [dict(g) for g in getattr(canvas, 'guides', [])]
        self.new_guides = []
        for g in self.old_guides:
            pos = g['pos'] - (rect.y() if g.get('orient') == 'h' else rect.x())
            limite = rect.height() if g.get('orient') == 'h' else rect.width()
            if 0 <= pos <= limite:
                self.new_guides.append({**g, 'pos': pos})
        self.new_images = None  # Se calculan en el primer redo()
        self.new_masks = None

    def _apply_size(self):
        c = self.canvas
        c.setFixedSize(int(c.base_width * c.zoom_factor),
                       int(c.base_height * c.zoom_factor))

    def _apply_guides(self, guides):
        self.canvas.guides = [dict(g) for g in guides]
        notify = getattr(self.canvas, '_notify_guides_changed', None)
        if notify is not None:
            notify()

    def redo(self):
        if self.new_images is None:
            self.new_images = [img.copy(self.rect) for img in self.old_images]
            self.new_masks = [m.copy(self.rect) if m is not None else None
                              for m in self.old_masks]

        for layer, img, mask, txt in zip(self.canvas.layers, self.new_images,
                                         self.new_masks, self.old_text):
            layer.image = QImage(img)
            layer.mask = QImage(mask) if mask is not None else None
            if txt is not None:
                # Capa de texto: el origen se desplaza con el recorte y el
                # tamaño base pasa a ser el del lienzo nuevo. La caché de
                # render se anula a mano (set_text no la invalida si el
                # origen no cambia, p. ej. recortando desde la esquina 0,0).
                origen, _bw, _bh = txt
                layer.base_width = self.rect.width()
                layer.base_height = self.rect.height()
                layer.set_text(layer.text_html,
                               QPointF(origen.x() - self.rect.x(),
                                       origen.y() - self.rect.y()))
                layer._text_cache = None
        self.canvas.base_width = self.rect.width()
        self.canvas.base_height = self.rect.height()
        self._apply_size()
        self._apply_guides(self.new_guides)

        # La selección ya no tiene sentido tras el recorte
        self.canvas.selection = None
        self.canvas.notify_selection_changed()
        self._notify()

    def undo(self):
        for layer, img, mask, txt in zip(self.canvas.layers, self.old_images,
                                         self.old_masks, self.old_text):
            layer.image = QImage(img)
            layer.mask = QImage(mask) if mask is not None else None
            if txt is not None:
                origen, bw, bh = txt
                layer.base_width = bw
                layer.base_height = bh
                layer.set_text(layer.text_html, QPointF(origen))
                layer._text_cache = None
        self.canvas.base_width = self.old_width
        self.canvas.base_height = self.old_height
        self._apply_size()
        self._apply_guides(self.old_guides)

        # Restauramos también la selección que originó el recorte
        self.canvas.selection = self.old_selection
        self.canvas.notify_selection_changed()
        self._notify()


class CanvasResizeCommand(_LayerCommand):
    tool_id = "canvas_size"
    """Cambia el tamaño del LIENZO sin escalar el contenido: las capas se
    recolocan en el lienzo nuevo según el offset dado. Es el motor de
    'Expandir lienzo' al pegar algo más grande. Totalmente deshacible."""

    def __init__(self, canvas, new_width, new_height, offset_x, offset_y,
                 text=None, fill_color=None):
        if text is None:
            text = t("hist.exp_canvas")
        super().__init__(canvas, f"{text} ({new_width}x{new_height})")
        self.fill_color = fill_color  # color del margen nuevo (None=transparente)
        self.new_width = new_width
        self.new_height = new_height
        self.offset_x = offset_x
        self.offset_y = offset_y
        self.old_width = canvas.base_width
        self.old_height = canvas.base_height
        self.old_images = [QImage(layer.image) for layer in canvas.layers]
        self.old_masks = [_copiar_mascara(layer.mask) for layer in canvas.layers]
        # 📝 Capas de texto: viajan con el offset (origen desplazado)
        self.old_text = [(QPointF(l.text_origin), l.base_width, l.base_height)
                         if getattr(l, "is_text", False) else None
                         for l in canvas.layers]
        self.old_selection = canvas.selection
        self.new_images = None  # Se calculan en el primer redo()
        self.new_masks = None

    def _apply_size(self):
        c = self.canvas
        c.setFixedSize(int(c.base_width * c.zoom_factor),
                       int(c.base_height * c.zoom_factor))

    def redo(self):
        if self.new_images is None:
            self.new_images = []
            self.new_masks = []
            for i, (img, mask) in enumerate(zip(self.old_images, self.old_masks)):
                fill = self.fill_color if i == 0 else None
                resized, resized_mask = _reubicar_imagen_y_mascara(
                    img, mask, self.new_width, self.new_height,
                    self.offset_x, self.offset_y, fill)
                self.new_images.append(resized)
                self.new_masks.append(resized_mask)

        for layer, img, mask, txt in zip(
                self.canvas.layers, self.new_images, self.new_masks, self.old_text):
            layer.image = QImage(img)
            layer.mask = _copiar_mascara(mask)
            if txt is not None:
                origen, _bw, _bh = txt
                layer.base_width = self.new_width
                layer.base_height = self.new_height
                layer.set_text(layer.text_html,
                               QPointF(origen.x() + self.offset_x,
                                       origen.y() + self.offset_y))
                layer._text_cache = None
        self.canvas.base_width = self.new_width
        self.canvas.base_height = self.new_height
        self._apply_size()

        # La selección viaja con el contenido recolocado
        if self.old_selection is not None:
            from PySide6.QtGui import QTransform
            self.canvas.selection = QTransform().translate(
                self.offset_x, self.offset_y).map(self.old_selection)
        self.canvas.notify_selection_changed()
        self._notify()

    def undo(self):
        for layer, img, mask, txt in zip(
                self.canvas.layers, self.old_images, self.old_masks, self.old_text):
            layer.image = QImage(img)
            layer.mask = _copiar_mascara(mask)
            if txt is not None:
                origen, bw, bh = txt
                layer.base_width = bw
                layer.base_height = bh
                layer.set_text(layer.text_html, QPointF(origen))
                layer._text_cache = None
        self.canvas.base_width = self.old_width
        self.canvas.base_height = self.old_height
        self._apply_size()
        self.canvas.selection = self.old_selection
        self.canvas.notify_selection_changed()
        self._notify()


class ImageResizeCommand(_LayerCommand):
    tool_id = "resize"
    """Cambia el tamaño de la IMAGEN escalando todas las capas (con
    suavizado de alta calidad). Para 'Imagen → Cambiar tamaño'."""

    def __init__(self, canvas, new_width, new_height):
        super().__init__(canvas, t("hist.resize_image", w=new_width, h=new_height))
        self.new_width = new_width
        self.new_height = new_height
        self.old_width = canvas.base_width
        self.old_height = canvas.base_height
        self.old_images = [QImage(layer.image) for layer in canvas.layers]
        self.old_masks = [_copiar_mascara(layer.mask) for layer in canvas.layers]
        # 📝 Capas de texto: origen, tamaño base, HTML y ancho fijo del cuadro
        # (el redo escala fuentes y ancho, así que el undo necesita los originales).
        self.old_text = [(QPointF(l.text_origin), l.base_width, l.base_height,
                          l.text_html, getattr(l, "text_box_width", 0))
                         if getattr(l, "is_text", False) else None
                         for l in canvas.layers]
        self.old_selection = canvas.selection
        self.new_images = None
        self.new_masks = None
        self.new_text = None

    def _apply_size(self):
        c = self.canvas
        c.setFixedSize(int(c.base_width * c.zoom_factor),
                       int(c.base_height * c.zoom_factor))

    def redo(self):
        sx = self.new_width / max(1, self.old_width)
        sy = self.new_height / max(1, self.old_height)
        if self.new_images is None:
            pares = [_escalar_imagen_y_mascara(
                img, mask, self.new_width, self.new_height)
                for img, mask in zip(self.old_images, self.old_masks)]
            self.new_images = [par[0] for par in pares]
            self.new_masks = [par[1] for par in pares]
            # Texto: el origen escala por eje y la FUENTE con el ALTO (con
            # proporciones distintas el texto no se estira en horizontal:
            # sigue siendo vectorial y editable). El ancho FIJO del cuadro
            # escala con el ANCHO (sigue ocupando la misma franja del lienzo).
            self.new_text = []
            for txt in self.old_text:
                if txt is None:
                    self.new_text.append(None)
                else:
                    origen, _bw, _bh, html, boxw = txt
                    self.new_text.append((QPointF(origen.x() * sx, origen.y() * sy),
                                          _texto_html_escalado(html, sy),
                                          int(round(boxw * sx)) if boxw else 0))

        for layer, img, mask, txt in zip(
                self.canvas.layers, self.new_images, self.new_masks, self.new_text):
            layer.image = QImage(img)
            layer.mask = _copiar_mascara(mask)
            if txt is not None:
                layer.base_width = self.new_width
                layer.base_height = self.new_height
                layer.set_text(txt[1], QPointF(txt[0]), box_width=txt[2])
                layer._text_cache = None
        self.canvas.base_width = self.new_width
        self.canvas.base_height = self.new_height
        self._apply_size()

        # La selección se escala proporcionalmente con el contenido
        if self.old_selection is not None and self.old_width > 0 and self.old_height > 0:
            from PySide6.QtGui import QTransform
            self.canvas.selection = QTransform().scale(sx, sy).map(self.old_selection)
        self.canvas.notify_selection_changed()
        self._notify()

    def undo(self):
        for layer, img, mask, txt in zip(
                self.canvas.layers, self.old_images, self.old_masks, self.old_text):
            layer.image = QImage(img)
            layer.mask = _copiar_mascara(mask)
            if txt is not None:
                origen, bw, bh, html, boxw = txt
                layer.base_width = bw
                layer.base_height = bh
                layer.set_text(html, QPointF(origen), box_width=boxw)
                layer._text_cache = None
        self.canvas.base_width = self.old_width
        self.canvas.base_height = self.old_height
        self._apply_size()
        self.canvas.selection = self.old_selection
        self.canvas.notify_selection_changed()
        self._notify()


class SuperResolutionCommand(_LayerCommand):
    tool_id = "resize"
    """Aumenta la resolución del LIENZO por un factor (2 o 4): la capa ACTIVA se
    reemplaza por su versión de IA (ya escalada), y las demás capas y las máscaras
    se escalan con suavizado, para mantener todo alineado. Deshacible."""

    def __init__(self, canvas, scale, active_index, active_new_image):
        super().__init__(canvas, t("hist.upscale", default="Aumentar resolución (x{s})", s=scale))
        self.scale = scale
        self.active_index = active_index
        self.active_new_image = QImage(active_new_image)   # ya a tamaño nuevo
        self.old_width = canvas.base_width
        self.old_height = canvas.base_height
        self.new_width = self.old_width * scale
        self.new_height = self.old_height * scale
        self.old_images = [QImage(layer.image) for layer in canvas.layers]
        self.old_masks = [layer.mask for layer in canvas.layers]
        self.old_selection = canvas.selection
        self.new_images = None
        self.new_masks = None

    def _apply_size(self):
        c = self.canvas
        c.setFixedSize(int(c.base_width * c.zoom_factor),
                       int(c.base_height * c.zoom_factor))

    def redo(self):
        from PySide6.QtCore import Qt as _Qt
        if self.new_images is None:
            self.new_images = []
            for i, img in enumerate(self.old_images):
                if i == self.active_index:
                    self.new_images.append(QImage(self.active_new_image))
                else:
                    self.new_images.append(img.scaled(
                        self.new_width, self.new_height,
                        _Qt.IgnoreAspectRatio, _Qt.SmoothTransformation))
            self.new_masks = [None if m is None else m.scaled(
                self.new_width, self.new_height,
                _Qt.IgnoreAspectRatio, _Qt.SmoothTransformation)
                for m in self.old_masks]

        for layer, img, mask in zip(self.canvas.layers, self.new_images, self.new_masks):
            layer.image = QImage(img)
            layer.mask = mask
        self.canvas.base_width = self.new_width
        self.canvas.base_height = self.new_height
        self._apply_size()
        if self.old_selection is not None:
            from PySide6.QtGui import QTransform
            self.canvas.selection = QTransform().scale(
                self.scale, self.scale).map(self.old_selection)
        self.canvas.notify_selection_changed()
        self._notify()

    def undo(self):
        for layer, img, mask in zip(self.canvas.layers, self.old_images, self.old_masks):
            layer.image = QImage(img)
            layer.mask = mask
        self.canvas.base_width = self.old_width
        self.canvas.base_height = self.old_height
        self._apply_size()
        self.canvas.selection = self.old_selection
        self.canvas.notify_selection_changed()
        self._notify()


# =====================================================================
# Máscaras de capa (no destructivas)
# =====================================================================
class CreateMaskCommand(_LayerCommand):
    """Añade una máscara (escala de grises) a una capa. Deshacer la quita."""

    def __init__(self, canvas, index, mask, text=None):
        super().__init__(canvas, text if text is not None else t("hist.add_mask"))
        self.index = index
        self.mask = mask
        self.old_mask = canvas.layers[index].mask

    def redo(self):
        self.canvas.layers[self.index].mask = self.mask
        self._notify()

    def undo(self):
        self.canvas.layers[self.index].mask = self.old_mask
        self.canvas.validate_mask_edit()
        self._notify()


class RemoveMaskCommand(_LayerCommand):
    """Descarta la máscara de una capa sin tocar sus píxeles."""

    def __init__(self, canvas, index):
        super().__init__(canvas, t("hist.del_mask"))
        self.index = index
        self.old_mask = canvas.layers[index].mask

    def redo(self):
        self.canvas.layers[self.index].mask = None
        self.canvas.mask_edit_active = False
        self._notify()

    def undo(self):
        self.canvas.layers[self.index].mask = self.old_mask
        self._notify()


class ApplyMaskCommand(_LayerCommand):
    """Hornea la máscara en los píxeles de la capa (multiplica su alfa) y la
    elimina. Deshacer restaura imagen y máscara originales."""

    def __init__(self, canvas, index):
        super().__init__(canvas, t("hist.apply_mask"))
        self.index = index
        layer = canvas.layers[index]
        self.old_image = layer.image.copy()
        self.old_mask = layer.mask
        self.new_image = None  # Se calcula en el primer redo()

    def redo(self):
        layer = self.canvas.layers[self.index]
        if self.new_image is None:
            from models.layer import _apply_mask_to_image
            self.new_image = _apply_mask_to_image(
                self.old_image, self.old_mask).convertToFormat(QImage.Format_ARGB32)
        layer.image = QImage(self.new_image)
        layer.mask = None
        self.canvas.mask_edit_active = False
        self._notify()

    def undo(self):
        layer = self.canvas.layers[self.index]
        layer.image = self.old_image.copy()
        layer.mask = self.old_mask
        self._notify()


class FlipCommand(_LayerCommand):
    """Voltea TODAS las capas (y la seleccion) en horizontal o vertical.
    Es su propia inversa: deshacer es volver a voltear igual (sin perdida)."""

    def __init__(self, canvas, horizontal):
        super().__init__(canvas,
                         t("hist.flip_h_full") if horizontal else t("hist.flip_v_full"))
        self.horizontal = horizontal
        self.tool_id = "flip_h" if horizontal else "flip_v"

    def _flip(self):
        c = self.canvas
        for layer in c.layers:
            _imagen_reflejada, mascara_reflejada = _reflejar_imagen_y_mascara(
                layer.image, layer.mask, self.horizontal)
            if getattr(layer, "is_text", False):
                # 📝 Capa de texto: se recoloca su CAJA reflejada, el contenido
                # sigue LEGIBLE (no se espeja; espejarlo exigiría rasterizar).
                # Volver a voltear la devuelve exacta: la operación sigue
                # siendo su propia inversa.
                r = layer.get_text_rect()
                if self.horizontal:
                    nuevo = QPointF(c.base_width - r.x() - r.width(), r.y())
                else:
                    nuevo = QPointF(r.x(), c.base_height - r.y() - r.height())
                layer.set_text(layer.text_html, nuevo)
                layer._text_cache = None
            else:
                layer.image = _imagen_reflejada
            layer.mask = mascara_reflejada
        if c.selection is not None:
            from PySide6.QtGui import QTransform
            if self.horizontal:
                t = QTransform().translate(c.base_width, 0).scale(-1, 1)
            else:
                t = QTransform().translate(0, c.base_height).scale(1, -1)
            c.selection = t.map(c.selection)
            c.notify_selection_changed()
        self._notify()

    def redo(self):
        self._flip()

    def undo(self):
        self._flip()


class FlipLayerCommand(_LayerCommand):
    """Voltea una capa y su mascara como un unico paso de historial."""

    def __init__(self, canvas, index, horizontal, text):
        super().__init__(canvas, text)
        self.index = index
        self.tool_id = "flip_h" if horizontal else "flip_v"
        layer = canvas.layers[index]
        self.old_image = QImage(layer.image)
        self.old_mask = _copiar_mascara(layer.mask)
        self.new_image, self.new_mask = _reflejar_imagen_y_mascara(
            self.old_image, self.old_mask, horizontal)

    def redo(self):
        layer = self.canvas.layers[self.index]
        layer.image = QImage(self.new_image)
        layer.mask = _copiar_mascara(self.new_mask)
        self._notify()

    def undo(self):
        layer = self.canvas.layers[self.index]
        layer.image = QImage(self.old_image)
        layer.mask = _copiar_mascara(self.old_mask)
        self._notify()


class RotateLayerCommand(_LayerCommand):
    """Gira una capa y su mascara, centradas en el lienzo sin redimensionarlo."""

    def __init__(self, canvas, index, degrees, text, tool_id):
        super().__init__(canvas, text)
        self.index = index
        self.tool_id = tool_id
        layer = canvas.layers[index]
        self.old_image = QImage(layer.image)
        self.old_mask = _copiar_mascara(layer.mask)
        imagen_girada, mascara_girada = _girar_imagen_y_mascara(
            self.old_image, self.old_mask, degrees)
        x = (canvas.base_width - imagen_girada.width()) // 2
        y = (canvas.base_height - imagen_girada.height()) // 2
        self.new_image, self.new_mask = _reubicar_imagen_y_mascara(
            imagen_girada, mascara_girada, canvas.base_width,
            canvas.base_height, x, y)

    def redo(self):
        layer = self.canvas.layers[self.index]
        layer.image = QImage(self.new_image)
        layer.mask = _copiar_mascara(self.new_mask)
        self._notify()

    def undo(self):
        layer = self.canvas.layers[self.index]
        layer.image = QImage(self.old_image)
        layer.mask = _copiar_mascara(self.old_mask)
        self._notify()


class LayerPropertiesCommand(_LayerCommand):
    """Cambia nombre y/o opacidad de una capa desde el diálogo de Propiedades.
    Agrupa ambos cambios en un solo paso del historial."""

    def __init__(self, canvas, index, old_name, new_name, old_opacity, new_opacity, old_blend=None, new_blend=None, old_alpha_locked=None, new_alpha_locked=None,
                 old_pixels_locked=None, new_pixels_locked=None,
                 old_position_locked=None, new_position_locked=None):
        super().__init__(canvas, t("hist.layer_props", name=new_name))
        self.index = index
        self.old_name = old_name
        self.new_name = new_name
        self.old_opacity = old_opacity
        self.new_opacity = new_opacity
        self.old_blend = old_blend
        self.new_blend = new_blend
        self.old_alpha_locked = old_alpha_locked
        self.new_alpha_locked = new_alpha_locked
        self.old_pixels_locked = old_pixels_locked
        self.new_pixels_locked = new_pixels_locked
        self.old_position_locked = old_position_locked
        self.new_position_locked = new_position_locked

    def redo(self):
        layer = self.canvas.layers[self.index]
        layer.name = self.new_name
        layer.opacity = self.new_opacity
        if self.new_blend is not None:
            layer.blend_mode = self.new_blend
        if self.new_alpha_locked is not None:
            layer.alpha_locked = self.new_alpha_locked
        if self.new_pixels_locked is not None:
            layer.pixels_locked = self.new_pixels_locked
        if self.new_position_locked is not None:
            layer.position_locked = self.new_position_locked
        self._notify()

    def undo(self):
        layer = self.canvas.layers[self.index]
        layer.name = self.old_name
        layer.opacity = self.old_opacity
        if self.old_blend is not None:
            layer.blend_mode = self.old_blend
        if self.old_alpha_locked is not None:
            layer.alpha_locked = self.old_alpha_locked
        if self.old_pixels_locked is not None:
            layer.pixels_locked = self.old_pixels_locked
        if self.old_position_locked is not None:
            layer.position_locked = self.old_position_locked
        self._notify()


class ClipLayerCommand(_LayerCommand):
    """Activa o desactiva la MÁSCARA DE RECORTE de una capa (la capa solo se
    ve donde su base — la primera no recortada por debajo — tiene píxeles).
    Deshacer baratísimo: viaja solo la marca, ni un píxel."""

    def __init__(self, canvas, index, clipped):
        layer_name = canvas.layers[index].name
        super().__init__(canvas, t("hist.clip_on" if clipped else "hist.clip_off",
                                   name=layer_name))
        self.index = index
        self.new_clipped = bool(clipped)
        self.old_clipped = bool(getattr(canvas.layers[index], "clipped", False))

    def redo(self):
        self.canvas.layers[self.index].clipped = self.new_clipped
        self._notify()

    def undo(self):
        self.canvas.layers[self.index].clipped = self.old_clipped
        self._notify()


class ToggleVisibilityCommand(_LayerCommand):
    """Activa o desactiva la visibilidad de una capa. Al pasar por el
    QUndoStack marca el documento como modificado (sin guardar) y aparece
    en el panel de Historial igual que cualquier otra operación de capa."""

    def __init__(self, canvas, index, visible):
        layer_name = canvas.layers[index].name
        super().__init__(canvas, t("hist.show_layer" if visible else "hist.hide_layer", name=layer_name))
        self.index = index
        self.new_visible = visible
        self.old_visible = canvas.layers[index].visible

    def redo(self):
        self.canvas.layers[self.index].visible = self.new_visible
        self._notify()

    def undo(self):
        self.canvas.layers[self.index].visible = self.old_visible
        self._notify()


class RotateCommand(_LayerCommand):
    """Gira TODAS las capas (y la seleccion) 90 horario (+90), 90 antihorario
    (-90) o 180. Las rotaciones de 90 son exactas (sin interpolacion).
    Deshacible: guarda el estado anterior completo."""

    # Claves i18n (se resuelven con t() en runtime, no en import).
    _LABELS = {90: "hist.rotate_cw_full",
               -90: "hist.rotate_ccw_full",
               180: "hist.rotate_180_full"}

    def __init__(self, canvas, degrees):
        super().__init__(canvas, t(self._LABELS.get(degrees, "hist.rotate")))
        self.degrees = degrees
        self.tool_id = {90: "rotate_cw", -90: "rotate_ccw",
                        180: "rotate_180"}.get(degrees, "rotate_cw")
        self.old_width = canvas.base_width
        self.old_height = canvas.base_height
        self.old_images = [QImage(layer.image) for layer in canvas.layers]
        self.old_masks = [_copiar_mascara(layer.mask) for layer in canvas.layers]
        # 📝 Capas de texto: origen, tamaño base y su RECTÁNGULO en el lienzo
        # viejo (para recolocar la caja al girar; el rect deriva del HTML, que
        # no cambia, así que puede medirse ya aquí).
        self.old_text = [(QPointF(l.text_origin), l.base_width, l.base_height,
                          l.get_text_rect())
                         if getattr(l, "is_text", False) else None
                         for l in canvas.layers]
        self.old_selection = canvas.selection
        self.new_images = None
        self.new_masks = None

    def _apply_size(self):
        c = self.canvas
        c.setFixedSize(int(c.base_width * c.zoom_factor),
                       int(c.base_height * c.zoom_factor))

    def _rotate_selection(self):
        # Rotar la seleccion y reubicarla en el nuevo lienzo (dos pasos sin
        # ambiguedad de orden): primero rotar, luego trasladar el bounding box.
        from PySide6.QtGui import QTransform
        ow, oh = self.old_width, self.old_height
        path = QTransform().rotate(self.degrees).map(self.old_selection)
        if self.degrees == 90:
            tx, ty = oh, 0
        elif self.degrees == -90:
            tx, ty = 0, ow
        else:
            tx, ty = ow, oh
        return QTransform().translate(tx, ty).map(path)

    def redo(self):
        if self.new_images is None:
            pares = [_girar_imagen_y_mascara(img, mask, self.degrees)
                     for img, mask in zip(self.old_images, self.old_masks)]
            self.new_images = [par[0] for par in pares]
            self.new_masks = [par[1] for par in pares]
        for layer, img, mask in zip(
                self.canvas.layers, self.new_images, self.new_masks):
            layer.image = QImage(img)
            layer.mask = _copiar_mascara(mask)
        if self.degrees in (90, -90):
            self.canvas.base_width = self.old_height
            self.canvas.base_height = self.old_width
        self._apply_size()
        # 📝 Capas de texto: la CAJA gira a su nueva posición pero el contenido
        # sigue horizontal y legible (girar las letras exigiría rasterizar).
        ow, oh = self.old_width, self.old_height
        for layer, txt in zip(self.canvas.layers, self.old_text):
            if txt is None:
                continue
            _origen, _bw, _bh, r = txt
            if self.degrees == 90:
                nuevo = QPointF(oh - r.y() - r.height(), r.x())
            elif self.degrees == -90:
                nuevo = QPointF(r.y(), ow - r.x() - r.width())
            else:
                nuevo = QPointF(ow - r.x() - r.width(), oh - r.y() - r.height())
            layer.base_width = self.canvas.base_width
            layer.base_height = self.canvas.base_height
            layer.set_text(layer.text_html, nuevo)
            layer._text_cache = None
        if self.old_selection is not None:
            self.canvas.selection = self._rotate_selection()
            self.canvas.notify_selection_changed()
        self._notify()

    def undo(self):
        for layer, img, mask, txt in zip(
                self.canvas.layers, self.old_images, self.old_masks, self.old_text):
            layer.image = QImage(img)
            layer.mask = _copiar_mascara(mask)
            if txt is not None:
                origen, bw, bh, _r = txt
                layer.base_width = bw
                layer.base_height = bh
                layer.set_text(layer.text_html, QPointF(origen))
                layer._text_cache = None
        self.canvas.base_width = self.old_width
        self.canvas.base_height = self.old_height
        self._apply_size()
        self.canvas.selection = self.old_selection
        self.canvas.notify_selection_changed()
        self._notify()


class PerspectiveCommand(_LayerCommand):
    tool_id = "crop"
    """Rectifica un CUADRILATERO de la imagen a vista frontal ('Corregir
    perspectiva'): todas las capas se transforman con la misma proyectiva
    (QTransform.quadToQuad) y el lienzo pasa a medir el rectangulo de destino.
    Como en el recorte, la seleccion se descarta (y se restaura al deshacer)."""

    def __init__(self, canvas, quad, new_width, new_height):
        super().__init__(canvas, t("hist.perspective",
                                   default="Corregir perspectiva ({w}x{h})",
                                   w=new_width, h=new_height))
        self.quad = [(float(x), float(y)) for x, y in quad]   # TL, TR, BR, BL
        self.new_width = int(new_width)
        self.new_height = int(new_height)
        self.old_width = canvas.base_width
        self.old_height = canvas.base_height
        self.old_images = [QImage(layer.image) for layer in canvas.layers]
        self.old_masks = [layer.mask for layer in canvas.layers]
        self.old_selection = canvas.selection
        self.new_images = None
        self.new_masks = None

    def _transform(self):
        from PySide6.QtGui import QTransform, QPolygonF
        from PySide6.QtCore import QPointF
        src = QPolygonF([QPointF(x, y) for x, y in self.quad])
        dst = QPolygonF([QPointF(0, 0), QPointF(self.new_width, 0),
                         QPointF(self.new_width, self.new_height),
                         QPointF(0, self.new_height)])
        return QTransform.quadToQuad(src, dst)

    def _warped(self, img):
        out = QImage(self.new_width, self.new_height, QImage.Format_ARGB32)
        out.fill(0)
        p = QPainter(out)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        p.setTransform(self._transform())
        p.drawImage(0, 0, img)
        p.end()
        return out

    def _apply_size(self):
        c = self.canvas
        c.setFixedSize(int(c.base_width * c.zoom_factor),
                       int(c.base_height * c.zoom_factor))

    def redo(self):
        if self.new_images is None:
            self.new_images = [self._warped(img) for img in self.old_images]
            self.new_masks = [
                None if m is None else self._warped(
                    m.convertToFormat(QImage.Format_ARGB32)
                ).convertToFormat(QImage.Format_Grayscale8)
                for m in self.old_masks]
        for layer, img, mask in zip(self.canvas.layers, self.new_images, self.new_masks):
            layer.image = QImage(img)
            layer.mask = mask
        self.canvas.base_width = self.new_width
        self.canvas.base_height = self.new_height
        self._apply_size()
        self.canvas.selection = None                # como en CropCommand
        self.canvas.notify_selection_changed()
        self._notify()

    def undo(self):
        for layer, img, mask in zip(self.canvas.layers, self.old_images, self.old_masks):
            layer.image = QImage(img)
            layer.mask = mask
        self.canvas.base_width = self.old_width
        self.canvas.base_height = self.old_height
        self._apply_size()
        self.canvas.selection = self.old_selection
        self.canvas.notify_selection_changed()
        self._notify()


class StraightenCommand(_LayerCommand):
    tool_id = "rotate_cw"
    """Gira TODAS las capas un ángulo ARBITRARIO (grados, convención Qt: positivo
    = horario) alrededor del centro del lienzo, manteniendo su tamaño: es el motor
    de 'Enderezar horizonte'. Las esquinas que salen se pierden y las que entran
    quedan transparentes (ángulos pequeños: pérdida mínima). Deshacible."""

    def __init__(self, canvas, degrees):
        super().__init__(canvas, t("hist.straighten",
                                   default="Enderezar horizonte ({d}°)",
                                   d=round(degrees, 1)))
        self.degrees = float(degrees)
        self.old_images = [QImage(layer.image) for layer in canvas.layers]
        self.old_masks = [layer.mask for layer in canvas.layers]
        self.old_selection = canvas.selection
        self.new_images = None
        self.new_masks = None

    def _transform(self):
        from PySide6.QtGui import QTransform
        w, h = self.canvas.base_width, self.canvas.base_height
        return (QTransform().translate(w / 2.0, h / 2.0)
                .rotate(self.degrees).translate(-w / 2.0, -h / 2.0))

    def _rotated(self, img):
        w, h = self.canvas.base_width, self.canvas.base_height
        out = QImage(w, h, QImage.Format_ARGB32)
        out.fill(0)
        p = QPainter(out)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        p.setTransform(self._transform())
        p.drawImage(0, 0, img)
        p.end()
        return out

    def redo(self):
        if self.new_images is None:
            self.new_images = [self._rotated(img) for img in self.old_images]
            # Las máscaras giran con su capa (vía ARGB y de vuelta a grises).
            self.new_masks = [
                None if m is None else self._rotated(
                    m.convertToFormat(QImage.Format_ARGB32)
                ).convertToFormat(QImage.Format_Grayscale8)
                for m in self.old_masks]
        for layer, img, mask in zip(self.canvas.layers, self.new_images, self.new_masks):
            layer.image = QImage(img)
            layer.mask = mask
        if self.old_selection is not None:
            self.canvas.selection = self._transform().map(self.old_selection)
        self.canvas.notify_selection_changed()
        self._notify()

    def undo(self):
        for layer, img, mask in zip(self.canvas.layers, self.old_images, self.old_masks):
            layer.image = QImage(img)
            layer.mask = mask
        self.canvas.selection = self.old_selection
        self.canvas.notify_selection_changed()
        self._notify()

class FreeRotateCommand(_LayerCommand):
    tool_id = "rotate_cw"
    """Gira TODAS las capas un angulo ARBITRARIO (grados, convencion Qt:
    positivo = horario) alrededor del centro del lienzo. Con expand=True el
    lienzo se AMPLIA al rectangulo envolvente del giro (no se pierde ninguna
    esquina; lo que entra queda transparente); con expand=False mantiene el
    tamano (lo que sobresale se pierde, como Enderezar horizonte). Las
    mascaras y la seleccion giran con la imagen. Deshacible."""

    def __init__(self, canvas, degrees, expand=True, text=None):
        if text is None:
            text = t("hist.free_rotate", default="Rotacion libre ({d} grados)",
                     d=round(float(degrees), 1))
        super().__init__(canvas, text)
        import math
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QTransform
        self.degrees = float(degrees)
        self.expand = bool(expand)
        self.old_w, self.old_h = canvas.base_width, canvas.base_height
        if self.expand:
            br = QTransform().rotate(self.degrees).mapRect(
                QRectF(0, 0, self.old_w, self.old_h))
            self.new_w = max(1, int(math.ceil(br.width() - 1e-6)))
            self.new_h = max(1, int(math.ceil(br.height() - 1e-6)))
        else:
            self.new_w, self.new_h = self.old_w, self.old_h
        # Foto de TODAS las capas (imagenes y mascaras) antes del giro
        self.old_images = [QImage(layer.image) for layer in canvas.layers]
        self.old_masks = [layer.mask for layer in canvas.layers]
        self.old_selection = canvas.selection
        self.new_images = None
        self.new_masks = None

    def _transform(self):
        """Giro alrededor del centro: el centro del lienzo viejo cae en el
        centro del nuevo (que con expand es el rectangulo envolvente)."""
        from PySide6.QtGui import QTransform
        return (QTransform()
                .translate(self.new_w / 2.0, self.new_h / 2.0)
                .rotate(self.degrees)
                .translate(-self.old_w / 2.0, -self.old_h / 2.0))

    def _rotated(self, img):
        out = QImage(self.new_w, self.new_h, QImage.Format_ARGB32)
        out.fill(0)
        p = QPainter(out)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        p.setTransform(self._transform())
        p.drawImage(0, 0, img)
        p.end()
        return out

    def _apply_size(self, w, h):
        c = self.canvas
        c.base_width, c.base_height = w, h
        c.setFixedSize(int(w * c.zoom_factor), int(h * c.zoom_factor))

    def redo(self):
        if self.new_images is None:
            self.new_images = [self._rotated(img) for img in self.old_images]
            # Las mascaras giran con su capa (via ARGB y de vuelta a grises)
            self.new_masks = [
                None if m is None else self._rotated(
                    m.convertToFormat(QImage.Format_ARGB32)
                ).convertToFormat(QImage.Format_Grayscale8)
                for m in self.old_masks]
        for layer, img, mask in zip(self.canvas.layers, self.new_images, self.new_masks):
            layer.image = QImage(img)
            layer.mask = mask
        self._apply_size(self.new_w, self.new_h)
        if self.old_selection is not None:
            self.canvas.selection = self._transform().map(self.old_selection)
        self.canvas.notify_selection_changed()
        self._notify()

    def undo(self):
        for layer, img, mask in zip(self.canvas.layers, self.old_images, self.old_masks):
            layer.image = QImage(img)
            layer.mask = mask
        self._apply_size(self.old_w, self.old_h)
        self.canvas.selection = self.old_selection
        self.canvas.notify_selection_changed()
        self._notify()
