from pathlib import Path

from flow_cad.core.exporter import Exporter


class Params:
    project_id = "test_project"


def test_exporter_clear_removes_stale_generated_files(tmp_path: Path) -> None:
    exporter = Exporter(tmp_path, Params(), exports_dir=tmp_path / "exports")
    stale_files = (
        exporter.step_dir / "old" / "part.step",
        exporter.step_dir / "old" / ".part.step.glb",
        exporter.stl_dir / "old" / "part.stl",
        exporter.snapshot_dir / "old" / "part_front.svg",
    )
    for path in stale_files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("stale\n", encoding="utf-8")

    exporter.clear()

    for path in stale_files:
        assert not path.exists()
        assert not path.parent.exists()
