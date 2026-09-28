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
    group: int = 0            # شماره گروه تجهیز روی پی
    tag: str = ""             # برچسب تجهیز همان گروه


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
    grout: float = 50.0                                 # ضخامت گروت (mm)
    plate_t: float = 20.0                               # ضخامت صفحه کف (mm)
    anchor_embed: float = 0.0                           # طول مدفون محاسبه‌شده (mm)
    anchor_projection: float = 150.0                    # بیرون‌زدگی از روی بتن (mm)
    anchor_hook: float = 0.0                            # قلاب انتهایی (×d)؛ صفر = صاف
    base_plate: float = 0.0                             # ضلع صفحه کف (mm)؛ صفر = نامشخص
    steel: list = field(default_factory=list)           # structural.placement.Placed
    equipment: list = field(default_factory=list)       # structural.equipment3d اولیه‌ها

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


def pedestal_spacing(eq, B):  # noqa: D401 — سازگاری با کد قدیمی
    """
    فاصله محور تا محور ستون‌ها (m). برای تجهیز دوستونه باید از نقشه سازه وارد
    شود؛ اگر نشده (فقط کاتالوگ قدیمی خط فرمان)، نصف عرض پی فرض می‌شود.
    """
    if eq.n_pedestal <= 1:
        return 0.0
    return eq.pedestal_spacing or B / 2


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


def _grid_n(length, cover, db, n):
    """n میلگرد با فاصله مساوی از پوشش تا پوشش (مرکز میلگرد در cover + d/2)."""
    first, last = -length / 2 + cover + db / 2, length / 2 - cover - db / 2
    if n <= 1:
        return [0.0]
    step = (last - first) / (n - 1)
    return [first + i * step for i in range(n)]


