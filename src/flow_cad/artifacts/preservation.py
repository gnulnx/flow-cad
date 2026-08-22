"""Generic, byte-exact source and artifact preservation primitives."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


_COPY_CHUNK_SIZE = 1024 * 1024


class PreservationError(RuntimeError):
    """Base error for preservation operations."""


class UnsafePreservationPathError(PreservationError, ValueError):
    """Raised when a requested path could escape or follow a symlink."""


class ArchiveFileExistsError(PreservationError, FileExistsError):
    """Raised when an archive copy would overwrite an existing path."""


class PreservationMismatchError(PreservationError):
    """Raised for the first source/archive byte mismatch."""

    def __init__(
        self,
        relative_path: str,
        *,
        sha256_matches: bool,
        bytes_match: bool,
    ) -> None:
        self.relative_path = relative_path
        self.sha256_matches = sha256_matches
        self.bytes_match = bytes_match
        super().__init__(
            f"preservation mismatch for {relative_path}: "
            f"sha256_matches={sha256_matches}, bytes_match={bytes_match}"
        )


@dataclass(frozen=True, slots=True)
class ManifestEntry:
    """One deterministic SHA-256 manifest entry."""

    path: str
    sha256: str
    byte_count: int

    def manifest_line(self) -> str:
        return f"{self.sha256}  {self.path}"

    def to_dict(self) -> dict[str, str | int]:
        return {
            "path": self.path,
            "sha256": self.sha256,
            "byte_count": self.byte_count,
        }


@dataclass(frozen=True, slots=True)
class PreservationInventory:
    """A machine-readable inventory for an explicit set of regular files."""

    entries: tuple[ManifestEntry, ...]

    @property
    def file_count(self) -> int:
        return len(self.entries)

    @property
    def byte_count(self) -> int:
        return sum(entry.byte_count for entry in self.entries)

    def manifest_text(self) -> str:
        if not self.entries:
            return ""
        return "\n".join(entry.manifest_line() for entry in self.entries) + "\n"

    def to_dict(self) -> dict[str, object]:
        return {
            "file_count": self.file_count,
            "byte_count": self.byte_count,
            "entries": [entry.to_dict() for entry in self.entries],
        }


def build_inventory(
    root: str | os.PathLike[str],
    relative_paths: Iterable[str | os.PathLike[str]],
) -> PreservationInventory:
    """Hash an explicit set of safe, repo-relative regular files."""

    root_path = _require_directory(root)
    normalized_paths = _normalize_relative_paths(relative_paths)
    entries = tuple(
        _manifest_entry(root_path, relative_path)
        for relative_path in normalized_paths
    )
    return PreservationInventory(entries=entries)


def write_manifest_atomic(
    manifest_path: str | os.PathLike[str],
    inventory: PreservationInventory,
) -> None:
    """Atomically write a standard sorted SHA-256 manifest."""

    destination = Path(manifest_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(inventory.manifest_text())
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, destination)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def copy_archive(
    source_root: str | os.PathLike[str],
    archive_root: str | os.PathLike[str],
    relative_paths: Iterable[str | os.PathLike[str]],
    *,
    overwrite: bool = False,
) -> PreservationInventory:
    """Copy explicit files byte-for-byte and verify every copied pair."""

    source_path = _require_directory(source_root)
    normalized_paths = _normalize_relative_paths(relative_paths)
    inventory = build_inventory(source_path, normalized_paths)
    archive_path = _prepare_archive_root(archive_root)

    for relative_path in normalized_paths:
        source = _require_regular_file(source_path, relative_path)
        destination = _archive_destination(archive_path, relative_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        _reject_symlink_components(archive_path, relative_path.parent)
        _copy_file(source, destination, overwrite=overwrite)
        _verify_pair(source, destination, relative_path.as_posix())

    return inventory


def verify_archive(
    source_root: str | os.PathLike[str],
    archive_root: str | os.PathLike[str],
    relative_paths: Iterable[str | os.PathLike[str]],
) -> PreservationInventory:
    """Verify each sorted source/archive pair by SHA-256 and byte comparison."""

    source_path = _require_directory(source_root)
    archive_path = _require_directory(archive_root)
    normalized_paths = _normalize_relative_paths(relative_paths)
    inventory = build_inventory(source_path, normalized_paths)

    for relative_path in normalized_paths:
        source = _require_regular_file(source_path, relative_path)
        archived = _require_regular_file(archive_path, relative_path)
        _verify_pair(source, archived, relative_path.as_posix())

    return inventory


def _normalize_relative_paths(
    relative_paths: Iterable[str | os.PathLike[str]],
) -> tuple[Path, ...]:
    normalized: set[Path] = set()
    for value in relative_paths:
        path = Path(value)
        if path.is_absolute() or not path.parts or path == Path("."):
            raise UnsafePreservationPathError(
                f"preservation paths must be non-empty and relative: {value!s}"
            )
        if ".." in path.parts:
            raise UnsafePreservationPathError(
                f"preservation paths may not traverse parents: {value!s}"
            )
        normalized.add(path)
    return tuple(sorted(normalized, key=lambda path: path.as_posix()))


def _absolute_without_resolving(path: Path) -> Path:
    if path.is_absolute():
        return path
    return Path.cwd() / path


def _require_directory(root: str | os.PathLike[str]) -> Path:
    path = _absolute_without_resolving(Path(root))
    if path.is_symlink():
        raise UnsafePreservationPathError(f"preservation root may not be a symlink: {path}")
    if not path.is_dir():
        raise PreservationError(f"preservation root is not a directory: {path}")
    return path


def _prepare_archive_root(root: str | os.PathLike[str]) -> Path:
    path = _absolute_without_resolving(Path(root))
    if path.is_symlink():
        raise UnsafePreservationPathError(f"archive root may not be a symlink: {path}")
    path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir():
        raise PreservationError(f"archive root is not a directory: {path}")
    return path


def _reject_symlink_components(root: Path, relative_path: Path) -> None:
    current = root
    for part in relative_path.parts:
        current = current / part
        if current.is_symlink():
            raise UnsafePreservationPathError(
                f"preservation paths may not contain symlinks: {relative_path.as_posix()}"
            )


def _require_regular_file(root: Path, relative_path: Path) -> Path:
    _reject_symlink_components(root, relative_path)
    candidate = root / relative_path
    if not candidate.is_file():
        raise PreservationError(
            f"preservation path is not a regular file: {relative_path.as_posix()}"
        )
    return candidate


def _archive_destination(root: Path, relative_path: Path) -> Path:
    _reject_symlink_components(root, relative_path)
    return root / relative_path


def _manifest_entry(root: Path, relative_path: Path) -> ManifestEntry:
    file_path = _require_regular_file(root, relative_path)
    return ManifestEntry(
        path=relative_path.as_posix(),
        sha256=_sha256(file_path),
        byte_count=file_path.stat().st_size,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_COPY_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _files_equal(left: Path, right: Path) -> bool:
    try:
        result = subprocess.run(
            ["cmp", "-s", "--", str(left), str(right)],
            check=False,
        )
    except FileNotFoundError as error:
        raise PreservationError(
            "byte verification requires the `cmp` command to be installed"
        ) from error
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    raise PreservationError(
        f"cmp failed while verifying {left} and {right} (exit {result.returncode})"
    )


def _copy_file(source: Path, destination: Path, *, overwrite: bool) -> None:
    if destination.is_symlink():
        raise UnsafePreservationPathError(
            f"archive destination may not be a symlink: {destination}"
        )
    if destination.exists() and not overwrite:
        raise ArchiveFileExistsError(f"archive file already exists: {destination}")

    if overwrite:
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
        )
        temporary_path = Path(temporary_name)
        try:
            with source.open("rb") as source_handle, os.fdopen(
                file_descriptor, "wb"
            ) as destination_handle:
                shutil.copyfileobj(source_handle, destination_handle, _COPY_CHUNK_SIZE)
                destination_handle.flush()
                os.fsync(destination_handle.fileno())
            os.replace(temporary_path, destination)
        except BaseException:
            temporary_path.unlink(missing_ok=True)
            raise
        return

    try:
        with source.open("rb") as source_handle, destination.open("xb") as destination_handle:
            shutil.copyfileobj(source_handle, destination_handle, _COPY_CHUNK_SIZE)
            destination_handle.flush()
            os.fsync(destination_handle.fileno())
    except FileExistsError as error:
        raise ArchiveFileExistsError(f"archive file already exists: {destination}") from error
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


def _verify_pair(source: Path, archived: Path, relative_path: str) -> None:
    sha256_matches = _sha256(source) == _sha256(archived)
    bytes_match = _files_equal(source, archived)
    if not sha256_matches or not bytes_match:
        raise PreservationMismatchError(
            relative_path,
            sha256_matches=sha256_matches,
            bytes_match=bytes_match,
        )
