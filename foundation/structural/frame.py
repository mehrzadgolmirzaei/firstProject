"""
حل‌کننده قاب فضایی — روش سختی مستقیم، تحلیل استاتیکی خطی (همان تحلیل Linear
Static در SAP2000).

    عضو: تیر تیموشنکو ۱۲ درجه آزادی (تغییرشکل برشی با سطح برشی AS2، AS3)
    آزادسازی انتهای عضو (مفصل، آزادسازی پیچش): با تراکم استاتیکی ماتریس عضو
    تقسیم خودکار عضو در گره‌های میانی که روی آن افتاده‌اند (مثل AutoMesh at Joints)
    بارها: گرهی، گسترده یکنواخت (سراسری یا محلی)، وزن با ضریب در هر جهت
    محورهای محلی: قاعده پیش‌فرض SAP (عضو قائم: محور ۲ = +X؛ بقیه: صفحه ۱-۲ قائم، ۲ رو به بالا)

علامت نیروهای داخلی مثل SAP: P مثبت = کشش. واحد: kgf، m.
"""
import math
from dataclasses import dataclass, field

import numpy as np

from .sections import STEEL

DOF = 6
RELEASE_KEYS = ("PI", "V2I", "V3I", "TI", "M2I", "M3I", "PJ", "V2J", "V3J", "TJ", "M2J", "M3J")


@dataclass
class Member:
    name: str
    i: str
    j: str
    section: object                          # sections.Section
    releases: tuple = (False,) * 12          # ترتیب RELEASE_KEYS
    angle: float = 0.0                       # چرخش محورهای محلی حول محور ۱ (درجه)
    group: str = ""                          # chord | brace | beam | ...
    k_major: float = 1.0                     # ضریب طول مؤثر (برای طراحی)
    k_minor: float = 1.0


@dataclass
class Pattern:
    """یک الگوی بار (مثل DEAD، Wb، EY)."""
    self_weight: float = 0.0                              # ضریب وزن اعضا (رو به پایین)
    joint: list = field(default_factory=list)             # [(گره، (F1,F2,F3,M1,M2,M3))]
    uniform: list = field(default_factory=list)           # [(عضو، "X"|"Y"|"Z"|"1"|"2"|"3"، w)]
    partial: list = field(default_factory=list)           # [(عضو، جهت، ra، rb، wa، wb)] نسبی، خطی
    gravity: list = field(default_factory=list)           # [(عضو، (mx, my, mz))] × وزن عضو


@dataclass
class Model:
    nodes: dict = field(default_factory=dict)             # نام ← (x, y, z)
    members: list = field(default_factory=list)
    supports: dict = field(default_factory=dict)          # نام ← (U1..R3) True = مقید
    patterns: dict = field(default_factory=dict)          # نام ← Pattern
    combos: dict = field(default_factory=dict)            # نام ← [(ضریب، الگو یا ترکیب)]
    E: float = STEEL["E"]
    G: float = STEEL["G"]
    gamma: float = STEEL["gamma"]

    def member(self, name):
        return next(m for m in self.members if m.name == name)


# ------------------------------------------------------------------ هندسه عضو
def local_axes(p, q, angle=0.0):
    """ماتریس دوران ۳×۳ (سطرها: محورهای محلی ۱، ۲، ۳ در مختصات سراسری)."""
    d = np.subtract(q, p, dtype=float)
    L = np.linalg.norm(d)
    e1 = d / L
    if abs(e1[2]) > 1 - 1e-9:                       # قائم
        e2 = np.array([1.0, 0.0, 0.0])
    else:
        z = np.array([0.0, 0.0, 1.0])
        e2 = z - e1 * e1.dot(z)
        e2 /= np.linalg.norm(e2)
    e3 = np.cross(e1, e2)
    if angle:
        a = math.radians(angle)
        e2, e3 = math.cos(a) * e2 + math.sin(a) * e3, -math.sin(a) * e2 + math.cos(a) * e3
    return np.vstack([e1, e2, e3]), L


