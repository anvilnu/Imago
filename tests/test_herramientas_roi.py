"""Regresiones de buffers locales y coberturas dispersas de pincel."""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

from tools.airbrush_tool import AirbrushTool
from tools.clone_tool import CloneTool
from tools.dodge_burn_tool import DodgeBurnTool
from tools.draw_tools import PenTool, ReplaceColorTool
from tools.liquify_tool import LiquifyTool
from tools.roi_buffers import CoberturaDispersa, ImagenPremultiplicadaDispersa
from tools.smudge_tool import SmudgeTool
from tools.sponge_tool import SpongeTool
from widgets.canvas import Canvas


_APP = QApplication.instance() or QApplication([])


class _Evento:
    def __init__(self, x, y, boton=Qt.LeftButton, botones=Qt.LeftButton,
                 modificadores=Qt.NoModifier):
        self._pos = QPointF(x, y)
        self._boton = boton
        self._botones = botones
        self._modificadores = modificadores

    def position(self):
        return QPointF(self._pos)

    def button(self):
        return self._boton

    def buttons(self):
        return self._botones

    def modifiers(self):
        return self._modificadores


def _bytes_numpy_herramienta(herramienta):
    total = sum(valor.nbytes for valor in vars(herramienta).values()
                if isinstance(valor, np.ndarray))
    for valor in vars(herramienta).values():
        if isinstance(valor, (CoberturaDispersa,
                              ImagenPremultiplicadaDispersa)):
            total += valor.bytes_asignados
    return total


def _imagen_bicolor(ancho=64, alto=32, alpha=255):
    imagen = QImage(ancho, alto, QImage.Format_RGBA8888)
    imagen.fill(QColor(220, 30, 30, alpha))
    painter = QPainter(imagen)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
    painter.fillRect(ancho // 2, 0, ancho // 2, alto,
                     QColor(20, 40, 220, alpha))
    painter.end()
    return imagen


class CoberturaDispersaTests(unittest.TestCase):
    def test_teselas_solo_se_crean_donde_pasa_el_trazo(self):
        cobertura = CoberturaDispersa(4000, 5000)
        valores = np.full((20, 20), 0.6, dtype=np.float32)
        cobertura.maximo(250, 250, valores)  # cruza cuatro teselas

        self.assertEqual(
            cobertura.bytes_asignados,
            4 * cobertura.LADO_TESELA ** 2 * np.dtype(np.float32).itemsize)
        self.assertTrue(np.allclose(
            cobertura.region(250, 250, 270, 270), 0.6))
        self.assertFalse(cobertura.region(1000, 1000, 1010, 1010).any())

        cobertura.sumar_saturado(
            250, 250, np.full((20, 20), 0.7, dtype=np.float32))
        self.assertTrue(np.allclose(
            cobertura.region(250, 250, 270, 270), 1.0))


