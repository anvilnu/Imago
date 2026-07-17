# ai/runner.py
"""Ejecucion de trabajos pesados (inferencia ONNX, descargas) FUERA del hilo
principal (regla de oro de Qt).

Piezas:
  - InferenceRunner: envuelve un QThreadPool y expone submit(fn, on_done,
    on_error, on_progress) con senales Qt, cancelacion cooperativa y entrega de
    los callbacks SIEMPRE en el hilo GUI.
  - Cache de InferenceSession (crear una sesion ONNX es caro: se reutiliza).
  - onnx_available() / get_session() con import PEREZOSO de onnxruntime, para que
    Imago arranque aunque onnxruntime no este instalado.

Contrato de la funcion de trabajo (se ejecuta en el hilo secundario):

    def trabajo(report_progress, token):
        # report_progress(0..100) para la barra de progreso (opcional).
        # token.cancelled -> True si se pidio cancelar: comprobarlo en bucles
        #   largos y salir cuanto antes.
        ...
        return resultado

El resultado se entrega a on_done EN EL HILO GUI. Los errores (excepciones) se
entregan a on_error como texto. Una tarea cancelada NO invoca on_done/on_error.
"""

import uuid

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot


# ------------------------------------------------------------------ cancelacion
class CancelToken:
    """Testigo de cancelacion cooperativa. El trabajo consulta `cancelled`."""

    def __init__(self):
        self.cancelled = False

    def cancel(self):
        self.cancelled = True


class TaskHandle:
    """Devuelto por submit(). Permite cancelar la tarea en curso."""

    def __init__(self, task_id, token, runner):
        self.task_id = task_id
        self._token = token
        self._runner = runner

    def cancel(self):
        self._token.cancel()

    @property
    def cancelled(self):
        return self._token.cancelled


# --------------------------------------------------------------------- senales
class _Signals(QObject):
    """Puente de senales worker -> GUI. Vive en el hilo que crea el runner (GUI),
    asi la entrega desde el hilo secundario es en cola (queued) hacia la GUI."""

    finished = Signal(str, object)   # (task_id, resultado)
    failed = Signal(str, str)        # (task_id, mensaje de error)
    progress = Signal(str, int)      # (task_id, porcentaje 0..100)


class _Worker(QRunnable):
    def __init__(self, task_id, fn, token, signals):
        super().__init__()
        self._task_id = task_id
        self._fn = fn
        self._token = token
        self._signals = signals

    @Slot()
    def run(self):
        def report(pct):
            self._signals.progress.emit(self._task_id, int(pct))
        try:
            result = self._fn(report, self._token)
        except Exception as exc:                      # noqa: BLE001 (se reporta)
            self._signals.failed.emit(self._task_id, str(exc))
            return
        self._signals.finished.emit(self._task_id, result)


class InferenceRunner(QObject):
    """Cola de trabajos en segundo plano. Crear en el hilo GUI.

    max_threads=1 por defecto: la inferencia es intensiva; serializarla evita
    saturar la CPU y hace el progreso predecible. Se puede subir si hace falta.
    """

    def __init__(self, parent=None, max_threads=1):
        super().__init__(parent)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(max(1, int(max_threads)))
        # _Signals se crea aqui (hilo GUI) -> afinidad GUI -> callbacks en GUI.
        self._signals = _Signals()
        self._signals.finished.connect(self._on_finished)
        self._signals.failed.connect(self._on_failed)
        self._signals.progress.connect(self._on_progress)
        self._tasks = {}   # task_id -> {done, error, progress, token}

    def submit(self, fn, on_done=None, on_error=None, on_progress=None):
        """Encola `fn` (ver contrato en el docstring del modulo). Devuelve un
        TaskHandle con el que cancelar."""
        task_id = uuid.uuid4().hex
        token = CancelToken()
        self._tasks[task_id] = {
            "done": on_done, "error": on_error,
            "progress": on_progress, "token": token,
        }
        self._pool.start(_Worker(task_id, fn, token, self._signals))
        return TaskHandle(task_id, token, self)

    # -- slots en el hilo GUI (entrega en cola desde el worker) ---------------
    @Slot(str, object)
    def _on_finished(self, task_id, result):
        info = self._tasks.pop(task_id, None)
        if info and not info["token"].cancelled and info["done"]:
            info["done"](result)

    @Slot(str, str)
    def _on_failed(self, task_id, message):
        info = self._tasks.pop(task_id, None)
        if info and not info["token"].cancelled and info["error"]:
            info["error"](message)

    @Slot(str, int)
    def _on_progress(self, task_id, pct):
        info = self._tasks.get(task_id)
        if info and not info["token"].cancelled and info["progress"]:
            info["progress"](pct)


