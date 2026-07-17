from i18n import t
# print_dialog.py — dialogo de impresion PROPIO de Imago.
# No usamos QPrintDialog: en Windows es el dialogo NATIVO del SO (imposible de
# temar) y en Linux, aunque lo dibuja Qt, sale como ventana aparte con marco
# del sistema. Este es un FramelessDialog con los colores de theme.py, igual
# que el resto de dialogos. La impresion en si la hace main.print_file con
# QPrinter a partir de get_settings(); aqui solo se eligen las opciones, con
# una vista previa de la pagina que replica la colocacion real de la imagen.
from PySide6.QtWidgets import (QLabel, QSpinBox, QComboBox, QPushButton,
                               QHBoxLayout, QVBoxLayout, QGridLayout, QWidget,
                               QSizePolicy)
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QPen, QColor, QPixmap, QImage, QPageSize
from PySide6.QtPrintSupport import QPrinter, QPrinterInfo
from widgets.custom_titlebar import FramelessDialog
import theme

_PDF_ID = "__pdf__"

# Tamanos estandar ofrecidos cuando el destino es PDF o la impresora no
# declara los suyos. Los nombres de papel (A4, Letter...) son universales:
# no pasan por t().
_PAPELES_ESTANDAR = (QPageSize.PageSizeId.A4, QPageSize.PageSizeId.A5,
                     QPageSize.PageSizeId.A3, QPageSize.PageSizeId.Letter,
                     QPageSize.PageSizeId.Legal)


