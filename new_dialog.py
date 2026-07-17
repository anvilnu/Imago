from i18n import t
# new_dialog.py
from PySide6.QtWidgets import (QLabel, QSpinBox, QDoubleSpinBox, QCheckBox, QPushButton,
                             QHBoxLayout, QGridLayout, QButtonGroup, QComboBox,
                             QSlider, QWidget, QSizePolicy, QListWidget,
                             QListWidgetItem, QAbstractItemView)
from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QIcon
from widgets.custom_titlebar import FramelessDialog
from widgets.overlay_panel import OverlayPanel
import theme

# Resolución por defecto (PPP) y conversiones píxeles <-> unidades físicas.
DEFAULT_DPI = 96
_CM_PER_INCH = 2.54


def _px_to_unit(px, unit, dpi):
    if unit == "cm":
        return px / dpi * _CM_PER_INCH
    if unit == "in":
        return px / dpi
    return px


def _unit_to_px(val, unit, dpi):
    if unit == "cm":
        return val / _CM_PER_INCH * dpi
    if unit == "in":
        return val * dpi
    return val


class ImageSizeDialog(FramelessDialog):
    """Diálogo de tamaño de imagen, COMPARTIDO por 'Nuevo' y 'Cambiar tamaño'.
    Dos apartados enlazados: 'Tamaño' (píxeles) y 'Tamaño de impresión'
    (PPP + medida física en cm o pulgadas). La casilla 'Remuestrear' decide qué
    pasa al cambiar la PPP o la medida física: activada, se recalculan los píxeles
    (la imagen se re-muestrea); desactivada, los píxeles quedan fijos y solo cambia
    el tamaño de impresión. get_values() -> (ancho, alto) en píxeles; get_dpi() -> PPP."""

    # Recordatorio SOLO de sesión (atributos de CLASE, no QSettings) del estado
    # de las casillas 'Mantener la relación de aspecto' y 'Tamaño del
    # portapapeles': ambas arrancan desactivadas y conservan la última elección
    # del usuario hasta cerrar Imago.
    _session_keep_aspect = False
    _session_clipboard = False

    def __init__(self, parent=None, width=800, height=600, dpi=DEFAULT_DPI,
                 title=t("dlg.new", default="Nuevo"), show_fill=False):
        super().__init__(parent)
        self.setWindowTitle(title)
        # 'Nuevo' añade un desplegable de color de fondo (show_fill=True); 'Cambiar
        # tamaño' reutiliza el mismo diálogo sin él. La fila extra sube el alto, con
        # holgura para que la fila de botones respire (no quede pegada al fondo).
        # (+26 px por la casilla 'Tamaño del portapapeles'.)
        self._body.setFixedSize(380, 490 if show_fill else 426)
        self.setStyleSheet(
            "QDialog { background-color: %s; } QLabel { color: %s; }" % (theme.BG_WINDOW, theme.TEXT)
            + theme.spinbox_dialog_qss() + theme.combobox_dialog_qss() + theme.checkbox_qss()
            + theme.dialog_button_plain_qss()
        )

        # Estado CANÓNICO (píxeles + PPP); los campos se derivan siempre de aquí.
        self._px_w = float(max(1, int(width)))
        self._px_h = float(max(1, int(height)))
        self._dpi = float(dpi) if dpi else float(DEFAULT_DPI)
        self._aspect = self._px_w / self._px_h
        self._updating = False

        layout = self.body_layout

        # Ancho común para la columna de etiquetas de TODAS las rejillas (píxeles,
        # impresión y fondo): así los campos (spinbox/combo) arrancan a la misma
        # x y tienen el mismo ancho. Se calcula desde la etiqueta más larga.
        from PySide6.QtGui import QFontMetrics
        _fm = QFontMetrics(self.font())
        _lbls = [t("dlg.width"), t("dlg.height"), t("dlg.res_dpi"), t("dlg.unit")]
        if show_fill:
            _lbls.append(t("dlg.bg_fill"))
        self._label_col_w = max(_fm.horizontalAdvance(s) for s in _lbls) + 6

        # Ancho FIJO de los campos (spinbox/combo): TODOS miden igual, sea cual sea
        # su contenido. NO se fija por widget (setFixedWidth/MaximumWidth): el QSS de
        # los spinbox trae su propio min-width y pisa ese mínimo, dejándolos a ancho
        # "según contenido" (distinto en cada uno). En su lugar se controla desde la
        # COLUMNA del campo (columna 2 de las rejillas), que el QSS no toca: cada
        # campo llena esa columna. El valor se ajusta al contenido más largo
        # (+ flechas y márgenes); sube/baja el sumando para ensanchar/estrechar
        # TODOS los campos a la vez.
        _flds = ["10000 px", t("dlg.fill_palette"), t("dlg.unit_cm"), t("dlg.unit_in")]
        self._field_w = max(_fm.horizontalAdvance(s) for s in _flds) + 100

        def _config_grid(g):
            """Rejilla de 3 columnas común a los tres apartados: etiqueta (ancho
            fijo, alineadas) · hueco elástico · campo (ancho fijo _field_w, pegado
            a la derecha). Así todos los campos miden y se alinean igual."""
            g.setVerticalSpacing(8)
            g.setColumnMinimumWidth(0, self._label_col_w)
            g.setColumnStretch(1, 1)
            g.setColumnMinimumWidth(2, self._field_w)
        self._config_grid = _config_grid

        # Relación de aspecto (arriba del todo). Desactivada por defecto;
        # recuerda la última elección del usuario durante la sesión.
        self.keep_aspect_check = QCheckBox(t("dlg.keep_aspect"))
        self.keep_aspect_check.setChecked(ImageSizeDialog._session_keep_aspect)
        layout.addWidget(self.keep_aspect_check)

        # Tamaño del portapapeles: al marcarla se vuelcan las dimensiones de la
        # imagen copiada en los campos (los campos siguen editables). Si no hay
        # imagen en el portapapeles, la casilla queda deshabilitada. Recordada
        # solo durante la sesión (si estaba marcada, al abrir se aplica ya).
        self.clipboard_check = QCheckBox(t("dlg.clipboard_size",
                                           default="Tamaño del portapapeles"))
        self._clipboard_size = self._read_clipboard_size()
        if self._clipboard_size is None:
            self.clipboard_check.setEnabled(False)
            self.clipboard_check.setToolTip(t("dlg.clipboard_none",
                default="No hay ninguna imagen en el portapapeles"))
        else:
            self.clipboard_check.setChecked(ImageSizeDialog._session_clipboard)
            if ImageSizeDialog._session_clipboard:
                self._apply_clipboard_size()
        layout.addWidget(self.clipboard_check)

        layout.addSpacing(6)

        # --- Apartado: Tamaño en píxeles ---
        layout.addLayout(self._section_header(t("dlg.size_px")))
        g1 = QGridLayout()
        self._config_grid(g1)
        g1.addWidget(QLabel(t("dlg.width")), 0, 0)
        self.px_w_spin = QSpinBox()
        self.px_w_spin.setRange(1, 10000)
        self.px_w_spin.setSuffix(" px")
        g1.addWidget(self.px_w_spin, 0, 2)
        g1.addWidget(QLabel(t("dlg.height")), 1, 0)
        self.px_h_spin = QSpinBox()
        self.px_h_spin.setRange(1, 10000)
        self.px_h_spin.setSuffix(" px")
        g1.addWidget(self.px_h_spin, 1, 2)
        layout.addLayout(g1)

        layout.addSpacing(6)

        # --- Apartado: Tamaño de impresión (PPP + medida física) ---
        layout.addLayout(self._section_header(t("dlg.print_size")))
        g2 = QGridLayout()
        self._config_grid(g2)
        g2.addWidget(QLabel(t("dlg.res_dpi")), 0, 0)
        self.dpi_spin = QSpinBox()
        self.dpi_spin.setRange(1, 1000)
        g2.addWidget(self.dpi_spin, 0, 2)

        g2.addWidget(QLabel(t("dlg.unit")), 1, 0)
        self.unit_combo = QComboBox()
        self.unit_combo.addItem(t("dlg.unit_cm"), "cm")
        self.unit_combo.addItem(t("dlg.unit_in"), "in")
        g2.addWidget(self.unit_combo, 1, 2)

        g2.addWidget(QLabel(t("dlg.width")), 2, 0)
        self.print_w_spin = QDoubleSpinBox()
        self.print_w_spin.setDecimals(2)
        self.print_w_spin.setRange(0.01, 10000.0)
        self.print_w_spin.setSingleStep(0.1)
        g2.addWidget(self.print_w_spin, 2, 2)

        g2.addWidget(QLabel(t("dlg.height")), 3, 0)
        self.print_h_spin = QDoubleSpinBox()
        self.print_h_spin.setDecimals(2)
        self.print_h_spin.setRange(0.01, 10000.0)
        self.print_h_spin.setSingleStep(0.1)
        g2.addWidget(self.print_h_spin, 3, 2)
        layout.addLayout(g2)

        self.resample_check = QCheckBox(t("dlg.resample"))
        self.resample_check.setChecked(True)
        layout.addWidget(self.resample_check)

        # Color de fondo del lienzo nuevo (solo en 'Nuevo'). El lienzo se rellena
        # con la opción elegida al crearlo; por defecto Blanco (comportamiento
        # histórico). None cuando el diálogo se usa para 'Cambiar tamaño'.
        self.fill_combo = None
        if show_fill:
            g3 = QGridLayout()
            self._config_grid(g3)
            g3.addWidget(QLabel(t("dlg.bg_fill")), 0, 0)
            self.fill_combo = QComboBox()
            for _label, _fid in ((t("dlg.fill_white"), "white"),
                                 (t("dlg.fill_black"), "black"),
                                 (t("dlg.fill_trans"), "transparent"),
                                 (t("dlg.fill_palette"), "primary")):
                self.fill_combo.addItem(_label, _fid)
            g3.addWidget(self.fill_combo, 0, 2)
            layout.addSpacing(6)
            layout.addLayout(g3)

        # Absorbe el espacio sobrante para que las filas de los grids no se
        # separen de más y los botones queden pegados abajo.
        layout.addStretch(1)

        # Tamaño de la imagen + botones en la misma línea
        self.size_label = QLabel("")
        self.size_label.setStyleSheet(f"color: {theme.TEXT_DIM}; font-style: italic;")

        btn_layout = QHBoxLayout()
        self.btn_ok = QPushButton(t("dlg.ok"))
        self.btn_cancel = QPushButton(t("dlg.cancel"))
        btn_layout.addWidget(self.size_label)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_ok)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

        self._recalc_display()

        self.px_w_spin.valueChanged.connect(self.on_px_w)
        self.px_h_spin.valueChanged.connect(self.on_px_h)
        self.dpi_spin.valueChanged.connect(self.on_dpi)
        self.print_w_spin.valueChanged.connect(self.on_print_w)
        self.print_h_spin.valueChanged.connect(self.on_print_h)
        self.unit_combo.currentIndexChanged.connect(lambda _i: self._recalc_display())
        self.resample_check.toggled.connect(self.on_resample)
        self.keep_aspect_check.toggled.connect(self.on_keep_aspect)
        self.clipboard_check.toggled.connect(self.on_clipboard_size)
        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)

    def _section_header(self, text):
        """Cabecera de apartado: el título en negrita y, a su derecha, una línea
        fina que llega hasta el borde, para separar bien los dos apartados."""
        row = QHBoxLayout()
        lbl = QLabel(text)
        lbl.setStyleSheet("color: %s; font-weight: bold;" % theme.TEXT)
        row.addWidget(lbl)
        line = QWidget()
        line.setFixedHeight(1)
        line.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        line.setStyleSheet("background-color: %s;" % theme.BORDER)
        row.addWidget(line)
        return row

    def _recalc_display(self):
        """Refresca TODOS los campos desde el estado canónico (px + PPP)."""
        self._updating = True
        unit = self.unit_combo.currentData()
        self.px_w_spin.setValue(int(round(self._px_w)))
        self.px_h_spin.setValue(int(round(self._px_h)))
        self.dpi_spin.setValue(int(round(self._dpi)))
        suf = " cm" if unit == "cm" else " in"
        self.print_w_spin.setSuffix(suf)
        self.print_h_spin.setSuffix(suf)
        self.print_w_spin.setValue(_px_to_unit(self._px_w, unit, self._dpi))
        self.print_h_spin.setValue(_px_to_unit(self._px_h, unit, self._dpi))
        w, h = int(round(self._px_w)), int(round(self._px_h))
        mb = (w * h * 4) / (1024 * 1024)  # 4 bytes/píxel (RGBA) -> MB aprox.
        self.size_label.setText(f"{t('dlg.img_size')} {mb:.2f} MB")
        self._updating = False

    # ---- handlers (actualizan el estado canónico y refrescan) ----
    def on_px_w(self, v):
        if self._updating: return
        self._px_w = float(v)
        if self.keep_aspect_check.isChecked():
            self._px_h = self._px_w / self._aspect
        self._recalc_display()

    def on_px_h(self, v):
        if self._updating: return
        self._px_h = float(v)
        if self.keep_aspect_check.isChecked():
            self._px_w = self._px_h * self._aspect
        self._recalc_display()

    def on_print_w(self, v):
        if self._updating: return
        unit = self.unit_combo.currentData()
        if self.resample_check.isChecked():
            self._px_w = _unit_to_px(v, unit, self._dpi)
            if self.keep_aspect_check.isChecked():
                self._px_h = self._px_w / self._aspect
        else:
            inch = v / _CM_PER_INCH if unit == "cm" else v
            if inch > 0:
                self._dpi = self._px_w / inch
        self._recalc_display()

    def on_print_h(self, v):
        if self._updating: return
        unit = self.unit_combo.currentData()
        if self.resample_check.isChecked():
            self._px_h = _unit_to_px(v, unit, self._dpi)
            if self.keep_aspect_check.isChecked():
                self._px_w = self._px_h * self._aspect
        else:
            inch = v / _CM_PER_INCH if unit == "cm" else v
            if inch > 0:
                self._dpi = self._px_h / inch
        self._recalc_display()

    def on_dpi(self, v):
        if self._updating: return
        v = float(v)
        if self.resample_check.isChecked():
            # Mantener el tamaño de impresión: los píxeles se escalan con la PPP.
            if self._dpi > 0:
                factor = v / self._dpi
                self._px_w *= factor
                self._px_h *= factor
            self._dpi = v
        else:
            # Píxeles fijos: solo cambia el tamaño físico (se recalcula al mostrar).
            self._dpi = v
        self._recalc_display()

    def on_resample(self, checked):
        # Sin remuestreo, el número de píxeles queda bloqueado.
        self.px_w_spin.setEnabled(checked)
        self.px_h_spin.setEnabled(checked)

    def on_keep_aspect(self, checked):
        ImageSizeDialog._session_keep_aspect = bool(checked)
        if checked and self._px_h > 0:
            self._aspect = self._px_w / self._px_h

    def on_clipboard_size(self, checked):
        ImageSizeDialog._session_clipboard = bool(checked)
        if checked:
            self._apply_clipboard_size()
            self._recalc_display()

    @staticmethod
    def _read_clipboard_size():
        """(ancho, alto) de la imagen del portapapeles, o None si no hay."""
        from PySide6.QtWidgets import QApplication
        img = QApplication.clipboard().image()
        if img is None or img.isNull():
            return None
        return img.width(), img.height()

    def _apply_clipboard_size(self):
        """Vuelca el tamaño del portapapeles al estado canónico (y a la relación
        de aspecto, para que 'mantener' parta del tamaño nuevo)."""
        if self._clipboard_size is None:
            return
        w, h = self._clipboard_size
        self._px_w = float(max(1, w))
        self._px_h = float(max(1, h))
        self._aspect = self._px_w / self._px_h

    def get_values(self):
        """Ancho y alto finales en píxeles (acotados a 1..10000)."""
        return (max(1, min(10000, int(round(self._px_w)))),
                max(1, min(10000, int(round(self._px_h)))))

    def get_dpi(self):
        """Resolución (PPP) elegida."""
        return max(1, int(round(self._dpi)))

    def get_fill(self):
        """Color de fondo elegido para el lienzo nuevo: 'white', 'black',
        'transparent' o 'primary' (color de la paleta). None si el diálogo se
        abrió sin el desplegable (p. ej. 'Cambiar tamaño')."""
        if self.fill_combo is None:
            return None
        return self.fill_combo.currentData()

