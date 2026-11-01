"""Failures in real SVR must surface without training another model."""
import unittest
from unittest.mock import patch

import numpy as np
from sklearn.svm import SVR

from backend.core import surrogate


class SvrErrorsTest(unittest.TestCase):
    def setUp(self):
        self.x = np.linspace(0, 1, 12).reshape(-1, 1)
        self.y = np.sin(self.x[:, 0] * 6)
        self.params = dict(c_min=1, c_max=1, g_min=.5, g_max=.5)

    def train(self):
        return surrogate.train_svr(self.x, self.y, self.x[:3], **self.params)

    def test_grid_training_and_prediction_errors_keep_original_reason(self):
        for method in ('fit', 'predict'):
            with self.subTest(method=method), \
                 patch.object(SVR, method, side_effect=ValueError('original failure')):
                with self.assertRaisesRegex(RuntimeError, '支持向量回归参数搜索失败.*ValueError.*original failure') as raised:
                    self.train()
                self.assertIsInstance(raised.exception.__cause__, ValueError)

    def test_final_training_error_is_explicit(self):
        original_fit = SVR.fit
        calls = 0

        def fail_on_final_fit(model, *args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError('final fit failed')
            return original_fit(model, *args, **kwargs)

        with patch.object(SVR, 'fit', fail_on_final_fit):
            with self.assertRaisesRegex(RuntimeError, '支持向量回归最终训练失败.*final fit failed'):
                self.train()

    def test_prediction_state_construction_error_is_explicit(self):
        with patch.object(surrogate, 'Predictor', side_effect=RuntimeError('state failed')) as predictor:
            with self.assertRaisesRegex(RuntimeError, '支持向量回归预测器构造失败.*state failed'):
                self.train()
        self.assertEqual(predictor.call_args.args[0], 'svr')
        self.assertEqual(predictor.call_count, 1)

    def test_final_prediction_error_is_explicit(self):
        original_predict = SVR.predict

        def fail_on_test(model, values):
            if len(values) == 3:
                raise RuntimeError('test prediction failed')
            return original_predict(model, values)

        with patch.object(SVR, 'predict', fail_on_test):
            with self.assertRaisesRegex(RuntimeError, '支持向量回归测试集预测失败.*test prediction failed'):
                self.train()

    def test_nonfinite_predictions_are_errors(self):
        for count, stage in ((12, '参数搜索'), (3, '测试集预测')):
            original_predict = SVR.predict

            def nonfinite(model, values):
                return np.full(len(values), np.nan) if len(values) == count else original_predict(model, values)

            with self.subTest(stage=stage), patch.object(SVR, 'predict', nonfinite):
                with self.assertRaisesRegex(RuntimeError, '支持向量回归' + stage + '失败.*非有限数'):
                    self.train()

    def test_invalid_search_ranges_do_not_use_default_parameters(self):
        for params in (dict(c_min=2, c_max=1), dict(g_step=0), dict(c_min=float('nan'))):
            with self.subTest(params=params):
                self.params.update(params)
                with self.assertRaisesRegex(RuntimeError, '支持向量回归参数搜索失败.*搜索范围'):
                    self.train()
                self.params = dict(c_min=1, c_max=1, g_min=.5, g_max=.5)


if __name__ == '__main__':
    unittest.main()
