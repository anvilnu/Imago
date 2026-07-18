"""Banco headless reproducible de las rutas críticas del editor.

Ejemplo::

    python -m benchmarks.benchmark_editor --perfil estandar --salida resultado.json
"""

import argparse
import gc
import json
import math
import os
import platform
import statistics
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PySide6 import __version__ as PYSIDE_VERSION
from PySide6.QtCore import QCoreApplication, QEvent, QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QUndoCommand
from PySide6.QtWidgets import (QApplication, QScrollArea, QTabWidget, QWidget)

from adjustments import apply_gaussian_blur
from models.autosave import AutoSaveManager
from models.layer import Layer
from models.project_io import crear_instantanea_proyecto, save_project
from tools.draw_tools import PenTool
from widgets.canvas import Canvas
from widgets.history_panel import HistoryPanel
from widgets.layers_panel import LayersPanel
from widgets.tab_thumbnails import TabThumbnailBar


VERSION_BANCO = 1
SEMILLA = 20_260_718
PERFILES = {
    "rapido": {
        "ancho": 320, "alto": 240, "capas": 3, "pestanas": 3,
        "movimientos": 8, "radio_efecto": 2.0,
        "repeticiones": 2, "calentamientos": 1,
    },
    "estandar": {
        "ancho": 1024, "alto": 768, "capas": 8, "pestanas": 4,
        "movimientos": 24, "radio_efecto": 4.0,
        "repeticiones": 5, "calentamientos": 1,
    },
    "grande": {
        "ancho": 2048, "alto": 1536, "capas": 16, "pestanas": 5,
        "movimientos": 48, "radio_efecto": 6.0,
        "repeticiones": 3, "calentamientos": 1,
    },
}
METRICAS_ESPERADAS = (
    "trazo_inicio_ms", "trazo_movimiento_ms", "trazo_fin_ms",
    "pestana_cambio_ms", "pestana_cierre_ms", "composicion_ms",
    "efecto_gaussiano_ms", "guardado_imago_ms", "autoguardado_ms",
)


class _Evento:
    def __init__(self, x, y, boton=Qt.MouseButton.LeftButton,
                 botones=Qt.MouseButton.LeftButton):
        self._posicion = QPointF(float(x), float(y))
        self._boton = boton
        self._botones = botones

    def position(self):
        return QPointF(self._posicion)

    def button(self):
        return self._boton

    def buttons(self):
        return self._botones

    def modifiers(self):
        return Qt.KeyboardModifier.NoModifier


class _PestanasAutoguardado:
    def __init__(self, canvas):
        self.canvas = canvas

    def count(self):
        return 1

    def widget(self, _indice):
        return type("Marcador", (), {"canvas": self.canvas})()

    def tabText(self, _indice):
        return "Banco de rendimiento"


class _PrincipalAutoguardado:
    def __init__(self, canvas):
        self.tabs = _PestanasAutoguardado(canvas)


class _PrincipalPestanas:
    def __init__(self, tabs):
        self.tabs = tabs

    def close_tab(self, _indice):
        pass

    def update_tab_tooltip(self, _indice, _miniatura=None):
        pass


