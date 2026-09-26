"""
زنجیره کامل محاسبه برای یک تجهیز:
    ضریب زلزله ← جست‌وجوی ابعاد ← طراحی مقطع ← متره ← لیست آرماتور

خط فرمان و سامانه وب هر دو از همین تابع استفاده می‌کنند، تا نتیجه یک
ورودی در هر دو دقیقاً یکی باشد.
"""
from config import ProjectConfig
from equipment import Equipment
from engine import from_config, find_dimensions, quantities
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


def run(equipment: Equipment, cfg: ProjectConfig):
    soil, wind = from_config(cfg)
    seis = seismic_coefficients(equipment, cfg)
    f = cfg.foundation
    res = find_dimensions(equipment, soil, wind, seis.ch, seis.cv,
                          hp=f.hp, b=f.b, tf=f.tf,
                          lo=f.search_min, hi=f.search_max, step=f.search_step)
    if res is None:
        return None, seis, None, None, None
    des = design_all(res, equipment, soil, cfg.rebar)
    qty = quantities(res, equipment, soil)
    bbs = bar_schedule(model.build(res, equipment, des, cfg))
    qty["rebar"] = sum(r["weight"] for r in bbs)
    return res, seis, des, qty, bbs
