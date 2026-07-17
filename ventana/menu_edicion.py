# menu_edicion.py
"""Acciones del menú Edición y de selección (mixin de MainWindow).

Extraído de main.py TAL CUAL (sin cambios de comportamiento): cortar/copiar/
pegar (como capa, como imagen y la forma de la selección), seleccionar todo/
deseleccionar/invertir, borrar/rellenar la selección y el refinado
(expandir/contraer/suavizar/difuminar/borde/crecer/parecido, vía
_refine_selection). MainWindow hereda de AccionesMenuEdicion, así que los
menús siguen conectando con self.* igual que antes."""
from PySide6.QtCore import QTimer
from PySide6.QtGui import QPainterPath

from i18n import t
from models.destino_edicion import canvas_activo
from widgets.custom_titlebar import ImagoMessageBox


class AccionesMenuEdicion:
    def edit_cut(self):
        canvas = self.get_current_canvas()
        if canvas and not canvas.cut_selection():
            self.status_bar.showMessage(t("status.no_cut"), 4000)

    def edit_copy(self):
        canvas = self.get_current_canvas()
        if canvas:
            if canvas.copy_selection():
                self.status_bar.showMessage(t("status.copied"), 4000)
            else:
                self.status_bar.showMessage(t("status.no_copy"), 4000)

    def edit_paste(self):
        """Ctrl+V: pega en la CAPA ACTIVA como contenido flotante. Si lo
        pegado es más grande que el lienzo, pregunta qué hacer (Paint.NET)."""
        from PySide6.QtWidgets import QApplication
        canvas = self.get_current_canvas()
        if not canvas:
            return
        img = QApplication.clipboard().image()
        if img.isNull():
            self.status_bar.showMessage(t("status.no_clip"), 4000)
            return

        # ¿Lo pegado desborda el lienzo? Preguntar antes de actuar
        if img.width() > canvas.base_width or img.height() > canvas.base_height:
            box = ImagoMessageBox(self, t("dlg.paste.title"),
                t("dlg.paste.text"), icon_kind="question")
            box.add_button(t("dlg.paste.expand"), "expand")
            box.add_button(t("dlg.paste.keep"), "keep")
            box.add_button(t("common.cancel"), "cancel")
            box.exec()

            clicked = box.value()
            if clicked == "expand":
                # Comando deshacible: el lienzo crece y el contenido se centra
                canvas.expand_canvas_for(img.width(), img.height())
                self.fit_canvas_to_screen()
            elif clicked != "keep":
                return  # Cancelar: no pegamos nada

        self.set_tool("move")
        canvas.current_tool.begin_paste(img)
        self.activateWindow()
        canvas.setFocus()

    def edit_paste_as_layer(self):
        canvas = self.get_current_canvas()
        if canvas and not canvas.paste_as_new_layer():
            self.status_bar.showMessage(t("status.no_clip"), 4000)

    def edit_select_all(self):
        canvas = self.get_current_canvas()
        if canvas: canvas.select_all()

    def edit_deselect(self):
        canvas = self.get_current_canvas()
        if not canvas:
            return
        if getattr(canvas, 'selection', None) is not None:
            canvas.clear_selection()
            return
        # Sin selección real: si la herramienta de mover muestra la caja de
        # una capa de TEXTO, Deseleccionar la anula (las hormigas desaparecen;
        # un clic sobre el texto la re-arma).
        tool = getattr(canvas, 'current_tool', None)
        if tool is not None and hasattr(tool, 'dismiss_text_box'):
            tool.dismiss_text_box()

    def edit_paste_as_image(self):
        """Pegar en una imagen nueva: crea una pestaña con la imagen del
        portapapeles a su tamaño original."""
        from PySide6.QtWidgets import QApplication
        img = QApplication.clipboard().image()
        if img.isNull():
            self.status_bar.showMessage(t("status.no_clip"), 4000)
            return
        self.create_new_tab_canvas(img.width(), img.height(),
                                   f"{t('dlg.untitled')} {self.tabs.count()}", image_to_load=img)
        QTimer.singleShot(20, self.fit_canvas_to_screen)

    def edit_copy_selection_shape(self):
        canvas = self.get_current_canvas()
        if canvas and canvas.copy_selection_shape():
            self.status_bar.showMessage(t("status.shape_copied"), 4000)
        else:
            self.status_bar.showMessage(t("status.no_copy"), 4000)

    def edit_paste_selection_shape(self, mode):
        canvas = self.get_current_canvas()
        if canvas and not canvas.paste_selection_shape(mode):
            self.status_bar.showMessage(t("status.no_shape_copy"), 4000)

    def edit_delete_selection(self):
        canvas = self.get_current_canvas()
        if canvas is None:
            return
        # 🔒 Píxeles bloqueados: borrar la selección edita la capa activa.
        if getattr(canvas.get_active_layer_obj(), "pixels_locked", False):
            self.status_bar.showMessage(t("status.layer_pixels_locked"), 4000)
            return
        if not canvas.delete_selection():
            self.status_bar.showMessage(t("status.no_del"), 4000)

    def edit_fill_selection(self):
        canvas = self.get_current_canvas()
        if canvas is None:
            return
        # 🔒 Píxeles bloqueados: rellenar la selección edita la capa activa.
        if getattr(canvas.get_active_layer_obj(), "pixels_locked", False):
            self.status_bar.showMessage(t("status.layer_pixels_locked"), 4000)
            return
        if not canvas.fill_selection():
            self.status_bar.showMessage(t("status.no_fill"), 4000)

    def edit_invert_selection(self):
        canvas = self.get_current_canvas()
        if canvas: canvas.invert_selection()

    def _refine_selection(self, method_name, title, label, minimum=1, show_direction=False):
        """Abre el PANEL OVERLAY de radio y aplica una operación de refinado de la
        selección (expand_selection / contract_selection / smooth_selection /
        feather_selection / border_selection). El panel es un hijo del lienzo (no
        una ventana del SO): no se sale del lienzo y recuerda su posición. No es
        modal: la operación se aplica al Aceptar, vía callback."""
        canvas = self.get_current_canvas()
        if not canvas or getattr(canvas, 'selection', None) is None:
            return
        seleccion_inicial = QPainterPath(canvas.selection)

        if not hasattr(self, '_refine_cache'):
            self._refine_cache = {
                'expand_selection': {'radius': 4, 'direction': "Completo"},
                'contract_selection': {'radius': 4, 'direction': "Completo"},
                'smooth_selection': {'radius': 4},
                'feather_selection': {'radius': 4},
                'border_selection': {'radius': 4}
            }

        cache = self._refine_cache.get(method_name)
        default_r = cache['radius']

        def _apply(val, direction):
            # El panel no es modal: solo puede modificar el documento y la
            # selección concretos con los que se abrió. Si cualquiera cambió,
            # se descarta para no aplicar el resultado sobre otro destino.
            if (not canvas_activo(self, canvas)
                    or getattr(canvas, 'selection', None) is None
                    or canvas.selection != seleccion_inicial):
                self.status_bar.showMessage(t("edit.target_changed"), 5000)
                return
            cache['radius'] = val
            if show_direction:
                cache['direction'] = direction
                getattr(canvas, method_name)(val, direction)
            else:
                getattr(canvas, method_name)(val)

        from new_dialog import SelectionRefineDialog
        panel = SelectionRefineDialog(self, title=title, label=label, default=default_r,
                                      minimum=minimum, show_direction=show_direction,
                                      on_apply=_apply)
        panel.canvas = canvas

        if show_direction:
            _di = panel.direction_combo.findData(cache.get('direction', "Completo"))
            panel.direction_combo.setCurrentIndex(_di if _di >= 0 else 0)

        # Instancia única + open_over + limpieza de referencia al cerrar (mismo
        # gestor que usan los Ajustes/Efectos overlay).
        self._open_ai_overlay(panel)

    def edit_expand_selection(self):
        self._refine_selection('expand_selection', t("hist.exp_sel"), t("dlg.lbl.expand"), show_direction=True)

    def edit_contract_selection(self):
        self._refine_selection('contract_selection', t("hist.cont_sel"), t("dlg.lbl.contract"), show_direction=True)

    def edit_smooth_selection(self):
        self._refine_selection('smooth_selection', t("hist.smooth_sel"), t("dlg.lbl.radius"))

    def edit_feather_selection(self):
        self._refine_selection('feather_selection', t("hist.feather"), t("dlg.lbl.radius"), minimum=-200)

    def edit_border_selection(self):
        self._refine_selection('border_selection', t("hist.border_sel"), t("dlg.lbl.border"))

    def edit_grow_selection(self):
        """Crecer: extiende la selección a los píxeles contiguos parecidos
        (tolerancia de la varita). Sin cambios, avisa en la barra de estado."""
        canvas = self.get_current_canvas()
        if canvas and not canvas.grow_selection():
            self.status_bar.showMessage(t("status.no_grow"), 4000)

    def edit_similar_selection(self):
        """Seleccionar parecido: extiende a todos los píxeles parecidos de la
        imagen (tolerancia de la varita)."""
        canvas = self.get_current_canvas()
        if canvas and not canvas.select_similar():
            self.status_bar.showMessage(t("status.no_grow"), 4000)

