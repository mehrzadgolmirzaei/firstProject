"""
چیدمان ستون‌های بتنی (پدستال) روی پی.

یک پی می‌تواند یک یا چند «گروه» داشته باشد؛ هر گروه یک تجهیز (با npol فاز روی
یک سازه) است که روی یک یا چند ستون می‌نشیند:

    پی منفرد (پست ۲۳۰/۴۰۰)  : یک گروه، یک ستون در مرکز پی
    پی مشترک (پست ۶۳)       : یک گروه، دو یا سه ستون در یک ردیف با فاصله D
    پی ترکیبی (LA+CVT، PI+CVT): دو گروه، هر کدام ردیف خودش

مختصات بر حسب متر، مبدأ در مرکز پی؛ x در راستای L ، y در راستای B.
بار جانبی در راستای B فرض می‌شود (مثل دفترچه‌ها: M_r = W·B/2).
"""
from dataclasses import dataclass, field
from typing import Optional

from equipment import Equipment


@dataclass
class Group:
    eq: Equipment
    positions: Optional[list] = None      # [(x, y)] ؛ None = فاصله نامشخص (کاتالوگ قدیمی)
    case: Optional[int] = None            # حالت بار دستی همین گروه؛ None = طبق گزینه کلی
    n_legacy: int = 1                     # تعداد ستون وقتی positions نامشخص است

    @property
    def n(self) -> int:
        return len(self.positions) if self.positions is not None else self.n_legacy

    def resolved(self, B: float) -> list:
        """
        مختصات ستون‌ها. برای کاتالوگ قدیمی بدون فاصله محور (پی منفرد مربعی
        دوستونه)، نصف عرض پی فرض می‌شود.
        """
        if self.positions is not None:
            return list(self.positions)
        if self.n_legacy <= 1:
            return [(0.0, 0.0)]
        s = B / 2
        return [(-(self.n_legacy - 1) / 2 * s + i * s, 0.0) for i in range(self.n_legacy)]


def row(eq: Equipment, spacing: Optional[float] = None, axis: str = "x",
        x: float = 0.0, y: float = 0.0, case: Optional[int] = None,
        n: Optional[int] = None) -> Group:
    """یک ردیف ستون برای یک تجهیز، به مرکز (x, y) و در راستای axis."""
    n = n or eq.n_pedestal
    s = eq.pedestal_spacing if spacing is None else spacing
    if n > 1 and not s:
        return Group(eq, None, case, n_legacy=n)
    offs = [(-(n - 1) / 2 + i) * s for i in range(n)]
    pos = [(x + o, y) if axis == "x" else (x, y + o) for o in offs]
    return Group(eq, pos, case)


@dataclass
class PadLayout:
    groups: list = field(default_factory=list)
    square: bool = False    # پی منفرد مربعی (پست ۲۳۰/۴۰۰)، حتی با دو ستون

    @classmethod
    def single(cls, eq: Equipment) -> "PadLayout":
        return cls([row(eq)])

    @property
    def n_ped(self) -> int:
        return sum(g.n for g in self.groups)

    @property
    def rectangular(self) -> bool:
        """پی مستطیلی مشترک: چند گروه، یا ستون‌های با فاصله معلوم."""
        if self.square:
            return False
        if len(self.groups) > 1:
            return True
        g = self.groups[0]
        return g.positions is not None and g.n > 1

    @property
    def main(self) -> Equipment:
        return self.groups[0].eq

    def positions(self, B: float) -> list:
        """[(x, y, شماره گروه)] همه ستون‌ها."""
        return [(x, y, i) for i, g in enumerate(self.groups) for x, y in g.resolved(B)]

    def footprint(self, b: float):
        """
        کوچک‌ترین مستطیل دربرگیرنده ستون‌ها (بدون بیرون‌زدگی پی) و مرکزش،
        برای چیدمان‌هایی که مختصاتشان معلوم است.
        """
        pts = [(x, y) for g in self.groups if g.positions is not None for x, y in g.positions]
        if not pts:
            return b, b
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        return (max(xs) - min(xs) + b, max(ys) - min(ys) + b)

    def describe(self) -> str:
        parts = []
        for g in self.groups:
            parts.append(f"{g.eq.tag}×{g.n}")
        return " + ".join(parts)
