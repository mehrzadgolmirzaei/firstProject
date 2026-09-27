"""
محاسبه و ترسیم فونداسیون پایه تجهیزات پست.

    python run.py LA
    python run.py LA --edition 4          بازتولید دفترچه قدیمی
    python run.py LA --recommended        روش کنترل پیشنهادی سامانه
    python run.py LA --governing envelope --bearing max
    python run.py --all                   همه تجهیزات کاتالوگ
    python run.py LA --no-dxf             فقط محاسبه و گزارش
    python run.py --save-project project.json   ساخت فایل تنظیمات پیش‌فرض
    python run.py --keyplan 04-KEY_PLAN.dxf    همه پی‌های کی‌پلن (چیدمان و ابعاد از نقشه)

خروجی در out/:  گزارش LA_report.md ، نقشه دوبعدی LA_2D.dxf ، مدل سه‌بعدی LA_3D.dxf

تمام اعداد قابل تنظیم در project.json هستند: مصالح، خاک، باد، لرزه،
آرماتور، ابعاد اولیه، روش کنترل، مقیاس و فیلدهای جدول عنوان.
یادداشت‌های نقشه در notes.txt ویرایش می‌شوند.
"""
import argparse, copy, os, datetime
from config import ProjectConfig
from equipment import ALL_EQUIPMENT as CATALOG
from pipeline import run, run_layout
from engine import GOVERNING_OPTIONS, BEARING_OPTIONS, RECOMMENDED
from engine import from_config

