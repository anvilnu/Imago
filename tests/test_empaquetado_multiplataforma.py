import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from imago_version import APP_VERSION


_RAIZ = Path(__file__).resolve().parents[1]
_ID_APP = "io.github.anvilnu.imago"


class EmpaquetadoMultiplataformaTests(unittest.TestCase):
    def _leer(self, ruta):
        return (_RAIZ / ruta).read_text(encoding="utf-8")

    def test_identidad_linux_coincide_en_todos_los_metadatos(self):
        main = self._leer("main.py")
        desktop = self._leer(f"packaging/linux/{_ID_APP}.desktop")
        manifiesto = self._leer(f"packaging/linux/{_ID_APP}.yml")
        metainfo = ET.parse(
            _RAIZ / f"packaging/linux/{_ID_APP}.metainfo.xml"
        ).getroot()

        self.assertIn(f'setDesktopFileName("{_ID_APP}")', main)
        self.assertIn(f"Icon={_ID_APP}", desktop)
        self.assertRegex(manifiesto, rf"(?m)^id:\s*{re.escape(_ID_APP)}$")
        self.assertEqual(metainfo.findtext("id"), _ID_APP)
        self.assertEqual(
            metainfo.find("launchable").text,
            f"{_ID_APP}.desktop",
        )

    def test_linux_usa_version_central_y_no_activa_modo_portable(self):
        script = self._leer("empaquetar_linux.sh")
        apprun = self._leer("packaging/linux/AppRun")
        metainfo = self._leer(
            f"packaging/linux/{_ID_APP}.metainfo.xml"
        )

        self.assertIn("from imago_version import APP_VERSION", script)
        self.assertIn('s/@APP_VERSION@/$VERSION/g', script)
        self.assertIn('version="@APP_VERSION@"', metainfo)
        self.assertIn("Imago-$VERSION-x86_64.AppImage", script)
        self.assertIn("Imago-$VERSION-x86_64.flatpak", script)
        self.assertNotIn("portable.txt", script)
        self.assertNotIn("portable.txt", apprun)
        self.assertRegex(APP_VERSION, r"^\d+\.\d+(?:\.\d+){0,2}$")

    def test_workflow_construye_los_cuatro_paquetes(self):
        workflow = self._leer(".github/workflows/distribucion.yml")

        self.assertIn(".\\empaquetar.ps1 -Python", workflow)
        self.assertIn("./empaquetar_linux.sh", workflow)
        self.assertIn("Imago-$env:VERSION-Setup.exe", workflow)
        self.assertIn("Imago-$env:VERSION-portable.zip", workflow)
        self.assertIn("Imago-$VERSION-x86_64.AppImage", workflow)
        self.assertIn("Imago-$VERSION-x86_64.flatpak", workflow)
        self.assertIn("--draft", workflow)
        self.assertIn("APPIMAGETOOL_SHA256", workflow)
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("publicar_release:", workflow)
        self.assertIn("ETIQUETA_SOLICITADA", workflow)
        self.assertNotIn("branches:", workflow)
        self.assertNotIn("\n  push:", workflow)
        self.assertIn(
            "ref: ${{ inputs.publicar_release && inputs.etiqueta || github.ref }}",
            workflow,
        )

    def test_receta_pyinstaller_separa_icono_por_plataforma(self):
        receta = self._leer("Imago.spec")

        self.assertIn("if os.name == 'nt' else None", receta)


if __name__ == "__main__":
    unittest.main()
