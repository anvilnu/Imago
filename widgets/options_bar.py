# widgets/options_bar.py
from i18n import t
from PySide6.QtWidgets import (QWidget, QStackedWidget, QComboBox, QLabel,
                               QToolBar, QSizePolicy)
from PySide6.QtCore import QSize, QFile
import theme

# Mixins con los paneles por familia (dibujo, trazados, texto, selección):
# viven en módulos propios para aligerar este archivo; DynamicOptionsBar los
# hereda y todo sigue accediéndose vía self.* igual que antes.
from widgets.opciones_dibujo import PanelesDibujo
from widgets.opciones_trazados import PanelesTrazados
from widgets.opciones_texto import PanelesTexto
from widgets.opciones_seleccion import PanelesSeleccion


class _ClipWrapper(QWidget):
    """Contenedor de recorte para el QStackedWidget de la barra de opciones.

    Engaña al QToolBar reportando ancho cero (para no forzar el ancho de la
    barra), pero en resizeEvent da al inner widget su ancho natural completo
    (nunca menos que su minimumSizeHint). Qt clipea automáticamente los hijos
    al rect del padre, así los controles no se comprimen ni se apilan."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0)
        self._inner = None

    def setInnerWidget(self, widget):
        self._inner = widget
        widget.setParent(self)
        widget.move(0, 0)
        widget.show()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_inner()

    def _update_inner(self):
        if self._inner is not None:
            sh_w = self._inner.sizeHint().width()
            natural_w = max(sh_w if sh_w > 0 else 0, self.width())
            self._inner.resize(natural_w, self.height())

    def adjustInnerSize(self):
        """Llamar cuando cambie la visibilidad de controles en un panel."""
        self._update_inner()

    def sizeHint(self):
        if self._inner is not None:
            h = self._inner.sizeHint().height()
            if h > 0:
                return QSize(0, h)
        return QSize(0, 26)

    def minimumSizeHint(self):
        return QSize(0, self.sizeHint().height())

class DynamicOptionsBar(PanelesDibujo, PanelesTrazados, PanelesTexto,
                        PanelesSeleccion, QToolBar):
    def __init__(self, main_window):
        super().__init__(t("opt.bar.title"), main_window)
        self.main_window = main_window
        self.setMovable(False)
        
        # 🛡️ Bandera protectora para evitar bucles infinitos al sincronizar
        self.is_syncing = False

        # El icono de flecha (down_arrow) viaja ahora dentro de los recursos
        # embebidos (:/icons/down_arrow.png), así que ya no hace falta generarlo
        # en disco al arrancar.

        # =========================================================================
        # 🛠️ SELECTOR GLOBAL DE HERRAMIENTA (SIEMPRE VISIBLE)
        # =========================================================================
        self.label_herramienta = QLabel(t("opt.bar.tool"))
        self.label_herramienta.setStyleSheet("margin-left: 6px; margin-right: 4px;")
        self.addWidget(self.label_herramienta)

        self.tool_combo = QComboBox()
        self.tool_combo.setIconSize(QSize(14, 14))
        self.tool_combo.setMaxVisibleItems(25)
        self.tool_combo.setFixedWidth(160)
        self.tool_combo.setStyleSheet(self._get_combo_style())
        
        # Mismo orden que el panel de Herramientas, por COLUMNAS de la rejilla
        # (la izquierda entera y luego la derecha), para que ambos cuenten la
        # misma historia. Si el usuario reordena el panel arrastrando botones,
        # reorder_tool_combo() reconstruye este combo con el orden nuevo.
        self.tools_list = [
            {"id": "select_rect", "name": t("tool.name.select_rect"), "icon": ":/icons/select_rect.png", "fallback": "⬚"},
            {"id": "select_lasso", "name": t("tool.name.select_lasso"), "icon": ":/icons/select_lasso.png", "fallback": "➰"},
            {"id": "select_ellipse", "name": t("tool.name.select_ellipse"), "icon": ":/icons/select_ellipse.png", "fallback": "⬭"},
            {"id": "pen", "name": t("tool.name.pen"), "icon": ":/icons/pen.png", "fallback": "✏️"},
            {"id": "pencil", "name": t("tool.name.pencil"), "icon": ":/icons/pencil.png", "fallback": "✎"},
            {"id": "airbrush", "name": t("tool.name.airbrush"), "icon": ":/icons/airbrush.png", "fallback": "💨"},
            {"id": "magic_wand", "name": t("tool.name.magic_wand"), "icon": ":/icons/magic_wand.png", "fallback": "🪄"},
            {"id": "clone", "name": t("tool.name.clone"), "icon": ":/icons/clone.png", "fallback": "🅢"},
            {"id": "dodge_burn", "name": t("tool.name.dodge_burn"), "icon": ":/icons/dodge_burn.png", "fallback": "🔆"},
            {"id": "sponge", "name": t("tool.name.sponge"), "icon": ":/icons/sponge.png", "fallback": "🧽"},
            {"id": "replace_color", "name": t("tool.name.replace_color"), "icon": ":/icons/replace_color.png", "fallback": "🎨"},
            {"id": "text", "name": t("tool.name.text"), "icon": ":/icons/text.png", "fallback": "🅣"},
            {"id": "line_curve", "name": t("tool.name.line_curve"), "icon": ":/icons/line_curve.png", "fallback": "〰"},
            {"id": "move", "name": t("tool.name.move"), "icon": ":/icons/move.png", "fallback": "✥"},
            {"id": "hand", "name": t("tool.name.hand"), "icon": ":/icons/hand.png", "fallback": "✋"},
            {"id": "crop", "name": t("tool.name.crop"), "icon": ":/icons/crop.png", "fallback": "✂"},
            {"id": "eraser", "name": t("tool.name.eraser"), "icon": ":/icons/eraser.png", "fallback": "🧽"},
            {"id": "bucket", "name": t("tool.name.bucket"), "icon": ":/icons/bucket.png", "fallback": "🪣"},
            {"id": "pen_path", "name": t("tool.name.pen_path"), "icon": ":/icons/pen_path.png", "fallback": "✒️"},
            {"id": "eyedropper", "name": t("tool.name.eyedropper"), "icon": ":/icons/eyedropper.png", "fallback": "💧"},
            {"id": "smudge", "name": t("tool.name.smudge"), "icon": ":/icons/smudge.png", "fallback": "👆"},
            {"id": "heal", "name": t("tool.name.heal"), "icon": ":/icons/heal.png", "fallback": "🩹"},
            {"id": "liquify", "name": t("tool.name.liquify"), "icon": ":/icons/liquify.png", "fallback": "🌀"},
            {"id": "gradient", "name": t("tool.name.gradient"), "icon": ":/icons/gradient.png", "fallback": "🌈"},
            {"id": "measure", "name": t("tool.name.measure"), "icon": ":/icons/measure.png", "fallback": "📏"},
            {"id": "shapes", "name": t("tool.name.shapes"), "icon": ":/icons/shapes.png", "fallback": "🔷"}
        ]

        for tool in self.tools_list:
            if QFile.exists(tool["icon"]):
                self.tool_combo.addItem(theme.icono(tool["icon"]), tool["name"], tool["id"])
            else:
                self.tool_combo.addItem(f"{tool['fallback']}  {tool['name']}", tool["id"])

        self.tool_combo.currentIndexChanged.connect(self.on_global_combo_changed)
        self.tool_combo.currentIndexChanged.connect(self.main_window.update_canvas_cursor)
        self.addWidget(self.tool_combo)
        
        # Separadores estéticos
        spacer_izq = QWidget()
        spacer_izq.setFixedWidth(12)
        self.addWidget(spacer_izq)

        self.linea_separadora = QWidget()
        self.linea_separadora.setFixedWidth(1)
        self.linea_separadora.setStyleSheet("background-color: %s; margin-top: 4px; margin-bottom: 4px;" % theme.BORDER)
        self.addWidget(self.linea_separadora)

        spacer_der = QWidget()
        spacer_der.setFixedWidth(4)
        self.addWidget(spacer_der)

        # =========================================================================
        # ARCHIVADOR DE SUB-PANELES (QStackedWidget)
        # =========================================================================
        self.stacked_widget = QStackedWidget()
        # _ClipWrapper recorta el stacked_widget al ancho disponible sin
        # comprimirlo: le da su ancho natural en resizeEvent y Qt se encarga
        # de clipear los hijos al rect del padre.
        self._panel_clip = _ClipWrapper()
        self._panel_clip.setInnerWidget(self.stacked_widget)
        self.addWidget(self._panel_clip)
        
        # Inicializamos los paneles independientes
        self.panel_pen = self.create_pen_panel()
        self.panel_eraser = self.create_eraser_panel()
        self.panel_bucket = self.create_bucket_panel()
        self.panel_shapes = self.create_shapes_panel()
        self.panel_pencil = self.create_pencil_panel()
        self.panel_eyedropper = self.create_eyedropper_panel()
        self.panel_selection = self.create_selection_panel()
        self.panel_move = self.create_move_panel()
        self.panel_hand = self.create_hand_panel()
        self.panel_crop = self.create_crop_panel()
        self.panel_magic_wand = self.create_magic_wand_panel()
        self.panel_clone = self.create_clone_panel()
        self.panel_text = self.create_text_panel()
        self.panel_pen_path = self.create_pen_path_panel()
        self.panel_airbrush = self.create_airbrush_panel()
        self.panel_gradient = self.create_gradient_panel()
        self.panel_smudge = self.create_smudge_panel()
        self.panel_replace_color = self.create_replace_color_panel()
        self.panel_dodge_burn = self.create_dodge_burn_panel()
        self.panel_sponge = self.create_sponge_panel()
        self.panel_liquify = self.create_liquify_panel()
        self.panel_heal = self.create_heal_panel()
        self.panel_line_curve = self.create_line_curve_panel()
        self.panel_measure = self.create_measure_panel()

        self.stacked_widget.addWidget(self.panel_pen)
        self.stacked_widget.addWidget(self.panel_eraser)
        self.stacked_widget.addWidget(self.panel_bucket)
        self.stacked_widget.addWidget(self.panel_shapes)
        self.stacked_widget.addWidget(self.panel_pencil)
        self.stacked_widget.addWidget(self.panel_eyedropper)
        self.stacked_widget.addWidget(self.panel_selection)
        self.stacked_widget.addWidget(self.panel_move)
        self.stacked_widget.addWidget(self.panel_hand)
        self.stacked_widget.addWidget(self.panel_crop)
        self.stacked_widget.addWidget(self.panel_magic_wand)
        self.stacked_widget.addWidget(self.panel_clone)
        self.stacked_widget.addWidget(self.panel_text)
        self.stacked_widget.addWidget(self.panel_pen_path)
        self.stacked_widget.addWidget(self.panel_airbrush)
        self.stacked_widget.addWidget(self.panel_gradient)
        self.stacked_widget.addWidget(self.panel_smudge)
        self.stacked_widget.addWidget(self.panel_replace_color)
        self.stacked_widget.addWidget(self.panel_dodge_burn)
        self.stacked_widget.addWidget(self.panel_sponge)
        self.stacked_widget.addWidget(self.panel_liquify)
        self.stacked_widget.addWidget(self.panel_heal)
        self.stacked_widget.addWidget(self.panel_line_curve)
        self.stacked_widget.addWidget(self.panel_measure)

        # Cada panel conserva su ancho natural (no se comprime). Cuando la
        # ventana es estrecha, el QStackedWidget recorta el panel por la derecha
        # en vez de amontonar los controles unos sobre otros.
        # Cada panel conserva su ancho natural (no se comprime). Cuando la
        # ventana es estrecha, el QStackedWidget recorta el panel por la derecha
        # en vez de amontonar los controles unos sobre otros.
        for _i in range(self.stacked_widget.count()):
            _p = self.stacked_widget.widget(_i)
            _p.setMinimumWidth(_p.sizeHint().width())

        # El QStackedLayout hereda el minimumWidth máximo de todos los paneles
        # (~1440 px) y lo propagaría como mínimo de ventana. Anulamos ese
        # mínimo explícitamente; _update_inner() sigue redimensionando el
        # stacked_widget a su tamaño natural para que los controles no se compriman.
        self.stacked_widget.setMinimumWidth(0)

        # Forzar recálculo de geometría ahora que los paneles están creados.
        self._panel_clip.updateGeometry()

        # Asignar un QStyledItemDelegate a todos los comboboxes para que el menú
        # desplegable no use el dibujado nativo y respete :hover en el CSS.
        from PySide6.QtWidgets import QStyledItemDelegate
        for combo in self.findChildren(QComboBox):
            combo.setItemDelegate(QStyledItemDelegate(combo))
    def _get_combo_style(self):
        return theme.combobox_qss()

    def _get_btn_style(self):
        return theme.small_button_qss()

    def _get_check_style(self):
        """Casilla con el azul de la app al marcar (en vez del naranja de acento
        del sistema), para que combine con el resto de la interfaz."""
        return theme.checkbox_qss()

    def _get_slider_style(self):
        return theme.slider_qss()

    def on_global_combo_changed(self, index):
        if self.is_syncing or index == -1: return
        tool_id = self.tool_combo.itemData(index)
        if self.main_window: self.main_window.set_tool(tool_id)

    def reorder_tool_combo(self, order_ids):
        """Reconstruye el combo global de herramienta en el orden dado (lista
        de tool_ids), tras reordenar el panel de Herramientas. Ids que no
        estén en el combo se ignoran y herramientas del combo no listadas se
        quedan al final (en su orden relativo actual). Conserva la selección."""
        actual = self.tool_combo.currentData()
        pos = {tid: i for i, tid in enumerate(order_ids)}
        self.tools_list.sort(key=lambda tl: pos.get(tl["id"], len(pos)))
        self.is_syncing = True
        # blockSignals: que la reconstrucción no dispare set_tool ni el cursor
        self.tool_combo.blockSignals(True)
        self.tool_combo.clear()
        for tool in self.tools_list:
            if QFile.exists(tool["icon"]):
                self.tool_combo.addItem(theme.icono(tool["icon"]), tool["name"], tool["id"])
            else:
                self.tool_combo.addItem(f"{tool['fallback']}  {tool['name']}", tool["id"])
        idx = self.tool_combo.findData(actual)
        if idx >= 0:
            self.tool_combo.setCurrentIndex(idx)
        self.tool_combo.blockSignals(False)
        self.is_syncing = False

    def show_panel_for_tool(self, tool_name):
        self.is_syncing = True
        for i in range(self.tool_combo.count()):
            if self.tool_combo.itemData(i) == tool_name:
                self.tool_combo.setCurrentIndex(i)
                break
        self.is_syncing = False

        if tool_name == "hand":
            self.stacked_widget.setCurrentWidget(self.panel_hand)
        elif tool_name == "crop":
            self.stacked_widget.setCurrentWidget(self.panel_crop)
        elif tool_name == "magic_wand":
            self.stacked_widget.setCurrentWidget(self.panel_magic_wand)
            self._sync_wand_mode_buttons()
        elif tool_name == "move":
            self.stacked_widget.setCurrentWidget(self.panel_move)
        elif tool_name in ("select_rect", "select_ellipse", "select_lasso"):
            self.stacked_widget.setCurrentWidget(self.panel_selection)
            self._sync_selection_mode_buttons()
            self._sync_selection_size_controls(tool_name)
        elif tool_name == "pen":
            self.stacked_widget.setCurrentWidget(self.panel_pen)
            if self.main_window and hasattr(self, 'brush_shape_combo'):
                self.main_window.update_brush_shape(self.brush_shape_combo.currentData())
                self.main_window.update_brush_opacity(self.brush_opacity_slider.value())
                self._set_brush_opacity_enabled(
                    self._pattern_data_is_solid(self.pattern_combo.currentData()))
        elif tool_name == "pencil":
            self.stacked_widget.setCurrentWidget(self.panel_pencil)
            if self.main_window and hasattr(self, 'pencil_size_box'):
                t = self.pencil_size_box.currentText().strip()
                if t.isdigit():
                    self.main_window.update_pencil_size(int(t))
                self.main_window.update_pencil_shape(self.pencil_shape_combo.currentData())
        elif tool_name == "eraser":
            self.stacked_widget.setCurrentWidget(self.panel_eraser)
            if self.main_window:
                _data = self.eraser_mode_combo.currentData()
                _is_color = (_data == "color")
                _is_bg = (_data == "background")
                self._set_eraser_tolerance_enabled(_is_color or _is_bg)
                self._set_eraser_bg_options_visible(_is_bg)
                self.main_window.update_eraser_color_mode(_is_color)
                self.main_window.update_eraser_bg_mode(_is_bg)
                self.main_window.update_eraser_color_tolerance(self.eraser_tolerance_slider.value())
                if _is_bg:
                    self.main_window.update_eraser_bg_one_shot(self.eraser_bg_one_shot_check.isChecked())
                    self.main_window.update_eraser_bg_protect_primary(self.eraser_bg_protect_primary_check.isChecked())
                if hasattr(self, 'eraser_shape_combo'):
                    self.main_window.update_eraser_shape(self.eraser_shape_combo.currentData())
        elif tool_name == "bucket":
            self.stacked_widget.setCurrentWidget(self.panel_bucket)
        elif tool_name == "eyedropper":
            self.stacked_widget.setCurrentWidget(self.panel_eyedropper)
        elif tool_name == "clone":
            self.stacked_widget.setCurrentWidget(self.panel_clone)
            self._sync_clone_panel_from_canvas()
        elif tool_name == "text":
            self.stacked_widget.setCurrentWidget(self.panel_text)
            self._push_text_panel_to_canvas()
        elif tool_name == "shapes":
            self.stacked_widget.setCurrentWidget(self.panel_shapes)
            self.main_window.update_active_shape(self.shape_selector.currentText())
        elif tool_name == "pen_path":
            self.stacked_widget.setCurrentWidget(self.panel_pen_path)
            if self.main_window and hasattr(self, 'pen_path_output_combo'):
                self.main_window.set_pen_path_output(
                    self.pen_path_output_combo.currentData())
                self.main_window.set_pen_path_fill_pattern(
                    self.pen_path_fill_combo.currentData())
        elif tool_name == "airbrush":
            self.stacked_widget.setCurrentWidget(self.panel_airbrush)
            if self.main_window:
                self.main_window.update_airbrush_hardness(self.airbrush_hardness_slider.value())
                self.main_window.update_airbrush_flow(self.airbrush_flow_slider.value())
                self.main_window.update_airbrush_shape(self.airbrush_shape_combo.currentData())
                self.main_window.update_airbrush_texture("speckled" if self.airbrush_speckle_check.isChecked() else "smooth")
        elif tool_name == "gradient":
            self.stacked_widget.setCurrentWidget(self.panel_gradient)
            if self.main_window:
                self.main_window.update_gradient_pattern(self.gradient_pattern_selector.currentData())
        elif tool_name == "smudge":
            self.stacked_widget.setCurrentWidget(self.panel_smudge)
            if self.main_window:
                self.main_window.update_smudge_hardness(self.smudge_hardness_slider.value())
                self.main_window.update_smudge_strength(self.smudge_strength_slider.value())
        elif tool_name == "replace_color":
            self.stacked_widget.setCurrentWidget(self.panel_replace_color)
            if self.main_window:
                self.main_window.update_replace_color_tolerance(self.replace_tolerance_slider.value())
                self.main_window.update_replace_color_shape(self.replace_shape_combo.currentData())
                self.main_window.update_replace_color_hardness(self.replace_hardness_slider.value())
                self.main_window.update_replace_color_contiguous(self.replace_contiguous_check.isChecked())
                self.main_window.update_replace_color_sample_all(self.replace_sample_all_check.isChecked())
        elif tool_name == "dodge_burn":
            self.stacked_widget.setCurrentWidget(self.panel_dodge_burn)
            if self.main_window:
                self.main_window.update_dodge_mode(self.dodge_mode_combo.currentData())
                self.main_window.update_dodge_range(self.dodge_range_combo.currentData())
                self.main_window.update_dodge_exposure(self.dodge_exposure_slider.value())
                self.main_window.update_dodge_hardness(self.dodge_hardness_slider.value())
        elif tool_name == "sponge":
            self.stacked_widget.setCurrentWidget(self.panel_sponge)
            if self.main_window:
                self.main_window.update_sponge_mode(self.sponge_mode_combo.currentData())
                self.main_window.update_sponge_flow(self.sponge_flow_slider.value())
                self.main_window.update_sponge_hardness(self.sponge_hardness_slider.value())
        elif tool_name == "liquify":
            self.stacked_widget.setCurrentWidget(self.panel_liquify)
            if self.main_window:
                self.main_window.update_liquify_strength(self.liquify_strength_slider.value())
                self.main_window.update_liquify_hardness(self.liquify_hardness_slider.value())
        elif tool_name == "heal":
            self.stacked_widget.setCurrentWidget(self.panel_heal)
        elif tool_name == "line_curve":
            self.stacked_widget.setCurrentWidget(self.panel_line_curve)
            if self.main_window and hasattr(self, 'line_curve_mode_combo'):
                self.main_window.set_line_curve_mode(
                    self.line_curve_mode_combo.currentData())
                self.main_window.set_line_curve_style(
                    self.line_curve_style_combo.currentData())
                self.main_window.set_line_curve_cap_start(
                    self.line_curve_cap_start_combo.currentData())
                self.main_window.set_line_curve_cap_end(
                    self.line_curve_cap_end_combo.currentData())
                self.on_line_curve_cap_size_changed(
                    self.line_curve_cap_size_box.currentText())
        elif tool_name == "measure":
            self.stacked_widget.setCurrentWidget(self.panel_measure)
            if self.main_window and hasattr(self, 'measure_unit_combo'):
                self.main_window.set_measure_unit(
                    self.measure_unit_combo.currentData())

    def sync_spin_boxes(self, value):
        if hasattr(self, 'pen_size_box'):
            self.pen_size_box.blockSignals(True)
            self.pen_size_box.setCurrentText(str(value))
            self.pen_size_box.blockSignals(False)
        if hasattr(self, 'eraser_size_box'):
            self.eraser_size_box.blockSignals(True)
            self.eraser_size_box.setCurrentText(str(value))
            self.eraser_size_box.blockSignals(False)
        if hasattr(self, 'shape_size_box'):
            self.shape_size_box.blockSignals(True)
            self.shape_size_box.setCurrentText(str(value))
            self.shape_size_box.blockSignals(False)
        if hasattr(self, 'pen_path_size_box'):
            self.pen_path_size_box.blockSignals(True)
            self.pen_path_size_box.setCurrentText(str(value))
            self.pen_path_size_box.blockSignals(False)
        if hasattr(self, 'replace_size_box'):
            self.replace_size_box.blockSignals(True)
            self.replace_size_box.setCurrentText(str(value))
            self.replace_size_box.blockSignals(False)
        if hasattr(self, 'airbrush_size_box'):
            self.airbrush_size_box.blockSignals(True)
            self.airbrush_size_box.setCurrentText(str(value))
            self.airbrush_size_box.blockSignals(False)
        if hasattr(self, 'smudge_size_box'):
            self.smudge_size_box.blockSignals(True)
            self.smudge_size_box.setCurrentText(str(value))
            self.smudge_size_box.blockSignals(False)
        if hasattr(self, 'dodge_size_box'):
            self.dodge_size_box.blockSignals(True)
            self.dodge_size_box.setCurrentText(str(value))
            self.dodge_size_box.blockSignals(False)
        if hasattr(self, 'sponge_size_box'):
            self.sponge_size_box.blockSignals(True)
            self.sponge_size_box.setCurrentText(str(value))
            self.sponge_size_box.blockSignals(False)
        if hasattr(self, 'liquify_size_box'):
            self.liquify_size_box.blockSignals(True)
            self.liquify_size_box.setCurrentText(str(value))
            self.liquify_size_box.blockSignals(False)
        if hasattr(self, 'heal_size_box'):
            self.heal_size_box.blockSignals(True)
            self.heal_size_box.setCurrentText(str(value))
            self.heal_size_box.blockSignals(False)
        if hasattr(self, 'line_curve_size_box'):
            self.line_curve_size_box.blockSignals(True)
            self.line_curve_size_box.setCurrentText(str(value))
            self.line_curve_size_box.blockSignals(False)

    def decrease_size(self, combo_box):
        texto = combo_box.currentText().strip()
        if texto.isdigit():
            val = int(texto)
            if val > 1: combo_box.setCurrentText(str(val - 1))

    def increase_size(self, combo_box):
        texto = combo_box.currentText().strip()
        if texto.isdigit():
            val = int(texto)
            if val < 300: combo_box.setCurrentText(str(val + 1))

    def sync_all_options(self, size, hardness, spacing, pattern="solid", eraser_hardness=100, eraser_spacing=10, bucket_pattern=None, antialias=True):
        """Sincroniza los controles visuales de ambos paneles al cambiar de pestaña"""
        self.is_syncing = True
        
        # Sincronizar selectores de tamaño comunes
        if hasattr(self, 'pen_size_box'): self.pen_size_box.setCurrentText(str(size))
        if hasattr(self, 'eraser_size_box'): self.eraser_size_box.setCurrentText(str(size))
        if hasattr(self, 'shape_size_box'): self.shape_size_box.setCurrentText(str(size))
        if hasattr(self, 'pen_path_size_box'): self.pen_path_size_box.setCurrentText(str(size))
        if hasattr(self, 'line_curve_size_box'): self.line_curve_size_box.setCurrentText(str(size))
        if hasattr(self, 'airbrush_size_box'): self.airbrush_size_box.setCurrentText(str(size))
        if hasattr(self, 'smudge_size_box'): self.smudge_size_box.setCurrentText(str(size))
        if hasattr(self, 'sponge_size_box'): self.sponge_size_box.setCurrentText(str(size))
        if hasattr(self, 'liquify_size_box'): self.liquify_size_box.setCurrentText(str(size))

        # Sincronizar deslizadores del Pincel
        if hasattr(self, 'hardness_slider'):
            self.hardness_slider.setValue(hardness)
            self.hardness_value_label.setText(f"{hardness}%")
        if hasattr(self, 'spacing_slider'):
            self.spacing_slider.setValue(spacing)
            self.spacing_value_label.setText(f"{spacing}%")
        if hasattr(self, 'pattern_combo'):
            idx = self.pattern_combo.findData(pattern)
            if idx != -1: self.pattern_combo.setCurrentIndex(idx)
            
        # Sincronizar deslizadores de la Goma (NUEVO)
        if hasattr(self, 'eraser_hardness_slider'):
            self.eraser_hardness_slider.setValue(eraser_hardness)
            self.eraser_hardness_label.setText(f"{eraser_hardness}%")
        if hasattr(self, 'eraser_spacing_slider'):
            self.eraser_spacing_slider.setValue(eraser_spacing)
            self.eraser_spacing_label.setText(f"{eraser_spacing}%")

        # El combo del Cubo tiene su PROPIO patrón (independiente del Pincel).
        if hasattr(self, 'bucket_pattern_combo'):
            bp = bucket_pattern if bucket_pattern is not None else pattern
            idx = self.bucket_pattern_combo.findData(bp)
            if idx != -1: self.bucket_pattern_combo.setCurrentIndex(idx)

        # Suavizado del Pincel
        if hasattr(self, 'brush_antialias_check'):
            self.brush_antialias_check.setChecked(bool(antialias))

        self.is_syncing = False
