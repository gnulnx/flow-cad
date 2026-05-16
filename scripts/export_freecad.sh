#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export_script="${project_root}/scripts/export_freecad.py"

/Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd -c \
  "g={'__file__':'${export_script}','__name__':'__main__'}; exec(open('${export_script}', encoding='utf-8').read(), g)"
