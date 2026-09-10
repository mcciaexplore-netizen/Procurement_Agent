"""Immutable raw-capture storage.

The local adapter is used for development and preserves the same object-key
contract expected by an S3/MinIO adapter in production. A feed body is written
once under its content hash; normalized records keep only the pointer.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol


class RawCaptureStore(Protocol):
    def put(self, source_id: str, content_hash: str, payload: bytes) -> str: ...


class FilesystemRawCaptureStore:
    def __init__(self, root: Path | None = None) -> None:
        configured = os.getenv("RAW_CAPTURE_ROOT")
        self.root = root or (Path(configured) if configured else self._default_root())

    @staticmethod
    def _default_root() -> Path:
        """Use the repository data directory locally, or /app/data in a container.

        A fixed ``parents[n]`` lookup is unsafe because production containers
        intentionally have a much shallower file layout than the repository.
        """
        module_path = Path(__file__).resolve()
        for candidate in module_path.parents:
            if (candidate / "services" / "api").is_dir() and (candidate / "infra").is_dir():
                return candidate / "data" / "raw-captures"
        return Path.cwd() / "data" / "raw-captures"

    def put(self, source_id: str, content_hash: str, payload: bytes) -> str:
        if len(content_hash) != 64 or any(char not in "0123456789abcdef" for char in content_hash):
            raise ValueError("raw capture content hash must be a SHA-256 hex digest")
        safe_source = "".join(char if char.isalnum() or char in "-_" else "_" for char in source_id)
        object_key = f"raw/{safe_source}/{content_hash[:2]}/{content_hash}.csv"
        destination = self.root / object_key
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if destination.read_bytes() != payload:
                raise ValueError("content hash collision for raw capture")
            return object_key
        temporary = destination.with_suffix(".tmp")
        temporary.write_bytes(payload)
        temporary.replace(destination)
        return object_key


class S3RawCaptureStore:
    """S3-compatible immutable raw capture store (AWS S3 or MinIO)."""

    def __init__(self, bucket: str, endpoint_url: str | None, access_key: str, secret_key: str, region: str = "ap-south-1") -> None:
        self.bucket = bucket
        self.endpoint_url = endpoint_url
        self.access_key = access_key
        self.secret_key = secret_key
        self.region = region

    def _client(self):
        try:
            import boto3
            from botocore.client import Config
        except ImportError as error:  # pragma: no cover - deployment dependency
            raise RuntimeError("S3 raw storage requires boto3; install services/api/requirements.txt") from error
        return boto3.client(
            "s3", endpoint_url=self.endpoint_url, aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key, region_name=self.region,
            config=Config(signature_version="s3v4"),
        )

    def _ensure_bucket(self, client) -> None:
        try:
            client.head_bucket(Bucket=self.bucket)
        except Exception as error:  # ClientError type is optional until boto3 is installed
            code = getattr(getattr(error, "response", {}), "get", lambda _key, _default=None: _default)("Error", {}).get("Code")
            if code not in {"404", "NoSuchBucket", "NotFound"}:
                raise
            create_args = {"Bucket": self.bucket}
            if not self.endpoint_url and self.region != "us-east-1":
                create_args["CreateBucketConfiguration"] = {"LocationConstraint": self.region}
            client.create_bucket(**create_args)

    def put(self, source_id: str, content_hash: str, payload: bytes) -> str:
        if len(content_hash) != 64 or any(char not in "0123456789abcdef" for char in content_hash):
            raise ValueError("raw capture content hash must be a SHA-256 hex digest")
        safe_source = "".join(char if char.isalnum() or char in "-_" else "_" for char in source_id)
        object_key = f"raw/{safe_source}/{content_hash[:2]}/{content_hash}.csv"
        client = self._client()
        self._ensure_bucket(client)
        try:
            client.head_object(Bucket=self.bucket, Key=object_key)
            return object_key
        except Exception as error:
            code = getattr(getattr(error, "response", {}), "get", lambda _key, _default=None: _default)("Error", {}).get("Code")
            if code not in {"404", "NoSuchKey", "NotFound"}:
                raise
        client.put_object(
            Bucket=self.bucket, Key=object_key, Body=payload, ContentType="text/csv; charset=utf-8",
            Metadata={"sha256": content_hash, "source-id": safe_source},
        )
        return object_key


def build_raw_capture_store() -> RawCaptureStore:
    backend = os.getenv("RAW_CAPTURE_BACKEND", "filesystem").lower()
    if backend == "filesystem":
        return FilesystemRawCaptureStore()
    if backend != "s3":
        raise RuntimeError("RAW_CAPTURE_BACKEND must be filesystem or s3")
    bucket = os.getenv("S3_RAW_CAPTURE_BUCKET")
    access_key = os.getenv("S3_ACCESS_KEY")
    secret_key = os.getenv("S3_SECRET_KEY")
    if not bucket or not access_key or not secret_key:
        raise RuntimeError("S3 raw storage requires S3_RAW_CAPTURE_BUCKET, S3_ACCESS_KEY, and S3_SECRET_KEY")
    return S3RawCaptureStore(bucket, os.getenv("S3_ENDPOINT_URL"), access_key, secret_key, os.getenv("AWS_REGION", "ap-south-1"))
