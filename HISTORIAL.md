# Historial de lo implementado en Imago (hasta la 1.0, jul 2026)

Copia de la hoja de ruta ORIGINAL con todo el detalle de lo implementado
(decisiones, gotchas y mediciones). La hoja de ruta viva, con solo lo
pendiente, es ROADMAP.md.

# Hoja de ruta de mejoras de Imago

Lista de funciones sugeridas tras comparar Imago con Paint.NET, GIMP, Krita y
Photopea (julio 2026). Ir marcando `[x]` según se implementen.

**Orden acordado:**
1. Tanda rápida: más modos de fusión + auto-niveles + selección de borde.
2. Herramientas nuevas: Sobreexponer/Subexponer (Dodge & Burn) y Pincel corrector.
3. Proyecto grande: capas de ajuste no destructivas.
4. El resto, según apetezca.

---

## 1. Victorias rápidas (encajan directo en la arquitectura actual)

- [x] **Más modos de fusión de capas** — HECHO (jul 2026): 13 modos en el combo
  (se añadieron Adición, Luz suave, Luz fuerte, Diferencia y Exclusión). La
  serialización ya guardaba el valor del enum y el importador PSD ya los mapeaba.
  Además, el modo ahora está A LA VISTA: combo "Modo:" arriba del panel de
  Capas (deshacible, sincronizado con capa/pestaña/undo) y doble clic en una
  capa abre sus Propiedades.
- [x] **Auto-niveles / auto-contraste / auto-color** — HECHO (jul 2026): el
  antiguo Auto-contraste (que estiraba por canal) pasó a ser Auto-niveles;
  Auto-contraste ahora es estirado uniforme (no altera el color) y Auto-color
  neutraliza la dominante ("mundo gris"). Los tres en Ajustes ▸ Automático.
- [x] **Selección ▸ Borde** — HECHO (jul 2026): anillo de N px centrado en el
  contorno (`border_selection` en `widgets/canvas.py`), en Edición ▸ Refinar
  selección. Pendiente opcional: icono propio `selection_border.png` (ahora
  sale sin icono; al añadir el PNG ejecutar `python generar_recursos.py`).
- [x] **Exportar a PDF** — HECHO (jul 2026): Archivo ▸ Exportar ▸ PDF
  (`export_pdf` en `main.py`, con `QPdfWriter`): la página mide EXACTAMENTE lo
  que la imagen según sus PPP (sin papel ni márgenes; distinto de Imprimir ▸
  PDF, que centra en una hoja). Pendiente opcional: icono `exportar_pdf.png`.
- [x] **Importar SVG rasterizado** — HECHO (jul 2026): al abrir un `.svg`/
  `.svgz`, `SvgSizeDialog` (en `new_dialog.py`) pregunta el tamaño (por
  defecto el declarado, proporción enlazada) y `_open_svg` lo rasteriza con
  `QSvgRenderer` sobre fondo transparente. El lienzo queda sin archivo
  asociado (nunca se pisa el SVG original).
- [x] **Muestras de color personalizadas** — HECHO (jul 2026): fila "Muestras
  propias" en el panel de color con `+` (guarda el primario, sin duplicados,
  tope 96) e `…` (importa `.gpl` de GIMP). Clic = primario; clic derecho =
  menú (secundario / eliminar). Persisten en QSettings
  (`colors/custom_swatches`, hex ARGB separados por comas).
- [x] **Efectos clásicos que faltan** — HECHO (jul 2026), en `adjustments.py`:
  - [x] Coordenadas polares (Efectos ▸ Distorsionar; rectangular ↔ polar)
  - [x] Cristalizar / Voronoi (Efectos ▸ Estilizar; semilla fija por celda
        con jitter, vecindario 3×3)
  - [x] Vidrio esmerilado (Efectos ▸ Distorsionar; dispersión aleatoria
        determinista)
  - [x] Duotono / tritono (Ajustes ▸ Blanco y negro; 2-3 tintas por
        luminosidad, tinta intermedia opcional)
  Pendiente opcional: iconos `fx_polar.png`, `fx_frosted.png`,
  `fx_crystallize.png`, `fx_duotone.png` (salen sin icono; al añadirlos,
  `python generar_recursos.py`).

## 2. Herramientas nuevas (esfuerzo medio)

- [x] **Sobreexponer / Subexponer (Dodge & Burn)** — HECHO (jul 2026):
  `tools/dodge_burn_tool.py`, atajo O. Modo (aclarar/oscurecer, Ctrl lo
  invierte), rango tonal (sombras/medios/luces), exposición y dureza. El
  efecto no se acumula al repasar dentro de un mismo trazo.
- [x] **Esponja** — HECHO (jul 2026): `tools/sponge_tool.py`, atajo Y (nació
  con X, pero X ya era Intercambiar colores y el duplicado dejaba ambos
  atajos mudos; corregido en la revisión de atajos de la 1.0), con el
  molde de `dodge_burn_tool.py`. Modo Desaturar (interpola hacia el gris de
  LUMINOSIDAD: conserva el brillo percibido) o Saturar (aleja el color del
  gris), Ctrl invierte el modo, Flujo y Dureza en la barra; sin acumular
  dentro del trazo (máscara por máximo) y respetando la selección.
- [x] **Pincel corrector (spot healing)** — HECHO (jul 2026):
  `tools/heal_tool.py`, atajo J. Se pinta la imperfección (resaltada en azul)
  y al soltar se reconstruye con `cv2.inpaint` (Telea). Import de cv2
  perezoso: sin OpenCV avisa una vez y no rompe nada.
- [x] **Herramienta de medición** — HECHO (jul 2026): `tools/measure_tool.py`,
  atajo Q. Arrastrar mide (Shift = 15°); distancia, ángulo y ΔX/ΔY en vivo en
  la barra de opciones y la de estado, en px/cm/in (combo "Unidades", misma
  convención de 96 PPP que las reglas, `RulerOverlay.DPI`). Los extremos se
  reajustan arrastrándolos; Esc borra. No pinta ni toca el historial.
  De paso llegó **Línea / Curva** (jul 2026, atajo K, no estaba en la lista):
  recta de 4 nudos estilo Paint.NET con spline/Bézier/segmentos, asa de mover,
  giro con botón derecho y terminaciones (flecha/círculo/barra por extremo).
