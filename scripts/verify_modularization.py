import sys
import os
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# Force XDG cache for build123d
os.environ["XDG_CACHE_HOME"] = "/tmp/erb-balance-bot-cad-cache"

try:
    from erb_cad.params import ChassisParams
    from erb_cad.parts.shelves import make_equipment_shelf as make_shelf_new
    from erb_cad.parts.chassis import make_side_plate as make_side_plate_new
    from erb_cad.parts.panels import (
        make_end_panel as make_end_panel_new,
        make_rear_panel_body_for_bumpout as make_rear_panel_body_new,
        make_rear_panel_bumpout_shell as make_rear_panel_bumpout_shell_new,
        make_rear_panel_detachable_body as make_rear_panel_detachable_body_new,
        make_rear_panel_detachable_bumpout_shell as make_rear_panel_detachable_bumpout_shell_new
    )
    from erb_cad.parts.chassis import (
        make_bottom_tray as make_bottom_tray_new,
        make_top_lid as make_top_lid_new
    )
    from erb_cad.parts.inserts import make_axle_insert as make_axle_insert_new
    from erb_cad.parts.upper_module import (
        make_upper_wide_center_adapter_deck as make_adapter_deck_new,
        make_upper_wide_center_compute_bay as make_compute_bay_new,
        make_upper_wide_overwheel_pod as make_overwheel_pod_new,
        make_upper_wide_center_crossmember as make_center_crossmember_new,
        make_upper_wide_side_crossmember as make_side_crossmember_new,
        make_upper_perception_pod as make_perception_pod_new
    )
    # Import legacy via sys.path trick
    sys.path.insert(0, str(PROJECT_ROOT / "cad"))
    from erb_lower_chassis_legacy import (
        make_equipment_shelf as make_shelf_legacy,
        make_side_plate as make_side_plate_legacy,
        make_end_panel as make_end_panel_legacy,
        make_rear_panel_body_for_bumpout as make_rear_panel_body_legacy,
        make_rear_panel_bumpout_shell as make_rear_panel_bumpout_shell_legacy,
        make_rear_panel_detachable_body as make_rear_panel_detachable_body_legacy,
        make_rear_panel_detachable_bumpout_shell as make_rear_panel_detachable_bumpout_shell_legacy,
        make_bottom_tray as make_bottom_tray_legacy,
        make_top_lid as make_top_lid_legacy,
        make_axle_insert as make_axle_insert_legacy,
        make_upper_wide_center_adapter_deck as make_adapter_deck_legacy,
        make_upper_wide_center_compute_bay as make_compute_bay_legacy,
        make_upper_wide_overwheel_pod as make_overwheel_pod_legacy,
        make_upper_wide_center_crossmember as make_center_crossmember_legacy,
        make_upper_wide_side_crossmember as make_side_crossmember_legacy,
        make_upper_perception_pod as make_perception_pod_legacy
    )
except ImportError as e:
    print(f"Error importing: {e}")
    sys.exit(1)

