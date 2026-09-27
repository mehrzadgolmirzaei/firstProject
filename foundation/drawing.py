"""
نقشه دوبعدی فونداسیون (برای ساخت) روی کادر و استاندارد شیت شرکت.

    PLAN · SECTION A-A · SECTION B-B · DET."1" ANCHOR BOLT
    BAR BENDING SCHEDULE · NOTE · کادر و جدول عنوان

همه مختصات میلگرد، ستون و میل مهار از مدل مرکزی (model.py) می‌آید؛ این
فایل فقط آن را روی کاغذ می‌آورد.

چیدمان خودکار است: هر نما یک‌بار «خشک» ترسیم و اندازه‌اش سنجیده می‌شود،
بعد کوچک‌ترین مقیاس مجاز (ترجیحاً ۱:۲۰) که همه نماها بدون هم‌پوشانی در
کادر جا شوند انتخاب و نماها چیده می‌شوند. در پایان، هر چیزی که بیرون کادر
افتاده یا نماهایی که روی هم افتاده‌اند گزارش می‌شوند.

دو نکته که اتوکد را می‌شکند و اینجا رعایت شده:
  - نام خالی یا دارای | در جدول‌های نماد → «Invalid symbol table record name»
    و دور انداختن کل فایل. همه فیلتر می‌شوند.
  - کادر شرکت XREF است؛ محتوایش داخل یک بلاک تازه ریخته و درج می‌شود تا
    فایل خروجی خودکفا باشد.
"""
import os
from dataclasses import dataclass

import ezdxf
from ezdxf.enums import TextEntityAlignment

import layout as LO
import model as M


def _valid(name) -> bool:
    n = str(name or "").strip()
    return bool(n) and "|" not in n


@dataclass
class Box:
    x0: float = float("inf")
    y0: float = float("inf")
    x1: float = float("-inf")
    y1: float = float("-inf")

    def add(self, x, y):
        self.x0, self.y0 = min(self.x0, x), min(self.y0, y)
        self.x1, self.y1 = max(self.x1, x), max(self.y1, y)

    def merge(self, o):
        if o.empty:
            return
        self.add(o.x0, o.y0)
        self.add(o.x1, o.y1)

    @property
    def empty(self):
        return self.x0 > self.x1

    @property
    def w(self):
        return self.x1 - self.x0

    @property
    def h(self):
        return self.y1 - self.y0

    def overlaps(self, o, tol=0.0):
        return not (self.x1 <= o.x0 + tol or o.x1 <= self.x0 + tol or
                    self.y1 <= o.y0 + tol or o.y1 <= self.y0 + tol)


ALIGN = {"left": TextEntityAlignment.LEFT, "center": TextEntityAlignment.CENTER,
         "right": TextEntityAlignment.RIGHT, "mleft": TextEntityAlignment.MIDDLE_LEFT,
         "mcenter": TextEntityAlignment.MIDDLE_CENTER, "mright": TextEntityAlignment.MIDDLE_RIGHT}


