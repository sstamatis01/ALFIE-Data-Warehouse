"""Resolve MinIO paths for user datasets linked to the public catalog."""

from __future__ import annotations

from ..models.dataset import DatasetMetadata, PublicDatasetLink

PUBLIC_OWNER_USER_ID = "public"


def is_linked_public_copy(dataset: DatasetMetadata) -> bool:
    return dataset.public_link is not None


def public_storage_prefix(link: PublicDatasetLink) -> str:
    return f"datasets/{PUBLIC_OWNER_USER_ID}/{link.dataset_id}/{link.version}/"


def resolve_storage_path(dataset: DatasetMetadata, logical_path: str) -> str:
    """
    Map a user-namespace MinIO path to the underlying storage path.
    For linked imports, data lives under datasets/public/{id}/{version}/.
    """
    if not dataset.public_link:
        return logical_path

    user_prefix = f"datasets/{dataset.user_id}/{dataset.dataset_id}/{dataset.version}/"
    storage_prefix = public_storage_prefix(dataset.public_link)

    if logical_path.startswith(user_prefix):
        return storage_prefix + logical_path[len(user_prefix) :]

    public_prefix = f"datasets/{PUBLIC_OWNER_USER_ID}/"
    if logical_path.startswith(public_prefix):
        return logical_path

    if not logical_path.startswith("datasets/"):
        return storage_prefix + logical_path.lstrip("/")

    return logical_path
