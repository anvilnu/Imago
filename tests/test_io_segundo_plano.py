"""Regresiones de instantáneas y E/S pesada fuera del hilo de interfaz."""

import os
import tempfile
import threading
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, QEventLoop, QTimer
from PySide6.QtGui import QColor, QUndoCommand
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow

from i18n import t
from models.autosave import AutoSaveManager
from models.project_io import (crear_instantanea_proyecto, load_project,
                               save_project)
from ai.runner import CancelToken
from ventana.menu_archivo import AccionesMenuArchivo
from ventana.menu_ver import AccionesMenuVer
from widgets.canvas import Canvas


_APP = QApplication.instance() or QApplication([])


def _esperar(condicion, timeout_ms=3000):
    bucle = QEventLoop()
    temporizador = QTimer()
    temporizador.setInterval(5)
    temporizador.timeout.connect(
        lambda: bucle.quit() if condicion() else None)
    limite = QTimer()
    limite.setSingleShot(True)
    limite.timeout.connect(bucle.quit)
    temporizador.start()
    limite.start(timeout_ms)
    bucle.exec()
    temporizador.stop()
    return condicion()


class _VentanaIO(AccionesMenuArchivo, QMainWindow):
    pass


class _Tabs:
    def __init__(self, canvas):
        self.canvas = canvas

    def count(self):
        return 1

    def widget(self, indice):
        del indice
        return type("Marker", (), {"canvas": self.canvas})()

    def tabText(self, indice):
        del indice
        return "Documento"


class _MainAutosave(QObject):
    def __init__(self, canvas):
        super().__init__()
        self.tabs = _Tabs(canvas)
        self.estados_autoguardado = []

    def actualizar_estado_autoguardado(self, estado, hora=None):
        self.estados_autoguardado.append((estado, hora))


class _EstadoAutoguardado(AccionesMenuVer):
    def __init__(self):
        self.status_autosave_value = QLabel()


class IOSegundoPlanoTests(unittest.TestCase):
    def test_indicador_conserva_el_error_hasta_un_exito_confirmado(self):
        estado = _EstadoAutoguardado()
        self.addCleanup(estado.status_autosave_value.deleteLater)

        estado.actualizar_estado_autoguardado("error")
        QApplication.processEvents()
        self.assertEqual(estado.status_autosave_value.text(),
                         t("status.autosave.error"))

        estado.actualizar_estado_autoguardado("guardado", "12:34:56")
        self.assertEqual(estado.status_autosave_value.text(),
                         t("status.autosave.saved", time="12:34:56"))

    def test_instantanea_no_cambia_si_se_edita_el_lienzo(self):
        canvas = Canvas(5, 4)
        capa = canvas.layers[0]
        capa.image.fill(QColor("#cc2211"))
        instantanea = crear_instantanea_proyecto(canvas)

        capa.image.fill(QColor("#1144cc"))
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = os.path.join(carpeta, "captura.imago")
            self.assertTrue(save_project(instantanea, ruta))
            datos = load_project(ruta)

        self.assertEqual(datos["layers"][0].image.pixelColor(0, 0),
                         QColor("#cc2211"))

    def test_el_worker_no_bloquea_el_bucle_qt(self):
        ventana = _VentanaIO()
        self.addCleanup(ventana.deleteLater)
        hilo_gui = threading.get_ident()
        liberar = threading.Event()
        timer_atendido = []

        def atender_timer():
            timer_atendido.append(True)
            liberar.set()

        QTimer.singleShot(20, atender_timer)

        def trabajo(report, token):
            del token
            report(50)
            liberar.wait(1)
            return threading.get_ident()

        completado, hilo_worker = ventana._ejecutar_trabajo_io(
            trabajo, "Probando E/S")
        self.assertTrue(completado)
        self.assertTrue(timer_atendido)
        self.assertNotEqual(hilo_worker, hilo_gui)

    def test_cancelar_no_publica_sobre_el_archivo_anterior(self):
        canvas = Canvas(5, 4)
        instantanea = crear_instantanea_proyecto(canvas)
        token = CancelToken()
        token.cancel()
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = os.path.join(carpeta, "documento.imago")
            with open(ruta, "wb") as archivo:
                archivo.write(b"VERSION ANTERIOR")
            self.assertFalse(save_project(instantanea, ruta, token=token))
            with open(ruta, "rb") as archivo:
                self.assertEqual(archivo.read(), b"VERSION ANTERIOR")

    def test_autoguardado_comprime_en_worker_y_confirma_revision(self):
        canvas = Canvas(6, 4)
        canvas.undo_stack.push(QUndoCommand("Cambio"))
        main = _MainAutosave(canvas)
        self.addCleanup(main.deleteLater)
        hilo_gui = threading.get_ident()
        hilos_guardado = []

        with tempfile.TemporaryDirectory() as carpeta, \
                patch("models.autosave.app_paths.base_datos", return_value=carpeta):
            manager = AutoSaveManager(main, interval_min=60)
            self.addCleanup(manager.stop)
            self.assertIs(manager._runner, main._io_runner)
            original = save_project

            def guardar(snapshot, ruta, report=None, token=None):
                hilos_guardado.append(threading.get_ident())
                return original(snapshot, ruta, report=report, token=token)

            with patch("models.autosave.save_project", side_effect=guardar):
                manager.snapshot()
                self.assertIsNotNone(manager._handle)
                self.assertTrue(_esperar(lambda: manager._handle is None))

            self.assertTrue(hilos_guardado)
            self.assertTrue(all(hilo != hilo_gui for hilo in hilos_guardado))
            self.assertEqual(canvas._autosave_revision,
                             canvas.revision_autoguardado)
            self.assertTrue(os.path.exists(manager._session_path()))
            self.assertEqual(main.estados_autoguardado[0],
                             ("guardando", None))
            self.assertEqual(main.estados_autoguardado[-1][0], "guardado")
            self.assertRegex(main.estados_autoguardado[-1][1],
                             r"^\d{2}:\d{2}:\d{2}$")

    def test_autoguardado_no_anuncia_exito_si_falla_publicar_manifiesto(self):
        canvas = Canvas(6, 4)
        canvas.undo_stack.push(QUndoCommand("Cambio"))
        main = _MainAutosave(canvas)
        self.addCleanup(main.deleteLater)

        with tempfile.TemporaryDirectory() as carpeta, \
                patch("models.autosave.app_paths.base_datos", return_value=carpeta):
            manager = AutoSaveManager(main, interval_min=60)
            self.addCleanup(manager.stop)
            with patch("models.autosave.escribir_atomico", return_value=False):
                manager.snapshot()
                self.assertTrue(_esperar(lambda: manager._handle is None))

        self.assertEqual(main.estados_autoguardado,
                         [("guardando", None), ("error", None)])
        self.assertFalse(hasattr(canvas, "_autosave_revision"))


if __name__ == "__main__":
    unittest.main()
