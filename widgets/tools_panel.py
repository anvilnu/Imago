from i18n import t
# widgets/tools_panel.py
import os
from PySide6.QtWidgets import QWidget, QGridLayout, QToolButton, QApplication, QMenu
from PySide6.QtGui import QIcon, QDrag, QPainter, QPen, QColor
from PySide6.QtCore import QSize, Qt, QEvent, QMimeData, QFile
import theme

# Formato MIME propio del arrastre de botones (solo reordena dentro del panel)
_MIME_HERRAMIENTA = "application/x-imago-tool"

# ⌨️ Atajos de UNA TECLA por herramienta (estilo Photoshop/GIMP). ÚNICA FUENTE
# DE VERDAD: el panel los muestra en los tooltips y main.py crea con ellos las
# QAction de ventana (_crear_atajos_herramientas). M alterna las 2 marquesinas.
ATAJOS_HERRAMIENTAS = {
    "select_rect": "M", "select_ellipse": "M", "select_lasso": "L",
    "magic_wand": "W", "move": "V", "pen": "B", "pencil": "N",
    "eraser": "E", "bucket": "G", "gradient": "D", "eyedropper": "I",
    "text": "T", "clone": "S", "airbrush": "A", "smudge": "U",
    "replace_color": "R", "pen_path": "P", "shapes": "F", "hand": "H",
    "crop": "C", "dodge_burn": "O", "heal": "J", "line_curve": "K",
    "measure": "Q", "sponge": "Y", "liquify": "Z",
}
# OJO al elegir teclas nuevas: la X está reservada para INTERCAMBIAR los
# colores primario/secundario (swap_colors_action) — un atajo duplicado deja
# AMBAS acciones mudas (Qt lo marca ambiguo y no dispara ninguna).

