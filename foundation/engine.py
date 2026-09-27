"""
موتور محاسبه فونداسیون پایه تجهیزات پست.

منطق دقیقاً بازنویسی شیت‌های EQUIPMENT CALCULATION است و با هر هشت شیت
پروژه کامی‌آباد تطبیق داده شده (اختلاف نیروها کمتر از ۱ کیلوگرم).

تفاوت مهم با اکسل: در اکسل ابعاد ورودی است و شیت فقط کنترل می‌کند.
اینجا find_dimensions کوچک‌ترین ابعادی را پیدا می‌کند که همه کنترل‌ها را پاس کند.

واحدها: kg و m ، تنش خاک kg/cm².
"""
import math
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
    shear_offset: float = 60.0  # d = t_f − این مقدار در کنترل برش (mm) — دفترچه ۶۳: ۴۰−۶=۳۴

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
    case: int = 0              # حالت باری که این کنترل را حاکم کرده


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


# ------------------------------------------------------------------ گزینه‌های مهندس
# هر دو انتخاب با مهندس است؛ سامانه پیشنهاد خودش را کنار هر گزینه نشان می‌دهد
# و ابعاد هر دو روش را حساب می‌کند تا اثر انتخاب دیده شود.
GOVERNING_OPTIONS = {
    "notebook": "روش دفترچه — حالتی که N+V+M آن بیشترین است",
    "envelope": "پوش همه حالات — هر کنترل با بحرانی‌ترین حالت خودش",
    "1": "فقط حالت ۱ — یخ + باد نرمال",
    "2": "فقط حالت ۲ — باد شدید",
    "3": "فقط حالت ۳ — باد شدید + اتصال کوتاه",
    "4": "فقط حالت ۴ — زلزله",
    "5": "فقط حالت ۵ — زلزله + اتصال کوتاه",
}
BEARING_OPTIONS = {
    "min": "با N_min — روش دفترچه",
    "max": "با N_max",
    "envelope": "بحرانی‌ترین از N_max و N_min",
}
RECOMMENDED = {"governing": "envelope", "bearing": "envelope"}
WHY = {
    "governing": "جمع N+V+M واحدهای ناهمگون (kg و kg·m) را با هم جمع می‌کند؛ "
                 "حالتی که برای واژگونی بحرانی است لزوماً برای تنش خاک یا لغزش "
                 "بحرانی نیست. پوش، هر چهار کنترل را برای هر پنج حالت انجام "
                 "می‌دهد و بدترین را برمی‌دارد.",
    "bearing": "تنش خاک معمولاً با بیشترین بار قائم کنترل می‌شود؛ ولی وقتی خروج "
               "از مرکزیت زیاد است (توزیع مثلثی)، بار قائم کمتر می‌تواند تنش لبه "
               "بیشتری بدهد. پس هر دو حساب و بدترین برداشته می‌شود.",
}


def _with_operation(c: CaseForces, eq: Equipment) -> CaseForces:
    """بارهای مانور تجهیز روی حالت اضافه می‌شوند."""
    return CaseForces(c.no, c.name, c.Fe, c.Fs,
                      c.Nmax + eq.op_vertical, c.Nmin - eq.op_vertical,
                      c.V + eq.op_horizontal, c.M + eq.op_moment, c.factor)


def _bearing(w, mo, geo):
    """تنش حداکثر خاک برای بار قائم w و لنگر واژگونی mo."""
    ecc = mo / w
    Bc, Lc, ec = geo.B * 100, geo.L * 100, ecc * 100
    triangular = ecc > geo.B / 6
    if Bc - 2 * ec <= 0:
        q = float("inf")
    elif triangular:
        q = 4 * w / (3 * Lc * (Bc - 2 * ec))
    else:
        q = w / (Lc * Bc) * (1 + 6 * ecc / geo.B)
    return q, ecc, triangular