# ===========================================================================
#  ONNX Runtime: import PEREZOSO + cache de sesiones
# ===========================================================================
_SESSIONS = {}   # (model_path, providers) -> InferenceSession

# Proveedores FORZADOS para el proceso actual. En el subproceso de inferencia
# (ai/subproc_worker.py) se fija con set_forced_providers ANTES de llamar a la
# funcion ai.*, para que get_session use esos proveedores y NO _auto_providers
# (que leeria QSettings/Qt, innecesario en el hijo). None => autodeteccion normal.
_FORCED_PROVIDERS = None


def set_forced_providers(providers):
    """Fija los proveedores que usara get_session cuando no se le pasen explicitos.
    Lo usa el subproceso de inferencia para imponer GPU o CPU segun decida el
    proceso principal. providers=None restaura la autodeteccion."""
    global _FORCED_PROVIDERS
    _FORCED_PROVIDERS = list(providers) if providers else None


def onnx_available():
    """True si onnxruntime esta instalado. Se comprueba con find_spec (SIN importarlo):
    la inferencia va SIEMPRE en un subproceso (ai/subproc.py), asi el proceso principal
    nunca carga la DLL nativa de onnxruntime y un crash suyo no puede tumbar la GUI."""
    import importlib.util
    return importlib.util.find_spec("onnxruntime") is not None


def _auto_providers():
    """Proveedores de ejecución preferidos: GPU si el build de onnxruntime
    instalado la ofrece (p. ej. DmlExecutionProvider, del paquete
    onnxruntime-directml que se instala en Windows) y el usuario no la ha
    desactivado en Preferencias; si no, CPU. Con el build solo-CPU (Linux/Mac)
    devuelve siempre CPU: todo queda exactamente como hasta ahora."""
    import onnxruntime as ort
    from app_paths import settings as app_settings
    use_gpu = app_settings().value("ai/use_gpu", True, type=bool)
    if use_gpu and "DmlExecutionProvider" in ort.get_available_providers():
        return ["DmlExecutionProvider", "CPUExecutionProvider"]
    return ["CPUExecutionProvider"]


def get_session(model_path, providers=None):
    """Devuelve una InferenceSession CACHEADA para `model_path` (la crea la
    primera vez). Sin `providers` explícitos se autodetectan con
    _auto_providers() (GPU si está disponible, con la CPU siempre detrás como
    respaldo); si la sesión con GPU fallara al crearse (driver, modelo
    incompatible...), se reintenta solo-CPU."""
    import onnxruntime as ort
    if providers is None:
        providers = _FORCED_PROVIDERS or _auto_providers()
    key = (model_path, tuple(providers))
    sess = _SESSIONS.get(key)
    if sess is None:
        # Silenciar los avisos de onnxruntime (nivel 3 = solo errores). Algunos
        # modelos (p. ej. fast-neural-style) declaran sus pesos como "entradas del
        # grafo" y ort emite decenas de warnings inofensivos que inundan la
        # terminal; no afectan al resultado.
        so = ort.SessionOptions()
        so.log_severity_level = 3
        if "DmlExecutionProvider" in providers:
            # Requisito documentado de DirectML: sin patrones de memoria (la
            # asignación la gestiona la GPU).
            so.enable_mem_pattern = False
        try:
            sess = ort.InferenceSession(
                model_path, sess_options=so, providers=list(providers))
        except Exception:
            if list(providers) == ["CPUExecutionProvider"]:
                raise
            # La GPU no pudo con este modelo: red de seguridad solo-CPU.
            sess = get_session(model_path, ["CPUExecutionProvider"])
        _SESSIONS[key] = sess
    return sess


def run_session(session, feeds, output_names=None):
    """Ejecuta session.run() (llamar dentro de la funcion de trabajo, en el hilo
    secundario). `feeds` es {nombre_entrada: array}. Devuelve la lista de salidas."""
    return session.run(output_names, feeds)


def clear_sessions():
    """Vacia la cache de sesiones (para liberar memoria o tras borrar modelos)."""
    _SESSIONS.clear()
