"""
سامانه طراحی فونداسیون پایه تجهیزات پست — لایه وب.

اجرا:
    python server.py
سپس در مرورگر: http://127.0.0.1:5000
"""
import json, os, sys
from pathlib import Path
from dataclasses import asdict
from flask import (Flask, render_template, request, redirect, url_for, session,
                   flash, jsonify, send_file, abort, g)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import database as db
import auth
import codeprofiles as cp
import settings as st
from calc_service import build_equipment, run, to_dict
from config import ProjectConfig
from equipment import CATALOG

OUT = Path(__file__).with_name("generated")
OUT.mkdir(exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("FOUNDATION_SECRET", "change-me-in-production")
app.jinja_env.add_extension("jinja2.ext.do")


@app.before_request
def _reset_user_cache():
    g._user = None


@app.context_processor
def _inject():
    return {"user": auth.current_user(), "ROLES": auth.ROLES}


# ================================================================= ورود
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = auth.verify(request.form.get("username", ""),
                           request.form.get("password", ""))
        if not user:
            flash("نام کاربری یا رمز عبور درست نیست.", "error")
        else:
            session.clear()
            session["uid"] = user["id"]
            g._user = user
            auth.record("ورود به سامانه")
            return redirect(request.args.get("next") or url_for("dashboard"))
    return render_template("login.html")


@app.route("/logout")
def logout():
    if auth.current_user():
        auth.record("خروج از سامانه")
    session.clear()
    return redirect(url_for("login"))


# ================================================================= داشبورد
@app.route("/")
@auth.login_required
def dashboard():
    stats = {
        "calculations": db.query("SELECT COUNT(*) c FROM calculations", one=True)["c"],
        "projects": db.query("SELECT COUNT(*) c FROM projects", one=True)["c"],
        "catalog": db.query("SELECT COUNT(*) c FROM equipment_catalog", one=True)["c"],
        "users": db.query("SELECT COUNT(*) c FROM users WHERE is_active=1", one=True)["c"],
    }
    recent = db.query(
        "SELECT c.*, u.full_name AS who FROM calculations c"
        " LEFT JOIN users u ON u.id=c.run_by ORDER BY c.run_at DESC LIMIT 8")
    return render_template("dashboard.html", stats=stats,
                           recent=[dict(r) for r in recent])


# ================================================================= محاسبه
@app.route("/calculate")
@auth.login_required
def calculate():
    cat = db.query("SELECT * FROM equipment_catalog ORDER BY tag")
    subs = db.query("SELECT s.*, p.name AS project FROM substations s"
                    " LEFT JOIN projects p ON p.id=s.project_id ORDER BY s.code")
    return render_template("calculate.html",
                           catalog=[dict(r) for r in cat],
                           builtin={k: asdict(v) for k, v in CATALOG.items()},
                           substations=[dict(r) for r in subs],
                           profiles=cp.listing(),
                           defaults=asdict(ProjectConfig()))


@app.post("/api/calculate")
@auth.requires("engineer")
def api_calculate():
    form = request.get_json(force=True)
    cfg = ProjectConfig()

    # --- پارامترهای پروژه از فرم ---
    for group, keys in (("materials", ("fc", "fy", "cover", "lean")),
                        ("soil", ("q_base", "q_factor")),
                        ("wind", ("v_normal", "v_high")),
                        ("foundation", ("hp", "b", "tf")),
                        ("rebar", ("pad_dia", "col_dia", "tie_dia", "tie_spacing"))):
        target = getattr(cfg, group)
        for key in keys:
            val = form.get(f"{group}.{key}")
            if val not in (None, ""):
                cur = getattr(target, key)
                setattr(target, key, type(cur)(float(val)))

    s = cfg.seismic
    s.edition = int(form.get("seismic.edition", 5))
    for key in ("ss", "s1", "ie", "ru", "a", "b", "i", "r", "k_lateral"):
        val = form.get(f"seismic.{key}")
        if val not in (None, ""):
            setattr(s, key, float(val))
    s.soil_class = form.get("seismic.soil_class", s.soil_class)
    s.method = form.get("seismic.method", s.method)

    try:
        eq = build_equipment(form.get("equipment", {}))
    except (TypeError, ValueError) as exc:
        return jsonify({"error": f"ورودی تجهیز نامعتبر است: {exc}"}), 400

    # تجهیزاتی که سازه‌شان را سازنده می‌دهد: تا اعداد اوت‌لاین وارد نشود،
    # محاسبه اجرا نمی‌شود تا کسی سهواً با عدد نمونه نقشه نگیرد.
    base = CATALOG.get(eq.tag)
    missing = []
    if base and base.requires_outline:
        raw = form.get("equipment", {})
        LABELS = {"He": "ارتفاع تجهیز", "he": "مرکز ثقل تجهیز", "Ae": "سطح دید تجهیز",
                  "We": "وزن تجهیز", "Hs": "ارتفاع استراکچر", "As": "سطح دید استراکچر",
                  "Ws": "وزن استراکچر", "anchor_gauge": "گِیج میل مهار",
                  "base_plate": "ضلع صفحه کف", "conductor_points": "نقاط اتصال هادی",
                  "op_vertical": "بار قائم مانور", "op_horizontal": "بار افقی مانور"}
        for key in base.requires_outline:
            val = raw.get(key)
            if val in (None, "", 0) or (isinstance(val, str) and not val.strip()):
                missing.append(LABELS.get(key, key))
    if missing:
        return jsonify({"error": "این تجهیز سازه‌اش را سازنده می‌دهد؛ این مقادیر باید از "
                                 "اوت‌لاین سازنده وارد شوند: " + "، ".join(missing)}), 400

    res, seis, des, qty, bbs = run(eq, cfg)
    if res is None:
        return jsonify({"error": "تا حد جست‌وجو ابعادی پیدا نشد که همه کنترل‌ها را پاس کند."}), 200

    payload = to_dict(res, seis, des, qty, bbs, eq, cfg)
    profile_id = form.get("code_profile_id")
    calc_id = db.execute(
        "INSERT INTO calculations (project_id, substation_id, equipment_tag,"
        " code_profile_id, inputs, results, status, run_by, run_at)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (form.get("project_id") or None, form.get("substation_id") or None,
         eq.tag, profile_id or None,
         json.dumps({"equipment": asdict(eq), "config": asdict(cfg)}, ensure_ascii=False),
         json.dumps(payload, ensure_ascii=False),
         "ok" if payload["ok"] else "ng",
         auth.current_user()["id"], db.now()))
    auth.record("اجرای محاسبه", "calculation", calc_id, {"tag": eq.tag})
    payload["id"] = calc_id
    return jsonify(payload)


