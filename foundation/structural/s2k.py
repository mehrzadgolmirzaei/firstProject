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
    kfac = {}        # صفر در SAP یعنی «تعیین توسط برنامه» = ۱ برای قاب مهاربندی‌شده
    for r in t.get("OVERWRITES - STEEL DESIGN - AISC-ASD89", []):
        kfac[_name(r["Frame"])] = tuple(r.get(k) or 1.0 for k in
                                        ("XKMajor", "XKMinor", "XLMajor", "XLMinor"))
    fy = {r["Material"]: r["Fy"] for r in t.get("MATERIAL PROPERTIES 03A - STEEL DATA", [])}
    cache = {}
    members = []
    for r in t["CONNECTIVITY - FRAME"]:
        f = _name(r["Frame"])
        sn = sec_of[f]
        if sn not in cache:
            cache[sn] = from_sap(sections[sn])
            cache[sn].fy = fy.get(sections[sn].get("Material"))
        km, kn, lm, ln = kfac.get(f, (1.0, 1.0, 1.0, 1.0))
        members.append(Member(f, _name(r["JointI"]), _name(r["JointJ"]), cache[sn],
                              rel.get(f, (False,) * 12), ang.get(f, 0.0), k_major=km,
                              k_minor=kn, l_major=lm, l_minor=ln))
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
    model.design_combos = [c for c in dict.fromkeys(
        r["ComboName"] for r in t.get("COMBINATION DEFINITIONS", [])
        if r.get("SteelDesign") == "Strength")]
    return model


# ------------------------------------------------------------------ نوشتن
def _fmt(v, sep):
    if isinstance(v, bool):
        return "Yes" if v else "No"
    if isinstance(v, (int, float)):
        s = repr(float(v)) if abs(v) >= 1e-4 or v == 0 else f"{v:.10E}"
        if s.endswith(".0"):
            s = s[:-2]
        return s.replace(".", sep)
    v = str(v)
    return f'"{v}"' if (" " in v or not v) else v


def _row(sep, **kw):
    return "   " + "   ".join(f"{k}={_fmt(v, sep)}" for k, v in kw.items())


