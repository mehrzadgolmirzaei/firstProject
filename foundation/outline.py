"""
خواندن نقشه اوت‌لاین سازنده (PDF): عددهای لازم برای بار تجهیز.

هر صفحه یک تجهیز فرض می‌شود. متن صفحه یا از لایه متنی PDF خوانده می‌شود یا، اگر صفحه اسکن
باشد، با OCR (rapidocr، اختیاری). بعد برای هر عدد برچسبش پیدا می‌شود («Total mass»،
«Center of gravity»، «wind load area»، «FR = … N») و نزدیک‌ترین عدد هم‌خط یا زیر آن برداشته
می‌شود. خروجی فقط «پیشنهاد» است: مهندس هر عدد را کنار تصویر همان صفحه — که جای برداشت
هر عدد روی آن علامت خورده — می‌بیند و تأیید می‌کند.

عددهایی که برداشته می‌شوند (همان واحد فرم تجهیز):
    He  ارتفاع تجهیز (m)         — برچسب Height، وگرنه بزرگ‌ترین اندازه قائم نقشه
    he  ارتفاع مرکز ثقل (m)      — برچسب Center of gravity
    Ae  سطح بادگیر (m²)          — برچسب wind (load) area
    We  وزن یک فاز (kg)          — Total mass / Weight / جدول جرم «3x1366» / W = a + b·L
    F   بار مجاز ترمینال (N)     — FR=، test load F=، permissible force، cantilever strength
"""
import math
import re
import threading
from dataclasses import dataclass

# نوع تجهیز از متن صفحه؛ ترتیب مهم است (DSE پیش از DS، CVT پیش از CT)
TYPE_WORDS = [
    ("DSROW", r"ROW\s*EREC|ROW\s*MOUNT|DS\s*-?\s*ROW"),
    ("DSE", r"EARTH(ING)?\s*SWITCH|DS\s*\+\s*ES|\bDSE\b"),
    ("DS", r"DISCONNECT|ISOLATOR|\bNSA\s*\d|\bDS\b"),
    ("LA", r"ARRESTER|ARESSTER|ARRESTOR"),
    ("CB", r"CIRCUIT\s*BREAKER|SF6[\s-]*BREAKER|\bHPL\s*\d|\bLTB\s*\d"),
    ("CVT", r"CAPACITIVE\s*VOLTAGE\s*TRANSF|VOLTAGE\s*TRANSFORMER|\bCVT\b|\bCPA\s*\d"),
    ("CT", r"CURRENT\s*TRANSFORMER|\bIMBD?\s*\d|\bCT\b"),
    ("PI", r"POST\s*INSULATOR|STATION\s*POST"),
]

NUM = r"(\d+(?:[.,]\d+)?)"

_ocr = None
_ocr_lock = threading.Lock()


@dataclass
class Tok:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def cx(self):
        return (self.x0 + self.x1) / 2

    @property
    def cy(self):
        return (self.y0 + self.y1) / 2

    @property
    def h(self):
        return self.y1 - self.y0

    @property
    def w(self):
        return self.x1 - self.x0

    @property
    def vertical(self):
        """متن چرخیده ۹۰ درجه (اندازه‌گذاری قائم نقشه)."""
        return self.h > 1.4 * self.w


def _pymupdf():
    """کتابخانه خواندن PDF (نام جدید pymupdf، نام قدیمی fitz)؛ اگر نصب نیست پیام روشن."""
    try:
        import pymupdf
        return pymupdf
    except ImportError:
        pass
    try:
        import fitz
        return fitz
    except ImportError:
        raise RuntimeError("کتابخانه خواندن PDF (PyMuPDF) روی این رایانه نصب نیست. برنامه را یک بار "
                           "ببندید و دوباره اجرا کنید تا خودش نصب کند، یا در پوشه foundation این را بزنید: "
                           "python -m pip install -r requirements.txt")


def _ocr_module():
    """
    موتور OCR: rapidocr نسخه ۳ (برای همه نسخه‌های پایتون، از جمله ۳٫۱۳ به بعد) یا
    rapidocr_onnxruntime قدیمی (فقط تا پایتون ۳٫۱۲). مدل‌ها داخل خود بسته‌اند؛ اینترنت لازم نیست.
    """
    import importlib.util
    for name in ("rapidocr", "rapidocr_onnxruntime"):
        try:
            if importlib.util.find_spec(name) is not None:
                return name
        except (ImportError, ValueError):
            continue
    return None


def ocr_available():
    return _ocr_module() is not None


