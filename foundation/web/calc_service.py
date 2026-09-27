"""
پل بین سامانه وب و موتور محاسبه.

موتور دست‌نخورده می‌ماند؛ اینجا فقط ورودی وب به اشیای موتور تبدیل می‌شود و
خروجی به ساختار قابل ذخیره و نمایش برمی‌گردد.
"""
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import ProjectConfig                      # noqa: E402
from equipment import Equipment, CATALOG              # noqa: E402,F401
from pipeline import run, run_layout                  # noqa: E402,F401
from padlayout import PadLayout, row                  # noqa: E402
from presets import ALL_EQUIPMENT, FOUNDATION_PRESETS  # noqa: E402,F401
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


def _num(v, cast=float, default=None):
    if v in (None, ""):
        return default
    return cast(float(v))


def layout_from_spec(spec, eq1: Equipment):
    """
    چیدمان پی از ورودی فرم یا اسنپ‌شات.

    spec = {"kind": "single" | "combined",
            "groups": [{"n", "spacing", "axis", "x", "y", "case"},          # گروه ۱ = eq1
                       {"equipment": {...}, "n", "spacing", "axis", "x", "y", "case"}]}

    single   : پی منفرد مربعی (پست ۲۳۰/۴۰۰)؛ فقط گروه ۱ ، ستون‌ها در مرکز.
    combined : پی مشترک مستطیلی (پست ۶۳)؛ یک یا دو گروه با مختصات داده‌شده.

    خروجی: (PadLayout، spec کامل برای اسنپ‌شات — تجهیز گروه‌های بعدی کامل ذخیره می‌شود)
    """
    spec = spec or {}
    kind = spec.get("kind") or "single"
    if kind not in ("single", "combined"):
        raise ValueError("نوع پی باید single یا combined باشد")
    raw = list(spec.get("groups") or [{}])
    if kind == "single":
        raw = raw[:1]
    groups, saved = [], []
    for i, g in enumerate(raw):
        g = g or {}
        if i == 0:
            eq = eq1
        else:
            data = dict(g.get("equipment") or {})
            tag = data.get("tag")
            if tag in ALL_EQUIPMENT:
                base = {k: v for k, v in asdict(ALL_EQUIPMENT[tag]).items()}
                base.update({k: v for k, v in data.items() if v not in ("", None)})
                data = base
            if not data.get("tag"):
                raise ValueError("تجهیز گروه دوم انتخاب نشده")
            eq = build_equipment(data)
        n = _num(g.get("n"), int) or eq.n_pedestal
        if not 1 <= n <= 4:
            raise ValueError("تعداد ستون هر گروه باید ۱ تا ۴ باشد")
        spacing = _num(g.get("spacing"))
        if spacing is None:
            spacing = eq.pedestal_spacing
        axis = g.get("axis") or "x"
        if axis not in ("x", "y"):
            raise ValueError("راستای ردیف ستون‌ها باید x یا y باشد")
        x = _num(g.get("x"), default=0.0) if kind == "combined" else 0.0
        y = _num(g.get("y"), default=0.0) if kind == "combined" else 0.0
        case = _num(g.get("case"), int) if kind == "combined" else None
        if case is not None and not 1 <= case <= 5:
            raise ValueError("حالت بار گروه باید ۱ تا ۵ باشد")
        groups.append(row(eq, spacing=spacing or None, axis=axis, x=x, y=y, case=case, n=n))
        item = {"n": n, "spacing": spacing, "axis": axis, "x": x, "y": y, "case": case}
        if i:
            item["equipment"] = asdict(eq)
        saved.append(item)
    return PadLayout(groups, square=(kind == "single")), {"kind": kind, "groups": saved}


def layout_problems(layout: PadLayout, b: float, L: float = 0.0, B: float = 0.0) -> list:
    """ستون‌های روی هم افتاده، یا بیرون زده از پی داده‌شده."""
    errs = []
    for g in layout.groups:
        if g.n > 1 and g.positions is None:
            errs.append(f"برای {g.n} ستون {g.eq.tag}، «فاصله محور تا محور ستون‌ها» را وارد کنید.")
    pts = [(x, y, g.eq.tag) for g in layout.groups if g.positions is not None
           for x, y in g.positions]
    gap = b + 0.10
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            (x1, y1, t1), (x2, y2, t2) = pts[i], pts[j]
            if abs(x1 - x2) < gap - 1e-9 and abs(y1 - y2) < gap - 1e-9:
                errs.append(f"ستون‌های {t1} ({x1:+.2f}، {y1:+.2f}) و {t2} ({x2:+.2f}، {y2:+.2f}) "
                            f"روی هم می‌افتند؛ فاصله محورها باید دست‌کم عرض ستون + ۱۰ سانت "
                            f"({gap:.2f} m) باشد.")
    if L and B:
        for x, y, t in pts:
            if abs(x) + b / 2 > L / 2 + 1e-9 or abs(y) + b / 2 > B / 2 + 1e-9:
                errs.append(f"ستون {t} در ({x:+.2f}، {y:+.2f}) از پی {L:.2f}×{B:.2f} بیرون می‌زند.")
    return errs


def to_dict(res, seis, des, qty, bbs, eq, cfg):
    """خروجی قابل ذخیره در دیتابیس و قابل مصرف در رابط کاربری."""
    g = res.geometry
    fm = model.build(res, getattr(res, "layout", eq), des, cfg)
    clashes = model.clashes(fm)
    return {
        "geometry": {"L": g.L, "B": g.B, "tf": g.tf, "hp": g.hp, "b": g.b,
                     "n_pedestal": res._n,
                     "pedestal_spacing": model.pedestal_spacing(eq, g.B),
                     "layout": res.layout.describe(),
                     "pedestals": [[x, y, i] for x, y, i in res.layout.positions(g.B)],
                     "anchor_n": eq.anchor_n, "anchor_dia": eq.anchor_dia,
                     "anchor_gauge": eq.anchor_gauge,
                     "anchor_embed": des["anchor"].embed if "anchor" in des else None,
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
                    "ok": c.passed, "dir": c.direction, "unit": c.unit, "case": c.case,
                    "steps": [list(s) for s in c.steps]} for c in res.checks],
        "design": {k: {"title": d.title, "ok": d.ok, "note": d.note,
                       "bars": d.bar_count, "dia": d.bar_dia, "spacing": d.spacing,
                       "as_req": d.as_req, "steps": [list(s) for s in d.steps],
                       **({"embed": d.embed, "tension": d.tension, "shear": d.shear}
                          if hasattr(d, "embed") else {})}
                   for k, d in des.items() if k != "groups"},
        "groups": [{"tag": x["tag"], "pedestal": x["pedestal"].bar_count,
                    "npol": res.layout.groups[i].eq.npol, "n": res.layout.groups[i].n,
                    "case": u.no,
                    "pedestal_dia": x["pedestal"].bar_dia, "embed": x["anchor"].embed,
                    "tension": x["anchor"].tension}
                   for i, (x, (_, u)) in enumerate(zip(des.get("groups", []), res.group_forces))],
        "bbs": bbs,
        "model": model.to_dict(fm),
        "clashes": clashes,
        "options": {"governing": str(cfg.design.governing), "bearing": cfg.design.bearing},
        "comparison": getattr(res, "comparison", []),
        "quantities": qty,
        "ok": res.ok and all(d.ok for k, d in des.items() if k != "groups") and not clashes,
    }