class FoundationDrawing:
    # نسبت عرض به ارتفاع حروف فونت ROMANC. از روی نقشه 06-4LA_C اندازه‌گیری
    # شد (ضریب واقعی حدود ۰٫۷۸)؛ با حاشیه اطمینان ۰٫۸۵.
    CHAR_W = 0.85

    def __init__(self, cfg, simple=False):
        self.cfg = cfg
        self.simple = simple
        self.s = float(cfg.drawing.scale)
        self.doc = ezdxf.new(cfg.drawing.dxf_version, setup=True)
        self.doc.header["$INSUNITS"] = 4
        self.msp = self.doc.modelspace()
        self.style = "Standard"
        self.dimstyle = "Standard"
        self._dry = False          # در حالت خشک فقط اندازه سنجیده می‌شود
        self._box = None           # جعبه نمای در حال ترسیم
        self._origin = (0.0, 0.0)
        self._excluded = set()     # handle موجودیت‌هایی که عمداً بیرون ناحیه ترسیم‌اند
        self.view_boxes = {}
        self.outside, self.overlaps = [], []
        self._import_styles(cfg.drawing.template_file)
        self._ensure_layers()

    # ================================================== منابع
    def _import_styles(self, template):
        if not template or not os.path.exists(template):
            return
        try:
            src = ezdxf.readfile(template)
            from ezdxf.addons import Importer
            imp = Importer(src, self.doc)
            for table_name, table in (("layers", src.layers),
                                      ("styles", src.styles),
                                      ("dimstyles", src.dimstyles)):
                imp.import_table(table_name,
                                 entries=[e.dxf.name for e in table if _valid(e.dxf.name)])
            imp.finalize()
            self._purge_invalid()
            if LO.TXT_STYLE in self.doc.styles:
                self.style = LO.TXT_STYLE
            if LO.DIM_STYLE in self.doc.dimstyles:
                self.dimstyle = LO.DIM_STYLE
        except Exception as exc:
            print(f"   (سبک‌های تمپلیت وارد نشد: {exc})")

    def _purge_invalid(self):
        for table in (self.doc.layers, self.doc.styles, self.doc.dimstyles):
            for rec in list(table):
                name = getattr(rec.dxf, "name", "")
                if not _valid(name):
                    try:
                        table.remove(name)
                    except Exception:
                        pass

    def _ensure_layers(self):
        for name in {LO.LY_CONCRETE, LO.LY_TEXT, LO.LY_DETAIL, LO.LY_REBAR, LO.LY_HATCH}:
            if name not in self.doc.layers:
                self.doc.layers.add(name)

    # ================================================== تبدیل واحد
    def u(self, paper_mm):
        """طول روی کاغذ → طول در فضای مدل."""
        return paper_mm * self.s

    def paper_to_model(self, x, y):
        ox, oy = LO.FRAME_INSERT
        return ox + x * self.s, oy + y * self.s

    def sheet_bounds(self):
        """ناحیه ترسیم در فضای مدل. کف آن خط بالای جدول عنوان است، نه لبه کادر."""
        x0, y0, x1, y1 = LO.DRAW_AREA
        return (*self.paper_to_model(x0, y0), *self.paper_to_model(x1, y1))

    def _p(self, p):
        return (self._origin[0] + p[0], self._origin[1] + p[1])

    # ================================================== ابزارهای ترسیم
    # همه مختصات نسبت به مبدأ نمای جاری‌اند؛ در حالت خشک فقط جعبه به‌روز می‌شود.
    def _track(self, pts):
        if self._box is not None:
            for x, y in pts:
                self._box.add(x, y)

    def line(self, p1, p2, layer=LO.LY_CONCRETE):
        a, b = self._p(p1), self._p(p2)
        self._track((a, b))
        if not self._dry:
            self.msp.add_line(a, b, dxfattribs={"layer": layer})

    def polyline(self, pts, layer=LO.LY_CONCRETE, close=False):
        pts = [self._p(p) for p in pts]
        self._track(pts)
        if not self._dry:
            self.msp.add_lwpolyline(pts, close=close, dxfattribs={"layer": layer})

    def rect(self, x, y, w, h, layer=LO.LY_CONCRETE):
        self.polyline([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], layer, close=True)

    def circle(self, p, r, layer=LO.LY_CONCRETE):
        c = self._p(p)
        self._track(((c[0] - r, c[1] - r), (c[0] + r, c[1] + r)))
        if not self._dry:
            self.msp.add_circle(c, r, dxfattribs={"layer": layer})

    def text_width(self, s, h):
        return len(str(s).replace("%%C", "Ø").replace("%%c", "Ø")) * h * self.CHAR_W

    def text(self, p, s, h_paper=LO.H_NORM, layer=LO.LY_TEXT, align="left", rotation=0.0):
        """h_paper ارتفاع متن روی کاغذ است (mm)."""
        h = self.u(h_paper)
        x, y = self._p(p)
        w = self.text_width(s, h)
        if rotation:
            self._track(((x - h, y - w / 2), (x + h * 0.2, y + w / 2)))
        else:
            x0 = x - (w if align.endswith("right") else w / 2 if align.endswith("center") else 0)
            y0 = y - (h / 2 if align.startswith("m") else 0)
            self._track(((x0, y0), (x0 + w, y0 + h)))
        if self._dry:
            return None
        t = self.msp.add_text(str(s), height=h, rotation=rotation,
                              dxfattribs={"layer": layer, "style": self.style})
        t.set_placement((x, y), align=ALIGN[align])
        return t

    def fit_text(self, p, s, h_paper, max_w):
        """اگر متن پهن‌تر از فضای مجاز باشد، ارتفاعش کم می‌شود تا جا شود."""
        w = self.text_width(s, self.u(h_paper))
        if w > max_w > 0:
            h_paper = max(h_paper * 0.6, h_paper * max_w / w)
        return self.text(p, s, h_paper)

    def wrap(self, s, h, max_w):
        """شکستن یک بند طولانی به چند سطر که در عرض مجاز جا شوند."""
        limit = max(10, int(max_w / (h * self.CHAR_W)))
        words, lines, cur = str(s).split(), [], ""
        for wd in words:
            trial = (cur + " " + wd).strip()
            if len(trial) <= limit or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = wd
        if cur:
            lines.append(cur)
        return lines

    def hatch_rect(self, x, y, w, h, step):
        d = -h
        while d < w:
            x1, y1, x2, y2 = x + d, y, x + d + h, y + h
            if x1 < x:
                y1 += (x - x1)
                x1 = x
            if x2 > x + w:
                y2 -= (x2 - (x + w))
                x2 = x + w
            if x2 > x1 and y2 > y1:
                self.line((x1, y1), (x2, y2), LO.LY_HATCH)
            d += step

    def leader(self, target, knee, txt, dx):
        """خط راهنما: از هدف به زانو، بعد افقی به طول dx، و متن در ادامه."""
        end = (knee[0] + dx, knee[1])
        self.line(target, knee, LO.LY_TEXT)
        self.line(knee, end, LO.LY_TEXT)
        gap = self.u(1.0)
        if dx >= 0:
            self.text((end[0] + gap, end[1] - self.u(LO.H_NORM) / 2), txt, LO.H_NORM)
        else:
            self.text((end[0] - gap, end[1] - self.u(LO.H_NORM) / 2), txt, LO.H_NORM,
                      align="right")

    def section_mark(self, p, letter):
        r = self.u(3.2)
        self.circle(p, r, LO.LY_DETAIL)
        self.text(p, letter, LO.H_MARK, align="mcenter")

    # ---------------------------------------------- اندازه‌گذاری
    def _dim(self, p1, p2, base, horizontal, factor=1.0):
        """
        factor: نسبت اندازه واقعی به طول ترسیم؛ برای دیتیلی که با بزرگ‌نمایی
        کشیده شده کمتر از ۱ است تا عدد نوشته‌شده اندازه واقعی باشد.
        """
        a, b = self._p(p1), self._p(p2)
        real = (abs(b[0] - a[0]) if horizontal else abs(b[1] - a[1])) * factor
        label = f"{real:.0f}"
        th = self.u(LO.H_NORM)
        tw = self.text_width(label, th)
        if horizontal:
            by = self._origin[1] + base
            mid = (a[0] + b[0]) / 2
            self._track((a, b, (a[0], by), (b[0], by), (mid - tw / 2, by + th * 1.6)))
        else:
            bx = self._origin[0] + base
            mid = (a[1] + b[1]) / 2
            self._track((a, b, (bx, a[1]), (bx, b[1]), (bx - th * 1.6, mid - tw / 2),
                         (bx, mid + tw / 2)))
        if self._dry:
            return
        if self.simple:
            if horizontal:
                self.msp.add_line((a[0], by), (b[0], by), dxfattribs={"layer": LO.LY_DIM})
                self.msp.add_line(a, (a[0], by), dxfattribs={"layer": LO.LY_DIM})
                self.msp.add_line(b, (b[0], by), dxfattribs={"layer": LO.LY_DIM})
                t = self.msp.add_text(label, height=th, dxfattribs={"layer": LO.LY_DIM,
                                                                    "style": self.style})
                t.set_placement((mid, by + th * 0.4), align=TextEntityAlignment.CENTER)
            else:
                self.msp.add_line((bx, a[1]), (bx, b[1]), dxfattribs={"layer": LO.LY_DIM})
                self.msp.add_line(a, (bx, a[1]), dxfattribs={"layer": LO.LY_DIM})
                self.msp.add_line(b, (bx, b[1]), dxfattribs={"layer": LO.LY_DIM})
                t = self.msp.add_text(label, height=th, rotation=90,
                                      dxfattribs={"layer": LO.LY_DIM, "style": self.style})
                t.set_placement((bx - th * 0.4, mid), align=TextEntityAlignment.CENTER)
            return
        override = {"dimtxt": th, "dimasz": self.u(2.0), "dimexe": self.u(1.5),
                    "dimexo": self.u(1.0), "dimgap": self.u(0.6), "dimdec": 0,
                    "dimlfac": factor}
        if horizontal:
            d = self.msp.add_linear_dim(base=(a[0], by), p1=a, p2=b, dimstyle=self.dimstyle,
                                        override=override, dxfattribs={"layer": LO.LY_DIM})
        else:
            d = self.msp.add_linear_dim(base=(bx, a[1]), p1=a, p2=b, angle=90,
                                        dimstyle=self.dimstyle, override=override,
                                        dxfattribs={"layer": LO.LY_DIM})
        d.render()

    def dim_h(self, p1, p2, y, factor=1.0):
        self._dim(p1, p2, y, True, factor)

    def dim_v(self, p1, p2, x, factor=1.0):
        self._dim(p1, p2, x, False, factor)

    def view_title(self, p, title, scale_txt, h=LO.H_TITLE):
        self.text(p, title, h)
        self.text((p[0], p[1] - self.u(2.4)), scale_txt, LO.H_TINY)

    # ================================================== نماها
    # هر نما نسبت به مبدأ خودش ترسیم می‌شود؛ _layout مبدأ را تعیین می‌کند.
    def _cut_y(self):
        """
        تراز برش A-A: ردیفی که بیشترین ستون را دارد (در تساوی، نزدیک‌ترین به محور پی)،
        تا در پی مشترک چندردیفه برش از وسط ستون‌ها بگذرد نه از فاصله بین ردیف‌ها.
        """
        rows = {}
        for p in self.fm.pedestals:
            rows.setdefault(round(p.y, 1), []).append(p)
        y = max(rows, key=lambda k: (len(rows[k]), -abs(k)))
        return rows[y][0].y

    def _in_cut(self, p, y):
        return abs(p.y - y) <= p.size / 2 + 1e-6

    def _plan(self):
        fm = self.fm
        L, B, lm = fm.L, fm.B, fm.lean_margin
        u = self.u
        self.rect(-L / 2 - lm, -B / 2 - lm, L + 2 * lm, B + 2 * lm, LO.LY_DETAIL)
        self.rect(-L / 2, -B / 2, L, B, LO.LY_CONCRETE)

        # شبکه آرماتور زیرین، از مدل
        for bar in fm.bars_by_mark("01"):
            (x1, y1, _), (x2, y2, _) = bar.points[1], bar.points[2]
            self.line((x1, y1), (x2, y2), LO.LY_REBAR)

        for p in fm.pedestals:
            self.rect(p.x - p.size / 2, p.y - p.size / 2, p.size, p.size, LO.LY_CONCRETE)
        for a in fm.anchors:
            r = a.dia / 2
            self.circle((a.x, a.y), r, LO.LY_DETAIL)
            self.line((a.x - 2.2 * r, a.y), (a.x + 2.2 * r, a.y), LO.LY_DIM)
            self.line((a.x, a.y - 2.2 * r), (a.x, a.y + 2.2 * r), LO.LY_DIM)

        # زنجیره اندازه محور ستون‌ها (پی چندستونه) و اندازه کلی
        xs = sorted({round(p.x, 3) for p in fm.pedestals})
        ys = sorted({round(p.y, 3) for p in fm.pedestals})
        chain_x = len(xs) > 1 or abs(xs[0]) > 1e-6
        chain_y = len(ys) > 1 or abs(ys[0]) > 1e-6
        yb = -B / 2 - lm - u(8)
        if chain_x:
            pts = [-L / 2] + xs + [L / 2]
            for a, b in zip(pts, pts[1:]):
                if b - a > 1:
                    self.dim_h((a, -B / 2), (b, -B / 2), yb)
            yb -= u(7)
        self.dim_h((-L / 2, -B / 2), (L / 2, -B / 2), yb)
        xr = L / 2 + lm + u(8)
        if chain_y:
            pts = [-B / 2] + ys + [B / 2]
            for a, b in zip(pts, pts[1:]):
                if b - a > 1:
                    self.dim_v((L / 2, a), (L / 2, b), xr)
            xr += u(7)
        self.dim_v((L / 2, -B / 2), (L / 2, B / 2), xr)

        # نام تجهیز هر گروه، در پی مشترک با بیش از یک تجهیز
        tags = {}
        for p in fm.pedestals:
            tags.setdefault(p.group, []).append(p)
        if len(tags) > 1:
            for peds in tags.values():
                p = min(peds, key=lambda q: (q.x, q.y))
                self.text((p.x - p.size / 2, p.y + p.size / 2 + u(1.5)), p.tag, LO.H_TINY)

        # خط برش A-A از محور ردیف اصلی ستون‌ها
        yc = self._cut_y()
        ext = lm + u(2)
        self.line((-L / 2 - ext, yc), (L / 2 + ext, yc), LO.LY_DIM)
        self.section_mark((-L / 2 - ext - u(3.2), yc), "A")
        self.section_mark((L / 2 + ext + u(3.2), yc), "A")

        pad = self.des["pad"]
        top_bar = max((b.points[1][1] for b in fm.bars_by_mark("01")), default=0)
        self.leader((L * 0.12, top_bar), (-L * 0.08, B / 2 + lm + u(5)),
                    f"{pad.bar_count}%%C{pad.bar_dia}@{pad.spacing:.0f}  T&B  E.W.", u(4))
        self.view_title((-L / 2, yb - u(7)), "PLAN", f"Sc.1:{self.s:.0f}")

    def _section_a(self):
        fm = self.fm
        L, lm, tf, top, lean = fm.L, fm.lean_margin, fm.tf, fm.top, fm.lean
        u = self.u
        hw = u(12)                                   # عرض نمایش خاک دو طرف
        gl = top - fm.soil_cover                     # تراز زمین تمام‌شده

        self.hatch_rect(-L / 2 - lm - hw, -lean, hw, gl + lean, u(7.5))
        self.hatch_rect(L / 2 + lm, -lean, hw, gl + lean, u(7.5))
        self.rect(-L / 2 - lm, -lean, L + 2 * lm, lean, LO.LY_DETAIL)
        self.rect(-L / 2, 0, L, tf, LO.LY_CONCRETE)
        yc = self._cut_y()
        cut = [p for p in fm.pedestals if self._in_cut(p, yc)]
        for p in cut:
            self.rect(p.x - p.size / 2, tf, p.size, fm.hp, LO.LY_CONCRETE)
        self.line((-L / 2 - lm - hw, gl), (L / 2 + lm + hw, gl), LO.LY_DETAIL)
        self.text((-L / 2 - lm - hw, gl + u(1)), "F.S.L.", LO.H_TINY)
        self.text((-L / 2 - lm - hw, top + u(1)), "F.B.L.", LO.H_TINY)

        # آرماتور پی: میلگرد راستای x نزدیک صفحه برش کامل، راستای y به صورت نقطه
        for mark in ("01", "03"):
            bars = fm.bars_by_mark(mark)
            along_x = [b for b in bars if abs(b.points[1][0] - b.points[2][0]) > 1]
            along_y = [b for b in bars if abs(b.points[1][0] - b.points[2][0]) <= 1]
            if along_x:
                near = min(along_x, key=lambda b: abs(b.points[1][1] - yc))
                self.polyline([(x, z) for x, _, z in near.points], LO.LY_REBAR)
            for b in along_y:
                self.circle((b.points[1][0], b.points[1][2]), b.dia / 2, LO.LY_REBAR)

        # ستون: میلگردهای طولی دو وجه، خاموت‌ها و میل مهارها
        for p in cut:
            verts = [b for b in fm.bars_by_mark("02")
                     if abs(b.points[1][0] - p.x) <= p.size / 2
                     and abs(b.points[1][1] - p.y) <= p.size / 2]
            xs = sorted({round(b.points[1][0], 3) for b in verts})
            for x in (xs[0], xs[-1]) if xs else ():
                bar = next(b for b in verts if round(b.points[1][0], 3) == x)
                self.polyline([(px, pz) for px, _, pz in bar.points], LO.LY_REBAR)
            for t in fm.bars_by_mark("05"):
                if (abs(t.points[0][0] + t.points[1][0] - 2 * p.x) < 1
                        and abs(t.points[0][1] + t.points[2][1] - 2 * p.y) < 1):
                    self.line((t.points[0][0], t.points[0][2]), (t.points[1][0], t.points[1][2]),
                              LO.LY_REBAR)
        cut_anchors = [a for a in fm.anchors if any(
            abs(a.x - p.x) <= p.size / 2 and abs(a.y - p.y) <= p.size / 2 for p in cut)]
        for x in sorted({a.x for a in cut_anchors}):
            a = next(a for a in cut_anchors if a.x == x)
            self.line((a.x, a.z_bottom), (a.x, a.z_top), LO.LY_DETAIL)

        # برش B-B از میانه ستون‌ها
        zc = tf + fm.hp * 0.45
        xl = min(p.x - p.size / 2 for p in cut) - u(2)
        xr = max(p.x + p.size / 2 for p in cut) + u(2)
        self.line((xl, zc), (xr, zc), LO.LY_DIM)
        self.section_mark((xl - u(3.2), zc), "B")
        self.section_mark((xr + u(3.2), zc), "B")

        # برچسب‌ها
        p0, p1 = cut[0], cut[-1]
        groups = self.des.get("groups") or [{"pedestal": self.des["pedestal"]}]
        ped, pad = groups[min(p0.group, len(groups) - 1)]["pedestal"], self.des["pad"]
        r = self.cfg.rebar
        core = p0.size / 2 - fm.cover
        self.leader((p0.x - core, gl - u(4)), (p0.x - p0.size / 2 - u(8), top + u(6)),
                    f"{ped.bar_count}%%C{ped.bar_dia}", -u(4))
        self.leader((p1.x + core, tf + M.TIE_START + r.tie_spacing),
                    (p1.x + p1.size / 2 + u(8), top + u(6)),
                    f"%%C{r.tie_dia}@{r.tie_spacing:.0f}", u(4))
        self.leader((-L * 0.3, fm.cover), (-L * 0.25, -lean - u(13)),
                    f"{pad.bar_count}%%C{pad.bar_dia}@{pad.spacing:.0f}", -u(4))
        self.leader((L * 0.3, -lean / 2), (L * 0.25, -lean - u(13)), "LEAN CONCRETE", u(4))
        self.text((L / 2 + lm + u(1), -lean - u(3.5)), "COMPACTED SOIL", LO.H_TINY)

        self.dim_v((-L / 2, 0), (-L / 2, tf), -L / 2 - lm - hw - u(3))
        self.dim_v((-L / 2, tf), (-L / 2, top), -L / 2 - lm - hw - u(3))
        self.dim_h((-L / 2, 0), (L / 2, 0), -lean - u(6))
        self.view_title((-L / 2, -lean - u(21)), "SECTION A-A", f"Sc.1:{self.s:.0f}")

    def _section_b(self):
        fm = self.fm
        p = fm.pedestals[0]
        b, u = p.size, self.u
        ped = self.des["pedestal"]
        r = self.cfg.rebar
        self.rect(-b / 2, -b / 2, b, b, LO.LY_CONCRETE)
        tie = next((t for t in fm.bars_by_mark("05")
                    if abs(t.points[0][0] + t.points[1][0] - 2 * p.x) < 1
                    and abs(t.points[0][1] + t.points[2][1] - 2 * p.y) < 1), None)
        if tie:
            self.polyline([(x - p.x, y - p.y) for x, y, _ in tie.points], LO.LY_REBAR, close=True)
        for bar in fm.bars_by_mark("02"):
            x, y = bar.points[1][0] - p.x, bar.points[1][1] - p.y
            if abs(x) <= b / 2 and abs(y) <= b / 2:
                self.circle((x, y), bar.dia / 2, LO.LY_REBAR)
        for a in fm.anchors:
            if abs(a.x - p.x) <= b / 2 and abs(a.y - p.y) <= b / 2:
                self.circle((a.x - p.x, a.y - p.y), a.dia / 2, LO.LY_DETAIL)

        core = b / 2 - fm.cover
        self.leader((-core, core * 0.4), (-b / 2 - u(8), b / 2 + u(2)),
                    f"{ped.bar_count}%%C{ped.bar_dia}", -u(4))
        self.leader((-core - ped.bar_dia, -core * 0.3), (-b / 2 - u(8), -b / 2 + u(2)),
                    f"%%C{r.tie_dia}@{r.tie_spacing:.0f}", -u(4))
        self.dim_h((-b / 2, -b / 2), (b / 2, -b / 2), -b / 2 - u(7))
        self.view_title((-b / 2, -b / 2 - u(15)), "SECTION B-B", f"Sc.1:{self.s:.0f}")

    def hatch_pattern(self, pts, pattern="AR-CONC", scale=1.0, layer=LO.LY_HATCH):
        """هاشور الگودار (مثل AR-CONC برای گروت)؛ الگو در خود اتوکد هم شناخته‌شده است."""
        pts = [self._p(p) for p in pts]
        self._track(pts)
        if self._dry:
            return
        h = self.msp.add_hatch(dxfattribs={"layer": layer})
        h.paths.add_polyline_path(pts, is_closed=True)
        h.set_pattern_fill(pattern, scale=scale)

    def spline(self, pts, layer=LO.LY_CONCRETE):
        pts = [self._p(p) for p in pts]
        self._track(pts)
        if not self._dry:
            self.msp.add_spline(fit_points=[(x, y, 0) for x, y in pts],
                                dxfattribs={"layer": layer})

    def nut(self, cx, y, w, h, layer=LO.LY_DETAIL):
        """مهره شش‌گوش از نمای کنار: مستطیل با دو خط وجه."""
        self.rect(cx - w / 2, y, w, h, layer)
        for f in (-0.22, 0.22):
            self.line((cx + f * w, y), (cx + f * w, y + h), layer)

    def _detail_anchor(self):
        """
        دیتیل میل مهار، مطابق دیتیل استاندارد دفتر (نقشه 08-CT):
        میلگرد بدنه (Ф22 برای M20) تا طول مدفون محاسبه‌شده، گروت ۵۰ هاشورخورده با
        پخ ۴۵ درجه و خط شکست موجی، مهره تراز زیر صفحه داخل گروت، صفحه کف، واشر و
        دو مهره، رزوه از سر میل مهار تا زیر گروت. اندازه‌ها: گروت و بالای گروت روی
        خط داخلی، بیرون‌زدگی کل و طول مدفون روی خط بیرونی.
        """
        eq, fm, u = self.eq, self.fm, self.u
        an = self.cfg.anchorage
        k = self.s / self.cfg.drawing.detail_scale
        d = eq.anchor_dia * k                           # قطر رزوه
        rod = (an.rod_dia or eq.anchor_dia + 2) * k     # قطر میلگرد بدنه
        r = rod / 2
        emb, gr = fm.anchor_embed * k, fm.grout * k
        pt, proj = fm.plate_t * k, fm.anchor_projection * k
        left, right = -100 * k, 100 * k                 # محدوده نمایش گروت
        plate_r = 50 * k
        nut_w, nut_h = 1.7 * d, 0.8 * d

        # گروت با پخ ۴۵ درجه و هاشور بتنی
        grout = [(left, 0), (right + gr, 0), (right, gr), (left, gr)]
        self.polyline(grout, LO.LY_DETAIL, close=True)
        self.hatch_pattern(grout, "AR-CONC", scale=k * 0.25)
        # مهره تراز زیر صفحه (داخل گروت)
        self.nut(0, gr - nut_h, nut_w, nut_h)
        # صفحه کف، واشر، دو مهره
        self.rect(left, gr, plate_r - left, pt, LO.LY_DETAIL)
        y = gr + pt
        washer = 4 * k
        self.rect(-1.25 * d, y, 2.5 * d, washer, LO.LY_DETAIL)
        y += washer
        for _ in range(2):
            self.nut(0, y, nut_w, nut_h)
            y += nut_h
        # خط شکست موجی سمت چپ
        wv = u(1.2)
        y0, y1 = -u(2.5), gr + pt + u(2.5)
        self.spline([(left + wv * dx, y0 + (y1 - y0) * t) for t, dx in
                     ((0, 0), (0.2, 0.9), (0.4, -0.3), (0.6, 0.9), (0.8, -0.3), (1, 0.5))],
                    LO.LY_CONCRETE)

        # میل مهار: بدنه صاف تا طول مدفون (قلاب فقط اگر در تنظیمات داده شده باشد)
        hook = fm.anchor_hook * eq.anchor_dia * k
        self.line((-r, proj), (r, proj), LO.LY_DETAIL)
        self.line((-r, proj), (-r, -emb), LO.LY_DETAIL)
        if hook > 0:
            self.line((r, proj), (r, -emb + rod), LO.LY_DETAIL)
            self.polyline([(-r, -emb), (hook, -emb), (hook, -emb + rod), (r, -emb + rod)],
                          LO.LY_DETAIL)
        else:
            self.line((r, proj), (r, -emb), LO.LY_DETAIL)
            self.line((-r, -emb), (r, -emb), LO.LY_DETAIL)
        # رزوه (قرمز): بالای مهره‌ها تا سر میل مهار، و زیر مهره تراز تا زیر گروت
        for y_a, y_b in ((y, proj), (0, gr - nut_h)):
            t, step = y_a, u(0.45)
            while t + step * 0.6 <= y_b:
                self.line((-r, t), (r, t + step * 0.6), LO.LY_CONCRETE)
                t += step

        # اندازه‌ها
        f = 1 / k
        x1 = right + gr + u(4)
        x2 = x1 + u(9)
        self.dim_v((right + gr, 0), (right + gr, gr), x1, factor=f)
        self.dim_v((r, gr), (r, proj), x1, factor=f)
        self.dim_v((r, 0), (r, proj), x2, factor=f)
        self.dim_v((r, -emb), (r, 0), x2, factor=f)

        # برچسب‌ها مثل دیتیل دفتر
        self.leader((-r, proj - u(1)), (-r - u(6), proj + u(6)), f"M{eq.anchor_dia:.0f}", -u(6))
        self.leader((left + u(3), gr * 0.4), (left - u(4), gr * 0.4 - u(2)), "GROUT", -u(5))
        self.leader((r, -emb * 0.3), (r + u(10), -emb * 0.3), f"%%C{rod / k:.0f}", u(4))

        self.text((left, -emb - u(8)), "ANCHOR BOLT", LO.H_BIG)
        self.text((left, -emb - u(8) - u(3.2)), f"Sc.1:{self.cfg.drawing.detail_scale:.0f}",
                  LO.H_TINY)

    # ================================================== چیدمان
    def _measure(self, fn):
        self._dry, self._origin, self._box = True, (0.0, 0.0), Box()
        fn()
        box, self._dry, self._box = self._box, False, None
        return box

    def _draw_at(self, name, fn, origin):
        self._origin, self._box = origin, Box()
        fn()
        self.view_boxes[name] = self._box
        self._box, self._origin = None, (0.0, 0.0)

    def _layout(self):
        """
        کوچک‌ترین مقیاس مجاز که در آن پلان و مقطع A (ستون چپ، هم‌محور) و
        مقطع B و دیتیل (ستون میانی) در کنار ستون لیست آرماتور جا شوند.
        """
        x_lo, y_lo, _, y_hi = LO.DRAW_AREA
        x0, y0, y1 = x_lo + LO.MARGIN, y_lo + LO.MARGIN, y_hi - LO.MARGIN
        preferred = float(self.cfg.drawing.scale)
        scales = [s for s in LO.SCALES if s >= preferred] or [preferred]
        if preferred not in scales:
            scales.insert(0, preferred)
        for s in scales:
            self.s = s
            P, A = self._measure(self._plan), self._measure(self._section_a)
            S, D = self._measure(self._section_b), self._measure(self._detail_anchor)
            to_p = 1 / s
            left_l = max(-P.x0, -A.x0) * to_p
            left_r = max(P.x1, A.x1) * to_p
            w_left = left_l + left_r
            h_left = (P.h + A.h) * to_p + LO.GAP
            w_mid = max(S.w, D.w) * to_p
            h_mid = (S.h + D.h) * to_p + LO.GAP
            fits = (x0 + w_left + LO.GAP + w_mid + LO.GAP <= LO.RIGHT_COLUMN_X
                    and h_left <= y1 - y0 and h_mid <= y1 - y0)
            if fits:
                break
        if not fits:
            print(f"   ⚠ نماها حتی در مقیاس ۱:{self.s:.0f} در کادر جا نشدند")

        # ستون چپ: پلان بالا، مقطع A پایین، هر دو روی یک محور
        cx = x0 + left_l
        plan_o = self.paper_to_model(cx, y1 - P.y1 * to_p)
        sec_o = self.paper_to_model(cx, y0 - A.y0 * to_p)
        # ستون میانی: وسط فضای باقی‌مانده بین ستون چپ و ستون راست
        mx0 = x0 + w_left + LO.GAP
        mw = LO.RIGHT_COLUMN_X - LO.GAP - mx0
        sb_o = self.paper_to_model(mx0 + (mw - S.w * to_p) / 2 - S.x0 * to_p, y1 - S.y1 * to_p)
        det_o = self.paper_to_model(mx0 + (mw - D.w * to_p) / 2 - D.x0 * to_p,
                                    y0 - D.y0 * to_p)
        return {"plan": plan_o, "section_a": sec_o, "section_b": sb_o, "detail": det_o}

    # ================================================== کادر
    def insert_frame(self):
        """
        کادر A3 شرکت. در فایل کادر بلاکی به نام Frame نیست — کادر در
        مدل‌اسپیس همان فایل است و در نقشه اصلی XREF می‌شد. اینجا محتوای
        مدل‌اسپیس داخل یک بلاک تازه ریخته و همان بلاک درج می‌شود.
        """
        path = self.cfg.drawing.frame_file
        if not path or not os.path.exists(path):
            print(f"   (کادر {path} پیدا نشد — نقشه بدون کادر ساخته شد)")
            return
        try:
            src = ezdxf.readfile(path)
            self._strip_fields(src)
            from ezdxf.addons import Importer
            imp = Importer(src, self.doc)
            imp.import_table("layers", entries=[e.dxf.name for e in src.layers if _valid(e.dxf.name)])
            imp.import_table("styles", entries=[e.dxf.name for e in src.styles if _valid(e.dxf.name)])
            names = [b.name for b in src.blocks
                     if _valid(b.name) and not b.name.startswith("*")]
            imp.import_blocks(names)
            if LO.FRAME_BLOCK in self.doc.blocks:
                self.doc.blocks.delete_block(LO.FRAME_BLOCK, safe=False)
            blk = self.doc.blocks.new(LO.FRAME_BLOCK)
            skip = {"VIEWPORT", "OLE2FRAME", "ATTRIB", "SEQEND"}
            body = [e for e in src.modelspace() if e.dxftype() not in skip]
            imp.import_entities(body, target_layout=blk)
            imp.finalize()
            self._purge_invalid()
        except Exception as exc:
            print(f"   (کادر وارد نشد: {exc})")
            return

        ref = self.msp.add_blockref(LO.FRAME_BLOCK, LO.FRAME_INSERT,
                                    dxfattribs={"xscale": self.s, "yscale": self.s,
                                                "layer": LO.LY_DETAIL})
        self._excluded.add(ref.dxf.handle)
        self._fill_title_block()

    @staticmethod
    def _strip_fields(src):
        """
        ATTDEF های BLOCK2 کادر به FIELD اتوکد وصل‌اند. Importer نمی‌تواند FIELD را
        کپی کند و ارجاع بی‌صاحب در فایل خروجی می‌ماند؛ پس ارجاع قبل از کپی قطع
        می‌شود و فقط متن ذخیره‌شده (مثل ####) باقی می‌ماند.
        """
        for blk in src.blocks:
            for e in blk:
                if e.has_extension_dict and "ACAD_FIELD" in e.get_extension_dict():
                    e.discard_extension_dict()

    def _fill_title_block(self):
        """مقادیر جدول عنوان روی مختصات استاندارد کادر (layout.TITLE_FIELDS)."""
        fields = dict(self.cfg.title_block.fields)
        fields["SCALE"] = f"1/{self.s:.0f}"
        align = {0: TextEntityAlignment.MIDDLE_LEFT, 1: TextEntityAlignment.MIDDLE_CENTER,
                 2: TextEntityAlignment.MIDDLE_RIGHT}
        unknown = []
        for tag, val in fields.items():
            val = str(val).strip()
            if not val:
                continue
            spec = LO.TITLE_FIELDS.get(tag)
            if spec is None:
                unknown.append(tag)
                continue
            fx, fy, fh, ha = spec
            t = self.msp.add_text(val, height=fh * self.s,
                                  dxfattribs={"layer": LO.LY_TEXT, "style": self.style})
            t.set_placement(self.paper_to_model(fx, fy),
                            align=align.get(ha, TextEntityAlignment.MIDDLE_LEFT))
            self._excluded.add(t.dxf.handle)
        if unknown:
            print(f"   (فیلدهای ناشناخته جدول عنوان نادیده گرفته شد: {', '.join(unknown)})")

    # ================================================== ستون راست
    def _right_column(self, bbs, qty, soil, seismic):
        """لیست آرماتور، جمع‌بندی و یادداشت‌ها، پشت سر هم از بالا به پایین."""
        self._origin, self._box = (0.0, 0.0), Box()
        x_lo, y_lo, x_hi, y_hi = LO.DRAW_AREA
        ox = LO.RIGHT_COLUMN_X
        avail = x_hi - LO.MARGIN - ox
        P = self.paper_to_model
        u = self.u
        y = y_hi - LO.MARGIN - LO.H_SUMMARY

        # --- لیست آرماتور
        self.text(P(ox + avail / 2, y), "BAR BENDING SCHEDULE", LO.H_SUMMARY, align="center")
        y -= 7.0
        pos, acc = {}, 0.0
        for key, frac in LO.BBS_COL_SHARE:
            pos[key] = ox + acc * avail
            acc += frac
        width = {key: u(frac * avail - 2) for key, frac in LO.BBS_COL_SHARE}
        head = {"pos": ("POS.", ""), "shape": ("BENDING DIAGRAM", ""),
                "dia": ("%%c", "mm"), "no": ("NO", "RQD."),
                "length": ("LENGTH", "m"), "total": ("TOTAL", "m"),
                "unit_w": ("UNIT WEIGHT", "kg/m"), "weight": ("TOTAL WEIGHT", "kg")}
        for key, (l1, l2) in head.items():
            self.fit_text(P(pos[key], y), l1, LO.H_TABLE, width[key])
            if l2:
                self.fit_text(P(pos[key], y - LO.H_TABLE * 1.5), l2, LO.H_TABLE, width[key])
        y -= LO.H_TABLE * 1.5 + 3.5
        self.line(P(ox - 2.5, y), P(ox + avail, y), LO.LY_DETAIL)
        y -= LO.BBS_ROW_H * 0.8
        for row in bbs:
            cells = {"pos": row["pos"], "shape": row["shape"], "dia": row["dia"],
                     "no": row["no"], "length": f"{row['length']:.2f}",
                     "total": f"{row['total']:.1f}", "unit_w": f"{row['unit_w']:.3f}",
                     "weight": f"{row['weight']:.2f}"}
            for key, val in cells.items():
                self.fit_text(P(pos[key], y), val, LO.H_TABLE, width[key])
            y -= LO.BBS_ROW_H
        y += LO.BBS_ROW_H - 3.0
        self.line(P(ox - 2.5, y), P(ox + avail, y), LO.LY_DETAIL)

        # --- جمع‌بندی
        y -= LO.SUMMARY_ROW_H
        for lab, val in (("TOTAL WEIGHT", f"{qty['rebar']:.2f} Kg"),
                         ("CONCRETE VOL.", f"{qty['concrete']:.2f} m3"),
                         ("LEAN CON. VOL.", f"{qty['lean']:.3f} m3")):
            self.text(P(ox + 2, y), lab, LO.H_SUMMARY)
            self.text(P(ox + 2 + LO.SUMMARY_VALUE_DX, y), val, LO.H_SUMMARY)
            y -= LO.SUMMARY_ROW_H
        y += LO.SUMMARY_ROW_H - 4.5
        for ln in self.wrap("BAR BENDING IS ONLY FOR INFORMATION AND SHOULD BE CHECKED "
                            "BEFORE CONST.", u(LO.H_NOTE), u(avail)):
            self.text(P(ox, y), ln, LO.H_NOTE)
            y -= LO.NOTES_ROW_H

        # --- یادداشت‌ها
        y -= 5.0
        self._notes(P, ox, y, avail, soil, seismic)
        self.view_boxes["right"] = self._box
        self._box = None

    def _notes(self, P, ox, y, avail, soil, seismic):
        path = self.cfg.drawing.notes_file
        m = self.cfg.materials
        subst = {"fc": m.fc, "fy": m.fy, "cover": m.cover, "lean": m.lean,
                 "q_all": f"{soil.q_all:.2f}",
                 "seismic": f"{seismic.ch:.3f}/{seismic.cv:.3f}",
                 "edition": seismic.edition}
        try:
            with open(path, encoding="utf-8") as fh:
                raw_lines = [ln.rstrip() for ln in fh
                             if ln.strip() and not ln.lstrip().startswith("#")]
        except FileNotFoundError:
            print(f"   (فایل یادداشت {path} نبود — بخش NOTE خالی ماند)")
            return
        self.text(P(ox, y), "NOTE:", LO.H_SUMMARY)
        y -= LO.NOTES_ROW_H * 2
        for raw in raw_lines:
            try:
                txt = raw.format(**subst)
            except (KeyError, IndexError, ValueError):
                txt = raw
            base = LO.NOTES_INDENT if raw.startswith((" ", "\t")) else 0
            for k, ln in enumerate(self.wrap(txt.strip(), self.u(LO.H_NOTE),
                                             self.u(avail - base))):
                indent = base + (LO.NOTES_INDENT if k else 0)
                self.text(P(ox + indent, y), ln, LO.H_NOTE)
                y -= LO.NOTES_ROW_H

    # ================================================== ساخت نقشه
    def build(self, res, eq, soil, qty, bbs, seismic, des):
        self.des, self.eq = des, eq
        self.fm = M.build(res, getattr(res, "layout", eq), des, self.cfg)
        origins = self._layout()
        self.insert_frame()
        self._draw_at("plan", self._plan, origins["plan"])
        self._draw_at("section_a", self._section_a, origins["section_a"])
        self._draw_at("section_b", self._section_b, origins["section_b"])
        self._draw_at("detail", self._detail_anchor, origins["detail"])
        self._right_column(bbs, qty, soil, seismic)
        self._fit_view()
        self.check_bounds()
        return self

    def _fit_view(self):
        w, h = LO.FRAME_SIZE[0] * self.s, LO.FRAME_SIZE[1] * self.s
        cx, cy = LO.FRAME_INSERT[0] + w / 2, LO.FRAME_INSERT[1] + h / 2
        self.doc.set_modelspace_vport(height=h * 1.05, center=(cx, cy))

    def _entity_points(self, e):
        t = e.dxftype()
        if t == "LINE":
            return [e.dxf.start, e.dxf.end]
        if t == "LWPOLYLINE":
            return list(e.get_points("xy"))
        if t == "CIRCLE":
            c, r = e.dxf.center, e.dxf.radius
            return [(c.x - r, c.y - r), (c.x + r, c.y + r)]
        if t == "TEXT":
            h = e.dxf.height
            w = self.text_width(e.dxf.text, h)
            p = e.dxf.align_point if e.dxf.halign or e.dxf.valign else e.dxf.insert
            if e.dxf.rotation:
                return [(p.x - h, p.y - w / 2), (p.x + h, p.y + w / 2)]
            x0 = p.x - (w if e.dxf.halign == 2 else w / 2 if e.dxf.halign in (1, 4) else 0)
            return [(x0, p.y - h / 2), (x0 + w, p.y + h)]
        if t == "DIMENSION":
            return [p for p in (e.dxf.get("defpoint"), e.dxf.get("defpoint2"),
                                e.dxf.get("defpoint3"), e.dxf.get("text_midpoint")) if p]
        return []

    def check_bounds(self):
        """
        بعد از ساخت نقشه: هر موجودیتی که بیرون ناحیه ترسیم افتاده باشد، و هر دو
        نمایی که روی هم افتاده باشند، گزارش می‌شوند.
        """
        lo_x, lo_y, hi_x, hi_y = self.sheet_bounds()
        self.outside = []
        for e in self.msp:
            if e.dxf.handle in self._excluded:
                continue
            for p in self._entity_points(e):
                x, y = p[0], p[1]
                if not (lo_x - 1e-6 <= x <= hi_x + 1e-6 and lo_y - 1e-6 <= y <= hi_y + 1e-6):
                    label = getattr(e.dxf, "text", e.dxftype())
                    self.outside.append(f"{str(label)[:28]} @ ({x:.0f},{y:.0f})")
                    break
        names = list(self.view_boxes)
        self.overlaps = [(a, b) for i, a in enumerate(names) for b in names[i + 1:]
                         if self.view_boxes[a].overlaps(self.view_boxes[b])]
        if self.outside:
            print(f"   ⚠ {len(self.outside)} مورد بیرون از کادر:")
            for item in self.outside[:12]:
                print("      ", item)
        for a, b in self.overlaps:
            print(f"   ⚠ نمای {a} و {b} روی هم افتاده‌اند")
        if not self.outside and not self.overlaps:
            print(f"   همه‌چیز داخل کادر است، بدون هم‌پوشانی (مقیاس ۱:{self.s:.0f}).")
        return self.outside

    def save(self, path):
        self.doc.saveas(path)
        return path
