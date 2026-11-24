from typing import Optional
from datetime import datetime, timezone
from bson import ObjectId
from bson.errors import InvalidId
from ..core.database import get_database
from ..models.transformation_report import (
    TransformationReportCreate,
    TransformationReportResponse,
)


def _ensure_datetime(value):
    """Ensure value is a timezone-aware datetime for JSON serialization."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return value


def _to_response(doc: dict) -> TransformationReportResponse:
    return TransformationReportResponse(
        id=str(doc.get("_id")) if doc.get("_id") else None,
        user_id=doc["user_id"],
        dataset_id=doc["dataset_id"],
        version=doc["version"],
        report=doc["report"],
        created_at=_ensure_datetime(doc["created_at"]),
        updated_at=_ensure_datetime(doc["updated_at"]),
    )


class TransformationReportService:
    def __init__(self) -> None:
        self.collection = None

    async def initialize(self) -> None:
        db = get_database()
        self.collection = db.transformation_reports

    async def upsert_report(self, data: TransformationReportCreate) -> TransformationReportResponse:
        now = datetime.now(tz=timezone.utc)
        update = {
            "$set": {
                "user_id": data.user_id,
                "dataset_id": data.dataset_id,
                "version": data.version,
                "report": data.report,
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        }
        await self.collection.update_one(
            {"user_id": data.user_id, "dataset_id": data.dataset_id, "version": data.version},
            update,
            upsert=True,
        )
        doc = await self.collection.find_one({"user_id": data.user_id, "dataset_id": data.dataset_id, "version": data.version})
        if not doc:
            raise RuntimeError("Transformation report doc not found after upsert")
        return _to_response(doc)

    async def get_report(self, user_id: str, dataset_id: str, version: str) -> Optional[TransformationReportResponse]:
        doc = await self.collection.find_one({"user_id": user_id, "dataset_id": dataset_id, "version": version})
        if not doc:
            return None
        return _to_response(doc)

    async def get_report_by_id(self, report_id: str) -> Optional[TransformationReportResponse]:
        """Load a transformation report by MongoDB id. Invalid ids return None."""
        try:
            oid = ObjectId(report_id)
        except (InvalidId, TypeError):
            return None
        doc = await self.collection.find_one({"_id": oid})
        if not doc:
            return None
        return _to_response(doc)

    async def get_latest_report_for_dataset(
        self, user_id: str, dataset_id: str
    ) -> Optional[TransformationReportResponse]:
        """Most recently updated transformation report for a dataset (any version)."""
        doc = await self.collection.find_one(
            {"user_id": user_id, "dataset_id": dataset_id},
            sort=[("updated_at", -1), ("created_at", -1)],
        )
        if not doc:
            return None
        return _to_response(doc)

    async def delete_report(self, user_id: str, dataset_id: str, version: str) -> bool:
        """Delete a transformation report"""
        result = await self.collection.delete_one({"user_id": user_id, "dataset_id": dataset_id, "version": version})
        return result.deleted_count > 0


transformation_report_service = TransformationReportService()

