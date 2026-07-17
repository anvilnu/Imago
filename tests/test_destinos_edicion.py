"""Regresiones de identidad para IA y overlays con trabajo diferido."""

import os
import threading
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QImage, QPainterPath, QUndoStack
from PySide6.QtWidgets import QApplication, QWidget

from adjustments import AdjustmentDialog
from models.destino_edicion import DestinoCapa, DestinoDocumento
from models.layer import Layer
from ventana.menu_edicion import AccionesMenuEdicion
from ventana.menu_ia import AccionesMenuIA


_APP = QApplication.instance() or QApplication([])


class _Marker:
    def __init__(self, canvas):
        self.canvas = canvas


class _Tabs:
    def __init__(self, canvases):
        self.markers = [_Marker(canvas) for canvas in canvases]

    def count(self):
        return len(self.markers)

    def widget(self, index):
        return self.markers[index]


class _Status:
    def __init__(self):
        self.messages = []

    def showMessage(self, text, timeout=0):
        self.messages.append((text, timeout))


class _Canvas(QWidget):
    def __init__(self, layers):
        super().__init__()
        self.layers = layers
        self.active_layer_index = 0
        self.base_width = layers[0].image.width()
        self.base_height = layers[0].image.height()
        self.selection = None
        self.undo_stack = QUndoStack()
        self.updates = 0

    def get_active_layer(self):
        if 0 <= self.active_layer_index < len(self.layers):
            return self.layers[self.active_layer_index].image
        return None

    def composite_selection_result(self, before, result, offset=(0, 0)):
        return QImage(result)

    def update(self):
        self.updates += 1


class _Ventana(QWidget):
    def __init__(self, canvases):
        super().__init__()
        self.tabs = _Tabs(canvases)
        self.current_canvas = canvases[0] if canvases else None
        self.status_bar = _Status()

    def get_current_canvas(self):
        return self.current_canvas


class _AjustePrueba(AdjustmentDialog):
    title = "Ajuste de prueba"

    def build_controls(self):
        pass

    def compute(self, arr):
        out = arr.copy()
        out[..., 0] = 255 - out[..., 0]
        return out


_HILOS_AJUSTE_PESADO = []


class _AjustePesadoPrueba(AdjustmentDialog):
    title = "Ajuste pesado de prueba"
    heavy = True

    def build_controls(self):
        self.add_slider_row("cantidad", "Cantidad", 0, 255, 25)

    def compute(self, arr):
        _HILOS_AJUSTE_PESADO.append(threading.get_ident())
        time.sleep(0.08)
        out = arr.copy()
        out[..., 0] = np.clip(
            out[..., 0].astype(np.int16) + self.val("cantidad"), 0, 255)
        return out.astype(np.uint8)


class _VentanaIA(AccionesMenuIA):
    def __init__(self, canvases):
        self.tabs = _Tabs(canvases)
        self.current_canvas = canvases[0]
        self.statuses = []
        self._ai_active_icon = None
        self.busy_states = []

    def get_current_canvas(self):
        return self.current_canvas

    def _ai_status(self, text, timeout=0):
        self.statuses.append((text, timeout))

    def _ai_set_busy(self, busy):
        self.busy_states.append(busy)


class _VentanaRefinado(QWidget, AccionesMenuEdicion):
    def __init__(self, canvases):
        super().__init__()
        self.tabs = _Tabs(canvases)
        self.current_canvas = canvases[0]
        self.status_bar = _Status()
        self.panel = None

    def get_current_canvas(self):
        return self.current_canvas

    def _open_ai_overlay(self, panel):
        self.panel = panel


class _Handle:
    def __init__(self):
        self.cancelled = False

    def cancel(self):
        self.cancelled = True


def _layer(color):
    layer = Layer(3, 2, "Capa")
    layer.image.fill(QColor(color))
    return layer


