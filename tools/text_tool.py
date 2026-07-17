# tools/text_tool.py
import math
from PySide6.QtWidgets import QTextEdit, QFrame
from PySide6.QtGui import (QFont, QColor, QPainter, QPen, QImage, QTextCharFormat,
                           QTextBlockFormat, QTextCursor, QTextFormat)
from PySide6.QtCore import Qt, QPointF, QPoint
from i18n import t
from tools.base_tool import BaseTool


MOVE_MARGIN = 7   # franja arrastrable alrededor del cuadro (px de pantalla)
_MIN_BOX_W = 24   # ancho mínimo del cuadro en modo ancho fijo (px de lienzo)


class _CanvasTextEdit(QTextEdit):
    """QTextEdit hijo del marco de edición. Atajos: Esc cancela, Ctrl+Enter
    confirma. Además avisa al tool de los cambios de cursor/selección para que
    el panel de opciones refleje el formato bajo el cursor."""

    def __init__(self, tool, parent):
        super().__init__(parent)
        self._tool = tool
        self.cursorPositionChanged.connect(tool._emit_format_to_panel)
        self.selectionChanged.connect(tool._emit_format_to_panel)

    def keyPressEvent(self, event):
        k = event.key()
        if k == Qt.Key_Escape:
            self._tool.cancel_editing()
            event.accept()
            return
        if k in (Qt.Key_Return, Qt.Key_Enter) and (event.modifiers() & Qt.ControlModifier):
            self._tool.commit_editing()
            event.accept()
            return
        super().keyPressEvent(event)

    def insertFromMimeData(self, source):
        """PEGAR (Ctrl+V, Mayús+Ins o menú contextual): tras insertar, el cuadro
        pasa a modo ANCHO FIJO con tirador (el texto pegado suele ser largo y
        interesa poder encajarlo); el texto tecleado a mano no cambia nada."""
        super().insertFromMimeData(source)
        if source.hasText():
            self._tool._on_paste()