- [x] **Sesgar/perspectiva en la caja de transformación** — HECHO (jul 2026):
  `MoveTool` gana distorsión libre por esquinas. **Ctrl + arrastrar una esquina**
  la distorsiona; **sin Ctrl** los 8 tiradores escalan y la corona rota, como
  siempre. La deformación se guarda en ESPACIO OBJETO (`local_corners`) y se
  compone DEBAJO de la afín (`display = Q·afín`, vía `QTransform.quadToQuad`),
  así mover/escalar/girar afines siguen operando sobre la forma ya deformada
  (nada de modos exclusivos: conviven). Todo el pipeline pasa por
  `_display_transform()`, de modo que recompose/márgenes/selección heredan la
  perspectiva sin tocarse. Deshacible como "Distorsionar"; las esquinas objeto
  viajan en el snapshot de sesión (undo/redo las restaura).
- [x] **Licuar (warp push)** — HECHO (jul 2026): `tools/liquify_tool.py`,
  atajo Z. Forward-warp básico: cada paso corto del trazo re-muestrea la
  región del pincel HACIA ATRÁS con interpolación bilineal numpy sobre el
  estado actual (deformación acumulada suave, sin desgarros), en alfa
  PREMULTIPLICADO (bordes transparentes sin halos; con la transparencia
  bloqueada solo deforma el color). Fuerza y Dureza en la barra; selección
  respetada; un paso de deshacer por trazo.

### Mejoras de los pinceles (revisión jul 2026)

- [x] **Lápiz: línea recta con Mayús** — HECHO (jul 2026): Mayús+clic traza
  una línea de Bresenham desde el final del último trazo (mismo
  `_last_end_point` que el pincel, que el lápiz ya heredaba en el release).
- [x] **Avisar cuando la goma no actúa por bloqueo de alfa** — HECHO
  (jul 2026): mensaje de 4 s en la barra de estado
  (`status.eraser_alpha_lock`) en vez de fallar en silencio.
- [x] **Opacidad del trazo del pincel** — HECHO (jul 2026): slider "Opacidad"
  en el panel del pincel (`canvas.brush_opacity`), independiente del alfa del
  color; el motor de cobertura la aplica al recomponer (cobertura ×
  opacidad), uniforme aunque el trazo se solape. Con un patrón de relleno el
  slider se deshabilita (los patrones no pasan por el motor de cobertura).
- [x] **Alt+clic = cuentagotas temporal en los pinceles** — HECHO (jul 2026):
  pincel, lápiz y aerógrafo capturan color con Alt+clic (izq=primario,
  der=secundario) vía `BaseTool._alt_pick_color`, que delega en la lógica del
  cuentagotas (sin lupa). La goma queda fuera a propósito (no pinta con color).
- [x] **Lupa del cuentagotas con colores del tema** — HECHO (jul 2026):
  `_LoupeWidget` lee los tokens de `theme.py` al pintar (fondo, borde, texto);
  el marcador del píxel central conserva el doble borde negro/blanco fijo
  (debe verse sobre cualquier color).

### Mejoras de recorte, texto, formas y pluma (revisión jul 2026)

- [x] **Clic para editar cualquier capa de texto** — HECHO (jul 2026):
  hit-test de todas las capas de texto visibles (de arriba abajo) en
  `TextTool.mouse_press`; la capa tocada pasa a ser la activa y se abre su
  editor con un solo clic.
- [x] **Relación de aspecto fija en el recorte** — HECHO (jul 2026): combo
  "Proporción" (Libre / 1:1 / 4:3 / 16:9 / verticales…) en la barra del
  recorte (`canvas.crop_ratio`). Restringe al crear la caja (manda sobre
  Mayús) y al redimensionar (esquinas anclan la opuesta; lados centran el
  otro eje), y cambiar el combo reencaja la caja ya dibujada en el acto.
- [x] **Reubicar las guías tras recortar** — HECHO (jul 2026): `CropCommand`
  desplaza las guías por el origen del recorte y descarta las que queden
  fuera; deshacer las repone todas.
- [x] **Capas de texto en el RESTO de operaciones de imagen completa** —
  HECHO (jul 2026): redimensionar escala origen y TAMAÑOS DE FUENTE (por el
  factor vertical; el texto sigue vectorial y editable); tamaño de lienzo
  desplaza el origen con el offset; voltear y rotar 90/180 recolocan la CAJA
  del texto en su posición reflejada/girada manteniendo el contenido
  horizontal y legible (espejar/girar las letras exigiría rasterizar — se
  decidió transformar el origen, no rasterizar). Todo deshacible; Flip sigue
  siendo su propia inversa.
- [x] **Girar / texto vertical** — TERMINADO (jul 2026). Remate final de la
  herramienta de texto (misma tanda): (a) la caja de mover/girar del texto se
  anula con **Deseleccionar** (Ctrl+D/menú/botón; un clic sobre el texto la
  re-arma) y el desplegable Modo de mover se desactiva con capa de texto;
  (b) **edición EN VIVO**: al reeditar, la capa ya NO se oculta — el editor
  vuelca los cambios al instante (`_update_live_layer` en `text_tool.py`) y el
  lienzo enseña el render real (efectos de capa, interletraje, vertical y giro)
  mientras se escribe; el interletraje también se ve DENTRO del editor (visual,
  toHtml lo descarta); Esc/vaciar reponen la instantánea y el deshacer usa ese
  "antes". Fases originales:
  - Fase 1 (HECHA): `TextLayer.text_angle` — el texto se rinde GIRADO alrededor
    del centro de su caja (suave), SIGUE editable, persiste en `.imago` y el
    hit-test de clic-para-editar respeta el giro (`contains_point`/
    `get_text_transform`). Los efectos de capa funcionan sobre el texto girado.
  - Fase 2 (HECHA): girar/mover el texto con la herramienta **Mover** de forma
    NO destructiva (vía propia en `MoveTool` guardada por `is_text`, separada de
    la maquinaria de píxeles): corona = ángulo, interior = mover; caja de
    transformación girada; `TextTransformCommand` (deshacer por ángulo+origen).
    Editar en horizontal (un clic con Texto reabre el editor; el ángulo se
    conserva). Escalar→tamaño de fuente queda para después.
  - Fase 3 (HECHA): modo texto APILADO vertical (`TextLayer.text_vertical`):
    `_to_vertical` remaqueta cada carácter en su propio bloque centrado (conserva
    fuente/tamaño/color), `_build_doc` unifica horizontal/vertical, persiste en
    `.imago` y se combina con el giro. Toggle **⬍** en la barra de opciones de
    texto (`opt.tt.text_vertical`): se sincroniza al editar (`canvas.text_vertical`)
    y se aplica al confirmar (nuevo → `set_text`; existente → `EditTextLayerCommand`
    con old/new vertical, deshacible). El "de lado" sale con ángulo 90° (Fase 2).
    UI: checkbox **Vertical** en la barra de opciones de texto.
  - Interletraje (HECHO): `TextLayer.text_spacing` (px). Como el toHtml NO conserva
    el letter-spacing, se guarda aparte y se aplica al RENDER: en horizontal como
    letter-spacing absoluto (admite negativo), en vertical como line-height por
    bloque (hueco entre caracteres apilados, `setLineHeight(px, 4)`). El
    espaciado se aplica a todos los caracteres MENOS al último (si no, sobraba
    hueco y con negativo recortaba la última letra). Slider "Interletraje" con
    botones +/- en la barra de texto (`opt.tt.spacing`), sincronizado y aplicado
    al confirmar como `text_vertical`; deshacible y persistente en `.imago`.
