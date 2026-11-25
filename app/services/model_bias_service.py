"""
Score a stored tabular model and audit its predictions with Aequitas.

Protected attributes and the privileged group come from the dataset bias report
unless the request overrides them. Vision and regression artifacts are refused:
Aequitas only audits binary classification predictions.
"""
from __future__ import annotations

import io
import logging
import os
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import anyio
import pandas as pd
from fastapi import HTTPException

from ..core.database import get_database
from ..models.dataset import DatasetMetadata
from ..models.model_bias import ModelBiasAuditRequest, ModelBiasAuditResponse
from ..utils.public_dataset_link import resolve_storage_path
from .aequitas_audit import run_aequitas_audit
from .ai_model_service import ai_model_service
from .model_archive import safe_extract_zip, unpack_model_archives
from .model_bias_alerts import build_model_bias_alerts, user_audit_note
from .model_feature_align import restore_group_columns, select_scoring_frame
from .bias_report_service import bias_report_service
from .file_service import file_service
from .metadata_service import metadata_service

logger = logging.getLogger(__name__)

_REGRESSION_TYPES = {
    "tabular_regression",
    "regression",
    "tabular_time_series",
    "time_series",
}
_VISION_TYPES = {
    "image_classification",
    "image_segmentation",
    "object_detection",
    "video_classification",
    "keypoint_detection",
    "computer_vision",
    "audio_classification",
}


def _read_table_bytes(data: bytes, filename: str = "") -> pd.DataFrame:
    name = (filename or "").lower()
    if name.endswith(".zip") or (len(data) >= 2 and data[:2] == b"PK"):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            csv_names = [
                entry
                for entry in archive.namelist()
                if entry.lower().endswith(".csv") and not os.path.basename(entry).startswith("__")
            ]
            if not csv_names:
                raise ValueError("The dataset archive has no CSV for the model audit.")
            preferred = [entry for entry in csv_names if os.path.basename(entry).lower() in {"data.csv", "annotations.csv"}]
            chosen = (preferred or csv_names)[0]
            with archive.open(chosen) as handle:
                return _read_csv_bytes(handle.read())
    return _read_csv_bytes(data)


