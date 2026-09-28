"""
شکل سه‌بعدی تجهیز روی سازه — پارامتری از داده خود تجهیز، نه مدل آماده:

    ارتفاع کل He، پهنای متوسط از سطح بادگیر (Ae / He)، نوع تجهیز
    ستون مقره با بشقابک‌ها (Sheds)، مخزن پایه CT و CVT، سر CT، قاب و تیغه سکسیونر،
    جعبه مکانیزم و محفظه قطع کلید قدرت، ترمینال هادی در ارتفاع واقعی اتصال.

هر جزء یک «اولیه» است: استوانه {p, q, r} یا منشور {p, q, e2, e3, profile} (mm) با
گروه رنگ (porcelain، metal، tank، terminal)؛ نمای مرورگر و مدل سه‌بعدی اتوکد هر دو از
همین فهرست ساخته می‌شوند.
"""
import math

from equipment import equipment_type


def _cyl(p, q, r, group):
    return {"t": "cyl", "p": [round(v, 1) for v in p], "q": [round(v, 1) for v in q],
            "r": round(r, 1), "g": group}


def _box(p, q, w, d, ang, group):
    """منشور مستطیلی از p تا q (محور)، پهنای w در امتداد X چرخیده و d عمود بر آن."""
    c, s = math.cos(ang), math.sin(ang)
    e2, e3 = (c, s, 0.0), (-s, c, 0.0)
    if abs(q[0] - p[0]) + abs(q[1] - p[1]) > 1e-6:          # افقی: محور در امتداد X چرخیده
        e2, e3 = (0.0, 0.0, 1.0), (-s, c, 0.0)
    prof = [[[-w / 2, -d / 2], [w / 2, -d / 2], [w / 2, d / 2], [-w / 2, d / 2]]]
    return {"t": "box", "p": [round(v, 1) for v in p], "q": [round(v, 1) for v in q],
            "e2": e2, "e3": e3, "profile": prof, "g": group}


def _column(x, y, z0, z1, core, shed, out, group="porcelain"):
    """ستون مقره: هسته + بشقابک‌ها با فاصله حدود ۶ سانت (حداکثر ۳۶ بشقابک)."""
    out.append(_cyl((x, y, z0), (x, y, z1), core, group))
    h = z1 - z0
    n = max(3, min(36, int(h / 60)))
    for k in range(n):
        z = z0 + h * (k + 0.5) / n
        out.append(_cyl((x, y, z - 6), (x, y, z + 6), shed, group))


