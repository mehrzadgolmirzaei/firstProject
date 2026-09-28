"""
پیش‌نمایش شیت نقشه دوبعدی در مرورگر: همان FoundationDrawing که فایل DXF را می‌سازد،
بدون ذخیره فایل، با موتور رسم ezdxf به SVG تبدیل می‌شود.
"""
from ezdxf.addons.drawing import Frontend, RenderContext, layout, svg
from ezdxf.addons.drawing.config import BackgroundPolicy, Configuration

from drawing import FoundationDrawing
import layout as LO


def sheet_svg(res, eq, soil, qty, bbs, seis, des, cfg):
    tb = cfg.title_block.fields
    if not str(tb.get("DOCUMENT_TITLE", "")).strip():
        lay = getattr(res, "layout", None)
        names = [g.eq.title.upper() for g in lay.groups] if lay else [eq.title.upper()]
        tb["DOCUMENT_TITLE"] = " & ".join(dict.fromkeys(names)) + " FOUNDATION"
    dwg = FoundationDrawing(cfg).build(res, eq, soil, qty, bbs, seis, des)
    doc = dwg.doc
    backend = svg.SVGBackend()
    # پس‌زمینه تیره مثل فضای مدل اتوکد، تا رنگ‌ها همان باشد که در اتوکد دیده می‌شود
    conf = Configuration(background_policy=BackgroundPolicy.CUSTOM, custom_bg_color="#212830")
    Frontend(RenderContext(doc), backend, config=conf).draw_layout(doc.modelspace())
    w, h = LO.FRAME_SIZE
    page = layout.Page(w, h, layout.Units.mm, margins=layout.Margins.all(0))
    return backend.get_string(page)
