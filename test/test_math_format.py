"""Math is presentation-only: preserve numbers, labels and exportable table data."""
import base64
from io import BytesIO
import re
import unittest

from PIL import Image
from PyQt6.QtWidgets import QComboBox

from backend.reporting.math_format import Math, formula_html, polynomial, rich_text, symbol
from backend.reporting import report_engine
from backend.services import analysis_service
from frontend.math_widgets import MATH_ROLE, decorate_combo
from frontend.pages.result_overview import SummaryTable
from test_workbench_analysis import APP, make_context


class MathFormatTests(unittest.TestCase):
    def test_polynomial_uses_encoded_subscripts_powers_and_fraction(self):
        _, context = make_context()
        model = context['models']['Y']
        coefficients = model['coef'].copy()
        terms, pieces, coding = polynomial('Y', model, context['names'])
        self.assertEqual(str(terms[1]), 'z_A')
        self.assertEqual(terms[1].latex, 'z_{A}')
        self.assertIn('^2', terms[2].latex)
        self.assertIn(r'\frac', coding[0].latex)
        for latex in pieces + [item.latex for item in coding]:
            self.assertIn('data:image/png;base64,', formula_html(latex))
        self.assertTrue((coefficients == model['coef']).all())

    def test_formula_images_have_transparent_background(self):
        content = formula_html(r'z_b=\frac{b-50}{10}')
        encoded = re.search(r'base64,([^" ]+)', content).group(1)
        with Image.open(BytesIO(base64.b64decode(encoded))) as image:
            self.assertEqual(image.mode, 'RGBA')
            low, high = image.getchannel('A').getextrema()
            self.assertEqual(low, 0)
            self.assertGreater(high, 0)

    def test_literal_names_and_prose_are_escaped(self):
        self.assertEqual(rich_text('<script>x</script>'), '&lt;script&gt;x&lt;/script&gt;')
        self.assertEqual(rich_text('path_name.csv'), 'path_name.csv')
        for name in ['b_1', '长度', 'a$b', 'Q{a}', r'a\b']:
            with self.subTest(name=name), self.assertNoLogs('matplotlib', level='WARNING'):
                self.assertIn('<img ', formula_html(symbol(name), name))
        for text in ['R²', 'x1²', 'x1·x2', 'σ=区间宽度/(2k)', 'μ±kσ', 'σ ≤ 2', '2^k']:
            self.assertIn('<img ', rich_text(text))

    def test_table_preserves_raw_data_and_reserves_fraction_height(self):
        value = Math('z_b = (b - 50) / 10', r'z_b=\frac{b-50}{10}')
        table = SummaryTable(['换算关系'], [[value]])
        self.addCleanup(table.deleteLater)
        self.assertEqual(table.item(0, 0).text(), str(value))
        self.assertIn('<img ', table.item(0, 0).data(MATH_ROLE))
        self.assertGreaterEqual(table.rowHeight(0), 32)

    def test_combo_keeps_configuration_keys(self):
        combo = QComboBox()
        self.addCleanup(combo.deleteLater)
        choices = ['全因子 2^k（小因子数）', '部分析因 1/2 分数']
        combo.addItems(choices)
        decorate_combo(combo)
        self.assertEqual([combo.itemText(i) for i in range(combo.count())], choices)
        self.assertIn('<img ', combo.itemData(0, MATH_ROLE))

    def test_report_uses_the_same_serializable_formulas(self):
        project, context = make_context()
        project.workbench_result = analysis_service.analyze(project, context, {})['snapshot']
        # Report export consumes a serializable snapshot, never a fitted callable.
        project.workbench_result = report_engine.serializable(project.workbench_result)
        report = report_engine.build_current_report(report_engine.bundle(project))
        formulas = [b for s in report['sections'] for b in s['blocks'] if b['type'] == 'formula']
        self.assertEqual(len(formulas), 3)
        html = report_engine.render_html(report)
        self.assertIn('z_{A}', html)
        self.assertIn('\\frac', html)
        self.assertIn('data:image/png;base64,', html)


if __name__ == '__main__':
    unittest.main()
