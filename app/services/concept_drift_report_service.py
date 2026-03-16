from typing import Optional, List
from datetime import datetime, timezone
from ..core.database import get_database
from ..models.concept_drift_report import ConceptDriftReportCreate, ConceptDriftReportResponse
import logging

logger = logging.getLogger(__name__)


def _ensure_datetime(value):
    """Ensure value is a timezone-aware datetime for JSON serialization."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return value


class ConceptDriftReportService:
    def __init__(self) -> None:
        self.collection = None

    async def initialize(self) -> None:
        db = get_database()
        self.collection = db.concept_drift_reports

    async def upsert_report(self, data: ConceptDriftReportCreate) -> ConceptDriftReportResponse:
        """Create or update a concept drift report (unique by user, dataset version, model version)."""
        now = datetime.now(tz=timezone.utc)
        update = {
            "$set": {
                "user_id": data.user_id,
                "dataset_id": data.dataset_id,
                "dataset_version": data.dataset_version,
                "model_id": data.model_id,
                "model_version": data.model_version,
                "report": data.report,
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        }
        await self.collection.update_one(
            {
                "user_id": data.user_id,
                "dataset_id": data.dataset_id,
                "dataset_version": data.dataset_version,
                "model_id": data.model_id,
                "model_version": data.model_version,
            },
            update,
            upsert=True,
        )
        doc = await self.collection.find_one({
            "user_id": data.user_id,
            "dataset_id": data.dataset_id,
            "dataset_version": data.dataset_version,
            "model_id": data.model_id,
            "model_version": data.model_version,
        })
        if not doc:
            raise RuntimeError("Concept drift report doc not found after upsert")
        return ConceptDriftReportResponse(
            id=str(doc["_id"]) if doc.get("_id") else None,
            user_id=doc["user_id"],
            dataset_id=doc["dataset_id"],
            dataset_version=doc["dataset_version"],
            model_id=doc["model_id"],
            model_version=doc["model_version"],
            report=doc["report"],
            created_at=_ensure_datetime(doc["created_at"]),
            updated_at=_ensure_datetime(doc["updated_at"]),
        )

    async def get_report(
        self,
        user_id: str,
        dataset_id: str,
        model_id: str,
        dataset_version: Optional[str] = None,
        model_version: Optional[str] = None,
    ) -> Optional[ConceptDriftReportResponse]:
        """Get a single concept drift report (specific versions or latest)."""
        query = {"user_id": user_id, "dataset_id": dataset_id, "model_id": model_id}
        if dataset_version:
            query["dataset_version"] = dataset_version
        if model_version:
            query["model_version"] = model_version
        if not dataset_version and not model_version:
            cursor = self.collection.find(query).sort("created_at", -1).limit(1)
            docs = await cursor.to_list(length=1)
            doc = docs[0] if docs else None
        else:
            doc = await self.collection.find_one(query)
        if not doc:
            return None
        return ConceptDriftReportResponse(
            id=str(doc["_id"]) if doc.get("_id") else None,
            user_id=doc["user_id"],
            dataset_id=doc["dataset_id"],
            dataset_version=doc["dataset_version"],
            model_id=doc["model_id"],
            model_version=doc["model_version"],
            report=doc["report"],
            created_at=_ensure_datetime(doc["created_at"]),
            updated_at=_ensure_datetime(doc["updated_at"]),
        )

    async def get_all_reports(
        self,
        user_id: str,
        dataset_id: str,
        model_id: str,
        dataset_version: Optional[str] = None,
        model_version: Optional[str] = None,
    ) -> List[ConceptDriftReportResponse]:
        """Get all concept drift reports for a dataset/model (optionally filtered by versions)."""
        query = {"user_id": user_id, "dataset_id": dataset_id, "model_id": model_id}
        if dataset_version:
            query["dataset_version"] = dataset_version
        if model_version:
            query["model_version"] = model_version
        cursor = self.collection.find(query).sort("created_at", -1)
        docs = await cursor.to_list(length=None)
        return [
            ConceptDriftReportResponse(
                id=str(doc["_id"]) if doc.get("_id") else None,
                user_id=doc["user_id"],
                dataset_id=doc["dataset_id"],
                dataset_version=doc["dataset_version"],
                model_id=doc["model_id"],
                model_version=doc["model_version"],
                report=doc["report"],
                created_at=_ensure_datetime(doc["created_at"]),
                updated_at=_ensure_datetime(doc["updated_at"]),
            )
            for doc in docs
        ]

    async def delete_report(
        self,
        user_id: str,
        dataset_id: str,
        model_id: str,
        dataset_version: Optional[str] = None,
        model_version: Optional[str] = None,
    ) -> bool:
        """Delete concept drift report(s). If no versions given, deletes all for this dataset/model."""
        query = {"user_id": user_id, "dataset_id": dataset_id, "model_id": model_id}
        if dataset_version:
            query["dataset_version"] = dataset_version
        if model_version:
            query["model_version"] = model_version
        result = await self.collection.delete_many(query)
        return result.deleted_count > 0


concept_drift_report_service = ConceptDriftReportService()