- [x] **Cuadro de texto con ANCHO FIJO al pegar (tirador)** — HECHO (jul 2026):
  al PEGAR del portapapeles (Ctrl+V/menú; pensado para el texto del OCR), el
  cuadro pasa a ancho fijo con un TIRADOR en el borde derecho: arrastrarlo fija
  el ancho y el texto REFLUYE envolviéndose (el alto se autoajusta); el ancho
  inicial se acota a lo que queda de lienzo. El texto TECLEADO no cambia: cuadro
  automático como siempre, sin tirador. `TextLayer.text_box_width` (0 = auto;
  en vertical se ignora), persistente en `.imago`, deshacible
  (`EditTextLayerCommand`), se conserva al reeditar/duplicar y escala con
  Redimensionar imagen (factor horizontal). De paso, DUPLICAR una capa de texto
  ahora copia también giro/vertical/interletraje (antes solo html+origen).

### Mejoras de Mover/transformación (revisión jul 2026)

- [x] **Escalar anclando el lado/esquina opuesta** — HECHO (jul 2026): el lado
  contrario al tirador queda clavado (estilo Paint.NET/Photoshop) y con Alt se
  escala desde el centro (se puede alternar a mitad de gesto). Todo se calcula
  desde el estado del press en `_apply_scale_drag`, compensando `tx/ty`.
- [x] **Volteo con escala negativa** — HECHO (jul 2026): `_clamp` conserva el
  signo, así que cruzar el ancla con un tirador refleja la imagen (espejo) en
  vivo; re-agarrar un flotante ya volteado sigue funcionando.
- [x] **Feedback numérico en vivo** — HECHO (jul 2026): en la barra de estado
  durante el gesto: tamaño (W × H px) al escalar, ángulo al rotar y
  desplazamiento al mover (también con las flechas).
- [x] **Flechas para mover la marquesina** — HECHO (jul 2026):
  `MoveSelectionTool` mueve 1 px (Shift = ×10) y las ráfagas consecutivas se
  fusionan en una entrada del historial (`NudgeSelectionCommand`).

### Mejoras de las herramientas de selección (revisión jul 2026)

- [x] **Tamaño en vivo al arrastrar** — HECHO (jul 2026): "Tamaño: W × H px"
  en la barra de estado durante el arrastre (rectángulo, elipse y lazo), desde
  `_update_live_marquee`; se limpia al soltar.
- [x] **Relación fija / tamaño fijo** — HECHO (jul 2026): combo en el panel de
  selección (Normal / Relación fija / Tamaño fijo). Relación fija ofrece
  presets (1:1, 4:3, 16:9, verticales…) y «Personalizada» (dos spins W:H);
  Tamaño fijo usa spins en px exactos (basta un clic) con valores propios
  independientes de la proporción. Aplicado en `_drag_rect`; solo visible en
  rectángulo/elipse. De paso se corrigió que un arrastre iniciado exactamente
  en (0,0) no funcionara (QPoint(0,0) es falsy: los checks ahora usan
  `is not None`).
- [x] **Espacio para reposicionar sobre la marcha** — HECHO (jul 2026):
  Espacio mantenido durante el arrastre mueve la caja (o el lazo) en curso;
  al soltarlo se sigue redimensionando. El canvas consulta
  `wants_space_key()` para no activar la mano temporal en pleno arrastre.
- [x] **Lazo poligonal** — HECHO (jul 2026): combo "Trazado" en el panel del
  lazo (Mano alzada / Poligonal). Clic a clic, doble clic o Intro cierra,
  Esc cancela y restaura la selección previa.
- [x] **Selección ▸ Crecer / Seleccionar parecido** — HECHO (jul 2026): en
  Edición ▸ Refinar selección, con la tolerancia de la varita (por canal,
  rango [mín−tol, máx+tol] de los colores seleccionados, como Photoshop);
  `build_similar_mask` en `tools/numpy_utils.py` + `grow_selection`/
  `select_similar` en el canvas. Sin cambios que añadir avisa en la barra de
  estado y no ensucia el historial.
- [ ] **Vista previa de la varita al pasar el ratón** — Resaltar la región que
  se seleccionaría antes de hacer clic. Caro de hacer bien (recalcular el
  flood fill en cada movimiento); valorar un retardo o resolución reducida.

## 3. Capas (más ambicioso, lo que más distancia marca)

- [ ] **Capas de ajuste no destructivas** ⭐ PROYECTO GRANDE — Ya existe toda
  la maquinaria: el `compute(arr)` de cada ajuste es una función pura. Una
  `AdjustmentLayer` que guarde clave+parámetros y aplique el `compute` al
  componer. Diferenciador enorme frente a Paint.NET. Requiere: nueva clase en
  `models/layer.py`, composición en `widgets/canvas.py`, doble clic para
  reeditar, serialización en `.imago`, undo.
