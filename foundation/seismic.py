"""
ضریب زلزله — استاندارد ۲۸۰۰ ایران

ویرایش ۵ (فروردین ۱۴۰۵):
    SS, S1  از نقشه‌های پیوست (۱) بر حسب مختصات جغرافیایی ساختگاه
    Fs, F1  از جداول ۲-۱ و ۲-۲ بر حسب نوع زمین، با درون‌یابی خطی
    S_MS = Fs·SS      S_M1 = F1·S1
    S_DS = ⅔·S_MS     S_D1 = ⅔·S_M1
    افقی : C_h = 0.3·S_DS·Ie      (رابطه ۵-۴، سازه صلب غیرمشابه ساختمان)
           C_h = S_DS·Ie/Ru       (رابطه ۳-۱، بازه شتاب ثابت طیف)
    حداقل: C_min = max(0.044·S_DS·Ie , 0.01) و اگر S1 ≥ 0.6 شرط 0.5·S1·Ie/Ru
    قائم : C_v = 0.2·S_DS         (رابطه ۳-۱۵)

ویرایش ۴ فقط برای بازتولید گزارش‌های تأییدشده قبلی نگه داشته شده است.
"""
from dataclasses import dataclass, field

# جدول ۲-۱ — ضریب ساختگاه Fs بر حسب SS
FS_TABLE = {
    "I":   {0.50: 1.0, 0.75: 1.0, 1.00: 1.0, 1.25: 1.0, 1.50: 1.0},
    "II":  {0.50: 1.2, 0.75: 1.2, 1.00: 1.1, 1.25: 1.0, 1.50: 1.0},
    "III": {0.50: 1.3, 0.75: 1.2, 1.00: 1.1, 1.25: 1.0, 1.50: 1.0},
    "IV":  {0.50: 1.6, 0.75: 1.3, 1.00: 1.3, 1.25: 1.1, 1.50: 1.1},
    "V":   {0.50: 1.6, 0.75: 1.4, 1.00: 1.4, 1.25: 1.2, 1.50: 1.2},
}

# جدول ۲-۲ — ضریب ساختگاه F1 بر حسب S1
F1_TABLE = {
    "I":   {0.20: 1.0, 0.30: 1.0, 0.40: 1.0, 0.50: 1.0, 0.60: 1.0},
    "II":  {0.20: 1.5, 0.30: 1.3, 0.40: 1.3, 0.50: 1.3, 0.60: 1.3},
    "III": {0.20: 2.2, 0.30: 2.1, 0.40: 2.1, 0.50: 2.1, 0.60: 2.1},
    "IV":  {0.20: 3.3, 0.30: 3.3, 0.40: 3.2, 0.50: 2.8, 0.60: 2.8},
    "V":   {0.20: 2.2, 0.30: 2.1, 0.40: 2.1, 0.50: 2.1, 0.60: 2.1},
}

# جدول ۱-۱ — ضریب اهمیت. پست برق در گروه ۱ است.
IMPORTANCE = {1: 1.4, 2: 1.2, 3: 1.0, 4: 0.8}


def interpolate(table: dict, soil: str, x: float) -> float:
    """درون‌یابی خطی بین ستون‌های جدول؛ خارج از بازه، مقدار حدی."""
    row = table[soil]
    keys = sorted(row)
    if x <= keys[0]:
        return row[keys[0]]
    if x >= keys[-1]:
        return row[keys[-1]]
    for a, b in zip(keys, keys[1:]):
        if a <= x <= b:
            t = (x - a) / (b - a)
            return row[a] + t * (row[b] - row[a])
    return row[keys[0]]


GRAVITY = 981.0          # cm/s²
RIGID_LIMIT = 0.06       # ثانیه — بند ۵-۵-۱


def period(w_effective, k_lateral):
    """
    زمان تناوب پایه تجهیز به صورت یک درجه آزادی:
        T = 2π · √( W / (g · k) )

    w_effective : وزن مؤثر لرزه‌ای (kg) — وزن تجهیز به‌علاوه یک‌سوم وزن استراکچر
    k_lateral   : سختی جانبی استراکچر (kg/cm)

    اگر سختی در دست نباشد None برمی‌گردد؛ در آن صورت انتخاب روش صلب یا
    استاتیکی تصمیم مهندس است و سیستم پیشنهادی نمی‌دهد.
    """
    if not k_lateral or k_lateral <= 0 or w_effective <= 0:
        return None, None, None
    import math
    t = 2 * math.pi * math.sqrt(w_effective / (GRAVITY * k_lateral))
    rigid = t <= RIGID_LIMIT
    note = (f"T = 2π·√({w_effective:.0f} / (981 × {k_lateral:.0f})) = {t:.4f} s"
            f"  →  {'صلب' if rigid else 'غیرصلب'}  (حد بند ۵-۵-۱: {RIGID_LIMIT} s)")
    return t, ("rigid" if rigid else "static"), note