class ToolsPanel(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window

        # 🎨 Tema oscuro + azul, unificado con los paneles de Capas e Historial.
        # Lo aplicamos a nivel de panel: todos los QToolButton hijos lo heredan.
        self.setStyleSheet(
            "ToolsPanel { background-color: %s; }\n" % theme.BG_WINDOW
            + theme.tool_grid_button_qss())

        layout = QGridLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        # Espaciado idéntico en ambas direcciones
        layout.setHorizontalSpacing(6)
        layout.setVerticalSpacing(6)
        
        # Los iconos vienen de los recursos EMBEBIDOS (:/icons/...).
        # Mapeamos cada herramienta con: (Nombre, ID, Nombre del archivo PNG)
        # Orden POR DEFECTO de la rejilla (intercalado fila a fila: columna
        # izquierda / columna derecha). Debe contar la misma historia que
        # tools_list en options_bar.py (allí por columnas: izquierda y derecha).
        tools = [
            (t("tool.name.select_rect"), "select_rect", "select_rect.png"),
            (t("tool.name.move"), "move", "move.png"),
            (t("tool.name.select_lasso"), "select_lasso", "select_lasso.png"),
            (t("tool.name.hand"), "hand", "hand.png"),
            (t("tool.name.select_ellipse"), "select_ellipse", "select_ellipse.png"),
            (t("tool.name.crop"), "crop", "crop.png"),
            (t("tool.name.pen"), "pen", "pen.png"),
            (t("tool.name.eraser"), "eraser", "eraser.png"),
            (t("tool.name.pencil"), "pencil", "pencil.png"),
            (t("tool.name.bucket"), "bucket", "bucket.png"),
            (t("tool.name.airbrush"), "airbrush", "airbrush.png"),
            (t("tool.name.pen_path"), "pen_path", "pen_path.png"),
            (t("tool.name.magic_wand"), "magic_wand", "magic_wand.png"),
            (t("tool.name.eyedropper"), "eyedropper", "eyedropper.png"),
            (t("tool.name.clone"), "clone", "clone.png"),
            (t("tool.name.smudge"), "smudge", "smudge.png"),
            (t("tool.name.dodge_burn"), "dodge_burn", "dodge_burn.png"),
            (t("tool.name.heal"), "heal", "heal.png"),
            (t("tool.name.sponge"), "sponge", "sponge.png"),
            (t("tool.name.liquify"), "liquify", "liquify.png"),
            (t("tool.name.replace_color"), "replace_color", "replace_color.png"),
            (t("tool.name.gradient"), "gradient", "gradient.png"),
            (t("tool.name.text"), "text", "text.png"),
            (t("tool.name.measure"), "measure", "measure.png"),
            (t("tool.name.line_curve"), "line_curve", "line_curve.png"),
            (t("tool.name.shapes"), "shapes", "shapes.png")
        ]
        
        # Crear los botones (la COLOCACIÓN en la rejilla de 2 columnas la hace
        # _recolocar, que se reutiliza al reordenar o al alojar el selector)
        self._buttons = []
        for name, tool_id, icon_file in tools:
            btn = QToolButton()

            # Ruta al recurso EMBEBIDO del icono (:/icons/...)
            icon_path = ":/icons/" + icon_file

            # Comprobamos si el recurso existe; si no, dejamos el texto para que no falle
            if QFile.exists(icon_path):
                btn.setIcon(theme.icono(icon_path))  # factory: tinta en tema claro
                btn.setIconSize(QSize(24, 24)) # Tamaño ideal del icono dentro del botón
            else:
                btn.setText(name) # Plan B si te falta alguna imagen

            btn.setCheckable(True)
            # 🎯 NoFocus: clicar una herramienta no roba el foco de teclado
            # al lienzo (las flechas de Mover siguen funcionando)
            btn.setFocusPolicy(Qt.NoFocus)
            btn.setFixedSize(30, 30) # Tamaño del botón contenedor (estilo rejilla Paint.NET)
            tecla = ATAJOS_HERRAMIENTAS.get(tool_id)
            btn.setToolTip(f"{name}  ({tecla})" if tecla else name)

            btn.clicked.connect(lambda checked, tid=tool_id: self.main_window.set_tool(tid))

            btn.setProperty("tool_id", tool_id)
            # 🔀 El filtro de eventos distingue clic (activar) de arrastre (reordenar)
            btn.installEventFilter(self)
            self._buttons.append(btn)

        # Reordenación por arrastre: estado del gesto y del indicador de soltado.
        # 'reorderable' (preferencia, main.py la aplica): si es False no se pueden
        # arrastrar ni reordenar los botones (ni el menú de restaurar orden).
        self._orden_defecto = [b.property("tool_id") for b in self._buttons]
        self._drag_btn = None
        self._drag_origen = None
        self._drop_index = None
        self.reorderable = True
        self.setAcceptDrops(True)

        # Selector de color compacto opcional al pie de la rejilla (lo asigna
        # main.py con set_color_selector); se muestra cuando main.py lo pide
        # (panel de Color cerrado).
        self.color_selector = None
        self._color_selector_visible = False

        self._recolocar()

        self.set_active_tool_visual("pen")

    def set_reorderable(self, enabled):
        """Activa o desactiva la reordenación de los botones (arrastrar y el menú
        de restaurar orden). Desactivada, la barra queda fija."""
        self.reorderable = bool(enabled)
        # Si se desactiva a mitad de un gesto, cancela el arrastre pendiente.
        if not self.reorderable:
            self._drag_btn = None
            self._drop_index = None
            self.update()

    def set_color_selector(self, widget):
        """Aloja el selector de color compacto al pie del panel (una sola vez).
        La visibilidad efectiva la controla set_color_selector_visible."""
        self.color_selector = widget
        widget.setParent(self)
        self._recolocar()

    def set_color_selector_visible(self, visible):
        """Muestra u oculta el selector de color del pie (main.py decide el
        criterio: panel de Color cerrado)."""
        self._color_selector_visible = bool(visible)
        self._recolocar()

    def _recolocar(self):
        """Recoloca la rejilla de botones en sus 2 columnas fijas. La fila
        elástica final se recalcula: empotrado en el splitter, el panel ocupa
        todo el alto y esa fila absorbe el hueco para que los botones queden
        agrupados ARRIBA."""
        layout = self.layout()
        for btn in self._buttons:
            layout.removeWidget(btn)
        for r in range(layout.rowCount()):
            layout.setRowStretch(r, 0)   # limpiar la fila elástica anterior
        row, col = 0, 0
        for btn in self._buttons:
            layout.addWidget(btn, row, col)
            col += 1
            if col >= 2:
                col = 0
                row += 1
        if col != 0:
            row += 1
        # Selector de color al pie: justo debajo de la última fila de botones
        # (main.py decide su visibilidad según el panel de Color).
        if self.color_selector is not None:
            layout.removeWidget(self.color_selector)
            self.color_selector.setVisible(self._color_selector_visible)
            if self._color_selector_visible:
                layout.addWidget(self.color_selector, row, 0, 1, 2)
                row += 1
        layout.setRowStretch(row + 1, 1)

    def set_active_tool_visual(self, tool_id):
        for btn in self.findChildren(QToolButton):
            if btn.property("tool_id") == tool_id:
                btn.setChecked(True)
            else:
                btn.setChecked(False)

    # ------------------------------------------------------------------
    # 🔀 Reordenación por arrastre (insertar desplazando, estilo pestañas)
    # ------------------------------------------------------------------

    def tool_order(self):
        """Orden actual como lista de tool_ids."""
        return [b.property("tool_id") for b in self._buttons]

    def apply_order(self, ids):
        """Reordena los botones según la lista de tool_ids dada. Ids
        desconocidos se ignoran, y herramientas no listadas (p. ej. añadidas
        en una versión nueva) se quedan al final en su orden actual."""
        por_id = {b.property("tool_id"): b for b in self._buttons}
        nuevos = [por_id.pop(tid) for tid in ids if tid in por_id]
        nuevos.extend(por_id.values())
        self._buttons = nuevos
        self._recolocar()

    def eventFilter(self, obj, ev):
        # Distinguir clic (activar herramienta) de arrastre (reordenar): el
        # arrastre solo empieza al superar startDragDistance con botón pulsado.
        if ev.type() == QEvent.MouseButtonPress and ev.button() == Qt.LeftButton:
            self._drag_btn = obj
            self._drag_origen = ev.position().toPoint()
        elif ev.type() == QEvent.MouseButtonRelease:
            self._drag_btn = None
        elif (ev.type() == QEvent.MouseMove and obj is self._drag_btn
              and ev.buttons() & Qt.LeftButton and self.reorderable):
            if ((ev.position().toPoint() - self._drag_origen).manhattanLength()
                    >= QApplication.startDragDistance()):
                self._iniciar_arrastre(obj)
                return True
        return super().eventFilter(obj, ev)

    def _iniciar_arrastre(self, btn):
        btn.setDown(False)   # que no se quede "pulsado" mientras se lo llevan
        self._drag_btn = None
        drag = QDrag(btn)
        mime = QMimeData()
        mime.setData(_MIME_HERRAMIENTA, btn.property("tool_id").encode("utf-8"))
        drag.setMimeData(mime)
        pixmap = btn.grab()
        drag.setPixmap(pixmap)
        drag.setHotSpot(pixmap.rect().center())
        drag.exec(Qt.MoveAction)
        # Si se soltó fuera del panel no llega dropEvent: limpiar el indicador
        self._drop_index = None
        self.update()

    def dragEnterEvent(self, ev):
        if self.reorderable and ev.mimeData().hasFormat(_MIME_HERRAMIENTA):
            ev.acceptProposedAction()

    def dragMoveEvent(self, ev):
        if not ev.mimeData().hasFormat(_MIME_HERRAMIENTA):
            return
        indice = self._indice_insercion(ev.position().toPoint())
        if indice != self._drop_index:
            self._drop_index = indice
            self.update()
        ev.acceptProposedAction()

    def dragLeaveEvent(self, ev):
        self._drop_index = None
        self.update()

    def dropEvent(self, ev):
        datos = ev.mimeData().data(_MIME_HERRAMIENTA)
        indice = self._drop_index
        self._drop_index = None
        self.update()
        if datos.isEmpty() or indice is None:
            return
        tool_id = bytes(datos).decode("utf-8")
        orden = list(self._buttons)
        origen = next((b for b in orden if b.property("tool_id") == tool_id), None)
        if origen is None:
            return
        i_origen = orden.index(origen)
        orden.pop(i_origen)
        if indice > i_origen:
            indice -= 1
        orden.insert(indice, origen)
        self._buttons = orden
        self._recolocar()
        ev.acceptProposedAction()
        self.main_window.on_tools_reordered()

    def _indice_insercion(self, pos):
        """Índice donde caería el botón soltado en pos: el hueco más cercano,
        decidido por el centro del botón más próximo."""
        orden = self._buttons
        if not orden:
            return 0
        if pos.y() > orden[-1].geometry().bottom():
            return len(orden)   # por debajo de todos → al final
        mejor, d2_mejor = 0, None
        for i, b in enumerate(orden):
            c = b.geometry().center()
            d2 = (c.x() - pos.x()) ** 2 + (c.y() - pos.y()) ** 2
            if d2_mejor is None or d2 < d2_mejor:
                mejor, d2_mejor = i, d2
        centro = orden[mejor].geometry().center()
        return mejor + 1 if pos.x() > centro.x() else mejor

    def paintEvent(self, ev):
        super().paintEvent(ev)
        if self._drop_index is None:
            return
        orden = self._buttons
        if not orden:
            return
        # Indicador de inserción: línea de acento en el hueco de destino
        p = QPainter(self)
        p.setPen(QPen(QColor(theme.ACCENT), 2))
        i = self._drop_index
        g = orden[i].geometry() if i < len(orden) else orden[-1].geometry()
        x = g.left() - 3 if i < len(orden) else g.right() + 3
        p.drawLine(x, g.top(), x, g.bottom())
        p.end()

    def contextMenuEvent(self, ev):
        if not self.reorderable:
            return   # con la reordenación bloqueada, no se ofrece restaurar orden
        menu = QMenu(self)
        accion = menu.addAction(t("panel.tools_reset_order",
                                  default="Restaurar orden por defecto"))
        if menu.exec(ev.globalPos()) is accion:
            self.apply_order(self._orden_defecto)
            self.main_window.on_tools_reordered()
