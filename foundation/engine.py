"""
موتور محاسبه فونداسیون پایه تجهیزات پست.

منطق دقیقاً بازنویسی شیت‌های EQUIPMENT CALCULATION است و با هر هشت شیت
پروژه کامی‌آباد تطبیق داده شده (اختلاف نیروها کمتر از ۱ کیلوگرم).

تفاوت مهم با اکسل: در اکسل ابعاد ورودی است و شیت فقط کنترل می‌کند.
اینجا find_dimensions کوچک‌ترین ابعادی را پیدا می‌کند که همه کنترل‌ها را پاس کند.

واحدها: kg و m ، تنش خاک kg/cm².
"""
from dataclasses import dataclass, field
from equipment import Equipment


def from_config(cfg):
    """ساخت SoilAndMaterials و WindParams از روی ProjectConfig."""
    m, so, w = cfg.materials, cfg.soil, cfg.wind
    soil = SoilAndMaterials(q_base=so.q_base, q_factor=so.q_factor,
                            gamma_c=m.gamma_c, gamma_s=m.gamma_s,
                            friction=so.friction, soil_cover=so.soil_cover,
                            fc=m.fc, fy=m.fy, cover=m.cover, lean=m.lean)
    wind = WindParams(v_normal=w.v_normal, v_high=w.v_high, sc_ratio=w.sc_ratio)
    return soil, wind


@dataclass
class SoilAndMaterials:
    q_base: float = 2.83       # تنش مجاز پایه از گزارش ژئوتکنیک (kg/cm²)
    q_factor: float = 1.33     # ضریب افزایش برای بارهای موقت
    gamma_c: float = 2500.0    # وزن مخصوص بتن (kg/m³)
    gamma_s: float = 1900.0    # وزن مخصوص خاک (kg/m³)
    friction: float = 0.466    # ضریب اصطکاک کف پی
    soil_cover: float = 0.15   # ضخامت خاک روی پی که در وزن حساب نمی‌شود
    fc: int = 250              # kg/cm²
    fy: int = 4000             # kg/cm²
    cover: int = 50            # پوشش بتن (mm)
    lean: int = 100            # ضخامت بتن مگر (mm)
    sf_overturn: float = 1.75
    sf_sliding: float = 1.20

    @property
    def q_all(self) -> float:
        return self.q_base * self.q_factor


@dataclass
class WindParams:
    v_normal: float = 25.0     # m/s
    v_high: float = 40.0       # m/s
    sc_ratio: float = 0.70     # نسبت سرعت باد همزمان با اتصال کوتاه

    @property
    def q_normal(self):  return 0.0625 * self.v_normal ** 2      # 39.0625 kg/m²

    @property
    def q_high(self):    return 0.0625 * self.v_high ** 2        # 100 kg/m²

    @property
    def q_sc(self):      return self.q_high * self.sc_ratio ** 2  # 49 kg/m²


@dataclass
class Geometry:
    L: float
    B: float
    hp: float = 1.00           # ارتفاع ستون
    b: float = 0.80            # ضلع ستون مربعی
    tf: float = 0.40           # ضخامت پی


@dataclass
class CaseForces:
    no: int
    name: str
    Fe: float
    Fs: float
    Nmax: float
    Nmin: float
    V: float
    M: float
    factor: float


@dataclass
class Check:
    name: str
    value: float
    limit: float
    passed: bool
    direction: str             # ">" یا "<"
    unit: str = ""
    steps: list = field(default_factory=list)


