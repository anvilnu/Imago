from i18n import t
# widgets/history_panel.py
import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListView, QPushButton, QAbstractItemView
)
from PySide6.QtGui import QIcon, QColor, QFont
from PySide6.QtCore import QSize, QTimer, QAbstractListModel, QModelIndex, Qt, QFile
import theme


class HistoryModel(QAbstractListModel):
    """Modelo del historial: los datos viven en PYTHON (una lista de dicts), NO
    en objetos C++ por fila. Motivo: el panel corria antes sobre QListWidget y
    cada refresco hacia clear()+addItem, creando y DESTRUYENDO cientos de
    QListWidgetItem (objetos C++ con envoltorio shiboken). Ese churn de
    destruccion abortaba de forma intermitente en Shiboken::Object::destroy
    (doble-free) con PySide6 6.11 / Python 3.14. Con un modelo real, refrescar es
    resetear una lista de Python: la vista descarta indices ligeros, sin destruir
    envoltorios por fila, y el aborto desaparece.

    Cada fila es un dict: {'text': str, 'icon': QIcon|None, 'undone': bool}."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows = []
        self._base_font = QFont()

    def set_base_font(self, font):
        self._base_font = QFont(font)

    def set_rows(self, rows):
        """Reemplaza por completo el contenido. beginResetModel/endResetModel es
        seguro: no destruye objetos C++ por fila (a diferencia de clear())."""
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(self._rows)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row = index.row()
        if row < 0 or row >= len(self._rows):
            return None
        datos = self._rows[row]
        if role == Qt.DisplayRole:
            return datos["text"]
        if role == Qt.DecorationRole:
            return datos["icon"]
        if role == Qt.ForegroundRole:
            # Lo deshecho (por debajo de la accion activa) se ve fantasma.
            return QColor(theme.TEXT_FAINT if datos["undone"] else theme.TEXT)
        if role == Qt.FontRole:
            f = QFont(self._base_font)
            f.setItalic(datos["undone"])
            return f
        return None


class HistoryPanel(QWidget):
    def __init__(self, canvas, main_window=None):
        super().__init__()
        self.canvas = canvas
        self.main_window = main_window
        self.undo_stack = canvas.undo_stack

        # Sintonía con el tema oscuro general
        self.setStyleSheet("background-color: %s; color: %s;" % (theme.BG_WINDOW, theme.TEXT))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(4)

        # 1️⃣ Vista del historial (QListView + modelo: ver HistoryModel para el
        #    porqué de no usar QListWidget).
        self.model = HistoryModel(self)
        self.list_view = QListView()
        self.list_view.setModel(self.model)
        self.list_view.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list_view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.list_view.setUniformItemSizes(True)

        # 🟢 Forzamos a que los iconos ocupen menos espacio vertical
        self.list_view.setIconSize(QSize(16, 16))
        self.model.set_base_font(self.list_view.font())

        # 🟢 Reducimos el padding y fijamos la altura de cada fila a 20px
        self.list_view.setStyleSheet(
            theme.listview_qss()
            + """
            QListView::item {
                padding-top: 1px;
                padding-bottom: 1px;
                padding-left: 4px;
                margin: 0px;
                height: 20px; /* Altura ultra-compacta */
            }
        """)
        layout.addWidget(self.list_view)

        # 2️⃣ Botones de acción inferiores (Deshacer / Rehacer)
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(4)

        self.btn_undo = QPushButton(t("btn.undo", default="Deshacer"))
        self.btn_redo = QPushButton(t("btn.redo", default="Rehacer"))

        # 🟢 Hoja de estilo para iluminar los botones activos con borde azul
        estilo_iluminado = theme.panel_action_button_qss()
        self.btn_undo.setStyleSheet(estilo_iluminado)
        self.btn_redo.setStyleSheet(estilo_iluminado)

        btn_layout.addWidget(self.btn_undo)
        btn_layout.addWidget(self.btn_redo)
        layout.addLayout(btn_layout)

        # Conexiones de los botones. NO van directas a la pila: pasan por la
        # misma protección que Ctrl+Z (ver _deshacer/_rehacer): mover la pila
        # con un objeto flotante EN EDICIÓN (Línea/Curva, Formas) hornearía el
        # flotante en la capa sin entrada de historial (imborrable).
        self.btn_undo.clicked.connect(self._deshacer)
        self.btn_redo.clicked.connect(self._rehacer)

        # Escuchar cambios en el stack para refrescar la lista.
        # OJO: el refresco se hace DIFERIDO y coalescido (QTimer 0 ms), nunca
        # directo. Aunque el modelo ya no destruye items uno a uno (lo que
        # abortaba con QListWidget.clear()), resetearlo DENTRO de la propia
        # emisión de indexChanged que dispara undo_stack.push() sigue siendo
        # reentrar en el widget en mitad del push. Posponerlo deja que push()
        # termine antes de tocar la vista.
        self._refresco_pendiente = False
        self._detached = False
        # Guarda para no re-disparar setIndex() mientras SINCRONIZAMOS la
        # selección de la vista con el índice del stack (selección programática).
        self._updating = False
        # Timer MIEMBRO (hijo de self): se destruye con el panel y se puede parar
        # en detach(), así nunca dispara sobre un panel ya reemplazado/destruido.
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self._ejecutar_refresco)
        self.undo_stack.indexChanged.connect(self._programar_refresco)
        # La selección la escuchamos por el selectionModel de la vista: cubre
        # clic de ratón Y navegación con teclado, igual que hacía currentRowChanged.
        self.list_view.selectionModel().currentChanged.connect(self._on_current_changed)

        # Rellenar inicialmente
        self.update_history_list()

    def detach(self):
        """Desconecta este panel del undo_stack antes de ser reemplazado.
        Evita que paneles 'fantasma' sigan escuchando señales de stacks antiguos
        y CANCELA cualquier refresco diferido pendiente (si no, podía dispararse
        sobre el panel ya borrado)."""
        self._detached = True
        try:
            self._refresh_timer.stop()
        except (RuntimeError, AttributeError):
            pass
        try:
            self.undo_stack.indexChanged.disconnect(self._programar_refresco)
        except (RuntimeError, TypeError):
            pass  # Ya estaba desconectado o el stack fue destruido
        try:
            self.list_view.selectionModel().currentChanged.disconnect(self._on_current_changed)
        except (RuntimeError, TypeError):
            pass

    def _programar_refresco(self, *args):
        """Pospone (coalescido) la reconstrucción de la lista al siguiente ciclo
        del bucle de eventos, cuando undo_stack.push() ya ha terminado."""
        if self._detached or self._refresco_pendiente:
            return
        self._refresco_pendiente = True
        self._refresh_timer.start(0)

    def _ejecutar_refresco(self):
        self._refresco_pendiente = False
        if self._detached:
            return
        self.update_history_list()

    def _resolver_icono(self, command):
        """Devuelve la ruta de icono para un comando del stack (misma lógica que
        antes: por tool_id, con override history_icon de los efectos de IA)."""
        text = command.text()
        tid = getattr(command, 'tool_id', None)
        icon_path = ":/icons/pen.png"
        if tid == "eraser": icon_path = ":/icons/eraser.png"
        elif tid == "bucket": icon_path = ":/icons/bucket.png"
        elif tid in ["rect", "ellipse", "line"]: icon_path = ":/icons/shapes.png"
        elif tid == "layer": icon_path = ":/icons/layers_panel.png"
        elif tid == "move": icon_path = ":/icons/move.png"
        elif tid == "move_copy": icon_path = ":/icons/move_copy.png"
        elif tid == "cut": icon_path = ":/icons/cut.png"
        elif tid == "transform": icon_path = ":/icons/transform.png"
        elif tid == "paste": icon_path = ":/icons/paste.png"
        elif tid == "select": icon_path = ":/icons/select_rect.png"
        elif tid == "select_rect": icon_path = ":/icons/select_rect.png"
        elif tid == "select_ellipse": icon_path = ":/icons/select_ellipse.png"
        elif tid == "select_lasso": icon_path = ":/icons/select_lasso.png"
        elif tid == "deselect": icon_path = ":/icons/deselect.png"
        elif tid == "delete": icon_path = ":/icons/delete_selection.png"
        elif tid == "fill": icon_path = ":/icons/fill_selection.png"
        elif tid == "invert": icon_path = ":/icons/invert_selection.png"
        elif tid == "paste_selection": icon_path = ":/icons/paste_selection.png"
        elif tid == "clone": icon_path = ":/icons/clone.png"
        elif tid == "text": icon_path = ":/icons/text.png"
        elif tid == "pen_path": icon_path = ":/icons/pen_path.png"
        elif tid == "airbrush": icon_path = ":/icons/airbrush.png"
        elif tid == "gradient": icon_path = ":/icons/gradient.png"
        elif tid == "smudge": icon_path = ":/icons/smudge.png"
        elif tid == "dodge_burn": icon_path = ":/icons/dodge_burn.png"
        elif tid == "heal": icon_path = ":/icons/heal.png"
        elif tid == "replace_color": icon_path = ":/icons/replace_color.png"
        elif tid == "guides": icon_path = ":/icons/guides.png"
        elif tid == "adjust":
            # Cada ajuste/efecto tiene su icono propio: se resuelve por el
            # nombre del comando contra el registro construido desde los menús.
            icon_path = ":/icons/adjust.png"
            mw = self.main_window
            if mw is not None and hasattr(mw, "_history_icons"):
                key = text.replace("...", "").replace("&", "").strip()
                ic = mw._history_icons.get(key)
                if ic and QFile.exists(":/icons/" + ic):
                    icon_path = ":/icons/" + ic
        elif tid == "shape": icon_path = ":/icons/shapes.png"
        elif tid == "magic_wand": icon_path = ":/icons/magic_wand.png"
        elif tid == "crop": icon_path = ":/icons/crop.png"
        elif tid == "resize": icon_path = ":/icons/resize.png"
        elif tid == "canvas_size": icon_path = ":/icons/canvas_size.png"
        elif tid == "flip_h": icon_path = ":/icons/flip_h.png"
        elif tid == "flip_v": icon_path = ":/icons/flip_v.png"
        elif tid == "rotate_cw": icon_path = ":/icons/rotate_cw.png"
        elif tid == "rotate_ccw": icon_path = ":/icons/rotate_ccw.png"
        elif tid == "rotate_180": icon_path = ":/icons/rotate_180.png"

        # Los efectos del menú IA marcan su icono propio en el comando
        # (history_icon): prevalece sobre el que resolvería el tool_id, para
        # que cada efecto de IA muestre su icono y no el del pincel.
        hist_icon = getattr(command, 'history_icon', None)
        if hist_icon and QFile.exists(":/icons/" + hist_icon):
            icon_path = ":/icons/" + hist_icon
        return icon_path

    def update_history_list(self):
        """Refresca por completo el contenido de la vista basándose en el
        QUndoStack. Construye una lista de filas (datos Python) y resetea el
        modelo; no se crea ni destruye ningún objeto C++ por fila."""
        count = self.undo_stack.count()
        active_index = self.undo_stack.index()

        rows = []

        # 📌 1. Fila inicial fija: "Abrir / Lienzo Nuevo"
        base_icon = None
        if QFile.exists(":/icons/imagen_inicial.png"):
            base_icon = theme.icono(":/icons/imagen_inicial.png")
        rows.append({
            "text": t("hist.initial_canvas", default="Lienzo Inicial"),
            "icon": base_icon,
            "undone": 0 > active_index,
        })

        # 📌 2. Agregar los comandos reales que están en el stack
        for i in range(count):
            command = self.undo_stack.command(i)
            icon_path = self._resolver_icono(command)
            icon = theme.icono(icon_path) if QFile.exists(icon_path) else None
            rows.append({
                "text": command.text(),
                "icon": icon,
                # Filas por encima de la acción activa = deshechas (gris+itálica).
                "undone": (i + 1) > active_index,
            })

        self.model.set_rows(rows)

        # 📌 3. Establecer foco en la acción temporal activa. Marcamos _updating
        #    para que la selección programática NO reentre en el stack vía
        #    _on_current_changed.
        self._updating = True
        idx = self.model.index(active_index, 0)
        if idx.isValid():
            self.list_view.setCurrentIndex(idx)
        self._updating = False

        # 📌 4. Refrescar estado operativo de los botones inferiores
        self.btn_undo.setEnabled(self.undo_stack.canUndo())
        self.btn_redo.setEnabled(self.undo_stack.canRedo())

    def _cancelar_flotante(self):
        """Si la herramienta activa tiene un objeto flotante EN EDICIÓN
        (Línea/Curva, Formas), lo cancela (como Esc) y devuelve True. Debe
        llamarse ANTES de mover la pila desde el panel: si la pila se mueve
        con el flotante vivo, este queda horneado en la capa sin comando."""
        tool = getattr(self.canvas, 'current_tool', None)
        if getattr(tool, 'editing', False) and hasattr(tool, '_cancel_edit'):
            tool._cancel_edit()
            return True
        return False

    def _deshacer(self):
        """Deshacer desde el panel con la misma semántica que Ctrl+Z: el primer
        clic cancela el flotante (sin mover la pila); el siguiente ya deshace."""
        if self._cancelar_flotante():
            return
        self.undo_stack.undo()

    def _rehacer(self):
        """Rehacer desde el panel: el flotante se cancela primero (su estado
        quedaría obsoleto al mover la pila) y después se rehace."""
        self._cancelar_flotante()
        self.undo_stack.redo()

    def _on_current_changed(self, current, previous):
        """Permite al usuario saltar a cualquier punto del historial (clic o
        teclado). Se ignora cuando la selección la fijamos nosotros al refrescar."""
        if self._updating or self._detached:
            return
        if current is None or not current.isValid():
            return
        # Saltar por el historial con un flotante vivo también pasa por la
        # protección: primero se cancela, luego se salta al punto pedido.
        self._cancelar_flotante()
        self.undo_stack.setIndex(current.row())
