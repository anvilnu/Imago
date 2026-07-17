"""Regresiones de equivalencia visual al fusionar una capa hacia abajo."""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter, QUndoStack
from PySide6.QtWidgets import QApplication

from models.layer import (Layer, LayerGroup, base_de_recorte, render_recortada,
                          visible_efectiva, visible_para_fusion)
from models.layer_commands import MergeDownCommand
from models.layer_effects import SuperposicionColor
from widgets.canvas import Canvas


_APP = QApplication.instance() or QApplication([])


def _componer(layers, width, height):
    """Compositor de referencia equivalente al del lienzo."""
    image = QImage(width, height, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    for idx, layer in enumerate(layers):
        if not visible_efectiva(layer):
            continue
        base = base_de_recorte(layers, idx)
        if (getattr(layer, "clipped", False) and base is not None
                and not visible_efectiva(base)):
            continue
        painter.setOpacity(layer.opacity / 100.0)
        painter.setCompositionMode(layer.blend_mode)
        painter.drawImage(0, 0, render_recortada(layer, base))
    painter.end()
    return image.convertToFormat(QImage.Format_ARGB32)


def _pixeles(image):
    return tuple(image.pixelColor(x, y).rgba()
                 for y in range(image.height())
                 for x in range(image.width()))


def _capa(width, height, color, name):
    layer = Layer(width, height, name)
    layer.image.fill(QColor(color))
    return layer


class _CanvasFalso:
    def __init__(self, layers, width=3, height=2):
        self.base_width = width
        self.base_height = height
        self.layers = layers
        self.active_layer_index = len(layers) - 1
        self.selected_layer_indices = [self.active_layer_index]
        self.undo_stack = QUndoStack()
        self.notificaciones = 0

    def notify_layers_changed(self):
        self.notificaciones += 1


class FusionarHaciaAbajoTests(unittest.TestCase):
    def test_opacidad_inferior_no_se_aplica_dos_veces(self):
        bottom = _capa(2, 1, "#ff0000", "Inferior")
        bottom.opacity = 50
        top = _capa(2, 1, "#00000000", "Superior")
        top.image.setPixelColor(0, 0, QColor("#0000ff"))
        canvas = _CanvasFalso([bottom, top], 2, 1)
        before = _pixeles(_componer(canvas.layers, 2, 1))

        canvas.undo_stack.push(MergeDownCommand(canvas, 1))

        merged = canvas.layers[0]
        self.assertEqual(_pixeles(_componer(canvas.layers, 2, 1)), before)
        self.assertEqual(merged.image.pixelColor(0, 0).alpha(), 255)
        self.assertEqual(merged.opacity, 100)
        self.assertEqual(
            merged.blend_mode,
            QPainter.CompositionMode.CompositionMode_SourceOver)

    def test_hornea_mascara_efectos_y_modo_de_fusion_una_sola_vez(self):
        bottom = _capa(3, 2, "#80c040", "Inferior")
        bottom.opacity = 70
        bottom.mask = QImage(3, 2, QImage.Format_Grayscale8)
        bottom.mask.fill(180)
        bottom.effects = [SuperposicionColor("#2040ff", 35)]
        top = _capa(3, 2, "#d06080", "Superior")
        top.opacity = 60
        top.blend_mode = QPainter.CompositionMode.CompositionMode_Multiply
        top.effects = [SuperposicionColor("#ffff00", 25)]
        canvas = _CanvasFalso([bottom, top])
        before = _pixeles(_componer(canvas.layers, 3, 2))

        canvas.undo_stack.push(MergeDownCommand(canvas, 1))

        merged = canvas.layers[0]
        self.assertEqual(_pixeles(_componer(canvas.layers, 3, 2)), before)
        self.assertIsNone(merged.mask)
        self.assertEqual(merged.effects, [])
        self.assertEqual(merged.opacity, 100)
        self.assertEqual(
            merged.blend_mode,
            QPainter.CompositionMode.CompositionMode_SourceOver)

    def test_hornea_el_recorte_sin_recortar_la_parte_superior(self):
        base = _capa(3, 1, "#00000000", "Base de recorte")
        base.image.setPixelColor(0, 0, QColor("#ffffff"))
        bottom = _capa(3, 1, "#ff0000", "Inferior recortada")
        bottom.clipped = True
        top = _capa(3, 1, "#0000ff", "Superior libre")
        canvas = _CanvasFalso([base, bottom, top], 3, 1)
        before = _pixeles(_componer(canvas.layers, 3, 1))

        canvas.undo_stack.push(MergeDownCommand(canvas, 2))

        merged = canvas.layers[1]
        self.assertEqual(_pixeles(_componer(canvas.layers, 3, 1)), before)
        self.assertFalse(merged.clipped)
        self.assertEqual(merged.image.pixelColor(2, 0), QColor("#0000ff"))

    def test_grupos_visibilidad_y_deshacer_reponen_el_estado_completo(self):
        group = LayerGroup("Grupo")
        bottom = _capa(2, 1, "#40a060", "Inferior")
        bottom.group = group
        bottom.opacity = 45
        bottom.blend_mode = QPainter.CompositionMode.CompositionMode_Screen
        bottom.clipped = True
        bottom.mask = QImage(2, 1, QImage.Format_Grayscale8)
        bottom.mask.fill(144)
        bottom.effects = [SuperposicionColor("#ff8000", 30)]
        top = _capa(2, 1, "#6040c0", "Superior")
        top.group = group
        canvas = _CanvasFalso([bottom, top], 2, 1)
        canvas.selected_layer_indices = [0, 1]
        original = _pixeles(_componer(canvas.layers, 2, 1))

        canvas.undo_stack.push(MergeDownCommand(canvas, 1))
        merged_pixels = _pixeles(canvas.layers[0].image)
        self.assertIs(canvas.layers[0].group, group)
        self.assertEqual(canvas.selected_layer_indices, [0])

        canvas.undo_stack.undo()
        self.assertEqual(canvas.layers, [bottom, top])
        self.assertEqual(_pixeles(_componer(canvas.layers, 2, 1)), original)
        self.assertEqual(bottom.opacity, 45)
        self.assertEqual(
            bottom.blend_mode,
            QPainter.CompositionMode.CompositionMode_Screen)
        self.assertTrue(bottom.clipped)
        self.assertIsNotNone(bottom.mask)
        self.assertEqual(len(bottom.effects), 1)
        self.assertEqual(canvas.selected_layer_indices, [0, 1])

        canvas.undo_stack.redo()
        self.assertEqual(_pixeles(canvas.layers[0].image), merged_pixels)

        canvas.undo_stack.undo()
        group.visible = False
        self.assertFalse(visible_para_fusion(canvas.layers, 0))
        self.assertFalse(visible_para_fusion(canvas.layers, 1))
        self.assertFalse(Canvas.merge_layer_down(canvas))
        self.assertEqual(canvas.undo_stack.count(), 1)


if __name__ == "__main__":
    unittest.main()
