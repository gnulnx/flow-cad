from __future__ import annotations
from dataclasses import dataclass
import math
from build123d import (
    Box,
    BuildPart,
    BuildSketch,
    Compound,
    Cylinder,
    Location,
    Plane,
    Polygon,
    Rectangle,
    Solid,
    Sphere,
    Vector,
    chamfer,
    extrude,
    loft,
)

Point3D = tuple[float, float, float]


@dataclass(frozen=True)
class StructuralNode:
    """Named attachment or load-junction point in a structural graph."""

    key: str
    position: Point3D
    radius: float


@dataclass(frozen=True)
class StructuralPath:
    """Curved, tapered structural edge between two named graph nodes."""

    key: str
    start: str
    end: str
    start_radius: float
    end_radius: float
    controls: tuple[Point3D, ...] = ()
    samples: int = 8


def _point_vector(point: Point3D) -> Vector:
    return Vector(*point)


def _bezier_point(points: tuple[Vector, ...], t: float) -> Vector:
    """Evaluate a Bezier curve of arbitrary degree with de Casteljau steps."""

    working = list(points)
    while len(working) > 1:
        working = [
            left * (1.0 - t) + right * t
            for left, right in zip(working, working[1:])
        ]
    return working[0]


def sample_structural_path(
    nodes: tuple[StructuralNode, ...],
    path: StructuralPath,
) -> tuple[tuple[Point3D, float], ...]:
    """Return deterministic centerline and radius samples for one graph edge."""

    if path.samples < 1:
        raise ValueError("structural path samples must be at least 1")
    if path.start_radius <= 0.0 or path.end_radius <= 0.0:
        raise ValueError("structural path radii must be positive")

    node_by_key = {node.key: node for node in nodes}
    if len(node_by_key) != len(nodes):
        raise ValueError("structural node keys must be unique")
    try:
        start = node_by_key[path.start]
        end = node_by_key[path.end]
    except KeyError as exc:
        raise ValueError(f"unknown structural path node: {exc.args[0]}") from exc
    if start.key == end.key:
        raise ValueError("structural path endpoints must be different nodes")

    control_vectors = (
        _point_vector(start.position),
        *(_point_vector(point) for point in path.controls),
        _point_vector(end.position),
    )
    samples: list[tuple[Point3D, float]] = []
    for index in range(path.samples + 1):
        t = index / path.samples
        point = _bezier_point(control_vectors, t)
        radius = path.start_radius + (path.end_radius - path.start_radius) * t
        samples.append(((point.X, point.Y, point.Z), radius))
    return tuple(samples)


def build_structural_network(
    nodes: tuple[StructuralNode, ...],
    paths: tuple[StructuralPath, ...],
    *,
    fuse: bool = False,
    label: str = "structural_network",
):
    """Build an organic BREP graph from tapered members and junction bodies.

    Each path is a sampled Bezier centerline. Consecutive samples are joined by
    tapered conical solids and blended with overlapping spheres. Node spheres
    widen attachment and branching regions. ``fuse=False`` preserves labeled
    path/node children for fast concept work; ``fuse=True`` returns their
    boolean union for downstream single-body workflows.
    """

    if not nodes:
        raise ValueError("structural network requires at least one node")
    node_by_key = {node.key: node for node in nodes}
    if len(node_by_key) != len(nodes):
        raise ValueError("structural node keys must be unique")
    if any(not node.key for node in nodes):
        raise ValueError("structural node keys cannot be empty")
    if any(node.radius <= 0.0 for node in nodes):
        raise ValueError("structural node radii must be positive")
    if len({path.key for path in paths}) != len(paths):
        raise ValueError("structural path keys must be unique")

    children = []
    for node in nodes:
        junction = Sphere(node.radius).solid().moved(Location(node.position))
        junction.label = f"node:{node.key}"
        children.append(junction)

    for path in paths:
        samples = sample_structural_path(nodes, path)
        path_children = []
        for (start_point, start_radius), (end_point, end_radius) in zip(
            samples, samples[1:]
        ):
            start_vector = _point_vector(start_point)
            end_vector = _point_vector(end_point)
            segment_vector = end_vector - start_vector
            if segment_vector.length <= 1e-6:
                raise ValueError(f"structural path {path.key!r} has a zero-length segment")
            member_plane = Plane(
                origin=start_vector,
                z_dir=segment_vector.normalized(),
            )
            if math.isclose(start_radius, end_radius, rel_tol=0.0, abs_tol=1e-9):
                member = Solid.make_cylinder(
                    start_radius,
                    segment_vector.length,
                    member_plane,
                )
            else:
                member = Solid.make_cone(
                    start_radius,
                    end_radius,
                    segment_vector.length,
                    member_plane,
                )
            blend = Sphere(end_radius).solid().moved(Location(end_vector))
            path_children.extend((member, blend))
        path_shape = Compound(label=f"path:{path.key}", children=path_children)
        children.append(path_shape)

    if fuse:
        network = fused_shapes(*children)
        network.label = label
        return network
    return Compound(label=label, children=children)

