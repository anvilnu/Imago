# plugins/ruido_sal_pimienta/__init__.py
"""Plugin de EJEMPLO para Imago: un efecto de ruido "sal y pimienta".

Igual que el de sepia pero se registra en Efectos ▸ Plugins con
api.registrar_efecto(...). Salpica un porcentaje de píxeles a blanco (sal) y otro
tanto a negro (pimienta).

Detalle didáctico: el patrón de ruido se genera con una SEMILLA FIJA
(np.random.default_rng(0)), así la vista previa coincide EXACTAMENTE con el
resultado que se confirma al Aceptar (si fuera aleatorio en cada recálculo, lo
previsualizado y lo aplicado no coincidirían).
"""
import numpy as np


def registrar(api):
    api.registrar_traducciones({
        "plugin.saltpepper.title":  {"es": "Ruido sal y pimienta",
                                     "en": "Salt & pepper noise",
                                     "fr": "Bruit sel et poivre"},
        "plugin.saltpepper.amount": {"es": "Cantidad", "en": "Amount",
                                     "fr": "Quantité"},
    })

    class SaltPepperDialog(api.AdjustmentDialog):
        title = api.t("plugin.saltpepper.title")

        def build_controls(self):
            # "Cantidad" es el % total de píxeles afectados (mitad sal, mitad pimienta).
            self.add_slider_row("cantidad", api.t("plugin.saltpepper.amount"),
                                0, 50, 10)

        def compute(self, arr):
            cant = self.val("cantidad") / 100.0
            if cant <= 0:
                return arr
            h, w = arr.shape[:2]
            rng = np.random.default_rng(0)          # semilla fija -> preview == commit
            ruido = rng.random((h, w))
            sal = ruido < (cant / 2.0)
            pimienta = ruido > (1.0 - cant / 2.0)
            arr[sal, 0:3] = 255                      # blanco; alfa (canal 3) intacto
            arr[pimienta, 0:3] = 0                   # negro
            return arr

    api.registrar_efecto("ruido_sal_pimienta", SaltPepperDialog)
