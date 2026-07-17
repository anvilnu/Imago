"""Estado compartido de persistencia de un documento de Imago."""


def documento_pendiente(canvas):
    """True si cerrar el lienzo requeriría guardar o descartar cambios.

    Una recuperación recién abierta conserva una pila de deshacer limpia, pero
    sigue sin estar guardada de verdad. Por eso ``recovered_dirty`` forma parte
    del estado pendiente igual que ``QUndoStack.isClean()``.
    """
    if canvas is None:
        return False
    return (not canvas.undo_stack.isClean()) or bool(
        getattr(canvas, "recovered_dirty", False))
