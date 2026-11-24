"""Jinja2 -> HTML -> WeasyPrint -> PDF bytes."""
from __future__ import annotations
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from .config import SEVERITY_STYLE, ReportConfig
from .context import build_context

TEMPLATES = Path(__file__).parent / "templates"


@lru_cache(maxsize=1)
def _env() -> Environment:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)),
                      autoescape=select_autoescape(["html", "j2"]),
                      trim_blocks=True, lstrip_blocks=True)
    env.globals["SEV"] = SEVERITY_STYLE
    return env


def build_report_html(bias_report: Dict[str, Any], transformation_report: Any = None, *,
                      config: Optional[ReportConfig] = None) -> str:
    ctx = build_context(bias_report, transformation_report, config)
    footer = f"{ctx['cfg'].footer_text} · dataset {ctx['meta']['dataset_id']}"
    ctx["css"] = (TEMPLATES / "report.css").read_text(encoding="utf-8").replace(
        "__FOOTER__", footer.replace("\\", "").replace('"', "'"))
    return _env().get_template("report.html.j2").render(**ctx)


def build_report_pdf(bias_report: Dict[str, Any], transformation_report: Any = None, *,
                     config: Optional[ReportConfig] = None) -> bytes:
    from weasyprint import HTML  # imported lazily: needs pango at runtime
    from weasyprint.text.fonts import FontConfiguration
    try:  # WeasyPrint >= 66: only local files (bundled fonts), no network access
        from weasyprint import URLFetcher
        fetcher = URLFetcher(allowed_protocols={"file"})
    except ImportError:  # older WeasyPrint
        fetcher = None
    html = build_report_html(bias_report, transformation_report, config=config)
    # base_url = templates dir so the bundled fonts (../fonts/*.ttf) resolve without network access
    kwargs = {"url_fetcher": fetcher} if fetcher else {}
    return HTML(string=html, base_url=str(TEMPLATES) + "/", **kwargs).write_pdf(font_config=FontConfiguration())