class CanvasSizeDialog(FramelessDialog):
    """Imagen -> Tamano del lienzo: cambia el lienzo SIN escalar el contenido.
    El usuario elige el nuevo tamano y el ANCLAJE (donde queda el contenido
    actual) en una rejilla 3x3. get_values() -> (w, h, anchor_x, anchor_y)
    con anchor en {0.0, 0.5, 1.0}."""

    def __init__(self, current_width, current_height, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("dlg.canvas_size", default="Tamano del lienzo"))
        self._body.setFixedSize(340, 384)
        self.setStyleSheet(
            "QDialog { background-color: %s; } QLabel { color: %s; }" % (theme.BG_WINDOW, theme.TEXT)
            + theme.spinbox_dialog_qss() + theme.combobox_dialog_qss() + theme.dialog_button_plain_qss()
            + """
            QPushButton[anchor="true"] {
                background-color: %s; border: 1px solid %s;
                border-radius: 2px; padding: 0px;
            }
            QPushButton[anchor="true"]:hover { border: 1px solid %s; }
            QPushButton[anchor="true"]:checked {
                background-color: %s; border: 1px solid %s;
            }
            """ % (theme.BG_BUTTON, theme.BORDER, theme.ACCENT, theme.BG_PRESSED, theme.ACCENT)
        )

        layout = self.body_layout

        grid = QGridLayout()
        grid.addWidget(QLabel(t("dlg.width_px")), 0, 0)
        self.width_spin = QSpinBox()
        self.width_spin.setRange(1, 10000)
        self.width_spin.setValue(current_width)
        grid.addWidget(self.width_spin, 0, 1)

        grid.addWidget(QLabel(t("dlg.height_px")), 1, 0)
        self.height_spin = QSpinBox()
        self.height_spin.setRange(1, 10000)
        self.height_spin.setValue(current_height)
        grid.addWidget(self.height_spin, 1, 1)
        layout.addLayout(grid)

        layout.addSpacing(4)
        layout.addWidget(QLabel(t("dlg.anchor")))

        anchor_grid = QGridLayout()
        anchor_grid.setSpacing(3)
        self.anchor_group = QButtonGroup(self)
        self.anchor_group.setExclusive(True)
        self._anchors = {}
        for row in range(3):
            for col in range(3):
                b = QPushButton()
                b.setCheckable(True)
                b.setFixedSize(34, 34)
                b.setIconSize(QSize(18, 18))
                b.setProperty("anchor", "true")
                self.anchor_group.addButton(b)
                anchor_grid.addWidget(b, row, col)
                self._anchors[(col, row)] = b
        self._anchors[(0, 0)].setChecked(True)  # superior-izquierda por defecto
        self.anchor_group.buttonClicked.connect(lambda _b: self._update_arrows())

        wrap = QHBoxLayout()
        wrap.addStretch()
        wrap.addLayout(anchor_grid)
        wrap.addStretch()
        layout.addLayout(wrap)

        layout.addSpacing(6)
        fill_row = QHBoxLayout()
        fill_lbl = QLabel(t("dlg.fill"))
        fill_lbl.setMinimumWidth(70)
        fill_row.addWidget(fill_lbl)
        self.fill_combo = QComboBox()
        for _label, _fid in ((t("dlg.fill_trans"), "transparent"),
                             (t("dlg.fill_prim"), "primary"),
                             (t("dlg.fill_sec"), "secondary"),
                             (t("dlg.fill_white"), "white"),
                             (t("dlg.fill_black"), "black")):
            self.fill_combo.addItem(_label, _fid)
        fill_row.addWidget(self.fill_combo, 1)
        layout.addLayout(fill_row)

        self.size_label = QLabel("")
        self.size_label.setStyleSheet(f"color: {theme.TEXT_DIM}; font-style: italic;")
        layout.addWidget(self.size_label)

        btn_layout = QHBoxLayout()
        self.btn_ok = QPushButton(t("dlg.ok"))
        self.btn_cancel = QPushButton(t("dlg.cancel"))
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_ok)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)
        self.width_spin.valueChanged.connect(self.update_file_size)
        self.height_spin.valueChanged.connect(self.update_file_size)
        self.update_file_size()
        self._update_arrows()

    def update_file_size(self):
        w, h = self.width_spin.value(), self.height_spin.value()
        mb = (w * h * 4) / (1024 * 1024)
        self.size_label.setText(f"{t('dlg.mem_size')} {mb:.2f} MB")

    _ARROWS = {(0, -1): "arrow_n", (1, -1): "arrow_ne", (1, 0): "arrow_e",
               (1, 1): "arrow_se", (0, 1): "arrow_s", (-1, 1): "arrow_sw",
               (-1, 0): "arrow_w", (-1, -1): "arrow_nw"}

    def _current_anchor(self):
        for (c, r), b in self._anchors.items():
            if b.isChecked():
                return c, r
        return 0, 0

    def _update_arrows(self):
        """Muestra una flecha (hacia afuera) en cada celda adyacente al
        ancla, indicando hacia donde se expande el lienzo."""
        ac, ar = self._current_anchor()
        for (c, r), b in self._anchors.items():
            dc, dr = c - ac, r - ar
            if (dc, dr) != (0, 0) and max(abs(dc), abs(dr)) == 1:
                b.setIcon(theme.icono(f":/icons/{self._ARROWS[(dc, dr)]}.png"))
            else:
                b.setIcon(QIcon())

    def get_values(self):
        col, row = self._current_anchor()
        amap = {0: 0.0, 1: 0.5, 2: 1.0}
        return (self.width_spin.value(), self.height_spin.value(),
                amap[col], amap[row], self.fill_combo.currentData())


