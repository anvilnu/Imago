from i18n import t
from imago_version import APP_VERSION
# help_dialogs.py
"""Diálogos del menú Ayuda y de Preferencias (Edición → Preferencias).

Todos heredan de FramelessDialog (sin marco, con barra de título propia) y usan
los tokens/funciones de theme.py para el estilo. Contiene:
  - PreferencesDialog : opciones de la app (arranque, idioma...).
  - AboutDialog       : "Acerca de" con logo, versión y descripción.
  - ManualDialog      : manual de uso de Imago.
  - ShortcutsDialog   : referencia de atajos de teclado.
"""

import os
from PySide6.QtWidgets import (QLabel, QPushButton, QHBoxLayout, QComboBox,
                               QTextBrowser, QWidget, QSizePolicy, QListWidget,
                               QListWidgetItem, QSpinBox, QCheckBox, QFrame,
                               QVBoxLayout, QStackedWidget)
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt, QFile
from widgets.custom_titlebar import FramelessDialog
import theme

def _dark():
    """Estilo base de los diálogos de ayuda (fondo + etiquetas). Función (no
    constante) para que responda al tema activo; una constante de módulo se
    congelaría con el tema que hubiera al importar."""
    return "QDialog { background-color: %s; } QLabel { color: %s; }" % (
        theme.BG_WINDOW, theme.TEXT)


# Colores FIJOS que usan los HTML de ayuda (Manual, guía de plugins, atajos) en
# atributos style=. Se sustituyen por los del tema al pintar, para que el texto
# se lea igual en claro y en oscuro. No incluye #000000 (aparece en el CÓDIGO de
# ejemplo mostrado, no como estilo).
def _themed_html(html):
    import re
    mapa = {
        "#e0e0e0": theme.TEXT,
        "#9cc6ff": theme.INFO_BLUE,
        "#888888": theme.TEXT_MUTED,
        "#ffcc66": theme.WARNING,
        "#202020": theme.BG_DARK,   # fondo de los bloques de código
        "#555555": theme.BORDER,
    }
    # UN SOLO PASO (regex): cada color original se sustituye una única vez y el
    # valor resultante NO se vuelve a escanear. Con .replace() encadenado había
    # colisión: theme.TEXT vale #202020, que es la clave vieja de BG_DARK, así
    # que el texto (#e0e0e0 -> #202020) acababa reconvertido a #e4e4e4 (invisible).
    patron = re.compile("|".join(re.escape(k) for k in mapa))
    return patron.sub(lambda mo: mapa[mo.group(0)], html)


def _section_header(text):
    """Cabecera de sección: título en negrita + línea fina hasta el borde."""
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


def _text_browser():
    tb = QTextBrowser()
    tb.setOpenExternalLinks(False)
    tb.setStyleSheet(
        "QTextBrowser { background-color: %s; color: %s; border: 1px solid %s;"
        " border-radius: 4px; padding: 8px; }" % (theme.BG_DARK, theme.TEXT, theme.BORDER))
    return tb


# =====================================================================
# Preferencias (Edición → Preferencias)
# =====================================================================
class PreferencesDialog(FramelessDialog):
    """Preferencias de la aplicación.
    Los valores se guardan en QSettings y se aplican en el próximo arranque."""

    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.settings = main_window.settings
        self.setWindowTitle(t("pref.title", default="Preferencias"))
        self._body.setFixedSize(660, 340)
        self.setStyleSheet(_dark() + theme.combobox_dialog_qss()
                           + theme.spinbox_qss() + theme.checkbox_qss()
                           + theme.dialog_button_plain_qss() + theme.list_qss())

        # Diseño como el Manual de Imago: índice de secciones a la IZQUIERDA y, a
        # la DERECHA, SOLO los controles de la sección elegida (un QStackedWidget
        # con una página por sección). Antes todo iba apilado en una sola columna
        # que crecía sin parar. La sección activa por defecto es General.
        main_layout = QHBoxLayout()
        self.body_layout.addLayout(main_layout, 1)

        # --- Columna izquierda: índice de secciones ---
        self.nav = QListWidget()
        self.nav.setFixedWidth(150)
        self.nav.setStyleSheet(theme.list_qss() + """
            QListWidget::item { margin: 0px; padding: 6px 8px; }
        """)
        for etiqueta in (t("pref.general", default="General"),
                         t("pref.lang.title", default="Idioma"),
                         t("pref.history", default="Historial"),
                         t("pref.nav.ai", default="IA"),
                         t("pref.nav.save", default="Guardado"),
                         t("pref.plugins", default="Plugins")):
            self.nav.addItem(etiqueta)
        main_layout.addWidget(self.nav)

        # --- Columna derecha: páginas (una por sección), dentro de un recuadro ---
        box = QFrame()
        box.setObjectName("PrefBox")
        box.setStyleSheet(
            "QFrame#PrefBox { background-color: %s; border: 1px solid %s;"
            " border-radius: 4px; }" % (theme.BG_DARK, theme.BORDER))
        box_lay = QVBoxLayout(box)
        box_lay.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        box_lay.addWidget(self.stack)
        main_layout.addWidget(box, 1)

        # Construir cada página EN EL MISMO ORDEN que el índice.
        self._build_general_page()
        self._build_language_page()
        self._build_history_page()
        self._build_ai_page()
        self._build_save_page()
        self._build_plugins_page()

        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)   # General por defecto

        # --- Botones inferiores (FUERA del recuadro, como en el Manual) ---
        btns = QHBoxLayout()
        btns.addStretch()
        ok = QPushButton(t("msg.ok", default="Aceptar"))
        ok.clicked.connect(self._save_and_accept)
        cancel = QPushButton(t("msg.cancel", default="Cancelar"))
        cancel.clicked.connect(self.reject)
        btns.addWidget(ok)
        btns.addWidget(cancel)
        self.body_layout.addLayout(btns)

    # ------------------------------------------------------------------
    # Páginas del stack (una por sección). _new_page crea el contenedor con
    # su cabecera; cada _build_* añade sus controles y la registra en el stack.
    # ------------------------------------------------------------------
    def _new_page(self, title):
        page = QWidget()
        # Fondo transparente ACOTADO al propio widget (selector por objectName):
        # un "background: transparent;" pelado se propaga a los hijos y les
        # envenena la paleta (los combos heredaban Base=#000000 -> popup negro).
        page.setObjectName("PrefPage")
        page.setStyleSheet("QWidget#PrefPage { background: transparent; }")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.addLayout(_section_header(title))
        lay.addSpacing(4)
        return page, lay

    def _note(self, text):
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-style: italic; font-size: 11px;")
        return lbl

    def _build_general_page(self):
        page, layout = self._new_page(t("pref.general", default="General"))
        # Al iniciar
        row = QHBoxLayout()
        lbl = QLabel(t("pref.startup.label", default="Al iniciar:"))
        lbl.setMinimumWidth(90)
        row.addWidget(lbl)
        self.startup_combo = QComboBox()
        self.startup_combo.addItem(t("pref.startup.welcome", default="Mostrar pantalla de bienvenida"), "welcome")
        self.startup_combo.addItem(t("pref.startup.blank", default="Abrir un lienzo en blanco"), "blank")
        cur = str(self.settings.value("startup_mode", "welcome"))
        i = self.startup_combo.findData(cur)
        if i >= 0:
            self.startup_combo.setCurrentIndex(i)
        row.addWidget(self.startup_combo, 1)
        layout.addLayout(row)

        layout.addSpacing(10)

        # Tema visual (claro / oscuro). Se aplica al reiniciar.
        row_theme = QHBoxLayout()
        lbl_theme = QLabel(t("pref.theme.label", default="Tema:"))
        lbl_theme.setMinimumWidth(90)
        row_theme.addWidget(lbl_theme)
        self.theme_combo = QComboBox()
        self.theme_combo.addItem(t("pref.theme.dark", default="Oscuro"), "dark")
        self.theme_combo.addItem(t("pref.theme.light", default="Claro"), "light")
        cur_theme = str(self.settings.value("theme", "dark"))
        k = self.theme_combo.findData(cur_theme)
        if k >= 0:
            self.theme_combo.setCurrentIndex(k)
        row_theme.addWidget(self.theme_combo, 1)
        layout.addLayout(row_theme)
        layout.addWidget(self._note(
            t("pref.theme.note",
              default="El cambio de tema se aplica al reiniciar.")))

        layout.addSpacing(10)

        # Mini panel de color en la barra de Herramientas
        self.mini_color_check = QCheckBox(
            t("pref.general.mini_color",
              default="Mostrar mini panel de color en herramientas al cerrar panel de color"))
        self.mini_color_check.setChecked(
            self.settings.value("panels/mini_color_selector", True, type=bool))
        layout.addWidget(self.mini_color_check)
        layout.addWidget(self._note(
            t("pref.general.mini_color.note",
              default="El mini selector aparece al pie del panel de Herramientas cuando "
                      "el panel de Color está cerrado.")))

        layout.addSpacing(10)

        # Reordenar los botones de la barra de Herramientas
        self.tools_reorder_check = QCheckBox(
            t("pref.general.tools_reorder",
              default="Permitir reordenar los botones de la barra de herramientas"))
        self.tools_reorder_check.setChecked(
            self.settings.value("panels/tools_reorderable", True, type=bool))
        layout.addWidget(self.tools_reorder_check)
        layout.addWidget(self._note(
            t("pref.general.tools_reorder.note",
              default="Si se desactiva, los botones de herramientas quedan fijos y no se "
                      "pueden arrastrar.")))

        layout.addStretch()
        self.stack.addWidget(page)

    def _build_language_page(self):
        page, layout = self._new_page(t("pref.lang.title", default="Idioma"))
        row = QHBoxLayout()
        lbl = QLabel(t("pref.lang.label", default="Idioma:"))
        lbl.setMinimumWidth(90)
        row.addWidget(lbl)
        self.lang_combo = QComboBox()
        self.lang_combo.addItem("Español", "es")
        self.lang_combo.addItem("English", "en")
        self.lang_combo.addItem("Français", "fr")
        cur_lang = str(self.settings.value("language", "es"))
        j = self.lang_combo.findData(cur_lang)
        if j >= 0:
            self.lang_combo.setCurrentIndex(j)
        row.addWidget(self.lang_combo, 1)
        layout.addLayout(row)
        layout.addWidget(self._note(t("pref.lang.note", default="Más idiomas próximamente.")))
        layout.addStretch()
        self.stack.addWidget(page)

    def _build_history_page(self):
        page, layout = self._new_page(t("pref.history", default="Historial"))
        row = QHBoxLayout()
        lbl = QLabel(t("pref.undo_limit.label", default="Pasos de deshacer:"))
        lbl.setMinimumWidth(90)
        row.addWidget(lbl)
        self.undo_limit_spin = QSpinBox()
        self.undo_limit_spin.setRange(0, 1000)
        self.undo_limit_spin.setSpecialValueText(
            t("pref.undo_limit.unlimited", default="Sin límite"))
        try:
            cur_limit = int(self.settings.value("undo_limit", 100))
        except (TypeError, ValueError):
            cur_limit = 100
        self.undo_limit_spin.setValue(max(0, cur_limit))
        row.addWidget(self.undo_limit_spin, 1)
        layout.addLayout(row)
        layout.addWidget(self._note(
            t("pref.undo_limit.note",
              default="Se aplica a los documentos que abras a partir de ahora (0 = sin límite).")))
        layout.addStretch()
        self.stack.addWidget(page)

    def _build_ai_page(self):
        page, layout = self._new_page(t("pref.ai", default="Inteligencia artificial"))
        self.use_gpu_check = QCheckBox(
            t("pref.ai.use_gpu", default="Usar la GPU si está disponible"))
        self.use_gpu_check.setChecked(
            self.settings.value("ai/use_gpu", True, type=bool))
        layout.addWidget(self.use_gpu_check)
        layout.addWidget(self._note(
            t("pref.ai.use_gpu.note",
              default="Solo surte efecto si el motor de IA instalado ofrece un proveedor de GPU.")))
        layout.addStretch()
        self.stack.addWidget(page)

    def _build_save_page(self):
        page, layout = self._new_page(t("pref.save", default="Guardado de imágenes"))
        self.keep_exif_check = QCheckBox(
            t("pref.save.keep_exif",
              default="Conservar metadatos EXIF al guardar JPEG (fecha, cámara, GPS…)"))
        self.keep_exif_check.setChecked(
            self.settings.value("save/keep_exif", True, type=bool))
        layout.addWidget(self.keep_exif_check)
        # Sub-casilla sangrada: solo tiene sentido si se conserva el EXIF.
        row_gps = QHBoxLayout()
        row_gps.addSpacing(22)
        self.keep_gps_check = QCheckBox(
            t("pref.save.keep_gps", default="Incluir la ubicación GPS (privacidad)"))
        self.keep_gps_check.setChecked(
            self.settings.value("save/keep_gps", True, type=bool))
        self.keep_gps_check.setEnabled(self.keep_exif_check.isChecked())
        self.keep_exif_check.toggled.connect(self.keep_gps_check.setEnabled)
        row_gps.addWidget(self.keep_gps_check)
        row_gps.addStretch()
        layout.addLayout(row_gps)
        row_gps_note = QHBoxLayout()
        row_gps_note.addSpacing(44)
        self.keep_gps_note = self._note(
            t("pref.save.keep_gps.note",
              default="Al desmarcarla, Imago sobrescribe físicamente los datos "
                      "GPS del EXIF antes de guardar. Si el bloque no puede "
                      "limpiarse con seguridad, no conserva ningún EXIF."))
        self.keep_gps_note.setEnabled(self.keep_exif_check.isChecked())
        self.keep_exif_check.toggled.connect(self.keep_gps_note.setEnabled)
        row_gps_note.addWidget(self.keep_gps_note, 1)
        layout.addLayout(row_gps_note)
        layout.addStretch()
        self.stack.addWidget(page)

    def _build_plugins_page(self):
        page, layout = self._new_page(t("pref.plugins", default="Plugins"))
        self.load_plugins_check = QCheckBox(
            t("pref.plugins.load_third_party",
              default="Cargar plugins de terceros (código de otros autores)"))
        self.load_plugins_check.setChecked(
            self.settings.value("plugins/load_third_party", True, type=bool))
        layout.addWidget(self.load_plugins_check)
        layout.addWidget(self._note(
            t("pref.plugins.note",
              default="Un plugin es código Python sin aislamiento. Imago pedirá "
                      "permiso antes de ejecutar cada plugin nuevo o modificado. "
                      "Se aplica al reiniciar.")))
        layout.addStretch()
        self.stack.addWidget(page)

    def _save_and_accept(self):
        old_lang = str(self.settings.value("language", "es"))
        new_lang = self.lang_combo.currentData()

        old_theme = str(self.settings.value("theme", "dark"))
        new_theme = self.theme_combo.currentData()

        old_use_gpu = self.settings.value("ai/use_gpu", True, type=bool)
        new_use_gpu = bool(self.use_gpu_check.isChecked())

        self.settings.setValue("startup_mode", self.startup_combo.currentData())
        self.settings.setValue("language", new_lang)
        self.settings.setValue("theme", new_theme)
        self.settings.setValue("undo_limit", int(self.undo_limit_spin.value()))
        self.settings.setValue("ai/use_gpu", new_use_gpu)
        self.settings.setValue("save/keep_exif", bool(self.keep_exif_check.isChecked()))
        self.settings.setValue("save/keep_gps", bool(self.keep_gps_check.isChecked()))
        self.settings.setValue("plugins/load_third_party", bool(self.load_plugins_check.isChecked()))
        self.settings.setValue("panels/mini_color_selector", bool(self.mini_color_check.isChecked()))
        self.settings.setValue("panels/tools_reorderable", bool(self.tools_reorder_check.isChecked()))
        # Aplicar en vivo (no requieren reiniciar): mini selector de color y el
        # bloqueo de reordenación de la barra de herramientas.
        if hasattr(self.main_window, "_update_tools_color_selector_visibility"):
            self.main_window._update_tools_color_selector_visibility()
        if hasattr(self.main_window, "tools_panel"):
            self.main_window.tools_panel.set_reorderable(
                bool(self.tools_reorder_check.isChecked()))

        if old_use_gpu != new_use_gpu:
            # Vaciar la caché de sesiones ONNX para que el cambio aplique ya
            # (sin reiniciar): la próxima inferencia crea la sesión con el
            # proveedor nuevo. Import perezoso: no arrastra onnxruntime.
            from ai.runner import clear_sessions
            clear_sessions()
            # Reevaluar la GPU: olvida qué modelos se marcaron como "GPU no apta"
            # (p. ej. si se cambió el driver), para volver a probar la GPU con ellos.
            from ai.subproc import clear_gpu_unsafe
            clear_gpu_unsafe()

        self.accept()

        # Cambios que requieren reiniciar (idioma o tema). Si cambian ambos, un
        # solo aviso: el reinicio aplica los dos. El idioma tiene prioridad de
        # mensaje por ser el cambio más visible.
        if old_lang != new_lang:
            titulo, cuerpo = t("pref.lang.restart_title"), t("msg.lang_restart")
        elif old_theme != new_theme:
            titulo, cuerpo = t("pref.theme.restart_title"), t("msg.theme_restart")
        else:
            titulo = None
        if titulo is not None:
            from widgets.custom_titlebar import imago_question
            from PySide6.QtWidgets import QMessageBox
            resp = imago_question(
                self.main_window,
                titulo,
                cuerpo,
                buttons=(QMessageBox.Ok | QMessageBox.Cancel),
                default=QMessageBox.Ok)
            if resp == QMessageBox.Ok:
                self.main_window.reiniciar_app()


