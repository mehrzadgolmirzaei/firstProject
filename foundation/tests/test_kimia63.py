"""
اعتبارسنجی پست ۶۳/۲۰ کیمیا در برابر دفترچه VP-63POST-CAL-0004 (7390-SB-KIM-CV-CAL-104).

پی‌های ۶۳ مشترک و مستطیلی‌اند و ابعادشان را مهندس داده؛ پس اینجا سامانه در
«حالت کنترل» (L و B داده‌شده) اجرا می‌شود و هر عدد جدول‌ها و کنترل‌های دفترچه
باید دربیاید. اعداد دفترچه گرد شده‌اند (مثلاً Fe=13 به جای 12.7)، پس نیروها با
تلرانس نسبی ۱٪ و ضرایب با دو رقم اعشار مقایسه می‌شوند.
"""
import pytest

from config import ProjectConfig
from equipment import CATALOG_KIMIA63 as K
from padlayout import PadLayout, row
from pipeline import run_layout


def kimia_config():
    cfg = ProjectConfig()
    s = cfg.seismic
    s.edition, s.a, s.b, s.i, s.r = 4, 0.25, 2.5, 1.4, 2.0      # Ch=0.4375 , Cv=0.245
    cfg.soil.q_base, cfg.soil.q_factor = 1.72, 1.33              # q_all = 2.29
    cfg.foundation.hp, cfg.foundation.tf, cfg.foundation.b = 1.0, 0.4, 0.6
    cfg.rebar.col_dia = 14
    return cfg


# (چیدمان، L، B، ضلع ستون، حالت دستی هر گروه)
FOUNDATIONS = {
    "LA":   (lambda: PadLayout([row(K["LA63"])]), 2.5, 1.5, 0.6, None),
    "CB":   (lambda: PadLayout([row(K["CB63"])]), 3.2, 2.0, 0.7, None),
    "CT":   (lambda: PadLayout([row(K["CT63"])]), 3.0, 1.7, 0.6, None),
    "DSE":  (lambda: PadLayout([row(K["DSE63"])]), 2.5, 1.8, 0.6, None),
    "DS2":  (lambda: PadLayout([row(K["DS2_63"])]), 2.5, 2.1, 0.6, None),
    "LA/CVT": (lambda: PadLayout([row(K["LA63"], y=0.75), row(K["CVT63"], y=-0.75)]),
               3.8, 2.5, 0.6, None),
    # دفترچه برای PI حالت ۵ را برداشته (برچسبش «۴» است)؛ قاعده N+V+M حالت ۳ می‌دهد
    "PI/CVT": (lambda: PadLayout([row(K["PI63"], axis="y", x=0.75, case=5),
                                  row(K["CVT63_1"], x=-0.75)]), 3.0, 3.0, 0.6, None),
}

# نیروهای حاکم سرویس (N_max، N_min، V، M) و نهایی — جدول «MAXIMUM FORCES»
GOVERNING = {
    "LA":  ((700, 520, 720, 2537), (770, 572, 792, 2791)),
    "CB":  ((2523, -237, 1909, 5942), (2775, -261, 2100, 6536)),
    "CT":  ((2160, 1310, 1444, 4283), (2376, 1441, 1588, 4711)),
    "DSE": ((1780, 1080, 1220, 3831), (1958, 1188, 1342, 4214)),
    "DS2": ((1830, 1110, 1238, 5689), (2013, 1221, 1362, 6258)),
}

# واژگونی و تنش خاک: (M_o، W، FS، e، q_max)
STABILITY = {
    "LA":     (3545, 10963, 2.32, 0.32, 0.68),
    "CB":     (8615, 17366, 2.02, 0.50, 0.72),
    "CT":     (6305, 15284, 2.06, 0.41, 0.77),
    "DSE":    (5539, 13485, 2.19, 0.41, 0.73),
    "DS2":    (7422, 15476, 2.19, 0.48, 0.72),
    "LA/CVT": (9369, 28058, 3.74, 0.33, 0.54),
    "PI/CVT": (15710, 25633, 2.45, 0.61, 0.64),
}


def _run(name):
    make, L, B, b, _ = FOUNDATIONS[name]
    cfg = kimia_config()
    cfg.foundation.L, cfg.foundation.B, cfg.foundation.b = L, B, b
    return run_layout(make(), cfg)


def _close(a, b, rel=0.01, abs_=3):
    return abs(a - b) <= max(abs_, rel * abs(b))


@pytest.mark.parametrize("name", list(GOVERNING))
def test_governing_forces(name):
    res, *_ = _run(name)
    (sv, ul) = GOVERNING[name]
    g, u = res.governing, res.ultimate
    for got, exp in zip((g.Nmax, g.Nmin, g.V, g.M), sv):
        assert _close(got, exp), (name, "service", got, exp)
    for got, exp in zip((u.Nmax, u.Nmin, u.V, u.M), ul):
        assert _close(got, exp), (name, "ultimate", got, exp)


def test_load_table_la():
    """جدول «CALCULATION OF FORCES» برق‌گیر، هر پنج حالت."""
    res, *_ = _run("LA")
    table = [(610, 610, 424, 1369), (610, 610, 617, 1680), (610, 610, 756, 2589),
             (759, 461, 502, 1509), (700, 520, 720, 2537)]
    for c, exp in zip(res.cases, table):
        for got, e in zip((c.Nmax, c.Nmin, c.V, c.M), exp):
            assert _close(got, e), (c.no, got, e)