@dataclass
class SeismicResult:
    ch: float
    cv: float
    steps: list = field(default_factory=list)   # (عنوان، فرمول، جایگذاری عددی)
    edition: int = 5
    period: float = None                        # زمان تناوب، اگر سختی داده شده باشد
    period_note: str = ""


@dataclass
class Site2800v5:
    """پارامترهای لرزه‌ای یک ساختگاه — یک‌بار برای هر پست ثبت و ذخیره می‌شود."""
    ss: float                   # شتاب طیفی ۰٫۲ ثانیه، از نقشه پیوست ۱
    s1: float                   # شتاب طیفی ۱ ثانیه
    soil: str = "III"           # نوع زمین ساختگاه I تا V
    ie: float = 1.4             # ضریب اهمیت — گروه ۱
    ru: float = 2.0             # ضریب رفتار
    method: str = "rigid"       # rigid: رابطه ۵-۴ | static: رابطه ۳-۱
    map_date: str = ""          # تاریخ نقشه مرجع، برای Audit

    def compute(self) -> SeismicResult:
        fs = interpolate(FS_TABLE, self.soil, self.ss)
        f1 = interpolate(F1_TABLE, self.soil, self.s1)
        sms, sm1 = fs * self.ss, f1 * self.s1
        sds, sd1 = 2 / 3 * sms, 2 / 3 * sm1

        if self.method == "rigid":
            ch_raw = 0.3 * sds * self.ie
            formula = "C_h = 0.30 · S_DS · Ie   (رابطه ۵-۴)"
            subst = f"0.30 × {sds:.3f} × {self.ie:.2f} = {ch_raw:.3f}"
        else:
            ch_raw = sds * self.ie / self.ru
            formula = "C_h = S_DS · Ie / Ru   (رابطه ۳-۱)"
            subst = f"{sds:.3f} × {self.ie:.2f} / {self.ru:.1f} = {ch_raw:.3f}"

        cmin = max(0.044 * sds * self.ie, 0.01)
        if self.s1 >= 0.6:
            cmin = max(cmin, 0.5 * self.s1 * self.ie / self.ru)
        ch = max(ch_raw, cmin)
        cv = 0.2 * sds

        steps = [
            ("ضریب ساختگاه", "Fs , F1 — جداول ۲-۱ و ۲-۲",
             f"زمین {self.soil}: Fs = {fs:.2f} , F1 = {f1:.2f}"),
            ("شتاب روی زمین", "S_MS = Fs·SS   ,   S_M1 = F1·S1",
             f"{fs:.2f}×{self.ss:.2f} = {sms:.3f}  ,  {f1:.2f}×{self.s1:.2f} = {sm1:.3f}"),
            ("شتاب طرح", "S_DS = ⅔·S_MS   ,   S_D1 = ⅔·S_M1",
             f"{sds:.3f}  ,  {sd1:.3f}"),
            ("ضریب افقی", formula, subst),
            ("حداقل برش پایه", "C_min = max(0.044·S_DS·Ie , 0.01)",
             f"{cmin:.3f} → {'حاکم است' if ch_raw < cmin else 'حاکم نیست'}"),
            ("افقی نهایی", "C_h = max(C_h , C_min)", f"{ch:.3f}"),
            ("ضریب قائم", "C_v = 0.20 · S_DS   (رابطه ۳-۱۵)",
             f"0.20 × {sds:.3f} = {cv:.3f}"),
        ]
        return SeismicResult(ch=ch, cv=cv, steps=steps, edition=5)


@dataclass
class Site2800v4:
    """ویرایش ۴ — فقط برای بازتولید محاسبات قدیمی."""
    a: float = 0.30
    b: float = 2.75
    i: float = 1.4
    r: float = 2.0

    def compute(self) -> SeismicResult:
        ch = self.b * self.a * self.i / self.r
        cv = 0.7 * self.a * self.i
        return SeismicResult(ch=ch, cv=cv, edition=4, steps=[
            ("افقی", "C_h = B·A·I/R", f"{self.b}×{self.a}×{self.i}/{self.r} = {ch:.3f}"),
            ("قائم", "C_v = 0.7·A·I", f"0.7×{self.a}×{self.i} = {cv:.3f}"),
        ])