def element_stiffness(sec, L, E, G):
    """ماتریس سختی ۱۲×۱۲ محلی، تیر تیموشنکو."""
    A, J, Iz, Iy = sec.A, sec.J, sec.I33, sec.I22
    py = 12 * E * Iz / (G * sec.AS2 * L * L) if sec.AS2 else 0.0     # خمش در صفحه ۱-۲
    pz = 12 * E * Iy / (G * sec.AS3 * L * L) if sec.AS3 else 0.0     # خمش در صفحه ۱-۳
    k = np.zeros((12, 12))
    ea, gj = E * A / L, G * J / L
    k[0, 0] = k[6, 6] = ea
    k[0, 6] = k[6, 0] = -ea
    k[3, 3] = k[9, 9] = gj
    k[3, 9] = k[9, 3] = -gj
    # جابه‌جایی ۲ و دوران ۳
    a = 12 * E * Iz / (L ** 3 * (1 + py))
    b = 6 * E * Iz / (L ** 2 * (1 + py))
    c = (4 + py) * E * Iz / (L * (1 + py))
    d = (2 - py) * E * Iz / (L * (1 + py))
    for (r, s), v in {(1, 1): a, (1, 5): b, (1, 7): -a, (1, 11): b, (5, 5): c, (5, 7): -b,
                      (5, 11): d, (7, 7): a, (7, 11): -b, (11, 11): c}.items():
        k[r, s] = k[s, r] = v
    # جابه‌جایی ۳ و دوران ۲
    a = 12 * E * Iy / (L ** 3 * (1 + pz))
    b = 6 * E * Iy / (L ** 2 * (1 + pz))
    c = (4 + pz) * E * Iy / (L * (1 + pz))
    d = (2 - pz) * E * Iy / (L * (1 + pz))
    for (r, s), v in {(2, 2): a, (2, 4): -b, (2, 8): -a, (2, 10): -b, (4, 4): c, (4, 8): b,
                      (4, 10): d, (8, 8): a, (8, 10): b, (10, 10): c}.items():
        k[r, s] = k[s, r] = v
    return k


_GX, _GW = np.polynomial.legendre.leggauss(6)


def _gauss(f, a, b):
    if b <= a:
        return 0.0
    h = (b - a) / 2
    return h * sum(w * f(a + h * (1 + x)) for x, w in zip(_GX, _GW))


def _q(segs, k, s):
    """شدت بار محلی در امتداد k در فاصله s."""
    v = 0.0
    for a, b, wa, wb in segs:
        if a - 1e-12 <= s <= b + 1e-12 and b > a:
            v += wa[k] + (wb[k] - wa[k]) * (s - a) / (b - a)
    return v


def _int_q(segs, k, x0, x1, arm=None):
    """∫ q_k(s)·(s − arm) ds روی [x0, x1] (arm=None یعنی بدون بازو)."""
    tot = 0.0
    for a, b, _, _ in segs:
        lo, hi = max(a, x0), min(b, x1)
        if hi > lo:
            tot += _gauss(lambda s: _q([(a, b, *_ab(segs, a, b))], k, s) *
                          (1.0 if arm is None else (s - arm)), lo, hi)
    return tot


def _ab(segs, a, b):
    for sa, sb, wa, wb in segs:
        if sa == a and sb == b:
            return wa, wb
    raise KeyError


def fixed_end(segs, L, sec=None, E=STEEL["E"], G=STEEL["G"]):
    """
    نیروهای انتهای گیردار عضو (نیروی گره‌ها بر عضو) زیر بار خطی تکه‌ای محلی
    segs = [(xa, xb, wa(3), wb(3))]. از سازگاری کنسول تیموشنکو: دقیق با تغییرشکل برشی.
    """
    r = np.zeros(12)
    if not segs:
        return r
    brk = sorted({0.0, L} | {min(max(v, 0.0), L) for a, b, _, _ in segs for v in (a, b)})
    # محوری
    q1 = _int_q(segs, 0, 0, L)
    fj = -_int_q(segs, 0, 0, L, arm=0.0) / L
    r[6], r[0] = fj, -(fj + q1)

    def plane(k, EI, GAs):
        tot = _int_q(segs, k, 0, L)
        if abs(tot) < 1e-15 and not any(abs(wa[k]) + abs(wb[k]) for *_, wa, wb in segs):
            return 0.0, 0.0, 0.0, 0.0
        m = lambda x: _int_q(segs, k, x, L, arm=x)         # لنگر ناشی از بار بعد از x
        v = lambda x: _int_q(segs, k, x, L)
        dq = sum(_gauss(lambda x: m(x) * (L - x), a, b) for a, b in zip(brk, brk[1:])) / EI
        if GAs:
            dq += sum(_gauss(v, a, b) for a, b in zip(brk, brk[1:])) / GAs
        tq = sum(_gauss(m, a, b) for a, b in zip(brk, brk[1:])) / EI
        fl = np.array([[L ** 3 / (3 * EI) + (L / GAs if GAs else 0), L * L / (2 * EI)],
                       [L * L / (2 * EI), L / EI]])
        FJ, MJ = np.linalg.solve(fl, [-dq, -tq])
        FI = -(FJ + tot)
        MI = -(MJ + FJ * L + _int_q(segs, k, 0, L, arm=0.0))
        return FI, MI, FJ, MJ

    if sec is None:
        raise ValueError("fixed_end به مقطع نیاز دارد")
    FI, MI, FJ, MJ = plane(1, E * sec.I33, G * sec.AS2)
    r[1], r[5], r[7], r[11] = FI, MI, FJ, MJ
    FI, MI, FJ, MJ = plane(2, E * sec.I22, G * sec.AS3)
    r[2], r[4], r[8], r[10] = FI, -MI, FJ, -MJ                   # دوران ۲ = −dw/dx
    return r


