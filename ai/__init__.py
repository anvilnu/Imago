# ai/__init__.py
"""Infraestructura de IA local de Imago (motor ONNX Runtime).

Este paquete agrupa toda la maquinaria comun de las funciones de IA que corren
en LOCAL, offline y autocontenidas (ver propuesta_ia.md). Fase 0:

  - runner.py         Ejecucion de inferencia en un hilo secundario (nunca en el
                      hilo principal), con progreso, cancelacion y cache de
                      InferenceSession.
  - model_manager.py  Catalogo de modelos y descarga bajo demanda (verificacion
                      de hash, cache en la carpeta de datos del usuario, borrado)
                      mas el dialogo "Modelos de IA".
  - imgproc.py        Helpers de pre/postproceso de imagen que reutilizan
                      qimage_to_array / array_to_qimage de adjustments.py.

Las funciones concretas de IA (Eliminar fondo, Inpainting...) se construyen
encima de esta base en fases posteriores.
"""
