# tools/eyedropper_tool.py
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QPoint, QRect
from i18n import t
from tools.base_tool import BaseTool
from tools.numpy_utils import qimage_to_u32


# Lupa: área (en píxeles de imagen) y tamaño en pantalla de cada píxel ampliado
LOUPE_AREA = 11        # 11x11 píxeles alrededor del cursor (impar: hay centro)
LOUPE_PXSIZE = 9       # cada píxel se dibuja a 9x9 en pantalla
LOUPE_ZOOM = LOUPE_AREA * LOUPE_PXSIZE


class _LoupeWidget(QWidget):
    """Pequeño overlay que sigue al cursor: muestra el área ampliada bajo el
    puntero (con el píxel central marcado) y el color capturado con su Hex."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._zoom = None
        self._color = QColor(0, 0, 0, 0)
        self._hex = ""
        self.setFixedSize(LOUPE_ZOOM + 8, LOUPE_ZOOM + 34)

    def set_data(self, zoom_img, color):
        self._zoom = zoom_img
        self._color = color
        self._hex = color.name().upper()
        self.update()

    def paintEvent(self, event):
        # 🎨 Colores desde theme.py (leídos al pintar: siguen al tema activo,
        # también el claro; antes iban grises hardcodeados y la lupa quedaba
        # oscura en el tema claro). El marcador del píxel central conserva su
        # doble borde negro/blanco fijo: debe verse sobre CUALQUIER color.
        import theme
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        # Fondo redondeado
        p.setPen(QPen(QColor(theme.BORDER), 1))
        p.setBrush(QColor(theme.BG_WINDOW))
        p.drawRoundedRect(0, 0, w - 1, h - 1, 6, 6)
        # Zoom del área (nearest -> pixelado)
        if self._zoom is not None:
            p.drawImage(QRect(4, 4, LOUPE_ZOOM, LOUPE_ZOOM), self._zoom)
        else:
            p.fillRect(QRect(4, 4, LOUPE_ZOOM, LOUPE_ZOOM), QColor(theme.BG_BUTTON))
        # Recuadro del píxel central (doble borde para verlo sobre cualquier color)
        c = 4 + (LOUPE_AREA // 2) * LOUPE_PXSIZE
        p.setPen(QPen(QColor(0, 0, 0), 1)); p.setBrush(Qt.NoBrush)
        p.drawRect(c - 1, c - 1, LOUPE_PXSIZE + 1, LOUPE_PXSIZE + 1)
        p.setPen(QPen(QColor(255, 255, 255), 1))
        p.drawRect(c, c, LOUPE_PXSIZE - 1, LOUPE_PXSIZE - 1)
        # Muestra de color + Hex
        by = 4 + LOUPE_ZOOM + 4
        p.setPen(QPen(QColor(theme.BORDER), 1)); p.setBrush(self._color)
        p.drawRect(4, by, 22, 18)
        p.setPen(QColor(theme.TEXT))
        p.drawText(QRect(30, by, w - 34, 18), Qt.AlignVCenter | Qt.AlignLeft, self._hex)
        p.end()


class EyedropperTool(BaseTool):
    """Cuentagotas: captura el color bajo el cursor.
    Izquierdo -> primario | Derecho -> secundario.

    Opciones: tamaño de muestra (1 px, media 3x3 o 5x5) y fuente (todas las
    capas = imagen compuesta, o solo la capa activa). Mientras arrastras, una
    lupa muestra el área ampliada y el color. No genera historial."""

    def __init__(self, canvas):
        super().__init__(canvas)
        self.tool_id = "eyedropper"
        self.history_name = t("tool.name.eyedropper")
        self._sample_cache = None     # imagen de muestreo cacheada durante el arrastre

    # ------------------------------------------------------------------
    def _opts(self):
        c = self.canvas
        return (int(getattr(c, "eyedropper_sample_size", 1)),
                bool(getattr(c, "eyedropper_sample_all", True)))

    def _build_sample_image(self, sample_all):
        if sample_all and hasattr(self.canvas, "render_flat_image"):
            # Fondo TRANSPARENTE (como varita/cubo/clonar): con el blanco por
            # defecto, las zonas transparentes capturaban un blanco fantasma
            # y las semitransparentes se lavaban hacia blanco. OJO: el
            # composite viene PREMULTIPLICADO y pixel() devolvería el RGB ya
            # multiplicado por el alfa; se convierte a ARGB32 recto.
            return self.canvas.render_flat_image(Qt.transparent).convertToFormat(
                QImage.Format_ARGB32)
        layer = self.canvas.layers[self.canvas.active_layer_index]
        return layer.image

    def _loupe_parent(self):
        """La lupa cuelga del viewport del scroll (no del lienzo): así nunca se
        recorta, ni con imágenes más pequeñas que la propia lupa."""
        vp = self.canvas.parentWidget()
        return vp if vp is not None else self.canvas

    def _ensure_loupe(self):
        loupe = getattr(self.canvas, "_eyedropper_loupe", None)
        parent = self._loupe_parent()
        if loupe is None or loupe.parent() is not parent:
            if loupe is not None:
                loupe.deleteLater()
            loupe = _LoupeWidget(parent)
            self.canvas._eyedropper_loupe = loupe
        return loupe

    # ------------------------------------------------------------------
    def mouse_press(self, event):
        if event.button() not in (Qt.LeftButton, Qt.RightButton):
            return
        _, sample_all = self._opts()
        self._sample_cache = self._build_sample_image(sample_all)
        self._sample(event, primary=(event.button() == Qt.LeftButton))

    def mouse_move(self, event):
        if self._sample_cache is None:
            return
        if event.buttons() & Qt.LeftButton:
            self._sample(event, primary=True)
        elif event.buttons() & Qt.RightButton:
            self._sample(event, primary=False)

    def mouse_release(self, event):
        self._sample_cache = None
        loupe = getattr(self.canvas, "_eyedropper_loupe", None)
        if loupe is not None:
            loupe.hide()

    # ------------------------------------------------------------------
    def _pick_color(self, sample, cx, cy, size):
        """Color en (cx,cy): un píxel, o la media de un área NxN (numpy).
        fromRgba conserva el ALFA (QColor(QRgb) lo descarta): el color
        capturado reproduce también la transparencia real del píxel, igual
        que ya hacía la media NxN (que promedia el alfa), como Paint.NET."""
        if size <= 1:
            return QColor.fromRgba(sample.pixel(cx, cy))
        try:
            arr = qimage_to_u32(sample)
            H, W = arr.shape
            half = size // 2
            x0 = max(0, cx - half); x1 = min(W, cx + half + 1)
            y0 = max(0, cy - half); y1 = min(H, cy + half + 1)
            win = arr[y0:y1, x0:x1]
            a = float(((win >> 24) & 0xFF).mean())
            r = float(((win >> 16) & 0xFF).mean())
            g = float(((win >> 8) & 0xFF).mean())
            b = float((win & 0xFF).mean())
            return QColor(int(round(r)), int(round(g)), int(round(b)), int(round(a)))
        except Exception:
            return QColor.fromRgba(sample.pixel(cx, cy))

    def _sample(self, event, primary, show_loupe=True):
        """Captura el color bajo el cursor. Con show_loupe=False no muestra la
        lupa: lo usa el cuentagotas TEMPORAL (Alt+clic desde los pinceles)."""
        zoom = self.canvas.zoom_factor
        pos = event.position() / zoom
        point = QPoint(int(pos.x()), int(pos.y()))
        if not (0 <= point.x() < self.canvas.base_width and
                0 <= point.y() < self.canvas.base_height):
            return

        sample = self._sample_cache
        if sample is None:
            _, sample_all = self._opts()
            sample = self._build_sample_image(sample_all)
        size, _ = self._opts()

        color = self._pick_color(sample, point.x(), point.y(), size)

        if primary:
            self.canvas.brush_color = color
        else:
            self.canvas.brush_color_secondary = color

        callback = getattr(self.canvas, "color_picked_callback", None)
        if callback:
            callback(color, primary)

        if show_loupe:
            self._update_loupe(event, sample, point, color)

    def _update_loupe(self, event, sample, point, color):
        """Sitúa y rellena la lupa junto al cursor."""
        loupe = self._ensure_loupe()
        half = LOUPE_AREA // 2
        # Recorte del área (copy rellena con transparente lo que caiga fuera)
        area = sample.copy(point.x() - half, point.y() - half, LOUPE_AREA, LOUPE_AREA)
        zoom_img = area.scaled(LOUPE_ZOOM, LOUPE_ZOOM,
                               Qt.IgnoreAspectRatio, Qt.FastTransformation)
        loupe.set_data(zoom_img, color)

        # Posición: convertimos el punto del cursor (coords del lienzo) a las
        # del PADRE de la lupa (el viewport), desplazado para no tapar el puntero.
        parent = loupe.parent()
        gpos = self.canvas.mapToGlobal(event.position().toPoint())
        ppos = parent.mapFromGlobal(gpos)
        lx = ppos.x() + 20
        ly = ppos.y() + 20
        if lx + loupe.width() > parent.width():
            lx = ppos.x() - 20 - loupe.width()
        if ly + loupe.height() > parent.height():
            ly = ppos.y() - 20 - loupe.height()
        loupe.move(max(0, lx), max(0, ly))
        loupe.show()
        loupe.raise_()