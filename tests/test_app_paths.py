"""Regresiones de identidad, migración y modo portable de QSettings."""

import os
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QSettings

import app_paths


def _ini(ruta):
    return QSettings(ruta, QSettings.Format.IniFormat)


class AjustesAplicacionTests(unittest.TestCase):
    def test_migracion_prioriza_miestudio_y_solo_se_ejecuta_una_vez(self):
        with tempfile.TemporaryDirectory() as carpeta:
            anterior = _ini(os.path.join(carpeta, "anterior.ini"))
            actual = _ini(os.path.join(carpeta, "actual.ini"))
            anterior.setValue("language", "fr")
            anterior.setValue("theme", "light")
            actual.setValue("language", "en")
            actual.setValue("solo_actual", 7)

            self.assertTrue(app_paths._migrar_ajustes(actual, anterior))
            self.assertEqual(actual.value("language"), "fr")
            self.assertEqual(actual.value("theme"), "light")
            self.assertEqual(actual.value("solo_actual", type=int), 7)

            anterior.setValue("language", "es")
            self.assertFalse(app_paths._migrar_ajustes(actual, anterior))
            self.assertEqual(actual.value("language"), "fr")

    def test_settings_normal_usa_avnsoft_y_migra_el_almacen_anterior(self):
        with tempfile.TemporaryDirectory() as carpeta:
            almacenes = {
                app_paths.ORGANIZACION: _ini(os.path.join(carpeta, "actual.ini")),
                app_paths._ORGANIZACION_ANTERIOR:
                    _ini(os.path.join(carpeta, "anterior.ini")),
            }
            almacenes[app_paths._ORGANIZACION_ANTERIOR].setValue(
                "language", "en")

            with (patch("app_paths.es_portable", return_value=False),
                  patch("app_paths._settings_nativos",
                        side_effect=lambda org: almacenes[org]) as crear):
                resultado = app_paths.settings()

            self.assertIs(resultado, almacenes[app_paths.ORGANIZACION])
            self.assertEqual(app_paths.idioma(resultado), "en")
            self.assertEqual(
                [llamada.args[0] for llamada in crear.call_args_list],
                [app_paths.ORGANIZACION, app_paths._ORGANIZACION_ANTERIOR])

    def test_settings_portable_solo_usa_el_ini_junto_al_ejecutable(self):
        with tempfile.TemporaryDirectory() as carpeta:
            with (patch("app_paths.es_portable", return_value=True),
                  patch("app_paths.base_datos", return_value=carpeta),
                  patch("app_paths._settings_nativos") as nativos):
                ajustes = app_paths.settings()
                ajustes.setValue("language", "fr")
                ajustes.sync()

            nativos.assert_not_called()
            self.assertEqual(
                os.path.normcase(os.path.abspath(ajustes.fileName())),
                os.path.normcase(os.path.join(carpeta, "Imago.ini")))
            self.assertEqual(app_paths.idioma(ajustes), "fr")

    def test_idioma_invalido_cae_a_espanol(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ajustes = _ini(os.path.join(carpeta, "idioma.ini"))
            ajustes.setValue("language", "xx")
            self.assertEqual(app_paths.idioma(ajustes), "es")


if __name__ == "__main__":
    unittest.main()
