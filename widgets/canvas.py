from i18n import t
# widgets/canvas.py
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter, QImage, QColor, QBrush, QUndoStack, QRegion
from PySide6.QtCore import Qt, QSize
from models.layer import (Layer, visible_efectiva, visible_para_fusion,
                          base_de_recorte, render_recortada)

# 🔒 Herramientas que EDITAN los píxeles de la capa activa: con el bloqueo de
# píxeles (Propiedades de capa) su clic se corta en mousePressEvent con un
# aviso en la barra de estado. Mover queda fuera (tiene su propio bloqueo de
# posición) y las de selección/vista no tocan píxeles.
HERRAMIENTAS_DE_PIXELES = {
    "pen", "pencil", "eraser", "bucket", "gradient", "airbrush", "clone",
    "smudge", "dodge_burn", "sponge", "liquify", "heal", "replace_color",
    "shapes", "line_curve", "pen_path",
}
import theme

class Canvas(QWidget):
    def __init__(self, width=800, height=600):
        super().__init__()
        self.setAttribute(Qt.WA_StaticContents)
        # ⌨️ Necesario para recibir eventos de teclado (flechas para mover, etc.)
        self.setFocusPolicy(Qt.StrongFocus)
        # 🖱️ Recibir movimientos de ratón SIN botón pulsado: el transformador
        # cambia el cursor al sobrevolar sus tiradores. Las demás herramientas
        # no se ven afectadas (todas comprueban event.buttons() en mouse_move).
        self.setMouseTracking(True)
        
        # Dimensiones base fijas de la imagen real
        self.base_width = width
        self.base_height = height
        
        self.zoom_factor = 1.0  # 1.0 significa 100%
        
        # Le damos el tamaño físico inicial en Qt
        self.setFixedSize(self.base_width, self.base_height)
        
        # Configuración de dibujo
        self.brush_size = 5
        # ✎ Lápiz: tamaño y forma propios (independientes del pincel)
        self.pencil_size = 1
        self.pencil_shape = 'round'
        self.brush_shape = 'round'   # forma de la punta del pincel
        self.eraser_shape = 'round'  # forma de la punta de la goma
        # Pincel en modo SELECCIÓN: al activarlo, el pincel no pinta píxeles, sino
        # que define una selección pintando (izq=añade, der=resta). Ver PenTool.
        self.pen_selection_mode = False
        self.brush_color = QColor(Qt.black)            # 🎨 Primario (botón izquierdo)
        self.brush_color_secondary = QColor(Qt.white)  # 🎨 Secundario (botón derecho)
        self.brush_hardness = 100   # dureza por defecto (trazo sólido)
        self.brush_opacity = 100    # opacidad del trazo (independiente del alfa del color)
        
        # Historial y Capas
        self.undo_stack = QUndoStack(self)
        # 🔔 Avisar a la herramienta activa cuando el historial cambie
        # (deshacer/rehacer): así la caja de Mover selección sigue los cambios
        self.undo_stack.indexChanged.connect(self._on_history_changed)
        self.layers = []
        self.active_layer_index = 0
        # 🗂️ Selección MÚLTIPLE del panel de capas (índices reales; normalmente
        # incluye la activa). Las acciones en bloque del panel (subir/bajar,
        # arrastrar, eliminar, duplicar, visibilidad) operan sobre esta lista.
        self.selected_layer_indices = [0]
        self.layer_counter = 0  # Contador independiente para nombrar capas

        # 📁 Ruta del archivo .imago asociado a este lienzo.
        # None = proyecto nunca guardado (Ctrl+S preguntará dónde la primera vez)
        self.project_path = None

        # 🖼️ Ruta del archivo de IMAGEN asociado (png/jpg/...) cuando se guardó
        # en un formato plano. Mutuamente excluyente con project_path: el lienzo
        # está ligado a un .imago O a una imagen. Ctrl+S sobrescribe el asociado.
        self.image_path = None
        self.image_quality = -1  # calidad/compresión recordada para Ctrl+S (-1=por defecto)
        self.dpi = 96.0  # resolución de impresión (PPP); metadato, no afecta a los píxeles

        # ✂️ Selección activa (QPainterPath) o None si no hay nada seleccionado
        self.selection = None
        self.selection_mode = 'replace'      # replace | add | subtract | intersect
        # 🪶 Calado (feather): máscara de selección SUAVE (QImage Grayscale8, mismo
        # tamaño que el lienzo) con bordes difuminados. None = selección dura (se
        # usa el trazado binario). Se descarta al cambiar la selección.
        self.selection_soft = None
        self.selection_feather_radius = 0   # radio del calado activo (px)
        # 📏 Guías: líneas de referencia con imán. Cada una: {'orient':'h'|'v',
        # 'pos': px de lienzo}. 'h' usa pos = y; 'v' usa pos = x. Se guardan en el
        # proyecto .imago. _pending_guide es la que se está arrastrando desde la regla.
        self.guides = []
        self.show_guides = True
        self._pending_guide = None
        self._dragging_guide = None          # índice de la guía que se mueve (o None)
        self._guides_drag_old = None         # snapshot al empezar a arrastrar una guía

        # 🎭 Edición de máscara: True = los trazos van a la MÁSCARA de la capa
        # activa (en gris) en vez de a sus píxeles. Lo activa el panel de capas
        # al pulsar la miniatura de la máscara.
        self.mask_edit_active = False
        # --- Varita mágica ---
        self.magic_wand_tolerance = 32
        self.magic_wand_contiguous = True
        self.magic_wand_sample_all = False
        # --- Recorte ---
        self.crop_ratio = None                # None=libre | (rw, rh) relación fija
        # --- Herramientas de selección (panel de opciones) ---
        self.selection_size_mode = 'normal'   # 'normal' | 'ratio' | 'fixed'
        self.selection_ratio_w = 1            # proporción W:H (modo 'ratio')
        self.selection_ratio_h = 1
        self.selection_fixed_w = 100          # tamaño exacto en px (modo 'fixed')
        self.selection_fixed_h = 100
        self.lasso_polygonal = False          # lazo: False=mano alzada, True=clic a clic
        # --- Sustituir color ---
        self.replace_tolerance = 32
        self.replace_shape = 'round'
        self.replace_hardness = 100
        self.replace_contiguous = False
        self.replace_sample_all = False
        # --- Aerógrafo ---
        self.airbrush_hardness = 50
        self.airbrush_flow = 20
        self.airbrush_shape = 'round'
        self.airbrush_texture = 'smooth'   # 'smooth' | 'speckled'
        # --- Tampón de clonar ---
        self.clone_shape = 'round'
        self.clone_aligned = True
        self.clone_sample_all = False
        # --- Cubo de pintura ---
        self.bucket_tolerance = 32
        self.bucket_contiguous = True      # True = Local (región contigua), False = Global
        self.bucket_antialias = False
        self.bucket_sample_all = False
        # --- Selector de color (cuentagotas) ---
        self.eyedropper_sample_size = 1     # 1 | 3 | 5 (media de área)
        self.eyedropper_sample_all = True   # True = todas las capas, False = capa activa
        # --- Formas ---
        self.shape_fill_pattern = None              # None = sin relleno (solo contorno)
        self.shape_line_style = Qt.PenStyle.SolidLine  # estilo del contorno
        # --- Degradado ---
        self.gradient_pattern = "Lineal"
        self.gradient_mode = "Color"            # Color | Transparencia
        self.gradient_dither = False            # suavizar bandas
        # --- Pluma ---
        self.pen_path_line_style = Qt.PenStyle.SolidLine
        # --- Dedo / Emborronar ---
        self.smudge_hardness = 50
        self.smudge_strength = 50
        self.smudge_spacing = 12        # % del diámetro entre estampados
        self.smudge_finger_paint = False
        # 🐜 "Marching ants": desfase animado del contorno de selección.
        self._ants_offset = 0
        from PySide6.QtCore import QTimer
        self._ants_timer = QTimer(self)
        self._ants_timer.setInterval(90)
        self._ants_timer.timeout.connect(self._advance_ants)
        self._ants_timer.start()

        # 🖼️ Márgenes de vista (en píxeles lógicos): espacio extra alrededor
        # del lienzo para que la caja de transformación sea visible y agarrable
        # aunque sobresalga (pegados más grandes que el lienzo, rotaciones...)
        # 👁️ Opciones de vista (menú Ver): cuadrícula de píxeles y reglas
        self.show_grid = False
        self.grid_tile = 0      # mosaico de la cuadrícula: línea maestra cada
                                # N px (8/16/32/64; 0 = sin mosaico)
        self.show_rulers = False
        self.RULER_SIZE = 22  # Grosor de las reglas en píxeles de pantalla
        self.ruler_overlay = None  # Lo asigna main; recibe la posición del cursor

        self.margin_left = 0
        self.margin_top = 0
        self.margin_right = 0
        self.margin_bottom = 0
        # Margen permanente: el lienzo se muestra centrado con un borde gris
        # (del mismo color del fondo) clicable alrededor, para poder iniciar
        # selecciones desde FUERA del lienzo. set_view_margins recorta este
        # valor al espacio realmente disponible del viewport.
        self._permanent_margin = False
        self._base_margin = 100000

        # Añadir primera capa (se llama "Fondo")
        self.add_new_layer()
        self.layers[0].image.fill(Qt.white)
        
        # Herramienta por defecto
        from tools.draw_tools import PenTool # Importación local para evitar bucles
        self.current_tool = PenTool(self)

    def _create_layer(self):
        """Crea un objeto Layer con el nombre correcto según el contador interno."""
        if self.layer_counter == 0:
            name = t("layer.bg", default="Fondo")
        else:
            name = t("layer.new_default", default="Capa {}").format(self.layer_counter)
        self.layer_counter += 1
        return Layer(self.base_width, self.base_height, name=name)

    def add_new_layer(self):
        """Añade una capa SIN pasar por el historial.
        Solo para la inicialización del lienzo (la capa Fondo no debe ser deshacible)."""
        new_layer = self._create_layer()
        self.layers.append(new_layer)
        self.active_layer_index = len(self.layers) - 1

    def notify_layers_changed(self):
        """Repinta el lienzo y avisa al panel de capas (si hay uno escuchando).
        Los comandos de deshacer/rehacer llaman aquí para mantener la UI en sincronía."""
        self.update()
        callback = getattr(self, 'layers_changed_callback', None)
        if callback:
            callback()

    def get_active_layer(self):
        return self.layers[self.active_layer_index].image

    def get_active_layer_obj(self):
        """La CAPA activa (objeto Layer), o None. Nota: get_active_layer()
        devuelve su .image por motivos históricos; esto da la capa entera."""
        if 0 <= self.active_layer_index < len(self.layers):
            return self.layers[self.active_layer_index]
        return None

    def paint_on_mask(self):
        """True si las herramientas de pintura deben escribir en la MÁSCARA de la
        capa activa (modo edición de máscara activo y la capa tiene máscara)."""
        layer = self.get_active_layer_obj()
        return bool(self.mask_edit_active and layer is not None and layer.has_mask())

    def paint_target(self):
        """El QImage sobre el que pintan las herramientas: la máscara (Grayscale8)
        si está activo el modo máscara, o los píxeles de la capa (ARGB32) si no."""
        layer = self.get_active_layer_obj()
        if layer is None:
            return None
        if self.mask_edit_active and layer.has_mask():
            return layer.mask
        return layer.image

    def get_active_layer_image(self):
        # Esta es la forma segura de obtener la imagen de la capa seleccionada
        if 0 <= self.active_layer_index < len(self.layers):
            return self.layers[self.active_layer_index].image
        return None

    def load_image_into_layer(self, qimage):
        """Carga un QImage en la capa Fondo correctamente, ajustando dimensiones y nombre."""
        # Actualizamos dimensiones base
        self.base_width = qimage.width()
        self.base_height = qimage.height()
        self.setFixedSize(self.base_width, self.base_height)
        self.set_view_margins(0, 0, 0, 0)
        from PySide6.QtCore import QTimer as _QTimer
        _QTimer.singleShot(0, self._recenter_view)

        # Cargamos la imagen en la capa Fondo existente (índice 0)
        self.layers[0].image = qimage.convertToFormat(QImage.Format_ARGB32)
        self.layers[0].name = t("layer.bg", default="Fondo")
        self.active_layer_index = 0

    # =========================================================================
    # OPERACIONES DE CAPAS (deshacibles)
    # Cada operación empuja un QUndoCommand al stack: aparece en el Historial
    # y se puede deshacer/rehacer con Ctrl+Z / Ctrl+Y.
    # =========================================================================

    def add_layer_undoable(self):
        """Añade una capa nueva pasando por el historial."""
        from models.layer_commands import AddLayerCommand
        self.undo_stack.push(AddLayerCommand(self))

    def remove_active_layer(self):
        """Elimina la capa activa (deshacible). No permite borrar la última capa."""
        if len(self.layers) <= 1:
            return False
        from models.layer_commands import RemoveLayerCommand
        self.undo_stack.push(RemoveLayerCommand(self, self.active_layer_index))
        return True

    def duplicate_active_layer(self):
        """Duplica la capa activa y la coloca justo encima (deshacible)."""
        from models.layer_commands import DuplicateLayerCommand
        self.undo_stack.push(DuplicateLayerCommand(self, self.active_layer_index))

    def merge_layer_down(self):
        """Fusiona la capa activa con la inferior (deshacible).
        Devuelve False si la capa activa ya es la del fondo o si alguna de las
        dos está oculta (se hornearían píxeles que no se ven)."""
        i = self.active_layer_index
        if (i <= 0 or not visible_para_fusion(self.layers, i)
                or not visible_para_fusion(self.layers, i - 1)):
            return False
        from models.layer_commands import MergeDownCommand
        self.undo_stack.push(MergeDownCommand(self, self.active_layer_index))
        return True

    def merge_layer_effects(self):
        """Fusiona (hornea) los efectos de capa de la capa activa en sus
        píxeles (deshacible); con texto, además rasteriza. Devuelve False si
        la capa no tiene efectos."""
        layer = self.get_active_layer_obj()
        if layer is None or not getattr(layer, "effects", None):
            return False
        from models.layer_commands import MergeEffectsCommand
        self.undo_stack.push(MergeEffectsCommand(self, self.active_layer_index))
        return True

    def move_layer_up(self):
        """Sube la capa activa una posición (deshacible). 📁 Con grupos usa la
        fábrica común: al cruzar el borde de una carpeta, la capa entra o sale
        de ella (manteniendo la contigüidad del grupo)."""
        from models.layer_commands import comando_mover_capas
        cmd = comando_mover_capas(self, [self.active_layer_index], +1)
        if cmd is None:
            return False
        self.undo_stack.push(cmd)
        return True

    def move_layer_down(self):
        """Baja la capa activa una posición (deshacible)."""
        from models.layer_commands import comando_mover_capas
        cmd = comando_mover_capas(self, [self.active_layer_index], -1)
        if cmd is None:
            return False
        self.undo_stack.push(cmd)
        return True

    def flatten_layers(self):
        """Fusiona todas las capas visibles en una sola (deshacible).
        Devuelve False si solo hay una capa."""
        if len(self.layers) <= 1:
            return False
        from models.layer_commands import FlattenLayersCommand
        self.undo_stack.push(FlattenLayersCommand(self))
        return True

    # =========================================================================
    # MÁSCARAS DE CAPA (no destructivas)
    # =========================================================================
    def _build_white_mask(self):
        """Máscara blanca (la capa se ve entera), en escala de grises."""
        from PySide6.QtGui import QImage
        m = QImage(self.base_width, self.base_height, QImage.Format_Grayscale8)
        m.fill(255)
        return m

    def _build_mask_from_selection(self):
        """Máscara desde la selección actual: lo seleccionado visible (blanco),
        el resto oculto (negro)."""
        from PySide6.QtGui import QImage, QPainter
        m = QImage(self.base_width, self.base_height, QImage.Format_Grayscale8)
        m.fill(0)
        p = QPainter(m)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.fillPath(self.selection, Qt.white)
        p.end()
        return m

    def create_mask(self, from_selection=False):
        """Añade una máscara a la capa activa (deshacible). 'from_selection' la
        construye a partir de la selección; si no, máscara blanca. No hace nada
        si la capa ya tiene máscara (o no hay selección y se pedía desde ella)."""
        layer = self.get_active_layer_obj()
        if layer is None or layer.has_mask():
            return False
        if from_selection:
            if self.selection is None:
                return False
            mask = self._build_mask_from_selection()
            text = t("hist.mask_from_sel")
        else:
            mask = self._build_white_mask()
            text = t("hist.add_mask")
        from models.layer_commands import CreateMaskCommand
        self.undo_stack.push(
            CreateMaskCommand(self, self.active_layer_index, mask, text))
        return True

    def apply_mask(self):
        """Hornea la máscara en los píxeles de la capa activa y la elimina."""
        layer = self.get_active_layer_obj()
        if layer is None or not layer.has_mask():
            return False
        from models.layer_commands import ApplyMaskCommand
        self.undo_stack.push(ApplyMaskCommand(self, self.active_layer_index))
        return True

    def remove_mask(self):
        """Descarta la máscara de la capa activa sin tocar sus píxeles."""
        layer = self.get_active_layer_obj()
        if layer is None or not layer.has_mask():
            return False
        from models.layer_commands import RemoveMaskCommand
        self.undo_stack.push(RemoveMaskCommand(self, self.active_layer_index))
        return True

    def validate_mask_edit(self):
        """Si la capa activa no tiene máscara, desactiva el modo de edición de
        máscara (no se puede pintar en una máscara inexistente)."""
        layer = self.get_active_layer_obj()
        if layer is None or not layer.has_mask():
            self.mask_edit_active = False

    def render_flat_image(self, background=Qt.white):
        """Compone todas las capas visibles (con su opacidad) en un único QImage.
        NO modifica las capas: es solo para guardar a disco o exportar."""
        final_image = QImage(self.base_width, self.base_height, QImage.Format_ARGB32_Premultiplied)
        final_image.fill(background)
        painter = QPainter(final_image)
        for i, layer in enumerate(self.layers):
            # 📁 Visibilidad EFECTIVA: la de la capa Y la de sus grupos.
            if visible_efectiva(layer):
                # ✂️ Máscara de recorte: igual que el compositor en pantalla
                # (base oculta = la recortada no se ve; el render sale ya
                # acotado al alfa de la base).
                base = base_de_recorte(self.layers, i)
                if getattr(layer, "clipped", False) and base is not None \
                        and not visible_efectiva(base):
                    continue
                painter.setOpacity(layer.opacity / 100.0)
                painter.setCompositionMode(getattr(layer, "blend_mode", QPainter.CompositionMode.CompositionMode_SourceOver))
                # ✨ Con efectos de capa (sombra...): el aplanado para guardar/
                # exportar debe incluirlos, como los ve el usuario.
                painter.drawImage(0, 0, render_recortada(layer, base))
        painter.end()
        return final_image

    # =========================================================================
    # SELECCIÓN Y PORTAPAPELES
    # =========================================================================

    def draw_pixel_grid(self, painter, sx=0, sy=0, sw=None, sh=None):
        """Rejilla de 1px por celda. Pen cosmético (ancho 0) para que las
        líneas midan 1px en pantalla sin deformarse con el zoom. Se limita a
        las celdas VISIBLES (sx,sy,sw,sh en coords de imagen): así no se trazan
        miles de líneas de extremo a extremo a zoom alto."""
        from PySide6.QtGui import QPen
        if sw is None: sw = self.base_width
        if sh is None: sh = self.base_height
        x0 = max(0, int(sx)); x1 = min(self.base_width, int(sx + sw) + 1)
        y0 = max(0, int(sy)); y1 = min(self.base_height, int(sy + sh) + 1)
        pen = QPen(QColor(128, 128, 128, 90))
        pen.setWidth(0)
        painter.setPen(pen)
        for x in range(x0, x1 + 1):
            painter.drawLine(x, y0, x, y1)
        for y in range(y0, y1 + 1):
            painter.drawLine(x0, y, x1, y)

    def draw_tile_grid(self, painter, sx=0, sy=0, sw=None, sh=None):
        """Línea MAESTRA de mosaico cada `grid_tile` px (8/16/32/64): delimita
        los tiles de un sprite sheet o tileset. Más marcada que la rejilla de
        píxel y visible ya desde el 100% (la de píxel exige zoom alto). Igual
        que draw_pixel_grid: pen cosmético y acotada a las celdas VISIBLES.
        El gris fijo es intencional, como el de la rejilla de píxel (overlay
        neutro sobre cualquier imagen, no un control del tema)."""
        from PySide6.QtGui import QPen
        paso = int(getattr(self, "grid_tile", 0))
        if paso <= 0:
            return
        if sw is None: sw = self.base_width
        if sh is None: sh = self.base_height
        x0 = max(0, int(sx)); x1 = min(self.base_width, int(sx + sw) + 1)
        y0 = max(0, int(sy)); y1 = min(self.base_height, int(sy + sh) + 1)
        pen = QPen(QColor(128, 128, 128, 170))
        pen.setWidth(0)
        painter.setPen(pen)
        for x in range(((x0 + paso - 1) // paso) * paso, x1 + 1, paso):
            painter.drawLine(x, y0, x, y1)
        for y in range(((y0 + paso - 1) // paso) * paso, y1 + 1, paso):
            painter.drawLine(x0, y, x1, y)

    def draw_rulers(self, painter):
        """Reglas horizontal y vertical pegadas al borde del widget. Marcan
        coordenadas del LIENZO (en píxeles lógicos), siguiendo zoom, márgenes
        y desplazamiento. El intervalo entre marcas se adapta al zoom."""
        from PySide6.QtGui import QPen, QFont
        z = self.zoom_factor
        rs = self.RULER_SIZE

        def lienzo_a_pantalla_x(lx):
            return (self.margin_left + lx) * z

        def lienzo_a_pantalla_y(ly):
            return (self.margin_top + ly) * z

        # Intervalo de marcas: que no se amontonen (apuntamos a ~50px/marca)
        candidatos = [1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000]
        intervalo = candidatos[-1]
        for c in candidatos:
            if c * z >= 50:
                intervalo = c
                break

        # Bandas de fondo de las reglas
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(45, 45, 45))
        painter.drawRect(0, 0, self.width(), rs)               # Horizontal (arriba)
        painter.drawRect(0, 0, rs, self.height())              # Vertical (izquierda)
        # Cuadradito de la esquina
        painter.setBrush(QColor(35, 35, 35))
        painter.drawRect(0, 0, rs, rs)

        pen = QPen(QColor(200, 200, 200))
        pen.setWidth(1)
        painter.setPen(pen)
        font = QFont("Segoe UI", 7)
        painter.setFont(font)

        # Regla horizontal: marcas en X
        x = 0
        while x <= self.base_width:
            sx = lienzo_a_pantalla_x(x)
            if sx >= rs:
                painter.drawLine(int(sx), rs - 6, int(sx), rs)
                painter.drawText(int(sx) + 2, rs - 8, str(x))
            x += intervalo

        # Regla vertical: marcas en Y (texto rotado 90°)
        y = 0
        while y <= self.base_height:
            sy = lienzo_a_pantalla_y(y)
            if sy >= rs:
                painter.drawLine(rs - 6, int(sy), rs, int(sy))
                painter.save()
                painter.translate(rs - 8, int(sy) + 2)
                painter.rotate(-90)
                painter.drawText(0, 0, str(y))
                painter.restore()
            y += intervalo

    def set_show_grid(self, value):
        self.show_grid = bool(value)
        self.update()

    def set_show_rulers(self, value):
        self.show_rulers = bool(value)
        self.update()

    def set_grid_tile(self, paso):
        """Tamaño del mosaico de la cuadrícula (línea maestra cada `paso` px;
        0 = sin mosaico). Solo se dibuja con la cuadrícula activada."""
        self.grid_tile = max(0, int(paso))
        self.update()

    def _advance_ants(self):
        """Avanza el desfase de los guiones para que el contorno 'camine'.
        Solo repinta si hay una selección activa (si no, no gasta nada)."""
        if self.selection is None:
            return
        self._ants_offset = (self._ants_offset + 1) % 8
        self.update()

    def draw_selection_outline(self, painter, path, fill=False):
        """Dibuja el contorno de selección: línea negra sólida con guiones
        blancos encima (las 'hormigas' clásicas, visibles sobre cualquier fondo).
        Los QPen de ancho 0 son 'cosméticos': miden 1px en pantalla sea cual
        sea el nivel de zoom.
        Con fill=True rellena antes el interior con un velo azulado (color de
        acento) casi transparente, para que el área seleccionada destaque un
        poco: lo usa la MARQUESINA de selección (y su previsualización al
        arrastrar). Las cajas de recorte/transformación/formas llaman sin
        relleno (ahí el interior no está "seleccionado")."""
        from PySide6.QtGui import QPen
        if fill:
            velo = QColor(theme.ACCENT)
            velo.setAlpha(32)
            painter.fillPath(path, velo)
        painter.setBrush(Qt.NoBrush)

        pen_black = QPen(QColor(0, 0, 0))
        pen_black.setWidth(0)
        painter.setPen(pen_black)
        painter.drawPath(path)

        pen_white = QPen(QColor(255, 255, 255))
        pen_white.setWidth(0)
        pen_white.setDashPattern([4, 4])
        pen_white.setDashOffset(self._ants_offset)
        painter.setPen(pen_white)
        painter.drawPath(path)

    def _on_history_changed(self, _index=None):
        """El historial cambió (deshacer/rehacer/nuevo comando): si la
        herramienta activa quiere resincronizarse, se lo decimos."""
        tool = getattr(self, 'current_tool', None)
        if tool is not None and hasattr(tool, 'on_history_changed'):
            tool.on_history_changed()

    def set_view_margins(self, left, top, right, bottom):
        """Ajusta el espacio extra de vista alrededor del lienzo. La
        herramienta de mover lo solicita cuando su caja sobresale.
        🧷 Dos políticas para que el LIENZO NO BAILE en pantalla:
        1) Márgenes simétricos: lo que crece un lado crece su opuesto.
           Con la vista centrada, el lienzo queda clavado por construcción.
        2) Compensación de scroll: si hay barras activas, desplazamos la
           vista exactamente lo que crecieron los márgenes de izq./arriba,
           anclando los píxeles del lienzo a la pantalla."""
        # Con borde permanente, el margen lo calcula _apply_permanent_margin
        # (espacio sobrante EXACTO del viewport). Toda petición -incluida la
        # del move- se redirige ahí, así el lienzo nunca baila ni se agranda.
        if getattr(self, "_permanent_margin", False):
            self._apply_permanent_margin()
            return
        horizontal = max(0, int(left), int(right))
        vertical = max(0, int(top), int(bottom))

        # 🚫 TOPE (estilo Paint.NET): los márgenes nunca hacen que el widget
        # supere el tamaño de la ventana visible, así que JAMÁS provocan
        # barras de desplazamiento (que era la fuente del saltito). La caja
        # es visible y agarrable en todo el fondo oscuro disponible; lo que
        # quede fuera de la ventana se alcanza alejando el zoom (Ctrl+rueda).
        viewport = self.parentWidget()
        if viewport is not None and viewport.width() > 0:
            z = max(self.zoom_factor, 0.0001)
            avail_w = (viewport.width() - 2) / z - self.base_width
            avail_h = (viewport.height() - 2) / z - self.base_height
            horizontal = min(horizontal, max(0, int(avail_w // 2)))
            vertical = min(vertical, max(0, int(avail_h // 2)))

        # 🔑 Cuadrar los márgenes a un número ENTERO de píxeles de pantalla
        # (margen * zoom ∈ ℤ). Así, al recentrar el widget tras cambiar de
        # tamaño, el origen del lienzo cae SIEMPRE en el mismo píxel y
        # desaparecen los micro-saltos de centrado al mover la selección fuera.
        z = max(self.zoom_factor, 0.0001)
        horizontal = round(horizontal * z) / z
        vertical = round(vertical * z) / z

        if (horizontal, vertical) == (self.margin_left, self.margin_top):
            return

        # 📐 ANCLA GLOBAL + DOS PASADAS: anotamos dónde está el origen del
        # lienzo en coordenadas de PANTALLA y lo devolvemos ahí dos veces:
        # 1) inmediatamente (cubre el cambio de tamaño y el centrado), y
        # 2) diferido con singleShot(0), porque la APARICIÓN de las barras
        #    de desplazamiento es un re-layout que Qt procesa un instante
        #    después — la pasada diferida corre tras ese re-layout pero
        #    ANTES del siguiente repintado, así que el residuo nunca se ve.
        from PySide6.QtCore import QPoint, QTimer
        z = self.zoom_factor
        self._view_anchor = self.mapToGlobal(
            QPoint(int(self.margin_left * z), int(self.margin_top * z)))

        self.margin_left = self.margin_right = horizontal
        self.margin_top = self.margin_bottom = vertical
        self._apply_view_size()

        self._restore_view_anchor()                  # Pasada 1: lo síncrono
        QTimer.singleShot(0, self._restore_view_anchor)  # Pasada 2: tras las barras
        self.update()

    def _restore_view_anchor(self):
        """Devuelve el origen del lienzo a su punto anclado de pantalla,
        midiendo la desviación actual en coordenadas globales. Es
        idempotente: si no hay desviación, no hace nada."""
        anchor = getattr(self, '_view_anchor', None)
        if anchor is None:
            return
        from PySide6.QtCore import QPoint
        z = self.zoom_factor
        current = self.mapToGlobal(
            QPoint(int(self.margin_left * z), int(self.margin_top * z)))
        self._compensate_scroll(current.x() - anchor.x(),
                                current.y() - anchor.y())

    def _compensate_scroll(self, delta_x, delta_y):
        """Desplaza las barras del QScrollArea contenedor exactamente la
        diferencia MEDIDA de posición del lienzo: quede como quede tras el
        cambio (centrado, con barras, transición entre ambos), las barras
        lo devuelven a su sitio y el lienzo permanece inmóvil en pantalla."""
        viewport = self.parentWidget()
        scroll_area = viewport.parentWidget() if viewport is not None else None
        if scroll_area is None or not hasattr(scroll_area, 'horizontalScrollBar'):
            return
        if delta_x:
            bar = scroll_area.horizontalScrollBar()
            bar.setValue(bar.value() + int(delta_x))
        if delta_y:
            bar = scroll_area.verticalScrollBar()
            bar.setValue(bar.value() + int(delta_y))

    def reset_view_margins(self):
        self.set_view_margins(0, 0, 0, 0)

    def showEvent(self, event):
        super().showEvent(event)
        sa = self._get_scroll_area()
        if sa is not None and not getattr(self, "_vp_filter_installed", False):
            sa.viewport().installEventFilter(self)
            self._vp_filter_installed = True
        # Aplicar el margen permanente ahora que ya hay viewport con tamaño
        self.set_view_margins(0, 0, 0, 0)
        self._recenter_view()
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self._recenter_view)

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        if event.type() == QEvent.Type.Resize:
            # La ventana/viewport cambió de tamaño: recalcular el borde clicable
            self.set_view_margins(0, 0, 0, 0)
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self._recenter_view)
        return super().eventFilter(obj, event)

    def _apply_permanent_margin(self):
        """Calcula el borde clicable EXACTO = espacio sobrante del viewport, lo
        asigna como margen simétrico y centra el lienzo. Si aún no hay viewport
        con tamaño, no hace nada (nunca deja un marco gigante)."""
        if not getattr(self, "_permanent_margin", False):
            return
        vp = self.parentWidget()
        if vp is None or vp.width() <= 1 or vp.height() <= 1:
            return
        z = max(self.zoom_factor, 0.0001)
        avail_w = vp.width() / z - self.base_width
        avail_h = vp.height() / z - self.base_height
        h = max(0.0, avail_w / 2.0)
        v = max(0.0, avail_h / 2.0)
        # Cuadrar a un nº entero de píxeles de pantalla (margen * zoom ∈ ℤ)
        h = round(h * z) / z
        v = round(v * z) / z
        changed = not (h == self.margin_left == self.margin_right
                       and v == self.margin_top == self.margin_bottom)
        if changed:
            self.margin_left = self.margin_right = h
            self.margin_top = self.margin_bottom = v
            self._apply_view_size()
        self._recenter_view()
        if changed:
            self.update()

    def _recenter_view(self):
        """Centra el lienzo en el viewport cuando hay borde (imagen <= ventana).
        Si la imagen es mayor que la ventana (sin borde), no toca el scroll y se
        navega normal."""
        if self.margin_left == 0 and self.margin_top == 0:
            return
        sa = self._get_scroll_area()
        if sa is None:
            return
        for bar in (sa.horizontalScrollBar(), sa.verticalScrollBar()):
            if bar is not None:
                bar.setValue((bar.minimum() + bar.maximum()) // 2)

    def _apply_view_size(self):
        """Tamaño físico del widget: lienzo + márgenes, todo escalado."""
        z = self.zoom_factor
        self.setFixedSize(
            int((self.base_width + self.margin_left + self.margin_right) * z),
            int((self.base_height + self.margin_top + self.margin_bottom) * z))

    def notify_selection_changed(self):
        """Avisa a la ventana principal de que la selección cambió,
        para que active/desactive Cortar, Copiar y Deseleccionar."""
        # Cualquier cambio del trazado de selección descarta el calado anterior
        # (el borde suave dejaría de corresponder con la nueva forma).
        self.selection_soft = None
        self.selection_feather_radius = 0
        callback = getattr(self, 'selection_changed_callback', None)
        if callback:
            callback()

    def alpha_lock_active(self):
        """True si la capa activa tiene bloqueada la transparencia (y no se está
        editando su máscara). Los motores numpy que vuelcan con modo Source
        (pincel sólido, aerógrafo, clonar, sustituir color, dedo) deben
        consultarlo y aplicar el equivalente a SourceAtop por su cuenta, porque
        el modo que fija apply_selection_clip lo pisa su propio volcado."""
        layer = self.get_active_layer_obj()
        return bool(layer and getattr(layer, "alpha_locked", False)
                    and not self.mask_edit_active)

    def apply_selection_clip(self, painter):
        """Si hay una selección activa, restringe el painter a su forma:
        las herramientas solo podrán pintar DENTRO de la selección
        (comportamiento estándar de todos los editores).

        Además aplica el bloqueo de transparencia (SourceAtop) si está activo.

        Con CALADO activo, en vez del recorte duro se recorta a la caja de la
        selección AMPLIADA por la banda de calado, para que el trazo pueda entrar
        en esa banda; el confinado fino (borde suave) se hace al cerrar el trazo
        mezclando con la máscara suave (ver PaintCommand 'confine')."""
        
        layer = self.get_active_layer_obj()
        if layer and getattr(layer, "alpha_locked", False) and not self.mask_edit_active:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)

        if self.selection is None or self.selection.isEmpty():
            return
        if self.selection_soft is not None:
            from PySide6.QtCore import QRectF
            pad = int(abs(self.selection_feather_radius) * 3) + 2
            r = self.selection.boundingRect().adjusted(-pad, -pad, pad, pad)
            r = r.intersected(QRectF(0, 0, self.base_width, self.base_height))
            painter.setClipRect(r)
        else:
            painter.setClipPath(self.selection)

    def confine_to_soft(self, before, after):
        """Mezcla 'after' sobre 'before' a través de la máscara suave de selección:
        resultado = before·(1−m) + after·m. Da bordes suaves a los trazos. Si no
        hay calado, devuelve 'after' tal cual."""
        if self.selection_soft is None:
            return after
        import numpy as np
        from PySide6.QtGui import QImage
        W, H = self.base_width, self.base_height
        b = before.convertToFormat(QImage.Format_RGBA8888)
        a = after.convertToFormat(QImage.Format_RGBA8888)
        ba = np.frombuffer(b.constBits(), np.uint8).reshape(H, b.bytesPerLine())[:, :W * 4].reshape(H, W, 4).astype(np.float32)
        aa = np.frombuffer(a.constBits(), np.uint8).reshape(H, a.bytesPerLine())[:, :W * 4].reshape(H, W, 4).astype(np.float32)
        m = self.selection_soft
        mbpl = m.bytesPerLine()
        mm = (np.frombuffer(m.constBits(), np.uint8).reshape(H, mbpl)[:, :W].astype(np.float32) / 255.0)[..., None]
        out = ba * (1.0 - mm) + aa * mm
        out8 = np.ascontiguousarray(np.clip(out + 0.5, 0, 255).astype(np.uint8))
        return QImage(out8.data, W, H, 4 * W, QImage.Format_RGBA8888).copy().convertToFormat(QImage.Format_ARGB32)

    def select_all(self):
        """Selecciona el lienzo completo (Ctrl+A). Deshacible."""
        from PySide6.QtGui import QPainterPath
        from PySide6.QtCore import QRectF
        from tools.commands import SelectionChangeCommand
        path = QPainterPath()
        path.addRect(QRectF(0, 0, self.base_width, self.base_height))
        self.undo_stack.push(SelectionChangeCommand(
            self, self.selection, path, t("hist.select_all")))

    def clear_selection(self):
        """Descarta la selección activa (Ctrl+D). Deshacible."""
        if self.selection is None:
            return
        from tools.commands import SelectionChangeCommand
        self.undo_stack.push(SelectionChangeCommand(
            self, self.selection, None, t("hist.deselect"), tool_id="deselect"))

    def copy_selection(self):
        """Copia la zona seleccionada de la capa activa al portapapeles del
        sistema, recortada por la forma exacta de la selección.
        Devuelve False si no hay selección o capa válida."""
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import QRect, QPoint

        if self.selection is None or self.selection.isEmpty():
            return False
        layer_img = self.get_active_layer_image()
        if layer_img is None:
            return False

        # Recortamos al rectángulo envolvente de la selección (dentro del lienzo)
        bounds = self.selection.boundingRect().toAlignedRect()
        bounds = bounds.intersected(QRect(0, 0, self.base_width, self.base_height))
        if bounds.isEmpty():
            return False

        # Imagen del tamaño justo, con la forma de la selección como recorte:
        # lo que queda fuera de la forma (p.ej. las esquinas de una elipse)
        # se mantiene transparente
        result = QImage(bounds.size(), QImage.Format_ARGB32)
        result.fill(0)
        p = QPainter(result)
        p.translate(-bounds.topLeft())
        soft = self._soft_alpha_image()
        if soft is not None:
            # Calado: copiar todo y confinar por el alfa suave (DestinationIn).
            p.drawImage(0, 0, layer_img)
            p.setCompositionMode(QPainter.CompositionMode_DestinationIn)
            p.drawImage(0, 0, soft)
        else:
            p.setClipPath(self.selection)
            p.drawImage(0, 0, layer_img)
        p.end()

        QApplication.clipboard().setImage(result)
        # 📍 Recordar el origen para que el pegado caiga sobre el mismo sitio.
        # A nivel de clase: compartido entre todas las pestañas.
        type(self).last_copy_info = (QPoint(bounds.topLeft()), result.size())
        return True

    def cut_selection(self):
        """Corta: copia al portapapeles y borra la zona de la capa activa
        (el borrado es deshacible). Devuelve False si no había selección."""
        if not self.copy_selection():
            return False

        layer_obj = self.layers[self.active_layer_index]
        before = QImage(layer_obj.image)

        self._clear_selection_pixels(layer_obj.image)

        after = QImage(layer_obj.image)
        from tools.commands import PaintCommand
        self.undo_stack.push(PaintCommand(
            self, self.active_layer_index, before, after,
            t("hist.cut_sel"), tool_id="cut"))
        return True

    def _clear_selection_pixels(self, image):
        """Borra los píxeles de la selección en 'image': por alfa suave
        (DestinationOut) si hay calado, o recorte duro + Clear si no."""
        p = QPainter(image)
        soft = self._soft_alpha_image()
        if soft is not None:
            p.setCompositionMode(QPainter.CompositionMode_DestinationOut)
            p.drawImage(0, 0, soft)
        else:
            p.setClipPath(self.selection)
            p.setCompositionMode(QPainter.CompositionMode_Clear)
            p.fillRect(0, 0, self.base_width, self.base_height, Qt.transparent)
        p.end()

    def delete_selection(self):
        """Borra los píxeles dentro de la selección en la capa activa
        (deshacible). Devuelve False si no hay selección."""
        if self.selection is None or self.selection.isEmpty():
            return False
        layer_obj = self.layers[self.active_layer_index]
        before = QImage(layer_obj.image)
        self._clear_selection_pixels(layer_obj.image)
        after = QImage(layer_obj.image)
        from tools.commands import PaintCommand
        self.undo_stack.push(PaintCommand(
            self, self.active_layer_index, before, after,
            t("hist.del_sel"), tool_id="delete"))
        return True

    def fill_selection(self, color=None):
        """Rellena la selección con el color dado (primario por defecto) en
        la capa activa (deshacible). Devuelve False si no hay selección."""
        if self.selection is None or self.selection.isEmpty():
            return False
        if color is None:
            color = self.brush_color
        layer_obj = self.layers[self.active_layer_index]
        before = QImage(layer_obj.image)
        soft = self._soft_alpha_image()
        p = QPainter(layer_obj.image)
        p.setRenderHint(QPainter.Antialiasing, True)
        if soft is not None:
            # Calado: capa de color confinada por el alfa suave (DestinationIn).
            fill_img = QImage(self.base_width, self.base_height, QImage.Format_ARGB32)
            fill_img.fill(color)
            fp = QPainter(fill_img)
            fp.setCompositionMode(QPainter.CompositionMode_DestinationIn)
            fp.drawImage(0, 0, soft)
            fp.end()
            p.drawImage(0, 0, fill_img)
        else:
            p.fillPath(self.selection, color)
        p.end()
        after = QImage(layer_obj.image)
        from tools.commands import PaintCommand
        self.undo_stack.push(PaintCommand(
            self, self.active_layer_index, before, after,
            t("hist.fill_sel"), tool_id="fill"))
        return True

    # ---------------------------------------------------------- Calado (feather)
    def _build_soft_mask(self, radius):
        """Máscara de selección SUAVE (Grayscale8): rasteriza la selección (o
        parte del calado anterior si ya lo había) y la difumina con una gaussiana.
        Si el radio es negativo, recorta el desbordamiento hacia fuera."""
        import numpy as np
        from scipy import ndimage
        from PySide6.QtGui import QImage
        W, H = self.base_width, self.base_height
        if self.selection_soft is not None:
            m = self.selection_soft
            bpl = m.bytesPerLine()
            base = np.frombuffer(m.constBits(), np.uint8).reshape(H, bpl)[:, :W].astype(np.float32) / 255.0
        else:
            base = self._selection_mask().astype(np.float32)   # 0.0 / 1.0

        soft = ndimage.gaussian_filter(base, sigma=max(0.1, float(abs(radius))))
        if radius < 0:
            # Calado interior: remapeamos los valores para que el borde (0.5) sea 0.0,
            # creando un verdadero gradiente suave hacia el interior sin desbordar.
            soft = np.clip((soft - 0.5) * 2.0, 0.0, 1.0)

        soft8 = np.clip(soft * 255.0 + 0.5, 0, 255).astype(np.uint8)
        soft8 = np.ascontiguousarray(soft8)
        out = QImage(W, H, QImage.Format_Grayscale8)
        obpl = out.bytesPerLine()
        dst = np.frombuffer(out.bits(), np.uint8).reshape(H, obpl)
        dst[:, :W] = soft8
        return out

    def _soft_alpha_image(self):
        """ARGB del tamaño del lienzo con alfa = máscara suave de selección (rgb 0),
        para confinar operaciones por DestinationIn/DestinationOut. None si no hay
        calado activo."""
        if self.selection_soft is None:
            return None
        import numpy as np
        from PySide6.QtGui import QImage
        W, H = self.base_width, self.base_height
        m = self.selection_soft
        bpl = m.bytesPerLine()
        g = np.frombuffer(m.constBits(), np.uint8).reshape(H, bpl)[:, :W]
        argb = np.zeros((H, W, 4), np.uint8)
        argb[..., 3] = g
        argb = np.ascontiguousarray(argb)
        return QImage(argb.data, W, H, 4 * W, QImage.Format_RGBA8888).copy()

    def composite_selection_result(self, before, full_result, offset=(0, 0)):
        """Compone 'full_result' (imagen o parche YA procesado) sobre
        'before', confinado a la selección: por alfa suave si hay calado, por
        recorte duro si hay selección sin calar, o entero si no hay selección.
        'offset' indica la coordenada (x, y) donde se ubica 'full_result'."""
        from PySide6.QtGui import QImage, QPainter
        result = QImage(before)
        p = QPainter(result)
        soft = self._soft_alpha_image()
        ox, oy = offset
        if soft is not None:
            confined = full_result.convertToFormat(QImage.Format_ARGB32)
            cp = QPainter(confined)
            cp.setCompositionMode(QPainter.CompositionMode_DestinationIn)
            cp.drawImage(-ox, -oy, soft)
            cp.end()
            p.drawImage(ox, oy, confined)
        elif self.selection is not None and not self.selection.isEmpty():
            p.setClipPath(self.selection)
            p.drawImage(ox, oy, full_result)
        else:
            p.drawImage(ox, oy, full_result)
        p.end()
        return result

    def feather_selection(self, radius):
        """Aplica calado (bordes suaves) a la selección actual con el radio dado,
        en píxeles. Deshacible. Devuelve False si no hay selección o radio == 0."""
        if self.selection is None or self.selection.isEmpty() or radius == 0:
            return False
        new_soft = self._build_soft_mask(radius)
        from tools.commands import FeatherSelectionCommand
        self.undo_stack.push(FeatherSelectionCommand(
            self, self.selection_soft, new_soft,
            self.selection_feather_radius, float(radius)))
        return True

    def _selection_mask(self):
        """Rasteriza la selección actual a una máscara booleana (H, W) del tamaño
        base del lienzo. Es la base para una morfología ACOTADA por el tamaño del
        lienzo (no por la complejidad del trazado), que no se dispara."""
        import numpy as np
        from PySide6.QtGui import QImage, QPainter
        W, H = self.base_width, self.base_height
        img = QImage(W, H, QImage.Format_Grayscale8)
        img.fill(0)
        p = QPainter(img)
        p.fillPath(self.selection, Qt.white)   # sin antialias: máscara nítida
        p.end()
        bpl = img.bytesPerLine()
        buf = np.frombuffer(img.constBits(), np.uint8).reshape(H, bpl)
        return buf[:, :W] > 127

    def _mask_to_selection(self, mask):
        """Construye un QPainterPath a partir de una máscara booleana, igual que
        la varita mágica (path_from_mask: tramos vectorizados + rectángulos
        fusionados + simplified). Devuelve None si la máscara queda vacía."""
        from tools.numpy_utils import path_from_mask
        return path_from_mask(mask)

    def _refine_selection_mask(self, radius, op, direction="Completo"):
        """Aplica morfología sobre la máscara de la selección con scipy (rápida y
        acotada). op: 'expand' (dilatar), 'contract' (erosionar), 'smooth'
        (apertura de un cierre: redondea esquinas y quita salientes/entrantes
        menores que 'radius'). Devuelve el nuevo QPainterPath (o None)."""
        from scipy import ndimage as ndi
        import numpy as np
        mask = self._selection_mask()
        r = float(radius)
        
        if direction == "Completo":
            dil = lambda m: ndi.distance_transform_edt(~m) <= r      # dilatar r px
            ero = lambda m: ndi.distance_transform_edt(m) > r        # erosionar r px
        else:
            R_int = int(np.ceil(r))
            struct = np.zeros((2*R_int+1, 2*R_int+1), dtype=bool)
            if direction == "Solo Arriba": struct[0:R_int+1, R_int] = True
            elif direction == "Solo Abajo": struct[R_int:, R_int] = True
            elif direction == "Solo Izquierda": struct[R_int, 0:R_int+1] = True
            elif direction == "Solo Derecha": struct[R_int, R_int:] = True
            elif direction == "Horizontal (Izquierda y Derecha)": struct[R_int, :] = True
            elif direction == "Vertical (Arriba y Abajo)": struct[:, R_int] = True
            
            dil = lambda m: ndi.binary_dilation(m, structure=struct)
            ero = lambda m: ndi.binary_erosion(m, structure=struct)

        if op == 'expand':
            out = dil(mask)
        elif op == 'contract':
            out = ero(mask)
        else:  # smooth = apertura(cierre)
            out = dil(ero(ero(dil(mask))))
        return self._mask_to_selection(out)

    def _apply_selection_refine(self, new_sel, text):
        """Empuja el cambio de selección como un paso de deshacer; si el resultado
        queda vacío, lo trata como anular selección."""
        from tools.commands import SelectionChangeCommand
        if new_sel is not None and new_sel.isEmpty():
            new_sel = None
        self.undo_stack.push(SelectionChangeCommand(
            self, self.selection, new_sel, text, tool_id="select"))
        return True

    def _is_axis_rect(self, path):
        """True si la selección es exactamente un rectángulo alineado a los ejes
        (para expandir/contraer sin redondear sus esquinas)."""
        from PySide6.QtGui import QPainterPath
        br = path.boundingRect()
        if br.isEmpty():
            return False
        rectp = QPainterPath()
        rectp.addRect(br)
        return path.subtracted(rectp).isEmpty() and rectp.subtracted(path).isEmpty()

    def _offset_rect_or_mask(self, radius, grow, direction="Completo"):
        """Si la selección es un rectángulo, desplaza sus lados (esquinas rectas);
        si no, usa morfología euclídea por máscara (que redondea, como un disco)."""
        from PySide6.QtGui import QPainterPath
        from PySide6.QtCore import QRectF
        sel = self.selection
        if self._is_axis_rect(sel):
            r = float(radius)
            br = sel.boundingRect()
            
            dx1 = dy1 = dx2 = dy2 = 0
            if direction in ["Completo", "Horizontal (Izquierda y Derecha)", "Solo Izquierda"]: dx1 = -r
            if direction in ["Completo", "Vertical (Arriba y Abajo)", "Solo Arriba"]: dy1 = -r
            if direction in ["Completo", "Horizontal (Izquierda y Derecha)", "Solo Derecha"]: dx2 = r
            if direction in ["Completo", "Vertical (Arriba y Abajo)", "Solo Abajo"]: dy2 = r
            
            if not grow:
                dx1, dy1, dx2, dy2 = -dx1, -dy1, -dx2, -dy2
                
            if grow:
                nb = br.adjusted(dx1, dy1, dx2, dy2).intersected(
                    QRectF(0, 0, self.base_width, self.base_height))
            else:
                nb = br.adjusted(dx1, dy1, dx2, dy2)
            if nb.width() <= 0 or nb.height() <= 0:
                return None
            p = QPainterPath()
            p.addRect(nb)
            return p
        return self._refine_selection_mask(radius, 'expand' if grow else 'contract', direction)

    def expand_selection(self, radius, direction="Completo"):
        """Expande la selección 'radius' px. Deshacible."""
        if self.selection is None or self.selection.isEmpty():
            return False
        new_sel = self._offset_rect_or_mask(radius, grow=True, direction=direction)
        return self._apply_selection_refine(new_sel, t("hist.exp_sel"))

    def contract_selection(self, radius, direction="Completo"):
        """Contrae la selección 'radius' px. Deshacible."""
        if self.selection is None or self.selection.isEmpty():
            return False
        new_sel = self._offset_rect_or_mask(radius, grow=False, direction=direction)
        return self._apply_selection_refine(new_sel, t("hist.cont_sel"))

    def smooth_selection(self, radius):
        """Suaviza la selección (redondea esquinas y elimina entrantes/salientes
        menores que 'radius'). Deshacible."""
        if self.selection is None or self.selection.isEmpty():
            return False
        new_sel = self._refine_selection_mask(radius, 'smooth')
        return self._apply_selection_refine(new_sel, t("hist.smooth_sel"))

    def border_selection(self, width):
        """Convierte la selección en un anillo de 'width' px centrado en su
        contorno (mitad hacia dentro, mitad hacia fuera). Deshacible."""
        if self.selection is None or self.selection.isEmpty():
            return False
        from scipy import ndimage as ndi
        mask = self._selection_mask()
        mitad = max(float(width) / 2.0, 0.5)
        dil = ndi.distance_transform_edt(~mask) <= mitad   # dilatada mitad px
        ero = ndi.distance_transform_edt(mask) > mitad     # erosionada mitad px
        new_sel = self._mask_to_selection(dil & ~ero)
        return self._apply_selection_refine(new_sel, t("hist.border_sel"))

    def grow_selection(self):
        """Crecer (como Photoshop): extiende la selección a los píxeles
        CONTIGUOS de color parecido, usando la tolerancia de la varita.
        Deshacible."""
        return self._extend_by_similarity(contiguous=True, text=t("hist.grow_sel"))

    def select_similar(self):
        """Seleccionar parecido (como Photoshop): extiende la selección a
        TODOS los píxeles de color parecido de la imagen (no solo los
        contiguos), con la tolerancia de la varita. Deshacible."""
        return self._extend_by_similarity(contiguous=False, text=t("hist.similar_sel"))

    def _extend_by_similarity(self, contiguous, text):
        """Máscara de 'parecidos' a los colores de la selección (por canal,
        rango [mín−tol, máx+tol], como el Grow/Similar de Photoshop) sobre la
        misma muestra que usa la varita (capa activa o composición visible)."""
        if self.selection is None or self.selection.isEmpty():
            return False
        import numpy as np
        from scipy import ndimage as ndi
        from tools.numpy_utils import build_similar_mask
        sel_mask = self._selection_mask()
        if not sel_mask.any():
            return False
        if getattr(self, 'magic_wand_sample_all', False):
            image = self.render_flat_image(Qt.transparent)
        else:
            image = self.layers[self.active_layer_index].image
        tol = int(getattr(self, 'magic_wand_tolerance', 32))
        similar = build_similar_mask(image, sel_mask, tol)
        if contiguous:
            # Solo las manchas de 'parecidos' que TOCAN la selección actual
            labels, _n = ndi.label(similar)
            seeds = np.unique(labels[sel_mask])
            seeds = seeds[seeds != 0]
            region = np.isin(labels, seeds) if len(seeds) else sel_mask
        else:
            region = similar
        region = region | sel_mask
        if np.array_equal(region, sel_mask):
            return False   # nada nuevo que añadir: sin entrada en el historial
        return self._apply_selection_refine(self._mask_to_selection(region), text)

    def invert_selection(self):
        """Invierte la selección respecto al lienzo. Sin selección previa,
        equivale a seleccionar todo. Deshacible."""
        from PySide6.QtGui import QPainterPath
        full = QPainterPath()
        full.addRect(0, 0, self.base_width, self.base_height)
        if self.selection is None or self.selection.isEmpty():
            new_sel = full
        else:
            new_sel = full.subtracted(self.selection)
            if new_sel.isEmpty():
                new_sel = None
        from tools.commands import SelectionChangeCommand
        self.undo_stack.push(SelectionChangeCommand(
            self, self.selection, new_sel, t("hist.inv_sel"), tool_id="invert"))
        return True

    def copy_selection_shape(self):
        """Copia la FORMA de la selección actual a un portapapeles interno
        (compartido entre pestañas). Devuelve False si no hay selección."""
        from PySide6.QtGui import QPainterPath
        if self.selection is None or self.selection.isEmpty():
            return False
        type(self).selection_shape_clipboard = QPainterPath(self.selection)
        return True

    def paste_selection_shape(self, mode="replace"):
        """Aplica la forma de selección guardada combinándola con la actual:
        replace / add / subtract / intersect. Deshacible. Devuelve False si no
        hay forma guardada o el resultado queda vacío."""
        from PySide6.QtGui import QPainterPath
        saved = getattr(type(self), "selection_shape_clipboard", None)
        if saved is None or saved.isEmpty():
            return False
        prev = self.selection
        shape = QPainterPath(saved)
        if mode == "add" and prev is not None and not prev.isEmpty():
            result = QPainterPath(prev).united(shape); text = t("hist.paste_sel_add")
        elif mode == "subtract" and prev is not None and not prev.isEmpty():
            result = QPainterPath(prev).subtracted(shape); text = t("hist.paste_sel_sub")
        elif mode == "intersect" and prev is not None and not prev.isEmpty():
            result = QPainterPath(prev).intersected(shape); text = t("hist.paste_sel_int")
        else:
            result = shape; text = t("hist.paste_sel")
        if result is not None and result.isEmpty():
            result = None
        from tools.commands import SelectionChangeCommand
        self.undo_stack.push(SelectionChangeCommand(
            self, prev, result, text, tool_id="paste_selection"))
        return True

    def expand_canvas_for(self, needed_width, needed_height):
        """Expande el lienzo (deshacible) para que quepa el tamaño pedido,
        centrando el contenido actual. Para el pegado más grande que el lienzo.
        Devuelve False si ya cabe."""
        new_w = max(self.base_width, needed_width)
        new_h = max(self.base_height, needed_height)
        if new_w == self.base_width and new_h == self.base_height:
            return False
        offset_x = (new_w - self.base_width) // 2
        offset_y = (new_h - self.base_height) // 2
        from models.layer_commands import CanvasResizeCommand
        self.undo_stack.push(CanvasResizeCommand(
            self, new_w, new_h, offset_x, offset_y, t("hist.exp_canvas")))
        return True

    def resize_image(self, new_width, new_height, new_dpi=None):
        """Cambia tamaño y/o PPP mediante un único comando deshacible."""
        if new_width < 1 or new_height < 1:
            return False
        old_dpi = float(getattr(self, "dpi", 96.0) or 96.0)
        new_dpi = old_dpi if new_dpi is None else float(new_dpi)
        import math
        if not math.isfinite(new_dpi) or new_dpi < 1.0:
            return False
        mismo_tamano = (new_width == self.base_width
                        and new_height == self.base_height)
        if mismo_tamano and abs(new_dpi - old_dpi) < 1e-9:
            return False
        from models.layer_commands import ImageResizeCommand
        self.undo_stack.push(ImageResizeCommand(
            self, new_width, new_height, new_dpi=new_dpi))
        return True

    def crop_to_selection(self):
        """Recorta el lienzo al rectángulo envolvente de la selección
        (deshacible). Devuelve False si no hay selección válida."""
        from PySide6.QtCore import QRect
        if self.selection is None or self.selection.isEmpty():
            return False
        bounds = self.selection.boundingRect().toAlignedRect()
        bounds = bounds.intersected(QRect(0, 0, self.base_width, self.base_height))
        if bounds.isEmpty():
            return False
        # Recortar al lienzo completo no cambia nada: lo ignoramos
        if bounds.width() == self.base_width and bounds.height() == self.base_height:
            return False
        from models.layer_commands import CropCommand
        self.undo_stack.push(CropCommand(self, bounds))
        return True

    def flip_image(self, horizontal):
        """Voltea toda la imagen (todas las capas) en horizontal o vertical.
        Deshacible. Para Imagen -> Voltear."""
        from models.layer_commands import FlipCommand
        self.undo_stack.push(FlipCommand(self, horizontal))
        return True

    def rotate_image(self, degrees):
        """Gira toda la imagen (todas las capas) 90, -90 o 180 grados.
        Deshacible. 90/-90 intercambian ancho y alto. Devuelve False si el
        angulo no es valido."""
        if degrees not in (90, -90, 180):
            return False
        from models.layer_commands import RotateCommand
        self.undo_stack.push(RotateCommand(self, degrees))
        return True

    def resize_canvas(self, new_width, new_height, anchor_x=0.5, anchor_y=0.5,
                      fill_color=None):
        """Cambia el tamano del LIENZO sin escalar el contenido; el contenido
        se ancla segun (anchor_x, anchor_y) en [0,1] (0=izq/arriba, 1=der/abajo).
        Deshacible. Para Imagen -> Tamano del lienzo."""
        if new_width < 1 or new_height < 1:
            return False
        if new_width == self.base_width and new_height == self.base_height:
            return False
        offset_x = int(round((new_width - self.base_width) * anchor_x))
        offset_y = int(round((new_height - self.base_height) * anchor_y))
        from models.layer_commands import CanvasResizeCommand
        self.undo_stack.push(CanvasResizeCommand(
            self, new_width, new_height, offset_x, offset_y,
            text=t("hist.resize_canvas"), fill_color=fill_color))
        return True

    def flip_layer(self, horizontal):
        """Voltea SOLO la capa activa (mismo tamaño de lienzo). Deshacible."""
        from models.layer_commands import FlipLayerCommand
        txt = t("hist.flip_layer_h") if horizontal else t("hist.flip_layer_v")
        self.undo_stack.push(FlipLayerCommand(
            self, self.active_layer_index, horizontal, txt))
        return True

    def rotate_layer(self, degrees):
        """Gira SOLO la capa activa 90/-90/180 grados, recolocando el contenido
        centrado en el lienzo (el tamaño del lienzo NO cambia). Deshacible."""
        if degrees not in (90, -90, 180):
            return False
        from models.layer_commands import RotateLayerCommand
        labels = {90: t("hist.rot_layer_cw"), -90: t("hist.rot_layer_ccw"),
                  180: t("hist.rot_layer_180")}
        tids = {90: "rotate_cw", -90: "rotate_ccw", 180: "rotate_180"}
        self.undo_stack.push(RotateLayerCommand(
            self, self.active_layer_index, degrees, labels[degrees], tids[degrees]))
        return True

    def paste_as_new_layer(self):
        """Pega la imagen del portapapeles como una CAPA NUEVA (deshacible),
        centrada en el lienzo. Es la opción explícita del menú Edición
        (Ctrl+Shift+V); el pegado normal va a la capa activa como flotante."""
        from PySide6.QtWidgets import QApplication
        img = QApplication.clipboard().image()
        if img.isNull():
            return False
        from models.layer_commands import PasteLayerCommand
        self.undo_stack.push(PasteLayerCommand(self, img))
        return True

    def apply_project_data(self, data):
        """Aplica los datos de un proyecto .imago cargado con project_io.load_project().
        Reemplaza por completo las capas y dimensiones del lienzo."""
        self.base_width = data["width"]
        self.base_height = data["height"]
        self.setFixedSize(self.base_width, self.base_height)
        self.set_view_margins(0, 0, 0, 0)
        from PySide6.QtCore import QTimer as _QTimer
        _QTimer.singleShot(0, self._recenter_view)

        self.layers = data["layers"]
        self.active_layer_index = min(data["active_layer_index"], len(self.layers) - 1)
        self.layer_counter = data["layer_counter"]
        if data.get("dpi") is not None:
            self.dpi = float(data["dpi"])
        self.guides = list(data.get("guides", []))
        # Si el proyecto trae guías, deja las guías ACTIVAS (visibles y botón
        # marcado) para que se vean y se puedan manejar al abrirlo.
        if self.guides:
            self.show_guides = True

        self.notify_layers_changed()  # Repinta y refresca el panel de capas

    # ============================ Guías (líneas de referencia con imán) =======
    def _draw_guides(self, painter):
        """Dibuja las guías (y la que se esté arrastrando) como líneas cian de
        1 px en pantalla. Se llama con el painter ESCALADO por el zoom y
        trasladado a los márgenes, así que se usan coordenadas de lienzo y una
        pluma COSMÉTICA (ancho 0) para que no engorden al ampliar."""
        from PySide6.QtGui import QPen, QColor
        from PySide6.QtCore import QPointF
        pen = QPen(QColor(0, 180, 230))
        pen.setCosmetic(True)
        painter.setPen(pen)
        todas = list(self.guides)
        if self._pending_guide is not None:
            todas.append(self._pending_guide)
        for g in todas:
            if g['orient'] == 'h':
                y = g['pos']
                painter.drawLine(QPointF(0, y), QPointF(self.base_width, y))
            else:
                x = g['pos']
                painter.drawLine(QPointF(x, 0), QPointF(x, self.base_height))

    def add_guide(self, orient, pos):
        """Añade una guía 'h'/'v' en 'pos' (px de lienzo), recortada al lienzo."""
        limit = self.base_height if orient == 'h' else self.base_width
        pos = max(0.0, min(float(limit), float(pos)))
        self.guides.append({'orient': orient, 'pos': pos})
        self.update()

    def clear_guides(self):
        """Elimina todas las guías. Devuelve True si había alguna."""
        if not self.guides:
            return False
        self.guides = []
        self.update()
        return True

    def _notify_guides_changed(self):
        """Avisa a la ventana (si hay callback) de que las guías o el indicador
        show_guides cambiaron, para sincronizar el botón/menú de Guías."""
        cb = getattr(self, 'guides_changed_callback', None)
        if cb is not None:
            cb(self)

    def add_guide_committed(self, orient, pos):
        """Como add_guide pero registrando un comando de deshacer (crear guía)."""
        old = [dict(g) for g in self.guides]
        self.add_guide(orient, pos)
        from tools.commands import GuidesCommand
        self.undo_stack.push(GuidesCommand(self, old, self.guides, t("hist.add_guide")))

    def disable_guides(self):
        """Desactiva las guías de este documento: las borra (deshacible si las
        había) y deja show_guides en False. Lo usa el botón/menú de Guías."""
        if self.guides:
            old = [dict(g) for g in self.guides]
            from tools.commands import GuidesCommand
            self.undo_stack.push(
                GuidesCommand(self, old, [], t("hist.del_guides"),
                              old_show=True, new_show=False))
        else:
            self.show_guides = False
            self.update()
            self._notify_guides_changed()

    def guide_at(self, cx, cy, threshold_px=4.0):
        """Índice de la guía cercana al punto (cx, cy) en coords de lienzo, dentro
        de 'threshold_px' de PANTALLA (se convierte a lienzo por el zoom). O None."""
        z = self.zoom_factor or 1.0
        t = threshold_px / z
        best, best_d = None, t
        for i, g in enumerate(self.guides):
            d = abs(cy - g['pos']) if g['orient'] == 'h' else abs(cx - g['pos'])
            if d <= best_d:
                best, best_d = i, d
        return best

    # Radio de captura del imán, en PÍXELES DE PANTALLA (se convierte a píxeles de
    # lienzo dividiendo por el zoom). Lo bastante amplio para enganchar con
    # fluidez sin tener que ir despacio.
    SNAP_PX = 10.0

    def snap_x(self, x, threshold_px=None):
        """Imanta una coordenada X a la guía vertical más cercana (si la hay)."""
        if not (self.show_guides and self.guides):
            return x
        z = self.zoom_factor or 1.0
        t = (self.SNAP_PX if threshold_px is None else threshold_px) / z
        best, best_d = x, t
        for g in self.guides:
            if g['orient'] == 'v' and abs(x - g['pos']) <= best_d:
                best, best_d = g['pos'], abs(x - g['pos'])
        return best

    def snap_y(self, y, threshold_px=None):
        """Imanta una coordenada Y a la guía horizontal más cercana (si la hay)."""
        if not (self.show_guides and self.guides):
            return y
        z = self.zoom_factor or 1.0
        t = (self.SNAP_PX if threshold_px is None else threshold_px) / z
        best, best_d = y, t
        for g in self.guides:
            if g['orient'] == 'h' and abs(y - g['pos']) <= best_d:
                best, best_d = g['pos'], abs(y - g['pos'])
        return best

    def paintEvent(self, event):
        painter = QPainter(self)
        # QRect se importa AQUÍ (no dentro del branch del scroll area): al ser
        # un import local, Python lo trata como variable de TODA la función y
        # un canvas sin scroll area reventaba al usarlo más abajo (línea del
        # src_rect_int) sin haber pasado por el branch que lo importaba.
        from PySide6.QtCore import QPoint, QRect, QRectF

        z = self.zoom_factor
        ml, mt = self.margin_left, self.margin_top

        # 🚀 CLAVE DE RENDIMIENTO: pintamos SOLO la región expuesta. Nunca
        # rasterizamos la imagen entera escalada (cuyas coordenadas de
        # dispositivo, base*zoom, disparan el motor de Qt y lo cuelgan con
        # imágenes grandes a zoom alto). Aquí todo cae dentro del viewport.
        vis = event.rect()
        # 🔒 Acotar SIEMPRE a la región realmente visible del viewport. Sin
        # esto, un update() puede invalidar el widget entero (a zoom alto,
        # decenas de miles de px) y dibujaríamos con extensiones gigantescas
        # que atascan el rasterizador de Qt.
        sa = self._get_scroll_area()
        if sa is not None:
            hbar = sa.horizontalScrollBar()
            vbar = sa.verticalScrollBar()
            vp = sa.viewport()
            vis_vp = QRect(hbar.value() if hbar is not None else 0,
                           vbar.value() if vbar is not None else 0,
                           vp.width(), vp.height())
            vis = vis.intersected(vis_vp)
            if vis.isEmpty():
                painter.end()
                return

        # Fondo de los márgenes de vista (mismo gris que detrás del lienzo, para
        # que no se note el "baile" al mover una selección que desborda), solo en
        # lo visible. Color desde theme.BG_TILE.
        if self.margin_left or self.margin_top or self.margin_right or self.margin_bottom:
            painter.fillRect(vis, QColor(theme.BG_TILE))

        # Rectángulo de la imagen en coordenadas de dispositivo (widget)
        img_x = ml * z
        img_y = mt * z
        img_dev = QRectF(img_x, img_y, self.base_width * z, self.base_height * z)

        # Trozo a pintar = intersección de la imagen con lo expuesto (destino)
        draw = img_dev.intersected(QRectF(vis))
        if draw.width() > 0.0 and draw.height() > 0.0:
            # Sub-rectángulo ORIGEN correspondiente, en coordenadas de imagen
            sx = (draw.x() - img_x) / z
            sy = (draw.y() - img_y) / z
            sw = draw.width() / z
            sh = draw.height() / z

            # 1) Tablero de ajedrez, solo bajo el trozo visible (acotado)
            painter.save()
            painter.scale(z, z)
            painter.translate(ml, mt)
            self.draw_checkerboard(painter, QRectF(sx, sy, sw, sh))
            painter.restore()

            # 2) Capas: origen→destino con el destino acotado al viewport, sin
            #    coordenadas gigantes. Vecino más próximo (como antes), así que
            #    se mantiene nítido píxel a píxel al ampliar.
            src = QRectF(sx, sy, sw, sh)
            src_rect_int = src.toAlignedRect().intersected(QRect(0, 0, self.base_width, self.base_height))
            
            # --- VALIDACIÓN DE CACHÉ ---
            if not hasattr(self, "_composed_cache") or self._composed_cache.size() != QSize(self.base_width, self.base_height):
                self._composed_cache = QImage(self.base_width, self.base_height, QImage.Format.Format_ARGB32_Premultiplied)
                self._cache_valid_region = QRegion()
                self._last_cache_state = None
                
            state = []
            for layer in self.layers:
                # ✨ Huella de los efectos ACTIVOS: cambiar/añadir/quitar/reordenar
                # o togglear un efecto altera esta tupla e invalida la caché de
                # composición (el resultado del efecto se recomputa en su propia
                # caché por capa dentro de render_with_effects()).
                fx = tuple(e.fingerprint() for e in getattr(layer, "effects", ())
                           if getattr(e, "activo", False))
                mask = getattr(layer, "mask", None)
                state.append((
                    layer.image.cacheKey() if layer.image else 0,
                    # 🎭 La máscara también invalida (pintar sobre ella cambia el
                    # render); ✂️ y la marca de recorte (activarla/quitarla
                    # cambia la composición; los cambios de la BASE ya invalidan
                    # por su propio cacheKey).
                    mask.cacheKey() if mask is not None else 0,
                    getattr(layer, "clipped", False),
                    layer.opacity,
                    # 📁 Visibilidad EFECTIVA (capa Y sus grupos): así ocultar o
                    # mostrar una carpeta invalida la caché igual que la casilla
                    # de la propia capa.
                    visible_efectiva(layer),
                    getattr(layer, "blend_mode", 0),
                    getattr(layer, "alpha_locked", False),
                    fx,
                ))
            if state != getattr(self, "_last_cache_state", None):
                self._cache_valid_region = QRegion()
                self._last_cache_state = state

            # --- RECOMPOSICIÓN PARCIAL ---
            dirty_region = QRegion(src_rect_int).subtracted(self._cache_valid_region)
            if not dirty_region.isEmpty():
                p = QPainter(self._composed_cache)
                p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
                
                # Iterar el QRegion puede fallar en alguna versión de PySide6;
                # el plan B compone su rectángulo envolvente: pinta más área de
                # la cuenta pero NUNCA deja la caché marcada como válida sin
                # haberla compuesto (que dejaba zonas en blanco irreparables).
                try:
                    rects_to_draw = list(dirty_region)
                except TypeError:
                    rects_to_draw = [dirty_region.boundingRect()]

                for r in rects_to_draw:
                    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
                    p.fillRect(r, Qt.GlobalColor.transparent)
                    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
                    for i_capa, layer in enumerate(self.layers):
                        if visible_efectiva(layer):
                            # ✂️ Máscara de recorte: base = primera capa no
                            # recortada por debajo. Base oculta => la recortada
                            # no se ve; sin base (capa del fondo) => normal.
                            base = base_de_recorte(self.layers, i_capa)
                            if getattr(layer, "clipped", False) and base is not None \
                                    and not visible_efectiva(base):
                                continue
                            p.setOpacity(layer.opacity / 100.0)
                            p.setCompositionMode(getattr(layer, "blend_mode", QPainter.CompositionMode.CompositionMode_SourceOver))
                            # ✨ render_with_effects() = render base + efectos de
                            # capa (sombra...). Sin efectos devuelve el base tal
                            # cual (coste cero) y cachea por capa, así que llamarlo
                            # por cada rect sucio es un acierto de caché.
                            if base is not None:
                                # El recorte se calcula SOLO para el rect sucio
                                # (buffer temporal de su tamaño, nunca a imagen
                                # completa): la capa se pinta y se le deja el
                                # alfa de la base con DestinationIn. Coste
                                # acotado, como el resto del compositor.
                                tmp = QImage(r.size(), QImage.Format.Format_ARGB32_Premultiplied)
                                tmp.fill(0)
                                tp = QPainter(tmp)
                                tp.drawImage(QPoint(0, 0), layer.render_with_effects(), r)
                                tp.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
                                tp.drawImage(QPoint(0, 0), base.render_image(), r)
                                tp.end()
                                p.drawImage(r.topLeft(), tmp)
                            else:
                                p.drawImage(r, layer.render_with_effects(), r)
                p.end()
                self._cache_valid_region += dirty_region

            # --- DIBUJADO FINAL DESDE CACHÉ ---
            # Vecino más próximo SOLO con zoom entero (1x, 2x, 3x...): ahí es lo
            # nítido y lo que se espera para inspeccionar píxeles. Con zoom
            # FRACCIONARIO (87%, 150%...) el vecino duplica/salta filas y
            # "dienta" todos los bordes (muy visible en texto y trazos de alto
            # contraste), así que se interpola suave, como otros editores.
            _smooth = abs(z - round(z)) > 1e-3
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, _smooth)
            painter.drawImage(draw, self._composed_cache, src)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
            painter.setOpacity(1.0)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

            # 3) Overlays (rejilla, selección, previsualización) bajo el painter
            #    escalado, RECORTADOS a lo visible para acotar la rasterización.
            painter.save()
            painter.scale(z, z)
            painter.translate(ml, mt)
            # Clip = lo EXPUESTO del viewport en coords lógicas (no solo el
            # trozo de imagen): así las previsualizaciones de herramienta
            # (nudos de Línea/Curva, cajas y asas de Formas/Mover) se ven
            # también sobre los MÁRGENES de vista, que existen precisamente
            # para agarrarlas fuera del lienzo. Sigue acotado al viewport,
            # así que la rasterización no crece.
            painter.setClipRect(QRectF(vis.x() / z - ml, vis.y() / z - mt,
                                       vis.width() / z, vis.height() / z))
            # Mismo criterio que la caché: suave con zoom fraccionario (afecta
            # a las imágenes de las previsualizaciones, p. ej. el objeto
            # flotante de Mover; los trazados vectoriales no cambian).
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, _smooth)
            if self.show_grid:
                # Rejilla de píxel desde el 800% (antes 400%: con celdas de
                # 4 px la línea se comía el 25% del ancho y falseaba los
                # colores justo al comparar tonos, lo peor para pixel-art).
                if z >= 8:
                    self.draw_pixel_grid(painter, sx, sy, sw, sh)
                # Línea maestra de mosaico (Ver ▸ Mosaico de la cuadrícula):
                # útil ya al 100% para ver la estructura de un sprite sheet.
                if getattr(self, "grid_tile", 0) > 0 and z >= 1:
                    self.draw_tile_grid(painter, sx, sy, sw, sh)
            # Durante una sesión de Mover/Transformar, su draw_preview ya pinta
            # la caja con hormigas en la posición nueva: ocultamos la marquesina
            # original para que no se vean dos a la vez.
            _t = getattr(self, "current_tool", None)
            if self.selection is not None and not getattr(_t, "lifted", False):
                self.draw_selection_outline(painter, self.selection, fill=True)
            if hasattr(self.current_tool, 'draw_preview'):
                self.current_tool.draw_preview(painter)
            if self.show_guides and (self.guides or self._pending_guide):
                self._draw_guides(painter)
            painter.restore()

        painter.end()

        # Las reglas (overlay) se repintan junto al lienzo para seguir el
        # desplazamiento, el zoom y los márgenes en todo momento
        if self.ruler_overlay is not None and self.show_rulers:
            self.ruler_overlay.update()

    def draw_checkerboard(self, painter, rect):
        """Genera el patrón cuadriculado gris y blanco de transparencia"""
        tile_size = 8
        chk_layer = QImage(tile_size * 2, tile_size * 2, QImage.Format_RGB32)
        p = QPainter(chk_layer)
        p.fillRect(0, 0, tile_size, tile_size, QColor(200, 200, 200))
        p.fillRect(tile_size, 0, tile_size, tile_size, QColor(160, 160, 160))
        p.fillRect(0, tile_size, tile_size, tile_size, QColor(160, 160, 160))
        p.fillRect(tile_size, tile_size, tile_size, tile_size, QColor(200, 200, 200))
        p.end()
        
        brush = QBrush(chk_layer)
        painter.fillRect(rect, brush)

    def _adjusted_mouse_event(self, event):
        """Si hay márgenes de vista, desplaza la posición del evento para
        que las herramientas sigan recibiendo coordenadas relativas al lienzo
        real, sin enterarse de los márgenes. Así NINGUNA herramienta necesita
        cambios: su matemática (position()/zoom) sigue siendo válida."""
        if self.margin_left == 0 and self.margin_top == 0:
            return event
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtCore import QPointF
        offset = QPointF(self.margin_left * self.zoom_factor,
                         self.margin_top * self.zoom_factor)
        return QMouseEvent(event.type(), event.position() - offset,
                           event.globalPosition(), event.button(),
                           event.buttons(), event.modifiers())

    # Redirigir eventos del ratón a la herramienta activa
    def _aviso_bloqueo(self, clave):
        """Aviso de 4 s en la barra de estado al toparse con un bloqueo de capa
        (misma vía que el aviso de la goma con la transparencia bloqueada)."""
        from i18n import t
        win = self.window() if hasattr(self, "window") else None
        bar = getattr(win, 'status_bar', None)
        if bar is not None:
            bar.showMessage(t(clave), 4000)

    def mousePressEvent(self, event):
        self.setFocus()  # Asegurar que el teclado llega al lienzo al hacer clic
        # 🖱️ Botón CENTRAL: pan temporal con cualquier herramienta (estándar)
        if event.button() == Qt.MiddleButton and not getattr(self, "_middle_panning", False):
            from tools.hand_tool import HandTool
            self._middle_panning = True
            self._middle_pan_tool = HandTool(self)
            self._middle_pan_tool.panning = True
            self._middle_pan_tool.last_global = event.globalPosition()
            self._middle_pan_tool._acc_x = 0.0
            self._middle_pan_tool._acc_y = 0.0
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        # 🔒 Bloqueos por capa (Propiedades de capa): con los píxeles bloqueados
        # las herramientas de pintado no arrancan; con la posición bloqueada,
        # Mover no agarra la capa (sí un objeto ya flotante, p. ej. un pegado).
        # Puerta ÚNICA aquí: cero coste para el resto del programa.
        if event.button() == Qt.LeftButton and self.layers and not self.mask_edit_active:
            layer = self.layers[self.active_layer_index]
            tid = getattr(self.current_tool, "tool_id", "")
            if (getattr(layer, "pixels_locked", False)
                    and tid in HERRAMIENTAS_DE_PIXELES):
                self._aviso_bloqueo("status.layer_pixels_locked")
                event.accept()
                return
            if (getattr(layer, "position_locked", False) and tid == "move"
                    and not getattr(self.current_tool, "lifted", False)):
                self._aviso_bloqueo("status.layer_position_locked")
                event.accept()
                return
        # 📏 Agarrar una guía existente (con cualquier herramienta): si el clic
        # cae sobre una guía, se arrastra en vez de pintar.
        if event.button() == Qt.LeftButton and self.show_guides and self.guides:
            p = self._adjusted_mouse_event(event).position() / (self.zoom_factor or 1.0)
            idx = self.guide_at(p.x(), p.y())
            if idx is not None:
                self._dragging_guide = idx
                self._guides_drag_old = [dict(g) for g in self.guides]
                self.setCursor(Qt.SplitVCursor if self.guides[idx]['orient'] == 'h'
                               else Qt.SplitHCursor)
                event.accept()
                return
        self.current_tool.mouse_press(self._adjusted_mouse_event(event))

    def mouseMoveEvent(self, event):
        if getattr(self, "_middle_panning", False) and getattr(self, "_middle_pan_tool", None) is not None:
            self._middle_pan_tool.mouse_move(event)
            event.accept()
            return
        # 📏 Arrastrar la guía agarrada (se mueve con el cursor)
        if self._dragging_guide is not None:
            p = self._adjusted_mouse_event(event).position() / (self.zoom_factor or 1.0)
            g = self.guides[self._dragging_guide]
            g['pos'] = p.y() if g['orient'] == 'h' else p.x()
            self.update()
            event.accept()
            return
        self.current_tool.mouse_move(self._adjusted_mouse_event(event))
        self._update_guide_hover(event)
        # 📐 Informar a las reglas de la posición del cursor (coords de lienzo)
        # para la línea azul de seguimiento
        if self.ruler_overlay is not None and self.show_rulers:
            from PySide6.QtCore import QPoint
            adj = self._adjusted_mouse_event(event)
            z = self.zoom_factor
            pos = adj.position() / z
            self.ruler_overlay.set_cursor_pos(QPoint(int(pos.x()), int(pos.y())))

        # 📍 Avisar también a la barra de estado de la posición del cursor
        # (coords de lienzo), independientemente de las reglas.
        cb = getattr(self, 'cursor_moved_callback', None)
        if cb is not None:
            from PySide6.QtCore import QPoint
            adj = self._adjusted_mouse_event(event)
            p = adj.position() / self.zoom_factor
            cb(QPoint(int(p.x()), int(p.y())))

    def leaveEvent(self, event):
        # El cursor salió del lienzo: quitar la guía azul de las reglas
        if self.ruler_overlay is not None:
            self.ruler_overlay.set_cursor_pos(None)
        cb = getattr(self, 'cursor_moved_callback', None)
        if cb is not None:
            cb(None)
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton and getattr(self, "_middle_panning", False):
            self._middle_panning = False
            self._middle_pan_tool = None
            cb = getattr(self, "cursor_restore_callback", None)
            if cb:
                cb()
            event.accept()
            return
        # 📏 Soltar una guía: si quedó FUERA del lienzo, se elimina (arrastrar
        # fuera = borrar); si no, se queda en su nueva posición.
        if self._dragging_guide is not None:
            p = self._adjusted_mouse_event(event).position() / (self.zoom_factor or 1.0)
            out = (p.x() < 0 or p.y() < 0
                   or p.x() > self.base_width or p.y() > self.base_height)
            if out:
                del self.guides[self._dragging_guide]
            self._dragging_guide = None
            # Registrar el cambio en la pila de deshacer (mover o borrar guía).
            old = self._guides_drag_old
            self._guides_drag_old = None
            if old is not None and old != self.guides:
                from tools.commands import GuidesCommand
                text = t("hist.del_guide") if len(self.guides) < len(old) else t("hist.move_guide")
                self.undo_stack.push(GuidesCommand(self, old, self.guides, text))
            cb = getattr(self, "cursor_restore_callback", None)
            if cb:
                cb()
            self.update()
            event.accept()
            return
        self.current_tool.mouse_release(self._adjusted_mouse_event(event))

    def _update_guide_hover(self, event):
        """Cambia el cursor a 'mover guía' al pasar por encima de una (salvo con
        herramientas de pintar, cuyo cursor dinámico no conviene pisar)."""
        painting = {'pen', 'eraser', 'pencil', 'airbrush', 'clone', 'smudge',
                    'replace_color', 'bucket'}
        tool_id = getattr(self.current_tool, 'tool_id', None)
        if (self.show_guides and self.guides and tool_id not in painting
                and not (event.buttons() & Qt.LeftButton)):
            p = self._adjusted_mouse_event(event).position() / (self.zoom_factor or 1.0)
            idx = self.guide_at(p.x(), p.y())
            if idx is not None:
                self.setCursor(Qt.SplitVCursor if self.guides[idx]['orient'] == 'h'
                               else Qt.SplitHCursor)
                self._guide_hover = True
                return
        if getattr(self, '_guide_hover', False):
            self._guide_hover = False
            cb = getattr(self, 'cursor_restore_callback', None)
            if cb:
                cb()

    def mouseDoubleClickEvent(self, event):
        # Doble clic: lo usan herramientas como la Pluma para confirmar el trazo.
        tool = self.current_tool
        if hasattr(tool, 'mouse_double_click'):
            tool.mouse_double_click(self._adjusted_mouse_event(event))
        else:
            super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        # 🖐️ ESPACIO: activa la mano temporalmente sin cambiar de herramienta.
        # Se mantiene mientras la tecla esté pulsada; al soltar, vuelve a la
        # herramienta de antes (estándar de Photoshop/Paint.NET).
        if (event.key() == Qt.Key_Space and not event.isAutoRepeat()
                and not getattr(self, '_space_panning', False)
                and not (hasattr(self.current_tool, 'wants_space_key')
                         and self.current_tool.wants_space_key())):
            # (Si la herramienta reclama el Espacio —p. ej. una selección en
            # pleno arrastre, que lo usa para reposicionar la caja— no se
            # activa la mano temporal: la tecla le llega por key_press.)
            from tools.hand_tool import HandTool
            self._saved_tool = self.current_tool
            self._space_panning = True
            self.current_tool = HandTool(self)
            self.setCursor(Qt.OpenHandCursor)
            event.accept()
            return

        # Delegar a la herramienta activa; si no lo consume, comportamiento
        # normal (las flechas hacen scroll del lienzo como siempre)
        if hasattr(self.current_tool, 'key_press') and self.current_tool.key_press(event):
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        # Soltar ESPACIO: restaurar la herramienta que estaba activa
        if (event.key() == Qt.Key_Space and not event.isAutoRepeat()
                and getattr(self, '_space_panning', False)):
            self._space_panning = False
            self.current_tool = getattr(self, '_saved_tool', self.current_tool)
            self._saved_tool = None
            # Restaurar el cursor de la herramienta restaurada
            cb = getattr(self, 'cursor_restore_callback', None)
            if cb:
                cb()
            else:
                self.setCursor(Qt.ArrowCursor)
            event.accept()
            return

        if hasattr(self.current_tool, 'key_release') and self.current_tool.key_release(event):
            event.accept()
            return
        super().keyReleaseEvent(event)

    def _get_scroll_area(self):
        """Devuelve el QScrollArea contenedor (o None). El lienzo es hijo del
        viewport del scroll, así que subimos dos niveles."""
        viewport = self.parentWidget()
        sa = viewport.parentWidget() if viewport is not None else None
        if sa is not None and hasattr(sa, 'horizontalScrollBar'):
            return sa
        return None

    def apply_zoom_anchored(self, new_zoom, anchor_pos=None):
        """Cambia el zoom manteniendo FIJO el punto bajo 'anchor_pos' (en coords
        del widget; p.ej. la posición del ratón). Si es None, ancla en el centro
        del viewport. Reajusta el scroll del QScrollArea para que ese punto no se
        mueva, de modo que el zoom 'crece' desde el cursor y no desde la esquina
        0,0."""
        from PySide6.QtCore import QTimer
        # Tope 64×: útil para pixel art (el paintEvent solo rasteriza la región
        # visible, así que el zoom extremo no dispara el coste de repintado).
        new_zoom = max(0.1, min(float(new_zoom), 64.0))
        z_old = self.zoom_factor
        if abs(new_zoom - z_old) < 1e-9:
            return

        sa = self._get_scroll_area()
        hbar = sa.horizontalScrollBar() if sa is not None else None
        vbar = sa.verticalScrollBar() if sa is not None else None
        old_h = hbar.value() if hbar is not None else 0
        old_v = vbar.value() if vbar is not None else 0

        # Punto de anclaje en coordenadas del WIDGET (antiguo)
        if anchor_pos is None and sa is not None:
            vp = sa.viewport()
            ax = old_h + vp.width() / 2.0
            ay = old_v + vp.height() / 2.0
        elif anchor_pos is None:
            ax = self.width() / 2.0
            ay = self.height() / 2.0
        else:
            ax = float(anchor_pos.x())
            ay = float(anchor_pos.y())

        # Aplicar el zoom y el nuevo tamaño físico del widget
        self.zoom_factor = new_zoom
        self._apply_view_size()

        # Nuevo scroll: mantener el punto de anclaje en la misma posición del
        # viewport.  new = old + ax*(ratio-1)
        ratio = new_zoom / z_old
        new_h = int(round(old_h + ax * (ratio - 1.0)))
        new_v = int(round(old_v + ay * (ratio - 1.0)))
        if hbar is not None:
            hbar.setValue(new_h)
        if vbar is not None:
            vbar.setValue(new_v)
        # 2ª pasada diferida: el QScrollArea recalcula el rango de las barras de
        # forma asíncrona tras el redimensionado; reafirmamos el valor para que
        # no quede recortado a un rango antiguo (mismo patrón que los márgenes).
        def _reassert():
            if hbar is not None: hbar.setValue(new_h)
            if vbar is not None: vbar.setValue(new_v)
        QTimer.singleShot(0, _reassert)

        # El tope de los márgenes depende del zoom: que la herramienta recalcule
        if hasattr(self.current_tool, '_update_view_margins'):
            self.current_tool._update_view_margins()
        # La herramienta de texto reubica/reescala su cuadro de edición al zoom
        if hasattr(self.current_tool, 'on_zoom_changed'):
            self.current_tool.on_zoom_changed()
        # Mantener el borde clicable permanente también al cambiar el zoom
        QTimer.singleShot(0, lambda: (self.set_view_margins(0, 0, 0, 0), self._recenter_view()))
        if hasattr(self, 'zoom_changed_callback') and self.zoom_changed_callback:
            self.zoom_changed_callback()
        self.update()

    def wheelEvent(self, event):
        # 🖱️ Estándar de los editores: Ctrl+rueda = zoom; rueda sola = scroll.
        # Al ignorar el evento, el QScrollArea lo recoge y desplaza la vista.
        if not (event.modifiers() & Qt.ControlModifier):
            # Mayús+rueda = desplazamiento HORIZONTAL; rueda sola = vertical
            if event.modifiers() & Qt.ShiftModifier:
                sa = self._get_scroll_area()
                hbar = sa.horizontalScrollBar() if sa is not None else None
                if hbar is not None and hbar.maximum() > 0:
                    delta = event.angleDelta().y() or event.angleDelta().x()
                    hbar.setValue(hbar.value() - delta)
                    event.accept()
                    return
            event.ignore()
            return

        # Paso de zoom y ANCLAJE en la posición del ratón (crece desde el cursor)
        step = 1.15
        if event.angleDelta().y() > 0:
            new_zoom = self.zoom_factor * step
        else:
            new_zoom = self.zoom_factor / step
        self.apply_zoom_anchored(new_zoom, event.position())


    def sizeHint(self):
        """Le dice al QScrollArea cuánto mide el lienzo con el zoom aplicado"""
        z = self.zoom_factor
        return QSize(
            int((self.base_width + self.margin_left + self.margin_right) * z),
            int((self.base_height + self.margin_top + self.margin_bottom) * z))
