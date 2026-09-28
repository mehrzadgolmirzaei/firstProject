"""
نقشه جانمایی ← فونداسیون‌ها: نقشه ساختگی سه‌بعدی و چرخیده مثل نقشه جانمایی پست ۶۳
(ترانس، LA، CT، CB، DS با فاصله‌های برش A-A)، با مانع و نماد تخت.
"""
import json
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import layoutplan as LP                                          # noqa: E402
from equipment import ALL_EQUIPMENT                              # noqa: E402
from keyplan import read_foundations                             # noqa: E402
from test_kimia63 import kimia_config                            # noqa: E402
from test_web import _login, app                                 # noqa: E402,F401

Z0 = 1779796.0                       # تراز زمین نقشه واقعی (mm)
ANG = 13.37
# (نام بلاک، موقعیت در امتداد ردیف m، عرض در امتداد ردیف، عمق، ارتفاع پای بلاک، ارتفاع)
ROW = [("TR", -23.44, 4.8, 5.8, 0.0, 4.7), ("STST-LA1", -19.18, 0.43, 2.7, 0.0, 3.0),
       ("6LA1", -19.18, 0.15, 0.15, 3.0, 1.1), ("CT63", -17.12, 0.8, 3.7, 0.0, 4.0),
       ("STST-CB", -15.18, 0.6, 2.5, 0.0, 2.65), ("CB", -15.18, 1.0, 2.3, 2.65, 1.7),
       ("6Bay - Tr 1$0$Ds-e 2250", -12.68, 1.35, 3.4, 0.0, 2.6)]
EXTRA = [("1CT1", -20.22, -3.2, 0.5, 0.5, 0.0, 4.0),             # تجهیز دیگر، کنار ردیف
         ("EARTH PLAN", -12.4, -1.9, 0.9, 0.6, 0.0, 0.0)]        # نماد تخت


def _box(blk, w, d, z0, h):
    x, y = w * 500, d * 500
    lo, hi = z0 * 1000, (z0 + h) * 1000
    pts = [(-x, -y), (x, -y), (x, y), (-x, y)]
    for z in (lo, hi):
        for a, b in zip(pts, pts[1:] + pts[:1]):
            blk.add_line((*a, z), (*b, z))
    for a in pts:
        blk.add_line((*a, lo), (*a, hi))


def make_layout(path):
    import ezdxf
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    c, s = math.cos(math.radians(ANG)), math.sin(math.radians(ANG))

    def place(name, u, v, w, d, z0, h):
        if name not in doc.blocks:
            _box(doc.blocks.new(name), w, d, z0, h)
        X, Y = (u * c - v * s) * 1000, (u * s + v * c) * 1000
        msp.add_blockref(name, (X, Y, Z0), dxfattribs={"rotation": ANG})
        msp.add_blockref(name, (X, Y, Z0), dxfattribs={"rotation": ANG})   # تکراری، مثل نقشه واقعی
    for name, u, w, d, z0, h in ROW:
        place(name, u, 0.0, w, d, z0, h)
    for name, u, v, w, d, z0, h in EXTRA:
        place(name, u, v, w, d, z0, h)
    doc.saveas(path)
    return path


@pytest.fixture(scope="module")
def layout_file(tmp_path_factory):
    return str(make_layout(tmp_path_factory.mktemp("lyt") / "layout.dxf"))


@pytest.fixture(scope="module")
def result(layout_file):
    return LP.design_layout(layout_file, kimia_config(), "63")


@pytest.mark.parametrize("name,expect", [
    ("6LA1", ["LA"]), ("STST-DS2", ["DS2"]), ("6Bay - Tr 1$0$Ds-e 2250", ["DSE"]),
    ("6Bay - Tr 2$0$XREF-63$0$6CV1700", ["CVT"]), ("pi5750", ["PI"]), ("CT63", ["CT"]),
    ("Gantry 1", ["GANTRY"]), ("SURGE COUNTER", []), ("xref-63f$0$A$C00354E74", [])])
def test_name_tokens(name, expect):
    assert LP.name_tokens(name) == expect


def test_stations_and_row(layout_file):
    items = LP.read_items(layout_file)
    assert len(items) == len(ROW) + len(EXTRA)                  # بلاک‌های تکراری یک بار
    stations, ang, _ = LP.site_stations(items, "63")
    assert math.degrees(ang) == pytest.approx(ANG, abs=0.01)
    kinds = {s.kind: s for s in stations}
    assert kinds["LA"].key == "LA63" and kinds["CB"].key == "CB63" and kinds["DSE"].key == "DSE63"
    assert "6LA1" in kinds["LA"].names                           # تجهیز روی سازه به ایستگاهش
    assert kinds["TR"].key == ""                                 # ترانس مانع است
    small_ct = [s for s in stations if "1CT1" in s.names][0]
    assert small_ct.key == "" and small_ct.note                   # جای پا برای دو ستون کافی نیست
    assert not any("EARTH PLAN" in s.names for s in stations)    # نماد تخت ایستگاه نیست
    rows = LP.find_rows(stations)
    assert len(rows) == 1
    got = [(m.kind, round(m.cx, 2)) for m in rows[0].members]
    assert got == [("LA", -19.18), ("CT", -17.12), ("CB", -15.18), ("DSE", -12.68)]


