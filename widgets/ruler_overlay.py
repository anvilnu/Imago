# widgets/ruler_overlay.py
import math
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter, QPen, QColor, QFont
from PySide6.QtCore import Qt, QPoint
import theme


class RulerOverlay(QWidget):
    """Reglas que bordean el ÁREA DE CONTENIDO (arriba e izquierda), pegadas
    al borde de la ventana tras las barras de herramientas, no al lienzo.

    Es un overlay transparente que se superpone al área del lienzo: lee del
    canvas el zoom, los márgenes y el desplazamiento del scroll para mapear
    coordenadas del lienzo a la pantalla. Dibuja además una línea azul que
    sigue la posición del cursor en ambas reglas.

    No interfiere con el ratón (transparente a eventos): las reglas son pura
    decoración informativa."""

    RULER_SIZE = 20
    DPI = 96.0  # Puntos por pulgada (convención de pantalla, como Paint.NET)
    PX_PER_CM = DPI / 2.54  # 1 pulgada = 2,54 cm → ≈ 37,8 px/cm

    def __init__(self, parent=None):
        super().__init__(parent)
        self.canvas = None
        self.scroll_area = None
        self.cursor_pos = None  # Posición del cursor en coords de lienzo (o None)
        self.unit = "px"        # "px" o "cm" — lo cambia el menú Ver
        # 'empty_mode': sin lienzo (pantalla de bienvenida) pero reglas activas;
        # se dibujan solo las bandas (el marco), sin marcas ni números.
        self.empty_mode = False
        # El overlay captura el ratón SOLO en las bandas de las reglas (vía
        # setMask en forma de "L"); el resto pasa al lienzo de debajo. Sobre las
        # bandas se pueden ARRASTRAR guías hacia el lienzo.
        self._creating = None     # 'h'/'v' mientras se arrastra una guía nueva
        self._mask_key = None     # cache para no re-aplicar la máscara sin cambios
        # Arranque INERTE al ratón: hasta que las reglas se muestren, todo clic
        # debe atravesar el overlay (lienzo o pantalla de bienvenida de debajo).
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def set_unit(self, unit):
        """Cambia la unidad mostrada en las reglas: 'px', 'cm' o 'in' (pulgadas)."""
        self.unit = unit if unit in ("px", "cm", "in") else "px"
        self.update()

    def set_empty_mode(self, on):
        """Activa/desactiva el modo 'solo bandas' (bienvenida, sin lienzo). Al
        activarlo se desvincula del lienzo para no usar uno ya cerrado."""
        self.empty_mode = bool(on)
        if on:
            self.canvas = None
            self.scroll_area = None
        self.update()

    def attach(self, scroll_area, canvas):
        """Vincula el overlay al lienzo activo y su scroll."""
        self.scroll_area = scroll_area
        self.canvas = canvas
        self.empty_mode = False
        self.update()

    def set_cursor_pos(self, logical_point):
        """El canvas nos informa de la posición del cursor (en coords de
        lienzo) para dibujar la guía azul. None = cursor fuera."""
        self.cursor_pos = logical_point
        self.update()

    # ------------------------------ máscara de entrada (solo bandas) ----------
    def _rulers_visible(self):
        return getattr(self, 'empty_mode', False) or (
            self.canvas is not None and self.scroll_area is not None
            and getattr(self.canvas, 'show_rulers', False))

    def _update_mask(self):
        """Limita la captura de ratón (y el pintado) a las bandas en 'L'. Si las
        reglas no están visibles, máscara vacía -> el ratón pasa entero al lienzo."""
        from PySide6.QtGui import QRegion
        show = self._rulers_visible()
        key = (show, self.width(), self.height())
        if key == self._mask_key:
            return
        self._mask_key = key
        if show:
            rs = self.RULER_SIZE
            region = QRegion(0, 0, self.width(), rs)
            region = region.united(QRegion(0, 0, rs, self.height()))
            self.setMask(region)
            self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        else:
            # ⚠️ TRAMPA DE QT: setMask(QRegion()) equivale a clearMask(), NO a
            # "no capturar nada": el overlay invisible volvía a capturar TODOS
            # los clics del área de contenido (bienvenida y lienzo muertos con
            # las reglas ocultas). Lo correcto es hacerse transparente al ratón.
            self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            self.clearMask()

    def resizeEvent(self, event):
        self._update_mask()
        super().resizeEvent(event)

    # ------------------------------ crear guías arrastrando -------------------
    def _overlay_to_canvas(self, pt):
        """Convierte un punto de ESTE overlay a coordenadas de lienzo (o None)."""
        origin = self._canvas_origin_in_overlay()
        if origin is None:
            return None
        z = self.canvas.zoom_factor or 1.0
        return ((pt.x() - origin.x()) / z, (pt.y() - origin.y()) / z)

    def _update_pending(self, pt):
        c = self._overlay_to_canvas(pt)
        if c is None or self._creating is None:
            return
        cx, cy = c
        if self._creating == 'h':
            val = max(0.0, min(float(self.canvas.base_height), cy))
        else:
            val = max(0.0, min(float(self.canvas.base_width), cx))
        self.canvas._pending_guide = {'orient': self._creating, 'pos': val}
        self.canvas.update()

    def mousePressEvent(self, event):
        # Solo se pueden sacar guías con las reglas visibles y las guías ACTIVAS
        # (botón de Guías encendido en este documento).
        if not (self.canvas is not None and self.scroll_area is not None
                and getattr(self.canvas, 'show_rulers', False)
                and getattr(self.canvas, 'show_guides', True)):
            event.ignore()
            return
        rs = self.RULER_SIZE
        x, y = event.position().x(), event.position().y()
        if y < rs and x >= rs:
            self._creating = 'h'      # banda superior -> guía horizontal
        elif x < rs and y >= rs:
            self._creating = 'v'      # banda izquierda -> guía vertical
        else:
            event.ignore()
            return
        self._update_pending(event.position())
        event.accept()

    def mouseMoveEvent(self, event):
        if self._creating:
            self._update_pending(event.position())
            event.accept()

    def mouseReleaseEvent(self, event):
        if not self._creating:
            return
        c = self._overlay_to_canvas(event.position())
        self.canvas._pending_guide = None
        if c is not None:
            cx, cy = c
            if self._creating == 'h' and 0 <= cy <= self.canvas.base_height:
                self.canvas.add_guide_committed('h', cy)
            elif self._creating == 'v' and 0 <= cx <= self.canvas.base_width:
                self.canvas.add_guide_committed('v', cx)
        self._creating = None
        self.canvas.update()
        event.accept()

    def _canvas_origin_in_overlay(self):
        """Esquina (0,0) del lienzo en coordenadas de ESTE overlay, teniendo
        en cuenta márgenes de vista y desplazamiento del scroll."""
        if self.canvas is None or self.scroll_area is None:
            return None
        z = self.canvas.zoom_factor
        # Origen del lienzo dentro del widget canvas (tras los márgenes)
        canvas_local = QPoint(int(self.canvas.margin_left * z),
                              int(self.canvas.margin_top * z))
        # Pasar a global y de ahí a coords del overlay
        global_pt = self.canvas.mapToGlobal(canvas_local)
        return self.mapFromGlobal(global_pt)

    def _paint_empty_bands(self):
        """Dibuja solo las bandas de las reglas y la etiqueta de unidad (sin
        marcas), para la pantalla de bienvenida cuando las reglas están activas."""
        painter = QPainter(self)
        rs = self.RULER_SIZE
        w, h = self.width(), self.height()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(theme.BG_DARK))
        painter.drawRect(0, 0, w, rs)
        painter.drawRect(0, 0, rs, h)
        painter.drawRect(0, 0, rs, rs)
        painter.setPen(QPen(QColor(theme.BORDER_SOFT), 1))
        painter.drawLine(0, rs, w, rs)
        painter.drawLine(rs, 0, rs, h)
        painter.setPen(QPen(QColor(theme.TEXT_DIM)))
        painter.setFont(QFont("Segoe UI", 7))
        painter.drawText(0, 0, rs, rs, Qt.AlignCenter, self.unit)
        painter.end()

    def paintEvent(self, event):
        self._update_mask()   # mantener la captura de ratón acorde a las reglas
        active = (self.canvas is not None and self.scroll_area is not None
                  and getattr(self.canvas, 'show_rulers', False))
        if not active:
            if self.empty_mode:
                self._paint_empty_bands()
            return

        origin = self._canvas_origin_in_overlay()
        if origin is None:
            return

        painter = QPainter(self)
        z = self.canvas.zoom_factor
        rs = self.RULER_SIZE
        w, h = self.width(), self.height()

        # Bandas de fondo (mismo gris que las barras de herramientas)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(theme.BG_DARK))
        painter.drawRect(0, 0, w, rs)        # Horizontal (arriba)
        painter.drawRect(0, 0, rs, h)        # Vertical (izquierda)
        painter.setBrush(QColor(theme.BG_DARK))
        painter.drawRect(0, 0, rs, rs)       # Esquina

        # Borde de separación con el fondo (gris, a juego con los demás bordes)
        painter.setPen(QPen(QColor(theme.BORDER_SOFT), 1))
        painter.drawLine(0, rs, w, rs)       # Bajo la regla horizontal
        painter.drawLine(rs, 0, rs, h)       # A la derecha de la vertical

        # 📐 Unidad activa: factor de píxeles por unidad y candidatos de
        # intervalo "redondos" en esa unidad. En cm las marcas caen en
        # centímetros enteros/medios; en px, en píxeles. Las POSICIONES
        # siempre se calculan en píxeles de lienzo: solo cambian el paso
        # entre marcas y el número que se escribe.
        if self.unit == "cm":
            px_per_unit = self.PX_PER_CM
            candidatos_u = [0.5, 1, 2, 5, 10, 20, 50, 100]  # centímetros
        elif self.unit == "in":
            px_per_unit = self.DPI                           # 96 px = 1 pulgada
            candidatos_u = [0.25, 0.5, 1, 2, 5, 10, 20, 50]  # pulgadas
        else:
            px_per_unit = 1.0
            candidatos_u = [1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000]

        # Elegir intervalo (en la unidad) que deje ~80px entre etiquetas
        intervalo_u = candidatos_u[-1]
        for c in candidatos_u:
            if c * px_per_unit * z >= 80:
                intervalo_u = c
                break
        intervalo = intervalo_u * px_per_unit       # paso en píxeles (mayor)
        menor = intervalo / 5.0                       # paso en píxeles (menor)

        def fmt(value_px):
            """Convierte una posición en píxeles al número a mostrar."""
            if self.unit == "cm":
                v = value_px / self.PX_PER_CM
                # Sin decimales si es entero; si no, uno
                return f"{v:.0f}" if abs(v - round(v)) < 0.05 else f"{v:.1f}"
            if self.unit == "in":
                v = value_px / self.DPI
                # Entero si lo es; si no, hasta 2 decimales (1/4, 1/2...) sin ceros
                if abs(v - round(v)) < 0.01:
                    return f"{v:.0f}"
                return f"{v:.2f}".rstrip("0").rstrip(".")
            return str(int(round(value_px)))

        # Conversión pantalla<->lienzo en cada eje
        def screen_to_x(sx): return (sx - origin.x()) / z
        def screen_to_y(sy): return (sy - origin.y()) / z

        # 🟦 Franja azul: marca el rango de la selección sobre ambas reglas. Si
        # hay un arrastre EN CURSO (canvas.live_marquee) se usa ese rectángulo,
        # para que la franja siga al ratón en TIEMPO REAL al crear/mover; si no,
        # la selección consolidada. Sin nada, no se dibuja. Recortado a lo visible.
        b = getattr(self.canvas, "live_marquee", None)
        if b is None:
            sel = getattr(self.canvas, "selection", None)
            b = sel.boundingRect() if sel is not None else None
        if b is not None:
            try:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(0, 122, 204, 70))
                sx0 = origin.x() + b.left() * z
                sx1 = origin.x() + b.right() * z
                left = int(max(sx0, rs)); right = int(min(sx1, w))
                if right > left:
                    painter.drawRect(left, 0, right - left, rs)
                sy0 = origin.y() + b.top() * z
                sy1 = origin.y() + b.bottom() * z
                top = int(max(sy0, rs)); bottom = int(min(sy1, h))
                if bottom > top:
                    painter.drawRect(0, top, rs, bottom - top)
            except Exception:
                pass

        # Rango de píxeles de lienzo VISIBLE en cada eje (puede ser negativo)
        x_first = math.floor(screen_to_x(rs) / menor) * menor
        x_last = screen_to_x(w)
        y_first = math.floor(screen_to_y(rs) / menor) * menor
        y_last = screen_to_y(h)

        # --- Regla horizontal ---
        # Marcas menores (cortas, sin número)
        painter.setPen(QPen(QColor(theme.TEXT_MUTED)))
        xm = x_first
        while xm <= x_last:
            sx = origin.x() + xm * z
            if sx >= rs and sx <= w:
                painter.drawLine(int(sx), rs - 4, int(sx), rs - 1)
            xm += menor
        # Marcas mayores (largas, con número)
        painter.setPen(QPen(QColor(theme.TEXT_BRIGHT)))
        painter.setFont(QFont("Segoe UI", 7))
        x = math.floor(screen_to_x(rs) / intervalo) * intervalo
        while x <= x_last:
            sx = origin.x() + x * z
            if sx >= rs and sx <= w:
                painter.drawLine(int(sx), rs - 8, int(sx), rs - 1)
                painter.drawText(int(sx) + 2, rs - 9, fmt(x))
            x += intervalo

        # --- Regla vertical (texto rotado) ---
        painter.setPen(QPen(QColor(theme.TEXT_MUTED)))
        ym = y_first
        while ym <= y_last:
            sy = origin.y() + ym * z
            if sy >= rs and sy <= h:
                painter.drawLine(rs - 4, int(sy), rs - 1, int(sy))
            ym += menor
        painter.setPen(QPen(QColor(theme.TEXT_BRIGHT)))
        y = math.floor(screen_to_y(rs) / intervalo) * intervalo
        while y <= y_last:
            sy = origin.y() + y * z
            if sy >= rs and sy <= h:
                painter.drawLine(rs - 8, int(sy), rs - 1, int(sy))
                painter.save()
                painter.translate(rs - 9, int(sy) + 2)
                painter.rotate(-90)
                painter.drawText(0, 0, fmt(y))
                painter.restore()
            y += intervalo

        # 🏷️ Etiqueta de unidad en la esquina superior izquierda (px / cm)
        painter.setPen(QPen(QColor(theme.TEXT_DIM)))
        painter.setFont(QFont("Segoe UI", 7))
        painter.drawText(0, 0, rs, rs, Qt.AlignCenter, self.unit)

        # --- Línea azul de seguimiento del cursor ---
        if self.cursor_pos is not None:
            painter.setPen(QPen(QColor(0, 122, 204), 1))
            cx = origin.x() + self.cursor_pos.x() * z
            cy = origin.y() + self.cursor_pos.y() * z
            if rs <= cx <= w:
                painter.drawLine(int(cx), 0, int(cx), rs)
            if rs <= cy <= h:
                painter.drawLine(0, int(cy), rs, int(cy))

        painter.end()