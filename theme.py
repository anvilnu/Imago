# theme.py
"""Tema visual de Imago: UNICA FUENTE DE VERDAD para colores y estilos de
controles.

Cualquier widget que necesite estilo propio debe tomarlo de aqui, para que el
resaltado (hover / pressed / checked / disabled) sea identico en toda la app.
La regla: NUNCA dependemos del hover por defecto de Fusion; lo definimos aqui.

Este modulo es ADITIVO: los arquetipos ya publicados no cambian de aspecto.
Segun se vayan unificando mas archivos (dialogos, paneles, barra de opciones)
se AGREGAN funciones nuevas (combo, spinbox, checkbox, boton de dialogo...),
pero las existentes se mantienen estables para que reaplicar sea seguro.
"""

# =====================================================================
#  PALETA BASE  (los hex exactos que ya usaba el proyecto)
# =====================================================================
BG_WINDOW     = "#2b2b2b"   # fondo general de paneles/ventanas
BG_DARK       = "#202020"   # barras (menu, toolbars, estado) y campos
BG_BASE       = "#202020"   # alias: fondo de campos de entrada
BG_BUTTON     = "#3a3a3a"   # fondo de boton con relieve en reposo
BG_HOVER      = "#333333"   # fondo al pasar el raton
BG_PRESSED    = "#1a4f7c"   # fondo al pulsar / activo (azul oscuro)
BG_TILE       = "#404040"   # fondo gris DETRÁS del lienzo (área del scroll y el
                            # relleno de los márgenes al desbordar la selección).
                            # Cámbialo aquí para probar tonos.

TEXT          = "#e0e0e0"   # texto normal
TEXT_DIM      = "#aaaaaa"   # texto secundario (barra de estado)
TEXT_MUTED    = "#888888"   # texto tenue (ayudas)
TEXT_DISABLED = "#555555"   # texto deshabilitado
TEXT_HINT     = "#666666"   # texto de pista muy tenue (placeholder, "arrastrar aquí")

BORDER        = "#555555"   # borde de ventana / paneles
BORDER_SOFT   = "#484848"   # separadores / lineas finas
BORDER_BUTTON = "#4a4a4a"   # borde de boton con relieve en reposo
BORDER_FAINT  = "#444444"   # borde tenue (campos, flechas)
BORDER_DIM    = "#333333"   # borde de control deshabilitado

ACCENT        = "#007acc"   # azul de acento (hover / borde activo)
ACCENT_BRIGHT = "#3399dd"   # azul claro (hover de handles de slider)
ACCENT_DARK   = "#1a4f7c"   # azul oscuro (seleccion / activo) == BG_PRESSED
DANGER        = "#ff4444"   # rojo de cerrar
WARNING       = "#ffcc66"   # ambar de aviso (seguridad de plugins, etc.)
SEL_TEXT      = "#ffffff"   # texto sobre el fondo de seleccion (BG_PRESSED)

FONT = "'Segoe UI', 'Noto Sans', 'DejaVu Sans', Arial, sans-serif"

# Tonos especificos de algunos arquetipos (se conservan tal cual para no
# alterar el aspecto en reposo; ver nota de uniformidad #5):
BORDER_CHECK     = "#5a5a5a"   # borde de la casilla en reposo
CAPTION_CLOSE    = "#c42b1c"   # rojo de cerrar de la barra de titulo (estilo Windows)

# Botones / paneles. Tras la pasada de uniformidad: TODOS los botones con
# relieve comparten un unico gris de reposo (BG_BUTTON) y un unico hover
# (BG_HOVER_RAISED). Antes habia un casi-duplicado para dialogos (#383838 /
# #454545) que se ha colapsado a estos.
BG_HOVER_RAISED  = "#4a4a4a"   # hover de boton CON RELIEVE (aclara desde BG_BUTTON)
BG_DISABLED      = "#222222"   # fondo de boton deshabilitado (estado 'apagado' de paneles)
BORDER_INPUT     = "#3d3d3d"   # borde de listas y campos de texto
TEXT_FAINT       = "#777777"   # texto fantasma (historial deshecho, en italica)

# Colores semanticos puntuales (uno o pocos usos concretos): se centralizan aqui
# para no incrustarlos a mano en los widgets (norma: el color sale de theme.py).
TEXT_BRIGHT = "#cccccc"   # texto un punto mas claro que el secundario (valores)
INFO_BLUE   = "#9cc6ff"   # azul claro: tamano/valor resultante destacado en dialogos
TITLE_GREY  = "#9aa0a6"   # gris de titulos de seccion (selector de formas)
CHANNEL_R   = "#ff8888"   # etiqueta del canal Rojo
CHANNEL_G   = "#88ff88"   # etiqueta del canal Verde
CHANNEL_B   = "#8888ff"   # etiqueta del canal Azul


