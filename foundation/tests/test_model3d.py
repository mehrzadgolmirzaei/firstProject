"""آزمون مدل سه‌بعدی: فایل سالم، همه اجزا حجم واقعی، هم‌خوان با مدل مرکزی."""
import ezdxf
import pytest
from ezdxf.acis import api as acis

from config import ProjectConfig
from equipment import CATALOG
from pipeline import run
import model
import model3d


@pytest.mark.parametrize("tag", ["LA", "DSE"])
def test_3d_file(tag, tmp_path):
    cfg = ProjectConfig()
    eq = CATALOG[tag]
    res, seis, des, qty, bbs = run(eq, cfg)
    fm = model.build(res, eq, des, cfg)
    path = tmp_path / "f3d.dxf"
    model3d.export(fm, eq, str(path))

    doc = ezdxf.readfile(str(path))
    assert len(doc.audit().errors) == 0
    msp = doc.modelspace()
    assert set(e.dxftype() for e in msp) == {"3DSOLID"}
    layers = {e.dxf.layer for e in msp}
    assert {"F-LEAN", "F-CONCRETE", "F-ANCHOR", "F-REBAR-01", "F-REBAR-02"} <= layers

    # هر قطعه میلگرد مدل یک حجم در فایل
    segments = sum(len(b.points) - (0 if b.closed else 1) for b in fm.bars)
    rebar = [e for e in msp if e.dxf.layer.startswith("F-REBAR")]
    assert len(rebar) == segments

    # حجم‌ها قابل خواندن‌اند (ACIS معتبر)
    for e in list(msp)[:5]:
        assert acis.load_dxf(e)
