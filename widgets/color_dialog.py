# widgets/color_dialog.py
"""Selector de color PROPIO de Imago (boceto C): rueda de tono+saturacion
(el angulo elige el tono, el radio la saturacion), una barra vertical de valor
(brillo), una barra horizontal de canal alfa, recuadros R/G/B/A editables con
flechas y un campo Hex sin flechas, mas una rejilla de muestras.

Sustituye al viejo QColorDialog. La logica de edicion vive en _ColorEditorMixin;
NINGUN selector es ya una ventana del SO: todos son overlays HIJOS del lienzo
(_ColorOverlayBase, misma familia que los Ajustes/Efectos) -> Wayland-safe, con
topes y aspecto identico en Windows y Linux. Dos subclases:

- ImagoColorOverlay: editor EN VIVO del panel de color. Lleva los cuadros
  primario/secundario (invertir y restablecer) y REFLEJA cada cambio en el panel
  (y guarda el color de pincel) SIN repintar la herramienta en vivo. Lo abre el
  panel (open_color_dialog / _open_live_editor).
- ImagoColorPickerOverlay: selector para los sitios que necesitan UN color
  concreto (color de efecto, fondo de IA...). Lleva previsualizacion y botones
  Aceptar/Cancelar y entrega el color por callback on_accept(color). Lo abre
  imago_pick_color() (widgets/colors_panel.py).

Clic izquierdo en una muestra -> la usa como color en edicion; clic derecho -> el
"otro" color (en el editor en vivo: el secundario si edito el primario, y al
reves).
"""

import math

import numpy as np
from PySide6.QtWidgets import (QWidget, QLabel, QSpinBox, QLineEdit, QPushButton,
                               QHBoxLayout, QVBoxLayout, QGridLayout)
from PySide6.QtGui import QColor, QPainter, QPen, QLinearGradient, QImage, QIcon
from PySide6.QtCore import Qt, Signal, QPointF, QSize, QFile, QEvent, QTimer

from widgets.overlay_panel import OverlayPanel
from widgets.colors_panel import ColorSwatch, _DefaultColorsIcon, _paint_checker
from i18n import t
import theme


# Las 24 muestras de la rejilla (mismas que la paleta fija del panel de color).
_PRESETS = [
    "#000000", "#404040", "#808080", "#C0C0C0", "#FFFFFF", "#800000",
    "#FF0000", "#FF8000", "#FFFF00", "#00FF00", "#00FFFF", "#0000FF",
    "#FF00FF", "#800080", "#804000", "#808000", "#A04000", "#FF8080",
    "#FFC080", "#FFFF80", "#80FF80", "#80FFFF", "#8080FF", "#FF80FF",
]


def _hsv_to_rgb_arrays(h, s, v):
    """HSV -> RGB vectorizado. h en [0,360), s en [0,1], v escalar en [0,1].
    Devuelve tres arrays float (0..1) con la forma de h/s."""
    h = np.asarray(h, dtype=np.float64)
    s = np.asarray(s, dtype=np.float64)
    c = v * s
    hp = (h / 60.0) % 6.0
    x = c * (1.0 - np.abs(hp % 2.0 - 1.0))
    z = np.zeros_like(hp)
    conds = [hp < 1, hp < 2, hp < 3, hp < 4, hp < 5, hp <= 6]
    r = np.select(conds, [c, x, z, z, x, c], default=z)
    g = np.select(conds, [x, c, c, x, z, z], default=z)
    b = np.select(conds, [z, z, x, c, c, x], default=z)
    m = v - c
    return r + m, g + m, b + m


def _wheel_qimage(size, value):
    """Rueda (disco) RGBA de lado 'size' con el brillo 'value' (0..1): angulo =
    tono, radio = saturacion. Borde suavizado 1px por el alfa."""
    r = size / 2.0
    yy, xx = np.ogrid[0:size, 0:size]
    dx = xx - r + 0.5
    dy = yy - r + 0.5
    dist = np.sqrt(dx * dx + dy * dy)
    sat = np.clip(dist / r, 0.0, 1.0)
    ang = np.degrees(np.arctan2(-dy, dx)) % 360.0
    rr, gg, bb = _hsv_to_rgb_arrays(ang + 0 * sat, sat, value)
    out = np.zeros((size, size, 4), dtype=np.uint8)
    out[..., 0] = np.clip(rr * 255.0, 0, 255).astype(np.uint8)
    out[..., 1] = np.clip(gg * 255.0, 0, 255).astype(np.uint8)
    out[..., 2] = np.clip(bb * 255.0, 0, 255).astype(np.uint8)
    out[..., 3] = (np.clip(r + 0.5 - dist, 0.0, 1.0) * 255.0).astype(np.uint8)
    out = np.ascontiguousarray(out)
    # .copy() -> Qt se queda con los datos; el array numpy puede liberarse.
    return QImage(out.data, size, size, 4 * size, QImage.Format_RGBA8888).copy()


