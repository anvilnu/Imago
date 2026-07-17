from i18n import t
# widgets/overlay_panel.py
"""Panel OVERLAY: un QWidget HIJO de la ventana principal (NO una ventana del SO),
superpuesto sobre el lienzo, con barra de título propia ARRASTRABLE dentro de la
ventana (coordenadas LOCALES, acotado al contenedor).

Motivo: los antiguos Ajustes/Efectos con vista previa en vivo eran diálogos
`FramelessDialog` modales; en KDE/Wayland el compositor ATENÚA la ventana
principal cuando queda inactiva (efecto "Atenuar ventanas inactivas") y no se
apreciaba la preview. Al ser un HIJO y no una ventana aparte, la principal nunca
queda inactiva -> ningún compositor la atenúa, en cualquier SO. Y como se mueve
en coordenadas locales (no `startSystemMove`) es Wayland-safe por diseño.
Ver migrar_dialogos_a_overlay.md.

Replica la "superficie" de FramelessDialog (un `_frame` temado con
`theme.frame_qss` + `self.body_layout`) para que las subclases (AdjustmentDialog)
apenas cambien. Las subclases sobreescriben accept()/reject(); por defecto solo
cierran el panel.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PySide6.QtCore import Qt, QPoint, QEvent, Signal
import theme
import app_paths
from widgets.custom_titlebar import _CaptionButton


class _OverlayTitleBar(QWidget):
    """Barra de título ligera para un overlay HIJO. Arrastra el panel padre con
    coordenadas LOCALES (delta de ratón global aplicado a la posición en el
    padre, acotado) en vez de `startSystemMove` (que mueve una ventana del SO)."""

    def __init__(self, panel, title="", height=32, parent=None):
        super().__init__(parent or panel)
        self._panel = panel
        self._press_global = None
        self._start_pos = None
        self.setObjectName("OverlayTitleBar")
        self.setFixedHeight(height)
        self.setStyleSheet(
            "#OverlayTitleBar { background-color: %s; }"
            "#OverlayTitleBar QLabel#TitleText { color: %s; font-family:'Segoe UI',Arial; font-size:12px; }"
            % (theme.BG_DARK, theme.TEXT)
        )

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 0, 0, 0)
        lay.setSpacing(8)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("TitleText")
        lay.addWidget(self.title_label)
        lay.addStretch()

        # La X cancela (punto de diseño 3: X = Cancelar).
        self.btn_close = _CaptionButton("close", height, 34)
        lay.addWidget(self.btn_close)
        self.btn_close.clicked.connect(self._panel.reject)

    def set_title(self, text):
        self.title_label.setText(text)

    # ----------------------------------------------------------- arrastrar
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._press_global = event.globalPosition().toPoint()
            self._start_pos = self._panel.pos()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._press_global is None or not (event.buttons() & Qt.LeftButton):
            return
        # El delta en coordenadas globales equivale al delta en coordenadas del
        # padre (no hay escala/rotación), así que se puede sumar a la posición.
        delta = event.globalPosition().toPoint() - self._press_global
        self._panel.move_clamped(self._start_pos + delta)
        event.accept()

    def mouseReleaseEvent(self, event):
        self._press_global = None
        self._start_pos = None
        event.accept()


class OverlayPanel(QWidget):
    """Base de un panel overlay superpuesto al lienzo.

    Superficie equivalente a FramelessDialog:
      - `self._frame`: marco temado (theme.frame_qss).
      - `self.title_bar`: barra propia con título + cerrar, arrastrable.
      - `self._body` / `self.body_layout`: donde las subclases meten su contenido.

    API compatible con lo que usa AdjustmentDialog:
      - `setWindowTitle()` actualiza también la barra.
      - `accept()` / `reject()` virtuales (por defecto cierran el panel); las
        subclases los sobreescriben y llaman a `super()` para cerrar.
      - `open_over(main_window)` lo superpone sobre el área del lienzo.
    """

    # Se emite justo antes de destruir el panel (para que main.py libere la
    # instancia única y restaure la interacción del lienzo).
    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._title = ""
        self._host = None       # área sobre la que se superpone (content_container)
        self._is_closed = False
        self._qsettings = None  # QSettings para recordar la última posición
        # Foco fuerte para recibir Esc/Enter aunque ningún hijo tenga el foco.
        self.setFocusPolicy(Qt.StrongFocus)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._frame = QWidget()
        self._frame.setObjectName("ImagoOverlayFrame")
        self._frame.setStyleSheet(theme.frame_qss("ImagoOverlayFrame"))
        frame_lay = QVBoxLayout(self._frame)
        frame_lay.setContentsMargins(1, 1, 1, 1)
        frame_lay.setSpacing(0)

        self.title_bar = _OverlayTitleBar(self, self._title)
        frame_lay.addWidget(self.title_bar)

        # Línea separadora explícita (1px) entre barra y cuerpo, igual que en
        # FramelessDialog (más fiable que un border-bottom por stylesheet).
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: %s;" % theme.BORDER)
        frame_lay.addWidget(sep)

        # Cuerpo: las subclases meten aquí su contenido (self.body_layout), sin
        # tocar los márgenes por defecto -> área de contenido idéntica a la del
        # antiguo QVBoxLayout(self).
        self._body = QWidget()
        self.body_layout = QVBoxLayout(self._body)
        frame_lay.addWidget(self._body)

        outer.addWidget(self._frame)

    # ---- compat con la API de FramelessDialog/QDialog ----
    def setWindowTitle(self, text):
        super().setWindowTitle(text)
        self._title = text
        self.title_bar.set_title(text)

    # ---- colocación / arrastre ----
    def move_clamped(self, pos):
        """Mueve el panel a `pos` (coordenadas del padre) acotándolo para que no
        se salga del contenedor. `pos` puede ser un QPoint."""
        parent = self.parentWidget()
        if parent is None:
            self.move(pos)
            return
        max_x = max(0, parent.width() - self.width())
        max_y = max(0, parent.height() - self.height())
        x = min(max(pos.x(), 0), max_x)
        y = min(max(pos.y(), 0), max_y)
        self.move(x, y)

    def open_over(self, main_window, position=None):
        """Superpone el panel sobre el área del lienzo de `main_window`.

        Lo reparenta al `content_container` (o al central si no existe), lo
        dimensiona a su sizeHint y lo posiciona. Por defecto arriba-derecha del
        lienzo (la persistencia de la última posición se añade en una fase
        posterior). No es modal: se muestra y se sube al frente."""
        host = (getattr(main_window, "content_container", None)
                or main_window.centralWidget() or main_window)
        self._host = host
        # Reutiliza el QSettings de la ventana (misma org/app) para recordar la
        # última posición; si no lo expone, crea uno con la misma clave.
        self._qsettings = (getattr(main_window, "settings", None)
                           or app_paths.settings())
        self.setParent(host)
        # Reclampar el overlay cuando el área del lienzo cambie de tamaño
        # (redimensionar/maximizar la ventana, ocultar paneles, arrastrar
        # splitters -> todos disparan un Resize de este contenedor).
        host.installEventFilter(self)
        self.adjustSize()
        margin = 16
        if position is None:
            position = self._read_saved_pos()
        if position is None:
            x = max(0, host.width() - self.width() - margin)
            position = QPoint(x, margin)
        self.move_clamped(position)
        self.show()
        self.raise_()
        self.setFocus(Qt.OtherFocusReason)

    # ---- persistencia de la última posición (QSettings) ----
    def _read_saved_pos(self):
        """Última posición guardada (coords del padre) o None si no hay/ inválida."""
        if self._qsettings is None:
            return None
        x = self._qsettings.value("overlay/last_x", None)
        y = self._qsettings.value("overlay/last_y", None)
        if x is None or y is None:
            return None
        try:
            return QPoint(int(x), int(y))
        except (TypeError, ValueError):
            return None

    def _save_pos(self):
        if self._qsettings is None:
            return
        self._qsettings.setValue("overlay/last_x", int(self.x()))
        self._qsettings.setValue("overlay/last_y", int(self.y()))

    # ---- clamp al redimensionarse el contenedor del lienzo ----
    def eventFilter(self, obj, event):
        if obj is self._host and event.type() == QEvent.Resize:
            # Mantener el panel dentro del área visible tras el cambio de tamaño.
            self.move_clamped(self.pos())
        return super().eventFilter(obj, event)

    # ---- teclado (punto de diseño 3: Enter=Aceptar, Esc=Cancelar) ----
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.reject()
            event.accept()
            return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.accept()
            event.accept()
            return
        super().keyPressEvent(event)

    # ---- ciclo de vida (equivalentes a QDialog.accept/reject) ----
    def accept(self):
        """Aceptar. Las subclases sobreescriben para confirmar y luego cierran
        llamando a super().accept()."""
        self._close_panel()

    def reject(self):
        """Cancelar. Las subclases sobreescriben para deshacer y luego cierran
        llamando a super().reject()."""
        self._close_panel()

    def _close_panel(self):
        if self._is_closed:
            return
        self._is_closed = True
        if self._host is not None:
            self._save_pos()   # recuerda dónde quedó para el próximo overlay
            self._host.removeEventFilter(self)
        self.hide()
        self.closed.emit()
        self.setParent(None)
        self.deleteLater()