class _PagePreview(QWidget):
    """Miniatura de la pagina: el papel con su proporcion real y la imagen
    colocada como va a salir (misma regla de escala y centrado que la
    impresion). El area imprimible se aproxima con un margen fijo; el
    definitivo lo decide la impresora al imprimir."""

    _MARGEN_IN = 0.2  # margen aproximado del area imprimible (pulgadas)

    def __init__(self, image, dpi, parent=None):
        super().__init__(parent)
        self._dpi = float(dpi) or 96.0
        self._img_w = image.width()
        self._img_h = image.height()
        # Copia reducida (y su version en grises) para pintar barato.
        pequena = image.scaled(512, 512, Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
        self._pix = QPixmap.fromImage(pequena)
        self._pix_gris = QPixmap.fromImage(
            pequena.convertToFormat(QImage.Format.Format_Grayscale8))
        self._page_size = QPageSize(QPageSize.PageSizeId.A4)
        self._apaisado = False
        self._gris = False
        self._ajustar = False
        self.setMinimumSize(210, 240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_config(self, page_size, apaisado, gris, ajustar):
        self._page_size = page_size
        self._apaisado = apaisado
        self._gris = gris
        self._ajustar = ajustar
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(theme.BG_DARK))
        tam = self._page_size.size(QPageSize.Unit.Inch)
        pw, ph = tam.width(), tam.height()
        if self._apaisado:
            pw, ph = ph, pw
        area = self.rect().adjusted(14, 14, -14, -18)
        if area.width() <= 0 or area.height() <= 0 or pw <= 0 or ph <= 0:
            return
        k = min(area.width() / pw, area.height() / ph)  # px de preview por pulgada
        pagina = QRectF(area.x() + (area.width() - pw * k) / 2.0,
                        area.y() + (area.height() - ph * k) / 2.0,
                        pw * k, ph * k)
        p.fillRect(pagina.translated(3, 3), QColor(0, 0, 0, 90))   # sombra
        p.fillRect(pagina, Qt.white)
        p.setPen(QPen(QColor(theme.BORDER)))
        p.drawRect(pagina)
        m = self._MARGEN_IN * k
        imprimible = pagina.adjusted(m, m, -m, -m)
        # Misma regla que la impresion real: tamano natural segun los PPP del
        # lienzo, reducido solo si no cabe; o ajustado a la pagina si se pide.
        w_nat = self._img_w / self._dpi * k
        h_nat = self._img_h / self._dpi * k
        ajuste = min(imprimible.width() / w_nat, imprimible.height() / h_nat)
        escala = ajuste if self._ajustar else min(1.0, ajuste)
        w, h = w_nat * escala, h_nat * escala
        destino = QRectF(imprimible.center().x() - w / 2.0,
                         imprimible.center().y() - h / 2.0, w, h)
        pix = self._pix_gris if self._gris else self._pix
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.drawPixmap(destino, pix, QRectF(pix.rect()))


class PrintDialog(FramelessDialog):
    """Opciones de impresion con vista previa de pagina. get_settings() ->
    dict con: pdf (bool), printer (nombre), copies, landscape, page_size
    (QPageSize), gray, duplex (QPrinter.DuplexMode) y fit (ajustar a pagina)."""

    def __init__(self, image, dpi, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("dlg.print_title", default="Imprimir"))
        self._body.setFixedSize(620, 400)
        self.setStyleSheet(
            "QDialog { background-color: %s; } QLabel { color: %s; }" % (theme.BG_WINDOW, theme.TEXT)
            + theme.spinbox_dialog_qss() + theme.combobox_dialog_qss()
            + theme.dialog_button_plain_qss()
        )

        # --- Columna izquierda: formulario de opciones ---
        form = QGridLayout()
        form.setVerticalSpacing(8)
        form.setColumnStretch(1, 1)

        fila = 0
        form.addWidget(QLabel(t("print.printer")), fila, 0)
        self.printer_combo = QComboBox()
        for info in QPrinterInfo.availablePrinters():
            self.printer_combo.addItem(info.printerName(), info.printerName())
        self.printer_combo.addItem(t("print.pdf"), _PDF_ID)
        por_defecto = QPrinterInfo.defaultPrinterName()
        idx = self.printer_combo.findData(por_defecto) if por_defecto else -1
        self.printer_combo.setCurrentIndex(idx if idx >= 0 else self.printer_combo.count() - 1)
        form.addWidget(self.printer_combo, fila, 1)

        fila += 1
        form.addWidget(QLabel(t("print.copies")), fila, 0)
        self.copies_spin = QSpinBox()
        self.copies_spin.setRange(1, 99)
        form.addWidget(self.copies_spin, fila, 1)

        fila += 1
        form.addWidget(QLabel(t("print.orientation")), fila, 0)
        self.orient_combo = QComboBox()
        self.orient_combo.addItem(t("print.portrait"), "v")
        self.orient_combo.addItem(t("print.landscape"), "h")
        # Por defecto, la orientacion que mejor le va a la imagen.
        if image.width() > image.height():
            self.orient_combo.setCurrentIndex(1)
        form.addWidget(self.orient_combo, fila, 1)

        fila += 1
        form.addWidget(QLabel(t("print.paper")), fila, 0)
        self.paper_combo = QComboBox()
        form.addWidget(self.paper_combo, fila, 1)

        fila += 1
        form.addWidget(QLabel(t("print.color_mode")), fila, 0)
        self.color_combo = QComboBox()
        self.color_combo.addItem(t("print.color"), "color")
        self.color_combo.addItem(t("print.gray"), "gris")
        form.addWidget(self.color_combo, fila, 1)

        fila += 1
        form.addWidget(QLabel(t("print.duplex")), fila, 0)
        self.duplex_combo = QComboBox()
        self.duplex_combo.addItem(t("print.duplex.none"), QPrinter.DuplexMode.DuplexNone)
        self.duplex_combo.addItem(t("print.duplex.long"), QPrinter.DuplexMode.DuplexLongSide)
        self.duplex_combo.addItem(t("print.duplex.short"), QPrinter.DuplexMode.DuplexShortSide)
        form.addWidget(self.duplex_combo, fila, 1)

        fila += 1
        form.addWidget(QLabel(t("print.scale")), fila, 0)
        self.scale_combo = QComboBox()
        self.scale_combo.addItem(t("print.scale.real"), "real")
        self.scale_combo.addItem(t("print.scale.fit"), "fit")
        form.addWidget(self.scale_combo, fila, 1)

        izquierda = QWidget()
        izquierda.setFixedWidth(300)
        izq_lay = QVBoxLayout(izquierda)
        izq_lay.setContentsMargins(0, 0, 0, 0)
        izq_lay.addLayout(form)
        izq_lay.addStretch(1)

        # --- Columna derecha: vista previa de la pagina ---
        self.preview = _PagePreview(image, dpi)

        cols = QHBoxLayout()
        cols.setSpacing(12)
        cols.addWidget(izquierda)
        cols.addWidget(self.preview, 1)
        self.body_layout.addLayout(cols, 1)

        btns = QHBoxLayout()
        btns.addStretch()
        self.btn_print = QPushButton(t("print.btn"))
        self.btn_cancel = QPushButton(t("dlg.cancel"))
        btns.addWidget(self.btn_print)
        btns.addWidget(self.btn_cancel)
        self.body_layout.addLayout(btns)

        self.btn_print.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)
        self.printer_combo.currentIndexChanged.connect(self._on_printer_changed)
        self.paper_combo.currentIndexChanged.connect(self._refrescar_preview)
        self.orient_combo.currentIndexChanged.connect(self._refrescar_preview)
        self.color_combo.currentIndexChanged.connect(self._refrescar_preview)
        self.scale_combo.currentIndexChanged.connect(self._refrescar_preview)

        self._on_printer_changed()

    # ---- destino ----
    def _es_pdf(self):
        return self.printer_combo.currentData() == _PDF_ID

    def _info_actual(self):
        """QPrinterInfo de la impresora elegida (None si el destino es PDF)."""
        if self._es_pdf():
            return None
        return QPrinterInfo.printerInfo(self.printer_combo.currentData())

    def _on_printer_changed(self, _index=None):
        """Al cambiar de destino: papeles de esa impresora y habilitado de las
        opciones que solo aplican a impresoras fisicas (copias, doble cara)."""
        info = self._info_actual()
        self.copies_spin.setEnabled(info is not None)
        if info is not None:
            modos = info.supportedDuplexModes()
            admite = (QPrinter.DuplexMode.DuplexLongSide in modos
                      or QPrinter.DuplexMode.DuplexShortSide in modos)
        else:
            admite = False
        self.duplex_combo.setEnabled(admite)
        if not admite:
            self.duplex_combo.setCurrentIndex(0)
        self._rellenar_papeles(info)
        self._refrescar_preview()

    def _rellenar_papeles(self, info):
        """Rellena el combo de papel con los tamanos del destino, conservando
        el papel elegido si el nuevo destino tambien lo tiene."""
        elegido = self.paper_combo.currentData()
        self.paper_combo.blockSignals(True)
        self.paper_combo.clear()
        tams = list(info.supportedPageSizes()) if info is not None else []
        if not tams:
            tams = [QPageSize(pid) for pid in _PAPELES_ESTANDAR]
        for ps in tams:
            if ps.isValid():
                self.paper_combo.addItem(ps.name(), ps)
        # Preferencia: papel ya elegido > papel por defecto de la impresora > A4.
        idx = self._indice_papel(elegido)
        if idx < 0 and info is not None:
            idx = self._indice_papel(info.defaultPageSize())
        if idx < 0:
            idx = self._indice_papel(QPageSize(QPageSize.PageSizeId.A4))
        self.paper_combo.setCurrentIndex(max(0, idx))
        self.paper_combo.blockSignals(False)

    def _indice_papel(self, page_size):
        if page_size is None or not page_size.isValid():
            return -1
        for i in range(self.paper_combo.count()):
            if self.paper_combo.itemData(i).id() == page_size.id():
                return i
        return -1

    # ---- preview y resultado ----
    def _refrescar_preview(self, _index=None):
        papel = self.paper_combo.currentData() or QPageSize(QPageSize.PageSizeId.A4)
        self.preview.set_config(papel,
                                self.orient_combo.currentData() == "h",
                                self.color_combo.currentData() == "gris",
                                self.scale_combo.currentData() == "fit")

    def get_settings(self):
        return {
            "pdf": self._es_pdf(),
            "printer": self.printer_combo.currentData(),
            "copies": self.copies_spin.value(),
            "landscape": self.orient_combo.currentData() == "h",
            "page_size": self.paper_combo.currentData() or QPageSize(QPageSize.PageSizeId.A4),
            "gray": self.color_combo.currentData() == "gris",
            "duplex": (self.duplex_combo.currentData()
                       if self.duplex_combo.isEnabled()
                       else QPrinter.DuplexMode.DuplexNone),
            "fit": self.scale_combo.currentData() == "fit",
        }
