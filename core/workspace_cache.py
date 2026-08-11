"""Bounded, on-disk snapshots for temporary Streamlit workspaces.

The application deliberately has no user account system.  A workspace is
therefore addressed by an opaque, short-lived token that is carried in the
browser URL.  This module owns only filesystem persistence; Streamlit session
state selection and hydration live in :mod:`ui.workspace`.
"""

from __future__ import annotations

import copy
import gzip
import hashlib
import json
import os
import pickle
import re
import secrets
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from core.config import DATA_DIR


WORKSPACE_CACHE_SCHEMA_VERSION = 1
WORKSPACE_TTL_SECONDS = 24 * 60 * 60
WORKSPACE_MAX_BYTES = 160 * 1024 * 1024
WORKSPACE_CACHE_MAX_BYTES = int(1.5 * 1024 * 1024 * 1024)
WORKSPACE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{20,128}$")


class WorkspaceCacheError(RuntimeError):
    """Raised when a workspace cannot be safely persisted."""


@dataclass(frozen=True)
class WorkspaceSnapshotMeta:
    workspace_id: str
    created_at: float
    updated_at: float
    expires_at: float
    size_bytes: int


def default_workspace_cache_root() -> Path:
    return Path(DATA_DIR) / "runtime-cache" / "workspaces"


def is_valid_workspace_id(value: object) -> bool:
    return bool(WORKSPACE_ID_PATTERN.fullmatch(str(value or "")))


def new_workspace_id() -> str:
    return secrets.token_urlsafe(24)


