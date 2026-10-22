"""Real numerical models survive task archives and fresh-process prediction."""
import json
import builtins
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

import numpy as np
from backend.domain.models import ProjectData, FactorItem, ResponseItem
from backend.services import model_service, task_storage
from backend.services.project_service import ProjectService
from backend.core.response_models import model_predict
from test_workbench_analysis import make_context


def surrogate_project(model, **params):
    rng = np.random.default_rng(12)
    x = rng.uniform(-2, 3, (32, 2))
    p = ProjectData(factors=[FactorItem(name=n, param1='-2', param2='3') for n in ('A', 'B')],
        responses=[ResponseItem(name='Y')], design_method='代理模型建模',
        doe_matrix=[{'Run_ID': i+1, 'A': a, 'B': b, 'Y': a*a + b + .2*a*b}
                    for i, (a, b) in enumerate(x)],
        surrogate_config={'model': model, 'model_params': params})
    ProjectService.for_project(p).publish_results(surrogate_result=model_service.train_surrogates(p))
    return p


class TaskStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / 'temp')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def round_trip(self, p, filename='task.rodas'):
        path = self.root / filename
        digest = task_storage.save_task(p, path)
        restored = task_storage.load_task(path)
        self.assertEqual(task_storage.fingerprint(restored), digest)
        return restored, path

    def test_empty_partial_data_and_literal_reserved_keys(self):
        p = ProjectData(factors=[FactorItem(name='厚度', param1='1', param2='2')],
            responses=[ResponseItem(name='位移', unit='mm')],
            doe_matrix=[{'Run_ID': 1, '厚度': 1., '位移': ''}],
            design_params={'type': 'array', 'items': {'type': 'predictor'}})
        restored, _ = self.round_trip(p)
        self.assertEqual(restored, p)
        self.assertEqual(list(restored.doe_matrix[0]), list(p.doe_matrix[0]))
        self.round_trip(ProjectData(), 'empty.rodas')

    def test_response_surface_restores_without_refit_and_invalidates_after_edit(self):
        p, _ = make_context()
        context = model_service.build_rsm_context(p)
        restored, _ = self.round_trip(p)
        with patch.object(model_service.optimizer, 'build_models', side_effect=AssertionError('must not fit')):
            loaded = model_service.build_rsm_context(restored)
            for point in ([0, 0], [.2, -.5], [1, 1]):
                self.assertAlmostEqual(model_predict(context['models']['Y'], point),
                                       model_predict(loaded['models']['Y'], point), places=12)
        rows = [dict(row) for row in restored.doe_matrix]
        rows[0]['Y'] += 1
        ProjectService.for_project(restored).update_responses(rows)
        self.assertFalse(ProjectService.for_project(restored).model_cache)

    def test_surrogates_preserve_predictions_for_all_current_kernels_and_correlations(self):
        cases = [('Kriging', {'correlation': c}) for c in ('Gaussian', '指数', 'Matern 3/2')]
        cases += [('SVR', {'kernel': k, 'c_min': 1, 'c_max': 1, 'g_min': .5, 'g_max': .5})
                  for k in ('RBF 核', '多项式核', 'Sigmoid 核')]
        cases += [('ANN', {'activation': a, 'epochs': 50}) for a in ('sigmoid', 'tanh', 'relu')]
        for kind, params in cases:
            with self.subTest(kind=kind, params=params):
                p = surrogate_project(kind, **params)
                original = p.surrogate_result['responses']['Y']
                predictor = original['predict_fn']
                # The training return uses the original solver's held-out predictions.
                x = np.array([[(row[n]+2)/5 for n in ('A', 'B')] for row in p.doe_matrix])
                test_rows = np.random.default_rng(2026).permutation(len(x))[:round(len(x)*.2)]
                np.testing.assert_allclose(predictor.predict(x[test_rows]), original['predicted'], rtol=1e-10, atol=1e-12)
                restored, _ = self.round_trip(p)
                before, _ = model_service.build_surrogate_context(p)
                with patch.object(model_service, 'train_surrogates', side_effect=AssertionError('must not train')):
                    after, errors = model_service.build_surrogate_context(restored)
                self.assertFalse(errors)
                for point in ([0, 0], [.2, -.5], [2, 1]):
                    self.assertAlmostEqual(model_predict(before['models']['Y'], point),
                                           model_predict(after['models']['Y'], point), places=12)

    def test_predictive_models_work_in_a_fresh_process(self):
        paths, expected = [], []
        for i, kind in enumerate(('Kriging', 'SVR', 'ANN')):
            params = {'epochs': 50} if kind == 'ANN' else {}
            if kind == 'SVR':
                params = dict(c_min=1, c_max=1, g_min=.5, g_max=.5)
            p = surrogate_project(kind, **params)
            context, _ = model_service.build_surrogate_context(p)
            expected.append(model_predict(context['models']['Y'], [.3, -.4]))
            _, path = self.round_trip(p, f'{i}.rodas')
            paths.append(str(path))
        code = '''import sys,json
from backend.services import task_storage,model_service
from backend.core.response_models import model_predict
def no_train(*a,**k): raise AssertionError('unexpected training')
model_service.train_surrogates=no_train
values=[]
for path in sys.argv[1:]:
    p=task_storage.load_task(path)
    c,e=model_service.build_surrogate_context(p)
    assert not e,e
    values.append(model_predict(c['models']['Y'],[.3,-.4]))
print(json.dumps(values))'''
        result = subprocess.run([sys.executable, '-c', code, *paths], cwd=Path(__file__).resolve().parents[1],
                                env=dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1])),
                                capture_output=True, text=True, timeout=40)
        self.assertEqual(result.returncode, 0, result.stderr)
        np.testing.assert_allclose(json.loads(result.stdout), expected, rtol=1e-12)

    def test_numpy_fallback_models_are_also_predictive_after_restore(self):
        original_import = builtins.__import__

        def without_sklearn(name, *args, **kwargs):
            if name.startswith('sklearn'):
                raise ImportError('exercise numpy fallback')
            return original_import(name, *args, **kwargs)

        for kind, params in [('SVR', dict(c_min=1, c_max=1, g_min=.5, g_max=.5)),
                             ('ANN', dict(epochs=40))]:
            with self.subTest(kind=kind):
                with patch.object(builtins, '__import__', side_effect=without_sklearn):
                    p = surrogate_project(kind, **params)
                result = p.surrogate_result['responses']['Y']
                self.assertIn(result['predict_fn'].kind, ('krr', 'ann'))
                restored, _ = self.round_trip(p)
                loaded = restored.surrogate_result['responses']['Y']['predict_fn']
                self.assertAlmostEqual(loaded([.25, .75]), result['predict_fn']([.25, .75]), places=12)

    def test_atomic_failure_keeps_existing_task_and_removes_temporary_file(self):
        _, path = self.round_trip(ProjectData())
        before = path.read_bytes()
        with patch.object(task_storage.os, 'replace', side_effect=OSError('simulated failure')):
            with self.assertRaises(OSError):
                task_storage.save_task(ProjectData(design_method='changed'), path)
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse(list(self.root.glob('*.tmp')))

    def test_unwritable_destination_fails_immediately_without_touching_original(self):
        _, path = self.round_trip(ProjectData())
        before = path.read_bytes()
        with patch.object(Path, 'open', side_effect=PermissionError('read-only destination')):
            with self.assertRaises(PermissionError):
                task_storage.save_task(ProjectData(), path)
        self.assertEqual(path.read_bytes(), before)

    def test_corrupt_or_unsupported_archive_is_rejected(self):
        _, path = self.round_trip(ProjectData())
        with ZipFile(path) as archive:
            manifest = json.loads(archive.read('task.json'))
        manifest['version'] = 999
        with ZipFile(path, 'w') as archive:
            archive.writestr('task.json', json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, '版本'):
            task_storage.load_task(path)
        path.write_bytes(b'not a task')
        with self.assertRaises(ValueError):
            task_storage.load_task(path)


if __name__ == '__main__':
    unittest.main()
