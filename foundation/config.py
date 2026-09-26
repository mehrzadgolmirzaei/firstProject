"""
تمام ورودی‌های قابل تنظیم پروژه در یک جا.

هیچ عددی در کد ثابت نیست: مقاومت بتن، پوشش، مقیاس، تعداد تجهیز، مشخصات
آرماتور، پارامترهای لرزه‌ای و فیلدهای جدول عنوان همگی اینجا هستند و از فایل
project.json خوانده می‌شوند.

    python run.py LA --project project.json

اگر فایل نباشد، مقادیر پیش‌فرض به کار می‌روند و با --save-project ساخته می‌شود.
"""
import json
from dataclasses import dataclass, field, asdict


@dataclass
class Materials:
    fc: int = 250                  # مقاومت مشخصه بتن (kg/cm²)
    fy: int = 4000                 # مقاومت فولاد (kg/cm²)
    cover: int = 75                # پوشش بتن (mm)
    lean: int = 100                # ضخامت بتن مگر (mm)
    gamma_c: float = 2500.0
    gamma_s: float = 1900.0


@dataclass
class SoilData:
    q_base: float = 2.83           # تنش مجاز پایه از گزارش ژئوتکنیک (kg/cm²)
    q_factor: float = 1.33         # ضریب افزایش برای بار موقت
    friction: float = 0.466
    soil_cover: float = 0.15       # خاک روی پی که در وزن حساب نمی‌شود (m)


@dataclass
class SeismicData:
    edition: int = 5               # ۵ یا ۴
    ss: float = 0.90               # نقشه پیوست ۱ ویرایش ۵
    s1: float = 0.35
    soil_class: str = "III"
    ie: float = 1.4
    ru: float = 2.0
    method: str = "rigid"          # rigid | static
    k_lateral: float = 0.0         # سختی جانبی استراکچر (kg/cm) — صفر یعنی نامشخص
    auto_method: bool = True       # اگر سختی داده شود، روش از روی T انتخاب شود
    map_date: str = ""             # تاریخ نقشه مرجع، برای Audit
    # ویرایش ۴
    a: float = 0.30
    b: float = 2.75
    i: float = 1.4
    r: float = 2.0


@dataclass
class Wind:
    v_normal: float = 25.0
    v_high: float = 40.0
    sc_ratio: float = 0.70


@dataclass
class Rebar:
    pad_dia: int = 14              # قطر آرماتور پی
    pad_spacing_max: float = 200   # حداکثر فاصله شبکه (mm)
    col_dia: int = 18              # قطر آرماتور ستون
    col_min_bars: int = 8          # حداقل تعداد میلگرد ستون (استاندارد دفتر)
    tie_dia: int = 10
    tie_spacing: float = 150
    standee_dia: int = 14


@dataclass
class Foundation:
    hp: float = 1.00               # ارتفاع ستون (m)
    b: float = 0.80                # ضلع ستون (m)
    tf: float = 0.40               # ضخامت پی (m)
    search_min: float = 1.0        # بازه جست‌وجوی ابعاد پی
    search_max: float = 5.0
    search_step: float = 0.10


@dataclass
class DesignOptions:
    """
    انتخاب‌های مهندس (فهرست گزینه‌ها و پیشنهاد سامانه در engine.py).
    پیش‌فرض همان روش دفترچه کامی‌آباد است تا محاسبات تأییدشده بازتولید شوند.
    """
    governing: str = "notebook"    # notebook | envelope | 1..5
    bearing: str = "min"           # min | max | envelope


@dataclass
class TitleBlock:
    """
    مقادیر جدول عنوان. کلیدها همان نام فیلدهای کادر شرکت هستند
    (فهرست کامل در layout.TITLE_FIELDS). هر کلیدی که اینجا مقدار بگیرد
    روی نقشه نوشته می‌شود؛ بقیه خالی می‌مانند.
    """
    fields: dict = field(default_factory=lambda: {
        "DOCUMENT_TITLE": "",
        "DESC.1": "",
        "DESC.2": "",
        "PANEL_NAME": "",
        "DWG.": "",
        "NO.P": "",
        "T.P": "",
        "COUNT.": "",
        "SCALE": "",
        "CONTRACT_NO.": "",
        "CONTRACTOR_DOC_CODE": "",
        "PREP": "",
        "CHCK": "",
        "APP": "",
        "AUTH": "",
        "REV1": "", "DATE1": "", "DESC1": "",
        "MOD.1": "", "CHCK.1": "", "APPRD.1": "",
    })


@dataclass
class DrawingSetup:
    scale: float = 20.0            # مقیاس شیت — ۲۰ یعنی ۱:۲۰
    detail_scale: float = 10.0     # مقیاس دیتیل میل مهار
    frame_file: str = "frame_blank.dxf"  # کادر شرکت (نسخه خالی)
    template_file: str = "template.dxf"   # مرجع لایه و سبک
    notes_file: str = "notes.txt"
    dxf_version: str = "R2000"


@dataclass
class ProjectConfig:
    project_name: str = ""
    substation: str = ""
    equipment_count: int = 1       # مثلاً ۴ عدد برق‌گیر
    materials: Materials = field(default_factory=Materials)
    soil: SoilData = field(default_factory=SoilData)
    seismic: SeismicData = field(default_factory=SeismicData)
    wind: Wind = field(default_factory=Wind)
    rebar: Rebar = field(default_factory=Rebar)
    foundation: Foundation = field(default_factory=Foundation)
    design: DesignOptions = field(default_factory=DesignOptions)
    title_block: TitleBlock = field(default_factory=TitleBlock)
    drawing: DrawingSetup = field(default_factory=DrawingSetup)

    # ------------------------------------------------------------------
    @classmethod
    def load(cls, path=None):
        if not path:
            return cls()
        try:
            with open(path, encoding="utf-8") as fh:
                raw = json.load(fh)
        except FileNotFoundError:
            print(f"   (فایل {path} نبود — با مقادیر پیش‌فرض ادامه می‌دهم)")
            return cls()
        return cls._from_dict(raw)

    @classmethod
    def _from_dict(cls, raw: dict):
        sub = {"materials": Materials, "soil": SoilData, "seismic": SeismicData,
               "wind": Wind, "rebar": Rebar, "foundation": Foundation, "design": DesignOptions,
               "title_block": TitleBlock, "drawing": DrawingSetup}
        kwargs = {}
        for key, value in raw.items():
            if key in sub and isinstance(value, dict):
                kwargs[key] = sub[key](**{k: v for k, v in value.items()
                                          if k in sub[key].__dataclass_fields__})
            elif key in cls.__dataclass_fields__:
                kwargs[key] = value
        return cls(**kwargs)

    def save(self, path):
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(asdict(self), fh, ensure_ascii=False, indent=2)
        return path
