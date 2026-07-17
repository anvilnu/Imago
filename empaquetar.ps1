# empaquetar.ps1 - Construye Imago.exe y (si Inno Setup esta instalado) el instalador.
# Uso:  .\empaquetar.ps1
# Requiere haber hecho antes (una sola vez):
#   .\.venv\Scripts\python.exe -m pip install pyinstaller
#   e instalar Inno Setup 6 (https://jrsoftware.org/isdl.php)

$py = ".\.venv\Scripts\python.exe"

Write-Host "== 1/4  Icono =="
& $py -c "from PIL import Image; Image.open('icons/imago.png').save('icons/imago.ico', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])"

Write-Host "== 2/4  PyInstaller (esto tarda varios minutos) =="
& $py -m PyInstaller --noconfirm Imago.spec
if ($LASTEXITCODE -ne 0) { Write-Host "PyInstaller fallo. Revisa el error de arriba." -ForegroundColor Red; exit 1 }

Write-Host "== 3/4  Inno Setup (instalador) =="
# OJO: el instalador se construye SIN el marcador portable.txt -> la version
# instalada NO es portable (usa registro + AppData, como debe ser).
# ISCC.exe puede estar en instalacion global (Program Files) o por usuario (AppData).
$isccCandidatos = @(
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
)
$iscc = $isccCandidatos | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($iscc) {
    & $iscc Imago.iss
    Write-Host "Listo: installer\ImagoSetup.exe" -ForegroundColor Green
} else {
    Write-Host "Inno Setup no encontrado. Abre Imago.iss en Inno Setup y pulsa Build." -ForegroundColor Yellow
}

Write-Host "== 4/4  ZIP portable (autocontenido) =="
# Se anade el marcador portable.txt SOLO al ZIP (se borra tras comprimir): con el,
# Imago guarda ajustes, modelos y autoguardado en la carpeta 'datos' junto al .exe.
$marker = "dist\Imago\portable.txt"
$zip = "Imago-1.0-portable.zip"
Set-Content -Path $marker -Value "Modo portable: Imago guarda sus datos (ajustes, modelos de IA y autoguardado) en la carpeta 'datos' junto a este ejecutable. No borres este archivo." -Encoding UTF8
try {
    if (Test-Path $zip) { Remove-Item $zip -Force }
    Compress-Archive -Path "dist\Imago" -DestinationPath $zip -CompressionLevel Optimal
    Write-Host "Listo: $zip" -ForegroundColor Green
} finally {
    Remove-Item $marker -Force
}