class DestinosEdicionTests(unittest.TestCase):
    @staticmethod
    def _procesar_hasta(predicate, timeout=3.0):
        limite = time.monotonic() + timeout
        while not predicate() and time.monotonic() < limite:
            _APP.processEvents()
            time.sleep(0.005)
        _APP.processEvents()
        return predicate()

    def test_destino_capa_sigue_al_objeto_reordenado(self):
        target = _layer("#102030")
        other = _layer("#405060")
        canvas = _Canvas([target, other])
        window = _Ventana([canvas])
        destino = DestinoCapa(canvas, 0)

        canvas.layers[:] = [other, target]

        self.assertEqual(destino.indice_actual(window, exigir_activo=True), 1)
        target.image.fill(QColor("#abcdef"))
        self.assertIsNone(destino.indice_actual(window, exigir_activo=True))

    def test_destino_rechaza_capa_reemplazada_pestana_distinta_y_cierre(self):
        target = _layer("#102030")
        canvas = _Canvas([target])
        other_canvas = _Canvas([_layer("#ffffff")])
        window = _Ventana([canvas, other_canvas])
        destino = DestinoCapa(canvas, 0)

        window.current_canvas = other_canvas
        self.assertIsNone(destino.indice_actual(window, exigir_activo=True))
        self.assertEqual(destino.indice_actual(window, exigir_activo=False), 0)
        canvas.layers[0] = _layer("#102030")
        self.assertIsNone(destino.indice_actual(window, exigir_revision=False))
        window.tabs.markers = [_Marker(other_canvas)]
        self.assertIsNone(destino.indice_actual(window, exigir_revision=False))

    def test_revision_documento_detecta_edicion_y_reordenacion(self):
        first = _layer("#102030")
        second = _layer("#405060")
        canvas = _Canvas([first, second])
        window = _Ventana([canvas])
        destino = DestinoDocumento(canvas)

        self.assertTrue(destino.vigente(window, exigir_activo=True))
        canvas.layers.reverse()
        self.assertFalse(destino.vigente(window, exigir_activo=True))
        canvas.layers.reverse()
        self.assertTrue(destino.vigente(window, exigir_activo=True))
        first.image.fill(QColor("#abcdef"))
        self.assertFalse(destino.vigente(window, exigir_activo=True))

    def test_overlay_confirma_sobre_la_capa_capturada_tras_reordenar(self):
        target = _layer("#102030")
        other = _layer("#405060")
        canvas = _Canvas([target, other])
        window = _Ventana([canvas])
        before = QImage(target.image)
        other_before = QImage(other.image)
        panel = _AjustePrueba(window)

        canvas.layers[:] = [other, target]
        canvas.active_layer_index = 0
        panel.accept()

        self.assertEqual(canvas.undo_stack.count(), 1)
        self.assertNotEqual(target.image, before)
        self.assertEqual(other.image, other_before)
        canvas.undo_stack.undo()
        self.assertEqual(target.image, before)

    def test_overlay_no_restaura_encima_de_una_edicion_externa(self):
        target = _layer("#102030")
        canvas = _Canvas([target])
        window = _Ventana([canvas])
        panel = _AjustePrueba(window)
        external = QImage(3, 2, QImage.Format_ARGB32)
        external.fill(QColor("#abcdef"))
        target.image = external

        panel.reject()

        self.assertEqual(target.image, external)
        self.assertEqual(canvas.undo_stack.count(), 0)

    def test_overlay_pesado_confirma_en_worker_y_mantiene_qt_responsivo(self):
        _HILOS_AJUSTE_PESADO.clear()
        target = _layer("#102030")
        canvas = _Canvas([target])
        window = _Ventana([canvas])
        panel = _AjustePesadoPrueba(window)
        hilo_gui = threading.get_ident()
        pulso_qt = []
        QTimer.singleShot(10, lambda: pulso_qt.append(True))

        panel.accept()

        self.assertIsNotNone(panel._final_handle)
        self.assertTrue(self._procesar_hasta(lambda: canvas.undo_stack.count() == 1))
        self.assertTrue(pulso_qt)
        self.assertTrue(any(hilo != hilo_gui for hilo in _HILOS_AJUSTE_PESADO))
        self.assertEqual(canvas.undo_stack.count(), 1)

    def test_overlay_pesado_descarta_resultado_si_cambia_la_capa(self):
        target = _layer("#102030")
        canvas = _Canvas([target])
        window = _Ventana([canvas])
        panel = _AjustePesadoPrueba(window)
        panel.accept()
        external = QImage(3, 2, QImage.Format_ARGB32)
        external.fill(QColor("#abcdef"))
        target.image = external

        self.assertTrue(self._procesar_hasta(lambda: panel._final_handle is None))
        self.assertEqual(target.image, external)
        self.assertEqual(canvas.undo_stack.count(), 0)
        self.assertTrue(window.status_bar.messages)

    def test_commit_ia_usa_indice_actual_y_descarta_revision_obsoleta(self):
        target = _layer("#102030")
        other = _layer("#405060")
        canvas = _Canvas([target, other])
        window = _VentanaIA([canvas])
        destino = DestinoCapa(canvas, 0)
        old_image = QImage(target.image)
        rgba = np.zeros((2, 3, 4), dtype=np.uint8)
        rgba[..., 0] = 220
        rgba[..., 3] = 255
        canvas.layers[:] = [other, target]

        applied = window._ai_commit_pixels(
            destino, rgba, old_image, "hist.colorize")

        self.assertTrue(applied)
        self.assertEqual(canvas.undo_stack.count(), 1)
        self.assertEqual(target.image.pixelColor(0, 0).red(), 220)
        self.assertEqual(other.image.pixelColor(0, 0), QColor("#405060"))

        stale = DestinoCapa(canvas, 1)
        stale_before = QImage(target.image)
        target.image.fill(QColor("#ffffff"))
        applied = window._ai_commit_pixels(
            stale, rgba, stale_before, "hist.colorize")
        self.assertFalse(applied)
        self.assertEqual(canvas.undo_stack.count(), 1)

    def test_cerrar_documento_cancela_solo_su_trabajo_de_ia(self):
        canvas = _Canvas([_layer("#102030")])
        other = _Canvas([_layer("#405060")])
        window = _VentanaIA([canvas, other])
        handle = _Handle()
        window._ai_handle = handle
        window._ai_target_canvas = canvas

        window._ai_cancel_for_canvas(other)
        self.assertFalse(handle.cancelled)
        window._ai_cancel_for_canvas(canvas)

        self.assertTrue(handle.cancelled)
        self.assertIsNone(window._ai_handle)
        self.assertIsNone(window._ai_target_canvas)
        self.assertEqual(window.busy_states, [False])

    def test_refinado_no_salta_a_otro_lienzo_ni_a_otra_seleccion(self):
        canvas = _Canvas([_layer("#102030")])
        other = _Canvas([_layer("#405060")])
        path = QPainterPath()
        path.addRect(0, 0, 2, 2)
        canvas.selection = path
        other.selection = QPainterPath(path)
        canvas.calls = []
        other.calls = []
        canvas.expand_selection = lambda *args: canvas.calls.append(args)
        other.expand_selection = lambda *args: other.calls.append(args)
        window = _VentanaRefinado([canvas, other])

        window._refine_selection(
            "expand_selection", "Expandir", "Cantidad", show_direction=True)
        self.assertIs(window.panel.canvas, canvas)
        window.current_canvas = other
        window.panel.accept()

        self.assertEqual(canvas.calls, [])
        self.assertEqual(other.calls, [])
        self.assertTrue(window.status_bar.messages)

        window.current_canvas = canvas
        window._refine_selection(
            "expand_selection", "Expandir", "Cantidad", show_direction=True)
        canvas.selection.addRect(2, 0, 1, 1)
        window.panel.accept()

        self.assertEqual(canvas.calls, [])


if __name__ == "__main__":
    unittest.main()
