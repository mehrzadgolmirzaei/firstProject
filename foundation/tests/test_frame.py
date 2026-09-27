"""
حل‌کننده قاب در برابر پاسخ‌های بسته کتاب‌های درسی — اگر این‌ها درست باشد، هر مدل
خطی دیگری هم درست حل می‌شود (همان ریاضیاتی که SAP به کار می‌برد).
"""
import math

import numpy as np
import pytest

from structural.frame import Member, Model, Pattern, analyse
from structural.sections import STEEL, angle, channel

E, G = STEEL["E"], STEEL["G"]
FIX = (True,) * 6
PIN_BOTH = (False, False, False, True, True, True, False, False, False, False, True, True)


def cantilever(sec, L=2.0, load=(0, 0, -100, 0, 0, 0), along="X"):
    tip = {"X": (L, 0, 0), "Z": (0, 0, L)}[along]
    m = Model(nodes={"a": (0, 0, 0), "b": tip},
              members=[Member("m", "a", "b", sec)], supports={"a": FIX},
              patterns={"P": Pattern(joint=[("b", load)])})
    return m, analyse(m)


def test_cantilever_tip_load_bending_and_shear():
    sec = channel(0.14, 0.06, 0.007, 0.01)
    P, L = 100.0, 2.0
    m, r = cantilever(sec, L)
    # افقی در امتداد X: محور ۲ رو به بالا → خمش حول ۳ با I33 و برش با AS2
    exact = P * L ** 3 / (3 * E * sec.I33) + P * L / (G * sec.AS2)
    assert -r.displacement("P", "b")[2] == pytest.approx(exact, rel=1e-9)
    Fz, My = r.reactions["P"]["a"][2], r.reactions["P"]["a"][4]
    assert Fz == pytest.approx(P) and My == pytest.approx(-P * L)      # لنگر گیرداری
    rows = r.forces["P"]["m"]
    assert abs(rows[0][6]) == pytest.approx(P * L) and abs(rows[-1][6]) < 1e-6


def test_vertical_cantilever_uses_local2_equal_X():
    sec = channel(0.14, 0.06, 0.007, 0.01)
    P, L = 50.0, 3.0
    m, r = cantilever(sec, L, load=(P, 0, 0, 0, 0, 0), along="Z")
    exact = P * L ** 3 / (3 * E * sec.I33) + P * L / (G * sec.AS2)
    assert r.displacement("P", "b")[0] == pytest.approx(exact, rel=1e-9)
    m, r = cantilever(sec, L, load=(0, P, 0, 0, 0, 0), along="Z")
    exact = P * L ** 3 / (3 * E * sec.I22) + P * L / (G * sec.AS3)
    assert r.displacement("P", "b")[1] == pytest.approx(exact, rel=1e-9)


def test_torsion():
    sec = angle(0.06, 0.006)
    Tq, L = 5.0, 1.5
    m, r = cantilever(sec, L, load=(0, 0, 0, Tq, 0, 0))
    assert r.displacement("P", "b")[3] == pytest.approx(Tq * L / (G * sec.J), rel=1e-9)


def test_axial():
    sec = angle(0.06, 0.006)
    m, r = cantilever(sec, 2.0, load=(1000, 0, 0, 0, 0, 0))
    assert r.displacement("P", "b")[0] == pytest.approx(1000 * 2 / (E * sec.A), rel=1e-9)
    assert r.forces["P"]["m"][1][1] == pytest.approx(1000)            # کشش مثبت


def fixed_beam(sec, L, w, releases=(False,) * 12, mid_node=False):
    nodes = {"a": (0, 0, 0), "b": (L, 0, 0)}
    if mid_node:
        nodes["c"] = (L / 2, 0, 0)
    m = Model(nodes=nodes, members=[Member("m", "a", "b", sec, releases)],
              supports={"a": FIX, "b": FIX},
              patterns={"W": Pattern(uniform=[("m", "Z", -w)])})
    return analyse(m, stations=5)


def test_fixed_fixed_udl():
    sec = channel(0.16, 0.065, 0.0075, 0.0105)
    L, w = 3.0, 400.0
    r = fixed_beam(sec, L, w, mid_node=True)       # گره میانی: عضو خودکار دو قطعه می‌شود
    M = {round(row[0], 6): row[6] for row in r.forces["W"]["m"]}
    assert abs(M[0.0]) == pytest.approx(w * L * L / 12, rel=1e-9)
    assert abs(M[1.5]) == pytest.approx(w * L * L / 24, rel=1e-9)
    mid = w * L ** 4 / (384 * E * sec.I33) + w * L * L / (8 * G * sec.AS2)
    assert -r.displacement("W", "c")[2] == pytest.approx(mid, rel=1e-9)


def test_released_ends_make_simple_beam():
    sec = channel(0.16, 0.065, 0.0075, 0.0105)
    L, w = 3.0, 400.0
    r = fixed_beam(sec, L, w, releases=PIN_BOTH)
    rows = r.forces["W"]["m"]
    assert abs(rows[0][6]) < 1e-6 and abs(rows[-1][6]) < 1e-6
    assert abs(rows[2][6]) == pytest.approx(w * L * L / 8, rel=1e-9)
    assert abs(rows[0][2]) == pytest.approx(w * L / 2, rel=1e-9)


