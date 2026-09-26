"""
مدل هندسی مرکزی فونداسیون — تنها منبع مختصات.

نقشه دوبعدی (ساخت) و مدل سه‌بعدی (ارائه) هر دو از همین مدل ساخته می‌شوند؛
هیچ‌کدام خودشان جای میلگرد یا ستون را حساب نمی‌کنند. این‌طور دو خروجی
هیچ‌وقت با هم اختلاف پیدا نمی‌کنند.

دستگاه مختصات: میلی‌متر، مبدأ در مرکز کف پی (روی بتن مگر).
    x در راستای L ، y در راستای B ، z رو به بالا
    z = 0 کف پی ، z = tf روی پی ، z = tf + hp روی ستون
"""
from dataclasses import asdict, dataclass, field


@dataclass
class Bar:
    """یک میلگرد به صورت خط شکسته سه‌بعدی (محور میلگرد)."""
    mark: str                 # شماره ردیف در لیست آرماتور، مثل "01"
    dia: float                # mm
    points: list              # [(x, y, z), ...]
    closed: bool = False      # خاموت

    @property
    def length(self):
        """طول گسترده میلگرد (mm)؛ برای خاموت، قلاب‌های ۱۳۵ درجه (۲×۱۰d) اضافه می‌شود."""
        pts = self.points + ([self.points[0]] if self.closed else [])
        total = sum(((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5
                    for a, b in zip(pts, pts[1:]))
        return total + (20 * self.dia if self.closed else 0)


@dataclass
class Anchor:
    x: float
    y: float
    dia: float
    z_bottom: float
    z_top: float


@dataclass
class Pedestal:
    x: float
    y: float
    size: float               # ضلع مقطع مربعی


@dataclass
class FoundationModel:
    L: float
    B: float
    tf: float
    hp: float
    b: float
    cover: float
    lean: float
    lean_margin: float                                  # بیرون‌زدگی مگر از هر طرف
    soil_cover: float                                   # فاصله روی ستون تا تراز زمین
    pedestals: list = field(default_factory=list)
    anchors: list = field(default_factory=list)
    bars: list = field(default_factory=list)
    pad_spacing: float = 0.0

    @property
    def top(self):
        return self.tf + self.hp

    def bars_by_mark(self, mark):
        return [b for b in self.bars if b.mark == mark]


TIE_START = 50.0          # فاصله اولین و آخرین خاموت از کف و سر ستون (mm)


def _grid(length, cover, spacing):
    """مختصات میلگردها در یک راستا، از پوشش تا پوشش با فاصله مشخص."""
    first, last = -length / 2 + cover, length / 2 - cover
    out, v = [], first
    while v <= last + 1e-6:
        out.append(v)
        v += spacing
    return out


def pedestal_bar_positions(core, count):
    """
    میلگردهای طولی دور تا دور مقطع مربعی، با میلگرد در چهار گوشه.
    خروجی: [(dx, dy), ...] نسبت به مرکز ستون.
    """
    per_side = max(1, max(4, count) // 4)
    step = core / per_side
    pts = []
    for k in range(per_side):
        o = -core / 2 + k * step
        pts += [(o, -core / 2), (core / 2, o), (-o, core / 2), (-core / 2, -o)]
    return pts


def build(res, eq, des, cfg) -> FoundationModel:
    g = res.geometry
    m = cfg.materials
    r = cfg.rebar
    L, B, tf, hp, b = g.L * 1000, g.B * 1000, g.tf * 1000, g.hp * 1000, g.b * 1000
    cov = float(m.cover)
    fm = FoundationModel(L=L, B=B, tf=tf, hp=hp, b=b, cover=cov, lean=float(m.lean),
                         lean_margin=100.0, soil_cover=cfg.soil.soil_cover * 1000)

    # --- ستون‌ها
    n = eq.n_pedestal
    sp = eq.pedestal_spacing * 1000 or (B / 2 if n > 1 else 0)
    xs = [0.0] if n == 1 else [-sp / 2, sp / 2]
    fm.pedestals = [Pedestal(x, 0.0, b) for x in xs]

    # --- شبکه پی: دو لایه، هر لایه دو جهت، با قلاب ۱۰d در دو سر
    pad = des["pad"]
    s = pad.spacing
    fm.pad_spacing = s
    d = pad.bar_dia
    hook = 10 * d
    z_bot = cov + d / 2
    z_top = tf - cov - d / 2
    for layer, (mark_x, z1, z2, up) in {
            "bottom": ("01", z_bot, z_bot + d, 1), "top": ("03", z_top, z_top - d, -1)}.items():
        for y in _grid(B, cov, s):                       # میلگردهای راستای x
            x0, x1 = -L / 2 + cov, L / 2 - cov
            fm.bars.append(Bar(mark_x, d, [(x0, y, z1 + up * hook), (x0, y, z1),
                                           (x1, y, z1), (x1, y, z1 + up * hook)]))
        for x in _grid(L, cov, s):                       # میلگردهای راستای y
            y0, y1 = -B / 2 + cov, B / 2 - cov
            fm.bars.append(Bar(mark_x, d, [(x, y0, z2 + up * hook), (x, y0, z2),
                                           (x, y1, z2), (x, y1, z2 + up * hook)]))

    # --- ستون: میلگرد طولی با قلاب ۱۵d در کف پی، و خاموت
    ped = des["pedestal"]
    core = b - 2 * cov
    for p in fm.pedestals:
        for dx, dy in pedestal_bar_positions(core, ped.bar_count):
            x, y = p.x + dx, p.y + dy
            z0, z1 = z_bot + d, tf + hp - cov
            # قلاب ۱۵d رو به بیرون مقطع؛ اگر از لبه پی بیرون بزند، رو به داخل
            hook = 15 * ped.bar_dia
            if abs(dx) >= abs(dy):
                sx = 1 if dx > 0 else -1
                if abs(x + sx * hook) > L / 2 - cov:
                    sx = -sx
                hx, hy = sx * hook, 0.0
            else:
                sy = 1 if dy > 0 else -1
                if abs(y + sy * hook) > B / 2 - cov:
                    sy = -sy
                hx, hy = 0.0, sy * hook
            fm.bars.append(Bar("02", ped.bar_dia, [(x + hx, y + hy, z0), (x, y, z0), (x, y, z1)]))
        z = tf + TIE_START
        while z <= tf + hp - TIE_START + 1e-6:
            h = core / 2 + ped.bar_dia / 2 + r.tie_dia / 2
            fm.bars.append(Bar("05", r.tie_dia, [(p.x - h, p.y - h, z), (p.x + h, p.y - h, z),
                                                 (p.x + h, p.y + h, z), (p.x - h, p.y + h, z)],
                               closed=True))
            z += r.tie_spacing

    # --- خرک بین دو لایه، یکی روی هر میلگرد راستای y
    for x in _grid(L, cov, s):
        fm.bars.append(Bar("04", r.standee_dia, [(x, -100, z_bot + d), (x, -100, z_top - d),
                                                 (x, 100, z_top - d), (x, 100, z_bot + d)]))

    # --- میل مهار
    gge = eq.anchor_gauge
    for p in fm.pedestals:
        for sx in (-1, 1):
            for sy in (-1, 1):
                fm.anchors.append(Anchor(p.x + sx * gge / 2, p.y + sy * gge / 2, eq.anchor_dia,
                                         fm.top - eq.anchor_embed, fm.top + 200))
    return fm


def clashes(fm: FoundationModel) -> list:
    """
    کنترل هندسی جزئیات: هر میلگردی که پوشش بتن را رعایت نکند یا از بتن بیرون
    بزند، هر میل مهاری که از ستون بیرون باشد یا تا پی نرسد، و ستون‌هایی که روی
    هم افتاده‌اند یا از پی بیرون زده‌اند.
    """
    out = []
    tol = 1.0

    def inside(x, y, z, margin):
        if -margin <= z <= fm.tf + margin and abs(x) <= fm.L / 2 - margin and \
                abs(y) <= fm.B / 2 - margin:
            return True
        return any(abs(x - p.x) <= p.size / 2 - margin and abs(y - p.y) <= p.size / 2 - margin
                   and fm.tf - margin <= z <= fm.top - margin for p in fm.pedestals)

    for bar in fm.bars:
        r = bar.dia / 2
        for x, y, z in bar.points:
            if not inside(x, y, z, fm.cover * 0.5 - r - tol):
                out.append(f"میلگرد {bar.mark} (Ф{bar.dia:.0f}) در ({x:.0f}, {y:.0f}, {z:.0f}) "
                           f"از بتن بیرون زده یا پوشش ندارد")
                break
    for a in fm.anchors:
        if not any(abs(a.x - p.x) <= p.size / 2 - a.dia and abs(a.y - p.y) <= p.size / 2 - a.dia
                   for p in fm.pedestals):
            out.append(f"میل مهار ({a.x:.0f}, {a.y:.0f}) بیرون از ستون است")
    for i, p in enumerate(fm.pedestals):
        if abs(p.x) + p.size / 2 > fm.L / 2 + tol or abs(p.y) + p.size / 2 > fm.B / 2 + tol:
            out.append(f"ستون {i + 1} از پی بیرون زده")
        for q in fm.pedestals[i + 1:]:
            if abs(p.x - q.x) < (p.size + q.size) / 2 and abs(p.y - q.y) < (p.size + q.size) / 2:
                out.append("دو ستون روی هم افتاده‌اند")
    return out


def to_dict(fm: FoundationModel) -> dict:
    """نسخه JSON مدل برای نمای سه‌بعدی مرورگر؛ همان مختصات فایل‌های اتوکد."""
    d = asdict(fm)
    d["top"] = fm.top
    return d