# ================================================================= تنظیمات نقشه
TITLE_LABELS = [
    ("DOCUMENT_TITLE", "عنوان نقشه"), ("DESC.1", "شرح ۱"), ("DESC.2", "شرح ۲"),
    ("PANEL_NAME", "نام پست"), ("DWG.", "شماره نقشه"), ("NO.P", "شماره صفحه"),
    ("T.P", "تعداد صفحات"), ("COUNT.", "شماره مدرک"), ("CONTRACT_NO.", "شماره قرارداد"),
    ("CONTRACTOR_DOC_CODE", "کد مدرک پیمانکار"),
    ("PREP", "تهیه‌کننده"), ("CHCK", "کنترل‌کننده"), ("APP", "تأییدکننده"), ("AUTH", "تصویب"),
    ("REV1", "بازنگری"), ("DATE1", "تاریخ بازنگری"), ("DESC1", "شرح بازنگری"),
    ("MOD.1", "اصلاح"), ("CHCK.1", "کنترل"), ("APPRD.1", "تأیید"),
]


@app.route("/settings", methods=["GET", "POST"])
@auth.login_required
def drawing_settings():
    if request.method == "POST":
        if auth.RANK[auth.current_user()["role"]] < auth.RANK["engineer"]:
            abort(403)
        data = {
            "notes": request.form.get("notes", ""),
            "title_block": {k: request.form.get("tb." + k, "").strip()
                            for k, _ in TITLE_LABELS},
            "drawing": {k: request.form.get("dw." + k, "").strip()
                        for k in ("scale", "detail_scale")},
            "rebar": {k: request.form.get("rb." + k, "").strip()
                      for k in ("pad_dia", "pad_spacing_max", "col_dia", "col_min_bars",
                                "tie_dia", "tie_spacing", "standee_dia")},
        }
        st.save(data, auth.current_user()["id"])
        auth.record("ویرایش تنظیمات نقشه", "settings")
        flash("تنظیمات نقشه ذخیره شد. از این پس روی نقشه‌های تازه اعمال می‌شود.", "ok")
        return redirect(url_for("drawing_settings"))

    data = st.load()
    return render_template("settings.html", data=data, labels=TITLE_LABELS,
                           defaults=asdict(ProjectConfig()))


