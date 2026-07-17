"""Regresiones de alineacion entre capas y mascaras al transformarlas."""

import unittest

from PySide6.QtGui import QColor, QImage, QUndoStack

from models.layer import Layer
from models.layer_commands import (
    CanvasResizeCommand,
    FlipCommand,
    FlipLayerCommand,
    ImageResizeCommand,
    RotateCommand,
    RotateLayerCommand,
)
from widgets.canvas import Canvas


def _pixeles(image):
    return tuple(
        image.pixelColor(x, y).rgba()
        for y in range(image.height())
        for x in range(image.width())
    )


def _estado(image):
    return image.width(), image.height(), image.format(), _pixeles(image)


def _crear_capa(width=3, height=2, con_mascara=True):
    layer = Layer(width, height, "Capa")
    layer.image.fill(0)
    layer.image.setPixelColor(0, 0, QColor("#ff0000"))
    layer.image.setPixelColor(width - 1, height - 1, QColor("#0000ff"))
    if con_mascara:
        layer.mask = QImage(width, height, QImage.Format_Grayscale8)
        layer.mask.fill(0)
        layer.mask.setPixelColor(0, 0, QColor(255, 255, 255))
        layer.mask.setPixelColor(width - 1, height - 1, QColor(96, 96, 96))
    return layer


class _CanvasFalso:
    def __init__(self, width=3, height=2, layers=None):
        self.base_width = width
        self.base_height = height
        self.dpi = 96.0
        self.zoom_factor = 1.0
        self.layers = layers or [_crear_capa(width, height)]
        self.active_layer_index = 0
        self.selection = None
        self.notificaciones_capas = 0
        self.notificaciones_seleccion = 0
        self.tamano_fijo = None
        self.undo_stack = QUndoStack()

    def setFixedSize(self, width, height):
        self.tamano_fijo = (width, height)

    def notify_layers_changed(self):
        self.notificaciones_capas += 1

    def notify_selection_changed(self):
        self.notificaciones_seleccion += 1


