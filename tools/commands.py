# tools/commands.py
from PySide6.QtGui import QUndoCommand, QImage, QPainter
from PySide6.QtCore import QRect
from i18n import t


def _diff_rect(old, new):
    """Rectángulo envolvente (QRect) de los píxeles que difieren entre dos
    QImage del mismo tamaño y formato, o None si son idénticas. Comparación
    vectorizada byte a byte con NumPy (rápida incluso en imágenes grandes)."""
    import numpy as np
    H, W = old.height(), old.width()
    bpp = old.depth() // 8
    a = np.frombuffer(old.constBits(), np.uint8).reshape(H, old.bytesPerLine())[:, :W * bpp]
    b = np.frombuffer(new.constBits(), np.uint8).reshape(H, new.bytesPerLine())[:, :W * bpp]
    changed = (a != b)
    rows = np.flatnonzero(changed.any(axis=1))
    if rows.size == 0:
        return None
    y0, y1 = int(rows[0]), int(rows[-1])
    cols = np.flatnonzero(changed[y0:y1 + 1].any(axis=0))
    x0, x1 = int(cols[0]) // bpp, int(cols[-1]) // bpp
    return QRect(x0, y0, x1 - x0 + 1, y1 - y0 + 1)


class PaintCommand(QUndoCommand):
    """Edición de píxeles deshacible. 💾 MEMORIA: no guarda copias del lienzo
    completo, sino solo el PARCHE del rectángulo realmente modificado
    (self.rect + antes/después recortados a él). Antes se guardaban dos copias
    enteras de la capa por trazo, lo que disparaba la RAM en imágenes grandes."""

    def __init__(self, canvas, layer_index, old_image, new_image, description=None,
                 tool_id=None, target="image", confine=False):
        if description is None:
            description = t("hist.draw", default="Dibujar")
        # 🎭 'target': "image" pinta los píxeles de la capa; "mask" pinta su
        # máscara (Grayscale8). El texto del historial lo indica entre paréntesis.
        if target == "mask":
            description = f"{description} {t('hist.mask_suf', default='(máscara)')}"
        super().__init__(description)
        self.canvas = canvas
        self.layer_index = layer_index
        self.target = target

        old_full = QImage(old_image)
        new_full = QImage(new_image)

        # 🪶 'confine': si hay CALADO de selección activo y se pinta sobre los
        # píxeles (no la máscara), el trazo se confina con borde suave mezclando
        # con la máscara suave al cerrar el trazo (resultado = antes·(1−m)+después·m).
        if confine and target == "image" and getattr(canvas, "selection_soft", None) is not None:
            new_full = QImage(canvas.confine_to_soft(old_full, new_full))

        # Recorte al rectángulo modificado. Convenio de almacenamiento:
        #   rect + parches      → caso normal (solo la zona tocada).
        #   rect=None, parches=None → el trazo no cambió ningún píxel.
        #   rect=None, parches enteros → caso anómalo (tamaño/formato dispares):
        #     se conservan las imágenes completas, como antaño.
        if (old_full.size() == new_full.size()
                and old_full.format() == new_full.format()):
            self.rect = _diff_rect(old_full, new_full)
            if self.rect is None:
                self.old_image = None
                self.new_image = None
            else:
                self.old_image = old_full.copy(self.rect)
                self.new_image = new_full.copy(self.rect)
        else:
            self.rect = None
            self.old_image = old_full
            self.new_image = new_full

        # 🌟 Guardamos el ID de la herramienta responsable del comando
        self.tool_id = tool_id

    def _set(self, patch):
        # Reconstruye SOLO la propiedad afectada del Layer (.image o .mask):
        # copia de la imagen actual con el parche pegado en su rectángulo. Se
        # asigna un objeto NUEVO a propósito (no se pinta in place): MoveTool
        # detecta los cambios externos comparando la IDENTIDAD del QImage.
        if patch is None:   # el trazo no cambió ningún píxel: nada que restaurar
            return
        layer = self.canvas.layers[self.layer_index]
        if self.rect is None:   # modo imagen completa (caso anómalo)
            result = QImage(patch)
        else:
            base = layer.mask if self.target == "mask" else layer.image
            if base is None:
                return
            result = QImage(base)
            p = QPainter(result)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            p.drawImage(self.rect.topLeft(), patch)
            p.end()
        if self.target == "mask":
            layer.mask = result
        else:
            layer.image = result
        self.canvas.update()

    def undo(self):
        if 0 <= self.layer_index < len(self.canvas.layers):
            self._set(self.old_image)

    def redo(self):
        if 0 <= self.layer_index < len(self.canvas.layers):
            self._set(self.new_image)

