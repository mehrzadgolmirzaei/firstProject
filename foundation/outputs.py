"""
ساخت دو خروجی اتوکد از یک محاسبه:

    <stem>_2D.dxf   نقشه اجرایی برای ساخت (روی کادر شرکت)
    <stem>_3D.dxf   مدل سه‌بعدی با حجم واقعی برای ارائه

هر دو از یک مدل مرکزی (model.py) ساخته می‌شوند.
"""
import os

import model


def make_outputs(res, eq, soil, qty, bbs, seis, des, cfg, out_dir, stem, simple=False):
    from drawing import FoundationDrawing
    import model3d

    os.makedirs(out_dir, exist_ok=True)
    tb = cfg.title_block.fields
    if not str(tb.get("DOCUMENT_TITLE", "")).strip():
        lay = getattr(res, "layout", None)
        names = [g.eq.title.upper() for g in lay.groups] if lay else [eq.title.upper()]
        tb["DOCUMENT_TITLE"] = " & ".join(dict.fromkeys(names)) + " FOUNDATION"

    dwg = FoundationDrawing(cfg, simple=simple).build(res, eq, soil, qty, bbs, seis, des)
    p2 = dwg.save(os.path.join(out_dir, f"{stem}_2D.dxf"))
    fm = model.build(res, getattr(res, "layout", eq), des, cfg)
    p3 = model3d.export(fm, eq, os.path.join(out_dir, f"{stem}_3D.dxf"))
    return {"2d": p2, "3d": p3, "scale": dwg.s,
            "warnings": [*dwg.outside, *(f"{a} / {b}" for a, b in dwg.overlaps)]}
