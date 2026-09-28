"""
طراحی فونداسیون‌های یک ردیف تجهیزات (بی) با محدودیت فضا.

ورودی همان زنجیره اندازه‌ای است که در برش طولی نقشه جانمایی (Layout / Section) آمده:

    GM 1700 PR/TR 3500 LA 2000 CT 2000 CB 2500 DS 2000 PI 1500 PI+CVT 1500 PI ...

نام‌ها ایستگاه‌های روی محور ردیف‌اند و عددها فاصله محور تا محور (میلی‌متر). نام تجهیزی
که برنامه نمی‌شناسد (دکل، ترانسفورماتور، جاده) مانع است: جای آن حفظ می‌شود و با
PR/TR[4.0] می‌توان پهنای اشغالی‌اش را (m) داد. «+» یعنی دو تجهیز روی یک ایستگاه.

روش:
    ۱. برای هر واحد، «مرز طراحی»: به ازای هر عرض B (امتداد ردیف) کوچک‌ترین L و ضخامت
       پی که همه کنترل‌های پایداری را پاس کند.
    ۲. انتخاب B همه واحدها با برنامه‌ریزی پویا روی زنجیره: پی‌های مجاور هم‌پوشانی
       ندارند (دست‌کم فاصله آزاد gap) و حجم کل بتن پی کمینه است — جواب دقیق.
    ۳. اگر دو واحد مجاور در هیچ ترکیبی جا نشوند، روی یک پی مشترک ادغام می‌شوند
       (مثل LA+CVT) و دوباره از ۱.
"""
import math
import re
from dataclasses import dataclass, field

from engine import analyse, Geometry, from_config
from equipment import ALL_EQUIPMENT, VOLTAGE_LEVELS
from keyplan import KEYPLAN_TOKENS, VARIANTS
from padlayout import Group, PadLayout, row

STEP = 0.1


@dataclass
class Station:
    label: str
    pos: float                         # موقعیت روی محور ردیف (m)
    keys: list                         # کلیدهای کاتالوگ؛ خالی = مانع
    width: float = 0.0                 # پهنای اشغالی مانع در امتداد ردیف (m)
    y: float = 0.0                     # موقعیت عرضی (عمود بر ردیف، m) — از نقشه جانمایی
    depth: float = 0.0                 # عمق اشغالی مانع عمود بر ردیف؛ صفر = تمام عرض ردیف


@dataclass
class Unit:
    stations: list                     # [Station] روی یک پی
    options: list = field(default_factory=list)   # [(B, L, tf, حجم)]
    choice: tuple = None
    layout: object = None
    offset: float = 0.0                # مرکز پی نسبت به میانگین ایستگاه‌ها در امتداد ردیف

    @property
    def axis(self):
        return sum(s.pos for s in self.stations) / len(self.stations)

    @property
    def cy(self):
        """موقعیت عرضی محور پی (عمود بر ردیف)."""
        return sum(s.y for s in self.stations) / len(self.stations)

    @property
    def centre(self):
        """مرکز پی روی محور ردیف (مرکز جای ستون‌ها)."""
        return self.axis + self.offset

    @property
    def label(self):
        return "+".join(s.label for s in self.stations)


def parse(text, voltage="63"):
    """زنجیره ← [Station]؛ عدد بزرگ‌تر از ۵۰ میلی‌متر، وگرنه متر."""
    types = VOLTAGE_LEVELS[voltage]["types"]
    tokens = text.replace("،", " ").replace(",", " ").split()
    stations, pos, expect_name = [], 0.0, True
    for tok in tokens:
        if re.fullmatch(r"[\d.]+", tok):
            if expect_name:
                raise ValueError(f"دو عدد پشت سر هم در زنجیره: «{tok}»")
            v = float(tok)
            pos += v / 1000 if v > 50 else v
            expect_name = True
            continue
        if not expect_name:
            raise ValueError(f"بین «{stations[-1].label}» و «{tok}» فاصله نیامده")
        m = re.fullmatch(r"(.+?)(?:\[([\d.]+)\])?", tok)
        name, width = m.group(1), float(m.group(2) or 0)
        keys = []
        for part in name.upper().split("+"):
            t = KEYPLAN_TOKENS.get(part) or KEYPLAN_TOKENS.get(part.split("/")[0]) \
                if part not in ("LT/GA", "PR/TR", "AUX/TR", "GM", "GA", "ROAD", "NCT") else None
            cands = ([types[t]] if t in types else
                     [types[v] for v in VARIANTS.get(t, [t]) if v in types]) if t else []
            if cands:
                keys.append(cands[0])
        stations.append(Station(name, pos, keys, width))
        expect_name = False
    if not stations:
        raise ValueError("زنجیره خالی است")
    return stations


