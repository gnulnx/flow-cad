import hashlib
from pathlib import Path

import pytest

from flow_cad.artifacts.preservation import (
    ArchiveFileExistsError,
    PreservationMismatchError,
    UnsafePreservationPathError,
    build_inventory,
    copy_archive,
    verify_archive,
    write_manifest_atomic,
)


def test_inventory_and_manifest_are_deterministic_and_machine_readable(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    (root / "zeta.bin").write_bytes(b"z")
    (root / "nested").mkdir()
    (root / "nested" / "alpha.txt").write_bytes(b"alpha\n")

    first = build_inventory(root, ["zeta.bin", "nested/alpha.txt", "zeta.bin"])
    second = build_inventory(root, {Path("nested/alpha.txt"), Path("zeta.bin")})

    assert first == second
    assert [entry.path for entry in first.entries] == ["nested/alpha.txt", "zeta.bin"]
    assert first.to_dict() == {
        "file_count": 2,
        "byte_count": 7,
        "entries": [entry.to_dict() for entry in first.entries],
    }
    alpha_digest = hashlib.sha256(b"alpha\n").hexdigest()
    zeta_digest = hashlib.sha256(b"z").hexdigest()
    assert first.manifest_text() == (
        f"{alpha_digest}  nested/alpha.txt\n"
        f"{zeta_digest}  zeta.bin\n"
    )


def test_copy_and_verify_preserve_exact_binary_and_newline_bytes(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    payloads = {
        "binary/model.step": b"\x00\xffISO-10303-21;\r\nEND-ISO-10303-21;\n",
        "text/notes.txt": b"first\r\nsecond\nthird\r",
    }
    for relative_path, payload in payloads.items():
        path = source / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)

    archive = tmp_path / "archive"
    inventory = copy_archive(source, archive, payloads)

    assert inventory.file_count == 2
    assert inventory.byte_count == sum(len(payload) for payload in payloads.values())
    assert inventory.to_dict()["byte_count"] == inventory.byte_count
    for relative_path, payload in payloads.items():
        assert (archive / relative_path).read_bytes() == payload
    assert verify_archive(source, archive, reversed(tuple(payloads))) == inventory


def test_verify_archive_fails_on_first_sorted_mismatch(tmp_path: Path) -> None:
    source = tmp_path / "source"
    archive = tmp_path / "archive"
    source.mkdir()
    archive.mkdir()
    for name in ("a.bin", "b.bin"):
        (source / name).write_bytes(b"source")
        (archive / name).write_bytes(b"different")

    with pytest.raises(PreservationMismatchError) as error_info:
        verify_archive(source, archive, ["b.bin", "a.bin"])

    assert error_info.value.relative_path == "a.bin"
    assert not error_info.value.sha256_matches
    assert not error_info.value.bytes_match


@pytest.mark.parametrize("relative_path", ["/absolute.bin", "../escape.bin", "nested/../../escape.bin"])
def test_inventory_rejects_absolute_and_traversal_paths(
    tmp_path: Path,
    relative_path: str,
) -> None:
    with pytest.raises(UnsafePreservationPathError):
        build_inventory(tmp_path, [relative_path])


def test_inventory_and_archive_reject_symlink_paths(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"outside")
    (source / "linked.bin").symlink_to(outside)

    with pytest.raises(UnsafePreservationPathError):
        build_inventory(source, ["linked.bin"])

    safe_source = source / "linked-parent" / "safe.bin"
    safe_source.parent.mkdir()
    safe_source.write_bytes(b"safe")
    archive = tmp_path / "archive"
    archive.mkdir()
    (archive / "linked-parent").symlink_to(tmp_path, target_is_directory=True)

    with pytest.raises(UnsafePreservationPathError):
        copy_archive(source, archive, ["linked-parent/safe.bin"])


def test_copy_archive_does_not_overwrite_existing_file_by_default(tmp_path: Path) -> None:
    source = tmp_path / "source"
    archive = tmp_path / "archive"
    source.mkdir()
    archive.mkdir()
    (source / "part.bin").write_bytes(b"new bytes")
    destination = archive / "part.bin"
    destination.write_bytes(b"preserve me")

    with pytest.raises(ArchiveFileExistsError):
        copy_archive(source, archive, ["part.bin"])

    assert destination.read_bytes() == b"preserve me"


def test_write_manifest_atomically_replaces_complete_content(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "part.bin").write_bytes(b"part bytes")
    inventory = build_inventory(source, ["part.bin"])
    manifest = tmp_path / "manifests" / "source-manifest.sha256"
    manifest.parent.mkdir()
    manifest.write_text("stale\n", encoding="utf-8")

    write_manifest_atomic(manifest, inventory)

    assert manifest.read_text(encoding="utf-8") == inventory.manifest_text()
    assert list(manifest.parent.glob(f".{manifest.name}.*.tmp")) == []
