# tools/base_tool.py


def best_snap(deltas):
    """De varios desplazamientos de imán candidatos (uno por borde), devuelve el
    de MENOR magnitud que NO sea cero —el borde realmente imantado a una guía—,
    o 0 si ningún borde está dentro del radio. Descartar los ceros evita que un
    borde lejano (delta 0) 'gane' al borde que sí debe pegarse."""
    nz = [d for d in deltas if d]
    return min(nz, key=abs) if nz else 0.0


class BaseTool:
    def __init__(self, canvas):
        self.canvas = canvas

    def _alt_pick_color(self, event):
        """🎨 Alt+clic = cuentagotas temporal (clásico de Photoshop/Krita):
        captura el color bajo el cursor sin cambiar de herramienta (botón
        izquierdo → primario, derecho → secundario), con la misma lógica del
        cuentagotas pero sin lupa. Devuelve True si consumió el clic; las
        herramientas de pintura lo llaman al principio de su mouse_press."""
        from PySide6.QtCore import Qt
        if not (event.modifiers() & Qt.AltModifier):
            return False
        if event.button() not in (Qt.LeftButton, Qt.RightButton):
            return False
        from tools.eyedropper_tool import EyedropperTool
        EyedropperTool(self.canvas)._sample(
            event, primary=(event.button() == Qt.LeftButton), show_loupe=False)
        return True

    def mouse_press(self, event):
        pass

    def mouse_move(self, event):
        pass

    def mouse_release(self, event):
        pass