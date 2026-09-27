"""
مدل سه‌بعدی فونداسیون (برای ارائه) — فایل DXF با حجم‌های واقعی 3DSOLID.

هر جزء از مدل مرکزی (model.py) ساخته می‌شود؛ همان میلگردی که در نقشه
دوبعدی و لیست آرماتور آمده، اینجا حجم دارد. هر گروه در لایه جدا با رنگ
مشخص است تا در اتوکد بشود خاموش/روشن یا شفاف کرد:

    F-LEAN       بتن مگر
    F-CONCRETE   پی و ستون (نیمه‌شفاف تا آرماتور دیده شود)
    F-REBAR-01…  آرماتور، هر ردیف لیست آرماتور یک لایه
    F-ANCHOR     میل مهار، مهره، صفحه کف
    F-GROUT      گروت زیر صفحه کف

در اتوکد: VSCURRENT → Realistic یا Conceptual، و دستور 3DORBIT.
"""
import ezdxf
from ezdxf.acis import api as acis
from ezdxf.render import forms

# نام لایه → (رنگ RGB، شفافیت ۰ تا ۱)
# پالت ملایم و واقعی: بتن خاکستری گرم، آرماتور قهوه‌ای زنگ‌زده مات،
# میل مهار و صفحه فولاد گالوانیزه، گروت بژ. رنگ‌های اشباع‌شده عمداً نیست.
LAYERS = {
    "F-LEAN": ((128, 124, 116), 0.0),
    "F-CONCRETE": ((212, 208, 200), 0.60),
    "F-REBAR-01": ((126, 84, 64), 0.0),     # شبکه زیرین
    "F-REBAR-02": ((112, 74, 56), 0.0),     # میلگرد طولی ستون
    "F-REBAR-03": ((138, 94, 72), 0.0),     # شبکه رویی
    "F-REBAR-04": ((120, 98, 80), 0.0),     # خرک
    "F-REBAR-05": ((150, 112, 90), 0.0),    # خاموت
    "F-ANCHOR": ((176, 182, 188), 0.0),     # میل مهار، مهره، واشر
    "F-PLATE": ((150, 158, 166), 0.0),      # صفحه کف
    "F-GROUT": ((198, 190, 172), 0.25),
}
SIDES = 16          # تعداد وجه منشور جایگزین مقطع دایره‌ای میلگرد