def condense(k, r, released):
    """تراکم استاتیکی درجات آزادسازی‌شده؛ نیروی انتهای آزاد شده صفر می‌شود."""
    rel = [i for i, x in enumerate(released) if x]
    if not rel:
        return k, r
    keep = [i for i in range(12) if i not in rel]
    krr = k[np.ix_(rel, rel)]
    kkr = k[np.ix_(keep, rel)]
    inv = np.linalg.pinv(krr)
    kc = np.zeros_like(k)
    kc[np.ix_(keep, keep)] = k[np.ix_(keep, keep)] - kkr @ inv @ kkr.T
    rc = np.zeros_like(r)
    rc[keep] = r[keep] - kkr @ inv @ r[rel]
    return kc, rc


# ------------------------------------------------------------------ تقسیم در گره‌ها
@dataclass
class _Element:
    member: Member
    a: str
    b: str
    T: np.ndarray        # ۳×۳
    L: float
    released: tuple
    s0: float            # فاصله ابتدای این قطعه از سر I عضو اصلی


def _mesh(model):
    pts = {n: np.array(c, dtype=float) for n, c in model.nodes.items()}
    elements = []
    for m in model.members:
        p, q = pts[m.i], pts[m.j]
        d = q - p
        L = float(np.linalg.norm(d))
        inner = []
        for n, c in pts.items():
            if n in (m.i, m.j):
                continue
            t = float((c - p).dot(d) / (L * L))
            if 1e-6 < t < 1 - 1e-6 and np.linalg.norm(p + t * d - c) < 1e-5:
                inner.append((t, n))
        chain = [m.i] + [n for _, n in sorted(inner)] + [m.j]
        T, _ = local_axes(p, q, m.angle)
        s0 = 0.0
        for k, (a, b) in enumerate(zip(chain, chain[1:])):
            le = float(np.linalg.norm(pts[b] - pts[a]))
            rel = [False] * 12
            if k == 0:
                rel[:6] = m.releases[:6]
            if k == len(chain) - 2:
                rel[6:] = m.releases[6:]
            elements.append(_Element(m, a, b, T, le, tuple(rel), s0))
            s0 += le
    return elements


# ------------------------------------------------------------------ تحلیل
class Results:
    def __init__(self, model, index, disp, forces, reactions):
        self.model, self.index = model, index
        self.disp = disp              # الگو/ترکیب ← آرایه (n_node، ۶)
        self.forces = forces          # الگو/ترکیب ← {عضو: [(s, P, V2, V3, T, M2, M3)]}
        self.reactions = reactions    # الگو/ترکیب ← {گره: (F1..M3)}

    def cases(self):
        return list(self.disp)

    def displacement(self, case, node):
        return self.disp[case][self.index[node]]


