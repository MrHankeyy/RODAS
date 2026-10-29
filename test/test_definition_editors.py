"""Business forms, independent ranges, uncertainty values and archive compatibility."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile, ZIP_DEFLATED

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6.QtWidgets import QApplication, QCheckBox, QPushButton, QLabel
from backend.domain.models import FactorItem, ProjectData, ResponseItem
from backend.core.factors import factor_limits, factor_center
from backend.core.design_evaluation import _sigma_of_factor, robust_moments
from backend.services import design_service, model_service, task_storage
from backend.services.project_service import ProjectService
from frontend.pages.modeling_page import ModelingPage
from frontend.pages.definition_editors import DefinitionTable, FactorTable, ResponseTable, FactorEditor, ResponseEditor

APP = QApplication.instance() or QApplication([])


def factor(name='b', source='设计', probability=False):
    design = source == '设计'
    return FactorItem(name=name, source=source, nominal_lower='40' if design else '', nominal_upper='60' if design else '',
                      uncertainty='概率' if probability else '区间',
                      distribution='正态分布' if probability else '无',
                      param1=('0' if design else '50') if probability else ('-.2' if design else '40'),
                      param2='.01' if probability else ('.2' if design else '60'), unit='mm')


class DefinitionEditorTests(unittest.TestCase):
    def page(self):
        project = ProjectData(factors=[factor(), factor('T', '环境', True)],
                              responses=[ResponseItem(name='Y', kind='目标', feature='望小')])
        page = ModelingPage(project)
        page.load_project_data()
        self.addCleanup(page.close)
        return page, project

    def test_all_sections_share_compact_tables_and_factor_fields(self):
        page, project = self.page()
        self.assertIsInstance(page.design_factors, FactorTable)
        self.assertIsInstance(page.environment_factors, FactorTable)
        self.assertIsInstance(page.responses, ResponseTable)
        self.assertEqual(page.design_factors.table.cellWidget(0, 0).text(), 'b')
        table = page.design_factors.table
        self.assertEqual(table.columnCount(), 8)
        self.assertEqual(table.horizontalHeaderItem(5).text(), '不确定性参数')
        self.assertIs(table.cellWidget(0, 1), page.design_factors.editors[0].lower)
        self.assertIs(table.cellWidget(0, 2), page.design_factors.editors[0].upper)
        self.assertLessEqual(table.rowHeight(0), 40)
        for section, name in ((page.responses, 'Y'), (page.environment_factors, 'T')):
            self.assertIsInstance(section, DefinitionTable)
            self.assertEqual(section.table.cellWidget(0, 0).text(), name)
        self.assertFalse(page.findChildren(QPushButton, 'fixed_value'))
        self.assertFalse(any('固定' in b.text() for b in page.findChildren(QPushButton)))
        self.assertFalse(page.design_factors.findChildren(QCheckBox))
        self.assertIn('不确定性偏差 Δ', page.design_factors.relation.text())
        environment = page.environment_factors
        self.assertEqual(environment.table.columnCount(), 6)
        self.assertNotIn('lower', environment.editors[0].__dict__)
        self.assertFalse(hasattr(environment, 'relation'))

    def test_switching_type_and_item_preserves_each_draft(self):
        page, project = self.page()
        editor = page.design_factors.editors[0]
        editor.delta_lower.setText('-.45')
        editor.set_mode(1)
        editor.mean.setText('.1')
        editor.stddev.setText('.2')
        page.design_factors.add(factor('h'))
        page.design_factors.set_current_index(0)
        editor.set_mode(0)
        self.assertEqual(editor.delta_lower.text(), '-.45')
        self.assertEqual(editor.mean.text(), '.1')
        self.assertEqual(editor.stddev.text(), '.2')
        self.assertEqual(editor.parameters.currentIndex(), 0)
        self.assertEqual(project.factors[0].param1, '-.2')
        editor.set_mode(1)
        self.assertAlmostEqual(float(editor.collect().param2), .04)

    def test_explicit_save_and_invalid_save_are_atomic(self):
        page, project = self.page()
        editor = page.design_factors.editors[0]
        editor.lower.setText('30')
        page.model_tabs.setCurrentIndex(2)
        self.assertEqual(project.factors[0].nominal_lower, '40')
        editor.delta_upper.setText('-2')
        with patch('frontend.pages.modeling_page.Notice.warning') as notice:
            page.save_btn.click()
            notice.assert_called_once()
        self.assertEqual(project.factors[0].nominal_lower, '40')
        editor.delta_upper.setText('.2')
        page.save_btn.click()
        self.assertEqual(project.factors[0].nominal_lower, '30')
        self.assertEqual(page.save_status_label.text(), '已保存')

    def test_deleting_middle_last_and_all_items_tracks_correct_editor(self):
        page, _ = self.page()
        section = page.design_factors
        section.add(factor('h'))
        section.add(factor('t'))
        section.editors[1].delete_btn.click()
        self.assertEqual([e.name.text() for e in section.editors], ['b', 't'])
        self.assertIs(section.table.cellWidget(1, 0), section.editors[1].name)
        section.clear()
        self.assertEqual(section.table.rowCount(), 0)
        section.add(factor('new'))
        self.assertEqual(section.table.cellWidget(0, 0).text(), 'new')

    def test_response_thresholds_change_without_comma_encoding_in_ui(self):
        editor = ResponseEditor(ResponseItem(name='Y', kind='目标+约束', feature='望目', lower='2', upper='5'))
        self.addCleanup(editor.close)
        self.assertEqual(editor.limits.currentIndex(), 1)
        editor.feature.setCurrentText('望小')
        editor.limit.setText('6')
        self.assertEqual(editor.limit_label.text(), '上限')
        self.assertEqual(editor.collect().robust_limit, '6')
        editor.feature.setCurrentText('望目')
        self.assertEqual((editor.collect().lower, editor.collect().upper), ('2', '5'))
        editor.lower.setText('7')
        with self.assertRaisesRegex(ValueError, '下限'):
            editor.collect()

    def test_finite_values_stddev_duplicate_names_and_legacy_missing_deviation(self):
        page, _ = self.page()
        editor = page.environment_factors.editors[0]
        editor.stddev.setText('-1')
        with self.assertRaisesRegex(ValueError, '标准差'):
            page.sync_to_project_data()
        editor.stddev.setText('1e-8')
        editor.mean.setText('1e309')
        with self.assertRaisesRegex(ValueError, '有限'):
            page.sync_to_project_data()
        editor.mean.setText('0')
        editor.name.setText('b')
        with self.assertRaisesRegex(ValueError, '重复'):
            page.sync_to_project_data()
        legacy = FactorEditor('设计', FactorItem(name='old', param1='40', param2='60'))
        self.addCleanup(legacy.close)
        self.assertEqual((legacy.lower.text(), legacy.upper.text()), ('40.0', '60.0'))
        self.assertEqual(legacy.delta_lower.text(), '')
        with self.assertRaisesRegex(ValueError, '偏差参数'):
            legacy.collect()

    def test_nominal_range_and_input_sigma_are_independent(self):
        item = factor()
        sigma = _sigma_of_factor(item, 6)
        item.nominal_lower, item.nominal_upper = '1', '100'
        self.assertEqual(factor_limits(item), (1, 100))
        self.assertEqual(_sigma_of_factor(item, 6), sigma)
        item.param2 = '.4'
        self.assertGreater(_sigma_of_factor(item, 6), sigma)
        self.assertEqual(factor_limits(item), (1, 100))

    def test_design_bias_and_actual_environment_determine_response_center(self):
        design, environment = factor(), factor('T', '环境', True)
        design.param1, design.param2 = '1', '3'
        environment.param1 = '52'
        self.assertEqual(factor_center(design, {'b': 45}), 47)
        self.assertEqual(factor_center(environment), 52)
        model = dict(predict_fn=lambda x: x[0] + 2*x[1], grad_fn=lambda x: [1, 2],
                     hess_diag_fn=lambda x: [0, 0], residual_std=0)
        mu, sigma = robust_moments(model, {'b':45}, dict(inputs=[design, environment], names=['b','T']), 6)
        self.assertAlmostEqual(mu, 151)
        self.assertGreater(sigma, 0)

    def test_new_environment_factors_participate_in_doe_and_model(self):
        project = ProjectData(factors=[factor(), factor('T', '环境', True)], responses=[ResponseItem(name='Y')])
        plan = design_service.model_plan(project, '响应曲面设计', dict(model='RSM', doe_method='CCD'))
        self.assertTrue(all('T' in row for row in plan.rows))
        design_service.commit_plan(project, plan)
        for row in project.doe_matrix:
            row['Y'] = row['b'] + 2*row['T']
        context = model_service.build_rsm_context(project)
        self.assertEqual(context['names'], ['b','T'])
        mu, sigma = robust_moments(context['models']['Y'], {'b':45}, context, 6)
        self.assertAlmostEqual(mu, 145)
        self.assertGreater(sigma, .19)

    def test_new_definitions_roundtrip_and_legacy_v1_archive_is_readable(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / 'temp') as directory:
            path = Path(directory) / 'new.rodas'
            project = ProjectData(factors=[factor(), factor('T','环境',True)])
            task_storage.save_task(project, path)
            self.assertEqual(task_storage.load_task(path), project)
            legacy = ProjectData(factors=[FactorItem(name='old', param1='1',param2='2')])
            task_storage.save_task(legacy, path)
            with ZipFile(path) as archive:
                manifest = json.loads(archive.read('task.json'))
            def remove_new_keys(value):
                if isinstance(value, dict) and value.get('type') == 'map':
                    value['items'] = [[k, v] for k, v in value['items'] if k not in ('nominal_lower','nominal_upper')]
                    for _, v in value['items']:
                        remove_new_keys(v)
                elif isinstance(value, list):
                    for v in value:
                        remove_new_keys(v)
            remove_new_keys(manifest['document'])
            manifest['version'] = 1
            with ZipFile(path,'w',ZIP_DEFLATED) as archive:
                archive.writestr('task.json', json.dumps(manifest, ensure_ascii=False))
            self.assertEqual(task_storage.load_task(path), legacy)

    def test_new_environment_surrogate_roundtrip_preserves_prediction_dimensions(self):
        project = ProjectData(factors=[factor(), factor('T','环境',True)], responses=[ResponseItem(name='Y')])
        plan = design_service.model_plan(project, '代理模型建模 · Kriging',
                                        dict(model='Kriging',doe_method='Latin Hypercube (LHS)',sample_count=15))
        design_service.commit_plan(project, plan)
        for row in project.doe_matrix:
            row['Y'] = row['b'] + 2*row['T']
        service = ProjectService.for_project(project)
        service.ensure_current()
        service.publish_results(surrogate_result=model_service.train_surrogates(project))
        before, errors = model_service.build_surrogate_context(project)
        self.assertFalse(errors)
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / 'temp') as directory:
            path = Path(directory) / 'environment.rodas'
            task_storage.save_task(project, path)
            restored = task_storage.load_task(path)
            with patch.object(model_service, 'train_surrogates', side_effect=AssertionError('must not retrain')):
                after, errors = model_service.build_surrogate_context(restored)
            self.assertFalse(errors)
            self.assertEqual(after['names'], ['b','T'])
            self.assertAlmostEqual(before['models']['Y']['predict_fn']([45,50]),
                                   after['models']['Y']['predict_fn']([45,50]), places=12)

    def test_table_rows_switch_parameters_independently_and_keep_hidden_drafts(self):
        page, _ = self.page()
        section = page.design_factors
        first = section.editors[0]
        second = section.add(factor('h', probability=True))
        first.delta_lower.setText('-.35')
        self.assertEqual(first.distribution_cell.currentWidget().currentText(), '无')
        self.assertFalse(first.distribution_cell.currentWidget().isEnabled())
        self.assertIs(second.distribution_cell.currentWidget(), second.distribution)
        first.type_combo.setCurrentIndex(1)
        first.mean.setText('.1')
        first.stddev.setText('.2')
        self.assertIs(first.distribution_cell.currentWidget(), first.distribution)
        second.type_combo.setCurrentIndex(0)
        self.assertAlmostEqual(float(first.collect().param2), .04)
        self.assertEqual(second.parameters.currentIndex(), 0)
        first.type_combo.setCurrentIndex(0)
        self.assertEqual(first.delta_lower.text(), '-.35')
        first.type_combo.setCurrentIndex(1)
        self.assertEqual(first.mean.text(), '.1')
        self.assertIs(section.table.cellWidget(1, 5), second.parameters)
        self.assertTrue(second.delta_upper.isVisibleTo(second.parameters))
        first.distribution.setCurrentText('均匀分布')
        first.type_combo.setCurrentIndex(0)
        first.type_combo.setCurrentIndex(1)
        self.assertEqual(first.distribution.currentText(), '均匀分布')
        self.assertIn('偏差标准差', first.stddev.toolTip())
        self.assertIn('mm', first.stddev.toolTip())
        self.assertNotIn('²', first.stddev.toolTip())

    def test_dynamic_parameter_names_follow_type_and_distribution_per_row(self):
        page, _ = self.page()
        editor = page.design_factors.editors[0]
        labels = lambda: [label.text() for label in editor.parameters.currentWidget().findChildren(QLabel)]
        self.assertEqual(labels(), ['下界', '上界'])
        editor.type_combo.setCurrentIndex(1)
        self.assertEqual(labels(), ['均值', '标准差'])
        editor.mean.setText('0.1')
        editor.stddev.setText('0.2')
        editor.distribution.setCurrentText('均匀分布')
        self.assertEqual(labels(), ['下界', '上界'])
        editor.uniform_lower.setText('-.3')
        editor.uniform_upper.setText('.5')
        editor.distribution.setCurrentText('正态分布')
        self.assertEqual((editor.mean.text(), editor.stddev.text()), ('0.1', '0.2'))
        editor.distribution.setCurrentText('均匀分布')
        editor.set_mode(0)
        self.assertEqual(editor.delta_lower.text(), '-.2')
        editor.set_mode(1)
        self.assertEqual((editor.uniform_lower.text(), editor.uniform_upper.text()), ('-.3', '.5'))
        editor.unit.setText('cm')
        self.assertIn('cm', editor.uniform_lower.toolTip())
        self.assertIn('cm', editor.stddev.toolTip())
        self.assertNotIn('²', editor.stddev.toolTip())

    def test_uniform_bounds_convert_to_existing_moments_and_roundtrip(self):
        page, project = self.page()
        editor = page.design_factors.editors[0]
        editor.set_mode(1)
        editor.distribution.setCurrentText('均匀分布')
        editor.uniform_lower.setText('-2')
        editor.uniform_upper.setText('4')
        page.save_btn.click()
        item = project.factors[0]
        self.assertAlmostEqual(float(item.param1), 1)
        self.assertAlmostEqual(float(item.param2), 3)
        self.assertEqual(factor_center(item, {'b': 45}), 46)
        self.assertAlmostEqual(_sigma_of_factor(item, 6), 3**.5)
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / 'temp') as directory:
            path = Path(directory) / 'uniform.rodas'
            task_storage.save_task(project, path)
            restored = FactorEditor('设计', task_storage.load_task(path).factors[0])
            self.addCleanup(restored.deleteLater)
            self.assertEqual((restored.uniform_lower.text(), restored.uniform_upper.text()), ('-2', '4'))
            self.assertEqual(restored.collect(), item)

    def test_old_uniform_moments_remain_exact_when_bounds_not_edited(self):
        item = factor(probability=True)
        item.distribution, item.param1, item.param2 = '均匀分布', '1.2345678901234567', '0.9876543210987654'
        editor = FactorEditor('设计', item)
        self.addCleanup(editor.deleteLater)
        self.assertEqual(editor.collect(), item)
        editor.uniform_upper.setText('4')
        updated = editor.collect()
        self.assertNotEqual(updated.param2, item.param2)
        self.assertEqual(updated.nominal_lower, item.nominal_lower)
        legacy = FactorEditor('设计', FactorItem(name='old', uncertainty='概率', distribution='均匀分布',
                                                param1='50', param2='3'))
        self.addCleanup(legacy.deleteLater)
        converted = legacy.collect()
        self.assertEqual(converted.param1, '0')
        self.assertEqual((legacy.uniform_lower.text(), legacy.uniform_upper.text()), ('-3', '3'))
        self.assertEqual(factor_center(converted), 50)

    def test_invalid_uniform_bounds_block_submission_and_leave_project_unchanged(self):
        page, project = self.page()
        editor = page.design_factors.editors[0]
        editor.set_mode(1)
        editor.distribution.setCurrentText('均匀分布')
        for lower, upper in (('', '1'), ('2', '-1'), ('1e309', '2'), ('-1e308', '1e308')):
            editor.uniform_lower.setText(lower)
            editor.uniform_upper.setText(upper)
            with patch('frontend.pages.modeling_page.Notice.warning') as notice:
                page.save_btn.click()
                notice.assert_called_once()
            self.assertEqual(project.factors[0], factor())

    def test_design_and_environment_only_offer_normal_and_uniform_distributions(self):
        for source in ('设计', '环境'):
            editor = FactorEditor(source, factor(source=source, probability=True))
            self.addCleanup(editor.deleteLater)
            self.assertEqual([editor.distribution.itemText(i) for i in range(editor.distribution.count())],
                             ['正态分布', '均匀分布'])

    def test_environment_uniform_table_preserves_drafts_and_commits_only_on_save(self):
        page, project = self.page()
        editor = page.environment_factors.editors[0]
        editor.mean.setText('.1')
        editor.distribution.setCurrentText('均匀分布')
        editor.uniform_lower.setText('-2')
        editor.uniform_upper.setText('4')
        page.model_tabs.setCurrentIndex(0)
        self.assertEqual(project.factors[1].param1, '50')
        editor.distribution.setCurrentText('正态分布')
        self.assertEqual(editor.mean.text(), '.1')
        editor.distribution.setCurrentText('均匀分布')
        page.save_btn.click()
        item = project.factors[1]
        self.assertEqual(item.source, '环境')
        self.assertAlmostEqual(float(item.param1), 1)
        self.assertAlmostEqual(float(item.param2), 3)
        self.assertEqual((item.nominal_lower, item.nominal_upper), ('', ''))
        self.assertFalse(hasattr(page.environment_factors, 'relation'))
        page.load_project_data()
        editor = page.environment_factors.editors[0]
        self.assertEqual((editor.uniform_lower.text(), editor.uniform_upper.text()), ('-2', '4'))

    def test_environment_intervals_collect_actual_values_and_keep_current_sigma_rule(self):
        editor = FactorEditor('环境', FactorItem(name='T', source='环境', param1='20', param2='40', unit='℃'))
        self.addCleanup(editor.deleteLater)
        item = editor.collect()
        self.assertEqual((item.nominal_lower, item.nominal_upper), ('', ''))
        self.assertEqual(factor_limits(item), (20, 40))
        self.assertEqual(factor_center(item), 30)
        self.assertAlmostEqual(_sigma_of_factor(item, 6), 20/12)
        self.assertAlmostEqual(_sigma_of_factor(item, 3), 20/6)
        self.assertIn('环境实际取值下界', editor.delta_lower.toolTip())
        self.assertNotIn('偏差', editor.delta_lower.toolTip())

    def test_stddev_input_roundtrip_and_sampling_use_variance_once(self):
        for source in ('设计', '环境'):
            item = factor(source=source, probability=True)
            item.param2 = '.0225'
            editor = FactorEditor(source, item)
            self.addCleanup(editor.deleteLater)
            self.assertEqual(editor.stddev.text(), '0.15')
            self.assertEqual(editor.collect().param2, '.0225')
            editor.mean.setText('30')
            editor.stddev.setText('2')
            collected = editor.collect()
            self.assertEqual(float(collected.param2), 4)
            self.assertEqual(_sigma_of_factor(collected, 6), 2)
            if source == '环境':
                self.assertEqual(factor_limits(collected), (24, 36))
            with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / 'temp') as directory:
                path = Path(directory) / 'stddev.rodas'
                task_storage.save_task(ProjectData(factors=[collected]), path)
                restored = FactorEditor(source, task_storage.load_task(path).factors[0])
                self.addCleanup(restored.deleteLater)
                self.assertEqual(restored.stddev.text(), '2')
                self.assertEqual(restored.collect(), collected)
            editor.stddev.setText('1e200')
            with self.assertRaisesRegex(ValueError, '标准差过大'):
                editor.collect()

    def test_classical_designs_use_nominal_design_levels_and_actual_environment_levels(self):
        cases = [('区间', '无', '20', '40', [20, 40]),
                 ('概率', '正态分布', '30', '4', [24, 36]),
                 ('概率', '均匀分布', '30', str(100/3), [20, 40])]
        for uncertainty, distribution, p1, p2, bounds in cases:
            environment = FactorItem(name='T', source='环境', uncertainty=uncertainty,
                                     distribution=distribution, param1=p1, param2=p2)
            project = ProjectData(factors=[factor(), factor('h'), environment])
            for outer, levels in [('L4', bounds), ('L9', [bounds[0], sum(bounds)/2, bounds[1]])]:
                plan = design_service.taguchi_plan(project, '田口设计', 'L4', outer, 2,
                                                   seed=1, replicates=1, randomize=False, snr_mode='auto')
                self.assertEqual(plan.params['meta']['factor_levels']['b'], [40, 60])
                actual = plan.params['meta']['noise_levels']['T']
                for value, expected in zip(actual, levels):
                    self.assertAlmostEqual(value, expected)
                self.assertTrue(all('T' in row for row in plan.rows))
            plan = design_service.screening_plan(project, '筛选设计', 'full', seed=1,
                                                 centers=0, replicates=1, randomize=False, top_n=2)
            self.assertEqual({row['b'] for row in plan.rows}, {40, 60})
            self.assertTrue(all('T' not in row for row in plan.rows))

    def test_previous_nominal_environment_definitions_convert_to_actual_values_on_submit(self):
        for probability, distribution in ((False, '无'), (True, '正态分布'), (True, '均匀分布')):
            old = FactorItem(name='T', source='环境', nominal_lower='20', nominal_upper='40',
                             uncertainty='概率' if probability else '区间', distribution=distribution,
                             param1='2' if probability else '-1', param2='3' if probability else '1')
            editor = FactorEditor('环境', old)
            self.addCleanup(editor.deleteLater)
            actual = editor.collect()
            self.assertEqual((actual.nominal_lower, actual.nominal_upper), ('', ''))
            self.assertEqual(factor_center(actual), factor_center(old))
            self.assertAlmostEqual(_sigma_of_factor(actual, 6), _sigma_of_factor(old, 6))
            if not probability:
                self.assertEqual((float(actual.param1), float(actual.param2)), (29, 31))
            self.assertEqual(old.nominal_lower, '20')

    def test_actual_environment_distributions_drive_sampling_and_only_design_is_optimized(self):
        from backend.core.optimization import robust_optimize
        cases = [('区间', '无', '20', '40', (20, 40)),
                 ('概率', '正态分布', '30', '4', (24, 36)),
                 ('概率', '均匀分布', '30', str(100/3), (20, 40))]
        for uncertainty, distribution, p1, p2, bounds in cases:
            environment = FactorItem(name='T', source='环境', uncertainty=uncertainty,
                                     distribution=distribution, param1=p1, param2=p2)
            project = ProjectData(factors=[factor(), environment], responses=[ResponseItem(name='Y')])
            plan = design_service.model_plan(project, '响应曲面设计', dict(model='RSM', doe_method='CCD'))
            self.assertAlmostEqual(plan.params['model_config']['bounds']['T'][0], bounds[0])
            self.assertAlmostEqual(plan.params['model_config']['bounds']['T'][1], bounds[1])
            design_service.commit_plan(project, plan)
            for row in project.doe_matrix:
                row['Y'] = row['b'] + 2*row['T']
            context = model_service.build_rsm_context(project)
            self.assertEqual(context['names'], ['b', 'T'])
            mu, _ = robust_moments(context['models']['Y'], {'b':45}, context, 6)
            self.assertAlmostEqual(mu, 105)
            result = robust_optimize(context, mode='weighted', pop=8, gen=2)
            self.assertEqual(result['design_names'], ['b'])
            self.assertEqual(set(result['best']['x']), {'b'})

    def test_response_table_roles_thresholds_and_edits_clear_saved_status(self):
        page, project = self.page()
        editor = page.responses.editors[0]
        page.save_btn.click()
        self.assertEqual(page.save_status_label.text(), '已保存')
        editor.constraint.click()
        self.assertEqual(page.save_status_label.text(), '')
        editor.feature.setCurrentText('望目')
        editor.lower.setText('2')
        editor.upper.setText('5')
        editor.feature.setCurrentText('望大')
        self.assertEqual(editor.limit_label.text(), '下限')
        editor.limit.setText('1')
        editor.feature.setCurrentText('望目')
        page.model_tabs.setCurrentIndex(2)
        self.assertEqual(project.responses[0].feature, '望小')
        page.save_btn.click()
        self.assertEqual(project.responses[0].kind, '目标+约束')
        self.assertEqual((project.responses[0].lower, project.responses[0].upper), ('2', '5'))
        editor.objective.click()
        editor.constraint.click()
        with patch('frontend.pages.modeling_page.Notice.warning') as notice:
            page.save_btn.click()
            notice.assert_called_once()
        self.assertEqual(project.responses[0].kind, '目标+约束')

    def test_shared_deletion_and_reload_work_for_response_and_environment_tables(self):
        page, _ = self.page()
        for section, items in ((page.responses, [ResponseItem(name='Y2'), ResponseItem(name='Y3')]),
                               (page.environment_factors, [factor('T2', '环境'), factor('T3', '环境')])):
            for item in items:
                section.add(item)
            survivor = section.editors[2]
            section.editors[1].delete_btn.click()
            self.assertIs(section.table.cellWidget(1, 0), survivor.name)
            survivor.name.setText('survivor')
            survivor.delete_btn.click()
            self.assertEqual(section.table.rowCount(), 1)
            section.clear()
            self.assertEqual(section.table.rowCount(), 0)
        page.load_project_data()
        self.assertEqual(page.responses.table.rowCount(), 1)
        self.assertEqual(page.environment_factors.table.rowCount(), 1)

    def test_table_delete_buttons_track_rows_after_repeated_deletions(self):
        page, _ = self.page()
        section = page.design_factors
        for i in range(16):
            section.add(factor('X'+str(i), probability=i%2==0))
        victim = section.editors[7]
        survivor = section.editors[8]
        victim.delete_btn.click()
        self.assertIs(section.table.cellWidget(7, 0), survivor.name)
        survivor.type_combo.setCurrentIndex(1)
        self.assertEqual(survivor.parameters.currentIndex(), 1)
        survivor.delete_btn.click()
        self.assertNotIn(survivor, section.editors)
        self.assertEqual(section.table.rowCount(), len(section.editors))

    def test_table_columns_fill_viewport_after_window_resize(self):
        from frontend.main_window import MainWindow
        window = MainWindow()
        window.task_actions.confirm_leave = lambda **kwargs: True
        self.addCleanup(window.close)
        window.page_MOD.design_factors.add(factor())
        window.page_MOD.design_factors.add(factor('h', probability=True))
        window.show()
        window.switch_page(0)
        window.page_MOD.model_tabs.setCurrentIndex(1)
        table = window.page_MOD.design_factors.table
        previous = None
        for width,height in ((1050,700),(1440,940),(1920,1080),(1050,700)):
            window.resize(width,height)
            APP.processEvents()
            APP.processEvents()
            widths = [table.columnWidth(i) for i in range(table.columnCount())]
            total = sum(widths)
            self.assertGreaterEqual(total, table.viewport().width()-6)
            self.assertLessEqual(total, table.viewport().width())
            self.assertEqual(table.horizontalScrollBar().maximum(), 0)
            self.assertEqual(widths[6:], [60, 64])
            self.assertLess(widths[5], table.viewport().width() * .35)
            if previous is not None and width != 1050:
                growth = [widths[i] - previous[i] for i in range(6)]
                self.assertGreater(min(growth), 0)
                self.assertLessEqual(max(growth) - min(growth), 1)
            previous = widths

    def test_column_minima_survive_tight_space_and_vertical_scrollbar(self):
        from frontend.pages.table_widgets import BalancedColumnsTable
        table = BalancedColumnsTable((70, 80, 80, 90, 110, 250, 60, 64), fixed_columns=(6, 7))
        self.addCleanup(table.close)
        table.setRowCount(30)
        table.show()
        for width in (1100, 650, 900):
            table.resize(width, 220)
            APP.processEvents()
            APP.processEvents()
            widths = [table.columnWidth(i) for i in range(8)]
            self.assertGreater(table.verticalScrollBar().maximum(), 0)
            self.assertEqual(widths[6:], [60, 64])
            if width < 804:
                self.assertEqual(tuple(widths), table.minimum_widths)
                self.assertGreater(table.horizontalScrollBar().maximum(), 0)
            else:
                self.assertEqual(sum(widths), table.viewport().width())
                self.assertEqual(table.horizontalScrollBar().maximum(), 0)


if __name__ == '__main__':
    unittest.main()
