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
    پانچ و یک‌طرفه: نشریه ۵۰۷ (روش دفترچه ۶۳ کیمیا)
    ستون و میل مهار: روش دفترچه ۶۳ کیمیا (VP-63POST-CAL-0004)
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


def design_pedestal(nu, vu, mu_top, geo, mat, n_ped, bar_dia=18, min_bars=8,
                    min_ratio_g=0.005, tie_dia=10, tie_spacing=150):
    """
    ستون بتنی به روش دفترچه ۶۳ (صفحه ۱۲):
        M_u1 = (V_u·h_p + M_u) / n_p
        d = b − پوشش − d_خاموت − ½·d_طولی
        آرماتور یک وجه ≥ ρ·b·d   و   آرماتور کل ≥ ρg,min·b·h (۰٫۵٪)
        تعداد مضرب ۴؛ خاموت: (A_v/s)min = 3.5·b_w/f_y ، s_max = 0.5·d
    """
    b = geo.b * 100
    h = b
    d = b - mat.cover / 10 - tie_dia / 10 - 0.5 * bar_dia / 10
    mu = (mu_top + vu * geo.hp) / n_ped * 100          # kg·cm
    rho, rn = rho_required(mu, b, d, mat.fc, mat.fy)
    rmin = min_ratio(rho, mat.fy)
    rmax = 0.75 * rho_balanced(mat.fc, mat.fy)
    ok = rho is not None and rho <= rmax
    rho_used = max(rho or 0, rmin)
    a_bar = BAR_AREA[bar_dia]
    as_face_req = rho_used * b * d
    as_g_req = min_ratio_g * b * h
    count = max(min_bars, 4)
    count = math.ceil(count / 4) * 4
    while count * a_bar < as_g_req or (count / 4 + 1) * a_bar < as_face_req:
        count += 4
    as_face = (count / 4 + 1) * a_bar
    as_tot = count * a_bar
    per_side = count / 4 + 1
    s_ext = (h - 2 * (mat.cover / 10 + tie_dia / 10) - bar_dia / 10) / (per_side - 1) - bar_dia / 10
    s_min = max(1.5 * bar_dia / 10, 4.0)
    av = 2 * BAR_AREA[tie_dia]
    s_req = av / (3.5 * b / mat.fy)
    s_max = 0.5 * d
    ties_ok = tie_spacing / 10 <= min(s_req, s_max)
    ok = ok and s_ext >= s_min and ties_ok
    note = ""
    if not ok:
        note = ("فاصله خاموت بیشتر از مجاز است" if not ties_ok else
                "مقطع ستون برای لنگر یا جای میلگردها کافی نیست — b را بزرگ کنید")
    return SectionDesign(
        "آرماتور ستون", mu, b, d, rho_used, rmin, rmax, as_face_req, bar_dia,
        bar_count=count, ok=ok, note=note,
        steps=[
            ("لنگر پای هر ستون", "M_u1 = (V_u·h_p + M_u) / n_p",
             f"({vu:.0f}×{geo.hp:.2f} + {mu_top:.0f}) / {n_ped} = {mu/100:.0f} kg·m"),
            ("عمق مؤثر", "d = b − پوشش − d_st − 0.5·d_ax",
             f"{b:.0f} − {mat.cover/10:.1f} − {tie_dia/10:.1f} − {0.5*bar_dia/10:.1f} = {d:.1f} cm"),
            ("Rn", "R_n = M_u1 / (φ·b·d²)", f"{rn:.4f} kg/cm²"),
            ("نسبت آرماتور", "ρ_reqd = 0.85f'c/fy·(1−√(1−2Rn/0.85f'c))  ،  ρ_min",
             f"ρ = {rho if rho else 0:.5f}  |  ρ_min = {rmin:.5f}  |  ρ_max = {rmax:.5f}"),
            ("آرماتور یک وجه", "A_s,face = (n/4 + 1)·A_b ≥ ρ·b·d",
             f"{as_face:.2f} ≥ {as_face_req:.2f} cm²"),
            ("آرماتور کل", f"ρg = A_st/(b·h) ≥ {min_ratio_g}",
             f"{as_tot:.2f}/({b:.0f}×{h:.0f}) = {as_tot/(b*h):.5f}"),
            ("فاصله میلگردها", "S_ext ≥ S_min = max(1.5d_b, 4 cm)", f"{s_ext:.1f} ≥ {s_min:.1f} cm"),
            ("خاموت", "(A_v/s)min = 3.5·b_w/f_y  ،  s_max = 0.5·d",
             f"Ф{tie_dia}@{tie_spacing:.0f} ≤ min({s_req:.1f} , {s_max:.1f}) cm"),
            ("انتخاب", f"{count}Ф{bar_dia}  ،  Ф{tie_dia}@{tie_spacing:.0f}",
             f"{count}×{a_bar} = {as_tot:.2f} cm²"),
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


def bar_count(width_cm, cover_cm, db_cm, smax_cm, rule="ceil"):
    """
    تعداد میلگرد در یک عرض.
    ceil  (دفترچه ۶۳): n = ⌈(W − 2c − d_b)/s_max⌉ + 1 — فاصله واقعی هرگز از s_max بیشتر نمی‌شود
    floor (نقشه کامی‌آباد): n = ⌊(W − 2c)/s_max⌋ + 1
    """
    if rule == "floor":
        return int((width_cm - 2 * cover_cm) // smax_cm) + 1
    return math.ceil(round((width_cm - 2 * cover_cm - db_cm) / smax_cm, 6)) + 1


def design_pad(res, geo, mat, n_ped, bar_dia=14, smax=200.0, rule="ceil"):
    """
    خمش پی در مقطع بر وجه ستون (مقطع A-A دفترچه)، با توزیع تنش نهایی خاک.
    شبکه در هر دو جهت، رو و زیر؛ تعداد میلگرد هر جهت از عرض همان جهت.
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
    a_bar = BAR_AREA[bar_dia]
    cov, db = mat.cover / 10, bar_dia / 10
    s = smax
    while True:
        n_L = bar_count(L, cov, db, s / 10, rule)       # میلگردهای توزیع‌شده در طول L
        n_B = bar_count(B, cov, db, s / 10, rule)       # میلگردهای توزیع‌شده در عرض B
        as_prov = n_L * a_bar
        if as_prov >= as_req or s <= 100:
            break
        s -= 25
    s_L = (L - 2 * cov - db) / (n_L - 1) * 10 if n_L > 1 else s
    s_B = (B - 2 * cov - db) / (n_B - 1) * 10 if n_B > 1 else s
    sd = SectionDesign(
        "آرماتور پی", mu, L, d, rho_used, rmin, rmax, as_req, bar_dia,
        spacing=s, bar_count=n_L, ok=ok and as_prov >= as_req,
        note="" if ok else "ضخامت پی برای خمش کافی نیست — t_f را زیاد کنید",
        steps=[
            ("توزیع تنش نهایی", "e = M_u / W_u  →  " +
             ("مثلثی، q_max = 2W_u/(3·L·m)" if P["triangular"] else "ذوزنقه‌ای"),
             f"e = {P['e']:.1f} cm ، طول ناحیه فشاری = {P['span']:.1f} cm ، "
             f"q_max = {P['q_max']:.3f} kg/cm²"),
            ("تنش در مقطع A-A", "q_A-A = (3m − l)/(3m)·q_max", f"{P['q_face']:.3f} kg/cm²"),
            ("طره", "l = (B − b)/2", f"({B:.0f}−{b:.0f})/2 = {c:.1f} cm"),
            ("لنگر", "M_u = [0.5·q_A-A·l² + ⅓·(q_max−q_A-A)·l²]·L", f"{mu/100:.0f} kg·m"),
            ("عمق مؤثر", "d = t_f − پوشش − ۱٫۵", f"{d:.1f} cm"),
            ("نسبت آرماتور", "ρ", f"{rho_used:.5f}  (ρ_min={rmin:.5f})"),
            ("سطح لازم", "A_s = ρ·L·d", f"{as_req:.1f} cm²"),
            ("تعداد", "n = ⌈(W − 2·cover − d_b)/s_max⌉ + 1" if rule == "ceil"
             else "n = ⌊(W − 2·cover)/s_max⌋ + 1",
             f"روی L: {n_L} عدد (فاصله {s_L/10:.1f} cm) ، روی B: {n_B} عدد (فاصله {s_B/10:.1f} cm)"),
            ("انتخاب", f"Ф{bar_dia}@{s:.0f}  در هر جهت، رو و زیر",
             f"A_s تأمین‌شده = {n_L}×{a_bar} = {as_prov:.2f} ≥ {as_req:.2f} cm²"),
        ])
    sd.n_L, sd.n_B, sd.s_L, sd.s_B = n_L, n_B, s_L, s_B
    return sd


def _shear_setup(res, geo, mat):
    """مقادیر مشترک برش (واحد ton و m مثل دفترچه ۶۳)."""
    d = geo.tf - mat.shear_offset / 1000                        # m
    fc = mat.fc * 10                                             # ton/m²
    P = (res.ultimate.Nmax + res.w_concrete + res.w_soil) / 1000  # ton
    pu = 1.4 * P
    qu = (pu / (geo.L * geo.B) - mat.gamma_s / 1000 * (geo.hp - mat.soil_cover)
          - mat.gamma_c / 1000 * geo.tf)
    return d, fc, P, pu, qu


def check_punching(res, geo, mat, n_ped):
    """
    برش دوطرفه — نشریه ۵۰۷ روابط ۳-۱۳ تا ۳-۱۵ (دفترچه ۶۳ صفحه ۱۷):
        V_c1 = (1 + 2/β)·√f'c/0.6·b₀·d
        V_c2 = (α·d/b₀ + 2)·√f'c/1.2·b₀·d        (α = 20)
        V_c3 = √f'c/0.3·b₀·d                    φ = 0.75
        P_u = 1.4·P ، q_u = P_u/(L·B) − γ_s·(h_p − h_e) − γ_c·t_f
    برش وارده هر ستون: q_u × (سهم سطح پی هر ستون − (b + d)²).
    """
    d, fc, P, pu, qu = _shear_setup(res, geo, mat)
    b = geo.b
    b0 = 4 * (b + d)
    beta, alpha = 1.0, 20.0
    vc1 = (1 + 2 / beta) * math.sqrt(fc) / 0.6 * b0 * d
    vc2 = (alpha * d / b0 + 2) * math.sqrt(fc) / 1.2 * b0 * d
    vc3 = math.sqrt(fc) / 0.3 * b0 * d
    phi_vc = PHI_SHEAR * min(vc1, vc2, vc3)
    vu = max(0.0, qu * (geo.L * geo.B / n_ped - (b + d) ** 2))
    sd = SectionDesign(
        "برش پانچ", 0, b0, d, 0, 0, 0, 0, 0, ok=vu <= phi_vc,
        note=f"{vu:.1f} ton ≤ {phi_vc:.1f} ton",
        steps=[
            ("عمق مؤثر و محیط", "b₀ = 4·(b + d)", f"d = {d:.2f} m ، b₀ = 4×({b:.2f}+{d:.2f}) = {b0:.2f} m"),
            ("V_c1", "(1 + 2/β)·√f'c/0.6·b₀·d", f"{vc1:.1f} ton"),
            ("V_c2", "(α·d/b₀ + 2)·√f'c/1.2·b₀·d  (α=20)", f"{vc2:.1f} ton"),
            ("V_c3", "√f'c/0.3·b₀·d", f"{vc3:.1f} ton"),
            ("مقاومت", "φV_c = 0.75·min(V_c1, V_c2, V_c3)", f"{phi_vc:.1f} ton"),
            ("بار نهایی", "P_u = 1.4·P ، q_u = P_u/(L·B) − γ_s(h_p−h_e) − γ_c·t_f",
             f"1.4×{P:.3f} = {pu:.2f} ton ، q_u = {qu:.3f} ton/m²"),
            ("برش وارده", "V_u = q_u·(L·B/n − (b+d)²)", f"{vu:.2f} ton"),
            ("نتیجه", "V_u < φV_c", f"{vu:.2f} < {phi_vc:.1f}"),
        ])
    sd.capacity = phi_vc * 1000
    sd.demand = vu * 1000
    return sd


def check_oneway(res, geo, mat, footprint):
    """
    برش یک‌طرفه — نشریه ۵۰۷ رابطه ۳-۱۶: V_c = √f'c/0.6·b·d ، در مقطع به فاصله d
    از بر ستون‌ها، در هر دو جهت؛ بدترین حالت گزارش می‌شود.
    """
    d, fc, P, pu, qu = _shear_setup(res, geo, mat)
    fx, fy = footprint
    rows = []
    for label, width, length, ext in (("راستای B", geo.L, geo.B, fy), ("راستای L", geo.B, geo.L, fx)):
        a = max(0.0, (length - ext) / 2 - d)
        vu = qu * width * a
        vc = PHI_SHEAR * math.sqrt(fc) / 0.6 * width * d
        rows.append((vu / vc if vc else 0, label, width, a, vu, vc))
    ratio, label, width, a, vu, vc = max(rows)
    sd = SectionDesign(
        "برش یک‌طرفه", 0, width, d, 0, 0, 0, 0, 0, ok=vu <= vc,
        note=f"{vu:.1f} ton ≤ {vc:.1f} ton",
        steps=[(f"{r[1]}", "a = (طول − عرض ستون‌ها)/2 − d ، V_u = q_u·b·a",
                f"a = {r[3]:.2f} m ، V_u = {r[4]:.2f} ton ، φV_c = {r[5]:.1f} ton") for r in rows]
        + [("نتیجه", "V_u < φV_c = 0.75·√f'c/0.6·b·d", f"{vu:.2f} < {vc:.1f}")])
    return sd


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


def design_anchor(u, eq, n_ped, geo, mat, anch, ped=None):
    """
    میل مهار به روش دفترچه ۶۳ (صفحه ۱۵ و ۱۶، مبحث نهم ۹-۱۸):
        T = M_u/(n_p·(0.5·n_ab)·d) − N_min/(n_p·n_ab)      V = V_u/(n_p·n_ab)
        A_se = π/4·(d_a − 0.9743/n_t)²
        φV_sa = 0.6·0.6·A_se·f_u      φN_sa = 0.65·A_se·f_u
        اگر هر دو بیش از ۲۰٪: V/φV_sa + T/φN_sa ≤ 1.2
        تنش ترکیبی: F'_nv = F_nv(1.3 − f_ut/φF_nt) ، F'_nt = F_nt(1.3 − f_uv/φF_nv)
        طول مهاری: L_d = 0.9·f_y/(λ√f'c)·ψ/((c+K_tr)/d_b)·d_b  (d_b قطر بدنه، مثلاً Ф22)
    طول مدفون = L_d گرد به بالا (پیش‌فرض ۱۰۰ mm).
    """
    n, da, g = max(eq.anchor_n, 1), eq.anchor_dia, eq.anchor_gauge / 1000
    t = (u.M / (n_ped * (0.5 * n) * g) - u.Nmin / (n_ped * n)) if g else 0.0
    t = max(t, 0.0)
    v = u.V / (n_ped * n)
    a_se = math.pi / 4 * (da - 0.9743 / anch.threads_per_mm) ** 2 / 100      # cm²
    phi_vsa = 0.6 * 0.6 * a_se * anch.fu
    phi_nsa = 0.65 * a_se * anch.fu
    both = v > 0.2 * phi_vsa and t > 0.2 * phi_nsa
    inter = v / phi_vsa + t / phi_nsa
    inter_ok = inter <= 1.2 if both else True
    ab = math.pi * da ** 2 / 4 / 100                                            # cm²
    fnv, fnt = 0.45 * anch.fu, 0.75 * anch.fu
    fuv, fut = v / ab, t / ab
    fnv_p = fnv * (1.3 - fut / (0.75 * fnt))
    fnt_p = fnt * (1.3 - fuv / (0.75 * fnv))
    comb_ok = fuv <= 0.75 * fnv_p and fut <= 0.75 * fnt_p
    steel_ok = v <= phi_vsa and t <= phi_nsa and inter_ok and comb_ok

    db = anch.rod_dia or da + 2
    ld = 0.9 * (anch.fy / 10) / math.sqrt(mat.fc / 10) / anch.cb_ktr * db
    embed = math.ceil(round(ld / anch.rounding, 6)) * anch.rounding
    available = (geo.hp + geo.tf) * 1000 - mat.cover - 2 * 14
    ok = steel_ok and embed <= available
    note = ""
    if embed > available:
        note = (f"طول مدفون لازم {embed:.0f} mm از عمق موجود {available:.0f} mm بیشتر است — "
                "h_p یا t_f را زیاد کنید")
    elif not steel_ok:
        note = "مقطع میل مهار برای کشش/برش کافی نیست — قطر یا تعداد را زیاد کنید"

    sd = SectionDesign(
        "میل مهار", 0, 0, 0, 0, 0, 0, 0, int(da), bar_count=n, ok=ok, note=note,
        steps=[
            ("نیروی کششی", "T = M_u/(n_p·(0.5·n_ab)·d) − N_min/(n_p·n_ab)",
             f"{u.M:.0f}/({n_ped}×0.5×{n}×{g:.2f}) − {u.Nmin:.0f}/({n_ped}×{n}) = {t:.0f} kg"),
            ("نیروی برشی", "V = V_u/(n_p·n_ab)", f"{u.V:.0f}/({n_ped}×{n}) = {v:.0f} kg"),
            ("سطح مؤثر", "A_se = π/4·(d_a − 0.9743/n_t)²",
             f"π/4×({da:.0f} − 0.9743/{anch.threads_per_mm})² = {a_se:.2f} cm²"),
            ("مقاومت برشی", "φV_sa = 0.6·0.6·A_se·f_u", f"{phi_vsa:.0f} kg  ≥ {v:.0f}"),
            ("مقاومت کششی", "φN_sa = 0.65·A_se·f_u", f"{phi_nsa:.0f} kg  ≥ {t:.0f}"),
            ("اندرکنش", "V/φV_sa + T/φN_sa ≤ 1.2", f"{inter:.2f}"),
            ("تنش ترکیبی", "f_uv ≤ 0.75·F'_nv ، f_ut ≤ 0.75·F'_nt",
             f"{fuv:.1f} ≤ {0.75*fnv_p:.0f} ، {fut:.1f} ≤ {0.75*fnt_p:.0f} kg/cm²"),
            ("طول مهاری", "L_d = 0.9·f_y/(λ√f'c)·ψ/((c+K_tr)/d_b)·d_b",
             f"0.9×{anch.fy/10:.0f}/√{mat.fc/10:.0f}/{anch.cb_ktr}×{db:.0f} = {ld:.0f} mm"),
            ("طول مدفون", f"گرد به {anch.rounding:.0f} mm",
             f"{embed:.0f} mm  (عمق موجود {available:.0f} mm)"),
        ])
    sd.embed, sd.tension, sd.shear = embed, t, v
    sd.a_se, sd.phi_nsa, sd.phi_vsa, sd.ld = a_se, phi_nsa, phi_vsa, ld
    return sd


def design_all(res, layout, mat, rebar=None, anchorage=None):
    """
    طراحی مقطع برای همه ستون‌ها و میل مهارهای هر گروه تجهیز، پی، و برش.
    خروجی "pedestal" و "anchor" بحرانی‌ترین گروه است؛ همه گروه‌ها در "groups".
    """
    from config import Anchorage, Rebar
    from padlayout import PadLayout
    from equipment import Equipment
    if isinstance(layout, Equipment):
        layout = PadLayout.single(layout)
    rebar = rebar or Rebar()
    anchorage = anchorage or Anchorage()
    geo = res.geometry
    forces = getattr(res, "group_forces", None) or [(res.governing, res.ultimate)]
    groups = []
    for grp, (g, u) in zip(layout.groups, forces):
        ped = design_pedestal(u.Nmax, u.V, u.M, geo, mat, grp.n, bar_dia=rebar.col_dia,
                              min_bars=rebar.col_min_bars, min_ratio_g=rebar.pedestal_min_ratio,
                              tie_dia=rebar.tie_dia, tie_spacing=rebar.tie_spacing)
        anc = design_anchor(u, grp.eq, grp.n, geo, mat, anchorage, ped)
        groups.append({"tag": grp.eq.tag, "pedestal": ped, "anchor": anc})
    pad = design_pad(res, geo, mat, layout.n_ped, bar_dia=rebar.pad_dia,
                     smax=rebar.pad_spacing_max, rule=rebar.pad_count_rule)
    punch = check_punching(res, geo, mat, layout.n_ped)
    oneway = check_oneway(res, geo, mat, layout.footprint(geo.b))
    out = {"pedestal": max((x["pedestal"] for x in groups), key=lambda p: p.bar_count),
           "pad": pad, "punching": punch, "oneway": oneway,
           "anchor": max((x["anchor"] for x in groups), key=lambda a: a.tension)}
    out["groups"] = groups
    return out
