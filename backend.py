#!/usr/bin/env python3
"""OmaTiles backend: desk layout, the widget store, machine cards, chat tiles and weather.

Called by Service.qml as `backend.py <operation> [args]`. Everything it writes
lives in ~/.config/omarchy/omatiles.json (the desk), ~/.config/omarchy/omatiles/
(widgets) and ~/.cache/omatiles/ (data the tiles read)."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time

# Nothing may be written into the plugin folder: Omarchy reloads a plugin when its files change.
sys.dont_write_bytecode = True

CACHE = Path.home() / '.cache/omatiles'
CONFIG = Path.home() / '.config/omarchy'
CONFIG_FILE = 'omatiles.json'
DATA = CONFIG / 'omatiles'
WIDGETS = DATA / 'widgets'
TRASH = WIDGETS / '.trash'
OWL = Path(__file__).resolve().parent / 'owl'
STORE = 'https://simonschubert.github.io/omarchy-widgets/'
WIDGET_ID = re.compile(r'^[a-z0-9-]+/[a-z0-9-]+\Z')

def atomic(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as out:
            out.write(text)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)

def curl(url):
    return subprocess.run(['curl', '--silent', '--fail', '--location', '--max-time', '20', url], capture_output=True, text=True)

# ── Desk layout ───────────────────────────────────────────────────────────────
# A 16 x 8 grid on each page: workspaces 1 to 3, as many as the user picks. Built-in tiles have
# fixed keys; store and Claude-made widgets are "owl:<author>/<name>".
COLS, ROWS, GRID, PAGES = 16, 8, 16, 3
AGENTS = ('claude', 'codex', 'grok', 'hermes')
BUILTIN = ('clock', 'local', 'remote', 'calendar', 'weather', 'sun') + tuple('chat-' + a for a in AGENTS)
DEFAULT_PLACES = {'clock': (0, 0, 5, 4), 'local': (5, 0, 6, 4), 'calendar': (11, 0, 5, 8),
                  'weather': (0, 4, 5, 4), 'sun': (5, 4, 6, 4), 'remote': (0, 0, 8, 4),
                  **{'chat-' + a: (0, 0, 8, 4) for a in AGENTS}}
# Built-ins that start hidden; they are added from the store's "built in" list.
DEFAULT_OFF = {'remote'} | {'chat-' + a for a in AGENTS}
# Machine cards stop being readable below 6 x 4; a chat tile needs a few lines.
BUILTIN_MIN = {'local': (6, 4), 'remote': (6, 4), **{'chat-' + a: (4, 3) for a in AGENTS}}

def load_config():
    try:
        config = json.loads((CONFIG / CONFIG_FILE).read_text())
    except (OSError, ValueError):
        config = {}
    if not isinstance(config, dict):
        config = {}
    if not isinstance(config.get('tiles'), dict):
        config['tiles'] = {}
    config['grid'] = GRID
    return config

def desk_count(config):
    """How many workspaces, from 1, are tile desks. Unchosen means all three."""
    n = config.get('desks')
    return max(1, min(PAGES, n)) if isinstance(n, int) and not isinstance(n, bool) and n > 0 else PAGES

def save_config(config):
    atomic(CONFIG / CONFIG_FILE, json.dumps(config, indent=1))

def config_lock():
    CACHE.mkdir(parents=True, exist_ok=True)
    lock = (CACHE / 'config.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX)
    return lock

def place(tile, geometry):
    """Save one tile's dragged or resized cell."""
    with config_lock():
        config = load_config()
        g = json.loads(geometry)
        entry = config['tiles'].setdefault(tile, {'enabled': True})
        entry.pop('top', None)  # placed by hand: no longer stacked on top
        for key in ('col', 'row', 'w', 'h'):
            if isinstance(g.get(key), (int, float)) and g[key] >= 0:
                entry[key] = int(g[key])
        # Kept on the 16 x 8 grid, as the desk reads it.
        entry['w'] = max(1, min(COLS, entry.get('w', 1)))
        entry['h'] = max(1, min(ROWS, entry.get('h', 1)))
        entry['col'] = max(0, min(COLS - entry['w'], entry.get('col', 0)))
        entry['row'] = max(0, min(ROWS - entry['h'], entry.get('row', 0)))
        save_config(config)

def free_spot(config, w, h, page=1):
    """First free cell on one page, row by row, for a w x h tile; None when the page is full."""
    used = set()
    for key, t in config['tiles'].items():
        if not isinstance(t, dict) or not t.get('enabled', True) or t.get('page', 1) != page:
            continue
        d = DEFAULT_PLACES.get(key, (0, 0, 0, 0))
        c, r, tw, th = t.get('col', d[0]), t.get('row', d[1]), t.get('w', d[2]), t.get('h', d[3])
        used |= {(x, y) for x in range(c, c + tw) for y in range(r, r + th)}
    for key, d in DEFAULT_PLACES.items():
        if key not in config['tiles'] and key not in DEFAULT_OFF and page == 1:
            used |= {(x, y) for x in range(d[0], d[0] + d[2]) for y in range(d[1], d[1] + d[3])}
    for y in range(ROWS - h + 1):
        for x in range(COLS - w + 1):
            if not any((xx, yy) in used for xx in range(x, x + w) for yy in range(y, y + h)):
                return x, y
    return None

def fit(config, w, h, least, page):
    """Where a tile goes on one page: full size, else the largest size down to `least` that fits."""
    spot = free_spot(config, w, h, page)
    if spot:
        return spot + (w, h)
    sizes = sorted(((a, b) for a in range(least[0], w + 1) for b in range(least[1], h + 1)),
                   key=lambda s: (-s[0] * s[1], -s[1]))
    for a, b in sizes:
        spot = free_spot(config, a, b, page)
        if spot:
            return spot + (a, b)
    return None

