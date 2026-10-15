"""File format adapters. Domain and page modules pass plain Python data."""
import csv
import json
import os
from pathlib import Path
import tempfile


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
    writer.setTitle("RAMS 稳定性设计分析报告")
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
                f"RAMS · {page_index + 1} / {page_count}")
    finally:
        painter.end()