# =====================================================================
# Acerca de
# =====================================================================
class AboutDialog(FramelessDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("about.title", default="Acerca de Imago"))
        self._body.setFixedSize(400, 380)
        self.setStyleSheet(_dark() + theme.dialog_button_plain_qss())

        layout = self.body_layout
        layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        # Recuadro con el icono y los textos (mismo estilo que el Manual/Atajos)
        box = QFrame()
        box.setStyleSheet(
            "QFrame { background-color: %s; border: 1px solid %s;"
            " border-radius: 4px; }" % (theme.BG_DARK, theme.BORDER))
        box_layout = QVBoxLayout(box)
        box_layout.setContentsMargins(16, 16, 16, 16)
        box_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        logo = QLabel()
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setStyleSheet("border: none;")
        if QFile.exists(":/icons/imago.png"):
            logo.setPixmap(QPixmap(":/icons/imago.png").scaled(
                84, 84, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        box_layout.addWidget(logo)

        title = QLabel("Imago")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color: %s; font-size: 26px; font-weight: bold; border: none;" % theme.TEXT)
        box_layout.addWidget(title)

        ver = QLabel(t("about.version", v=APP_VERSION, default="Versión {v}"))
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ver.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 12px; border: none;")
        box_layout.addWidget(ver)

        box_layout.addSpacing(10)
        desc = QLabel(t("about.desc").replace("\\n", "\n"))
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setStyleSheet("color: %s; font-size: 12px; border: none;" % theme.TEXT)
        desc.setWordWrap(True)
        box_layout.addWidget(desc)

        box_layout.addSpacing(10)
        autor = QLabel(t("about.author", default="Creado por AVN Bramg"))
        autor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        autor.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 12px; border: none;")
        box_layout.addWidget(autor)

        layout.addWidget(box)

        layout.addStretch()
        btns = QHBoxLayout()
        btns.addStretch()
        close = QPushButton(t("btn.close", default="Cerrar"))
        close.clicked.connect(self.accept)
        btns.addWidget(close)
        btns.addStretch()
        layout.addLayout(btns)


# =====================================================================
# Manual
# =====================================================================
_MANUAL_HTML_ES = """
<a name="intro"></a>
<h2 style="color:#e0e0e0; font-size:20px;">Bienvenida a Imago</h2>
<p>Imago es un editor de imágenes de escritorio que combina la <b>potencia</b> de las herramientas profesionales con la <b>simplicidad</b> de los editores clásicos. Inspirado en programas como Paint.NET, busca ser ligero y ágil sin renunciar a las funciones que necesitas.</p>
<p>Con Imago puedes hacer desde recortes rápidos y correcciones de color hasta fotomontajes complejos, gracias a su motor de <b>capas</b>, <b>máscaras no destructivas</b>, <b>efectos con vista previa en vivo</b> y un completo conjunto de funciones de <b>Inteligencia Artificial</b> que se ejecutan en tu propio ordenador.</p>
<p><b>Imago está disponible en español, inglés y francés.</b> Puedes cambiar el idioma en Edición → Preferencias (el cambio se aplica al reiniciar).</p>
<p style="color:#9cc6ff;"><b>Consejo:</b> este manual tiene un índice a la izquierda. Haz clic en cualquier sección para saltar a ella.</p>

<br><a name="interfaz"></a>
<h2 style="color:#e0e0e0; font-size:20px;">Interfaz y área de trabajo</h2>
<ul>
<li><b>Barra de menús:</b> En la parte superior. Reúne todas las acciones organizadas por menús (Archivo, Edición, Imagen, Capas, Ajustes, Efectos, IA, Ver y Ayuda).</li>
<li><b>Barra de opciones dinámica:</b> Justo debajo de los menús. Su contenido <b>cambia según la herramienta activa</b>: muestra solo lo que esa herramienta necesita (el tamaño y la dureza del pincel, la tolerancia del bote, el estilo de una forma, la fuente del texto...).</li>
<li><b>El lienzo:</b> El corazón de Imago. Acércate con <code>Ctrl+Rueda</code>, desplázate con la rueda (o manteniendo <b>Espacio</b> y arrastrando) y apóyate en las <b>reglas</b> (en píxeles o centímetros).</li>
<li><b>Paneles laterales:</b> Herramientas (a la izquierda) e Histograma, Historial, Capas y Color (a la derecha). Van <b>empotrados</b> en la ventana, no flotan: puedes cambiar su tamaño arrastrando las divisiones entre ellos, y ocultarlos o mostrarlos con los botones de la esquina superior derecha para ganar espacio. Los paneles de la <b>columna derecha</b> se pueden <b>reordenar</b> con los botones ▲/▼ de su cabecera, y el de <b>Herramientas</b> permite <b>recolocar sus botones</b> arrastrándolos a la posición que prefieras; con un clic derecho sobre el panel, <b>Restaurar orden por defecto</b> los devuelve a su posición original con un solo clic.</li>
<li><b>Histograma en vivo:</b> El panel de <b>Histograma</b> muestra la distribución tonal de la imagen y se <b>actualiza solo</b> mientras editas. Elige el canal en su desplegable (<b>Luminosidad</b>, <b>RGB</b> superpuesto, o Rojo/Verde/Azul por separado) y <b>léelo con el ratón</b>: al pasar el cursor marca el nivel bajo él ("Nivel 128 · 2.4 %") y <b>arrastrando</b> mides un rango entero ("Rango 60–190 · 78 %"); un clic seco quita el rango. Se muestra/oculta con su botón de la esquina superior derecha.</li>
<li><b>Barra de estado:</b> En la parte inferior. Indica el nivel de zoom y la posición del cursor sobre la imagen.</li>
<li><b>Ver a pantalla completa:</b> Con <code>F11</code> (o <b>Ver ▸ Ver a pantalla completa</b>) se muestra solo la imagen, ocupando toda la pantalla, para revisarla. Dentro puedes hacer zoom (rueda o <code>+</code>/<code>-</code>), desplazarla arrastrando, ajustarla con <code>0</code>/<code>F</code> o verla a tamaño real con <code>1</code>; sal con <code>Esc</code>.</li>
<li><b>Tema claro u oscuro:</b> En <b>Preferencias ▸ Tema</b> puedes elegir el aspecto oscuro (por defecto) o el claro; el cambio se aplica al reiniciar.</li>
</ul>

<br><a name="archivos"></a>
<h2 style="color:#e0e0e0; font-size:20px;">Gestión de archivos</h2>
<p>Imago admite los formatos estándar más habituales (PNG, JPEG, WebP, BMP, GIF, SVG, TGA, ICO y los modernos <b>AVIF, HEIC y JPEG XL</b>, entre otros) además de su formato nativo, y también abre documentos de <b>Photoshop</b> (PSD y PSB) conservando sus capas.</p>
<ul>
<li><b>Nuevo (<code>Ctrl+N</code>):</b> Crea un lienzo vacío. Puedes definir el tamaño en <b>píxeles</b> (para pantalla) o en <b>centímetros/pulgadas</b> con una resolución (PPP) para impresión. También eliges el <b>color de fondo</b> inicial: blanco, negro, transparente o el color de la paleta.</li>
<li><b>Arrastrar y soltar:</b> Suelta una imagen desde tu explorador de archivos sobre la ventana de Imago para abrirla como un documento nuevo.</li>
<li><b>El formato .imago:</b> Si trabajas con varias capas, máscaras o guías, <b>guarda (<code>Ctrl+S</code>)</b> en el formato nativo <b>.imago</b>. Conserva toda la estructura del proyecto para seguir editándolo más adelante.</li>
<li><b>Exportar (Guardar como...):</b> Con <code>Ctrl+Shift+S</code> guardas el resultado final en PNG, JPEG (con ajuste de calidad) o WebP. Al exportar, Imago combina automáticamente todas las capas.</li>
<li><b>Importar SVG:</b> Al abrir un archivo vectorial <b>.svg</b>, Imago pregunta a qué tamaño rasterizarlo (con la proporción enlazada) y lo abre como un lienzo con fondo transparente.</li>
<li><b>Exportar PDF:</b> <b>Archivo ▸ Exportar ▸ PDF</b> crea un PDF cuya página mide exactamente lo que la imagen (según sus PPP). Es distinto de <b>Imprimir ▸ Guardar como PDF</b>, que centra la imagen en una hoja de papel.</li>
<li><b>Exportar OpenRaster (.ora):</b> <b>Archivo ▸ Exportar ▸ OpenRaster</b> guarda las capas en el formato de intercambio que abren <b>GIMP y Krita</b>, conservando su opacidad, visibilidad y modo de fusión. Para guardarlo absolutamente todo (texto editable, máscaras aparte...), el formato nativo sigue siendo .imago.</li>
<li><b>Animaciones GIF/WebP:</b> Al abrir un GIF o WebP <b>animado</b>, Imago ofrece convertir sus fotogramas en <b>capas</b> (cada una recuerda su duración original). Con <b>Ver ▸ Previsualizar animación</b> la reproduces sin salir del programa (reproducir/pausa, fotograma a fotograma, duración ajustable) y con <b>Archivo ▸ Exportar ▸ Animación GIF/WebP</b> creas un GIF o WebP animado a partir de las capas visibles, con duración por fotograma y bucle opcional.</li>
<li><b>Propiedades de imagen:</b> <b>Imagen ▸ Propiedades de imagen</b> muestra las dimensiones, la resolución, el tamaño de impresión, el número de capas y los <b>metadatos EXIF</b> de la foto (cámara, fecha, exposición y coordenadas GPS con un botón para ver el lugar en el mapa), además de un histograma de luminosidad.</li>
<li><b>Procesar por lotes:</b> <b>Archivo ▸ Procesar por lotes...</b> aplica una misma receta a <b>una carpeta entera</b> de imágenes: <b>redimensionar</b> (por porcentaje o ajustando a un máximo), <b>convertir de formato</b> (con calidad para JPEG/WebP), <b>renombrar en secuencia</b> (Fondo_001, Fondo_002...) y <b>marca de agua</b> (texto o imagen PNG, con posición, tamaño y opacidad). El resultado va a otra carpeta y <b>nunca sobreescribe</b> nada (si un nombre existe, numera); si no eliges ninguna transformación, los archivos se <b>copian idénticos</b> byte a byte (perfecto para solo renombrar). En JPEG→JPEG conserva los metadatos EXIF. No necesita ningún documento abierto.</li>
<li><b>PNG de 8 bits (paleta):</b> Al guardar un PNG, el diálogo de calidad ofrece <b>"8 bits paleta"</b> con el <b>número de colores</b> (256 a 16) y <b>difuminado</b> opcional para fotos: archivos mucho más pequeños. Para pixel-art con pocos colores la paleta resultante es <b>exacta</b>, transparencia incluida, y el tamaño estimado del diálogo es el real.</li>
</ul>

<br><a name="capas"></a>
<h2 style="color:#e0e0e0; font-size:20px;">Capas y máscaras</h2>
<p>El panel de Capas (a la derecha) permite componer imágenes complejas trabajando por partes sin afectar al resto. Las zonas transparentes se muestran con un tablero de ajedrez gris.</p>
<ul>
<li><b>Ordenar:</b> Arrastra las capas en la lista para reordenarlas. La de arriba tapa a las de abajo.</li>
<li><b>Grupos de capas:</b> El botón con la <b>carpeta</b> (o <b>Capas ▸ Agrupar las capas seleccionadas</b>, <code>Ctrl+G</code>) agrupa las capas seleccionadas en una carpeta (se pueden <b>anidar</b>). En su cabecera tienes la <b>flecha</b> para plegarla/desplegarla, el nombre (<b>clic</b> = seleccionar el grupo entero, para moverlo, duplicarlo o eliminarlo con los botones de siempre) y el <b>ojo</b>, que oculta o muestra todo el grupo sin tocar la casilla de cada capa. Con <b>clic derecho</b> en la cabecera puedes <b>renombrar</b>, <b>desagrupar</b>, <b>duplicar</b>, <b>subir/bajar</b> el grupo entero o <b>eliminarlo</b>. Arrastra capas para <b>meterlas o sacarlas</b> de una carpeta (soltarlas justo bajo su cabecera las mete en la cima). Los grupos se guardan en el proyecto <b>.imago</b>.</li>
<li><b>Modos de fusión:</b> El desplegable <b>Modo</b>, arriba del panel, cambia al instante cómo se mezcla la capa activa con las inferiores: 13 modos (Multiplicar, Trama, Superponer, Luz suave, Diferencia...). Cuando una capa usa un modo distinto de Normal o una opacidad menor del 100%, se indica bajo su nombre en la lista.</li>
<li><b>Propiedades de capa:</b> Con <b>doble clic</b> sobre una capa (o su botón ⚙, o <code>Ctrl+Shift+P</code>) editas su nombre, opacidad, modo y los bloqueos, con vista previa en vivo.</li>
<li><b>Bloqueos de capa:</b> En Propiedades de capa puedes bloquear la <b>transparencia</b> (se pinta sin alterar el alfa), los <b>píxeles</b> (la capa no se puede pintar, ajustar ni borrar) o la <b>posición</b> (la herramienta Mover no la desplaza). Las capas bloqueadas muestran un <b>candado</b> en el panel, y si intentas editarlas la barra de estado te lo recuerda.</li>
<li><b>Máscara de recorte:</b> <b>Capas ▸ Máscara de recorte</b> (<code>Ctrl+Alt+G</code>) hace que la capa activa solo se vea <b>donde la capa de debajo tiene píxeles</b>: por ejemplo, un degradado o una foto "dentro" de un texto o de una forma, sin tocar ninguno de los dos. Varias capas recortadas seguidas comparten la misma base, y la recortada se marca con <b>↳</b> delante del nombre. Es no destructiva, deshacible y se guarda en el proyecto .imago.</li>
<li><b>Máscaras de capa:</b> Haz clic derecho en una capa y añade una máscara. Pintando en <b>negro</b> ocultas partes de la capa y en <b>blanco</b> las vuelves a mostrar: es edición <b>100% no destructiva</b>. Haz clic en la miniatura de la máscara (junto a la capa) para editarla, y en la miniatura principal para volver a pintar la imagen.</li>
<li><b>Efectos de capa (no destructivos):</b> El botón <b>fx</b> (arriba del panel, junto a <b>Modo</b>) añade a la capa activa efectos que se recalculan solos a partir de su contenido, sin tocar los píxeles: <b>Sombra paralela</b>, <b>Sombra interior</b>, <b>Resplandor exterior</b>, <b>Trazo</b> (contorno), <b>Bisel/relieve</b>, <b>Satinado</b>, <b>Superposición de color</b> y <b>Superposición de degradado</b>. Cada efecto se ajusta en un <b>panel con vista previa en vivo</b> y aparece como un renglón bajo su capa, donde puedes <b>activarlo/ocultarlo</b> (casilla), <b>editarlo</b> (clic en su nombre) o <b>quitarlo</b> (×). Funcionan también sobre <b>capas de texto sin rasterizarlas</b>: si editas el texto, la sombra o el trazo se adaptan al instante. Se guardan con el proyecto <b>.imago</b> y son deshacibles.</li>
</ul>

<br><a name="dibujo"></a>
<h2 style="color:#e0e0e0; font-size:20px;">Herramientas de dibujo</h2>
<p>El botón izquierdo del ratón pinta con el color <b>primario</b> y el derecho con el <b>secundario</b>.</p>
<ul>
<li><b>Pincel:</b> Trazo de bordes suaves con Tamaño, Dureza y <b>Opacidad de trazo</b> ajustables (la opacidad es independiente del color y queda uniforme aunque el trazo se solape). Puede pintar con color sólido o con patrones (ladrillos, zig-zag, tablero...). Con <b>Mayús</b> el clic traza una <b>línea recta</b> desde el final del trazo anterior.</li>
<li><b>Lápiz:</b> Trazo de borde duro (<i>sin suavizado</i>), ideal para pixel art o recortes nítidos. También traza <b>líneas rectas con Mayús</b>.</li>
<li><b>Aerógrafo:</b> Suelta pintura de forma continua mientras mantienes pulsado el botón, con un efecto de spray que se acumula.</li>
<li><b>Cuentagotas temporal:</b> En el pincel, el lápiz y el aerógrafo, <b>Alt+clic</b> captura un color del lienzo sin cambiar de herramienta (izquierdo = primario, derecho = secundario).</li>
<li><b>Borrador:</b> Como el pincel, pero deja la capa transparente. Incluye modos avanzados como <b>Borrar fondos</b>, que protege los bordes según el color de la primera muestra que tocas. Si la capa tiene la <b>transparencia bloqueada</b>, la goma no actúa y te lo indica la barra de estado.</li>
<li><b>Tampón de clonar:</b> Mantén <b>Ctrl</b> y haz clic para fijar el origen; después pinta en otra zona para copiar esos píxeles (respeta la opacidad y la dureza del pincel).</li>
<li><b>Reemplazar color:</b> Pinta solo sobre los píxeles parecidos al color en el que haces clic, sustituyéndolos por el color activo.</li>
<li><b>Sobreexponer / Subexponer:</b> Aclara u oscurece la zona pintada, actuando sobre las sombras, los medios tonos o las luces según el <b>Rango</b> elegido; la <b>Exposición</b> regula la intensidad. Mantén <b>Ctrl</b> al empezar el trazo para invertir el modo sin pasar por la barra.</li>
<li><b>Pincel corrector:</b> Pinta sobre una imperfección (una mancha, un cable, una peca...) y, al soltar, Imago la elimina reconstruyéndola a partir de su entorno.</li>
<li><b>Esponja:</b> Sube o baja la <b>saturación</b> de la zona pintada: el modo <b>Desaturar</b> apaga el color hacia el gris (conservando el brillo) y <b>Saturar</b> lo aviva. Mantén <b>Ctrl</b> al empezar el trazo para invertir el modo; el <b>Flujo</b> regula la intensidad y el efecto no se acumula al repasar dentro del mismo trazo.</li>
<li><b>Licuar:</b> <b>Empuja los píxeles</b> en la dirección del trazo, deformando la imagen como pintura líquida: afinar una silueta, arquear una sonrisa, estirar un borde... La <b>Fuerza</b> controla cuánto siguen los píxeles al cursor y la <b>Dureza</b>, la caída del empuje hacia el borde del pincel.</li>
</ul>

<br><a name="formas"></a>
<h2 style="color:#e0e0e0; font-size:20px;">Formas, trazados y texto</h2>
<ul>
<li><b>Formas:</b> Rectángulos, elipses, flechas, estrellas... Al dibujar una forma, queda "viva" (flotante). Mientras lo esté, puedes <b>cambiar en tiempo real su color, grosor, estilo de línea e incluso el tipo de forma</b>. Pulsa <b>Enter</b> para fijarla al lienzo.</li>
<li><b>Pluma:</b> Crea trazados precisos por nodos. Haz clic para añadir nodos y formar polígonos o líneas continuas. Pulsa <b>Esc</b> para terminar.</li>
<li><b>Línea / Curva:</b> Arrastra para trazar una línea recta (con <b>Mayús</b>, en ángulos de 15°). Al soltar aparecen <b>4 nudos</b>: arrástralos para curvarla como spline, Bézier o segmentos rectos (el modo se elige en la barra de opciones). El <b>asa junto a la línea</b> la mueve entera, arrastrar con el <b>botón derecho</b> la gira (Mayús = pasos de 15°) y en <b>Inicio</b>/<b>Final</b> puedes añadir a cada extremo una punta de <b>flecha, círculo o barra</b> (mezclables), con <b>Tamaño</b> propio o "Auto" (el grosor de la línea). <b>Enter</b> la fija y <b>Esc</b> la cancela.</li>
<li><b>Texto:</b> Haz clic en el lienzo y escribe; el texto es editable y ajustas fuente, tamaño y estilo en la barra superior. Un clic sobre <b>cualquier texto existente</b> lo reabre para editarlo (aunque su capa no sea la activa). Las capas de texto siguen siendo editables tras recortar, redimensionar, cambiar el lienzo, voltear o rotar la imagen. Si cambias a la herramienta <b>Mover</b> con el texto abierto, se convierte en un objeto flotante que puedes escalar y girar libremente. Al <b>pegar</b> texto del portapapeles (p. ej. el extraído con IA ▸ Extraer texto), el cuadro gana un <b>tirador</b> en su borde derecho: arrástralo para fijar el ancho y el texto se reajusta envolviéndose dentro.</li>
</ul>

<br><a name="seleccion"></a>
<h2 style="color:#e0e0e0; font-size:20px;">Selección y transformación</h2>
<p>Las selecciones limitan el área donde las herramientas tienen efecto (pintar, borrar, copiar, aplicar un ajuste...).</p>
<ul>
<li><b>Selecciones básicas:</b> Marco rectangular, elíptico y lazo (a mano alzada). Mientras arrastras, la barra de estado muestra el <b>tamaño en vivo</b> y mantener <b>Espacio</b> te deja <b>reposicionar</b> la caja sin soltarla. En la barra de opciones puedes fijar una <b>Relación fija</b> (1:1, 4:3, 16:9…) o un <b>Tamaño fijo</b> en píxeles (con tamaño fijo basta un clic).</li>
<li><b>Lazo poligonal:</b> El lazo tiene un modo <b>Poligonal</b> en su barra de opciones: cada clic añade un vértice, <b>doble clic o Intro</b> cierra el polígono y <b>Esc</b> lo cancela.</li>
<li><b>Varita mágica:</b> Selecciona zonas del mismo color (continuas o de toda la imagen) según una <b>Tolerancia</b> ajustable. El <b>clic derecho resta</b> de la selección.</li>
<li><b>Pincel de selección:</b> Activa la casilla <b>"Pincel de selección"</b> en la barra de opciones del Pincel para "pintar" a mano alzada la zona a seleccionar. El botón izquierdo <b>añade</b> y el derecho <b>resta</b> de la selección.</li>
<li><b>Herramienta Mover:</b> La más versátil. Si hay algo seleccionado, lo recorta y lo convierte en un "objeto flotante" con una caja de tiradores para <b>mover</b>, <b>escalar</b> y <b>girar</b> (acercando el ratón por fuera de los tiradores de las esquinas). Al escalar, el lado opuesto al tirador queda <b>anclado</b> (con <b>Alt</b>, se escala desde el centro) y cruzar el ancla <b>voltea</b> la imagen en espejo; durante el gesto, la barra de estado muestra el tamaño, el ángulo o el desplazamiento. Las <b>flechas</b> mueven el objeto píxel a píxel (Mayús = ×10), también en el modo <b>Mover marquesina</b>.</li>
<li><b>Recorte (C):</b> Caja ajustable con regla de los tercios y oscurecido exterior. En su barra puedes fijar una <b>Proporción</b> (Libre, 1:1, 4:3, 16:9…); <b>Intro</b> aplica y <b>Esc</b> cancela. Las <b>guías</b> se desplazan con el recorte (las que quedan fuera se descartan).</li>
<li><b>Refinar selección:</b> Desde el menú Edición (o la barra de opciones) puedes <b>Expandir</b>, <b>Contraer</b>, <b>Suavizar</b> o <b>Calar</b> los bordes de la selección, convertirla en un anillo con <b>Borde</b>, o ampliarla por color con <b>Crecer</b> (zonas contiguas parecidas) y <b>Seleccionar parecido</b> (toda la imagen), usando la tolerancia de la varita.</li>
</ul>

<br><a name="colores"></a>
<h2 style="color:#e0e0e0; font-size:20px;">Colores y degradados</h2>
<ul>
<li><b>Primario y secundario:</b> El clic izquierdo usa el color primario y el derecho el secundario. La tecla <b>X</b> los intercambia al instante.</li>
<li><b>Panel de colores:</b> Elige el color con la rueda/valores RGB, por código hexadecimal o desde las muestras predefinidas.</li>
<li><b>Muestras propias:</b> Debajo de la paleta fija puedes guardar tus propios colores: el botón <b>+</b> añade el color primario actual y el botón <b>…</b> importa una <b>paleta de GIMP (.gpl)</b>. Clic en una muestra para usarla; clic derecho para usarla como secundario o eliminarla. Se conservan entre sesiones.</li>
<li><b>Cuentagotas:</b> Haz clic en el lienzo para capturar un color de la imagen (izquierdo = primario, derecho = secundario).</li>
<li><b>Bote de pintura:</b> Rellena un área con color sólido o con un <b>patrón geométrico</b> según una tolerancia. La <b>Expansión</b> ensancha el relleno unos píxeles bajo el contorno: perfecta para colorear dibujos sin dejar un halo claro junto a las líneas.</li>
<li><b>Degradado:</b> Crea transiciones suaves. Haz clic y arrastra en el lienzo para fijar la dirección y la longitud del degradado.</li>
</ul>

<br><a name="ajustes"></a>
<h2 style="color:#e0e0e0; font-size:20px;">Ajustes y efectos</h2>
<p>Todos los menús de Ajustes y Efectos se muestran en un <b>panel superpuesto con vista previa en vivo</b>: ves el resultado sobre el lienzo antes de aplicarlo (pulsa Aceptar para confirmar o Cancelar/Esc para descartar).</p>
<ul>
<li><b>Correcciones de color:</b> Curvas, Niveles, Tono/Saturación y Equilibrio de color para retocar fotografías.</li>
<li><b>Ajustes automáticos:</b> En <b>Ajustes ▸ Automático</b> tienes correcciones de un clic: <b>Auto-niveles</b> (ajusta el punto negro y blanco de cada canal), <b>Auto-contraste</b> (recupera contraste sin alterar el color), <b>Auto-color</b> (neutraliza dominantes) y <b>Ecualizar histograma</b>.</li>
<li><b>Mapa de degradado:</b> Colorea la imagen asignando su luminosidad a un degradado de 3 colores (Sombras, Medios tonos, Luces). Ideal para <i>color grading</i>.</li>
<li><b>Duotono / tritono:</b> En <b>Ajustes ▸ Blanco y negro</b>, reproduce la imagen con dos o tres <b>tintas</b> según su luminosidad, como un viraje de imprenta.</li>
<li><b>Distorsión y estilo:</b> Entre muchos otros efectos: <b>Coordenadas polares</b> (envuelve la imagen en torno al centro, o la desenrolla) y <b>Vidrio esmerilado</b> en Efectos ▸ Distorsionar, y <b>Cristalizar</b> (teselas irregulares de color plano) en Efectos ▸ Estilizar.</li>
<li><b>Estilos de capa:</b> Sombra paralela, Resplandores, Bisel y relieve, y Trazo. Se aplican sobre los <b>bordes transparentes</b> de la capa. Prueba a escribir un texto y darle una sombra y un bisel para ver su potencial.</li>
</ul>

<br><a name="plugins"></a>
<h2 style="color:#e0e0e0; font-size:20px;">Plugins (extensiones)</h2>
<p>Imago admite <b>plugins de terceros</b> que añaden nuevos <b>Ajustes</b> y <b>Efectos</b>, con la misma vista previa en vivo que los integrados. Aparecen en los submenús <b>Ajustes ▸ Plugins</b> y <b>Efectos ▸ Plugins</b>, que solo se muestran si tienes alguno instalado.</p>
<ul>
<li><b>Instalar un plugin:</b> copia su carpeta dentro de la carpeta <code>plugins</code> de tus datos de usuario y reinicia Imago. En Windows suele estar en <code>%APPDATA%\\Imago\\plugins</code> (o en <code>datos\\plugins</code>, junto al ejecutable, si usas la versión portable).</li>
<li><b>Desactivar uno:</b> borra su carpeta (o muévela fuera de <code>plugins</code>) y reinicia.</li>
<li style="color:#ffcc66;"><b>Seguridad:</b> un plugin es <b>código Python</b> que se ejecuta con tus mismos permisos. Instala solo plugins de <b>fuentes en las que confíes</b>. Imago te avisa la primera vez que carga un plugin de terceros.</li>
</ul>
<p style="color:#9cc6ff;"><b>¿Quieres crear los tuyos?</b> En <b>Ayuda → Crear plugins…</b> tienes una guía técnica paso a paso con un ejemplo completo.</p>

<br><a name="ia"></a>
<h2 style="color:#e0e0e0; font-size:20px;">Inteligencia Artificial</h2>
<p>El menú <b>IA</b> reúne funciones automáticas que resuelven en un clic tareas que a mano llevarían mucho tiempo. Todo se ejecuta <b>en tu ordenador</b>: no se envía ninguna imagen a Internet. La mayoría emplea redes neuronales; unas pocas usan visión por computador clásica.</p>
<p style="color:#9cc6ff;"><b>Descarga de modelos:</b> las funciones neuronales necesitan un archivo de modelo que se descarga <b>una sola vez</b>, la primera vez que las usas (Imago te avisa y pide confirmación). Puedes revisar, descargar o borrar esos modelos en <b>IA → Gestionar modelos de IA...</b>, donde se indica el tamaño y la licencia de cada uno. Las funciones de visión clásica (enderezar horizonte, ojos rojos, perspectiva y panorama) no descargan nada.</p>

<h3 style="color:#e0e0e0; font-size:15px;">Retoque y mejora de la foto</h3>
<ul>
<li><b>Eliminar fondo:</b> Recorta el sujeto principal y deja transparente el resto.</li>
<li><b>Borrar objeto (relleno inteligente):</b> Selecciona algo que sobre (un cable, una persona de fondo...) e Imago rellena el hueco reconstruyendo el fondo de forma coherente (<i>inpainting</i>).</li>
<li><b>Colorizar (blanco y negro):</b> Añade color realista a una foto antigua en escala de grises.</li>
<li><b>Reducir ruido:</b> Limpia el grano de fotos hechas con poca luz o ISO alto.</li>
<li><b>Restaurar caras:</b> Detecta las caras y las reconstruye con más nitidez y detalle (ideal para fotos antiguas o pequeñas).</li>
<li><b>Aumentar resolución ×2 / ×4:</b> Agranda la imagen recreando detalle en lugar de emborronarla (super-resolución).</li>
<li><b>Extraer texto (OCR):</b> Lee el texto de la imagen (carteles, documentos escaneados...) y lo copia al <b>portapapeles</b>. Reconoce el alfabeto latino (español incluido).</li>
</ul>

<h3 style="color:#e0e0e0; font-size:15px;">Efectos creativos</h3>
<ul>
<li><b>Bokeh por profundidad:</b> Estima qué está cerca y qué lejos para desenfocar el fondo como haría un objetivo luminoso, con la intensidad que elijas.</li>
<li><b>Efecto 3D (anaglifo):</b> Genera la clásica imagen para gafas rojo/cian a partir de la profundidad de la escena.</li>
</ul>

<h3 style="color:#e0e0e0; font-size:15px;">Visión clásica (sin descargas)</h3>
<ul>
<li><b>Enderezar horizonte:</b> Detecta la inclinación y nivela la foto automáticamente.</li>
<li><b>Eliminar ojos rojos:</b> Corrige el reflejo rojo del flash en los ojos.</li>
<li><b>Corregir perspectiva:</b> Endereza planos inclinados (edificios, documentos...).</li>
<li><b>Crear panorama:</b> Une varias fotos que se solapan en una única imagen panorámica.</li>
</ul>

<h3 style="color:#e0e0e0; font-size:15px;">Sujeto y fondo</h3>
<p>Este grupo parte de detectar el sujeto de la imagen para trabajar con él o con su fondo:</p>
<ul>
<li><b>Seleccionar sujeto:</b> Crea una selección automática del elemento principal (luego puedes refinarla o usarla con cualquier herramienta).</li>
<li><b>Seleccionar objeto:</b> Selecciona por tipo (persona, coche, animal...).</li>
<li><b>Desenfocar fondo:</b> Mantiene nítido el sujeto y difumina todo lo demás.</li>
<li><b>Realce de color (fondo gris):</b> Deja el sujeto a color y pasa el fondo a blanco y negro.</li>
<li><b>Reemplazar fondo por color / por imagen:</b> Sustituye el fondo por un color liso o por otra fotografía.</li>
</ul>

<br><a name="guias"></a>
<h2 style="color:#e0e0e0; font-size:20px;">Guías y cuadrícula</h2>
<ul>
<li><b>Reglas y cuadrícula:</b> Actívalas desde el menú Ver para medir y alinear elementos con precisión. Con la cuadrícula activada, al acercarte al <b>800% o más</b> aparece la <b>rejilla de píxeles</b> (una celda por píxel), pensada para pixel-art: fina, sin falsear los colores.</li>
<li><b>Mosaico de la cuadrícula:</b> <b>Ver ▸ Mosaico de la cuadrícula</b> añade una línea maestra cada <b>8, 16, 32 o 64 píxeles</b>, visible ya desde el 100%: perfecta para ver la estructura de un <i>sprite sheet</i> o un <i>tileset</i> de un vistazo.</li>
<li><b>Guías magnéticas:</b> Pulsa el botón "Guías" (o <code>Ctrl+;</code>). Después pincha en las reglas (arriba o a la izquierda) y <b>arrastra hacia el lienzo</b> para sacar una guía; tus selecciones, formas y recortes se "pegarán" a ella automáticamente. Para borrar una guía, arrástrala de vuelta fuera del lienzo.</li>
<li><b>Medición (Q):</b> Arrastra entre dos puntos para medir: la <b>distancia, el ángulo y ΔX/ΔY</b> aparecen en la barra de opciones (en píxeles, centímetros o pulgadas). Los extremos se pueden reajustar arrastrándolos; <b>Esc</b> borra la medición. No pinta nada.</li>
</ul>

<br><a name="historial"></a>
<h2 style="color:#e0e0e0; font-size:20px;">Historial y autoguardado</h2>
<ul>
<li><b>Deshacer casi ilimitado:</b> Casi cualquier acción (pintar, mover, crear guías, reordenar capas...) se puede deshacer (<code>Ctrl+Z</code>) y rehacer (<code>Ctrl+Y</code>). El panel de Historial muestra la lista de acciones recientes: haz clic en cualquier paso para volver a ese punto.</li>
<li><b>Recuperación automática:</b> Si se corta la luz o el programa se cierra de forma inesperada, no perderás tu trabajo. Al volver a abrir Imago, detectará los lienzos sin guardar y te ofrecerá recuperarlos intactos, con todas sus capas.</li>
</ul>
<br>
"""

_MANUAL_HTML_EN = """
<a name="intro"></a>
<h2 style="color:#e0e0e0; font-size:20px;">Welcome to Imago</h2>
<p>Imago is a desktop image editor that combines the <b>power</b> of professional tools with the <b>simplicity</b> of classic editors. Inspired by programs like Paint.NET, it aims to be light and responsive without giving up the features you need.</p>
<p>With Imago you can do everything from quick crops and colour corrections to complex photo montages, thanks to its engine for <b>layers</b>, <b>non-destructive masks</b>, <b>effects with live preview</b> and a full set of <b>Artificial Intelligence</b> features that run on your own computer.</p>
<p><b>Imago is available in Spanish, English and French.</b> You can change the language in Edit → Preferences (the change takes effect after restarting).</p>
<p style="color:#9cc6ff;"><b>Tip:</b> this manual has an index on the left. Click any section to jump to it.</p>

<br><a name="interfaz"></a>
<h2 style="color:#e0e0e0; font-size:20px;">Interface and workspace</h2>
<ul>
<li><b>Menu bar:</b> At the top. Gathers every action organised into menus (File, Edit, Image, Layers, Adjustments, Effects, AI, View and Help).</li>
<li><b>Dynamic options bar:</b> Right below the menus. Its contents <b>change with the active tool</b>, showing only what that tool needs (brush size and hardness, bucket tolerance, a shape's style, the text font...).</li>
<li><b>The canvas:</b> The heart of Imago. Zoom with <code>Ctrl+Wheel</code>, scroll with the wheel (or by holding <b>Space</b> and dragging), and rely on the <b>rulers</b> (in pixels or centimetres).</li>
<li><b>Side panels:</b> Tools (on the left) and Histogram, History, Layers and Colour (on the right). They are <b>docked</b> in the window, not floating: you can resize them by dragging the dividers between them, and hide or show them with the buttons in the top-right corner to gain space. The <b>right-column</b> panels can be <b>reordered</b> with the ▲/▼ buttons in their headers, and the <b>Tools</b> panel lets you <b>rearrange its buttons</b> by dragging them wherever you like; right-clicking the panel offers <b>Restore default order</b> to return them to their original position with a single click.</li>
<li><b>Live histogram:</b> The <b>Histogram</b> panel shows the tonal distribution of the image and <b>updates by itself</b> as you edit. Pick the channel in its dropdown (<b>Luminosity</b>, overlaid <b>RGB</b>, or Red/Green/Blue separately) and <b>read it with the mouse</b>: hovering marks the level under the cursor ("Level 128 · 2.4 %") and <b>dragging</b> measures a whole range ("Range 60–190 · 78 %"); a plain click clears the range. Show/hide it with its button in the top-right corner.</li>
<li><b>Status bar:</b> At the bottom. Shows the zoom level and the cursor position over the image.</li>
<li><b>Fullscreen view:</b> Press <code>F11</code> (or <b>View ▸ View fullscreen</b>) to show just the image, filling the screen, to review it. Inside you can zoom (wheel or <code>+</code>/<code>-</code>), pan by dragging, fit it with <code>0</code>/<code>F</code> or see it at actual size with <code>1</code>; exit with <code>Esc</code>.</li>
<li><b>Light or dark theme:</b> In <b>Preferences ▸ Theme</b> you can choose the dark look (default) or the light one; the change applies after restarting.</li>
</ul>

<br><a name="archivos"></a>
<h2 style="color:#e0e0e0; font-size:20px;">File management</h2>
<p>Imago supports the most common standard formats (PNG, JPEG, WebP, BMP, GIF, SVG, TGA, ICO and the modern <b>AVIF, HEIC and JPEG XL</b>, among others) in addition to its own native format, and it also opens <b>Photoshop</b> documents (PSD and PSB) keeping their layers.</p>
<ul>
<li><b>New (<code>Ctrl+N</code>):</b> Creates an empty canvas. You can set the size in <b>pixels</b> (for screen) or in <b>centimetres/inches</b> with a resolution (DPI) for printing. You also choose the initial <b>background colour</b>: white, black, transparent or the palette colour.</li>
<li><b>Drag and drop:</b> Drop an image from your file explorer onto the Imago window to open it as a new document.</li>
<li><b>The .imago format:</b> If you work with several layers, masks or guides, <b>save (<code>Ctrl+S</code>)</b> in the native <b>.imago</b> format. It preserves the whole project structure so you can keep editing later.</li>
<li><b>Export (Save as...):</b> With <code>Ctrl+Shift+S</code> you save the final result as PNG, JPEG (with a quality setting) or WebP. When exporting, Imago automatically merges all layers.</li>
<li><b>Import SVG:</b> When opening a vector <b>.svg</b> file, Imago asks at what size to rasterize it (with the aspect ratio linked) and opens it as a canvas with a transparent background.</li>
<li><b>Export PDF:</b> <b>File ▸ Export ▸ PDF</b> creates a PDF whose page measures exactly what the image does (based on its DPI). It differs from <b>Print ▸ Save as PDF</b>, which centres the image on a sheet of paper.</li>
<li><b>Export OpenRaster (.ora):</b> <b>File ▸ Export ▸ OpenRaster</b> saves the layers in the interchange format that <b>GIMP and Krita</b> open, keeping their opacity, visibility and blend mode. To keep absolutely everything (editable text, separate masks...), the native format is still .imago.</li>
<li><b>GIF/WebP animations:</b> When opening an <b>animated</b> GIF or WebP, Imago offers to turn its frames into <b>layers</b> (each one remembers its original duration). With <b>View ▸ Preview animation</b> you play it without leaving the program (play/pause, frame by frame, adjustable duration) and with <b>File ▸ Export ▸ GIF/WebP animation</b> you create an animated GIF or WebP from the visible layers, with per-frame duration and optional looping.</li>
<li><b>Image properties:</b> <b>Image ▸ Image properties</b> shows the dimensions, resolution, print size, layer count and the photo's <b>EXIF metadata</b> (camera, date, exposure and GPS coordinates with a button to view the spot on a map), plus a luminosity histogram.</li>
<li><b>Batch processing:</b> <b>File ▸ Batch processing...</b> applies one recipe to <b>a whole folder</b> of images: <b>resize</b> (by percentage or fitting a maximum), <b>convert format</b> (with quality for JPEG/WebP), <b>rename in sequence</b> (Background_001, Background_002...) and <b>watermark</b> (text or PNG image, with position, size and opacity). The output goes to another folder and <b>never overwrites</b> anything (existing names get numbered); if you pick no transformation at all, files are <b>copied byte-for-byte</b> (perfect for renaming only). JPEG→JPEG keeps the EXIF metadata. No open document needed.</li>
<li><b>8-bit PNG (palette):</b> When saving a PNG, the quality dialog offers <b>"8-bit palette"</b> with the <b>number of colors</b> (256 down to 16) and optional <b>dithering</b> for photos: much smaller files. For pixel-art with few colors the resulting palette is <b>exact</b>, transparency included, and the dialog's estimated size is the real one.</li>
</ul>

<br><a name="capas"></a>
<h2 style="color:#e0e0e0; font-size:20px;">Layers and masks</h2>
<p>The Layers panel (on the right) lets you build complex images by working part by part without affecting the rest. Transparent areas are shown with a grey checkerboard.</p>
<ul>
<li><b>Reorder:</b> Drag layers in the list to reorder them. The top one covers those below.</li>
<li><b>Layer groups:</b> The <b>folder</b> button (or <b>Layers ▸ Group selected layers</b>, <code>Ctrl+G</code>) groups the selected layers into a folder (they can be <b>nested</b>). Its header has the <b>arrow</b> to collapse/expand it, the name (<b>click</b> = select the whole group, so you can move, duplicate or delete it with the usual buttons) and the <b>eye</b>, which hides or shows the whole group without touching each layer's own checkbox. <b>Right-click</b> the header to <b>rename</b>, <b>ungroup</b>, <b>duplicate</b>, <b>move up/down</b> the whole group or <b>delete</b> it. Drag layers to <b>move them in or out</b> of a folder (dropping them right under its header puts them at its top). Groups are saved in the <b>.imago</b> project.</li>
<li><b>Blend modes:</b> The <b>Mode</b> dropdown at the top of the panel instantly changes how the active layer mixes with the ones below: 13 modes (Multiply, Screen, Overlay, Soft Light, Difference...). When a layer uses a mode other than Normal or an opacity below 100%, it is shown under its name in the list.</li>
<li><b>Layer properties:</b> <b>Double-click</b> a layer (or use its ⚙ button, or <code>Ctrl+Shift+P</code>) to edit its name, opacity, mode and locks, with live preview.</li>
<li><b>Layer locks:</b> In Layer properties you can lock the <b>transparency</b> (painting never alters the alpha), the <b>pixels</b> (the layer can't be painted, adjusted or erased) or the <b>position</b> (the Move tool won't drag it). Locked layers show a <b>padlock</b> in the panel, and the status bar reminds you if you try to edit them.</li>
<li><b>Clipping mask:</b> <b>Layers ▸ Clipping mask</b> (<code>Ctrl+Alt+G</code>) makes the active layer visible <b>only where the layer below has pixels</b>: for instance, a gradient or a photo "inside" a text or a shape, without touching either. Several consecutive clipped layers share the same base, and a clipped layer is marked with <b>↳</b> before its name. It's non-destructive, undoable and saved in the .imago project.</li>
<li><b>Layer masks:</b> Right-click a layer and add a mask. Painting in <b>black</b> hides parts of the layer and painting in <b>white</b> reveals them again: it is <b>100% non-destructive</b> editing. Click the mask thumbnail (next to the layer) to edit it, and the main thumbnail to go back to painting the image.</li>
<li><b>Layer effects (non-destructive):</b> The <b>fx</b> button (top of the panel, next to <b>Mode</b>) adds effects to the active layer that recompute automatically from its content, without touching the pixels: <b>Drop shadow</b>, <b>Inner shadow</b>, <b>Outer glow</b>, <b>Stroke</b>, <b>Bevel &amp; emboss</b>, <b>Satin</b>, <b>Color overlay</b> and <b>Gradient overlay</b>. Each effect is set up in a <b>live-preview panel</b> and appears as a row under its layer, where you can <b>toggle</b> it (checkbox), <b>edit</b> it (click its name) or <b>remove</b> it (×). They also work on <b>text layers without rasterizing them</b>: edit the text and the shadow or stroke adapt instantly. They are saved with the <b>.imago</b> project and are undoable.</li>
</ul>

<br><a name="dibujo"></a>
<h2 style="color:#e0e0e0; font-size:20px;">Drawing tools</h2>
<p>The left mouse button paints with the <b>primary</b> colour and the right button with the <b>secondary</b> one.</p>
<ul>
<li><b>Brush:</b> Soft-edged stroke with adjustable Size, Hardness and <b>stroke Opacity</b> (independent of the colour's alpha and uniform even where the stroke overlaps itself). It can paint with a solid colour or with patterns (bricks, zig-zag, checkerboard...). With <b>Shift</b>, a click draws a <b>straight line</b> from the end of the previous stroke.</li>
<li><b>Pencil:</b> Hard-edged stroke (<i>no anti-aliasing</i>), ideal for pixel art or crisp cut-outs. It also draws <b>straight lines with Shift</b>.</li>
<li><b>Airbrush:</b> Sprays paint continuously while you hold the button down, with a build-up spray effect.</li>
<li><b>Temporary eyedropper:</b> In the brush, pencil and airbrush, <b>Alt+click</b> picks a colour from the canvas without switching tools (left = primary, right = secondary).</li>
<li><b>Eraser:</b> Like the brush, but leaves the layer transparent. It includes advanced modes such as <b>Erase backgrounds</b>, which protects edges based on the colour of the first sample you touch. If the layer's <b>transparency is locked</b>, the eraser does nothing and the status bar tells you why.</li>
<li><b>Clone stamp:</b> Hold <b>Ctrl</b> and click to set the origin; then paint elsewhere to copy those pixels (it respects the brush's opacity and hardness).</li>
<li><b>Replace colour:</b> Paints only over pixels similar to the colour you click on, replacing them with the active colour.</li>
<li><b>Dodge / Burn:</b> Lightens or darkens the painted area, acting on the shadows, midtones or highlights depending on the chosen <b>Range</b>; <b>Exposure</b> controls the strength. Hold <b>Ctrl</b> when starting the stroke to invert the mode without going to the bar.</li>
<li><b>Healing brush:</b> Paint over a blemish (a spot, a wire, a freckle...) and, on release, Imago removes it by rebuilding it from its surroundings.</li>
<li><b>Sponge:</b> Raises or lowers the <b>saturation</b> of the painted area: <b>Desaturate</b> fades the color towards gray (keeping the brightness) and <b>Saturate</b> livens it up. Hold <b>Ctrl</b> when starting the stroke to invert the mode; <b>Flow</b> sets the intensity and the effect doesn't build up when going over the same spot within one stroke.</li>
<li><b>Liquify:</b> <b>Pushes pixels</b> along the stroke, warping the image like wet paint: slim a silhouette, curve a smile, stretch an edge... <b>Strength</b> controls how closely pixels follow the cursor and <b>Hardness</b> the falloff towards the brush edge.</li>
</ul>

<br><a name="formas"></a>
<h2 style="color:#e0e0e0; font-size:20px;">Shapes, paths and text</h2>
<ul>
<li><b>Shapes:</b> Rectangles, ellipses, arrows, stars... When you draw a shape it stays "alive" (floating). While it is, you can <b>change its colour, thickness, line style and even the type of shape in real time</b>. Press <b>Enter</b> to commit it to the canvas.</li>
<li><b>Pen:</b> Creates precise paths from nodes. Click to add nodes and form polygons or continuous lines. Press <b>Esc</b> to finish.</li>
<li><b>Line / Curve:</b> Drag to draw a straight line (hold <b>Shift</b> for 15° angles). On release, <b>4 nodes</b> appear: drag them to bend it as a spline, a Bézier or straight segments (pick the mode in the options bar). The <b>handle next to the line</b> moves it as a whole, dragging with the <b>right button</b> rotates it (Shift = 15° steps), and <b>Start</b>/<b>End</b> add an <b>arrow, circle or bar</b> tip to each end (mixable), with its own <b>Size</b> or "Auto" (the line width). <b>Enter</b> commits it and <b>Esc</b> cancels.</li>
<li><b>Text:</b> Click on the canvas and type; the text is editable and you set the font, size and style in the top bar. Clicking on <b>any existing text</b> reopens it for editing (even if its layer is not the active one). Text layers remain editable after cropping, resizing, changing the canvas size, flipping or rotating the image. If you switch to the <b>Move</b> tool while the text is open, it becomes a floating object you can scale and rotate freely. When you <b>paste</b> text from the clipboard (e.g. the one extracted with AI ▸ Extract text), the box gets a <b>handle</b> on its right edge: drag it to set the width and the text rewraps to fit inside.</li>
</ul>

<br><a name="seleccion"></a>
<h2 style="color:#e0e0e0; font-size:20px;">Selection and transformation</h2>
<p>Selections limit the area where tools take effect (painting, erasing, copying, applying an adjustment...).</p>
<ul>
<li><b>Basic selections:</b> Rectangular marquee, elliptical marquee and lasso (freehand). While dragging, the status bar shows the <b>live size</b>, and holding <b>Space</b> lets you <b>reposition</b> the box without releasing. In the options bar you can set a <b>Fixed ratio</b> (1:1, 4:3, 16:9…) or a <b>Fixed size</b> in pixels (with fixed size a single click is enough).</li>
<li><b>Polygonal lasso:</b> The lasso has a <b>Polygonal</b> mode in its options bar: each click adds a vertex, <b>double-click or Enter</b> closes the polygon and <b>Esc</b> cancels it.</li>
<li><b>Magic wand:</b> Selects areas of the same colour (contiguous or across the whole image) based on an adjustable <b>Tolerance</b>. <b>Right-click subtracts</b> from the selection.</li>
<li><b>Selection brush:</b> Enable the <b>"Selection brush"</b> checkbox in the Brush options bar to "paint" the area to select freehand. The left button <b>adds</b> to the selection and the right button <b>subtracts</b> from it.</li>
<li><b>Move tool:</b> The most versatile one. If something is selected, it cuts it out and turns it into a "floating object" with a handle box to <b>move</b>, <b>scale</b> and <b>rotate</b> (by moving the mouse just outside the corner handles). When scaling, the side opposite the handle stays <b>anchored</b> (hold <b>Alt</b> to scale from the centre) and dragging across the anchor <b>flips</b> the image; during the gesture the status bar shows the size, angle or offset. The <b>arrow keys</b> nudge the object pixel by pixel (Shift = ×10), also in the <b>Move marquee</b> mode.</li>
<li><b>Crop (C):</b> Adjustable box with rule-of-thirds overlay and darkened outside. Its bar offers a fixed <b>Ratio</b> (Free, 1:1, 4:3, 16:9…); <b>Enter</b> applies and <b>Esc</b> cancels. <b>Guides</b> move along with the crop (those left outside are discarded).</li>
<li><b>Refine selection:</b> From the Edit menu (or the options bar) you can <b>Expand</b>, <b>Contract</b>, <b>Smooth</b> or <b>Feather</b> the selection edges, turn it into a ring with <b>Border</b>, or extend it by colour with <b>Grow</b> (similar contiguous areas) and <b>Select similar</b> (whole image), using the wand's tolerance.</li>
</ul>

<br><a name="colores"></a>
<h2 style="color:#e0e0e0; font-size:20px;">Colours and gradients</h2>
<ul>
<li><b>Primary and secondary:</b> The left click uses the primary colour and the right click the secondary one. The <b>X</b> key swaps them instantly.</li>
<li><b>Colours panel:</b> Pick the colour with the RGB wheel/values, by hexadecimal code or from the preset swatches.</li>
<li><b>Custom swatches:</b> Below the fixed palette you can save your own colours: the <b>+</b> button adds the current primary colour and the <b>…</b> button imports a <b>GIMP palette (.gpl)</b>. Click a swatch to use it; right-click to use it as secondary or delete it. They persist between sessions.</li>
<li><b>Eyedropper:</b> Click on the canvas to pick up a colour from the image (left = primary, right = secondary).</li>
<li><b>Paint bucket:</b> Fills an area with a solid colour or a <b>geometric pattern</b> based on a tolerance. <b>Expand</b> widens the fill a few pixels under the outline: perfect for coloring drawings without leaving a light halo next to the lines.</li>
<li><b>Gradient:</b> Creates smooth transitions. Click and drag on the canvas to set the direction and length of the gradient.</li>
</ul>

<br><a name="ajustes"></a>
<h2 style="color:#e0e0e0; font-size:20px;">Adjustments and effects</h2>
<p>Every Adjustment and Effect menu opens in an <b>overlay panel with live preview</b>: you see the result on the canvas before applying it (press Accept to confirm or Cancel/Esc to discard).</p>
<ul>
<li><b>Colour corrections:</b> Curves, Levels, Hue/Saturation and Colour Balance to retouch photos.</li>
<li><b>Automatic adjustments:</b> Under <b>Adjustments ▸ Automatic</b> you get one-click fixes: <b>Auto levels</b> (adjusts each channel's black and white point), <b>Auto-contrast</b> (recovers contrast without shifting colours), <b>Auto color</b> (neutralizes colour casts) and <b>Equalize histogram</b>.</li>
<li><b>Gradient map:</b> Colours the image by mapping its lightness to a 3-colour gradient (Shadows, Midtones, Highlights). Ideal for <i>colour grading</i>.</li>
<li><b>Duotone / tritone:</b> Under <b>Adjustments ▸ Black and white</b>, renders the image with two or three <b>inks</b> based on its luminosity, like a press tone.</li>
<li><b>Distortion and style:</b> Among many other effects: <b>Polar coordinates</b> (wraps the image around the centre, or unrolls it) and <b>Frosted glass</b> under Effects ▸ Distort, and <b>Crystallize</b> (irregular flat-colour tiles) under Effects ▸ Stylize.</li>
<li><b>Layer styles:</b> Drop shadow, Glows, Bevel and emboss, and Stroke. They are applied over the <b>transparent edges</b> of the layer. Try writing text and giving it a shadow and a bevel to see its potential.</li>
</ul>

<br><a name="plugins"></a>
<h2 style="color:#e0e0e0; font-size:20px;">Plugins (extensions)</h2>
<p>Imago supports <b>third-party plugins</b> that add new <b>Adjustments</b> and <b>Effects</b>, with the same live preview as the built-in ones. They appear in the <b>Adjustments ▸ Plugins</b> and <b>Effects ▸ Plugins</b> submenus, shown only when you have at least one installed.</p>
<ul>
<li><b>Install a plugin:</b> copy its folder into the <code>plugins</code> folder of your user data and restart Imago. On Windows it is usually at <code>%APPDATA%\\Imago\\plugins</code> (or <code>datos\\plugins</code>, next to the executable, if you use the portable version).</li>
<li><b>Disable one:</b> delete its folder (or move it out of <code>plugins</code>) and restart.</li>
<li style="color:#ffcc66;"><b>Security:</b> a plugin is <b>Python code</b> that runs with your own permissions. Only install plugins from <b>sources you trust</b>. Imago warns you the first time it loads a third-party plugin.</li>
</ul>
<p style="color:#9cc6ff;"><b>Want to create your own?</b> Under <b>Help → Create plugins…</b> you'll find a step-by-step technical guide with a full example.</p>

<br><a name="ia"></a>
<h2 style="color:#e0e0e0; font-size:20px;">Artificial Intelligence</h2>
<p>The <b>AI</b> menu gathers automatic features that solve, in a single click, tasks that would take a long time by hand. Everything runs <b>on your computer</b>: no image is sent to the Internet. Most use neural networks; a few use classic computer vision.</p>
<p style="color:#9cc6ff;"><b>Model downloads:</b> the neural features need a model file that is downloaded <b>only once</b>, the first time you use them (Imago warns you and asks for confirmation). You can review, download or delete these models in <b>AI → Manage AI models...</b>, where each one's size and licence is shown. The classic vision features (straighten horizon, red eyes, perspective and panorama) download nothing.</p>

<h3 style="color:#e0e0e0; font-size:15px;">Photo retouching and enhancement</h3>
<ul>
<li><b>Remove background:</b> Cuts out the main subject and leaves the rest transparent.</li>
<li><b>Erase object (smart fill):</b> Select something you want gone (a cable, a person in the background...) and Imago fills the gap by reconstructing the background coherently (<i>inpainting</i>).</li>
<li><b>Colourize (black and white):</b> Adds realistic colour to an old greyscale photo.</li>
<li><b>Reduce noise:</b> Cleans up the grain in photos shot in low light or at high ISO.</li>
<li><b>Restore faces:</b> Detects faces and reconstructs them with more sharpness and detail (great for old or small photos).</li>
<li><b>Upscale ×2 / ×4:</b> Enlarges the image by recreating detail instead of blurring it (super-resolution).</li>
<li><b>Extract text (OCR):</b> Reads the text in the image (signs, scanned documents...) and copies it to the <b>clipboard</b>. Recognizes the latin alphabet (Spanish included).</li>
</ul>

<h3 style="color:#e0e0e0; font-size:15px;">Creative effects</h3>
<ul>
<li><b>Depth bokeh:</b> Estimates what is near and what is far to blur the background like a fast lens would, with the intensity you choose.</li>
<li><b>3D effect (anaglyph):</b> Generates the classic red/cyan glasses image from the depth of the scene.</li>
</ul>

<h3 style="color:#e0e0e0; font-size:15px;">Classic vision (no downloads)</h3>
<ul>
<li><b>Straighten horizon:</b> Detects the tilt and levels the photo automatically.</li>
<li><b>Remove red eyes:</b> Fixes the red flash reflection in the eyes.</li>
<li><b>Fix perspective:</b> Straightens tilted planes (buildings, documents...).</li>
<li><b>Create panorama:</b> Stitches several overlapping photos into a single panoramic image.</li>
</ul>

<h3 style="color:#e0e0e0; font-size:15px;">Subject and background</h3>
<p>This group starts by detecting the subject of the image to work with it or with its background:</p>
<ul>
<li><b>Select subject:</b> Creates an automatic selection of the main element (you can then refine it or use it with any tool).</li>
<li><b>Select object:</b> Selects by type (person, car, animal...).</li>
<li><b>Blur background:</b> Keeps the subject sharp and blurs everything else.</li>
<li><b>Colour pop (grey background):</b> Keeps the subject in colour and turns the background black and white.</li>
<li><b>Replace background with colour / with image:</b> Swaps the background for a flat colour or another photo.</li>
</ul>

<br><a name="guias"></a>
<h2 style="color:#e0e0e0; font-size:20px;">Guides and grid</h2>
<ul>
<li><b>Rulers and grid:</b> Enable them from the View menu to measure and align elements precisely. With the grid on, zooming to <b>800% or more</b> reveals the <b>pixel grid</b> (one cell per pixel), designed for pixel-art: thin, without distorting the colors.</li>
<li><b>Grid tile size:</b> <b>View ▸ Grid tile size</b> adds a stronger master line every <b>8, 16, 32 or 64 pixels</b>, visible from 100%: perfect for seeing the structure of a sprite sheet or a tileset at a glance.</li>
<li><b>Magnetic guides:</b> Click the "Guides" button (or <code>Ctrl+;</code>). Then click on the rulers (top or left) and <b>drag towards the canvas</b> to pull out a guide; your selections, shapes and cut-outs will "snap" to it automatically. To delete a guide, drag it back off the canvas.</li>
<li><b>Measure (Q):</b> Drag between two points to measure: the <b>distance, angle and ΔX/ΔY</b> appear in the options bar (in pixels, centimeters or inches). The ends can be readjusted by dragging them; <b>Esc</b> clears the measurement. It paints nothing.</li>
</ul>

<br><a name="historial"></a>
<h2 style="color:#e0e0e0; font-size:20px;">History and autosave</h2>
<ul>
<li><b>Near-unlimited undo:</b> Almost any action (painting, moving, creating guides, reordering layers...) can be undone (<code>Ctrl+Z</code>) and redone (<code>Ctrl+Y</code>). The History panel shows the list of recent actions: click any step to return to that point.</li>
<li><b>Auto-recovery:</b> If the power goes out or the program closes unexpectedly, you won't lose your work. When you reopen Imago, it will detect unsaved canvases and offer to recover them intact, with all their layers.</li>
</ul>
<br>
"""


_MANUAL_HTML_FR = """
<a name="intro"></a>
<h2 style="color:#e0e0e0; font-size:20px;">Bienvenue dans Imago</h2>
<p>Imago est un éditeur d'images de bureau qui allie la <b>puissance</b> des outils professionnels à la <b>simplicité</b> des éditeurs classiques. Inspiré de logiciels comme Paint.NET, il se veut léger et réactif sans renoncer aux fonctions dont vous avez besoin.</p>
<p>Avec Imago, vous pouvez tout faire, du recadrage rapide et des corrections de couleur aux photomontages complexes, grâce à son moteur de <b>calques</b>, ses <b>masques non destructifs</b>, ses <b>effets avec aperçu en direct</b> et un ensemble complet de fonctions d'<b>Intelligence Artificielle</b> qui s'exécutent sur votre propre ordinateur.</p>
<p><b>Imago est disponible en français, espagnol et anglais.</b> Vous pouvez changer de langue dans Édition → Préférences (le changement s'applique au redémarrage).</p>
<p style="color:#9cc6ff;"><b>Astuce :</b> ce manuel comporte un index à gauche. Cliquez sur n'importe quelle section pour y accéder.</p>

<br><a name="interfaz"></a>
<h2 style="color:#e0e0e0; font-size:20px;">Interface et espace de travail</h2>
<ul>
<li><b>Barre de menus :</b> En haut. Elle regroupe toutes les actions organisées par menus (Fichier, Édition, Image, Calques, Réglages, Effets, IA, Affichage et Aide).</li>
<li><b>Barre d'options dynamique :</b> Juste sous les menus. Son contenu <b>change selon l'outil actif</b> : elle n'affiche que ce dont cet outil a besoin (la taille et la dureté du pinceau, la tolérance du pot, le style d'une forme, la police du texte...).</li>
<li><b>Le plan de travail :</b> Le cœur d'Imago. Zoomez avec <code>Ctrl+Molette</code>, déplacez-vous avec la molette (ou en maintenant <b>Espace</b> et en faisant glisser) et appuyez-vous sur les <b>règles</b> (en pixels ou en centimètres).</li>
<li><b>Panneaux latéraux :</b> Outils (à gauche) et Histogramme, Historique, Calques et Couleur (à droite). Ils sont <b>intégrés</b> à la fenêtre, ils ne flottent pas : vous pouvez modifier leur taille en faisant glisser les séparations entre eux, et les masquer ou les afficher avec les boutons du coin supérieur droit pour gagner de la place. Les panneaux de la <b>colonne de droite</b> peuvent être <b>réordonnés</b> avec les boutons ▲/▼ de leur en-tête, et celui des <b>Outils</b> permet de <b>réagencer ses boutons</b> en les faisant glisser à l'endroit souhaité ; d'un clic droit sur le panneau, <b>Restaurer l'ordre par défaut</b> les remet à leur position d'origine en un seul clic.</li>
<li><b>Histogramme en direct :</b> Le panneau <b>Histogramme</b> montre la distribution tonale de l'image et se <b>met à jour tout seul</b> pendant l'édition. Choisissez le canal dans sa liste (<b>Luminosité</b>, <b>RVB</b> superposé, ou Rouge/Vert/Bleu séparément) et <b>lisez-le à la souris</b> : le survol marque le niveau sous le curseur (« Niveau 128 · 2.4 % ») et le <b>glisser</b> mesure une plage entière (« Plage 60–190 · 78 % ») ; un simple clic efface la plage. Affichez/masquez-le avec son bouton du coin supérieur droit.</li>
<li><b>Barre d'état :</b> En bas. Elle indique le niveau de zoom et la position du curseur sur l'image.</li>
<li><b>Affichage plein écran :</b> Avec <code>F11</code> (ou <b>Affichage ▸ Afficher en plein écran</b>), seule l'image s'affiche, occupant tout l'écran, pour la revoir. À l'intérieur, vous pouvez zoomer (molette ou <code>+</code>/<code>-</code>), la déplacer en faisant glisser, l'ajuster avec <code>0</code>/<code>F</code> ou la voir à taille réelle avec <code>1</code> ; quittez avec <code>Échap</code>.</li>
<li><b>Thème clair ou sombre :</b> Dans <b>Préférences ▸ Thème</b>, vous pouvez choisir l'apparence sombre (par défaut) ou claire ; le changement s'applique au redémarrage.</li>
</ul>

<br><a name="archivos"></a>
<h2 style="color:#e0e0e0; font-size:20px;">Gestion des fichiers</h2>
<p>Imago prend en charge les formats standard les plus courants (PNG, JPEG, WebP, BMP, GIF, SVG, TGA, ICO et les formats modernes <b>AVIF, HEIC et JPEG XL</b>, entre autres) en plus de son format natif, et ouvre également les documents <b>Photoshop</b> (PSD et PSB) en conservant leurs calques.</p>
<ul>
<li><b>Nouveau (<code>Ctrl+N</code>) :</b> Crée un plan de travail vide. Vous pouvez définir la taille en <b>pixels</b> (pour l'écran) ou en <b>centimètres/pouces</b> avec une résolution (PPP) pour l'impression. Vous choisissez aussi la <b>couleur de fond</b> initiale : blanc, noir, transparent ou la couleur de la palette.</li>
<li><b>Glisser-déposer :</b> Déposez une image depuis votre explorateur de fichiers sur la fenêtre d'Imago pour l'ouvrir comme un nouveau document.</li>
<li><b>Le format .imago :</b> Si vous travaillez avec plusieurs calques, masques ou repères, <b>enregistrez (<code>Ctrl+S</code>)</b> au format natif <b>.imago</b>. Il conserve toute la structure du projet pour continuer à l'éditer plus tard.</li>
<li><b>Exporter (Enregistrer sous...) :</b> Avec <code>Ctrl+Shift+S</code>, vous enregistrez le résultat final en PNG, JPEG (avec réglage de la qualité) ou WebP. À l'export, Imago fusionne automatiquement tous les calques.</li>
<li><b>Importer un SVG :</b> À l'ouverture d'un fichier vectoriel <b>.svg</b>, Imago demande à quelle taille le rastériser (proportions liées) et l'ouvre comme un plan de travail à fond transparent.</li>
<li><b>Exporter en PDF :</b> <b>Fichier ▸ Exporter ▸ PDF</b> crée un PDF dont la page mesure exactement la taille de l'image (selon ses PPP). C'est différent d'<b>Imprimer ▸ Enregistrer en PDF</b>, qui centre l'image sur une feuille de papier.</li>
<li><b>Exporter en OpenRaster (.ora) :</b> <b>Fichier ▸ Exporter ▸ OpenRaster</b> enregistre les calques dans le format d'échange qu'ouvrent <b>GIMP et Krita</b>, en conservant leur opacité, leur visibilité et leur mode de fusion. Pour tout conserver (texte modifiable, masques séparés...), le format natif reste le .imago.</li>
<li><b>Animations GIF/WebP :</b> À l'ouverture d'un GIF ou WebP <b>animé</b>, Imago propose de convertir ses images en <b>calques</b> (chacun garde sa durée d'origine). Avec <b>Affichage ▸ Prévisualiser l'animation</b>, vous la lisez sans quitter le programme (lecture/pause, image par image, durée réglable) et avec <b>Fichier ▸ Exporter ▸ Animation GIF/WebP</b>, vous créez un GIF ou WebP animé à partir des calques visibles, avec durée par image et boucle en option.</li>
<li><b>Propriétés de l'image :</b> <b>Image ▸ Propriétés de l'image</b> affiche les dimensions, la résolution, la taille d'impression, le nombre de calques et les <b>métadonnées EXIF</b> de la photo (appareil, date, exposition et coordonnées GPS avec un bouton pour voir le lieu sur une carte), ainsi qu'un histogramme de luminosité.</li>
<li><b>Traitement par lots :</b> <b>Fichier ▸ Traitement par lots...</b> applique une même recette à <b>un dossier entier</b> d'images : <b>redimensionner</b> (par pourcentage ou en ajustant à un maximum), <b>convertir le format</b> (avec qualité pour JPEG/WebP), <b>renommer en séquence</b> (Fond_001, Fond_002...) et <b>filigrane</b> (texte ou image PNG, avec position, taille et opacité). Le résultat va dans un autre dossier et <b>n'écrase jamais</b> rien (les noms existants sont numérotés) ; sans aucune transformation, les fichiers sont <b>copiés à l'identique</b> octet par octet (parfait pour renommer seulement). JPEG→JPEG conserve les métadonnées EXIF. Aucun document ouvert n'est nécessaire.</li>
<li><b>PNG 8 bits (palette) :</b> À l'enregistrement d'un PNG, le dialogue de qualité propose <b>« 8 bits palette »</b> avec le <b>nombre de couleurs</b> (256 à 16) et un <b>tramage</b> facultatif pour les photos : des fichiers bien plus petits. Pour le pixel-art à peu de couleurs, la palette obtenue est <b>exacte</b>, transparence comprise, et la taille estimée du dialogue est la vraie.</li>
</ul>

<br><a name="capas"></a>
<h2 style="color:#e0e0e0; font-size:20px;">Calques et masques</h2>
<p>Le panneau Calques (à droite) permet de composer des images complexes en travaillant par parties sans affecter le reste. Les zones transparentes sont affichées avec un damier gris.</p>
<ul>
<li><b>Ordonner :</b> Faites glisser les calques dans la liste pour les réordonner. Celui du haut recouvre ceux du bas.</li>
<li><b>Groupes de calques :</b> Le bouton <b>dossier</b> (ou <b>Calques ▸ Grouper les calques sélectionnés</b>, <code>Ctrl+G</code>) regroupe les calques sélectionnés dans un dossier (ils peuvent être <b>imbriqués</b>). Son en-tête porte la <b>flèche</b> pour le plier/déplier, le nom (<b>clic</b> = sélectionner tout le groupe, pour le déplacer, le dupliquer ou le supprimer avec les boutons habituels) et l'<b>œil</b>, qui masque ou affiche tout le groupe sans toucher à la case de chaque calque. Un <b>clic droit</b> sur l'en-tête permet de <b>renommer</b>, <b>dissocier</b>, <b>dupliquer</b>, <b>monter/descendre</b> le groupe entier ou le <b>supprimer</b>. Faites glisser des calques pour les <b>entrer ou sortir</b> d'un dossier (les déposer juste sous son en-tête les place en haut). Les groupes sont enregistrés dans le projet <b>.imago</b>.</li>
<li><b>Modes de fusion :</b> Le menu déroulant <b>Mode</b>, en haut du panneau, change instantanément la façon dont le calque actif se mélange aux calques inférieurs : 13 modes (Produit, Superposition, Incrustation, Lumière tamisée, Différence...). Quand un calque utilise un mode autre que Normal ou une opacité inférieure à 100 %, cela s'affiche sous son nom dans la liste.</li>
<li><b>Propriétés du calque :</b> <b>Double-cliquez</b> sur un calque (ou son bouton ⚙, ou <code>Ctrl+Shift+P</code>) pour modifier son nom, son opacité, son mode et les verrouillages, avec aperçu en direct.</li>
<li><b>Verrouillages de calque :</b> Dans Propriétés du calque, vous pouvez verrouiller la <b>transparence</b> (on peint sans altérer l'alpha), les <b>pixels</b> (le calque ne peut être ni peint, ni ajusté, ni effacé) ou la <b>position</b> (l'outil Déplacer ne le bouge pas). Les calques verrouillés affichent un <b>cadenas</b> dans le panneau, et la barre d'état vous le rappelle si vous tentez de les modifier.</li>
<li><b>Masque d'écrêtage :</b> <b>Calques ▸ Masque d'écrêtage</b> (<code>Ctrl+Alt+G</code>) fait que le calque actif ne soit visible que <b>là où le calque du dessous a des pixels</b> : par exemple, un dégradé ou une photo « dans » un texte ou une forme, sans toucher ni l'un ni l'autre. Plusieurs calques écrêtés consécutifs partagent la même base, et le calque écrêté est marqué d'un <b>↳</b> devant son nom. Non destructif, annulable et enregistré dans le projet .imago.</li>
<li><b>Masques de calque :</b> Faites un clic droit sur un calque et ajoutez un masque. En peignant en <b>noir</b> vous masquez des parties du calque et en <b>blanc</b> vous les réaffichez : c'est une édition <b>100 % non destructive</b>. Cliquez sur la miniature du masque (à côté du calque) pour le modifier, et sur la miniature principale pour repeindre l'image.</li>
<li><b>Effets de calque (non destructifs) :</b> Le bouton <b>fx</b> (en haut du panneau, à côté de <b>Mode</b>) ajoute au calque actif des effets recalculés automatiquement à partir de son contenu, sans toucher aux pixels : <b>Ombre portée</b>, <b>Ombre interne</b>, <b>Lueur externe</b>, <b>Contour</b>, <b>Biseautage / estampage</b>, <b>Satin</b>, <b>Incrustation couleur</b> et <b>Incrustation dégradé</b>. Chaque effet se règle dans un <b>panneau avec aperçu en direct</b> et apparaît comme une ligne sous son calque, où vous pouvez l'<b>activer/masquer</b> (case), le <b>modifier</b> (clic sur son nom) ou le <b>supprimer</b> (×). Ils fonctionnent aussi sur les <b>calques de texte sans les pixelliser</b> : modifiez le texte et l'ombre ou le contour s'adaptent aussitôt. Ils sont enregistrés avec le projet <b>.imago</b> et annulables.</li>
</ul>

<br><a name="dibujo"></a>
<h2 style="color:#e0e0e0; font-size:20px;">Outils de dessin</h2>
<p>Le bouton gauche de la souris peint avec la couleur <b>primaire</b> et le bouton droit avec la <b>secondaire</b>.</p>
<ul>
<li><b>Pinceau :</b> Tracé aux bords doux avec Taille, Dureté et <b>Opacité du trait</b> ajustables (indépendante de l'alpha de la couleur et uniforme même lorsque le trait se chevauche). Il peut peindre en couleur unie ou avec des motifs (briques, zigzag, damier...). Avec <b>Maj</b>, le clic trace une <b>ligne droite</b> depuis la fin du trait précédent.</li>
<li><b>Crayon :</b> Tracé à bord dur (<i>sans lissage</i>), idéal pour le pixel art ou les découpes nettes. Il trace aussi des <b>lignes droites avec Maj</b>.</li>
<li><b>Aérographe :</b> Diffuse de la peinture en continu tant que vous maintenez le bouton, avec un effet de spray qui s'accumule.</li>
<li><b>Pipette temporaire :</b> Dans le pinceau, le crayon et l'aérographe, <b>Alt+clic</b> capture une couleur du plan de travail sans changer d'outil (gauche = primaire, droit = secondaire).</li>
<li><b>Gomme :</b> Comme le pinceau, mais elle rend le calque transparent. Elle inclut des modes avancés comme <b>Gommer les arrière-plans</b>, qui protège les bords selon la couleur du premier échantillon touché. Si la <b>transparence du calque est verrouillée</b>, la gomme n'agit pas et la barre d'état vous l'indique.</li>
<li><b>Tampon de duplication :</b> Maintenez <b>Ctrl</b> et cliquez pour définir la source ; peignez ensuite ailleurs pour copier ces pixels (il respecte l'opacité et la dureté du pinceau).</li>
<li><b>Remplacer la couleur :</b> Peint uniquement sur les pixels proches de la couleur sur laquelle vous cliquez, en les remplaçant par la couleur active.</li>
<li><b>Densité - / + (éclaircir/obscurcir) :</b> Éclaircit ou obscurcit la zone peinte, en agissant sur les tons foncés, moyens ou clairs selon la <b>Gamme</b> choisie ; l'<b>Exposition</b> règle l'intensité. Maintenez <b>Ctrl</b> au début du tracé pour inverser le mode sans passer par la barre.</li>
<li><b>Correcteur localisé :</b> Peignez sur une imperfection (une tache, un fil, un grain de beauté...) et, au relâchement, Imago l'élimine en la reconstruisant à partir de son entourage.</li>
<li><b>Éponge :</b> Augmente ou diminue la <b>saturation</b> de la zone peinte : <b>Désaturer</b> éteint la couleur vers le gris (en conservant la luminosité) et <b>Saturer</b> l'avive. Maintenez <b>Ctrl</b> au début du trait pour inverser le mode ; le <b>Flux</b> règle l'intensité et l'effet ne s'accumule pas en repassant au même endroit dans un même trait.</li>
<li><b>Fluidité :</b> <b>Pousse les pixels</b> dans la direction du trait, déformant l'image comme de la peinture fraîche : affiner une silhouette, courber un sourire, étirer un bord... La <b>Force</b> contrôle à quel point les pixels suivent le curseur et la <b>Dureté</b>, la décroissance vers le bord du pinceau.</li>
</ul>

<br><a name="formas"></a>
<h2 style="color:#e0e0e0; font-size:20px;">Formes, tracés et texte</h2>
<ul>
<li><b>Formes :</b> Rectangles, ellipses, flèches, étoiles... Lorsque vous dessinez une forme, elle reste « vivante » (flottante). Tant qu'elle l'est, vous pouvez <b>changer en temps réel sa couleur, son épaisseur, son style de ligne et même le type de forme</b>. Appuyez sur <b>Entrée</b> pour la fixer au plan de travail.</li>
<li><b>Plume :</b> Crée des tracés précis par nœuds. Cliquez pour ajouter des nœuds et former des polygones ou des lignes continues. Appuyez sur <b>Échap</b> pour terminer.</li>
<li><b>Ligne / Courbe :</b> Faites glisser pour tracer une ligne droite (avec <b>Maj</b>, par angles de 15°). Au relâchement, <b>4 nœuds</b> apparaissent : déplacez-les pour la courber en spline, en Bézier ou en segments droits (le mode se choisit dans la barre d'options). La <b>poignée à côté de la ligne</b> la déplace en entier, faire glisser avec le <b>bouton droit</b> la fait pivoter (Maj = pas de 15°) et <b>Début</b>/<b>Fin</b> ajoutent à chaque bout une pointe en <b>flèche, cercle ou barre</b> (mélangeables), avec sa propre <b>Taille</b> ou « Auto » (l'épaisseur de la ligne). <b>Entrée</b> la fixe et <b>Échap</b> l'annule.</li>
<li><b>Texte :</b> Cliquez sur le plan de travail et écrivez ; le texte est modifiable et vous réglez la police, la taille et le style dans la barre du haut. Un clic sur <b>n'importe quel texte existant</b> le rouvre pour l'éditer (même si son calque n'est pas actif). Les calques de texte restent modifiables après recadrage, redimensionnement, changement de taille du plan de travail, retournement ou rotation. Si vous passez à l'outil <b>Déplacer</b> avec le texte ouvert, il devient un objet flottant que vous pouvez mettre à l'échelle et faire pivoter librement. En <b>collant</b> du texte du presse-papiers (p. ex. celui extrait avec IA ▸ Extraire le texte), le cadre gagne une <b>poignée</b> sur son bord droit : faites-la glisser pour fixer la largeur et le texte se réajuste à l'intérieur.</li>
</ul>

<br><a name="seleccion"></a>
<h2 style="color:#e0e0e0; font-size:20px;">Sélection et transformation</h2>
<p>Les sélections limitent la zone où les outils agissent (peindre, gommer, copier, appliquer un réglage...).</p>
<ul>
<li><b>Sélections de base :</b> Cadre rectangulaire, elliptique et lasso (à main levée). Pendant le glissement, la barre d'état affiche la <b>taille en direct</b> et maintenir <b>Espace</b> permet de <b>repositionner</b> la boîte sans la lâcher. Dans la barre d'options, vous pouvez fixer des <b>Proportions fixes</b> (1:1, 4:3, 16:9…) ou une <b>Taille fixe</b> en pixels (en taille fixe, un simple clic suffit).</li>
<li><b>Lasso polygonal :</b> Le lasso a un mode <b>Polygonal</b> dans sa barre d'options : chaque clic ajoute un sommet, <b>double-clic ou Entrée</b> ferme le polygone et <b>Échap</b> l'annule.</li>
<li><b>Baguette magique :</b> Sélectionne des zones de même couleur (continues ou dans toute l'image) selon une <b>Tolérance</b> ajustable. Le <b>clic droit soustrait</b> de la sélection.</li>
<li><b>Pinceau de sélection :</b> Cochez la case <b>« Pinceau de sélection »</b> dans la barre d'options du Pinceau pour « peindre » à main levée la zone à sélectionner. Le bouton gauche <b>ajoute</b> et le droit <b>soustrait</b> de la sélection.</li>
<li><b>Outil Déplacer :</b> Le plus polyvalent. S'il y a une sélection, il la découpe et la transforme en « objet flottant » avec une boîte de poignées pour <b>déplacer</b>, <b>mettre à l'échelle</b> et <b>faire pivoter</b> (en approchant la souris à l'extérieur des poignées d'angle). À la mise à l'échelle, le côté opposé à la poignée reste <b>ancré</b> (avec <b>Alt</b>, depuis le centre) et traverser l'ancre <b>retourne</b> l'image en miroir ; pendant le geste, la barre d'état affiche la taille, l'angle ou le décalage. Les <b>flèches</b> déplacent l'objet pixel par pixel (Maj = ×10), aussi en mode <b>Déplacer le liseré</b>.</li>
<li><b>Recadrage (C) :</b> Boîte ajustable avec règle des tiers et extérieur assombri. Sa barre propose des <b>Proportions</b> fixes (Libre, 1:1, 4:3, 16:9…) ; <b>Entrée</b> applique et <b>Échap</b> annule. Les <b>repères</b> se déplacent avec le recadrage (ceux qui restent dehors sont supprimés).</li>
<li><b>Améliorer la sélection :</b> Depuis le menu Édition (ou la barre d'options), vous pouvez <b>Dilater</b>, <b>Contracter</b>, <b>Lisser</b> ou <b>Adoucir</b> les bords de la sélection, la transformer en anneau avec <b>Bordure</b>, ou l'étendre par couleur avec <b>Étendre</b> (zones contiguës semblables) et <b>Sélectionner semblable</b> (toute l'image), avec la tolérance de la baguette.</li>
</ul>

<br><a name="colores"></a>
<h2 style="color:#e0e0e0; font-size:20px;">Couleurs et dégradés</h2>
<ul>
<li><b>Primaire et secondaire :</b> Le clic gauche utilise la couleur primaire et le droit la secondaire. La touche <b>X</b> les échange instantanément.</li>
<li><b>Panneau de couleurs :</b> Choisissez la couleur avec la roue/les valeurs RVB, par code hexadécimal ou depuis les échantillons prédéfinis.</li>
<li><b>Échantillons personnels :</b> Sous la palette fixe, vous pouvez enregistrer vos propres couleurs : le bouton <b>+</b> ajoute la couleur primaire actuelle et le bouton <b>…</b> importe une <b>palette GIMP (.gpl)</b>. Cliquez sur un échantillon pour l'utiliser ; clic droit pour l'utiliser comme secondaire ou le supprimer. Ils sont conservés entre les sessions.</li>
<li><b>Pipette :</b> Cliquez sur le plan de travail pour capturer une couleur de l'image (gauche = primaire, droit = secondaire).</li>
<li><b>Pot de peinture :</b> Remplit une zone d'une couleur unie ou d'un <b>motif géométrique</b> selon une tolérance. L'<b>Expansion</b> élargit le remplissage de quelques pixels sous le contour : parfait pour colorier des dessins sans laisser de halo clair près des lignes.</li>
<li><b>Dégradé :</b> Crée des transitions douces. Cliquez et faites glisser sur le plan de travail pour définir la direction et la longueur du dégradé.</li>
</ul>

<br><a name="ajustes"></a>
<h2 style="color:#e0e0e0; font-size:20px;">Réglages et effets</h2>
<p>Tous les menus Réglages et Effets s'affichent dans un <b>panneau superposé avec aperçu en direct</b> : vous voyez le résultat sur le plan de travail avant de l'appliquer (appuyez sur Valider pour confirmer ou Annuler/Échap pour abandonner).</p>
<ul>
<li><b>Corrections de couleur :</b> Courbes, Niveaux, Teinte/Saturation et Balance des couleurs pour retoucher les photographies.</li>
<li><b>Réglages automatiques :</b> Dans <b>Réglages ▸ Automatique</b>, des corrections en un clic : <b>Niveaux automatiques</b> (ajuste le point noir et blanc de chaque canal), <b>Contraste automatique</b> (récupère du contraste sans altérer les couleurs), <b>Couleur automatique</b> (neutralise les dominantes) et <b>Égaliser l'histogramme</b>.</li>
<li><b>Dégradé de couleurs :</b> Colore l'image en associant sa luminosité à un dégradé de 3 couleurs (Ombres, Tons moyens, Lumières). Idéal pour l'<i>étalonnage</i>.</li>
<li><b>Bichromie / trichromie :</b> Dans <b>Réglages ▸ Noir et blanc</b>, reproduit l'image avec deux ou trois <b>encres</b> selon sa luminosité, comme un virage d'imprimerie.</li>
<li><b>Distorsion et style :</b> Parmi bien d'autres effets : <b>Coordonnées polaires</b> (enroule l'image autour du centre, ou la déroule) et <b>Verre dépoli</b> dans Effets ▸ Déformer, et <b>Cristalliser</b> (pavés irréguliers de couleur unie) dans Effets ▸ Styliser.</li>
<li><b>Styles de calque :</b> Ombre portée, Lueurs, Biseautage et estampage, et Contour. Ils s'appliquent sur les <b>bords transparents</b> du calque. Essayez d'écrire un texte et de lui donner une ombre et un biseau pour voir tout son potentiel.</li>
</ul>

<br><a name="plugins"></a>
<h2 style="color:#e0e0e0; font-size:20px;">Extensions (plugins)</h2>
<p>Imago prend en charge des <b>extensions tierces</b> qui ajoutent de nouveaux <b>Réglages</b> et <b>Effets</b>, avec le même aperçu en direct que ceux intégrés. Elles apparaissent dans les sous-menus <b>Réglages ▸ Extensions</b> et <b>Effets ▸ Extensions</b>, affichés uniquement si au moins une est installée.</p>
<ul>
<li><b>Installer une extension :</b> copiez son dossier dans le dossier <code>plugins</code> de vos données utilisateur et redémarrez Imago. Sous Windows, il se trouve généralement dans <code>%APPDATA%\\Imago\\plugins</code> (ou <code>datos\\plugins</code>, à côté de l'exécutable, si vous utilisez la version portable).</li>
<li><b>En désactiver une :</b> supprimez son dossier (ou déplacez-le hors de <code>plugins</code>) et redémarrez.</li>
<li style="color:#ffcc66;"><b>Sécurité :</b> une extension est du <b>code Python</b> exécuté avec vos propres droits. N'installez que des extensions de <b>sources fiables</b>. Imago vous prévient la première fois qu'il charge une extension tierce.</li>
</ul>
<p style="color:#9cc6ff;"><b>Envie de créer les vôtres ?</b> Dans <b>Aide → Créer des extensions…</b>, vous trouverez un guide technique pas à pas avec un exemple complet.</p>

<br><a name="ia"></a>
<h2 style="color:#e0e0e0; font-size:20px;">Intelligence Artificielle</h2>
<p>Le menu <b>IA</b> regroupe des fonctions automatiques qui résolvent en un clic des tâches qui, à la main, prendraient beaucoup de temps. Tout s'exécute <b>sur votre ordinateur</b> : aucune image n'est envoyée sur Internet. La plupart emploient des réseaux de neurones ; quelques-unes utilisent la vision par ordinateur classique.</p>
<p style="color:#9cc6ff;"><b>Téléchargement des modèles :</b> les fonctions neuronales nécessitent un fichier de modèle qui se télécharge <b>une seule fois</b>, la première fois que vous les utilisez (Imago vous prévient et demande confirmation). Vous pouvez consulter, télécharger ou supprimer ces modèles dans <b>IA → Gérer les modèles d'IA...</b>, où sont indiqués la taille et la licence de chacun. Les fonctions de vision classique (redresser l'horizon, yeux rouges, perspective et panorama) ne téléchargent rien.</p>

<h3 style="color:#e0e0e0; font-size:15px;">Retouche et amélioration de la photo</h3>
<ul>
<li><b>Supprimer l'arrière-plan :</b> Découpe le sujet principal et rend le reste transparent.</li>
<li><b>Effacer un objet (remplissage intelligent) :</b> Sélectionnez un élément superflu (un câble, une personne en fond...) et Imago comble le vide en reconstruisant l'arrière-plan de façon cohérente (<i>inpainting</i>).</li>
<li><b>Coloriser (noir et blanc) :</b> Ajoute une couleur réaliste à une vieille photo en niveaux de gris.</li>
<li><b>Réduire le bruit :</b> Nettoie le grain des photos prises en basse lumière ou à ISO élevé.</li>
<li><b>Restaurer les visages :</b> Détecte les visages et les reconstruit avec plus de netteté et de détail (idéal pour les photos anciennes ou petites).</li>
<li><b>Augmenter la résolution ×2 / ×4 :</b> Agrandit l'image en recréant du détail au lieu de la rendre floue (super-résolution).</li>
<li><b>Extraire le texte (OCR) :</b> Lit le texte de l'image (panneaux, documents numérisés...) et le copie dans le <b>presse-papiers</b>. Reconnaît l'alphabet latin (espagnol inclus).</li>
</ul>

<h3 style="color:#e0e0e0; font-size:15px;">Effets créatifs</h3>
<ul>
<li><b>Bokeh selon la profondeur :</b> Estime ce qui est proche et ce qui est loin pour flouter l'arrière-plan comme le ferait un objectif lumineux, avec l'intensité que vous choisissez.</li>
<li><b>Effet 3D (anaglyphe) :</b> Génère la classique image pour lunettes rouge/cyan à partir de la profondeur de la scène.</li>
</ul>

<h3 style="color:#e0e0e0; font-size:15px;">Vision classique (sans téléchargement)</h3>
<ul>
<li><b>Redresser l'horizon :</b> Détecte l'inclinaison et met la photo à niveau automatiquement.</li>
<li><b>Supprimer les yeux rouges :</b> Corrige le reflet rouge du flash dans les yeux.</li>
<li><b>Corriger la perspective :</b> Redresse les plans inclinés (bâtiments, documents...).</li>
<li><b>Créer un panorama :</b> Assemble plusieurs photos qui se chevauchent en une seule image panoramique.</li>
</ul>

<h3 style="color:#e0e0e0; font-size:15px;">Sujet et arrière-plan</h3>
<p>Ce groupe part de la détection du sujet de l'image pour travailler avec lui ou avec son arrière-plan :</p>
<ul>
<li><b>Sélectionner le sujet :</b> Crée une sélection automatique de l'élément principal (vous pouvez ensuite l'affiner ou l'utiliser avec n'importe quel outil).</li>
<li><b>Sélectionner un objet :</b> Sélectionne par type (personne, voiture, animal...).</li>
<li><b>Flouter l'arrière-plan :</b> Garde le sujet net et floute tout le reste.</li>
<li><b>Rehaussement de couleur (fond gris) :</b> Laisse le sujet en couleur et passe l'arrière-plan en noir et blanc.</li>
<li><b>Remplacer l'arrière-plan par une couleur / par une image :</b> Remplace l'arrière-plan par une couleur unie ou par une autre photographie.</li>
</ul>

<br><a name="guias"></a>
<h2 style="color:#e0e0e0; font-size:20px;">Repères et grille</h2>
<ul>
<li><b>Règles et grille :</b> Activez-les depuis le menu Affichage pour mesurer et aligner les éléments avec précision. Avec la grille active, en zoomant à <b>800 % ou plus</b> apparaît la <b>grille de pixels</b> (une cellule par pixel), pensée pour le pixel-art : fine, sans fausser les couleurs.</li>
<li><b>Mosaïque de la grille :</b> <b>Affichage ▸ Mosaïque de la grille</b> ajoute une ligne maîtresse tous les <b>8, 16, 32 ou 64 pixels</b>, visible dès 100 % : parfaite pour voir d'un coup d'œil la structure d'un sprite sheet ou d'un tileset.</li>
<li><b>Repères magnétiques :</b> Appuyez sur le bouton « Repères » (ou <code>Ctrl+;</code>). Cliquez ensuite sur les règles (en haut ou à gauche) et <b>faites glisser vers le plan de travail</b> pour tirer un repère ; vos sélections, formes et recadrages s'y « colleront » automatiquement. Pour supprimer un repère, faites-le glisser à nouveau hors du plan de travail.</li>
<li><b>Mesure (Q) :</b> Faites glisser entre deux points pour mesurer : la <b>distance, l'angle et ΔX/ΔY</b> s'affichent dans la barre d'options (en pixels, centimètres ou pouces). Les extrémités se réajustent en les déplaçant ; <b>Échap</b> efface la mesure. Ne peint rien.</li>
</ul>

<br><a name="historial"></a>
<h2 style="color:#e0e0e0; font-size:20px;">Historique et enregistrement automatique</h2>
<ul>
<li><b>Annulation quasi illimitée :</b> Presque toute action (peindre, déplacer, créer des repères, réordonner des calques...) peut être annulée (<code>Ctrl+Z</code>) et rétablie (<code>Ctrl+Y</code>). Le panneau Historique affiche la liste des actions récentes : cliquez sur n'importe quelle étape pour revenir à ce point.</li>
<li><b>Récupération automatique :</b> En cas de coupure de courant ou de fermeture inattendue du programme, vous ne perdrez pas votre travail. À la réouverture d'Imago, il détectera les plans de travail non enregistrés et vous proposera de les récupérer intacts, avec tous leurs calques.</li>
</ul>
<br>
"""


class ManualDialog(FramelessDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("manual.title", default="Manual de Imago"))
        self._body.setFixedSize(850, 600)
        self.setStyleSheet(_dark() + theme.dialog_button_plain_qss() + theme.list_qss())

        # El cuerpo principal usará un diseño horizontal para separar índice y contenido
        main_layout = QHBoxLayout()
        self.body_layout.addLayout(main_layout, 1)

        # --- Columna Izquierda: Índice ---
        self.index_list = QListWidget()
        self.index_list.setFixedWidth(220)
        # Quitar los márgenes de los items para ajustarse al estilo list_qss
        self.index_list.setStyleSheet(theme.list_qss() + """
            QListWidget::item { margin: 0px; padding: 6px; }
        """)
        
        from i18n import current_language
        if current_language() == "en":
            self.sections = [
                ("Welcome to Imago", "intro"),
                ("Interface and Workspace", "interfaz"),
                ("File Management", "archivos"),
                ("Layers and Masks", "capas"),
                ("Drawing Tools", "dibujo"),
                ("Shapes, Paths, and Text", "formas"),
                ("Selection and Transformation", "seleccion"),
                ("Colors and Gradients", "colores"),
                ("Adjustments and Effects", "ajustes"),
                ("Plugins", "plugins"),
                ("Artificial Intelligence", "ia"),
                ("Guides and Grid", "guias"),
                ("History and Autosave", "historial")
            ]
        elif current_language() == "fr":
            self.sections = [
                ("Bienvenue dans Imago", "intro"),
                ("Interface et espace de travail", "interfaz"),
                ("Gestion des fichiers", "archivos"),
                ("Calques et masques", "capas"),
                ("Outils de dessin", "dibujo"),
                ("Formes, tracés et texte", "formas"),
                ("Sélection et transformation", "seleccion"),
                ("Couleurs et dégradés", "colores"),
                ("Réglages et effets", "ajustes"),
                ("Extensions", "plugins"),
                ("Intelligence Artificielle", "ia"),
                ("Repères et grille", "guias"),
                ("Historique et enregistrement automatique", "historial")
            ]
        else:
            self.sections = [
                ("Bienvenida a Imago", "intro"),
                ("Interfaz y Área de Trabajo", "interfaz"),
                ("Gestión de Archivos", "archivos"),
                ("Capas y Máscaras", "capas"),
                ("Herramientas de Dibujo", "dibujo"),
                ("Formas, Trazados y Texto", "formas"),
                ("Selección y Transformación", "seleccion"),
                ("Colores y Degradados", "colores"),
                ("Ajustes y Efectos", "ajustes"),
                ("Plugins", "plugins"),
                ("Inteligencia Artificial", "ia"),
                ("Guías y Cuadrícula", "guias"),
                ("Historial y Autoguardado", "historial")
            ]
        
        for title, anchor in self.sections:
            item = QListWidgetItem(title)
            item.setData(Qt.UserRole, anchor)
            self.index_list.addItem(item)
            
        main_layout.addWidget(self.index_list)

        # --- Columna Derecha: Contenido ---
        self.tb = _text_browser()
        from i18n import current_language
        _lang = current_language()
        self.tb.setHtml(_themed_html(_MANUAL_HTML_FR if _lang == "fr"
                        else _MANUAL_HTML_EN if _lang == "en"
                        else _MANUAL_HTML_ES))
        main_layout.addWidget(self.tb, 1)

        # Conectar el índice
        self.index_list.itemClicked.connect(self._on_index_clicked)

        # Seleccionar el primero por defecto
        self.index_list.setCurrentRow(0)

        # --- Botones inferiores ---
        btns = QHBoxLayout()
        btns.addStretch()
        close = QPushButton(t("btn.close", default="Cerrar"))
        close.clicked.connect(self.accept)
        btns.addWidget(close)
        self.body_layout.addLayout(btns)

    def _on_index_clicked(self, item):
        anchor = item.data(Qt.UserRole)
        self.tb.scrollToAnchor(anchor)


# =====================================================================
# Atajos de teclado
# =====================================================================

def _shortcuts_html_en():
    grupos = [
        ("Mouse and navigation", [
            ("Left / Right click", "Paint with primary / secondary color"),
            ("Space (hold)", "Temporary hand: pan view"),
            ("Ctrl + wheel", "Zoom in / out (towards cursor)"),
            ("Wheel", "Scroll vertically"),
            ("Shift + wheel", "Scroll horizontally"),
            ("Alt + click", "Temporary eyedropper (brush, pencil and airbrush)"),
            ("Shift + click", "Brush / Pencil: straight line from the last stroke"),
            ("Esc", "Cancel current operation (gradient, text, pen...)"),
        ]),
        ("Selection and transformation", [
            ("Space (while dragging)", "Reposition the selection being drawn"),
            ("Alt (while scaling)", "Move: scale from the centre (without Alt, the opposite side is anchored)"),
            ("Arrow keys", "Nudge the object or the marquee 1 px (Shift = ×10)"),
            ("Double-click / Enter", "Polygonal lasso: close the polygon"),
            ("Enter / Esc", "Crop: apply / cancel the box"),
        ]),
        ("Tools (single key)", [
            ("M", "Marquee (press again to toggle rectangle ↔ ellipse)"),
            ("L", "Lasso"), ("W", "Magic wand"), ("V", "Move"),
            ("B", "Brush"), ("N", "Pencil"), ("E", "Eraser"),
            ("G", "Paint bucket"), ("D", "Gradient"),
            ("I", "Eyedropper"), ("T", "Text"), ("S", "Clone stamp"),
            ("A", "Airbrush"), ("U", "Smudge"),
            ("R", "Replace color"), ("P", "Pen (paths)"),
            ("F", "Shapes"), ("H", "Hand"),
            ("C", "Crop (adjustable box)"),
            ("O", "Dodge / Burn"),
            ("J", "Healing brush"),
            ("K", "Line / Curve"),
            ("Q", "Measure"),
            ("Y", "Sponge (saturation)"),
            ("Z", "Liquify (push pixels)"),
        ]),
        ("File", [
            ("Ctrl+N", "New"), ("Ctrl+O", "Open"),
            ("Ctrl+S", "Save"), ("Ctrl+Shift+S", "Save as..."),
            ("Ctrl+P", "Print"),
            ("Ctrl+W", "Close tab"), ("Ctrl+Q", "Exit"),
        ]),
        ("Edit", [
            ("Ctrl+Z", "Undo"), ("Ctrl+Y", "Redo"),
            ("Ctrl+X", "Cut"), ("Ctrl+C", "Copy"), ("Ctrl+V", "Paste"),
            ("Ctrl+Shift+V", "Paste as layer"),
            ("Ctrl+A", "Select all"), ("Ctrl+D", "Deselect"),
            ("Ctrl+I", "Invert selection"), ("Del", "Delete selection"),
            ("X", "Swap primary/secondary colors"),
        ]),
        ("View", [
            ("Ctrl++", "Zoom in"), ("Ctrl+-", "Zoom out"),
            ("Ctrl+0", "Fit to window"), ("Ctrl+1", "Actual size"),
            ("F11", "View fullscreen"),
            ("Ctrl+'", "Grid"), ("Ctrl+Shift+R", "Rulers"),
            ("Ctrl+;", "Show / hide guides"),
            ("F8", "Color palette"),
        ]),
        ("Image", [
            ("Ctrl+R", "Resize image"),
            ("Ctrl+Shift+C", "Canvas size"),
        ]),
        ("Layers", [
            ("Ctrl+Shift+N", "New layer"), ("Ctrl+J", "Duplicate layer"),
            ("Ctrl+Shift+Del", "Delete layer"),
            ("Ctrl+G", "Group the selected layers"),
            ("Ctrl+Alt+G", "Clipping mask"),
            ("Ctrl+E", "Merge down"),
            ("Ctrl+Shift+E", "Merge all layers"),
            ("Ctrl+]", "Move layer up"),
            ("Ctrl+[", "Move layer down"),
            ("Ctrl+Shift+P", "Layer properties"),
        ]),
        ("Help", [
            ("F1", "Open the manual"),
        ]),
    ]
    partes = ['<h2 style="color:#e0e0e0;">Keyboard Shortcuts</h2>',
              '<p style="color:#888888;">Keyboard and mouse shortcuts.</p>']
    for titulo, filas in grupos:
        partes.append('<h3 style="color:#e0e0e0;">%s</h3>' % titulo)
        partes.append('<table cellspacing="0" cellpadding="3">')
        for tecla, desc in filas:
            partes.append(
                '<tr>'
                '<td valign="middle" style="color:#9cc6ff; font-family:Consolas,monospace;"><b>%s</b></td>'
                '<td valign="middle" style="color:#e0e0e0; padding-left:18px;">%s</td>'
                '</tr>' % (tecla, desc))
        partes.append('</table>')
    return "".join(partes)


def _shortcuts_html_fr():
    grupos = [
        ("Souris et navigation", [
            ("Clic gauche / droit", "Peindre avec la couleur primaire / secondaire"),
            ("Espace (maintenir)", "Main temporaire : déplacer la vue"),
            ("Ctrl + molette", "Zoom avant / arrière (vers le curseur)"),
            ("Molette", "Défilement vertical"),
            ("Maj + molette", "Défilement horizontal"),
            ("Alt + clic", "Pipette temporaire (pinceau, crayon et aérographe)"),
            ("Maj + clic", "Pinceau / Crayon : ligne droite depuis le dernier trait"),
            ("Échap", "Annuler l'opération en cours (dégradé, texte, plume…)"),
        ]),
        ("Sélection et transformation", [
            ("Espace (en glissant)", "Repositionner la sélection en cours"),
            ("Alt (à l'échelle)", "Déplacer : mise à l'échelle depuis le centre (sans Alt, le côté opposé est ancré)"),
            ("Flèches", "Déplacer l'objet ou le liseré de 1 px (Maj = ×10)"),
            ("Double-clic / Entrée", "Lasso polygonal : fermer le polygone"),
            ("Entrée / Échap", "Recadrage : appliquer / annuler la boîte"),
        ]),
        ("Outils (une touche)", [
            ("M", "Sélection rectangulaire (répéter alterne rectangle ↔ ellipse)"),
            ("L", "Lasso"), ("W", "Baguette magique"), ("V", "Déplacer"),
            ("B", "Pinceau"), ("N", "Crayon"), ("E", "Gomme"),
            ("G", "Pot de peinture"), ("D", "Dégradé"),
            ("I", "Pipette"), ("T", "Texte"), ("S", "Tampon de duplication"),
            ("A", "Aérographe"), ("U", "Doigt (estomper)"),
            ("R", "Remplacer la couleur"), ("P", "Plume (tracés)"),
            ("F", "Formes"), ("H", "Main"),
            ("C", "Recadrage (boîte ajustable)"),
            ("O", "Densité - / + (éclaircir/obscurcir)"),
            ("J", "Correcteur localisé"),
            ("K", "Ligne / Courbe"),
            ("Q", "Mesure"),
            ("Y", "Éponge (saturation)"),
            ("Z", "Fluidité (pousser les pixels)"),
        ]),
        ("Fichier", [
            ("Ctrl+N", "Nouveau"), ("Ctrl+O", "Ouvrir"),
            ("Ctrl+S", "Enregistrer"), ("Ctrl+Shift+S", "Enregistrer sous…"),
            ("Ctrl+P", "Imprimer"),
            ("Ctrl+W", "Fermer l'onglet"), ("Ctrl+Q", "Quitter"),
        ]),
        ("Édition", [
            ("Ctrl+Z", "Annuler"), ("Ctrl+Y", "Rétablir"),
            ("Ctrl+X", "Couper"), ("Ctrl+C", "Copier"), ("Ctrl+V", "Coller"),
            ("Ctrl+Shift+V", "Coller comme calque"),
            ("Ctrl+A", "Tout sélectionner"), ("Ctrl+D", "Désélectionner"),
            ("Ctrl+I", "Inverser la sélection"), ("Suppr", "Supprimer la sélection"),
            ("X", "Échanger les couleurs primaire/secondaire"),
        ]),
        ("Affichage", [
            ("Ctrl++", "Zoom avant"), ("Ctrl+-", "Zoom arrière"),
            ("Ctrl+0", "Ajuster à la fenêtre"), ("Ctrl+1", "Taille réelle"),
            ("F11", "Afficher en plein écran"),
            ("Ctrl+'", "Grille"), ("Ctrl+Shift+R", "Règles"),
            ("Ctrl+;", "Afficher / masquer les repères"),
            ("F8", "Palette de couleurs"),
        ]),
        ("Image", [
            ("Ctrl+R", "Redimensionner l'image"),
            ("Ctrl+Shift+C", "Taille du plan de travail"),
        ]),
        ("Calques", [
            ("Ctrl+Shift+N", "Nouveau calque"), ("Ctrl+J", "Dupliquer le calque"),
            ("Ctrl+Shift+Suppr", "Supprimer le calque"),
            ("Ctrl+G", "Grouper les calques sélectionnés"),
            ("Ctrl+Alt+G", "Masque d'écrêtage"),
            ("Ctrl+E", "Fusionner avec le calque inférieur"),
            ("Ctrl+Shift+E", "Fusionner tous les calques"),
            ("Ctrl+]", "Monter le calque"),
            ("Ctrl+[", "Descendre le calque"),
            ("Ctrl+Shift+P", "Propriétés du calque"),
        ]),
        ("Aide", [
            ("F1", "Ouvrir le manuel"),
        ]),
    ]
    partes = ['<h2 style="color:#e0e0e0;">Raccourcis clavier</h2>',
              '<p style="color:#888888;">Raccourcis clavier et souris.</p>']
    for titulo, filas in grupos:
        partes.append('<h3 style="color:#e0e0e0;">%s</h3>' % titulo)
        partes.append('<table cellspacing="0" cellpadding="3">')
        for tecla, desc in filas:
            partes.append(
                '<tr>'
                '<td valign="middle" style="color:#9cc6ff; font-family:Consolas,monospace;"><b>%s</b></td>'
                '<td valign="middle" style="color:#e0e0e0; padding-left:18px;">%s</td>'
                '</tr>' % (tecla, desc))
        partes.append('</table>')
    return "".join(partes)


def _shortcuts_html():
    from i18n import current_language
    if current_language() == "en": return _shortcuts_html_en()
    if current_language() == "fr": return _shortcuts_html_fr()
    grupos = [
        ("Ratón y navegación", [
            ("Clic izq. / der.", "Pintar con el color primario / secundario"),
            ("Espacio (mantener)", "Mano temporal: desplazar la vista"),
            ("Ctrl + rueda", "Acercar / alejar (hacia el cursor)"),
            ("Rueda", "Desplazar verticalmente"),
            ("Mayús + rueda", "Desplazar horizontalmente"),
            ("Alt + clic", "Cuentagotas temporal (pincel, lápiz y aerógrafo)"),
            ("Mayús + clic", "Pincel / Lápiz: línea recta desde el último trazo"),
            ("Esc", "Cancelar la operación en curso (degradado, texto, pluma…)"),
        ]),
        ("Selección y transformación", [
            ("Espacio (arrastrando)", "Reposicionar la selección en curso"),
            ("Alt (escalando)", "Mover: escalar desde el centro (sin Alt, ancla el lado opuesto)"),
            ("Flechas", "Mover el objeto o la marquesina 1 px (Mayús = ×10)"),
            ("Doble clic / Intro", "Lazo poligonal: cerrar el polígono"),
            ("Intro / Esc", "Recorte: aplicar / cancelar la caja"),
        ]),
        ("Herramientas (una tecla)", [
            ("M", "Marquesina (repetir alterna rectángulo ↔ elipse)"),
            ("L", "Lazo"), ("W", "Varita mágica"), ("V", "Mover"),
            ("B", "Pincel"), ("N", "Lápiz"), ("E", "Goma de borrar"),
            ("G", "Cubo de pintura"), ("D", "Degradado"),
            ("I", "Cuentagotas"), ("T", "Texto"), ("S", "Tampón de clonar"),
            ("A", "Aerógrafo"), ("U", "Dedo (difuminar)"),
            ("R", "Sustituir color"), ("P", "Pluma (trazados)"),
            ("F", "Formas"), ("H", "Mano"),
            ("C", "Recorte (caja ajustable)"),
            ("O", "Sobreexponer / Subexponer"),
            ("J", "Pincel corrector"),
            ("K", "Línea / Curva"),
            ("Q", "Medición"),
            ("Y", "Esponja (saturación)"),
            ("Z", "Licuar (empujar píxeles)"),
        ]),
        ("Archivo", [
            ("Ctrl+N", "Nuevo"), ("Ctrl+O", "Abrir"),
            ("Ctrl+S", "Guardar"), ("Ctrl+Shift+S", "Guardar como…"),
            ("Ctrl+P", "Imprimir"),
            ("Ctrl+W", "Cerrar pestaña"), ("Ctrl+Q", "Salir"),
        ]),
        ("Edición", [
            ("Ctrl+Z", "Deshacer"), ("Ctrl+Y", "Rehacer"),
            ("Ctrl+X", "Cortar"), ("Ctrl+C", "Copiar"), ("Ctrl+V", "Pegar"),
            ("Ctrl+Shift+V", "Pegar como capa"),
            ("Ctrl+A", "Seleccionar todo"), ("Ctrl+D", "Anular selección"),
            ("Ctrl+I", "Invertir selección"), ("Supr", "Borrar la selección"),
            ("X", "Intercambiar colores primario/secundario"),
        ]),
        ("Ver", [
            ("Ctrl++", "Acercar"), ("Ctrl+-", "Alejar"),
            ("Ctrl+0", "Ajustar a la ventana"), ("Ctrl+1", "Tamaño real"),
            ("F11", "Ver a pantalla completa"),
            ("Ctrl+'", "Cuadrícula"), ("Ctrl+Shift+R", "Reglas"),
            ("Ctrl+;", "Mostrar / ocultar guías"),
            ("F8", "Paleta de colores"),
        ]),
        ("Imagen", [
            ("Ctrl+R", "Cambiar tamaño de imagen"),
            ("Ctrl+Shift+C", "Tamaño del lienzo"),
        ]),
        ("Capas", [
            ("Ctrl+Shift+N", "Nueva capa"), ("Ctrl+J", "Duplicar capa"),
            ("Ctrl+Shift+Supr", "Eliminar capa"),
            ("Ctrl+G", "Agrupar las capas seleccionadas"),
            ("Ctrl+Alt+G", "Máscara de recorte"),
            ("Ctrl+E", "Fusionar hacia abajo"),
            ("Ctrl+Shift+E", "Fusionar todas las capas"),
            ("Ctrl+]", "Mover capa hacia arriba"),
            ("Ctrl+[", "Mover capa hacia abajo"),
            ("Ctrl+Shift+P", "Propiedades de la capa"),
        ]),
        ("Ayuda", [
            ("F1", "Abrir el manual"),
        ]),
    ]
    partes = ['<h2 style="color:#e0e0e0;">Atajos de teclado</h2>',
              '<p style="color:#888888;">Atajos de teclado y de ratón.</p>']
    for titulo, filas in grupos:
        partes.append('<h3 style="color:#e0e0e0;">%s</h3>' % titulo)
        partes.append('<table cellspacing="0" cellpadding="3">')
        for tecla, desc in filas:
            partes.append(
                '<tr>'
                '<td valign="middle" style="color:#9cc6ff; font-family:Consolas,monospace;"><b>%s</b></td>'
                '<td valign="middle" style="color:#e0e0e0; padding-left:18px;">%s</td>'
                '</tr>' % (tecla, desc))
        partes.append('</table>')
    return "".join(partes)


# =====================================================================
# Guía para crear plugins (Ayuda → Crear plugins...)
# =====================================================================

def _plugin_guide_html():
    """Guía técnica para desarrolladores de plugins (ES/EN/FR). Los bloques de
    código son idénticos en los tres idiomas (solo se traduce la prosa) y van
    ESCAPADOS con html.escape porque contienen '<' ('<=') que rompería el HTML."""
    import html
    from i18n import current_language
    lang = current_language()
    PRE = ('style="background-color:#202020; color:#e0e0e0; padding:8px;'
           ' border:1px solid #555555; border-radius:4px;'
           ' font-family:Consolas,monospace; white-space:pre-wrap;"')

    arbol = ("plugins/\n"
             "  mi_plugin/\n"
             "    manifest.json\n"
             "    __init__.py")

    manifest = ('{\n'
                '  "name": "Mi plugin",\n'
                '  "id": "mi_plugin",\n'
                '  "version": "1.0.0",\n'
                '  "author": "Tu nombre",\n'
                '  "api_version": 1,\n'
                '  "description": "Que hace el plugin."\n'
                '}')

    controles = ('self.add_slider_row(clave, etiqueta, min, max, valor)\n'
                 'self.add_checkbox_row(clave, etiqueta, por_defecto)\n'
                 'self.add_combo_row(clave, etiqueta, [opcion1, opcion2], indice)\n'
                 'self.add_color_row(clave, etiqueta, "#000000")\n'
                 'self.add_angle_row(clave, etiqueta, min, max, valor)')

    lectores = ('self.val(clave)          -> deslizador / angulo (int)\n'
                'self.checked(clave)      -> casilla (bool)\n'
                'self.combo_index(clave)  -> desplegable (int)\n'
                'self.color(clave)        -> color (r, g, b)')

    ejemplo = (
        'import numpy as np\n'
        '\n'
        'def registrar(api):\n'
        '    api.registrar_traducciones({\n'
        '        "sepia.title": {"es": "Sepia", "en": "Sepia", "fr": "Sepia"},\n'
        '        "sepia.amt":   {"es": "Intensidad", "en": "Intensity", "fr": "Intensite"},\n'
        '    })\n'
        '\n'
        '    class SepiaDialog(api.AdjustmentDialog):\n'
        '        title = api.t("sepia.title")\n'
        '\n'
        '        def build_controls(self):\n'
        '            self.add_slider_row("amt", api.t("sepia.amt"), 0, 100, 100)\n'
        '\n'
        '        def compute(self, arr):\n'
        '            inten = self.val("amt") / 100.0\n'
        '            if inten <= 0:\n'
        '                return arr\n'
        '            rgb = arr[:, :, :3].astype(np.float32)\n'
        '            r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]\n'
        '            sep = np.empty_like(rgb)\n'
        '            sep[:, :, 0] = 0.393*r + 0.769*g + 0.189*b\n'
        '            sep[:, :, 1] = 0.349*r + 0.686*g + 0.168*b\n'
        '            sep[:, :, 2] = 0.272*r + 0.534*g + 0.131*b\n'
        '            np.clip(sep, 0, 255, out=sep)\n'
        '            mez = rgb*(1.0 - inten) + sep*inten\n'
        '            arr[:, :, :3] = mez.astype(np.uint8)\n'
        '            return arr\n'
        '\n'
        '    api.registrar_ajuste("sepia", SepiaDialog)')

    b_arbol = '<pre %s>%s</pre>' % (PRE, html.escape(arbol))
    b_manifest = '<pre %s>%s</pre>' % (PRE, html.escape(manifest))
    b_controles = '<pre %s>%s</pre>' % (PRE, html.escape(controles))
    b_lectores = '<pre %s>%s</pre>' % (PRE, html.escape(lectores))
    b_ejemplo = '<pre %s>%s</pre>' % (PRE, html.escape(ejemplo))

    H2 = '<h2 style="color:#e0e0e0; font-size:20px;">%s</h2>'
    H3 = '<h3 style="color:#e0e0e0; font-size:15px;">%s</h3>'

    if lang == "en":
        p = []
        p.append(H2 % "Creating plugins for Imago")
        p.append('<p>A <b>plugin</b> adds new <b>Adjustments</b> and <b>Effects</b> to Imago without touching its code. You write a small piece of Python that transforms pixels; in return Imago gives you, for free, the panel with <b>live preview</b>, the Reset button, <b>undo/redo</b>, respect for the active <b>selection</b> and the dark theme.</p>')
        p.append('<p style="color:#ffcc66;"><b>Warning:</b> a plugin is Python code running with your full permissions. Only publish and use plugins from sources you trust.</p>')
        p.append(H3 % "1. Where they are installed")
        p.append('<p>Each plugin is a <b>folder</b> inside the <code>plugins</code> folder of Imago\'s user data:</p>'
                 '<ul><li>Windows (installed): <code>%APPDATA%\\Imago\\plugins\\</code></li>'
                 '<li>Portable: <code>datos\\plugins\\</code> next to the executable.</li></ul>'
                 '<p>Imago creates that folder by itself the first time. Plugins load at startup.</p>')
        p.append(H3 % "2. Plugin structure")
        p.append(b_arbol)
        p.append(H3 % "3. The manifest.json")
        p.append(b_manifest)
        p.append('<p><code>api_version</code> is the plugin API version it needs (currently <b>1</b>). If you ask for one higher than this Imago supports, the plugin is skipped.</p>')
        p.append(H3 % "4. The registrar(api) function")
        p.append('<p>Imago imports your <code>__init__.py</code> and calls <code>registrar(api)</code>. There you define your dialog and register it:</p>'
                 '<ul><li><code>api.registrar_ajuste(key, DialogClass)</code> &rarr; Adjustments &#9656; Plugins.</li>'
                 '<li><code>api.registrar_efecto(key, DialogClass)</code> &rarr; Effects &#9656; Plugins.</li></ul>'
                 '<p>Both accept <code>titulo=</code> (menu text; defaults to <code>DialogClass.title</code>) and <code>icono=</code> (an optional <code>:/icons/x.png</code> resource path).</p>')
        p.append(H3 % "5. The dialog: build_controls() and compute(arr)")
        p.append('<p>Your dialog <b>inherits from <code>api.AdjustmentDialog</code></b> and defines:</p>'
                 '<ul><li><code>title</code>: the visible name.</li>'
                 '<li><code>build_controls(self)</code>: creates the controls (sliders, checkboxes...).</li>'
                 '<li><code>compute(self, arr)</code>: receives the image as a <b>NumPy</b> array and returns the result.</li></ul>')
        p.append('<p><b>The compute array</b> is a <code>numpy.uint8</code> array of shape <b>(height, width, 4)</b> in <b>RGBA</b> order: channel 0=Red, 1=Green, 2=Blue, 3=Alpha. Return an array of the same type and shape. <b>Preserve the alpha channel</b> (channel 3) unless you mean to change transparency.</p>')
        p.append('<p><b>Controls</b> you can add inside <code>build_controls</code>:</p>')
        p.append(b_controles)
        p.append('<p>And to read their values inside <code>compute</code>:</p>')
        p.append(b_lectores)
        p.append(H3 % "6. Translated text (optional)")
        p.append('<p>To make your plugin speak EN/ES/FR, register your strings and read them with <code>api.t</code>:</p>'
                 '<pre %s>%s</pre>' % (PRE, html.escape('api.registrar_traducciones({\n    "myplugin.title": {"es": "...", "en": "...", "fr": "..."},\n})\ntitle = api.t("myplugin.title")')))
        p.append(H3 % "7. Full example (a sepia adjustment)")
        p.append(b_ejemplo)
        p.append(H3 % "8. Useful details")
        p.append('<ul>'
                 '<li><b>Heavy preview:</b> if your <code>compute</code> is slow, set <code>heavy = True</code> on the class so the preview recomputes when you release the control, and/or <code>preview_downscale = True</code> to preview on a reduced version.</li>'
                 '<li><b>Selection:</b> if there is an active selection, Imago already crops the area and your <code>compute</code> only sees that patch; you need to do nothing.</li>'
                 '<li><b>Errors:</b> if your plugin fails to load, Imago does not crash: it logs the error to <code>imago_crash.log</code> and continues with the rest.</li>'
                 '<li><b>NumPy</b> ships with Imago (<code>import numpy as np</code>). For other libraries you must make sure they are available.</li></ul>')
        return "".join(p)

    if lang == "fr":
        p = []
        p.append(H2 % "Créer des extensions pour Imago")
        p.append('<p>Une <b>extension</b> ajoute de nouveaux <b>Réglages</b> et <b>Effets</b> à Imago sans toucher à son code. Vous écrivez un petit morceau de Python qui transforme des pixels ; en échange, Imago vous offre le panneau avec <b>aperçu en direct</b>, le bouton Réinitialiser, l\'<b>annuler/rétablir</b>, le respect de la <b>sélection</b> active et le thème sombre.</p>')
        p.append('<p style="color:#ffcc66;"><b>Avertissement :</b> une extension est du code Python exécuté avec tous vos droits. Ne publiez et n\'utilisez que des extensions de sources fiables.</p>')
        p.append(H3 % "1. Où elles s'installent")
        p.append('<p>Chaque extension est un <b>dossier</b> dans le dossier <code>plugins</code> des données utilisateur d\'Imago :</p>'
                 '<ul><li>Windows (installé) : <code>%APPDATA%\\Imago\\plugins\\</code></li>'
                 '<li>Portable : <code>datos\\plugins\\</code> à côté de l\'exécutable.</li></ul>'
                 '<p>Imago crée ce dossier tout seul la première fois. Les extensions se chargent au démarrage.</p>')
        p.append(H3 % "2. Structure d'une extension")
        p.append(b_arbol)
        p.append(H3 % "3. Le manifest.json")
        p.append(b_manifest)
        p.append('<p><code>api_version</code> est la version de l\'API d\'extensions requise (actuellement <b>1</b>). Si vous demandez une version supérieure à celle d\'Imago, l\'extension est ignorée.</p>')
        p.append(H3 % "4. La fonction registrar(api)")
        p.append('<p>Imago importe votre <code>__init__.py</code> et appelle <code>registrar(api)</code>. Vous y définissez votre dialogue et l\'enregistrez :</p>'
                 '<ul><li><code>api.registrar_ajuste(cle, ClasseDialogue)</code> &rarr; Réglages &#9656; Extensions.</li>'
                 '<li><code>api.registrar_efecto(cle, ClasseDialogue)</code> &rarr; Effets &#9656; Extensions.</li></ul>'
                 '<p>Les deux acceptent <code>titulo=</code> (texte du menu ; par défaut <code>ClasseDialogue.title</code>) et <code>icono=</code> (chemin de ressource <code>:/icons/x.png</code>, optionnel).</p>')
        p.append(H3 % "5. Le dialogue : build_controls() et compute(arr)")
        p.append('<p>Votre dialogue <b>hérite de <code>api.AdjustmentDialog</code></b> et définit :</p>'
                 '<ul><li><code>title</code> : le nom visible.</li>'
                 '<li><code>build_controls(self)</code> : crée les contrôles (curseurs, cases...).</li>'
                 '<li><code>compute(self, arr)</code> : reçoit l\'image comme tableau <b>NumPy</b> et renvoie le résultat.</li></ul>')
        p.append('<p><b>Le tableau de compute</b> est un tableau <code>numpy.uint8</code> de forme <b>(hauteur, largeur, 4)</b> en ordre <b>RGBA</b> : canal 0=Rouge, 1=Vert, 2=Bleu, 3=Alpha. Renvoyez un tableau du même type et de la même forme. <b>Préservez le canal alpha</b> (canal 3) sauf si vous voulez modifier la transparence.</p>')
        p.append('<p><b>Contrôles</b> à ajouter dans <code>build_controls</code> :</p>')
        p.append(b_controles)
        p.append('<p>Et pour lire leurs valeurs dans <code>compute</code> :</p>')
        p.append(b_lectores)
        p.append(H3 % "6. Textes traduits (optionnel)")
        p.append('<p>Pour que votre extension parle FR/ES/EN, enregistrez vos textes et lisez-les avec <code>api.t</code> :</p>'
                 '<pre %s>%s</pre>' % (PRE, html.escape('api.registrar_traducciones({\n    "monext.titre": {"es": "...", "en": "...", "fr": "..."},\n})\ntitle = api.t("monext.titre")')))
        p.append(H3 % "7. Exemple complet (un réglage sépia)")
        p.append(b_ejemplo)
        p.append(H3 % "8. Détails utiles")
        p.append('<ul>'
                 '<li><b>Aperçu lourd :</b> si votre <code>compute</code> est lent, mettez <code>heavy = True</code> sur la classe pour que l\'aperçu se recalcule au relâchement du contrôle, et/ou <code>preview_downscale = True</code> pour prévisualiser sur une version réduite.</li>'
                 '<li><b>Sélection :</b> s\'il y a une sélection active, Imago recadre déjà la zone et votre <code>compute</code> ne voit que ce morceau ; vous n\'avez rien à faire.</li>'
                 '<li><b>Erreurs :</b> si votre extension échoue au chargement, Imago ne plante pas : il consigne l\'erreur dans <code>imago_crash.log</code> et continue avec le reste.</li>'
                 '<li><b>NumPy</b> est fourni avec Imago (<code>import numpy as np</code>). Pour d\'autres bibliothèques, vous devez vous assurer qu\'elles sont disponibles.</li></ul>')
        return "".join(p)

    # Español (por defecto)
    p = []
    p.append(H2 % "Crear plugins para Imago")
    p.append('<p>Un <b>plugin</b> añade nuevos <b>Ajustes</b> y <b>Efectos</b> a Imago sin tocar su código. Escribes una pequeña pieza de Python que transforma píxeles; a cambio, Imago te da gratis el panel con <b>vista previa en vivo</b>, el botón Restablecer, el <b>deshacer/rehacer</b>, el respeto de la <b>selección</b> activa y el tema oscuro.</p>')
    p.append('<p style="color:#ffcc66;"><b>Aviso:</b> un plugin es código Python que se ejecuta con todos tus permisos. Publica y usa solo plugins de fuentes en las que confíes.</p>')
    p.append(H3 % "1. Dónde se instalan")
    p.append('<p>Cada plugin es una <b>carpeta</b> dentro de la carpeta <code>plugins</code> de los datos de usuario de Imago:</p>'
             '<ul><li>Windows (instalado): <code>%APPDATA%\\Imago\\plugins\\</code></li>'
             '<li>Portable: <code>datos\\plugins\\</code> junto al ejecutable.</li></ul>'
             '<p>Imago crea esa carpeta sola la primera vez. Los plugins se cargan al arrancar.</p>')
    p.append(H3 % "2. Estructura de un plugin")
    p.append(b_arbol)
    p.append(H3 % "3. El manifest.json")
    p.append(b_manifest)
    p.append('<p><code>api_version</code> es la versión de la API de plugins que necesita (hoy <b>1</b>). Si pides una mayor que la que soporta este Imago, el plugin se omite.</p>')
    p.append(H3 % "4. La función registrar(api)")
    p.append('<p>Imago importa tu <code>__init__.py</code> y llama a <code>registrar(api)</code>. Ahí defines tu diálogo y lo das de alta:</p>'
             '<ul><li><code>api.registrar_ajuste(clave, ClaseDialogo)</code> &rarr; Ajustes &#9656; Plugins.</li>'
             '<li><code>api.registrar_efecto(clave, ClaseDialogo)</code> &rarr; Efectos &#9656; Plugins.</li></ul>'
             '<p>Ambas aceptan <code>titulo=</code> (texto del menú; por defecto <code>ClaseDialogo.title</code>) e <code>icono=</code> (ruta de recurso <code>:/icons/x.png</code>, opcional).</p>')
    p.append(H3 % "5. El diálogo: build_controls() y compute(arr)")
    p.append('<p>Tu diálogo <b>hereda de <code>api.AdjustmentDialog</code></b> y define:</p>'
             '<ul><li><code>title</code>: el nombre que se ve.</li>'
             '<li><code>build_controls(self)</code>: crea los controles (deslizadores, casillas...).</li>'
             '<li><code>compute(self, arr)</code>: recibe la imagen como array <b>NumPy</b> y devuelve el resultado.</li></ul>')
    p.append('<p><b>El array de compute</b> es un array <code>numpy.uint8</code> de forma <b>(alto, ancho, 4)</b> en orden <b>RGBA</b>: canal 0=Rojo, 1=Verde, 2=Azul, 3=Alfa. Devuelve un array del mismo tipo y forma. <b>Respeta el canal alfa</b> (canal 3) salvo que quieras cambiar la transparencia.</p>')
    p.append('<p><b>Controles</b> que puedes añadir dentro de <code>build_controls</code>:</p>')
    p.append(b_controles)
    p.append('<p>Y para leer sus valores dentro de <code>compute</code>:</p>')
    p.append(b_lectores)
    p.append(H3 % "6. Textos traducidos (opcional)")
    p.append('<p>Para que tu plugin hable ES/EN/FR, registra tus textos y léelos con <code>api.t</code>:</p>'
             '<pre %s>%s</pre>' % (PRE, html.escape('api.registrar_traducciones({\n    "miplugin.titulo": {"es": "...", "en": "...", "fr": "..."},\n})\ntitle = api.t("miplugin.titulo")')))
    p.append(H3 % "7. Ejemplo completo (un ajuste de sepia)")
    p.append(b_ejemplo)
    p.append(H3 % "8. Detalles útiles")
    p.append('<ul>'
             '<li><b>Vista previa pesada:</b> si tu <code>compute</code> es lento, pon <code>heavy = True</code> en la clase para que la preview se recalcule al soltar el control, y/o <code>preview_downscale = True</code> para previsualizar sobre una versión reducida.</li>'
             '<li><b>Selección:</b> si hay una selección activa, Imago ya recorta el área y tu <code>compute</code> solo ve ese trozo; no tienes que hacer nada.</li>'
             '<li><b>Errores:</b> si tu plugin falla al cargar, Imago no se cae: registra el error en <code>imago_crash.log</code> y sigue con el resto.</li>'
             '<li><b>NumPy</b> viene con Imago (<code>import numpy as np</code>). Para otras librerías tendrías que asegurarte de que estén disponibles.</li></ul>')
    return "".join(p)


class PluginGuideDialog(FramelessDialog):
    """Guía técnica para crear plugins de terceros (Ayuda → Crear plugins...)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("plugin_guide.title", default="Crear plugins"))
        self._body.setFixedSize(760, 620)
        self.setStyleSheet(_dark() + theme.dialog_button_plain_qss())

        layout = self.body_layout
        tb = _text_browser()
        tb.setHtml(_themed_html(_plugin_guide_html()))
        layout.addWidget(tb)

        btns = QHBoxLayout()
        btns.addStretch()
        close = QPushButton(t("btn.close", default="Cerrar"))
        close.clicked.connect(self.accept)
        btns.addWidget(close)
        layout.addLayout(btns)


class ShortcutsDialog(FramelessDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("shortcuts.title", default="Atajos de teclado"))
        self._body.setFixedSize(520, 560)
        self.setStyleSheet(_dark() + theme.dialog_button_plain_qss())

        layout = self.body_layout
        tb = _text_browser()
        tb.setHtml(_themed_html(_shortcuts_html()))
        layout.addWidget(tb)

        btns = QHBoxLayout()
        btns.addStretch()
        close = QPushButton(t("btn.close", default="Cerrar"))
        close.clicked.connect(self.accept)
        btns.addWidget(close)
        layout.addLayout(btns)