# =====================================================================
#  CONMUTADOR DE TEMA  (base del tema claro)
# =====================================================================
# Los valores de arriba son el TEMA OSCURO (el de siempre, por defecto). El tema
# claro se activa con use_theme("light"), que REASIGNA esos tokens con el juego
# _LIGHT de abajo. Como toda la app hace "import theme" + "theme.X" y las
# funciones de QSS leen los globals en el momento de construir cada widget,
# basta con llamar a use_theme() ANTES de montar la UI para que todo salga claro.
#
# ICON_TINT: en oscuro es None (los iconos, siluetas casi-blancas, se usan tal
# cual). En claro es un gris oscuro y el factory icono()/tintar_pixmap()
# recolorea la silueta para que se vea sobre fondo claro. El logo de marca
# (imago.png) NUNCA se tinta.
MODE = "dark"          # "dark" | "light"
ICON_TINT = None       # None = sin tinte; hex ("#333333") = recolorear iconos

# Iconos que NO se tintan aunque el tema sea claro (arte de marca a color).
LOGOS_SIN_TINTE = ("imago.png",)

# Solo los tokens que CAMBIAN respecto al oscuro (ACCENT, ACCENT_BRIGHT, DANGER,
# CAPTION_CLOSE y FONT se conservan: funcionan igual sobre claro).
_LIGHT = {
    "BG_WINDOW":       "#f0f0f0",
    "BG_DARK":         "#e4e4e4",
    "BG_BASE":         "#ffffff",
    "BG_BUTTON":       "#e6e6e6",
    "BG_HOVER":        "#dcdcdc",
    "BG_PRESSED":      "#cfe4f7",
    "BG_TILE":         "#c8c8c8",
    "TEXT":            "#202020",
    "TEXT_DIM":        "#555555",
    "TEXT_MUTED":      "#6a6a6a",
    "TEXT_DISABLED":   "#aaaaaa",
    "TEXT_HINT":       "#999999",
    "BORDER":          "#b8b8b8",
    "BORDER_SOFT":     "#cccccc",
    "BORDER_BUTTON":   "#bcbcbc",
    "BORDER_FAINT":    "#c6c6c6",
    "BORDER_DIM":      "#d2d2d2",
    "ACCENT_DARK":     "#cfe4f7",   # == BG_PRESSED en claro
    "BORDER_CHECK":    "#b0b0b0",
    "BG_HOVER_RAISED": "#d6d6d6",
    "BG_DISABLED":     "#e8e8e8",
    "BORDER_INPUT":    "#c4c4c4",
    "TEXT_FAINT":      "#aaaaaa",
    "TEXT_BRIGHT":     "#333333",
    "INFO_BLUE":       "#0a63b0",
    "WARNING":         "#9a6a00",
    "SEL_TEXT":        "#14344f",   # texto oscuro sobre la selección azul clara
    "TITLE_GREY":      "#6a7075",
    "CHANNEL_R":       "#cc3333",
    "CHANNEL_G":       "#2e9e2e",
    "CHANNEL_B":       "#3355cc",
}


def use_theme(mode):
    """Fija el juego de tokens del tema pedido ("dark" | "light"). Reasigna los
    globals de este modulo (y ICON_TINT). Llamalo ANTES de construir la UI: los
    QSS y el factory de iconos leen estos globals al construir cada widget. El
    tema oscuro es el de por defecto y no altera nada."""
    global MODE, ICON_TINT
    if mode == "light":
        globals().update(_LIGHT)
        ICON_TINT = "#333333"
        MODE = "light"
    else:
        MODE = "dark"
        ICON_TINT = None


def es_logo(ruta):
    """True si la ruta de recurso corresponde a arte de marca que NO se tinta."""
    if not isinstance(ruta, str):
        return False
    nombre = ruta.replace("\\", "/").rsplit("/", 1)[-1]
    return nombre in LOGOS_SIN_TINTE


def tintar_pixmap(pm):
    """Recolorea un pixmap monocromo a ICON_TINT conservando su alfa (bordes
    antialias limpios), via CompositionMode_SourceIn. Si no hay tinte activo o
    el pixmap es nulo, devuelve el original sin tocar."""
    if not ICON_TINT or pm is None or pm.isNull():
        return pm
    from PySide6.QtGui import QPixmap, QPainter, QColor
    from PySide6.QtCore import Qt
    out = QPixmap(pm.size())
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.drawPixmap(0, 0, pm)
    p.setCompositionMode(QPainter.CompositionMode_SourceIn)
    p.fillRect(out.rect(), QColor(ICON_TINT))
    p.end()
    return out