- [x] **Efectos de capa no destructivos** ⭐ PROYECTO GRANDE -- HECHO (jul    2026) —
  Sombra paralela, trazo, resplandor… como PARÁMETROS pegados a la capa que el
  compositor recalcula a partir de los píxeles de ESA MISMA capa. El texto sigue
  editable y el efecto se actualiza solo al editarlo (adiós a rasterizar para
  ponerle sombra/trazo). Prima hermana de las capas de ajuste, pero SIN su
  problema de lentitud: un efecto depende SOLO de su propia capa (no del
  compuesto inferior), así que se cachea por capa (clave = cacheKey del render +
  huella de efectos) y solo se recalcula cuando esa capa cambia; un trazo en otra
  capa no lo toca. Cómputo acotado a la bbox del contenido + padding (nunca a
  pantalla completa); el desenfoque (lo caro) solo sobre el alfa y cacheado
  aparte (mover offset/color/opacidad no re-desenfoca). Undo baratísimo (guarda
  params, no píxeles). REGLA DE ORO: el efecto debe ser AUTORREFERENTE (nunca
  leer lo que hay debajo); en cuanto dependa del fondo (knockout, blend-if)
  reaparece la lentitud de las capas de ajuste → fuera del MVP.
  - Fase 1 (EN CURSO): modelo `Layer.effects` + clase `Sombra` +
    `Layer.render_with_effects()` con caché por capa. Probado a mano.
  - Fase 2: enganchar el compositor (`canvas.py`, usar `render_with_effects()`)
    y sumar la huella de efectos al `state` de la caché.
  - Fase 3 (HECHA): overlay `EffectDialog`/`SombraDialog`
    (`widgets/layer_effects_ui.py`) reusando `OverlayPanel`; preview en vivo GRATIS
    vía el compositor (mutar el efecto + `canvas.update()`); Aceptar/Cancelar con
    snapshot. Se adelantó el comando de undo `LayerEffectsCommand`
    (`models/layer_commands.py`, deshace por PARÁMETROS) porque Aceptar lo necesita.
    Abridor `_open_layer_effect` (NO rasteriza el texto) + entrada temporal
    Capas ▸ Efectos de capa ▸ Sombra paralela (reabre la sombra existente).
  - Fase 4 (HECHA): sublista "fx" en el panel de Capas
    (`widgets/layers_panel.py`): un renglón por efecto bajo su capa con casilla de
    activo, nombre (clic = editar overlay) y botón de quitar; botón "fx" en la
    botonera para añadir. Togglear/quitar pasan por `LayerEffectsCommand` (undo).
    Registro tipo→diálogo/nombre en `layer_effects_ui` (`dialog_para_efecto`,
    `nombre_efecto`) y `open_layer_effect_editor` en el mixin. Jubilada la entrada
    de menú Capas ▸ Efectos de capa. (El icono `layer_fx.png` ya existe, jul 2026,
    junto con los submenús Capas ▸ Efectos de capa y Modo de fusión.)
  - Fase 5 (HECHA): persistencia en `.imago` (`models/project_io.py`): cada capa
    guarda `effects` como JSON en el manifest (píxeles CRUDOS, el efecto se
    re-aplica al abrir); la carga reconstruye con `crear_efecto`, ignorando tipos
    desconocidos (compat con `.imago` más nuevos). El autoguardado lo hereda.
  - Fase 6 (HECHA): **8 efectos**: **Sombra paralela**, **Sombra interior**
    (borde interno desplazado+difuminado), **Resplandor exterior** (silueta
    difuminada centrada; comparte `_silueta_desenfocada` con la sombra),
    **Trazo/contorno** (transformada de distancia), **Bisel/relieve** (mapa de
    altura por distancia + iluminación por gradiente/normal), **Satinado**
    (interferencia de la silueta desplazada en dos sentidos), **Superposición de
    color** y **Superposición de degradado** (`QLinearGradient` a un ángulo). Las
    dos vías de composición están cubiertas: `render_below` (sombra, resplandor,
    trazo) y `render_above` recortado al alfa (interior, bisel, satinado, color,
    degradado). El menú "fx" y los registros son genéricos
    (`_EFECTOS`/`efectos_disponibles`/`layer_effect_add(tipo)`), así que un efecto
    nuevo es enchufar clase (`fingerprint`/`to_dict`/`render_below` o
    `render_above`) + controles + una línea en `_EFECTOS`. Todos persisten en
    `.imago`. La miniatura del panel usa `render_with_effects()`.
  - Fase 7 (HECHA): **panel UNIFICADO** estilo "Estilo de capa" de Photoshop
    (`EfectosDialog`, un `OverlayPanel` anclado al lienzo): a la izquierda los 8
    efectos con casilla (activar/desactivar), a la derecha los controles del
    seleccionado (`QStackedWidget` de `EffectControls`). Uno de cada tipo, una
    sola preview y un solo Aceptar/Cancelar (un `LayerEffectsCommand`). Tocar un
    control auto-activa su efecto. El botón fx (y clic en la sublista) abren este
    panel con el efecto elegido seleccionado. Los antiguos overlays por efecto se
    jubilaron; los controles se reutilizan tal cual en `EffectControls`.
- [x] **Los efectos de capa sobreviven a rasterizar y fusionar** — HECHO
  (jul 2026): rasterizar una capa de texto (p. ej. para aplicar un Ajuste)
  traspasa sus efectos VIVOS (clonados) a la capa de píxeles, junto con el
  grupo y frame_delay (antes se perdían en silencio); Fusionar hacia abajo
  HORNEA los efectos de ambas capas con `render_with_effects()` (el resultado
  se ve igual que antes de fusionar) y el deshacer los repone. Nueva acción
  **Capas ▸ Fusionar los efectos en la capa** (`MergeEffectsCommand`, también
  en el menú del botón fx del panel): hornea los fx de la capa activa en sus
  píxeles y vacía la sublista; con texto rasteriza a la vez (confirmación).
- [x] **Grupos de capas** — HECHO (jul 2026) — Carpetas anidables en el panel de
  capas, SOLO organización a propósito (sin opacidad/fusión propias del grupo:
  eso exigiría componer a buffer intermedio, y es la puerta a la lentitud de
  las capas de ajuste). Cero coste de render: la lista plana `canvas.layers`
  sigue siendo la fuente de verdad (pintado/undo intactos) y el grupo es solo
  una referencia `layer.group` → árbol de `LayerGroup` (`models/layer.py`);
  la composición usa la visibilidad EFECTIVA (capa Y sus carpetas). Cabeceras
  con plegado, ojo y menú contextual (renombrar/desagrupar/duplicar/mover/
  eliminar) en el panel; botón ▣ agrupa la selección; arrastrar dentro/fuera
  reasigna carpeta (regla del "grupo común de los vecinos", que garantiza la
  contigüidad de los miembros). Serializado en `.imago` retrocompatible.
  Pendiente para una fase 2 (con medición): opacidad/modo de fusión de grupo.
