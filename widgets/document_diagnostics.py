# widgets/document_diagnostics.py
"""Diagnóstico ligero y bajo demanda del documento activo.

Las métricas recorren objetos y tamaños de buffers ya existentes; nunca leen
píxeles, renderizan capas ni comprimen el proyecto. La ventana no usa
temporizador: cerrada cuesta cero y, visible, una edición solo marca los datos
como pendientes hasta que el usuario pulsa Actualizar.
"""

import os
from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QImage
from PySide6.QtWidgets import (QFormLayout, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout, QWidget)

from i18n import t
from models.document_state import documento_pendiente
from models.layer import TextLayer, grupos_del_lienzo, visible_efectiva
from widgets.custom_titlebar import FramelessDialog
import theme


_EFECTOS_COSTOSOS = {
    "sombra", "sombra_interior", "resplandor", "trazo", "bisel", "satinado",
}
_CLAVES_EFECTOS = {
    "sombra": "fx.layer.shadow",
    "sombra_interior": "fx.layer.inner_shadow",
    "resplandor": "fx.layer.glow",
    "trazo": "fx.layer.stroke",
    "bisel": "fx.layer.bevel",
    "satinado": "fx.layer.satin",
    "superposicion": "fx.layer.color_overlay",
    "degradado": "fx.layer.gradient",
}
_MODULOS_COMANDOS = {"tools.commands", "models.layer_commands"}


@dataclass(frozen=True)
class DiagnosticoDocumento:
    ancho: int
    alto: int
    capas: int
    capas_visibles: int
    capas_texto: int
    mascaras: int
    grupos: int
    memoria_bytes: int
    proyecto_bruto_bytes: int
    archivo_bytes: Optional[int]
    archivo_desactualizado: bool
    efectos_activos: int
    capas_con_efectos: int
    efectos_costosos: tuple


def _sumar_imagen(imagen, claves, tamanos):
    """Registra una QImage una sola vez aunque existan copias implícitas."""
    if not isinstance(imagen, QImage) or imagen.isNull():
        return
    clave = int(imagen.cacheKey())
    if clave not in claves:
        claves.add(clave)
        tamanos.append(int(imagen.sizeInBytes()))


def _sumar_imagenes_comando(valor, claves, tamanos, visitados, profundidad=0):
    """Busca QImage en comandos de undo sin recorrer canvas, capas ni widgets."""
    if isinstance(valor, QImage):
        _sumar_imagen(valor, claves, tamanos)
        return
    if profundidad > 6 or valor is None or isinstance(
            valor, (str, bytes, int, float, bool)):
        return
    identidad = id(valor)
    if identidad in visitados:
        return
    visitados.add(identidad)
    if isinstance(valor, dict):
        elementos = valor.values()
    elif isinstance(valor, (list, tuple, set)):
        elementos = valor
    elif valor.__class__.__module__ in _MODULOS_COMANDOS:
        elementos = getattr(valor, "__dict__", {}).values()
    else:
        return
    for elemento in elementos:
        _sumar_imagenes_comando(
            elemento, claves, tamanos, visitados, profundidad + 1)


def analizar_documento(canvas):
    """Devuelve métricas O(capas + historial), sin trabajo proporcional a píxeles."""
    capas = list(getattr(canvas, "layers", ()))

    proyecto_bruto = 0
    claves_memoria, tamanos_memoria = set(), []
    for capa in capas:
        for imagen in (getattr(capa, "image", None),
                       getattr(capa, "mask", None)):
            if isinstance(imagen, QImage) and not imagen.isNull():
                # El .imago escribe una entrada PNG por capa/máscara aunque dos
                # QImage compartan memoria, por eso aquí no se deduplican.
                proyecto_bruto += int(imagen.sizeInBytes())
            _sumar_imagen(imagen, claves_memoria, tamanos_memoria)
    proyecto_bruto += sum(
        len(getattr(capa, "text_html", "").encode("utf-8"))
        for capa in capas if isinstance(capa, TextLayer))
    proyecto_bruto += 1024 + len(capas) * 512

    for capa in capas:
        for atributo in ("_mask_cache", "_fx_cache", "_text_cache"):
            _sumar_imagen(getattr(capa, atributo, None),
                          claves_memoria, tamanos_memoria)
    for atributo in ("selection_soft", "_composed_cache"):
        _sumar_imagen(getattr(canvas, atributo, None),
                      claves_memoria, tamanos_memoria)

    pila = getattr(canvas, "undo_stack", None)
    if pila is not None:
        visitados = set()
        for indice in range(pila.count()):
            _sumar_imagenes_comando(
                pila.command(indice), claves_memoria, tamanos_memoria, visitados)

    activos = []
    capas_con_efectos = 0
    for capa in capas:
        efectos = [efecto for efecto in getattr(capa, "effects", ())
                   if getattr(efecto, "activo", False)]
        if efectos:
            capas_con_efectos += 1
            activos.extend(efectos)
    recuento_costosos = {}
    for efecto in activos:
        tipo = getattr(efecto, "tipo", "")
        if tipo in _EFECTOS_COSTOSOS:
            recuento_costosos[tipo] = recuento_costosos.get(tipo, 0) + 1

    ruta = getattr(canvas, "project_path", None)
    archivo_bytes = None
    if ruta:
        try:
            archivo_bytes = os.path.getsize(ruta)
        except OSError:
            pass

    return DiagnosticoDocumento(
        ancho=int(getattr(canvas, "base_width", 0)),
        alto=int(getattr(canvas, "base_height", 0)),
        capas=len(capas),
        capas_visibles=sum(1 for capa in capas if visible_efectiva(capa)),
        capas_texto=sum(1 for capa in capas if isinstance(capa, TextLayer)),
        mascaras=sum(1 for capa in capas if getattr(capa, "mask", None) is not None),
        grupos=len(grupos_del_lienzo(capas)),
        memoria_bytes=sum(tamanos_memoria),
        proyecto_bruto_bytes=proyecto_bruto,
        archivo_bytes=archivo_bytes,
        archivo_desactualizado=bool(archivo_bytes is not None
                                    and documento_pendiente(canvas)),
        efectos_activos=len(activos),
        capas_con_efectos=capas_con_efectos,
        efectos_costosos=tuple(sorted(recuento_costosos.items())),
    )


