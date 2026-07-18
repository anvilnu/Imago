# Hoja de ruta de Imago

**Versión 1.0 (julio 2026): el plan original está COMPLETO.** Todo lo
implementado (con sus decisiones, gotchas y mediciones) quedó archivado en
`HISTORIAL.md`; las funciones de cara al usuario están documentadas en el
Manual (Ayuda ▸ Manual). Aquí queda SOLO lo pendiente: cosas que se harán,
pero sin fecha ni prisa.

## Auditoría técnica (julio 2026)

La auditoría estática y las pruebas Qt fuera de pantalla de julio de 2026
terminaron sin modificar el código. Los 104 archivos Python analizados
compilan, los 258 iconos coinciden con `recursos.qrc` y la cobertura
ES/EN/FR es buena. Los puntos siguientes son el trabajo detectado, ordenado
por riesgo. Antes de añadir proyectos grandes conviene cerrar al menos las
prioridades críticas, porque afectan a la integridad del documento.

### Prioridad crítica — integridad y pérdida de trabajo

- [x] **Proteger los documentos recuperados al cerrar una pestaña o Imago.**
  Completado el 17-07-2026 y cubierto por 9 pruebas de regresión headless.
  `close_tab()` solo consulta `undo_stack.isClean()` y no
  `canvas.recovered_dirty`: una recuperación recién abierta puede tener la
  pila limpia y cerrarse sin aviso. En `closeEvent()` se detecta al principio,
  pero tras Guardar se vuelve a comprobar solo la pila; cancelar o fallar el
  guardado puede permitir el cierre y `autosave.clear()` borra después todas
  las copias. Centralizar la condición «documento pendiente» y hacer que
  `save_file()`/`save_file_as()` devuelvan éxito, cancelación o error. Una
  recuperación solo deja de estar pendiente después de un guardado confirmado.
  Se centralizó la condición en `models/document_state.py`; Guardar y Guardar
  como devuelven `ResultadoGuardado`, y ambos cierres exigen tanto `EXITO` como
  un documento realmente limpio antes de eliminar la pestaña o el autoguardado.

- [x] **Hacer atómicos todos los guardados que sustituyen un archivo.**
  Completado el 17-07-2026 y cubierto por 15 pruebas específicas de escritura
  y fallo, además de las 9 regresiones de cierre seguro.
  `save_project()` abre el `.imago` definitivo con `ZipFile(..., "w")`, y
  `QImageWriter`, PNG8 y la reincrustación EXIF también escriben directamente
  sobre el destino. Un cierre, disco lleno o error de codificación puede
  destruir una versión anterior válida. Escribir en un temporal de la misma
  carpeta, cerrar y verificar, y sustituir con `os.replace()` solo al terminar;
  conservar el original si cualquier fase falla. Aplicarlo primero a `.imago`
  y Ctrl+S de imágenes, y después a ORA, animación, PDF y `session.json`.
  Se centralizó el protocolo en `atomic_io.py`: el temporal se crea en la misma
  carpeta y conserva la extensión, se cierra y sincroniza, y solo entonces se
  publica con `os.replace()`. Ya lo usan `.imago`, PNG/JPEG y EXIF, ORA, ambos
  PDF, GIF/WebP, procesamiento por lotes y `session.json`. Si falla cualquier
  fase se conserva el destino anterior y se elimina el temporal. El manifiesto
  de recuperación solo poda copias antiguas después de publicarse con éxito.
  Endurecido después para Linux: los archivos nuevos respetan `umask`, los ya
  existentes conservan sus permisos POSIX, guardar mediante un enlace simbólico
  actualiza su objetivo sin romper el enlace y, tras `os.replace()`, se intenta
  sincronizar también el directorio. Las pruebas POSIX quedan condicionales para
  ejecutarse automáticamente en Linux; las comunes siguen cubriendo Windows.

