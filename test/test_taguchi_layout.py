"""Taguchi preview, actual observations, candidate honesty and round-trip results."""
import copy
import csv
import math
import statistics
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PyQt6.QtWidgets import QGroupBox
from backend.domain.models import ProjectData, FactorItem, ResponseItem
from backend.core import design_analysis as da
from backend.services import design_service, task_storage
from backend.services.project_service import ProjectService
from frontend.pages.configuration_page import ConfigurationPage
from frontend.pages.optimization_page import OptimizationPage
from frontend.pages.taguchi_results import TaguchiResultsPanel
from test_ui_constraints import APP


def beam():
    project = ProjectData(task_type='taguchi', factors=[
        FactorItem(name=n,nominal_lower=str(lo),nominal_upper=str(hi),param1='0',param2='0',unit='mm')
        for n,lo,hi in [('b',40,60),('h',90,110)]]+[
        FactorItem(name=n,source='环境',param1=str(lo),param2=str(hi),unit=unit)
        for n,lo,hi,unit in [('F',800,1200,'N'),('E',200000,220000,'MPa')]],
        responses=[ResponseItem(name='D',unit='mm')])
    plan = design_service.taguchi_plan(project,'田口设计','L4','L4',2,1103,5,True,'按各响应目标特征自动')
    design_service.commit_plan(project,plan)
    for row, error in zip(project.doe_matrix,np.random.default_rng(20261103).normal(0,.008,80)):
        row['D'] = round(4*row['F']*1000**3/(row['E']*row['b']*row['h']**3)+error,8)
    ProjectService.for_project(project).publish_results(taguchi_result=da.taguchi(project))
    return project