def icono(ruta):
    """Factory CENTRAL de QIcon consciente del tinte: carga el recurso y, en tema
    claro, tinta la silueta (salvo el logo de marca). Los call-sites que hoy
    hacen QIcon(":/icons/..") deben pasar por aqui para que tinten en claro.
    En tema oscuro devuelve el icono tal cual (sin coste extra)."""
    from PySide6.QtGui import QIcon, QPixmap
    if not ICON_TINT or es_logo(ruta):
        return QIcon(ruta)
    pm = QPixmap(ruta)
    if pm.isNull():
        return QIcon(ruta)
    return QIcon(tintar_pixmap(pm))


_icon_url_cache = {}

def qss_icon_url(recurso):
    """URL de icono para usar en QSS (`image: url(...)`). En tema oscuro devuelve
    el propio recurso (:/icons/..). En claro, como el QSS no sabe tintar, genera
    un PNG tintado en la cache y devuelve su file:// url. Se usa para las flechas
    de combo/spinbox, que si no quedarian casi blancas sobre fondo claro."""
    if not ICON_TINT:
        return recurso
    if recurso in _icon_url_cache:
        return _icon_url_cache[recurso]
    from PySide6.QtGui import QPixmap
    from PySide6.QtCore import QStandardPaths, QDir
    import os, hashlib
    pm = QPixmap(recurso)
    if pm.isNull():
        return recurso
    pm = tintar_pixmap(pm)
    base = QStandardPaths.writableLocation(QStandardPaths.CacheLocation) or QDir.tempPath()
    try:
        os.makedirs(base, exist_ok=True)
    except OSError:
        base = QDir.tempPath()
    nombre = "imago_tint_" + hashlib.md5((recurso + ICON_TINT).encode()).hexdigest()[:10] + ".png"
    ruta = os.path.join(base, nombre)
    pm.save(ruta, "PNG")
    # Ruta PLANA con barras normales (sin esquema file://): el url() de las QSS
    # de Qt NO acepta file:///, quiere una ruta de fichero o de recurso. Se
    # entrecomilla en el call-site por si la ruta lleva espacios.
    url = ruta.replace("\\", "/")
    _icon_url_cache[recurso] = url
    return url


# =====================================================================
#  HELPERS DE MARCO / SUPERFICIE
# =====================================================================
def frame_qss(object_name, bg=None, border=None, width=1):
    """Marco con borde para un widget con setObjectName(object_name). Lo usan
    el _frame de los dialogos y el de los paneles flotantes (que no pintan bien
    el borde de una ventana top-level por stylesheet, asi que lo lleva un hijo).

    OJO: los colores por defecto se resuelven AQUI (bg is None -> BG_WINDOW), no
    como valores por defecto del parametro: un default se ata al importar el
    modulo (tema oscuro) y no cambiaria al conmutar a claro con use_theme()."""
    if bg is None:
        bg = BG_WINDOW
    if border is None:
        border = BORDER
    return ("#%s { background-color: %s; border: %dpx solid %s; }"
            % (object_name, bg, int(width), border))


# =====================================================================
#  ARQUETIPOS DE CONTROL  (devuelven el QSS listo para setStyleSheet)
# =====================================================================
def toolbutton_flat_qss():
    """Boton de accion plano (barra fija, controles de zoom).

    Parte transparente y al pasar el raton se resalta en gris con borde azul;
    al pulsar, azul oscuro. NO se estiliza :checked a proposito: en estos
    botones el estado activo lo transmite el propio icono (ver
    crear_icono_checkable en main.py), no un fondo de color.
    """
    return f"""
        QToolButton {{
            background-color: transparent;
            border: 1px solid transparent;
            border-radius: 4px;
            padding: 3px;
            color: {TEXT};
        }}
        QToolButton:hover {{
            background-color: {BG_HOVER};
            border: 1px solid {ACCENT};
        }}
        QToolButton:pressed {{
            background-color: {BG_PRESSED};
        }}
        QToolButton:disabled {{
            background-color: transparent;
            border: 1px solid transparent;
            color: {TEXT_DISABLED};
        }}
    """


def toolbutton_toggle_qss():
    """Boton conmutable con relieve (los toggles de panel de arriba a la
    derecha). El fondo azul indica 'panel visible / activo'."""
    return f"""
        QToolButton {{
            background-color: {BG_BUTTON};
            border: 1px solid {BORDER_BUTTON};
            border-radius: 4px;
            padding: 2px;
        }}
        QToolButton:hover {{
            background-color: {BG_HOVER_RAISED};
            border: 1px solid {ACCENT};
        }}
        QToolButton:pressed {{
            background-color: {BG_PRESSED};
            border: 1px solid {ACCENT};
        }}
        QToolButton:checked {{
            background-color: {BG_PRESSED};
            border: 1px solid {ACCENT};
        }}
        QToolButton:disabled {{
            color: {TEXT_DISABLED};
            border: 1px solid {BORDER_FAINT};
        }}
    """


