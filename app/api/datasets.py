from typing import List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, File, UploadFile, Depends, HTTPException, Query, Form
from fastapi import status
from fastapi.responses import StreamingResponse
from io import BytesIO
from ..models.dataset import DatasetCreate, DatasetUpdate, DatasetResponse, DatasetMetadata, DatasetFile, PublicDatasetLink
from ..models.upload_job import UploadJobResponse
from ..services.file_service import file_service
from ..services.metadata_service import metadata_service
from ..services.kafka_service import kafka_producer_service
from ..utils.public_dataset_link import is_linked_public_copy, resolve_storage_path
import logging
import uuid
import asyncio
import tempfile
import os

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/datasets", tags=["datasets"])

# Public dataset catalog (summer school)
PUBLIC_USER_ID = "public"


def _to_dataset_response(dataset: DatasetMetadata) -> DatasetResponse:
    return DatasetResponse(
        dataset_id=dataset.dataset_id,
        user_id=dataset.user_id,
        name=dataset.name,
        description=dataset.description,
        version=dataset.version,
        file_type=dataset.file_type,
        file_size=dataset.file_size,
        original_filename=dataset.original_filename,
        files=dataset.files,
        is_folder=dataset.is_folder,
        columns=dataset.columns,
        row_count=dataset.row_count,
        data_types=dataset.data_types,
        tags=dataset.tags,
        custom_metadata=dataset.custom_metadata,
        is_public=dataset.is_public,
        public_source=dataset.public_source,
        public_link=dataset.public_link,
        created_at=dataset.created_at,
        updated_at=dataset.updated_at,
        file_hash=dataset.file_hash,
    )


def _rewrite_files_for_user_namespace(
    files: Optional[List[DatasetFile]], *, src_prefix: str, dst_prefix: str
) -> Optional[List[DatasetFile]]:
    if not files:
        return files
    out: List[DatasetFile] = []
    for f in files:
        fp = f.file_path
        if fp.startswith(src_prefix):
            fp = dst_prefix + fp[len(src_prefix) :]
        out.append(
            DatasetFile(
                filename=f.filename,
                file_path=fp,
                file_size=f.file_size,
                file_type=f.file_type,
                file_hash=f.file_hash,
                content_type=f.content_type,
            )
        )
    return out


def _build_linked_user_file_metadata(
    src: DatasetMetadata,
    *,
    user_id: str,
    dataset_id: str,
    version: str,
    public_dataset_id: str,
    public_version: str,
) -> dict:
    """Build storage metadata for a user import that references public MinIO objects."""
    src_prefix = f"datasets/{src.user_id}/{src.dataset_id}/{src.version}/"
    dst_prefix = f"datasets/{user_id}/{dataset_id}/{version}/"
    tags = [t for t in (src.tags or []) if str(t).lower() != "public"]

    if src.is_folder:
        file_path = dst_prefix
    else:
        file_path = f"{dst_prefix}{src.original_filename}"

    meta = src.dict()
    meta.update(
        {
            "user_id": user_id,
            "dataset_id": dataset_id,
            "version": version,
            "is_public": False,
            "public_source": None,
            "public_link": PublicDatasetLink(
                dataset_id=public_dataset_id,
                version=public_version,
            ),
            "file_path": file_path,
            "files": _rewrite_files_for_user_namespace(
                src.files,
                src_prefix=src_prefix,
                dst_prefix=dst_prefix,
            ),
            "tags": tags,
        }
    )
    return meta


def _parse_csv_list(val: str | None) -> list[str]:
    if not val:
        return []
    return [t.strip() for t in val.split(",") if t.strip()]


async def _update_upload_job(job_id: str, patch: dict) -> None:
    from ..core.database import get_database
    db = get_database()
    await db.upload_jobs.update_one({"job_id": job_id}, {"$set": patch})


