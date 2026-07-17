# plugins/sepia_ejemplo/__init__.py
"""Plugin de EJEMPLO para Imago: un ajuste de tono sepia.

Muestra el patrón mínimo de un plugin de AJUSTE de terceros:
  1. Registrar sus textos con api.registrar_traducciones (ES/EN/FR).
  2. Definir una subclase de api.AdjustmentDialog con build_controls() y
     compute(arr): recibe un array numpy uint8 (alto, ancho, 4) en RGBA y
     devuelve otro igual; el canal 3 es alfa (respétalo).
  3. Registrarla con api.registrar_ajuste(...).

La base aporta gratis el panel overlay, la vista previa en vivo, el botón
Restablecer, el deshacer/rehacer, el respeto de la selección y el tema oscuro.
"""
import numpy as np


def registrar(api):
    api.registrar_traducciones({
        "plugin.sepia.title":     {"es": "Sepia (plugin)", "en": "Sepia (plugin)",
                                   "fr": "Sépia (extension)"},
        "plugin.sepia.intensity": {"es": "Intensidad", "en": "Intensity",
                                   "fr": "Intensité"},
    })

    class SepiaDialog(api.AdjustmentDialog):
        title = api.t("plugin.sepia.title")

        def build_controls(self):
            self.add_slider_row("intensidad", api.t("plugin.sepia.intensity"),
                                0, 100, 100)

        def compute(self, arr):
            inten = self.val("intensidad") / 100.0
            if inten <= 0:
                return arr
            rgb = arr[:, :, :3].astype(np.float32)
            r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
            sep = np.empty_like(rgb)
            sep[:, :, 0] = 0.393 * r + 0.769 * g + 0.189 * b
            sep[:, :, 1] = 0.349 * r + 0.686 * g + 0.168 * b
            sep[:, :, 2] = 0.272 * r + 0.534 * g + 0.131 * b
            np.clip(sep, 0, 255, out=sep)
            mez = rgb * (1.0 - inten) + sep * inten
            arr[:, :, :3] = mez.astype(np.uint8)   # alfa (canal 3) intacto
            return arr

    api.registrar_ajuste("sepia_ejemplo", SepiaDialog)