def box_at(size: tuple[float, float, float], center: tuple[float, float, float]):
    return Box(*size).moved(Location(center))

def cyl_x(radius: float, length: float, center: tuple[float, float, float]):
    return Cylinder(radius, length, rotation=(0, 90, 0)).moved(Location(center))

def cyl_y(radius: float, length: float, center: tuple[float, float, float]):
    return Cylinder(radius, length, rotation=(90, 0, 0)).moved(Location(center))

def cyl_z(radius: float, length: float, center: tuple[float, float, float]):
    return Cylinder(radius, length).moved(Location(center))

def vertical_slot_y(radius: float, height_z: float, length_y: float, center: tuple[float, float, float]):
    """Create a vertical obround slot cutting along Y."""
    x, y, z = center
    if height_z <= 2.0 * radius:
        return cyl_y(radius, length_y, center)
    slot = box_at((2.0 * radius, length_y, height_z - 2.0 * radius), center)
    slot += cyl_y(radius, length_y, (x, y, z - height_z / 2.0 + radius))
    slot += cyl_y(radius, length_y, (x, y, z + height_z / 2.0 - radius))
    return slot

def horizontal_slot_z(
    radius: float,
    length_x: float,
    length_y: float,
    cut_height: float,
    center: tuple[float, float, float],
):
    """Create a rounded rectangular through-slot cutting along Z."""
    x, y, z = center
    length_x = max(length_x, 2.0 * radius)
    length_y = max(length_y, 2.0 * radius)
    slot = box_at((length_x, length_y - 2.0 * radius, cut_height), center)
    slot += box_at((length_x - 2.0 * radius, length_y, cut_height), center)
    for sx in (-1, 1):
        for sy in (-1, 1):
            slot += cyl_z(
                radius,
                cut_height,
                (
                    x + sx * (length_x / 2.0 - radius),
                    y + sy * (length_y / 2.0 - radius),
                    z,
                ),
            )
    return slot

def xy_polygon_prism(
    points: tuple[tuple[float, float], ...],
    height: float,
    center_z: float,
):
    with BuildPart() as prism:
        with BuildSketch(Plane.XY):
            Polygon(*points, align=None)
        extrude(amount=height / 2.0, both=True)
    return prism.part.moved(Location((0.0, 0.0, center_z)))

def safe_chamfer(shape, amount: float):
    fallback = shape if hasattr(shape, "bounding_box") else Compound(children=list(shape))
    try:
        chamfered = chamfer(fallback.edges(), amount)
        return chamfered if hasattr(chamfered, "bounding_box") else fallback
    except Exception:
        return fallback

def solid_shape(shape):
    return shape if hasattr(shape, "bounding_box") else Compound(children=list(shape))

def fused_shapes(*shapes):
    result = solid_shape(shapes[0])
    for shape in shapes[1:]:
        result = solid_shape(result.fuse(solid_shape(shape)))
    try:
        return result.clean()
    except Exception:
        return result

def double_d_points(diameter: float, flat_to_flat: float, segments: int = 24):
    """Return a double-D profile clipped by two horizontal flats."""
    radius = diameter / 2.0
    half_flat = flat_to_flat / 2.0
    if half_flat >= radius:
        raise ValueError("flat_to_flat must be smaller than diameter")

    theta = math.asin(half_flat / radius)
    pts: list[tuple[float, float]] = []

    # Right circular side, top flat to bottom flat.
    for i in range(segments + 1):
        t = theta + (-2.0 * theta) * (i / segments)
        pts.append((radius * math.cos(t), radius * math.sin(t)))

    # Bottom flat.
    pts.append((-radius * math.cos(theta), -half_flat))

    # Left circular side, bottom flat to top flat.
    for i in range(segments + 1):
        t = math.pi + theta + (-2.0 * theta) * (i / segments)
        pts.append((radius * math.cos(t), radius * math.sin(t)))

    # Top flat.
    pts.append((radius * math.cos(theta), half_flat))
    return pts

def double_d_prism(
    diameter: float,
    flat_to_flat: float,
    length: float,
    center: tuple[float, float, float],
):
    with BuildPart() as prism:
        with BuildSketch(Plane.YZ):
            Polygon(*double_d_points(diameter, flat_to_flat), align=None)
        extrude(amount=length / 2.0, both=True)
    return prism.part.moved(Location(center))

def chamfered_rect_points(width: float, height: float, corner_chamfer: float):
    """Return a rectangular profile with clipped corners."""
    half_w = width / 2.0
    half_h = height / 2.0
    c = min(corner_chamfer, half_w - 0.1, half_h - 0.1)
    return (
        (-half_w + c, -half_h),
        (half_w - c, -half_h),
        (half_w, -half_h + c),
        (half_w, half_h - c),
        (half_w - c, half_h),
        (-half_w + c, half_h),
        (-half_w, half_h - c),
        (-half_w, -half_h + c),
    )

