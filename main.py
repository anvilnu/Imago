# main.py
import sys
import os
import app_paths

# === EMPAQUETADO (.exe con PyInstaller) ======================================
# Estos dos bloques SOLO actuan dentro del ejecutable congelado; con
# "python main.py" (desarrollo) getattr(sys, "frozen", False) es False y no hacen
# nada. Ver Imago.spec y el Popen de ai/subproc.py.
#
# 1) Modo worker de IA: el .exe se relanza a SI MISMO como proceso hijo de
#    inferencia (ai/subproc.py lo lanza con la bandera --ai-worker). En ese modo
#    NO abre la GUI: hace de worker (host/puerto/authkey en argv) y termina.
if getattr(sys, "frozen", False) and len(sys.argv) >= 5 and sys.argv[1] == "--ai-worker":
    import multiprocessing
    multiprocessing.freeze_support()
    from ai.subproc_worker import main as _ai_worker_main
    sys.argv = [sys.argv[0]] + sys.argv[2:]   # deja host/puerto/authkey en argv[1..3]
    _ai_worker_main()
    sys.exit(0)

# 2) Recursos: los iconos viajan EMBEBIDOS en recursos_rc (rutas ":/icons/...", no
#    archivos sueltos). Aun asi fijamos el cwd a la base del bundle por si algun
#    otro recurso se cargara con ruta relativa.
if getattr(sys, "frozen", False):
    os.chdir(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)))

# === DIAGNÓSTICO DE CIERRES INESPERADOS ======================================
# Registra en "imago_crash.log" TODO lo que pueda tumbar o degradar Imago, para que
# un usuario pueda compartir el archivo si tiene problemas:
#   - Fallos graves a nivel C/Qt (segfault, access violation, abort) con la traza de
#     TODAS las hebras, vía faulthandler.
#   - Excepciones de Python no capturadas del hilo principal (sys.excepthook) Y de
#     hilos secundarios (threading.excepthook).
#   - Mensajes internos de Qt de nivel Critical/Fatal (qInstallMessageHandler, más
#     abajo tras importar Qt): un qFatal aborta, pero su texto explica el porqué.
# El log se ROTA al pasar de ~1 MB (se conserva una copia .old), así no crece sin
# límite. Es permanente (útil en distribución) y su coste en marcha es nulo: solo se
# escribe ante un fallo (más una línea de cabecera al arrancar).
import faulthandler
import traceback
import datetime
import tempfile
import platform as _platform
import threading as _threading
from i18n import t
# La carpeta del script es lo cómodo en desarrollo; si es de SOLO LECTURA
# (p. ej. en el sandbox de Flatpak), se usa una carpeta escribible del usuario.
def _ruta_log_crash():
    aqui = os.path.join(os.path.dirname(os.path.abspath(__file__)), "imago_crash.log")
    if os.access(os.path.dirname(aqui), os.W_OK):
        return aqui
    base = os.environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state")
    destino = os.path.join(base, "imago")
    try:
        os.makedirs(destino, exist_ok=True)
    except OSError:
        destino = tempfile.gettempdir()
    return os.path.join(destino, "imago_crash.log")

_LOG_CRASH = _ruta_log_crash()
# Rotación: si el log creció mucho, se guarda como .old y se empieza uno nuevo.
try:
    if os.path.exists(_LOG_CRASH) and os.path.getsize(_LOG_CRASH) > 1_000_000:
        try:
            os.replace(_LOG_CRASH, _LOG_CRASH + ".old")
        except OSError:
            pass
except OSError:
    pass
try:
    _crash_file = open(_LOG_CRASH, "a", buffering=1, encoding="utf-8")
    faulthandler.enable(file=_crash_file, all_threads=True)
except Exception:
    _crash_file = None

def _log_crash(texto):
    """Escribe en el log de crashes; un fallo al escribir jamás rompe nada."""
    try:
        if _crash_file is not None:
            _crash_file.write(texto)
            _crash_file.flush()
    except Exception:
        pass
    try:
        sys.__stderr__.write(texto)
    except Exception:
        pass

def _volcar_excepcion(cabecera, exc_type, exc_value, exc_tb):
    _log_crash(cabecera + "".join(traceback.format_exception(exc_type, exc_value, exc_tb)))

def _registrar_excepcion(exc_type, exc_value, exc_tb):
    _volcar_excepcion("\n===== EXCEPCIÓN NO CAPTURADA %s =====\n"
                      % datetime.datetime.now().isoformat(), exc_type, exc_value, exc_tb)

def _registrar_excepcion_hilo(args):
    # Excepciones no capturadas en hilos de Python (sys.excepthook solo cubre el
    # principal). Se ignora SystemExit (fin normal de un hilo).
    if args.exc_type is SystemExit:
        return
    _volcar_excepcion("\n===== EXCEPCIÓN NO CAPTURADA (hilo %s) %s =====\n"
                      % (getattr(args.thread, "name", "?"),
                         datetime.datetime.now().isoformat()),
                      args.exc_type, args.exc_value, args.exc_traceback)

sys.excepthook = _registrar_excepcion
_threading.excepthook = _registrar_excepcion_hilo

# Cabecera de sesión: contexto para interpretar un log compartido por un usuario.
try:
    import PySide6 as _pyside6
    _pyside_ver = _pyside6.__version__
except Exception:
    _pyside_ver = "?"
_log_crash("\n########## IMAGO · inicio %s ##########\nSO: %s | Python: %s | PySide6: %s\n"
           % (datetime.datetime.now().isoformat(), _platform.platform(),
              _platform.python_version(), _pyside_ver))
# =============================================================================

from PySide6.QtWidgets import (QApplication, QWidget, QPushButton,
                             QVBoxLayout, QHBoxLayout,
                             QTabWidget, QMenuBar,
                             QMainWindow, QSplitter,
                             QProxyStyle, QStyle, QStyleFactory)
from PySide6.QtGui import QAction
from PySide6.QtCore import Qt, QTimer, QEvent, QSettings, QFile

# Iconos EMBEBIDOS: recursos_rc.py (generado por generar_recursos.py a partir de
# la carpeta icons/) registra todos los PNG bajo ":/icons/...". Con solo
# importarlo quedan disponibles para toda la app; ya no se distribuye icons/.
import recursos_rc  # noqa: F401

# Mensajes internos de Qt: los de nivel Critical/Fatal van también al log de crashes
# (un qFatal aborta —lo pilla faulthandler— pero su texto explica la causa). Los de
# nivel Warning/Info/Debug siguen yendo solo a la terminal (no ensucian el log).
from PySide6.QtCore import qInstallMessageHandler as _qInstallMessageHandler, QtMsgType as _QtMsgType
def _handler_mensajes_qt(mode, context, message):
    _nivel = {_QtMsgType.QtCriticalMsg: "Qt CRITICAL",
              _QtMsgType.QtFatalMsg: "Qt FATAL"}.get(mode)
    if _nivel is not None:
        _log_crash("\n===== %s %s =====\n%s\n"
                   % (_nivel, datetime.datetime.now().isoformat(), message))
    else:
        try:
            sys.__stderr__.write(message + "\n")   # Warning/Info/Debug: solo terminal
        except Exception:
            pass
_qInstallMessageHandler(_handler_mensajes_qt)

from widgets.canvas import Canvas
from tools.bucket_tool import BucketTool
from widgets.custom_titlebar import (CustomTitleBar, FramelessResizeFilter,
                                     imago_warning)
from widgets.history_panel import HistoryPanel
from tools.draw_tools import PenTool, EraserTool, PencilTool, ReplaceColorTool
from tools.eyedropper_tool import EyedropperTool
from tools.selection_tools import RectSelectTool, EllipseSelectTool, LassoSelectTool
from tools.hand_tool import HandTool
from tools.magic_wand_tool import MagicWandTool
from tools.clone_tool import CloneTool
from tools.text_tool import TextTool
from tools.pen_path_tool import PenPathTool
from tools.line_curve_tool import LineCurveTool
from tools.measure_tool import MeasureTool
from tools.airbrush_tool import AirbrushTool
from tools.gradient_tool import GradientTool
from tools.smudge_tool import SmudgeTool
from tools.dodge_burn_tool import DodgeBurnTool
from tools.sponge_tool import SpongeTool
from tools.liquify_tool import LiquifyTool
from tools.heal_tool import HealTool
from tools.crop_tool import CropTool
from widgets.ruler_overlay import RulerOverlay
# Mixins con las acciones de los menús (IA, Ajustes/Efectos, Archivo, Edición,
# Imagen/Capas, Ver), los handlers de la barra de opciones, la construcción de
# la UI y los cursores: viven en el paquete ventana/ para aligerar main.py;
# MainWindow los hereda y todo sigue conectándose vía self.* igual que antes.
from ventana.menu_ia import AccionesMenuIA
from ventana.menu_ajustes import AccionesMenuAjustes
from ventana.opciones_herramientas import OpcionesHerramientas
from ventana.menu_archivo import AccionesMenuArchivo, ResultadoGuardado
from ventana.menu_edicion import AccionesMenuEdicion
from ventana.menu_imagen_capas import AccionesMenuImagenCapas
from ventana.menu_ver import AccionesMenuVer
from ventana.construccion_ui import ConstruccionUI
from ventana.cursores import CursoresHerramientas
from widgets.tab_thumbnails import TabThumbnailBar
from widgets.canvas_scroll import CanvasScrollArea
import theme

# Utilidades compartidas (iconos temados, carga con orientación EXIF,
# miniaturas de lienzo): movidas a utilidades.py para que los mixins de
# MainWindow puedan importarlas sin crear un import circular con main.py.
# cargar_imagen_orientada se reexporta por compatibilidad: es EL cargador de
# imágenes de disco de Imago y siempre se ha referenciado como "de main.py".
from utilidades import (crear_icono,
                        cargar_imagen_orientada)   # noqa: F401


