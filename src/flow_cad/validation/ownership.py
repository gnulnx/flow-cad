from __future__ import annotations

import ast
import hashlib
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any


FLOW_CAD_RUNTIME_PATH = "/home/gnulnx/flow-cad"
DEFAULT_ALLOWED_IMPORT_PREFIXES = ("flow_cad.sdk",)
DEFAULT_FORBIDDEN_DEFINITION_NAMES = frozenset(
    {
        "PartDefinition",
        "PartRole",
        "RegistryService",
        "RegistryModel",
        "CacheService",
        "CacheModel",
        "BuildService",
        "BuildOrchestrator",
        "ViewerService",
        "ViewerRouter",
        "ExportService",
        "Exporter",
    }
)

_RUNTIME_CLASS_DOMAINS = ("registry", "cache", "build", "viewer", "export")
_RUNTIME_CLASS_ROLES = (
    "service",
    "model",
    "store",
    "database",
    "manager",
    "orchestrator",
    "router",
    "route",
    "api",
    "registry",
    "cache",
    "builder",
    "job",
    "exporter",
)


class OwnershipIssueCode(StrEnum):
    FORBIDDEN_IMPORT = "forbidden_import"
    FORBIDDEN_DEFINITION = "forbidden_definition"
    HARDCODED_RUNTIME_PATH = "hardcoded_runtime_path"
    IDENTICAL_RUNTIME_COPY = "identical_runtime_copy"
    SYNTAX_ERROR = "syntax_error"


@dataclass(frozen=True)
class OwnershipIssue:
    code: OwnershipIssueCode
    path: str
    message: str
    line: int | None = None
    column: int | None = None
    subject: str | None = None
    sha256: str | None = None
    runtime_matches: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": str(self.code),
            "path": self.path,
            "line": self.line,
            "column": self.column,
            "subject": self.subject,
            "message": self.message,
            "sha256": self.sha256,
            "runtime_matches": list(self.runtime_matches),
        }


