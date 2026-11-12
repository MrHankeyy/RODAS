"""Grouped statistics retain numerical results, missing causes and flat exports."""
import csv
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6.QtWidgets import QApplication, QFileDialog
from backend.core.workbench_analysis import diagnostics, descriptive, descriptive_missing_reasons
from backend.core.response_models import build_models
from backend.core.doe import build_response_surface
from backend.services import task_storage
from backend.domain.models import ProjectData, FactorItem, ResponseItem
from frontend.pages.model_overview import FitStatistics, ModelOverview
from backend.services import analysis_service
from frontend.pages.data_inspection import DataAnalysis
from frontend.notifications import Notice
from frontend.terminology import statistic_tooltip
from test_workbench_analysis import make_context

APP = QApplication.instance() or QApplication([])


def demo_context():
    rows, _meta = build_response_surface([('b', 40, 60, None), ('h', 90, 110, None)],
        'CCD', 'face', 1, 3, randomize=False)
    for row in rows:
        b, h = row['b'], row['h']
        row.update(D=round(4*1000*1000**3/(210000*b*h**3), 8), M=round(7.85e-6*1000*b*h, 8))
    project = ProjectData(design_method='二次响应面模型', doe_matrix=rows,
        factors=[FactorItem(name='b', nominal_lower='40', nominal_upper='60'),
                 FactorItem(name='h', nominal_lower='90', nominal_upper='110')],
        responses=[ResponseItem(name='D'), ResponseItem(name='M')])
    context, errors = build_models(project)
    assert not errors, errors
    return project, context


