"""
نمونه‌های آماده فونداسیون — هر نمونه یک پی کامل با ورودی‌های یک دفترچه تأییدشده.

در سامانه وب «نمونه آماده» همه فرم را پر می‌کند؛ مهندس بعد هر عددی را که
بخواهد تغییر می‌دهد. آزمون‌های tests/test_kimia63.py همین اعداد را کنترل می‌کنند.
"""
from equipment import CATALOG, CATALOG_KIMIA63

ALL_EQUIPMENT = {**CATALOG, **CATALOG_KIMIA63}

# تنظیمات مشترک پست ۶۳ کیمیا (VP-63POST-CAL-0004 صفحه ۶ و ۷)
KIMIA63_SITE = {
    "seismic": {"edition": 4, "a": 0.25, "b": 2.5, "i": 1.4, "r": 2.0},
    "soil": {"q_base": 1.72, "q_factor": 1.33},
    "foundation": {"hp": 1.0, "tf": 0.4},
    "rebar": {"col_dia": 14, "pad_dia": 14},
}


def _g(tag, axis="x", x=0.0, y=0.0, case=None):
    return {"tag": tag, "axis": axis, "x": x, "y": y, "case": case}


FOUNDATION_PRESETS = {
    "K63-LA": {"title": "LA — کیمیا ۶۳ (پی ۲٫۵×۱٫۵)", "site": KIMIA63_SITE,
               "L": 2.5, "B": 1.5, "b": 0.6, "groups": [_g("LA63")]},
    "K63-CB": {"title": "CB — کیمیا ۶۳ (پی ۳٫۲×۲٫۰)", "site": KIMIA63_SITE,
               "L": 3.2, "B": 2.0, "b": 0.7, "groups": [_g("CB63")]},
    "K63-CT": {"title": "CT — کیمیا ۶۳ (پی ۳٫۰×۱٫۷)", "site": KIMIA63_SITE,
               "L": 3.0, "B": 1.7, "b": 0.6, "groups": [_g("CT63")]},
    "K63-DSE": {"title": "DS/DSE — کیمیا ۶۳ (پی ۲٫۵×۱٫۸)", "site": KIMIA63_SITE,
                "L": 2.5, "B": 1.8, "b": 0.6, "groups": [_g("DSE63")]},
    "K63-DS2": {"title": "DS2 — کیمیا ۶۳ (پی ۲٫۵×۲٫۱)", "site": KIMIA63_SITE,
                "L": 2.5, "B": 2.1, "b": 0.6, "groups": [_g("DS2_63")]},
    "K63-LACVT": {"title": "LA/CVT — کیمیا ۶۳ (پی ۳٫۸×۲٫۵، پنج ستون)", "site": KIMIA63_SITE,
                  "L": 3.8, "B": 2.5, "b": 0.6,
                  "groups": [_g("LA63", y=0.75), _g("CVT63", y=-0.75)]},
    "K63-PICVT": {"title": "PI/CVT — کیمیا ۶۳ (پی ۳٫۰×۳٫۰، سه ستون)", "site": KIMIA63_SITE,
                  "L": 3.0, "B": 3.0, "b": 0.6,
                  "groups": [_g("PI63", axis="y", x=0.75, case=5), _g("CVT63_1", x=-0.75)]},
}


def layout_from_spec(groups, equipment_override=None):
    """
    ساخت PadLayout از فهرست گروه‌ها: [{"tag", "axis", "x", "y", "case", "n", "spacing"}].
    equipment_override: {شماره گروه: Equipment} برای وقتی مهندس اعداد را در فرم عوض کرده.
    """
    from padlayout import PadLayout, row
    out = []
    for i, g in enumerate(groups):
        eq = (equipment_override or {}).get(i) or ALL_EQUIPMENT[g["tag"]]
        out.append(row(eq, spacing=g.get("spacing"), axis=g.get("axis") or "x",
                       x=float(g.get("x") or 0), y=float(g.get("y") or 0),
                       case=int(g["case"]) if g.get("case") else None,
                       n=int(g["n"]) if g.get("n") else None))
    return PadLayout(out)
