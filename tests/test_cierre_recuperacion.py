"""Regresiones del cierre seguro de documentos recuperados."""

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QMessageBox

# Importar main.py instala el registrador de fallos y normalmente abre
# imago_crash.log. En pruebas lo redirigimos a NUL para no contaminar el
# diagnóstico real del usuario cada vez que se ejecuta la suite.
_open_real = open


def _open_sin_log_imago(file, *args, **kwargs):
    if os.path.basename(os.fspath(file)) == "imago_crash.log":
        return _open_real(os.devnull, *args, **kwargs)
    return _open_real(file, *args, **kwargs)


with patch("builtins.open", side_effect=_open_sin_log_imago):
    from main import MainWindow

from models.document_state import documento_pendiente
from ventana.menu_archivo import AccionesMenuArchivo, ResultadoGuardado


class _SignalFalsa:
    def disconnect(self):
        pass


class _PilaFalsa:
    def __init__(self, limpia=True):
        self.limpia = limpia
        self.indexChanged = _SignalFalsa()

    def isClean(self):
        return self.limpia


class _CanvasFalso:
    def __init__(self, limpio=True, recuperado=False):
        self.undo_stack = _PilaFalsa(limpio)
        self.recovered_dirty = recuperado


class _MarkerFalso:
    def __init__(self, canvas):
        self.canvas = canvas


class _TabsFalsas:
    def __init__(self, canvas):
        self.items = [_MarkerFalso(canvas)]
        self.current_index = 0

    def widget(self, index):
        return self.items[index] if 0 <= index < len(self.items) else None

    def setCurrentIndex(self, index):
        self.current_index = index

    def tabText(self, index):
        return "Recuperado.imago"

    def removeTab(self, index):
        self.items.pop(index)

    def count(self):
        return len(self.items)


class _AutoguardadoFalso:
    def __init__(self):
        self.detenido = False
        self.borrado = False

    def stop(self):
        self.detenido = True

    def clear(self):
        self.borrado = True


class _EventoFalso:
    def __init__(self):
        self.aceptado = False
        self.ignorado = False

    def accept(self):
        self.aceptado = True

    def ignore(self):
        self.ignorado = True


class _VentanaFalsa:
    def __init__(self, canvas, resultado=ResultadoGuardado.CANCELADO,
                 limpiar_al_guardar=False):
        self.tabs = _TabsFalsas(canvas)
        self.autosave = _AutoguardadoFalso()
        self.resultado = resultado
        self.limpiar_al_guardar = limpiar_al_guardar
        self.guardados = 0
        self.preferencias_guardadas = False

    def save_file(self):
        self.guardados += 1
        if self.limpiar_al_guardar:
            canvas = self.tabs.widget(self.tabs.current_index).canvas
            canvas.undo_stack.limpia = True
            canvas.recovered_dirty = False
        return self.resultado

    def _update_window_title(self):
        pass

    def save_preferences(self):
        self.preferencias_guardadas = True


class EstadoDocumentoTests(unittest.TestCase):
    def test_documento_pendiente_reune_historial_y_recuperacion(self):
        self.assertFalse(documento_pendiente(_CanvasFalso(True, False)))
        self.assertTrue(documento_pendiente(_CanvasFalso(False, False)))
        self.assertTrue(documento_pendiente(_CanvasFalso(True, True)))
        self.assertFalse(documento_pendiente(None))


