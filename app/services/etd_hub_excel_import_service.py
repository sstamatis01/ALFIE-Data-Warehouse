"""
Load ETD-Hub data from an Excel file produced by GET /etd-hub/export/excel.
Output shape matches the JSON bulk import format (Theme, Document, Question, ...).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Reverse of column_mapping in etd_hub_export_service.py (friendly name -> Mongo field)
SHEET_COLUMN_MAPS: Dict[str, Dict[str, str]] = {
    "Themes": {
        "Theme ID": "theme_id",
        "Theme Name": "name",
        "Description": "description",
        "Views": "views",
        "Expert ID": "expert_id",
        "Problem Category": "problem_category",
        "Model Category": "model_category",
        "Domain Category": "domain_category",
        "Created At": "created_at",
    },
    "Documents": {
        "Document ID": "document_id",
        "Title": "title",
        "Description": "description",
        "File Path": "file_path",
        "File Size (bytes)": "file_size",
        "Content Type": "content_type",
        "Expert ID": "expert_id",
        "Theme ID": "theme_id",
        "Created At": "created_at",
    },
    "Questions": {
        "Question ID": "question_id",
        "Question Title": "title",
        "Question Body": "body",
        "Created At": "created_at",
        "Views": "views",
        "Expert ID": "expert_id",
        "Theme ID": "theme_id",
    },
    "Answers": {
        "Answer ID": "answer_id",
        "Answer Description": "description",
        "Created At": "created_at",
        "Question ID": "question_id",
        "Expert ID": "expert_id",
        "Parent Answer ID": "parent_id",
    },
    "Votes": {
        "Vote ID": "vote_id",
        "Expert ID": "expert_id",
        "Answer ID": "answer_id",
        "Vote Value": "vote_value",
        "Created At": "created_at",
        "Updated At": "updated_at",
    },
    "Experts": {
        "Expert ID": "expert_id",
        "User ID": "user_id",
        "Is Deleted": "is_deleted",
        "Area of Expertise": "area_of_expertise",
        "Biography": "bio",
        "Date Joined": "date_joined",
        "Profile Picture": "profile_picture",
    },
}

SHEET_TO_ENTITY_KEY = {
    "Themes": "Theme",
    "Documents": "Document",
    "Questions": "Question",
    "Answers": "Answer",
    "Votes": "Vote",
    "Experts": "Expert",
}

INT_FIELDS = {
    "theme_id",
    "document_id",
    "question_id",
    "answer_id",
    "vote_id",
    "expert_id",
    "user_id",
    "views",
    "vote_value",
    "parent_id",
    "theme_id",
    "file_size",
}


def _normalize_cell(key: str, value: Any) -> Any:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, str) and value.strip() == "":
        return None
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if key in INT_FIELDS:
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
        try:
            return int(value)
        except (TypeError, ValueError):
            return value
    if key == "is_deleted":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in ("true", "1", "yes")
        return bool(value)
    if key == "parent_id" and value in (None, "", 0):
        return None
    return value


def _sheet_to_records(df: pd.DataFrame, column_map: Dict[str, str]) -> List[Dict[str, Any]]:
    if df.empty:
        return []
    rename = {c: column_map[c] for c in df.columns if c in column_map}
    df = df.rename(columns=rename)
    keep = [c for c in column_map.values() if c in df.columns]
    if not keep:
        return []
    df = df[keep]
    records: List[Dict[str, Any]] = []
    for row in df.to_dict(orient="records"):
        doc: Dict[str, Any] = {}
        for key, raw in row.items():
            val = _normalize_cell(key, raw)
            if val is not None:
                doc[key] = val
        if doc:
            records.append(doc)
    return records


def load_excel_to_import_dict(
    path: str | Path,
    *,
    sheets: Optional[List[str]] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Read export-format Excel and return dict for ETDHubDataImporter.import_data().
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"ETD-Hub Excel seed not found: {path}")

    xl = pd.ExcelFile(path)
    target_sheets = sheets or [s for s in SHEET_COLUMN_MAPS if s in xl.sheet_names]
    result: Dict[str, List[Dict[str, Any]]] = {}

    for sheet_name in target_sheets:
        column_map = SHEET_COLUMN_MAPS.get(sheet_name)
        entity_key = SHEET_TO_ENTITY_KEY.get(sheet_name)
        if not column_map or not entity_key:
            continue
        df = pd.read_excel(path, sheet_name=sheet_name)
        records = _sheet_to_records(df, column_map)
        if records:
            result[entity_key] = records
            logger.info("Loaded %s rows from sheet %s", len(records), sheet_name)

    return result
