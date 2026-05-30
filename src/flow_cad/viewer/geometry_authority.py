from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal


DISPLAY_MESH_CONTRACT_VERSION = 1
SNAP_FEATURE_SCHEMA_VERSION = 2
SNAP_EXTRACTOR_CONTRACT_VERSION = 1

SourceKind = Literal["flow_python", "step", "stl", "missing"]
GeometryAuthority = Literal["step_kernel", "mesh", "missing"]
QualityLabel = Literal["exact", "approximate", "missing"]


class GeometryAuthorityError(RuntimeError):
    """Raised when kernel-backed geometry authority operations are unavailable."""


@dataclass(frozen=True)
class GeometryCapabilities:
    display_mesh: bool
    mesh_metrics: bool
    exact_topology: bool
    exact_snap: bool
    exact_measurement: bool
    approximate_measurement: bool
    exact_editing: bool
    mesh_only: bool


@dataclass(frozen=True)
class PartGeometry:
    source_kind: SourceKind
    geometry_authority: GeometryAuthority
    quality_label: QualityLabel
    capabilities: GeometryCapabilities
    warnings: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "source_kind": self.source_kind,
            "geometry_authority": self.geometry_authority,
            "quality_label": self.quality_label,
            "capabilities": asdict(self.capabilities),
            "warnings": list(self.warnings),
        }


STEP_FLOW_GEOMETRY = PartGeometry(
    source_kind="flow_python",
    geometry_authority="step_kernel",
    quality_label="exact",
    capabilities=GeometryCapabilities(
        display_mesh=True,
        mesh_metrics=True,
        exact_topology=True,
        exact_snap=True,
        exact_measurement=True,
        approximate_measurement=False,
        exact_editing=False,
        mesh_only=False,
    ),
)

STL_MESH_GEOMETRY = PartGeometry(
    source_kind="stl",
    geometry_authority="mesh",
    quality_label="approximate",
    capabilities=GeometryCapabilities(
        display_mesh=True,
        mesh_metrics=True,
        exact_topology=False,
        exact_snap=False,
        exact_measurement=False,
        approximate_measurement=True,
        exact_editing=False,
        mesh_only=True,
    ),
    warnings=(
        "STL-only mesh: viewing and approximate mesh measurements are available; exact CAD editing is disabled.",
    ),
)

MISSING_GEOMETRY = PartGeometry(
    source_kind="missing",
    geometry_authority="missing",
    quality_label="missing",
    capabilities=GeometryCapabilities(
        display_mesh=False,
        mesh_metrics=False,
        exact_topology=False,
        exact_snap=False,
        exact_measurement=False,
        approximate_measurement=False,
        exact_editing=False,
        mesh_only=False,
    ),
    warnings=("No generated STEP or STL artifact is available. Run `flow cad build` first.",),
)


def geometry_for_artifact(source_format: str | None) -> PartGeometry:
    if source_format == "step":
        return STEP_FLOW_GEOMETRY
    if source_format == "stl":
        return STL_MESH_GEOMETRY
    return MISSING_GEOMETRY


def display_mesh_cache_metadata(source_path: Path) -> dict[str, Any]:
    return {
        "contract_version": DISPLAY_MESH_CONTRACT_VERSION,
        "source_path": str(source_path),
        "source_mtime_ns": source_path.stat().st_mtime_ns,
        "source_size": source_path.stat().st_size,
    }


def snap_feature_cache_metadata(source_path: Path) -> dict[str, Any]:
    return {
        "schema_version": SNAP_FEATURE_SCHEMA_VERSION,
        "extractor_contract_version": SNAP_EXTRACTOR_CONTRACT_VERSION,
        "source_path": str(source_path),
        "source_mtime_ns": source_path.stat().st_mtime_ns,
        "source_size": source_path.stat().st_size,
    }


def cache_metadata_matches(payload: dict[str, Any], expected: dict[str, Any]) -> bool:
    return all(payload.get(key) == value for key, value in expected.items())


