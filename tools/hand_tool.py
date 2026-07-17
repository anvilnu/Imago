# tools/hand_tool.py
from PySide6.QtCore import Qt
from i18n import t
from tools.base_tool import BaseTool


class HandTool(BaseTool):
    """Mano (pan): arrastra para desplazar la vista, moviendo las barras de
    desplazamiento del QScrollArea. Imprescindible cuando el lienzo es más
    grande que la ventana (zoom alto o imagen grande maximizada).

    No modifica píxeles ni el historial: solo cambia qué parte se ve.
    Usa coordenadas de pantalla (globales), no las del lienzo, porque lo que
    importa es cuánto se ha movido el ratón físicamente, no sobre qué píxel."""

    def __init__(self, canvas):
        super().__init__(canvas)
        self.tool_id = "hand"
        self.history_name = t("tool.name.hand")
        self.panning = False
        self.last_global = None
        self._acc_x = 0.0   # resto fraccionario acumulado (pan suave)
        self._acc_y = 0.0

    def _scroll_area(self):
        """Localiza el QScrollArea que contiene el lienzo (viewport→scroll)."""
        viewport = self.canvas.parentWidget()
        scroll_area = viewport.parentWidget() if viewport is not None else None
        if scroll_area is not None and hasattr(scroll_area, 'horizontalScrollBar'):
            return scroll_area
        return None

    def _can_pan(self):
        """¿Hay algo que desplazar? True si alguna barra de scroll tiene
        recorrido (la imagen no cabe entera en la ventana)."""
        scroll_area = self._scroll_area()
        if scroll_area is None:
            return False
        h = scroll_area.horizontalScrollBar()
        v = scroll_area.verticalScrollBar()
        return h.maximum() > 0 or v.maximum() > 0

    def apply_rest_cursor(self):
        """Cursor de reposo: mano abierta si se puede desplazar; mano+cruz
        (PNG) si la imagen cabe en pantalla y no hay nada que arrastrar."""
        import os
        if self._can_pan():
            self.canvas.setCursor(Qt.OpenHandCursor)
            return
        # No hay desplazamiento posible: mano abierta + cruz (PNG si existe)
        ruta = ":/icons/cursor/hand_pan.png"
        from PySide6.QtCore import QFile
        if QFile.exists(ruta):
            from PySide6.QtGui import QPixmap, QCursor
            pixmap = QPixmap(ruta)
            if not pixmap.isNull():
                if pixmap.width() > 32 or pixmap.height() > 32:
                    pixmap = pixmap.scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatio,
                                           Qt.TransformationMode.SmoothTransformation)
                self.canvas.setCursor(QCursor(pixmap, 16, 16))
                return
        # Fallback nativo si no está el PNG
        self.canvas.setCursor(Qt.OpenHandCursor)

    def mouse_press(self, event):
        if event.button() != Qt.LeftButton:
            return
        self.panning = True
        self.last_global = event.globalPosition()
        self._acc_x = 0.0
        self._acc_y = 0.0
        self.canvas.setCursor(Qt.ClosedHandCursor)  # Puño cerrado al agarrar

    def mouse_move(self, event):
        if not self.panning or self.last_global is None:
            return
        scroll_area = self._scroll_area()
        if scroll_area is None:
            return

        # Cuánto se ha movido el ratón desde el último evento (en pantalla)
        current = event.globalPosition()
        dx = current.x() - self.last_global.x()
        dy = current.y() - self.last_global.y()
        self.last_global = current

        # 🪶 Pan suave: acumulamos el resto fraccionario y desplazamos solo por
        # la parte entera. Así los movimientos lentos (sub-píxel) no se pierden.
        self._acc_x += dx
        self._acc_y += dy
        move_x = int(self._acc_x)
        move_y = int(self._acc_y)
        self._acc_x -= move_x
        self._acc_y -= move_y
        if move_x == 0 and move_y == 0:
            return

        # Arrastrar a la derecha debe mostrar lo que hay a la IZQUIERDA del
        # lienzo, así que el scroll se mueve en sentido contrario al ratón
        h_bar = scroll_area.horizontalScrollBar()
        v_bar = scroll_area.verticalScrollBar()
        h_bar.setValue(h_bar.value() - move_x)
        v_bar.setValue(v_bar.value() - move_y)

    def mouse_release(self, event):
        if event.button() != Qt.LeftButton:
            return
        self.panning = False
        self.last_global = None
        self.apply_rest_cursor()  # Vuelve al cursor de reposo adecuado