def _ocr_engine():
    """تابعی که تصویر می‌گیرد و [(چهارگوشه، متن، اطمینان)] برمی‌گرداند."""
    global _ocr
    with _ocr_lock:
        if _ocr is None:
            import logging
            if _ocr_module() == "rapidocr":
                from rapidocr import RapidOCR
                eng = RapidOCR()

                def run(img):
                    r = eng(img)
                    if r is None or r.boxes is None:
                        return []
                    return list(zip(r.boxes.tolist(), r.txts, r.scores))
            else:
                from rapidocr_onnxruntime import RapidOCR
                eng = RapidOCR()

                def run(img):
                    res, _ = eng(img)
                    return res or []
            for n in ("RapidOCR", "rapidocr"):
                logging.getLogger(n).setLevel(logging.ERROR)
            _ocr = run
        return _ocr


def _tokens_text(page):
    """خط‌های لایه متنی PDF (هر خط یک توکن، با مختصات صفحه)."""
    out = []
    for b in page.get_text("dict")["blocks"]:
        for ln in b.get("lines", []):
            t = " ".join(s["text"] for s in ln["spans"]).strip()
            if t:
                x0, y0, x1, y1 = ln["bbox"]
                dx, dy = ln.get("dir", (1, 0))
                if abs(dy) > abs(dx):          # متن قائم
                    x0, x1 = min(x0, x1), max(x0, x1)
                out.append(Tok(t, x0, y0, x1, y1))
    return out


def _tokens_ocr(page, dpi=200, max_px=5000):
    import numpy as np
    # برگه‌های بزرگ (A1/A0) کوچک‌تر خوانده می‌شوند تا حافظه و زمان معقول بماند
    dpi = int(min(dpi, max_px * 72.0 / max(page.rect.width, page.rect.height, 1)))
    pix = page.get_pixmap(dpi=dpi)
    img = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, pix.n)[:, :, :3]
    res = _ocr_engine()(img)
    k = 72.0 / dpi
    out = []
    for box, txt, score in res:
        if score < 0.5 or not txt.strip():
            continue
        xs = [p[0] * k for p in box]
        ys = [p[1] * k for p in box]
        out.append(Tok(_fix_ocr(txt.strip()), min(xs), min(ys), max(xs), max(ys)))
    return out


def _fix_ocr(t):
    """خطای رایج OCR در عدد: «o/O» پس از رقم همان صفر است (400oN ← 4000N)."""
    prev = None
    while prev != t:
        prev, t = t, re.sub(r"(?<=\d)[oO]", "0", t)
    return t


def page_tokens(page):
    """(توکن‌ها، روش): لایه متنی اگر معنادار باشد، وگرنه OCR."""
    toks = _tokens_text(page)
    words = sum(len(re.findall(r"[A-Za-z]{3,}", t.text)) for t in toks)
    if words >= 8:
        return toks, "text"
    if ocr_available():
        return _tokens_ocr(page), "ocr"
    return toks, "none"


# ------------------------------------------------------------------ عدد کنار برچسب
def _num(text):
    """عدد تنها در یک توکن («1720»، «1.96 m2»، «4000 N»، «3x1366»)؛ (مقدار، ضریب فاز، واحد)."""
    t = text.strip().replace("，", ",").replace("（", "(").replace("）", ")")
    m = re.fullmatch(r"(\d)\s*[xX×]\s*" + NUM, t)
    if m:
        return float(m.group(2).replace(",", ".")), int(m.group(1)), ""
    m = re.fullmatch(r"[~≈(]?\s*" + NUM + r"\s*\)?\s*(kg|n|kn|m2|m²|mm|m|hz)?\.?", t, re.I)
    if m:
        return float(m.group(1).replace(",", ".")), 1, (m.group(2) or "").lower()
    return None


def _near(label, toks, lo, hi, units, reach=260.0):
    """نزدیک‌ترین توکن عددی در بازه [lo, hi] با یکی از واحدهای units، هم‌خط سمت راست یا زیر برچسب."""
    best = None
    for t in toks:
        if t is label:
            continue
        v = _num(t.text)
        if v is None or not (lo <= v[0] <= hi) or v[2] not in units:
            continue
        h = max(label.h, 4.0)
        if abs(t.cy - label.cy) <= 0.8 * h and t.x0 >= label.x1 - 2:          # هم‌خط، راست
            d = t.x0 - label.x1
        elif t.y0 >= label.y1 - 1 and t.y0 - label.y1 <= 2.5 * h \
                and t.x1 >= label.x0 - 10 and t.x0 <= label.x1:              # زیر
            d = (t.y0 - label.y1) * 2 + abs(t.x0 - label.x0) * 0.5
        else:
            continue
        if d <= reach and (best is None or d < best[0]):
            best = (d, t, v)
    return best


