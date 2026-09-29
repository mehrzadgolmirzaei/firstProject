"""
داده تجهیزات و ساختگاه.

فعلاً به صورت فایل نگه داشته می‌شود؛ ساختار دیکشنری‌ها عیناً همان ستون‌هایی است
که بعداً جدول equipment_catalog دیتابیس خواهد داشت، تا انتقال بدون بازنویسی باشد.

مقادیر He, he, Ae, Ce, We و کشش هادی از نقشه اوت‌لاین سازنده می‌آید.
مقادیر anchor_* از نقشه فونداسیون اجراشده یا اوت‌لاین سازنده استخراج می‌شود.
"""
from dataclasses import dataclass, field


@dataclass
class Equipment:
    tag: str                       # LA, CB, CT, CVT, PI, DSE, DS, DSROW
    title: str
    # --- تجهیز ---
    He: float                      # ارتفاع تجهیز (m)
    Ae: float                      # سطح دید تجهیز (m²)
    We: float                      # وزن تجهیز (kg)
    he: float = None               # ارتفاع مرکز ثقل تجهیز؛ پیش‌فرض He/2
    Ce: float = 0.5                # ضریب درگ تجهیز
    npol: int = 1                  # تعداد پایه
    # --- استراکچر ---
    Hs: float = 0.0                # ارتفاع استراکچر (m)
    As: float = 0.0                # سطح دید استراکچر (m²)
    Ws: float = 0.0                # وزن استراکچر (kg)
    hs: float = None               # مرکز ثقل استراکچر؛ پیش‌فرض Hs/2
    Cs: float = 2.05               # ضریب درگ استراکچر
    # --- هادی ---
    Wc: float = 50.0               # وزن هادی (kg)
    Fc: float = 0.0                # کشش افقی هادی، حالت عادی (kg)
    Fc_sc: float = None            # کشش در اتصال کوتاه؛ پیش‌فرض = Fc
    conductor_points: list = field(default_factory=list)   # ارتفاع نقاط اتصال از پای استراکچر
    # --- بار مانور تجهیز ---
    op_vertical: float = 0.0
    op_horizontal: float = 0.0
    op_moment: float = 0.0
    # --- مشخصات اتصال ---
    n_pedestal: int = 1            # تعداد ستون روی پی
    pedestal_spacing: float = 0.0  # فاصله محور ستون‌ها (m)؛ صفر یعنی B/2
    anchor_n: int = 4              # تعداد میل مهار در هر ستون
    anchor_dia: int = 20           # قطر میل مهار (mm)
    anchor_gauge: float = 450      # فاصله میل مهارها (mm)
    anchor_embed: float = 600      # طول مدفون (mm)
    base_plate: float = 0          # ضلع صفحه کف (mm)؛ صفر یعنی نامشخص
    source: str = ""               # مرجع داده — برای Audit
    # فیلدهایی که باید هر پروژه از اوت‌لاین سازنده خوانده و دستی وارد شوند.
    # تا پر نشوند محاسبه اجرا نمی‌شود، تا کسی سهواً با عدد پیش‌فرض نقشه نگیرد.
    requires_outline: list = field(default_factory=list)

    def __post_init__(self):
        if self.he is None:
            self.he = self.He / 2
        if self.hs is None:
            self.hs = self.Hs / 2
        if self.Fc_sc is None:
            self.Fc_sc = self.Fc
        if not self.conductor_points:
            self.conductor_points = [self.He]


