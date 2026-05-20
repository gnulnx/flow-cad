from __future__ import annotations
import os
import datetime
import re
from pathlib import Path
from build123d import (
    Shape,
    ExportSVG,
    Unit,
    ColorIndex,
    LineType,
    Vector,
    Compound
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

def get_edges_bounds(edges) -> tuple[float, float, float, float] | None:
    """
    Safely find the 2D bounding box of a collection of edges.
    Returns (min_x, max_x, min_y, max_y) or None if empty.
    """
    if not edges:
        return None
    try:
        if isinstance(edges, Shape):
            bb = edges.bounding_box()
            return bb.min.X, bb.max.X, bb.min.Y, bb.max.Y
            
        valid_edges = [e for e in edges if e is not None]
        if not valid_edges:
            return None
            
        comp = Compound(valid_edges)
        bb = comp.bounding_box()
        return bb.min.X, bb.max.X, bb.min.Y, bb.max.Y
    except Exception:
        return None

def export_part_snapshots(
    shape: Shape,
    part_id: str,
    output_dir: Path,
    metadata: dict[str, str] | None = None
) -> dict[str, Path]:
    """
    Generate 2D orthographic projections for 'top', 'front', and 'side' views,
    styled with black/visible and dashed-gray/hidden layers, auto-dimensioned,
    annotated with technical drawings sheets layout, and saved as SVGs.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    views = project_part_views(shape, part_id)
    saved_paths = {}
    
    # Determine bounding box of 3D shape for dimensions
    bb = shape.bounding_box()
    dims = (bb.max.X - bb.min.X, bb.max.Y - bb.min.Y, bb.max.Z - bb.min.Z)
    max_dim_3d = max(dims[0], dims[1], dims[2])
    
    for view_name, (visible_edges, hidden_edges) in views.items():
        # Setup SVG exporter with generous margin to clear dimension annotations
        margin_val = max(15.0, max_dim_3d * 0.15)
        exporter = ExportSVG(unit=Unit.MM, margin=margin_val, fit_to_stroke=True)
        
        # Add visible layer: Black solid lines
        exporter.add_layer(
            "visible",
            line_color=ColorIndex.BLACK,
            line_weight=0.4,
            line_type=LineType.CONTINUOUS
        )
        # Add hidden layer: Gray dashed lines
        exporter.add_layer(
            "hidden",
            line_color=ColorIndex.GRAY,
            line_weight=0.25,
            line_type=LineType.DASHED
        )
        
        exporter.add_shape(visible_edges, layer="visible")
        exporter.add_shape(hidden_edges, layer="hidden")
        
        filename = f"{part_id}_{view_name}.svg"
        dest_path = output_dir / filename
        exporter.write(dest_path)
        
        # Post-process: Add background, grids, dimensions and text labels
        if dest_path.exists():
            content = dest_path.read_text(encoding="utf-8")
            
            # Find 2D projected geometry bounds
            bounds_vis = get_edges_bounds(visible_edges)
            bounds_hid = get_edges_bounds(hidden_edges)
            
            min_xs = [b[0] for b in [bounds_vis, bounds_hid] if b is not None]
            max_xs = [b[1] for b in [bounds_vis, bounds_hid] if b is not None]
            min_ys = [b[2] for b in [bounds_vis, bounds_hid] if b is not None]
            max_ys = [b[3] for b in [bounds_vis, bounds_hid] if b is not None]
            
            geom_min_x = min(min_xs) if min_xs else 0.0
            geom_max_x = max(max_xs) if max_xs else 0.0
            geom_min_y = min(min_ys) if min_ys else 0.0
            geom_max_y = max(max_ys) if max_ys else 0.0
            
            # Calculate physical dimensions in projected view plane
            width_mm = geom_max_x - geom_min_x
            height_mm = geom_max_y - geom_min_y
            
            # Screen coords map from geom coordinates: Y is inverted by scale(1,-1)
            screen_x_left = geom_min_x
            screen_x_right = geom_max_x
            screen_y_top = -geom_max_y
            screen_y_bottom = -geom_min_y
            
            # Extract viewBox values
            vb_min_x, vb_min_y, vb_w, vb_h = 0.0, 0.0, 100.0, 100.0
            vb_match = re.search(r'viewBox="([^"]+)"', content)
            if vb_match:
                try:
                    vb = [float(x) for x in vb_match.group(1).split()]
                    if len(vb) == 4:
                        vb_min_x, vb_min_y, vb_w, vb_h = vb
                except Exception:
                    pass
            
            max_vb_dim = max(vb_w, vb_h)
            
            # 1. Background, rounded sheet border, and subtle grid alignment marks
            bg_xml = [
                f'  <rect width="100%" height="100%" fill="#ffffff" />',
                f'  <rect x="{vb_min_x + 0.5}" y="{vb_min_y + 0.5}" width="{vb_w - 1.0}" height="{vb_h - 1.0}" fill="none" stroke="#e2e8f0" stroke-width="0.5" rx="2" />'
            ]
            
            # Grid dots spaced every 10mm
            grid_xml = []
            grid_start_x = int(vb_min_x / 10) * 10
            grid_end_x = int((vb_min_x + vb_w) / 10) * 10 + 10
            grid_start_y = int(vb_min_y / 10) * 10
            grid_end_y = int((vb_min_y + vb_h) / 10) * 10 + 10
            for gx in range(grid_start_x, grid_end_x, 10):
                for gy in range(grid_start_y, grid_end_y, 10):
                    # Skip dots close to the card borders
                    if (vb_min_x + 2 < gx < vb_min_x + vb_w - 2) and (vb_min_y + 2 < gy < vb_min_y + vb_h - 2):
                        grid_xml.append(f'  <circle cx="{gx}" cy="{gy}" r="0.15" fill="#cbd5e1" />')
            
            # 2. Premium title block header (clean modern industrial typography)
            title_font_size = max(3.0, max_vb_dim * 0.024)
            sub_font_size = max(2.0, max_vb_dim * 0.016)
            
            title_xml = [
                f'  <!-- Header block -->',
                f'  <text x="{vb_min_x + 6}" y="{vb_min_y + 9}" font-family="sans-serif" font-size="{title_font_size:.2f}" font-weight="bold" fill="#1e293b">{part_id}</text>',
                f'  <text x="{vb_min_x + 6}" y="{vb_min_y + 9 + title_font_size * 1.25}" font-family="sans-serif" font-size="{sub_font_size:.2f}" fill="#64748b" font-weight="600">{view_name.upper()} VIEW • {width_mm:.1f} × {height_mm:.1f} mm</text>'
            ]
            
            # 3. Dynamic geometry dimensioning (if part has valid physical size)
            dim_xml = []
            dim_font_size = max(2.2, max_vb_dim * 0.018)
            
            if width_mm > 0.01 and height_mm > 0.01:
                # Horizontal dimension line (Width) placed below geometry
                offset_y = 12.0
                dim_y = screen_y_bottom + offset_y
                if dim_y > vb_min_y + vb_h - 6:
                    dim_y = vb_min_y + vb_h - 6
                
                # Extension and dimension lines
                dim_xml.append(f'  <line x1="{screen_x_left}" y1="{screen_y_bottom}" x2="{screen_x_left}" y2="{dim_y + 1.5}" stroke="#94a3b8" stroke-width="0.2" stroke-dasharray="1,1" />')
                dim_xml.append(f'  <line x1="{screen_x_right}" y1="{screen_y_bottom}" x2="{screen_x_right}" y2="{dim_y + 1.5}" stroke="#94a3b8" stroke-width="0.2" stroke-dasharray="1,1" />')
                dim_xml.append(f'  <line x1="{screen_x_left}" y1="{dim_y}" x2="{screen_x_right}" y2="{dim_y}" stroke="#64748b" stroke-width="0.25" />')
                
                # Architectural ticks (slash marks)
                dim_xml.append(f'  <line x1="{screen_x_left - 0.7}" y1="{dim_y + 0.7}" x2="{screen_x_left + 0.7}" y2="{dim_y - 0.7}" stroke="#334155" stroke-width="0.4" />')
                dim_xml.append(f'  <line x1="{screen_x_right - 0.7}" y1="{dim_y + 0.7}" x2="{screen_x_right + 0.7}" y2="{dim_y - 0.7}" stroke="#334155" stroke-width="0.4" />')
                
                # Label middle text
                dim_xml.append(f'  <text x="{(screen_x_left + screen_x_right) / 2.0}" y="{dim_y - 1.0}" font-family="sans-serif" font-size="{dim_font_size:.2f}" fill="#334155" text-anchor="middle" font-weight="600">{width_mm:.1f} mm</text>')
                
                # Vertical dimension line (Height) placed to the right of geometry
                offset_x = 12.0
                dim_x = screen_x_right + offset_x
                if dim_x > vb_min_x + vb_w - 6:
                    dim_x = vb_min_x + vb_w - 6
                
                # Extension and dimension lines
                dim_xml.append(f'  <line x1="{screen_x_right}" y1="{screen_y_top}" x2="{dim_x + 1.5}" y2="{screen_y_top}" stroke="#94a3b8" stroke-width="0.2" stroke-dasharray="1,1" />')
                dim_xml.append(f'  <line x1="{screen_x_right}" y1="{screen_y_bottom}" x2="{dim_x + 1.5}" y2="{screen_y_bottom}" stroke="#94a3b8" stroke-width="0.2" stroke-dasharray="1,1" />')
                dim_xml.append(f'  <line x1="{dim_x}" y1="{screen_y_top}" x2="{dim_x}" y2="{screen_y_bottom}" stroke="#64748b" stroke-width="0.25" />')
                
                # Architectural ticks (slash marks)
                dim_xml.append(f'  <line x1="{dim_x - 0.7}" y1="{screen_y_top + 0.7}" x2="{dim_x + 0.7}" y2="{screen_y_top - 0.7}" stroke="#334155" stroke-width="0.4" />')
                dim_xml.append(f'  <line x1="{dim_x - 0.7}" y1="{screen_y_bottom + 0.7}" x2="{dim_x + 0.7}" y2="{screen_y_bottom - 0.7}" stroke="#334155" stroke-width="0.4" />')
                
                # Label middle text rotated -90 degrees
                mid_y = (screen_y_top + screen_y_bottom) / 2.0
                text_x = dim_x + 2.0
                dim_xml.append(f'  <text x="{text_x}" y="{mid_y}" font-family="sans-serif" font-size="{dim_font_size:.2f}" fill="#334155" text-anchor="middle" dominant-baseline="middle" transform="rotate(-90 {text_x} {mid_y})" font-weight="600">{height_mm:.1f} mm</text>')
            
            # Inject background card & grids right after <svg ...> tag
            svg_match = re.search(r'<svg[^>]*>', content)
            if svg_match:
                svg_tag_end = svg_match.end()
                bg_content = "\n" + "\n".join(bg_xml) + "\n" + "\n".join(grid_xml) + "\n"
                content = content[:svg_tag_end] + bg_content + content[svg_tag_end:]
            
            # Inject headers and dimension annotations right before </svg> tag
            close_index = content.rfind("</svg>")
            if close_index != -1:
                annotations_content = "\n" + "\n".join(title_xml) + "\n" + "\n".join(dim_xml) + "\n"
                content = content[:close_index] + annotations_content + content[close_index:]
            
            # Add metadata XML comments
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
            
            if content.startswith("<?xml"):
                first_line_end = content.find("\n") + 1
                new_content = content[:first_line_end] + "\n".join(meta_lines) + content[first_line_end:]
            else:
                new_content = "\n".join(meta_lines) + content
                
            dest_path.write_text(new_content, encoding="utf-8")
            
        saved_paths[view_name] = dest_path
        
    return saved_paths
