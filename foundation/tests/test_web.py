"""آزمون دود سامانه وب: صفحه‌ها، محاسبه، نقشه، امنیت."""
import json
import os
from dataclasses import asdict

import pytest


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("web")
    os.environ["FOUNDATION_DB"] = str(tmp / "test.db")
    os.environ["FOUNDATION_OUT"] = str(tmp / "generated")
    os.environ["FOUNDATION_SECRET"] = "test"
    import server
    server.bootstrap()
    server.app.config["TESTING"] = True
    return server


def _login(client):
    client.get("/login")
    with client.session_transaction() as s:
        token = s["_csrf"]
    r = client.post("/login", data={"username": "admin", "password": "admin", "_csrf": token})
    assert r.status_code == 302
    client.get("/")
    with client.session_transaction() as s:
        return s["_csrf"]


@pytest.fixture()
def client(app):
    c = app.app.test_client()
    c.csrf = _login(c)
    return c


def _calc(client, tag="LA", **extra):
    from equipment import CATALOG
    body = {"equipment": asdict(CATALOG[tag]), "seismic.edition": "5", **extra}
    return client.post("/api/calculate", json=body, headers={"X-CSRF-Token": client.csrf})


@pytest.mark.parametrize("path", ["/", "/calculate", "/history", "/catalog", "/codes",
                                  "/codes?a=1&b=2", "/settings", "/users", "/audit", "/account"])
def test_pages(client, path):
    assert client.get(path).status_code == 200


def test_post_without_csrf_rejected(client):
    from equipment import CATALOG
    r = client.post("/api/calculate", json={"equipment": asdict(CATALOG["LA"])})
    assert r.status_code == 400


def test_login_does_not_redirect_offsite(app):
    c = app.app.test_client()
    c.get("/login")
    with c.session_transaction() as s:
        token = s["_csrf"]
    r = c.post("/login?next=https://evil.example", data={
        "username": "admin", "password": "admin", "_csrf": token})
    assert r.headers["Location"] == "/"


def test_calculate_and_draw(client, app):
    r = _calc(client)
    d = r.get_json()
    assert r.status_code == 200 and d["ok"]
    assert d["geometry"]["L"] == pytest.approx(1.9)
    row = app.db.query("SELECT code_profile_id FROM calculations WHERE id=?", (d["id"],), one=True)
    assert row["code_profile_id"] is not None
    r = client.post(f"/api/drawing/{d['id']}", headers={"X-CSRF-Token": client.csrf})
    assert r.status_code == 200, r.get_json()
    files = {f["kind"]: f for f in r.get_json()["files"]}
    assert set(files) == {"2d", "3d"}
    for f in files.values():
        body = client.get(f["url"]).data
        assert body.startswith(b"  0\r\nSECTION") or b"SECTION" in body[:40]
    assert r.get_json()["warnings"] == []
    assert client.get(f"/calculation/{d['id']}/print").status_code == 200


@pytest.mark.parametrize("extra", [{"seismic.edition": None}, {"seismic.soil_class": None},
                                   {"seismic.soil_class": "IX"}, {"seismic.ss": "abc"},
                                   {"materials.fc": "x"}])
def test_bad_input_is_400_not_500(client, extra):
    r = _calc(client, **extra)
    assert r.status_code in (200, 400)
    if r.status_code == 400:
        assert "error" in r.get_json()


def test_cb_requires_outline(client):
    r = _calc(client, "CB")
    assert r.status_code == 400 and "اوت‌لاین" in r.get_json()["error"]


def test_office_min_column_bars_reaches_calculation(client, app):
    """«حداقل میلگرد ستون» تنظیمات باید در خود محاسبه اثر کند، نه فقط در نقشه."""
    app.st.save({"notes": "", "title_block": {}, "drawing": {},
                 "rebar": {"col_min_bars": "16"}}, 1)
    try:
        d = _calc(client).get_json()
        assert d["design"]["pedestal"]["bars"] == 16
        saved = json.loads(app.db.query("SELECT inputs FROM calculations WHERE id=?",
                                        (d["id"],), one=True)["inputs"])
        assert saved["config"]["rebar"]["col_min_bars"] == 16
        # تغییر بعدی تنظیمات نباید نقشه این محاسبه را عوض کند
        app.st.save({"notes": "", "title_block": {}, "drawing": {},
                     "rebar": {"col_min_bars": "8"}}, 1)
        r = client.post(f"/api/drawing/{d['id']}", headers={"X-CSRF-Token": client.csrf})
        assert r.status_code == 200, r.get_json()
    finally:
        app.st.save({"notes": "", "title_block": {}, "drawing": {}, "rebar": {}}, 1)


