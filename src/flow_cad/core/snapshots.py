from __future__ import annotations
import os
import datetime
from pathlib import Path
from build123d import (
    Shape,
    ExportSVG,
    Unit,
    ColorIndex,
    LineType,
    Vector
)

def project_part_views(shape: Shape, part_id: str) -> dict[str, tuple]:
    """
    Project a 3D shape into 2D orthographic visible and hidden edges for three views:
    - 'top': XY projection (looking down from +Z)
    - 'front': XZ projection (looking from -Y)
    - 'side': YZ projection (looking from +X)
    """
    bb = shape.bounding_box()
    center = Vector(
        (bb.min.X + bb.max.X) / 2.0,
        (bb.min.Y + bb.max.Y) / 2.0,
        (bb.min.Z + bb.max.Z) / 2.0
    )
    
    # Calculate a safe distance (greater than shape bounding box diagonal)
    size = max(bb.max.X - bb.min.X, bb.max.Y - bb.min.Y, bb.max.Z - bb.min.Z)
    distance = max(1000.0, size * 10.0)
    
    # Standard Orthographic Viewports:
    # 1. Top View (XY): Viewport origin at +Z relative to center, Up along +Y
    top_origin = center + Vector(0.0, 0.0, distance)
    visible_top, hidden_top = shape.project_to_viewport(
        viewport_origin=top_origin,
        viewport_up=(0.0, 1.0, 0.0),
        look_at=center,
        focus=None
    )
    
    # 2. Front View (XZ): Viewport origin at -Y relative to center, Up along +Z
    front_origin = center + Vector(0.0, -distance, 0.0)
    visible_front, hidden_front = shape.project_to_viewport(
        viewport_origin=front_origin,
        viewport_up=(0.0, 0.0, 1.0),
        look_at=center,
        focus=None
    )
    
    # 3. Side View (YZ): Viewport origin at +X relative to center, Up along +Z
    side_origin = center + Vector(distance, 0.0, 0.0)
    visible_side, hidden_side = shape.project_to_viewport(
        viewport_origin=side_origin,
        viewport_up=(0.0, 0.0, 1.0),
        look_at=center,
        focus=None
    )
    
    return {
        "top": (visible_top, hidden_top),
        "front": (visible_front, hidden_front),
        "side": (visible_side, hidden_side),
    }

def export_part_snapshots(
    shape: Shape,
    part_id: str,
    output_dir: Path,
    metadata: dict[str, str] | None = None
) -> dict[str, Path]:
    """
    Generate 2D orthographic projections for 'top', 'front', and 'side' views,
    styled with black/visible and dashed-gray/hidden layers, and save them as SVGs.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    views = project_part_views(shape, part_id)
    saved_paths = {}
    
    # Determine bounding box of 3D shape for metadata
    bb = shape.bounding_box()
    dims = (bb.max.X - bb.min.X, bb.max.Y - bb.min.Y, bb.max.Z - bb.min.Z)
    
    for view_name, (visible_edges, hidden_edges) in views.items():
        # Setup SVG exporter
        max_dim_2d = max(dims[0], dims[1], dims[2])
        margin_val = max(5.0, max_dim_2d * 0.10)
        
        exporter = ExportSVG(unit=Unit.MM, margin=margin_val, fit_to_stroke=True)
        
        # Add visible layer: Black solid lines
        exporter.add_layer(
            "visible",
            line_color=ColorIndex.BLACK,
            line_weight=0.5,
            line_type=LineType.CONTINUOUS
        )
        # Add hidden layer: Gray dashed lines
        exporter.add_layer(
            "hidden",
            line_color=ColorIndex.GRAY,
            line_weight=0.3,
            line_type=LineType.DASHED
        )
        
        exporter.add_shape(visible_edges, layer="visible")
        exporter.add_shape(hidden_edges, layer="hidden")
        
        filename = f"{part_id}_{view_name}.svg"
        dest_path = output_dir / filename
        exporter.write(dest_path)
        
        # Post-process: Append metadata comment header to the XML file
        if dest_path.exists():
            content = dest_path.read_text(encoding="utf-8")
            meta_lines = [
                "<!--",
                f"  Part ID: {part_id}",
                f"  View: {view_name}",
                f"  Dimensions (X, Y, Z): {dims[0]:.2f} x {dims[1]:.2f} x {dims[2]:.2f} mm",
                f"  Generated: {datetime.datetime.now().isoformat()}",
            ]
            if metadata:
                for k, v in metadata.items():
                    meta_lines.append(f"  {k}: {v}")
            meta_lines.extend([
                "-->",
                ""
            ])
            # Prepend metadata at the top of the file
            if content.startswith("<?xml"):
                first_line_end = content.find("\n") + 1
                new_content = content[:first_line_end] + "\n".join(meta_lines) + content[first_line_end:]
            else:
                new_content = "\n".join(meta_lines) + content
            dest_path.write_text(new_content, encoding="utf-8")
            
        saved_paths[view_name] = dest_path
        
    return saved_paths
