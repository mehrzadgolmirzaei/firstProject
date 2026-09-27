"""
خواندن کی‌پلن فونداسیون (DXF) — چیدمان ستون‌ها از خود نقشه، نه ورود دستی.

در کی‌پلن دفتر هر نوع پی یک بلاک است با نامی مثل «LA+CVT-3-2.5» یا «PI-CVT-3-3».
داخل بلاک:
    بزرگ‌ترین مستطیل بسته      ← طرح پی (L×B)
    مستطیل‌های مربعی داخل آن   ← ستون‌های بتنی (ضلع b)
نام بلاک می‌گوید چه تجهیزی روی پی است؛ ستون‌های هر تجهیز از روی ردیفشان
(هم‌تراز در x یا y) و تعدادشان (از کاتالوگ) شناخته می‌شوند.

مختصات خروجی بر حسب متر و نسبت به مرکز پی است — همان قرارداد padlayout.
"""
import re
from collections import defaultdict
from dataclasses import dataclass, field

from equipment import VOLTAGE_LEVELS
from padlayout import Group, PadLayout

# نام تجهیز در کی‌پلن ← نوع تجهیز. «DS-DSE» یک تجهیز است.
KEYPLAN_TOKENS = {"LA": "LA", "CB": "CB", "CT": "CT", "CVT": "CVT", "PI": "PI",
                  "DS": "DSE", "DSE": "DSE", "DS2": "DS2", "DSROW": "DSROW"}
# نوعی که بسته به تعداد ستون در کی‌پلن گونه دیگری دارد (CVT سه‌ستونه / تک‌فاز)
VARIANTS = {"CVT": ["CVT", "CVT1"]}

TOL = 5.0        # mm — تلرانس هم‌ترازی و مربع بودن


@dataclass
class KeyplanFoundation:
    name: str                       # نام بلاک
    count: int                      # تعداد در کی‌پلن
    L: float = 0.0                  # m
    B: float = 0.0
    b: float = 0.0                  # ضلع ستون
    groups: list = field(default_factory=list)   # [{"tag", "positions": [(x, y)]}]
    problem: str = ""               # اگر خالی نباشد، این پی قابل استفاده نیست

    @property
    def ok(self):
        return not self.problem

    def describe(self):
        return " + ".join(f"{g['tag']}×{len(g['positions'])}" for g in self.groups)

    def to_dict(self):
        return {"name": self.name, "count": self.count, "L": self.L, "B": self.B,
                "b": self.b, "groups": self.groups, "problem": self.problem,
                "describe": self.describe()}

    def layout(self, catalog):
        return PadLayout([Group(catalog[g["tag"]], [tuple(p) for p in g["positions"]])
                          for g in self.groups])


def _rects(block):
    """مستطیل‌های بسته چهارگوشه بلاک: (xmin, ymin, xmax, ymax)."""
    out = []
    for e in block:
        if e.dxftype() != "LWPOLYLINE":
            continue
        pts = [(x, y) for x, y in e.get_points("xy")]
        if len(pts) >= 2 and pts[0] == pts[-1]:
            pts = pts[:-1]
        if len(pts) != 4:
            continue
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        out.append((min(xs), min(ys), max(xs), max(ys)))
    return out


def equipment_tokens(name):
    """«LA+CVT-3-2.5» ← ["LA", "CVT"] ؛ «DS-DSE-2.5-1.8» ← ["DSE"]  (نوع تجهیز)."""
    tokens = [t for t in re.split(r"[+\-_ ]", name.upper()) if t and not re.fullmatch(r"[\d.]+", t)]
    keys = []
    for t in tokens:
        key = KEYPLAN_TOKENS.get(t)
        if key is None:
            return None, t
        if not keys or keys[-1] != key:       # DS-DSE یک تجهیز است
            keys.append(key)
    return keys, None


def _candidates(typ, types):
    return [types[v] for v in VARIANTS.get(typ, [typ]) if v in types]


