from i18n import t
# widgets/custom_titlebar.py
"""Barra de título propia (sin marco) y redimensionado manual, multiplataforma.

Se usa para que la ventana se vea EXACTAMENTE igual en Windows y en Linux,
siempre en oscuro, sin depender de la barra de título nativa del sistema.

Contiene:
  - _CaptionButton: botón de minimizar/maximizar/restaurar/cerrar. El icono se
    dibuja con QPainter (no con fuentes), asi no dependemos de que el glifo
    exista en el sistema y se ve idéntico en todos lados.
  - CustomTitleBar: la barra (icono + título + botones). Arrastrar para mover,
    doble clic para maximizar/restaurar.
  - FramelessResizeFilter: filtro de eventos que permite redimensionar la
    ventana sin marco agarrando cualquiera de los 8 bordes/esquinas.

Colores del proyecto: fondo #202020, texto #e0e0e0, hover #3a3a3a, cerrar #c42b1c.
"""

import os
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel,
                               QPushButton, QApplication, QDialog,
                               QMessageBox, QStyle)
from PySide6.QtCore import Qt, QObject, QEvent, QPoint, QRect, QFile
from PySide6.QtGui import QIcon, QPainter, QPen, QColor
import theme

# Los colores de la barra de título salen de theme (única fuente de verdad). Se
# leen EN EL MOMENTO de construir/pintar cada barra (no en constantes de módulo),
# porque el módulo se importa antes de fijar el tema (use_theme) y una constante
# se congelaría en el tema inicial (oscuro). Mapeo:
#   fondo = theme.BG_DARK · texto = theme.TEXT · hover min/max = theme.BG_BUTTON
#   hover cerrar = theme.CAPTION_CLOSE (rojo estilo Windows)


class _CaptionButton(QPushButton):
    """Botón de control de ventana con el icono dibujado a mano."""

    def __init__(self, kind, height=32, width=46, parent=None):
        super().__init__(parent)
        self._kind = kind          # 'min' | 'max' | 'restore' | 'close'
        self._hover = False
        self.setFixedSize(width, height)
        self.setCursor(Qt.ArrowCursor)
        self.setFocusPolicy(Qt.NoFocus)

    def set_kind(self, kind):
        self._kind = kind
        self.update()

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def _bg_color(self):
        if self._hover:
            return QColor(theme.CAPTION_CLOSE if self._kind == "close" else theme.BG_BUTTON)
        return QColor(theme.BG_DARK)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        # Fondo (hover)
        if self._hover:
            p.fillRect(self.rect(), self._bg_color())
        # Color del trazo
        if self._hover and self._kind == "close":
            col = QColor("#ffffff")
        else:
            col = QColor(theme.TEXT)
        pen = QPen(col)
        pen.setWidthF(1.3)
        p.setPen(pen)

        cx, cy = self.width() / 2.0, self.height() / 2.0
        s = 5  # semilado del glifo (~10px)

        if self._kind == "min":
            p.drawLine(int(cx - s), int(cy), int(cx + s), int(cy))

        elif self._kind == "max":
            p.drawRect(int(cx - s), int(cy - s), int(2 * s), int(2 * s))

        elif self._kind == "restore":
            o = 2
            d = 2 * s
            # Cuadro de atrás (arriba-derecha)
            p.drawRect(int(cx - s + o), int(cy - s - o), d, d)
            # Tapamos la zona del cuadro de delante para que no se crucen las líneas
            p.fillRect(int(cx - s - o), int(cy - s + o), d, d, self._bg_color())
            # Cuadro de delante (abajo-izquierda)
            p.drawRect(int(cx - s - o), int(cy - s + o), d, d)

        elif self._kind == "close":
            p.drawLine(int(cx - s), int(cy - s), int(cx + s), int(cy + s))
            p.drawLine(int(cx - s), int(cy + s), int(cx + s), int(cy - s))

        p.end()