def _layout(unit):
    """
    چیدمان ستون‌های واحد: ایستگاه‌ها در امتداد Y، ردیف ستون‌های هر تجهیز در امتداد X؛
    در پایان مرکز پی روی مرکز جای ستون‌ها گذاشته می‌شود (unit.offset).
    """
    c = unit.axis
    groups, taken = [], {}
    for st in unit.stations:
        y = st.pos - c
        x = 0.0
        for k, key in enumerate(st.keys):
            eq = ALL_EQUIPMENT[key]
            g = row(eq, y=y)
            if k:                                  # دو تجهیز روی یک ایستگاه: کنار هم در X
                prev = groups[-1]
                w_prev = (max(p[0] for p in prev.positions) - min(p[0] for p in prev.positions)
                          if prev.positions else 0.0)
                w_new = (max(p[0] for p in g.positions) - min(p[0] for p in g.positions)
                         if g.positions else 0.0)
                x = (w_prev + w_new) / 2 + 0.9
                shift = x / 2
                prev.positions = [(px - shift, py) for px, py in prev.positions]
                g.positions = [(px + shift, py) for px, py in g.positions]
            groups.append(g)
        taken[st.label] = y
    for g in groups:
        if g.positions is None:
            raise ValueError(f"فاصله ستون‌های «{g.eq.tag}» در کاتالوگ این سطح ولتاژ نیامده است")
    pts = [p for g in groups for p in g.positions]
    mx = (max(p[0] for p in pts) + min(p[0] for p in pts)) / 2
    my = (max(p[1] for p in pts) + min(p[1] for p in pts)) / 2
    for g in groups:
        g.positions = [(round(px - mx, 6), round(py - my, 6)) for px, py in g.positions]
    unit.offset = my
    return PadLayout(groups)


def frontier(unit, cfg, soil, wind, ch, cv, B_hi=5.0, L_hi=5.0, tf_steps=3):
    """به ازای هر B کوچک‌ترین L (و ضخامت) که کنترل‌های پایداری را پاس کند."""
    f, opt = cfg.foundation, cfg.design
    lay = unit.layout
    fx, fy = lay.footprint(f.b)
    L0 = math.ceil(round((fx + 2 * f.min_projection) / STEP, 6)) * STEP
    B0 = math.ceil(round((fy + 2 * f.min_projection) / STEP, 6)) * STEP
    L0, B0 = max(L0, f.search_min), max(B0, f.search_min)
    out = []
    B = B0
    while B <= B_hi + 1e-9:
        best = None
        for k in range(tf_steps):
            tf = round(f.tf + 0.1 * k, 2)
            L = L0
            while L <= L_hi + 1e-9:
                r = analyse(lay, Geometry(round(L, 2), round(B, 2), f.hp, f.b, tf), soil, wind,
                            ch, cv, opt.governing, opt.bearing)
                if r.ok:
                    vol = L * B * tf
                    if best is None or vol < best[3] - 1e-9:
                        best = (round(B, 2), round(L, 2), tf, vol)
                    break
                L += STEP
        if best:
            out.append(best)
        B += STEP
    return out


def _gap_ok(a_pos, a_B, b_pos, b_B, gap):
    return abs(b_pos - a_pos) - a_B / 2 - b_B / 2 >= gap - 1e-9


def _clear(u, o, ob, gap):
    """
    پی واحد u با گزینه o از مانع ob فاصله آزاد دارد: در امتداد ردیف، یا — اگر مانع عمق
    محدود دارد (نقشه جانمایی) — در عرض ردیف.
    """
    if _gap_ok(u.centre, o[0], ob.pos, ob.width, gap):
        return True
    return ob.depth > 0 and abs(ob.y - u.cy) - o[1] / 2 - ob.depth / 2 >= gap - 1e-9


