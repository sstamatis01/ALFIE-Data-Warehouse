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
# Pre-built download archives live beside split folders (not inside train/test/drift).
ARCHIVE_DIRNAME = "archives"


def stratified_train_test_drift_indices(
    labels: List[Any],
    *,
    train_ratio: float = SPLIT_TRAIN_RATIO,
    test_ratio: float = SPLIT_TEST_RATIO,
    rng: Optional[random.Random] = None,
) -> Tuple[List[int], List[int], List[int]]:
    """
    Stratified 70/15/15 index split that keeps class coverage when possible.

    Guardrails per class size ``n``:
      - n == 1: train only
      - n == 2: train + test (cannot cover all three splits)
      - n >= 3: at least one sample in train, test, and drift; remainder follows ratios

    Without stratification, small classes are often missing from test/drift
    (e.g. 10 images/class with random 70/15/15).
    """
    if not labels:
        return [], [], []

    rng = rng or random.Random()
    by_class: Dict[Any, List[int]] = {}
    for i, label in enumerate(labels):
        key = label if label is not None and str(label).strip() != "" else "__missing__"
        by_class.setdefault(key, []).append(i)

    train_idx: List[int] = []
    test_idx: List[int] = []
    drift_idx: List[int] = []

    for _label, idxs in by_class.items():
        idxs = list(idxs)
        rng.shuffle(idxs)
        n = len(idxs)

        if n == 1:
            train_idx.append(idxs[0])
            continue
        if n == 2:
            train_idx.append(idxs[0])
            test_idx.append(idxs[1])
            continue

        # n >= 3: guarantee coverage in all three splits
        n_test = max(1, int(n * test_ratio))
        n_drift = max(1, int(n * (1.0 - train_ratio - test_ratio)))
        n_train = n - n_test - n_drift
        if n_train < 1:
            # Shrink test/drift until train has at least one sample
            while n_train < 1 and (n_test > 1 or n_drift > 1):
                if n_test >= n_drift and n_test > 1:
                    n_test -= 1
                elif n_drift > 1:
                    n_drift -= 1
                else:
                    break
                n_train = n - n_test - n_drift
        if n_train < 1:
            n_train = 1
            rem = n - 1
            n_test = max(1, rem // 2)
            n_drift = rem - n_test

        train_idx.extend(idxs[:n_train])
        test_idx.extend(idxs[n_train : n_train + n_test])
        drift_idx.extend(idxs[n_train + n_test :])

    rng.shuffle(train_idx)
    rng.shuffle(test_idx)
    rng.shuffle(drift_idx)
    return train_idx, test_idx, drift_idx


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
    def dataset_version_folder_path(user_id: str, dataset_id: str, version: str) -> str:
        return f"datasets/{user_id}/{dataset_id}/{version}/"

    @staticmethod
    def archive_object_key(folder_path: str, split: Optional[str] = None) -> str:
        """
        Object key for a pre-built download ZIP.

        Examples:
          datasets/u/d/v2/archives/train.zip
          datasets/u/d/v1/archives/full.zip
        """
        base = (folder_path or "").rstrip("/")
        name = f"{split}.zip" if split else "full.zip"
        return f"{base}/{ARCHIVE_DIRNAME}/{name}"

    def object_exists(self, object_name: str) -> bool:
        try:
            self.client.stat_object(self.bucket_name, object_name)
            return True
        except S3Error:
            return False
        except Exception:
            return False

    def iter_object_chunks(self, object_name: str, *, chunk_size: int = 1024 * 1024):
        """Yield bytes from a MinIO object (for StreamingResponse)."""
        response = self.client.get_object(self.bucket_name, object_name)
        try:
            for chunk in response.stream(chunk_size):
                if chunk:
                    yield chunk
        finally:
            try:
                response.close()
            finally:
                response.release_conn()

    def _list_folder_member_objects(
        self, folder_path: str, subfolder_prefix: Optional[str] = None
    ) -> List[Tuple[str, str]]:
        """
        List (object_name, zip_entry_name) under a folder, excluding ``archives/``.
        """
        prefix = folder_path if not subfolder_prefix else (
            f"{folder_path.rstrip('/')}/{subfolder_prefix}/"
        )
        archive_marker = f"/{ARCHIVE_DIRNAME}/"
        pairs: List[Tuple[str, str]] = []
        for obj in self.client.list_objects(
            self.bucket_name, prefix=prefix, recursive=True
        ):
            name = obj.object_name or ""
            if not name or name.endswith("/"):
                continue
            if archive_marker in f"/{name}" or name.rstrip("/").endswith(f"/{ARCHIVE_DIRNAME}"):
                continue
            zip_path = name.replace(prefix, "", 1).lstrip("/")
            if zip_path:
                pairs.append((name, zip_path))
        return pairs

    def _build_zip_file_from_objects(
        self,
        members: List[Tuple[str, str]],
        dest_path: str,
        *,
        compression: int = zipfile.ZIP_STORED,
    ) -> int:
        """
        Write members (object_name, zip_entry) into dest_path. Returns member count.

        Uses ZIP_STORED by default — vision payloads are usually already compressed
        (JPEG/PNG), and STORED is much faster for 10k+ files.
        """
        if not members:
            raise HTTPException(status_code=404, detail="No files found in folder")
        with zipfile.ZipFile(dest_path, "w", compression=compression) as zf:
            for object_name, zip_path in members:
                response = self.client.get_object(self.bucket_name, object_name)
                try:
                    # Stream object into the zip entry to limit peak RAM
                    with zf.open(zip_path, "w") as dest:
                        for chunk in response.stream(1024 * 1024):
                            if chunk:
                                dest.write(chunk)
                finally:
                    try:
                        response.close()
                    finally:
                        response.release_conn()
        return len(members)

    async def build_and_store_folder_archive(
        self,
        folder_path: str,
        subfolder_prefix: Optional[str] = None,
        *,
        force: bool = False,
    ) -> Dict[str, Any]:
        """
        Build a ZIP of the folder (or split subfolder) and store it under ``archives/``.

        Safe to call after upload/split so later downloads are a single object GET.
        """
        object_key = self.archive_object_key(folder_path, subfolder_prefix)
        if not force and self.object_exists(object_key):
            try:
                st = self.client.stat_object(self.bucket_name, object_key)
                size = getattr(st, "size", None)
            except Exception:
                size = None
            return {
                "object_key": object_key,
                "split": subfolder_prefix,
                "built": False,
                "size": size,
            }

        def _work() -> Dict[str, Any]:
            members = self._list_folder_member_objects(folder_path, subfolder_prefix)
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                tmp_path = tmp.name
            try:
                count = self._build_zip_file_from_objects(members, tmp_path)
                file_size = os.path.getsize(tmp_path)
                # Blocking MinIO put — run inside worker thread via anyio
                self.client.fput_object(
                    self.bucket_name,
                    object_key,
                    tmp_path,
                    content_type="application/zip",
                )
                return {
                    "object_key": object_key,
                    "split": subfolder_prefix,
                    "built": True,
                    "size": file_size,
                    "file_count": count,
                }
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

        result = await anyio.to_thread.run_sync(_work)
        logger.info(
            "Stored download archive %s (built=%s size=%s files=%s)",
            result.get("object_key"),
            result.get("built"),
            result.get("size"),
            result.get("file_count"),
        )
        return result

    async def ensure_split_archives(
        self,
        folder_path: str,
        splits: Tuple[str, ...] = SPLIT_SUBFOLDERS,
        *,
        force: bool = False,
    ) -> Dict[str, Any]:
        """Ensure train/test/drift (or given) archives exist under folder_path."""
        out: Dict[str, Any] = {}
        for split_name in splits:
            try:
                out[split_name] = await self.build_and_store_folder_archive(
                    folder_path, split_name, force=force
                )
            except HTTPException as e:
                logger.warning(
                    "Skip archive for %s/%s: %s", folder_path, split_name, e.detail
                )
                out[split_name] = {"error": str(e.detail), "split": split_name}
            except Exception as e:
                logger.warning(
                    "Failed building archive for %s/%s: %s", folder_path, split_name, e
                )
                out[split_name] = {"error": str(e), "split": split_name}
        return out

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
    def _extract_vision_annotation_schema(
        collected: List[Tuple[str, str, str, int, str]],
        *,
        filename_column: str = "filename",
        label_column: str = "label",
    ) -> Optional[Dict[str, Any]]:
        """
        Read the vision annotation CSV/JSON and return schema for dataset metadata.

        Returns dict with: columns, row_count, data_types, annotation_file,
        filename_column, label_column — or None if not a usable annotation set.
        """
        picked = FileService._select_annotation_candidate(collected)
        if not picked:
            return None
        rel_norm, ext_lower, abs_path = picked
        fn_pref = (filename_column or "filename").strip().lower()
        lbl_pref = (label_column or "label").strip().lower()

        try:
            with open(abs_path, "rb") as f:
                data = f.read()
        except OSError as e:
            logger.warning("Could not read annotation file %s: %s", rel_norm, e)
            return None

        if ext_lower == "csv":
            try:
                df = pd.read_csv(BytesIO(data))
            except Exception as e:
                logger.warning("Could not parse annotation CSV %s: %s", rel_norm, e)
                return None
            if df.empty and len(df.columns) == 0:
                return None
            cols_map = {str(c).strip().lower(): str(c) for c in df.columns}
            cols_l = set(cols_map.keys())
            fn_l = FileService._pick_annotation_column(
                cols_l, FileService._VISION_FILENAME_COLUMNS, fn_pref
            )
            lbl_l = FileService._pick_annotation_column(
                cols_l, FileService._VISION_LABEL_COLUMNS, lbl_pref
            )
            columns = [str(c) for c in df.columns]
            data_types = {str(c): str(df[c].dtype) for c in df.columns}
            return {
                "columns": columns,
                "row_count": int(len(df)),
                "data_types": data_types,
                "annotation_file": rel_norm,
                "filename_column": cols_map.get(fn_l) if fn_l else None,
                "label_column": cols_map.get(lbl_l) if lbl_l else None,
            }

        if ext_lower == "json":
            try:
                obj = json.loads(data.decode("utf-8", errors="strict"))
            except Exception as e:
                logger.warning("Could not parse annotation JSON %s: %s", rel_norm, e)
                return None
            if isinstance(obj, dict) and "annotations" in obj:
                obj = obj["annotations"]
            if not isinstance(obj, list) or not obj:
                return None
            rows = [x for x in obj if isinstance(x, dict)]
            if not rows:
                return None
            # Union of keys across rows (stable order: first-row keys, then extras)
            columns: list[str] = []
            seen: set[str] = set()
            for r in rows:
                for k in r.keys():
                    ks = str(k)
                    if ks not in seen:
                        seen.add(ks)
                        columns.append(ks)
            keys_l = {str(k).strip().lower(): str(k) for k in columns}
            fn_l = FileService._pick_annotation_column(
                set(keys_l.keys()), FileService._VISION_FILENAME_COLUMNS, fn_pref
            )
            lbl_l = FileService._pick_annotation_column(
                set(keys_l.keys()), FileService._VISION_LABEL_COLUMNS, lbl_pref
            )
            data_types = {c: "object" for c in columns}
            return {
                "columns": columns,
                "row_count": int(len(rows)),
                "data_types": data_types,
                "annotation_file": rel_norm,
                "filename_column": keys_l.get(fn_l) if fn_l else None,
                "label_column": keys_l.get(lbl_l) if lbl_l else None,
            }

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
        # Stratify on a label-like column when present so rare classes are not dropped
        # from test/drift; otherwise fall back to a plain shuffle.
        label_col = None
        cols_l = {str(c).strip().lower(): c for c in df.columns}
        for cand in self._VISION_LABEL_COLUMNS:
            if cand in cols_l:
                label_col = cols_l[cand]
                break
        if label_col is not None:
            train_idx, test_idx, drift_idx = stratified_train_test_drift_indices(
                df[label_col].tolist()
            )
            logger.info(
                "Tabular split stratified on column '%s' (train=%d test=%d drift=%d)",
                label_col,
                len(train_idx),
                len(test_idx),
                len(drift_idx),
            )
        else:
            indices = list(range(n))
            random.shuffle(indices)
            n_train = int(n * SPLIT_TRAIN_RATIO)
            n_test = int(n * SPLIT_TEST_RATIO)
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
    ) -> Tuple[
        Tuple[List[DatasetFile], int, Optional[Dict[str, int]]],
        Optional[Tuple[List[DatasetFile], int, Dict[str, int]]],
        Optional[Dict[str, Any]],
    ]:
        """
        Upload a folder of dataset files (as zip). Original is always stored under `version` (v1).
        If the number of files is large enough and `version_split` is set, a train/test/drift split
        is also stored under `version_split` (v2).

        Returns:
            ((v1_files, v1_size, split_counts|None), (v2_files, v2_size, split_counts) or None,
             vision_annotation_schema or None).
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
            vision_schema: Optional[Dict[str, Any]] = None
            if is_image_folder:
                self._validate_automl_vision_annotations(collected, filename_column="filename", label_column="label")
                vision_schema = self._extract_vision_annotation_schema(
                    collected, filename_column="filename", label_column="label"
                )

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
                return ((dataset_files_v1, total_size_v1, None), (v2_files, v2_size, split_counts), vision_schema)

            if do_split and not version_split:
                logger.info("Folder large enough to split but version_split not set; only v1 stored")
            if split_counts_existing is not None:
                try:
                    await self.ensure_split_archives(
                        self.dataset_version_folder_path(user_id, dataset_id, version)
                    )
                except Exception as e:
                    logger.warning(
                        "Pre-building archives for pre-split upload failed: %s", e
                    )
            return ((dataset_files_v1, total_size_v1, split_counts_existing), None, vision_schema)

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
    ) -> Tuple[
        Tuple[List[DatasetFile], int, Optional[Dict[str, int]]],
        Optional[Tuple[List[DatasetFile], int, Dict[str, int]]],
        Optional[Dict[str, Any]],
    ]:
        """
        Same as `upload_dataset_folder`, but reads a local ZIP file path.
        Intended for background ingestion jobs (ZIP already staged in object storage).

        Returns:
            ((v1_files, v1_size, split_counts|None), v2_result or None, vision_annotation_schema or None).
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
                vision_schema: Optional[Dict[str, Any]] = None
                if is_image_folder:
                    self._validate_automl_vision_annotations(collected, filename_column="filename", label_column="label")
                    vision_schema = self._extract_vision_annotation_schema(
                        collected, filename_column="filename", label_column="label"
                    )

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
                    return ((dataset_files_v1, total_size_v1, None), (v2_files, v2_size, split_counts), vision_schema)

                if split_counts_existing is not None:
                    try:
                        await self.ensure_split_archives(
                            self.dataset_version_folder_path(user_id, dataset_id, version)
                        )
                    except Exception as e:
                        logger.warning(
                            "Pre-building archives for pre-split ZIP-path upload failed: %s", e
                        )
                return ((dataset_files_v1, total_size_v1, split_counts_existing), None, vision_schema)

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
        try:
            await self.ensure_split_archives(
                self.dataset_version_folder_path(user_id, dataset_id, version)
            )
        except Exception as e:
            logger.warning("Pre-building split archives after folder split failed: %s", e)
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

        # Build image -> label map from annotations (needed for stratified split)
        image_to_label: dict[str, Any] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            mapped = _map_to_rel(row.get(fn_key))
            lbl_val = row.get(lbl_key)
            if mapped is None or lbl_val is None or str(lbl_val).strip() == "":
                continue
            image_to_label[mapped] = lbl_val

        # Stratified split by class so test/drift are not missing a label when n>=3 per class
        image_labels = [image_to_label.get(rel, "__unlabeled__") for rel in image_relpaths]
        n_labeled = sum(1 for lab in image_labels if lab != "__unlabeled__")
        if n_labeled > 0:
            train_list, test_list, drift_list = stratified_train_test_drift_indices(image_labels)
            logger.info(
                "Vision split stratified by label (%d/%d images labeled): train=%d test=%d drift=%d",
                n_labeled,
                len(image_relpaths),
                len(train_list),
                len(test_list),
                len(drift_list),
            )
        else:
            # No usable labels — fall back to random partition
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
            train_list = indices[:n_train]
            test_list = indices[n_train : n_train + n_test]
            drift_list = indices[n_train + n_test :]
            logger.warning(
                "Vision split could not stratify (no labels matched images); using random split"
            )

        split_to_images: dict[str, set[str]] = {"train": set(), "test": set(), "drift": set()}
        for i in train_list:
            split_to_images["train"].add(image_relpaths[i])
        for i in test_list:
            split_to_images["test"].add(image_relpaths[i])
        for i in drift_list:
            split_to_images["drift"].add(image_relpaths[i])

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
        # custom_metadata.split should reflect labeled samples (images), not annotation files
        image_split_counts: Dict[str, int] = {
            "train": len(split_to_images["train"]),
            "test": len(split_to_images["test"]),
            "drift": len(split_to_images["drift"]),
        }

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

        # Log per-class coverage for debugging AutoML empty-class failures
        for split_name, rows_s in split_rows.items():
            class_counts: Dict[str, int] = {}
            for r in rows_s:
                lab = str(r.get(lbl_key, "")).strip() or "?"
                class_counts[lab] = class_counts.get(lab, 0) + 1
            logger.info(
                "Vision split '%s' class coverage: %s (images=%d, annotation_rows=%d)",
                split_name,
                class_counts,
                image_split_counts[split_name],
                len(rows_s),
            )

        logger.info(
            "Vision folder split complete: train=%d test=%d drift=%d (image files=%d)",
            image_split_counts["train"],
            image_split_counts["test"],
            image_split_counts["drift"],
            len(image_relpaths),
        )
        try:
            await self.ensure_split_archives(
                self.dataset_version_folder_path(user_id, dataset_id, version)
            )
        except Exception as e:
            logger.warning("Pre-building split archives after vision split failed: %s", e)
        return dataset_files, total_size, image_split_counts
    
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

    def resolve_prebuilt_archive(
        self,
        folder_path: str,
        subfolder_prefix: Optional[str] = None,
        *,
        archive_basename: str = "dataset",
    ) -> Optional[Dict[str, Any]]:
        """If a pre-built archive exists, return stream metadata for the download API."""
        object_key = self.archive_object_key(folder_path, subfolder_prefix)
        if not self.object_exists(object_key):
            return None
        try:
            st = self.client.stat_object(self.bucket_name, object_key)
            size = int(getattr(st, "size", 0) or 0)
        except Exception:
            size = None
        zip_name = archive_basename + (
            f"_{subfolder_prefix}" if subfolder_prefix else ""
        ) + ".zip"
        return {
            "object_key": object_key,
            "filename": zip_name,
            "media_type": "application/zip",
            "size": size,
            "source": "prebuilt_archive",
        }

    async def download_folder_subset(
        self,
        folder_path: str,
        subfolder_prefix: Optional[str] = None,
        *,
        archive_basename: str = "dataset",
        prefer_prebuilt: bool = True,
        store_archive_if_missing: bool = True,
    ) -> Tuple[bytes, str, str]:
        """
        Download objects under a folder prefix.

        Prefers pre-built ``archives/{split}.zip`` when present. Otherwise builds on
        the fly (and optionally caches that archive for the next request).

        When exactly one file exists (typical tabular split), return a ZIP with that
        one file so AutoML Tabular stays consistent.

        Returns:
            (data, download_filename, media_type)
        """
        zip_name = archive_basename + (
            f"_{subfolder_prefix}" if subfolder_prefix else ""
        ) + ".zip"

        if prefer_prebuilt:
            prebuilt = self.resolve_prebuilt_archive(
                folder_path,
                subfolder_prefix,
                archive_basename=archive_basename,
            )
            if prebuilt:
                logger.info("Serving pre-built archive %s", prebuilt["object_key"])
                data = b"".join(self.iter_object_chunks(prebuilt["object_key"]))
                return data, prebuilt["filename"], prebuilt["media_type"]

        try:
            members = self._list_folder_member_objects(folder_path, subfolder_prefix)
        except S3Error as e:
            logger.error(f"MinIO error listing folder {folder_path}: {e}")
            raise HTTPException(status_code=404, detail="Folder not found") from e

        if not members:
            raise HTTPException(status_code=404, detail="No files found in folder")

        if len(members) == 1:
            object_name, entry_name = members[0]
            response = None
            try:
                response = self.client.get_object(self.bucket_name, object_name)
                file_data = response.read()
            except S3Error as e:
                logger.error(f"MinIO error downloading {object_name}: {e}")
                raise HTTPException(status_code=404, detail="File not found") from e
            finally:
                if response is not None:
                    try:
                        response.close()
                        response.release_conn()
                    except Exception:
                        pass
            zip_buffer = BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                zip_file.writestr(os.path.basename(entry_name), file_data)
            return zip_buffer.getvalue(), zip_name, "application/zip"

        zip_data = await self.download_folder_as_zip(
            folder_path, subfolder_prefix=subfolder_prefix
        )
        if store_archive_if_missing:
            try:
                await self.build_and_store_folder_archive(
                    folder_path, subfolder_prefix, force=True
                )
            except Exception as e:
                logger.warning("Could not cache on-the-fly zip as archive: %s", e)
        return zip_data, zip_name, "application/zip"

    async def download_folder_as_zip(
        self, folder_path: str, subfolder_prefix: Optional[str] = None
    ) -> bytes:
        """
        Download all files in a folder as a zip archive (excludes ``archives/``).

        Prefer ``resolve_prebuilt_archive`` + streaming for large vision splits.
        """
        try:
            members = self._list_folder_member_objects(folder_path, subfolder_prefix)
            if not members:
                raise HTTPException(status_code=404, detail="No files found in folder")

            def _work() -> bytes:
                with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                    tmp_path = tmp.name
                try:
                    self._build_zip_file_from_objects(members, tmp_path)
                    with open(tmp_path, "rb") as f:
                        return f.read()
                finally:
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass

            return await anyio.to_thread.run_sync(_work)
        except HTTPException:
            raise
        except S3Error as e:
            logger.error(f"MinIO error during folder zip download: {e}")
            raise HTTPException(status_code=404, detail="Folder not found")
        except Exception as e:
            logger.error(f"Unexpected error during folder zip download: {e}")
            raise HTTPException(status_code=500, detail="Folder zip download failed")


# Global file service instance
file_service = FileService()