class CustomTitleBar(QWidget):
    """Barra de título propia para una ventana sin marco.

    `window` es la ventana de nivel superior a la que controla. Arrastrar la
    barra mueve la ventana; doble clic maximiza/restaura; los botones hacen lo
    suyo.
    """

    def __init__(self, window, title="", icon_path=None, height=32,
                 show_min_max=True, bottom_border=False, btn_width=46, parent=None):
        super().__init__(parent or window)
        self._win = window
        self._height = height
        self._btn_width = btn_width
        self._drag_offset = None
        self._maximized = False  # estado propio (isMaximized() no es fiable sin marco)
        self._normal_geom = None  # geometría "ventana" guardada al maximizar, para restaurar
        self._show_min_max = show_min_max
        self.setObjectName("CustomTitleBar")
        self.setFixedHeight(height)
        # Separador opcional bajo la barra de título (lo usan los diálogos, cuyo
        # cuerpo es del mismo tono y si no parece que no hubiera separación).
        _sep = (" border-bottom: 1px solid %s;" % theme.BORDER) if bottom_border else ""
        self.setStyleSheet(
            "#CustomTitleBar { background-color: %s;%s }"
            "#CustomTitleBar QLabel#TitleText { color: %s; font-family:'Segoe UI',Arial; font-size:12px; }"
            % (theme.BG_DARK, _sep, theme.TEXT)
        )

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 0, 0, 0)
        lay.setSpacing(8)

        # Icono
        self.icon_label = QLabel()
        _has_icon = bool(icon_path and QFile.exists(icon_path))
        self.icon_label.setFixedWidth(20 if _has_icon else 0)
        if _has_icon:
            self.icon_label.setPixmap(theme.icono(icon_path).pixmap(18, 18))
        lay.addWidget(self.icon_label)

        # Título
        self.title_label = QLabel(title or window.windowTitle())
        self.title_label.setObjectName("TitleText")
        lay.addWidget(self.title_label)

        lay.addStretch()

        # Botones de control. Los diálogos solo llevan "cerrar".
        self.btn_min = None
        self.btn_max = None
        if show_min_max:
            self.btn_min = _CaptionButton("min", height, self._btn_width)
            self.btn_max = _CaptionButton("max", height, self._btn_width)
            lay.addWidget(self.btn_min)
            lay.addWidget(self.btn_max)
            self.btn_min.clicked.connect(self._win.showMinimized)
            self.btn_max.clicked.connect(self.toggle_max_restore)
        self.btn_close = _CaptionButton("close", height, self._btn_width)
        lay.addWidget(self.btn_close)
        self.btn_close.clicked.connect(self._win.close)

        # Seguimos el TÍTULO de la ventana con un filtro de eventos. El estado
        # maximizado lo llevamos nosotros (self._maximized) porque con la ventana
        # sin marco isMaximized() no es fiable en todas las plataformas.
        self._win.installEventFilter(self)
        self._sync_max_button()

    def set_title(self, text):
        self.title_label.setText(text)

    def toggle_max_restore(self):
        if not self._show_min_max:
            return
        if self._maximized:
            self._restore_window()
        else:
            self._maximize_window()
        self._win._imago_maximized = self._maximized
        self._sync_max_button()

    def _maximize_window(self):
        """Maximiza SIN usar showMaximized() en Windows: en una ventana sin marco
        hace que Qt y Windows se peleen por la geometría exacta.
        En Linux/Mac sí se usa showMaximized() para integrarse con Wayland/X11."""
        self._normal_geom = self._win.geometry()
        import sys
        if sys.platform == "win32":
            scr = self._win.screen() or QApplication.primaryScreen()
            if scr is not None:
                avail = scr.availableGeometry()
                if avail == scr.geometry():          # barra de tareas oculta/ausente
                    avail = avail.adjusted(0, 0, 0, -1)  # 1 px libre abajo
                self._win.setGeometry(avail)
        else:
            self._win.showMaximized()
        self._maximized = True

    def _restore_window(self):
        """Restaura a mano la geometría 'ventana' guardada al maximizar en Windows.
        En Linux/Mac usa showNormal()."""
        import sys
        if sys.platform == "win32":
            if self._normal_geom is not None:
                self._win.setGeometry(self._normal_geom)
        else:
            self._win.showNormal()
            if self._normal_geom is not None:
                # Ocasionalmente Wayland necesita que se aplique la geometría guardada
                # si el estado maximizado no fue gestionado correctamente por el compositor.
                self._win.setGeometry(self._normal_geom)
        self._maximized = False

    def _sync_max_button(self):
        if self.btn_max is not None:
            self.btn_max.set_kind("restore" if self._maximized else "max")

    def eventFilter(self, obj, event):
        # Reflejamos el TÍTULO de la ventana en la barra (icono + "archivo - Imago").
        # Robusto: si por cualquier motivo el objeto aún no está listo o el evento
        # da problemas, no dejamos que la excepción rompa el bucle de eventos de Qt.
        try:
            win = getattr(self, "_win", None)
            if win is not None and obj is win and event.type() == QEvent.WindowTitleChange:
                self.title_label.setText(win.windowTitle())
        except Exception:
            pass
        return False

    # ----------------------------------------------------------- arrastrar
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self._maximized:
                self._drag_offset = (event.globalPosition().toPoint()
                                     - self._win.frameGeometry().topLeft())
            else:
                self._drag_offset = None
                wh = self._win.windowHandle()
                if wh:
                    wh.startSystemMove()
            event.accept()

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.LeftButton):
            return
        gp = event.globalPosition().toPoint()
        if self._maximized and self._drag_offset is not None:
            # Restaurar y seguir arrastrando con el cursor sobre la barra.
            ratio = event.position().x() / max(1, self.width())
            self._restore_window()
            self._win._imago_maximized = False
            self._sync_max_button()
            new_w = self._win.width()
            self._drag_offset = QPoint(int(new_w * ratio), event.position().toPoint().y())
            self._win.move(gp - self._drag_offset)
            self._drag_offset = None
            # Delegar el resto del movimiento al sistema
            wh = self._win.windowHandle()
            if wh:
                wh.startSystemMove()
        event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton and self._show_min_max:
            self.toggle_max_restore()
            event.accept()


