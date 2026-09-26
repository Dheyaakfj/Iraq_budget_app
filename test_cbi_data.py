"""Offline ingestion tests: schema changes, units, partial years and atomic fallback."""
from datetime import date, datetime, timezone
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest

from openpyxl import Workbook

from cbi_data import latest_preset, load_data
from extract_cbi_data import (parse_workbook, DataValidationError, RESERVES, M0, FX,
                             EXPENSE, CURRENT, ANNUAL_NAMES, IMPORTS)
from sync_cbi_data import discover_link, sync, SOURCE_PAGE

URL = 'https://cbi.iq/static/uploads/up/bulletin.xlsx'
NOW = datetime(2026, 9, 26, tzinfo=timezone.utc)


def workbook_bytes(edit=None):
    workbook = Workbook()
    indicators = workbook.active
    indicators.title = 'المؤشرات الاقتصادية '
    indicators.append(['التفاصيل', 'الوحدة', 'Dec.2024', 'Dec.2025', '31/1/2026',
                       datetime(2027, 6, 30), '31/7/2026'])
    indicators.append(['الاحتياطيات الاجنبية Official Reserve', 'مليار دولار', 100, 97, 101, 86, 80])
    indicators.append(['الاحتياطيات الاجنبية Official Reserve', 'مليار دينار', 130000, 126000, 131000, 112000, 104000])
    indicators.append(['M0 الاساس النقدي', 'مليار دينار', 140000, 132000, 130000, 136000, 133000])
    indicators.append(['معدل سعر الصرف exchange rate', 'دينار', 1300, 1300, 1300, 1300, 1300])
    indicators.append(['الواردات السلعية Imports Goods', 'مليون دولار', 74000, 71000, 1000, None, 7000])
    indicators.append(['التضخم Inflation', '%', 2.6, .3, 0, 3.1, 3.3])
    fiscal = workbook.create_sheet('6-1')
    fiscal.append(['( Million ID)'])
    fiscal.append(['Period', 'إيرادات', 'نفقات', 'جاري', 'رصيد'])
    fiscal.append([None, 'Actual Revenues', 'Actual Expenditures', 'Current Expenditures', 'Surplus /Deficit*'])
    fiscal.append([2024, 100000000, 120000000, 100000000, -20000000])
    fiscal.append([2025])
    months = ['Jan.', 'Feb.', 'Mar.', 'Apr.', 'May', 'Jun.', 'Jul.', 'Aug.', 'Sep.', 'Oct.', 'Nov.', 'Dec.']
    for i, month in enumerate(months, 1):
        fiscal.append([month, i*10000000, i*12000000, i*9000000, -i*2000000])
    fiscal.append([2026])
    fiscal.append(['Jan.', 9000000, 8000000, 7000000, 1000000])
    fiscal.append(['Feb.', 19000000, 18000000, 17000000, 1000000])
    if edit:
        edit(workbook)
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