TABLE_LABEL = r"creep|arc\b|distance|diameter|voltage|strength|frequency|current|rated|:\s*$|/\s*(mm|kv|kn|n)\s*$"


def _in_table(t, toks):
    """
    عدد ستون مقدار یک جدول («Creepage distance/mm  7880»، «6190 mm»)، نه اندازه‌گذاری نقشه:
    برچسب جدول در چپ یا واحد در راستش (اندازه‌گذاری نقشه واحد ندارد).
    """
    for u in toks:
        if u is t or abs(u.cy - t.cy) > 0.6 * max(t.h, 4):
            continue
        if 0 <= t.x0 - u.x1 <= 260 and re.search(TABLE_LABEL, u.text, re.I):
            return True
        if -2 <= u.x0 - t.x1 <= 30 and re.fullmatch(r"\s*(mm|kv|kg|n|kn|hz|m2|m²|a|ka)\.?\s*", u.text, re.I):
            return True
    return False


def _dimension(t):
    """اندازه‌گذاری میلی‌متری تنها: «3044»، «3325±50»، «-2300±3.5-»."""
    m = re.fullmatch(r"[-–(]?\s*(\d{4,5})\s*(?:±\s*[\d.]+)?\s*[-–)]?", t.text.strip())
    return float(m.group(1)) if m else None


def _field(key, value, unit, how, toks, confident=True, note=""):
    return {"key": key, "value": value, "unit": unit, "how": how, "confident": confident,
            "note": note, "boxes": [[round(t.x0, 1), round(t.y0, 1), round(t.x1, 1), round(t.y1, 1)]
                                    for t in toks]}


def _labelled(toks, label_re, lo, hi, units, inline_re=None):
    """
    عدد یک برچسب: اول داخل خود توکن برچسب (inline_re، گروه ۱ عدد)، بعد نزدیک‌ترین عدد کنارش.
    خروجی: (مقدار، ضریب فاز، [توکن‌ها]، متن برچسب) یا None
    """
    for t in toks:
        if not re.search(label_re, t.text, re.I):
            continue
        if inline_re:
            m = re.search(inline_re, t.text, re.I)
            if m:
                v = float(m.group(1).replace(",", "."))
                if lo <= v <= hi:
                    return v, 1, [t], t.text
        hit = _near(t, toks, lo, hi, units)
        if hit:
            return hit[2][0], hit[2][1], [t, hit[1]], t.text
    return None


NOT_OUTLINE = r"LAYOUT|GENERAL\s*PLAN|SITE\s*PLAN|KEY\s*PLAN|SINGLE\s*LINE|SCHEMATIC|FOUNDATION\s*PLAN"


def not_outline(text):
    """
    صفحه‌ای که اوت‌لاین یک تجهیز نیست: نقشه جانمایی، شماتیک، کی‌پلن … (عنوانش، یا نام سه نوع تجهیز
    یا بیشتر مثل راهنمای نقشه جانمایی). اوت‌لاین سکسیونر با تیغه زمین دو نوع دارد، نه سه.
    """
    up = text.upper()
    kinds = {tag for tag, pat in TYPE_WORDS if re.search(pat, up)}
    return bool(re.search(NOT_OUTLINE, up)) or len(kinds - {"DS"}) >= 3


def detect_type(text):
    up = text.upper()
    for tag, pat in TYPE_WORDS:
        if re.search(pat, up):
            return tag
    return ""


MODEL = r"^[A-Z]{2,5}\d?\s?-?\d{2,3}(?:[/-][\w.]+)*$"


def _title(toks, tag):
    """عنوان صفحه: عبارت نوع تجهیز + مدل سازنده (IMBD245، HPL245/31B1، CPA 245) + سازنده."""
    pat = dict(TYPE_WORDS).get(tag)
    kind = next((t.text for t in toks if pat and re.search(pat, t.text.upper())), "")
    model = next((t.text for t in toks if re.match(MODEL, t.text.strip()) and t.text not in kind), "")
    maker = next((t.text for t in toks if re.search(r"COMPANY|\bCO\.?$|COMPANY", t.text, re.I)
                  and len(t.text) <= 40), "")
    return " · ".join(x.strip(" :.") for x in (kind[:70], model, maker) if x)