class TransformCommand(PaintCommand):
    """PaintCommand que además guarda la SELECCIÓN de antes y después.
    Al deshacer/rehacer un movimiento o transformación, las hormigas (y la
    caja de la herramienta) vuelven a la posición correcta junto con los
    píxeles, en vez de quedarse donde estaban."""

    def __init__(self, canvas, layer_index, old_image, new_image,
                 description=None, tool_id=None,
                 selection_before=None, selection_after=None, session=None):
        if description is None:
            description = t("hist.transform", default="Transformar")
        super().__init__(canvas, layer_index, old_image, new_image,
                         description, tool_id)
        self.selection_before = selection_before
        self.selection_after = selection_after
        # 📦 Instantánea de la sesión de flotado en este punto del historial:
        # {base, floating, origin, orig_selection, params_after}. La herramienta
        # la usa para restaurar la sesión EXACTA al deshacer/rehacer, sin
        # re-extraer píxeles (que es lo que mordía el fondo de lo pegado).
        self.session = session

    def redo(self):
        super().redo()
        self.canvas.selection = self.selection_after
        self.canvas.notify_selection_changed()

    def undo(self):
        super().undo()
        self.canvas.selection = self.selection_before
        self.canvas.notify_selection_changed()


class NudgeMoveCommand(TransformCommand):
    """Movimiento con flechas del teclado: los comandos CONSECUTIVOS se
    fusionan en una única entrada del historial (mecanismo mergeWith de Qt).
    Así puedes ajustar a flechazos sin inundar el historial, pero un Ctrl+Z
    sigue deshaciendo el desplazamiento acumulado completo.
    Cualquier otra operación intermedia (un trazo, un arrastre con el ratón)
    corta la cadena y el siguiente movimiento empieza una entrada nueva."""

    MERGE_ID = 1001  # Comandos con el mismo id() son candidatos a fusión

    def id(self):
        return self.MERGE_ID

    def mergeWith(self, other):
        """Qt llama aquí al apilar un comando con el mismo id que el último.
        Absorbemos su estado final; nuestro estado inicial se conserva,
        de modo que deshacer revierte TODO el movimiento acumulado.
        Con PARCHES: el rect pasa a ser la unión de ambos; el 'después' se toma
        de la capa (que ya está en el estado final, porque el redo() de 'other'
        ya corrió) y el 'antes' se reconstruye pegando el antes de 'other'
        (estado intermedio = inicial fuera de nuestro rect) y encima el nuestro
        (estado inicial); lo que ninguno tocó no cambió entre medias."""
        if not isinstance(other, NudgeMoveCommand):
            return False
        if other.layer_index != self.layer_index or other.target != self.target:
            return False
        if other.old_image is not None:
            if self.old_image is None:
                # Nosotros no tocamos píxeles: adoptamos los parches del otro
                self.rect = QRect(other.rect) if other.rect is not None else None
                self.old_image = QImage(other.old_image)
                self.new_image = QImage(other.new_image)
            elif self.rect is None or other.rect is None:
                # Alguno guarda la imagen completa (caso anómalo): no fusionar
                return False
            else:
                union = self.rect.united(other.rect)
                layer = self.canvas.layers[self.layer_index]
                base = layer.mask if self.target == "mask" else layer.image
                new_patch = base.copy(union)
                old_patch = base.copy(union)
                p = QPainter(old_patch)
                p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
                p.drawImage(other.rect.topLeft() - union.topLeft(), other.old_image)
                p.drawImage(self.rect.topLeft() - union.topLeft(), self.old_image)
                p.end()
                self.rect = union
                self.old_image = old_patch
                self.new_image = new_patch
        self.selection_after = other.selection_after
        self.session = other.session  # La instantánea más reciente de la ráfaga
        return True