def build(eq, base, ang=0.0):
    """
    اولیه‌های یک فاز تجهیز با پای base (mm) و زاویه سازه ang (رادیان).
    """
    t = equipment_type(eq.tag)
    He = eq.He * 1000
    w = min(800.0, max(120.0, eq.Ae / max(eq.He, 0.1) * 1000))
    x, y, z = base
    c, s = math.cos(ang), math.sin(ang)
    X = lambda dx, dy=0.0: (x + c * dx - s * dy, y + s * dx + c * dy)
    out = []
    out.append(_box((x, y, z), (x, y, z + 20), w * 1.1, w * 1.1, ang, "metal"))      # صفحه پایه
    z0 = z + 20
    if t in ("LA", "PI"):
        _column(x, y, z0, z + He * 0.94, w * 0.26, w * 0.46, out)
        out.append(_cyl((x, y, z + He * 0.94), (x, y, z + He), w * 0.30, "metal"))
        if t == "LA":                                            # حلقه یکنواخت‌کننده ولتاژ
            out.append(_cyl((x, y, z + He * 0.90), (x, y, z + He * 0.905), w * 1.1, "metal"))
    elif t in ("CT", "CVT", "CVT1"):
        tank = He * (0.28 if t == "CT" else 0.24)
        if t == "CT":
            out.append(_cyl((x, y, z0), (x, y, z0 + tank), w * 0.5, "tank"))
        else:
            out.append(_box((x, y, z0), (x, y, z0 + tank), w * 1.0, w * 0.9, ang, "tank"))
        top = He * (0.80 if t == "CT" else 0.95)
        _column(x, y, z0 + tank, z + top, w * 0.22, w * 0.40, out)
        if t == "CT":                                            # سر CT: استوانه افقی
            (ax, ay), (bx, by) = X(-w * 0.6), X(w * 0.6)
            out.append(_cyl((ax, ay, z + top + (He - top) / 2), (bx, by, z + top + (He - top) / 2),
                            (He - top) / 2, "tank"))
        else:
            out.append(_cyl((x, y, z + top), (x, y, z + He), w * 0.20, "metal"))
    elif t in ("DS", "DSE", "DS2", "DSROW"):
        span = max(600.0, min(1400.0, He * 0.55))
        out.append(_box((X(-span / 2 - 80)[0], X(-span / 2 - 80)[1], z0 + 60),
                        (X(span / 2 + 80)[0], X(span / 2 + 80)[1], z0 + 60), 120, 160, ang, "metal"))
        for dx in (-span / 2, span / 2):
            px, py = X(dx)
            _column(px, py, z0 + 120, z + He * 0.82, w * 0.20, w * 0.36, out)
            out.append(_cyl((px, py, z + He * 0.82), (px, py, z + He * 0.86), w * 0.26, "metal"))
        (ax, ay), (bx, by) = X(-span / 2), X(span / 2)
        out.append(_box((ax, ay, z + He * 0.88), (bx, by, z + He * 0.88), 40, 60, ang, "terminal"))
        if t == "DSE":                                           # تیغه زمین
            (ex, ey) = X(span / 2 + 120)
            out.append(_box((ex, ey, z0 + 120), (ex, ey, z + He * 0.55), 30, 30, ang, "metal"))
    elif t == "CB":
        out.append(_box((x, y, z0), (x, y, z0 + He * 0.18), w * 1.2, w * 1.0, ang, "tank"))
        _column(x, y, z0 + He * 0.18, z + He * 0.55, w * 0.25, w * 0.42, out)
        out.append(_cyl((x, y, z + He * 0.55), (x, y, z + He * 0.95), w * 0.34, "tank"))
        out.append(_cyl((x, y, z + He * 0.95), (x, y, z + He), w * 0.22, "metal"))
    else:
        _column(x, y, z0, z + He, w * 0.25, w * 0.42, out)
    # ترمینال هادی در ارتفاع واقعی اتصال
    for h in eq.conductor_points:
        hz = z + h * 1000
        (ax, ay), (bx, by) = X(-w * 0.35), X(w * 0.35)
        out.append(_cyl((ax, ay, hz), (bx, by, hz), 18, "terminal"))
    return out


def for_design(eq, design, pedestals, base_z):
    """همه فازهای تجهیز روی سازه طراحی‌شده."""
    from .placement import phase_bases
    prims = []
    for pt, ang in phase_bases(design, pedestals, base_z):
        prims += build(eq, pt, ang)
    return prims


def for_stand(eq, pedestals, base_z, pitch=1.5):
    """
    تجهیزی که سازه‌اش را سازنده می‌دهد (یا طراحی سازه خاموش است): استراکچر به شکل
    ساده (ستون روی هر ستون بتنی و تیر سرِ آن‌ها) به ارتفاع Hs، و تجهیز روی آن.
    """
    peds = sorted(pedestals)
    if not peds:
        return []
    Hs = eq.Hs * 1000
    top = base_z + Hs
    out = []
    for x, y in peds:
        out.append(_box((x, y, base_z), (x, y, top), 300, 300, 0.0, "metal"))
    (x0, y0), (x1, y1) = peds[0], peds[-1]
    ang = math.atan2(y1 - y0, x1 - x0) if len(peds) > 1 else 0.0
    if eq.npol > 1 and eq.npol == len(peds):
        bases = [(x, y, top) for x, y in peds]
    else:
        cx = sum(x for x, _ in peds) / len(peds)
        cy = sum(y for _, y in peds) / len(peds)
        c, s = math.cos(ang), math.sin(ang)
        d = pitch * 1000
        bases = [(cx + c * d * (k - (eq.npol - 1) / 2), cy + s * d * (k - (eq.npol - 1) / 2), top)
                 for k in range(eq.npol)]
        ends = [b[:2] for b in bases] + peds
        u = [(px - cx) * c + (py - cy) * s for px, py in ends]
        if max(u) - min(u) > 1:                                  # تیر سر ستون‌ها زیر همه فازها
            a = (cx + c * (min(u) - 150), cy + s * (min(u) - 150), top - 100)
            b = (cx + c * (max(u) + 150), cy + s * (max(u) + 150), top - 100)
            out.append(_box(a, b, 200, 100, ang, "metal"))
    for b in bases:
        out += build(eq, b, ang)
    return out
