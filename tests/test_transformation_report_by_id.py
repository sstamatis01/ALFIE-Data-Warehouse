"""get_report_by_id: valid ObjectId returns the document; invalid ids return None."""
import asyncio
from datetime import datetime, timezone

from bson import ObjectId

from app.services.transformation_report_service import TransformationReportService


class _Collection:
    def __init__(self, doc):
        self.doc = doc

    async def find_one(self, query):
        if query.get("_id") == self.doc["_id"]:
            return self.doc
        return None


def test_get_report_by_id_valid_and_invalid():
    oid = ObjectId()
    now = datetime.now(tz=timezone.utc)
    doc = {
        "_id": oid,
        "user_id": "user-1",
        "dataset_id": "dataset-1",
        "version": "v3",
        "report": [{"transformation": "missing_value_fill"}],
        "created_at": now,
        "updated_at": now,
    }
    service = TransformationReportService()
    service.collection = _Collection(doc)

    async def run():
        found = await service.get_report_by_id(str(oid))
        missing = await service.get_report_by_id(str(ObjectId()))
        invalid = await service.get_report_by_id("not-an-object-id")
        return found, missing, invalid

    found, missing, invalid = asyncio.run(run())
    assert found is not None
    assert found.id == str(oid)
    assert found.version == "v3"
    assert found.report[0]["transformation"] == "missing_value_fill"
    assert missing is None
    assert invalid is None
