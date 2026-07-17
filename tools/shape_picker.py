# tools/shape_picker.py
"""Selector de formas estilo Paint.NET: un botón que muestra la forma actual y,
al pulsarlo, despliega un menú con secciones tituladas (Básico, Polígonos y
estrellas, Flechas, Rótulos, Símbolos) y una rejilla de iconos por sección.

Los iconos se generan al vuelo a partir de la misma geometría que dibuja la
herramienta (build_shape_path), así que nunca se desincronizan."""

from PySide6.QtWidgets import (QToolButton, QMenu, QWidgetAction, QWidget,
                               QGridLayout, QLabel)
from PySide6.QtGui import QIcon, QPixmap, QPainter, QPen, QColor, QBrush
from PySide6.QtCore import Qt, QSize, QRectF, Signal
from tools.shape_geometry import (get_shape_categories, get_shape_name, DEFAULT_SHAPE, build_shape_path)
import theme


def make_shape_icon(shape_id, size=22, color=None, fill=None):
    """Devuelve un QIcon con la forma dibujada (supersampling x2 para nitidez).
    Sin color explícito usa el texto del tema (theme.TEXT), calculado AL VUELO
    para respetar el tema activo (claro/oscuro); un default fijo se congelaría
    con el tema que hubiera al importar."""
    if color is None:
        color = QColor(theme.TEXT)
    if fill is None:
        fill = QColor(color)
        fill.setAlpha(45)
    ss = 2
    px = size * ss
    pm = QPixmap(px, px)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pad = max(2.0, px * 0.16)
    rect = QRectF(pad, pad, px - 2 * pad, px - 2 * pad)
    try:
        path = build_shape_path(shape_id, rect)
        p.setPen(QPen(color, 1.4 * ss))
        p.setBrush(QBrush(fill))
        p.drawPath(path)
    finally:
        p.end()
    return QIcon(pm)


def _button_style():
    return f"""
QToolButton {{
    background-color: {theme.BG_WINDOW}; color: {theme.TEXT};
    border: 1px solid {theme.BORDER_FAINT}; border-radius: 4px;
    font-family: 'Segoe UI'; font-size: 11px;
    padding: 2px 20px 2px 5px; text-align: left;
}}
QToolButton:hover {{ background-color: {theme.BG_HOVER}; border: 1px solid {theme.ACCENT}; }}
QToolButton::menu-indicator {{
    subcontrol-origin: padding; subcontrol-position: right center; right: 5px;
}}
"""


def _menu_style():
    return f"""
QMenu {{ background: {theme.BG_WINDOW}; border: 1px solid {theme.BORDER}; padding: 2px; }}
"""


def _grid_btn_style():
    return f"""
QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: 3px; padding: 0px; margin: 0px; }}
QToolButton:hover {{ background: {theme.ACCENT}; border: 1px solid {theme.ACCENT_BRIGHT}; }}
"""


class ShapePicker(QToolButton):
    """Botón-selector de forma. Emite shapeChanged(nombre) al elegir una."""

    shapeChanged = Signal(str)

    def __init__(self, parent=None, icon_size=20, columns=8):
        super().__init__(parent)
        self._icon_size = icon_size
        self._columns = columns
        self._current_id = DEFAULT_SHAPE
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setIconSize(QSize(icon_size, icon_size))
        self.setMinimumWidth(210)
        self.setStyleSheet(_button_style())

        self._menu = QMenu(self)
        self._menu.setStyleSheet(_menu_style())
        self._build_menu()
        self.setMenu(self._menu)
        self.set_current_id(DEFAULT_SHAPE)

    def _build_menu(self):
        gsize = self._icon_size + 6
        for cat_name, items in get_shape_categories():
            title = QLabel(cat_name)
            title.setStyleSheet(f"color:{theme.TITLE_GREY}; font: bold 11px {theme.FONT}; "
                                "padding:5px 8px 2px 8px;")
            wa_title = QWidgetAction(self._menu)
            wa_title.setDefaultWidget(title)
            wa_title.setEnabled(False)
            self._menu.addAction(wa_title)

            grid_w = QWidget()
            grid = QGridLayout(grid_w)
            grid.setContentsMargins(6, 0, 6, 4)
            grid.setSpacing(2)
            for i, (sid, name) in enumerate(items):
                b = QToolButton()
                b.setIcon(make_shape_icon(sid, gsize))
                b.setIconSize(QSize(gsize, gsize))
                b.setFixedSize(gsize + 8, gsize + 8)  # cuadrado, ceñido al icono
                b.setToolTip(name)
                b.setAutoRaise(True)
                b.setStyleSheet(_grid_btn_style())
                b.clicked.connect(lambda _=False, s=sid: self._on_pick(s))
                grid.addWidget(b, i // self._columns, i % self._columns)
            grid.setColumnStretch(self._columns, 1)  # empuja los iconos a la izquierda
            wa_grid = QWidgetAction(self._menu)
            wa_grid.setDefaultWidget(grid_w)
            self._menu.addAction(wa_grid)

    def _on_pick(self, shape_id):
        self.set_current_id(shape_id)
        self._menu.hide()
        self.shapeChanged.emit(get_shape_name(shape_id))

    # --- API usada por options_bar (compatibilidad con el combo anterior) ---
    def set_current_id(self, shape_id):
        self._current_id = shape_id
        self.setIcon(make_shape_icon(shape_id, self._icon_size))
        self.setText("  " + get_shape_name(shape_id))

    def current_id(self):
        return self._current_id

    def currentText(self):
        return get_shape_name(self._current_id)

    def setCurrentText(self, name):
        from tools.shape_geometry import get_shape_id_by_name
        self.set_current_id(get_shape_id_by_name(name))