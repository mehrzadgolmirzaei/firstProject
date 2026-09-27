"""
سامانه طراحی فونداسیون پایه تجهیزات پست — لایه وب.

اجرا:
    python server.py
سپس در مرورگر: http://127.0.0.1:5000
"""
import json, os, secrets, sys
from pathlib import Path
from dataclasses import asdict
from flask import (Flask, render_template, request, redirect, url_for, session,
                   flash, jsonify, send_file, abort, g)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import database as db
import auth
import codeprofiles as cp
import settings as st
from calc_service import (build_equipment, run_layout, to_dict, layout_from_spec,
                          layout_problems, ALL_EQUIPMENT, VOLTAGE_LEVELS, EQUIPMENT_TYPES)
from config import ProjectConfig
from engine import from_config, GOVERNING_OPTIONS, BEARING_OPTIONS, RECOMMENDED, WHY
from equipment import CATALOG  # noqa: F401
from seismic import FS_TABLE

VERSION = "1.7.1"      # در منوی کناری دیده می‌شود؛ نشانی فایل‌های css/js هم با آن عوض می‌شود

OUT = Path(os.environ.get("FOUNDATION_OUT") or Path(__file__).with_name("generated"))
OUT.mkdir(parents=True, exist_ok=True)


def _secret_key():
    """کلید نشست: از متغیر محیطی، وگرنه یک‌بار ساخته و کنار برنامه نگه داشته می‌شود."""
    env = os.environ.get("FOUNDATION_SECRET")
    if env:
        return env
    path = Path(__file__).with_name(".secret_key")
    if not path.exists():
        path.write_text(secrets.token_hex(32))
    return path.read_text().strip()


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024        # کی‌پلن‌ها چند مگابایت‌اند
app.secret_key = _secret_key()
app.jinja_env.add_extension("jinja2.ext.do")


@app.before_request
def _before():
    g._user = None
    auth.check_csrf()


@app.context_processor
def _inject():
    return {"user": auth.current_user(), "ROLES": auth.ROLES,
            "csrf_token": auth.csrf_token, "csrf_field": auth.csrf_field,
            "VERSION": VERSION}


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
            return redirect(auth.safe_next(request.args.get("next")) or url_for("dashboard"))
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
                           builtin={k: asdict(v) for k, v in ALL_EQUIPMENT.items()},
                           voltages=VOLTAGE_LEVELS, types=EQUIPMENT_TYPES,
                           guide=__import__("guide").by_id(),
                           # ترتیب فهرست تجهیز (tojson کلیدها را الفبایی می‌کند)
                           voltage_order={v: list(l["types"].items())
                                          for v, l in VOLTAGE_LEVELS.items()},
                           substations=[dict(r) for r in subs],
                           profiles=cp.listing(),
                           defaults=asdict(_office_config()),
                           options=design_options())


def _office_config():
    """پیش‌فرض‌ها + تنظیمات دفتر (مثلاً قطر آرماتور)، برای مقدار اولیه فرم."""
    cfg = ProjectConfig()
    st.apply_to(cfg, st.load(), parts=st.ENGINEERING_PARTS)
    return cfg


def design_options():
    return {"governing": GOVERNING_OPTIONS, "bearing": BEARING_OPTIONS,
            "recommended": RECOMMENDED, "why": WHY}


class InputError(ValueError):
    pass


def _number(form, key, cast=float):
    val = form.get(key)
    if val is None or (isinstance(val, str) and not val.strip()):
        return None
    try:
        return cast(float(val))
    except (TypeError, ValueError):
        raise InputError(f"مقدار «{key}» عدد نیست: {val!r}")


def _choice(form, key, allowed, default):
    val = form.get(key)
    if val in (None, ""):
        return default
    if str(val) not in allowed:
        raise InputError(f"مقدار «{key}» باید یکی از {', '.join(allowed)} باشد")
    return str(val)