async def _run_folder_upload_job(
    *,
    job_id: str,
    user_id: str,
    dataset_id: str,
    name: str,
    description: str | None,
    preserve_structure: bool,
    tags: list[str],
    zip_object_name: str,
    v1: str,
    v2: str,
) -> None:
    """Background ingestion task. Downloads staged ZIP and performs extraction + upload + optional split."""
    from ..core.database import get_database
    db = get_database()

    try:
        await _update_upload_job(
            job_id,
            {
                "status": "running",
                "updated_at": UploadJobResponse.now(),
                "progress": {"phase": "download_zip", "processed_files": 0, "message": "Downloading ZIP from object storage"},
            },
        )

        with tempfile.TemporaryDirectory() as td:
            local_zip = os.path.join(td, "staged.zip")
            await file_service.download_object_to_path(object_name=zip_object_name, dest_path=local_zip)

            await _update_upload_job(
                job_id,
                {
                    "updated_at": UploadJobResponse.now(),
                    "progress": {"phase": "ingest", "processed_files": 0, "message": "Extracting and uploading dataset files"},
                },
            )

            (dataset_files_v1, total_size_v1, split_counts_v1), v2_result = await file_service.upload_dataset_folder_from_zip_path(
                zip_path=local_zip,
                user_id=user_id,
                dataset_id=dataset_id,
                version=v1,
                version_split=v2,
                preserve_structure=preserve_structure,
            )

        if not dataset_files_v1:
            raise HTTPException(status_code=400, detail="No valid files found in ZIP")

        file_types_v1 = list(set([f.file_type for f in dataset_files_v1]))
        folder_path_v1 = f"datasets/{user_id}/{dataset_id}/{v1}/"
        custom_meta_v1 = {"file_count": len(dataset_files_v1), "preserve_structure": preserve_structure}
        if split_counts_v1:
            custom_meta_v1["split"] = split_counts_v1

        dataset_metadata_v1 = DatasetMetadata(
            dataset_id=dataset_id,
            user_id=user_id,
            name=name,
            description=description,
            version=v1,
            file_type=", ".join(file_types_v1),
            file_size=total_size_v1,
            file_path=folder_path_v1,
            original_filename=os.path.basename(zip_object_name),
            files=dataset_files_v1,
            is_folder=True,
            columns=None,
            row_count=None,
            data_types=None,
            tags=tags,
            custom_metadata=custom_meta_v1,
            created_at=datetime.now(tz=timezone.utc),
            updated_at=datetime.now(tz=timezone.utc),
            file_hash=None,
        )
        await db.datasets.insert_one(dataset_metadata_v1.dict(by_alias=True, exclude={"id"}))

        result_version = v1

        if v2_result is not None:
            dataset_files_v2, total_size_v2, split_counts = v2_result
            file_types_v2 = list(set([f.file_type for f in dataset_files_v2]))
            folder_path_v2 = f"datasets/{user_id}/{dataset_id}/{v2}/"
            custom_meta_v2 = {
                "file_count": len(dataset_files_v2),
                "preserve_structure": preserve_structure,
                "split": split_counts,
            }
            dataset_metadata_v2 = DatasetMetadata(
                dataset_id=dataset_id,
                user_id=user_id,
                name=name,
                description=description,
                version=v2,
                file_type=", ".join(file_types_v2),
                file_size=total_size_v2,
                file_path=folder_path_v2,
                original_filename=os.path.basename(zip_object_name),
                files=dataset_files_v2,
                is_folder=True,
                columns=None,
                row_count=None,
                data_types=None,
                tags=tags,
                custom_metadata=custom_meta_v2,
                created_at=datetime.now(tz=timezone.utc),
                updated_at=datetime.now(tz=timezone.utc),
                file_hash=None,
            )
            await db.datasets.insert_one(dataset_metadata_v2.dict(by_alias=True, exclude={"id"}))
            result_version = v2

            # Kafka only once (on split version)
            try:
                await kafka_producer_service.send_dataset_uploaded_event(dataset_metadata_v2)
            except Exception as kafka_error:
                logger.warning(f"Failed to send Kafka event for v2: {kafka_error}")
        else:
            try:
                await kafka_producer_service.send_dataset_uploaded_event(dataset_metadata_v1)
            except Exception as kafka_error:
                logger.warning(f"Failed to send Kafka event for upload: {kafka_error}")

        await _update_upload_job(
            job_id,
            {
                "status": "completed",
                "updated_at": UploadJobResponse.now(),
                "progress": {"phase": "completed", "processed_files": 0, "message": "Dataset upload completed"},
                "result": {"dataset_id": dataset_id, "v1": v1, "v2": (v2 if v2_result else None), "result_version": result_version},
            },
        )

    except HTTPException as e:
        try:
            if e.status_code == 400 and e.detail and "annotation" in str(e.detail).lower():
                await kafka_producer_service.send_dataset_upload_failed_event(
                    user_id=user_id,
                    dataset_id=dataset_id,
                    filename=os.path.basename(zip_object_name),
                    error_message=str(e.detail),
                )
        except Exception as kafka_err:
            logger.warning(f"Failed to send dataset upload failed event: {kafka_err}")

        await _update_upload_job(
            job_id,
            {
                "status": "failed",
                "updated_at": UploadJobResponse.now(),
                "error": str(e.detail),
                "progress": {"phase": "failed", "processed_files": 0, "message": str(e.detail)},
            },
        )
    except Exception as e:
        await _update_upload_job(
            job_id,
            {
                "status": "failed",
                "updated_at": UploadJobResponse.now(),
                "error": str(e),
                "progress": {"phase": "failed", "processed_files": 0, "message": "Upload failed"},
            },
        )


async def _get_next_dataset_name(user_id: str) -> str:
    """
    Generate the next automatic dataset name for a user.
    Returns names like: user_uploaded_dataset_1, user_uploaded_dataset_2, etc.
    """
    try:
        from ..core.database import get_database
        db = get_database()
        
        # Find all datasets with auto-generated names for this user
        cursor = db.datasets.find({
            "user_id": user_id,
            "name": {"$regex": r"^user_uploaded_dataset_\d+$"}
        }, {"name": 1})
        
        datasets = await cursor.to_list(length=1000)
        
        if not datasets:
            return "user_uploaded_dataset_1"
        
        # Extract numbers from names (user_uploaded_dataset_1 -> 1, etc.)
        numbers = []
        for doc in datasets:
            name = doc.get("name", "")
            if name.startswith("user_uploaded_dataset_"):
                try:
                    number = int(name.split("_")[-1])
                    numbers.append(number)
                except (ValueError, IndexError):
                    pass
        
        # Get the max number and increment
        if numbers:
            next_number = max(numbers) + 1
        else:
            next_number = 1
        
        return f"user_uploaded_dataset_{next_number}"
        
    except Exception as e:
        logger.error(f"Error generating dataset name: {e}")
        # Fallback to timestamp-based name
        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
        return f"user_uploaded_dataset_{timestamp}"