class TransformacionesMascaraTests(unittest.TestCase):
    def test_cambiar_lienzo_reubica_mascara_y_deshace_exactamente(self):
        canvas = _CanvasFalso()
        original_image = _estado(canvas.layers[0].image)
        original_mask = _estado(canvas.layers[0].mask)

        canvas.undo_stack.push(CanvasResizeCommand(
            canvas, 5, 4, 1, 1, fill_color=QColor("white")))

        layer = canvas.layers[0]
        self.assertEqual((canvas.base_width, canvas.base_height), (5, 4))
        self.assertEqual((layer.mask.width(), layer.mask.height()), (5, 4))
        self.assertEqual(layer.mask.format(), QImage.Format_Grayscale8)
        self.assertEqual(layer.mask.pixelColor(1, 1).red(), 255)
        self.assertEqual(layer.mask.pixelColor(0, 0).red(), 0)
        transformed_image = _estado(layer.image)
        transformed_mask = _estado(layer.mask)

        canvas.undo_stack.undo()
        self.assertEqual(_estado(layer.image), original_image)
        self.assertEqual(_estado(layer.mask), original_mask)
        canvas.undo_stack.redo()
        self.assertEqual(_estado(layer.image), transformed_image)
        self.assertEqual(_estado(layer.mask), transformed_mask)

    def test_cambiar_tamano_y_dpi_se_deshacen_exactamente(self):
        canvas = _CanvasFalso()
        original_image = _estado(canvas.layers[0].image)
        original_mask = _estado(canvas.layers[0].mask)

        canvas.undo_stack.push(ImageResizeCommand(
            canvas, 6, 4, new_dpi=300.0))

        layer = canvas.layers[0]
        self.assertEqual((canvas.base_width, canvas.base_height), (6, 4))
        self.assertEqual(canvas.dpi, 300.0)
        self.assertEqual((layer.mask.width(), layer.mask.height()), (6, 4))
        self.assertEqual(layer.mask.format(), QImage.Format_Grayscale8)
        self.assertEqual(layer.mask.pixelColor(0, 0).red(), 255)
        transformed_image = _estado(layer.image)
        transformed_mask = _estado(layer.mask)

        canvas.undo_stack.undo()
        self.assertEqual(canvas.dpi, 96.0)
        self.assertEqual(_estado(layer.image), original_image)
        self.assertEqual(_estado(layer.mask), original_mask)
        canvas.undo_stack.redo()
        self.assertEqual(canvas.dpi, 300.0)
        self.assertEqual(_estado(layer.image), transformed_image)
        self.assertEqual(_estado(layer.mask), transformed_mask)

    def test_cambiar_solo_dpi_crea_un_paso_sucio_sin_tocar_pixeles(self):
        canvas = _CanvasFalso()
        original_image = _estado(canvas.layers[0].image)
        original_mask = _estado(canvas.layers[0].mask)
        canvas.undo_stack.setClean()

        self.assertTrue(Canvas.resize_image(canvas, 3, 2, new_dpi=240.0))

        self.assertEqual(canvas.undo_stack.count(), 1)
        self.assertFalse(canvas.undo_stack.isClean())
        self.assertEqual(canvas.undo_stack.command(0).old_images, [])
        self.assertEqual(canvas.dpi, 240.0)
        self.assertEqual(_estado(canvas.layers[0].image), original_image)
        self.assertEqual(_estado(canvas.layers[0].mask), original_mask)
        self.assertIn("240", canvas.undo_stack.text(0))

        canvas.undo_stack.undo()
        self.assertTrue(canvas.undo_stack.isClean())
        self.assertEqual(canvas.dpi, 96.0)
        self.assertEqual(_estado(canvas.layers[0].image), original_image)
        canvas.undo_stack.redo()
        self.assertEqual(canvas.dpi, 240.0)

    def test_voltear_documento_mantiene_mascara_alineada(self):
        for horizontal, expected in ((True, (2, 0)), (False, (0, 1))):
            with self.subTest(horizontal=horizontal):
                layers = [_crear_capa(), _crear_capa(con_mascara=False)]
                canvas = _CanvasFalso(layers=layers)
                original_image = _estado(layers[0].image)
                original_mask = _estado(layers[0].mask)

                canvas.undo_stack.push(FlipCommand(canvas, horizontal))

                x, y = expected
                self.assertEqual(layers[0].image.pixelColor(x, y), QColor("#ff0000"))
                self.assertEqual(layers[0].mask.pixelColor(x, y).red(), 255)
                self.assertIsNone(layers[1].mask)
                canvas.undo_stack.undo()
                self.assertEqual(_estado(layers[0].image), original_image)
                self.assertEqual(_estado(layers[0].mask), original_mask)

    def test_girar_documento_mantiene_dimensiones_y_pixeles_de_mascara(self):
        cases = ((90, (2, 3), (1, 0)),
                 (-90, (2, 3), (0, 2)),
                 (180, (3, 2), (2, 1)))
        for degrees, size, expected in cases:
            with self.subTest(degrees=degrees):
                canvas = _CanvasFalso()
                layer = canvas.layers[0]
                original_image = _estado(layer.image)
                original_mask = _estado(layer.mask)

                canvas.undo_stack.push(RotateCommand(canvas, degrees))

                self.assertEqual((canvas.base_width, canvas.base_height), size)
                self.assertEqual((layer.mask.width(), layer.mask.height()), size)
                self.assertEqual(layer.mask.format(), QImage.Format_Grayscale8)
                x, y = expected
                self.assertEqual(layer.image.pixelColor(x, y), QColor("#ff0000"))
                self.assertEqual(layer.mask.pixelColor(x, y).red(), 255)
                transformed_image = _estado(layer.image)
                transformed_mask = _estado(layer.mask)

                canvas.undo_stack.undo()
                self.assertEqual(_estado(layer.image), original_image)
                self.assertEqual(_estado(layer.mask), original_mask)
                canvas.undo_stack.redo()
                self.assertEqual(_estado(layer.image), transformed_image)
                self.assertEqual(_estado(layer.mask), transformed_mask)

    def test_transformar_una_capa_es_un_solo_paso_para_imagen_y_mascara(self):
        canvas = _CanvasFalso(width=3, height=3,
                              layers=[_crear_capa(3, 3)])
        layer = canvas.layers[0]
        original_image = _estado(layer.image)
        original_mask = _estado(layer.mask)

        canvas.undo_stack.push(FlipLayerCommand(
            canvas, 0, True, "Voltear capa"))
        self.assertEqual(canvas.undo_stack.count(), 1)
        self.assertEqual(layer.image.pixelColor(2, 0), QColor("#ff0000"))
        self.assertEqual(layer.mask.pixelColor(2, 0).red(), 255)
        canvas.undo_stack.undo()
        self.assertEqual(_estado(layer.image), original_image)
        self.assertEqual(_estado(layer.mask), original_mask)

        canvas.undo_stack.clear()
        canvas.undo_stack.push(RotateLayerCommand(
            canvas, 0, 90, "Girar capa", "rotate_cw"))
        self.assertEqual(canvas.undo_stack.count(), 1)
        self.assertEqual(layer.image.pixelColor(2, 0), QColor("#ff0000"))
        self.assertEqual(layer.mask.pixelColor(2, 0).red(), 255)
        canvas.undo_stack.undo()
        self.assertEqual(_estado(layer.image), original_image)
        self.assertEqual(_estado(layer.mask), original_mask)


if __name__ == "__main__":
    unittest.main()
