from __future__ import annotations

from pathlib import Path

from flow_cad.validation.ownership import (
    OwnershipIssueCode,
    OwnershipScanConfig,
    scan_downstream_ownership,
    scan_ownership,
)


def _write_python(root: Path, relative_path: str, source: str) -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def test_ownership_allows_sdk_and_explicit_helpers(tmp_path: Path) -> None:
    project = tmp_path / "downstream"
    _write_python(
        project,
        "flow_b2/part.py",
        """\
import flow_cad.sdk
from flow_cad import sdk
from flow_cad.sdk import Part
from flow_cad.geometry.helpers import make_box
from pathlib import Path
""",
    )

    result = scan_ownership(
        OwnershipScanConfig(
            downstream_root=project,
            allowed_helper_imports=("flow_cad.geometry.helpers",),
        )
    )

    assert result.ok
    assert result.scanned_files == ("flow_b2/part.py",)
    assert result.to_dict()["issue_count"] == 0


def test_ownership_rejects_flow_cad_internal_imports(tmp_path: Path) -> None:
    project = tmp_path / "downstream"
    _write_python(
        project,
        "flow_b2/bad_imports.py",
        """\
import flow_cad.viewer.service
from flow_cad import project
from flow_cad.registry.models import PartRow
""",
    )

    result = scan_downstream_ownership(project)

    assert not result.ok
    assert [issue.code for issue in result.issues] == [OwnershipIssueCode.FORBIDDEN_IMPORT] * 3
    assert [issue.subject for issue in result.issues] == [
        "flow_cad.viewer.service",
        "flow_cad.project",
        "flow_cad.registry.models",
    ]


def test_ownership_rejects_runtime_class_definitions(tmp_path: Path) -> None:
    project = tmp_path / "downstream"
    _write_python(
        project,
        "flow_b2/runtime_copies.py",
        """\
class PartDefinition:
    pass

class PartRole:
    pass

class B2ViewerService:
    pass

class ProjectCacheModel:
    pass

class GeometryPart:
    pass
""",
    )

    result = scan_downstream_ownership(project)

    assert [issue.subject for issue in result.issues] == [
        "PartDefinition",
        "PartRole",
        "B2ViewerService",
        "ProjectCacheModel",
    ]
    assert all(issue.code is OwnershipIssueCode.FORBIDDEN_DEFINITION for issue in result.issues)


def test_ownership_rejects_hardcoded_flow_cad_checkout_path(tmp_path: Path) -> None:
    project = tmp_path / "downstream"
    _write_python(project, "flow_b2/config.py", 'RUNTIME = "/home/gnulnx/flow-cad/src"\n')

    result = scan_downstream_ownership(project)

    assert result.issue_count == 1
    issue = result.issues[0]
    assert issue.code is OwnershipIssueCode.HARDCODED_RUNTIME_PATH
    assert issue.subject == "/home/gnulnx/flow-cad"
    assert issue.line == 1


def test_ownership_detects_byte_identical_runtime_python_copy(tmp_path: Path) -> None:
    runtime_file = _write_python(tmp_path, "runtime/service.py", "class RuntimeOnly:\n    pass\n")
    project = tmp_path / "downstream"
    copied_file = _write_python(project, "flow_b2/copied_service.py", runtime_file.read_text(encoding="utf-8"))

    result = scan_downstream_ownership(project, runtime_python_files=(runtime_file,))

    assert result.issue_count == 1
    issue = result.issues[0]
    assert issue.code is OwnershipIssueCode.IDENTICAL_RUNTIME_COPY
    assert issue.path == copied_file.relative_to(project).as_posix()
    assert len(issue.sha256 or "") == 64
    assert issue.runtime_matches == (str(runtime_file.resolve()),)


def test_ownership_does_not_silently_exclude_project_directories(tmp_path: Path) -> None:
    project = tmp_path / "downstream"
    directories = (".flow", "migration", "exports", ".venv", "__pycache__", "tests")
    for directory in directories:
        _write_python(project, f"{directory}/violation.py", "import flow_cad.viewer\n")

    default_result = scan_downstream_ownership(project)
    excluded_result = scan_downstream_ownership(project, excluded_paths=directories)

    assert default_result.issue_count == len(directories)
    assert default_result.file_count == len(directories)
    assert excluded_result.ok
    assert excluded_result.file_count == 0


def test_ownership_issue_order_is_deterministic(tmp_path: Path) -> None:
    project = tmp_path / "downstream"
    _write_python(
        project,
        "z_last.py",
        'RUNTIME = "/home/gnulnx/flow-cad"\nimport flow_cad.viewer\n',
    )
    _write_python(project, "a_first.py", "class PartRole:\n    pass\n")

    first = scan_downstream_ownership(project)
    second = scan_downstream_ownership(project)

    first_keys = [(issue.path, issue.line, issue.code, issue.subject) for issue in first.issues]
    second_keys = [(issue.path, issue.line, issue.code, issue.subject) for issue in second.issues]
    assert first_keys == second_keys
    assert first_keys == [
        ("a_first.py", 1, OwnershipIssueCode.FORBIDDEN_DEFINITION, "PartRole"),
        ("z_last.py", 1, OwnershipIssueCode.HARDCODED_RUNTIME_PATH, "/home/gnulnx/flow-cad"),
        ("z_last.py", 2, OwnershipIssueCode.FORBIDDEN_IMPORT, "flow_cad.viewer"),
    ]
