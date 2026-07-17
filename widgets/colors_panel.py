from i18n import t
# widgets/colors_panel.py
import os
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
                             QPushButton, QSlider, QLabel, QLineEdit)
from PySide6.QtGui import QColor, QPainter, QPen, QIcon
from PySide6.QtCore import Qt, QSize, QFile
import theme


def imago_pick_color(initial, parent=None, title="", show_alpha=False, on_accept=None):
    """Selector de color de Imago para los sitios que necesitan UN color concreto
    (color de efecto, fondo de IA...). Abre un OVERLAY hijo del lienzo (Wayland-safe,
    NO una ventana del SO; mismo aspecto que el editor del panel) con previsualizacion
    y botones Aceptar/Cancelar; al Aceptar llama on_accept(color). NO bloquea ni
    devuelve el color (patron por CALLBACK, como los overlays de Ajustes/Efectos):
    la logica que use el color va dentro de on_accept. `parent` sirve para localizar
    la ventana principal (parent.window())."""
    from widgets.color_dialog import ImagoColorPickerOverlay   # perezoso: evita ciclo
    main_window = parent.window() if parent is not None else None
    picker = ImagoColorPickerOverlay(QColor(initial), main_window, title=title,
                                     show_alpha=show_alpha, on_accept=on_accept)
    picker.open_editor()
    return picker