# ================================================================= نقشه و گزارش
@app.post("/api/drawing/<int:cid>")
@auth.requires("engineer")
def api_drawing(cid):
    """تولید DXF و گزارش از روی یک محاسبه ذخیره‌شده."""
    row = db.query("SELECT * FROM calculations WHERE id=?", (cid,), one=True)
    if not row:
        return jsonify({"error": "چنین محاسبه‌ای ثبت نشده."}), 404

    saved = json.loads(row["inputs"])
    from dataclasses import asdict as _asdict
    cfg = ProjectConfig._from_dict(saved["config"])
    root = Path(__file__).resolve().parent.parent
    cfg.drawing.frame_file = str(root / Path(cfg.drawing.frame_file).name)
    cfg.drawing.template_file = str(root / Path(cfg.drawing.template_file).name)
    cfg.drawing.notes_file = str(root / Path(cfg.drawing.notes_file).name)

    conf = st.load()
    st.apply_to(cfg, conf)
    notes_text = (conf.get("notes") or "").strip()
    if notes_text:
        notes_file = OUT / f"notes_{cid}.txt"
        notes_file.write_text(notes_text, encoding="utf-8")
        cfg.drawing.notes_file = str(notes_file)

    eq = build_equipment(saved["equipment"])
    res, seis, des, qty, bbs = run(eq, cfg)
    if res is None:
        return jsonify({"error": "محاسبه بازتولید نشد."}), 400
    qty["rebar"] = sum(r["weight"] for r in bbs)

    tb = cfg.title_block.fields
    if not str(tb.get("DOCUMENT_TITLE", "")).strip():
        tb["DOCUMENT_TITLE"] = f"{eq.title.upper()} FOUNDATION"
    tb["SCALE"] = f"1/{cfg.drawing.scale:.0f}"

    dxf_name = f"{eq.tag}_{cid}.dxf"
    try:
        from drawing import FoundationDrawing
        soil, _ = from_config_for_drawing(cfg)
        dwg = FoundationDrawing(cfg)
        dwg.build(res, eq, soil, qty, bbs, seis, des)
        dwg.save(str(OUT / dxf_name))
    except ImportError:
        return jsonify({"error": "کتابخانه ezdxf نصب نیست: python -m pip install ezdxf"}), 500
    except Exception as exc:
        return jsonify({"error": f"نقشه ساخته نشد: {exc}"}), 500

    db.execute("UPDATE calculations SET dxf_path=? WHERE id=?", (dxf_name, cid))
    auth.record("تولید نقشه", "calculation", cid, {"file": dxf_name})
    return jsonify({"url": url_for("download", name=dxf_name), "name": dxf_name})


def from_config_for_drawing(cfg):
    from engine import from_config as _fc
    return _fc(cfg)


@app.route("/files/<path:name>")
@auth.login_required
def download(name):
    target = (OUT / name).resolve()
    if not str(target).startswith(str(OUT.resolve())) or not target.exists():
        abort(404)
    return send_file(target, as_attachment=True)


# ================================================================= تاریخچه
@app.route("/history")
@auth.login_required
def history():
    rows = db.query(
        "SELECT c.*, u.full_name AS who, p.name AS project"
        " FROM calculations c LEFT JOIN users u ON u.id=c.run_by"
        " LEFT JOIN projects p ON p.id=c.project_id ORDER BY c.run_at DESC LIMIT 200")
    return render_template("history.html", rows=[dict(r) for r in rows])


@app.route("/calculation/<int:cid>")
@auth.login_required
def calculation_detail(cid):
    row = db.query("SELECT c.*, u.full_name AS who FROM calculations c"
                   " LEFT JOIN users u ON u.id=c.run_by WHERE c.id=?", (cid,), one=True)
    if not row:
        abort(404)
    data = dict(row)
    data["results"] = json.loads(data["results"])
    data["inputs"] = json.loads(data["inputs"])
    return render_template("detail.html", calc=data)