def build(res, layout, des, cfg) -> FoundationModel:
    from padlayout import PadLayout
    from equipment import Equipment
    if isinstance(layout, Equipment):
        layout = PadLayout.single(layout)
    g = res.geometry
    m = cfg.materials
    r = cfg.rebar
    L, B, tf, hp, b = g.L * 1000, g.B * 1000, g.tf * 1000, g.hp * 1000, g.b * 1000
    cov = float(m.cover)
    fm = FoundationModel(L=L, B=B, tf=tf, hp=hp, b=b, cover=cov, lean=float(m.lean),
                         lean_margin=100.0, soil_cover=cfg.soil.soil_cover * 1000)

    # --- ستون‌ها، از چیدمان (هر ستون می‌داند مال کدام گروه است)
    fm.pedestals = [Pedestal(x * 1000, y * 1000, b, i, layout.groups[i].eq.tag)
                    for x, y, i in layout.positions(g.B)]
    owner = [i for _, _, i in layout.positions(g.B)]
    groups = des.get("groups") or [{"pedestal": des["pedestal"], "anchor": des["anchor"]}]

    # --- شبکه پی: دو لایه، هر لایه دو جهت؛ تعداد هر جهت از طراحی پی.
    # قلاب دو سر تا لایه مقابل (ضخامت پی − ۲ پوشش) مثل نقشه‌های دفتر.
    pad = des["pad"]
    s = pad.spacing
    fm.pad_spacing = s
    d = pad.bar_dia
    n_L = getattr(pad, "n_L", None) or len(_grid(L, cov, s))
    n_B = getattr(pad, "n_B", None) or len(_grid(B, cov, s))
    hook = r.pad_hook or (tf - 2 * cov - 2 * d)
    z_bot = cov + d / 2
    z_top = tf - cov - d / 2
    xs_L = _grid_n(L, cov, d, n_L)                       # محل میلگردهای راستای y
    ys_B = _grid_n(B, cov, d, n_B)                       # محل میلگردهای راستای x
    for mark, z1, z2, up in (("01", z_bot, z_bot + d, 1), ("03", z_top, z_top - d, -1)):
        for y in ys_B:
            x0, x1 = -L / 2 + cov, L / 2 - cov
            fm.bars.append(Bar(mark, d, [(x0, y, z1 + up * hook), (x0, y, z1),
                                         (x1, y, z1), (x1, y, z1 + up * hook)]))
        for x in xs_L:
            y0, y1 = -B / 2 + cov, B / 2 - cov
            fm.bars.append(Bar(mark, d, [(x, y0, z2 + up * hook), (x, y0, z2),
                                         (x, y1, z2), (x, y1, z2 + up * hook)]))

    # --- ستون: میلگرد طولی با قلاب ۱۵d در کف پی، و خاموت؛ هر ستون با طراحی گروه خودش
    core = b - 2 * cov
    for p, gi in zip(fm.pedestals, owner):
        ped = groups[gi]["pedestal"]
        for dx, dy in pedestal_bar_positions(core, ped.bar_count):
            x, y = p.x + dx, p.y + dy
            z0, z1 = z_bot + d, tf + hp - cov
            # قلاب ۱۵d رو به بیرون مقطع؛ اگر از لبه پی بیرون بزند، رو به داخل
            hk = 15 * ped.bar_dia
            if abs(dx) >= abs(dy):
                sx = 1 if dx > 0 else -1
                if abs(x + sx * hk) > L / 2 - cov:
                    sx = -sx
                hx, hy = sx * hk, 0.0
            else:
                sy = 1 if dy > 0 else -1
                if abs(y + sy * hk) > B / 2 - cov:
                    sy = -sy
                hx, hy = 0.0, sy * hk
            fm.bars.append(Bar("02", ped.bar_dia, [(x + hx, y + hy, z0), (x, y, z0), (x, y, z1)]))
        z = tf + TIE_START
        while z <= tf + hp - TIE_START + 1e-6:
            h = core / 2 + ped.bar_dia / 2 + r.tie_dia / 2
            fm.bars.append(Bar("05", r.tie_dia, [(p.x - h, p.y - h, z), (p.x + h, p.y - h, z),
                                                 (p.x + h, p.y + h, z), (p.x - h, p.y + h, z)],
                               closed=True))
            z += r.tie_spacing

    # --- خرک بین دو لایه، یکی روی هر میلگرد راستای y
    for x in xs_L:
        fm.bars.append(Bar("04", r.standee_dia, [(x, -100, z_bot + d), (x, -100, z_top - d),
                                                 (x, 100, z_top - d), (x, 100, z_bot + d)]))

    # --- میل مهار: طول مدفون از طراحی هر گروه، نه ورودی
    an = cfg.anchorage
    fm.grout, fm.plate_t, fm.anchor_projection = an.grout, an.plate_thickness, an.projection
    fm.anchor_hook = an.hook
    fm.base_plate = float(layout.main.base_plate or 0)
    fm.anchor_embed = max(x["anchor"].embed for x in groups)
    for p, gi in zip(fm.pedestals, owner):
        eq = layout.groups[gi].eq
        emb = groups[gi]["anchor"].embed
        gge = eq.anchor_gauge
        for sx in (-1, 1):
            for sy in (-1, 1):
                fm.anchors.append(Anchor(p.x + sx * gge / 2, p.y + sy * gge / 2, eq.anchor_dia,
                                         fm.top - emb, fm.top + an.projection))

    # --- سازه فولادی طراحی‌شده در برنامه، روی صفحه کف ستون‌های همان تجهیز
    from structural.placement import place
    base_z = fm.top + an.grout + an.plate_thickness
    from structural.equipment3d import for_design, for_stand
    designed = set()
    for gi, sd in getattr(res, "structures", []) or []:
        peds = [(p.x, p.y) for p, o in zip(fm.pedestals, owner) if o == gi]
        fm.steel += place(sd, peds, base_z)
        fm.equipment += for_design(layout.groups[gi].eq, sd, peds, base_z)
        designed.add(gi)
    # سازه سازنده یا طراحی سازه خاموش: شکل ساده استراکچر و تجهیز روی آن
    pitch = cfg.steel.phase_pitch if getattr(cfg, "steel", None) else 1.5
    for gi, g in enumerate(layout.groups):
        if gi not in designed:
            peds = [(p.x, p.y) for p, o in zip(fm.pedestals, owner) if o == gi]
            fm.equipment += for_stand(g.eq, peds, base_z, pitch)
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

    names = {"01": "شبکه زیرین پی", "02": "میلگرد طولی ستون", "03": "شبکه رویی پی",
             "04": "خرک", "05": "خاموت ستون"}
    bad = {}
    for bar in fm.bars:
        r = bar.dia / 2
        if any(not inside(x, y, z, fm.cover * 0.5 - r - tol) for x, y, z in bar.points):
            bad[bar.mark] = bad.get(bar.mark, 0) + 1
    for mark, count in bad.items():
        out.append(f"{count} عدد {names.get(mark, mark)} ({mark}) از بتن بیرون زده یا پوشش ندارد")
    outside = sum(1 for a in fm.anchors
                  if not any(abs(a.x - p.x) <= p.size / 2 - a.dia
                             and abs(a.y - p.y) <= p.size / 2 - a.dia for p in fm.pedestals))
    if outside:
        out.append(f"{outside} میل مهار بیرون از ستون است — فاصله محور میل مهارها از عرض ستون بیشتر است")
    for i, p in enumerate(fm.pedestals):
        if abs(p.x) + p.size / 2 > fm.L / 2 + tol or abs(p.y) + p.size / 2 > fm.B / 2 + tol:
            out.append(f"ستون {i + 1} از پی بیرون زده")
        for q in fm.pedestals[i + 1:]:
            if abs(p.x - q.x) < (p.size + q.size) / 2 and abs(p.y - q.y) < (p.size + q.size) / 2:
                out.append("دو ستون روی هم افتاده‌اند")
    return out


def to_dict(fm: FoundationModel) -> dict:
    """نسخه JSON مدل برای نمای سه‌بعدی مرورگر؛ همان مختصات فایل‌های اتوکد."""
    steel, equipment = fm.steel, fm.equipment
    fm.steel, fm.equipment = [], []
    d = asdict(fm)
    fm.steel, fm.equipment = steel, equipment
    d["equipment"] = equipment
    d["top"] = fm.top
    d["steel"] = [{"p": [round(v, 1) for v in m.p], "q": [round(v, 1) for v in m.q],
                   "e2": [round(v, 5) for v in m.e2], "e3": [round(v, 5) for v in m.e3],
                   "profile": [[[round(u, 2), round(w, 2)] for u, w in poly] for poly in m.profile],
                   "group": m.group, "section": m.section, "ratio": round(m.ratio, 3),
                   "member": m.member,
                   "d": {c: [round(v, 2) for v in dv] for c, dv in (m.disp or {}).items()},
                   "r": {c: round(v, 3) for c, v in (m.ratios or {}).items()},
                   "f": {c: v for c, v in (m.modes or {}).items()
                         if (m.ratios or {}).get(c, 0) > 0.9}} for m in steel]
    from structural.loads import COMBO_TITLES
    combos = list(dict.fromkeys(c for m in steel for c in (m.disp or {})))
    d["load_cases"] = [{"id": c, "title": COMBO_TITLES.get(c, c)} for c in combos]
    return d