def config_from_form(form) -> ProjectConfig:
    """
    ساخت تنظیمات محاسبه از فرم.
    ترتیب: پیش‌فرض ← تنظیمات دفتر (آرماتور) ← مقادیر فرم.
    نتیجه کامل در اسنپ‌شات ذخیره می‌شود؛ تغییر بعدی تنظیمات روی این محاسبه اثر ندارد.
    """
    cfg = ProjectConfig()
    st.apply_to(cfg, st.load(), parts=st.ENGINEERING_PARTS)
    for group, keys in (("materials", ("fc", "fy", "cover", "lean")),
                        ("soil", ("q_base", "q_factor")),
                        ("wind", ("v_normal", "v_high")),
                        ("foundation", ("hp", "b", "tf", "min_projection", "L", "B")),
                        ("rebar", ("pad_dia", "col_dia", "tie_dia", "tie_spacing")),
                        ("steel", ("leg_width", "k_chord", "fy", "connection_factor", "panel"))):
        target = getattr(cfg, group)
        for key in keys:
            cur = getattr(target, key)
            val = _number(form, f"{group}.{key}", type(cur))
            if val is not None:
                setattr(target, key, val)

    for key in ("enabled", "feed_foundation"):
        val = form.get(f"steel.{key}")
        if val is not None:
            setattr(cfg.steel, key, val in (True, 1, "1", "true", "on"))
    if not 0.2 <= cfg.steel.leg_width <= 1.0:
        raise InputError("ضلع پایه مشبک باید بین ۰٫۲ و ۱ متر باشد")
    if cfg.steel.k_chord not in (1.0, 2.0):
        raise InputError("ضریب طول مؤثر نبشی اصلی باید ۱ یا ۲ باشد")

    s = cfg.seismic
    s.edition = int(_choice(form, "seismic.edition", ("4", "5"), str(s.edition)))
    for key in ("ss", "s1", "ie", "ru", "a", "b", "i", "r", "k_lateral"):
        val = _number(form, f"seismic.{key}")
        if val is not None:
            setattr(s, key, val)
    s.soil_class = _choice(form, "seismic.soil_class", tuple(FS_TABLE), s.soil_class)
    s.method = _choice(form, "seismic.method", ("rigid", "static"), s.method)
    d = cfg.design
    d.governing = _choice(form, "design.governing", tuple(GOVERNING_OPTIONS), d.governing)
    d.bearing = _choice(form, "design.bearing", tuple(BEARING_OPTIONS), d.bearing)
    return cfg


def _profile_for(form, edition):
    pid = form.get("code_profile_id")
    if pid:
        return int(pid)
    row = db.query("SELECT id FROM code_profiles WHERE edition=? AND is_active=1"
                   " ORDER BY id DESC LIMIT 1", (edition,), one=True)
    return row["id"] if row else None


