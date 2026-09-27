"""
سازه فولادی روی فونداسیون — از مدل SAP2000 کتابخانه (structures/).

هر تجهیز کاتالوگ می‌تواند فایل .s2k سازه‌اش را داشته باشد (Equipment.structure).
سازه طوری روی ستون‌های بتنی گذاشته می‌شود که مرکز هر پایه مشبک روی مرکز یک
ستون بنشیند و پای سازه روی صفحه کف باشد. سازه تک‌پایه (مثل CVT تک‌فاز) روی
هر ستون گروه یک نسخه می‌گیرد.

محورهای محلی عضو مطابق قاعده پیش‌فرض SAP (مدل‌های دفتر محور محلی سفارشی ندارند):
    ۱  در امتداد عضو از I به J
    ۲  عضو قائم: +X ؛ بقیه: در صفحه قائم گذرنده از عضو، رو به بالا
    ۳  = ۱ × ۲
نبشی‌های اصلی پایه‌ها (قائم، روی گوشه پایه) مثل ساخت واقعی قرار می‌گیرند: پاشنه
رو به بیرون، بال‌ها رو به داخل پایه.
"""
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from sap2000 import read_structure

LIBRARY = Path(__file__).resolve().parent / "structures"


@dataclass
class Member:
    p: tuple              # سر I (mm، مختصات پی)
    q: tuple              # سر J
    section: object       # sap2000.Section
    e2: tuple             # محور محلی ۲ (بردار یکه)
    e3: tuple             # محور محلی ۳
    profile: list         # چندضلعی مقطع در صفحه (۲، ۳) بر حسب mm، پادساعتگرد
    kind: str             # chord | brace | beam

    @property
    def length(self):
        return math.dist(self.p, self.q)


@lru_cache(maxsize=None)
def load(rel):
    """سازه از کتابخانه؛ مسیری که از پوشه structures بیرون برود پذیرفته نمی‌شود."""
    path = (LIBRARY / rel).resolve()
    if path.suffix.lower() != ".s2k" or LIBRARY.resolve() not in path.parents:
        return None
    return read_structure(path) if path.is_file() else None


def structure_for(eq):
    return load(eq.structure) if getattr(eq, "structure", "") else None


# ---------------------------------------------------------------- هندسه
def _sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def _norm(v):
    n = math.sqrt(sum(c * c for c in v))
    return tuple(c / n for c in v)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def local_axes(p, q):
    e1 = _norm(_sub(q, p))
    if abs(e1[2]) > 0.999:
        e2 = (1.0, 0.0, 0.0)
    else:
        z = (0.0, 0.0, 1.0)
        e2 = _norm(_sub(z, tuple(_dot(z, e1) * c for c in e1)))
    return e1, e2, _cross(e1, e2)


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
    """چندضلعی مقطع (mm) در صفحه (محور ۲، محور ۳)."""
    h, b, tf, tw = sec.t3 * 1000, sec.t2 * 1000, sec.tf * 1000, sec.tw * 1000
    shape = sec.shape.lower()
    if shape == "angle":
        poly = [(0, 0), (h, 0), (h, tw), (tf, tw), (tf, b), (0, b)]
        if not heel_on_axis:
            c = _centroid(poly)
            poly = [(x - c[0], y - c[1]) for x, y in poly]
        return _ccw(poly)
    if shape in ("channel", "double channel"):
        # جان در امتداد ۲ (ارتفاع h)، بال‌ها رو به +۳
        ch = [(-h / 2, 0), (h / 2, 0), (h / 2, b), (h / 2 - tf, b), (h / 2 - tf, tw),
              (-h / 2 + tf, tw), (-h / 2 + tf, b), (-h / 2, b)]
        if shape == "channel":
            c = _centroid(ch)
            return [_ccw([(x - c[0], y - c[1]) for x, y in ch])]
        g = sec.dis * 1000 / 2          # دو ناودانی پشت به پشت
        right = [(x, y + g) for x, y in ch]
        left = [(x, -y - g) for x, y in ch]
        return [_ccw(right), _ccw(left)]
    # مقطع ناشناخته: مستطیل پر
    return _ccw([(-h / 2, -b / 2), (h / 2, -b / 2), (h / 2, b / 2), (-h / 2, b / 2)])


