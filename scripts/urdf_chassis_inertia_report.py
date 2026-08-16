#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from flow_cad.urdf_inertia_report import main


if __name__ == "__main__":
    raise SystemExit(main())
