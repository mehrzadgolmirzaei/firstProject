"""
طراحی خودکار سازه نگهدارنده: ساخت ← بارگذاری ← تحلیل ← کنترل ASD89 ← انتخاب مقطع.

انتخاب مقطع از سبک‌ترین مقطع مجاز هر گروه شروع می‌شود و فقط گروهی که رد شود یک
پله سنگین‌تر می‌شود؛ بعد از هر تغییر کل سازه دوباره تحلیل می‌شود (نیروی اعضای
سازه نامعین به سختی بستگی دارد). نتیجه: سبک‌ترین ترکیب مقاطعی که همه کنترل‌ها را
پاس می‌کند، با نسبت تنش هر عضو، عکس‌العمل هر پایه و وزن سازه.
"""
import copy
import math
from dataclasses import dataclass, field

from . import asd89
from .frame import analyse
from .lattice import LatticeSpec, build
from .loads import apply_loads, COMBO_TITLES
from .sections import ANGLES, CHANNELS, CATALOG

GROUP_TITLES = {"chord": "نبشی اصلی پایه", "brace": "مهاربند", "strut": "افقی سر پایه",
                "beam": "تیر سر سازه"}


def failure_mode(ck):
    """حالت حاکم یک کنترل: کدام اثر نسبت تنش را ساخته است."""
    g = ck.governing
    if ck.klr and abs(g - ck.klr / ck.klr_limit) < 1e-12 and g > ck.ratio:
        return "slender"
    if abs(g - ck.shear_ratio) < 1e-12 and g > ck.ratio:
        return "shear"
    axial = ck.fa / ck.Fa if ck.Fa else 0.0
    bend = (ck.fb33 / ck.Fb33 if ck.Fb33 else 0.0) + (ck.fb22 / ck.Fb22 if ck.Fb22 else 0.0)
    if ck.P < 0:
        return "buckle" if axial >= bend else "bend"
    return "tension" if axial >= bend else "bend"


@dataclass
class StructureDesign:
    spec: LatticeSpec
    model: object
    results: object
    checks: dict                        # عضو ← asd89.Check
    sections: dict                      # گروه ← نام مقطع
    weight: float                       # وزن اعضا (kg)
    wind_area: float
    stands: int                         # تعداد سازه مستقل (CVT سه‌فاز روی سه پایه: ۳)
    phases_per_stand: int
    leg_reactions: dict = field(default_factory=dict)   # ترکیب ← [(Fx, Fy, Fz, Mx, My) هر پایه]
    history: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    @property
    def max_ratio(self):
        return max(c.governing for c in self.checks.values())

    @property
    def ok(self):
        return all(c.ok for c in self.checks.values())

    def combo_ratios(self):
        """
        نسبت تنش هر عضو در هر ترکیب طراحی جداگانه — برای نمایش سازه «زیر بار» هر ترکیب.
        {ترکیب: {عضو: نسبت حاکم}}
        """
        if getattr(self, "_combo_ratios", None) is None:
            import math as _m
            m, res = self.model, self.results
            combos = getattr(m, "design_combos", None) or list(m.combos)
            fy = getattr(self, "fy", None)
            out, modes = {c: {} for c in combos}, {}
            for mb in m.members:
                L = _m.dist(m.nodes[mb.i], m.nodes[mb.j])
                f = fy or getattr(mb.section, "fy", None) or 2.4e7
                for c in combos:
                    ck = asd89.check_member(mb.name, mb.section, L, {c: res.forces[c][mb.name]}, f,
                                            m.E, mb.k_major, mb.k_minor,
                                            getattr(mb, "l_major", 1.0), getattr(mb, "l_minor", 1.0))
                    out[c][mb.name] = ck.governing
                    modes.setdefault(c, {})[mb.name] = failure_mode(ck)
            self._combo_ratios, self._combo_modes = out, modes
        return self._combo_ratios

    def combo_modes(self):
        """{ترکیب: {عضو: حالت حاکم}} — «buckle» کمانش فشاری، «bend» خمش، «tension» کشش،
        «shear» برش، «slender» لاغری."""
        self.combo_ratios()
        return self._combo_modes

    def chord_extremes(self):
        """
        هر پایه: بیشترین فشار و کشش یک نبشی (پای نبشی ← میل مهار)، بیشترین لنگر پایه
        (زوج‌نیروی نبشی‌ها) — [(فشار، ترکیب)، (کشش، ترکیب)، (لنگر، ترکیب)].
        """
        m, a = self.model, self.spec.leg_width
        out = []
        for i, cx in enumerate(m.leg_centres):
            sup = [n for n in m.supports if abs(m.nodes[n][0] - cx) <= a / 2 + 1e-6]
            comp = max(((self.results.reactions[c][n][2], c) for c in m.combos for n in sup))
            ten = min(((self.results.reactions[c][n][2], c) for c in m.combos for n in sup))
            mom = max(((abs(complex(r[3], r[4])), c) for c, legs in self.leg_reactions.items()
                       for r in [legs[i]]))
            out.append((comp, ten, mom))
        return out

    def group_summary(self):
        out = {}
        for m in self.model.members:
            c = self.checks[m.name]
            g = out.setdefault(m.group, {"group": m.group, "title": GROUP_TITLES.get(m.group, m.group),
                                         "section": m.section.name, "count": 0, "ratio": 0.0,
                                         "member": "", "check": None, "length": 0.0})
            g["count"] += 1
            g["length"] += math.dist(self.model.nodes[m.i], self.model.nodes[m.j])
            if c.governing > g["ratio"]:
                g["ratio"], g["member"], g["check"] = c.governing, m.name, c
        return list(out.values())


