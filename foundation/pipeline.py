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
            seen[sig] = None if r is None else r.geometry.L
        rows.append({"key": key, "label": label, **o, "side": seen[sig],
                     "selected": sig == (chosen["governing"], chosen["bearing"])})
    return rows


def run(equipment: Equipment, cfg: ProjectConfig):
    soil, wind = from_config(cfg)
    seis = seismic_coefficients(equipment, cfg)
    f, opt = cfg.foundation, cfg.design

    def search(governing, bearing):
        return find_dimensions(equipment, soil, wind, seis.ch, seis.cv,
                               hp=f.hp, b=f.b, tf=f.tf,
                               lo=f.search_min, hi=f.search_max, step=f.search_step,
                               governing=governing, bearing=bearing)

    res = search(opt.governing, opt.bearing)
    if res is not None:
        res.comparison = compare(search, opt)
    if res is None:
        return None, seis, None, None, None
    des = design_all(res, equipment, soil, cfg.rebar)
    qty = quantities(res, equipment, soil)
    bbs = bar_schedule(model.build(res, equipment, des, cfg))
    qty["rebar"] = sum(r["weight"] for r in bbs)
    return res, seis, des, qty, bbs