- [x] **Máscara de recorte (clipping mask)** — HECHO (jul 2026): Capas ▸
  Máscara de recorte (checkable, Ctrl+Alt+G como en PS). `layer.clipped`: la
  capa se ve solo donde su BASE (la primera no recortada por debajo) tiene
  píxeles; varias recortadas consecutivas comparten base y base oculta =
  recortadas ocultas. RENDIMIENTO: el recorte se aplica AL COMPONER con un
  buffer temporal del tamaño del RECT SUCIO (DestinationIn contra
  `base.render_image()`, sin efectos de la base) — coste acotado, nada
  por-píxel dependiente del compuesto; capas no recortadas, coste cero (un
  getattr). Cubierto en: compositor de pantalla, `render_flat_image`
  (helper `render_recortada` en `models/layer.py`), fusionar hacia abajo
  (hornea el recorte), histograma en vivo, export ORA (horneado al alfa) y
  `.imago` retrocompatible. Deshacible por parámetro (`ClipLayerCommand`);
  el panel marca la capa con "↳". De paso, la caché de composición ahora
  también invalida por el cacheKey de la MÁSCARA de cada capa (faltaba).
- [x] **Bloqueo de píxeles / de posición por capa** — HECHO (jul 2026): dos
  casillas nuevas en Propiedades de capa (`layer.pixels_locked` /
  `position_locked`, undo vía `LayerPropertiesCommand` ampliado, persistidos
  en `.imago` y copiados al duplicar/rasterizar). Son PUERTAS en los puntos
  de entrada (coste cero en caliente): píxeles = las herramientas de pintado
  no arrancan (puerta única en `canvas.mousePressEvent` con
  `HERRAMIENTAS_DE_PIXELES`), y tampoco Ajustes/Efectos (`_open_adjustment`)
  ni borrar/rellenar selección; posición = Mover no agarra la capa (los
  objetos ya flotantes, p. ej. un pegado, sí se mueven). Aviso de 4 s en la
  barra de estado, como el de la goma con alfa bloqueado; candado 🔒 en la
  fila del panel.
- [x] **Capa nueva encima de la ACTIVA** — HECHO (jul 2026): `AddLayerCommand`
  inserta siempre en `activa + 1` (antes la capa vacía iba arriba del todo).
- [x] **Deshabilitar "Fusionar hacia abajo" con capas ocultas** — HECHO
  (jul 2026): botón del panel, menú Capas y guarda en `merge_layer_down`.
- [x] **Mostrar el modo de fusión en la fila del panel** — HECHO (jul 2026):
  "Capa 2 (Multiplicar, 75%)" cuando el modo no es Normal u opacidad < 100.

## 4. Formatos

- [x] **Exportar OpenRaster (.ora)** — HECHO (jul 2026): Archivo ▸ Exportar ▸
  OpenRaster (`save_ora` en `models/project_io.py`): mimetype (primera
  entrada, sin comprimir) + `stack.xml` (capas de arriba abajo, opacidad,
  visibilidad y composite-op svg:* mapeado desde los 13 modos de fusión) +
  PNG por capa + mergedimage.png + miniatura. Las máscaras se aplican al alfa
  y el texto se rasteriza (ORA no los tiene); es EXPORT (no asocia el lienzo).
- [x] **Abrir GIF/WebP animados como capas** — HECHO (jul 2026): al abrir un
  animado se pregunta (`_open_animated` en `main.py`); cada fotograma → una
  capa (de abajo arriba) con su duración en `layer.frame_delay` (que además
  se serializa en el `.imago`). Tope de 240 fotogramas. Si se responde que
  no, se abre solo el primero como siempre.
- [x] **Exportar GIF/WebP animado** — HECHO (jul 2026): Archivo ▸ Exportar ▸
  Animación GIF/WebP (`models/anim_io.py`, escribe Pillow, import perezoso): las
  capas VISIBLES son los fotogramas, con duración configurable
  (`AnimExportDialog`), opción de usar las duraciones originales y bucle.
  GIF se compone sobre blanco (sin alfa parcial); WebP conserva el alfa.
  Además, Ver ▸ Previsualizar animación (`AnimPreviewDialog`) reproduce
  esos mismos fotogramas en un diálogo (play/pausa, deslizador, duración)
  sin tocar el lienzo; todo Qt, no necesita Pillow.
- [x] **AVIF / HEIC / JXL** — HECHO (jul 2026), solo LECTURA: fallback
  `_cargar_via_pillow` en `cargar_imagen_orientada` (main.py) vía los
  paquetes OPCIONALES `pillow-heif` (avif/heic/heif) y `pillow-jxl-plugin`
  (jxl), import perezoso (anotados como opcionales en requirements.txt).
  Sin el plugin, un aviso dice qué paquete instalar; con él, las extensiones
  aparecen en el filtro de Abrir. Pendiente opcional: escritura.
