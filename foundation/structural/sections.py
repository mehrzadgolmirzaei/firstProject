"""
مقاطع فولادی — همه خواص از ابعاد، با همان روابطی که SAP2000 برای مقاطع
پارامتری به کار می‌برد (بدون گردی گوشه). آزمون‌ها این اعداد را با جدول
FRAME SECTION PROPERTIES مدل‌های دفتر مقایسه می‌کنند.

محورهای مقطع مثل SAP:
    ۲  در امتداد عمق t3 (برای ناودانی: امتداد جان)
    ۳  در امتداد پهنا t2
    I33 لنگر دوم حول محور ۳ (خمش در صفحه ۱-۲)، I22 حول محور ۲.
نبشی: SAP تحلیل را با I33 و I22 هندسی انجام می‌دهد (حاصل‌ضرب اینرسی را نادیده
می‌گیرد)؛ برای کمانش، شعاع ژیراسیون حداقل حول محور اصلی ضعیف (rz) هم حساب می‌شود.
"""
import math
from dataclasses import dataclass, field

STEEL = {"E": 2.0389019158e10, "G": 7.841930445e9, "gamma": 7849.0476,   # kgf/m²، kgf/m³
         "Fy": 2.4e7, "Fu": 3.7e7}                                      # St37: 2400 و 3700 kg/cm²


def _rects_props(rects):
    """خواص مستطیل‌ها [(y0, z0, y1, z1)] — y در امتداد محور ۲، z در امتداد محور ۳."""
    A = sum((y1 - y0) * (z1 - z0) for y0, z0, y1, z1 in rects)
    cy = sum((y1 - y0) * (z1 - z0) * (y0 + y1) / 2 for y0, z0, y1, z1 in rects) / A
    cz = sum((y1 - y0) * (z1 - z0) * (z0 + z1) / 2 for y0, z0, y1, z1 in rects) / A
    Iyy = Izz = Iyz = 0.0          # Iyy: حول محوری موازی ۳ (خمش با بازوی y) = I33
    for y0, z0, y1, z1 in rects:
        h, b = y1 - y0, z1 - z0
        a = h * b
        dy, dz = (y0 + y1) / 2 - cy, (z0 + z1) / 2 - cz
        Iyy += b * h ** 3 / 12 + a * dy ** 2
        Izz += h * b ** 3 / 12 + a * dz ** 2
        Iyz += a * dy * dz
    return A, cy, cz, Iyy, Izz, Iyz


