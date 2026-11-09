"""File format adapters. Domain and page modules pass plain Python data."""
import csv
import json
import os
from pathlib import Path
import tempfile

TABLE_FILTER = "表格文件 (*.csv *.xlsx *.xls)"
EXCEL_SUFFIXES = (".xlsx", ".xls")
READ_ENCODINGS = ("utf-8-sig", "gbk")


def read_csv_records(path, encoding="utf-8"):
    with open(path, mode="r", encoding=encoding, newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv_records(path, rows, encoding="utf-8"):
    if not rows:
        raise ValueError("没有可导出的数据")
    with open(path, mode="w", encoding=encoding, newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def write_csv_table(path, headers, rows, encoding="utf-8-sig"):
    with open(path, mode="w", encoding=encoding, newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)


def table_suffix(path):
    return Path(path).suffix.lower()


def _cell_text(value):
    """Render a spreadsheet cell as the text the table widget displays."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _records_from_grid(grid):
    """First non-empty row is the header; blank rows and unnamed columns are dropped."""
    rows = [list(row) for row in grid]
    first = next((index for index, row in enumerate(rows)
                  if any(_cell_text(cell) for cell in row)), None)
    if first is None:
        return []
    header = [_cell_text(cell) for cell in rows[first]]
    keep = [index for index, name in enumerate(header) if name]
    if not keep:
        return []
    records = []
    for row in rows[first + 1:]:
        record = {header[index]: _cell_text(row[index]) if index < len(row) else ""
                  for index in keep}
        if any(record.values()):
            records.append(record)
    return records


def _read_excel_grid(path):
    if table_suffix(path) == ".xlsx":
        from openpyxl import load_workbook
        book = load_workbook(str(path), read_only=True, data_only=True)
        try:
            sheet = book.active
            return [list(row) for row in sheet.iter_rows(values_only=True)]
        finally:
            book.close()
    import xlrd
    book = xlrd.open_workbook(str(path))
    sheet = book.sheet_by_index(0)
    return [sheet.row_values(index) for index in range(sheet.nrows)]


def read_table_records(path, encoding=None):
    """Read a header-row table from CSV, XLSX or XLS without requiring any specific column."""
    if table_suffix(path) in EXCEL_SUFFIXES:
        return _records_from_grid(_read_excel_grid(path))
    candidates = (encoding,) if encoding else READ_ENCODINGS
    last_error = None
    for candidate in candidates:
        try:
            with open(path, mode="r", encoding=candidate, newline="") as handle:
                return _records_from_grid(csv.reader(handle))
        except UnicodeDecodeError as error:
            last_error = error
    raise ValueError("无法识别文件编码，请另存为 UTF-8 或 Excel 工作簿后再导入。") from last_error


def _write_excel(path, headers, rows):
    if table_suffix(path) == ".xls":
        import xlwt
        book = xlwt.Workbook(encoding="utf-8")
        sheet = book.add_sheet("试验数据")
        for column, name in enumerate(headers):
            sheet.write(0, column, name)
        for line, row in enumerate(rows, 1):
            for column, value in enumerate(row):
                sheet.write(line, column, value)
        book.save(str(path))
        return
    from openpyxl import Workbook
    book = Workbook()
    sheet = book.active
    sheet.title = "试验数据"
    sheet.append(list(headers))
    for row in rows:
        sheet.append(list(row))
    for column, name in enumerate(headers, 1):
        width = max(12, min(28, len(str(name)) + 6))
        sheet.column_dimensions[sheet.cell(row=1, column=column).column_letter].width = width
    book.save(str(path))


def write_table(path, headers, rows):
    """Write a header row plus data rows; the suffix decides CSV or Excel."""
    if table_suffix(path) in EXCEL_SUFFIXES:
        _write_excel(path, headers, rows)
    else:
        write_csv_table(path, headers, rows)


def write_table_records(path, rows):
    """Write record dicts (first row defines the columns) as CSV or Excel."""
    if not rows:
        raise ValueError("没有可导出的数据")
    headers = list(rows[0])
    write_table(path, headers, [[row.get(name, "") for name in headers] for row in rows])


def write_text(path, value, encoding="utf-8"):
    Path(path).write_text(value, encoding=encoding)


def read_json(path, encoding="utf-8-sig"):
    return json.loads(Path(path).read_text(encoding=encoding))


def write_json(path, value, encoding="utf-8"):
    text = json.dumps(
        value, ensure_ascii=False, indent=2, allow_nan=False)
    write_text(path, text, encoding=encoding)


def atomic_write_json(path, value):
    path = Path(path)
    descriptor, temporary = tempfile.mkstemp(
        prefix=".rams-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(
                value, handle, ensure_ascii=False, indent=2,
                allow_nan=False)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def export_pdf(html_text, path):
    """Write selectable report text through the existing Qt PDF backend."""
    from PyQt6.QtCore import QRectF, QMarginsF, Qt, QSizeF
    from PyQt6.QtGui import (
        QPdfWriter, QPageSize, QTextDocument, QPainter, QFont,
        QAbstractTextDocumentLayout,
    )
    writer = QPdfWriter(str(path))
    writer.setResolution(96)
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageMargins(QMarginsF(15, 15, 15, 15))
    writer.setTitle("RODAS 鲁棒优化设计分析报告")
    document = QTextDocument()
    document.setDefaultFont(QFont("Microsoft YaHei", 10))
    document.documentLayout().setPaintDevice(writer)
    document.setHtml(html_text)
    width = writer.width()
    height = writer.height() - 38
    document.setPageSize(QSizeF(width, height))
    painter = QPainter(writer)
    if not painter.isActive():
        raise OSError("PDF 文件无法写入，请检查路径和文件占用")
    try:
        page_count = document.pageCount()
        for page_index in range(page_count):
            if page_index and not writer.newPage():
                raise OSError("PDF 新页面写入失败")
            painter.save()
            painter.setClipRect(QRectF(0, 0, width, height))
            painter.translate(0, -page_index * height)
            context = QAbstractTextDocumentLayout.PaintContext()
            context.clip = QRectF(
                0, page_index * height, width, height)
            document.documentLayout().draw(painter, context)
            painter.restore()
            painter.setFont(QFont("Microsoft YaHei", 8))
            painter.drawText(
                QRectF(0, height + 12, width, 22),
                Qt.AlignmentFlag.AlignRight,
                f"RODAS · {page_index + 1} / {page_count}")
    finally:
        painter.end()
