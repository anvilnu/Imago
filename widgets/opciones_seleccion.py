# widgets/opciones_seleccion.py
"""Paneles de SELECCIÓN y transformación de la barra de opciones (mixin de
DynamicOptionsBar).

Extraído de widgets/options_bar.py TAL CUAL (sin cambios de comportamiento):
paneles y handlers de mover (con botones de refinar), marquesinas (modos,
relación/tamaño fijo), mover selección/copia, mano, recorte y varita mágica.
DynamicOptionsBar hereda de PanelesSeleccion, así que todo sigue accediéndose
vía self.* igual que antes."""
from i18n import t
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QComboBox, QLabel,
                               QPushButton, QSlider, QCheckBox, QSpinBox)
from PySide6.QtCore import Qt, QFile
import theme


class PanelesSeleccion:
    def create_move_panel(self):
        """Panel de Mover: desplegable con las 3 modalidades (patrón Formas)."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(2, 0, 5, 0)
        layout.setSpacing(4)

        layout.addWidget(QLabel(t("opt.lbl.mode_space")))
        self.move_mode_selector = QComboBox()
        # Etiqueta traducida + valor interno estable (selection/outline/copy) en
        # itemData: update_active_move_mode compara contra esos valores.
        self.move_mode_selector.addItem(t("opt.mode.move_sel"), "selection")
        self.move_mode_selector.addItem(t("opt.mode.move_out"), "outline")
        self.move_mode_selector.addItem(t("opt.mode.move_copy"), "copy")
        self.move_mode_selector.setStyleSheet(self._get_combo_style())
        self.move_mode_selector.currentIndexChanged.connect(
            lambda i: self.main_window.update_active_move_mode(self.move_mode_selector.itemData(i)))
        layout.addWidget(self.move_mode_selector)

        layout.addStretch()
        return widget

    def _add_refine_buttons(self, layout):
        """Añade 'Refinar:' + 7 botones (Expandir, Contraer, Suavizar, Calar,
        Borde, Crecer, Seleccionar parecido). Se desactivan si no hay selección
        activa."""
        if not hasattr(self, "_refine_buttons"):
            self._refine_buttons = []
        
        lbl_refine = QLabel(t("opt.lbl.refine"))
        lbl_refine.setStyleSheet("margin-left: 6px; margin-right: 4px; font-weight: normal;")
        layout.addWidget(lbl_refine)
        
        def _refine_btn(icon_file, fallback, tip, action_func):
            from PySide6.QtGui import QIcon
            from PySide6.QtCore import QSize
            b = QPushButton()
            b.setFixedSize(24, 24)
            b.setToolTip(tip)
            ic = ":/icons/" + icon_file
            if QFile.exists(ic):
                b.setIcon(theme.icono(ic))
                b.setIconSize(QSize(24, 24))
            else:
                b.setText(fallback)
            b.setStyleSheet(self._get_mode_btn_style())
            b.clicked.connect(action_func)
            self._refine_buttons.append(b)
            layout.addWidget(b)
            return b

        _refine_btn("selection_expand.png", "+", t("opt.btn.expand"), lambda: self.main_window and self.main_window.edit_expand_selection())
        _refine_btn("selection_contract.png", "-", t("opt.btn.contract"), lambda: self.main_window and self.main_window.edit_contract_selection())
        _refine_btn("selection_smooth.png", "S", t("opt.btn.smooth"), lambda: self.main_window and self.main_window.edit_smooth_selection())
        _refine_btn("selection_feather.png", "C", t("opt.btn.feather"), lambda: self.main_window and self.main_window.edit_feather_selection())
        _refine_btn("selection_border.png", "B", t("opt.btn.border"), lambda: self.main_window and self.main_window.edit_border_selection())
        _refine_btn("selection_grow.png", "G", t("opt.btn.grow"), lambda: self.main_window and self.main_window.edit_grow_selection())
        _refine_btn("selection_similar.png", "P", t("opt.btn.similar"), lambda: self.main_window and self.main_window.edit_similar_selection())

    def set_refine_enabled(self, enabled):
        """Habilita/deshabilita los botones 'Refinar' de los paneles de
        selección según haya o no una selección activa (lo llama main)."""
        for btn in getattr(self, "_refine_buttons", []):
            btn.setEnabled(bool(enabled))

    def create_selection_panel(self):
        """Panel compartido por las 3 herramientas de selección: modo de
        combinación (Reemplazar / Añadir / Restar) + guía de uso."""
        import os
        from PySide6.QtGui import QIcon
        from PySide6.QtCore import QSize
        from PySide6.QtWidgets import QButtonGroup
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(5, 0, 5, 0)
        layout.setSpacing(6)

        layout.addWidget(QLabel(t("opt.lbl.mode")))
        self.sel_mode_group = QButtonGroup(widget)
        self.sel_mode_group.setExclusive(True)

        def _mode_btn(mode, icon_file, fallback, tip):
            b = QPushButton()
            b.setCheckable(True)
            b.setFixedSize(24, 24)
            b.setToolTip(tip)
            ic = ":/icons/" + icon_file
            if QFile.exists(ic):
                b.setIcon(theme.icono(ic))
                b.setIconSize(QSize(18, 18))
            else:
                b.setText(fallback)
            b.setStyleSheet(self._get_mode_btn_style())
            b.clicked.connect(lambda checked, m=mode: self.on_selection_mode_changed(m))
            self.sel_mode_group.addButton(b)
            layout.addWidget(b)
            return b

        self.sel_mode_replace = _mode_btn("replace", "sel_replace.png", "N",
            t("opt.mode.replace"))
        self.sel_mode_add = _mode_btn("add", "sel_add.png", "+",
            t("opt.mode.add"))
        self.sel_mode_subtract = _mode_btn("subtract", "sel_subtract.png", "−",
            t("opt.mode.subtract"))
        self.sel_mode_intersect = _mode_btn("intersect", "sel_intersect.png", "∩",
            t("opt.mode.intersect"))
        self.sel_mode_replace.setChecked(True)

        layout.addSpacing(12)
        self._add_refine_buttons(layout)

        # 📐 Tamaño: Normal / Relación fija / Tamaño fijo (px). En relación
        # fija se elige la proporción en un combo de presets (1:1, 4:3, 16:9…)
        # o «Personalizada», que destapa los spins; en tamaño fijo los spins
        # son píxeles exactos. Solo visible en rectángulo/elipse.
        layout.addSpacing(12)
        self.sel_size_lbl = QLabel(t("opt.lbl.selsize"))
        layout.addWidget(self.sel_size_lbl)
        self.sel_size_mode_combo = QComboBox()
        self.sel_size_mode_combo.addItem(t("opt.selsize.normal"), "normal")
        self.sel_size_mode_combo.addItem(t("opt.selsize.ratio"), "ratio")
        self.sel_size_mode_combo.addItem(t("opt.selsize.fixed"), "fixed")
        self.sel_size_mode_combo.setStyleSheet(self._get_combo_style())
        self.sel_size_mode_combo.currentIndexChanged.connect(self.on_sel_size_mode_changed)
        layout.addWidget(self.sel_size_mode_combo)

        # Presets de proporción (dato = (W, H); "custom" = escribirla en los spins)
        self._sel_custom_ratio = (1, 1)      # última proporción personalizada
        self._sel_fixed_size = (100, 100)    # último tamaño fijo en px
        self.sel_ratio_combo = QComboBox()
        for rw, rh in ((1, 1), (4, 3), (3, 4), (3, 2), (2, 3),
                       (16, 9), (9, 16), (5, 4), (4, 5), (2, 1), (1, 2)):
            self.sel_ratio_combo.addItem(f"{rw}:{rh}", (rw, rh))
        self.sel_ratio_combo.addItem(t("opt.selsize.custom"), "custom")
        self.sel_ratio_combo.setStyleSheet(self._get_combo_style())
        self.sel_ratio_combo.setToolTip(t("opt.selsize.ratio_tip"))
        self.sel_ratio_combo.currentIndexChanged.connect(self.on_sel_ratio_changed)
        layout.addWidget(self.sel_ratio_combo)

        def _size_spin(tip):
            s = QSpinBox()
            s.setRange(1, 99999)
            s.setValue(100)
            s.setFixedWidth(64)
            s.setToolTip(tip)
            s.setStyleSheet(theme.spinbox_qss())
            s.setFocusPolicy(Qt.ClickFocus)
            layout.addWidget(s)
            return s

        self.sel_size_w_spin = _size_spin(t("opt.selsize.w_tip"))
        self.sel_size_x_lbl = QLabel("×")
        layout.addWidget(self.sel_size_x_lbl)
        self.sel_size_h_spin = _size_spin(t("opt.selsize.h_tip"))
        self.sel_size_w_spin.valueChanged.connect(self.on_sel_size_spin_changed)
        self.sel_size_h_spin.valueChanged.connect(self.on_sel_size_spin_changed)

        # 🪢 Modo del lazo: mano alzada / poligonal (solo visible con el Lazo)
        self.lasso_mode_lbl = QLabel(t("opt.lbl.lasso"))
        layout.addWidget(self.lasso_mode_lbl)
        self.lasso_mode_combo = QComboBox()
        self.lasso_mode_combo.addItem(t("opt.lasso.freehand"), "freehand")
        self.lasso_mode_combo.addItem(t("opt.lasso.polygon"), "polygon")
        self.lasso_mode_combo.setStyleSheet(self._get_combo_style())
        self.lasso_mode_combo.currentIndexChanged.connect(
            lambda i: self.main_window and self.main_window.update_lasso_polygonal(
                self.lasso_mode_combo.itemData(i) == "polygon"))
        layout.addWidget(self.lasso_mode_combo)

        # Estado inicial (rectángulo, modo Normal): presets, spins y lazo
        # ocultos, para que no engorden el minimumWidth del panel al construirse.
        for w in (self.sel_ratio_combo, self.sel_size_w_spin, self.sel_size_x_lbl,
                  self.sel_size_h_spin, self.lasso_mode_lbl, self.lasso_mode_combo):
            w.setVisible(False)

        layout.addStretch()
        return widget

    def on_sel_size_mode_changed(self, index):
        if index == -1:
            return
        mode = self.sel_size_mode_combo.itemData(index)
        self._load_sel_spins_for_mode(mode)
        self._update_sel_size_controls_visible()
        if self.main_window:
            self.main_window.update_selection_size_mode(mode)
            if mode == "ratio":
                self._push_current_ratio()
            elif mode == "fixed":
                w, h = self._sel_fixed_size
                self.main_window.update_selection_fixed_w(w)
                self.main_window.update_selection_fixed_h(h)

    def on_sel_ratio_changed(self, index):
        if index == -1:
            return
        self._update_sel_size_controls_visible()
        self._push_current_ratio()

    def on_sel_size_spin_changed(self, _v=None):
        """Los spins valen para la proporción personalizada (relación fija) o
        para los píxeles exactos (tamaño fijo), según el modo activo."""
        w = self.sel_size_w_spin.value()
        h = self.sel_size_h_spin.value()
        if self.sel_size_mode_combo.currentData() == "ratio":
            self._sel_custom_ratio = (w, h)
            if self.main_window:
                self.main_window.update_selection_ratio(w, h)
        else:
            self._sel_fixed_size = (w, h)
            if self.main_window:
                self.main_window.update_selection_fixed_w(w)
                self.main_window.update_selection_fixed_h(h)

    def current_selection_ratio(self):
        """Proporción (W, H) activa: la del preset o la personalizada."""
        data = self.sel_ratio_combo.currentData()
        return self._sel_custom_ratio if data == "custom" else data

    def current_selection_fixed(self):
        """Último tamaño fijo (W, H) en px introducido en los spins."""
        return self._sel_fixed_size

    def _push_current_ratio(self):
        if self.sel_ratio_combo.currentData() == "custom":
            self._load_sel_spins_for_mode("ratio")
        if self.main_window:
            w, h = self.current_selection_ratio()
            self.main_window.update_selection_ratio(w, h)

    def _load_sel_spins_for_mode(self, mode):
        """Carga en los spins la pareja de valores del modo (proporción
        personalizada o px), sin disparar sus señales."""
        vals = self._sel_custom_ratio if mode == "ratio" else self._sel_fixed_size
        for spin, v in ((self.sel_size_w_spin, vals[0]),
                        (self.sel_size_h_spin, vals[1])):
            spin.blockSignals(True)
            spin.setValue(v)
            spin.blockSignals(False)

    def _update_sel_size_controls_visible(self):
        es_lazo = getattr(self, '_sel_panel_is_lasso', False)
        mode = self.sel_size_mode_combo.currentData()
        ratio = (not es_lazo) and mode == "ratio"
        self.sel_ratio_combo.setVisible(ratio)
        spins = (not es_lazo) and (mode == "fixed" or (
            ratio and self.sel_ratio_combo.currentData() == "custom"))
        for w in (self.sel_size_w_spin, self.sel_size_x_lbl, self.sel_size_h_spin):
            w.setVisible(spins)

    def _sync_selection_size_controls(self, tool_name):
        """Muestra los controles que tocan según la herramienta de selección:
        combo de tamaño (rectángulo/elipse) o modo del lazo (lazo)."""
        self._sel_panel_is_lasso = (tool_name == "select_lasso")
        for w in (self.sel_size_lbl, self.sel_size_mode_combo):
            w.setVisible(not self._sel_panel_is_lasso)
        for w in (self.lasso_mode_lbl, self.lasso_mode_combo):
            w.setVisible(self._sel_panel_is_lasso)
        self._update_sel_size_controls_visible()

    def _get_mode_btn_style(self):
        return theme.mode_toggle_qss()

    def on_selection_mode_changed(self, mode):
        if self.main_window:
            self.main_window.set_selection_mode(mode)

    def _sync_selection_mode_buttons(self):
        mode = "replace"
        if self.main_window:
            c = self.main_window.get_current_canvas()
            if c is not None:
                mode = getattr(c, "selection_mode", "replace")
        btn = {"replace": self.sel_mode_replace, "add": self.sel_mode_add,
               "subtract": self.sel_mode_subtract,
               "intersect": self.sel_mode_intersect}.get(mode, self.sel_mode_replace)
        btn.setChecked(True)

    def create_move_copy_panel(self):
        """Panel de Mover selección (copia): sin controles (la guía de uso vive
        en la barra de estado)."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(5, 0, 5, 0)
        layout.addStretch()
        return widget

    def create_move_selection_panel(self):
        """Panel de Mover selección (contorno): sin controles (la guía de uso
        vive en la barra de estado)."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(5, 0, 5, 0)
        layout.addStretch()
        return widget

    def create_hand_panel(self):
        """Panel de la Mano: sin controles (la guía de uso vive en la barra de
        estado)."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(5, 0, 5, 0)
        layout.addStretch()
        return widget

    def create_crop_panel(self):
        """Panel del Recorte, de izquierda a derecha: caja de texto (solo
        lectura) con las dimensiones en vivo y botones Recortar (Enter) y
        Cancelar (Esc). Los botones llaman a los handlers update_crop_* de main,
        que hablan con la herramienta activa. La guía de uso vive en la barra de
        estado."""
        from PySide6.QtWidgets import QPushButton, QLineEdit
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(5, 0, 5, 0)
        layout.setSpacing(8)

        # 📐 Relación de aspecto fija: Libre / 1:1 / 4:3... (dato None o (W, H))
        layout.addWidget(QLabel(t("opt.lbl.crop_ratio")))
        self.crop_ratio_combo = QComboBox()
        self.crop_ratio_combo.addItem(t("opt.crop.free"), None)
        for rw, rh in ((1, 1), (4, 3), (3, 4), (3, 2), (2, 3),
                       (16, 9), (9, 16), (5, 4), (4, 5)):
            self.crop_ratio_combo.addItem(f"{rw}:{rh}", (rw, rh))
        self.crop_ratio_combo.setStyleSheet(self._get_combo_style())
        self.crop_ratio_combo.currentIndexChanged.connect(
            lambda i: self.main_window and self.main_window.update_crop_ratio(
                self.crop_ratio_combo.itemData(i)))
        layout.addWidget(self.crop_ratio_combo)

        # Dimensiones de la caja en una CAJA DE TEXTO (solo lectura)
        self.crop_size_box = QLineEdit()
        self.crop_size_box.setReadOnly(True)
        self.crop_size_box.setFocusPolicy(Qt.NoFocus)
        self.crop_size_box.setAlignment(Qt.AlignCenter)
        self.crop_size_box.setFixedWidth(110)
        self.crop_size_box.setFixedHeight(22)
        self.crop_size_box.setStyleSheet(theme.lineedit_qss())
        layout.addWidget(self.crop_size_box)

        self.crop_apply_btn = QPushButton(t("opt.crop.apply"))
        self.crop_cancel_btn = QPushButton(t("opt.crop.cancel"))
        for b in (self.crop_apply_btn, self.crop_cancel_btn):
            b.setStyleSheet(theme.panel_action_button_qss())
            b.setFixedHeight(22)
            b.setMinimumWidth(70)
            b.setFocusPolicy(Qt.NoFocus)
        self.crop_apply_btn.clicked.connect(self.main_window.update_crop_apply)
        self.crop_cancel_btn.clicked.connect(self.main_window.update_crop_cancel)
        layout.addWidget(self.crop_apply_btn)
        layout.addWidget(self.crop_cancel_btn)

        layout.addStretch()
        self.set_crop_info(None)
        return widget

    def set_crop_info(self, rect):
        """Refresca las dimensiones de la caja de recorte (o vacía) y el estado
        de los botones. Lo llama la herramienta vía crop_changed_callback."""
        if not hasattr(self, 'crop_size_box'):
            return
        tiene_caja = rect is not None and rect.width() > 0 and rect.height() > 0
        self.crop_size_box.setText(
            f"{rect.width()} × {rect.height()} px" if tiene_caja else "—")
        self.crop_apply_btn.setEnabled(tiene_caja)
        self.crop_cancel_btn.setEnabled(tiene_caja)

    def create_magic_wand_panel(self):
        """Panel de la Varita: modo de combinación + tolerancia + contigua + capas."""
        import os
        from PySide6.QtGui import QIcon
        from PySide6.QtCore import QSize
        from PySide6.QtWidgets import QButtonGroup
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(5, 0, 5, 0)
        layout.setSpacing(6)

        # --- Modo de combinación (mismos iconos y comportamiento que las selecciones) ---
        layout.addWidget(QLabel(t("opt.lbl.mode")))
        self.wand_mode_group = QButtonGroup(widget)
        self.wand_mode_group.setExclusive(True)

        def _wand_mode_btn(mode, icon_file, fallback, tip):
            b = QPushButton()
            b.setCheckable(True)
            b.setFixedSize(24, 24)
            b.setToolTip(tip)
            ic = ":/icons/" + icon_file
            if QFile.exists(ic):
                b.setIcon(theme.icono(ic))
                b.setIconSize(QSize(18, 18))
            else:
                b.setText(fallback)
            b.setStyleSheet(self._get_mode_btn_style())
            b.clicked.connect(lambda checked, m=mode: self.on_selection_mode_changed(m))
            self.wand_mode_group.addButton(b)
            layout.addWidget(b)
            return b

        self.wand_mode_replace = _wand_mode_btn("replace", "sel_replace.png", "N",
            t("opt.mode.replace"))
        self.wand_mode_add = _wand_mode_btn("add", "sel_add.png", "+",
            t("opt.mode.add_wand"))
        self.wand_mode_subtract = _wand_mode_btn("subtract", "sel_subtract.png", "\u2212",
            t("opt.mode.subtract_wand"))
        self.wand_mode_intersect = _wand_mode_btn("intersect", "sel_intersect.png", "\u2229",
            t("opt.mode.intersect_wand"))
        self.wand_mode_replace.setChecked(True)

        layout.addSpacing(12)

        # --- Tolerancia ---
        layout.addWidget(QLabel(t("opt.lbl.tolerance")))
        self.wand_tolerance_slider = QSlider(Qt.Horizontal)
        self.wand_tolerance_slider.setRange(0, 255)
        self.wand_tolerance_slider.setValue(32)
        self.wand_tolerance_slider.setFixedWidth(120)
        self.wand_tolerance_slider.setStyleSheet(self._get_slider_style())
        self.wand_tolerance_label = QLabel("32")
        self.wand_tolerance_label.setFixedWidth(28)
        self.wand_tolerance_label.setStyleSheet(f"color: {theme.TEXT_DIM}; font-family: monospace; font-size: 11px;")
        self.wand_tolerance_slider.valueChanged.connect(self.on_wand_tolerance_changed)

        tol_minus = QPushButton("-")
        tol_minus.setFixedSize(20, 20)
        tol_minus.setStyleSheet(self._get_btn_style())
        tol_minus.setAutoRepeat(True); tol_minus.setAutoRepeatDelay(400); tol_minus.setAutoRepeatInterval(40)
        tol_minus.clicked.connect(lambda: self.wand_tolerance_slider.setValue(self.wand_tolerance_slider.value() - 1))
        tol_plus = QPushButton("+")
        tol_plus.setFixedSize(20, 20)
        tol_plus.setStyleSheet(self._get_btn_style())
        tol_plus.setAutoRepeat(True); tol_plus.setAutoRepeatDelay(400); tol_plus.setAutoRepeatInterval(40)
        tol_plus.clicked.connect(lambda: self.wand_tolerance_slider.setValue(self.wand_tolerance_slider.value() + 1))

        layout.addWidget(tol_minus)
        layout.addWidget(self.wand_tolerance_slider)
        layout.addWidget(tol_plus)
        layout.addWidget(self.wand_tolerance_label)

        layout.addSpacing(12)

        # --- Contigua / Todas las capas ---
        self.wand_contiguous_check = QCheckBox(t("opt.chk.contiguous"))
        self.wand_contiguous_check.setChecked(True)
        self.wand_contiguous_check.setStyleSheet(self._get_check_style())
        self.wand_contiguous_check.setToolTip(t("opt.tip.contig_wand"))
        self.wand_contiguous_check.toggled.connect(self.on_wand_contiguous_toggled)
        layout.addWidget(self.wand_contiguous_check)

        layout.addSpacing(12)
        self.wand_sample_all_check = QCheckBox(t("opt.chk.all_layers"))
        self.wand_sample_all_check.setChecked(False)
        self.wand_sample_all_check.setStyleSheet(self._get_check_style())
        self.wand_sample_all_check.setToolTip(t("opt.tip.sample_wand"))
        self.wand_sample_all_check.toggled.connect(self.on_wand_sample_all_toggled)
        layout.addWidget(self.wand_sample_all_check)

        layout.addSpacing(12)
        self._add_refine_buttons(layout)

        layout.addStretch()
        return widget

    def on_wand_tolerance_changed(self, value):
        self.wand_tolerance_label.setText(str(value))
        if self.main_window:
            self.main_window.update_wand_tolerance(value)

    def on_wand_contiguous_toggled(self, checked):
        if self.main_window:
            self.main_window.update_wand_contiguous(checked)

    def on_wand_sample_all_toggled(self, checked):
        if self.main_window:
            self.main_window.update_wand_sample_all(checked)

    def _sync_wand_mode_buttons(self):
        mode = "replace"
        if self.main_window:
            c = self.main_window.get_current_canvas()
            if c is not None:
                mode = getattr(c, "selection_mode", "replace")
        btn = {"replace": self.wand_mode_replace, "add": self.wand_mode_add,
               "subtract": self.wand_mode_subtract,
               "intersect": self.wand_mode_intersect}.get(mode, self.wand_mode_replace)
        btn.setChecked(True)

