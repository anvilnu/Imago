# widgets/tab_thumbnails.py
"""Barra de miniaturas de pestañas (extraída de main.py TAL CUAL).

_ThumbButton (miniatura clicable con 'x' de cerrar), _ThumbStrip (tira
interior) y TabThumbnailBar (la barra completa con flechas de desplazamiento),
que MainWindow crea en __init__ y refresca al cambiar de pestaña/documento."""
from PySide6.QtCore import Qt, QSize, QFile, QTimer
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QPushButton,
                               QSizePolicy)

from utilidades import _canvas_thumb_pixmap
import theme

class _ThumbButton(QWidget):
    """Miniatura de un documento: imagen de ancho fijo, borde azul si está activa
    y una 'x' de cerrar que solo aparece al pasar el ratón por encima."""
    W = 88
    H = 50

    def __init__(self, bar, index):
        super().__init__()
        self.bar = bar
        self.index = index
        self.active = False
        self._pixmap = None
        self.setFixedSize(self.W, self.H)
        self.setCursor(Qt.PointingHandCursor)
        self.close_btn = QPushButton("\u2715", self)
        self.close_btn.setFixedSize(16, 16)
        self.close_btn.setCursor(Qt.PointingHandCursor)
        # Mismo estilo de X que el resto de la app (como el cierre de los paneles):
        # transparente, gris fina, y roja con un leve destello al pasar el ratón.
        self.close_btn.setStyleSheet(
            "QPushButton { background-color:rgba(255,68,68,1.0); border-radius:0px;"
            " font-family:'Segoe UI','Arial'; font-size:10px; font-weight:bold; }"
            " QPushButton:hover { color:#ffffff;"
            " background-color:rgba(255,68,68,1.0); border-radius:0px; }")
        self.close_btn.move(self.W - 19, 2)
        self.close_btn.hide()
        self.close_btn.clicked.connect(self._on_close)

    def set_pixmap(self, pm):
        self._pixmap = pm
        self.update()

    def set_active(self, active):
        if active != self.active:
            self.active = active
            self.update()

    def enterEvent(self, e):
        self.close_btn.show()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.close_btn.hide()
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.bar.main_window.tabs.setCurrentIndex(self.index)
        super().mousePressEvent(e)

    def _on_close(self):
        self.bar.main_window.close_tab(self.index)

    def paintEvent(self, e):
        from PySide6.QtGui import QPainter, QPen, QColor
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), QColor(theme.BG_WINDOW))
        if self._pixmap is not None and not self._pixmap.isNull():
            pm = self._pixmap
            x = (self.width() - pm.width()) // 2
            y = (self.height() - pm.height()) // 2
            p.drawPixmap(x, y, pm)
        if self.active:
            pen = QPen(QColor(theme.ACCENT)); pen.setWidth(2)
        else:
            pen = QPen(QColor(theme.BORDER_BUTTON)); pen.setWidth(1)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRect(self.rect().adjusted(1, 1, -2, -2))
        p.end()


class _ThumbStrip(QWidget):
    """Contenedor de las miniaturas que NUNCA impone ancho mínimo (su anchura la
    manda la ventana). Evita que la tira fuerce el ancho de la ventana."""
    def minimumSizeHint(self):
        return QSize(0, 0)


