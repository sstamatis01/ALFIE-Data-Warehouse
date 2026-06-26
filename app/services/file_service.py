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
import json
import anyio

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

    async def copy_prefix(
        self,
        *,
        src_prefix: str,
        dst_prefix: str,
    ) -> int:
        """
        Copy all objects under `src_prefix` to `dst_prefix` within the same bucket.
        Returns number of objects copied.

        Note: Implemented as a stream read + put (portable across S3 backends).
        """
        if not self.client:
            await self.initialize()

        # Normalize prefixes to ensure trailing slash semantics.
        src_prefix_n = src_prefix if src_prefix.endswith("/") else (src_prefix + "/")
        dst_prefix_n = dst_prefix if dst_prefix.endswith("/") else (dst_prefix + "/")

        def _copy_sync() -> int:
            copied = 0
            objects = self.client.list_objects(
                self.bucket_name, prefix=src_prefix_n, recursive=True
            )
            for obj in objects:
                src_name = obj.object_name
                rel = src_name[len(src_prefix_n) :]
                dst_name = dst_prefix_n + rel

                stat = self.client.stat_object(self.bucket_name, src_name)
                resp = None
                try:
                    resp = self.client.get_object(self.bucket_name, src_name)
                    self.client.put_object(
                        bucket_name=self.bucket_name,
                        object_name=dst_name,
                        data=resp,
                        length=stat.size,
                        content_type=getattr(stat, "content_type", None)
                        or "application/octet-stream",
                    )
                    copied += 1
                finally:
                    try:
                        if resp is not None:
                            resp.close()
                            resp.release_conn()
                    except Exception:
                        pass
            return copied

        return await anyio.to_thread.run_sync(_copy_sync)

    @staticmethod
    def _should_split_dataset(num_samples: int, num_features: int) -> bool:
        """True if dataset is large enough to split: num_samples > (num_features + 1) * 10"""
        return num_samples > (num_features + 1) * 10

    # Extensions treated as images vs annotation files for folder upload validation
    _IMAGE_EXTENSIONS = frozenset({"jpg", "jpeg", "png", "gif", "bmp", "webp", "tiff", "tif"})
    # AutoML Vision contract: annotations must be machine-readable.
    # We intentionally do NOT accept "txt" as it could be a readme and not a label mapping.
    _ANNOTATION_EXTENSIONS = frozenset({"csv", "json"})

    # Common alternative column names we accept for vision annotations and normalize to (filename,label)
    _VISION_FILENAME_COLUMNS = ("filename", "image_file_path", "file_path", "path", "filepath", "image_path", "image")
    _VISION_LABEL_COLUMNS = ("label", "class", "category", "target", "y")

    @staticmethod
    def _pick_annotation_column(cols_l: set[str], candidates: tuple[str, ...], preferred: str) -> str | None:
        """Pick an annotation column name (lowercased) from candidates, preferring `preferred` first."""
        pref = (preferred or "").strip().lower()
        if pref and pref in cols_l:
            return pref
        for c in candidates:
            c_l = (c or "").strip().lower()
            if c_l and c_l in cols_l:
                return c_l
        return None

    @staticmethod
    def _calculate_md5_from_path(path: str, *, chunk_size: int = 1024 * 1024) -> str:
        """Calculate MD5 hash without loading the entire file into memory."""
        h = hashlib.md5()
        with open(path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()

    async def _put_object_from_path(
        self,
        *,
        object_name: str,
        file_path: str,
        file_size: int,
        content_type: str = "application/octet-stream",
    ) -> None:
        """
        Upload a local file to MinIO without blocking the event loop.
        MinIO client is sync; run it in a worker thread.
        """

        def _upload() -> None:
            with open(file_path, "rb") as f:
                self.client.put_object(
                    bucket_name=self.bucket_name,
                    object_name=object_name,
                    data=f,
                    length=file_size,
                    content_type=content_type,
                )

        await anyio.to_thread.run_sync(_upload)

    async def put_object_from_upload_file(
        self,
        *,
        object_name: str,
        upload: UploadFile,
        content_type: str = "application/zip",
        part_size: int = 10 * 1024 * 1024,
    ) -> None:
        """
        Stream an UploadFile into MinIO without loading it into memory.
        Uses multipart upload (unknown length) and runs in a worker thread.
        """

        def _upload() -> None:
            try:
                upload.file.seek(0)
            except Exception:
                pass
            self.client.put_object(
                bucket_name=self.bucket_name,
                object_name=object_name,
                data=upload.file,
                length=-1,
                part_size=part_size,
                content_type=content_type,
            )

        await anyio.to_thread.run_sync(_upload)

    async def download_object_to_path(self, *, object_name: str, dest_path: str, chunk_size: int = 1024 * 1024) -> None:
        """Download a MinIO object to a local file path without blocking the event loop."""

        def _download() -> None:
            resp = self.client.get_object(self.bucket_name, object_name)
            try:
                os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
                with open(dest_path, "wb") as f:
                    for chunk in resp.stream(chunk_size):
                        if chunk:
                            f.write(chunk)
            finally:
                try:
                    resp.close()
                except Exception:
                    pass
                try:
                    resp.release_conn()
                except Exception:
                    pass

        await anyio.to_thread.run_sync(_download)

    @staticmethod
    def _check_image_folder_has_annotations(
        collected: List[Tuple[str, str, str, int, str]],
    ) -> Tuple[bool, bool]:
        """
        Check if the folder looks like an image dataset and if it has an annotation file.
        collected: list of (relative_path, file_basename, absolute_path, file_size, file_type).

        Returns:
            (is_image_folder, has_annotation_file)
        """
        if not collected:
            return False, False
        image_count = 0
        has_annotation = False
        for _rel, _name, _abs, _size, ext in collected:
            ext_lower = (ext or "").lower()
            if ext_lower in FileService._IMAGE_EXTENSIONS:
                image_count += 1
            if ext_lower in FileService._ANNOTATION_EXTENSIONS:
                has_annotation = True
        # Consider it an image folder if at least one file is an image
        is_image_folder = image_count > 0
        return is_image_folder, has_annotation

    @staticmethod
    def _normalize_relpath(p: str) -> str:
        """Normalize to forward-slash relative paths for comparisons."""
        return (p or "").replace("\\", "/").lstrip("./")

    @staticmethod
    def _validate_automl_vision_annotations(
        collected: List[Tuple[str, str, str, int, str]],
        *,
        filename_column: str = "filename",
        label_column: str = "label",
    ) -> None:
        """
        Enforce the AutoML Vision dataset contract for image folder uploads.

        Contract enforced at dataset-upload time (so training can't proceed with bad inputs):
        - ZIP contains >=1 image file
        - ZIP contains an annotation file in CSV or JSON
        - Annotation rows reference image paths that exist in the ZIP
        - Annotation file contains at least the columns: filename_column + label_column
          (defaults to 'filename' and 'label' as used by orchestrator/consumer)
        """
        if not collected:
            return

        images: set[str] = set()
        annotation_candidates: list[tuple[str, str, str]] = []  # (relpath, ext, abs_path)

        for rel, _name, abs_path, _size, ext in collected:
            ext_lower = (ext or "").lower()
            rel_norm = FileService._normalize_relpath(rel)
            if ext_lower in FileService._IMAGE_EXTENSIONS:
                images.add(rel_norm)
            if ext_lower in FileService._ANNOTATION_EXTENSIONS:
                annotation_candidates.append((rel_norm, ext_lower, abs_path))

        if not images:
            return  # not a vision dataset

        # Prefer explicit "annotations.*" files if present.
        preferred = [c for c in annotation_candidates if os.path.basename(c[0]).lower().startswith("annotations.")]
        candidates = preferred or annotation_candidates

        if not candidates:
            raise HTTPException(
                status_code=400,
                detail="Missing annotations file. Please provide an annotations CSV or JSON (with filename+label) and re-upload your dataset.",
            )

        fn_pref = (filename_column or "filename").strip().lower()
        lbl_pref = (label_column or "label").strip().lower()

        def _coerce_filename_value(v) -> str | None:
            if v is None:
                return None
            s = str(v).strip()
            if not s:
                return None
            return FileService._normalize_relpath(s)

        # Try candidates until we find one that validates.
        last_error: str | None = None
        for rel_norm, ext_lower, abs_path in candidates:
            try:
                with open(abs_path, "rb") as f:
                    data = f.read()
                if ext_lower == "csv":
                    try:
                        df = pd.read_csv(BytesIO(data))
                    except Exception as e:
                        raise ValueError(f"Could not parse CSV: {e}") from e

                    cols = {str(c).strip().lower(): c for c in df.columns}
                    cols_l = set(cols.keys())
                    fn_col = FileService._pick_annotation_column(cols_l, FileService._VISION_FILENAME_COLUMNS, fn_pref)
                    lbl_col = FileService._pick_annotation_column(cols_l, FileService._VISION_LABEL_COLUMNS, lbl_pref)
                    if not fn_col or not lbl_col:
                        raise ValueError(
                            f"CSV must contain a filename column (e.g. '{filename_column}' or 'image_file_path') and a label column (e.g. '{label_column}'). Found: {list(df.columns)[:30]}"
                        )
                    if df.empty:
                        raise ValueError("CSV has no rows")

                    filenames = df[cols[fn_col]].apply(_coerce_filename_value).dropna()
                    if filenames.empty:
                        raise ValueError("CSV has no valid filenames")

                    # Require that at least one annotation row references an existing image file.
                    # We allow both full relative paths and basenames as long as they match uniquely.
                    image_basenames = {}
                    for img in images:
                        bn = os.path.basename(img).lower()
                        image_basenames.setdefault(bn, 0)
                        image_basenames[bn] += 1

                    matched = 0
                    for fn in filenames.head(5000):  # cap work on huge annotation files
                        if fn in images:
                            matched += 1
                            continue
                        bn = os.path.basename(fn).lower()
                        if image_basenames.get(bn, 0) == 1:
                            matched += 1
                    if matched == 0:
                        raise ValueError(
                            "CSV does not reference any images found in the ZIP (check paths in the filename column)."
                        )

                    return  # valid

                if ext_lower == "json":
                    try:
                        obj = json.loads(data.decode("utf-8", errors="strict"))
                    except Exception as e:
                        raise ValueError(f"Could not parse JSON: {e}") from e

                    # Support a simple list-of-objects format: [{"filename": "...", "label": "..."}]
                    if isinstance(obj, dict) and "annotations" in obj:
                        obj = obj["annotations"]
                    if not isinstance(obj, list) or not obj:
                        raise ValueError("JSON must be a non-empty list (or a dict with key 'annotations' as a list)")

                    first = obj[0]
                    if not isinstance(first, dict):
                        raise ValueError("JSON list items must be objects")

                    # Case-insensitive key lookup
                    def _get_ci(d: dict, key: str):
                        for k, v in d.items():
                            if str(k).strip().lower() == key:
                                return v
                        return None

                    keys_l = {str(k).strip().lower() for k in first.keys()}
                    fn_col = FileService._pick_annotation_column(keys_l, FileService._VISION_FILENAME_COLUMNS, fn_pref)
                    lbl_col = FileService._pick_annotation_column(keys_l, FileService._VISION_LABEL_COLUMNS, lbl_pref)
                    if not fn_col or not lbl_col:
                        raise ValueError(
                            f"JSON items must contain a filename key (e.g. '{filename_column}' or 'image_file_path') and a label key (e.g. '{label_column}'). Found keys: {list(first.keys())[:30]}"
                        )

                    image_basenames = {}
                    for img in images:
                        bn = os.path.basename(img).lower()
                        image_basenames.setdefault(bn, 0)
                        image_basenames[bn] += 1

                    matched = 0
                    checked = 0
                    for item in obj[:5000]:
                        if not isinstance(item, dict):
                            continue
                        checked += 1
                        fn_val = _coerce_filename_value(_get_ci(item, fn_col))
                        lbl_val = _get_ci(item, lbl_col)
                        if fn_val is None or lbl_val is None or str(lbl_val).strip() == "":
                            continue
                        if fn_val in images:
                            matched += 1
                            continue
                        bn = os.path.basename(fn_val).lower()
                        if image_basenames.get(bn, 0) == 1:
                            matched += 1
                    if checked == 0:
                        raise ValueError("JSON contains no object annotations")
                    if matched == 0:
                        raise ValueError(
                            "JSON does not reference any images found in the ZIP (check paths in the filename key)."
                        )
                    return  # valid

                last_error = f"Unsupported annotation extension: {ext_lower}"
            except Exception as e:
                last_error = f"{rel_norm}: {e}"
                continue

        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid or missing annotations for image dataset. "
                f"Expected CSV/JSON with '{filename_column}' and '{label_column}' referencing images in the ZIP. "
                f"Last error: {last_error or 'unknown'}"
            ),
        )

    @staticmethod
    def _select_annotation_candidate(
        collected: List[Tuple[str, str, str, int, str]],
    ) -> tuple[str, str, str] | None:
        """
        Pick the annotation file for a vision dataset.
        Preference order:
        1) basename starts with 'annotations.' (any folder)
        2) first csv/json found
        Returns (relative_path_normalized, ext_lower, abs_path) or None.
        """
        candidates: list[tuple[str, str, str]] = []
        preferred: list[tuple[str, str, str]] = []
        for rel, _name, abs_path, _size, ext in collected:
            ext_lower = (ext or "").lower()
            if ext_lower not in FileService._ANNOTATION_EXTENSIONS:
                continue
            rel_norm = FileService._normalize_relpath(rel)
            item = (rel_norm, ext_lower, abs_path)
            candidates.append(item)
            if os.path.basename(rel_norm).lower().startswith("annotations."):
                preferred.append(item)
        if preferred:
            return preferred[0]
        if candidates:
            return candidates[0]
        return None

    @staticmethod
    def _parse_vision_annotations_to_rows(
        annotation_relpath: str,
        ext_lower: str,
        data: bytes,
        *,
        filename_column: str = "filename",
        label_column: str = "label",
    ) -> list[dict]:
        """
        Parse CSV/JSON annotations into list-of-dicts rows.
        For CSV we preserve all columns; for JSON we preserve keys.
        """
        fn_pref = (filename_column or "filename").strip()
        lbl_pref = (label_column or "label").strip()

        if ext_lower == "csv":
            try:
                df = pd.read_csv(BytesIO(data))
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Invalid annotations CSV '{annotation_relpath}': {e}")
            cols = {str(c).strip().lower(): c for c in df.columns}
            cols_l = set(cols.keys())
            fn_col_l = FileService._pick_annotation_column(cols_l, FileService._VISION_FILENAME_COLUMNS, fn_pref)
            lbl_col_l = FileService._pick_annotation_column(cols_l, FileService._VISION_LABEL_COLUMNS, lbl_pref)
            if not fn_col_l or not lbl_col_l:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Annotations CSV '{annotation_relpath}' must contain a filename column "
                        f"(e.g. '{fn_pref}' or 'image_file_path') and a label column (e.g. '{lbl_pref}')."
                    ),
                )
            fn_col = cols[fn_col_l]
            lbl_col = cols[lbl_col_l]
            rows: list[dict] = []
            for _, r in df.iterrows():
                row = {str(c): r[c] for c in df.columns}
                # Normalize to the orchestrator schema
                row["filename"] = row.get(str(fn_col))
                row["label"] = row.get(str(lbl_col))
                rows.append(row)
            return rows

        if ext_lower == "json":
            try:
                obj = json.loads(data.decode("utf-8", errors="strict"))
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Invalid annotations JSON '{annotation_relpath}': {e}")
            if isinstance(obj, dict) and "annotations" in obj:
                obj = obj["annotations"]
            if not isinstance(obj, list):
                raise HTTPException(status_code=400, detail=f"Annotations JSON '{annotation_relpath}' must be a list (or a dict with key 'annotations').")
            rows = [dict(x) for x in obj if isinstance(x, dict)]
            if not rows:
                raise HTTPException(status_code=400, detail=f"Annotations JSON '{annotation_relpath}' is empty.")
            keys_l = {str(k).strip().lower() for k in rows[0].keys()}
            fn_key_l = FileService._pick_annotation_column(keys_l, FileService._VISION_FILENAME_COLUMNS, fn_pref)
            lbl_key_l = FileService._pick_annotation_column(keys_l, FileService._VISION_LABEL_COLUMNS, lbl_pref)
            if not fn_key_l or not lbl_key_l:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Annotations JSON '{annotation_relpath}' must contain a filename key "
                        f"(e.g. '{fn_pref}' or 'image_file_path') and a label key (e.g. '{lbl_pref}')."
                    ),
                )

            def _find_key(d: dict, key_l: str) -> str | None:
                for k in d.keys():
                    if str(k).strip().lower() == key_l:
                        return str(k)
                return None

            fn_key = _find_key(rows[0], fn_key_l) or fn_pref
            lbl_key = _find_key(rows[0], lbl_key_l) or lbl_pref
            out: list[dict] = []
            for r in rows:
                r2 = dict(r)
                r2["filename"] = r2.get(fn_key)
                r2["label"] = r2.get(lbl_key)
                out.append(r2)
            return out

        raise HTTPException(status_code=400, detail=f"Unsupported annotation file '{annotation_relpath}'")

    @staticmethod
    def _write_split_annotations_bytes(
        *,
        ext_lower: str,
        rows: list[dict],
    ) -> bytes:
        """Serialize filtered annotation rows back to CSV/JSON bytes."""
        if ext_lower == "csv":
            df = pd.DataFrame(rows)
            buf = BytesIO()
            df.to_csv(buf, index=False)
            return buf.getvalue()
        if ext_lower == "json":
            return json.dumps(rows, ensure_ascii=False).encode("utf-8")
        raise ValueError(f"Unsupported annotation extension: {ext_lower}")

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
            collected: List[Tuple[str, str, str, int, str]] = []  # (relative_path, file_basename, abs_path, size, file_type)

            with tempfile.TemporaryDirectory() as temp_dir:
                zip_path = os.path.join(temp_dir, "dataset_files.zip")
                # Stream ZIP to disk to avoid buffering entire archive in memory
                with open(zip_path, "wb") as f:
                    while True:
                        chunk = await zip_file.read(1024 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
                with zipfile.ZipFile(zip_path, "r") as zip_ref:
                    zip_ref.extractall(temp_dir)

                for root, dirs, files in os.walk(temp_dir):
                    for file in files:
                        if file == "dataset_files.zip" or file.startswith(".") or "__MACOSX" in root:
                            continue
                        file_path = os.path.join(root, file)
                        relative_path = os.path.relpath(file_path, temp_dir)
                        file_size = os.path.getsize(file_path)
                        collected.append((
                            relative_path,
                            file,
                            file_path,
                            file_size,
                            self._get_file_extension(file),
                        ))

            # Enforce AutoML Vision contract for image datasets:
            # require machine-readable annotations that reference images in the ZIP.
            is_image_folder, _has_annotation = self._check_image_folder_has_annotations(collected)
            if is_image_folder:
                self._validate_automl_vision_annotations(collected, filename_column="filename", label_column="label")

            # Detect if the uploaded ZIP already contains a train/test/drift split structure.
            # This commonly happens for bias-mitigated datasets that are uploaded as:
            #   train/data.csv, test/data.csv, drift/data.csv
            # In that case we should preserve the split and record split_counts on THIS version,
            # not create an extra "version_split" with a random reassignment.
            split_counts_existing: Optional[Dict[str, int]] = None
            split_prefixes = ("train" + os.sep, "test" + os.sep, "drift" + os.sep)
            existing_counts = {"train": 0, "test": 0, "drift": 0}
            for relative_path, _file, _abs, _size, _ftype in collected:
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
            for relative_path, file, abs_path, file_size, file_type in collected:
                file_hash = self._calculate_md5_from_path(abs_path)
                if preserve_structure:
                    minio_path = self.generate_file_path(user_id, dataset_id, version, relative_path)
                else:
                    minio_path = self.generate_file_path(user_id, dataset_id, version, file)
                await self._put_object_from_path(
                    object_name=minio_path,
                    file_path=abs_path,
                    file_size=file_size,
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
                if is_image_folder:
                    v2_files, v2_size, split_counts = await self._upload_vision_folder_with_split(
                        collected,
                        user_id,
                        dataset_id,
                        version_split,
                        preserve_structure,
                        filename_column="filename",
                        label_column="label",
                    )
                else:
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

    async def upload_dataset_folder_from_zip_path(
        self,
        *,
        zip_path: str,
        user_id: str,
        dataset_id: str,
        version: str = "v1",
        version_split: Optional[str] = None,
        preserve_structure: bool = True,
    ) -> Tuple[Tuple[List[DatasetFile], int, Optional[Dict[str, int]]], Optional[Tuple[List[DatasetFile], int, Dict[str, int]]]]:
        """
        Same as `upload_dataset_folder`, but reads a local ZIP file path.
        Intended for background ingestion jobs (ZIP already staged in object storage).
        """
        try:
            if not zip_path or not os.path.exists(zip_path):
                raise HTTPException(status_code=400, detail="ZIP path not found")

            collected: List[Tuple[str, str, str, int, str]] = []

            with tempfile.TemporaryDirectory() as temp_dir:
                with zipfile.ZipFile(zip_path, "r") as zip_ref:
                    zip_ref.extractall(temp_dir)

                for root, _dirs, files in os.walk(temp_dir):
                    for file in files:
                        if file.startswith(".") or "__MACOSX" in root:
                            continue
                        file_path = os.path.join(root, file)
                        relative_path = os.path.relpath(file_path, temp_dir)
                        file_size = os.path.getsize(file_path)
                        collected.append(
                            (
                                relative_path,
                                file,
                                file_path,
                                file_size,
                                self._get_file_extension(file),
                            )
                        )

                # Enforce AutoML Vision contract for image datasets:
                is_image_folder, _has_annotation = self._check_image_folder_has_annotations(collected)
                if is_image_folder:
                    self._validate_automl_vision_annotations(collected, filename_column="filename", label_column="label")

                # Detect pre-split folder structure
                split_counts_existing: Optional[Dict[str, int]] = None
                split_prefixes = ("train" + os.sep, "test" + os.sep, "drift" + os.sep)
                existing_counts = {"train": 0, "test": 0, "drift": 0}
                for relative_path, _file, _abs, _size, _ftype in collected:
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

                # Upload original to v1
                dataset_files_v1: List[DatasetFile] = []
                total_size_v1 = 0
                for relative_path, file, abs_path, file_size, file_type in collected:
                    file_hash = self._calculate_md5_from_path(abs_path)
                    if preserve_structure:
                        minio_path = self.generate_file_path(user_id, dataset_id, version, relative_path)
                    else:
                        minio_path = self.generate_file_path(user_id, dataset_id, version, file)
                    await self._put_object_from_path(
                        object_name=minio_path,
                        file_path=abs_path,
                        file_size=file_size,
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

                logger.info(
                    "Uploaded %d original files to %s, total size: %d bytes",
                    len(dataset_files_v1),
                    version,
                    total_size_v1,
                )

                if do_split and version_split:
                    if is_image_folder:
                        v2_files, v2_size, split_counts = await self._upload_vision_folder_with_split(
                            collected,
                            user_id,
                            dataset_id,
                            version_split,
                            preserve_structure,
                            filename_column="filename",
                            label_column="label",
                        )
                    else:
                        v2_files, v2_size, split_counts = await self._upload_folder_with_split(
                            collected, user_id, dataset_id, version_split, preserve_structure
                        )
                    return ((dataset_files_v1, total_size_v1, None), (v2_files, v2_size, split_counts))

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
        collected: List[Tuple[str, str, str, int, str]],
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

        for i, (relative_path, file, abs_path, file_size, file_type) in enumerate(collected):
            if i in train_idx:
                subfolder = "train"
            elif i in test_idx:
                subfolder = "test"
            else:
                subfolder = "drift"
            path_in_split = f"{subfolder}/{relative_path}" if preserve_structure else f"{subfolder}/{file}"
            minio_path = f"datasets/{user_id}/{dataset_id}/{version}/{path_in_split}"
            await self._put_object_from_path(
                object_name=minio_path,
                file_path=abs_path,
                file_size=file_size,
                content_type="application/octet-stream",
            )
            file_hash = self._calculate_md5_from_path(abs_path)
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

    async def _upload_vision_folder_with_split(
        self,
        collected: List[Tuple[str, str, str, int, str]],
        user_id: str,
        dataset_id: str,
        version: str,
        preserve_structure: bool,
        *,
        filename_column: str = "filename",
        label_column: str = "label",
    ) -> Tuple[List[DatasetFile], int, Dict[str, int]]:
        """
        Split an image dataset into train/test/drift and generate split-specific annotations.

        - Split assignment is based on image files only.
        - The original annotation file is not randomly assigned; instead, we generate one per split:
          train/<annotations.*>, test/<annotations.*>, drift/<annotations.*>
        - Filenames in annotations are normalized to match paths inside the split ZIP
          (the DW download strips the train/test/drift prefix).
        """
        # Collect image relpaths
        image_relpaths: list[str] = []
        image_relset: set[str] = set()
        image_basename_counts: dict[str, int] = {}
        for rel, _name, _abs, _size, ext in collected:
            ext_lower = (ext or "").lower()
            if ext_lower in self._IMAGE_EXTENSIONS:
                rel_norm = self._normalize_relpath(rel)
                image_relpaths.append(rel_norm)
                image_relset.add(rel_norm)
                bn = os.path.basename(rel_norm).lower()
                image_basename_counts[bn] = image_basename_counts.get(bn, 0) + 1

        if not image_relpaths:
            return await self._upload_folder_with_split(collected, user_id, dataset_id, version, preserve_structure)

        # Select + parse annotations
        ann = self._select_annotation_candidate(collected)
        if not ann:
            raise HTTPException(
                status_code=400,
                detail="Missing annotations file. Please provide an annotations CSV or JSON (with filename+label) and re-upload your dataset.",
            )
        ann_rel, ann_ext, ann_abs_path = ann
        ann_basename = os.path.basename(ann_rel) or f"annotations.{ann_ext}"
        with open(ann_abs_path, "rb") as f:
            ann_bytes = f.read()
        rows = self._parse_vision_annotations_to_rows(
            ann_rel, ann_ext, ann_bytes, filename_column=filename_column, label_column=label_column
        )

        fn_key_l = (filename_column or "filename").strip().lower()
        lbl_key_l = (label_column or "label").strip().lower()

        def _find_key(d: dict, key_l: str) -> str | None:
            for k in d.keys():
                if str(k).strip().lower() == key_l:
                    return str(k)
            return None

        fn_key = _find_key(rows[0], fn_key_l) or (filename_column or "filename")
        lbl_key = _find_key(rows[0], lbl_key_l) or (label_column or "label")

        # Split image list
        indices = list(range(len(image_relpaths)))
        random.shuffle(indices)
        n = len(indices)
        n_train = int(n * SPLIT_TRAIN_RATIO)
        n_test = int(n * SPLIT_TEST_RATIO)
        if n_train == 0 and n > 0:
            n_train = 1
        if n_test == 0 and n > 2:
            n_test = 1
        n_train = min(n_train, n)
        n_test = min(n_test, n - n_train)
        train_idx = set(indices[:n_train])
        test_idx = set(indices[n_train : n_train + n_test])
        drift_idx = set(indices[n_train + n_test :])

        split_to_images: dict[str, set[str]] = {"train": set(), "test": set(), "drift": set()}
        for i, rel_norm in enumerate(image_relpaths):
            if i in train_idx:
                split_to_images["train"].add(rel_norm)
            elif i in test_idx:
                split_to_images["test"].add(rel_norm)
            else:
                split_to_images["drift"].add(rel_norm)

        # Map a filename from annotations to an image relpath in the ZIP
        def _map_to_rel(fn_val) -> str | None:
            if fn_val is None:
                return None
            rel_norm = self._normalize_relpath(str(fn_val))
            if rel_norm in image_relset:
                return rel_norm
            bn = os.path.basename(rel_norm).lower()
            if image_basename_counts.get(bn, 0) == 1:
                for r in image_relset:
                    if os.path.basename(r).lower() == bn:
                        return r
            return None

        # Build split annotation rows
        split_rows: dict[str, list[dict]] = {"train": [], "test": [], "drift": []}
        for row in rows:
            if not isinstance(row, dict):
                continue
            mapped = _map_to_rel(row.get(fn_key))
            lbl_val = row.get(lbl_key)
            if mapped is None or lbl_val is None or str(lbl_val).strip() == "":
                continue
            for split_name in ("train", "test", "drift"):
                if mapped in split_to_images[split_name]:
                    r2 = dict(row)
                    r2[fn_key] = mapped.replace("\\", "/")
                    split_rows[split_name].append(r2)
                    break

        # Identify original annotation files to skip uploading into split as-is
        annotation_relpaths = {
            self._normalize_relpath(rel)
            for rel, _n, _abs, _s, ext in collected
            if (ext or "").lower() in self._ANNOTATION_EXTENSIONS
        }

        dataset_files: List[DatasetFile] = []
        total_size = 0
        split_counts: Dict[str, int] = {"train": 0, "test": 0, "drift": 0}

        # Upload images to their assigned split; copy other non-annotation files to all splits
        rel_to_split = {}
        for split_name, rels in split_to_images.items():
            for r in rels:
                rel_to_split[r] = split_name

        for relative_path, file, abs_path, file_size, file_type in collected:
            rel_norm = self._normalize_relpath(relative_path)
            ext_lower = (file_type or "").lower()

            if rel_norm in annotation_relpaths:
                continue

            if ext_lower in self._IMAGE_EXTENSIONS:
                subfolder = rel_to_split.get(rel_norm, "train")
                path_in_split = f"{subfolder}/{relative_path}" if preserve_structure else f"{subfolder}/{file}"
                minio_path = f"datasets/{user_id}/{dataset_id}/{version}/{path_in_split}"
                await self._put_object_from_path(
                    object_name=minio_path,
                    file_path=abs_path,
                    file_size=file_size,
                    content_type="application/octet-stream",
                )
                file_hash = self._calculate_md5_from_path(abs_path)
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
                split_counts[subfolder] += 1
            else:
                for subfolder in ("train", "test", "drift"):
                    path_in_split = f"{subfolder}/{relative_path}" if preserve_structure else f"{subfolder}/{file}"
                    minio_path = f"datasets/{user_id}/{dataset_id}/{version}/{path_in_split}"
                    await self._put_object_from_path(
                        object_name=minio_path,
                        file_path=abs_path,
                        file_size=file_size,
                        content_type="application/octet-stream",
                    )
                    file_hash = self._calculate_md5_from_path(abs_path)
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
                    split_counts[subfolder] += 1

        # Upload generated annotations at root of each split folder
        for subfolder in ("train", "test", "drift"):
            out_bytes = self._write_split_annotations_bytes(ext_lower=ann_ext, rows=split_rows[subfolder])
            minio_path = f"datasets/{user_id}/{dataset_id}/{version}/{subfolder}/{ann_basename}"
            self.client.put_object(
                bucket_name=self.bucket_name,
                object_name=minio_path,
                data=BytesIO(out_bytes),
                length=len(out_bytes),
                content_type="application/octet-stream",
            )
            file_hash = self.calculate_file_hash(out_bytes)
            dataset_files.append(
                DatasetFile(
                    filename=ann_basename,
                    file_path=minio_path,
                    file_size=len(out_bytes),
                    file_type=ann_ext,
                    file_hash=file_hash,
                    content_type="application/octet-stream",
                )
            )
            total_size += len(out_bytes)
            split_counts[subfolder] += 1

        logger.info(
            "Vision folder split complete: train=%d test=%d drift=%d (image files=%d)",
            split_counts["train"],
            split_counts["test"],
            split_counts["drift"],
            len(image_relpaths),
        )
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
    
    @staticmethod
    def _media_type_for_filename(filename: str) -> str:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext == "csv":
            return "text/csv"
        if ext in ("xlsx", "xls"):
            return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        return "application/octet-stream"

    async def download_folder_subset(
        self,
        folder_path: str,
        subfolder_prefix: Optional[str] = None,
        *,
        archive_basename: str = "dataset",
    ) -> Tuple[bytes, str, str]:
        """
        Download objects under a folder prefix.

        When exactly one file exists (typical for tabular train/test/drift splits),
        return a ZIP containing that single file so AutoML Tabular (expects one file per
        archive) and multi-file folder downloads stay consistent. Otherwise return a ZIP.

        Returns:
            (data, download_filename, media_type)
        """
        prefix = folder_path
        if subfolder_prefix:
            prefix = f"{folder_path.rstrip('/')}/{subfolder_prefix}/"

        object_names: List[str] = []
        try:
            for obj in self.client.list_objects(
                self.bucket_name, prefix=prefix, recursive=True
            ):
                if not obj.object_name or obj.object_name.endswith("/"):
                    continue
                rel = obj.object_name.replace(prefix, "", 1).lstrip("/")
                if rel:
                    object_names.append(obj.object_name)
        except S3Error as e:
            logger.error(f"MinIO error listing folder {prefix}: {e}")
            raise HTTPException(status_code=404, detail="Folder not found") from e

        if not object_names:
            raise HTTPException(status_code=404, detail="No files found in folder")

        if len(object_names) == 1:
            object_name = object_names[0]
            try:
                response = self.client.get_object(self.bucket_name, object_name)
                file_data = response.read()
            except S3Error as e:
                logger.error(f"MinIO error downloading {object_name}: {e}")
                raise HTTPException(status_code=404, detail="File not found") from e
            entry_name = os.path.basename(object_name)
            zip_buffer = BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                zip_file.writestr(entry_name, file_data)
            zip_name = archive_basename + (
                f"_{subfolder_prefix}" if subfolder_prefix else ""
            ) + ".zip"
            return zip_buffer.getvalue(), zip_name, "application/zip"

        zip_data = await self.download_folder_as_zip(
            folder_path, subfolder_prefix=subfolder_prefix
        )
        zip_name = archive_basename + (
            f"_{subfolder_prefix}" if subfolder_prefix else ""
        ) + ".zip"
        return zip_data, zip_name, "application/zip"

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
