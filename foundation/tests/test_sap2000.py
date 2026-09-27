"""خواندن مدل‌های SAP2000 دفتر و گذاشتن سازه روی فونداسیون."""
import sys
from pathlib import Path

import pytest

from sap2000 import read_structure, read_tables, _value
from steel import LIBRARY, place
from equipment import ALL_EQUIPMENT

sys.path.insert(0, str(Path(__file__).parent))


def test_persian_decimal_separator():
    """ویندوز فارسی اعشار را با «/» می‌نویسد."""
    assert _value("0/45") == 0.45
    assert _value("1/55861333333333E-09") == pytest.approx(1.55861333333333e-09)
    assert _value("-0/1") == -0.1
    assert _value("2.5") == 2.5
    assert _value("L60X6") == "L60X6"


@pytest.mark.parametrize("tag,height,legs,spacing,weight", [
    ("LA63", 2.85, 2, 1.70, 294), ("CT63", 2.00, 2, 1.70, 283), ("PI63", 4.58, 2, 1.70, 579),
    ("DS2_63", 4.10, 2, 1.70, 482), ("CVT63_1", 2.00, 1, 0.0, 82)])
def test_library_structures(tag, height, legs, spacing, weight):
    st = read_structure(LIBRARY / ALL_EQUIPMENT[tag].structure)
    assert st.height == pytest.approx(height)
    assert len(st.legs()) == legs
    assert st.leg_spacing == pytest.approx(spacing)
    assert st.member_weight == pytest.approx(weight, abs=1)
    # وزن محاسبه‌شده همان TotalWt خود SAP است
    t = read_tables(LIBRARY / ALL_EQUIPMENT[tag].structure)
    used = {f.section for f in st.frames}
    sap = sum(r.get("TotalWt", 0) or 0 for r in t["FRAME SECTION PROPERTIES 01 - GENERAL"]
              if r["SectionName"] in used)
    assert st.member_weight == pytest.approx(sap, rel=0.01)


def test_place_on_pedestals():
    st = read_structure(LIBRARY / ALL_EQUIPMENT["LA63"].structure)
    members, warn = place(st, [(-850, 750), (850, 750)], 1470)
    assert not warn and len(members) == 96
    assert min(min(m.p[2], m.q[2]) for m in members) == pytest.approx(1470)
    assert max(max(m.p[2], m.q[2]) for m in members) == pytest.approx(1470 + 2850)
    feet = [m.p for m in members if m.kind == "chord" and m.p[2] == pytest.approx(1470)]
    assert len(feet) == 8
    for x, y, _ in feet:        # چهار نبشی هر پایه دور مرکز ستون، مربع ۴۰۰
        assert min(abs(x + 850), abs(x - 850)) == pytest.approx(200)
        assert abs(y - 750) == pytest.approx(200)


def test_single_leg_structure_on_every_pedestal():
    st = read_structure(LIBRARY / ALL_EQUIPMENT["CVT63"].structure)
    members, warn = place(st, [(-1500, 0), (0, 0), (1500, 0)], 1470)
    assert not warn and len(members) == 3 * len(st.frames)


def test_leg_count_mismatch_is_reported():
    st = read_structure(LIBRARY / ALL_EQUIPMENT["LA63"].structure)
    members, warn = place(st, [(0, 0), (1000, 0), (2000, 0)], 0)
    assert members == [] and warn


def test_steel_in_model_and_3d(tmp_path):
    pytest.importorskip("ezdxf")
    import ezdxf
    import model
    import model3d
    from padlayout import Group, PadLayout
    from pipeline import run_layout
    from test_kimia63 import kimia_config
    cfg = kimia_config()
    cfg.foundation.L, cfg.foundation.B, cfg.foundation.b = 3.0, 3.0, 0.6
    lay = PadLayout([Group(ALL_EQUIPMENT["PI63"], [(-0.75, -0.85), (-0.75, 0.85)]),
                     Group(ALL_EQUIPMENT["CVT63_1"], [(0.75, 0.0)])])
    res, seis, des, *_ = run_layout(lay, cfg)
    fm = model.build(res, lay, des, cfg)
    assert len(fm.steel) == 160 + 28 and not model.clashes(fm)
    path = model3d.export(fm, lay.main, str(tmp_path / "pi.dxf"))
    layers = {e.dxf.layer for e in ezdxf.readfile(path).modelspace().query("3DSOLID")}
    assert {"S-CHORD", "S-BRACE", "S-BEAM"} <= layers
    d = model.to_dict(fm)
    assert len(d["steel"]) == 188 and d["steel"][0]["profile"]


@pytest.mark.parametrize("rel", ["../config.py", "../../../etc/passwd", "/etc/passwd",
                                 "63kV/../../project.json"])
def test_library_path_cannot_escape(rel):
    from steel import load
    assert load(rel) is None