def _parts(prof):
    """profile ممکن است یک چندضلعی یا فهرست چندضلعی (دوبل) باشد."""
    return prof if prof and isinstance(prof[0], list) else [prof]


# ---------------------------------------------------------------- جای‌گذاری
def place(st, peds, base_z):
    """
    اعضای سازه در مختصات پی (mm).
    peds: [(x, y)] مرکز ستون‌های همین تجهیز (mm)؛ base_z: تراز زیر پای سازه (mm).
    خروجی: (اعضا، هشدارها)
    """
    legs = st.legs()
    warn = []
    peds = sorted(peds)
    if len(legs) == 1:
        targets = [[p] for p in peds]                    # یک نسخه روی هر ستون
    elif len(legs) == len(peds):
        targets = [peds]
    else:
        return [], [f"سازه {st.name} {len(legs)} پایه دارد ولی تجهیز {len(peds)} ستون؛ "
                    "سازه در مدل گذاشته نشد."]

    zmin = min(st.joints[s][2] for s in st.supports)
    lc = [(cx * 1000, cy * 1000) for cx, cy, _ in legs]
    members = []
    for tgt in targets:
        # چرخش: امتداد پایه‌های سازه ← امتداد ستون‌ها
        if len(tgt) > 1:
            a_s = math.atan2(lc[-1][1] - lc[0][1], lc[-1][0] - lc[0][0])
            a_p = math.atan2(tgt[-1][1] - tgt[0][1], tgt[-1][0] - tgt[0][0])
            sp_s = math.dist(lc[0], lc[-1]) / (len(lc) - 1)
            sp_p = math.dist(tgt[0], tgt[-1]) / (len(tgt) - 1)
            if abs(sp_s - sp_p) > 20:
                warn.append(f"فاصله پایه‌های سازه {st.name} ({sp_s:.0f} mm) با فاصله ستون‌ها "
                            f"({sp_p:.0f} mm) نمی‌خواند.")
        else:
            a_s = a_p = 0.0
        rot = a_p - a_s
        c, s = math.cos(rot), math.sin(rot)
        sx = sum(x for x, _ in lc) / len(lc)
        sy = sum(y for _, y in lc) / len(lc)
        tx = sum(x for x, _ in tgt) / len(tgt)
        ty = sum(y for _, y in tgt) / len(tgt)

        def T(pt):
            x, y, z = pt[0] * 1000 - sx, pt[1] * 1000 - sy, (pt[2] - zmin) * 1000
            return (tx + c * x - s * y, ty + s * x + c * y, base_z + z)

        def R(v):
            return (c * v[0] - s * v[1], s * v[0] + c * v[1], v[2])

        corners = {(round(x, 3), round(y, 3)): (lx, ly)
                   for lx, ly, pts in legs for x, y in pts}
        for f in st.frames:
            a, b = st.joints[f.i], st.joints[f.j]
            if a[2] > b[2]:
                a, b = b, a
            sec = st.sections[f.section]
            _, e2, e3 = local_axes(a, b)
            vertical = abs(a[0] - b[0]) < 1e-6 and abs(a[1] - b[1]) < 1e-6
            corner = corners.get((round(a[0], 3), round(a[1], 3)))
            if vertical and corner and sec.shape.lower() == "angle":
                # نبشی اصلی پایه: پاشنه روی محور، بال‌ها رو به مرکز پایه
                e2 = (math.copysign(1, corner[0] - a[0]), 0.0, 0.0)
                e3 = (0.0, math.copysign(1, corner[1] - a[1]), 0.0)
                prof, kind = profile(sec, heel_on_axis=True), "chord"
            else:
                prof = profile(sec)
                kind = "beam" if sec.shape.lower() != "angle" else "brace"
            members.append(Member(T(a), T(b), sec, R(e2), R(e3), prof, kind))
    return members, warn


def section_points(m, at):
    """نقاط سه‌بعدی مقطع عضو در سر at (برای ساخت حجم)."""
    return [[tuple(at[k] + u * m.e2[k] + v * m.e3[k] for k in range(3)) for u, v in part]
            for part in _parts(m.profile)]