def extract(toks):
    """عددهای بار تجهیز از توکن‌های یک صفحه."""
    fields = {}
    text = "\n".join(t.text for t in toks)

    # --- وزن
    m = None
    for t in toks:
        m = re.search(r"W(?:eight)?\s*(?:\(\s*kg\s*\))?\s*=\s*\(?\s*" + NUM + r"\s*\+\s*" + NUM
                      + r"\s*[x×*·]?\s*L", t.text, re.I)
        if m:
            a, b = float(m.group(1)), float(m.group(2))
            L, used, Lhow = None, [t], ""
            for u in toks:
                mm = re.search(r"L\s*normal\s*=?\s*" + NUM, u.text, re.I)
                if mm:
                    L, Lhow = float(mm.group(1)), "L عادی نقشه"
                else:
                    mm = re.search(r"L\s*=\s*" + NUM + r"\s*to\s*" + NUM, u.text, re.I)
                    if mm:
                        L, Lhow = (float(mm.group(1)) + float(mm.group(2))) / 2, "میانه بازه L نقشه"
                if L:
                    L = L / 1000 if L > 50 else L
                    used.append(u)
                    break
            W = a + b * (L or 0)
            note = (f"W = {a:g} + {b:g}·L وزن کل سه فاز با مکانیزم و میله‌ها؛ "
                    f"{'با ' + Lhow + f' = {L:g} m' if L else 'L در نقشه نبود (صفر گرفته شد)'}؛ "
                    f"وزن یک فاز = W/3 = {W / 3:.0f}")
            fields["We"] = _field("We", round(W / 3), "kg", "فرمول وزن سازنده ÷ ۳", used, False, note)
            break
    if "We" not in fields:
        for lab in (r"total\s*mass", r"^\s*weight\b", r"weight\s*/\s*kg", r"mass\s*incl",
                    r"^\s*mass\s*:?\s*$"):
            hit = _labelled(toks, lab, 5, 60000, ("", "kg"), r"(?:mass|weight)[^0-9]{0,25}" + NUM + r"\s*kg")
            if hit:
                v, per, used, lt = hit
                fields["We"] = _field("We", v, "kg", f"«{lt}»", used,
                                      note="وزن یک فاز" + (f" (جدول: {per} قطب)" if per > 1 else ""))
                break

    # --- سطح بادگیر
    hit = _labelled(toks, r"wind\s*(load)?\s*area", 0.02, 30, ("", "m2", "m²"), r"area[^0-9]{0,30}" + NUM)
    if hit:
        fields["Ae"] = _field("Ae", hit[0], "m²", f"«{hit[3]}»", hit[2])

    # --- بار ترمینال
    rules = [
        (r"\bFR\s*=", 100, 100000, r"FR\s*=\s*" + NUM, 1),
        (r"test\s*load", 100, 100000, r"F\s*=\s*" + NUM, 1),
        (r"permissible\s*force", 100, 100000, r"force\s*is\s*" + NUM, 1),
        (r"permissible\s*pull", 100, 100000, NUM + r"\s*/\s*" + NUM + r"\s*N", 1),
        (r"terminal\s*load\s*static", 100, 100000, r"max\s*" + NUM, 1),
        (r"cantilever\s*strength", 1, 100, None, 1000),
    ]
    for lab, lo, hi, inl, k in rules:
        if lab == r"permissible\s*pull":       # «dynamic / static 5850/2300 N»: عدد استاتیکی
            for t in toks:
                mm = re.search(NUM + r"\s*/\s*" + NUM + r"\s*N\b", t.text)
                if mm and re.search(r"static", text, re.I):
                    fields["F"] = _field("F", float(mm.group(2)), "N", "بار استاتیکی مجاز ترمینال",
                                         [t])
                    break
            if "F" in fields:
                break
            continue
        hit = _labelled(toks, lab, lo, hi, ("", "n", "kn"), inl)
        if hit:
            fields["F"] = _field("F", hit[0] * k, "N", f"«{hit[3]}»", hit[2])
            break

    # --- ارتفاع و مرکز ثقل (mm در نقشه)
    hit = _labelled(toks, r"^\s*(overall\s*)?height\b", 300, 15000, ("", "mm"), r"height\s*:?\s*" + NUM)
    if hit:
        fields["He"] = _field("He", hit[0] / 1000, "m", f"«{hit[3]}»", hit[2])
    else:
        dims = sorted(((v, t) for t in toks if (v := _dimension(t)) and 1000 <= v <= 12000
                       and not _in_table(t, toks)), key=lambda d: -d[0])
        if dims:
            v, t = dims[0]
            f = _field("He", v / 1000, "m", "بزرگ‌ترین اندازه نقشه", [t], False,
                       "اگر سازه سازنده (مثل کلید) در نقشه است، ارتفاع آن کم شود")
            f["options"] = sorted({d[0] / 1000 for d in dims}, reverse=True)[:5]
            fields["He"] = f
    He_mm = fields["He"]["value"] * 1000 if "He" in fields else 15000
    hit = _labelled(toks, r"cent(er|re)\s*of\s*gravity|\bC\.?\s*O\.?\s*G\b", 100, He_mm * 0.9,
                    ("", "mm"), r"gravity\s*:?\s*" + NUM)
    if hit:
        fields["he"] = _field("he", hit[0] / 1000, "m", f"«{hit[3]}»", hit[2], False,
                              "از پای تجهیز؛ با نقشه تطبیق شود")
    return fields


