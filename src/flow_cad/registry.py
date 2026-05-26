from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from flow_cad.params import ChassisParams
from flow_cad.parts.chassis import (
    make_bottom_tray,
    make_side_plate,
    make_simple_mounting_plate,
    make_top_lid,
)
from flow_cad.parts.coupons import make_push_button_hole_test_coupon, make_push_button_recess_test_coupon
from flow_cad.parts.inserts import make_axle_insert
from flow_cad.parts.panels import (
    make_end_panel,
    make_rear_panel_body_for_bumpout,
    make_rear_panel_bumpout,
    make_rear_panel_bumpout_shell,
    make_rear_panel_detachable_body,
    make_rear_panel_detachable_bumpout,
    make_rear_panel_detachable_bumpout_shell,
    make_rear_panel_detachable_bumpout_shell_tpu,
)
from flow_cad.parts.reference import (
    make_reference_axle_pair,
    make_reference_wheel_axle_pair,
    make_reference_wheel_pair,
)
from flow_cad.parts.shelves import make_bottom_cable_shelf, make_equipment_shelf, make_shelf_spacer_block


class PartRole(StrEnum):
    PRINTABLE = "printable"
    REFERENCE = "reference"
    INSPECTION = "inspection"


PartFactory = Callable[[ChassisParams], object]


@dataclass(frozen=True)
class PartDefinition:
    id: str
    module_id: str
    filename: str
    factory: PartFactory
    role: PartRole = PartRole.PRINTABLE
    material: str = "PETG"
    shell_count: int = 4
    infill_density: float = 0.4

    @property
    def is_printable(self) -> bool:
        return self.role == PartRole.PRINTABLE


INSERT_VARIANTS: dict[str, tuple[float, float]] = {
    "tight": (16.3, 12.3),
    "medium": (16.6, 12.5),
    "loose": (16.9, 12.8),
}


def _insert_factory(diameter: float, flat_to_flat: float) -> PartFactory:
    return lambda params: make_axle_insert(params, diameter, flat_to_flat)


