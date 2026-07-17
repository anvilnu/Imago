"""Identidad y revisiones para resultados asincronos y previews de edicion."""


def _enum_value(value):
    return value.value if hasattr(value, "value") else int(value)


def canvas_abierto(main_window, canvas):
    """Indica si el lienzo sigue perteneciendo a una pestaña de la ventana."""
    tabs = getattr(main_window, "tabs", None)
    if tabs is None:
        return True
    try:
        for index in range(tabs.count()):
            marker = tabs.widget(index)
            if marker is not None and getattr(marker, "canvas", None) is canvas:
                return True
    except RuntimeError:
        return False
    return False


def canvas_activo(main_window, canvas):
    """Comprueba que el lienzo sigue abierto y es el documento visible."""
    if not canvas_abierto(main_window, canvas):
        return False
    getter = getattr(main_window, "get_current_canvas", None)
    return getter is None or getter() is canvas


def revision_documento(canvas):
    """Huella barata del contenido y orden que forman la imagen compuesta."""
    layers = []
    for layer in canvas.layers:
        mask = getattr(layer, "mask", None)
        effects = tuple(
            effect.fingerprint() for effect in getattr(layer, "effects", ())
            if hasattr(effect, "fingerprint")
        )
        group = getattr(layer, "group", None)
        group_state = []
        while group is not None:
            group_state.append((id(group), getattr(group, "visible", True)))
            group = getattr(group, "parent", None)
        layers.append((
            layer.uid,
            layer.image.cacheKey(),
            mask.cacheKey() if mask is not None else 0,
            bool(layer.visible),
            int(layer.opacity),
            _enum_value(layer.blend_mode),
            bool(getattr(layer, "clipped", False)),
            tuple(group_state),
            effects,
        ))
    return (int(canvas.base_width), int(canvas.base_height), tuple(layers))


class DestinoCapa:
    """Capa concreta más la revisión de píxeles que originó una operación."""

    def __init__(self, canvas, index):
        self.canvas = canvas
        self.layer = canvas.layers[index]
        self.uid = self.layer.uid
        self.revision = self.layer.image.cacheKey()

    def indice_actual(self, main_window=None, exigir_revision=True,
                      exigir_activo=False):
        if main_window is not None:
            comprobador = canvas_activo if exigir_activo else canvas_abierto
            if not comprobador(main_window, self.canvas):
                return None
        try:
            for index, layer in enumerate(self.canvas.layers):
                if layer is self.layer and layer.uid == self.uid:
                    if exigir_revision and layer.image.cacheKey() != self.revision:
                        return None
                    return index
        except RuntimeError:
            return None
        return None

    def actualizar_revision(self):
        self.revision = self.layer.image.cacheKey()


class DestinoDocumento:
    """Documento completo más la revisión de todas sus capas y geometría."""

    def __init__(self, canvas):
        self.canvas = canvas
        self.revision = revision_documento(canvas)

    def vigente(self, main_window=None, exigir_revision=True,
                exigir_activo=False):
        if main_window is not None:
            comprobador = canvas_activo if exigir_activo else canvas_abierto
            if not comprobador(main_window, self.canvas):
                return False
        if not exigir_revision:
            return True
        try:
            return revision_documento(self.canvas) == self.revision
        except RuntimeError:
            return False

    def actualizar_revision(self):
        self.revision = revision_documento(self.canvas)
