#!/usr/bin/env bash
set -euo pipefail
src=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
target="${XDG_CONFIG_HOME:-$HOME/.config}/omarchy/plugins/io.github.adamtcroft.pipewire-control"
if [[ ! -L "$target" || $(readlink -f "$target") != "$src" ]]; then
  echo "Refusing to remove a plugin link not owned by this checkout." >&2
  exit 1
fi
omarchy plugin disable io.github.adamtcroft.pipewire-control
unlink "$target"
omarchy-shell shell rescanPlugins
echo 'Plugin removed. Source, saved audio defaults and current overrides are preserved.'
echo 'Clear saved defaults before uninstalling using Clear defaults in the popup, if desired.'