@dataclass
class Result:
    geometry: Geometry
    cases: list
    governing: CaseForces
    ultimate: CaseForces
    w_concrete: float
    w_soil: float
    w_total: float
    eccentricity: float
    checks: list

    @property
    def ok(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def volumes(self) -> dict:
        g = self.geometry
        return {"concrete": g.L * g.B * g.tf + self._n * g.hp * g.b ** 2}

    _n: int = 1


def build_cases(eq: Equipment, wind: WindParams, ch: float, cv: float, eq_sc: float = 0.6):
    """پنج حالت بارگذاری مطابق بخش LOAD COMBINATIONS."""
    return [
        dict(no=1, name="یخ + باد نرمال",      Fc=eq.Fc,    Fe=wind.q_normal * eq.Ce * eq.Ae,
             Fs=wind.q_normal * eq.Cs * eq.As, k=1.5, cv=0.0),
        dict(no=2, name="باد شدید",            Fc=eq.Fc,    Fe=wind.q_high * eq.Ce * eq.Ae,
             Fs=wind.q_high * eq.Cs * eq.As,   k=1.5, cv=0.0),
        dict(no=3, name="باد شدید + ات.کوتاه", Fc=eq.Fc_sc, Fe=wind.q_sc * eq.Ce * eq.Ae,
             Fs=wind.q_sc * eq.Cs * eq.As,     k=1.1, cv=0.0),
        dict(no=4, name="زلزله",               Fc=eq.Fc,    Fe=ch * eq.We,
             Fs=ch * eq.Ws,                    k=1.1, cv=cv),
        dict(no=5, name="زلزله + ات.کوتاه",    Fc=eq.Fc_sc, Fe=ch * eq.We * eq_sc,
             Fs=ch * eq.Ws * eq_sc,            k=1.1, cv=cv * eq_sc),
    ]


def case_forces(lc: dict, eq: Equipment) -> CaseForces:
    n = (eq.Wc + eq.We) * eq.npol + eq.Ws
    v = (lc["Fc"] + lc["Fe"]) * eq.npol + lc["Fs"]
    m = (sum(lc["Fc"] * eq.npol * (eq.Hs + h) for h in eq.conductor_points)
         + lc["Fe"] * eq.npol * (eq.Hs + eq.he)
         + lc["Fs"] * eq.hs)
    return CaseForces(lc["no"], lc["name"], lc["Fe"], lc["Fs"],
                      (1 + lc["cv"]) * n, (1 - lc["cv"]) * n, v, m, lc["k"])


def analyse(eq: Equipment, geo: Geometry, soil: SoilAndMaterials,
            wind: WindParams, ch: float, cv: float) -> Result:
    cases = [case_forces(lc, eq) for lc in build_cases(eq, wind, ch, cv)]
    g = max(cases, key=lambda c: c.Nmax + c.V + c.M)

    # بارهای مانور تجهیز روی حالت حاکم اضافه می‌شوند
    g = CaseForces(g.no, g.name, g.Fe, g.Fs,
                   g.Nmax + eq.op_vertical, g.Nmin - eq.op_vertical,
                   g.V + eq.op_horizontal, g.M + eq.op_moment, g.factor)
    u = CaseForces(g.no, g.name, g.Fe, g.Fs,
                   g.Nmax * g.factor, g.Nmin * g.factor,
                   g.V * g.factor, g.M * g.factor, g.factor)

    n = eq.n_pedestal
    A = geo.L * geo.B
    f = lambda v, d=2: f"{v:.{d}f}"

    w_c = (A * geo.tf + n * geo.hp * geo.b ** 2) * soil.gamma_c
    w_s = (A - n * geo.b ** 2) * (geo.hp - soil.soil_cover) * soil.gamma_s
    w_t = w_c + w_s + g.Nmin

    weight_steps = [
        ("وزن بتن", "W_c = (L·B·t_f + n·h_p·b²)·γ_c",
         f"({f(geo.L)}×{f(geo.B)}×{f(geo.tf)} + {n}×{f(geo.hp)}×{f(geo.b)}²)×{soil.gamma_c:.0f} = {w_c:.0f} kg"),
        ("وزن خاک روی پی", "W_s = (L·B − n·b²)·(h_p − 0.15)·γ_s",
         f"({f(A)} − {n}×{f(geo.b**2)})×({f(geo.hp)}−0.15)×{soil.gamma_s:.0f} = {w_s:.0f} kg"),
        ("وزن کل قائم", "W = W_c + W_s + N_min",
         f"{w_c:.0f} + {w_s:.0f} + {g.Nmin:.0f} = {w_t:.0f} kg"),
    ]

    checks = []

    # ۱ — واژگونی
    mo = g.V * (geo.hp + geo.tf) + g.M
    mr = w_t * geo.B / 2
    sf = mr / mo if mo else float("inf")
    checks.append(Check("ضریب اطمینان واژگونی", sf, soil.sf_overturn, sf > soil.sf_overturn, ">", "",
        weight_steps + [
            ("لنگر واژگون‌کننده", "M_o = V·(h_p + t_f) + M",
             f"{g.V:.0f}×({f(geo.hp)}+{f(geo.tf)}) + {g.M:.0f} = {mo:.0f} kg·m"),
            ("لنگر مقاوم", "M_r = W · B/2", f"{w_t:.0f} × {f(geo.B)}/2 = {mr:.0f} kg·m"),
            ("ضریب اطمینان", "SF = M_r / M_o ≥ 1.75", f"{mr:.0f} / {mo:.0f} = {sf:.2f}"),
        ]))

    # ۲ — تنش خاک
    ecc = mo / w_t
    Bc, Lc, ec = geo.B * 100, geo.L * 100, ecc * 100
    triangular = ecc > geo.B / 6
    if Bc - 2 * ec <= 0:
        q = float("inf")
    elif triangular:
        q = 4 * w_t / (3 * Lc * (Bc - 2 * ec))
    else:
        q = w_t / (Lc * Bc) * (1 + 6 * ecc / geo.B)
    checks.append(Check("حداکثر تنش خاک", q, soil.q_all, q <= soil.q_all, "<", "kg/cm²", [
        ("خروج از مرکزیت", "e = M_o / W", f"{mo:.0f} / {w_t:.0f} = {ecc:.3f} m"),
        ("هسته مرکزی", "B/6", f"{f(geo.B)}/6 = {geo.B/6:.3f} m → توزیع "
                              f"{'مثلثی' if triangular else 'ذوزنقه‌ای'}"),
        ("تنش حداکثر",
         "q_max = 4W / (3·L·(B − 2e))" if triangular else "q_max = W/(L·B)·(1 + 6e/B)",
         f"{q:.2f} kg/cm²"),
        ("تنش مجاز", "q_all = q_a × ضریب بار موقت",
         f"{soil.q_base:.2f} × {soil.q_factor:.2f} = {soil.q_all:.2f} kg/cm²"),
    ]))

    # ۳ — بلندشدگی پی
    w_u = u.Nmax + w_c + w_s
    m_u = u.M + u.V * (geo.hp + geo.tf)
    x = geo.B / 2 - m_u / w_u
    uplift = geo.B - 3 * x
    checks.append(Check("طول بلندشدگی پی", uplift, geo.B / 4, uplift <= geo.B / 4, "<", "m", [
        ("وزن قائم نهایی", "W_u = N_u + W_c + W_s", f"{u.Nmax:.0f} + {w_c:.0f} + {w_s:.0f} = {w_u:.0f} kg"),
        ("لنگر نهایی", "M_u = M + V·(h_p + t_f)", f"{m_u:.0f} kg·m"),
        ("بازوی فشاری", "x = B/2 − M_u / W_u", f"{f(geo.B)}/2 − {m_u:.0f}/{w_u:.0f} = {x:.3f} m"),
        ("طول بلندشدگی", "L_up = B − 3x", f"{f(geo.B)} − 3×{x:.3f} = {uplift:.3f} m"),
        ("حد مجاز", "B/4", f"{geo.B/4:.3f} m"),
    ]))

    # ۴ — لغزش
    resist = (w_c + w_s + g.Nmin) * soil.friction
    sf_s = resist / g.V if g.V else float("inf")
    checks.append(Check("ضریب اطمینان لغزش", sf_s, soil.sf_sliding, sf_s > soil.sf_sliding, ">", "", [
        ("نیروی مقاوم", "F_r = (W_c + W_s + N_min)·μ",
         f"({w_c:.0f}+{w_s:.0f}+{g.Nmin:.0f})×{soil.friction} = {resist:.0f} kg"),
        ("ضریب اطمینان", "SF = F_r / V ≥ 1.20", f"{resist:.0f} / {g.V:.0f} = {sf_s:.2f}"),
    ]))

    r = Result(geo, cases, g, u, w_c, w_s, w_t, ecc, checks)
    r._n = n
    return r


def find_dimensions(eq: Equipment, soil: SoilAndMaterials, wind: WindParams,
                    ch: float, cv: float, hp=1.0, b=0.8, tf=0.4,
                    lo=1.0, hi=5.0, step=0.1):
    """کوچک‌ترین پی مربعی که هر چهار کنترل را پاس کند."""
    i = 0
    while True:
        side = round(lo + i * step, 2)
        if side > hi:
            return None
        res = analyse(eq, Geometry(side, side, hp, b, tf), soil, wind, ch, cv)
        if res.ok:
            return res
        i += 1


def quantities(res: Result, eq: Equipment, soil: SoilAndMaterials) -> dict:
    """متره — با اعداد نقشه ۰۶-۴LA_C تطبیق داده شده (۲٫۲۴ و ۰٫۴۸۴ متر مکعب)."""
    g, n = res.geometry, eq.n_pedestal
    lean = soil.lean / 1000
    return {
        "concrete": g.L * g.B * g.tf + n * g.hp * g.b ** 2,
        "lean": (g.L + 0.2) * (g.B + 0.2) * lean,
        "excavation": (g.L + 1.0) * (g.B + 1.0) * (g.tf + g.hp - soil.soil_cover + lean),
        "formwork": 2 * (g.L + g.B) * g.tf + n * 4 * g.b * g.hp,
    }
