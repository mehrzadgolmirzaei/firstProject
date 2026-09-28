"""
خواندن نقشه جانمایی الکتریکال (Layout / General Plan، DXF) و طراحی همه فونداسیون‌ها از روی آن.

از نقشه فقط آنچه واقعاً در آن هست خوانده می‌شود: جای هر تجهیز و فضای اطرافش.
    ۱. هندسه هر بلاک (با بلاک‌های تو در تو و جسم‌های سه‌بعدی ACIS) به مختصات واقعی.
    ۲. «ایستگاه»: بلاک‌هایی که روی زمین می‌نشینند (سازه، ترانس، دکل) و هم‌پوشان‌ها با هم؛
       تجهیز روی سازه (بالاتر از زمین) به ایستگاه زیر خود می‌پیوندد.
    ۳. نوع ایستگاه از نام بلاک‌هایش (LA، CT، CB، DS، CVT، PI …) با کاتالوگ همان سطح ولتاژ؛
       اگر جای پای سازه برای ستون‌های کاتالوگ کافی نباشد، تجهیز دیگری است و مانع حساب می‌شود.
    ۴. امتداد ردیف‌ها از جهت بلاک‌ها؛ ایستگاه‌های هم‌محور یک ردیف (یا ستون) می‌شوند.
    ۵. هر ردیف با bay.design_bay طراحی می‌شود؛ هر چیز دیگر نقشه (ترانس، دکل، ردیف‌های کناری)
       با ابعاد واقعی‌اش مانع دوبعدی است: کنار ردیف طول L را محدود می‌کند، در ردیف عرض B را.

آرایش ستون‌های هر تجهیز از کاتالوگ است (سازه‌های مدل سه‌بعدی نقشه جانمایی نمادین‌اند).
"""
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

import numpy as np

from equipment import ALL_EQUIPMENT, VOLTAGE_LEVELS
from keyplan import VARIANTS

GROUND_TOL = 300.0          # mm — بلاکی که پایش تا این فاصله از زمین است روی زمین نشسته
MIN_HEIGHT = 500.0          # mm — نماد تخت (مثل پلان ارت) ایستگاه نیست
MAX_SIZE = 20000.0          # mm — بلاک بزرگ‌تر (پلان محوطه، ساختمان، کادر) ایستگاه تجهیز نیست
ROW_TOL = 0.6               # m — ایستگاه‌های هم‌محور یک ردیف
NEAR = 8.0                  # m — مانع‌هایی که در طراحی یک ردیف دیده می‌شوند

# نام تجهیز در بلاک‌های نقشه ← نوع (همان نام‌های کی‌پلن)
TOKENS = {"LA": "LA", "CB": "CB", "CT": "CT", "CVT": "CVT", "CV": "CVT", "PI": "PI",
          "DS": "DSE", "DSE": "DSE", "DS2": "DS2"}
OBSTACLE_TOKENS = {"TR": "TR", "GANTRY": "GANTRY", "GM": "GANTRY"}
PRIORITY = ["DS2", "CVT", "DSE", "CB", "CT", "LA", "PI"]


# ------------------------------------------------------------------ هندسه بلاک‌ها
def _solid_points(e, cache):
    """نقاط جسم سه‌بعدی از داده ACIS (SAB) با تبدیل خود جسم."""
    if id(e) in cache:
        return cache[id(e)]
    pts = []
    try:
        from ezdxf.acis import sab
        dec = sab.Decoder(e.sab)
        dec.read_header()
        recs = list(dec.read_records())
        T = None
        for rec in recs:
            if rec[0].value == "transform":
                v = [t.value for t in rec if t.tag == 20]
                sc = [t.value for t in rec if t.tag == 6]
                T = (np.array(v[:3]), np.array(v[3]), sc[0] if sc else 1.0)
                break
        for rec in recs:
            if rec[0].value in ("point", "ellipse-curve"):
                for t in rec:
                    if t.tag == 19:
                        pts.append(t.value)
                        break
        if T is not None and pts:
            R, tr, sc = T
            pts = [tuple(np.array(p) @ R * sc + tr) for p in pts]
    except Exception:
        pts = []
    cache[id(e)] = pts
    return pts


