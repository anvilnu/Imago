# 🔄 Cómo actualizar Imago (instalador y portable)

Guía **paso a paso, sin prisa**. Úsala cada vez que cambies el código de Imago y
quieras volver a generar el **instalador** (`ImagoSetup.exe`) y la **versión
portable** (`Imago-1.0-portable.zip`).

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
> Verás cómo avanza por 4 fases:
> `1/4 Icono` → `2/4 PyInstaller` → `3/4 Inno Setup` → `4/4 ZIP portable`.
> Cuando termine, verás en verde **"Listo: ..."**.

### Paso 5 — Recoge los resultados
Ya están regenerados y listos para repartir:

| Qué | Dónde queda |
|---|---|
| 🧩 **Instalador** | `installer\ImagoSetup.exe` |
| 🎒 **Portable** | `Imago-1.0-portable.zip` |

**¡Y ya está!** Eso es todo el proceso de actualización.

---

## 💻 Cómo poner la versión nueva en tu propio PC

- **Instalada:** ejecuta el nuevo `installer\ImagoSetup.exe`. Se instala **encima**
  de la anterior (no hace falta desinstalar nada). Tus ajustes se conservan.
- **Portable:** extrae el nuevo `Imago-1.0-portable.zip` **encima de la carpeta
  vieja** y acepta reemplazar. Como la carpeta `datos\` **no** viene dentro del ZIP,
  **no se borra**: conservas tus ajustes y modelos de IA. 👌

---

## 🔢 (Opcional) Cambiar el número de versión

Si quieres pasar, por ejemplo, de **1.0** a **1.1**, cambia el número en estos **3
sitios** antes de ejecutar el script del Paso 4:

1. **`help_dialogs.py`** → busca `APP_VERSION = "1.0"` y ponlo en `"1.1"`
   *(es el número que se ve en Ayuda → Acerca de).*
2. **`Imago.iss`** → línea `AppVersion=1.0` → `AppVersion=1.1`
3. **`empaquetar.ps1`** → línea `$zip = "Imago-1.0-portable.zip"` →
   `$zip = "Imago-1.1-portable.zip"` *(para que el ZIP salga con el nombre nuevo).*

Si no cambias nada, no pasa nada: simplemente se regenera la 1.0 encima.

---

## 🆘 Si algo va mal

- **"no se puede ejecutar scripts en este sistema"** → estás ejecutando el script
  sin el permiso. Usa **exactamente** el comando del Paso 4 (el que lleva
  `-ExecutionPolicy Bypass`).
- **Error de "Acceso denegado" o no puede escribir en `dist`** → tienes **Imago
  abierto**. Ciérralo (incluida cualquier ventana que hayas abierto desde
  `dist\Imago`) y vuelve a ejecutar el script.
- **"Inno Setup no encontrado"** (amarillo al final) → el `.exe` y el ZIP portable
  **sí se generaron**; solo faltó el instalador. Instala Inno Setup 6 (ver abajo), o
  abre `Imago.iss` con doble clic y pulsa el botón **Build (▶)**.
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
5. Recoge `installer\ImagoSetup.exe` y `Imago-1.0-portable.zip`.