def formatear_bytes(cantidad):
    valor = float(max(0, cantidad))
    for unidad in ("B", "KiB", "MiB", "GiB"):
        if valor < 1024.0 or unidad == "GiB":
            decimales = 0 if unidad == "B" else 1
            return f"{valor:.{decimales}f} {unidad}"
        valor /= 1024.0


class DiagnosticoDocumentoWidget(QWidget):
    """Contenido del diagnóstico: calcula al mostrarse y luego bajo demanda."""

    contenido_actualizado = Signal()

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self._main = main_window
        self._canvas = None
        self._conexion_pila = None
        self._pendiente = False

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(7, 7, 7, 7)
        raiz.setSpacing(7)

        formulario = QFormLayout()
        formulario.setContentsMargins(0, 0, 0, 0)
        formulario.setHorizontalSpacing(8)
        formulario.setVerticalSpacing(5)
        self._valores = {}
        for clave, etiqueta in (
                ("dimensiones", t("diagnostics.dimensions")),
                ("capas", t("diagnostics.layers")),
                ("memoria", t("diagnostics.memory")),
                ("proyecto", t("diagnostics.project")),
                ("efectos", t("diagnostics.effects"))):
            titulo = QLabel(etiqueta)
            titulo.setStyleSheet(theme.value_label_qss())
            valor = QLabel(t("diagnostics.not_available"))
            valor.setWordWrap(True)
            valor.setStyleSheet(f"color: {theme.TEXT};")
            formulario.addRow(titulo, valor)
            self._valores[clave] = valor
        raiz.addLayout(formulario)

        self._aviso = QLabel(t("diagnostics.no_document"))
        self._aviso.setWordWrap(True)
        self._aviso.setStyleSheet(theme.info_label_qss())
        raiz.addWidget(self._aviso)

        fila = QHBoxLayout()
        fila.addStretch(1)
        self._actualizar_btn = QPushButton(t("diagnostics.refresh"))
        self._actualizar_btn.setStyleSheet(theme.panel_action_button_qss())
        self._actualizar_btn.setMinimumHeight(24)
        self._actualizar_btn.clicked.connect(self.actualizar)
        fila.addWidget(self._actualizar_btn)
        raiz.addLayout(fila)
        raiz.addStretch(1)

    def _desconectar(self):
        if self._conexion_pila is not None:
            try:
                QObject.disconnect(self._conexion_pila)
            except RuntimeError:
                pass
        self._conexion_pila = None

    def _conectar(self):
        self._desconectar()
        pila = getattr(self._canvas, "undo_stack", None)
        if self.isVisible() and pila is not None:
            self._conexion_pila = pila.indexChanged.connect(
                self._marcar_desactualizado)

    def set_canvas(self, canvas):
        cambio = canvas is not self._canvas
        self._canvas = canvas
        self._conectar()
        if self.isVisible() and cambio:
            self.actualizar()

    def showEvent(self, event):
        super().showEvent(event)
        canvas = (self._main.get_current_canvas()
                  if hasattr(self._main, "get_current_canvas") else None)
        self._canvas = canvas
        self._conectar()
        self.actualizar()

    def hideEvent(self, event):
        self._desconectar()
        super().hideEvent(event)

    def _marcar_desactualizado(self, _indice=None):
        if self._pendiente:
            return
        self._pendiente = True
        self._actualizar_btn.setText(t("diagnostics.refresh_pending"))
        self._actualizar_btn.setToolTip(t("diagnostics.refresh_pending.tip"))

    def _texto_efectos(self, diagnostico):
        if not diagnostico.efectos_activos:
            return t("diagnostics.effects.none")
        base = t("diagnostics.effects.summary",
                 count=diagnostico.efectos_activos,
                 layers=diagnostico.capas_con_efectos)
        if not diagnostico.efectos_costosos:
            return base
        nombres = []
        for tipo, cantidad in diagnostico.efectos_costosos:
            clave = _CLAVES_EFECTOS.get(tipo)
            nombre = t(clave) if clave else tipo
            nombres.append(f"{nombre} ×{cantidad}")
        return base + " · " + ", ".join(nombres)

    def actualizar(self):
        self._pendiente = False
        self._actualizar_btn.setText(t("diagnostics.refresh"))
        self._actualizar_btn.setToolTip(t("diagnostics.refresh.tip"))
        canvas = self._canvas
        if canvas is None:
            for valor in self._valores.values():
                valor.setText(t("diagnostics.not_available"))
            self._aviso.setText(t("diagnostics.no_document"))
            self.contenido_actualizado.emit()
            return

        diagnostico = analizar_documento(canvas)
        megapixeles = diagnostico.ancho * diagnostico.alto / 1_000_000.0
        self._valores["dimensiones"].setText(
            t("diagnostics.dimensions.value", width=diagnostico.ancho,
              height=diagnostico.alto, mp=f"{megapixeles:.1f}"))
        self._valores["capas"].setText(t(
            "diagnostics.layers.value", total=diagnostico.capas,
            visible=diagnostico.capas_visibles, text=diagnostico.capas_texto,
            masks=diagnostico.mascaras, groups=diagnostico.grupos))
        self._valores["memoria"].setText(
            formatear_bytes(diagnostico.memoria_bytes))
        self._valores["memoria"].setToolTip(t("diagnostics.memory.tip"))
        if diagnostico.archivo_bytes is not None:
            clave = ("diagnostics.project.saved_pending"
                     if diagnostico.archivo_desactualizado
                     else "diagnostics.project.saved")
            proyecto = t(clave, size=formatear_bytes(diagnostico.archivo_bytes))
        else:
            proyecto = t("diagnostics.project.raw",
                         size=formatear_bytes(diagnostico.proyecto_bruto_bytes))
        self._valores["proyecto"].setText(proyecto)
        self._valores["proyecto"].setToolTip(t("diagnostics.project.tip"))
        self._valores["efectos"].setText(self._texto_efectos(diagnostico))

        factores = []
        if megapixeles >= 20.0:
            factores.append(t("diagnostics.factor.large"))
        if diagnostico.capas >= 50:
            factores.append(t("diagnostics.factor.layers"))
        if diagnostico.memoria_bytes >= 512 * 1024 * 1024:
            factores.append(t("diagnostics.factor.memory"))
        if diagnostico.efectos_costosos:
            factores.append(t("diagnostics.factor.effects"))
        self._aviso.setText(
            t("diagnostics.factors", factors=" · ".join(factores))
            if factores else t("diagnostics.factors.none"))
        self.contenido_actualizado.emit()