def arrow_button_qss():
    """Flechas de paginacion de la tira de miniaturas. Mantienen su fondo en
    reposo, pero el hover/pressed pasan al lenguaje estandar (gris + borde
    azul / azul oscuro) en vez del gris-claro antiguo, para ser coherentes."""
    return f"""
        QPushButton {{
            background-color: {BG_WINDOW};
            border: 1px solid {BORDER_FAINT};
            border-radius: 4px;
            color: {TEXT};
            font-family: {FONT};
            font-size: 12px;
            font-weight: bold;
        }}
        QPushButton:hover {{
            background-color: {BG_HOVER};
            border: 1px solid {ACCENT};
        }}
        QPushButton:pressed {{
            background-color: {BG_PRESSED};
        }}
        QPushButton:disabled {{
            color: {TEXT_DISABLED};
            border: 1px solid {BORDER_DIM};
        }}
    """


def toolbar_qss():
    """Chrome de una QToolBar oscura (fondo + separador) MAS los botones de
    accion planos. Lo usa la barra de herramientas fija."""
    return f"""
        QToolBar {{
            background-color: {BG_DARK};
            border: none;
            padding: 2px;
        }}
        QToolBar::separator {{
            background: {BORDER_SOFT};
            width: 1px;
            margin: 4px 4px;
        }}
    """ + toolbutton_flat_qss()


def menubar_qss():
    """Barra de menus superior (QMenuBar) + menus desplegables (QMenu). Antes
    estaba incrustada a mano en main.py con hex fijos; ahora sale de aqui para
    que responda al tema (claro/oscuro)."""
    return f"""
        QMenuBar {{ background-color: {BG_DARK}; color: {TEXT}; padding: 4px; font-size: 12px; }}
        QMenuBar::item {{ padding: 2px 8px; background: transparent; border-radius: 3px; }}
        QMenuBar::item:selected {{ background-color: {ACCENT_DARK}; border-radius: 3px; }}
        QMenuBar::item:pressed {{ background-color: {ACCENT}; border-radius: 3px; }}

        QMenu {{
            background-color: {BG_WINDOW};
            color: {TEXT};
            border: 1px solid {BORDER_SOFT};
            padding: 4px;
        }}
        QMenu::item {{
            /* El padding derecho deja sitio al atajo de teclado */
            padding: 5px 30px 5px 10px;
            border-radius: 3px;
        }}
        QMenu::item:selected {{ background-color: {ACCENT_DARK}; }}
        QMenu::item:disabled {{ color: {TEXT_DISABLED}; }}
        QMenu::separator {{ height: 1px; background: {BORDER_SOFT}; margin: 4px 8px; }}
        QMenu::icon {{ padding-left: 6px; }}
    """


def optionsbar_qss():
    """Barra de opciones dinamica (QToolBar bajo la barra de herramientas)."""
    return f"""
        QToolBar {{
            background-color: {BG_DARK};
            border-bottom: 1px solid {BORDER_SOFT};
            padding: 3px;
            border-top: none;
            border-left: none;
            border-right: none;
        }}
        QLabel {{ color: {TEXT}; }}
    """


def statusbar_qss():
    """Barra de estado inferior."""
    return f"""
        QStatusBar {{
            background-color: {BG_DARK};
            color: {TEXT_DIM};
            border-left: 1px solid {BORDER};
            border-right: 1px solid {BORDER};
            border-bottom: 1px solid {BORDER};
            font-family: 'Segoe UI';
            font-size: 11px;
            min-height: 30px;
            max-height: 30px;
        }}
        QStatusBar::item {{ border: none; }}
    """


def tooltip_qss():
    """Estilo de los tooltips (QToolTip). Se aplica como stylesheet GLOBAL de la
    QApplication: no hay ninguna regla QToolTip en los widgets, y sin ella el
    aspecto del tooltip depende de si el widget bajo el cursor tiene stylesheet o
    no (unos salían oscuros y otros claros con texto invisible). Con esta regla
    todos son iguales y respetan el tema."""
    return f"""
        QToolTip {{
            background-color: {BG_WINDOW};
            color: {TEXT};
            border: 1px solid {BORDER};
            padding: 1px 6px;
        }}
    """


