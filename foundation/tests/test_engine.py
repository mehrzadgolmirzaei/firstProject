"""
اعتبارسنجی موتور در برابر دفترچه کامی‌آباد.

این اعداد مرجع‌اند: اگر تستی از این فایل شکست، یعنی رفتار موتور عوض شده
و باید قبل از هر چیز دلیلش روشن شود.
"""
import pytest
from config import ProjectConfig
from equipment import CATALOG
from engine import from_config, quantities
from design import design_all
from pipeline import run

# ابعاد دفترچه EQUIPMENT CALCULATION-KAMI ABAD-A2 (ویرایش ۴)
NOTEBOOK = {"LA": 2.0, "CB": 2.3, "CT": 2.2, "CVT": 1.9,
            "PI": 2.5, "DSE": 1.8, "DS": 1.8, "DSROW": 1.7}


def _run(tag, edition):
    cfg = ProjectConfig()
    cfg.seismic.edition = edition
    res, seis, des, qty, bbs = run(CATALOG[tag], cfg)
    return cfg, from_config(cfg)[0], seis, res


@pytest.mark.parametrize("tag,side", NOTEBOOK.items())
def test_edition4_matches_notebook(tag, side):
    _, _, _, res = _run(tag, 4)
    assert res is not None and res.ok
    assert res.geometry.L == pytest.approx(side)
    assert res.geometry.B == pytest.approx(side)


def test_edition4_coefficients():
    _, _, seis, _ = _run("LA", 4)
    assert seis.ch == pytest.approx(0.5775, abs=1e-4)
    assert seis.cv == pytest.approx(0.294, abs=1e-4)


def test_edition5_la():
    _, _, seis, res = _run("LA", 5)
    assert seis.ch == pytest.approx(0.287, abs=1e-3)
    assert res.geometry.L == pytest.approx(1.9)


def test_quantities_match_drawing_06_4LA_C():
    cfg, soil, _, res = _run("LA", 4)
    q = quantities(res, CATALOG["LA"], soil)
    assert q["concrete"] == pytest.approx(2.24, abs=1e-3)
    assert q["lean"] == pytest.approx(0.484, abs=1e-3)


def test_pad_rebar_matches_drawing():
    cfg, soil, _, res = _run("LA", 4)
    des = design_all(res, CATALOG["LA"], soil, cfg.rebar)
    pad = des["pad"]
    assert (pad.bar_count, pad.bar_dia, pad.spacing) == (10, 14, 200)
