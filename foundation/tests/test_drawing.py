"""
آزمون نقشه دوبعدی: فایل سالم برای اتوکد، همه‌چیز داخل کادر، بدون هم‌پوشانی
نماها، و جدول آرماتور منطبق با مدل.
"""
import pytest
import ezdxf

from config import ProjectConfig
from equipment import CATALOG
from engine import from_config
from pipeline import run
from drawing import FoundationDrawing
import model

ROOT_FILES = {"frame_file": "frame_blank.dxf", "template_file": "template.dxf",
              "notes_file": "notes.txt"}


def _drawing(tag, edition=5, simple=False, **foundation):
    cfg = ProjectConfig()
    cfg.seismic.edition = edition
    for k, v in foundation.items():
        setattr(cfg.foundation, k, v)
    from conftest import ROOT
    for k, v in ROOT_FILES.items():
        setattr(cfg.drawing, k, str(ROOT / v))
    eq = CATALOG[tag]
    res, seis, des, qty, bbs = run(eq, cfg)
    dwg = FoundationDrawing(cfg, simple=simple).build(res, eq, from_config(cfg)[0],
                                                      qty, bbs, seis, des)
    return dwg, res, des, bbs, cfg


@pytest.mark.parametrize("tag", list(CATALOG))
@pytest.mark.parametrize("edition", [4, 5])
def test_sheet_fits(tag, edition):
    dwg, *_ = _drawing(tag, edition)
    assert dwg.outside == []
    assert dwg.overlaps == []


@pytest.mark.parametrize("hp,b,tf", [(1.5, 0.8, 0.5), (0.8, 0.6, 0.35), (1.2, 1.0, 0.6)])
def test_sheet_fits_other_proportions(hp, b, tf):
    dwg, *_ = _drawing("PI", hp=hp, b=b, tf=tf)
    assert dwg.outside == [] and dwg.overlaps == []


def test_prefers_office_scale():
    dwg, *_ = _drawing("LA", 4)
    assert dwg.s == 20


def test_dxf_is_clean_for_autocad(tmp_path):
    dwg, *_ = _drawing("DSE")
    path = tmp_path / "x.dxf"
    dwg.save(str(path))
    doc = ezdxf.readfile(str(path))
    assert len(doc.audit().errors) == 0
    for table in (doc.layers, doc.styles, doc.dimstyles):
        for rec in table:
            name = rec.dxf.name
            assert name.strip() and "|" not in name, f"invalid table name {name!r}"


def test_simple_mode_has_no_dimension_entities():
    dwg, *_ = _drawing("LA", simple=True)
    assert not dwg.msp.query("DIMENSION")


def test_bbs_counts_come_from_model():
    dwg, res, des, bbs, cfg = _drawing("DSE")
    fm = model.build(res, CATALOG["DSE"], des, cfg)
    for row in bbs:
        mark = row["pos"][:2]
        assert row["no"] <= len(fm.bars_by_mark(mark))
    assert sum(r["no"] for r in bbs) == len(fm.bars)


def test_title_block_scale_follows_chosen_scale():
    dwg, *_ = _drawing("PI", 4)
    texts = [t.dxf.text for t in dwg.msp.query("TEXT")]
    assert f"1/{dwg.s:.0f}" in texts
