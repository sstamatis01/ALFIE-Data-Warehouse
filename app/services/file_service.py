import hashlib
import os
import random
import pandas as pd
from io import BytesIO
from typing import Optional, Dict, Any, List, Tuple
from minio.error import S3Error
from fastapi import UploadFile, HTTPException
from ..core.minio_client import minio_client
from ..models.dataset import DatasetMetadata, DatasetFile
import logging
import tempfile
import zipfile

logger = logging.getLogger(__name__)

# Split ratios: train 70%, test 15%, drift 15%
SPLIT_TRAIN_RATIO = 0.70
SPLIT_TEST_RATIO = 0.15
SPLIT_DRIFT_RATIO = 0.15
SPLIT_SUBFOLDERS = ("train", "test", "drift")


class FileService:
    def __init__(self):
        self.client = None
        self.bucket_name = minio_client.bucket_name

    async def initialize(self):
        """Initialize the file service"""
        await minio_client.connect()
        self.client = minio_client.get_client()

    def generate_file_path(self, user_id: str, dataset_id: str, version: str, filename: str) -> str:
        """Generate organized file path with user separation and versioning"""
        # Format: datasets/user1/dataset_name/v1/filename.csv
        return f"datasets/{user_id}/{dataset_id}/{version}/{filename}"

    def generate_file_path_with_subfolder(
        self, user_id: str, dataset_id: str, version: str, subfolder: str, filename: str
    ) -> str:
        """Generate path with train/test/drift subfolder. Format: datasets/user1/dataset_id/v1/train/filename.csv"""
        return f"datasets/{user_id}/{dataset_id}/{version}/{subfolder}/{filename}"

    @staticmethod
    def _should_split_dataset(num_samples: int, num_features: int) -> bool:
        """True if dataset is large enough to split: num_samples > (num_features + 1) * 10"""
        return num_samples > (num_features + 1) * 10

    # Extensions treated as images vs annotation files for folder upload validation
    _IMAGE_EXTENSIONS = frozenset({"jpg", "jpeg", "png", "gif", "bmp", "webp", "tiff", "tif"})
    _ANNOTATION_EXTENSIONS = frozenset({"csv", "json", "xml", "txt"})

    @staticmethod
    def _check_image_folder_has_annotations(
        collected: List[Tuple[str, str, bytes, int, str]],
    ) -> Tuple[bool, bool]:
        """
        Check if the folder looks like an image dataset and if it has an annotation file.
        collected: list of (relative_path, file_basename, file_data, file_size, file_type).

        Returns:
            (is_image_folder, has_annotation_file)
        """
        if not collected:
            return False, False
        image_count = 0
        has_annotation = False
        for _rel, _name, _data, _size, ext in collected:
            ext_lower = (ext or "").lower()
            if ext_lower in FileService._IMAGE_EXTENSIONS:
                image_count += 1
            if ext_lower in FileService._ANNOTATION_EXTENSIONS:
                has_annotation = True
        # Consider it an image folder if at least one file is an image
        is_image_folder = image_count > 0
        return is_image_folder, has_annotation

    def calculate_file_hash(self, file_data: bytes) -> str:
        """Calculate MD5 hash of file data"""
        return hashlib.md5(file_data).hexdigest()

    async def upload_file(
        self,
        file: UploadFile,
        user_id: str,
        dataset_id: str,
        version: str = "v1",
        version_split: Optional[str] = None,
    ) -> Tuple[str, Dict[str, Any], Optional[Dict[str, Any]]]:
        """
        Upload file to MinIO. Original is always stored under `version` (v1).
        If the dataset is large enough (num_samples > (num_features + 1) * 10) and
        `version_split` is set, a train/test/drift split is also stored under `version_split` (v2).

        Returns:
            Tuple of (v1_file_path, v1_metadata, v2_metadata or None).
            v2_metadata has 'file_path' (base), 'files', 'file_size', 'is_folder'=True, custom_metadata.split.
        """
        try:
            file_data = await file.read()
            file_size = len(file_data)
            file_extension = self._get_file_extension(file.filename or "")
            metadata = await self._extract_file_metadata(file_data, file.filename or "", file.content_type)

            row_count = metadata.get("row_count")
            columns = metadata.get("columns") or []
            num_features = len(columns)
            do_split = (
                file_extension in ("csv", "xlsx", "xls")
                and row_count is not None
                and num_features > 0
                and self._should_split_dataset(row_count, num_features)
            )

            # Always upload original to v1
            file_path = self.generate_file_path(user_id, dataset_id, version, file.filename or "data")
            file_hash = self.calculate_file_hash(file_data)
            self.client.put_object(
                bucket_name=self.bucket_name,
                object_name=file_path,
                data=BytesIO(file_data),
                length=file_size,
                content_type=file.content_type or "application/octet-stream",
            )
            logger.info(f"Original file uploaded to {file_path}")
            v1_metadata = dict(metadata)
            v1_metadata.update({
                "file_size": file_size,
                "file_hash": file_hash,
                "file_type": file_extension,
                "original_filename": file.filename,
            })
            v1_metadata["file_path"] = file_path

            if do_split and version_split:
                v2_metadata = await self._upload_single_file_with_split(
                    file_data=file_data,
                    filename=file.filename or "data",
                    content_type=file.content_type,
                    user_id=user_id,
                    dataset_id=dataset_id,
                    version=version_split,
                    metadata=metadata,
                    file_extension=file_extension,
                )
                return file_path, v1_metadata, v2_metadata
            if do_split and not version_split:
                logger.info(f"Dataset large enough to split but version_split not set; only v1 stored")
            elif row_count is not None and num_features > 0 and not do_split:
                logger.info(f"Dataset too small to split (samples={row_count}, features={num_features}); only v1 stored")
            return file_path, v1_metadata, None

        except S3Error as e:
            logger.error(f"MinIO error during file upload: {e}")
            raise HTTPException(status_code=500, detail=f"File upload failed: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error during file upload: {e}")
            raise HTTPException(status_code=500, detail=f"File upload failed: {str(e)}")

    async def _upload_single_file_with_split(
        self,
        file_data: bytes,
        filename: str,
        content_type: Optional[str],
        user_id: str,
        dataset_id: str,
        version: str,
        metadata: Dict[str, Any],
        file_extension: str,
    ) -> Dict[str, Any]:
        """Split a single tabular file into train/test/drift and upload to MinIO under `version` (v2). Returns metadata dict for the split."""
        if file_extension == "csv":
            df = pd.read_csv(BytesIO(file_data))
        else:
            df = pd.read_excel(BytesIO(file_data))

        n = len(df)
        indices = list(range(n))
        random.shuffle(indices)
        n_train = int(n * SPLIT_TRAIN_RATIO)
        n_test = int(n * SPLIT_TEST_RATIO)
        n_drift = n - n_train - n_test
        train_idx = indices[:n_train]
        test_idx = indices[n_train : n_train + n_test]
        drift_idx = indices[n_train + n_test :]

        base_path = f"datasets/{user_id}/{dataset_id}/{version}/"
        split_dfs = {"train": df.iloc[train_idx], "test": df.iloc[test_idx], "drift": df.iloc[drift_idx]}
        dataset_files: List[DatasetFile] = []
        total_size = 0

        for subfolder in SPLIT_SUBFOLDERS:
            part = split_dfs[subfolder]
            buf = BytesIO()
            if file_extension == "csv":
                part.to_csv(buf, index=False)
            else:
                part.to_excel(buf, index=False)
            buf.seek(0)
            data = buf.getvalue()
            size = len(data)
            total_size += size
            minio_path = self.generate_file_path_with_subfolder(
                user_id, dataset_id, version, subfolder, filename
            )
            self.client.put_object(
                bucket_name=self.bucket_name,
                object_name=minio_path,
                data=BytesIO(data),
                length=size,
                content_type=content_type or "application/octet-stream",
            )
            file_hash = self.calculate_file_hash(data)
            dataset_files.append(
                DatasetFile(
                    filename=filename,
                    file_path=minio_path,
                    file_size=size,
                    file_type=file_extension,
                    file_hash=file_hash,
                    content_type=content_type or "application/octet-stream",
                )
            )
            logger.info(f"Uploaded split: {minio_path}")

        metadata["file_path"] = base_path
        metadata["file_size"] = total_size
        metadata["file_hash"] = None
        metadata["file_type"] = file_extension
        metadata["original_filename"] = filename
        metadata["files"] = dataset_files
        metadata["is_folder"] = True
        metadata["custom_metadata"] = metadata.get("custom_metadata") or {}
        metadata["custom_metadata"]["split"] = {
            "train": len(train_idx),
            "test": len(test_idx),
            "drift": len(drift_idx),
        }
        logger.info(f"Dataset split into train={len(train_idx)}, test={len(test_idx)}, drift={len(drift_idx)}")
        return metadata

    async def download_file(self, file_path: str) -> bytes:
        """Download file from MinIO"""
        try:
            response = self.client.get_object(self.bucket_name, file_path)
            return response.read()
        except S3Error as e:
            logger.error(f"MinIO error during file download: {e}")
            raise HTTPException(status_code=404, detail="File not found")
        except Exception as e:
            logger.error(f"Unexpected error during file download: {e}")
            raise HTTPException(status_code=500, detail="File download failed")

    async def delete_file(self, file_path: str) -> bool:
        """Delete file from MinIO"""
        try:
            self.client.remove_object(self.bucket_name, file_path)
            logger.info(f"File deleted successfully: {file_path}")
            return True
        except S3Error as e:
            logger.error(f"MinIO error during file deletion: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during file deletion: {e}")
            return False

    async def file_exists(self, file_path: str) -> bool:
        """Check if file exists in MinIO"""
        try:
            self.client.stat_object(self.bucket_name, file_path)
            return True
        except S3Error:
            return False
        except Exception as e:
            logger.error(f"Error checking file existence: {e}")
            return False

    async def list_user_files(self, user_id: str, dataset_id: Optional[str] = None) -> List[str]:
        """List all files for a user, optionally filtered by dataset"""
        try:
            prefix = f"datasets/{user_id}/"
            if dataset_id:
                prefix += f"{dataset_id}/"
            
            objects = self.client.list_objects(self.bucket_name, prefix=prefix, recursive=True)
            return [obj.object_name for obj in objects]
        except S3Error as e:
            logger.error(f"MinIO error listing files: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error listing files: {e}")
            return []

    def _get_file_extension(self, filename: str) -> str:
        """Get file extension from filename"""
        return os.path.splitext(filename)[1].lower().lstrip('.')

    async def _extract_file_metadata(self, file_data: bytes, filename: str, content_type: Optional[str]) -> Dict[str, Any]:
        """Extract metadata from file content based on file type"""
        metadata = {}
        file_extension = self._get_file_extension(filename)
        
        try:
            if file_extension in ['csv', 'xlsx', 'xls']:
                # For structured data files
                if file_extension == 'csv':
                    df = pd.read_csv(BytesIO(file_data))
                else:
                    df = pd.read_excel(BytesIO(file_data))
                
                metadata.update({
                    'columns': df.columns.tolist(),
                    'row_count': len(df),
                    'data_types': df.dtypes.astype(str).to_dict()
                })
                
            elif file_extension in ['json']:
                # For JSON files, we could parse and extract schema
                pass
                
            elif file_extension in ['jpg', 'jpeg', 'png', 'gif', 'bmp']:
                # For image files, we could extract dimensions, etc.
                pass
                
            elif file_extension in ['mp4', 'avi', 'mov', 'mkv']:
                # For video files, we could extract duration, resolution, etc.
                pass
                
            elif file_extension in ['mp3', 'wav', 'flac']:
                # For audio files, we could extract duration, bitrate, etc.
                pass
                
        except Exception as e:
            logger.warning(f"Failed to extract metadata from {filename}: {e}")
            
        return metadata
    
    async def upload_dataset_folder(
        self,
        zip_file: UploadFile,
        user_id: str,
        dataset_id: str,
        version: str = "v1",
        version_split: Optional[str] = None,
        preserve_structure: bool = True
    ) -> Tuple[Tuple[List[DatasetFile], int, Optional[Dict[str, int]]], Optional[Tuple[List[DatasetFile], int, Dict[str, int]]]]:
        """
        Upload a folder of dataset files (as zip). Original is always stored under `version` (v1).
        If the number of files is large enough and `version_split` is set, a train/test/drift split
        is also stored under `version_split` (v2).

        Returns:
            ((v1_files, v1_size, None), (v2_files, v2_size, split_counts) or None).
        """
        try:
            zip_data = await zip_file.read()
            collected: List[Tuple[str, str, bytes, int, str]] = []  # (relative_path, file_basename, data, size, file_type)

            with tempfile.TemporaryDirectory() as temp_dir:
                zip_path = os.path.join(temp_dir, "dataset_files.zip")
                with open(zip_path, "wb") as f:
                    f.write(zip_data)
                with zipfile.ZipFile(zip_path, "r") as zip_ref:
                    zip_ref.extractall(temp_dir)

                for root, dirs, files in os.walk(temp_dir):
                    for file in files:
                        if file == "dataset_files.zip" or file.startswith(".") or "__MACOSX" in root:
                            continue
                        file_path = os.path.join(root, file)
                        relative_path = os.path.relpath(file_path, temp_dir)
                        with open(file_path, "rb") as f:
                            file_data = f.read()
                        file_size = len(file_data)
                        collected.append((
                            relative_path,
                            file,
                            file_data,
                            file_size,
                            self._get_file_extension(file),
                        ))

            # Require annotation file when folder contains images
            is_image_folder, has_annotation = self._check_image_folder_has_annotations(collected)
            if is_image_folder and not has_annotation:
                raise HTTPException(
                    status_code=400,
                    detail="Annotations missing: image datasets must be accompanied by an annotation file (CSV, JSON, or XML).",
                )

            # Detect if the uploaded ZIP already contains a train/test/drift split structure.
            # This commonly happens for bias-mitigated datasets that are uploaded as:
            #   train/data.csv, test/data.csv, drift/data.csv
            # In that case we should preserve the split and record split_counts on THIS version,
            # not create an extra "version_split" with a random reassignment.
            split_counts_existing: Optional[Dict[str, int]] = None
            split_prefixes = ("train" + os.sep, "test" + os.sep, "drift" + os.sep)
            existing_counts = {"train": 0, "test": 0, "drift": 0}
            for relative_path, _file, _data, _size, _ftype in collected:
                # Normalize to OS separator for the startswith check (paths come from os.walk)
                rp = relative_path
                if rp.startswith(split_prefixes[0]):
                    existing_counts["train"] += 1
                elif rp.startswith(split_prefixes[1]):
                    existing_counts["test"] += 1
                elif rp.startswith(split_prefixes[2]):
                    existing_counts["drift"] += 1
            if all(existing_counts[k] > 0 for k in ("train", "test", "drift")):
                split_counts_existing = existing_counts
                logger.info(
                    "Detected pre-split folder structure in uploaded ZIP: %s. Will preserve split on version=%s and skip auto-splitting.",
                    split_counts_existing,
                    version,
                )

            num_samples = len(collected)
            num_features = 1
            do_split = self._should_split_dataset(num_samples, num_features)
            if split_counts_existing is not None:
                do_split = False

            # Always upload original to v1 (no split)
            dataset_files_v1 = []
            total_size_v1 = 0
            for relative_path, file, file_data, file_size, file_type in collected:
                file_hash = self.calculate_file_hash(file_data)
                if preserve_structure:
                    minio_path = self.generate_file_path(user_id, dataset_id, version, relative_path)
                else:
                    minio_path = self.generate_file_path(user_id, dataset_id, version, file)
                self.client.put_object(
                    bucket_name=self.bucket_name,
                    object_name=minio_path,
                    data=BytesIO(file_data),
                    length=file_size,
                    content_type="application/octet-stream",
                )
                dataset_files_v1.append(
                    DatasetFile(
                        filename=file,
                        file_path=minio_path,
                        file_size=file_size,
                        file_type=file_type,
                        file_hash=file_hash,
                        content_type="application/octet-stream",
                    )
                )
                total_size_v1 += file_size
                logger.info(f"Uploaded original file: {minio_path}")

            logger.info(f"Uploaded {len(dataset_files_v1)} original files to v1, total size: {total_size_v1} bytes")

            if do_split and version_split:
                v2_files, v2_size, split_counts = await self._upload_folder_with_split(
                    collected, user_id, dataset_id, version_split, preserve_structure
                )
                return ((dataset_files_v1, total_size_v1, None), (v2_files, v2_size, split_counts))

            if do_split and not version_split:
                logger.info("Folder large enough to split but version_split not set; only v1 stored")
            return ((dataset_files_v1, total_size_v1, split_counts_existing), None)

        except zipfile.BadZipFile:
            logger.error("Invalid zip file")
            raise HTTPException(status_code=400, detail="Invalid zip file")
        except HTTPException:
            raise
        except S3Error as e:
            logger.error(f"MinIO error during folder upload: {e}")
            raise HTTPException(status_code=500, detail=f"Folder upload failed: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error during folder upload: {e}")
            raise HTTPException(status_code=500, detail=f"Folder upload failed: {str(e)}")

    async def _upload_folder_with_split(
        self,
        collected: List[Tuple[str, str, bytes, int, str]],
        user_id: str,
        dataset_id: str,
        version: str,
        preserve_structure: bool,
    ) -> Tuple[List[DatasetFile], int, Dict[str, int]]:
        """Assign each file to train/test/drift and upload under subfolders."""
        indices = list(range(len(collected)))
        random.shuffle(indices)
        n = len(indices)
        n_train = int(n * SPLIT_TRAIN_RATIO)
        n_test = int(n * SPLIT_TEST_RATIO)
        n_drift = n - n_train - n_test
        train_idx = set(indices[:n_train])
        test_idx = set(indices[n_train : n_train + n_test])
        drift_idx = set(indices[n_train + n_test :])

        split_counts = {"train": len(train_idx), "test": len(test_idx), "drift": len(drift_idx)}
        dataset_files: List[DatasetFile] = []
        total_size = 0

        for i, (relative_path, file, file_data, file_size, file_type) in enumerate(collected):
            if i in train_idx:
                subfolder = "train"
            elif i in test_idx:
                subfolder = "test"
            else:
                subfolder = "drift"
            path_in_split = f"{subfolder}/{relative_path}" if preserve_structure else f"{subfolder}/{file}"
            minio_path = f"datasets/{user_id}/{dataset_id}/{version}/{path_in_split}"
            self.client.put_object(
                bucket_name=self.bucket_name,
                object_name=minio_path,
                data=BytesIO(file_data),
                length=file_size,
                content_type="application/octet-stream",
            )
            file_hash = self.calculate_file_hash(file_data)
            dataset_files.append(
                DatasetFile(
                    filename=file,
                    file_path=minio_path,
                    file_size=file_size,
                    file_type=file_type,
                    file_hash=file_hash,
                    content_type="application/octet-stream",
                )
            )
            total_size += file_size
            logger.info(f"Uploaded split file: {minio_path}")

        logger.info(f"Folder split into train={split_counts['train']}, test={split_counts['test']}, drift={split_counts['drift']}")
        return dataset_files, total_size, split_counts
    
    async def delete_folder_files(self, folder_path: str) -> int:
        """
        Delete all files in a folder from MinIO
        
        Returns:
            Number of files deleted
        """
        try:
            objects = self.client.list_objects(self.bucket_name, prefix=folder_path, recursive=True)
            deleted_count = 0
            
            for obj in objects:
                try:
                    self.client.remove_object(self.bucket_name, obj.object_name)
                    logger.info(f"Deleted file: {obj.object_name}")
                    deleted_count += 1
                except Exception as e:
                    logger.warning(f"Failed to delete {obj.object_name}: {e}")
            
            return deleted_count
            
        except S3Error as e:
            logger.error(f"MinIO error during folder deletion: {e}")
            return 0
        except Exception as e:
            logger.error(f"Unexpected error during folder deletion: {e}")
            return 0
    
    async def download_folder_as_zip(
        self, folder_path: str, subfolder_prefix: Optional[str] = None
    ) -> bytes:
        """
        Download all files in a folder as a zip archive.

        Args:
            folder_path: Path to folder in MinIO (e.g., "datasets/user1/dataset1/v1/")
            subfolder_prefix: If set (e.g. "train", "test", "drift"), only include objects
                under folder_path + subfolder_prefix + "/". Use for split datasets.
                Zip entries are relative to that subfolder (e.g. "file.csv" not "drift/file.csv").

        Returns:
            ZIP archive as bytes
        """
        try:
            prefix = folder_path
            if subfolder_prefix:
                prefix = f"{folder_path.rstrip('/')}/{subfolder_prefix}/"
            objects = self.client.list_objects(self.bucket_name, prefix=prefix, recursive=True)

            zip_buffer = BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                has_files = False
                for obj in objects:
                    file_data = self.client.get_object(self.bucket_name, obj.object_name)
                    # Entry name: strip prefix so we get relative path (e.g. "file.csv" or "subdir/file.csv")
                    zip_path = obj.object_name.replace(prefix, "")
                    if zip_path:
                        zip_file.writestr(zip_path, file_data.read())
                        has_files = True
                if not has_files:
                    raise HTTPException(status_code=404, detail="No files found in folder")
            zip_buffer.seek(0)
            return zip_buffer.getvalue()
        except S3Error as e:
            logger.error(f"MinIO error during folder zip download: {e}")
            raise HTTPException(status_code=404, detail="Folder not found")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Unexpected error during folder zip download: {e}")
            raise HTTPException(status_code=500, detail="Folder zip download failed")


# Global file service instance
file_service = FileService()
