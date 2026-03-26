from typing import List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, File, UploadFile, Depends, HTTPException, Query, Form
from fastapi.responses import StreamingResponse
from io import BytesIO
from ..models.dataset import DatasetCreate, DatasetUpdate, DatasetResponse, DatasetMetadata, DatasetFile
from ..services.file_service import file_service
from ..services.metadata_service import metadata_service
from ..services.kafka_service import kafka_producer_service
import logging
import uuid

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/datasets", tags=["datasets"])


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


@router.post("/upload/folder/{user_id}", response_model=DatasetResponse)
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
    try:
        if not zip_file.filename or not zip_file.filename.endswith('.zip'):
            raise HTTPException(status_code=400, detail="File must be a ZIP archive")
        
        # Generate dataset_id if not provided
        if not dataset_id:
            dataset_id = str(uuid.uuid4())
            logger.info(f"Generated new dataset_id: {dataset_id}")
        
        # Generate dataset_name if not provided
        if not name:
            name = await _get_next_dataset_name(user_id)
            logger.info(f"Generated new dataset_name: {name}")
        
        tag_list = []
        if tags:
            tag_list = [tag.strip() for tag in tags.split(",") if tag.strip()]
        
        v1, v2 = await _get_next_dataset_versions(user_id, dataset_id, count=2)
        logger.info(f"Reserved versions: v1={v1}, v2={v2} for dataset folder {dataset_id}")
        
        # Upload: original always to v1; split to v2 when large enough
        try:
            (dataset_files_v1, total_size_v1, split_counts_v1), v2_result = await file_service.upload_dataset_folder(
                zip_file=zip_file,
                user_id=user_id,
                dataset_id=dataset_id,
                version=v1,
                version_split=v2,
                preserve_structure=preserve_structure
            )
        except HTTPException as e:
            if e.status_code == 400 and e.detail and "annotation" in str(e.detail).lower():
                try:
                    await kafka_producer_service.send_dataset_upload_failed_event(
                        user_id=user_id,
                        dataset_id=dataset_id,
                        filename=zip_file.filename or "archive.zip",
                        error_message=e.detail,
                    )
                except Exception as kafka_err:
                    logger.warning(f"Failed to send dataset upload failed event: {kafka_err}")
            raise

        if not dataset_files_v1:
            raise HTTPException(status_code=400, detail="No valid files found in ZIP")
        
        file_types_v1 = list(set([f.file_type for f in dataset_files_v1]))
        folder_path_v1 = f"datasets/{user_id}/{dataset_id}/{v1}/"
        custom_meta_v1 = {"file_count": len(dataset_files_v1), "preserve_structure": preserve_structure}
        # If the uploaded folder already had train/test/drift structure (e.g., mitigated dataset zip),
        # preserve split metadata on this version so split=train|test|drift downloads work.
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
            original_filename=zip_file.filename,
            files=dataset_files_v1,
            is_folder=True,
            columns=None,
            row_count=None,
            data_types=None,
            tags=tag_list,
            custom_metadata=custom_meta_v1,
            created_at=datetime.now(tz=timezone.utc),
            updated_at=datetime.now(tz=timezone.utc),
            file_hash=None
        )
        from ..core.database import get_database
        db = get_database()
        await db.datasets.insert_one(dataset_metadata_v1.dict(by_alias=True, exclude={'id'}))
        
        if v2_result is not None:
            dataset_files_v2, total_size_v2, split_counts = v2_result
            file_types_v2 = list(set([f.file_type for f in dataset_files_v2]))
            folder_path_v2 = f"datasets/{user_id}/{dataset_id}/{v2}/"
            custom_meta_v2 = {"file_count": len(dataset_files_v2), "preserve_structure": preserve_structure, "split": split_counts}
            dataset_metadata_v2 = DatasetMetadata(
                dataset_id=dataset_id,
                user_id=user_id,
                name=name,
                description=description,
                version=v2,
                file_type=", ".join(file_types_v2),
                file_size=total_size_v2,
                file_path=folder_path_v2,
                original_filename=zip_file.filename,
                files=dataset_files_v2,
                is_folder=True,
                columns=None,
                row_count=None,
                data_types=None,
                tags=tag_list,
                custom_metadata=custom_meta_v2,
                created_at=datetime.now(tz=timezone.utc),
                updated_at=datetime.now(tz=timezone.utc),
                file_hash=None
            )
            await db.datasets.insert_one(dataset_metadata_v2.dict(by_alias=True, exclude={'id'}))
            # Send Kafka only for v2 so the pipeline runs once on the split version (orchestrator expects one event per upload)
            try:
                await kafka_producer_service.send_dataset_uploaded_event(dataset_metadata_v2)
            except Exception as kafka_error:
                logger.warning(f"Failed to send Kafka event for v2: {kafka_error}")
            created_dataset = await db.datasets.find_one({"dataset_id": dataset_id, "user_id": user_id, "version": v2})
        else:
            try:
                await kafka_producer_service.send_dataset_uploaded_event(dataset_metadata_v1)
            except Exception as kafka_error:
                logger.warning(f"Failed to send Kafka event for upload: {kafka_error}")
            created_dataset = await db.datasets.find_one({"dataset_id": dataset_id, "user_id": user_id, "version": v1})
        
        logger.info(f"Dataset folder uploaded: {dataset_id} (v1 + v2 split)" if v2_result else f"Dataset folder uploaded: {dataset_id} (v1 only)")
        
        return DatasetResponse(**created_dataset)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading dataset folder: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload dataset folder")


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
        created_at=dataset.created_at,
        updated_at=dataset.updated_at,
        file_hash=dataset.file_hash
    )


