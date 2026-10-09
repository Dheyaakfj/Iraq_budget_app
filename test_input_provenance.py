"""Prevent model assumptions or user edits from being attributed to the CBI."""
import unittest

from cbi_data import official_inputs, latest_preset
from input_provenance import describe_input, audit_row, format_value
from test_cbi_data import workbook_bytes, NOW
from extract_cbi_data import parse_workbook


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = parse_workbook(workbook_bytes(), NOW.date())
        self.snapshot['source'] = {'file_url': 'https://cbi.iq/static/uploads/up/test.xlsx'}
        self.sources = official_inputs(self.snapshot)
        self.official = self.sources['سعر_الصرف_الرسمي']

    def test_only_six_verified_fields_are_official(self):
        self.assertEqual(len(self.sources), 6)
        self.assertNotIn('فاتورة_الرواتب_مليار', self.sources)
        self.assertNotIn('ايرادات_غير_نفطية_مليار', self.sources)
        self.assertNotIn('سعر_الصرف_الموازي', self.sources)
        self.assertEqual(self.official['period'], '2026-07')
        self.assertEqual(self.sources['اجمالي_النفقات_مليار']['period'], '2025')
        self.assertEqual(self.sources['واردات_سنوية_مليار_دولار']['value'], 71)

    def test_edit_and_restore_official_input(self):
        before = describe_input(1300, 1300, self.official)
        edited = describe_input(1400, 1300, self.official)
        restored = describe_input(1300, 1300, self.official)
        self.assertEqual(before['kind'], 'official')
        self.assertEqual(edited['kind'], 'manual')
        self.assertEqual(edited['reference'], 1300)
        self.assertEqual(edited['period'], '2026-07')
        self.assertEqual(restored['kind'], 'official')

    def test_coincidental_numeric_match_is_not_official(self):
        self.assertEqual(describe_input(1300, 1300)['kind'], 'assumption')
        self.assertEqual(describe_input(1300, 1300, historical=True)['kind'], 'reference')
        self.assertEqual(describe_input(1400, 1300, historical=True)['kind'], 'manual')

    def test_mismatched_reference_is_not_stamped_official(self):
        self.assertEqual(describe_input(1400, 1400, self.official)['kind'], 'manual')

    def test_edit_assumption_and_reorder_scenario_values(self):
        self.assertEqual(describe_input(72000, 68000)['kind'], 'manual')
        self.assertEqual(describe_input([80, 60], [60, 80])['kind'], 'assumption')
        self.assertEqual(describe_input([90, 60], [60, 80])['kind'], 'manual')
        self.assertEqual(describe_input(False, True)['kind'], 'manual')

    def test_audit_preserves_adopted_value_units_and_reference(self):
        row = audit_row('السعر الرسمي', describe_input(1400, 1300, self.official), 'دينار/دولار')
        self.assertEqual(row['القيمة المستخدمة'], '1,400')
        self.assertEqual(row['القيمة المرجعية'], '1,300')
        self.assertEqual(row['التصنيف'], 'معدّل يدويًا')
        self.assertEqual(row['الفترة المرجعية'], '2026-07')
        self.assertEqual(row['الوحدة'], 'دينار/دولار')
        self.assertEqual(row['رابط المصدر المرجعي'], self.official['source_url'])
        self.assertEqual(format_value(0.4), '0.4')

    def test_defaults_and_source_annotations_share_exact_values(self):
        config = latest_preset(self.snapshot, {'اسعار_الصرف_سيناريو': [1300, 1400]})
        for field, source in self.sources.items():
            if field == 'سعر_الصرف_الرسمي':
                continue  # يسبقه قرار مجلس الوزراء الأحدث؛ يغطيه الاختبار التالي
            self.assertEqual(config[field], source['value'])

    def test_cabinet_decision_supersedes_only_an_older_cbi_period(self):
        from reported_inputs import REPORTED_INPUTS, PARALLEL_AFTER_DECISION, supersedes
        fx = REPORTED_INPUTS['سعر_الصرف_الرسمي']
        self.assertEqual(self.official['period'], '2026-07')
        self.assertTrue(supersedes(fx, '2026-07'))
        self.assertFalse(supersedes(fx, '2026-10'))   # نشرة تغطي شهر القرار: الرقم المنشور فيها يسبق
        self.assertFalse(supersedes(fx, '2026-11'))
        config = latest_preset(self.snapshot, {'اسعار_الصرف_سيناريو': [1300, 1400]})
        self.assertEqual(config['سعر_الصرف_الرسمي'], 1520.0)
        self.assertEqual(config['سعر_الصرف_الموازي'], PARALLEL_AFTER_DECISION)
        self.assertGreater(config['سعر_الصرف_الموازي'], config['سعر_الصرف_الرسمي'])  # فجوة موجبة
        self.assertIn(1520.0, config['اسعار_الصرف_سيناريو'])
        self.assertIn('544', config['وصف'])
        ok = describe_input(1520.0, 1520.0, reported=fx)
        self.assertEqual((ok['kind'], ok['period']), ('reported', '2026-10-07'))
        self.assertEqual(describe_input(1300.0, 1300.0, reported=fx)['kind'], 'manual')

    def test_reported_input_is_not_stamped_cbi_official(self):
        from reported_inputs import REPORTED_INPUTS
        ref = REPORTED_INPUTS['صادرات_مقاسة_مليون_برميل_يوم']
        self.assertNotIn('صادرات_مقاسة_مليون_برميل_يوم', self.sources)
        ok = describe_input(ref['value'], ref['value'], reported=ref)
        edited = describe_input(1.5, ref['value'], reported=ref)
        self.assertEqual((ok['kind'], ok['label']), ('reported', 'تصريح رسمي'))
        self.assertEqual(ok['period'], ref['period'])
        self.assertEqual(edited['kind'], 'manual')
        self.assertEqual(edited['reference'], ref['value'])
        # preset stale vs the sourced reference must not be stamped as reported
        self.assertEqual(describe_input(1.5, 1.5, reported=ref)['kind'], 'manual')
        row = audit_row('الصادرات', ok, 'مليون برميل/يوم')
        self.assertIn('وزارة النفط', row['أصل المرجع'])
        self.assertEqual(row['التصنيف'], 'تصريح رسمي')

    def test_latest_preset_carries_reported_exports_with_period(self):
        from reported_inputs import REPORTED_INPUTS
        ref = REPORTED_INPUTS['صادرات_مقاسة_مليون_برميل_يوم']
        config = latest_preset(self.snapshot, {
            'اسعار_الصرف_سيناريو': [1300.0], 'سعر_الصرف_الرسمي': 1300.0, 'وصف': ''})
        self.assertEqual(config['صادرات_مقاسة_مليون_برميل_يوم'], ref['value'])
        self.assertIn(ref['period'], config['وصف'])


if __name__ == '__main__':
    unittest.main()
