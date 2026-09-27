"""
ساخت خودکار سازه مشبک نگهدارنده تجهیز — همان الگوی سازه‌های دفتر:

    پایه    چهار نبشی اصلی پیوسته در گوشه‌های مربع a×a، پانل‌های مساوی حدود ۰٫۵ متر
            مهاربند قطری مفصلی در هر وجه (زیگزاگ یا ضربدری)، افقی مفصلی بالای پایه
    سر      دو پایه: دو تیر ناودانی در امتداد X روی دو خط نبشی‌ها، فازها با گام ثابت
            یک پایه: قاب ناودانی روی سر پایه (مثل CVT تک‌فاز)
    تکیه‌گاه مفصلی زیر هر نبشی (روی صفحه کف)

مختصات: مبدأ وسط کف سازه، X در امتداد ردیف ستون‌ها (امتداد فازها)، Y عمود بر آن
(امتداد هادی و باد اصلی)، Z رو به بالا. واحد: متر.
"""
import math
from dataclasses import dataclass, field

from .frame import Member, Model
from .sections import CATALOG

PIN = (False, False, False, True, True, True, False, False, False, False, True, True)


@dataclass
class LatticeSpec:
    height: float                   # ارتفاع سازه تا روی تیر سر (m) — Hs تجهیز
    legs: int = 2                   # تعداد پایه مشبک (= تعداد ستون بتنی زیر سازه)
    leg_spacing: float = 1.70       # فاصله محور پایه‌ها (m)
    leg_width: float = 0.40         # ضلع مربع نبشی‌های یک پایه (m)
    phases: int = 3                 # تعداد فاز روی سازه (npol)
    phase_pitch: float = 1.50       # فاصله فازها روی تیر سر (m)
    panel: float = 0.50             # ارتفاع هدف هر پانل (m)
    bracing: str = "zigzag"         # zigzag | x
    chord: str = "L60X6"
    brace: str = "L40X4"
    beam: str = "UNP140"
    k_chord: float = 1.0            # ضریب طول مؤثر نبشی اصلی (رویه دفتر: ۲)
    groups: dict = field(default_factory=dict)


def build(spec: LatticeSpec, sections=CATALOG):
    """مدل سازه (بدون بار)؛ هر عضو گروه chord / brace / strut / beam دارد."""
    a = spec.leg_width
    H = spec.height
    n = max(1, round(H / spec.panel))
    levels = [H * k / n for k in range(n + 1)]
    if spec.legs == 1:
        centres = [0.0]
    else:
        centres = [(-(spec.legs - 1) / 2 + i) * spec.leg_spacing for i in range(spec.legs)]
    nodes, members, supports = {}, [], {}

    def node(x, y, z):
        key = (round(x, 6), round(y, 6), round(z, 6))
        name = f"N{key[0]:+.3f}_{key[1]:+.3f}_{key[2]:.3f}"
        nodes.setdefault(name, key)
        return name

    def add(kind, i, j, sec, released=False, k=1.0):
        members.append(Member(f"{kind[0].upper()}{len(members) + 1}", i, j, sections[sec],
                              PIN if released else (False,) * 12, group=kind,
                              k_major=k, k_minor=k))

    corners = [(-a / 2, -a / 2), (a / 2, -a / 2), (a / 2, a / 2), (-a / 2, a / 2)]
    for cx in centres:
        for dx, dy in corners:
            # مفصلی حول محورهای افقی؛ چرخش حول محور قائم را صفحه کف جوش‌شده مهار می‌کند
            supports[node(cx + dx, dy, 0.0)] = (True, True, True, False, False, True)
            for z0, z1 in zip(levels, levels[1:]):
                add("chord", node(cx + dx, dy, z0), node(cx + dx, dy, z1), spec.chord,
                    k=spec.k_chord)
        # مهاربند چهار وجه
        for f in range(4):
            (x0, y0), (x1, y1) = corners[f], corners[(f + 1) % 4]
            for p, (z0, z1) in enumerate(zip(levels, levels[1:])):
                up = (p + f) % 2 == 0
                if spec.bracing == "x" or up:
                    add("brace", node(cx + x0, y0, z0), node(cx + x1, y1, z1), spec.brace, True)
                if spec.bracing == "x" or not up:
                    add("brace", node(cx + x1, y1, z0), node(cx + x0, y0, z1), spec.brace, True)
        # افقی مفصلی بالای پایه در امتداد Y (امتداد X را تیر سر می‌گیرد)
        for dx in (-a / 2, a / 2):
            add("strut", node(cx + dx, -a / 2, H), node(cx + dx, a / 2, H), spec.chord, True)

    # سر سازه و نقاط نصب فازها
    load_points = []
    if spec.legs >= 2 or spec.phases > 1:
        xs = [(-(spec.phases - 1) / 2 + k) * spec.phase_pitch for k in range(spec.phases)]
        x_lo = min(xs + [c - a / 2 for c in centres])
        x_hi = max(xs + [c + a / 2 for c in centres])
        for y in (-a / 2, a / 2):
            for x in xs:
                node(x, y, H)
            add("beam", node(x_lo, y, H), node(x_hi, y, H), spec.beam)
        load_points = [[node(x, -a / 2, H), node(x, a / 2, H)] for x in xs]
    else:
        cx = centres[0]
        for y in (-a / 2, a / 2):
            add("beam", node(cx - a / 2, y, H), node(cx + a / 2, y, H), spec.beam, True)
        load_points = [[node(cx + dx, dy, H) for dx, dy in corners]]

    model = Model(nodes, members, supports)
    model.load_points = load_points            # هر فاز: گره‌های زیر پایه تجهیز
    model.leg_centres = centres
    model.spec = spec
    return model


def projected_width(member, model, wind=(0.0, 1.0, 0.0)):
    """
    سطح بادگیر عضو برای باد در امتداد +Y (m، m): فقط اعضای وجه رو به باد (کمترین y)
    — ضریب درگ سازه مشبک (Cs = 2.05) اثر وجه پشت باد را خودش دارد، مثل مدل‌های دفتر.
    اعضای وجه‌های موازی باد لبه‌به‌لبه‌اند و سطح تازه‌ای نمی‌سازند.
    خروجی: (پهنای مؤثر × |sin زاویه با باد|، طول)
    """
    p, q = model.nodes[member.i], model.nodes[member.j]
    d = [q[k] - p[k] for k in range(3)]
    L = math.sqrt(sum(c * c for c in d))
    y_face = min(c[1] for c in model.nodes.values())
    if abs(p[1] - y_face) > 1e-6 or abs(q[1] - y_face) > 1e-6:
        return 0.0, L
    cos = abs(sum(d[k] * wind[k] for k in range(3))) / L
    sin = math.sqrt(max(0.0, 1 - cos * cos))
    width = member.section.t3 if member.group == "beam" else max(member.section.t3, member.section.t2)
    return width * sin, L
