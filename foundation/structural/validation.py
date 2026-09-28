"""
صحت‌سنجی زنده حل‌کننده سازه — همان آزمون‌هایی که جای SAP2000 را توجیه می‌کند.

۱. پاسخ بسته کتاب‌های درسی (کنسول، تیر دوسرگیردار، پیچش، محوری) با تغییرشکل برشی.
۲. خواص مقاطع در برابر جدول «FRAME SECTION PROPERTIES» خود SAP در مدل‌های نمونه دفتر.
۳. تعادل کامل نیرو و لنگر همان مدل‌های نمونه SAP، حل‌شده با حل‌کننده برنامه.

هر ردیف: عنوان، مقدار مرجع، مقدار برنامه، خطای نسبی و وضعیت.
"""
import math
from pathlib import Path

import numpy as np

from .frame import Member, Model, Pattern, analyse
from .s2k import read_model, read_tables
from .sections import STEEL, angle, channel, from_sap

SAP_DIR = Path(__file__).resolve().parents[1] / "tests" / "data" / "sap"
FIX = (True,) * 6
TOL = 1e-6


def _row(title, formula, ref, got, unit=""):
    err = abs(got - ref) / max(abs(ref), 1e-30)
    return {"title": title, "formula": formula, "ref": ref, "got": got, "unit": unit,
            "error": err, "ok": err <= TOL}


def _cantilever(sec, L, load, along="X"):
    tip = {"X": (L, 0, 0), "Z": (0, 0, L)}[along]
    m = Model(nodes={"a": (0, 0, 0), "b": tip}, members=[Member("m", "a", "b", sec)],
              supports={"a": FIX}, patterns={"P": Pattern(joint=[("b", load)])})
    return analyse(m)


def closed_form():
    E, G = STEEL["E"], STEEL["G"]
    ch, an = channel(0.14, 0.06, 0.007, 0.01), angle(0.06, 0.006)
    rows = []

    P, L = 100.0, 2.0
    r = _cantilever(ch, L, (0, 0, -P, 0, 0, 0))
    rows.append(_row("کنسول، بار متمرکز نوک — تغییرمکان (خمش + برش)",
                     "PL³/3EI + PL/GAₛ", (P * L ** 3 / (3 * E * ch.I33) + P * L / (G * ch.AS2)) * 1000,
                     -r.displacement("P", "b")[2] * 1000, "mm"))
    rows.append(_row("کنسول، بار متمرکز نوک — لنگر تکیه‌گاه", "PL", P * L,
                     abs(r.forces["P"]["m"][0][6]), "kgf·m"))

    P, L = 50.0, 3.0
    r = _cantilever(ch, L, (0, P, 0, 0, 0, 0), along="Z")
    rows.append(_row("ستون کنسول، بار جانبی در محور ضعیف", "PL³/3EI₂₂ + PL/GAₛ₃",
                     (P * L ** 3 / (3 * E * ch.I22) + P * L / (G * ch.AS3)) * 1000,
                     r.displacement("P", "b")[1] * 1000, "mm"))

    T, L = 5.0, 1.5
    r = _cantilever(an, L, (0, 0, 0, T, 0, 0))
    rows.append(_row("پیچش نبشی", "TL/GJ", T * L / (G * an.J), r.displacement("P", "b")[3], "rad"))

    r = _cantilever(an, 2.0, (1000, 0, 0, 0, 0, 0))
    rows.append(_row("کشش محوری", "PL/EA", 1000 * 2 / (E * an.A) * 1000,
                     r.displacement("P", "b")[0] * 1000, "mm"))

    sec, L, w = channel(0.16, 0.065, 0.0075, 0.0105), 4.0, 300.0
    m = Model(nodes={"a": (0, 0, 0), "b": (L, 0, 0)}, members=[Member("m", "a", "b", sec)],
              supports={"a": FIX, "b": FIX},
              patterns={"W": Pattern(partial=[("m", "Z", 0.0, 0.5, -w, -w)])}, G=1e25)
    r = analyse(m)
    rows.append(_row("تیر دوسرگیردار، بار یکنواخت روی نیمه چپ — لنگر گیرداری", "11wL²/192",
                     11 * w * L * L / 192, abs(r.forces["W"]["m"][0][6]), "kgf·m"))

    L, q = 2.0, 200.0
    m = Model(nodes={"a": (0, 0, 0), "b": (L, 0, 0)}, members=[Member("m", "a", "b", ch)],
              supports={"a": FIX}, patterns={"T": Pattern(partial=[("m", "Z", 0, 1, 0, -q)])})
    r = analyse(m)
    rows.append(_row("کنسول، بار مثلثی — تغییرمکان نوک", "11qL⁴/120EI + qL²/3GAₛ",
                     (11 * q * L ** 4 / (120 * E * ch.I33) + q * L * L / (3 * G * ch.AS2)) * 1000,
                     -r.displacement("T", "b")[2] * 1000, "mm"))
    return rows


