# Imago — guía para agentes de IA

Este archivo contiene las instrucciones persistentes del repositorio para Codex,
Claude Code y cualquier otro asistente de programación. Debe leerse antes de
analizar, modificar, validar o documentar código del proyecto.

Imago es un **editor de imágenes de escritorio estilo Paint.NET**, escrito en
**Python + PySide6 (Qt 6)**, con capas, selección, deshacer/rehacer, herramientas
de dibujo, IA local y un tema oscuro propio. Pensado principalmente para
**Linux** (el desarrollo actual es en CachyOS/KDE), con versión también para
**Windows** (donde nació el proyecto): los branches por plataforma de
maximizar/restaurar deben seguir funcionando en ambos.

## Alcance y prioridad de estas instrucciones

- Estas reglas se aplican a todo el repositorio, salvo que un `AGENTS.md` situado
  en una subcarpeta defina instrucciones más específicas para esa parte.
- Las instrucciones explícitas de la tarea actual tienen prioridad sobre este
  documento, excepto cuando contradigan requisitos de seguridad, integridad de
  datos o compatibilidad indicados aquí.
- Antes de editar, inspecciona los archivos relacionados y sigue los patrones ya
  existentes. No presupongas la arquitectura a partir del nombre de un archivo.
- No conviertas una tarea concreta en una refactorización general. Conserva las
  APIs, el comportamiento y la estructura que no formen parte del encargo.

## Filosofía del proyecto

Imago busca ofrecer una experiencia de edición rápida, estable y coherente, con
funciones avanzadas e IA local sin obligar al usuario a enviar imágenes a la
nube. Prioriza, en este orden: integridad de los documentos del usuario,
estabilidad, compatibilidad Windows/Linux, rendimiento, coherencia de interfaz y
mantenibilidad. Una solución pequeña integrada en la arquitectura existente es
preferible a otra más vistosa que duplique sistemas o introduzca deuda técnica.

## Compatibilidad obligatoria Windows/Linux

**Toda corrección, mejora y función nueva debe diseñarse para funcionar tanto en
Windows como en Linux**, aunque la sesión de desarrollo actual se ejecute solo
en uno de ellos. Linux (KDE/Wayland nativo) es la plataforma principal de Imago;
Windows sigue siendo una plataforma soportada de primera clase. No se da una
tarea por terminada si resuelve un sistema rompiendo o ignorando el otro.

- Usa APIs multiplataforma de Python/Qt siempre que sea posible. Si hace falta
  una rama específica, aíslala mediante una detección explícita de plataforma,
  conserva un camino funcional para la otra y explica el motivo en el código.
- No presupongas separadores, letras de unidad, mayúsculas del sistema de
  archivos, permisos POSIX, disponibilidad de enlaces simbólicos ni semántica
  de archivos abiertos de Windows. Construye rutas con `os.path`/`pathlib` y
  trata bloqueos, permisos y errores de E/S sin pérdida de datos.
- En escrituras atómicas, el temporal debe estar en el mismo sistema de archivos;
  en POSIX hay que respetar `umask`, conservar los permisos del destino cuando
  exista y no romper enlaces simbólicos. En Windows, cerrar todos los objetos Qt
  y descriptores antes de reemplazar, porque un archivo abierto no se sustituye.
- La UI no debe depender de X11/XWayland: mantener Wayland nativo, overlays hijo
  y coordenadas locales. No alteres las ramas Windows/Linux de ventana sin
  validar conceptualmente ambos comportamientos.
- Añade pruebas comunes y, cuando proceda, pruebas condicionales por plataforma.
  Ejecuta las disponibles en el sistema actual y deja claro en la entrega qué
  plataforma se probó físicamente y cuál quedó cubierta por diseño/pruebas para
  su siguiente ejecución en CI o en una máquina real. Nunca afirmes que una
  plataforma fue probada si no lo fue.

## Idioma (importante)

**Todo el proyecto está en español**: nombres de la interfaz, textos, comentarios,
docstrings y mensajes. Mantén el español en cualquier código, comentario o texto
que generes. Responde y razona en español.

La interfaz está **traducida ES/EN/FR** vía `i18n.py`: TODO texto visible al usuario
debe pasar por `t("clave", default="Texto en español")`, añadiendo la clave con
sus tres idiomas al diccionario de `i18n.py`. En los combos, el dato va en
`itemData` y el texto visible sale de `t()` (no acoples lógica al texto).

## Stack y ejecución

- **Python 3** + **PySide6** (Qt 6) para toda la UI.
- **NumPy** para operaciones de píxeles vectorizadas (máscaras de borrado, etc.).
- Punto de entrada: `python main.py` (al final de `main.py` está el
  `if __name__ == "__main__"` que crea el `QApplication` y lanza la ventana).
- Hay `requirements.txt` con las dependencias de pip (PySide6, numpy, scipy,
  onnxruntime, opencv-python-headless…). `pillow` se usa en `exif_utils.py`
  (import perezoso) para conservar los metadatos EXIF al reescribir un JPEG.
  onnxruntime y cv2 se importan de forma
  PEREZOSA: Imago arranca aunque falten (solo se necesitan para ejecutar IA).
  El viejo aviso de `libxcb-cursor` solo aplica si alguien fuerza a mano
  `QT_QPA_PLATFORM=xcb` (por defecto ya no se usa ese backend).
- Los errores no capturados se registran en `imago_crash.log` (hook al
  principio de `main.py`), útil para diagnosticar cierres inesperados.
- Hay pruebas de regresión headless en `tests/`. Para validar un cambio:
  comprueba que compila (`python -m py_compile <archivo>`), ejecuta
  `python -m unittest discover -v tests` y prueba manualmente la app cuando el
  cambio afecte a interacción o integración gráfica no cubierta por la suite.

## Estructura del proyecto

