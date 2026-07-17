# menu_ajustes.py
"""Acciones de los menús Ajustes y Efectos (mixin de MainWindow).

Extraído de main.py TAL CUAL (sin cambios de comportamiento): cada entrada de
menú conecta con su adjust_*/effect_*, que abre el diálogo correspondiente de
adjustments.py vía _open_adjustment (panel OVERLAY no modal, con política de
INSTANCIA ÚNICA en _open_ai_overlay, compartida con los efectos de IA). """
from i18n import t


class AccionesMenuAjustes:
    def _open_adjustment(self, dialog_cls):
        canvas = self.get_current_canvas()
        if canvas and canvas.get_active_layer() is not None:
            layer = canvas.layers[canvas.active_layer_index]
            # 🔒 Píxeles bloqueados (Propiedades de capa): los Ajustes/Efectos
            # reescriben los píxeles de la capa activa, así que se cortan aquí.
            if getattr(layer, "pixels_locked", False):
                self.status_bar.showMessage(t("status.layer_pixels_locked"), 4000)
                return
            if getattr(layer, "is_text", False):
                from widgets.custom_titlebar import imago_question
                from PySide6.QtWidgets import QMessageBox
                if imago_question(self, t("msg.rasterize.title"), t("msg.rasterize.body")) != QMessageBox.Yes:
                    return
                from models.layer_commands import RasterizeLayerCommand
                canvas.undo_stack.push(RasterizeLayerCommand(canvas, canvas.active_layer_index))
            # Ajustes/Efectos como PANEL OVERLAY (no modal): instancia única. Si ya
            # hay un ajuste abierto, se cancela antes de abrir el nuevo.
            self._open_ai_overlay(dialog_cls(self))

    def open_layer_effects(self, tipo=None):
        """Abre el PANEL UNIFICADO de efectos de capa (no destructivo) sobre la
        capa activa. A diferencia de _open_adjustment, NO rasteriza el texto (los
        efectos se pegan a la capa y el texto sigue editable). `tipo` es el efecto
        que queda seleccionado y activado al abrir (el elegido desde el botón fx
        o el pulsado en la sublista). Instancia única vía _open_ai_overlay."""
        canvas = self.get_current_canvas()
        if canvas and canvas.get_active_layer() is not None:
            from widgets.layer_effects_ui import EfectosDialog
            self._open_ai_overlay(EfectosDialog(self, tipo=tipo))

    def _open_ai_overlay(self, panel):
        """Muestra un panel overlay (AdjustmentDialog/OverlayPanel) con la política
        de INSTANCIA ÚNICA: si ya había uno abierto, se cancela antes. Común a los
        Ajustes/Efectos y a los efectos de IA con parámetros y preview."""
        # El editor de color en vivo (no modal) no debe convivir con un overlay:
        # se cierra al abrir uno (efecto, ajuste o IA).
        cp = getattr(self, "colors_panel", None)
        if cp is not None:
            cp.close_live_editor()
        prev = getattr(self, "_active_adjustment_overlay", None)
        if prev is not None:
            prev.reject()
        self._active_adjustment_overlay = panel
        # La preview posee una o todas las capas: bloquear el panel y todas las
        # acciones de Capas evita borrar/reordenar/transformar su destino.
        if getattr(self, "layers_panel", None) is not None:
            self.layers_panel.setEnabled(False)
        for action in getattr(self, "_layer_menu_actions", {}).values():
            action.setEnabled(False)
        for name in (
                "undo_action", "redo_action", "cut_action", "paste_action",
                "paste_layer_action", "delete_sel_action", "fill_sel_action",
                "crop_action", "resize_action", "canvas_size_action",
                "flip_h_action", "flip_v_action", "rotate_cw_action",
                "rotate_ccw_action", "rotate_180_action", "rotate_free_action"):
            action = getattr(self, name, None)
            if action is not None:
                action.setEnabled(False)
        panel.closed.connect(lambda p=panel: self._clear_adjustment_overlay(p))
        panel.open_over(self)

    def _clear_adjustment_overlay(self, panel):
        """Libera la referencia al overlay de ajuste cuando este se cierra."""
        if getattr(self, "_active_adjustment_overlay", None) is panel:
            self._active_adjustment_overlay = None
            if getattr(self, "layers_panel", None) is not None:
                self.layers_panel.setEnabled(self.get_current_canvas() is not None)
            if hasattr(self, "update_layer_menu_state"):
                self.update_layer_menu_state()
            if hasattr(self, "update_edit_actions_state"):
                self.update_edit_actions_state()

    def _cancel_overlay_for_canvas(self, canvas):
        """Cancela la preview que pertenece al lienzo indicado, si existe."""
        panel = getattr(self, "_active_adjustment_overlay", None)
        if panel is not None and getattr(panel, "canvas", None) is canvas:
            panel.reject()

    def adjust_brightness_contrast(self):
        from adjustments import BrightnessContrastDialog
        self._open_adjustment(BrightnessContrastDialog)

    def adjust_shadows_highlights(self):
        from adjustments import ShadowsHighlightsDialog
        self._open_adjustment(ShadowsHighlightsDialog)

    def adjust_curves(self):
        from adjustments import CurvesDialog
        self._open_adjustment(CurvesDialog)

    def adjust_vibrance(self):
        from adjustments import VibranceDialog
        self._open_adjustment(VibranceDialog)

    def adjust_clarity(self):
        from adjustments import ClarityDialog
        self._open_adjustment(ClarityDialog)

    def adjust_dehaze(self):
        from adjustments import DehazeDialog
        self._open_adjustment(DehazeDialog)

    def adjust_photo_filter(self):
        from adjustments import PhotoFilterDialog
        self._open_adjustment(PhotoFilterDialog)

    def effect_bloom(self):
        from adjustments import BloomDialog
        self._open_adjustment(BloomDialog)

    def effect_tilt_shift(self):
        from adjustments import TiltShiftDialog
        self._open_adjustment(TiltShiftDialog)

    def adjust_white_balance(self):
        from adjustments import WhiteBalanceDialog
        self._open_adjustment(WhiteBalanceDialog)

    def effect_dithering(self):
        from adjustments import DitherDialog
        self._open_adjustment(DitherDialog)

    def effect_color_halftone(self):
        from adjustments import ColorHalftoneDialog
        self._open_adjustment(ColorHalftoneDialog)

    def effect_spin_blur(self):
        from adjustments import SpinBlurDialog
        self._open_adjustment(SpinBlurDialog)

    def effect_kaleidoscope(self):
        from adjustments import KaleidoscopeDialog
        self._open_adjustment(KaleidoscopeDialog)

    def effect_polar_coords(self):
        from adjustments import PolarCoordinatesDialog
        self._open_adjustment(PolarCoordinatesDialog)

    def effect_frosted_glass(self):
        from adjustments import FrostedGlassDialog
        self._open_adjustment(FrostedGlassDialog)

    def effect_crystallize(self):
        from adjustments import CrystallizeDialog
        self._open_adjustment(CrystallizeDialog)

    def effect_wave(self):
        from adjustments import WaveDialog
        self._open_adjustment(WaveDialog)

    def effect_spherize(self):
        from adjustments import SpherizeDialog
        self._open_adjustment(SpherizeDialog)

    def effect_twirl(self):
        from adjustments import TwirlDialog
        self._open_adjustment(TwirlDialog)

    def effect_surface_blur(self):
        from adjustments import SurfaceBlurDialog
        self._open_adjustment(SurfaceBlurDialog)

    def adjust_hue_saturation(self):
        from adjustments import HueSaturationDialog
        self._open_adjustment(HueSaturationDialog)

    def adjust_replace_color(self):
        from adjustments import ReplaceColorGlobalDialog
        self._open_adjustment(ReplaceColorGlobalDialog)

    def adjust_channel_mixer(self):
        from adjustments import ChannelMixerDialog
        self._open_adjustment(ChannelMixerDialog)

    def adjust_bw_advanced(self):
        from adjustments import BlackWhiteAdvancedDialog
        self._open_adjustment(BlackWhiteAdvancedDialog)

    def adjust_gamma(self):
        from adjustments import GammaDialog
        self._open_adjustment(GammaDialog)

    def adjust_posterize(self):
        from adjustments import PosterizeDialog
        self._open_adjustment(PosterizeDialog)

    def adjust_invert(self):
        from adjustments import apply_instant, invert
        apply_instant(self, invert, t("menu.adj.invert"))

    def adjust_grayscale(self):
        from adjustments import apply_instant, grayscale
        apply_instant(self, grayscale, t("menu.adj.grayscale"))

    def adjust_levels(self):
        from adjustments import LevelsDialog
        self._open_adjustment(LevelsDialog)

    def adjust_exposure(self):
        from adjustments import ExposureDialog
        self._open_adjustment(ExposureDialog)

    def adjust_color_balance(self):
        from adjustments import ColorBalanceDialog
        self._open_adjustment(ColorBalanceDialog)

    def adjust_temperature(self):
        from adjustments import TemperatureDialog
        self._open_adjustment(TemperatureDialog)

    def adjust_threshold(self):
        from adjustments import ThresholdDialog
        self._open_adjustment(ThresholdDialog)

    def adjust_solarize(self):
        from adjustments import SolarizeDialog
        self._open_adjustment(SolarizeDialog)

    def adjust_gradient_map(self):
        from adjustments import GradientMapDialog
        self._open_adjustment(GradientMapDialog)

    def adjust_sepia(self):
        from adjustments import apply_instant, sepia
        apply_instant(self, sepia, t("menu.adj.sepia"))

    def adjust_duotone(self):
        from adjustments import DuotoneDialog
        self._open_adjustment(DuotoneDialog)

    def adjust_auto_contrast(self):
        from adjustments import apply_instant, auto_contrast
        apply_instant(self, auto_contrast, t("menu.adj.auto_contrast"))

    def adjust_auto_levels(self):
        from adjustments import apply_instant, auto_levels
        apply_instant(self, auto_levels, t("menu.adj.auto_levels"))

    def adjust_auto_color(self):
        from adjustments import apply_instant, auto_color
        apply_instant(self, auto_color, t("menu.adj.auto_color"))

    def adjust_equalize(self):
        from adjustments import apply_instant, equalize
        apply_instant(self, equalize, t("menu.adj.equalize"))

    # ----- Efectos (scipy) -----
    def effect_gaussian_blur(self):
        from adjustments import GaussianBlurDialog
        self._open_adjustment(GaussianBlurDialog)

    def effect_sharpen(self):
        from adjustments import SharpenDialog
        self._open_adjustment(SharpenDialog)

    def effect_edge_enhance(self):
        from adjustments import EdgeEnhanceDialog
        self._open_adjustment(EdgeEnhanceDialog)

    def effect_find_edges(self):
        from adjustments import FindEdgesDialog
        self._open_adjustment(FindEdgesDialog)

    def effect_emboss(self):
        from adjustments import EmbossDialog
        self._open_adjustment(EmbossDialog)

    def effect_median(self):
        from adjustments import MedianDialog
        self._open_adjustment(MedianDialog)

    def effect_box_blur(self):
        from adjustments import BoxBlurDialog
        self._open_adjustment(BoxBlurDialog)

    def effect_motion_blur(self):
        from adjustments import MotionBlurDialog
        self._open_adjustment(MotionBlurDialog)

    def effect_sharpen_threshold(self):
        from adjustments import SharpenThresholdDialog
        self._open_adjustment(SharpenThresholdDialog)

    def effect_pixelate(self):
        from adjustments import PixelateDialog
        self._open_adjustment(PixelateDialog)

    def effect_vignette(self):
        from adjustments import VignetteDialog
        self._open_adjustment(VignetteDialog)

    # (Los antiguos "Estilos de capa" destructivos —sombra paralela/interior,
    # resplandores, bisel, superposición y trazo— se retiraron del menú Efectos:
    # existen como EFECTOS DE CAPA no destructivos en Capas ▸ Efectos.)

    def effect_chromatic(self):
        from adjustments import ChromaticDialog
        self._open_adjustment(ChromaticDialog)

    def effect_maximum(self):
        from adjustments import MaximumDialog
        self._open_adjustment(MaximumDialog)

    def effect_minimum(self):
        from adjustments import MinimumDialog
        self._open_adjustment(MinimumDialog)

    def effect_contour(self):
        from adjustments import ContourDialog
        self._open_adjustment(ContourDialog)

    def effect_add_noise(self):
        from adjustments import AddNoiseDialog
        self._open_adjustment(AddNoiseDialog)

    def effect_zoom_blur(self):
        from adjustments import ZoomBlurDialog
        self._open_adjustment(ZoomBlurDialog)

    def effect_lens_blur(self):
        from adjustments import LensBlurDialog
        self._open_adjustment(LensBlurDialog)

    def effect_render_clouds(self):
        from adjustments import RenderCloudsDialog
        self._open_adjustment(RenderCloudsDialog)

    def effect_displace(self):
        from adjustments import DisplaceDialog
        self._open_adjustment(DisplaceDialog)

    def effect_glitch(self):
        from adjustments import GlitchDialog
        self._open_adjustment(GlitchDialog)

    def effect_halftone(self):
        from adjustments import HalftoneDialog
        self._open_adjustment(HalftoneDialog)

    def effect_pencil_sketch(self):
        from adjustments import PencilSketchDialog
        self._open_adjustment(PencilSketchDialog)

    def effect_ink_sketch(self):
        from adjustments import InkSketchDialog
        self._open_adjustment(InkSketchDialog)

    def effect_oil_painting(self):
        from adjustments import OilPaintingDialog
        self._open_adjustment(OilPaintingDialog)

    def effect_cartoon(self):
        from adjustments import CartoonDialog
        self._open_adjustment(CartoonDialog)

