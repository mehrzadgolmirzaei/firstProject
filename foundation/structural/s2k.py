"""
فایل متنی SAP2000 (.s2k) — خواندن مدل برای اعتبارسنجی، و نوشتن مدل برای تحویل
به مشاوری که فایل SAP بخواهد. برنامه برای تحلیل و طراحی به SAP نیاز ندارد.

فایل‌های دفتر با ویندوز فارسی ساخته شده‌اند و جداکننده اعشار «/» است (0/45 = 0.45)؛
سطرهای طولانی با « _» ادامه دارند. واحد باید «Kgf, m, C» باشد.
"""
import re
from collections import defaultdict
from pathlib import Path

from .frame import Member, Model, Pattern, RELEASE_KEYS
from .sections import from_sap

_NUM = re.compile(r"^[-+]?(\d+([./]\d*)?|[./]\d+)([eE][-+]?\d+)?$")
_PAIR = re.compile(r'(\w+)=("([^"]*)"|\S+)')


def value(raw):
    return float(raw.replace("/", ".")) if _NUM.match(raw) else raw


def read_tables(path):
    text = Path(path).read_bytes().decode("latin-1").replace("\r", "")
    text = re.sub(r" _\n\s*", " ", text)
    tables, cur = defaultdict(list), None
    for line in text.split("\n"):
        if line.startswith("TABLE:"):
            cur = line.split(":", 1)[1].strip().strip('"')
            continue
        if cur is None or not line.strip() or line.startswith("END TABLE"):
            continue
        rec = {m.group(1): (m.group(3) if m.group(3) is not None else value(m.group(2)))
               for m in _PAIR.finditer(line)}
        if rec:
            tables[cur].append(rec)
    return tables


def _name(v):
    return str(int(v)) if isinstance(v, float) and v.is_integer() else str(v)


def read_model(path):
    """مدل SAP ← structural.frame.Model (همراه با ضریب طول مؤثر طراحی هر عضو)."""
    t = read_tables(path)
    for r in t.get("PROGRAM CONTROL", []):
        units = r.get("CurrUnits", "")
        if units and not units.lower().startswith("kgf, m"):
            raise ValueError(f"واحد مدل باید «Kgf, m, C» باشد، نه «{units}»")
    nodes = {_name(r["Joint"]): (r["GlobalX"], r["GlobalY"], r["GlobalZ"])
             for r in t["JOINT COORDINATES"]}
    sections = {r["SectionName"]: r for r in t["FRAME SECTION PROPERTIES 01 - GENERAL"]}
    sec_of = {_name(r["Frame"]): r["AnalSect"] for r in t["FRAME SECTION ASSIGNMENTS"]}
    rel = {_name(r["Frame"]): tuple(r.get(k) == "Yes" for k in RELEASE_KEYS)
           for r in t.get("FRAME RELEASE ASSIGNMENTS 1 - GENERAL", [])}
    ang = {_name(r["Frame"]): r.get("Angle", 0.0)
           for r in t.get("FRAME LOCAL AXES ASSIGNMENTS 1 - TYPICAL", [])}
    kfac = {}
    for r in t.get("OVERWRITES - STEEL DESIGN - AISC-ASD89", []):
        kfac[_name(r["Frame"])] = (r.get("XKMajor") or 1.0, r.get("XKMinor") or 1.0)
    cache = {}
    members = []
    for r in t["CONNECTIVITY - FRAME"]:
        f = _name(r["Frame"])
        sn = sec_of[f]
        if sn not in cache:
            cache[sn] = from_sap(sections[sn])
        km, kn = kfac.get(f, (1.0, 1.0))
        members.append(Member(f, _name(r["JointI"]), _name(r["JointJ"]), cache[sn],
                              rel.get(f, (False,) * 12), ang.get(f, 0.0), k_major=km,
                              k_minor=kn))
    supports = {_name(r["Joint"]): tuple(r[k] == "Yes" for k in ("U1", "U2", "U3", "R1", "R2", "R3"))
                for r in t["JOINT RESTRAINT ASSIGNMENTS"]}

    pats = {r["LoadPat"]: Pattern(self_weight=r.get("SelfWtMult", 0.0) or 0.0)
            for r in t["LOAD PATTERN DEFINITIONS"]}
    for r in t.get("JOINT LOADS - FORCE", []):
        if r.get("CoordSys", "GLOBAL") != "GLOBAL":
            raise ValueError("بار گرهی فقط در مختصات سراسری پشتیبانی می‌شود")
        pats[r["LoadPat"]].joint.append(
            (_name(r["Joint"]), tuple(r.get(k, 0.0) for k in ("F1", "F2", "F3", "M1", "M2", "M3"))))
    for r in t.get("FRAME LOADS - DISTRIBUTED", []):
        if r.get("Type") != "Force":
            raise ValueError(f"بار گسترده عضو {_name(r['Frame'])}: فقط نوع Force پشتیبانی می‌شود")
        d, wa, wb = r["Dir"], r["FOverLA"], r["FOverLB"]
        if r.get("CoordSys", "GLOBAL") == "Local":
            d = str(int(d)) if isinstance(d, float) else str(d)
        elif d == "Gravity":
            d, wa, wb = "Z", -wa, -wb
        elif d not in ("X", "Y", "Z"):
            raise ValueError(f"جهت بار {d} پشتیبانی نمی‌شود (عضو {_name(r['Frame'])})")
        pats[r["LoadPat"]].partial.append((_name(r["Frame"]), d, r.get("RelDistA", 0.0),
                                           r.get("RelDistB", 1.0), wa, wb))
    for r in t.get("FRAME LOADS - GRAVITY", []):
        pats[r["LoadPat"]].gravity.append(
            (_name(r["Frame"]), (r.get("MultiplierX", 0.0), r.get("MultiplierY", 0.0),
                                 r.get("MultiplierZ", 0.0))))

    # حالت‌های بار استاتیکی ← ترکیب الگوها؛ ترکیب‌های تعریف‌شده روی حالت‌ها
    combos = {}
    cases = defaultdict(list)
    for r in t.get("CASE - STATIC 1 - LOAD ASSIGNMENTS", []):
        cases[r["Case"]].append((r.get("LoadSF", 1.0), r["LoadName"]))
    for case, parts in cases.items():
        if parts == [(1.0, case)]:
            continue
        if case in pats:                          # نام حالت با نام الگو یکی ولی محتوا فرق دارد
            pats["P:" + case] = pats.pop(case)
            parts = [(f, "P:" + p if p == case else p) for f, p in parts]
        combos[case] = parts
    for r in t.get("COMBINATION DEFINITIONS", []):
        combos.setdefault(r["ComboName"], []).append((r["ScaleFactor"], r["CaseName"]))
    model = Model(nodes, members, supports, pats, combos)
    model.name = Path(path).stem
    return model
