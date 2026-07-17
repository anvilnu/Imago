# plugin_manager.py
"""Descubre y carga los PLUGINS de terceros (ajustes/efectos) de Imago.

Busca en DOS carpetas, cada plugin en su propia subcarpeta con un manifest.json y
un __init__.py que defina `registrar(api)`:

  1. INCLUIDOS: <carpeta del código/exe>/plugins  -> los ejemplos que trae Imago.
  2. DE USUARIO: <datos de usuario>/plugins        -> los que instala el usuario
     (AppData en instalación normal, <exe>/datos en modo portable).

Carga TOLERANTE A FALLOS (mismo espíritu que los imports perezosos de IA): un
plugin roto se registra en imago_crash.log y NO impide arrancar el resto ni la
app.

SEGURIDAD (un plugin es código Python SIN sandbox, con todos los permisos del
usuario):
  - Los plugins INCLUIDOS viajan dentro de Imago: son de confianza y se cargan
    siempre.
  - Los de USUARIO (terceros) están sujetos a:
      * un interruptor en Preferencias (QSettings `plugins/load_third_party`); si
        está desactivado, NO se carga ninguno.
      * CONSENTIMIENTO PREVIO A EJECUTARLOS: se calcula una huella (hash) del
        contenido de cada plugin; los ya aprobados (misma huella) se cargan sin
        preguntar, y los NUEVOS o MODIFICADOS se listan en un diálogo que pide
        permiso ANTES de importarlos. Las aprobaciones se guardan en QSettings
        (`plugins/approved`, mapa nombre->huella en JSON).
"""
import hashlib
import importlib.util
import json
import os
import sys

from app_paths import base_datos


def dir_plugins_incluidos():
    """Carpeta de los plugins de ejemplo que viajan con Imago (solo lectura).

    En desarrollo: <carpeta del código>/plugins.
    Congelado (PyInstaller): la carpeta de datos empaquetados (sys._MEIPASS), que
    en el build one-folder es <exe>/_internal; ahí deja los 'datas' del spec."""
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        return os.path.join(base, "plugins")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "plugins")


def dir_plugins_usuario():
    """Carpeta donde el usuario deja sus plugins de terceros (se crea si falta)."""
    base = base_datos()
    if not base:
        return None
    d = os.path.join(base, "plugins")
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        pass
    return d


