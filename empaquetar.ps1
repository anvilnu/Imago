# empaquetar.ps1 - Construye Imago.exe y (si Inno Setup esta instalado) el instalador.
# Uso:  .\empaquetar.ps1
# Requiere haber hecho antes (una sola vez):
#   .\.venv\Scripts\python.exe -m pip install pyinstaller
#   e instalar Inno Setup 6 (https://jrsoftware.org/isdl.php)

$py = ".\.venv\Scripts\python.exe"
$versionSalida = & $py -c "from imago_version import APP_VERSION; print(APP_VERSION)"
if ($LASTEXITCODE -ne 0) { Write-Host "No se pudo leer la versión de imago_version.py." -ForegroundColor Red; exit 1 }
$version = "$versionSalida".Trim()
if ($version -notmatch '^\d+\.\d+(?:\.\d+){0,2}$') { Write-Host "Versión no válida: $version" -ForegroundColor Red; exit 1 }
Write-Host "Versión de Imago: $version" -ForegroundColor Cyan

Write-Host "== 1/5  Icono =="
& $py -c "from PIL import Image; Image.open('icons/imago.png').save('icons/imago.ico', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])"

Write-Host "== 2/5  PyInstaller (esto tarda varios minutos) =="
& $py -m PyInstaller --noconfirm Imago.spec
if ($LASTEXITCODE -ne 0) { Write-Host "PyInstaller fallo. Revisa el error de arriba." -ForegroundColor Red; exit 1 }

Write-Host "== 3/5  Inno Setup (instalador) =="
# OJO: el instalador se construye SIN el marcador portable.txt -> la version
# instalada NO es portable (usa registro + AppData, como debe ser).
# ISCC.exe puede estar en instalacion global (Program Files) o por usuario (AppData).
$isccCandidatos = @(
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
)
$iscc = $isccCandidatos | Where-Object { Test-Path $_ } | Select-Object -First 1
$instaladorGenerado = $false
if ($iscc) {
    & $iscc "/DMyAppVersion=$version" Imago.iss
    if ($LASTEXITCODE -ne 0) { Write-Host "Inno Setup falló. Revisa el error de arriba." -ForegroundColor Red; exit 1 }
    $instaladorGenerado = $true
    Write-Host "Listo: installer\ImagoSetup.exe" -ForegroundColor Green
} else {
    Write-Host "Inno Setup no encontrado. Instálalo y vuelve a ejecutar empaquetar.ps1." -ForegroundColor Yellow
}

Write-Host "== 4/5  ZIP portable (autocontenido) =="
# Se anade el marcador portable.txt SOLO al ZIP (se borra tras comprimir): con el,
# Imago guarda ajustes, modelos y autoguardado en la carpeta 'datos' junto al .exe.
$marker = "dist\Imago\portable.txt"
$zip = "Imago-$version-portable.zip"
Set-Content -Path $marker -Value "Modo portable: Imago guarda sus datos (ajustes, modelos de IA y autoguardado) en la carpeta 'datos' junto a este ejecutable. No borres este archivo." -Encoding UTF8
try {
    if (Test-Path $zip) { Remove-Item $zip -Force }
    Compress-Archive -Path "dist\Imago" -DestinationPath $zip -CompressionLevel Optimal
    Write-Host "Listo: $zip" -ForegroundColor Green
} finally {
    Remove-Item $marker -Force
}

Write-Host "== 5/5  Higiene, tamaños y hashes =="
$argumentosVerificacion = @("verificar_distribucion.py", "--portable", $zip)
if (-not $instaladorGenerado) { $argumentosVerificacion += "--omitir-instalador" }
& $py @argumentosVerificacion
if ($LASTEXITCODE -ne 0) { Write-Host "La distribución no es apta para publicar." -ForegroundColor Red; exit 1 }