async def _get_next_dataset_version(user_id: str, dataset_id: str) -> str:
    """
    Auto-detect the next version number for a dataset.
    Queries existing versions and increments (v1, v2, v3, etc.)
    """
    versions = await _get_next_dataset_versions(user_id, dataset_id, count=1)
    return versions[0]


async def _get_next_dataset_versions(user_id: str, dataset_id: str, count: int = 2) -> tuple:
    """
    Return the next `count` version strings for a dataset (e.g. v1, v2).
    Used so we can reserve v1 for original and v2 for split in one upload flow.
    """
    try:
        from ..core.database import get_database
        db = get_database()

        cursor = db.datasets.find({
            "user_id": user_id,
            "dataset_id": dataset_id
        }, {"version": 1})

        versions = await cursor.to_list(length=1000)

        version_numbers = []
        for doc in versions:
            version_str = doc.get("version", "v1")
            if version_str.startswith("v"):
                try:
                    version_numbers.append(int(version_str[1:]))
                except ValueError:
                    pass

        start = max(version_numbers) + 1 if version_numbers else 1
        return tuple(f"v{i}" for i in range(start, start + count))

    except Exception as e:
        logger.warning(f"Error detecting next versions, defaulting to v1..v{count}: {e}")
        return tuple(f"v{i}" for i in range(1, 1 + count))


