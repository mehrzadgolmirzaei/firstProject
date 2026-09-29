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
from padlayout import Group, PadLayout, row           # noqa: E402
from equipment import ALL_EQUIPMENT, VOLTAGE_LEVELS, EQUIPMENT_TYPES  # noqa: E402,F401
import model                                          # noqa: E402

def build_equipment(data: dict) -> Equipment:
    """ساخت شیء تجهیز از دیکشنری کاتالوگ یا فرم."""
    allowed = Equipment.__dataclass_fields__
    kwargs = {k: v for k, v in data.items() if k in allowed and v not in ("", None)}
    missing = [n for n, t in (("He", "ارتفاع تجهیز"), ("Ae", "سطح بادگیر"), ("We", "وزن تجهیز"))
               if n not in kwargs]
    if missing:
        raise ValueError("تجهیز انتخاب نشده یا مشخصات آن ناقص است ("
                         + "، ".join(t for n, t in (("He", "ارتفاع تجهیز He"), ("Ae", "سطح بادگیر Ae"),
                                                    ("We", "وزن تجهیز We")) if n in missing)
                         + "). یک پی را از فهرست نقشه جانمایی یا روی پلان انتخاب کنید، یا تجهیز را برگزینید.")
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
    چیدمان پی از ورودی فرم یا اسنپ‌شات. مهندس مختصات تایپ نمی‌کند:

    ۱. positions داده شده ← از کی‌پلن (یا نمونه آماده که خودش از کی‌پلن است)
    ۲. وگرنه قاعده ثابت: ستون‌های هر تجهیز در یک ردیف در امتداد L با فاصله
       سازه‌اش؛ پی تک‌تجهیزه ردیف در مرکز؛ پی دوتجهیزه دو ردیف موازی به فاصله
       «فاصله محور دو تجهیز» (gap، از کی‌پلن)، متقارن نسبت به مرکز پی.

    spec = {"kind": "single" | "combined", "source": "...",
            "gap": فاصله محور دو تجهیز (m),
            "groups": [{"n", "spacing", "positions"?},                   # گروه ۱ = eq1
                       {"equipment": {...}, "n", "spacing", "positions"?}]}

    خروجی: (PadLayout، spec کامل برای اسنپ‌شات — مختصات نهایی ستون‌ها هم ذخیره می‌شود)
    """
    spec = spec or {}
    kind = spec.get("kind") or "single"
    if kind not in ("single", "combined"):
        raise ValueError("نوع پی باید single یا combined باشد")
    raw = list(spec.get("groups") or [{}])
    if kind == "single":
        raw = raw[:1]
    if len(raw) > 6:
        raise ValueError("روی یک پی حداکثر شش تجهیز")
    gap = _num(spec.get("gap"))
    groups, saved = [], []
    for i, g in enumerate(raw):
        g = g or {}
        if i == 0:
            eq = eq1
        else:
            data = dict(g.get("equipment") or {})
            tag = data.get("tag")
            if tag in ALL_EQUIPMENT:
                base = asdict(ALL_EQUIPMENT[tag])
                base.update({k: v for k, v in data.items() if v not in ("", None)})
                data = base
            if not data.get("tag"):
                raise ValueError("تجهیز دوم انتخاب نشده")
            eq = build_equipment(data)
        pos = g.get("positions")
        if pos:
            positions = [(float(x), float(y)) for x, y in pos]
            groups.append(Group(eq, positions))
            saved.append({"positions": positions, **({"equipment": asdict(eq)} if i else {})})
            continue
        n = _num(g.get("n"), int) or eq.n_pedestal
        if not 1 <= n <= 4:
            raise ValueError("تعداد ستون هر تجهیز باید ۱ تا ۴ باشد")
        spacing = _num(g.get("spacing"))
        if spacing is None:
            spacing = eq.pedestal_spacing
        y = 0.0
        if len(raw) == 2:
            if not gap:
                raise ValueError("برای دو تجهیز روی یک پی، «فاصله محور دو تجهیز» را از کی‌پلن "
                                 "وارد کنید، یا کی‌پلن را بارگذاری کنید")
            y = gap / 2 if i == 0 else -gap / 2
        grp = row(eq, spacing=spacing or None, y=y, n=n)
        groups.append(grp)
        saved.append({"n": n, "spacing": spacing, "positions": grp.positions,
                      **({"equipment": asdict(eq)} if i else {})})
    out = {"kind": kind, "source": str(spec.get("source") or ""), "gap": gap, "groups": saved}
    return PadLayout(groups, square=(kind == "single")), out


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


def _suggestion(d, st):
    """پیشنهاد سیستم در حالت کنترل: سبک‌ترین مقاطعی که با همین هندسه جواب می‌دهد."""
    a = getattr(d, "suggestion", None)
    if a is None:
        return None
    return {"sections": dict(a.sections), "ratio": round(float(a.max_ratio), 3), "ok": bool(a.ok),
            "weight": round(a.weight * a.stands * st.connection_factor, 1),
            "same": dict(a.sections) == dict(d.sections),
            "saving": round((d.weight - a.weight) * d.stands * st.connection_factor, 1)}


def structures_dict(res, cfg):
    """سازه‌های فولادی طراحی‌شده برای نمایش و ذخیره."""
    from structural.loads import COMBO_TITLES
    out = []
    for gi, d in getattr(res, "structures", []) or []:
        eq = res.layout.groups[gi].eq
        groups = []
        for g in d.group_summary():
            ck = g["check"]
            groups.append({"group": g["group"], "title": g["title"], "section": g["section"],
                           "count": g["count"] * d.stands, "length": round(g["length"] * d.stands, 2),
                           "ratio": round(g["ratio"], 3), "member": g["member"],
                           "combo": COMBO_TITLES.get(ck.combo, ck.combo), "equation": ck.equation,
                           "notes": ck.notes, "steps": [list(x) for x in ck.steps()]})
        legs = []
        extremes = d.chord_extremes()
        for i in range(len(d.model.leg_centres)):
            rows = [(c, r[i]) for c, r in d.leg_reactions.items()]
            comp = max(rows, key=lambda x: x[1][2])
            upl = min(rows, key=lambda x: x[1][2])
            shr = max(rows, key=lambda x: (x[1][0] ** 2 + x[1][1] ** 2) ** 0.5)
            legs.append({"leg": i + 1,
                         "compression": round(comp[1][2], 1), "compression_combo": COMBO_TITLES[comp[0]],
                         "uplift": round(upl[1][2], 1), "uplift_combo": COMBO_TITLES[upl[0]],
                         "shear": round((shr[1][0] ** 2 + shr[1][1] ** 2) ** 0.5, 1),
                         "shear_combo": COMBO_TITLES[shr[0]],
                         "chord_comp": round(extremes[i][0][0], 1),
                         "chord_tension": round(max(0.0, -extremes[i][1][0]), 1),
                         "chord_tension_combo": COMBO_TITLES[extremes[i][1][1]],
                         "moment": round(extremes[i][2][0], 1),
                         "moment_combo": COMBO_TITLES[extremes[i][2][1]]})
        st = cfg.steel
        out.append({"tag": eq.tag, "stands": d.stands, "legs": d.spec.legs,
                    "phases": d.phases_per_stand, "height": d.spec.height,
                    "leg_width": d.spec.leg_width, "panels": round(d.spec.height / d.spec.panel),
                    "members": len(d.model.members) * d.stands,
                    "weight": round(d.weight * d.stands, 1),
                    "weight_design": round(d.weight * d.stands * st.connection_factor, 1),
                    "wind_area": round(d.wind_area * d.stands, 3),
                    "fed": st.feed_foundation, "Ws_used": eq.Ws, "As_used": eq.As,
                    "max_ratio": round(d.max_ratio, 3), "ok": d.ok, "k_chord": st.k_chord,
                    "mode": st.mode,
                    "suggestion": _suggestion(d, st),
                    "loads": getattr(d, "load_table", None),
                    "fy": st.fy, "iterations": len(d.history), "groups": groups, "legs_reactions": legs,
                    "warnings": d.warnings})
    return out


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
        "structures": structures_dict(res, cfg),
        "model": model.to_dict(fm),
        "clashes": clashes,
        "options": {"governing": str(cfg.design.governing), "bearing": cfg.design.bearing},
        "comparison": getattr(res, "comparison", []),
        "quantities": qty,
        "ok": (res.ok and all(d.ok for k, d in des.items() if k != "groups") and not clashes
               and all(d.ok for _, d in getattr(res, "structures", []) or [])),
    }