def test_pads_fit_the_space(result):
    pads = result["plan"]["pads"]
    assert [p["label"] for p in pads] == ["LA", "CT", "CB", "DSE"]
    tr = [s for s in result["plan"]["stations"] if s["label"] == "TR"][0]
    for a, b in zip(pads, pads[1:]):                             # فاصله آزاد بین پی‌های مجاور
        assert (b["cx"] - b["dx"] / 2) - (a["cx"] + a["dx"] / 2) >= 0.2 - 1e-6
    assert pads[0]["cx"] - pads[0]["dx"] / 2 - tr["x1"] >= 0.2 - 1e-6   # فاصله از ترانس
    for p in pads:                                               # هر پی زیر ایستگاه خودش
        assert abs(p["cy"]) < 0.3
    assert not [n for n in result["notes"] if "فاصله آزاد" in n]


def test_generated_keyplan_reads_back(result, tmp_path):
    path = str(tmp_path / "kp.dxf")
    LP.plan_dxf(result, path)
    back = {f.name: f for f in read_foundations(path, ALL_EQUIPMENT, "63")}
    assert set(back) == {f["name"] for f in result["foundations"]}
    for f in result["foundations"]:
        k = back[f["name"]]
        assert k.ok and (k.L, k.B) == (f["L"], f["B"]) and k.count == f["count"]


def test_web_layout_upload(layout_file, app):
    c = app.app.test_client()
    h = {"X-CSRF-Token": _login(c)}
    with open(layout_file, "rb") as fh:
        r = c.post("/api/keyplan", data={"file": (fh, "layout.dxf"), "voltage": "63"}, headers=h,
                   content_type="multipart/form-data")
    assert r.status_code == 400 and "ساختگاه" in r.get_json()["error"]
    form = {"seismic.edition": "4", "seismic.a": 0.25, "seismic.b": 2.5, "seismic.i": 1.4,
            "seismic.r": 2, "soil.q_base": 1.72}
    with open(layout_file, "rb") as fh:
        r = c.post("/api/keyplan", data={"file": (fh, "layout.dxf"), "voltage": "63",
                                         "form": json.dumps(form)},
                   headers=h, content_type="multipart/form-data")
    d = r.get_json()
    assert r.status_code == 200 and d["kind"] == "layout", d
    assert d["voltage"] == "63" and not d["voltage_changed"]
    assert {f["name"].split("-")[0] for f in d["foundations"]} == {"LA", "CT", "CB", "DSE"}
    assert all(f["b"] > 0 and f["tf"] > 0 for f in d["foundations"])
    assert c.get(d["dxf"]).status_code == 200


def test_voltage_from_layout_names(layout_file, app):
    """نقشه پست ۶۳ با سطح ولتاژ اشتباه (۲۳۰) در فرم: ولتاژ از نام بلاک‌ها (CT63) تشخیص داده می‌شود."""
    assert LP.detect_voltage(LP.read_items(layout_file)) == "63"
    c = app.app.test_client()
    h = {"X-CSRF-Token": _login(c)}
    form = {"seismic.edition": "4", "seismic.a": 0.25, "seismic.b": 2.5, "seismic.i": 1.4,
            "seismic.r": 2, "soil.q_base": 1.72}
    with open(layout_file, "rb") as fh:
        r = c.post("/api/keyplan", data={"file": (fh, "layout.dxf"), "voltage": "230",
                                         "form": json.dumps(form)},
                   headers=h, content_type="multipart/form-data")
    d = r.get_json()
    assert r.status_code == 200 and d["voltage"] == "63" and d["voltage_changed"], d
    assert all(g["tag"].endswith("63") for f in d["foundations"] for g in f["groups"])


def test_full_design_from_layout(layout_file, app):
    """یک کلیک: همه تیپ‌ها طراحی و ثبت می‌شوند، با مقاطع سازه و فهرست کل فولاد."""
    c = app.app.test_client()
    h = {"X-CSRF-Token": _login(c)}
    form = {"seismic.edition": "4", "seismic.a": 0.25, "seismic.b": 2.5, "seismic.i": 1.4,
            "seismic.r": 2, "soil.q_base": 1.72}
    with open(layout_file, "rb") as fh:
        r = c.post("/api/keyplan", data={"file": (fh, "layout.dxf"), "voltage": "63",
                                         "form": json.dumps(form), "full": "1"},
                   headers=h, content_type="multipart/form-data")
    d = r.get_json()
    assert r.status_code == 200, d
    F = d["full"]
    assert F["totals"]["pads"] == 4 and F["totals"]["concrete"] > 0
    ct = [t for t in F["types"] if t["name"].startswith("CT")][0]
    assert ct["structures"] and ct["structures"][0]["sections"]["chord"].startswith("L")
    assert {b["section"][0] for b in F["bill"]} == {"L", "U"}
    assert all(c.get(t["url"]).status_code == 200 for t in F["types"])
