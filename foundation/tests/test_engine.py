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


# ------------------------------------------------------------ گزینه‌های مهندس
def _run_opt(tag, governing, bearing, edition=4):
    cfg = ProjectConfig()
    cfg.seismic.edition = edition
    cfg.design.governing, cfg.design.bearing = governing, bearing
    return run(CATALOG[tag], cfg)[0]


def test_notebook_is_default_and_reproduces_notebook():
    cfg = ProjectConfig()
    assert (cfg.design.governing, cfg.design.bearing) == ("notebook", "min")


@pytest.mark.parametrize("tag", list(NOTEBOOK))
def test_envelope_never_smaller_than_notebook(tag):
    """پوش همه حالات شامل حالت دفترچه هم هست، پس پی کوچک‌تر نمی‌دهد."""
    nb = _run_opt(tag, "notebook", "min")
    env = _run_opt(tag, "envelope", "envelope")
    assert env.geometry.L >= nb.geometry.L - 1e-9


def test_envelope_catches_wind_uplift_in_pi():
    """در PI حالت ۲ (باد شدید، ضریب ۱٫۵) بلندشدگی را حاکم می‌کند؛ روش دفترچه آن را نمی‌بیند."""
    env = _run_opt("PI", "envelope", "envelope")
    assert env.geometry.L == pytest.approx(2.7)
    rows = {r["key"]: r["side"] for r in env.comparison}
    assert rows["notebook"] == pytest.approx(2.5) and rows["recommended"] == pytest.approx(2.7)


def test_manual_case_selection():
    res = _run_opt("LA", "2", "min")
    assert all(c.case == 2 for c in res.checks)


def test_bearing_envelope_takes_worse_of_nmin_nmax():
    lo = _run_opt("CB", "notebook", "min").checks[1].value
    hi = _run_opt("CB", "notebook", "max").checks[1].value
    both = _run_opt("CB", "notebook", "envelope").checks[1].value
    assert both == pytest.approx(max(lo, hi))