class WorkspaceSnapshotStore:
    """Persist opaque workspaces with TTL and byte-budget based cleanup."""

    _process_lock = threading.RLock()

    def __init__(
        self,
        root: str | Path | None = None,
        *,
        ttl_seconds: int = WORKSPACE_TTL_SECONDS,
        max_workspace_bytes: int = WORKSPACE_MAX_BYTES,
        max_total_bytes: int = WORKSPACE_CACHE_MAX_BYTES,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.root = Path(root) if root is not None else default_workspace_cache_root()
        self.ttl_seconds = int(ttl_seconds)
        self.max_workspace_bytes = int(max_workspace_bytes)
        self.max_total_bytes = int(max_total_bytes)
        self._clock = clock
        self._lock = self._process_lock

    def create_workspace_id(self) -> str:
        return new_workspace_id()

    def save(self, workspace_id: str, payload: dict[str, Any]) -> WorkspaceSnapshotMeta:
        if not is_valid_workspace_id(workspace_id):
            raise WorkspaceCacheError("invalid workspace id")

        with self._lock:
            now = float(self._clock())
            self._ensure_root()
            workspace_dir = self._workspace_dir(workspace_id)
            workspace_dir.mkdir(parents=True, exist_ok=True)
            self._restrict_directory(workspace_dir)

            prepared = copy.deepcopy(payload)
            created_uploads: set[Path] = set()
            try:
                upload_references, created_uploads = self._replace_upload_bytes_with_references(prepared, workspace_dir)
                encoded = gzip.compress(pickle.dumps(prepared, protocol=pickle.HIGHEST_PROTOCOL))
            except Exception:
                self._discard_created_uploads(workspace_dir, created_uploads)
                raise

            attachment_bytes = self._referenced_upload_size(workspace_dir, upload_references)
            total_size = len(encoded) + attachment_bytes
            if total_size > self.max_workspace_bytes:
                self._discard_created_uploads(workspace_dir, created_uploads)
                raise WorkspaceCacheError(
                    f"workspace snapshot is {total_size} bytes; limit is {self.max_workspace_bytes}"
                )

            previous = self._read_manifest(workspace_dir)
            created_at = float(previous.get("created_at", now)) if previous else now
            self._atomic_write_bytes(workspace_dir / "snapshot.pkl.gz", encoded)
            manifest = {
                "schema_version": WORKSPACE_CACHE_SCHEMA_VERSION,
                "workspace_id": workspace_id,
                "created_at": created_at,
                "updated_at": now,
                "expires_at": now + self.ttl_seconds,
                "size_bytes": total_size,
            }
            self._atomic_write_text(workspace_dir / "manifest.json", json.dumps(manifest, sort_keys=True))
            self._prune_unreferenced_uploads(workspace_dir, upload_references)
            self.cleanup(exclude_workspace_ids={workspace_id})
            return WorkspaceSnapshotMeta(
                workspace_id=workspace_id,
                created_at=created_at,
                updated_at=now,
                expires_at=float(manifest["expires_at"]),
                size_bytes=total_size,
            )

    def load(self, workspace_id: str) -> dict[str, Any] | None:
        if not is_valid_workspace_id(workspace_id):
            return None

        with self._lock:
            workspace_dir = self._workspace_dir(workspace_id)
            manifest = self._read_manifest(workspace_dir)
            if manifest is None:
                return None
            now = float(self._clock())
            try:
                expires_at = float(manifest.get("expires_at", 0))
                schema_version = int(manifest.get("schema_version", -1))
            except (TypeError, ValueError):
                self._remove_workspace(workspace_dir)
                return None
            if expires_at <= now:
                self._remove_workspace(workspace_dir)
                return None
            if schema_version != WORKSPACE_CACHE_SCHEMA_VERSION:
                self._remove_workspace(workspace_dir)
                return None

            try:
                encoded = (workspace_dir / "snapshot.pkl.gz").read_bytes()
                payload = pickle.loads(gzip.decompress(encoded))
            except Exception:
                self._remove_workspace(workspace_dir)
                return None
            if not isinstance(payload, dict):
                self._remove_workspace(workspace_dir)
                return None

            self._restore_upload_bytes(payload, workspace_dir)
            manifest["updated_at"] = now
            manifest["expires_at"] = now + self.ttl_seconds
            self._atomic_write_text(workspace_dir / "manifest.json", json.dumps(manifest, sort_keys=True))
            return payload

    def clear(self, workspace_id: str) -> None:
        if not is_valid_workspace_id(workspace_id):
            return
        with self._lock:
            self._remove_workspace(self._workspace_dir(workspace_id))

    def cleanup(self, *, exclude_workspace_ids: set[str] | None = None) -> list[str]:
        """Delete expired snapshots, then oldest snapshots until within budget."""
        excluded = exclude_workspace_ids or set()
        removed: list[str] = []
        with self._lock:
            self._ensure_root()
            entries: list[tuple[Path, dict[str, Any], int]] = []
            now = float(self._clock())
            for workspace_dir in self.root.iterdir():
                if not workspace_dir.is_dir() or workspace_dir.name.startswith("."):
                    continue
                manifest = self._read_manifest(workspace_dir)
                if manifest is None:
                    self._remove_workspace(workspace_dir)
                    removed.append(workspace_dir.name)
                    continue
                try:
                    expires_at = float(manifest.get("expires_at", 0))
                    updated_at = float(manifest.get("updated_at", 0))
                except (TypeError, ValueError):
                    self._remove_workspace(workspace_dir)
                    removed.append(workspace_dir.name)
                    continue
                if expires_at <= now:
                    self._remove_workspace(workspace_dir)
                    removed.append(workspace_dir.name)
                    continue
                manifest["updated_at"] = updated_at
                entries.append((workspace_dir, manifest, self._directory_size(workspace_dir)))

            total_size = sum(size for _path, _manifest, size in entries)
            for workspace_dir, manifest, size in sorted(entries, key=lambda item: float(item[1].get("updated_at", 0))):
                if total_size <= self.max_total_bytes:
                    break
                if workspace_dir.name in excluded:
                    continue
                self._remove_workspace(workspace_dir)
                removed.append(workspace_dir.name)
                total_size -= size
        return removed

    def _workspace_dir(self, workspace_id: str) -> Path:
        return self.root / workspace_id

    def _ensure_root(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self._restrict_directory(self.root)

    @staticmethod
    def _restrict_directory(path: Path) -> None:
        try:
            os.chmod(path, 0o700)
        except OSError:
            pass

    @staticmethod
    def _directory_size(path: Path) -> int:
        if not path.exists():
            return 0
        return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())

    @staticmethod
    def _read_manifest(workspace_dir: Path) -> dict[str, Any] | None:
        try:
            value = json.loads((workspace_dir / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return None
        return value if isinstance(value, dict) else None

    @staticmethod
    def _atomic_write_bytes(path: Path, payload: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
            handle.write(payload)
            temporary_path = Path(handle.name)
        try:
            os.replace(temporary_path, path)
        finally:
            temporary_path.unlink(missing_ok=True)

    @classmethod
    def _atomic_write_text(cls, path: Path, payload: str) -> None:
        cls._atomic_write_bytes(path, payload.encode("utf-8"))

    def _remove_workspace(self, workspace_dir: Path) -> None:
        if workspace_dir.parent != self.root:
            return
        shutil.rmtree(workspace_dir, ignore_errors=True)

    def _replace_upload_bytes_with_references(
        self,
        payload: dict[str, Any],
        workspace_dir: Path,
    ) -> tuple[set[str], set[Path]]:
        routes = payload.get("routes")
        if not isinstance(routes, dict):
            return set(), set()
        uploads_dir = workspace_dir / "uploads"
        references: set[str] = set()
        created: set[Path] = set()

        def store_bytes(raw: object) -> str | None:
            if not isinstance(raw, (bytes, bytearray)):
                return None
            content = bytes(raw)
            digest = hashlib.sha256(content).hexdigest()
            target = uploads_dir / f"{digest}.bin"
            if not target.exists():
                self._atomic_write_bytes(target, content)
                self._restrict_directory(uploads_dir)
                created.add(target)
            references.add(digest)
            return digest

        single = routes.get("single")
        if isinstance(single, dict):
            upload_ref = store_bytes(single.get("uploaded_bytes"))
            if upload_ref is not None:
                single["uploaded_ref"] = upload_ref
                single["uploaded_bytes"] = None

        multi = routes.get("multi")
        if isinstance(multi, dict):
            for item in multi.get("uploads", []):
                if not isinstance(item, dict):
                    continue
                upload_ref = store_bytes(item.get("bytes"))
                if upload_ref is not None:
                    item["upload_ref"] = upload_ref
                    item["bytes"] = None
                elif isinstance(item.get("upload_ref"), str):
                    references.add(item["upload_ref"])
        if isinstance(single, dict) and isinstance(single.get("uploaded_ref"), str):
            references.add(single["uploaded_ref"])
        return references, created

    @staticmethod
    def _referenced_upload_size(workspace_dir: Path, references: set[str]) -> int:
        uploads_dir = workspace_dir / "uploads"
        total = 0
        for digest in references:
            if not re.fullmatch(r"[a-f0-9]{64}", digest):
                continue
            try:
                total += (uploads_dir / f"{digest}.bin").stat().st_size
            except OSError:
                continue
        return total

    @staticmethod
    def _prune_unreferenced_uploads(workspace_dir: Path, references: set[str]) -> None:
        uploads_dir = workspace_dir / "uploads"
        if not uploads_dir.exists():
            return
        for upload in uploads_dir.glob("*.bin"):
            if upload.stem not in references:
                upload.unlink(missing_ok=True)

    def _discard_created_uploads(self, workspace_dir: Path, created: set[Path]) -> None:
        for upload in created:
            upload.unlink(missing_ok=True)
        uploads_dir = workspace_dir / "uploads"
        try:
            uploads_dir.rmdir()
        except OSError:
            pass
        if self._read_manifest(workspace_dir) is None:
            try:
                workspace_dir.rmdir()
            except OSError:
                pass

    @staticmethod
    def _restore_upload_bytes(payload: dict[str, Any], workspace_dir: Path) -> None:
        routes = payload.get("routes")
        if not isinstance(routes, dict):
            return

        def read_reference(value: object) -> bytes | None:
            digest = str(value or "")
            if not re.fullmatch(r"[a-f0-9]{64}", digest):
                return None
            try:
                return (workspace_dir / "uploads" / f"{digest}.bin").read_bytes()
            except OSError:
                return None

        single = routes.get("single")
        if isinstance(single, dict) and single.get("uploaded_ref"):
            single["uploaded_bytes"] = read_reference(single.get("uploaded_ref"))

        multi = routes.get("multi")
        if isinstance(multi, dict):
            for item in multi.get("uploads", []):
                if isinstance(item, dict) and item.get("upload_ref"):
                    item["bytes"] = read_reference(item.get("upload_ref"))
