from i18n import t
# widgets/layers_panel.py
import os
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget,
                             QListWidgetItem, QPushButton, QCheckBox, QLabel,
                             QLineEdit, QSlider, QDialogButtonBox, QFormLayout,
                             QAbstractItemView, QComboBox, QFrame)
from PySide6.QtGui import QPixmap, QIcon, QPainter, QColor, QPen
from PySide6.QtCore import Qt, QSize, QTimer, Signal, QFile
import theme
from widgets.custom_titlebar import FramelessDialog


class _ClickableLabel(QLabel):
    """QLabel que emite 'clicked' al pulsarlo (para elegir entre editar la capa
    o su máscara). Consume el evento para no cambiar la selección de la lista."""
    clicked = Signal()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)


class _ElideLabel(QLabel):
    """QLabel que RECORTA su texto con '…' cuando no cabe, en vez de exigir
    todo su ancho. Sin esto, un nombre de capa largo (p. ej. de un PSD
    importado) ensanchaba la fila más que el panel y empujaba la casilla de
    visibilidad fuera de la vista."""

    def __init__(self, text=""):
        super().__init__(text)
        self._texto_completo = text
        self.setMinimumWidth(40)

    def setText(self, text):
        self._texto_completo = text
        super().setText(text)

    def resizeEvent(self, event):
        fm = self.fontMetrics()
        super().setText(fm.elidedText(self._texto_completo,
                                      Qt.TextElideMode.ElideRight, self.width()))
        super().resizeEvent(event)


def blend_modes():
    """Lista (texto traducido, CompositionMode) de los modos de fusión de capa,
    agrupados como en otros editores: oscurecer / aclarar / contraste /
    comparativos. Se construye en cada llamada para usar el idioma actual.
    La comparten el diálogo de Propiedades y el combo del panel de Capas."""
    M = QPainter.CompositionMode
    return [
        (t("blend.normal"), M.CompositionMode_SourceOver),
        (t("blend.darken"), M.CompositionMode_Darken),
        (t("blend.multiply"), M.CompositionMode_Multiply),
        (t("blend.color_burn"), M.CompositionMode_ColorBurn),
        (t("blend.lighten"), M.CompositionMode_Lighten),
        (t("blend.screen"), M.CompositionMode_Screen),
        (t("blend.color_dodge"), M.CompositionMode_ColorDodge),
        (t("blend.addition"), M.CompositionMode_Plus),
        (t("blend.overlay"), M.CompositionMode_Overlay),
        (t("blend.soft_light"), M.CompositionMode_SoftLight),
        (t("blend.hard_light"), M.CompositionMode_HardLight),
        (t("blend.difference"), M.CompositionMode_Difference),
        (t("blend.exclusion"), M.CompositionMode_Exclusion),
    ]


class LayerPropertiesDialog(FramelessDialog):
    """Diálogo de propiedades de capa: nombre y opacidad con previsualización en vivo.

    Usa FramelessDialog para llevar la misma barra de título oscura propia que el
    resto de diálogos (sin barra nativa del sistema). El contenido va en
    ``self.body_layout`` y el tamaño fijo se aplica al CUERPO (``self._body``),
    no al diálogo, para no pisar la barra de título."""

    def __init__(self, canvas, layer, parent=None):
        super().__init__(parent)
        self.canvas = canvas
        self.layer = layer

        # Guardamos los valores originales por si el usuario cancela
        self._original_name = layer.name
        self._original_opacity = layer.opacity
        self._original_blend = layer.blend_mode
        self._original_alpha_locked = layer.alpha_locked
        self._original_pixels_locked = getattr(layer, "pixels_locked", False)
        self._original_position_locked = getattr(layer, "position_locked", False)

        self.setWindowTitle(t("layer.properties"))
        self._body.setFixedWidth(280)
        # Estilo del cuerpo desde theme (el borde del marco lo lleva el _frame
        # interno de FramelessDialog, con su propio stylesheet, y sobrevive a este).
        self.setStyleSheet(
            "QLabel { color: %s; }\n" % theme.TEXT
            + theme.lineedit_qss()
            + theme.slider_qss()
            # OJO: el selector lleva SCOPE (QDialogButtonBox ...). Un "QPushButton"
            # a secas alcanzaria tambien la X de la barra de titulo (_CaptionButton
            # es un QPushButton), que se ensancharia por el min-width/padding y
            # quedaria descentrada. Acotado al button box, solo afecta a Aceptar/Cancelar.
            + theme.dialog_button_qss("QDialogButtonBox QPushButton")
        )

        form = QFormLayout()

        # Campo de nombre
        self.name_edit = QLineEdit(layer.name)
        form.addRow(t("layer.name"), self.name_edit)

        # Slider de opacidad con etiqueta de porcentaje
        opacity_row = QHBoxLayout()
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(layer.opacity)
        self.opacity_label = QLabel(f"{layer.opacity}%")
        self.opacity_label.setFixedWidth(38)
        opacity_row.addWidget(self.opacity_slider)
        opacity_row.addWidget(self.opacity_label)
        form.addRow(t("layer.opacity"), opacity_row)

        # ComboBox de modo de fusión (lista compartida con el panel de Capas)
        self.blend_combo = QComboBox()
        self.blend_combo.setStyleSheet(theme.combobox_qss())
        self.modes = blend_modes()
        current_idx = 0
        for i, (name, mode) in enumerate(self.modes):
            self.blend_combo.addItem(name, mode)
            if mode == layer.blend_mode:
                current_idx = i
        self.blend_combo.setCurrentIndex(current_idx)
        form.addRow(t("opt.lbl.mode"), self.blend_combo)

        # Checkbox para bloquear transparencia
        self.alpha_locked_check = QCheckBox(t("layer.lock_alpha"))
        self.alpha_locked_check.setStyleSheet(theme.checkbox_qss())
        self.alpha_locked_check.setChecked(layer.alpha_locked)
        form.addRow("", self.alpha_locked_check)

        # 🔒 Bloqueos de edición: píxeles (no pintar/ajustar sobre la capa) y
        # posición (no moverla con la herramienta Mover).
        self.pixels_locked_check = QCheckBox(t("layer.lock_pixels"))
        self.pixels_locked_check.setStyleSheet(theme.checkbox_qss())
        self.pixels_locked_check.setChecked(self._original_pixels_locked)
        form.addRow("", self.pixels_locked_check)
        self.position_locked_check = QCheckBox(t("layer.lock_position"))
        self.position_locked_check.setStyleSheet(theme.checkbox_qss())
        self.position_locked_check.setChecked(self._original_position_locked)
        form.addRow("", self.position_locked_check)

        # Previsualización en vivo: la opacidad y modo se aplican
        self.opacity_slider.valueChanged.connect(self._preview_opacity)
        self.blend_combo.currentIndexChanged.connect(self._preview_mode)

        # Botones Aceptar / Cancelar
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

        # El formulario se inserta en el cuerpo del diálogo sin marco
        self.body_layout.addLayout(form)

    def _preview_opacity(self, value):
        self.opacity_label.setText(f"{value}%")
        self.layer.opacity = value
        self.canvas.update()

    def _preview_mode(self, idx):
        self.layer.blend_mode = self.modes[idx][1]
        self.canvas.update()

    def accept(self):
        from models.layer_commands import LayerPropertiesCommand
        new_name = self.name_edit.text().strip() or self._original_name
        new_opacity = self.opacity_slider.value()
        new_blend = self.modes[self.blend_combo.currentIndex()][1]
        new_alpha_locked = self.alpha_locked_check.isChecked()
        new_pixels_locked = self.pixels_locked_check.isChecked()
        new_position_locked = self.position_locked_check.isChecked()

        # Si no hubo cambios reales no hay nada que registrar
        if (new_name == self._original_name and new_opacity == self._original_opacity and
            new_blend == self._original_blend and new_alpha_locked == self._original_alpha_locked and
            new_pixels_locked == self._original_pixels_locked and
            new_position_locked == self._original_position_locked):
            super().accept()
            return

        # Revertimos el preview en vivo para que el comando parta de estado original
        self.layer.name = self._original_name
        self.layer.opacity = self._original_opacity
        self.layer.blend_mode = self._original_blend
        self.layer.alpha_locked = self._original_alpha_locked

        index = self.canvas.layers.index(self.layer)
        cmd = LayerPropertiesCommand(
            self.canvas, index,
            self._original_name, new_name,
            self._original_opacity, new_opacity,
            self._original_blend, new_blend,
            self._original_alpha_locked, new_alpha_locked,
            old_pixels_locked=self._original_pixels_locked,
            new_pixels_locked=new_pixels_locked,
            old_position_locked=self._original_position_locked,
            new_position_locked=new_position_locked,
        )
        self.canvas.undo_stack.push(cmd)
        super().accept()

    def reject(self):
        # Restaurar los valores originales si se cancela
        self.layer.name = self._original_name
        self.layer.opacity = self._original_opacity
        self.layer.blend_mode = self._original_blend
        self.layer.alpha_locked = self._original_alpha_locked
        self.canvas.update()
        super().reject()


