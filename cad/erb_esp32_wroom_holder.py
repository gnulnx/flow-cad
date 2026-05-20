#!/usr/bin/env python3
"""Parametric STEP generator for an Erb ESP32-WROOM holder.

The holder is a small two-piece enclosure for a HiLetgo/ESP-32S style
ESP32-WROOM development board with side pin access for IMU wiring.
Dimensions are millimeters.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
os.environ.setdefault("XDG_CACHE_HOME", "/tmp/erb-balance-bot-cad-cache")
Path(os.environ["XDG_CACHE_HOME"]).mkdir(parents=True, exist_ok=True)

from build123d import Box, Compound, Cylinder, Location, chamfer, export_step  # noqa: E402
from flow_cad.step_io import normalize_step_file  # noqa: E402


@dataclass(frozen=True)
class Esp32HolderParams:
    # Working board envelope from photos plus common ESP32-WROOM devkit sizes.
    board_length: float = 55.0
    board_width: float = 28.5
    board_clearance: float = 1.6

    wall_thickness: float = 2.4
    bottom_thickness: float = 2.6
    base_height: float = 15.0
    lid_thickness: float = 2.6
    lid_lip_height: float = 2.0
    lid_lip_thickness: float = 1.6

    mount_tab_length: float = 10.0
    mount_tab_width: float = 42.0
    mount_tab_thickness: float = 3.2

    m3_clearance_diameter: float = 3.4
    m3_counterbore_diameter: float = 7.0
    m3_mount_hole_x: float = 15.5
    lid_screw_clearance_diameter: float = 2.8
    lid_screw_pilot_diameter: float = 2.2
    lid_screw_counterbore_diameter: float = 5.6
    lid_screw_x: float = 6.0
    lid_screw_boss_width: float = 8.5
    lid_screw_boss_length: float = 8.5
    lid_screw_boss_outset: float = 4.4
    lid_screw_end_tab_width: float = 36.0
    lid_screw_end_tab_length: float = 10.5

    side_pin_window_length: float = 52.0
    side_pin_window_height: float = 16.0
    side_pin_window_center_z: float = 7.5
    pin_trough_width: float = 6.2
    pin_trough_length: float = 52.0
    pin_trough_center_x: float = 12.6

    usb_window_width: float = 12.5
    usb_window_height: float = 7.0
    usb_window_center_z: float = 6.5
    imu_cable_window_width: float = 18.0
    imu_cable_window_height: float = 7.0
    imu_cable_window_center_z: float = 7.0

    board_stop_height: float = 2.0
    board_stop_width: float = 3.0
    board_stop_length: float = 7.0

    antenna_slot_width: float = 4.0
    antenna_slot_length: float = 24.0
    antenna_slot_spacing: float = 7.0
    antenna_slot_count: int = 4

    def internal_width(self) -> float:
        return self.board_width + self.board_clearance * 2.0

    def internal_length(self) -> float:
        return self.board_length + self.board_clearance * 2.0

    def outer_width(self) -> float:
        return self.internal_width() + self.wall_thickness * 2.0

    def outer_length(self) -> float:
        return self.internal_length() + self.wall_thickness * 2.0

    def overall_length(self) -> float:
        return self.outer_length() + self.mount_tab_length * 2.0

    def lid_screw_y(self) -> float:
        return self.outer_length() / 2.0 + self.lid_screw_boss_outset


P = Esp32HolderParams()

STEP_DIR = PROJECT_ROOT / "exports" / "step" / "esp32_wroom_holder"
REPORT_DIR = PROJECT_ROOT / "reports"

PART_FILENAMES = {
    "base": "erb_esp32_wroom_holder_base.step",
    "lid": "erb_esp32_wroom_holder_lid.step",
}


def box_at(size: tuple[float, float, float], center: tuple[float, float, float]):
    return Box(*size).moved(Location(center))


def cyl_z(radius: float, length: float, center: tuple[float, float, float]):
    return Cylinder(radius, length).moved(Location(center))


def safe_chamfer(shape, amount: float):
    fallback = shape if hasattr(shape, "bounding_box") else Compound(children=list(shape))
    try:
        chamfered = chamfer(fallback.edges(), amount)
        return chamfered if hasattr(chamfered, "bounding_box") else fallback
    except Exception:
        return fallback


def make_base():
    ow = P.outer_width()
    ol = P.outer_length()
    iw = P.internal_width()
    il = P.internal_length()
    h = P.base_height

    base = box_at((ow, ol, h), (0.0, 0.0, h / 2.0))

    # Open board cavity from the top while leaving a printed bottom floor.
    base -= box_at(
        (iw, il, h + 2.0),
        (0.0, 0.0, P.bottom_thickness + (h + 2.0) / 2.0),
    )

    # Four shelf-mount ears with M3 through holes and washer/counterbore relief.
    tab_y = ol / 2.0 + P.mount_tab_length / 2.0
    for side in (-1.0, 1.0):
        base += box_at(
            (P.mount_tab_width, P.mount_tab_length, P.mount_tab_thickness),
            (0.0, side * tab_y, P.mount_tab_thickness / 2.0),
        )
        for x in (-P.m3_mount_hole_x, P.m3_mount_hole_x):
            y = side * tab_y
            base -= cyl_z(P.m3_clearance_diameter / 2.0, 12.0, (x, y, P.mount_tab_thickness / 2.0))
            base -= cyl_z(P.m3_counterbore_diameter / 2.0, 1.6, (x, y, P.mount_tab_thickness - 0.8))

    # Long side openings expose the header rows. Matching bottom troughs let
    # downward-facing pins and Dupont leads pass through instead of being trapped.
    for side in (-1.0, 1.0):
        base -= box_at(
            (
                P.wall_thickness + 2.0,
                P.side_pin_window_length,
                P.side_pin_window_height,
            ),
            (
                side * ow / 2.0,
                0.0,
                P.side_pin_window_center_z,
            ),
        )
        base -= box_at(
            (
                P.pin_trough_width,
                P.pin_trough_length,
                P.bottom_thickness + 2.0,
            ),
            (
                side * P.pin_trough_center_x,
                0.0,
                P.bottom_thickness / 2.0,
            ),
        )

    # USB/service cable opening on the front and an IMU cable window on the rear.
    base -= box_at(
        (P.usb_window_width, P.wall_thickness + 2.0, P.usb_window_height),
        (0.0, -ol / 2.0, P.usb_window_center_z),
    )
    base -= box_at(
        (P.imu_cable_window_width, P.wall_thickness + 2.0, P.imu_cable_window_height),
        (0.0, ol / 2.0, P.imu_cable_window_center_z),
    )

    # Small bottom stops keep the PCB lifted above the floor and give pin solder joints clearance.
    stop_z = P.bottom_thickness + P.board_stop_height / 2.0
    for x in (-(iw / 2.0 - P.board_stop_width / 2.0), iw / 2.0 - P.board_stop_width / 2.0):
        for y in (-(il / 2.0 - 7.5), il / 2.0 - 7.5):
            base += box_at(
                (P.board_stop_width, P.board_stop_length, P.board_stop_height),
                (x, y, stop_z),
            )

    # Lid screw bosses sit outside the board cavity, so the lid holes have full edge margin.
    lid_screw_y = P.lid_screw_y()
    for y in (-lid_screw_y, lid_screw_y):
        for x in (-P.lid_screw_x, P.lid_screw_x):
            base += box_at(
                (P.lid_screw_boss_width, P.lid_screw_boss_length, h),
                (x, y, h / 2.0),
            )
            base -= cyl_z(P.lid_screw_pilot_diameter / 2.0, 9.0, (x, y, h - 3.0))

    return safe_chamfer(base, 0.45)


def make_lid():
    ow = P.outer_width()
    ol = P.outer_length()
    iw = P.internal_width()
    il = P.internal_length()
    t = P.lid_thickness

    lid = box_at((ow + 0.8, ol + 0.8, t), (0.0, 0.0, t / 2.0))

    lid_screw_y = P.lid_screw_y()
    for y in (-lid_screw_y, lid_screw_y):
        lid += box_at(
            (P.lid_screw_end_tab_width, P.lid_screw_end_tab_length, t),
            (0.0, y, t / 2.0),
        )

    # Underside locating lip. It is a ring so it does not press on the board.
    lip_z = -P.lid_lip_height / 2.0
    lip_outer_w = iw - 0.8
    lip_outer_l = il - 0.8
    lip_t = P.lid_lip_thickness
    lid += box_at((lip_outer_w, lip_t, P.lid_lip_height), (0.0, -lip_outer_l / 2.0 + lip_t / 2.0, lip_z))
    lid += box_at((lip_outer_w, lip_t, P.lid_lip_height), (0.0, lip_outer_l / 2.0 - lip_t / 2.0, lip_z))
    lid += box_at((lip_t, lip_outer_l, P.lid_lip_height), (-lip_outer_w / 2.0 + lip_t / 2.0, 0.0, lip_z))
    lid += box_at((lip_t, lip_outer_l, P.lid_lip_height), (lip_outer_w / 2.0 - lip_t / 2.0, 0.0, lip_z))

    # Antenna/vent slots near the ESP module end; PETG-CF can attenuate RF, so keep this area open.
    slot_span = (P.antenna_slot_count - 1) * P.antenna_slot_spacing
    for i in range(P.antenna_slot_count):
        x = -slot_span / 2.0 + i * P.antenna_slot_spacing
        lid -= box_at(
            (P.antenna_slot_width, P.antenna_slot_length, t + 4.0),
            (x, il / 2.0 - 18.0, t / 2.0),
        )

    # Lid screw clearance holes and top-side counterbores.
    for y in (-lid_screw_y, lid_screw_y):
        for x in (-P.lid_screw_x, P.lid_screw_x):
            lid -= cyl_z(P.lid_screw_clearance_diameter / 2.0, t + 6.0, (x, y, t / 2.0))
            lid -= cyl_z(P.lid_screw_counterbore_diameter / 2.0, 1.3, (x, y, t - 0.65))

    return safe_chamfer(lid, 0.35)


def make_assembly(parts: dict[str, object]):
    base = parts["base"]
    lid = parts["lid"].moved(Location((0.0, 0.0, P.base_height)))
    return Compound(children=[base, lid], label="erb_esp32_wroom_holder_assembly")


def bbox_dims(shape) -> tuple[float, float, float]:
    bb = shape.bounding_box()
    return (bb.max.X - bb.min.X, bb.max.Y - bb.min.Y, bb.max.Z - bb.min.Z)


def export_shape(shape, filename: str) -> Path:
    STEP_DIR.mkdir(parents=True, exist_ok=True)
    path = STEP_DIR / filename
    ok = export_step(shape, path)
    if not ok:
        raise RuntimeError(f"STEP export failed: {path}")
    normalize_step_file(path)
    return path


def clear_generated_steps() -> None:
    STEP_DIR.mkdir(parents=True, exist_ok=True)
    for path in STEP_DIR.glob("erb_esp32_wroom*.step"):
        path.unlink()


def write_report(parts: dict[str, object], exported: list[Path]) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / "esp32_wroom_holder_report.txt"
    assembly_dims = bbox_dims(parts["assembly"])
    base_dims = bbox_dims(parts["base"])
    lid_dims = bbox_dims(parts["lid"])

    lines = [
        "Erb ESP32-WROOM holder CAD report",
        "==================================",
        "",
        "Working board envelope:",
        f"- Board assumed: {P.board_width:.1f} W x {P.board_length:.1f} L mm",
        f"- Internal case envelope: {P.internal_width():.1f} W x {P.internal_length():.1f} L mm",
        "",
        "Final outer dimensions:",
        f"- Base body: {base_dims[0]:.1f} W x {base_dims[1]:.1f} L x {base_dims[2]:.1f} H mm",
        f"- Lid: {lid_dims[0]:.1f} W x {lid_dims[1]:.1f} L x {lid_dims[2]:.1f} H mm",
        f"- Closed assembly: {assembly_dims[0]:.1f} W x {assembly_dims[1]:.1f} L x {assembly_dims[2]:.1f} H mm",
        "",
        "Access features:",
        f"- Side pin openings: {P.side_pin_window_length:.1f} L x {P.side_pin_window_height:.1f} H mm on both long sides",
        f"- Bottom pin troughs: {P.pin_trough_width:.1f} W x {P.pin_trough_length:.1f} L mm below both header rows",
        f"- USB opening: {P.usb_window_width:.1f} W x {P.usb_window_height:.1f} H mm on one short end",
        f"- IMU/cable opening: {P.imu_cable_window_width:.1f} W x {P.imu_cable_window_height:.1f} H mm on the opposite short end",
        f"- Lid antenna slots: {P.antenna_slot_count} slots, each {P.antenna_slot_width:.1f} W x {P.antenna_slot_length:.1f} L mm",
        "",
        "Screw sizes assumed:",
        f"- Chassis/shelf mount: M3 clearance holes, {P.m3_clearance_diameter:.1f} mm",
        f"- Lid screws: M2.5/M2.6 clearance holes, {P.lid_screw_clearance_diameter:.1f} mm, pilot holes {P.lid_screw_pilot_diameter:.1f} mm",
        f"- Lid screw bosses: {P.lid_screw_boss_width:.1f} x {P.lid_screw_boss_length:.1f} mm external bosses at Y +/-{P.lid_screw_y():.1f} mm",
        "",
        "Exported STEP files:",
    ]
    for path in sorted(exported, key=lambda p: p.name):
        lines.append(f"- {path.relative_to(PROJECT_ROOT)}")

    lines.extend(
        [
            "",
            "Assumptions made:",
            "- Coordinate convention: X is holder width, Y is board length, Z is vertical.",
            "- This holder is sized for the ESP-32S / ESP32-WROOM dev board in the supplied photos, not for the downloaded STL case geometry.",
            "- The long side openings and bottom troughs intentionally leave the header pins reachable for IMU wiring while the board body remains protected.",
            "- PETG-CF may reduce WiFi/Bluetooth range, so the lid has open slots above the antenna/module end.",
            "- Print base flat on its bottom; print lid exterior face down or lip-up depending on preferred finish/support settings.",
        ]
    )

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def main() -> None:
    clear_generated_steps()
    parts = {
        "base": make_base(),
        "lid": make_lid(),
    }
    parts["assembly"] = make_assembly(parts)

    exported: list[Path] = []
    for name, filename in PART_FILENAMES.items():
        exported.append(export_shape(parts[name], filename))
    exported.append(export_shape(parts["assembly"], "erb_esp32_wroom_holder_assembly.step"))

    report_path = write_report(parts, exported)
    print(f"Exported {len(exported)} STEP files to {STEP_DIR}")
    print(f"Wrote report to {report_path}")


if __name__ == "__main__":
    main()