@pytest.mark.parametrize("name", list(STABILITY))
def test_overturning_and_soil(name):
    res, *_ = _run(name)
    mo, w, fs, e, q = STABILITY[name]
    ov, soil = res.checks[0], res.checks[1]
    assert _close(res.overturning_moment, mo), (res.overturning_moment, mo)
    assert _close(res.w_total, w), (res.w_total, w)
    assert ov.value == pytest.approx(fs, abs=0.02)
    assert res.eccentricity == pytest.approx(e, abs=0.01)
    assert soil.value == pytest.approx(q, abs=0.01)
    assert res.ok


def test_weights_la():
    res, *_ = _run("LA")
    assert res.w_concrete == pytest.approx(5550, abs=1)
    assert res.w_soil == pytest.approx(4893, abs=1)


def test_uplift_la():
    """طول بلندشدگی ۰٫۳۰ ≤ B/4 = ۰٫۳۸ (صفحه ۱۳)."""
    res, *_ = _run("LA")
    up = res.checks[2]
    assert up.value == pytest.approx(0.30, abs=0.01) and up.passed


def test_pedestal_la():
    """M_u1 = (792×1+2791)/2 = 1792 ؛ ρg ≥ 0.005 ← 12Ф14 (صفحه ۱۲)."""
    res, seis, des, *_ = _run("LA")
    ped = des["pedestal"]
    assert ped.mu / 100 == pytest.approx(1792, abs=2)
    assert (ped.bar_count, ped.bar_dia) == (12, 14)


def test_pedestal_cb():
    """ستون ۷۰ سانتی CB: ρg ≥ 0.005 ← 16Ф14 = 24.63 cm² (صفحه ۲۲)."""
    res, seis, des, *_ = _run("CB")
    assert (des["pedestal"].bar_count, des["pedestal"].bar_dia) == (16, 14)


def test_pad_la():
    """M_u(A-A) = 1656 kg·m ؛ Ф14 با حداکثر فاصله ۲۰۰ ← ۱۳ عدد روی ۲٫۵ متر (صفحه ۱۳ و ۱۴)."""
    res, seis, des, *_ = _run("LA")
    pad = des["pad"]
    assert pad.mu / 100 == pytest.approx(1656, rel=0.01)
    assert pad.bar_count == 13 and pad.spacing == 200


@pytest.mark.parametrize("name,tension,shear", [
    ("LA", 1814, 99), ("CB", 4118, 263), ("CT", 3003, 199)])
def test_anchor_forces(name, tension, shear):
    res, seis, des, *_ = _run(name)
    a = des["anchor"]
    assert _close(a.tension, tension, abs_=5), (a.tension, tension)
    assert _close(a.shear, shear, abs_=2), (a.shear, shear)


def test_anchor_capacity_and_embed_la():
    """A_se = 2.56 cm² ، φN_sa = 9984 ، φV_sa = 5530 ، L_d = 634 ← مدفون ۷۰۰ (صفحه ۱۵ و ۱۶)."""
    res, seis, des, *_ = _run("LA")
    a = des["anchor"]
    assert a.a_se == pytest.approx(2.56, abs=0.01)
    assert a.phi_nsa == pytest.approx(9984, rel=0.005)
    assert a.phi_vsa == pytest.approx(5530, rel=0.005)
    assert a.ld == pytest.approx(634, abs=1)
    assert a.embed == 700 and a.ok


def test_punching_capacity_la():
    """φV_c = 0.75 × min(319.6 , 202.9 , 213.1) = 152.2 ton (صفحه ۱۷)."""
    res, seis, des, *_ = _run("LA")
    assert des["punching"].capacity / 1000 == pytest.approx(152.2, rel=0.01)


def test_design_mode_finds_pad_no_bigger_than_notebook():
    """در حالت طراحی (بدون L و B)، پی پیدا شده از پی دفترچه بزرگ‌تر نیست."""
    for name in ("LA", "CT", "DSE"):
        make, L, B, b, _ = FOUNDATIONS[name]
        cfg = kimia_config()
        cfg.foundation.b = b
        res, *_ = run_layout(make(), cfg)
        assert res.ok
        assert res.geometry.L * res.geometry.B <= L * B + 1e-9, name


def test_combined_pad_drawing_cuts_through_pedestal_row(tmp_path):
    """پی LA/CVT: برش A-A از ردیف سه‌ستونه CVT می‌گذرد، نه از بین دو ردیف."""
    pytest.importorskip("ezdxf")
    from drawing import FoundationDrawing
    from engine import from_config
    make, L, B, b, _ = FOUNDATIONS["LA/CVT"]
    cfg = kimia_config()
    cfg.foundation.L, cfg.foundation.B, cfg.foundation.b = L, B, b
    lay = make()
    res, seis, des, qty, bbs = run_layout(lay, cfg)
    dwg = FoundationDrawing(cfg).build(res, lay.main, from_config(cfg)[0], qty, bbs, seis, des)
    assert dwg._cut_y() == pytest.approx(-750)
    assert not dwg.outside and not dwg.overlaps
    assert {p.tag for p in dwg.fm.pedestals} == {"LA63", "CVT63"}
