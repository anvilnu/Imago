# widgets/fullscreen_viewer.py
"""Visor a PANTALLA COMPLETA (solo la imagen) para revisar el trabajo.

Es una ventana top-level propia que se abre con showFullScreen() y dibuja la
imagen compuesta del lienzo centrada y escalada sobre un fondo neutro, con:
  - Zoom con la rueda (anclado al cursor) y con + / -.
  - Desplazamiento (pan) arrastrando con el botón izquierdo o central.
  - Ajustar a pantalla con doble clic, F o 0.
  - Esc o F11 para cerrar.

Wayland-safe: showFullScreen() no depende de posicionar en coordenadas globales
(a diferencia de las viejas paletas Qt.Tool), así que funciona en Wayland puro
igual que en Windows. La imagen se compone con canvas.render_flat_image(), que
NO modifica el documento.
"""

from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter, QColor
from PySide6.QtCore import Qt, QPointF, QRectF
import theme


class FullScreenViewer(QWidget):
    """Muestra un QImage a pantalla completa con zoom y desplazamiento."""

    _MIN_ZOOM = 0.02
    _MAX_ZOOM = 40.0
    _STEP = 1.15

    def __init__(self, image, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self._image = image
        self._zoom = 1.0
        self._offset = QPointF(0, 0)     # desplazamiento del centro respecto al centro de la pantalla
        self._panning = False
        self._pan_last = None
        self._user_interacted = False    # mientras sea False, la imagen se reajusta al redimensionar
        self.setWindowTitle("Imago")
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

    # ------------------------------------------------------------------
    # Encaje / geometría
    # ------------------------------------------------------------------
    def _fit(self):
        """Ajusta el zoom para que la imagen quepa entera y centrada."""
        if self._image.isNull():
            return
        iw, ih = self._image.width(), self._image.height()
        if iw <= 0 or ih <= 0:
            return
        self._zoom = min(self.width() / iw, self.height() / ih)
        self._offset = QPointF(0, 0)
        self.update()

    def _actual_size(self):
        """Tamaño real (100%): 1 píxel de imagen = 1 píxel de pantalla, centrado."""
        self._user_interacted = True
        self._zoom = 1.0
        self._offset = QPointF(0, 0)
        self._clamp_offset()
        self.update()

    def _target_rect(self):
        iw = self._image.width() * self._zoom
        ih = self._image.height() * self._zoom
        cx = self.width() / 2 + self._offset.x()
        cy = self.height() / 2 + self._offset.y()
        return QRectF(cx - iw / 2, cy - ih / 2, iw, ih)

    def _clamp_offset(self):
        """Acota el desplazamiento para que la imagen no se pueda arrastrar más
        allá de sus bordes: si un lado es MAYOR que la pantalla, se puede
        desplazar hasta que su borde llegue al borde de la pantalla; si es MENOR
        o igual (cabe entero), queda centrado en ese eje."""
        if self._image.isNull():
            return
        iw = self._image.width() * self._zoom
        ih = self._image.height() * self._zoom
        max_x = max(0.0, (iw - self.width()) / 2)
        max_y = max(0.0, (ih - self.height()) / 2)
        x = max(-max_x, min(self._offset.x(), max_x))
        y = max(-max_y, min(self._offset.y(), max_y))
        self._offset = QPointF(x, y)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Hasta que el usuario toque zoom/pan, la imagen se reajusta al tamaño
        # actual (incluye el primer redimensionado al pasar a pantalla completa).
        if not self._user_interacted:
            self._fit()

    # ------------------------------------------------------------------
    # Pintado
    # ------------------------------------------------------------------
    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(theme.BG_TILE))
        if not self._image.isNull():
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            p.drawImage(self._target_rect(), self._image)
        p.end()

    # ------------------------------------------------------------------
    # Zoom
    # ------------------------------------------------------------------
    def _clamp(self, z):
        return max(self._MIN_ZOOM, min(z, self._MAX_ZOOM))

    def wheelEvent(self, event):
        self._user_interacted = True
        old = self._zoom
        new = self._clamp(old * (self._STEP if event.angleDelta().y() > 0 else 1 / self._STEP))
        if new == old:
            return
        # Anclaje: el punto de la imagen bajo el cursor se queda fijo.
        sc = QPointF(self.width() / 2, self.height() / 2)
        centro = sc + self._offset
        u = event.position()
        f = new / old
        self._zoom = new
        self._offset = centro * f + u * (1 - f) - sc
        self._clamp_offset()
        self.update()

    def _zoom_centro(self, factor):
        self._user_interacted = True
        old = self._zoom
        new = self._clamp(old * factor)
        if new == old:
            return
        # Anclado al centro de la pantalla: el offset escala igual que el zoom.
        self._offset = self._offset * (new / old)
        self._zoom = new
        self._clamp_offset()
        self.update()

    # ------------------------------------------------------------------
    # Ratón (pan)
    # ------------------------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton):
            self._panning = True
            self._pan_last = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if self._panning and self._pan_last is not None:
            self._user_interacted = True
            self._offset += event.position() - self._pan_last
            self._pan_last = event.position()
            self._clamp_offset()
            self.update()

    def mouseReleaseEvent(self, event):
        self._panning = False
        self._pan_last = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mouseDoubleClickEvent(self, event):
        # Doble clic: volver a ajustar a pantalla.
        self._user_interacted = False
        self._fit()

    # ------------------------------------------------------------------
    # Teclado
    # ------------------------------------------------------------------
    def keyPressEvent(self, event):
        k = event.key()
        if k in (Qt.Key.Key_Escape, Qt.Key.Key_F11):
            self.close()
        elif k in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self._zoom_centro(self._STEP)
        elif k == Qt.Key.Key_Minus:
            self._zoom_centro(1 / self._STEP)
        elif k in (Qt.Key.Key_F, Qt.Key.Key_0):
            self._user_interacted = False
            self._fit()
        elif k == Qt.Key.Key_1:
            self._actual_size()
        else:
            super().keyPressEvent(event)