class QualityDialog(FramelessDialog):
    """Opciones de guardado para formatos con calidad/compresion. Muestra el
    tamano aproximado del archivo en vivo y opciones propias de cada formato:
      - JPEG: calidad + 'optimizar' + 'progresivo'
      - WebP: calidad
      - PNG : compresion + profundidad de color (32 bits / 8 bits paleta)
    value() -> calidad/compresion (int);  options() -> dict con los extras."""

    def __init__(self, ext, image, default, parent=None):
        super().__init__(parent)
        self.ext = ext.lower()
        self.image = image
        self.setWindowTitle(f"{t('dlg.save_title', default='Guardar')} {self.ext.upper()}")
        self.setMinimumWidth(410)
        self.setStyleSheet(
            "QDialog { background-color: %s; } QLabel { color: %s; }" % (theme.BG_WINDOW, theme.TEXT)
            + theme.spinbox_dialog_qss() + theme.combobox_dialog_qss() + theme.checkbox_qss()
            + theme.slider_qss() + theme.dialog_button_plain_qss()
        )

        is_png = (self.ext == "png")
        cap = t("dlg.compression") if is_png else t("dlg.quality")
        lo = 0 if is_png else 1
        hint = (t("dlg.hint_comp")
                if is_png else
                t("dlg.hint_qual"))

        root = self.body_layout
        info = QLabel(hint)
        info.setWordWrap(True)
        info.setStyleSheet(f"color:{theme.TEXT_DIM}; font-style:italic;")
        root.addWidget(info)

        # Control principal: slider + spin
        row = QHBoxLayout()
        lbl = QLabel(cap)
        lbl.setMinimumWidth(110)
        row.addWidget(lbl)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(lo, 100)
        self.slider.setValue(default)
        self.slider.setMinimumWidth(170)
        row.addWidget(self.slider)
        self.spin = QSpinBox()
        self.spin.setRange(lo, 100)
        self.spin.setValue(default)
        self.slider.valueChanged.connect(self.spin.setValue)
        self.spin.valueChanged.connect(self.slider.setValue)
        row.addWidget(self.spin)
        root.addLayout(row)

        # Opciones especificas del formato
        self.depth_combo = None
        self.chk_optimize = None
        self.chk_progressive = None
        self.colors_combo = None
        self.chk_dither = None
        if is_png:
            drow = QHBoxLayout()
            dlbl = QLabel(t("dlg.depth"))
            dlbl.setMinimumWidth(110)
            drow.addWidget(dlbl)
            self.depth_combo = QComboBox()
            self.depth_combo.addItem(t("dlg.depth32"), 32)
            self.depth_combo.addItem(t("dlg.depth8"), 8)
            drow.addWidget(self.depth_combo, 1)
            root.addLayout(drow)
            # PNG de 8 bits (paleta): nº de colores y difuminado. La paleta la
            # cuantiza Pillow (png8_bytes en utilidades.py); para pixel-art con
            # pocos colores el resultado es exacto y el archivo, mínimo.
            crow = QHBoxLayout()
            self.colors_label = QLabel(t("dlg.colors"))
            self.colors_label.setMinimumWidth(110)
            crow.addWidget(self.colors_label)
            self.colors_combo = QComboBox()
            for n in (256, 128, 64, 32, 16):
                self.colors_combo.addItem(str(n), n)
            crow.addWidget(self.colors_combo, 1)
            root.addLayout(crow)
            self.chk_dither = QCheckBox(t("dlg.dither"))
            root.addWidget(self.chk_dither)
            self.depth_combo.currentIndexChanged.connect(self._sync_png8)
            self._sync_png8()
        elif self.ext in ("jpg", "jpeg"):
            self.chk_optimize = QCheckBox(t("dlg.optimize"))
            self.chk_optimize.setChecked(True)
            root.addWidget(self.chk_optimize)
            self.chk_progressive = QCheckBox(t("dlg.progressive"))
            root.addWidget(self.chk_progressive)

        # Tamano aproximado del archivo
        self.size_label = QLabel(t("dlg.size_calc"))
        self.size_label.setStyleSheet(f"color:{theme.INFO_BLUE};")
        root.addWidget(self.size_label)

        root.addSpacing(4)
        btns = QHBoxLayout()
        btns.addStretch()
        ok_btn = QPushButton(t("dlg.save"))
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton(t("dlg.cancel"))
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(ok_btn)
        btns.addWidget(cancel_btn)
        root.addLayout(btns)

        # Recalculo del tamano con pequeno retardo (no saturar al arrastrar)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._estimate_size)
        self.slider.valueChanged.connect(lambda _=None: self._timer.start())
        if self.depth_combo is not None:
            self.depth_combo.currentIndexChanged.connect(lambda _=None: self._timer.start())
        if self.colors_combo is not None:
            self.colors_combo.currentIndexChanged.connect(lambda _=None: self._timer.start())
        if self.chk_dither is not None:
            self.chk_dither.toggled.connect(lambda _=None: self._timer.start())
        if self.chk_optimize is not None:
            self.chk_optimize.toggled.connect(lambda _=None: self._timer.start())
        if self.chk_progressive is not None:
            self.chk_progressive.toggled.connect(lambda _=None: self._timer.start())
        QTimer.singleShot(0, self._estimate_size)

    def _sync_png8(self, _=None):
        """Colores y difuminado solo aplican al PNG de 8 bits (paleta)."""
        indexado = (self.depth_combo.currentData() == 8)
        self.colors_label.setVisible(indexado)
        self.colors_combo.setVisible(indexado)
        self.chk_dither.setVisible(indexado)
        self.adjustSize()

    def value(self):
        return self.slider.value()

    def options(self):
        opts = {}
        if self.depth_combo is not None:
            opts["indexed8"] = (self.depth_combo.currentData() == 8)
        if self.colors_combo is not None:
            opts["colors"] = self.colors_combo.currentData()
            opts["dither"] = self.chk_dither.isChecked()
        if self.chk_optimize is not None:
            opts["optimized"] = self.chk_optimize.isChecked()
        if self.chk_progressive is not None:
            opts["progressive"] = self.chk_progressive.isChecked()
        return opts

    def _fmt_bytes(self, n):
        if n >= 1024 * 1024:
            return f"{n / (1024 * 1024):.2f} MB"
        if n >= 1024:
            return f"{n / 1024:.1f} KB"
        return f"{n} bytes"

    def _estimate_size(self):
        if self.image is None or self.image.isNull():
            self.size_label.setText(t("dlg.size_na"))
            return
        try:
            from PySide6.QtCore import QBuffer, QByteArray, QIODevice
            from PySide6.QtGui import QImageWriter, QImage
            img = self.image
            opts = self.options()
            if opts.get("indexed8"):
                # La misma vía que usará el guardado (png8_bytes): el tamaño
                # estimado es el real. Si Pillow faltara, cae al Indexed8 de Qt.
                from utilidades import png8_bytes
                nivel = round(max(0, self.value()) * 9 / 100)
                datos = png8_bytes(img, opts.get("colors", 256),
                                   opts.get("dither", False), nivel)
                if datos:
                    self.size_label.setText(
                        t("dlg.size_approx") + " " + self._fmt_bytes(len(datos)))
                    return
                img = img.convertToFormat(QImage.Format_Indexed8)
            ba = QByteArray()
            buf = QBuffer(ba)
            buf.open(QIODevice.WriteOnly)
            writer = QImageWriter(buf, bytes(self.ext, "ascii"))
            if self.value() >= 0:
                writer.setQuality(self.value())
            if opts.get("optimized") and hasattr(writer, "setOptimizedWrite"):
                writer.setOptimizedWrite(True)
            if opts.get("progressive") and hasattr(writer, "setProgressiveScanWrite"):
                writer.setProgressiveScanWrite(True)
            ok = writer.write(img)
            buf.close()
            if ok and ba.size() > 0:
                self.size_label.setText(t("dlg.size_approx") + " " + self._fmt_bytes(ba.size()))
            else:
                self.size_label.setText(t("dlg.size_na"))
        except Exception:
            self.size_label.setText(t("dlg.size_na"))


