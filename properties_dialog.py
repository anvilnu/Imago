from i18n import t
# properties_dialog.py — Imagen > Propiedades de imagen: visor de metadatos.
# Muestra lo general (dimensiones, PPP, capas, archivo), el EXIF que la imagen
# traiga (cámara, fecha, exposición, GPS con enlace al mapa) y un histograma
# de luminosidad. El EXIF crudo ya viaja en canvas.source_exif (exif_utils lo
# conserva al guardar); aquí solo se DECODIFICA para verlo (Pillow, perezoso).

import os
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QPainter, QPen
from PySide6.QtWidgets import (QGridLayout, QHBoxLayout, QLabel, QPushButton,
                               QWidget)
from widgets.custom_titlebar import FramelessDialog
import theme


def _gps_grados(valor, ref):
    """(grados, minutos, segundos) EXIF -> grados decimales con signo."""
    try:
        g, m, s = (float(v) for v in valor)
        dec = g + m / 60.0 + s / 3600.0
        if str(ref).upper().strip() in ("S", "W"):
            dec = -dec
        return round(dec, 6)
    except Exception:
        return None


def exif_decodificado(raw):
    """Parsea el bloque EXIF crudo con Pillow y devuelve un dict con los campos
    del diálogo: camera, date, exposure, gps=(lat, lon). {} si no hay o falla."""
    if not raw:
        return {}
    try:
        from PIL import Image
        ex = Image.Exif()
        ex.load(raw)
        d = {}
        make = str(ex.get(271, "")).strip("\x00 ").strip()
        model = str(ex.get(272, "")).strip("\x00 ").strip()
        if make and model and model.lower().startswith(make.lower()):
            make = ""   # muchos móviles repiten la marca dentro del modelo
        camara = (make + " " + model).strip()
        if camara:
            d["camera"] = camara

        sub = ex.get_ifd(0x8769)   # IFD Exif (fecha original, exposición...)
        fecha = sub.get(0x9003) or ex.get(306)
        if fecha:
            d["date"] = str(fecha)

        partes = []
        texp = sub.get(0x829A)     # ExposureTime
        if texp:
            texp = float(texp)
            if 0 < texp < 1:
                partes.append("1/%d s" % round(1.0 / texp))
            elif texp > 0:
                partes.append("%g s" % texp)
        fnum = sub.get(0x829D)     # FNumber
        if fnum and float(fnum) > 0:
            partes.append("f/%g" % float(fnum))
        iso = sub.get(0x8827)      # ISO
        if isinstance(iso, (tuple, list)):
            iso = iso[0] if iso else None
        try:
            iso = int(iso) if iso else None
        except (TypeError, ValueError):
            iso = None
        if iso:
            partes.append("ISO %d" % iso)
        focal = sub.get(0x920A)    # FocalLength
        if focal and float(focal) > 0:
            partes.append("%g mm" % float(focal))
        if partes:
            d["exposure"] = " · ".join(partes)

        gps = ex.get_ifd(0x8825)   # IFD GPS
        lat = _gps_grados(gps.get(2), gps.get(1))
        lon = _gps_grados(gps.get(4), gps.get(3))
        if lat is not None and lon is not None and (lat, lon) != (0.0, 0.0):
            d["gps"] = (lat, lon)
        return d
    except Exception:
        return {}


def _tamano_legible(n):
    """Bytes -> texto corto (KB/MB)."""
    if n >= 1024 * 1024:
        return "%.2f MB" % (n / (1024.0 * 1024.0))
    if n >= 1024:
        return "%.1f KB" % (n / 1024.0)
    return "%d B" % n


class _HistogramaWidget(QWidget):
    """Histograma de LUMINOSIDAD de la imagen aplanada (256 niveles), pintado
    con los colores del tema. Ignora los píxeles totalmente transparentes."""

    def __init__(self, qimg, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(96)
        import numpy as np
        from adjustments import qimage_to_array
        arr = qimage_to_array(qimg)
        rgb = arr[..., :3].astype(np.float32)
        lum = rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114
        lum = lum[arr[..., 3] > 0]
        if lum.size:
            self._hist = np.bincount(np.clip(lum, 0, 255).astype(np.int32),
                                     minlength=256).astype(np.float64)
        else:
            self._hist = np.zeros(256, dtype=np.float64)

    def paintEvent(self, event):
        p = QPainter(self)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor(theme.BG_DARK))
        maximo = float(self._hist.max())
        if maximo > 0 and w > 4:
            p.setPen(QPen(QColor(theme.ACCENT)))
            interior = w - 2
            for x in range(interior):
                nivel = int(x * 256 / interior)
                alto = int((self._hist[nivel] / maximo) * (h - 4))
                if alto > 0:
                    p.drawLine(1 + x, h - 2, 1 + x, h - 2 - alto)
        p.setPen(QPen(QColor(theme.BORDER)))
        p.drawRect(0, 0, w - 1, h - 1)
        p.end()


