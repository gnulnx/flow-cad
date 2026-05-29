from pathlib import Path
from build123d import Box
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
