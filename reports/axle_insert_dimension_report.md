# Axle Insert Dimension Report

Generated from the current CAD source and the exported STEP files.

## Key Finding

**PASS:** every exported axle insert STEP measures **12 mm x 12 mm** at the washer-tab relief mouth and at the pocket floor.

## Source Cutter Dimensions

- Nominal relief cutter width along Y: **12 mm**
- Nominal relief cutter height along Z: **12 mm**
- Nominal relief depth along X: **3.2 mm**
- Clearance from axle side before pocket: **1.5 mm**

## STEP-Measured Pocket Dimensions

| Variant | Source cutter Y x Z x X | STEP mouth at washer face | STEP flat floor | STEP face-to-floor depth |
| --- | ---: | ---: | ---: | ---: |
| tight | 12 x 12 x 3.2 mm | 12 x 12 mm | 12 x 12 mm | 3.2 mm |
| medium | 12 x 12 x 3.2 mm | 12 x 12 mm | 12 x 12 mm | 3.2 mm |
| loose | 12 x 12 x 3.2 mm | 12 x 12 mm | 12 x 12 mm | 3.2 mm |

## Medium Variant Coordinates

- Nominal cutter X span: 26.8 to 30 mm
- Nominal cutter Y span: 9.8 to 21.8 mm
- Nominal cutter Z span: -6 to 6 mm
- STEP mouth Y span: 9.8 to 21.8 mm
- STEP mouth Z span: -6 to 6 mm
- STEP floor Y span: 9.8 to 21.8 mm
- STEP floor Z span: -6 to 6 mm

## Interpretation

The washer-tab relief is now cut after the global insert chamfer, so the chamfer does not widen the washer-facing mouth. The exported STEP geometry measures 12 mm at the mouth and 12 mm at the floor for tight, medium, and loose insert variants.
