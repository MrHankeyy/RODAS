"""试验数据表文件：CSV/Excel 读写、表头即列名、试验序号非必需。"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt6.QtWidgets import QApplication, QFileDialog

from backend.domain.models import ProjectData, ResponseItem
from backend.infrastructure import file_io
from backend.services import project_service
from backend.services.project_service import ProjectService
from frontend.pages.data_management_page import DataManagementPage

APP = QApplication.instance() or QApplication([])

ROWS = [{'试验序号': '1', 'X': '0.5', 'Y': '3'},
        {'试验序号': '2', 'X': '-1', 'Y': '4'}]


class TableFileTests(unittest.TestCase):
    def test_csv_xlsx_xls_roundtrip_keeps_header_and_values(self):
        with tempfile.TemporaryDirectory() as directory:
            for suffix in ('.csv', '.xlsx', '.xls'):
                with self.subTest(suffix=suffix):
                    path = Path(directory) / f'试验数据表{suffix}'
                    file_io.write_table_records(path, ROWS)
                    self.assertTrue(path.exists())
                    self.assertEqual(file_io.read_table_records(path), ROWS)

    def test_first_row_is_the_header_and_blank_rows_are_dropped(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'data.csv'
            path.write_text('\ufeff试验序号,X,Y\n1,0.5,3\n,,\n2,-1,4\n', encoding='utf-8')
            self.assertEqual(file_io.read_table_records(path), ROWS)

    def test_unnamed_columns_are_ignored_and_gbk_csv_is_readable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'gbk.csv'
            path.write_bytes('试验序号,因子,响应\n1,0.5,3\n'.encode('gb18030'))
            self.assertEqual(file_io.read_table_records(path),
                             [{'试验序号': '1', '因子': '0.5', '响应': '3'}])

    def test_round_trip_survives_whole_numbers_written_as_floats(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'numbers.xlsx'
            file_io.write_table_records(path, [{'试验序号': 1, 'X': 0.5, 'Y': 3.0}])
            self.assertEqual(file_io.read_table_records(path),
                             [{'试验序号': '1', 'X': '0.5', 'Y': '3'}])


class RunIdTests(unittest.TestCase):
    def test_missing_run_id_is_numbered_from_one(self):
        rows = project_service.with_run_ids([{'X': '1', 'Y': '2'}, {'X': '2', 'Y': '4'}])
        self.assertEqual([row['试验序号'] for row in rows], ['1', '2'])
        self.assertEqual(list(rows[0]), ['试验序号', 'X', 'Y'])

    def test_alias_spellings_are_merged_into_run_id(self):
        rows = project_service.with_run_ids([{'run id': 'A', 'X': '1'},
                                             {'RUN-ID': 'B', 'X': '2'}])
        self.assertEqual([row['试验序号'] for row in rows], ['A', 'B'])
        self.assertNotIn('run id', rows[0])
        self.assertNotIn('RUN-ID', rows[1])

    def test_blank_run_id_cells_are_filled_in_order(self):
        rows = project_service.with_run_ids([{'试验序号': '', 'X': '1'},
                                             {'试验序号': '7', 'X': '2'}])
        self.assertEqual([row['试验序号'] for row in rows], ['1', '7'])

    def test_replace_dataset_no_longer_requires_run_id(self):
        project = ProjectData(responses=[ResponseItem(name='Y')])
        ProjectService.for_project(project).replace_dataset([{'X': '1', 'Y': '2'}])
        self.assertEqual(project.doe_matrix, [{'试验序号': '1', 'X': '1', 'Y': '2'}])


class DataManagementFileTests(unittest.TestCase):
    def page(self):
        page = DataManagementPage(ProjectData(responses=[ResponseItem(name='Y')]))
        self.addCleanup(page.close)
        return page

    def test_import_reads_excel_without_run_id(self):
        page = self.page()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '输入.xlsx'
            file_io.write_table_records(path, [{'X': '1', 'Y': '2'}, {'X': '2', 'Y': '4'}])
            with patch.object(QFileDialog, 'getOpenFileName',
                              return_value=(str(path), file_io.TABLE_FILTER)):
                page.import_from_csv()
        self.assertEqual(page.table.rowCount(), 2)
        headers = [page.table.horizontalHeaderItem(c).text()
                   for c in range(page.table.columnCount())]
        self.assertEqual(headers[:2], ['试验序号', 'X'])
        self.assertEqual(page.table.item(1, 0).text(), '2')

    def test_export_writes_whichever_table_format_is_chosen(self):
        page = self.page()
        page.project_data.doe_matrix = list(ROWS)
        with tempfile.TemporaryDirectory() as directory:
            for suffix, label in (('.xlsx', 'Excel 工作簿 (*.xlsx)'), ('.csv', file_io.TABLE_FILTER)):
                with self.subTest(suffix=suffix):
                    target = Path(directory) / f'导出{suffix}'
                    with patch.object(QFileDialog, 'getSaveFileName',
                                      return_value=(str(target), label)):
                        page.export_to_csv()
                    self.assertEqual(file_io.read_table_records(target), ROWS)

    def test_typed_name_without_suffix_uses_the_chosen_filter(self):
        from frontend.workspace import table_save_path
        self.assertEqual(table_save_path('表', 'Excel 工作簿 (*.xlsx)'), '表.xlsx')
        self.assertEqual(table_save_path('表', file_io.TABLE_FILTER), '表.csv')
        self.assertEqual(table_save_path('表.xls', file_io.TABLE_FILTER), '表.xls')


if __name__ == '__main__':
    unittest.main()
