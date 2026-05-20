#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export_script="${project_root}/scripts/export_freecad.py"

if [[ -f "${project_root}/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "${project_root}/.env"
  set +a
fi

if [[ -n "${FREECAD_CMD:-}" ]]; then
  freecadcmd="${FREECAD_CMD}"
elif command -v freecadcmd >/dev/null 2>&1; then
  freecadcmd="$(command -v freecadcmd)"
elif command -v FreeCADCmd >/dev/null 2>&1; then
  freecadcmd="$(command -v FreeCADCmd)"
elif [[ -x "/Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd" ]]; then
  freecadcmd="/Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd"
else
  echo "FreeCAD command not found. Set FREECAD_CMD to your freecadcmd executable." >&2
  exit 127
fi

"${freecadcmd}" -c \
  "g={'__file__':'${export_script}','__name__':'__main__'}; exec(open('${export_script}', encoding='utf-8').read(), g)"