def report(res, eq, soil, seis, qty, bbs, des, cfg):
    g = res.geometry
    o = [f"# محاسبه فونداسیون — {eq.tag}  ({eq.title})", ""]
    o.append(f"تاریخ: {datetime.date.today()}  |  استاندارد ۲۸۰۰ ویرایش {seis.edition}")
    if cfg.project_name:
        o.append(f"پروژه: {cfg.project_name}  |  پست: {cfg.substation}")
    o.append(f"مرجع داده تجهیز: {eq.source or 'نامشخص'}")
    o.append(f"مصالح: fc={soil.fc} , fy={soil.fy} , پوشش={soil.cover} mm , مگر={soil.lean} mm")
    o += ["", "## ابعاد نهایی",
          f"- پی: **{g.L:.2f} × {g.B:.2f} × {g.tf:.2f} m**",
          f"- چیدمان: {res.layout.describe()}",
          f"- ستون: {res._n} عدد {g.b:.2f}×{g.b:.2f} به ارتفاع {g.hp:.2f} m",
          f"- تعداد تجهیز در پروژه: {cfg.equipment_count}", "",
          "## ضریب زلزله"]
    for lab, formula, subst in seis.steps:
        o.append(f"- **{lab}** — `{formula}` → {subst}")
    o += ["", "## روش کنترل",
          f"- حالت بار حاکم: {GOVERNING_OPTIONS[str(cfg.design.governing)]}",
          f"- تنش خاک: {BEARING_OPTIONS[cfg.design.bearing]}"]
    o += ["", "## حالات بارگذاری",
          "| # | حالت | Fe | Fs | N max | N min | V | M |", "|---|---|---|---|---|---|---|---|"]
    for c in res.cases:
        mark = " ←" if c.no == res.governing.no else ""
        o.append(f"| {c.no}{mark} | {c.name} | {c.Fe:.0f} | {c.Fs:.0f} | {c.Nmax:.0f} | "
                 f"{c.Nmin:.0f} | {c.V:.0f} | {c.M:.0f} |")
    o += ["", "## کنترل‌های طراحی"]
    for ck in res.checks:
        o.append(f"### {ck.name} — {'قبول' if ck.passed else 'مردود'} (حالت {ck.case})")
        for lab, formula, subst in ck.steps:
            o.append(f"- {lab}: `{formula}` → {subst}")
        o += [f"- **نتیجه: {ck.value:.2f} {ck.direction} {ck.limit:.2f} {ck.unit}**", ""]
    o.append("## طراحی مقطع")
    for key in ("pedestal", "pad", "punching", "oneway", "anchor"):
        d = des[key]
        o.append(f"### {d.title} — {'قبول' if d.ok else 'مردود'}")
        for lab, formula, subst in d.steps:
            o.append(f"- {lab}: `{formula}` → {subst}")
        if d.note and not d.ok:
            o.append(f"- ⚠ {d.note}")
        o.append("")
    o += ["## لیست آرماتور", "| POS | شرح | قطر | تعداد | طول | طول کل | وزن |",
          "|---|---|---|---|---|---|---|"]
    for r in bbs:
        o.append(f"| {r['pos']} | {r['shape']} | {r['dia']} | {r['no']} | "
                 f"{r['length']:.2f} | {r['total']:.1f} | {r['weight']:.1f} |")
    o += [f"\n**جمع وزن آرماتور: {qty['rebar']:.1f} kg**", "", "## متره",
          f"- بتن: {qty['concrete']:.2f} m³",
          f"- بتن مگر: {qty['lean']:.3f} m³",
          f"- خاکبرداری: {qty['excavation']:.2f} m³",
          f"- قالب‌بندی: {qty['formwork']:.2f} m²", ""]
    if cfg.equipment_count > 1:
        o.append(f"- برای {cfg.equipment_count} عدد: بتن {qty['concrete']*cfg.equipment_count:.2f} m³ ، "
                 f"آرماتور {qty['rebar']*cfg.equipment_count:.0f} kg")
        o.append("")
    o += ["> آرماتور از طراحی خمشی محاسبه و برش پانچ و یک‌طرفه کنترل شده است.",
          "> آنچه هنوز نیست: ترکیب ۱۰۰/۳۰ زلزله ، طراحی میل مهار و صفحه کف."]
    return "\n".join(o)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tag", nargs="?", choices=list(CATALOG))
    ap.add_argument("--project", default="project.json")
    ap.add_argument("--save-project", metavar="PATH")
    ap.add_argument("--edition", type=int, choices=[4, 5])
    ap.add_argument("--governing", choices=list(GOVERNING_OPTIONS),
                    help="حالت بار حاکم: notebook (دفترچه) | envelope (پوش، پیشنهادی) | 1..5")
    ap.add_argument("--bearing", choices=list(BEARING_OPTIONS),
                    help="بار قائم در تنش خاک: min (دفترچه) | max | envelope (پیشنهادی)")
    ap.add_argument("--recommended", action="store_true",
                    help="هر دو انتخاب با پیشنهاد سامانه")
    ap.add_argument("--all", action="store_true", help="همه تجهیزات کاتالوگ")
    ap.add_argument("--no-dxf", action="store_true")
    ap.add_argument("--simple", action="store_true",
                    help="بدون DIMENSION — برای عیب‌یابی باز نشدن فایل")
    ap.add_argument("--out", default="out")
    ap.add_argument("--keyplan", metavar="DXF",
                    help="کی‌پلن فونداسیون: همه پی‌ها با چیدمان و ابعاد نقشه")
    a = ap.parse_args()

    if a.all:
        import sys
        base = [x for x in sys.argv[1:] if x != "--all"]
        for tag in CATALOG:
            print("=" * 60)
            sys.argv = [sys.argv[0], tag, *base]
            main()
        return
    if a.save_project:
        ProjectConfig().save(a.save_project)
        print(f"فایل تنظیمات ساخته شد: {a.save_project}")
        return
    if not a.tag and not a.keyplan:
        ap.error("نام تجهیز لازم است، مثلاً:  python run.py LA")

    cfg = ProjectConfig.load(a.project if os.path.exists(a.project) else None)
    if a.edition:
        cfg.seismic.edition = a.edition
    if a.recommended:
        cfg.design.governing, cfg.design.bearing = RECOMMENDED["governing"], RECOMMENDED["bearing"]
    if a.governing:
        cfg.design.governing = a.governing
    if a.bearing:
        cfg.design.bearing = a.bearing
    if a.simple:
        cfg.drawing.dxf_version = "R2000"

    if a.keyplan:
        from keyplan import read_foundations
        for f in read_foundations(a.keyplan, CATALOG):
            print("=" * 60)
            if not f.ok:
                print(f"{f.name}: رد شد — {f.problem}")
                continue
            c = copy.deepcopy(cfg)
            c.foundation.L, c.foundation.B, c.foundation.b = f.L, f.B, f.b
            print(f"{f.name} ({f.count} عدد در کی‌پلن): {f.describe()}")
            solve(f.layout(CATALOG), f.name.replace("+", "_"), c, a)
        return
    solve(None, a.tag, cfg, a)