def combobox_qss():
    """Desplegable (QComboBox) de las barras de opciones. Reposo plano oscuro;
    al pasar el raton, borde azul (antes era gris #666666: ese era el outlier)."""
    return f"""
        QComboBox {{
            background-color: {BG_WINDOW}; border: 1px solid {BORDER_FAINT}; border-radius: 4px;
            color: {TEXT}; font-family: 'Segoe UI'; font-size: 11px; padding: 2px 14px 2px 5px;
            combobox-popup: 0;
        }}
        QComboBox:hover {{ background-color: {BG_HOVER}; border: 1px solid {ACCENT}; }}
        QComboBox::drop-down {{
            subcontrol-origin: padding; subcontrol-position: top right; width: 18px;
            border-left: 1px solid {BORDER_FAINT}; border-top-right-radius: 4px; border-bottom-right-radius: 4px;
            background-color: {BG_HOVER};
        }}
        QComboBox::down-arrow {{ image: url("{qss_icon_url(':/icons/down_arrow.png')}"); width: 10px; height: 6px; }}
        QComboBox QAbstractItemView {{
            background-color: {BG_WINDOW}; border: 1px solid {BORDER_FAINT}; color: {TEXT};
            selection-background-color: {ACCENT}; selection-color: white; outline: 0px;
        }}
        QComboBox QAbstractItemView::item:hover {{
            background-color: {ACCENT}; color: white;
        }}
        QComboBox QAbstractItemView::item:selected {{
            background-color: {ACCENT}; color: white;
        }}
    """


def combobox_dialog_qss():
    """Desplegable (QComboBox) ESTÁNDAR de los DIÁLOGOS (Nuevo, Abrir,
    Preferencias, Redimensionar...). Mismo estilo que el de la barra de opciones
    pero con mayor altura (26px) para alinearse con los QSpinBox y botones de los
    diálogos. Los comboboxes de la barra de opciones usan combobox_qss() (más
    compacto): NO mezclar, cada ámbito tiene su regla.

    El FONDO se fija a BG_DARK (no BG_WINDOW) para que coincida con el de los
    QSpinBox/QDoubleSpinBox de los diálogos (spinbox_dialog_qss usa BG_DARK): así
    ancho/alto y desplegables comparten el mismo color de campo. El hover mantiene
    el fondo oscuro (solo cambia el borde a azul), igual que el spinbox, que no se
    aclara al pasar el ratón. La barra de opciones NO se ve afectada (usa
    combobox_qss)."""
    return combobox_qss() + f"""
        QComboBox {{
            min-height: 26px; max-height: 26px;
            background-color: {BG_DARK};
        }}
        QComboBox:hover {{ background-color: {BG_DARK}; border: 1px solid {ACCENT}; }}
    """


def value_label_qss():
    """Etiqueta de VALOR/parámetro de la barra de opciones (p. ej. "Dureza",
    "Flujo"...): texto secundario tenue, pequeño, con un pelín de margen. Patrón
    repetido por toda la barra de opciones."""
    return f"font-family: {FONT}; font-size: 11px; color: {TEXT_DIM}; margin-left: 1px;"


def info_label_qss():
    """Etiqueta INFORMATIVA en cursiva (notas, ayudas breves): texto tenue,
    pequeño, itálica. Patrón repetido en barra de opciones y diálogos."""
    return f"color: {TEXT_MUTED}; font-family: {FONT}; font-size: 11px; font-style: italic;"


def small_button_qss():
    """Botones pequenos etiquetados (los +/- de las barras de opciones). Reposo
    plano oscuro; hover gris con borde azul; pulsado azul oscuro. Antes hacian
    hover #383838/borde #666666 y pulsado #1a1a1a (el mismo outlier de las
    flechas); ahora siguen el lenguaje comun."""
    return f"""
        QPushButton {{
            background-color: {BG_WINDOW}; border: 1px solid {BORDER_FAINT}; border-radius: 4px;
            color: {TEXT}; font-family: 'Segoe UI'; font-size: 12px; font-weight: bold;
        }}
        QPushButton:hover {{ background-color: {BG_HOVER}; border: 1px solid {ACCENT}; }}
        QPushButton:pressed {{ background-color: {BG_PRESSED}; }}
        QPushButton:disabled {{ color: {TEXT_DISABLED}; border: 1px solid {BORDER_DIM}; }}
    """


def slider_qss():
    """Deslizador horizontal UNICO de la app: el de la barra dinamica del pincel
    (dureza, flujo, tamano, tolerancia, opacidad, RGB, zoom...). Groove fino con
    borde, mango azul de 10px que se aclara al pasar el raton, y relleno azul
    oscuro (sub-page) en la parte ya recorrida. Lleva fondo transparente para
    verse igual sobre barras, paneles y dialogos."""
    return f"""
        QSlider {{ background: transparent; }}
        QSlider::groove:horizontal {{
            border: 1px solid {BORDER_FAINT}; height: 4px; background: {BG_WINDOW}; border-radius: 2px;
        }}
        QSlider::sub-page:horizontal {{ background: {BG_PRESSED}; border: 1px solid {ACCENT}; border-radius: 2px; }}
        QSlider::handle:horizontal {{
            background: {ACCENT}; border: none; width: 10px; height: 10px; margin: -3px 0; border-radius: 5px;
        }}
        QSlider::handle:horizontal:hover {{ background: {ACCENT_BRIGHT}; }}
    """


