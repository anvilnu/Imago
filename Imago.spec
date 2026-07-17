# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller: receta para construir Imago.exe (one-folder, sin consola).
# Construir con:  python -m PyInstaller --noconfirm Imago.spec
# Salida:         dist\Imago\Imago.exe  (+ carpeta _internal con las dependencias)
#
# Particularidades de este proyecto que resuelve la receta:
#  - Los iconos viajan EMBEBIDOS en recursos_rc.py (generado por
#    generar_recursos.py); NO se empaqueta la carpeta icons/ como datos.
#  - ai.* se importan POR NOMBRE (importlib) en el worker de IA -> PyInstaller no
#    los detecta solo; se declaran con collect_submodules('ai').
#  - onnxruntime(-directml) / cv2 / scipy / psd_tools traen DLLs y datos que hay
#    que arrastrar con collect_all.
#  - Los modelos ONNX NO se empaquetan: se descargan a AppData la primera vez que
#    se usa una funcion de IA (el instalador queda mucho mas ligero).

import os
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas = []
binaries = []
hiddenimports = collect_submodules('ai')

# Plugins de EJEMPLO incluidos: viajan como datos (manifest.json + .py), NO como
# codigo importado por PyInstaller (se cargan por ruta con importlib en runtime).
# Se empaquetan en _internal/plugins/... ; el PluginManager los busca en
# sys._MEIPASS/plugins. Se omiten cachés (__pycache__/.pyc). Los plugins de
# TERCEROS no viajan aqui: el usuario los deja en su carpeta de datos.
for _raiz, _dirs, _archivos in os.walk('plugins'):
    if '__pycache__' in _raiz:
        continue
    for _f in _archivos:
        if _f.endswith('.pyc'):
            continue
        _ruta = os.path.join(_raiz, _f)
        datas.append((_ruta, _raiz))

# pillow_heif (.avif/.heic) y pillow_jxl (.jxl) tambien llevan DLLs nativas de
# codecs y se importan PEREZOSAMENTE (main._cargar_via_pillow): collect_all los
# arrastra completos para que el instalador y el portable abran esos formatos.
for _pkg in ('onnxruntime', 'cv2', 'scipy', 'psd_tools',
             'pillow_heif', 'pillow_jxl'):
    _d, _b, _h = collect_all(_pkg)
    datas += _d
    binaries += _b
    hiddenimports += _h

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Imago',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon='icons/imago.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='Imago',
)