class MainWindow(AccionesMenuIA, AccionesMenuAjustes, OpcionesHerramientas,
                 AccionesMenuArchivo, AccionesMenuEdicion, AccionesMenuImagenCapas,
                 AccionesMenuVer, ConstruccionUI, CursoresHerramientas,
                 QMainWindow):  # ← QMainWindow en vez de QWidget
    FILTRO_PROYECTO = "Proyecto Imago (*.imago)"
    FILTRO_EXPORTACION = "PNG Image (*.png);;JPEG Image (*.jpg *.jpeg);;BMP Image (*.bmp)"
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Imago")
        # Ventana SIN MARCO: usamos barra de título propia (igual en Windows y Linux)
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        # Almacén de preferencias (debe existir antes de restaurar geometría).
        # app_paths.settings() = registro nativo normalmente, o Imago.ini junto al
        # .exe en modo portable (ver app_paths.py).
        self.settings = app_paths.settings()
        from i18n import set_language
        set_language(app_paths.idioma(self.settings))
        
        # Tamaño de arranque por defecto (primer uso): suficiente para que los
        # paneles flotantes no se monten sobre el lienzo. Si hay geometría
        # guardada de una sesión anterior, restore_preferences la sobrescribe.
        self.setGeometry(100, 100, 1330, 915)
        self.setAcceptDrops(True)  # arrastrar y soltar imágenes para abrirlas

        if QFile.exists(":/icons/imago.png"):
            self.setWindowIcon(crear_icono(":/icons/imago.png"))

        # Aplicamos tema oscuro a la barra de título nativa de Windows 11
        self._apply_dark_titlebar()

        self.last_opened_dir = self.settings.value("last_opened_dir", "")

        # =========================================================================
        # BARRA DE TÍTULO NATIVA: metemos icono + nombre + pestañas con setMenuWidget
        # =========================================================================
        title_widget = QWidget()
        # 1: Dibujamos la línea fina aquí para que quede justo debajo de las pestañas
        title_widget.setStyleSheet(f"background: transparent; border-bottom: 1px solid {theme.BORDER_SOFT};")
        title_layout = QHBoxLayout(title_widget)
        title_layout.setContentsMargins(2, 0, 0, 1)
        title_layout.setSpacing(0)

        # Las pestañas ocupan el espacio restante
        self.tabs = QTabWidget()
        
        # 2: Forzamos la altura exacta de las pestañas (30px de alto + 2px de margin-top)
        # Esto destruye el espacio muerto del 'pane' interno de Qt y pega la pestaña a la línea.
        self.tabs.setFixedHeight(32)
        
        # AÑADIDO: Corta los nombres largos con "..." si no caben en el ancho estipulado
        self.tabs.setElideMode(Qt.TextElideMode.ElideRight)
        
        self.tabs.setTabsClosable(True)
        self.tabs.setTabPosition(QTabWidget.TabPosition.North)
        self.tabs.setStyleSheet("""
            QTabWidget {
                border: none;
                background: transparent;
            }
            QTabWidget::pane {
                border: none;
                background: transparent;
            }
            QTabBar {
                /* EL TRUCO: Desactiva por completo la línea base interna de Qt */
                qproperty-drawBase: 0; 
                background: transparent;
                border: none;
            }
            QTabBar::tab {
                background: #3a3a3a;
                color: #b0b0b0;
                height: 30px;
                padding-left: 10px;
                padding-right: 28px;
                margin-right: 2px;
                margin-top: 2px;
                font-family: 'Segoe UI', Arial;
                font-size: 11px;
                border: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                max-width: 80px;  /* AÑADIDO: Límite superior de tamaño 140 a las pestañas */
                min-width: 80px;   /* AÑADIDO: Límite inferior de tamaño 80 a las pestañas */
            }
            QTabBar::tab:selected {
                background: #1a4f7c; /* Pestaña activa en azul */
                color: white;
                font-weight: bold;
                border-top: 2px solid #007acc; /* Filo superior brillante */
            }
            QTabBar::tab:hover:!selected { 
                background: #4a4a4a; 
                color: white; 
            }
        """)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self.on_tab_changed)
        # ── La barra de pestañas clásica se sustituye por la tira de miniaturas (más
        #    abajo). Mantenemos self.tabs como almacén de datos / control de índice,
        #    pero oculto (no se muestra ninguna barra de pestañas).
        self.tabs.setParent(self)
        self.tabs.hide()

        # =========================================================================
        # WIDGET CENTRAL
        # =========================================================================
        central = QWidget()
        central.setObjectName("RootCentral")
        # Borde fino (1px) de la ventana sin marco, para que el contorno se vea bien
        central.setStyleSheet(f"#RootCentral {{ background-color: {theme.BG_WINDOW}; border: 1px solid {theme.BORDER}; }}")
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(1, 1, 1, 1)
        main_layout.setSpacing(0)

        # ── Barra de título propia (va la primera, arriba del todo) ──
        self.title_bar = CustomTitleBar(self, "Imago", ":/icons/imago.png")
        main_layout.addWidget(self.title_bar)
        # Redimensionado manual por bordes (ventana sin marco) + tracking de ratón
        central.setMouseTracking(True)
        self.setMouseTracking(True)
        self._resize_filter = FramelessResizeFilter(self)

        # Barra de menús
        self.custom_menu_bar = QMenuBar(self)
        self.custom_menu_bar.setStyleSheet(theme.menubar_qss())
        # ── Bloque superior: a la izquierda menús + barra de herramientas (apilados);
        #    en el centro la tira de miniaturas de documentos (abarca ese alto);
        #    a la derecha los botones de panel.
        top_block = QWidget()
        top_block.setStyleSheet(f"background-color: {theme.BG_DARK};")
        top_block_layout = QHBoxLayout(top_block)
        top_block_layout.setContentsMargins(0, 0, 0, 0)
        top_block_layout.setSpacing(8)

        left_col = QWidget()
        self._left_col_layout = QVBoxLayout(left_col)
        self._left_col_layout.setContentsMargins(0, 0, 0, 0)
        self._left_col_layout.setSpacing(0)
        self._left_col_layout.addWidget(self.custom_menu_bar)
        top_block_layout.addWidget(left_col)

        # Tira de miniaturas (ocupa el hueco libre entre menús y botones)
        self.thumbnail_bar = TabThumbnailBar(self)
        top_block_layout.addWidget(self.thumbnail_bar, stretch=1)

        # Botones de panel (Herramientas/Historial/Capas/Colores) a la derecha
        self.create_panel_toggle_buttons(top_block_layout)

        main_layout.addWidget(top_block)

        self.create_menus()
        self._crear_atajos_herramientas()

        # Plugins de terceros (ajustes/efectos): se cargan cuando el bucle de
        # eventos ya está en marcha y la ventana montada (por si algún aviso sale).
        QTimer.singleShot(0, self._cargar_plugins)

        QApplication.clipboard().dataChanged.connect(self.update_edit_actions_state)

        # Barra de herramientas fija (debajo del menú, dentro del bloque superior)
        self.create_fixed_toolbar()
        self._left_col_layout.addWidget(self.fixed_toolbar)

        # Barra de opciones dinámicas
        self.create_dynamic_options_bar()
        self.options_bar.setStyleSheet(theme.optionsbar_qss())
        main_layout.addWidget(self.options_bar)

        # ── Zona inferior: splitter horizontal raíz [herramientas | centro |
        #    columna derecha]. De momento solo aloja el centro; las celdas
        #    izquierda (Herramientas) y derecha (Capas/Historial/Color) se
        #    rellenan en fases posteriores de la migración a paneles empotrados.
        self.root_splitter = QSplitter(Qt.Horizontal)
        self.root_splitter.setObjectName("RootSplitter")
        self.root_splitter.setChildrenCollapsible(False)
        self.root_splitter.setStyleSheet(theme.splitter_qss())

        # Contenedor de lienzos (celda central del splitter)
        self.content_container = QWidget()
        self.content_layout = QVBoxLayout(self.content_container)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)
        self.root_splitter.addWidget(self.content_container)
        main_layout.addWidget(self.root_splitter, stretch=1)
        self.ruler_overlay = RulerOverlay(self.content_container)
        self.ruler_overlay.setGeometry(self.content_container.rect())
        self.ruler_overlay.raise_()  # Siempre por encima del lienzo
        # El área de contenido cambia de tamaño no solo al redimensionar la
        # ventana (resizeEvent), sino también al arrastrar el separador del
        # splitter raíz o al mostrar/ocultar paneles. Vigilamos su Resize para
        # re-sincronizar las reglas en todos esos casos (ver eventFilter).
        self.content_container.installEventFilter(self)
        # Estado GLOBAL de cuadrícula y reglas (compartido por todas las pestañas)
        self.global_show_grid = False
        self.global_grid_tile = 0    # mosaico de la cuadrícula (0 = sin él)
        self.global_show_rulers = False
        self.global_show_guides = True   # las guías se ven salvo que se oculten

        # Barra de estado (ayuda contextual a la izquierda; lecturas + zoom a la derecha)
        self._build_status_bar()
        self.status_bar.showMessage(t("status.init"))

        welcome_canvas = self.create_new_tab_canvas(800, 600, t("dlg.untitled"))
        # Solo ESTA pestaña (la del arranque) es candidata al autocierre
        welcome_canvas.is_welcome_canvas = True
        self.create_docks()

        self.status_bar.clearMessage()

        self.current_tool_name = "pen"

        # Establecer la herramienta inicial por el cauce oficial: así el
        # panel de herramientas, el desplegable de la barra dinámica, el
        # panel de opciones y el cursor arrancan todos sincronizados
        self.set_tool("pen")

        # Modo de arranque (ajuste, por defecto 'welcome'): 'welcome' muestra la
        # pantalla de inicio; 'blank' deja el lienzo en blanco recién creado. El
        # lienzo se crea siempre (los docks lo necesitan para construirse); en modo
        # bienvenida lo cerramos -> 0 pestañas -> pantalla de inicio. Lo expondremos
        # como opción en el menú Preferencias.
        if str(self.settings.value("startup_mode", "welcome")) == "welcome":
            self.close_tab(0)

        # Restaurar preferencias de la sesión anterior (paneles visibles,
        # cuadrícula, reglas, unidad). Diferido para que el layout y la primera
        # pestaña ya estén montados cuando apliquemos visibilidad y geometría.
        QTimer.singleShot(0, self.restore_preferences)

        # Autoguardado y recuperación ante fallos: copia de seguridad cada
        # 3 min de las pestañas con cambios sin guardar; si la sesión anterior no
        # se cerró bien, se ofrece recuperar al arrancar (tras montar la UI).
        from models.autosave import AutoSaveManager
        self.autosave = AutoSaveManager(self, interval_min=3)
        self.autosave.start()
        QTimer.singleShot(0, self._check_recovery)

    def _apply_dark_titlebar(self):
        """Activa el tema oscuro en la barra de título nativa de Windows 10/11"""
        try:
            import ctypes
            hwnd = int(self.winId())
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
                ctypes.byref(ctypes.c_int(1)), ctypes.sizeof(ctypes.c_int)
            )
        except Exception:
            pass  # En Linux/Mac simplemente no hace nada

    def update_edit_actions_state(self):
        """Activa/desactiva Cortar, Copiar, Pegar y compañía según el contexto:
        sin selección no se puede cortar/copiar; sin imagen en el portapapeles
        no se puede pegar; sin lienzo, nada de nada."""
        from PySide6.QtWidgets import QApplication
        canvas = self.get_current_canvas()
        has_canvas = canvas is not None
        has_sel = has_canvas and getattr(canvas, 'selection', None) is not None
        has_clip_img = has_canvas and not QApplication.clipboard().image().isNull()
        # La caja de hormigas de una capa de TEXTO (herramienta de mover) no
        # es una selección real, pero Deseleccionar también debe poder anularla.
        tool = getattr(canvas, 'current_tool', None) if has_canvas else None
        has_text_box = bool(tool is not None and hasattr(tool, 'text_box_active')
                            and tool.text_box_active())

        if hasattr(self, 'cut_action'):
            self.cut_action.setEnabled(has_sel)
            self.copy_action.setEnabled(has_sel)
            self.paste_action.setEnabled(has_clip_img)
            self.select_all_action.setEnabled(has_canvas)
            self.deselect_action.setEnabled(has_sel or has_text_box)
            # Recortar es ahora una HERRAMIENTA: disponible siempre que haya
            # lienzo (con selección, la caja arranca ajustada a ella)
            self.crop_action.setEnabled(has_canvas)
            self.paste_layer_action.setEnabled(has_clip_img)
            self.resize_action.setEnabled(has_canvas)
            self.copy_sel_shape_action.setEnabled(has_sel)
            self.delete_sel_action.setEnabled(has_sel)
            self.fill_sel_action.setEnabled(has_sel)
            self.invert_sel_action.setEnabled(has_sel)
            if hasattr(self, 'refine_menu'):
                self.refine_menu.setEnabled(has_sel)
            if hasattr(self, 'options_bar'):
                self.options_bar.set_refine_enabled(has_sel)
            self.paste_image_action.setEnabled(has_clip_img)
            has_shape = (has_canvas and getattr(type(canvas), 'selection_shape_clipboard', None) is not None)
            self.paste_sel_menu.menuAction().setEnabled(has_shape)
            has_layer = has_canvas and canvas.get_active_layer() is not None
            for _a in getattr(self, '_fx_actions', []):
                _a.setEnabled(has_layer)

            # Imagen → transformaciones (Tamaño del lienzo, Voltear, Girar):
            # solo tienen sentido con un lienzo abierto.
            self.canvas_size_action.setEnabled(has_canvas)
            self.flip_h_action.setEnabled(has_canvas)
            self.flip_v_action.setEnabled(has_canvas)
            self.rotate_cw_action.setEnabled(has_canvas)
            self.rotate_ccw_action.setEnabled(has_canvas)
            self.rotate_180_action.setEnabled(has_canvas)
            self.rotate_free_action.setEnabled(has_canvas)

            # Archivo → Cerrar: solo con un documento abierto.
            if hasattr(self, 'close_tab_action'):
                self.close_tab_action.setEnabled(has_canvas)

        # Menú Capas y menú IA: estado fino según el contexto.
        self.update_layer_menu_state()
        self.update_ai_menu_state()

    def update_layer_menu_state(self):
        """Habilita/deshabilita las acciones del menú Capas según el contexto,
        igual que los botones del panel de Capas: sin lienzo/capa, todo gris;
        'Eliminar capa' y 'Fusionar todas' requieren más de una capa; 'Fusionar
        hacia abajo' y 'Mover hacia abajo' requieren no estar en el fondo; 'Mover
        hacia arriba' requiere no estar arriba del todo. El resto solo necesita
        una capa activa."""
        acts = getattr(self, '_layer_menu_actions', None)
        if not acts:
            return
        canvas = self.get_current_canvas()
        if canvas is None or canvas.get_active_layer() is None:
            for act in acts.values():
                act.setEnabled(False)
            return

        total = len(canvas.layers)
        idx = canvas.active_layer_index

        # Disponibles siempre que haya una capa activa (los submenús Efectos y
        # Modo de fusión operan sobre la activa, así que basta con eso).
        for key in ("new", "duplicate", "group", "toggle_vis", "flip_h", "flip_v",
                    "rot_cw", "rot_ccw", "rot_180", "properties",
                    "fx_menu", "blend_menu"):
            if key in acts:
                acts[key].setEnabled(True)

        # Dependientes del número de capas y de la posición de la activa
        acts["remove"].setEnabled(total > 1)
        acts["flatten"].setEnabled(total > 1)
        # Fusionar exige además que la activa y la inferior estén VISIBLES
        # (mismo criterio que el botón del panel de Capas).
        from models.layer import visible_para_fusion
        acts["merge_down"].setEnabled(
            idx > 0 and visible_para_fusion(canvas.layers, idx)
            and visible_para_fusion(canvas.layers, idx - 1))
        # Fusionar los efectos en la capa: solo si la activa tiene efectos fx
        if "merge_fx" in acts:
            acts["merge_fx"].setEnabled(
                bool(getattr(canvas.layers[idx], "effects", None)))
        acts["move_up"].setEnabled(idx < total - 1)
        acts["move_down"].setEnabled(idx > 0)

        # ✂️ Máscara de recorte: necesita una capa debajo (la del fondo no se
        # recorta a nada); la marca refleja el estado de la capa activa.
        if "clip" in acts:
            acts["clip"].setEnabled(idx > 0)
            acts["clip"].setChecked(
                bool(getattr(canvas.layers[idx], "clipped", False)))

        # Máscara de capa: crear si no hay; "desde selección" requiere selección;
        # aplicar/eliminar requieren que la capa tenga máscara.
        if "mask_create" in acts:
            layer = canvas.get_active_layer_obj()
            has_mask = layer is not None and layer.has_mask()
            has_sel = canvas.selection is not None
            acts["mask_create"].setEnabled(not has_mask)
            acts["mask_from_sel"].setEnabled(not has_mask and has_sel)
            acts["mask_apply"].setEnabled(has_mask)
            acts["mask_remove"].setEnabled(has_mask)

    def update_view_menu_state(self):
        """Menú Ver: el zoom y las Guías necesitan un lienzo abierto (en la
        pantalla de bienvenida no tienen sentido). Las reglas, la cuadrícula y las
        unidades son ajustes de vista globales y se dejan siempre disponibles."""
        canvas = self.get_current_canvas()
        has_canvas = canvas is not None
        for nombre in ('zoom_in_action', 'zoom_out_action', 'zoom_fit_action',
                       'zoom_actual_action', 'guides_action', 'fullscreen_action'):
            act = getattr(self, nombre, None)
            if act is not None:
                act.setEnabled(has_canvas)

    def update_ai_menu_state(self):
        """Menú IA: cada efecto necesita una capa activa (imagen sobre la que
        operar); sin lienzo/capa se deshabilitan. Excepción: 'Crear panorama'
        parte de archivos sueltos y crea un documento nuevo, así que NO requiere
        lienzo. Mientras hay un trabajo de IA en curso todo queda deshabilitado
        (lo marca self._ai_busy desde _ai_set_busy). 'Gestionar modelos' no está
        en _ai_actions: se deja siempre disponible."""
        canvas = self.get_current_canvas()
        has_layer = canvas is not None and canvas.get_active_layer() is not None
        busy = getattr(self, '_ai_busy', False)
        pano = getattr(self, 'ai_pano_action', None)
        for act in getattr(self, '_ai_actions', []):
            if act is pano:
                act.setEnabled(not busy)  # panorama no requiere lienzo abierto
            else:
                act.setEnabled(has_layer and not busy)

    def create_new_tab_canvas(self, width, height, title, image_to_load=None, dpi=None, fill_color=None):
        canvas = Canvas(width, height)
        # Límite de pasos de deshacer (Preferencias). 0 = sin límite. Qt solo
        # permite fijarlo con la pila VACÍA, por eso se hace al crear el lienzo
        # (los documentos ya abiertos conservan el límite con el que nacieron).
        try:
            undo_limit = int(self.settings.value("undo_limit", 100))
        except (TypeError, ValueError):
            undo_limit = 100
        canvas.undo_stack.setUndoLimit(max(0, undo_limit))
        if dpi:
            canvas.dpi = float(dpi)

        # Heredar el estado global de cuadrícula y reglas
        canvas.show_grid = getattr(self, 'global_show_grid', False)
        canvas.grid_tile = getattr(self, 'global_grid_tile', 0)
        canvas.show_rulers = getattr(self, 'global_show_rulers', False)
        canvas.show_guides = getattr(self, 'global_show_guides', True)

        # Conservar los colores primario y secundario del documento activo
        current = self.get_current_canvas()
        if current is not None:
            canvas.brush_color = current.brush_color
            canvas.brush_color_secondary = current.brush_color_secondary

        # NUEVO: Forzar al nuevo lienzo a usar los valores actuales de la barra de opciones
        if hasattr(self, 'options_bar'):
            try:
                canvas.brush_size = int(self.options_bar.pen_size_box.currentText())
            except Exception:
                canvas.brush_size = 5
            if hasattr(self.options_bar, 'hardness_slider'):
                canvas.brush_hardness = self.options_bar.hardness_slider.value()
            if hasattr(self.options_bar, 'brush_opacity_slider'):
                canvas.brush_opacity = self.options_bar.brush_opacity_slider.value()
            if hasattr(self.options_bar, 'spacing_slider'):
                canvas.brush_spacing = self.options_bar.spacing_slider.value()
                
            if hasattr(self.options_bar, 'pattern_combo'):
                canvas.brush_pattern = self.options_bar.pattern_combo.currentData()
            else:
                canvas.brush_pattern = "solid"

            if hasattr(self.options_bar, 'bucket_pattern_combo'):
                canvas.bucket_pattern = self.options_bar.bucket_pattern_combo.currentData()
            else:
                canvas.bucket_pattern = "solid"

            if hasattr(self.options_bar, 'pen_selection_check'):
                canvas.pen_selection_mode = self.options_bar.pen_selection_check.isChecked()

            if hasattr(self.options_bar, 'brush_antialias_check'):
                canvas.brush_antialias = self.options_bar.brush_antialias_check.isChecked()

        canvas.eraser_hardness = 100
        canvas.eraser_spacing = 10

        if image_to_load:
            canvas.load_image_into_layer(image_to_load)
        elif fill_color is not None:
            canvas.layers[0].image.fill(fill_color)
        else:
            canvas.layers[0].image.fill(Qt.white)

        # Conexión del historial (Paso anterior)
        canvas.undo_stack.indexChanged.connect(lambda _: self._safe_update_undo_redo())

        # SOLUCIÓN: Le pasamos al lienzo una función callback para que la llame 
        # cada vez que el usuario haga zoom con la rueda del ratón
        canvas.zoom_changed_callback = self.update_status_bar_zoom
        canvas.cursor_moved_callback = self.update_cursor_position
        # Recorte: dimensiones en vivo en la barra de opciones y reencuadre
        # de la vista tras aplicar (mismo comportamiento que el menú Imagen)
        canvas.crop_changed_callback = (
            lambda rect: self.options_bar.set_crop_info(rect)
            if hasattr(self, 'options_bar') else None)
        canvas.crop_applied_callback = self.fit_canvas_to_screen

        scroll_area = CanvasScrollArea()
        scroll_area.setStyleSheet(f"background-color: {theme.BG_TILE}; border: none;")
        scroll_area.setAlignment(Qt.AlignCenter)
        scroll_area.setWidget(canvas)
        scroll_area.canvas = canvas

        dummy_tab_marker = QWidget()
        dummy_tab_marker.canvas = canvas
        dummy_tab_marker.scroll_area = scroll_area

        index = self.tabs.addTab(dummy_tab_marker, title)
        
        # ✕ BOTÓN DE CIERRE PERSONALIZADO E INMUNE A LOS BUGS DE QT CSS
        close_btn = QPushButton("✕")
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {theme.TEXT_DIM};
                border: none;
                font-family: 'Segoe UI', Arial;
                font-size: 10px;
                font-weight: bold;
                width: 16px;
                height: 16px;
            }}
            QPushButton:hover {{
                color: {theme.DANGER}; /* La X se vuelve roja fina al pasar el ratón */
                background-color: rgba(255, 255, 255, 0.15); /* Destello sutil moderno */
                border-radius: 3px;
            }}
        """)
        # Conectamos de forma segura buscando dinámicamente el índice real de la pestaña
        close_btn.clicked.connect(lambda checked=False, m=dummy_tab_marker: self.close_tab(self.tabs.indexOf(m)))
        # Colocamos el botón en el lado derecho de la pestaña nativamente
        self.tabs.tabBar().setTabButton(index, self.tabs.tabBar().ButtonPosition.RightSide, close_btn)

        self.tabs.setCurrentIndex(index)
        return canvas

    def on_tab_changed(self, index):
        # Un overlay no puede sobrevivir al cambio de documento: cancelar
        # restaura su preview en el lienzo de origen antes de mostrar el nuevo.
        new_marker = self.tabs.widget(index) if index >= 0 else None
        new_canvas = getattr(new_marker, "canvas", None)
        panel = getattr(self, "_active_adjustment_overlay", None)
        if panel is not None and getattr(panel, "canvas", None) is not new_canvas:
            panel.reject()

        # Primero limpiamos siempre el layout de restos visuales
        for i in reversed(range(self.content_layout.count())): 
            widget_to_remove = self.content_layout.itemAt(i).widget()
            if widget_to_remove:
                widget_to_remove.setParent(None)

        if index == -1:
            # ESTADO DE BLOQUEO: No hay ningún lienzo abierto
            self.setWindowTitle("Imago")
            if hasattr(self, 'thumbnail_bar'): self.thumbnail_bar.rebuild()
            
            self.content_layout.addWidget(self._build_welcome_widget())

            self.save_action.setEnabled(False)
            self.save_as_action.setEnabled(False)
            self.print_action.setEnabled(False)
            self.export_menu.menuAction().setEnabled(False)
            self.export_pdf_action.setEnabled(False)
            self.export_ora_action.setEnabled(False)
            self.preview_anim_action.setEnabled(False)
            self.export_anim_action.setEnabled(False)
            self.undo_action.setEnabled(False)
            self.redo_action.setEnabled(False)
            if hasattr(self, 'color_action'): self.color_action.setEnabled(False)
            if hasattr(self, 'options_bar'): self.options_bar.setEnabled(False)
            
            if hasattr(self, 'tools_panel'): self.tools_panel.setEnabled(False)
            if hasattr(self, 'layers_panel'): self.layers_panel.setEnabled(False)
            if hasattr(self, 'history_view'): self.history_view.setEnabled(False)
            if hasattr(self, 'colors_panel'): self.colors_panel.setEnabled(False)

            self.update_edit_actions_state()
            self.update_view_menu_state()

            # Reglas en la pantalla de bienvenida: muestra las bandas si están
            # activas (respeta el toggle). _sync decide el modo según haya lienzo.
            self._sync_ruler_overlay_geometry()
            QTimer.singleShot(15, self._sync_ruler_overlay_geometry)

            if hasattr(self, 'tool_help_label'):
                self.tool_help_label.setText(t("status.no_canvas"))
            self._update_status_readouts()
            self.update_cursor_position(None)
            self.status_bar.clearMessage()
            return

        # ESTADO ACTIVO: Hay un lienzo válido, devolvemos la vida a la interfaz
        self._update_window_title()
        
        self.save_action.setEnabled(True)
        self.save_as_action.setEnabled(True)
        self.print_action.setEnabled(True)
        self.export_menu.menuAction().setEnabled(True)
        self.export_pdf_action.setEnabled(True)
        self.export_ora_action.setEnabled(True)
        self.preview_anim_action.setEnabled(True)
        self.export_anim_action.setEnabled(True)
        if hasattr(self, 'color_action'): self.color_action.setEnabled(True)
        if hasattr(self, 'options_bar'): self.options_bar.setEnabled(True)
        
        if hasattr(self, 'tools_panel'): self.tools_panel.setEnabled(True)
        if hasattr(self, 'layers_panel'): self.layers_panel.setEnabled(True)
        if hasattr(self, 'colors_panel'): self.colors_panel.setEnabled(True)

        # Cargar los datos del lienzo seleccionado
        marker = self.tabs.widget(index)
        if marker and hasattr(marker, 'scroll_area'):
            self.content_layout.addWidget(marker.scroll_area)
            canvas = marker.canvas
            
            self.status_bar.clearMessage()
            self._refresh_tool_help()
            self._update_status_readouts()

            # Actualizar panel de capas
            if hasattr(self, 'layers_panel'):
                self.layers_panel.canvas = canvas 
                self.layers_panel.update_layer_list()

            # Actualizar el panel de historial: HistoryPanel no admite re-acoplado,
            # así que lo RECREAMOS para el nuevo undo_stack y lo reemplazamos DENTRO
            # de su contenedor (debajo de la cabecera). El contenedor sigue en el
            # splitter, así que no hay que tocar tamaños ni visibilidad.
            if hasattr(self, 'history_container') and hasattr(self, 'history_view'):
                old_panel = self.history_view
                if hasattr(old_panel, 'detach'):
                    old_panel.detach()

                new_panel = HistoryPanel(canvas, self)
                new_panel.setEnabled(True)
                self.history_container.layout().replaceWidget(old_panel, new_panel)
                old_panel.setParent(None)
                old_panel.deleteLater()
                self.history_view = new_panel

            if hasattr(self, 'colors_panel'):
                self.colors_panel.sync_from_canvas(canvas)

            canvas.selection_changed_callback = self.update_edit_actions_state
            # Para que al soltar ESPACIO el cursor vuelva al de la herramienta
            canvas.cursor_restore_callback = self.update_canvas_cursor
            # Sincronizar el botón de Guías cuando cambian (deshacer/rehacer)
            canvas.guides_changed_callback = self._on_guides_changed
            self.update_edit_actions_state()
            self.update_view_menu_state()

            self.grid_action.setChecked(self.global_show_grid)
            self.rulers_action.setChecked(self.global_show_rulers)
            # Las guías son POR DOCUMENTO: el botón refleja el estado del lienzo
            # activo, no un estado global.
            self.guides_action.blockSignals(True)
            self.guides_action.setChecked(getattr(canvas, 'show_guides', True))
            self.guides_action.blockSignals(False)

            canvas.ruler_overlay = self.ruler_overlay
            self.ruler_overlay.attach(marker.scroll_area, canvas)
            self.ruler_overlay.raise_()
            # Reajustar la geometría tras el cambio de pestaña (el área pudo cambiar)
            QTimer.singleShot(15, self._sync_ruler_overlay_geometry)

            # Refrescar estados visuales comunes
            self.update_undo_redo_actions_state()
            QTimer.singleShot(0, lambda c=canvas: self._restore_or_fit_canvas_zoom(c))
            self.update_tab_tooltips()
            if hasattr(self, 'thumbnail_bar'): self.thumbnail_bar.rebuild()

            # NUEVO: Forzamos al nuevo lienzo enfocado a adoptar la herramienta activa de la UI
            if hasattr(self, 'current_tool_name'):
                self.set_tool(self.current_tool_name)

            # RECOLECCIÓN Y SINCRONIZACIÓN DE OPCIONES (Evita el UnboundLocalError)
            if hasattr(self, 'options_bar') and hasattr(self.options_bar, 'sync_all_options'):
                # Leemos de forma segura los atributos específicos que este lienzo guardó
                size = getattr(canvas, 'brush_size', 5)
                hardness = getattr(canvas, 'brush_hardness', 100)
                spacing = getattr(canvas, 'brush_spacing', 10)
                pattern = getattr(canvas, 'brush_pattern', "solid")
                bucket_pattern = getattr(canvas, 'bucket_pattern', "solid")
                ehard = getattr(canvas, 'eraser_hardness', 100) # ← NUEVO
                espac = getattr(canvas, 'eraser_spacing', 10)   # ← NUEVO
                antialias = getattr(canvas, 'brush_antialias', True)

                self.options_bar.sync_all_options(size, hardness, spacing, pattern, ehard, espac, bucket_pattern, antialias) # ← ACTUALIZADO
                self.update_canvas_cursor() # ← AÑADIDO

        canvas.setFocus()

    def get_current_canvas(self):
        marker = self.tabs.currentWidget()
        if marker and hasattr(marker, 'canvas'):
            return marker.canvas
        return None

    def get_current_scroll(self):
        marker = self.tabs.currentWidget()
        if marker and hasattr(marker, 'scroll_area'):
            return marker.scroll_area
        return None

    def open_fullscreen_view(self):
        """Muestra la imagen compuesta del lienzo activo a PANTALLA COMPLETA (solo
        la imagen, para revisar: con zoom y desplazamiento). No hace nada si no hay
        documento abierto. render_flat_image() NO modifica el documento."""
        canvas = self.get_current_canvas()
        if canvas is None:
            return
        image = canvas.render_flat_image(Qt.transparent)
        from widgets.fullscreen_viewer import FullScreenViewer
        # Se guarda la referencia (además del padre) para que no lo recoja el GC.
        self._fullscreen_viewer = FullScreenViewer(image, self)
        self._fullscreen_viewer.showFullScreen()
        self._fullscreen_viewer.activateWindow()
        self._fullscreen_viewer.setFocus()

    def _safe_update_undo_redo(self):
        try:
            if not self.isVisible():
                return
            self.update_undo_redo_actions_state()
            # Un undo/redo puede cambiar el tamaño base del lienzo (recortar,
            # cambiar tamaño...) sin pasar por el flujo de zoom, dejando la vista
            # a tamaño real aunque antes estuviera ajustada. Refrescamos las
            # lecturas y, sobre todo, el estado del botón 'Ajustar a la ventana'
            # (si no, quedaba apagado pese a no estar ya ajustada la imagen).
            self.update_status_bar_zoom()
        except RuntimeError:
            pass  # El widget ya fue destruido, ignoramos silenciosamente

    def menuBar(self):
        return self.custom_menu_bar

    def _registrar_plugin_overlay(self, tipo, clave, dialog_cls, titulo=None, icono=None):
        """Da de alta un ajuste/efecto de plugin en su submenú Plugins.

        Lo llama la API de plugins (ImagoPluginAPI.registrar_ajuste/efecto). El
        ajuste/efecto se abre por la MISMA vía que los nativos (_open_adjustment ->
        panel overlay con preview, undo y respeto de la selección) y se habilita/
        deshabilita por contexto junto al resto (self._fx_actions).
        tipo: "ajuste" -> submenú de Ajustes; "efecto" -> submenú de Efectos."""
        texto = titulo or getattr(dialog_cls, "title", clave)
        if tipo == "ajuste":
            menu = self.adjust_plugins_menu
            icono_def = ":/icons/adjust.png"
        else:
            menu = self.effects_plugins_menu
            icono_def = ":/icons/fx_blur.png"
        ruta_icono = icono or icono_def
        if not QFile.exists(ruta_icono):
            ruta_icono = icono_def
        act = QAction(texto, self)
        if QFile.exists(ruta_icono):
            act.setIcon(crear_icono(ruta_icono))
        act.triggered.connect(lambda checked=False, dc=dialog_cls: self._open_adjustment(dc))
        menu.addAction(act)
        self._fx_actions.append(act)   # se activa/desactiva por contexto con el resto
        # Icono para el panel de Historial (basename; cae a adjust.png si no existe).
        self._history_icons[texto.replace("...", "").replace("&", "").strip()] = \
            ruta_icono.rsplit("/", 1)[-1]
        menu.menuAction().setVisible(True)   # el submenú estaba oculto si no había plugins

    def _cargar_plugins(self):
        """Carga los plugins de terceros tras montar la UI. Tolerante a fallos: un
        plugin roto se registra en imago_crash.log y no impide arrancar el resto."""
        try:
            from plugin_manager import PluginManager
            self.plugin_manager = PluginManager(self, log=_log_crash)
            self.plugin_manager.cargar_todos()
        except Exception:
            import traceback
            _log_crash("[plugins] Fallo general al cargar plugins:\n%s\n"
                       % traceback.format_exc())

    def open_preferences(self):
        from help_dialogs import PreferencesDialog
        PreferencesDialog(self).exec()

    def reiniciar_app(self):
        """Cierra Imago (con su guardado/limpieza normal de closeEvent) y lo vuelve
        a lanzar. Solo relanza si el cierre se acepta: si hay cambios sin guardar y
        el usuario cancela el cierre, NO se reinicia (evita dos instancias)."""
        import sys
        from PySide6.QtCore import QProcess
        if getattr(sys, "frozen", False):
            programa, args = sys.executable, sys.argv[1:]   # el .exe ya es argv[0]
        else:
            programa, args = sys.executable, sys.argv       # python + main.py [...]
        if self.close():
            QProcess.startDetached(programa, args)

    def open_manual(self):
        from help_dialogs import ManualDialog
        ManualDialog(self).exec()

    def open_shortcuts(self):
        from help_dialogs import ShortcutsDialog
        ShortcutsDialog(self).exec()

    def open_plugin_guide(self):
        from help_dialogs import PluginGuideDialog
        PluginGuideDialog(self).exec()

    def open_about(self):
        from help_dialogs import AboutDialog
        AboutDialog(self).exec()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(10, self._fit_if_zoom_mode)
        # El overlay de reglas se reajusta DESPUÉS de que el layout se asiente,
        # si no mide un tamaño intermedio y las reglas salen cortadas a media
        # pantalla
        QTimer.singleShot(15, self._sync_ruler_overlay_geometry)

    def eventFilter(self, obj, event):
        """Re-sincroniza las reglas cuando el área de contenido cambia de tamaño
        por una vía distinta del resizeEvent de la ventana: arrastre del separador
        del splitter raíz o mostrar/ocultar paneles. El overlay es hijo de
        content_container, así que basta con reajustar su geometría a la nueva."""
        if obj is getattr(self, 'content_container', None) and \
                event.type() == QEvent.Type.Resize:
            self._sync_ruler_overlay_geometry()
        return super().eventFilter(obj, event)

    def _sync_ruler_overlay_geometry(self):
        """Ajusta el overlay de reglas al tamaño REAL del área de contenido.
        Además, cuando las reglas están activas, aplica un margen al área de
        contenido para que el lienzo se desplace y no quede tapado por ellas."""
        if hasattr(self, 'ruler_overlay') and hasattr(self, 'content_container'):
            # Sin lienzo (pantalla de bienvenida): el overlay muestra solo las
            # bandas si las reglas están activas; con lienzo, modo normal.
            no_canvas = self.get_current_canvas() is None
            self.ruler_overlay.set_empty_mode(
                no_canvas and getattr(self, 'global_show_rulers', False))
            self.ruler_overlay.setGeometry(self.content_container.rect())
            self.ruler_overlay.raise_()
            self.ruler_overlay.update()
            # Si hay un panel overlay de ajuste abierto, mantenerlo POR ENCIMA de
            # las reglas (que se acaban de re-elevar), para que no lo tapen.
            ov = getattr(self, '_active_adjustment_overlay', None)
            if ov is not None:
                ov.raise_()
            # Empujar el contenido (el lienzo o la bienvenida) tras las reglas
            rs = self.ruler_overlay.RULER_SIZE if getattr(self, 'global_show_rulers', False) else 0
            self.content_layout.setContentsMargins(rs, rs, 0, 0)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            QTimer.singleShot(10, self._fit_if_zoom_mode)

    def close_tab(self, index):
        if index == -1: return
        marker = self.tabs.widget(index)
        # La preview no forma parte aún del historial: restaurarla ANTES de
        # comprobar/guardar evita publicar por accidente píxeles provisionales.
        canvas_objetivo = getattr(marker, "canvas", None)
        cancel_overlay = getattr(self, "_cancel_overlay_for_canvas", None)
        if canvas_objetivo is not None and callable(cancel_overlay):
            cancel_overlay(canvas_objetivo)
        from models.document_state import documento_pendiente
        if (marker and hasattr(marker, 'canvas')
                and documento_pendiente(marker.canvas)):
            from PySide6.QtWidgets import QMessageBox
            self.tabs.setCurrentIndex(index)
            nombre = self.tabs.tabText(index)
            resp = imago_warning(
                self, t("msg.unsaved.title"),
                t("msg.unsaved.text", nombre=nombre),
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel
            )
            if resp == QMessageBox.Save:
                resultado = self.save_file()
                # Defensa doble: el método debe confirmar éxito Y el lienzo debe
                # haber quedado realmente limpio (incluida una recuperación).
                if (resultado is not ResultadoGuardado.EXITO
                        or documento_pendiente(marker.canvas)):
                    return
            elif resp == QMessageBox.Cancel:
                return
        self._retirar_y_destruir_pestana(index)
        if hasattr(self, 'thumbnail_bar'): self.thumbnail_bar.rebuild()
        self._update_window_title()

    def _retirar_y_destruir_pestana(self, index):
        """Retira una pestaña y libera todos los objetos de su documento.

        QTabWidget.removeTab() solo oculta el widget de la página: el marcador
        sigue perteneciendo a su QStackedWidget. El scroll y el lienzo, además,
        viven fuera de ese marcador. Por eso los tres se destruyen de forma
        explícita tras cancelar cualquier trabajo que todavía los use.
        """
        marker = self.tabs.widget(index)
        if marker is None:
            return False

        canvas = getattr(marker, "canvas", None)
        scroll_area = getattr(marker, "scroll_area", None)

        cancel_overlay = getattr(self, "_cancel_overlay_for_canvas", None)
        if canvas is not None and callable(cancel_overlay):
            cancel_overlay(canvas)
        cancel_ai = getattr(self, "_ai_cancel_for_canvas", None)
        if canvas is not None and callable(cancel_ai):
            cancel_ai(canvas)

        # Las herramientas con objetos flotantes conservan imágenes auxiliares.
        # Cancelarlas antes de destruir el lienzo evita dejar esos buffers vivos.
        tool = getattr(canvas, "current_tool", None)
        if getattr(tool, "editing", False) and hasattr(tool, "_cancel_edit"):
            tool._cancel_edit()

        tab_bar = self.tabs.tabBar() if hasattr(self.tabs, "tabBar") else None
        close_btn = None
        if tab_bar is not None:
            close_btn = tab_bar.tabButton(index, tab_bar.ButtonPosition.RightSide)

        self.tabs.removeTab(index)

        # Si era la última pestaña, on_tab_changed(-1) no sustituye los
        # paneles por los de otro documento: retirar sus referencias expresamente.
        layers_panel = getattr(self, "layers_panel", None)
        if layers_panel is not None and getattr(layers_panel, "canvas", None) is canvas:
            if hasattr(layers_panel, "detach_canvas"):
                layers_panel.detach_canvas()
            else:
                layers_panel.canvas = None

        history_view = getattr(self, "history_view", None)
        if history_view is not None and getattr(history_view, "canvas", None) is canvas:
            if hasattr(history_view, "detach"):
                history_view.detach()
            else:
                history_view.canvas = None
                history_view.undo_stack = None

        ruler_overlay = getattr(self, "ruler_overlay", None)
        if ruler_overlay is not None and getattr(ruler_overlay, "canvas", None) is canvas:
            ruler_overlay.set_empty_mode(True)

        if canvas is not None:
            for callback in (
                    "zoom_changed_callback", "cursor_moved_callback",
                    "crop_changed_callback", "crop_applied_callback",
                    "selection_changed_callback", "cursor_restore_callback",
                    "guides_changed_callback", "layers_changed_callback",
                    "color_picked_callback"):
                if hasattr(canvas, callback):
                    setattr(canvas, callback, None)
            if hasattr(canvas, "ruler_overlay"):
                canvas.ruler_overlay = None
            if hasattr(canvas, "current_tool"):
                canvas.current_tool = None
            if hasattr(canvas, "_saved_tool"):
                canvas._saved_tool = None

        if close_btn is not None:
            try:
                close_btn.clicked.disconnect()
            except (RuntimeError, TypeError):
                pass
            close_btn.deleteLater()

        if scroll_area is not None:
            if hasattr(scroll_area, "takeWidget"):
                scroll_area.takeWidget()
            if hasattr(scroll_area, "canvas"):
                scroll_area.canvas = None
            frame_overlay = getattr(scroll_area, "_frame_overlay", None)
            if frame_overlay is not None:
                frame_overlay.canvas = None
            scroll_area.deleteLater()

        marker.canvas = None
        marker.scroll_area = None
        if canvas is not None and hasattr(canvas, "deleteLater"):
            canvas.deleteLater()
        if hasattr(marker, "deleteLater"):
            marker.deleteLater()
        return True

    def _update_window_title(self):
        """Pone el nombre del documento activo en el título de la ventana."""
        idx = self.tabs.currentIndex()
        if idx == -1:
            self.setWindowTitle("Imago")
        else:
            self.setWindowTitle(f"{self.tabs.tabText(idx)} - Imago")

    def set_tool(self, tool_name):
        """Define la herramienta activa global y la asigna al lienzo actual"""
        self.current_tool_name = tool_name  # 🌟 NUEVO: Guardamos la selección globalmente
        self._refresh_tool_help()

        if hasattr(self, 'options_bar'): self.options_bar.show_panel_for_tool(tool_name)
        canvas = self.get_current_canvas()
        if not canvas: return

        # Si la herramienta saliente tiene una edición de texto en curso,
        # la confirmamos antes de cambiar (no perder lo escrito).
        old_tool = getattr(canvas, 'current_tool', None)

        # (Eliminada la antigua lógica de text_payload que convertía texto en selección flotante
        # al cambiar a la herramienta Mover, ya que ahora usamos TextLayer verdaderas).

        if old_tool is not None and hasattr(old_tool, 'finish_editing'):
            old_tool.finish_editing()   # no-op si el editor ya se cerró

        canvas.reset_view_margins()  # Limpiar los márgenes de la herramienta anterior

        if tool_name == "pen": canvas.current_tool = PenTool(canvas)
        elif tool_name == "eraser": canvas.current_tool = EraserTool(canvas)
        elif tool_name == "bucket":
            canvas.current_tool = BucketTool(canvas)
            if hasattr(self, "options_bar") and hasattr(self.options_bar, "bucket_tolerance_slider"):
                canvas.bucket_tolerance = self.options_bar.bucket_tolerance_slider.value()
                canvas.bucket_contiguous = self.options_bar.bucket_contiguous_check.isChecked()
                canvas.bucket_antialias = self.options_bar.bucket_antialias_check.isChecked()
                canvas.bucket_sample_all = self.options_bar.bucket_sample_all_check.isChecked()
                canvas.bucket_expand = self.options_bar.bucket_expand_slider.value()
        elif tool_name == "pencil": canvas.current_tool = PencilTool(canvas)        # ← AÑADIR
        elif tool_name == "eyedropper":
            canvas.current_tool = EyedropperTool(canvas)
            if hasattr(self, "options_bar") and hasattr(self.options_bar, "eyedropper_size_combo"):
                canvas.eyedropper_sample_size = self.options_bar.eyedropper_size_combo.currentData()
                canvas.eyedropper_sample_all = (self.options_bar.eyedropper_source_combo.currentData() == "all")
        elif tool_name == "select_rect":
            canvas.current_tool = RectSelectTool(canvas)
            self._sync_selection_options(canvas)
        elif tool_name == "select_ellipse":
            canvas.current_tool = EllipseSelectTool(canvas)
            self._sync_selection_options(canvas)
        elif tool_name == "select_lasso":
            canvas.current_tool = LassoSelectTool(canvas)
            self._sync_selection_options(canvas)
        elif tool_name == "move":
            mode = self.options_bar.move_mode_selector.currentData() if (hasattr(self, 'options_bar') and hasattr(self.options_bar, 'move_mode_selector')) else "selection"
            self.update_active_move_mode(mode)
        elif tool_name == "hand": canvas.current_tool = HandTool(canvas)
        elif tool_name == "magic_wand":
            canvas.current_tool = MagicWandTool(canvas)
            # Sincronizar las opciones del panel en el canvas (la herramienta
            # las lee de ahí EN VIVO, como el cubo)
            if hasattr(self, 'options_bar') and hasattr(self.options_bar, 'wand_tolerance_slider'):
                canvas.magic_wand_tolerance = self.options_bar.wand_tolerance_slider.value()
                canvas.magic_wand_contiguous = self.options_bar.wand_contiguous_check.isChecked()
                canvas.magic_wand_sample_all = self.options_bar.wand_sample_all_check.isChecked()
        elif tool_name == "clone": canvas.current_tool = CloneTool(canvas)
        elif tool_name == "text": canvas.current_tool = TextTool(canvas)
        elif tool_name == "pen_path":
            canvas.current_tool = PenPathTool(canvas)
            if hasattr(self, 'options_bar'):
                ob = self.options_bar
                if hasattr(ob, 'pen_path_output_combo'):
                    canvas.pen_path_output = ob.pen_path_output_combo.currentData()
                if hasattr(ob, 'pen_path_fill_combo'):
                    canvas.pen_path_fill_pattern = ob.pen_path_fill_combo.currentData()
                if hasattr(ob, 'pen_path_style_combo'):
                    canvas.pen_path_line_style = ob.pen_path_style_combo.currentData()
        elif tool_name == "line_curve":
            canvas.current_tool = LineCurveTool(canvas)
            if hasattr(self, 'options_bar'):
                ob = self.options_bar
                if hasattr(ob, 'line_curve_mode_combo'):
                    canvas.line_curve_mode = ob.line_curve_mode_combo.currentData()
                if hasattr(ob, 'line_curve_style_combo'):
                    canvas.line_curve_style = ob.line_curve_style_combo.currentData()
                if hasattr(ob, 'line_curve_cap_start_combo'):
                    canvas.line_curve_cap_start = ob.line_curve_cap_start_combo.currentData()
                    canvas.line_curve_cap_end = ob.line_curve_cap_end_combo.currentData()
                    _tam = ob.line_curve_cap_size_box.currentText().strip()
                    canvas.line_curve_cap_size = (max(1, min(300, int(_tam)))
                                                  if _tam.isdigit() else 0)
        elif tool_name == "measure":
            if hasattr(self, 'options_bar') and hasattr(self.options_bar, 'measure_unit_combo'):
                canvas.measure_unit = self.options_bar.measure_unit_combo.currentData()
            canvas.current_tool = MeasureTool(canvas)
        elif tool_name == "airbrush": canvas.current_tool = AirbrushTool(canvas)
        elif tool_name == "gradient":
            canvas.current_tool = GradientTool(canvas)
            # Sincronizar los ajustes del panel con esta pestaña (al cambiar de
            # pestaña o abrir otra imagen, el lienzo nuevo hereda patrón/modo/dither)
            if hasattr(self, 'options_bar'):
                ob = self.options_bar
                if hasattr(ob, 'gradient_pattern_selector'):
                    canvas.gradient_pattern = ob.gradient_pattern_selector.currentData()
                if hasattr(ob, 'gradient_mode_selector'):
                    canvas.gradient_mode = ob.gradient_mode_selector.currentData()
                if hasattr(ob, 'gradient_dither_check'):
                    canvas.gradient_dither = ob.gradient_dither_check.isChecked()
        elif tool_name == "smudge":
            canvas.current_tool = SmudgeTool(canvas)
            if hasattr(self, 'options_bar'):
                ob = self.options_bar
                if hasattr(ob, 'smudge_hardness_slider'):
                    canvas.smudge_hardness = ob.smudge_hardness_slider.value()
                if hasattr(ob, 'smudge_strength_slider'):
                    canvas.smudge_strength = ob.smudge_strength_slider.value()
                if hasattr(ob, 'smudge_spacing_slider'):
                    canvas.smudge_spacing = ob.smudge_spacing_slider.value()
                if hasattr(ob, 'smudge_finger_check'):
                    canvas.smudge_finger_paint = ob.smudge_finger_check.isChecked()
        elif tool_name == "dodge_burn":
            canvas.current_tool = DodgeBurnTool(canvas)
            if hasattr(self, 'options_bar') and hasattr(self.options_bar, 'dodge_mode_combo'):
                ob = self.options_bar
                canvas.dodge_mode = ob.dodge_mode_combo.currentData()
                canvas.dodge_range = ob.dodge_range_combo.currentData()
                canvas.dodge_exposure = ob.dodge_exposure_slider.value()
                canvas.dodge_hardness = ob.dodge_hardness_slider.value()
        elif tool_name == "sponge":
            canvas.current_tool = SpongeTool(canvas)
            if hasattr(self, 'options_bar') and hasattr(self.options_bar, 'sponge_mode_combo'):
                ob = self.options_bar
                canvas.sponge_mode = ob.sponge_mode_combo.currentData()
                canvas.sponge_flow = ob.sponge_flow_slider.value()
                canvas.sponge_hardness = ob.sponge_hardness_slider.value()
        elif tool_name == "liquify":
            canvas.current_tool = LiquifyTool(canvas)
            if hasattr(self, 'options_bar') and hasattr(self.options_bar, 'liquify_strength_slider'):
                ob = self.options_bar
                canvas.liquify_strength = ob.liquify_strength_slider.value()
                canvas.liquify_hardness = ob.liquify_hardness_slider.value()
        elif tool_name == "heal":
            canvas.current_tool = HealTool(canvas)
        elif tool_name == "replace_color":
            canvas.current_tool = ReplaceColorTool(canvas)
            if hasattr(self, 'options_bar') and hasattr(self.options_bar, 'replace_tolerance_slider'):
                canvas.replace_tolerance = self.options_bar.replace_tolerance_slider.value()
        elif tool_name == "crop":
            # La relación fija del panel se vuelca ANTES de crear la herramienta
            # (la caja inicial ajustada a la selección no se fuerza a la relación)
            if hasattr(self, 'options_bar') and hasattr(self.options_bar, 'crop_ratio_combo'):
                canvas.crop_ratio = self.options_bar.crop_ratio_combo.currentData()
            canvas.current_tool = CropTool(canvas)
            # Sincronizar la barra de opciones con la caja inicial (puede venir
            # ya ajustada a la selección activa) o vacía si no hay
            if hasattr(self, 'options_bar') and hasattr(self.options_bar, 'set_crop_info'):
                self.options_bar.set_crop_info(canvas.current_tool.rect)
        if hasattr(self, 'tools_panel'):
            self.tools_panel.set_active_tool_visual(tool_name)
        # La caja de texto de la herramienta de mover habilita Deseleccionar
        # sin selección real: re-evaluar el estado al cambiar de herramienta.
        self.update_edit_actions_state()
        self.update_canvas_cursor() # ← AÑADIDO
        self.activateWindow()  # Recuperar la activación (los docks flotantes son ventanas aparte)
        canvas.setFocus()      # Y dentro de ella, el foco al lienzo

        # (El bloque de begin_paste para texto fue eliminado)

    def _crear_atajos_herramientas(self):
        """Atajos de UNA TECLA para las herramientas (estilo Photoshop/GIMP):
        B pincel, E goma, V mover, M marquesina (repetir alterna rectángulo/
        elipse), C recortar a la selección... El mapa vive en
        widgets/tools_panel.py (ATAJOS_HERRAMIENTAS), que también los enseña
        en los tooltips de la rejilla. Son QAction de ámbito de VENTANA sin
        entrada de menú. No estorban al escribir: los controles de texto
        (QTextEdit/QLineEdit/QSpinBox) aceptan el ShortcutOverride de las
        teclas imprimibles y el atajo no llega a dispararse; el handler
        además lo comprueba por si acaso (doble cinturón)."""
        from widgets.tools_panel import ATAJOS_HERRAMIENTAS
        vistos = set()
        for tool_id, tecla in ATAJOS_HERRAMIENTAS.items():
            if tecla in vistos:      # M está dos veces (rect/elipse): una QAction
                continue
            vistos.add(tecla)
            accion = QAction(self)
            accion.setShortcut(tecla)
            accion.setShortcutContext(Qt.WindowShortcut)
            accion.triggered.connect(
                lambda checked=False, tid=tool_id: self._atajo_herramienta(tid))
            self.addAction(accion)

    def _atajo_herramienta(self, tool_id):
        """Activa una herramienta por tecla, salvo que el foco esté en un
        control de escritura (editor de texto, campo hex, spinbox, combo
        editable): ahí la tecla debe escribir, no cambiar de herramienta."""
        from PySide6.QtWidgets import (QLineEdit, QTextEdit, QPlainTextEdit,
                                       QAbstractSpinBox, QComboBox)
        w = QApplication.focusWidget()
        if isinstance(w, (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox)):
            return
        if isinstance(w, QComboBox) and w.isEditable():
            return
        # M alterna entre las dos marquesinas (estándar de los editores)
        actual = getattr(self, "current_tool_name", None)
        if tool_id == "select_rect" and actual == "select_rect":
            tool_id = "select_ellipse"
        self.set_tool(tool_id)

    def change_color(self):
        # "Paleta de Colores" (menú Ver): abre el MISMO editor de color EN VIVO
        # que el cuadro primario del panel (overlay del lienzo, color primario),
        # no el selector modal suelto (ese es solo para efectos/IA).
        cp = getattr(self, 'colors_panel', None)
        if cp is not None:
            cp.open_color_dialog()

    def trigger_canvas_undo(self): # ← Este método ya lo teníamos, sirve como referencia visual
        canvas = self.get_current_canvas()
        if not canvas: return
        # Con un objeto flotante EN EDICIÓN (Línea/Curva, Formas), el primer
        # deshacer lo CANCELA (como Esc) en vez de tocar la pila: si la pila se
        # moviera con él vivo, su image_before quedaría obsoleto y al recomponer
        # o confirmar resucitaría contenido ya deshecho.
        tool = getattr(canvas, 'current_tool', None)
        if getattr(tool, 'editing', False) and hasattr(tool, '_cancel_edit'):
            tool._cancel_edit()
            return
        if canvas.undo_stack.canUndo(): canvas.undo_stack.undo()

    def trigger_canvas_redo(self):
        canvas = self.get_current_canvas()
        if not canvas: return
        # Misma protección que en deshacer: el flotante se cancela primero.
        tool = getattr(canvas, 'current_tool', None)
        if getattr(tool, 'editing', False) and hasattr(tool, '_cancel_edit'):
            tool._cancel_edit()
        if canvas.undo_stack.canRedo(): canvas.undo_stack.redo()

    def update_undo_redo_actions_state(self):
        canvas = self.get_current_canvas()
        if canvas and hasattr(self, 'undo_action'):
            self.undo_action.setEnabled(canvas.undo_stack.canUndo())
            self.redo_action.setEnabled(canvas.undo_stack.canRedo())

    def save_preferences(self):
        """Guarda en QSettings las preferencias que deben sobrevivir al cierre:
        visibilidad de los cuatro paneles empotrados, tamaños de los splitters
        (anchura de columnas y reparto vertical de la columna derecha) y estado
        de cuadrícula y reglas."""
        s = self.settings
        s.setValue("panels/tools", self.tools_container.isVisible())
        s.setValue("panels/layers", self.layers_container.isVisible())
        s.setValue("panels/history", self.history_container.isVisible())
        s.setValue("panels/colors", self.colors_container.isVisible())
        s.setValue("panels/histogram", self.histogram_container.isVisible())
        # Orden de la columna derecha (reordenable con ▲/▼). Se guarda como
        # claves, no por índice: saveState() del splitter solo repone tamaños.
        s.setValue("panels/right_order", ",".join(self._right_panel_order()))
        # Tamaños de los splitters (sustituyen a la antigua geometría de las
        # paletas flotantes). saveState() guarda el reparto entre celdas.
        s.setValue("splitters/root", self.root_splitter.saveState())
        s.setValue("splitters/right", self.right_splitter.saveState())
        s.setValue("view/grid", self.global_show_grid)
        s.setValue("view/grid_tile", self.global_grid_tile)
        s.setValue("view/rulers", self.global_show_rulers)
        s.setValue("view/unit", self.ruler_overlay.unit if hasattr(self, 'ruler_overlay') else "px")
        # Geometría de la ventana. El maximizar de la ventana sin marco es
        # MANUAL (CustomTitleBar lleva _maximized y _normal_geom), así que no nos
        # vale saveGeometry(): captura la geometría maximizada sin marcar el estado.
        # Guardamos por separado la geometría "ventana" (tamaño normal) y si está
        # maximizada, para reconstruir el estado correctamente al reabrir.
        tb = getattr(self, 'title_bar', None)
        maximized = bool(getattr(tb, '_maximized', False))
        if maximized and tb is not None and tb._normal_geom is not None:
            normal_geom = tb._normal_geom            # la "ventana" guardada al maximizar
        else:
            normal_geom = self.geometry()            # tamaño normal actual
        s.setValue("window/normal_geometry", normal_geom)
        s.setValue("window/maximized", maximized)

    def restore_preferences(self):
        """Restaura las preferencias guardadas al arrancar. Se llama al final
        del __init__, cuando ya existen todos los paneles y la primera pestaña.
        Si no hay nada guardado (primera vez), usa los valores por defecto."""
        s = self.settings

        def as_bool(value, default):
            # QSettings puede devolver el bool como cadena "true"/"false"
            if value is None:
                return default
            if isinstance(value, bool):
                return value
            return str(value).lower() == "true"

        # Geometría de la ventana. Restauramos la geometría "ventana" (tamaño
        # normal) y, si se cerró maximizada, maximizamos a mano por la MISMA vía
        # que el botón de la barra de título, de modo que el estado interno
        # (_maximized, _normal_geom) y el icono del botón queden coherentes y al
        # restaurar se vuelva al tamaño pequeño correcto. No usamos restoreGeometry:
        # su flag de maximizado de Qt no encaja con el maximizar manual sin marco
        # (dejaba la ventana "casi maximizada" con un hueco arriba).
        normal_geom = s.value("window/normal_geometry")
        if normal_geom is not None:
            self.setGeometry(normal_geom)
        if as_bool(s.value("window/maximized"), False):
            tb = getattr(self, 'title_bar', None)
            if tb is not None and getattr(tb, '_show_min_max', False) and not tb._maximized:
                tb.toggle_max_restore()

        # --- Paneles empotrados (por defecto, todos visibles) ---
        self.btn_toggle_tools.setChecked(as_bool(s.value("panels/tools"), True))
        self.btn_toggle_layers.setChecked(as_bool(s.value("panels/layers"), True))
        self.btn_toggle_history.setChecked(as_bool(s.value("panels/history"), True))
        self.btn_toggle_colors.setChecked(as_bool(s.value("panels/colors"), True))
        # Histograma en vivo: visible por defecto, como el resto de paneles.
        self.btn_toggle_histogram.setChecked(as_bool(s.value("panels/histogram"), True))
        # Sincronizar la visibilidad de la columna derecha por si se restauran
        # los tres paneles ocultos (toggled no salta si el estado no cambia).
        self._update_right_column_visibility()

        # Reevaluar el selector de color del pie con el estado ya restaurado
        # (panel de Color) por si ningún toggled saltó.
        self._update_tools_color_selector_visibility()

        # --- Orden personalizado del panel de Herramientas (arrastrar y
        # soltar). apply_order sanea ids desconocidos y añade al final las
        # herramientas nuevas; el combo se reordena con el orden ya saneado. ---
        orden_tools = str(s.value("panels/tools_order") or "")
        if orden_tools:
            self.tools_panel.apply_order([k for k in orden_tools.split(",") if k])
            ids = self.tools_panel.tool_order()
            self.options_bar.reorder_tool_combo(ids[0::2] + ids[1::2])

        # --- ¿Se pueden reordenar los botones de Herramientas? (Preferencias) ---
        self.tools_panel.set_reorderable(
            as_bool(s.value("panels/tools_reorderable"), True))

        # --- Orden de la columna derecha (ANTES de restaurar tamaños: el
        # restoreState del splitter repone tamaños por posición) ---
        orden = str(s.value("panels/right_order") or "")
        if orden:
            claves = [k for k in orden.split(",")
                      if k in ("layers", "history", "colors", "histogram")]
            # Orden guardado ANTES de existir el panel de Histograma: se
            # respeta el orden del usuario y el Histograma se queda arriba
            # (su posición por defecto).
            if "histogram" not in claves:
                claves.insert(0, "histogram")
            for pos, clave in enumerate(claves):
                cont = getattr(self, f"{clave}_container", None)
                if cont is not None:
                    self.right_splitter.insertWidget(pos, cont)
            self._apply_right_stretch_factors()

        # --- Tamaños de los splitters (si hay algo guardado) ---
        root_state = s.value("splitters/root")
        if root_state is not None:
            self.root_splitter.restoreState(root_state)
        right_state = s.value("splitters/right")
        if right_state is not None:
            self.right_splitter.restoreState(right_state)

        # --- Cuadrícula y reglas ---
        # Cuadrícula: oculta por defecto. Reglas: VISIBLES en el primer arranque
        # (cuando aún no hay preferencia guardada); después se recuerda la elección.
        grid = as_bool(s.value("view/grid"), False)
        rulers = as_bool(s.value("view/rulers"), True)
        unit = s.value("view/unit") or "px"

        # Aplicar vía las casillas del menú, que ya propagan a todos los lienzos
        self.grid_action.setChecked(grid)
        self.global_show_grid = grid
        for i in range(self.tabs.count()):
            marker = self.tabs.widget(i)
            if marker and hasattr(marker, 'canvas'):
                marker.canvas.set_show_grid(grid)

        # Mosaico de la cuadrícula (0 = sin mosaico; valores desconocidos → 0)
        try:
            tile = int(s.value("view/grid_tile", 0))
        except (TypeError, ValueError):
            tile = 0
        if tile not in self.grid_tile_actions:
            tile = 0
        self.grid_tile_actions[tile].setChecked(True)
        self.set_grid_tile_global(tile)

        self.rulers_action.setChecked(rulers)
        self.global_show_rulers = rulers
        for i in range(self.tabs.count()):
            marker = self.tabs.widget(i)
            if marker and hasattr(marker, 'canvas'):
                marker.canvas.set_show_rulers(rulers)

        if hasattr(self, 'ruler_overlay'):
            self.ruler_overlay.set_unit(unit)
            if unit == "cm":
                self.unit_cm_action.setChecked(True)
            elif unit == "in":
                self.unit_in_action.setChecked(True)
            else:
                self.unit_px_action.setChecked(True)

        self._sync_ruler_overlay_geometry()
        # Tras restaurar geometría (sobre todo si era maximizada, que se asienta
        # en otro ciclo de eventos), reposicionar paneles y reglas una vez más
        QTimer.singleShot(30, self._sync_ruler_overlay_geometry)
        QTimer.singleShot(30, self.fit_canvas_to_screen)

    def dragEnterEvent(self, event):
        """Acepta el arrastre si trae al menos un archivo local."""
        md = event.mimeData()
        if md.hasUrls() and any(u.isLocalFile() for u in md.urls()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        """Abre los archivos soltados (imágenes o proyectos .imago). open_path
        avisa con elegancia si alguno no es una imagen válida."""
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        paths = [p for p in paths if p and os.path.exists(p)]
        if not paths:
            return
        event.acceptProposedAction()
        for p in paths:
            self.open_path(p)

    def closeEvent(self, event):
        from PySide6.QtWidgets import QMessageBox
        from models.document_state import documento_pendiente

        # Ninguna preview provisional debe entrar en un guardado provocado por
        # el cierre de la aplicación.
        panel = getattr(self, "_active_adjustment_overlay", None)
        if panel is not None:
            panel.reject()

        # 1. Revisar TODAS las pestañas en busca de cambios sin guardar (incluye
        # documentos recuperados que aún no se han guardado de verdad)
        for i in range(self.tabs.count()):
            marker = self.tabs.widget(i)
            if (marker and hasattr(marker, 'canvas')
                    and documento_pendiente(marker.canvas)):
                self.tabs.setCurrentIndex(i)  # Mostramos la pestaña afectada al usuario
                nombre = self.tabs.tabText(i)
                resp = imago_warning(
                    self, t("msg.unsaved.title"),
                    t("msg.unsaved.text", nombre=nombre),
                    QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel
                )
                if resp == QMessageBox.Save:
                    resultado = self.save_file()
                    # Cancelar, fallar o seguir pendiente aborta el cierre; así
                    # autosave.clear() nunca borra la única copia recuperable.
                    if (resultado is not ResultadoGuardado.EXITO
                            or documento_pendiente(marker.canvas)):
                        event.ignore()
                        return
                elif resp == QMessageBox.Cancel:
                    event.ignore()
                    return
                # Discard: seguimos con la siguiente pestaña

        if getattr(self, "_ai_handle", None) is not None:
            self._ai_cancel_current()

        # 2. Desconexión de stacks (tu código existente)
        for i in range(self.tabs.count()):
            marker = self.tabs.widget(i)
            if marker and hasattr(marker, 'canvas'):
                try:
                    marker.canvas.undo_stack.indexChanged.disconnect()
                except RuntimeError:
                    pass
        # 3. Guardar preferencias (paneles visibles, cuadrícula, reglas)
        self.save_preferences()
        # 4. Cierre LIMPIO: ya no hay nada que recuperar -> borrar copias y parar
        # el autoguardado (lo no guardado se gestionó en el paso 1).
        if hasattr(self, 'autosave'):
            self.autosave.stop()
            self.autosave.clear()
        event.accept()


class _NoMnemonicUnderlineStyle(QProxyStyle):
    """Oculta el subrayado de las teclas de acceso (mnemónicos Alt) en menús y
    botones, CONSERVANDO la navegación Alt+letra (solo se quita el subrayado)."""

    def styleHint(self, hint, option=None, widget=None, returnData=None):
        if hint == QStyle.StyleHint.SH_UnderlineShortcut:
            return 0
        # Clic en el surco de un QSlider = saltar al valor de la posición del
        # ratón (absoluto), en vez del salto de página (10 en 10) por defecto.
        if hint == QStyle.StyleHint.SH_Slider_AbsoluteSetButtons:
            return int(Qt.MouseButton.LeftButton.value)
        return super().styleHint(hint, option, widget, returnData)


def apply_dark_theme(app):
    """Estilo Fusion + paleta oscura con los colores EXACTOS del proyecto.
    Fusion dibuja todos los widgets el propio Qt (igual en Windows y en Linux)
    e ignora el tema claro/oscuro del sistema. La paleta usa los hex actuales,
    asi que los widgets no estilados a mano (QMessageBox, spinbox, combos,
    scrollbars, tooltips...) quedan oscuros y consistentes en ambos sistemas.
    Lo ya estilado con stylesheets NO cambia: el stylesheet manda sobre la paleta.
    """
    from PySide6.QtGui import QPalette, QColor, QFont
    # 'Segoe UI' (y 'Arial') son fuentes de Windows; en Linux no existen.
    # Registramos sustitutos equivalentes para que Qt use una fuente parecida.
    # Afecta tanto a QFont(...) como a los font-family de los stylesheets; en
    # Windows no cambia nada (Segoe UI sí existe y se usa la primera).
    QFont.insertSubstitutions("Segoe UI", ["Noto Sans", "Cantarell", "DejaVu Sans", "Liberation Sans"])
    QFont.insertSubstitutions("Arial", ["Liberation Sans", "DejaVu Sans", "Noto Sans"])
    # Fusion envuelto en el proxy que oculta el subrayado de los mnemónicos.
    app.setStyle(_NoMnemonicUnderlineStyle(QStyleFactory.create("Fusion")))

    WIN  = QColor("#2b2b2b")   # fondo general de paneles/ventanas
    BASE = QColor("#202020")   # fondo de campos de entrada
    TEXT = QColor("#e0e0e0")   # texto
    BTN  = QColor("#3a3a3a")   # fondo de botones
    DIS  = QColor("#555555")   # texto deshabilitado
    HL   = QColor("#1a4f7c")   # seleccion (mismo azul que el menu)

    pal = QPalette()
    pal.setColor(QPalette.Window, WIN)
    pal.setColor(QPalette.WindowText, TEXT)
    pal.setColor(QPalette.Base, BASE)
    pal.setColor(QPalette.AlternateBase, WIN)
    pal.setColor(QPalette.Text, TEXT)
    pal.setColor(QPalette.ToolTipBase, WIN)
    pal.setColor(QPalette.ToolTipText, TEXT)
    pal.setColor(QPalette.Button, BTN)
    pal.setColor(QPalette.ButtonText, TEXT)
    pal.setColor(QPalette.BrightText, QColor("#ffffff"))
    pal.setColor(QPalette.Link, QColor("#007acc"))
    pal.setColor(QPalette.Highlight, HL)
    pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    pal.setColor(QPalette.PlaceholderText, QColor("#888888"))
    # Bordes/relieves de Fusion en tonos oscuros (si no, dibuja biseles claros)
    pal.setColor(QPalette.Light,    QColor("#3a3a3a"))
    pal.setColor(QPalette.Midlight, QColor("#333333"))
    pal.setColor(QPalette.Mid,      QColor("#444444"))
    pal.setColor(QPalette.Dark,     QColor("#1e1e1e"))
    pal.setColor(QPalette.Shadow,   QColor("#000000"))
    # Estados deshabilitados
    for _role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, _role, DIS)
    pal.setColor(QPalette.Disabled, QPalette.Highlight, QColor("#3a3a3a"))
    pal.setColor(QPalette.Disabled, QPalette.HighlightedText, DIS)
    app.setPalette(pal)


def apply_light_theme(app):
    """Igual que apply_dark_theme pero con la paleta CLARA (primer borrador).
    Fusion + QPalette clara para los widgets no estilados a mano; el resto lo
    resuelve theme.use_theme("light") (tokens de QSS) + el tintado de iconos.
    Se afinará; el tema oscuro sigue siendo el de por defecto."""
    from PySide6.QtGui import QPalette, QColor, QFont
    QFont.insertSubstitutions("Segoe UI", ["Noto Sans", "Cantarell", "DejaVu Sans", "Liberation Sans"])
    QFont.insertSubstitutions("Arial", ["Liberation Sans", "DejaVu Sans", "Noto Sans"])
    app.setStyle(_NoMnemonicUnderlineStyle(QStyleFactory.create("Fusion")))

    WIN  = QColor("#f0f0f0")   # fondo general de paneles/ventanas
    BASE = QColor("#ffffff")   # fondo de campos de entrada
    TEXT = QColor("#202020")   # texto
    BTN  = QColor("#e6e6e6")   # fondo de botones
    DIS  = QColor("#aaaaaa")   # texto deshabilitado
    HL   = QColor("#007acc")   # seleccion (mismo azul de acento)

    pal = QPalette()
    pal.setColor(QPalette.Window, WIN)
    pal.setColor(QPalette.WindowText, TEXT)
    pal.setColor(QPalette.Base, BASE)
    pal.setColor(QPalette.AlternateBase, WIN)
    pal.setColor(QPalette.Text, TEXT)
    pal.setColor(QPalette.ToolTipBase, WIN)
    pal.setColor(QPalette.ToolTipText, TEXT)
    pal.setColor(QPalette.Button, BTN)
    pal.setColor(QPalette.ButtonText, TEXT)
    pal.setColor(QPalette.BrightText, QColor("#000000"))
    pal.setColor(QPalette.Link, QColor("#007acc"))
    pal.setColor(QPalette.Highlight, HL)
    pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    pal.setColor(QPalette.PlaceholderText, QColor("#999999"))
    # Bordes/relieves de Fusion en tonos claros
    pal.setColor(QPalette.Light,    QColor("#ffffff"))
    pal.setColor(QPalette.Midlight, QColor("#f6f6f6"))
    pal.setColor(QPalette.Mid,      QColor("#c0c0c0"))
    pal.setColor(QPalette.Dark,     QColor("#a0a0a0"))
    pal.setColor(QPalette.Shadow,   QColor("#808080"))
    # Estados deshabilitados
    for _role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, _role, DIS)
    pal.setColor(QPalette.Disabled, QPalette.Highlight, QColor("#d6d6d6"))
    pal.setColor(QPalette.Disabled, QPalette.HighlightedText, DIS)
    app.setPalette(pal)


if __name__ == "__main__":
    import sys, os
    # Fijar el directorio de trabajo a la carpeta del script, por si algún recurso
    # se carga con ruta relativa aunque se lance Imago desde otro directorio o desde
    # un lanzador .desktop (que no fija el cwd). Los iconos ya no dependen de esto:
    # viajan embebidos como recursos (":/icons/...").
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    # NOTA (migración a paneles empotrados): antes se forzaba XWayland
    # (QT_QPA_PLATFORM=xcb) porque las 4 paletas eran ventanas Qt.Tool que se
    # posicionaban en coordenadas globales con move(), algo que Wayland puro
    # prohíbe. Ahora los paneles van EMPOTRADOS en QSplitters dentro de la
    # ventana, así que ya no hace falta: Imago usa el backend nativo del SO
    # (Wayland si la sesión lo es). Si alguna distro diera problemas, el usuario
    # siempre puede forzar el backend a mano con QT_QPA_PLATFORM=xcb.

    app = QApplication(sys.argv)
    # Identidad de la app (misma que QSettings): así rutas estándar como la
    # carpeta de recuperación quedan en .../AVNSoft/Imago/... y no en .../python/...
    app.setOrganizationName(app_paths.ORGANIZACION)
    app.setApplicationName(app_paths.APLICACION)
    app.setDesktopFileName("io.github.anvilnu.imago")
    # Tema: oscuro por defecto. Se elige en Preferencias (clave QSettings "theme")
    # y la variable de entorno IMAGO_THEME lo fuerza (útil para pruebas). use_theme()
    # debe ejecutarse ANTES de construir la ventana (los QSS y el tintado de iconos
    # leen los tokens al montar cada widget). Se lee con app_paths.settings() (el
    # MISMO almacén que usa Preferencias: QSettings("AVNSoft","Imago") o el .ini
    # portable); un QSettings() pelado usaría otra organización y no vería el valor.
    _env_theme = os.environ.get("IMAGO_THEME")
    if _env_theme:
        _theme_mode = _env_theme.strip().lower()
    else:
        _theme_mode = str(app_paths.settings().value("theme", "dark")).strip().lower()
    if _theme_mode not in ("dark", "light"):
        _theme_mode = "dark"
    theme.use_theme(_theme_mode)
    if _theme_mode == "light":
        apply_light_theme(app)
    else:
        apply_dark_theme(app)
    # Regla GLOBAL de tooltips (única en toda la app): sin ella el aspecto del
    # tooltip variaba según el widget bajo el cursor (unos oscuros, otros claros
    # con texto invisible en tema claro).
    app.setStyleSheet(theme.tooltip_qss())

    # Cargar las traducciones de Qt en el idioma activo: traduce todos los textos
    # estándar de Qt (botones de QMessageBox, diálogos de color, etc.). El idioma
    # se lee del MISMO almacén que Preferencias / i18n, incluido el INI portable.
    from PySide6.QtCore import QTranslator, QLibraryInfo, QLocale
    _qt_lang = app_paths.idioma()
    qt_translator = QTranslator()
    translations_path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if qt_translator.load(QLocale(_qt_lang), "qtbase", "_", translations_path):
        app.installTranslator(qt_translator)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())