- [x] **Transformar siempre la máscara junto con su capa.** Voltear o girar
  una capa o toda la imagen, cambiar el tamaño de imagen y cambiar el tamaño
  del lienzo modifican los píxeles pero no todas las máscaras. Una prueba
  confirmó que al girar un lienzo de 3×2 a 2×3 la máscara seguía midiendo
  3×2. Crear auxiliares compartidos para imagen+máscara y usarlos en
  `FlipCommand`, `RotateCommand`, `ImageResizeCommand`,
  `CanvasResizeCommand` y las transformaciones de una sola capa. Deshacer y
  rehacer deben restaurar ambas exactamente.
  Se centralizaron la reubicación, escala, reflejo y giro coordinados de imagen
  y máscara en `models/layer_commands.py`. Las transformaciones del documento
  completo actualizan todas las máscaras y las de una sola capa usan comandos
  propios, por lo que imagen+máscara forman un único paso de historial. Los
  márgenes nuevos de una máscara quedan ocultos (negro), su formato continúa
  siendo `Grayscale8` y las capas sin máscara siguen sin ella. La regresión
  `tests/test_transformaciones_mascara.py` verifica dimensiones, píxeles y
  ciclos exactos de deshacer/rehacer en las seis rutas afectadas.

- [x] **Corregir la duplicación y rasterización de capas con máscara.**
  `_copia_de_capa()` y `RasterizeLayerCommand` leen `mask_linked`, atributo
  inexistente en `Layer`; duplicar una capa enmascarada lanza
  `AttributeError`. Decidir si el vínculo de máscara forma parte del modelo o
  retirar esa propiedad. Al duplicar deben clonarse también los efectos no
  destructivos y `frame_delay`. Revisar además que rasterizar texto no hornee
  una máscara y después vuelva a aplicarla.
  Se retiró `mask_linked`: no formaba parte del modelo, la interfaz ni la
  persistencia, por lo que añadirlo habría creado estado sin comportamiento.
  Una rutina común copia ahora todos los metadatos de capa; máscara y efectos
  se clonan de forma independiente, mientras el grupo conserva su referencia
  organizativa y `frame_delay` mantiene la temporización de animación. El
  modelo expone además el render base sin máscara: al rasterizar texto se
  guardan esos píxeles y se conserva la máscara editable, aplicándola una sola
  vez. `tests/test_duplicacion_rasterizacion.py` cubre capas de píxeles y texto,
  ausencia de alias, efectos, animación y deshacer/rehacer.

- [x] **Validar la identidad del destino de IA y overlays antes de aplicar.**
  La IA conserva `canvas`+índice mientras el usuario puede editar, reordenar o
  borrar capas, cambiar de pestaña o cerrarla; el resultado puede terminar en
  otra capa o sobrescribir cambios posteriores. Ajustes y Efectos de capa
  mezclan también objeto, índice capturado y capa activa. Añadir una identidad
  estable de capa y una revisión del documento/imagen; al terminar, aplicar
  solo si siguen coincidiendo o pedir al usuario que repita. Cancelar o cerrar
  el overlay/trabajo al cerrar el documento y bloquear las mutaciones de capa
  incompatibles mientras la preview posee la capa.
  Completado el 17-07-2026. Cada `Layer` recibe un `uid` estable durante la
  ejecución y `models/destino_edicion.py` centraliza `DestinoCapa` y
  `DestinoDocumento`: localizan de nuevo el objeto aunque se haya reordenado y
  comprueban que el documento siga abierto, activo y con la misma revisión.
  Todas las rutas de IA conservan ese destino desde antes de una posible
  descarga y lo revalidan antes de leer o aplicar; un resultado obsoleto se
  descarta con un aviso, sin saltar a la capa o pestaña actuales. Los overlays
  de Ajustes, Efectos, giro libre y refinado de selección quedan ligados a su
  destino, no restauran encima de ediciones externas y se cancelan al cambiar o
  cerrar el documento. Mientras poseen una preview se bloquean las mutaciones
  incompatibles de capas/documento. Cubierto por 8 regresiones específicas de
  identidad, reordenación, revisión, cierre, cancelación y deshacer.

### Prioridad alta — corrección y persistencia

