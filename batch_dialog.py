# batch_dialog.py
"""Procesamiento por lotes (Archivo ▸ Procesar por lotes...): aplica a todas
las imágenes de una carpeta redimensionado, conversión de formato y/o marca de
agua (texto o imagen PNG), guardando el resultado en OTRA carpeta sin tocar
los originales (si un nombre de destino ya existe se numera: aquí nunca se
sobreescribe nada).

El trabajo corre FUERA del hilo GUI vía InferenceRunner (ai/runner.py), un
archivo por iteración y con cancelación cooperativa entre archivo y archivo;
la GUI solo recibe el progreso y el resumen final (callbacks en el hilo GUI).
Pintar con QPainter sobre QImage es seguro en un hilo secundario (motor
raster); QPixmap NO se usa aquí a propósito. El runner lo crea y lo conserva
MainWindow (batch_process en ventana/menu_archivo.py): sobrevive al diálogo,
así cancelar cierra la GUI al momento y el trabajo muere solo en la siguiente
comprobación del token, sin señales hacia objetos destruidos.
"""
import os
import shutil

from atomic_io import escribir_atomico
from PySide6.QtCore import Qt, QPointF, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QProgressBar,
                               QPushButton, QSlider, QSpinBox)

import theme
from i18n import t
from utilidades import cargar_imagen_orientada
from widgets.custom_titlebar import FramelessDialog, imago_warning


# Formatos de salida CON canal alfa: se guardan sobre fondo transparente.
# El resto (JPG, BMP...) se aplana sobre blanco, como hace _save_image.
_EXTS_ALFA = {"png", "webp", "tif", "tiff", "gif", "tga", "ico", "icns",
              "xpm", "cur"}

# Posiciones de la marca de agua: (fila, columna) codificadas en dos letras
# (t/c/b = arriba/centro/abajo, l/c/r = izquierda/centro/derecha).
_POSICIONES = ("tl", "tc", "tr", "cl", "cc", "cr", "bl", "bc", "br")


def extensiones_legibles():
    """Extensiones de imagen que Imago sabe abrir: las de QImageReader más las
    del fallback de Pillow (AVIF/HEIC/JXL). Los vectoriales quedan fuera (un
    SVG rasterizado a su tamaño declarado no es lo que se espera de un lote)."""
    from PySide6.QtGui import QImageReader
    exts = {bytes(b).decode().lower() for b in QImageReader.supportedImageFormats()}
    exts |= {"jpeg", "tif", "avif", "heic", "heif", "jxl"}
    exts -= {"svg", "svgz"}
    return exts


def listar_imagenes(carpeta):
    """Rutas de las imágenes de `carpeta` (sin recursión), ordenadas por nombre.
    Devuelve [] si la carpeta no existe o no se puede leer."""
    exts = extensiones_legibles()
    try:
        with os.scandir(carpeta) as it:
            rutas = [e.path for e in it if e.is_file()
                     and os.path.splitext(e.name)[1].lower().lstrip(".") in exts]
    except OSError:
        return []
    return sorted(rutas, key=lambda r: os.path.basename(r).lower())


# ===========================================================================
#  Trabajo en el hilo secundario (funciones puras sobre los parámetros)
# ===========================================================================
def _ruta_unica(ruta):
    """Si `ruta` ya existe, numera el nombre (_1, _2...): nunca se pisa nada."""
    if not os.path.exists(ruta):
        return ruta
    base, ext = os.path.splitext(ruta)
    n = 1
    while os.path.exists(f"{base}_{n}{ext}"):
        n += 1
    return f"{base}_{n}{ext}"