class SelectionRefineDialog(OverlayPanel):
    """Panel OVERLAY para refinar la selección (Expandir / Contraer / Suavizar /
    Calar / Borde): un control de radio en píxeles y, opcionalmente, la dirección.

    Igual que los paneles de Efectos, es un HIJO del lienzo (no una ventana del
    SO ni un diálogo modal): así NO se sale del área del lienzo y RECUERDA su
    última posición (QSettings, vía OverlayPanel). No bloquea ni devuelve: aplica
    la operación al Aceptar llamando al callback `on_apply(valor, dirección)`
    (misma filosofía que los overlays de Ajustes/Efectos)."""

    def __init__(self, parent=None, title=t("dlg.expand", default="Expandir selección"),
                 label=t("dlg.amount", default="Cantidad:"), default=4, maximum=200,
                 minimum=1, show_direction=False, on_apply=None):
        super().__init__(parent)
        self.setWindowTitle(title)

        self.show_direction = show_direction
        self._on_apply = on_apply

        # El fondo/borde sale del marco temado del OverlayPanel; aquí solo se
        # estilan las etiquetas y los controles (mismas funciones de theme que
        # el resto de diálogos, para no acoplar new_dialog con adjustments).
        self.setStyleSheet(
            "QLabel { color: %s; }" % theme.TEXT
            + theme.slider_qss() + theme.spinbox_dialog_qss()
            + theme.dialog_button_plain_qss() + theme.combobox_dialog_qss()
        )
        self.setMinimumWidth(320)

        layout = self.body_layout
        row = QHBoxLayout()
        lbl = QLabel(label)
        lbl.setMinimumWidth(80)
        row.addWidget(lbl)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(minimum, maximum)
        self.slider.setValue(default)
        self.slider.setMinimumWidth(150)
        self.spin = QSpinBox()
        self.spin.setRange(minimum, maximum)
        self.spin.setValue(default)
        self.spin.setSuffix(" px")
        self.slider.valueChanged.connect(self.spin.setValue)
        self.spin.valueChanged.connect(self.slider.setValue)
        row.addWidget(self.slider)
        row.addWidget(self.spin)
        layout.addLayout(row)

        if self.show_direction:
            dir_row = QHBoxLayout()
            dir_lbl = QLabel(t("dlg.direction"))
            dir_lbl.setMinimumWidth(80)
            dir_row.addWidget(dir_lbl)
            self.direction_combo = QComboBox()
            # Acota el ancho del combo (sus etiquetas son largas): sin esto el
            # panel se ensancharía a ~540 px para caber "Horizontal (Izquierda y
            # Derecha)". Se elide el texto y el panel mantiene un ancho compacto.
            self.direction_combo.setSizeAdjustPolicy(
                QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            self.direction_combo.setMinimumContentsLength(14)
            # Etiqueta traducida + valor interno ESTABLE en itemData: canvas.py
            # compara la dirección contra estos valores en español.
            for _label, _val in ((t("dlg.dir_full"), "Completo"),
                                 (t("dlg.dir_h"), "Horizontal (Izquierda y Derecha)"),
                                 (t("dlg.dir_v"), "Vertical (Arriba y Abajo)"),
                                 (t("dlg.dir_up"), "Solo Arriba"),
                                 (t("dlg.dir_down"), "Solo Abajo"),
                                 (t("dlg.dir_left"), "Solo Izquierda"),
                                 (t("dlg.dir_right"), "Solo Derecha")):
                self.direction_combo.addItem(_label, _val)
            dir_row.addWidget(self.direction_combo)
            layout.addLayout(dir_row)

        layout.addSpacing(14)

        btns = QHBoxLayout()
        btns.addStretch()
        ok_btn = QPushButton(t("dlg.ok"))
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton(t("dlg.cancel"))
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(ok_btn)
        btns.addWidget(cancel_btn)
        layout.addLayout(btns)

    def get_value(self):
        return self.spin.value()

    def get_direction(self):
        if self.show_direction:
            return self.direction_combo.currentData()
        return "Completo"

    def accept(self):
        """Aplica la operación UNA sola vez (callback) y cierra el panel. El guard
        de _is_closed evita reejecutar el callback si accept() llega dos veces
        (p. ej. Enter + botón)."""
        if self._is_closed:
            return
        if self._on_apply is not None:
            self._on_apply(self.get_value(), self.get_direction())
        super().accept()


class SvgSizeDialog(FramelessDialog):
    """Pregunta a qué tamaño rasterizar un SVG al abrirlo (un vectorial no
    tiene píxeles propios). Arranca con el tamaño declarado por el archivo y,
    con la casilla marcada, mantiene la proporción al editar un campo.
    get_values() -> (ancho, alto) en píxeles."""

    def __init__(self, parent=None, width=512, height=512):
        super().__init__(parent)
        self.setWindowTitle(t("dlg.svg_import", default="Importar SVG"))
        self._body.setFixedSize(340, 220)
        self.setStyleSheet(
            "QDialog { background-color: %s; } QLabel { color: %s; }" % (theme.BG_WINDOW, theme.TEXT)
            + theme.spinbox_dialog_qss() + theme.checkbox_qss() + theme.dialog_button_plain_qss()
        )

        self._aspect = width / max(1, height)
        self._updating = False

        layout = self.body_layout
        layout.addWidget(QLabel(t("dlg.svg_declared", w=width, h=height)))
        layout.addSpacing(4)

        self.keep_aspect_check = QCheckBox(t("dlg.keep_aspect"))
        self.keep_aspect_check.setChecked(True)
        layout.addWidget(self.keep_aspect_check)

        g = QGridLayout()
        g.setVerticalSpacing(8)
        g.setColumnStretch(1, 1)
        g.addWidget(QLabel(t("dlg.width")), 0, 0)
        self.w_spin = QSpinBox()
        self.w_spin.setRange(1, 20000)
        self.w_spin.setSuffix(" px")
        self.w_spin.setValue(int(width))
        g.addWidget(self.w_spin, 0, 2)
        g.addWidget(QLabel(t("dlg.height")), 1, 0)
        self.h_spin = QSpinBox()
        self.h_spin.setRange(1, 20000)
        self.h_spin.setSuffix(" px")
        self.h_spin.setValue(int(height))
        g.addWidget(self.h_spin, 1, 2)
        layout.addLayout(g)

        self.w_spin.valueChanged.connect(self._on_width_changed)
        self.h_spin.valueChanged.connect(self._on_height_changed)

        layout.addStretch()

        btns = QHBoxLayout()
        btns.addStretch()
        ok_btn = QPushButton(t("dlg.ok"))
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton(t("dlg.cancel"))
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(ok_btn)
        btns.addWidget(cancel_btn)
        layout.addLayout(btns)

    def _on_width_changed(self, val):
        if self._updating or not self.keep_aspect_check.isChecked():
            return
        self._updating = True
        self.h_spin.setValue(max(1, round(val / self._aspect)))
        self._updating = False

    def _on_height_changed(self, val):
        if self._updating or not self.keep_aspect_check.isChecked():
            return
        self._updating = True
        self.w_spin.setValue(max(1, round(val * self._aspect)))
        self._updating = False

    def get_values(self):
        return self.w_spin.value(), self.h_spin.value()


class AnimExportDialog(FramelessDialog):
    """Opciones al exportar las capas visibles como animación GIF/WebP:
    duración por fotograma, usar las duraciones originales (si las capas las
    traen de un animado importado) y bucle.
    get_values() -> (ms, usar_originales, bucle)."""

    def __init__(self, parent=None, default_ms=100, has_original=False):
        super().__init__(parent)
        self.setWindowTitle(t("dlg.anim_export", default="Exportar animación"))
        self._body.setFixedSize(360, 200)
        self.setStyleSheet(
            "QDialog { background-color: %s; } QLabel { color: %s; }" % (theme.BG_WINDOW, theme.TEXT)
            + theme.spinbox_dialog_qss() + theme.checkbox_qss() + theme.dialog_button_plain_qss()
        )

        layout = self.body_layout
        row = QHBoxLayout()
        row.addWidget(QLabel(t("dlg.anim_duration")))
        self.ms_spin = QSpinBox()
        self.ms_spin.setRange(20, 10000)
        self.ms_spin.setSuffix(" ms")
        self.ms_spin.setValue(int(default_ms))
        row.addWidget(self.ms_spin)
        row.addStretch()
        layout.addLayout(row)

        self.orig_check = QCheckBox(t("dlg.anim_use_original"))
        self.orig_check.setChecked(bool(has_original))
        self.orig_check.setEnabled(bool(has_original))
        layout.addWidget(self.orig_check)

        self.loop_check = QCheckBox(t("dlg.anim_loop"))
        self.loop_check.setChecked(True)
        layout.addWidget(self.loop_check)

        layout.addStretch()

        btns = QHBoxLayout()
        btns.addStretch()
        ok_btn = QPushButton(t("dlg.ok"))
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton(t("dlg.cancel"))
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(ok_btn)
        btns.addWidget(cancel_btn)
        layout.addLayout(btns)

    def get_values(self):
        return (self.ms_spin.value(), self.orig_check.isChecked(),
                self.loop_check.isChecked())


class _AnimPreviewCanvas(QWidget):
    """Área de la previsualización: pinta el fotograma actual sobre un tablero
    de transparencia (los fotogramas pueden traer alfa)."""

    def __init__(self, size, parent=None):
        super().__init__(parent)
        self.setFixedSize(size)
        self._pixmap = None

    def set_pixmap(self, pm):
        self._pixmap = pm
        self.update()

    def paintEvent(self, event):
        from PySide6.QtGui import QPainter, QColor
        p = QPainter(self)
        w, h = self.width(), self.height()
        tile, c1, c2 = 8, QColor(200, 200, 200), QColor(160, 160, 160)
        y = 0
        while y < h:
            x = 0
            while x < w:
                p.fillRect(x, y, tile, tile,
                           c1 if ((x // tile + y // tile) % 2 == 0) else c2)
                x += tile
            y += tile
        if self._pixmap is not None:
            p.drawPixmap(0, 0, self._pixmap)
        p.setPen(theme.BORDER)
        p.drawRect(0, 0, w - 1, h - 1)
        p.end()


class AnimPreviewDialog(FramelessDialog):
    """Previsualiza la animación SIN tocar el lienzo: recibe los fotogramas ya
    compuestos (los de frames_de_capas, los mismos que se exportarían) y los
    reproduce con un QTimer encadenado. Controles: reproducir/pausa, deslizador
    de fotograma, duración y usar las duraciones originales si las hay."""

    MAX_W, MAX_H = 480, 360

    def __init__(self, parent, frames, delays, default_ms=100):
        super().__init__(parent)
        self.setWindowTitle(t("dlg.anim_preview", default="Previsualizar animación"))

        from PySide6.QtGui import QPixmap
        w0, h0 = frames[0].width(), frames[0].height()
        escala = min(1.0, self.MAX_W / w0, self.MAX_H / h0)
        sw, sh = max(1, round(w0 * escala)), max(1, round(h0 * escala))
        self._pixmaps = []
        for f in frames:
            pm = QPixmap.fromImage(f)
            if escala < 1.0:
                pm = pm.scaled(sw, sh, Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
            self._pixmaps.append(pm)
        self._delays = list(delays)
        self._idx = 0
        self._reproduciendo = False

        self._body.setFixedSize(max(sw + 24, 380), sh + 192)
        self.setStyleSheet(
            "QDialog { background-color: %s; } QLabel { color: %s; }" % (theme.BG_WINDOW, theme.TEXT)
            + theme.slider_qss() + theme.spinbox_dialog_qss()
            + theme.checkbox_qss() + theme.dialog_button_plain_qss()
        )

        layout = self.body_layout
        self._area = _AnimPreviewCanvas(QSize(sw, sh))
        layout.addWidget(self._area, 0, Qt.AlignmentFlag.AlignHCenter)

        # ─── fila de transporte: reproducir/pausa · deslizador · "i / n" ───
        fila = QHBoxLayout()
        self.btn_play = QPushButton(t("dlg.anim_pause"))
        self.btn_play.setFixedWidth(96)
        self.btn_play.clicked.connect(self._toggle_play)
        fila.addWidget(self.btn_play)
        self.frame_slider = QSlider(Qt.Orientation.Horizontal)
        self.frame_slider.setRange(0, len(self._pixmaps) - 1)
        self.frame_slider.valueChanged.connect(self._ir_a)
        fila.addWidget(self.frame_slider)
        self.lbl_frame = QLabel("")
        self.lbl_frame.setMinimumWidth(56)
        self.lbl_frame.setAlignment(Qt.AlignmentFlag.AlignRight
                                    | Qt.AlignmentFlag.AlignVCenter)
        fila.addWidget(self.lbl_frame)
        layout.addLayout(fila)

        # ─── duración: spin en ms, y debajo la casilla de las originales ───
        fila2 = QHBoxLayout()
        fila2.addWidget(QLabel(t("dlg.anim_duration")))
        self.ms_spin = QSpinBox()
        self.ms_spin.setRange(20, 10000)
        self.ms_spin.setSuffix(" ms")
        self.ms_spin.setValue(int(default_ms))
        # Ancho holgado: con el que negocia el QSS se corta "10000 ms".
        self.ms_spin.setMinimumWidth(110)
        fila2.addWidget(self.ms_spin)
        fila2.addStretch()
        layout.addLayout(fila2)

        self.orig_check = QCheckBox(t("dlg.anim_use_original"))
        hay_orig = any(self._delays)
        self.orig_check.setChecked(hay_orig)
        self.orig_check.setEnabled(hay_orig)
        layout.addWidget(self.orig_check)

        layout.addStretch()
        btns = QHBoxLayout()
        btns.addStretch()
        cerrar = QPushButton(t("common.close"))
        cerrar.clicked.connect(self.accept)
        btns.addWidget(cerrar)
        layout.addLayout(btns)

        # QTimer de UN disparo encadenado: cada fotograma programa el
        # siguiente con SU duración (así respeta delays distintos por capa).
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._siguiente)
        self._mostrar()
        self._play(True)

    def _intervalo(self):
        if self.orig_check.isChecked():
            d = self._delays[self._idx] if self._idx < len(self._delays) else None
            if d:
                return max(20, int(d))
        return self.ms_spin.value()

    def _mostrar(self):
        self._area.set_pixmap(self._pixmaps[self._idx])
        self.lbl_frame.setText("%d / %d" % (self._idx + 1, len(self._pixmaps)))
        # sincroniza el deslizador sin re-disparar _ir_a
        self.frame_slider.blockSignals(True)
        self.frame_slider.setValue(self._idx)
        self.frame_slider.blockSignals(False)

    def _siguiente(self):
        self._idx = (self._idx + 1) % len(self._pixmaps)
        self._mostrar()
        if self._reproduciendo:
            self._timer.start(self._intervalo())

    def _ir_a(self, i):
        self._idx = int(i)
        self._mostrar()
        if self._reproduciendo:            # seguir reproduciendo desde ahí
            self._timer.start(self._intervalo())

    def _play(self, activo):
        self._reproduciendo = bool(activo)
        self.btn_play.setText(t("dlg.anim_pause") if activo else t("dlg.anim_play"))
        if activo:
            self._timer.start(self._intervalo())
        else:
            self._timer.stop()

    def _toggle_play(self):
        self._play(not self._reproduciendo)


class SegmentPickerDialog(FramelessDialog):
    """Tras la segmentación semántica, elegir qué clase(s) seleccionar. `items`
    es una lista de (etiqueta, índice_de_clase); admite selección múltiple.
    get_selected() devuelve la lista de índices elegidos."""

    def __init__(self, items, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("ai.seg.title", default="Seleccionar objeto"))
        self.setMinimumWidth(320)
        self.setStyleSheet(
            "QDialog { background-color: %s; } QLabel { color: %s; }" % (theme.BG_WINDOW, theme.TEXT)
            + theme.list_qss() + theme.dialog_button_plain_qss()
        )
        layout = self.body_layout
        info = QLabel(t("ai.seg.pick", default="Elige qué seleccionar:"))
        info.setStyleSheet(f"color:{theme.TEXT_DIM}; font-style:italic;")
        layout.addWidget(info)

        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list.setStyleSheet(theme.list_qss() + " QListWidget::item { padding: 5px; }")
        for label, idx in items:
            it = QListWidgetItem(label)
            it.setData(Qt.ItemDataRole.UserRole, idx)
            self.list.addItem(it)
        if items:
            self.list.setCurrentRow(0)
        self.list.setMinimumHeight(min(260, 34 * max(1, len(items)) + 8))
        layout.addWidget(self.list)

        layout.addSpacing(4)
        btns = QHBoxLayout()
        btns.addStretch()
        ok = QPushButton(t("common.accept", default="Aceptar"))
        ok.clicked.connect(self.accept)
        cancel = QPushButton(t("common.cancel", default="Cancelar"))
        cancel.clicked.connect(self.reject)
        btns.addWidget(ok)
        btns.addWidget(cancel)
        layout.addLayout(btns)

    def get_selected(self):
        return [it.data(Qt.ItemDataRole.UserRole) for it in self.list.selectedItems()]