```
main.py                 Ventana principal (MainWindow, QMainWindow SIN MARCO):
                        arranque y hook de crashes, __init__ y cableado,
                        set_tool, pestañas (create_new_tab_canvas,
                        on_tab_changed), estado de menús por contexto,
                        preferencias, arrastrar-y-soltar y closeEvent
                        (~1500 líneas tras el refactor de jul 2026). El grueso
                        vive en los MIXINS del paquete ventana/, que MainWindow
                        hereda; todo sigue llamándose vía self.* igual que
                        siempre:

ventana/                Paquete con los MIXINS de MainWindow:
  menu_ia.py            AccionesMenuIA: handlers ai_* del menú IA y auxiliares
                        _ai_*/_cv_* (prechequeos, descarga, commit, busy...).
  menu_ajustes.py       AccionesMenuAjustes: adjust_*/effect_* + _open_adjustment
                        y la instancia única de overlays (_open_ai_overlay).
  menu_archivo.py       AccionesMenuArchivo: nuevo/abrir (PSD, SVG, animados,
                        recuperación de autoguardado), guardar/guardar como,
                        imprimir, exportar (PDF/ORA/animación), calidad y
                        filtros de formato, y recientes (con _RecentItem).
  menu_edicion.py       AccionesMenuEdicion: edit_* (portapapeles, seleccionar
                        todo/deseleccionar...) y _refine_selection (refinado).
  menu_imagen_capas.py  AccionesMenuImagenCapas: image_* (recortar a selección,
                        tamaños, voltear/girar) y layer_* (visibilidad, modo de
                        fusión, máscaras, voltear/girar capa).
  menu_ver.py           AccionesMenuVer: cuadrícula/reglas/guías, TODO el zoom,
                        la construcción de la barra de estado
                        (_build_status_bar) y los tooltips de pestañas.
  opciones_herramientas.py  OpcionesHerramientas: los ~60 handlers update_*/
                        set_* que la barra de opciones invoca al tocar un
                        control y escriben los parámetros como atributos del
                        canvas.
  construccion_ui.py    ConstruccionUI: create_menus (toda la barra de menús),
                        create_docks (paneles empotrados en splitters), toggles
                        de paneles, toolbar fija y pantalla de bienvenida.
                        Métodos llamados desde __init__ en el orden de siempre.
  cursores.py           CursoresHerramientas: CURSOR_DEFS/FALLBACK, cursores
                        PNG con punto caliente y el círculo dinámico del
                        pincel/goma.
utilidades.py           crear_icono / crear_icono_checkable /
                        cargar_imagen_orientada (fallback Pillow para
                        AVIF/HEIC/JXL) / _canvas_thumb_pixmap: módulo propio
                        para que los mixins las importen sin ciclos con main.
theme.py                ÚNICA FUENTE DE VERDAD del estilo (tokens de color +
                        funciones que devuelven QSS por tipo de control).
i18n.py                 Traducciones ES/EN/FR: diccionario de claves + t("clave",
                        default=...). TODO texto visible pasa por t().
adjustments.py          Diálogos de Ajustes y Efectos (heredan de
                        AdjustmentDialog, que es un OverlayPanel: panel overlay
                        NO modal, no un FramelessDialog).
new_dialog.py           Diálogos Nuevo / Cambiar tamaño / Tamaño de lienzo /
                        Calidad (todos FramelessDialog).
help_dialogs.py         Preferencias, Acerca de, Manual, Atajos de teclado y
                        Crear plugins (guía técnica, PluginGuideDialog); todos
                        FramelessDialog.
plugin_api.py           ImagoPluginAPI: fachada ESTABLE que se pasa a cada plugin
                        de terceros (registrar_ajuste/efecto/traducciones + la
                        base AdjustmentDialog reexportada). API_VERSION versiona
                        el contrato. Ver "Sistema de plugins" más abajo.
plugin_manager.py       PluginManager: descubre y carga los plugins (incluidos +
                        de usuario), con consentimiento por huella y tolerancia a
                        fallos. Lo instancia MainWindow._cargar_plugins.
plugins/                Plugins de EJEMPLO incluidos (sepia_ejemplo,
                        ruido_sal_pimienta): cada uno es una carpeta con
                        manifest.json + __init__.py. Viajan como datos del .exe
                        (ver el os.walk de Imago.spec). Los de terceros NO van
                        aquí: el usuario los deja en su carpeta de datos.
exif_utils.py           Conserva los metadatos EXIF (fecha, cámara, GPS,
                        miniatura...) al reescribir un JPEG: reincrusta el bloque
                        EXIF de origen CRUDO como segmento APP1 tras el SOI, sin
                        recomprimir. Se parchea IN SITU (mismo tamaño): la
                        Orientación a 1 (los píxeles ya se guardan derechos) y, si
                        no se quiere GPS, se neutraliza el puntero 0x8825. NO se
                        re-serializa con Pillow (su TIFF lo rechaza exiv2/KDE y
                        pierde la miniatura); Pillow sólo LEE el bloque original.
                        El lienzo lleva canvas.source_exif del abrir.

models/                 (código, no confundir con los modelos ONNX de IA)
  layer.py              Layer (imagen + máscara no destructiva + blend + opacidad),
                        TextLayer (capa de texto vectorial reeditable) y
                        LayerGroup (grupos/carpetas del panel, SOLO organización;
                        ver "Grupos de capas" más abajo).
  layer_commands.py     Comandos de deshacer de CAPAS y de imagen completa
                        (añadir/quitar/duplicar/fusionar capa, máscaras, resize,
                        crop, flip, rotate...).
  project_io.py         Formato nativo .imago: un ZIP con manifest.json + una
                        PNG por capa (conserva transparencia).
  autosave.py           AutoSaveManager: copia de recuperación (.imago) cada
                        3 min de las pestañas con cambios; en un cierre limpio se
                        borra, y si queda, al arrancar se ofrece recuperarla.

tools/                  Una clase por herramienta (tool_id, mouse_press/move/
                        release). Muchas heredan de PenTool/BaseTool.
  base_tool.py          BaseTool.
  commands.py           Comandos de deshacer de píxeles. PaintCommand guarda solo
                        el PARCHE del rectángulo modificado (no copias del lienzo
                        entero) y su undo/redo REEMPLAZA el objeto layer.image
                        (no pinta in place): MoveTool detecta cambios externos
                        comparando la IDENTIDAD del QImage.
  numpy_utils.py        Utilidades numpy compartidas: kernels de pincel, flood
                        fill por tolerancia, path_from_mask (máscara booleana ->
                        QPainterPath de selección, con fusión de rectángulos).
  roi_buffers.py        Coberturas e imagen premultiplicada `float32` dispersas
                        por teselas, más lectura/escritura y selección por ROI.
  draw_tools.py         PenTool, EraserTool, PencilTool, ReplaceColorTool.
  bucket_tool.py        BucketTool (relleno).
  eyedropper_tool.py    EyedropperTool (cuentagotas).
  selection_tools.py    RectSelectTool, EllipseSelectTool, LassoSelectTool.
  magic_wand_tool.py    MagicWandTool (varita mágica).
  crop_tool.py          CropTool (recorte con caja ajustable: tiradores,
                        oscurecido exterior, tercios; Enter aplica CropCommand).
  move_tool.py          MoveTool: caja de transformación (mover/escalar/GIRAR)
                        con begin_paste() para levantar una imagen flotante.
  move_selection_tool.py  MoveSelectionTool (mueve solo la marquesina).
  move_copy_tool.py     MoveCopyTool (mueve una copia).
  text_tool.py          TextTool (texto editable con QTextEdit superpuesto).
  clone_tool.py         CloneTool (clonar/tampón).
  airbrush_tool.py      AirbrushTool (aerógrafo).
  smudge_tool.py        SmudgeTool (dedo/difuminar).
  dodge_burn_tool.py    DodgeBurnTool (sobreexponer/subexponer por rango tonal;
                        Ctrl invierte el modo; sin acumular dentro del trazo).
  heal_tool.py          HealTool (pincel corrector: marca la zona y al soltar
                        la reconstruye con cv2.inpaint; cv2 se importa perezoso).
  gradient_tool.py      GradientTool (degradado).
  shape_tool.py         ShapeTool + shape_geometry.py + shape_picker.py (formas).
  pattern_tiles.py      Patrones de relleno (pincel, cubo, formas).
  pen_path_tool.py      PenPathTool (pluma/trazados).
  hand_tool.py          HandTool (mano, desplazar la vista).

widgets/
  canvas.py             EL LIENZO (ojo: vive aquí, no en la raíz): capas,
                        selección, zoom, pila de deshacer, composición con caché
                        parcial por regiones, guías con imán. Atributos de
                        parámetros de herramienta.
  custom_titlebar.py    CustomTitleBar (barra de título propia de la ventana sin
                        marco), FramelessDialog (base de los diálogos MODALES),
                        ImagoMessageBox + helpers imago_information/imago_warning/
                        imago_question/imago_critical, y FramelessResizeFilter
                        (redimensionar por bordes). Maximizar/restaurar a mano.
  overlay_panel.py      OverlayPanel: base de los Ajustes/Efectos con preview en
                        vivo (AdjustmentDialog). Panel HIJO de la ventana (no una
                        ventana del SO), no modal, arrastrable en coords locales.
  options_bar.py        Barra de opciones DINÁMICA: un QStackedWidget con un panel
                        por herramienta; show_panel_for_tool() muestra el activo.
                        Los paneles viven en 4 MIXINS por familia que
                        DynamicOptionsBar hereda (refactor jul 2026):
  opciones_dibujo.py    PanelesDibujo: pincel, lápiz, goma, cubo, patrones,
                        formas, aerógrafo, difuminar, sobre/subexponer,
                        corrector, clonar, degradado, reemplazo de color y
                        cuentagotas.
  opciones_trazados.py  PanelesTrazados: pluma (trazados), línea/curva y
                        medición.
  opciones_texto.py     PanelesTexto: panel de texto y su sincronización.
  opciones_seleccion.py PanelesSeleccion: mover (con refinar), marquesinas,
                        mover selección/copia, mano, recorte y varita.
  tab_thumbnails.py     TabThumbnailBar (+_ThumbButton/_ThumbStrip): barra de
                        miniaturas de pestañas, dirigida por la huella visual
                        del canvas y con caché reducida compartida con tooltips.
  canvas_scroll.py      CanvasScrollArea + CanvasFrameOverlay (scroll del
                        lienzo con marco/sombra y clic de fondo que
                        deselecciona), extraídas de main.py.
  tools_panel.py        Rejilla de botones de herramienta (izquierda) y
                        ATAJOS_HERRAMIENTAS: mapa de atajos de UNA TECLA por
                        herramienta (B pincel, E goma, M marquesina...), única
                        fuente de verdad para tooltips y QActions
                        (_crear_atajos_herramientas en main.py).
  layers_panel.py       Panel de capas (incluye LayerPropertiesDialog).
  history_panel.py      Panel de historial (deshacer/rehacer).
  colors_panel.py       Panel de color (primario/secundario, RGB, hex, muestras).
  histogram_panel.py    Histograma muestreado del documento activo; solo sondea
                        mientras su panel está visible.
  document_diagnostics.py  Ventana modeless de diagnóstico bajo demanda:
                        dimensiones, capas, memoria, proyecto y efectos caros;
                        SIN temporizador ni lectura de píxeles.
  ruler_overlay.py      RulerOverlay: reglas (px/cm) con línea de seguimiento.
  effect_controls.py    CenterPicker y AngleDial (controles de los efectos).

ai/                     Menú IA: modelos ONNX LOCALES (CPU) + OpenCV clásico.
                        Los imports de onnxruntime/cv2 son PEREZOSOS: Imago
                        arranca aunque no estén instalados.
  runner.py             InferenceRunner (QThreadPool): inferencia y descargas
                        FUERA del hilo GUI; callbacks siempre en el hilo GUI.
  ipc_arrays.py         Transporte de arrays grandes por `.npy` mapeados entre
                        el proceso principal y el worker aislado (sin pickle
                        proporcional a la imagen; limpieza por tarea).
  model_manager.py      Catálogo de modelos (url + sha256), descarga con
                        verificación y diálogo de gestión. Los .onnx se guardan
                        en la carpeta de datos del usuario (AppDataLocation).
  effect_panels.py      Paneles overlay de IA con preview en vivo (misma familia
                        que AdjustmentDialog).
  cv_effects.py         OpenCV clásico: enderezar horizonte, ojos rojos,
                        perspectiva, panorama. Ver el gotcha del locale es_ES.
  imgproc.py            Conversión QImage <-> arrays y utilidades comunes.
  bg_removal.py, segment.py, inpaint.py, colorize.py, upscale.py, denoise.py,
  depth.py, anaglyph.py, face_restore.py, bg_effects.py
                        Una función de IA por módulo (isnet, DeepLab, LaMa,
                        DDColor, Real-ESRGAN, SCUNet, MiDaS, GFPGAN...).

icons/                  Iconos PNG (FUENTE de los iconos). En dev se usan desde
                        aquí, pero NO se distribuyen: se EMBEBEN en recursos_rc.py
                        (ver más abajo). Incluye icons/cursor/ (cursores).
recursos.qrc            Lista de recursos (generada). No editar a mano.
recursos_rc.py          Recursos EMBEBIDOS compilados (generado por
                        generar_recursos.py). main.py hace `import recursos_rc` y
                        así todos los iconos quedan como ":/icons/...".
generar_recursos.py     Regenera recursos.qrc + recursos_rc.py desde icons/.
                        EJECÚTALO cada vez que añadas/quites/cambies un icono:
                        `python generar_recursos.py`.
imago_crash.log         Registro de excepciones no capturadas (hook de main.py).
```