def sap_sections(folder=SAP_DIR):
    """بیشینه خطای نسبی خواص هر مقطع نسبت به جدول خود SAP."""
    rows = []
    for path in sorted(Path(folder).glob("*.s2k")):
        worst, n = 0.0, 0
        for r in read_tables(path)["FRAME SECTION PROPERTIES 01 - GENERAL"]:
            if r["Shape"] not in ("Angle", "Channel", "Double Channel"):
                continue
            s = from_sap(r)
            n += 1
            for key, attr in (("Area", "A"), ("TorsConst", "J"), ("I33", "I33"), ("I22", "I22"),
                              ("AS2", "AS2"), ("AS3", "AS3"), ("S33", "S33"), ("S22", "S22"),
                              ("R33", "r33"), ("R22", "r22")):
                worst = max(worst, abs(getattr(s, attr) - r[key]) / max(abs(r[key]), 1e-30))
        rows.append({"model": path.stem, "sections": n, "error": worst, "ok": worst <= TOL})
    return rows


def applied_loads(m, pat):
    """برآیند نیرو و لنگر بارهای یک حالت بار حول مبدأ (وزن، گرهی، گسترده، ضریب ثقلی)."""
    P = lambda n: np.array(m.nodes[n])
    F, M = np.zeros(3), np.zeros(3)

    def add(f, at):
        nonlocal F, M
        F = F + f
        M = M + np.cross(at, f)
    for mem in m.members:
        L = math.dist(m.nodes[mem.i], m.nodes[mem.j])
        add(np.array([0, 0, -pat.self_weight * mem.section.A * m.gamma * L]),
            (P(mem.i) + P(mem.j)) / 2)
    for n, f in pat.joint:
        add(np.array(f[:3]), P(n))
        M = M + np.array(f[3:])
    for mn, d, ra, rb, wa, wb in pat.partial + [(a, b, 0, 1, c, c) for a, b, c in pat.uniform]:
        mem = m.member(mn)
        L = math.dist(m.nodes[mem.i], m.nodes[mem.j])
        tot = (wa + wb) / 2 * L * (rb - ra)
        xc = ra + (rb - ra) * ((wa + 2 * wb) / (3 * (wa + wb)) if wa + wb else 0.5)
        v = np.zeros(3)
        v["XYZ".index(d)] = tot
        add(v, P(mem.i) + (P(mem.j) - P(mem.i)) * xc)
    for mn, mult in pat.gravity:
        mem = m.member(mn)
        L = math.dist(m.nodes[mem.i], m.nodes[mem.j])
        add(np.array(mult) * mem.section.A * m.gamma * L, (P(mem.i) + P(mem.j)) / 2)
    return F, M


def sap_equilibrium(folder=SAP_DIR):
    """هر مدل نمونه SAP با حل‌کننده برنامه: باقیمانده نیرو (kgf) و لنگر (kgf·m) در همه حالت‌ها."""
    rows = []
    for path in sorted(Path(folder).glob("*.s2k")):
        m = read_model(path)
        r = analyse(m)
        rf = rm = load = 0.0
        for case, pat in m.patterns.items():
            F, M = applied_loads(m, pat)
            RF = sum(np.array(v[:3]) for v in r.reactions[case].values())
            RM = sum(np.cross(m.nodes[n], v[:3]) + np.array(v[3:])
                     for n, v in r.reactions[case].items())
            rf = max(rf, float(np.abs(RF + F).max()))
            rm = max(rm, float(np.abs(RM + M).max()))
            load = max(load, float(np.abs(F).max()))
        rows.append({"model": path.stem, "joints": len(m.nodes), "members": len(m.members),
                     "cases": len(m.patterns), "combos": len(m.combos), "load": load,
                     "force": rf, "moment": rm, "ok": rf <= TOL and rm <= TOL})
    return rows


_CACHE = {}


def run():
    """همه آزمون‌ها؛ یک بار در هر اجرای برنامه حساب می‌شود."""
    if not _CACHE:
        _CACHE["closed"] = closed_form()
        have = SAP_DIR.is_dir() and any(SAP_DIR.glob("*.s2k"))
        _CACHE["sections"] = sap_sections() if have else []
        _CACHE["equilibrium"] = sap_equilibrium() if have else []
        _CACHE["ok"] = all(r["ok"] for k in ("closed", "sections", "equilibrium")
                           for r in _CACHE[k])
    return _CACHE
