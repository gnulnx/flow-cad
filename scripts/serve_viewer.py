#!/usr/bin/env python3
"""Start the STL viewer development server.

Usage:
    python scripts/serve_viewer.py           # serves viewer on port 3000
    python scripts/serve_viewer.py 3001      # custom port
"""
import argparse
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Start 3D viewer server")
    parser.add_argument("port", nargs="?", type=int, default=3000, help="Port to serve on")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    viewer_dir = repo_root / "viewer" / "stl-viewer"
    if not (viewer_dir / "node_modules").exists():
        print("ERROR: viewer dependencies are missing. Run: npm --prefix viewer/stl-viewer install")
        sys.exit(1)

    url = f"http://127.0.0.1:{args.port}/"
    print(f"3D Viewer ready at: {url}")
    print("Load generated STLs with URLs like:")
    print(f"{url}?stl=/exports/stl/lower_chassis/b3_lower_chassis_simple_mounting_plate.stl")
    print("Drag/drop or Open File also work.")
    subprocess.run(
        ["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", str(args.port)],
        cwd=viewer_dir,
        check=True,
    )


if __name__ == "__main__":
    main()