def analyse(model, stations=3):
    """تحلیل همه الگوها و ترکیب‌ها."""
    names = list(model.nodes)
    index = {n: k for k, n in enumerate(names)}
    ndof = len(names) * DOF
    elements = _mesh(model)
    E, G = model.E, model.G

    K = np.zeros((ndof, ndof))
    kcache = []
    for el in elements:
        k = element_stiffness(el.member.section, el.L, E, G)
        kc, _ = condense(k, np.zeros(12), el.released)
        R = np.zeros((12, 12))
        for b in range(4):
            R[3 * b:3 * b + 3, 3 * b:3 * b + 3] = el.T
        kg = R.T @ kc @ R
        dofs = [index[el.a] * 6 + i for i in range(6)] + [index[el.b] * 6 + i for i in range(6)]
        K[np.ix_(dofs, dofs)] += kg
        kcache.append((k, R, dofs))

    fixed = np.zeros(ndof, dtype=bool)
    for n, flags in model.supports.items():
        for i, f in enumerate(flags):
            if f:
                fixed[index[n] * 6 + i] = True
    # درجه آزادی بدون سختی (گره‌ای که همه اعضایش در آن دوران آزاد دارند): مقید، بدون بار
    diag = np.abs(np.diag(K))
    tiny = (diag < 1e-9 * diag.max()) & ~fixed
    free = ~fixed & ~tiny

    # بردار بار هر الگو + بار گسترده هر قطعه (برای نیروی داخلی)
    pats = list(model.patterns)
    F = np.zeros((ndof, len(pats)))
    wloc = {}                        # (الگو، شماره قطعه) ← w محلی
    for c, pn in enumerate(pats):
        pat = model.patterns[pn]
        for n, load in pat.joint:
            F[index[n] * 6:index[n] * 6 + 6, c] += load
        per_member = {}
        for mname, direction, w in pat.uniform:
            per_member.setdefault(mname, []).append((direction, 0.0, 1.0, w, w))
        for mname, direction, ra, rb, wa, wb in pat.partial:
            per_member.setdefault(mname, []).append((direction, ra, rb, wa, wb))
        for mname, mult in pat.gravity:
            per_member.setdefault(mname, []).append(("G", 0.0, 1.0, mult, mult))
        mlen = {}
        for e, el in enumerate(elements):
            m = el.member
            if m.name not in mlen:
                mlen[m.name] = math.dist(model.nodes[m.i], model.nodes[m.j])
            Lm = mlen[m.name]
            loads = list(per_member.get(m.name, []))
            if pat.self_weight:
                loads.append(("G", 0.0, 1.0, (0, 0, -pat.self_weight), (0, 0, -pat.self_weight)))
            segs = []
            for direction, ra, rb, wa, wb in loads:
                a, b = ra * Lm - el.s0, rb * Lm - el.s0            # در مختصات این قطعه
                lo, hi = max(a, 0.0), min(b, el.L)
                if hi - lo < 1e-12:
                    continue
                va = _vec(direction, wa, el, m, model)
                vb = _vec(direction, wb, el, m, model)
                at = lambda x: va + (vb - va) * ((x - a) / (b - a) if b > a else 0.0)
                segs.append((lo, hi, at(lo), at(hi)))
            if not segs:
                continue
            wloc[(c, e)] = segs
            k, R, dofs = kcache[e]
            _, rc = condense(k, fixed_end(segs, el.L, m.section, E, G), el.released)
            F[dofs, c] -= R.T @ rc

    U = np.zeros((ndof, len(pats)))
    warnings = []
    if free.any():
        Kff = K[np.ix_(free, free)]
        try:
            np.linalg.cholesky(Kff)
            U[free] = np.linalg.solve(Kff, F[free])
        except np.linalg.LinAlgError:
            U[free], warnings = _solve_with_mechanisms(Kff, F[free], np.where(free)[0], names)

    # ایستگاه‌های یکسان برای همه حالت‌ها (برای ترکیب): سرها، میانه‌ها و مرز بارها
    marks = {}
    for (c, e), segs in wloc.items():
        marks.setdefault(e, set()).update(v for a, b, _, _ in segs for v in (a, b))
    disp, forces, reactions = {}, {}, {}
    for c, pn in enumerate(pats):
        disp[pn] = U[:, c].reshape(-1, 6)
        forces[pn] = _internal(elements, kcache, U[:, c], {e: w for (cc, e), w in wloc.items()
                                                        if cc == c}, stations, model, marks)
        r = K @ U[:, c] - F[:, c]
        reactions[pn] = {n: tuple(r[index[n] * 6:index[n] * 6 + 6]) for n in model.supports}

    res = Results(model, index, disp, forces, reactions)
    res.warnings = warnings
    for cn in model.combos:
        _combine(res, cn, model.combos)
    return res


