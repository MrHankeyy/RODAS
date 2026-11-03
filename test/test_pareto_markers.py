"""Selected Pareto designs must remain visible above the front and dense samples."""
import unittest

import matplotlib
import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from frontend.pages.optimization_plots import pareto


class ParetoMarkerTests(unittest.TestCase):
    def render(self, result, size=(6, 4), dpi=100):
        figure = Figure(figsize=size, dpi=dpi)
        canvas = FigureCanvasAgg(figure)
        with matplotlib.rc_context({'font.family': 'Microsoft YaHei'}):
            pareto(figure, canvas, result)
        return figure.axes[0], canvas

    def result(self, points, selected):
        return {
            'mode': 'multi',
            'front_scatter': points * 30,
            'front': [{'obj': point} for point in points],
            'knee': {'obj': selected},
            'best': {'obj': selected},
        }

    def assert_visible_selection(self, axes, canvas, selected):
        markers = [artist for artist in axes.collections
                   if artist.get_label() == '折中推荐解']
        self.assertEqual(len(markers), 1)
        self.assertFalse(any(artist.get_label() in ('折中解', '推荐解')
                             for artist in axes.collections))
        marker = markers[0]
        np.testing.assert_allclose(marker.get_offsets(), [selected])
        self.assertGreater(marker.get_zorder(), max(line.get_zorder() for line in axes.lines))
        # Check rendered pixels as well: a front marker must not cover the selected center.
        pixels = np.asarray(canvas.buffer_rgba())
        x, y = axes.transData.transform(selected)
        actual = pixels[pixels.shape[0] - 1 - round(y), round(x), :3] / 255
        np.testing.assert_allclose(actual, marker.get_facecolors()[0, :3], atol=.03)
        labels = [text.get_text() for text in axes.get_legend().get_texts()]
        self.assertEqual(labels.count('折中推荐解'), 1)
        self.assertNotIn('折中解', labels)
        self.assertNotIn('推荐解', labels)

    def test_overlapping_selection_is_one_visible_marker_at_multiple_sizes(self):
        points = [[.1, .9], [.5, .5], [.9, .1]]
        for size, dpi in (((4, 2.8), 100), ((7, 4.2), 150)):
            for selected in (points[1], points[-1]):
                with self.subTest(size=size, dpi=dpi, selected=selected):
                    axes, canvas = self.render(self.result(points, selected), size, dpi)
                    self.assert_visible_selection(axes, canvas, selected)

    def test_single_point_front_keeps_selected_marker_visible(self):
        point = [.4, .02]
        axes, canvas = self.render(self.result([point], point))
        self.assert_visible_selection(axes, canvas, point)

    def test_viewed_design_has_distinct_filled_marker_and_no_sample_legend(self):
        points = [[.1, .9], [.5, .5], [.9, .1]]
        result = self.result(points, points[1])
        result['viewed'] = {'obj': points[0]}
        axes, canvas = self.render(result)
        marker = next(a for a in axes.collections if a.get_label() == '当前查看')
        self.assertGreater(marker.get_zorder(), max(line.get_zorder() for line in axes.lines))
        np.testing.assert_allclose(marker.get_facecolors()[0, :3], [192/255, 38/255, 211/255])
        pixels = np.asarray(canvas.buffer_rgba())
        x, y = axes.transData.transform(points[0])
        np.testing.assert_allclose(pixels[pixels.shape[0]-1-round(y), round(x), :3]/255,
                                   marker.get_facecolors()[0, :3], atol=.03)
        labels = [t.get_text() for t in axes.get_legend().get_texts()]
        self.assertEqual(set(labels), {'帕累托前沿', '折中推荐解', '当前查看'})

    def test_no_feasible_front_does_not_claim_a_compromise(self):
        axes, _ = self.render({'mode': 'multi', 'front_scatter': [],
                               'front': [], 'knee': None, 'best': {'obj': [.4, .02]}})
        self.assertFalse(axes.collections)
        self.assertTrue(any('暂无可行' in text.get_text() for text in axes.texts))

    def test_single_objective_modes_do_not_add_compromise_marker(self):
        for mode in ('weighted', 'constraint'):
            with self.subTest(mode=mode):
                axes, _ = self.render({'mode': mode, 'front_scatter': [], 'knee': None,
                    'best': {'obj': [.3], 'mean_perf': .7, 'std_norm': .2,
                             'sigma_constraints': [{'name': 'M', 'sigma': .1, 'sigma_limit': .2}]}})
                self.assertFalse(axes.collections)
                self.assertEqual(len(axes.patches), 2 if mode == 'weighted' else 1)


if __name__ == '__main__':
    unittest.main()
