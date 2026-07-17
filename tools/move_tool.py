# tools/move_tool.py
# Herramienta unificada "Mover selección" (estilo Paint.NET):
# mover + escalar con tiradores + rotar con el asa, todo en una.
import math
from PySide6.QtGui import (QImage, QPainter, QPainterPath, QTransform,
                           QPen, QBrush, QColor, QPolygonF)
from PySide6.QtCore import Qt, QPoint, QPointF, QRect, QRectF
from i18n import t
from tools.base_tool import BaseTool, best_snap
from tools.commands import TransformCommand, NudgeMoveCommand


def _point_segment_dist(p, a, b):
    """Distancia (coords de lienzo) del punto p al segmento a-b. La usa la
    corona de rotación del cuádruple deformado."""
    abx, aby = b.x() - a.x(), b.y() - a.y()
    apx, apy = p.x() - a.x(), p.y() - a.y()
    denom = abx * abx + aby * aby
    if denom <= 1e-12:
        return math.hypot(apx, apy)
    t = max(0.0, min(1.0, (apx * abx + apy * aby) / denom))
    return math.hypot(apx - t * abx, apy - t * aby)


class MoveTool(BaseTool):
    """Mover selección: la herramienta de manipulación unificada.
    - Interior de la caja: mover (también con las flechas del teclado).
    - 8 tiradores: escalar (Shift = proporcional).
    - Asa superior: rotar (Shift = pasos de 15°).
    - CON selección: opera sobre los píxeles seleccionados.
    - SIN selección: opera sobre el contenido completo de la capa activa.

    🧬 SIN PÉRDIDA DE CALIDAD: el flotante original se conserva intacto toda
    la sesión; cada fotograma se renderiza desde él con la transformación
    acumulada (escala+rotación+traslación) en un único QTransform.

    🧲 Sesión persistente: se levanta una vez; los arrastres sucesivos
    acumulan sin morder el fondo. Cada gesto es deshacible por separado
    (los movimientos de flechas consecutivos se fusionan en una entrada).

    📋 begin_paste(): el pegado abre una sesión flotante directamente sobre
    la capa activa — la caja aparece al instante alrededor de lo pegado y
    moverlo no daña el fondo (la base es la capa de ANTES del pegado)."""

    HANDLE_SCREEN_SIZE = 8
    ROTATE_OFFSET_SCREEN = 28
    ROTATE_RING_SCREEN = 60   # Grosor de la corona de rotación alrededor de la caja
    MIN_SCALE = 0.05
    MAX_SCALE = 50.0

    # 🔷 Distorsión libre: qué esquina del cuádruple mueve cada tirador de
    # escala (mismo orden que el polígono fuente: lt, rt, rb, lb → 0..3).
    SCALE_TO_CORNER = {'lt': 0, 'rt': 1, 'rb': 2, 'lb': 3}

    NUDGE_KEYS = {
        Qt.Key_Left:  QPoint(-1, 0),
        Qt.Key_Right: QPoint(1, 0),
        Qt.Key_Up:    QPoint(0, -1),
        Qt.Key_Down:  QPoint(0, 1),
    }

    def __init__(self, canvas):
        super().__init__(canvas)
        self.tool_id = "move"
        self.history_name = t("tool.name.move_hist", default="Mover")

        # --- Sesión de flotado ---
        self.lifted = False
        self.base_image = None
        self.floating = None            # Píxeles ORIGINALES, nunca se tocan
        self.fw = 0
        self.fh = 0
        self.orig_center = QPointF(0, 0)
        self.orig_selection = None      # Path original en coords de lienzo
        self.float_origin = QPoint(0, 0)
        self.tracked_selection = None
        self.lifted_layer_index = None
        self.last_committed = None

        # --- Transformación acumulada ---
        self.sx = 1.0
        self.sy = 1.0
        self.angle = 0.0
        self.tx = 0.0
        self.ty = 0.0

        # 🔷 Distorsión libre (perspectiva) COMPUESTA con la afín: mientras es
        # None no hay deformación (solo la afín de arriba). Cuando es una lista
        # de 4 QPointF en ESPACIO OBJETO (0..fw × 0..fh, orden lt/rt/rb/lb),
        # deforma el rectángulo del flotante ANTES de la afín (display = Q·afín).
        # Así mover/escalar/girar (afines) siguen operando sobre la forma ya
        # deformada, y los 8 tiradores + rotación conviven con la distorsión.
        # Ctrl+arrastrar una esquina mueve su punto objeto (aff⁻¹ del ratón).
        self.local_corners = None
        self.press_local = None         # copia al empezar un gesto de distorsión
        self.press_affine_inv = None    # aff⁻¹ fijada al iniciar el arrastre
        self.active_corner = None

        # --- Arrastre en curso ---
        self.mode = None                # None | 'move' | 'scale' | 'rotate' | 'distort'
        self.active_handle = None
        self.image_before = None
        self.press_canvas = QPointF(0, 0)
        self.press_sx = 1.0
        self.press_sy = 1.0
        self.press_tx = 0.0
        self.press_ty = 0.0
        self.press_angle = 0.0
        self.press_mouse_angle = 0.0
        self.press_obj = QPointF(0, 0)
        self.press_inv = None           # Marco (inverso) fijado al iniciar el escalado

        # --- Ráfaga de flechas ---
        self.nudging = False
        self.press_selection = None   # Selección al iniciar el gesto (para deshacer)
        self._pushing = False         # Evita auto-resincronizarnos con nuestros propios push

        # --- 🔤 Transformación de capa de TEXTO (no destructiva): gira/mueve la
        # capa manteniéndola EDITABLE (sin rasterizar), por una vía propia
        # separada de la maquinaria de píxeles. ---
        self.text_layer = None        # capa de texto en transformación (o None)
        self.text_op = None           # None | 'rotate' | 'move'
        self.press_text_angle = 0.0
        self.press_text_origin = QPointF(0, 0)
        self.press_text_center = QPointF(0, 0)
        self.press_text_mouse_angle = 0.0
        self._text_before = None      # (ángulo, origen) al empezar el gesto (undo)
        self.text_box_dismissed = None  # capa cuya caja se anuló con Deseleccionar

        # La caja aparece al instante al activar la herramienta SOLO si ya
        # hay una selección. Sin selección, aparecerá al primer clic (mover
        # la capa completa bajo demanda). Así, abrir otra pestaña con esta
        # herramienta activa no enmarca el lienzo entero ni pide márgenes.
        sel = getattr(canvas, 'selection', None)
        if sel is not None and not sel.isEmpty():
            self._try_lift()

    # =========================================================================
    # SESIÓN DE FLOTADO
    # =========================================================================

    def _try_lift(self):
        try:
            layer = self.canvas.layers[self.canvas.active_layer_index]
            self._lift(layer)
        except (IndexError, AttributeError):
            pass

    def _session_valid(self):
        if not self.lifted:
            return False
        if self.canvas.selection is not self.tracked_selection:
            return False
        if self.canvas.active_layer_index != self.lifted_layer_index:
            return False
        layer = self.canvas.layers[self.canvas.active_layer_index]
        if layer.image is not self.last_committed:
            return False
        return True

    def _reset_params(self):
        self.sx = self.sy = 1.0
        self.angle = 0.0
        self.tx = self.ty = 0.0
        self.local_corners = None   # se descarta la deformación al re-levantar

    def _lift(self, layer):
        """Levanta selección o capa completa y reinicia la transformación."""
        # 🔤 El texto NO se levanta (píxeles): se transforma por su propia vía
        # (gira/mueve la capa manteniéndola editable). Ver _text_press.
        if getattr(layer, "is_text", False):
            return
        # 🔒 Transparencia bloqueada: mover (cortar) vaciaría el origen
        # violando el bloqueo, y el SourceAtop del recompose impediría que el
        # flotante aterrizara sobre el propio hueco (el contenido "desaparece").
        # Se bloquea el levantado (mouse_press avisa al usuario); Mover COPIA
        # sí se permite: no vacía nada y es coherente con el bloqueo.
        if not getattr(self, 'copy_mode', False) and self.canvas.alpha_lock_active():
            return
        sel = self.canvas.selection

        if sel is not None and not sel.isEmpty():
            bounds = sel.boundingRect().toAlignedRect()
            bounds = bounds.intersected(QRect(0, 0, self.canvas.base_width, self.canvas.base_height))
        else:
            bounds = None

        if bounds is not None and not bounds.isEmpty():
            self.floating = QImage(bounds.size(), QImage.Format_ARGB32)
            self.floating.fill(0)
            p = QPainter(self.floating)
            p.translate(-bounds.topLeft())
            p.setClipPath(sel)
            p.drawImage(0, 0, layer.image)
            p.end()

            self.base_image = QImage(layer.image)
            if not getattr(self, 'copy_mode', False):
                # Modo CORTAR: vaciar el origen (deja hueco). En modo COPIA
                # se omite, así el original queda intacto.
                p = QPainter(self.base_image)
                p.setClipPath(sel)
                p.setCompositionMode(QPainter.CompositionMode_Clear)
                p.fillRect(0, 0, self.canvas.base_width, self.canvas.base_height, Qt.transparent)
                p.end()

            self.float_origin = bounds.topLeft()
            self.orig_selection = QPainterPath(sel)
        else:
            self.floating = QImage(layer.image)
            if getattr(self, 'copy_mode', False):
                self.base_image = QImage(layer.image)
            else:
                self.base_image = QImage(self.canvas.base_width, self.canvas.base_height, QImage.Format_ARGB32)
                self.base_image.fill(0)
            self.float_origin = QPoint(0, 0)
            self.orig_selection = None

        self._finish_lift(sel, layer)

    def _finish_lift(self, sel, layer):
        self.fw = self.floating.width()
        self.fh = self.floating.height()
        self.orig_center = QPointF(self.float_origin.x() + self.fw / 2.0,
                                   self.float_origin.y() + self.fh / 2.0)
        self._reset_params()
        self.tracked_selection = sel
        self.lifted_layer_index = self.canvas.active_layer_index
        self.last_committed = layer.image
        self.lifted = True
        self._update_view_margins()

    def begin_paste(self, image, origin=None, history_name=t("tool.name.paste", default="Pegar"), tool_id="paste"):
        """📋 Abre una sesión flotante con una imagen, lista para mover/girar/
        escalar. Por defecto se comporta como el pegado del portapapeles
        (centrada sobre la capa activa, comando 'Pegar').

        Si se indica 'origin' (QPoint en coordenadas de lienzo), la imagen se
        coloca exactamente ahí, sin recentrar ni recortar a los bordes: lo usa
        la herramienta de Texto para soltar el texto justo donde se escribió.
        'history_name'/'tool_id' etiquetan el comando deshacible."""
        try:
            layer = self.canvas.layers[self.canvas.active_layer_index]
        except (IndexError, AttributeError):
            return False
        if image.isNull():
            return False

        self.image_before = QImage(layer.image)   # Estado pre-pegado (deshacer)
        self.press_selection = self.canvas.selection  # Selección previa al pegado
        self.base_image = QImage(layer.image)     # 🛡️ Fondo intacto bajo el flotante
        self.floating = image.convertToFormat(QImage.Format_ARGB32)

        w, h = self.floating.width(), self.floating.height()
        bw, bh = self.canvas.base_width, self.canvas.base_height
        if origin is not None:
            # 📍 Posición explícita (p. ej. el texto en su sitio): tal cual.
            px, py = int(origin.x()), int(origin.y())
        else:
            # 📍 Pegar SOBRE el origen de la copia si lo conocemos (misma imagen
            # del portapapeles); si viene de otro programa, centrado
            info = getattr(type(self.canvas), 'last_copy_info', None)
            if info is not None and info[1] == self.floating.size():
                px, py = info[0].x(), info[0].y()
            else:
                px = (bw - w) // 2
                py = (bh - h) // 2
            # Si desborda el lienzo (en cualquier eje): anclaje completo a la
            # esquina superior izquierda, estilo Paint.NET. Si cabe: dentro
            # de los límites del lienzo
            if w >= bw or h >= bh:
                px, py = 0, 0
            else:
                px = max(0, min(px, bw - w))
                py = max(0, min(py, bh - h))
        self.float_origin = QPoint(px, py)

        # La selección enmarca exactamente lo pegado
        path = QPainterPath()
        path.addRect(QRectF(px, py, self.floating.width(), self.floating.height()))
        self.canvas.selection = path
        self.orig_selection = QPainterPath(path)

        self._finish_lift(path, layer)
        self.canvas.notify_selection_changed()

        # Previsualizar y registrar el pegado como comando deshacible
        # (guarda la selección previa: al deshacer el pegado, vuelve)
        self._recompose()
        image_after = QImage(layer.image)
        self._pushing = True
        self.canvas.undo_stack.push(TransformCommand(
            self.canvas, self.canvas.active_layer_index,
            self.image_before, image_after, history_name, tool_id=tool_id,
            selection_before=self.press_selection,
            selection_after=path,
            session=self._session_snapshot()))
        self._pushing = False
        self.last_committed = layer.image
        self.tracked_selection = self.canvas.selection  # El redo() asignó el path
        self._request_update()
        return True

    # =========================================================================
    # GEOMETRÍA
    # =========================================================================

    def _center(self):
        return QPointF(self.orig_center.x() + self.tx, self.orig_center.y() + self.ty)

    def _snap_move_to_guides(self):
        """Imanta la posición del objeto a las guías al moverlo (solo traslación
        pura, sin rotar ni escalar): pega sus bordes a la guía más cercana."""
        c = self.canvas
        if (not getattr(c, 'show_guides', False) or not c.guides
                or self.angle != 0 or self.sx != 1 or self.sy != 1
                or self.local_corners is not None):
            return
        left = self.float_origin.x() + self.tx
        top = self.float_origin.y() + self.ty
        right, bottom = left + self.fw, top + self.fh
        self.tx += best_snap((c.snap_x(left) - left, c.snap_x(right) - right))
        self.ty += best_snap((c.snap_y(top) - top, c.snap_y(bottom) - bottom))

    def _affine_transform(self):
        """Transformación afín acumulada (mover/escalar/girar): mapa del espacio
        objeto (0..fw × 0..fh) al lienzo. Es la caja de siempre."""
        c = self._center()
        t = QTransform()
        t.translate(c.x(), c.y())
        t.rotate(self.angle)
        t.scale(self.sx, self.sy)
        t.translate(-self.fw / 2.0, -self.fh / 2.0)
        return t

    def _display_transform(self):
        # Todo el pipeline (recompose, márgenes, selección al confirmar) pasa
        # por aquí, así que hereda la deformación sin tocar nada más.
        aff = self._affine_transform()
        # 🔷 Distorsión: deforma el rectángulo del flotante en ESPACIO OBJETO y
        # LUEGO aplica la afín (Q·aff = aff.map(Q.map(p))). Componer la
        # deformación DEBAJO permite que escalar/girar/mover afines sigan
        # actuando sobre la forma ya deformada.
        if self.local_corners is not None:
            src = QPolygonF([QPointF(0, 0), QPointF(self.fw, 0),
                             QPointF(self.fw, self.fh), QPointF(0, self.fh)])
            dst = QPolygonF(self.local_corners)
            q = QTransform.quadToQuad(src, dst)
            if q is not None:
                return q * aff
            # Cuádruple degenerado (esquinas colapsadas): red de seguridad afín.
        return aff

    def _unrotated_frame(self):
        c = self._center()
        t = QTransform()
        t.translate(c.x(), c.y())
        t.rotate(self.angle)
        inv, _ = t.inverted()
        return inv

    def _half_extents(self):
        return (abs(self.sx) * self.fw / 2.0, abs(self.sy) * self.fh / 2.0)

    def _handles(self):
        hw, hh = self._half_extents()
        return {
            'lt': QPointF(-hw, -hh), 't': QPointF(0, -hh), 'rt': QPointF(hw, -hh),
            'l':  QPointF(-hw, 0),                          'r':  QPointF(hw, 0),
            'lb': QPointF(-hw, hh),  'b': QPointF(0, hh),  'rb': QPointF(hw, hh),
        }

    def _rotate_handle_pos(self):
        hw, hh = self._half_extents()
        offset = self.ROTATE_OFFSET_SCREEN / max(self.canvas.zoom_factor, 0.0001)
        return QPointF(0, -hh - offset)

    def _handle_object_points(self):
        """Los 8 tiradores en ESPACIO OBJETO (0..fw × 0..fh). Mapeados por
        _display_transform() caen sobre la forma actual (deformada o no)."""
        fw, fh = self.fw, self.fh
        return {
            'lt': QPointF(0, 0),      't': QPointF(fw / 2, 0),  'rt': QPointF(fw, 0),
            'l':  QPointF(0, fh / 2),                           'r':  QPointF(fw, fh / 2),
            'lb': QPointF(0, fh),     'b': QPointF(fw / 2, fh), 'rb': QPointF(fw, fh),
        }

    def _zone_at(self, canvas_point, ctrl=False):
        # Sin deformación: geometría afín exacta de siempre. Con deformación:
        # se prueba sobre el cuádruple visible. En ambos casos, Ctrl sobre una
        # ESQUINA reconvierte ese tirador de escala en distorsión.
        if self.local_corners is None:
            zone = self._zone_at_affine(canvas_point)
        else:
            zone = self._zone_at_quad(canvas_point)
        if (ctrl and isinstance(zone, tuple) and zone[0] == 'scale'
                and zone[1] in self.SCALE_TO_CORNER):
            return ('distort', self.SCALE_TO_CORNER[zone[1]])
        return zone

    def _zone_at_affine(self, canvas_point):
        inv = self._unrotated_frame()
        m = inv.map(QPointF(canvas_point))
        radius = (self.HANDLE_SCREEN_SIZE + 4) / max(self.canvas.zoom_factor, 0.0001)
        # 📦 En cajas pequeñas, el radio de captura se acota a un tercio del
        # lado menor: si no, las zonas de los 8 tiradores se solapaban y
        # cubrían TODO el interior (imposible 'mover' una selección de ~24 px
        # a zoom 1: cualquier clic caía en un tirador de escala).
        hw, hh = self._half_extents()
        radius = min(radius, max(1e-6, min(hw, hh)) * 0.66)

        rp = self._rotate_handle_pos()
        if math.hypot(m.x() - rp.x(), m.y() - rp.y()) <= radius:
            return 'rotate'

        for hid, pos in self._handles().items():
            if math.hypot(m.x() - pos.x(), m.y() - pos.y()) <= radius:
                return ('scale', hid)

        if abs(m.x()) <= hw and abs(m.y()) <= hh:
            return 'move'

        # 👑 Corona de rotación: fuera de la caja pero pegado a su borde,
        # rotar funciona igual que desde el asa (el ángulo se mide respecto
        # al centro, da igual desde dónde se agarre)
        ring = self.ROTATE_RING_SCREEN / max(self.canvas.zoom_factor, 0.0001)
        if abs(m.x()) <= hw + ring and abs(m.y()) <= hh + ring:
            return 'rotate'

        return None

    def _zone_at_quad(self, canvas_point):
        """Detección de zona sobre la forma DEFORMADA, en coords de lienzo:
        los 8 tiradores caen sobre el cuádruple; interior mueve; corona rota."""
        p = QPointF(canvas_point)
        zoom = max(self.canvas.zoom_factor, 0.0001)
        radius = (self.HANDLE_SCREEN_SIZE + 4) / zoom
        disp = self._display_transform()

        quad = [disp.map(QPointF(0, 0)), disp.map(QPointF(self.fw, 0)),
                disp.map(QPointF(self.fw, self.fh)), disp.map(QPointF(0, self.fh))]
        # Acotar el radio en cajas pequeñas (análogo a la ruta afín) usando el
        # tamaño aparente del cuádruple.
        hw = (math.hypot(*(quad[1] - quad[0]).toTuple())
              + math.hypot(*(quad[2] - quad[3]).toTuple())) / 4.0
        hh = (math.hypot(*(quad[3] - quad[0]).toTuple())
              + math.hypot(*(quad[2] - quad[1]).toTuple())) / 4.0
        radius = min(radius, max(1e-6, min(hw, hh)) * 0.66)

        for hid, opt in self._handle_object_points().items():
            hp = disp.map(opt)
            if math.hypot(p.x() - hp.x(), p.y() - hp.y()) <= radius:
                return ('scale', hid)

        poly = QPolygonF(quad)
        if poly.containsPoint(p, Qt.OddEvenFill):
            return 'move'

        # 👑 Corona de rotación: cerca de cualquier borde del cuádruple.
        ring = self.ROTATE_RING_SCREEN / zoom
        edge_dist = min(_point_segment_dist(p, quad[i], quad[(i + 1) % 4])
                        for i in range(4))
        if edge_dist <= ring:
            return 'rotate'

        return None

    def _request_update(self, full=False):
        if full:
            self.canvas.update()
            self._last_update_rect = None
            return

        zoom = max(self.canvas.zoom_factor, 0.0001)
        if getattr(self, 'lifted', False) and getattr(self, 'fw', 0) > 0:
            disp = self._display_transform()
            rect = disp.mapRect(QRectF(0, 0, self.fw, self.fh))

            ml = self.canvas.margin_left + getattr(self.canvas, 'view_margin_left', 0)
            mt = self.canvas.margin_top + getattr(self.canvas, 'view_margin_top', 0)

            # 🛡️ Una transformación proyectiva extrema (el cuádruple cruzando la
            # "línea del horizonte" al distorsionar una esquina) puede devolver
            # un mapRect infinito o gigantesco; int() de eso desborda el int de
            # QRect. Ante coordenadas no finitas o desmedidas, repintar entero.
            vals = ((rect.left() + ml) * zoom, (rect.top() + mt) * zoom,
                    rect.width() * zoom, rect.height() * zoom)
            if not all(math.isfinite(v) and abs(v) < 1e7 for v in vals):
                self.canvas.update()
                self._last_update_rect = None
                return

            r = QRect(int(vals[0]), int(vals[1]), int(vals[2]), int(vals[3])
                      ).adjusted(-80, -80, 80, 80)

            if getattr(self, '_last_update_rect', None):
                self.canvas.update(self._last_update_rect.united(r))
            else:
                self.canvas.update(r)
            self._last_update_rect = r
        else:
            self.canvas.update()

    # =========================================================================
    # 📐 FEEDBACK NUMÉRICO EN VIVO (barra de estado durante el gesto)
    # =========================================================================

    def _status_bar(self):
        win = self.canvas.window() if hasattr(self.canvas, "window") else None
        return getattr(win, 'status_bar', None)

    def _show_live_status(self, kind):
        """Muestra el dato del gesto en curso: tamaño (W×H px) al escalar,
        ángulo al rotar y desplazamiento acumulado al mover."""
        bar = self._status_bar()
        if bar is None:
            return
        if kind == 'scale':
            w = abs(self.sx) * self.fw
            h = abs(self.sy) * self.fh
            bar.showMessage(t("status.live.size", w=round(w), h=round(h)))
        elif kind == 'rotate':
            ang = self.angle % 360.0
            if ang > 180.0:
                ang -= 360.0
            bar.showMessage(t("status.live.angle", angle=f"{ang:.1f}"))
        elif kind == 'move':
            bar.showMessage(t("status.live.offset", dx=round(self.tx), dy=round(self.ty)))
        elif kind == 'distort':
            if (self.local_corners is not None and self.press_local is not None
                    and self.active_corner is not None):
                aff = self._affine_transform()
                c0 = aff.map(self.press_local[self.active_corner])
                c1 = aff.map(self.local_corners[self.active_corner])
                bar.showMessage(t("status.live.offset",
                                  dx=round(c1.x() - c0.x()), dy=round(c1.y() - c0.y())))

    def _clear_live_status(self):
        bar = self._status_bar()
        if bar is not None:
            bar.clearMessage()

    # =========================================================================
    # RATÓN
    # =========================================================================

    def mouse_press(self, event):
        if event.button() != Qt.LeftButton:
            return
            
        layer = self.canvas.layers[self.canvas.active_layer_index]
        if getattr(layer, "is_text", False):
            # 🔤 Capa de texto: girar/mover NO destructivo (sigue editable).
            if layer is self.text_box_dismissed:
                # Caja anulada con Deseleccionar: solo un clic sobre el propio
                # texto la re-arma; fuera de él no se hace nada.
                p = QPointF(event.position() / self.canvas.zoom_factor)
                if self._text_zone_at(p, layer) is None:
                    return
                self.text_box_dismissed = None
                cb = getattr(self.canvas, 'selection_changed_callback', None)
                if cb:
                    cb()
            self._text_press(event, layer)
            return

        zoom = self.canvas.zoom_factor
        p = QPointF(event.position() / zoom)

        if not self._session_valid():
            # Con la transparencia bloqueada el levantado (modo cortar) está
            # vetado: avisar aquí, al hacer clic (no al activar la herramienta).
            if (not getattr(self, 'copy_mode', False)
                    and self.canvas.alpha_lock_active()):
                from widgets.custom_titlebar import imago_information
                win = self.canvas.window() if hasattr(self.canvas, "window") else None
                imago_information(win, t("msg.move_locked.title"), t("msg.move_locked.body"))
                return
            self._try_lift()
            if not self.lifted:
                return

        layer = self.canvas.layers[self.canvas.active_layer_index]
        self.image_before = QImage(layer.image)
        self.press_selection = self.canvas.selection  # Para restaurar al deshacer
        self.press_canvas = p
        self.press_sx, self.press_sy = self.sx, self.sy
        self.press_tx, self.press_ty = self.tx, self.ty
        self.press_angle = self.angle

        ctrl = bool(event.modifiers() & Qt.ControlModifier)
        zone = self._zone_at(p, ctrl)

        if zone == 'rotate':
            self.mode = 'rotate'
            c = self._center()
            self.press_mouse_angle = math.degrees(math.atan2(p.y() - c.y(), p.x() - c.x()))
        elif isinstance(zone, tuple) and zone[0] == 'scale':
            self.mode = 'scale'
            self.active_handle = zone[1]
            inv = self._unrotated_frame()
            # ⚓ Marco FIJO del gesto: al anclar el lado opuesto, el centro se
            # desplaza durante el arrastre; medir siempre en el marco del press
            # evita que ese desplazamiento realimente la escala. Con deformación
            # activa, el ancla parte de la posición NOMINAL del tirador (no del
            # clic real, que cae sobre la esquina deformada) para que la escala
            # no dependa de la deformación.
            self.press_inv = inv
            if self.local_corners is not None:
                self.press_obj = self._handles()[zone[1]]
            else:
                self.press_obj = inv.map(p)
        elif isinstance(zone, tuple) and zone[0] == 'distort':
            # 🔷 Distorsión: mueve el punto OBJETO de la esquina. Si aún no había
            # deformación, se parte de la identidad (esquinas del rectángulo).
            self.mode = 'distort'
            self.active_corner = zone[1]
            if self.local_corners is None:
                self.local_corners = [QPointF(0, 0), QPointF(self.fw, 0),
                                      QPointF(self.fw, self.fh), QPointF(0, self.fh)]
            self.press_local = [QPointF(c) for c in self.local_corners]
            self.press_affine_inv, _ = self._affine_transform().inverted()
        elif zone == 'move':
            self.mode = 'move'
        else:
            self.mode = None

    # =========================================================================
    # 🔤 TRANSFORMACIÓN DE CAPA DE TEXTO (girar/mover, no destructivo)
    # =========================================================================

    def _active_text_layer(self):
        try:
            layer = self.canvas.layers[self.canvas.active_layer_index]
        except (IndexError, AttributeError):
            return None
        if layer is self.text_box_dismissed:
            return None   # caja anulada con Deseleccionar (ver dismiss_text_box)
        return layer if getattr(layer, "is_text", False) else None

    def text_box_active(self):
        """¿Está visible la caja de transformación de una capa de texto?
        (Lo consulta main para habilitar Deseleccionar aunque no haya
        selección real: la caja usa las mismas hormigas.)"""
        return self._active_text_layer() is not None

    def dismiss_text_box(self):
        """Anula la caja de la capa de texto activa (acción Deseleccionar):
        las hormigas desaparecen sin tocar la capa. Un clic sobre el propio
        texto (o cambiar de capa/herramienta) la vuelve a armar. Devuelve
        True si había caja que anular."""
        layer = self._active_text_layer()
        if layer is None:
            return False
        self.text_box_dismissed = layer
        self.canvas.update()
        cb = getattr(self.canvas, 'selection_changed_callback', None)
        if cb:
            cb()   # re-evaluar el estado de la acción Deseleccionar
        return True

    def _text_zone_at(self, p, layer):
        """'move' si el punto cae dentro de la caja del texto (girada), 'rotate'
        en la corona pegada a su borde, None fuera."""
        rect = layer.get_text_rect()
        inv, ok = layer.get_text_transform().inverted()
        if not ok:
            return None
        m = inv.map(p)                      # punto en el marco SIN girar
        if rect.contains(m):
            return 'move'
        ring = self.ROTATE_RING_SCREEN / max(self.canvas.zoom_factor, 0.0001)
        if rect.adjusted(-ring, -ring, ring, ring).contains(m):
            return 'rotate'
        return None

    def _text_press(self, event, layer):
        zoom = self.canvas.zoom_factor
        p = QPointF(event.position() / zoom)
        self.text_layer = layer
        self._text_before = (layer.text_angle, QPointF(layer.text_origin))
        self.press_canvas = p
        self.press_text_angle = layer.text_angle
        self.press_text_origin = QPointF(layer.text_origin)
        self.press_text_center = layer.get_text_rect().center()

        zone = self._text_zone_at(p, layer)
        if zone == 'rotate':
            self.text_op = 'rotate'
            c = self.press_text_center
            self.press_text_mouse_angle = math.degrees(
                math.atan2(p.y() - c.y(), p.x() - c.x()))
        elif zone == 'move':
            self.text_op = 'move'
        else:
            self.text_op = None

    def _text_move(self, event):
        zoom = self.canvas.zoom_factor
        p = QPointF(event.position() / zoom)
        shift = bool(event.modifiers() & Qt.ShiftModifier)

        if self.text_op == 'rotate':
            c = self.press_text_center      # el centro no se mueve al rotar
            mouse_angle = math.degrees(math.atan2(p.y() - c.y(), p.x() - c.x()))
            new_angle = self.press_text_angle + (mouse_angle - self.press_text_mouse_angle)
            if shift:
                new_angle = round(new_angle / 15.0) * 15.0
            self.text_layer.text_angle = new_angle
            self._show_live_status_text('rotate')
        elif self.text_op == 'move':
            delta = p - self.press_canvas
            self.text_layer.text_origin = self.press_text_origin + delta
            self._show_live_status_text('move')
        else:
            return
        self._touch_text()
        self.canvas.update()

    def _text_release(self):
        if self.text_layer is None:
            return
        op, layer = self.text_op, self.text_layer
        self.text_op = None
        self.text_layer = None
        self._clear_live_status()
        if op is None or self._text_before is None:
            return
        old_angle, old_origin = self._text_before
        new_angle, new_origin = layer.text_angle, QPointF(layer.text_origin)
        if old_angle == new_angle and old_origin == new_origin:
            return
        idx = self.canvas.layers.index(layer)
        text = t("hist.rotate") if op == 'rotate' else t("hist.move")
        from models.layer_commands import TextTransformCommand
        self.canvas.undo_stack.push(TextTransformCommand(
            self.canvas, idx, old_angle, old_origin, new_angle, new_origin, text))

    def _touch_text(self):
        """Fuerza nueva cacheKey del dummy de la capa de texto para que el
        compositor recomponga (el ángulo/origen no cambian layer.image)."""
        self.text_layer.image = QImage(1, 1, QImage.Format_ARGB32)
        self.text_layer.image.fill(0)

    def _text_box_path(self, layer):
        """QPainterPath de la caja del texto (girada), en coords de lienzo."""
        rect = layer.get_text_rect()
        poly = layer.get_text_transform().map(QPolygonF(rect))
        path = QPainterPath()
        path.addPolygon(poly)
        path.closeSubpath()
        return path

    def _show_live_status_text(self, kind):
        bar = self._status_bar()
        if bar is None or self.text_layer is None:
            return
        if kind == 'rotate':
            ang = self.text_layer.text_angle % 360.0
            if ang > 180.0:
                ang -= 360.0
            bar.showMessage(t("status.live.angle", angle=f"{ang:.1f}"))
        elif kind == 'move':
            o = self.text_layer.text_origin
            b = self._text_before[1] if self._text_before else o
            bar.showMessage(t("status.live.offset",
                              dx=round(o.x() - b.x()), dy=round(o.y() - b.y())))

    def mouse_move(self, event):
        zoom = self.canvas.zoom_factor
        p = QPointF(event.position() / zoom)

        # 🔤 Capa de texto: girar/mover por su propia vía.
        text_layer = self._active_text_layer()
        if text_layer is not None:
            if event.buttons() & Qt.LeftButton:
                if self.text_op is not None:
                    self._text_move(event)
            else:
                zone = self._text_zone_at(p, text_layer)
                self.canvas.setCursor(Qt.OpenHandCursor if zone == 'rotate'
                                      else Qt.SizeAllCursor if zone == 'move'
                                      else Qt.ArrowCursor)
            return

        # Sin botón: solo cursor de sobrevuelo (Ctrl anticipa la distorsión)
        if not (event.buttons() & Qt.LeftButton):
            if self.lifted:
                self._update_hover_cursor(p, bool(event.modifiers() & Qt.ControlModifier))
            return

        if self.mode is None or not self.lifted:
            return

        shift = bool(event.modifiers() & Qt.ShiftModifier)

        if self.mode == 'move':
            # Mover es afín (tx/ty): con deformación activa, el composite entero
            # se traslada igual, sin tocar los puntos objeto.
            delta = p - self.press_canvas
            self.tx = self.press_tx + delta.x()
            self.ty = self.press_ty + delta.y()
            self._snap_move_to_guides()

        elif self.mode == 'distort':
            # 🔷 Coloca la esquina visible bajo el ratón: su punto objeto es la
            # antiimagen afín del ratón (la afín está fija durante el arrastre).
            self.local_corners[self.active_corner] = self.press_affine_inv.map(p)

        elif self.mode == 'rotate':
            c = self._center()
            mouse_angle = math.degrees(math.atan2(p.y() - c.y(), p.x() - c.x()))
            new_angle = self.press_angle + (mouse_angle - self.press_mouse_angle)
            if shift:
                new_angle = round(new_angle / 15.0) * 15.0
            self.angle = new_angle

        elif self.mode == 'scale':
            m = self.press_inv.map(p)
            alt = bool(event.modifiers() & Qt.AltModifier)
            self._apply_scale_drag(m, shift, alt)

        self._show_live_status(self.mode)
        self._recompose()
        # 🟦 Publicar el rectángulo EN CURSO para que la regla siga la
        # selección en tiempo real mientras se mueve/transforma.
        if self.orig_selection is not None:
            _to_obj = QTransform().translate(-self.float_origin.x(), -self.float_origin.y())
            _disp = self._display_transform().map(_to_obj.map(self.orig_selection))
            _br = _disp.boundingRect()
            # No publicar un rectángulo no finito (distorsión proyectiva extrema).
            if all(math.isfinite(v) for v in (_br.left(), _br.top(), _br.width(), _br.height())):
                self.canvas.live_marquee = _br
            else:
                self.canvas.live_marquee = None
        else:
            self.canvas.live_marquee = None
        self._request_update()

    def _apply_scale_drag(self, m, proportional, from_center):
        """Escala respecto a un ANCLA: por defecto el lado/esquina opuesta al
        tirador queda clavada (estilo Paint.NET/Photoshop); con Alt se escala
        desde el centro (comportamiento simétrico clásico). Cruzar el ancla
        vuelve la escala negativa y VOLTEA el flotante (espejo).
        Todo se calcula desde el estado del press (sin acumular deriva)."""
        h = self.active_handle
        eps = 1e-6
        sign_x = -1 if 'l' in h else (1 if 'r' in h else 0)
        sign_y = -1 if 't' in h else (1 if 'b' in h else 0)
        hw0 = abs(self.press_sx) * self.fw / 2.0
        hh0 = abs(self.press_sy) * self.fh / 2.0
        # ⚓ Ancla en el marco del press (0,0 = centro con Alt)
        ax = 0.0 if from_center else -sign_x * hw0
        ay = 0.0 if from_center else -sign_y * hh0

        if proportional and h in ('lt', 'rt', 'lb', 'rb'):
            d0 = math.hypot(self.press_obj.x() - ax, self.press_obj.y() - ay)
            d1 = math.hypot(m.x() - ax, m.y() - ay)
            if d0 <= eps:
                return
            factor = d1 / d0
            self.sx = self._clamp(self.press_sx * factor)
            self.sy = self._clamp(self.press_sy * factor)
        else:
            if sign_x and abs(self.press_obj.x() - ax) > eps:
                self.sx = self._clamp(self.press_sx * (m.x() - ax) / (self.press_obj.x() - ax))
            if sign_y and abs(self.press_obj.y() - ay) > eps:
                self.sy = self._clamp(self.press_sy * (m.y() - ay) / (self.press_obj.y() - ay))

        if from_center:
            # Alt puede pulsarse/soltarse A MITAD de gesto: volver al centro
            self.tx, self.ty = self.press_tx, self.press_ty
            return

        # 🧭 Compensar tx/ty para que el ancla no se mueva: el centro queda
        # siempre a mitad de camino entre el ancla y el borde arrastrado.
        dx = dy = 0.0
        if sign_x:
            dx = sign_x * math.copysign(1.0, self.press_sx) * (self.fw / 2.0) * (self.sx - self.press_sx)
        if sign_y:
            dy = sign_y * math.copysign(1.0, self.press_sy) * (self.fh / 2.0) * (self.sy - self.press_sy)
        rad = math.radians(self.angle)
        cos_a, sin_a = math.cos(rad), math.sin(rad)
        self.tx = self.press_tx + dx * cos_a - dy * sin_a
        self.ty = self.press_ty + dx * sin_a + dy * cos_a

    def _clamp(self, s):
        # Conserva el SIGNO: una escala negativa voltea (espejo) el flotante
        mag = max(self.MIN_SCALE, min(abs(s), self.MAX_SCALE))
        return -mag if s < 0 else mag

    def mouse_release(self, event):
        # 🔤 Capa de texto: cerrar el gesto de girar/mover.
        if self.text_layer is not None:
            self._text_release()
            self._request_update(full=True)
            return
        if self.mode is None or not self.lifted:
            return
        gesture = self.mode
        self.mode = None
        self.active_handle = None
        self.active_corner = None
        self.canvas.live_marquee = None  # fin del gesto: la regla vuelve a canvas.selection
        self._clear_live_status()

        # 🔷 Distorsión: el estado vive en los puntos objeto (local_corners),
        # no en sx/sy/tx; los demás gestos (mover/escalar/girar) son afines.
        if gesture == 'distort':
            changed = (self.press_local is not None
                       and self.local_corners != self.press_local)
            if not changed:
                return
            self._commit(t("hist.distort"))
            self._request_update()
            return

        moved = (self.tx != self.press_tx or self.ty != self.press_ty)
        scaled = (self.sx != self.press_sx or self.sy != self.press_sy)
        rotated = (self.angle != self.press_angle)
        if not (moved or scaled or rotated):
            return

        # 📝 Texto del historial según el gesto realizado
        if scaled and not rotated and not moved:
            text = t("hist.scale")
        elif rotated and not scaled and not moved:
            text = t("hist.rotate")
        elif moved and not scaled and not rotated:
            text = t("hist.move")
        else:
            text = t("hist.transform")

        self._commit(text)
        self._request_update()

    def _commit(self, text, merge=False):
        """Consolida el estado actual como comando deshacible (que guarda
        también la selección de antes/después) y actualiza la sesión."""
        self._recompose()
        layer = self.canvas.layers[self.canvas.active_layer_index]
        image_after = QImage(layer.image)

        # 🧲 Selección transformada con el contenido (la asignará el redo())
        selection_after = None
        if self.orig_selection is not None:
            to_object = QTransform().translate(-self.float_origin.x(), -self.float_origin.y())
            selection_after = self._display_transform().map(to_object.map(self.orig_selection))

        command_class = NudgeMoveCommand if merge else TransformCommand
        self._pushing = True
        self.canvas.undo_stack.push(command_class(
            self.canvas, self.canvas.active_layer_index,
            self.image_before, image_after, text, tool_id=self.tool_id,
            selection_before=self.press_selection,
            selection_after=selection_after,
            session=self._session_snapshot()))
        self._pushing = False

        self.last_committed = layer.image
        self.tracked_selection = self.canvas.selection  # El redo() ya la asignó

    def _recompose(self):
        layer = self.canvas.layers[self.canvas.active_layer_index]
        img = QImage(self.base_image)
        p = QPainter(img)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.setRenderHint(QPainter.Antialiasing)
        
        if getattr(layer, "alpha_locked", False) and not self.canvas.mask_edit_active:
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)

        p.setTransform(self._display_transform())
        p.drawImage(0, 0, self.floating)
        p.end()
        layer.image = img
        self._update_view_margins()

    def _update_view_margins(self):
        """🖼️ Si la caja (tiradores y asa incluidos) sobresale del lienzo,
        pide al canvas márgenes de vista para que sea visible y agarrable
        sobre el fondo oscuro, con barras de desplazamiento si hace falta."""
        if not self.lifted:
            self.canvas.reset_view_margins()
            return

        zoom = max(self.canvas.zoom_factor, 0.0001)
        disp = self._display_transform()
        pts = [disp.map(QPointF(0, 0)), disp.map(QPointF(self.fw, 0)),
               disp.map(QPointF(self.fw, self.fh)), disp.map(QPointF(0, self.fh))]

        # La corona de rotación (basada en el marco afín) debe caber a la vista.
        c = self._center()
        frame = QTransform()
        frame.translate(c.x(), c.y())
        frame.rotate(self.angle)
        pts.append(frame.map(self._rotate_handle_pos()))

        pad = (self.HANDLE_SCREEN_SIZE + self.ROTATE_RING_SCREEN) / zoom
        xs = [p.x() for p in pts]
        ys = [p.y() for p in pts]

        # 🛡️ Con una distorsión proyectiva extrema (cuádruple cruzando el
        # horizonte), disp.map da puntos no finitos o clampados a valores
        # gigantescos (Qt: ~4e7); math.ceil de eso fijaría márgenes absurdos
        # (scroll disparatado). Ante coordenadas fuera de rango, no tocar nada.
        if not all(math.isfinite(v) and abs(v) < 1e6 for v in xs + ys):
            return

        left = max(0, math.ceil(-(min(xs) - pad)))
        top = max(0, math.ceil(-(min(ys) - pad)))
        right = max(0, math.ceil(max(xs) + pad - self.canvas.base_width))
        bottom = max(0, math.ceil(max(ys) + pad - self.canvas.base_height))
        self.canvas.set_view_margins(left, top, right, bottom)

    # =========================================================================
    # ⌨️ FLECHAS: mover píxel a píxel (Shift = x10); la ráfaga mantenida se
    # fusiona en UNA entrada del historial (NudgeMoveCommand).
    # =========================================================================

    def key_press(self, event):
        delta = self.NUDGE_KEYS.get(event.key())
        if delta is None:
            return False
        if self.mode is not None:
            return True  # No mezclar con un arrastre de ratón en curso

        if event.modifiers() & Qt.ShiftModifier:
            delta = QPoint(delta.x() * 10, delta.y() * 10)

        if not self.nudging:
            if not self._session_valid():
                self._try_lift()
                if not self.lifted:
                    return True
            layer = self.canvas.layers[self.canvas.active_layer_index]
            self.image_before = QImage(layer.image)
            self.press_selection = self.canvas.selection
            self.nudging = True

        self.tx += delta.x()
        self.ty += delta.y()
        self._show_live_status('move')
        self._recompose()

        # Las hormigas siguen al contenido en vivo (el commit del key_release
        # dejará la versión definitiva dentro del comando deshacible)
        if self.orig_selection is not None:
            to_object = QTransform().translate(-self.float_origin.x(), -self.float_origin.y())
            moved_path = self._display_transform().map(to_object.map(self.orig_selection))
            self.canvas.selection = moved_path
            self.tracked_selection = moved_path

        self._request_update()
        return True

    def key_release(self, event):
        if event.key() not in self.NUDGE_KEYS:
            return False
        if event.isAutoRepeat() or not self.nudging:
            return True
        self.nudging = False
        self._clear_live_status()
        self._commit(t("hist.move"), merge=True)
        return True

    # =========================================================================
    # 🔔 SINCRONIZACIÓN CON EL HISTORIAL
    # =========================================================================

    def _session_snapshot(self):
        """📦 Instantánea de la sesión actual para guardar en el comando:
        referencias compartidas (no copias) a base y flotante — todas las
        instantáneas de una sesión comparten los mismos objetos, así que el
        coste de memoria es mínimo."""
        return {
            'base': self.base_image,
            'floating': self.floating,
            'origin': QPoint(self.float_origin),
            'orig_selection': self.orig_selection,
            'params_after': (self.sx, self.sy, self.angle, self.tx, self.ty),
            'local_corners': ([QPointF(cpt) for cpt in self.local_corners]
                              if self.local_corners is not None else None),
        }

    def _restore_session(self, sess):
        """Restaura la sesión exacta de un punto del historial: mismo fondo
        pre-pegado, mismo flotante original, parámetros de ese momento."""
        self.base_image = sess['base']
        self.floating = sess['floating']
        self.float_origin = QPoint(sess['origin'])
        self.orig_selection = sess['orig_selection']
        self.fw = self.floating.width()
        self.fh = self.floating.height()
        self.orig_center = QPointF(self.float_origin.x() + self.fw / 2.0,
                                   self.float_origin.y() + self.fh / 2.0)
        (self.sx, self.sy, self.angle, self.tx, self.ty) = sess['params_after']
        saved_corners = sess.get('local_corners')
        self.local_corners = ([QPointF(cpt) for cpt in saved_corners]
                              if saved_corners else None)

        layer = self.canvas.layers[self.canvas.active_layer_index]
        self.tracked_selection = self.canvas.selection
        self.lifted_layer_index = self.canvas.active_layer_index
        self.last_committed = layer.image
        self.lifted = True
        self._update_view_margins()

    def on_history_changed(self):
        """El historial cambió (deshacer/rehacer o cualquier comando).
        Política: la caja solo se muestra automáticamente si el punto actual
        del historial corresponde a un gesto de ESTA herramienta — entonces
        restauramos su sesión exacta (la caja sigue al deshacer, sin morder
        el fondo). En cualquier otro caso la caja desaparece; reaparecerá
        cuando el usuario haga clic para manipular algo."""
        if self._pushing:
            return
        if self._session_valid():
            return

        stack = self.canvas.undo_stack
        idx = stack.index()
        cmd = stack.command(idx - 1) if idx > 0 else None
        sess = getattr(cmd, 'session', None) if cmd is not None else None

        if (sess is not None
                and getattr(cmd, 'canvas', None) is self.canvas
                and getattr(cmd, 'layer_index', -1) == self.canvas.active_layer_index
                and self.canvas.selection is not None):
            self._restore_session(sess)
        else:
            self.lifted = False
            self.canvas.reset_view_margins()
        self._request_update()

    # =========================================================================
    # CURSOR Y DIBUJO DE LA CAJA
    # =========================================================================

    def _update_hover_cursor(self, p, ctrl=False):
        zone = self._zone_at(p, ctrl)
        if zone == 'rotate':
            self.canvas.setCursor(Qt.OpenHandCursor)
        elif isinstance(zone, tuple) and zone[0] == 'distort':
            self.canvas.setCursor(Qt.CrossCursor)   # 🔷 Ctrl+esquina: distorsión
        elif isinstance(zone, tuple):
            self.canvas.setCursor(Qt.PointingHandCursor)
        elif zone == 'move':
            self.canvas.setCursor(Qt.SizeAllCursor)
        else:
            self.canvas.setCursor(Qt.ArrowCursor)

    def draw_preview(self, painter):
        # 🔤 Capa de texto: dibujar su caja (girada) para poder mover/rotar.
        text_layer = self._active_text_layer()
        if text_layer is not None:
            rect = text_layer.get_text_rect()
            if rect.isValid() and not rect.isEmpty():
                self.canvas.draw_selection_outline(painter, self._text_box_path(text_layer))
            return

        if not self.lifted:
            return
        zoom = max(self.canvas.zoom_factor, 0.0001)
        disp = self._display_transform()

        corners = [disp.map(QPointF(0, 0)), disp.map(QPointF(self.fw, 0)),
                   disp.map(QPointF(self.fw, self.fh)), disp.map(QPointF(0, self.fh))]

        # Caja con las MISMAS hormigas parpadeantes que la selección (no azul)
        box = QPainterPath()
        box.addPolygon(QPolygonF(corners))
        box.closeSubpath()
        self.canvas.draw_selection_outline(painter, box)

        # Los 8 tiradores (cuadro blanco con borde negro), sobre la forma actual:
        # se colocan mapeando sus puntos objeto con el display transform, así
        # SIEMPRE caen sobre el cuádruple (deformado o no). Con Ctrl+esquina se
        # distorsiona; sin Ctrl escalan; la rotación va por la corona del borde.
        size = self.HANDLE_SCREEN_SIZE / zoom
        pen_h = QPen(QColor(0, 0, 0))
        pen_h.setWidth(0)
        painter.setPen(pen_h)
        painter.setBrush(QBrush(QColor("#ffffff")))
        for opt in self._handle_object_points().values():
            pt = disp.map(opt)
            painter.drawRect(QRectF(pt.x() - size / 2, pt.y() - size / 2, size, size))

        # El ASA de rotación NO se dibuja: se rota desde la corona alrededor
        # de la caja (zona ampliada), con su propio cursor.