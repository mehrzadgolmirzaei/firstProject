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
