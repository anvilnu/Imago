from i18n import t
# tools/move_copy_tool.py
from tools.move_tool import MoveTool


class MoveCopyTool(MoveTool):
    """Como 'Mover selección', pero COPIA en vez de cortar.

    Seleccionas una zona y, al arrastrar, se mueve una COPIA de su contenido:
    el original se queda en su sitio (sin hueco) y, al soltar, la copia se
    fusiona en el destino (tapando lo que haya debajo, en la misma capa).

    Reutiliza toda la maquinaria de MoveTool (arrastrar, escalar, rotar); lo
    único que cambia es que al levantar la selección NO se vacía el origen.
    """

    def __init__(self, canvas):
        # IMPORTANTE: activar el modo copia ANTES del super().__init__(), porque
        # MoveTool ya intenta "levantar" la selección dentro de su propio init.
        self.copy_mode = True
        super().__init__(canvas)
        self.tool_id = "move_copy"
        self.history_name = t("tool.name.move_copy_hist", default="Mover copia")