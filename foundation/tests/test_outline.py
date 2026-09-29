"""
خواندن اوت‌لاین سازنده (PDF): عددهای بار تجهیز، نوع تجهیز، و به‌کار رفتن عدد تأییدشده به جای
کاتالوگ در طراحی از نقشه جانمایی. PDF آزمون با لایه متنی ساخته می‌شود تا نتیجه به OCR وابسته نباشد.
"""
import json

import pymupdf
import pytest

import outline as OL
from equipment import ALL_EQUIPMENT, CATALOG_KIMIA63, outline_values
from test_web import app, _login  # noqa: F401


def _pdf(path, pages):
    doc = pymupdf.open()
    for items in pages:
        page = doc.new_page(width=842, height=595)
        for x, y, text, *rot in items:
            page.insert_text((x, y), text, fontsize=9, rotate=rot[0] if rot else 0)
    doc.save(path)
    return path


CT_PAGE = [
    (40, 40, "Current Transformer Type IMBD245"),
    (40, 60, "Capacitive voltage tap with protective cap"),
    (40, 80, "Nirou Trans Company"),
    (500, 300, "Total mass:"), (580, 300, "1720"), (610, 300, "Kg"),
    (500, 320, "Mass of oil:"), (580, 320, "315"),
    (500, 340, "Total windload area (effective)"), (680, 340, "1.96"),
    (500, 360, "Static withstand test load, F="), (680, 360, "4000"), (710, 360, "N"),
    (500, 380, "Creepage Distance/mm"), (640, 380, "7880"),
    (300, 250, "Center of gravity"), (300, 262, "1560"),
    (120, 400, "4077", 90), (160, 400, "3325", 90),
]
DS_PAGE = [
    (40, 40, "Disconnector NSA245/3150D with Earthing Switch"),
    (40, 60, "PARS SWITCH COMPANY"),
    (40, 100, "W(kg)= 2078+31.25L(m)"),
    (40, 120, "L=4500 to 5500 mm, 2\" Iron pipe galvanized"),
    (40, 140, "Total permissible force is 4000N including safety factor"),
    (300, 300, "3044"), (360, 300, "2804"),
]
LA_PAGE = [
    (40, 40, "Out Line Drawing For Surge Arrester  Type: PAE2"),
    (40, 60, "F : Max. permissible Pull load"), (40, 72, "(dynamic / static) 5850/2300 N"),
    (400, 200, "Height"), (400, 212, "2205 mm"),
    (400, 240, "Weight"), (400, 252, "227       Kg"),
]


@pytest.fixture(scope="module")
def pdf(tmp_path_factory):
    return str(_pdf(tmp_path_factory.mktemp("ol") / "outline.pdf", [CT_PAGE, DS_PAGE, LA_PAGE]))


def test_reads_each_page(pdf):
    ct, ds, la = OL.read_pdf(pdf)
    assert (ct["type"], ds["type"], la["type"]) == ("CT", "DSE", "LA")   # «Capacitive voltage tap» ≠ CVT
    assert all(p["method"] == "text" for p in (ct, ds, la))
    f = ct["fields"]
    assert f["We"]["value"] == 1720 and f["Ae"]["value"] == 1.96 and f["F"]["value"] == 4000
    assert f["he"]["value"] == pytest.approx(1.56)
    assert f["He"]["value"] == pytest.approx(4.077)       # 7880 جدول خزش است، نه اندازه
    assert 3.325 in f["He"]["options"] and not f["He"]["confident"]
    assert la["fields"]["He"]["value"] == pytest.approx(2.205) and la["fields"]["He"]["confident"]
    assert la["fields"]["We"]["value"] == 227 and la["fields"]["F"]["value"] == 2300


def test_weight_formula_per_phase(pdf):
    ds = OL.read_pdf(pdf)[1]["fields"]
    assert ds["We"]["value"] == round((2078 + 31.25 * 5.0) / 3)       # میانه L = 5 m، ÷ سه فاز
    assert "2078" in ds["We"]["note"] and not ds["We"]["confident"]
    assert ds["He"]["value"] == pytest.approx(3.044) and ds["F"]["value"] == 4000


