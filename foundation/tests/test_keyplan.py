"""خواندن کی‌پلن: چیدمان ستون‌ها از بلاک‌های نقشه، مطابق دفترچه ۶۳."""
from pathlib import Path

import pytest

pytest.importorskip("ezdxf")

from equipment import ALL_EQUIPMENT                        # noqa: E402
from keyplan import read_foundations, equipment_tokens    # noqa: E402
from kimia63_data import PADS                              # noqa: E402

DXF = Path(__file__).with_name("data") / "keyplan_kimia63.dxf"


@pytest.fixture(scope="module")
def found():
    return {f.name: f for f in read_foundations(str(DXF), ALL_EQUIPMENT, "63")}


def test_tokens():
    assert equipment_tokens("LA+CVT-3-2.5") == (["LA", "CVT"], None)
    assert equipment_tokens("DS-DSE-2.5-1.8") == (["DSE"], None)
    assert equipment_tokens("G1-4500-2500") == (None, "G1")


def test_unknown_blocks_skipped(found):
    assert not any(n.startswith(("G1", "GM", "shomal")) for n in found)


@pytest.mark.parametrize("block", list(PADS))
def test_keyplan_matches_notebook(found, block):
    """ابعاد و چیدمان هر پی کی‌پلن همان دفترچه است."""
    f = found[block]
    L, B, b, groups = PADS[block]
    assert f.ok, f.problem
    assert (f.L, f.B, f.b) == (L, B, b)
    assert [(g["tag"], sorted(g["positions"])) for g in f.groups] == \
           [(t, sorted(p)) for t, p in groups]


def test_same_keyplan_as_230kv_gets_230_catalog():
    """همان نام بلاک در پست ۲۳۰ به کاتالوگ ۲۳۰ می‌رود (CT نه CT63)."""
    found = {f.name: f for f in read_foundations(str(DXF), ALL_EQUIPMENT, "230")}
    assert found["CT-3-1.7"].groups[0]["tag"] == "CT"


def test_keyplan_layout_runs(found):
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from test_kimia63 import kimia_config
    from pipeline import run_layout
    f = found["LA+CVT-3-2.5"]
    cfg = kimia_config()
    cfg.foundation.L, cfg.foundation.B, cfg.foundation.b = f.L, f.B, f.b
    res, *_ = run_layout(f.layout(ALL_EQUIPMENT), cfg)
    assert res.checks[0].value == pytest.approx(3.74, abs=0.02)