def checkbox_qss():
    """Casilla con el azul de la app al marcar (en vez del acento del sistema).
    Marcada+hover usa el azul claro comun {ACCENT_BRIGHT} (antes #1a8fe0)."""
    return f"""
        QCheckBox {{ color: {TEXT}; }}
        QCheckBox::indicator {{ width: 13px; height: 13px; border-radius: 3px;
            border: 1px solid {BORDER_CHECK}; background: {BG_BUTTON}; }}
        QCheckBox::indicator:hover {{ border: 1px solid {ACCENT}; }}
        QCheckBox::indicator:checked {{ background: {ACCENT}; border: 1px solid {ACCENT}; image: url(:/icons/check.png); }}
        QCheckBox::indicator:checked:hover {{ background: {ACCENT_BRIGHT}; border: 1px solid {ACCENT_BRIGHT}; image: url(:/icons/check.png); }}
    """


def labeled_toggle_qss():
    """Boton etiquetado CONMUTABLE (toggles N/K/S de texto, etc.). Reposo con
    relieve; al pasar el raton, borde azul; activo, azul oscuro con borde azul."""
    return f"""
        QPushButton {{
            background-color: {BG_BUTTON}; color: {TEXT};
            border: 1px solid {BORDER_BUTTON}; border-radius: 3px;
        }}
        QPushButton:hover {{ background-color: {BG_HOVER_RAISED}; border: 1px solid {ACCENT}; }}
        QPushButton:checked {{
            background-color: {BG_PRESSED}; border: 1px solid {ACCENT}; color: {SEL_TEXT};
        }}
        QPushButton:disabled {{ color: {TEXT_DISABLED}; border: 1px solid {BORDER_FAINT}; }}
    """


def dialog_button_qss(selector="QPushButton"):
    """Boton etiquetado de dialogo/mensaje (Aceptar, Cancelar, Guardar...).
    Reposo con relieve y borde gris; hover aclara y pone borde azul; pulsado
    azul oscuro {BG_PRESSED} (antes el azul brillante #007acc). Reutilizable
    por los dialogos futuros (Preferencias, Ayuda/Acerca de) pasando su selector.

    IMPORTANTE: dentro de un FramelessDialog, NUNCA pasar 'QPushButton' a secas:
    el boton de cerrar de la barra de titulo (_CaptionButton) tambien es un
    QPushButton, y el min-width/padding lo deformarian (X descentrada, recuadro
    grande). Usar siempre un selector ACOTADO, p.ej. 'QDialogButtonBox QPushButton'
    o '#TuObjectName'."""
    return f"""
        {selector} {{
            background-color: {BG_BUTTON}; color: {TEXT};
            border: 1px solid {BORDER}; border-radius: 4px; padding: 5px 16px;
            min-width: 70px;
        }}
        {selector}:hover {{ background-color: {BG_HOVER_RAISED}; border: 1px solid {ACCENT}; }}
        {selector}:pressed {{ background-color: {BG_PRESSED}; border: 1px solid {ACCENT}; }}
    """


def dialog_button_plain_qss(selector="QPushButton"):
    """Boton etiquetado de dialogo SIN min-width: pensado para usarse con
    selector 'QPushButton' a secas dentro de un FramelessDialog cuyos botones
    se crean sueltos (no en un QDialogButtonBox). Al no fijar min-width NO
    deforma la X de la barra de titulo. Mismo aspecto gris que dialog_button_qss
    (reposo gris, hover azul, pulsado azul oscuro). Lo usan los dialogos Nuevo,
    Cambiar tamano, Tamano de lienzo y Calidad (y vale para Ajustes/Efectos)."""
    return f"""
        {selector} {{
            background-color: {BG_BUTTON}; color: {TEXT};
            border: 1px solid {BORDER}; border-radius: 4px; padding: 5px 14px;
        }}
        {selector}:hover {{ background-color: {BG_HOVER_RAISED}; border: 1px solid {ACCENT}; }}
        {selector}:pressed {{ background-color: {BG_PRESSED}; }}
    """


def mode_toggle_qss():
    """Boton CONMUTABLE plano (modos Anadir/Restar/Intersecar de seleccion y
    modos de movimiento). Reposo plano oscuro; al pasar el raton, borde azul;
    activo, azul oscuro comun de la app. Antes el activo usaba un azul propio
    (#0d5a8a / #2a9fd6 / #0e6499) y el hover borde gris #666666; ahora sigue el
    mismo lenguaje que el resto de conmutables (sin un tono especial de
    checked+hover: el estado activo se mantiene al pasar por encima)."""
    return f"""
        QPushButton {{
            background-color: {BG_WINDOW}; border: 1px solid {BORDER_FAINT};
            border-radius: 4px; color: {TEXT}; font-family: 'Segoe UI'; font-size: 13px;
        }}
        QPushButton:hover {{ background-color: {BG_HOVER}; border: 1px solid {ACCENT}; }}
        QPushButton:checked {{ background-color: {BG_PRESSED}; border: 1px solid {ACCENT}; color: {SEL_TEXT}; }}
        QPushButton:disabled {{ color: {TEXT_DISABLED}; border: 1px solid {BORDER_DIM}; }}
    """