# ------------------------------------------------------------------
# پروژه کامی‌آباد — استخراج‌شده از EQUIPMENT CALCULATION KAMI ABAD A2
#
# گِیج میل مهار: برای همه تجهیزات ۴۵۰ میلی‌متر استاندارد است (از نقشه
# 06-4LA_C استخراج و توسط دفتر فنی تأیید شد).
#
# استثنا — کلید قدرت (CB): سازه‌اش را خود سازنده می‌دهد، پس ابعاد و وزن
# استراکچر و تجهیز، نقاط اتصال هادی، گِیج میل مهار و صفحه کف هر پروژه از
# اوت‌لاین سازنده خوانده و دستی وارد می‌شوند. مقادیر زیر برای CB فقط
# نمونه‌ی پروژه کامی‌آباد است و به عنوان پیش‌فرض به کار نمی‌رود.
# ------------------------------------------------------------------
CATALOG = {
    "LA": Equipment("LA", "Lightning Arrester", He=2.205, he=1.103, Ae=0.77, We=227,
                    Hs=3.55, As=0.70, Ws=250, Fc=230, Fc_sc=585,
                    anchor_gauge=450, anchor_n=4, anchor_dia=20, base_plate=600,
                    source="KAMI ABAD A2 / DWG 06-4LA_C"),

    "CB": Equipment("CB", "Circuit Breaker", He=5.258, he=2.629, Ae=1.90, We=1266,
                    Hs=2.00, As=1.90, Ws=100, Fc=175, Fc_sc=125,
                    conductor_points=[3.11, 5.13], op_vertical=3250, op_horizontal=600,
                    anchor_gauge=0, base_plate=0,
                    source="KAMI ABAD A2 — سازه از سازنده، اعداد نمونه",
                    requires_outline=["He", "he", "Ae", "We", "Hs", "As", "Ws",
                                      "anchor_gauge", "base_plate",
                                      "conductor_points", "op_vertical", "op_horizontal"]),

    "CT": Equipment("CT", "Current Transformer", He=3.375, he=1.56, Ae=1.96, We=1720,
                    Hs=2.00, As=0.70, Ws=180, Fc=400, Fc_sc=560,
                    source="KAMI ABAD A2"),

    "CVT": Equipment("CVT", "Capacitive Voltage Transformer", He=3.045, he=1.288, Ae=1.00, We=495,
                     Hs=2.00, As=0.70, Ws=180, Fc=400, Fc_sc=560,
                     source="KAMI ABAD A2"),

    "PI": Equipment("PI", "Post Insulator", He=2.304, he=1.152, Ae=0.71, We=220,
                    Hs=2.90, As=0.60, Ws=220, Fc=1250,
                    source="KAMI ABAD A2"),

    "DSE": Equipment("DSE", "Disconnector with Earthing Switch", He=3.044, he=0.92, Ae=1.52, We=370,
                     Hs=2.35, As=1.00, Ws=450, Fc=400,
                     n_pedestal=2, source="KAMI ABAD A2"),

    "DS": Equipment("DS", "Disconnector", He=3.044, he=0.815, Ae=1.52, We=350,
                    Hs=2.35, As=1.00, Ws=450, Fc=400,
                    n_pedestal=2, source="KAMI ABAD A2"),

    "DSROW": Equipment("DSROW", "Disconnector - Row Mounted", He=3.044, he=0.815, Ae=1.52, We=300,
                       Hs=2.35, As=1.00, Ws=350, Fc=338,
                       n_pedestal=2, source="KAMI ABAD A2"),
}


# ------------------------------------------------------------------
# پست ۶۳/۲۰ کیمیا — از دفترچه VP-63POST-CAL-0004 (7390-SB-KIM-CV-CAL-104)
#
# در پست ۶۳ به خاطر کمبود فضا، پی‌ها مشترک و مستطیلی‌اند: هر تجهیز با
# npol=3 روی یک سازه با دو (یا سه) ستون بتنی در یک ردیف، و گاهی دو تجهیز
# (LA+CVT و PI+CVT) روی یک پی. ابعاد پی را مهندس انتخاب کرده است.
# ------------------------------------------------------------------
_K63 = dict(Ce=0.5, Cs=2.05, Wc=50, anchor_n=4, anchor_dia=20, anchor_gauge=370,
            source="KIMIA 63kV — VP-63POST-CAL-0004")

