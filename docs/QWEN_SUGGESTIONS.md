# B2 Balance Bot CAD Architecture: Technical Debt & Modernization Strategy

## Executive Summary

The current CAD architecture works but has accumulated significant technical debt that makes iteration slow, testing difficult, and collaboration challenging. This document outlines the problems, proposes a modernized architecture, and provides a migration plan.

---

## Current State Analysis

### Architecture Overview

```
cad/erb_lower_chassis.py (2,047 lines, 92KB)
├── ChassisParams class (~150 parameters)
├── 29 part generator functions (make_*)
└── 30+ part instantiations → STEP exports
```

### Key Metrics
| Metric | Value |
|--------|-------|
| Lines of code | 2,047 |
| Functions | 68 |
| Parameters | ~150 |
| Exported parts | 30+ |
| Test files | 1 (ad-hoc) |

---

## Technical Debt Inventory

### 🔴 Critical Issues

#### 1. Monolithic Architecture
**Problem:** Single 2,047-line file contains everything - parameters, generators, instantiations, exports.

**Impact:**
- Cannot test a single part in isolation
- Importing one function pulls entire file into memory
- Merge conflicts when multiple people work on different parts
- Slow iteration cycle (regenerate all → sync → view)

#### 2. No Unit Testing Infrastructure
**Problem:** Validation happens via manual inspection in FreeCAD/Bambu Studio.

**Impact:**
- Breaking changes discovered late (after regeneration)
- Cannot run tests before committing
- Regression testing is manual and slow
- "Does this shelf still connect properly?" requires visual inspection

#### 3. Geometry Validation is Post-Hoc
**Problem:** Physics violations (disconnected geometry, interference) found after STEP generation.

**Impact:**
- Recent shelf disconnection bug required multiple regeneration cycles
- Each cycle: edit → regenerate (30s) → sync (10s) → open FreeCAD (20s) → inspect = ~60s per iteration
- Could have been caught in <1s with proper tests

#### 4. Parameter Explosion Without Organization
**Problem:** ~150 parameters in single `ChassisParams` dataclass.

**Impact:**
- Hard to find relevant parameters for a specific part
- No validation that parameter combinations are valid
- Changing one dimension may break unrelated parts

### 🟡 Medium Issues

#### 5. Hardcoded Export Lists
**Problem:** `sync_text_to_cad.py` has hardcoded `STEP_FILENAMES` list.

**Impact:**
- New parts don't appear in viewer until manually added to sync script
- Easy to forget this step (as happened with `service_fit_four_way`)

#### 6. No Dependency Tracking
**Problem:** No way to know which parts depend on which parameters or other parts.

**Impact:**
- Changing axle diameter requires regenerating everything
- Cannot do incremental builds

#### 7. Ad-Hoc Validation Scripts
**Problem:** `check_assembly_interference.py`, `check_mounting_features.py` are separate scripts with duplicated logic.

**Impact:**
- Validation logic scattered across multiple files
- No unified test runner

---

## Proposed Architecture

### High-Level Design

```
erb_cad/
├── __init__.py                    # Public API exports
├── params/
│   ├── __init__.py               # Parameter hierarchy
│   ├── base.py                   # Shared constants (M4 hardware, tolerances)
│   ├── chassis.py                # Chassis-specific parameters
│   └── shelf.py                  # Shelf family parameters
├── parts/
│   ├── __init__.py               # Part factory registry
│   ├── base.py                   # AbstractPart base class
│   ├── chassis/
│   │   ├── __init__.py
│   │   ├── side_plate.py         # make_side_plate()
│   │   ├── bottom_tray.py        # make_bottom_tray()
│   │   └── ...
│   ├── shelf/
│   │   ├── __init__.py
│   │   ├── base.py               # EquipmentShelf base class
│   │   ├── variants.py           # Shelf variant factories
│   │   └── connectivity.py       # Connectivity validation logic
│   └── reference/
│       ├── wheel.py
│       └── axle.py
├── assemblies/
│   ├── __init__.py
│   ├── lower_chassis.py          # Assembly builder
│   └── validation.py             # Assembly-level checks
├── exporters/
│   ├── __init__.py
│   ├── step.py                   # STEP export with auto-discovery
│   └── registry.py               # Auto-register exported parts
├── validators/
│   ├── __init__.py
│   ├── geometry.py               # Per-part geometry checks
│   ├── connectivity.py           # Is part connected?
│   ├── interference.py           # Part-to-part collision
│   └── mounting.py               # Hardware clearance checks
└── cli/
    ├── generate.py               # "erb-cad generate"
    ├── validate.py               # "erb-cad validate"
    └── test.py                   # "erb-cad test"

tests/
├── test_parts/
│   ├── test_shelf_connectivity.py
│   ├── test_side_plate_mounting.py
│   └── ...
├── test_assemblies/
│   ├── test_lower_chassis_interference.py
│   └── ...
└── conftest.py                   # pytest fixtures
```