# ================================================================= آیین‌نامه
@app.route("/calculation/<int:cid>/print")
@auth.login_required
def calculation_print(cid):
    """گزارش چاپی A4 — با Ctrl+P و انتخاب «Save as PDF» فایل PDF می‌دهد."""
    row = db.query("SELECT c.*, u.full_name AS who, u.initials FROM calculations c"
                   " LEFT JOIN users u ON u.id=c.run_by WHERE c.id=?", (cid,), one=True)
    if not row:
        abort(404)
    data = dict(row)
    data["results"] = json.loads(data["results"])
    data["inputs"] = json.loads(data["inputs"])
    return render_template("print.html", calc=data, conf=st.load())


@app.route("/codes")
@auth.login_required
def codes():
    profiles = cp.listing(active_only=False)
    a = request.args.get("a", type=int)
    b = request.args.get("b", type=int)
    changes = cp.diff(a, b) if a and b and a != b else None
    return render_template("codes.html", profiles=profiles,
                           changes=changes, a=a, b=b)


# ================================================================= کاتالوگ
@app.route("/catalog")
@auth.login_required
def catalog():
    rows = db.query("SELECT e.*, u.full_name AS who FROM equipment_catalog e"
                    " LEFT JOIN users u ON u.id=e.created_by ORDER BY e.tag")
    items = []
    for r in rows:
        d = dict(r)
        d["data"] = json.loads(d["data"])
        items.append(d)
    return render_template("catalog.html", items=items,
                           builtin={k: asdict(v) for k, v in CATALOG.items()})


@app.post("/catalog/import-builtin")
@auth.requires("engineer")
def catalog_import():
    uid = auth.current_user()["id"]
    added = 0
    for tag, eq in CATALOG.items():
        exists = db.query("SELECT id FROM equipment_catalog WHERE tag=? AND"
                          " IFNULL(manufacturer,'')='' AND IFNULL(model,'')=''",
                          (tag,), one=True)
        if exists:
            continue
        db.execute("INSERT INTO equipment_catalog (tag, title, data, source,"
                   " created_by, created_at) VALUES (?,?,?,?,?,?)",
                   (tag, eq.title, json.dumps(asdict(eq), ensure_ascii=False),
                    eq.source, uid, db.now()))
        added += 1
    auth.record("درج کاتالوگ پایه", "equipment_catalog", None, {"added": added})
    flash(f"{added} تجهیز از کاتالوگ پایه افزوده شد.", "ok")
    return redirect(url_for("catalog"))


# ================================================================= کاربران
@app.route("/users")
@auth.requires("admin")
def users():
    rows = db.query("SELECT * FROM users ORDER BY id")
    return render_template("users.html", rows=[dict(r) for r in rows])


@app.post("/users/new")
@auth.requires("admin")
def users_new():
    f = request.form
    try:
        uid = auth.create_user(f["username"], f["full_name"], f["password"],
                               f.get("role", "engineer"), f.get("initials"))
        auth.record("ایجاد کاربر", "users", uid, {"username": f["username"]})
        flash("کاربر ساخته شد.", "ok")
    except Exception as exc:
        flash(f"کاربر ساخته نشد: {exc}", "error")
    return redirect(url_for("users"))


@app.route("/audit")
@auth.requires("admin")
def audit():
    rows = db.query("SELECT a.*, u.full_name AS who FROM audit_log a"
                    " LEFT JOIN users u ON u.id=a.user_id ORDER BY a.at DESC LIMIT 300")
    return render_template("audit.html", rows=[dict(r) for r in rows])


@app.errorhandler(403)
def forbidden(_):
    return render_template("error.html", code=403,
                           message="این بخش برای نقش کاربری شما باز نیست."), 403


@app.errorhandler(404)
def missing(_):
    return render_template("error.html", code=404,
                           message="چنین صفحه‌ای وجود ندارد."), 404


def bootstrap():
    db.init_db()
    creds = auth.seed_admin()
    admin = db.query("SELECT id FROM users WHERE role='admin' ORDER BY id LIMIT 1", one=True)
    cp.seed_defaults(admin["id"] if admin else None)
    return creds


if __name__ == "__main__":
    creds = bootstrap()
    if creds:
        print(f"کاربر مدیر ساخته شد — {creds}  (رمز را بعد از اولین ورود عوض کنید)")
    print("سامانه روی http://127.0.0.1:5000 بالا آمد")
    app.run(debug=True, port=5000)