def _ultimate(c: CaseForces) -> CaseForces:
    return CaseForces(c.no, c.name, c.Fe, c.Fs, c.Nmax * c.factor, c.Nmin * c.factor,
                      c.V * c.factor, c.M * c.factor, c.factor)


def _sum(forces, no, name) -> CaseForces:
    """جمع نیروهای چند گروه تجهیز روی یک پی."""
    return CaseForces(no, name, sum(c.Fe for c in forces), sum(c.Fs for c in forces),
                      sum(c.Nmax for c in forces), sum(c.Nmin for c in forces),
                      sum(c.V for c in forces), sum(c.M for c in forces), forces[0].factor)


def _checks_for(g: CaseForces, u: CaseForces, n: int, geo, soil, bearing):
    """چهار کنترل برای یک حالت بار (g سرویس، u نهایی، n تعداد کل ستون‌ها)."""
    A = geo.L * geo.B
    f = lambda v, d=2: f"{v:.{d}f}"
    case_step = ("حالت بار", f"#{g.no}", g.name)

    w_c = (A * geo.tf + n * geo.hp * geo.b ** 2) * soil.gamma_c
    w_s = (A - n * geo.b ** 2) * (geo.hp - soil.soil_cover) * soil.gamma_s
    w_t = w_c + w_s + g.Nmin

    weight_steps = [
        case_step,
        ("وزن بتن", "W_c = (L·B·t_f + n·h_p·b²)·γ_c",
         f"({f(geo.L)}×{f(geo.B)}×{f(geo.tf)} + {n}×{f(geo.hp)}×{f(geo.b)}²)×{soil.gamma_c:.0f} = {w_c:.0f} kg"),
        ("وزن خاک روی پی", f"W_s = (L·B − n·b²)·(h_p − {soil.soil_cover:.2f})·γ_s",
         f"({f(A)} − {n}×{f(geo.b**2)})×({f(geo.hp)}−{soil.soil_cover:.2f})×{soil.gamma_s:.0f} = {w_s:.0f} kg"),
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
            ("ضریب اطمینان", f"SF = M_r / M_o ≥ {soil.sf_overturn}", f"{mr:.0f} / {mo:.0f} = {sf:.2f}"),
        ]))

    # ۲ — تنش خاک
    variants = {"min": ("N_min", g.Nmin), "max": ("N_max", g.Nmax)}
    use = ["min", "max"] if bearing == "envelope" else [bearing]
    results = []
    for key in use:
        label, nv = variants[key]
        w = w_c + w_s + nv
        q, ecc, tri = _bearing(w, mo, geo)
        results.append((q, label, w, ecc, tri))
    q, label, w_b, ecc, triangular = max(results, key=lambda r: r[0])
    steps = [case_step,
             ("بار قائم", f"W = W_c + W_s + {label}", f"{w_b:.0f} kg")]
    if len(results) > 1:
        steps.append(("مقایسه", "q با N_min و با N_max",
                      "  ،  ".join(f"{r[1]}: {r[0]:.2f}" for r in results) + f"  → حاکم: {label}"))
    steps += [
        ("خروج از مرکزیت", "e = M_o / W", f"{mo:.0f} / {w_b:.0f} = {ecc:.3f} m"),
        ("هسته مرکزی", "B/6", f"{f(geo.B)}/6 = {geo.B/6:.3f} m → توزیع "
                              f"{'مثلثی' if triangular else 'ذوزنقه‌ای'}"),
        ("تنش حداکثر",
         "q_max = 4W / (3·L·(B − 2e))" if triangular else "q_max = W/(L·B)·(1 + 6e/B)",
         f"{q:.2f} kg/cm²"),
        ("تنش مجاز", "q_all = q_a × ضریب بار موقت",
         f"{soil.q_base:.2f} × {soil.q_factor:.2f} = {soil.q_all:.2f} kg/cm²"),
    ]
    checks.append(Check("حداکثر تنش خاک", q, soil.q_all, q <= soil.q_all, "<", "kg/cm²", steps))

    # ۳ — بلندشدگی پی
    w_u = u.Nmax + w_c + w_s
    m_u = u.M + u.V * (geo.hp + geo.tf)
    x = geo.B / 2 - m_u / w_u
    uplift = geo.B - 3 * x
    checks.append(Check("طول بلندشدگی پی", uplift, geo.B / 4, uplift <= geo.B / 4, "<", "m", [
        case_step,
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
        case_step,
        ("نیروی مقاوم", "F_r = (W_c + W_s + N_min)·μ",
         f"({w_c:.0f}+{w_s:.0f}+{g.Nmin:.0f})×{soil.friction} = {resist:.0f} kg"),
        ("ضریب اطمینان", f"SF = F_r / V ≥ {soil.sf_sliding}", f"{resist:.0f} / {g.V:.0f} = {sf_s:.2f}"),
    ]))
    for c in checks:
        c.case = g.no
    return checks, u, w_c, w_s, w_t, ecc, mo