class FramelessResizeFilter(QObject):
    """Permite redimensionar una ventana sin marco agarrando sus bordes/esquinas.

    Se instala como filtro de eventos GLOBAL (en la QApplication) para detectar
    el cursor aunque esté sobre widgets hijos. Solo actúa cuando la ventana
    objetivo está activa y no está maximizada.
    """

    def __init__(self, window, border=6, min_w=640, min_h=420):
        super().__init__(window)
        self._win = window
        self._b = border
        self._min_w = min_w
        self._min_h = min_h
        self._edge = ""
        self._resizing = False
        self._start_geom = None
        self._start_global = None
        self._cursor_active = False
        self._busy = False
        QApplication.instance().installEventFilter(self)

    # ---- geometría / detección de borde
    def _edge_at(self, local_pos):
        if (not self._win.isVisible() or self._win.isMaximized()
                or getattr(self._win, "_imago_maximized", False)
                or self._win.isMinimized() or self._win.isFullScreen()):
            return ""
        
        w, h = self._win.width(), self._win.height()
        b = self._b
        x, y = local_pos.x(), local_pos.y()
        
        # Si el cursor está más allá del margen del borde, ignorar
        if not (-b <= x <= w + b and -b <= y <= h + b):
            return ""
            
        edge = ""
        if y <= b:
            edge += "t"
        elif y >= h - b:
            edge += "b"
        if x <= b:
            edge += "l"
        elif x >= w - b:
            edge += "r"
        return edge

    def _cursor_for(self, edge):
        if edge in ("tl", "br"):
            return Qt.SizeFDiagCursor
        if edge in ("tr", "bl"):
            return Qt.SizeBDiagCursor
        if edge in ("l", "r"):
            return Qt.SizeHorCursor
        if edge in ("t", "b"):
            return Qt.SizeVerCursor
        return None

    def _update_cursor(self, edge):
        cur = self._cursor_for(edge)
        if cur is not None:
            if not self._cursor_active:
                QApplication.setOverrideCursor(cur)
                self._cursor_active = True
            else:
                QApplication.changeOverrideCursor(cur)
        else:
            self._clear_cursor()

    def _clear_cursor(self):
        if self._cursor_active:
            QApplication.restoreOverrideCursor()
            self._cursor_active = False

    # ---- redimensionado
    def _do_resize(self, gp):
        g = self._start_geom
        dx = gp.x() - self._start_global.x()
        dy = gp.y() - self._start_global.y()
        left, top, right, bottom = g.left(), g.top(), g.right(), g.bottom()
        if "l" in self._edge:
            left = g.left() + dx
        if "r" in self._edge:
            right = g.right() + dx
        if "t" in self._edge:
            top = g.top() + dy
        if "b" in self._edge:
            bottom = g.bottom() + dy
        # Mínimos
        if right - left + 1 < self._min_w:
            if "l" in self._edge:
                left = right - self._min_w + 1
            else:
                right = left + self._min_w - 1
        if bottom - top + 1 < self._min_h:
            if "t" in self._edge:
                top = bottom - self._min_h + 1
            else:
                bottom = top + self._min_h - 1
        self._win.setGeometry(QRect(QPoint(left, top), QPoint(right, bottom)))

    # ---- filtro
    def eventFilter(self, obj, event):
        # Guard de re-entrada: si ya estamos dentro, salimos (evita recursión si
        # alguna acción dispara nuevos eventos sincrónicamente).
        if self._busy:
            return False
        try:
            et = event.type()
        except Exception:
            return False
        # Solo nos interesan eventos de ratón.
        if et not in (QEvent.MouseMove, QEvent.MouseButtonPress,
                      QEvent.MouseButtonRelease):
            return False

        self._busy = True
        try:
            from PySide6.QtGui import QCursor

            # Redimensionado en curso: capturamos todo el ratón
            if self._resizing:
                if et == QEvent.MouseMove:
                    self._do_resize(QCursor.pos())
                    return True
                if et == QEvent.MouseButtonRelease:
                    self._resizing = False
                    self._edge = ""
                    return True
                return False

            # Si hay un diálogo/ventana modal, no tocamos nada.
            if QApplication.activeModalWidget() is not None:
                self._clear_cursor()
                return False

            if not self._win.isActiveWindow():
                self._clear_cursor()
                return False

            if not isinstance(obj, QWidget) or obj.window() is not self._win:
                return False
                
            try:
                local_pos = obj.mapTo(self._win, event.position().toPoint())
            except AttributeError:
                return False

            edge = self._edge_at(local_pos)
            if (et == QEvent.MouseButtonPress
                    and event.button() == Qt.LeftButton and edge):
                self._resizing = False
                self._edge = ""
                edge_map = {
                    "t": Qt.TopEdge,
                    "b": Qt.BottomEdge,
                    "l": Qt.LeftEdge,
                    "r": Qt.RightEdge,
                    "tl": Qt.TopEdge | Qt.LeftEdge,
                    "tr": Qt.TopEdge | Qt.RightEdge,
                    "bl": Qt.BottomEdge | Qt.LeftEdge,
                    "br": Qt.BottomEdge | Qt.RightEdge,
                }
                qt_edge = edge_map.get(edge)
                if qt_edge:
                    wh = self._win.windowHandle()
                    if wh:
                        wh.startSystemResize(qt_edge)
                return True
            if et == QEvent.MouseMove:
                self._update_cursor(edge)
            return False
        except Exception:
            return False
        finally:
            self._busy = False