- [x] **Fusionar hacia abajo sin alterar el aspecto.** La composición hornea
  la capa inferior y después conserva su opacidad y modo de fusión, que se
  aplican una segunda vez al resultado combinado. Se reprodujo una capa azul
  opaca que acabó con alfa 127 al fusionarse sobre una inferior al 50 %.
  Calcular el resultado visual equivalente y normalizar en la capa resultante
  las propiedades que ya hayan sido horneadas; añadir casos con opacidad,
  modos de fusión, recorte, máscara, efectos y grupos.
  Completado el 17-07-2026 y cubierto por 4 pruebas de regresión específicas.
  `MergeDownCommand` compone ahora ambas capas sobre transparencia con las
  mismas reglas del lienzo y hornea una sola vez máscaras, efectos, opacidad,
  modo de fusión y recorte. La capa resultante normaliza esas propiedades
  (`100 %`, modo Normal, sin máscara/efectos/recorte), conserva el grupo y los
  demás metadatos de la inferior, y deshacer restaura píxeles, propiedades y
  selección múltiple exactamente. `visible_para_fusion()` unifica además la
  disponibilidad entre lienzo, menú y panel, incluyendo grupos y bases de
  recorte ocultos.

- [x] **Destruir de verdad los widgets de pestañas cerradas.** `removeTab()`
  solo los oculta: el marcador continúa bajo el `QStackedWidget` y conserva
  lienzo, imágenes, historial y cachés hasta salir de Imago. Recuperar el
  widget, quitar la pestaña y llamar a `deleteLater()` tras desconectar/cancelar
  sus trabajos. Aplicarlo también al cierre automático del lienzo inicial.
  Completado el 17-07-2026 y cubierto por 2 regresiones Qt específicas.
  `_retirar_y_destruir_pestana()` centraliza ahora ambos caminos de cierre:
  cancela previews, IA y herramientas flotantes; desvincula los paneles y
  callbacks que apuntaban al documento; retira la pestaña y programa la
  destrucción del botón, el marcador, el scroll y el lienzo. Las pruebas fuerzan
  los eventos `DeferredDelete` y comprueban que los cuatro objetos Qt dejan de
  ser válidos, mientras el documento recién abierto permanece intacto.

- [x] **Endurecer el cargador `.imago` y versionar el contrato.** Validar
  `version`, tipos, dimensiones positivas y razonables, número de capas,
  tamaño descomprimido, dimensiones de PNG/máscaras, índices activos, modos de
  fusión y guías. Rechazar ciclos de grupos (A→B→A), que hoy pueden dejar
  `LayerGroup.chain()`/`visible_efectiva()` en bucle infinito. Traducir todos
  los errores de archivo/esquema a un error de proyecto comprensible. No abrir
  ni volver a guardar silenciosamente una versión futura que contenga datos
  desconocidos.
  Completado el 17-07-2026 y cubierto por 10 regresiones específicas.
  `load_project()` valida ahora íntegramente el contrato v1 antes de crear capas:
  versión, claves y tipos, dimensiones y memoria estimada, cantidades, rutas y
  tamaños ZIP, PNG y máscaras del tamaño exacto, índices, modos de fusión,
  guías, grupos y efectos. Rechaza ciclos, referencias huérfanas, entradas
  duplicadas o desconocidas y versiones futuras para impedir que un posterior
  guardado elimine información que esta versión no entiende. Todos los fallos
  se traducen a `ErrorCargaProyecto` con mensajes ES/EN/FR; una prueba de ida y
  vuelta confirma que el guardador actual cumple el contrato.

- [x] **Conservar el DPI en `.imago` y hacerlo parte del historial sucio.** El
  manifiesto no serializa `canvas.dpi`; al reabrir vuelve a 96. Cambiar solo
  el DPI tampoco crea una operación ni activa el aviso de guardado, y deshacer
  un cambio combinado de tamaño no restaura el DPI. Guardarlo en el proyecto y
  crear un comando que incluya tamaño anterior/nuevo y DPI anterior/nuevo.
  Completado el 17-07-2026. El manifiesto v1 guarda y valida `dpi`, manteniendo
  96 PPP como valor compatible para proyectos antiguos. `ImageResizeCommand`
  conserva ahora tamaño y PPP anteriores/nuevos dentro del mismo paso: deshacer
  y rehacer restauran ambos, y un cambio exclusivo de resolución entra en
  `QUndoStack`, marca el documento como pendiente y aparece en Historial sin
  copiar innecesariamente las imágenes de las capas. Cubierto por 4 escenarios
  de regresión de persistencia, compatibilidad, cambio combinado y solo PPP.

