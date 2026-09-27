"""
طراحی مقطع بتنی — خمش، برش پانچ و برش یک‌طرفه.

مبنا: مبحث نهم مقررات ملی (روش مقاومت نهایی).
واحدها در این ماژول: kg و cm  (ورودی از موتور بر حسب kg و m است و اینجا تبدیل می‌شود)

فرمول‌ها:
    خمش      Rn = M_u / (φ·b·d²)
             ρ  = 0.85·f'c/f_y · (1 − √(1 − 2·Rn/(0.85·f'c)))
             ρ_min = max( min(14.1/f_y , 4/3·ρ) , 0.0018 )     ρ_max = 0.75·ρ_b
             (بند جایگزین ۴/۳ برابر آرماتور لازم — همان قاعده‌ای که دفترچه
              کامی‌آباد به کار برده و به Ф۱۴@۲۰۰ برای پی می‌رسد)
             ρ_b = 0.85·β₁·f'c/f_y · 6120/(6120 + f_y)
    پانچ     b₀ = 4·(b + d)      φV_c = φ·1.06·√f'c·b₀·d
    یک‌طرفه  φV_c = φ·0.53·√f'c·b_w·d
"""
import math
from dataclasses import dataclass, field

PHI_FLEX = 0.90
PHI_SHEAR = 0.75

BAR_AREA = {10: 0.785, 12: 1.131, 14: 1.539, 16: 2.011,
            18: 2.545, 20: 3.142, 22: 3.801, 25: 4.909, 28: 6.158}


def beta1(fc: float) -> float:
    if fc <= 280:
        return 0.85
    return max(0.65, 0.85 - 0.05 * (fc - 280) / 70)


def rho_balanced(fc: float, fy: float) -> float:
    return 0.85 * beta1(fc) * fc / fy * (6120 / (6120 + fy))


def min_ratio(rho, fy):
    """ρ_min = max( min(14.1/fy , 4/3·ρ) , 0.0018 ) — بند جایگزین مبحث نهم."""
    if rho is None:
        return max(14.1 / fy, 0.0018)
    return max(min(14.1 / fy, 4 / 3 * rho), 0.0018)


def rho_required(mu: float, b: float, d: float, fc: float, fy: float):
    """mu بر حسب kg·cm ، b و d بر حسب cm. خروجی: (ρ، Rn) یا None اگر مقطع کافی نباشد."""
    rn = mu / (PHI_FLEX * b * d ** 2)
    inner = 1 - 2 * rn / (0.85 * fc)
    if inner < 0:
        return None, rn
    return 0.85 * fc / fy * (1 - math.sqrt(inner)), rn


@dataclass
class SectionDesign:
    title: str
    mu: float                 # kg·cm
    b: float                  # cm
    d: float                  # cm
    rho: float
    rho_min: float
    rho_max: float
    as_req: float             # cm²
    bar_dia: int
    bar_count: int = 0
    spacing: float = 0.0      # mm — برای شبکه پی
    ok: bool = True
    note: str = ""
    steps: list = field(default_factory=list)