def _paint_checker(painter, w, h, tile=5,
                   c1=QColor(200, 200, 200), c2=QColor(160, 160, 160)):
    """Pinta un tablero de transparencia en el area indicada."""
    y = 0
    while y < h:
        x = 0
        while x < w:
            painter.fillRect(x, y, tile, tile,
                             c1 if ((x // tile + y // tile) % 2 == 0) else c2)
            x += tile
        y += tile


class ColorSwatch(QWidget):
    """Cuadro de color que muestra la transparencia (tablero) cuando el alfa < 255.
    Con color None queda "vacio" (hueco). Clic izquierdo/derecho -> callbacks."""

    def __init__(self, on_click=None, on_right=None, border="auto", parent=None):
        super().__init__(parent)
        self._color = QColor("#000000")
        self._empty = False
        self._on_click = on_click
        self._on_right = on_right
        self._border = border
        self.setCursor(Qt.PointingHandCursor)

    def set_color(self, color):
        if color is None:
            self._empty = True
        else:
            self._empty = False
            self._color = QColor(color)
        self.update()

    def set_border(self, border):
        """Cambia el borde del cuadro ('auto' = contraste automatico, o un color
        p.ej. el acento para marcarlo como activo)."""
        self._border = border
        self.update()

    def is_empty(self):
        return self._empty

    def color(self):
        return None if self._empty else QColor(self._color)

    def paintEvent(self, event):
        p = QPainter(self)
        w, h = self.width(), self.height()
        if self._empty:
            p.fillRect(0, 0, w, h, QColor(theme.BG_HOVER))
            p.setPen(QPen(QColor(theme.BORDER_FAINT)))
            p.drawRect(0, 0, w - 1, h - 1)
            p.end()
            return
        if self._color.alpha() < 255:
            _paint_checker(p, w, h)
        p.fillRect(0, 0, w, h, self._color)
        # Borde que contrasta con el relleno: claro sobre colores oscuros y
        # oscuro sobre colores claros. Asi el cuadro blanco SI tiene borde, y
        # sigue viendose aunque se intercambien primario y secundario.
        if self._border == "auto":
            c = self._color
            lum = 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
            bcol = QColor(95, 95, 95) if lum >= 128 else QColor(140, 140, 140)
        else:
            bcol = QColor(self._border)
        p.setPen(QPen(bcol))
        p.drawRect(0, 0, w - 1, h - 1)
        p.end()

    def mousePressEvent(self, event):
        if self._empty:
            return
        if event.button() == Qt.LeftButton and self._on_click:
            self._on_click(event)
        elif event.button() == Qt.RightButton and self._on_right:
            self._on_right(event)


class _DefaultColorsIcon(QWidget):
    """Icono clicable (fondo transparente, sin aspecto de boton) con dos cuadros
    montados negro/blanco. Al pulsarlo restablece primario=negro, secundario=blanco."""

    def __init__(self, on_click, parent=None):
        super().__init__(parent)
        self._on_click = on_click
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(t("color.reset"))

    def paintEvent(self, event):
        p = QPainter(self)
        m = min(self.width(), self.height())
        s = int(m * 0.48)          # lado de cada cuadrito
        gap = int(m * 0.28)        # desplazamiento del montaje
        # Cuadro BLANCO detras (abajo-derecha)
        p.fillRect(gap, gap, s, s, QColor("#ffffff"))
        p.setPen(QPen(QColor("#777777")))
        p.drawRect(gap, gap, s - 1, s - 1)
        # Cuadro NEGRO delante (arriba-izquierda)
        p.fillRect(0, 0, s, s, QColor("#000000"))
        p.setPen(QPen(QColor("#777777")))
        p.drawRect(0, 0, s - 1, s - 1)
        p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._on_click()


class ColorsPanel(QWidget):
    BOX = 40          # lado de cada cuadro de color
    OFF = 20          # desplazamiento del montaje primario/secundario
    GAP = 23          # lado de los huecos (swap / reset)

    def __init__(self, main_window, dock=None):
        super().__init__()
        self.main_window = main_window
        self.dock = dock  # vestigial: antiguo dock flotante, ya no se usa
        self.is_updating = False
        # Selector compacto opcional (pie del panel de Herramientas) que refleja
        # estos mismos colores; lo asigna main.py. Ver MiniColorSelector.
        self.mirror = None

        self.setStyleSheet("background: transparent; color: %s;" % theme.TEXT)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # ───────────────────────── SECCION SUPERIOR ─────────────────────────
        top_layout = QHBoxLayout()
        BOX, OFF, GAP = self.BOX, self.OFF, self.GAP
        area = OFF + BOX

        self.swatch_area = QWidget()
        self.swatch_area.setFixedSize(area, area)

        # Secundario (detras, abajo-derecha)
        self.secondary_box = ColorSwatch(on_click=self.open_secondary_color_dialog,
                                         parent=self.swatch_area)
        self.secondary_box.setGeometry(OFF, OFF, BOX, BOX)
        self.secondary_box.setToolTip(t("color.secondary_tip").replace("\\n", "\n"))

        # Primario (delante, arriba-izquierda)
        self.preview_box = ColorSwatch(on_click=self.open_color_dialog,
                                       parent=self.swatch_area)
        self.preview_box.setGeometry(0, 0, BOX, BOX)
        self.preview_box.setToolTip(t("color.primary_tip").replace("\\n", "\n"))

        # Boton intercambiar en el hueco superior (entre los dos cuadros)
        self.btn_swap = QPushButton(self.swatch_area)
        # Si existe icons/swap.png se usa esa imagen; si no, el simbolo ⇄.
        if QFile.exists(":/icons/swap.png"):
            self.btn_swap.setIcon(theme.icono(":/icons/swap.png"))
            self.btn_swap.setIconSize(QSize(GAP - 6, GAP - 6))
        else:
            self.btn_swap.setText("\u21c4")
        self.btn_swap.setGeometry(BOX + 0, - 3, GAP, GAP)
        self.btn_swap.setCursor(Qt.PointingHandCursor)
        self.btn_swap.setToolTip(t("color.swap"))
        self.btn_swap.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: none; color: {theme.TEXT_BRIGHT}; font-size: 13px; }}
            QPushButton:hover {{ color: {theme.TEXT}; }}
            QPushButton:pressed {{ color: {theme.ACCENT}; }}
        """)
        self.btn_swap.clicked.connect(self.swap_colors)

        # Icono restablecer (negro/blanco) en el hueco inferior izquierdo
        self.default_icon = _DefaultColorsIcon(self.reset_default_colors,
                                               parent=self.swatch_area)
        self.default_icon.setGeometry(0, BOX + 2, GAP, GAP)

        # Apilado: secundario detras, primario delante, controles encima
        self.secondary_box.lower()
        self.preview_box.raise_()
        self.btn_swap.raise_()
        self.default_icon.raise_()

        top_layout.addWidget(self.swatch_area, 0, Qt.AlignTop)
        top_layout.addSpacing(8)

        # Columna derecha: boton "mas" arriba-derecha + fila Hex
        right_col = QVBoxLayout()
        right_col.setSpacing(6)
        more_row = QHBoxLayout()
        more_row.addStretch()
        self.btn_more = QPushButton(t("color.more.btn", default=" Mas >>"))
        self.btn_more.setCursor(Qt.PointingHandCursor)
        self.btn_more.setToolTip(t("color.more"))
        self.btn_more.setFixedHeight(20)
        self.btn_more.setStyleSheet(f"""
            QPushButton {{
                background-color: {theme.BG_BUTTON}; border: 1px solid {theme.BORDER}; border-radius: 3px;
                color: {theme.TEXT}; font-size: 11px; padding: 1px 12px;
            }}
            QPushButton:hover {{ background-color: {theme.BG_HOVER_RAISED}; border: 1px solid {theme.ACCENT}; }}
            QPushButton:pressed {{ background-color: {theme.BG_PRESSED}; }}
        """)
        self.btn_more.clicked.connect(self.open_color_dialog)
        more_row.addWidget(self.btn_more)
        right_col.addLayout(more_row)

        hex_row = QHBoxLayout()
        hex_row.setSpacing(5)
        hex_label = QLabel(t("color.hex"))
        hex_label.setStyleSheet(f"font-size: 11px; color: {theme.TEXT_DIM}; background: transparent;")
        hex_row.addStretch()
        hex_row.addWidget(hex_label)
        self.hex_input = QLineEdit("#000000")
        self.hex_input.setMaxLength(7)
        self.hex_input.setFixedSize(70, 20)
        self.hex_input.setStyleSheet(f"""
            QLineEdit {{
                background: transparent; border: 1px solid {theme.BORDER_FAINT}; color: white;
                font-family: monospace; font-size: 11px; padding-left: 3px; border-radius: 3px;
            }}
            QLineEdit:focus {{ border: 1px solid {theme.ACCENT}; }}
            QLineEdit:disabled {{ color: {theme.TEXT_DISABLED}; border: 1px solid {theme.BORDER_DIM}; }}
        """)
        self.hex_input.textChanged.connect(self.on_hex_changed)
        hex_row.addWidget(self.hex_input)
        right_col.addLayout(hex_row)
        right_col.setContentsMargins(0, 0, 0, 0)

        # 'Más' y Hex arriba, alineados con la parte alta de las muestras. Se
        # envuelve en un widget alineado ARRIBA (en vez de un addStretch al final)
        # para que la fila superior NO se vuelva expansible en vertical: con el
        # panel empotrado en un splitter y sobrándole alto, ese stretch hacía que
        # top_layout absorbiera espacio y abriera un hueco entre las muestras y la
        # paleta (la paleta y los sliders se iban al centro en vez de quedar justo
        # debajo). Con el widget alineado arriba, todo el contenido se agrupa
        # arriba y el hueco sobrante queda al fondo (addStretch de main_layout).
        right_col_widget = QWidget()
        right_col_widget.setStyleSheet("background: transparent;")
        right_col_widget.setLayout(right_col)

        top_layout.addWidget(right_col_widget, 0, Qt.AlignTop)
        main_layout.addLayout(top_layout)
        main_layout.addSpacing(9)

        # ───────────────────────── PALETA FIJA (24) ─────────────────────────
        grid_layout = QGridLayout()
        grid_layout.setSpacing(4)
        preset_colors = [
            "#000000", "#404040", "#808080", "#C0C0C0", "#FFFFFF", "#800000", "#804000", "#808000",
            "#FF0000", "#FF8000", "#FFFF00", "#00FF00", "#00FFFF", "#0000FF", "#FF00FF", "#800080",
            "#FF8080", "#FFC080", "#FFFF80", "#80FF80", "#80FFFF", "#8080FF", "#FF80FF", "#A04000"
        ]
        for index, hex_color in enumerate(preset_colors):
            btn = QPushButton()
            btn.setFixedSize(18, 18)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{ background-color: {hex_color}; border: 1px solid {theme.BORDER_FAINT}; border-radius: 2px; }}
                QPushButton:hover {{ border: 1px solid {theme.ACCENT}; }}
            """)
            btn.clicked.connect(lambda checked=False, c=hex_color: self._use_primary(QColor(c)))
            btn.setContextMenuPolicy(Qt.CustomContextMenu)
            btn.customContextMenuRequested.connect(
                lambda pos, c=hex_color: self.set_secondary_color(QColor(c)))
            grid_layout.addWidget(btn, index // 8, index % 8)
        main_layout.addLayout(grid_layout)

        # Las muestras personalizadas (guardar color / importar paleta .gpl) ya
        # NO viven aqui: se muestran en el selector de color (widgets/color_dialog),
        # debajo de la paleta fija. Siguen persistiendo en QSettings
        # (colors/custom_swatches), asi que el panel y el selector comparten datos.

        # ───────────────────────── SLIDERS R/G/B/A ──────────────────────────
        self.advanced_widget = QWidget()
        self.advanced_widget.setStyleSheet("background: transparent;")
        adv_layout = QVBoxLayout(self.advanced_widget)
        adv_layout.setContentsMargins(0, 4, 0, 0)
        adv_layout.setSpacing(6)
        self.r_slider, self.r_val_lbl = self.create_slider_row("R:", adv_layout)
        self.g_slider, self.g_val_lbl = self.create_slider_row("G:", adv_layout)
        self.b_slider, self.b_val_lbl = self.create_slider_row("B:", adv_layout)
        self.a_slider, self.a_val_lbl = self.create_slider_row("A:", adv_layout)
        self.a_slider.setValue(255)
        self.r_slider.valueChanged.connect(self.on_sliders_interacted)
        self.g_slider.valueChanged.connect(self.on_sliders_interacted)
        self.b_slider.valueChanged.connect(self.on_sliders_interacted)
        self.a_slider.valueChanged.connect(self.on_sliders_interacted)
        main_layout.addWidget(self.advanced_widget)
        main_layout.addStretch()

        # Inicializacion de ambos colores
        canvas = self.main_window.get_current_canvas()
        initial_color = canvas.brush_color if (canvas and hasattr(canvas, 'brush_color')) else QColor("#000000")
        initial_secondary = canvas.brush_color_secondary if (canvas and hasattr(canvas, 'brush_color_secondary')) else QColor("#FFFFFF")
        self.set_active_color(initial_color)
        self.set_secondary_color(initial_secondary)
        if canvas:
            canvas.color_picked_callback = self.on_color_picked

    def _sync_mirror(self):
        """Refleja los dos colores actuales en el selector compacto del panel de
        Herramientas, si está enganchado (main.py lo asigna en self.mirror)."""
        if self.mirror is not None:
            try:
                self.mirror.sync(self.preview_box.color(), self.secondary_box.color())
            except RuntimeError:      # widget ya destruido
                self.mirror = None

    def _use_primary(self, color):
        """Aplica un color como primario."""
        self.set_active_color(color)

    def reset_default_colors(self):
        """Restablece primario=negro, secundario=blanco (como al inicio)."""
        self.set_active_color(QColor("#000000"))
        self.set_secondary_color(QColor("#FFFFFF"))

    # ----------------------------------------------------------------- canvas
    def sync_from_canvas(self, canvas):
        """Sincroniza ambos colores al cambiar de pestana."""
        if not canvas:
            return
        canvas.color_picked_callback = self.on_color_picked
        self.set_active_color(getattr(canvas, 'brush_color', QColor("#000000")), notify_text=False)
        self.set_secondary_color(getattr(canvas, 'brush_color_secondary', QColor("#FFFFFF")))

    def on_color_picked(self, color, is_primary=True):
        """Color capturado por el cuentagotas."""
        if is_primary:
            self._use_primary(color)
        else:
            self.set_secondary_color(color)
        # Si el editor de color en vivo está abierto, reflejar en él la captura
        # (si no, se quedaba mostrando el color anterior y cualquier gesto en el
        # editor volvía a aplicar ese color obsoleto, "pisando" al cuentagotas).
        ed = getattr(self, "_live_editor", None)
        if ed is not None:
            try:
                if ed.isVisible():
                    ed.sync_picked("primary" if is_primary else "secondary")
            except RuntimeError:      # overlay ya destruido (C++ borrado)
                self._live_editor = None

    def set_secondary_color(self, color, refresh_tool=True):
        color = QColor(color)
        canvas = self.main_window.get_current_canvas()
        if canvas:
            canvas.brush_color_secondary = color
            # refresh_tool=False -> solo se guarda el color y se refleja en el
            # panel, SIN repintar la herramienta en vivo sobre el lienzo (lo usa
            # el editor de color en vivo).
            if refresh_tool:
                _t = getattr(canvas, 'current_tool', None)
                if hasattr(_t, 'refresh_live'):
                    _t.refresh_live()
        self.secondary_box.set_color(color)
        self._sync_mirror()

    def swap_colors(self):
        canvas = self.main_window.get_current_canvas()
        if not canvas:
            return
        primario = QColor(canvas.brush_color)
        secundario = QColor(canvas.brush_color_secondary)
        self.set_active_color(secundario)
        self.set_secondary_color(primario)

    def open_secondary_color_dialog(self, event=None):
        self._open_live_editor("secondary")

    def open_color_dialog(self, event=None):
        self._open_live_editor("primary")

    def _open_live_editor(self, active):
        """Abre el editor de color EN VIVO conectado a este panel: los cambios se
        reflejan al momento en el color primario/secundario del panel, sin botones
        de Aceptar/Cancelar. `active` indica cual se edita al abrir.

        Es un OVERLAY HIJO del lienzo (no una ventana del SO): Wayland-safe, con
        topes y arranca arriba-derecha del lienzo, sin bloquearlo (se puede pintar
        con el abierto). Instancia unica: si ya esta abierto y se pulsa el otro
        cuadro, solo cambia el color en edicion (no abre otro)."""
        # Si hay un SELECTOR SUELTO abierto (el que usan Ajustes/Efectos/IA para
        # pedir un color), NO se abre el editor en vivo: cerrarlo perderia el
        # enlace con el efecto que espera ese color. Se trae al frente para avisar.
        active_overlay = getattr(self.main_window, "_active_color_overlay", None)
        if active_overlay is not None and not getattr(active_overlay, "_live", True):
            try:
                active_overlay.raise_()
                active_overlay.setFocus(Qt.OtherFocusReason)
            except RuntimeError:      # overlay ya destruido (C++ borrado)
                pass
            return
        ed = getattr(self, "_live_editor", None)
        if ed is not None:
            try:
                visible = ed.isVisible()
            except RuntimeError:      # overlay ya destruido (C++ borrado)
                ed, visible = None, False
            if ed is not None and visible:
                ed.set_target(active)
                ed.raise_()
                ed.setFocus(Qt.OtherFocusReason)
                return
        from widgets.color_dialog import ImagoColorOverlay
        ed = ImagoColorOverlay(self, active)
        ed.closed.connect(lambda: setattr(self, "_live_editor", None))
        self._live_editor = ed
        ed.open_editor()

    def close_live_editor(self):
        """Cierra el editor de color en vivo si esta abierto. Lo llama la apertura
        de overlays de ajuste/efecto/IA (que no deben convivir con el); los
        dialogos MODALES lo cierran solos via el evento WindowBlocked."""
        ed = getattr(self, "_live_editor", None)
        if ed is not None:
            try:
                ed.reject()
            except RuntimeError:
                pass
            self._live_editor = None

    def create_slider_row(self, name, parent_layout):
        row = QHBoxLayout()
        lbl_name = QLabel(name)
        lbl_name.setFixedWidth(15)
        lbl_name.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {theme.TEXT_DIM}; background: transparent;")
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, 255)
        slider.setStyleSheet(theme.slider_qss())
        lbl_val = QLabel("0")
        lbl_val.setFixedWidth(26)
        lbl_val.setStyleSheet(f"font-size: 11px; color: {theme.TEXT_DIM}; font-family: monospace; background: transparent;")
        row.addWidget(lbl_name)
        row.addWidget(slider)
        row.addWidget(lbl_val)
        parent_layout.addLayout(row)
        return slider, lbl_val

    def set_active_color(self, color, update_sliders=True, update_hex=True, notify_text=True,
                         refresh_tool=True):
        if self.is_updating:
            return
        self.is_updating = True
        color = QColor(color)

        canvas = self.main_window.get_current_canvas()
        if canvas:
            canvas.brush_color = color
            # refresh_tool=False -> solo se guarda el color y se refleja en el
            # panel, SIN repintar la herramienta en vivo sobre el lienzo (lo usa
            # el editor de color en vivo).
            if refresh_tool:
                _t = getattr(canvas, 'current_tool', None)
                if hasattr(_t, 'refresh_live'):
                    _t.refresh_live()

        self.preview_box.set_color(color)
        self._sync_mirror()

        if update_sliders:
            self.r_slider.setValue(color.red())
            self.g_slider.setValue(color.green())
            self.b_slider.setValue(color.blue())
            self.a_slider.setValue(color.alpha())
        self.r_val_lbl.setText(str(color.red()))
        self.g_val_lbl.setText(str(color.green()))
        self.b_val_lbl.setText(str(color.blue()))
        self.a_val_lbl.setText(str(color.alpha()))

        if update_hex:
            self.hex_input.setText(color.name().upper())

        self.is_updating = False

        if notify_text and self.main_window and hasattr(self.main_window, "update_text_color"):
            self.main_window.update_text_color(color)

    def on_sliders_interacted(self):
        if self.is_updating:
            return
        new_color = QColor(self.r_slider.value(), self.g_slider.value(), self.b_slider.value())
        new_color.setAlpha(self.a_slider.value())
        self.set_active_color(new_color, update_sliders=False, update_hex=True)

    def on_hex_changed(self, text):
        if self.is_updating:
            return
        if len(text) == 7 and text.startswith("#"):
            color = QColor(text)
            if color.isValid():
                color.setAlpha(self.a_slider.value())   # conserva la opacidad actual
                self.set_active_color(color, update_sliders=True, update_hex=False)