class SelectionChangeCommand(QUndoCommand):
    """Cambio de selección deshacible: crear una selección, deseleccionar,
    seleccionar todo... Cada cambio es una entrada del historial, así que
    deshacer hasta el principio también devuelve la selección a su estado
    inicial (normalmente, ninguna)."""

    tool_id = "select"  # Para el icono en el panel de Historial

    def __init__(self, canvas, old_selection, new_selection, text=None,
                 tool_id="select"):
        if text is None:
            text = t("hist.select", default="Selección")
        super().__init__(text)
        self.canvas = canvas
        self.old_selection = old_selection
        self.new_selection = new_selection
        self.tool_id = tool_id  # "select" por defecto; la varita pasa "magic_wand"

    def redo(self):
        self.canvas.selection = self.new_selection
        self.canvas.notify_selection_changed()
        self.canvas.update()

    def undo(self):
        self.canvas.selection = self.old_selection
        self.canvas.notify_selection_changed()
        self.canvas.update()


class NudgeSelectionCommand(SelectionChangeCommand):
    """Desplazamiento de la marquesina con las flechas del teclado: las
    ráfagas consecutivas se fusionan en una única entrada del historial
    (misma mecánica que NudgeMoveCommand, pero solo cambia la selección;
    ningún píxel se toca). Cualquier otra operación intermedia corta la
    cadena y el siguiente flechazo abre una entrada nueva."""

    MERGE_ID = 1002  # Comandos con el mismo id() son candidatos a fusión

    def id(self):
        return self.MERGE_ID

    def mergeWith(self, other):
        if not isinstance(other, NudgeSelectionCommand):
            return False
        if other.canvas is not self.canvas:
            return False
        # Absorbemos su estado final; el inicial (nuestro) se conserva, así
        # deshacer devuelve la marquesina al punto de partida de la ráfaga.
        self.new_selection = other.new_selection
        return True


class FeatherSelectionCommand(QUndoCommand):
    """Aplica/retira el calado (borde suave) de la selección. Guarda la máscara
    suave anterior y la nueva, y alterna entre ellas (deshacible)."""

    tool_id = "select"

    def __init__(self, canvas, old_mask, new_mask, old_radius, new_radius):
        super().__init__(t("hist.feather", default="Calar selección"))
        self.canvas = canvas
        self.old_soft = old_mask
        self.new_soft = new_mask
        self.old_radius = old_radius
        self.new_radius = new_radius

    def redo(self):
        self.canvas.selection_soft = self.new_soft
        self.canvas.selection_feather_radius = self.new_radius
        self.canvas.update()

    def undo(self):
        self.canvas.selection_soft = self.old_soft
        self.canvas.selection_feather_radius = self.old_radius
        self.canvas.update()


class GuidesCommand(QUndoCommand):
    """Cambio en las guías de un lienzo (crear, mover, borrar una, o borrar
    todas al desactivar el botón de Guías). Guarda la lista de guías de antes y
    de después y alterna entre ellas. Opcionalmente cambia también el indicador
    show_guides (estado del botón/menú de Guías de ese documento)."""

    tool_id = "guides"  # Para el icono en el panel de Historial

    def __init__(self, canvas, old_guides, new_guides, text=None,
                 old_show=None, new_show=None):
        if text is None:
            text = t("hist.guides", default="Guías")
        super().__init__(text)
        self.canvas = canvas
        self.old_guides = [dict(g) for g in old_guides]
        self.new_guides = [dict(g) for g in new_guides]
        self.old_show = old_show
        self.new_show = new_show

    def _apply(self, guides, show):
        self.canvas.guides = [dict(g) for g in guides]
        if show is not None:
            self.canvas.show_guides = show
        self.canvas.update()
        self.canvas._notify_guides_changed()

    def redo(self):
        self._apply(self.new_guides, self.new_show)

    def undo(self):
        self._apply(self.old_guides, self.old_show)