def _utilisation(c: Check) -> float:
    """نسبت بهره‌برداری: بیشتر از ۱ یعنی مردود."""
    if c.direction == ">":
        return c.limit / c.value if c.value else float("inf")
    return c.value / c.limit if c.limit else float("inf")


def _as_layout(obj):
    from padlayout import PadLayout
    return PadLayout.single(obj) if isinstance(obj, Equipment) else obj


def _pick(cases, mode):
    mode = str(mode)
    if mode.isdigit():
        return next(c for c in cases if c.no == int(mode))
    return max(cases, key=lambda c: c.Nmax + c.V + c.M)


def analyse(layout, geo: Geometry, soil: SoilAndMaterials,
            wind: WindParams, ch: float, cv: float,
            governing="notebook", bearing="min") -> Result:
    """
    کنترل‌های پایداری برای یک پی با یک یا چند گروه تجهیز.

    هر گروه پنج حالت بار خودش را دارد. برای پی ترکیبی، نیروهای حاکم گروه‌ها با هم
    جمع می‌شوند (مثل دفترچه ۶۳: V_LA + V_CVT و M_LA + M_CVT). در «پوش همه حالات»
    حالت j همه گروه‌ها با هم جمع و هر پنج ترکیب کنترل می‌شود. حالت دستی یک گروه
    (Group.case) بر گزینه کلی مقدم است.
    """
    layout = _as_layout(layout)
    governing = str(governing)
    per_group = [[case_forces(lc, g.eq) for lc in build_cases(g.eq, wind, ch, cv)]
                 for g in layout.groups]

    if governing == "envelope":
        candidates = [[(_pick(cs, grp.case) if grp.case else cs[j])
                       for grp, cs in zip(layout.groups, per_group)] for j in range(5)]
    else:
        candidates = [[_pick(cs, grp.case or governing)
                       for grp, cs in zip(layout.groups, per_group)]]

    n = layout.n_ped
    single = len(layout.groups) == 1
    evaluated = []
    for picks in candidates:
        gs = [_with_operation(c, grp.eq) for c, grp in zip(picks, layout.groups)]
        us = [_ultimate(c) for c in gs]
        if single:
            G, U = gs[0], us[0]
        else:
            name = " + ".join(f"{grp.eq.tag} #{c.no}" for c, grp in zip(picks, layout.groups))
            G, U = _sum(gs, picks[0].no, name), _sum(us, picks[0].no, name)
        checks, _, w_c, w_s, w_t, ecc, mo = _checks_for(G, U, n, geo, soil, bearing)
        evaluated.append((G, U, checks, w_c, w_s, w_t, ecc, mo, list(zip(gs, us))))

    # هر کنترل با بحرانی‌ترین ترکیب خودش
    checks = [max((e[2][i] for e in evaluated), key=_utilisation) for i in range(4)]
    # طراحی مقطع با ترکیبی که بیشترین بلندشدگی (خروج از مرکزیت نهایی) را دارد
    G, U, _, w_c, w_s, w_t, ecc, mo, group_forces = max(evaluated,
                                                        key=lambda e: _utilisation(e[2][2]))
    if single:
        cases = per_group[0]
    else:
        cases = [_sum([cs[j] for cs in per_group], j + 1, per_group[0][j].name) for j in range(5)]

    r = Result(geo, cases, G, U, w_c, w_s, w_t, ecc, checks)
    r._n = n
    r.overturning_moment = mo
    r.group_forces = group_forces          # [(سرویس، نهایی)] هر گروه برای طراحی ستون و میل مهار
    r.layout = layout
    r.options = {"governing": governing, "bearing": bearing}
    return r