@dataclass(frozen=True)
class OwnershipScanResult:
    root: Path
    scanned_files: tuple[str, ...]
    issues: tuple[OwnershipIssue, ...]

    @property
    def ok(self) -> bool:
        return not self.issues

    @property
    def file_count(self) -> int:
        return len(self.scanned_files)

    @property
    def issue_count(self) -> int:
        return len(self.issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "root": str(self.root),
            "file_count": self.file_count,
            "scanned_files": list(self.scanned_files),
            "issue_count": self.issue_count,
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass(frozen=True)
class OwnershipScanConfig:
    downstream_root: Path
    allowed_helper_imports: tuple[str, ...] = ()
    excluded_paths: tuple[str | Path, ...] = ()
    runtime_python_files: tuple[Path, ...] = ()
    forbidden_definition_names: frozenset[str] = DEFAULT_FORBIDDEN_DEFINITION_NAMES


def scan_ownership(config: OwnershipScanConfig) -> OwnershipScanResult:
    """Scan a downstream project without importing or executing its Python code.

    Nothing is excluded implicitly. Callers that do not want local state,
    migration archives, exports, virtual environments, caches, or tests scanned
    must name those paths in ``excluded_paths``.
    """

    return scan_downstream_ownership(
        config.downstream_root,
        allowed_helper_imports=config.allowed_helper_imports,
        excluded_paths=config.excluded_paths,
        runtime_python_files=config.runtime_python_files,
        forbidden_definition_names=config.forbidden_definition_names,
    )


def scan_downstream_ownership(
    downstream_root: Path,
    *,
    allowed_helper_imports: Iterable[str] = (),
    excluded_paths: Iterable[str | Path] = (),
    runtime_python_files: Iterable[Path] = (),
    forbidden_definition_names: Iterable[str] = DEFAULT_FORBIDDEN_DEFINITION_NAMES,
) -> OwnershipScanResult:
    root = downstream_root.resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"Downstream project root is not a directory: {root}")

    allowed_prefixes = _normalized_allowed_prefixes(allowed_helper_imports)
    resolved_exclusions = tuple(
        sorted({_resolve_from_root(root, path) for path in excluded_paths}, key=str)
    )
    forbidden_names = frozenset(str(name).strip() for name in forbidden_definition_names if str(name).strip())
    runtime_hashes = _runtime_hash_index(runtime_python_files)
    source_paths = tuple(
        path
        for path in sorted(root.rglob("*.py"), key=lambda candidate: candidate.relative_to(root).as_posix())
        if path.is_file() and not _is_excluded(path, resolved_exclusions)
    )

    issues: list[OwnershipIssue] = []
    scanned_files: list[str] = []
    for source_path in source_paths:
        relative_path = source_path.relative_to(root).as_posix()
        scanned_files.append(relative_path)
        source_bytes = source_path.read_bytes()
        digest = hashlib.sha256(source_bytes).hexdigest()
        matches = runtime_hashes.get(digest, ()) if source_bytes.strip() else ()
        if matches:
            issues.append(
                OwnershipIssue(
                    code=OwnershipIssueCode.IDENTICAL_RUNTIME_COPY,
                    path=relative_path,
                    subject=relative_path,
                    sha256=digest,
                    runtime_matches=matches,
                    message=(
                        f"Downstream Python file is byte-identical to Flow CAD runtime file: "
                        f"{', '.join(matches)}"
                    ),
                )
            )

        try:
            source_text = source_bytes.decode("utf-8")
            tree = ast.parse(source_text, filename=str(source_path))
        except (SyntaxError, UnicodeDecodeError) as exc:
            issues.append(_syntax_issue(relative_path, exc))
            continue

        issues.extend(
            _ast_issues(
                tree,
                path=relative_path,
                allowed_prefixes=allowed_prefixes,
                forbidden_definition_names=forbidden_names,
            )
        )

    ordered_issues = tuple(sorted(issues, key=_issue_sort_key))
    return OwnershipScanResult(
        root=root,
        scanned_files=tuple(scanned_files),
        issues=ordered_issues,
    )


def _normalized_allowed_prefixes(allowed_helper_imports: Iterable[str]) -> tuple[str, ...]:
    prefixes = set(DEFAULT_ALLOWED_IMPORT_PREFIXES)
    for value in allowed_helper_imports:
        prefix = str(value).strip().rstrip(".")
        if prefix:
            prefixes.add(prefix)
    return tuple(sorted(prefixes))


