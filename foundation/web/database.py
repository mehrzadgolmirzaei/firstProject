"""
دیتابیس سامانه — SQLite با کتابخانه استاندارد پایتون، بدون وابستگی بیرونی.

همه‌چیز ذخیره می‌شود: کاربران و نقش‌ها، پروژه‌ها و پست‌ها، کاتالوگ تجهیزات،
اجراهای محاسبه با اسنپ‌شات کامل ورودی و خروجی، پروفایل‌های آیین‌نامه و
سیاهه رویدادها.

قاعده‌ی بنیادی: هر اجرای محاسبه، ورودی‌ها و پروفایل آیین‌نامه‌ی لحظه‌ی اجرا را
کامل در خود نگه می‌دارد. پس تغییر بعدی کاتالوگ یا آیین‌نامه، گزارش‌های
تأییدشده‌ی قبلی را دست‌کاری نمی‌کند و هر اجرا همیشه قابل بازتولید است.
"""
import json
import sqlite3
from contextlib import closing
from datetime import datetime
import os
from pathlib import Path

DB_PATH = Path(os.environ.get("FOUNDATION_DB") or Path(__file__).with_name("foundation.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY,
    username      TEXT UNIQUE NOT NULL,
    full_name     TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'engineer',   -- admin | engineer | viewer
    initials      TEXT,                               -- برای جدول عنوان نقشه
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    id          INTEGER PRIMARY KEY,
    code        TEXT UNIQUE NOT NULL,
    name        TEXT NOT NULL,
    client      TEXT,
    contract_no TEXT,
    created_by  INTEGER REFERENCES users(id),
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS substations (
    id         INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    code       TEXT NOT NULL,
    name       TEXT NOT NULL,
    voltage    TEXT,
    -- پارامترهای ساختگاه: یک‌بار برای هر پست ثبت می‌شود
    ss         REAL, s1 REAL, soil_class TEXT DEFAULT 'III',
    map_date   TEXT,                                  -- تاریخ نقشه مرجع پیوست ۱
    q_base     REAL DEFAULT 2.83, q_factor REAL DEFAULT 1.33,
    geotech_ref TEXT,                                 -- شماره گزارش ژئوتکنیک
    UNIQUE(project_id, code)
);

CREATE TABLE IF NOT EXISTS equipment_catalog (
    id         INTEGER PRIMARY KEY,
    tag        TEXT NOT NULL,
    title      TEXT NOT NULL,
    manufacturer TEXT, model TEXT, voltage_kv INTEGER,
    data       TEXT NOT NULL,          -- JSON: He, he, Ae, Ce, We, Hs, As, Ws, Fc ...
    source     TEXT,                   -- مرجع داده، برای Audit
    created_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL,
    UNIQUE(tag, manufacturer, model)
);

CREATE TABLE IF NOT EXISTS code_profiles (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,          -- «۲۸۰۰ ویرایش ۵»
    edition     INTEGER NOT NULL,
    issued_on   TEXT,                   -- تاریخ انتشار ویرایش
    definition  TEXT NOT NULL,          -- JSON: فرمول‌ها، جداول، ضرایب
    document    TEXT,                   -- مسیر PDF پیوست
    is_active   INTEGER NOT NULL DEFAULT 1,
    notes       TEXT,
    created_by  INTEGER REFERENCES users(id),
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS calculations (
    id             INTEGER PRIMARY KEY,
    project_id     INTEGER REFERENCES projects(id),
    substation_id  INTEGER REFERENCES substations(id),
    equipment_tag  TEXT NOT NULL,
    code_profile_id INTEGER REFERENCES code_profiles(id),
    inputs         TEXT NOT NULL,       -- JSON اسنپ‌شات کامل ورودی
    results        TEXT NOT NULL,       -- JSON ابعاد، کنترل‌ها، آرماتور، متره
    status         TEXT NOT NULL,       -- ok | ng | failed
    dxf_path       TEXT,
    report_path    TEXT,
    run_by         INTEGER REFERENCES users(id),
    run_at         TEXT NOT NULL,
    approved_by    INTEGER REFERENCES users(id),
    approved_at    TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id         INTEGER PRIMARY KEY,
    user_id    INTEGER REFERENCES users(id),
    action     TEXT NOT NULL,
    entity     TEXT, entity_id INTEGER,
    detail     TEXT,
    ip         TEXT,
    at         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    id         INTEGER PRIMARY KEY,
    scope      TEXT NOT NULL DEFAULT 'global',   -- global | project
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    data       TEXT NOT NULL,                    -- JSON: notes, title_block, drawing, rebar
    updated_by INTEGER REFERENCES users(id),
    updated_at TEXT NOT NULL,
    UNIQUE(scope, project_id)
);

CREATE INDEX IF NOT EXISTS idx_calc_run   ON calculations(run_at DESC);
CREATE INDEX IF NOT EXISTS idx_calc_tag   ON calculations(equipment_tag);
CREATE INDEX IF NOT EXISTS idx_audit_at   ON audit_log(at DESC);
"""


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with closing(connect()) as conn, conn:
        conn.executescript(SCHEMA)


def now():
    return datetime.now().isoformat(timespec="seconds")


def query(sql, args=(), one=False):
    with closing(connect()) as conn:
        rows = conn.execute(sql, args).fetchall()
    return (rows[0] if rows else None) if one else rows


def execute(sql, args=()):
    with closing(connect()) as conn, conn:
        return conn.execute(sql, args).lastrowid


def log(user_id, action, entity=None, entity_id=None, detail=None, ip=None):
    execute("INSERT INTO audit_log (user_id, action, entity, entity_id, detail, ip, at)"
            " VALUES (?,?,?,?,?,?,?)",
            (user_id, action, entity, entity_id,
             json.dumps(detail, ensure_ascii=False) if detail is not None else None,
             ip, now()))
