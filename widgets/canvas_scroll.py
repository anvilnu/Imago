# widgets/canvas_scroll.py
"""Área de scroll del lienzo (extraída de main.py TAL CUAL).

CanvasFrameOverlay (marco y sombra alrededor del lienzo, pintado sobre el
viewport) y CanvasScrollArea (QScrollArea que lo sincroniza y reenvía los
clics del fondo al canvas para deseleccionar). Cada pestaña crea la suya en
create_new_tab_canvas."""
from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import QScrollArea, QWidget

class CanvasFrameOverlay(QWidget):
    """Overlay transparente, por encima del lienzo, que dibuja un marco sutil
    ceñido a la IMAGEN (no al widget): aunque el widget crezca por los márgenes
    de vista al sacar una selección, el marco sigue pegado al borde de la imagen.
    Al ser un widget aparte, se repinta entero (no pierde lados ni deja rastro) y
    no interfiere con el desplazamiento."""

    FRAME = (110, 110, 110)   # gris sutil, más claro que el fondo (#404040)

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.canvas = None

    def paintEvent(self, event):
        w = self.canvas
        if w is None or not w.isVisible():
            return
        bw = getattr(w, 'base_width', None)
        bh = getattr(w, 'base_height', None)
        if bw is None or bh is None:
            return
        import math
        z = getattr(w, 'zoom_factor', 1.0)
        ml = getattr(w, 'margin_left', 0)
        mt = getattr(w, 'margin_top', 0)
        Mh = int(round(ml * z))   # margen horizontal en píxeles de pantalla (0 si no hay)
        Mv = int(round(mt * z))   # margen vertical en píxeles de pantalla
        # Esquina superior-izquierda de la IMAGEN (no del widget), vía coords
        # globales para no depender de la jerarquía ni del scroll actual.
        tl = self.mapFromGlobal(w.mapToGlobal(QPoint(Mh, Mv)))
        L, T = tl.x(), tl.y()
        # Ancho/alto de la imagen EN PANTALLA, cuadrado con el tamaño real del
        # widget: SIN márgenes el lienzo se recorta al entero inferior (int),
        # CON márgenes se dibuja completo (ceil). Así la separación del marco es
        # SIEMPRE de 2 px en los cuatro lados, sea cual sea el zoom.
        img_w = int(bw * z) if Mh == 0 else math.ceil(bw * z)
        img_h = int(bh * z) if Mv == 0 else math.ceil(bh * z)
        R = L + img_w - 1
        B = T + img_h - 1
        from PySide6.QtGui import QPainter, QPen, QColor
        p = QPainter(self)
        pen = QPen(QColor(*self.FRAME))
        pen.setWidth(1)
        pen.setCosmetic(True)
        p.setPen(pen)
        # 2 px por FUERA de la imagen en cada lado. ACOTAMOS al área visible
        # del overlay: a zoom alto sobre imágenes grandes, R y B llegan a
        # decenas de miles de px y dibujar líneas con esas coordenadas dispara
        # el motor de Qt (cuelgue). Solo trazamos el tramo que cae en pantalla.
        W, H = self.width(), self.height()
        M = 4
        def cx(v): return max(-M, min(W + M, v))
        def cy(v): return max(-M, min(H + M, v))
        yt, yb = T - 2, B + 2
        xl, xr = L - 2, R + 2
        if -M <= yt <= H + M:
            p.drawLine(cx(xl), yt, cx(xr), yt)   # arriba
        if -M <= yb <= H + M:
            p.drawLine(cx(xl), yb, cx(xr), yb)   # abajo
        if -M <= xl <= W + M:
            p.drawLine(xl, cy(yt), xl, cy(yb))   # izquierda
        if -M <= xr <= W + M:
            p.drawLine(xr, cy(yt), xr, cy(yb))   # derecha
        p.end()


