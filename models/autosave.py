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
from atomic_io import escribir_atomico
from PySide6.QtCore import QTimer
import app_paths
from models.document_state import documento_pendiente
from models.project_io import save_project


class AutoSaveManager:
    def __init__(self, main_window, interval_min=3):
        self.main = main_window
        self._counter = 0

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
        self.timer.start()

    def stop(self):
        self.timer.stop()

    # ------------------------------------------------------------------ util
    def _session_path(self):
        return os.path.join(self.dir, "session.json")

    def _iter_canvases(self):
        tabs = self.main.tabs
        for i in range(tabs.count()):
            marker = tabs.widget(i)
            if marker is not None and hasattr(marker, "canvas"):
                yield i, marker.canvas

    @staticmethod
    def _needs_recovery(canvas):
        """Una pestaña necesita copia si tiene cambios sin guardar (pila de
        deshacer no 'limpia') o es un documento recuperado aún sin guardar."""
        return documento_pendiente(canvas)

    # --------------------------------------------------------------- escribir
    def snapshot(self):
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
