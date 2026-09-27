"""
کنترل اعضای فولادی طبق AISC-ASD89 (مبنای مدل‌های SAP دفتر: Steel Design Code AISC-ASD89،
قاب مهاربندی‌شده).

برای هر عضو و هر ترکیب طراحی، در همه ایستگاه‌ها:
    محوری   fa = P/A ؛ کشش Ft = 0.60Fy (D1) ؛ فشار Fa از E2-1 / E2-2 با ضریب کاهش Q
            (پیوست B5) و لاغری KL/r — برای نبشی تکی r حداقل حول محور اصلی (rz)
    خمشی   fb = M/S ؛ ناودانی حول محور قوی: 0.66Fy فشرده، وگرنه کمانش جانبی F1-8
            (برای ناودانی فقط F1-8)؛ حول محور ضعیف 0.75Fy فشرده / 0.60Fy ؛ نبشی 0.60Fy·Q
    ترکیبی H1-1 و H1-2 (fa/Fa > 0.15)، H1-3 (fa/Fa ≤ 0.15)، H2-1 (کشش)
            Cm = 0.6 − 0.4·M1/M2 ≥ 0.4 (قاب مهاربندی‌شده)، F'e = 12π²E / 23(KL/r)²
    برشی   fv/Fv ، Fv = 0.40Fy
    لاغری  KL/r ≤ 200 (فشاری) و ≤ 300 (کششی) — B7

واحد ورودی kgf و m؛ روابطی که ضریب انگلیسی دارند با ksi حساب و برگردانده می‌شوند.
"""
import math
from dataclasses import dataclass, field

KSI = 7.0306958e5            # kgf/m² در یک ksi
INCH = 0.0254


@dataclass
class Check:
    member: str
    section: str
    combo: str = ""
    station: float = 0.0
    ratio: float = 0.0             # نسبت P-M حاکم
    shear_ratio: float = 0.0
    equation: str = ""
    P: float = 0.0
    M2: float = 0.0
    M3: float = 0.0
    fa: float = 0.0
    Fa: float = 0.0
    fb33: float = 0.0
    Fb33: float = 0.0
    fb22: float = 0.0
    Fb22: float = 0.0
    klr: float = 0.0
    klr_limit: float = 200.0
    Q: float = 1.0
    notes: list = field(default_factory=list)

    @property
    def governing(self):
        return max(self.ratio, self.shear_ratio, self.klr / self.klr_limit if self.klr else 0.0)

    @property
    def ok(self):
        return self.governing <= 1.0 + 1e-9

    def steps(self):
        """مراحل کنترل حاکم برای گزارش: (عنوان، رابطه، مقدار) — تنش‌ها بر حسب kg/cm²."""
        c = lambda v: f"{v / 1e4:,.0f} kg/cm²"
        out = [("نیروها", f"ترکیب {self.combo} — فاصله {self.station:.2f} m از سر عضو",
                 f"P = {self.P:,.0f} kg ({'فشار' if self.P < 0 else 'کشش'}) ، "
                 f"M3 = {self.M3:,.1f} ، M2 = {self.M2:,.1f} kg·m"),
               ("لاغری", "KL/r (نبشی تکی: r حداقل حول محور اصلی)",
                f"{self.klr:.0f} ≤ {self.klr_limit:.0f}"),
               ("تنش محوری", "fa = P/A", c(self.fa)),
               ("تنش مجاز محوری", "Fa (E2-1/E2-2 با Q)" if self.P < 0 else "Ft = 0.60 Fy",
                c(self.Fa) + (f" ، Q = {self.Q:.3f}" if self.Q < 1 else "")),
               ("تنش خمشی", "fb33 = M3/S33 ، fb22 = M2/S22",
                f"{c(self.fb33)} ، {c(self.fb22)}"),
               ("تنش مجاز خمشی", "Fb33 ، Fb22 (F1 / F2)", f"{c(self.Fb33)} ، {c(self.Fb22)}"),
               ("اندرکنش", self.equation, f"{self.ratio:.3f} ≤ 1.0"),
               ("برش", "fv / (0.40 Fy)", f"{self.shear_ratio:.3f}")]
        return out


