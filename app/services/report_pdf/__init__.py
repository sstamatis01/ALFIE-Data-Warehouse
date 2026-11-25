"""AutoDW bias + transformation (+ model bias) report -> PDF (pure Python: Jinja2 + inline SVG + WeasyPrint).

Public API:
    build_report_html(bias_report, transformation_report=None, *, config=None, model_bias=None) -> str
    build_report_pdf(bias_report, transformation_report=None, *, config=None, model_bias=None) -> bytes
    build_model_bias_html(model_bias, bias_report=None, *, config=None) -> str
    build_model_bias_pdf(model_bias, bias_report=None, *, config=None) -> bytes

`bias_report` is the stored bias-report document (BiasReportResponse as dict, i.e. with
`report`, `dataset_id`, `dataset_version`, `created_at`, ...) OR just its inner `report` dict.
`transformation_report` is the TransformationReportResponse as dict (with `report` = list of
steps) OR just the list of steps, OR None for a bias-only PDF.
`model_bias` is the stored Aequitas audit (ModelBiasAuditResponse as dict, collection
`model_bias_audits`) OR just its inner `report` ({metrics, disparities, performance, alerts}).
"""
from .render import build_model_bias_html, build_model_bias_pdf, build_report_html, build_report_pdf
from .config import ReportConfig

__all__ = ["build_report_html", "build_report_pdf", "build_model_bias_html", "build_model_bias_pdf", "ReportConfig"]