- [x] **Visor de metadatos** — HECHO (jul 2026): Imagen ▸ Propiedades de
  imagen (`properties_dialog.py`): general (dimensiones, PPP, tamaño de
  impresión, capas, archivo y tamaño en disco), EXIF decodificado con Pillow
  desde `canvas.source_exif` (cámara, fecha, exposición, GPS con botón "Ver
  en el mapa" a OpenStreetMap) e histograma de luminosidad con los colores
  del tema. Icono `propiedades.png` añadido (jul 2026).

## 5. IA local (la infraestructura ONNX + runner ya existe)

- [ ] ~~**Anonimizar: pixelar caras/matrículas automáticamente**~~ — DESCARTADO
  (jul 2026) tras implementarlo y probarlo: la detección (YuNet + cascada Haar
  de matrículas de OpenCV) fallaba en cuanto la foto estaba un poco borrosa
  ("no se encontró nada" demasiado a menudo) y no compensaba mantenerlo. Si se
  retoma, hará falta un detector de matrículas de verdad (no la cascada) y
  bajar umbrales de YuNet con imágenes degradadas.
- [ ] ~~**Mejora de fotos con poca luz (Zero-DCE)**~~ — DESCARTADO (jul 2026)
  tras implementarlo y probarlo: iluminaba DEMASIADO (resultado lavado) y
  además no hay dónde alojar el .onnx (se convirtió localmente desde los pesos
  MIT de bsun0802/Zero-DCE; no hay cuenta propia de Hugging Face donde
  subirlo). Si se retoma: modular la intensidad (mezcla con el original o menos
  iteraciones de la curva) y resolver el hosting primero.
- [x] **OCR: extraer texto de la imagen** — HECHO (jul 2026): IA ▸ Extraer texto
  (OCR), sección nueva "Utilidades" (`ai/ocr.py`). PP-OCRv5 móvil con las
  conversiones ONNX OFICIALES de PaddlePaddle (Apache-2.0): detección DBNet
  (contornos con OpenCV; el "unclip" área/perímetro sustituye a pyclipper) +
  reconocimiento latino (34 idiomas, español incluido) con CTC voraz; el
  diccionario de 836 clases viaja EMBEBIDO en `_LATIN_DICT` (ojo: la clase 0 es
  el separador CTC y la última el espacio; el preprocesado es BGR+ImageNet para
  el det y BGR -1..1 para el rec — la conversión de monkt/paddleocr-onnx se
  descartó por rota). Opera sobre la imagen COMPUESTA, agrupa por líneas, copia
  al portapapeles y no toca el historial. Icono `ai_ocr.png` (jul 2026).
- [ ] ~~**Deblur (desenfoque inverso)**~~ — DESCARTADO (jul 2026): NAFNet dejaba
  costuras/calidad floja (ya se vio al elegir denoise) y no hay alternativa
  ligera redistribuible convincente.
- [ ] **Transferencia de estilo** — Fast neural style: modelos ONNX de ~7 MB.

## 6. Utilidades

- [x] **Procesamiento por lotes** — HECHO (jul 2026): Archivo ▸ Procesar por
  lotes... (`batch_dialog.py` + `batch_process` en `ventana/menu_archivo.py`):
  redimensionar (porcentaje o ajustar dentro de un máximo, con "solo reducir"),
  convertir de formato (mantener / PNG / JPEG / WebP / BMP / TIFF, con calidad),
  renombrar en secuencia (nombre base → `Fondo_001`, `Fondo_002`..., relleno de
  3 dígitos o más si hay >999) y marca de agua (texto con sombra de contraste o
  imagen PNG; 9 posiciones,
  opacidad y color blanco/negro/primario) sobre una carpeta entera, a otra
  carpeta. Corre FUERA del hilo GUI con un `InferenceRunner` PROPIO (no el de
  IA), cancelable entre archivo y archivo; NUNCA sobreescribe (numera _1,
  _2...), conserva los PPP y reincrusta el EXIF en JPEG→JPEG (`exif_utils`).
  Sin transformación alguna (solo renombrar/mover, manteniendo formato) hace
  COPIA DIRECTA byte a byte: idéntico en píxeles, peso y metadatos (sin pérdida
  generacional JPEG ni intercambio ancho×alto por la rotación EXIF); para
  recomprimir con el slider de calidad hay que elegir JPEG/WebP como salida.
  No necesita documento abierto. Icono `lote.png` añadido (jul 2026, junto con
  `propiedades.png`, `layer_mask.png` y los 4 `mask_*.png` del submenú).
- [x] **Histograma en vivo** — HECHO (jul 2026): panel EMPOTRADO en la columna
  derecha (`widgets/histogram_panel.py`; se probó también como overlay
  arrastrable y se decidió el panel, retirando el overlay). Orden por defecto:
  Histograma · Historial · Capas · Color, reordenable con ▲/▼; ALTO FIJO de
  156 px (`ALTO_HISTOGRAMA` en construccion_ui) que ni el separador estira —
  y como un maximumHeight en el ÚNICO hijo visible lo heredaría el
  right_splitter (el gotcha de Color), `_update_histogram_height_lock` suelta
  el máximo cuando el Histograma queda solo (el contenido conserva su alto y
  el hueco queda vacío) y lo re-fija al volver otro panel. Botón propio en la
  fila de toggles (icono `histogram_panel.png`) y canales Luminosidad / RGB
  superpuesto / R / G / B (fila "Canal:" compacta, como el "Modo:" de Capas).
  Canal, visibilidad y orden persisten (`histogram/canal`, `panels/histogram`,
  `panels/right_order`, con migración del orden guardado antiguo).
  INTERACTIVO en modo lectura (jul 2026): pasar el ratón marca el nivel
  ("Nivel N · X %") y arrastrar mide un rango resaltado ("Rango A–B · X %";
  clic seco lo quita). Todo dentro del widget (estado + repintado propios,
  ~1 ms): cero recálculos del histograma y cero impacto en el lienzo. En RGB
  superpuesto los porcentajes se leen sobre la luminosidad.
  RENDIMIENTO (la prioridad): nada enganchado al pintado ni a la composición —
  sondeo ligero a ~2,5 Hz que no corre oculto (coste cero), se salta los
  gestos con ratón pulsado, compara una HUELLA barata del documento (los
  campos de la caché de composición + máscaras) y solo si cambió recompone un
  MUESTREO ≤192 px (vecino más próximo: no lee megapíxeles). Medido con
  4000×3000 × 3 capas: huella 0,004 ms, refresco completo ~1,2 ms,
  independiente del tamaño del documento. Un `_reflotar` en ChildAdded evita
  que el contenido de una pestaña nueva lo entierre (cede la cima a los
  overlays de Ajustes).
- [x] **Cuadrícula de píxeles al hacer zoom ≥ 800 %** — HECHO (jul 2026). La
  cuadrícula de Ver ya ERA por píxel; lo que faltaba para pixel-art: (1) el
  umbral sube de 400% a 800% (con celdas de 4 px la línea se comía el 25% del
  ancho y falseaba los colores); (2) nueva **línea maestra de mosaico** (Ver ▸
  Mosaico de la cuadrícula: Ninguno / 8 / 16 / 32 / 64 px), más marcada y
  visible ya al 100%, para ver la estructura de sprite sheets/tilesets.
  Global como la cuadrícula, persistido en `view/grid_tile`, heredado por las
  pestañas nuevas y acotado al viewport (pen cosmético; coste nulo). De paso
  se corrigió un bug latente: el import local de QRect en `paintEvent` vivía
  dentro del branch del scroll area y un canvas suelto reventaba al pintar.
- [x] **PNG indexado al guardar** — HECHO (jul 2026). El diálogo de calidad
  del PNG ya ofrecía "8 bits paleta", pero usaba el Indexed8 de Qt (con >256
  colores tramaba a una paleta fija, con mala calidad). Ahora "8 bits" cuantiza
  de verdad con Pillow (`png8_bytes` en `utilidades.py`: FASTOCTREE sobre RGBA
  → paleta con ALFA; pixel-art con pocos colores = paleta exacta) con controles
  de **nº de colores** (256/128/64/32/16) y **difuminado Floyd-Steinberg**
  (para fotos); conserva los PPP (pHYs) y mapea el slider de compresión a zlib.
  La estimación de tamaño del diálogo usa la MISMA vía (es el tamaño real).
  Sin Pillow se cae al Indexed8 de Qt de siempre.

## 7. Deuda técnica (refactor, sin cambios funcionales)

- [x] **Desmenuzar main.py y options_bar.py en módulos** — HECHO (jul 2026),
  las 6 etapas en una tanda. Los métodos se movieron TAL CUAL (ni una línea de
  lógica cambió) a MIXINS que MainWindow/DynamicOptionsBar heredan; `self.*`
  sigue funcionando igual. Resultado: **main.py 5326 → ~1490 líneas** y
  **options_bar.py ~3150 → ~450**. Nuevos módulos:
  - De main.py, al paquete `ventana/` (junto con los mixins previos menu_ia y
    menu_ajustes): `menu_archivo.py`, `menu_edicion.py`,
    `menu_imagen_capas.py`, `menu_ver.py` (incluye zoom + barra de estado),
    `opciones_herramientas.py` (los ~60 `update_*`), `construccion_ui.py`
    (create_menus/create_docks/toolbar/bienvenida; la etapa 6 se hizo también
    como mixin, no como funciones constructoras: mismo orden de creación de
    atributos, menos riesgo) y `cursores.py`. En la raíz solo quedó
    `utilidades.py` (crear_icono, cargar_imagen_orientada —reexportada por
    main—, _canvas_thumb_pixmap: la comparten ventana/ y widgets/), y las
    clases de UI fueron a `widgets/tab_thumbnails.py` +
    `widgets/canvas_scroll.py`.
  - De options_bar.py: `widgets/opciones_dibujo.py`, `opciones_trazados.py`,
    `opciones_texto.py`, `opciones_seleccion.py` (mixins por familia).
  El único import circular se resolvió con `utilidades.py`, como estaba
  previsto; CRLF conservado en todo; PyInstaller/QSettings/i18n/plugins sin
  cambios. Verificado: py_compile + pyflakes limpio (los avisos que quedan son
  preexistentes/intencionados), smoke offscreen (todas las herramientas,
  pincel+undo/redo, guardar .imago, menús) y capturas en tema oscuro y claro.

- [x] **Volcado por PARCHE en las herramientas de retoque** — HECHO (jul 2026):
  Dedo, Licuar, Esponja y Sobre/Subexponer volcaban su preview reconvirtiendo
  la imagen ENTERA en cada movimiento del ratón (el des-premultiplicado float
  de 20 Mpx costaba ~1 s POR EVENTO en 4000×5000 con dedo/licuar). Ahora
  asignan la imagen de TRABAJO una vez al empezar el trazo y cada movimiento
  pinta in place solo el PARCHE sucio (bbox de los estampados desde el último
  volcado), como el pincel; el commit reutiliza esa imagen (sin otra
  reconversión entera). Medido en 4000×5000: dedo 1086→1 ms/movimiento,
  licuar 1056→3 ms, esponja/dodge 16→0 ms; soltar el trazo 1,1 s→~0,1 s. El
  coste que queda es el ARRANQUE del trazo (conversión float única: ~0,5 s
  dedo/licuar, ~0,25 s esponja/dodge), una vez por trazo.

## 8. Bugs a investigar

- [x] **`app.quit()` no sale de `app.exec()` con un documento modificado** —
  RESUELTO (jul 2026): NO ES UN BUG. Diagnóstico con `faulthandler`
  (volcado de pilas tras 6 s): en Qt 6, `app.quit()` no termina el bucle sin
  más — primero intenta CERRAR las ventanas, lo que dispara
  `MainWindow.closeEvent`; con un documento sucio, `closeEvent` muestra el
  diálogo MODAL "¿Guardar los cambios?" (`imago_warning`, main.py ~1490) y en
  offscreen no hay nadie que lo responda: el "cuelgue" era el diálogo
  esperando respuesta. Verificado por triple vía: documento limpio sale al
  instante; Qt pelado (sin closeEvent propio) sale; y auto-respondiendo
  "Descartar" al diálogo, `aboutToQuit` se emite y `exec()` vuelve con rc 0.
  Es el comportamiento DESEADO (salir por cualquier vía pregunta antes de
  perder cambios); no hay fuga ni bloqueo que arreglar. Para los smoke tests
  offscreen: documento limpio o parchear `imago_warning` para auto-responder.

- [x] **El texto CAMBIA de tamaño al validar/reeditar** — HECHO (jul 2026). Solo
  se notaba con **zoom ≠ 100%**. El editor trabaja a resolución de PANTALLA
  (`pixelSize = tamaño*zoom`), pero `commit_editing` guardaba `ed.toHtml()` TAL
  CUAL: se rasterizaba a `tamaño*zoom` px de LIENZO y el canvas lo mostraba a
  `tamaño*zoom²` → "crecía" ×zoom; al reeditar cargaba el html sin reescalar →
  "disminuía". Arreglado en `tools/text_tool.py`: (1) `commit_editing` guarda a
  resolución de lienzo (`_doc_at_canvas_resolution_from`, ÷zoom, como ya hacía
  `render_to_image`); (2) `_start_editor` reescala el html cargado a resolución de
  pantalla (×zoom) al reeditar. Lógica unificada en `_scale_doc_fonts(doc, factor)`
  (escala fragmentos + fuente por defecto), que ahora usan commit, reedición y
  `on_zoom_changed`. Resultado: el guardado es ESTABLE (siempre resolución de
  lienzo) y el render sale idéntico a cualquier zoom de edición.

- [x] **El texto pierde el color al vaciar el campo y reescribir** — HECHO
  (jul 2026). Escribiendo en un color (p. ej. rojo), si se BORRA TODO el texto y
  se reescribe, salía en el color por defecto del tema (casi blanco) y no admitía
  cambios. Causa: al vaciar el documento, Qt resetea el formato de entrada
  (`currentCharFormat().foreground()` -> `NoBrush`), así que lo siguiente se
  escribe sin color. Arreglado en `tools/text_tool.py`: se recuerda el último
  formato de carácter válido (`_remember_fmt`, capturado al crear, al cambiar
  formato y al mover el cursor) y, cuando el documento queda vacío
  (`_on_text_changed`, nuevo handler de `textChanged`), se repone con
  `setCurrentCharFormat`. Con ≥1 carácter nunca pasaba (el formato se conservaba).

## 9. Correcciones de la auditoría técnica posterior a la 1.0

- [x] **Fusionar hacia abajo sin alterar el aspecto** — HECHO (17-07-2026).
  `MergeDownCommand` ya no conserva la opacidad y el modo de fusión inferiores
  después de hornearlos: compone el par una vez sobre transparencia con las
  mismas reglas del lienzo (máscaras, efectos, opacidad, modos y recorte) y
  normaliza el resultado a 100 %, modo Normal y sin máscara/efectos/recorte.
  Esto corrige, entre otros casos, que una capa superior opaca terminara con
  alfa 127 al fusionarla sobre una inferior al 50 %. La capa resultante conserva
  el grupo y el resto de metadatos de la inferior; deshacer restaura también
  todas sus propiedades y la selección múltiple. La nueva comprobación común
  `visible_para_fusion()` impide fusionar capas que no aportan píxeles por un
  grupo o una base de recorte ocultos, y mantiene sincronizados lienzo, menú y
  panel. Cubierto por 4 regresiones headless y por la suite completa (47 pruebas
  en Windows; 3 casos POSIX se omiten condicionalmente en esa plataforma).
- [x] **Liberar los documentos al cerrar sus pestañas** — HECHO (17-07-2026).
  El nuevo `_retirar_y_destruir_pestana()` sustituye el `removeTab()` aislado:
  cancela previews, trabajos de IA y ediciones flotantes; corta las referencias
  de Capas, Historial, reglas y callbacks; separa el lienzo de su scroll y llama
  a `deleteLater()` sobre botón, marcador, scroll y lienzo. El mismo camino se
  usa al retirar automáticamente el lienzo inicial después de abrir un archivo.
  Dos regresiones con widgets Qt reales fuerzan `DeferredDelete` y comprueban
  tanto la destrucción completa como la conservación de la pestaña nueva. Suite
  completa: 49 pruebas en Windows; 3 casos POSIX omitidos condicionalmente.
  Corrección posterior: Capas desacopla ahora su callback, filas y miniaturas,
  y `HistoryPanel.detach()` es idempotente y libera sus referencias. Así, al
  abrir otra pestaña tras cerrar la última, una segunda desconexión no interrumpe
  `on_tab_changed()` antes de volver a enlazar las reglas (el fallo dejaba solo
  sus bandas vacías). Las llamadas repetidas salen ahora antes de volver a
  desconectar señales Qt, evitando también el `RuntimeWarning` de libpyside en
  la terminal. Cubierto por regresiones con paneles simulados y un
  `HistoryPanel` Qt real que trata el aviso como error; suite actual:
  66 pruebas en Windows, 3 POSIX omitidas condicionalmente.
- [x] **Contrato seguro y versionado para proyectos `.imago`** — HECHO
  (17-07-2026). El cargador valida completamente el manifiesto v1 antes de
  reservar imágenes: versión, esquema, tipos, dimensiones, memoria estimada,
  capas, guías, modos de fusión, grupos y referencias. El ZIP tiene límites por
  entrada y totales; las cabeceras PNG se comprueban antes de decodificarlas y
  cada capa/máscara debe medir exactamente lo mismo que el lienzo. Se rechazan
  ciclos de grupos, entradas duplicadas o desconocidas, máscaras corruptas,
  efectos no soportados y versiones futuras, evitando cuelgues y pérdida
  silenciosa al volver a guardar. `ErrorCargaProyecto` unifica los fallos con
  mensajes ES/EN/FR. Cubierto por 10 regresiones, incluida una ida y vuelta con
  el guardador real; suite completa: 59 pruebas en Windows, 3 POSIX omitidas.
- [x] **DPI persistente y deshacible** — HECHO (17-07-2026). Los proyectos
  `.imago` guardan ahora `canvas.dpi`; el cargador lo valida y conserva 96 PPP
  como valor por defecto para archivos v1 anteriores. Cambiar tamaño y PPP usa
  un único `ImageResizeCommand`, por lo que deshacer/rehacer restaura a la vez
  dimensiones, capas, máscaras, selección y resolución. Cambiar solo PPP crea
  también un paso de Historial y deja el documento pendiente de guardar, pero
  al ser únicamente metadato no retiene copias de todas las imágenes. Los textos
  de Historial distinguen cambio de tamaño, cambio de resolución y operación
  combinada en ES/EN/FR. Cubierto por 4 escenarios de regresión; suite completa:
  60 pruebas en Windows, 3 POSIX omitidas condicionalmente.
- [x] **Revisión monotónica para el autoguardado** — HECHO (17-07-2026).
  `AutoSaveManager` ya no identifica el contenido por `QUndoStack.index()`, que
  puede repetirse al deshacer y crear una rama nueva. Cada lienzo incrementa
  `revision_autoguardado` en nuevos comandos, deshacer y rehacer, y solo actualiza
  la revisión de la última copia cuando `save_project()` confirma el éxito. La
  publicación atómica de `session.json` y la poda posterior se mantienen: un
  fallo conserva el manifiesto y las copias recuperables anteriores. Cubierto
  por una regresión que alcanza el mismo índice mediante dos ramas distintas;
  suite completa: 62 pruebas en Windows, 3 POSIX omitidas condicionalmente.
- [x] **Animaciones coherentes con grupos y efectos** — HECHO (17-07-2026).
  La precomprobación de Exportar, la preview y la escritura GIF/WebP comparten
  ahora `capas_de_animacion()`/`frames_de_capas()`: una carpeta oculta excluye
  también los fotogramas de sus subgrupos y cada capa se rasteriza mediante
  `render_with_effects()`, conservando máscara, efectos, opacidad y duración.
  Tres regresiones comprueban grupos anidados, visibilidad individual y que el
  píxel exportado procede del resultado con efectos; suite completa: 65 pruebas
  en Windows, 3 POSIX omitidas condicionalmente.
- [x] **Identidad única de ajustes y traducciones Qt** — HECHO (17-07-2026).
  `AVNSoft/Imago` gobierna ahora tanto `QSettings` como `QStandardPaths`, evitando
  que el idioma propio y los textos nativos de Qt lean almacenes distintos. Las
  preferencias existentes en `MiEstudio/Imago` se copian una sola vez con
  prioridad, sin borrar el origen y sin confirmar la migración ante un error de
  sincronización. El modo portable sigue aislado en `datos/Imago.ini`, y de ese
  mismo archivo salen tema, preferencias e idioma de `i18n`/`QTranslator`.
  Cubierto por 4 regresiones; suite completa: 70 pruebas en Windows, 3 POSIX
  omitidas condicionalmente.