@dataclass
class Section:
    name: str
    shape: str             # angle | channel | 2channel
    t3: float              # عمق (m)
    t2: float              # پهنا (m)
    tf: float
    tw: float
    dis: float = 0.0       # فاصله پشت‌به‌پشت دوبل ناودانی
    # خواص (در __post_init__)
    A: float = field(init=False)
    J: float = field(init=False)
    I33: float = field(init=False)
    I22: float = field(init=False)
    I23: float = field(init=False)
    AS2: float = field(init=False)
    AS3: float = field(init=False)
    S33: float = field(init=False)
    S22: float = field(init=False)
    r33: float = field(init=False)
    r22: float = field(init=False)
    rz: float = field(init=False)          # حداقل شعاع ژیراسیون (محور اصلی ضعیف)
    c2: float = field(init=False)          # فاصله مرکز سطح از پشت/پاشنه در امتداد ۲
    c3: float = field(init=False)          # و در امتداد ۳

    def __post_init__(self):
        d, b, tf, tw = self.t3, self.t2, self.tf, self.tw
        if self.shape == "angle":
            # پاشنه در مبدأ؛ بال عمودی (امتداد ۲) با ضخامت tw، بال افقی (امتداد ۳) با ضخامت tf
            rects = [(0, 0, d, tw), (0, tw, tf, b)]
            A, cy, cz, I33, I22, I23 = _rects_props(rects)
            J = (d * tw ** 3 * (1 - 0.63 * tw / d) + (b - tw) * tf ** 3
                 - 0.105 * tf ** 4) / 3
            AS2, AS3 = d * tw, b * tf
            S33 = I33 / max(cy, d - cy)
            S22 = I22 / max(cz, b - cz)
            Imin = (I33 + I22) / 2 - math.hypot((I33 - I22) / 2, I23)
            self.c2, self.c3 = cy, cz
        elif self.shape in ("channel", "2channel"):
            # جان در امتداد ۲ با پشت در z=0، بال‌ها رو به +۳
            h = d - 2 * tf
            rects = [(0, 0, tf, b), (d - tf, 0, d, b), (tf, 0, d - tf, tw)]
            A, cy, cz, I33, I22, I23 = _rects_props(rects)
            J = (2 * b * tf ** 3 * (1 - 0.63 * tf / b) + h * tw ** 3 * (1 - 0.63 * tw / h)) / 3
            AS2, AS3 = d * tw, 2 * b * tf
            S22 = I22 / max(cz, b - cz)
            if self.shape == "2channel":
                g = self.dis / 2
                I22 = 2 * (I22 + A * (cz + g) ** 2)
                A, J, AS2, AS3, I33 = 2 * A, 2 * J, 2 * AS2, 2 * AS3, 2 * I33
                S22 = I22 / (b + g)            # دورترین تار: لبه بال، b + فاصله/۲
                cz = 0.0
            S33 = I33 / (d / 2)
            I23 = 0.0
            Imin = min(I33, I22)
            self.c2, self.c3 = d / 2, cz
        else:
            raise ValueError(f"مقطع ناشناخته: {self.shape}")
        self.A, self.J, self.I33, self.I22, self.I23 = A, J, I33, I22, I23
        self.AS2, self.AS3, self.S33, self.S22 = AS2, AS3, S33, S22
        self.r33, self.r22 = math.sqrt(I33 / A), math.sqrt(I22 / A)
        self.rz = math.sqrt(Imin / A)

    @property
    def weight(self):
        """وزن واحد طول (kg/m)"""
        return self.A * STEEL["gamma"]

    @property
    def kind(self):
        return self.shape


def angle(b, t, name=None):
    return Section(name or f"L{b * 1000:.0f}X{t * 1000:.0f}", "angle", b, b, t, t)


def channel(h, b, tw, tf, name=None):
    return Section(name or f"UNP{h * 1000:.0f}", "channel", h, b, tf, tw)


def double_channel(h, b, tw, tf, gap=0.01, name=None):
    # t2 کل پهنای دوبل است (مثل SAP): دو بال + فاصله
    s = Section(name or f"2UNP{h * 1000:.0f}", "2channel", h, b, tf, tw, gap)
    s.t2_total = 2 * b + gap
    return s


# کاتالوگ — نبشی بال مساوی (DIN EN 10056) و ناودانی (DIN 1026)، به ترتیب وزن
ANGLES = [angle(b / 1000, t / 1000) for b, t in (
    (30, 3), (40, 4), (45, 5), (50, 5), (60, 6), (70, 7), (80, 8), (90, 9),
    (100, 10), (120, 12))]
CHANNELS = [channel(h / 1000, b / 1000, tw / 1000, tf / 1000) for h, b, tw, tf in (
    (80, 45, 6, 8), (100, 50, 6, 8.5), (120, 55, 7, 9), (140, 60, 7, 10),
    (160, 65, 7.5, 10.5), (180, 70, 8, 11), (200, 75, 8.5, 11.5))]
CATALOG = {s.name: s for s in ANGLES + CHANNELS}


def from_sap(row):
    """مقطع از سطر جدول FRAME SECTION PROPERTIES 01 فایل s2k."""
    shape = {"Angle": "angle", "Channel": "channel", "Double Channel": "2channel"}.get(
        row.get("Shape"))
    if shape is None:
        raise ValueError(f"شکل مقطع {row.get('Shape')} پشتیبانی نمی‌شود ({row['SectionName']})")
    t2 = row["t2"]
    if shape == "2channel":
        dis = row.get("dis", 0.0) or 0.0
        return Section(row["SectionName"], shape, row["t3"], (t2 - dis) / 2,
                       row["tf"], row["tw"], dis)
    return Section(row["SectionName"], shape, row["t3"], t2, row["tf"], row["tw"])