def design_pedestal(nu, vu, mu_top, geo, mat, n_ped, bar_dia=18, min_bars=8):
    """
    ستون به صورت عضو خمشی طراحی می‌شود (همان روش دفترچه کامی‌آباد).
    لنگر پای ستون = لنگر بالای پی + برش × ارتفاع ستون، تقسیم بر تعداد ستون.
    """
    b = geo.b * 100
    d = b - mat.cover / 10 - 2.5
    mu = (mu_top + vu * geo.hp) / n_ped * 100          # kg·cm
    rho, rn = rho_required(mu, b, d, mat.fc, mat.fy)
    rmin = min_ratio(rho, mat.fy)
    rmax = 0.75 * rho_balanced(mat.fc, mat.fy)
    ok = rho is not None and rho <= rmax
    rho_used = max(rho or 0, rmin)
    as_req = rho_used * b * d
    count = max(min_bars, math.ceil(as_req / BAR_AREA[bar_dia] / 4) * 4)   # مضرب ۴
    return SectionDesign(
        "آرماتور ستون", mu, b, d, rho_used, rmin, rmax, as_req, bar_dia,
        bar_count=count, ok=ok,
        note="" if ok else "مقطع ستون برای لنگر کافی نیست — b یا h_p را بزرگ کنید",
        steps=[
            ("لنگر پای ستون", "M_u = (M_u,top + V_u·h_p) / n",
             f"({mu_top:.0f} + {vu:.0f}×{geo.hp:.2f}) / {n_ped} = {mu/100:.0f} kg·m"),
            ("عمق مؤثر", "d = b − پوشش − ۲٫۵", f"{b:.0f} − {mat.cover/10:.1f} − 2.5 = {d:.1f} cm"),
            ("Rn", "R_n = M_u / (φ·b·d²)", f"{rn:.2f} kg/cm²"),
            ("نسبت آرماتور", "ρ = 0.85f'c/fy·(1−√(1−2Rn/0.85f'c))",
             f"ρ = {rho if rho else 0:.5f}  |  ρ_min = {rmin:.5f}  |  ρ_max = {rmax:.5f}"),
            ("سطح مقطع لازم", "A_s = ρ·b·d", f"{rho_used:.5f}×{b:.0f}×{d:.1f} = {as_req:.1f} cm²"),
            ("انتخاب", f"{count} میلگرد Ф{bar_dia}",
             f"{count}×{BAR_AREA[bar_dia]} = {count*BAR_AREA[bar_dia]:.1f} cm² ≥ {as_req:.1f}"),
        ])


def ultimate_pressure(res, geo, mat, n_ped):
    """
    توزیع تنش نهایی زیر پی با احتساب خروج از مرکزیت.
    خروجی بر حسب kg/cm² و فاصله‌ها بر حسب cm.
    وقتی e > B/6 توزیع مثلثی است و فشار لبه بسیار بزرگ‌تر از فرض یکنواخت می‌شود؛
    همین توزیع مبنای خمش پی و برش قرار می‌گیرد.
    """
    L, B, tf, b = geo.L * 100, geo.B * 100, geo.tf * 100, geo.b * 100
    w_u = res.ultimate.Nmax + res.w_concrete + res.w_soil          # kg
    m_u = (res.ultimate.M + res.ultimate.V * (geo.hp + geo.tf)) * 100   # kg·cm
    e = m_u / w_u                                                   # cm
    if e > B / 6:                                                   # مثلثی
        x = B / 2 - e
        span = max(3 * x, 1.0)                                      # طول ناحیه فشاری
        q_max = 2 * w_u / (3 * L * x)
    else:                                                           # ذوزنقه‌ای
        span = B
        q_max = w_u / (L * B) * (1 + 6 * e / B)
    c = (B - b) / 2                                                 # طره از وجه ستون
    q_face = q_max * max(0.0, (span - c)) / span
    return dict(w_u=w_u, e=e, span=span, q_max=q_max, q_face=q_face, c=c,
                L=L, B=B, tf=tf, b=b, triangular=e > B / 6)


