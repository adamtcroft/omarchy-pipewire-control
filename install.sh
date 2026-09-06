#!/usr/bin/env bash
set -euo pipefail
src=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
config=${XDG_CONFIG_HOME:-$HOME/.config}
target="$config/omarchy/plugins/io.github.adamtcroft.pipewire-control"
for cmd in python3 pw-metadata pw-top omarchy; do command -v "$cmd" >/dev/null || { echo "Missing dependency: $cmd" >&2; exit 1; }; done
omarchy plugin validate "$src"
mkdir -p "$(dirname "$target")"
if [[ -e "$target" || -L "$target" ]]; then
  [[ $(readlink -f "$target") == "$src" ]] || { echo "Refusing to replace $target" >&2; exit 1; }
else
  ln -s "$src" "$target"
fi
if [[ -f "$config/omarchy/shell.json" ]]; then
  cp -p "$config/omarchy/shell.json" "$config/omarchy/shell.json.pipewire-control-backup.$(date +%s%N)"
fi
omarchy-shell shell rescanPlugins
omarchy plugin enable io.github.adamtcroft.pipewire-control --section right
echo 'Installed. Click the equalizer icon in the bar. No audio settings were changed.'
echo 'If QML is cached after an update, run: omarchy restart shell'
