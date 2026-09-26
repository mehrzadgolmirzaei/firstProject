"""
محاسبه و ترسیم فونداسیون پایه تجهیزات پست.

    python run.py LA
    python run.py LA --project project.json
    python run.py LA --edition 4                  بازتولید دفترچه قدیمی
    python run.py --save-project project.json     ساخت فایل تنظیمات پیش‌فرض

تمام اعداد قابل تنظیم در project.json هستند: مصالح، خاک، باد، لرزه،
آرماتور، ابعاد اولیه، مقیاس و فیلدهای جدول عنوان.
یادداشت‌های نقشه در notes.txt ویرایش می‌شوند.
"""
import argparse, os, datetime
from config import ProjectConfig
from equipment import CATALOG
from engine import from_config, find_dimensions, quantities
from seismic import Site2800v5, Site2800v4
from design import design_all

REBAR_UNIT = lambda d: 0.006165 * d * d


def bar_schedule(res, eq, soil, des, rebar):
    g = res.geometry
    cov = soil.cover / 1000
    L, B, tf, hp, b = g.L, g.B, g.tf, g.hp, g.b
    n_ped = eq.n_pedestal
    pad_dia, pad_sp = des["pad"].bar_dia, des["pad"].spacing
    col_n, col_dia = des["pedestal"].bar_count, des["pedestal"].bar_dia
    nx = int((L - 2 * cov) / (pad_sp / 1000)) + 1
    ny = int((B - 2 * cov) / (pad_sp / 1000)) + 1
    raw = [
        ("01", "PAD  BOTTOM  E.W.", pad_dia, 2 * ny, L - 2 * cov + 2 * 10 * pad_dia / 1000),
        ("02", "PEDESTAL VERTICAL", col_dia, col_n * n_ped,
         tf + hp - 2 * cov + 15 * col_dia / 1000),
        ("03", "PAD  TOP  E.W.", pad_dia, 2 * nx, B - 2 * cov + 2 * 10 * pad_dia / 1000),
        ("04", "STANDEE", rebar.standee_dia, nx, (tf - 2 * cov) + 0.4),
        ("05", "PEDESTAL TIE", rebar.tie_dia, (int(hp / (rebar.tie_spacing / 1000)) + 1) * n_ped,
         4 * (b - 2 * cov) + 20 * rebar.tie_dia / 1000),
    ]
    rows = []
    for pos, shape, dia, no, length in raw:
        total = no * length
        rows.append(dict(pos=pos, shape=shape, dia=dia, no=no, length=length,
                         total=total, unit_w=REBAR_UNIT(dia), weight=total * REBAR_UNIT(dia)))
    return rows


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
          f"- ستون: {eq.n_pedestal} عدد {g.b:.2f}×{g.b:.2f} به ارتفاع {g.hp:.2f} m",
          f"- تعداد تجهیز در پروژه: {cfg.equipment_count}", "",
          "## ضریب زلزله"]
    for lab, formula, subst in seis.steps:
        o.append(f"- **{lab}** — `{formula}` → {subst}")
    o += ["", "## حالات بارگذاری",
          "| # | حالت | Fe | Fs | N max | N min | V | M |", "|---|---|---|---|---|---|---|---|"]
    for c in res.cases:
        mark = " ←" if c.no == res.governing.no else ""
        o.append(f"| {c.no}{mark} | {c.name} | {c.Fe:.0f} | {c.Fs:.0f} | {c.Nmax:.0f} | "
                 f"{c.Nmin:.0f} | {c.V:.0f} | {c.M:.0f} |")
    o += ["", "## کنترل‌های طراحی"]
    for ck in res.checks:
        o.append(f"### {ck.name} — {'قبول' if ck.passed else 'مردود'}")
        for lab, formula, subst in ck.steps:
            o.append(f"- {lab}: `{formula}` → {subst}")
        o += [f"- **نتیجه: {ck.value:.2f} {ck.direction} {ck.limit:.2f} {ck.unit}**", ""]
    o.append("## طراحی مقطع")
    for key in ("pedestal", "pad", "punching", "oneway"):
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
          "> آنچه هنوز نیست: زمان تناوب T ، ترکیب ۱۰۰/۳۰ زلزله ، طراحی میل مهار و صفحه کف."]
    return "\n".join(o)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tag", nargs="?", choices=list(CATALOG))
    ap.add_argument("--project", default="project.json")
    ap.add_argument("--save-project", metavar="PATH")
    ap.add_argument("--edition", type=int, choices=[4, 5])
    ap.add_argument("--no-dxf", action="store_true")
    ap.add_argument("--simple", action="store_true",
                    help="بدون DIMENSION — برای عیب‌یابی باز نشدن فایل")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()

    if a.save_project:
        ProjectConfig().save(a.save_project)
        print(f"فایل تنظیمات ساخته شد: {a.save_project}")
        return
    if not a.tag:
        ap.error("نام تجهیز لازم است، مثلاً:  python run.py LA")

    cfg = ProjectConfig.load(a.project if os.path.exists(a.project) else None)
    if a.edition:
        cfg.seismic.edition = a.edition
    if a.simple:
        cfg.drawing.dxf_version = "R2000"

    eq = CATALOG[a.tag]
    soil, wind = from_config(cfg)
    s = cfg.seismic
    seis = (Site2800v4(a=s.a, b=s.b, i=s.i, r=s.r).compute() if s.edition == 4
            else Site2800v5(ss=s.ss, s1=s.s1, soil=s.soil_class, ie=s.ie,
                            ru=s.ru, method=s.method, map_date=s.map_date).compute())

    f = cfg.foundation
    res = find_dimensions(eq, soil, wind, seis.ch, seis.cv,
                          hp=f.hp, b=f.b, tf=f.tf,
                          lo=f.search_min, hi=f.search_max, step=f.search_step)
    if res is None:
        print(f"تا {f.search_max} متر جوابی پیدا نشد — ورودی‌ها را بررسی کنید.")
        return

    des = design_all(res, eq, soil, cfg.rebar)
    qty = quantities(res, eq, soil)
    bbs = bar_schedule(res, eq, soil, des, cfg.rebar)
    qty["rebar"] = sum(r["weight"] for r in bbs)

    os.makedirs(a.out, exist_ok=True)
    rpt = os.path.join(a.out, f"{a.tag}_report.md")
    open(rpt, "w", encoding="utf-8").write(report(res, eq, soil, seis, qty, bbs, des, cfg))

    g = res.geometry
    print(f"{eq.tag}: پی {g.L:.2f}×{g.B:.2f}×{g.tf:.2f} m  |  "
          f"Ch={seis.ch:.3f} Cv={seis.cv:.3f} (ویرایش {seis.edition})")
    for c in res.checks:
        print(f"   {c.name:24} {c.value:8.2f} {c.direction} {c.limit:6.2f}  "
              f"{'قبول' if c.passed else 'مردود'}")
    pad, ped = des["pad"], des["pedestal"]
    print(f"   آرماتور پی   {pad.bar_count}Ф{pad.bar_dia}@{pad.spacing:.0f}")
    print(f"   آرماتور ستون {ped.bar_count}Ф{ped.bar_dia}")
    for key in ("punching", "oneway"):
        print(f"   {des[key].title:24} {des[key].note}")
    print(f"   بتن {qty['concrete']:.2f} m3 | مگر {qty['lean']:.3f} m3 | "
          f"آرماتور {qty['rebar']:.0f} kg")
    print(f"گزارش: {rpt}")

    if a.no_dxf:
        return
    try:
        from drawing import FoundationDrawing
        tb = cfg.title_block.fields
        if not str(tb.get("DOCUMENT_TITLE", "")).strip():
            tb["DOCUMENT_TITLE"] = f"{eq.title.upper()} FOUNDATION"
        tb["SCALE"] = f"1/{cfg.drawing.scale:.0f}"
        dwg = FoundationDrawing(cfg, simple=a.simple)
        dwg.build(res, eq, soil, qty, bbs, seis, des)
        print("نقشه:", dwg.save(os.path.join(a.out, f"{a.tag}_foundation.dxf")))
    except ImportError:
        print("ezdxf نصب نیست:  python -m pip install ezdxf")


if __name__ == "__main__":
    main()