def extract_step_snap_features(step_path: Path) -> dict[str, Any]:
    """Extract authoritative snap targets from STEP topology."""
    try:
        from build123d import import_step
    except Exception as exc:  # pragma: no cover - depends on local CAD install
        raise GeometryAuthorityError(
            "STEP snap extraction requires build123d/OCP. Install project dependencies or configure the CAD environment."
        ) from exc

    try:
        shape = import_step(step_path)
    except Exception:
        return _empty_step_payload(step_path, f"Could not extract snap features from STEP file: {step_path.name}")

    try:
        vertices = shape.vertices()
        edges = shape.edges()
    except Exception:
        return _empty_step_payload(step_path, f"Could not read topology from STEP file: {step_path.name}")

    features: list[dict[str, Any]] = []

    for vertex in vertices:
        try:
            point = _vector_to_float_tuple(vertex.center())
        except Exception:
            continue
        features.append(
            _feature(
                {
                    "kind": "vertex",
                    "label": "Vertex",
                    "point": _as_float_tuple(point),
                }
            )
        )

    for edge in edges:
        try:
            geom_type = getattr(getattr(edge, "geom_type", None), "name", str(getattr(edge, "geom_type", ""))).lower()
            length = float(edge.length)
        except Exception:
            continue

        if geom_type == "line":
            try:
                start = _vector_to_float_tuple(edge.position_at(0))
                end = _vector_to_float_tuple(edge.position_at(1))
                midpoint = _vector_to_float_tuple(edge.position_at(0.5))
            except Exception:
                continue
            features.append(
                _feature(
                    {
                        "kind": "line_edge",
                        "label": "Line Edge",
                        "start": _as_float_tuple(start),
                        "end": _as_float_tuple(end),
                        "point": _as_float_tuple(midpoint),
                        "length": length,
                    }
                )
            )
            features.append(
                _feature(
                    {
                        "kind": "edge_midpoint",
                        "label": "Edge Midpoint",
                        "point": _as_float_tuple(midpoint),
                        "edge_start": _as_float_tuple(start),
                        "edge_end": _as_float_tuple(end),
                    }
                )
            )
        elif geom_type == "circle":
            try:
                center = _vector_to_float_tuple(edge.arc_center)
                radius = float(edge.radius)
                ring_points = [
                    _as_float_tuple(_vector_to_float_tuple(edge.position_at(position)))
                    for position in (0.0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875)
                ]
            except Exception:
                continue
            features.append(
                _feature(
                    {
                        "kind": "circle_center",
                        "label": "Circle Center",
                        "point": _as_float_tuple(center),
                        "ring_points": ring_points,
                        "radius": radius,
                        "length": length,
                    }
                )
            )

    sorted_features = sorted(features, key=_snap_feature_sort_key)
    for index, feature in enumerate(sorted_features):
        feature["id"] = _snap_feature_id(index, feature)

    return {
        **snap_feature_cache_metadata(step_path),
        "source_format": "step",
        "features": sorted_features,
        "warnings": [] if sorted_features else [f"No snap features found in STEP file: {step_path.name}"],
    }


def _empty_step_payload(step_path: Path, warning: str) -> dict[str, Any]:
    return {
        **snap_feature_cache_metadata(step_path),
        "source_format": "step",
        "features": [],
        "warnings": [warning],
    }


def _feature(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        **payload,
        "source": "step_topology",
        "quality": "exact",
        "quality_label": "Exact",
    }


def _vector_to_float_tuple(vector: Any) -> tuple[float, float, float]:
    return (float(vector.X), float(vector.Y), float(vector.Z))


def _as_float_tuple(values: tuple[float, float, float]) -> list[float]:
    return [float(values[0]), float(values[1]), float(values[2])]


def _snap_feature_sort_key(feature: dict[str, Any]) -> tuple[Any, ...]:
    point = tuple(round(float(value), 5) for value in feature.get("point", [0.0, 0.0, 0.0]))
    start = tuple(round(float(value), 5) for value in feature.get("start", feature.get("edge_start", point)))
    end = tuple(round(float(value), 5) for value in feature.get("end", feature.get("edge_end", point)))
    return (feature["kind"], point, start, end, round(float(feature.get("radius", 0.0)), 5))


def _snap_feature_id(index: int, feature: dict[str, Any]) -> str:
    point = "_".join(f"{float(value):.4f}" for value in feature.get("point", [0.0, 0.0, 0.0]))
    return f"{feature['kind']}:{index}:{point}"