class CierrePestanaTests(unittest.TestCase):
    def _cerrar(self, respuesta, resultado=ResultadoGuardado.CANCELADO,
                limpiar_al_guardar=False):
        canvas = _CanvasFalso(limpio=True, recuperado=True)
        ventana = _VentanaFalsa(canvas, resultado, limpiar_al_guardar)
        with patch("main.imago_warning", return_value=respuesta) as aviso:
            MainWindow.close_tab(ventana, 0)
        return ventana, aviso

    def test_cancelar_conserva_una_recuperacion_con_historial_limpio(self):
        ventana, aviso = self._cerrar(QMessageBox.Cancel)
        self.assertEqual(ventana.tabs.count(), 1)
        aviso.assert_called_once()

    def test_guardado_cancelado_o_fallido_conserva_la_pestana(self):
        for resultado in (ResultadoGuardado.CANCELADO, ResultadoGuardado.ERROR):
            with self.subTest(resultado=resultado):
                ventana, _ = self._cerrar(QMessageBox.Save, resultado)
                self.assertEqual(ventana.tabs.count(), 1)
                self.assertEqual(ventana.guardados, 1)

    def test_solo_un_guardado_confirmado_y_limpio_cierra(self):
        ventana, _ = self._cerrar(
            QMessageBox.Save, ResultadoGuardado.EXITO, limpiar_al_guardar=True)
        self.assertEqual(ventana.tabs.count(), 0)

    def test_exito_incorrecto_no_cierra_si_el_documento_sigue_pendiente(self):
        ventana, _ = self._cerrar(QMessageBox.Save, ResultadoGuardado.EXITO)
        self.assertEqual(ventana.tabs.count(), 1)

    def test_descartar_cierra_sin_guardar(self):
        ventana, _ = self._cerrar(QMessageBox.Discard)
        self.assertEqual(ventana.tabs.count(), 0)
        self.assertEqual(ventana.guardados, 0)


class CierreAplicacionTests(unittest.TestCase):
    def _cerrar(self, resultado, limpiar_al_guardar=False):
        canvas = _CanvasFalso(limpio=True, recuperado=True)
        ventana = _VentanaFalsa(canvas, resultado, limpiar_al_guardar)
        evento = _EventoFalso()
        with patch("main.imago_warning", return_value=QMessageBox.Save):
            MainWindow.closeEvent(ventana, evento)
        return ventana, evento

    def test_cancelar_o_fallar_guardado_no_borra_autoguardado(self):
        for resultado in (ResultadoGuardado.CANCELADO, ResultadoGuardado.ERROR):
            with self.subTest(resultado=resultado):
                ventana, evento = self._cerrar(resultado)
                self.assertTrue(evento.ignorado)
                self.assertFalse(evento.aceptado)
                self.assertFalse(ventana.autosave.borrado)
                self.assertFalse(ventana.autosave.detenido)

    def test_guardado_confirmado_permite_cerrar_y_limpiar_recuperacion(self):
        ventana, evento = self._cerrar(
            ResultadoGuardado.EXITO, limpiar_al_guardar=True)
        self.assertTrue(evento.aceptado)
        self.assertFalse(evento.ignorado)
        self.assertTrue(ventana.autosave.detenido)
        self.assertTrue(ventana.autosave.borrado)


class ResultadoGuardadoTests(unittest.TestCase):
    def test_guardar_propaga_el_resultado_de_cada_destino(self):
        class VentanaArchivoFalsa:
            def __init__(self, project_path=None, image_path=None):
                self.canvas = type("Canvas", (), {
                    "project_path": project_path,
                    "image_path": image_path,
                })()

            def get_current_canvas(self):
                return self.canvas

            def _save_project(self, canvas, path):
                return ResultadoGuardado.EXITO

            def _save_image(self, canvas, path):
                return ResultadoGuardado.ERROR

            def save_file_as(self):
                return ResultadoGuardado.CANCELADO

        proyecto = VentanaArchivoFalsa(project_path="doc.imago")
        imagen = VentanaArchivoFalsa(image_path="foto.png")
        nuevo = VentanaArchivoFalsa()
        self.assertIs(AccionesMenuArchivo.save_file(proyecto), ResultadoGuardado.EXITO)
        self.assertIs(AccionesMenuArchivo.save_file(imagen), ResultadoGuardado.ERROR)
        self.assertIs(AccionesMenuArchivo.save_file(nuevo), ResultadoGuardado.CANCELADO)


if __name__ == "__main__":
    unittest.main()
