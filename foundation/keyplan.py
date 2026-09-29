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
KEYPLAN_TOKENS = {"LA": "LA", "CB": "CB", "CT": "CT", "CVT": "CVT", "CVT1": "CVT1", "PI": "PI", "PI1": "PI1",
                  "DS": "DSE", "DSE": "DSE", "DS2": "DS2", "DSROW": "DSROW"}
# نوعی که بسته به تعداد ستون در کی‌پلن گونه دیگری دارد (CVT سه‌ستونه / تک‌فاز)
VARIANTS = {"CVT": ["CVT", "CVT1"], "PI": ["PI", "PI1"]}

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
    up = re.sub(r"DS[-_ ]?ROW", "DSROW", name.upper())       # «DS-ROW» یک تجهیز است (سکسیونر ردیفی)
    tokens = [t for t in re.split(r"[+\-_ ]", up) if t and not re.fullmatch(r"[\d.]+", t)]
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


def read_foundations(path, catalog, voltage="63", doc=None):
    """همه انواع پی کی‌پلن، با تعداد تکرار هر کدام؛ تجهیزها از کاتالوگ سطح ولتاژ پست."""
    types = VOLTAGE_LEVELS[voltage]["types"]
    if doc is None:
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


def fit_score(found, catalog):
    """چند نوع پی با کاتالوگ این سطح ولتاژ می‌خواند: تعداد ستون هر تجهیز = ستون‌های کاتالوگ."""
    n = 0
    for f in found:
        if f.ok and all(len(g["positions"]) == catalog[g["tag"]].n_pedestal for g in f.groups):
            n += f.count
    return n


def detect_voltage(doc, catalog, selected="63"):
    """
    سطح ولتاژ کی‌پلن: همان که ستون‌های بیشترین پی با کاتالوگش می‌خواند (پی ۲۳۰ یک ستون، پی ۶۳
    یک سازه دو یا سه ستونه). اگر برابر بود، انتخاب فرم می‌ماند.
    خروجی: (سطح ولتاژ، پی‌ها با همان سطح)
    """
    best = None
    for v in [selected] + [v for v in VOLTAGE_LEVELS if v != selected]:
        found = read_foundations(None, catalog, v, doc=doc)
        s = fit_score(found, catalog)
        if best is None or s > best[0]:
            best = (s, v, found)
    return best[1], best[2]


def plan(doc, names):
    """جای هر پی کی‌پلن (m) برای نمایش پلان: [{type, label, cx, cy, dx, dy}]."""
    from ezdxf import bbox
    cache = bbox.Cache()
    out = []
    for ins in doc.modelspace().query("INSERT"):
        if ins.dxf.name not in names:
            continue
        e = bbox.extents([ins], cache=cache)
        if not e.has_data:
            continue
        label = re.sub(r"(-[\d.]+)+$", "", ins.dxf.name).upper()      # LA+CVT-3-2.5 ← LA+CVT
        out.append({"type": ins.dxf.name, "label": label,
                    "cx": round(e.center.x / 1000, 3), "cy": round(e.center.y / 1000, 3),
                    "dx": round(e.size.x / 1000, 3), "dy": round(e.size.y / 1000, 3)})
    return out