def test_ocr_digit_fix():
    assert OL._fix_ocr("TOTALPERMISSIBLEFORCEIS338ONINCL") == "TOTALPERMISSIBLEFORCEIS3380NINCL"
    assert OL._num("3x1366") == (1366.0, 3, "")


def test_page_image_marks_values(pdf):
    p = OL.read_pdf(pdf)[0]
    png = OL.render_page(pdf, 1, p["fields"])
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_outline_values_replace_catalog_temporarily():
    before = ALL_EQUIPMENT["CT63"]
    with outline_values("63", {"CT": {"We": 999.0, "He": before.He * 2}}) as used:
        assert ALL_EQUIPMENT["CT63"].We == 999.0 and CATALOG_KIMIA63["CT63"].We == 999.0
        assert ALL_EQUIPMENT["CT63"].he == pytest.approx(before.he * 2, abs=1e-3)
        assert "CT63" in used and "اوت‌لاین" in used["CT63"].source
    assert ALL_EQUIPMENT["CT63"] is before and CATALOG_KIMIA63["CT63"] is before
    with pytest.raises(ValueError):
        OL.overrides_ok({"CT": {"We": -5}})


def test_web_outline_upload(pdf, app):  # noqa: F811
    c = app.app.test_client()
    h = {"X-CSRF-Token": _login(c)}
    with open(pdf, "rb") as fh:
        r = c.post("/api/outline", data={"file": (fh, "all.pdf"), "voltage": "230"}, headers=h,
                   content_type="multipart/form-data")
    d = r.get_json()
    assert r.status_code == 200, d
    ct = d["pages"][0]
    assert ct["catalog_key"] == "CT" and ct["catalog"]["We"] == ALL_EQUIPMENT["CT"].We
    img = c.get(ct["image"])
    assert img.status_code == 200 and img.mimetype == "image/png"
    with open(pdf, "rb") as fh:
        r = c.post("/api/outline", data={"file": (fh, "x.dxf")}, headers=h,
                   content_type="multipart/form-data")
    assert r.status_code == 400
    assert 'id="olfile"' in c.get("/final").get_data(as_text=True)


def test_layout_design_uses_outline(app, tmp_path):  # noqa: F811
    """عدد تأییدشده اوت‌لاین در طراحی کامل از نقشه جانمایی به جای کاتالوگ می‌نشیند."""
    import database as db
    from test_layoutplan import make_layout
    c = app.app.test_client()
    h = {"X-CSRF-Token": _login(c)}
    form = {"seismic.edition": "4", "seismic.a": 0.25, "seismic.b": 2.5, "seismic.i": 1.4,
            "seismic.r": 2, "soil.q_base": 1.72}
    path = make_layout(tmp_path / "layout.dxf")

    def ct_inputs(ol):
        with open(path, "rb") as fh:
            r = c.post("/api/keyplan", data={"file": (fh, "layout.dxf"), "voltage": "63",
                                             "form": json.dumps(form), "full": "1",
                                             "outline": json.dumps(ol)},
                       headers=h, content_type="multipart/form-data")
        d = r.get_json()
        assert r.status_code == 200, d
        t = [t for t in d["full"]["types"] if "CT" in t["name"]][0]
        cid = int(t["url"].rstrip("/").split("/")[-1])
        inp = json.loads(db.query("SELECT inputs FROM calculations WHERE id=?", (cid,), one=True)["inputs"])
        eqs = [inp["equipment"]] + [g["equipment"] for g in inp["layout"]["groups"] if "equipment" in g]
        return [e for e in eqs if e["tag"] == "CT63"][0]

    assert ct_inputs({})["We"] == ALL_EQUIPMENT["CT63"].We
    heavy = ct_inputs({"CT": {"We": 3000}})
    assert heavy["We"] == 3000 and "اوت‌لاین" in heavy["source"]
    assert ALL_EQUIPMENT["CT63"].We != 3000                        # کاتالوگ دست‌نخورده ماند
    # (در این نقشه CT سنگین‌تر پی بزرگ‌تری می‌خواهد و با CB کناری یک پی مشترک می‌شود)
    with open(path, "rb") as fh:
        r = c.post("/api/keyplan", data={"file": (fh, "layout.dxf"), "voltage": "63",
                                         "form": json.dumps(form), "outline": '{"CT": {"We": -1}}'},
                   headers=h, content_type="multipart/form-data")
    assert r.status_code == 400 and "اوت‌لاین" in r.get_json()["error"]


