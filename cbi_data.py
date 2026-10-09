"""Read published CBI snapshots and derive explicitly dated scenario defaults."""
from copy import deepcopy
import json
from pathlib import Path

import pandas as pd

from input_provenance import official_inputs
from reported_inputs import REPORTED_INPUTS, PARALLEL_AFTER_DECISION, supersedes

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
    sources = official_inputs(snapshot)
    config.update({field: source['value'] for field, source in sources.items()})
    fx = REPORTED_INPUTS['سعر_الصرف_الرسمي']
    fx_from_decision = supersedes(fx, sources['سعر_الصرف_الرسمي']['period'])
    if fx_from_decision:
        config['سعر_الصرف_الرسمي'] = fx['value']
        config['سعر_الصرف_الموازي'] = PARALLEL_AFTER_DECISION
    exports = REPORTED_INPUTS['صادرات_مقاسة_مليون_برميل_يوم']
    config['صادرات_مقاسة_مليون_برميل_يوم'] = exports['value']
    config['اسعار_الصرف_سيناريو'] = sorted(set(config['اسعار_الصرف_سيناريو'] + [config['سعر_الصرف_الرسمي']]))
    cbi_fx = sources['سعر_الصرف_الرسمي']
    fx_note = (f"الصرف الرسمي: قرار مجلس الوزراء 544، {fx['period']} (بدل {cbi_fx['value']:g} في النشرة). "
               if fx_from_decision else f"الصرف: {cbi_fx['period']}. ")
    config['وصف'] = (
        f"الاحتياطي والنقد: {cbi_fx['period']}. "
        f"{fx_note}"
        f"الإنفاق السنوي: {sources['اجمالي_النفقات_مليار']['period']}. "
        f"الواردات السنوية: {sources['واردات_سنوية_مليار_دولار']['period']}. "
        f"الصادرات: تصريح وزارة النفط، {exports['period']}. "
        "بقية المدخلات افتراضات قابلة للتعديل؛ لا تُحوّل الأرقام الشهرية التراكمية إلى إنفاق سنوي."
    )
    return config


def data_signature(directory):
    return tuple((p.name, p.stat().st_mtime_ns, p.stat().st_size)
                 for p in sorted(Path(directory).glob('cbi_*')) if p.is_file())