@router.get("/{user_id}", response_model=List[DatasetResponse])
async def get_user_datasets(
    user_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000)
):
    """Get all datasets for a user with pagination"""
    datasets = await metadata_service.get_datasets_by_user(user_id, skip, limit)
    
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
    
    return DatasetResponse(
        dataset_id=updated_dataset.dataset_id,
        user_id=updated_dataset.user_id,
        name=updated_dataset.name,
        description=updated_dataset.description,
        version=updated_dataset.version,
        file_type=updated_dataset.file_type,
        file_size=updated_dataset.file_size,
        original_filename=updated_dataset.original_filename,
        files=updated_dataset.files,
        is_folder=updated_dataset.is_folder,
        columns=updated_dataset.columns,
        row_count=updated_dataset.row_count,
        data_types=updated_dataset.data_types,
        tags=updated_dataset.tags,
        custom_metadata=updated_dataset.custom_metadata,
        created_at=updated_dataset.created_at,
        updated_at=updated_dataset.updated_at,
        file_hash=updated_dataset.file_hash
    )


@router.delete("/{user_id}/{dataset_id}")
async def delete_dataset(user_id: str, dataset_id: str):
    """Delete all versions of a dataset and their files"""
    # Get all versions of the dataset first
    datasets = await metadata_service.get_dataset_versions(dataset_id, user_id)
    if not datasets:
        raise HTTPException(status_code=404, detail="Dataset not found")
    
    # Delete all files from MinIO
    files_deleted = 0
    files_failed = 0
    for dataset in datasets:
        try:
            if dataset.is_folder:
                # Delete all files in folder
                deleted_count = await file_service.delete_folder_files(dataset.file_path)
                files_deleted += deleted_count
                logger.info(f"Deleted {deleted_count} files from folder: {dataset.file_path}")
            else:
                # Delete single file
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
    - For folders without filename: downloads all files as ZIP (optionally only train/test/drift if split= is set)
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
            file_data = await file_service.download_file(target_file.file_path)
            return StreamingResponse(
                BytesIO(file_data),
                media_type='application/octet-stream',
                headers={"Content-Disposition": f"attachment; filename={filename}"}
            )
        subfolder = None
        if split and split in ("train", "test", "drift") and (dataset.custom_metadata or {}).get("split"):
            subfolder = split
        zip_data = await file_service.download_folder_as_zip(dataset.file_path, subfolder_prefix=subfolder)
        zip_name = f"{dataset_id}_{dataset.version}" + (f"_{split}" if subfolder else "") + ".zip"
        return StreamingResponse(
            BytesIO(zip_data),
            media_type='application/zip',
            headers={"Content-Disposition": f"attachment; filename={zip_name}"}
        )
    file_data = await file_service.download_file(dataset.file_path)
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
            file_data = await file_service.download_file(target_file.file_path)
            return StreamingResponse(
                BytesIO(file_data),
                media_type='application/octet-stream',
                headers={"Content-Disposition": f"attachment; filename={filename}"}
            )
        subfolder = None
        if split and split in ("train", "test", "drift") and (dataset.custom_metadata or {}).get("split"):
            subfolder = split
        zip_data = await file_service.download_folder_as_zip(dataset.file_path, subfolder_prefix=subfolder)
        zip_name = f"{dataset_id}_{version}" + (f"_{split}" if subfolder else "") + ".zip"
        return StreamingResponse(
            BytesIO(zip_data),
            media_type='application/zip',
            headers={"Content-Disposition": f"attachment; filename={zip_name}"}
        )
    file_data = await file_service.download_file(dataset.file_path)
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


@router.get("/{user_id}/{dataset_id}/version/{version}", response_model=DatasetResponse)
async def get_dataset_by_version(user_id: str, dataset_id: str, version: str):
    """Get a specific version of a dataset"""
    dataset = await metadata_service.get_dataset_by_version(dataset_id, user_id, version)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
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
        created_at=dataset.created_at,
        updated_at=dataset.updated_at,
        file_hash=dataset.file_hash
    )


@router.delete("/{user_id}/{dataset_id}/version/{version}")
async def delete_dataset_by_version(user_id: str, dataset_id: str, version: str):
    """Delete a specific version of a dataset and its file(s)"""
    dataset = await metadata_service.get_dataset_by_version(dataset_id, user_id, version)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    
    # Handle folder vs single file deletion
    files_deleted = 0
    if dataset.is_folder:
        files_deleted = await file_service.delete_folder_files(dataset.file_path)
        logger.info(f"Deleted {files_deleted} files from folder: {dataset.file_path}")
    else:
        file_deleted = await file_service.delete_file(dataset.file_path)
        files_deleted = 1 if file_deleted else 0
    
    metadata_deleted = await metadata_service.delete_dataset_by_version(dataset_id, user_id, version)
    if not metadata_deleted:
        raise HTTPException(status_code=500, detail="Failed to delete dataset metadata")
    
    return {
        "message": "Dataset deleted successfully",
        "files_deleted": files_deleted,
        "metadata_deleted": metadata_deleted
    }