## Convenciones críticas (respétalas siempre)

### Finales de línea: CRLF
Casi todos los `.py` usan **CRLF** (`\r\n`). **Conserva CRLF** al editar; no los
conviertas a LF (provoca diffs enormes y finales mezclados). Si tu editor o una
herramienta los cambia, vuelve a dejarlos en CRLF antes de guardar.

### Iconos: recursos EMBEBIDOS (`:/icons/...`)
Los iconos NO se distribuyen como carpeta suelta: viajan dentro del programa,
compilados en `recursos_rc.py` (que `main.py` importa al arrancar). Reglas:
- Referéncialos SIEMPRE por su ruta de recurso **`:/icons/nombre.png`** (no
  `"icons/nombre.png"`), tanto en Python (`QIcon`, `QPixmap`, `crear_icono`) como
  en QSS de `theme.py` (`url(:/icons/...)`).
- Para comprobar si un icono existe usa **`QFile.exists(":/icons/x.png")`**, NO
  `os.path.exists` (que solo ve el disco, no los recursos).
- Al añadir/quitar/cambiar un PNG en `icons/`, **regenera** los recursos con
  `python generar_recursos.py` (reconstruye `recursos.qrc` y `recursos_rc.py`); si
  no, el icono nuevo no aparecerá. La carpeta `icons/` sigue en el repo como
  fuente, pero PyInstaller ya NO la empaqueta (`datas=[]` en `Imago.spec`).
