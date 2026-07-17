#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Genera los recursos EMBEBIDOS de Imago a partir de la carpeta icons/.

Recorre icons/ (incluidas subcarpetas como icons/cursor/), escribe recursos.qrc
listando todos los archivos bajo el prefijo "/", y lo compila con pyside6-rcc a
recursos_rc.py. La aplicación solo tiene que hacer `import recursos_rc` (lo hace
main.py) para que todos los iconos queden disponibles como ":/icons/...".

Ejecuta este script CADA VEZ que añadas, quites o cambies un icono en icons/:

    python generar_recursos.py

Así los iconos NO se distribuyen como carpeta suelta: viajan dentro del propio
programa. (No es cifrado: un curioso con herramientas de Qt podría extraerlos;
solo evita la carpeta abierta a la vista.)
"""
import os
import sys
import shutil
import subprocess

RAIZ = os.path.dirname(os.path.abspath(__file__))
DIR_ICONS = os.path.join(RAIZ, "icons")
QRC = os.path.join(RAIZ, "recursos.qrc")
SALIDA_PY = os.path.join(RAIZ, "recursos_rc.py")


def buscar_rcc():
    """Localiza el ejecutable pyside6-rcc (en el PATH o junto al intérprete)."""
    ruta = shutil.which("pyside6-rcc")
    if ruta:
        return ruta
    base = os.path.dirname(sys.executable)
    for sub, nombre in (("Scripts", "pyside6-rcc.exe"), ("bin", "pyside6-rcc")):
        cand = os.path.join(base, sub, nombre)
        if os.path.exists(cand):
            return cand
        cand = os.path.join(base, nombre)
        if os.path.exists(cand):
            return cand
    return None


def recopilar_iconos():
    """Rutas relativas (con /) de todos los archivos bajo icons/, ordenadas."""
    rutas = []
    for carpeta, _dirs, archivos in os.walk(DIR_ICONS):
        for nombre in archivos:
            abs_ = os.path.join(carpeta, nombre)
            rel = os.path.relpath(abs_, RAIZ).replace(os.sep, "/")
            rutas.append(rel)
    rutas.sort()
    return rutas


def escribir_qrc(rutas):
    lineas = ['<!DOCTYPE RCC><RCC version="1.0">', '  <qresource prefix="/">']
    lineas += ["    <file>%s</file>" % r for r in rutas]
    lineas += ["  </qresource>", "</RCC>", ""]
    # CRLF, como el resto del proyecto.
    with open(QRC, "w", encoding="utf-8", newline="\r\n") as f:
        f.write("\n".join(lineas))


def main():
    if not os.path.isdir(DIR_ICONS):
        print("ERROR: no existe la carpeta icons/ junto a este script.")
        return 1
    rutas = recopilar_iconos()
    if not rutas:
        print("ERROR: la carpeta icons/ está vacía.")
        return 1
    escribir_qrc(rutas)
    print("recursos.qrc: %d archivos" % len(rutas))

    rcc = buscar_rcc()
    if not rcc:
        print("ERROR: no se encontró pyside6-rcc. Instala PySide6 (pip install "
              "PySide6) o añádelo al PATH.")
        return 1
    res = subprocess.run([rcc, QRC, "-o", SALIDA_PY])
    if res.returncode != 0:
        print("ERROR: pyside6-rcc devolvió el código %d." % res.returncode)
        return res.returncode

    # pyside6-rcc emite LF; el proyecto usa CRLF. Reescribimos en CRLF.
    with open(SALIDA_PY, "rb") as f:
        data = f.read()
    data = data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    with open(SALIDA_PY, "wb") as f:
        f.write(data)

    print("recursos_rc.py generado (%d KB)." % (len(data) // 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
