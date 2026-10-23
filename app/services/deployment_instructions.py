"""
Deployment instructions for AutoML models stored in AutoDW.

Primary source: ``*_deployment_instructions.md`` inside the model ZIP/folder
(already produced by the AutoML engine). Cached on the model Mongo document at
upload time so Agentic Core can fetch text without calling the AutoML host.

Fallback order on GET:
  1. Mongo ``deployment_instructions`` field
  2. Matching ``.md`` file already in MinIO for that model version
  3. Bundled static defaults under ``static_docs/deployment/`` (by modality)
"""
from __future__ import annotations

import logging
import os
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

INSTRUCTION_BASENAMES = (
    "tabular_deployment_instructions.md",
    "vision_deployment_instructions.md",
)


def _default_static_dir() -> Path:
    image_path = Path("/app/static_docs/deployment")
    if image_path.is_dir():
        return image_path
    return Path(__file__).resolve().parents[2] / "static_docs" / "deployment"


def is_deployment_instructions_filename(filename: str) -> bool:
    base = os.path.basename(filename or "").lower()
    if base in INSTRUCTION_BASENAMES:
        return True
    return base.endswith("deployment_instructions.md")


def modality_from_filename(filename: str) -> Optional[str]:
    base = os.path.basename(filename or "").lower()
    if base.startswith("tabular_"):
        return "tabular"
    if base.startswith("vision_"):
        return "vision"
    return None


def modality_from_model_type(model_type: Any) -> Optional[str]:
    raw = getattr(model_type, "value", model_type)
    s = str(raw or "").strip().lower()
    if s.startswith("tabular_") or s in {"regression", "time_series", "timeseries"}:
        return "tabular"
    # Bare "classification" is ambiguous (tabular vs vision); leave unset so caller can fall back.
    vision_prefixes = (
        "image_",
        "object_detection",
        "video_",
        "keypoint_",
        "audio_",
        "computer_vision",
    )
    if any(s.startswith(p) or s == p.rstrip("_") for p in vision_prefixes):
        return "vision"
    return None


def extract_from_text_file(filename: str, content: bytes) -> Optional[Dict[str, str]]:
    if not is_deployment_instructions_filename(filename):
        return None
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("utf-8", errors="replace")
    text = text.strip()
    if not text:
        return None
    return {
        "instructions": text,
        "filename": os.path.basename(filename),
        "modality": modality_from_filename(filename) or "unknown",
        "source": "upload",
    }


def extract_from_zip_bytes(zip_bytes: bytes) -> Optional[Dict[str, str]]:
    """Return the first deployment-instructions markdown found in a ZIP."""
    try:
        with zipfile.ZipFile(BytesIO(zip_bytes), "r") as zf:
            # Prefer known names; then any *deployment_instructions.md
            names = [n for n in zf.namelist() if not n.endswith("/") and not n.startswith("__")]
            ordered: List[str] = []
            for wanted in INSTRUCTION_BASENAMES:
                ordered.extend(n for n in names if os.path.basename(n).lower() == wanted)
            ordered.extend(
                n
                for n in names
                if is_deployment_instructions_filename(n) and n not in ordered
            )
            for name in ordered:
                try:
                    data = zf.read(name)
                except Exception:
                    continue
                found = extract_from_text_file(name, data)
                if found:
                    found["source"] = "zip"
                    return found
    except zipfile.BadZipFile:
        return None
    except Exception as e:
        logger.warning("Could not scan ZIP for deployment instructions: %s", e)
    return None


def extract_from_model_files(
    files: List[Any],
    *,
    read_bytes,
) -> Optional[Dict[str, str]]:
    """
    Find instructions among already-uploaded ModelFile entries.

    ``read_bytes`` is a callable ``(file_path: str) -> bytes`` (sync or result of await).
    """
    candidates = []
    for f in files or []:
        filename = getattr(f, "filename", None) or (f.get("filename") if isinstance(f, dict) else None)
        file_path = getattr(f, "file_path", None) or (f.get("file_path") if isinstance(f, dict) else None)
        if filename and file_path and is_deployment_instructions_filename(filename):
            candidates.append((filename, file_path))
    # Prefer tabular_/vision_ canonical names
    def sort_key(item: Tuple[str, str]) -> int:
        base = os.path.basename(item[0]).lower()
        try:
            return INSTRUCTION_BASENAMES.index(base)
        except ValueError:
            return 99

    for filename, file_path in sorted(candidates, key=sort_key):
        try:
            data = read_bytes(file_path)
            found = extract_from_text_file(filename, data)
            if found:
                found["source"] = "minio"
                return found
        except Exception as e:
            logger.warning("Failed reading %s for deployment instructions: %s", file_path, e)
    return None


