"""
پل بین سامانه وب و موتور محاسبه.

موتور دست‌نخورده می‌ماند؛ اینجا فقط ورودی وب به اشیای موتور تبدیل می‌شود و
خروجی به ساختار قابل ذخیره و نمایش برمی‌گردد.
"""
import sys, json
from pathlib import Path
from dataclasses import replace

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import ProjectConfig                      # noqa: E402
from equipment import Equipment, CATALOG              # noqa: E402
from engine import from_config, find_dimensions, quantities   # noqa: E402
from seismic import Site2800v5, Site2800v4, period    # noqa: E402
from design import design_all                         # noqa: E402

REBAR_UNIT = lambda d: 0.006165 * d * d


def build_equipment(data: dict) -> Equipment:
    """ساخت شیء تجهیز از دیکشنری کاتالوگ یا فرم."""
    allowed = Equipment.__dataclass_fields__
    kwargs = {k: v for k, v in data.items() if k in allowed and v not in ("", None)}
    kwargs.setdefault("tag", data.get("tag", "EQ"))
    kwargs.setdefault("title", data.get("title", kwargs["tag"]))
    for num in ("He", "Ae", "We", "he", "Ce", "Hs", "As", "Ws", "hs",
                "Wc", "Fc", "Fc_sc", "op_vertical", "op_horizontal", "op_moment",
                "pedestal_spacing", "anchor_gauge", "anchor_embed", "base_plate"):
        if num in kwargs:
            kwargs[num] = float(kwargs[num])
    for i in ("npol", "n_pedestal", "anchor_n", "anchor_dia"):
        if i in kwargs:
            kwargs[i] = int(float(kwargs[i]))
    if isinstance(kwargs.get("conductor_points"), str):
        pts = [p for p in kwargs["conductor_points"].replace("،", ",").split(",") if p.strip()]
        kwargs["conductor_points"] = [float(p) for p in pts]
    return Equipment(**kwargs)


def run(equipment: Equipment, cfg: ProjectConfig):
    soil, wind = from_config(cfg)
    s = cfg.seismic

    # اگر سختی جانبی داده شده باشد، روش از روی زمان تناوب انتخاب می‌شود
    w_eff = equipment.We + equipment.Ws / 3
    t_period, suggested, note = period(w_eff, s.k_lateral)
    if suggested and getattr(s, "auto_method", True):
        s.method = suggested
    seis = (Site2800v4(a=s.a, b=s.b, i=s.i, r=s.r).compute() if s.edition == 4
            else Site2800v5(ss=s.ss, s1=s.s1, soil=s.soil_class, ie=s.ie,
                            ru=s.ru, method=s.method, map_date=s.map_date).compute())
    seis.period = t_period
    seis.period_note = note or ""
    if note:
        seis.steps.insert(0, ("زمان تناوب", "T = 2π·√(W/(g·k))   بند ۵-۵-۱", note))
    f = cfg.foundation
    res = find_dimensions(equipment, soil, wind, seis.ch, seis.cv,
                          hp=f.hp, b=f.b, tf=f.tf,
                          lo=f.search_min, hi=f.search_max, step=f.search_step)
    if res is None:
        return None, seis, None, None, None
    des = design_all(res, equipment, soil, cfg.rebar)
    qty = quantities(res, equipment, soil)
    bbs = bar_schedule(res, equipment, soil, des, cfg.rebar)
    qty["rebar"] = sum(r["weight"] for r in bbs)
    return res, seis, des, qty, bbs


def bar_schedule(res, eq, soil, des, rebar):
    g = res.geometry
    cov = soil.cover / 1000
    L, B, tf, hp, b = g.L, g.B, g.tf, g.hp, g.b
    n = eq.n_pedestal
    pad_dia, pad_sp = des["pad"].bar_dia, des["pad"].spacing
    col_n, col_dia = des["pedestal"].bar_count, des["pedestal"].bar_dia
    nx = int((L - 2 * cov) / (pad_sp / 1000)) + 1
    ny = int((B - 2 * cov) / (pad_sp / 1000)) + 1
    raw = [("01", "PAD  BOTTOM  E.W.", pad_dia, 2 * ny, L - 2 * cov + 2 * 10 * pad_dia / 1000),
           ("02", "PEDESTAL VERTICAL", col_dia, col_n * n, tf + hp - 2 * cov + 15 * col_dia / 1000),
           ("03", "PAD  TOP  E.W.", pad_dia, 2 * nx, B - 2 * cov + 2 * 10 * pad_dia / 1000),
           ("04", "STANDEE", rebar.standee_dia, nx, (tf - 2 * cov) + 0.4),
           ("05", "PEDESTAL TIE", rebar.tie_dia,
            (int(hp / (rebar.tie_spacing / 1000)) + 1) * n,
            4 * (b - 2 * cov) + 20 * rebar.tie_dia / 1000)]
    rows = []
    for pos, shape, dia, no, length in raw:
        total = no * length
        rows.append(dict(pos=pos, shape=shape, dia=dia, no=no, length=length,
                         total=total, unit_w=REBAR_UNIT(dia), weight=total * REBAR_UNIT(dia)))
    return rows


def to_dict(res, seis, des, qty, bbs, eq, cfg):
    """خروجی قابل ذخیره در دیتابیس و قابل مصرف در رابط کاربری."""
    g = res.geometry
    return {
        "geometry": {"L": g.L, "B": g.B, "tf": g.tf, "hp": g.hp, "b": g.b,
                     "n_pedestal": eq.n_pedestal,
                     "pedestal_spacing": eq.pedestal_spacing or (g.B / 2 if eq.n_pedestal > 1 else 0),
                     "anchor_n": eq.anchor_n, "anchor_dia": eq.anchor_dia,
                     "anchor_gauge": eq.anchor_gauge, "cover": cfg.materials.cover,
                     "lean": cfg.materials.lean},
        "seismic": {"ch": seis.ch, "cv": seis.cv, "edition": seis.edition,
                    "period": getattr(seis, "period", None),
                    "period_note": getattr(seis, "period_note", ""),
                    "method": cfg.seismic.method,
                    "steps": [list(s) for s in seis.steps]},
        "governing": {"no": res.governing.no, "name": res.governing.name,
                      "N": res.governing.Nmax, "Nmin": res.governing.Nmin,
                      "V": res.governing.V, "M": res.governing.M,
                      "factor": res.governing.factor},
        "cases": [{"no": c.no, "name": c.name, "Fe": c.Fe, "Fs": c.Fs,
                   "N": c.Nmax, "Nmin": c.Nmin, "V": c.V, "M": c.M} for c in res.cases],
        "checks": [{"name": c.name, "value": c.value, "limit": c.limit,
                    "ok": c.passed, "dir": c.direction, "unit": c.unit,
                    "steps": [list(s) for s in c.steps]} for c in res.checks],
        "design": {k: {"title": d.title, "ok": d.ok, "note": d.note,
                       "bars": d.bar_count, "dia": d.bar_dia, "spacing": d.spacing,
                       "as_req": d.as_req, "steps": [list(s) for s in d.steps]}
                   for k, d in des.items()},
        "bbs": bbs,
        "quantities": qty,
        "ok": res.ok and all(d.ok for d in des.values()),
    }