def test_invalid_role_rejected(client, app):
    client.post("/users/new", data={"username": "x1", "full_name": "X", "password": "12345678",
                                    "role": "superuser", "_csrf": client.csrf})
    assert app.db.query("SELECT id FROM users WHERE username='x1'", one=True) is None


def test_change_password(app):
    c = app.app.test_client()
    tok = _login(c)
    app.auth.create_user("eng1", "Eng", "oldpassword", "engineer")
    c2 = app.app.test_client()
    c2.get("/login")
    with c2.session_transaction() as s:
        t = s["_csrf"]
    c2.post("/login", data={"username": "eng1", "password": "oldpassword", "_csrf": t})
    c2.get("/")
    with c2.session_transaction() as s:
        t = s["_csrf"]
    r = c2.post("/account", data={"old": "oldpassword", "new": "newpassword1",
                                  "confirm": "newpassword1", "_csrf": t})
    assert r.status_code == 302
    assert app.auth.verify("eng1", "newpassword1")


def test_design_options_from_form(client):
    d = _calc(client, "PI", **{"design.governing": "envelope", "design.bearing": "envelope"}).get_json()
    assert d["options"] == {"governing": "envelope", "bearing": "envelope"}
    assert d["geometry"]["L"] == pytest.approx(2.7)
    assert {r["key"] for r in d["comparison"]} == {"notebook", "recommended", "selected"}
    assert _calc(client, "PI", **{"design.governing": "9"}).status_code == 400


def test_print_report_shows_only_chosen_method(client):
    """گزارش چاپی سند رسمی است: روش انتخاب‌شده می‌آید، پیشنهاد و مقایسه نه."""
    d = _calc(client, "PI", **{"design.governing": "envelope"}).get_json()
    html = client.get(f"/calculation/{d['id']}/print").get_data(as_text=True)
    assert "پوش همه حالات" in html
    import re
    for w in ("پیشنهاد", "مقایسه"):
        m = re.search(w, html)
        assert m is None, html[max(0, m.start() - 200):m.end() + 50]


def test_two_pedestals_need_valid_spacing(client):
    from equipment import CATALOG
    eq = asdict(CATALOG["CT"])
    eq.update(n_pedestal=2, pedestal_spacing=None)
    h = {"X-CSRF-Token": client.csrf}
    r = client.post("/api/calculate", json={"equipment": eq}, headers=h)
    assert r.status_code == 400 and "فاصله محور" in r.get_json()["error"]
    eq.update(pedestal_spacing=0.5)
    r = client.post("/api/calculate", json={"equipment": eq, "foundation.b": 0.6}, headers=h)
    assert r.status_code == 400 and "روی هم" in r.get_json()["error"]
    eq.update(pedestal_spacing=1.7)
    d = client.post("/api/calculate", json={"equipment": eq, "foundation.b": 0.6},
                    headers=h).get_json()
    assert d["geometry"]["L"] >= 2.5 - 1e-9 and d["clashes"] == []
    assert d["design"]["anchor"]["embed"] == 700


def _preset_payload(key):
    """همان payload که «نمونه آماده» در فرم می‌سازد."""
    from presets import FOUNDATION_PRESETS, ALL_EQUIPMENT
    p = FOUNDATION_PRESETS[key]
    s = p["site"]
    g1, *rest = p["groups"]
    groups = [{"axis": g1["axis"], "x": g1["x"], "y": g1["y"], "case": g1["case"]}]
    for g in rest:
        groups.append({"equipment": {"tag": g["tag"]}, "axis": g["axis"], "x": g["x"],
                       "y": g["y"], "case": g["case"]})
    return {"equipment": asdict(ALL_EQUIPMENT[g1["tag"]]),
            "layout": {"kind": "combined", "groups": groups},
            "seismic.edition": "4", "seismic.a": s["seismic"]["a"], "seismic.b": s["seismic"]["b"],
            "seismic.i": s["seismic"]["i"], "seismic.r": s["seismic"]["r"],
            "soil.q_base": s["soil"]["q_base"], "soil.q_factor": s["soil"]["q_factor"],
            "foundation.hp": s["foundation"]["hp"], "foundation.tf": s["foundation"]["tf"],
            "foundation.b": p["b"], "foundation.L": p["L"], "foundation.B": p["B"],
            "rebar.col_dia": s["rebar"]["col_dia"], "rebar.pad_dia": s["rebar"]["pad_dia"]}