class HueSatWheel(QWidget):
    """Disco de tono (angulo) y saturacion (radio). Emite changed(h, s) con h en
    grados [0,360) y s en [0,1]. Se dibuja SIEMPRE a color pleno (no se oscurece
    con el valor): es el selector de tono/saturacion; el brillo lo lleva la barra
    de valor. Solo el marcador se mueve segun el color elegido."""

    changed = Signal(float, float)

    def __init__(self, diameter=156, parent=None):
        super().__init__(parent)
        self._d = diameter
        self.setFixedSize(diameter, diameter)
        self.setCursor(Qt.CrossCursor)
        self._h = 0.0
        self._s = 0.0
        # La rueda SIEMPRE a brillo maximo (V=1): asi se ve a color aunque el
        # color elegido sea muy oscuro o negro. La imagen no depende del valor,
        # se construye una sola vez.
        self._img = _wheel_qimage(self._d, 1.0)

    def set_hsv(self, h, s, v):
        # v se ignora a proposito (la rueda no se apaga); solo movemos el
        # marcador segun tono/saturacion.
        self._h = h
        self._s = s
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        if self._img is not None:
            p.drawImage(0, 0, self._img)
        p.setPen(QPen(QColor("#191919"), 1))
        p.drawEllipse(0, 0, self._d - 1, self._d - 1)
        # Marcador
        r = self._d / 2.0
        ang = math.radians(self._h)
        rad = self._s * r
        mx = r + rad * math.cos(ang)
        my = r - rad * math.sin(ang)
        c = QPointF(mx, my)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(0, 0, 0, 200), 2))
        p.drawEllipse(c, 6, 6)
        p.setPen(QPen(QColor(255, 255, 255), 1.4))
        p.drawEllipse(c, 6, 6)
        p.end()

    def _emit_from_pos(self, pos):
        r = self._d / 2.0
        dx = pos.x() - r
        dy = pos.y() - r
        dist = math.hypot(dx, dy)
        s = min(1.0, dist / r) if r else 0.0
        h = math.degrees(math.atan2(-dy, dx)) % 360.0
        self.changed.emit(h, s)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._emit_from_pos(event.position())

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self._emit_from_pos(event.position())


class ValueBar(QWidget):
    """Barra vertical de valor/brillo: arriba el color puro, abajo el negro.
    Emite changed(v) con v en [0,1]."""

    changed = Signal(float)

    def __init__(self, height=156, width=18, parent=None):
        super().__init__(parent)
        self.setFixedSize(width, height)
        self.setCursor(Qt.PointingHandCursor)
        self._h = 0.0
        self._s = 0.0
        self._v = 1.0

    def set_hsv(self, h, s, v):
        self._h = h
        self._s = s
        self._v = v
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        w, h = self.width(), self.height()
        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0.0, QColor.fromHsvF((self._h % 360.0) / 360.0, self._s, 1.0))
        grad.setColorAt(1.0, QColor(0, 0, 0))
        p.fillRect(0, 0, w, h, grad)
        p.setPen(QPen(QColor("#191919"), 1))
        p.drawRect(0, 0, w - 1, h - 1)
        # Tirador
        gy = int(round((1.0 - self._v) * (h - 1)))
        p.setPen(QPen(QColor(0, 0, 0), 1))
        p.setBrush(QColor(255, 255, 255))
        p.drawRect(0, max(0, gy - 2), w - 1, 4)
        p.end()

    def _emit_from_pos(self, pos):
        h = self.height()
        v = 1.0 - (pos.y() / h if h else 0.0)
        self.changed.emit(min(1.0, max(0.0, v)))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._emit_from_pos(event.position())

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self._emit_from_pos(event.position())


class AlphaBar(QWidget):
    """Barra horizontal de canal alfa: tablero de transparencia + degradado de
    transparente al color actual. Emite changed(frac) con frac en [0,1]."""

    changed = Signal(float)

    def __init__(self, height=15, parent=None):
        super().__init__(parent)
        self.setFixedHeight(height)
        self.setMinimumWidth(60)
        self.setCursor(Qt.PointingHandCursor)
        self._color = QColor("#000000")
        self._frac = 1.0

    def set_color(self, h, s, v):
        self._color = QColor.fromHsvF((h % 360.0) / 360.0, s, v)
        self.update()

    def set_fraction(self, frac):
        self._frac = min(1.0, max(0.0, frac))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        w, h = self.width(), self.height()
        _paint_checker(p, w, h, tile=4)
        c0 = QColor(self._color)
        c0.setAlpha(0)
        c1 = QColor(self._color)
        c1.setAlpha(255)
        grad = QLinearGradient(0, 0, w, 0)
        grad.setColorAt(0.0, c0)
        grad.setColorAt(1.0, c1)
        p.fillRect(0, 0, w, h, grad)
        p.setPen(QPen(QColor("#191919"), 1))
        p.drawRect(0, 0, w - 1, h - 1)
        gx = int(round(self._frac * (w - 1)))
        p.setPen(QPen(QColor(0, 0, 0), 1))
        p.setBrush(QColor(255, 255, 255))
        p.drawRect(max(0, gx - 2), 0, 4, h - 1)
        p.end()

    def _emit_from_pos(self, pos):
        w = self.width()
        self.changed.emit(min(1.0, max(0.0, pos.x() / w if w else 0.0)))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._emit_from_pos(event.position())

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self._emit_from_pos(event.position())


