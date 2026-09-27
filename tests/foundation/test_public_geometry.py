from __future__ import annotations

import subprocess
import sys

import pytest

from flow_cad.geometry import (
    StructuralNode,
    StructuralPath,
    build_structural_network,
    sample_structural_path,
)


def test_public_geometry_helpers_are_lazy_until_explicitly_imported() -> None:
    script = """
import sys
import flow_cad.sdk
assert 'build123d' not in sys.modules
import flow_cad.geometry as geometry
assert 'build123d' in sys.modules
assert geometry.__all__ == sorted(geometry.__all__)
assert geometry.box_at((1, 2, 3), (0, 0, 0)).volume == 6.0
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_structural_path_sampling_is_curved_tapered_and_deterministic() -> None:
    nodes = (
        StructuralNode("root", (0.0, 0.0, 0.0), 6.0),
        StructuralNode("tip", (40.0, 0.0, 30.0), 4.0),
    )
    path = StructuralPath(
        "rib",
        "root",
        "tip",
        start_radius=5.0,
        end_radius=2.5,
        controls=((8.0, 18.0, 4.0), (28.0, 12.0, 26.0)),
        samples=6,
    )

    first = sample_structural_path(nodes, path)
    second = sample_structural_path(nodes, path)

    assert first == second
    assert first[0] == ((0.0, 0.0, 0.0), 5.0)
    assert first[-1] == ((40.0, 0.0, 30.0), 2.5)
    assert max(point[1] for point, _radius in first[1:-1]) > 8.0
    assert [radius for _point, radius in first] == sorted(
        (radius for _point, radius in first), reverse=True
    )


def test_structural_network_builds_labeled_junctions_and_member() -> None:
    nodes = (
        StructuralNode("root", (0.0, 0.0, 0.0), 6.0),
        StructuralNode("tip", (40.0, 0.0, 30.0), 4.0),
    )
    paths = (
        StructuralPath(
            "rib",
            "root",
            "tip",
            start_radius=5.0,
            end_radius=5.0,
            controls=((12.0, 10.0, 12.0),),
            samples=4,
        ),
    )

    network = build_structural_network(nodes, paths, label="test_network")
    bounds = network.bounding_box()

    assert network.label == "test_network"
    assert [child.label for child in network.children] == [
        "node:root",
        "node:tip",
        "path:rib",
    ]
    assert network.volume > 0.0
    assert len(network.children[2].solids()) == 8
    assert bounds.min.X < 0.0
    assert bounds.max.X > 40.0
    assert bounds.max.Z > 30.0


@pytest.mark.parametrize(
    "nodes,path,message",
    [
        (
            (
                StructuralNode("same", (0.0, 0.0, 0.0), 4.0),
                StructuralNode("same", (10.0, 0.0, 0.0), 4.0),
            ),
            StructuralPath("rib", "same", "missing", 3.0, 2.0),
            "unique",
        ),
        (
            (StructuralNode("root", (0.0, 0.0, 0.0), 4.0),),
            StructuralPath("rib", "root", "missing", 3.0, 2.0),
            "unknown",
        ),
        (
            (
                StructuralNode("root", (0.0, 0.0, 0.0), 4.0),
                StructuralNode("tip", (10.0, 0.0, 0.0), 4.0),
            ),
            StructuralPath("rib", "root", "tip", 3.0, 2.0, samples=0),
            "samples",
        ),
    ],
)
def test_structural_network_rejects_invalid_graphs(nodes, path, message) -> None:
    with pytest.raises(ValueError, match=message):
        build_structural_network(nodes, (path,))
