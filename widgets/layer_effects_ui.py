from i18n import t
# widgets/layer_effects_ui.py
"""Panel UNIFICADO de EFECTOS DE CAPA no destructivos (estilo "Estilo de capa").

Un solo overlay (OverlayPanel, anclado al lienzo — NO una ventana del SO) con:
  - a la IZQUIERDA, la lista de los efectos disponibles, cada uno con una casilla
    para activarlo/desactivarlo;
  - a la DERECHA, un QStackedWidget con el panel de controles del efecto
    seleccionado (reutiliza los mismos controles que antes).

NO toca los píxeles: edita los objetos-efecto pegados a la capa
(models/layer_effects) y la vista previa en vivo sale GRATIS del compositor
(render_with_effects). Aceptar consolida UN LayerEffectsCommand (deshacer por
parámetros); Cancelar restaura la lista de efectos previa. Uno de cada tipo.

`EffectControls` (+ subclases) = los controles de un efecto, embebibles en el
stack. `EfectosDialog` = el overlay que orquesta lista + stack + preview + undo.
"""
from PySide6.QtWidgets import (QVBoxLayout, QHBoxLayout, QLabel, QSlider,
                               QSpinBox, QPushButton, QWidget, QStackedWidget,
                               QListWidget, QListWidgetItem)
from PySide6.QtGui import QColor
from PySide6.QtCore import Qt, QEvent, QTimer
import theme
from widgets.overlay_panel import OverlayPanel
from adjustments import _panel_qss   # estilo base común de los paneles overlay
from models.layer_effects import (Sombra, Trazo, Resplandor, SuperposicionColor,
                                  SombraInterior, SuperposicionDegradado,
                                  Bisel, Satinado, clonar_efectos)
from models.layer_commands import LayerEffectsCommand


# =============================================================================
# CONTROLES DE UN EFECTO (widget embebible en el stack del panel unificado)
# =============================================================================
class EffectControls(QWidget):
    """Controles de UN efecto. Las subclases definen `efecto_cls`,
    `build_controls()` y `_apply_to_effect()`. Al cambiar cualquier control,
    vuelca los valores en `self._effect` y avisa con `on_change` (para la
    preview del panel). Reutiliza los constructores add_slider_row/add_color_row."""
    efecto_cls = None

    def __init__(self, effect, on_change, parent=None):
        super().__init__(parent)
        self._effect = effect
        self._on_change = on_change
        self._sliders = {}
        self._defaults = {}
        self._colors = {}
        self._color_defaults = {}
        self._color_repaints = {}
        self._row_labels = []

        self.controls_layout = QVBoxLayout(self)
        self.controls_layout.setContentsMargins(0, 0, 0, 0)
        self.controls_layout.setSpacing(8)
        self.build_controls()
        self._equalize_labels()
        self.controls_layout.addStretch()

    # ---- constructores de controles (mínimos, locales a los efectos) ----
    def add_slider_row(self, key, label, minv, maxv, default):
        row = QHBoxLayout()
        lbl = QLabel(label)
        lbl.setMinimumWidth(80)
        row.addWidget(lbl)
        self._row_labels.append(lbl)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(minv, maxv)
        slider.setValue(int(default))
        slider.setMinimumWidth(200)
        spin = QSpinBox()
        spin.setRange(minv, maxv)
        spin.setValue(int(default))
        slider.valueChanged.connect(spin.setValue)
        spin.valueChanged.connect(slider.setValue)
        slider.valueChanged.connect(lambda _=None: self._changed())
        row.addWidget(slider)
        row.addWidget(spin)
        self.controls_layout.addLayout(row)
        self._sliders[key] = slider
        self._defaults[key] = int(default)
        return slider

    def add_color_row(self, key, label, default="#000000", pick_title=None):
        from widgets.colors_panel import imago_pick_color
        row = QHBoxLayout()
        lbl = QLabel(label)
        lbl.setMinimumWidth(80)
        row.addWidget(lbl)
        self._row_labels.append(lbl)
        btn = QPushButton()
        btn.setFixedSize(60, 22)
        self._colors[key] = QColor(default)
        self._color_defaults[key] = QColor(default)
        titulo = pick_title or label.rstrip(":")

        def repaint():
            c = self._colors[key]
            btn.setStyleSheet("background-color: %s; border: 1px solid %s;"
                              % (c.name(), theme.BORDER))

        def pick():
            def _apply(c):
                self._colors[key] = c
                repaint()
                self._changed()
            imago_pick_color(self._colors[key], self, titulo, on_accept=_apply)

        repaint()
        self._color_repaints[key] = repaint
        btn.clicked.connect(pick)
        row.addWidget(btn)
        row.addStretch()
        self.controls_layout.addLayout(row)
        return btn

    def _equalize_labels(self):
        if not self._row_labels:
            return
        w = max([80] + [lbl.sizeHint().width() for lbl in self._row_labels])
        for lbl in self._row_labels:
            lbl.setFixedWidth(w)

    # ---- lectura de controles ----
    def val(self, key):
        return self._sliders[key].value()

    def color_hex(self, key):
        return self._colors[key].name()

    # ---- a implementar por las subclases ----
    def build_controls(self):
        pass

    def _apply_to_effect(self):
        """Vuelca los valores de los controles en self._effect."""
        pass

    # ---- reacción a los cambios ----
    def _changed(self):
        self._apply_to_effect()
        if self._on_change is not None:
            self._on_change()

    def reset(self):
        for key, slider in self._sliders.items():
            slider.setValue(self._defaults[key])
        for key, col in self._color_defaults.items():
            self._colors[key] = QColor(col)
            self._color_repaints[key]()
        self._changed()