### Key Architectural Decisions

#### 1. Modular Part Generators
Each part lives in its own module with isolated dependencies.

```python
# parts/shelf/base.py
class EquipmentShelf(ParametricPart):
    """Base equipment shelf with configurable cutouts."""
    
    def __init__(self, params: ShelfParams):
        self.params = params
        self._validate_params()
        
    def _validate_params(self):
        """Validate parameter combinations before geometry creation."""
        if self.params.side_notch_depth + self.params.center_channel_width > self.params.width / 2:
            raise ParamValidationError("Side notches overlap with center channels")
```

#### 2. Connectivity Validation as Code
Connectivity checks run during part generation, not after.

```python
# parts/shelf/connectivity.py
def validate_shelf_connectivity(shelf: EquipmentShelf) -> ConnectivityReport:
    """Verify shelf forms single connected component."""
    
    # Calculate theoretical bridges between features
    bridges = [
        Bridge(location="top", thickness=shelf._top_bridge_thickness()),
        Bridge(location="bottom", thickness=shelf._bottom_bridge_thickness()),
        Bridge(location="left", thickness=shelf._left_bridge_thickness()),
        Bridge(location="right", thickness=shelf._right_bridge_thickness()),
    ]
    
    # Check minimum bridge requirements
    min_bridge = min(b.thickness for b in bridges)
    if min_bridge < shelf.params.min_safe_bridge:
        return ConnectivityReport(
            connected=False,
            weakest_link=min_bridge,
            bridges=bridges,
        )
    
    return ConnectivityReport(connected=True, bridges=bridges)
```

#### 3. pytest-Based Testing
Standard Python testing with fixtures for parts and assemblies.

```python
# tests/test_parts/test_shelf_connectivity.py
def test_service_fit_is_connected(shelf_service_fit: EquipmentShelf):
    """Service-fit shelf must be single connected piece."""
    report = validate_shelf_connectivity(shelf_service_fit)
    assert report.connected, f"Shelf disconnected! Weakest bridge: {report.weakest_link}mm"

def test_four_way_cable_shallow_is_connected(shelf_four_way: EquipmentShelf):
    """Four-way shallow shelf must maintain connectivity."""
    report = validate_shelf_connectivity(shelf_four_way)
    assert report.connected
    # Also verify bridges are reasonable (>2mm for 3D printing)
    assert all(b.thickness > 2.0 for b in report.bridges), "Bridge too thin for printing"
```

#### 4. Auto-Discovery Export System
No more hardcoded file lists.

```python
# exporters/registry.py
class PartRegistry:
    """Auto-discovers and registers all exported parts."""
    
    def __init__(self):
        self.parts = {}
        
    def register(self, name: str, factory: Callable[[], Part]):
        """Register a part for export."""
        self.parts[name] = factory
        
    def export_all(self, output_dir: Path):
        """Export all registered parts."""
        for name, factory in self.parts.items():
            part = factory()
            step_path = output_dir / f"{name}.step"
            part.export_step(step_path)
```

```python
# parts/shelf/variants.py
@PART_REGISTRY.register("equipment_shelf_service_fit")
def make_equipment_shelf_service_fit() -> EquipmentShelf:
    return EquipmentShelf(
        width=170, depth=188, thickness=6,
        side_notches=True, side_notch_depth=36, side_notch_length=84,
        end_notches=False,  # Side-only variant
    )
```

---

## Migration Plan

### Phase 1: Foundation (Week 1-2)

**Goal:** Extract core infrastructure without breaking existing workflow.

#### Tasks:
1. **Create package structure** - Set up `erb_cad/` directory hierarchy
2. **Extract parameter classes** - Move `ChassisParams` to `params/chassis.py`
3. **Create base part class** - Define `ParametricPart` with common functionality
4. **Set up pytest** - Configure test runner, add conftest fixtures
5. **Add connectivity validator** - Implement shelf connectivity check as library function

#### Deliverables:
- ✅ New package structure in parallel with existing monolith
- ✅ pytest configured and running
- ✅ First unit test: `test_shelf_connectivity.py`
- ✅ Existing workflow unchanged (monolith still works)

### Phase 2: Shelf Family Migration (Week 2-3)

