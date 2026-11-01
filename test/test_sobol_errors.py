"""Sobol generates the selected sequence or reports its original failure."""
import os
import sys
import unittest
from copy import deepcopy
from dataclasses import asdict
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import numpy as np
from scipy.stats import qmc
from PyQt6.QtWidgets import QApplication

from backend.core import sampling
from backend.domain.models import ProjectData, FactorItem, ResponseItem
from backend.services import design_service
from frontend.pages.configuration_page import ConfigurationPage

APP = QApplication.instance() or QApplication([])


class SobolErrorsTest(unittest.TestCase):
    def test_points_match_real_scipy_sobol(self):
        expected = qmc.Sobol(d=3, scramble=False).random_base2(3)
        np.testing.assert_array_equal(sampling._sobol(8, 3), expected)

    def test_sampling_preserves_sobol_points_when_mapping_factor_bounds(self):
        rows = sampling.build_samples([('A', 0, 8, None), ('B', 10, 18, None)],
                                      4, '低差异序列 SOBOL', seed=12)
        self.assertEqual({(row['A'], row['B']) for row in rows},
                         {(0, 10), (4, 14), (6, 12), (2, 16)})

    def test_missing_dependency_reports_error_without_points(self):
        with patch.dict(sys.modules, {'scipy.stats': None}):
            with self.assertRaisesRegex(ValueError, '索博尔序列依赖加载失败.*ModuleNotFoundError') as raised:
                sampling._sobol(8, 2)
        self.assertIsInstance(raised.exception.__cause__, ModuleNotFoundError)

    def test_constructor_and_generation_errors_keep_the_original_reason(self):
        cases = ((patch.object(qmc, 'Sobol', side_effect=RuntimeError('constructor failed')), 'constructor failed'),
                 (patch.object(qmc.Sobol, 'random', side_effect=RuntimeError('generation failed')), 'generation failed'))
        for failure, message in cases:
            with self.subTest(message=message), failure:
                with self.assertRaisesRegex(ValueError, '索博尔序列生成失败.*RuntimeError.*' + message) as raised:
                    sampling._sobol(8, 2)
                self.assertIsInstance(raised.exception.__cause__, RuntimeError)

    def test_invalid_dimensions_report_error_without_replacement(self):
        with self.assertRaisesRegex(ValueError, '索博尔序列生成失败'):
            sampling._sobol(8, -1)

    def test_generation_failure_is_visible_and_preserves_the_existing_plan(self):
        failures = (lambda: patch.dict(sys.modules, {'scipy.stats': None}),
                    lambda: patch.object(qmc, 'Sobol', side_effect=RuntimeError('constructor failed')),
                    lambda: patch.object(qmc.Sobol, 'random', side_effect=RuntimeError('generation failed')))
        for failure in failures:
            with self.subTest(failure=failure):
                project = ProjectData(factors=[FactorItem(name=n, param1='-1', param2='1') for n in ('A', 'B')],
                                      responses=[ResponseItem(name='Y')])
                config = dict(model='Kriging', doe_method='Latin Hypercube (LHS)', sample_count=16)
                plan = design_service.model_plan(project, '代理模型建模 · Kriging', config)
                design_service.commit_plan(project, plan)
                page = ConfigurationPage(project)
                self.addCleanup(page.close)
                editor = page.model_editors['Kriging']
                editor.doe_method_combo.setCurrentIndex(editor.doe_method_combo.findData('低差异序列 SOBOL'))
                editor.sample_count_spin.setValue(16)
                page._preview_timer.stop()
                before, applied = deepcopy(asdict(project)), deepcopy(page._applied_state)
                with failure(), \
                     patch('frontend.pages.configuration_page.Notice.warning') as warning, \
                     patch('frontend.pages.configuration_page.Notice.information') as success:
                    page.gen_btn.click()
                warning.assert_called_once()
                self.assertIn('索博尔序列', warning.call_args.args[2])
                self.assertIn('失败', warning.call_args.args[2])
                success.assert_not_called()
                self.assertEqual(asdict(project), before)
                self.assertEqual(page._applied_state, applied)


if __name__ == '__main__':
    unittest.main()
