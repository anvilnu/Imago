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

- [ ] **Identificar cambios de autoguardado por revisión, no por índice de
  `QUndoStack`.** Tras deshacer del índice 5 al 4 y crear una rama alternativa
  que vuelve al 5, el contenido es distinto pero el autoguardado cree que no
  cambió. Mantener un contador monotónico de revisión o una identidad de estado
  independiente del índice. Escribir `session.json` atómicamente y no podar la
  última copia válida hasta confirmar la nueva.

- [ ] **Respetar grupos y efectos al exportar animaciones.**
  `frames_de_capas()` usa `layer.visible` en lugar de
  `visible_efectiva(layer)` y `render_image()` en lugar del render con efectos;
  una capa dentro de un grupo oculto todavía se exporta y los efectos pueden
  desaparecer. Unificar la precomprobación, preview y exportación con la misma
  función de render de fotograma.

- [ ] **Unificar la identidad de QSettings y el traductor de Qt.** Los ajustes
  usan `app_paths.settings()` (`MiEstudio/Imago` o INI portable), pero el
  traductor lee un `QSettings()` ligado a `AVNSoft/Imago`. El idioma propio
  puede cambiar sin que cambien los textos nativos de Qt, y el modo portable
  queda ignorado. Leer siempre mediante `app_paths.settings()` y decidir una
  única organización para ajustes y `QStandardPaths`, con migración de valores
  existentes si se cambia.

### Rendimiento y memoria

- [ ] **Actualizar miniaturas solo cuando cambie el documento.** La miniatura
  activa recompone y reduce todo el lienzo cada 1,2 segundos aunque nada haya
  cambiado. Sustituir el sondeo periódico por una revisión/dirty flag, limitar
  la frecuencia durante un trazo y reutilizar el último compuesto o una caché
  reducida. Medir documentos grandes con muchas capas y efectos.

- [ ] **Evitar matrices de imagen completa al iniciar herramientas locales.**
  Dedo, Licuar, Esponja y Sobreexponer/Subexponer convierten la capa completa y
  crean buffers `float32`; una imagen RGBA de 4000×5000 ocupa ~80 MB en
  `uint8` y ~320 MB por copia `float32`, con picos que pueden superar 500 MB.
  Trabajar por teselas/ROI alrededor del trazo o mantener un buffer compartido
  con copia diferida. Revisar también coberturas completas de pincel,
  aerógrafo y clonado.

- [ ] **Pasar el rectángulo sucio conocido a `PaintCommand`.** El comando
  guarda únicamente el parche, pero para encontrarlo crea una comparación
  booleana de toda la imagen al soltar cada trazo (~80 MB adicionales en una
  imagen RGBA de 20 MP). Las herramientas ya conocen normalmente la zona
  tocada: admitir un `dirty_rect` opcional y conservar `_diff_rect` como
  respaldo para operaciones que no puedan proporcionarlo.

- [ ] **Sacar autoguardado, guardado y exportaciones pesadas del hilo GUI.**
  El `QTimer` de autoguardado comprime secuencialmente todas las capas en el
  hilo de interfaz cada tres minutos; guardar, cargar y algunos exports hacen
  lo mismo. Crear una instantánea coherente y desasociada del documento en el
  hilo GUI y comprimir/escribir en un worker, con cancelación, progreso y una
  sola operación de E/S pesada por documento.

- [ ] **Medir y presupuestar las previews y efectos de capa.** La preview
  reducida y el debounce existentes son buenos, pero Aceptar recalcula a
  resolución completa en el hilo GUI y cualquier cambio de píxeles invalida
  la caché completa de efectos de la capa. Medir por efecto y tamaño; mover
  los finales pesados a workers y estudiar cachés por región antes de retomar
  capas de ajuste u opacidad de grupos.

- [ ] **Reducir copias en el IPC de IA y hacer rápida la cancelación.** Los
  arrays grandes se serializan entre procesos y duplican memoria. Valorar
  memoria compartida o archivos mapeados para entrada/salida. Durante la
  espera inicial del worker, comprobar cancelación en vez de poder esperar
  hasta 120 segundos; cerrar Imago debe cancelar y terminar los procesos sin
  bloquear la salida.

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

- [ ] **Indicador de autoguardado verificable.** Mostrar estado «guardando»,
  hora de la última copia confirmada y error persistente si no pudo escribirse;
  no comunicar éxito antes del `os.replace()` final.
- [ ] **Diagnóstico opcional del documento.** Un panel pequeño con dimensiones,
  capas, memoria estimada, efectos caros y tamaño aproximado del proyecto
  ayudaría a explicar lentitud antes de una operación pesada.
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