def bundled_fallback(modality: Optional[str]) -> Optional[Dict[str, str]]:
    if modality not in ("tabular", "vision"):
        return None
    path = _default_static_dir() / f"{modality}_deployment_instructions.md"
    if not path.is_file():
        logger.warning("Bundled deployment instructions missing: %s", path)
        return None
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return None
    return {
        "instructions": text,
        "filename": path.name,
        "modality": modality,
        "source": "bundled",
    }


# ---------------------------------------------------------------------------
# Bias-mitigation appendix (summary + illustrative snippets)
# ---------------------------------------------------------------------------

_APPLIED_TRANSFORMS = frozenset(
    {
        "missing_value_fill",
        "duplicate_removal",
        "encoding",
        "invalid_boolean_cleaned",
        "skew_correction",
        "oversampling",
        "text_class_balance",
        "drift_mitigation",
    }
)

_SKIP_TRANSFORMS = frozenset(
    {
        "encoding_skipped",
        "target_encoding_skipped",
        "oversampling_skipped",
        "text_class_balance_skipped",
    }
)

_MAX_BULLETS = 40
_MAX_CODE_EXAMPLES = 6


def _short(value: Any, limit: int = 120) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.4g}"
    text = str(value)
    text = " ".join(text.split())
    if len(text) > limit:
        return text[: limit - 1] + "…"
    return text


def _normalize_transform_entries(report: Any) -> List[Dict[str, Any]]:
    """Accept list-of-dicts (current) or wrapped dict shapes."""
    if report is None:
        return []
    if isinstance(report, list):
        return [e for e in report if isinstance(e, dict)]
    if isinstance(report, dict):
        for key in ("transformations", "entries", "log", "steps"):
            inner = report.get(key)
            if isinstance(inner, list):
                return [e for e in inner if isinstance(e, dict)]
        # Single entry dict
        if "transformation" in report:
            return [report]
    return []


