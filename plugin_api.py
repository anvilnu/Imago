# plugin_api.py
"""API pública y ESTABLE que Imago pasa a cada plugin de terceros.

Un plugin es un paquete (carpeta con manifest.json + __init__.py) cuyo __init__.py
define una función `registrar(api)`. Imago la llama al arrancar pasándole una
instancia de `ImagoPluginAPI`. Ejemplo mínimo:

    def registrar(api):
        class MiDialogo(api.AdjustmentDialog):
            title = "Mi efecto"
            def build_controls(self):
                self.add_slider_row("k", "Intensidad", 0, 100, 50)
            def compute(self, arr):        # arr: numpy uint8 (alto, ancho, 4) RGBA
                return arr
        api.registrar_efecto("mi_efecto", MiDialogo)

La API es una FACHADA sobre MainWindow: expone SOLO lo necesario para registrar
ajustes/efectos y traducciones, sin acoplar el plugin a los internos de Imago. Al
heredar de `api.AdjustmentDialog`, el plugin obtiene gratis el panel overlay, la
vista previa en vivo, el deshacer/rehacer, el respeto de la selección y el tema.

Compatibilidad: `API_VERSION` sube cuando cambia el contrato. El manifest.json de
un plugin puede declarar "api_version"; el PluginManager rechaza los de una API
mayor que la que entiende esta versión de Imago.
"""

# Versión del contrato de plugins. Súbela solo si cambias la firma pública.
API_VERSION = 1


class ImagoPluginAPI:
    """Fachada que se entrega a cada plugin en su `registrar(api)`."""

    API_VERSION = API_VERSION

    def __init__(self, main_window, plugin_id="?"):
        self._mw = main_window
        self.plugin_id = plugin_id
        # Base reexportada: el plugin hereda de aquí sin conocer rutas internas de
        # Imago (`from adjustments import AdjustmentDialog` es un detalle privado).
        from adjustments import AdjustmentDialog
        self.AdjustmentDialog = AdjustmentDialog

    # ------------------------------------------------------------------ i18n
    def registrar_traducciones(self, strings):
        """Da de alta los textos del plugin en i18n (ES/EN/FR). `strings` es un
        dict {clave: {"es": ..., "en": ..., "fr": ...}}. No pisa claves de Imago."""
        from i18n import registrar_strings
        registrar_strings(strings)

    def t(self, key, **kwargs):
        """Texto traducido en el idioma activo (usa las claves que registraste)."""
        from i18n import t
        return t(key, **kwargs)

    # -------------------------------------------------- registro de acciones
    def registrar_ajuste(self, clave, dialog_cls, titulo=None, icono=None):
        """Añade el ajuste al submenú Ajustes ▸ Plugins.

        - clave: identificador estable del plugin (string).
        - dialog_cls: subclase de `api.AdjustmentDialog` (define build_controls y
          compute).
        - titulo: texto del menú; si es None se usa `dialog_cls.title`.
        - icono: ruta de recurso ":/icons/x.png" opcional (si no, un icono genérico).
        """
        self._mw._registrar_plugin_overlay("ajuste", clave, dialog_cls, titulo, icono)

    def registrar_efecto(self, clave, dialog_cls, titulo=None, icono=None):
        """Igual que `registrar_ajuste` pero en el submenú Efectos ▸ Plugins."""
        self._mw._registrar_plugin_overlay("efecto", clave, dialog_cls, titulo, icono)