class TaguchiLayoutTests(unittest.TestCase):
    def panel(self, project):
        panel = TaguchiResultsPanel(project)
        self.addCleanup(panel.close)
        panel.set_result(project.taguchi_result)
        return panel

    def test_partitioned_preview_changes_without_replacing_observations(self):
        project = beam()
        original = copy.deepcopy(project.doe_matrix)
        page = ConfigurationPage(project)
        self.addCleanup(page.close)
        page._refresh_preview()
        self.assertEqual(page.taguchi_preview.counts.item(0,3).text(),'80')
        self.assertEqual(page.taguchi_preview.factors.rowCount(),4)
        titles = [g.title() for g in page.taguchi_widget.findChildren(QGroupBox)]
        for title in ('内表设置 · 控制因子','外表设置 · 噪声因子','重复与试验顺序','信噪比设置'):
            self.assertIn(title,titles)
        self.assertGreaterEqual(page.t_settings_header.indexOf(page.gen_btn),0)
        page.t_repeat_spin.setValue(3)
        page._refresh_preview()
        self.assertEqual(page.taguchi_preview.counts.item(0,3).text(),'48')
        self.assertEqual(project.doe_matrix,original)
        page.t_outer_combo.setCurrentIndex(0)
        page._refresh_preview()
        self.assertFalse(page.gen_btn.isEnabled())
        self.assertIn('外表',page.preview_label.text())
        self.assertEqual(project.doe_matrix,original)
        page.dynamic_params_widget.setCurrentIndex(1)
        page._on_selection_changed()
        self.assertGreaterEqual(page.actions.indexOf(page.gen_btn),0)

    def test_observation_groups_and_error_bars_match_independent_statistics(self):
        project = beam()
        expected = copy.deepcopy(project.taguchi_result)
        panel = self.panel(project)
        panel.select_inner(1)
        self.assertEqual(panel.environment_table.rowCount(),4)
        self.assertEqual(panel.raw_table.rowCount(),20)
        for i in range(4):
            values = [r['D'] for r in project.doe_matrix if r['内表组号']==1 and r['外表组号']==i+1]
            self.assertAlmostEqual(float(panel.environment_table.item(i,3).text()),5)
            self.assertAlmostEqual(float(panel.environment_table.item(i,4).text()),statistics.mean(values),delta=1e-6)
            self.assertAlmostEqual(float(panel.environment_table.item(i,5).text()),statistics.stdev(values),delta=1e-7)
        self.assertAlmostEqual(panel.run_figure.axes[0].collections[-1].get_offsets()[0,1],expected['response_analysis']['D']['runs'][0]['mean'])
        panel.raw_toggle.setChecked(True)
        self.assertFalse(panel.raw_table.isHidden())
        panel.factor_combo.setCurrentIndex(panel.factor_combo.findData('h'))
        np.testing.assert_allclose(panel.fig.axes[0].lines[0].get_xdata(),[90,110])
        self.assertEqual(project.taguchi_result,expected)
        project.doe_matrix.reverse()
        noise, environments, raw = da.taguchi_observations(project,'D',1)
        self.assertEqual(noise,['F','E'])
        self.assertEqual(len(raw),20)
        self.assertAlmostEqual(environments[0][4],statistics.mean([r['D'] for r in project.doe_matrix if r['内表组号']==1 and r['外表组号']==1]))

    def test_response_switching_keeps_candidates_separate_and_constraints_descriptive(self):
        project = beam()
        project.responses += [ResponseItem(name='Q',feature='望大'),ResponseItem(name='C',kind='约束')]
        for row in project.doe_matrix:
            row.update(Q=250-row['b']-row['h'],C=row['D'])
        project.taguchi_result = da.taguchi(project)
        self.assertEqual(project.taguchi_result['best_levels'],{})
        panel = self.panel(project)
        panel.response_combo.setCurrentIndex(panel.response_combo.findData('Q'))
        self.assertEqual([float(panel.candidate_table.item(i,1).text()) for i in range(2)],[40,90])
        panel.response_combo.setCurrentIndex(panel.response_combo.findData('C'))
        self.assertTrue(panel.candidate_table.isHidden())
        self.assertEqual(panel.observed_table.rowCount(),0)
        self.assertEqual(panel.table.rowCount(),4)
        self.assertEqual(panel.runs_table.rowCount(),4)

    def test_unobserved_candidate_has_no_fabricated_observed_statistics(self):
        project = ProjectData(task_type='taguchi',responses=[ResponseItem(name='Y')],factors=[
            FactorItem(name=n,nominal_lower='1',nominal_upper='2') for n in ('a','b','c')])
        plan = design_service.taguchi_plan(project,'田口设计','L4','无',2,7,2,True,'按各响应目标特征自动')
        design_service.commit_plan(project,plan)
        for r in project.doe_matrix:
            r['Y'] = 20-r['a']-r['b']-r['c']
        project.taguchi_result = da.taguchi(project)
        panel = self.panel(project)
        self.assertEqual(project.taguchi_result['best_levels'],dict(a=2,b=2,c=2))
        self.assertTrue(panel.observed_table.isHidden())
        self.assertIn('未在内表中出现',panel.observed_message.text())

    def test_single_observation_and_zero_loss_are_not_misreported(self):
        for repeats,value in ((1,1.),(2,0.)):
            with self.subTest(repeats=repeats):
                project = ProjectData(task_type='taguchi',responses=[ResponseItem(name='Y')],factors=[FactorItem(name='a',nominal_lower='1',nominal_upper='2')])
                plan = design_service.taguchi_plan(project,'田口设计','L4','无',2,7,repeats,True,'按各响应目标特征自动')
                design_service.commit_plan(project,plan)
                for row in project.doe_matrix:
                    row['Y'] = value
                project.taguchi_result = da.taguchi(project)
                panel = self.panel(project)
                if repeats==1:
                    self.assertIsNone(panel.runs_table.export_data[1][0][4])
                    self.assertIn('不能评估稳健性',panel.evaluation.text())
                else:
                    self.assertTrue(math.isinf(panel.table.export_data[1][0][4]))
                    self.assertTrue(any('+∞' in t.get_text() for t in panel.fig.axes[1].texts))

    def test_clear_restore_and_csv_export_preserve_full_numeric_results(self):
        project = beam()
        panel = self.panel(project)
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'temp') as directory:
            path = Path(directory)/'taguchi.rodas'
            task_storage.save_task(project,path)
            restored = task_storage.load_task(path)
            with patch.object(da,'taguchi',side_effect=AssertionError('restore recomputed')):
                other = self.panel(restored)
            self.assertEqual(other.table.export_data,panel.table.export_data)
            panel.details.setCurrentIndex(1)
            output = Path(directory)/'runs.csv'
            with patch('frontend.pages.taguchi_results.QFileDialog.getSaveFileName',return_value=(str(output),'')):
                panel.export_table()
            with output.open(encoding='utf-8-sig',newline='') as stream:
                rows = list(csv.reader(stream))
            self.assertEqual(len(rows),5)
            self.assertNotIn('观测明细',rows[0])
            self.assertAlmostEqual(float(rows[1][4]),project.taguchi_result['response_analysis']['D']['runs'][0]['mean'])
        panel.set_result({})
        self.assertEqual(panel.raw_table.rowCount(),0)
        self.assertEqual(panel.table.rowCount(),0)
        self.assertFalse(panel.export_button.isEnabled())
        panel.set_result(project.taguchi_result)
        self.assertEqual(panel.raw_table.rowCount(),20)

    def test_primary_action_is_accessible_in_overview_and_analysis(self):
        page = OptimizationPage(beam())
        self.addCleanup(page.close)
        page.tabs.setCurrentIndex(0)
        self.assertGreaterEqual(page.primary_actions.indexOf(page.run_all_btn),0)
        page.tabs.setCurrentIndex(8)
        self.assertGreaterEqual(page.taguchi_panel.settings_header.indexOf(page.run_all_btn),0)
