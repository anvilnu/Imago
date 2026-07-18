"""Regresiones del panel de diagnóstico bajo demanda."""

import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QImage, QUndoCommand
from PySide6.QtWidgets import QApplication, QMainWindow

from models.layer import Layer, LayerGroup
from models.layer_effects import Sombra, SuperposicionColor
from widgets.canvas import Canvas
from widgets.document_diagnostics import (DiagnosticoDocumentoDialog,
                                          DiagnosticoDocumentoWidget,
                                          analizar_documento)


_APP = QApplication.instance() or QApplication([])


class _MainFalso:
    def __init__(self, canvas):
        self.canvas = canvas

    def get_current_canvas(self):
        return self.canvas


class _VentanaFalsa(QMainWindow):
    def __init__(self, canvas):
        super().__init__()
        self.canvas = canvas

    def get_current_canvas(self):
        return self.canvas


class DiagnosticoDocumentoTests(unittest.TestCase):
    def test_analisis_lee_metadatos_sin_renderizar_ni_copiar_pixeles(self):
        canvas = Canvas(100, 50)
        capa = Layer(100, 50, "Segunda")
        capa.group = LayerGroup("Grupo")
        capa.mask = QImage(100, 50, QImage.Format_Grayscale8)
        capa.mask.fill(255)
        capa.effects = [Sombra(), SuperposicionColor()]
        canvas.layers.append(capa)
        canvas.undo_stack.push(QUndoCommand("Cambio"))

        with tempfile.TemporaryDirectory() as carpeta:
            ruta = os.path.join(carpeta, "documento.imago")
            with open(ruta, "wb") as archivo:
                archivo.write(b"x" * 1234)
            canvas.project_path = ruta
            with patch.object(
                    Layer, "render_with_effects",
                    side_effect=AssertionError("No debe renderizar")):
                diagnostico = analizar_documento(canvas)

        self.assertEqual((diagnostico.ancho, diagnostico.alto), (100, 50))
        self.assertEqual(diagnostico.capas, 2)
        self.assertEqual(diagnostico.capas_visibles, 2)
        self.assertEqual(diagnostico.mascaras, 1)
        self.assertEqual(diagnostico.grupos, 1)
        self.assertEqual(diagnostico.efectos_activos, 2)
        self.assertEqual(diagnostico.efectos_costosos, (("sombra", 1),))
        self.assertEqual(diagnostico.archivo_bytes, 1234)
        self.assertTrue(diagnostico.archivo_desactualizado)
        minimo = sum(c.image.sizeInBytes() for c in canvas.layers)
        minimo += capa.mask.sizeInBytes()
        self.assertGreaterEqual(diagnostico.memoria_bytes, minimo)

    def test_memoria_deduplica_pero_proyecto_cuenta_cada_capa(self):
        canvas = Canvas(80, 40)
        compartida = QImage(canvas.layers[0].image)
        segunda = Layer(80, 40, "Compartida")
        segunda.image = compartida
        canvas.layers.append(segunda)

        diagnostico = analizar_documento(canvas)
        tamano = canvas.layers[0].image.sizeInBytes()
        self.assertEqual(diagnostico.memoria_bytes, tamano)
        self.assertEqual(diagnostico.proyecto_bruto_bytes,
                         2 * tamano + 1024 + 2 * 512)

    def test_contenido_oculto_no_sondea_y_visible_solo_marca_cambios(self):
        canvas = Canvas(30, 20)
        panel = DiagnosticoDocumentoWidget(_MainFalso(canvas))
        self.addCleanup(panel.deleteLater)
        self.assertEqual(panel.findChildren(QTimer), [])

        with patch("widgets.document_diagnostics.analizar_documento",
                   wraps=analizar_documento) as analizar:
            canvas.undo_stack.push(QUndoCommand("Oculto"))
            _APP.processEvents()
            analizar.assert_not_called()

            panel.show()
            _APP.processEvents()
            self.assertEqual(analizar.call_count, 1)
            analizar.reset_mock()

            canvas.undo_stack.push(QUndoCommand("Visible"))
            _APP.processEvents()
            analizar.assert_not_called()
            self.assertTrue(panel._pendiente)

            panel._actualizar_btn.click()
            self.assertEqual(analizar.call_count, 1)
            self.assertFalse(panel._pendiente)
        panel.hide()

    def test_dialogo_es_una_ventana_independiente_sin_temporizadores(self):
        principal = _VentanaFalsa(Canvas(40, 30))
        dialogo = DiagnosticoDocumentoDialog(principal)
        self.addCleanup(principal.deleteLater)

        principal.show()
        _APP.processEvents()
        minimo_antes = principal.minimumSizeHint()
        dialogo.show()
        _APP.processEvents()

        self.assertTrue(dialogo.isWindow())
        self.assertTrue(dialogo.windowFlags() & Qt.WindowType.Dialog)
        self.assertFalse(dialogo.isModal())
        self.assertEqual(dialogo.findChildren(QTimer), [])
        self.assertEqual(dialogo._body.size().width(), 460)
        self.assertEqual(principal.minimumSizeHint(), minimo_antes)
        dialogo.close()
        _APP.processEvents()


if __name__ == "__main__":
    unittest.main()