class CBIDataTests(unittest.TestCase):
    def setUp(self):
        self.content = workbook_bytes()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name)

    def fetch(self, url):
        if url == SOURCE_PAGE:
            return f'<a href="{URL}">download</a>'.encode()
        self.assertEqual(url, URL)
        return self.content

    def parse(self, content=None):
        return parse_workbook(content or self.content, today=NOW.date())

    def test_dynamic_periods_bilingual_names_and_units(self):
        result = self.parse()
        self.assertEqual(result['periods'], {'monetary': '2026-07', 'fiscal': '2026-02', 'annual_budget': '2025'})
        self.assertEqual(result['indicators'][RESERVES]['2026-07'], 104000)
        self.assertEqual(result['fiscal_annual'][-1][ANNUAL_NAMES[EXPENSE]], 144000)
        self.assertEqual(result['fiscal_monthly'][-1][EXPENSE], 18000)
        self.assertEqual(set(result['annual_indicators'][FX]), {'2024', '2025'})

    def test_future_column_is_excluded_with_provenance(self):
        result = self.parse()
        self.assertNotIn('2027-06', result['indicators'][M0])
        self.assertEqual(result['warnings'][0]['column'], 6)
        self.assertEqual(result['warnings'][0]['reason'], 'future_period_excluded')

    def test_unit_changes_are_rejected(self):
        with self.assertRaises(DataValidationError):
            self.parse(workbook_bytes(lambda w: setattr(w.worksheets[0]['B3'], 'value', 'مليون دينار')))

    def test_missing_required_sheet_is_rejected(self):
        with self.assertRaises(DataValidationError):
            self.parse(workbook_bytes(lambda w: w.remove(w['6-1'])))

    def test_bad_fiscal_identity_is_rejected(self):
        with self.assertRaises(DataValidationError):
            self.parse(workbook_bytes(lambda w: setattr(w['6-1']['E20'], 'value', 999)))

    def test_duplicate_period_is_rejected(self):
        with self.assertRaises(DataValidationError):
            self.parse(workbook_bytes(lambda w: setattr(w.worksheets[0]['G1'], 'value', '31/1/2026')))

    def test_latest_monetary_period_must_be_complete(self):
        with self.assertRaises(DataValidationError):
            self.parse(workbook_bytes(lambda w: setattr(w.worksheets[0]['G4'], 'value', None)))

    def test_ambiguous_and_offsite_links_are_rejected(self):
        self.assertEqual(discover_link('<a href="/static/uploads/up/new.xlsx">Excel</a>'), 'https://cbi.iq/static/uploads/up/new.xlsx')
        for html in ['<a href="https://example.org/x.xlsx">Excel</a>', '<p>offline</p>',
                     '<a href="/a.xlsx"></a><a href="/b.xlsx"></a>']:
            with self.assertRaises(DataValidationError):
                discover_link(html)

    def test_no_change_preserves_snapshot_and_updates_check_time(self):
        first = sync(self.out, self.fetch, NOW)
        before = (self.out/'cbi_latest.json').read_bytes()
        later = NOW.replace(hour=6)
        second = sync(self.out, self.fetch, later)
        self.assertEqual(first['status'], 'updated')
        self.assertEqual(second['status'], 'unchanged')
        self.assertEqual(before, (self.out/'cbi_latest.json').read_bytes())
        self.assertNotEqual(first['last_checked_at'], second['last_checked_at'])
        self.assertEqual(first['last_updated_at'], second['last_updated_at'])

    def test_download_failure_keeps_last_good_snapshot(self):
        old = sync(self.out, self.fetch, NOW)
        before = (self.out/'cbi_latest.json').read_bytes()
        def offline(url):
            raise OSError('network unavailable')
        with self.assertRaises(OSError):
            sync(self.out, offline, NOW.replace(hour=6))
        self.assertEqual(before, (self.out/'cbi_latest.json').read_bytes())
        status = json.loads((self.out/'cbi_status.json').read_text())
        self.assertEqual(status['status'], 'failed')
        self.assertEqual(status['last_success_at'], old['last_success_at'])
        self.assertIn('سنوي', load_data(self.out))

    def test_bad_replacement_keeps_last_good_snapshot(self):
        sync(self.out, self.fetch, NOW)
        before = (self.out/'cbi_latest.json').read_bytes()
        self.content = workbook_bytes(lambda w: setattr(w['6-1']['E20'], 'value', 999))
        with self.assertRaises(DataValidationError):
            sync(self.out, self.fetch, NOW.replace(hour=6))
        self.assertEqual(before, (self.out/'cbi_latest.json').read_bytes())

    def test_revised_values_at_same_url_are_detected(self):
        first = sync(self.out, self.fetch, NOW)
        self.content = workbook_bytes(lambda w: setattr(w.worksheets[0]['G3'], 'value', 105000))
        second = sync(self.out, self.fetch, NOW.replace(hour=6))
        self.assertEqual(second['status'], 'updated')
        self.assertNotEqual(first['last_updated_at'], second['last_updated_at'])
        self.assertEqual(load_data(self.out)['snapshot']['indicators'][RESERVES]['2026-07'], 105000)

    def test_older_bulletin_cannot_replace_newer_period(self):
        sync(self.out, self.fetch, NOW)
        before = (self.out/'cbi_latest.json').read_bytes()
        self.content = workbook_bytes(lambda w: setattr(w.worksheets[0]['G1'], 'value', '28/2/2026'))
        with self.assertRaises(DataValidationError):
            sync(self.out, self.fetch, NOW.replace(hour=6))
        self.assertEqual(before, (self.out/'cbi_latest.json').read_bytes())

    def test_latest_defaults_use_completed_annual_flows(self):
        baseline = {'اسعار_الصرف_سيناريو': [1300, 1400], 'ايرادات_غير_نفطية_مليار': 12000}
        config = latest_preset(self.parse(), baseline)
        self.assertEqual(config['اجمالي_النفقات_مليار'], 144000)
        self.assertEqual(config['النفقات_الجارية_مليار'], 108000)
        self.assertEqual(config['واردات_سنوية_مليار_دولار'], 71)
        self.assertEqual(config['الاحتياطيات_الاجنبية_مليار'], 104000)
        self.assertEqual(config['ايرادات_غير_نفطية_مليار'], 12000)
        self.assertNotIn('اجمالي_النفقات_مليار', baseline)


if __name__ == '__main__':
    unittest.main()
