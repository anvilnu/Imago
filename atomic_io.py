"""Escritura atómica de archivos de usuario.

El contenido se genera en un temporal de la MISMA carpeta y con la MISMA
extensión que el destino. Solo después de cerrar y sincronizar el temporal se
sustituye el archivo definitivo con ``os.replace()``. Así un fallo conserva la
versión anterior y no deja un documento nuevo a medias.
"""

import os
import secrets
import stat


def _crear_temporal(carpeta, raiz, extension, modo_existente=None):
    """Crea un temporal exclusivo con permisos naturales de cada plataforma.

    ``os.open(..., 0o666)`` deja que POSIX aplique el umask del usuario, a
    diferencia de ``mkstemp()`` (0600 fijo). Si se sustituye un archivo POSIX,
    fchmod restaura exactamente sus permisos aunque el umask sea más restrictivo.
    O_EXCL mantiene la creación libre de carreras igual que tempfile.mkstemp().
    """
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    prefijo = ".%s-" % (raiz or "imago")
    for _ in range(100):
        nombre = "%s%s%s" % (prefijo, secrets.token_hex(8), extension)
        ruta = os.path.join(carpeta, nombre)
        try:
            fd = os.open(ruta, flags, 0o666)
        except FileExistsError:
            continue
        try:
            if modo_existente is not None and hasattr(os, "fchmod"):
                os.fchmod(fd, modo_existente)
        except OSError:
            os.close(fd)
            try:
                os.remove(ruta)
            except OSError:
                pass
            raise
        return fd, ruta
    raise FileExistsError("No se pudo reservar un nombre temporal único")


def _sincronizar_directorio(carpeta):
    """Fuerza en POSIX la entrada de directorio creada por os.replace().

    Es una garantía adicional ante corte de alimentación. Algunos sistemas de
    archivos no permiten fsync sobre directorios; en ese caso el reemplazo ya
    realizado sigue siendo válido y no se convierte falsamente en un error.
    """
    if os.name != "posix":
        return
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        fd = os.open(carpeta, flags)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


class ReemplazoAtomico:
    """Temporal asociado a un destino que solo se publica con ``confirmar()``."""

    def __init__(self, destino):
        self.ruta = None
        self._confirmado = False
        solicitado = os.path.abspath(os.fspath(destino))
        # Guardar a través de un enlace debe actualizar su objetivo, no sustituir
        # el propio enlace por un archivo regular (comportamiento importante en
        # escritorios y flujos Linux).
        self.destino = (os.path.realpath(solicitado)
                        if os.path.islink(solicitado) else solicitado)
        carpeta = os.path.dirname(self.destino)
        nombre = os.path.basename(self.destino)
        raiz, extension = os.path.splitext(nombre)
        modo_existente = None
        if os.name == "posix":
            try:
                estado = os.stat(self.destino)
                if stat.S_ISREG(estado.st_mode):
                    modo_existente = stat.S_IMODE(estado.st_mode)
            except FileNotFoundError:
                pass
        fd, self.ruta = _crear_temporal(
            carpeta, raiz, extension, modo_existente=modo_existente)
        os.close(fd)

    def __enter__(self):
        return self

    def confirmar(self):
        """Sincroniza y sustituye el destino. Devuelve False si no fue posible."""
        if self._confirmado or not self.ruta:
            return self._confirmado
        try:
            # El escritor ya debe haber cerrado el archivo. fsync reduce la
            # ventana en la que un corte de alimentación deja datos sin volcar.
            # En Windows fsync exige un descriptor abierto con permiso de
            # escritura; sobre uno "rb" devuelve EBADF aunque el archivo sea
            # perfectamente válido. "rb+" no modifica el contenido.
            with open(self.ruta, "rb+") as temporal:
                os.fsync(temporal.fileno())
            os.replace(self.ruta, self.destino)
        except OSError:
            return False
        self._confirmado = True
        self.ruta = None
        _sincronizar_directorio(os.path.dirname(self.destino))
        return True

    def cancelar(self):
        """Elimina el temporal si todavía no se publicó; nunca toca el destino."""
        if not self.ruta:
            return
        try:
            os.remove(self.ruta)
        except OSError:
            pass
        self.ruta = None

    def __exit__(self, exc_type, exc_value, traceback):
        self.cancelar()
        return False

    def __del__(self):
        # Red de seguridad para usos no contextuales (p. ej. QPrinter).
        self.cancelar()


def escribir_atomico(destino, escritor):
    """Ejecuta ``escritor(ruta_temporal)`` y publica el archivo si devuelve True.

    Los OSError esperables de E/S se traducen a False. Cualquier otra excepción
    se propaga después de limpiar el temporal, para no ocultar errores de código.
    """
    try:
        with ReemplazoAtomico(destino) as reemplazo:
            if not escritor(reemplazo.ruta):
                return False
            return reemplazo.confirmar()
    except OSError:
        return False
