from i18n import t
# adjustments.py
"""Ajustes de imagen (menú "Ajustes").

Contiene un diálogo base reutilizable (AdjustmentDialog) que se encarga de toda
la fontanería común: capturar la capa original, mostrar vista previa en vivo
mientras se mueven los controles, respetar la selección activa, y confirmar como
UN solo paso de deshacer (o restaurar al cancelar). Cada ajuste concreto solo
implementa qué controles tiene y cómo transforma los píxeles (con numpy).
"""

import math
import numpy as np
from PySide6.QtCore import Qt, QTimer, Signal, QPointF, QRectF, QEvent, QObject
from PySide6.QtGui import QImage, QPainter, QPen, QColor, QPainterPath
from PySide6.QtWidgets import (QVBoxLayout, QHBoxLayout, QLabel, QSlider,
                               QSpinBox, QPushButton, QWidget, QComboBox,
                               QAbstractButton, QAbstractSlider,
                               QAbstractSpinBox)

from tools.commands import PaintCommand
from widgets.overlay_panel import OverlayPanel
import theme


def _panel_qss():
    """Estilo base de los paneles de Ajustes/Efectos (fondo, etiquetas y
    botones). Sale de tokens para responder al tema (claro/oscuro)."""
    return f"""
QDialog {{ background-color: {theme.BG_WINDOW}; }}
QLabel {{ color: {theme.TEXT}; font-family: 'Segoe UI'; font-size: 12px; }}
QPushButton {{
    background-color: {theme.BG_BUTTON}; color: {theme.TEXT};
    border: 1px solid {theme.BORDER}; border-radius: 4px; padding: 5px 14px;
}}
QPushButton:hover {{ background-color: {theme.BG_HOVER_RAISED}; border: 1px solid {theme.ACCENT}; }}
QPushButton:pressed {{ background-color: {theme.ACCENT_DARK}; }}
"""


# --------------------------------------------------------- QImage <-> numpy
def qimage_to_array(qimg):
    qimg = qimg.convertToFormat(QImage.Format_RGBA8888)
    W, H = qimg.width(), qimg.height()
    bpl = qimg.bytesPerLine()
    buf = np.frombuffer(qimg.constBits(), np.uint8).reshape(H, bpl)
    return buf[:, :W * 4].reshape(H, W, 4).copy()


def array_to_qimage(arr, W, H):
    arr = np.ascontiguousarray(arr)
    return QImage(arr.data, W, H, 4 * W, QImage.Format_RGBA8888).copy()


class _ComputeSnapshot:
    """Estado inmutable y sin widgets que un ``compute`` puede leer en worker."""

    def __init__(self, values, checks, combos, colors, attrs):
        self._values = values
        self._check_values = checks
        self._combo_values = combos
        self._color_values = colors
        for name, value in attrs.items():
            setattr(self, name, value)

    def val(self, key):
        return self._values[key]

    def checked(self, key):
        return self._check_values[key]

    def combo_index(self, key):
        return self._combo_values[key]

    def color(self, key):
        return self._color_values[key]


_NO_WORKER_VALUE = object()


def _worker_safe_value(value):
    """Copia contenedores de datos simples y rechaza cualquier objeto Qt."""
    if isinstance(value, QObject):
        return _NO_WORKER_VALUE
    if value is None or isinstance(value, (bool, int, float, str, bytes, np.ndarray)):
        return value
    if isinstance(value, tuple):
        items = tuple(_worker_safe_value(item) for item in value)
        return (_NO_WORKER_VALUE if any(item is _NO_WORKER_VALUE for item in items)
                else items)
    if isinstance(value, list):
        items = [_worker_safe_value(item) for item in value]
        return (_NO_WORKER_VALUE if any(item is _NO_WORKER_VALUE for item in items)
                else items)
    if isinstance(value, dict):
        items = {key: _worker_safe_value(item) for key, item in value.items()}
        return (_NO_WORKER_VALUE
                if any(item is _NO_WORKER_VALUE for item in items.values())
                else items)
    return _NO_WORKER_VALUE


