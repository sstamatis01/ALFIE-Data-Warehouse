from typing import Optional
from datetime import datetime, timezone
from .metadata_service import metadata_service
from ..core.database import get_database
from ..models.bias_report import BiasReportCreate, BiasReportResponse


class BiasReportService:
    def __init__(self) -> None:
        self.collection = None

    async def initialize(self) -> None:
        db = get_database()
        self.collection = db.bias_reports

    async def upsert_report(self, data: BiasReportCreate) -> BiasReportResponse:
        # Ensure dataset exists with specific version
        dataset = await metadata_service.get_dataset_by_id_and_version(
            data.dataset_id, data.user_id, data.dataset_version
        )
        if not dataset:
            raise ValueError(f"Dataset {data.dataset_id} version {data.dataset_version} not found for bias report")

        now = datetime.now(tz=timezone.utc)
        update = {
            "$set": {
                "user_id": data.user_id,
                "dataset_id": data.dataset_id,
                "dataset_version": data.dataset_version,
                "report": data.report,
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        }
        # Update unique constraint to include dataset_version
        await self.collection.update_one(
            {
                "user_id": data.user_id, 
                "dataset_id": data.dataset_id,
                "dataset_version": data.dataset_version
            }, 
            update, 
            upsert=True
        )

        doc = await self.collection.find_one({
            "user_id": data.user_id, 
            "dataset_id": data.dataset_id,
            "dataset_version": data.dataset_version
        })
        return BiasReportResponse(
            id=str(doc.get("_id")) if doc and doc.get("_id") else None,
            user_id=doc["user_id"],
            dataset_id=doc["dataset_id"],
            dataset_version=doc["dataset_version"],
            report=doc["report"],
            created_at=doc["created_at"],
            updated_at=doc["updated_at"],
        )

    async def get_report(self, user_id: str, dataset_id: str, dataset_version: str = None) -> Optional[BiasReportResponse]:
        query = {"user_id": user_id, "dataset_id": dataset_id}
        if dataset_version:
            query["dataset_version"] = dataset_version
        else:
            # If no version specified, get the latest one
            cursor = self.collection.find(query).sort("created_at", -1).limit(1)
            docs = await cursor.to_list(length=1)
            doc = docs[0] if docs else None
        
        if dataset_version:
            doc = await self.collection.find_one(query)
        
        if not doc:
            return None
        return BiasReportResponse(
            id=str(doc.get("_id")) if doc and doc.get("_id") else None,
            user_id=doc["user_id"],
            dataset_id=doc["dataset_id"],
            dataset_version=doc.get("dataset_version", "v1"),  # Backward compatibility
            report=doc["report"],
            created_at=doc["created_at"],
            updated_at=doc["updated_at"],
        )

    async def get_all_reports(self, user_id: str, dataset_id: str) -> list[BiasReportResponse]:
        """Get all bias reports for a dataset (all versions)"""
        cursor = self.collection.find({"user_id": user_id, "dataset_id": dataset_id}).sort("created_at", -1)
        docs = await cursor.to_list(length=None)
        return [
            BiasReportResponse(
                id=str(doc.get("_id")) if doc and doc.get("_id") else None,
                user_id=doc["user_id"],
                dataset_id=doc["dataset_id"],
                dataset_version=doc.get("dataset_version", "v1"),  # Backward compatibility
                report=doc["report"],
                created_at=doc["created_at"],
                updated_at=doc["updated_at"],
            )
            for doc in docs
        ]

    async def delete_report(self, user_id: str, dataset_id: str, dataset_version: str = None) -> bool:
        """Delete a bias report (specific version or all versions if no version specified)"""
        query = {"user_id": user_id, "dataset_id": dataset_id}
        if dataset_version:
            query["dataset_version"] = dataset_version
        
        result = await self.collection.delete_many(query)
        return result.deleted_count > 0


bias_report_service = BiasReportService()