def write_model(model, path, title="", decimal="/"):
    """
    مدل برنامه ← فایل متنی SAP2000 (Kgf, m, C) برای مشاوری که فایل SAP بخواهد.
    decimal: جداکننده اعشار؛ «/» همان تنظیم ویندوز فارسی سیستم‌های دفتر است (فایل‌های نمونه).
    """
    import datetime
    sep = decimal
    L = []

    def t(name):
        # مثل فایل‌های خود SAP: هر جدول با سطر «سه فاصله» بسته و جدول بعد بی‌فاصله شروع می‌شود
        if L and L[-1].startswith("TABLE:") is False and len(L) > 2:
            L.append("   ")
        L.append(f'TABLE:  "{name}"')
    now = datetime.datetime.now()
    L.append(f"File {Path(path).name} was saved on {now.month}/{now.day}/{now:%y} at {now:%H:%M:%S}")
    L.append("")
    t("PROGRAM CONTROL")
    L.append("   ProgramName=SAP2000   Version=14.2.2   ProgLevel=Advanced   CurrUnits=\"Kgf, m, C\"   "
             "SteelCode=AISC-ASD89   ConcCode=\"ACI 318-05/IBC2003\"   RegenHinge=Yes")
    t("MATERIAL PROPERTIES 01 - GENERAL")
    L.append(_row(sep, Material="STEEL", Type="Steel", SymType="Isotropic", TempDepend=False,
                  Color="Yellow"))
    t("MATERIAL PROPERTIES 02 - BASIC MECHANICAL PROPERTIES")
    L.append(_row(sep, Material="STEEL", UnitWeight=model.gamma, UnitMass=model.gamma / 9.80665,
                  E1=model.E, G12=model.G, U12=model.E / (2 * model.G) - 1, A1=1.17e-5))
    fy = next((getattr(m.section, "fy", None) for m in model.members if getattr(m.section, "fy", None)),
              None) or 2.35e7
    t("MATERIAL PROPERTIES 03A - STEEL DATA")
    L.append(_row(sep, Material="STEEL", Fy=fy, Fu=fy * 1.6, EffFy=fy * 1.1, EffFu=fy * 1.76,
                  SSCurveOpt="Simple", SSHysType="Kinematic", SHard=0.02, SMax=0.14, SRup=0.2,
                  FinalSlope=-0.1))
    t("FRAME SECTION PROPERTIES 01 - GENERAL")
    shapes = {"angle": "Angle", "channel": "Channel", "2channel": "Double Channel"}
    seen = {}
    for m in model.members:
        s = m.section
        if s.name in seen:
            continue
        seen[s.name] = s
        extra = {"dis": s.dis} if s.shape == "2channel" else {}
        t2 = 2 * s.t2 + s.dis if s.shape == "2channel" else s.t2
        L.append(_row(sep, SectionName=s.name, Material="STEEL", Shape=shapes[s.shape], t3=s.t3,
                      t2=t2, tf=s.tf, tw=s.tw, **extra, Area=s.A, TorsConst=s.J, I33=s.I33,
                      I22=s.I22, AS2=s.AS2, AS3=s.AS3, S33=s.S33, S22=s.S22))
    t("LOAD PATTERN DEFINITIONS")
    for name, p in model.patterns.items():
        L.append(_row(sep, LoadPat=name, DesignType="DEAD" if p.self_weight else "OTHER",
                      SelfWtMult=p.self_weight))
    t("LOAD CASE DEFINITIONS")
    for name in model.patterns:
        L.append(_row(sep, Case=name, Type="LinStatic", InitialCond="Zero", RunCase=True))
    t("CASE - STATIC 1 - LOAD ASSIGNMENTS")
    for name in model.patterns:
        L.append(_row(sep, Case=name, LoadType="Load pattern", LoadName=name, LoadSF=1))
    t("COMBINATION DEFINITIONS")
    design = set(getattr(model, "design_combos", None) or model.combos)
    for name, parts in model.combos.items():
        for k, (f, case) in enumerate(parts):
            kw = {"ComboName": name}
            if k == 0:
                kw.update(ComboType="Linear Add", AutoDesign=False)
            kw.update(CaseType="Linear Static", CaseName=case, ScaleFactor=f)
            if k == 0:
                kw.update(SteelDesign="Strength" if name in design else "None")
            L.append(_row(sep, **kw))
    t("JOINT COORDINATES")
    names = {n: str(k + 1) for k, n in enumerate(model.nodes)}
    for n, (x, y, z) in model.nodes.items():
        L.append(_row(sep, Joint=names[n], CoordSys="GLOBAL", CoordType="Cartesian", XorR=x,
                      Y=y, Z=z, SpecialJt=False, GlobalX=x, GlobalY=y, GlobalZ=z))
    t("CONNECTIVITY - FRAME")
    fnames = {m.name: str(k + 1) for k, m in enumerate(model.members)}
    for m in model.members:
        L.append(_row(sep, Frame=fnames[m.name], JointI=names[m.i], JointJ=names[m.j],
                      IsCurved=False))
    t("JOINT RESTRAINT ASSIGNMENTS")
    for n, flags in model.supports.items():
        L.append(_row(sep, Joint=names[n], **dict(zip(("U1", "U2", "U3", "R1", "R2", "R3"), flags))))
    t("JOINT LOADS - FORCE")
    for pn, p in model.patterns.items():
        for n, f in p.joint:
            L.append(_row(sep, Joint=names[n], LoadPat=pn, CoordSys="GLOBAL",
                          **dict(zip(("F1", "F2", "F3", "M1", "M2", "M3"), f))))
    t("FRAME SECTION ASSIGNMENTS")
    for m in model.members:
        L.append(_row(sep, Frame=fnames[m.name], SectionType=shapes[m.section.shape],
                      AutoSelect="N.A.", AnalSect=m.section.name, DesignSect=m.section.name,
                      MatProp="Default"))
    t("FRAME RELEASE ASSIGNMENTS 1 - GENERAL")
    for m in model.members:
        if any(m.releases):
            L.append(_row(sep, Frame=fnames[m.name], **dict(zip(RELEASE_KEYS, m.releases)),
                          PartialFix=False))
    t("FRAME LOADS - GRAVITY")
    for pn, p in model.patterns.items():
        for mn, (mx, my, mz) in p.gravity:
            L.append(_row(sep, Frame=fnames[mn], LoadPat=pn, CoordSys="GLOBAL", MultiplierX=mx,
                          MultiplierY=my, MultiplierZ=mz))
    t("FRAME LOADS - DISTRIBUTED")
    for pn, p in model.patterns.items():
        for mn, d, ra, rb, wa, wb in [(a, b, 0.0, 1.0, c, c) for a, b, c in p.uniform] + p.partial:
            local = d in ("1", "2", "3")
            L.append(_row(sep, Frame=fnames[mn], LoadPat=pn, CoordSys="Local" if local else "GLOBAL",
                          Type="Force", Dir=d, DistType="RelDist", RelDistA=ra, RelDistB=rb,
                          FOverLA=wa, FOverLB=wb))
    t("OVERWRITES - STEEL DESIGN - AISC-ASD89")
    for m in model.members:
        L.append(_row(sep, Frame=fnames[m.name], XLMajor=m.l_major, XLMinor=m.l_minor,
                      XKMajor=m.k_major, XKMinor=m.k_minor))
    t("PREFERENCES - STEEL DESIGN - AISC-ASD89")
    L.append(_row(sep, THDesign="Envelopes", FrameType="Braced Frame", SRatioLimit=1))
    if title:
        t("PROJECT INFORMATION")
        L.append(_row(sep, Item="Project Name", Data=title))
    L.append("   ")
    L.append("END TABLE DATA")
    Path(path).write_bytes(("\r\n".join(L) + "\r\n").encode("latin-1", "replace"))
    return path