def design_pad(res, geo, mat, n_ped, bar_dia=14):
    """
    خمش پی در مقطع بر وجه ستون، با توزیع تنش نهایی خاک.
    q_u از بار نهایی و سطح پی گرفته می‌شود (توزیع یکنواخت معادل، سمت اطمینان).
    """
    P = ultimate_pressure(res, geo, mat, n_ped)
    L, B, tf, b, c = P["L"], P["B"], P["tf"], P["b"], P["c"]
    d = tf - mat.cover / 10 - 1.5
    # لنگر طره با توزیع ذوزنقه‌ای: بخش مستطیلی + بخش مثلثی
    mu = (0.5 * P["q_face"] * c ** 2 + (1 / 3) * (P["q_max"] - P["q_face"]) * c ** 2) * L
    rho, rn = rho_required(mu, L, d, mat.fc, mat.fy)
    rmin = min_ratio(rho, mat.fy)
    rmax = 0.75 * rho_balanced(mat.fc, mat.fy)
    ok = rho is not None and rho <= rmax
    rho_used = max(rho or 0, rmin)
    as_req = rho_used * L * d
    n_bar = max(2, math.ceil(as_req / BAR_AREA[bar_dia]))
    width = (L - 2 * mat.cover / 10) * 10                 # عرض قابل استفاده، mm
    smax = min(3 * tf * 10, 450.0)                        # حداکثر فاصله مجاز
    spacing = width / (n_bar - 1) if n_bar > 1 else smax
    spacing = min(spacing, smax, 200.0)                   # ۲۰۰ استاندارد دفتر
    spacing = max(100.0, math.floor(spacing / 25) * 25)
    n_bar = int(width // spacing) + 1                     # تعداد واقعی با این فاصله
    as_prov = n_bar * BAR_AREA[bar_dia]
    return SectionDesign(
        "آرماتور پی", mu, L, d, rho_used, rmin, rmax, as_req, bar_dia,
        spacing=spacing, bar_count=n_bar, ok=ok and as_prov >= as_req,
        note="" if ok else "ضخامت پی برای خمش کافی نیست — t_f را زیاد کنید",
        steps=[
            ("توزیع تنش نهایی", "e = M_u / W_u  →  " +
             ("مثلثی، q_max = 2W_u/(3·L·x)" if P["triangular"] else "ذوزنقه‌ای"),
             f"e = {P['e']:.1f} cm ، طول ناحیه فشاری = {P['span']:.1f} cm ، "
             f"q_max = {P['q_max']:.3f} kg/cm²"),
            ("تنش در وجه ستون", "q_face = q_max·(span − c)/span", f"{P['q_face']:.3f} kg/cm²"),
            ("طره", "c = (B − b)/2", f"({B:.0f}−{b:.0f})/2 = {c:.1f} cm"),
            ("لنگر", "M_u = [0.5·q_face·c² + ⅓·(q_max−q_face)·c²]·L", f"{mu/100:.0f} kg·m"),
            ("عمق مؤثر", "d = t_f − پوشش − ۱٫۵", f"{d:.1f} cm"),
            ("نسبت آرماتور", "ρ", f"{rho_used:.5f}  (ρ_min={rmin:.5f})"),
            ("سطح لازم", "A_s = ρ·L·d", f"{as_req:.1f} cm²"),
            ("انتخاب", f"{n_bar}Ф{bar_dia}@{spacing:.0f}  در هر جهت، رو و زیر",
             f"A_s تأمین‌شده = {as_prov:.1f} ≥ {as_req:.1f} cm²"),
        ])


def check_punching(res, geo, mat, n_ped):
    """برش دوطرفه در محیط بحرانی به فاصله d/2 از وجه ستون."""
    P = ultimate_pressure(res, geo, mat, n_ped)
    L, B, tf, b = P["L"], P["B"], P["tf"], P["b"]
    d = tf - mat.cover / 10 - 1.5
    nu = res.ultimate.Nmax
    qu = P["q_max"]                                    # سمت اطمینان: فشار لبه
    b0 = 4 * (b + d)
    vu = nu / n_ped - qu * (b + d) ** 2 * 0
    vc = PHI_SHEAR * 1.06 * math.sqrt(mat.fc) * b0 * d
    return SectionDesign(
        "برش پانچ", 0, b0, d, 0, 0, 0, 0, 0, ok=vu <= vc,
        note=f"{vu/1000:.1f} ton ≤ {vc/1000:.1f} ton",
        steps=[
            ("محیط بحرانی", "b₀ = 4·(b + d)", f"4×({b:.0f}+{d:.1f}) = {b0:.0f} cm"),
            ("برش وارده", "V_u = N_u / n   (سمت اطمینان، بدون کسر فشار داخل محیط)",
             f"{nu:.0f} / {n_ped} = {vu:.0f} kg"),
            ("مقاومت", "φV_c = 0.75·1.06·√f'c·b₀·d",
             f"0.75×1.06×√{mat.fc}×{b0:.0f}×{d:.1f} = {vc:.0f} kg"),
            ("نتیجه", "V_u ≤ φV_c", f"{vu/1000:.1f} ton ≤ {vc/1000:.1f} ton"),
        ])


def check_oneway(res, geo, mat, n_ped=1):
    """برش یک‌طرفه در مقطع به فاصله d از وجه ستون."""
    P = ultimate_pressure(res, geo, mat, 1)
    L, B, tf, b = P["L"], P["B"], P["tf"], P["b"]
    d = tf - mat.cover / 10 - 1.5
    a = max(0.0, (B - b) / 2 - d)                       # طول باقی‌مانده طره
    qu = P["q_max"]                                     # فشار لبه، سمت اطمینان
    vu = qu * L * a
    vc = PHI_SHEAR * 0.53 * math.sqrt(mat.fc) * L * d
    return SectionDesign(
        "برش یک‌طرفه", 0, L, d, 0, 0, 0, 0, 0, ok=vu <= vc,
        note=f"{vu/1000:.1f} ton ≤ {vc/1000:.1f} ton",
        steps=[
            ("طول مؤثر طره", "a = (B − b)/2 − d", f"{a:.1f} cm"),
            ("برش وارده", "V_u = q_max·L·a", f"{qu:.3f}×{L:.0f}×{a:.1f} = {vu:.0f} kg"),
            ("مقاومت", "φV_c = 0.75·0.53·√f'c·L·d", f"{vc:.0f} kg"),
            ("نتیجه", "V_u ≤ φV_c", f"{vu/1000:.1f} ton ≤ {vc/1000:.1f} ton"),
        ])


# سطح مقطع تنش کششی پیچ (mm²) — ISO 898-1
TENSILE_AREA = {12: 84.3, 16: 157, 20: 245, 22: 303, 24: 353, 27: 459, 30: 561, 33: 694, 36: 817}
KG_CM2_TO_MPA = 0.0980665


def development_length(db, fy, fc):
    """
    طول مهاری میلگرد مستقیم در کشش (mm) — مبحث نهم / ACI 318 جدول 25.4.2.3،
    با ψt = ψe = λ = 1:  l_d = fy/(2.1·√f'c)·d_b برای قطر ۱۹ و کمتر، و /1.7 برای بزرگ‌تر.
    fy و fc بر حسب kg/cm².
    """
    fy_m, fc_m = fy * KG_CM2_TO_MPA, fc * KG_CM2_TO_MPA
    k = 2.1 if db <= 19 else 1.7
    return max(fy_m / (k * math.sqrt(fc_m)) * db, 300.0)


def hooked_length(db, fy, fc):
    """طول مهاری میلگرد قلاب‌دار (mm) — ACI 318 بند 25.4.3.1: l_dh = 0.24·fy/√f'c·d_b ≥ max(8d_b, 150)."""
    fy_m, fc_m = fy * KG_CM2_TO_MPA, fc * KG_CM2_TO_MPA
    return max(0.24 * fy_m / math.sqrt(fc_m) * db, 8 * db, 150.0)


def design_anchor(res, eq, mat, anch, ped):
    """
    میل مهار پای سازه.

    نیرو: لنگر پای سازه سهم هر ستون، به صورت زوج‌نیرو روی ردیف میل مهارها،
    منهای سهم وزن (N_min) هر میل مهار:
        T_u = M_u / (n_ped · g · n_row) − N_u,min / (n_ped · n)

    طول مدفون (خودکار) — بیشترینِ:
      ۱) طول مهاری میلگرد طولی ستون (l_d). مخروط شکست بتن زیر میل مهار باید
         آرماتور ستون را قطع کند و آرماتور دو طرف آن گیرایی داشته باشد؛ پس
         میل مهار دست‌کم به اندازه l_d آرماتور ستون در بتن می‌رود.
      ۲) طول مهاری خود میل مهار قلاب‌دار (l_dh).
      ۳) حداقل ۱۲ برابر قطر میل مهار.
    به بالا گرد می‌شود و نباید از عمق موجود (ستون + پی − پوشش − شبکه پی) بیشتر شود.
    """
    geo, u = res.geometry, res.ultimate
    n_ped, n = eq.n_pedestal, max(eq.anchor_n, 1)
    d, g = eq.anchor_dia, eq.anchor_gauge
    rows = max(1, n // 2)
    m_ped = u.M / n_ped                                    # kg·m
    n_min = u.Nmin / n_ped                                 # kg
    t_u = max(0.0, m_ped * 1000 / (g * rows) - n_min / n) if g else 0.0
    v_u = u.V / n_ped / n

    a_se = TENSILE_AREA.get(int(d), 0.78 * math.pi * d * d / 4)      # mm²
    phi_nsa = 0.75 * a_se / 100 * anch.fu                           # kg
    phi_vsa = 0.65 * 0.6 * a_se / 100 * anch.fu * 0.8               # kg، با ضریب ۰٫۸ گروت
    inter = t_u / phi_nsa + v_u / phi_vsa if phi_nsa and phi_vsa else 0.0
    steel_ok = t_u <= phi_nsa and v_u <= phi_vsa and inter <= 1.2

    ld_ped = development_length(ped.bar_dia, mat.fy, mat.fc)
    ldh = hooked_length(d, anch.fy, mat.fc)
    l_min = 12 * d
    required = max(ld_ped, ldh, l_min)
    embed = math.ceil(required / anch.rounding) * anch.rounding
    pad_bar = 14
    available = (geo.hp + geo.tf) * 1000 - mat.cover - 2 * pad_bar
    ok = steel_ok and embed <= available
    governs = {ld_ped: "طول مهاری آرماتور ستون", ldh: "طول مهاری میل مهار قلاب‌دار",
               l_min: "حداقل ۱۲d"}[required]
    note = ""
    if embed > available:
        note = (f"طول مدفون لازم {embed:.0f} mm از عمق موجود {available:.0f} mm بیشتر است — "
                "h_p یا t_f را زیاد کنید")
    elif not steel_ok:
        note = "مقطع میل مهار برای کشش/برش کافی نیست — قطر یا تعداد را زیاد کنید"

    sd = SectionDesign(
        "میل مهار", 0, 0, 0, 0, 0, 0, 0, int(d), bar_count=n, ok=ok, note=note,
        steps=[
            ("نیروی کششی هر میل مهار",
             "T_u = M_u/(n_ped·g·n_row) − N_u,min/(n_ped·n)",
             f"{u.M:.0f}/({n_ped}×{g/1000:.3f}×{rows}) − {u.Nmin:.0f}/({n_ped}×{n}) = {t_u:.0f} kg"),
            ("برش هر میل مهار", "V_u = V/(n_ped·n)", f"{v_u:.0f} kg"),
            ("مقاومت کششی فولاد", "φN_sa = 0.75·A_se·f_u",
             f"0.75×{a_se:.0f} mm²×{anch.fu:.0f} = {phi_nsa:.0f} kg"),
            ("مقاومت برشی فولاد", "φV_sa = 0.65·0.6·A_se·f_u·0.8 (گروت)", f"{phi_vsa:.0f} kg"),
            ("اندرکنش", "T/φN + V/φV ≤ 1.2", f"{inter:.2f}"),
            ("۱) مهاری آرماتور ستون", f"l_d = fy/(2.1√f'c)·d_b  (Ф{ped.bar_dia})",
             f"{ld_ped:.0f} mm"),
            ("۲) مهاری میل مهار قلاب‌دار", "l_dh = 0.24·fy/√f'c·d_b ≥ max(8d, 150)",
             f"{ldh:.0f} mm"),
            ("۳) حداقل", "12·d", f"{l_min:.0f} mm"),
            ("طول مدفون", f"max(۱، ۲، ۳) ← {governs}، گرد به {anch.rounding:.0f}",
             f"{embed:.0f} mm  (عمق موجود {available:.0f} mm)"),
        ])
    sd.embed = embed
    sd.tension = t_u
    sd.shear = v_u
    return sd


def design_all(res, eq, mat, rebar=None, anchorage=None):
    geo = res.geometry
    n = eq.n_pedestal
    col_dia = rebar.col_dia if rebar else 18
    pad_dia = rebar.pad_dia if rebar else 14
    min_bars = rebar.col_min_bars if rebar else 8
    ped = design_pedestal(res.ultimate.Nmax, res.ultimate.V, res.ultimate.M, geo, mat, n,
                          bar_dia=col_dia, min_bars=min_bars)
    pad = design_pad(res, geo, mat, n, bar_dia=pad_dia)
    punch = check_punching(res, geo, mat, n)
    oneway = check_oneway(res, geo, mat, n)
    if anchorage is None:
        from config import Anchorage
        anchorage = Anchorage()
    anchor = design_anchor(res, eq, mat, anchorage, ped)
    return {"pedestal": ped, "pad": pad, "punching": punch, "oneway": oneway, "anchor": anchor}
