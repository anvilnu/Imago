# widgets/effect_controls.py
"""Controles interactivos para los diálogos de Efectos:
- CenterPicker: miniatura de la imagen con un tirador de 4 puntas que fija el
  centro del efecto (distorsión). Cursor mano abierta al pasar, cerrada al
  arrastrar. Emite centerChanged(x%, y%).
- AngleDial: dial circular con una manilla para fijar un ángulo de forma cómoda.
  Emite angleChanged(grados).
"""

import math
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter, QPen, QColor, QPixmap
from PySide6.QtCore import Qt, QPointF, QRectF, Signal
import theme


class CenterPicker(QWidget):
    """Miniatura de la imagen con un tirador de 4 puntas; al arrastrarlo se fija
    el centro del efecto. Emite centerChanged(x_pct, y_pct) en 0..100."""

    centerChanged = Signal(float, float)

    def __init__(self, qimage, max_w=170, max_h=150, parent=None):
        super().__init__(parent)
        self._pix = QPixmap.fromImage(qimage).scaled(
            max_w, max_h, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation)
        self.setFixedSize(self._pix.size())
        self._cx, self._cy = 0.5, 0.5     # fracciones 0..1
        self._dragging = False
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def setCenter(self, x_pct, y_pct):
        self._cx = max(0.0, min(1.0, x_pct / 100.0))
        self._cy = max(0.0, min(1.0, y_pct / 100.0))
        self.update()

    def _emit_from(self, pos):
        self._cx = max(0.0, min(1.0, pos.x() / max(1, self.width())))
        self._cy = max(0.0, min(1.0, pos.y() / max(1, self.height())))
        self.update()
        self.centerChanged.emit(self._cx * 100.0, self._cy * 100.0)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self._emit_from(e.position())

    def mouseMoveEvent(self, e):
        if self._dragging:
            self._emit_from(e.position())

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self.setCursor(Qt.CursorShape.OpenHandCursor)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.drawPixmap(0, 0, self._pix)
        p.setPen(QPen(QColor(theme.BORDER), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(0, 0, self.width() - 1, self.height() - 1)
        self._draw_handle(p, self._cx * self.width(), self._cy * self.height())

    def _draw_handle(self, p, cx, cy):
        r, ah = 11, 4
        segs = [((-r, 0), (r, 0)), ((0, -r), (0, r)),
                ((-r, 0), (-r + ah, -ah)), ((-r, 0), (-r + ah, ah)),
                ((r, 0), (r - ah, -ah)), ((r, 0), (r - ah, ah)),
                ((0, -r), (-ah, -r + ah)), ((0, -r), (ah, -r + ah)),
                ((0, r), (-ah, r - ah)), ((0, r), (ah, r - ah))]
        # dos pasadas (oscura gruesa + clara fina) para que se vea sobre cualquier fondo
        for pen in (QPen(QColor(0, 0, 0, 160), 4), QPen(QColor(255, 255, 255), 2)):
            p.setPen(pen)
            for (x1, y1), (x2, y2) in segs:
                p.drawLine(QPointF(cx + x1, cy + y1), QPointF(cx + x2, cy + y2))


class AngleDial(QWidget):
    """Dial circular con una manilla para fijar un ángulo. Emite angleChanged(grados),
    en convención de pantalla (0° a la derecha, crece en sentido horario), igual que
    los efectos que usan (dx, dy) = (cos, sin) con la Y hacia abajo."""

    angleChanged = Signal(float)

    def __init__(self, size=72, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._angle = 0.0
        self._dragging = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def setAngle(self, deg):
        self._angle = float(deg)
        self.update()

    def _emit_from(self, pos):
        cx, cy = self.width() / 2.0, self.height() / 2.0
        self._angle = math.degrees(math.atan2(pos.y() - cy, pos.x() - cx))
        self.update()
        self.angleChanged.emit(self._angle)

    def mousePressEvent(self, e):
        self._dragging = True
        self._emit_from(e.position())

    def mouseMoveEvent(self, e):
        if self._dragging:
            self._emit_from(e.position())

    def mouseReleaseEvent(self, e):
        self._dragging = False

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        m = 3
        rect = QRectF(m, m, self.width() - 2 * m, self.height() - 2 * m)
        p.setPen(QPen(QColor(theme.BORDER), 1.5))
        p.setBrush(QColor(theme.BG_DARK))
        p.drawEllipse(rect)
        cx, cy = self.width() / 2.0, self.height() / 2.0
        rad = rect.width() / 2.0 - 2.0
        a = math.radians(self._angle)
        hx, hy = cx + rad * math.cos(a), cy + rad * math.sin(a)
        p.setPen(QPen(QColor(theme.ACCENT), 2.5))
        p.drawLine(QPointF(cx, cy), QPointF(hx, hy))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(theme.ACCENT))
        p.drawEllipse(QPointF(cx, cy), 2.5, 2.5)
        p.drawEllipse(QPointF(hx, hy), 3.0, 3.0)