def on_top(w, h):
    """Where a tile goes when the page has no room: centered, over the others."""
    return ((COLS - w) // 2, (ROWS - h) // 2, w, h)

def put_on_desk(key, size, page=1, missing=(), least=None):
    """Place a tile on this page, shrunk to fit if need be. With no room it sits on
    top of the others (marked `top`), so the user can drag it or remove a tile."""
    w, h = max(1, min(COLS, int(size[0]))), max(1, min(ROWS, int(size[1])))
    least = least or (w, h)
    least = (max(1, min(w, int(least[0]))), max(1, min(h, int(least[1]))))
    with config_lock():
        config = load_config()
        desks = desk_count(config)
        p = max(1, min(desks, int(page)))
        spot = fit(config, w, h, least, p)
        tile = {'enabled': True, 'col': 0, 'row': 0, 'w': w, 'h': h}
        if spot:
            tile.update(col=spot[0], row=spot[1], w=spot[2], h=spot[3])
        else:
            tile.update(zip(('col', 'row', 'w', 'h'), on_top(w, h)), top=True)
        if p != 1:
            tile['page'] = p
        config['tiles'][key] = tile
        save_config(config)
    return {'ok': True, 'missing': list(missing), 'page': p, 'w': tile['w'], 'h': tile['h'],
            'shrunk': (tile['w'], tile['h']) != (w, h), 'overlap': not spot}

def owl_sizes(source):
    """A widget's `size:` and `minSize:`; without a minSize it may shrink to half."""
    def find(name):
        m = re.search(r'^\s*' + name + r':\s*(\d+)\s*x\s*(\d+)', source, re.M)
        return (int(m.group(1)), int(m.group(2))) if m else None
    size = find('size') or (4, 4)
    least = find('minSize') or (max(1, -(-size[0] // 2)), max(1, -(-size[1] // 2)))
    return size, least

def widget_size(folder):
    try:
        return owl_sizes((folder / 'widget.owl').read_text())
    except OSError:
        return None

def owl_folder(key):
    return WIDGETS / key[4:] if key.startswith('owl:') and WIDGET_ID.match(key[4:]) else None

def move(key, page):
    """Send a tile to another page, at the first spot it fits there, else on top."""
    with config_lock():
        config = load_config()
        page = max(1, min(desk_count(config), int(page)))
        tile = config['tiles'].get(key)
        if not isinstance(tile, dict) or tile.get('page', 1) == page:
            return
        d = DEFAULT_PLACES.get(key, (0, 0, 4, 4))
        w, h = tile.get('w', d[2]), tile.get('h', d[3])
        folder = owl_folder(key)
        sizes = widget_size(folder) if folder else None
        least = sizes[1] if sizes else BUILTIN_MIN.get(key, (max(2, w // 2), max(2, h // 2)))
        spot = fit(config, w, h, (min(w, least[0]), min(h, least[1])), page)
        tile.pop('top', None)
        if spot:
            tile.update(col=spot[0], row=spot[1], w=spot[2], h=spot[3])
        else:
            tile.update(zip(('col', 'row', 'w', 'h'), on_top(w, h)), top=True)
        if page == 1:
            tile.pop('page', None)
        else:
            tile['page'] = page
        save_config(config)
    print(json.dumps({'ok': True, 'page': page}))

def add_builtin(key, page=1):
    """Put a hidden built-in, or a widget already on disk, back on the desk."""
    if key in BUILTIN:
        d = DEFAULT_PLACES[key]
        print(json.dumps(put_on_desk(key, (d[2], d[3]), page, least=BUILTIN_MIN.get(key, (max(2, d[2] // 2), max(2, d[3] // 2))))))
        return
    folder = owl_folder(key)
    sizes = widget_size(folder) if folder else None
    if sizes is None:
        print(json.dumps({'ok': False, 'error': 'unknown widget'}))
        sys.exit(1)
    print(json.dumps(put_on_desk(key, sizes[0], page, least=sizes[1])))

def remove(key):
    """Take a tile off the desk. Built-ins are hidden; widgets go to the trash so the
    desk can undo it for a while (`restore`). The trash is emptied after a day."""
    with config_lock():
        config = load_config()
        tile = config['tiles'].get(key)
        if key in BUILTIN:
            config['tiles'].setdefault(key, {})['enabled'] = False
        elif owl_folder(key):
            config['tiles'].pop(key, None)
            folder = owl_folder(key).resolve()
            if folder.parent.parent == WIDGETS.resolve() and folder.exists():
                slot = TRASH / key[4:].replace('/', '__')
                shutil.rmtree(slot, ignore_errors=True)
                slot.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(folder), str(slot))
                (slot / '.tile.json').write_text(json.dumps(tile or {}))
                try:
                    folder.parent.rmdir()
                except OSError:
                    pass
        save_config(config)

def restore(key):
    """Undo `remove`: the built-in shows again, or the widget comes back from the trash."""
    with config_lock():
        config = load_config()
        if key in BUILTIN:
            config['tiles'].setdefault(key, {})['enabled'] = True
        elif owl_folder(key):
            slot = TRASH / key[4:].replace('/', '__')
            if not slot.exists():
                return
            try:
                tile = json.loads((slot / '.tile.json').read_text())
            except (OSError, ValueError):
                tile = {}
            (slot / '.tile.json').unlink(missing_ok=True)
            owl_folder(key).parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(slot), str(owl_folder(key)))
            config['tiles'][key] = dict(tile or {}, enabled=True)
        save_config(config)

def prune_trash(days=1):
    if TRASH.exists():
        for slot in TRASH.iterdir():
            if time.time() - slot.stat().st_mtime > days * 86400:
                shutil.rmtree(slot, ignore_errors=True)

OPTIONS = {'dockMono': bool, 'menuHint': bool, 'desks': int}

def set_option(name, value):
    """Set one of the desk's own switches, or how many workspaces are desks."""
    kind = OPTIONS.get(name)
    if kind is None or (kind is int and not value.isdigit()):
        return
    with config_lock():
        config = load_config()
        config[name] = value == 'true' if kind is bool else max(1, min(PAGES, int(value)))
        save_config(config)

def pin(app, on):
    """Pin a desktop entry id to the dock, or unpin it."""
    if not app or any(c in app for c in '\r\n/'):
        return
    with config_lock():
        config = load_config()
        dock = [d for d in config.get('dock', []) if isinstance(d, str) and d != app]
        config['dock'] = dock + [app] if on else dock
        save_config(config)

RECENT_KEEP = 16

def recent(app):
    """Remember an app as just used, for the dock's recent apps."""
    if not app or any(c in app for c in '\r\n/'):
        return
    path = CACHE / 'recent.json'
    try:
        apps = json.loads(path.read_text())
        apps = apps if isinstance(apps, list) else []
    except (OSError, ValueError):
        apps = []
    atomic(path, json.dumps([app] + [a for a in apps if a != app][:RECENT_KEEP - 1]))

# ── Widget store ──────────────────────────────────────────────────────────────

def store(force=False):
    """Fetch the reviewed widget index, at most hourly unless forced, then note what works here."""
    CACHE.mkdir(parents=True, exist_ok=True)
    stamp = CACHE / 'store.attempt'
    if force or not stamp.exists() or time.time() - stamp.stat().st_mtime >= 3600 or not (CACHE / 'store.json').exists():
        stamp.touch()
        result = curl(STORE + 'index.json')
        try:
            data = json.loads(result.stdout)
            assert isinstance(data['widgets'], list)
            atomic(CACHE / 'store.json', result.stdout)
        except (ValueError, KeyError, AssertionError, TypeError):
            pass
    compat()

PHONE_ONLY = re.compile(r'\bAndroid notifications\b', re.I)

def compat():
    """Per store widget: whether it only works on the phone (it reads Android notifications,
    which a desktop doesn't have) and which of its packages are not installed here."""
    try:
        widgets = json.loads((CACHE / 'store.json').read_text())['widgets']
    except (OSError, ValueError, KeyError):
        return
    try:
        have = set(subprocess.run(['pacman', '-Qq'], capture_output=True, text=True, timeout=20).stdout.split())
    except (OSError, subprocess.TimeoutExpired):
        have = None
    out = {}
    for w in widgets if isinstance(widgets, list) else []:
        if not isinstance(w, dict) or not isinstance(w.get('id'), str):
            continue
        packages = (w.get('requires') or {}).get('pacman') or []
        out[w['id']] = {'phone': any(isinstance(c, str) and PHONE_ONLY.search(c) for c in w.get('commands') or []),
                        'missing': [p for p in packages if isinstance(p, str) and have is not None and p not in have]}
    atomic(CACHE / 'compat.json', json.dumps(out))

def store_entry(widget_id):
    if not WIDGET_ID.match(widget_id):
        return None
    try:
        widgets = json.loads((CACHE / 'store.json').read_text())['widgets']
    except (OSError, ValueError, KeyError):
        return None
    return next((w for w in widgets if w.get('id') == widget_id), None)

def missing_packages(packages):
    return [p for p in packages if isinstance(p, str) and re.match(r'^[a-z0-9][a-z0-9+._-]*$', p)
            and subprocess.run(['pacman', '-Q', p], capture_output=True).returncode != 0]

def install(widget_id, page=1):
    """Download a reviewed widget, check it against the index's SHA-256, and put it on the desk."""
    entry = store_entry(widget_id)
    if not entry:
        print(json.dumps({'ok': False, 'error': 'unknown widget'}))
        sys.exit(1)
    result = subprocess.run(['curl', '-fsSL', '--max-time', '30', STORE + entry['path']], capture_output=True)
    if result.returncode != 0 or hashlib.sha256(result.stdout).hexdigest() != entry.get('sha256'):
        print(json.dumps({'ok': False, 'error': 'the download did not match the reviewed file'}))
        sys.exit(1)
    folder = WIDGETS / widget_id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'widget.owl').write_bytes(result.stdout)
    (folder / 'store.json').write_text(json.dumps(entry))
    size, least = owl_sizes(result.stdout.decode('utf-8', 'replace'))
    print(json.dumps(put_on_desk('owl:' + widget_id, entry.get('size') or size, page,
                                 missing_packages((entry.get('requires') or {}).get('pacman', [])), least)))

CREATE_PROMPT = """You write one widget for an Omarchy desktop's home screen, in OWL.
The language reference is {lang}; read it first. Two reviewed widgets to learn from: {ex1} and {ex2}.

Write the widget to ./widget.owl (nothing else) for this request:

{request}

Rules: start with `widget "<short-name>" {{`, give it `meta {{ description: "..."; version: "1.0"; license: "MIT"; category: "<one of news, dev, productivity, time, world, sport, finance, media, games, pets, fun, home, system>" }}` and a `size:` that fits a 16 x 8 grid (at most 16x8; most widgets are 4x4 to 8x4). Declare every package its commands need in `requires {{ pacman: [...] }}`. Use the theme's colors by name (accent, foreground, muted, red...), never hex. Commands must be read-only and safe: no root, no deleting files, no piping downloads into a shell, no eval, no secrets or tokens, no hard-coded personal paths; put values into commands with ${{sh(value)}} or ${{int(n)}}. When done, run nothing; just make sure the file is complete."""

def check_owl(path):
    result = subprocess.run(['java', '-jar', str(OWL / 'owl.jar'), 'check', str(path)], capture_output=True, text=True, timeout=60)
    return result.returncode == 0, (result.stdout + result.stderr).strip()

def create(request, page=1):
    """Have Claude write a widget from a description, check it, and put it on the desk."""
    if not shutil.which('claude'):
        print(json.dumps({'ok': False, 'error': 'Claude Code is not installed on this machine'}))
        sys.exit(1)
    if not shutil.which('java'):
        print(json.dumps({'ok': False, 'error': "the widget checker needs Java 21 (omarchy pkg add jdk21-openjdk)"}))
        sys.exit(1)
    slug = re.sub(r'[^a-z0-9]+', '-', request.lower()).strip('-')[:30].strip('-') or 'widget'
    folder, n = WIDGETS / 'local' / slug, 2
    while folder.exists():
        folder, n = WIDGETS / 'local' / f'{slug}-{n}', n + 1
    folder.mkdir(parents=True)
    prompt = CREATE_PROMPT.format(lang=OWL / 'LANGUAGE.md', ex1=OWL / 'examples' / 'feeds.owl',
                                  ex2=OWL / 'examples' / 'todo.owl', request=request)
    # Sonnet without the user's settings or MCP servers: just the files it needs.
    base = ['claude', '-p', '--model', 'sonnet', '--output-format', 'json', '--setting-sources', 'project',
            '--strict-mcp-config', '--tools', 'Read,Write,Edit', '--permission-mode', 'acceptEdits',
            '--add-dir', str(OWL)]
    session, ok, report = None, False, 'Claude did not write widget.owl'
    for attempt in range(2):
        command = base + (['--resume', session] if session else [])
        text = prompt if not session else 'The checker rejected widget.owl:\n\n' + report + '\n\nFix widget.owl.'
        try:
            result = subprocess.run(command, input=text, cwd=folder, capture_output=True, text=True, timeout=420)
            session = json.loads(result.stdout).get('session_id') or session
        except (OSError, subprocess.TimeoutExpired, ValueError):
            break
        if (folder / 'widget.owl').exists():
            ok, report = check_owl(folder / 'widget.owl')
            if ok:
                break
    if not ok:
        print(json.dumps({'ok': False, 'error': report[-600:], 'folder': str(folder)}))
        sys.exit(1)
    source = (folder / 'widget.owl').read_text()
    named = re.search(r'^widget\s+"([a-z0-9-]+)"', source, re.M)
    if named and named.group(1) != folder.name and not (folder.parent / named.group(1)).exists():
        folder = folder.rename(folder.parent / named.group(1))
    size, least = owl_sizes(source)
    programs = subprocess.run(['java', '-jar', str(OWL / 'owl.jar'), 'programs', str(folder / 'widget.owl')],
                              capture_output=True, text=True, timeout=60).stdout.strip()
    packages = [line.split(' ', 1)[1] for line in programs.splitlines() if line.startswith('pacman ')]
    key = 'owl:local/' + folder.name
    placed = put_on_desk(key, size, page, missing_packages(packages), least)
    print(json.dumps(dict(placed, key=key, programs=programs.splitlines())))

def themes():
    """Omarchy themes with their background and five swatch colors, for the theme picker
    and for choosing the closest store preview."""
    names = subprocess.run(['omarchy', 'theme', 'list'], capture_output=True, text=True, timeout=20).stdout.splitlines()
    out = []
    for name in (n.strip() for n in names if n.strip()):
        slug = name.lower().replace(' ', '-')
        colors = {}
        for root in (CONFIG / 'themes', Path('/usr/share/omarchy/themes')):
            try:
                for line in (root / slug / 'colors.toml').read_text().splitlines():
                    m = re.match(r'^\s*([a-z0-9_]+)\s*=\s*"(#[0-9a-fA-F]{6})"', line)
                    if m:
                        colors[m.group(1)] = m.group(2)
                break
            except OSError:
                continue
        swatch = [colors[k] for k in ('accent', 'red', 'orange', 'green', 'magenta') if k in colors]
        out.append({'name': name, 'slug': slug, 'background': colors.get('background', ''), 'swatch': swatch})
    print(json.dumps(out))

# ── Machine cards ─────────────────────────────────────────────────────────────
# One read-only probe for this machine (every minute while its card shows) and
# for the remote machine (over ssh, only when its card's refresh is pressed).
# Services are the config's own list of systemd units: {"label", "unit", "user"}.

PROBE = r'''. /etc/os-release; echo "os=$PRETTY_NAME"
echo "who=$(id -un)@$(cat /proc/sys/kernel/hostname)"
v=$(cat /sys/devices/virtual/dmi/id/sys_vendor 2>/dev/null); m=$(cat /sys/devices/virtual/dmi/id/product_name 2>/dev/null)
case "$m" in "$v"*) echo "host=$m";; *) echo "host=$v $m";; esac
echo "kernel=$(uname -r)"; echo "packages=$(pacman -Qq 2>/dev/null | wc -l)"; echo "shell=bash ${BASH_VERSION%%(*}"
echo "cpuName=$(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2- | sed 's/^ *//; s/([^)]*)//g; s/ @.*//; s/  */ /g')"
echo "stat1=$(head -1 /proc/stat)"; sleep 1; echo "stat2=$(head -1 /proc/stat)"
echo "uptime=$(cut -d' ' -f1 /proc/uptime)"
echo "memTotal=$(awk '/^MemTotal/{print $2*1024}' /proc/meminfo)"; echo "memAvail=$(awk '/^MemAvailable/{print $2*1024}' /proc/meminfo)"
echo "disk=$(df -B1 --output=size,used / | tail -1)"
t=; for z in /sys/class/thermal/thermal_zone*; do case "$(cat $z/type 2>/dev/null)" in x86_pkg_temp|cpu-thermal|k10temp) t=$(cat $z/temp);; esac; done
[ -z "$t" ] && for h in /sys/class/hwmon/hwmon*; do case "$(cat $h/name 2>/dev/null)" in k10temp|coretemp|zenpower) t=$(cat $h/temp1_input 2>/dev/null);; esac; done
[ -n "$t" ] && echo "temp=$t"
b=$(ls -d /sys/class/power_supply/BAT* 2>/dev/null | head -1); [ -n "$b" ] && echo "battery=$(cat $b/capacity) $(cat $b/status)"
command -v tailscale >/dev/null && echo "tailscale=$(systemctl is-active tailscaled) $(tailscale ip -4 2>/dev/null | head -1)"
echo @@units
'''
PROBE_TAIL = r'''echo @@docker; command -v docker >/dev/null && docker ps -a --format '{{.Names}}\t{{.State}}\t{{.Status}}' 2>/dev/null
echo @@failed; { systemctl --user list-units --failed --no-legend --plain; systemctl list-units --failed --no-legend --plain; } 2>/dev/null | awk '{print $1}'
'''
UNIT = re.compile(r'^[A-Za-z0-9@._*:-]+$')

def services(spec):
    """The config's services list, kept to what the probe can safely ask systemd about."""
    out = []
    for s in spec if isinstance(spec, list) else []:
        if isinstance(s, dict) and isinstance(s.get('unit'), str) and UNIT.match(s['unit']):
            out.append({'label': str(s.get('label') or s['unit'])[:40], 'unit': s['unit'], 'user': s.get('user', True) is not False})
    return out[:6]

def probe_script(spec):
    lines = []
    for i, s in enumerate(services(spec)):
        scope = '--user ' if s['user'] else ''
        lines.append("systemctl %slist-units --all --no-legend --plain %s 2>/dev/null | awk '{print \"%d\\t\"$1\"\\t\"$3\"\\t\"$4}'"
                     % (scope, shlex.quote(s['unit']), i))
    return PROBE + '\n'.join(lines) + '\n' + PROBE_TAIL

def probe_parse(out, spec=()):
    facts, parts, key = {}, {}, None
    for line in out.splitlines():
        if line.startswith('@@'):
            key = line[2:]
            parts[key] = []
        elif key:
            parts[key].append(line)
        elif '=' in line:
            k, v = line.split('=', 1)
            facts[k] = v.strip()
    rows = lambda k: [l.split('\t') for l in parts.get(k, []) if l.strip()]
    num = lambda v: float(v) if re.match(r'^[0-9.]+$', v or '') else None
    def busy(line):
        n = [int(x) for x in line.split()[1:]]
        return sum(n) - n[3] - (n[4] if len(n) > 4 else 0), sum(n)
    try:
        (b1, t1), (b2, t2) = busy(facts['stat1']), busy(facts['stat2'])
        cpu = round(100 * (b2 - b1) / max(1, t2 - t1), 1)
    except (KeyError, ValueError, IndexError):
        cpu = None
    secs = int(num(facts.get('uptime')) or 0)
    days, hours, mins = secs // 86400, secs % 86400 // 3600, secs % 3600 // 60
    uptime = (f"{days} day{'s' if days != 1 else ''}, " if days else '') + f"{hours}:{mins:02d}"
    total, avail = num(facts.get('memTotal')), num(facts.get('memAvail'))
    disk = (facts.get('disk') or '').split()
    size, used = (int(disk[0]), int(disk[1])) if len(disk) == 2 and all(d.isdigit() for d in disk) else (None, None)
    temp = num(facts.get('temp'))
    battery = (facts.get('battery') or '').split(' ', 1)
    tail = (facts.get('tailscale') or '').split()
    units = rows('units')
    svc = []
    for i, s in enumerate(services(spec)):
        mine = [r for r in units if r[0] == str(i) and len(r) > 2]
        running = sum(1 for r in mine if r[2] == 'active')
        svc.append({'label': s['label'], 'running': running, 'units': len(mine)})
    return {
        'ok': True, 'who': facts.get('who', ''), 'os': facts.get('os', ''), 'host': facts.get('host', '').strip(),
        'kernel': facts.get('kernel', ''), 'packages': facts.get('packages', ''), 'shell': facts.get('shell', ''),
        'cpuName': facts.get('cpuName', ''), 'cpu': cpu, 'uptime': uptime, 'memTotal': total,
        'mem': round(100 * (total - avail) / total, 1) if total and avail is not None else None,
        'disk': round(100 * used / size, 1) if size else None, 'diskSize': size,
        'temp': round(temp / 1000) if temp is not None else None,
        'battery': {'level': int(battery[0]), 'status': battery[1] if len(battery) > 1 else ''} if battery[0].isdigit() else None,
        # None: no Tailscale here; '': installed but down; else this machine's tailnet address.
        'tailscale': None if 'tailscale' not in facts else tail[1] if len(tail) > 1 and tail[0] == 'active' else '',
        'services': svc,
        'containers': [{'name': r[0], 'up': r[1] == 'running', 'status': r[2] if len(r) > 2 else r[1]} for r in rows('docker')],
        'failed': [r[0] for r in rows('failed')],
    }

def ssh_host(value):
    """A user@host or ssh alias from the config, refused if it could be read as an option."""
    return value if isinstance(value, str) and re.match(r'^[A-Za-z0-9_.@:-]+$', value) and not value.startswith('-') else ''

def ssh_base(host, timeout=8):
    # One shared connection for the card and chat turns, so the machine sees one login.
    return ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=%d' % timeout, '-o', 'ControlMaster=auto',
            '-o', 'ControlPath=' + str(CACHE / 'ssh-%C'), '-o', 'ControlPersist=6m', host]

def probe(which):
    """Read this machine (`local`) or the configured remote one (`remote`) into the cache."""
    CACHE.mkdir(parents=True, exist_ok=True)
    section = load_config().get(which) or {}
    path = CACHE / (which + '.json')
    with (CACHE / (which + '.lock')).open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        stamp = CACHE / (which + '.attempt')
        if stamp.exists() and time.time() - stamp.stat().st_mtime < (50 if which == 'local' else 10):
            return
        stamp.touch()
        now = time.time() * 1000
        script = probe_script(section.get('services'))
        try:
            if which == 'local':
                result = subprocess.run(['bash', '-s'], input=script, capture_output=True, text=True, timeout=20)
            else:
                host = ssh_host(section.get('host'))
                if not host:
                    raise OSError('no host')
                result = subprocess.run(ssh_base(host, 5) + ['bash -s'], input=script, capture_output=True, text=True, timeout=25)
                if result.returncode != 0:
                    raise OSError(result.stderr.strip())
            data = probe_parse(result.stdout, section.get('services'))
            data['updatedAt'] = data['seenAt'] = now
        except (OSError, ValueError, subprocess.TimeoutExpired) as error:
            try:
                data = json.loads(path.read_text())
            except (OSError, ValueError):
                data = {}
            data.update({'ok': False, 'updatedAt': now, 'error': str(error)[:160]})
        atomic(path, json.dumps(data))

# ── Chat tiles ────────────────────────────────────────────────────────────────
# Each agent CLI runs here, or on `chat.host` over ssh. Turns run with no one
# to approve tools: Claude, Codex and Grok are held to read-only or web-only;
# Hermes runs with its profile's own tools (see the README). The thread
# (session id) and transcript live in chat/<agent>/.

NAMES = {'claude': 'Claude', 'codex': 'Codex', 'grok': 'Grok', 'hermes': 'Hermes'}
BINARIES = {'claude': 'claude', 'codex': 'codex', 'grok': 'grok', 'hermes': 'hermes'}
LOG_KEEP = 60

def chat_settings():
    chat = load_config().get('chat') or {}
    agents = chat.get('agents') if isinstance(chat.get('agents'), dict) else {}
    return ssh_host(chat.get('host')), agents

def agent_name(agent, agents):
    return str((agents.get(agent) or {}).get('name') or NAMES[agent])[:24]

def hermes_profile(agents):
    p = (agents.get('hermes') or {}).get('profile') or ''
    return p if re.match(r'^[a-z0-9_-]*$', p) else ''

def safe_session(session):
    return session if session and all(c.isalnum() or c in '-_' for c in session) else ''

def wrap(agent, command):
    """The shell line for one CLI: hermes works from home, the others from their own chat dir."""
    head = 'export PATH=$HOME/.local/bin:$PATH; '
    if agent != 'hermes':
        head += 'd=$HOME/.cache/omatiles-chat/%s; mkdir -p "$d" && cd "$d" && ' % agent
    return head + 'exec ' + command

def turn_command(agent, session, agents):
    """One turn's command. The prompt arrives on stdin, never in argv."""
    if agent == 'hermes':
        p = hermes_profile(agents)
        return 'hermes' + (' -p ' + p if p else '') + ' chat -Q --format stream-json' + (' --resume ' + session if session else '') + ' --query-file /dev/stdin'
    if agent == 'grok':
        # Grok's -c continues the newest chat in its cwd, so its session file is just a marker.
        return 'grok' + (' -c' if session else '') + (' --prompt-file /dev/stdin --cwd . --permission-mode dontAsk'
                                                       ' --tools web_search --disallowed-tools search_tool,use_tool')
    if agent == 'claude':
        return 'claude -p --output-format json --tools WebSearch,WebFetch' + (' --resume ' + session if session else '')
    if agent == 'codex':
        if session:
            return "codex exec resume --json --skip-git-repo-check -c 'sandbox_mode=\"read-only\"' " + session + ' -'
        return 'codex exec --json -s read-only --skip-git-repo-check -'
    raise ValueError(agent)

def app_command(agent, session, agents):
    """The interactive CLI for the tile's terminal link, on the tile's thread when it has one.
    `chat.agents.<agent>.open` replaces it with the user's own command."""
    own = (agents.get(agent) or {}).get('open')
    if isinstance(own, str) and own.strip() and '\n' not in own:
        return own
    p = hermes_profile(agents)
    return {'hermes': 'hermes' + (' -p ' + p if p else '') + (' --resume ' + session if session else ''),
            'grok': 'grok' + (' -c' if session else ''),
            'claude': 'claude' + (' --resume ' + session if session else ''),
            'codex': 'codex' + (' resume ' + session if session else '')}[agent]

def read_session(agent):
    stamp = CACHE / 'chat' / agent / 'session'
    return safe_session(stamp.read_text().strip()) if stamp.exists() else ''

def open_app(agent):
    host, agents = chat_settings()
    session = read_session(agent)
    session = '' if session == 'continue' and agent != 'grok' else session
    line = wrap(agent, app_command(agent, session, agents))
    run = (['ssh', '-t', host, line] if host else ['bash', '-lc', line])
    try:
        subprocess.run(['setsid', '-f', 'omarchy-launch-tui', '--app-id=org.omarchy.omatiles-' + agent] + run,
                       capture_output=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        sys.exit(1)

def parse_reply(agent, out):
    """Reply text and session id from one turn's stdout."""
    if agent == 'grok':
        return out.strip(), 'continue'
    if agent == 'claude':
        data = json.loads(out)
        return str(data.get('result', '')).strip(), data.get('session_id')
    text, session = [], None
    for line in out.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if agent == 'codex':
            if event.get('type') == 'thread.started':
                session = event.get('thread_id')
            elif event.get('type') == 'item.completed' and event['item'].get('type') == 'agent_message':
                text.append(event['item'].get('text', ''))
        elif event.get('type') == 'result':
            session = event.get('session_id')
            text = [event.get('text', '')]
    return '\n\n'.join(t for t in text if t).strip(), session

def explain(name, where, code, raw):
    """A sentence for a failed turn: what went wrong and what to do about it."""
    low = raw.lower()
    if code == 255 or 'could not resolve' in low or 'connection refused' in low or 'connection timed out' in low or 'no route to host' in low:
        return "Couldn't reach %s. Check that it is on and reachable over ssh." % where
    if code == 127 or 'command not found' in low:
        return '%s is not installed %s.' % (name, 'on ' + where if where != 'this machine' else 'here')
    if 'native binary not installed' in low or 'reinstall' in low:
        return '%s is installed incompletely %s. Reinstall it there, then retry.' % (name, 'on ' + where if where != 'this machine' else 'here')
    if any(k in low for k in ('not logged in', 'please log in', 'please run /login', 'unauthorized', 'invalid api key', 'authentication')):
        return '%s is not signed in %s. Open the terminal and sign in, then retry.' % (name, 'on ' + where if where != 'this machine' else 'here')
    if 'rate limit' in low or '429' in low or 'quota' in low:
        return '%s is rate limited right now. Try again in a few minutes.' % name
    return '%s returned no answer.' % name

def log_read(agent):
    try:
        log = json.loads((CACHE / 'chat' / agent / 'log.json').read_text())
        return log if isinstance(log, list) else []
    except (OSError, ValueError):
        return []

def log_write(agent, log):
    atomic(CACHE / 'chat' / agent / 'log.json', json.dumps(log[-LOG_KEEP:]))

def log_turn(agent, who, text, error=False, detail=''):
    """Append one message to the agent's transcript, the chat tile's history."""
    entry = {'who': who, 'text': text, 'at': int(time.time() * 1000)}
    if error:
        entry['error'] = True
    if detail:
        entry['detail'] = detail[:240]
    log_write(agent, log_read(agent) + [entry])

def ask(agent, text, retry=False):
    """One chat turn. A retry drops the failed answer and sends the last question again."""
    if agent not in AGENTS:
        sys.exit(1)
    host, agents = chat_settings()
    name, where = agent_name(agent, agents), (str((load_config().get('chat') or {}).get('where') or host) if host else 'this machine')
    (CACHE / 'chat' / agent).mkdir(parents=True, exist_ok=True)
    if retry:
        log = log_read(agent)
        while log and log[-1].get('who') != 'you':
            log.pop()
        if not log:
            sys.exit(1)
        text = log[-1]['text']
        log_write(agent, log)
    else:
        log_turn(agent, 'you', text.strip())
    session = read_session(agent)
    line = wrap(agent, turn_command(agent, session, agents))
    command = ssh_base(host) + [line] if host else ['bash', '-lc', line]
    try:
        result = subprocess.run(command, input=text, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        log_turn(agent, 'agent', "%s didn't answer within 5 minutes." % name, error=True)
        sys.exit(1)
    except OSError as error:
        log_turn(agent, 'agent', explain(name, where, 127, str(error)), error=True, detail=str(error))
        sys.exit(1)
    try:
        reply, new_session = parse_reply(agent, result.stdout)
    except (ValueError, KeyError, TypeError, AttributeError):
        reply, new_session = '', None
    if result.returncode == 0 and reply and safe_session(new_session):
        (CACHE / 'chat' / agent / 'session').write_text(new_session)
    if not reply:
        lines = [l for l in (result.stderr + '\n' + result.stdout).splitlines() if l.strip() and not l.startswith('{')]
        raw = lines[-1].strip() if lines else ''
        log_turn(agent, 'agent', explain(name, where, result.returncode, result.stderr + result.stdout), error=True, detail=raw)
        sys.exit(1)
    log_turn(agent, 'agent', reply)

def new_chat(agent):
    if agent in AGENTS:
        (CACHE / 'chat' / agent / 'session').unlink(missing_ok=True)
        (CACHE / 'chat' / agent / 'log.json').unlink(missing_ok=True)

def agents_here():
    """Which agent CLIs this machine has, for tiles whose agents run here."""
    found = {a: bool(shutil.which(BINARIES[a]) or (Path.home() / '.local/bin' / BINARIES[a]).exists()) for a in AGENTS}
    atomic(CACHE / 'agents.json', json.dumps(found))

# ── Weather ───────────────────────────────────────────────────────────────────

def weather():
    """Weather for Omarchy's weather location (wttr.in), at most every 30 minutes."""
    CACHE.mkdir(parents=True, exist_ok=True)
    with (CACHE / 'weather.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        stamp = CACHE / 'weather.attempt'
        if stamp.exists() and time.time() - stamp.stat().st_mtime < 1800:
            return
        stamp.touch()
        try:
            place = subprocess.run(['omarchy-weather-location'], capture_output=True, text=True, timeout=10).stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            place = ''
        if any(c in place for c in '\r\n'):
            return
        from urllib.parse import quote
        result = curl('https://wttr.in/' + quote(place) + '?format=j1')
        if result.returncode != 0:
            return
        try:
            data = json.loads(result.stdout)
            cur = data['current_condition'][0]
            area = (data.get('nearest_area') or [{}])[0]
            days = []
            for day in data['weather'][:3]:
                noon = day['hourly'][min(4, len(day['hourly']) - 1)]
                astro = day['astronomy'][0]
                days.append({'date': day['date'], 'hi': int(day['maxtempF']), 'lo': int(day['mintempF']),
                             'hiC': int(day['maxtempC']), 'loC': int(day['mintempC']),
                             'code': int(noon['weatherCode']), 'desc': noon['weatherDesc'][0]['value'],
                             'sunrise': astro['sunrise'], 'sunset': astro['sunset'],
                             'moonPhase': astro['moon_phase'], 'moonIllum': int(astro['moon_illumination'])})
            location = place or ((area.get('areaName') or [{}])[0].get('value', ''))
            out = {'updatedAt': time.time() * 1000, 'location': location,
                   'temp': int(cur['temp_F']), 'feels': int(cur['FeelsLikeF']), 'tempC': int(cur['temp_C']), 'feelsC': int(cur['FeelsLikeC']),
                   'code': int(cur['weatherCode']), 'desc': cur['weatherDesc'][0]['value'],
                   'wind': int(cur['windspeedMiles']), 'windK': int(cur['windspeedKmph']), 'days': days}
        except (ValueError, KeyError, IndexError, TypeError):
            return
        atomic(CACHE / 'weather.json', json.dumps(out))

# ──────────────────────────────────────────────────────────────────────────────

def init(defaults):
    """First run: the config with the desk's defaults, without overwriting an existing one."""
    CONFIG.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    try:
        with (CONFIG / CONFIG_FILE).open('x') as out:
            out.write(defaults)
    except FileExistsError:
        pass
    prune_trash()
    agents_here()

# ── Dock marks: an app's own shape, traced from its icon ────────────────────────
ICON_NAME = re.compile(r'[A-Za-z0-9@._+-]{1,200}\Z')
MARK_MAX_BYTES = 4 * 1024 * 1024

def icon_dirs():
    home = Path.home()
    data = [home / '.local/share'] + [Path(d) for d in os.environ.get('XDG_DATA_DIRS', '/usr/local/share:/usr/share').split(':') if d]
    out = [home / '.icons'] + [d / 'icons' for d in data] + [home / '.local/share/flatpak/exports/share/icons',
                                                          Path('/var/lib/flatpak/exports/share/icons')]
    return [d for d in out if d.is_dir()], [d / 'pixmaps' for d in data if (d / 'pixmaps').is_dir()]

def icon_png(name):
    """The largest PNG (up to 512 px) of an app icon in the hicolor theme, else pixmaps."""
    if name.startswith('/'):
        p = Path(name)
        return p if p.suffix == '.png' and p.is_file() else None
    if not ICON_NAME.match(name):
        return None
    themes, pixmaps = icon_dirs()
    best, size = None, 0
    for base in themes:
        for folder in (base / 'hicolor').glob('*/apps'):
            m = re.match(r'(\d+)x\d+(@\d+)?$', folder.parent.name)
            px = int(m.group(1)) if m else 0
            cand = folder / (name + '.png')
            if size < px <= 512 and cand.is_file():
                best, size = cand, px
    if best:
        return best
    for base in pixmaps:
        cand = base / (name + '.png')
        if cand.is_file():
            return cand
    return None

_TRACER = []

def tracer():
    """icontrace.py next to this file, loaded by path (the standard library has a `trace`)."""
    if not _TRACER:
        import importlib.util
        spec = importlib.util.spec_from_file_location('icontrace', Path(__file__).resolve().parent / 'icontrace.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _TRACER.append(module)
    return _TRACER[0]

def marks(names):
    """Trace each dock icon's shape once; cache/marks.json maps icon name -> 24 x 24 path."""
    out_file = CACHE / 'marks.json'
    try:
        cached = json.loads(out_file.read_text())
    except (OSError, ValueError):
        cached = {}
    out = {}
    for name in names[:64]:
        if not isinstance(name, str):
            continue
        png = icon_png(name)
        if not png:
            continue
        st = png.stat()
        key = '%s:%d:%d' % (png, st.st_size, int(st.st_mtime))
        old = cached.get(name)
        if isinstance(old, dict) and old.get('key') == key:
            out[name] = old
            continue
        d = ''
        if st.st_size <= MARK_MAX_BYTES:
            try:
                d = tracer().trace(png)
            except Exception:
                d = ''
        out[name] = {'key': key, 'path': d}
    atomic(out_file, json.dumps(out))

def page_arg(i):
    return int(sys.argv[i]) if len(sys.argv) > i and sys.argv[i].isdigit() else 1

if __name__ == '__main__':
    op, args = sys.argv[1], sys.argv[2:]
    ops = {
        'init': lambda: init(args[0]),
        'place': lambda: place(args[0], args[1]),
        'store': lambda: store(args == ['force']),
        'install': lambda: install(args[0], page_arg(3)),
        'add': lambda: add_builtin(args[0], page_arg(3)),
        'create': lambda: create(args[0], page_arg(3)),
        'move': lambda: move(args[0], page_arg(3)),
        'remove': lambda: remove(args[0]),
        'restore': lambda: restore(args[0]),
        'themes': themes,
        'set': lambda: set_option(args[0], args[1]),
        'pin': lambda: pin(args[0], True),
        'unpin': lambda: pin(args[0], False),
        'recent': lambda: recent(args[0]),
        'probe': lambda: probe(args[0]) if args and args[0] in ('local', 'remote') else None,
        'ask': lambda: ask(args[0], args[1] if len(args) > 1 else '', retry=args[1:] == ['--retry'] or args[2:] == ['--retry']),
        'open': lambda: open_app(args[0]) if args and args[0] in AGENTS else None,
        'new': lambda: new_chat(args[0]),
        'agents': agents_here,
        'weather': weather,
        'marks': lambda: marks(json.loads(args[0]) if args else []),
    }
    if op not in ops:
        sys.exit('unknown operation: ' + op)
    ops[op]()
