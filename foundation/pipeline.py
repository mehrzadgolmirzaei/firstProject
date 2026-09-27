"""
زنجیره کامل محاسبه برای یک تجهیز:
    ضریب زلزله ← جست‌وجوی ابعاد ← طراحی مقطع ← متره ← لیست آرماتور

خط فرمان و سامانه وب هر دو از همین تابع استفاده می‌کنند، تا نتیجه یک
ورودی در هر دو دقیقاً یکی باشد.
"""
from config import ProjectConfig
from equipment import Equipment
from engine import from_config, find_dimensions, quantities, RECOMMENDED
from seismic import Site2800v5, Site2800v4, period
from design import design_all
from schedule import bar_schedule
import model


def seismic_coefficients(equipment: Equipment, cfg: ProjectConfig):
    s = cfg.seismic
    # اگر سختی جانبی داده شده باشد، روش از روی زمان تناوب انتخاب می‌شود
    w_eff = equipment.We + equipment.Ws / 3
    t_period, suggested, note = period(w_eff, s.k_lateral)
    if suggested and s.auto_method:
        s.method = suggested
    seis = (Site2800v4(a=s.a, b=s.b, i=s.i, r=s.r).compute() if s.edition == 4
            else Site2800v5(ss=s.ss, s1=s.s1, soil=s.soil_class, ie=s.ie,
                            ru=s.ru, method=s.method, map_date=s.map_date).compute())
    seis.period = t_period
    seis.period_note = note or ""
    if note:
        seis.steps.insert(0, ("زمان تناوب", "T = 2π·√(W/(g·k))   بند ۵-۵-۱", note))
    return seis


PROFILES = [
    ("notebook", "روش دفترچه", {"governing": "notebook", "bearing": "min"}),
    ("recommended", "پیشنهاد سامانه", RECOMMENDED),
]


def compare(search, opt):
    """
    ابعاد پی با روش دفترچه، با پیشنهاد سامانه و با انتخاب مهندس — تا اثر
    انتخاب کنار هم دیده شود.
    """
    rows, seen = [], {}
    chosen = {"governing": str(opt.governing), "bearing": opt.bearing}
    for key, label, o in PROFILES + [("selected", "انتخاب شما", chosen)]:
        sig = (o["governing"], o["bearing"])
        if sig not in seen:
            r = search(*sig)
            seen[sig] = None if r is None else (r.geometry.L, r.geometry.B)
        dims = seen[sig]
        rows.append({"key": key, "label": label, **o,
                     "side": dims and dims[0], "L": dims and dims[0], "B": dims and dims[1],
                     "selected": sig == (chosen["governing"], chosen["bearing"])})
    return rows


def run(equipment: Equipment, cfg: ProjectConfig):
    """یک تجهیز روی پی خودش (منفرد، یا مشترک اگر چند ستون با فاصله معلوم دارد)."""
    from padlayout import PadLayout
    return run_layout(PadLayout.single(equipment), cfg)


from dataclasses import asdict

_STRUCTURE_CACHE = {}               # همان تجهیز و همان ساختگاه ← همان طرح سازه
MANUFACTURER_STRUCTURE = {"CB"}     # سازه را سازنده تجهیز می‌دهد؛ برنامه طراحی نمی‌کند


def design_structures(layout, cfg, wind, seis):
    """
    سازه فولادی هر تجهیز پی: ساخت، تحلیل و طراحی در خود برنامه (structural/).
    اگر cfg.steel.feed_foundation روشن باشد، وزن و سطح بادگیر سازه که به پی می‌رود از
    همین سازه است (وزن اعضا × ضریب اتصالات، و سطح وجه رو به باد).
    خروجی: (چیدمان با تجهیزهای به‌روزشده، [(شماره گروه، طرح سازه)])
    """
    import copy
    from equipment import equipment_type
    from padlayout import Group, PadLayout
    from structural.steel_design import design_structure
    st = cfg.steel
    if not st.enabled:
        return layout, []
    designs, groups = [], []
    for gi, g in enumerate(layout.groups):
        eq = g.eq
        if equipment_type(eq.tag) in MANUFACTURER_STRUCTURE or not eq.Hs:
            groups.append(g)
            continue
        key = (repr(sorted(asdict(eq).items())), repr(asdict(st)), wind.v_normal, wind.v_high,
               wind.sc_ratio, round(seis.ch, 9), round(seis.cv, 9))
        d = _STRUCTURE_CACHE.get(key)
        if d is None:
            d = _STRUCTURE_CACHE[key] = design_structure(eq, st, wind, seis.ch, seis.cv)
        designs.append((gi, d))
        if st.feed_foundation:
            eq = copy.copy(eq)
            eq.Ws = round(d.weight * st.connection_factor * d.stands, 1)
            eq.As = round(d.wind_area * d.stands, 3)
        groups.append(Group(eq, g.positions, g.case, g.n_legacy))
    return PadLayout(groups, square=layout.square), designs


def run_layout(layout, cfg: ProjectConfig):
    """یک پی با یک یا چند گروه تجهیز (padlayout.PadLayout)."""
    equipment = layout.main
    soil, wind = from_config(cfg)
    seis = seismic_coefficients(equipment, cfg)
    layout, structures = design_structures(layout, cfg, wind, seis)
    equipment = layout.main
    f, opt = cfg.foundation, cfg.design

    def search(governing, bearing):
        return find_dimensions(layout, soil, wind, seis.ch, seis.cv,
                               hp=f.hp, b=f.b, tf=f.tf,
                               lo=f.search_min, hi=f.search_max, step=f.search_step,
                               governing=governing, bearing=bearing,
                               min_projection=f.min_projection, L=f.L, B=f.B)

    res = search(opt.governing, opt.bearing)
    if res is not None:
        res.comparison = compare(search, opt)
    if res is None:
        return None, seis, None, None, None
    res.structures = structures
    des = design_all(res, layout, soil, cfg.rebar, cfg.anchorage)
    qty = quantities(res, equipment, soil)
    bbs = bar_schedule(model.build(res, layout, des, cfg))
    qty["rebar"] = sum(r["weight"] for r in bbs)
    return res, seis, des, qty, bbs
