# 🔄 Cómo actualizar Imago (instalador y portable)

Guía **paso a paso, sin prisa**. Úsala cada vez que cambies el código de Imago y
quieras volver a generar el **instalador** (`ImagoSetup.exe`) y la **versión
portable** (`Imago-<versión>-portable.zip`).

> **La idea en una frase:** ejecutas **un solo script** (`empaquetar.ps1`) y él te
> regenera TODO: el `.exe`, el instalador y el ZIP portable. Nada más.

---

## ✅ Antes de empezar (esto ya lo tienes instalado)

No hace falta tocar nada; solo para que sepas qué usa por debajo:

- Python con su entorno `.venv` y las dependencias + **PyInstaller**.
- **Inno Setup 6** (el que crea el instalador).

Si algún día cambias de ordenador y falta algo, mira el final: **"Reinstalar las
herramientas"**.

---

## 🟢 Los 5 pasos para actualizar

### Paso 1 — Guarda tus cambios de código
En VSCode, guarda todos los archivos que tocaste (**Ctrl+S**, o *Archivo →
Guardar todo*). Si no está guardado, no entra en la nueva versión.

### Paso 1.5 (SOLO si tocaste iconos) — Regenera los recursos
Los iconos ya **no** viajan en una carpeta suelta: van **embebidos** dentro del
programa (en `recursos_rc.py`). Por eso, si añadiste, quitaste o cambiaste algún
PNG de la carpeta `icons\`, tienes que regenerar los recursos **antes** de
empaquetar. Ejecuta:

```powershell
.\.venv\Scripts\python.exe generar_recursos.py
```

Eso reconstruye `recursos.qrc` y `recursos_rc.py` a partir de la carpeta `icons\`.
⚠️ **Si te lo saltas, el icono nuevo no aparecerá** en la versión empaquetada
(seguirá mostrándose el juego de iconos anterior). Si en este cambio **no** tocaste
ningún icono, sáltate este paso: no hace falta.

### Paso 2 — Cierra Imago si lo tienes abierto
Sobre todo si abriste `dist\Imago\Imago.exe`. Si está abierto, el script no podrá
sobrescribir sus archivos y fallará. (La versión **instalada** puedes cerrarla
también, por si acaso.)

### Paso 3 — Abre una terminal EN la carpeta del proyecto
Elige la que te resulte más fácil:

- **Desde VSCode** (lo más cómodo): menú **Terminal → Nueva terminal**. Se abre ya
  dentro de `d:\Python\editor_imagenes`.
- **Desde el Explorador de Windows**: entra en la carpeta `d:\Python\editor_imagenes`,
  mantén pulsado **Mayús** y haz **clic derecho** en un hueco vacío →
  *"Abrir ventana de PowerShell aquí"*.

### Paso 4 — Ejecuta el script
Copia y pega esta línea, pulsa **Enter** y espera:

```powershell
powershell -ExecutionPolicy Bypass -File .\empaquetar.ps1
```

> ⏳ **Tarda varios minutos** (el paso de PyInstaller es el lento; es normal).
> Verás cómo avanza por 5 fases:
> `1/5 Icono` → `2/5 PyInstaller` → `3/5 Inno Setup` →
> `4/5 ZIP portable` → `5/5 Higiene, tamaños y hashes`.
> Cuando termine, verás en verde **"Listo: ..."**.

### Paso 5 — Recoge los resultados
Ya están regenerados y listos para repartir:

| Qué | Dónde queda |
|---|---|
| 🧩 **Instalador** | `installer\ImagoSetup.exe` |
| 🎒 **Portable** | `Imago-<versión>-portable.zip` |

La última fase muestra el tamaño exacto y el SHA-256 de ambos archivos. También
comprueba que el ZIP tenga su marcador `portable.txt`, que la distribución
instalada no lo tenga y que ningún paquete incluya `datos`, logs, cachés o
bytecode local. También exige que el contenido y los tamaños del ZIP coincidan
archivo por archivo con `dist\Imago`. Si falla una comprobación, **no publiques
esos archivos**.

**¡Y ya está!** Eso es todo el proceso de actualización.

---

## 🧹 Qué se genera y qué se versiona

El repositorio conserva el código y las recetas de construcción, no sus salidas.
Estos artefactos son locales, están cubiertos por `.gitignore` y se pueden volver
a generar:

| Artefacto | Uso | Cómo se regenera |
|---|---|---|
| `.venv\` | Entorno y dependencias locales | `pip install -r requirements.txt` |
| `build\` | Trabajo temporal de PyInstaller | `empaquetar.ps1` |
| `dist\Imago\` | Aplicación desplegada sin comprimir | `empaquetar.ps1` |
| `installer\ImagoSetup.exe` | Instalador de Windows | Inno Setup desde `empaquetar.ps1` |
| `Imago-*-portable.zip` | Paquete portable publicable | `empaquetar.ps1` |
| `icons\imago.ico` | Icono temporal para empaquetar | `empaquetar.ps1` |
| `__pycache__`, `*.pyc`, logs y cachés de herramientas | Datos efímeros | Los recrean Python y las herramientas |
| `datos\` y `portable.txt` en la raíz | Ajustes/datos locales del modo portable | Los crea Imago al ejecutarse |

Sí se versionan `Imago.spec`, `Imago.iss`, `empaquetar.ps1` y
`verificar_distribucion.py`, porque son las recetas reproducibles.

Antes de publicar una distribución ya construida también puedes repetir solo la
auditoría, sin modificar ningún archivo:

```powershell
.\.venv\Scripts\python.exe verificar_distribucion.py
```

Si conservas ZIP de varias versiones en la carpeta del proyecto, indica el que
quieres revisar con `--portable ruta\al\archivo.zip`; la autodetección se niega a
elegir uno al azar para evitar publicar una versión antigua.

Como referencia de la auditoría del 18-07-2026, la versión 1.0 ocupa
**494,85 MiB** desplegada, **191,74 MiB** en ZIP y **134,39 MiB** como instalador.
Los tamaños cambiarán con las dependencias; revisa siempre las cifras que imprime
el verificador actual.

---

## 💻 Cómo poner la versión nueva en tu propio PC

- **Instalada:** ejecuta el nuevo `installer\ImagoSetup.exe`. Se instala **encima**
  de la anterior (no hace falta desinstalar nada). Tus ajustes se conservan.
- **Portable:** extrae el nuevo `Imago-<versión>-portable.zip` **encima de la carpeta
  vieja** y acepta reemplazar. Como la carpeta `datos\` **no** viene dentro del ZIP,
  **no se borra**: conservas tus ajustes y modelos de IA. 👌

---

## 🔢 (Opcional) Cambiar el número de versión

La versión tiene una **única fuente de verdad**: `imago_version.py`. Para pasar,
por ejemplo, de **1.0** a **1.1**, abre ese archivo y cambia solamente:

```python
APP_VERSION = "1.1"
```

Admite versiones numéricas como `1.1`, `1.2.1` o `2.0.0.1`. Después ejecuta
`empaquetar.ps1` como siempre. El mismo valor aparecerá en Ayuda ▸ Acerca de,
en los metadatos del instalador y en el nombre `Imago-1.1-portable.zip`. Ya no
hay que editar `help_dialogs.py`, `Imago.iss` ni `empaquetar.ps1`.

---

## 🆘 Si algo va mal

- **"no se puede ejecutar scripts en este sistema"** → estás ejecutando el script
  sin el permiso. Usa **exactamente** el comando del Paso 4 (el que lleva
  `-ExecutionPolicy Bypass`).
- **Error de "Acceso denegado" o no puede escribir en `dist`** → tienes **Imago
  abierto**. Ciérralo (incluida cualquier ventana que hayas abierto desde
  `dist\Imago`) y vuelve a ejecutar el script.
- **"Inno Setup no encontrado"** (amarillo al final) → el `.exe` y el ZIP portable
  **sí se generaron** y se verifican; el instalador se omite y cualquier copia
  anterior de `ImagoSetup.exe` **no cuenta como actualizada**. Instala Inno Setup 6
  (ver abajo) y vuelve a ejecutar `empaquetar.ps1`.
- **Windows dice "Editor desconocido"** al instalar/abrir → es normal (el `.exe` no
  está firmado): *Más información → Ejecutar de todos modos*.
- **El antivirus marca el `.exe`** → es un falso positivo típico de los programas
  hechos con PyInstaller. Añade una excepción. (Se elimina del todo solo firmando el
  ejecutable con un certificado de pago, opcional.)

---

## 🧰 Reinstalar las herramientas (SOLO si cambias de PC o se rompe el `.venv`)

Desde una terminal en la carpeta del proyecto:

```powershell
# Dependencias de Imago + PyInstaller (dentro del entorno .venv)
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install pyinstaller
```

Y **Inno Setup 6** se descarga e instala desde: https://jrsoftware.org/isdl.php

---

### 📌 Chuleta rápida (para cuando ya le pilles el truco)

1. Guarda el código. *(Si tocaste iconos: `.\.venv\Scripts\python.exe generar_recursos.py`)*
2. Cierra Imago.
3. Terminal en la carpeta del proyecto.
4. `powershell -ExecutionPolicy Bypass -File .\empaquetar.ps1`
5. Confirma que la verificación termina en «Distribución apta para publicar» y
   recoge `installer\ImagoSetup.exe` y `Imago-<versión>-portable.zip`.