def _ruta_destino(origen, p, num, ext=None):
    """Ruta de salida para `origen`: mismo nombre base (o «base_001, base_002…»
    si se pidió renombrar; `num` es el ordinal del archivo), con la extensión
    del formato elegido (o la original con «Mantener formato»), en la carpeta
    de destino. `ext` fuerza la extensión: la copia directa conserva la
    original SIN pasar por el chequeo de formatos escribibles (copiar un GIF o
    un AVIF es perfectamente posible; re-codificarlos no)."""
    if p["rename_base"]:
        nombre = "%s_%0*d" % (p["rename_base"], p["rename_pad"], num)
    else:
        nombre = os.path.splitext(os.path.basename(origen))[0]
    if ext is None:
        ext_src = os.path.splitext(origen)[1].lower().lstrip(".")
        ext = p["format"] or ext_src
        if ext not in p["writable_exts"]:
            # Formato solo de lectura (GIF, AVIF...): con «Mantener formato» no
            # hay salida posible; se avisa por archivo para que elija formato.
            raise ValueError(t("batch.err.format_ro", ext=ext_src.upper()))
    return _ruta_unica(os.path.join(p["dst_dir"], nombre + "." + ext))


def _redimensionar(img, p):
    modo = p["resize_mode"]
    if modo == "percent":
        pct = p["resize_percent"]
        if pct == 100:
            return img
        w = max(1, round(img.width() * pct / 100.0))
        h = max(1, round(img.height() * pct / 100.0))
        # Ambos lados llevan el mismo porcentaje: la proporción se conserva sola.
        return img.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    if modo == "fit":
        fw, fh = p["fit_w"], p["fit_h"]
        if p["only_shrink"] and img.width() <= fw and img.height() <= fh:
            return img
        return img.scaled(fw, fh, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return img


def _pos_xy(codigo, ancho, alto, w, h, margen):
    """Esquina superior izquierda de una marca de w×h según la posición
    elegida (dos letras: fila t/c/b + columna l/c/r) y el margen."""
    fila, col = codigo[0], codigo[1]
    if col == "l":
        x = margen
    elif col == "c":
        x = (ancho - w) / 2.0
    else:
        x = ancho - w - margen
    if fila == "t":
        y = margen
    elif fila == "c":
        y = (alto - h) / 2.0
    else:
        y = alto - h - margen
    return x, y


def _aplicar_marca(img, p):
    """Estampa la marca de agua (texto o imagen) sobre una copia ARGB de `img`."""
    modo = p["wm_mode"]
    if modo == "none":
        return img
    base = img.convertToFormat(QImage.Format_ARGB32_Premultiplied)
    ancho, alto = base.width(), base.height()
    margen = max(8, round(min(ancho, alto) * 0.03))
    painter = QPainter(base)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setOpacity(p["wm_opacity"] / 100.0)
    if modo == "text":
        px = max(8, round(alto * p["wm_text_pct"] / 100.0))
        font = QFont()
        font.setPixelSize(px)
        painter.setFont(font)
        fm = QFontMetricsF(font)
        w = fm.horizontalAdvance(p["wm_text"])
        h = fm.height()
        x, y = _pos_xy(p["wm_pos"], ancho, alto, w, h, margen)
        color = p["wm_color"]
        # Sombra de contraste (oscura bajo tinta clara y viceversa): sin ella,
        # un texto blanco sobre una zona clara desaparecería.
        sombra = QColor(0, 0, 0) if color.lightness() >= 128 else QColor(255, 255, 255)
        off = max(1.0, px / 24.0)
        painter.setPen(sombra)
        painter.drawText(QPointF(x + off, y + off + fm.ascent()), p["wm_text"])
        painter.setPen(color)
        painter.drawText(QPointF(x, y + fm.ascent()), p["wm_text"])
    else:
        marca = p["wm_image"]
        w_obj = max(1, round(ancho * p["wm_scale"] / 100.0))
        marca = marca.scaledToWidth(w_obj, Qt.SmoothTransformation)
        if marca.height() > alto:
            marca = marca.scaledToHeight(alto, Qt.SmoothTransformation)
        x, y = _pos_xy(p["wm_pos"], ancho, alto, marca.width(), marca.height(), margen)
        painter.drawImage(QPointF(x, y), marca)
    painter.end()
    return base


def _guardar(img, origen, destino, p):
    """Escribe `img` en `destino` (aplanando sobre blanco si el formato no tiene
    alfa) y, en JPEG→JPEG, reincrusta el EXIF crudo del original."""
    from PySide6.QtGui import QImageWriter
    ext = os.path.splitext(destino)[1].lower().lstrip(".")
    if ext not in _EXTS_ALFA and img.hasAlphaChannel():
        plano = QImage(img.size(), QImage.Format_RGB32)
        plano.fill(Qt.white)
        painter = QPainter(plano)
        painter.drawImage(0, 0, img)
        painter.end()
        plano.setDotsPerMeterX(img.dotsPerMeterX())
        plano.setDotsPerMeterY(img.dotsPerMeterY())
        img = plano
    def _escribir(ruta_temporal):
        writer = QImageWriter(ruta_temporal)
        if ext in ("jpg", "jpeg", "webp"):
            writer.setQuality(p["quality"])
        if not writer.write(img):
            return False
        ext_src = os.path.splitext(origen)[1].lower().lstrip(".")
        if p["keep_exif"] and ext in ("jpg", "jpeg") and ext_src in ("jpg", "jpeg"):
            # Igual que _save_image: el bloque EXIF se incrusta aún en el
            # temporal, antes de publicar el resultado definitivo.
            from exif_utils import leer_exif, incrustar_exif_jpeg
            incrustar_exif_jpeg(
                ruta_temporal, leer_exif(origen), incluir_gps=p["keep_gps"])
        return True

    if not escribir_atomico(destino, _escribir):
        raise ValueError(t("batch.err.save"))


def _trabajo_lote(p, report, token):
    """Función de trabajo (hilo secundario): procesa los archivos uno a uno y
    devuelve el resumen {ok, errores, cancelado}. Un archivo que falla se anota
    y NO detiene el resto."""
    resultado = {"ok": 0, "errores": [], "cancelado": False}
    total = max(1, len(p["files"]))
    contador = 0    # ordinal del renombrado: solo avanza si el archivo se lee
    # COPIA DIRECTA: sin transformación alguna (ni redimensionar, ni marca de
    # agua, ni conversión), el archivo se copia byte a byte: idéntico en
    # píxeles, peso y metadatos (nada de pérdida generacional JPEG ni de
    # hornear la rotación EXIF, que intercambiaba ancho×alto en las fotos de
    # móvil). Quien quiera RE-COMPRIMIR una carpeta con la calidad del slider
    # debe elegir JPEG/WebP como formato de salida, no «Mantener formato».
    copia_directa = (p["resize_mode"] == "no" and p["wm_mode"] == "none"
                     and p["format"] is None)
    for i, origen in enumerate(p["files"]):
        if token.cancelled:
            resultado["cancelado"] = True
            break
        try:
            if copia_directa:
                contador += 1
                ext = os.path.splitext(origen)[1].lower().lstrip(".")
                destino = _ruta_destino(origen, p, contador, ext=ext)
                if not escribir_atomico(
                        destino, lambda temporal: bool(shutil.copy2(origen, temporal))):
                    raise ValueError(t("batch.err.save"))
                resultado["ok"] += 1
                report(round((i + 1) * 100 / total))
                continue
            img = cargar_imagen_orientada(origen)
            if img is None or img.isNull():
                raise ValueError(t("batch.err.unreadable"))
            dpm_x, dpm_y = img.dotsPerMeterX(), img.dotsPerMeterY()
            img = _redimensionar(img, p)
            img = _aplicar_marca(img, p)
            # Conservar la resolución de impresión (PPP) del original.
            if dpm_x > 0:
                img.setDotsPerMeterX(dpm_x)
            if dpm_y > 0:
                img.setDotsPerMeterY(dpm_y)
            contador += 1
            destino = _ruta_destino(origen, p, contador)
            _guardar(img, origen, destino, p)
            resultado["ok"] += 1
        except Exception as exc:   # noqa: BLE001 (cada archivo se reporta aparte)
            resultado["errores"].append("%s: %s" % (os.path.basename(origen), exc))
        report(round((i + 1) * 100 / total))
    return resultado


# ===========================================================================
#  Diálogo
# ===========================================================================
class BatchDialog(FramelessDialog):
    """Diálogo del procesamiento por lotes. Recibe el runner ya creado (vive
    en MainWindow, ver el docstring del módulo)."""

    def __init__(self, parent, runner):
        super().__init__(parent)
        self._main = parent
        self._runner = runner
        self._handle = None      # TaskHandle del lote en curso (None = parado)
        self._total = 0
        self.setWindowTitle(t("batch.title"))
        self.setMinimumWidth(540)
        self.setStyleSheet(
            "QDialog { background-color: %s; } QLabel { color: %s; }"
            % (theme.BG_WINDOW, theme.TEXT)
            + theme.spinbox_dialog_qss() + theme.combobox_dialog_qss()
            + theme.checkbox_qss() + theme.slider_qss() + theme.lineedit_qss()
            + theme.progressbar_qss() + theme.dialog_button_plain_qss()
        )

        root = self.body_layout
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        root.addLayout(grid)
        self._grid = grid
        self._fila = 0
        # Controles a congelar mientras el lote corre (todos menos los botones).
        self._controles = []

        # ----------------------------------------------------- carpetas
        self.src_edit = QLineEdit()
        btn_src = QPushButton(t("batch.browse"))
        btn_src.clicked.connect(self._browse_src)
        self._add_row(t("batch.src"), self.src_edit, btn_src)

        self.found_label = QLabel("")
        self.found_label.setStyleSheet(f"color:{theme.TEXT_DIM}; font-style:italic;")
        grid.addWidget(self.found_label, self._fila, 1, 1, 2)
        self._fila += 1

        self.dst_edit = QLineEdit()
        btn_dst = QPushButton(t("batch.browse"))
        btn_dst.clicked.connect(self._browse_dst)
        self._add_row(t("batch.dst"), self.dst_edit, btn_dst)

        # ------------------------------------------------- redimensionar
        self.resize_combo = QComboBox()
        self.resize_combo.addItem(t("batch.resize.no"), "no")
        self.resize_combo.addItem(t("batch.resize.percent"), "percent")
        self.resize_combo.addItem(t("batch.resize.fit"), "fit")
        self._add_row(t("batch.resize"), self.resize_combo)

        self.percent_spin = QSpinBox()
        self.percent_spin.setRange(1, 1000)
        self.percent_spin.setValue(50)
        self.percent_spin.setSuffix(" %")
        self._row_percent = self._add_row("", self.percent_spin)

        fila_fit = QHBoxLayout()
        self.fit_w_spin = QSpinBox()
        self.fit_w_spin.setRange(1, 30000)
        self.fit_w_spin.setValue(1920)
        self.fit_h_spin = QSpinBox()
        self.fit_h_spin.setRange(1, 30000)
        self.fit_h_spin.setValue(1920)
        fila_fit.addWidget(self.fit_w_spin)
        lbl_x = QLabel("×")
        fila_fit.addWidget(lbl_x)
        fila_fit.addWidget(self.fit_h_spin)
        self.only_shrink_chk = QCheckBox(t("batch.resize.only_shrink"))
        self.only_shrink_chk.setChecked(True)
        fila_fit.addWidget(self.only_shrink_chk, 1)
        self._row_fit = self._add_row(t("batch.resize.fit_px"), fila_fit,
                                      extras=[self.fit_w_spin, lbl_x,
                                              self.fit_h_spin, self.only_shrink_chk])

        # ------------------------------------------------------- formato
        self.format_combo = QComboBox()
        self.format_combo.addItem(t("batch.format.keep"), None)
        for ext, texto in (("png", "PNG"), ("jpg", "JPEG"), ("webp", "WebP"),
                           ("bmp", "BMP"), ("tif", "TIFF")):
            self.format_combo.addItem(texto, ext)
        self._add_row(t("batch.format"), self.format_combo)

        fila_q = QHBoxLayout()
        self.quality_slider = QSlider(Qt.Orientation.Horizontal)
        self.quality_slider.setRange(1, 100)
        self.quality_slider.setValue(92)
        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(1, 100)
        self.quality_spin.setValue(92)
        self.quality_slider.valueChanged.connect(self.quality_spin.setValue)
        self.quality_spin.valueChanged.connect(self.quality_slider.setValue)
        fila_q.addWidget(self.quality_slider, 1)
        fila_q.addWidget(self.quality_spin)
        self._row_quality = self._add_row(t("batch.quality"), fila_q,
                                          extras=[self.quality_slider, self.quality_spin])

        self.keep_exif_chk = QCheckBox(t("batch.keep_exif"))
        self.keep_exif_chk.setChecked(True)
        grid.addWidget(self.keep_exif_chk, self._fila, 1, 1, 2)
        self._controles.append(self.keep_exif_chk)
        self._fila += 1

        # ----------------------------------------------------- renombrar
        # La casilla hace de etiqueta de la fila; el campo da el nombre base y
        # la numeración (base_001, base_002...) la añade el lote por su cuenta.
        self.rename_chk = QCheckBox(t("batch.rename"))
        self.rename_edit = QLineEdit()
        self.rename_edit.setEnabled(False)
        self.rename_chk.toggled.connect(self.rename_edit.setEnabled)
        grid.addWidget(self.rename_chk, self._fila, 0)
        grid.addWidget(self.rename_edit, self._fila, 1, 1, 2)
        self._controles.extend([self.rename_chk, self.rename_edit])
        self._fila += 1

        self.rename_hint = QLabel("")
        self.rename_hint.setStyleSheet(f"color:{theme.TEXT_DIM}; font-style:italic;")
        grid.addWidget(self.rename_hint, self._fila, 1, 1, 2)
        self._fila += 1
        self.rename_edit.textChanged.connect(self._update_rename_hint)
        self.rename_chk.toggled.connect(self._update_rename_hint)

        # ------------------------------------------------- marca de agua
        self.wm_combo = QComboBox()
        self.wm_combo.addItem(t("batch.wm.none"), "none")
        self.wm_combo.addItem(t("batch.wm.text"), "text")
        self.wm_combo.addItem(t("batch.wm.image"), "image")
        self._add_row(t("batch.wm"), self.wm_combo)

        self.wm_text_edit = QLineEdit()
        self._row_wm_text = self._add_row(t("batch.wm.text_lbl"), self.wm_text_edit)

        self.wm_size_spin = QSpinBox()
        self.wm_size_spin.setRange(1, 50)
        self.wm_size_spin.setValue(5)
        self.wm_size_spin.setSuffix(" %")
        self._row_wm_size = self._add_row(t("batch.wm.size"), self.wm_size_spin)

        self.wm_color_combo = QComboBox()
        self.wm_color_combo.addItem(t("batch.wm.white"), "white")
        self.wm_color_combo.addItem(t("batch.wm.black"), "black")
        self.wm_color_combo.addItem(t("batch.wm.primary"), "primary")
        self._row_wm_color = self._add_row(t("batch.wm.color"), self.wm_color_combo)

        self.wm_image_edit = QLineEdit()
        btn_wm = QPushButton(t("batch.browse"))
        btn_wm.clicked.connect(self._browse_wm_image)
        self._row_wm_image = self._add_row(t("batch.wm.image_lbl"),
                                           self.wm_image_edit, btn_wm)

        self.wm_scale_spin = QSpinBox()
        self.wm_scale_spin.setRange(1, 100)
        self.wm_scale_spin.setValue(25)
        self.wm_scale_spin.setSuffix(" %")
        self._row_wm_scale = self._add_row(t("batch.wm.scale"), self.wm_scale_spin)

        self.wm_pos_combo = QComboBox()
        for codigo in _POSICIONES:
            self.wm_pos_combo.addItem(t("batch.pos." + codigo), codigo)
        self.wm_pos_combo.setCurrentIndex(len(_POSICIONES) - 1)   # abajo derecha
        self._row_wm_pos = self._add_row(t("batch.wm.pos"), self.wm_pos_combo)

        fila_op = QHBoxLayout()
        self.wm_opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.wm_opacity_slider.setRange(1, 100)
        self.wm_opacity_slider.setValue(50)
        self.wm_opacity_spin = QSpinBox()
        self.wm_opacity_spin.setRange(1, 100)
        self.wm_opacity_spin.setValue(50)
        self.wm_opacity_slider.valueChanged.connect(self.wm_opacity_spin.setValue)
        self.wm_opacity_spin.valueChanged.connect(self.wm_opacity_slider.setValue)
        fila_op.addWidget(self.wm_opacity_slider, 1)
        fila_op.addWidget(self.wm_opacity_spin)
        self._row_wm_opacity = self._add_row(t("batch.wm.opacity"), fila_op,
                                             extras=[self.wm_opacity_slider,
                                                     self.wm_opacity_spin])

        # ---------------------------------------------- progreso y botones
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setVisible(False)
        root.addWidget(self.progress)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet(f"color:{theme.INFO_BLUE};")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        botones = QHBoxLayout()
        botones.addStretch()
        self.btn_process = QPushButton(t("batch.process"))
        self.btn_process.clicked.connect(self._on_process)
        self.btn_cancel = QPushButton(t("common.cancel"))
        self.btn_cancel.clicked.connect(self._on_cancel)
        self.btn_cancel.setVisible(False)
        self.btn_close = QPushButton(t("common.close"))
        self.btn_close.clicked.connect(self.reject)
        botones.addWidget(self.btn_process)
        botones.addWidget(self.btn_cancel)
        botones.addWidget(self.btn_close)
        root.addLayout(botones)

        # Sincronización de visibilidad y del contador de imágenes (el contador
        # con un pequeño retardo para no escanear el disco a cada tecla).
        self._found_timer = QTimer(self)
        self._found_timer.setSingleShot(True)
        self._found_timer.setInterval(300)
        self._found_timer.timeout.connect(self._update_found)
        self.src_edit.textChanged.connect(lambda _=None: self._found_timer.start())
        self.resize_combo.currentIndexChanged.connect(self._sync_rows)
        self.format_combo.currentIndexChanged.connect(self._sync_rows)
        self.wm_combo.currentIndexChanged.connect(self._sync_rows)
        self._sync_rows()

    # ------------------------------------------------------------- helpers UI
    def _add_row(self, etiqueta, control, boton=None, extras=None):
        """Añade una fila [etiqueta | control (o layout) | botón] a la rejilla y
        devuelve la lista de widgets de la fila (para mostrarla/ocultarla)."""
        fila = []
        lbl = QLabel(etiqueta)
        self._grid.addWidget(lbl, self._fila, 0)
        fila.append(lbl)
        if hasattr(control, "addWidget"):     # es un layout
            self._grid.addLayout(control, self._fila, 1, 1, 1 if boton else 2)
            fila.extend(extras or [])
        else:
            self._grid.addWidget(control, self._fila, 1, 1, 1 if boton else 2)
            fila.append(control)
        if boton is not None:
            self._grid.addWidget(boton, self._fila, 2)
            fila.append(boton)
        self._controles.extend(w for w in fila if not isinstance(w, QLabel))
        self._fila += 1
        return fila

    @staticmethod
    def _set_row_visible(fila, visible):
        for w in fila:
            w.setVisible(visible)

    def _sync_rows(self):
        modo_r = self.resize_combo.currentData()
        self._set_row_visible(self._row_percent, modo_r == "percent")
        self._set_row_visible(self._row_fit, modo_r == "fit")
        fmt = self.format_combo.currentData()
        self._set_row_visible(self._row_quality, fmt in (None, "jpg", "webp"))
        modo_w = self.wm_combo.currentData()
        self._set_row_visible(self._row_wm_text, modo_w == "text")
        self._set_row_visible(self._row_wm_size, modo_w == "text")
        self._set_row_visible(self._row_wm_color, modo_w == "text")
        self._set_row_visible(self._row_wm_image, modo_w == "image")
        self._set_row_visible(self._row_wm_scale, modo_w == "image")
        self._set_row_visible(self._row_wm_pos, modo_w != "none")
        self._set_row_visible(self._row_wm_opacity, modo_w != "none")
        self.adjustSize()

    def _browse_src(self):
        carpeta = QFileDialog.getExistingDirectory(
            self, t("batch.src"), self.src_edit.text() or os.path.expanduser("~"))
        if carpeta:
            self.src_edit.setText(carpeta)
            if not self.dst_edit.text().strip():
                self.dst_edit.setText(
                    os.path.join(carpeta, t("batch.default_subdir")))

    def _browse_dst(self):
        carpeta = QFileDialog.getExistingDirectory(
            self, t("batch.dst"), self.dst_edit.text() or self.src_edit.text()
            or os.path.expanduser("~"))
        if carpeta:
            self.dst_edit.setText(carpeta)

    def _browse_wm_image(self):
        ruta, _ = QFileDialog.getOpenFileName(
            self, t("batch.wm.image_lbl"), self.wm_image_edit.text() or "",
            t("batch.wm.image_filter") + " (*.png)")
        if ruta:
            self.wm_image_edit.setText(ruta)

    def _update_rename_hint(self, _=None):
        """Ejemplo en vivo del renombrado («Fondo_001, Fondo_002, …»)."""
        base = self.rename_edit.text().strip()
        if self.rename_chk.isChecked() and base:
            self.rename_hint.setText("%s_001, %s_002, …" % (base, base))
        else:
            self.rename_hint.setText("")

    def _update_found(self):
        carpeta = self.src_edit.text().strip()
        if not carpeta:
            self.found_label.setText("")
            return
        n = len(listar_imagenes(carpeta))
        self.found_label.setText(t("batch.found", n=n) if n
                                 else t("batch.found_none"))

    def _color_primario(self):
        """Color primario actual de Imago (el del panel de color / lienzo)."""
        canvas = None
        if hasattr(self._main, "get_current_canvas"):
            canvas = self._main.get_current_canvas()
        color = getattr(canvas, "brush_color", None)
        if color is None:
            panel = getattr(self._main, "colors_panel", None)
            try:
                color = panel.preview_box.color()
            except AttributeError:
                color = QColor("#000000")
        return QColor(color)

    # ------------------------------------------------------------ proceso
    def _aviso(self, texto):
        imago_warning(self, t("batch.title"), texto)

    def _on_process(self):
        origen = self.src_edit.text().strip()
        destino = self.dst_edit.text().strip()
        if not origen or not os.path.isdir(origen):
            self._aviso(t("batch.err.no_src"))
            return
        archivos = listar_imagenes(origen)
        if not archivos:
            self._aviso(t("batch.err.no_images"))
            return
        if not destino:
            self._aviso(t("batch.err.no_dst"))
            return
        try:
            os.makedirs(destino, exist_ok=True)
        except OSError:
            self._aviso(t("batch.err.dst_create"))
            return

        rename_base = None
        if self.rename_chk.isChecked():
            rename_base = self.rename_edit.text().strip()
            if not rename_base:
                self._aviso(t("batch.err.rename"))
                return
            if any(c in rename_base for c in '<>:"/\\|?*'):
                self._aviso(t("batch.err.rename_chars"))
                return

        modo_wm = self.wm_combo.currentData()
        wm_image = None
        if modo_wm == "text" and not self.wm_text_edit.text().strip():
            self._aviso(t("batch.err.no_text"))
            return
        if modo_wm == "image":
            wm_image = QImage(self.wm_image_edit.text().strip())
            if wm_image.isNull():
                self._aviso(t("batch.err.wm_image"))
                return

        colores = {"white": QColor("#ffffff"), "black": QColor("#000000")}
        clave_color = self.wm_color_combo.currentData()
        wm_color = colores.get(clave_color) or self._color_primario()

        from PySide6.QtGui import QImageWriter
        escribibles = {bytes(b).decode().lower()
                       for b in QImageWriter.supportedImageFormats()}

        settings = getattr(self._main, "settings", None)
        keep_gps = settings.value("save/keep_gps", True, type=bool) if settings else True

        params = {
            "files": archivos,
            "dst_dir": destino,
            "writable_exts": escribibles,
            "resize_mode": self.resize_combo.currentData(),
            "resize_percent": self.percent_spin.value(),
            "fit_w": self.fit_w_spin.value(),
            "fit_h": self.fit_h_spin.value(),
            "only_shrink": self.only_shrink_chk.isChecked(),
            "format": self.format_combo.currentData(),
            "quality": self.quality_spin.value(),
            "rename_base": rename_base,
            "rename_pad": max(3, len(str(len(archivos)))),
            "keep_exif": self.keep_exif_chk.isChecked(),
            "keep_gps": keep_gps,
            "wm_mode": modo_wm,
            "wm_text": self.wm_text_edit.text().strip(),
            "wm_text_pct": self.wm_size_spin.value(),
            "wm_color": wm_color,
            "wm_image": wm_image,
            "wm_scale": self.wm_scale_spin.value(),
            "wm_pos": self.wm_pos_combo.currentData(),
            "wm_opacity": self.wm_opacity_spin.value(),
        }

        self._total = len(archivos)
        self._set_running(True)
        self.progress.setValue(0)
        self.status_label.setText(t("batch.working", i=0, n=self._total))
        self._handle = self._runner.submit(
            lambda report, token: _trabajo_lote(params, report, token),
            on_done=self._on_done, on_error=self._on_error,
            on_progress=self._on_progress)

    def _set_running(self, corriendo):
        for w in self._controles:
            w.setEnabled(not corriendo)
        self.btn_process.setEnabled(not corriendo)
        self.btn_cancel.setVisible(corriendo)
        self.progress.setVisible(corriendo)
        if not corriendo:
            self._handle = None

    def _on_progress(self, pct):
        self.progress.setValue(pct)
        hechos = round(pct * self._total / 100)
        self.status_label.setText(t("batch.working", i=hechos, n=self._total))

    def _on_done(self, resultado):
        self._set_running(False)
        errores = resultado["errores"]
        if resultado.get("cancelado"):
            self.status_label.setText(t("batch.cancelled", ok=resultado["ok"]))
        elif errores:
            self.status_label.setText(
                t("batch.done_err", ok=resultado["ok"], err=len(errores)))
        else:
            self.status_label.setText(t("batch.done", ok=resultado["ok"]))
        if errores:
            detalle = "\n".join(errores[:12])
            if len(errores) > 12:
                detalle += "\n…"
            self._aviso(t("batch.errors_detail") + "\n\n" + detalle)

    def _on_error(self, mensaje):
        # Solo llega si el propio bucle revienta (los archivos fallidos se
        # recogen uno a uno en el resumen): se enseña tal cual.
        self._set_running(False)
        self.status_label.setText("")
        self._aviso(mensaje)

    def _on_cancel(self):
        if self._handle is not None:
            self._handle.cancel()
        # Una tarea cancelada NO entrega callbacks (contrato del runner): la GUI
        # se repone aquí mismo; el trabajo muere al siguiente chequeo del token.
        self._set_running(False)
        self.status_label.setText(t("batch.cancelled_simple"))

    def reject(self):
        if self._handle is not None:
            self._handle.cancel()
            self._handle = None
        super().reject()