- Esto reduce la copia casual de los iconos; no es cifrado (son extraíbles con
  herramientas de Qt).

### El estilo sale SIEMPRE de theme.py
No incrustes colores ni QSS a mano en los widgets. Usa los **tokens** y las
**funciones** de `theme.py`:
- Tokens: `BG_WINDOW` `#2b2b2b`, `BG_DARK` `#202020`, `BG_BUTTON` `#3a3a3a`,
  `ACCENT` `#007acc`, `BG_PRESSED` `#1a4f7c`, `TEXT` `#e0e0e0`, `BORDER` `#555555`…
- Funciones por arquetipo: `toolbutton_flat_qss`, `toolbutton_toggle_qss`,
  `dialog_button_qss(selector)`, `dialog_button_plain_qss(selector)`,
  `slider_qss`, `spinbox_qss`, `combobox_qss`, `checkbox_qss`, `list_qss`,
  `panel_action_button_qss`, etc.
- **Lenguaje de interacción unificado** (mantenlo en cualquier control nuevo):
  hover = fondo se aclara + borde azul `#007acc`; activo/seleccionado/pulsado =
  `#1a4f7c`; deshabilitado = texto `#555555`; mango de slider `#007acc` (hover
  `#3399dd`) con relleno (sub-page) `#1a4f7c`.

### Ventana y diálogos SIN MARCO
La ventana principal y todos los diálogos son *frameless* con barra de título
propia. **No uses `QDialog` ni `QMessageBox` nativos.** Para diálogos hereda de
**`FramelessDialog`**; para mensajes usa los helpers `imago_information`,
`imago_warning`, `imago_question`, `imago_critical` (de `widgets/custom_titlebar`).
- Excepción permitida: `QFileDialog` nativo del SO (selector estándar; intencionado).
- Selector de color: **NO** uses `QColorDialog` ni un `FramelessDialog` (sería una
  ventana del SO, y en Wayland no se puede posicionar/acotar). El selector propio
  de Imago vive en `widgets/color_dialog.py` y son **overlays HIJOS del lienzo**
  (`_ColorOverlayBase`, misma familia que los Ajustes/Efectos): Wayland-safe, con
  topes, e idénticos en Windows y Linux. Dos variantes:
  - **Editor del panel de color** (`ImagoColorOverlay`): en vivo, con cuadros
    primario/secundario. Lo abre el panel (`open_color_dialog`) y también el menú
    Ver ▸ Paleta de Colores (`MainWindow.change_color`).
  - **Selector suelto** para pedir UN color (efecto, fondo de IA...):
    `imago_pick_color(initial, parent, title, show_alpha=False, on_accept=...)` de
    `widgets/colors_panel.py`. Es un overlay con Aceptar/Cancelar que entrega el
    color por **callback** `on_accept(color)` (NO bloquea ni devuelve; la lógica
    que use el color va dentro del callback, como los overlays de Ajustes).
- Trampa conocida: dentro de un `FramelessDialog`, **nunca** uses un selector
  `QPushButton` pelado con `min-width` (deforma la "X" de la barra de título).
  Usa `dialog_button_plain_qss()` (sin min-width) o `dialog_button_qss()` con un
  selector acotado (p. ej. `QDialogButtonBox QPushButton`).