# --------------------------------------------------------- controles concretos
class SombraControls(EffectControls):
    efecto_cls = Sombra

    def build_controls(self):
        e = self._effect
        self.add_slider_row("dx", t("fx.l.offset_x", default="Desplaz. X:"), -100, 100, e.dx)
        self.add_slider_row("dy", t("fx.l.offset_y", default="Desplaz. Y:"), -100, 100, e.dy)
        self.add_slider_row("radio", t("fx.l.blur", default="Desenfoque:"), 0, 100, int(e.radio))
        self.add_slider_row("opacidad", t("fx.l.opacity"), 0, 100, e.opacidad)
        self.add_color_row("color", t("fx.l.color", default="Color:"), e.color)

    def _apply_to_effect(self):
        self._effect.dx = self.val("dx")
        self._effect.dy = self.val("dy")
        self._effect.radio = float(self.val("radio"))
        self._effect.opacidad = self.val("opacidad")
        self._effect.color = self.color_hex("color")
        self._effect.activo = True


class SombraInteriorControls(EffectControls):
    efecto_cls = SombraInterior

    def build_controls(self):
        e = self._effect
        self.add_slider_row("dx", t("fx.l.offset_x", default="Desplaz. X:"), -100, 100, e.dx)
        self.add_slider_row("dy", t("fx.l.offset_y", default="Desplaz. Y:"), -100, 100, e.dy)
        self.add_slider_row("radio", t("fx.l.blur", default="Desenfoque:"), 0, 100, int(e.radio))
        self.add_slider_row("opacidad", t("fx.l.opacity"), 0, 100, e.opacidad)
        self.add_color_row("color", t("fx.l.color", default="Color:"), e.color)

    def _apply_to_effect(self):
        self._effect.dx = self.val("dx")
        self._effect.dy = self.val("dy")
        self._effect.radio = float(self.val("radio"))
        self._effect.opacidad = self.val("opacidad")
        self._effect.color = self.color_hex("color")
        self._effect.activo = True


class ResplandorControls(EffectControls):
    efecto_cls = Resplandor

    def build_controls(self):
        e = self._effect
        self.add_slider_row("radio", t("fx.l.blur", default="Desenfoque:"), 0, 100, int(e.radio))
        self.add_slider_row("opacidad", t("fx.l.opacity"), 0, 100, e.opacidad)
        self.add_color_row("color", t("fx.l.color", default="Color:"), e.color)

    def _apply_to_effect(self):
        self._effect.radio = float(self.val("radio"))
        self._effect.opacidad = self.val("opacidad")
        self._effect.color = self.color_hex("color")
        self._effect.activo = True


class TrazoControls(EffectControls):
    efecto_cls = Trazo

    def build_controls(self):
        e = self._effect
        self.add_slider_row("grosor", t("fx.l.thickness", default="Grosor:"), 1, 100, e.grosor)
        self.add_slider_row("opacidad", t("fx.l.opacity"), 0, 100, e.opacidad)
        self.add_color_row("color", t("fx.l.color", default="Color:"), e.color)

    def _apply_to_effect(self):
        self._effect.grosor = self.val("grosor")
        self._effect.opacidad = self.val("opacidad")
        self._effect.color = self.color_hex("color")
        self._effect.activo = True