- [x] **Identificar cambios de autoguardado por revisión, no por índice de
  `QUndoStack`.** Tras deshacer del índice 5 al 4 y crear una rama alternativa
  que vuelve al 5, el contenido es distinto pero el autoguardado cree que no
  cambió. Mantener un contador monotónico de revisión o una identidad de estado
  independiente del índice. Escribir `session.json` atómicamente y no podar la
  última copia válida hasta confirmar la nueva.
  Completado el 17-07-2026. Cada `Canvas` mantiene ahora una
  `revision_autoguardado` monotónica que avanza con nuevos comandos, deshacer y
  rehacer; `AutoSaveManager` compara esa revisión con la última copia confirmada
  en vez de comparar la posición de `QUndoStack`. Una regresión reproduce dos
  ramas distintas que terminan en el mismo índice y confirma que la segunda se
  vuelve a guardar, sin reescribir cuando la revisión no cambia. `session.json`
  conserva la escritura atómica existente y las copias antiguas solo se podan
  después de publicar correctamente el nuevo manifiesto.

- [x] **Respetar grupos y efectos al exportar animaciones.**
  `frames_de_capas()` usa `layer.visible` en lugar de
  `visible_efectiva(layer)` y `render_image()` en lugar del render con efectos;
  una capa dentro de un grupo oculto todavía se exporta y los efectos pueden
  desaparecer. Unificar la precomprobación, preview y exportación con la misma
  función de render de fotograma.
  Completado el 17-07-2026. `capas_de_animacion()` es ahora la única selección
  de fotogramas para la precomprobación y respeta la visibilidad de la capa, su
  grupo y todos sus ancestros. `frames_de_capas()` consume esa lista y usa
  `render_with_effects()`, que conserva también máscara y efectos antes de
  aplicar la opacidad. La preview y `save_animation()` ya compartían estos
  fotogramas, por lo que las tres rutas muestran y exportan ahora el mismo
  resultado. Cubierto por 3 regresiones de grupos anidados, visibilidad propia,
  duraciones y render con efectos.

- [x] **Unificar la identidad de QSettings y el traductor de Qt.** Los ajustes
  usan `app_paths.settings()` (`MiEstudio/Imago` o INI portable), pero el
  traductor lee un `QSettings()` ligado a `AVNSoft/Imago`. El idioma propio
  puede cambiar sin que cambien los textos nativos de Qt, y el modo portable
  queda ignorado. Leer siempre mediante `app_paths.settings()` y decidir una
  única organización para ajustes y `QStandardPaths`, con migración de valores
  existentes si se cambia.
  Completado el 17-07-2026. `AVNSoft/Imago` es ahora la identidad normal única
  para `QSettings` y `QStandardPaths`, conservando así la ubicación existente de
  modelos y recuperaciones. `app_paths.settings()` migra una sola vez todas las
  preferencias de `MiEstudio/Imago`, con prioridad para esos valores y sin borrar
  el almacén anterior; solo confirma la migración si las sincronizaciones no dan
  error. `app_paths.idioma()` alimenta tanto `i18n` como `QTranslator`, incluido
  `datos/Imago.ini` en el ejecutable portable, que continúa sin tocar el registro.
  Cubierto por 4 regresiones de migración, identidad, aislamiento portable y
  fallback de idioma.

### Rendimiento y memoria

