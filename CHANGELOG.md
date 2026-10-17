# Changelog

## 2.1.0 (2026-10-17)

- **Pick your tile desktops:** on first run the desk asks which desktops become the dashboard: desktop 1,
  desktops 1–2 or 1–3 (`desks`). The right-click menu changes it later. Tiles on desktops you turn off are kept
  and come back when you turn them on.
- **Tile desktops stay clear:** a tiled window that opens on one moves to the next desktop, and the view follows
  it. Floating pop-ups may still open over the tiles.
- **Send a tile to any desk:** arrange mode shows one button per other desk, so any tile reaches any desk in one
  click. With one tile desktop, the page dots and the send buttons are hidden.
- **A full desk still takes a new widget:** it goes on the desk you're looking at and, when nothing is free, sits on
  top of the other tiles, drawn solid. Arrange mode opens so you can drag it into place or remove a tile. Sending a
  tile to a full desk works the same way. New widgets no longer spill onto another desk.
- **Themed dock icons, like a phone's icon pack:** each app is drawn flat in the bar's color, not tinted over its
  picture. It gets its real logo (about 80 apps, from Simple Icons, CC0), or a Nerd Font symbol for generic tools.
  Any other app gets its own shape, traced once from its PNG icon (`icontrace.py`, standard library only) and cached
  in `marks.json`. `dockSymbols` sets any app's icon: a logo name, an SVG path or a symbol.
- The backend no longer writes Python bytecode into the plugin folder, which made Omarchy reload the plugin.

## 2.0.0 (2026-10-17)

OmaTiles is the public release of a desk first built for one machine, renamed from Grokbot Desktop.

- **Generic machine cards:** the local card and an optional remote one. Services, the remote host, its name and a
  link button come from the settings. The remote card reads its machine only on refresh, over one shared ssh
  connection. Each service's state is written out next to its dot.
- **Chat tiles for Claude Code, Codex, Grok and Hermes:**
  - they run here, or on `chat.host` over ssh
  - failures say what went wrong (unreachable, not installed, not signed in, rate limited), with **retry**
  - missing CLIs show an install hint
- **Dock:** pinned apps, then recently used ones. Right-click pins or unpins an icon. Theme-colored icons stay
  optional; their brightest parts are exactly the bar's color, like a phone's themed icons.
- **Undo:** removing a tile offers undo for ten seconds. Removed widgets are kept for a day.
- **Keyboard mode** (`qs ipc … call omatiles focus`): arrows, Enter, M, S, A, Esc.
- **First-run hint**, an arranging hint bar, and page dots in the dock.
- **Locale:** metric or imperial units (`units`), the 12 or 24 hour clock, and the date order.
- **Theme:**
  - the desk accent follows the bar's color and is kept at 4.5:1 or better
  - secondary text is lifted to 4.5:1
  - type uses the shell's font tokens, 12 px minimum
- **Store:** previews fall back to the closest theme's screenshot. Widgets made for the phone (they read Android
  notifications) are labelled and listed last, and widgets whose packages are missing say which ones.
- **Calendar** explains how to add a Google OAuth client when there is none.
- **Keyboard arranging:** in keyboard mode, arranging moves the focused tile with the arrows and resizes it with
  Shift+arrows.
- **Red means trouble only:** errors and removal use the theme's red, lifted to 4.5:1. The sun and its arc use the accent.
- **Calmer glance:** the clock drops its weather line when the weather tile is on the same desk. The menu, store and
  widget creator fade in.
- **Widget states:** store widgets say when they're loading, and a widget that fails explains itself before its raw error.
- **Undo** shows above the store too, so removing from the store can be undone there. Deleting your own widget
  takes a second click.
- **Accessibility names** on buttons, fields, dock icons and arrange handles. Calendar controls are 24 px.
- **Settings and data move:**
  - settings to `~/.config/omarchy/omatiles.json`
  - widgets and the Google client to `~/.config/omarchy/omatiles/`
  - caches to `~/.cache/omatiles/`
