from pathlib import Path
import tarfile

from scripts.create_exports_bundle import create_bundle, should_include


def test_create_exports_bundle_contains_exports_tree(tmp_path: Path, monkeypatch) -> None:
    exports_dir = tmp_path / "exports"
    output_dir = tmp_path / "handoff"
    (exports_dir / "step").mkdir(parents=True)
    (exports_dir / "step" / "part.step").write_text("STEP\n", encoding="utf-8")

    monkeypatch.setattr("scripts.create_exports_bundle.EXPORTS_DIR", exports_dir)

    bundle = create_bundle(output_dir, "test-export")

    assert bundle == output_dir / "test-export.tar.gz"
    with tarfile.open(bundle, "r:gz") as archive:
        assert "exports/step/part.step" in archive.getnames()


def test_create_exports_bundle_excludes_local_junk(tmp_path: Path, monkeypatch) -> None:
    exports_dir = tmp_path / "exports"
    output_dir = tmp_path / "handoff"
    (exports_dir / "step" / ".part.step").mkdir(parents=True)
    (exports_dir / "step" / ".part.step" / "model.glb").write_text("sidecar\n", encoding="utf-8")
    (exports_dir / "step" / ".DS_Store").write_text("junk\n", encoding="utf-8")
    (exports_dir / "freecad").mkdir()
    (exports_dir / "freecad" / "backup.FCBak").write_text("backup\n", encoding="utf-8")
    (exports_dir / "step" / "part.step").write_text("STEP\n", encoding="utf-8")

    monkeypatch.setattr("scripts.create_exports_bundle.EXPORTS_DIR", exports_dir)

    bundle = create_bundle(output_dir, "test-export")

    with tarfile.open(bundle, "r:gz") as archive:
        names = archive.getnames()
    assert "exports/step/part.step" in names
    assert "exports/step/.part.step/model.glb" not in names
    assert "exports/step/.DS_Store" not in names
    assert "exports/freecad/backup.FCBak" not in names


def test_create_exports_bundle_replaces_existing_fixed_bundle(tmp_path: Path, monkeypatch) -> None:
    exports_dir = tmp_path / "exports"
    output_dir = tmp_path
    (exports_dir / "step").mkdir(parents=True)
    (exports_dir / "step" / "part.step").write_text("old\n", encoding="utf-8")

    monkeypatch.setattr("scripts.create_exports_bundle.EXPORTS_DIR", exports_dir)

    bundle = create_bundle(output_dir, "exports.tar.gz")
    (exports_dir / "step" / "part.step").write_text("new\n", encoding="utf-8")
    bundle = create_bundle(output_dir, "exports.tar.gz")

    assert bundle == output_dir / "exports.tar.gz"
    with tarfile.open(bundle, "r:gz") as archive:
        part = archive.extractfile("exports/step/part.step")
        assert part is not None
        assert part.read() == b"new\n"


def test_should_include_keeps_regular_export_paths() -> None:
    assert should_include(Path("exports/step/part.step"), Path("exports"))
    assert not should_include(Path("exports/step/.part.step/model.glb"), Path("exports"))
