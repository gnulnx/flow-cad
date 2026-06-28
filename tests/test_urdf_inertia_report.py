from __future__ import annotations

import pytest

from flow_cad.urdf_inertia_report import compute_chassis_pitch_inertia_report


def test_component_summed_pitch_inertia_excludes_wheel_links() -> None:
    report = {
        "project_id": "unit",
        "target": {"name": "dojo"},
        "chassis_box_size_m": [0.1, 0.2, 0.3],
        "chassis_joint_xyz_m": [0.0, 0.0, 0.0],
        "recommended_chassis_mass_kg": 4.0,
        "nominal_chassis_com_m": {"x": 0.0, "z": 0.0},
        "mass_properties": {
            "contributions": [
                {
                    "occurrence_name": "body_low",
                    "part_id": "body",
                    "mass_kg": 2.0,
                    "assembly_center_of_mass_mm": [0.0, 0.0, 0.0],
                },
                {
                    "occurrence_name": "body_high",
                    "part_id": "body",
                    "mass_kg": 2.0,
                    "assembly_center_of_mass_mm": [0.0, 0.0, 100.0],
                },
                {
                    "occurrence_name": "left_reference_wheel",
                    "part_id": "reference_wheel",
                    "mass_kg": 10.0,
                    "assembly_center_of_mass_mm": [0.0, 0.0, 0.0],
                },
            ],
        },
        "chassis_collision_geometry": {
            "occurrences": [
                {
                    "occurrence_name": "body_low",
                    "flow_size_mm": [10.0, 20.0, 30.0],
                },
                {
                    "occurrence_name": "body_high",
                    "flow_size_mm": [10.0, 20.0, 30.0],
                },
            ],
        },
    }

    result = compute_chassis_pitch_inertia_report(report, multiplier=9.0)

    local_each = 2.0 / 12.0 * (0.020**2 + 0.030**2)
    shift_each = 2.0 * 0.050**2
    assert result["component_total_mass_kg"] == pytest.approx(4.0)
    assert result["component_com_flow_mm"] == pytest.approx([0.0, 0.0, 50.0])
    assert result["component_composite_iyy_kg_m2"] == pytest.approx(2 * (local_each + shift_each))
    assert result["exported_chassis_box_iyy_kg_m2"] == pytest.approx(4.0 / 12.0 * (0.1**2 + 0.3**2))
    assert result["ratio_dojo_multiplied_to_exported_iyy"] == pytest.approx(9.0)
    assert result["skipped_contributions"] == [
        {"occurrence_name": "left_reference_wheel", "reason": "wheel_link"}
    ]
