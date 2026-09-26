"""Read published CBI snapshots and derive explicitly dated scenario defaults."""
from copy import deepcopy
import json
from pathlib import Path

import pandas as pd

from extract_cbi_data import RESERVES, M0, FX, IMPORTS, ANNUAL_NAMES, EXPENSE, CURRENT

LATEST_SCENARIO = 'أحدث بيانات فعلية — البنك المركزي'


def load_data(directory):
    directory = Path(directory)
    snapshot = directory / 'cbi_latest.json'
    result = {'metadata': {}, 'snapshot': None}
    if snapshot.exists():
        data = json.loads(snapshot.read_text(encoding='utf-8'))
        result.update({
            'snapshot': data,
            'سنوي': pd.DataFrame.from_dict(data['annual_indicators'], orient='index'),
            'مؤشرات': pd.DataFrame.from_dict(data['indicators'], orient='index'),
            'مالية_شهري': pd.DataFrame(data['fiscal_monthly']),
            'مالية_سنوي': pd.DataFrame(data['fiscal_annual']),
        })
    else:
        for key, filename in [('سنوي', 'cbi_annual.csv'), ('مالية_شهري', 'cbi_fiscal_monthly.csv'),
                              ('مالية_سنوي', 'cbi_fiscal_annual.csv')]:
            path = directory / filename
            result[key] = pd.read_csv(path, index_col=0 if key == 'سنوي' else None) if path.exists() else None
    status = directory / 'cbi_status.json'
    if status.exists():
        result['metadata'] = json.loads(status.read_text(encoding='utf-8'))
    return result


def latest_preset(snapshot, base):
    """Stocks use the newest complete month; annual flows use completed years only."""
    config = deepcopy(base)
    p = snapshot['periods']['monetary']
    metrics = snapshot['indicators']
    fiscal = snapshot['fiscal_annual'][-1]
    config.update({
        'الاحتياطيات_الاجنبية_مليار': metrics[RESERVES][p],
        'النقد_القاعدي_مليار': metrics[M0][p],
        'سعر_الصرف_الرسمي': metrics[FX][p],
        'اجمالي_النفقات_مليار': fiscal[ANNUAL_NAMES[EXPENSE]],
        'النفقات_الجارية_مليار': fiscal[ANNUAL_NAMES[CURRENT]],
    })
    if config['النفقات_الجارية_مليار'] is None:
        raise ValueError('Latest completed fiscal year has no current expenditure value')
    import_years = {year: values for year, values in snapshot['annual_indicators'][IMPORTS].items()
                    if values is not None}
    if not import_years:
        raise ValueError('No completed year of import data')
    imports_year = max(import_years)
    config['واردات_سنوية_مليار_دولار'] = import_years[imports_year] / 1000
    config['اسعار_الصرف_سيناريو'] = sorted(set(config['اسعار_الصرف_سيناريو'] + [metrics[FX][p]]))
    config['وصف'] = (
        f"الاحتياطي والنقد والصرف: {p}. الإنفاق السنوي: {fiscal['السنة']}. "
        f"الواردات السنوية: {imports_year}. بقية المدخلات افتراضات قابلة للتعديل؛ "
        "لا تُحوّل الأرقام الشهرية التراكمية إلى إنفاق سنوي."
    )
    return config


def data_signature(directory):
    return tuple((p.name, p.stat().st_mtime_ns, p.stat().st_size)
                 for p in sorted(Path(directory).glob('cbi_*')) if p.is_file())