class Foundation3D:
    def __init__(self, fm, eq, sides=SIDES):
        self.fm, self.eq, self.sides = fm, eq, sides
        self.doc = ezdxf.new("R2010")
        self.doc.header["$INSUNITS"] = 4                   # میلی‌متر
        self.msp = self.doc.modelspace()
        for name, (rgb, transparency) in LAYERS.items():
            layer = self.doc.layers.add(name)
            layer.rgb = rgb
            if transparency:
                layer.transparency = transparency
        self.count = 0

    # ---------------------------------------------- حجم‌ها
    def _solid(self, mesh, layer):
        s = self.msp.add_3dsolid(dxfattribs={"layer": layer})
        acis.export_dxf(s, [acis.body_from_mesh(mesh)])
        self.count += 1
        return s

    def box(self, x0, y0, z0, x1, y1, z1, layer):
        m = forms.cube(center=False).scale(x1 - x0, y1 - y0, z1 - z0).translate(x0, y0, z0)
        return self._solid(m, layer)

    def rod(self, p, q, dia, layer, sides=None):
        m = forms.cylinder_2p(count=sides or self.sides, radius=dia / 2,
                              base_center=p, top_center=q)
        return self._solid(m, layer)

    def bar(self, bar):
        """میلگرد خم‌دار: هر قطعه یک منشور؛ در محل خم نیم‌قطر ادامه می‌یابد تا درز نماند."""
        pts = bar.points + ([bar.points[0]] if bar.closed else [])
        layer = f"F-REBAR-{bar.mark}"
        ext = bar.dia / 2
        for i, (a, b) in enumerate(zip(pts, pts[1:])):
            d = [b[k] - a[k] for k in range(3)]
            n = sum(c * c for c in d) ** 0.5
            if n < 1e-6:
                continue
            u = [c / n for c in d]
            first, last = i == 0 and not bar.closed, i == len(pts) - 2 and not bar.closed
            p = [a[k] - (0 if first else ext) * u[k] for k in range(3)]
            q = [b[k] + (0 if last else ext) * u[k] for k in range(3)]
            self.rod(p, q, bar.dia, layer)

    # ---------------------------------------------- اجزا
    def build(self):
        fm, eq = self.fm, self.eq
        L, B, lm = fm.L, fm.B, fm.lean_margin
        self.box(-L / 2 - lm, -B / 2 - lm, -fm.lean, L / 2 + lm, B / 2 + lm, 0, "F-LEAN")
        self.box(-L / 2, -B / 2, 0, L / 2, B / 2, fm.tf, "F-CONCRETE")
        for p in fm.pedestals:
            self.box(p.x - p.size / 2, p.y - p.size / 2, fm.tf,
                     p.x + p.size / 2, p.y + p.size / 2, fm.top, "F-CONCRETE")
        for bar in fm.bars:
            self.bar(bar)
        self._anchorage()
        self._view()
        return self

    def _anchorage(self):
        """
        مطابق دیتیل استاندارد دفتر: گروت زیر صفحه کف، صفحه کف، واشر و دو مهره،
        میل مهار با قلاب انتهایی رو به داخل ستون. ابعاد از مدل مرکزی.
        """
        fm, eq = self.fm, self.eq
        grout, plate_t = fm.grout, fm.plate_t
        for p in fm.pedestals:
            mine = [a for a in fm.anchors if abs(a.x - p.x) <= p.size / 2]
            if not mine:
                continue
            side = eq.base_plate or eq.anchor_gauge + 150
            side = min(side, p.size - 50)
            z = fm.top
            g = side / 2 + 25
            self.box(p.x - g, p.y - g, z, p.x + g, p.y + g, z + grout, "F-GROUT")
            self.box(p.x - side / 2, p.y - side / 2, z + grout,
                     p.x + side / 2, p.y + side / 2, z + grout + plate_t, "F-PLATE")
            for a in mine:
                d = a.dia
                self.rod((a.x, a.y, a.z_bottom), (a.x, a.y, a.z_top), d, "F-ANCHOR")
                hx = 1 if a.x < p.x else -1                   # قلاب رو به داخل ستون
                self.rod((a.x - hx * d / 2, a.y, a.z_bottom),
                         (a.x + hx * fm.anchor_hook * d, a.y, a.z_bottom), d, "F-ANCHOR")
                zn = z + grout + plate_t
                self.rod((a.x, a.y, zn), (a.x, a.y, zn + 4), 2.2 * d, "F-ANCHOR", sides=24)
                for k in range(2):
                    z0 = zn + 4 + k * 0.85 * d
                    self.rod((a.x, a.y, z0), (a.x, a.y, z0 + 0.8 * d), 1.7 * d, "F-ANCHOR",
                             sides=6)

    def _view(self):
        """نمای ایزومتریک با سایه‌زنی، تا فایل از همان اول سه‌بعدی باز شود."""
        fm = self.fm
        vp = self.doc.viewports.get("*Active")[0]
        vp.dxf.target = (0, 0, fm.top / 2)
        vp.dxf.direction = (1, -1.2, 0.9)
        vp.dxf.center = (0, 0)
        vp.dxf.height = max(fm.L, fm.B, fm.top) * 2.2
        vp.dxf.render_mode = 6          # Gouraud + edges

    def save(self, path):
        self.doc.saveas(path)
        return path


def export(fm, eq, path):
    return Foundation3D(fm, eq).build().save(path)