### Ajustes/Efectos = PANEL OVERLAY (no diálogo modal)
Los Ajustes/Efectos con **vista previa en vivo** (`AdjustmentDialog`, ~55
subclases) **NO** son diálogos modales: son un **panel overlay** (`OverlayPanel`,
en `widgets/overlay_panel.py`), un `QWidget` **HIJO** de la ventana superpuesto
sobre el lienzo. Motivo: en KDE/Wayland el compositor **atenúa** la ventana
principal cuando un diálogo modal la deja inactiva ("Atenuar ventanas inactivas")
y no se apreciaba la preview. Al ser un hijo (no una ventana del SO), la principal
nunca queda inactiva → ningún compositor la atenúa, en cualquier SO; y se mueve en
coordenadas LOCALES (no `startSystemMove`) → Wayland-safe.
- `OverlayPanel` replica la superficie de `FramelessDialog` (`self._frame` temado,
  `self.body_layout`, barra propia arrastrable con "X"=Cancelar), más `open_over(
  main_window)`, `accept()/reject()` virtuales, teclas (Esc=Cancelar/Enter=Aceptar)
  y persistencia de la última posición en QSettings (`overlay/last_x|y`).
- Apertura: `_open_adjustment()` (en `ventana/menu_ajustes.py`) hace `panel = dialog_cls(self);
  panel.open_over(self)` (no `.exec()`), con **instancia única** (abrir otro
  cancela el anterior). No quites esto ni vuelvas a `FramelessDialog`/`.exec()` para
  estos ajustes: reintroduce el atenuado en Wayland.
- Mientras el overlay está abierto, un `eventFilter` sobre el canvas **bloquea el
  pintado** (clic/arrastre izquierdo) y deja pasar zoom/pan (rueda + botón central)
  para inspeccionar. Se retira al cerrar.
- Los diálogos SIN preview (Preferencias, Nuevo, Cambiar tamaño, ImagoMessageBox…)
  siguen siendo `FramelessDialog` modales: su atenuado es inofensivo (no hay preview
  que mirar).

### Paneles empotrados en splitters (no flotan)
Los paneles (Herramientas, Capas, Historial, Color e Histograma) van
**empotrados**
dentro de la ventana, no flotan. El montaje (en `create_docks()` de
`ventana/construccion_ui.py`, nombre histórico) es:
- Cada panel va envuelto por `_panel_with_header(panel, título, header_buttons)`
  en un contenedor `[cabecera + panel]` (`*_container`). **Lo que se mete en el
  splitter y lo que muestran/ocultan los toggles y la persistencia es el
  CONTENEDOR**, no el panel pelado (así la cabecera se oculta con su panel). La
  cabecera simple usa `theme.panel_header_qss()`; con botones (▲/▼) es
  un `QWidget#PanelHeaderBar` con `theme.panel_header_bar_qss()`. Herramientas
  usa el título corto `panel.tools_short` ("Herr.").
- `self.root_splitter` (QSplitter horizontal) = `[tools_container |
  content_container | right_splitter]`. Herramientas tiene ancho fijo (76 px,
  rejilla SIEMPRE a 2 columnas); el centro
  (lienzo) es la celda elástica (`setStretchFactor(1, 1)`). Los separadores se
  estilizan con `theme.splitter_qss()` (línea de 1 px, azul al pasar/arrastrar).
- `self.right_splitter` (QSplitter vertical) = Histograma · Historial · Capas ·
  Color por defecto,
  **REORDENABLES por el usuario** con los botones ▲/▼ de cada cabecera
  (`_move_right_panel`, que conserva los tamaños con el panel; orden persistido
  en `panels/right_order` y aplicado en `restore_preferences` ANTES del
  `restoreState`, que repone tamaños por posición). **Color e Histograma NO se
  estiran**: los
  stretch factors se aplican POR IDENTIDAD con `_apply_right_stretch_factors()`
  (Capas=1, Historial=1, los demás=0), nunca a mano por índice (el orden puede
  cambiar) ni con `setFixedHeight`. IMPORTANTE: fijar el alto de Color con
  `setFixedHeight` le pone un `maximumHeight` que, cuando Color queda como
  único hijo visible (Capas e Historial ocultos), lo hereda el `right_splitter` y
  con él el `root_splitter`, descuadrando toda la interfaz (se iba hacia abajo).
  Con stretch factors Capas e Historial absorben el espacio y Color mantiene su
  alto sin imponer ningún máximo.
- `_update_right_column_visibility()` oculta el `right_splitter` entero cuando
  todos sus paneles están ocultos (el lienzo recupera el espacio) y lo reaparece
  si se abre alguno. Conectado a todos los toggles y sincronizado en
  `restore_preferences`.
- Los botones `btn_toggle_*` hacen `container.setVisible(...)`. El de Historial
  apunta a `history_container` (estable); el panel interno `history_view` se
  **recrea** al cambiar de pestaña — ver el swap en `on_tab_changed`, que lo
  reemplaza DENTRO de su contenedor con `layout().replaceWidget(...)`.
- El `RulerOverlay` es hijo de `content_container`; un `eventFilter` re-sincroniza
  las reglas ante cualquier `Resize` de ese contenedor (arrastre de splitter,
  ocultar panel, resize de ventana).
- Persistencia: visibilidad de los contenedores + `saveState()/restoreState()` de
  ambos splitters en `save_preferences`/`restore_preferences` (claves `panels/*` y
  `splitters/*`).

### Diagnóstico del documento = ventana independiente
`DiagnosticoDocumentoDialog` es un `FramelessDialog` **modeless** separado de la
columna derecha. Se abre con el botón de propiedades superior o desde Ver ▸
Diagnóstico del documento; se conserva una sola instancia y sigue el documento
activo. Su contenido no lleva sondeo: al abrir lee solo metadatos, `cacheKey()` y
`sizeInBytes()`. Si cambia el historial visible, únicamente marca «Actualizar •»
y espera al usuario. No debe volver al `right_splitter` ni renderizar capas,
convertir imágenes o comprimir para calcular cifras: su ventana independiente
evita que la suma de alturas mínimas de los paneles agrande MainWindow.