def read_pdf(path, pages=None, max_pages=30):
    """
    هر صفحه: {page, type, title, method, fields, width, height}.
    method: text (لایه متنی) / ocr / none (اسکن و OCR نصب نیست).
    """
    pymupdf = _pymupdf()
    doc = pymupdf.open(path)
    out = []
    for i, page in enumerate(doc):
        if i >= max_pages or (pages and i + 1 not in pages):
            continue
        toks, how = page_tokens(page)
        text = "\n".join(t.text for t in toks)
        if not_outline(text):
            out.append({"page": i + 1, "type": "", "title": "", "method": how, "fields": {},
                        "foreign": True, "width": page.rect.width, "height": page.rect.height})
            continue
        tag = detect_type(text)
        out.append({"page": i + 1, "type": tag, "title": _title(toks, tag),
                    "method": how, "fields": extract(toks) if toks else {},
                    "width": page.rect.width, "height": page.rect.height})
    return out


def render_page(path, page_no, fields=None, dpi=110):
    """PNG صفحه با قاب رنگی دور هر عددی که برداشته شده."""
    pymupdf = _pymupdf()
    doc = pymupdf.open(path)
    page = doc[page_no - 1]
    colors = {"He": (0.85, 0.2, 0.2), "he": (0.9, 0.55, 0.1), "Ae": (0.1, 0.5, 0.85),
              "We": (0.15, 0.6, 0.25), "F": (0.55, 0.25, 0.75)}
    rot = page.rotation_matrix
    for f in (fields or {}).values():
        for b in f.get("boxes", []):
            r = pymupdf.Rect(*b) * ~rot if page.rotation else pymupdf.Rect(*b)
            r = r + (-2, -2, 2, 2)
            page.draw_rect(r, color=colors.get(f["key"], (0.8, 0.2, 0.2)), width=1.6)
    return page.get_pixmap(dpi=dpi).tobytes("png")


def compare(fields, eq):
    """اختلاف با کاتالوگ: {key: (کاتالوگ، اوت‌لاین، اختلاف نسبی)}."""
    out = {}
    for k in ("He", "he", "Ae", "We"):
        if k in fields and eq is not None:
            cat = getattr(eq, k, None)
            v = fields[k]["value"]
            if cat:
                out[k] = {"catalog": cat, "outline": v, "diff": (v - cat) / cat}
    return out


def overrides_ok(ov):
    """
    اعتبار عددهایی که از فرم می‌آید: {نوع: {He, he, Ae, We, n_pedestal, pedestal_spacing}} —
    عددهای تأییدشده اوت‌لاین و ستون‌های سازه‌ای که مهندس برای این پروژه تعیین کرده.
    """
    clean = {}
    for tag, vals in (ov or {}).items():
        d = {}
        for k in ("He", "he", "Ae", "We"):
            v = (vals or {}).get(k)
            if v in (None, ""):
                continue
            v = float(v)
            if not math.isfinite(v) or v <= 0:
                raise ValueError(f"{tag}: مقدار {k} از اوت‌لاین باید مثبت باشد.")
            d[k] = v
        n = (vals or {}).get("n_pedestal")
        if n not in (None, ""):
            n = int(float(n))
            if not 1 <= n <= 4:
                raise ValueError(f"{tag}: تعداد ستون سازه باید ۱ تا ۴ باشد.")
            d["n_pedestal"] = n
        sp = (vals or {}).get("pedestal_spacing")
        if sp not in (None, ""):
            sp = float(sp)
            if not 0.5 <= sp <= 5:
                raise ValueError(f"{tag}: فاصله ستون‌های سازه باید ۰٫۵ تا ۵ متر باشد.")
            d["pedestal_spacing"] = sp
        if d:
            clean[str(tag)] = d
    return clean