class BiselControls(EffectControls):
    efecto_cls = Bisel

    def build_controls(self):
        e = self._effect
        self.add_slider_row("grosor", t("fx.l.thickness", default="Grosor:"), 1, 100, e.grosor)
        self.add_slider_row("angulo", t("fx.l.angle", default="Ángulo:"), 0, 360, e.angulo)
        self.add_slider_row("opacidad", t("fx.l.opacity"), 0, 100, e.opacidad)
        self.add_color_row("color_luz", t("fx.l.light", default="Luz:"), e.color_luz)
        self.add_color_row("color_sombra", t("fx.l.shadow", default="Sombra:"), e.color_sombra)

    def _apply_to_effect(self):
        self._effect.grosor = self.val("grosor")
        self._effect.angulo = self.val("angulo")
        self._effect.opacidad = self.val("opacidad")
        self._effect.color_luz = self.color_hex("color_luz")
        self._effect.color_sombra = self.color_hex("color_sombra")
        self._effect.activo = True


class SatinadoControls(EffectControls):
    efecto_cls = Satinado

    def build_controls(self):
        e = self._effect
        self.add_slider_row("angulo", t("fx.l.angle", default="Ángulo:"), 0, 360, e.angulo)
        self.add_slider_row("distancia", t("fx.l.distance", default="Distancia:"), 0, 100, e.distancia)
        self.add_slider_row("radio", t("fx.l.blur", default="Desenfoque:"), 0, 100, int(e.radio))
        self.add_slider_row("opacidad", t("fx.l.opacity"), 0, 100, e.opacidad)
        self.add_color_row("color", t("fx.l.color", default="Color:"), e.color)

    def _apply_to_effect(self):
        self._effect.angulo = self.val("angulo")
        self._effect.distancia = self.val("distancia")
        self._effect.radio = float(self.val("radio"))
        self._effect.opacidad = self.val("opacidad")
        self._effect.color = self.color_hex("color")
        self._effect.activo = True


class SuperposicionColorControls(EffectControls):
    efecto_cls = SuperposicionColor

    def build_controls(self):
        e = self._effect
        self.add_slider_row("opacidad", t("fx.l.opacity"), 0, 100, e.opacidad)
        self.add_color_row("color", t("fx.l.color", default="Color:"), e.color)

    def _apply_to_effect(self):
        self._effect.opacidad = self.val("opacidad")
        self._effect.color = self.color_hex("color")
        self._effect.activo = True


class SuperposicionDegradadoControls(EffectControls):
    efecto_cls = SuperposicionDegradado

    def build_controls(self):
        e = self._effect
        self.add_slider_row("angulo", t("fx.l.angle", default="Ángulo:"), 0, 360, e.angulo)
        self.add_slider_row("opacidad", t("fx.l.opacity"), 0, 100, e.opacidad)
        self.add_color_row("color1", t("fx.l.color1", default="Color 1:"), e.color1)
        self.add_color_row("color2", t("fx.l.color2", default="Color 2:"), e.color2)

    def _apply_to_effect(self):
        self._effect.angulo = self.val("angulo")
        self._effect.opacidad = self.val("opacidad")
        self._effect.color1 = self.color_hex("color1")
        self._effect.color2 = self.color_hex("color2")
        self._effect.activo = True


# --- Registro de efectos: tipo -> (controles, clave i18n del nombre) ----------
# El ORDEN es el de la lista de la izquierda del panel (y el de composición).
_EFECTOS = [
    ("sombra", SombraControls, "fx.layer.shadow"),
    ("sombra_interior", SombraInteriorControls, "fx.layer.inner_shadow"),
    ("resplandor", ResplandorControls, "fx.layer.glow"),
    ("trazo", TrazoControls, "fx.layer.stroke"),
    ("bisel", BiselControls, "fx.layer.bevel"),
    ("satinado", SatinadoControls, "fx.layer.satin"),
    ("superposicion", SuperposicionColorControls, "fx.layer.color_overlay"),
    ("degradado", SuperposicionDegradadoControls, "fx.layer.gradient"),
]
_ORDEN = [tp for tp, _c, _k in _EFECTOS]
_CONTROLES = {tp: cls for tp, cls, _k in _EFECTOS}
_NOMBRES = {tp: clave for tp, _c, clave in _EFECTOS}


def nombre_efecto(effect):
    """Nombre traducido del efecto, para mostrarlo en el panel de Capas."""
    clave = _NOMBRES.get(getattr(effect, "tipo", None))
    return t(clave) if clave else getattr(effect, "tipo", "?")


