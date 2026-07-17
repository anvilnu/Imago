# ai/subproc_worker.py
"""Proceso HIJO que ejecuta UNA funcion de inferencia de IA aislada del proceso
principal. Se lanza con:  python -m ai.subproc_worker <host> <puerto> <authkey_hex>

Motivo (robustez): onnxruntime con el proveedor DirectML puede provocar un
"access violation" NATIVO en modelos pesados (p. ej. SCUNet). Un fallo nativo NO
es capturable con try/except y se llevaria por delante toda la app. Al ejecutar la
inferencia en un proceso aparte, si revienta solo muere ESTE proceso: Imago
sobrevive, lo detecta (el canal se cierra sin resultado) y puede reintentar en CPU.

Canal: multiprocessing.connection (socket local con authkey). El hijo se CONECTA de
vuelta al proceso principal (que hace de Listener) y recibe la peticion
{module, func, args, kwargs, force_cpu}. Responde con mensajes:
    ("progress", pct)   progreso 0..100 (si la funcion lo reporta)
    ("result", obj)     resultado (array numpy u otro objeto picklable)
    ("error", texto)    excepcion de Python capturada
Una caida NATIVA no manda nada: el principal la detecta por el cierre del canal.

Este proceso NO carga PySide6.QtWidgets ni main.py: solo numpy, onnxruntime y el
modulo ai.* concreto (mas ai.runner, que trae QtCore, inofensivo sin GUI).
"""
import sys


def _pick_providers(force_cpu):
    """Elige los proveedores DENTRO del hijo (que si tiene onnxruntime): CPU si se
    fuerza; si no, DirectML cuando este disponible, con CPU siempre de respaldo."""
    if force_cpu:
        return ["CPUExecutionProvider"]
    try:
        import onnxruntime as ort
        if "DmlExecutionProvider" in ort.get_available_providers():
            return ["DmlExecutionProvider", "CPUExecutionProvider"]
    except Exception:
        pass
    return ["CPUExecutionProvider"]


class _RemoteToken:
    """Testigo de cancelacion que consulta el canal: el principal envia "cancel"
    cuando el usuario cancela. Misma interfaz que ai.runner.CancelToken."""

    def __init__(self, conn):
        self._conn = conn
        self._cancelled = False

    @property
    def cancelled(self):
        if not self._cancelled:
            try:
                while self._conn.poll(0):
                    if self._conn.recv() == "cancel":
                        self._cancelled = True
                        break
            except Exception:
                self._cancelled = True   # canal roto: parar cuanto antes
        return self._cancelled

    def cancel(self):
        self._cancelled = True


def _safe_send(conn, msg):
    try:
        conn.send(msg)
    except Exception:
        pass


def _handle(conn):
    import importlib
    import inspect

    req = conn.recv()
    import ai.runner as runner
    # Los proveedores se fijan aqui (el hijo tiene onnxruntime); get_session los usa
    # y NO llama a _auto_providers (asi no se toca QSettings en el hijo).
    runner.set_forced_providers(_pick_providers(req.get("force_cpu", False)))

    mod = importlib.import_module(req["module"])
    fn = getattr(mod, req["func"])
    args = list(req.get("args", ()))
    kwargs = dict(req.get("kwargs", {}))

    # report/token: se inyectan solo si la funcion los acepta. El report manda el
    # progreso por el canal; el token refleja la cancelacion pedida por el principal.
    params = inspect.signature(fn).parameters
    if "report" in params:
        kwargs["report"] = lambda pct: _safe_send(conn, ("progress", int(pct)))
    if "token" in params:
        kwargs["token"] = _RemoteToken(conn)

    result = fn(*args, **kwargs)
    conn.send(("result", result))


def main():
    # NOTA: NO se activa faulthandler aqui. Un crash NATIVO (access violation de
    # DirectML) mata este proceso de forma silenciosa y el principal lo detecta por
    # el codigo de salida; faulthandler solo ensuciaria la terminal con un volcado
    # que ademas no trae pila C ("cannot get C stack on this system").
    host = sys.argv[1]
    port = int(sys.argv[2])
    authkey = bytes.fromhex(sys.argv[3])

    from multiprocessing.connection import Client
    conn = Client((host, port), authkey=authkey)
    try:
        _handle(conn)
    except BaseException as exc:      # noqa: BLE001 (se reporta al principal como texto)
        import traceback
        texto = "".join(traceback.format_exception_only(type(exc), exc)).strip()
        _safe_send(conn, ("error", texto))
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
