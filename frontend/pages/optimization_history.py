"""优化历程：逐代展示鲁棒优化的目标值与可行解变化，只读取后端记录。"""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView,
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from frontend.pages.result_overview import label
from frontend.terminology import tooltip

SERIES_COLORS = ("#246da4", "#168064", "#c73545")
EMPTY_MESSAGE = "尚无优化历程。执行鲁棒优化后，这里按代显示整个过程的目标值与可行解变化。"


class OptimizationHistory(QWidget):
    """Per-generation convergence record; never recomputes the optimization."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.history = []
        self.objectives = []
        column = QVBoxLayout(self)
        column.setContentsMargins(16, 16, 16, 12)
        column.setSpacing(10)

        header = QHBoxLayout()
        self.heading = label('优化历程', 'heading')
        self.heading.setToolTip(tooltip('optimization_history'))
        self.summary = label('', 'muted')
        self.summary.setToolTip(tooltip('optimization_history'))
        header.addWidget(self.heading)
        header.addStretch()
        header.addWidget(self.summary)
        column.addLayout(header)

        self.figure = Figure(figsize=(8, 5.2), dpi=100, layout='constrained')
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setMinimumHeight(320)
        column.addWidget(self.canvas, 1)

        self.table = QTableWidget(0, 0)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().hide()
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.setMaximumHeight(186)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        column.addWidget(self.table)
        self.clear()

    # ------------------------------------------------------------------ data
    def clear(self):
        self.history, self.objectives = [], []
        self.summary.setText('')
        self.table.clear()
        self.table.setRowCount(0)
        self.table.setColumnCount(0)
        self.table.setVisible(False)
        self._empty_figure()

    def set_result(self, robust):
        robust = robust or {}
        self.history = list(robust.get('history') or [])
        self.objectives = list(robust.get('history_objectives') or [])
        if not self.history:
            self.clear()
            return
        last = self.history[-1]
        note = '（按停滞判据提前停止）' if robust.get('stop_reason') == 'stall' else ''
        self.summary.setText(
            f"{len(self.history)} 代{note} · 累计评估 {last.get('evaluated', 0)} 个设计点 · "
            f"末代可行解 {last.get('feasible', 0)} 个")
        self._render_table()
        self._render_figure()

    # ------------------------------------------------------------------ view
    def _empty_figure(self):
        self.figure.clear()
        axes = self.figure.add_subplot(111)
        axes.axis('off')
        axes.text(.5, .5, EMPTY_MESSAGE, ha='center', va='center',
                  color='#6c7c8f', wrap=True, transform=axes.transAxes)
        self.canvas.draw_idle()

    def _render_table(self):
        labels = self.objectives or []
        headers = ['代数'] + labels + ['可行解数', '累计评估']
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(self.history))
        for row, record in enumerate(self.history):
            values = [record.get('gen'), *record.get('best', []),
                      record.get('feasible'), record.get('evaluated')]
            for column in range(len(headers)):
                value = values[column] if column < len(values) else ''
                text = f"{value:.4g}" if isinstance(value, float) else str(value)
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, column, item)
        self.table.setVisible(True)

    def _render_figure(self):
        self.figure.clear()
        generations = [record.get('gen', index + 1) for index, record in enumerate(self.history)]
        objectives = self.objectives or ['目标值']
        top, bottom = self.figure.subplots(2, 1, sharex=True,
                                           gridspec_kw={'height_ratios': (3, 2)})
        for index, name in enumerate(objectives):
            values = [record.get('best', [None] * len(objectives))[index]
                      if index < len(record.get('best', [])) else None
                      for record in self.history]
            top.plot(generations, values, '-o', ms=2.4, lw=1.6,
                     color=SERIES_COLORS[index % len(SERIES_COLORS)], label=name)
        top.set_ylabel('每代最优目标值')
        top.set_title('目标值收敛历程')
        top.grid(alpha=.15)
        if len(objectives) > 1:
            top.legend(fontsize=8, frameon=False)

        feasible = [record.get('feasible', 0) for record in self.history]
        bottom.bar(generations, feasible, color='#8fb8d8', width=.8)
        bottom.set_ylabel('可行解数')
        bottom.set_xlabel('代数')
        bottom.set_title('每代可行解数量')
        bottom.grid(alpha=.15, axis='y')

        stop = generations[-1] if generations else None
        if stop is not None:
            for axes in (top, bottom):
                axes.axvline(stop, color='#8495a6', linestyle='--', lw=1.0)
        self.canvas.draw_idle()