- [x] **Actualizar miniaturas solo cuando cambie el documento.** La miniatura
  activa recompone y reduce todo el lienzo cada 1,2 segundos aunque nada haya
  cambiado. Sustituir el sondeo periódico por una revisión/dirty flag, limitar
  la frecuencia durante un trazo y reutilizar el último compuesto o una caché
  reducida. Medir documentos grandes con muchas capas y efectos.
  Completado el 17-07-2026. `Canvas` emite cambios solo cuando varía la huella
  visual de dimensiones, capas, máscaras, grupos, recorte y efectos; selección,
  zoom y animación de hormigas no invalidan. La barra conserva por documento
  una vista previa de 150×110 compartida con el tooltip y agrupa ráfagas con un
  `QTimer` de disparo único a 250 ms: en reposo no hay temporizador activo ni
  recomposiciones. Medición Windows, documento 2400×1600 con 8 capas y 8 efectos:
  412,78 ms en frío, 35,63 ms en caliente y 17,92 µs por huella; se eliminan
  los 50 sondeos/minuto anteriores. Cubierto por 3 regresiones de caché,
  agrupación/reposo e invalidación visual.

- [x] **Evitar matrices de imagen completa al iniciar herramientas locales.**
  Dedo, Licuar, Esponja y Sobreexponer/Subexponer convierten la capa completa y
  crean buffers `float32`; una imagen RGBA de 4000×5000 ocupa ~80 MB en
  `uint8` y ~320 MB por copia `float32`, con picos que pueden superar 500 MB.
  Trabajar por teselas/ROI alrededor del trazo o mantener un buffer compartido
  con copia diferida. Revisar también coberturas completas de pincel,
  aerógrafo y clonado.
  Completado el 17-07-2026. `tools/roi_buffers.py` aporta estado RGBA
  premultiplicado y coberturas `float32` por teselas de 256×256, cargadas solo
  donde pasa el pincel, además de conversiones y selección limitadas al ROI.
  Dedo y Licuar conservan la precisión flotante entre estampas; Esponja y
  Sobre/Subexponer recalculan cada parche desde el original y su cobertura
  dispersa, manteniendo selección, bloqueo alfa, preview y deshacer. Pincel,
  Aerógrafo, Clonado y la cobertura de Sustituir color usan la misma estructura.
  Medición Windows en 4000×5000 con punta de 101 px: los arrays auxiliares al
  pulsar bajan de unos 400–420 MB a 2,20 MB (Dedo), 0,04 MB (Licuar) y 0,54 MB
  (Esponja y Sobre/Subexponer), con arranques de 18–26 ms. Cubierto por 5
  regresiones de teselas, memoria independiente del documento, resultado,
  deshacer, selección, alfa y coberturas de las otras herramientas.

- [x] **Pasar el rectángulo sucio conocido a `PaintCommand`.** El comando
  guarda únicamente el parche, pero para encontrarlo crea una comparación
  booleana de toda la imagen al soltar cada trazo (~80 MB adicionales en una
  imagen RGBA de 20 MP). Las herramientas ya conocen normalmente la zona
  tocada: admitir un `dirty_rect` opcional y conservar `_diff_rect` como
  respaldo para operaciones que no puedan proporcionarlo.
  Completado el 17-07-2026. `PaintCommand` acepta `QRect` o una caja semiabierta
  `(x0, y0, x1, y1)`, la recorta al lienzo y busca el parche exacto solo dentro
  de ella; `_diff_rect` completo se conserva para las operaciones sin geometría
  conocida. Pinceles, retoque, cubo, geometrías y operaciones de selección
  propagan su zona, y el calado también se compone por parche. Los gestos sin
  cambios se marcan obsoletos y no entran en Historial, sin comparar antes dos
  `QImage` completos. Medición Windows en 4000×5000, ROI de 101×101: mediana de
  27,06 ms y ~80 MB temporales a 0,10 ms y ~40 KB. Cubierto por 5 regresiones
  específicas y la suite completa de 83 pruebas (3 POSIX omitidas en Windows).

