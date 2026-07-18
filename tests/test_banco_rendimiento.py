import json
import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from benchmarks.benchmark_editor import (
    METRICAS_ESPERADAS, _resumen, comparar_resultados, ejecutar_banco,
    guardar_resultado,
)


class BancoRendimientoTests(unittest.TestCase):
    def test_resumen_usa_mediana_y_conserva_muestras(self):
        resumen = _resumen([9, 1, 5])
        self.assertEqual(resumen["mediana"], 5.0)
        self.assertEqual(resumen["minimo"], 1.0)
        self.assertEqual(resumen["maximo"], 9.0)
        self.assertEqual(resumen["muestras"], [9.0, 1.0, 5.0])

    def test_comparacion_detecta_solo_regresiones_fuera_de_tolerancia(self):
        metricas_base = {
            nombre: {"mediana": 10.0} for nombre in METRICAS_ESPERADAS
        }
        metricas_actuales = {
            nombre: {"mediana": 12.0} for nombre in METRICAS_ESPERADAS
        }
        metricas_actuales["composicion_ms"] = {"mediana": 14.0}
        base = {"perfil": "rapido", "metricas": metricas_base,
                "memoria": {"incremento_pico_mib": 10.0}}
        actual = {"perfil": "rapido", "metricas": metricas_actuales,
                  "memoria": {"incremento_pico_mib": 12.0}}

        regresiones = comparar_resultados(actual, base, tolerancia=0.35)

        self.assertEqual(
            [regresion["metrica"] for regresion in regresiones],
            ["composicion_ms"])

        base_pequena = {"perfil": "rapido", "metricas": {
            nombre: {"mediana": 0.05} for nombre in METRICAS_ESPERADAS
        }, "memoria": {"incremento_pico_mib": 2.0}}
        actual_pequena = {"perfil": "rapido", "metricas": {
            nombre: {"mediana": 0.12} for nombre in METRICAS_ESPERADAS
        }, "memoria": {"incremento_pico_mib": 6.0}}
        self.assertEqual(
            comparar_resultados(actual_pequena, base_pequena), [])

        actual["memoria"]["incremento_pico_mib"] = 25.0
        self.assertEqual(
            comparar_resultados(actual, base)[-1]["metrica"],
            "incremento_pico_mib")

    def test_perfil_rapido_ejecuta_todas_las_rutas_y_serializa_json(self):
        resultado = ejecutar_banco(
            "rapido", repeticiones=1, calentamientos=0)

        self.assertEqual(set(resultado["metricas"]), set(METRICAS_ESPERADAS))
        self.assertEqual(resultado["configuracion"]["ancho"], 320)
        self.assertGreaterEqual(
            resultado["memoria"]["rss_pico_mib"],
            resultado["memoria"]["rss_inicial_mib"])
        for metrica in resultado["metricas"].values():
            self.assertEqual(len(metrica["muestras"]), 1)
            self.assertGreaterEqual(metrica["mediana"], 0.0)

        with tempfile.TemporaryDirectory() as carpeta:
            ruta = os.path.join(carpeta, "resultado.json")
            guardar_resultado(resultado, ruta)
            with open(ruta, "r", encoding="utf-8") as archivo:
                cargado = json.load(archivo)
        self.assertEqual(cargado["version_banco"], resultado["version_banco"])


if __name__ == "__main__":
    unittest.main()