# ------------------------------------------------------------- diálogo base
class AdjustmentDialog(OverlayPanel):
    """Base de todos los ajustes. Las subclases definen `title`, `build_controls`
    (añadir filas de control con add_slider_row) y `compute(arr)` (transformar el
    array RGBA y devolverlo).

    Es un PANEL OVERLAY (QWidget hijo de la ventana, no una ventana del SO ni un
    diálogo modal): así el compositor no atenúa la principal y la preview se ve
    bien en cualquier SO. Ver migrar_dialogos_a_overlay.md."""

    title = t("fx.t.adjustment")
    heavy = False   # True en filtros pesados -> preview con debounce (al soltar)
    preview_downscale = False  # True -> previsualiza sobre version reducida (rapido)
    PREVIEW_MAX = 1200         # lado mayor de la version reducida para el preview

    def __init__(self, main_window, destino=None):
        super().__init__(main_window)
        self.main_window = main_window
        from models.destino_edicion import DestinoCapa
        if destino is None:
            canvas = main_window.get_current_canvas()
            if canvas is not None and canvas.get_active_layer() is not None:
                destino = DestinoCapa(canvas, canvas.active_layer_index)
        self._destino = destino
        self.canvas = destino.canvas if destino is not None else None
        self.setWindowTitle(self.title)
        self.setStyleSheet(_panel_qss() + theme.slider_qss() + theme.spinbox_qss())

        self._sliders = {}
        self._defaults = {}
        self._checks = {}
        self._check_defaults = {}
        self._combos = {}
        self._combo_defaults = {}
        self._colors = {}
        self._row_labels = []   # etiquetas de las filas de slider (para igualar su ancho)
        self._valid = bool(self._destino) and self._destino.indice_actual(
            self.main_window, exigir_activo=True) is not None
        self._cur_scale = 1.0
        self._orig_small = None
        self._scale = 1.0
        self._final_handle = None

        # Debounce de la vista previa para filtros pesados (efectos)
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(160)
        self._preview_timer.timeout.connect(self._update_preview)

        if self._valid:
            self._layer_index = self._destino.indice_actual(
                self.main_window, exigir_activo=True)
            self._layer = self._destino.layer
            img = self._layer.image
            self._full_before = QImage(img)
            self._patch_offset = (0, 0)
            
            if self.canvas.selection is not None and not self.canvas.selection.isEmpty():
                rect = self.canvas.selection.boundingRect().toAlignedRect().intersected(img.rect())
                if rect.isValid() and not rect.isEmpty():
                    img = img.copy(rect)
                    self._patch_offset = (rect.x(), rect.y())
                    
            self._before = QImage(img)
            self._orig = qimage_to_array(img)
            self._H, self._W = self._orig.shape[0], self._orig.shape[1]
            if self.preview_downscale:
                longest = max(self._W, self._H)
                if longest > self.PREVIEW_MAX:
                    sf = self.PREVIEW_MAX / float(longest)
                    ws = max(1, int(round(self._W * sf)))
                    hs = max(1, int(round(self._H * sf)))
                    small_q = self._before.scaled(
                        ws, hs, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
                    self._orig_small = qimage_to_array(small_q)
                    self._H_small = self._orig_small.shape[0]
                    self._W_small = self._orig_small.shape[1]
                    self._scale = self._W_small / float(self._W)

        root = self.body_layout
        self.controls_layout = QVBoxLayout()
        self.controls_layout.setSpacing(8)
        root.addLayout(self.controls_layout)

        self.build_controls()
        self._equalize_labels()

        root.addSpacing(6)
        btns = QHBoxLayout()
        self._final_status = QLabel(t("fx.full.working"))
        self._final_status.setVisible(False)
        btns.addWidget(self._final_status)
        self._reset_btn = QPushButton(t("common.reset"))
        self._reset_btn.clicked.connect(self.reset)
        btns.addWidget(self._reset_btn)
        btns.addStretch()
        self._ok_btn = QPushButton(t("btn.accept", default="Aceptar"))
        self._ok_btn.clicked.connect(self.accept)
        self._cancel_btn = QPushButton(t("btn.cancel", default="Cancelar"))
        self._cancel_btn.clicked.connect(self.reject)
        btns.addWidget(self._ok_btn)
        btns.addWidget(self._cancel_btn)
        root.addLayout(btns)

        self.setMinimumWidth(380)
        self._update_preview()   # estado inicial (sin cambios)

        # Mientras el overlay está abierto, la preview POSEE la capa: se bloquea
        # pintar sobre el lienzo (chocaría) dejando pasar zoom/pan para inspeccionar
        # (punto de diseño 1). El filtro se retira al cerrarse el panel.
        if self._valid and self.canvas is not None:
            self.canvas.installEventFilter(self)
            self.closed.connect(self._unlock_canvas)

    # ---- API para las subclases ----
    def add_slider_row(self, key, label, minv, maxv, default, layout=None, slider_min=220):
        target = layout if layout is not None else self.controls_layout
        row = QHBoxLayout()
        lbl = QLabel(label)
        lbl.setMinimumWidth(80)
        row.addWidget(lbl)
        self._row_labels.append(lbl)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(minv, maxv)
        slider.setValue(default)
        slider.setMinimumWidth(slider_min)
        spin = QSpinBox()
        spin.setRange(minv, maxv)
        spin.setValue(default)
        slider.valueChanged.connect(spin.setValue)
        spin.valueChanged.connect(slider.setValue)
        slider.valueChanged.connect(lambda _=None: self._request_preview())
        row.addWidget(slider)
        row.addWidget(spin)
        target.addLayout(row)
        self._sliders[key] = slider
        self._defaults[key] = default
        return slider

    def add_center_picker(self, key_x="cx", key_y="cy", default=50):
        """Selector de centro del efecto: miniatura con tirador de 4 puntas a la
        izquierda y los sliders Centro X / Centro Y a la derecha, sincronizados en
        ambos sentidos (arrastrar el tirador mueve los sliders y viceversa)."""
        from widgets.effect_controls import CenterPicker
        row = QHBoxLayout()
        picker = None
        if self._valid:
            picker = CenterPicker(self._before)
            row.addWidget(picker, 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        sx = self.add_slider_row(key_x, t("fx.l.center_x"), 0, 100, default, layout=col, slider_min=110)
        sy = self.add_slider_row(key_y, t("fx.l.center_y"), 0, 100, default, layout=col, slider_min=110)
        col.addStretch()
        row.addLayout(col, 1)
        self.controls_layout.addLayout(row)
        if picker is not None:
            picker.setCenter(default, default)
            picker.centerChanged.connect(
                lambda x, y: (self._sliders[key_x].setValue(int(round(x))),
                              self._sliders[key_y].setValue(int(round(y)))))
            sync = lambda _=None: picker.setCenter(self._sliders[key_x].value(),
                                                   self._sliders[key_y].value())
            sx.valueChanged.connect(sync)
            sy.valueChanged.connect(sync)

    def add_angle_row(self, key, label, minv, maxv, default):
        """Fila de ángulo: slider + dial circular con manilla, sincronizados."""
        from widgets.effect_controls import AngleDial
        row = QHBoxLayout()
        left = QVBoxLayout()
        s = self.add_slider_row(key, label, minv, maxv, default, layout=left, slider_min=170)
        left.addStretch()
        row.addLayout(left, 1)
        dial = AngleDial()
        row.addWidget(dial, 0, Qt.AlignmentFlag.AlignVCenter)
        self.controls_layout.addLayout(row)
        dial.setAngle(default)
        dial.angleChanged.connect(lambda a: self._sliders[key].setValue(int(round(a))))
        s.valueChanged.connect(lambda _=None: dial.setAngle(self._sliders[key].value()))
        return s

    def _equalize_labels(self):
        """Iguala el ancho de TODAS las etiquetas de las filas de slider al de la
        más larga, para que los deslizadores empiecen a la misma altura y midan lo
        mismo (con cualquier número de filas y longitudes de texto)."""
        if not self._row_labels:
            return
        w = max([80] + [lbl.sizeHint().width() for lbl in self._row_labels])
        for lbl in self._row_labels:
            lbl.setFixedWidth(w)

    def add_checkbox_row(self, key, label, default=False):
        from PySide6.QtWidgets import QCheckBox
        row = QHBoxLayout()
        chk = QCheckBox(label)
        chk.setChecked(default)
        chk.toggled.connect(lambda _=None: self._request_preview())
        row.addWidget(chk)
        row.addStretch()
        self.controls_layout.addLayout(row)
        self._checks[key] = chk
        self._check_defaults[key] = default
        return chk

    def add_combo_row(self, key, label, items, default=0):
        """Fila con un desplegable (QComboBox). `items` es una lista de textos;
        se lee con combo_index(key)."""
        from PySide6.QtWidgets import QComboBox
        row = QHBoxLayout()
        lbl = QLabel(label)
        lbl.setMinimumWidth(80)
        row.addWidget(lbl)
        self._row_labels.append(lbl)
        combo = QComboBox()
        combo.addItems(items)
        combo.setCurrentIndex(default)
        combo.setStyleSheet(theme.combobox_qss())
        combo.currentIndexChanged.connect(lambda _=None: self._request_preview())
        row.addWidget(combo)
        row.addStretch()
        self.controls_layout.addLayout(row)
        self._combos[key] = combo
        self._combo_defaults[key] = default
        return combo

    def add_color_row(self, key, label, default="#000000"):
        """Fila con un botón que muestra y permite elegir un color (selector no
        nativo de Imago, para respetar el tema oscuro+azul en cualquier SO)."""
        from widgets.colors_panel import imago_pick_color
        from PySide6.QtGui import QColor
        row = QHBoxLayout()
        lbl = QLabel(label)
        lbl.setMinimumWidth(80)
        row.addWidget(lbl)
        self._row_labels.append(lbl)
        btn = QPushButton()
        btn.setFixedSize(60, 22)
        self._colors[key] = QColor(default)

        def repaint():
            c = self._colors[key]
            btn.setStyleSheet("background-color: %s; border: 1px solid %s;" % (c.name(), theme.BORDER))

        def pick():
            # El selector es un overlay hijo del lienzo (Wayland-safe) y entrega el
            # color por callback al Aceptar.
            def _apply(c):
                self._colors[key] = c
                repaint()
                self._request_preview()
            imago_pick_color(self._colors[key], self, t("fx.shadow_color"),
                             on_accept=_apply)

        repaint()
        btn.clicked.connect(pick)
        row.addWidget(btn)
        row.addStretch()
        self.controls_layout.addLayout(row)
        return btn

    def checked(self, key):
        return self._checks[key].isChecked()

    def combo_index(self, key):
        return self._combos[key].currentIndex()

    def color(self, key):
        c = self._colors[key]
        return (c.red(), c.green(), c.blue())

    def val(self, key):
        return self._sliders[key].value()

    def build_controls(self):
        pass

    def compute(self, arr):
        return arr

    # ---- fontanería común ----
    def _request_preview(self):
        """En efectos pesados (heavy) recalcula al soltar/parar el control
        (debounce) para no congelar la UI; en el resto, en vivo."""
        if self.heavy:
            self._preview_timer.start()
        else:
            self._update_preview()

    def _indice_destino(self, exigir_activo=True):
        if not self._valid or self._destino is None:
            return None
        return self._destino.indice_actual(
            self.main_window, exigir_revision=True,
            exigir_activo=exigir_activo)

    def _invalidar_destino(self):
        if not self._valid:
            return
        self._valid = False
        self._preview_timer.stop()
        if self._final_handle is not None:
            self._final_handle.cancel()
            self._final_handle = None
        status = getattr(self.main_window, "status_bar", None)
        if status is not None:
            status.showMessage(t("edit.target_changed"), 5000)
        OverlayPanel.reject(self)

    def _update_preview(self, full=False):
        index = self._indice_destino(exigir_activo=True)
        if index is None:
            self._invalidar_destino()
            return
        if (not full) and self._orig_small is not None:
            # Vista previa rapida sobre la version reducida (efectos pesados)
            self._cur_scale = self._scale
            small = self.compute(self._orig_small.copy())
            grad = array_to_qimage(small, self._W_small, self._H_small)
            grad = grad.scaled(self._W, self._H,
                               Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        else:
            self._cur_scale = 1.0
            adjusted = self.compute(self._orig.copy())
            grad = array_to_qimage(adjusted, self._W, self._H)
        result = self.canvas.composite_selection_result(self._full_before, grad, self._patch_offset)
        self._layer.image = result
        self._layer_index = index
        self._destino.actualizar_revision()
        self.canvas.update()

    def reset(self):
        for key, slider in self._sliders.items():
            slider.setValue(self._defaults[key])
        for key, chk in self._checks.items():
            chk.setChecked(self._check_defaults[key])
        for key, combo in self._combos.items():
            combo.setCurrentIndex(self._combo_defaults[key])

    def _restore(self):
        index = self._indice_destino(exigir_activo=False)
        if index is None:
            return False
        self._layer.image = QImage(self._full_before)
        self._layer_index = index
        self._destino.actualizar_revision()
        self.canvas.update()
        return True

    def _compute_snapshot(self):
        """Captura en GUI solo datos Python/NumPy; ningun widget viaja al hilo."""
        attrs = {}
        for name, value in self.__dict__.items():
            if not name.startswith("_"):
                continue
            safe = _worker_safe_value(value)
            if safe is not _NO_WORKER_VALUE:
                attrs[name] = safe
        attrs["_cur_scale"] = 1.0
        return _ComputeSnapshot(
            {key: slider.value() for key, slider in self._sliders.items()},
            {key: check.isChecked() for key, check in self._checks.items()},
            {key: combo.currentIndex() for key, combo in self._combos.items()},
            {key: (color.red(), color.green(), color.blue())
             for key, color in self._colors.items()},
            attrs)

    def _set_final_busy(self, busy):
        """Bloquea parametros durante el calculo pero conserva Cancelar y la X."""
        self._final_status.setVisible(bool(busy))
        interactivos = (QAbstractButton, QAbstractSlider,
                        QAbstractSpinBox, QComboBox)
        for widget in self._body.findChildren(QWidget):
            if isinstance(widget, interactivos):
                widget.setEnabled(not busy)
        self._cancel_btn.setEnabled(True)
        self.title_bar.btn_close.setEnabled(True)

    def _get_compute_runner(self):
        runner = getattr(self.main_window, "_adjustment_runner", None)
        if runner is None:
            from ai.runner import InferenceRunner
            runner = InferenceRunner(self.main_window, max_threads=1)
            self.main_window._adjustment_runner = runner
        return runner

    def _commit_final(self, grad):
        """Aplica en GUI el QImage ya calculado y crea un unico paso de undo."""
        index = self._indice_destino(exigir_activo=True)
        if index is None:
            self._invalidar_destino()
            return False
        result = self.canvas.composite_selection_result(
            self._full_before, grad, self._patch_offset)
        self._layer.image = result
        self._layer_index = index
        self._destino.actualizar_revision()
        self.canvas.update()
        after = QImage(self._layer.image)
        if after != self._full_before:
            cmd = PaintCommand(
                self.canvas, index, self._full_before, after,
                self.title, tool_id="adjust")
            hist_icon = getattr(self, "history_icon", None)
            if hist_icon:
                cmd.history_icon = hist_icon
            self.canvas.undo_stack.push(cmd)
        OverlayPanel.accept(self)
        return True

    def _accept_in_worker(self):
        contexto = self._compute_snapshot()
        origen = self._orig
        compute = type(self).compute
        ancho, alto = self._W, self._H
        self._set_final_busy(True)
        status = getattr(self.main_window, "status_bar", None)
        if status is not None:
            status.showMessage(t("fx.full.working"))

        def work(_report, token):
            if token.cancelled:
                return None
            adjusted = compute(contexto, origen.copy())
            if token.cancelled:
                return None
            return array_to_qimage(adjusted, ancho, alto)

        def done(grad):
            self._final_handle = None
            self._set_final_busy(False)
            if grad is not None:
                applied = self._commit_final(grad)
                if applied and status is not None:
                    status.showMessage(t("fx.full.done"), 3000)

        def error(message):
            self._final_handle = None
            self._set_final_busy(False)
            if status is not None:
                status.showMessage(t("fx.full.error", err=message), 5000)
            from widgets.custom_titlebar import imago_warning
            imago_warning(self.main_window, self.title,
                          t("fx.full.error", err=message))

        self._final_handle = self._get_compute_runner().submit(
            work, on_done=done, on_error=error)

    def accept(self):
        self._preview_timer.stop()
        if self._final_handle is not None:
            return
        if self._valid:
            if self.heavy:
                self._accept_in_worker()
                return
            self._update_preview(full=True)
            index = self._indice_destino(exigir_activo=True)
            if index is None:
                self._invalidar_destino()
                return
            after = QImage(self._layer.image)
            if after != self._full_before:
                cmd = PaintCommand(
                    self.canvas, index, self._full_before, after,
                    self.title, tool_id="adjust")
                # Los efectos de IA con overlay (bokeh, anaglifo, desenfoque de
                # fondo) marcan su propio icono al abrirse; así el Historial
                # muestra el icono del efecto y no el genérico de Ajustes.
                hist_icon = getattr(self, "history_icon", None)
                if hist_icon:
                    cmd.history_icon = hist_icon
                self.canvas.undo_stack.push(cmd)
        super().accept()

    def reject(self):
        self._preview_timer.stop()
        if self._final_handle is not None:
            self._final_handle.cancel()
            self._final_handle = None
        self._restore()
        super().reject()

    # ---- bloqueo del pintado sobre el lienzo mientras el overlay está abierto ----
    def eventFilter(self, obj, event):
        """Bloquea SOLO el pintado (botón/arrastre IZQUIERDO y doble clic) sobre el
        lienzo. Deja pasar el botón central (pan), la rueda (zoom), el teclado y el
        movimiento sin botón (para que reglas/cursor sigan)."""
        if obj is self.canvas:
            et = event.type()
            # Modo "cuentagotas": lo usan los ajustes que toman un color del lienzo
            # (p. ej. Balance de blancos). Con él activo, el clic izquierdo TOMA la
            # muestra (via _on_canvas_pick de la subclase) en vez de bloquearse.
            if getattr(self, "_pick_active", False) and \
                    et == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                self._on_canvas_pick(event)
                return True
            if et in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease,
                      QEvent.MouseButtonDblClick):
                if event.button() == Qt.LeftButton:
                    return True
            elif et == QEvent.MouseMove:
                if event.buttons() & Qt.LeftButton:
                    return True
        return super().eventFilter(obj, event)

    def _unlock_canvas(self):
        """Restaura la interacción del lienzo al cerrarse el overlay."""
        if self.canvas is not None:
            self.canvas.removeEventFilter(self)


# ----------------------------------------------------------- ajustes concretos
def apply_brightness_contrast(arr, brightness, contrast):
    """brightness y contrast en [-100, 100]. Modifica RGB, conserva alfa."""
    rgb = arr[..., :3].astype(np.float32)
    c = contrast / 100.0 * 255.0
    factor = (259.0 * (c + 255.0)) / (255.0 * (259.0 - c))
    rgb = (rgb - 128.0) * factor + 128.0
    rgb = rgb + brightness / 100.0 * 127.0
    arr[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    return arr


class BrightnessContrastDialog(AdjustmentDialog):
    title = t("fx.t.brightness_contrast")

    def build_controls(self):
        self.add_slider_row("brightness", t("adj.bright"), -100, 100, 0)
        self.add_slider_row("contrast", t("adj.contrast"), -100, 100, 0)

    def compute(self, arr):
        return apply_brightness_contrast(arr, self.val("brightness"), self.val("contrast"))


# ----------------------------------------------------------- RGB <-> HSV (vectorizado)
def rgb_to_hsv(rgb):
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    df = mx - mn
    h = np.zeros_like(mx)
    mask = df > 1e-6
    idx = mask & (mx == r); h[idx] = ((g[idx] - b[idx]) / df[idx]) % 6
    idx = mask & (mx == g); h[idx] = ((b[idx] - r[idx]) / df[idx]) + 2
    idx = mask & (mx == b); h[idx] = ((r[idx] - g[idx]) / df[idx]) + 4
    h = (h / 6.0) % 1.0
    s = np.where(mx > 1e-6, df / np.maximum(mx, 1e-12), 0.0)
    return h, s, mx


def hsv_to_rgb(h, s, v):
    i = np.floor(h * 6.0)
    f = h * 6.0 - i
    p = v * (1 - s); q = v * (1 - f * s); t = v * (1 - (1 - f) * s)
    i = i.astype(int) % 6
    r = np.choose(i, [v, q, p, p, t, v])
    g = np.choose(i, [t, v, v, q, p, p])
    b = np.choose(i, [p, p, t, v, v, q])
    return np.stack([r, g, b], axis=-1)


# ----------------------------------------------------------- funciones de ajuste
def invert(arr):
    arr[..., :3] = 255 - arr[..., :3]
    return arr


def grayscale(arr):
    rgb = arr[..., :3].astype(np.float32)
    lum = rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114
    lum = np.clip(lum, 0, 255).astype(np.uint8)
    arr[..., 0] = arr[..., 1] = arr[..., 2] = lum
    return arr


def apply_gamma(arr, val):
    """val en [-100,100]; 0 = neutro. Positivo aclara los medios tonos."""
    g = 2.0 ** (-val / 100.0)
    rgb = arr[..., :3].astype(np.float32) / 255.0
    arr[..., :3] = np.clip(np.power(rgb, g) * 255.0, 0, 255).astype(np.uint8)
    return arr


def apply_posterize(arr, levels):
    levels = max(2, int(levels))
    rgb = arr[..., :3].astype(np.float32)
    q = np.round(rgb / 255.0 * (levels - 1)) / (levels - 1) * 255.0
    arr[..., :3] = np.clip(q, 0, 255).astype(np.uint8)
    return arr


def apply_hue_sat(arr, hue, sat, light):
    rgb = arr[..., :3].astype(np.float32) / 255.0
    h, s, v = rgb_to_hsv(rgb)
    h = (h + hue / 360.0) % 1.0
    s = np.clip(s * (1.0 + sat / 100.0), 0, 1)
    v = np.clip(v * (1.0 + light / 100.0), 0, 1)
    arr[..., :3] = np.clip(hsv_to_rgb(h, s, v) * 255.0, 0, 255).astype(np.uint8)
    return arr


# ----------------------------------------------------------- ajuste instantáneo (sin diálogo)
def apply_instant(main_window, func, title):
    """Aplica un ajuste sin parámetros directamente (Invertir, B/N…),
    respetando la selección y como un solo paso de deshacer."""
    canvas = main_window.get_current_canvas()
    if not canvas or canvas.get_active_layer() is None:
        return
    img = canvas.get_active_layer()
    before = QImage(img)
    out = func(qimage_to_array(img))
    qimg = array_to_qimage(out, img.width(), img.height())
    result = canvas.composite_selection_result(before, qimg)
    idx = canvas.active_layer_index
    canvas.layers[idx].image = result
    canvas.update()
    after = QImage(result)
    if after != before:
        canvas.undo_stack.push(PaintCommand(canvas, idx, before, after, title, tool_id="adjust"))


# ----------------------------------------------------------- diálogos concretos
class HueSaturationDialog(AdjustmentDialog):
    title = t("fx.t.hue_sat")
    preview_downscale = True   # roundtrip HSV: previa en vivo sobre versión reducida

    def build_controls(self):
        self.add_slider_row("hue", t("adj.hue"), -180, 180, 0)
        self.add_slider_row("sat", t("adj.sat"), -100, 100, 0)
        self.add_slider_row("light", t("adj.lightness"), -100, 100, 0)

    def compute(self, arr):
        return apply_hue_sat(arr, self.val("hue"), self.val("sat"), self.val("light"))


class GammaDialog(AdjustmentDialog):
    title = t("fx.t.gamma")

    def build_controls(self):
        self.add_slider_row("gamma", t("fx.l.gamma"), -100, 100, 0)

    def compute(self, arr):
        return apply_gamma(arr, self.val("gamma"))


class PosterizeDialog(AdjustmentDialog):
    title = t("fx.t.posterize")

    def build_controls(self):
        self.add_slider_row("levels", t("fx.l.levels"), 2, 32, 8)

    def compute(self, arr):
        return apply_posterize(arr, self.val("levels"))


# ----------------------------------------------------------- Curvas
def _build_monotone_lut(points):
    """Tabla de mapeo 0..255 (uint8) construida por una spline cúbica de Hermite
    MONÓTONA (Fritsch–Carlson) a través de los puntos de control (entrada, salida).
    Monótona = no oscila ni "se pasa de rosca" entre puntos."""
    pts = sorted(points, key=lambda p: p[0])
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    n = len(pts)
    lut = np.empty(256, dtype=np.float64)
    if n == 1:
        lut[:] = ys[0]
        return np.clip(lut, 0, 255).astype(np.uint8)

    # Pendiente de cada segmento y tangentes en los nodos
    h = [xs[i + 1] - xs[i] for i in range(n - 1)]
    delta = [((ys[i + 1] - ys[i]) / h[i]) if h[i] > 0 else 0.0 for i in range(n - 1)]
    m = [0.0] * n
    m[0] = delta[0]
    m[n - 1] = delta[-1]
    for i in range(1, n - 1):
        m[i] = 0.0 if delta[i - 1] * delta[i] <= 0 else (delta[i - 1] + delta[i]) / 2.0

    # Corrección de monotonicidad (Fritsch–Carlson)
    for i in range(n - 1):
        if delta[i] == 0:
            m[i] = m[i + 1] = 0.0
        else:
            a = m[i] / delta[i]
            b = m[i + 1] / delta[i]
            s = a * a + b * b
            if s > 9.0:
                t = 3.0 / math.sqrt(s)
                m[i] = t * a * delta[i]
                m[i + 1] = t * b * delta[i]

    # Evaluar la spline para cada entrada entera 0..255
    seg = 0
    for x in range(256):
        if x <= xs[0]:
            lut[x] = ys[0]
            continue
        if x >= xs[-1]:
            lut[x] = ys[-1]
            continue
        while seg < n - 2 and x > xs[seg + 1]:
            seg += 1
        hh = xs[seg + 1] - xs[seg]
        t = (x - xs[seg]) / hh
        t2 = t * t
        t3 = t2 * t
        h00 = 2 * t3 - 3 * t2 + 1
        h10 = t3 - 2 * t2 + t
        h01 = -2 * t3 + 3 * t2
        h11 = t3 - t2
        lut[x] = (h00 * ys[seg] + h10 * hh * m[seg]
                  + h01 * ys[seg + 1] + h11 * hh * m[seg + 1])
    return np.clip(lut, 0, 255).astype(np.uint8)


class CurveEditor(QWidget):
    """Editor interactivo de curva tonal. Una rejilla con una curva editable por
    puntos de control sobre el histograma de la imagen:
    - Clic izquierdo en zona libre: añade un punto y lo arrastra.
    - Clic izquierdo sobre un punto: lo arrastra.
    - Clic derecho sobre un punto interior: lo borra.
    - Los extremos (entrada 0 y 255) solo se mueven en vertical.
    La unión es una spline cúbica monótona. Emite curveChanged al editar; lut()
    devuelve la tabla de mapeo 0..255."""

    curveChanged = Signal()

    PAD = 8
    HIT = 10   # radio de captura del ratón a un punto (px)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(300, 260)
        self.setMouseTracking(True)
        self._points = [[0.0, 0.0], [255.0, 255.0]]   # (entrada, salida) 0..255
        self._drag = None
        self._hist = None        # histograma normalizado (256,) en 0..1
        self._lut_cache = None

    # ---- datos ----
    def set_histogram(self, hist):
        h = np.asarray(hist, dtype=np.float64)
        m = h.max()
        self._hist = (h / m) if m > 0 else None
        self.update()

    def reset(self):
        self._points = [[0.0, 0.0], [255.0, 255.0]]
        self._drag = None
        self._lut_cache = None
        self.update()

    def lut(self):
        if self._lut_cache is None:
            self._lut_cache = _build_monotone_lut(self._points)
        return self._lut_cache

    # ---- mapeo datos <-> pantalla ----
    def _plot_rect(self):
        return QRectF(self.PAD, self.PAD,
                      self.width() - 2 * self.PAD, self.height() - 2 * self.PAD)

    def _to_screen(self, x, y):
        r = self._plot_rect()
        return QPointF(r.left() + (x / 255.0) * r.width(),
                       r.bottom() - (y / 255.0) * r.height())

    def _to_data(self, sx, sy):
        r = self._plot_rect()
        x = (sx - r.left()) / r.width() * 255.0
        y = (r.bottom() - sy) / r.height() * 255.0
        return (max(0.0, min(255.0, x)), max(0.0, min(255.0, y)))

    # ---- ratón ----
    def _point_at(self, sx, sy):
        for i, (x, y) in enumerate(self._points):
            sp = self._to_screen(x, y)
            if abs(sp.x() - sx) <= self.HIT and abs(sp.y() - sy) <= self.HIT:
                return i
        return None

    def _insert_point(self, x, y):
        x = max(1.0, min(254.0, x))
        i = 0
        while i < len(self._points) and self._points[i][0] < x:
            i += 1
        if i < len(self._points) and abs(self._points[i][0] - x) < 1.0:
            return i
        self._points.insert(i, [x, y])
        return i

    def mousePressEvent(self, e):
        sx, sy = e.position().x(), e.position().y()
        idx = self._point_at(sx, sy)
        if e.button() == Qt.MouseButton.RightButton:
            if idx is not None and 0 < idx < len(self._points) - 1:
                del self._points[idx]
                self._changed()
            return
        if e.button() != Qt.MouseButton.LeftButton:
            return
        if idx is None:
            x, y = self._to_data(sx, sy)
            idx = self._insert_point(x, y)
        self._drag = idx
        self._changed()

    def mouseMoveEvent(self, e):
        if self._drag is None:
            return
        x, y = self._to_data(e.position().x(), e.position().y())
        i = self._drag
        n = len(self._points)
        if i == 0:
            x = 0.0
        elif i == n - 1:
            x = 255.0
        else:
            x = max(self._points[i - 1][0] + 1.0,
                    min(self._points[i + 1][0] - 1.0, x))
        self._points[i] = [x, y]
        self._changed()

    def mouseReleaseEvent(self, e):
        self._drag = None

    def _changed(self):
        self._lut_cache = None
        self.update()
        self.curveChanged.emit()

    # ---- pintado ----
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = self._plot_rect()
        p.fillRect(self.rect(), QColor(theme.BG_DARK))

        # Histograma de fondo
        if self._hist is not None:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(theme.BORDER))
            bw = max(1.0, r.width() / 256.0)
            for i in range(256):
                bh = float(self._hist[i]) * r.height()
                if bh > 0:
                    x = r.left() + (i / 255.0) * r.width()
                    p.drawRect(QRectF(x, r.bottom() - bh, bw, bh))

        # Rejilla (cuartos) y diagonal de identidad
        grid = QColor(theme.BORDER)
        grid.setAlpha(110)
        p.setPen(QPen(grid, 1))
        for k in range(1, 4):
            gx = r.left() + r.width() * k / 4.0
            gy = r.top() + r.height() * k / 4.0
            p.drawLine(QPointF(gx, r.top()), QPointF(gx, r.bottom()))
            p.drawLine(QPointF(r.left(), gy), QPointF(r.right(), gy))
        p.drawLine(r.bottomLeft(), r.topRight())

        # Marco
        p.setPen(QPen(QColor(theme.BORDER), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(r)

        # Curva (la propia LUT)
        lut = self.lut()
        path = QPainterPath()
        path.moveTo(self._to_screen(0, float(lut[0])))
        for x in range(1, 256):
            path.lineTo(self._to_screen(x, float(lut[x])))
        p.setPen(QPen(QColor(theme.TEXT), 2))
        p.drawPath(path)

        # Puntos de control
        for (x, y) in self._points:
            sp = self._to_screen(x, y)
            p.setPen(QPen(QColor(theme.TEXT), 1.5))
            p.setBrush(QColor(theme.ACCENT))
            p.drawEllipse(sp, 4.5, 4.5)
        p.end()


class CurvesDialog(AdjustmentDialog):
    title = t("adj.curves", default="Curvas")
    preview_downscale = True   # previsualización fluida en imágenes grandes

    def build_controls(self):
        self.curve_editor = CurveEditor()
        if self._valid:
            rgb = self._orig[..., :3].astype(np.float32)
            lum = rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114
            hist = np.bincount(np.clip(lum, 0, 255).astype(np.uint8).ravel(),
                               minlength=256)
            self.curve_editor.set_histogram(hist)
        self.curve_editor.curveChanged.connect(self._request_preview)
        self.controls_layout.addWidget(
            self.curve_editor, alignment=Qt.AlignmentFlag.AlignHCenter)
        hint = QLabel(t("fx.curves.hint"))
        hint.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: 11px;")
        hint.setWordWrap(True)
        self.controls_layout.addWidget(hint)

    def compute(self, arr):
        lut = self.curve_editor.lut()
        arr[..., :3] = lut[arr[..., :3]]
        return arr

    def reset(self):
        self.curve_editor.reset()
        self._request_preview()


# ----------------------------------------------------------- más funciones de ajuste
def apply_levels(arr, in_black, in_white, gamma_val, out_black, out_white):
    rgb = arr[..., :3].astype(np.float32)
    in_white = max(in_white, in_black + 1)
    rgb = np.clip((rgb - in_black) / (in_white - in_black), 0, 1)
    g = 2.0 ** (-gamma_val / 100.0)
    rgb = np.power(rgb, g) * (out_white - out_black) + out_black
    arr[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    return arr


def apply_exposure(arr, ev):
    """ev en [-100,100] -> factor 2^(ev/50) (±2 pasos)."""
    rgb = arr[..., :3].astype(np.float32) * (2.0 ** (ev / 50.0))
    arr[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    return arr


def apply_color_balance(arr, r, g, b):
    rgb = arr[..., :3].astype(np.float32)
    rgb[..., 0] += r / 100.0 * 127.0
    rgb[..., 1] += g / 100.0 * 127.0
    rgb[..., 2] += b / 100.0 * 127.0
    arr[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    return arr


def apply_temperature(arr, temp):
    """temp en [-100,100]: positivo = cálido (más rojo, menos azul)."""
    rgb = arr[..., :3].astype(np.float32)
    amt = temp / 100.0 * 40.0
    rgb[..., 0] += amt
    rgb[..., 2] -= amt
    arr[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    return arr


def apply_threshold(arr, t):
    rgb = arr[..., :3].astype(np.float32)
    lum = rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114
    v = np.where(lum >= t, 255, 0).astype(np.uint8)
    arr[..., 0] = arr[..., 1] = arr[..., 2] = v
    return arr


def apply_solarize(arr, t):
    rgb = arr[..., :3].copy()
    mask = rgb >= t
    rgb[mask] = 255 - rgb[mask]
    arr[..., :3] = rgb
    return arr


def sepia(arr):
    rgb = arr[..., :3].astype(np.float32)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    arr[..., 0] = np.clip(0.393 * r + 0.769 * g + 0.189 * b, 0, 255).astype(np.uint8)
    arr[..., 1] = np.clip(0.349 * r + 0.686 * g + 0.168 * b, 0, 255).astype(np.uint8)
    arr[..., 2] = np.clip(0.272 * r + 0.534 * g + 0.131 * b, 0, 255).astype(np.uint8)
    return arr


def auto_contrast(arr):
    # Estirado UNIFORME (el mismo para los tres canales): recupera contraste
    # sin alterar el color. El estirado POR CANAL es auto_levels (debajo).
    rgb = arr[..., :3].astype(np.float32)
    lo = float(np.percentile(rgb, 0.5))
    hi = float(np.percentile(rgb, 99.5))
    if hi > lo:
        arr[..., :3] = np.clip((rgb - lo) / (hi - lo) * 255.0, 0, 255).astype(np.uint8)
    return arr


def auto_levels(arr):
    # Estirado POR CANAL (punto negro/blanco independientes en R, G y B):
    # maximiza el rango de cada canal y de paso corrige dominantes fuertes.
    rgb = arr[..., :3].astype(np.float32)
    for c in range(3):
        ch = rgb[..., c]
        lo = np.percentile(ch, 0.5)
        hi = np.percentile(ch, 99.5)
        if hi > lo:
            rgb[..., c] = np.clip((ch - lo) / (hi - lo) * 255.0, 0, 255)
    arr[..., :3] = rgb.astype(np.uint8)
    return arr


def auto_color(arr):
    # Neutraliza la dominante de color ("mundo gris"): escala cada canal para
    # que su media iguale la media global, conservando el brillo de la imagen.
    rgb = arr[..., :3].astype(np.float32)
    medias = rgb.reshape(-1, 3).mean(axis=0)
    gris = float(medias.mean())
    if gris > 0:
        for c in range(3):
            if medias[c] > 0:
                rgb[..., c] = np.clip(rgb[..., c] * (gris / medias[c]), 0, 255)
    arr[..., :3] = rgb.astype(np.uint8)
    return arr


def equalize(arr):
    for c in range(3):
        ch = arr[..., c]
        hist, _ = np.histogram(ch, bins=256, range=(0, 256))
        cdf = hist.cumsum().astype(np.float32)
        if cdf[-1] > 0:
            lut = cdf / cdf[-1] * 255.0
            arr[..., c] = lut[ch].astype(np.uint8)
    return arr


# ----------------------------------------------------------- más diálogos
class LevelsDialog(AdjustmentDialog):
    title = t("adj.levels", default="Niveles")

    def build_controls(self):
        self.add_slider_row("in_black", t("fx.l.in_black"), 0, 254, 0)
        self.add_slider_row("in_white", t("fx.l.in_white"), 1, 255, 255)
        self.add_slider_row("gamma", t("fx.l.gamma"), -100, 100, 0)
        self.add_slider_row("out_black", t("fx.l.out_black"), 0, 255, 0)
        self.add_slider_row("out_white", t("fx.l.out_white"), 0, 255, 255)

    def compute(self, arr):
        return apply_levels(arr, self.val("in_black"), self.val("in_white"),
                            self.val("gamma"), self.val("out_black"), self.val("out_white"))


class ExposureDialog(AdjustmentDialog):
    title = t("fx.t.exposure")

    def build_controls(self):
        self.add_slider_row("ev", t("fx.l.exposure"), -100, 100, 0)

    def compute(self, arr):
        return apply_exposure(arr, self.val("ev"))


class ColorBalanceDialog(AdjustmentDialog):
    title = t("fx.t.color_balance")

    def build_controls(self):
        self.add_slider_row("r", t("fx.l.red"), -100, 100, 0)
        self.add_slider_row("g", t("fx.l.green"), -100, 100, 0)
        self.add_slider_row("b", t("fx.l.blue"), -100, 100, 0)

    def compute(self, arr):
        return apply_color_balance(arr, self.val("r"), self.val("g"), self.val("b"))


class TemperatureDialog(AdjustmentDialog):
    title = t("fx.t.color_temp")

    def build_controls(self):
        self.add_slider_row("temp", t("fx.l.temperature"), -100, 100, 0)

    def compute(self, arr):
        return apply_temperature(arr, self.val("temp"))


class ThresholdDialog(AdjustmentDialog):
    title = t("fx.t.threshold")

    def build_controls(self):
        self.add_slider_row("t", t("fx.l.threshold"), 0, 255, 128)

    def compute(self, arr):
        return apply_threshold(arr, self.val("t"))


class SolarizeDialog(AdjustmentDialog):
    title = t("fx.t.solarize")

    def build_controls(self):
        self.add_slider_row("t", t("fx.l.threshold"), 0, 255, 128)

    def compute(self, arr):
        return apply_solarize(arr, self.val("t"))


# ============================================================ EFECTOS (scipy)
# Filtros espaciales con scipy.ndimage. Import perezoso: si faltara scipy, solo
# fallarian los efectos, no el resto de Ajustes ni la app. Operan sobre los
# canales RGB y conservan el alfa. La seleccion (recorte) la aplica el dialogo.

def _ndi():
    from scipy import ndimage as ndi
    return ndi


def apply_gaussian_blur(arr, radius, perceptual=False):
    """Desenfoque gaussiano de 'radius' pixeles (sigma)."""
    if radius <= 0:
        return arr
    ndi = _ndi()
    rgb = arr[..., :3].astype(np.float32)
    if perceptual:
        rgb = np.power(rgb / 255.0, 2.2)
    rgb = ndi.gaussian_filter(rgb, sigma=(radius, radius, 0))
    if perceptual:
        rgb = np.power(np.clip(rgb, 0, 1), 1.0 / 2.2) * 255.0
    arr[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    return arr


def apply_sharpen(arr, radius, amount):
    """Enfoque por mascara de desenfoque (unsharp): original + amount*(orig-blur)."""
    if amount <= 0:
        return arr
    ndi = _ndi()
    r = max(0.1, float(radius))
    rgb = arr[..., :3].astype(np.float32)
    blur = ndi.gaussian_filter(rgb, sigma=(r, r, 0))
    rgb = rgb + (amount / 100.0) * (rgb - blur)
    arr[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    return arr


def apply_edge_enhance(arr, intensity):
    """Realce de bordes (laplaciano): nitido = f - k*laplace(f), por canal."""
    if intensity <= 0:
        return arr
    ndi = _ndi()
    k = intensity / 100.0
    rgb = arr[..., :3].astype(np.float32)
    out = rgb.copy()
    for c in range(3):
        out[..., c] = rgb[..., c] - k * ndi.laplace(rgb[..., c])
    arr[..., :3] = np.clip(out, 0, 255).astype(np.uint8)
    return arr


def apply_find_edges(arr, intensity):
    """Hallar bordes: magnitud del gradiente Sobel por canal (bordes claros
    sobre fondo oscuro)."""
    ndi = _ndi()
    k = (intensity / 100.0) / 4.0   # el Sobel amplifica ~x4; lo normalizamos
    rgb = arr[..., :3].astype(np.float32)
    out = np.zeros_like(rgb)
    for c in range(3):
        gx = ndi.sobel(rgb[..., c], axis=1)
        gy = ndi.sobel(rgb[..., c], axis=0)
        out[..., c] = np.hypot(gx, gy) * k
    arr[..., :3] = np.clip(out, 0, 255).astype(np.uint8)
    return arr


def apply_emboss(arr, angle, intensity, color=False):
    """Relieve direccional. 'angle' = dirección de la luz (-180..180); 'intensity'
    = fuerza. Dos modos:
    - color=False: BAJORRELIEVE GRIS clásico (gris + realce direccional).
    - color=True: relieve que CONSERVA la foto a color, añadiéndole profundidad 3D
      direccional (estilo Paint.NET)."""
    ndi = _ndi()
    rgb = arr[..., :3].astype(np.float32)
    gray = rgb.mean(axis=2)
    a = np.radians(float(angle))
    gx = ndi.sobel(gray, axis=1)
    gy = ndi.sobel(gray, axis=0)
    directional = (gx * np.cos(a) + gy * np.sin(a)) / 4.0   # gradiente hacia la luz
    k = intensity / 100.0
    if color:
        out = rgb + directional[..., None] * k * 1.4        # realce sobre la foto
    else:
        emb = np.clip(128.0 + directional * k, 0, 255)
        out = np.repeat(emb[..., None], 3, axis=2)          # bajorrelieve gris
    arr[..., :3] = np.clip(out, 0, 255).astype(np.uint8)
    return arr


def apply_median(arr, size):
    """Filtro de mediana (quita ruido sal y pimienta). 'size' impar, por canal."""
    if size < 2:
        return arr
    ndi = _ndi()
    if size % 2 == 0:
        size += 1
    for c in range(3):
        arr[..., c] = ndi.median_filter(arr[..., c], size=size)
    return arr


class GaussianBlurDialog(AdjustmentDialog):
    title = t("eff.blur", default="Desenfoque gaussiano")
    heavy = True
    preview_downscale = True

    def build_controls(self):
        self.add_slider_row("radius", t("eff.radius", default=t("fx.l.radius")), 0, 100, 10)
        self.add_checkbox_row("perceptual", t("fx.perceptual_blur"), default=False)

    def compute(self, arr):
        return apply_gaussian_blur(arr, self.val("radius") * self._cur_scale, self.checked("perceptual"))


class SharpenDialog(AdjustmentDialog):
    title = t("fx.t.sharpen")
    heavy = True
    preview_downscale = True

    def build_controls(self):
        self.add_slider_row("radius", t("eff.radius"), 1, 20, 2)
        self.add_slider_row("amount", t("fx.l.amount"), 0, 300, 100)

    def compute(self, arr):
        return apply_sharpen(arr, self.val("radius") * self._cur_scale, self.val("amount"))


class EdgeEnhanceDialog(AdjustmentDialog):
    title = t("fx.t.edge_enhance")
    heavy = True

    def build_controls(self):
        self.add_slider_row("intensity", t("eff.intensity"), 0, 300, 100)

    def compute(self, arr):
        return apply_edge_enhance(arr, self.val("intensity"))


class FindEdgesDialog(AdjustmentDialog):
    title = t("fx.t.find_edges")
    heavy = True

    def build_controls(self):
        self.add_slider_row("intensity", t("eff.intensity"), 50, 400, 100)

    def compute(self, arr):
        return apply_find_edges(arr, self.val("intensity"))


class EmbossDialog(AdjustmentDialog):
    title = t("fx.t.emboss")
    heavy = True

    def build_controls(self):
        self.add_slider_row("angle", t("eff.angle"), -180, 180, 43)
        self.add_slider_row("intensity", t("eff.intensity"), 0, 300, 100)
        self.add_checkbox_row("color", t("fx.keep_color"), False)

    def compute(self, arr):
        return apply_emboss(arr, self.val("angle"), self.val("intensity"),
                            self.checked("color"))


class MedianDialog(AdjustmentDialog):
    title = t("fx.t.median")
    heavy = True
    preview_downscale = True

    def build_controls(self):
        self.add_slider_row("size", t("eff.size"), 1, 15, 3)

    def compute(self, arr):
        return apply_median(arr, max(1, int(round(self.val("size") * self._cur_scale))))


# ===================================================== EFECTOS (lote 2)
def apply_box_blur(arr, radius, perceptual=False):
    """Desenfoque de caja (media uniforme) de radio 'radius'."""
    if radius <= 0:
        return arr
    ndi = _ndi()
    size = int(round(radius)) * 2 + 1
    rgb = arr[..., :3].astype(np.float32)
    if perceptual:
        rgb = np.power(rgb / 255.0, 2.2)
    rgb = ndi.uniform_filter(rgb, size=(size, size, 1))
    if perceptual:
        rgb = np.power(np.clip(rgb, 0, 1), 1.0 / 2.2) * 255.0
    arr[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    return arr


def _motion_kernel(length, angle_deg):
    """Núcleo de línea para desenfoque de movimiento: longitud y ángulo."""
    n = max(1, int(round(length)))
    k = np.zeros((n, n), np.float32)
    c = (n - 1) / 2.0
    a = np.deg2rad(angle_deg)
    dx, dy = np.cos(a), np.sin(a)
    for s in np.linspace(-n / 2.0, n / 2.0, n * 3):
        x = int(round(c + dx * s))
        y = int(round(c + dy * s))
        if 0 <= x < n and 0 <= y < n:
            k[y, x] = 1.0
    s = k.sum()
    return (k / s) if s > 0 else k


def apply_motion_blur(arr, length, angle, perceptual=False):
    """Desenfoque de movimiento (direccional)."""
    if length <= 1:
        return arr
    ndi = _ndi()
    k = _motion_kernel(length, angle)
    rgb = arr[..., :3].astype(np.float32)
    if perceptual:
        rgb = np.power(rgb / 255.0, 2.2)
    for c in range(3):
        rgb[..., c] = ndi.convolve(rgb[..., c], k, mode="reflect")
    if perceptual:
        rgb = np.power(np.clip(rgb, 0, 1), 1.0 / 2.2) * 255.0
    arr[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    return arr


def apply_sharpen_threshold(arr, radius, amount, threshold):
    """Enfoque con umbral: solo realza donde la diferencia supera el umbral
    (evita amplificar ruido y zonas planas)."""
    if amount <= 0:
        return arr
    ndi = _ndi()
    r = max(0.1, float(radius))
    rgb = arr[..., :3].astype(np.float32)
    blur = ndi.gaussian_filter(rgb, sigma=(r, r, 0))
    diff = rgb - blur
    mask = (np.abs(diff) >= float(threshold)).astype(np.float32)
    rgb = rgb + (amount / 100.0) * diff * mask
    arr[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    return arr


def apply_pixelate(arr, block):
    """Pixelar / mosaico: cada bloque de 'block' px toma el color medio."""
    block = max(1, int(round(block)))
    if block <= 1:
        return arr
    h, w = arr.shape[0], arr.shape[1]
    ph, pw = (-h) % block, (-w) % block
    rgb = arr[..., :3].astype(np.float32)
    rgb = np.pad(rgb, ((0, ph), (0, pw), (0, 0)), mode="edge")
    H, W = rgb.shape[0], rgb.shape[1]
    rgb = rgb.reshape(H // block, block, W // block, block, 3).mean(axis=(1, 3))
    rgb = np.repeat(np.repeat(rgb, block, axis=0), block, axis=1)
    arr[..., :3] = np.clip(rgb[:h, :w], 0, 255).astype(np.uint8)
    return arr


def apply_vignette(arr, amount):
    """Viñeta: oscurece progresivamente hacia las esquinas."""
    if amount <= 0:
        return arr
    h, w = arr.shape[0], arr.shape[1]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cy, cx = (h - 1) / 2.0, (w - 1) / 2.0
    d = np.sqrt(((xx - cx) / (w / 2.0)) ** 2 + ((yy - cy) / (h / 2.0)) ** 2)
    k = amount / 100.0
    mask = 1.0 - k * np.clip((d - 0.4) / 0.6, 0.0, 1.0)
    mask = np.clip(mask, 0.0, 1.0)[..., None]
    rgb = arr[..., :3].astype(np.float32) * mask
    arr[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    return arr


def apply_chromatic(arr, shift):
    """Aberración cromática RADIAL (como una lente real): desplaza el canal rojo
    hacia AFUERA y el azul hacia ADENTRO desde el centro, tanto más cuanto más
    lejos del centro. 'shift' = desplazamiento (px) en las esquinas. Usa
    interpolación con borde fijado (clamp), sin el 'wrap' del método anterior."""
    shift = float(shift)
    if abs(shift) < 0.5:
        return arr
    ndi = _ndi()
    h, w = arr.shape[0], arr.shape[1]
    cy, cx = (h - 1) / 2.0, (w - 1) / 2.0
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    dx, dy = xx - cx, yy - cy
    R = max(1.0, float(np.hypot(cx, cy)))
    k = shift / R
    for ch, sgn in ((0, 1.0), (2, -1.0)):   # rojo afuera, azul adentro
        sx = xx + sgn * k * dx
        sy = yy + sgn * k * dy
        arr[..., ch] = ndi.map_coordinates(
            arr[..., ch].astype(np.float32), [sy, sx], order=1, mode="nearest"
        ).clip(0, 255).astype(np.uint8)
    return arr


def apply_maximum(arr, size):
    """Máximo / dilatar: engrosa las zonas claras."""
    size = max(1, int(round(size)))
    if size < 2:
        return arr
    ndi = _ndi()
    for c in range(3):
        arr[..., c] = ndi.grey_dilation(arr[..., c], size=(size, size))
    return arr


def apply_minimum(arr, size):
    """Mínimo / erosionar: engrosa las zonas oscuras."""
    size = max(1, int(round(size)))
    if size < 2:
        return arr
    ndi = _ndi()
    for c in range(3):
        arr[..., c] = ndi.grey_erosion(arr[..., c], size=(size, size))
    return arr


def apply_contour(arr, thickness=1):
    """Contorno: dibuja los bordes en oscuro sobre fondo claro. 'thickness'
    engrosa las líneas dilatando la magnitud del gradiente (1 = líneas finas)."""
    ndi = _ndi()
    gray = arr[..., :3].mean(axis=2).astype(np.float32)
    gx = ndi.sobel(gray, axis=1)
    gy = ndi.sobel(gray, axis=0)
    mag = np.hypot(gx, gy) / 4.0
    thickness = max(1, int(round(thickness)))
    if thickness > 1:
        mag = ndi.grey_dilation(mag, size=(thickness, thickness))
    out = np.clip(255.0 - mag, 0, 255).astype(np.uint8)
    arr[..., 0] = out
    arr[..., 1] = out
    arr[..., 2] = out
    return arr


def apply_add_noise(arr, amount, mono=False, seed=0):
    """Añade ruido gaussiano. mono = mismo ruido en RGB (monocromo)."""
    if amount <= 0:
        return arr
    rng = np.random.default_rng(seed)
    sigma = amount / 100.0 * 80.0
    rgb = arr[..., :3].astype(np.float32)
    if mono:
        n = rng.normal(0.0, sigma, size=(rgb.shape[0], rgb.shape[1], 1))
    else:
        n = rng.normal(0.0, sigma, size=rgb.shape)
    rgb = rgb + n
    arr[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    return arr


class BoxBlurDialog(AdjustmentDialog):
    title = t("fx.t.box_blur")
    heavy = True
    preview_downscale = True

    def build_controls(self):
        self.add_slider_row("radius", t("eff.radius"), 1, 100, 10)
        self.add_checkbox_row("perceptual", t("fx.perceptual_blur"), default=False)

    def compute(self, arr):
        return apply_box_blur(arr, self.val("radius") * self._cur_scale, self.checked("perceptual"))


class MotionBlurDialog(AdjustmentDialog):
    title = t("fx.t.motion_blur")
    heavy = True
    preview_downscale = True

    def build_controls(self):
        self.add_slider_row("length", t("fx.l.length"), 1, 200, 20)
        self.add_angle_row("angle", t("fx.l.angle"), -180, 180, 0)
        self.add_checkbox_row("perceptual", t("fx.perceptual_blur"), default=False)

    def compute(self, arr):
        return apply_motion_blur(arr, self.val("length") * self._cur_scale,
                                 self.val("angle"), self.checked("perceptual"))


class SharpenThresholdDialog(AdjustmentDialog):
    title = t("fx.t.sharpen_threshold")
    heavy = True
    preview_downscale = True

    def build_controls(self):
        self.add_slider_row("radius", t("eff.radius"), 1, 20, 2)
        self.add_slider_row("amount", t("fx.l.amount"), 0, 300, 100)
        self.add_slider_row("threshold", t("fx.l.threshold"), 0, 100, 10)

    def compute(self, arr):
        return apply_sharpen_threshold(arr, self.val("radius") * self._cur_scale,
                                       self.val("amount"), self.val("threshold"))


class PixelateDialog(AdjustmentDialog):
    title = t("eff.pixelate", default="Pixelar")

    def build_controls(self):
        self.add_slider_row("block", t("eff.size"), 2, 64, 8)

    def compute(self, arr):
        return apply_pixelate(arr, self.val("block"))


class VignetteDialog(AdjustmentDialog):
    title = t("eff.vignette", default="Viñeta")

    def build_controls(self):
        self.add_slider_row("amount", t("eff.intensity"), 0, 100, 50)

    def compute(self, arr):
        return apply_vignette(arr, self.val("amount"))


class ChromaticDialog(AdjustmentDialog):
    title = t("fx.t.chromatic")
    heavy = True
    preview_downscale = True

    def build_controls(self):
        self.add_slider_row("shift", t("fx.l.shift"), -20, 20, 4)

    def compute(self, arr):
        return apply_chromatic(arr, self.val("shift") * self._cur_scale)


class MaximumDialog(AdjustmentDialog):
    title = t("fx.t.maximum")
    heavy = True
    preview_downscale = True

    def build_controls(self):
        self.add_slider_row("size", t("eff.size"), 1, 15, 3)

    def compute(self, arr):
        return apply_maximum(arr, max(1, int(round(self.val("size") * self._cur_scale))))


class MinimumDialog(AdjustmentDialog):
    title = t("fx.t.minimum")
    heavy = True
    preview_downscale = True

    def build_controls(self):
        self.add_slider_row("size", t("eff.size"), 1, 15, 3)

    def compute(self, arr):
        return apply_minimum(arr, max(1, int(round(self.val("size") * self._cur_scale))))


class ContourDialog(AdjustmentDialog):
    title = t("fx.t.contour")
    heavy = True
    preview_downscale = True

    def build_controls(self):
        self.add_slider_row("thickness", t("eff.thickness"), 1, 15, 2)

    def compute(self, arr):
        return apply_contour(arr, max(1, int(round(self.val("thickness") * self._cur_scale))))


class AddNoiseDialog(AdjustmentDialog):
    title = t("fx.t.add_noise")
    heavy = True

    def build_controls(self):
        import random
        self._seed = random.randint(0, 2 ** 31 - 1)
        self.add_slider_row("amount", t("fx.l.amount"), 0, 100, 25)
        self.add_checkbox_row("mono", t("fx.monochrome"), False)

    def compute(self, arr):
        return apply_add_noise(arr, self.val("amount"),
                               mono=self.checked("mono"), seed=self._seed)


# ===================================================== EFECTOS (lote 3)
def apply_zoom_blur(arr, amount, perceptual=False):
    """Desenfoque radial/zoom: promedia copias escaladas hacia el centro."""
    if amount <= 0:
        return arr
    ndi = _ndi()
    h, w = arr.shape[0], arr.shape[1]
    rgb = arr[..., :3].astype(np.float32)
    if perceptual:
        rgb = np.power(rgb / 255.0, 2.2)
    cy, cx = (h - 1) / 2.0, (w - 1) / 2.0
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    n = 12
    maxz = amount / 100.0 * 0.25
    acc = np.zeros_like(rgb)
    for i in range(n):
        z = 1.0 - maxz * (i / (n - 1))
        sy = cy + (yy - cy) * z
        sx = cx + (xx - cx) * z
        for c in range(3):
            acc[..., c] += ndi.map_coordinates(rgb[..., c], [sy, sx],
                                                order=1, mode="nearest")
    acc /= n
    if perceptual:
        acc = np.power(np.clip(acc, 0, 1), 1.0 / 2.2) * 255.0
    arr[..., :3] = np.clip(acc, 0, 255).astype(np.uint8)
    return arr


def apply_halftone(arr, cell):
    """Semitono: rejilla de puntos cuyo tamaño depende del brillo local (B/N)."""
    cell = max(2, int(round(cell)))
    h, w = arr.shape[0], arr.shape[1]
    gray = arr[..., :3].mean(axis=2).astype(np.float32)
    ph, pw = (-h) % cell, (-w) % cell
    g = np.pad(gray, ((0, ph), (0, pw)), mode="edge")
    H, W = g.shape
    cm = g.reshape(H // cell, cell, W // cell, cell).mean(axis=(1, 3))
    cm = np.repeat(np.repeat(cm, cell, axis=0), cell, axis=1)[:h, :w]
    yy, xx = np.mgrid[0:h, 0:w]
    fy = (yy % cell) - (cell - 1) / 2.0
    fx = (xx % cell) - (cell - 1) / 2.0
    dist = np.sqrt(fx * fx + fy * fy)
    radius = (1.0 - cm / 255.0) * (cell * 0.75)
    out = np.where(dist <= radius, 0.0, 255.0).astype(np.uint8)
    arr[..., 0] = out
    arr[..., 1] = out
    arr[..., 2] = out
    return arr


def apply_oil(arr, radius, levels):
    """Pintura al óleo: cada píxel toma el color medio del 'nivel' de
    intensidad más frecuente en su vecindad."""
    ndi = _ndi()
    size = 2 * max(1, int(round(radius))) + 1
    levels = max(2, int(round(levels)))
    rgb = arr[..., :3].astype(np.float32)
    inten = rgb.mean(axis=2)
    q = np.clip((inten / 256.0 * levels).astype(np.int32), 0, levels - 1)
    best = np.full(inten.shape, -1.0, np.float32)
    out = np.zeros_like(rgb)
    for L in range(levels):
        m = (q == L).astype(np.float32)
        cnt = ndi.uniform_filter(m, size=size)
        sel = cnt > best
        best = np.where(sel, cnt, best)
        denom = np.maximum(cnt, 1e-6)
        for c in range(3):
            sc = ndi.uniform_filter(rgb[..., c] * m, size=size)
            out[..., c] = np.where(sel, sc / denom, out[..., c])
    arr[..., :3] = np.clip(out, 0, 255).astype(np.uint8)
    return arr


def apply_pencil_sketch(arr, tip, shading):
    """Boceto a lápiz. Dos parámetros:
    - 'tip' (espesor del lápiz): radio del desenfoque del color dodge; controla el
      grosor/suavidad del trazo.
    - 'shading' (sombreado, 0..100): cuánto sombreado del original se conserva. El
      color dodge puro lleva las zonas planas a blanco (poco grafito); multiplicando
      por una capa de sombreado del gris se recuperan los medios tonos. 0 = trazo
      sobre papel blanco (como antes); valores altos = sombreado de grafito completo."""
    ndi = _ndi()
    gray = arr[..., :3].mean(axis=2).astype(np.float32)
    inv = 255.0 - gray
    blur = ndi.gaussian_filter(inv, sigma=max(1.0, float(tip)))
    denom = np.clip(255.0 - blur, 1.0, 255.0)
    dodge = np.clip(gray * 255.0 / denom, 0.0, 255.0)        # el trazo (papel claro)
    k = max(0.0, float(shading)) / 100.0
    shade = 255.0 - (255.0 - gray) * k                       # capa de sombreado
    out = np.clip(dodge * shade / 255.0, 0, 255).astype(np.uint8)
    arr[..., 0] = out
    arr[..., 1] = out
    arr[..., 2] = out
    return arr


def apply_ink_sketch(arr, ink, coloring):
    """Boceto a tinta estilo Paint.NET: se CONSERVA la foto (con su color) y se le
    MULTIPLICA encima una capa de tinta —líneas de contorno + punteado (stipple) en
    las sombras—, que solo oscurece en los bordes y deja el resto intacto (por eso
    el color y el detalle se mantienen).
    - 'ink' (0..100): cantidad de tinta (líneas + punteado).
    - 'coloring' (0..100): saturación del color (0 = blanco y negro; 100 = color pleno)."""
    ndi = _ndi()
    rgb = arr[..., :3].astype(np.float32)
    gray = rgb.mean(axis=2)
    amt = max(0.0, min(100.0, float(ink))) / 100.0
    col = max(0.0, min(100.0, float(coloring))) / 100.0

    # Base: la FOTO, desaturada según 'coloring' (el BRILLO se mantiene intacto).
    base = gray[..., None] + (rgb - gray[..., None]) * col

    # Líneas de tinta por umbral adaptativo (contornos limpios y selectivos).
    local = ndi.gaussian_filter(gray, 2.5)
    C = (1.0 - amt) * 12.0 + 4.0
    line = np.clip((local - gray - C) / 4.0, 0.0, 1.0)

    # Punteado (stipple) en los medios/sombras: densidad creciente con la oscuridad.
    inv = 1.0 - gray / 255.0
    prob = np.clip((inv - 0.35) * amt * 1.1, 0.0, 0.5)
    noise = np.random.default_rng(0).random(gray.shape)
    stipple = (prob > noise).astype(np.float32)

    ink_mask = np.clip(line + stipple, 0.0, 1.0)
    out = base * (1.0 - ink_mask[..., None])   # MULTIPLY: color preservado en lo plano
    arr[..., :3] = np.clip(out, 0, 255).astype(np.uint8)
    return arr


def apply_cartoon(arr, levels, edge_threshold):
    """Cómic: suaviza y posteriza el color y superpone un contorno oscuro."""
    ndi = _ndi()
    levels = max(2, int(round(levels)))
    rgb = arr[..., :3].astype(np.float32)
    sm = ndi.median_filter(rgb, size=(3, 3, 1))
    post = np.round(sm / 255.0 * (levels - 1)) / (levels - 1) * 255.0
    gray = rgb.mean(axis=2)
    gx = ndi.sobel(gray, axis=1)
    gy = ndi.sobel(gray, axis=0)
    mag = np.hypot(gx, gy) / 4.0
    edge = mag >= float(edge_threshold)
    post[edge] = 0.0
    arr[..., :3] = np.clip(post, 0, 255).astype(np.uint8)
    return arr


class ZoomBlurDialog(AdjustmentDialog):
    title = t("fx.t.radial_blur")
    heavy = True
    preview_downscale = True

    def build_controls(self):
        self.add_slider_row("amount", t("fx.l.amount"), 0, 100, 40)
        self.add_checkbox_row("perceptual", t("fx.perceptual_blur"), default=False)

    def compute(self, arr):
        return apply_zoom_blur(arr, self.val("amount"), self.checked("perceptual"))


class HalftoneDialog(AdjustmentDialog):
    title = t("fx.t.halftone")
    heavy = True
    preview_downscale = True

    def build_controls(self):
        self.add_slider_row("cell", t("fx.l.cell_size"), 3, 20, 6)

    def compute(self, arr):
        return apply_halftone(arr, max(2, int(round(self.val("cell") * self._cur_scale))))


class OilPaintingDialog(AdjustmentDialog):
    title = t("fx.t.oil")
    heavy = True
    preview_downscale = True

    def build_controls(self):
        self.add_slider_row("radius", t("eff.radius"), 1, 8, 3)
        self.add_slider_row("levels", t("fx.l.levels"), 3, 16, 8)

    def compute(self, arr):
        r = max(0.5, self.val("radius") * self._cur_scale)
        return apply_oil(arr, r, self.val("levels"))


class PencilSketchDialog(AdjustmentDialog):
    title = t("fx.t.pencil_sketch")
    heavy = True
    preview_downscale = True

    def build_controls(self):
        self.add_slider_row("tip", t("fx.l.pencil_thick"), 1, 30, 8)
        self.add_slider_row("shading", t("fx.l.shading"), 0, 100, 50)

    def compute(self, arr):
        return apply_pencil_sketch(arr, self.val("tip") * self._cur_scale,
                                   self.val("shading"))


class InkSketchDialog(AdjustmentDialog):
    title = t("fx.t.ink_sketch")
    heavy = True

    def build_controls(self):
        self.add_slider_row("ink", t("fx.l.ink"), 0, 100, 50)
        self.add_slider_row("coloring", t("fx.l.coloring"), 0, 100, 50)

    def compute(self, arr):
        return apply_ink_sketch(arr, self.val("ink"), self.val("coloring"))


class CartoonDialog(AdjustmentDialog):
    title = t("fx.t.comic")
    heavy = True
    preview_downscale = True

    def build_controls(self):
        self.add_slider_row("levels", t("fx.l.color_levels"), 2, 12, 6)
        self.add_slider_row("edge", t("fx.l.edge_threshold"), 1, 100, 25)

    def compute(self, arr):
        return apply_cartoon(arr, self.val("levels"), self.val("edge"))


# ============================================ Vibración + Distorsionar + Superficie
def apply_vibrance(arr, amount):
    # Sube la saturacion sobre todo en los tonos poco saturados (los ya muy
    # saturados apenas cambian). amount en [-100, 100].
    if amount == 0:
        return arr
    rgb = arr[..., :3].astype(np.float32) / 255.0
    h, s, v = rgb_to_hsv(rgb)
    k = amount / 100.0
    s = np.clip(s * (1.0 + k * (1.0 - s)), 0.0, 1.0)
    arr[..., :3] = np.clip(hsv_to_rgb(h, s, v) * 255.0, 0, 255).astype(np.uint8)
    return arr


class VibranceDialog(AdjustmentDialog):
    title = t("fx.t.vibrance")
    preview_downscale = True   # roundtrip HSV: previa en vivo sobre versión reducida

    def build_controls(self):
        self.add_slider_row("amount", t("fx.l.vibrance"), -100, 100, 0)

    def compute(self, arr):
        return apply_vibrance(arr, self.val("amount"))


def apply_wave(arr, amplitude, wavelength):
    # Ondas senoidales: desplaza cada pixel segun un seno (en X y en Y).
    if amplitude <= 0:
        return arr
    ndi = _ndi()
    h, w = arr.shape[0], arr.shape[1]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    wl = max(1.0, float(wavelength))
    nx = xx + amplitude * np.sin(2 * np.pi * yy / wl)
    ny = yy + amplitude * np.sin(2 * np.pi * xx / wl)
    coords = np.array([ny, nx])
    out = np.empty_like(arr)
    for c in range(arr.shape[2]):
        out[..., c] = ndi.map_coordinates(arr[..., c], coords, order=1, mode='reflect')
    return out


class WaveDialog(AdjustmentDialog):
    title = t("fx.t.waves")
    heavy = True
    preview_downscale = True

    def build_controls(self):
        self.add_slider_row("amplitude", t("fx.l.amplitude"), 0, 50, 10)
        self.add_slider_row("wavelength", t("fx.l.wavelength"), 5, 200, 40)

    def compute(self, arr):
        s = self._cur_scale
        return apply_wave(arr, self.val("amplitude") * s,
                          max(1.0, self.val("wavelength") * s))


def apply_spherize(arr, amount, cx_frac=50.0, cy_frac=50.0):
    # Distorsion esferica: amount>0 abomba (lupa), amount<0 pellizca [-100,100].
    # cx_frac/cy_frac (0..100) = posicion del centro del efecto en la imagen.
    if amount == 0:
        return arr
    ndi = _ndi()
    h, w = arr.shape[0], arr.shape[1]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cx = cx_frac / 100.0 * (w - 1)
    cy = cy_frac / 100.0 * (h - 1)
    R = max(1.0, min(w, h) / 2.0)
    dx = xx - cx
    dy = yy - cy
    r = np.sqrt(dx * dx + dy * dy)
    rr = np.clip(r / R, 0.0, 1.0)
    exp = 1.0 - (amount / 100.0) * 0.8
    src = np.power(rr, exp)
    scale = np.where(rr > 1e-6, src / np.maximum(rr, 1e-6), 1.0)
    nx = cx + dx * scale
    ny = cy + dy * scale
    out_mask = r > R
    nx = np.where(out_mask, xx, nx)
    ny = np.where(out_mask, yy, ny)
    coords = np.array([ny, nx])
    out = np.empty_like(arr)
    for c in range(arr.shape[2]):
        out[..., c] = ndi.map_coordinates(arr[..., c], coords, order=1, mode='reflect')
    return out


class SpherizeDialog(AdjustmentDialog):
    title = t("fx.t.spherize")
    heavy = True
    preview_downscale = True

    def build_controls(self):
        self.add_slider_row("amount", t("fx.l.amount"), -100, 100, 50)
        self.add_center_picker()

    def compute(self, arr):
        return apply_spherize(arr, self.val("amount"), self.val("cx"), self.val("cy"))


def apply_twirl(arr, angle, cx_frac=50.0, cy_frac=50.0):
    # Remolino: gira los pixeles un angulo que decae con el radio (0 en el borde).
    # cx_frac/cy_frac (0..100) = posicion del centro del remolino.
    if angle == 0:
        return arr
    ndi = _ndi()
    h, w = arr.shape[0], arr.shape[1]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cx = cx_frac / 100.0 * (w - 1)
    cy = cy_frac / 100.0 * (h - 1)
    R = max(1.0, min(w, h) / 2.0)
    dx = xx - cx
    dy = yy - cy
    r = np.sqrt(dx * dx + dy * dy)
    fac = np.clip(1.0 - r / R, 0.0, 1.0)
    th = np.radians(angle) * fac
    cs = np.cos(th)
    sn = np.sin(th)
    nx = cx + (dx * cs + dy * sn)
    ny = cy + (-dx * sn + dy * cs)
    coords = np.array([ny, nx])
    out = np.empty_like(arr)
    for c in range(arr.shape[2]):
        out[..., c] = ndi.map_coordinates(arr[..., c], coords, order=1, mode='reflect')
    return out


class TwirlDialog(AdjustmentDialog):
    title = t("fx.t.swirl")
    heavy = True
    preview_downscale = True

    def build_controls(self):
        self.add_slider_row("angle", t("eff.angle"), -360, 360, 120)
        self.add_center_picker()

    def compute(self, arr):
        return apply_twirl(arr, self.val("angle"), self.val("cx"), self.val("cy"))


def apply_surface_blur(arr, radius, threshold):
    # Desenfoque de superficie (bilateral): suaviza las zonas planas pero
    # respeta los bordes (solo promedia vecinos de color parecido). 'threshold'
    # controla cuanto se han de parecer para mezclarse.
    radius = int(round(radius))
    if radius < 1:
        return arr
    threshold = max(1.0, float(threshold))
    rgb = arr[..., :3].astype(np.float32)
    ss = radius / 2.0
    inv2s = 1.0 / (2.0 * ss * ss)
    inv2r = 1.0 / (2.0 * threshold * threshold)
    acc = np.zeros_like(rgb)
    wsum = np.zeros(rgb.shape[:2] + (1,), np.float32)
    ctr = rgb
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            sh = np.roll(np.roll(rgb, dy, axis=0), dx, axis=1)
            sp = np.exp(-(dx * dx + dy * dy) * inv2s)
            diff = sh - ctr
            rw = np.exp(-np.sum(diff * diff, axis=2, keepdims=True) * inv2r)
            wg = sp * rw
            acc += sh * wg
            wsum += wg
    arr[..., :3] = np.clip(acc / np.maximum(wsum, 1e-6), 0, 255).astype(np.uint8)
    return arr


class SurfaceBlurDialog(AdjustmentDialog):
    title = t("fx.t.surface_blur")
    heavy = True
    preview_downscale = True

    def build_controls(self):
        self.add_slider_row("radius", t("eff.radius"), 1, 15, 5)
        self.add_slider_row("threshold", t("fx.l.threshold"), 1, 100, 25)

    def compute(self, arr):
        r = max(1, int(round(self.val("radius") * self._cur_scale)))
        return apply_surface_blur(arr, r, self.val("threshold"))


# ===================================================== Mapa de degradado
def apply_gradient_map(arr, c_low, c_mid, c_high, invert=False):
    """Mapa de degradado: sustituye cada píxel por un color tomado de un degradado
    (sombras -> medios -> luces) según su LUMINOSIDAD. Clásico para virajes y
    color grading. Conserva el alfa. c_* son (r,g,b); invert voltea el mapeo."""
    rgb = arr[..., :3].astype(np.float32)
    lum = rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114
    if invert:
        lum = 255.0 - lum
    # LUT de 256 por canal con 3 paradas (0, 128, 255) interpoladas linealmente.
    x = np.arange(256, dtype=np.float32)
    xp = np.array([0.0, 128.0, 255.0], np.float32)
    stops = np.array([c_low, c_mid, c_high], np.float32)   # (3 paradas, 3 canales)
    lut = np.stack([np.interp(x, xp, stops[:, ch]) for ch in range(3)], axis=1)
    idx = np.clip(lum, 0, 255).astype(np.int32)
    arr[..., :3] = np.clip(lut[idx], 0, 255).astype(np.uint8)
    return arr


class GradientMapDialog(AdjustmentDialog):
    title = t("eff.grad_map", default="Mapa de degradado")

    def build_controls(self):
        self.add_color_row("low", t("adj.shadows"), "#202a4a")
        self.add_color_row("mid", t("adj.midtones"), "#b85c7e")
        self.add_color_row("high", t("adj.highlights"), "#f2e4b0")
        self.add_checkbox_row("invert", t("adj.invert"), False)

    def compute(self, arr):
        return apply_gradient_map(arr, self.color("low"), self.color("mid"),
                                  self.color("high"), self.checked("invert"))

# ===================================================== Fase 2: Nuevos Ajustes (Color y Tono)
def apply_black_white_advanced(arr, r_pct, g_pct, b_pct):
    rgb = arr[..., :3].astype(np.float32)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    gray = (r * (r_pct / 100.0) + g * (g_pct / 100.0) + b * (b_pct / 100.0))
    gray_clipped = np.clip(gray, 0, 255).astype(np.uint8)
    arr[..., 0] = arr[..., 1] = arr[..., 2] = gray_clipped
    return arr

class BlackWhiteAdvancedDialog(AdjustmentDialog):
    title = t("fx.t.bw_advanced")

    def build_controls(self):
        self.add_slider_row("r", t("fx.l.red_pct"), -200, 300, 30)
        self.add_slider_row("g", t("fx.l.green_pct"), -200, 300, 59)
        self.add_slider_row("b", t("fx.l.blue_pct"), -200, 300, 11)

    def compute(self, arr):
        return apply_black_white_advanced(arr, self.val("r"), self.val("g"), self.val("b"))

def apply_shadows_highlights(arr, shadows, highlights, radius):
    if shadows == 0 and highlights == 0:
        return arr
    ndi = _ndi()
    rgb = arr[..., :3].astype(np.float32) / 255.0
    lum = rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114
    
    if radius > 0:
        lum_blur = ndi.gaussian_filter(lum, sigma=(radius, radius))
    else:
        lum_blur = lum

    s_mask = 1.0 - lum_blur
    h_mask = lum_blur
    
    gamma_s = 1.0 - (s_mask * (shadows / 100.0) * 0.7)
    gamma_h = 1.0 + (h_mask * (highlights / 100.0) * 2.0)
    
    gamma_total = np.clip(gamma_s * gamma_h, 0.1, 5.0)
    
    rgb = np.power(rgb + 1e-6, gamma_total[..., None])
    arr[..., :3] = np.clip(rgb * 255.0, 0, 255).astype(np.uint8)
    return arr

class ShadowsHighlightsDialog(AdjustmentDialog):
    title = t("fx.t.shadows_highlights")
    heavy = True
    preview_downscale = True
    
    def build_controls(self):
        self.add_slider_row("shadows", t("fx.l.lighten_shadows"), 0, 100, 0)
        self.add_slider_row("highlights", t("fx.l.darken_highlights"), 0, 100, 0)
        self.add_slider_row("radius", t("fx.l.radius_smooth"), 0, 200, 30)

    def compute(self, arr):
        return apply_shadows_highlights(arr, self.val("shadows"), self.val("highlights"), self.val("radius") * self._cur_scale)

def apply_replace_color(arr, src_color, dst_color, tolerance):
    if tolerance <= 0:
        return arr
    
    rgb = arr[..., :3].astype(np.float32)
    sr, sg, sb = src_color
    dr, dg, db = dst_color
    
    dist = np.sqrt((rgb[..., 0] - sr)**2 + (rgb[..., 1] - sg)**2 + (rgb[..., 2] - sb)**2)
    mask = np.clip(1.0 - (dist / float(tolerance)), 0, 1)
    mask = mask * mask * (3.0 - 2.0 * mask)
    
    rgb[..., 0] += (dr - sr) * mask
    rgb[..., 1] += (dg - sg) * mask
    rgb[..., 2] += (db - sb) * mask
    
    arr[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    return arr

class ReplaceColorGlobalDialog(AdjustmentDialog):
    title = t("fx.t.replace_color")

    def build_controls(self):
        self.add_color_row("src", t("fx.l.source_color"), "#ff0000")
        self.add_color_row("dst", t("fx.l.target_color"), "#0000ff")
        self.add_slider_row("tolerance", t("fx.l.tolerance"), 1, 255, 60)

    def compute(self, arr):
        return apply_replace_color(arr, self.color("src"), self.color("dst"), self.val("tolerance"))

def apply_channel_mixer(arr, rr, rg, rb, gr, gg, gb, br, bg, bb):
    rgb = arr[..., :3].astype(np.float32)
    r = rgb[..., 0]
    g = rgb[..., 1]
    b = rgb[..., 2]
    
    out_r = r * (rr / 100.0) + g * (rg / 100.0) + b * (rb / 100.0)
    out_g = r * (gr / 100.0) + g * (gg / 100.0) + b * (gb / 100.0)
    out_b = r * (br / 100.0) + g * (bg / 100.0) + b * (bb / 100.0)
    
    arr[..., 0] = np.clip(out_r, 0, 255).astype(np.uint8)
    arr[..., 1] = np.clip(out_g, 0, 255).astype(np.uint8)
    arr[..., 2] = np.clip(out_b, 0, 255).astype(np.uint8)
    return arr

class ChannelMixerDialog(AdjustmentDialog):
    title = t("fx.t.channel_mixer")
    
    def build_controls(self):
        lbl_r = QLabel(t("fx.l.final_red"))
        lbl_r.setStyleSheet(f"font-weight: bold; color: {theme.CHANNEL_R}; margin-top: 5px;")
        self.controls_layout.addWidget(lbl_r)
        self.add_slider_row("rr", t("fx.l.red_pct_ind"), -200, 200, 100)
        self.add_slider_row("rg", t("fx.l.green_pct_ind"), -200, 200, 0)
        self.add_slider_row("rb", t("fx.l.blue_pct_ind"), -200, 200, 0)
        
        lbl_g = QLabel(t("fx.l.final_green"))
        lbl_g.setStyleSheet(f"font-weight: bold; color: {theme.CHANNEL_G}; margin-top: 5px;")
        self.controls_layout.addWidget(lbl_g)
        self.add_slider_row("gr", t("fx.l.red_pct_ind"), -200, 200, 0)
        self.add_slider_row("gg", t("fx.l.green_pct_ind"), -200, 200, 100)
        self.add_slider_row("gb", t("fx.l.blue_pct_ind"), -200, 200, 0)

        lbl_b = QLabel(t("fx.l.final_blue"))
        lbl_b.setStyleSheet(f"font-weight: bold; color: {theme.CHANNEL_B}; margin-top: 5px;")
        self.controls_layout.addWidget(lbl_b)
        self.add_slider_row("br", t("fx.l.red_pct_ind"), -200, 200, 0)
        self.add_slider_row("bg", t("fx.l.green_pct_ind"), -200, 200, 0)
        self.add_slider_row("bb", t("fx.l.blue_pct_ind"), -200, 200, 100)

    def compute(self, arr):
        return apply_channel_mixer(arr,
            self.val("rr"), self.val("rg"), self.val("rb"),
            self.val("gr"), self.val("gg"), self.val("gb"),
            self.val("br"), self.val("bg"), self.val("bb"))

# ===================================================== Fase 3: Nuevos Efectos Visuales
def create_polygon_kernel(radius, sides=6):
    size = int(radius * 2 + 1)
    kernel = np.zeros((size, size), dtype=np.float32)
    center = radius
    Y, X = np.ogrid[:size, :size]
    angles = np.linspace(0, 2 * np.pi, sides, endpoint=False)
    mask = np.ones((size, size), dtype=bool)
    for angle in angles:
        nx, ny = np.cos(angle), np.sin(angle)
        dist = (X - center) * nx + (Y - center) * ny
        mask &= (dist <= radius)
    kernel[mask] = 1.0
    if kernel.sum() == 0:
        kernel[center, center] = 1.0
    return kernel / kernel.sum()

def apply_lens_blur(arr, radius, sides, brightness):
    if radius <= 0:
        return arr
    ndi = _ndi()
    kernel = create_polygon_kernel(radius, sides)
    rgb = arr[..., :3].astype(np.float32)
    
    gamma = 1.0 + (brightness / 100.0) * 2.0
    rgb = np.power(rgb / 255.0, gamma)
    
    for c in range(3):
        rgb[..., c] = ndi.convolve(rgb[..., c], kernel, mode='reflect')
    
    rgb = np.power(rgb, 1.0 / gamma) * 255.0
    arr[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    return arr

class LensBlurDialog(AdjustmentDialog):
    title = t("fx.t.lens_blur")
    heavy = True
    preview_downscale = True

    def build_controls(self):
        self.add_slider_row("radius", t("fx.l.radius"), 0, 100, 20)
        self.add_slider_row("sides", t("fx.l.sides"), 3, 9, 6)
        self.add_slider_row("brightness", t("fx.l.specular"), 0, 100, 20)

    def compute(self, arr):
        return apply_lens_blur(arr, self.val("radius") * self._cur_scale, self.val("sides"), self.val("brightness"))

def generate_fractal_noise(shape, scale, octaves=4, seed=42, ref_shape=None):
    ndi = _ndi()
    np.random.seed(seed)
    noise = np.zeros(shape, dtype=np.float32)
    h, w = shape
    # El nº de celdas del ruido se basa en la resolución de referencia (la del
    # patch a tamaño completo), no en el tamaño en píxeles de salida: así la
    # vista previa reducida y el render final usan las MISMAS rejillas aleatorias
    # y producen el mismo patrón (si no, la previa no coincidía con el resultado).
    rh, rw = ref_shape if ref_shape else shape
    for i in range(octaves):
        s = max(1, scale / (2 ** i))
        lr_h, lr_w = max(2, int(rh / s)), max(2, int(rw / s))
        n = np.random.rand(lr_h, lr_w).astype(np.float32)
        n = ndi.zoom(n, (h / lr_h, w / lr_w), order=3)
        n = n[:h, :w]
        noise += n / (2 ** i)
    return noise

def apply_render_clouds(arr, scale, octaves, c1, c2, ref_shape=None):
    h, w = arr.shape[:2]
    seed = int(scale * 10 + octaves * 100)
    noise = generate_fractal_noise((h, w), scale, octaves, seed, ref_shape=ref_shape)
    
    noise_min, noise_max = noise.min(), noise.max()
    if noise_max > noise_min:
        noise = (noise - noise_min) / (noise_max - noise_min)
    
    color1 = np.array(c1, dtype=np.float32)
    color2 = np.array(c2, dtype=np.float32)
    
    result = color1 * (1.0 - noise[..., None]) + color2 * noise[..., None]
    arr[..., :3] = np.clip(result, 0, 255).astype(np.uint8)
    return arr

class RenderCloudsDialog(AdjustmentDialog):
    title = t("fx.t.render_clouds")
    heavy = True
    preview_downscale = True

    def build_controls(self):
        self.add_slider_row("scale", t("fx.l.scale"), 10, 200, 50)
        self.add_slider_row("octaves", t("fx.l.detail_octaves"), 1, 8, 4)
        self.add_color_row("c1", t("fx.l.color1"), "#000000")
        self.add_color_row("c2", t("fx.l.color2"), "#ffffff")

    def compute(self, arr):
        return apply_render_clouds(arr, self.val("scale"), self.val("octaves"),
                                   self.color("c1"), self.color("c2"),
                                   ref_shape=(self._H, self._W))

def apply_displace(arr, amount, scale):
    if amount == 0:
        return arr
    ndi = _ndi()
    h, w = arr.shape[:2]
    seed = int(amount + scale)
    noise_x = generate_fractal_noise((h, w), scale, 2, seed)
    noise_y = generate_fractal_noise((h, w), scale, 2, seed + 1)
    
    noise_x = (noise_x - noise_x.mean()) / (noise_x.std() + 1e-5)
    noise_y = (noise_y - noise_y.mean()) / (noise_y.std() + 1e-5)
    
    Y, X = np.indices((h, w))
    map_x = X + noise_x * amount
    map_y = Y + noise_y * amount
    
    coords = np.array([map_y, map_x])
    
    rgb = arr[..., :3].astype(np.float32)
    for c in range(3):
        rgb[..., c] = ndi.map_coordinates(rgb[..., c], coords, order=1, mode='reflect')
    
    arr[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    return arr

class DisplaceDialog(AdjustmentDialog):
    title = t("fx.t.displacement")
    heavy = True
    preview_downscale = True

    def build_controls(self):
        self.add_slider_row("amount", t("fx.l.intensity"), 0, 200, 30)
        self.add_slider_row("scale", t("fx.l.noise_scale"), 10, 200, 50)

    def compute(self, arr):
        return apply_displace(arr, self.val("amount") * self._cur_scale, self.val("scale"))

def apply_glitch(arr, amount, shift_rgb):
    if amount == 0 and shift_rgb == 0:
        return arr
    h, w = arr.shape[:2]
    rgb = arr[..., :3].astype(np.float32)
    
    np.random.seed(int(amount + shift_rgb) + 42)
    
    if shift_rgb > 0:
        shift = int(shift_rgb)
        rgb[..., 0] = np.roll(rgb[..., 0], -shift, axis=1)
        rgb[..., 2] = np.roll(rgb[..., 2], shift, axis=1)
        
    if amount > 0:
        num_blocks = int(amount / 2)
        for _ in range(max(1, num_blocks)):
            y = np.random.randint(0, h)
            bh = np.random.randint(1, max(2, int(h / 10)))
            shift_x = np.random.randint(-amount, amount + 1)
            y_end = min(y + bh, h)
            rgb[y:y_end] = np.roll(rgb[y:y_end], shift_x, axis=1)
            
    arr[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    return arr

class GlitchDialog(AdjustmentDialog):
    title = t("fx.t.glitch")
    heavy = True
    preview_downscale = True

    def build_controls(self):
        self.add_slider_row("amount", t("fx.l.distortion_blocks"), 0, 200, 20)
        self.add_slider_row("shift_rgb", t("fx.l.chromatic_lbl"), 0, 100, 10)

    def compute(self, arr):
        return apply_glitch(arr, self.val("amount") * self._cur_scale, self.val("shift_rgb") * self._cur_scale)


# ===================================================== NUEVOS (lote 1)
# Claridad, Quitar neblina y Filtro de fotografía (Ajustes) + Resplandor/Bloom y
# Tilt-shift (Efectos). Todos numpy/scipy, misma familia AdjustmentDialog.

def apply_clarity(arr, amount, radius):
    """Claridad: contraste LOCAL de medios tonos (máscara de desenfoque de radio
    grande sobre la luminancia), protegiendo sombras y luces con un peso de medios
    tonos para no ensuciar negros ni quemar blancos. amount<0 suaviza."""
    if amount == 0:
        return arr
    ndi = _ndi()
    rgb = arr[..., :3].astype(np.float32)
    lum = rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114
    blur = ndi.gaussian_filter(lum, sigma=max(0.5, float(radius)))
    detail = lum - blur                                   # contraste local
    n = lum / 255.0
    mid = 1.0 - np.abs(2.0 * n - 1.0) ** 2                # 1 en gris medio, 0 en extremos
    add = (amount / 100.0) * detail * mid
    out = rgb + add[..., None]                            # igual a los 3 canales
    arr[..., :3] = np.clip(out, 0, 255).astype(np.uint8)
    return arr


class ClarityDialog(AdjustmentDialog):
    title = t("fx.t.clarity")
    heavy = True
    preview_downscale = True

    def build_controls(self):
        self.add_slider_row("amount", t("fx.l.amount"), -100, 100, 40)

    def compute(self, arr):
        # Radio proporcional al tamaño (contraste realmente "local"), escalado en
        # la vista previa reducida.
        r = max(3.0, 0.02 * max(self._W, self._H)) * self._cur_scale
        return apply_clarity(arr, self.val("amount"), r)


def apply_dehaze(arr, amount):
    """Quita neblina (dark channel prior simplificado, He et al.): estima el velo
    atmosférico a partir del canal oscuro y lo resta, recuperando contraste y
    color en fotos con bruma."""
    if amount <= 0:
        return arr
    ndi = _ndi()
    I = arr[..., :3].astype(np.float32) / 255.0
    strength = amount / 100.0
    dark = I.min(axis=2)                                   # canal oscuro
    win = max(3, int(round(0.02 * max(arr.shape[0], arr.shape[1]))))
    dark = ndi.minimum_filter(dark, size=win)
    # Luz atmosférica A: media de los píxeles con canal oscuro más alto (~0.1%).
    flat = dark.ravel()
    k = max(1, int(flat.size * 0.001))
    idx = np.argpartition(flat, -k)[-k:]
    A = float(np.clip(I.reshape(-1, 3)[idx].max(axis=0).mean(), 0.3, 1.0))
    omega = 0.95 * strength
    t = np.clip(1.0 - omega * (dark / max(A, 1e-3)), 0.1, 1.0)[..., None]
    J = (I - A) / t + A
    arr[..., :3] = np.clip(J * 255.0, 0, 255).astype(np.uint8)
    return arr


class DehazeDialog(AdjustmentDialog):
    title = t("fx.t.dehaze")
    heavy = True
    preview_downscale = True

    def build_controls(self):
        self.add_slider_row("amount", t("fx.l.amount"), 0, 100, 60)

    def compute(self, arr):
        return apply_dehaze(arr, self.val("amount"))


def apply_photo_filter(arr, color, density, preserve_lum):
    """Filtro de fotografía: tiñe la imagen con un color (densidad ajustable),
    conservando opcionalmente la luminosidad original (como el de Photoshop): así
    solo cambia el matiz, no el brillo."""
    if density <= 0:
        return arr
    rgb = arr[..., :3].astype(np.float32)
    d = density / 100.0
    tint = np.array(color, np.float32) / 255.0
    out = rgb * (1.0 - d) + (rgb * tint[None, None, :]) * d
    if preserve_lum:
        w = np.array([0.299, 0.587, 0.114], np.float32)
        lin = rgb @ w
        lout = out @ w
        out = out * (lin / np.clip(lout, 1e-3, None))[..., None]
    arr[..., :3] = np.clip(out, 0, 255).astype(np.uint8)
    return arr


class PhotoFilterDialog(AdjustmentDialog):
    title = t("fx.t.photo_filter")

    def build_controls(self):
        self.add_color_row("color", t("eff.color"), "#EC8A00")
        self.add_slider_row("density", t("fx.l.density"), 0, 100, 25)
        self.add_checkbox_row("preserve", t("fx.l.preserve_lum"), default=True)

    def compute(self, arr):
        return apply_photo_filter(arr, self.color("color"),
                                  self.val("density"), self.checked("preserve"))


def apply_bloom(arr, threshold, radius, intensity):
    """Resplandor (bloom): aísla las zonas más claras (por encima de un umbral de
    luminancia), las desenfoca y las funde en modo TRAMA, dando un brillo etéreo."""
    if intensity <= 0 or radius <= 0:
        return arr
    ndi = _ndi()
    rgb = arr[..., :3].astype(np.float32)
    lum = rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114
    thr = float(threshold)
    mask = np.clip((lum - thr) / max(1.0, 255.0 - thr), 0.0, 1.0)
    bright = rgb * mask[..., None]
    glow = ndi.gaussian_filter(bright, sigma=(radius, radius, 0)) * (intensity / 100.0)
    glow = np.clip(glow, 0, 255)
    out = 255.0 - (255.0 - rgb) * (255.0 - glow) / 255.0   # trama (screen)
    arr[..., :3] = np.clip(out, 0, 255).astype(np.uint8)
    return arr


class BloomDialog(AdjustmentDialog):
    title = t("fx.t.bloom")
    heavy = True
    preview_downscale = True

    def build_controls(self):
        self.add_slider_row("threshold", t("fx.l.threshold"), 0, 255, 180)
        self.add_slider_row("radius", t("fx.l.radius"), 1, 100, 25)
        self.add_slider_row("intensity", t("eff.intensity"), 0, 100, 70)

    def compute(self, arr):
        return apply_bloom(arr, self.val("threshold"),
                           self.val("radius") * self._cur_scale,
                           self.val("intensity"))


def apply_tilt_shift(arr, position, band, blur):
    """Tilt-shift (miniatura): mantiene nítida una banda horizontal y desenfoca
    de forma progresiva por encima y por debajo. position/band en % de la altura;
    blur en píxeles."""
    if blur <= 0:
        return arr
    ndi = _ndi()
    h = arr.shape[0]
    rgb = arr[..., :3].astype(np.float32)
    blurred = ndi.gaussian_filter(rgb, sigma=(blur, blur, 0))
    yc = (position / 100.0) * h
    half = max(1.0, (band / 100.0) * h * 0.5)
    y = np.arange(h, dtype=np.float32)
    m = np.clip((np.abs(y - yc) - half) / half, 0.0, 1.0)   # 0 nítido en la banda, 1 fuera
    m = m[:, None, None]
    out = rgb * (1.0 - m) + blurred * m
    arr[..., :3] = np.clip(out, 0, 255).astype(np.uint8)
    return arr


class TiltShiftDialog(AdjustmentDialog):
    title = t("fx.t.tilt_shift")
    heavy = True
    preview_downscale = True

    def build_controls(self):
        self.add_slider_row("position", t("fx.l.position"), 0, 100, 50)
        self.add_slider_row("band", t("fx.l.band_width"), 5, 100, 30)
        self.add_slider_row("blur", t("eff.radius"), 1, 60, 20)

    def compute(self, arr):
        # position/band son % de la altura (no escalan); blur es en píxeles.
        return apply_tilt_shift(arr, self.val("position"), self.val("band"),
                                self.val("blur") * self._cur_scale)


# ===================================================== NUEVOS (lote 2)
# Balance de blancos (cuentagotas) (Ajuste) + Tramado, Semitono de color,
# Desenfoque giratorio y Caleidoscopio (Efectos).

class WhiteBalanceDialog(AdjustmentDialog):
    """Balance de blancos: neutraliza una dominante de color. Pica en la imagen un
    punto que debería ser gris/blanco neutro (o pulsa Automático, gris-medio) y
    calcula ganancias por canal; la Intensidad regula cuánto se aplica."""
    title = t("fx.t.white_balance")
    preview_downscale = True

    def build_controls(self):
        self._gain = (1.0, 1.0, 1.0)
        self._pick_active = False
        row = QHBoxLayout()
        self._pick_btn = QPushButton(t("fx.wb.pick"))
        self._pick_btn.setCheckable(True)
        self._pick_btn.clicked.connect(self._toggle_pick)
        auto_btn = QPushButton(t("fx.wb.auto"))
        auto_btn.clicked.connect(self._auto_wb)
        row.addWidget(self._pick_btn)
        row.addWidget(auto_btn)
        row.addStretch()
        self.controls_layout.addLayout(row)
        self.add_slider_row("strength", t("eff.intensity"), 0, 100, 100)
        hint = QLabel(t("fx.wb.hint"))
        hint.setWordWrap(True)
        hint.setStyleSheet("color:%s; font-size:11px; font-style:italic;" % theme.TEXT_MUTED)
        self.controls_layout.addWidget(hint)
        self.closed.connect(self._end_pick)   # restaurar cursor si se cierra picando

    def _toggle_pick(self):
        self._pick_active = self._pick_btn.isChecked()
        if self.canvas is not None:
            self.canvas.setCursor(Qt.CrossCursor if self._pick_active else Qt.ArrowCursor)

    def _end_pick(self):
        self._pick_active = False
        if hasattr(self, "_pick_btn") and self._pick_btn.isChecked():
            self._pick_btn.setChecked(False)
        if self.canvas is not None:
            self.canvas.unsetCursor()

    def _on_canvas_pick(self, event):
        if not self._valid or self._full_before is None:
            self._end_pick()
            return
        z = getattr(self.canvas, "zoom_factor", 1.0) or 1.0
        pos = event.position() / z
        x, y = int(pos.x()), int(pos.y())
        img = self._full_before
        if 0 <= x < img.width() and 0 <= y < img.height():
            c = img.pixelColor(x, y)
            vals = [max(1.0, float(v)) for v in (c.red(), c.green(), c.blue())]
            target = sum(vals) / 3.0
            self._gain = tuple(target / v for v in vals)
            self._request_preview()
        self._end_pick()

    def _auto_wb(self):
        if not self._valid:
            return
        rgb = self._orig[..., :3].astype(np.float32)
        means = [max(1.0, float(rgb[..., c].mean())) for c in range(3)]
        target = sum(means) / 3.0
        self._gain = tuple(target / m for m in means)
        self._request_preview()

    def compute(self, arr):
        s = self.val("strength") / 100.0
        g = self._gain
        if s <= 0 or g == (1.0, 1.0, 1.0):
            return arr
        rgb = arr[..., :3].astype(np.float32)
        for c in range(3):
            rgb[..., c] = rgb[..., c] * (1.0 + (g[c] - 1.0) * s)
        arr[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
        return arr


def apply_dither(arr, levels):
    """Tramado ORDENADO (matriz de Bayer 8x8): reduce a 'levels' niveles por canal
    difundiendo el error con un patrón fijo (estética retro), vectorizado."""
    levels = max(2, int(round(levels)))
    bayer = np.array([
        [0, 32, 8, 40, 2, 34, 10, 42], [48, 16, 56, 24, 50, 18, 58, 26],
        [12, 44, 4, 36, 14, 46, 6, 38], [60, 28, 52, 20, 62, 30, 54, 22],
        [3, 35, 11, 43, 1, 33, 9, 41], [51, 19, 59, 27, 49, 17, 57, 25],
        [15, 47, 7, 39, 13, 45, 5, 37], [63, 31, 55, 23, 61, 29, 53, 21],
    ], np.float32) / 64.0 - 0.5                      # umbral centrado en 0
    h, w = arr.shape[0], arr.shape[1]
    thr = np.tile(bayer, (h // 8 + 1, w // 8 + 1))[:h, :w]
    step = 255.0 / (levels - 1)
    rgb = arr[..., :3].astype(np.float32)
    vd = rgb + (thr[..., None] * step)               # perturba con el patrón
    q = np.round(vd / step) * step
    arr[..., :3] = np.clip(q, 0, 255).astype(np.uint8)
    return arr


class DitherDialog(AdjustmentDialog):
    title = t("fx.t.dithering")
    heavy = True
    preview_downscale = True

    def build_controls(self):
        self.add_slider_row("levels", t("fx.l.levels"), 2, 16, 2)

    def compute(self, arr):
        return apply_dither(arr, self.val("levels"))


def apply_color_halftone(arr, cell):
    """Semitono de COLOR (estilo CMYK): puntos de tinta cian/magenta/amarillo en
    rejillas ROTADAS a ángulos distintos, con tamaño según la tinta local. Da el
    look de cómic/serigrafía a color."""
    ndi = _ndi()
    cell = max(3, int(round(cell)))
    h, w = arr.shape[0], arr.shape[1]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    rgb = arr[..., :3].astype(np.float32)
    # Tintas CMY (sustractivas) suavizadas al tamaño de celda (cobertura local).
    inks = [255.0 - rgb[..., 0], 255.0 - rgb[..., 1], 255.0 - rgb[..., 2]]
    angles = [15.0, 75.0, 0.0]      # C, M, Y (ángulos clásicos de trama)
    out = np.full_like(rgb, 255.0)  # papel blanco
    for ch, (ink, ang) in enumerate(zip(inks, angles)):
        cov = ndi.uniform_filter(ink, size=cell)
        a = np.radians(ang)
        rx = xx * np.cos(a) + yy * np.sin(a)
        ry = -xx * np.sin(a) + yy * np.cos(a)
        fx = np.mod(rx, cell) - cell / 2.0
        fy = np.mod(ry, cell) - cell / 2.0
        dist = np.sqrt(fx * fx + fy * fy)
        radius = np.sqrt(np.clip(cov / 255.0, 0, 1)) * (cell * 0.7)
        dot = dist <= radius                          # hay tinta de este canal
        out[..., ch] = np.where(dot, 0.0, 255.0)      # la tinta absorbe ese canal
    arr[..., :3] = np.clip(out, 0, 255).astype(np.uint8)
    return arr


class ColorHalftoneDialog(AdjustmentDialog):
    title = t("fx.t.color_halftone")
    heavy = True
    preview_downscale = True

    def build_controls(self):
        self.add_slider_row("cell", t("fx.l.cell_size"), 3, 20, 6)

    def compute(self, arr):
        return apply_color_halftone(arr, max(3, int(round(self.val("cell") * self._cur_scale))))


def apply_spin_blur(arr, amount):
    """Desenfoque GIRATORIO: promedia varias copias de la imagen giradas pequeños
    ángulos en torno al centro (sensación de rotación)."""
    if amount <= 0:
        return arr
    ndi = _ndi()
    rgb = arr[..., :3].astype(np.float32)
    n = 11
    acc = np.zeros_like(rgb)
    for ang in np.linspace(-amount / 2.0, amount / 2.0, n):
        acc += ndi.rotate(rgb, ang, axes=(0, 1), reshape=False,
                          order=1, mode="nearest")
    arr[..., :3] = np.clip(acc / n, 0, 255).astype(np.uint8)
    return arr


class SpinBlurDialog(AdjustmentDialog):
    title = t("fx.t.spin_blur")
    heavy = True
    preview_downscale = True

    def build_controls(self):
        self.add_slider_row("amount", t("fx.l.amount"), 1, 45, 12)

    def compute(self, arr):
        return apply_spin_blur(arr, self.val("amount"))   # ángulo: no escala


def apply_kaleidoscope(arr, segments, angle):
    """Caleidoscopio: refleja un sector angular alrededor del centro N veces."""
    ndi = _ndi()
    segments = max(2, int(round(segments)))
    h, w = arr.shape[0], arr.shape[1]
    cy, cx = (h - 1) / 2.0, (w - 1) / 2.0
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    dx, dy = xx - cx, yy - cy
    r = np.sqrt(dx * dx + dy * dy)
    th = np.arctan2(dy, dx) + np.radians(angle)
    wedge = 2.0 * np.pi / segments
    a = np.mod(th, wedge)
    a = np.minimum(a, wedge - a)                  # espejo dentro de la cuña
    a = a + np.radians(angle)
    sx = cx + r * np.cos(a)
    sy = cy + r * np.sin(a)
    out = np.empty_like(arr)
    for c in range(arr.shape[2]):
        out[..., c] = ndi.map_coordinates(arr[..., c], [sy, sx], order=1, mode="reflect")
    return out


class KaleidoscopeDialog(AdjustmentDialog):
    title = t("fx.t.kaleidoscope")
    heavy = True
    preview_downscale = True

    def build_controls(self):
        self.add_slider_row("segments", t("fx.l.segments"), 2, 24, 6)
        self.add_angle_row("angle", t("eff.angle"), -180, 180, 0)

    def compute(self, arr):
        return apply_kaleidoscope(arr, self.val("segments"), self.val("angle"))


# ===================================================== Coordenadas polares
def apply_polar_coords(arr, mode_idx):
    """Coordenadas polares: 0 = rectangular a polar (envuelve la imagen en
    torno al centro: la fila superior queda en el centro y la inferior en el
    borde exterior), 1 = polar a rectangular (la inversa: desenrolla)."""
    ndi = _ndi()
    h, w = arr.shape[0], arr.shape[1]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cx, cy = (w - 1) / 2.0, (h - 1) / 2.0
    rmax = max(1.0, min(cx, cy))
    dos_pi = 2.0 * np.pi
    if mode_idx == 0:
        # Para cada pixel de SALIDA (x,y): su angulo (0 arriba, horario) elige
        # la columna de origen y su radio la fila (centro=arriba, borde=abajo).
        dx = xx - cx
        dy = yy - cy
        th = np.mod(np.arctan2(dx, -dy), dos_pi)      # 0 en las 12, horario
        r = np.sqrt(dx * dx + dy * dy)
        sx = th / dos_pi * (w - 1)
        sy = np.clip(r / rmax, 0.0, 1.0) * (h - 1)
    else:
        # Inversa: la columna es el angulo y la fila el radio.
        th = xx / max(1.0, float(w - 1)) * dos_pi
        r = yy / max(1.0, float(h - 1)) * rmax
        sx = cx + r * np.sin(th)
        sy = cy - r * np.cos(th)
    out = np.empty_like(arr)
    for c in range(arr.shape[2]):
        out[..., c] = ndi.map_coordinates(arr[..., c], [sy, sx], order=1, mode="nearest")
    return out


class PolarCoordinatesDialog(AdjustmentDialog):
    title = t("fx.t.polar")
    heavy = True
    preview_downscale = True

    def build_controls(self):
        self.add_combo_row("dir", t("fx.polar.dir"),
                           [t("fx.polar.rect2pol"), t("fx.polar.pol2rect")], 0)

    def compute(self, arr):
        return apply_polar_coords(arr, self.combo_index("dir"))


# ===================================================== Cristalizar (Voronoi)
def apply_crystallize(arr, cell, seed=0):
    """Cristalizar: tesela la imagen en celdas Voronoi irregulares de color
    plano. Un punto-semilla por celda de una rejilla (con desplazamiento
    aleatorio pero de semilla FIJA, para una preview estable) y cada pixel
    copia el color del punto mas cercano de su vecindario 3x3 de celdas."""
    cell = max(2, int(round(cell)))
    h, w = arr.shape[0], arr.shape[1]
    gh = (h + cell - 1) // cell + 2        # celdas + 1 de borde a cada lado
    gw = (w + cell - 1) // cell + 2
    rng = np.random.default_rng(seed)
    jx = rng.random((gh, gw), dtype=np.float32)
    jy = rng.random((gh, gw), dtype=np.float32)
    # Posicion absoluta de la semilla de cada celda (la rejilla empieza en -1)
    seed_x = (np.arange(gw, dtype=np.float32)[None, :] - 1.0 + jx) * cell
    seed_y = (np.arange(gh, dtype=np.float32)[:, None] - 1.0 + jy) * cell
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cell_i = (yy / cell).astype(np.int32) + 1
    cell_j = (xx / cell).astype(np.int32) + 1
    best_d = np.full((h, w), np.inf, dtype=np.float32)
    best_sx = np.zeros((h, w), dtype=np.float32)
    best_sy = np.zeros((h, w), dtype=np.float32)
    for di in (-1, 0, 1):
        for dj in (-1, 0, 1):
            sx = seed_x[cell_i + di, cell_j + dj]
            sy = seed_y[cell_i + di, cell_j + dj]
            d = (xx - sx) ** 2 + (yy - sy) ** 2
            gana = d < best_d
            best_d[gana] = d[gana]
            best_sx[gana] = sx[gana]
            best_sy[gana] = sy[gana]
    px = np.clip(np.rint(best_sx), 0, w - 1).astype(np.int32)
    py = np.clip(np.rint(best_sy), 0, h - 1).astype(np.int32)
    return arr[py, px]


class CrystallizeDialog(AdjustmentDialog):
    title = t("fx.t.crystallize")
    heavy = True
    preview_downscale = True

    def build_controls(self):
        self.add_slider_row("cell", t("fx.l.cell_size"), 3, 100, 16)

    def compute(self, arr):
        return apply_crystallize(arr, max(2, int(round(self.val("cell") * self._cur_scale))))


# ===================================================== Vidrio esmerilado
def apply_frosted_glass(arr, radius, seed=0):
    """Vidrio esmerilado: cada pixel toma el de un punto AL AZAR a menos de
    'radius' px (dispersion uniforme; semilla fija para una preview estable).
    El picado aleatorio, sin interpolar, es lo que da el grano del vidrio."""
    radius = float(radius)
    if radius <= 0:
        return arr
    h, w = arr.shape[0], arr.shape[1]
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    nx = xx + rng.uniform(-radius, radius, (h, w)).astype(np.float32)
    ny = yy + rng.uniform(-radius, radius, (h, w)).astype(np.float32)
    px = np.clip(np.rint(nx), 0, w - 1).astype(np.int32)
    py = np.clip(np.rint(ny), 0, h - 1).astype(np.int32)
    return arr[py, px]


class FrostedGlassDialog(AdjustmentDialog):
    title = t("fx.t.frosted")
    heavy = True
    preview_downscale = True

    def build_controls(self):
        self.add_slider_row("radius", t("eff.radius"), 1, 50, 6)

    def compute(self, arr):
        return apply_frosted_glass(arr, self.val("radius") * self._cur_scale)


# ===================================================== Duotono / tritono
def apply_duotone(arr, c_shadow, c_mid, c_high, tritone=False):
    """Duotono/tritono: reproduce la imagen con dos o tres TINTAS mapeando la
    luminosidad (sombras -> [medios] -> luces), como los virajes de imprenta.
    Pariente del mapa de degradado, con la tinta intermedia opcional.
    Conserva el alfa; c_* son (r,g,b)."""
    rgb = arr[..., :3].astype(np.float32)
    lum = rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114
    if tritone:
        xp = np.array([0.0, 127.5, 255.0], dtype=np.float32)
        stops = np.array([c_shadow, c_mid, c_high], dtype=np.float32)
    else:
        xp = np.array([0.0, 255.0], dtype=np.float32)
        stops = np.array([c_shadow, c_high], dtype=np.float32)
    x = np.arange(256, dtype=np.float32)
    lut = np.stack([np.interp(x, xp, stops[:, ch]) for ch in range(3)], axis=1)
    idx = np.clip(lum, 0, 255).astype(np.int32)
    arr[..., :3] = np.clip(lut[idx], 0, 255).astype(np.uint8)
    return arr


class DuotoneDialog(AdjustmentDialog):
    title = t("fx.t.duotone")

    def build_controls(self):
        self.add_combo_row("inks", t("fx.duo.mode"),
                           [t("fx.duo.two"), t("fx.duo.three")], 0)
        self.add_color_row("shadow", t("adj.shadows"), "#1a2a55")
        self.add_color_row("mid", t("adj.midtones"), "#8a6a4a")
        self.add_color_row("high", t("adj.highlights"), "#f5efe0")

    def compute(self, arr):
        return apply_duotone(arr, self.color("shadow"), self.color("mid"),
                             self.color("high"), self.combo_index("inks") == 1)


# =============================================================================
# ROTACIÓN LIBRE (imagen completa, ángulo arbitrario)
# =============================================================================
class FreeRotateDialog(OverlayPanel):
    """Rotación LIBRE de la imagen completa (todas las capas) con vista previa
    en vivo. NO es un AdjustmentDialog (esos operan sobre la capa activa a
    tamaño fijo): aquí giran todas las capas y, al Aceptar, el lienzo puede
    AMPLIARSE al rectángulo envolvente (FreeRotateCommand). La preview gira
    las capas manteniendo el tamaño del lienzo (la ampliación se aplica solo
    al confirmar) y REEMPLAZA los objetos layer.image; los originales se
    conservan aparte y se restauran tal cual al aceptar o cancelar."""

    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.canvas = main_window.get_current_canvas()
        self.setWindowTitle(t("fx.rotate_free.title", default="Rotación libre"))
        self.setStyleSheet(_panel_qss() + theme.spinbox_qss() + theme.checkbox_qss())

        from models.destino_edicion import DestinoDocumento
        self._destino = (DestinoDocumento(self.canvas) if self.canvas is not None
                         and bool(getattr(self.canvas, 'layers', None)) else None)
        self._valid = bool(self._destino) and self._destino.vigente(
            self.main_window, exigir_activo=True)
        self._angle = 0.0
        if self._valid:
            self._orig_layers = list(self.canvas.layers)
            self._orig_images = [layer.image for layer in self.canvas.layers]
            self._orig_masks = [layer.mask for layer in self.canvas.layers]

        # Debounce: girar todas las capas a resolución completa en cada tic
        # del dial sería un derroche; se recalcula al parar (120 ms)
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(120)
        self._preview_timer.timeout.connect(self._update_preview)

        from PySide6.QtWidgets import QDoubleSpinBox, QCheckBox
        from widgets.effect_controls import AngleDial
        root = self.body_layout

        fila = QHBoxLayout()
        self.dial = AngleDial(84)
        self.dial.angleChanged.connect(self._on_dial)
        fila.addWidget(self.dial)
        fila.addSpacing(12)
        col = QVBoxLayout()
        col.addStretch()
        lbl = QLabel(t("fx.rotate_free.angle", default="Ángulo:"))
        col.addWidget(lbl)
        self.spin = QDoubleSpinBox()
        self.spin.setRange(-180.0, 180.0)
        self.spin.setDecimals(1)
        self.spin.setSingleStep(1.0)
        self.spin.setSuffix(" °")
        self.spin.setFixedWidth(110)
        self.spin.valueChanged.connect(self._on_spin)
        col.addWidget(self.spin)
        col.addStretch()
        fila.addLayout(col)
        fila.addStretch()
        root.addLayout(fila)

        self.expand_check = QCheckBox(
            t("fx.rotate_free.expand", default="Ampliar el lienzo (sin recortar las esquinas)"))
        self.expand_check.setChecked(True)
        root.addWidget(self.expand_check)
        nota = QLabel(t("fx.rotate_free.note",
                        default="La vista previa recorta al lienzo actual; la ampliación se aplica al Aceptar."))
        nota.setWordWrap(True)
        nota.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-style: italic; font-size: 11px;")
        root.addWidget(nota)

        root.addSpacing(6)
        btns = QHBoxLayout()
        reset_btn = QPushButton(t("common.reset"))
        reset_btn.clicked.connect(self.reset)
        btns.addWidget(reset_btn)
        btns.addStretch()
        ok_btn = QPushButton(t("btn.accept", default="Aceptar"))
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton(t("btn.cancel", default="Cancelar"))
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(ok_btn)
        btns.addWidget(cancel_btn)
        root.addLayout(btns)

        self.setMinimumWidth(360)

        # Mientras el overlay está abierto, la preview POSEE las capas: se
        # bloquea pintar sobre el lienzo dejando pasar zoom/pan (mismo patrón
        # que AdjustmentDialog). El filtro se retira al cerrarse el panel.
        if self._valid and self.canvas is not None:
            self.canvas.installEventFilter(self)
            self.closed.connect(self._unlock_canvas)

    # ---------------------------------------------------------- controles
    def _on_dial(self, deg):
        self.spin.blockSignals(True)
        self.spin.setValue(deg)
        self.spin.blockSignals(False)
        self._angle = float(deg)
        self._preview_timer.start()

    def _on_spin(self, value):
        self.dial.setAngle(value)
        self._angle = float(value)
        self._preview_timer.start()

    def reset(self):
        self.spin.setValue(0.0)   # sincroniza dial y dispara la preview

    # ---------------------------------------------------------- preview
    def _rotated_keep_size(self, img, degrees):
        """Gira 'img' alrededor del centro manteniendo el tamaño del lienzo
        (para la vista previa; el resultado final lo hace FreeRotateCommand)."""
        from PySide6.QtGui import QTransform
        W, H = self.canvas.base_width, self.canvas.base_height
        out = QImage(W, H, QImage.Format_ARGB32)
        out.fill(0)
        p = QPainter(out)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        p.setTransform(QTransform().translate(W / 2.0, H / 2.0)
                       .rotate(degrees).translate(-W / 2.0, -H / 2.0))
        p.drawImage(0, 0, img)
        p.end()
        return out

    def _update_preview(self):
        if not self._valid:
            return
        if not self._destino.vigente(self.main_window, exigir_activo=True):
            self._invalidar_destino()
            return
        a = self._angle
        if abs(a) < 0.05:
            self._restore()
            return
        for layer, orig, mask in zip(self._orig_layers,
                                     self._orig_images, self._orig_masks):
            layer.image = self._rotated_keep_size(orig, a)
            if mask is not None:
                layer.mask = self._rotated_keep_size(
                    mask.convertToFormat(QImage.Format_ARGB32), a
                ).convertToFormat(QImage.Format_Grayscale8)
        self._destino.actualizar_revision()
        self.canvas.update()

    def _restore(self):
        """Devuelve a cada capa sus objetos ORIGINALES (misma identidad)."""
        if not self._valid:
            return False
        if not self._destino.vigente(self.main_window, exigir_activo=False):
            return False
        for layer, orig, mask in zip(self._orig_layers,
                                     self._orig_images, self._orig_masks):
            layer.image = orig
            layer.mask = mask
        self._destino.actualizar_revision()
        self.canvas.update()
        return True

    def _invalidar_destino(self):
        if not self._valid:
            return
        self._valid = False
        self._preview_timer.stop()
        status = getattr(self.main_window, "status_bar", None)
        if status is not None:
            status.showMessage(t("edit.target_changed"), 5000)
        OverlayPanel.reject(self)

    # ---------------------------------------------------------- cierre
    def accept(self):
        self._preview_timer.stop()
        if self._valid:
            if not self._restore():
                self._invalidar_destino()
                return
            if abs(self._angle) >= 0.05:
                from models.layer_commands import FreeRotateCommand
                antes = (self.canvas.base_width, self.canvas.base_height)
                self.canvas.undo_stack.push(FreeRotateCommand(
                    self.canvas, self._angle,
                    expand=self.expand_check.isChecked()))
                # Si el lienzo cambió de tamaño, reencuadrar la vista
                if (self.canvas.base_width, self.canvas.base_height) != antes:
                    self.main_window.fit_canvas_to_screen()
        super().accept()

    def reject(self):
        self._preview_timer.stop()
        if self._valid:
            self._restore()
        super().reject()

    # ---- bloqueo del pintado sobre el lienzo mientras el overlay está abierto ----
    def eventFilter(self, obj, event):
        if obj is self.canvas:
            et = event.type()
            if et in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease,
                      QEvent.MouseButtonDblClick):
                if event.button() == Qt.LeftButton:
                    return True
            elif et == QEvent.MouseMove:
                if event.buttons() & Qt.LeftButton:
                    return True
        return super().eventFilter(obj, event)

    def _unlock_canvas(self):
        if self.canvas is not None:
            self.canvas.removeEventFilter(self)