def verify_shelves():
    params = ChassisParams()
    variants = [
        {},  # Default
        {"side_cable_notches": True},
        {"end_cable_notches": True},
        {"side_cable_notches": True, "end_cable_notches": True},
        {"width": 170, "depth": 188},  # service fit
    ]

    success = True
    for i, v in enumerate(variants):
        print(f"Verifying variant {i}: {v}")
        
        # Legacy uses global P, so we don't pass it
        # But wait, did I change the legacy to use the NEW params?
        # Yes, I put a shim in cad/params.py
        
        legacy_part = make_shelf_legacy(**v)
        # New modular code takes params as first arg
        new_part = make_shelf_new(params, **v)

        vol_l = legacy_part.volume
        vol_n = new_part.volume
        bbox_l = legacy_part.bounding_box()
        bbox_n = new_part.bounding_box()

        if abs(vol_l - vol_n) > 1e-6:
            print(f"  FAILED: Volume mismatch! Legacy: {vol_l}, New: {vol_n}")
            success = False
        else:
            print(f"  Volume match: {vol_l}")

        if str(bbox_l) != str(bbox_n):
            print(f"  FAILED: BBox mismatch! Legacy: {bbox_l}, New: {bbox_n}")
            success = False
        else:
            print(f"  BBox match: {bbox_l}")

    if success:
        print("\nALL SHELF VARIANTS VERIFIED IDENTICAL.")
    else:
        print("\nSHELF VERIFICATION FAILED.")
        success = False

    print("\nVerifying Side Plates...")
    for inward in (-1, 1):
        print(f"Verifying inward={inward}")
        legacy_part = make_side_plate_legacy(inward)
        new_part = make_side_plate_new(params, inward)

        vol_l = legacy_part.volume
        vol_n = new_part.volume
        bbox_l = legacy_part.bounding_box()
        bbox_n = new_part.bounding_box()

        if abs(vol_l - vol_n) > 1e-6:
            print(f"  FAILED: Volume mismatch! Legacy: {vol_l}, New: {vol_n}")
            success = False
        else:
            print(f"  Volume match: {vol_l}")

        if str(bbox_l) != str(bbox_n):
            print(f"  FAILED: BBox mismatch! Legacy: {bbox_l}, New: {bbox_n}")
            success = False
        else:
            print(f"  BBox match: {bbox_l}")

    if success:
        print("\nSIDE PLATES VERIFIED IDENTICAL.")
    else:
        print("\nSIDE PLATE VERIFICATION FAILED.")
        success = False

    print("\nVerifying Panels...")
    panel_tests = [
        ("End Panel Front", make_end_panel_legacy, make_end_panel_new, {"inward_y": 1, "cable_panel": False}),
        ("End Panel Rear", make_end_panel_legacy, make_end_panel_new, {"inward_y": -1, "cable_panel": True}),
        ("Rear Panel Body", make_rear_panel_body_legacy, make_rear_panel_body_new, {}),
        ("Rear Bumpout Shell", make_rear_panel_bumpout_shell_legacy, make_rear_panel_bumpout_shell_new, {}),
        ("Detachable Body", make_rear_panel_detachable_body_legacy, make_rear_panel_detachable_body_new, {}),
        ("Detachable Bumpout Shell", make_rear_panel_detachable_bumpout_shell_legacy, make_rear_panel_detachable_bumpout_shell_new, {}),
    ]

    for name, legacy_fn, new_fn, kwargs in panel_tests:
        print(f"Verifying {name}")
        legacy_part = legacy_fn(**kwargs)
        new_part = new_fn(params, **kwargs)

        vol_l = legacy_part.volume
        vol_n = new_part.volume
        bbox_l = legacy_part.bounding_box()
        bbox_n = new_part.bounding_box()

        if abs(vol_l - vol_n) > 1e-6:
            print(f"  FAILED: Volume mismatch! Legacy: {vol_l}, New: {vol_n}")
            success = False
        else:
            print(f"  Volume match: {vol_l}")

        if str(bbox_l) != str(bbox_n):
            print(f"  FAILED: BBox mismatch! Legacy: {bbox_l}, New: {bbox_n}")
            success = False
        else:
            print(f"  BBox match: {bbox_l}")

    if success:
        print("\nPANELS VERIFIED IDENTICAL.")
    else:
        print("\nPANEL VERIFICATION FAILED.")
        success = False

    print("\nVerifying Core Chassis & Inserts...")
    core_tests = [
        ("Bottom Tray", make_bottom_tray_legacy, make_bottom_tray_new, {}),
        ("Top Lid", make_top_lid_legacy, make_top_lid_new, {}),
        ("Axle Insert Medium", make_axle_insert_legacy, make_axle_insert_new, {"diameter": 16.0, "flat_to_flat": 14.5}),
        ("Axle Insert Tight", make_axle_insert_legacy, make_axle_insert_new, {"diameter": 15.9, "flat_to_flat": 14.4}),
    ]

    for name, legacy_fn, new_fn, kwargs in core_tests:
        print(f"Verifying {name}")
        legacy_part = legacy_fn(**kwargs)
        new_part = new_fn(params, **kwargs)

        vol_l = legacy_part.volume
        vol_n = new_part.volume
        bbox_l = legacy_part.bounding_box()
        bbox_n = new_part.bounding_box()

        if abs(vol_l - vol_n) > 1e-6:
            print(f"  FAILED: Volume mismatch! Legacy: {vol_l}, New: {vol_n}")
            success = False
        else:
            print(f"  Volume match: {vol_l}")

        if str(bbox_l) != str(bbox_n):
            print(f"  FAILED: BBox mismatch! Legacy: {bbox_l}, New: {bbox_n}")
            success = False
        else:
            print(f"  BBox match: {bbox_l}")

    print("\nVerifying Upper Module...")
    upper_tests = [
        ("Adapter Deck", make_adapter_deck_legacy, make_adapter_deck_new, {}),
        ("Compute Bay", make_compute_bay_legacy, make_compute_bay_new, {}),
        ("Overwheel Pod Left", make_overwheel_pod_legacy, make_overwheel_pod_new, {"side": -1}),
        ("Overwheel Pod Right", make_overwheel_pod_legacy, make_overwheel_pod_new, {"side": 1}),
        ("Center Crossmember", make_center_crossmember_legacy, make_center_crossmember_new, {}),
        ("Side Crossmember", make_side_crossmember_legacy, make_side_crossmember_new, {}),
        ("Perception Pod", make_perception_pod_legacy, make_perception_pod_new, {}),
    ]

    for name, legacy_fn, new_fn, kwargs in upper_tests:
        print(f"Verifying {name}")
        legacy_part = legacy_fn(**kwargs)
        new_part = new_fn(params, **kwargs)

        vol_l = legacy_part.volume
        vol_n = new_part.volume
        bbox_l = legacy_part.bounding_box()
        bbox_n = new_part.bounding_box()

        if abs(vol_l - vol_n) > 1e-6:
            print(f"  FAILED: Volume mismatch! Legacy: {vol_l}, New: {vol_n}")
            success = False
        else:
            print(f"  Volume match: {vol_l}")

        if str(bbox_l) != str(bbox_n):
            print(f"  FAILED: BBox mismatch! Legacy: {bbox_l}, New: {bbox_n}")
            success = False
        else:
            print(f"  BBox match: {bbox_l}")

    if success:
        print("\nALL PARTS VERIFIED IDENTICAL.")
    else:
        print("\nVERIFICATION FAILED.")
        sys.exit(1)

if __name__ == "__main__":
    verify_shelves()
