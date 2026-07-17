"""Regresiones de escritura atómica de documentos y exportaciones."""

import json
import os
import stat
import tempfile
import unittest
import zipfile
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor, QImage, QPageSize
from PySide6.QtWidgets import QApplication

from atomic_io import escribir_atomico
from batch_dialog import _guardar as guardar_lote
from exif_utils import incrustar_exif_jpeg
from models.anim_io import save_animation
from models.autosave import AutoSaveManager
from models.layer import Layer
from models.project_io import load_project, save_ora, save_project
from ventana.menu_archivo import AccionesMenuArchivo, ResultadoGuardado


_APP = QApplication.instance() or QApplication([])


def _imagen(color=QColor("#336699"), ancho=4, alto=3):
    img = QImage(ancho, alto, QImage.Format_ARGB32)
    img.fill(color)
    return img


class _CanvasProyecto:
    def __init__(self):
        self.base_width = 4
        self.base_height = 3
        self.active_layer_index = 0
        self.layer_counter = 1
        self.guides = []
        self.dpi = 96.0
        layer = Layer(4, 3, "Capa")
        layer.image = _imagen()
        self.layers = [layer]

    def render_flat_image(self, background=None):
        return self.layers[0].image.copy()


class _PilaGuardado:
    def __init__(self):
        self.limpia = False

    def setClean(self):
        self.limpia = True

    def isClean(self):
        return self.limpia


class _CanvasImagen:
    def __init__(self):
        self.imagen = _imagen()
        self.dpi = 96.0
        self.image_quality = -1
        self.image_path = None
        self.project_path = None
        self.source_exif = None
        self.recovered_dirty = True
        self.undo_stack = _PilaGuardado()

    def render_flat_image(self, background=None):
        return self.imagen.copy()


class _AjustesFalsos:
    def __init__(self):
        self.valores = {}

    def setValue(self, clave, valor):
        self.valores[clave] = valor

    def value(self, clave, default=None, type=None):
        return self.valores.get(clave, default)


class _TabsFalsas:
    def __init__(self, titulo="Documento"):
        self.titulo = titulo

    def currentIndex(self):
        return 0

    def tabText(self, index):
        return self.titulo

    def setTabText(self, index, texto):
        self.titulo = texto


class _EstadoFalso:
    def __init__(self):
        self.mensajes = []

    def showMessage(self, texto, tiempo=0):
        self.mensajes.append((texto, tiempo))


class _VentanaArchivo:
    def __init__(self, canvas, titulo="Documento"):
        self.canvas = canvas
        self.tabs = _TabsFalsas(titulo)
        self.settings = _AjustesFalsos()
        self.status_bar = _EstadoFalso()
        self.last_opened_dir = ""
        self.recientes = []

    def get_current_canvas(self):
        return self.canvas

    def _update_window_title(self):
        pass

    def _add_recent(self, ruta):
        self.recientes.append(ruta)


class EscrituraAtomicaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.destino = os.path.join(self.tmp.name, "documento.png")
        with open(self.destino, "wb") as f:
            f.write(b"ORIGINAL")

    def _temporales(self):
        return [n for n in os.listdir(self.tmp.name) if n != "documento.png"]

    def test_exito_reemplaza_y_conserva_extension_para_el_codificador(self):
        extensiones = []

        def escribir(ruta):
            extensiones.append(os.path.splitext(ruta)[1])
            with open(ruta, "wb") as f:
                f.write(b"NUEVO")
            return True

        self.assertTrue(escribir_atomico(self.destino, escribir))
        with open(self.destino, "rb") as f:
            self.assertEqual(f.read(), b"NUEVO")
        self.assertEqual(extensiones, [".png"])
        self.assertEqual(self._temporales(), [])

    def test_resultado_falso_conserva_original_y_limpia_temporal(self):
        def escribir(ruta):
            with open(ruta, "wb") as f:
                f.write(b"PARCIAL")
            return False

        self.assertFalse(escribir_atomico(self.destino, escribir))
        with open(self.destino, "rb") as f:
            self.assertEqual(f.read(), b"ORIGINAL")
        self.assertEqual(self._temporales(), [])

    def test_excepcion_conserva_original_y_se_propaga_sin_dejar_temporal(self):
        def escribir(ruta):
            with open(ruta, "wb") as f:
                f.write(b"PARCIAL")
            raise ValueError("fallo simulado")

        with self.assertRaisesRegex(ValueError, "fallo simulado"):
            escribir_atomico(self.destino, escribir)
        with open(self.destino, "rb") as f:
            self.assertEqual(f.read(), b"ORIGINAL")
        self.assertEqual(self._temporales(), [])

    def test_fallo_de_replace_conserva_original_y_limpia_temporal(self):
        def escribir(ruta):
            with open(ruta, "wb") as f:
                f.write(b"COMPLETO")
            return True

        with patch("atomic_io.os.replace", side_effect=OSError("bloqueado")):
            self.assertFalse(escribir_atomico(self.destino, escribir))
        with open(self.destino, "rb") as f:
            self.assertEqual(f.read(), b"ORIGINAL")
        self.assertEqual(self._temporales(), [])

    @unittest.skipUnless(os.name == "posix", "Permisos POSIX")
    def test_archivo_nuevo_respeta_umask(self):
        os.remove(self.destino)
        umask_anterior = os.umask(0o027)
        try:
            self.assertTrue(escribir_atomico(
                self.destino, lambda ruta: _escribir_bytes(ruta, b"NUEVO")))
        finally:
            os.umask(umask_anterior)
        modo = stat.S_IMODE(os.stat(self.destino).st_mode)
        self.assertEqual(modo, 0o640)

    @unittest.skipUnless(os.name == "posix", "Permisos POSIX")
    def test_archivo_existente_conserva_permisos_con_umask_restrictivo(self):
        os.chmod(self.destino, 0o664)
        umask_anterior = os.umask(0o077)
        try:
            self.assertTrue(escribir_atomico(
                self.destino, lambda ruta: _escribir_bytes(ruta, b"NUEVO")))
        finally:
            os.umask(umask_anterior)
        modo = stat.S_IMODE(os.stat(self.destino).st_mode)
        self.assertEqual(modo, 0o664)

    @unittest.skipUnless(os.name == "posix", "Enlaces simbólicos POSIX")
    def test_guardar_mediante_enlace_conserva_el_enlace(self):
        objetivo = os.path.join(self.tmp.name, "objetivo.png")
        with open(objetivo, "wb") as f:
            f.write(b"OBJETIVO ANTERIOR")
        os.remove(self.destino)
        os.symlink(objetivo, self.destino)

        self.assertTrue(escribir_atomico(
            self.destino, lambda ruta: _escribir_bytes(ruta, b"NUEVO")))

        self.assertTrue(os.path.islink(self.destino))
        with open(objetivo, "rb") as f:
            self.assertEqual(f.read(), b"NUEVO")


def _escribir_bytes(ruta, datos):
    with open(ruta, "wb") as f:
        f.write(datos)
    return True


class IntegracionProyectoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.canvas = _CanvasProyecto()

    def test_imago_y_ora_sustituyen_el_destino_con_archivos_validos(self):
        ruta_imago = os.path.join(self.tmp.name, "documento.imago")
        ruta_ora = os.path.join(self.tmp.name, "documento.ora")
        for ruta in (ruta_imago, ruta_ora):
            with open(ruta, "wb") as f:
                f.write(b"VERSION ANTERIOR")

        self.assertTrue(save_project(self.canvas, ruta_imago))
        cargado = load_project(ruta_imago)
        self.assertEqual((cargado["width"], cargado["height"]), (4, 3))

        self.assertTrue(save_ora(self.canvas, ruta_ora))
        with zipfile.ZipFile(ruta_ora) as zf:
            self.assertEqual(zf.read("mimetype"), b"image/openraster")
            self.assertIn("stack.xml", zf.namelist())

        self.assertEqual(sorted(os.listdir(self.tmp.name)),
                         ["documento.imago", "documento.ora"])

    def test_fallo_durante_zip_conserva_el_imago_anterior(self):
        ruta = os.path.join(self.tmp.name, "documento.imago")
        with open(ruta, "wb") as f:
            f.write(b"IMAGO ANTERIOR")

        def fallar(ruta_temporal, *args, **kwargs):
            with open(ruta_temporal, "wb") as f:
                f.write(b"ZIP PARCIAL")
            raise OSError("fallo simulado")

        with patch("models.project_io.zipfile.ZipFile", side_effect=fallar):
            self.assertFalse(save_project(self.canvas, ruta))
        with open(ruta, "rb") as f:
            self.assertEqual(f.read(), b"IMAGO ANTERIOR")
        self.assertEqual(os.listdir(self.tmp.name), ["documento.imago"])


class IntegracionImagenExifTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_guardado_png_publica_imagen_y_limpia_recuperacion(self):
        ruta = os.path.join(self.tmp.name, "imagen.png")
        with open(ruta, "wb") as f:
            f.write(b"PNG ANTERIOR")
        canvas = _CanvasImagen()
        ventana = _VentanaArchivo(canvas)

        resultado = AccionesMenuArchivo._save_image(
            ventana, canvas, ruta, settings={"quality": -1})

        self.assertIs(resultado, ResultadoGuardado.EXITO)
        self.assertFalse(QImage(ruta).isNull())
        self.assertTrue(canvas.undo_stack.isClean())
        self.assertFalse(canvas.recovered_dirty)
        self.assertEqual(os.listdir(self.tmp.name), ["imagen.png"])

    def test_fallo_al_publicar_png_conserva_anterior_y_estado_pendiente(self):
        ruta = os.path.join(self.tmp.name, "imagen.png")
        with open(ruta, "wb") as f:
            f.write(b"PNG ANTERIOR")
        canvas = _CanvasImagen()
        ventana = _VentanaArchivo(canvas)

        with (patch("atomic_io.os.replace", side_effect=OSError("bloqueado")),
              patch("ventana.menu_archivo.imago_critical")):
            resultado = AccionesMenuArchivo._save_image(
                ventana, canvas, ruta, settings={"quality": -1})

        self.assertIs(resultado, ResultadoGuardado.ERROR)
        with open(ruta, "rb") as f:
            self.assertEqual(f.read(), b"PNG ANTERIOR")
        self.assertFalse(canvas.undo_stack.isClean())
        self.assertTrue(canvas.recovered_dirty)
        self.assertEqual(os.listdir(self.tmp.name), ["imagen.png"])

    def test_reincrustacion_exif_es_atomica(self):
        ruta = os.path.join(self.tmp.name, "foto.jpg")
        self.assertTrue(_imagen().save(ruta, "JPEG"))
        with open(ruta, "rb") as f:
            original = f.read()
        # TIFF little-endian mínimo: cabecera, IFD0 vacío y puntero siguiente 0.
        exif = b"Exif\x00\x00II\x2a\x00\x08\x00\x00\x00\x00\x00\x00\x00\x00\x00"

        with patch("atomic_io.os.replace", side_effect=OSError("bloqueado")):
            self.assertFalse(incrustar_exif_jpeg(ruta, exif))
        with open(ruta, "rb") as f:
            self.assertEqual(f.read(), original)

        self.assertTrue(incrustar_exif_jpeg(ruta, exif))
        with open(ruta, "rb") as f:
            self.assertIn(b"Exif\x00\x00", f.read()[:4096])
        self.assertEqual(os.listdir(self.tmp.name), ["foto.jpg"])


class _CapaFotograma:
    def __init__(self, color):
        self.visible = True
        self.opacity = 100
        self.frame_delay = 40
        self.image = _imagen(color)

    def render_image(self):
        return self.image


class _CanvasAnimacion:
    base_width = 4
    base_height = 3

    def __init__(self):
        self.layers = [_CapaFotograma(QColor("red")),
                       _CapaFotograma(QColor("blue"))]


class ExportacionesAtomicasTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_animacion_reemplaza_con_gif_valido(self):
        ruta = os.path.join(self.tmp.name, "animacion.gif")
        with open(ruta, "wb") as f:
            f.write(b"GIF ANTERIOR")
        ok, error = save_animation(_CanvasAnimacion(), ruta, 40)
        self.assertTrue(ok)
        self.assertIsNone(error)
        from PIL import Image
        with Image.open(ruta) as gif:
            self.assertEqual(gif.n_frames, 2)
        self.assertEqual(os.listdir(self.tmp.name), ["animacion.gif"])

    def test_exportar_pdf_reemplaza_con_pdf_valido(self):
        ruta = os.path.join(self.tmp.name, "documento.pdf")
        with open(ruta, "wb") as f:
            f.write(b"PDF ANTERIOR")
        ventana = _VentanaArchivo(_CanvasImagen(), "Documento.png")

        with patch("ventana.menu_archivo.QFileDialog.getSaveFileName",
                   return_value=(ruta, "")):
            AccionesMenuArchivo.export_pdf(ventana)

        with open(ruta, "rb") as f:
            self.assertEqual(f.read(4), b"%PDF")
        self.assertEqual(os.listdir(self.tmp.name), ["documento.pdf"])

    def test_imprimir_a_pdf_reemplaza_con_pdf_valido(self):
        ruta = os.path.join(self.tmp.name, "impresion.pdf")
        with open(ruta, "wb") as f:
            f.write(b"PDF ANTERIOR")
        ventana = _VentanaArchivo(_CanvasImagen(), "Documento.png")

        class DialogoImpresionFalso:
            def __init__(self, *args, **kwargs):
                pass

            def exec(self):
                return True

            def get_settings(self):
                return {
                    "pdf": True,
                    "page_size": QPageSize(QPageSize.PageSizeId.A4),
                    "landscape": False,
                    "gray": False,
                    "fit": True,
                }

        with (patch("print_dialog.PrintDialog", DialogoImpresionFalso),
              patch("ventana.menu_archivo.QFileDialog.getSaveFileName",
                    return_value=(ruta, ""))):
            AccionesMenuArchivo.print_file(ventana)

        with open(ruta, "rb") as f:
            self.assertEqual(f.read(4), b"%PDF")
        self.assertEqual(os.listdir(self.tmp.name), ["impresion.pdf"])

    def test_resultado_por_lotes_no_deja_archivo_parcial(self):
        ruta = os.path.join(self.tmp.name, "lote.png")
        origen = os.path.join(self.tmp.name, "origen.png")
        parametros = {"quality": 90, "keep_exif": False, "keep_gps": False}
        with open(ruta, "wb") as f:
            f.write(b"LOTE ANTERIOR")

        guardar_lote(_imagen(), origen, ruta, parametros)
        self.assertFalse(QImage(ruta).isNull())

        with open(ruta, "wb") as f:
            f.write(b"LOTE ANTERIOR")
        with patch("atomic_io.os.replace", side_effect=OSError("bloqueado")):
            with self.assertRaises(ValueError):
                guardar_lote(_imagen(), origen, ruta, parametros)
        with open(ruta, "rb") as f:
            self.assertEqual(f.read(), b"LOTE ANTERIOR")
        self.assertEqual(os.listdir(self.tmp.name), ["lote.png"])


class ManifiestoRecuperacionTests(unittest.TestCase):
    def test_si_falla_session_json_no_se_podan_las_copias_anteriores(self):
        with tempfile.TemporaryDirectory() as carpeta:
            session = os.path.join(carpeta, "session.json")
            copia = os.path.join(carpeta, "doc_1.imago")
            with open(session, "w", encoding="utf-8") as f:
                json.dump({"entries": [{"file": "anterior.imago"}]}, f)
            with open(session, "rb") as f:
                session_anterior = f.read()
            with open(copia, "wb") as f:
                f.write(b"COPIA")

            canvas = _CanvasProyecto()
            canvas.undo_stack = type("Pila", (), {
                "isClean": lambda self: False,
                "index": lambda self: 1,
            })()
            canvas._autosave_id = 1
            canvas._autosave_idx = 1
            canvas.project_path = None

            tabs = type("Tabs", (), {
                "count": lambda self: 1,
                "widget": lambda self, i: type("Marker", (), {"canvas": canvas})(),
                "tabText": lambda self, i: "Documento",
            })()
            manager = AutoSaveManager.__new__(AutoSaveManager)
            manager.dir = carpeta
            manager.main = type("Main", (), {"tabs": tabs})()
            manager._counter = 1

            with (patch("models.autosave.escribir_atomico", return_value=False),
                  patch.object(manager, "_prune") as podar):
                manager.snapshot()

            podar.assert_not_called()
            with open(session, "rb") as f:
                self.assertEqual(f.read(), session_anterior)

    def test_si_falla_la_unica_copia_pendiente_no_se_borra_sesion_anterior(self):
        with tempfile.TemporaryDirectory() as carpeta:
            session = os.path.join(carpeta, "session.json")
            with open(session, "wb") as f:
                f.write(b'{"entries": [{"file": "anterior.imago"}]}')
            with open(session, "rb") as f:
                session_anterior = f.read()

            canvas = _CanvasProyecto()
            canvas.undo_stack = type("Pila", (), {
                "isClean": lambda self: False,
                "index": lambda self: 1,
            })()
            canvas.project_path = None
            tabs = type("Tabs", (), {
                "count": lambda self: 1,
                "widget": lambda self, i: type("Marker", (), {"canvas": canvas})(),
                "tabText": lambda self, i: "Documento",
            })()
            manager = AutoSaveManager.__new__(AutoSaveManager)
            manager.dir = carpeta
            manager.main = type("Main", (), {"tabs": tabs})()
            manager._counter = 0

            with (patch("models.autosave.save_project", return_value=False),
                  patch.object(manager, "clear") as borrar,
                  patch.object(manager, "_prune") as podar):
                manager.snapshot()

            borrar.assert_not_called()
            podar.assert_not_called()
            with open(session, "rb") as f:
                self.assertEqual(f.read(), session_anterior)


if __name__ == "__main__":
    unittest.main()