class FramelessDialog(QDialog):
    """QDialog sin marco con barra de título propia oscura (solo botón cerrar).

    Las subclases añaden su contenido a ``self.body_layout`` (en lugar de crear
    su propio ``QVBoxLayout(self)``). El borde va en un 'frame' interno con su
    propio stylesheet, de modo que sobreviva aunque la subclase llame a
    ``setStyleSheet`` sobre el diálogo.

    Para diálogos de tamaño fijo, fija el CUERPO en vez del diálogo:
        self._body.setFixedSize(w, h)
    así el área de contenido queda idéntica a la de antes y la barra de título
    se suma por encima.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._frame = QWidget()
        self._frame.setObjectName("ImagoDialogFrame")
        self._frame.setStyleSheet(theme.frame_qss("ImagoDialogFrame"))
        frame_lay = QVBoxLayout(self._frame)
        frame_lay.setContentsMargins(1, 1, 1, 1)
        frame_lay.setSpacing(0)

        self.title_bar = CustomTitleBar(
            self, self.windowTitle(), icon_path=":/icons/imago.png",
            show_min_max=False, btn_width=34)
        frame_lay.addWidget(self.title_bar)

        # Línea separadora explícita (1px) entre la barra de título y el cuerpo.
        # Un widget propio es más fiable que un border-bottom por stylesheet, que
        # los botones de altura completa podían tapar.
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: %s;" % theme.BORDER)
        frame_lay.addWidget(sep)

        # Cuerpo: las subclases meten aquí su contenido (self.body_layout).
        # Sin tocar los márgenes -> usa los de por defecto, igual que el antiguo
        # QVBoxLayout(self), para conservar el área de contenido.
        self._body = QWidget()
        self.body_layout = QVBoxLayout(self._body)
        frame_lay.addWidget(self._body)

        outer.addWidget(self._frame)


# ===========================================================================
#  Caja de mensaje sin marco (reemplazo de QMessageBox con barra de título
#  oscura). Las funciones imago_* devuelven los mismos valores StandardButton
#  que QMessageBox, así la lógica de cada llamada no cambia.
# ===========================================================================
def _msg_qss():
    """Estilo de la caja de mensaje. Función (no constante de módulo): una
    constante congelaría los tokens con el tema del import (oscuro) y no
    cambiaría al conmutar a claro con use_theme()."""
    return (
        "QLabel { color: %s; font-family: 'Segoe UI'; font-size: 12px; }\n" % theme.TEXT
        + theme.dialog_button_qss("QPushButton#MsgButton")
    )


class ImagoMessageBox(FramelessDialog):
    """Caja de mensaje modal sin marco, con barra de título oscura."""

    def __init__(self, parent=None, title="", text="", icon_kind=None, min_width=340):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self._value = None
        self._centered = False
        self.setStyleSheet(_msg_qss())
        self._body.setMinimumWidth(min_width)

        row = QHBoxLayout()
        row.setContentsMargins(4, 4, 4, 4)
        row.setSpacing(12)
        if icon_kind:
            icon_lbl = QLabel()
            icon_lbl.setPixmap(self._std_pixmap(icon_kind))
            icon_lbl.setFixedSize(40, 40)
            row.addWidget(icon_lbl, 0, Qt.AlignTop)
        text_lbl = QLabel(text)
        text_lbl.setWordWrap(True)
        row.addWidget(text_lbl, 1)
        self.body_layout.addLayout(row)
        self.body_layout.addSpacing(14)

        self._btn_row = QHBoxLayout()
        self._btn_row.addStretch()
        self.body_layout.addLayout(self._btn_row)

    def showEvent(self, event):
        # Centrar la caja SOBRE la ventana de Imago (no en una esquina): con la
        # ventana maximizada, la colocación por defecto de Qt salía desviada. Se
        # hace UNA vez, ya con el tamaño final del contenido (word-wrap incluido).
        super().showEvent(event)
        if not self._centered:
            self._centered = True
            self._center_on_parent()

    def _center_on_parent(self):
        par = self.parent().window() if self.parent() is not None else None
        if par is not None and par.isVisible():
            ref = par.frameGeometry()               # ventana de Imago (global)
        else:
            scr = (par.screen() if par is not None else None) or QApplication.primaryScreen()
            ref = scr.availableGeometry()
        geo = self.frameGeometry()
        geo.moveCenter(ref.center())
        self.move(geo.topLeft())

    def _std_pixmap(self, kind):
        table = {
            "info": QStyle.StandardPixmap.SP_MessageBoxInformation,
            "warning": QStyle.StandardPixmap.SP_MessageBoxWarning,
            "critical": QStyle.StandardPixmap.SP_MessageBoxCritical,
            "question": QStyle.StandardPixmap.SP_MessageBoxQuestion,
        }
        sp = table.get(kind, QStyle.StandardPixmap.SP_MessageBoxInformation)
        return QApplication.style().standardIcon(sp).pixmap(40, 40)

    def add_button(self, label, value, default=False):
        b = QPushButton(label)
        b.setObjectName("MsgButton")
        b.clicked.connect(lambda _=False, v=value: self._choose(v))
        if default:
            b.setDefault(True)
        self._btn_row.addWidget(b)
        return b

    def _choose(self, value):
        self._value = value
        self.accept()

    def value(self):
        return self._value


def _build_message(parent, icon_kind, title, text, buttons, default):
    box = ImagoMessageBox(parent, title, text, icon_kind)
    # Orden de aparición de los botones estándar (estilo Windows/Qt)
    order = [
        (QMessageBox.Save, t("msg.save", default="Guardar")),
        (QMessageBox.Yes, t("msg.yes", default="Sí")),
        (QMessageBox.Ok, t("msg.ok", default="Aceptar")),
        (QMessageBox.Discard, t("msg.discard", default="Descartar")),
        (QMessageBox.No, t("msg.no", default="No")),
        (QMessageBox.Cancel, t("msg.cancel", default="Cancelar")),
    ]
    for flag, label in order:
        if int(buttons) & int(flag):
            box.add_button(label, flag, default=(flag == default))
    box.exec()
    v = box.value()
    if v is not None:
        return v
    # Cerrado con la X: si había Cancelar, equivale a Cancelar; si no, a Aceptar.
    return QMessageBox.Cancel if (int(buttons) & int(QMessageBox.Cancel)) else QMessageBox.Ok


def imago_information(parent, title, text, buttons=QMessageBox.Ok, default=None):
    return _build_message(parent, "info", title, text, buttons, default)


def imago_warning(parent, title, text, buttons=QMessageBox.Ok, default=None):
    return _build_message(parent, "warning", title, text, buttons, default)


def imago_critical(parent, title, text, buttons=QMessageBox.Ok, default=None):
    return _build_message(parent, "critical", title, text, buttons, default)


def imago_question(parent, title, text, buttons=(QMessageBox.Yes | QMessageBox.No), default=None):
    return _build_message(parent, "question", title, text, buttons, default)