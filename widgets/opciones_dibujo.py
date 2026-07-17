# widgets/opciones_dibujo.py
"""Paneles de DIBUJO de la barra de opciones (mixin de DynamicOptionsBar).

Extraído de widgets/options_bar.py TAL CUAL (sin cambios de comportamiento):
paneles y handlers de pincel, lápiz, goma (con sus modos color/fondos), cubo,
patrones de relleno compartidos, formas, aerógrafo, difuminar, sobreexponer/
subexponer, corrector, clonar, degradado, reemplazo de color y cuentagotas.
DynamicOptionsBar hereda de PanelesDibujo, así que todo sigue accediéndose
vía self.* igual que antes."""
from i18n import t
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QComboBox, QLabel,
                               QPushButton, QSlider, QCheckBox)
from PySide6.QtGui import QColor
from PySide6.QtCore import Qt, QSize, QFile
from tools import pattern_tiles
import theme


class PanelesDibujo:
    def create_smudge_panel(self):
        """Panel del Dedo: Tamaño (- [combo] +), Dureza y Fuerza."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(2, 0, 5, 0)
        layout.setSpacing(4)

        layout.addWidget(QLabel(t("opt.lbl.size")))
        bm = QPushButton("-"); bm.setFixedSize(20, 20); bm.setStyleSheet(self._get_btn_style())
        bm.setAutoRepeat(True); bm.setAutoRepeatDelay(400); bm.setAutoRepeatInterval(40)
        layout.addWidget(bm)
        self.smudge_size_box = QComboBox()
        self.smudge_size_box.setMaxVisibleItems(25)
        self.smudge_size_box.setEditable(True)
        self.smudge_size_box.setFixedWidth(75)
        self.smudge_size_box.addItems(["1","2","3","4","5","6","7","8","9","10","12","14","16","18","20","25","30","35","40","45","50","60","70","80","90","100","125","150","200"])
        self.smudge_size_box.setCurrentText("20")
        self.smudge_size_box.setStyleSheet(self._get_combo_style())
        self.smudge_size_box.currentTextChanged.connect(self.on_size_changed)
        layout.addWidget(self.smudge_size_box)
        bp = QPushButton("+"); bp.setFixedSize(20, 20); bp.setStyleSheet(self._get_btn_style())
        bp.setAutoRepeat(True); bp.setAutoRepeatDelay(400); bp.setAutoRepeatInterval(40)
        layout.addWidget(bp)
        bm.clicked.connect(lambda: self.decrease_size(self.smudge_size_box))
        bp.clicked.connect(lambda: self.increase_size(self.smudge_size_box))

        layout.addSpacing(10)

        layout.addWidget(QLabel(t("opt.lbl.hardness")))
        sm_hd_menos = QPushButton("-"); sm_hd_menos.setFixedSize(20, 20); sm_hd_menos.setStyleSheet(self._get_btn_style())
        sm_hd_menos.setAutoRepeat(True); sm_hd_menos.setAutoRepeatDelay(400); sm_hd_menos.setAutoRepeatInterval(40)
        layout.addWidget(sm_hd_menos)
        self.smudge_hardness_slider = QSlider(Qt.Orientation.Horizontal)
        self.smudge_hardness_slider.setRange(1, 100); self.smudge_hardness_slider.setValue(50)
        self.smudge_hardness_slider.setFixedWidth(90); self.smudge_hardness_slider.setStyleSheet(self._get_slider_style())
        self.smudge_hardness_slider.valueChanged.connect(self.on_smudge_hardness_changed)
        layout.addWidget(self.smudge_hardness_slider)
        sm_hd_mas = QPushButton("+"); sm_hd_mas.setFixedSize(20, 20); sm_hd_mas.setStyleSheet(self._get_btn_style())
        sm_hd_mas.setAutoRepeat(True); sm_hd_mas.setAutoRepeatDelay(400); sm_hd_mas.setAutoRepeatInterval(40)
        layout.addWidget(sm_hd_mas)
        sm_hd_menos.clicked.connect(lambda: self.smudge_hardness_slider.setValue(self.smudge_hardness_slider.value() - 1))
        sm_hd_mas.clicked.connect(lambda: self.smudge_hardness_slider.setValue(self.smudge_hardness_slider.value() + 1))
        self.smudge_hardness_label = QLabel("50%"); self.smudge_hardness_label.setFixedWidth(32)
        self.smudge_hardness_label.setStyleSheet(theme.value_label_qss())
        layout.addWidget(self.smudge_hardness_label)

        layout.addSpacing(10)

        layout.addWidget(QLabel(t("opt.lbl.strength", default="Fuerza:")))
        sm_fz_menos = QPushButton("-"); sm_fz_menos.setFixedSize(20, 20); sm_fz_menos.setStyleSheet(self._get_btn_style())
        sm_fz_menos.setAutoRepeat(True); sm_fz_menos.setAutoRepeatDelay(400); sm_fz_menos.setAutoRepeatInterval(40)
        layout.addWidget(sm_fz_menos)
        self.smudge_strength_slider = QSlider(Qt.Orientation.Horizontal)
        self.smudge_strength_slider.setRange(1, 100); self.smudge_strength_slider.setValue(50)
        self.smudge_strength_slider.setFixedWidth(90); self.smudge_strength_slider.setStyleSheet(self._get_slider_style())
        self.smudge_strength_slider.valueChanged.connect(self.on_smudge_strength_changed)
        layout.addWidget(self.smudge_strength_slider)
        sm_fz_mas = QPushButton("+"); sm_fz_mas.setFixedSize(20, 20); sm_fz_mas.setStyleSheet(self._get_btn_style())
        sm_fz_mas.setAutoRepeat(True); sm_fz_mas.setAutoRepeatDelay(400); sm_fz_mas.setAutoRepeatInterval(40)
        layout.addWidget(sm_fz_mas)
        sm_fz_menos.clicked.connect(lambda: self.smudge_strength_slider.setValue(self.smudge_strength_slider.value() - 1))
        sm_fz_mas.clicked.connect(lambda: self.smudge_strength_slider.setValue(self.smudge_strength_slider.value() + 1))
        self.smudge_strength_label = QLabel("50%"); self.smudge_strength_label.setFixedWidth(32)
        self.smudge_strength_label.setStyleSheet(theme.value_label_qss())
        layout.addWidget(self.smudge_strength_label)

        layout.addSpacing(10)
        layout.addWidget(QLabel(t("opt.lbl.spacing")))
        sm_sp_menos = QPushButton("-"); sm_sp_menos.setFixedSize(20, 20); sm_sp_menos.setStyleSheet(self._get_btn_style())
        sm_sp_menos.setAutoRepeat(True); sm_sp_menos.setAutoRepeatDelay(400); sm_sp_menos.setAutoRepeatInterval(40)
        layout.addWidget(sm_sp_menos)
        self.smudge_spacing_slider = QSlider(Qt.Orientation.Horizontal)
        self.smudge_spacing_slider.setRange(1, 50); self.smudge_spacing_slider.setValue(12)
        self.smudge_spacing_slider.setFixedWidth(90); self.smudge_spacing_slider.setStyleSheet(self._get_slider_style())
        self.smudge_spacing_slider.valueChanged.connect(self.on_smudge_spacing_changed)
        layout.addWidget(self.smudge_spacing_slider)
        sm_sp_mas = QPushButton("+"); sm_sp_mas.setFixedSize(20, 20); sm_sp_mas.setStyleSheet(self._get_btn_style())
        sm_sp_mas.setAutoRepeat(True); sm_sp_mas.setAutoRepeatDelay(400); sm_sp_mas.setAutoRepeatInterval(40)
        layout.addWidget(sm_sp_mas)
        sm_sp_menos.clicked.connect(lambda: self.smudge_spacing_slider.setValue(self.smudge_spacing_slider.value() - 1))
        sm_sp_mas.clicked.connect(lambda: self.smudge_spacing_slider.setValue(self.smudge_spacing_slider.value() + 1))
        self.smudge_spacing_label = QLabel("12%"); self.smudge_spacing_label.setFixedWidth(32)
        self.smudge_spacing_label.setStyleSheet(theme.value_label_qss())
        layout.addWidget(self.smudge_spacing_label)

        layout.addSpacing(12)
        self.smudge_finger_check = QCheckBox(t("opt.chk.paint_color", default="Pintar con color"))
        self.smudge_finger_check.setStyleSheet(self._get_check_style())
        self.smudge_finger_check.toggled.connect(self.on_smudge_finger_changed)
        layout.addWidget(self.smudge_finger_check)

        layout.addStretch()
        return widget

    def on_smudge_hardness_changed(self, value):
        self.smudge_hardness_label.setText(f"{value}%")
        if self.main_window: self.main_window.update_smudge_hardness(value)

    def on_smudge_strength_changed(self, value):
        self.smudge_strength_label.setText(f"{value}%")
        if self.main_window: self.main_window.update_smudge_strength(value)

    def on_smudge_spacing_changed(self, value):
        self.smudge_spacing_label.setText(f"{value}%")
        if self.main_window: self.main_window.update_smudge_spacing(value)

    def on_smudge_finger_changed(self, on):
        if self.main_window: self.main_window.update_smudge_finger_paint(on)

    def create_dodge_burn_panel(self):
        """Panel de Sobreexponer/Subexponer: Tamaño (- [combo] +), Modo,
        Rango tonal, Exposición y Dureza."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(2, 0, 5, 0)
        layout.setSpacing(4)

        layout.addWidget(QLabel(t("opt.lbl.size")))
        db_menos = QPushButton("−"); db_menos.setFixedSize(20, 20); db_menos.setStyleSheet(self._get_btn_style())
        db_menos.setAutoRepeat(True); db_menos.setAutoRepeatDelay(400); db_menos.setAutoRepeatInterval(40)
        layout.addWidget(db_menos)
        self.dodge_size_box = QComboBox()
        self.dodge_size_box.setMaxVisibleItems(25)
        self.dodge_size_box.setEditable(True)
        self.dodge_size_box.setFixedWidth(75)
        self.dodge_size_box.addItems(["1","2","3","4","5","6","7","8","9","10","12","14","16","18","20","25","30","35","40","45","50","60","70","80","90","100","125","150","200"])
        self.dodge_size_box.setCurrentText("20")
        self.dodge_size_box.setStyleSheet(self._get_combo_style())
        self.dodge_size_box.currentTextChanged.connect(self.on_size_changed)
        layout.addWidget(self.dodge_size_box)
        db_mas = QPushButton("+"); db_mas.setFixedSize(20, 20); db_mas.setStyleSheet(self._get_btn_style())
        db_mas.setAutoRepeat(True); db_mas.setAutoRepeatDelay(400); db_mas.setAutoRepeatInterval(40)
        layout.addWidget(db_mas)
        db_menos.clicked.connect(lambda: self.decrease_size(self.dodge_size_box))
        db_mas.clicked.connect(lambda: self.increase_size(self.dodge_size_box))

        layout.addSpacing(10)
        layout.addWidget(QLabel(t("opt.lbl.mode")))
        self.dodge_mode_combo = QComboBox()
        self.dodge_mode_combo.addItem(t("opt.dodge.dodge"), "dodge")
        self.dodge_mode_combo.addItem(t("opt.dodge.burn"), "burn")
        self.dodge_mode_combo.setStyleSheet(self._get_combo_style())
        self.dodge_mode_combo.currentIndexChanged.connect(
            lambda i: self.main_window.update_dodge_mode(self.dodge_mode_combo.itemData(i)))
        layout.addWidget(self.dodge_mode_combo)

        layout.addSpacing(10)
        layout.addWidget(QLabel(t("opt.lbl.range")))
        self.dodge_range_combo = QComboBox()
        self.dodge_range_combo.addItem(t("opt.dodge.shadows"), "shadows")
        self.dodge_range_combo.addItem(t("opt.dodge.midtones"), "midtones")
        self.dodge_range_combo.addItem(t("opt.dodge.highlights"), "highlights")
        self.dodge_range_combo.setCurrentIndex(1)
        self.dodge_range_combo.setStyleSheet(self._get_combo_style())
        self.dodge_range_combo.currentIndexChanged.connect(
            lambda i: self.main_window.update_dodge_range(self.dodge_range_combo.itemData(i)))
        layout.addWidget(self.dodge_range_combo)

        layout.addSpacing(10)
        layout.addWidget(QLabel(t("opt.lbl.exposure")))
        db_ex_menos = QPushButton("-"); db_ex_menos.setFixedSize(20, 20); db_ex_menos.setStyleSheet(self._get_btn_style())
        db_ex_menos.setAutoRepeat(True); db_ex_menos.setAutoRepeatDelay(400); db_ex_menos.setAutoRepeatInterval(40)
        layout.addWidget(db_ex_menos)
        self.dodge_exposure_slider = QSlider(Qt.Orientation.Horizontal)
        self.dodge_exposure_slider.setRange(1, 100); self.dodge_exposure_slider.setValue(25)
        self.dodge_exposure_slider.setFixedWidth(90); self.dodge_exposure_slider.setStyleSheet(self._get_slider_style())
        self.dodge_exposure_slider.valueChanged.connect(self.on_dodge_exposure_changed)
        layout.addWidget(self.dodge_exposure_slider)
        db_ex_mas = QPushButton("+"); db_ex_mas.setFixedSize(20, 20); db_ex_mas.setStyleSheet(self._get_btn_style())
        db_ex_mas.setAutoRepeat(True); db_ex_mas.setAutoRepeatDelay(400); db_ex_mas.setAutoRepeatInterval(40)
        layout.addWidget(db_ex_mas)
        db_ex_menos.clicked.connect(lambda: self.dodge_exposure_slider.setValue(self.dodge_exposure_slider.value() - 1))
        db_ex_mas.clicked.connect(lambda: self.dodge_exposure_slider.setValue(self.dodge_exposure_slider.value() + 1))
        self.dodge_exposure_label = QLabel("25%"); self.dodge_exposure_label.setFixedWidth(32)
        self.dodge_exposure_label.setStyleSheet(theme.value_label_qss())
        layout.addWidget(self.dodge_exposure_label)

        layout.addSpacing(10)
        layout.addWidget(QLabel(t("opt.lbl.hardness")))
        db_du_menos = QPushButton("-"); db_du_menos.setFixedSize(20, 20); db_du_menos.setStyleSheet(self._get_btn_style())
        db_du_menos.setAutoRepeat(True); db_du_menos.setAutoRepeatDelay(400); db_du_menos.setAutoRepeatInterval(40)
        layout.addWidget(db_du_menos)
        self.dodge_hardness_slider = QSlider(Qt.Orientation.Horizontal)
        self.dodge_hardness_slider.setRange(1, 100); self.dodge_hardness_slider.setValue(50)
        self.dodge_hardness_slider.setFixedWidth(90); self.dodge_hardness_slider.setStyleSheet(self._get_slider_style())
        self.dodge_hardness_slider.valueChanged.connect(self.on_dodge_hardness_changed)
        layout.addWidget(self.dodge_hardness_slider)
        db_du_mas = QPushButton("+"); db_du_mas.setFixedSize(20, 20); db_du_mas.setStyleSheet(self._get_btn_style())
        db_du_mas.setAutoRepeat(True); db_du_mas.setAutoRepeatDelay(400); db_du_mas.setAutoRepeatInterval(40)
        layout.addWidget(db_du_mas)
        db_du_menos.clicked.connect(lambda: self.dodge_hardness_slider.setValue(self.dodge_hardness_slider.value() - 1))
        db_du_mas.clicked.connect(lambda: self.dodge_hardness_slider.setValue(self.dodge_hardness_slider.value() + 1))
        self.dodge_hardness_label = QLabel("50%"); self.dodge_hardness_label.setFixedWidth(32)
        self.dodge_hardness_label.setStyleSheet(theme.value_label_qss())
        layout.addWidget(self.dodge_hardness_label)

        layout.addStretch()
        return widget

    def on_dodge_exposure_changed(self, value):
        self.dodge_exposure_label.setText(f"{value}%")
        if self.main_window: self.main_window.update_dodge_exposure(value)

    def on_dodge_hardness_changed(self, value):
        self.dodge_hardness_label.setText(f"{value}%")
        if self.main_window: self.main_window.update_dodge_hardness(value)

    def create_sponge_panel(self):
        """Panel de la Esponja: Tamaño (- [combo] +), Modo (desaturar/saturar),
        Flujo y Dureza. Mismo esqueleto que Sobreexponer/Subexponer."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(2, 0, 5, 0)
        layout.setSpacing(4)

        layout.addWidget(QLabel(t("opt.lbl.size")))
        sp_menos = QPushButton("−"); sp_menos.setFixedSize(20, 20); sp_menos.setStyleSheet(self._get_btn_style())
        sp_menos.setAutoRepeat(True); sp_menos.setAutoRepeatDelay(400); sp_menos.setAutoRepeatInterval(40)
        layout.addWidget(sp_menos)
        self.sponge_size_box = QComboBox()
        self.sponge_size_box.setMaxVisibleItems(25)
        self.sponge_size_box.setEditable(True)
        self.sponge_size_box.setFixedWidth(75)
        self.sponge_size_box.addItems(["1","2","3","4","5","6","7","8","9","10","12","14","16","18","20","25","30","35","40","45","50","60","70","80","90","100","125","150","200"])
        self.sponge_size_box.setCurrentText("20")
        self.sponge_size_box.setStyleSheet(self._get_combo_style())
        self.sponge_size_box.currentTextChanged.connect(self.on_size_changed)
        layout.addWidget(self.sponge_size_box)
        sp_mas = QPushButton("+"); sp_mas.setFixedSize(20, 20); sp_mas.setStyleSheet(self._get_btn_style())
        sp_mas.setAutoRepeat(True); sp_mas.setAutoRepeatDelay(400); sp_mas.setAutoRepeatInterval(40)
        layout.addWidget(sp_mas)
        sp_menos.clicked.connect(lambda: self.decrease_size(self.sponge_size_box))
        sp_mas.clicked.connect(lambda: self.increase_size(self.sponge_size_box))

        layout.addSpacing(8)
        layout.addWidget(QLabel(t("opt.lbl.mode")))
        self.sponge_mode_combo = QComboBox()
        self.sponge_mode_combo.addItem(t("opt.sponge.desaturate"), "desaturate")
        self.sponge_mode_combo.addItem(t("opt.sponge.saturate"), "saturate")
        self.sponge_mode_combo.setStyleSheet(self._get_combo_style())
        self.sponge_mode_combo.currentIndexChanged.connect(
            lambda i: self.main_window.update_sponge_mode(self.sponge_mode_combo.itemData(i)))
        layout.addWidget(self.sponge_mode_combo)

        layout.addSpacing(8)
        layout.addWidget(QLabel(t("opt.lbl.flow")))
        sp_fl_menos = QPushButton("-"); sp_fl_menos.setFixedSize(20, 20); sp_fl_menos.setStyleSheet(self._get_btn_style())
        sp_fl_menos.setAutoRepeat(True); sp_fl_menos.setAutoRepeatDelay(400); sp_fl_menos.setAutoRepeatInterval(40)
        layout.addWidget(sp_fl_menos)
        self.sponge_flow_slider = QSlider(Qt.Orientation.Horizontal)
        self.sponge_flow_slider.setRange(1, 100); self.sponge_flow_slider.setValue(50)
        self.sponge_flow_slider.setFixedWidth(90); self.sponge_flow_slider.setStyleSheet(self._get_slider_style())
        self.sponge_flow_slider.valueChanged.connect(self.on_sponge_flow_changed)
        layout.addWidget(self.sponge_flow_slider)
        sp_fl_mas = QPushButton("+"); sp_fl_mas.setFixedSize(20, 20); sp_fl_mas.setStyleSheet(self._get_btn_style())
        sp_fl_mas.setAutoRepeat(True); sp_fl_mas.setAutoRepeatDelay(400); sp_fl_mas.setAutoRepeatInterval(40)
        layout.addWidget(sp_fl_mas)
        sp_fl_menos.clicked.connect(lambda: self.sponge_flow_slider.setValue(self.sponge_flow_slider.value() - 1))
        sp_fl_mas.clicked.connect(lambda: self.sponge_flow_slider.setValue(self.sponge_flow_slider.value() + 1))
        self.sponge_flow_label = QLabel("50%"); self.sponge_flow_label.setFixedWidth(32)
        self.sponge_flow_label.setStyleSheet(theme.value_label_qss())
        layout.addWidget(self.sponge_flow_label)

        layout.addSpacing(8)
        layout.addWidget(QLabel(t("opt.lbl.hardness")))
        sp_du_menos = QPushButton("-"); sp_du_menos.setFixedSize(20, 20); sp_du_menos.setStyleSheet(self._get_btn_style())
        sp_du_menos.setAutoRepeat(True); sp_du_menos.setAutoRepeatDelay(400); sp_du_menos.setAutoRepeatInterval(40)
        layout.addWidget(sp_du_menos)
        self.sponge_hardness_slider = QSlider(Qt.Orientation.Horizontal)
        self.sponge_hardness_slider.setRange(1, 100); self.sponge_hardness_slider.setValue(50)
        self.sponge_hardness_slider.setFixedWidth(90); self.sponge_hardness_slider.setStyleSheet(self._get_slider_style())
        self.sponge_hardness_slider.valueChanged.connect(self.on_sponge_hardness_changed)
        layout.addWidget(self.sponge_hardness_slider)
        sp_du_mas = QPushButton("+"); sp_du_mas.setFixedSize(20, 20); sp_du_mas.setStyleSheet(self._get_btn_style())
        sp_du_mas.setAutoRepeat(True); sp_du_mas.setAutoRepeatDelay(400); sp_du_mas.setAutoRepeatInterval(40)
        layout.addWidget(sp_du_mas)
        sp_du_menos.clicked.connect(lambda: self.sponge_hardness_slider.setValue(self.sponge_hardness_slider.value() - 1))
        sp_du_mas.clicked.connect(lambda: self.sponge_hardness_slider.setValue(self.sponge_hardness_slider.value() + 1))
        self.sponge_hardness_label = QLabel("50%"); self.sponge_hardness_label.setFixedWidth(32)
        self.sponge_hardness_label.setStyleSheet(theme.value_label_qss())
        layout.addWidget(self.sponge_hardness_label)

        layout.addStretch()
        return widget

    def on_sponge_flow_changed(self, value):
        self.sponge_flow_label.setText(f"{value}%")
        if self.main_window: self.main_window.update_sponge_flow(value)

    def on_sponge_hardness_changed(self, value):
        self.sponge_hardness_label.setText(f"{value}%")
        if self.main_window: self.main_window.update_sponge_hardness(value)

    def create_liquify_panel(self):
        """Panel de Licuar: Tamaño (- [combo] +), Fuerza y Dureza."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(2, 0, 5, 0)
        layout.setSpacing(4)

        layout.addWidget(QLabel(t("opt.lbl.size")))
        lq_menos = QPushButton("−"); lq_menos.setFixedSize(20, 20); lq_menos.setStyleSheet(self._get_btn_style())
        lq_menos.setAutoRepeat(True); lq_menos.setAutoRepeatDelay(400); lq_menos.setAutoRepeatInterval(40)
        layout.addWidget(lq_menos)
        self.liquify_size_box = QComboBox()
        self.liquify_size_box.setMaxVisibleItems(25)
        self.liquify_size_box.setEditable(True)
        self.liquify_size_box.setFixedWidth(75)
        self.liquify_size_box.addItems(["5","10","15","20","25","30","35","40","45","50","60","70","80","90","100","125","150","200","250","300"])
        self.liquify_size_box.setCurrentText("50")
        self.liquify_size_box.setStyleSheet(self._get_combo_style())
        self.liquify_size_box.currentTextChanged.connect(self.on_size_changed)
        layout.addWidget(self.liquify_size_box)
        lq_mas = QPushButton("+"); lq_mas.setFixedSize(20, 20); lq_mas.setStyleSheet(self._get_btn_style())
        lq_mas.setAutoRepeat(True); lq_mas.setAutoRepeatDelay(400); lq_mas.setAutoRepeatInterval(40)
        layout.addWidget(lq_mas)
        lq_menos.clicked.connect(lambda: self.decrease_size(self.liquify_size_box))
        lq_mas.clicked.connect(lambda: self.increase_size(self.liquify_size_box))

        layout.addSpacing(8)
        layout.addWidget(QLabel(t("opt.lbl.strength")))
        lq_fu_menos = QPushButton("-"); lq_fu_menos.setFixedSize(20, 20); lq_fu_menos.setStyleSheet(self._get_btn_style())
        lq_fu_menos.setAutoRepeat(True); lq_fu_menos.setAutoRepeatDelay(400); lq_fu_menos.setAutoRepeatInterval(40)
        layout.addWidget(lq_fu_menos)
        self.liquify_strength_slider = QSlider(Qt.Orientation.Horizontal)
        self.liquify_strength_slider.setRange(1, 100); self.liquify_strength_slider.setValue(50)
        self.liquify_strength_slider.setFixedWidth(90); self.liquify_strength_slider.setStyleSheet(self._get_slider_style())
        self.liquify_strength_slider.valueChanged.connect(self.on_liquify_strength_changed)
        layout.addWidget(self.liquify_strength_slider)
        lq_fu_mas = QPushButton("+"); lq_fu_mas.setFixedSize(20, 20); lq_fu_mas.setStyleSheet(self._get_btn_style())
        lq_fu_mas.setAutoRepeat(True); lq_fu_mas.setAutoRepeatDelay(400); lq_fu_mas.setAutoRepeatInterval(40)
        layout.addWidget(lq_fu_mas)
        lq_fu_menos.clicked.connect(lambda: self.liquify_strength_slider.setValue(self.liquify_strength_slider.value() - 1))
        lq_fu_mas.clicked.connect(lambda: self.liquify_strength_slider.setValue(self.liquify_strength_slider.value() + 1))
        self.liquify_strength_label = QLabel("50%"); self.liquify_strength_label.setFixedWidth(32)
        self.liquify_strength_label.setStyleSheet(theme.value_label_qss())
        layout.addWidget(self.liquify_strength_label)

        layout.addSpacing(8)
        layout.addWidget(QLabel(t("opt.lbl.hardness")))
        lq_du_menos = QPushButton("-"); lq_du_menos.setFixedSize(20, 20); lq_du_menos.setStyleSheet(self._get_btn_style())
        lq_du_menos.setAutoRepeat(True); lq_du_menos.setAutoRepeatDelay(400); lq_du_menos.setAutoRepeatInterval(40)
        layout.addWidget(lq_du_menos)
        self.liquify_hardness_slider = QSlider(Qt.Orientation.Horizontal)
        self.liquify_hardness_slider.setRange(1, 100); self.liquify_hardness_slider.setValue(50)
        self.liquify_hardness_slider.setFixedWidth(90); self.liquify_hardness_slider.setStyleSheet(self._get_slider_style())
        self.liquify_hardness_slider.valueChanged.connect(self.on_liquify_hardness_changed)
        layout.addWidget(self.liquify_hardness_slider)
        lq_du_mas = QPushButton("+"); lq_du_mas.setFixedSize(20, 20); lq_du_mas.setStyleSheet(self._get_btn_style())
        lq_du_mas.setAutoRepeat(True); lq_du_mas.setAutoRepeatDelay(400); lq_du_mas.setAutoRepeatInterval(40)
        layout.addWidget(lq_du_mas)
        lq_du_menos.clicked.connect(lambda: self.liquify_hardness_slider.setValue(self.liquify_hardness_slider.value() - 1))
        lq_du_mas.clicked.connect(lambda: self.liquify_hardness_slider.setValue(self.liquify_hardness_slider.value() + 1))
        self.liquify_hardness_label = QLabel("50%"); self.liquify_hardness_label.setFixedWidth(32)
        self.liquify_hardness_label.setStyleSheet(theme.value_label_qss())
        layout.addWidget(self.liquify_hardness_label)

        layout.addStretch()
        return widget

    def on_liquify_strength_changed(self, value):
        self.liquify_strength_label.setText(f"{value}%")
        if self.main_window: self.main_window.update_liquify_strength(value)

    def on_liquify_hardness_changed(self, value):
        self.liquify_hardness_label.setText(f"{value}%")
        if self.main_window: self.main_window.update_liquify_hardness(value)

    def create_heal_panel(self):
        """Panel del Pincel corrector: Tamaño (- [combo] +) y una pista de uso."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(2, 0, 5, 0)
        layout.setSpacing(4)

        layout.addWidget(QLabel(t("opt.lbl.size")))
        he_menos = QPushButton("−"); he_menos.setFixedSize(20, 20); he_menos.setStyleSheet(self._get_btn_style())
        he_menos.setAutoRepeat(True); he_menos.setAutoRepeatDelay(400); he_menos.setAutoRepeatInterval(40)
        layout.addWidget(he_menos)
        self.heal_size_box = QComboBox()
        self.heal_size_box.setMaxVisibleItems(25)
        self.heal_size_box.setEditable(True)
        self.heal_size_box.setFixedWidth(75)
        self.heal_size_box.addItems(["1","2","3","4","5","6","7","8","9","10","12","14","16","18","20","25","30","35","40","45","50","60","70","80","90","100","125","150","200"])
        self.heal_size_box.setCurrentText("20")
        self.heal_size_box.setStyleSheet(self._get_combo_style())
        self.heal_size_box.currentTextChanged.connect(self.on_size_changed)
        layout.addWidget(self.heal_size_box)
        he_mas = QPushButton("+"); he_mas.setFixedSize(20, 20); he_mas.setStyleSheet(self._get_btn_style())
        he_mas.setAutoRepeat(True); he_mas.setAutoRepeatDelay(400); he_mas.setAutoRepeatInterval(40)
        layout.addWidget(he_mas)
        he_menos.clicked.connect(lambda: self.decrease_size(self.heal_size_box))
        he_mas.clicked.connect(lambda: self.increase_size(self.heal_size_box))

        layout.addStretch()
        return widget

    def create_gradient_panel(self):
        """Panel del Degradado: desplegable de patrones."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(2, 0, 5, 0)
        layout.setSpacing(4)
        layout.addWidget(QLabel(t("opt.lbl.pattern")))
        self.gradient_pattern_selector = QComboBox()
        # Etiqueta traducida (visible) + valor interno ESTABLE en itemData: el
        # gradient_tool compara el patrón contra estos valores en español, así que
        # la traducción no rompe la lógica.
        for _label, _val in ((t("opt.grad.linear"), "Lineal"),
                             (t("opt.grad.linear_reflected"), "Lineal reflejado"),
                             (t("opt.grad.radial"), "Radial"),
                             (t("opt.brush.diamond"), "Rombo"),
                             (t("opt.grad.box"), "Cuadrado (caja)"),
                             (t("opt.grad.conic"), "Cónico"),
                             (t("opt.grad.spiral_cw"), "Espiral (horario)"),
                             (t("opt.grad.spiral_ccw"), "Espiral (antihorario)")):
            self.gradient_pattern_selector.addItem(_label, _val)
        self.gradient_pattern_selector.setStyleSheet(self._get_combo_style())
        self.gradient_pattern_selector.currentIndexChanged.connect(
            lambda i: self.main_window.update_gradient_pattern(
                self.gradient_pattern_selector.itemData(i)))
        layout.addWidget(self.gradient_pattern_selector)

        layout.addSpacing(10)
        layout.addWidget(QLabel(t("opt.lbl.mode_space")))
        self.gradient_mode_selector = QComboBox()
        self.gradient_mode_selector.setFixedWidth(130)
        for _label, _val in ((t("opt.grad.mode_color"), "Color"),
                             (t("opt.grad.mode_transp"), "Transparencia")):
            self.gradient_mode_selector.addItem(_label, _val)
        self.gradient_mode_selector.setStyleSheet(self._get_combo_style())
        self.gradient_mode_selector.currentIndexChanged.connect(
            lambda i: self.main_window.update_gradient_mode(
                self.gradient_mode_selector.itemData(i)))
        layout.addWidget(self.gradient_mode_selector)

        layout.addSpacing(12)
        self.gradient_dither_check = QCheckBox(t("opt.chk.dither", default="Suavizar bandas"))
        self.gradient_dither_check.setStyleSheet(self._get_check_style())
        self.gradient_dither_check.toggled.connect(self.main_window.update_gradient_dither)
        layout.addWidget(self.gradient_dither_check)

        layout.addStretch()
        return widget

    def create_airbrush_panel(self):
        """Panel del Aerógrafo: Tamaño (- [combo] +), Dureza y Flujo."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(2, 0, 5, 0)
        layout.setSpacing(4)

        layout.addWidget(QLabel(t("opt.lbl.size")))
        bm = QPushButton("-"); bm.setFixedSize(20, 20); bm.setStyleSheet(self._get_btn_style())
        bm.setAutoRepeat(True); bm.setAutoRepeatDelay(400); bm.setAutoRepeatInterval(40)
        layout.addWidget(bm)
        self.airbrush_size_box = QComboBox()
        self.airbrush_size_box.setMaxVisibleItems(25)
        self.airbrush_size_box.setEditable(True)
        self.airbrush_size_box.setFixedWidth(75)
        self.airbrush_size_box.addItems(["1","2","3","4","5","6","7","8","9","10","12","14","16","18","20","25","30","35","40","45","50","60","70","80","90","100","125","150","200"])
        self.airbrush_size_box.setCurrentText("5")
        self.airbrush_size_box.setStyleSheet(self._get_combo_style())
        self.airbrush_size_box.currentTextChanged.connect(self.on_size_changed)
        layout.addWidget(self.airbrush_size_box)
        bp = QPushButton("+"); bp.setFixedSize(20, 20); bp.setStyleSheet(self._get_btn_style())
        bp.setAutoRepeat(True); bp.setAutoRepeatDelay(400); bp.setAutoRepeatInterval(40)
        layout.addWidget(bp)
        bm.clicked.connect(lambda: self.decrease_size(self.airbrush_size_box))
        bp.clicked.connect(lambda: self.increase_size(self.airbrush_size_box))

        layout.addSpacing(10)

        layout.addWidget(QLabel(t("opt.lbl.hardness")))
        ab_hd_menos = QPushButton("-"); ab_hd_menos.setFixedSize(20, 20); ab_hd_menos.setStyleSheet(self._get_btn_style())
        ab_hd_menos.setAutoRepeat(True); ab_hd_menos.setAutoRepeatDelay(400); ab_hd_menos.setAutoRepeatInterval(40)
        layout.addWidget(ab_hd_menos)
        self.airbrush_hardness_slider = QSlider(Qt.Orientation.Horizontal)
        self.airbrush_hardness_slider.setRange(1, 100)
        self.airbrush_hardness_slider.setValue(50)
        self.airbrush_hardness_slider.setFixedWidth(90)
        self.airbrush_hardness_slider.setStyleSheet(self._get_slider_style())
        self.airbrush_hardness_slider.valueChanged.connect(self.on_airbrush_hardness_changed)
        layout.addWidget(self.airbrush_hardness_slider)
        ab_hd_mas = QPushButton("+"); ab_hd_mas.setFixedSize(20, 20); ab_hd_mas.setStyleSheet(self._get_btn_style())
        ab_hd_mas.setAutoRepeat(True); ab_hd_mas.setAutoRepeatDelay(400); ab_hd_mas.setAutoRepeatInterval(40)
        layout.addWidget(ab_hd_mas)
        ab_hd_menos.clicked.connect(lambda: self.airbrush_hardness_slider.setValue(self.airbrush_hardness_slider.value() - 1))
        ab_hd_mas.clicked.connect(lambda: self.airbrush_hardness_slider.setValue(self.airbrush_hardness_slider.value() + 1))
        self.airbrush_hardness_label = QLabel("50%")
        self.airbrush_hardness_label.setFixedWidth(32)
        self.airbrush_hardness_label.setStyleSheet(theme.value_label_qss())
        layout.addWidget(self.airbrush_hardness_label)

        layout.addSpacing(10)

        layout.addWidget(QLabel(t("opt.lbl.flow")))
        ab_fl_menos = QPushButton("-"); ab_fl_menos.setFixedSize(20, 20); ab_fl_menos.setStyleSheet(self._get_btn_style())
        ab_fl_menos.setAutoRepeat(True); ab_fl_menos.setAutoRepeatDelay(400); ab_fl_menos.setAutoRepeatInterval(40)
        layout.addWidget(ab_fl_menos)
        self.airbrush_flow_slider = QSlider(Qt.Orientation.Horizontal)
        self.airbrush_flow_slider.setRange(1, 100)
        self.airbrush_flow_slider.setValue(20)
        self.airbrush_flow_slider.setFixedWidth(90)
        self.airbrush_flow_slider.setStyleSheet(self._get_slider_style())
        self.airbrush_flow_slider.valueChanged.connect(self.on_airbrush_flow_changed)
        layout.addWidget(self.airbrush_flow_slider)
        ab_fl_mas = QPushButton("+"); ab_fl_mas.setFixedSize(20, 20); ab_fl_mas.setStyleSheet(self._get_btn_style())
        ab_fl_mas.setAutoRepeat(True); ab_fl_mas.setAutoRepeatDelay(400); ab_fl_mas.setAutoRepeatInterval(40)
        layout.addWidget(ab_fl_mas)
        ab_fl_menos.clicked.connect(lambda: self.airbrush_flow_slider.setValue(self.airbrush_flow_slider.value() - 1))
        ab_fl_mas.clicked.connect(lambda: self.airbrush_flow_slider.setValue(self.airbrush_flow_slider.value() + 1))
        self.airbrush_flow_label = QLabel("20%")
        self.airbrush_flow_label.setFixedWidth(32)
        self.airbrush_flow_label.setStyleSheet(theme.value_label_qss())
        layout.addWidget(self.airbrush_flow_label)

        layout.addSpacing(10)

        # --- Forma de punta ---
        layout.addWidget(QLabel(t("opt.lbl.shape")))
        self.airbrush_shape_combo = QComboBox()
        self.airbrush_shape_combo.setFixedWidth(170)
        self.airbrush_shape_combo.setStyleSheet(self._get_combo_style())
        self._populate_shape_combo(self.airbrush_shape_combo)
        self.airbrush_shape_combo.currentIndexChanged.connect(self.on_airbrush_shape_changed)
        layout.addWidget(self.airbrush_shape_combo)

        layout.addSpacing(12)

        # --- Textura ---
        self.airbrush_speckle_check = QCheckBox(t("opt.chk.speckle", default="Moteado"))
        self.airbrush_speckle_check.setChecked(False)
        self.airbrush_speckle_check.setStyleSheet(self._get_check_style())
        self.airbrush_speckle_check.setToolTip(t("opt.tt.airbrush_speckle"))
        self.airbrush_speckle_check.toggled.connect(self.on_airbrush_speckle_toggled)
        layout.addWidget(self.airbrush_speckle_check)

        layout.addStretch()
        return widget

    def on_airbrush_hardness_changed(self, value):
        self.airbrush_hardness_label.setText(f"{value}%")
        if self.main_window: self.main_window.update_airbrush_hardness(value)

    def on_airbrush_flow_changed(self, value):
        self.airbrush_flow_label.setText(f"{value}%")
        if self.main_window: self.main_window.update_airbrush_flow(value)

    def on_airbrush_shape_changed(self, index):
        if self.main_window:
            self.main_window.update_airbrush_shape(self.airbrush_shape_combo.currentData())

    def on_airbrush_speckle_toggled(self, checked):
        if self.main_window:
            self.main_window.update_airbrush_texture("speckled" if checked else "smooth")

    def create_pen_panel(self):
        """Panel de Pincel: Tamaño (con auto-repeat), Dureza, Espaciado y Relleno unificados"""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(2, 0, 5, 0)
        layout.setSpacing(4)
        
        # --- 1. CONTROL DE TAMAÑO ---
        layout.addWidget(QLabel(t("opt.lbl.size")))
        
        btn_menos_sz = QPushButton("-")
        btn_menos_sz.setFixedSize(20, 20)
        btn_menos_sz.setStyleSheet(self._get_btn_style())
        btn_menos_sz.setAutoRepeat(True) 
        btn_menos_sz.setAutoRepeatDelay(400)
        btn_menos_sz.setAutoRepeatInterval(40)
        layout.addWidget(btn_menos_sz)
        
        self.pen_size_box = QComboBox()
        self.pen_size_box.setMaxVisibleItems(25)
        self.pen_size_box.setEditable(True)
        self.pen_size_box.setFixedWidth(75)  
        tamaños = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "12", "14", "16", "18", "20", "25", "30", "35", "40", "45", "50", "55", "60", "70", "75", "80", "90", "100", "125", "150", "175", "200", "225", "250", "275", "300"]
        self.pen_size_box.addItems(tamaños)
        self.pen_size_box.setCurrentText("5")
        self.pen_size_box.setStyleSheet(self._get_combo_style())
        self.pen_size_box.currentTextChanged.connect(self.on_size_changed)
        layout.addWidget(self.pen_size_box)
        
        btn_mas_sz = QPushButton("+")
        btn_mas_sz.setFixedSize(20, 20)
        btn_mas_sz.setStyleSheet(self._get_btn_style())
        btn_mas_sz.setAutoRepeat(True) 
        btn_mas_sz.setAutoRepeatDelay(400)
        btn_mas_sz.setAutoRepeatInterval(40)
        layout.addWidget(btn_mas_sz)
        
        btn_menos_sz.clicked.connect(lambda: self.decrease_size(self.pen_size_box))
        btn_mas_sz.clicked.connect(lambda: self.increase_size(self.pen_size_box))
        
        layout.addSpacing(10)
        
        # --- FORMA DE LA PUNTA ---
        layout.addWidget(QLabel(t("opt.lbl.shape")))
        self.brush_shape_combo = QComboBox()
        self.brush_shape_combo.setFixedWidth(170)
        self.brush_shape_combo.setStyleSheet(self._get_combo_style())
        self._populate_shape_combo(self.brush_shape_combo)
        self.brush_shape_combo.currentIndexChanged.connect(self.on_brush_shape_changed)
        layout.addWidget(self.brush_shape_combo)
        layout.addSpacing(10)

        # --- 2. BARRA DESLIZANTE DE DUREZA ---
        layout.addWidget(QLabel(t("opt.lbl.hardness")))
        
        btn_menos_hd = QPushButton("-")
        btn_menos_hd.setFixedSize(20, 20)
        btn_menos_hd.setStyleSheet(self._get_btn_style())
        btn_menos_hd.setAutoRepeat(True)
        btn_menos_hd.setAutoRepeatDelay(400)
        btn_menos_hd.setAutoRepeatInterval(40)
        layout.addWidget(btn_menos_hd)
        
        self.hardness_slider = QSlider(Qt.Orientation.Horizontal)
        self.hardness_slider.setRange(1, 100)
        self.hardness_slider.setValue(100)
        self.hardness_slider.setFixedWidth(90)
        self.hardness_slider.setStyleSheet(self._get_slider_style())
        layout.addWidget(self.hardness_slider)
        
        btn_mas_hd = QPushButton("+")
        btn_mas_hd.setFixedSize(20, 20)
        btn_mas_hd.setStyleSheet(self._get_btn_style())
        btn_mas_hd.setAutoRepeat(True)
        btn_mas_hd.setAutoRepeatDelay(400)
        btn_mas_hd.setAutoRepeatInterval(40)
        layout.addWidget(btn_mas_hd)
        
        self.hardness_value_label = QLabel("100%")
        self.hardness_value_label.setFixedWidth(32)
        self.hardness_value_label.setStyleSheet(theme.value_label_qss())
        layout.addWidget(self.hardness_value_label)
        
        self.hardness_slider.valueChanged.connect(self.on_hardness_slider_changed)
        btn_menos_hd.clicked.connect(lambda: self.hardness_slider.setValue(self.hardness_slider.value() - 1))
        btn_mas_hd.clicked.connect(lambda: self.hardness_slider.setValue(self.hardness_slider.value() + 1))

        layout.addSpacing(10)

        # --- 2b. OPACIDAD DEL TRAZO ---
        # Independiente del alfa del color: el motor de cobertura la aplica al
        # recomponer (cobertura × opacidad), uniforme aunque el trazo se solape.
        # Solo actúa con relleno SÓLIDO: con un patrón se deshabilita.
        self.brush_opacity_lbl = QLabel(t("opt.lbl.opacity"))
        layout.addWidget(self.brush_opacity_lbl)

        btn_menos_op = QPushButton("-")
        btn_menos_op.setFixedSize(20, 20)
        btn_menos_op.setStyleSheet(self._get_btn_style())
        btn_menos_op.setAutoRepeat(True)
        btn_menos_op.setAutoRepeatDelay(400)
        btn_menos_op.setAutoRepeatInterval(40)
        layout.addWidget(btn_menos_op)

        self.brush_opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.brush_opacity_slider.setRange(1, 100)
        self.brush_opacity_slider.setValue(100)
        self.brush_opacity_slider.setFixedWidth(90)
        self.brush_opacity_slider.setStyleSheet(self._get_slider_style())
        self.brush_opacity_slider.setToolTip(t("opt.brush_opacity.tip"))
        layout.addWidget(self.brush_opacity_slider)

        btn_mas_op = QPushButton("+")
        btn_mas_op.setFixedSize(20, 20)
        btn_mas_op.setStyleSheet(self._get_btn_style())
        btn_mas_op.setAutoRepeat(True)
        btn_mas_op.setAutoRepeatDelay(400)
        btn_mas_op.setAutoRepeatInterval(40)
        layout.addWidget(btn_mas_op)

        self.brush_opacity_value_label = QLabel("100%")
        self.brush_opacity_value_label.setFixedWidth(32)
        self.brush_opacity_value_label.setStyleSheet(theme.value_label_qss())
        layout.addWidget(self.brush_opacity_value_label)
        self.brush_opacity_slider.valueChanged.connect(self.on_brush_opacity_changed)
        btn_menos_op.clicked.connect(lambda: self.brush_opacity_slider.setValue(self.brush_opacity_slider.value() - 1))
        btn_mas_op.clicked.connect(lambda: self.brush_opacity_slider.setValue(self.brush_opacity_slider.value() + 1))
        # Que el des/habilitado con patrón alcance también a los botones -/+
        self._brush_opacity_btns = (btn_menos_op, btn_mas_op)

        layout.addSpacing(10)

        # --- 3. BARRA DESLIZANTE DE ESPACIADO ---
        layout.addWidget(QLabel(t("opt.lbl.spacing")))
        
        btn_menos_sp = QPushButton("-")
        btn_menos_sp.setFixedSize(20, 20)
        btn_menos_sp.setStyleSheet(self._get_btn_style())
        btn_menos_sp.setAutoRepeat(True)
        btn_menos_sp.setAutoRepeatDelay(400)
        btn_menos_sp.setAutoRepeatInterval(40)
        layout.addWidget(btn_menos_sp)
        
        self.spacing_slider = QSlider(Qt.Orientation.Horizontal)
        self.spacing_slider.setRange(1, 200)
        self.spacing_slider.setValue(10)     
        self.spacing_slider.setFixedWidth(90)
        self.spacing_slider.setStyleSheet(self._get_slider_style())
        layout.addWidget(self.spacing_slider)
        
        btn_mas_sp = QPushButton("+")
        btn_mas_sp.setFixedSize(20, 20)
        btn_mas_sp.setStyleSheet(self._get_btn_style())
        btn_mas_sp.setAutoRepeat(True)
        btn_mas_sp.setAutoRepeatDelay(400)
        btn_mas_sp.setAutoRepeatInterval(40)
        layout.addWidget(btn_mas_sp)
        
        self.spacing_value_label = QLabel("10%")
        self.spacing_value_label.setFixedWidth(38)
        self.spacing_value_label.setStyleSheet(theme.value_label_qss())
        layout.addWidget(self.spacing_value_label)
        
        self.spacing_slider.valueChanged.connect(self.on_spacing_slider_changed)
        btn_menos_sp.clicked.connect(lambda: self.spacing_slider.setValue(self.spacing_slider.value() - 1))
        btn_mas_sp.clicked.connect(lambda: self.spacing_slider.setValue(self.spacing_slider.value() + 1))
        
        # --- 4. CONTROL DE RELLENO (PATRÓN) ---
        layout.addSpacing(10)
        layout.addWidget(QLabel(t("opt.lbl.fill")))
        
        self.pattern_combo = QComboBox()
        self.pattern_combo.setFixedWidth(175)
        self.pattern_combo.setStyleSheet(self._get_combo_style())
        
        self._populate_fill_combo(self.pattern_combo, include_transparent=False)
        self.pattern_combo.setIconSize(QSize(16, 16))
        self._append_custom_patterns(self.pattern_combo)

        self.pattern_combo.currentIndexChanged.connect(self.on_pattern_changed)
        layout.addWidget(self.pattern_combo)

        # --- 5. PINCEL DE SELECCIÓN ---
        # Sin marcar: pincel normal. Marcado: el pincel define una SELECCIÓN al
        # pintar (izq=añade, der=resta), sin tocar los píxeles de la capa.
        layout.addSpacing(12)
        self.pen_selection_check = QCheckBox(
            t("opt.chk.sel_brush", default="Pincel de selección"))
        self.pen_selection_check.setStyleSheet(theme.checkbox_qss())
        self.pen_selection_check.toggled.connect(self.on_pen_selection_toggled)
        layout.addWidget(self.pen_selection_check)

        # --- 6. SUAVIZADO (ANTIALIASING) ---
        # Marcado (por defecto): bordes suaves. Sin marcar: bordes dentados.
        layout.addSpacing(12)
        self.brush_antialias_check = QCheckBox(
            t("opt.chk.antialias", default="Suavizado"))
        self.brush_antialias_check.setStyleSheet(theme.checkbox_qss())
        self.brush_antialias_check.setChecked(True)
        self.brush_antialias_check.setToolTip(
            t("opt.chk.antialias.tip", default="Bordes suaves; desactívalo para bordes dentados"))
        self.brush_antialias_check.toggled.connect(self.on_brush_antialias_toggled)
        layout.addWidget(self.brush_antialias_check)

        # 🚨 EL MUELLE AL FINAL ABSOLUTO: Empuja todo el bloque junto hacia la izquierda
        layout.addStretch()
        return widget

    def on_pen_selection_toggled(self, checked):
        if getattr(self, 'is_syncing', False):
            return
        if self.main_window:
            self.main_window.update_pen_selection_mode(checked)

    def on_brush_antialias_toggled(self, checked):
        if getattr(self, 'is_syncing', False):
            return
        if self.main_window:
            self.main_window.update_brush_antialias(checked)

    def create_clone_panel(self):
        """Panel del Sello de clonar: Tamaño, Dureza y Espaciado. SIN relleno
        (el sello copia píxeles del origen; el patrón de relleno no aplica)."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(2, 0, 5, 0)
        layout.setSpacing(4)

        # --- 1. TAMAÑO ---
        layout.addWidget(QLabel(t("opt.lbl.size")))
        btn_menos_sz = QPushButton("-")
        btn_menos_sz.setFixedSize(20, 20)
        btn_menos_sz.setStyleSheet(self._get_btn_style())
        btn_menos_sz.setAutoRepeat(True)
        btn_menos_sz.setAutoRepeatDelay(400)
        btn_menos_sz.setAutoRepeatInterval(40)
        layout.addWidget(btn_menos_sz)

        self.clone_size_box = QComboBox()
        self.clone_size_box.setMaxVisibleItems(25)
        self.clone_size_box.setEditable(True)
        self.clone_size_box.setFixedWidth(75)
        tamanos = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "12", "14",
                   "16", "18", "20", "25", "30", "35", "40", "45", "50", "55",
                   "60", "70", "75", "80", "90", "100", "125", "150", "175",
                   "200", "225", "250", "275", "300"]
        self.clone_size_box.addItems(tamanos)
        self.clone_size_box.setCurrentText("5")
        self.clone_size_box.setStyleSheet(self._get_combo_style())
        self.clone_size_box.currentTextChanged.connect(self.on_size_changed)
        layout.addWidget(self.clone_size_box)

        btn_mas_sz = QPushButton("+")
        btn_mas_sz.setFixedSize(20, 20)
        btn_mas_sz.setStyleSheet(self._get_btn_style())
        btn_mas_sz.setAutoRepeat(True)
        btn_mas_sz.setAutoRepeatDelay(400)
        btn_mas_sz.setAutoRepeatInterval(40)
        layout.addWidget(btn_mas_sz)

        btn_menos_sz.clicked.connect(lambda: self.decrease_size(self.clone_size_box))
        btn_mas_sz.clicked.connect(lambda: self.increase_size(self.clone_size_box))

        layout.addSpacing(10)

        # --- 2. DUREZA ---
        layout.addWidget(QLabel(t("opt.lbl.hardness")))
        btn_menos_hd = QPushButton("-")
        btn_menos_hd.setFixedSize(20, 20)
        btn_menos_hd.setStyleSheet(self._get_btn_style())
        btn_menos_hd.setAutoRepeat(True)
        btn_menos_hd.setAutoRepeatDelay(400)
        btn_menos_hd.setAutoRepeatInterval(40)
        layout.addWidget(btn_menos_hd)

        self.clone_hardness_slider = QSlider(Qt.Orientation.Horizontal)
        self.clone_hardness_slider.setRange(1, 100)
        self.clone_hardness_slider.setValue(100)
        self.clone_hardness_slider.setFixedWidth(90)
        self.clone_hardness_slider.setStyleSheet(self._get_slider_style())
        layout.addWidget(self.clone_hardness_slider)

        btn_mas_hd = QPushButton("+")
        btn_mas_hd.setFixedSize(20, 20)
        btn_mas_hd.setStyleSheet(self._get_btn_style())
        btn_mas_hd.setAutoRepeat(True)
        btn_mas_hd.setAutoRepeatDelay(400)
        btn_mas_hd.setAutoRepeatInterval(40)
        layout.addWidget(btn_mas_hd)

        self.clone_hardness_label = QLabel("100%")
        self.clone_hardness_label.setFixedWidth(32)
        self.clone_hardness_label.setStyleSheet(theme.value_label_qss())
        layout.addWidget(self.clone_hardness_label)

        self.clone_hardness_slider.valueChanged.connect(self.on_clone_hardness_changed)
        btn_menos_hd.clicked.connect(lambda: self.clone_hardness_slider.setValue(self.clone_hardness_slider.value() - 1))
        btn_mas_hd.clicked.connect(lambda: self.clone_hardness_slider.setValue(self.clone_hardness_slider.value() + 1))

        layout.addSpacing(10)

        # --- 3. ESPACIADO ---
        layout.addWidget(QLabel(t("opt.lbl.spacing")))
        btn_menos_sp = QPushButton("-")
        btn_menos_sp.setFixedSize(20, 20)
        btn_menos_sp.setStyleSheet(self._get_btn_style())
        btn_menos_sp.setAutoRepeat(True)
        btn_menos_sp.setAutoRepeatDelay(400)
        btn_menos_sp.setAutoRepeatInterval(40)
        layout.addWidget(btn_menos_sp)

        self.clone_spacing_slider = QSlider(Qt.Orientation.Horizontal)
        self.clone_spacing_slider.setRange(1, 200)
        self.clone_spacing_slider.setValue(10)
        self.clone_spacing_slider.setFixedWidth(90)
        self.clone_spacing_slider.setStyleSheet(self._get_slider_style())
        layout.addWidget(self.clone_spacing_slider)

        btn_mas_sp = QPushButton("+")
        btn_mas_sp.setFixedSize(20, 20)
        btn_mas_sp.setStyleSheet(self._get_btn_style())
        btn_mas_sp.setAutoRepeat(True)
        btn_mas_sp.setAutoRepeatDelay(400)
        btn_mas_sp.setAutoRepeatInterval(40)
        layout.addWidget(btn_mas_sp)

        self.clone_spacing_label = QLabel("10%")
        self.clone_spacing_label.setFixedWidth(38)
        self.clone_spacing_label.setStyleSheet(theme.value_label_qss())
        layout.addWidget(self.clone_spacing_label)

        self.clone_spacing_slider.valueChanged.connect(self.on_clone_spacing_changed)
        btn_menos_sp.clicked.connect(lambda: self.clone_spacing_slider.setValue(self.clone_spacing_slider.value() - 1))
        btn_mas_sp.clicked.connect(lambda: self.clone_spacing_slider.setValue(self.clone_spacing_slider.value() + 1))

        layout.addSpacing(10)

        # --- 4. Forma de punta ---
        layout.addWidget(QLabel(t("opt.lbl.shape")))
        self.clone_shape_combo = QComboBox()
        self.clone_shape_combo.setFixedWidth(170)
        self.clone_shape_combo.setStyleSheet(self._get_combo_style())
        self._populate_shape_combo(self.clone_shape_combo)
        self.clone_shape_combo.currentIndexChanged.connect(self.on_clone_shape_changed)
        layout.addWidget(self.clone_shape_combo)

        layout.addSpacing(12)

        # --- 5. Alineado / Todas las capas ---
        self.clone_aligned_check = QCheckBox(t("opt.chk.aligned", default="Alineado"))
        self.clone_aligned_check.setChecked(True)
        self.clone_aligned_check.setStyleSheet(self._get_check_style())
        self.clone_aligned_check.setToolTip(t("opt.tt.clone_aligned"))
        self.clone_aligned_check.toggled.connect(self.on_clone_aligned_toggled)
        layout.addWidget(self.clone_aligned_check)

        layout.addSpacing(12)
        self.clone_sample_all_check = QCheckBox(t("opt.chk.all_layers"))
        self.clone_sample_all_check.setChecked(False)
        self.clone_sample_all_check.setStyleSheet(self._get_check_style())
        self.clone_sample_all_check.setToolTip(t("opt.tt.clone_sample_all"))
        self.clone_sample_all_check.toggled.connect(self.on_clone_sample_all_toggled)
        layout.addWidget(self.clone_sample_all_check)

        layout.addStretch()
        return widget

    def on_clone_hardness_changed(self, value):
        self.clone_hardness_label.setText(f"{value}%")
        if self.main_window:
            self.main_window.update_brush_hardness(value)

    def on_clone_spacing_changed(self, value):
        self.clone_spacing_label.setText(f"{value}%")
        if self.main_window:
            self.main_window.update_brush_spacing(value)

    def on_clone_shape_changed(self, index):
        if self.main_window:
            self.main_window.update_clone_shape(self.clone_shape_combo.currentData())

    def on_clone_aligned_toggled(self, checked):
        if self.main_window:
            self.main_window.update_clone_aligned(checked)

    def on_clone_sample_all_toggled(self, checked):
        if self.main_window:
            self.main_window.update_clone_sample_all(checked)

    def _sync_clone_panel_from_canvas(self):
        """Al activar el sello, refleja en su panel los valores reales del
        lienzo (tamaño/dureza/espaciado), para que el círculo de origen y el
        cursor coincidan con lo que se va a clonar. Bloquea señales para no
        reescribir el lienzo durante la sincronización."""
        canvas = self.main_window.get_current_canvas() if self.main_window else None
        if not canvas:
            return
        size = getattr(canvas, "brush_size", 5)
        hardness = getattr(canvas, "brush_hardness", 75)
        spacing = getattr(canvas, "brush_spacing", 10)
        for w in (self.clone_size_box, self.clone_hardness_slider, self.clone_spacing_slider):
            w.blockSignals(True)
        self.clone_size_box.setCurrentText(str(size))
        self.clone_hardness_slider.setValue(hardness)
        self.clone_spacing_slider.setValue(spacing)
        for w in (self.clone_size_box, self.clone_hardness_slider, self.clone_spacing_slider):
            w.blockSignals(False)
        self.clone_hardness_label.setText(f"{hardness}%")
        self.clone_spacing_label.setText(f"{spacing}%")
        shape = getattr(canvas, "clone_shape", "round")
        aligned = getattr(canvas, "clone_aligned", True)
        sample_all = getattr(canvas, "clone_sample_all", False)
        for w in (self.clone_shape_combo, self.clone_aligned_check, self.clone_sample_all_check):
            w.blockSignals(True)
        _i = self.clone_shape_combo.findData(shape)
        if _i >= 0:
            self.clone_shape_combo.setCurrentIndex(_i)
        self.clone_aligned_check.setChecked(aligned)
        self.clone_sample_all_check.setChecked(sample_all)
        for w in (self.clone_shape_combo, self.clone_aligned_check, self.clone_sample_all_check):
            w.blockSignals(False)

    def create_eraser_panel(self):
        """Panel de Goma: Tamaño (auto-repeat), Dureza y Espaciado individuales"""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(2, 0, 5, 0)
        layout.setSpacing(4)
        
        # --- 1. CONTROL DE TAMAÑO ---
        layout.addWidget(QLabel(t("opt.lbl.size")))
        
        btn_menos = QPushButton("-")
        btn_menos.setFixedSize(20, 20)
        btn_menos.setStyleSheet(self._get_btn_style())
        btn_menos.setAutoRepeat(True)
        btn_menos.setAutoRepeatDelay(400)
        btn_menos.setAutoRepeatInterval(40)
        layout.addWidget(btn_menos)
        
        self.eraser_size_box = QComboBox()
        self.eraser_size_box.setMaxVisibleItems(25)
        self.eraser_size_box.setEditable(True)
        self.eraser_size_box.setFixedWidth(75)  
        tamaños = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "12", "14", "16", "18", "20", "24", "28", "32", "40", "64", "128"]
        self.eraser_size_box.addItems(tamaños)
        self.eraser_size_box.setCurrentText("5")
        self.eraser_size_box.setStyleSheet(self._get_combo_style())
        self.eraser_size_box.currentTextChanged.connect(self.on_size_changed)
        layout.addWidget(self.eraser_size_box)
        
        btn_mas = QPushButton("+")
        btn_mas.setFixedSize(20, 20)
        btn_mas.setStyleSheet(self._get_btn_style())
        btn_mas.setAutoRepeat(True)
        btn_mas.setAutoRepeatDelay(400)
        btn_mas.setAutoRepeatInterval(40)
        layout.addWidget(btn_mas)
        
        btn_menos.clicked.connect(lambda: self.decrease_size(self.eraser_size_box))
        btn_mas.clicked.connect(lambda: self.increase_size(self.eraser_size_box))
        
        layout.addSpacing(10)
        
        # --- FORMA DE LA PUNTA ---
        layout.addWidget(QLabel(t("opt.lbl.shape")))
        self.eraser_shape_combo = QComboBox()
        self.eraser_shape_combo.setFixedWidth(170)
        self.eraser_shape_combo.setStyleSheet(self._get_combo_style())
        self._populate_shape_combo(self.eraser_shape_combo)
        self.eraser_shape_combo.currentIndexChanged.connect(self.on_eraser_shape_changed)
        layout.addWidget(self.eraser_shape_combo)
        layout.addSpacing(10)

        # --- MODO: Borrador / Borrador de color ---
        from PySide6.QtCore import QSize as _QSize
        from PySide6.QtGui import QIcon as _QIcon
        import os as _os
        layout.addWidget(QLabel(t("opt.lbl.mode")))
        self.eraser_mode_combo = QComboBox()
        self.eraser_mode_combo.setFixedWidth(170)
        self.eraser_mode_combo.setStyleSheet(self._get_combo_style())
        self.eraser_mode_combo.setIconSize(_QSize(16, 16))
        for _label, _data, _icon in ((t("tool.name.eraser"), "normal", "eraser.png"),
                                     (t("opt.eraser.color"), "color", "eraser_color.png"),
                                     (t("opt.eraser.background"), "background", "eraser_bg.png")):
            _p = ":/icons/" + _icon
            if QFile.exists(_p):
                self.eraser_mode_combo.addItem(theme.icono(_p), _label, _data)
            else:
                self.eraser_mode_combo.addItem(_label, _data)
        self.eraser_mode_combo.currentIndexChanged.connect(self.on_eraser_mode_changed)
        layout.addWidget(self.eraser_mode_combo)
        layout.addSpacing(10)

        # --- 2. BARRA DESLIZANTE DE DUREZA (NUEVA PARA GOMA) ---
        layout.addWidget(QLabel(t("opt.lbl.hardness")))
        
        btn_menos_hd = QPushButton("-")
        btn_menos_hd.setFixedSize(20, 20)
        btn_menos_hd.setStyleSheet(self._get_btn_style())
        btn_menos_hd.setAutoRepeat(True)
        btn_menos_hd.setAutoRepeatDelay(400)
        btn_menos_hd.setAutoRepeatInterval(40)
        layout.addWidget(btn_menos_hd)
        
        self.eraser_hardness_slider = QSlider(Qt.Orientation.Horizontal)
        self.eraser_hardness_slider.setRange(1, 100)
        self.eraser_hardness_slider.setValue(100) # 100% por defecto (borrado sólido tradicional)
        self.eraser_hardness_slider.setFixedWidth(90)
        self.eraser_hardness_slider.setStyleSheet(self._get_slider_style())
        layout.addWidget(self.eraser_hardness_slider)
        
        btn_mas_hd = QPushButton("+")
        btn_mas_hd.setFixedSize(20, 20)
        btn_mas_hd.setStyleSheet(self._get_btn_style())
        btn_mas_hd.setAutoRepeat(True)
        btn_mas_hd.setAutoRepeatDelay(400)
        btn_mas_hd.setAutoRepeatInterval(40)
        layout.addWidget(btn_mas_hd)
        
        self.eraser_hardness_label = QLabel("100%")
        self.eraser_hardness_label.setFixedWidth(32)
        self.eraser_hardness_label.setStyleSheet(theme.value_label_qss())
        layout.addWidget(self.eraser_hardness_label)
        
        self.eraser_hardness_slider.valueChanged.connect(self.on_eraser_hardness_changed)
        btn_menos_hd.clicked.connect(lambda: self.eraser_hardness_slider.setValue(self.eraser_hardness_slider.value() - 1))
        btn_mas_hd.clicked.connect(lambda: self.eraser_hardness_slider.setValue(self.eraser_hardness_slider.value() + 1))
        
        layout.addSpacing(10)

        # --- 3. BARRA DESLIZANTE DE ESPACIADO (NUEVA PARA GOMA) ---
        layout.addWidget(QLabel(t("opt.lbl.spacing")))
        
        btn_menos_sp = QPushButton("-")
        btn_menos_sp.setFixedSize(20, 20)
        btn_menos_sp.setStyleSheet(self._get_btn_style())
        btn_menos_sp.setAutoRepeat(True)
        btn_menos_sp.setAutoRepeatDelay(400)
        btn_menos_sp.setAutoRepeatInterval(40)
        layout.addWidget(btn_menos_sp)
        
        self.eraser_spacing_slider = QSlider(Qt.Orientation.Horizontal)
        self.eraser_spacing_slider.setRange(1, 200)
        self.eraser_spacing_slider.setValue(10) # 10% por defecto para borrado fluido
        self.eraser_spacing_slider.setFixedWidth(90)
        self.eraser_spacing_slider.setStyleSheet(self._get_slider_style())
        layout.addWidget(self.eraser_spacing_slider)
        
        btn_mas_sp = QPushButton("+")
        btn_mas_sp.setFixedSize(20, 20)
        btn_mas_sp.setStyleSheet(self._get_btn_style())
        btn_mas_sp.setAutoRepeat(True)
        btn_mas_sp.setAutoRepeatDelay(400)
        btn_mas_sp.setAutoRepeatInterval(40)
        layout.addWidget(btn_mas_sp)
        
        self.eraser_spacing_label = QLabel("10%")
        self.eraser_spacing_label.setFixedWidth(38)
        self.eraser_spacing_label.setStyleSheet(theme.value_label_qss())
        layout.addWidget(self.eraser_spacing_label)
        
        self.eraser_spacing_slider.valueChanged.connect(self.on_eraser_spacing_changed)
        btn_menos_sp.clicked.connect(lambda: self.eraser_spacing_slider.setValue(self.eraser_spacing_slider.value() - 1))
        btn_mas_sp.clicked.connect(lambda: self.eraser_spacing_slider.setValue(self.eraser_spacing_slider.value() + 1))

        layout.addSpacing(10)

        # --- 4. TOLERANCIA (solo visible en modo "Borrador de color") ---
        self.eraser_tol_label_title = QLabel(t("opt.lbl.tolerance"))
        layout.addWidget(self.eraser_tol_label_title)

        self.eraser_tol_btn_menos = QPushButton("-")
        self.eraser_tol_btn_menos.setFixedSize(20, 20)
        self.eraser_tol_btn_menos.setStyleSheet(self._get_btn_style())
        self.eraser_tol_btn_menos.setAutoRepeat(True)
        self.eraser_tol_btn_menos.setAutoRepeatDelay(400)
        self.eraser_tol_btn_menos.setAutoRepeatInterval(40)
        layout.addWidget(self.eraser_tol_btn_menos)

        self.eraser_tolerance_slider = QSlider(Qt.Orientation.Horizontal)
        self.eraser_tolerance_slider.setRange(0, 255)
        self.eraser_tolerance_slider.setValue(32)
        self.eraser_tolerance_slider.setFixedWidth(90)
        self.eraser_tolerance_slider.setStyleSheet(self._get_slider_style())
        self.eraser_tolerance_slider.valueChanged.connect(self.on_eraser_tolerance_changed)
        layout.addWidget(self.eraser_tolerance_slider)

        self.eraser_tol_btn_mas = QPushButton("+")
        self.eraser_tol_btn_mas.setFixedSize(20, 20)
        self.eraser_tol_btn_mas.setStyleSheet(self._get_btn_style())
        self.eraser_tol_btn_mas.setAutoRepeat(True)
        self.eraser_tol_btn_mas.setAutoRepeatDelay(400)
        self.eraser_tol_btn_mas.setAutoRepeatInterval(40)
        layout.addWidget(self.eraser_tol_btn_mas)

        self.eraser_tolerance_label = QLabel("32")
        self.eraser_tolerance_label.setFixedWidth(28)
        self.eraser_tolerance_label.setStyleSheet(theme.value_label_qss())
        layout.addWidget(self.eraser_tolerance_label)

        self.eraser_tol_btn_menos.clicked.connect(lambda: self.eraser_tolerance_slider.setValue(self.eraser_tolerance_slider.value() - 1))
        self.eraser_tol_btn_mas.clicked.connect(lambda: self.eraser_tolerance_slider.setValue(self.eraser_tolerance_slider.value() + 1))

        # La tolerancia solo aplica en modo borrador de color/fondos
        self._set_eraser_tolerance_enabled(False)

        layout.addSpacing(10)

        # --- 5. OPCIONES EXCLUSIVAS DEL BORRADOR DE FONDOS ---
        self.eraser_bg_one_shot_check = QCheckBox(t("opt.chk.one_shot"))
        self.eraser_bg_one_shot_check.setChecked(False)
        self.eraser_bg_one_shot_check.setStyleSheet(self._get_check_style())
        self.eraser_bg_one_shot_check.setToolTip(t("opt.tt.one_shot"))
        self.eraser_bg_one_shot_check.toggled.connect(self.on_eraser_bg_one_shot_toggled)
        layout.addWidget(self.eraser_bg_one_shot_check)

        layout.addSpacing(10)

        self.eraser_bg_protect_primary_check = QCheckBox(t("opt.chk.protect_primary"))
        self.eraser_bg_protect_primary_check.setChecked(False)
        self.eraser_bg_protect_primary_check.setStyleSheet(self._get_check_style())
        self.eraser_bg_protect_primary_check.setToolTip(t("opt.tt.protect_primary"))
        self.eraser_bg_protect_primary_check.toggled.connect(self.on_eraser_bg_protect_primary_toggled)
        layout.addWidget(self.eraser_bg_protect_primary_check)

        # Solo visibles en modo "Borrador de fondos"
        self.eraser_bg_one_shot_check.setVisible(False)
        self.eraser_bg_protect_primary_check.setVisible(False)

        layout.addStretch()
        return widget

    def create_bucket_panel(self):
        """Panel del Cubo de Pintura: Selección de tipo de relleno geométrico"""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(2, 0, 5, 0)
        layout.setSpacing(4)
        
        # --- CONTROL DE RELLENO ---
        layout.addWidget(QLabel(t("opt.lbl.fill")))
        
        self.bucket_pattern_combo = QComboBox()
        self.bucket_pattern_combo.setFixedWidth(175)
        self.bucket_pattern_combo.setStyleSheet(self._get_combo_style())
        
        self._populate_fill_combo(self.bucket_pattern_combo, include_transparent=False)
        self._append_custom_patterns(self.bucket_pattern_combo)

        self.bucket_pattern_combo.currentIndexChanged.connect(self.on_bucket_pattern_changed)
        layout.addWidget(self.bucket_pattern_combo)

        layout.addSpacing(12)
        # --- Tolerancia ---
        layout.addWidget(QLabel(t("opt.lbl.tolerance")))
        self.bucket_tolerance_slider = QSlider(Qt.Horizontal)
        self.bucket_tolerance_slider.setRange(0, 255)
        self.bucket_tolerance_slider.setValue(32)
        self.bucket_tolerance_slider.setFixedWidth(120)
        self.bucket_tolerance_slider.setStyleSheet(self._get_slider_style())
        self.bucket_tolerance_label = QLabel("32")
        self.bucket_tolerance_label.setFixedWidth(28)
        self.bucket_tolerance_label.setStyleSheet(f"color: {theme.TEXT_DIM}; font-family: monospace; font-size: 11px;")
        self.bucket_tolerance_slider.valueChanged.connect(self.on_bucket_tolerance_changed)
        tol_minus = QPushButton("-")
        tol_minus.setFixedSize(20, 20)
        tol_minus.setStyleSheet(self._get_btn_style())
        tol_minus.setAutoRepeat(True); tol_minus.setAutoRepeatDelay(400); tol_minus.setAutoRepeatInterval(40)
        tol_minus.clicked.connect(lambda: self.bucket_tolerance_slider.setValue(self.bucket_tolerance_slider.value() - 1))
        tol_plus = QPushButton("+")
        tol_plus.setFixedSize(20, 20)
        tol_plus.setStyleSheet(self._get_btn_style())
        tol_plus.setAutoRepeat(True); tol_plus.setAutoRepeatDelay(400); tol_plus.setAutoRepeatInterval(40)
        tol_plus.clicked.connect(lambda: self.bucket_tolerance_slider.setValue(self.bucket_tolerance_slider.value() + 1))
        layout.addWidget(tol_minus)
        layout.addWidget(self.bucket_tolerance_slider)
        layout.addWidget(tol_plus)
        layout.addWidget(self.bucket_tolerance_label)

        layout.addSpacing(12)
        # --- Expansión del relleno (px bajo el contorno; evita el halo) ---
        layout.addWidget(QLabel(t("opt.lbl.expand_fill")))
        self.bucket_expand_slider = QSlider(Qt.Horizontal)
        self.bucket_expand_slider.setRange(0, 10)
        self.bucket_expand_slider.setValue(0)
        self.bucket_expand_slider.setFixedWidth(70)
        self.bucket_expand_slider.setStyleSheet(self._get_slider_style())
        self.bucket_expand_slider.setToolTip(t("opt.tip.expand_fill"))
        self.bucket_expand_label = QLabel("0")
        self.bucket_expand_label.setFixedWidth(18)
        self.bucket_expand_label.setStyleSheet(f"color: {theme.TEXT_DIM}; font-family: monospace; font-size: 11px;")
        self.bucket_expand_slider.valueChanged.connect(self.on_bucket_expand_changed)
        exp_menos = QPushButton("-")
        exp_menos.setFixedSize(20, 20)
        exp_menos.setStyleSheet(self._get_btn_style())
        exp_menos.setAutoRepeat(True); exp_menos.setAutoRepeatDelay(400); exp_menos.setAutoRepeatInterval(40)
        exp_menos.clicked.connect(lambda: self.bucket_expand_slider.setValue(self.bucket_expand_slider.value() - 1))
        exp_mas = QPushButton("+")
        exp_mas.setFixedSize(20, 20)
        exp_mas.setStyleSheet(self._get_btn_style())
        exp_mas.setAutoRepeat(True); exp_mas.setAutoRepeatDelay(400); exp_mas.setAutoRepeatInterval(40)
        exp_mas.clicked.connect(lambda: self.bucket_expand_slider.setValue(self.bucket_expand_slider.value() + 1))
        layout.addWidget(exp_menos)
        layout.addWidget(self.bucket_expand_slider)
        layout.addWidget(exp_mas)
        layout.addWidget(self.bucket_expand_label)

        layout.addSpacing(12)
        self.bucket_contiguous_check = QCheckBox(t("opt.chk.contiguous"))
        self.bucket_contiguous_check.setChecked(True)
        self.bucket_contiguous_check.setStyleSheet(self._get_check_style())
        self.bucket_contiguous_check.setToolTip(t("opt.tip.contig_bucket"))
        self.bucket_contiguous_check.toggled.connect(self.on_bucket_contiguous_toggled)
        layout.addWidget(self.bucket_contiguous_check)

        layout.addSpacing(12)
        self.bucket_antialias_check = QCheckBox(t("opt.chk.antialias"))
        self.bucket_antialias_check.setChecked(False)
        self.bucket_antialias_check.setStyleSheet(self._get_check_style())
        self.bucket_antialias_check.setToolTip(t("opt.tip.antialias"))
        self.bucket_antialias_check.toggled.connect(self.on_bucket_antialias_toggled)
        layout.addWidget(self.bucket_antialias_check)

        layout.addSpacing(12)
        self.bucket_sample_all_check = QCheckBox(t("opt.chk.all_layers"))
        self.bucket_sample_all_check.setChecked(False)
        self.bucket_sample_all_check.setStyleSheet(self._get_check_style())
        self.bucket_sample_all_check.setToolTip(t("opt.tip.sample_bucket"))
        self.bucket_sample_all_check.toggled.connect(self.on_bucket_sample_all_toggled)
        layout.addWidget(self.bucket_sample_all_check)
        
        layout.addStretch()
        return widget
    
    def on_bucket_pattern_changed(self, index):
        """Envía el patrón del Cubo al lienzo (independiente del Pincel)."""
        if self.is_syncing: return
        pattern = self.bucket_pattern_combo.itemData(index)
        if self.main_window:
            self.main_window.update_bucket_pattern(pattern)
        
    def on_bucket_tolerance_changed(self, value):
        self.bucket_tolerance_label.setText(str(value))
        if self.main_window:
            self.main_window.update_bucket_tolerance(value)

    def on_bucket_expand_changed(self, value):
        self.bucket_expand_label.setText(str(value))
        if self.main_window:
            self.main_window.update_bucket_expand(value)

    def on_bucket_contiguous_toggled(self, checked):
        if self.main_window:
            self.main_window.update_bucket_contiguous(checked)

    def on_bucket_antialias_toggled(self, checked):
        if self.main_window:
            self.main_window.update_bucket_antialias(checked)

    def on_bucket_sample_all_toggled(self, checked):
        if self.main_window:
            self.main_window.update_bucket_sample_all(checked)

    def _fill_pattern_defs(self):
        """Patrones de relleno nativos de Qt (icono, etiqueta, estilo). Lista
        única reutilizada por los combos de formas, cubo y pluma."""
        B = Qt.BrushStyle
        return [
            (":/icons/fill_solid.png",     t("opt.fill.solid"),                  B.SolidPattern),
            (":/icons/fill_hor.png",       t("opt.fill.h_lines"),     B.HorPattern),
            (":/icons/fill_ver.png",       t("opt.fill.v_lines"),       B.VerPattern),
            (":/icons/fill_cross.png",     t("opt.fill.grid"),                 B.CrossPattern),
            (":/icons/fill_bdiag.png",     t("opt.fill.l_diag"),      B.BDiagPattern),
            (":/icons/fill_fdiag.png",     t("opt.fill.r_diag"),        B.FDiagPattern),
            (":/icons/fill_diagcross.png", t("opt.fill.diag_grid"),        B.DiagCrossPattern),
            (":/icons/fill_dense1.png",    t("opt.fill.dot1"),      B.Dense1Pattern),
            (":/icons/fill_dense2.png",    t("opt.fill.dot2"),          B.Dense2Pattern),
            (":/icons/fill_dense3.png",    t("opt.fill.dot3"),    B.Dense3Pattern),
            (":/icons/fill_dense4.png",    t("opt.fill.dot4"),          B.Dense4Pattern),
            (":/icons/fill_dense5.png",    t("opt.fill.dot5"), B.Dense5Pattern),
            (":/icons/fill_dense6.png",    t("opt.fill.dot6"),       B.Dense6Pattern),
            (":/icons/fill_dense7.png",    t("opt.fill.dot7"),   B.Dense7Pattern),
        ]

    def _populate_shape_combo(self, combo):
        """Rellena un combo de formas de punta con iconos (con texto de
        reserva si el icono no existe todavia)."""
        combo.setIconSize(QSize(16, 16))
        defs = [("round", t("opt.brush.round"), "\u25cf"), ("square", t("opt.brush.square"), "\u25a0"),
                ("diamond", t("opt.brush.diamond"), "\u25c6"), ("horizontal", t("opt.brush.h_bar"), "\u2014"),
                ("vertical", t("opt.brush.v_bar"), "\u2758"), ("fdiag", t("opt.brush.d_bar"), "\\"),
                ("bdiag", t("opt.brush.d_bar"), "/")]
        for sid, label, fb in defs:
            icon = ":/icons/shape_%s.png" % sid
            if QFile.exists(icon):
                combo.addItem(theme.icono(icon), label, sid)
            else:
                combo.addItem("%s  %s" % (fb, label), sid)

    def _populate_fill_combo(self, combo, include_transparent=False):
        """Rellena un combo de patrones con iconos. Con include_transparent
        antepone la opción 'Transparente' (sin relleno, dato None)."""
        combo.setIconSize(QSize(16, 16))  # igualar altura con los demás combos
        if include_transparent:
            combo.addItem(theme.icono(":/icons/fill_none.png"), t("opt.fill.transparent"), None)
        for icon, label, style in self._fill_pattern_defs():
            combo.addItem(theme.icono(icon), label, style)

    def _append_custom_patterns(self, combo):
        """Añade los patrones PROCEDURALES (tablero, ladrillo, zigzag...) al combo,
        con icono generado por código. Colores de previsualización claros para que
        se distingan sobre el fondo oscuro del combo. Solo el PINCEL los usa."""
        fg = QColor(theme.TEXT)
        bg = QColor(theme.TEXT_MUTED)
        for pid, _label, two_tone in pattern_tiles.CUSTOM_BRUSH_PATTERNS:
            icon = pattern_tiles.make_icon(pid, fg, bg if two_tone else None)
            combo.addItem(icon, t("pat." + pid), pid)

    def create_shapes_panel(self):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(2, 0, 5, 0)
        layout.setSpacing(4)

        # --- Forma ---
        layout.addWidget(QLabel(t("opt.lbl.shape_space")))
        from tools.shape_picker import ShapePicker
        self.shape_selector = ShapePicker(icon_size=16)
        self.shape_selector.shapeChanged.connect(self.main_window.update_active_shape)
        layout.addWidget(self.shape_selector)

        layout.addSpacing(12)
        layout.addWidget(QLabel(t("opt.lbl.style")))
        self.shape_style_combo = QComboBox()
        self.shape_style_combo.setFixedWidth(155)
        self.shape_style_combo.setStyleSheet(self._get_combo_style())
        self.shape_style_combo.setIconSize(QSize(25, 14))
        from PySide6.QtGui import QPixmap, QPainter, QPen, QIcon, QColor
        for _lbl, _st in ((t("opt.fill.solid"), Qt.PenStyle.SolidLine),
                          (t("opt.style.dash"), Qt.PenStyle.DashLine),
                          (t("opt.style.dot"), Qt.PenStyle.DotLine),
                          (t("opt.style.dash_dot"), Qt.PenStyle.DashDotLine),
                          (t("opt.style.dash_dot_dot"), Qt.PenStyle.DashDotDotLine)):
            pixmap = QPixmap(25, 14)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            # Dibujamos la línea con el estilo correspondiente
            pen = QPen(QColor(theme.TEXT), 2, _st, Qt.FlatCap)
            painter.setPen(pen)
            painter.drawLine(2, 7, 23, 7)
            painter.end()
            self.shape_style_combo.addItem(QIcon(pixmap), _lbl, _st)
        self.shape_style_combo.currentIndexChanged.connect(self.on_shape_line_style_changed)
        layout.addWidget(self.shape_style_combo)
        self.shape_selector.setFixedHeight(self.shape_style_combo.sizeHint().height())

        layout.addSpacing(12)

        # --- Grosor del contorno (estilo pincel: - [combo] +) ---
        layout.addWidget(QLabel(t("opt.lbl.thickness")))
        btn_menos_sz = QPushButton("-")
        btn_menos_sz.setFixedSize(20, 20)
        btn_menos_sz.setStyleSheet(self._get_btn_style())
        btn_menos_sz.setAutoRepeat(True); btn_menos_sz.setAutoRepeatDelay(400); btn_menos_sz.setAutoRepeatInterval(40)
        layout.addWidget(btn_menos_sz)

        self.shape_size_box = QComboBox()
        self.shape_size_box.setMaxVisibleItems(25)
        self.shape_size_box.setEditable(True)
        self.shape_size_box.setFixedWidth(75)
        self.shape_size_box.addItems(["1","2","3","4","5","6","7","8","9","10","12","14","16","18","20","25","30","35","40","45","50","60","70","80","90","100"])
        self.shape_size_box.setCurrentText("5")
        self.shape_size_box.setStyleSheet(self._get_combo_style())
        self.shape_size_box.currentTextChanged.connect(self.on_size_changed)
        layout.addWidget(self.shape_size_box)

        btn_mas_sz = QPushButton("+")
        btn_mas_sz.setFixedSize(20, 20)
        btn_mas_sz.setStyleSheet(self._get_btn_style())
        btn_mas_sz.setAutoRepeat(True); btn_mas_sz.setAutoRepeatDelay(400); btn_mas_sz.setAutoRepeatInterval(40)
        layout.addWidget(btn_mas_sz)

        btn_menos_sz.clicked.connect(lambda: self.decrease_size(self.shape_size_box))
        btn_mas_sz.clicked.connect(lambda: self.increase_size(self.shape_size_box))

        layout.addSpacing(12)

        # --- Relleno (Transparente por defecto + patrones, como el cubo) ---
        self.shape_fill_label = QLabel(t("opt.lbl.fill"))
        layout.addWidget(self.shape_fill_label)
        self.shape_fill_combo = QComboBox()
        self.shape_fill_combo.setFixedWidth(175)
        self.shape_fill_combo.setStyleSheet(self._get_combo_style())
        self._populate_fill_combo(self.shape_fill_combo, include_transparent=True)
        self._append_custom_patterns(self.shape_fill_combo)
        self.shape_fill_combo.currentIndexChanged.connect(self.on_shape_fill_changed)
        layout.addWidget(self.shape_fill_combo)

        layout.addStretch()
        return widget

    def on_shape_fill_changed(self, index):
        if getattr(self, 'is_syncing', False): return
        pattern = self.shape_fill_combo.itemData(index)
        if self.main_window:
            self.main_window.update_shape_fill(pattern)

    def on_shape_line_style_changed(self, index):
        if getattr(self, 'is_syncing', False): return
        if self.main_window:
            self.main_window.update_shape_line_style(self.shape_style_combo.itemData(index))

    def _set_shape_fill_enabled(self, enabled):
        """La línea no admite relleno: ocultamos su control para esa forma."""
        if hasattr(self, 'shape_fill_label'):
            self.shape_fill_label.setVisible(enabled)
            self.shape_fill_combo.setVisible(enabled)
            self._panel_clip.adjustInnerSize()


    def create_pencil_panel(self):
        """Panel del Lápiz: Tamaño (- [combo] +) y Forma (Redondo/Cuadrado).
        Trazo siempre duro y sin suavizado. Tamaño y forma propios, independientes
        del pincel."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(2, 0, 5, 0)
        layout.setSpacing(4)

        layout.addWidget(QLabel(t("opt.lbl.size")))
        bm = QPushButton("-"); bm.setFixedSize(20, 20); bm.setStyleSheet(self._get_btn_style())
        bm.setAutoRepeat(True); bm.setAutoRepeatDelay(400); bm.setAutoRepeatInterval(40)
        layout.addWidget(bm)
        self.pencil_size_box = QComboBox()
        self.pencil_size_box.setMaxVisibleItems(25)
        self.pencil_size_box.setEditable(True)
        self.pencil_size_box.setFixedWidth(75)
        self.pencil_size_box.addItems(["1","2","3","4","5","6","7","8","9","10","12","14","16","20","24","28","32","40","48","64"])
        self.pencil_size_box.setCurrentText("1")
        self.pencil_size_box.setStyleSheet(self._get_combo_style())
        self.pencil_size_box.currentTextChanged.connect(self.on_pencil_size_changed)
        layout.addWidget(self.pencil_size_box)
        bp = QPushButton("+"); bp.setFixedSize(20, 20); bp.setStyleSheet(self._get_btn_style())
        bp.setAutoRepeat(True); bp.setAutoRepeatDelay(400); bp.setAutoRepeatInterval(40)
        layout.addWidget(bp)
        bm.clicked.connect(lambda: self.decrease_size(self.pencil_size_box))
        bp.clicked.connect(lambda: self.increase_size(self.pencil_size_box))

        layout.addSpacing(10)

        layout.addWidget(QLabel(t("opt.lbl.shape")))
        self.pencil_shape_combo = QComboBox()
        self.pencil_shape_combo.setFixedWidth(170)
        self.pencil_shape_combo.setStyleSheet(self._get_combo_style())
        self._populate_shape_combo(self.pencil_shape_combo)
        self.pencil_shape_combo.currentIndexChanged.connect(self.on_pencil_shape_changed)
        layout.addWidget(self.pencil_shape_combo)

        layout.addStretch()
        return widget

    def on_pencil_size_changed(self, text):
        if getattr(self, 'is_syncing', False): return
        t = text.strip()
        if not t.isdigit(): return
        val = int(t)
        if 1 <= val <= 64 and self.main_window:
            self.main_window.update_pencil_size(val)

    def on_pencil_shape_changed(self, index):
        if getattr(self, 'is_syncing', False): return
        if self.main_window:
            self.main_window.update_pencil_shape(self.pencil_shape_combo.itemData(index))

    def create_eyedropper_panel(self):
        """Panel del Cuentagotas: tamaño de muestra (punto / media 3x3 / 5x5) y
        fuente (todas las capas o solo la activa), más una guía breve."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(5, 0, 5, 0)
        layout.setSpacing(4)

        layout.addWidget(QLabel(t("opt.lbl.sample")))
        self.eyedropper_size_combo = QComboBox()
        self.eyedropper_size_combo.setFixedWidth(120)
        self.eyedropper_size_combo.setStyleSheet(self._get_combo_style())
        self.eyedropper_size_combo.addItem(t("opt.sample.point"), 1)
        self.eyedropper_size_combo.addItem(t("opt.sample.avg3"), 3)
        self.eyedropper_size_combo.addItem(t("opt.sample.avg5"), 5)
        self.eyedropper_size_combo.currentIndexChanged.connect(self.on_eyedropper_size_changed)
        layout.addWidget(self.eyedropper_size_combo)

        layout.addSpacing(10)
        layout.addWidget(QLabel(t("opt.lbl.source")))
        self.eyedropper_source_combo = QComboBox()
        self.eyedropper_source_combo.setFixedWidth(135)
        self.eyedropper_source_combo.setStyleSheet(self._get_combo_style())
        self.eyedropper_source_combo.addItem(t("opt.chk.all_layers"), "all")
        self.eyedropper_source_combo.addItem(t("opt.source.active"), "active")
        self.eyedropper_source_combo.currentIndexChanged.connect(self.on_eyedropper_source_changed)
        layout.addWidget(self.eyedropper_source_combo)

        layout.addStretch()
        return widget

    def on_eyedropper_size_changed(self, index):
        if self.main_window:
            self.main_window.update_eyedropper_sample_size(self.eyedropper_size_combo.currentData())

    def on_eyedropper_source_changed(self, index):
        if self.main_window:
            self.main_window.update_eyedropper_sample_all(
                self.eyedropper_source_combo.currentData() == "all")

    def on_size_changed(self, text):
        if not text.strip().isdigit(): return
        val = int(text)
        if 1 <= val <= 300:
            if self.main_window: self.main_window.update_brush_size(val)

    def on_hardness_slider_changed(self, value):
        self.hardness_value_label.setText(f"{value}%")
        if self.main_window:
            self.main_window.update_brush_hardness(value)

    def on_pattern_changed(self, index):
        if self.is_syncing: return
        pattern_id = self.pattern_combo.itemData(index)
        self.main_window.update_brush_pattern(pattern_id)
        # La opacidad del trazo solo actúa con relleno sólido (motor de
        # cobertura); con un patrón se deshabilita para no confundir.
        self._set_brush_opacity_enabled(self._pattern_data_is_solid(pattern_id))

    @staticmethod
    def _pattern_data_is_solid(data):
        # Mismo criterio que _pattern_is_solid en draw_tools (el combo guarda
        # Qt.BrushStyle.SolidPattern para el sólido, no la cadena 'solid')
        return data in (None, 'solid', Qt.BrushStyle.SolidPattern)

    def _set_brush_opacity_enabled(self, enabled):
        for w in ((self.brush_opacity_lbl, self.brush_opacity_slider,
                   self.brush_opacity_value_label)
                  + getattr(self, '_brush_opacity_btns', ())):
            w.setEnabled(bool(enabled))

    def on_brush_opacity_changed(self, value):
        self.brush_opacity_value_label.setText(f"{value}%")
        if self.main_window:
            self.main_window.update_brush_opacity(value)

    def on_brush_shape_changed(self, index):
        if getattr(self, 'is_syncing', False): return
        if self.main_window:
            self.main_window.update_brush_shape(self.brush_shape_combo.itemData(index))

    def on_spacing_slider_changed(self, value):
        """Actualiza el texto del porcentaje de espaciado y se lo comunica a MainWindow"""
        self.spacing_value_label.setText(f"{value}%")
        if self.main_window:
            self.main_window.update_brush_spacing(value)

    def on_eraser_hardness_changed(self, value):
        self.eraser_hardness_label.setText(f"{value}%")
        if self.main_window: self.main_window.update_eraser_hardness(value)

    def on_eraser_spacing_changed(self, value):
        self.eraser_spacing_label.setText(f"{value}%")
        if self.main_window: self.main_window.update_eraser_spacing(value)

    def on_eraser_shape_changed(self, index):
        if getattr(self, 'is_syncing', False): return
        if self.main_window:
            self.main_window.update_eraser_shape(self.eraser_shape_combo.itemData(index))

    def on_eraser_mode_changed(self, index):
        if getattr(self, "is_syncing", False): return
        data = self.eraser_mode_combo.itemData(index)
        is_color = (data == "color")
        is_bg = (data == "background")
        # La tolerancia se usa tanto en 'Borrador de color' como en 'de fondos'
        self._set_eraser_tolerance_enabled(is_color or is_bg)
        # Las opciones de muestra única y proteger primario son exclusivas de fondos
        self._set_eraser_bg_options_visible(is_bg)
        if self.main_window:
            self.main_window.update_eraser_color_mode(is_color)
            self.main_window.update_eraser_bg_mode(is_bg)

    def on_eraser_tolerance_changed(self, value):
        self.eraser_tolerance_label.setText(str(value))
        if self.main_window: self.main_window.update_eraser_color_tolerance(value)

    def on_replace_tolerance_changed(self, value):
        self.replace_tolerance_label.setText(str(value))
        if self.main_window: self.main_window.update_replace_color_tolerance(value)

    def on_replace_shape_changed(self, index):
        if self.main_window:
            self.main_window.update_replace_color_shape(self.replace_shape_combo.currentData())

    def on_replace_hardness_changed(self, value):
        self.replace_hardness_label.setText(str(value))
        if self.main_window:
            self.main_window.update_replace_color_hardness(value)

    def on_replace_contiguous_toggled(self, checked):
        if self.main_window:
            self.main_window.update_replace_color_contiguous(checked)

    def on_replace_sample_all_toggled(self, checked):
        if self.main_window:
            self.main_window.update_replace_color_sample_all(checked)

    def _set_eraser_tolerance_enabled(self, visible):
        # La tolerancia solo tiene sentido en "Borrador de color/fondos": se OCULTA
        # cuando el modo es el borrador normal.
        for _w in (self.eraser_tol_label_title, self.eraser_tol_btn_menos,
                   self.eraser_tolerance_slider, self.eraser_tol_btn_mas,
                   self.eraser_tolerance_label):
            _w.setVisible(visible)
        self._panel_clip.adjustInnerSize()


    def _set_eraser_bg_options_visible(self, visible):
        self.eraser_bg_one_shot_check.setVisible(visible)
        self.eraser_bg_protect_primary_check.setVisible(visible)
        self._panel_clip.adjustInnerSize()


    def on_eraser_bg_one_shot_toggled(self, checked):
        if self.main_window:
            self.main_window.update_eraser_bg_one_shot(checked)

    def on_eraser_bg_protect_primary_toggled(self, checked):
        if self.main_window:
            self.main_window.update_eraser_bg_protect_primary(checked)

    def create_replace_color_panel(self):
        """Panel de Sustituir color: Tamaño (compartido con el pincel) y
        Tolerancia propia. Pinta el color primario solo donde el color de la
        capa coincide con el de debajo (dentro de la tolerancia)."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(2, 0, 5, 0)
        layout.setSpacing(4)

        # --- Tamaño (compartido con el pincel) ---
        layout.addWidget(QLabel(t("opt.lbl.size")))
        btn_menos = QPushButton("-")
        btn_menos.setFixedSize(20, 20)
        btn_menos.setStyleSheet(self._get_btn_style())
        btn_menos.setAutoRepeat(True)
        btn_menos.setAutoRepeatDelay(400)
        btn_menos.setAutoRepeatInterval(40)
        layout.addWidget(btn_menos)

        self.replace_size_box = QComboBox()
        self.replace_size_box.setMaxVisibleItems(25)
        self.replace_size_box.setEditable(True)
        self.replace_size_box.setFixedWidth(75)
        self.replace_size_box.addItems(["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "12", "14", "16", "18", "20", "24", "28", "32", "40", "64", "128"])
        self.replace_size_box.setCurrentText("5")
        self.replace_size_box.setStyleSheet(self._get_combo_style())
        self.replace_size_box.currentTextChanged.connect(self.on_size_changed)
        layout.addWidget(self.replace_size_box)

        btn_mas = QPushButton("+")
        btn_mas.setFixedSize(20, 20)
        btn_mas.setStyleSheet(self._get_btn_style())
        btn_mas.setAutoRepeat(True)
        btn_mas.setAutoRepeatDelay(400)
        btn_mas.setAutoRepeatInterval(40)
        layout.addWidget(btn_mas)

        btn_menos.clicked.connect(lambda: self.decrease_size(self.replace_size_box))
        btn_mas.clicked.connect(lambda: self.increase_size(self.replace_size_box))

        layout.addSpacing(12)

        # --- Tolerancia (propia de esta herramienta) ---
        layout.addWidget(QLabel(t("opt.lbl.tolerance")))
        btn_menos_t = QPushButton("-")
        btn_menos_t.setFixedSize(20, 20)
        btn_menos_t.setStyleSheet(self._get_btn_style())
        btn_menos_t.setAutoRepeat(True)
        btn_menos_t.setAutoRepeatDelay(400)
        btn_menos_t.setAutoRepeatInterval(40)
        layout.addWidget(btn_menos_t)

        self.replace_tolerance_slider = QSlider(Qt.Orientation.Horizontal)
        self.replace_tolerance_slider.setRange(0, 255)
        self.replace_tolerance_slider.setValue(32)
        self.replace_tolerance_slider.setFixedWidth(90)
        self.replace_tolerance_slider.setStyleSheet(self._get_slider_style())
        self.replace_tolerance_slider.valueChanged.connect(self.on_replace_tolerance_changed)
        layout.addWidget(self.replace_tolerance_slider)

        btn_mas_t = QPushButton("+")
        btn_mas_t.setFixedSize(20, 20)
        btn_mas_t.setStyleSheet(self._get_btn_style())
        btn_mas_t.setAutoRepeat(True)
        btn_mas_t.setAutoRepeatDelay(400)
        btn_mas_t.setAutoRepeatInterval(40)
        layout.addWidget(btn_mas_t)

        self.replace_tolerance_label = QLabel("32")
        self.replace_tolerance_label.setFixedWidth(28)
        self.replace_tolerance_label.setStyleSheet(theme.value_label_qss())
        layout.addWidget(self.replace_tolerance_label)

        btn_menos_t.clicked.connect(lambda: self.replace_tolerance_slider.setValue(self.replace_tolerance_slider.value() - 1))
        btn_mas_t.clicked.connect(lambda: self.replace_tolerance_slider.setValue(self.replace_tolerance_slider.value() + 1))

        layout.addSpacing(12)

        # --- Forma de punta ---
        layout.addWidget(QLabel(t("opt.lbl.shape")))
        self.replace_shape_combo = QComboBox()
        self.replace_shape_combo.setFixedWidth(170)
        self.replace_shape_combo.setStyleSheet(self._get_combo_style())
        self._populate_shape_combo(self.replace_shape_combo)
        self.replace_shape_combo.currentIndexChanged.connect(self.on_replace_shape_changed)
        layout.addWidget(self.replace_shape_combo)

        layout.addSpacing(12)

        # --- Dureza ---
        layout.addWidget(QLabel(t("opt.lbl.hardness")))
        rh_menos = QPushButton("-")
        rh_menos.setFixedSize(20, 20)
        rh_menos.setStyleSheet(self._get_btn_style())
        rh_menos.setAutoRepeat(True); rh_menos.setAutoRepeatDelay(400); rh_menos.setAutoRepeatInterval(40)
        layout.addWidget(rh_menos)
        self.replace_hardness_slider = QSlider(Qt.Orientation.Horizontal)
        self.replace_hardness_slider.setRange(0, 100)
        self.replace_hardness_slider.setValue(100)
        self.replace_hardness_slider.setFixedWidth(90)
        self.replace_hardness_slider.setStyleSheet(self._get_slider_style())
        self.replace_hardness_slider.valueChanged.connect(self.on_replace_hardness_changed)
        layout.addWidget(self.replace_hardness_slider)
        rh_mas = QPushButton("+")
        rh_mas.setFixedSize(20, 20)
        rh_mas.setStyleSheet(self._get_btn_style())
        rh_mas.setAutoRepeat(True); rh_mas.setAutoRepeatDelay(400); rh_mas.setAutoRepeatInterval(40)
        layout.addWidget(rh_mas)
        self.replace_hardness_label = QLabel("100")
        self.replace_hardness_label.setFixedWidth(28)
        self.replace_hardness_label.setStyleSheet(theme.value_label_qss())
        layout.addWidget(self.replace_hardness_label)
        rh_menos.clicked.connect(lambda: self.replace_hardness_slider.setValue(self.replace_hardness_slider.value() - 1))
        rh_mas.clicked.connect(lambda: self.replace_hardness_slider.setValue(self.replace_hardness_slider.value() + 1))

        layout.addSpacing(12)

        # --- Contigua / Todas las capas ---
        self.replace_contiguous_check = QCheckBox(t("opt.chk.contiguous"))
        self.replace_contiguous_check.setChecked(False)
        self.replace_contiguous_check.setStyleSheet(self._get_check_style())
        self.replace_contiguous_check.setToolTip(t("opt.tip.contig_replace"))
        self.replace_contiguous_check.toggled.connect(self.on_replace_contiguous_toggled)
        layout.addWidget(self.replace_contiguous_check)

        layout.addSpacing(12)
        self.replace_sample_all_check = QCheckBox(t("opt.chk.all_layers"))
        self.replace_sample_all_check.setChecked(False)
        self.replace_sample_all_check.setStyleSheet(self._get_check_style())
        self.replace_sample_all_check.setToolTip(t("opt.tip.sample_replace"))
        self.replace_sample_all_check.toggled.connect(self.on_replace_sample_all_toggled)
        layout.addWidget(self.replace_sample_all_check)

        layout.addStretch()
        return widget