class _TextFrame(QFrame):
    """Marco que envuelve el editor. El interior es el QTextEdit (donde escribes);
    la franja del borde (MOVE_MARGIN) sirve para arrastrar y MOVER el cuadro.
    En modo ANCHO FIJO (texto pegado del portapapeles) además pinta un TIRADOR
    en el centro del borde derecho: arrastrarlo cambia el ancho del cuadro y el
    texto refluye envolviéndose (el alto se sigue autoajustando al contenido)."""

    _HANDLE = 12       # lado del tirador (px de pantalla)

    def __init__(self, tool, parent):
        super().__init__(parent)
        self._tool = tool
        self._drag = False
        self._resizing = False
        self._press_global = None
        self._start_pos = None
        self._start_box_w = 0
        self.setCursor(Qt.SizeAllCursor)
        self.setMouseTracking(True)
        self.setStyleSheet("background: transparent;")

    def _handle_rect(self):
        """Cuadradito VISUAL del tirador (o None si el cuadro es automático)."""
        if not getattr(self._tool, "box_width", 0):
            return None
        from PySide6.QtCore import QRect
        s = self._HANDLE
        return QRect(self.width() - s, (self.height() - s) // 2, s, s)

    def _in_resize_zone(self, pos):
        """¿El punto cae en la franja DERECHA del marco (zona de redimensionar)?
        Solo en modo ancho fijo; el editor tapa el interior, así que la franja
        del margen es lo único clicable del marco por ese lado."""
        if not getattr(self._tool, "box_width", 0):
            return False
        return pos.x() >= self.width() - MOVE_MARGIN - 2

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self._in_resize_zone(event.position().toPoint()):
                self._resizing = True
                self._press_global = event.globalPosition().toPoint()
                self._start_box_w = self._tool.box_width
                event.accept()
                return
            self._drag = True
            self._press_global = event.globalPosition().toPoint()
            self._start_pos = self.pos()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._resizing:
            delta = event.globalPosition().toPoint() - self._press_global
            self._tool.set_box_width_from_drag(self._start_box_w, delta.x())
            event.accept()
            return
        if self._drag:
            delta = event.globalPosition().toPoint() - self._press_global
            self.move(self._start_pos + delta)
            self._tool._on_frame_moved()
            event.accept()
            return
        # Sin botón pulsado: cursor de redimensionar sobre la franja derecha.
        if self._in_resize_zone(event.position().toPoint()):
            self.setCursor(Qt.SizeHorCursor)
        else:
            self.setCursor(Qt.SizeAllCursor)

    def mouseReleaseEvent(self, event):
        self._drag = False
        self._resizing = False
        event.accept()

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        pen = QPen(QColor(120, 120, 120))
        pen.setStyle(Qt.DashLine)
        pen.setCosmetic(True)
        p.setPen(pen)
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        hr = self._handle_rect()
        if hr is not None:
            import theme
            p.setPen(QPen(QColor(theme.BG_DARK)))
            p.setBrush(QColor(theme.ACCENT))
            p.drawRect(hr.adjusted(1, 1, -2, -2))


class TextTool(BaseTool):
    """Herramienta de Texto con cuadro de edición REAL.

    Flujo:
      1. Clic en el lienzo -> aparece un cuadro de texto editable.
      2. Se CONFIRMA (rasteriza a la capa activa) al hacer clic fuera, al cambiar
         de herramienta o con Ctrl+Enter. Enter = salto de línea. Esc CANCELA.

    Mejoras: el cuadro se puede MOVER (arrastrando su borde); el formato (fuente,
    tamaño, estilos, alineación) se aplica SOLO a la parte seleccionada -o a todo
    el texto si no hay selección-, y el panel refleja el formato bajo el cursor.
    Al confirmar, el texto se rasteriza a resolución del LIENZO (nítido sea cual
    sea el zoom) y se integra con capas, selección y deshacer/rehacer."""

    def __init__(self, canvas):
        super().__init__(canvas)
        self.tool_id = "text"
        self.history_name = t("tool.name.text")
        self.editor = None          # QTextEdit activo (o None)
        self.frame = None           # marco contenedor arrastrable
        self.start_logical = None   # esquina sup-izq del texto (coords de lienzo)
        self._edit_zoom = 1.0       # zoom con el que se está mostrando el cuadro
        self._suppress_sync = False # evita rebotes panel<->editor
        self._last_char_fmt = None  # último formato de carácter válido (color/estilo)
        self._editing_layer = None  # TextLayer en reedición (o None si es nueva)
        self._edit_before = None    # (html, origen, vertical, interletraje,
                                    #  ancho de cuadro) al empezar
        self._editor_spacing_active = False  # hay interletraje visual en el editor
        self.box_width = 0          # ⇲ ancho FIJO del cuadro en px de LIENZO
                                    # (0 = automático; >0 al pegar del portapapeles)

    # ------------------------------------------------------------------
    # Ratón: un clic confirma lo anterior y abre un cuadro nuevo
    # ------------------------------------------------------------------
    def mouse_press(self, event):
        if event.button() != Qt.LeftButton:
            return
        
        # Si estábamos editando, el clic confirma el texto y terminamos la acción.
        if self.editor is not None:
            self.commit_editing()
            return
            
        pt = (event.position() / self.canvas.zoom_factor)
        logical_pt = QPointF(pt.x(), pt.y())

        # 🔎 Hit-test de TODAS las capas de texto visibles, de arriba abajo
        # (antes solo se reeditaba si su capa ya era la activa): editar
        # cualquier texto es UN clic; la capa tocada pasa a ser la activa.
        layer = None
        for idx in range(len(self.canvas.layers) - 1, -1, -1):
            capa = self.canvas.layers[idx]
            if (getattr(capa, "is_text", False) and capa.visible
                    and capa.contains_point(logical_pt)):
                if idx != self.canvas.active_layer_index:
                    self.canvas.active_layer_index = idx
                    self.canvas.notify_layers_changed()
                layer = capa
                break

        if layer is not None:
            # Editar la TextLayer tocada. La capa NO se oculta: su render sigue
            # visible y el editor va volcando los cambios EN VIVO (ver
            # _update_live_layer), así se ven efectos de capa, interletraje,
            # vertical y giro mientras se edita. La instantánea permite
            # cancelar (Esc) y es el "antes" del comando de deshacer.
            self._editing_layer = layer
            self._edit_before = (layer.text_html, QPointF(layer.text_origin),
                                 layer.text_vertical, layer.text_spacing,
                                 getattr(layer, "text_box_width", 0))
            # El panel (vertical + interletraje) refleja el estado de esta capa.
            self.canvas.text_vertical = getattr(layer, "text_vertical", False)
            self.canvas.text_spacing = getattr(layer, "text_spacing", 0)
            # Un texto de ancho fijo (pegado) reabre con su tirador.
            self.box_width = int(getattr(layer, "text_box_width", 0))
            self._start_editor(layer.text_origin, html=layer.text_html)
        else:
            # Crear un texto nuevo (cuadro automático, como siempre)
            self._editing_layer = None
            self._edit_before = None
            self.box_width = 0
            self._start_editor(logical_pt)

    # ------------------------------------------------------------------
    # Fuente/formato base desde el lienzo (panel de opciones)
    # ------------------------------------------------------------------
    def _font(self):
        c = self.canvas
        zoom = c.zoom_factor or 1.0
        family = getattr(c, "text_family", "Arial")
        size = getattr(c, "text_size", 24)
        f = QFont(family)
        f.setPixelSize(max(1, round(size * zoom)))
        f.setBold(getattr(c, "text_bold", False))
        f.setItalic(getattr(c, "text_italic", False))
        f.setUnderline(getattr(c, "text_underline", False))
        f.setStrikeOut(getattr(c, "text_strike", False))
        return f

    def _align_flag(self, a=None):
        if a is None:
            a = getattr(self.canvas, "text_align", "left")
        if a == "center":
            return Qt.AlignHCenter
        if a == "right":
            return Qt.AlignRight
        if a == "justify":
            return Qt.AlignJustify
        return Qt.AlignLeft

    def _align_str(self, flag):
        if flag & Qt.AlignHCenter:
            return "center"
        if flag & Qt.AlignRight:
            return "right"
        if flag & Qt.AlignJustify:
            return "justify"
        return "left"

    def _text_color(self):
        return QColor(getattr(self.canvas, "brush_color", QColor(Qt.black)))

    # ------------------------------------------------------------------
    # Aplicación de formato: SOLO a la selección, o a TODO si no hay selección
    # ------------------------------------------------------------------
    def _merge_char(self, fmt):
        ed = self.editor
        if ed is None:
            return
        ed.blockSignals(True)
        cur = ed.textCursor()
        if cur.hasSelection():
            cur.mergeCharFormat(fmt)
        else:
            allc = QTextCursor(ed.document())
            allc.select(QTextCursor.Document)
            allc.mergeCharFormat(fmt)
            ed.mergeCurrentCharFormat(fmt)   # también para lo que se escriba
        ed.blockSignals(False)
        self._autoresize()
        self._remember_fmt()

    def _merge_block(self, bfmt):
        ed = self.editor
        if ed is None:
            return
        ed.blockSignals(True)
        cur = ed.textCursor()
        if cur.hasSelection():
            cur.mergeBlockFormat(bfmt)
        else:
            allc = QTextCursor(ed.document())
            allc.select(QTextCursor.Document)
            allc.mergeBlockFormat(bfmt)
        ed.blockSignals(False)
        self._autoresize()

    def apply_family(self, family):
        fmt = QTextCharFormat()
        fmt.setFontFamily(family)
        self._merge_char(fmt)

    def apply_size(self, size):
        z = self.canvas.zoom_factor or 1.0
        fmt = QTextCharFormat()
        # OJO: FontPixelSize debe ser INT. Con float, PySide6 6.11 lo acepta en
        # vivo (la edición se ve bien) pero toHtml() exporta "font-size:0px" y
        # el texto cometido a la TextLayer pierde su tamaño real.
        fmt.setProperty(QTextFormat.FontPixelSize, int(max(1, round(size * z))))
        self._merge_char(fmt)

    def apply_bold(self, b):
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Bold if b else QFont.Normal)
        self._merge_char(fmt)

    def apply_italic(self, b):
        fmt = QTextCharFormat()
        fmt.setFontItalic(bool(b))
        self._merge_char(fmt)

    def apply_underline(self, b):
        fmt = QTextCharFormat()
        fmt.setFontUnderline(bool(b))
        self._merge_char(fmt)

    def apply_strike(self, b):
        fmt = QTextCharFormat()
        fmt.setFontStrikeOut(bool(b))
        self._merge_char(fmt)

    def apply_align(self, a):
        bfmt = QTextBlockFormat()
        bfmt.setAlignment(self._align_flag(a))
        self._merge_block(bfmt)

    def apply_color(self, color):
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        self._merge_char(fmt)

    def apply_format_from_canvas(self):
        """Vuelca TODA la configuración del panel al cuadro. Se usa al CREAR el
        cuadro (texto vacío). Mientras editas, el panel usa los apply_* granulares
        para no pisar el formato por selección."""
        if self.editor is None:
            return
        f = self._font()
        ed = self.editor
        ed.blockSignals(True)
        ed.setFont(f)
        ed.document().setDefaultFont(f)
        cursor = ed.textCursor()
        allc = QTextCursor(ed.document())
        allc.select(QTextCursor.Document)
        fmt = QTextCharFormat()
        fmt.setFont(f)
        fmt.setForeground(self._text_color())
        allc.mergeCharFormat(fmt)
        bfmt = QTextBlockFormat()
        bfmt.setAlignment(self._align_flag())
        allc.mergeBlockFormat(bfmt)
        ed.setTextCursor(cursor)
        ed.setCurrentCharFormat(fmt)
        ed.blockSignals(False)
        self._autoresize()
        self._remember_fmt()

    # ------------------------------------------------------------------
    # Sincronización inversa: el panel refleja el formato bajo el cursor
    # ------------------------------------------------------------------
    def _emit_format_to_panel(self):
        if self.editor is None or self._suppress_sync:
            return
        ed = self.editor
        self._remember_fmt()   # recordar color/estilo mientras hay texto
        fmt = ed.currentCharFormat()
        f = fmt.font()
        z = self.canvas.zoom_factor or 1.0
        ps = f.pixelSize()
        if ps <= 0:
            ps = round(getattr(self.canvas, "text_size", 24) * z)
        info = {
            "family": f.family(),
            "size": int(max(1, round(ps / z))),
            "bold": f.bold(),
            "italic": f.italic(),
            "underline": f.underline(),
            "strike": f.strikeOut(),
            "align": self._align_str(ed.alignment()),
            # Orientación de la CAPA (no del carácter): la lee del lienzo, que se
            # sincronizó al empezar a editar y la actualiza el toggle del panel.
            "vertical": bool(getattr(self.canvas, "text_vertical", False)),
            "spacing": int(getattr(self.canvas, "text_spacing", 0)),
        }
        win = self.canvas.window() if hasattr(self.canvas, "window") else None
        if win is not None and hasattr(win, "sync_text_panel"):
            win.sync_text_panel(info)

    # ------------------------------------------------------------------
    # Autoajuste del cuadro al contenido
    # ------------------------------------------------------------------
    def _autoresize(self):
        if self.editor is None:
            return
        doc = self.editor.document()
        if self.box_width:
            # ⇲ Ancho FIJO (texto pegado): el ancho lo manda el tirador y el
            # texto REFLUYE envolviéndose; solo el ALTO se autoajusta. El modo
            # FixedPixelWidth deja el textWidth del documento en manos del
            # editor (con NoWrap lo repondría a -1 en cualquier relayout).
            z = self._edit_zoom or 1.0
            w = max(28, int(round(self.box_width * z)))
            self.editor.setLineWrapMode(QTextEdit.FixedPixelWidth)
            self.editor.setLineWrapColumnOrWidth(w)
            h = int(doc.size().height()) + 6
            self.editor.setFixedSize(w, max(22, h))
        else:
            # Quitamos el límite para medir el ancho real sin restricciones
            doc.setTextWidth(-1)
            ideal_w = doc.idealWidth()
            # Le aplicamos el ancho ideal para que la alineación Center/Right funcione respecto a la línea más larga
            doc.setTextWidth(ideal_w)

            w = int(ideal_w) + 14
            h = int(doc.size().height()) + 6
            self.editor.setFixedSize(max(28, w), max(22, h))
        if self.frame is not None:
            self.frame.setFixedSize(self.editor.width() + 2 * MOVE_MARGIN,
                                    self.editor.height() + 2 * MOVE_MARGIN)
        self._update_live_layer()

    # ------------------------------------------------------------------
    # ⇲ Ancho fijo del cuadro (texto PEGADO del portapapeles)
    # ------------------------------------------------------------------
    def _on_paste(self):
        """Al pegar del portapapeles, el cuadro pasa a modo ANCHO FIJO con
        tirador. El ancho inicial es el del contenido, ACOTADO a lo que queda
        de lienzo por la derecha (un pegado largo no crea un cuadro
        kilométrico: refluye). El texto tecleado no pasa por aquí."""
        if self.editor is None or self.box_width:
            return
        z = self._edit_zoom or 1.0
        doc = self.editor.document()
        doc.setTextWidth(-1)
        ideal = doc.idealWidth() / z + 2          # contenido, en px de lienzo
        avail = self.canvas.base_width - self.start_logical.x() - 2
        self.box_width = int(round(max(_MIN_BOX_W, min(ideal, avail))))
        self._autoresize()
        if self.frame is not None:
            self.frame.update()   # aparece el tirador

    def set_box_width_from_drag(self, start_w, delta_x_screen):
        """Arrastre del tirador: nuevo ancho = el del press + el delta del ratón
        (pasado a px de lienzo). El alto se recalcula solo (_autoresize)."""
        z = self._edit_zoom or 1.0
        self.box_width = int(round(max(_MIN_BOX_W, start_w + delta_x_screen / z)))
        self._autoresize()
        if self.frame is not None:
            self.frame.update()

    # ------------------------------------------------------------------
    # ✨ Preview EN VIVO al reeditar una capa de texto
    # ------------------------------------------------------------------
    def _update_live_layer(self):
        """Vuelca al instante el contenido del editor a la capa en reedición
        (texto, posición, vertical, interletraje): el lienzo enseña el render
        REAL —con efectos de capa, giro, interletraje y vertical— mientras se
        escribe. Al confirmar, el comando de deshacer usa la instantánea de
        _edit_before; Esc la repone. Para un texto NUEVO no hay capa aún: ahí
        el preview es el propio editor (con su interletraje visual)."""
        layer = self._editing_layer
        if layer is None or self.editor is None:
            return
        html = self._doc_at_canvas_resolution_from(self.editor).toHtml()
        layer.set_text(html, QPointF(self.start_logical),
                       vertical=bool(getattr(self.canvas, "text_vertical", False)),
                       spacing=int(getattr(self.canvas, "text_spacing", 0)),
                       box_width=self.box_width)
        self.canvas.update()

    def apply_vertical(self, value):
        """Toggle VERTICAL con el cuadro abierto: en el editor se sigue
        escribiendo en horizontal, pero la capa en reedición enseña el apilado
        vertical EN VIVO. El interletraje visual del editor solo aplica en
        horizontal (en vertical el hueco lo enseña el render de la capa)."""
        self._refresh_editor_spacing()
        self._update_live_layer()

    def apply_spacing(self, value):
        """Interletraje con el cuadro abierto: se aplica visualmente al editor
        (toHtml no lo conserva, así que no ensucia el html guardado) y la capa
        en reedición lo enseña además con su render real."""
        self._refresh_editor_spacing()
        self._update_live_layer()

    def _refresh_editor_spacing(self):
        """Reaplica al editor el interletraje visual vigente: todos los
        caracteres MENOS el último (como _apply_letter_spacing de la capa, para
        que las letras del editor y las del render coincidan), escalado por el
        zoom como los tamaños. En vertical (o interletraje 0) lo limpia."""
        ed = self.editor
        if ed is None:
            return
        spacing = int(getattr(self.canvas, "text_spacing", 0))
        if getattr(self.canvas, "text_vertical", False):
            spacing = 0
        # Sin interletraje y sin restos que limpiar: no tocar el documento (cada
        # merge ensucia el deshacer interno del editor).
        if spacing == 0 and not self._editor_spacing_active:
            return
        self._editor_spacing_active = spacing != 0
        z = self.canvas.zoom_factor or 1.0
        ed.blockSignals(True)
        fmt = self._merge_doc_spacing(ed.document(), float(spacing) * z)
        ed.mergeCurrentCharFormat(fmt)   # lo que se escriba a continuación
        ed.blockSignals(False)
        self._autoresize()

    @staticmethod
    def _merge_doc_spacing(doc, spacing):
        """Aplica un interletraje ABSOLUTO a un documento: todos los caracteres
        MENOS el último, que queda sin hueco final (el letter-spacing se añade
        después de cada carácter; en el último sobra y ensancha la caja — el
        mismo criterio que _apply_letter_spacing de la capa). Devuelve el
        formato usado (para mergeCurrentCharFormat del editor)."""
        from PySide6.QtGui import QFont as _QFont
        fmt = QTextCharFormat()
        fmt.setFontLetterSpacingType(_QFont.AbsoluteSpacing)
        fmt.setFontLetterSpacing(float(spacing))
        sin = QTextCharFormat()
        sin.setFontLetterSpacingType(_QFont.AbsoluteSpacing)
        sin.setFontLetterSpacing(0.0)
        total = doc.characterCount()
        if total > 2:
            cur = QTextCursor(doc)
            cur.setPosition(0)
            cur.setPosition(total - 2, QTextCursor.KeepAnchor)
            cur.mergeCharFormat(fmt)
        if total > 1:
            last = QTextCursor(doc)
            last.setPosition(max(0, total - 2))
            last.setPosition(total - 1, QTextCursor.KeepAnchor)
            last.mergeCharFormat(sin)
        return fmt

    def _remember_fmt(self):
        """Guarda el formato de carácter actual SI tiene un color de primer plano
        real (no NoBrush), para poder reponerlo si el usuario vacía el campo."""
        ed = self.editor
        if ed is None:
            return
        cf = ed.currentCharFormat()
        if cf.foreground().style() != Qt.NoBrush:
            self._last_char_fmt = QTextCharFormat(cf)

    def _on_text_changed(self):
        """Al cambiar el texto: reajusta la caja y, si el documento quedó VACÍO,
        repone el último formato de carácter. Motivo: al borrar TODO, Qt resetea
        el formato de entrada (color -> NoBrush) y lo siguiente que se escribe
        saldría con el color por defecto del tema (casi blanco), sin poder
        cambiarlo. Reponerlo mantiene el color/estilo que se venía usando."""
        ed = self.editor
        if ed is not None and ed.toPlainText() == "" and self._last_char_fmt is not None:
            ed.blockSignals(True)
            ed.setCurrentCharFormat(QTextCharFormat(self._last_char_fmt))
            ed.blockSignals(False)
        # Con interletraje activo, reaplicarlo: el "último carácter sin hueco"
        # cambia de sitio al escribir/borrar (termina llamando a _autoresize).
        self._refresh_editor_spacing()
        self._autoresize()

    # ------------------------------------------------------------------
    # Crear / confirmar / cancelar el cuadro
    # ------------------------------------------------------------------
    def _start_editor(self, logical_pt, html=None):
        self.start_logical = logical_pt
        self._edit_zoom = self.canvas.zoom_factor or 1.0
        self._on_mask = self.canvas.paint_on_mask()

        frame = _TextFrame(self, self.canvas)
        ed = _CanvasTextEdit(self, frame)
        ed.move(MOVE_MARGIN, MOVE_MARGIN)
        ed.setFrameStyle(QFrame.NoFrame)
        ed.setLineWrapMode(QTextEdit.NoWrap)
        ed.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        ed.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        ed.setViewportMargins(0, 0, 0, 0)
        ed.document().setDocumentMargin(0)
        ed.viewport().setAutoFillBackground(False)
        ed.setStyleSheet("QTextEdit { background: transparent; border: none; }")
        ed.textChanged.connect(self._on_text_changed)
        self.editor = ed
        self.frame = frame
        self._last_char_fmt = None
        self._editor_spacing_active = False

        if html:
            ed.setHtml(html)
            # El html se guarda a resolución de LIENZO; al editar hay que mostrarlo
            # a resolución de PANTALLA (×zoom), inverso de commit_editing. Sin esto,
            # reeditar con zoom != 100% mostraría el texto más pequeño de lo real.
            z = self.canvas.zoom_factor or 1.0
            if abs(z - 1.0) > 1e-9:
                ed.blockSignals(True)
                self._scale_doc_fonts(ed.document(), z)
                ed.blockSignals(False)
            # Interletraje visual del editor (si la capa reeditada lo traía),
            # para que sus letras coincidan con las del render en vivo.
            self._refresh_editor_spacing()
            from PySide6.QtGui import QTextCursor
            cursor = ed.textCursor()
            cursor.movePosition(QTextCursor.End)
            ed.setTextCursor(cursor)
        else:
            self.apply_format_from_canvas()
            
        self._reposition_frame()
        self._autoresize()
        frame.show()
        ed.show()
        ed.setFocus()

    def _reposition_frame(self):
        """Coloca el marco según start_logical y el zoom de edición."""
        if self.frame is None:
            return
        z = self._edit_zoom or 1.0
        wx = int(round((self.canvas.margin_left + self.start_logical.x()) * z)) - MOVE_MARGIN
        wy = int(round((self.canvas.margin_top + self.start_logical.y()) * z)) - MOVE_MARGIN
        self.frame.move(wx, wy)

    def _on_frame_moved(self):
        """Tras arrastrar el marco, recalcula la posición lógica del texto."""
        if self.frame is None:
            return
        z = self._edit_zoom or 1.0
        ex = self.frame.x() + MOVE_MARGIN
        ey = self.frame.y() + MOVE_MARGIN
        self.start_logical = QPointF(ex / z - self.canvas.margin_left,
                                     ey / z - self.canvas.margin_top)
        self._update_live_layer()   # los efectos/giro siguen al cuadro en vivo

    def on_zoom_changed(self):
        """Si cambia el zoom con el cuadro abierto, reescala las fuentes y
        reubica el marco para que el texto siga cuadrando con el lienzo."""
        if self.editor is None:
            return
        new_z = self.canvas.zoom_factor or 1.0
        old_z = self._edit_zoom or 1.0
        if new_z == old_z:
            return
        factor = new_z / old_z
        ed = self.editor
        ed.blockSignals(True)
        self._scale_doc_fonts(ed.document(), factor)
        ed.blockSignals(False)
        self._edit_zoom = new_z
        self._autoresize()
        self._reposition_frame()

    @staticmethod
    def _iter_fragments(doc):
        """Lista de (posición, longitud, pixelSize) agrupando rangos contiguos
        con el mismo tamaño. Recorre por posiciones (sin el iterador de fragmentos
        de Qt, que no es fiable en todas las versiones de PySide)."""
        out = []
        total = doc.characterCount()
        start = 0
        prev = None
        pos = 0
        while pos < total - 1:
            c = QTextCursor(doc)
            c.setPosition(pos)
            c.setPosition(pos + 1, QTextCursor.KeepAnchor)
            ps = c.charFormat().font().pixelSize()
            ps = ps if ps > 0 else 1
            if prev is None:
                prev = ps
                start = pos
            elif ps != prev:
                out.append((start, pos - start, prev))
                start = pos
                prev = ps
            pos += 1
        if prev is not None and pos > start:
            out.append((start, pos - start, prev))
        return out

    def commit_editing(self, *args):
        """Rasteriza el texto a la capa activa y registra el deshacer. Cuadro
        vacío -> se descarta sin crear comando."""
        if self.editor is None:
            return
        ed = self.editor
        frame = self.frame
        self.editor = None
        self.frame = None

        if ed.toPlainText().strip() != "":
            # El editor trabaja a resolución de PANTALLA (pixelSize = tamaño*zoom);
            # la capa debe guardar el texto a resolución de LIENZO (pixelSize/zoom),
            # o al confirmar con zoom != 100% el texto se rasterizaría a
            # tamaño*zoom² y "crecería" respecto a lo que se veía al editar (mismo
            # criterio que render_to_image para el traspaso a 'mover').
            html = self._doc_at_canvas_resolution_from(ed).toHtml()
            origin = self.start_logical
            
            # Es el layer activo una TextLayer?
            active_idx = self.canvas.active_layer_index
            active_layer = self.canvas.layers[active_idx]
            
            if getattr(active_layer, "is_text", False) and getattr(self, "_editing_layer", None) == active_layer:
                # Modificamos la existente. OJO: con el preview EN VIVO la capa
                # ya contiene el texto nuevo; el "antes" del comando es la
                # instantánea tomada al empezar la edición (_edit_before).
                (old_html, old_origin, old_vertical, old_spacing,
                 old_box_width) = self._edit_before
                from models.layer_commands import EditTextLayerCommand
                cmd = EditTextLayerCommand(self.canvas, active_idx,
                                           old_html, old_origin,
                                           html, origin,
                                           old_vertical=old_vertical,
                                           new_vertical=bool(getattr(self.canvas, "text_vertical", False)),
                                           old_spacing=old_spacing,
                                           new_spacing=int(getattr(self.canvas, "text_spacing", 0)),
                                           old_box_width=old_box_width,
                                           new_box_width=self.box_width)
                self.canvas.undo_stack.push(cmd)
            else:
                # Creamos una TextLayer NUEVA
                from models.layer import TextLayer
                from models.layer_commands import AddLayerCommand

                # Recortamos a unos 20 caracteres para el nombre
                name_preview = ed.toPlainText().strip()[:20]
                if not name_preview:
                    name_preview = t("layer.text_default")

                new_layer = TextLayer(self.canvas.base_width, self.canvas.base_height, name=name_preview)
                new_layer.set_text(html, origin,
                                   vertical=bool(getattr(self.canvas, "text_vertical", False)),
                                   spacing=int(getattr(self.canvas, "text_spacing", 0)),
                                   box_width=self.box_width)

                cmd = AddLayerCommand(self.canvas, layer=new_layer, text=t("hist.text_layer"))
                self.canvas.undo_stack.push(cmd)

        if getattr(self, "_editing_layer", None) is not None:
            if ed.toPlainText().strip() == "" and self._edit_before is not None:
                # Cuadro VACIADO: la edición se descarta sin comando, pero el
                # preview en vivo ya había modificado la capa — reponerla.
                (old_html, old_origin, old_vertical, old_spacing,
                 old_box_width) = self._edit_before
                self._editing_layer.set_text(old_html, old_origin,
                                             vertical=old_vertical, spacing=old_spacing,
                                             box_width=old_box_width)
            self._editing_layer = None
        self._edit_before = None

        if frame is not None:
            frame.hide()
            frame.deleteLater()
        self.start_logical = None
        self.canvas.update()

    def render_to_image(self):
        """Rasteriza el texto actual a una QImage transparente, a resolución de
        LIENZO y recortada a su tamaño. Devuelve (QImage, QPoint) -imagen y
        esquina superior-izquierda en coordenadas de lienzo- o None si el cuadro
        está vacío. Lo usa main.py para pasar el texto a 'modo transformación'
        (mover/girar/escalar como una selección) en lugar de rasterizarlo recto:
        no aplica recorte por selección porque el texto se va a transformar
        libremente."""
        ed = self.editor
        if ed is None or ed.toPlainText().strip() == "":
            return None
        z = self.canvas.zoom_factor or 1.0
        try:
            doc = self._doc_at_canvas_resolution_from(ed)
            doc.setTextWidth(ed.viewport().width() / z)
        except Exception:
            return None
        # Rasterizado con supersampling (bordes sin dientes), como TextLayer
        from models.layer import render_doc_supersampled
        img = render_doc_supersampled(doc)
        origin = QPoint(int(round(self.start_logical.x())),
                        int(round(self.start_logical.y())))
        return (img, origin)

    def _scale_doc_fonts(self, doc, factor):
        """Multiplica por 'factor' el pixelSize de CADA fragmento y de la fuente
        POR DEFECTO del documento. Se usa para pasar entre resolución de PANTALLA
        (edición: tamaño*zoom) y de LIENZO (guardado/render: tamaño). INT
        obligatorio: con float, toHtml() exporta 'font-size:0px'."""
        for pos, length, ps in self._iter_fragments(doc):
            c = QTextCursor(doc)
            c.setPosition(pos)
            c.setPosition(pos + length, QTextCursor.KeepAnchor)
            nf = QTextCharFormat()
            nf.setProperty(QTextFormat.FontPixelSize, int(max(1, round(ps * factor))))
            c.mergeCharFormat(nf)
        df = doc.defaultFont()
        dps = df.pixelSize()
        if dps > 0:
            df.setPixelSize(max(1, round(dps * factor)))
            doc.setDefaultFont(df)

    def _doc_at_canvas_resolution_from(self, ed):
        """Clon del documento del editor a resolución de LIENZO (pixelSize/zoom).
        El interletraje VISUAL del editor va escalado por el zoom (y toHtml lo
        descarta, así que el html guardado sale limpio): en el clon se re-aplica
        a su valor real, para que render_to_image (traspaso a 'mover') rasterice
        con el interletraje correcto."""
        z = self.canvas.zoom_factor or 1.0
        doc = ed.document().clone()
        self._scale_doc_fonts(doc, 1.0 / z)
        if self._editor_spacing_active:
            self._merge_doc_spacing(doc, int(getattr(self.canvas, "text_spacing", 0)))
        return doc

    def cancel_editing(self):
        if self.editor is None:
            return
        frame = self.frame
        self.editor = None
        self.frame = None
        if getattr(self, "_editing_layer", None) is not None:
            if self._edit_before is not None:
                # Esc: reponer la capa como estaba (el preview en vivo la había
                # ido actualizando) y devolver el panel a su estado.
                (old_html, old_origin, old_vertical, old_spacing,
                 old_box_width) = self._edit_before
                self._editing_layer.set_text(old_html, old_origin,
                                             vertical=old_vertical, spacing=old_spacing,
                                             box_width=old_box_width)
                self.canvas.text_vertical = old_vertical
                self.canvas.text_spacing = old_spacing
            self._editing_layer = None
        self._edit_before = None

        if frame is not None:
            frame.hide()
            frame.deleteLater()
        self.start_logical = None
        self.canvas.update()

    def finish_editing(self):
        """Gancho que llama main.py al cambiar de herramienta."""
        self.commit_editing()