- [x] **Sacar autoguardado, guardado y exportaciones pesadas del hilo GUI.**
  El `QTimer` de autoguardado comprime secuencialmente todas las capas en el
  hilo de interfaz cada tres minutos; guardar, cargar y algunos exports hacen
  lo mismo. Crear una instantánea coherente y desasociada del documento en el
  hilo GUI y comprimir/escribir en un worker, con cancelación, progreso y una
  sola operación de E/S pesada por documento.
  Completado el 18-07-2026. `.imago` captura metadatos, grupos, capas, máscaras
  y efectos mediante copias implícitas de `QImage`: la instantánea queda
  congelada por copy-on-write y la compresión PNG/ZIP se ejecuta después sin
  leer el lienzo vivo. El mismo patrón cubre imagen plana (incluido PNG8 y
  EXIF), PDF, ORA y GIF/WebP. Cargar `.imago`, PSD, imágenes y animaciones, y
  rasterizar SVG también se ejecutan en el worker. Autoguardado y operaciones
  manuales comparten una única cola serial, con progreso y cancelación
  cooperativa; cancelar nunca publica el temporal. La espera usa un bucle Qt
  anidado, por lo que la ventana sigue atendiendo eventos. Si el usuario edita
  durante un guardado, se publica la instantánea solicitada pero el documento
  nuevo permanece pendiente en vez de marcarse limpio por error. Cubierto por
  4 regresiones nuevas de hilo, capacidad de respuesta, aislamiento de la
  instantánea y cancelación, además de la suite completa de 87 pruebas (3
  POSIX omitidas en Windows).

- [x] **Medir y presupuestar las previews y efectos de capa.** La preview
  reducida y el debounce existentes son buenos, pero Aceptar recalcula a
  resolución completa en el hilo GUI y cualquier cambio de píxeles invalida
  la caché completa de efectos de la capa. Medir por efecto y tamaño; mover
  los finales pesados a workers y estudiar cachés por región antes de retomar
  capas de ajuste u opacidad de grupos.
  Completado el 18-07-2026. Los ajustes marcados `heavy` capturan en GUI una
  instantánea formada solo por valores Python/NumPy y calculan el resultado
  final en una cola serial; ningún widget se lee desde el worker y el callback
  vuelve a validar documento, capa y revisión antes de crear el único paso de
  deshacer. Los controles quedan bloqueados durante el cálculo, pero Cancelar
  y la X siguen disponibles. Los efectos de capa agrupan las ráfagas de slider
  durante 140 ms y su caché ya no es otro lienzo completo: conserva un parche
  con la caja del alfa y sus halos; exportación/rasterizado materializan el
  tamaño completo solo cuando lo necesitan.
  Medición Windows 11: a 1200×800 / 2400×1600, gaussiano 652/859 ms, óleo
  438/1815 ms y desenfoque radial 1500/5973 ms; esos finales ya no bloquean el
  bucle Qt. En una capa dispersa de 800×600 dentro de un lienzo 4000×3000 con
  los ocho efectos, la caché baja de 45,8 a 2,3 MiB y el cálculo de 1034 a
  869 ms. Una capa completamente opaca sigue siendo el peor caso regional
  (45,8 MiB y ~7,1 s con los ocho efectos), dato que desaconseja introducir
  todavía efectos que dependan de otras capas. Cubierto por 7 regresiones
  nuevas de worker, revalidación, debounce, invalidación y parche regional,
  además de la suite completa de 94 pruebas (3 POSIX omitidas en Windows).

- [x] **Reducir copias en el IPC de IA y hacer rápida la cancelación.** Los
  arrays grandes se serializan entre procesos y duplican memoria. Valorar
  memoria compartida o archivos mapeados para entrada/salida. Durante la
  espera inicial del worker, comprobar cancelación en vez de poder esperar
  hasta 120 segundos; cerrar Imago debe cancelar y terminar los procesos sin
  bloquear la salida.
  Completado el 18-07-2026. Los arrays NumPy de 256 KiB o más, también cuando
  están anidados en listas/tuplas/diccionarios, viajan como descriptores de
  archivos `.npy` mapeados dentro de un directorio temporal privado por tarea;
  el socket autenticado conserva pickle solo para control y objetos pequeños.
  El hijo abre entradas en copia-en-escritura y el principal desliga la salida
  antes de terminarlo; después se elimina el directorio tanto en éxito como en
  error, crash nativo o cancelación, respetando el bloqueo de archivos de
  Windows y la semántica POSIX. En RGB 4000×3000 el mensaje baja de un pickle
  adicional de 34,3 MiB a un descriptor de 85 bytes (queda una única copia al
  mapa, medido en 130 ms, en vez de pickle + socket).
  `_accept()` sondea cada 50 ms el token y la muerte del hijo durante el antiguo
  timeout de 120 s. Tras conectar, Cancelar concede solo 0,5 s cooperativos y
  termina el proceso; una cancelación real medida concluyó en 273 ms. Las copias
  al mapa se trocean a ~16 MiB para consultar el token entre bloques. Cubierto
  por 5 regresiones nuevas con proceso real, progreso, entrada/salida anidada,
  espera inicial, error, crash y limpieza; suite completa de 99 pruebas (3
  POSIX omitidas en Windows).

