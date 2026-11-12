"""Approved setting/result zones preserve actions, data and hover guidance."""
import unittest
from PyQt6.QtWidgets import QLabel, QGroupBox
from frontend.pages.optimization_page import OptimizationPage
from backend.engines import optimizer as oe
from backend.services import analysis_service
from test_workbench_analysis import APP, make_context


class SettingsResultsLayoutTests(unittest.TestCase):
    def page(self):
        project, context = make_context()
        page = OptimizationPage(project)
        self.addCleanup(page.close)
        return project, context, page

    def test_model_information_uses_model_type_and_actions_follow_task(self):
        project, _, page = self.page()
        page.show()
        APP.processEvents()
        for model, title in (('RSM', '二次响应面模型'), ('Kriging', '克里金模型'),
                             ('SVR', '支持向量回归模型'), ('ANN', '神经网络模型')):
            project.design_method = '响应曲面设计' if model == 'RSM' else f'代理模型建模 · {model}'
            project.surrogate_config = {'model': model}
            page._refresh_view()
            info = page.overview.info_values
            self.assertEqual(info[0][0].text(), '当前模型')
            self.assertEqual(info[0][1].text(), title)
            self.assertEqual(info[1][1].text(), '35 次')
            self.assertTrue(info[2][0].isHidden())
            self.assertEqual(page.overview.info.layout().stretch(2), 0)
        project.design_method = '田口设计'
        page._refresh_view()
        APP.processEvents()
        self.assertEqual(page.overview.settings_heading.text(), '方案分析设置')
        self.assertGreaterEqual(page.primary_actions.indexOf(page.run_all_btn), 0)
        self.assertTrue(page.stats_btn.isHidden())
        self.assertTrue(page.run_all_btn.isVisible())
        project.design_method = '响应曲面设计'
        page._refresh_view()
        self.assertGreaterEqual(page.robust_settings_header.indexOf(page.run_all_btn), 0)
        self.assertGreaterEqual(page.overview.settings_header.indexOf(page.stats_btn), 0)
        self.assertFalse(page.stats_btn.isHidden())

    def test_result_cleanup_preserves_numerical_results_and_hover_explanations(self):
        _, context, page = self.page()
        result = oe.robust_optimize(context, pop=8, gen=2)
        widget = page.robust_results
        widget.set_result(context, result)
        self.assertEqual(set(widget.comparison.tables), {'schemes', 'factors', 'responses'})
        self.assertEqual(result['population_size'], 8)
        self.assertIn('k_constraint', result)
        self.assertEqual(widget.comparison.tables['factors'].rowCount(), 2)
        self.assertEqual(widget.comparison.tables['responses'].rowCount(), 1)
        labels = widget.findChildren(QLabel)
        self.assertFalse(any(x.text().startswith(('越大越好', '越小越好', '越接近零', '均值和标准差基于', '余量为负')) for x in labels))
        self.assertFalse(any(g.title() == '推荐设计指标' for g in widget.findChildren(QGroupBox)))
        groups = {g.title(): g for g in widget.comparison.findChildren(QGroupBox)+widget.verification.findChildren(QGroupBox)}
        self.assertNotIn('求解统计与设置', groups)
        self.assertIn('局部二阶矩近似', groups['当前方案 · 响应结果'].toolTip())
        self.assertIn('不是预测置信区间', groups['约束核验'].toolTip())

    def test_titles_match_and_zones_keep_separation(self):
        _, _, page = self.page()
        page.show()
        titles = [page.overview.settings_heading, page.model_overview.heading,
                  page.robust_settings_heading, page.robust_results.heading]
        self.assertTrue(all(x.property('role') == 'sectionHeading' for x in titles))
        for width, height in ((1050, 700), (1440, 940)):
            page.resize(width, height)
            for tab in (page.tab_overview, page.tab_robust):
                page.tabs.setCurrentWidget(tab)
                APP.processEvents()
            self.assertGreaterEqual(page.robust_results.y()-page.robust_settings_zone.geometry().bottom(), 24)
            self.assertEqual(page.robust_scroll.horizontalScrollBar().maximum(), 0)
            page.tabs.setCurrentWidget(page.tab_overview)
            APP.processEvents()
            self.assertGreaterEqual(page.model_overview.y()-page.overview.scheme_zone.geometry().bottom(), 24)
