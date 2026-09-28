"""
طراحی ردیف با محدودیت فضا — بازتولید پی‌های دفترچه ۶۳ از روی زنجیره برش طولی
نقشه جانمایی (VP-63POST-LYT-0057)، بدون وارد کردن ابعاد.
"""
import itertools
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from bay import design_bay, parse, verify, _dp, Unit, Station, plan_dxf   # noqa: E402
from test_kimia63 import kimia_config                                      # noqa: E402

KIMIA_BAY = ("GM[1.2] 1700 PR/TR[4.0] 3500 LA 2000 CT 2000 CB 2500 DS 2000 PI 1500 PI+CVT1 "
             "1500 PI 2000 DS 2500 CB 2000 CT 2500 DS/E 2500 LT/GA+CVT 1500 LA 2000 ROAD")


def _cfg():
    cfg = kimia_config()
    cfg.foundation.b = 0.6
    cfg.steel.enabled = False
    return cfg


@pytest.fixture(scope="module")
def kimia():
    return design_bay(KIMIA_BAY, _cfg())


def test_parse_chain():
    st = parse(KIMIA_BAY)
    assert [s.label for s in st][:4] == ["GM", "PR/TR", "LA", "CT"]
    assert st[2].pos == pytest.approx(5.2) and st[-1].pos == pytest.approx(31.7)
    assert st[0].keys == [] and st[0].width == 1.2 and st[1].width == 4.0
    pi_cvt = next(s for s in st if s.label == "PI+CVT1")
    assert pi_cvt.keys == ["PI63", "CVT63_1"]
    assert next(s for s in st if s.label == "LT/GA+CVT").keys == ["CVT63"]
    with pytest.raises(ValueError):
        parse("LA 2000 1500 CT")


def test_reproduces_notebook_pads_from_space_alone(kimia):
    """ابعاد پی‌ها فقط از فاصله محورها و کنترل‌ها — برابر دفترچه ۶۳."""
    by = {}
    for u in kimia["units"]:
        by.setdefault(u.label, []).append(u.choice[:3])
    assert by["LA"][0] == (1.5, 2.5, 0.4)          # دفترچه: 2.5×1.5
    assert by["CT"][0] == (1.7, 3.0, 0.4)          # دفترچه: 3.0×1.7
    assert by["DS"][0] == (1.8, 2.5, 0.4)          # دفترچه DS/DSE: 2.5×1.8
    la_cvt = by["LT/GA+CVT+LA"][0]                 # دفترچه: پی مشترک 3.8×2.5
    assert la_cvt[1] == pytest.approx(3.8) and la_cvt[0] == pytest.approx(2.3)


def test_no_overlap_and_obstacles(kimia):
    units, gap = kimia["units"], kimia["gap"]
    for a, b in zip(units, units[1:]):
        assert (b.centre - b.choice[0] / 2) - (a.centre + a.choice[0] / 2) >= gap - 1e-9
    for ob in kimia["obstacles"]:
        for u in units:
            assert abs(u.centre - ob.pos) - u.choice[0] / 2 - ob.width / 2 >= gap - 1e-9


def test_forced_merge_when_too_close():
    r = design_bay("CT 1000 CT", _cfg())
    assert len(r["units"]) == 1 and r["merges"][0][3] == "کمبود فضا"


def test_dp_is_optimal_bruteforce():
    """برنامه‌ریزی پویا = جست‌وجوی کامل روی همه ترکیب‌ها."""
    us = [Unit([Station("a", 0.0, ["LA63"])]), Unit([Station("b", 2.0, ["CT63"])]),
          Unit([Station("c", 4.0, ["CB63"])])]
    us[0].options = [(1.0, 5.0, 0.4, 2.0), (1.5, 2.5, 0.4, 1.5), (2.0, 2.0, 0.4, 1.6)]
    us[1].options = [(1.2, 6.0, 0.4, 2.9), (1.7, 3.0, 0.4, 2.04), (2.3, 2.4, 0.4, 2.2)]
    us[2].options = [(1.4, 5.8, 0.4, 3.2), (1.9, 3.4, 0.4, 2.58), (2.4, 2.9, 0.4, 2.8)]
    picks, _ = _dp(us, [], 0.2)
    best = min((c for c in itertools.product(*[u.options for u in us])
                if all((us[i + 1].centre - c[i + 1][0] / 2) - (us[i].centre + c[i][0] / 2) >= 0.2 - 1e-9
                       for i in range(2))), key=lambda c: sum(o[3] for o in c))
    assert sum(p[3] for p in picks) == pytest.approx(sum(o[3] for o in best))


def test_full_design_and_plan(tmp_path, kimia):
    r = verify(design_bay("LA 2000 CT 2000 CB", _cfg()), _cfg())
    assert all(u.ok for u in r["units"])
    path = plan_dxf(r, str(tmp_path / "bay.dxf"))
    import ezdxf
    doc = ezdxf.readfile(path)
    assert len(doc.modelspace().query('LWPOLYLINE[layer=="FOUNDATION"]')) == 3
