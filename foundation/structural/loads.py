"""
بارگذاری سازه نگهدارنده — از همان داده تجهیز و همان پنج حالت بار فونداسیون
(engine.build_cases)، تا سازه و پی از یک محاسبه بیایند:

    DEAD   وزن اعضا + وزن تجهیز و هادی هر فاز روی نقاط نصب
    H1..H5 بار افقی هر حالت در امتداد Y: کشش هادی، باد یا زلزله تجهیز در ارتفاع خودش
           (نیروی افقی + زوج‌نیروی قائم روی دو تیر، مثل مدل‌های دفتر)، و باد یا زلزله
           خود سازه روی تک‌تک اعضا
    EV     واحد زلزله قائم (همه وزن‌ها رو به بالا) — در ترکیب با ضریب ±Cv
    EX     زلزله در امتداد X (عمود بر امتداد اصلی) — مثل COMB7/8 دفتر
    N, LIVE کشش هادی بدون باد + بار نفر هنگام تعمیر (مثل COMB6 دفتر)

ترکیب‌ها (تنش مجاز، بدون ضریب): C1..C3 = DEAD + Hk ؛ C4±، C5± = DEAD + Hk ∓ Cv·EV ؛
CX± = DEAD + EX ∓ Cv·EV ؛ C6 = DEAD + N + LIVE.
"""
from .frame import Pattern
from .lattice import projected_width


def _apply(pat, nodes, coords, F, arm, axis):
    """
    نیروی افقی F (در امتداد axis: 0=X، 1=Y) با بازوی arm بالای نقاط نصب:
    F بین نقاط تقسیم می‌شود و لنگر F·arm با زوج‌نیروی قائم (یا اگر نقاط در آن امتداد
    فاصله ندارند، با لنگر گرهی).
    """
    n = len(nodes)
    c = [coords[k][axis] for k in nodes]
    mean = sum(c) / n
    s2 = sum((v - mean) ** 2 for v in c)
    for k, v in zip(nodes, c):
        f = [0.0] * 6
        f[axis] = F / n
        if s2 > 1e-12:
            # Y: M_x = −F·h = Σ y·fz  ؛  X: M_y = F·h = −Σ x·fz ← در هر دو fz = −F·h·(c − c̄)/Σ
            f[2] = -F * arm * (v - mean) / s2
        else:
            f[3 + (1 - axis)] = (-F * arm if axis == 1 else F * arm) / n
        pat.joint.append((k, tuple(f)))