@app.post("/api/calculate")
@auth.requires("engineer")
def api_calculate():
    form = request.get_json(silent=True)
    if not isinstance(form, dict):
        return jsonify({"error": "درخواست باید JSON باشد."}), 400
    try:
        cfg = config_from_form(form)
        eq = build_equipment(form.get("equipment") or {})
    except (TypeError, ValueError) as exc:
        return jsonify({"error": f"ورودی نامعتبر است: {exc}"}), 400

    # چیدمان پی: منفرد مربعی (۲۳۰/۴۰۰) یا مشترک مستطیلی با یک یا دو گروه تجهیز (۶۳)
    try:
        layout, layout_spec = layout_from_spec(form.get("layout"), eq)
    except (TypeError, ValueError, KeyError) as exc:
        return jsonify({"error": f"چیدمان پی نامعتبر است: {exc}"}), 400
    f = cfg.foundation
    if bool(f.L) != bool(f.B):
        return jsonify({"error": "برای کنترل یک پی معلوم، هر دو ضلع L و B را وارد کنید؛ "
                                 "یا هر دو را خالی بگذارید تا سامانه ابعاد را پیدا کند."}), 400
    if layout.square and f.L and abs(f.L - f.B) > 1e-9:
        return jsonify({"error": "پی منفرد مربعی است؛ L و B باید برابر باشند. برای پی "
                                 "مستطیلی نوع پی را «مشترک» انتخاب کنید."}), 400
    problems = layout_problems(layout, f.b, f.L, f.B)
    if problems:
        return jsonify({"error": " ".join(problems)}), 400

    # تجهیزاتی که سازه‌شان را سازنده می‌دهد: تا اعداد اوت‌لاین وارد نشود،
    # محاسبه اجرا نمی‌شود تا کسی سهواً با عدد نمونه نقشه نگیرد.
    base = ALL_EQUIPMENT.get(eq.tag)
    missing = []
    if base and base.requires_outline:
        raw = form.get("equipment") or {}
        LABELS = {"He": "ارتفاع تجهیز", "he": "مرکز ثقل تجهیز", "Ae": "سطح دید تجهیز",
                  "We": "وزن تجهیز", "Hs": "ارتفاع استراکچر", "As": "سطح دید استراکچر",
                  "Ws": "وزن استراکچر", "anchor_gauge": "گِیج میل مهار",
                  "base_plate": "ضلع صفحه کف", "conductor_points": "ارتفاع اتصال هادی",
                  "op_vertical": "بار قائم مانور", "op_horizontal": "بار افقی مانور"}
        for key in base.requires_outline:
            val = raw.get(key)
            if val in (None, "", 0) or (isinstance(val, str) and not val.strip()):
                missing.append(LABELS.get(key, key))
    if missing:
        return jsonify({"error": "این تجهیز سازه‌اش را سازنده می‌دهد؛ این مقادیر باید از "
                                 "اوت‌لاین سازنده وارد شوند: " + "، ".join(missing)}), 400

    res, seis, des, qty, bbs = run_layout(layout, cfg)
    if res is None:
        return jsonify({"error": "تا حد جست‌وجو ابعادی پیدا نشد که همه کنترل‌ها را پاس کند."}), 200

    payload = to_dict(res, seis, des, qty, bbs, eq, cfg)
    calc_id = db.execute(
        "INSERT INTO calculations (project_id, substation_id, equipment_tag,"
        " code_profile_id, inputs, results, status, run_by, run_at)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (form.get("project_id") or None, form.get("substation_id") or None,
         eq.tag, _profile_for(form, cfg.seismic.edition),
         json.dumps({"equipment": asdict(eq), "config": asdict(cfg), "layout": layout_spec},
                    ensure_ascii=False),
         json.dumps(payload, ensure_ascii=False),
         "ok" if payload["ok"] else "ng",
         auth.current_user()["id"], db.now()))
    auth.record("اجرای محاسبه", "calculation", calc_id, {"tag": eq.tag})
    payload["id"] = calc_id
    return jsonify(payload)