def test_project_pedestals_override_catalog():
    """ستون‌های سازه این پروژه (CVT سلیمانی: دو پایه با فاصله ۱٫۵) فقط روی گونه سه‌فاز اثر دارد."""
    ov = OL.overrides_ok({"CVT": {"n_pedestal": "2", "pedestal_spacing": "1.5"}})
    assert ov == {"CVT": {"n_pedestal": 2, "pedestal_spacing": 1.5}}
    with outline_values("63", ov):
        assert (ALL_EQUIPMENT["CVT63"].n_pedestal, ALL_EQUIPMENT["CVT63"].pedestal_spacing) == (2, 1.5)
        assert ALL_EQUIPMENT["CVT63_1"].n_pedestal == 1
    assert ALL_EQUIPMENT["CVT63"].n_pedestal == 3
    with pytest.raises(ValueError):
        OL.overrides_ok({"CVT": {"n_pedestal": 7}})


def test_missing_pdf_library_is_explained(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "pymupdf", None)
    monkeypatch.setitem(sys.modules, "fitz", None)
    with pytest.raises(RuntimeError, match="requirements"):
        OL._pymupdf()


def test_layout_or_schematic_is_not_an_outline():
    """راهنمای نقشه جانمایی همه تجهیزها را نام می‌برد؛ اوت‌لاین سکسیونر با تیغه زمین فقط دو نوع."""
    legend = "LIGHTNING ARRESTER\\nCURRENT TRANSFORMER\\nCIRCUIT BREAKER\\nPOST INSULATOR\\nDISCONNECTING SWITCH"
    assert OL.not_outline(legend)
    assert OL.not_outline("132kV Line 1 Protection Panel Schematic Diagram")
    assert OL.not_outline("General Layout & Section — HV Switchgear Layout")
    assert not OL.not_outline("Disconnector NSA245 with Earthing Switch\\nTotal permissible force")
    assert not OL.not_outline("230kV SF6 Circuit Breaker\\nPOST INSULATOR\\nSECTION A-A")


def test_web_rejects_layout_pdf_clearly(app, tmp_path):  # noqa: F811
    pdf = _pdf(tmp_path / "layout.pdf", [[(40, 40, "GENERAL LAYOUT"), (40, 60, "LIGHTNING ARRESTER"),
                                          (40, 80, "CURRENT TRANSFORMER"), (40, 100, "CIRCUIT BREAKER")]])
    c = app.app.test_client()
    h = {"X-CSRF-Token": _login(c)}
    with open(pdf, "rb") as fh:
        r = c.post("/api/outline", data={"file": (fh, "layout.pdf"), "voltage": "230"}, headers=h,
                   content_type="multipart/form-data")
    assert r.status_code == 400 and "اوت‌لاین تجهیز به نظر نمی‌رسد" in r.get_json()["error"]


def test_server_text_files_are_utf8():
    """ویندوز فارسی cp1256 است و «۳» را ندارد؛ هر نوشتن/خواندن متن باید encoding صریح داشته باشد."""
    import re
    from pathlib import Path
    src = (Path(__file__).parent.parent / "web" / "server.py").read_text(encoding="utf-8")
    calls = re.findall(r"\.(?:write_text|read_text)\((?:[^()]|\([^()]*\))*\)", src, re.S)
    assert calls and all("encoding=" in c for c in calls), [c for c in calls if "encoding=" not in c]


def test_api_errors_are_json(app, monkeypatch):  # noqa: F811
    c = app.app.test_client()
    h = {"X-CSRF-Token": _login(c)}
    monkeypatch.setattr(OL, "read_pdf", lambda *a, **k: [{"page": 1, "type": "LA", "title": "",
                                                          "method": "text", "fields": {}, "width": 1,
                                                          "height": 1, "x": object()}])
    import io
    r = c.post("/api/outline", data={"file": (io.BytesIO(b"%PDF-1.4"), "a.pdf"), "voltage": "230"},
               headers=h, content_type="multipart/form-data")
    assert r.status_code == 500 and r.is_json and "پیش‌بینی‌نشده" in r.get_json()["error"]