# (FS واژگونی، تنش خاک) — دفترچه VP-63POST-CAL-0004
@pytest.mark.parametrize("key,fs,q", [
    ("K63-LA", 2.32, 0.68), ("K63-CB", 2.02, 0.72), ("K63-CT", 2.06, 0.77),
    ("K63-DSE", 2.19, 0.73), ("K63-DS2", 2.19, 0.72),
    ("K63-LACVT", 3.74, 0.54), ("K63-PICVT", 2.45, 0.64)])
def test_kimia_presets_reproduce_notebook(client, app, key, fs, q):
    r = client.post("/api/calculate", json=_preset_payload(key),
                    headers={"X-CSRF-Token": client.csrf})
    d = r.get_json()
    assert r.status_code == 200, d
    assert d["checks"][0]["value"] == pytest.approx(fs, abs=0.02)
    assert d["checks"][1]["value"] == pytest.approx(q, abs=0.01)
    assert d["clashes"] == []
    # نقشه از اسنپ‌شات دوباره ساخته می‌شود و همان چیدمان را دارد
    r = client.post(f"/api/drawing/{d['id']}", headers={"X-CSRF-Token": client.csrf})
    assert r.status_code == 200, r.get_json()


def test_combined_pad_layout_saved_and_described(client, app):
    d = client.post("/api/calculate", json=_preset_payload("K63-LACVT"),
                    headers={"X-CSRF-Token": client.csrf}).get_json()
    assert d["geometry"]["n_pedestal"] == 5
    assert d["geometry"]["layout"] == "LA63×2 + CVT63×3"
    assert [g["tag"] for g in d["groups"]] == ["LA63", "CVT63"]
    saved = json.loads(app.db.query("SELECT inputs FROM calculations WHERE id=?",
                                    (d["id"],), one=True)["inputs"])
    assert saved["layout"]["kind"] == "combined"
    assert saved["layout"]["groups"][1]["equipment"]["tag"] == "CVT63"


def test_combined_pad_validation(client):
    h = {"X-CSRF-Token": client.csrf}
    body = _preset_payload("K63-LACVT")
    body["layout"]["groups"][1]["y"] = 0.3            # ردیف CVT روی ردیف LA
    r = client.post("/api/calculate", json=body, headers=h)
    assert r.status_code == 400 and "روی هم" in r.get_json()["error"]
    body = _preset_payload("K63-LA")
    body["foundation.L"] = 2.0                         # ستون‌ها از پی بیرون می‌زنند
    r = client.post("/api/calculate", json=body, headers=h)
    assert r.status_code == 400 and "بیرون" in r.get_json()["error"]
    body = _preset_payload("K63-LA")
    body["foundation.B"] = None                        # فقط یک ضلع
    r = client.post("/api/calculate", json=body, headers=h)
    assert r.status_code == 400 and "هر دو" in r.get_json()["error"]


def test_npol_changes_loads(client):
    """npol تعداد فاز روی یک سازه است و در بار ضرب می‌شود."""
    from equipment import CATALOG
    one = _calc(client, "LA").get_json()
    eq = asdict(CATALOG["LA"]); eq["npol"] = 3
    three = client.post("/api/calculate", json={"equipment": eq, "seismic.edition": "5"},
                        headers={"X-CSRF-Token": client.csrf}).get_json()
    assert three["governing"]["N"] > one["governing"]["N"] + 2 * CATALOG["LA"].We - 1


def test_calculate_page_has_presets_and_npol(client):
    html = client.get("/calculate").get_data(as_text=True)
    for s in ('id="npol"', 'id="fpreset"', "K63-LACVT", 'id="kind"', "LA63"):
        assert s in html
    assert 'id="base_plate"' not in html