### Calidad, seguridad y mantenibilidad

- [ ] **Añadir pruebas automatizadas headless de los invariantes críticos.**
  Empezar por round-trip `.imago`, recuperación y cancelación de guardado,
  undo/redo, capa+máscara en toda transformación, duplicar/fusionar, grupos,
  exportación animada y callbacks asíncronos sobre capas reordenadas. Añadir
  también archivos corruptos/maliciosos pequeños. La compilación sintáctica no
  protege estas interacciones de estado.

- [ ] **Crear un banco de rendimiento reproducible.** Generar documentos de
  tamaños y números de capas conocidos y medir inicio/movimiento/fin de trazo,
  cambio/cierre de pestaña, composición, efectos, guardado, autoguardado y pico
  de RAM. Registrar una línea base para impedir regresiones y decidir con datos
  los proyectos grandes aparcados.

- [ ] **Verificar completamente los modelos de IA instalados.**
  `is_installed()` solo comprueba que exista el `.onnx`; no verifica hash ni
  el `.data` acompañante. Conservar una marca de instalación validada, hacer
  atómica la extracción de ZIP y volver a verificar después de descarga o al
  detectar un error de carga. No marcar permanentemente una operación como
  incompatible con GPU por errores que no sean realmente del proveedor GPU.

- [ ] **Limpiar duplicados de i18n y centralizar el estilo restante.**
  `opt.chk.antialias` está definida dos veces con textos distintos y varias
  claves de efectos están repetidas. Eliminar duplicados y añadir una
  comprobación automática. Mover a `theme.py` los colores/QSS visibles que aún
  están en `main.py`, `tab_thumbnails.py` y otros widgets, respetando tema
  claro y oscuro.

- [ ] **Aclarar o reforzar la eliminación de GPS EXIF.** Hoy se neutraliza el
  puntero GPS, por lo que lectores normales no muestran las coordenadas, pero
  los bytes originales quedan huérfanos y podrían recuperarse de forma
  forense. Si la opción se presenta como privacidad/anonimización, ofrecer
  eliminación física real o explicar con precisión su alcance.

- [ ] **Higiene del repositorio y de las distribuciones.** Confirmar que
  `.venv`, `build`, `dist`, ZIP portables, `__pycache__` y logs no estén
  versionados; añadir/actualizar `.gitignore` y documentar qué artefactos se
  generan. Revisar el tamaño de cada distribución antes de publicar.

### Mejoras de producto sugeridas por la auditoría

- [x] **Indicador de autoguardado verificable.** Mostrar estado «guardando»,
  hora de la última copia confirmada y error persistente si no pudo escribirse;
  no comunicar éxito antes del `os.replace()` final.
  Completado el 18-07-2026. La barra de estado incorpora una lectura permanente
  traducida ES/EN/FR: empieza sin copia confirmada, muestra «guardando» durante
  el trabajo, conserva «error» si falla y solo publica la hora `HH:mm:ss` cuando
  tanto las copias como `session.json` han terminado su reemplazo atómico. Una
  revisión tampoco se marca internamente como autoguardada si falló el
  manifiesto, de modo que el siguiente ciclo vuelve a intentarla. El indicador
  es dirigido por eventos y no añade temporizadores ni inspecciones del lienzo;
  10.000 actualizaciones sintéticas de la etiqueta costaron 29,43 ms en Windows
  11 (0,0029 ms por evento), frente a como máximo unas pocas por ciclo de tres
  minutos. Cubierto por regresiones de éxito posterior al manifiesto, fallo de
  publicación y persistencia visual del error, además de la suite completa de
  101 pruebas (3 POSIX omitidas en Windows).