class _ColorEditorMixin:
    """Logica compartida del editor de color: rueda de tono/saturacion, barra de
    valor, barra de alfa, campos R/G/B/A y Hex, rejilla de muestras y estado HSV.

    La comparten las dos subclases de _ColorOverlayBase (ambas overlays HIJOS del
    lienzo, Wayland-safe):
      - ImagoColorOverlay: editor EN VIVO del panel de color; con los cuadros
        primario/secundario (invertir y restablecer), refleja cada cambio en el
        panel SIN repintar la herramienta en vivo. Sin previsualizacion ni botones.
      - ImagoColorPickerOverlay: selector suelto (color de efecto, fondo de IA...)
        que entrega el color por callback on_accept(color). Con previsualizacion y
        botones Aceptar/Cancelar.

    El contenedor provee self.body_layout, self._body, setWindowTitle y accept/
    reject. Antes de _build_editor() hay que fijar self._live, self._panel,
    self._active, self._show_alpha, self._sync y el estado inicial con
    _init_color_state()."""

    def _init_color_state(self, initial):
        self._h = 0.0
        self._s = 0.0
        self._v = 1.0
        self._a = 255
        col = QColor(initial) if initial is not None else QColor("#000000")
        if not col.isValid():
            col = QColor("#000000")
        self._set_from_qcolor(col)

    def _build_editor(self):
        layout = self.body_layout
        layout.setSpacing(11)

        # ── Fila superior: [cuadros prim/sec] rueda + barra de valor + campos ──
        top = QHBoxLayout()
        top.setSpacing(12)
        if self._live:
            top.addWidget(self._build_color_boxes(), 0, Qt.AlignTop)
        self.wheel = HueSatWheel(150)
        self.value_bar = ValueBar(150, 16)
        top.addWidget(self.wheel)
        top.addWidget(self.value_bar)

        # Ancho comun de TODOS los campos (R/G/B/A y Hex) y del rectangulo de
        # previsualizacion: asi miden lo mismo y quedan alineados a la derecha
        # de la columna.
        FW = 76
        fields = QVBoxLayout()
        fields.setSpacing(6)

        # La previsualizacion solo existe en modo MODAL; en vivo su papel lo hacen
        # los cuadros primario/secundario de arriba a la izquierda.
        self.preview = None
        if not self._live:
            self.preview = ColorSwatch()
            self.preview.setFixedSize(FW, 30)
            self.preview.setCursor(Qt.ArrowCursor)
            prow = QHBoxLayout()
            prow.setContentsMargins(0, 0, 0, 0)
            prow.addStretch()
            prow.addWidget(self.preview)
            fields.addLayout(prow)

        self.r_spin = self._make_spin(FW)
        self.g_spin = self._make_spin(FW)
        self.b_spin = self._make_spin(FW)
        fields.addLayout(self._field_row("R", self.r_spin))
        fields.addLayout(self._field_row("G", self.g_spin))
        fields.addLayout(self._field_row("B", self.b_spin))
        self.a_spin = None
        if self._show_alpha:
            self.a_spin = self._make_spin(FW)
            fields.addLayout(self._field_row("A", self.a_spin))
        self.hex_edit = QLineEdit()
        self.hex_edit.setMaxLength(7)
        self.hex_edit.setFixedWidth(FW)
        self.hex_edit.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.hex_edit.setStyleSheet(
            f"QLineEdit {{ background: {theme.BG_DARK}; border: 1px solid {theme.BORDER_FAINT};"
            f" color: {theme.TEXT}; font-family: monospace; padding: 2px 4px; border-radius: 3px; }}"
            f" QLineEdit:focus {{ border: 1px solid {theme.ACCENT}; }}"
        )
        fields.addLayout(self._field_row("#", self.hex_edit))
        fields.addStretch(1)
        top.addLayout(fields, 1)
        layout.addLayout(top)

        # ── Barra de alfa (ancho completo) ──
        self.alpha_bar = None
        if self._show_alpha:
            arow = QHBoxLayout()
            arow.setSpacing(8)
            a_lbl = QLabel("α")  # α
            a_lbl.setFixedWidth(12)
            self.alpha_bar = AlphaBar(15)
            arow.addWidget(a_lbl)
            arow.addWidget(self.alpha_bar, 1)
            layout.addLayout(arow)

        # ── Separador + rejilla de muestras ──
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: %s;" % theme.BORDER_SOFT)
        layout.addWidget(sep)

        swatches = QGridLayout()
        swatches.setSpacing(4)
        show_tip = self._live
        for i, hexc in enumerate(_PRESETS):
            btn = QPushButton()
            btn.setFixedSize(20, 20)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(
                f"QPushButton {{ background-color: {hexc}; border: 1px solid {theme.BORDER_FAINT};"
                f" border-radius: 2px; }} QPushButton:hover {{ border: 1px solid {theme.ACCENT}; }}"
            )
            if show_tip:
                btn.setToolTip(t("color.picker.swatch_tip"))
            btn.clicked.connect(lambda _=False, c=hexc: self._use_color(QColor(c)))
            btn.setContextMenuPolicy(Qt.CustomContextMenu)
            btn.customContextMenuRequested.connect(
                lambda _pos, c=hexc: self._alt_pick(QColor(c)))
            swatches.addWidget(btn, i // 12, i % 12)
        layout.addLayout(swatches)

        # ── Muestras personalizadas (persistentes en QSettings) ──
        # Debajo de la paleta fija: el usuario guarda el color actual con "+" o
        # importa una paleta de GIMP (.gpl) con "…". Se comparten entre las dos
        # variantes del selector (viven en QSettings, no en el panel de color).
        self._build_custom_swatches(layout)

        # ── Botones: solo en modo MODAL (en vivo se aplica al momento) ──
        self.btn_ok = None
        self.btn_cancel = None
        if not self._live:
            btn_row = QHBoxLayout()
            btn_row.addStretch()
            self.btn_ok = QPushButton(t("dlg.ok"))
            self.btn_cancel = QPushButton(t("dlg.cancel"))
            self.btn_ok.setDefault(True)
            btn_row.addWidget(self.btn_ok)
            btn_row.addWidget(self.btn_cancel)
            layout.addLayout(btn_row)

        # Conexiones
        self.wheel.changed.connect(self._on_wheel)
        self.value_bar.changed.connect(self._on_value)
        if self.alpha_bar is not None:
            self.alpha_bar.changed.connect(self._on_alpha_bar)
        self.r_spin.valueChanged.connect(self._on_rgb)
        self.g_spin.valueChanged.connect(self._on_rgb)
        self.b_spin.valueChanged.connect(self._on_rgb)
        if self.a_spin is not None:
            self.a_spin.valueChanged.connect(self._on_alpha_spin)
        self.hex_edit.textChanged.connect(self._on_hex)
        if self.btn_ok is not None:
            self.btn_ok.clicked.connect(self.accept)
            self.btn_cancel.clicked.connect(self.reject)

        self._body.setFixedWidth(388 if self._live else 360)
        if self._live:
            self._update_active()
        self._refresh_ui()

    # ------------------------------------------------------------- utilidades
    def _make_spin(self, width):
        sp = QSpinBox()
        sp.setRange(0, 255)
        sp.setFixedWidth(width)
        sp.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        return sp

    def _field_row(self, name, widget):
        """Fila 'etiqueta + campo' pegada a la DERECHA de la columna: un stretch
        a la izquierda empuja la etiqueta y el campo hacia el borde derecho, de
        modo que los campos de todas las filas quedan alineados."""
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        lbl = QLabel(name)
        lbl.setStyleSheet(f"font-family: monospace; font-size: 12px; color: {theme.TEXT_DIM};")
        row.addStretch()
        row.addWidget(lbl)
        row.addWidget(widget)
        return row

    def _current_qcolor(self):
        c = QColor.fromHsvF((self._h % 360.0) / 360.0, self._s, self._v)
        c.setAlpha(self._a if self._show_alpha else 255)
        return c

    def _set_from_qcolor(self, color):
        """Vuelca un QColor al estado HSV canonico; si es acromatico (gris),
        CONSERVA el tono anterior para que el marcador no salte."""
        h = color.hueF()
        if h < 0:
            h = (self._h % 360.0) / 360.0
        self._h = (h * 360.0) % 360.0
        self._s = color.saturationF()
        self._v = color.valueF()
        if self._show_alpha:
            self._a = color.alpha()

    def selected_color(self):
        return self._current_qcolor()

    # ---------------------------------------------------------------- refresco
    def _refresh_ui(self):
        self._sync = True
        col = self._current_qcolor()
        self.wheel.set_hsv(self._h, self._s, self._v)
        self.value_bar.set_hsv(self._h, self._s, self._v)
        if self.alpha_bar is not None:
            self.alpha_bar.set_color(self._h, self._s, self._v)
            self.alpha_bar.set_fraction(self._a / 255.0)
        self.r_spin.setValue(col.red())
        self.g_spin.setValue(col.green())
        self.b_spin.setValue(col.blue())
        if self.a_spin is not None:
            self.a_spin.setValue(self._a)
        self.hex_edit.setText("#%02X%02X%02X" % (col.red(), col.green(), col.blue()))
        if self.preview is not None:
            self.preview.set_color(col)
        self._sync = False

    def _after_change(self):
        """Refresca los controles y, en modo en vivo, aplica el color al target
        activo del panel (que actualiza el lienzo y sus cuadros)."""
        self._refresh_ui()
        if self._live:
            self._apply_active()

    # ---------------------------------------------------------------- handlers
    def _on_wheel(self, h, s):
        if self._sync:
            return
        self._h, self._s = h, s
        # Si el color estaba en negro (valor 0), un clic en la rueda a color
        # daria negro igualmente; subimos el brillo al maximo para que el clic
        # produzca el color que se ve en la rueda.
        if self._v <= 0.0:
            self._v = 1.0
        self._after_change()

    def _on_value(self, v):
        if self._sync:
            return
        self._v = v
        self._after_change()

    def _on_alpha_bar(self, frac):
        if self._sync:
            return
        self._a = int(round(frac * 255))
        self._after_change()

    def _on_rgb(self, _value=0):
        if self._sync:
            return
        col = QColor(self.r_spin.value(), self.g_spin.value(), self.b_spin.value())
        col.setAlpha(self._a)
        self._set_from_qcolor(col)
        self._after_change()

    def _on_alpha_spin(self, value):
        if self._sync:
            return
        self._a = value
        self._after_change()

    def _on_hex(self, text):
        if self._sync:
            return
        text = text.strip()
        if not text.startswith("#"):
            text = "#" + text
        if len(text) == 7:
            col = QColor(text)
            if col.isValid():
                col.setAlpha(self._a)
                self._set_from_qcolor(col)
                self._after_change()

    def _use_color(self, qcolor):
        """Muestra elegida con clic izquierdo: pasa a ser el color en edicion
        (conservando el alfa actual)."""
        col = QColor(qcolor)
        col.setAlpha(self._a)
        self._set_from_qcolor(col)
        self._after_change()

    def _alt_pick(self, qcolor):
        """Muestra con clic DERECHO (solo en modo EN VIVO): asigna el 'OTRO' color
        (el secundario si edito el primario, y viceversa). En el modal suelto el
        clic derecho no hace nada."""
        if self._live:
            col = QColor(qcolor)   # el otro color se asigna opaco
            if self._active == "primary":
                self._panel.set_secondary_color(col)
            else:
                self._panel.set_active_color(col)
            self._refresh_boxes()

    # -------------------------------------------------- muestras personalizadas
    MAX_MUESTRAS = 96   # tope para que la rejilla no crezca sin fin

    def _build_custom_swatches(self, layout):
        """Monta la cabecera (etiqueta + botones "+"/"…") y la rejilla de muestras
        propias. Solo si hay ventana principal (de ahi salen QSettings/status_bar)."""
        if self._main_window is None:
            self.custom_grid = None
            return
        fila = QHBoxLayout()
        fila.setSpacing(4)
        fila.addWidget(QLabel(t("color.custom")))
        fila.addStretch()
        # padding:0 anula el 'padding: 5px 14px' que el selector suelto hereda de
        # dialog_button_plain_qss(): en un boton de 18x18 dejaba el "+"/"…" sin
        # sitio (se veian vacios). El editor en vivo no hereda ese padding.
        btn_qss = theme.panel_action_button_qss() + " QPushButton { padding: 0px; }"
        self.btn_add_swatch = QPushButton("+")
        self.btn_add_swatch.setFixedSize(18, 18)
        self.btn_add_swatch.setCursor(Qt.PointingHandCursor)
        self.btn_add_swatch.setToolTip(t("color.custom_add_tip"))
        self.btn_add_swatch.setStyleSheet(btn_qss)
        self.btn_add_swatch.clicked.connect(self.add_custom_swatch)
        fila.addWidget(self.btn_add_swatch)
        self.btn_import_gpl = QPushButton("…")
        self.btn_import_gpl.setFixedSize(18, 18)
        self.btn_import_gpl.setCursor(Qt.PointingHandCursor)
        self.btn_import_gpl.setToolTip(t("color.custom_import_tip"))
        self.btn_import_gpl.setStyleSheet(btn_qss)
        self.btn_import_gpl.clicked.connect(self.import_gpl_palette)
        fila.addWidget(self.btn_import_gpl)
        layout.addLayout(fila)

        # La rejilla vive en un 'holder' que se RECREA en cada reconstruccion:
        # QGridLayout NO reduce su numero de filas al quitar items, asi que al
        # borrar una muestra que ocupaba su propia fila el hueco persistia y el
        # panel no encogia. El HBox con un stretch a la derecha deja las muestras
        # alineadas a la IZQUIERDA (si no, el grid reparte el ancho y las separa).
        self._custom_row = QHBoxLayout()
        self._custom_row.setContentsMargins(0, 0, 0, 0)
        self._custom_row.addStretch()
        layout.addLayout(self._custom_row)
        self.custom_holder = None
        self._custom_colors = self._load_custom_swatches()
        self._rebuild_custom_swatches()

    def _load_custom_swatches(self):
        """Lee las muestras de QSettings (una cadena 'hex,hex,...' en ARGB;
        se guarda como cadena y no como lista para esquivar la rareza de
        QSettings de devolver un str suelto cuando la lista tiene 1 elemento)."""
        crudo = self._main_window.settings.value("colors/custom_swatches", "")
        colores = []
        for trozo in str(crudo or "").split(","):
            c = QColor(trozo.strip())
            if trozo.strip() and c.isValid():
                colores.append(c)
        return colores[:self.MAX_MUESTRAS]

    def _save_custom_swatches(self):
        self._main_window.settings.setValue(
            "colors/custom_swatches",
            ",".join(c.name(QColor.HexArgb) for c in self._custom_colors))

    def _rebuild_custom_swatches(self):
        """Reconstruye la rejilla de muestras propias desde self._custom_colors,
        RECREANDO el contenedor (ver nota sobre el numero de filas del grid)."""
        if self.custom_holder is not None:
            self._custom_row.removeWidget(self.custom_holder)
            self.custom_holder.deleteLater()
        self.custom_holder = QWidget()
        self.custom_holder.setStyleSheet("background: transparent;")
        grid = QGridLayout(self.custom_holder)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(4)
        for i, color in enumerate(self._custom_colors):
            sw = ColorSwatch(
                on_click=lambda ev, c=QColor(color): self._use_color(QColor(c)),
                on_right=lambda ev, idx=i: self._custom_swatch_menu(idx))
            sw.setFixedSize(20, 20)
            sw.set_color(color)
            sw.setToolTip(color.name(QColor.HexArgb if color.alpha() < 255
                                     else QColor.HexRgb).upper()
                          + "\n" + t("color.custom_swatch_tip"))
            grid.addWidget(sw, i // 12, i % 12)
        self._custom_row.insertWidget(0, self.custom_holder)
        # El overlay se posiciona a mano (no lo gestiona un layout del padre): al
        # crecer/menguar la rejilla hay que reajustar su alto o el contenido se
        # solaparia. Se difiere un tick (QTimer 0) porque justo tras mutar la
        # rejilla el sizeHint aun no esta recalculado (la invalidacion de los
        # layouts anidados y el deleteLater de las muestras viejas se procesan en
        # el bucle de eventos). En la construccion inicial no hace falta: lo
        # dimensiona open_over.
        if self.isVisible():
            QTimer.singleShot(0, self._refit)

    def _refit(self):
        """Reajusta el alto del overlay a su contenido y lo reencuadra."""
        if self._is_closed or not self.isVisible():
            return
        self.adjustSize()
        self.move_clamped(self.pos())

    def add_custom_swatch(self):
        """Guarda el color en edicion como muestra propia (sin duplicados)."""
        color = self._current_qcolor()
        if any(c.name(QColor.HexArgb) == color.name(QColor.HexArgb)
               for c in self._custom_colors):
            return
        if len(self._custom_colors) >= self.MAX_MUESTRAS:
            self._main_window.status_bar.showMessage(
                t("color.custom_full", n=self.MAX_MUESTRAS), 4000)
            return
        self._custom_colors.append(QColor(color))
        self._save_custom_swatches()
        self._rebuild_custom_swatches()

    def _custom_swatch_menu(self, index):
        """Menu contextual de una muestra propia: (solo en vivo) usar como
        secundario / eliminar."""
        from PySide6.QtWidgets import QMenu
        from PySide6.QtGui import QCursor
        if not (0 <= index < len(self._custom_colors)):
            return
        menu = QMenu(self)
        acc_sec = menu.addAction(t("color.custom_use_secondary")) if self._live else None
        acc_del = menu.addAction(t("color.custom_delete"))
        elegido = menu.exec(QCursor.pos())
        if acc_sec is not None and elegido is acc_sec:
            self._panel.set_secondary_color(QColor(self._custom_colors[index]))
            self._refresh_boxes()
        elif elegido is acc_del:
            del self._custom_colors[index]
            self._save_custom_swatches()
            self._rebuild_custom_swatches()

    def import_gpl_palette(self):
        """Importa una paleta de GIMP (.gpl): texto plano con lineas 'R G B
        [nombre]'. Anade los colores que no esten ya, hasta el tope."""
        from PySide6.QtWidgets import QFileDialog
        # El QFileDialog (y el posible aviso modal) disparan WindowBlocked en la
        # ventana, que normalmente cierra este overlay (ver eventFilter). Se
        # suprime ese autocierre durante la importacion para no operar despues
        # sobre widgets ya destruidos (y para que el overlay siga abierto y se
        # vean las muestras importadas).
        self._suppress_block = True
        try:
            ruta, _sel = QFileDialog.getOpenFileName(
                self._main_window, t("dlg.gpl_open"),
                getattr(self._main_window, "last_opened_dir", "") or "",
                t("dlg.filter.gpl"))
            if not ruta:
                return
            colores = self._parse_gpl(ruta)
            if colores is None:
                from widgets.custom_titlebar import imago_warning
                imago_warning(self._main_window, t("dlg.gpl_open"), t("msg.gpl.invalid"))
                return
            presentes = {c.name(QColor.HexArgb) for c in self._custom_colors}
            nuevos = 0
            for c in colores:
                if len(self._custom_colors) >= self.MAX_MUESTRAS:
                    break
                if c.name(QColor.HexArgb) in presentes:
                    continue
                self._custom_colors.append(c)
                presentes.add(c.name(QColor.HexArgb))
                nuevos += 1
            self._save_custom_swatches()
            self._rebuild_custom_swatches()
            self._main_window.status_bar.showMessage(
                t("status.gpl_imported", n=nuevos), 4000)
        finally:
            self._suppress_block = False

    @staticmethod
    def _parse_gpl(ruta):
        """Parsea un .gpl. Devuelve la lista de QColor, o None si el archivo
        no tiene la cabecera 'GIMP Palette'."""
        try:
            with open(ruta, "r", encoding="utf-8", errors="replace") as f:
                lineas = f.readlines()
        except OSError:
            return None
        if not lineas or "gimp palette" not in lineas[0].strip().lower():
            return None
        colores = []
        for linea in lineas[1:]:
            linea = linea.strip()
            if (not linea or linea.startswith("#")
                    or linea.lower().startswith(("name:", "columns:"))):
                continue
            partes = linea.split()
            if len(partes) < 3:
                continue
            try:
                r, g, b = (max(0, min(255, int(p))) for p in partes[:3])
            except ValueError:
                continue
            colores.append(QColor(r, g, b))
        return colores

    # -------------------------------------------------------- modo EN VIVO
    def _panel_color(self, which):
        """Color actual del cuadro primario/secundario del panel."""
        box = self._panel.preview_box if which == "primary" else self._panel.secondary_box
        c = box.color()
        if c is not None:
            return QColor(c)
        return QColor("#000000" if which == "primary" else "#FFFFFF")

    def _build_color_boxes(self):
        """Montaje primario/secundario (como el del panel de color) con los
        botones de invertir y restablecer, arriba a la izquierda."""
        BOX, OFF, GAP = 40, 20, 23
        area = OFF + BOX
        holder = QWidget()
        holder.setFixedSize(area, area)

        self.box_secondary = ColorSwatch(
            on_click=lambda e: self._select_target("secondary"), parent=holder)
        self.box_secondary.setGeometry(OFF, OFF, BOX, BOX)
        self.box_secondary.setToolTip(t("color.dlg.secondary"))
        self.box_primary = ColorSwatch(
            on_click=lambda e: self._select_target("primary"), parent=holder)
        self.box_primary.setGeometry(0, 0, BOX, BOX)
        self.box_primary.setToolTip(t("color.dlg.primary"))

        self.btn_swap = QPushButton(holder)
        if QFile.exists(":/icons/swap.png"):
            self.btn_swap.setIcon(theme.icono(":/icons/swap.png"))
            self.btn_swap.setIconSize(QSize(GAP - 6, GAP - 6))
        else:
            self.btn_swap.setText("⇄")
        self.btn_swap.setGeometry(BOX, -3, GAP, GAP)
        self.btn_swap.setCursor(Qt.PointingHandCursor)
        self.btn_swap.setToolTip(t("color.swap"))
        self.btn_swap.setStyleSheet(
            "QPushButton { background: transparent; border: none; color: %s; font-size: 13px; }"
            " QPushButton:hover { color: %s; }"
            " QPushButton:pressed { color: %s; }" % (theme.TEXT_BRIGHT, theme.TEXT, theme.ACCENT))
        self.btn_swap.clicked.connect(self._swap)

        self.icon_reset = _DefaultColorsIcon(self._reset, parent=holder)
        self.icon_reset.setGeometry(0, BOX + 2, GAP, GAP)

        self.box_secondary.lower()
        self.box_primary.raise_()
        self.btn_swap.raise_()
        self.icon_reset.raise_()
        self._refresh_boxes()
        return holder

    def _refresh_boxes(self):
        self.box_primary.set_color(self._panel_color("primary"))
        self.box_secondary.set_color(self._panel_color("secondary"))

    def _update_active(self):
        """Marca con borde de acento el cuadro que se esta editando y lo trae al
        frente para que se vea entero."""
        prim = self._active == "primary"
        self.box_primary.set_border(theme.ACCENT if prim else "auto")
        self.box_secondary.set_border(theme.ACCENT if not prim else "auto")
        (self.box_primary if prim else self.box_secondary).raise_()
        self.btn_swap.raise_()
        self.icon_reset.raise_()

    def set_target(self, active):
        """(Modo en vivo) Cambia desde fuera cual color se edita, en un editor ya
        abierto: lo llama el panel al pulsar el otro cuadro mientras esta abierto."""
        if self._live and active in ("primary", "secondary"):
            self._select_target(active)

    def _select_target(self, which):
        """Elige cual de los dos colores se edita y carga su valor en el editor."""
        self._active = which
        self._set_from_qcolor(self._panel_color(which))
        self._update_active()
        self._refresh_ui()

    def _apply_active(self):
        """Refleja el color en edicion en el cuadro correspondiente del panel
        (primario/secundario, hex y sliders), guarda el color de pincel y
        REFRESCA la herramienta activa: si hay un objeto flotante con preview
        (linea/curva, forma, degradado), el color se le aplica EN VIVO, igual
        que al cambiarlo desde los sliders o las muestras del panel. Tambien
        notifica al TEXTO en edicion (notify_text por defecto): un cuadro de
        texto abierto adopta el primario nuevo (en la seleccion, o en todo el
        texto/lo que se escriba), igual que desde el panel de color. Solo se
        llama en interacciones reales (_after_change), nunca al ABRIR el
        editor, asi que abrir la paleta no recolorea nada."""
        col = self._current_qcolor()
        if self._active == "primary":
            self._panel.set_active_color(col)
        else:
            self._panel.set_secondary_color(col)
        self._refresh_boxes()

    def _swap(self):
        # Intercambio primario/secundario reflejado en el panel y en la
        # herramienta en vivo (coherente con la X del panel de color, que
        # tambien notifica al texto en edicion).
        prim = self._panel_color("primary")
        sec = self._panel_color("secondary")
        self._panel.set_active_color(sec)
        self._panel.set_secondary_color(prim)
        self._select_target(self._active)
        self._refresh_boxes()

    def _reset(self):
        # Restablece negro/blanco (tambien en vivo sobre el objeto flotante
        # y sobre el texto en edicion, como cualquier cambio de primario).
        self._panel.set_active_color(QColor("#000000"))
        self._panel.set_secondary_color(QColor("#FFFFFF"))
        self._select_target(self._active)
        self._refresh_boxes()


class _ColorOverlayBase(_ColorEditorMixin, OverlayPanel):
    """Base comun de los editores de color OVERLAY (hijos del lienzo, Wayland-safe):
    los coloca arriba-derecha del lienzo con topes (open_editor), se cierran si
    aparece un dialogo MODAL (filtro de WindowBlocked) y NO persisten la posicion.
    Las subclases fijan su estado (self._live, self._panel, self._active,
    self._show_alpha, self._sync...) y llaman a _init_color_state()+_build_editor()."""

    def __init__(self, main_window):
        super().__init__(main_window)
        self._main_window = main_window
        self._top_win = None

    def open_editor(self):
        """Muestra el overlay arriba-derecha del lienzo (con topes, via open_over)
        y se engancha para cerrarse si aparece un dialogo modal."""
        # Instancia unica GLOBAL de overlay de color: el editor en vivo del panel
        # y el selector suelto (efectos, fondo de IA...) NO deben convivir en
        # pantalla. Si ya hay otro abierto, se cierra antes de abrir este.
        mw = self._main_window
        if mw is not None:
            prev = getattr(mw, "_active_color_overlay", None)
            if prev is not None and prev is not self:
                try:
                    prev.reject()
                except RuntimeError:
                    pass
            mw._active_color_overlay = self
        self.open_over(self._main_window)
        self._top_win = self._main_window.window() if self._main_window is not None else None
        if self._top_win is not None:
            self._top_win.installEventFilter(self)

    def eventFilter(self, obj, event):
        # Cerrarse si un dialogo MODAL bloquea la ventana principal (Preferencias,
        # Nuevo...): no deben convivir dos dialogos. Excepcion: cuando el propio
        # overlay abre un dialogo modal a proposito (importar paleta .gpl), no
        # debe autocerrarse (_suppress_block); si lo hiciera, seguiria operando
        # sobre sus widgets ya destruidos al volver.
        if obj is self._top_win and event.type() == QEvent.WindowBlocked:
            if not getattr(self, "_suppress_block", False):
                self.reject()
            return False
        return super().eventFilter(obj, event)

    def _close_panel(self):
        mw = self._main_window
        if mw is not None and getattr(mw, "_active_color_overlay", None) is self:
            mw._active_color_overlay = None
        if self._top_win is not None:
            self._top_win.removeEventFilter(self)
            self._top_win = None
        super()._close_panel()

    # No persistir la posicion: arranca SIEMPRE arriba-derecha (y evita compartir
    # la clave overlay/last_* con los overlays de efectos).
    def _read_saved_pos(self):
        return None

    def _save_pos(self):
        pass


class ImagoColorOverlay(_ColorOverlayBase):
    """Editor de color EN VIVO del panel de color. Refleja cada cambio en el color
    primario/secundario del panel SIN repintar la herramienta en vivo; lleva los
    cuadros primario/secundario (invertir y restablecer). NO modal: el lienzo sigue
    activo para pintar con el abierto."""

    def __init__(self, panel, active="primary"):
        super().__init__(panel.main_window)
        self._live = True
        self._panel = panel
        self._active = active if active in ("primary", "secondary") else "primary"
        self._show_alpha = True
        self._sync = False
        self.setWindowTitle(t("color.dlg.primary"))
        # Estilos de los controles; el fondo/marco lo pone OverlayPanel (frame_qss).
        self.setStyleSheet(
            "QLabel { color: %s; background: transparent; }" % theme.TEXT
            + theme.spinbox_qss()
        )
        self._init_color_state(self._panel_color(self._active))
        self._build_editor()

    def sync_picked(self, which):
        """Refleja un color capturado DESDE FUERA (el cuentagotas) en un editor ya
        abierto: recarga ambos cuadros del panel y deja en edicion el cuadro
        capturado (primario con clic izquierdo, secundario con derecho), con la
        rueda/los campos cargados con ese color. Lo llama on_color_picked del
        panel de color."""
        self._select_target(which)
        self._refresh_boxes()


class ImagoColorPickerOverlay(_ColorOverlayBase):
    """Selector de color para los sitios que necesitan UN color concreto (color de
    efecto, fondo de IA...): mismo aspecto que el editor + previsualizacion y
    botones Aceptar/Cancelar, pero tambien overlay HIJO del lienzo (Wayland-safe).
    Al aceptar llama on_accept(color) y se cierra; al cancelar solo se cierra. Lo
    abre imago_pick_color()."""

    def __init__(self, initial, main_window, title="", show_alpha=False, on_accept=None):
        super().__init__(main_window)
        self._live = False
        self._panel = None
        self._active = "primary"
        self._show_alpha = bool(show_alpha)
        self._sync = False
        self._on_accept = on_accept
        self.setWindowTitle(title or t("color.dlg.primary"))
        self.setStyleSheet(
            "QLabel { color: %s; background: transparent; }" % theme.TEXT
            + theme.spinbox_qss()
            + theme.dialog_button_plain_qss()
        )
        self._init_color_state(initial)
        self._build_editor()

    def accept(self):
        # Confirma: entrega el color por callback y cierra el overlay.
        if self._on_accept is not None:
            self._on_accept(self.selected_color())
        super().accept()
