#!/usr/bin/env python3
"""Small local PipeWire controller. No external Python dependencies."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

RATES = (0, 44100, 48000, 88200, 96000)
BUFFERS = (0, 64, 128, 256, 512, 1024, 2048)
MARKER = '# Owned by io.github.adamtcroft.pipewire-control\n'
CONFIG = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'pipewire/pipewire.conf.d/90-pipewire-control.conf'


def run(args):
    return subprocess.run(args, text=True, capture_output=True, check=True, timeout=8,
                          env={**os.environ, 'LC_ALL': 'C'}).stdout


def metadata():
    text = run(['pw-metadata', '-n', 'settings'])
    return dict(re.findall(r"key:'([^']+)' value:'([^']*)'", text))


def hardware(root=Path('/proc/asound')):
    rows = []
    for path in sorted(root.glob('card*/stream*')):
        try:
            text = path.read_text()
        except OSError:
            continue  # Device unplugged while reading /proc.
        if not text.strip():
            continue
        rates = sorted(set(re.findall(r'Momentary freq = (\d+) Hz', text)))
        bits = sorted(set(re.findall(r'Bits: (\d+)', text)))
        rows.append({'device': text.splitlines()[0], 'rates': rates, 'bits': bits})
    return rows


def validate(rate, buffer):
    if rate not in RATES or buffer not in BUFFERS:
        raise ValueError('Unsupported rate or buffer')


def apply(rate, buffer):
    validate(rate, buffer)
    old = metadata()
    try:
        for key, value in [('clock.force-rate', rate), ('clock.force-quantum', buffer)]:
            run(['pw-metadata', '-n', 'settings', '0', key, str(value)])
    except Exception as exc:
        errors = []
        for key in ('clock.force-rate', 'clock.force-quantum'):
            try:
                run(['pw-metadata', '-n', 'settings', '0', key, old.get(key, '0')])
            except Exception as rollback:
                errors.append(str(rollback))
        raise RuntimeError(f'Apply failed: {exc}. Rollback: {errors or "completed"}') from exc


def save(rate, buffer, path=CONFIG):
    validate(rate, buffer)
    if path.is_symlink() or (path.exists() and not path.read_text().startswith(MARKER)):
        raise ValueError(f'Refusing to overwrite an unowned file: {path}')
    if rate == 0 and buffer == 0:
        path.unlink(missing_ok=True)
        return
    lines = [MARKER.rstrip(), 'context.properties = {']
    if rate:
        lines += [f'    default.clock.rate = {rate}', f'    default.clock.allowed-rates = [ {rate} ]']
    if buffer:
        lines += [f'    default.clock.quantum = {buffer}']
    lines += ['}', '']
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix='.pipewire-control-')
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write('\n'.join(lines))
        os.replace(temp, path)
    finally:
        Path(temp).unlink(missing_ok=True)


def snapshot():
    settings = metadata()
    devices = hardware()
    graph = []
    try:
        text = run(['pw-top', '-b', '-n', '2']).split('S   ID')[-1]
        for line in text.splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[0] == 'R' and '+' not in parts:
                quantum, rate = int(parts[2]), int(parts[3])
                if quantum > 0 and rate > 0:
                    graph.append({'quantum': quantum, 'rate': rate})
    except (ValueError, subprocess.SubprocessError):
        pass
    saved = {}
    if CONFIG.exists():
        content = CONFIG.read_text()
        for key in ('rate', 'quantum'):
            match = re.search(r'default\.clock\.' + key + r'\s*=\s*(\d+)', content)
            if match:
                saved[key] = int(match.group(1))
    return {'settings': settings, 'devices': devices, 'graph': graph, 'saved': saved}


def report():
    data = metadata()
    lines = ['SYSTEM CLOCK SETTINGS (not a measured round-trip latency)',
             f'Default rate: {data.get("clock.rate", "?")} Hz',
             f'Default quantum: {data.get("clock.quantum", "?")} samples',
             f'Forced rate: {data.get("clock.force-rate", "0")} (0 = automatic)',
             f'Forced quantum: {data.get("clock.force-quantum", "0")} (0 = automatic)', '',
             'USB HARDWARE — actual running rate; idle devices show no active rate']
    for row in hardware():
        lines += [row['device'], '  Active Hz: ' + (', '.join(row['rates']) or 'idle / unavailable'),
                  '  Advertised valid bits: ' + (', '.join(row['bits']) or 'unavailable')]
    lines += ['', 'ACTIVE GRAPH (RATE and QUANT columns; ? / zero may mean idle)']
    try:
        lines.append('S   ID' + run(['pw-top', '-b', '-n', '2']).split('S   ID')[-1])
    except Exception:
        lines.append('Live graph unavailable. Use pw-top in a terminal.')
    lines += ['', 'STARTUP DEFAULTS', CONFIG.read_text() if CONFIG.exists() else 'Not set.']
    return '\n'.join(lines)


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else 'gui'
    if action == 'gui':
        run(['omarchy-shell', 'shell', 'toggle', 'io.github.adamtcroft.pipewire-control', '{}'])
    elif action == 'json':
        print(json.dumps(snapshot()))
    elif action in ('apply', 'save'):
        if len(sys.argv) != 4:
            raise ValueError('Expected rate and buffer arguments')
        rate, buffer = int(sys.argv[2]), int(sys.argv[3])
        (apply if action == 'apply' else save)(rate, buffer)
        print('Audio overrides applied.' if action == 'apply' else 'Startup defaults saved. Current audio unchanged.')
    elif action == 'status':
        print(report())
    else:
        raise ValueError('Use gui, status, json, apply RATE BUFFER, or save RATE BUFFER')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