def stand_layout(eq):
    """
    چند سازه و هر کدام چند پایه/فاز: CVT سه‌فاز روی سه ستون ← سه سازه تک‌پایه تک‌فاز؛
    تجهیز سه‌فاز روی دو ستون ← یک سازه دوپایه سه‌فاز؛ تک‌فاز روی یک ستون ← یک سازه.
    """
    n = max(1, eq.n_pedestal)
    if eq.npol > 1 and eq.npol == n:
        return n, 1, 1                  # (تعداد سازه، پایه هر سازه، فاز هر سازه)
    return 1, n, eq.npol


def _ladder(kind, minimum):
    items = ANGLES if kind == "angle" else CHANNELS
    names = [s.name for s in items]
    start = names.index(minimum) if minimum in names else 0
    return names[start:]


def _leg_reactions(model, results, combos):
    out = {}
    a = model.spec.leg_width
    for c in combos:
        legs = []
        for cx in model.leg_centres:
            F = [0.0] * 5
            for n, r in results.reactions[c].items():
                x, y, _ = model.nodes[n]
                if abs(x - cx) <= a / 2 + 1e-6:
                    F[0] += r[0]
                    F[1] += r[1]
                    F[2] += r[2]
                    F[3] += y * r[2] + r[3]               # لنگر حول X در مرکز پایه
                    F[4] += -(x - cx) * r[2] + r[4]       # لنگر حول Y
            legs.append(tuple(F))
        out[c] = legs
    return out


def design_structure(eq, steel_cfg, wind, ch, cv, eq_sc=0.6, sections=None, max_iter=25):
    """
    eq: تجهیز (engine.Equipment)؛ steel_cfg: config.SteelStructure.
    sections: {گروه: مقطع} برای کنترل یک طرح داده‌شده (بدون انتخاب خودکار).
    """
    stands, legs, phases = stand_layout(eq)
    eq_s = copy.copy(eq)
    eq_s.npol = phases
    fy = steel_cfg.fy * 1e4
    chosen = dict(sections or {"chord": steel_cfg.min_chord, "brace": steel_cfg.min_brace,
                               "strut": steel_cfg.min_chord, "beam": steel_cfg.min_beam})
    ladders = {"chord": _ladder("angle", steel_cfg.min_chord),
               "brace": _ladder("angle", steel_cfg.min_brace),
               "strut": _ladder("angle", steel_cfg.min_chord),
               "beam": _ladder("channel", steel_cfg.min_beam)}
    history = []
    for it in range(max_iter):
        spec = LatticeSpec(eq.Hs, legs=legs, leg_spacing=eq.pedestal_spacing or 0.0,
                           leg_width=steel_cfg.leg_width, phases=phases,
                           phase_pitch=steel_cfg.phase_pitch, panel=steel_cfg.panel,
                           bracing=steel_cfg.bracing, chord=chosen["chord"],
                           brace=chosen["brace"], beam=chosen["beam"], k_chord=steel_cfg.k_chord)
        model = build(spec)
        for m in model.members:                      # افقی‌ها مقطع گروه خودشان را دارند
            if m.group == "strut":
                m.section = CATALOG[chosen["strut"]]
        info = apply_loads(model, eq_s, wind, ch, cv, eq_sc, steel_cfg.live_load)
        results = analyse(model)
        checks = asd89.design(model, results, Fy=fy)
        worst = {}
        for m in model.members:
            worst[m.group] = max(worst.get(m.group, 0.0), checks[m.name].governing)
        history.append({"iter": it + 1, "sections": dict(chosen),
                        "ratios": {g: round(v, 3) for g, v in worst.items()}})
        if sections is not None:
            break
        changed = False
        for g, r in worst.items():
            if r > steel_cfg.ratio_limit + 1e-9:
                lad = ladders[g]
                k = lad.index(chosen[g]) if chosen[g] in lad else 0
                if k + 1 < len(lad):
                    chosen[g] = lad[k + 1]
                    changed = True
        if not changed:
            break
    weight = sum(m.section.A * model.gamma * math.dist(model.nodes[m.i], model.nodes[m.j])
                 for m in model.members)
    d = StructureDesign(spec, model, results, checks, chosen, weight, info["wind_area"],
                        stands, phases, _leg_reactions(model, results, model.combos),
                        history, list(results.warnings))
    d.fy = fy
    from .loads import load_table
    d.load_table = load_table(eq_s, wind, ch, cv, eq_sc, steel_cfg.live_load, weight,
                              info["wind_area"], phases)
    if not d.ok and sections is None:          # فقط در طراحی خودکار؛ در کنترل، رد شدن خودش نتیجه است
        d.warnings.append("با بزرگ‌ترین مقطع کاتالوگ هم همه کنترل‌ها پاس نشد — ابعاد پایه "
                          "(ضلع مربع) یا ارتفاع پانل را تغییر دهید.")
    return d


__all__ = ["design_structure", "StructureDesign", "COMBO_TITLES", "GROUP_TITLES", "stand_layout"]