### Maximizar/restaurar (ventana sin marco)
**En Windows** se hace a mano (no `showMaximized()`/`showNormal()`, poco fiables
sin marco): se guarda la geometría y se fija `screen().availableGeometry()`. Si la
barra de tareas está autooculta, se deja 1 px libre abajo para que pueda seguir
saliendo. **En Linux/Mac sí** se usan `showMaximized()`/`showNormal()` (se integran
mejor con el compositor). El branch por plataforma vive en
`widgets/custom_titlebar.py` (`_maximize_window`/`_restore_window`). No cambies el
branch de Windows a `showMaximized()`.

### Linux: Wayland nativo (ya NO se fuerza XWayland)
Históricamente se forzaba el backend xcb (`QT_QPA_PLATFORM=xcb`) en el `__main__`
porque las 4 paletas eran ventanas `Qt.Tool` posicionadas en **coordenadas
globales** con `move()`, algo que **Wayland puro prohíbe**. Tras migrar los
paneles a **empotrados en QSplitters** (ya no flotan), ese forzado se eliminó:
Imago usa el **backend nativo del SO** (Wayland si la sesión lo es). La ventana
(mover/redimensionar/maximizar) ya funcionaba en Wayland nativo vía
`startSystemMove()`/`startSystemResize()`/`showMaximized()`. Si alguna distro
diera problemas, el usuario puede forzar el backend a mano con
`QT_QPA_PLATFORM=xcb` (no está cableado en el código).

## Patrones de arquitectura (para añadir cosas de forma coherente)

- **Rendimiento como criterio de aceptación:** toda mejora debe evitar trabajo
  continuo proporcional al número de capas, píxeles o documentos durante la
  interacción. Prefiere señales/eventos y cachés invalidadas frente a sondeos;
  desplaza CPU, compresión y E/S pesada fuera del hilo GUI. Añade una regresión
  o una medición proporcionada al riesgo y no cierres el punto si introduce
  pausas o ralentizaciones apreciables en el uso normal.
- **Añadir/ajustar una herramienta:** crea/edita su clase en `tools/`
  (con `tool_id` y `mouse_press/move/release`), instánciala en `set_tool()` de
  `main.py`, y guarda sus parámetros como **atributos del canvas**
  (p. ej. `canvas.eraser_color_tolerance`). La barra de opciones los modifica
  llamando a handlers `update_*` de `ventana/opciones_herramientas.py` (mixin
  de MainWindow), que escriben en el canvas.
- **Barra de opciones dinámica:** cada herramienta tiene un panel en
  `widgets/opciones_*.py` (mixins de `options_bar.py`, por familia); muestra
  solo los controles que esa herramienta usa y oculta
  los demás (ejemplo: la tolerancia del borrador solo aparece en los modos
  "color" y "fondos", no en el normal). Sincroniza el estado al cambiar de
  herramienta y de pestaña.
- **Ajustes, rutas e idioma:** la identidad normal única es `AVNSoft/Imago` para
  `QSettings` y `QStandardPaths`; usa siempre `app_paths.settings()` y
  `app_paths.idioma()`, nunca un `QSettings()` pelado. En modo portable deben
  permanecer aislados en `datos/Imago.ini`, sin leer el registro. La migración
  desde el antiguo `MiEstudio/Imago` es conservadora y no borra el origen.
- **Miniaturas de documentos:** no restaures un sondeo periódico. `Canvas`
  compara `_huella_visual()` y emite `contenido_visual_cambiado`; la barra
  agrupa las ráfagas con un `QTimer` de disparo único y conserva una vista previa
  reducida por lienzo, compartida con su tooltip. Tras regenerarla llama a
  `confirmar_miniatura_actualizada()`. Cualquier propiedad nueva que altere el
  compuesto debe formar parte de `_huella_visual()`.
- **E/S pesada de documentos:** no comprimas ni decodifiques imágenes, ZIP,
  Pillow o PDF en el hilo GUI. Captura primero una instantánea coherente con
  `crear_instantanea_proyecto()`/`crear_instantanea_ora()` o un `QImage`
  desligado y ejecuta el trabajo mediante `_ejecutar_trabajo_io()`. El
  autoguardado comparte `main._io_runner`, cuya cola serial evita operaciones
  pesadas simultáneas. El worker no debe leer widgets ni `QSettings`; captura
  antes esos valores simples. Comprueba el token entre capas/fotogramas y antes
  de `os.replace()`. Tras Guardar, solo marca limpio el lienzo si su
  `revision_autoguardado` sigue siendo la capturada: una edición posterior a la
  instantánea debe continuar pendiente.
- **Ajustes pesados y efectos de capa:** `AdjustmentDialog.heavy` confirma a
  resolución completa mediante `_adjustment_runner`, nunca en el hilo GUI. La
  instantánea `_ComputeSnapshot` solo contiene valores simples y arrays; un
  `compute()` pesado no puede leer widgets desde el worker. Al terminar hay que
  revalidar el `DestinoCapa` antes de aplicar o crear el `PaintCommand`. En el
  compositor, usa `Layer.render_with_effects_patch()`: la caché conserva solo la
  caja del contenido y los halos. `render_with_effects()` materializa el lienzo
  completo para exportar/rasterizar/miniaturas, no para cada rectángulo sucio.
  Los controles de efectos de capa mantienen el debounce de 140 ms para no
  invalidar y recomponer por cada evento de un slider.
- **Herramientas locales y memoria:** Dedo, Licuar, Esponja y Sobre/Subexponer
  nunca deben convertir la capa completa a NumPy al empezar un trazo. Usa
  `ImagenPremultiplicadaDispersa`, `CoberturaDispersa` y los helpers de ROI de
  `tools/roi_buffers.py`; Pincel, Aerógrafo, Clonado y Sustituir color también
  acumulan su cobertura con esa clase. Las teselas se crean solo al tocarlas y
  deben liberarse al terminar. Conserva siempre selección, bloqueo alfa,
  precisión premultiplicada durante el trazo, preview y un único paso de undo.
