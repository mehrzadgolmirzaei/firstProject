"""کاربران، نقش‌ها و نشست."""
import functools
from flask import session, redirect, url_for, request, abort, g
from werkzeug.security import generate_password_hash, check_password_hash
from database import query, execute, now, log

ROLES = {"admin": "مدیر سامانه", "engineer": "مهندس طراح", "viewer": "بیننده"}
RANK = {"viewer": 0, "engineer": 1, "admin": 2}


def create_user(username, full_name, password, role="engineer", initials=None):
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