def apply_loads(model, eq, wind, ch, cv, eq_sc=0.6, live=100.0):
    """الگوها و ترکیب‌ها را روی مدل می‌گذارد؛ خلاصه‌ای از بارها برمی‌گرداند."""
    from engine import build_cases
    cases = build_cases(eq, wind, ch, cv, eq_sc)
    pts = model.load_points
    coords = model.nodes
    per_phase = eq.npol / max(1, len(pts))           # فاز روی هر گروه نقاط (معمولاً ۱)
    arms_c = sum(eq.conductor_points)                # engine: M = Σ Fc·(Hs + h)
    pats = {}

    dead = Pattern(self_weight=1.0)
    for ph in pts:
        w = (eq.We + eq.Wc) * per_phase
        for k in ph:
            dead.joint.append((k, (0, 0, -w / len(ph), 0, 0, 0)))
    pats["DEAD"] = dead

    widths = {m.name: projected_width(m, model) for m in model.members}
    area = sum(w * L for w, L in widths.values())
    q = {1: wind.q_normal, 2: wind.q_high, 3: wind.q_sc}
    for lc in cases:
        k = lc["no"]
        p = Pattern()
        for ph in pts:
            _apply(p, ph, coords, lc["Fc"] * per_phase, arms_c, 1)
            _apply(p, ph, coords, lc["Fe"] * per_phase, eq.he, 1)
        if k in q:                                   # باد روی اعضا
            for m in model.members:
                w, _ = widths[m.name]
                if w > 0:
                    p.uniform.append((m.name, "Y", q[k] * eq.Cs * w))
        else:                                        # زلزله: ضریب × وزن اعضا
            f = ch * (eq_sc if k == 5 else 1.0)
            p.gravity = [(m.name, (0.0, f, 0.0)) for m in model.members]
        pats[f"H{k}"] = p

    ev = Pattern(gravity=[(m.name, (0.0, 0.0, 1.0)) for m in model.members])
    for ph in pts:
        w = (eq.We + eq.Wc) * per_phase
        for k in ph:
            ev.joint.append((k, (0, 0, w / len(ph), 0, 0, 0)))
    pats["EV"] = ev

    ex = Pattern(gravity=[(m.name, (ch, 0.0, 0.0)) for m in model.members])
    for ph in pts:
        _apply(ex, ph, coords, ch * eq.We * per_phase, eq.he, 0)
    pats["EX"] = ex

    n = Pattern()
    for ph in pts:
        _apply(n, ph, coords, eq.Fc * per_phase, arms_c, 1)
    pats["N"] = n
    mid = pts[len(pts) // 2]
    pats["LIVE"] = Pattern(joint=[(k, (0, 0, -live / len(mid), 0, 0, 0)) for k in mid])

    combos = {"C1": [(1, "DEAD"), (1, "H1")], "C2": [(1, "DEAD"), (1, "H2")],
              "C3": [(1, "DEAD"), (1, "H3")],
              "C4+": [(1, "DEAD"), (1, "H4"), (-cv, "EV")], "C4-": [(1, "DEAD"), (1, "H4"), (cv, "EV")],
              "C5+": [(1, "DEAD"), (1, "H5"), (-cv * eq_sc, "EV")],
              "C5-": [(1, "DEAD"), (1, "H5"), (cv * eq_sc, "EV")],
              "CX+": [(1, "DEAD"), (1, "EX"), (-cv, "EV")], "CX-": [(1, "DEAD"), (1, "EX"), (cv, "EV")],
              "C6": [(1, "DEAD"), (1, "N"), (1, "LIVE")]}
    model.patterns, model.combos = pats, combos
    model.design_combos = list(combos)
    return {"wind_area": area, "cases": cases}


def load_table(eq, wind, ch, cv, eq_sc, live, self_weight, wind_area, phases):
    """
    بارهای واردشده به سازه در هر ترکیب — همان بارهایی که apply_loads روی مدل می‌گذارد، به زبان
    مهندسی برای نمایش: برای هر فاز بار قائم و افقی (هادی + تجهیز) و روی خود سازه باد یا زلزله.
    """
    from engine import build_cases
    cs = {c["no"]: c for c in build_cases(eq, wind, ch, cv, eq_sc)}
    per = (eq.We + eq.Wc)
    q = {1: wind.q_normal, 2: wind.q_high, 3: wind.q_sc}
    rows = []

    def row(cid, V, Hc, He, direction, Hs, live_kg=0.0):
        rows.append({"id": cid, "title": COMBO_TITLES[cid], "V": round(V, 1), "Hc": round(Hc, 1),
                     "He": round(He, 1), "H": round(Hc + He, 1), "dir": direction,
                     "Hs": round(Hs, 1), "live": live_kg})
    for k in (1, 2, 3):
        c = cs[k]
        row(f"C{k}", per, c["Fc"], c["Fe"], "Y", q[k] * eq.Cs * wind_area)
    for k, cid in ((4, "C4"), (5, "C5")):
        c = cs[k]
        f = 1.0 if k == 4 else eq_sc
        row(cid + "+", per * (1 + cv * f), c["Fc"], c["Fe"], "Y", ch * f * self_weight)
        row(cid + "-", per * (1 - cv * f), c["Fc"], c["Fe"], "Y", ch * f * self_weight)
    row("CX+", per * (1 + cv), 0.0, ch * eq.We, "X", ch * self_weight)
    row("CX-", per * (1 - cv), 0.0, ch * eq.We, "X", ch * self_weight)
    row("C6", per, eq.Fc, 0.0, "Y", 0.0, live)
    return {"phases": phases, "We": eq.We, "Wc": eq.Wc, "Fc": eq.Fc, "Fc_sc": eq.Fc_sc,
            "He": eq.He, "he": eq.he, "conductor_points": list(eq.conductor_points),
            "Ae": eq.Ae, "Ce": eq.Ce, "Cs": eq.Cs, "ch": round(ch, 4), "cv": round(cv, 4),
            "self_weight": round(self_weight, 1), "wind_area": round(wind_area, 3),
            "q": {k: round(v, 1) for k, v in q.items()}, "combos": rows}


COMBO_TITLES = {
    "C1": "۱ — یخ + باد نرمال", "C2": "۲ — باد شدید", "C3": "۳ — باد شدید + اتصال کوتاه",
    "C4+": "۴ — زلزله، قائم رو به پایین", "C4-": "۴ — زلزله، قائم رو به بالا",
    "C5+": "۵ — زلزله + اتصال کوتاه، قائم رو به پایین",
    "C5-": "۵ — زلزله + اتصال کوتاه، قائم رو به بالا",
    "CX+": "زلزله عمود (X)، قائم رو به پایین", "CX-": "زلزله عمود (X)، قائم رو به بالا",
    "C6": "هادی + بار نفر (تعمیر)",
}