def _vec(direction, w, el, m, model):
    """شدت بار (عدد یا بردار ضریب وزن) ← بردار محلی ۳تایی."""
    if direction == "G":
        return el.T @ (np.array(w, dtype=float) * m.section.A * model.gamma)
    if direction in ("X", "Y", "Z"):
        g = np.zeros(3)
        g["XYZ".index(direction)] = w
        return el.T @ g
    v = np.zeros(3)
    v[int(direction) - 1] = w
    return v


def _solve_with_mechanisms(Kff, F, dofs, names):
    """
    ماتریس سختی منفرد (سازوکار بدون سختی، مثل چرخش نبشی پایه حول محور خودش وقتی همه
    اعضای متصل در پیچش آزادند). مثل SAP: اگر بار در امتداد سازوکار نباشد، جواب در
    زیرفضای پایدار یکتاست و گزارش می‌شود؛ اگر باشد، سازه ناپایدار است.
    """
    lam, vec = np.linalg.eigh(Kff)
    tol = 1e-10 * lam.max()
    zero = lam < tol
    Vn = vec[:, zero]
    leak = np.abs(Vn.T @ F).max() if zero.any() else 0.0
    if leak > 1e-6 * max(1.0, np.abs(F).max()):
        k = int(np.argmax(np.abs(Vn.T @ F).max(axis=1)))
        big = np.argsort(-np.abs(Vn[:, k]))[:4]
        where = "، ".join(f"گره {names[dofs[b] // 6]} ({'U1 U2 U3 R1 R2 R3'.split()[dofs[b] % 6]})"
                         for b in big)
        raise ValueError(f"سازه ناپایدار است: بار در امتداد یک سازوکار بدون سختی — {where}")
    Vs, ls = vec[:, ~zero], lam[~zero]
    U = Vs @ ((Vs.T @ F) / ls[:, None])
    notes = []
    for k in range(Vn.shape[1]):
        big = np.argsort(-np.abs(Vn[:, k]))[:2]
        notes.append("سازوکار بدون بار (مثل هشدار ناپایداری SAP): " + "، ".join(
            f"گره {names[dofs[b] // 6]} {'U1 U2 U3 R1 R2 R3'.split()[dofs[b] % 6]}" for b in big))
    return U, notes


def _internal(elements, kcache, u, wl, stations, model, marks):
    out = {}
    for e, el in enumerate(elements):
        k, R, dofs = kcache[e]
        segs = wl.get(e, [])
        sec = el.member.section
        kc, rc = condense(k, fixed_end(segs, el.L, sec, model.E, model.G), el.released)
        f = kc @ (R @ u[dofs]) + rc            # نیروی گره‌ها بر عضو، محلی
        fI = f[:6]
        rows = out.setdefault(el.member.name, [])
        xs = set(np.linspace(0, el.L, stations))
        xs |= {min(max(v, 0.0), el.L) for v in marks.get(e, ())}
        xs = {round(x, 9) for x in xs}
        for x in sorted(xs):
            q = [_int_q(segs, k_, 0, x) if segs else 0.0 for k_ in range(3)]
            mq = [_int_q(segs, k_, 0, x, arm=x) if segs else 0.0 for k_ in range(3)]
            P = -(fI[0] + q[0])
            V2 = fI[1] + q[1]
            V3 = fI[2] + q[2]
            Tq = -fI[3]
            M2 = -fI[4] - x * fI[2] + mq[2]
            M3 = -fI[5] + x * fI[1] - mq[1]
            rows.append((el.s0 + x, P, V2, V3, Tq, M2, M3))
    return out


def _combine(res, name, combos, seen=None):
    """ترکیب خطی (Linear Add)؛ ترکیب می‌تواند از ترکیب دیگر ساخته شده باشد."""
    if name in res.disp:
        return
    seen = (seen or set()) | {name}
    parts = combos[name]
    for _, case in parts:
        if case not in res.disp:
            if case in seen or case not in combos:
                raise ValueError(f"ترکیب {name}: حالت {case} تعریف نشده")
            _combine(res, case, combos, seen)
    first = parts[0][1]
    res.disp[name] = sum(f * res.disp[c] for f, c in parts)
    res.reactions[name] = {n: tuple(sum(f * np.array(res.reactions[c][n]) for f, c in parts))
                           for n in res.reactions[first]}
    res.forces[name] = {m: [tuple([rows[s][0]] + [sum(f * res.forces[c][m][s][q] for f, c in parts)
                                                  for q in range(1, 7)])
                            for s in range(len(rows))]
                        for m, rows in res.forces[first].items()}