- **Deshacer/rehacer:** `QUndoStack` en el canvas; los comandos de píxeles viven
  en `tools/commands.py` y los de capas/imagen completa en
  `models/layer_commands.py`. Las acciones de menú se habilitan/deshabilitan por
  contexto (`update_edit_actions_state`, `update_layer_menu_state`, conectadas a
  cambios de selección/portapapeles/pila y al `aboutToShow` de los menús).
  Dos INVARIANTES a respetar: (1) `PaintCommand` guarda solo el PARCHE del
  rectángulo modificado — pásale siempre el antes/después de la capa COMPLETA y,
  si la operación conoce una caja conservadora, `dirty_rect=QRect(...)` o
  `(x0, y0, x1, y1)` semiabierto; él la recorta y afina el parche exacto. No
  hagas antes `after != before`, porque volvería a recorrer toda la imagen; los
  comandos vacíos se marcan obsoletos y `QUndoStack` los descarta. (2) Su
  undo/redo REEMPLAZA el objeto `layer.image` (nunca pintar
  in place), porque `MoveTool` detecta cambios externos por identidad del QImage.
  El límite de pasos es configurable (Preferencias → Historial, clave QSettings
  `undo_limit`, 0 = sin límite) y se aplica al CREAR cada lienzo (Qt solo
  permite fijarlo con la pila vacía). El autoguardado NO identifica estados por
  `undo_stack.index()`: `canvas.revision_autoguardado` es monotónica y avanza
  con cada señal `indexChanged`, incluidas deshacer/rehacer y ramas nuevas; la
  última revisión solo se confirma después de escribir correctamente la copia.
- **Capas:** `canvas.layers` (lista) y `canvas.active_layer_index`;
  `widgets/layers_panel.py` las refleja y controla.
- **Grupos de capas (carpetas):** SOLO organización, a propósito (nada de
  opacidad/fusión por grupo: exigiría buffers intermedios y es la puerta a la
  lentitud que obligó a retirar las capas de ajuste). La lista plana
  `canvas.layers` sigue siendo LA fuente de verdad del render y del pintado;
  un grupo es una referencia `layer.group` → árbol de `LayerGroup`
  (`models/layer.py`), sin registro central (un grupo vive mientras alguna
  capa lo referencie; los vacíos desaparecen solos, y deshacer los revive
  porque la referencia viaja dentro de cada capa). INVARIANTES: (1) los
  miembros de un grupo van CONTIGUOS en `canvas.layers` (subgrupos anidados
  dentro del tramo del padre) — cualquier reorden nuevo debe conservarlo; la
  regla del panel es asignar a la capa movida el "grupo común más profundo de
  sus vecinos nuevos" (`grupo_comun`), que lo garantiza por construcción;
  (2) la composición y el aplanado usan `visible_efectiva(layer)` (la capa Y
  sus carpetas), no `layer.visible` a secas. Las filas del panel llevan su
  dato `("layer", idx)` / `("group", grupo)` en el UserRole: NO se puede
  deducir la capa de la posición de la fila (hay cabeceras y plegado). El
  plegado (`group.expanded`) es solo UI (ni historial ni documento sucio).
  La animación usa `capas_de_animacion()` y `frames_de_capas()` de
  `models/anim_io.py` para precomprobación, preview y exportación: no cuentes
  `layer.visible` directamente ni sustituyas `render_with_effects()` por el
  render base, porque reaparecerían capas de grupos ocultos o se perderían fx.
- **Cargar imágenes de disco:** SIEMPRE con `cargar_imagen_orientada(ruta)` de
  `utilidades.py` (QImageReader + setAutoTransform, reexportada por `main.py`),
  que aplica la rotación EXIF de las fotos de móvil. `QImage(ruta)` a secas las
  abriría tumbadas.
- **Máscara booleana → selección:** usa `path_from_mask(mask)` de
  `tools/numpy_utils.py` (devuelve el QPainterPath ya simplificado, o None).
  No reintroduzcas el patrón `region += QRegion(tramo)` fila a fila: con
  imágenes grandes tardaba decenas de segundos.
- **Trabajo pesado (IA, descargas):** nunca en el hilo GUI; usa
  `InferenceRunner.submit()` de `ai/runner.py` (los callbacks llegan al hilo GUI).
  Antes de lanzar una operación captura su destino con `DestinoCapa` o
  `DestinoDocumento` (`models/destino_edicion.py`) y vuelve a validarlo en cada
  callback que pueda modificar estado. No conserves solo un índice: las capas
  tienen un `uid` estable durante la ejecución y pueden reordenarse. Si el
  documento se cerró, dejó de ser el activo o su revisión cambió, descarta el
  resultado; nunca lo redirijas al lienzo o a la capa activos en ese momento.
- **IPC de inferencia aislada:** `ai/subproc.py`/`subproc_worker.py` deben pasar
  cualquier array NumPy grande mediante `ai/ipc_arrays.py`, no directamente por
  `Connection.send()` (pickle duplicaría sus bytes). El directorio temporal es
  exclusivo de una tarea y se elimina siempre DESPUÉS de terminar el hijo, para
  que Windows no conserve mapas abiertos. Conserva `allow_pickle=False`, valida
  que todo descriptor permanezca dentro de ese directorio y desliga en el
  principal los resultados que sobrevivirán a la limpieza. La espera inicial
  debe sondear el token/proceso y toda copia grande debe comprobar cancelación
  por bloques; no restaures un `join(120)` ni esperas largas al cerrar Imago.
- **Objeto flotante transformable** (selección movida, pegado y texto a girar):
  `MoveTool.begin_paste(image, origin=None, history_name="Pegar", tool_id="paste")`
  levanta una imagen como objeto que se mueve/gira/escala con tiradores. El texto
  usa esta misma vía: al pasar a la herramienta Mover con un cuadro de texto
  abierto, se rasteriza y se entrega a `begin_paste`.

### Sistema de plugins (Ajustes/Efectos de terceros)
Imago admite plugins de terceros que añaden Ajustes/Efectos, reutilizando toda la
maquinaria de `AdjustmentDialog` (overlay con preview, undo, selección, tema). Un
plugin es una CARPETA con `manifest.json` + `__init__.py` que define
`registrar(api)`. Piezas y reglas:
- **`plugin_api.py` (`ImagoPluginAPI`)**: la ÚNICA superficie pública para los
  plugins. Expone `AdjustmentDialog` reexportada, `registrar_ajuste/efecto(clave,
  DialogCls, titulo=None, icono=None)`, `registrar_traducciones(dict)` y `t()`.
  `API_VERSION` versiona el contrato: si tocas la firma pública, súbela. NO amplíes
  la API a la ligera: cada método nuevo es un contrato con terceros.
