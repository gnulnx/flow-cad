from __future__ import annotations

import subprocess
import sys


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