def test_space_frame_equilibrium_and_combos():
    """قاب فضایی دلخواه: جمع عکس‌العمل‌ها = منهای جمع بارها؛ ترکیب = جمع خطی."""
    L40, L60, U = angle(0.04, 0.004), angle(0.06, 0.006), channel(0.14, 0.06, 0.007, 0.01)
    nodes = {f"b{i}": (x, y, 0) for i, (x, y) in enumerate([(0, 0), (0.4, 0), (0.4, 0.4), (0, 0.4)])}
    nodes.update({f"t{i}": (x, y, 1.2) for i, (x, y) in enumerate([(0, 0), (0.4, 0), (0.4, 0.4), (0, 0.4)])})
    nodes["tip"] = (1.0, 0.2, 1.4)
    members = [Member(f"c{i}", f"b{i}", f"t{i}", L60) for i in range(4)]
    members += [Member(f"d{i}", f"b{i}", f"t{(i + 1) % 4}", L40, PIN_BOTH) for i in range(4)]
    members += [Member(f"h{i}", f"t{i}", f"t{(i + 1) % 4}", L40) for i in range(4)]
    members += [Member("arm", "t2", "tip", U), Member("arm2", "t1", "tip", U)]
    pats = {"D": Pattern(self_weight=1.0, joint=[("tip", (0, 0, -300, 0, 0, 0))]),
            "W": Pattern(uniform=[("arm", "Y", 40.0), ("c0", "X", 25.0)],
                         joint=[("tip", (120, 80, 0, 0, 0, 15))]),
            "E": Pattern(gravity=[(m.name, (0, 0.6, 0.3)) for m in members])}
    model = Model(nodes, members, {f"b{i}": FIX for i in range(4)}, pats,
                  {"C1": [(1.0, "D"), (1.0, "W")], "C2": [(1.0, "C1"), (-0.6, "E")]})
    r = analyse(model)
    for case in ("D", "W", "E"):
        pat = pats[case]
        total = np.zeros(3)
        wt = sum(m.section.A * STEEL["gamma"] * math.dist(nodes[m.i], nodes[m.j]) for m in members)
        total[2] -= pat.self_weight * wt
        for n, f in pat.joint:
            total += f[:3]
        for mn, d, w in pat.uniform:
            m = model.member(mn)
            total["XYZ".index(d)] += w * math.dist(nodes[m.i], nodes[m.j])
        for mn, mult in pat.gravity:
            m = model.member(mn)
            total += np.array(mult) * m.section.A * STEEL["gamma"] * math.dist(nodes[m.i], nodes[m.j])
        R = sum(np.array(v[:3]) for v in r.reactions[case].values())
        assert R == pytest.approx(-total, abs=1e-6)
    c1 = np.array(r.reactions["C1"]["b0"])
    assert c1 == pytest.approx(np.array(r.reactions["D"]["b0"]) + r.reactions["W"]["b0"])
    c2 = np.array(r.reactions["C2"]["b2"])
    assert c2 == pytest.approx(np.array(r.reactions["C1"]["b2"]) - 0.6 * np.array(r.reactions["E"]["b2"]))


def test_partial_load_fixed_fixed_euler():
    """بار یکنواخت روی نیمه چپ تیر دوسرگیردار: M_A = 11wL²/192 ، M_B = 5wL²/192."""
    sec = channel(0.16, 0.065, 0.0075, 0.0105)
    L, w = 4.0, 300.0
    m = Model(nodes={"a": (0, 0, 0), "b": (L, 0, 0)}, members=[Member("m", "a", "b", sec)],
              supports={"a": FIX, "b": FIX},
              patterns={"W": Pattern(partial=[("m", "Z", 0.0, 0.5, -w, -w)])}, G=1e25)
    r = analyse(m)
    rows = r.forces["W"]["m"]
    assert abs(rows[0][6]) == pytest.approx(11 * w * L * L / 192, rel=1e-9)
    assert abs(rows[-1][6]) == pytest.approx(5 * w * L * L / 192, rel=1e-9)
    assert r.reactions["W"]["a"][2] == pytest.approx(13 * w * L / 32, rel=1e-9)


def test_triangular_load_cantilever_with_shear():
    """کنسول زیر بار مثلثی (صفر در تکیه‌گاه تا q در نوک): δ = 11qL⁴/120EI + qL²/(3GAs)."""
    sec = channel(0.14, 0.06, 0.007, 0.01)
    L, q = 2.0, 200.0
    m = Model(nodes={"a": (0, 0, 0), "b": (L, 0, 0)}, members=[Member("m", "a", "b", sec)],
              supports={"a": FIX}, patterns={"T": Pattern(partial=[("m", "Z", 0, 1, 0, -q)])})
    r = analyse(m)
    exact = 11 * q * L ** 4 / (120 * E * sec.I33) + q * L * L / (3 * G * sec.AS2)
    assert -r.displacement("T", "b")[2] == pytest.approx(exact, rel=1e-9)
    assert abs(r.forces["T"]["m"][0][6]) == pytest.approx(q * L * L / 3, rel=1e-9)