**Goal:** Migrate shelf family to new architecture as proof of concept.

#### Tasks:
1. **Extract shelf generators** - Move `make_equipment_shelf()` and variants to `parts/shelf/`
2. **Add parametric tests** - Test all shelf variant combinations
3. **Integrate connectivity validation** - Run during part generation
4. **Update sync script** - Use auto-discovery instead of hardcoded list

#### Deliverables:
- ✅ All shelf variants in new architecture
- ✅ Connectivity tests catch the bug we just fixed (regression test)
- ✅ Auto-discovery export working for shelves

### Phase 3: Chassis Parts Migration (Week 3-4)

**Goal:** Migrate remaining chassis parts.

#### Tasks:
1. **Extract side plates, bottom tray, panels** - Move to `parts/chassis/`
2. **Add mounting feature tests** - Convert `check_mounting_features.py` to pytest
3. **Add interference tests** - Convert `check_assembly_interference.py` to pytest
4. **Create assembly builder** - Implement `assemblies/lower_chassis.py`

#### Deliverables:
- ✅ All chassis parts migrated
- ✅ Mounting feature validation as unit tests
- ✅ Assembly-level interference checks automated

### Phase 4: Cleanup & Tooling (Week 4-5)

**Goal:** Remove monolith, add developer tooling.

#### Tasks:
1. **Create CLI** - `erb-cad generate`, `erb-cad validate`, `erb-cad test`
2. **Add pre-commit hooks** - Run tests before commit
3. **Remove monolith** - Delete old `cad/erb_lower_chassis.py`
4. **Documentation** - README for new architecture

#### Deliverables:
- ✅ CLI tooling complete
- ✅ Pre-commit validation
- ✅ Monolith removed
- ✅ Documentation updated

---

## Immediate Wins (This Week)

Even before full migration, we can add value:

### 1. Add Shelf Connectivity Test (30 minutes)

```python
# tests/test_shelf_connectivity.py
import pytest
from cad.erb_lower_chassis import ChassisParams as P

def test_service_fit_geometry_theory():
    """Verify service-fit shelf theoretical connectivity."""
    # Shelf dimensions
    width, depth = 170, 188
    side_notch_depth, side_notch_length = 36, 84
    
    # Calculate bridges
    half_width = width / 2  # 85
    notch_edge = half_width - side_notch_depth  # 49
    
    # Center channels at X=-36, 0, +36 with width=10
    first_channel_edge = -36 + 5  # -31
    last_channel_edge = 36 - 5    # 31
    
    # Left bridge: from notch edge (-49) to first channel (-31)
    left_bridge = abs(-49 - (-31))  # 18mm ✓
    right_bridge = abs(31 - 49)     # 18mm ✓
    
    assert left_bridge > 2, "Left bridge too thin"
    assert right_bridge > 2, "Right bridge too thin"
```

### 2. Auto-Discovery Export Fix (15 minutes)

Modify `sync_text_to_cad.py` to auto-discover STEP files:

```python
# Instead of hardcoded list:
STEP_FILENAMES = [...]  # Remove this

# Auto-discover from exports/step/
def discover_step_files():
    step_dir = PROJECT_ROOT / "exports" / "step"
    return [f.name for f in step_dir.glob("*.step") if not f.name.startswith(".")]
```

### 3. Pre-Commit Hook (10 minutes)

```bash
# .git/hooks/pre-commit
#!/bin/bash
set -e
echo "Running shelf connectivity tests..."
python -m pytest tests/test_shelf_connectivity.py -v
```

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Breaking existing workflow | Run new architecture in parallel; only switch after all tests pass |
| Lost knowledge during migration | Keep old file as reference; document decisions inline |
| Tests don't catch real issues | Combine theoretical tests with occasional visual verification |
| Team resistance to change | Show immediate value: faster iteration, caught bugs before they matter |

---

## Success Metrics

After migration:
- ✅ **Iteration time**: 60s → 5s (edit → test → fix, no FreeCAD needed)
- ✅ **Test coverage**: 0% → 80%+ of parts have unit tests
- ✅ **Regression detection**: Post-generation → Pre-commit
- ✅ **Onboarding**: "Read monolith" → "Run tests, read relevant module"

---

## Next Steps

1. **Review this document** - Does the architecture make sense? Any concerns?
2. **Approve Phase 1 scope** - Foundation work (package structure, pytest setup)
3. **I'll implement Phase 1** - Deliver working skeleton with first tests
4. **Iterate** - Adjust based on what we learn during implementation

---

*Generated by Qwen3.5-27b | May 18, 2026*