class TabThumbnailBar(QWidget):
    """Tira de miniaturas por páginas: muestra solo las que caben ENTERAS en el
    ancho disponible (nunca recortadas) y las flechas pasan página, manteniendo
    la vista siempre llena (la última página enseña las últimas que caben, no una
    sola). No impone ancho mínimo. self.tabs sigue siendo el almacén de datos."""

    STRIDE = _ThumbButton.W + 6      # ancho de miniatura + separación

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.setFixedHeight(58)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._buttons = []
        self._start = 0

        root = QHBoxLayout(self)
        root.setContentsMargins(4, 0, 6, 0)
        root.setSpacing(4)

        self.btn_left = QPushButton()
        # Si existe icons/left_arrow.png se usa esa imagen; si no, el s\u00edmbolo \u2039.
        if QFile.exists(":/icons/left_arrow.png"):
            self.btn_left.setIcon(theme.icono(":/icons/left_arrow.png"))
            self.btn_left.setIconSize(QSize(14, 14))
        else:
            self.btn_left.setText("\u2039")
        self.btn_left.setCursor(Qt.PointingHandCursor)
        self.btn_left.setFixedSize(20, 20)
        self.btn_left.setStyleSheet(self._arrow_style())
        self.btn_left.clicked.connect(lambda: self._shift(-1))
        self.btn_left.hide()
        root.addWidget(self.btn_left)

        self._strip = _ThumbStrip()
        self._strip.setMinimumWidth(0)
        self._strip.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._strip_layout = QHBoxLayout(self._strip)
        self._strip_layout.setContentsMargins(0, 0, 0, 0)
        self._strip_layout.setSpacing(6)
        self._strip_layout.addStretch(1)
        root.addWidget(self._strip, stretch=1)

        self.btn_right = QPushButton()
        # Si existe icons/right_arrow.png se usa esa imagen; si no, el s\u00edmbolo \u203a.
        if QFile.exists(":/icons/right_arrow.png"):
            self.btn_right.setIcon(theme.icono(":/icons/right_arrow.png"))
            self.btn_right.setIconSize(QSize(14, 14))
        else:
            self.btn_right.setText("\u203a")
        self.btn_right.setCursor(Qt.PointingHandCursor)
        self.btn_right.setFixedSize(20, 20)
        self.btn_right.setStyleSheet(self._arrow_style())
        self.btn_right.clicked.connect(lambda: self._shift(1))
        self.btn_right.hide()
        root.addWidget(self.btn_right)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(1200)
        self._refresh_timer.timeout.connect(self._refresh_active_thumb)
        self._refresh_timer.start()

    def _arrow_style(self):
        return theme.arrow_button_qss()

    def _make_thumb(self, canvas):
        try:
            # NO usar canvas.grab(): a zoom alto el widget puede medir
            # decenas de miles de px (p.ej. 114000x76080 ≈ 34 GB) y bloquear la
            # app. Componemos la imagen a TAMAÑO BASE y la reducimos a miniatura.
            return _canvas_thumb_pixmap(
                canvas, _ThumbButton.W - 10, _ThumbButton.H - 10)
        except Exception:
            return None

    def _capacity(self):
        # Cuántas miniaturas ENTERAS caben (reservando hueco para las flechas).
        avail = self.width() - 10 - 48
        if avail < self.STRIDE:
            return 1
        return max(1, (avail + 6) // self.STRIDE)

    def rebuild(self):
        for b in self._buttons:
            b.setParent(None)
            b.deleteLater()
        self._buttons = []
        tabs = self.main_window.tabs
        for i in range(tabs.count()):
            marker = tabs.widget(i)
            btn = _ThumbButton(self, i)
            if marker is not None and hasattr(marker, 'canvas'):
                btn.set_pixmap(self._make_thumb(marker.canvas))
            self._strip_layout.insertWidget(i, btn)
            self._buttons.append(btn)
        self._update_active()
        QTimer.singleShot(0, self._relayout_active)

    def _update_active(self):
        cur = self.main_window.tabs.currentIndex()
        for i, b in enumerate(self._buttons):
            b.set_active(i == cur)

    def _refresh_active_thumb(self):
        cur = self.main_window.tabs.currentIndex()
        if 0 <= cur < len(self._buttons):
            marker = self.main_window.tabs.widget(cur)
            if marker is not None and hasattr(marker, 'canvas'):
                self._buttons[cur].set_pixmap(self._make_thumb(marker.canvas))

    def _relayout(self, ensure_active=False):
        n = len(self._buttons)
        cap = self._capacity()
        max_start = max(0, n - cap)
        if ensure_active:
            cur = self.main_window.tabs.currentIndex()
            if 0 <= cur < n:
                if cur < self._start:
                    self._start = cur
                elif cur >= self._start + cap:
                    self._start = cur - cap + 1
        self._start = max(0, min(self._start, max_start))
        for i, b in enumerate(self._buttons):
            b.setVisible(self._start <= i < self._start + cap)
        overflow = n > cap
        self.btn_left.setVisible(overflow)
        self.btn_right.setVisible(overflow)
        if overflow:
            self.btn_left.setEnabled(self._start > 0)
            self.btn_right.setEnabled(self._start + cap < n)

    def _relayout_active(self):
        self._relayout(ensure_active=True)

    def _shift(self, direction):
        cap = self._capacity()
        self._start += direction * cap
        self._relayout(ensure_active=False)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        QTimer.singleShot(0, self._relayout_active)