class PluginManager:
    def __init__(self, main_window, log=None):
        self.main_window = main_window
        # `log` escribe en imago_crash.log; si no se pasa, se silencia.
        self._log = log or (lambda *_a, **_k: None)
        self.cargados = []          # nombres de plugins cargados con éxito

    def cargar_todos(self):
        """Carga los plugins INCLUIDOS (de confianza) siempre, y los de USUARIO
        solo si el interruptor lo permite y tras pedir consentimiento por los
        nuevos o modificados (huella por plugin)."""
        from plugin_api import API_VERSION
        vistos = set()  # el mismo nombre de USUARIO no re-carga uno ya incluido

        # 1) Incluidos (dentro de Imago): de confianza -> se cargan directamente.
        inc = dir_plugins_incluidos()
        if inc and os.path.isdir(inc):
            for nombre, ruta, init in self._listar(inc, vistos):
                self._cargar_uno(nombre, ruta, init, API_VERSION)

        # 2) De usuario (terceros): sujetos al interruptor y al consentimiento.
        self._cargar_terceros(vistos, API_VERSION)

    # ------------------------------------------------------------- terceros
    def _cargar_terceros(self, vistos, api_actual):
        from app_paths import settings
        s = settings()
        if not s.value("plugins/load_third_party", True, type=bool):
            self._log("[plugins] Plugins de terceros desactivados en "
                      "Preferencias; omitidos.\n")
            return
        carpeta = dir_plugins_usuario()
        if not carpeta or not os.path.isdir(carpeta):
            return
        candidatos = list(self._listar(carpeta, vistos))
        if not candidatos:
            return

        aprobados = self._leer_aprobados(s)   # {nombre: huella}
        a_cargar, pendientes, huellas = [], [], {}
        for nombre, ruta, init in candidatos:
            h = self._huella(ruta)
            huellas[nombre] = h
            if aprobados.get(nombre) == h:
                a_cargar.append((nombre, ruta, init))   # ya aprobado, sin cambios
            else:
                pendientes.append((nombre, ruta, init))  # nuevo o modificado

        # CONSENTIMIENTO antes de importar (ejecutar) nada nuevo/modificado.
        if pendientes:
            if self._pedir_consentimiento(pendientes):
                for nombre, ruta, init in pendientes:
                    aprobados[nombre] = huellas[nombre]
                    a_cargar.append((nombre, ruta, init))
                self._guardar_aprobados(s, aprobados)
            else:
                nombres = ", ".join(n for n, _r, _i in pendientes)
                self._log("[plugins] El usuario NO autorizó: %s\n" % nombres)

        for nombre, ruta, init in a_cargar:
            self._cargar_uno(nombre, ruta, init, api_actual)

    def _pedir_consentimiento(self, pendientes):
        """Diálogo de permiso para plugins de terceros nuevos/modificados. Devuelve
        True solo si el usuario acepta. Ante cualquier fallo, NO autoriza."""
        try:
            from widgets.custom_titlebar import imago_question
            from PySide6.QtWidgets import QMessageBox
            from i18n import t
            lista = "\n".join("    • " + n for n, _r, _i in pendientes)
            resp = imago_question(self.main_window, t("plugins.consent.title"),
                                  t("plugins.consent.body", lista=lista))
            return resp == QMessageBox.Yes
        except Exception:
            import traceback
            self._log("[plugins] Fallo al pedir consentimiento:\n%s\n"
                      % traceback.format_exc())
            return False

    # ------------------------------------------------------ huella / aprobados
    def _huella(self, ruta):
        """SHA-256 del contenido de TODOS los archivos del plugin (ruta relativa +
        bytes, en orden estable), ignorando cachés. Cambia si cambia cualquier
        archivo -> vuelve a pedir consentimiento."""
        archivos = []
        for r, _dirs, files in os.walk(ruta):
            if "__pycache__" in r.split(os.sep):
                continue
            for f in files:
                if f.endswith(".pyc"):
                    continue
                archivos.append(os.path.join(r, f))
        archivos.sort(key=lambda p: os.path.relpath(p, ruta).replace(os.sep, "/"))
        h = hashlib.sha256()
        for p in archivos:
            rel = os.path.relpath(p, ruta).replace(os.sep, "/")
            try:
                with open(p, "rb") as fh:
                    data = fh.read()
            except OSError:
                data = b""
            h.update(rel.encode("utf-8", "replace") + b"\0")
            h.update(data + b"\0")
        return h.hexdigest()

    def _leer_aprobados(self, s):
        raw = s.value("plugins/approved", "", type=str)
        if not raw:
            return {}
        try:
            d = json.loads(raw)
            return d if isinstance(d, dict) else {}
        except (ValueError, TypeError):
            return {}

    def _guardar_aprobados(self, s, d):
        s.setValue("plugins/approved", json.dumps(d))

    # ----------------------------------------------------------- carga común
    def _listar(self, carpeta, vistos):
        """Devuelve (nombre, ruta, init) de cada subcarpeta que es un plugin
        válido (tiene __init__.py) y cuyo nombre no se haya visto ya."""
        for nombre in sorted(os.listdir(carpeta)):
            ruta = os.path.join(carpeta, nombre)
            init = os.path.join(ruta, "__init__.py")
            if not os.path.isdir(ruta) or not os.path.isfile(init):
                continue
            if nombre in vistos:
                continue
            vistos.add(nombre)
            yield nombre, ruta, init

    def _cargar_uno(self, nombre, ruta, init, api_actual):
        try:
            manifest = {}
            mf = os.path.join(ruta, "manifest.json")
            if os.path.isfile(mf):
                with open(mf, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
            req = int(manifest.get("api_version", 1))
            if req > api_actual:
                self._log("[plugins] '%s' pide api_version %d > %d soportada; "
                          "omitido.\n" % (nombre, req, api_actual))
                return
            mod = self._importar(nombre, ruta, init)
            registrar = getattr(mod, "registrar", None)
            if not callable(registrar):
                self._log("[plugins] '%s' no define registrar(api); omitido.\n"
                          % nombre)
                return
            from plugin_api import ImagoPluginAPI
            api = ImagoPluginAPI(self.main_window, plugin_id=nombre)
            registrar(api)
            self.cargados.append(nombre)
        except Exception:
            import traceback
            self._log("[plugins] Error cargando '%s':\n%s\n"
                      % (nombre, traceback.format_exc()))

    def _importar(self, nombre, ruta, init):
        """Importa el __init__.py del plugin como paquete aislado (con __path__,
        para que admita módulos auxiliares con imports relativos)."""
        mod_name = "imago_plugin_" + nombre
        spec = importlib.util.spec_from_file_location(
            mod_name, init, submodule_search_locations=[ruta])
        mod = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)
        return mod
