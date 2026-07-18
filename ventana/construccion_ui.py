# construccion_ui.py
"""Construcción de la interfaz de MainWindow (mixin).

Extraído de main.py TAL CUAL (sin cambios de comportamiento): create_menus
(toda la barra de menús con sus acciones e iconos), create_docks (los paneles
EMPOTRADOS en los splitters, con cabeceras, reordenación ▲/▼ y visibilidad de
la columna derecha), la botonera de toggles de paneles, la barra de
herramientas fija, la barra de opciones dinámica y la pantalla de bienvenida.
Todos son métodos que MainWindow.__init__ llama en el mismo orden de siempre,
así que el ORDEN de creación de atributos se conserva tal cual."""
import os

from PySide6.QtCore import Qt, QSize, QFile
from PySide6.QtGui import QAction, QActionGroup, QIcon, QPixmap
from PySide6.QtWidgets import (QWidget, QLabel, QHBoxLayout, QVBoxLayout,
                               QSplitter, QToolBar, QToolButton)

from i18n import t
from utilidades import crear_icono, crear_icono_checkable
from widgets.options_bar import DynamicOptionsBar
from widgets.tools_panel import ToolsPanel
from widgets.layers_panel import LayersPanel
from widgets.colors_panel import ColorsPanel, MiniColorSelector
import theme


# Cabeceras de sección (gris) en el menú IA, que agrupan sus funciones por tipo
# de tarea. Poner en False deja el menú con SOLO separadores (sin rótulos), sin
# tocar nada más: es el interruptor para quitarlas si no convencen.
IA_MENU_CABECERAS = False

# Alto FIJO del panel de Histograma (cabecera incluida), afinado a mano: el
# panel no debe estirarse nunca (ver _update_histogram_height_lock).
ALTO_HISTOGRAMA = 156


