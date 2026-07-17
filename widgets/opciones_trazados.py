# widgets/opciones_trazados.py
"""Paneles de TRAZADOS de la barra de opciones (mixin de DynamicOptionsBar).

Extraído de widgets/options_bar.py TAL CUAL (sin cambios de comportamiento):
paneles y handlers de la pluma (trazados), línea/curva (con terminaciones) y
la herramienta de medición. DynamicOptionsBar hereda de PanelesTrazados, así
que todo sigue accediéndose vía self.* igual que antes."""
from i18n import t
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QComboBox, QLabel,
                               QPushButton)
from PySide6.QtCore import Qt, QSize
import theme


class PanelesTrazados:
    def create_pen_path_panel(self):
        """Panel de la Pluma: grosor del trazo (estilo pincel: - [combo] +)."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(2, 0, 5, 0)
        layout.setSpacing(4)

        layout.addWidget(QLabel(t("opt.lbl.thickness")))
        btn_menos = QPushButton("-")
        btn_menos.setFixedSize(20, 20)
        btn_menos.setStyleSheet(self._get_btn_style())
        btn_menos.setAutoRepeat(True); btn_menos.setAutoRepeatDelay(400); btn_menos.setAutoRepeatInterval(40)
        layout.addWidget(btn_menos)

        self.pen_path_size_box = QComboBox()
        self.pen_path_size_box.setMaxVisibleItems(25)
        self.pen_path_size_box.setEditable(True)
        self.pen_path_size_box.setFixedWidth(75)
        self.pen_path_size_box.addItems(["1","2","3","4","5","6","7","8","9","10","12","14","16","18","20","25","30","35","40","45","50","60","70","80","90","100"])
        self.pen_path_size_box.setCurrentText("5")
        self.pen_path_size_box.setStyleSheet(self._get_combo_style())
        self.pen_path_size_box.currentTextChanged.connect(self.on_size_changed)
        layout.addWidget(self.pen_path_size_box)

        btn_mas = QPushButton("+")
        btn_mas.setFixedSize(20, 20)
        btn_mas.setStyleSheet(self._get_btn_style())
        btn_mas.setAutoRepeat(True); btn_mas.setAutoRepeatDelay(400); btn_mas.setAutoRepeatInterval(40)
        layout.addWidget(btn_mas)

        btn_menos.clicked.connect(lambda: self.decrease_size(self.pen_path_size_box))
        btn_mas.clicked.connect(lambda: self.increase_size(self.pen_path_size_box))

        layout.addSpacing(10)
        layout.addWidget(QLabel(t("opt.lbl.style")))
        self.pen_path_style_combo = QComboBox()
        self.pen_path_style_combo.setFixedWidth(150)
        self.pen_path_style_combo.setStyleSheet(self._get_combo_style())
        for _lbl, _st in ((t("opt.fill.solid"), Qt.PenStyle.SolidLine),
                          (t("opt.style.dash"), Qt.PenStyle.DashLine),
                          (t("opt.style.dot"), Qt.PenStyle.DotLine),
                          (t("opt.style.dash_dot"), Qt.PenStyle.DashDotLine),
                          (t("opt.style.dash_dot_dot"), Qt.PenStyle.DashDotDotLine)):
            self.pen_path_style_combo.addItem(_lbl, _st)
        self.pen_path_style_combo.currentIndexChanged.connect(self.on_pen_path_style_changed)
        layout.addWidget(self.pen_path_style_combo)

        layout.addSpacing(12)
        layout.addWidget(QLabel(t("opt.lbl.on_confirm", default="Al confirmar:")))
        self.pen_path_output_combo = QComboBox()
        self.pen_path_output_combo.setFixedWidth(150)
        self.pen_path_output_combo.setStyleSheet(self._get_combo_style())
        self.pen_path_output_combo.addItem(t("opt.penpath.stroke"), "stroke")
        self.pen_path_output_combo.addItem(t("opt.penpath.stroke_fill"), "fill")
        self.pen_path_output_combo.addItem(t("opt.penpath.selection"), "selection")
        self.pen_path_output_combo.currentIndexChanged.connect(self.on_pen_path_output_changed)
        layout.addWidget(self.pen_path_output_combo)

        layout.addSpacing(8)
        self.pen_path_fill_label = QLabel(t("opt.lbl.fill"))
        layout.addWidget(self.pen_path_fill_label)
        self.pen_path_fill_combo = QComboBox()
        self.pen_path_fill_combo.setFixedWidth(175)
        self.pen_path_fill_combo.setStyleSheet(self._get_combo_style())
        self._populate_fill_combo(self.pen_path_fill_combo, include_transparent=False)
        self.pen_path_fill_combo.currentIndexChanged.connect(self.on_pen_path_fill_changed)
        layout.addWidget(self.pen_path_fill_combo)

        layout.addStretch()
        return widget

    def on_pen_path_output_changed(self, index):
        if getattr(self, 'is_syncing', False):
            return
        mode = self.pen_path_output_combo.itemData(index)
        if self.main_window:
            self.main_window.set_pen_path_output(mode)

    def on_pen_path_fill_changed(self, index):
        if getattr(self, 'is_syncing', False):
            return
        if self.main_window:
            self.main_window.set_pen_path_fill_pattern(
                self.pen_path_fill_combo.itemData(index))

    def on_pen_path_style_changed(self, index):
        if getattr(self, 'is_syncing', False):
            return
        if self.main_window:
            self.main_window.set_pen_path_line_style(self.pen_path_style_combo.itemData(index))

    def create_line_curve_panel(self):
        """Panel de Línea/Curva: grosor, estilo del trazo y modo de curvado
        (spline / Bézier / directo). Modo y estilo actúan EN VIVO sobre la
        línea flotante."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(2, 0, 5, 0)
        layout.setSpacing(4)

        layout.addWidget(QLabel(t("opt.lbl.thickness")))
        btn_menos = QPushButton("-")
        btn_menos.setFixedSize(20, 20)
        btn_menos.setStyleSheet(self._get_btn_style())
        btn_menos.setAutoRepeat(True); btn_menos.setAutoRepeatDelay(400); btn_menos.setAutoRepeatInterval(40)
        layout.addWidget(btn_menos)

        self.line_curve_size_box = QComboBox()
        self.line_curve_size_box.setMaxVisibleItems(25)
        self.line_curve_size_box.setEditable(True)
        self.line_curve_size_box.setFixedWidth(75)
        self.line_curve_size_box.addItems(["1","2","3","4","5","6","7","8","9","10","12","14","16","18","20","25","30","35","40","45","50","60","70","80","90","100"])
        self.line_curve_size_box.setCurrentText("5")
        self.line_curve_size_box.setStyleSheet(self._get_combo_style())
        self.line_curve_size_box.currentTextChanged.connect(self.on_size_changed)
        layout.addWidget(self.line_curve_size_box)

        btn_mas = QPushButton("+")
        btn_mas.setFixedSize(20, 20)
        btn_mas.setStyleSheet(self._get_btn_style())
        btn_mas.setAutoRepeat(True); btn_mas.setAutoRepeatDelay(400); btn_mas.setAutoRepeatInterval(40)
        layout.addWidget(btn_mas)

        btn_menos.clicked.connect(lambda: self.decrease_size(self.line_curve_size_box))
        btn_mas.clicked.connect(lambda: self.increase_size(self.line_curve_size_box))

        layout.addSpacing(10)
        layout.addWidget(QLabel(t("opt.lbl.style")))
        self.line_curve_style_combo = QComboBox()
        self.line_curve_style_combo.setFixedWidth(150)
        self.line_curve_style_combo.setStyleSheet(self._get_combo_style())
        # Muestra dibujada de cada estilo delante del nombre (como en Formas)
        self.line_curve_style_combo.setIconSize(QSize(25, 14))
        from PySide6.QtGui import QPixmap, QPainter, QPen, QIcon, QColor
        for _lbl, _st in ((t("opt.fill.solid"), Qt.PenStyle.SolidLine),
                          (t("opt.style.dash"), Qt.PenStyle.DashLine),
                          (t("opt.style.dot"), Qt.PenStyle.DotLine),
                          (t("opt.style.dash_dot"), Qt.PenStyle.DashDotLine),
                          (t("opt.style.dash_dot_dot"), Qt.PenStyle.DashDotDotLine)):
            pixmap = QPixmap(25, 14)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            pen = QPen(QColor(theme.TEXT), 2, _st, Qt.FlatCap)
            painter.setPen(pen)
            painter.drawLine(2, 7, 23, 7)
            painter.end()
            self.line_curve_style_combo.addItem(QIcon(pixmap), _lbl, _st)
        self.line_curve_style_combo.currentIndexChanged.connect(self.on_line_curve_style_changed)
        layout.addWidget(self.line_curve_style_combo)

        layout.addSpacing(12)
        layout.addWidget(QLabel(t("opt.lbl.mode")))
        self.line_curve_mode_combo = QComboBox()
        self.line_curve_mode_combo.setFixedWidth(170)
        self.line_curve_mode_combo.setStyleSheet(self._get_combo_style())
        self.line_curve_mode_combo.addItem(t("opt.linecurve.spline"), "spline")
        self.line_curve_mode_combo.addItem(t("opt.linecurve.bezier"), "bezier")
        self.line_curve_mode_combo.addItem(t("opt.linecurve.direct"), "direct")
        self.line_curve_mode_combo.currentIndexChanged.connect(self.on_line_curve_mode_changed)
        layout.addWidget(self.line_curve_mode_combo)

        # --- Terminaciones: una punta POR EXTREMO (mezclables) + tamaño ---
        from PySide6.QtGui import QPolygonF
        from PySide6.QtCore import QPointF

        def _pix_terminacion(forma, al_inicio):
            """Muestra del combo: línea con la punta dibujada en su lado."""
            pixmap = QPixmap(25, 14)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing, True)
            col = QColor(theme.TEXT)
            painter.setPen(QPen(col, 2, Qt.SolidLine, Qt.FlatCap))
            painter.drawLine(4, 7, 21, 7)
            painter.setPen(Qt.NoPen)
            painter.setBrush(col)
            x0, x1 = (1, 8) if al_inicio else (24, 17)   # punta hacia fuera
            if forma == "arrow":
                painter.drawPolygon(QPolygonF(
                    [QPointF(x0, 7), QPointF(x1, 3), QPointF(x1, 11)]))
            elif forma == "circle":
                painter.drawEllipse(QPointF(5 if al_inicio else 20, 7), 3.5, 3.5)
            elif forma == "bar":
                bx = 2 if al_inicio else 20
                painter.drawRect(bx, 2, 3, 10)
            painter.end()
            return QIcon(pixmap)

        formas = ((t("opt.cap.none"), "none"), (t("opt.cap.arrow"), "arrow"),
                  (t("opt.cap.circle"), "circle"), (t("opt.cap.bar"), "bar"))

        layout.addSpacing(12)
        layout.addWidget(QLabel(t("opt.lbl.cap_start")))
        self.line_curve_cap_start_combo = QComboBox()
        self.line_curve_cap_start_combo.setFixedWidth(135)
        self.line_curve_cap_start_combo.setStyleSheet(self._get_combo_style())
        self.line_curve_cap_start_combo.setIconSize(QSize(25, 14))
        for _lbl, _forma in formas:
            self.line_curve_cap_start_combo.addItem(
                _pix_terminacion(_forma, True), _lbl, _forma)
        self.line_curve_cap_start_combo.currentIndexChanged.connect(
            self.on_line_curve_cap_start_changed)
        layout.addWidget(self.line_curve_cap_start_combo)

        layout.addSpacing(6)
        layout.addWidget(QLabel(t("opt.lbl.cap_end")))
        self.line_curve_cap_end_combo = QComboBox()
        self.line_curve_cap_end_combo.setFixedWidth(135)
        self.line_curve_cap_end_combo.setStyleSheet(self._get_combo_style())
        self.line_curve_cap_end_combo.setIconSize(QSize(25, 14))
        for _lbl, _forma in formas:
            self.line_curve_cap_end_combo.addItem(
                _pix_terminacion(_forma, False), _lbl, _forma)
        self.line_curve_cap_end_combo.currentIndexChanged.connect(
            self.on_line_curve_cap_end_changed)
        layout.addWidget(self.line_curve_cap_end_combo)

        # Tamaño de las puntas: 'Auto' = mismo grosor que la línea
        layout.addSpacing(6)
        layout.addWidget(QLabel(t("opt.lbl.cap_size")))
        self.line_curve_cap_size_box = QComboBox()
        self.line_curve_cap_size_box.setEditable(True)
        self.line_curve_cap_size_box.setFixedWidth(75)
        self.line_curve_cap_size_box.setStyleSheet(self._get_combo_style())
        self.line_curve_cap_size_box.addItems(
            [t("opt.cap.auto"), "1", "2", "3", "4", "5", "6", "8", "10",
             "12", "16", "20", "25", "30", "40", "50"])
        self.line_curve_cap_size_box.currentTextChanged.connect(
            self.on_line_curve_cap_size_changed)
        layout.addWidget(self.line_curve_cap_size_box)

        layout.addStretch()
        return widget

    def on_line_curve_style_changed(self, index):
        if getattr(self, 'is_syncing', False):
            return
        if self.main_window:
            self.main_window.set_line_curve_style(self.line_curve_style_combo.itemData(index))

    def on_line_curve_mode_changed(self, index):
        if getattr(self, 'is_syncing', False):
            return
        if self.main_window:
            self.main_window.set_line_curve_mode(self.line_curve_mode_combo.itemData(index))

    def on_line_curve_cap_start_changed(self, index):
        if getattr(self, 'is_syncing', False):
            return
        if self.main_window:
            self.main_window.set_line_curve_cap_start(
                self.line_curve_cap_start_combo.itemData(index))

    def on_line_curve_cap_end_changed(self, index):
        if getattr(self, 'is_syncing', False):
            return
        if self.main_window:
            self.main_window.set_line_curve_cap_end(
                self.line_curve_cap_end_combo.itemData(index))

    def create_measure_panel(self):
        """Panel de Medición: unidades (px/cm/in, la convención de 96 PPP de
        las reglas) y la lectura en vivo de distancia/ángulo/ΔX/ΔY."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(2, 0, 5, 0)
        layout.setSpacing(4)

        layout.addWidget(QLabel(t("opt.lbl.units")))
        self.measure_unit_combo = QComboBox()
        self.measure_unit_combo.setFixedWidth(110)
        self.measure_unit_combo.setStyleSheet(self._get_combo_style())
        self.measure_unit_combo.addItem(t("opt.unit.px"), "px")
        self.measure_unit_combo.addItem(t("opt.unit.cm"), "cm")
        self.measure_unit_combo.addItem(t("opt.unit.in"), "in")
        self.measure_unit_combo.currentIndexChanged.connect(self.on_measure_unit_changed)
        layout.addWidget(self.measure_unit_combo)

        layout.addSpacing(14)
        self.measure_info_label = QLabel(t("measure.empty"))
        self.measure_info_label.setStyleSheet(
            "color: %s; font-style: italic;" % theme.TEXT)
        layout.addWidget(self.measure_info_label)

        layout.addStretch()
        return widget

    def set_measure_info(self, texto):
        """Actualiza la lectura de la medición (la publica MeasureTool)."""
        if hasattr(self, 'measure_info_label'):
            self.measure_info_label.setText(texto)

    def on_measure_unit_changed(self, index):
        if getattr(self, 'is_syncing', False):
            return
        if self.main_window:
            self.main_window.set_measure_unit(self.measure_unit_combo.itemData(index))

    def on_line_curve_cap_size_changed(self, text):
        if getattr(self, 'is_syncing', False):
            return
        if not self.main_window:
            return
        texto = text.strip()
        if texto.isdigit():
            val = max(1, min(300, int(texto)))
            self.main_window.set_line_curve_cap_size(val)
        else:
            self.main_window.set_line_curve_cap_size(0)   # 'Auto' o vacío