def slender_q(sec, Fy):
    """ضریب کاهش Q برای اجزای لاغر (پیوست B5) — بال نبشی و بال ناودانی."""
    fy = Fy / KSI
    if sec.shape == "angle":
        bt = max(sec.t3 / sec.tw, sec.t2 / sec.tf)
        lo, hi = 76 / math.sqrt(fy), 155 / math.sqrt(fy)
        if bt <= lo:
            return 1.0
        if bt < hi:
            return 1.340 - 0.00447 * bt * math.sqrt(fy)
        return 15500 / (fy * bt * bt)
    bt = sec.t2 / sec.tf
    lo, hi = 95 / math.sqrt(fy), 176 / math.sqrt(fy)
    if bt <= lo:
        return 1.0
    if bt < hi:
        return 1.415 - 0.00437 * bt * math.sqrt(fy)
    return 20000 / (fy * bt * bt)


def allowable_compression(klr, Fy, E, Q=1.0):
    """E2-1 / E2-2 (با Q پیوست B5)."""
    Cc = math.sqrt(2 * math.pi ** 2 * E / (Q * Fy))
    if klr <= 0:
        return Q * Fy / (5 / 3)
    if klr <= Cc:
        fs = 5 / 3 + 3 / 8 * klr / Cc - klr ** 3 / (8 * Cc ** 3)
        return Q * (1 - klr ** 2 / (2 * Cc ** 2)) * Fy / fs
    return 12 * math.pi ** 2 * E / (23 * klr ** 2)


def allowable_bending(sec, Fy, Lb, Cb=1.0):
    """(Fb33، Fb22)"""
    fy = Fy / KSI
    if sec.shape == "angle":
        f = 0.60 * Fy * slender_q(sec, Fy)
        return f, f
    compact = sec.t2 / sec.tf <= 65 / math.sqrt(fy) and (sec.t3 - 2 * sec.tf) / sec.tw <= 640 / math.sqrt(fy)
    # حول محور ضعیف
    Fb22 = 0.75 * Fy if compact else 0.60 * Fy
    # حول محور قوی: فشرده و با مهار جانبی کافی 0.66Fy، وگرنه F1-8 (برای ناودانی تنها رابطه مجاز)
    Af = sec.t2 * sec.tf
    d_af = sec.t3 / Af                              # 1/m
    lc = min(76 * sec.t2 / math.sqrt(fy),
             20000 / (d_af * INCH * fy) * INCH)      # m
    if compact and Lb <= lc:
        Fb33 = 0.66 * Fy
    else:
        f18 = 12e3 * Cb / (Lb * d_af) * KSI if Lb > 0 else 0.60 * Fy
        Fb33 = min(0.60 * Fy, f18)
    return Fb33, Fb22


def _cm(m_a, m_b):
    """Cm = 0.6 − 0.4 M1/M2 ≥ 0.4 (M1/M2 مثبت برای خمش دوانحنایی)."""
    if abs(m_b) < 1e-9 and abs(m_a) < 1e-9:
        return 1.0
    m1, m2 = sorted((m_a, m_b), key=abs)
    ratio = -m1 / m2 if m2 else 0.0              # انحنای ساده: M1 و M2 هم‌علامت در علامت SAP
    return max(0.4, 0.6 - 0.4 * ratio)


def _cb(m_a, m_b, m_max):
    if abs(m_max) > max(abs(m_a), abs(m_b)) + 1e-9:
        return 1.0
    if abs(m_b) < 1e-9 and abs(m_a) < 1e-9:
        return 1.0
    m1, m2 = sorted((m_a, m_b), key=abs)
    r = -m1 / m2 if m2 else 0.0
    return min(2.3, 1.75 + 1.05 * r + 0.3 * r * r)


