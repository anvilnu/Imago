# tools/heal_tool.py
from i18n import t
import math
import numpy as np
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QImage, QPainter, QColor
from tools.base_tool import BaseTool
from tools.commands import PaintCommand


class HealTool(BaseTool):
    """Pincel corrector (spot healing). Se pinta sobre la imperfección (mancha,
    grano, cable...) y, al soltar, la zona marcada se RECONSTRUYE a partir de
    su entorno con cv2.inpaint (Telea), sin elegir origen (a diferencia de
    Clonar). Mientras se pinta, la zona marcada se resalta en el color de
    acento; al soltar se aplica la corrección como UN paso de deshacer.

    - Tamaño: compartido con el pincel.
    - Respeta la selección activa (solo corrige dentro).
    - cv2 (opencv) se importa PEREZOSAMENTE: si no está instalado, la
      herramienta avisa una vez y no hace nada (Imago sigue funcionando).
    """

    _cv2_avisado = False   # aviso de OpenCV ausente: una sola vez por sesión

    def __init__(self, canvas):
        super().__init__(canvas)
        self.tool_id = "heal"
        self._active = False
        self._before = None
        self._preview = None      # QImage con el resaltado del trazo
        self._mask_img = None     # QImage Grayscale8: zona marcada (255)
        self._last = None
        self._orig_fmt = None

    # ------------------------------------------------------------- OpenCV
    def _cv2(self):
        """Importa cv2 en el momento de usarlo; None (con aviso) si falta."""
        try:
            import cv2
            return cv2
        except ImportError:
            if not HealTool._cv2_avisado:
                HealTool._cv2_avisado = True
                from widgets.custom_titlebar import imago_warning
                imago_warning(self.canvas.window(),
                              t("tool.name.heal"),
                              t("heal.no_cv2",
                                default="El Pincel corrector necesita OpenCV "
                                        "(opencv-python-headless), que no está "
                                        "instalado."))
            return None

    # ------------------------------------------------------------- ratón
    def mouse_press(self, event):
        if event.button() != Qt.LeftButton:
            return
        if self._cv2() is None:
            return
        img = self.canvas.get_active_layer()
        if img is None:
            return
        self._orig_fmt = img.format()
        self._before = QImage(img)
        self._preview = img.convertToFormat(QImage.Format_ARGB32)
        self._mask_img = QImage(img.width(), img.height(), QImage.Format_Grayscale8)
        self._mask_img.fill(0)
        pos = event.position() / self.canvas.zoom_factor
        self._last = (pos.x(), pos.y())
        self._stamp(pos.x(), pos.y())
        self._active = True
        self._flush_preview()

    def mouse_move(self, event):
        if not self._active:
            return
        pos = event.position() / self.canvas.zoom_factor
        x1, y1 = pos.x(), pos.y()
        x0, y0 = self._last
        dist = math.hypot(x1 - x0, y1 - y0)
        step = max(1.0, self.canvas.brush_size * 0.25)
        n = max(1, int(dist / step))
        for i in range(1, n + 1):
            f = i / n
            self._stamp(x0 + (x1 - x0) * f, y0 + (y1 - y0) * f)
        self._last = (x1, y1)
        self._flush_preview()

    def mouse_release(self, event):
        if self._active:
            self._active = False
            self._apply()

    def finish_editing(self):
        if self._active:
            self._active = False
            self._apply()

    # --------------------------------------------------------- trazo
    def _stamp(self, cx, cy):
        """Marca un círculo del tamaño del pincel en la máscara y pinta el
        resaltado de vista previa (recortados a la selección, si la hay)."""
        r = max(0.5, self.canvas.brush_size / 2.0)
        sel = getattr(self.canvas, 'selection', None)
        import theme
        acento = QColor(theme.ACCENT)
        acento.setAlpha(110)
        for target, color in ((self._mask_img, QColor(255, 255, 255)),
                              (self._preview, acento)):
            p = QPainter(target)
            if sel is not None and not sel.isEmpty():
                p.setClipPath(sel)
            p.setRenderHint(QPainter.Antialiasing, False)
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            p.drawEllipse(QPointF(cx, cy), r, r)
            p.end()

    def _flush_preview(self):
        self.canvas.layers[self.canvas.active_layer_index].image = self._preview
        self.canvas.update()

    # --------------------------------------------------------- corrección
    def _apply(self):
        cv2 = self._cv2()
        layer = self.canvas.layers[self.canvas.active_layer_index]
        # Quitar el resaltado: se parte SIEMPRE de la imagen original
        layer.image = QImage(self._before)

        mask = self._mask_array()
        ys, xs = np.nonzero(mask)
        if cv2 is None or ys.size == 0:
            self._cleanup()
            self.canvas.update()
            return

        # Región de trabajo: caja del trazo + margen de contexto para inpaint
        H, W = mask.shape
        margen = int(max(16, self.canvas.brush_size * 2))
        y0 = max(0, ys.min() - margen); y1 = min(H, ys.max() + 1 + margen)
        x0 = max(0, xs.min() - margen); x1 = min(W, xs.max() + 1 + margen)

        u8 = self._qimage_to_array(layer.image)                 # (H,W,4) RGBA
        sub = u8[y0:y1, x0:x1]
        sub_mask = mask[y0:y1, x0:x1].copy()
        # Solo se corrigen píxeles con contenido (el alfa no se toca)
        sub_mask[sub[..., 3] == 0] = 0
        if not sub_mask.any():
            self._cleanup()
            self.canvas.update()
            return

        bgr = np.ascontiguousarray(sub[..., 2::-1])             # RGB -> BGR
        healed = cv2.inpaint(bgr, sub_mask, 3, cv2.INPAINT_TELEA)
        rgb = healed[..., ::-1]
        m = sub_mask > 0
        sub[..., :3][m] = rgb[m]

        out = self._array_to_qimage(u8).convertToFormat(self._orig_fmt)
        layer.image = out
        after = QImage(out)
        self.canvas.undo_stack.push(PaintCommand(
            self.canvas, self.canvas.active_layer_index,
            self._before, after, t("hist.heal"), tool_id="heal", confine=True,
            dirty_rect=(x0, y0, x1, y1)))
        self._cleanup()
        self.canvas.update()

    def _cleanup(self):
        self._before = self._preview = self._mask_img = None

    # --------------------------------------------------------- QImage<->numpy
    def _mask_array(self):
        bpl = self._mask_img.bytesPerLine()
        H, W = self._mask_img.height(), self._mask_img.width()
        buf = np.frombuffer(self._mask_img.constBits(), np.uint8).reshape(H, bpl)
        return np.where(buf[:, :W] > 127, np.uint8(255), np.uint8(0))

    def _qimage_to_array(self, qimg):
        qimg = qimg.convertToFormat(QImage.Format_RGBA8888)
        W, H = qimg.width(), qimg.height()
        bpl = qimg.bytesPerLine()
        buf = np.frombuffer(qimg.constBits(), np.uint8).reshape(H, bpl)
        return buf[:, :W * 4].reshape(H, W, 4).copy()

    def _array_to_qimage(self, arr):
        self._outbuf = np.ascontiguousarray(arr)
        W, H = arr.shape[1], arr.shape[0]
        qimg = QImage(self._outbuf.data, W, H, 4 * W, QImage.Format_RGBA8888)
        return qimg.copy()