def _resolve_from_root(root: Path, path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    return candidate.resolve()


def _is_excluded(path: Path, exclusions: tuple[Path, ...]) -> bool:
    resolved = path.resolve()
    return any(resolved == excluded or resolved.is_relative_to(excluded) for excluded in exclusions)


def _runtime_hash_index(runtime_python_files: Iterable[Path]) -> dict[str, tuple[str, ...]]:
    indexed: dict[str, list[str]] = defaultdict(list)
    resolved_paths = sorted({Path(path).resolve() for path in runtime_python_files}, key=str)
    for path in resolved_paths:
        if not path.is_file():
            raise FileNotFoundError(f"Runtime Python file does not exist: {path}")
        if path.suffix != ".py":
            raise ValueError(f"Runtime copy reference must be a Python file: {path}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        indexed[digest].append(str(path))
    return {digest: tuple(paths) for digest, paths in indexed.items()}


def _ast_issues(
    tree: ast.AST,
    *,
    path: str,
    allowed_prefixes: tuple[str, ...],
    forbidden_definition_names: frozenset[str],
) -> list[OwnershipIssue]:
    issues: list[OwnershipIssue] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                issues.extend(_import_issues(alias.name, alias, path, allowed_prefixes))
        elif isinstance(node, ast.ImportFrom):
            issues.extend(_from_import_issues(node, path, allowed_prefixes))
        elif isinstance(node, ast.ClassDef) and _is_forbidden_runtime_class(node.name, forbidden_definition_names):
            issues.append(
                OwnershipIssue(
                    code=OwnershipIssueCode.FORBIDDEN_DEFINITION,
                    path=path,
                    line=node.lineno,
                    column=node.col_offset + 1,
                    subject=node.name,
                    message=f"Downstream project defines forbidden Flow CAD runtime class: {node.name}",
                )
            )
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and FLOW_CAD_RUNTIME_PATH in node.value:
            issues.append(
                OwnershipIssue(
                    code=OwnershipIssueCode.HARDCODED_RUNTIME_PATH,
                    path=path,
                    line=getattr(node, "lineno", None),
                    column=getattr(node, "col_offset", -1) + 1,
                    subject=FLOW_CAD_RUNTIME_PATH,
                    message=f"Downstream project hardcodes Flow CAD checkout path: {FLOW_CAD_RUNTIME_PATH}",
                )
            )
    return issues


def _import_issues(
    module: str,
    node: ast.AST,
    path: str,
    allowed_prefixes: tuple[str, ...],
) -> list[OwnershipIssue]:
    if not _is_flow_cad_module(module) or _module_is_allowed(module, allowed_prefixes):
        return []
    return [_forbidden_import_issue(module, node, path)]


def _from_import_issues(
    node: ast.ImportFrom,
    path: str,
    allowed_prefixes: tuple[str, ...],
) -> list[OwnershipIssue]:
    if node.level or not node.module or not _is_flow_cad_module(node.module):
        return []
    if node.module != "flow_cad":
        return _import_issues(node.module, node, path, allowed_prefixes)

    issues: list[OwnershipIssue] = []
    for alias in node.names:
        imported_module = f"flow_cad.{alias.name}"
        if not _module_is_allowed(imported_module, allowed_prefixes):
            issues.append(_forbidden_import_issue(imported_module, alias, path))
    return issues


def _is_flow_cad_module(module: str) -> bool:
    return module == "flow_cad" or module.startswith("flow_cad.")


def _module_is_allowed(module: str, allowed_prefixes: tuple[str, ...]) -> bool:
    return any(module == prefix or module.startswith(f"{prefix}.") for prefix in allowed_prefixes)


def _forbidden_import_issue(module: str, node: ast.AST, path: str) -> OwnershipIssue:
    return OwnershipIssue(
        code=OwnershipIssueCode.FORBIDDEN_IMPORT,
        path=path,
        line=getattr(node, "lineno", None),
        column=getattr(node, "col_offset", -1) + 1,
        subject=module,
        message=(
            f"Downstream project imports Flow CAD internal module '{module}'; "
            "only flow_cad.sdk and explicitly allowed helper modules are permitted"
        ),
    )


def _is_forbidden_runtime_class(name: str, explicit_names: frozenset[str]) -> bool:
    if name in explicit_names:
        return True
    normalized = "".join(character.lower() for character in name if character.isalnum())
    return (
        any(domain in normalized for domain in _RUNTIME_CLASS_DOMAINS)
        and any(normalized.endswith(role) for role in _RUNTIME_CLASS_ROLES)
    )


def _syntax_issue(path: str, exc: SyntaxError | UnicodeDecodeError) -> OwnershipIssue:
    if isinstance(exc, SyntaxError):
        line = exc.lineno
        column = exc.offset
        detail = exc.msg
    else:
        line = None
        column = None
        detail = str(exc)
    return OwnershipIssue(
        code=OwnershipIssueCode.SYNTAX_ERROR,
        path=path,
        line=line,
        column=column,
        message=f"Could not parse downstream Python file for ownership validation: {detail}",
    )


def _issue_sort_key(issue: OwnershipIssue) -> tuple[Any, ...]:
    return (
        issue.path,
        issue.line if issue.line is not None else 0,
        issue.column if issue.column is not None else 0,
        str(issue.code),
        issue.subject or "",
        issue.runtime_matches,
        issue.message,
    )
