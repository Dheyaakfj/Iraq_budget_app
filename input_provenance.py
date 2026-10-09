"""Describe input origin separately from user overrides and model outputs."""
import math
from numbers import Real

from extract_cbi_data import RESERVES, M0, FX, IMPORTS, ANNUAL_NAMES, EXPENSE, CURRENT

LABELS = {'official': 'رسمي', 'reported': 'تصريح رسمي', 'assumption': 'افتراض',
          'reference': 'مرجع سيناريو', 'manual': 'معدّل يدويًا'}
INPUT_UNITS = {
    'اسعار_النفط': 'دولار/برميل',
    'حجم_الصادرات_مليون_برميل_يوم': 'مليون برميل/يوم',
    'الاستهلاك_المحلي_مليون_برميل_يوم': 'مليون برميل/يوم',
    'صادرات_مقاسة_مليون_برميل_يوم': 'مليون برميل/يوم',
    'حصة_الحكومة_من_الصادرات': 'نسبة من 0 إلى 1',
    'خصم_خام_البصرة_دولار': 'دولار/برميل',
    'كلفة_انتاج_البرميل_دولار': 'دولار/برميل',
    'سعر_الصرف_الرسمي': 'دينار/دولار',
    'سعر_الصرف_الموازي': 'دينار/دولار',
    'اسعار_الصرف_سيناريو': 'دينار/دولار',
    'ايرادات_غير_نفطية_مليار': 'مليار دينار/سنة',
    'اجمالي_النفقات_مليار': 'مليار دينار/سنة',
    'النفقات_الجارية_مليار': 'مليار دينار/سنة',
    'فاتورة_الرواتب_مليار': 'مليار دينار/سنة',
    'استخدام_الاجمالي': 'اختيار للنموذج',
    'الاحتياطيات_الاجنبية_مليار': 'مليار دينار',
    'النقد_القاعدي_مليار': 'مليار دينار',
    'نسبة_تمويل_المركزي': 'نسبة من 0 إلى 1',
    'نسبة_الفائض_للاحتياطي': 'نسبة من 0 إلى 1',
    'واردات_سنوية_مليار_دولار': 'مليار دولار/سنة',
    'حصة_المستورد_من_السلة': 'نسبة من 0 إلى 1',
    'معامل_تمرير_التضخم': 'معامل من 0 إلى 1',
}


def same_value(value, reference):
    if isinstance(value, (list, tuple)) and isinstance(reference, (list, tuple)):
        return sorted(value) == sorted(reference)
    if isinstance(value, bool) or isinstance(reference, bool):
        return type(value) is type(reference) and value == reference
    if isinstance(value, Real) and isinstance(reference, Real):
        return math.isclose(value, reference, rel_tol=1e-12, abs_tol=1e-9)
    return value == reference


def describe_input(value, baseline, official=None, historical=False, reported=None):
    """`official` من نشرة البنك المركزي؛ `reported` تصريح منشور من جهة رسمية أخرى."""
    # A numeric match alone is never evidence of an official origin.
    origin = ('official' if official is not None else 'reported' if reported is not None
              else 'reference' if historical else 'assumption')
    source = official if official is not None else reported
    kind = origin if same_value(value, baseline) else 'manual'
    # Defensive check: a stale/mismatched preset must not be stamped with a sourced origin.
    if source is not None and not same_value(value, source['value']):
        kind = 'manual'
    return {'kind': kind, 'label': LABELS[kind], 'origin': origin,
            'value': value, 'reference': source['value'] if source else baseline,
            'period': source['period'] if source else '',
            'source_url': source['source_url'] if source else '',
            'sheet': source['sheet'] if source else '',
            'body': source.get('body', '') if source else ''}


def format_value(value):
    if isinstance(value, bool):
        return 'نعم' if value else 'لا'
    if isinstance(value, (tuple, list)):
        return '، '.join(format_value(v) for v in value)
    if isinstance(value, Real):
        return f'{value:,.6f}'.rstrip('0').rstrip('.')
    return str(value)


def audit_row(label, provenance, unit):
    """Human-readable values for the review table and Excel export."""
    origin = provenance['origin']
    return {
        'المدخل': label,
        'القيمة المستخدمة': format_value(provenance['value']),
        'الوحدة': unit,
        'التصنيف': provenance['label'],
        'القيمة المرجعية': format_value(provenance['reference']),
        'أصل المرجع': {'official': 'البنك المركزي العراقي', 'reported': provenance.get('body') or 'تصريح رسمي',
                       'reference': 'قيمة ثابتة للسيناريو', 'assumption': 'افتراض للنموذج'}[origin],
        'الفترة المرجعية': provenance['period'] or 'غير محددة',
        'الجدول في المصدر': provenance['sheet'] or '—',
        'رابط المصدر المرجعي': provenance['source_url'],
    }


def official_inputs(snapshot):
    """The exact imported values, their periods, and their source sheets."""
    p = snapshot['periods']['monetary']
    metrics = snapshot['indicators']
    fiscal = snapshot['fiscal_annual'][-1]
    imports = {year: value for year, value in snapshot['annual_indicators'][IMPORTS].items()
               if value is not None}
    if not imports or fiscal[ANNUAL_NAMES[CURRENT]] is None:
        raise ValueError('Incomplete completed-year inputs')
    imports_year = max(imports)
    values = {
        'الاحتياطيات_الاجنبية_مليار': (metrics[RESERVES][p], p, 'المؤشرات الاقتصادية'),
        'النقد_القاعدي_مليار': (metrics[M0][p], p, 'المؤشرات الاقتصادية'),
        'سعر_الصرف_الرسمي': (metrics[FX][p], p, 'المؤشرات الاقتصادية'),
        'اجمالي_النفقات_مليار': (fiscal[ANNUAL_NAMES[EXPENSE]], str(fiscal['السنة']), '6-1'),
        'النفقات_الجارية_مليار': (fiscal[ANNUAL_NAMES[CURRENT]], str(fiscal['السنة']), '6-1'),
        'واردات_سنوية_مليار_دولار': (imports[imports_year] / 1000, imports_year, 'المؤشرات الاقتصادية'),
    }
    return {field: {'value': value, 'period': period, 'sheet': sheet,
                    'source_url': snapshot.get('source', {}).get('file_url', 'https://cbi.iq/page/122')}
            for field, (value, period, sheet) in values.items()}
