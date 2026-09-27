"""
مدل‌های نمونه SAP2000 دفتر (tests/data/sap): مقاطع دقیقاً همان خواص SAP، و هر
مدل با حل‌کننده برنامه در تعادل کامل نیرو و لنگر.
"""
import math
from pathlib import Path

import numpy as np
import pytest

from structural.frame import analyse
from structural.s2k import read_model, read_tables
from structural.sections import from_sap

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


def _applied(m, pat):
    P = lambda n: np.array(m.nodes[n])
    F, M = np.zeros(3), np.zeros(3)

    def add(f, at):
        nonlocal F, M
        F = F + f
        M = M + np.cross(at, f)
    for mem in m.members:
        L = math.dist(m.nodes[mem.i], m.nodes[mem.j])
        mid = (P(mem.i) + P(mem.j)) / 2
        add(np.array([0, 0, -pat.self_weight * mem.section.A * m.gamma * L]), mid)
    for n, f in pat.joint:
        add(np.array(f[:3]), P(n))
        M = M + np.array(f[3:])
    for mn, d, ra, rb, wa, wb in pat.partial + [(a, b, 0, 1, c, c) for a, b, c in pat.uniform]:
        mem = m.member(mn)
        L = math.dist(m.nodes[mem.i], m.nodes[mem.j])
        tot = (wa + wb) / 2 * L * (rb - ra)
        xc = ra + (rb - ra) * ((wa + 2 * wb) / (3 * (wa + wb)) if wa + wb else 0.5)
        v = np.zeros(3)
        v["XYZ".index(d)] = tot
        add(v, P(mem.i) + (P(mem.j) - P(mem.i)) * xc)
    for mn, mult in pat.gravity:
        mem = m.member(mn)
        L = math.dist(m.nodes[mem.i], m.nodes[mem.j])
        add(np.array(mult) * mem.section.A * m.gamma * L, (P(mem.i) + P(mem.j)) / 2)
    return F, M


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
