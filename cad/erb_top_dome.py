#!/usr/bin/env python3
"""Parametric STEP generator for Erb top dome prototypes.

These are visual/fit prototypes for a removable R2D2-like hollow dome that
could mount to the existing 240 x 240 mm top plate footprint. Dimensions are
millimeters.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("XDG_CACHE_HOME", "/tmp/erb-balance-bot-cad-cache")
Path(os.environ["XDG_CACHE_HOME"]).mkdir(parents=True, exist_ok=True)

from build123d import Box, Compound, Cylinder, Location, Sphere, chamfer, export_step  # noqa: E402


@dataclass(frozen=True)
class TopDomeParams:
    dome_outer_radius: float = 112.0
    wall_thickness: float = 3.5
    rim_skirt_height: float = 22.0

    flange_width: float = 240.0
    flange_depth: float = 240.0
    flange_thickness: float = 6.0
    flange_corner_hole_offset: float = 100.0
    flange_m4_clearance_diameter: float = 4.5
    flange_counterbore_diameter: float = 9.0
    flange_counterbore_depth: float = 2.0

    front_camera_center_z: float = 58.0
    front_camera_cut_diameter: float = 26.0

    top_sensor_pad_diameter: float = 64.0
    top_sensor_pad_height: float = 12.0
    top_sensor_pad_embed_depth: float = 8.0
    top_sensor_cut_diameter: float = 48.0

    side_service_port_width: float = 28.0
    side_service_port_height: float = 18.0
    side_service_port_center_z: float = 42.0
    side_service_port_y: float = 82.0

    def inner_radius(self) -> float:
        return self.dome_outer_radius - self.wall_thickness

    def flange_inner_cut_radius(self) -> float:
        # Slightly smaller than the inner shell radius so the flange leaves a
        # real annular ledge for strength and for future gasket/lip features.
        return self.inner_radius() - 2.0


P = TopDomeParams()

STEP_DIR = PROJECT_ROOT / "exports" / "step"
REPORT_DIR = PROJECT_ROOT / "reports"

PART_FILENAMES = {
    "plain": "erb_top_dome_plain.step",
    "sensor_mockup": "erb_top_dome_sensor_mockup.step",
    "prototypes": "erb_top_dome_prototypes.step",
}


def solid(shape):
    return shape if hasattr(shape, "bounding_box") else Compound(children=list(shape))


def fused(*shapes):
    result = solid(shapes[0])
    for shape in shapes[1:]:
        result = solid(result.fuse(solid(shape)))
    try:
        return result.clean()
    except Exception:
        return result


def box_at(size: tuple[float, float, float], center: tuple[float, float, float]):
    return Box(*size).moved(Location(center))


def cyl_x(radius: float, length: float, center: tuple[float, float, float]):
    return Cylinder(radius, length, rotation=(0, 90, 0)).moved(Location(center))


def cyl_y(radius: float, length: float, center: tuple[float, float, float]):
    return Cylinder(radius, length, rotation=(90, 0, 0)).moved(Location(center))


def cyl_z(radius: float, length: float, center: tuple[float, float, float]):
    return Cylinder(radius, length).moved(Location(center))


def safe_chamfer(shape, amount: float):
    fallback = solid(shape)
    try:
        chamfered = chamfer(fallback.edges(), amount)
        return solid(chamfered)
    except Exception:
        return fallback


def make_dome_shell():
    cut_below = box_at(
        (P.dome_outer_radius * 3.0, P.dome_outer_radius * 3.0, P.dome_outer_radius * 3.0),
        (0.0, 0.0, -P.dome_outer_radius * 1.35),
    )
    shell = solid(Sphere(P.dome_outer_radius) - Sphere(P.inner_radius()) - cut_below)
    skirt = cyl_z(
        P.dome_outer_radius,
        P.rim_skirt_height,
        (0.0, 0.0, P.rim_skirt_height / 2.0),
    )
    skirt -= cyl_z(
        P.inner_radius(),
        P.rim_skirt_height + 2.0,
        (0.0, 0.0, P.rim_skirt_height / 2.0),
    )
    return fused(shell, skirt)


def make_mounting_flange():
    flange = box_at(
        (P.flange_width, P.flange_depth, P.flange_thickness),
        (0.0, 0.0, P.flange_thickness / 2.0),
    )
    flange -= cyl_z(
        P.flange_inner_cut_radius(),
        P.flange_thickness + 4.0,
        (0.0, 0.0, P.flange_thickness / 2.0),
    )

    for x in (-P.flange_corner_hole_offset, P.flange_corner_hole_offset):
        for y in (-P.flange_corner_hole_offset, P.flange_corner_hole_offset):
            flange -= cyl_z(
                P.flange_m4_clearance_diameter / 2.0,
                P.flange_thickness + 6.0,
                (x, y, P.flange_thickness / 2.0),
            )
            flange -= cyl_z(
                P.flange_counterbore_diameter / 2.0,
                P.flange_counterbore_depth,
                (x, y, P.flange_thickness - P.flange_counterbore_depth / 2.0),
            )

    return solid(flange)


def make_plain_dome():
    dome = fused(make_dome_shell(), make_mounting_flange())
    return safe_chamfer(dome, 0.55)


def make_sensor_mockup_dome():
    dome = make_plain_dome()

    # Front camera aperture only. The earlier blocky external pad was useful
    # for scale, but it is not a credible final support strategy.
    dome = solid(dome - cyl_y(
        P.front_camera_cut_diameter / 2.0,
        P.wall_thickness + 28.0,
        (0.0, -P.dome_outer_radius, P.front_camera_center_z),
    ))

    # Top circular LiDAR/sensor hard point and through opening.
    top_pad_z = P.dome_outer_radius - P.top_sensor_pad_embed_depth + P.top_sensor_pad_height / 2.0
    dome = fused(dome, cyl_z(P.top_sensor_pad_diameter / 2.0, P.top_sensor_pad_height, (0.0, 0.0, top_pad_z)))
    dome = solid(dome - cyl_z(
        P.top_sensor_cut_diameter / 2.0,
        P.wall_thickness + P.top_sensor_pad_height + 24.0,
        (0.0, 0.0, P.dome_outer_radius),
    ))

    # Two small side service/cable ports, useful for judging whether side holes
    # make the dome look too busy.
    for x in (-P.dome_outer_radius, P.dome_outer_radius):
        dome = solid(dome - box_at(
            (
                P.wall_thickness + 18.0,
                P.side_service_port_width,
                P.side_service_port_height,
            ),
            (x, P.side_service_port_y, P.side_service_port_center_z),
        ))

    return safe_chamfer(dome, 0.55)


def make_prototype_pair(parts: dict[str, object]):
    plain = parts["plain"].moved(Location((-150.0, 0.0, 0.0)))
    sensor = parts["sensor_mockup"].moved(Location((150.0, 0.0, 0.0)))
    return Compound(children=[plain, sensor], label="erb_top_dome_prototypes")


def bbox_dims(shape) -> tuple[float, float, float]:
    bb = shape.bounding_box()
    return (bb.max.X - bb.min.X, bb.max.Y - bb.min.Y, bb.max.Z - bb.min.Z)


def assert_printable(name: str, shape) -> None:
    dims = bbox_dims(solid(shape))
    if any(dim > 250.0 for dim in dims):
        rounded = tuple(round(d, 2) for d in dims)
        raise ValueError(f"{name} exceeds 250 mm build volume: {rounded}")


def export_shape(shape, filename: str) -> Path:
    STEP_DIR.mkdir(parents=True, exist_ok=True)
    path = STEP_DIR / filename
    ok = export_step(solid(shape), path)
    if not ok:
        raise RuntimeError(f"STEP export failed: {path}")
    return path


def clear_generated_steps() -> None:
    STEP_DIR.mkdir(parents=True, exist_ok=True)
    for path in STEP_DIR.glob("erb_top_dome*.step"):
        path.unlink()


def write_report(parts: dict[str, object], exported: list[Path]) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / "top_dome_prototype_report.txt"

    plain_dims = bbox_dims(parts["plain"])
    sensor_dims = bbox_dims(parts["sensor_mockup"])

    lines = [
        "Erb top dome prototype CAD report",
        "=================================",
        "",
        "Prototype intent:",
        "- Visual/fit study for a removable R2D2-like hollow top dome.",
        "- Not yet a final structural or sensor-mount design.",
        "",
        "Final outer dimensions:",
        f"- Plain dome: {plain_dims[0]:.1f} W x {plain_dims[1]:.1f} D x {plain_dims[2]:.1f} H mm",
        f"- Sensor mockup dome: {sensor_dims[0]:.1f} W x {sensor_dims[1]:.1f} D x {sensor_dims[2]:.1f} H mm",
        "",
        "Design parameters:",
        f"- Dome outside radius: {P.dome_outer_radius:.1f} mm",
        f"- Shell wall thickness: {P.wall_thickness:.1f} mm",
        f"- Square mounting flange: {P.flange_width:.1f} x {P.flange_depth:.1f} x {P.flange_thickness:.1f} mm",
        f"- Flange holes: M4 clearance, {P.flange_m4_clearance_diameter:.1f} mm diameter, at X/Y +/-{P.flange_corner_hole_offset:.1f} mm",
        f"- Rim skirt: {P.rim_skirt_height:.1f} mm tall cylindrical overlap into the flange",
        f"- Sensor mockup front camera aperture: {P.front_camera_cut_diameter:.1f} mm diameter, no external pad",
        f"- Sensor mockup top cut: {P.top_sensor_cut_diameter:.1f} mm diameter",
        f"- Top sensor boss: {P.top_sensor_pad_diameter:.1f} mm diameter x {P.top_sensor_pad_height:.1f} mm tall, embedded {P.top_sensor_pad_embed_depth:.1f} mm into the dome",
        "",
        "Exported STEP files:",
    ]
    for path in sorted(exported, key=lambda p: p.name):
        lines.append(f"- {path.relative_to(PROJECT_ROOT)}")

    lines.extend(
        [
            "",
            "Print/iteration assumptions:",
            "- Intended print orientation is flange/open rim down on the bed.",
            "- The hollow dome is a cover/sensor shell, not a load-bearing chassis part.",
            "- The 240 mm square flange matches the current lower chassis top footprint for visual scale.",
            "- The front camera feature is currently just an aperture; a real camera mount should be designed around the selected camera module.",
            "- The prototype pair STEP is for side-by-side visual comparison only and is not printable as a single object.",
        ]
    )

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def main() -> None:
    clear_generated_steps()
    parts = {
        "plain": make_plain_dome(),
        "sensor_mockup": make_sensor_mockup_dome(),
    }
    parts["prototypes"] = make_prototype_pair(parts)

    assert_printable("plain", parts["plain"])
    assert_printable("sensor_mockup", parts["sensor_mockup"])

    exported: list[Path] = []
    for name, filename in PART_FILENAMES.items():
        exported.append(export_shape(parts[name], filename))

    report_path = write_report(parts, exported)
    print(f"Exported {len(exported)} STEP files to {STEP_DIR}")
    print(f"Wrote report to {report_path}")


if __name__ == "__main__":
    main()