class LayerListWidget(QListWidget):
    """QListWidget personalizado para gestionar el arrastrar y soltar de capas.
    Admite selección MÚLTIPLE (Ctrl/Shift + clic) para operar en bloque."""
    def __init__(self, on_reorder=None, parent=None):
        super().__init__(parent)
        self.on_reorder = on_reorder
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)

    def startDrag(self, supportedActions):
        from PySide6.QtGui import QDrag, QPixmap, QPainter
        from PySide6.QtCore import Qt, QPoint
        
        drag = QDrag(self)
        drag.setMimeData(self.mimeData(self.selectedItems()))
        
        item = self.currentItem()
        if item:
            rect = self.visualItemRect(item)
            pixmap = QPixmap(rect.size())
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            # Hacer que el pixmap sea semitransparente
            painter.setOpacity(0.5)
            self.render(painter, QPoint(0, 0), rect)
            painter.end()
            
            drag.setPixmap(pixmap)
            # Centrar el puntero del ratón en la imagen arrastrada
            drag.setHotSpot(QPoint(pixmap.width() // 2, pixmap.height() // 2))
            
        drag.exec(supportedActions)

    def dropEvent(self, event):
        """Al soltar NO movemos las filas aquí: calculamos el punto de inserción
        y las filas arrastradas (pueden ser varias con la selección múltiple) y
        avisamos al panel, que empuja un comando al historial; la lista se
        reconstruye sola al notificarse el cambio (sin movimientos visuales que
        haya que revertir, como pasaba con el InternalMove de una sola fila)."""
        if event.source() is not self:
            return
        index = self.indexAt(event.position().toPoint())
        if index.isValid():
            fila_destino = index.row()
            if self.dropIndicatorPosition() == QAbstractItemView.BelowItem:
                fila_destino += 1
        else:
            fila_destino = self.count()   # soltado bajo la última fila
        filas = sorted(self.row(it) for it in self.selectedItems())
        event.accept()
        if filas and self.on_reorder:
            self.on_reorder(filas, fila_destino)


class LayersPanel(QWidget):
    def __init__(self, canvas):
        super().__init__()
        self.canvas = canvas

        # 🎨 Sintonía con el tema oscuro del panel de Historial
        self.setStyleSheet("background-color: %s; color: %s;" % (theme.BG_WINDOW, theme.TEXT))

        # Diseño vertical compacto
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(4)

        # Modo de fusión de la capa activa, A LA VISTA (antes solo estaba dentro
        # del diálogo de Propiedades y costaba dar con él). Aplica el mismo
        # comando deshacible que el diálogo. Se sincroniza al cambiar de capa,
        # de pestaña y con deshacer/rehacer (_sync_blend_combo).
        modo_row = QHBoxLayout()
        modo_row.setSpacing(4)
        modo_row.setContentsMargins(0, 0, 0, 0)
        # ✨ Botón fx (efectos de capa) al inicio de esta fila, luego un separador
        # y el "Modo:" con su combo. Los efectos ya puestos se gestionan en la
        # sublista fx de cada fila.
        self.btn_fx = self._make_btn(
            ":/icons/layer_fx.png", "fx", t("layer.fx.add", default="Efectos de capa"),
            self._show_fx_menu)
        modo_row.addWidget(self.btn_fx)
        _fx_sep = QFrame()
        _fx_sep.setFrameShape(QFrame.VLine)
        _fx_sep.setFixedWidth(8)
        _fx_sep.setStyleSheet("color: %s;" % theme.BORDER)
        modo_row.addWidget(_fx_sep)
        lbl_modo = QLabel(t("opt.lbl.mode"))
        modo_row.addWidget(lbl_modo)
        self.blend_combo = QComboBox()
        self.blend_combo.setStyleSheet(theme.combobox_qss())
        self.blend_combo.setToolTip(t("layer.tip.blend"))
        for nombre, modo in blend_modes():
            self.blend_combo.addItem(nombre, modo)
        # 'activated' solo se emite por interacción del USUARIO (no al
        # sincronizar por código), así el refresco no re-aplica el modo.
        self.blend_combo.activated.connect(self._on_blend_combo)
        modo_row.addWidget(self.blend_combo, 1)
        layout.addLayout(modo_row)

        # Lista visual de capas (mismo estilo que el panel de Historial)
        self.list_widget = LayerListWidget(on_reorder=self.on_layer_dragged)
        self.list_widget.setStyleSheet(
            theme.list_qss()
            + """
            QListWidget::item {
                margin: 0px;
            }
        """)
        self.list_widget.currentRowChanged.connect(self.on_layer_selected)
        self.list_widget.itemSelectionChanged.connect(self.on_selection_changed)
        # Doble clic en una fila = Propiedades de capa (nombre, opacidad,
        # bloqueo…), como en otros editores. El primer clic ya activó la capa.
        self.list_widget.itemDoubleClicked.connect(lambda _it: self.show_properties())
        layout.addWidget(self.list_widget)

        # =====================================================================
        # BOTONERA: solo iconos (con fallback de texto hasta tener los .png)
        # Iconos esperados en la carpeta icons/:
        #   layer_add.png, layer_remove.png, layer_duplicate.png,
        #   layer_merge.png, layer_up.png, layer_down.png, layer_properties.png
        # =====================================================================
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(2)
        btn_layout.setContentsMargins(0, 0, 0, 0)

        self.btn_add = self._make_btn(
            ":/icons/layer_add.png", "+", t("layer.add"), self.add_layer)
        self.btn_remove = self._make_btn(
            ":/icons/layer_remove.png", "−", t("layer.remove"), self.remove_layer)
        self.btn_duplicate = self._make_btn(
            ":/icons/layer_duplicate.png", "⧉", t("layer.duplicate"), self.duplicate_layer)
        # 📁 Agrupar la selección en una carpeta (sin icono propio: glifo).
        self.btn_group = self._make_btn(
            ":/icons/layer_group.png", "▣", t("layer.group_new"), self.group_selection)
        self.btn_merge = self._make_btn(
            ":/icons/layer_merge.png", "⤓", t("layer.merge_down"), self.merge_down)
        self.btn_up = self._make_btn(
            ":/icons/layer_up.png", "▲", t("layer.move_up"), self.move_up)
        self.btn_down = self._make_btn(
            ":/icons/layer_down.png", "▼", t("layer.move_down"), self.move_down)
        self.btn_properties = self._make_btn(
            ":/icons/layer_properties.png", "⚙", t("layer.properties"), self.show_properties)

        for btn in (self.btn_add, self.btn_remove, self.btn_duplicate,
                    self.btn_group, self.btn_merge, self.btn_up, self.btn_down,
                    self.btn_properties):
            btn_layout.addWidget(btn)

        layout.addLayout(btn_layout)

        # Refresco en vivo de las miniaturas: mientras se pinta sobre una capa,
        # 'notify_layers_changed' no se dispara (solo al cerrar un comando), así
        # que un temporizador ligero mantiene las miniaturas al día en tiempo real.
        self._thumb_rows = []   # [(layer, QLabel)] de las filas actuales
        self._thumb_timer = QTimer(self)
        self._thumb_timer.setInterval(600)
        self._thumb_timer.timeout.connect(self._refresh_thumbnails)
        self._thumb_timer.start()

        # Sincronizar con el estado inicial
        self.update_layer_list()

    def _frame_thumb(self, p, w, h, highlight):
        """Dibuja el marco de la miniatura: azul de 2 px si es el destino de
        edición activo, gris de 1 px en caso contrario."""
        if highlight:
            # Azul claro: destaca tanto sobre el panel oscuro como sobre el
            # fondo azul de la fila seleccionada.
            pen = QPen(QColor(theme.ACCENT_BRIGHT)); pen.setWidth(2)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawRect(1, 1, w - 2, h - 2)
        else:
            p.setPen(QPen(QColor(theme.BORDER)))
            p.setBrush(Qt.NoBrush)
            p.drawRect(0, 0, w - 1, h - 1)

    def _thumb_pixmap(self, image, highlight=False):
        """Miniatura de la capa sobre un tablero de transparencia (mismo tono y
        tamaño que las miniaturas de las pestañas) y un marco, para que
        toda capa (incluidas las vacías/transparentes) muestre siempre algo.
        'highlight' resalta el marco en azul cuando es el destino de edición."""
        src = QPixmap.fromImage(image).scaled(50, 50, Qt.KeepAspectRatio,
                                              Qt.SmoothTransformation)
        w, h = max(1, src.width()), max(1, src.height())
        out = QPixmap(w, h)
        out.fill(Qt.transparent)
        p = QPainter(out)
        cell = 4
        light, dark = QColor(200, 200, 200), QColor(160, 160, 160)
        for gy, y in enumerate(range(0, h, cell)):
            for gx, x in enumerate(range(0, w, cell)):
                p.fillRect(x, y, cell, cell, light if (gx + gy) % 2 == 0 else dark)
        p.drawPixmap(0, 0, src)
        self._frame_thumb(p, w, h, highlight)
        p.end()
        return out

    def _mask_thumb_pixmap(self, mask, highlight=False):
        """Miniatura de la máscara (escala de grises) a tamaño fijo 50x50, con
        marco. 'highlight' la resalta en azul si es el destino de edición."""
        src = QPixmap.fromImage(mask).scaled(50, 50, Qt.KeepAspectRatio,
                                             Qt.SmoothTransformation)
        w, h = max(1, src.width()), max(1, src.height())
        out = QPixmap(w, h)
        out.fill(QColor(40, 40, 40))
        p = QPainter(out)
        p.drawPixmap(0, 0, src)
        self._frame_thumb(p, w, h, highlight)
        p.end()
        return out

    def _refresh_thumbnails(self):
        """Re-renderiza las miniaturas de las filas visibles (refresco en vivo)."""
        if not self.isVisible():
            return
        for idx, layer, lbl, mask_lbl in self._thumb_rows:
            # 📁 El índice real viaja con la fila (con cabeceras de grupo y
            # plegado ya no puede deducirse de la posición).
            hl_layer, hl_mask = self._thumb_highlights(layer, idx)
            try:
                lbl.setPixmap(self._thumb_pixmap(layer.render_with_effects(), hl_layer))
                if mask_lbl is not None and layer.mask is not None:
                    mask_lbl.setPixmap(self._mask_thumb_pixmap(layer.mask, hl_mask))
            except RuntimeError:
                pass   # el widget de la fila pudo destruirse entre refrescos

    def _thumb_highlights(self, layer, layer_index):
        """Devuelve (resaltar_capa, resaltar_máscara) para la capa dada: solo la
        capa activa se resalta, en su miniatura de capa o de máscara según el
        modo de edición de máscara."""
        c = self.canvas
        is_active = (layer_index == c.active_layer_index)
        mask_mode = getattr(c, 'mask_edit_active', False)
        return (is_active and not mask_mode,
                is_active and mask_mode and layer.has_mask())

    def _select_target(self, layer_index, edit_mask):
        """Elige qué se edita al pulsar una miniatura: los píxeles de la capa o
        su máscara. Activa esa capa y refresca el resaltado."""
        if not (0 <= layer_index < len(self.canvas.layers)):
            return
        self.canvas.active_layer_index = layer_index
        self.canvas.selected_layer_indices = [layer_index]
        layer = self.canvas.layers[layer_index]
        self.canvas.mask_edit_active = bool(edit_mask) and layer.has_mask()
        # Mover la selección de la lista SIN disparar on_layer_selected (que
        # repondría el modo a 'píxeles'); refrescar resaltado en sitio.
        row = self._row_of_layer(layer_index)
        if row is not None:
            self.list_widget.blockSignals(True)
            self.list_widget.setCurrentRow(row)
            self.list_widget.blockSignals(False)
        self._refresh_thumbnails()
        self._refresh_button_states()
        self.canvas.update()
        self._notify_active_layer_changed()

    def _make_btn(self, icon_path, fallback_text, tooltip, slot):
        """Crea un botón compacto de solo-icono con el estilo iluminado azul
        del panel de Historial: borde azul cuando está activo, apagado si no."""
        btn = QPushButton()
        if QFile.exists(icon_path):
            btn.setIcon(theme.icono(icon_path))
        else:
            btn.setText(fallback_text)
        btn.setToolTip(tooltip)
        btn.setFixedSize(26, 26)
        btn.setStyleSheet(theme.panel_action_button_qss())
        btn.clicked.connect(slot)
        return btn

    # =========================================================================
    # ✨ EFECTOS DE CAPA (fx): sublista por capa + añadir/editar/togglear/quitar.
    # Todo pasa por LayerEffectsCommand (deshacible por parámetros, sin píxeles).
    # =========================================================================

    def _build_fx_rows(self, container, layer, layer_index):
        """Añade a 'container' un renglón por cada efecto de la capa."""
        from widgets.layer_effects_ui import nombre_efecto
        for fx_index, effect in enumerate(layer.effects):
            fx_row = QHBoxLayout()
            fx_row.setContentsMargins(24, 0, 0, 0)   # sangría bajo la capa
            fx_row.setSpacing(4)

            # Orden (coherente con la fila de capa): quitar (×) a la IZQUIERDA,
            # y la casilla de ocultar/mostrar a la DERECHA (donde está la de
            # visibilidad de la capa), para no confundir ocultar con eliminar.
            rm = QPushButton("×")
            rm.setFixedSize(18, 18)
            rm.setStyleSheet(theme.panel_action_button_qss())
            rm.setToolTip(t("fx.tip.remove", default="Quitar efecto"))
            rm.clicked.connect(
                lambda _c=False, li=layer_index, fi=fx_index: self._remove_effect(li, fi))
            fx_row.addWidget(rm)

            name_lbl = _ClickableLabel(nombre_efecto(effect))
            name_lbl.setStyleSheet(theme.value_label_qss())
            name_lbl.setCursor(Qt.PointingHandCursor)
            name_lbl.setToolTip(t("fx.tip.edit", default="Editar efecto"))
            name_lbl.clicked.connect(
                lambda li=layer_index, fi=fx_index: self._edit_effect(li, fi))
            fx_row.addWidget(name_lbl)
            fx_row.addStretch()

            chk = QCheckBox()
            chk.setStyleSheet(theme.checkbox_qss())
            chk.setChecked(bool(getattr(effect, "activo", True)))
            chk.setToolTip(t("fx.tip.toggle", default="Mostrar/ocultar efecto"))
            chk.toggled.connect(
                lambda _checked, li=layer_index, fi=fx_index: self._toggle_effect(li, fi))
            fx_row.addWidget(chk)

            container.addLayout(fx_row)

    def _fx_command(self, layer_index, mutate):
        """Empuja un LayerEffectsCommand: clona la lista antes, aplica 'mutate'
        sobre la copia 'after' y registra el cambio (deshacible)."""
        if not (0 <= layer_index < len(self.canvas.layers)):
            return
        layer = self.canvas.layers[layer_index]
        from models.layer_effects import clonar_efectos
        from models.layer_commands import LayerEffectsCommand
        before = clonar_efectos(layer.effects)
        after = clonar_efectos(layer.effects)
        mutate(after)
        # No registrar un paso vacío si la mutación no cambió nada.
        if [e.to_dict() for e in after] == [e.to_dict() for e in before]:
            return
        self.canvas.undo_stack.push(
            LayerEffectsCommand(self.canvas, layer_index, before, after))

    def _toggle_effect(self, layer_index, fx_index):
        def mutate(after):
            if 0 <= fx_index < len(after):
                after[fx_index].activo = not after[fx_index].activo
        self._fx_command(layer_index, mutate)

    def _remove_effect(self, layer_index, fx_index):
        def mutate(after):
            if 0 <= fx_index < len(after):
                del after[fx_index]
        self._fx_command(layer_index, mutate)

    def _edit_effect(self, layer_index, fx_index):
        if not (0 <= layer_index < len(self.canvas.layers)):
            return
        layer = self.canvas.layers[layer_index]
        if not (0 <= fx_index < len(layer.effects)):
            return
        # Activar la capa (y reflejarlo en la selección del panel) y abrir el
        # panel unificado de efectos con ESTE efecto ya seleccionado.
        self._select_target(layer_index, False)
        win = self.window()
        if hasattr(win, "open_layer_effects"):
            win.open_layer_effects(getattr(layer.effects[fx_index], "tipo", None))

    def _show_fx_menu(self):
        """Menú del botón fx: efectos disponibles para añadir a la capa activa,
        y debajo la acción de FUSIONAR (hornear) los efectos en la capa."""
        if not self.canvas or self.canvas.get_active_layer() is None:
            return
        from PySide6.QtWidgets import QMenu
        from widgets.layer_effects_ui import efectos_disponibles
        menu = QMenu(self)
        for tipo, nombre in efectos_disponibles():
            act = menu.addAction(nombre)
            act.triggered.connect(lambda _c=False, tp=tipo: self._add_effect(tp))
        menu.addSeparator()
        acc_merge = menu.addAction(t("menu.layers.merge_fx"))
        layer = self.canvas.get_active_layer_obj()
        acc_merge.setEnabled(bool(layer is not None and getattr(layer, "effects", None)))
        acc_merge.triggered.connect(self._merge_effects)
        menu.exec(self.btn_fx.mapToGlobal(self.btn_fx.rect().bottomLeft()))

    def _merge_effects(self):
        """Delegación en la ventana principal: es quien confirma el rasterizado
        si la capa es de texto (mismo flujo que la entrada del menú Capas)."""
        win = self.window()
        if hasattr(win, "layer_merge_effects"):
            win.layer_merge_effects()

    def _add_effect(self, tipo):
        win = self.window()
        if hasattr(win, "open_layer_effects"):
            win.open_layer_effects(tipo)

    def _schedule_update(self):
        """Reconstruye la lista en el SIGUIENTE ciclo del bucle de eventos,
        NUNCA en mitad de una señal de un widget de la propia lista. Motivo
        (crash real): al pulsar la casilla de visibilidad, el comando notifica
        y update_layer_list hacía list_widget.clear() DENTRO de la señal
        'toggled', destruyendo la casilla EMISORA con su frame de C++ aún en
        la pila -> segfault en shiboken (PySide 6.11; mismo patrón que el
        gotcha de menu.clear() con QWidgetAction). Coalescente: varias
        notificaciones seguidas -> una sola reconstrucción."""
        if getattr(self, "_update_programado", False):
            return
        self._update_programado = True
        QTimer.singleShot(0, self._deferred_update)

    def _deferred_update(self):
        self._update_programado = False
        try:
            if self.canvas is None:
                return
            self.update_layer_list()
        except RuntimeError:
            pass  # el canvas o el panel ya no existen (pestaña cerrada)

    def update_layer_list(self):
        # 🔗 Registramos el callback de sincronización en el canvas actual.
        # Así, cuando un comando de deshacer/rehacer modifique las capas
        # (incluso desde Ctrl+Z o el panel de Historial), este panel se refresca.
        # Es idempotente: reasignarlo en cada refresco cubre el cambio de pestaña.
        # OJO: SIEMPRE la versión DIFERIDA (_schedule_update), nunca
        # update_layer_list directo: los comandos notifican dentro de señales
        # de widgets de esta lista y reconstruirla ahí segfaultea (ver arriba).
        self.canvas.layers_changed_callback = self._schedule_update

        # Si la capa activa ya no tiene máscara, salir del modo de edición de máscara
        self.canvas.validate_mask_edit()

        # Conservar la posición del scroll: reconstruir la lista la devolvía
        # arriba del todo, y con muchas capas (p. ej. un PSD) pulsar una casilla
        # de visibilidad hacía "saltar" el panel a la primera capa.
        scroll_prev = self.list_widget.verticalScrollBar().value()

        # Bloqueamos señales para evitar que el cambio de lista dispare eventos de selección
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        self._thumb_rows = []   # se reconstruye con las filas nuevas

        # Nombre visible de cada modo de fusión, para señalarlo en la fila
        nombres_modo = {modo: nombre for nombre, modo in blend_modes()}
        modo_normal = QPainter.CompositionMode.CompositionMode_SourceOver

        # 📁 Grupos: al recorrer de arriba abajo, cuando la cadena de grupos de
        # una capa diverge de la de la fila anterior, ahí EMPIEZAN grupos
        # nuevos y se emiten sus filas de cabecera (los miembros de un grupo
        # son contiguos por invariante, así que la cabecera cae siempre justo
        # encima de su primera capa). Bajo un grupo PLEGADO no se emite nada.
        from models.layer import cadena_de_grupos
        cadena_anterior = []

        # Orden inverso: La capa 0 es la del fondo, se muestra abajo en la lista
        for i in reversed(range(len(self.canvas.layers))):
            layer = self.canvas.layers[i]

            cadena = list(reversed(cadena_de_grupos(layer)))   # fuera → dentro
            comun = 0
            while (comun < len(cadena) and comun < len(cadena_anterior)
                   and cadena[comun] is cadena_anterior[comun]):
                comun += 1
            for depth in range(comun, len(cadena)):
                if all(a.expanded for a in cadena[:depth]):
                    self._add_group_row(cadena[depth], depth)
            cadena_anterior = cadena
            if not all(g.expanded for g in cadena):
                continue   # capa oculta bajo un grupo plegado

            hl_layer, hl_mask = self._thumb_highlights(layer, i)

            # Crear widget para la fila
            row_widget = QWidget()
            row_widget.setStyleSheet("background: transparent;")
            # Columna: fila principal [miniatura | texto | casilla] y, debajo, la
            # sublista de EFECTOS de capa (fx) si la capa tiene alguno.
            row_col = QVBoxLayout(row_widget)
            # 📁 Sangría según la profundidad de anidamiento de la capa.
            row_col.setContentsMargins(6 + 14 * len(cadena), 2, 6, 2)
            row_col.setSpacing(2)
            row_layout = QHBoxLayout()
            row_layout.setContentsMargins(0, 0, 0, 0)

            # Checkbox de visibilidad
            # Usamos 'toggled' (emite bool) en vez de 'stateChanged' (emite int)
            check = QCheckBox()
            # Estilo del tema: casilla SIEMPRE visible (caja redondeada cuando
            # está desactivada, caja azul con check cuando está activada), en vez
            # del indicador nativo cuyo estado desmarcado se perdía sobre el fondo.
            check.setStyleSheet(theme.checkbox_qss())
            check.setChecked(layer.visible)
            check.toggled.connect(lambda checked, idx=i: self.toggle_visibility(idx, checked))

            # Miniatura de la capa (clic = editar sus PÍXELES). Refresco en vivo.
            thumb_label = _ClickableLabel()
            # Miniatura = render de la capa CON efectos (para el texto usa su
            # render real, no el dummy 1×1; y refleja sombra/trazo si los tiene).
            thumb_label.setPixmap(self._thumb_pixmap(layer.render_with_effects(), hl_layer))
            thumb_label.setToolTip(t("layer.tip.image"))
            thumb_label.clicked.connect(lambda idx=i: self._select_target(idx, False))

            # Miniatura de la máscara (si la hay): clic = editar la MÁSCARA.
            mask_label = None
            if layer.has_mask():
                mask_label = _ClickableLabel()
                mask_label.setPixmap(self._mask_thumb_pixmap(layer.mask, hl_mask))
                mask_label.setToolTip(t("layer.tip.mask"))
                mask_label.clicked.connect(lambda idx=i: self._select_target(idx, True))

            self._thumb_rows.append((i, layer, thumb_label, mask_label))

            # Nombre en su propia línea y, si hay extras (modo de fusión y/u
            # opacidad), una SEGUNDA línea pequeña en texto tenue debajo. En una
            # sola línea los extras se comían el nombre (la etiqueta elide con
            # '…' enseguida); en dos líneas cada una se recorta por separado y
            # el nombre siempre se ve. El nombre completo queda en el tooltip.
            extras = []
            if layer.blend_mode != modo_normal and layer.blend_mode in nombres_modo:
                extras.append(nombres_modo[layer.blend_mode])
            if layer.opacity < 100:
                extras.append(f"{layer.opacity}%")
            # 🔒 Bloqueos de píxeles/posición: candado en la línea de extras.
            if getattr(layer, "pixels_locked", False) or getattr(layer, "position_locked", False):
                extras.append("🔒")
            # ✂️ Máscara de recorte: flecha delante del nombre (la capa se
            # recorta a la de debajo), como el sangrado de otros editores.
            prefijo = "↳ " if getattr(layer, "clipped", False) else ""
            lbl_name = _ElideLabel(prefijo + layer.name)
            lbl_name.setToolTip(layer.name)

            texto_col = QVBoxLayout()
            texto_col.setContentsMargins(0, 0, 0, 0)
            texto_col.setSpacing(0)
            texto_col.addStretch()
            texto_col.addWidget(lbl_name)
            if extras:
                lbl_extras = _ElideLabel(", ".join(extras))
                lbl_extras.setStyleSheet(theme.value_label_qss())
                lbl_extras.setToolTip(", ".join(extras))
                texto_col.addWidget(lbl_extras)
            texto_col.addStretch()

            # Orden: miniatura de capa, [miniatura de máscara], columna de
            # texto, y la casilla de visibilidad al final (a la derecha).
            row_layout.addWidget(thumb_label)
            if mask_label is not None:
                row_layout.addWidget(mask_label)
            row_layout.addLayout(texto_col)
            row_layout.addStretch()
            row_layout.addWidget(check)
            row_col.addLayout(row_layout)

            # ✨ Sublista de efectos de capa (fx): un renglón por efecto con
            # casilla de activo, nombre (clic = editar) y botón de quitar.
            if getattr(layer, "effects", None):
                self._build_fx_rows(row_col, layer, i)

            item = QListWidgetItem(self.list_widget)
            # Altura de fila ajustada a la miniatura (50 px) con poco margen
            # arriba/abajo. La ANCHURA no se pide al contenido: la fila se
            # estira al ancho del panel y el nombre se recorta con '…' si no
            # cabe (con el ancho del contenido, los nombres largos sacaban la
            # casilla de visibilidad fuera de la vista, con scroll horizontal).
            hint = row_widget.sizeHint()
            item.setSizeHint(QSize(40, max(hint.height(), 58)))
            # 📁 La fila lleva su dato ("layer", índice real): con las cabeceras
            # de grupo y el plegado, la fila YA NO se corresponde con
            # total-1-índice; todo el mapeo fila↔capa usa este dato.
            item.setData(Qt.ItemDataRole.UserRole, ("layer", i))
            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, row_widget)

        # Restaurar la selección visual: la capa activa como fila actual más el
        # resto de la selección múltiple. Si la activa quedó fuera de la
        # selección guardada (comandos de una sola capa que movieron la activa
        # sin saber de selecciones múltiples), la selección se repliega a la activa.
        total = len(self.canvas.layers)
        activo = self.canvas.active_layer_index
        seleccion = sorted(i for i in getattr(self.canvas, 'selected_layer_indices', [])
                           if 0 <= i < total)
        if activo not in seleccion:
            seleccion = [activo]
        self.canvas.selected_layer_indices = seleccion
        # 📁 Con cabeceras y plegado la fila se busca por su dato; una capa
        # oculta bajo un grupo plegado no tiene fila (se omite el reflejo).
        fila_activa = self._row_of_layer(activo)
        if fila_activa is not None:
            self.list_widget.setCurrentRow(fila_activa)
        for i in seleccion:
            fila = self._row_of_layer(i)
            if fila is not None:
                self.list_widget.item(fila).setSelected(True)
        self.list_widget.blockSignals(False)

        # Reponer el scroll donde estaba (Qt lo acota solo si ahora hay menos filas)
        self.list_widget.verticalScrollBar().setValue(scroll_prev)

        # Actualizar qué botones tienen sentido según la posición de la capa activa
        self._refresh_button_states()
        self._sync_blend_combo()
        # La capa activa pudo cambiar por un comando (añadir/quitar, deshacer...)
        # sin pasar por on_layer_selected (las señales van bloqueadas): avisar.
        self._notify_active_layer_changed()

    # =========================================================================
    # 📁 GRUPOS DE CAPAS (carpetas): cabeceras, plegado y operaciones
    # =========================================================================

    def _row_of_layer(self, layer_index):
        """Fila del QListWidget que muestra la capa dada, o None si no tiene
        fila (p. ej. está dentro de un grupo plegado)."""
        for r in range(self.list_widget.count()):
            d = self.list_widget.item(r).data(Qt.ItemDataRole.UserRole)
            if d and d[0] == "layer" and d[1] == layer_index:
                return r
        return None

    def _add_group_row(self, group, depth):
        """Fila de CABECERA de un grupo: flecha de plegado, nombre (clic =
        seleccionar sus capas) y ojo de visibilidad. La fila no es seleccionable
        ni arrastrable; sus operaciones van en el menú contextual."""
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(6 + 14 * depth, 1, 6, 1)
        lay.setSpacing(4)

        fold = QPushButton("▼" if group.expanded else "►")
        fold.setFixedSize(18, 18)
        fold.setStyleSheet(theme.panel_action_button_qss())
        fold.setToolTip(t("layer.tip.group_fold"))
        fold.clicked.connect(lambda _c=False, g=group: self._toggle_group_fold(g))
        lay.addWidget(fold)

        name = _ClickableLabel(f"📁 {group.name}")
        name.setStyleSheet(f"color: {theme.TEXT}; font-weight: bold; background: transparent;")
        name.setCursor(Qt.PointingHandCursor)
        name.setToolTip(t("layer.tip.group_select"))
        name.clicked.connect(lambda g=group: self._select_group(g))
        lay.addWidget(name)
        lay.addStretch()

        check = QCheckBox()
        check.setStyleSheet(theme.checkbox_qss())
        check.setChecked(group.visible)
        check.setToolTip(t("layer.tip.group_visible"))
        check.toggled.connect(
            lambda checked, g=group: self._toggle_group_visibility(g, checked))
        lay.addWidget(check)

        # Menú contextual de la cabecera (renombrar, desagrupar, mover...)
        w.setContextMenuPolicy(Qt.CustomContextMenu)
        w.customContextMenuRequested.connect(
            lambda pos, g=group, ww=w: self._group_menu(g, ww.mapToGlobal(pos)))

        item = QListWidgetItem(self.list_widget)
        item.setSizeHint(QSize(40, 26))
        # Ni seleccionable ni arrastrable: solo sus controles interactúan.
        item.setFlags(Qt.ItemIsEnabled)
        item.setData(Qt.ItemDataRole.UserRole, ("group", group))
        self.list_widget.addItem(item)
        self.list_widget.setItemWidget(item, w)

    def _toggle_group_fold(self, group):
        """Pliega/despliega la carpeta. Solo estado de UI: no pasa por el
        historial ni ensucia el documento. La reconstrucción va DIFERIDA
        (el botón emisor vive dentro de la lista que se reconstruye)."""
        group.expanded = not group.expanded
        self._schedule_update()

    def _toggle_group_visibility(self, group, visible):
        from models.layer_commands import GroupVisibilityCommand
        if bool(visible) == group.visible:
            return
        self.canvas.undo_stack.push(
            GroupVisibilityCommand(self.canvas, group, visible))

    def _select_group(self, group):
        """Selecciona TODAS las capas del grupo (con la más alta como activa):
        así los botones de eliminar/duplicar/subir/bajar operan sobre la
        carpeta entera con la maquinaria de selección múltiple de siempre."""
        from models.layer import miembros_de_grupo
        idxs = miembros_de_grupo(self.canvas.layers, group)
        if not idxs:
            return
        self.canvas.active_layer_index = idxs[-1]
        self.canvas.selected_layer_indices = list(idxs)
        self.canvas.mask_edit_active = False
        self.list_widget.blockSignals(True)
        fila_activa = self._row_of_layer(idxs[-1])
        if fila_activa is not None:
            self.list_widget.setCurrentRow(fila_activa)
        for r in range(self.list_widget.count()):
            it = self.list_widget.item(r)
            d = it.data(Qt.ItemDataRole.UserRole)
            it.setSelected(bool(d and d[0] == "layer" and d[1] in idxs))
        self.list_widget.blockSignals(False)
        self._refresh_thumbnails()
        self._refresh_button_states()
        self._sync_blend_combo()
        self.canvas.update()
        self._notify_active_layer_changed()

    def group_selection(self):
        """Botón ▣: agrupa las capas seleccionadas en una carpeta nueva."""
        from models.layer import grupos_del_lienzo
        from models.layer_commands import GroupLayersCommand
        seleccion = self._selected_indices()
        if not seleccion:
            return
        numero = len(grupos_del_lienzo(self.canvas.layers)) + 1
        nombre = t("layer.group_default", n=numero)
        self.canvas.undo_stack.push(
            GroupLayersCommand(self.canvas, seleccion, nombre))

    def _group_menu(self, group, global_pos):
        from PySide6.QtWidgets import QMenu
        from models.layer import miembros_de_grupo
        from models.layer_commands import (UngroupCommand, DuplicateGroupCommand,
                                           RemoveLayersCommand)
        idxs = miembros_de_grupo(self.canvas.layers, group)
        menu = QMenu(self)
        acc_ren = menu.addAction(t("layer.group.rename"))
        acc_ung = menu.addAction(t("layer.group.ungroup"))
        acc_dup = menu.addAction(t("layer.group.duplicate"))
        menu.addSeparator()
        acc_up = menu.addAction(t("layer.group.move_up"))
        acc_dn = menu.addAction(t("layer.group.move_down"))
        menu.addSeparator()
        acc_del = menu.addAction(t("layer.group.delete"))
        # No se puede dejar el lienzo sin capas.
        acc_del.setEnabled(len(idxs) < len(self.canvas.layers))
        elegido = menu.exec(global_pos)
        if elegido is acc_ren:
            self._rename_group(group)
        elif elegido is acc_ung:
            self.canvas.undo_stack.push(UngroupCommand(self.canvas, group))
        elif elegido is acc_dup:
            self.canvas.undo_stack.push(DuplicateGroupCommand(self.canvas, group))
        elif elegido is acc_up:
            self._mover_grupo(group, +1)
        elif elegido is acc_dn:
            self._mover_grupo(group, -1)
        elif elegido is acc_del and acc_del.isEnabled():
            self.canvas.undo_stack.push(RemoveLayersCommand(
                self.canvas, idxs, text=t("hist.del_group", name=group.name)))

    def _rename_group(self, group):
        from models.layer_commands import RenameGroupCommand
        dlg = FramelessDialog(self)
        dlg.setWindowTitle(t("layer.group.rename").rstrip("…"))
        dlg.setStyleSheet("QLabel { color: %s; }" % theme.TEXT
                          + theme.lineedit_qss()
                          + theme.dialog_button_qss("QDialogButtonBox QPushButton"))
        form = QFormLayout()
        editor = QLineEdit(group.name)
        form.addRow(t("dlg.group_name"), editor)
        botones = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botones.accepted.connect(dlg.accept)
        botones.rejected.connect(dlg.reject)
        form.addRow(botones)
        dlg.body_layout.addLayout(form)
        editor.setFocus()
        editor.selectAll()
        if dlg.exec():
            nuevo = editor.text().strip()
            if nuevo and nuevo != group.name:
                self.canvas.undo_stack.push(
                    RenameGroupCommand(self.canvas, group, nuevo))

    def _mover_grupo(self, group, delta):
        """Sube/baja el grupo ENTERO una posición: salta el bloque vecino
        completo (otra carpeta al mismo nivel o una capa suelta). Si el grupo
        está anidado y toca el borde de su carpeta padre, en vez de reordenar
        SALE de ella (se recuelga un nivel más arriba)."""
        from models.layer import miembros_de_grupo, cadena_de_grupos
        from models.layer_commands import ReorderLayersCommand
        layers = self.canvas.layers
        idxs = miembros_de_grupo(layers, group)
        if not idxs:
            return
        n = len(layers)
        lo, hi = idxs[0], idxs[-1]
        clave = "hist.move_group_up" if delta > 0 else "hist.move_group_down"
        texto = t(clave, name=group.name)

        vecino_idx = hi + 1 if delta > 0 else lo - 1
        fuera_de_pila = vecino_idx < 0 or vecino_idx >= n
        if not fuera_de_pila:
            vecino = layers[vecino_idx]
            fuera_del_padre = (group.parent is not None
                               and group.parent not in cadena_de_grupos(vecino))
        if fuera_de_pila or fuera_del_padre:
            # Borde: si está anidado, sale de la carpeta padre; si no, tope.
            if group.parent is None:
                return
            self.canvas.undo_stack.push(ReorderLayersCommand(
                self.canvas, list(range(n)), texto,
                parent_changes=[(group, group.parent.parent)]))
            return

        # Unidad vecina: la carpeta hermana COMPLETA a la que pertenezca el
        # vecino (mismo padre que este grupo), o la capa suelta.
        unidad = [vecino_idx]
        for g in cadena_de_grupos(vecino):
            if g is not group and g.parent is group.parent:
                unidad = miembros_de_grupo(layers, g)
                break
        if delta > 0:
            seg_lo, seg_hi = lo, unidad[-1]
            segmento = unidad + idxs
        else:
            seg_lo, seg_hi = unidad[0], hi
            segmento = idxs + unidad
        orden = (list(range(0, seg_lo)) + segmento + list(range(seg_hi + 1, n)))
        if orden == list(range(n)):
            return
        self.canvas.undo_stack.push(
            ReorderLayersCommand(self.canvas, orden, texto))

    def _sync_blend_combo(self):
        """Refleja en el combo del panel el modo de fusión de la capa activa
        (comparando por el CompositionMode guardado como dato, no por índice)."""
        if self.canvas is None or not (0 <= self.canvas.active_layer_index
                                       < len(self.canvas.layers)):
            return
        modo = self.canvas.layers[self.canvas.active_layer_index].blend_mode
        for i in range(self.blend_combo.count()):
            if self.blend_combo.itemData(i) == modo:
                self.blend_combo.setCurrentIndex(i)
                return
        self.blend_combo.setCurrentIndex(0)   # modo sin entrada (p. ej. de un PSD)

    def _on_blend_combo(self, idx):
        """Aplica el modo elegido en el combo a la capa activa, como un paso
        de deshacer (el mismo comando que usa el diálogo de Propiedades)."""
        if self.canvas is None or not self.canvas.layers:
            return
        index = self.canvas.active_layer_index
        layer = self.canvas.layers[index]
        nuevo = self.blend_combo.itemData(idx)
        if nuevo == layer.blend_mode:
            return
        from models.layer_commands import LayerPropertiesCommand
        self.canvas.undo_stack.push(LayerPropertiesCommand(
            self.canvas, index,
            layer.name, layer.name,
            layer.opacity, layer.opacity,
            layer.blend_mode, nuevo,
            layer.alpha_locked, layer.alpha_locked))

    def _selected_indices(self):
        """Índices reales (ascendentes) de las capas seleccionadas en el panel;
        si no hay ninguna válida, la capa activa."""
        n = len(self.canvas.layers)
        seleccion = sorted(i for i in getattr(self.canvas, 'selected_layer_indices', [])
                           if 0 <= i < n)
        return seleccion or [self.canvas.active_layer_index]

    def _refresh_button_states(self):
        """Desactiva los botones que no aplican según la selección actual
        (una o varias capas)."""
        idx = self.canvas.active_layer_index
        total = len(self.canvas.layers)
        sel = set(self._selected_indices())
        self.btn_remove.setEnabled(total > len(sel))
        # Fusionar exige que la capa activa y la inferior estén VISIBLES
        # (si no, se hornearían píxeles que no se ven).
        from models.layer import visible_para_fusion
        self.btn_merge.setEnabled(
            idx > 0 and visible_para_fusion(self.canvas.layers, idx)
            and visible_para_fusion(self.canvas.layers, idx - 1))
        # Subir/bajar en bloque: basta con que ALGUNA seleccionada tenga hueco
        self.btn_up.setEnabled(any(i + 1 < total and i + 1 not in sel for i in sel))
        self.btn_down.setEnabled(any(i - 1 >= 0 and i - 1 not in sel for i in sel))

    def toggle_visibility(self, index, visible):
        seleccion = self._selected_indices()
        if len(seleccion) > 1 and index in seleccion:
            # La casilla pulsada pertenece a la selección múltiple: se aplica a todas
            from models.layer_commands import SetLayersVisibilityCommand
            cmd = SetLayersVisibilityCommand(self.canvas, seleccion, visible)
        else:
            from models.layer_commands import ToggleVisibilityCommand
            cmd = ToggleVisibilityCommand(self.canvas, index, visible)
        self.canvas.undo_stack.push(cmd)

    def on_layer_selected(self, row):
        # Mapear de la fila del QListWidget al índice real vía el dato de la
        # fila (las cabeceras de grupo no son seleccionables, pero por si acaso).
        item = self.list_widget.item(row)
        d = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if not d or d[0] != "layer":
            return
        real_index = d[1]
        if 0 <= real_index < len(self.canvas.layers):
            self.canvas.active_layer_index = real_index
            # Seleccionar la fila apunta a los PÍXELES de la capa (para editar la
            # máscara se pulsa su miniatura). Refrescamos el resaltado en sitio.
            self.canvas.mask_edit_active = False
            self._refresh_thumbnails()
            self.canvas.update()
            self._refresh_button_states()
            self._sync_blend_combo()
            self._notify_active_layer_changed()

    def _notify_active_layer_changed(self):
        """Avisa a la ventana principal de que la capa activa cambió, para que
        sincronice el estado que depende de su TIPO (p. ej. el desplegable
        Modo de la herramienta de mover con capas de texto)."""
        win = self.window()
        if hasattr(win, '_on_active_layer_changed'):
            win._on_active_layer_changed()

    def on_selection_changed(self):
        """Guarda en el canvas los índices de TODAS las filas seleccionadas
        (selección múltiple con Ctrl/Shift). La capa activa la sigue fijando
        on_layer_selected a partir de la fila actual."""
        n = len(self.canvas.layers)
        seleccion = []
        for it in self.list_widget.selectedItems():
            d = it.data(Qt.ItemDataRole.UserRole)
            if d and d[0] == "layer" and 0 <= d[1] < n:
                seleccion.append(d[1])
        self.canvas.selected_layer_indices = sorted(seleccion)
        self._refresh_button_states()

    def _grupo_completo_de(self, seleccion):
        """Si la selección es EXACTAMENTE todas las capas de un grupo (incluidos
        sus subgrupos), devuelve ese grupo; si no, None."""
        from models.layer import miembros_de_grupo, grupos_del_lienzo
        selset = set(seleccion)
        for g in grupos_del_lienzo(self.canvas.layers):
            if set(miembros_de_grupo(self.canvas.layers, g)) == selset:
                return g
        return None

    def _mover_seleccion(self, seleccion, delta):
        """Empuja el comando que sube/baja en bloque la selección (una o varias
        capas). Si la selección es un grupo completo, mueve la carpeta entera;
        si no, cada capa avanza un puesto y su grupo se reasigna según sus
        vecinos nuevos (así se entra y se sale de las carpetas también con
        los botones ▲/▼)."""
        grupo = self._grupo_completo_de(seleccion)
        if grupo is not None:
            self._mover_grupo(grupo, delta)
            return
        from models.layer_commands import comando_mover_capas
        cmd = comando_mover_capas(self.canvas, seleccion, delta)
        if cmd is not None:
            self.canvas.undo_stack.push(cmd)

    def on_layer_dragged(self, filas, fila_destino):
        """Al soltar un arrastre: mueve las capas seleccionadas al punto de
        inserción y las asigna al grupo de destino — el grupo común más
        profundo de las dos capas vecinas a la inserción (soltar justo bajo la
        cabecera de un grupo abierto mete la capa en su cima; soltar fuera la
        saca). Un grupo COMPLETO arrastrado se recuelga entero, conservando su
        estructura interna."""
        from models.layer import cadena_de_grupos, grupo_comun, miembros_de_grupo
        lw = self.list_widget
        n = len(self.canvas.layers)

        def dato(r):
            it = lw.item(r)
            return it.data(Qt.ItemDataRole.UserRole) if it is not None else None

        indices = sorted({d[1] for d in (dato(f) for f in filas)
                          if d and d[0] == "layer" and 0 <= d[1] < n})
        if not indices:
            return
        selset = set(indices)

        # Punto de inserción en índices reales: encima de la primera capa que
        # haya en la lista a partir de la fila de destino (contando también las
        # arrastradas: la corrección de abajo las descuenta), o el fondo.
        destino = 0
        for r in range(fila_destino, lw.count()):
            d = dato(r)
            if d and d[0] == "layer":
                destino = d[1] + 1
                break

        # Grupo de destino: vecinos REALES (no arrastrados) de la inserción.
        arriba = abajo = None
        for r in range(fila_destino - 1, -1, -1):
            d = dato(r)
            if d and d[0] == "layer" and d[1] not in selset:
                arriba = self.canvas.layers[d[1]]
                break
        for r in range(fila_destino, lw.count()):
            d = dato(r)
            if d and d[0] == "layer" and d[1] not in selset:
                abajo = self.canvas.layers[d[1]]
                break
        cab = dato(fila_destino - 1) if fila_destino >= 1 else None
        cab = cab[1] if cab and cab[0] == "group" else None
        if (cab is not None and abajo is not None
                and cab in cadena_de_grupos(abajo)):
            grupo_destino = cab        # soltado bajo la cabecera: a la cima
        else:
            grupo_destino = grupo_comun(arriba, abajo)

        # Reasignaciones: un subárbol COMPLETO arrastrado se recuelga entero;
        # el resto de capas pasan directamente al grupo de destino.
        cambios_capa, cambios_padre, recolgados = [], [], set()
        for i in indices:
            capa = self.canvas.layers[i]
            completo = None
            for g in cadena_de_grupos(capa):    # de dentro a fuera
                if set(miembros_de_grupo(self.canvas.layers, g)) <= selset:
                    completo = g                # el más EXTERNO completo
                else:
                    break
            if completo is not None:
                if id(completo) not in recolgados:
                    recolgados.add(id(completo))
                    if completo.parent is not grupo_destino:
                        cambios_padre.append((completo, grupo_destino))
            elif getattr(capa, "group", None) is not grupo_destino:
                cambios_capa.append((capa, grupo_destino))

        # Nunca dejar caer una carpeta dentro de sí misma.
        if grupo_destino is not None:
            cadena_destino = grupo_destino.chain()
            if any(g in cadena_destino for g, _p in cambios_padre):
                return

        selset_l = list(indices)
        restantes = [i for i in range(n) if i not in selset]
        # El destino se corrige por las capas seleccionadas que había por debajo
        destino_adj = destino - sum(1 for i in selset_l if i < destino)
        destino_adj = max(0, min(destino_adj, len(restantes)))
        orden = restantes[:destino_adj] + selset_l + restantes[destino_adj:]
        if orden == list(range(n)) and not cambios_capa and not cambios_padre:
            return

        from models.layer_commands import ReorderLayersCommand
        if len(indices) == 1:
            nombre = self.canvas.layers[indices[0]].name
            texto = f"{t('hist.reorder_layer', default='Reordenar capa')} ({nombre})"
        else:
            texto = t("hist.reorder_layers", n=len(indices))
        self.canvas.undo_stack.push(ReorderLayersCommand(
            self.canvas, orden, texto,
            group_changes=cambios_capa, parent_changes=cambios_padre))

    # =========================================================================
    # ACCIONES — delegan en el Canvas, que empuja comandos deshacibles
    # al QUndoStack. El refresco visual llega vía notify_layers_changed(),
    # por lo que no hace falta llamar a update_layer_list() aquí.
    # =========================================================================

    def add_layer(self):
        self.canvas.add_layer_undoable()

    def remove_layer(self):
        seleccion = self._selected_indices()
        if len(seleccion) > 1:
            # No se puede dejar el lienzo sin capas: si están todas
            # seleccionadas se conserva la de más abajo
            if len(seleccion) >= len(self.canvas.layers):
                seleccion = seleccion[1:]
            from models.layer_commands import RemoveLayersCommand
            self.canvas.undo_stack.push(RemoveLayersCommand(self.canvas, seleccion))
        else:
            self.canvas.remove_active_layer()

    def duplicate_layer(self):
        seleccion = self._selected_indices()
        if len(seleccion) > 1:
            from models.layer_commands import DuplicateLayersCommand
            self.canvas.undo_stack.push(DuplicateLayersCommand(self.canvas, seleccion))
        else:
            self.canvas.duplicate_active_layer()

    def merge_down(self):
        self.canvas.merge_layer_down()

    def move_up(self):
        # Una o varias capas: misma vía (con grupos reasigna al cruzar carpetas)
        self._mover_seleccion(self._selected_indices(), +1)

    def move_down(self):
        self._mover_seleccion(self._selected_indices(), -1)

    def flatten(self):
        self.canvas.flatten_layers()

    def show_properties(self):
        layer = self.canvas.layers[self.canvas.active_layer_index]
        dialog = LayerPropertiesDialog(self.canvas, layer, self)
        dialog.exec()
        self.update_layer_list()  # Refrescar nombre y porcentaje de opacidad
