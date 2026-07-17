# cursores.py
"""Cursores de las herramientas sobre el lienzo (mixin de MainWindow).

Extraído de main.py TAL CUAL (sin cambios de comportamiento): carga de
cursores PNG con punto caliente, mapa herramienta→cursor y el cursor de
círculo del pincel/goma (dibujado al vuelo según tamaño, forma y zoom).
MainWindow hereda de CursoresHerramientas y todo sigue llamándose vía
self.* igual que antes."""
from PySide6.QtCore import Qt, QFile
from PySide6.QtGui import QPainter, QPen


class CursoresHerramientas:
    # =========================================================================
    # SISTEMA DE CURSORES POR HERRAMIENTA
    # Cada tool_id apunta a su cursor. Tres formatos posibles:
    #   - Qt.CrossCursor, etc.            → cursor nativo de Qt
    #   - ("png", ruta, hotspot_x, hotspot_y) → PNG personalizado con su punto
    #     caliente (el píxel exacto que "hace clic"). Si el PNG no existe,
    #     se usa el cursor nativo de respaldo indicado en CURSOR_FALLBACK.
    # Las herramientas con cursor que CAMBIA durante el gesto (mano, mover,
    # selección rect/elipse) NO van aquí: las gestiona la propia herramienta.
    # El pincel y la goma tampoco: usan el círculo dinámico de tamaño.
    # =========================================================================
    CURSOR_DEFS = {
        "crop":           Qt.CrossCursor,
        "bucket":         ("png", ":/icons/cursor/cubo_cursor.png", 24, 24),
        "pencil":         ("png", ":/icons/cursor/pencil.png", 2, 30),
        "eyedropper":     ("png", ":/icons/cursor/eyedropper.png", 2, 30),
        "magic_wand":     ("png", ":/icons/cursor/magic_wand.png", 2, 30),
        "select_rect":    ("png", ":/icons/cursor/select_rect.png", 16, 16),
        "select_ellipse": ("png", ":/icons/cursor/select_ellipse.png", 16, 16),
        "select_lasso":   Qt.CrossCursor,
        "text":           Qt.IBeamCursor,
    }
    # Cursor nativo de respaldo si falta el PNG (para no romper nada)
    CURSOR_FALLBACK = {
        "bucket": Qt.CrossCursor,
        "pencil": Qt.CrossCursor,
        "eyedropper": Qt.CrossCursor,
        "magic_wand": Qt.CrossCursor,
        "select_rect": Qt.CrossCursor,
        "select_ellipse": Qt.CrossCursor,
    }

    def _load_png_cursor(self, ruta, hotspot_x, hotspot_y):
        """Carga un PNG como QCursor con su hotspot. Lo ideal es crear el
        cursor ya a 32x32 con el hotspot en esas coordenadas (no se reescala
        nada). Si el PNG es mayor de 32, se reduce a 32x32 y el hotspot se
        escala EN LA MISMA PROPORCIÓN (antes se quedaba en coordenadas del
        original y el punto caliente caía desplazado). El hotspot se da en
        píxeles de la imagen original. Devuelve None si el archivo no existe."""
        from PySide6.QtGui import QPixmap, QCursor
        if not QFile.exists(ruta):
            return None
        pixmap = QPixmap(ruta)
        if pixmap.isNull():
            return None
        hx, hy = hotspot_x, hotspot_y
        if pixmap.width() > 32 or pixmap.height() > 32:
            ow, oh = pixmap.width(), pixmap.height()
            pixmap = pixmap.scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
            hx = int(round(hotspot_x * pixmap.width() / ow))
            hy = int(round(hotspot_y * pixmap.height() / oh))
        return QCursor(pixmap, hx, hy)

    def cursor_for_tool(self, tool_id):
        """Devuelve el QCursor (o forma nativa) para una herramienta según
        CURSOR_DEFS, resolviendo PNG y fallback. Para herramientas no listadas
        devuelve None (las gestiona su propia lógica)."""
        definicion = self.CURSOR_DEFS.get(tool_id)
        if definicion is None:
            return None
        if isinstance(definicion, tuple) and definicion[0] == "png":
            _, ruta, hx, hy = definicion
            cursor = self._load_png_cursor(ruta, hx, hy)
            if cursor is not None:
                return cursor
            return self.CURSOR_FALLBACK.get(tool_id, Qt.CrossCursor)
        return definicion  # Cursor nativo directo

    def update_canvas_cursor(self):
        """Asigna el cursor de la herramienta y lo ESPEJA en el fondo gris
        (viewport del scroll), para que se vea y se pueda empezar a trabajar
        también desde fuera del lienzo."""
        self._update_canvas_cursor_impl()
        canvas = self.get_current_canvas()
        scroll = self.get_current_scroll()
        if canvas is not None and scroll is not None:
            scroll.viewport().setCursor(canvas.cursor())

    def _update_canvas_cursor_impl(self):
        """Asigna el cursor según la herramienta activa. Casos especiales:
        - move y hand gestionan su propio cursor (cambia por zona / al arrastrar).
        - select_rect y select_ellipse muestran cruz+forma en reposo y cruz
          sola al arrastrar: lo gestiona la propia herramienta; aquí solo
          ponemos el de reposo.
        - pen y eraser usan el círculo dinámico que refleja el tamaño real.
        - el resto sale del diccionario CURSOR_DEFS (PNG o nativo)."""
        canvas = self.get_current_canvas()
        if not canvas: return

        tool_name = getattr(self, 'current_tool_name', None)

        # La mano y mover gestionan su cursor por su cuenta
        if tool_name == "move":
            return  # Las modalidades de mover gestionan su cursor (lo fija update_active_move_mode)
        if tool_name == "hand":
            # La herramienta mano fija su cursor de reposo según si la imagen
            # cabe en pantalla (mano+cruz) o se puede desplazar (mano abierta)
            if hasattr(canvas.current_tool, 'apply_rest_cursor'):
                canvas.current_tool.apply_rest_cursor()
            else:
                canvas.setCursor(Qt.OpenHandCursor)
            return

        # ✚ Selección rect/elipse: cursor de reposo cruz+forma (PNG); la
        # herramienta lo cambia a cruz sola al arrastrar
        if tool_name in ("select_rect", "select_ellipse"):
            cursor = self.cursor_for_tool(tool_name)
            canvas.setCursor(cursor if cursor is not None else Qt.CrossCursor)
            return

        # Leemos el ID interno de la herramienta seleccionada en el combo box
        tool_id = self.options_bar.tool_combo.itemData(self.options_bar.tool_combo.currentIndex())

        # Pincel y goma: contorno dinámico que muestra el tamaño Y la forma real
        if tool_id in ("pen", "eraser", "clone", "airbrush", "smudge",
                       "replace_color", "dodge_burn", "heal", "sponge",
                       "liquify"):
            if tool_id == "eraser":
                shape = getattr(canvas, "eraser_shape", "round")
            elif tool_id == "pen":
                shape = getattr(canvas, "brush_shape", "round")
            elif tool_id == "replace_color":
                shape = getattr(canvas, "replace_shape", "round")
            elif tool_id == "airbrush":
                shape = getattr(canvas, "airbrush_shape", "round")
            elif tool_id == "clone":
                shape = getattr(canvas, "clone_shape", "round")
            else:
                shape = "round"
            self._apply_brush_circle_cursor(canvas, shape)
            return

        # Resto de herramientas: del diccionario (PNG con hotspot o nativo)
        cursor = self.cursor_for_tool(tool_id)
        if cursor is not None:
            canvas.setCursor(cursor)
        else:
            canvas.setCursor(Qt.CrossCursor)

    def _draw_cursor_shape(self, painter, center, radius, shape, pen):
        """Dibuja el CONTORNO de la punta según la forma activa (círculo, cuadrado,
        rombo o barras), coincidiendo con la geometría de _shape_path de draw_tools."""
        from PySide6.QtCore import QPointF, QRectF
        from PySide6.QtGui import QPolygonF
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        a = 3.0  # aspecto caligráfico (== _CALLIG_ASPECT en draw_tools)
        c = QPointF(center, center)
        if shape == "square":
            painter.drawRect(QRectF(center - radius, center - radius, 2 * radius, 2 * radius))
        elif shape == "diamond":
            painter.drawPolygon(QPolygonF([
                QPointF(center, center - radius), QPointF(center + radius, center),
                QPointF(center, center + radius), QPointF(center - radius, center)]))
        elif shape == "horizontal":
            painter.drawEllipse(c, radius, radius / a)
        elif shape == "vertical":
            painter.drawEllipse(c, radius / a, radius)
        elif shape in ("fdiag", "bdiag"):
            painter.save()
            painter.translate(center, center)
            painter.rotate(45 if shape == "fdiag" else -45)
            painter.drawEllipse(QPointF(0, 0), radius, radius / a)
            painter.restore()
        else:  # round
            painter.drawEllipse(c, radius, radius)

    def _apply_brush_circle_cursor(self, canvas, shape="round"):
        """Cursor de pincel/goma: círculo que refleja el tamaño real del trazo
        MÁS una cruz central de doble color (negro+blanco) que se ve sobre
        cualquier fondo, para no perder nunca la posición del cursor."""
        diameter = canvas.brush_size * canvas.zoom_factor
        # El contenedor debe alojar el círculo Y la cruz central (mínimo 24px
        # para que la cruz quepa aunque el círculo sea diminuto)
        container_size = max(24, int(diameter) + 4)

        if container_size > 140:
            # Círculo demasiado grande para cursor: cae a cruz nativa
            canvas.setCursor(Qt.CursorShape.CrossCursor)
            return

        from PySide6.QtGui import QPixmap, QCursor
        pixmap = QPixmap(container_size, container_size)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        center = container_size / 2.0
        radius = diameter / 2.0

        # Círculo de tamaño: negro continuo + blanco punteado (solo si tiene
        # radio visible; con grosores muy pequeños el círculo se omite y queda
        # solo la cruz, que es lo legible a ese tamaño)
        if radius >= 2:
            self._draw_cursor_shape(painter, center, radius, shape,
                                    QPen(Qt.GlobalColor.black, 1, Qt.PenStyle.SolidLine))
            self._draw_cursor_shape(painter, center, radius, shape,
                                    QPen(Qt.GlobalColor.white, 1, Qt.PenStyle.DotLine))

        # ✚ Cruz central de doble color: una línea blanca de 3px por debajo y
        # otra negra de 1px encima, así contrasta sobre fondos claros y oscuros.
        # Mide 8px (4 a cada lado del centro) y deja un hueco en el medio para
        # marcar el punto exacto sin taparlo.
        arm = 8      # longitud de cada brazo
        gap = 1      # hueco central
        cx = cy = center

        def cruz(pen):
            painter.setPen(pen)
            # Horizontal (dos segmentos con hueco central)
            painter.drawLine(int(cx - arm), int(cy), int(cx - gap), int(cy))
            painter.drawLine(int(cx + gap), int(cy), int(cx + arm), int(cy))
            # Vertical
            painter.drawLine(int(cx), int(cy - arm), int(cx), int(cy - gap))
            painter.drawLine(int(cx), int(cy + gap), int(cx), int(cy + arm))

        cruz(QPen(Qt.GlobalColor.white, 3))  # Halo blanco grueso debajo
        cruz(QPen(Qt.GlobalColor.black, 1))  # Cruz negra fina encima
        painter.end()

        canvas.setCursor(QCursor(pixmap, int(center), int(center)))