- **El plugin** hereda de `api.AdjustmentDialog` y define `title`, `build_controls`
  y `compute(arr)`. `arr` es numpy `uint8` de forma `(alto, ancho, 4)` en RGBA;
  debe devolver lo mismo y **respetar el alfa** (canal 3). Es la misma base que los
  Ajustes nativos, así que valen `add_slider_row`/`add_combo_row`/etc. y `val()`,
  `checked()`, `combo_index()`, `color()`.
- **`plugin_manager.py`**: descubre en DOS sitios y carga TOLERANTE A FALLOS (un
  plugin roto se registra en `imago_crash.log` y no tumba nada):
  1. INCLUIDOS: `dir_plugins_incluidos()` = `<código>/plugins` en dev, o
     `sys._MEIPASS/plugins` congelado (los `datas` del spec caen en `_internal`).
     Son de confianza → se cargan siempre.
  2. DE USUARIO: `dir_plugins_usuario()` = `base_datos()/plugins` (AppData o
     `datos/` portable). Son de terceros → sujetos a SEGURIDAD (ver abajo).
- **Registro en menús**: `MainWindow._registrar_plugin_overlay(tipo, clave,
  DialogCls, ...)` mete la acción en el submenú `Ajustes ▸ Plugins` o
  `Efectos ▸ Plugins` (creados ocultos en `create_menus`, se muestran al aparecer
  el primero) y la abre por la MISMA vía que los nativos (`_open_adjustment`).
- **SEGURIDAD (un plugin es código Python SIN sandbox, con tus permisos):** los de
  terceros NO se importan sin más. (a) Interruptor en Preferencias
  (`plugins/load_third_party`, por defecto True); si está off, no se carga ninguno.
  (b) CONSENTIMIENTO PREVIO A EJECUTAR: se calcula una huella SHA-256 del contenido
  de cada plugin; los ya aprobados (`plugins/approved`, JSON nombre→huella en
  QSettings) cargan sin preguntar, y los NUEVOS o MODIFICADOS se listan en un
  `imago_question` que pide permiso ANTES de importarlos. NO reintroduzcas la carga
  directa ni muevas el aviso a después de importar: la puerta debe seguir siendo
  previa a ejecutar el código. Un plugin de usuario no puede suplantar el nombre de
  uno incluido (los incluidos se registran primero).
- **Empaquetado**: al añadir/cambiar un plugin de ejemplo en `plugins/`, recuerda
  que `Imago.spec` lo empaqueta con un `os.walk` (omitiendo `__pycache__`/`.pyc`);
  no hace falta tocar el spec para un plugin nuevo dentro de `plugins/`.
- **Docs**: la guía para desarrolladores vive en `PluginGuideDialog`
  (`help_dialogs._plugin_guide_html`, ES/EN/FR) y hay una sección corta en el
  Manual. Mantén ambas si cambias la API.

## Cómo trabajar en este repo

1. Lee este documento y localiza los módulos afectados antes de proponer cambios.
2. Inspecciona las llamadas, invariantes y patrones vecinos; no edites basándote
   únicamente en una coincidencia de texto.
3. Haz **ediciones quirúrgicas y mínimas**. No reescribas archivos enteros ni
   cambies estilo o estructura de paso; toca solo lo necesario para la tarea.
4. Si una decisión de diseño o comportamiento de UI es materialmente ambigua,
   solicita aclaración. Para detalles menores, conserva el comportamiento actual
   y sigue el patrón más cercano del código.
5. No añadas dependencias, cambies formatos persistentes ni alteres APIs públicas
   sin señalarlo expresamente y justificarlo.
6. Tras editar, revisa el diff para detectar cambios accidentales, especialmente
   conversiones CRLF/LF, reformateos masivos y archivos generados.
7. **Verifica que compila** cada archivo Python modificado con
   `python -m py_compile <archivo>`. Ejecuta comprobaciones adicionales cuando la
   tarea disponga de ellas, sin inventar que se han realizado pruebas manuales.
8. Resume al finalizar qué cambió, qué validaste y cualquier riesgo o prueba manual
   que siga pendiente.

Mantén **español**, **CRLF** y el **estilo desde `theme.py`** en todo lo nuevo.

## Cosas que NO hacer

- No metas colores/QSS a mano (usa `theme.py`).
- No uses `QDialog`/`QMessageBox` nativos (usa `FramelessDialog`/`imago_*`).
- No conviertas los archivos a LF.
- No vuelvas a `showMaximized()`/`showNormal()` para la ventana principal **en
  Windows** (en Linux/Mac sí es lo correcto).
- No vuelvas a hacer flotantes los paneles ni a forzar `QT_QPA_PLATFORM=xcb`:
  los paneles van empotrados en QSplitters precisamente para correr en Wayland
  puro.
- No introduzcas texto/comentarios en inglés.

## Checklist antes de finalizar una tarea

Comprueba únicamente los puntos aplicables y no afirmes haber validado algo que no
hayas ejecutado o inspeccionado:

- [ ] El cambio se limita al alcance solicitado y el diff no contiene reformateos
      ni modificaciones accidentales.
- [ ] Los `.py` modificados conservan CRLF.
- [ ] Todo texto visible usa `t()` y tiene traducciones ES/EN/FR en `i18n.py`.
- [ ] Los controles nuevos usan tokens o funciones de `theme.py`, sin QSS ni
      colores incrustados.
- [ ] Los iconos usan rutas `:/icons/...`; si cambió `icons/`, se regeneraron los
      recursos.
- [ ] Los cambios de píxeles, capas o imagen participan correctamente en
      deshacer/rehacer y respetan las invariantes de `QImage`.
- [ ] El trabajo pesado no bloquea el hilo GUI.
- [ ] Se mantiene la compatibilidad de los branches específicos de Windows y
      Linux/Wayland.
- [ ] Cada archivo Python modificado supera `python -m py_compile`.
- [ ] La respuesta final distingue entre validaciones ejecutadas y pruebas manuales
      pendientes.
