"""
لیست آرماتور (BBS).

تعداد و طول هر ردیف از روی میلگردهای مدل مرکزی (model.py) شمرده و اندازه
گرفته می‌شود؛ پس جدول نقشه، متره و مدل سه‌بعدی همیشه یک عدد دارند.
"""
from collections import OrderedDict

DESCRIPTION = {
    "01": "PAD  BOTTOM  E.W.",
    "02": "PEDESTAL VERTICAL",
    "03": "PAD  TOP  E.W.",
    "04": "STANDEE",
    "05": "PEDESTAL TIE",
}


def unit_weight(dia_mm: float) -> float:
    """وزن واحد طول میلگرد (kg/m)."""
    return 0.006165 * dia_mm * dia_mm


def bar_schedule(fm):
    """
    ردیف‌های لیست آرماتور از مدل. میلگردهای یک شماره که طولشان فرق دارد
    (مثلاً دو جهت پی مستطیلی) در ردیف‌های جدا با پسوند a و b می‌آیند.
    """
    groups = OrderedDict()
    for bar in sorted(fm.bars, key=lambda b: b.mark):
        key = (bar.mark, bar.dia, round(bar.length / 10) * 10)
        groups.setdefault(key, []).append(bar)
    per_mark = {}
    for mark, _, _ in groups:
        per_mark[mark] = per_mark.get(mark, 0) + 1
    seen, rows = {}, []
    for (mark, dia, _), bars in groups.items():
        pos = mark
        if per_mark[mark] > 1:
            seen[mark] = seen.get(mark, 0) + 1
            pos = mark + "abcdefgh"[seen[mark] - 1]
        length = bars[0].length / 1000
        total = length * len(bars)
        rows.append(dict(pos=pos, shape=DESCRIPTION.get(mark, mark), dia=int(dia),
                         no=len(bars), length=length, total=total,
                         unit_w=unit_weight(dia), weight=total * unit_weight(dia)))
    return rows