def check_member(name, sec, L, rows_by_combo, Fy, E, k33=1.0, k22=1.0, l33=1.0, l22=1.0):
    """
    rows_by_combo: {ترکیب: [(s, P, V2, V3, T, M2, M3)]} — خروجی frame.Results.forces
    L: طول عضو؛ l33/l22 ضریب طول مهارنشده (SAP: XLMajor/XLMinor)، k33/k22 ضریب طول مؤثر.
    """
    A = sec.A
    Q = slender_q(sec, Fy)
    if sec.shape == "angle":
        r33 = r22 = sec.rz                          # نبشی تکی: شعاع ژیراسیون حداقل
    else:
        r33, r22 = sec.r33, sec.r22
    kl33, kl22 = k33 * l33 * L, k22 * l22 * L
    klr33, klr22 = kl33 / r33, kl22 / r22
    klr = max(klr33, klr22)
    Fa = allowable_compression(klr, Fy, E, Q)
    Ft = 0.60 * Fy
    Fe33 = 12 * math.pi ** 2 * E / (23 * klr33 ** 2) if klr33 else float("inf")
    Fe22 = 12 * math.pi ** 2 * E / (23 * klr22 ** 2) if klr22 else float("inf")
    Fv = 0.40 * Fy
    if sec.shape == "angle":
        Av2, Av3 = sec.t3 * sec.tw, sec.t2 * sec.tf
    else:
        Av2, Av3 = sec.AS2, sec.AS3

    best = Check(name, sec.name, Q=Q, klr=klr)
    comp_seen = False
    for combo, rows in rows_by_combo.items():
        M3s = [r[6] for r in rows]
        M2s = [r[5] for r in rows]
        Cm33, Cm22 = _cm(M3s[0], M3s[-1]), _cm(M2s[0], M2s[-1])
        Cb = _cb(M3s[0], M3s[-1], max(M3s, key=abs))
        Fb33, Fb22 = allowable_bending(sec, Fy, l33 * L, Cb)
        for s, P, V2, V3, T, M2, M3 in rows:
            fa = abs(P) / A
            fb33, fb22 = abs(M3) / sec.S33, abs(M2) / sec.S22
            if P < 0:                                   # فشار
                comp_seen = comp_seen or fa > 1e-6
                if fa / Fa > 0.15:
                    h11 = (fa / Fa + Cm33 * fb33 / ((1 - fa / Fe33) * Fb33)
                           + Cm22 * fb22 / ((1 - fa / Fe22) * Fb22))
                    h12 = fa / (0.60 * Fy) + fb33 / Fb33 + fb22 / Fb22
                    ratio, eq = (h11, "H1-1") if h11 >= h12 else (h12, "H1-2")
                    if fa >= Fe33 or fa >= Fe22:
                        ratio, eq = float("inf"), "F'e"
                else:
                    ratio, eq = fa / Fa + fb33 / Fb33 + fb22 / Fb22, "H1-3"
                Fall = Fa
            else:
                ratio, eq = fa / Ft + fb33 / Fb33 + fb22 / Fb22, "H2-1"
                Fall = Ft
            vr = max(abs(V2) / Av2, abs(V3) / Av3) / Fv
            if vr > best.shear_ratio:
                best.shear_ratio = vr
            if ratio > best.ratio:
                best.ratio, best.equation, best.combo, best.station = ratio, eq, combo, s
                best.P, best.M2, best.M3 = P, M2, M3
                best.fa, best.Fa = fa, Fall
                best.fb33, best.Fb33, best.fb22, best.Fb22 = fb33, Fb33, fb22, Fb22
    best.klr_limit = 200.0 if comp_seen else 300.0
    if best.klr > best.klr_limit:
        best.notes.append(f"KL/r = {best.klr:.0f} از حد {best.klr_limit:.0f} (بند B7) بیشتر است")
    return best


def design(model, results, combos=None, Fy=None):
    """کنترل همه اعضا؛ خروجی {عضو: Check} و ترکیب‌های به‌کاررفته."""
    import math as _m
    combos = combos or [c for c in model.combos if getattr(model, "design_combos", None) is None
                        or c in model.design_combos]
    out = {}
    for m in model.members:
        L = _m.dist(model.nodes[m.i], model.nodes[m.j])
        rows = {c: results.forces[c][m.name] for c in combos}
        fy = Fy or getattr(m.section, "fy", None) or 2.4e7
        out[m.name] = check_member(m.name, m.section, L, rows, fy, model.E,
                                   m.k_major, m.k_minor, getattr(m, "l_major", 1.0),
                                   getattr(m, "l_minor", 1.0))
    return out
