"""
خواندن مدل SAP2000 (فایل متنی .s2k — در SAP: File ← Export ← SAP2000 .s2k Text File).

فایل‌های دفتر با SAP2000 نسخه 14.2.2 و تنظیمات منطقه‌ای فارسی ویندوز ساخته شده‌اند؛
جداکننده اعشار در آن‌ها «/» است (0/45 یعنی 0.45). هر دو شکل خوانده می‌شود.
سطرهای طولانی با « _» در انتهای سطر ادامه پیدا می‌کنند.

واحد فایل‌های دفتر: Kgf, m, C (در جدول PROGRAM CONTROL آمده و کنترل می‌شود).
"""
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

_NUM = re.compile(r"^[-+]?(\d+([./]\d*)?|[./]\d+)([eE][-+]?\d+)?$")
_PAIR = re.compile(r'(\w+)=("([^"]*)"|\S+)')


def _value(raw):
    if _NUM.match(raw):
        return float(raw.replace("/", "."))
    return raw


def read_tables(path):
    """{نام جدول: [سطرها به صورت dict]}"""
    text = Path(path).read_bytes().decode("latin-1").replace("\r", "")
    text = re.sub(r" _\n\s*", " ", text)
    tables, cur = defaultdict(list), None
    for line in text.split("\n"):
        if line.startswith("TABLE:"):
            cur = line.split(":", 1)[1].strip().strip('"')
            continue
        if cur is None or not line.strip() or line.startswith("END TABLE"):
            continue
        rec = {m.group(1): (m.group(3) if m.group(3) is not None else _value(m.group(2)))
               for m in _PAIR.finditer(line)}
        if rec:
            tables[cur].append(rec)
    return tables


@dataclass
class Section:
    name: str
    shape: str            # Angle | Channel | Double Channel | ...
    t3: float             # عمق (m)، در امتداد محور محلی ۲
    t2: float             # پهنا (m)، در امتداد محور محلی ۳
    tf: float
    tw: float
    dis: float = 0.0      # فاصله پشت‌به‌پشت دو ناودانی
    area: float = 0.0     # m²


@dataclass
class Frame:
    name: str
    i: str
    j: str
    section: str


@dataclass
class Structure:
    """سازه نگهدارنده تجهیز، همان‌طور که در SAP مدل شده (واحد: متر، کیلوگرم نیرو)."""
    name: str
    units: str
    joints: dict                       # نام ← (x, y, z)
    frames: list                       # [Frame]
    sections: dict                     # نام ← Section
    supports: list                     # نام گره‌های تکیه‌گاهی
    joint_loads: dict = field(default_factory=dict)   # الگو ← [(گره، F1، F2، F3)]
    combos: dict = field(default_factory=dict)        # ترکیب ← [(ضریب، حالت)]
    steel_code: str = ""

    # ------------------------------------------------ خواص هندسی
    @property
    def height(self):
        return max(z for _, _, z in self.joints.values()) - min(
            self.joints[s][2] for s in self.supports)

    def length(self, f):
        a, b = self.joints[f.i], self.joints[f.j]
        return math.dist(a, b)

    @property
    def member_weight(self):
        """وزن اعضا (kg) = Σ A·L·ρ ؛ بدون ورق اتصال، پیچ و صفحه کف."""
        return sum(self.sections[f.section].area * self.length(f) * 7850 for f in self.frames)

    def legs(self, gap=0.6):
        """
        پایه‌های سازه: تکیه‌گاه‌هایی که از هم کمتر از gap متر فاصله دارند یک پایه‌اند
        (هر پایه مشبک چهار نبشی دارد). خروجی: [(cx, cy, [(x, y)…])] مرتب در امتداد x.
        """
        pts = [self.joints[s][:2] for s in self.supports]
        groups = []
        for p in pts:
            for g in groups:
                if any(math.dist(p, q) < gap for q in g):
                    g.append(p)
                    break
            else:
                groups.append([p])
        out = [(sum(x for x, _ in g) / len(g), sum(y for _, y in g) / len(g), g) for g in groups]
        return sorted(out, key=lambda c: (c[0], c[1]))

    @property
    def leg_spacing(self):
        lg = self.legs()
        return math.dist(lg[0][:2], lg[-1][:2]) / (len(lg) - 1) if len(lg) > 1 else 0.0

    @property
    def leg_size(self):
        """ضلع مربع چهار نبشی یک پایه (فاصله محور نبشی‌ها، m)."""
        _, _, pts = self.legs()[0]
        return max(x for x, _ in pts) - min(x for x, _ in pts)

    def summary(self):
        return {"name": self.name, "height": round(self.height, 3),
                "member_weight": round(self.member_weight, 1), "legs": len(self.legs()),
                "leg_spacing": round(self.leg_spacing, 3), "leg_size": round(self.leg_size, 3),
                "members": len(self.frames),
                "sections": sorted({f.section for f in self.frames}),
                "combos": list(self.combos)}


def read_structure(path):
    t = read_tables(path)
    units, code = "", ""
    for r in t.get("PROGRAM CONTROL", []):
        units = r.get("CurrUnits", units)
        code = r.get("SteelCode", "")
    if units and not units.lower().startswith("kgf, m"):
        raise ValueError(f"واحد مدل SAP باید «Kgf, m, C» باشد، نه «{units}»")
    joints = {str(r["Joint"]): (r["GlobalX"], r["GlobalY"], r["GlobalZ"])
              for r in t["JOINT COORDINATES"]}
    sec_of = {str(r["Frame"]): r["AnalSect"] for r in t["FRAME SECTION ASSIGNMENTS"]}
    frames = [Frame(str(r["Frame"]), str(r["JointI"]), str(r["JointJ"]), sec_of[str(r["Frame"])])
              for r in t["CONNECTIVITY - FRAME"]]
    sections = {}
    for r in t["FRAME SECTION PROPERTIES 01 - GENERAL"]:
        sections[r["SectionName"]] = Section(
            r["SectionName"], r.get("Shape", ""), r.get("t3", 0.0), r.get("t2", 0.0),
            r.get("tf", 0.0), r.get("tw", 0.0), r.get("dis", 0.0) or 0.0, r.get("Area", 0.0))
    supports = [str(r["Joint"]) for r in t["JOINT RESTRAINT ASSIGNMENTS"]
                if r.get("U3") == "Yes"]
    loads = defaultdict(list)
    for r in t.get("JOINT LOADS - FORCE", []):
        loads[r["LoadPat"]].append((str(r["Joint"]), r["F1"], r["F2"], r["F3"]))
    combos = defaultdict(list)
    for r in t.get("COMBINATION DEFINITIONS", []):
        combos[r["ComboName"]].append((r["ScaleFactor"], r["CaseName"]))
    return Structure(Path(path).stem, units, joints, frames, sections, supports,
                     dict(loads), dict(combos), code)