CATALOG_KIMIA63 = {
    "LA63": Equipment("LA63", "63kV Lightning Arrester", He=1.044, he=0.522, Ae=0.20, We=20,
                      Hs=2.85, hs=1.43, As=1.40, Ws=400, Fc=100, Fc_sc=200, npol=3,
                      n_pedestal=2, pedestal_spacing=1.70, **_K63),
    "CB63": Equipment("CB63", "63kV Circuit Breaker", He=1.92, he=0.96, Ae=0.45, We=261,
                      Hs=2.22, hs=1.11, As=1.40, Ws=210, Fc=125, Fc_sc=125, npol=3,
                      op_vertical=1100, op_horizontal=1100, op_moment=3200,
                      n_pedestal=2, pedestal_spacing=1.50,
                      **{**_K63, "anchor_dia": 25, "anchor_gauge": 400}),
    "CT63": Equipment("CT63", "63kV Current Transformer", He=1.55, he=0.785, Ae=0.65, We=395,
                      Hs=2.00, hs=1.00, As=1.30, Ws=400, Fc=250, Fc_sc=250, npol=3,
                      n_pedestal=2, pedestal_spacing=1.70, **_K63),
    "DSE63": Equipment("DSE63", "63kV Disconnector with Earthing Switch", He=1.33, he=0.665,
                       Ae=0.30, We=240, Hs=2.50, hs=1.25, As=1.40, Ws=560, Fc=220, Fc_sc=220,
                       npol=3, n_pedestal=2, pedestal_spacing=1.70, **_K63),
    "DS2_63": Equipment("DS2_63", "63kV Disconnector (type 2)", He=1.41, he=0.705, Ae=0.30,
                        We=240, Hs=4.10, hs=2.05, As=1.90, Ws=600, Fc=220, Fc_sc=220, npol=3,
                        n_pedestal=2, pedestal_spacing=1.70, **_K63),
    "CVT63": Equipment("CVT63", "63kV Capacitive Voltage Transformer", He=1.645, he=0.585,
                       Ae=0.60, We=320, Hs=2.00, hs=1.00, As=1.17, Ws=350, Fc=250, Fc_sc=250,
                       npol=3, n_pedestal=3, pedestal_spacing=1.50, **_K63),
    "CVT63_1": Equipment("CVT63_1", "63kV CVT — single phase", He=1.645, he=0.585, Ae=0.60,
                         We=320, Hs=2.00, hs=1.00, As=1.17, Ws=150, Fc=250, Fc_sc=250, npol=1,
                         n_pedestal=1, **_K63),
    "PI63": Equipment("PI63", "63kV Post Insulator (C8)", He=0.77, he=0.385, Ae=0.30, We=36,
                      Hs=4.58, hs=2.29, As=2.20, Ws=620, Fc=320, Fc_sc=640, npol=3,
                      n_pedestal=2, pedestal_spacing=1.70, **_K63),
}


# ------------------------------------------------------------------
# دسته‌بندی برای کاربر: سطح ولتاژ پست ← نوع تجهیز.
# نام پروژه‌ها فقط در «source» هر تجهیز (برای Audit) می‌ماند.
# ------------------------------------------------------------------
ALL_EQUIPMENT = {**CATALOG, **CATALOG_KIMIA63}

EQUIPMENT_TYPES = {                 # نوع ← نام فارسی
    "LA": "برق‌گیر (LA)",
    "CB": "کلید قدرت (CB)",
    "CT": "ترانس جریان (CT)",
    "CVT": "ترانس ولتاژ خازنی (CVT)",
    "CVT1": "ترانس ولتاژ خازنی تک‌فاز (CVT)",
    "PI": "مقره اتکایی (PI)",
    "DSE": "سکسیونر با تیغه زمین (DS/DSE)",
    "DS": "سکسیونر (DS)",
    "DSROW": "سکسیونر ردیفی (DS)",
    "DS2": "سکسیونر نوع ۲ (DS2)",
}