@router.post("/upload/{user_id}", response_model=DatasetResponse)
async def upload_dataset(
    user_id: str,
    file: UploadFile = File(...),
    dataset_id: Optional[str] = Form(None),  # Made optional
    name: Optional[str] = Form(None),  # Made optional
    description: Optional[str] = Form(None),
    tags: Optional[str] = Form(None)  # Comma-separated tags
):
    """
    Upload a dataset file and create metadata
    
    This endpoint handles the main flow:
    1. Generate dataset_id (UUID) if not provided
    2. Generate dataset_name if not provided (user_uploaded_dataset_1, user_uploaded_dataset_2, etc.)
    3. Auto-detect next version number for this dataset
    4. Upload file to MinIO with organized path structure
    5. Extract metadata from file content
    6. Store metadata in MongoDB
    
    Version is automatically incremented (v1, v2, v3, etc.)
    dataset_id is optional - if not provided, a UUID will be generated automatically.
    dataset_name is optional - if not provided, an automatic name will be generated.
    """
    try:
        # Validate file type
        if not file.filename:
            raise HTTPException(status_code=400, detail="No file provided")
        
        # Generate dataset_id if not provided
        if not dataset_id:
            dataset_id = str(uuid.uuid4())
            logger.info(f"Generated new dataset_id: {dataset_id}")
        
        # Generate dataset_name if not provided
        if not name:
            name = await _get_next_dataset_name(user_id)
            logger.info(f"Generated new dataset_name: {name}")
        
        # Parse tags if provided
        tag_list = []
        if tags:
            tag_list = [tag.strip() for tag in tags.split(",") if tag.strip()]
        
        # Reserve v1 (original) and v2 (split if applicable)
        v1, v2 = await _get_next_dataset_versions(user_id, dataset_id, count=2)
        logger.info(f"Reserved versions: v1={v1}, v2={v2} for dataset {dataset_id}")
        
        # Upload: original always to v1; split to v2 when large enough
        file_path, v1_metadata, v2_metadata = await file_service.upload_file(
            file=file,
            user_id=user_id,
            dataset_id=dataset_id,
            version=v1,
            version_split=v2,
        )
        
        # Add file path to v1 metadata
        v1_metadata['file_path'] = file_path
        
        # Create v1 dataset record (original)
        dataset_create_v1 = DatasetCreate(
            dataset_id=dataset_id,
            user_id=user_id,
            name=name,
            description=description,
            version=v1,
            tags=tag_list
        )
        dataset_metadata_v1 = await metadata_service.create_dataset_metadata(
            dataset_data=dataset_create_v1,
            file_metadata=v1_metadata
        )
        
        # Optionally create v2 dataset record (split) and use as response
        if v2_metadata is not None:
            dataset_create_v2 = DatasetCreate(
                dataset_id=dataset_id,
                user_id=user_id,
                name=name,
                description=description,
                version=v2,
                tags=tag_list
            )
            dataset_metadata_v2 = await metadata_service.create_dataset_metadata(
                dataset_data=dataset_create_v2,
                file_metadata=v2_metadata
            )
            # Send Kafka only for v2 so the pipeline runs once on the split version (orchestrator expects one event per upload)
            try:
                await kafka_producer_service.send_dataset_uploaded_event(dataset_metadata_v2)
            except Exception as kafka_error:
                logger.warning(f"Failed to send Kafka event for v2: {kafka_error}")
            result_metadata = dataset_metadata_v2
        else:
            try:
                await kafka_producer_service.send_dataset_uploaded_event(dataset_metadata_v1)
            except Exception as kafka_error:
                logger.warning(f"Failed to send Kafka event for upload: {kafka_error}")
            result_metadata = dataset_metadata_v1
        
        return DatasetResponse(
            dataset_id=result_metadata.dataset_id,
            user_id=result_metadata.user_id,
            name=result_metadata.name,
            description=result_metadata.description,
            version=result_metadata.version,
            file_type=result_metadata.file_type,
            file_size=result_metadata.file_size,
            original_filename=result_metadata.original_filename,
            files=result_metadata.files,
            is_folder=result_metadata.is_folder,
            columns=result_metadata.columns,
            row_count=result_metadata.row_count,
            data_types=result_metadata.data_types,
            tags=result_metadata.tags,
            custom_metadata=result_metadata.custom_metadata,
            created_at=result_metadata.created_at,
            updated_at=result_metadata.updated_at,
            file_hash=result_metadata.file_hash
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading dataset: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload dataset")


@router.get("/public", response_model=List[DatasetResponse])
async def list_public_datasets(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    q: Optional[str] = Query(None, description="Search query (dataset_id, name, description)"),
    tags: Optional[str] = Query(None, description="Comma-separated required tags"),
):
    """List datasets in the public catalog."""
    rows = await metadata_service.get_public_datasets(
        skip=skip,
        limit=limit,
        query=q,
        tags=_parse_csv_list(tags),
    )
    return [DatasetResponse(**r.dict()) for r in rows]


@router.get("/public/catalog", response_model=List[DatasetResponse])
async def list_public_datasets_catalog(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    q: Optional[str] = Query(None, description="Search query (dataset_id, name, description)"),
    tags: Optional[str] = Query(None, description="Comma-separated required tags"),
):
    """
    List public datasets for UI browse (one entry per dataset).

    Returns only **v1** (original upload) rows so users do not see duplicate v1/v2 catalog entries.
    Import and pipeline behavior are unchanged; use POST .../import/{user_id} after selection.
    """
    rows = await metadata_service.get_public_datasets_catalog(
        skip=skip,
        limit=limit,
        query=q,
        tags=_parse_csv_list(tags),
    )
    return [DatasetResponse(**r.dict()) for r in rows]


@router.get("/public/{dataset_id}", response_model=DatasetResponse)
async def get_public_dataset_latest(dataset_id: str):
    """Get the latest version of a public dataset."""
    row = await metadata_service.get_public_dataset_latest(dataset_id=dataset_id)
    if not row:
        raise HTTPException(status_code=404, detail="Public dataset not found")
    return DatasetResponse(**row.dict())


@router.get("/public/{dataset_id}/version/{version}", response_model=DatasetResponse)
async def get_public_dataset_version(dataset_id: str, version: str):
    """Get a specific version of a public dataset."""
    row = await metadata_service.get_public_dataset_by_version(
        dataset_id=dataset_id, version=version
    )
    if not row:
        raise HTTPException(status_code=404, detail="Public dataset version not found")
    return DatasetResponse(**row.dict())


@router.post("/public/upload", response_model=DatasetResponse)
async def upload_public_dataset(
    file: UploadFile = File(...),
    dataset_id: Optional[str] = Form(None),
    name: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    public_source: Optional[str] = Form(None),
):
    """
    Upload a dataset into the public catalog.

    Important: This does NOT emit `dataset-events` to Kafka. The pipeline should only start
    after a user imports a public dataset into their own workspace.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    if not dataset_id:
        dataset_id = str(uuid.uuid4())
        logger.info(f"Generated new public dataset_id: {dataset_id}")

    if not name:
        name = f"public_dataset_{dataset_id[:8]}"

    tag_list = _parse_csv_list(tags)
    if "public" not in [t.lower() for t in tag_list]:
        tag_list.append("public")

    v1, v2 = await _get_next_dataset_versions(PUBLIC_USER_ID, dataset_id, count=2)
    file_path, v1_metadata, v2_metadata = await file_service.upload_file(
        file=file,
        user_id=PUBLIC_USER_ID,
        dataset_id=dataset_id,
        version=v1,
        version_split=v2,
    )
    v1_metadata["file_path"] = file_path

    dataset_create_v1 = DatasetCreate(
        dataset_id=dataset_id,
        user_id=PUBLIC_USER_ID,
        name=name,
        description=description,
        version=v1,
        tags=tag_list,
    )
    v1_metadata = dict(v1_metadata)
    v1_metadata["is_public"] = True
    v1_metadata["public_source"] = public_source
    dataset_metadata_v1 = await metadata_service.create_dataset_metadata(
        dataset_data=dataset_create_v1,
        file_metadata=v1_metadata,
    )

    dataset_metadata_v2 = None
    if v2_metadata is not None:
        dataset_create_v2 = DatasetCreate(
            dataset_id=dataset_id,
            user_id=PUBLIC_USER_ID,
            name=name,
            description=description,
            version=v2,
            tags=tag_list,
        )
        v2_metadata = dict(v2_metadata)
        v2_metadata["is_public"] = True
        v2_metadata["public_source"] = public_source
        dataset_metadata_v2 = await metadata_service.create_dataset_metadata(
            dataset_data=dataset_create_v2,
            file_metadata=v2_metadata,
        )

    return (
        DatasetResponse(**dataset_metadata_v2.dict())
        if dataset_metadata_v2
        else DatasetResponse(**dataset_metadata_v1.dict())
    )


@router.post("/public/{public_dataset_id}/import/{user_id}", response_model=DatasetResponse)
async def import_public_dataset_to_user(
    public_dataset_id: str,
    user_id: str,
    public_version: Optional[str] = Query(
        None, description="Public dataset version to import (defaults to latest)"
    ),
    dataset_id: Optional[str] = Query(
        None, description="Optional dataset_id to use in the user's workspace (defaults to public id, with collision handling)"
    ),
):
    """
    Import a public dataset into a user's dataset namespace.

    Creates user-scoped metadata that references the public MinIO prefix (no data copy).
    Emits `dataset-events` for the imported version (v2 when a split exists, else v1).
    """
    if public_version:
        src = await metadata_service.get_public_dataset_by_version(
            dataset_id=public_dataset_id, version=public_version
        )
    else:
        src = await metadata_service.get_public_dataset_latest(dataset_id=public_dataset_id)
    if not src:
        raise HTTPException(status_code=404, detail="Public dataset not found")

    desired_id = dataset_id or public_dataset_id
    existing = await metadata_service.get_dataset_by_id(desired_id, user_id)
    if existing:
        desired_id = f"{desired_id}_{uuid.uuid4().hex[:8]}"

    dst_v1, dst_v2 = await _get_next_dataset_versions(user_id, desired_id, count=2)

    src_versions = await metadata_service.get_dataset_versions(public_dataset_id, PUBLIC_USER_ID)
    public_has_v2 = any(
        (v.version == "v2" and (v.custom_metadata or {}).get("split"))
        for v in src_versions
        if getattr(v, "is_public", False)
    )

    src_v1 = await metadata_service.get_dataset_by_id_and_version(
        public_dataset_id, PUBLIC_USER_ID, "v1"
    )
    if not src_v1 or not src_v1.is_public:
        src_v1 = src

    v1_meta = _build_linked_user_file_metadata(
        src_v1,
        user_id=user_id,
        dataset_id=desired_id,
        version=dst_v1,
        public_dataset_id=public_dataset_id,
        public_version=src_v1.version,
    )
    dataset_create_v1 = DatasetCreate(
        dataset_id=desired_id,
        user_id=user_id,
        name=src_v1.name,
        description=src_v1.description,
        version=dst_v1,
        tags=v1_meta.get("tags", []),
        custom_metadata=v1_meta.get("custom_metadata", {}) or {},
    )
    v1_file_meta = {
        k: v
        for k, v in v1_meta.items()
        if k
        not in {
            "id",
            "_id",
            "dataset_id",
            "user_id",
            "name",
            "description",
            "version",
            "tags",
            "custom_metadata",
            "created_at",
            "updated_at",
        }
    }
    created_v1 = await metadata_service.create_dataset_metadata(
        dataset_data=dataset_create_v1,
        file_metadata=v1_file_meta,
    )
    result_metadata = created_v1

    if public_has_v2:
        src_v2 = await metadata_service.get_dataset_by_id_and_version(
            public_dataset_id, PUBLIC_USER_ID, "v2"
        )
        if src_v2 and src_v2.is_public:
            v2_meta = _build_linked_user_file_metadata(
                src_v2,
                user_id=user_id,
                dataset_id=desired_id,
                version=dst_v2,
                public_dataset_id=public_dataset_id,
                public_version=src_v2.version,
            )
            dataset_create_v2 = DatasetCreate(
                dataset_id=desired_id,
                user_id=user_id,
                name=src_v2.name,
                description=src_v2.description,
                version=dst_v2,
                tags=v2_meta.get("tags", []),
                custom_metadata=v2_meta.get("custom_metadata", {}) or {},
            )
            v2_file_meta = {
                k: v
                for k, v in v2_meta.items()
                if k
                not in {
                    "id",
                    "_id",
                    "dataset_id",
                    "user_id",
                    "name",
                    "description",
                    "version",
                    "tags",
                    "custom_metadata",
                    "created_at",
                    "updated_at",
                }
            }
            created_v2 = await metadata_service.create_dataset_metadata(
                dataset_data=dataset_create_v2,
                file_metadata=v2_file_meta,
            )
            result_metadata = created_v2

    try:
        await kafka_producer_service.send_dataset_uploaded_event(result_metadata)
    except Exception as kafka_error:
        logger.warning(f"Failed to send Kafka event for imported public dataset: {kafka_error}")

    return _to_dataset_response(result_metadata)


@router.post(
    "/upload/folder/{user_id}",
    response_model=UploadJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_dataset_folder(
    user_id: str,
    zip_file: UploadFile = File(...),
    dataset_id: Optional[str] = Form(None),  # Made optional
    name: Optional[str] = Form(None),  # Made optional
    description: Optional[str] = Form(None),
    preserve_structure: bool = Form(True),
    tags: Optional[str] = Form(None)
):
    """
    Upload a folder of dataset files (as zip)
    
    For folder uploads:
    - Generate dataset_id (UUID) if not provided
    - Generate dataset_name if not provided (user_uploaded_dataset_1, user_uploaded_dataset_2, etc.)
    - Auto-detects next version
    - Extracts and uploads all files
    - Simplified metadata (no column/row analysis)
    - Lists all files with sizes and types
    
    dataset_id is optional - if not provided, a UUID will be generated automatically.
    dataset_name is optional - if not provided, an automatic name will be generated.
    """
    # Async upload: stage ZIP → return job_id → ingest in background
    if not zip_file.filename or not zip_file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="File must be a ZIP archive")

    if not dataset_id:
        dataset_id = str(uuid.uuid4())
        logger.info(f"Generated new dataset_id: {dataset_id}")

    if not name:
        name = await _get_next_dataset_name(user_id)
        logger.info(f"Generated new dataset_name: {name}")

    tag_list: list[str] = []
    if tags:
        tag_list = [tag.strip() for tag in tags.split(",") if tag.strip()]

    v1, v2 = await _get_next_dataset_versions(user_id, dataset_id, count=2)
    logger.info(f"Reserved versions: v1={v1}, v2={v2} for dataset folder {dataset_id}")

    job_id = str(uuid.uuid4())
    zip_object_name = f"uploads/{user_id}/{dataset_id}/{job_id}.zip"

    from ..core.database import get_database
    db = get_database()

    now = UploadJobResponse.now()
    job_doc = {
        "job_id": job_id,
        "status": "queued",
        "user_id": user_id,
        "dataset_id": dataset_id,
        "name": name,
        "description": description,
        "tags": tag_list,
        "preserve_structure": preserve_structure,
        "zip_object_name": zip_object_name,
        "v1": v1,
        "v2": v2,
        "created_at": now,
        "updated_at": now,
        "progress": {"phase": "upload_zip", "processed_files": 0, "message": "Staging ZIP in object storage"},
        "result": None,
        "error": None,
        "metadata": {"original_filename": zip_file.filename},
    }
    await db.upload_jobs.insert_one(job_doc)

    # Stage ZIP in MinIO (multipart, unknown length)
    await file_service.put_object_from_upload_file(object_name=zip_object_name, upload=zip_file, content_type="application/zip")

    await _update_upload_job(
        job_id,
        {
            "updated_at": UploadJobResponse.now(),
            "progress": {"phase": "queued", "processed_files": 0, "message": "ZIP staged; ingestion queued"},
        },
    )

    asyncio.create_task(
        _run_folder_upload_job(
            job_id=job_id,
            user_id=user_id,
            dataset_id=dataset_id,
            name=name,
            description=description,
            preserve_structure=preserve_structure,
            tags=tag_list,
            zip_object_name=zip_object_name,
            v1=v1,
            v2=v2,
        )
    )

    return UploadJobResponse(
        job_id=job_id,
        status="queued",
        user_id=user_id,
        dataset_id=dataset_id,
        name=name,
        created_at=now,
        updated_at=UploadJobResponse.now(),
        progress=job_doc["progress"],
        result=None,
        error=None,
        metadata=job_doc["metadata"],
    )


@router.get("/upload/jobs/{job_id}", response_model=UploadJobResponse)
async def get_upload_job(job_id: str):
    """Get current status/progress of an upload job."""
    from ..core.database import get_database
    db = get_database()
    doc = await db.upload_jobs.find_one({"job_id": job_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Upload job not found")
    return UploadJobResponse(**doc)


@router.get("/upload/jobs/{job_id}/dataset", response_model=DatasetResponse)
async def get_upload_job_dataset(job_id: str):
    """
    Return the resulting dataset metadata once the job is completed.
    - If still running: 409
    - If failed: 400 with error
    """
    from ..core.database import get_database
    db = get_database()
    job = await db.upload_jobs.find_one({"job_id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Upload job not found")

    if job.get("status") == "failed":
        raise HTTPException(status_code=400, detail=job.get("error") or "Upload job failed")
    if job.get("status") != "completed":
        raise HTTPException(status_code=409, detail="Upload job not completed yet")

    result = job.get("result") or {}
    dataset_id = result.get("dataset_id")
    user_id = job.get("user_id")
    version = result.get("result_version")
    if not dataset_id or not user_id or not version:
        raise HTTPException(status_code=500, detail="Upload job completed but result is missing")

    created_dataset = await db.datasets.find_one({"dataset_id": dataset_id, "user_id": user_id, "version": version})
    if not created_dataset:
        raise HTTPException(status_code=404, detail="Resulting dataset not found")
    return DatasetResponse(**created_dataset)


@router.get("/search/{user_id}", response_model=List[DatasetResponse])
async def search_datasets(
    user_id: str,
    query: Optional[str] = Query(None, description="Search in name, description, and dataset_id"),
    tags: Optional[str] = Query(None, description="Comma-separated tags to filter by"),
    file_type: Optional[str] = Query(None, description="File type to filter by"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000)
):
    """Search datasets with various filters"""
    # Parse tags if provided
    tag_list = None
    if tags:
        tag_list = [tag.strip() for tag in tags.split(",") if tag.strip()]
    
    datasets = await metadata_service.search_datasets(
        user_id=user_id,
        query=query,
        tags=tag_list,
        file_type=file_type,
        skip=skip,
        limit=limit
    )
    
    return [
        DatasetResponse(
            dataset_id=dataset.dataset_id,
            user_id=dataset.user_id,
            name=dataset.name,
            description=dataset.description,
            version=dataset.version,
            file_type=dataset.file_type,
            file_size=dataset.file_size,
            original_filename=dataset.original_filename,
            files=dataset.files,
            is_folder=dataset.is_folder,
            columns=dataset.columns,
            row_count=dataset.row_count,
            data_types=dataset.data_types,
            tags=dataset.tags,
            custom_metadata=dataset.custom_metadata,
            created_at=dataset.created_at,
            updated_at=dataset.updated_at,
            file_hash=dataset.file_hash
        )
        for dataset in datasets
    ]


@router.get("/{user_id}/{dataset_id}", response_model=DatasetResponse)
async def get_dataset(user_id: str, dataset_id: str):
    """Get latest dataset metadata by user_id and dataset_id"""
    dataset = await metadata_service.get_latest_dataset(dataset_id, user_id)
    
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    
    return _to_dataset_response(dataset)


@router.get("/{user_id}", response_model=List[DatasetResponse])
async def get_user_datasets(
    user_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000)
):
    """Get all datasets for a user with pagination"""
    datasets = await metadata_service.get_datasets_by_user(user_id, skip, limit)
    
    return [_to_dataset_response(dataset) for dataset in datasets]


@router.put("/{user_id}/{dataset_id}", response_model=DatasetResponse)
async def update_dataset(
    user_id: str,
    dataset_id: str,
    update_data: DatasetUpdate
):
    """Update dataset metadata"""
    updated_dataset = await metadata_service.update_dataset_metadata(
        dataset_id, user_id, update_data
    )
    
    if not updated_dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    
    return _to_dataset_response(updated_dataset)


@router.delete("/{user_id}/{dataset_id}")
async def delete_dataset(user_id: str, dataset_id: str):
    """Delete all versions of a dataset and their files"""
    # Get all versions of the dataset first
    datasets = await metadata_service.get_dataset_versions(dataset_id, user_id)
    if not datasets:
        raise HTTPException(status_code=404, detail="Dataset not found")
    
    # Delete owned MinIO objects only (linked public imports have no user copy).
    files_deleted = 0
    files_failed = 0
    for dataset in datasets:
        if is_linked_public_copy(dataset):
            logger.info(
                "Skipping MinIO delete for linked public import %s version %s",
                dataset.dataset_id,
                dataset.version,
            )
            continue
        try:
            if dataset.is_folder:
                deleted_count = await file_service.delete_folder_files(dataset.file_path)
                files_deleted += deleted_count
                logger.info(f"Deleted {deleted_count} files from folder: {dataset.file_path}")
            else:
                if await file_service.delete_file(dataset.file_path):
                    files_deleted += 1
                else:
                    files_failed += 1
        except Exception as e:
            logger.warning(f"Failed to delete files for {dataset.file_path}: {e}")
            files_failed += 1
    
    # Delete all metadata from MongoDB
    versions_deleted = await metadata_service.delete_all_dataset_versions(dataset_id, user_id)
    
    if versions_deleted == 0:
        raise HTTPException(status_code=500, detail="Failed to delete dataset metadata")
    
    return {
        "message": f"All {versions_deleted} version(s) of dataset deleted successfully",
        "versions_deleted": versions_deleted,
        "files_deleted": files_deleted,
        "files_failed": files_failed
    }


@router.get("/{user_id}/{dataset_id}/download")
async def download_dataset(
    user_id: str,
    dataset_id: str,
    filename: Optional[str] = Query(None, description="Specific filename to download (for folders)"),
    split: Optional[str] = Query(None, description="For split datasets: 'train', 'test', or 'drift' to download only that subset"),
):
    """
    Download latest dataset file or folder.

    - For single files: downloads the file
    - For folders without filename: downloads all files as ZIP, or a single raw file when the
      folder (or split subfolder) contains exactly one file (typical for tabular v2 splits)
    - For folders with filename: downloads specific file from folder
    - split=train|test|drift: when dataset has train/test/drift split, download only that subset (does not affect non-split datasets)
    """
    dataset = await metadata_service.get_latest_dataset(dataset_id, user_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    if dataset.is_folder:
        if filename:
            dataset_files = dataset.files or []
            target_file = next((f for f in dataset_files if f.filename == filename), None)
            if not target_file:
                raise HTTPException(status_code=404, detail=f"File '{filename}' not found in dataset")
            file_data = await file_service.download_file(
                resolve_storage_path(dataset, target_file.file_path)
            )
            return StreamingResponse(
                BytesIO(file_data),
                media_type='application/octet-stream',
                headers={"Content-Disposition": f"attachment; filename={filename}"}
            )
        subfolder = None
        if split and split in ("train", "test", "drift") and (dataset.custom_metadata or {}).get("split"):
            subfolder = split
        file_data, download_name, media_type = await file_service.download_folder_subset(
            resolve_storage_path(dataset, dataset.file_path),
            subfolder_prefix=subfolder,
            archive_basename=f"{dataset_id}_{dataset.version}",
        )
        return StreamingResponse(
            BytesIO(file_data),
            media_type=media_type,
            headers={"Content-Disposition": f"attachment; filename={download_name}"},
        )
    file_data = await file_service.download_file(
        resolve_storage_path(dataset, dataset.file_path)
    )
    return StreamingResponse(
        BytesIO(file_data),
        media_type='application/octet-stream',
        headers={"Content-Disposition": f"attachment; filename={dataset.original_filename}"}
    )


@router.get("/{user_id}/{dataset_id}/version/{version}/download")
async def download_dataset_by_version(
    user_id: str,
    dataset_id: str,
    version: str,
    filename: Optional[str] = Query(None, description="Specific filename to download (for folders)"),
    split: Optional[str] = Query(None, description="For split datasets: 'train', 'test', or 'drift'"),
):
    """
    Download a specific version of a dataset file or folder.
    Use split=train|test|drift to download only that subset when the dataset has a split.
    Tabular split subsets with one file return a ZIP containing that file (AutoML Tabular expects one file per archive).
    """
    dataset = await metadata_service.get_dataset_by_version(dataset_id, user_id, version)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset version not found")

    if dataset.is_folder:
        if filename:
            dataset_files = dataset.files or []
            target_file = next((f for f in dataset_files if f.filename == filename), None)
            if not target_file:
                raise HTTPException(status_code=404, detail=f"File '{filename}' not found in dataset")
            file_data = await file_service.download_file(
                resolve_storage_path(dataset, target_file.file_path)
            )
            return StreamingResponse(
                BytesIO(file_data),
                media_type='application/octet-stream',
                headers={"Content-Disposition": f"attachment; filename={filename}"}
            )
        subfolder = None
        if split and split in ("train", "test", "drift") and (dataset.custom_metadata or {}).get("split"):
            subfolder = split
        file_data, download_name, media_type = await file_service.download_folder_subset(
            resolve_storage_path(dataset, dataset.file_path),
            subfolder_prefix=subfolder,
            archive_basename=f"{dataset_id}_{version}",
        )
        return StreamingResponse(
            BytesIO(file_data),
            media_type=media_type,
            headers={"Content-Disposition": f"attachment; filename={download_name}"},
        )
    file_data = await file_service.download_file(
        resolve_storage_path(dataset, dataset.file_path)
    )
    return StreamingResponse(
        BytesIO(file_data),
        media_type='application/octet-stream',
        headers={"Content-Disposition": f"attachment; filename={dataset.original_filename}"}
    )


@router.get("/{user_id}/{dataset_id}/files", response_model=List[DatasetFile])
async def list_dataset_files(
    user_id: str, 
    dataset_id: str,
    version: Optional[str] = Query(None, description="Specific version (defaults to latest)")
):
    """
    List all files in a dataset folder
    
    For single file datasets, returns a single-item list.
    For folder datasets, returns all files with metadata.
    """
    try:
        # Get dataset metadata
        if version:
            dataset = await metadata_service.get_dataset_by_version(dataset_id, user_id, version)
        else:
            dataset = await metadata_service.get_latest_dataset(dataset_id, user_id)
        
        if not dataset:
            raise HTTPException(status_code=404, detail="Dataset not found")
        
        # Return files list
        if dataset.is_folder and dataset.files:
            logger.info(f"Listed {len(dataset.files)} files for dataset {dataset_id} version {dataset.version}")
            return dataset.files
        else:
            # For single files, create a single-item list
            single_file = DatasetFile(
                filename=dataset.original_filename,
                file_path=dataset.file_path,
                file_size=dataset.file_size,
                file_type=dataset.file_type,
                file_hash=dataset.file_hash or "",
                content_type="application/octet-stream"
            )
            return [single_file]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing dataset files: {e}")
        raise HTTPException(status_code=500, detail="Failed to list dataset files")


@router.get("/{user_id}/{dataset_id}/versions", response_model=List[DatasetResponse])
async def get_dataset_versions(user_id: str, dataset_id: str):
    """Get all versions of a dataset"""
    datasets = await metadata_service.get_dataset_versions(dataset_id, user_id)
    
    return [_to_dataset_response(dataset) for dataset in datasets]


@router.get("/{user_id}/{dataset_id}/version/{version}", response_model=DatasetResponse)
async def get_dataset_by_version(user_id: str, dataset_id: str, version: str):
    """Get a specific version of a dataset"""
    dataset = await metadata_service.get_dataset_by_version(dataset_id, user_id, version)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return _to_dataset_response(dataset)


@router.delete("/{user_id}/{dataset_id}/version/{version}")
async def delete_dataset_by_version(user_id: str, dataset_id: str, version: str):
    """Delete a specific version of a dataset and its file(s)"""
    dataset = await metadata_service.get_dataset_by_version(dataset_id, user_id, version)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    
    # Handle folder vs single file deletion
    files_deleted = 0
    if not is_linked_public_copy(dataset):
        if dataset.is_folder:
            files_deleted = await file_service.delete_folder_files(dataset.file_path)
            logger.info(f"Deleted {files_deleted} files from folder: {dataset.file_path}")
        else:
            file_deleted = await file_service.delete_file(dataset.file_path)
            files_deleted = 1 if file_deleted else 0
    else:
        logger.info(
            "Skipping MinIO delete for linked public import %s version %s",
            dataset.dataset_id,
            dataset.version,
        )
    
    metadata_deleted = await metadata_service.delete_dataset_by_version(dataset_id, user_id, version)
    if not metadata_deleted:
        raise HTTPException(status_code=500, detail="Failed to delete dataset metadata")
    
    return {
        "message": "Dataset deleted successfully",
        "files_deleted": files_deleted,
        "metadata_deleted": metadata_deleted
    }

