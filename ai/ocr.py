# ai/ocr.py
"""OCR local: extrae el texto de la imagen (PP-OCR de PaddleOCR, Apache-2.0).

Dos modelos ONNX (conversion monkt/paddleocr-onnx, Apache-2.0):
  1. DETECCION (DBNet movil): mapa de probabilidad de "hay texto" por pixel; los
     cuadros salen de sus contornos (OpenCV) ensanchados un margen proporcional
     area/perimetro (el "unclip" de PaddleOCR sin la dependencia pyclipper).
  2. RECONOCIMIENTO (PP-OCRv5 movil latino, 34 idiomas incl. espanol): cada
     recorte se endereza con un warp de perspectiva y se lee con decodificacion
     CTC voraz (colapsar repetidos y quitar el separador).

El diccionario del reconocedor (ppocrv5_latin_dict.txt, 502 caracteres, uno por
clase) viaja EMBEBIDO en _LATIN_DICT para no anadir un tercer fichero al
catalogo: la clase 0 es el separador CTC, 1..502 = _LATIN_DICT y 503 el espacio.

Necesita OpenCV (contornos y warps); el llamador lo comprueba antes.
Trabajo SINCRONO: se ejecuta en el hilo secundario del InferenceRunner.
"""

import numpy as np

from ai import imgproc
from ai.runner import get_session, run_session

# Diccionario del modelo latino (character_dict del inference.yml oficial de
# PaddlePaddle/latin_PP-OCRv5_mobile_rec_onnx; 836 clases).
_LATIN_DICT = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyzÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖ×ØÙÚÛÜÝÞßàáâãäåæçèéêëìíîïðñòóôõö÷øùúûüýþÿĀāĂăĄąĆćĈĉĊċČčĎďĐđĒēĔĕĖėĘęĚěĜĝĞğĠġĢģĤĥĦħĨĩĪīĬĭĮįİıĲĳĴĵĶķĸĹĺĻļĽľĿŀŁłŃńŅņŇňŉŊŋŌōŎŏŐőŒœŔŕŖŗŘřŚśŜŝŞşŠšŢţŤťŦŧŨũŪūŬŭŮůŰűŲųŴŵŶŷŸŹźŻżŽžſƀƁƂƃƄƅƆƇƈƉƊƋƌƍƎƏƐƑƒƓƔƕƖƗƘƙƚƛƜƝƞƟƠơƢƣƤƥƦƧƨƩƪƫƬƭƮƯưƱƲƳƴƵƶƷƸƹƺƻƼƽƾƿǀǁǂǃǄǅǆǇǈǉǊǋǌǍǎǏǐǑǒǓǔǕǖǗǘǙǚǛǜǝǞǟǠǡǢǣǤǥǦǧǨǩǪǫǬǭǮǯǰǱǲǳǴǵǶǷǸǹǺǻǼǽǾǿȀȁȂȃȄȅȆȇȈȉȊȋȌȍȎȏȐȑȒȓȔȕȖȗȘșȚțȜȝȞȟȠȡȢȣȤȥȦȧȨȩȪȫȬȭȮȯȰȱȲȳȴȵȶȷȸȹȺȻȼȽȾȿɀɁɂɃɄɅɆɇɈɉɊɋɌɍɎɏ!"#$%&\'()*+,-./:;<=>?@[\\]_`{|}^~©®℉№Ω℮™∆✓✔✗✘✕☑☒●▪▫◼▶◀⬆¤¦§¨ª«¬¯°²³´µ¶¸¹º»¼½¾¿×‐‑‒—―‖‗‘’‚‛“”„‟†‡‣․…‧‰‴‵‶‷‸‹›※‼‽‾−₤₡₹₽₴₿¢€£¥ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅪⅫⅰⅱⅲⅳⅴⅵⅶⅷⅸⅹⅺⅻ➀➁➂➃➄➅➆➇➈➉➊➋➌➍➎➏➐➑➒➓❶❷❸❹❺❻❼❽❾❿①②③④⑤⑥⑦⑧⑨⑩↑→↓↕←↔⇒⇐⇔∀∃∄∴∵∝∞∩∪∂∫∬∭∮∯∰∑∏√∛∜∱∲∳∶∷∼∖∗≈≠≡≤≥⊂⊃⊥⊾⊿□∥∋ƒ′″ÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖØÙÚÛÜÝÞàáâãäåæçèéêëìíîïðñòóôõöøùúûüýþÿΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩαβγδεζηθικλμνξοπρσςτυφχψωÅℏ⌀⍺⍵𝑢𝜓०‥︽﹥•÷∕∙⋅·±∓∟∠∡∢℧☺'

