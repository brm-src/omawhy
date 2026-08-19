#!/usr/bin/env bash
set -euo pipefail

CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
if [[ -f "$CONFIG_HOME/hypr/hyprland.lua" ]]; then
  BINDINGS_FILE="$CONFIG_HOME/hypr/bindings.lua"
  FORMAT="lua"
  BEGIN="-- OmaWhy: begin"
  END="-- OmaWhy: end"
else
  BINDINGS_FILE="$CONFIG_HOME/hypr/bindings.conf"
  FORMAT="conf"
  BEGIN="# OmaWhy: begin"
  END="# OmaWhy: end"
fi

python3 - "$BINDINGS_FILE" "$BEGIN" "$END" "$FORMAT" "${1:-}" <<'PY'
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
begin, end, file_format, mode = sys.argv[2:]
text = path.read_text(encoding="utf-8") if path.exists() else ""
if file_format == "lua":
    binding = 'o.bind("SUPER + SHIFT + I", "OmaWhy", "omarchy-shell shell toggle io.github.brm-src.omawhy \'{}\'")'
else:
    binding = "bindd = SUPER SHIFT, I, OmaWhy, exec, omarchy-shell shell toggle io.github.brm-src.omawhy '{}'"
block = "\n".join([
    begin,
    binding,
    end,
    "",
])
pattern = re.compile(re.escape(begin) + r"\n.*?" + re.escape(end) + r"\n?", re.DOTALL)
if mode == "--remove":
    updated = pattern.sub("", text)
else:
    updated = text if pattern.search(text) else text.rstrip("\n") + ("\n" if text else "") + block
path.parent.mkdir(parents=True, exist_ok=True)
temporary = path.with_name(path.name + ".omawhy.tmp")
temporary.write_text(updated, encoding="utf-8")
temporary.replace(path)
PY

if command -v hyprctl >/dev/null 2>&1; then
  hyprctl reload >/dev/null 2>&1 || true
fi

if [[ "${1:-}" == "--remove" ]]; then
  printf 'Atajo de OmaWhy eliminado.\n'
else
  printf 'OmaWhy listo: Super + Shift + I.\n'
fi
