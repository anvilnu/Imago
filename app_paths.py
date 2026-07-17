# app_paths.py
"""Rutas de datos de Imago, con soporte de MODO PORTABLE.

Modo portable (solo en el .exe congelado): si junto al ejecutable existe el
archivo marcador "portable.txt", TODOS los datos del usuario (ajustes, modelos de
IA descargados y copias de autoguardado) se guardan en una carpeta "datos" JUNTO
al .exe, en formato INI, SIN tocar el registro de Windows ni AppData. Asi la app
no deja rastro en el sistema y es trasladable (USB, o varias copias aisladas).

En desarrollo ("python main.py") o en la versión INSTALADA (sin marcador) se usan
las rutas ESTÁNDAR del sistema: AVNSoft/Imago tanto para el registro de ajustes
como para QStandardPaths. Las preferencias de la identidad anterior
MiEstudio/Imago se migran una sola vez y se conservan como respaldo.
"""
import os
import sys

_MARCADOR = "portable.txt"
ORGANIZACION = "AVNSoft"
APLICACION = "Imago"
_ORGANIZACION_ANTERIOR = "MiEstudio"
_CLAVE_MIGRACION = "_internal/migrated_miestudio_v1"


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


def _settings_nativos(organizacion):
    """Construye el almacén nativo indicado; separado para poder probar la
    migración sin leer ni escribir las preferencias reales del sistema."""
    from PySide6.QtCore import QSettings
    return QSettings(organizacion, APLICACION)


def _migrar_ajustes(destino, anterior):
    """Copia una sola vez MiEstudio/Imago hacia la identidad definitiva.

    El almacén anterior era la fuente usada por Preferencias, por lo que sus
    valores prevalecen si también existe una clave antigua bajo AVNSoft. No se
    borra: queda como respaldo y versiones anteriores de Imago pueden seguir
    leyéndolo. Devuelve True si realizó la migración.
    """
    from PySide6.QtCore import QSettings
    if destino.value(_CLAVE_MIGRACION, False, type=bool):
        return False
    anterior.sync()
    if anterior.status() != QSettings.Status.NoError:
        return False
    for clave in anterior.allKeys():
        destino.setValue(clave, anterior.value(clave))
    destino.sync()
    if destino.status() != QSettings.Status.NoError:
        return False
    destino.setValue(_CLAVE_MIGRACION, True)
    destino.sync()
    return destino.status() == QSettings.Status.NoError


def settings():
    """QSettings de Imago (crea una instancia nueva en cada llamada, como el resto
    del codigo). En modo portable escribe en <exe>\\datos\\Imago.ini (formato INI,
    sin tocar el registro); si no, usa la identidad única "AVNSoft"/"Imago" y
    migra una vez los valores del antiguo "MiEstudio"/"Imago".

    OJO: el constructor de 2 argumentos QSettings(organización, aplicación) IGNORA
    setDefaultFormat y siempre usa el formato nativo (registro en Windows); por eso
    el modo portable usa el constructor explicito QSettings(fichero, IniFormat).
    """
    from PySide6.QtCore import QSettings
    if es_portable():
        return QSettings(os.path.join(base_datos(), APLICACION + ".ini"),
                         QSettings.Format.IniFormat)
    actual = _settings_nativos(ORGANIZACION)
    anterior = _settings_nativos(_ORGANIZACION_ANTERIOR)
    _migrar_ajustes(actual, anterior)
    return actual


def idioma(almacen=None):
    """Idioma configurado para textos propios y traducciones nativas de Qt."""
    if almacen is None:
        almacen = settings()
    valor = str(almacen.value("language", "es"))
    return valor if valor in ("es", "en", "fr") else "es"