# =====================================================================
#  ARQUETIPOS DE PANEL (Herramientas / Capas / Historial)
# =====================================================================
def list_qss():
    """Marco de un QListWidget de panel (Capas, Historial). NO fija la geometria
    de las filas (::item): cada panel anade su propia regla ::item con su alto/
    margenes, porque difieren (Historial usa filas ultra-compactas)."""
    return f"""
        QListWidget {{
            background-color: {BG_DARK};
            border: 1px solid {BORDER_INPUT};
            border-radius: 4px;
            outline: 0;
        }}
        QListWidget::item {{ border: none; }}
        QListWidget::item:selected {{
            background-color: {BG_PRESSED};
            color: {SEL_TEXT};
        }}
    """


def listview_qss():
    """Igual que list_qss() pero para un QListView (no QListWidget): los selectores
    de tipo en QSS son por clase EXACTA, asi que las reglas 'QListWidget' no
    estilan un QListView. Lo usa el panel de Historial, que corre sobre
    QListView + QAbstractListModel (mas robusto que QListWidget frente a los
    aborts de shiboken al destruir items). Cada panel anade su regla ::item."""
    return f"""
        QListView {{
            background-color: {BG_DARK};
            border: 1px solid {BORDER_INPUT};
            border-radius: 4px;
            outline: 0;
        }}
        QListView::item {{ border: none; }}
        QListView::item:selected {{
            background-color: {BG_PRESSED};
            color: {SEL_TEXT};
        }}
    """


def tool_grid_button_qss():
    """Botones del grid de Herramientas (estilo rejilla Paint.NET: esquinas casi
    rectas, radio 1px). Conmutables: activo en azul. Hover aclara + borde azul.
    Devuelve SOLO las reglas de QToolButton; el panel anade su propio fondo."""
    return f"""
        QToolButton {{
            background-color: {BG_BUTTON};
            border: 1px solid {BORDER_BUTTON};
            border-radius: 1px;
            color: {TEXT};
        }}
        QToolButton:hover {{
            background-color: {BG_HOVER_RAISED};
            border: 1px solid {ACCENT};
        }}
        QToolButton:checked {{
            background-color: {BG_PRESSED};
            border: 1px solid {ACCENT};
        }}
        QToolButton:disabled {{
            background-color: {BG_DISABLED};
            border: 1px solid {BORDER_DIM};
            color: {TEXT_DISABLED};
        }}
    """


def panel_action_button_qss():
    """Botones de accion de Capas e Historial (estilo 'iluminado': borde azul
    permanente cuando estan habilitados, apagado a gris cuando no). Hover aclara;
    pulsado en azul oscuro. Es un idioma propio de estos paneles (distinto del
    'gris en reposo, azul al hover' del resto), conservado a proposito."""
    return f"""
        QPushButton:enabled {{
            background-color: {BG_BUTTON};
            border: 1px solid {ACCENT};
            border-radius: 3px;
            color: {TEXT};
            font-size: 12px;
        }}
        QPushButton:disabled {{
            background-color: {BG_DISABLED};
            border: 1px solid {BORDER_DIM};
            border-radius: 3px;
            color: {TEXT_DISABLED};
            font-size: 12px;
        }}
        QPushButton:hover:enabled {{
            background-color: {BG_HOVER_RAISED};
        }}
        QPushButton:pressed {{
            background-color: {BG_PRESSED};
        }}
    """


def progressbar_qss():
    """Barra de progreso oscura (descarga de modelos de IA y operaciones largas).
    Canal en BG_DARK con borde de campo; relleno (chunk) en azul de acento, con
    el texto de porcentaje centrado en TEXT."""
    return f"""
        QProgressBar {{
            background-color: {BG_DARK};
            border: 1px solid {BORDER_INPUT};
            border-radius: 3px;
            text-align: center;
            color: {TEXT};
            font-size: 11px;
            min-height: 16px;
        }}
        QProgressBar::chunk {{
            background-color: {ACCENT};
            border-radius: 2px;
        }}
    """


def lineedit_qss():
    """Campo de texto oscuro RELLENO (dialogos: Propiedades de capa y, en el
    futuro, Preferencias). Borde azul al enfocar; atenuado al deshabilitar."""
    return f"""
        QLineEdit {{
            background-color: {BG_DARK}; color: {TEXT};
            border: 1px solid {BORDER_INPUT}; border-radius: 3px; padding: 3px;
        }}
        QLineEdit:focus {{ border: 1px solid {ACCENT}; }}
        QLineEdit:disabled {{ color: {TEXT_DISABLED}; border: 1px solid {BORDER_DIM}; }}
    """


