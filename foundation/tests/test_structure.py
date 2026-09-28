"""
سازه نگهدارنده: بارها همان بارهای پی، طراحی خودکار حداقلی و درست، و هماهنگی با دفترچه.
"""
import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))

from engine import from_config                                   # noqa: E402
from equipment import ALL_EQUIPMENT                              # noqa: E402
from pipeline import seismic_coefficients                        # noqa: E402
from structural import asd89                                     # noqa: E402
from structural.frame import analyse                             # noqa: E402
from structural.s2k import read_model, write_model               # noqa: E402
from structural.steel_design import design_structure, stand_layout  # noqa: E402
from test_kimia63 import kimia_config                            # noqa: E402


def _design(tag, **steel):
    cfg = kimia_config()
    for k, v in steel.items():
        setattr(cfg.steel, k, v)
    eq = ALL_EQUIPMENT[tag]
    seis = seismic_coefficients(eq, cfg)
    soil, wind = from_config(cfg)
    return design_structure(eq, cfg.steel, wind, seis.ch, seis.cv), eq, seis, wind


def _base(d, combo):
    R = d.results.reactions[combo].values()
    return sum(r[2] for r in R), -sum(r[1] for r in R), -sum(r[0] for r in R)   # تکیه‌گاه بر سازه


@pytest.mark.parametrize("tag", ["LA63", "PI63", "CVT63_1"])
def test_structure_loads_equal_foundation_loads(tag):
    """جمع عکس‌العمل‌ها = همان N و V که موتور پی با همین وزن و سطح بادگیر حساب می‌کند."""
    d, eq, seis, wind = _design(tag)
    npol = d.phases_per_stand
    W = d.weight
    for k, (combo, q) in enumerate((("C1", wind.q_normal), ("C2", wind.q_high),
                                    ("C3", wind.q_sc)), start=1):
        N, V, _ = _base(d, combo)
        Fc = eq.Fc if k != 3 else eq.Fc_sc
        assert N == pytest.approx(W + npol * (eq.We + eq.Wc), rel=1e-9)
        assert V == pytest.approx((Fc + q * eq.Ce * eq.Ae) * npol + q * eq.Cs * d.wind_area,
                                  rel=1e-9)
    N, V, _ = _base(d, "C4+")
    assert V == pytest.approx((eq.Fc + seis.ch * eq.We) * npol + seis.ch * W, rel=1e-9)
    assert N == pytest.approx((1 + seis.cv) * (W + npol * (eq.We + eq.Wc)), rel=1e-9)
    _, _, VX = _base(d, "CX+")
    assert VX == pytest.approx(seis.ch * (W + npol * eq.We), rel=1e-9)


def test_auto_design_passes_and_is_minimal():
    d, *_ = _design("PI63")
    assert d.ok and d.max_ratio <= 1.0
    lighter = dict(d.sections, chord="L60X6")          # یک پله سبک‌تر از L70X7
    d2, *_ = _design_with("PI63", lighter)
    assert not d2.ok


def _design_with(tag, sections):
    cfg = kimia_config()
    eq = ALL_EQUIPMENT[tag]
    seis = seismic_coefficients(eq, cfg)
    soil, wind = from_config(cfg)
    return design_structure(eq, cfg.steel, wind, seis.ch, seis.cv, sections=sections), eq


def test_chord_tension_matches_notebook_anchor_tension():
    """
    کشش یک نبشی پایه LA از تحلیل سازه (بهره‌برداری) ≈ کشش میل مهار دفترچه
    (۱۸۱۴ kg نهایی ÷ ۱٫۱) — دو روش مستقل.
    """
    d, *_ = _design("LA63")
    tension = max(-t for _, (t, _), _ in d.chord_extremes())
    assert tension == pytest.approx(1814 / 1.1, rel=0.06)


def test_stands_layout():
    assert stand_layout(ALL_EQUIPMENT["CVT63"]) == (3, 1, 1)     # سه سازه تک‌فاز
    assert stand_layout(ALL_EQUIPMENT["LA63"]) == (1, 2, 3)
    assert stand_layout(ALL_EQUIPMENT["LA"]) == (1, 1, 1)


def test_allowable_compression_hand_calc():
    """Fy=2350، E=2.0389e6 kg/cm²، KL/r=100: Cc=130.9 ← Fa = 877 kg/cm² (E2-1)."""
    Fa = asd89.allowable_compression(100, 2.35e7, 2.0389019158e10)
    assert Fa / 1e4 == pytest.approx(877.1, abs=1.0)
    Fe = asd89.allowable_compression(160, 2.35e7, 2.0389019158e10)      # > Cc: E2-2
    assert Fe == pytest.approx(12 * math.pi ** 2 * 2.0389019158e10 / (23 * 160 ** 2))


def test_sap_export_round_trip(tmp_path):
    d, *_ = _design("LA63")
    for m in d.model.members:
        m.section.fy = 2.35e7
    path = write_model(d.model, tmp_path / "la.s2k", "LA63")
    m2 = read_model(path)
    r2 = analyse(m2)
    names = {n: str(k + 1) for k, n in enumerate(d.model.nodes)}
    for c in d.model.combos:
        for n in d.model.supports:
            assert np.array(r2.reactions[c][names[n]]) == pytest.approx(
                np.array(d.results.reactions[c][n]), abs=1e-6)
    assert text_has_persian_decimal(path)


def text_has_persian_decimal(path):
    return "XorR=0/" in Path(path).read_text(encoding="latin-1") or "Y=0/" in Path(path).read_text(
        encoding="latin-1")


def test_foundation_uses_structure_when_fed():
    """با feed_foundation، Ws و As پی از خود سازه است، نه عدد دستی کاتالوگ."""
    from kimia63_data import PADS
    from padlayout import Group, PadLayout
    from pipeline import run_layout
    L, B, b, groups = PADS["LA-2.5-1.5"]
    cfg = kimia_config()
    cfg.foundation.L, cfg.foundation.B, cfg.foundation.b = L, B, b
    cfg.steel.feed_foundation = True
    res, *_ = run_layout(PadLayout([Group(ALL_EQUIPMENT[t], p) for t, p in groups]), cfg)
    gi, d = res.structures[0]
    eq = res.layout.groups[gi].eq
    assert eq.Ws == pytest.approx(d.weight * cfg.steel.connection_factor, abs=0.1)
    assert eq.As == pytest.approx(d.wind_area, abs=1e-3)
    assert eq.Ws < ALL_EQUIPMENT["LA63"].Ws


def test_sap_export_format_matches_office_files(tmp_path):
    """SAP 14.2.2 فقط CR+LF می‌خواند؛ PROGRAM CONTROL باید اولین جدول و Version=14.2.2 باشد."""
    d, *_ = _design("CVT63_1")
    path = write_model(d.model, tmp_path / "c.s2k")
    b = Path(path).read_bytes()
    assert b.replace(b"\r\n", b"").count(b"\n") == 0 and b.replace(b"\r\n", b"").count(b"\r") == 0
    lines = b.decode("latin-1").split("\r\n")
    assert lines[0].startswith("File ") and lines[1] == ""
    assert lines[2] == 'TABLE:  "PROGRAM CONTROL"' and "Version=14.2.2" in lines[3]
    assert lines[-2] == "END TABLE DATA"
    office = (Path(__file__).parent / "data" / "sap" / "LA.s2k").read_bytes().decode("latin-1")
    assert office.split("\r\n")[2] == lines[2]          # همان سرآیند جدول فایل‌های دفتر
