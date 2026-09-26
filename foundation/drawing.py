"""
تولید نقشه فونداسیون روی چیدمان و کادر شرکت.

ساختار شیت دقیقاً از نقشه واقعی 06-4LA_C برداشته شده است (فایل layout.py):
    PLAN · SECTION A-A · SECTION B-B · DET."1" ANCHOR BOLT
    BAR BENDING SCHEDULE · NOTES · کادر و جدول عنوان

کادر از FRAME.dxf به صورت بلاک وارد می‌شود — نه XREF — تا فایل خروجی خودکفا
باشد و برای باز شدن به فایل دیگری نیاز نداشته باشد.

نکته‌ای که دو بار به آن خوردیم: نام‌های خالی یا دارای | در جدول‌های نماد،
باعث می‌شوند اتوکد کل فایل را با پیام «Invalid symbol table record name»
دور بیندازد. همه‌شان فیلتر می‌شوند.
"""
import os
import ezdxf
from ezdxf.enums import TextEntityAlignment
import layout as LO


def _valid(name) -> bool:
    n = str(name or "").strip()
    return bool(n) and "|" not in n


class FoundationDrawing:
    def __init__(self, cfg, simple=False):
        self.cfg = cfg
        self.simple = simple
        self.doc = ezdxf.new(cfg.drawing.dxf_version, setup=True)
        self.doc.header["$INSUNITS"] = 4
        self.msp = self.doc.modelspace()
        self.style = "Standard"
        self.dimstyle = "Standard"
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

    # ================================================== کادر
    def insert_frame(self):
        """
        کادر A3 شرکت.

        در FRAME.dxf بلاکی به نام Frame وجود ندارد — کادر در مدل‌اسپیس همان
        فایل است و در نقشه اصلی به صورت XREF درج می‌شد. اینجا محتوای
        مدل‌اسپیس داخل یک بلاک تازه ریخته و همان بلاک درج می‌شود، تا فایل
        خروجی خودکفا باشد و به فایل بیرونی نیاز نداشته باشد.
        """
        path = self.cfg.drawing.frame_file
        if not path or not os.path.exists(path):
            print(f"   (کادر {path} پیدا نشد — نقشه بدون کادر ساخته شد)")
            return
        try:
            src = ezdxf.readfile(path)
            from ezdxf.addons import Importer
            imp = Importer(src, self.doc)

            # منابع لازم کادر
            imp.import_table("layers", entries=[e.dxf.name for e in src.layers if _valid(e.dxf.name)])
            imp.import_table("styles", entries=[e.dxf.name for e in src.styles if _valid(e.dxf.name)])
            names = [b.name for b in src.blocks
                     if _valid(b.name) and not b.name.startswith("*")]
            imp.import_blocks(names)

            # محتوای کادر → یک بلاک تازه
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

        s = self.cfg.drawing.scale
        self.msp.add_blockref(LO.FRAME_BLOCK, LO.FRAME_INSERT,
                              dxfattribs={"xscale": s, "yscale": s, "layer": LO.LY_DETAIL})
        self._fill_title_block(s)

    def _fill_title_block(self, scale):
        """
        مقادیر جدول عنوان روی مختصات استاندارد کادر نوشته می‌شوند.
        کادر خالی است و ATTRIB ندارد، پس موقعیت‌ها از layout.TITLE_FIELDS
        می‌آیند که یک‌بار از کادر اصلی شرکت استخراج شده‌اند.
        """
        values = {k: str(v).strip() for k, v in self.cfg.title_block.fields.items()
                  if str(v).strip()}
        if not values:
            return
        ox, oy = LO.FRAME_INSERT
        align = {0: TextEntityAlignment.MIDDLE_LEFT,
                 1: TextEntityAlignment.MIDDLE_CENTER,
                 2: TextEntityAlignment.MIDDLE_RIGHT}
        unknown = []
        for tag, val in values.items():
            spec = LO.TITLE_FIELDS.get(tag)
            if spec is None:
                unknown.append(tag)
                continue
            fx, fy, fh, ha = spec
            t = self.msp.add_text(val, height=fh * scale,
                                  dxfattribs={"layer": LO.LY_TEXT, "style": self.style})
            t.set_placement((ox + fx * scale, oy + fy * scale),
                            align=align.get(ha, TextEntityAlignment.MIDDLE_LEFT))
        if unknown:
            print(f"   (فیلدهای ناشناخته جدول عنوان نادیده گرفته شد: {', '.join(unknown)})")

    # ================================================== ابزارها
    def line(self, p1, p2, layer=LO.LY_CONCRETE):
        self.msp.add_line(p1, p2, dxfattribs={"layer": layer})

    def rect(self, x, y, w, h, layer=LO.LY_CONCRETE):
        self.msp.add_lwpolyline([(x, y), (x + w, y), (x + w, y + h), (x, y + h)],
                                close=True, dxfattribs={"layer": layer})

    def text(self, p, s, h=LO.H_NORM, layer=LO.LY_TEXT):
        t = self.msp.add_text(str(s), height=h,
                              dxfattribs={"layer": layer, "style": self.style})
        t.set_placement(p, align=TextEntityAlignment.LEFT)
        return t

    # نسبت عرض به ارتفاع حروف در فونت ROMANC.
    # از روی نقشه 06-4LA_C اندازه‌گیری شد: بلندترین بند ۶۱ حرف با ارتفاع ۳۱٫۱
    # تا لبه ناحیه ترسیم می‌رسد، یعنی ضریب واقعی حدود ۰٫۷۸.
    # با حاشیه اطمینان ۰٫۸۵ گرفته شده تا هیچ متنی از کادر نزند بیرون.
    CHAR_W = 0.85

    def text_width(self, s, h):
        return len(str(s)) * h * self.CHAR_W

    def fit_text(self, p, s, h, max_w, layer=LO.LY_TEXT):
        """اگر متن پهن‌تر از فضای مجاز باشد، ارتفاعش کم می‌شود تا جا شود."""
        w = self.text_width(s, h)
        if w > max_w > 0:
            h = max(h * 0.6, h * max_w / w)
        return self.text(p, s, h, layer)

    def wrap(self, s, h, max_w):
        """شکستن یک بند طولانی به چند سطر که در عرض مجاز جا شوند."""
        limit = max(10, int(max_w / (h * self.CHAR_W)))
        words, lines, cur = str(s).split(), [], ""
        for wd in words:
            trial = (cur + " " + wd).strip()
            if len(trial) <= limit or not cur:
                cur = trial
            else:
                lines.append(cur); cur = wd
        if cur:
            lines.append(cur)
        return lines

    def circle(self, p, r, layer=LO.LY_CONCRETE):
        self.msp.add_circle(p, r, dxfattribs={"layer": layer})

    def dim_h(self, p1, p2, y):
        if self.simple:
            return self._plain_dim(p1, p2, y, True)
        d = self.msp.add_linear_dim(base=(p1[0], y), p1=p1, p2=p2,
                                    dimstyle=self.dimstyle,
                                    override={"dimtxt": LO.H_NORM, "dimasz": 40,
                                              "dimexe": 30, "dimexo": 20, "dimdec": 0},
                                    dxfattribs={"layer": LO.LY_DIM})
        d.render()

    def dim_v(self, p1, p2, x):
        if self.simple:
            return self._plain_dim(p1, p2, x, False)
        d = self.msp.add_linear_dim(base=(x, p1[1]), p1=p1, p2=p2, angle=90,
                                    dimstyle=self.dimstyle,
                                    override={"dimtxt": LO.H_NORM, "dimasz": 40,
                                              "dimexe": 30, "dimexo": 20, "dimdec": 0},
                                    dxfattribs={"layer": LO.LY_DIM})
        d.render()

    def _plain_dim(self, p1, p2, base, horizontal):
        if horizontal:
            self.line((p1[0], base), (p2[0], base), LO.LY_DIM)
            self.line(p1, (p1[0], base), LO.LY_DIM)
            self.line(p2, (p2[0], base), LO.LY_DIM)
            self.text(((p1[0] + p2[0]) / 2 - 140, base + 45),
                      f"{abs(p2[0] - p1[0]):.0f}", LO.H_NORM, LO.LY_DIM)
        else:
            self.line((base, p1[1]), (base, p2[1]), LO.LY_DIM)
            self.line(p1, (base, p1[1]), LO.LY_DIM)
            self.line(p2, (base, p2[1]), LO.LY_DIM)
            self.text((base + 55, (p1[1] + p2[1]) / 2),
                      f"{abs(p2[1] - p1[1]):.0f}", LO.H_NORM, LO.LY_DIM)

    def hatch_rect(self, x, y, w, h, step=150):
        d = -h
        while d < w:
            x1, y1, x2, y2 = x + d, y, x + d + h, y + h
            if x1 < x:
                y1 += (x - x1); x1 = x
            if x2 > x + w:
                y2 -= (x2 - (x + w)); x2 = x + w
            if x2 > x1 and y2 > y1:
                self.line((x1, y1), (x2, y2), LO.LY_HATCH)
            d += step

    def sheet_bounds(self):
        """
        ناحیه ترسیم واقعی داخل کادر.
        کف این ناحیه خط بالای جدول عنوان است، نه لبه کادر — وگرنه متن‌ها
        روی خانه‌های جدول عنوان می‌افتند.
        """
        s = self.cfg.drawing.scale
        ax0, ay0, ax1, ay1 = LO.DRAW_AREA
        ox, oy = LO.FRAME_INSERT
        return ox + ax0 * s, oy + ay0 * s, ox + ax1 * s, oy + ay1 * s

    def leader(self, target, knee, txt, dx=700):
        """
        خط راهنما با زانویی که همیشه داخل کادر می‌ماند.
        اگر متن از لبه راست بزند بیرون، دنباله به سمت چپ کشیده می‌شود.
        """
        lo_x, lo_y, hi_x, hi_y = self.sheet_bounds()
        text_w = len(str(txt)) * LO.H_NORM * 0.62
        kx = min(max(knee[0], lo_x), hi_x - dx - text_w)
        ky = min(max(knee[1], lo_y), hi_y)
        if kx < lo_x:                       # جا نبود، از سمت چپ متن بگذار
            kx, dx = lo_x, -dx
        knee = (kx, ky)
        self.line(target, knee, LO.LY_TEXT)
        self.line(knee, (knee[0] + dx, knee[1]), LO.LY_TEXT)
        tx = knee[0] + dx + 60 if dx > 0 else knee[0] + dx - text_w - 60
        self.text((tx, knee[1] + 40), txt, LO.H_NORM)

    def section_mark(self, p, letter):
        self.circle(p, 90, LO.LY_DETAIL)
        self.text((p[0] - 30, p[1] - 35), letter, LO.H_MARK)

    # ================================================== ساخت نقشه
    def build(self, res, eq, soil, qty, bbs, seismic, des):
        self.des = des
        g = res.geometry
        self.L, self.B = g.L * 1000, g.B * 1000
        self.tf, self.hp, self.b = g.tf * 1000, g.hp * 1000, g.b * 1000
        self.cov = self.cfg.materials.cover
        self.lean = self.cfg.materials.lean
        self.n = eq.n_pedestal
        self.sp = eq.pedestal_spacing * 1000 or (self.B / 2 if self.n > 1 else 0)
        self.eq = eq

        self.insert_frame()
        self._plan()
        self._section_a()
        self._section_b()
        self._detail_anchor()
        self._bbs(bbs)
        self._summary(qty)
        self._notes(soil, seismic)
        self._fit_view()
        self.check_bounds()
        return self

    def _peds(self, cx):
        return [cx] if self.n == 1 else [cx - self.sp / 2, cx + self.sp / 2]

    # ---------------------------------------------- پلان
    def _plan(self):
        cx, cy = LO.PLAN_CENTER
        L, B, b, cov, lean = self.L, self.B, self.b, self.cov, self.lean
        x0, y0 = cx - L / 2, cy - B / 2
        pad = self.des["pad"]

        self.rect(x0 - lean, y0 - lean, L + 2 * lean, B + 2 * lean, LO.LY_DETAIL)
        self.rect(x0, y0, L, B, LO.LY_CONCRETE)

        s = pad.spacing
        i = 0
        while x0 + cov + i * s <= x0 + L - cov + 1:
            self.line((x0 + cov + i * s, y0 + cov), (x0 + cov + i * s, y0 + B - cov), LO.LY_REBAR)
            i += 1
        j = 0
        while y0 + cov + j * s <= y0 + B - cov + 1:
            self.line((x0 + cov, y0 + cov + j * s), (x0 + L - cov, y0 + cov + j * s), LO.LY_REBAR)
            j += 1

        # ستون‌ها بعد از شبکه، تا روی آرماتور دیده شوند
        for px in self._peds(cx):
            self.rect(px - b / 2, cy - b / 2, b, b, LO.LY_CONCRETE)
            gge, r = self.eq.anchor_gauge, self.eq.anchor_dia / 2
            for sx in (-1, 1):
                for sy in (-1, 1):
                    c = (px + sx * gge / 2, cy + sy * gge / 2)
                    self.circle(c, r, LO.LY_DETAIL)
                    self.line((c[0] - 2.2 * r, c[1]), (c[0] + 2.2 * r, c[1]), LO.LY_DIM)
                    self.line((c[0], c[1] - 2.2 * r), (c[0], c[1] + 2.2 * r), LO.LY_DIM)

        # اندازه‌ها فقط دور تا دور، نه از وسط نقشه
        self.dim_h((x0, y0), (x0 + L, y0), y0 - 620)
        self.dim_v((x0 + L, y0), (x0 + L, y0 + B), x0 + L + 620)

        # علامت‌های مقطع
        self.line((x0 - 380, cy), (x0 + L + 380, cy), LO.LY_DIM)
        self.section_mark(LO.PLAN_SEC_A_LEFT, "A")
        self.section_mark(LO.PLAN_SEC_A_RIGHT, "A")
        self.line((cx, y0 - 380), (cx, y0 + B + 380), LO.LY_DIM)
        self.section_mark(LO.PLAN_SEC_B_LEFT, "B")
        self.section_mark(LO.PLAN_SEC_B_RIGHT, "B")

        self.leader((x0 + L - cov - 2 * s, y0 + B * 0.72), (x0 + L + 420, y0 + B + 300),
                    f"{pad.bar_count}%%C{pad.bar_dia}@{pad.spacing:.0f}  T&B  E.W.", dx=450)
        self.text(LO.PLAN_TITLE, "PLAN", LO.H_TITLE)
        self.text((LO.PLAN_TITLE[0], LO.PLAN_TITLE[1] - 90),
                  f"Sc.1:{self.cfg.drawing.scale:.0f}", LO.H_TINY)

    # ---------------------------------------------- مقطع A-A
    def _section_a(self):
        x0, y0 = LO.SEC_A_LEFT_X, LO.SEC_A_BOF_Y
        L, tf, hp, b, cov, lean = self.L, self.tf, self.hp, self.b, self.cov, self.lean
        cx = LO.PLAN_CENTER[0]
        r = self.cfg.rebar

        self.hatch_rect(x0 - lean - 800, y0 - lean, 800, tf + hp - 150 + lean)
        self.hatch_rect(x0 + L + lean, y0 - lean, 800, tf + hp - 150 + lean)
        self.rect(x0 - lean, y0 - lean, L + 2 * lean, lean, LO.LY_DETAIL)
        self.rect(x0, y0, L, tf, LO.LY_CONCRETE)
        for px in self._peds(cx):
            self.rect(px - b / 2, y0 + tf, b, hp, LO.LY_CONCRETE)

        gl = y0 + tf + hp - 150
        self.line((x0 - 800, gl), (x0 + L + 800, gl), LO.LY_DETAIL)
        self.text((x0 - 760, gl + 40), "F.S.L.", LO.H_TINY)
        self.text((x0 - 760, y0 + tf + hp + 40), "F.B.L.", LO.H_TINY)

        self.line((x0 + cov, y0 + cov), (x0 + L - cov, y0 + cov), LO.LY_REBAR)
        self.line((x0 + cov, y0 + tf - cov), (x0 + L - cov, y0 + tf - cov), LO.LY_REBAR)
        for px in self._peds(cx):
            self.line((px - b / 2 + cov, y0 + cov), (px - b / 2 + cov, y0 + tf + hp - cov), LO.LY_REBAR)
            self.line((px + b / 2 - cov, y0 + cov), (px + b / 2 - cov, y0 + tf + hp - cov), LO.LY_REBAR)
            k = 0
            while y0 + tf + cov + k * r.tie_spacing <= y0 + tf + hp - cov:
                y = y0 + tf + cov + k * r.tie_spacing
                self.line((px - b / 2 + cov, y), (px + b / 2 - cov, y), LO.LY_REBAR)
                k += 1
            for sg in (-1, 1):
                bx = px + sg * self.eq.anchor_gauge / 2
                self.line((bx, y0 + tf + hp + 200), (bx, y0 + tf + hp - self.eq.anchor_embed),
                          LO.LY_DETAIL)

        pad, ped = self.des["pad"], self.des["pedestal"]
        self.leader((cx - b / 2 + cov, y0 + tf + hp * 0.62), (x0 - 500, y0 + tf + hp + 380),
                    f"{ped.bar_count}%%C{ped.bar_dia}", dx=-420)
        self.leader((cx + b / 2 - cov, y0 + tf + cov + 2 * r.tie_spacing),
                    (x0 + L + 320, y0 + tf + hp * 0.80),
                    f"%%C{r.tie_dia}@{r.tie_spacing:.0f}", dx=380)
        self.leader((x0 + L * 0.35, y0 + cov), (x0 + L + 900, y0 - 620),
                    f"{pad.bar_count}%%C{pad.bar_dia}@{pad.spacing:.0f}")
        # برچسب‌ها همه سمت راست مقطع، با فاصله عمودی مشخص تا روی هم نیفتند
        self.leader((x0 + L * 0.6, y0 - lean / 2), (x0 + L + 320, y0 - lean - 60),
                    "LEAN CONCRETE", dx=380)
        self.text((x0 + L + 700, y0 - lean - 330), "COMPACTED SOIL", LO.H_NORM)

        self.dim_v((x0, y0), (x0, y0 + tf), x0 - 420)
        self.dim_v((x0, y0 + tf), (x0, y0 + tf + hp), x0 - 420)
        self.dim_h((x0, y0), (x0 + L, y0), y0 - 250)
        self.text(LO.SEC_A_TITLE, "SECTION A-A", LO.H_TITLE)
        self.text((LO.SEC_A_TITLE[0], LO.SEC_A_TITLE[1] - 90),
                  f"Sc.1:{self.cfg.drawing.scale:.0f}", LO.H_TINY)

    # ---------------------------------------------- مقطع B-B : مقطع ستون
    def _section_b(self):
        cx, cy = LO.SEC_B_CENTER
        b, cov = self.b, self.cov
        ped = self.des["pedestal"]
        gge, r = self.eq.anchor_gauge, self.eq.anchor_dia / 2

        self.rect(cx - b / 2, cy - b / 2, b, b, LO.LY_CONCRETE)
        core = b - 2 * cov
        self.rect(cx - core / 2, cy - core / 2, core, core, LO.LY_REBAR)

        # توزیع میلگردها دور تا دور مقطع
        n = max(4, ped.bar_count)
        per_side = max(2, n // 4)
        step = core / per_side
        dot = ped.bar_dia / 2
        for k in range(per_side):
            o = -core / 2 + k * step
            self.circle((cx + o, cy - core / 2), dot, LO.LY_REBAR)
            self.circle((cx + core / 2, cy + o), dot, LO.LY_REBAR)
            self.circle((cx - o, cy + core / 2), dot, LO.LY_REBAR)
            self.circle((cx - core / 2, cy - o), dot, LO.LY_REBAR)

        for sx in (-1, 1):
            for sy in (-1, 1):
                self.circle((cx + sx * gge / 2, cy + sy * gge / 2), r, LO.LY_DETAIL)

        self.leader((cx - core / 2, cy + core * 0.3), (cx - b * 1.1, cy + b * 0.7),
                    f"{ped.bar_count}%%C{ped.bar_dia}", dx=-360)
        self.leader((cx - core / 2, cy - core * 0.2), (cx - b * 1.1, cy + b * 0.2),
                    f"%%C{self.cfg.rebar.tie_dia}@{self.cfg.rebar.tie_spacing:.0f}", dx=-360)
        self.dim_h((cx - b / 2, cy - b / 2), (cx + b / 2, cy - b / 2), cy - b / 2 - 420)
        self.text(LO.SEC_B_TITLE, "SECTION B-B", LO.H_TITLE)
        self.text((LO.SEC_B_TITLE[0], LO.SEC_B_TITLE[1] - 90),
                  f"Sc.1:{self.cfg.drawing.scale:.0f}", LO.H_TINY)

    # ---------------------------------------------- دیتیل میل مهار
    def _detail_anchor(self):
        cx, cy = LO.DET1_CENTER
        k = self.cfg.drawing.scale / self.cfg.drawing.detail_scale   # بزرگ‌نمایی دیتیل
        gge = self.eq.anchor_gauge * k
        dia = self.eq.anchor_dia * k
        emb = self.eq.anchor_embed * k
        proj = 200 * k
        bw = self.b * k * 0.9

        self.text(LO.DET1_TITLE, 'DET."1"', LO.H_TITLE)
        self.text(LO.DET1_SCALE_TXT, f"Sc.1:{self.cfg.drawing.detail_scale:.0f}", 30.0)

        top = cy + emb / 2
        self.rect(cx - bw / 2, cy - emb / 2 - 200, bw, emb + 200, LO.LY_CONCRETE)
        self.line((cx - gge / 2 - dia * 2, top), (cx + gge / 2 + dia * 2, top), LO.LY_DETAIL)
        self.line((cx - gge / 2 - dia * 2, top + 60), (cx + gge / 2 + dia * 2, top + 60), LO.LY_DETAIL)
        for sg in (-1, 1):
            bx = cx + sg * gge / 2
            self.line((bx - dia / 2, top - emb), (bx - dia / 2, top + proj), LO.LY_DETAIL)
            self.line((bx + dia / 2, top - emb), (bx + dia / 2, top + proj), LO.LY_DETAIL)
            self.line((bx - dia / 2, top - emb), (bx - sg * dia * 2, top - emb), LO.LY_DETAIL)
            self.rect(bx - dia, top + 70, 2 * dia, 70, LO.LY_DETAIL)
            self.rect(bx - dia, top + 150, 2 * dia, 70, LO.LY_DETAIL)

        self.dim_v((cx - gge / 2, top - emb), (cx - gge / 2, top), cx - gge / 2 - 500)
        self.dim_h((cx - gge / 2, top), (cx + gge / 2, top), top + 520)
        self.text((cx + gge / 2 + 400, top + 120), "BASE PLATE + 2 NUTS", LO.H_TINY)
        self.text((cx + gge / 2 + 400, top - 250), "GROUT", 47.5)
        self.text((cx - bw / 2, cy - emb / 2 - 500),
                  f"{self.eq.anchor_n}M{self.eq.anchor_dia}", 45.0)
        self.text(LO.DET1_BOTTOM_TITLE, "ANCHOR BOLT", LO.H_BIG)

    # ---------------------------------------------- جدول آرماتور
    def _bbs(self, bbs):
        """
        عرض ستون‌ها از فضای واقعی داخل کادر حساب می‌شود، نه مختصات دستی،
        تا نه روی هم بیفتند و نه از کادر بزنند بیرون.
        """
        ox, oy = LO.BBS_ORIGIN
        _, _, hi_x, _ = self.sheet_bounds()
        avail = hi_x - ox - LO.GRID_STRIP
        h = LO.H_TABLE

        # سهم هر ستون از عرض کل
        share = [("pos", 0.07), ("shape", 0.34), ("dia", 0.08), ("no", 0.08),
                 ("length", 0.11), ("total", 0.11), ("unit_w", 0.11), ("weight", 0.10)]
        pos, acc = {}, 0.0
        for key, frac in share:
            pos[key] = ox + acc * avail
            acc += frac
        width = {key: frac * avail for key, frac in share}

        self.text(LO.BBS_TITLE, "BAR BENDING SCHEDULE", LO.H_SUMMARY)
        head = {"pos": ("POS.", ""), "shape": ("BENDING DIAGRAM", ""),
                "dia": ("%%c", "mm"), "no": ("NO", "RQD."),
                "length": ("LENGTH", "m"), "total": ("TOTAL", "m"),
                "unit_w": ("UNIT WEIGHT", "kg/m"), "weight": ("TOTAL WEIGHT", "kg")}
        for key, (l1, l2) in head.items():
            self.fit_text((pos[key], oy), l1, h, width[key] - 40)
            if l2:
                self.fit_text((pos[key], oy - h * 1.5), l2, h, width[key] - 40)
        rule_y = oy - h * 1.5 - 70
        self.line((ox - 50, rule_y), (ox + avail, rule_y), LO.LY_DETAIL)

        y = rule_y - LO.BBS_ROW_H
        for row in bbs:
            cells = {"pos": row["pos"], "shape": row["shape"], "dia": row["dia"],
                     "no": row["no"], "length": f"{row['length']:.2f}",
                     "total": f"{row['total']:.1f}", "unit_w": f"{row['unit_w']:.3f}",
                     "weight": f"{row['weight']:.2f}"}
            for key, val in cells.items():
                self.fit_text((pos[key], y), val, h, width[key] - 40)
            y -= LO.BBS_ROW_H
        self.line((ox - 50, y + LO.BBS_ROW_H - 60), (ox + avail, y + LO.BBS_ROW_H - 60),
                  LO.LY_DETAIL)
        for i, ln in enumerate(self.wrap(
                "BAR BENDING IS ONLY FOR INFORMATION AND SHOULD BE CHECKED BEFORE CONST.",
                LO.H_NOTE, avail)):
            self.text((LO.BBS_FOOTNOTE[0], LO.BBS_FOOTNOTE[1] - i * LO.NOTES_ROW_H),
                      ln, LO.H_NOTE)

    # ---------------------------------------------- جمع‌بندی متره
    def _summary(self, qty):
        ox, oy = LO.SUMMARY_ORIGIN
        rows = [("TOTAL WEIGHT", f"{qty['rebar']:.2f} Kg"),
                ("CONCRETE VOL.", f"{qty['concrete']:.2f} m3"),
                ("LEAN CON. VOL.", f"{qty['lean']:.3f} m3")]
        for i, (lab, val) in enumerate(rows):
            y = oy - i * LO.SUMMARY_ROW_H
            self.text((ox, y), lab, LO.H_SUMMARY)
            self.text((ox + LO.SUMMARY_VALUE_DX, y), val, LO.H_SUMMARY)

    # ---------------------------------------------- یادداشت‌ها
    def _notes(self, soil, seismic):
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

        self.text(LO.NOTES_TITLE, "NOTE:", 49.0)
        ox, oy = LO.NOTES_ORIGIN
        _, lo_y, hi_x, _ = self.sheet_bounds()
        avail = hi_x - ox - LO.GRID_STRIP        # نوار حروف راهنمای کادر
        h = LO.H_NOTE
        y = oy
        for raw in raw_lines:
            try:
                txt = raw.format(**subst)
            except (KeyError, IndexError):
                txt = raw
            base_indent = LO.NOTES_INDENT if raw.startswith((" ", "\t")) else 0
            for k, ln in enumerate(self.wrap(txt.strip(), h, avail - base_indent)):
                indent = base_indent + (LO.NOTES_INDENT if k else 0)
                self.text((ox + indent, y), ln, h)
                y -= LO.NOTES_ROW_H
                if y < lo_y:
                    print("   (هشدار: یادداشت‌ها از پایین کادر بیرون زدند — "
                          "تعداد بندها را کم کنید یا notes.txt را کوتاه‌تر کنید)")
                    return

    # ---------------------------------------------- دید
    def _fit_view(self):
        s = self.cfg.drawing.scale
        w, h = 420 * s, 297 * s                  # A3
        cx = LO.FRAME_INSERT[0] + w / 2
        cy = LO.FRAME_INSERT[1] + h / 2
        self.doc.set_modelspace_vport(height=h * 1.05, center=(cx, cy))

    def check_bounds(self):
        """
        بعد از ساخت نقشه، هر موجودیتی که بیرون کادر افتاده باشد گزارش می‌شود.
        این‌طور دیگر لازم نیست از روی عکس بفهمیم چیزی بیرون زده یا نه.
        """
        lo_x, lo_y, hi_x, hi_y = self.sheet_bounds()
        outside = []
        for e in self.msp:
            if e.dxftype() == "INSERT":
                continue
            pts = []
            for attr in ("insert", "start", "end", "center"):
                p = getattr(e.dxf, attr, None)
                if p is not None:
                    pts.append((p.x, p.y))
            if e.dxftype() == "TEXT":
                w = self.text_width(e.dxf.text, e.dxf.height)
                if pts:
                    pts.append((pts[0][0] + w, pts[0][1]))
            for x, y in pts:
                if not (lo_x <= x <= hi_x and lo_y <= y <= hi_y):
                    label = getattr(e.dxf, "text", e.dxftype())
                    outside.append(f"{str(label)[:28]} @ ({x:.0f},{y:.0f})")
                    break
        if outside:
            print(f"   ⚠ {len(outside)} مورد بیرون از کادر:")
            for item in outside[:12]:
                print("      ", item)
        else:
            print("   همه‌چیز داخل کادر است.")
        return outside

    def save(self, path):
        self.doc.saveas(path)
        return path