class MiniColorSelector(QWidget):
    """Selector de color COMPACTO para el pie del panel de Herramientas: repite los
    cuadros primario/secundario superpuestos + el botón de intercambiar + el icono
    de restablecer de la parte alta del panel de Color, con el MISMO aspecto y las
    MISMAS funciones. No lleva lógica propia: DELEGA todo en el ColorsPanel
    principal (abrir el editor en vivo, intercambiar, restablecer) y solo refleja
    los dos colores (ColorsPanel lo mantiene al día vía self.mirror). main.py lo
    muestra siempre que el panel de Color esté CERRADO."""

    def __init__(self, colors_panel, parent=None):
        super().__init__(parent)
        self.colors_panel = colors_panel
        self.setStyleSheet("background: transparent;")

        # El swatch va centrado dentro de la columna de Herramientas.
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 2, 0, 4)

        self.swatch_area = QWidget()

        # Secundario (detrás, abajo-derecha)
        self.secondary_box = ColorSwatch(
            on_click=colors_panel.open_secondary_color_dialog, parent=self.swatch_area)
        self.secondary_box.setToolTip(t("color.secondary_tip").replace("\\n", "\n"))

        # Primario (delante, arriba-izquierda)
        self.preview_box = ColorSwatch(
            on_click=colors_panel.open_color_dialog, parent=self.swatch_area)
        self.preview_box.setToolTip(t("color.primary_tip").replace("\\n", "\n"))

        # Botón intercambiar en el hueco superior (entre los dos cuadros)
        self.btn_swap = QPushButton(self.swatch_area)
        self._tiene_icono_swap = QFile.exists(":/icons/swap.png")
        if self._tiene_icono_swap:
            self.btn_swap.setIcon(theme.icono(":/icons/swap.png"))
        else:
            self.btn_swap.setText("⇄")
        self.btn_swap.setCursor(Qt.PointingHandCursor)
        self.btn_swap.setToolTip(t("color.swap"))
        self.btn_swap.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: none; color: {theme.TEXT_BRIGHT}; font-size: 13px; }}
            QPushButton:hover {{ color: {theme.TEXT}; }}
            QPushButton:pressed {{ color: {theme.ACCENT}; }}
        """)
        self.btn_swap.clicked.connect(colors_panel.swap_colors)

        # Icono restablecer (negro/blanco) en el hueco inferior izquierdo
        self.default_icon = _DefaultColorsIcon(colors_panel.reset_default_colors,
                                               parent=self.swatch_area)

        # Apilado igual que en el panel: secundario detrás, primario delante
        self.secondary_box.lower()
        self.preview_box.raise_()
        self.btn_swap.raise_()
        self.default_icon.raise_()

        root.addWidget(self.swatch_area, 0, Qt.AlignHCenter)

        # Medidas fijas (anchura de la columna de Herramientas, 2 columnas):
        #   BOX = lado de cada cuadro · OFF = desplazamiento del montaje
        #   GAP = lado de los huecos (swap / reset)
        BOX, OFF, GAP = 25, 15, 18
        self.swatch_area.setFixedSize(OFF + BOX, OFF + BOX)
        self.secondary_box.setGeometry(OFF, OFF, BOX, BOX)
        self.preview_box.setGeometry(0, 0, BOX, BOX)
        self.btn_swap.setGeometry(BOX, - 2, GAP, GAP)
        if self._tiene_icono_swap:
            self.btn_swap.setIconSize(QSize(GAP - 6, GAP - 6))
        self.default_icon.setGeometry(0, BOX + 2, GAP, GAP)

        # Estado inicial desde el panel principal.
        self.sync(colors_panel.preview_box.color(), colors_panel.secondary_box.color())

    def sync(self, primary, secondary):
        """Refleja los colores actuales del panel principal en los dos cuadros."""
        self.secondary_box.set_color(secondary)
        self.preview_box.set_color(primary)