def efectos_disponibles():
    """Lista (tipo, nombre_traducido) para el menú fx del panel de Capas."""
    return [(tp, t(clave)) for tp, _c, clave in _EFECTOS]


def _list_indicator_qss():
    """Estilo de la casilla de cada fila de la lista (mismo look que checkbox_qss,
    pero con el selector de QListWidget)."""
    return f"""
        QListWidget::indicator {{ width: 13px; height: 13px; border-radius: 3px;
            border: 1px solid {theme.BORDER_CHECK}; background: {theme.BG_BUTTON}; }}
        QListWidget::indicator:hover {{ border: 1px solid {theme.ACCENT}; }}
        QListWidget::indicator:checked {{ background: {theme.ACCENT};
            border: 1px solid {theme.ACCENT}; image: url(:/icons/check.png); }}
    """


# =============================================================================
# PANEL UNIFICADO
# =============================================================================
class EfectosDialog(OverlayPanel):
    """Overlay unificado de efectos de capa: lista con casillas a la izquierda y
    controles del efecto seleccionado a la derecha. `tipo` (opcional) es el efecto
    que queda seleccionado y activado al abrir (el elegido desde el botón fx)."""

    def __init__(self, main_window, tipo=None, destino=None):
        super().__init__(main_window)
        self.main_window = main_window
        from models.destino_edicion import DestinoCapa
        if destino is None:
            canvas = main_window.get_current_canvas()
            if canvas is not None and canvas.get_active_layer() is not None:
                destino = DestinoCapa(canvas, canvas.active_layer_index)
        self._destino = destino
        self.canvas = destino.canvas if destino is not None else None
        self.setWindowTitle(t("layer.fx.title", default="Efectos de capa"))
        self.setStyleSheet(_panel_qss() + theme.slider_qss() + theme.spinbox_qss()
                           + theme.list_qss() + _list_indicator_qss())

        self._valid = bool(self._destino) and self._destino.indice_actual(
            self.main_window, exigir_revision=False, exigir_activo=True) is not None
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(140)
        self._preview_timer.timeout.connect(self._rebuild_effects)
        if self._valid:
            self._layer_index = self._destino.indice_actual(
                self.main_window, exigir_revision=False, exigir_activo=True)
            self._layer = self._destino.layer
            self._effects_before = clonar_efectos(self._layer.effects)
            self._effects_expected = self._revision_effects(self._layer.effects)
            # Una instancia por tipo: la existente en la capa o una por defecto.
            # 'enabled' = tipos presentes en la capa (aplicados).
            self._effects_by_type = {}
            self._enabled = set()
            for tp in _ORDEN:
                existing = next((e for e in self._layer.effects
                                 if getattr(e, "tipo", None) == tp), None)
                if existing is not None:
                    self._effects_by_type[tp] = existing
                    self._enabled.add(tp)
                else:
                    self._effects_by_type[tp] = _CONTROLES[tp].efecto_cls()

        body = self.body_layout
        cols = QHBoxLayout()
        cols.setSpacing(8)
        body.addLayout(cols, 1)

        # --- Izquierda: lista de efectos con casilla ---
        self.list = QListWidget()
        self.list.setFixedWidth(170)
        self._items_by_type = {}
        self.list.blockSignals(True)
        for tp, _cls, clave in _EFECTOS:
            it = QListWidgetItem(t(clave))
            it.setData(Qt.UserRole, tp)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            checked = self._valid and tp in self._enabled
            it.setCheckState(Qt.Checked if checked else Qt.Unchecked)
            self.list.addItem(it)
            self._items_by_type[tp] = it
        self.list.blockSignals(False)
        cols.addWidget(self.list)

        # --- Derecha: controles del efecto seleccionado ---
        self.stack = QStackedWidget()
        self._controls_by_type = {}
        for tp, cls, _clave in _EFECTOS:
            effect = self._effects_by_type[tp] if self._valid else cls.efecto_cls()
            ctrl = cls(effect, on_change=(lambda tp=tp: self._on_ctrl_change(tp)))
            self.stack.addWidget(ctrl)
            self._controls_by_type[tp] = ctrl
        cols.addWidget(self.stack, 1)

        self.list.currentRowChanged.connect(self._on_row_changed)
        self.list.itemChanged.connect(self._on_item_changed)

        # --- Botones ---
        body.addSpacing(6)
        btns = QHBoxLayout()
        reset_btn = QPushButton(t("common.reset"))
        reset_btn.clicked.connect(self._reset_current)
        btns.addWidget(reset_btn)
        btns.addStretch()
        ok_btn = QPushButton(t("btn.accept", default="Aceptar"))
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton(t("btn.cancel", default="Cancelar"))
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(ok_btn)
        btns.addWidget(cancel_btn)
        body.addLayout(btns)

        self.setMinimumWidth(540)

        if self._valid and self.canvas is not None:
            self.canvas.installEventFilter(self)
            self.closed.connect(self._unlock_canvas)

        # Selección inicial: el tipo elegido desde el botón fx queda seleccionado
        # Y activado; si no se indica, se selecciona el primero sin forzar nada.
        start = tipo if tipo in _ORDEN else _ORDEN[0]
        if self._valid and tipo in _ORDEN and tipo not in self._enabled:
            self._enabled.add(tipo)
            self.list.blockSignals(True)
            self._items_by_type[tipo].setCheckState(Qt.Checked)
            self.list.blockSignals(False)
        self.list.setCurrentRow(_ORDEN.index(start))
        if self._valid:
            self._rebuild_effects()   # aplica el estado inicial + preview

    # ---- selección / casillas ----
    def _on_row_changed(self, row):
        if 0 <= row < self.stack.count():
            self.stack.setCurrentIndex(row)

    def _on_item_changed(self, item):
        if not self._valid:
            return
        tp = item.data(Qt.UserRole)
        if item.checkState() == Qt.Checked:
            self._enabled.add(tp)
        else:
            self._enabled.discard(tp)
        self._request_rebuild()

    def _on_ctrl_change(self, tp):
        """Se tocó un control del efecto 'tp': si no estaba activo, se activa
        (marcando su casilla) y se recompone; si ya lo estaba, basta recomponer."""
        if not self._valid:
            return
        if tp not in self._enabled:
            self._enabled.add(tp)
            self.list.blockSignals(True)
            self._items_by_type[tp].setCheckState(Qt.Checked)
            self.list.blockSignals(False)
        self._request_rebuild()

    def _reset_current(self):
        row = self.list.currentRow()
        if 0 <= row < len(_ORDEN):
            self._controls_by_type[_ORDEN[row]].reset()

    # ---- aplicar el estado a la capa + preview ----
    @staticmethod
    def _revision_effects(effects):
        return tuple(tuple(sorted(effect.to_dict().items())) for effect in effects)

    def _indice_destino(self, exigir_activo=True):
        if not self._valid:
            return None
        return self._destino.indice_actual(
            self.main_window, exigir_revision=False,
            exigir_activo=exigir_activo)

    def _invalidar_destino(self):
        if not self._valid:
            return
        self._valid = False
        self._preview_timer.stop()
        status = getattr(self.main_window, "status_bar", None)
        if status is not None:
            status.showMessage(t("edit.target_changed"), 5000)
        OverlayPanel.reject(self)

    def _sincronizar_effects(self):
        index = self._indice_destino(exigir_activo=True)
        if index is None:
            self._invalidar_destino()
            return False
        self._layer.effects = [self._effects_by_type[tp] for tp in _ORDEN
                               if tp in self._enabled]
        for e in self._layer.effects:
            e.activo = True
        self._layer_index = index
        self._effects_expected = self._revision_effects(self._layer.effects)
        return True

    def _request_rebuild(self):
        """Agrupa la rafaga de eventos de slider antes de recalcular efectos."""
        if self._sincronizar_effects():
            self._preview_timer.start()

    def _rebuild_effects(self):
        self._preview_timer.stop()
        if not self._sincronizar_effects():
            return
        self._layer._fx_cache = None
        self._layer._fx_cache_key = None
        self.canvas.update()

    # ---- ciclo de vida ----
    def accept(self):
        self._preview_timer.stop()
        if self._valid:
            self._rebuild_effects()
            index = self._indice_destino(exigir_activo=True)
            if index is None:
                self._invalidar_destino()
                return
            after = clonar_efectos(self._layer.effects)
            before = self._effects_before
            if [e.to_dict() for e in after] != [e.to_dict() for e in before]:
                self.canvas.undo_stack.push(
                    LayerEffectsCommand(self.canvas, index,
                                        before, after, t("layer.fx.title")))
        super().accept()

    def reject(self):
        self._preview_timer.stop()
        if self._valid:
            index = self._indice_destino(exigir_activo=False)
            revision = self._revision_effects(self._layer.effects)
            if index is not None and revision == self._effects_expected:
                self._layer.effects = self._effects_before
                self._layer._fx_cache = None
                self._layer._fx_cache_key = None
                self.canvas.update()
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