def _dp(units, obstacles, gap):
    """
    انتخاب B هر واحد: کمینه جمع حجم با شرط فاصله آزاد بین پی‌های مجاور و مانع‌ها.
    خروجی: (انتخاب‌ها یا None، شماره جفت ناسازگار)
    """
    n = len(units)
    INF = float("inf")
    # مانع‌ها فقط حد بالای B هر واحد را محدود می‌کنند
    allowed = []
    for u in units:
        opts = []
        for o in u.options:
            if all(_clear(u, o, ob, gap) for ob in obstacles):
                opts.append(o)
        allowed.append(opts)
    for i, opts in enumerate(allowed):
        if not units[i].options:
            return None, ("size", i)
        if not opts:
            return None, ("obstacle", i)
    cost = [[o[3] for o in allowed[0]]]
    back = [[None] * len(allowed[0])]
    for i in range(1, n):
        row_c, row_b = [], []
        for o in allowed[i]:
            best, arg = INF, None
            for j, p in enumerate(allowed[i - 1]):
                if cost[-1][j] < best and _gap_ok(units[i - 1].centre, p[0], units[i].centre, o[0], gap):
                    best, arg = cost[-1][j], j
            row_c.append(best + o[3] if arg is not None else INF)
            row_b.append(arg)
        if all(c == INF for c in row_c):
            return None, ("pair", i - 1)
        cost.append(row_c)
        back.append(row_b)
    k = min(range(len(cost[-1])), key=lambda j: cost[-1][j])
    picks = [None] * n
    for i in range(n - 1, -1, -1):
        picks[i] = allowed[i][k]
        k = back[i][k] if i else None
    return picks, None


def design_bay(text, cfg, voltage="63", gap=0.20, B_hi=5.0, L_hi=6.0, merge_span=1.6):
    """
    کل ردیف؛ خروجی دیکشنری آماده نمایش (واحدها، ادغام‌ها، هشدارها).
    text: زنجیره متنی، یا فهرست Station که از نقشه جانمایی خوانده شده (layoutplan).
    """
    from pipeline import seismic_coefficients
    stations = parse(text, voltage) if isinstance(text, str) else list(text)
    soil, wind = from_config(cfg)
    obstacles = [s for s in stations if not s.keys]
    units = [Unit([s]) for s in stations if s.keys]
    if not units:
        raise ValueError("هیچ تجهیز قابل طراحی در زنجیره نیست")
    seis_cache = {}

    def prepare(u):
        u.layout = _layout(u)
        key = u.layout.main.tag
        if key not in seis_cache:
            seis_cache[key] = seismic_coefficients(u.layout.main, cfg)
        s = seis_cache[key]
        u.options = frontier(u, cfg, soil, wind, s.ch, s.cv, B_hi, L_hi)

    for u in units:
        prepare(u)
    merges = []
    for _ in range(len(units)):
        picks, bad = _dp(units, obstacles, gap)
        if picks is not None:
            break
        kind, i = bad
        if kind == "size":
            raise ValueError(f"برای «{units[i].label}» تا L و B حداکثر {L_hi:.1f} و {B_hi:.1f} متر "
                             "پی پایداری پیدا نشد")
        if kind == "obstacle" or i + 1 >= len(units):
            raise ValueError(f"«{units[i].label}» حتی با پی مشترک در فضای موجود جا نمی‌شود — "
                             "فاصله تا مانع کم است")
        a, b = units[i], units[i + 1]
        merged = Unit(a.stations + b.stations)
        prepare(merged)
        merges.append((a.label, b.label, round(b.centre - a.centre, 3), "کمبود فضا"))
        units[i:i + 2] = [merged]
    else:
        raise ValueError("چیدمان ردیف پیدا نشد")
    # ادغام اختیاری: اگر پی مشترک دو واحد مجاور بتن کمتری بخواهد، ادغام می‌شوند
    total = lambda ps: sum(p[3] for p in ps)
    improved = True
    while improved and len(units) > 1:
        improved = False
        best = None
        for i in range(len(units) - 1):
            a, b = units[i], units[i + 1]
            if b.centre - a.centre > merge_span:
                continue
            merged = Unit(a.stations + b.stations)
            prepare(merged)
            if not merged.options:
                continue
            trial = units[:i] + [merged] + units[i + 2:]
            p2, bad = _dp(trial, obstacles, gap)
            if p2 is not None and total(p2) < total(picks) - 1e-6 and (
                    best is None or total(p2) < best[0]):
                best = (total(p2), i, trial, p2, (a.label, b.label, round(b.centre - a.centre, 3)))
        if best:
            _, i, units, picks, info = best
            merges.append(info + ("کاهش حجم بتن",))
            improved = True
    for u, p in zip(units, picks):
        u.choice = p
    return {"stations": stations, "units": units, "obstacles": obstacles, "merges": merges,
            "gap": gap}


# ------------------------------------------------------------------ کنترل کامل و خروجی
def unit_spec(u):
    """چیدمان واحد به شکل ورودی calc_service.layout_from_spec (برای ثبت محاسبه)."""
    from dataclasses import asdict
    groups = []
    for i, g in enumerate(u.layout.groups):
        item = {"positions": [list(p) for p in g.positions]}
        if i:
            item["equipment"] = asdict(g.eq)
        groups.append(item)
    return {"kind": "combined", "source": f"ردیف: {u.label}", "groups": groups}


