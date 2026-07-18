# models/autosave.py
"""Autoguardado y recuperación ante fallos.

Cada N minutos escribe una copia de recuperación (.imago, capas completas) de
cada pestaña con cambios SIN GUARDAR en una carpeta propia, junto a un manifiesto
session.json. En un cierre LIMPIO esas copias se borran; si quedaron (la app se
cerró de forma inesperada), al arrancar se ofrece recuperarlas.

Reutiliza el formato nativo .imago (models.project_io), así que la recuperación
conserva todas las capas y sus propiedades."""

import os
import json
import weakref
from datetime import datetime
from atomic_io import escribir_atomico
from PySide6.QtCore import QTimer
import app_paths
from ai.runner import InferenceRunner
from models.document_state import documento_pendiente
from models.project_io import crear_instantanea_proyecto, save_project


class AutoSaveManager:
    def __init__(self, main_window, interval_min=3):
        self.main = main_window
        self._counter = 0
        # Una sola cola de E/S para toda la ventana: evita que un autoguardado
        # comprima a la vez que Guardar/Exportar sobre el mismo documento y
        # reduce los picos de CPU, RAM y disco.
        runner = getattr(main_window, "_io_runner", None)
        if runner is None:
            runner = InferenceRunner(main_window)
            main_window._io_runner = runner
        self._runner = runner
        self._handle = None
        self._repetir = False
        self._detenido = False

        base = app_paths.base_datos()
        if not base:
            base = os.path.join(os.path.expanduser("~"), ".imago")
        self.dir = os.path.join(base, "imago_recuperacion")
        try:
            os.makedirs(self.dir, exist_ok=True)
        except OSError:
            pass

        self.timer = QTimer(self.main)
        self.timer.setInterval(max(1, int(interval_min)) * 60 * 1000)
        self.timer.timeout.connect(self.snapshot)

    def start(self):
        self._detenido = False
        self.timer.start()

    def stop(self):
        self._detenido = True
        self.timer.stop()
        if self._handle is not None:
            self._handle.cancel()
            self._handle = None

    # ------------------------------------------------------------------ util
    def _session_path(self):
        return os.path.join(self.dir, "session.json")

    def _iter_canvases(self):
        tabs = self.main.tabs
        for i in range(tabs.count()):
            marker = tabs.widget(i)
            if marker is not None and hasattr(marker, "canvas"):
                yield i, marker.canvas

    def _notificar_estado(self, estado, hora=None):
        """Actualiza el indicador sin acoplar el gestor a widgets concretos.

        Todas las llamadas del flujo normal ocurren en el hilo GUI: ``snapshot``
        parte del temporizador y los callbacks del runner vuelven a dicho hilo.
        """
        callback = getattr(self.main, "actualizar_estado_autoguardado", None)
        if callable(callback):
            callback(estado, hora)

    @staticmethod
    def _needs_recovery(canvas):
        """Una pestaña necesita copia si tiene cambios sin guardar (pila de
        deshacer no 'limpia') o es un documento recuperado aún sin guardar."""
        return documento_pendiente(canvas)

    # --------------------------------------------------------------- escribir
    def snapshot(self):
        """Captura rápido en GUI y comprime/escribe en el worker de E/S."""
        # Los tests y consumidores mínimos que construyen la clase con __new__
        # conservan el camino síncrono histórico.
        if not hasattr(self, "_runner"):
            return self._snapshot_sincrono()
        if self._detenido:
            return None
        if self._handle is not None:
            self._repetir = True
            return None

        trabajos = []
        entries = []
        keep = set()
        hay_pendientes = False
        for i, canvas in self._iter_canvases():
            if not self._needs_recovery(canvas):
                continue
            hay_pendientes = True
            if not hasattr(canvas, "_autosave_id"):
                self._counter += 1
                canvas._autosave_id = self._counter
            fname = "doc_%d.imago" % canvas._autosave_id
            path = os.path.join(self.dir, fname)
            revision = canvas.revision_autoguardado
            if (getattr(canvas, "_autosave_revision", None) != revision
                    or not os.path.exists(path)):
                trabajos.append({
                    "canvas": weakref.ref(canvas),
                    "revision": revision,
                    "path": path,
                    "snapshot": crear_instantanea_proyecto(canvas),
                })
            entries.append({
                "file": fname,
                "title": self.main.tabs.tabText(i),
                "project_path": getattr(canvas, "project_path", None),
            })
            keep.add(fname)

        if not hay_pendientes:
            self.clear()
            return None

        self._notificar_estado("guardando")

        def trabajo(_report, token):
            snapshot_completo = True
            guardados = []
            for item in trabajos:
                if token.cancelled:
                    return None
                ok = save_project(item["snapshot"], item["path"], token=token)
                guardados.append((item["canvas"], item["revision"], ok))
                if not ok:
                    snapshot_completo = False

            # Una copia fallida que ya tenía versión anterior se conserva, pero
            # no se publica un manifiesto que mezcle revisiones distintas.
            if any(not os.path.exists(os.path.join(self.dir, e["file"]))
                   for e in entries):
                snapshot_completo = False
            publicado = False
            if entries and snapshot_completo and not token.cancelled:
                def _escribir_session(ruta_temporal):
                    with open(ruta_temporal, "w", encoding="utf-8") as f:
                        json.dump({"entries": entries}, f, ensure_ascii=False)
                    return not token.cancelled

                publicado = escribir_atomico(
                    self._session_path(), _escribir_session)
                if publicado and not token.cancelled:
                    self._prune(keep)
            return guardados, publicado

        def terminado(resultado):
            self._handle = None
            if resultado is not None:
                guardados, publicado = resultado
                for ref_canvas, revision, ok in guardados:
                    canvas = ref_canvas()
                    if publicado and ok and canvas is not None:
                        if canvas.revision_autoguardado == revision:
                            canvas._autosave_revision = revision
                        else:
                            # Hubo otra edición mientras se comprimía la copia:
                            # encadenar una instantánea de la revisión nueva.
                            self._repetir = True
                if publicado:
                    self._notificar_estado(
                        "guardado", datetime.now().strftime("%H:%M:%S"))
                else:
                    self._notificar_estado("error")
            self._programar_repeticion()

        def error(_mensaje):
            self._handle = None
            self._notificar_estado("error")
            self._programar_repeticion()

        self._handle = self._runner.submit(
            trabajo, on_done=terminado, on_error=error)
        return None

    def _programar_repeticion(self):
        if self._repetir and not self._detenido:
            self._repetir = False
            QTimer.singleShot(0, self.snapshot)

    def _snapshot_sincrono(self):
        """Escribe copias de las pestañas con cambios sin guardar + el manifiesto.
        Solo reescribe un documento si cambió desde la última copia (ahorra disco).

        La revisión es monotónica e independiente de QUndoStack.index(): dos
        ramas distintas del historial pueden ocupar el mismo índice.
        """
        entries = []
        keep = set()
        hay_pendientes = False
        snapshot_completo = True
        for i, canvas in self._iter_canvases():
            if not self._needs_recovery(canvas):
                continue
            hay_pendientes = True
            if not hasattr(canvas, "_autosave_id"):
                self._counter += 1
                canvas._autosave_id = self._counter
            fname = "doc_%d.imago" % canvas._autosave_id
            path = os.path.join(self.dir, fname)
            revision = canvas.revision_autoguardado
            if (getattr(canvas, "_autosave_revision", None) != revision
                    or not os.path.exists(path)):
                if save_project(canvas, path):
                    canvas._autosave_revision = revision
                else:
                    snapshot_completo = False
            # Si la copia nueva falló pero había una anterior, se conserva y se
            # mantiene en el manifiesto. Sin ningún archivo válido no se anuncia.
            if not os.path.exists(path):
                snapshot_completo = False
                continue
            entries.append({
                "file": fname,
                "title": self.main.tabs.tabText(i),
                "project_path": getattr(canvas, "project_path", None),
            })
            keep.add(fname)

        if hay_pendientes:
            self._notificar_estado("guardando")

        if entries and snapshot_completo:
            def _escribir_session(ruta_temporal):
                with open(ruta_temporal, "w", encoding="utf-8") as f:
                    json.dump({"entries": entries}, f, ensure_ascii=False)
                return True

            # Solo se podan copias antiguas después de publicar el manifiesto
            # nuevo. Si falla, el session.json anterior y sus documentos siguen
            # formando un conjunto recuperable coherente.
            if escribir_atomico(self._session_path(), _escribir_session):
                self._prune(keep)
                self._notificar_estado(
                    "guardado", datetime.now().strftime("%H:%M:%S"))
            else:
                self._notificar_estado("error")
        elif hay_pendientes:
            self._notificar_estado("error")
        elif not hay_pendientes:
            self.clear()

    def _prune(self, keep):
        """Borra las copias .imago de pestañas que ya no necesitan recuperación."""
        try:
            for fn in os.listdir(self.dir):
                if fn.startswith("doc_") and fn.endswith(".imago") and fn not in keep:
                    try:
                        os.remove(os.path.join(self.dir, fn))
                    except OSError:
                        pass
        except OSError:
            pass

    def clear(self):
        """Borra TODAS las copias (cierre limpio o nada pendiente de recuperar)."""
        try:
            for fn in os.listdir(self.dir):
                try:
                    os.remove(os.path.join(self.dir, fn))
                except OSError:
                    pass
        except OSError:
            pass

    # -------------------------------------------------------------- recuperar
    def pending_entries(self):
        """Lista de documentos recuperables de una sesión anterior (o [] si no hay).
        Cada entrada incluye 'path' (ruta de la copia .imago), 'title', 'project_path'."""
        sp = self._session_path()
        if not os.path.exists(sp):
            return []
        try:
            with open(sp, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return []
        out = []
        for e in data.get("entries", []):
            fp = os.path.join(self.dir, e.get("file", ""))
            if os.path.exists(fp):
                e = dict(e)
                e["path"] = fp
                out.append(e)
        return out