def _assign(peds, keys, catalog, types):
    """
    ستون‌ها را بین تجهیزها تقسیم می‌کند: ستون‌های هر تجهیز روی یک خط (هم‌تراز در y
    یا در x)اند و تعدادشان با کاتالوگ همان سطح ولتاژ می‌خواند.
    """
    if len(keys) == 1:
        cands = _candidates(keys[0], types)
        if not cands:
            return None
        for v in cands:
            if catalog[v].n_pedestal == len(peds):
                return [{"tag": v, "positions": peds}]
        return [{"tag": cands[0], "positions": peds}]

    for axis in (1, 0):                       # اول ردیف‌های افقی، بعد ستونی
        lines = defaultdict(list)
        for p in peds:
            k = round(p[axis] / 0.005)        # هم‌ترازی با تلرانس ۵ میلی‌متر
            lines[k].append(p)
        lines = list(lines.values())
        if len(lines) != len(keys):
            continue
        used, groups = set(), []
        for tag in keys:
            match = None
            for i, line in enumerate(lines):
                if i in used:
                    continue
                for v in _candidates(tag, types):
                    if catalog[v].n_pedestal == len(line):
                        match = (i, v)
                        break
                if match:
                    break
            if not match:
                break
            used.add(match[0])
            groups.append({"tag": match[1], "positions": sorted(lines[match[0]])})
        if len(groups) == len(keys):
            return groups
    return None


def read_foundations(path, catalog, voltage="63"):
    """همه انواع پی کی‌پلن، با تعداد تکرار هر کدام؛ تجهیزها از کاتالوگ سطح ولتاژ پست."""
    types = VOLTAGE_LEVELS[voltage]["types"]
    import ezdxf
    doc = ezdxf.readfile(path)
    counts = defaultdict(int)
    for ins in doc.modelspace().query("INSERT"):
        counts[ins.dxf.name] += 1

    found = []
    for name, count in counts.items():
        keys, unknown = equipment_tokens(name)
        if keys is None:
            continue                          # بلاک کادر، شمال‌نما، یا تجهیز ناشناخته
        block = doc.blocks.get(name)
        if block is None:
            continue
        rects = _rects(block)
        f = KeyplanFoundation(name, count)
        if not rects:
            f.problem = "طرح پی در بلاک پیدا نشد"
            found.append(f)
            continue
        pad = max(rects, key=lambda r: (r[2] - r[0]) * (r[3] - r[1]))
        cx, cy = (pad[0] + pad[2]) / 2, (pad[1] + pad[3]) / 2
        f.L = round(float(pad[2] - pad[0]) / 1000, 3)
        f.B = round(float(pad[3] - pad[1]) / 1000, 3)
        peds, sizes = [], set()
        for r in rects:
            if r is pad:
                continue
            w, h = r[2] - r[0], r[3] - r[1]
            inside = (r[0] >= pad[0] - TOL and r[2] <= pad[2] + TOL
                      and r[1] >= pad[1] - TOL and r[3] <= pad[3] + TOL)
            if inside and abs(w - h) <= TOL and w < min(pad[2] - pad[0], pad[3] - pad[1]):
                peds.append((round(float((r[0] + r[2]) / 2 - cx) / 1000, 3) + 0.0,
                             round(float((r[1] + r[3]) / 2 - cy) / 1000, 3) + 0.0))
                sizes.add(int(round(float(w) / 10)) * 10)
        peds = sorted(set(peds))
        if not peds:
            f.problem = "ستونی داخل طرح پی پیدا نشد"
        elif len(sizes) > 1:
            f.problem = f"ستون‌ها هم‌اندازه نیستند: {sorted(sizes)} mm"
        else:
            f.b = sizes.pop() / 1000
            groups = _assign(peds, keys, catalog, types)
            if groups is None:
                f.problem = ("تقسیم ستون‌ها بین تجهیزها با کاتالوگ نخواند: "
                             f"{len(peds)} ستون برای {'، '.join(keys)}")
            else:
                f.groups = groups
        found.append(f)
    found.sort(key=lambda f: f.name)
    return found