@app.post("/api/keyplan")
@auth.requires("engineer")
def api_keyplan():
    """
    خواندن کی‌پلن فونداسیون (DXF): انواع پی، ابعاد، ستون‌ها و تجهیز هر ستون.
    فایل فقط خوانده و پاک می‌شود؛ چیدمان انتخاب‌شده با خود محاسبه در اسنپ‌شات می‌ماند.
    """
    f = request.files.get("file")
    if not f or not f.filename.lower().endswith(".dxf"):
        return jsonify({"error": "فایل کی‌پلن باید DXF باشد (در اتوکد: Save As ← DXF)."}), 400
    tmp = OUT / f"keyplan_{secrets.token_hex(8)}.dxf"
    f.save(tmp)
    try:
        from keyplan import read_foundations
        voltage = request.form.get("voltage") or "63"
        if voltage not in VOLTAGE_LEVELS:
            return jsonify({"error": "سطح ولتاژ نامعتبر است."}), 400
        found = read_foundations(str(tmp), ALL_EQUIPMENT, voltage)
    except ImportError:
        return jsonify({"error": "کتابخانه ezdxf نصب نیست: python -m pip install ezdxf"}), 500
    except Exception as exc:
        return jsonify({"error": f"کی‌پلن خوانده نشد: {exc}"}), 400
    finally:
        tmp.unlink(missing_ok=True)
    if not found:
        return jsonify({"error": "هیچ بلاک پی با نام تجهیز (مثل LA+CVT-3-2.5) در کی‌پلن "
                                 "پیدا نشد."}), 400
    auth.record("خواندن کی‌پلن", "keyplan", None, {"file": f.filename, "types": len(found)})
    return jsonify({"file": f.filename, "foundations": [x.to_dict() for x in found]})


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
def _same_result(stored, fresh):
    """آیا بازتولید از اسنپ‌شات همان نتیجه ذخیره‌شده را داد؟"""
    a, b = stored["geometry"], fresh["geometry"]
    if any(abs(a[k] - b[k]) > 1e-9 for k in ("L", "B", "tf", "hp", "b")):
        return False
    for key in ("pad", "pedestal"):
        x, y = stored["design"][key], fresh["design"][key]
        if (x["bars"], x["dia"], x["spacing"]) != (y["bars"], y["dia"], y["spacing"]):
            return False
    return True


@app.post("/api/drawing/<int:cid>")
@auth.requires("engineer")
def api_drawing(cid):
    """
    تولید DXF از اسنپ‌شات یک محاسبه ذخیره‌شده.
    فقط تنظیمات ظاهری (جدول عنوان، مقیاس، یادداشت‌ها) از تنظیمات فعلی می‌آید؛
    هر چه روی عدد اثر دارد از خود اسنپ‌شات است، و اگر بازتولید با نتیجه
    ذخیره‌شده نخواند، نقشه ساخته نمی‌شود.
    """
    row = db.query("SELECT * FROM calculations WHERE id=?", (cid,), one=True)
    if not row:
        return jsonify({"error": "چنین محاسبه‌ای ثبت نشده."}), 404

    saved = json.loads(row["inputs"])
    cfg = ProjectConfig._from_dict(saved["config"])
    root = Path(__file__).resolve().parent.parent
    cfg.drawing.frame_file = str(root / Path(cfg.drawing.frame_file).name)
    cfg.drawing.template_file = str(root / Path(cfg.drawing.template_file).name)
    cfg.drawing.notes_file = str(root / Path(cfg.drawing.notes_file).name)

    conf = st.load()
    st.apply_to(cfg, conf, parts=st.PRESENTATION_PARTS)
    notes_text = (conf.get("notes") or "").strip()
    if notes_text:
        notes_file = OUT / f"notes_{cid}.txt"
        notes_file.write_text(notes_text, encoding="utf-8")
        cfg.drawing.notes_file = str(notes_file)

    eq = build_equipment(saved["equipment"])
    layout, _ = layout_from_spec(saved.get("layout"), eq)
    res, seis, des, qty, bbs = run_layout(layout, cfg)
    if res is None or not _same_result(json.loads(row["results"]),
                                       to_dict(res, seis, des, qty, bbs, eq, cfg)):
        return jsonify({"error": "بازتولید محاسبه از اسنپ‌شات با نتیجه ذخیره‌شده نخواند؛ "
                                 "نقشه ساخته نشد. محاسبه را دوباره اجرا کنید."}), 409

    try:
        from outputs import make_outputs
        out = make_outputs(res, eq, from_config(cfg)[0], qty, bbs, seis, des, cfg,
                           str(OUT), f"{eq.tag}_{cid}")
    except ImportError:
        return jsonify({"error": "کتابخانه ezdxf نصب نیست: python -m pip install ezdxf"}), 500
    except Exception as exc:
        app.logger.exception("drawing failed")
        return jsonify({"error": f"نقشه ساخته نشد: {exc}"}), 500

    n2, n3 = Path(out["2d"]).name, Path(out["3d"]).name
    sap = [Path(x).name for x in out.get("sap", [])]
    db.execute("UPDATE calculations SET dxf_path=?, dxf3d_path=? WHERE id=?", (n2, n3, cid))
    auth.record("تولید نقشه", "calculation", cid, {"2d": n2, "3d": n3})
    return jsonify({"files": [
        {"kind": "2d", "name": n2, "url": url_for("download", name=n2),
         "label": f"نقشه دوبعدی (مقیاس ۱:{out['scale']:.0f})"},
        {"kind": "3d", "name": n3, "url": url_for("download", name=n3),
         "label": "مدل سه‌بعدی"}] + [
        {"kind": "sap", "name": n, "url": url_for("download", name=n),
         "label": "مدل SAP سازه"} for n in sap],
        "warnings": out["warnings"]})