def _rss_bytes():
    """Memoria residente nativa actual sin añadir una dependencia a psutil."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class _Contadores(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
                ("PrivateUsage", ctypes.c_size_t),
            ]

        contadores = _Contadores()
        contadores.cb = ctypes.sizeof(contadores)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = (
            wintypes.HANDLE, ctypes.POINTER(_Contadores), wintypes.DWORD)
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        proceso = kernel32.GetCurrentProcess()
        ok = psapi.GetProcessMemoryInfo(
            proceso, ctypes.byref(contadores), contadores.cb)
        return int(contadores.WorkingSetSize) if ok else 0

    if sys.platform.startswith("linux"):
        try:
            with open("/proc/self/statm", "r", encoding="ascii") as archivo:
                paginas = int(archivo.read().split()[1])
            return paginas * os.sysconf("SC_PAGE_SIZE")
        except (OSError, ValueError, IndexError):
            return 0

    try:
        import resource
        valor = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        return valor if sys.platform == "darwin" else valor * 1024
    except (ImportError, ValueError):
        return 0


def _ram_total_bytes():
    if sys.platform == "win32":
        import ctypes

        class _EstadoMemoria(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        estado = _EstadoMemoria()
        estado.dwLength = ctypes.sizeof(estado)
        return (int(estado.ullTotalPhys)
                if ctypes.windll.kernel32.GlobalMemoryStatusEx(
                    ctypes.byref(estado)) else 0)
    try:
        return int(os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE"))
    except (AttributeError, OSError, ValueError):
        return 0


class _MuestreadorRSS:
    def __init__(self, intervalo=0.002):
        self.intervalo = intervalo
        self.inicial = _rss_bytes()
        self.pico = self.inicial
        self._detener = threading.Event()
        self._hilo = None

    def _muestrear(self):
        while not self._detener.wait(self.intervalo):
            self.pico = max(self.pico, _rss_bytes())

    def __enter__(self):
        self._hilo = threading.Thread(
            target=self._muestrear, name="imago-benchmark-rss", daemon=True)
        self._hilo.start()
        return self

    def __exit__(self, *_args):
        self.pico = max(self.pico, _rss_bytes())
        self._detener.set()
        self._hilo.join(timeout=1.0)


@contextmanager
def _sin_gc():
    activo = gc.isenabled()
    if activo:
        gc.disable()
    try:
        yield
    finally:
        if activo:
            gc.enable()


def _resumen(muestras, unidad="ms"):
    valores = [float(valor) for valor in muestras]
    return {
        "unidad": unidad,
        "mediana": round(statistics.median(valores), 4),
        "minimo": round(min(valores), 4),
        "maximo": round(max(valores), 4),
        "muestras": [round(valor, 4) for valor in valores],
    }


def _medir(operacion, repeticiones, calentamientos=0, despues=None):
    for _ in range(calentamientos):
        operacion()
        if despues:
            despues()
    gc.collect()
    muestras = []
    with _sin_gc():
        for _ in range(repeticiones):
            inicio = time.perf_counter_ns()
            operacion()
            muestras.append((time.perf_counter_ns() - inicio) / 1_000_000.0)
            if despues:
                despues()
    return _resumen(muestras)


def _crear_documento(ancho, alto, numero_capas):
    """Documento determinista, con alfa y geometría distinta en cada capa."""
    canvas = Canvas(ancho, alto)
    canvas.layers[0].name = "Capa 1"
    for indice in range(1, numero_capas):
        canvas.layers.append(Layer(ancho, alto, f"Capa {indice + 1}"))
    canvas.layer_counter = numero_capas
    canvas.active_layer_index = numero_capas - 1
    canvas.selected_layer_indices = [canvas.active_layer_index]

    for indice, capa in enumerate(canvas.layers):
        capa.image.fill(Qt.GlobalColor.transparent)
        pintor = QPainter(capa.image)
        color = QColor(
            (37 * indice + 40) % 256,
            (83 * indice + 70) % 256,
            (131 * indice + 20) % 256,
            150 + (indice % 4) * 25,
        )
        margen_x = (indice * 17) % max(1, ancho // 5)
        margen_y = (indice * 23) % max(1, alto // 5)
        pintor.fillRect(
            margen_x, margen_y,
            max(1, ancho - 2 * margen_x),
            max(1, alto - 2 * margen_y), color)
        pintor.end()
        capa.opacity = 70 + (indice % 4) * 10
    canvas.brush_size = max(5, min(31, ancho // 40))
    canvas.brush_hardness = 80
    canvas.brush_opacity = 75
    return canvas


def _medir_trazo(canvas, configuracion):
    repeticiones = configuracion["repeticiones"]
    calentamientos = configuracion["calentamientos"]
    movimientos = configuracion["movimientos"]
    inicio_muestras, movimiento_muestras, fin_muestras = [], [], []
    total = repeticiones + calentamientos
    gc.collect()
    with _sin_gc():
        for vuelta in range(total):
            herramienta = PenTool(canvas)
            x0, y0 = canvas.base_width * 0.2, canvas.base_height * 0.3
            x1, y1 = canvas.base_width * 0.8, canvas.base_height * 0.7
            evento_inicio = _Evento(x0, y0)
            eventos = [
                _Evento(x0 + (x1 - x0) * paso / movimientos,
                        y0 + (y1 - y0) * paso / movimientos)
                for paso in range(1, movimientos + 1)
            ]

            reloj = time.perf_counter_ns()
            herramienta.mouse_press(evento_inicio)
            tiempo_inicio = (time.perf_counter_ns() - reloj) / 1_000_000.0

            reloj = time.perf_counter_ns()
            for evento in eventos:
                herramienta.mouse_move(evento)
            tiempo_movimiento = (
                (time.perf_counter_ns() - reloj) / 1_000_000.0 / movimientos)

            evento_fin = _Evento(
                x1, y1, botones=Qt.MouseButton.NoButton)
            reloj = time.perf_counter_ns()
            herramienta.mouse_release(evento_fin)
            tiempo_fin = (time.perf_counter_ns() - reloj) / 1_000_000.0

            canvas.undo_stack.undo()
            canvas.undo_stack.clear()
            if vuelta >= calentamientos:
                inicio_muestras.append(tiempo_inicio)
                movimiento_muestras.append(tiempo_movimiento)
                fin_muestras.append(tiempo_fin)
    return {
        "trazo_inicio_ms": _resumen(inicio_muestras),
        "trazo_movimiento_ms": _resumen(movimiento_muestras),
        "trazo_fin_ms": _resumen(fin_muestras),
    }


def _crear_pestana(ancho, alto, capas=1):
    canvas = _crear_documento(ancho, alto, capas)
    scroll = QScrollArea()
    scroll.setWidget(canvas)
    scroll.canvas = canvas
    marcador = QWidget()
    marcador.canvas = canvas
    marcador.scroll_area = scroll
    return marcador


def _destruir_pestana(tabs, indice):
    marcador = tabs.widget(indice)
    canvas = marcador.canvas
    scroll = marcador.scroll_area
    tabs.removeTab(indice)
    scroll.takeWidget()
    scroll.canvas = None
    marcador.canvas = None
    marcador.scroll_area = None
    scroll.deleteLater()
    canvas.deleteLater()
    marcador.deleteLater()
    QCoreApplication.sendPostedEvents(
        None, QEvent.Type.DeferredDelete)
    QApplication.processEvents()


def _medir_pestanas(configuracion):
    ancho = min(configuracion["ancho"], 640)
    alto = min(configuracion["alto"], 480)
    tabs = QTabWidget()
    for indice in range(configuracion["pestanas"]):
        tabs.addTab(
            _crear_pestana(ancho, alto, configuracion["capas"]),
            f"Documento {indice + 1}")

    principal = _PrincipalPestanas(tabs)
    barra_miniaturas = TabThumbnailBar(principal)
    barra_miniaturas.rebuild()
    canvas_inicial = tabs.widget(0).canvas
    panel_capas = LayersPanel(canvas_inicial)
    estado = {"historial": HistoryPanel(canvas_inicial)}

    siguiente = {"indice": 0}

    def cambiar():
        siguiente["indice"] = (
            siguiente["indice"] + 1) % tabs.count()
        tabs.setCurrentIndex(siguiente["indice"])
        canvas = tabs.widget(siguiente["indice"]).canvas
        panel_capas.detach_canvas()
        panel_capas.canvas = canvas
        panel_capas.update_layer_list()
        anterior = estado["historial"]
        anterior.detach()
        estado["historial"] = HistoryPanel(canvas)
        anterior.deleteLater()
        barra_miniaturas.rebuild()
        QApplication.processEvents()

    cambio = _medir(
        cambiar, configuracion["repeticiones"],
        configuracion["calentamientos"])

    cierres = []
    for _ in range(configuracion["calentamientos"] +
                   configuracion["repeticiones"]):
        tabs.addTab(
            _crear_pestana(ancho, alto, configuracion["capas"]), "Temporal")
        indice = tabs.count() - 1
        reloj = time.perf_counter_ns()
        _destruir_pestana(tabs, indice)
        valor = (time.perf_counter_ns() - reloj) / 1_000_000.0
        if len(cierres) >= configuracion["repeticiones"]:
            continue
        if _ >= configuracion["calentamientos"]:
            cierres.append(valor)

    panel_capas.detach_canvas()
    estado["historial"].detach()
    panel_capas.deleteLater()
    estado["historial"].deleteLater()
    barra_miniaturas.deleteLater()
    while tabs.count():
        _destruir_pestana(tabs, tabs.count() - 1)
    tabs.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    return {
        "pestana_cambio_ms": cambio,
        "pestana_cierre_ms": _resumen(cierres),
    }


def _medir_documento(canvas, configuracion, carpeta_temporal):
    repeticiones = configuracion["repeticiones"]
    calentamientos = configuracion["calentamientos"]
    metricas = {}
    metricas["composicion_ms"] = _medir(
        lambda: canvas.render_flat_image(Qt.GlobalColor.transparent),
        repeticiones, calentamientos)

    rng = np.random.default_rng(SEMILLA)
    array = rng.integers(
        0, 256, size=(canvas.base_height, canvas.base_width, 4),
        dtype=np.uint8)
    array[:, :, 3] = 255
    metricas["efecto_gaussiano_ms"] = _medir(
        lambda: apply_gaussian_blur(
            array, configuracion["radio_efecto"]),
        repeticiones, calentamientos)

    instantanea = crear_instantanea_proyecto(canvas)
    ruta_guardado = os.path.join(carpeta_temporal, "banco.imago")

    def guardar():
        if not save_project(instantanea, ruta_guardado):
            raise RuntimeError("Falló el guardado .imago durante el benchmark")

    metricas["guardado_imago_ms"] = _medir(
        guardar, repeticiones, calentamientos)

    canvas.undo_stack.push(QUndoCommand("Banco de rendimiento"))
    manager = AutoSaveManager.__new__(AutoSaveManager)
    manager.dir = os.path.join(carpeta_temporal, "recuperacion")
    os.makedirs(manager.dir, exist_ok=True)
    manager.main = _PrincipalAutoguardado(canvas)
    manager._counter = 0
    manager._entradas_diferidas = []

    def autoguardar():
        canvas.revision_autoguardado += 1
        manager.snapshot()
        if not os.path.exists(manager._session_path()):
            raise RuntimeError("El autoguardado no publicó session.json")

    metricas["autoguardado_ms"] = _medir(
        autoguardar, repeticiones, calentamientos)
    return metricas


def _entorno():
    total_ram = _ram_total_bytes()
    return {
        "sistema": platform.platform(),
        "plataforma": sys.platform,
        "maquina": platform.machine(),
        "procesador": platform.processor() or "desconocido",
        "nucleos_logicos": os.cpu_count(),
        "ram_total_mib": round(total_ram / (1024 ** 2), 1) if total_ram else None,
        "python": platform.python_version(),
        "pyside6": PYSIDE_VERSION,
        "numpy": np.__version__,
        "qt_qpa_platform": os.environ.get("QT_QPA_PLATFORM", ""),
    }


def ejecutar_banco(perfil="estandar", repeticiones=None,
                   calentamientos=None):
    if perfil not in PERFILES:
        raise ValueError(f"Perfil desconocido: {perfil}")
    configuracion = dict(PERFILES[perfil])
    if repeticiones is not None:
        configuracion["repeticiones"] = max(1, int(repeticiones))
    if calentamientos is not None:
        configuracion["calentamientos"] = max(0, int(calentamientos))

    app = QApplication.instance() or QApplication([])
    metricas = {}
    rss_inicial = _rss_bytes()
    inicio_total = time.perf_counter()
    with _MuestreadorRSS() as memoria, tempfile.TemporaryDirectory() as carpeta:
        canvas = _crear_documento(
            configuracion["ancho"], configuracion["alto"],
            configuracion["capas"])
        metricas.update(_medir_trazo(canvas, configuracion))
        metricas.update(_medir_pestanas(configuracion))
        metricas.update(_medir_documento(canvas, configuracion, carpeta))
        canvas.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()

    faltantes = sorted(set(METRICAS_ESPERADAS) - set(metricas))
    if faltantes:
        raise RuntimeError("Métricas ausentes: " + ", ".join(faltantes))
    return {
        "version_banco": VERSION_BANCO,
        "fecha_utc": datetime.now(timezone.utc).isoformat(),
        "perfil": perfil,
        "semilla": SEMILLA,
        "configuracion": configuracion,
        "entorno": _entorno(),
        "memoria": {
            "rss_inicial_mib": round(rss_inicial / (1024 ** 2), 3),
            "rss_pico_mib": round(memoria.pico / (1024 ** 2), 3),
            "incremento_pico_mib": round(
                max(0, memoria.pico - rss_inicial) / (1024 ** 2), 3),
        },
        "duracion_total_s": round(time.perf_counter() - inicio_total, 3),
        "metricas": metricas,
    }


def comparar_resultados(actual, referencia, tolerancia=0.35,
                        margen_absoluto_ms=0.25,
                        margen_absoluto_mib=8.0):
    """Devuelve regresiones que superan el margen relativo Y el absoluto."""
    if actual.get("perfil") != referencia.get("perfil"):
        raise ValueError("Los resultados usan perfiles distintos")
    regresiones = []
    for nombre in METRICAS_ESPERADAS:
        valor_actual = actual["metricas"][nombre]["mediana"]
        valor_base = referencia["metricas"][nombre]["mediana"]
        limite = max(
            valor_base * (1.0 + float(tolerancia)),
            valor_base + float(margen_absoluto_ms),
        )
        if valor_actual > limite and not math.isclose(valor_actual, limite):
            regresiones.append({
                "metrica": nombre,
                "unidad": "ms",
                "base": valor_base,
                "actual": valor_actual,
                "limite": round(limite, 4),
                "incremento_pct": round(
                    (valor_actual / valor_base - 1.0) * 100.0, 2)
                if valor_base else None,
            })
    memoria_actual = actual.get("memoria", {}).get("incremento_pico_mib")
    memoria_base = referencia.get("memoria", {}).get("incremento_pico_mib")
    if memoria_actual is not None and memoria_base is not None:
        limite = max(
            memoria_base * (1.0 + float(tolerancia)),
            memoria_base + float(margen_absoluto_mib),
        )
        if memoria_actual > limite and not math.isclose(memoria_actual, limite):
            regresiones.append({
                "metrica": "incremento_pico_mib",
                "unidad": "MiB",
                "base": memoria_base,
                "actual": memoria_actual,
                "limite": round(limite, 4),
                "incremento_pct": round(
                    (memoria_actual / memoria_base - 1.0) * 100.0, 2)
                if memoria_base else None,
            })
    return regresiones


def guardar_resultado(resultado, ruta):
    carpeta = os.path.dirname(os.path.abspath(ruta))
    if carpeta:
        os.makedirs(carpeta, exist_ok=True)
    with open(ruta, "w", encoding="utf-8", newline="\n") as archivo:
        json.dump(resultado, archivo, ensure_ascii=False, indent=2)
        archivo.write("\n")


def _imprimir(resultado):
    cfg = resultado["configuracion"]
    print(
        f"Imago benchmark v{resultado['version_banco']} · {resultado['perfil']} · "
        f"{cfg['ancho']}x{cfg['alto']} · {cfg['capas']} capas")
    for nombre in METRICAS_ESPERADAS:
        dato = resultado["metricas"][nombre]
        print(
            f"  {nombre:<25} {dato['mediana']:>10.4f} ms "
            f"[{dato['minimo']:.4f}, {dato['maximo']:.4f}]")
    memoria = resultado["memoria"]
    print(
        f"  RSS pico                  {memoria['rss_pico_mib']:.3f} MiB "
        f"(+{memoria['incremento_pico_mib']:.3f} MiB)")
    print(f"  Duración total            {resultado['duracion_total_s']:.3f} s")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--perfil", choices=tuple(PERFILES), default="estandar")
    parser.add_argument("--repeticiones", type=int)
    parser.add_argument("--calentamientos", type=int)
    parser.add_argument("--salida", help="Ruta JSON donde guardar el resultado")
    parser.add_argument("--comparar", help="JSON de línea base")
    parser.add_argument("--tolerancia", type=float, default=0.35,
                        help="Incremento admitido al comparar (0.35 = 35 por ciento)")
    parser.add_argument("--margen-absoluto-ms", type=float, default=0.25,
                        help="Margen mínimo para métricas submilisegundo")
    parser.add_argument("--margen-absoluto-mib", type=float, default=8.0,
                        help="Margen mínimo del incremento de RSS")
    args = parser.parse_args(argv)

    resultado = ejecutar_banco(
        args.perfil, args.repeticiones, args.calentamientos)
    _imprimir(resultado)
    if args.salida:
        guardar_resultado(resultado, args.salida)
        print(f"Resultado guardado en: {os.path.abspath(args.salida)}")
    if args.comparar:
        with open(args.comparar, "r", encoding="utf-8") as archivo:
            referencia = json.load(archivo)
        regresiones = comparar_resultados(
            resultado, referencia, args.tolerancia,
            args.margen_absoluto_ms, args.margen_absoluto_mib)
        if regresiones:
            print("Regresiones detectadas:")
            for regresion in regresiones:
                print(
                    f"  {regresion['metrica']}: {regresion['actual']:.4f} "
                    f"{regresion['unidad']} > {regresion['limite']:.4f} "
                    f"{regresion['unidad']}")
            return 1
        print("Sin regresiones respecto a la línea base.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