class FitStatisticsTests(unittest.TestCase):
    def test_demo_values_remain_unchanged_and_zero_pure_error_is_explained(self):
        _project, context = demo_context()
        result = diagnostics(context, 'D')
        values = {row['统计量']: row['值'] for row in result['summary']}
        self.assertAlmostEqual(values['残差平方和'], 6.472476905422404e-5, places=15)
        self.assertAlmostEqual(values['LOO PRESS'], .0006841963391102308, places=15)
        self.assertGreater(values['纯误差平方和'], 0)  # no rounding-to-zero change
        self.assertIsNone(values['失拟 F'])
        self.assertIn('纯误差为零或数值上接近零', result['missing_reasons']['summary']['失拟 F'])
        view = FitStatistics()
        self.addCleanup(view.close)
        view.set_statistics(result['summary'], result['missing_reasons']['summary'])
        self.assertEqual(len(view.cards), 3)
        self.assertEqual(len(view.values) + 1, len(result['summary']))
        self.assertEqual(view.values['失拟 F'].text(), '—')
        self.assertIn('纯误差', view.values['失拟 F'].toolTip())
        self.assertEqual(view.labels['失拟 F'].toolTip(), statistic_tooltip('失拟 F'))

    def test_resize_switch_and_clear_leave_no_stale_fields(self):
        _project, context = demo_context()
        view = FitStatistics()
        self.addCleanup(view.close)
        view.show()
        for width in (980, 420, 980, 360, 980):
            result = diagnostics(context, 'M' if width == 420 else 'D')
            view.set_statistics(result['summary'], result['missing_reasons']['summary'])
            view.resize(width, 700)
            for _ in range(5):
                APP.processEvents()
            expected_columns = 2 if view.width() >= 680 else 1
            self.assertEqual(view._columns, expected_columns)
            for table in view.tables:
                self.assertGreaterEqual(table.viewport().height(), sum(table.rowHeight(i) for i in range(table.rowCount())))
            self.assertTrue(view.values['失拟 F'].toolTip())
        view.clear()
        self.assertFalse(view.records)
        self.assertFalse(view.values)
        self.assertEqual(view.column.count(), 0)

    def test_response_switch_and_grouped_csv_json_exports(self):
        _project, context = demo_context()
        panel = ModelOverview()
        self.addCleanup(panel.close)
        panel.set_result(context, analysis_service.build_snapshot(context))
        panel.response.setCurrentText('M')
        self.assertEqual(panel.summary.values['回归 F'].text(), '—')
        self.assertIn('残差平方和', panel.summary.values['回归 F'].toolTip())
        panel.response.setCurrentText('D')
        self.assertNotEqual(panel.summary.values['回归 F'].text(), '—')
        self.assertFalse(panel.summary.values['回归 F'].toolTip())
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / 'temp') as directory:
            csv_path, json_path = Path(directory)/'summary.csv', Path(directory)/'statistics.json'
            with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(csv_path), '')), patch.object(Notice, 'information'):
                panel.export_csv()
            with csv_path.open(encoding='utf-8-sig', newline='') as stream:
                exported = list(csv.DictReader(stream))
            self.assertEqual(len(exported), len(panel.summary.records))
            self.assertIn('训练集', exported[0]['值'])
            self.assertIn('留一预测决定系数', [row['统计量'] for row in exported])
            with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(json_path), '')):
                panel.export_json()
            saved = json.loads(json_path.read_text(encoding='utf-8'))
            self.assertIn('纯误差', saved['responses']['D']['missing_reasons']['summary']['失拟 p'])
            _project.workbench_result = panel.snapshot
            task_path = Path(directory) / 'statistics.rodas'
            task_storage.save_task(_project, task_path)
            restored = task_storage.load_task(task_path)
            panel.set_result(context, restored.workbench_result)
            panel.response.setCurrentText('D')
            self.assertIn('纯误差', panel.summary.values['失拟 p'].toolTip())
        panel.clear()
        self.assertFalse(panel.summary.records)

    def test_missing_causes_distinguish_no_repeats_zero_residual_and_zero_df(self):
        project, context = make_context()
        result = diagnostics(context, 'Y')
        self.assertIn('没有相同输入', result['missing_reasons']['summary']['失拟 F'])
        project, context = make_context(False)
        result = diagnostics(context, 'Y')
        self.assertIn('残差平方和', result['missing_reasons']['summary']['回归 p'])
        self.assertIn('变化幅度过小', result['missing_reasons']['summary']['残差 Shapiro p'])
        self.assertTrue(result['missing_reasons']['coefficients'][0]['未校正 p'])
        project.doe_matrix = project.doe_matrix[:6]
        context, errors = build_models(project)
        self.assertFalse(errors)
        result = diagnostics(context, 'Y')
        self.assertIn('自由度不足', result['missing_reasons']['summary']['回归 F'])
        self.assertIn('不可识别', result['missing_reasons']['summary']['LOO PRESS'])

    def test_surrogate_uses_validation_source_and_missing_const_response_reason(self):
        _project, context = make_context()
        context['models']['Y'] = {'predict_fn': lambda point: 2., 'validation': {'actual': [2.], 'predicted': [2.], 'validation_inputs': [[0, 0]]}}
        result = diagnostics(context, 'Y')
        view = FitStatistics()
        self.addCleanup(view.close)
        view.set_statistics(result['summary'], result['missing_reasons']['summary'])
        self.assertIn('测试集', result['source'])
        self.assertIn('全部相同', view.values['R²'].toolTip())
        self.assertIn('少于2个', view.values['残差样本标准差'].toolTip())
        self.assertNotIn('参数数', view.values)

    def test_descriptive_missing_values_get_specific_reasons_after_refresh(self):
        project = ProjectData(responses=[ResponseItem(name='Y')])
        view = DataAnalysis(project)
        self.addCleanup(view.close)
        for values, key, phrase in (([1], '样本标准差', '少于2个'), ([1, 2], '偏度', '少于3个'),
                                    ([2, 2, 2, 2], '偏度', '全部相同'), ([1, 2, 3], '超额峰度', '少于4个')):
            project.doe_matrix = [{'Y': value} for value in values]
            view.refresh()
            cell = view.stat_values[key]
            self.assertEqual(cell.text(), '—')
            self.assertIn(phrase, cell.toolTip())
        project.responses.append(ResponseItem(name='Z'))
        rows = descriptive(project)
        missing = descriptive_missing_reasons(rows)
        self.assertIn('没有有效', missing[1]['均值'])


if __name__ == '__main__':
    unittest.main()