_DET_SIDE = 960         # el lado MAYOR se reescala a esto (como DetResizeForTest)
_DET_THRESH = 0.3       # binarizado del mapa de probabilidad
_BOX_THRESH = 0.6       # confianza minima de un cuadro (media del mapa dentro)
_UNCLIP = 1.5           # ensanchado del cuadro (area/perimetro, como PaddleOCR)
_REC_H = 48             # altura de entrada del reconocedor
_REC_MAX_W = 1440       # tope de anchura de un recorte
_MIN_TEXT_CONF = 0.5    # confianza media minima del texto reconocido

# Normalizacion del detector (inference.yml oficial: BGR + ImageNet).
_DET_MEAN = (0.485, 0.456, 0.406)
_DET_STD = (0.229, 0.224, 0.225)


def _cv2():
    import cv2
    return cv2


# ----------------------------------------------------------------- deteccion
def _order_box(pts):
    """Ordena 4 esquinas como arriba-izq, arriba-der, abajo-der, abajo-izq."""
    s = pts.sum(axis=1)
    d = pts[:, 0] - pts[:, 1]
    return np.array([pts[np.argmin(s)], pts[np.argmax(d)],
                     pts[np.argmax(s)], pts[np.argmin(d)]], np.float32)


def _detect_boxes(rgb, det_path):
    """Cuadros de texto: lista de (4, 2) float32 (esquinas ordenadas) en
    coordenadas de la imagen original."""
    cv2 = _cv2()
    h, w = rgb.shape[:2]
    # DBNet exige lados multiplos de 32; el lado MAYOR se lleva a _DET_SIDE
    # (tambien hacia arriba: ayuda con el texto pequeno) estirando, como el
    # DetResizeForTest (resize_long) de PaddleOCR.
    scale = _DET_SIDE / float(max(h, w))
    dw = max(32, int(round(w * scale / 32.0)) * 32)
    dh = max(32, int(round(h * scale / 32.0)) * 32)
    small = cv2.resize(rgb, (dw, dh), interpolation=cv2.INTER_LINEAR)
    # Preprocesado del inference.yml oficial: BGR + /255 + mean/std ImageNet.
    x = imgproc.to_tensor(small[:, :, ::-1], mean=_DET_MEAN, std=_DET_STD)
    session = get_session(det_path)
    prob = run_session(session, {session.get_inputs()[0].name: x})[0][0, 0]

    mask = (prob > _DET_THRESH).astype(np.uint8)
    contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    sx, sy = w / float(dw), h / float(dh)
    boxes = []
    for cnt in contours:
        if len(cnt) < 4:
            continue
        (cx, cy), (bw, bh), ang = cv2.minAreaRect(cnt)
        if min(bw, bh) < 3:
            continue
        # Confianza del cuadro: media del mapa DENTRO del contorno.
        bx, by, bws, bhs = cv2.boundingRect(cnt)
        patch = prob[by:by + bhs, bx:bx + bws]
        m = np.zeros(patch.shape, np.uint8)
        cv2.fillPoly(m, [cnt.reshape(-1, 2) - (bx, by)], 1)
        inside = m.astype(bool)
        score = float(patch[inside].mean()) if inside.any() else 0.0
        if score < _BOX_THRESH:
            continue
        # "Unclip": el mapa de DBNet encoge el texto; se ensancha area/perimetro.
        area, per = bw * bh, 2.0 * (bw + bh)
        d = area * _UNCLIP / per if per > 0 else 0.0
        box = cv2.boxPoints(((cx, cy), (bw + 2.0 * d, bh + 2.0 * d), ang))
        box[:, 0] *= sx                     # a coordenadas originales
        box[:, 1] *= sy
        boxes.append(_order_box(box))
    return boxes


