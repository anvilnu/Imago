"""Regresiones de la fuente única de versión de Imago."""

from pathlib import Path
import re
import unittest

from imago_version import APP_VERSION


_RAIZ = Path(__file__).resolve().parents[1]


class VersionAplicacionTests(unittest.TestCase):
    def test_version_central_es_numerica_y_la_interfaz_la_importa(self):
        self.assertRegex(APP_VERSION, r"^\d+\.\d+(?:\.\d+){0,2}$")
        ayuda = (_RAIZ / "help_dialogs.py").read_text(encoding="utf-8")
        self.assertIn("from imago_version import APP_VERSION", ayuda)
        self.assertIsNone(re.search(r"^APP_VERSION\s*=", ayuda, re.MULTILINE))

    def test_zip_e_instalador_reciben_la_version_central(self):
        empaquetado = (_RAIZ / "empaquetar.ps1").read_text(encoding="utf-8")
        inno = (_RAIZ / "Imago.iss").read_text(encoding="utf-8")

        self.assertIn("from imago_version import APP_VERSION", empaquetado)
        self.assertIn('$zip = "Imago-$version-portable.zip"', empaquetado)
        self.assertIn('"/DMyAppVersion=$version"', empaquetado)
        self.assertIn("AppVersion={#MyAppVersion}", inno)
        self.assertIsNone(re.search(r"^AppVersion=\d", inno, re.MULTILINE))


if __name__ == "__main__":
    unittest.main()