def pedestal_fit(eq: Equipment, b: float, min_projection: float) -> float:
    """کوچک‌ترین ضلع پی که ستون‌ها با فاصله داده‌شده کامل رویش بنشینند (m)."""
    if eq.n_pedestal <= 1:
        return b + 2 * min_projection
    return eq.pedestal_spacing + b + 2 * min_projection


def _ceil_step(v, step):
    return round(math.ceil(round(v / step, 6)) * step, 3)


def find_dimensions(layout, soil: SoilAndMaterials, wind: WindParams,
                    ch: float, cv: float, hp=1.0, b=0.8, tf=0.4,
                    lo=1.0, hi=5.0, step=0.1, governing="notebook", bearing="min",
                    min_projection=0.10, L=0.0, B=0.0):
    """
    ابعاد پی.

    حالت کنترل (L و B هر دو داده شده): فقط همان پی کنترل می‌شود — مثل دفترچه ۶۳
    که ابعاد را مهندس انتخاب کرده. نتیجه حتی اگر مردود باشد برگردانده می‌شود.

    حالت طراحی:
      پی منفرد  — کوچک‌ترین پی مربعی که هر چهار کنترل را پاس کند.
      پی مشترک  — L از چیدمان ستون‌ها (+ بیرون‌زدگی دو طرف) یا مقدار داده‌شده؛
                  B از کوچک‌ترین مقدار ممکن آن‌قدر بزرگ می‌شود که کنترل‌ها پاس شوند.
    """
    layout = _as_layout(layout)
    args = (soil, wind, ch, cv, governing, bearing)

    def check(Lx, By):
        return analyse(layout, Geometry(Lx, By, hp, b, tf), soil, wind, ch, cv,
                       governing, bearing)

    if L and B:
        return check(L, B)

    if layout.rectangular:
        fx, fy = layout.footprint(b)
        Lx = L or _ceil_step(max(lo, fx + 2 * min_projection), step)
        By = _ceil_step(max(lo, fy + 2 * min_projection), step)
        if B:
            return check(Lx, B)
        while By <= hi + 1e-9:
            res = check(Lx, By)
            if res.ok:
                return res
            By = round(By + step, 3)
        return None

    if any(g.positions is not None and g.n > 1 for g in layout.groups):
        lo = max(lo, max(layout.footprint(b)) + 2 * min_projection)
    i = 0
    while True:
        side = round(lo + i * step, 2)
        if side > hi:
            return None
        res = check(side, side)
        if res.ok:
            return res
        i += 1


def quantities(res: Result, eq, soil: SoilAndMaterials) -> dict:
    """متره — با اعداد نقشه ۰۶-۴LA_C تطبیق داده شده (۲٫۲۴ و ۰٫۴۸۴ متر مکعب)."""
    g, n = res.geometry, res._n
    lean = soil.lean / 1000
    return {
        "concrete": g.L * g.B * g.tf + n * g.hp * g.b ** 2,
        "lean": (g.L + 0.2) * (g.B + 0.2) * lean,
        "excavation": (g.L + 1.0) * (g.B + 1.0) * (g.tf + g.hp - soil.soil_cover + lean),
        "formwork": 2 * (g.L + g.B) * g.tf + n * 4 * g.b * g.hp,
    }
