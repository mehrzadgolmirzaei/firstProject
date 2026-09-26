"""
داده تجهیزات و ساختگاه.

فعلاً به صورت فایل نگه داشته می‌شود؛ ساختار دیکشنری‌ها عیناً همان ستون‌هایی است
که بعداً جدول equipment_catalog دیتابیس خواهد داشت، تا انتقال بدون بازنویسی باشد.

مقادیر He, he, Ae, Ce, We و کشش هادی از نقشه اوت‌لاین سازنده می‌آید.
مقادیر anchor_* از نقشه فونداسیون اجراشده یا اوت‌لاین سازنده استخراج می‌شود.
"""
from dataclasses import dataclass, field


@dataclass
class Equipment:
    tag: str                       # LA, CB, CT, CVT, PI, DSE, DS, DSROW
    title: str
    # --- تجهیز ---
    He: float                      # ارتفاع تجهیز (m)
    Ae: float                      # سطح دید تجهیز (m²)
    We: float                      # وزن تجهیز (kg)
    he: float = None               # ارتفاع مرکز ثقل تجهیز؛ پیش‌فرض He/2
    Ce: float = 0.5                # ضریب درگ تجهیز
    npol: int = 1                  # تعداد پایه
    # --- استراکچر ---
    Hs: float = 0.0                # ارتفاع استراکچر (m)
    As: float = 0.0                # سطح دید استراکچر (m²)
    Ws: float = 0.0                # وزن استراکچر (kg)
    hs: float = None               # مرکز ثقل استراکچر؛ پیش‌فرض Hs/2
    Cs: float = 2.05               # ضریب درگ استراکچر
    # --- هادی ---
    Wc: float = 50.0               # وزن هادی (kg)
    Fc: float = 0.0                # کشش افقی هادی، حالت عادی (kg)
    Fc_sc: float = None            # کشش در اتصال کوتاه؛ پیش‌فرض = Fc
    conductor_points: list = field(default_factory=list)   # ارتفاع نقاط اتصال از پای استراکچر
    # --- بار مانور تجهیز ---
    op_vertical: float = 0.0
    op_horizontal: float = 0.0
    op_moment: float = 0.0
    # --- مشخصات اتصال ---
    n_pedestal: int = 1            # تعداد ستون روی پی
    pedestal_spacing: float = 0.0  # فاصله محور ستون‌ها (m)؛ صفر یعنی B/2
    anchor_n: int = 4              # تعداد میل مهار در هر ستون
    anchor_dia: int = 20           # قطر میل مهار (mm)
    anchor_gauge: float = 450      # فاصله میل مهارها (mm)
    anchor_embed: float = 600      # طول مدفون (mm)
    base_plate: float = 0          # ضلع صفحه کف (mm)؛ صفر یعنی نامشخص
    source: str = ""               # مرجع داده — برای Audit
    # فیلدهایی که باید هر پروژه از اوت‌لاین سازنده خوانده و دستی وارد شوند.
    # تا پر نشوند محاسبه اجرا نمی‌شود، تا کسی سهواً با عدد پیش‌فرض نقشه نگیرد.
    requires_outline: list = field(default_factory=list)

    def __post_init__(self):
        if self.he is None:
            self.he = self.He / 2
        if self.hs is None:
            self.hs = self.Hs / 2
        if self.Fc_sc is None:
            self.Fc_sc = self.Fc
        if not self.conductor_points:
            self.conductor_points = [self.He]


# ------------------------------------------------------------------
# پروژه کامی‌آباد — استخراج‌شده از EQUIPMENT CALCULATION KAMI ABAD A2
#
# گِیج میل مهار: برای همه تجهیزات ۴۵۰ میلی‌متر استاندارد است (از نقشه
# 06-4LA_C استخراج و توسط دفتر فنی تأیید شد).
#
# استثنا — کلید قدرت (CB): سازه‌اش را خود سازنده می‌دهد، پس ابعاد و وزن
# استراکچر و تجهیز، نقاط اتصال هادی، گِیج میل مهار و صفحه کف هر پروژه از
# اوت‌لاین سازنده خوانده و دستی وارد می‌شوند. مقادیر زیر برای CB فقط
# نمونه‌ی پروژه کامی‌آباد است و به عنوان پیش‌فرض به کار نمی‌رود.
# ------------------------------------------------------------------
CATALOG = {
    "LA": Equipment("LA", "Lightning Arrester", He=2.205, he=1.103, Ae=0.77, We=227,
                    Hs=3.55, As=0.70, Ws=250, Fc=230, Fc_sc=585,
                    anchor_gauge=450, anchor_n=4, anchor_dia=20, base_plate=600,
                    source="KAMI ABAD A2 / DWG 06-4LA_C"),

    "CB": Equipment("CB", "Circuit Breaker", He=5.258, he=2.629, Ae=1.90, We=1266,
                    Hs=2.00, As=1.90, Ws=100, Fc=175, Fc_sc=125,
                    conductor_points=[3.11, 5.13], op_vertical=3250, op_horizontal=600,
                    anchor_gauge=0, base_plate=0,
                    source="KAMI ABAD A2 — سازه از سازنده، اعداد نمونه",
                    requires_outline=["He", "he", "Ae", "We", "Hs", "As", "Ws",
                                      "anchor_gauge", "base_plate",
                                      "conductor_points", "op_vertical", "op_horizontal"]),

    "CT": Equipment("CT", "Current Transformer", He=3.375, he=1.56, Ae=1.96, We=1720,
                    Hs=2.00, As=0.70, Ws=180, Fc=400, Fc_sc=560,
                    source="KAMI ABAD A2"),

    "CVT": Equipment("CVT", "Capacitive Voltage Transformer", He=3.045, he=1.288, Ae=1.00, We=495,
                     Hs=2.00, As=0.70, Ws=180, Fc=400, Fc_sc=560,
                     source="KAMI ABAD A2"),

    "PI": Equipment("PI", "Post Insulator", He=2.304, he=1.152, Ae=0.71, We=220,
                    Hs=2.90, As=0.60, Ws=220, Fc=1250,
                    source="KAMI ABAD A2"),

    "DSE": Equipment("DSE", "Disconnector with Earthing Switch", He=3.044, he=0.92, Ae=1.52, We=370,
                     Hs=2.35, As=1.00, Ws=450, Fc=400,
                     n_pedestal=2, source="KAMI ABAD A2"),

    "DS": Equipment("DS", "Disconnector", He=3.044, he=0.815, Ae=1.52, We=350,
                    Hs=2.35, As=1.00, Ws=450, Fc=400,
                    n_pedestal=2, source="KAMI ABAD A2"),

    "DSROW": Equipment("DSROW", "Disconnector - Row Mounted", He=3.044, he=0.815, Ae=1.52, We=300,
                       Hs=2.35, As=1.00, Ws=350, Fc=338,
                       n_pedestal=2, source="KAMI ABAD A2"),
}
