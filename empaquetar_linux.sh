#!/usr/bin/env bash
# Construye los paquetes Linux de Imago a partir de una única salida PyInstaller.
# Requiere Python + dependencias, PyInstaller, appimagetool, Flatpak y
# flatpak-builder con org.freedesktop.Platform/SDK 25.08 instalados.

set -Eeuo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$RAIZ"

PYTHON_BIN="${PYTHON_BIN:-python3}"
APPIMAGETOOL="${APPIMAGETOOL:-appimagetool}"
ID_APP="io.github.anvilnu.imago"
SALIDA="$RAIZ/salida"
APPDIR="$RAIZ/build/AppDir"
BUILD_FLATPAK="$RAIZ/build/flatpak-build"
REPO_FLATPAK="$RAIZ/build/flatpak-repo"
METADATOS_LINUX="$RAIZ/build/linux-metadata"

VERSION="$($PYTHON_BIN -c 'from imago_version import APP_VERSION; print(APP_VERSION)')"
if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+(\.[0-9]+){0,2}$ ]]; then
    echo "Versión no válida: $VERSION" >&2
    exit 1
fi

for herramienta in "$PYTHON_BIN" "$APPIMAGETOOL" appstreamcli \
                   desktop-file-validate flatpak flatpak-builder; do
    if ! command -v "$herramienta" >/dev/null 2>&1 && [[ ! -x "$herramienta" ]]; then
        echo "Herramienta no encontrada: $herramienta" >&2
        exit 1
    fi
done

rm -rf -- "$METADATOS_LINUX"
mkdir -p "$METADATOS_LINUX"
sed "s/@APP_VERSION@/$VERSION/g" \
    packaging/linux/$ID_APP.metainfo.xml \
    > "$METADATOS_LINUX/$ID_APP.metainfo.xml"
desktop-file-validate packaging/linux/$ID_APP.desktop
appstreamcli validate --no-net "$METADATOS_LINUX/$ID_APP.metainfo.xml"

echo "Versión de Imago: $VERSION"
echo "== 1/5  PyInstaller para Linux =="
"$PYTHON_BIN" -m PyInstaller --noconfirm --clean Imago.spec

# Documentos legales (GPLv3, README y avisos de terceros): se copian a
# dist/Imago para que los recojan TANTO el AppImage (cp -a dist/Imago/.) COMO el
# Flatpak (su fuente es dist/Imago). Mismo criterio que empaquetar.ps1.
echo "== Documentos legales (licencia y avisos) =="
for doc in LICENSE README.md TERCEROS.md; do
    if [[ -f "$doc" ]]; then
        cp -a "$doc" dist/Imago/
        echo "  incluido: $doc"
    else
        echo "  AVISO: no se encontró $doc (no se incluirá)." >&2
    fi
done

echo "== 2/5  AppDir =="
rm -rf -- "$APPDIR"
mkdir -p "$APPDIR/usr/lib/imago" \
         "$APPDIR/usr/share/applications" \
         "$APPDIR/usr/share/icons/hicolor/64x64/apps" \
         "$APPDIR/usr/share/metainfo"
cp -a dist/Imago/. "$APPDIR/usr/lib/imago/"
install -Dm755 packaging/linux/AppRun "$APPDIR/AppRun"
install -Dm644 packaging/linux/$ID_APP.desktop "$APPDIR/$ID_APP.desktop"
install -Dm644 packaging/linux/$ID_APP.desktop \
    "$APPDIR/usr/share/applications/$ID_APP.desktop"
install -Dm644 "$METADATOS_LINUX/$ID_APP.metainfo.xml" \
    "$APPDIR/usr/share/metainfo/$ID_APP.metainfo.xml"
install -Dm644 icons/imago.png "$APPDIR/$ID_APP.png"
install -Dm644 icons/imago.png \
    "$APPDIR/usr/share/icons/hicolor/64x64/apps/$ID_APP.png"
ln -s "$ID_APP.png" "$APPDIR/.DirIcon"

mkdir -p "$SALIDA"
APPIMAGE="$SALIDA/Imago-$VERSION-x86_64.AppImage"
FLATPAK="$SALIDA/Imago-$VERSION-x86_64.flatpak"
rm -f -- "$APPIMAGE" "$APPIMAGE.sha256" "$FLATPAK" "$FLATPAK.sha256"

echo "== 3/5  AppImage =="
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$APPIMAGETOOL" "$APPDIR" "$APPIMAGE"
chmod +x "$APPIMAGE"

echo "== 4/5  Flatpak =="
rm -rf -- "$BUILD_FLATPAK" "$REPO_FLATPAK"
flatpak-builder --force-clean --repo="$REPO_FLATPAK" \
    "$BUILD_FLATPAK" packaging/linux/$ID_APP.yml
flatpak build-bundle --arch=x86_64 \
    --runtime-repo=https://flathub.org/repo/flathub.flatpakrepo \
    "$REPO_FLATPAK" "$FLATPAK" "$ID_APP" stable

echo "== 5/5  Tamaños y SHA-256 =="
(
    cd "$SALIDA"
    sha256sum "$(basename "$APPIMAGE")" > "$(basename "$APPIMAGE").sha256"
    sha256sum "$(basename "$FLATPAK")" > "$(basename "$FLATPAK").sha256"
    du -h "$(basename "$APPIMAGE")" "$(basename "$FLATPAK")"
    cat "$(basename "$APPIMAGE").sha256" "$(basename "$FLATPAK").sha256"
)

echo "Paquetes Linux listos en: $SALIDA"
