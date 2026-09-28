"""
سازه طراحی‌شده روی ستون‌های بتنی: هر پایه مشبک روی مرکز یک ستون، پای سازه روی
صفحه کف. خروجی اعضا با مقطع واقعی برای مدل سه‌بعدی و نمای مرورگر (mm).

محورهای محلی همان محورهای تحلیل (frame.local_axes)؛ نبشی‌های اصلی پایه مثل ساخت:
پاشنه رو به بیرون، بال‌ها رو به داخل.
"""
import math
from dataclasses import dataclass

from .frame import local_axes


@dataclass
class Placed:
    p: tuple
    q: tuple
    e2: tuple
    e3: tuple
    profile: list          # [چندضلعی‌ها] در صفحه (۲، ۳)، mm
    group: str
    section: str
    ratio: float
    member: str


def _centroid(poly):
    a = cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1]):
        c = x0 * y1 - x1 * y0
        a += c
        cx += (x0 + x1) * c
        cy += (y0 + y1) * c
    return cx / (3 * a), cy / (3 * a)


def _ccw(poly):
    a = sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1]))
    return poly if a > 0 else poly[::-1]


def profile(sec, heel_on_axis=False):
    h, b, tf, tw = sec.t3 * 1000, sec.t2 * 1000, sec.tf * 1000, sec.tw * 1000
    if sec.shape == "angle":
        poly = [(0, 0), (h, 0), (h, tw), (tf, tw), (tf, b), (0, b)]
        if not heel_on_axis:
            c = _centroid(poly)
            poly = [(x - c[0], y - c[1]) for x, y in poly]
        return [_ccw(poly)]
    ch = [(-h / 2, 0), (h / 2, 0), (h / 2, b), (h / 2 - tf, b), (h / 2 - tf, tw),
          (-h / 2 + tf, tw), (-h / 2 + tf, b), (-h / 2, b)]
    if sec.shape == "channel":
        c = _centroid(ch)
        return [_ccw([(x - c[0], y - c[1]) for x, y in ch])]
    g = sec.dis * 1000 / 2
    return [_ccw([(x, y + g) for x, y in ch]), _ccw([(x, -y - g) for x, y in ch])]


def _frames(design, pedestals, base_z):
    """تبدیل مختصات سازه (m) به مختصات پی (mm) برای هر نسخه سازه: [(T، R، زاویه)]."""
    model = design.model
    peds = sorted(pedestals)
    targets = [[p] for p in peds] if design.stands > 1 else [peds]
    lc = [(c * 1000, 0.0) for c in model.leg_centres]
    out = []
    for tgt in targets:
        if len(tgt) != len(lc):
            continue
        a_p = math.atan2(tgt[-1][1] - tgt[0][1], tgt[-1][0] - tgt[0][0]) if len(tgt) > 1 else 0.0
        c, s = math.cos(a_p), math.sin(a_p)
        tx = sum(x for x, _ in tgt) / len(tgt)
        ty = sum(y for _, y in tgt) / len(tgt)

        def T(pt, c=c, s=s, tx=tx, ty=ty):
            x, y, z = pt[0] * 1000, pt[1] * 1000, pt[2] * 1000
            return (tx + c * x - s * y, ty + s * x + c * y, base_z + z)

        def R(v, c=c, s=s):
            return (c * v[0] - s * v[1], s * v[0] + c * v[1], v[2])
        out.append((T, R, a_p))
    return out


def place(design, pedestals, base_z):
    """
    design: StructureDesign ؛ pedestals: [(x, y)] مرکز ستون‌های همین تجهیز (mm)
    base_z: تراز زیر پای سازه (mm). خروجی: [Placed]
    """
    model = design.model
    out = []
    for T, R, _ in _frames(design, pedestals, base_z):
        for m in model.members:
            a, b = model.nodes[m.i], model.nodes[m.j]
            ax, _ = local_axes(a, b, m.angle)
            e2, e3 = tuple(ax[1]), tuple(ax[2])
            if m.group == "chord":
                cx = min(model.leg_centres, key=lambda v: abs(v - a[0]))
                e2 = (math.copysign(1, cx - a[0]), 0.0, 0.0)
                e3 = (0.0, math.copysign(1, -a[1]), 0.0)
                prof = profile(m.section, heel_on_axis=True)
            else:
                prof = profile(m.section)
            ratio = design.checks[m.name].governing
            out.append(Placed(T(a), T(b), R(e2), R(e3), prof, m.group, m.section.name,
                              ratio, m.name))
    return out


def phase_bases(design, pedestals, base_z):
    """پای هر فاز تجهیز روی سازه (mm) و زاویه سازه: [(نقطه، زاویه)]."""
    model = design.model
    out = []
    for T, _, ang in _frames(design, pedestals, base_z):
        for nodes in model.load_points:
            pts = [model.nodes[n] for n in nodes]
            mid = tuple(sum(p[k] for p in pts) / len(pts) for k in range(3))
            out.append((T(mid), ang))
    return out


def section_points(pm, at):
    return [[tuple(at[k] + u * pm.e2[k] + v * pm.e3[k] for k in range(3)) for u, v in poly]
            for poly in pm.profile]


def ratio_color(r):
    """سبز (کم‌تنش) ← زرد ← قرمز (نزدیک ۱ یا بیشتر)."""
    r = max(0.0, min(1.2, r)) / 1.2
    stops = [(0.0, (46, 125, 80)), (0.55, (214, 170, 40)), (0.83, (214, 90, 40)), (1.0, (170, 30, 30))]
    for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
        if r <= t1:
            k = (r - t0) / (t1 - t0)
            return tuple(int(c0[i] + (c1[i] - c0[i]) * k) for i in range(3))
    return stops[-1][1]


__all__ = ["place", "Placed", "section_points", "ratio_color"]