def keyplan_dxf(doc, found, path):
    """
    کی‌پلن تمیز از کی‌پلن بارگذاری‌شده: هر پی با ستون‌هایش در همان جا و جهت نقشه اصلی، نام تیپ،
    و جدول تیپ‌ها (تعداد، ابعاد، ستون، تجهیز). فقط پی‌هایی که درست خوانده شده‌اند.
    """
    import math
    import ezdxf
    from ezdxf import bbox, zoom
    ok = {f.name: f for f in found if f.ok}
    out = ezdxf.new("R2010", setup=True)
    out.header["$INSUNITS"] = 4
    for name, color in (("FOUNDATION", 7), ("PEDESTAL", 1), ("TEXT", 2), ("TABLE", 7)):
        out.layers.add(name, color=color)
    msp = out.modelspace()
    for f in ok.values():                       # بلاک هر تیپ، مرکز پی روی مبدأ
        blk = out.blocks.new(f.name)
        L, B, b = f.L * 1000, f.B * 1000, (f.b or 0.6) * 1000
        blk.add_lwpolyline([(-L / 2, -B / 2), (L / 2, -B / 2), (L / 2, B / 2), (-L / 2, B / 2)],
                           close=True, dxfattribs={"layer": "FOUNDATION"})
        for g in f.groups:
            for x, y in g["positions"]:
                x, y = x * 1000, y * 1000
                blk.add_lwpolyline([(x - b / 2, y - b / 2), (x + b / 2, y - b / 2),
                                    (x + b / 2, y + b / 2), (x - b / 2, y + b / 2)], close=True,
                                   dxfattribs={"layer": "PEDESTAL"})
    centre = {}
    for name in ok:
        rects = _rects(doc.blocks.get(name))
        pad = max(rects, key=lambda r: (r[2] - r[0]) * (r[3] - r[1]))
        centre[name] = ((pad[0] + pad[2]) / 2, (pad[1] + pad[3]) / 2)
    for ins in doc.modelspace().query("INSERT"):
        if ins.dxf.name not in ok:
            continue
        m = ins.matrix44()
        X, Y, _ = m.transform(centre[ins.dxf.name] + (0,))
        sx, sy = ins.dxf.xscale, ins.dxf.yscale
        msp.add_blockref(ins.dxf.name, (X, Y), dxfattribs={
            "rotation": ins.dxf.rotation, "xscale": math.copysign(1, sx), "yscale": math.copysign(1, sy),
            "layer": "FOUNDATION"})
        f = ok[ins.dxf.name]
        a = math.radians(ins.dxf.rotation)                   # نیم‌پهنای پی در امتداد x نقشه
        hx = (abs(math.cos(a)) * f.L + abs(math.sin(a)) * f.B) * 500
        msp.add_text(ins.dxf.name, height=150, dxfattribs={"layer": "TEXT"}).set_placement(
            (X - hx - 250, Y), align=ezdxf.enums.TextEntityAlignment.MIDDLE_RIGHT)
    ext = bbox.extents(msp)
    if ext.has_data:                            # جدول تیپ‌ها کنار نقشه
        x0, y0 = ext.extmax.x + 3000, ext.extmax.y
        cols = [("TYPE", 5000), ("NO.", 1200), ("L x B (m)", 2600), ("PEDESTAL", 2600), ("EQUIPMENT", 5200)]
        rows = [[f.name, str(f.count), f"{f.L:g} x {f.B:g}",
                 f"{sum(len(g['positions']) for g in f.groups)} x {f.b:g}", f.describe()]
                for f in sorted(ok.values(), key=lambda f: f.name)]
        rows.append(["TOTAL", str(sum(f.count for f in ok.values())), "", "", ""])
        h = 500
        for r, row in enumerate([[c for c, _ in cols]] + rows):
            x = x0
            for (c, w), val in zip(cols, row):
                msp.add_lwpolyline([(x, y0 - r * h), (x + w, y0 - r * h), (x + w, y0 - (r + 1) * h),
                                    (x, y0 - (r + 1) * h)], close=True, dxfattribs={"layer": "TABLE"})
                msp.add_text(val, height=180, dxfattribs={"layer": "TEXT"}).set_placement(
                    (x + 120, y0 - r * h - h / 2), align=ezdxf.enums.TextEntityAlignment.MIDDLE_LEFT)
                x += w
    zoom.extents(msp, factor=1.1)
    ext = bbox.extents(msp)
    if ext.has_data:
        out.header["$EXTMIN"], out.header["$EXTMAX"] = ext.extmin, ext.extmax
    out.saveas(path)
    return path
