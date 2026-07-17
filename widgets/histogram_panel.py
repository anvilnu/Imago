# widgets/histogram_panel.py
"""HISTOGRAMA EN VIVO de Imago: HistogramaWidget, el panel EMPOTRADO arriba
del todo de la columna derecha (Histograma · Historial · Capas · Color,
reordenable con ▲/▼ y de ALTO FIJO; ver create_docks en
ventana/construccion_ui.py). Antes de ser panel fue un overlay arrastrable
(jul 2026); esa presentación se descartó tras probar ambas.

REGLA DE ORO ANTI-LENTITUD (aprendida con las capas de ajuste): esto no
engancha NADA al pintado ni a la composición del lienzo. Se refresca por
sondeo ligero (QTimer a ~2,5 Hz) que:
  1) ni siquiera corre con el widget oculto (coste CERO al no usarlo);
  2) no hace nada con un botón del ratón pulsado (nunca durante un trazo);
  3) compara una HUELLA barata del documento (la misma idea que la caché de
     composición del canvas: cacheKey + opacidad + visibilidad efectiva +
     modo de fusión + efectos por capa) y solo recalcula si cambió de verdad
     (zoom, pan o arrastrar splitters no la alteran);
  4) al recalcular NO compone a tamaño completo: MUESTREA el compuesto a
     ≤192 px de lado con vecino más próximo (Qt lee ~unos pocos miles de
     píxeles por capa, no megapíxeles) y saca los cuatro histogramas
     (luminosidad, R, G, B) de una sola pasada numpy.
El coste por refresco es de fracciones de milisegundo e independiente del
tamaño del documento (medido: ~1,2 ms con 4000×3000 y 3 capas)."""

import numpy as np

from PySide6.QtCore import Qt, QRect, QRectF, QTimer
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import (QApplication, QComboBox, QHBoxLayout, QLabel,
                               QSizePolicy, QVBoxLayout, QWidget)

import theme
from i18n import t
from models.layer import visible_efectiva, base_de_recorte


def _huella(canvas):
    """Huella barata del contenido visible del documento (mismos campos que la
    caché de composición del canvas + la máscara y el tamaño): si no cambia,
    el histograma tampoco. Calcularla es O(nº de capas), sin tocar píxeles."""
    est = [id(canvas), canvas.base_width, canvas.base_height]
    for layer in canvas.layers:
        fx = tuple(e.fingerprint() for e in getattr(layer, "effects", ())
                   if getattr(e, "activo", False))
        mask = getattr(layer, "mask", None)
        est.append((
            layer.image.cacheKey() if layer.image else 0,
            mask.cacheKey() if mask is not None else 0,
            getattr(layer, "clipped", False),
            layer.opacity,
            visible_efectiva(layer),
            getattr(layer, "blend_mode", 0),
            fx,
        ))
    return tuple(est)


def _componer_muestra(canvas, max_lado=192):
    """Compuesto MUESTREADO a ≤max_lado px: el mismo bucle de capas que
    render_flat_image (visibilidad efectiva, opacidad, modo de fusión y
    efectos), pero dibujando ESCALADO con vecino más próximo a propósito: al
    reducir, Qt muestrea ~ancho×alto píxeles de destino del origen (no lee la
    imagen entera), así que el coste no depende del tamaño del documento. Para
    un histograma ese muestreo estadístico es más que de sobra."""
    bw, bh = canvas.base_width, canvas.base_height
    esc = min(1.0, max_lado / float(max(1, max(bw, bh))))
    sw = max(1, round(bw * esc))
    sh = max(1, round(bh * esc))
    small = QImage(sw, sh, QImage.Format_ARGB32_Premultiplied)
    small.fill(Qt.transparent)
    p = QPainter(small)
    p.setRenderHint(QPainter.SmoothPixmapTransform, False)
    destino = QRect(0, 0, sw, sh)
    origen = QRect(0, 0, bw, bh)
    for i, layer in enumerate(canvas.layers):
        if visible_efectiva(layer):
            # ✂️ Máscara de recorte, como el compositor: la recortada se acota
            # al alfa de su base (aquí ESCALADO: el DestinationIn se hace sobre
            # la muestra pequeña, coste despreciable).
            base = base_de_recorte(canvas.layers, i)
            if getattr(layer, "clipped", False) and base is not None \
                    and not visible_efectiva(base):
                continue
            p.setOpacity(layer.opacity / 100.0)
            p.setCompositionMode(getattr(
                layer, "blend_mode", QPainter.CompositionMode_SourceOver))
            if base is not None:
                tmp = QImage(sw, sh, QImage.Format_ARGB32_Premultiplied)
                tmp.fill(Qt.transparent)
                tp = QPainter(tmp)
                tp.setRenderHint(QPainter.SmoothPixmapTransform, False)
                tp.drawImage(destino, layer.render_with_effects(), origen)
                tp.setCompositionMode(QPainter.CompositionMode_DestinationIn)
                tp.drawImage(destino, base.render_image(), origen)
                tp.end()
                p.drawImage(0, 0, tmp)
            else:
                p.drawImage(destino, layer.render_with_effects(), origen)
    p.end()
    return small