def _local_points(e, cache):
    from ezdxf.math import OCS, Vec3
    t = e.dxftype()
    if t == "3DSOLID" or t.endswith("SURFACE") or t == "REGION":
        return _solid_points(e, cache)
    if t == "3DFACE":
        return [e.dxf.get(f"vtx{i}") for i in range(4) if e.dxf.hasattr(f"vtx{i}")]
    if t == "LINE":
        return [e.dxf.start, e.dxf.end]
    if t == "POINT":
        return [e.dxf.location]
    ext = e.dxf.extrusion if e.dxf.is_supported("extrusion") and e.dxf.hasattr("extrusion") \
        else (0, 0, 1)
    ocs = OCS(ext)
    if t in ("CIRCLE", "ARC"):
        c, r = Vec3(e.dxf.center), e.dxf.radius
        return [ocs.to_wcs(c + Vec3(dx, dy, 0)) for dx, dy in ((r, 0), (-r, 0), (0, r), (0, -r))]
    if t == "LWPOLYLINE":
        z = e.dxf.elevation
        return [ocs.to_wcs(Vec3(x, y, z)) for x, y in e.get_points("xy")]
    if t == "POLYLINE":
        return [v.dxf.location if e.is_3d_polyline else ocs.to_wcs(v.dxf.location)
                for v in e.vertices]
    if t == "SOLID":
        return [ocs.to_wcs(e.dxf.get(f"vtx{i}")) for i in range(4) if e.dxf.hasattr(f"vtx{i}")]
    return []


def _insert_points(doc, ins, M, cache, depth=0):
    from ezdxf.math import Matrix44, Vec3
    blk = doc.blocks.get(ins.dxf.name)
    if blk is None or depth > 8 or blk.block_record.is_xref:
        return []
    bp = Vec3(blk.block.dxf.base_point)
    M = Matrix44.translate(-bp.x, -bp.y, -bp.z) @ M
    out = []
    for e in blk:
        if e.dxftype() == "INSERT":
            out += _insert_points(doc, e, e.matrix44() @ M, cache, depth + 1)
        else:
            out += [tuple(M.transform(Vec3(p))) for p in _local_points(e, cache)]
    return out


@dataclass(eq=False)
class Item:
    name: str
    pts: np.ndarray            # mm، مختصات واقعی
    angle: float               # جهت محور x بلاک در پلان (رادیان)
    children: list = field(default_factory=list)   # [(نام بلاک تو در تو، کمترین z)] سطح اول

    @property
    def zmax(self):
        return float(self.pts[:, 2].max())

    @property
    def zmin(self):
        return float(self.pts[:, 2].min())

    @property
    def height(self):
        return float(np.ptp(self.pts[:, 2]))


def read_items(path, doc=None):
    """همه بلاک‌های فضای مدل با هندسه واقعی؛ بلاک تکراری (روی هم) یک بار."""
    if doc is None:
        import ezdxf
        doc = ezdxf.readfile(path)
    cache, seen, items = {}, set(), []
    for e in doc.modelspace().query("INSERT"):
        m = e.matrix44()
        P = _insert_points(doc, e, m, cache)
        if len(P) < 2:
            continue
        P = np.array(P, dtype=float)
        key = (e.dxf.name, round(float(np.median(P[:, 0]))), round(float(np.median(P[:, 1]))))
        if key in seen:
            continue
        seen.add(key)
        ux = m.transform_direction((1, 0, 0))
        # بلاک‌های تو در توی سطح اول (مثلاً سه CT روی سازه در یک بلاک): کمترین z هر کدام
        children = []
        blk = doc.blocks.get(e.dxf.name)
        if blk is not None:
            from ezdxf.math import Matrix44
            bp = blk.block.dxf.base_point
            M = Matrix44.translate(-bp[0], -bp[1], -bp[2]) @ m
            for ch in blk.query("INSERT"):
                cp = _insert_points(doc, ch, ch.matrix44() @ M, cache, 1)
                if cp:
                    children.append((ch.dxf.name, float(min(p[2] for p in cp))))
        items.append(Item(e.dxf.name, P, math.atan2(ux.y, ux.x), children))
    return items


def detect_voltage(items):
    """
    سطح ولتاژ از نام بلاک‌ها (CT63، SI 63، xref-63 …): عدد مستقل ۶۳/۲۳۰/۴۰۰؛ اگر نبود None.
    """
    votes = Counter()
    for it in items:
        for part in it.name.split("$0$"):
            for v in re.findall(r"(?<!\d)(63|230|400)(?!\d)", part):
                votes[v] += 1
    return votes.most_common(1)[0][0] if votes else None