def verify(result, cfg, max_extra_tf=0.3):
    """
    طراحی کامل هر پی انتخاب‌شده (ستون، پانچ، برش، میل مهار، سازه). اگر کنترلی جز
    پایداری رد شود، ضخامت پی ۱۰ سانت‌ـ۱۰ سانت بیشتر می‌شود.
    """
    import copy
    from pipeline import run_layout
    for u in result["units"]:
        B, L, tf, _ = u.choice
        extra = 0.0
        while True:
            c = copy.deepcopy(cfg)
            c.foundation.L, c.foundation.B, c.foundation.tf = L, B, round(tf + extra, 2)
            out = run_layout(u.layout, c)
            res, seis, des = out[0], out[1], out[2]
            import model as M
            ok = (res is not None and res.ok and all(d.ok for k, d in des.items() if k != "groups")
                  and not M.clashes(M.build(res, res.layout, des, c))
                  and all(sd.ok for _, sd in getattr(res, "structures", []) or []))
            if ok or extra >= max_extra_tf - 1e-9:
                break
            extra += 0.1
        u.cfg, u.out, u.ok = c, out, ok
        u.choice = (B, L, round(tf + extra, 2), L * B * (tf + extra))
    return result


def plan_dxf(result, path, title="BAY FOUNDATION PLAN"):
    """کی‌پلن ردیف (mm): پی‌ها، ستون‌ها، محور ایستگاه‌ها، زنجیره اندازه و برچسب هر پی."""
    import ezdxf
    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = 4
    for name, color in (("FOUNDATION", 7), ("PEDESTAL", 1), ("AXIS", 8), ("DIM", 3), ("TEXT", 2),
                        ("OBSTACLE", 9)):
        doc.layers.add(name, color=color)
    msp = doc.modelspace()
    k = 1000.0
    ys = [0.0]
    for u in result["units"]:
        B, L, tf, _ = u.choice
        cx = u.centre * k
        ys.append(L / 2 * k)
        name = f"{u.label}-{L:g}-{B:g}"
        msp.add_lwpolyline([(cx - B * k / 2, -L * k / 2), (cx + B * k / 2, -L * k / 2),
                            (cx + B * k / 2, L * k / 2), (cx - B * k / 2, L * k / 2)],
                           close=True, dxfattribs={"layer": "FOUNDATION"})
        b = u.cfg.foundation.b * k if hasattr(u, "cfg") else 600
        for g in u.layout.groups:
            for px, py in g.positions:
                x, y = cx + py * k, px * k
                msp.add_lwpolyline([(x - b / 2, y - b / 2), (x + b / 2, y - b / 2),
                                    (x + b / 2, y + b / 2), (x - b / 2, y + b / 2)],
                                   close=True, dxfattribs={"layer": "PEDESTAL"})
        msp.add_text(name, height=120, dxfattribs={"layer": "TEXT"}).set_placement(
            (cx, L * k / 2 + 250), align=ezdxf.enums.TextEntityAlignment.BOTTOM_CENTER)
        d = msp.add_linear_dim(base=(cx, -L * k / 2 - 400), p1=(cx - B * k / 2, -L * k / 2),
                               p2=(cx + B * k / 2, -L * k / 2), dxfattribs={"layer": "DIM"})
        d.render()
    top = max(ys) + 900
    for s in result["stations"]:
        x = s.pos * k
        msp.add_line((x, -top), (x, top), dxfattribs={"layer": "AXIS", "linetype": "CENTER"})
        msp.add_text(s.label, height=150, dxfattribs={"layer": "TEXT"}).set_placement(
            (x, top + 120), align=ezdxf.enums.TextEntityAlignment.BOTTOM_CENTER)
        if not s.keys and s.width:
            w = s.width * k
            msp.add_lwpolyline([(x - w / 2, -top * 0.6), (x + w / 2, -top * 0.6),
                                (x + w / 2, top * 0.6), (x - w / 2, top * 0.6)], close=True,
                               dxfattribs={"layer": "OBSTACLE"})
    for a, b in zip(result["stations"], result["stations"][1:]):
        d = msp.add_linear_dim(base=(0, top + 600), p1=(a.pos * k, top), p2=(b.pos * k, top),
                               dxfattribs={"layer": "DIM"})
        d.render()
    msp.add_text(title, height=250, dxfattribs={"layer": "TEXT"}).set_placement(
        (result["stations"][0].pos * k, -top - 700))
    doc.saveas(path)
    return path
