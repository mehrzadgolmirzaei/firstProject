"""
تنظیمات نقشه که مهندس از داخل سامانه ویرایش می‌کند:
یادداشت‌های نقشه، فیلدهای جدول عنوان، مقیاس و مشخصات آرماتور.

یک ردیف سراسری نگه داشته می‌شود؛ ساختار برای تنظیمات per-project هم آماده است.
"""
import json
from pathlib import Path
from database import query, execute, now

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_NOTES = ROOT / "notes.txt"


def _blank():
    notes = ""
    if DEFAULT_NOTES.exists():
        notes = DEFAULT_NOTES.read_text(encoding="utf-8")
    return {"notes": notes, "title_block": {}, "drawing": {}, "rebar": {}}


def load(project_id=None):
    row = query("SELECT * FROM settings WHERE scope='global' LIMIT 1", one=True)
    if not row:
        return _blank()
    data = json.loads(row["data"])
    if not data.get("notes"):
        data["notes"] = _blank()["notes"]
    return data


def save(data, user_id, project_id=None):
    row = query("SELECT id FROM settings WHERE scope='global' LIMIT 1", one=True)
    blob = json.dumps(data, ensure_ascii=False)
    if row:
        execute("UPDATE settings SET data=?, updated_by=?, updated_at=? WHERE id=?",
                (blob, user_id, now(), row["id"]))
    else:
        execute("INSERT INTO settings (scope, data, updated_by, updated_at)"
                " VALUES ('global',?,?,?)", (blob, user_id, now()))


# بخش‌هایی که روی نتیجه مهندسی اثر دارند در لحظه اجرای محاسبه اعمال و در
# اسنپ‌شات ذخیره می‌شوند؛ بقیه فقط ظاهر نقشه‌اند و هنگام ساخت نقشه اعمال می‌شوند.
ENGINEERING_PARTS = ("rebar",)
PRESENTATION_PARTS = ("title_block", "drawing")


def apply_to(cfg, data, parts=ENGINEERING_PARTS + PRESENTATION_PARTS):
    """اعمال تنظیمات ذخیره‌شده روی ProjectConfig."""
    if "title_block" in parts:
        for key, val in (data.get("title_block") or {}).items():
            if str(val).strip():
                cfg.title_block.fields[key] = val
    for part in ("drawing", "rebar"):
        if part not in parts:
            continue
        target = getattr(cfg, part)
        for key, val in (data.get(part) or {}).items():
            if val in ("", None) or not hasattr(target, key):
                continue
            cur = getattr(target, key)
            setattr(target, key, val if isinstance(cur, str) else type(cur)(float(val)))
    return cfg