@app.route("/files/<path:name>")
@auth.login_required
def download(name):
    target = (OUT / name).resolve()
    if OUT.resolve() not in target.parents or not target.is_file():
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
    return render_template("print.html", calc=data, conf=st.load(), options=design_options())


# ================================================================= راهنما
@app.route("/guide")
@auth.login_required
def guide_page():
    from guide import GUIDE
    return render_template("guide.html", guide=GUIDE)


# ================================================================= آیین‌نامه
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
                           builtin={k: asdict(v) for k, v in ALL_EQUIPMENT.items()})


@app.post("/catalog/import-builtin")
@auth.requires("engineer")
def catalog_import():
    uid = auth.current_user()["id"]
    added = 0
    for tag, eq in ALL_EQUIPMENT.items():
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


# ================================================================= حساب کاربری
@app.route("/account", methods=["GET", "POST"])
@auth.login_required
def account():
    if request.method == "POST":
        f = request.form
        if f.get("new", "") != f.get("confirm", ""):
            flash("رمز تازه و تکرارش یکی نیستند.", "error")
        else:
            try:
                auth.change_password(auth.current_user()["id"], f.get("old", ""), f.get("new", ""))
                auth.record("تغییر رمز عبور", "users", auth.current_user()["id"])
                flash("رمز عبور عوض شد.", "ok")
                return redirect(url_for("dashboard"))
            except ValueError as exc:
                flash(str(exc), "error")
    return render_template("account.html", min_len=auth.MIN_PASSWORD)


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
    except (ValueError, KeyError) as exc:
        flash(f"کاربر ساخته نشد: {exc}", "error")
    except Exception as exc:
        flash("کاربر ساخته نشد — نام کاربری تکراری است؟" if "UNIQUE" in str(exc)
              else f"کاربر ساخته نشد: {exc}", "error")
    return redirect(url_for("users"))


@app.route("/audit")
@auth.requires("admin")
def audit():
    rows = db.query("SELECT a.*, u.full_name AS who FROM audit_log a"
                    " LEFT JOIN users u ON u.id=a.user_id ORDER BY a.at DESC LIMIT 300")
    return render_template("audit.html", rows=[dict(r) for r in rows])


@app.errorhandler(400)
def bad_request(exc):
    return render_template("error.html", code=400,
                           message=getattr(exc, "description", "درخواست نامعتبر")), 400


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
    port = int(os.environ.get("FOUNDATION_PORT", 5000))
    url = f"http://127.0.0.1:{port}"
    print(f"سامانه روی {url} بالا آمد — برای بستن این پنجره را ببندید")
    if os.environ.get("FOUNDATION_OPEN_BROWSER") == "1":
        import threading, webbrowser
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    app.run(debug=os.environ.get("FOUNDATION_DEBUG") == "1", port=port)
