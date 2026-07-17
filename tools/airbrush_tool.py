# tools/airbrush_tool.py
from i18n import t
import numpy as np
from PySide6.QtGui import QPainter, QImage
from PySide6.QtCore import Qt, QTimer, QLineF
from tools.base_tool import BaseTool
from tools.commands import PaintCommand
from tools.numpy_utils import SHAPES, get_kernel, qimage_to_bgra, bgra_to_qimage, recompose_alpha
from tools.roi_buffers import CoberturaDispersa



class AirbrushTool(BaseTool):
    """Aerógrafo con MOTOR DE DENSIDAD (numpy): mientras se mantiene pulsado,
    un temporizador deposita "pintura" a ritmo constante. La pintura se acumula
    en una cobertura dispersa por teselas (0..1) y la capa se recompone desde la imagen
    original como original-sobre-color·densidad. Ventajas frente al SourceOver
    repetido: acumulación suave y predecible, respeta forma de punta y selección,
    y -lo importante- la dosis de cada "tick" se REPARTE a lo largo del camino
    recorrido, así el trazo es continuo aunque muevas rápido (parado satura en el
    sitio, como un spray real).

    Opciones (barra): Tamaño (compartido con el pincel), Dureza, Flujo, Forma de
    punta y Textura (liso o moteado). Color primario (izq.) / secundario (der.).
    Toda una pulsación es UN único paso de deshacer."""

    INTERVAL_MS = 35      # frecuencia de los "soplidos" (~28 por segundo)
    SPECK_PROB = 0.8      # moteado: factor de probabilidad de partícula
    SPECK_AMOUNT = 1.0    # moteado: densidad que aporta cada partícula

    def __init__(self, canvas):
        super().__init__(canvas)
        self.tool_id = "airbrush"
        self._active = False
        self._pos = None            # posición actual del ratón
        self._deposit_pos = None    # última posición depositada
        self._color = canvas.brush_color
        self._before = None
        self._density = None
        self._kernel_cache = {}
        self._dirty_rect = None
        self._timer = QTimer(canvas)
        self._timer.setInterval(self.INTERVAL_MS)
        self._timer.timeout.connect(self._spray)

    # ------------------------------------------------------------- ratón
    def mouse_press(self, event):
        # 🎨 Alt+clic: cuentagotas temporal, no inicia el spray
        if self._alt_pick_color(event):
            return
        if event.button() not in (Qt.LeftButton, Qt.RightButton):
            return
        self._color = (self.canvas.brush_color if event.button() == Qt.LeftButton
                       else self.canvas.brush_color_secondary)
        self._pos = event.position() / self.canvas.zoom_factor
        self._deposit_pos = self._pos
        self._on_mask = self.canvas.paint_on_mask()   # 🎭 destino: máscara o píxeles
        layer = self.canvas.paint_target()
        self._before = QImage(layer)
        self._density = CoberturaDispersa(layer.width(), layer.height())
        self._kernel_cache = {}
        self._dirty_rect = None
        self._active = True
        self._timer.start()

    def mouse_move(self, event):
        if self._active:
            self._pos = event.position() / self.canvas.zoom_factor

    def mouse_release(self, event):
        self._commit()

    def finish_editing(self):
        # Si se cambia de herramienta con el ratón aún pulsado, cerramos limpio.
        self._commit()

    # --------------------------------------------------------- pintado
    def _commit(self):
        """Detiene el spray y empuja UN solo comando con todo el trazo."""
        self._timer.stop()
        if self._active:
            self._active = False
            after = QImage(self.canvas.paint_target())
            self.canvas.undo_stack.push(PaintCommand(
                self.canvas, self.canvas.active_layer_index, self._before, after,
                t("hist.airbrush"), tool_id="airbrush",
                target=("mask" if getattr(self, "_on_mask", False) else "image"),
                confine=True, dirty_rect=self._dirty_rect))
            self._before = None
            self._density = None
            self._kernel_cache = {}
            self._dirty_rect = None

    def _spray(self):
        """Un 'tick': reparte la dosis de este instante a lo largo del camino
        recorrido desde el tick anterior (trazo continuo). Parado, la dosis cae
        entera en el sitio y va saturando."""
        if not self._active or self._pos is None:
            return
        flow = getattr(self.canvas, 'airbrush_flow', 20)
        q_tick = max(0.005, flow / 100.0)     # densidad central por tick (parado)
        radius = max(0.6, self.canvas.brush_size / 2.0)
        step = max(1.0, radius * 0.5)

        line = QLineF(self._deposit_pos, self._pos)
        length = line.length()
        n = max(1, int(round(length / step)))
        dose = q_tick / n
        for i in range(n):
            t = (i + 1) / n
            pt = line.pointAt(t) if length > 1e-6 else self._pos
            self._deposit(pt, dose)
        self._deposit_pos = self._pos
        self.canvas.update()

    def _deposit(self, point, dose):
        """Acumula una dosis (kernel·dose, o partículas si 'moteado') en el buffer
        de densidad y recompone el rectángulo afectado."""
        radius = max(0.6, self.canvas.brush_size / 2.0)
        hardness = getattr(self.canvas, 'airbrush_hardness', 50)
        shape = getattr(self.canvas, 'airbrush_shape', 'round')
        if shape not in SHAPES:
            shape = 'round'
        ker = get_kernel(radius, hardness, shape)
        R = (ker.shape[0] - 1) // 2
        px, py = int(round(point.x())), int(round(point.y()))
        H, W = self._density.alto, self._density.ancho
        x0, y0 = px - R, py - R
        cx0, cy0 = max(0, x0), max(0, y0)
        cx1, cy1 = min(W, px + R + 1), min(H, py + R + 1)
        if cx1 <= cx0 or cy1 <= cy0:
            return
        ksub = ker[cy0 - y0:cy1 - y0, cx0 - x0:cx1 - x0]
        if getattr(self.canvas, 'airbrush_texture', 'smooth') == 'speckled':
            rnd = np.random.random(ksub.shape).astype(np.float32)
            add = np.where(rnd < ksub * dose * self.SPECK_PROB,
                           np.float32(self.SPECK_AMOUNT), np.float32(0.0))
        else:
            add = ksub * dose

        self._density.sumar_saturado(cx0, cy0, add)
        if self._dirty_rect is None:
            self._dirty_rect = [cx0, cy0, cx1, cy1]
        else:
            rect = self._dirty_rect
            rect[0] = min(rect[0], cx0); rect[1] = min(rect[1], cy0)
            rect[2] = max(rect[2], cx1); rect[3] = max(rect[3], cy1)
        self._recompose(cx0, cy0, cx1, cy1)

    def _recompose(self, x0, y0, x1, y1):
        """capa = original sobre color·densidad (SourceOver no premultiplicado,
        vectorizado), volcado con modo Source y respetando la selección."""
        w, h = x1 - x0, y1 - y0
        sub = self._before.copy(x0, y0, w, h).convertToFormat(QImage.Format.Format_ARGB32)
        o = qimage_to_bgra(sub).astype(np.float32)
        dens = self._density.region(x0, y0, x1, y1)

        # 🔒 Bloqueo de transparencia (SourceAtop a mano; el modo Source del
        # volcado pisa el de apply_selection_clip): densidad pesada por el alfa
        # original, que se conserva tal cual.
        if self.canvas.alpha_lock_active():
            dens = dens * (o[..., 3] / 255.0)
            out8 = recompose_alpha(o, dens, self._color)
            out8[..., 3] = o[..., 3].astype(np.uint8)
        else:
            out8 = recompose_alpha(o, dens, self._color)
        out_img = bgra_to_qimage(out8)

        layer = self.canvas.paint_target()
        painter = QPainter(layer)
        self.canvas.apply_selection_clip(painter)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.drawImage(x0, y0, out_img)
        painter.end()

    # Eliminadas funciones duplicadas (_kernel, _qimage_to_bgra, _bgra_to_qimage)
