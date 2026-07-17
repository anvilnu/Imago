"""Regresiones del recorte conocido de PaintCommand."""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

from tools.commands import PaintCommand, _diff_rect
from widgets.canvas import Canvas


_APP = QApplication.instance() or QApplication([])


def _imagen(ancho=40, alto=30, color=QColor(10, 20, 30, 255)):
    imagen = QImage(ancho, alto, QImage.Format_RGBA8888)
    imagen.fill(color)
    return imagen


class PaintCommandDirtyRectTests(unittest.TestCase):
    def test_diff_limitado_devuelve_el_mismo_rectangulo_global(self):
        antes = _imagen()
        despues = QImage(antes)
        painter = QPainter(despues)
        painter.fillRect(13, 9, 4, 3, QColor(200, 100, 50, 255))
        painter.end()

        esperado = QRect(13, 9, 4, 3)
        self.assertEqual(_diff_rect(antes, despues), esperado)
        self.assertEqual(
            _diff_rect(antes, despues, QRect(10, 7, 12, 9)), esperado)
        self.assertIsNone(
            _diff_rect(antes, despues, QRect(0, 0, 5, 5)))

    def test_dirty_rect_recorta_exactamente_y_deshace(self):
        canvas = Canvas(40, 30)
        antes = _imagen()
        despues = QImage(antes)
        despues.setPixelColor(15, 11, QColor(240, 10, 20, 255))
        canvas.layers[0].image = QImage(despues)

        comando = PaintCommand(
            canvas, 0, antes, despues, dirty_rect=(10, 8, 20, 18))
        self.assertEqual(comando.rect, QRect(15, 11, 1, 1))
        self.assertEqual(comando.old_image.size(), comando.rect.size())
        self.assertEqual(comando.new_image.size(), comando.rect.size())

        canvas.undo_stack.push(comando)
        canvas.undo_stack.undo()
        self.assertEqual(canvas.layers[0].image, antes)
        canvas.undo_stack.redo()
        self.assertEqual(canvas.layers[0].image, despues)

    def test_dirty_rect_vacio_no_ensucia_el_historial(self):
        canvas = Canvas(40, 30)
        imagen = _imagen()
        canvas.layers[0].image = QImage(imagen)

        comando = PaintCommand(
            canvas, 0, imagen, QImage(imagen), dirty_rect=None)
        self.assertTrue(comando.isObsolete())
        canvas.undo_stack.push(comando)
        self.assertEqual(canvas.undo_stack.count(), 0)
        self.assertEqual(canvas.revision_autoguardado, 0)

    def test_sin_dirty_rect_conserva_el_respaldo_automatico(self):
        canvas = Canvas(40, 30)
        antes = _imagen()
        despues = QImage(antes)
        despues.setPixelColor(37, 28, QColor(1, 2, 3, 255))

        comando = PaintCommand(canvas, 0, antes, despues)
        self.assertEqual(comando.rect, QRect(37, 28, 1, 1))
        self.assertFalse(comando.isObsolete())

    def test_calado_solo_materializa_el_parche_conocido(self):
        canvas = Canvas(40, 30)
        antes = _imagen()
        despues = QImage(antes)
        painter = QPainter(despues)
        painter.fillRect(12, 8, 6, 5, QColor(210, 110, 50, 255))
        painter.end()

        mascara = QImage(40, 30, QImage.Format_Grayscale8)
        mascara.fill(128)
        canvas.selection_soft = mascara
        llamadas = []
        confinar = canvas.confine_to_soft

        def registrar(before, after, offset=None):
            llamadas.append((before.size(), after.size(), QPoint(offset)))
            return confinar(before, after, offset)

        canvas.confine_to_soft = registrar
        comando = PaintCommand(
            canvas, 0, antes, despues, confine=True,
            dirty_rect=QRect(10, 6, 10, 10))

        self.assertEqual(len(llamadas), 1)
        self.assertEqual(llamadas[0][0].width(), 10)
        self.assertEqual(llamadas[0][0].height(), 10)
        self.assertEqual(llamadas[0][2], QPoint(10, 6))
        self.assertEqual(comando.rect, QRect(12, 8, 6, 5))
        self.assertEqual(comando.new_image.format(), antes.format())


if __name__ == "__main__":
    unittest.main()