# ------------------------------------------------------------ reconocimiento
def _crop_box(cv2, rgb, box):
    """Recorte enderezado (warp de perspectiva) del cuadro; None si es minusculo.
    Un recorte mas alto que ancho (vertical) se tumba, como PaddleOCR."""
    tl, tr, br, bl = box
    cw = int(round(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl))))
    ch = int(round(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl))))
    if cw < 3 or ch < 3:
        return None
    dst = np.array([[0, 0], [cw - 1, 0], [cw - 1, ch - 1], [0, ch - 1]],
                   np.float32)
    mat = cv2.getPerspectiveTransform(box, dst)
    crop = cv2.warpPerspective(rgb, mat, (cw, ch), flags=cv2.INTER_CUBIC)
    if ch >= cw * 1.5:
        crop = np.rot90(crop)
    return crop


def _recognize(cv2, session, in_name, crop):
    """Lee un recorte: (texto, confianza media). Decodificacion CTC voraz."""
    h, w = crop.shape[:2]
    rw = min(_REC_MAX_W, max(16, int(round(w * _REC_H / float(h)))))
    img = cv2.resize(crop[:, :, ::-1], (rw, _REC_H),   # a BGR (como PaddleOCR)
                     interpolation=cv2.INTER_LINEAR)
    x = (img.astype(np.float32) / 255.0 - 0.5) / 0.5
    x = np.ascontiguousarray(x.transpose(2, 0, 1)[None])
    out = run_session(session, {in_name: x})[0][0]      # (T, nº de clases)
    idxs = out.argmax(axis=1)
    probs = out.max(axis=1)
    n = len(_LATIN_DICT)
    chars, confs = [], []
    prev = 0
    for i, k in enumerate(idxs):
        k = int(k)
        if k != prev and k != 0:
            chars.append(_LATIN_DICT[k - 1] if k <= n else " ")
            confs.append(float(probs[i]))
        prev = k
    if not chars:
        return "", 0.0
    return "".join(chars).strip(), float(np.mean(confs))


def _group_lines(items):
    """Agrupa los cuadros leidos en LINEAS por su altura vertical y devuelve la
    lista de lineas de texto (izquierda a derecha, arriba a abajo)."""
    def cx(b):
        return float(b[:, 0].mean())

    def cy(b):
        return float(b[:, 1].mean())

    def alto(b):
        return float(b[:, 1].max() - b[:, 1].min())

    items = sorted(items, key=lambda it: cy(it[0]))
    lines = []
    for it in items:
        if lines:
            last = lines[-1]
            ref = sum(cy(b) for b, _ in last) / len(last)
            band = 0.6 * sum(alto(b) for b, _ in last) / len(last)
            if abs(cy(it[0]) - ref) <= band:
                last.append(it)
                continue
        lines.append([it])
    out = []
    for line in lines:
        line.sort(key=lambda it: cx(it[0]))
        out.append(" ".join(text for _, text in line))
    return out


def extract_text(rgb, det_path, rec_path, report=None, token=None):
    """rgb (H, W, 3) uint8 -> (texto, nº de zonas leidas). Texto "" si no se
    encontro nada; None si se cancelo. Sincrono."""
    cv2 = _cv2()
    boxes = _detect_boxes(rgb, det_path)
    if token is not None and token.cancelled:
        return None
    if report is not None:
        report(20)
    if not boxes:
        return "", 0

    session = get_session(rec_path)
    in_name = session.get_inputs()[0].name
    items = []
    for i, box in enumerate(boxes):
        if token is not None and token.cancelled:
            return None
        crop = _crop_box(cv2, rgb, box)
        if crop is not None:
            text, conf = _recognize(cv2, session, in_name, crop)
            if text and conf >= _MIN_TEXT_CONF:
                items.append((box, text))
        if report is not None:
            report(min(99, 20 + (i + 1) * 79 // len(boxes)))
    if not items:
        return "", 0
    return "\n".join(_group_lines(items)), len(items)
