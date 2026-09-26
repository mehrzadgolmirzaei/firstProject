"""
پل بین سامانه وب و موتور محاسبه.

موتور دست‌نخورده می‌ماند؛ اینجا فقط ورودی وب به اشیای موتور تبدیل می‌شود و
خروجی به ساختار قابل ذخیره و نمایش برمی‌گردد.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import ProjectConfig                      # noqa: E402
from equipment import Equipment, CATALOG              # noqa: E402
from pipeline import run                              # noqa: E402,F401
import model                                          # noqa: E402

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


def to_dict(res, seis, des, qty, bbs, eq, cfg):
    """خروجی قابل ذخیره در دیتابیس و قابل مصرف در رابط کاربری."""
    g = res.geometry
    fm = model.build(res, eq, des, cfg)
    clashes = model.clashes(fm)
    return {
        "geometry": {"L": g.L, "B": g.B, "tf": g.tf, "hp": g.hp, "b": g.b,
                     "n_pedestal": eq.n_pedestal,
                     "pedestal_spacing": eq.pedestal_spacing or (g.B / 2 if eq.n_pedestal > 1 else 0),
                     "anchor_n": eq.anchor_n, "anchor_dia": eq.anchor_dia,
                     "anchor_gauge": eq.anchor_gauge, "anchor_embed": eq.anchor_embed,
                     "cover": cfg.materials.cover, "lean": cfg.materials.lean,
                     "tie_dia": cfg.rebar.tie_dia, "tie_spacing": cfg.rebar.tie_spacing},
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
        "model": model.to_dict(fm),
        "clashes": clashes,
        "quantities": qty,
        "ok": res.ok and all(d.ok for d in des.values()) and not clashes,
    }