def _histogramas(canvas):
    """Los cuatro histogramas (lum, r, g, b) del compuesto muestreado, como
    arrays float64 de 256 niveles. Ignora los píxeles totalmente transparentes
    (como el histograma de Propiedades de imagen)."""
    from adjustments import qimage_to_array
    arr = qimage_to_array(_componer_muestra(canvas))
    opacos = arr[..., 3] > 0
    if not opacos.any():
        cero = np.zeros(256, dtype=np.float64)
        return {"lum": cero, "r": cero.copy(), "g": cero.copy(), "b": cero.copy()}
    r = arr[..., 0][opacos].astype(np.float32)
    g = arr[..., 1][opacos].astype(np.float32)
    b = arr[..., 2][opacos].astype(np.float32)
    lum = r * 0.299 + g * 0.587 + b * 0.114

    def hist(v):
        return np.bincount(np.clip(v, 0, 255).astype(np.int32),
                           minlength=256).astype(np.float64)
    return {"lum": hist(lum), "r": hist(r), "g": hist(g), "b": hist(b)}


class _VistaHistograma(QWidget):
    """Dibuja el histograma del canal elegido (o los tres RGB superpuestos) y
    es INTERACTIVA en modo lectura: pasar el ratón marca el nivel bajo el
    cursor ("Nivel N · X %") y arrastrar mide un rango ("Rango A–B · X %";
    un clic seco lo quita). Todo ocurre dentro de este widget (estado propio +
    repintados suyos): no toca el lienzo ni el sondeo, coste cero para Imago.
    La luminosidad usa el color de acento del tema; los canales llevan rojo/
    verde/azul FIJOS a propósito (son semánticos, como el doble borde
    negro/blanco de la lupa del cuentagotas: deben leerse en cualquier tema)."""

    _COLORES = {"r": QColor(224, 84, 84), "g": QColor(96, 200, 96),
                "b": QColor(96, 140, 235)}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(180, 96)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)          # hover sin botón pulsado
        self.setCursor(Qt.CrossCursor)
        self.setToolTip(t("histogram.tip"))
        self._datos = None
        self._canal = "lum"
        self._hover = None                   # nivel 0..255 bajo el cursor
        self._rango = None                   # (a, b) marcados con a <= b
        self._origen_arrastre = None         # nivel del press en curso

    def set_datos(self, datos):
        self._datos = datos
        self.update()

    def set_canal(self, canal):
        self._canal = canal
        self.update()

    def _series(self):
        """Lista de (histograma, color) a pintar según el canal activo."""
        if self._datos is None:
            return []
        if self._canal == "rgb":
            return [(self._datos[c], self._COLORES[c]) for c in ("r", "g", "b")]
        if self._canal in self._COLORES:
            return [(self._datos[self._canal], self._COLORES[self._canal])]
        return [(self._datos["lum"], QColor(theme.ACCENT))]

    def _hist_activa(self):
        """Histograma del que salen los porcentajes de la lectura: el del
        canal activo; en RGB superpuesto, la luminosidad (la lectura es
        "píxeles en el nivel/rango", no por canal)."""
        if self._datos is None:
            return None
        if self._canal in self._COLORES:
            return self._datos[self._canal]
        return self._datos["lum"]

    # -------------------------------------------------- nivel <-> posición x
    # La misma correspondencia que usan las barras del paintEvent.
    def _nivel_en(self, x):
        interior = max(1, self.width() - 2)
        return max(0, min(255, int((x - 1) * 256 / interior)))

    def _x_de(self, nivel):
        interior = max(1, self.width() - 2)
        return 1 + nivel * interior / 256.0

    # ------------------------------------------------------------- ratón
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._origen_arrastre = self._nivel_en(event.position().x())
            self._rango = None               # clic seco = quitar el rango
            self.update()
            event.accept()

    def mouseMoveEvent(self, event):
        self._hover = self._nivel_en(event.position().x())
        if self._origen_arrastre is not None and (event.buttons() & Qt.LeftButton):
            if self._hover != self._origen_arrastre:
                self._rango = (min(self._origen_arrastre, self._hover),
                               max(self._origen_arrastre, self._hover))
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._origen_arrastre = None
            self.update()

    def leaveEvent(self, event):
        self._hover = None
        self.update()
        super().leaveEvent(event)

    # ------------------------------------------------------------- pintura
    def paintEvent(self, event):
        p = QPainter(self)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor(theme.BG_DARK))
        # Franja del rango marcado, DEBAJO de las barras.
        if self._rango is not None:
            franja = QColor(theme.BG_PRESSED)
            franja.setAlpha(120)
            x0 = self._x_de(self._rango[0])
            x1 = self._x_de(self._rango[1] + 1)
            p.fillRect(QRectF(x0, 1, x1 - x0, h - 2), franja)
        series = self._series()
        maximo = max((float(s.max()) for s, _ in series), default=0.0)
        if maximo > 0 and w > 4:
            interior = w - 2
            varios = len(series) > 1
            for hist, color in series:
                if varios:
                    color = QColor(color)
                    color.setAlpha(160)   # RGB superpuesto: que se vean los tres
                p.setPen(QPen(color))
                for x in range(interior):
                    nivel = int(x * 256 / interior)
                    alto = int((hist[nivel] / maximo) * (h - 4))
                    if alto > 0:
                        p.drawLine(1 + x, h - 2, 1 + x, h - 2 - alto)
        # Línea del nivel bajo el cursor (encima de las barras).
        if self._hover is not None and series:
            guia = QColor(theme.TEXT)
            guia.setAlpha(140)
            p.setPen(QPen(guia))
            lx = int(self._x_de(self._hover))
            p.drawLine(lx, 1, lx, h - 2)
        # Lectura arriba a la derecha (rango si lo hay; si no, el hover).
        texto = None
        hist = self._hist_activa()
        total = float(hist.sum()) if hist is not None else 0.0
        if total > 0 and self._rango is not None:
            a, b = self._rango
            pct = float(hist[a:b + 1].sum()) * 100.0 / total
            texto = t("histogram.range", a=a, b=b, pct="%.1f" % pct)
        elif total > 0 and self._hover is not None:
            pct = float(hist[self._hover]) * 100.0 / total
            texto = t("histogram.readout", nivel=self._hover, pct="%.1f" % pct)
        if texto:
            fuente = p.font()
            fuente.setPointSizeF(7.5)
            p.setFont(fuente)
            fm = p.fontMetrics()
            ancho_t = fm.horizontalAdvance(texto)
            caja = QRectF(w - ancho_t - 10, 2, ancho_t + 8, fm.height() + 2)
            fondo = QColor(theme.BG_DARK)
            fondo.setAlpha(210)
            p.fillRect(caja, fondo)
            p.setPen(QPen(QColor(theme.TEXT)))
            p.drawText(caja, Qt.AlignCenter, texto)
        p.setPen(QPen(QColor(theme.BORDER)))
        p.drawRect(0, 0, w - 1, h - 1)
        p.end()


