#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
freecadcmd="/Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd"

run_freecad_script() {
  local script_path="$1"
  "${freecadcmd}" -c "g={'__file__':'${script_path}','__name__':'__main__'}; exec(open('${script_path}', encoding='utf-8').read(), g)"
}

run_freecad_script "${project_root}/freecad/erb_bottom_tray_native.py"
run_freecad_script "${project_root}/freecad/erb_bottom_tray_part_design.py"
run_freecad_script "${project_root}/freecad/erb_battery_cassette_native.py"
