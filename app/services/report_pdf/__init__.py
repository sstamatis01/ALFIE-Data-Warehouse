"""AutoDW bias + transformation report -> PDF (pure Python: Jinja2 + inline SVG + WeasyPrint).

Public API:
    build_report_html(bias_report, transformation_report=None, *, config=None) -> str
    build_report_pdf(bias_report, transformation_report=None, *, config=None) -> bytes

`bias_report` is the stored bias-report document (BiasReportResponse as dict, i.e. with
`report`, `dataset_id`, `dataset_version`, `created_at`, ...) OR just its inner `report` dict.
`transformation_report` is the TransformationReportResponse as dict (with `report` = list of
steps) OR just the list of steps, OR None for a bias-only PDF.
"""
from .render import build_report_html, build_report_pdf
from .config import ReportConfig

__all__ = ["build_report_html", "build_report_pdf", "ReportConfig"]
