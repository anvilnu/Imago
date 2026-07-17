"""Regresiones del contrato y los límites seguros del formato .imago."""

import copy
import json
import os
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter

from models.layer import Layer, LayerGroup
from models.project_io import (ErrorCargaProyecto, PROJECT_VERSION, _png_bytes,
                               _valor_enum, load_project, save_project)


def _png(ancho=2, alto=2, color=Qt.transparent):
    imagen = QImage(ancho, alto, QImage.Format_ARGB32)
    imagen.fill(color)
    return _png_bytes(imagen)


def _manifest_base():
    normal = QPainter.CompositionMode.CompositionMode_SourceOver
    return {
        "version": PROJECT_VERSION,
        "width": 2,
        "height": 2,
        "active_layer_index": 0,
        "layer_counter": 1,
        "guides": [{"orient": "h", "pos": 1.0}],
        "layers": [{
            "name": "Fondo",
            "visible": True,
            "opacity": 100,
            "blend_mode": _valor_enum(normal),
            "alpha_locked": False,
            "file": "layers/layer_0.png",
        }],
    }


class CargaProyectoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "prueba.imago")

    def tearDown(self):
        self.tmp.cleanup()

    def _escribir(self, manifest, archivos=None, extras=None):
        if archivos is None:
            archivos = {}
            for meta in manifest.get("layers", []):
                ruta = meta.get("file")
                if isinstance(ruta, str):
                    archivos.setdefault(ruta, _png())
                mask = meta.get("mask")
                if isinstance(mask, str):
                    archivos.setdefault(mask, _png())
        with zipfile.ZipFile(self.path, "w", zipfile.ZIP_DEFLATED) as zf:
            for nombre, datos in archivos.items():
                zf.writestr(nombre, datos)
            for nombre, datos in (extras or {}).items():
                zf.writestr(nombre, datos)
            zf.writestr("manifest.json", json.dumps(manifest))

    def _rechaza(self, manifest, archivos=None, contiene=None):
        self._escribir(manifest, archivos)
        with self.assertRaises(ErrorCargaProyecto) as ctx:
            load_project(self.path)
        if contiene is not None:
            self.assertIn(contiene, str(ctx.exception))

    def test_carga_un_proyecto_version_uno_valido(self):
        self._escribir(_manifest_base())

        data = load_project(self.path)

        self.assertEqual((data["width"], data["height"]), (2, 2))
        self.assertEqual(data["dpi"], 96.0)
        self.assertEqual(data["active_layer_index"], 0)
        self.assertEqual(data["guides"], [{"orient": "h", "pos": 1.0}])
        self.assertEqual(len(data["layers"]), 1)
        self.assertEqual((data["layers"][0].image.width(),
                          data["layers"][0].image.height()), (2, 2))

    def test_guardador_actual_genera_un_proyecto_que_supera_el_contrato(self):
        layer = Layer(3, 2, "Prueba")
        layer.image.fill(Qt.red)
        layer.mask = QImage(3, 2, QImage.Format_Grayscale8)
        layer.mask.fill(200)
        raiz = LayerGroup("Raíz")
        layer.group = LayerGroup("Interior", parent=raiz)
        canvas = type("CanvasGuardado", (), {
            "base_width": 3,
            "base_height": 2,
            "dpi": 240.0,
            "active_layer_index": 0,
            "layer_counter": 4,
            "guides": [{"orient": "v", "pos": 2.0}],
            "layers": [layer],
        })()

        self.assertTrue(save_project(canvas, self.path))
        data = load_project(self.path)

        self.assertEqual((data["width"], data["height"]), (3, 2))
        self.assertEqual(data["dpi"], 240.0)
        self.assertEqual(data["layer_counter"], 4)
        self.assertEqual(data["layers"][0].name, "Prueba")
        self.assertEqual((data["layers"][0].mask.width(),
                          data["layers"][0].mask.height()), (3, 2))
        self.assertEqual([g.name for g in data["layers"][0].group.chain()],
                         ["Interior", "Raíz"])

    def test_rechaza_version_ausente_y_version_futura(self):
        sin_version = _manifest_base()
        sin_version.pop("version")
        self._rechaza(sin_version, contiene="versión")

        futura = _manifest_base()
        futura["version"] = PROJECT_VERSION + 1
        self._rechaza(futura, contiene=str(PROJECT_VERSION + 1))

    def test_rechaza_tipos_rangos_indices_modos_y_guias_invalidos(self):
        casos = []
        for clave, valor in (("width", True), ("height", 0), ("dpi", 0),
                             ("active_layer_index", 1)):
            manifest = _manifest_base()
            manifest[clave] = valor
            casos.append((clave, manifest))

        manifest = _manifest_base()
        manifest["layers"][0]["opacity"] = 101
        casos.append(("opacity", manifest))
        manifest = _manifest_base()
        manifest["layers"][0]["blend_mode"] = 9999
        casos.append(("blend_mode", manifest))
        manifest = _manifest_base()
        manifest["guides"] = [{"orient": "v", "pos": float("nan")}]
        casos.append(("guides", manifest))

        for nombre, manifest in casos:
            with self.subTest(nombre=nombre):
                self._rechaza(manifest)

    def test_rechaza_limites_de_capas_memoria_y_tamano_descomprimido(self):
        dos_capas = _manifest_base()
        segunda = copy.deepcopy(dos_capas["layers"][0])
        segunda["file"] = "layers/layer_1.png"
        dos_capas["layers"].append(segunda)
        with patch("models.project_io.MAX_LAYERS", 1):
            self._rechaza(dos_capas)

        with patch("models.project_io.MAX_DOCUMENT_IMAGE_BYTES", 1):
            self._rechaza(_manifest_base())

        self._escribir(_manifest_base())
        with patch("models.project_io.MAX_TOTAL_UNCOMPRESSED_BYTES", 10):
            with self.assertRaises(ErrorCargaProyecto):
                load_project(self.path)

    def test_rechaza_png_y_mascara_con_dimensiones_distintas(self):
        manifest = _manifest_base()
        self._rechaza(
            manifest, {"layers/layer_0.png": _png(1, 2)}, contiene="2 × 2")

        manifest = _manifest_base()
        manifest["layers"][0]["mask"] = "layers/mask_0.png"
        self._rechaza(manifest, {
            "layers/layer_0.png": _png(),
            "layers/mask_0.png": _png(2, 1),
        }, contiene="2 × 2")

    def test_rechaza_png_corrupto_en_vez_de_ignorar_la_mascara(self):
        manifest = _manifest_base()
        manifest["layers"][0]["mask"] = "layers/mask_0.png"
        self._rechaza(manifest, {
            "layers/layer_0.png": _png(),
            "layers/mask_0.png": b"no es un png",
        }, contiene="PNG")

    def test_rechaza_ciclos_y_referencias_de_grupo_inexistentes(self):
        ciclo = _manifest_base()
        ciclo["groups"] = [
            {"id": 0, "name": "A", "parent": 1},
            {"id": 1, "name": "B", "parent": 0},
        ]
        ciclo["layers"][0]["group"] = 0
        self._rechaza(ciclo, contiene="ciclo")

        huerfano = _manifest_base()
        huerfano["layers"][0]["group"] = 7
        self._rechaza(huerfano, contiene="group")

        grupo_sin_capas = _manifest_base()
        grupo_sin_capas["groups"] = [{"id": 0, "name": "Vacío"}]
        self._rechaza(grupo_sin_capas, contiene="groups")

    def test_rechaza_datos_desconocidos_para_no_perderlos_al_guardar(self):
        manifest = _manifest_base()
        manifest["dato_futuro"] = {"importante": True}
        self._rechaza(manifest, contiene="dato_futuro")

        manifest = _manifest_base()
        manifest["layers"][0]["effects"] = [{"tipo": "efecto_futuro"}]
        self._rechaza(manifest, contiene="effects[0]")

        manifest = _manifest_base()
        self._escribir(manifest, extras={"datos/futuros.bin": b"importante"})
        with self.assertRaises(ErrorCargaProyecto) as ctx:
            load_project(self.path)
        self.assertIn("datos/futuros.bin", str(ctx.exception))

    def test_traduce_zip_json_y_entradas_ausentes_a_error_de_proyecto(self):
        with open(self.path, "wb") as f:
            f.write(b"no es un zip")
        with self.assertRaises(ErrorCargaProyecto):
            load_project(self.path)

        with zipfile.ZipFile(self.path, "w") as zf:
            zf.writestr("manifest.json", "{")
        with self.assertRaises(ErrorCargaProyecto):
            load_project(self.path)

        self._escribir(_manifest_base(), archivos={})
        with self.assertRaises(ErrorCargaProyecto) as ctx:
            load_project(self.path)
        self.assertIn("layers/layer_0.png", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
