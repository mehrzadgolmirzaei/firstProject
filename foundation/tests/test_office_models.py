"""
مدل‌های نمونه SAP2000 دفتر (tests/data/sap): مقاطع دقیقاً همان خواص SAP، و هر
مدل با حل‌کننده برنامه در تعادل کامل نیرو و لنگر.
"""
from pathlib import Path

import numpy as np
import pytest

from structural.frame import analyse
from structural.s2k import read_model, read_tables
from structural.sections import from_sap
from structural.validation import applied_loads as _applied

MODELS = sorted((Path(__file__).parent / "data" / "sap").glob("*.s2k"))


@pytest.mark.parametrize("path", MODELS, ids=lambda p: p.stem)
def test_section_properties_equal_sap(path):
    for r in read_tables(path)["FRAME SECTION PROPERTIES 01 - GENERAL"]:
        if r["Shape"] not in ("Angle", "Channel", "Double Channel"):
            continue
        s = from_sap(r)
        for key, attr in (("Area", "A"), ("TorsConst", "J"), ("I33", "I33"), ("I22", "I22"),
                          ("AS2", "AS2"), ("AS3", "AS3"), ("S33", "S33"), ("S22", "S22"),
                          ("R33", "r33"), ("R22", "r22")):
            assert getattr(s, attr) == pytest.approx(r[key], rel=1e-6), (r["SectionName"], key)


@pytest.mark.parametrize("path", MODELS, ids=lambda p: p.stem)
def test_office_model_equilibrium(path):
    m = read_model(path)
    r = analyse(m)
    for case, pat in m.patterns.items():
        F, M = _applied(m, pat)
        RF = sum(np.array(v[:3]) for v in r.reactions[case].values())
        RM = sum(np.cross(m.nodes[n], v[:3]) + np.array(v[3:]) for n, v in r.reactions[case].items())
        assert RF == pytest.approx(-F, abs=1e-6)
        assert RM == pytest.approx(-M, abs=1e-6)
    for c in (c for c in m.combos if c.startswith("COMB")):
        assert np.isfinite(r.disp[c]).all()