PART_DEFINITIONS: tuple[PartDefinition, ...] = (
    PartDefinition("left_side_plate", "lower_chassis", "b3_lower_chassis_left_side_plate.step", lambda p: make_side_plate(p, inward=1)),
    PartDefinition("right_side_plate", "lower_chassis", "b3_lower_chassis_right_side_plate.step", lambda p: make_side_plate(p, inward=-1)),
    PartDefinition("front_panel", "lower_chassis", "b3_lower_chassis_front_panel.step", lambda p: make_end_panel(p, inward_y=1, cable_panel=False)),
    PartDefinition("rear_panel", "lower_chassis", "b3_lower_chassis_rear_panel.step", make_rear_panel_bumpout),
    PartDefinition("rear_panel_body", "lower_chassis", "b3_lower_chassis_rear_panel_body.step", make_rear_panel_body_for_bumpout),
    PartDefinition("rear_panel_bumpout", "lower_chassis", "b3_lower_chassis_rear_panel_bumpout.step", make_rear_panel_bumpout_shell),
    PartDefinition("rear_panel_detachable", "lower_chassis", "b3_lower_chassis_rear_panel_detachable.step", make_rear_panel_detachable_bumpout),
    PartDefinition("rear_panel_detachable_body", "lower_chassis", "b3_lower_chassis_rear_panel_detachable_body.step", make_rear_panel_detachable_body),
    PartDefinition("rear_panel_detachable_bumpout", "lower_chassis", "b3_lower_chassis_rear_panel_detachable_bumpout.step", make_rear_panel_detachable_bumpout_shell),
    PartDefinition("rear_panel_detachable_bumpout_tpu", "lower_chassis", "b3_lower_chassis_rear_panel_detachable_bumpout_TPU.step", make_rear_panel_detachable_bumpout_shell_tpu, material="TPU"),
    PartDefinition("rear_panel_vented", "lower_chassis", "b3_lower_chassis_rear_panel_vented.step", lambda p: make_end_panel(p, inward_y=-1, cable_panel=True)),
    PartDefinition("bottom_tray", "lower_chassis", "b3_lower_chassis_bottom_tray.step", make_bottom_tray),
    PartDefinition("top_lid", "lower_chassis", "b3_lower_chassis_top_lid.step", make_top_lid),
    PartDefinition("simple_mounting_plate", "lower_chassis", "b3_lower_chassis_simple_mounting_plate.step", make_simple_mounting_plate),
    PartDefinition("bottom_cable_shelf", "lower_chassis", "b3_lower_chassis_bottom_cable_shelf.step", make_bottom_cable_shelf),
    PartDefinition("equipment_shelf", "lower_chassis", "b3_equipment_shelf.step", make_equipment_shelf),
    PartDefinition("equipment_shelf_side_cable", "lower_chassis", "b3_equipment_shelf_side_cable.step", lambda p: make_equipment_shelf(p, side_cable_notches=True)),
    PartDefinition(
        "equipment_shelf_side_cable_shallow",
        "lower_chassis",
        "b3_equipment_shelf_side_cable_shallow.step",
        lambda p: make_equipment_shelf(p, side_cable_notches=True, side_cable_notch_depth=p.shelf_side_cable_notch_shallow_depth),
    ),
    PartDefinition(
        "equipment_shelf_four_way_cable_shallow",
        "lower_chassis",
        "b3_equipment_shelf_four_way_cable_shallow.step",
        lambda p: make_equipment_shelf(
            p,
            side_cable_notches=True,
            side_cable_notch_depth=p.shelf_side_cable_notch_shallow_depth,
            end_cable_notches=True,
            end_cable_notch_depth=p.shelf_side_cable_notch_shallow_depth,
        ),
    ),
    PartDefinition(
        "equipment_shelf_service_fit",
        "lower_chassis",
        "b3_equipment_shelf_service_fit.step",
        lambda p: make_equipment_shelf(
            p,
            side_cable_notches=True,
            side_cable_notch_depth=p.service_shelf_side_relief_depth,
            side_cable_notch_length=p.service_shelf_side_relief_length,
            width=p.service_shelf_width,
            depth=p.service_shelf_depth,
        ),
    ),
    PartDefinition(
        "equipment_shelf_service_fit_four_way",
        "lower_chassis",
        "b3_equipment_shelf_service_fit_four_way.step",
        lambda p: make_equipment_shelf(
            p,
            side_cable_notches=True,
            side_cable_notch_depth=p.service_shelf_side_relief_depth,
            side_cable_notch_length=p.service_shelf_side_relief_length,
            end_cable_notches=True,
            end_cable_notch_depth=p.shelf_side_cable_notch_shallow_depth,
            end_cable_notch_length=p.shelf_side_cable_notch_length,
            width=p.service_shelf_width,
            depth=p.service_shelf_depth,
            center_wiring_channels=False,
        ),
    ),
    PartDefinition("shelf_spacer_block_55mm", "lower_chassis", "b3_shelf_spacer_block_55mm.step", make_shelf_spacer_block),
    PartDefinition("push_button_hole_test_coupon_12p1mm", "test_coupons", "b3_push_button_hole_test_coupon_12p1mm.step", make_push_button_hole_test_coupon),
    PartDefinition("push_button_recess_test_coupon_12p1mm", "test_coupons", "b3_push_button_recess_test_coupon_12p1mm.step", make_push_button_recess_test_coupon),
    *(
        PartDefinition(f"axle_insert_{variant}", "inserts", f"b3_axle_insert_{variant}.step", _insert_factory(diameter, flat_to_flat))
        for variant, (diameter, flat_to_flat) in INSERT_VARIANTS.items()
    ),
    PartDefinition("reference_wheel_pair", "reference", "b3_reference_wheel_pair.step", make_reference_wheel_pair, role=PartRole.REFERENCE, material=""),
    PartDefinition("reference_axle_pair", "reference", "b3_reference_axle_pair.step", make_reference_axle_pair, role=PartRole.REFERENCE, material=""),
    PartDefinition("reference_wheel_axle_pair", "reference", "b3_reference_wheel_axle_pair.step", make_reference_wheel_axle_pair, role=PartRole.REFERENCE, material=""),
)

REGISTRY: dict[str, PartDefinition] = {definition.id: definition for definition in PART_DEFINITIONS}

ASSEMBLY_DEFINITION = PartDefinition(
    "assembly",
    "lower_chassis",
    "b3_lower_chassis_assembly.step",
    lambda _params: None,
    role=PartRole.INSPECTION,
    material="",
)


def iter_part_definitions(*, include_references: bool = True) -> Iterable[PartDefinition]:
    for definition in PART_DEFINITIONS:
        if include_references or definition.role != PartRole.REFERENCE:
            yield definition


def iter_export_definitions(*, include_references: bool = True, include_assembly: bool = True) -> Iterable[PartDefinition]:
    yield from iter_part_definitions(include_references=include_references)
    if include_assembly:
        yield ASSEMBLY_DEFINITION


def expected_step_relative_paths(*, include_references: bool = True, include_assembly: bool = True) -> set[Path]:
    return {
        Path("step") / definition.module_id / definition.filename
        for definition in iter_export_definitions(
            include_references=include_references,
            include_assembly=include_assembly,
        )
    }


def build_registered_parts(params: ChassisParams) -> dict[str, object]:
    return {definition.id: definition.factory(params) for definition in PART_DEFINITIONS}