class HerramientasLocalesTests(unittest.TestCase):
    def test_pulsar_no_crea_arrays_proporcionales_al_documento(self):
        for clase in (SmudgeTool, LiquifyTool, SpongeTool, DodgeBurnTool):
            with self.subTest(herramienta=clase.__name__):
                canvas = Canvas(1024, 768)
                canvas.brush_size = 31
                herramienta = clase(canvas)
                herramienta.mouse_press(_Evento(500, 380))

                # Antes: entre 12 y 50 MiB de ndarray para esta imagen. Ahora
                # solo hay punta, carry y las pocas teselas cruzadas por ella.
                self.assertLess(_bytes_numpy_herramienta(herramienta), 3_000_000)

    def test_resultado_local_y_deshacer_se_conservan(self):
        casos = (
            (DodgeBurnTool, QColor(80, 80, 80, 255), (16, 16), (16, 16)),
            (SpongeTool, QColor(210, 60, 20, 255), (16, 16), (16, 16)),
        )
        for clase, color, inicio, fin in casos:
            with self.subTest(herramienta=clase.__name__):
                canvas = Canvas(32, 32)
                canvas.brush_size = 11
                canvas.layers[0].image.fill(color)
                antes = QImage(canvas.layers[0].image)
                herramienta = clase(canvas)
                herramienta.mouse_press(_Evento(*inicio))
                herramienta.mouse_release(_Evento(*fin, botones=Qt.NoButton))

                self.assertNotEqual(canvas.layers[0].image, antes)
                self.assertEqual(canvas.undo_stack.count(), 1)
                canvas.undo_stack.undo()
                self.assertEqual(canvas.layers[0].image, antes)

        for clase in (SmudgeTool, LiquifyTool):
            with self.subTest(herramienta=clase.__name__):
                canvas = Canvas(64, 32)
                canvas.brush_size = 13
                canvas.layers[0].image = _imagen_bicolor()
                antes = QImage(canvas.layers[0].image)
                herramienta = clase(canvas)
                herramienta.mouse_press(_Evento(24, 16))
                herramienta.mouse_move(_Evento(40, 16))
                herramienta.mouse_release(
                    _Evento(40, 16, botones=Qt.NoButton))

                self.assertNotEqual(canvas.layers[0].image, antes)
                self.assertEqual(canvas.undo_stack.count(), 1)
                canvas.undo_stack.undo()
                self.assertEqual(canvas.layers[0].image, antes)

    def test_seleccion_y_bloqueo_de_transparencia_siguen_aplicandose(self):
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QPainterPath

        canvas = Canvas(40, 20)
        canvas.brush_size = 9
        canvas.layers[0].image.fill(QColor(80, 80, 80, 120))
        canvas.layers[0].alpha_locked = True
        seleccion = QPainterPath()
        seleccion.addRect(QRectF(0, 0, 20, 20))
        canvas.selection = seleccion
        antes = QImage(canvas.layers[0].image)

        herramienta = DodgeBurnTool(canvas)
        herramienta.mouse_press(_Evento(30, 10))  # fuera de la selección
        herramienta.mouse_release(_Evento(30, 10, botones=Qt.NoButton))
        self.assertEqual(canvas.layers[0].image, antes)
        self.assertEqual(canvas.undo_stack.count(), 0)

        herramienta = DodgeBurnTool(canvas)
        herramienta.mouse_press(_Evento(10, 10))
        herramienta.mouse_release(_Evento(10, 10, botones=Qt.NoButton))
        self.assertEqual(canvas.layers[0].image.pixelColor(10, 10).alpha(), 120)

        for clase in (SmudgeTool, LiquifyTool):
            with self.subTest(bloqueo_alfa=clase.__name__):
                canvas = Canvas(64, 32)
                canvas.brush_size = 13
                canvas.layers[0].image = _imagen_bicolor(alpha=120)
                canvas.layers[0].alpha_locked = True
                herramienta = clase(canvas)
                herramienta.mouse_press(_Evento(24, 16))
                herramienta.mouse_move(_Evento(40, 16))
                herramienta.mouse_release(
                    _Evento(40, 16, botones=Qt.NoButton))
                self.assertEqual(
                    canvas.layers[0].image.pixelColor(36, 16).alpha(), 120)


class CoberturasPincelTests(unittest.TestCase):
    def test_pincel_aerografo_y_clonado_usan_cobertura_dispersa(self):
        canvas = Canvas(512, 512)
        canvas.brush_size = 21

        pincel = PenTool(canvas)
        pincel.mouse_press(_Evento(100, 100))
        self.assertIsInstance(pincel._coverage, CoberturaDispersa)
        self.assertLessEqual(pincel._coverage.bytes_asignados, 256 * 256 * 4)
        pincel.mouse_release(_Evento(100, 100, botones=Qt.NoButton))
        comando = canvas.undo_stack.command(0)
        self.assertLessEqual(comando.rect.width(), 23)
        self.assertLessEqual(comando.rect.height(), 23)

        sustituir = ReplaceColorTool(canvas)
        sustituir.mouse_press(_Evento(120, 120))
        self.assertIsInstance(sustituir._coverage, CoberturaDispersa)
        self.assertLessEqual(
            sustituir._coverage.bytes_asignados, 256 * 256 * 4)
        sustituir.mouse_release(_Evento(120, 120, botones=Qt.NoButton))

        aerografo = AirbrushTool(canvas)
        aerografo.mouse_press(_Evento(200, 200))
        aerografo._timer.stop()
        aerografo._deposit(QPointF(200, 200), 0.2)
        self.assertIsInstance(aerografo._density, CoberturaDispersa)
        self.assertLessEqual(aerografo._density.bytes_asignados, 256 * 256 * 4)
        aerografo.finish_editing()

        clonar = CloneTool(canvas)
        clonar.source_point = QPoint(50, 50)
        clonar._stroke_offset = QPoint(100, 100)
        clonar._begin_stroke()
        clonar._clone_stamp(QPoint(150, 150))
        self.assertIsInstance(clonar._coverage, CoberturaDispersa)
        self.assertLessEqual(clonar._coverage.bytes_asignados, 256 * 256 * 4)
        clonar.finish_editing()


if __name__ == "__main__":
    unittest.main()