# سطح ولتاژ ← {نوع: کلید کاتالوگ}. پست ۶۳ پی مشترک مستطیلی دارد، ۲۳۰/۴۰۰ پی منفرد.
VOLTAGE_LEVELS = {
    "63": {"title": "پست ۶۳ کیلوولت", "pad": "combined",
           "types": {"LA": "LA63", "CB": "CB63", "CT": "CT63", "CVT": "CVT63",
                     "CVT1": "CVT63_1", "PI": "PI63", "DSE": "DSE63", "DS2": "DS2_63"}},
    "230": {"title": "پست ۲۳۰ کیلوولت", "pad": "single",
            "types": {t: t for t in ("LA", "CB", "CT", "CVT", "PI", "DSE", "DS", "DSROW")}},
    "400": {"title": "پست ۴۰۰ کیلوولت", "pad": "single",
            "types": {t: t for t in ("LA", "CB", "CT", "CVT", "PI", "DSE", "DS", "DSROW")}},
}


def equipment_type(key):
    """کلید کاتالوگ ← نوع تجهیز (LA63 ← LA)."""
    for lvl in VOLTAGE_LEVELS.values():
        for t, k in lvl["types"].items():
            if k == key:
                return t
    return key


def with_structure_height(eq, Hs):
    """
    همان تجهیز با ارتفاع استراکچر دیگر (مثلاً از نقشه جانمایی). مرکز ثقل، وزن و سطح بادگیر
    استراکچر به نسبت ارتفاع (تقریب مرتبه اول)؛ با «وزن و سطح بادگیر از سازه طراحی‌شده» مقدار
    واقعی سازه جای این‌ها می‌نشیند.
    """
    import dataclasses
    if not Hs or not eq.Hs or abs(Hs - eq.Hs) < 1e-9:
        return eq
    k = Hs / eq.Hs
    return dataclasses.replace(eq, Hs=round(Hs, 3), hs=round(eq.hs * k, 3),
                               Ws=round(eq.Ws * k, 1), As=round(eq.As * k, 3))


# ------------------------------------------------------------------
# عددهای تأییدشده از اوت‌لاین سازنده همین پروژه، به جای کاتالوگ.
# کاتالوگ یک دیکشنری مشترک است که bay و layoutplan هم می‌خوانند؛ جایگزینی موقت زیر قفل
# انجام می‌شود تا دو درخواست هم‌زمان عدد یکدیگر را نبینند.
# ------------------------------------------------------------------
import threading as _threading
from contextlib import contextmanager as _contextmanager

_OUTLINE_LOCK = _threading.RLock()


def outline_keys(voltage, tag):
    """کلیدهای کاتالوگ یک نوع تجهیز در یک سطح ولتاژ (CVT ← CVT63 و CVT63_1)."""
    types = VOLTAGE_LEVELS.get(str(voltage), {}).get("types", {})
    return [k for t, k in types.items() if t == tag or t.rstrip("12") == tag]


@_contextmanager
def outline_values(voltage, overrides):
    """
    در طول بلوک، He/he/Ae/We هر نوع تجهیز از overrides ({نوع: {He, he, Ae, We}}) خوانده می‌شود.
    ارتفاع مرکز ثقل اگر داده نشده باشد به نسبت ارتفاع تجهیز تغییر می‌کند.
    """
    import dataclasses
    if not overrides:
        yield {}
        return
    with _OUTLINE_LOCK:
        saved = {}
        try:
            for tag, vals in overrides.items():
                for key in outline_keys(voltage, tag):
                    eq = ALL_EQUIPMENT[key]
                    v = {k: vals[k] for k in ("He", "he", "Ae", "We") if vals.get(k)}
                    if "He" in v and "he" not in v and eq.He:
                        v["he"] = round(eq.he * v["He"] / eq.He, 3)
                    if "He" in v and eq.conductor_points == [eq.He]:
                        v["conductor_points"] = [v["He"]]
                    saved[key] = eq
                    ALL_EQUIPMENT[key] = dataclasses.replace(
                        eq, **v, source=f"{eq.source} + اوت‌لاین پروژه")
                    for cat in (CATALOG, CATALOG_KIMIA63):
                        if key in cat:
                            cat[key] = ALL_EQUIPMENT[key]
            yield {k: ALL_EQUIPMENT[k] for k in saved}
        finally:
            for key, eq in saved.items():
                ALL_EQUIPMENT[key] = eq
                for cat in (CATALOG, CATALOG_KIMIA63):
                    if key in cat:
                        cat[key] = eq