def _read_csv_bytes(data: bytes) -> pd.DataFrame:
    last_error: Exception | None = None
    for encoding in ("utf-8", "latin-1"):
        try:
            return pd.read_csv(io.BytesIO(data), encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
    if last_error:
        raise ValueError(f"Could not read the evaluation CSV: {last_error}")
    return pd.read_csv(io.BytesIO(data))


def _predictor_dirs(root: Path) -> list[Path]:
    """Prefer the saved predictor over AutoGluon's ``-clone-opt`` copy."""
    found = [
        path
        for path in root.rglob("predictor.pkl")
        if "-clone-opt" not in path.parts
    ]
    return sorted(found, key=lambda path: (len(path.parts), str(path)))


def _score_frame(predictor, frame: pd.DataFrame, expected: list[str], positive_label: Any) -> tuple[pd.Series, str]:
    features = frame.loc[:, expected]
    if hasattr(predictor, "predict_proba"):
        proba = predictor.predict_proba(features)
        column = _positive_proba_column(proba, positive_label)
        return pd.Series(proba[column].to_numpy(), index=features.index), "autogluon_tabular_proba"
    predicted = predictor.predict(features)
    return pd.Series(predicted.to_numpy(), index=features.index), "autogluon_tabular_predict"


def _score_extracted_model(
    root: Path,
    candidates: list[tuple[str, pd.DataFrame]],
    *,
    target_column: str,
    protected: list[str],
    positive_label: Any,
) -> tuple[pd.Series, str, str, pd.DataFrame, list[str]]:
    unpack_model_archives(root)
    predictor_files = _predictor_dirs(root)
    requested_version, requested_frame = candidates[0]
    if predictor_files:
        from autogluon.tabular import TabularPredictor

        predictor = TabularPredictor.load(
            str(predictor_files[0].parent),
            require_py_version_match=False,
        )
        expected = [str(column) for column in predictor.features()]
        selected = select_scoring_frame(candidates, expected, requested_version)
        if selected is None:
            available = [str(column) for column in requested_frame.columns]
            missing = [column for column in expected if column not in requested_frame.columns]
            raise ValueError(
                "The evaluation table does not have the columns this model was trained on. "
                f"Missing: {missing}. Available on {requested_version}: {available}."
            )
        version, frame = selected
        if target_column not in frame.columns:
            raise ValueError(f"Label column '{target_column}' is not in dataset {version}.")
        frame, restored = restore_group_columns(frame, protected)
        missing_attrs = [name for name in protected if name not in frame.columns]
        if missing_attrs:
            raise ValueError(
                f"Protected attributes are not columns in dataset {version}, "
                f"and they could not be rebuilt from one-hot columns: {missing_attrs}."
            )
        scores, scorer = _score_frame(predictor, frame, expected, positive_label)
        return scores, scorer, version, frame, restored

    features = requested_frame.drop(columns=[target_column])
    requested_frame, restored = restore_group_columns(requested_frame, protected)
    missing_attrs = [name for name in protected if name not in requested_frame.columns]
    if missing_attrs:
        raise ValueError(
            f"Protected attributes are not columns in dataset {requested_version}: {missing_attrs}."
        )
    pickles = [
        path
        for path in root.rglob("*")
        if path.suffix.lower() in {".pkl", ".joblib"} and path.is_file()
    ]
    if len(pickles) == 1:
        scores, scorer = _score_sklearn_file(pickles[0], features, positive_label)
        return scores, scorer, requested_version, requested_frame, restored
    if not pickles:
        top = sorted(path.name for path in root.iterdir())[:20]
        raise ValueError(
            "This model archive has no AutoGluon predictor.pkl and no single sklearn .pkl/.joblib file. "
            f"Top-level entries after unpack: {top}."
        )
    raise ValueError(
        "This model archive has several pickle files and no AutoGluon predictor.pkl, so it is not clear which one to score."
    )


def _positive_proba_column(proba: pd.DataFrame, positive_label: Any) -> Any:
    if positive_label is not None:
        for column in proba.columns:
            if str(column) == str(positive_label):
                return column
            try:
                if float(column) == float(positive_label):
                    return column
            except (TypeError, ValueError):
                continue
    if 1 in proba.columns:
        return 1
    if len(proba.columns) == 2:
        return proba.columns[-1]
    raise ValueError(
        "predict_proba returned more than two classes and none matches positive_label. "
        "Pass the class that should count as the positive prediction."
    )


def _score_sklearn_file(path: Path, features: pd.DataFrame, positive_label: Any) -> tuple[pd.Series, str]:
    import joblib

    estimator = joblib.load(path)
    if hasattr(estimator, "predict_proba"):
        proba = estimator.predict_proba(features)
        frame = pd.DataFrame(proba)
        classes = list(getattr(estimator, "classes_", frame.columns))
        frame.columns = classes
        column = _positive_proba_column(frame, positive_label)
        return pd.Series(frame[column].to_numpy(), index=features.index), "sklearn_predict_proba"
    if hasattr(estimator, "predict"):
        predicted = estimator.predict(features)
        return pd.Series(predicted, index=features.index), "sklearn_predict"
    raise ValueError(f"{path.name} has no predict or predict_proba method.")


class ModelBiasService:
    def __init__(self) -> None:
        self.collection = None

    async def initialize(self) -> None:
        db = get_database()
        self.collection = db.model_bias_audits

    async def run_audit(self, request: ModelBiasAuditRequest) -> ModelBiasAuditResponse:
        model = await self._load_model(request.user_id, request.model_id, request.model_version)
        model_type = str(model.get("model_type") or "")
        if model_type in _REGRESSION_TYPES:
            raise HTTPException(
                status_code=422,
                detail="Aequitas audits binary classification predictions. This model is a regression or time-series model.",
            )
        if model_type in _VISION_TYPES:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Aequitas audits a prediction table. Scoring vision or audio artifacts is not part of this step. "
                    "Tabular classification models with an AutoGluon predictor or a single sklearn file are supported."
                ),
            )

        dataset_id = request.dataset_id or model.get("training_dataset")
        if not dataset_id:
            raise HTTPException(status_code=422, detail="dataset_id is required when the model has no training_dataset.")

        bias_report = await bias_report_service.get_report(
            request.user_id, dataset_id, request.dataset_version
        )
        attrs, privileged, target_column, report_pos = _from_bias_report(bias_report)
        protected = list(request.protected_attributes or attrs)
        positive = request.positive_label if request.positive_label is not None else report_pos
        if not protected:
            raise HTTPException(
                status_code=422,
                detail="No protected attributes. Run the dataset bias check first, or pass protected_attributes.",
            )
        if not target_column and bias_report is None:
            raise HTTPException(
                status_code=422,
                detail="No dataset bias report found, so the label column is unknown. Run the dataset bias check first.",
            )

        dataset_version = request.dataset_version
        if dataset_version is None and bias_report is not None:
            dataset_version = bias_report.dataset_version
        dataset = await self._load_dataset(request.user_id, dataset_id, dataset_version)
        if not target_column:
            target_column = (dataset.custom_metadata or {}).get("label_column")
        if not target_column:
            raise HTTPException(status_code=422, detail="Could not determine the label column for this dataset.")

        eval_split = _eval_split(request.split, dataset)
        table = await self._load_table(dataset, eval_split)
        if target_column not in table.columns:
            raise HTTPException(
                status_code=422,
                detail=f"Label column '{target_column}' is not in the evaluation table.",
            )
        candidates = await self._candidate_tables(request.user_id, dataset, eval_split, table)
        model_version = str(model.get("version") or "v1")
        try:
            scores, scorer, scored_version, scored_frame, _restored_groups = await self._score_model(
                request.user_id,
                request.model_id,
                model_version,
                candidates,
                target_column=target_column,
                protected=protected,
                positive_label=positive,
            )
        except (ValueError, AssertionError, KeyError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        audit_input = pd.DataFrame(
            {
                "label_value": scored_frame[target_column].to_numpy(),
                "score": scores.to_numpy(),
            },
            index=scored_frame.index,
        )
        for name in protected:
            audit_input[name] = scored_frame[name].to_numpy()

        try:
            audited = await anyio.to_thread.run_sync(
                lambda: run_aequitas_audit(
                    audit_input,
                    protected_attributes=protected,
                    privileged_groups=privileged,
                    positive_label=positive,
                    score_threshold=request.score_threshold,
                )
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        context_notes = [
            note
            for note in audited["notes"]
            if not note.startswith("Probabilities are turned")
            and not note.startswith("Scores are already")
            and not note.startswith("Statistical significance was skipped")
        ]
        hard_scores = any(note.startswith("Scores are already") for note in audited["notes"])
        notes = [
            user_audit_note(
                n_rows=audited["n_rows"],
                eval_split=eval_split,
                mitigated=scored_version != dataset.version,
                reference_groups=audited["reference_groups"],
                score_threshold=request.score_threshold,
                hard_scores=hard_scores,
            ),
            *context_notes,
        ]
        alerts = build_model_bias_alerts(
            audited["metrics"],
            audited["disparities"],
            audited["reference_groups"],
            audited["performance"],
        )

        now = datetime.now(tz=timezone.utc)
        doc = {
            "user_id": request.user_id,
            "model_id": request.model_id,
            "model_version": model_version,
            "dataset_id": dataset.dataset_id,
            "dataset_version": scored_version,
            "protected_attributes": audited["protected_attributes"],
            "reference_groups": audited["reference_groups"],
            "positive_label": audited["positive_label"],
            "label_mode": audited["label_mode"],
            "eval_split": eval_split,
            "scorer": scorer,
            "n_rows": audited["n_rows"],
            "report": {
                "metrics": audited["metrics"],
                "disparities": audited["disparities"],
                "performance": audited["performance"],
                "alerts": alerts,
            },
            "alerts": alerts,
            "notes": notes,
            "created_at": now,
        }
        result = await self.collection.insert_one(doc)
        doc["id"] = str(result.inserted_id)
        return _to_response(doc)

    async def get_latest(self, user_id: str, model_id: str) -> Optional[ModelBiasAuditResponse]:
        doc = await self.collection.find_one(
            {"user_id": user_id, "model_id": model_id},
            sort=[("created_at", -1)],
        )
        if not doc:
            return None
        doc["id"] = str(doc.pop("_id"))
        return _to_response(doc)

    async def get_latest_for_dataset(self, user_id: str, dataset_id: str) -> Optional[ModelBiasAuditResponse]:
        """Latest audit of any model trained/evaluated on this dataset (any dataset version)."""
        doc = await self.collection.find_one(
            {"user_id": user_id, "dataset_id": dataset_id},
            sort=[("created_at", -1)],
        )
        if not doc:
            return None
        doc["id"] = str(doc.pop("_id"))
        return _to_response(doc)

    async def _load_model(self, user_id: str, model_id: str, version: Optional[str]) -> dict:
        db = get_database()
        if version:
            model = await db.ai_models.find_one(
                {"user_id": user_id, "model_id": model_id, "version": version}
            )
        else:
            model = await db.ai_models.find_one(
                {"user_id": user_id, "model_id": model_id},
                sort=[("created_at", -1)],
            )
        if not model:
            raise HTTPException(status_code=404, detail="Model not found")
        return model

    async def _load_dataset(self, user_id: str, dataset_id: str, version: Optional[str]) -> DatasetMetadata:
        if version:
            dataset = await metadata_service.get_dataset_by_version(dataset_id, user_id, version)
        else:
            dataset = await metadata_service.get_latest_dataset(dataset_id, user_id)
        if not dataset:
            raise HTTPException(status_code=404, detail="Dataset not found")
        return dataset

    async def _load_table(self, dataset: DatasetMetadata, eval_split: Optional[str]) -> pd.DataFrame:
        storage_path = resolve_storage_path(dataset, dataset.file_path)
        if dataset.is_folder:
            data, filename, _media = await file_service.download_folder_subset(
                storage_path,
                eval_split,
                archive_basename=dataset.dataset_id,
                prefer_prebuilt=True,
                store_archive_if_missing=False,
            )
            return _read_table_bytes(data, filename)
        data = await file_service.download_file(storage_path)
        return _read_table_bytes(data, dataset.original_filename or storage_path)

    async def _candidate_tables(
        self,
        user_id: str,
        dataset: DatasetMetadata,
        eval_split: Optional[str],
        requested_table: pd.DataFrame,
    ) -> list[tuple[str, pd.DataFrame]]:
        candidates = [(dataset.version, requested_table)]
        try:
            versions = await metadata_service.get_dataset_versions(dataset.dataset_id, user_id)
        except Exception:
            logger.warning("Could not list dataset versions while aligning model columns", exc_info=True)
            return candidates
        for item in versions:
            if item.dataset_id != dataset.dataset_id or item.version == dataset.version:
                continue
            try:
                frame = await self._load_table(item, eval_split)
            except Exception:
                logger.warning(
                    "Skipped dataset %s %s while aligning model columns",
                    item.dataset_id,
                    item.version,
                    exc_info=True,
                )
                continue
            candidates.append((item.version, frame))
        return candidates

    async def _score_model(
        self,
        user_id: str,
        model_id: str,
        version: str,
        candidates: list[tuple[str, pd.DataFrame]],
        *,
        target_column: str,
        protected: list[str],
        positive_label: Any,
    ) -> tuple[pd.Series, str, str, pd.DataFrame, list[str]]:
        payload = await ai_model_service.download_model_as_zip(user_id, model_id, version)

        def _run() -> tuple[pd.Series, str, str, pd.DataFrame, list[str]]:
            with tempfile.TemporaryDirectory(prefix="model-bias-") as tmp:
                root = Path(tmp)
                with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                    safe_extract_zip(archive, root)
                return _score_extracted_model(
                    root,
                    candidates,
                    target_column=target_column,
                    protected=protected,
                    positive_label=positive_label,
                )

        return await anyio.to_thread.run_sync(_run)


def _from_bias_report(report) -> tuple[list[str], dict, Optional[str], Any]:
    if report is None or not isinstance(report.report, dict):
        return [], {}, None, None
    inner = report.report
    fairness = inner.get("fairness_profile") or {}
    config = fairness.get("config") or {}
    attributes = [str(name) for name in (config.get("protected_attributes") or []) if str(name).strip()]
    privileged = dict(config.get("privileged_groups") or {})
    target = inner.get("target_column") or config.get("target_column")
    positive = config.get("pos_label")
    return attributes, privileged, target, positive


def _eval_split(requested: Optional[str], dataset: DatasetMetadata) -> Optional[str]:
    if requested:
        if requested not in {"train", "test", "drift"}:
            raise HTTPException(status_code=422, detail="split must be train, test, or drift.")
        return requested
    split = (dataset.custom_metadata or {}).get("split")
    if split:
        return "test"
    return None


def _to_response(doc: dict) -> ModelBiasAuditResponse:
    return ModelBiasAuditResponse(
        id=doc.get("id"),
        user_id=doc["user_id"],
        model_id=doc["model_id"],
        model_version=doc["model_version"],
        dataset_id=doc["dataset_id"],
        dataset_version=doc["dataset_version"],
        protected_attributes=doc["protected_attributes"],
        reference_groups=doc["reference_groups"],
        positive_label=doc.get("positive_label"),
        label_mode=doc["label_mode"],
        eval_split=doc.get("eval_split"),
        scorer=doc["scorer"],
        n_rows=doc["n_rows"],
        report=doc["report"],
        alerts=list(doc.get("alerts") or doc.get("report", {}).get("alerts") or []),
        notes=doc["notes"],
        created_at=doc["created_at"],
    )


model_bias_service = ModelBiasService()
