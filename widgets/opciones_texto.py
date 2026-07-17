# widgets/opciones_texto.py
"""Panel de TEXTO de la barra de opciones (mixin de DynamicOptionsBar).

Extraído de widgets/options_bar.py TAL CUAL (sin cambios de comportamiento):
panel y handlers de la herramienta de texto (fuente, tamaño, estilos,
alineación, vertical, interletraje) y su sincronización con el editor del
lienzo. DynamicOptionsBar hereda de PanelesTexto, así que todo sigue
accediéndose vía self.* igual que antes."""
from i18n import t
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QComboBox, QLabel,
                               QPushButton, QSlider, QFontComboBox,
                               QButtonGroup, QCheckBox)
from PySide6.QtCore import Qt, QSize, QFile
import theme


class PanelesTexto:
    def _text_toggle_style(self):
        return theme.labeled_toggle_qss()

    def _make_text_toggle(self, label, tooltip, icon=None, bold=False, italic=False):
        # Si existe el PNG, usa icono; si no, cae a la inicial (N/K/S/T, I/C/D/J)
        b = QPushButton()
        b.setCheckable(True)
        b.setFixedSize(26, 24)
        b.setToolTip(tooltip)
        b.setFocusPolicy(Qt.NoFocus)
        if icon and QFile.exists(icon):
            b.setIcon(theme.icono(icon))
            b.setIconSize(QSize(16, 16))
        else:
            b.setText(label)
            f = b.font()
            if bold: f.setBold(True)
            if italic: f.setItalic(True)
            b.setFont(f)
        b.setStyleSheet(self._text_toggle_style())
        return b

    def create_text_panel(self):
        """Panel de Texto: fuente, tamaño, negrita/cursiva/subrayado/tachado y
        alineación izquierda/centro/derecha. El COLOR del texto es el color
        primario (panel de Colores), como en el resto de herramientas."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(2, 0, 5, 0)
        layout.setSpacing(4)

        # --- Fuente ---
        layout.addWidget(QLabel(t("opt.lbl.source")))
        self.text_font_combo = QFontComboBox()
        self.text_font_combo.setFixedWidth(160)
        self.text_font_combo.setStyleSheet(self._get_combo_style())
        self.text_font_combo.currentFontChanged.connect(self.on_text_font_changed)
        layout.addWidget(self.text_font_combo)

        # --- Tamaño ---
        layout.addSpacing(8)
        layout.addWidget(QLabel(t("opt.lbl.size")))
        
        btn_menos_text_sz = QPushButton("-")
        btn_menos_text_sz.setFixedSize(20, 20)
        btn_menos_text_sz.setStyleSheet(self._get_btn_style())
        btn_menos_text_sz.setAutoRepeat(True) 
        btn_menos_text_sz.setAutoRepeatDelay(400)
        btn_menos_text_sz.setAutoRepeatInterval(40)
        layout.addWidget(btn_menos_text_sz)
        
        self.text_size_box = QComboBox()
        self.text_size_box.setMaxVisibleItems(25)
        self.text_size_box.setEditable(True)
        self.text_size_box.setFixedWidth(75)
        self.text_size_box.addItems(["8", "9", "10", "11", "12", "14", "16", "18",
                                     "20", "24", "28", "32", "36", "42", "48", "56",
                                     "64", "72", "96", "128", "160", "200"])
        self.text_size_box.setCurrentText("24")
        self.text_size_box.setStyleSheet(self._get_combo_style())
        self.text_size_box.currentTextChanged.connect(self.on_text_size_changed)
        layout.addWidget(self.text_size_box)
        
        btn_mas_text_sz = QPushButton("+")
        btn_mas_text_sz.setFixedSize(20, 20)
        btn_mas_text_sz.setStyleSheet(self._get_btn_style())
        btn_mas_text_sz.setAutoRepeat(True) 
        btn_mas_text_sz.setAutoRepeatDelay(400)
        btn_mas_text_sz.setAutoRepeatInterval(40)
        layout.addWidget(btn_mas_text_sz)
        
        btn_menos_text_sz.clicked.connect(lambda: self.decrease_size(self.text_size_box))
        btn_mas_text_sz.clicked.connect(lambda: self.increase_size(self.text_size_box))

        # --- Estilos ---
        layout.addSpacing(8)
        self.text_btn_bold = self._make_text_toggle("N", t("opt.tt.text_bold"), icon=":/icons/text_bold.png", bold=True)
        self.text_btn_italic = self._make_text_toggle("K", t("opt.tt.text_italic"), icon=":/icons/text_italic.png", italic=True)
        self.text_btn_underline = self._make_text_toggle("S", t("opt.tt.text_underline"), icon=":/icons/text_underline.png")
        self.text_btn_strike = self._make_text_toggle("T", t("opt.tt.text_strike"), icon=":/icons/text_strike.png")
        self.text_btn_bold.toggled.connect(self.on_text_bold)
        self.text_btn_italic.toggled.connect(self.on_text_italic)
        self.text_btn_underline.toggled.connect(self.on_text_underline)
        self.text_btn_strike.toggled.connect(self.on_text_strike)
        for b in (self.text_btn_bold, self.text_btn_italic,
                  self.text_btn_underline, self.text_btn_strike):
            layout.addWidget(b)

        # --- Alineación (exclusiva) ---
        layout.addSpacing(8)
        self.text_btn_align_left = self._make_text_toggle("I", t("opt.tt.align_left"), icon=":/icons/align_left.png")
        self.text_btn_align_center = self._make_text_toggle("C", t("opt.tt.align_center"), icon=":/icons/align_center.png")
        self.text_btn_align_right = self._make_text_toggle("D", t("opt.tt.align_right"), icon=":/icons/align_right.png")
        self.text_btn_align_justify = self._make_text_toggle("J", t("opt.tt.align_justify"), icon=":/icons/align_justify.png")
        self.text_align_group = QButtonGroup(widget)
        self.text_align_group.setExclusive(True)
        for b in (self.text_btn_align_left, self.text_btn_align_center,
                  self.text_btn_align_right, self.text_btn_align_justify):
            self.text_align_group.addButton(b)
            layout.addWidget(b)
        self.text_btn_align_left.setChecked(True)
        self.text_btn_align_left.clicked.connect(lambda: self.on_text_align("left"))
        self.text_btn_align_center.clicked.connect(lambda: self.on_text_align("center"))
        self.text_btn_align_right.clicked.connect(lambda: self.on_text_align("right"))
        self.text_btn_align_justify.clicked.connect(lambda: self.on_text_align("justify"))

        # --- Texto VERTICAL apilado (orientación de la CAPA): marcado = vertical,
        # sin marcar = horizontal. ---
        layout.addSpacing(8)
        self.text_btn_vertical = QCheckBox(t("opt.tt.text_vertical_lbl", default="Vertical"))
        self.text_btn_vertical.setStyleSheet(theme.checkbox_qss())
        self.text_btn_vertical.setToolTip(t("opt.tt.text_vertical", default="Texto vertical (apilado)"))
        self.text_btn_vertical.toggled.connect(self.on_text_vertical)
        layout.addWidget(self.text_btn_vertical)

        # --- Interletraje (px): horizontal = separación entre letras; vertical =
        # hueco entre caracteres apilados. Admite negativo (apretar). Slider con
        # botones +/- para uniformar con las demás opciones de la barra. ---
        layout.addSpacing(8)
        layout.addWidget(QLabel(t("opt.tt.spacing", default="Interletraje:")))
        sp_menos = QPushButton("-"); sp_menos.setFixedSize(20, 20); sp_menos.setStyleSheet(self._get_btn_style())
        sp_menos.setAutoRepeat(True); sp_menos.setAutoRepeatDelay(400); sp_menos.setAutoRepeatInterval(40)
        layout.addWidget(sp_menos)
        self.text_spacing_slider = QSlider(Qt.Orientation.Horizontal)
        self.text_spacing_slider.setRange(-50, 300); self.text_spacing_slider.setValue(0)
        self.text_spacing_slider.setFixedWidth(90); self.text_spacing_slider.setStyleSheet(self._get_slider_style())
        self.text_spacing_slider.setToolTip(t("opt.tt.spacing", default="Interletraje:"))
        self.text_spacing_slider.valueChanged.connect(self.on_text_spacing)
        layout.addWidget(self.text_spacing_slider)
        sp_mas = QPushButton("+"); sp_mas.setFixedSize(20, 20); sp_mas.setStyleSheet(self._get_btn_style())
        sp_mas.setAutoRepeat(True); sp_mas.setAutoRepeatDelay(400); sp_mas.setAutoRepeatInterval(40)
        layout.addWidget(sp_mas)
        sp_menos.clicked.connect(lambda: self.text_spacing_slider.setValue(self.text_spacing_slider.value() - 1))
        sp_mas.clicked.connect(lambda: self.text_spacing_slider.setValue(self.text_spacing_slider.value() + 1))
        self.text_spacing_label = QLabel("0"); self.text_spacing_label.setFixedWidth(30)
        layout.addWidget(self.text_spacing_label)

        layout.addStretch()
        return widget

    def on_text_font_changed(self, qfont):
        if self.main_window:
            self.main_window.update_text_family(qfont.family())

    def on_text_size_changed(self, text):
        if not text.strip().isdigit():
            return
        val = int(text)
        if 1 <= val <= 1000 and self.main_window:
            self.main_window.update_text_size(val)

    def on_text_bold(self, checked):
        if self.main_window: self.main_window.update_text_bold(checked)

    def on_text_italic(self, checked):
        if self.main_window: self.main_window.update_text_italic(checked)

    def on_text_underline(self, checked):
        if self.main_window: self.main_window.update_text_underline(checked)

    def on_text_strike(self, checked):
        if self.main_window: self.main_window.update_text_strike(checked)

    def on_text_align(self, value):
        if self.main_window: self.main_window.update_text_align(value)

    def on_text_vertical(self, checked):
        if self.main_window: self.main_window.update_text_vertical(checked)

    def on_text_spacing(self, value):
        if hasattr(self, "text_spacing_label"):
            self.text_spacing_label.setText(str(int(value)))
        if self.main_window: self.main_window.update_text_spacing(int(value))

    def _push_text_panel_to_canvas(self):
        """Vuelca al lienzo la configuración del panel de texto al activar la
        herramienta (la fuente/estilo del panel es la fuente de verdad)."""
        if not self.main_window:
            return
        self.main_window.update_text_family(self.text_font_combo.currentFont().family())
        try:
            self.main_window.update_text_size(int(self.text_size_box.currentText()))
        except ValueError:
            pass
        self.main_window.update_text_bold(self.text_btn_bold.isChecked())
        self.main_window.update_text_italic(self.text_btn_italic.isChecked())
        self.main_window.update_text_underline(self.text_btn_underline.isChecked())
        self.main_window.update_text_strike(self.text_btn_strike.isChecked())
        align = "left"
        if self.text_btn_align_center.isChecked():
            align = "center"
        elif self.text_btn_align_right.isChecked():
            align = "right"
        elif self.text_btn_align_justify.isChecked():
            align = "justify"
        self.main_window.update_text_align(align)
        self.main_window.update_text_vertical(self.text_btn_vertical.isChecked())
        self.main_window.update_text_spacing(self.text_spacing_slider.value())

    def set_text_panel_from_format(self, info):
        """Refleja en el panel el formato del texto bajo el cursor (lo llama
        main.sync_text_panel). Bloquea señales para no reaplicar en bucle."""
        from PySide6.QtGui import QFont
        widgets = [self.text_font_combo, self.text_size_box,
                   self.text_btn_bold, self.text_btn_italic,
                   self.text_btn_underline, self.text_btn_strike,
                   self.text_btn_align_left, self.text_btn_align_center,
                   self.text_btn_align_right, self.text_btn_align_justify,
                   self.text_btn_vertical, self.text_spacing_slider]
        for w in widgets:
            w.blockSignals(True)
        le = self.text_size_box.lineEdit()
        if le is not None:
            le.blockSignals(True)
        try:
            self.text_font_combo.setCurrentFont(QFont(info.get("family", "Arial")))
            self.text_size_box.setCurrentText(str(info.get("size", 24)))
            self.text_btn_bold.setChecked(bool(info.get("bold", False)))
            self.text_btn_italic.setChecked(bool(info.get("italic", False)))
            self.text_btn_underline.setChecked(bool(info.get("underline", False)))
            self.text_btn_strike.setChecked(bool(info.get("strike", False)))
            a = info.get("align", "left")
            self.text_btn_align_left.setChecked(a == "left")
            self.text_btn_align_center.setChecked(a == "center")
            self.text_btn_align_right.setChecked(a == "right")
            self.text_btn_align_justify.setChecked(a == "justify")
            self.text_btn_vertical.setChecked(bool(info.get("vertical", False)))
            sp = int(info.get("spacing", 0))
            self.text_spacing_slider.setValue(sp)
            self.text_spacing_label.setText(str(sp))
        finally:
            for w in widgets:
                w.blockSignals(False)
            if le is not None:
                le.blockSignals(False)

