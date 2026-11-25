"""Jinja2 -> HTML -> WeasyPrint -> PDF bytes."""
from __future__ import annotations
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from .config import PALETTE, SEVERITY_STYLE, ReportConfig
from .context import build_context
from .model_bias_context import build_model_bias_context

TEMPLATES = Path(__file__).parent / "templates"


@lru_cache(maxsize=1)
def _env() -> Environment:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)),
                      autoescape=select_autoescape(["html", "j2"]),
                      trim_blocks=True, lstrip_blocks=True)
    env.globals["SEV"] = SEVERITY_STYLE
    return env


def _css(footer: str) -> str:
    return (TEMPLATES / "report.css").read_text(encoding="utf-8").replace(
        "__FOOTER__", footer.replace("\\", "").replace('"', "'"))


def build_report_html(bias_report: Dict[str, Any], transformation_report: Any = None, *,
                      config: Optional[ReportConfig] = None, model_bias: Optional[Dict[str, Any]] = None) -> str:
    """Merged report: dataset bias (+ transformation) (+ model bias section when `model_bias` is given)."""
    ctx = build_context(bias_report, transformation_report, config)
    ctx["mb"] = build_model_bias_context(model_bias, bias_report, ctx["cfg"]) if model_bias else None
    footer = f"{ctx['cfg'].footer_text} · dataset {ctx['meta']['dataset_id']}"
    ctx["css"] = _css(footer)
    return _env().get_template("report.html.j2").render(**ctx)


def build_model_bias_html(model_bias: Dict[str, Any], bias_report: Optional[Dict[str, Any]] = None, *,
                          config: Optional[ReportConfig] = None) -> str:
    """Standalone model bias report. `bias_report` (optional) adds the 'link to dataset findings' card."""
    cfg = config or ReportConfig()
    mb = build_model_bias_context(model_bias, bias_report, cfg)
    footer = f"{cfg.model_footer_text} · model {mb['meta']['model_id']}"
    return _env().get_template("model_bias_report.html.j2").render(
        mb=mb, mb_first=True, mb_p="", cfg=cfg, C=PALETTE, css=_css(footer))


def _write_pdf(html: str) -> bytes:
    from weasyprint import HTML  # imported lazily: needs pango at runtime
    from weasyprint.text.fonts import FontConfiguration
    try:  # WeasyPrint >= 66: only local files (bundled fonts), no network access
        from weasyprint import URLFetcher
        fetcher = URLFetcher(allowed_protocols={"file"})
    except ImportError:  # older WeasyPrint
        fetcher = None
    # base_url = templates dir so the bundled fonts (../fonts/*.ttf) resolve without network access
    kwargs = {"url_fetcher": fetcher} if fetcher else {}
    return HTML(string=html, base_url=str(TEMPLATES) + "/", **kwargs).write_pdf(font_config=FontConfiguration())


def build_report_pdf(bias_report: Dict[str, Any], transformation_report: Any = None, *,
                     config: Optional[ReportConfig] = None, model_bias: Optional[Dict[str, Any]] = None) -> bytes:
    return _write_pdf(build_report_html(bias_report, transformation_report, config=config, model_bias=model_bias))


def build_model_bias_pdf(model_bias: Dict[str, Any], bias_report: Optional[Dict[str, Any]] = None, *,
                         config: Optional[ReportConfig] = None) -> bytes:
    return _write_pdf(build_model_bias_html(model_bias, bias_report, config=config))
