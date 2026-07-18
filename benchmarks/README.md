# Banco de rendimiento de Imago

Este banco ejecuta rutas reales del editor con Qt en modo `offscreen`, semilla
fija y documentos de dimensiones conocidas. No abre `MainWindow`, no carga
plugins y no lee ni escribe preferencias del usuario. Los proyectos temporales
se crean en la carpeta temporal del sistema y se eliminan al terminar.

## Uso

Desde la raíz del repositorio y con el entorno de Imago activo:

```powershell
python -m benchmarks.benchmark_editor --perfil rapido
python -m benchmarks.benchmark_editor --perfil estandar --salida resultado.json
python -m benchmarks.benchmark_editor --perfil grande --salida resultado-grande.json
```

Los perfiles fijan dimensiones, capas, pestañas, movimientos por trazo, radio
del efecto, calentamientos y repeticiones. Estos dos últimos valores se pueden
sobrescribir para una investigación concreta:

```powershell
python -m benchmarks.benchmark_editor --perfil estandar `
  --repeticiones 9 --calentamientos 2 --salida resultado.json
```

Para comparar con una línea base y devolver código de salida 1 si alguna
mediana rebasa la tolerancia:

```powershell
python -m benchmarks.benchmark_editor --perfil estandar `
  --comparar benchmarks/baselines/windows-11-estandar.json `
  --tolerancia 0.35
```

La comparación exige el mismo perfil. El 35 % predeterminado y el margen
absoluto de 0,25 ms absorben ruido de planificador en métricas muy pequeñas,
antivirus, temperatura y almacenamiento; no sustituyen revisar el equipo y el
entorno incluidos en ambos JSON. El margen absoluto se puede cambiar con
`--margen-absoluto-ms`; para el incremento de RSS se usa además un margen de
8 MiB configurable con `--margen-absoluto-mib`.

## Qué se mide

- Inicio, cada movimiento y fin de un trazo del `PenTool` real. El final incluye
  crear e insertar el `PaintCommand`; undo y limpieza quedan fuera del tiempo.
- Cambio de índice y proceso de eventos de pestaña, incluida la reconstrucción
  real de Capas, Historial y barra de miniaturas; cierre incluye retirar el
  marcador, desacoplar el scroll, ejecutar `deleteLater` y procesar la destrucción.
- Composición RGBA de todas las capas mediante `Canvas.render_flat_image()`.
- Desenfoque gaussiano real sobre un array RGBA determinista.
- Guardado `.imago` completo mediante el reemplazo atómico de producción.
- Autoguardado completo, incluida la publicación atómica de `session.json`.
- RSS nativo inicial y pico mediante muestreo concurrente cada 2 ms. En Windows
  se usa `GetProcessMemoryInfo`; en Linux, `/proc/self/statm`; en macOS, el pico
  que ofrece `getrusage`.

Cada métrica temporal registra todas las muestras y resume mediana, mínimo y
máximo. La mediana es el valor usado al comparar porque resiste mejor picos
aislados. La salida también conserva versiones de Python, PySide6 y NumPy,
plataforma, procesador, núcleos lógicos y RAM física.

## Protocolo para una línea base

1. Cerrar aplicaciones pesadas y dejar el equipo conectado a corriente.
2. Usar el mismo perfil, versiones y modo de energía en todas las comparaciones.
3. Ejecutar una vez para calentar imports y cachés del sistema.
4. Ejecutar de nuevo con `--salida`; ese segundo JSON es la línea base.
5. No mezclar resultados de Windows y Linux ni de equipos diferentes.

Las líneas base versionadas describen el equipo concreto que las produjo; no
son objetivos universales. Sirven para detectar regresiones en ese entorno y
para decidir con datos si se retoman capas de ajuste u opacidad de grupos.
