"""کاربران، نقش‌ها، نشست و حفاظت فرم‌ها."""
import functools
import hmac
import secrets
from urllib.parse import urlsplit
from flask import session, redirect, url_for, request, abort, g
from markupsafe import Markup
from werkzeug.security import generate_password_hash, check_password_hash
from database import query, execute, now, log

ROLES = {"admin": "مدیر سامانه", "engineer": "مهندس طراح", "viewer": "بیننده"}
RANK = {"viewer": 0, "engineer": 1, "admin": 2}


MIN_PASSWORD = 8


def create_user(username, full_name, password, role="engineer", initials=None):
    if role not in ROLES:
        raise ValueError(f"نقش نامعتبر: {role}")
    if not username.strip() or not full_name.strip():
        raise ValueError("نام کاربری و نام لازم است")
    return execute(
        "INSERT INTO users (username, full_name, password_hash, role, initials, created_at)"
        " VALUES (?,?,?,?,?,?)",
        (username.strip(), full_name.strip(), generate_password_hash(password),
         role, (initials or "").strip() or None, now()))


def seed_admin():
    if query("SELECT id FROM users LIMIT 1", one=True):
        return None
    create_user("admin", "مدیر سامانه", "admin", "admin", "ADM")
    return "admin / admin"


def change_password(user_id, old, new):
    row = query("SELECT password_hash FROM users WHERE id=?", (user_id,), one=True)
    if not row or not check_password_hash(row["password_hash"], old):
        raise ValueError("رمز فعلی درست نیست")
    if len(new) < MIN_PASSWORD:
        raise ValueError(f"رمز تازه باید دست‌کم {MIN_PASSWORD} نویسه باشد")
    execute("UPDATE users SET password_hash=? WHERE id=?",
            (generate_password_hash(new), user_id))


def verify(username, password):
    row = query("SELECT * FROM users WHERE username=? AND is_active=1",
                (username.strip(),), one=True)
    if row and check_password_hash(row["password_hash"], password):
        return dict(row)
    return None


def current_user():
    uid = session.get("uid")
    if not uid:
        return None
    if getattr(g, "_user", None) is None:
        row = query("SELECT * FROM users WHERE id=? AND is_active=1", (uid,), one=True)
        g._user = dict(row) if row else None
    return g._user


def login_required(view):
    @functools.wraps(view)
    def wrapped(*a, **kw):
        if not current_user():
            return redirect(url_for("login", next=request.path))
        return view(*a, **kw)
    return wrapped


def requires(role):
    """حداقل نقش لازم برای دسترسی."""
    def deco(view):
        @functools.wraps(view)
        def wrapped(*a, **kw):
            user = current_user()
            if not user:
                return redirect(url_for("login", next=request.path))
            if RANK.get(user["role"], -1) < RANK[role]:
                abort(403)
            return view(*a, **kw)
        return wrapped
    return deco


def record(action, entity=None, entity_id=None, detail=None):
    user = current_user()
    log(user["id"] if user else None, action, entity, entity_id, detail,
        request.remote_addr if request else None)


def safe_next(target):
    """فقط مسیرهای داخلی همین سامانه؛ جلوی هدایت به سایت بیرونی را می‌گیرد."""
    if not target:
        return None
    parts = urlsplit(target)
    if parts.scheme or parts.netloc or not target.startswith("/") or target.startswith("//"):
        return None
    return target


# ---------------------------------------------------------------- CSRF
def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(32)
    return session["_csrf"]


def csrf_field():
    return Markup(f'<input type="hidden" name="_csrf" value="{csrf_token()}">')


def check_csrf():
    """هر درخواست POST باید توکن نشست را همراه داشته باشد (فیلد فرم یا هدر)."""
    if request.method != "POST":
        return
    sent = request.form.get("_csrf") or request.headers.get("X-CSRF-Token") or ""
    expected = session.get("_csrf") or ""
    if not expected or not hmac.compare_digest(sent, expected):
        abort(400, "توکن فرم نامعتبر است — صفحه را تازه کنید و دوباره تلاش کنید.")
