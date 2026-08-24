from pathlib import Path
from build123d import Box, Location, Plane, Solid, Sphere, Torus, Vector
from flow_cad.core.snapshots import project_part_views, export_part_snapshots

def test_project_part_views() -> None:
    # Build a simple box
    shape = Box(10, 20, 30)
    views = project_part_views(shape, "test_box")
    
    assert "top" in views
    assert "front" in views
    assert "side" in views
    
    for view_name in ("top", "front", "side"):
        visible, hidden = views[view_name]
        assert len(visible) > 0
        # For a simple box, there are no internal hidden features, so hidden is likely empty
        assert isinstance(visible, list) or hasattr(visible, "__iter__")
        assert isinstance(hidden, list) or hasattr(hidden, "__iter__")

def test_export_part_snapshots(tmp_path: Path) -> None:
    shape = Box(15, 25, 35)
    saved_paths = export_part_snapshots(
        shape=shape,
        part_id="test_part",
        output_dir=tmp_path,
        metadata={"Project": "Flow-Test"}
    )
    
    assert "top" in saved_paths
    assert "front" in saved_paths
    assert "side" in saved_paths
    
    for view_name in ("top", "front", "side"):
        path = saved_paths[view_name]
        assert path.exists()
        assert path.suffix == ".svg"
        
        content = path.read_text(encoding="utf-8")
        assert "<?xml" in content
        assert "<svg" in content
        assert "id=\"visible\"" in content
        assert "id=\"hidden\"" in content
        
        # Verify metadata comments are present
        assert "Part ID: test_part" in content
        assert f"View: {view_name}" in content
        assert "Dimensions (X, Y, Z): 15.00 x 25.00 x 35.00 mm" in content
        assert "Project: Flow-Test" in content


def test_export_part_snapshots_handles_nearly_closed_projected_conics(
    tmp_path: Path,
) -> None:
    path_points = []
    for index in range(13):
        fraction = index / 12
        path_points.append(
            Vector(
                102.0 - (102.0 - 34.0) * fraction**1.65,
                0.0,
                6.0 + (130.0 - 6.0) * fraction,
            )
        )

    arm = Sphere(5.9).solid().moved(Location(path_points[0]))
    for start, end in zip(path_points, path_points[1:]):
        segment = end - start
        arm = (
            arm
            + Solid.make_cylinder(
                5.9,
                segment.length,
                Plane(origin=start, z_dir=segment.normalized()),
            )
            + Sphere(5.9).solid().moved(Location(end))
        )

    arms = tuple(
        arm.moved(Location((0.0, 0.0, 0.0), (0.0, 0.0, angle)))
        for angle in (45.0, 135.0, 225.0, 315.0)
    )
    shape = Torus(34.0, 6.0).solid().moved(Location((0.0, 0.0, 130.0)))
    shape = shape.fuse(*arms)

    saved_paths = export_part_snapshots(
        shape=shape,
        part_id="curved_guard",
        output_dir=tmp_path,
    )

    assert set(saved_paths) == {"top", "front", "side"}
    assert all(path.stat().st_size > 0 for path in saved_paths.values())