# ------------------------------------------------------------------ نوع تجهیز
def name_tokens(name):
    """«6Bay - Tr 1$0$Ds-e 2250» ← نام خود بلاک (بعد از پیشوند xref) ← نوع‌ها."""
    own = name.split("$0$")[-1].upper()
    found = []
    if "DS2" in own.replace(" ", "").replace("_", ""):
        found.append("DS2")
    for t in re.findall(r"[A-Z]+", own):
        if t in TOKENS and TOKENS[t] not in found and not (t == "DS" and "DS2" in found):
            found.append(TOKENS[t])
        elif t in OBSTACLE_TOKENS:
            found.append(OBSTACLE_TOKENS[t])
    return found


@dataclass(eq=False)
class SiteStation:
    names: list
    x0: float                  # m، در دستگاه ردیف‌ها (پس از چرخش)
    x1: float
    y0: float
    y1: float
    hs: float = 0.0            # ارتفاع سازه از روی نقشه (m)؛ صفر = معلوم نیست
    kind: str = ""             # نوع کی‌پلن (LA، CT …) یا مانع (TR …) یا نامعلوم
    key: str = ""              # کلید کاتالوگ؛ خالی = مانع
    note: str = ""

    @property
    def cx(self):
        return (self.x0 + self.x1) / 2

    @property
    def cy(self):
        return (self.y0 + self.y1) / 2

    @property
    def label(self):
        return self.kind or self.names[0].split("$0$")[-1][:12]


def _structure_height(st, ground):
    """
    ارتفاع سازه نگهدارنده از نقشه سه‌بعدی: سازه پایین‌ترین بلاکِ روی زمینِ ایستگاه است
    (تجهیز روی آن بالاتر می‌رود)، پس ارتفاع = کمترین «بالای بلاک» در بلاک‌های روی زمین.
    اگر سازه و تجهیز در یک بلاک‌اند (مثل CT63)، پای پایین‌ترین تجهیزِ تو در تو.
    """
    base = [it for it in getattr(st, "_base", []) if it.height >= MIN_HEIGHT]
    if not base:
        return 0.0
    if len(base) == 1:
        kinds = {t for n in st.names for t in name_tokens(n)}
        tops = [z for name, z in base[0].children
                if z > ground + MIN_HEIGHT and set(name_tokens(name)) & kinds]
        if tops:
            return round((min(tops) - ground) / 1000, 2)
    return round((min(it.zmax for it in base) - ground) / 1000, 2)


def _frame(items):
    """زاویه غالب بلاک‌ها (به پیمانه ۹۰ درجه): امتداد ردیف‌ها."""
    angs = [((it.angle % (math.pi / 2)) + math.pi / 2) % (math.pi / 2) for it in items]
    if not angs:
        return 0.0
    # میانه دایره‌ای روی ۹۰ درجه
    z = np.mean([np.exp(4j * a) for a in angs])
    a = (np.angle(z) / 4) % (math.pi / 2)
    return a if a <= math.pi / 4 else a - math.pi / 2


def _choose_key(kind, st, types):
    """کلید کاتالوگ: گونه‌ای که ستون‌هایش در جای پای سازه جا شود (CVT سه‌ستونه یا تک‌ستونه)."""
    span = max(st.x1 - st.x0, st.y1 - st.y0)
    for v in VARIANTS.get(kind, [kind]):
        if v not in types:
            continue
        eq = ALL_EQUIPMENT[types[v]]
        need = (eq.n_pedestal - 1) * (eq.pedestal_spacing or 0)
        if span >= 0.6 * need:
            return types[v]
    return ""


