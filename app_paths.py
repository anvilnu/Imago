# app_paths.py
"""Rutas de datos de Imago, con soporte de MODO PORTABLE.

Modo portable (solo en el .exe congelado): si junto al ejecutable existe el
archivo marcador "portable.txt", TODOS los datos del usuario (ajustes, modelos de
IA descargados y copias de autoguardado) se guardan en una carpeta "datos" JUNTO
al .exe, en formato INI, SIN tocar el registro de Windows ni AppData. Asi la app
no deja rastro en el sistema y es trasladable (USB, o varias copias aisladas).

En desarrollo ("python main.py") o en la version INSTALADA (sin marcador) se usan
las rutas ESTANDAR del sistema de siempre: el registro para los ajustes y AppData
para los modelos y el autoguardado. La version instalada NO se ve afectada: sin
marcador, es_portable() es False y todo se comporta exactamente igual que antes.
"""
import os
import sys

_MARCADOR = "portable.txt"


def _dir_exe():
    """Carpeta que contiene el ejecutable (o este script, en desarrollo)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def es_portable():
    """True si es el .exe congelado Y hay un marcador 'portable.txt' junto a el."""
    return getattr(sys, "frozen", False) and os.path.exists(
        os.path.join(_dir_exe(), _MARCADOR))


def base_datos():
    """Carpeta base de los datos del usuario.

    - Portable: <carpeta del .exe>\\datos  (se crea si no existe).
    - Normal:   la carpeta de datos del usuario del sistema (AppData); puede ser
                "" en sistemas raros, y en ese caso el llamador aplica su respaldo.
    """
    if es_portable():
        d = os.path.join(_dir_exe(), "datos")
        try:
            os.makedirs(d, exist_ok=True)
        except OSError:
            pass
        return d
    from PySide6.QtCore import QStandardPaths
    return QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)


def settings():
    """QSettings de Imago (crea una instancia nueva en cada llamada, como el resto
    del codigo). En modo portable escribe en <exe>\\datos\\Imago.ini (formato INI,
    sin tocar el registro); si no, en el registro nativo ("MiEstudio"/"Imago").

    OJO: el constructor de 2 argumentos QSettings("MiEstudio", "Imago") IGNORA
    setDefaultFormat y siempre usa el formato nativo (registro en Windows); por eso
    el modo portable usa el constructor explicito QSettings(fichero, IniFormat).
    """
    from PySide6.QtCore import QSettings
    if es_portable():
        return QSettings(os.path.join(base_datos(), "Imago.ini"),
                         QSettings.Format.IniFormat)
    return QSettings("MiEstudio", "Imago")