def _dedupe_applied(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Prefer train-fit log rows. Split uploads append train+test+drift logs;
    keep the first occurrence of each (column, transformation, method) key.
    """
    seen = set()
    out: List[Dict[str, Any]] = []
    for e in entries:
        kind = str(e.get("transformation") or "")
        if kind not in _APPLIED_TRANSFORMS:
            continue
        key = (
            kind,
            str(e.get("column") or ""),
            str(e.get("method") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out


def _illustrative_snippet(entry: Dict[str, Any]) -> Optional[str]:
    kind = str(entry.get("transformation") or "")
    col = str(entry.get("column") or "column")
    method = str(entry.get("method") or "")
    fill = entry.get("modified_value")

    if kind == "missing_value_fill":
        return (
            f"# Fill missing values in '{col}' (logged fill={_short(fill, 40)})\n"
            f"df['{col}'] = df['{col}'].fillna({repr(fill)})"
        )
    if kind == "duplicate_removal":
        return "df = df.drop_duplicates()"
    if kind == "encoding" and "one-hot" in method.lower():
        return (
            f"# One-hot encode '{col}' (exact dummy column names not persisted)\n"
            f"df = pd.get_dummies(df, columns=['{col}'], drop_first=False)"
        )
    if kind == "encoding" and "label" in method.lower():
        return (
            f"# Label-encode '{col}' (category→int map was not persisted)\n"
            f"# Align categories with the training schema before predict()."
        )
    if kind == "skew_correction" and "yeo" in method.lower():
        return (
            f"# Skew correction on '{col}' (Yeo-Johnson; fitted params not persisted)\n"
            f"from sklearn.preprocessing import PowerTransformer\n"
            f"# pt = PowerTransformer(method='yeo-johnson').fit(train[['{col}']])\n"
            f"# df['{col}'] = pt.transform(df[['{col}']])"
        )
    if kind == "skew_correction":
        return (
            f"# Skew / scale '{col}' (StandardScaler; fitted params not persisted)\n"
            f"from sklearn.preprocessing import StandardScaler\n"
            f"# scaler = StandardScaler().fit(train[['{col}']])\n"
            f"# df['{col}'] = scaler.transform(df[['{col}']])"
        )
    if kind == "drift_mitigation":
        return (
            f"# Drift mitigation scaled '{col}' at train time only\n"
            f"# Do not re-fit a new scaler at inference unless you persist it yourself."
        )
    if kind == "oversampling":
        return (
            "# Class balancing used SMOTE on the training split only "
            f"({_short(method, 60)})\n"
            "# Do NOT apply SMOTE at inference — only use it when rebuilding training data."
        )
    if kind == "text_class_balance":
        return (
            "# Text class balance resampled training rows "
            f"({_short(method, 60)})\n"
            "# Do NOT resample at inference."
        )
    return None


def build_mitigation_instructions_markdown(
    *,
    dataset_id: str,
    mitigated_version: Optional[str],
    transformation_report_id: Optional[str],
    entries: List[Dict[str, Any]],
    bias_dataset_version: Optional[str] = None,
) -> str:
    """
    Human-readable mitigation section appended to deployment instructions.

    Intentionally summary + illustrative code — fitted encoders/scalers are not
    persisted by the bias consumer today, so this is not a bit-identical replay.
    """
    applied = _dedupe_applied(entries)
    skips = [
        e
        for e in entries
        if str(e.get("transformation") or "") in _SKIP_TRANSFORMS
    ]
    # Dedupe skips similarly
    skip_seen = set()
    skip_unique: List[Dict[str, Any]] = []
    for e in skips:
        key = (
            str(e.get("transformation") or ""),
            str(e.get("column") or ""),
            _short(e.get("modified_value"), 80),
        )
        if key in skip_seen:
            continue
        skip_seen.add(key)
        skip_unique.append(e)

    lines: List[str] = [
        "",
        "---",
        "",
        "## Bias mitigation applied before training",
        "",
        "AutoDW's bias mitigator transformed the **training data** before AutoML.",
        "Use this section to understand the feature space the model was trained on.",
        "",
        "**Important**",
        "",
        "- Train-only steps (SMOTE / text resample / duplicate drops) must **not** be "
        "re-run at inference.",
        "- AutoGluon already stores its own internal preprocessing for columns seen "
        "at training time.",
        "- Fitted fill values / encoders / scalers from AutoDW mitigation were **not** "
        "saved as a replayable pipeline artifact; snippets below are illustrative.",
        "",
        f"- Training dataset id: `{dataset_id}`",
    ]
    if bias_dataset_version:
        lines.append(f"- Bias report dataset version: `{bias_dataset_version}`")
    if mitigated_version:
        lines.append(f"- Mitigated dataset version: `{mitigated_version}`")
    if transformation_report_id:
        lines.append(f"- Transformation report id: `{transformation_report_id}`")
    lines.append(f"- Logged transform steps (deduped applied): **{len(applied)}**")
    lines.append("")

    if not applied and not skip_unique:
        lines.extend(
            [
                "_No detailed transformation log entries were found for this report._",
                "",
            ]
        )
        return "\n".join(lines)

    if applied:
        lines.append("### Applied transformations")
        lines.append("")
        for e in applied[:_MAX_BULLETS]:
            kind = e.get("transformation")
            col = e.get("column")
            method = e.get("method")
            orig = e.get("original_value", e.get("original_missing_values"))
            mod = e.get("modified_value")
            bits = [f"**{kind}**"]
            if col is not None:
                bits.append(f"on `{col}`")
            if method:
                bits.append(f"(method=`{_short(method, 80)}`)")
            detail_parts = []
            if orig is not None:
                detail_parts.append(f"before={_short(orig)}")
            if mod is not None:
                detail_parts.append(f"after={_short(mod)}")
            detail = f" — {', '.join(detail_parts)}" if detail_parts else ""
            lines.append(f"- {' '.join(bits)}{detail}")
        if len(applied) > _MAX_BULLETS:
            lines.append(f"- …and {len(applied) - _MAX_BULLETS} more")
        lines.append("")

    if skip_unique:
        lines.append("### Skipped / not applied")
        lines.append("")
        for e in skip_unique[:12]:
            lines.append(
                f"- **{e.get('transformation')}** on `{e.get('column')}` "
                f"({_short(e.get('modified_value') or e.get('method'), 100)})"
            )
        if len(skip_unique) > 12:
            lines.append(f"- …and {len(skip_unique) - 12} more")
        lines.append("")

    snippets: List[str] = []
    for e in applied:
        if len(snippets) >= _MAX_CODE_EXAMPLES:
            break
        snip = _illustrative_snippet(e)
        if snip and snip not in snippets:
            snippets.append(snip)

    if snippets:
        lines.append("### Illustrative preprocessing notes")
        lines.append("")
        lines.append(
            "These examples mirror the logged methods. They are **not** a drop-in "
            "replacement for the exact fitted state used during mitigation."
        )
        lines.append("")
        lines.append("```python")
        lines.append("import pandas as pd")
        lines.append("# df = raw inference / rebuild frame with the same columns as training")
        lines.append("")
        lines.append("\n\n".join(snippets))
        lines.append("```")
        lines.append("")

    return "\n".join(lines)


def append_mitigation_section(base_instructions: str, mitigation_md: Optional[str]) -> str:
    base = (base_instructions or "").rstrip()
    extra = (mitigation_md or "").strip()
    if not extra:
        return base
    if "## Bias mitigation applied before training" in base:
        return base
    return f"{base}\n\n{extra}\n"


async def resolve_mitigation_for_model(
    user_id: str,
    training_dataset: Optional[str],
) -> Dict[str, Any]:
    """
    Look up bias + transformation reports for the model's training dataset.

    Returns a dict with:
      mitigation_applied, mitigated_dataset_version, transformation_report_id,
      markdown (or None), training_dataset
    """
    empty = {
        "training_dataset": training_dataset,
        "mitigation_applied": False,
        "mitigated_dataset_version": None,
        "transformation_report_id": None,
        "markdown": None,
    }
    if not training_dataset:
        return empty

    try:
        from .bias_report_service import bias_report_service
        from .transformation_report_service import transformation_report_service
    except Exception as e:
        logger.warning("Mitigation services unavailable: %s", e)
        return empty

    try:
        bias_reports = await bias_report_service.get_all_reports(user_id, training_dataset)
    except Exception as e:
        logger.warning(
            "Could not load bias reports for dataset %s: %s", training_dataset, e
        )
        bias_reports = []

    mitigated_version: Optional[str] = None
    transform_id: Optional[str] = None
    bias_version: Optional[str] = None

    for br in bias_reports or []:
        report_body = br.report if isinstance(br.report, dict) else {}
        mit = report_body.get("mitigation") if isinstance(report_body, dict) else None
        mit = mit if isinstance(mit, dict) else {}
        tid = (
            mit.get("transformation_report_id")
            or getattr(br, "transformation_report_id", None)
        )
        mver = mit.get("mitigated_dataset_version")
        performed = bool(mit.get("mitigation_performed")) or bool(tid) or bool(mver)
        if performed:
            mitigated_version = mver or mitigated_version
            transform_id = tid or transform_id
            bias_version = getattr(br, "dataset_version", None) or bias_version
            break

    transform_doc = None
    try:
        if mitigated_version:
            transform_doc = await transformation_report_service.get_report(
                user_id, training_dataset, mitigated_version
            )
        if transform_doc is None:
            transform_doc = await transformation_report_service.get_latest_report_for_dataset(
                user_id, training_dataset
            )
    except Exception as e:
        logger.warning(
            "Could not load transformation report for dataset %s: %s",
            training_dataset,
            e,
        )
        transform_doc = None

    if transform_doc is None and not mitigated_version and not transform_id:
        return empty

    if transform_doc is not None:
        mitigated_version = mitigated_version or transform_doc.version
        transform_id = transform_id or transform_doc.id

    entries = _normalize_transform_entries(
        transform_doc.report if transform_doc is not None else None
    )
    # If we only have mitigation metadata and an empty/missing log, still announce it.
    if not entries and not mitigated_version and not transform_id:
        return empty

    markdown = build_mitigation_instructions_markdown(
        dataset_id=training_dataset,
        mitigated_version=mitigated_version,
        transformation_report_id=transform_id,
        entries=entries,
        bias_dataset_version=bias_version,
    )
    return {
        "training_dataset": training_dataset,
        "mitigation_applied": True,
        "mitigated_dataset_version": mitigated_version,
        "transformation_report_id": transform_id,
        "markdown": markdown,
    }