class ImagePropertiesDialog(FramelessDialog):
    """Propiedades de imagen (solo LECTURA): general + EXIF + histograma."""

    def __init__(self, main_window, canvas):
        super().__init__(main_window)
        self.setWindowTitle(t("dlg.props.title", default="Propiedades de imagen"))
        self._body.setFixedWidth(430)
        self.setStyleSheet(
            "QDialog { background-color: %s; } QLabel { color: %s; }"
            % (theme.BG_WINDOW, theme.TEXT)
            + theme.dialog_button_plain_qss()
        )

        layout = self.body_layout

        def cabecera(texto):
            lbl = QLabel(texto)
            lbl.setStyleSheet("font-weight: bold; color: %s;" % theme.TEXT)
            return lbl

        def fila(g, r, clave, valor):
            lbl = QLabel(clave)
            lbl.setStyleSheet("color: %s;" % theme.TEXT_MUTED)
            v = QLabel(valor)
            v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            v.setWordWrap(True)
            g.addWidget(lbl, r, 0, Qt.AlignmentFlag.AlignTop)
            g.addWidget(v, r, 1)
            return r + 1

        # ------------------------------------------------------- General
        layout.addWidget(cabecera(t("dlg.props.general")))
        g = QGridLayout()
        g.setColumnMinimumWidth(0, 130)
        g.setColumnStretch(1, 1)
        g.setVerticalSpacing(4)
        W, H = canvas.base_width, canvas.base_height
        dpi = float(getattr(canvas, "dpi", 96.0)) or 96.0
        r = fila(g, 0, t("dlg.props.dimensions"), "%d × %d px" % (W, H))
        r = fila(g, r, t("dlg.props.resolution"), "%g PPP" % dpi)
        r = fila(g, r, t("dlg.props.print_size"),
                 "%.2f × %.2f cm" % (W / dpi * 2.54, H / dpi * 2.54))
        r = fila(g, r, t("dlg.props.layers"), str(len(canvas.layers)))
        ruta = (getattr(canvas, "image_path", None)
                or getattr(canvas, "project_path", None))
        if ruta:
            r = fila(g, r, t("dlg.props.file"), ruta)
            try:
                r = fila(g, r, t("dlg.props.file_size"),
                         _tamano_legible(os.path.getsize(ruta)))
            except OSError:
                pass
        else:
            r = fila(g, r, t("dlg.props.file"), t("dlg.props.no_file"))
        layout.addLayout(g)
        layout.addSpacing(10)

        # ---------------------------------------------------------- EXIF
        layout.addWidget(cabecera(t("dlg.props.exif")))
        exif = exif_decodificado(getattr(canvas, "source_exif", None))
        if exif:
            g2 = QGridLayout()
            g2.setColumnMinimumWidth(0, 130)
            g2.setColumnStretch(1, 1)
            g2.setVerticalSpacing(4)
            r = 0
            if exif.get("camera"):
                r = fila(g2, r, t("dlg.props.camera"), exif["camera"])
            if exif.get("date"):
                r = fila(g2, r, t("dlg.props.date"), exif["date"])
            if exif.get("exposure"):
                r = fila(g2, r, t("dlg.props.exposure"), exif["exposure"])
            if exif.get("gps"):
                lat, lon = exif["gps"]
                r = fila(g2, r, t("dlg.props.gps"), "%.6f, %.6f" % (lat, lon))
            layout.addLayout(g2)
            if exif.get("gps"):
                lat, lon = exif["gps"]
                url = ("https://www.openstreetmap.org/?mlat=%f&mlon=%f"
                       "#map=16/%f/%f" % (lat, lon, lat, lon))
                fila_mapa = QHBoxLayout()
                btn_mapa = QPushButton(t("dlg.props.map"))
                btn_mapa.clicked.connect(
                    lambda _=False, u=url: QDesktopServices.openUrl(QUrl(u)))
                fila_mapa.addWidget(btn_mapa)
                fila_mapa.addStretch()
                layout.addSpacing(4)
                layout.addLayout(fila_mapa)
        else:
            sin = QLabel(t("dlg.props.no_exif"))
            sin.setStyleSheet("color: %s; font-style: italic;" % theme.TEXT_MUTED)
            layout.addWidget(sin)
        layout.addSpacing(10)

        # ----------------------------------------------------- Histograma
        layout.addWidget(cabecera(t("dlg.props.histogram")))
        layout.addWidget(_HistogramaWidget(
            canvas.render_flat_image(background=Qt.transparent)))
        layout.addSpacing(10)

        btns = QHBoxLayout()
        btns.addStretch()
        cerrar = QPushButton(t("common.close"))
        cerrar.clicked.connect(self.accept)
        btns.addWidget(cerrar)
        layout.addLayout(btns)