def chamfered_yz_rect_prism(
    width_y: float,
    height_z: float,
    corner_chamfer: float,
    length_x: float,
    center: tuple[float, float, float],
):
    with BuildPart() as prism:
        with BuildSketch(Plane.YZ):
            Polygon(*chamfered_rect_points(width_y, height_z, corner_chamfer), align=None)
        extrude(amount=length_x / 2.0, both=True)
    return prism.part.moved(Location(center))

def chamfered_xy_rect_prism(
    width_x: float,
    depth_y: float,
    corner_chamfer: float,
    height_z: float,
    center: tuple[float, float, float],
):
    with BuildPart() as prism:
        with BuildSketch(Plane.XY):
            Polygon(*chamfered_rect_points(width_x, depth_y, corner_chamfer), align=None)
        extrude(amount=height_z / 2.0, both=True)
    return prism.part.moved(Location(center))

def tapered_xz_rect_loft(
    width_base: float,
    height_base: float,
    y_base: float,
    width_face: float,
    height_face: float,
    y_face: float,
    center_z: float,
):
    """Create a tapered rectangular loft between two XZ profiles."""
    with BuildPart() as part:
        with BuildSketch(Plane.XZ.offset(-y_base)):
            Rectangle(width_base, height_base)
        with BuildSketch(Plane.XZ.offset(-y_face)):
            Rectangle(width_face, height_face)
        loft()
    return part.part.moved(Location((0.0, 0.0, center_z)))

def triangular_yz_prism(
    points: tuple[tuple[float, float], tuple[float, float], tuple[float, float]],
    thickness_x: float,
    center_x: float,
):
    """Create a triangular web in the YZ plane extruded through X."""
    with BuildPart() as prism:
        with BuildSketch(Plane.YZ):
            Polygon(*points, align=None)
        extrude(amount=thickness_x, both=True)
    return prism.part.moved(Location((center_x, 0.0, 0.0)))

def triangular_xz_prism(
    points: tuple[tuple[float, float], tuple[float, float], tuple[float, float]],
    thickness_y: float,
    center_y: float,
):
    """Create a triangular web in the XZ plane extruded through Y."""
    with BuildPart() as prism:
        with BuildSketch(Plane.XZ):
            Polygon(*points, align=None)
        extrude(amount=thickness_y / 2.0, both=True)
    return prism.part.moved(Location((0.0, center_y, 0.0)))

def xz_profile_prism(
    points: tuple[tuple[float, float], ...],
    depth_y: float,
    center_y: float = 0.0,
):
    """Create a constant-depth part from an XZ cross-section."""
    with BuildPart() as prism:
        with BuildSketch(Plane.XZ):
            Polygon(*points, align=None)
        extrude(amount=depth_y / 2.0, both=True)
    return prism.part.moved(Location((0.0, center_y, 0.0)))

def add_diagonal_rib(
    shape, 
    inward: int, 
    start: tuple[float, float], 
    end: tuple[float, float],
    thickness: float,
    projection: float,
):
    y0, z0 = start
    y1, z1 = end
    dy = y1 - y0
    dz = z1 - z0
    length = math.hypot(dy, dz)
    angle = math.degrees(math.atan2(dz, dy))
    center_y = (y0 + y1) / 2.0
    center_z = (z0 + z1) / 2.0
    center_x = inward * (thickness + projection / 2.0)
    rib = Box(
        projection,
        length,
        13.0,
        rotation=(angle, 0, 0),
    ).moved(Location((center_x, center_y, center_z)))
    return shape + rib

def xz_rect(center_x: float, center_z: float, width: float, height: float):
    return (
        center_x - width / 2.0,
        center_x + width / 2.0,
        center_z - height / 2.0,
        center_z + height / 2.0,
    )

def xz_rects_overlap_with_clearance(a, b, clearance: float) -> bool:
    return not (
        a[1] + clearance <= b[0]
        or b[1] + clearance <= a[0]
        or a[3] + clearance <= b[2]
        or b[3] + clearance <= a[2]
    )

def panel_dovetail_points(
    side: int,
    base_x: float,
    center_y: float,
    depth: float,
    neck_width: float,
    head_width: float,
) -> tuple[tuple[float, float], ...]:
    if side not in (-1, 1):
        raise ValueError("side must be -1 or 1")
    tip_x = base_x + side * depth
    if side > 0:
        return (
            (base_x, center_y - neck_width / 2.0),
            (tip_x, center_y - head_width / 2.0),
            (tip_x, center_y + head_width / 2.0),
            (base_x, center_y + neck_width / 2.0),
        )
    return (
        (base_x, center_y - neck_width / 2.0),
        (base_x, center_y + neck_width / 2.0),
        (tip_x, center_y + head_width / 2.0),
        (tip_x, center_y - head_width / 2.0),
    )

def panel_dovetail_prism(
    side: int,
    base_x: float,
    center_y: float,
    depth: float,
    neck_width: float,
    head_width: float,
    z_min: float,
    z_max: float,
):
    return xy_polygon_prism(
        panel_dovetail_points(side, base_x, center_y, depth, neck_width, head_width),
        z_max - z_min,
        (z_min + z_max) / 2.0,
    )