class DiagnosticoDocumentoDialog(FramelessDialog):
    """Ventana modeless independiente; no altera el tamaño de MainWindow."""

    def __init__(self, main_window):
        super().__init__(main_window)
        self.setWindowTitle(t("diagnostics.window_title"))
        self.setModal(False)
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self._body.setFixedWidth(460)

        self._diagnostico = DiagnosticoDocumentoWidget(main_window, self._body)
        self.body_layout.addWidget(self._diagnostico)
        self._diagnostico.contenido_actualizado.connect(
            self._ajustar_alto_al_contenido)
        self._ajustar_alto_al_contenido()

    def _ajustar_alto_al_contenido(self):
        """Elimina huecos y crece si las etiquetas necesitan más líneas."""
        for etiqueta in self._diagnostico.findChildren(QLabel):
            etiqueta.updateGeometry()
        contenido_layout = self._diagnostico.layout()
        contenido_layout.invalidate()
        contenido_layout.activate()

        margenes = self.body_layout.contentsMargins()
        ancho = self._body.width() - margenes.left() - margenes.right()
        alto_contenido = self._diagnostico.heightForWidth(ancho)
        if alto_contenido < 0:
            alto_contenido = self._diagnostico.sizeHint().height()
        alto = alto_contenido + margenes.top() + margenes.bottom()
        if alto > 0 and alto != self._body.height():
            self._body.setFixedHeight(alto)
            self.body_layout.invalidate()
            self.body_layout.activate()
            self._frame.layout().invalidate()
            self._frame.layout().activate()
            self.layout().invalidate()
            self.layout().activate()
            self.adjustSize()

    def set_canvas(self, canvas):
        self._diagnostico.set_canvas(canvas)

    def actualizar(self):
        self._diagnostico.actualizar()