class HistogramaWidget(QWidget):
    """Contenido del histograma en vivo: fila compacta "Canal:" (mismo estilo
    que el "Modo:" del panel de Capas) + vista + sondeo con huella. El sondeo
    SOLO corre mientras el widget está visible (show/hideEvent): oculto (o con
    su panel/overlay cerrado) el coste es exactamente cero."""

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self._main = main_window
        self._ultima_huella = None

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(4, 4, 4, 4)
        raiz.setSpacing(4)

        fila = QHBoxLayout()
        fila.setSpacing(4)
        etiqueta = QLabel(t("histogram.channel"))
        etiqueta.setStyleSheet(f"color:{theme.TEXT};")
        fila.addWidget(etiqueta)
        self.canal_combo = QComboBox()
        self.canal_combo.setStyleSheet(theme.combobox_qss())
        self.canal_combo.addItem(t("histogram.lum"), "lum")
        self.canal_combo.addItem(t("histogram.rgb"), "rgb")
        self.canal_combo.addItem(t("histogram.red"), "r")
        self.canal_combo.addItem(t("histogram.green"), "g")
        self.canal_combo.addItem(t("histogram.blue"), "b")
        self.canal_combo.currentIndexChanged.connect(self._on_canal)
        fila.addWidget(self.canal_combo, 1)
        raiz.addLayout(fila)

        self._vista = _VistaHistograma()
        raiz.addWidget(self._vista, 1)

        # Sondeo ligero: SOLO corre con el widget visible (show/hideEvent).
        self._timer = QTimer(self)
        self._timer.setInterval(400)
        self._timer.timeout.connect(self._tick)

        # Canal recordado entre sesiones.
        canal = str(main_window.settings.value("histogram/canal", "lum"))
        idx = self.canal_combo.findData(canal)
        if idx >= 0:
            self.canal_combo.setCurrentIndex(idx)
        self._vista.set_canal(self.canal_combo.currentData())

    # ------------------------------------------------------------ canal
    def _on_canal(self, _=None):
        canal = self.canal_combo.currentData()
        self._vista.set_canal(canal)
        self._main.settings.setValue("histogram/canal", canal)

    # ------------------------------------------------------- ciclo de vida
    def showEvent(self, event):
        super().showEvent(event)
        self._ultima_huella = None       # fuerza el primer refresco
        self._timer.start()
        QTimer.singleShot(0, self._tick)

    def hideEvent(self, event):
        super().hideEvent(event)
        self._timer.stop()

    # ------------------------------------------------------------ refresco
    def _tick(self):
        if not self.isVisible():
            return
        # Nunca durante un gesto (trazo, arrastre de un slider o splitter...):
        # se reintenta en el siguiente tic, ya en reposo.
        if QApplication.mouseButtons() != Qt.NoButton:
            return
        canvas = (self._main.get_current_canvas()
                  if hasattr(self._main, "get_current_canvas") else None)
        if canvas is None or not getattr(canvas, "layers", None):
            if self._ultima_huella is not None:
                self._ultima_huella = None
                self._vista.set_datos(None)
            return
        huella = _huella(canvas)
        if huella == self._ultima_huella:
            return
        self._ultima_huella = huella
        self._vista.set_datos(_histogramas(canvas))