class CanvasScrollArea(QScrollArea):
    """QScrollArea con un overlay que dibuja el marco del lienzo, ceñido a la
    imagen, sin interferir con el desplazamiento ni con el anclaje de márgenes."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Viewport PROPIO (no el interno de QScrollArea): con mucho trasiego de
        # widgets, self.viewport() de PySide6 llegaba a devolver un wrapper con el
        # tipo equivocado (un QWidgetItem) y reventaba al crear el overlay. Con un
        # viewport creado por nosotros el tipo está garantizado; lo guardamos y lo
        # usamos (self._viewport) para no volver a exponernos al glitch.
        vp = QWidget()
        self.setViewport(vp)
        self._viewport = vp
        self._frame_overlay = CanvasFrameOverlay(vp)
        # Capturar los clics que caen en el fondo gris (fuera del lienzo) para
        # poder INICIAR selecciones desde fuera, reenviándolos al lienzo.
        vp.installEventFilter(self)

    def setWidget(self, w):
        super().setWidget(w)
        self._frame_overlay.canvas = w
        if w is not None:
            w.installEventFilter(self)
        self._sync_frame()

    def _sync_frame(self):
        ov = self._frame_overlay
        ov.setGeometry(self._viewport.rect())
        ov.raise_()
        ov.update()

    # Herramientas que pueden EMPEZAR su acción desde FUERA del lienzo (fondo
    # gris): se reenvía el evento al lienzo con las coordenadas traducidas (quedan
    # fuera de la imagen) para trabajar los bordes con naturalidad. Se excluyen las
    # que necesitan un píxel bajo el cursor (cubo, cuentagotas, varita) o tienen
    # interacción propia (texto, mover, mano, pluma).
    _FORWARD_TOOLS = (
        "select_rect", "select_ellipse", "select_lasso",
        "pen", "pencil", "eraser", "airbrush", "clone", "smudge",
        "replace_color", "gradient", "shape",
    )

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        # Clics en el fondo gris (viewport): si la herramienta activa lo admite,
        # los reenviamos al lienzo para empezar su acción desde fuera.
        if obj is self._viewport and event.type() in (
                QEvent.Type.MouseButtonPress, QEvent.Type.MouseMove,
                QEvent.Type.MouseButtonRelease, QEvent.Type.MouseButtonDblClick):
            if self._forward_bg_click(event):
                return True
        if obj is self.widget() and event.type() in (
                QEvent.Type.Resize, QEvent.Type.Move, QEvent.Type.Show):
            self._sync_frame()
        return super().eventFilter(obj, event)

    def _forward_bg_click(self, event):
        """Reenvía un evento de ratón del fondo gris al lienzo (con las coords
        traducidas, que quedarán fuera del lienzo). Para las herramientas de
        _FORWARD_TOOLS, así se puede empezar a pintar/seleccionar desde fuera."""
        from PySide6.QtCore import QEvent
        canvas = self.widget()
        if canvas is None:
            return False
        tool = getattr(canvas, "current_tool", None)
        tid = getattr(tool, "tool_id", "")
        if tid not in self._FORWARD_TOOLS:
            return False
        if getattr(canvas, "_space_panning", False):
            return False
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtCore import QPointF
        local = canvas.mapFrom(self._viewport, event.position().toPoint())
        ev = QMouseEvent(event.type(), QPointF(local), event.globalPosition(),
                         event.button(), event.buttons(), event.modifiers())
        t = event.type()
        if t == QEvent.Type.MouseButtonPress:
            canvas.mousePressEvent(ev)
        elif t == QEvent.Type.MouseMove:
            canvas.mouseMoveEvent(ev)
        elif t == QEvent.Type.MouseButtonRelease:
            canvas.mouseReleaseEvent(ev)
        elif t == QEvent.Type.MouseButtonDblClick:
            canvas.mouseDoubleClickEvent(ev)
        return True

    def scrollContentsBy(self, dx, dy):
        super().scrollContentsBy(dx, dy)
        self._frame_overlay.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_frame()


