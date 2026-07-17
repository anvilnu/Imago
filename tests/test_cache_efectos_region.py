"""Regresiones de la cache regional de efectos de capa."""

import os
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QImage, QPainter, QUndoStack
from PySide6.QtWidgets import QApplication, QWidget

from models.layer import Layer
from models.layer_effects import (Bisel, Resplandor, Satinado, Sombra,
                                  SombraInterior, SuperposicionColor,
                                  SuperposicionDegradado, Trazo)
from widgets.layer_effects_ui import EfectosDialog


_APP = QApplication.instance() or QApplication([])


def _pintar_rect(layer, rect, color="#80c0ffff"):
    image = QImage(layer.image)
    painter = QPainter(image)
    painter.fillRect(rect, QColor(color))
    painter.end()
    layer.image = image


class _Marker:
    def __init__(self, canvas):
        self.canvas = canvas


class _Tabs:
    def __init__(self, canvas):
        self._marker = _Marker(canvas)

    def count(self):
        return 1

    def widget(self, _index):
        return self._marker


class _Canvas(QWidget):
    def __init__(self, layer):
        super().__init__()
        self.layers = [layer]
        self.active_layer_index = 0
        self.undo_stack = QUndoStack()
        self.updates = 0

    def get_active_layer(self):
        return self.layers[self.active_layer_index]

    def update(self):
        self.updates += 1


class _Window(QWidget):
    def __init__(self, canvas):
        super().__init__()
        self.canvas = canvas
        self.tabs = _Tabs(canvas)

    def get_current_canvas(self):
        return self.canvas


class CacheEfectosRegionTests(unittest.TestCase):
    def test_capa_dispersa_cachea_solo_contenido_y_halos(self):
        layer = Layer(1600, 1200, "Dispersa")
        _pintar_rect(layer, QRect(700, 520, 80, 60))
        layer.effects = [Sombra(dx=8, dy=6, radio=10),
                         Resplandor(radio=7), Trazo(grosor=4)]

        patch, posicion = layer.render_with_effects_patch()

        self.assertLess(patch.width(), 180)
        self.assertLess(patch.height(), 160)
        self.assertGreaterEqual(posicion.x(), 650)
        self.assertGreaterEqual(posicion.y(), 470)
        self.assertLess(patch.sizeInBytes(), layer.image.sizeInBytes() // 20)

        cache_key = patch.cacheKey()
        patch_again, posicion_again = layer.render_with_effects_patch()
        self.assertEqual(patch_again.cacheKey(), cache_key)
        self.assertEqual(posicion_again, posicion)

    def test_render_completo_conserva_posicion_y_transparencia(self):
        layer = Layer(120, 90, "Color")
        _pintar_rect(layer, QRect(40, 30, 20, 15), "#ff204060")
        layer.effects = [SuperposicionColor("#ff0000", 100)]

        full = layer.render_with_effects()

        self.assertEqual(full.size(), layer.image.size())
        self.assertEqual(full.pixelColor(0, 0).alpha(), 0)
        self.assertEqual(full.pixelColor(45, 35).red(), 255)
        self.assertGreater(full.pixelColor(45, 35).alpha(), 0)

    def test_cambio_de_pixeles_invalida_y_amplia_el_parche(self):
        layer = Layer(500, 300, "Variable")
        _pintar_rect(layer, QRect(20, 20, 30, 20))
        layer.effects = [Sombra(radio=4)]
        before, _ = layer.render_with_effects_patch()
        old_key = before.cacheKey()

        _pintar_rect(layer, QRect(430, 240, 20, 20))
        after, _ = layer.render_with_effects_patch()

        self.assertNotEqual(after.cacheKey(), old_key)
        self.assertGreater(after.width(), 400)

    def test_todos_los_efectos_se_componen_en_parche_acotado(self):
        layer = Layer(500, 400, "Todos")
        _pintar_rect(layer, QRect(210, 170, 60, 45))
        layer.effects = [Sombra(), Resplandor(), SuperposicionColor(), Trazo(),
                         SombraInterior(), SuperposicionDegradado(), Bisel(),
                         Satinado()]

        patch, posicion = layer.render_with_effects_patch()

        self.assertFalse(patch.isNull())
        self.assertLess(patch.width(), 180)
        self.assertLess(patch.height(), 170)
        self.assertGreaterEqual(posicion.x(), 0)
        self.assertGreaterEqual(posicion.y(), 0)

    def test_panel_agrupa_rafaga_de_slider_antes_de_invalidar(self):
        layer = Layer(120, 90, "Debounce")
        _pintar_rect(layer, QRect(30, 20, 40, 30))
        canvas = _Canvas(layer)
        window = _Window(canvas)
        panel = EfectosDialog(window, tipo="sombra")
        sentinel = QImage(2, 2, QImage.Format_ARGB32)
        layer._fx_cache = sentinel
        layer._fx_cache_key = ("sentinel",)

        control = panel._controls_by_type["sombra"]
        control._sliders["radio"].setValue(control.val("radio") + 1)

        self.assertIs(layer._fx_cache, sentinel)
        limite = time.monotonic() + 1.0
        while layer._fx_cache is sentinel and time.monotonic() < limite:
            _APP.processEvents()
            time.sleep(0.01)
        self.assertIsNone(layer._fx_cache)
        panel.reject()


if __name__ == "__main__":
    unittest.main()
