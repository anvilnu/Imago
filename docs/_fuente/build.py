"""Regenera ../index.html incrustando la fuente y las imágenes (WebP) en base64.
Uso:  python build.py    (no necesita internet ni dependencias externas)."""
import base64, re, os
HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")

with open(os.path.join(HERE, "imago_site.template.html"), encoding="utf-8") as f:
    html = f.read()

def datauri(path, mime):
    with open(path, "rb") as fh:
        return "data:%s;base64,%s" % (mime, base64.b64encode(fh.read()).decode("ascii"))

html = html.replace("@@FONT@@", datauri(os.path.join(ASSETS, "cantarell.woff2"), "font/woff2"))
html, n = re.subn(r"@@IMG:([a-z0-9_]+)@@",
                  lambda m: datauri(os.path.join(ASSETS, m.group(1) + ".webp"), "image/webp"),
                  html)
assert not re.findall(r"@@[^@]+@@", html), "Quedan tokens sin sustituir"

out = os.path.join(HERE, "..", "index.html")
with open(out, "w", encoding="utf-8") as f:
    f.write(html)
print("OK ·", n, "imágenes ·", "%.2f MB" % (os.path.getsize(out)/1048576), "->", os.path.abspath(out))
