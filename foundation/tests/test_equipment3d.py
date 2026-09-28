"""
شکل تجهیز روی سازه: هر فاز یک تجهیز، روی بالای سازه، به ارتفاع He و با ترمینال هادی.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import model                                                     # noqa: E402
from equipment import ALL_EQUIPMENT                              # noqa: E402
from kimia63_data import PADS                                    # noqa: E402
from padlayout import Group, PadLayout                           # noqa: E402
from pipeline import run_layout                                  # noqa: E402
from structural.equipment3d import build, for_stand              # noqa: E402
from test_kimia63 import kimia_config                            # noqa: E402


def _fm(key, **steel):
    L, B, b, groups = PADS[key]
    cfg = kimia_config()
    cfg.foundation.L, cfg.foundation.B, cfg.foundation.b = L, B, b
    for k, v in steel.items():
        setattr(cfg.steel, k, v)
    lay = PadLayout([Group(ALL_EQUIPMENT[t], p) for t, p in groups])
    res, seis, des, *_ = run_layout(lay, cfg)
    return model.build(res, res.layout, des, cfg)


def _z(prims):
    zs = [z for p in prims for z in (p["p"][2], p["q"][2])]
    return min(zs), max(zs)


@pytest.mark.parametrize("tag", ["LA63", "CT63", "CVT63", "PI63", "DSE63", "CB63"])
def test_phase_height_and_terminals(tag):
    eq = ALL_EQUIPMENT[tag]
    prims = build(eq, (0.0, 0.0, 1000.0))
    lo, hi = _z(prims)
    assert lo == pytest.approx(1000.0)
    assert hi == pytest.approx(1000.0 + eq.He * 1000, abs=15)
    terms = [p for p in prims if p["g"] == "terminal" and p["t"] == "cyl"]
    for h in eq.conductor_points:
        assert any(abs(p["p"][2] - 1000 - h * 1000) < 1 for p in terms)


def test_equipment_sits_on_designed_structure():
    fm = _fm("LA+CVT-3-2.5")
    top = max(max(m.p[2], m.q[2]) for m in fm.steel)
    bases = [p for p in fm.equipment if p["t"] == "box" and p["g"] == "metal"
             and abs(p["q"][2] - p["p"][2] - 20) < 1e-6]          # صفحه پای هر فاز
    assert len(bases) == ALL_EQUIPMENT["LA63"].npol + ALL_EQUIPMENT["CVT63"].npol
    for b in bases:
        assert b["p"][2] <= top + 1 and b["p"][2] > top - 1500


def test_manufacturer_structure_is_drawn():
    """CB سازه‌اش از سازنده است: ستون‌ها به ارتفاع Hs و سه فاز روی آن."""
    fm = _fm("CB-2-3.2")
    eq = ALL_EQUIPMENT["CB63"]
    assert not fm.steel
    lo, hi = _z(fm.equipment)
    assert hi - lo == pytest.approx((eq.Hs + eq.He) * 1000, abs=15)
    assert sum(1 for p in fm.equipment if p["g"] == "terminal") == eq.npol * len(eq.conductor_points)


def test_steel_disabled_still_shows_equipment():
    fm = _fm("LA-2.5-1.5", enabled=False)
    assert not fm.steel and fm.equipment


def test_stand_one_phase_per_pedestal():
    eq = ALL_EQUIPMENT["CVT63"]
    prims = for_stand(eq, [(-1000, 0), (0, 0), (1000, 0)], 0.0)
    cols = [p for p in prims if p["t"] == "box" and p["g"] == "metal" and p["p"][2] == 0.0]
    assert len(cols) == 3
