"""
لیست آرماتور (BBS).

تنها جای محاسبه تعداد و طول میلگردها؛ خط فرمان، سامانه وب و نقشه همه از
همین تابع استفاده می‌کنند تا عددها هیچ‌وقت از هم جدا نشوند.
"""


def unit_weight(dia_mm: float) -> float:
    """وزن واحد طول میلگرد (kg/m)."""
    return 0.006165 * dia_mm * dia_mm


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
                         total=total, unit_w=unit_weight(dia), weight=total * unit_weight(dia)))
    return rows