def site_stations(items, voltage="63"):
    """ایستگاه‌ها (روی زمین) در دستگاه ردیف‌ها، و زاویه آن دستگاه."""
    types = VOLTAGE_LEVELS[voltage]["types"]
    if not items:
        return [], 0.0, []
    items = [it for it in items if np.ptp(it.pts[:, :2], axis=0).max() <= MAX_SIZE]
    if not items:
        return [], 0.0, []
    zs = Counter(round(it.zmin / 10) * 10 for it in items if it.height >= MIN_HEIGHT)
    ground = zs.most_common(1)[0][0] if zs else min(it.zmin for it in items)
    flat = all(it.height < 1.0 for it in items)
    base = [it for it in items if flat or (it.zmin <= ground + GROUND_TOL and it.height >= MIN_HEIGHT)]
    rest = [it for it in items if it not in base]
    ang = _frame(base)
    c, s = math.cos(-ang), math.sin(-ang)

    def box(it):
        x = (it.pts[:, 0] * c - it.pts[:, 1] * s) / 1000
        y = (it.pts[:, 0] * s + it.pts[:, 1] * c) / 1000
        return [float(x.min()), float(x.max()), float(y.min()), float(y.max())]

    # بلاک‌های روی زمین که هم‌پوشانی دارند یک ایستگاه‌اند (سازه + تجهیز پایه‌دار)
    boxes = [box(it) for it in base]
    parent = list(range(len(base)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i in range(len(base)):
        for j in range(i + 1, len(base)):
            a, b = boxes[i], boxes[j]
            if min(a[1], b[1]) - max(a[0], b[0]) > 0.05 and min(a[3], b[3]) - max(a[2], b[2]) > 0.05:
                parent[find(i)] = find(j)
    groups = defaultdict(list)
    for i in range(len(base)):
        groups[find(i)].append(i)
    stations = []
    for idx in groups.values():
        bx = np.array([boxes[i] for i in idx])
        st = SiteStation([base[i].name for i in idx], bx[:, 0].min(), bx[:, 1].max(),
                         bx[:, 2].min(), bx[:, 3].max())
        st._base = [base[i] for i in idx]
        stations.append(st)
    # تجهیز روی سازه: به ایستگاهی که مرکزش را در بر دارد
    for it in rest:
        b = box(it)
        cx, cy = (b[0] + b[1]) / 2, (b[2] + b[3]) / 2
        for st in stations:
            if st.x0 <= cx <= st.x1 and st.y0 <= cy <= st.y1:
                st.names.append(it.name)
                break
    unknown = set()
    for st in stations:
        st.hs = _structure_height(st, ground)
        found = Counter(t for n in st.names for t in name_tokens(n))
        kinds = [k for k in PRIORITY if found.get(k)]
        obst = [k for k in ("TR", "GANTRY") if found.get(k)]
        if obst and not kinds:
            st.kind = obst[0]
        elif kinds:
            st.kind = kinds[0]
            st.key = _choose_key(st.kind, st, types)
            if not st.key:
                st.note = (f"نام «{st.kind}» دارد ولی جای پای آن برای ستون‌های کاتالوگ کافی "
                           "نیست؛ مانع در نظر گرفته شد")
        else:
            unknown.update(n.split("$0$")[-1] for n in st.names)
    return stations, ang, sorted(unknown)


# ------------------------------------------------------------------ ردیف‌ها
@dataclass
class Row:
    axis: str                  # "x": ردیف در امتداد x ؛ "y": ستونی در امتداد y
    members: list = field(default_factory=list)

    def pos(self, st):
        return st.cx if self.axis == "x" else st.cy

    def cross(self, st):
        return st.cy if self.axis == "x" else st.cx

    def extent(self, st):
        """(پهنا در امتداد ردیف، عمق عمود بر آن)"""
        w, h = st.x1 - st.x0, st.y1 - st.y0
        return (w, h) if self.axis == "x" else (h, w)


def _cluster(values, tol):
    order = sorted(range(len(values)), key=lambda i: values[i])
    groups, cur = [], []
    for i in order:
        if cur and values[i] - values[cur[-1]] > tol:
            groups.append(cur)
            cur = []
        cur.append(i)
    if cur:
        groups.append(cur)
    return groups


def find_rows(stations):
    """ردیف‌های افقی با دست‌کم دو تجهیز؛ باقی‌مانده‌ها ستون‌های عمودی، و تک‌ها ردیف یک‌عضوی."""
    design = [s for s in stations if s.key]
    rows, used = [], set()
    for g in _cluster([s.cy for s in design], ROW_TOL):
        if len(g) > 1:
            rows.append(Row("x", sorted((design[i] for i in g), key=lambda s: s.cx)))
            used.update(id(design[i]) for i in g)
    left = [s for s in design if id(s) not in used]
    for g in _cluster([s.cx for s in left], ROW_TOL):
        members = sorted((left[i] for i in g), key=lambda s: s.cy)
        rows.append(Row("y" if len(members) > 1 else "x", members))
    return rows


def row_stations(row, stations, gap=0.2, B_hi=5.0, L_hi=6.0):
    """ایستگاه‌های bay برای یک ردیف: تجهیزها، و هر چیز دیگر نقشه در نزدیکی به‌صورت مانع."""
    from bay import Station
    out = [Station(s.kind, row.pos(s), [s.key], 0.0, row.cross(s), hs=s.hs) for s in row.members]
    lo = min(row.pos(s) for s in row.members) - B_hi - NEAR
    hi = max(row.pos(s) for s in row.members) + B_hi + NEAR
    ymid = sum(row.cross(s) for s in row.members) / len(row.members)
    for st in stations:
        if st in row.members:
            continue
        w, h = row.extent(st)
        p, y = row.pos(st), row.cross(st)
        if lo <= p <= hi and abs(y - ymid) - h / 2 <= L_hi / 2 + gap + NEAR:
            out.append(Station(st.label, p, [], w, y, max(h, 1e-3)))
    return sorted(out, key=lambda s: s.pos)


# ------------------------------------------------------------------ طراحی کل نقشه
def design_layout(path, cfg, voltage="63", gap=0.20, B_hi=5.0, L_hi=6.0, merge_span=1.6,
                  items=None):
    """
    خروجی: {"foundations": [مثل کی‌پلن]، "rows": [...]، "plan": داده نقشه، "unknown": [...]،
    "notes": [...]}
    """
    import bay
    items = items if items is not None else read_items(path)
    stations, ang, unknown = site_stations(items, voltage)
    if not any(s.key for s in stations):
        raise ValueError("در نقشه تجهیز قابل طراحی (LA، CT، CB، DS، CVT، PI …) پیدا نشد")
    rows = find_rows(stations)
    notes = [f"{s.names[0].split('$0$')[-1]}: {s.note}" for s in stations if s.note]
    pads, row_out, cache = [], [], {}
    for r_i, row in enumerate(rows):
        chain = row_stations(row, stations, gap, B_hi, L_hi)
        sig = tuple((s.label, tuple(s.keys), s.hs, round(s.pos - chain[0].pos, 2),
                     round(s.y - row.cross(row.members[0]), 2), round(s.width, 2),
                     round(s.depth, 2)) for s in chain)
        try:
            if sig in cache:
                res = cache[sig]
                shift_p = chain[0].pos - res["_p0"]
                shift_y = row.cross(row.members[0]) - res["_y0"]
            else:
                res = bay.design_bay(chain, cfg, voltage, gap, B_hi=B_hi, L_hi=L_hi,
                                     merge_span=merge_span)
                res["_p0"], res["_y0"] = chain[0].pos, row.cross(row.members[0])
                cache[sig] = res
                shift_p = shift_y = 0.0
        except ValueError as exc:
            notes.append(f"ردیف {r_i + 1} ({' '.join(s.kind for s in row.members)}): {exc}")
            continue
        units = []
        for u in res["units"]:
            B, L, tf, vol = u.choice
            p, y = u.centre + shift_p, u.cy + shift_y
            cx, cy, dx, dy = (p, y, B, L) if row.axis == "x" else (y, p, L, B)
            pads.append({"label": u.label, "L": L, "B": B, "tf": tf, "volume": vol,
                         "cx": cx, "cy": cy, "dx": dx, "dy": dy, "row": r_i, "unit": u,
                         "along_x": row.axis == "x"})
            units.append(u.label)
        row_out.append({"axis": row.axis, "units": units,
                        "merges": [list(m) for m in res["merges"]]})
    notes += _pad_clashes(pads, gap)
    notes = list(dict.fromkeys(notes))
    found = _foundations(pads)
    for f in found:
        f["b"] = cfg.foundation.b
    return {"foundations": found, "rows": row_out, "angle": ang,
            "plan": _plan(stations, pads), "unknown": unknown, "notes": notes}


def _pad_clashes(pads, gap):
    out = []
    for i, a in enumerate(pads):
        for b in pads[i + 1:]:
            sx = abs(a["cx"] - b["cx"]) - (a["dx"] + b["dx"]) / 2
            sy = abs(a["cy"] - b["cy"]) - (a["dy"] + b["dy"]) / 2
            if max(sx, sy) < gap - 1e-6:
                out.append(f"پی {a['label']} و {b['label']} (ردیف‌های {a['row'] + 1} و {b['row'] + 1}) "
                           f"فاصله آزاد {max(sx, sy):.2f} m دارند")
    return out


NAME_ORDER = ["LA", "CB", "CT", "DSE", "DS2", "PI", "CVT"]


def _foundations(pads):
    """
    پی‌های هم‌نوع و هم‌اندازه یک تیپ‌اند (قرینه هم یکی حساب می‌شود) — همان قالب کی‌پلن
    برای صفحه محاسبه. ترتیب تجهیزها در نام مثل کی‌پلن دفتر (LA+CVT، PI+CVT).
    """
    import json
    rank = lambda tag: next((i for i, k in enumerate(NAME_ORDER) if tag.upper().startswith(k)), 99)
    types = {}
    for p in pads:
        u = p["unit"]
        gs = sorted(((g.eq.tag, [[float(round(x, 3)) + 0.0, float(round(y, 3)) + 0.0] for x, y in g.positions],
                      g.eq.Hs) for g in u.layout.groups), key=lambda g: rank(g[0]))
        groups = [{"tag": t, "positions": pos, "Hs": hs} for t, pos, hs in gs]
        mirror = [{"tag": g["tag"], "positions": sorted([x, -y + 0.0] for x, y in g["positions"]),
                   "Hs": g["Hs"]} for g in groups]
        canon = min(json.dumps([{"tag": g["tag"], "positions": sorted(g["positions"]), "Hs": g["Hs"]}
                                for g in groups]), json.dumps(mirror))
        label = "+".join(sorted(p["label"].split("+"), key=rank))
        key = (label, p["L"], p["B"], p["tf"], canon)
        if key not in types:
            types[key] = {"name": f"{label}-{p['L']:g}-{p['B']:g}", "count": 0, "L": p["L"],
                          "B": p["B"], "tf": p["tf"], "b": 0.0, "groups": groups, "problem": "",
                          "source": "layout",
                          "describe": " + ".join(f"{g['tag']}×{len(g['positions'])}" for g in groups)
                          + " · Hs " + "/".join(f"{g['Hs']:g}" for g in groups)}
        types[key]["count"] += 1
        p["type"] = types[key]["name"]
        own = json.dumps([{"tag": g["tag"], "positions": sorted(g["positions"])} for g in groups])
        p["mirror"] = own != json.dumps([{"tag": g["tag"], "positions": sorted(g["positions"])}
                                         for g in types[key]["groups"]])
    return sorted(types.values(), key=lambda f: f["name"])


def _plan(stations, pads):
    """داده پلان برای نمایش (m، دستگاه ردیف‌ها)."""
    return {"stations": [{"label": s.label, "x0": round(s.x0, 3), "x1": round(s.x1, 3),
                          "y0": round(s.y0, 3), "y1": round(s.y1, 3), "design": bool(s.key)}
                         for s in stations],
            "pads": [{"label": p["label"], "type": p.get("type", ""), "cx": round(p["cx"], 3), "cy": round(p["cy"], 3),
                      "dx": p["dx"], "dy": p["dy"], "L": p["L"], "B": p["B"],
                      "along_x": p["along_x"], "mirror": p.get("mirror", False)} for p in pads]}


def plan_dxf(result, path, angle=None):
    """کی‌پلن فونداسیون کل نقشه (mm) در مختصات واقعی نقشه جانمایی: هر تیپ یک بلاک مثل کی‌پلن دفتر."""
    import ezdxf
    ang = result["angle"] if angle is None else angle
    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = 4
    for name, color in (("FOUNDATION", 7), ("PEDESTAL", 1), ("TEXT", 2), ("EQUIPMENT", 8)):
        doc.layers.add(name, color=color)
    msp = doc.modelspace()
    c, s = math.cos(ang), math.sin(ang)
    for f in result["foundations"]:
        if f["name"] in doc.blocks:
            continue
        blk = doc.blocks.new(f["name"])
        L, B = f["L"] * 1000, f["B"] * 1000
        blk.add_lwpolyline([(-L / 2, -B / 2), (L / 2, -B / 2), (L / 2, B / 2), (-L / 2, B / 2)],
                           close=True, dxfattribs={"layer": "FOUNDATION"})
        b = (f.get("b") or 0.6) * 1000
        for g in f["groups"]:
            for x, y in g["positions"]:
                x, y = x * 1000, y * 1000
                blk.add_lwpolyline([(x - b / 2, y - b / 2), (x + b / 2, y - b / 2),
                                    (x + b / 2, y + b / 2), (x - b / 2, y + b / 2)], close=True,
                                   dxfattribs={"layer": "PEDESTAL"})
    for st in result["plan"]["stations"]:
        pts = [(st["x0"], st["y0"]), (st["x1"], st["y0"]), (st["x1"], st["y1"]), (st["x0"], st["y1"])]
        msp.add_lwpolyline([((x * c - y * s) * 1000, (x * s + y * c) * 1000) for x, y in pts],
                           close=True, dxfattribs={"layer": "EQUIPMENT"})
    for p in result["plan"]["pads"]:
        # بلاک: x در امتداد L (عمود بر ردیف)، y در امتداد ردیف. ردیف افقی: جابه‌جایی محورها
        # = دوران ۹۰ درجه با قرینه y ؛ ستون عمودی: همان جهت.
        sy = (-1 if p["along_x"] else 1) * (-1 if p["mirror"] else 1)
        rot = math.degrees(ang) + (90 if p["along_x"] else 0)
        X, Y = (p["cx"] * c - p["cy"] * s) * 1000, (p["cx"] * s + p["cy"] * c) * 1000
        if p["type"] in doc.blocks:
            msp.add_blockref(p["type"], (X, Y), dxfattribs={"rotation": rot, "yscale": sy,
                                                             "layer": "FOUNDATION"})
        msp.add_text(p["type"], height=150, rotation=math.degrees(ang),
                     dxfattribs={"layer": "TEXT"}).set_placement(
            (X - s * (p["dy"] * 500 + 250), Y + c * (p["dy"] * 500 + 250)))
    from ezdxf import zoom
    zoom.extents(msp, factor=1.1)       # اتوکد روی خود نقشه باز شود، نه مبدأ
    from ezdxf import bbox
    ext = bbox.extents(msp)
    if ext.has_data:
        doc.header["$EXTMIN"], doc.header["$EXTMAX"] = ext.extmin, ext.extmax
    doc.saveas(path)
    return path


# ------------------------------------------------------------------ طراحی کامل همه تیپ‌ها
def design_all(result, cfg, max_extra_tf=0.3):
    """
    طراحی کامل هر تیپ پی نقشه (ستون، آرماتور، برش، پانچ، میل مهار، سازه فولادی و کنترل تداخل)؛
    اگر کنترلی جز پایداری رد شود، ضخامت پی ۱۰ سانت‌ـ۱۰ سانت بیشتر می‌شود.
    خروجی: [(تیپ، چیدمان، cfg، (res, seis, des, qty, bbs)، ok)]
    """
    import copy
    import model as M
    from padlayout import Group, PadLayout
    from pipeline import run_layout
    out = []
    for f in result["foundations"]:
        from equipment import with_structure_height
        lay = PadLayout([Group(with_structure_height(ALL_EQUIPMENT[g["tag"]], g.get("Hs")),
                               [tuple(p) for p in g["positions"]]) for g in f["groups"]])
        extra = 0.0
        while True:
            c = copy.deepcopy(cfg)
            c.foundation.L, c.foundation.B = f["L"], f["B"]
            c.foundation.tf = round(f["tf"] + extra, 2)
            run = run_layout(lay, c)
            res, des = run[0], run[2]
            # ضخامت پی فقط برای کنترل‌های خود پی بیشتر می‌شود؛ رد شدن سازه با پی حل نمی‌شود
            found_ok = (res is not None and res.ok
                        and all(d.ok for k, d in des.items() if k != "groups")
                        and not M.clashes(M.build(res, res.layout, des, c)))
            if found_ok or extra >= max_extra_tf - 1e-9:
                break
            extra += 0.1
        ok = found_ok and all(sd.ok for _, sd in getattr(res, "structures", []) or [])
        out.append((f, lay, c, run, ok))
    return out
