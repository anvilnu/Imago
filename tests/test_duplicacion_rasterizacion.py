"""Regresiones al duplicar y rasterizar capas con mascara."""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QImage, QPainter, QUndoStack
from PySide6.QtWidgets import QApplication

from models.layer import Layer, LayerGroup, TextLayer
from models.layer_commands import DuplicateLayerCommand, RasterizeLayerCommand
from models.layer_effects import SuperposicionColor


_APP = QApplication.instance() or QApplication([])


def _pixeles(image):
    return tuple(
        image.pixelColor(x, y).rgba()
        for y in range(image.height())
        for x in range(image.width())
    )


def _mascara(width, height, value=128):
    mask = QImage(width, height, QImage.Format_Grayscale8)
    mask.fill(value)
    return mask


class _CanvasFalso:
    def __init__(self, layer, width, height):
        self.base_width = width
        self.base_height = height
        self.layers = [layer]
        self.active_layer_index = 0
        self.undo_stack = QUndoStack()
        self.notificaciones = 0

    def notify_layers_changed(self):
        self.notificaciones += 1


class DuplicacionRasterizacionTests(unittest.TestCase):
    def test_duplicar_clona_mascara_efectos_y_duracion_sin_alias(self):
        layer = Layer(4, 3, "Original")
        layer.image.fill(QColor("#123456"))
        layer.mask = _mascara(4, 3, 160)
        layer.effects = [SuperposicionColor("#abcdef", 45)]
        layer.frame_delay = 87
        layer.visible = False
        layer.opacity = 63
        layer.blend_mode = QPainter.CompositionMode.CompositionMode_Multiply
        layer.alpha_locked = True
        layer.pixels_locked = True
        layer.position_locked = True
        layer.clipped = True
        layer.group = LayerGroup("Grupo")
        canvas = _CanvasFalso(layer, 4, 3)

        canvas.undo_stack.push(DuplicateLayerCommand(canvas, 0))

        self.assertEqual(len(canvas.layers), 2)
        copy = canvas.layers[1]
        self.assertIsNot(copy, layer)
        self.assertEqual(_pixeles(copy.image), _pixeles(layer.image))
        self.assertEqual(_pixeles(copy.mask), _pixeles(layer.mask))
        self.assertIsNot(copy.mask, layer.mask)
        self.assertEqual(copy.effects[0].to_dict(), layer.effects[0].to_dict())
        self.assertIsNot(copy.effects[0], layer.effects[0])
        self.assertEqual(copy.frame_delay, 87)
        self.assertIs(copy.group, layer.group)
        self.assertFalse(copy.visible)
        self.assertEqual(copy.opacity, 63)
        self.assertEqual(copy.blend_mode, layer.blend_mode)
        self.assertTrue(copy.alpha_locked)
        self.assertTrue(copy.pixels_locked)
        self.assertTrue(copy.position_locked)
        self.assertTrue(copy.clipped)

        layer.image.fill(QColor("black"))
        layer.mask.fill(0)
        layer.effects[0].color = "#000000"
        self.assertEqual(copy.image.pixelColor(0, 0), QColor("#123456"))
        self.assertEqual(copy.mask.pixelColor(0, 0).red(), 160)
        self.assertEqual(copy.effects[0].color, "#abcdef")

        canvas.undo_stack.undo()
        self.assertEqual(canvas.layers, [layer])
        canvas.undo_stack.redo()
        self.assertIs(canvas.layers[1], copy)

    def test_duplicar_texto_conserva_todos_sus_parametros_y_metadatos(self):
        layer = TextLayer(60, 40, "Texto")
        layer.set_text(
            '<span style="font-size:18px; color:#ff0000">Imago</span>',
            QPointF(7.5, 9.0), angle=32.0, vertical=True, spacing=3,
            box_width=24)
        layer.mask = _mascara(60, 40, 210)
        layer.effects = [SuperposicionColor("#00ff00", 35)]
        layer.frame_delay = 120
        canvas = _CanvasFalso(layer, 60, 40)

        canvas.undo_stack.push(DuplicateLayerCommand(canvas, 0))

        copy = canvas.layers[1]
        self.assertIsInstance(copy, TextLayer)
        self.assertEqual(copy.text_html, layer.text_html)
        self.assertEqual(copy.text_origin, layer.text_origin)
        self.assertEqual(copy.text_angle, 32.0)
        self.assertTrue(copy.text_vertical)
        self.assertEqual(copy.text_spacing, 3)
        self.assertEqual(copy.text_box_width, 24)
        self.assertEqual(copy.frame_delay, 120)
        self.assertIsNot(copy.mask, layer.mask)
        self.assertIsNot(copy.effects[0], layer.effects[0])

    def test_rasterizar_texto_no_aplica_la_mascara_dos_veces(self):
        layer = TextLayer(64, 40, "Texto enmascarado")
        layer.set_text(
            '<span style="font-size:22px; color:#ff8040">Imago</span>',
            QPointF(3, 4))
        layer.mask = _mascara(64, 40, 128)
        layer.effects = [SuperposicionColor("#2040ff", 30)]
        layer.frame_delay = 95
        layer.group = LayerGroup("Grupo")
        base_before = _pixeles(layer.render_sin_mascara())
        visible_before = _pixeles(layer.render_image())
        self.assertNotEqual(base_before, visible_before)
        canvas = _CanvasFalso(layer, 64, 40)

        canvas.undo_stack.push(RasterizeLayerCommand(canvas, 0))

        raster = canvas.layers[0]
        self.assertIsInstance(raster, Layer)
        self.assertNotIsInstance(raster, TextLayer)
        self.assertEqual(_pixeles(raster.image), base_before)
        self.assertEqual(_pixeles(raster.render_image()), visible_before)
        self.assertEqual(raster.mask.format(), QImage.Format_Grayscale8)
        self.assertIsNot(raster.mask, layer.mask)
        self.assertIsNot(raster.effects[0], layer.effects[0])
        self.assertEqual(raster.effects[0].to_dict(), layer.effects[0].to_dict())
        self.assertEqual(raster.frame_delay, 95)
        self.assertIs(raster.group, layer.group)

        canvas.undo_stack.undo()
        self.assertIs(canvas.layers[0], layer)
        canvas.undo_stack.redo()
        self.assertIs(canvas.layers[0], raster)
        self.assertEqual(_pixeles(raster.render_image()), visible_before)


if __name__ == "__main__":
    unittest.main()