def solve(layout, name, cfg, a):
    eq = layout.main if layout else CATALOG[name]
    res, seis, des, qty, bbs = run_layout(layout, cfg) if layout else run(eq, cfg)
    if res is None:
        f = cfg.foundation
        print(f"تا {f.search_max} متر جوابی پیدا نشد — ورودی‌ها را بررسی کنید.")
        return
    soil = from_config(cfg)[0]

    os.makedirs(a.out, exist_ok=True)
    rpt = os.path.join(a.out, f"{name}_report.md")
    open(rpt, "w", encoding="utf-8").write(report(res, eq, soil, seis, qty, bbs, des, cfg))

    g = res.geometry
    print(f"{eq.tag}: پی {g.L:.2f}×{g.B:.2f}×{g.tf:.2f} m  |  "
          f"Ch={seis.ch:.3f} Cv={seis.cv:.3f} (ویرایش {seis.edition})")
    cmp_ = "  |  ".join(f"{c['label']}: {c['L']:.2f}×{c['B']:.2f}" if c["L"] else f"{c['label']}: —"
                        for c in res.comparison if c["key"] != "selected")
    print(f"   مقایسه روش‌ها — {cmp_}")
    for c in res.checks:
        print(f"   {c.name:24} {c.value:8.2f} {c.direction} {c.limit:6.2f}  "
              f"{'قبول' if c.passed else 'مردود'}  (حالت {c.case})")
    pad, ped = des["pad"], des["pedestal"]
    print(f"   آرماتور پی   {pad.bar_count}Ф{pad.bar_dia}@{pad.spacing:.0f}")
    print(f"   آرماتور ستون {ped.bar_count}Ф{ped.bar_dia}")
    anc = des["anchor"]
    print(f"   میل مهار     {anc.bar_count}M{anc.bar_dia} ، طول مدفون {anc.embed:.0f} mm "
          f"(کشش {anc.tension:.0f} kg) {'' if anc.ok else '⚠ ' + anc.note}")
    for key in ("punching", "oneway"):
        print(f"   {des[key].title:24} {des[key].note}")
    print(f"   بتن {qty['concrete']:.2f} m3 | مگر {qty['lean']:.3f} m3 | "
          f"آرماتور {qty['rebar']:.0f} kg")
    import model
    fm = model.build(res, getattr(res, "layout", eq), des, cfg)
    for n in fm.steel_notes:
        print(f"   {n}")
    for c in model.clashes(fm):
        print(f"   ⚠ تداخل: {c}")
    print(f"گزارش: {rpt}")

    if a.no_dxf:
        return
    try:
        from outputs import make_outputs
        out = make_outputs(res, eq, soil, qty, bbs, seis, des, cfg, a.out, name,
                           simple=a.simple)
        print(f"نقشه دوبعدی (ساخت، ۱:{out['scale']:.0f}):", out["2d"])
        print("مدل سه‌بعدی (ارائه):", out["3d"])
    except ImportError:
        print("ezdxf نصب نیست:  python -m pip install ezdxf")


if __name__ == "__main__":
    main()