def spinbox_qss():
    """Spinbox oscuro (campos numericos de los dialogos de Ajustes/Efectos).
    Botones up/down con relieve unificado (BG_BUTTON en reposo, BG_HOVER_RAISED
    al pasar el raton, BG_PRESSED al pulsar) y flechas por icono."""
    return f"""
        QAbstractSpinBox {{
            background-color: {BG_DARK}; color: {TEXT};
            border: 1px solid {BORDER_FAINT}; border-radius: 3px;
            padding: 2px 2px 2px 4px; min-width: 54px;
        }}
        QAbstractSpinBox:focus {{ border: 1px solid {ACCENT}; }}
        QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{
            subcontrol-origin: border;
            width: 16px;
            background-color: {BG_BUTTON};
            border-left: 1px solid {BORDER_FAINT};
        }}
        QAbstractSpinBox::up-button {{ subcontrol-position: top right; border-top-right-radius: 3px; }}
        QAbstractSpinBox::down-button {{ subcontrol-position: bottom right; border-bottom-right-radius: 3px; border-top: 1px solid {BORDER_FAINT}; }}
        QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover {{ background-color: {BG_HOVER_RAISED}; }}
        QAbstractSpinBox::up-button:pressed, QAbstractSpinBox::down-button:pressed {{ background-color: {BG_PRESSED}; }}
        QAbstractSpinBox::up-arrow {{ image: url("{qss_icon_url(':/icons/up_arrow.png')}"); width: 9px; height: 9px; }}
        QAbstractSpinBox::down-arrow {{ image: url("{qss_icon_url(':/icons/down_arrow.png')}"); width: 9px; height: 9px; }}
    """


def spinbox_dialog_qss():
    """Spinbox ESTÁNDAR de los DIÁLOGOS (Nuevo, Abrir, Cambiar tamaño,
    Calidad...): igual que spinbox_qss() pero con mayor altura (26px) para
    alinearse con los comboboxes y botones de los diálogos. Los spinbox de los
    diálogos de Ajustes/Efectos usan spinbox_qss() (más compacto): cada ámbito
    tiene su regla, no mezclar."""
    return spinbox_qss() + """
        QAbstractSpinBox { min-height: 26px; max-height: 26px; }
    """


def panel_header_qss():
    """Cabecera de un panel empotrado: franja oscura (BG_DARK, igual que las
    barras de menú/estado) con el título del panel, separada del contenido por
    una línea fina. Estilo discreto y coherente con el resto de la interfaz."""
    return f"""
        QLabel {{
            background-color: {BG_DARK};
            color: {TEXT};
            padding: 4px 8px;
            border-bottom: 1px solid {BORDER_SOFT};
        }}
    """


def panel_header_bar_qss():
    """Cabecera de panel CON BOTONES (reordenar ▲/▼, columnas «/»): la franja es
    un QWidget contenedor con el mismo look que panel_header_qss (BG_DARK +
    línea inferior), el título como QLabel transparente y pequeños QToolButton
    planos a la derecha (gris tenue en reposo; hover aclara + borde azul,
    pulsado azul oscuro: el lenguaje de interacción unificado)."""
    return f"""
        QWidget#PanelHeaderBar {{
            background-color: {BG_DARK};
            border-bottom: 1px solid {BORDER_SOFT};
        }}
        QWidget#PanelHeaderBar QLabel {{
            background: transparent;
            color: {TEXT};
            padding: 4px 8px;
            border: none;
        }}
        QWidget#PanelHeaderBar QToolButton {{
            background: transparent;
            border: 1px solid transparent;
            border-radius: 3px;
            color: {TEXT_MUTED};
            font-size: 10px;
            padding: 0px;
        }}
        QWidget#PanelHeaderBar QToolButton:hover {{
            background-color: {BG_BUTTON};
            border: 1px solid {ACCENT};
            color: {TEXT};
        }}
        QWidget#PanelHeaderBar QToolButton:pressed {{
            background-color: {BG_PRESSED};
        }}
    """


def splitter_qss():
    """Separadores (handles) de los QSplitter que empotran los paneles. Hacen de
    línea divisoria entre los paneles de la derecha (Capas/Historial/Color) y
    entre los paneles y el lienzo. En reposo, una línea fina del color de los
    separadores; al pasar el ratón o arrastrar, azul de acento (mismo lenguaje
    de interacción que el resto de la interfaz)."""
    return f"""
        QSplitter::handle {{
            background-color: {BORDER_SOFT};
        }}
        QSplitter::handle:horizontal {{ width: 1px; }}
        QSplitter::handle:vertical {{ height: 1px; }}
        QSplitter::handle:hover {{
            background-color: {ACCENT};
        }}
        QSplitter::handle:pressed {{
            background-color: {ACCENT};
        }}
    """