- [x] **Diagnóstico opcional del documento.** Un panel pequeño con dimensiones,
  capas, memoria estimada, efectos caros y tamaño aproximado del proyecto
  ayudaría a explicar lentitud antes de una operación pesada.
  Completado el 18-07-2026. El botón superior y Ver ▸ Diagnóstico del documento
  abren una ventana modeless independiente, sin ocupar ni aumentar la altura
  mínima de la columna derecha. Mantiene una única instancia y sigue la pestaña
  activa. Informa
  de dimensiones/megapíxeles, capas visibles, texto, máscaras, grupos, buffers
  únicos de capas+cachés+historial, tamaño real del último `.imago` (o estimación
  sin comprimir), efectos activos y los de mayor coste. Señala lienzos
  de 20 MP, 50 capas, más de 512 MiB o efectos caros antes de operaciones pesadas.
  No renderiza, convierte ni comprime imágenes. No tiene `QTimer`: al editar
  visible solo marca «Actualizar •» y oculto no mantiene conexiones. Medición en
  Windows 11 con 200 capas y 1.000 pasos de historial: mediana de 2,323 ms y
  máximo de 2,411 ms por actualización manual. La apertura mantuvo idéntico el
  tamaño mínimo de MainWindow (1014×860 en el smoke headless). Cubierto por 4
  regresiones de lectura sin píxeles, memoria compartida/tamaño de proyecto,
  ciclo oculto e independencia de ventana, además de la suite completa de 105
  pruebas (3 POSIX omitidas en Windows).
- [ ] **Gestor de recuperaciones.** En vez de una única pregunta global al
  arrancar, listar cada copia con nombre, fecha, miniatura y ruta original para
  abrirla, descartarla o conservarla individualmente.

## Pendiente (sin fecha)

- [ ] **Capas de ajuste no destructivas** ⭐ PROYECTO GRANDE — Ya existe toda
  la maquinaria: el `compute(arr)` de cada ajuste es una función pura. Una
  `AdjustmentLayer` que guarde clave+parámetros y aplique el `compute` al
  componer. Diferenciador enorme frente a Paint.NET. Requiere: nueva clase en
  `models/layer.py`, composición en `widgets/canvas.py`, doble clic para
  reeditar, serialización en `.imago`, undo. APARCADO por rendimiento: un
  ajuste que depende del COMPUESTO inferior obliga a recalcular por píxel en
  el bucle de composición (la lentitud que obligó a retirar el primer
  intento). Solo retomar con un diseño de caché sólido y MEDICIONES.
- [ ] **Opacidad y modo de fusión por GRUPO de capas** (fase 2 de los grupos) —
  Exigiría componer el grupo a un buffer intermedio: hacerlo solo con
  medición previa (es la misma puerta a la lentitud de las capas de ajuste).
- [ ] **Vista previa de la varita al pasar el ratón** — Resaltar la región que
  se seleccionaría antes de hacer clic. Caro de hacer bien (recalcular el
  flood fill en cada movimiento); valorar un retardo o resolución reducida.
- [ ] **Transferencia de estilo (IA)** — Fast neural style: modelos ONNX de
  ~7 MB. Probar calidad antes de cablear (regla de la casa para la IA).
- [ ] **Escritura AVIF/HEIC/JXL** — Hoy solo lectura (vía plugins opcionales
  de Pillow); la escritura iría por la misma vía.
- [ ] **Iconos opcionales pendientes** — `selection_border.png`,
  `fx_polar.png`, `fx_frosted.png`, `fx_crystallize.png`, `fx_duotone.png`
  (las acciones salen sin icono; al añadirlos, `python generar_recursos.py`).

## Descartados (no retomar sin resolver lo indicado)

- **Anonimizar caras/matrículas** — la detección fallaba con fotos borrosas;
  haría falta un detector de matrículas de verdad (no la cascada de OpenCV).
- **Zero-DCE (poca luz)** — iluminaba demasiado y no hay dónde alojar el
  .onnx (sin cuenta propia de Hugging Face).
- **Deblur (NAFNet)** — costuras y calidad floja; sin alternativa ligera
  redistribuible convincente.
