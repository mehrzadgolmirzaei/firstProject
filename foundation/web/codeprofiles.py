"""
پروفایل آیین‌نامه — نسخه‌دار و قابل مقایسه.

چرا این‌طور طراحی شده: خواندن خودکار PDF ویرایش جدید و فهمیدن تغییرات،
قابل اتکا نیست. به جایش ادمین پارامترهای ویرایش را تعریف می‌کند، سیستم آن
را با تاریخ ذخیره می‌کند، و صفحه مقایسه نشان می‌دهد دقیقاً چه عددی و چه
فرمولی نسبت به ویرایش قبل عوض شده. فایل PDF هم به عنوان سند مرجع پیوست
می‌شود. هر محاسبه به یک پروفایل مشخص گره می‌خورد، پس گزارش‌های تأییدشده
با آمدن ویرایش جدید تغییر نمی‌کنند.
"""
import json
from database import query, execute, now

# ---------------------------------------------------------------- پیش‌فرض‌ها
EDITION_5 = {
    "edition": 5,
    "formula_h": "C_h = 0.30·S_DS·Ie   (رابطه ۵-۴، سازه صلب غیرمشابه ساختمان)",
    "formula_h_static": "C_h = S_DS·Ie/Ru   (رابطه ۳-۱، بازه شتاب ثابت)",
    "formula_v": "C_v = 0.20·S_DS   (رابطه ۳-۱۵)",
    "spectral_source": "نقشه‌های پیوست (۱): SS و S1 بر حسب مختصات جغرافیایی",
    "sds_factor": 2 / 3,
    "cmin_factor": 0.044,
    "cmin_floor": 0.01,
    "cv_factor": 0.20,
    "rigid_factor": 0.30,
    "importance": {"گروه ۱": 1.4, "گروه ۲": 1.2, "گروه ۳": 1.0, "گروه ۴": 0.8},
    "fs_table": {
        "I":   {"0.50": 1.0, "0.75": 1.0, "1.00": 1.0, "1.25": 1.0, "1.50": 1.0},
        "II":  {"0.50": 1.2, "0.75": 1.2, "1.00": 1.1, "1.25": 1.0, "1.50": 1.0},
        "III": {"0.50": 1.3, "0.75": 1.2, "1.00": 1.1, "1.25": 1.0, "1.50": 1.0},
        "IV":  {"0.50": 1.6, "0.75": 1.3, "1.00": 1.3, "1.25": 1.1, "1.50": 1.1},
        "V":   {"0.50": 1.6, "0.75": 1.4, "1.00": 1.4, "1.25": 1.2, "1.50": 1.2},
    },
    "f1_table": {
        "I":   {"0.20": 1.0, "0.30": 1.0, "0.40": 1.0, "0.50": 1.0, "0.60": 1.0},
        "II":  {"0.20": 1.5, "0.30": 1.3, "0.40": 1.3, "0.50": 1.3, "0.60": 1.3},
        "III": {"0.20": 2.2, "0.30": 2.1, "0.40": 2.1, "0.50": 2.1, "0.60": 2.1},
        "IV":  {"0.20": 3.3, "0.30": 3.3, "0.40": 3.2, "0.50": 2.8, "0.60": 2.8},
        "V":   {"0.20": 2.2, "0.30": 2.1, "0.40": 2.1, "0.50": 2.1, "0.60": 2.2},
    },
}

EDITION_4 = {
    "edition": 4,
    "formula_h": "C_h = B·A·I/R",
    "formula_v": "C_v = 0.7·A·I",
    "spectral_source": "جدول پهنه‌بندی خطر نسبی شهرها (پیوست ۱ ویرایش ۴)",
    "A_default": 0.30, "B_default": 2.75, "I_default": 1.4, "R_default": 2.0,
    "importance": {"خیلی زیاد": 1.4, "زیاد": 1.2, "متوسط": 1.0, "کم": 0.8},
}


def seed_defaults(user_id=None):
    """اگر هیچ پروفایلی نیست، ویرایش ۴ و ۵ ثبت می‌شوند."""
    if query("SELECT id FROM code_profiles LIMIT 1", one=True):
        return
    for name, edition, issued, definition in (
        ("استاندارد ۲۸۰۰ — ویرایش ۴", 4, "1393", EDITION_4),
        ("استاندارد ۲۸۰۰ — ویرایش ۵", 5, "1405/01", EDITION_5),
    ):
        execute("INSERT INTO code_profiles (name, edition, issued_on, definition,"
                " is_active, created_by, created_at) VALUES (?,?,?,?,?,?,?)",
                (name, edition, issued, json.dumps(definition, ensure_ascii=False),
                 1, user_id, now()))


def get(profile_id):
    row = query("SELECT * FROM code_profiles WHERE id=?", (profile_id,), one=True)
    if not row:
        return None
    data = dict(row)
    data["definition"] = json.loads(data["definition"])
    return data


def listing(active_only=True):
    sql = "SELECT * FROM code_profiles"
    if active_only:
        sql += " WHERE is_active=1"
    return [dict(r) for r in query(sql + " ORDER BY edition DESC, id DESC")]


# ---------------------------------------------------------------- مقایسه
def _flatten(obj, prefix=""):
    out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(_flatten(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.update(_flatten(v, f"{prefix}[{i}]"))
    else:
        out[prefix] = obj
    return out


def diff(profile_a, profile_b):
    """
    تفاوت دو ویرایش، پارامتر به پارامتر.
    خروجی: فهرست (کلید، مقدار قدیم، مقدار جدید، وضعیت)
    """
    a = _flatten(get(profile_a)["definition"])
    b = _flatten(get(profile_b)["definition"])
    keys = sorted(set(a) | set(b))
    rows = []
    for k in keys:
        old, new = a.get(k), b.get(k)
        if old == new:
            continue
        state = "افزوده" if k not in a else ("حذف" if k not in b else "تغییر")
        rows.append({"key": k, "old": old, "new": new, "state": state})
    return rows