class ConstruccionUI:
    def create_panel_toggle_buttons(self, row_layout):
        """Crea los botones de paleta y los integra en el layout horizontal de la barra de menús"""
        # Contenedor horizontal exclusivo para los botones de panel
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 10, 0) # Margen derecho para separarlo del borde de la ventana
        layout.setSpacing(6)

        panel_btn_style = theme.toolbutton_toggle_qss()

        # 1. Botón Herramientas
        self.btn_toggle_tools = QToolButton()
        self.btn_toggle_tools.setCheckable(True)
        self.btn_toggle_tools.setChecked(True)
        self.btn_toggle_tools.setStyleSheet(panel_btn_style)
        if QFile.exists(":/icons/tools_panel.png"): 
            self.btn_toggle_tools.setIcon(crear_icono(":/icons/tools_panel.png"))
        else:
            self.btn_toggle_tools.setText("🛠️")
        self.btn_toggle_tools.setToolTip(t("tooltip.toggle.tools", default="Mostrar/Ocultar Herramientas"))
        layout.addWidget(self.btn_toggle_tools)

        # 2. Botón Historial
        self.btn_toggle_history = QToolButton()
        self.btn_toggle_history.setCheckable(True)
        self.btn_toggle_history.setChecked(True)
        self.btn_toggle_history.setStyleSheet(panel_btn_style)
        if QFile.exists(":/icons/history_panel.png"):
            self.btn_toggle_history.setIcon(crear_icono(":/icons/history_panel.png"))
        else:
            self.btn_toggle_history.setText("⏳")
        self.btn_toggle_history.setToolTip(t("tooltip.toggle.history", default="Mostrar/Ocultar Historial"))
        layout.addWidget(self.btn_toggle_history)

        # 3. Botón Capas
        self.btn_toggle_layers = QToolButton()
        self.btn_toggle_layers.setCheckable(True)
        self.btn_toggle_layers.setChecked(True)
        self.btn_toggle_layers.setStyleSheet(panel_btn_style)
        if QFile.exists(":/icons/layers_panel.png"):
            self.btn_toggle_layers.setIcon(crear_icono(":/icons/layers_panel.png"))
        else:
            self.btn_toggle_layers.setText("🥞")
        self.btn_toggle_layers.setToolTip(t("tooltip.toggle.layers", default="Mostrar/Ocultar Capas"))
        layout.addWidget(self.btn_toggle_layers)

        # 4. Botón Colores
        self.btn_toggle_colors = QToolButton()
        self.btn_toggle_colors.setCheckable(True)
        self.btn_toggle_colors.setChecked(True)
        self.btn_toggle_colors.setStyleSheet(panel_btn_style)
        if QFile.exists(":/icons/colors_panel.png"):
            self.btn_toggle_colors.setIcon(crear_icono(":/icons/colors_panel.png"))
        else:
            self.btn_toggle_colors.setText("🎨")
        self.btn_toggle_colors.setToolTip(t("tooltip.toggle.colors", default="Mostrar/Ocultar Paleta de Colores"))
        layout.addWidget(self.btn_toggle_colors)

        # 5. Botón Histograma en vivo: panel EMPOTRADO en la columna derecha
        # como los demás (se conecta a su contenedor en create_docks).
        self.btn_toggle_histogram = QToolButton()
        self.btn_toggle_histogram.setCheckable(True)
        self.btn_toggle_histogram.setChecked(True)
        self.btn_toggle_histogram.setStyleSheet(panel_btn_style)
        if QFile.exists(":/icons/histogram_panel.png"):
            self.btn_toggle_histogram.setIcon(crear_icono(":/icons/histogram_panel.png"))
        else:
            self.btn_toggle_histogram.setText("📊")
        self.btn_toggle_histogram.setToolTip(t("tooltip.toggle.histogram", default="Mostrar/Ocultar Histograma"))
        layout.addWidget(self.btn_toggle_histogram)

        # 6. Diagnóstico: abre una ventana independiente; no ocupa el splitter.
        self.btn_document_diagnostics = QToolButton()
        self.btn_document_diagnostics.setStyleSheet(theme.toolbutton_flat_qss())
        if QFile.exists(":/icons/layer_properties.png"):
            self.btn_document_diagnostics.setIcon(
                crear_icono(":/icons/layer_properties.png"))
        else:
            self.btn_document_diagnostics.setText(
                t("diagnostics.toggle.fallback"))
        self.btn_document_diagnostics.setToolTip(
            t("tooltip.toggle.diagnostics"))
        self.btn_document_diagnostics.clicked.connect(
            self.open_document_diagnostics)
        layout.addWidget(self.btn_document_diagnostics)

        # El contenedor de botones va a la derecha; el hueco libre lo ocupa la tira de miniaturas.
        row_layout.addWidget(container)

    def create_fixed_toolbar(self):
        self.fixed_toolbar = QToolBar(t("ui.toolbar_standard"), self)
        self.fixed_toolbar.setMovable(False)
        self.fixed_toolbar.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.fixed_toolbar.setStyleSheet(theme.toolbar_qss())
    
        self.fixed_toolbar.addAction(self.new_action)  
        self.fixed_toolbar.addAction(self.open_action) 
        self.fixed_toolbar.addAction(self.save_action) 
        self.fixed_toolbar.addSeparator()
        self.fixed_toolbar.addAction(self.cut_action)
        self.fixed_toolbar.addAction(self.copy_action)
        self.fixed_toolbar.addAction(self.paste_action)
        self.fixed_toolbar.addAction(self.crop_action)
        self.fixed_toolbar.addAction(self.deselect_action)
        self.fixed_toolbar.addSeparator()
        self.fixed_toolbar.addAction(self.undo_action)
        self.fixed_toolbar.addAction(self.redo_action)
        self.fixed_toolbar.addSeparator()
        self.fixed_toolbar.addAction(self.grid_action)
        self.fixed_toolbar.addAction(self.rulers_action)
        # El botón de Guías (alternable) ocupa el sitio donde antes estaba la
        # Paleta de Colores. Es la MISMA QAction que en el menú Ver (creada en
        # create_menus, que se construye antes): ambas se sincronizan solas.
        self.fixed_toolbar.addAction(self.guides_action)

        # (Los controles de zoom se han movido a la barra de estado inferior.)

    def create_dynamic_options_bar(self):
        self.options_bar = DynamicOptionsBar(self)

    def _panel_with_header(self, panel, title, header_buttons=None):
        """Envuelve un panel en un contenedor con una cabecera (franja de título)
        encima. El contenedor es lo que se mete en el splitter; el panel interno
        queda intacto. Mostrar/ocultar y la persistencia operan sobre el
        contenedor (así la cabecera se oculta con su panel).
        'header_buttons': lista opcional de (texto, tooltip, slot) que añade
        pequeños botones a la derecha de la cabecera (reordenar ▲/▼).
        El contenedor expone ._header_label y ._header_buttons por si hay que
        retocarlos después."""
        container = QWidget()
        v = QVBoxLayout(container)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        if header_buttons:
            header = QWidget()
            header.setObjectName("PanelHeaderBar")
            header.setStyleSheet(theme.panel_header_bar_qss())
            h = QHBoxLayout(header)
            h.setContentsMargins(0, 0, 4, 0)
            h.setSpacing(2)
            label = QLabel(title)
            h.addWidget(label)
            h.addStretch(1)
            container._header_label = label
            container._header_buttons = []
            for texto, tooltip, slot in header_buttons:
                b = QToolButton()
                b.setText(texto)
                b.setToolTip(tooltip)
                b.setFocusPolicy(Qt.NoFocus)
                b.setFixedSize(18, 18)
                b.clicked.connect(slot)
                h.addWidget(b)
                container._header_buttons.append(b)
            v.addWidget(header)
        else:
            header = QLabel(title)
            header.setStyleSheet(theme.panel_header_qss())
            v.addWidget(header)
        v.addWidget(panel)
        return container

    def _update_right_column_visibility(self):
        """Oculta la columna derecha entera (right_splitter) si todos sus
        paneles están ocultos; la muestra si alguno sigue abierto. Así el lienzo
        recupera el espacio cuando no queda ningún panel a la derecha."""
        any_visible = (self.btn_toggle_layers.isChecked() or
                       self.btn_toggle_history.isChecked() or
                       self.btn_toggle_colors.isChecked() or
                       self.btn_toggle_histogram.isChecked())
        self.right_splitter.setVisible(any_visible)
        self._update_histogram_height_lock()

    def _update_histogram_height_lock(self):
        """Alto FIJO del panel de Histograma (ALTO_HISTOGRAMA), con la
        excepción del gotcha documentado de Color: si el contenedor mantiene
        su maximumHeight cuando es el ÚNICO hijo visible del right_splitter,
        el splitter (y con él el root_splitter) hereda ese máximo y la
        interfaz entera se descuadra. Cuando el Histograma queda solo se le
        suelta el máximo (el contenido conserva su alto fijo y el hueco
        sobrante lo deja vacío el stretch del contenedor); al volver a haber
        otro panel visible se re-fija."""
        container = getattr(self, "histogram_container", None)
        if container is None:
            return
        solo = (self.btn_toggle_histogram.isChecked()
                and not (self.btn_toggle_layers.isChecked()
                         or self.btn_toggle_history.isChecked()
                         or self.btn_toggle_colors.isChecked()))
        if solo:
            container.setMinimumHeight(ALTO_HISTOGRAMA)
            container.setMaximumHeight(16777215)   # QWIDGETSIZE_MAX
        else:
            container.setFixedHeight(ALTO_HISTOGRAMA)

    def _apply_right_stretch_factors(self):
        """Reaplica los factores de estiramiento de la columna derecha POR
        IDENTIDAD (los setStretchFactor van por índice y el usuario puede
        reordenar los paneles con ▲/▼): Capas e Historial elásticos; Color e
        Histograma mantienen su alto natural sin estirarse (siempre por
        stretch, nunca setFixedHeight: ver el comentario de create_docks)."""
        fijos = (self.colors_container,
                 getattr(self, "histogram_container", None))
        for i in range(self.right_splitter.count()):
            w = self.right_splitter.widget(i)
            self.right_splitter.setStretchFactor(i, 0 if w in fijos else 1)

    def _move_right_panel(self, clave, delta):
        """Mueve un panel de la columna derecha ('layers'/'history'/'colors'/
        'histogram') una posición arriba o abajo, conservando el
        alto de cada panel (los tamaños viajan con su panel, no con la posición)."""
        container = getattr(self, f"{clave}_container", None)
        if container is None:
            return
        idx = self.right_splitter.indexOf(container)
        nuevo = idx + delta
        if idx < 0 or nuevo < 0 or nuevo >= self.right_splitter.count():
            return
        sizes = self.right_splitter.sizes()
        self.right_splitter.insertWidget(nuevo, container)
        sizes.insert(nuevo, sizes.pop(idx))
        self.right_splitter.setSizes(sizes)
        self._apply_right_stretch_factors()

    def _right_panel_order(self):
        """Orden actual de la columna derecha como claves ('layers',...)."""
        orden = []
        for i in range(self.right_splitter.count()):
            w = self.right_splitter.widget(i)
            if w is self.layers_container: orden.append("layers")
            elif w is self.history_container: orden.append("history")
            elif w is self.colors_container: orden.append("colors")
            elif w is getattr(self, "histogram_container", None): orden.append("histogram")
        return orden

    def _update_tools_color_selector_visibility(self):
        """El selector de color del pie de Herramientas se muestra cuando el panel
        de Color está CERRADO (si está abierto, el control ya está ahí) Y la opción
        de Preferencias está activada."""
        selector = getattr(self, "tools_color_selector", None)
        if selector is None:
            return
        activado = self.settings.value("panels/mini_color_selector", True, type=bool)
        color_cerrado = not self.btn_toggle_colors.isChecked()
        self.tools_panel.set_color_selector_visible(activado and color_cerrado)

    def on_tools_reordered(self):
        """Tras reordenar las herramientas (arrastre en el panel o «Restaurar
        orden por defecto»): persiste el orden nuevo y re-sincroniza el
        desplegable de la barra de opciones con el mismo criterio de siempre
        (por columnas: columna izquierda entera y luego la derecha)."""
        ids = self.tools_panel.tool_order()
        self.settings.setValue("panels/tools_order", ",".join(ids))
        self.options_bar.reorder_tool_combo(ids[0::2] + ids[1::2])

    def create_docks(self):
        # (Nombre histórico: ya no crea docks flotantes, sino que empotra los
        # paneles en los splitters. Se conserva el nombre por simplicidad.)
        canvas_actual = self.get_current_canvas()

        # Panel Herramientas — EMPOTRADO como primera celda del splitter raíz
        # (columna estrecha de ancho fijo, ~76px). Ya no es una ventana flotante
        # Qt.Tool: el splitter lo mantiene pegado a la izquierda del lienzo.
        self.tools_panel = ToolsPanel(self)
        # Título corto: "Herramientas" no cabe en la columna de 76px.
        self.tools_container = self._panel_with_header(
            self.tools_panel, t("panel.tools_short"))
        self.tools_container.setFixedWidth(76)
        self.root_splitter.insertWidget(0, self.tools_container)
        self.btn_toggle_tools.toggled.connect(self.tools_container.setVisible)

        # ── Columna derecha EMPOTRADA: splitter vertical con los paneles
        #    reordenables, como tercera celda del splitter raíz.
        #    Ya no son ventanas flotantes Qt.Tool: redimensionables entre sí.
        self.right_splitter = QSplitter(Qt.Vertical)
        self.right_splitter.setObjectName("RightSplitter")
        self.right_splitter.setChildrenCollapsible(False)
        self.right_splitter.setStyleSheet(theme.splitter_qss())

        # Botones ▲/▼ de la cabecera: reordenan el panel dentro de la columna
        # derecha (petición del usuario: cada cual con su orden preferido).
        def _botones_mover(clave):
            return [("▲", t("panel.move_up", default="Subir este panel"),
                     lambda checked=False, k=clave: self._move_right_panel(k, -1)),
                    ("▼", t("panel.move_down", default="Bajar este panel"),
                     lambda checked=False, k=clave: self._move_right_panel(k, +1))]

        # Panel Capas (envuelto con cabecera; el contenedor es lo que va al
        # splitter y lo que muestran/ocultan el toggle y la persistencia).
        self.layers_panel = LayersPanel(canvas_actual)
        self.layers_container = self._panel_with_header(
            self.layers_panel, t("panel.layers"), header_buttons=_botones_mover("layers"))
        self.right_splitter.addWidget(self.layers_container)
        self.btn_toggle_layers.toggled.connect(self.layers_container.setVisible)

        # Panel Historial. OJO: HistoryPanel se acopla a un undo_stack concreto en
        # su __init__ (no admite re-acoplado), por eso se RECREA al cambiar de
        # pestaña (ver on_tab_changed), reemplazándolo DENTRO de su contenedor.
        from widgets.history_panel import HistoryPanel
        self.history_view = HistoryPanel(canvas_actual, self)
        self.history_container = self._panel_with_header(
            self.history_view, t("panel.history"), header_buttons=_botones_mover("history"))
        # Orden POR DEFECTO (primer arranque, sin orden guardado): Historial - Capas -
        # Color. Capas ya se añadió (índice 0); insertamos Historial DELANTE en el 0.
        # (El usuario puede reordenar con ▲/▼; su orden se persiste y tiene prioridad.)
        self.right_splitter.insertWidget(0, self.history_container)
        self.btn_toggle_history.toggled.connect(self.history_container.setVisible)

        # Panel Colores. El 2º arg del constructor era el antiguo dock (vestigial,
        # nunca se usaba); ahora es opcional y no se pasa.
        self.colors_panel = ColorsPanel(self)
        self.colors_container = self._panel_with_header(
            self.colors_panel, t("panel.colors"), header_buttons=_botones_mover("colors"))
        self.right_splitter.addWidget(self.colors_container)
        self.btn_toggle_colors.toggled.connect(self.colors_container.setVisible)

        # Panel Histograma en vivo — EMPOTRADO, por defecto ARRIBA del todo
        # (Histograma · Historial · Capas · Color), reordenable con ▲/▼ y de
        # ALTO FIJO (156 px: no se estira ni arrastrando el separador). El
        # contenido lleva su propio alto fijo y el contenedor un stretch al
        # final: cuando el Histograma queda como ÚNICO panel visible,
        # _update_histogram_height_lock le suelta el máximo al contenedor (el
        # gotcha documentado de Color: un maximumHeight en el único hijo
        # visible lo hereda el right_splitter y descuadra la interfaz) y el
        # hueco sobrante queda vacío, con el contenido a su alto de siempre.
        # Su sondeo solo corre visible (hideEvent lo para: oculto cuesta cero).
        from widgets.histogram_panel import HistogramaWidget
        self.histogram_view = HistogramaWidget(self)
        self.histogram_container = self._panel_with_header(
            self.histogram_view, t("histogram.title"),
            header_buttons=_botones_mover("histogram"))
        cabecera = self.histogram_container._header_label.parentWidget()
        self.histogram_view.setFixedHeight(
            max(80, ALTO_HISTOGRAMA - cabecera.sizeHint().height()))
        self.histogram_container.layout().addStretch(1)
        self.right_splitter.insertWidget(0, self.histogram_container)
        self.btn_toggle_histogram.toggled.connect(self.histogram_container.setVisible)
        self._update_histogram_height_lock()

        # Selector de color compacto al pie del panel de Herramientas: repite los
        # cuadros primario/secundario + intercambiar + restablecer del panel de
        # Color y delega en él. Se ve siempre que el panel de Color esté CERRADO,
        # así no se duplica el control. El panel de Color lo mantiene
        # sincronizado vía self.mirror.
        self.tools_color_selector = MiniColorSelector(self.colors_panel)
        self.colors_panel.mirror = self.tools_color_selector
        self.tools_panel.set_color_selector(self.tools_color_selector)
        self.btn_toggle_colors.toggled.connect(
            lambda _checked: self._update_tools_color_selector_visibility())
        self._update_tools_color_selector_visibility()

        # Si se ocultan todos los paneles de la derecha, la columna entera (el
        # right_splitter) se oculta para que el lienzo recupere ese espacio; al
        # volver a mostrar cualquiera, reaparece.
        for _btn in (self.btn_toggle_layers, self.btn_toggle_history,
                     self.btn_toggle_colors, self.btn_toggle_histogram):
            _btn.toggled.connect(lambda _checked: self._update_right_column_visibility())

        # La columna derecha es la tercera celda del splitter raíz.
        self.root_splitter.addWidget(self.right_splitter)

        # El centro (lienzo) se queda el espacio elástico; Herramientas (fijo) y
        # columna derecha conservan su tamaño preferido.
        self.root_splitter.setStretchFactor(0, 0)  # herramientas
        self.root_splitter.setStretchFactor(1, 1)  # centro (lienzo)
        self.root_splitter.setStretchFactor(2, 0)  # columna derecha

        # Dentro de la columna derecha, Color NO se estira: Capas e Historial son
        # los elásticos (stretch 1) y Color mantiene su alto (stretch 0). Se usa
        # stretch —no setFixedHeight— a propósito: fijar el máximo de Color hacía
        # que, al quedar solo (Capas e Historial ocultos), el right_splitter y con
        # él el root_splitter heredaran ese máximo y la interfaz se descuadrara.
        # Se aplican POR IDENTIDAD (helper) porque el orden puede cambiar (▲/▼).
        self._apply_right_stretch_factors()

        # Tamaños iniciales aproximados a los antiguos de las paletas (Fase 8:
        # persistencia real en QSettings). Color arranca a su alto natural.
        self.root_splitter.setSizes([76, 900, 230])
        color_h = self.colors_container.sizeHint().height()
        self.right_splitter.setSizes([ALTO_HISTOGRAMA, 300, 260, color_h])

    def _build_welcome_widget(self):
        """Pantalla de inicio (sin lienzos abiertos): logo + identidad, botones de
        acción (Nuevo / Abrir) y lista de archivos recientes clicable. También se
        puede arrastrar una imagen sobre la ventana para abrirla."""
        from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                                       QPushButton)
        import theme

        root = QWidget()
        root.setStyleSheet("background-color: %s;" % theme.BG_WINDOW)
        outer = QVBoxLayout(root)

        card = QVBoxLayout()
        card.setSpacing(8)

        # Logo
        logo = QLabel()
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if QFile.exists(":/icons/imago.png"):
            logo.setPixmap(QPixmap(":/icons/imago.png").scaled(
                96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        card.addWidget(logo)

        # Título y coletilla
        title = QLabel("Imago")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color: %s; font-size: 30px; font-weight: bold;"
                            " font-family: 'Segoe UI';" % theme.TEXT)
        card.addWidget(title)
        tagline = QLabel(t("app.tagline"))
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tagline.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 13px; font-family: {theme.FONT};")
        card.addWidget(tagline)

        card.addSpacing(12)

        # Botones de acción
        btns = QHBoxLayout()
        btns.setAlignment(Qt.AlignmentFlag.AlignCenter)
        btn_new = QPushButton("  " + t("welcome.new"))
        btn_open = QPushButton("  " + t("welcome.open"))
        for b, icon, slot in ((btn_new, ":/icons/nuevo.png", self.new_file),
                              (btn_open, ":/icons/abrir.png", self.open_file)):
            b.setStyleSheet(theme.panel_action_button_qss())
            b.setMinimumWidth(150)
            b.setMinimumHeight(32)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            if QFile.exists(icon):
                b.setIcon(theme.icono(icon))
                b.setIconSize(QSize(18, 18))
            b.clicked.connect(slot)
            btns.addWidget(b)
        card.addLayout(btns)

        # Recientes como MINIATURAS (solo imagen, sin nombre), centradas y que
        # crecen hacia los lados según haya más.
        recent = [p for p in self._load_recent() if os.path.exists(p)]
        if recent:
            card.addSpacing(16)
            rec_lbl = QLabel(t("welcome.recent"))
            rec_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            rec_lbl.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 12px; font-weight: bold;")
            card.addWidget(rec_lbl)
            rec_row = QHBoxLayout()
            rec_row.setSpacing(8)
            rec_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
            for p in recent[:8]:
                rec_row.addWidget(self._make_recent_thumb(p))
            card.addLayout(rec_row)

        # Pista de arrastrar y soltar
        card.addSpacing(10)
        drop_hint = QLabel(t("welcome.drop"))
        drop_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_hint.setStyleSheet(f"color: {theme.TEXT_HINT}; font-size: 11px; font-style: italic;")
        card.addWidget(drop_hint)

        # Centrar el bloque vertical­mente MANTENIÉNDOLO COMPACTO: los stretches
        # de arriba y abajo absorben todo el espacio sobrante, así el contenido no
        # se estira aunque haya recientes; solo se desplaza para quedar centrado.
        outer.addStretch(1)
        outer.addLayout(card)
        outer.addStretch(1)
        return root

    def _make_recent_thumb(self, path):
        """Miniatura clicable (solo imagen, sin nombre) para los recientes de la
        pantalla de inicio. Al pulsar abre el archivo; el tooltip muestra el nombre."""
        from PySide6.QtWidgets import QPushButton
        import theme
        btn = QPushButton()
        btn.setFixedSize(72, 72)
        btn.setIconSize(QSize(60, 60))
        pm = self._thumbnail_pixmap(path, 60)
        if pm is not None:
            btn.setIcon(QIcon(pm))
        btn.setToolTip(os.path.basename(path))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            "QPushButton { background-color: %s; border: 1px solid %s; border-radius: 4px; }"
            "QPushButton:hover { background-color: %s; border: 1px solid %s; }"
            % (theme.BG_DARK, theme.BORDER, theme.BG_BUTTON, theme.ACCENT))
        btn.clicked.connect(lambda: self.open_path(path))
        return btn

    def create_menus(self):
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu(t("menu.file"))

        self.new_action = QAction(t("menu.file.new"), self)
        self.new_action.setShortcut("Ctrl+N")
        self.new_action.setIcon(crear_icono(":/icons/nuevo.png"))
        self.new_action.triggered.connect(self.new_file)
        file_menu.addAction(self.new_action)

        self.open_action = QAction(t("menu.file.open"), self)
        self.open_action.setShortcut("Ctrl+O")
        self.open_action.setIcon(crear_icono(":/icons/abrir.png"))
        self.open_action.triggered.connect(self.open_file)
        file_menu.addAction(self.open_action)

        self.recent_menu = file_menu.addMenu(t("menu.file.recent"))
        if QFile.exists(":/icons/abrir_reciente.png"):
            self.recent_menu.setIcon(crear_icono(":/icons/abrir_reciente.png"))
        # El submenú se reconstruye SIEMPRE en su aboutToShow (pila limpia, menú
        # aún no visible): así nunca se recrean sus QWidgetAction/miniaturas
        # anidados en otro handler ni mientras el menú está a la vista, que es lo
        # que PETABA (access violation en shiboken, PySide6 6.11/py3.14).
        self.recent_menu.aboutToShow.connect(self._rebuild_recent_menu)
        self._rebuild_recent_menu()
        file_menu.addSeparator()

        self.save_action = QAction(t("menu.file.save"), self)
        self.save_action.setShortcut("Ctrl+S")
        self.save_action.setIcon(crear_icono(":/icons/guardar.png"))
        self.save_action.triggered.connect(self.save_file)
        file_menu.addAction(self.save_action)

        self.save_as_action = QAction(t("menu.file.save_as"), self)
        self.save_as_action.setShortcut("Ctrl+Shift+S")
        self.save_as_action.setIcon(crear_icono(":/icons/guardar_como.png"))
        self.save_as_action.triggered.connect(self.save_file_as)
        file_menu.addAction(self.save_as_action)

        file_menu.addSeparator()

        self.print_action = QAction(t("menu.file.print"), self)
        self.print_action.setShortcut("Ctrl+P")
        self.print_action.setIcon(crear_icono(":/icons/imprimir.png"))
        self.print_action.triggered.connect(self.print_file)
        file_menu.addAction(self.print_action)

        # Submenú Exportar: agrupa las salidas que no son "Guardar como"
        # (PDF, OpenRaster y animación). La previsualización de la animación
        # vive en el menú Ver (es visualización, no salida a archivo).
        self.export_menu = file_menu.addMenu(t("menu.file.export"))
        if QFile.exists(":/icons/exportar.png"):
            self.export_menu.setIcon(crear_icono(":/icons/exportar.png"))

        self.export_pdf_action = QAction(t("menu.file.export.pdf"), self)
        if QFile.exists(":/icons/exportar_pdf.png"):
            self.export_pdf_action.setIcon(crear_icono(":/icons/exportar_pdf.png"))
        self.export_pdf_action.triggered.connect(self.export_pdf)
        self.export_menu.addAction(self.export_pdf_action)

        self.export_ora_action = QAction(t("menu.file.export.ora"), self)
        if QFile.exists(":/icons/exportar_ora.png"):
            self.export_ora_action.setIcon(crear_icono(":/icons/exportar_ora.png"))
        self.export_ora_action.triggered.connect(self.export_ora)
        self.export_menu.addAction(self.export_ora_action)

        self.export_anim_action = QAction(t("menu.file.export.anim"), self)
        if QFile.exists(":/icons/exportar_anim.png"):
            self.export_anim_action.setIcon(crear_icono(":/icons/exportar_anim.png"))
        self.export_anim_action.triggered.connect(self.export_animation)
        self.export_menu.addAction(self.export_anim_action)

        # Procesamiento por lotes: opera sobre una carpeta del disco, así que
        # NO necesita documento abierto (no entra en el bloque de acciones que
        # se deshabilitan sin pestañas).
        self.batch_action = QAction(t("menu.file.batch"), self)
        if QFile.exists(":/icons/lote.png"):
            self.batch_action.setIcon(crear_icono(":/icons/lote.png"))
        self.batch_action.triggered.connect(self.batch_process)
        file_menu.addAction(self.batch_action)

        file_menu.addSeparator()

        self.close_tab_action = QAction(t("menu.file.close", default="Cerrar"), self)
        if QFile.exists(":/icons/cerrar.png"): self.close_tab_action.setIcon(crear_icono(":/icons/cerrar.png"))
        self.close_tab_action.setShortcut("Ctrl+W")
        self.close_tab_action.triggered.connect(
            lambda: self.close_tab(self.tabs.currentIndex()))
        file_menu.addAction(self.close_tab_action)

        file_menu.addSeparator()
        exit_action = QAction(t("menu.file.exit"), self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.setIcon(crear_icono(":/icons/salir.png"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # =====================================================================
        # MENÚ EDICION
        # =====================================================================
        edit_menu = menu_bar.addMenu(t("menu.edit"))

        self.undo_action = QAction(t("menu.edit.undo"), self)
        self.undo_action.setShortcut("Ctrl+Z")
        self.undo_action.setIcon(crear_icono(":/icons/deshacer.png"))
        self.undo_action.triggered.connect(self.trigger_canvas_undo)
        edit_menu.addAction(self.undo_action)

        self.redo_action = QAction(t("menu.edit.redo"), self)
        self.redo_action.setShortcut("Ctrl+Y")
        self.redo_action.setIcon(crear_icono(":/icons/rehacer.png"))
        self.redo_action.triggered.connect(self.trigger_canvas_redo)
        edit_menu.addAction(self.redo_action)

        edit_menu.addSeparator()

        self.cut_action = QAction(t("menu.edit.cut"), self)
        self.cut_action.setShortcut("Ctrl+X")
        if QFile.exists(":/icons/cut.png"): self.cut_action.setIcon(crear_icono(":/icons/cut.png"))
        self.cut_action.triggered.connect(self.edit_cut)
        edit_menu.addAction(self.cut_action)

        self.copy_action = QAction(t("menu.edit.copy"), self)
        self.copy_action.setShortcut("Ctrl+C")
        if QFile.exists(":/icons/copy.png"): self.copy_action.setIcon(crear_icono(":/icons/copy.png"))
        self.copy_action.triggered.connect(self.edit_copy)
        edit_menu.addAction(self.copy_action)

        self.paste_action = QAction(t("menu.edit.paste"), self)
        self.paste_action.setShortcut("Ctrl+V")
        if QFile.exists(":/icons/paste.png"): self.paste_action.setIcon(crear_icono(":/icons/paste.png"))
        self.paste_action.triggered.connect(self.edit_paste)
        edit_menu.addAction(self.paste_action)

        self.paste_layer_action = QAction(t("menu.edit.paste_layer"), self)
        self.paste_layer_action.setShortcut("Ctrl+Shift+V")
        if QFile.exists(":/icons/paste_layer_new.png"): self.paste_layer_action.setIcon(crear_icono(":/icons/paste_layer_new.png"))
        self.paste_layer_action.triggered.connect(self.edit_paste_as_layer)
        edit_menu.addAction(self.paste_layer_action)

        self.paste_image_action = QAction(t("menu.edit.paste_image"), self)
        if QFile.exists(":/icons/paste_image_new.png"): self.paste_image_action.setIcon(crear_icono(":/icons/paste_image_new.png"))
        self.paste_image_action.triggered.connect(self.edit_paste_as_image)
        edit_menu.addAction(self.paste_image_action)

        edit_menu.addSeparator()

        self.copy_sel_shape_action = QAction(t("menu.edit.copy_sel"), self)
        if QFile.exists(":/icons/copy_selection.png"): self.copy_sel_shape_action.setIcon(crear_icono(":/icons/copy_selection.png"))
        self.copy_sel_shape_action.triggered.connect(self.edit_copy_selection_shape)
        edit_menu.addAction(self.copy_sel_shape_action)

        self.paste_sel_menu = edit_menu.addMenu(t("menu.edit.paste_sel"))
        if QFile.exists(":/icons/paste_selection.png"):
            self.paste_sel_menu.menuAction().setIcon(crear_icono(":/icons/paste_selection.png"))
        for _txt, _mode, _ic in ((t("menu.edit.paste_sel.rep"), "replace", "sel_replace"),
                                 (t("menu.edit.paste_sel.add"), "add", "sel_add"),
                                 (t("menu.edit.paste_sel.sub"), "subtract", "sel_subtract"),
                                 (t("menu.edit.paste_sel.int"), "intersect", "sel_intersect")):
            _act = QAction(_txt, self)
            if QFile.exists(f":/icons/{_ic}.png"): _act.setIcon(crear_icono(f":/icons/{_ic}.png"))
            _act.triggered.connect(lambda checked=False, m=_mode: self.edit_paste_selection_shape(m))
            self.paste_sel_menu.addAction(_act)

        edit_menu.addSeparator()

        self.delete_sel_action = QAction(t("menu.edit.del_sel"), self)
        self.delete_sel_action.setShortcut("Del")   # tecla Supr
        if QFile.exists(":/icons/delete_selection.png"): self.delete_sel_action.setIcon(crear_icono(":/icons/delete_selection.png"))
        self.delete_sel_action.triggered.connect(self.edit_delete_selection)
        edit_menu.addAction(self.delete_sel_action)

        self.fill_sel_action = QAction(t("menu.edit.fill_sel"), self)
        if QFile.exists(":/icons/fill_selection.png"): self.fill_sel_action.setIcon(crear_icono(":/icons/fill_selection.png"))
        self.fill_sel_action.triggered.connect(self.edit_fill_selection)
        edit_menu.addAction(self.fill_sel_action)

        self.invert_sel_action = QAction(t("menu.edit.inv_sel"), self)
        self.invert_sel_action.setShortcut("Ctrl+I")
        if QFile.exists(":/icons/invert_selection.png"): self.invert_sel_action.setIcon(crear_icono(":/icons/invert_selection.png"))
        self.invert_sel_action.triggered.connect(self.edit_invert_selection)
        edit_menu.addAction(self.invert_sel_action)

        self.select_all_action = QAction(t("menu.edit.sel_all"), self)
        self.select_all_action.setShortcut("Ctrl+A")
        if QFile.exists(":/icons/select_all.png"): self.select_all_action.setIcon(crear_icono(":/icons/select_all.png"))
        self.select_all_action.triggered.connect(self.edit_select_all)
        edit_menu.addAction(self.select_all_action)

        self.deselect_action = QAction(t("menu.edit.desel"), self)
        self.deselect_action.setShortcut("Ctrl+D")
        if QFile.exists(":/icons/deselect.png"): self.deselect_action.setIcon(crear_icono(":/icons/deselect.png"))
        self.deselect_action.triggered.connect(self.edit_deselect)
        edit_menu.addAction(self.deselect_action)

        self.refine_menu = edit_menu.addMenu(t("menu.edit.refine"))
        if QFile.exists(":/icons/selection_smooth.png"): self.refine_menu.setIcon(crear_icono(":/icons/selection_smooth.png"))
        
        self.expand_sel_action = QAction(t("menu.edit.refine.exp"), self)
        if QFile.exists(":/icons/selection_expand.png"): self.expand_sel_action.setIcon(crear_icono(":/icons/selection_expand.png"))
        self.expand_sel_action.triggered.connect(self.edit_expand_selection)
        self.refine_menu.addAction(self.expand_sel_action)
        
        self.contract_sel_action = QAction(t("menu.edit.refine.con"), self)
        if QFile.exists(":/icons/selection_contract.png"): self.contract_sel_action.setIcon(crear_icono(":/icons/selection_contract.png"))
        self.contract_sel_action.triggered.connect(self.edit_contract_selection)
        self.refine_menu.addAction(self.contract_sel_action)
        
        self.smooth_sel_action = QAction(t("menu.edit.refine.smo"), self)
        if QFile.exists(":/icons/selection_smooth.png"): self.smooth_sel_action.setIcon(crear_icono(":/icons/selection_smooth.png"))
        self.smooth_sel_action.triggered.connect(self.edit_smooth_selection)
        self.refine_menu.addAction(self.smooth_sel_action)
        
        self.feather_sel_action = QAction(t("menu.edit.refine.fea"), self)
        if QFile.exists(":/icons/selection_feather.png"): self.feather_sel_action.setIcon(crear_icono(":/icons/selection_feather.png"))
        self.feather_sel_action.triggered.connect(self.edit_feather_selection)
        self.refine_menu.addAction(self.feather_sel_action)

        self.border_sel_action = QAction(t("menu.edit.refine.bor"), self)
        if QFile.exists(":/icons/selection_border.png"): self.border_sel_action.setIcon(crear_icono(":/icons/selection_border.png"))
        self.border_sel_action.triggered.connect(self.edit_border_selection)
        self.refine_menu.addAction(self.border_sel_action)

        # Crecer / Seleccionar parecido (como Photoshop): amplían la selección
        # por color con la tolerancia de la varita (sin diálogo).
        self.refine_menu.addSeparator()
        self.grow_sel_action = QAction(t("menu.edit.refine.grow"), self)
        if QFile.exists(":/icons/selection_grow.png"): self.grow_sel_action.setIcon(crear_icono(":/icons/selection_grow.png"))
        self.grow_sel_action.triggered.connect(self.edit_grow_selection)
        self.refine_menu.addAction(self.grow_sel_action)

        self.similar_sel_action = QAction(t("menu.edit.refine.sim"), self)
        if QFile.exists(":/icons/selection_similar.png"): self.similar_sel_action.setIcon(crear_icono(":/icons/selection_similar.png"))
        self.similar_sel_action.triggered.connect(self.edit_similar_selection)
        self.refine_menu.addAction(self.similar_sel_action)

        edit_menu.addSeparator()
        self.preferences_action = QAction(t("menu.edit.pref"), self)
        if QFile.exists(":/icons/preferences.png"):
            self.preferences_action.setIcon(crear_icono(":/icons/preferences.png"))
        self.preferences_action.triggered.connect(self.open_preferences)
        edit_menu.addAction(self.preferences_action)

        # =====================================================================
        # MENÚ VER
        # =====================================================================
        view_menu = menu_bar.addMenu(t("menu.view"))

        # --- Zoom (arriba del todo) ---
        self.zoom_in_action = QAction(t("menu.view.zoom_in"), self)
        self.zoom_in_action.setShortcuts(["Ctrl++", "Ctrl+="])
        if QFile.exists(":/icons/zoom_in.png"): self.zoom_in_action.setIcon(crear_icono(":/icons/zoom_in.png"))
        self.zoom_in_action.triggered.connect(self.zoom_in)
        view_menu.addAction(self.zoom_in_action)

        self.zoom_out_action = QAction(t("menu.view.zoom_out"), self)
        self.zoom_out_action.setShortcut("Ctrl+-")
        if QFile.exists(":/icons/zoom_out.png"): self.zoom_out_action.setIcon(crear_icono(":/icons/zoom_out.png"))
        self.zoom_out_action.triggered.connect(self.zoom_out)
        view_menu.addAction(self.zoom_out_action)

        self.zoom_fit_action = QAction(t("menu.view.zoom_fit"), self)
        self.zoom_fit_action.setShortcut("Ctrl+0")
        if QFile.exists(":/icons/zoom_fit.png"): self.zoom_fit_action.setIcon(crear_icono(":/icons/zoom_fit.png"))
        self.zoom_fit_action.triggered.connect(self.fit_canvas_to_screen)
        view_menu.addAction(self.zoom_fit_action)

        self.zoom_actual_action = QAction(t("menu.view.zoom_act"), self)
        if QFile.exists(":/icons/zoom_actual.png"): self.zoom_actual_action.setIcon(crear_icono(":/icons/zoom_actual.png"))
        self.zoom_actual_action.setShortcut("Ctrl+1")
        self.zoom_actual_action.triggered.connect(self.actual_size)
        view_menu.addAction(self.zoom_actual_action)

        view_menu.addSeparator()

        # --- Ver la imagen a pantalla completa (solo la imagen, para revisar) ---
        self.fullscreen_action = QAction(
            t("menu.view.fullscreen", default="Ver a pantalla completa"), self)
        self.fullscreen_action.setShortcut("F11")
        if QFile.exists(":/icons/fullscreen.png"):
            self.fullscreen_action.setIcon(crear_icono(":/icons/fullscreen.png"))
        self.fullscreen_action.triggered.connect(self.open_fullscreen_view)
        view_menu.addAction(self.fullscreen_action)

        # Previsualizar la animación (capas visibles = fotogramas): es pura
        # visualización, por eso vive aquí y no junto a Exportar animación.
        self.preview_anim_action = QAction(t("menu.view.preview_anim"), self)
        if QFile.exists(":/icons/preview_anim.png"):
            self.preview_anim_action.setIcon(crear_icono(":/icons/preview_anim.png"))
        self.preview_anim_action.triggered.connect(self.preview_animation)
        view_menu.addAction(self.preview_anim_action)

        self.document_diagnostics_action = QAction(
            t("menu.view.diagnostics"), self)
        if QFile.exists(":/icons/layer_properties.png"):
            self.document_diagnostics_action.setIcon(
                crear_icono(":/icons/layer_properties.png"))
        self.document_diagnostics_action.triggered.connect(
            self.open_document_diagnostics)
        view_menu.addAction(self.document_diagnostics_action)

        view_menu.addSeparator()

        self.grid_action = QAction(t("menu.view.grid"), self)
        self.grid_action.setCheckable(True)
        self.grid_action.setShortcut("Ctrl+'")
        if QFile.exists(":/icons/grid.png"): self.grid_action.setIcon(crear_icono_checkable(":/icons/grid.png"))
        self.grid_action.triggered.connect(self.toggle_grid)
        view_menu.addAction(self.grid_action)

        # Mosaico de la cuadrícula: línea maestra cada N px (pixel-art /
        # sprite sheets), visible ya al 100% cuando la cuadrícula está activa.
        # Radio global (como la cuadrícula), persistido en view/grid_tile.
        self.grid_tile_menu = view_menu.addMenu(t("menu.view.grid_tile"))
        self.grid_tile_group = QActionGroup(self)
        self.grid_tile_actions = {}
        for paso in (0, 8, 16, 32, 64):
            texto = (t("menu.view.grid_tile.none") if paso == 0
                     else f"{paso} × {paso} px")
            act = QAction(texto, self)
            act.setCheckable(True)
            act.setChecked(paso == 0)
            act.triggered.connect(
                lambda checked=False, v=paso: self.set_grid_tile_global(v))
            self.grid_tile_group.addAction(act)
            self.grid_tile_menu.addAction(act)
            self.grid_tile_actions[paso] = act

        # Paleta de Colores: movida aquí desde la barra de herramientas. Se
        # crea y se añade al menú Ver (ya no hay botón en la barra).
        self.color_action = QAction(t("menu.view.color"), self)
        self.color_action.setShortcut("F8")  # como en Paint.NET (ventana de Colores)
        if QFile.exists(":/icons/color.png"):
            self.color_action.setIcon(crear_icono(":/icons/color.png"))
        self.color_action.triggered.connect(self.change_color)
        view_menu.addAction(self.color_action)

        self.guides_action = QAction(t("menu.view.guides"), self)
        self.guides_action.setCheckable(True)
        self.guides_action.setChecked(True)
        self.guides_action.setShortcut("Ctrl+;")
        if QFile.exists(":/icons/guides.png"): self.guides_action.setIcon(crear_icono_checkable(":/icons/guides.png"))
        self.guides_action.triggered.connect(self.toggle_guides)
        view_menu.addAction(self.guides_action)
        # (El botón de Guías se añade a la barra de herramientas en
        # create_fixed_toolbar, que se construye DESPUÉS de los menús.)

        # Reglas: justo encima de las unidades (px / cm / pulgadas) que le siguen.
        self.rulers_action = QAction(t("menu.view.rulers"), self)
        self.rulers_action.setCheckable(True)
        self.rulers_action.setShortcut("Ctrl+Shift+R")
        if QFile.exists(":/icons/rulers.png"): self.rulers_action.setIcon(crear_icono_checkable(":/icons/rulers.png"))
        self.rulers_action.triggered.connect(self.toggle_rulers)
        view_menu.addAction(self.rulers_action)

        # --- Unidad de las reglas (píxeles / centímetros / pulgadas) ---
        view_menu.addSeparator()
        self.unit_group = QActionGroup(self)
        self.unit_group.setExclusive(True)

        self.unit_px_action = QAction(t("menu.view.unit_px"), self)
        self.unit_px_action.setCheckable(True)
        self.unit_px_action.setChecked(True)  # px por defecto
        self.unit_px_action.triggered.connect(lambda: self.set_ruler_unit("px"))
        self.unit_group.addAction(self.unit_px_action)
        view_menu.addAction(self.unit_px_action)

        self.unit_cm_action = QAction(t("menu.view.unit_cm"), self)
        self.unit_cm_action.setCheckable(True)
        self.unit_cm_action.triggered.connect(lambda: self.set_ruler_unit("cm"))
        self.unit_group.addAction(self.unit_cm_action)
        view_menu.addAction(self.unit_cm_action)

        self.unit_in_action = QAction(t("menu.view.unit_in"), self)
        self.unit_in_action.setCheckable(True)
        self.unit_in_action.triggered.connect(lambda: self.set_ruler_unit("in"))
        self.unit_group.addAction(self.unit_in_action)
        view_menu.addAction(self.unit_in_action)

        # =====================================================================
        # MENÚ IMAGEN
        # =====================================================================
        image_menu = menu_bar.addMenu(t("menu.image"))

        self.crop_action = QAction(t("menu.image.crop"), self)
        # Activa la HERRAMIENTA de recorte (la tecla C es su atajo real; aquí no
        # se declara para no robar la C a la escritura de texto vía menú).
        # Si hay una selección activa, la caja arranca ajustada a ella (así se
        # conserva el antiguo flujo "recortar a la selección": menú + Enter).
        if QFile.exists(":/icons/crop.png"): self.crop_action.setIcon(crear_icono(":/icons/crop.png"))
        self.crop_action.triggered.connect(lambda: self.set_tool("crop"))
        image_menu.addAction(self.crop_action)

        self.resize_action = QAction(t("menu.image.resize"), self)
        self.resize_action.setShortcut("Ctrl+R")
        if QFile.exists(":/icons/resize.png"): self.resize_action.setIcon(crear_icono(":/icons/resize.png"))
        self.resize_action.triggered.connect(self.image_resize)
        image_menu.addAction(self.resize_action)

        self.canvas_size_action = QAction(t("menu.image.canvas"), self)
        self.canvas_size_action.setShortcut("Ctrl+Shift+C")
        if QFile.exists(":/icons/canvas_size.png"): self.canvas_size_action.setIcon(crear_icono(":/icons/canvas_size.png"))
        self.canvas_size_action.triggered.connect(self.image_canvas_size)
        image_menu.addAction(self.canvas_size_action)

        image_menu.addSeparator()

        self.flip_h_action = QAction(t("menu.image.flip_h"), self)
        if QFile.exists(":/icons/flip_h.png"): self.flip_h_action.setIcon(crear_icono(":/icons/flip_h.png"))
        self.flip_h_action.triggered.connect(lambda: self.image_flip(True))
        image_menu.addAction(self.flip_h_action)

        self.flip_v_action = QAction(t("menu.image.flip_v"), self)
        if QFile.exists(":/icons/flip_v.png"): self.flip_v_action.setIcon(crear_icono(":/icons/flip_v.png"))
        self.flip_v_action.triggered.connect(lambda: self.image_flip(False))
        image_menu.addAction(self.flip_v_action)

        image_menu.addSeparator()

        self.rotate_cw_action = QAction(t("menu.image.rot_cw"), self)
        if QFile.exists(":/icons/rotate_cw.png"): self.rotate_cw_action.setIcon(crear_icono(":/icons/rotate_cw.png"))
        self.rotate_cw_action.triggered.connect(lambda: self.image_rotate(90))
        image_menu.addAction(self.rotate_cw_action)

        self.rotate_ccw_action = QAction(t("menu.image.rot_ccw"), self)
        if QFile.exists(":/icons/rotate_ccw.png"): self.rotate_ccw_action.setIcon(crear_icono(":/icons/rotate_ccw.png"))
        self.rotate_ccw_action.triggered.connect(lambda: self.image_rotate(-90))
        image_menu.addAction(self.rotate_ccw_action)

        self.rotate_180_action = QAction(t("menu.image.rot_180"), self)
        if QFile.exists(":/icons/rotate_180.png"): self.rotate_180_action.setIcon(crear_icono(":/icons/rotate_180.png"))
        self.rotate_180_action.triggered.connect(lambda: self.image_rotate(180))
        image_menu.addAction(self.rotate_180_action)

        self.rotate_free_action = QAction(t("menu.image.rotate_free"), self)
        if QFile.exists(":/icons/rotate_free.png"): self.rotate_free_action.setIcon(crear_icono(":/icons/rotate_free.png"))
        self.rotate_free_action.triggered.connect(self.image_rotate_free)
        image_menu.addAction(self.rotate_free_action)

        image_menu.addSeparator()
        self.image_props_action = QAction(t("menu.image.properties"), self)
        if QFile.exists(":/icons/propiedades.png"):
            self.image_props_action.setIcon(crear_icono(":/icons/propiedades.png"))
        self.image_props_action.triggered.connect(self.show_image_properties)
        image_menu.addAction(self.image_props_action)

        # =====================================================================
        # MENÚ CAPAS
        # =====================================================================
        layers_menu = menu_bar.addMenu(t("menu.layers"))

        self._layer_menu_actions = {}
        acciones_capas = [
            ("new",        t("menu.layers.new_layer"),                ":/icons/layer_add.png",        "Ctrl+Shift+N",  lambda: self.layers_panel.add_layer()),
            ("duplicate",  t("menu.layers.dup"),             ":/icons/layer_duplicate.png",  "Ctrl+J",        lambda: self.layers_panel.duplicate_layer()),
            ("group",      t("layer.group_new"),             ":/icons/layer_group.png",      "Ctrl+G",        lambda: self.layers_panel.group_selection()),
            ("remove",     t("menu.layers.del"),             ":/icons/layer_remove.png",     "Ctrl+Shift+Del", lambda: self.layers_panel.remove_layer()),
            ("toggle_vis", t("menu.layers.toggle_vis"), ":/icons/layer_visibility.png", "", lambda: self.layer_toggle_visibility()),
            None,
            ("merge_down", t("menu.layers.merge"),      ":/icons/layer_merge.png",      "Ctrl+E",        lambda: self.layers_panel.merge_down()),
            ("merge_fx",   t("menu.layers.merge_fx"),   ":/icons/layer_fx.png",         "",              lambda: self.layer_merge_effects()),
            ("flatten",    t("menu.layers.flatten"),  ":/icons/layer_flatten.png",    "Ctrl+Shift+E",  lambda: self.layers_panel.flatten()),
            None,
            ("move_up",    t("menu.layers.move_up"),        ":/icons/layer_up.png",         "Ctrl+]",        lambda: self.layers_panel.move_up()),
            ("move_down",  t("menu.layers.move_down"),         ":/icons/layer_down.png",       "Ctrl+[",        lambda: self.layers_panel.move_down()),
            None,
            ("flip_h",     t("menu.layers.flip_h"),          ":/icons/flip_h.png",     "", lambda: self.layer_flip(True)),
            ("flip_v",     t("menu.layers.flip_v"),            ":/icons/flip_v.png",     "", lambda: self.layer_flip(False)),
            ("rot_cw",     t("menu.layers.rot_cw"),     ":/icons/rotate_cw.png",  "", lambda: self.layer_rotate(90)),
            ("rot_ccw",    t("menu.layers.rot_ccw"), ":/icons/rotate_ccw.png", "", lambda: self.layer_rotate(-90)),
            ("rot_180",    t("menu.layers.rot_180"),                       ":/icons/rotate_180.png", "", lambda: self.layer_rotate(180)),
            None,
            ("properties", t("menu.layers.prop_short"),            ":/icons/layer_properties.png", "Ctrl+Shift+P",  lambda: self.layers_panel.show_properties()),
        ]

        for entrada in acciones_capas:
            if entrada is None:
                layers_menu.addSeparator()
                continue
            key, texto, icono, atajo, slot = entrada
            action = QAction(texto, self)
            if QFile.exists(icono):
                action.setIcon(theme.icono(icono))
            if atajo:
                action.setShortcut(atajo)
            action.triggered.connect(slot)
            layers_menu.addAction(action)
            self._layer_menu_actions[key] = action

        # --- Submenú Máscara de capa (no destructiva) ---
        layers_menu.addSeparator()
        mask_menu = layers_menu.addMenu(t("menu.layers.mask"))
        if QFile.exists(":/icons/layer_mask.png"):
            mask_menu.setIcon(theme.icono(":/icons/layer_mask.png"))
        mask_entries = [
            ("mask_create",   t("menu.layers.mask.reveal2"), ":/icons/mask_reveal.png",   lambda: self.layer_mask_create()),
            ("mask_from_sel", t("menu.layers.mask.from_sel"), ":/icons/mask_from_sel.png", lambda: self.layer_mask_from_selection()),
            None,
            ("mask_apply",    t("menu.layers.mask.apply"),   ":/icons/mask_apply.png",    lambda: self.layer_mask_apply()),
            ("mask_remove",   t("menu.layers.mask.del"),     ":/icons/mask_remove.png",   lambda: self.layer_mask_remove()),
        ]
        for entrada in mask_entries:
            if entrada is None:
                mask_menu.addSeparator()
                continue
            key, texto, icono, slot = entrada
            action = QAction(texto, self)
            if QFile.exists(icono):
                action.setIcon(theme.icono(icono))
            action.triggered.connect(slot)
            mask_menu.addAction(action)
            self._layer_menu_actions[key] = action

        # ✂️ Máscara de recorte (clipping mask): checkable, la capa activa se
        # recorta al alfa de su capa base (la primera no recortada por debajo).
        # Atajo estándar Ctrl+Alt+G; estado y habilitado en
        # update_layer_menu_state (necesita una capa debajo).
        self.clip_action = QAction(t("menu.layers.clip"), self)
        self.clip_action.setCheckable(True)
        self.clip_action.setShortcut("Ctrl+Alt+G")
        self.clip_action.triggered.connect(self.layer_toggle_clipped)
        layers_menu.addAction(self.clip_action)
        self._layer_menu_actions["clip"] = self.clip_action

        # --- Submenú Efectos de capa (no destructivos): espejo del botón fx del
        # panel de Capas, para poder trabajar con el panel oculto. Cada entrada
        # abre el panel unificado con ese efecto seleccionado y activado. ---
        from widgets.layer_effects_ui import efectos_disponibles
        fx_menu = layers_menu.addMenu(t("menu.layers.fx"))
        if QFile.exists(":/icons/layer_fx.png"):
            fx_menu.setIcon(theme.icono(":/icons/layer_fx.png"))
        _fx_iconos = {"sombra": "fx_shadow.png", "sombra_interior": "fx_inner_shadow.png",
                      "resplandor": "fx_outer_glow.png", "trazo": "fx_stroke.png",
                      "bisel": "fx_bevel.png", "satinado": "fx_satin.png",
                      "superposicion": "fx_overlay.png", "degradado": "fx_gradient.png"}
        for tipo, nombre in efectos_disponibles():
            act = QAction(nombre, self)
            icono = ":/icons/" + _fx_iconos.get(tipo, "")
            if QFile.exists(icono):
                act.setIcon(theme.icono(icono))
            act.triggered.connect(lambda _c=False, tp=tipo: self.open_layer_effects(tp))
            fx_menu.addAction(act)
        self._layer_menu_actions["fx_menu"] = fx_menu.menuAction()

        # --- Submenú Modo de fusión de la capa activa: mismo comando deshacible
        # que el combo del panel de Capas; el modo vigente se marca al abrir. ---
        from widgets.layers_panel import blend_modes
        blend_menu = layers_menu.addMenu(t("menu.layers.blend"))
        if QFile.exists(":/icons/blend_mode.png"):
            blend_menu.setIcon(theme.icono(":/icons/blend_mode.png"))
        self._blend_menu_actions = []      # [(QAction, CompositionMode)]
        for nombre, modo in blend_modes():
            act = QAction(nombre, self)
            act.setCheckable(True)
            act.triggered.connect(lambda _c=False, m=modo: self.layer_set_blend_mode(m))
            blend_menu.addAction(act)
            self._blend_menu_actions.append((act, modo))
        blend_menu.aboutToShow.connect(self._sync_blend_menu)
        self._layer_menu_actions["blend_menu"] = blend_menu.menuAction()

        # Refrescar el estado de las acciones cada vez que se abre el menú
        # (recoge el nº de capas y la posición de la capa activa al instante).
        layers_menu.aboutToShow.connect(self.update_layer_menu_state)

        # =====================================================================
        # MENÚ AJUSTES
        # =====================================================================
        adjust_menu = menu_bar.addMenu(t("menu.adj"))

        self._fx_actions = []
        # Registro texto-normalizado -> icono, para que el panel de Historial
        # muestre el icono propio de cada ajuste/efecto (todos comparten
        # tool_id="adjust", así que el icono se resuelve por el nombre del comando).
        self._history_icons = {}
        def add_adj(menu, text, icon, slot, tip=""):
            act = QAction(text, self)
            act.setIcon(crear_icono(":/icons/" + icon))
            if tip:
                act.setStatusTip(tip)
            act.triggered.connect(slot)
            menu.addAction(act)
            self._fx_actions.append(act)
            self._history_icons[text.replace("...", "").replace("&", "").strip()] = icon
            return act

        # Agrupados en submenús (como el menú Efectos), en el orden del árbol
        # acordado: Luz y tono · Color · Blanco y negro · Estilizar · Automático.
        m_adj_light = adjust_menu.addMenu(t("menu.adj.grp.light"))
        self.adj_bc_action = add_adj(m_adj_light, t("menu.adj.brightness"), "adjust.png", self.adjust_brightness_contrast, t("fx.tip.brightness"))
        self.adj_exposure_action = add_adj(m_adj_light, t("menu.adj.exposure"), "exposure.png", self.adjust_exposure, t("fx.tip.exposure"))
        self.adj_sh_action = add_adj(m_adj_light, t("menu.adj.shadows_highlights"), "fx_shadows_highlights.png", self.adjust_shadows_highlights, t("fx.tip.shadows_highlights"))
        self.adj_clarity_action = add_adj(m_adj_light, t("menu.adj.clarity"), "clarity.png", self.adjust_clarity, t("fx.tip.clarity"))
        self.adj_dehaze_action = add_adj(m_adj_light, t("menu.adj.dehaze"), "dehaze.png", self.adjust_dehaze, t("fx.tip.dehaze"))
        self.adj_curves_action = add_adj(m_adj_light, t("menu.adj.curves"), "curves.png", self.adjust_curves, t("fx.tip.curves"))
        self.adj_levels_action = add_adj(m_adj_light, t("menu.adj.levels"), "levels.png", self.adjust_levels, t("fx.tip.levels"))
        self.adj_gamma_action = add_adj(m_adj_light, t("menu.adj.gamma"), "gamma.png", self.adjust_gamma, t("fx.tip.gamma"))

        m_adj_color = adjust_menu.addMenu(t("menu.adj.grp.color"))
        self.adj_hs_action = add_adj(m_adj_color, t("menu.adj.hue"), "hue_sat.png", self.adjust_hue_saturation, t("fx.tip.hue"))
        self.adj_vibrance_action = add_adj(m_adj_color, t("menu.adj.vibrance"), "vibrance.png", self.adjust_vibrance, t("fx.tip.vibrance"))
        self.adj_cb_action = add_adj(m_adj_color, t("menu.adj.color_bal"), "color_balance.png", self.adjust_color_balance, t("fx.tip.color_balance"))
        self.adj_temp_action = add_adj(m_adj_color, t("menu.adj.temp"), "temperature.png", self.adjust_temperature, t("fx.tip.temperature"))
        self.adj_white_balance_action = add_adj(m_adj_color, t("menu.adj.white_balance"), "white_balance.png", self.adjust_white_balance, t("fx.tip.white_balance"))
        self.adj_photo_filter_action = add_adj(m_adj_color, t("menu.adj.photo_filter"), "photo_filter.png", self.adjust_photo_filter, t("fx.tip.photo_filter"))
        self.adj_channel_mixer_action = add_adj(m_adj_color, t("menu.adj.channel_mixer"), "fx_channel_mixer.png", self.adjust_channel_mixer, t("fx.tip.channel_mixer"))
        self.adj_replace_color_action = add_adj(m_adj_color, t("menu.adj.replace_color"), "fx_replace_color.png", self.adjust_replace_color, t("fx.tip.replace_color"))

        m_adj_bw = adjust_menu.addMenu(t("menu.adj.grp.bw"))
        self.adj_grayscale_action = add_adj(m_adj_bw, t("menu.adj.grayscale"), "bw.png", self.adjust_grayscale, t("fx.tip.grayscale"))
        self.adj_bw_advanced_action = add_adj(m_adj_bw, t("menu.adj.bw_advanced"), "fx_bw_advanced.png", self.adjust_bw_advanced, t("fx.tip.bw_advanced"))
        self.adj_sepia_action = add_adj(m_adj_bw, t("menu.adj.sepia"), "sepia.png", self.adjust_sepia, t("fx.tip.sepia"))
        self.adj_duotone_action = add_adj(m_adj_bw, t("menu.adj.duotone"), "fx_duotone.png", self.adjust_duotone, t("fx.tip.duotone"))

        m_adj_stylize = adjust_menu.addMenu(t("menu.adj.grp.stylize"))
        self.adj_invert_action = add_adj(m_adj_stylize, t("menu.adj.invert"), "invert.png", self.adjust_invert, t("fx.tip.invert"))
        self.adj_posterize_action = add_adj(m_adj_stylize, t("menu.adj.posterize"), "posterize.png", self.adjust_posterize, t("fx.tip.posterize"))
        self.adj_threshold_action = add_adj(m_adj_stylize, t("menu.adj.threshold"), "threshold.png", self.adjust_threshold, t("fx.tip.threshold"))
        self.adj_solarize_action = add_adj(m_adj_stylize, t("menu.effects.style.solar"), "solarize.png", self.adjust_solarize, t("fx.tip.solarize"))
        self.adj_gradient_map_action = add_adj(m_adj_stylize, t("menu.adj.gradient"), "gradient_map.png", self.adjust_gradient_map, t("fx.tip.gradient_map"))

        m_adj_auto = adjust_menu.addMenu(t("menu.adj.grp.auto"))
        self.adj_autolevels_action = add_adj(m_adj_auto, t("menu.adj.auto_levels"), "levels.png", self.adjust_auto_levels, t("fx.tip.auto_levels"))
        self.adj_autocontrast_action = add_adj(m_adj_auto, t("menu.adj.auto_contrast"), "auto_contrast.png", self.adjust_auto_contrast, t("fx.tip.auto_contrast"))
        self.adj_autocolor_action = add_adj(m_adj_auto, t("menu.adj.auto_color"), "white_balance.png", self.adjust_auto_color, t("fx.tip.auto_color"))
        self.adj_equalize_action = add_adj(m_adj_auto, t("menu.adj.equalize"), "equalize.png", self.adjust_equalize, t("fx.tip.equalize"))

        # Submenú para los AJUSTES aportados por plugins de terceros. Nace oculto y
        # el PluginManager lo hace visible al registrar el primero (ver
        # _registrar_plugin_overlay y _cargar_plugins).
        adjust_menu.addSeparator()
        self.adjust_plugins_menu = adjust_menu.addMenu(t("menu.plugins"))
        self.adjust_plugins_menu.menuAction().setVisible(False)

        self.swap_colors_action = QAction(t("menu.adj.swap"), self)
        self.swap_colors_action.setShortcut("X")
        self.swap_colors_action.triggered.connect(
            lambda: self.colors_panel.swap_colors() if hasattr(self, 'colors_panel') else None)
        self.addAction(self.swap_colors_action)  # Atajo global, sin necesidad de menú

        # ----- Menú Efectos (filtros con scipy), en submenús -----
        effects_menu = menu_bar.addMenu(t("menu.effects"))

        def add_eff(menu, text, icon, slot, tip=""):
            act = QAction(text, self)
            act.setIcon(crear_icono(":/icons/" + icon))
            if tip:
                act.setStatusTip(tip)
            act.triggered.connect(slot)
            menu.addAction(act)
            self._fx_actions.append(act)
            self._history_icons[text.replace("...", "").replace("&", "").strip()] = icon
            return act

        m_art = effects_menu.addMenu(t("menu.effects.art"))
        self.eff_pencil_action = add_eff(m_art, t("menu.eff.pencil"), "fx_pencil.png", self.effect_pencil_sketch, t("fx.tip.pencil"))
        self.eff_ink_action = add_eff(m_art, t("menu.eff.ink"), "fx_ink.png", self.effect_ink_sketch, t("fx.tip.ink"))
        self.eff_cartoon_action = add_eff(m_art, t("menu.effects.art.comic"), "fx_cartoon.png", self.effect_cartoon, t("fx.tip.cartoon"))
        self.eff_oil_action = add_eff(m_art, t("menu.effects.art.oil"), "fx_oil.png", self.effect_oil_painting, t("fx.tip.oil"))

        m_blur = effects_menu.addMenu(t("menu.effects.blur"))
        self.eff_box_action = add_eff(m_blur, t("menu.effects.blur.box"), "fx_box.png", self.effect_box_blur, t("fx.tip.box_blur"))
        self.eff_motion_action = add_eff(m_blur, t("menu.effects.blur.motion"), "fx_motion.png", self.effect_motion_blur, t("fx.tip.motion_blur"))
        self.eff_surface_action = add_eff(m_blur, t("menu.eff.surface"), "fx_surface.png", self.effect_surface_blur, t("fx.tip.surface_blur"))
        self.eff_gblur_action = add_eff(m_blur, t("menu.effects.blur.gauss"), "fx_blur.png", self.effect_gaussian_blur, t("fx.tip.gaussian_blur"))
        self.eff_zoom_action = add_eff(m_blur, t("menu.effects.blur.radial"), "fx_zoom.png", self.effect_zoom_blur, t("fx.tip.zoom_blur"))
        self.eff_lens_action = add_eff(m_blur, t("menu.eff.lens_blur"), "fx_lens_blur.png", self.effect_lens_blur, t("fx.tip.lens_blur"))
        self.eff_tiltshift_action = add_eff(m_blur, t("menu.eff.tilt_shift"), "fx_tilt_shift.png", self.effect_tilt_shift, t("fx.tip.tilt_shift"))
        self.eff_spin_action = add_eff(m_blur, t("menu.eff.spin_blur"), "fx_spin_blur.png", self.effect_spin_blur, t("fx.tip.spin_blur"))

        m_distort = effects_menu.addMenu(t("menu.effects.distort"))
        self.eff_spherize_action = add_eff(m_distort, t("menu.eff.spherize"), "fx_spherize.png", self.effect_spherize, t("fx.tip.spherize"))
        self.eff_wave_action = add_eff(m_distort, t("menu.effects.distort.wave"), "fx_wave.png", self.effect_wave, t("fx.tip.wave"))
        self.eff_twirl_action = add_eff(m_distort, t("menu.effects.distort.vortex"), "fx_twirl.png", self.effect_twirl, t("fx.tip.twirl"))
        self.eff_displace_action = add_eff(m_distort, t("menu.eff.displace"), "fx_displace.png", self.effect_displace, t("fx.tip.displace"))
        self.eff_kaleidoscope_action = add_eff(m_distort, t("menu.eff.kaleidoscope"), "fx_kaleidoscope.png", self.effect_kaleidoscope, t("fx.tip.kaleidoscope"))
        self.eff_polar_action = add_eff(m_distort, t("menu.eff.polar"), "fx_polar.png", self.effect_polar_coords, t("fx.tip.polar"))
        self.eff_frosted_action = add_eff(m_distort, t("menu.eff.frosted"), "fx_frosted.png", self.effect_frosted_glass, t("fx.tip.frosted"))

        m_sharp = effects_menu.addMenu(t("menu.effects.sharp"))
        self.eff_sharpen_action = add_eff(m_sharp, t("menu.effects.sharp.sharp"), "fx_sharpen.png", self.effect_sharpen, t("fx.tip.sharpen"))
        self.eff_sharpen_thr_action = add_eff(m_sharp, t("menu.eff.sharp_thr"), "fx_sharpen_thr.png", self.effect_sharpen_threshold, t("fx.tip.sharpen_threshold"))
        self.eff_findedges_action = add_eff(m_sharp, t("menu.eff.edges2"), "fx_find_edges.png", self.effect_find_edges, t("fx.tip.find_edges"))
        self.eff_edge_action = add_eff(m_sharp, t("menu.eff.edge2"), "fx_edge.png", self.effect_edge_enhance, t("fx.tip.edge_enhance"))

        m_style = effects_menu.addMenu(t("menu.effects.style"))
        self.eff_chromatic_action = add_eff(m_style, t("menu.eff.chromatic"), "fx_chromatic.png", self.effect_chromatic, t("fx.tip.chromatic"))
        self.eff_pixelate_action = add_eff(m_style, t("menu.effects.art.pixel"), "fx_pixelate.png", self.effect_pixelate, t("fx.tip.pixelate"))
        self.eff_crystallize_action = add_eff(m_style, t("menu.eff.crystallize"), "fx_crystallize.png", self.effect_crystallize, t("fx.tip.crystallize"))
        self.eff_emboss_action = add_eff(m_style, t("menu.eff.emboss2"), "fx_emboss.png", self.effect_emboss, t("fx.tip.emboss"))
        self.eff_halftone_action = add_eff(m_style, t("menu.effects.art.halftone"), "fx_halftone.png", self.effect_halftone, t("fx.tip.halftone"))
        self.eff_color_halftone_action = add_eff(m_style, t("menu.eff.color_halftone"), "fx_color_halftone.png", self.effect_color_halftone, t("fx.tip.color_halftone"))
        self.eff_vignette_action = add_eff(m_style, t("menu.eff.vignette"), "fx_vignette.png", self.effect_vignette, t("fx.tip.vignette"))
        self.eff_glitch_action = add_eff(m_style, t("menu.eff.glitch"), "fx_glitch.png", self.effect_glitch, t("fx.tip.glitch"))
        self.eff_bloom_action = add_eff(m_style, t("menu.eff.bloom"), "fx_bloom.png", self.effect_bloom, t("fx.tip.bloom"))
        self.eff_dither_action = add_eff(m_style, t("menu.eff.dithering"), "fx_dither.png", self.effect_dithering, t("fx.tip.dithering"))

        # (El antiguo submenú "Estilos de capa" —sombra/trazo/bisel DESTRUCTIVOS
        # sobre la transparencia— se eliminó: hoy son efectos de capa NO
        # destructivos, en Capas ▸ Efectos y en el botón fx del panel de Capas.)

        m_morph = effects_menu.addMenu(t("menu.effects.morph"))
        self.eff_contour_action = add_eff(m_morph, t("menu.eff.contour"), "fx_contour.png", self.effect_contour, t("fx.tip.contour"))
        self.eff_maximum_action = add_eff(m_morph, t("menu.eff.max"), "fx_maximum.png", self.effect_maximum, t("fx.tip.maximum"))
        self.eff_minimum_action = add_eff(m_morph, t("menu.eff.min"), "fx_minimum.png", self.effect_minimum, t("fx.tip.minimum"))

        m_noise = effects_menu.addMenu(t("menu.effects.noise"))
        self.eff_noise_action = add_eff(m_noise, t("menu.effects.noise.add"), "fx_noise.png", self.effect_add_noise, t("fx.tip.add_noise"))
        self.eff_median_action = add_eff(m_noise, t("menu.eff.median2"), "fx_median.png", self.effect_median, t("fx.tip.median"))
        self.eff_clouds_action = add_eff(m_noise, t("menu.eff.clouds"), "fx_clouds.png", self.effect_render_clouds, t("fx.tip.clouds"))

        # Submenú para los EFECTOS aportados por plugins de terceros (oculto hasta
        # que el PluginManager registre el primero).
        effects_menu.addSeparator()
        self.effects_plugins_menu = effects_menu.addMenu(t("menu.plugins"))
        self.effects_plugins_menu.menuAction().setVisible(False)

        # =====================================================================
        # MENÚ IA  (funciones de IA local; va antes de Ayuda, que queda el último)
        # =====================================================================
        ai_menu = menu_bar.addMenu(t("menu.ai", default="&IA"))
        self._ai_actions = []   # acciones que se deshabilitan mientras hay trabajo IA

        def add_ai(text, icon, slot):
            act = QAction(text, self)
            if icon and QFile.exists(":/icons/" + icon):
                act.setIcon(crear_icono(":/icons/" + icon))
            # Al lanzar la acción recordamos su icono en self._ai_active_icon: la
            # barra de estado (_ai_status) y el Historial (_ai_tag) lo usan para
            # mostrar el icono propio del efecto de IA, no el del pincel.
            def _run(checked=False, _icon=icon, _slot=slot):
                self._ai_active_icon = _icon
                _slot()
            act.triggered.connect(_run)
            ai_menu.addAction(act)
            self._ai_actions.append(act)
            return act

        def ai_section(key, first=False):
            """Abre una sección del menú IA. Con IA_MENU_CABECERAS añade una CABECERA
            (rótulo gris + una regla que continúa en la MISMA línea, tras el texto,
            hasta el borde); sin él, solo una línea divisoria (salvo en la primera).
            Reversible con el flag, no rompe nada más."""
            if IA_MENU_CABECERAS:
                from PySide6.QtWidgets import (QWidgetAction, QWidget,
                                               QHBoxLayout, QSizePolicy)
                row = QWidget()
                row.setStyleSheet("background: transparent;")
                h = QHBoxLayout(row)
                h.setContentsMargins(10, 6, 12, 2)
                h.setSpacing(8)
                lbl = QLabel(t(key))
                lbl.setStyleSheet(
                    f"color: {theme.TEXT_MUTED}; background: transparent;"
                    f" font-size: 10px; font-weight: bold;")
                h.addWidget(lbl, 0)
                line = QWidget()
                line.setFixedHeight(1)
                line.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                line.setStyleSheet(f"background-color: {theme.BORDER};")
                h.addWidget(line, 1)
                wa = QWidgetAction(ai_menu)
                wa.setDefaultWidget(row)
                wa.setEnabled(False)
                ai_menu.addAction(wa)
            elif not first:
                ai_menu.addSeparator()

        # Reorganizado por TIPO de tarea (cabeceras opcionales, ver IA_MENU_CABECERAS).
        # Los self.ai_*_action no cambian: solo su orden y su sección.
        ai_section("menu.ai.grp.enhance", first=True)
        self.ai_denoise_action = add_ai(
            t("menu.ai.denoise", default="Reducir ruido"),
            "ai_denoise.png", self.ai_denoise)
        self.ai_faces_action = add_ai(
            t("menu.ai.faces", default="Restaurar caras"),
            "ai_faces.png", self.ai_restore_faces)
        self.ai_upscale2_action = add_ai(
            t("menu.ai.upscale2", default="Aumentar resolución ×2"),
            "ai_upscale.png", lambda checked=False: self.ai_upscale(2))
        self.ai_upscale4_action = add_ai(
            t("menu.ai.upscale4", default="Aumentar resolución ×4"),
            "ai_upscale.png", lambda checked=False: self.ai_upscale(4))
        self.ai_colorize_action = add_ai(
            t("menu.ai.colorize", default="Colorizar (blanco y negro)"),
            "ai_colorize.png", self.ai_colorize)

        ai_section("menu.ai.grp.retouch")
        self.ai_inpaint_action = add_ai(
            t("menu.ai.inpaint", default="Borrar objeto (relleno inteligente)"),
            "ai_inpaint.png", self.ai_inpaint_selection)
        self.ai_redeye_action = add_ai(
            t("menu.ai.redeye", default="Eliminar ojos rojos"),
            "ai_redeye.png", self.ai_red_eyes)

        ai_section("menu.ai.grp.subject")
        self.ai_select_subject_action = add_ai(
            t("menu.ai.select_subject", default="Seleccionar sujeto"),
            "ai_select_subject.png", self.ai_select_subject)
        self.ai_select_object_action = add_ai(
            t("menu.ai.select_object", default="Seleccionar objeto..."),
            "ai_select_object.png", self.ai_select_object)
        self.ai_remove_bg_action = add_ai(
            t("menu.ai.remove_bg", default="Eliminar fondo"),
            "ai_remove_bg.png", self.ai_remove_background)
        self.ai_blur_bg_action = add_ai(
            t("menu.ai.blur_bg", default="Desenfocar fondo..."),
            "ai_blur_bg.png", self.ai_blur_background)
        self.ai_color_pop_action = add_ai(
            t("menu.ai.color_pop", default="Realce de color (fondo gris)"),
            "ai_color_pop.png", self.ai_color_pop)
        self.ai_replace_color_action = add_ai(
            t("menu.ai.replace_color", default="Reemplazar fondo por color..."),
            "ai_replace_color.png", self.ai_replace_background_color)
        self.ai_replace_image_action = add_ai(
            t("menu.ai.replace_image", default="Reemplazar fondo por imagen..."),
            "ai_replace_image.png", self.ai_replace_background_image)

        ai_section("menu.ai.grp.frame")
        self.ai_horizon_action = add_ai(
            t("menu.ai.horizon", default="Enderezar horizonte"),
            "ai_horizon.png", self.ai_straighten_horizon)
        self.ai_persp_action = add_ai(
            t("menu.ai.persp", default="Corregir perspectiva"),
            "ai_persp.png", self.ai_fix_perspective)
        self.ai_pano_action = add_ai(
            t("menu.ai.pano", default="Crear panorama..."),
            "ai_pano.png", self.ai_panorama)

        ai_section("menu.ai.grp.creative")
        self.ai_bokeh_action = add_ai(
            t("menu.ai.bokeh", default="Bokeh por profundidad..."),
            "ai_bokeh.png", self.ai_depth_bokeh)
        self.ai_anaglyph_action = add_ai(
            t("menu.ai.anaglyph", default="Efecto 3D (anaglifo)..."),
            "ai_anaglyph.png", self.ai_anaglyph)

        ai_section("menu.ai.grp.tools")
        self.ai_ocr_action = add_ai(
            t("menu.ai.ocr", default="Extraer texto (OCR)"),
            "ai_ocr.png", self.ai_ocr)

        ai_menu.addSeparator()
        self.ai_models_action = QAction(
            t("menu.ai.models", default="Gestionar modelos de IA..."), self)
        if QFile.exists(":/icons/ai_models.png"):
            self.ai_models_action.setIcon(crear_icono(":/icons/ai_models.png"))
        self.ai_models_action.triggered.connect(self.open_ai_models)
        ai_menu.addAction(self.ai_models_action)

        # Estado de menús POR CONTEXTO: cada menú refresca el habilitado de sus
        # acciones justo antes de mostrarse (igual que Capas). Así nunca queda una
        # acción activa sin nada que hacer (p. ej. Zoom/IA en la bienvenida) sea
        # cual sea el evento que cambió el estado.
        file_menu.aboutToShow.connect(self.update_edit_actions_state)
        edit_menu.aboutToShow.connect(self.update_edit_actions_state)
        image_menu.aboutToShow.connect(self.update_edit_actions_state)
        view_menu.aboutToShow.connect(self.update_view_menu_state)
        ai_menu.aboutToShow.connect(self.update_ai_menu_state)

        # =====================================================================
        # MENÚ AYUDA
        # =====================================================================
        help_menu = menu_bar.addMenu(t("menu.help", default="&Ayuda"))
        self.manual_action = QAction(t("menu.help.manual", default="Manual..."), self)
        self.manual_action.setShortcut("F1")
        if QFile.exists(":/icons/manual.png"): self.manual_action.setIcon(crear_icono(":/icons/manual.png"))
        self.manual_action.triggered.connect(self.open_manual)
        help_menu.addAction(self.manual_action)

        self.shortcuts_action = QAction(t("menu.help.shortcuts", default="Atajos de teclado..."), self)
        if QFile.exists(":/icons/shortcuts.png"): self.shortcuts_action.setIcon(crear_icono(":/icons/shortcuts.png"))
        self.shortcuts_action.triggered.connect(self.open_shortcuts)
        help_menu.addAction(self.shortcuts_action)

        self.plugin_guide_action = QAction(t("menu.help.plugins", default="Crear plugins..."), self)
        if QFile.exists(":/icons/adjust.png"): self.plugin_guide_action.setIcon(crear_icono(":/icons/adjust.png"))
        self.plugin_guide_action.triggered.connect(self.open_plugin_guide)
        help_menu.addAction(self.plugin_guide_action)

        help_menu.addSeparator()
        self.about_action = QAction(t("menu.help.about", default="Acerca de Imago..."), self)
        if QFile.exists(":/icons/about.png"): self.about_action.setIcon(crear_icono(":/icons/about.png"))
        self.about_action.triggered.connect(self.open_about)
        help_menu.addAction(self.about_action)

    # ---------------------------------------------------------------- plugins
