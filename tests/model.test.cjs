const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const calendar = require('../calendar/Model.js');
const config = require('../Config.js');
const glyphs = require('../Glyphs.js');

// Ui.js has no exports and uses Qt.rgba / Qt.color: run it in a context with a tiny Qt shim.
const Qt = {
  rgba: (r, g, b, a) => ({r, g, b, a}),
  color: (hex) => ({r: parseInt(hex.slice(1, 3), 16) / 255, g: parseInt(hex.slice(3, 5), 16) / 255, b: parseInt(hex.slice(5, 7), 16) / 255, a: 1}),
};
const ctx = vm.createContext({Qt, Math, Date, Array, isFinite});
vm.runInContext(fs.readFileSync(path.join(__dirname, '..', 'Ui.js'), 'utf8'), ctx);
const rgb = (r, g, b) => ({r, g, b});
const black = rgb(0, 0, 0), white = rgb(1, 1, 1);

// ── Config.parse ──────────────────────────────────────────────────────────────
test('parse falls back to defaults on bad JSON, null and non-objects', () => {
  const d = config.defaults();
  for (const raw of ['{not json', 'null', '5', '"x"', '', undefined]) assert.deepEqual(config.parse(raw), d, String(raw));
  assert.equal(d.grid, 16);
  assert.deepEqual(Object.keys(d.tiles).sort(), config.BUILTIN.slice().sort());
  assert.equal(d.tiles.remote.enabled, false);
  assert.equal(d.tiles.clock.enabled, true);
});

test('parse leaves desks unchosen by default and clamps a chosen count to 1-3', () => {
  assert.equal(config.defaults().desks, 0);
  const desks = (v) => config.parse(JSON.stringify({desks: v})).desks;
  assert.equal(desks(1), 1); assert.equal(desks(2), 2); assert.equal(desks(3), 3);
  assert.equal(desks(9), 3); assert.equal(desks(0), 1); assert.equal(desks(-4), 1); assert.equal(desks(1.6), 2);
  assert.equal(desks('2'), 0); assert.equal(desks(null), 0); assert.equal(desks(true), 0);
});

test('parse keeps every default tile on the 16x8 grid', () => {
  for (const [k, t] of Object.entries(config.defaults().tiles)) {
    assert.ok(t.col >= 0 && t.col + t.w <= config.COLS, k);
    assert.ok(t.row >= 0 && t.row + t.h <= config.ROWS, k);
  }
});

test('tiles are clamped to the grid, rounded and keep other defaults', () => {
  const c = config.parse(JSON.stringify({tiles: {
    clock: {col: 99, row: 99, w: 99, h: 99},
    local: {col: -5, row: -5, w: 3.6, h: 2},
    calendar: {col: 15, row: 7, w: 5, h: 8},
    weather: {enabled: false},
    sun: {col: 'x', w: null, h: NaN},
  }}));
  assert.deepEqual([c.tiles.clock.col, c.tiles.clock.row, c.tiles.clock.w, c.tiles.clock.h], [0, 0, 16, 8]);
  assert.deepEqual([c.tiles.local.col, c.tiles.local.row, c.tiles.local.w, c.tiles.local.h], [0, 0, 4, 2]);
  assert.deepEqual([c.tiles.calendar.col, c.tiles.calendar.row], [11, 0]);
  assert.equal(c.tiles.weather.enabled, false);
  assert.equal(c.tiles.weather.w, 5);
  assert.deepEqual(c.tiles.sun, config.defaults().tiles.sun);
});

test('page is clamped to 1..3 and ignored when not a number', () => {
  const c = config.parse(JSON.stringify({tiles: {clock: {page: 9}, local: {page: 0}, calendar: {page: 2.4}, weather: {page: '2'}, sun: {page: -4}}}));
  assert.equal(c.tiles.clock.page, 3);
  assert.equal(c.tiles.local.page, 1);
  assert.equal(c.tiles.calendar.page, 2);
  assert.equal(c.tiles.weather.page, undefined);
  assert.equal(c.tiles.sun.page, 1);
});

test('only builtin keys and owl:<author>/<name> keys are kept', () => {
  const t = {col: 1, row: 1, w: 2, h: 2};
  const c = config.parse(JSON.stringify({tiles: {
    bogus: t, 'owl:al/clock-1': t, 'owl:Al/x': t, 'owl:a/b/c': t, 'owl:a': t, 'owl:../x': t, 'chat-claude': t, 'chat-nope': t, constructor: t, 'owl:a/b': 5,
  }}));
  const owl = Object.keys(c.tiles).filter(k => k.startsWith('owl:'));
  assert.deepEqual(owl, ['owl:al/clock-1']);
  assert.deepEqual(c.tiles['owl:al/clock-1'], {enabled: true, col: 1, row: 1, w: 2, h: 2});
  assert.equal(c.tiles.bogus, undefined);
  assert.equal(c.tiles['chat-nope'], undefined);
  assert.equal(Object.keys(c.tiles).length, config.BUILTIN.length + 1);
  assert.equal(c.tiles['chat-claude'].col, 1);
});

test('new widget tile defaults to 4x4 and enabled', () => {
  const c = config.parse(JSON.stringify({tiles: {'owl:a/b': {}}}));
  assert.deepEqual(c.tiles['owl:a/b'], {enabled: true, col: 0, row: 0, w: 4, h: 4});
});

test('dock keeps only non-empty strings', () => {
  assert.deepEqual(config.parse(JSON.stringify({dock: ['a', '', 5, null, 'b', {}]})).dock, ['a', 'b']);
  assert.deepEqual(config.parse(JSON.stringify({dock: []})).dock, []);
  assert.deepEqual(config.parse(JSON.stringify({dock: 'x'})).dock, config.defaults().dock);
  assert.equal(config.parse(JSON.stringify({dock: Array.from({length: 40}, (_, i) => 'a' + i)})).dock.length, 24);
});

test('clock is auto, 12 or 24', () => {
  assert.equal(config.parse('{}').clock, 'auto');
  for (const v of ['auto', '12', '24']) assert.equal(config.parse(JSON.stringify({clock: v})).clock, v);
  for (const v of [12, '13', null, 'AM']) assert.equal(config.parse(JSON.stringify({clock: v})).clock, 'auto');
});

test('units are restricted to auto, metric and imperial', () => {
  assert.equal(config.parse('{}').units, 'auto');
  for (const u of ['auto', 'metric', 'imperial']) assert.equal(config.parse(JSON.stringify({units: u})).units, u);
  for (const u of ['kelvin', 5, null, 'METRIC']) assert.equal(config.parse(JSON.stringify({units: u})).units, 'auto');
});

test('booleans: dockMono and menuHint only accept booleans', () => {
  assert.equal(config.parse('{"dockMono":true,"menuHint":false}').dockMono, true);
  assert.equal(config.parse('{"dockMono":true,"menuHint":false}').menuHint, false);
  assert.equal(config.parse('{"dockMono":"yes","menuHint":0}').dockMono, false);
  assert.equal(config.parse('{"dockMono":"yes","menuHint":0}').menuHint, true);
});

test('remote.link.url is kept only when http(s)', () => {
  const url = u => config.parse(JSON.stringify({remote: {host: 'h', link: {label: 'L', url: u}}})).remote.link;
  assert.deepEqual(url('https://example.org/a'), {label: 'L', url: 'https://example.org/a'});
  assert.equal(url('http://example.org').url, 'http://example.org');
  for (const bad of ['javascript:alert(1)', 'file:///etc/passwd', 'ftp://x', '//x', 'example.org', '', 5, null]) assert.equal(url(bad).url, '', String(bad));
  assert.equal(config.parse(JSON.stringify({remote: {host: 'h'}})).remote.link.url, '');
});

test('remote host, name and length limits', () => {
  const r = config.parse(JSON.stringify({remote: {host: 'a'.repeat(300), name: 'n'.repeat(50)}})).remote;
  assert.equal(r.host.length, 120);
  assert.equal(r.name.length, 24);
  assert.deepEqual(config.parse(JSON.stringify({remote: {host: 5}})).remote.host, '');
});

test('services are validated, user defaults to true, capped at 6', () => {
  const list = [{unit: 'a.service'}, {label: 'B', unit: 'b.service', user: false}, {label: 'C', unit: 'c', user: 'no'},
                {label: 'no unit'}, null, 'x', {unit: 5}, {unit: 'd'}, {unit: 'e'}, {unit: 'f'}, {unit: 'g'}];
  const s = config.parse(JSON.stringify({local: {services: list}})).local.services;
  assert.equal(s.length, 6);
  assert.deepEqual(s[0], {label: 'a.service', unit: 'a.service', user: true});
  assert.deepEqual(s[1], {label: 'B', unit: 'b.service', user: false});
  assert.equal(s[2].user, true);
  assert.equal(s[3].unit, 'd');
  assert.deepEqual(config.parse(JSON.stringify({remote: {services: 'x'}})).remote.services, []);
  assert.equal(config.parse(JSON.stringify({remote: {services: [{unit: 'x', label: 'L'.repeat(80)}]}})).remote.services[0].label.length, 40);
});

test('chat keeps host, where and only the name of known agents', () => {
  const c = config.parse(JSON.stringify({chat: {host: 'me@box', where: 'W'.repeat(40), agents: {
    claude: {name: 'Buddy', open: 'evil', profile: 'x'}, hermes: {name: 5}, bogus: {name: 'No'}, codex: 'str', grok: null}}})).chat;
  assert.equal(c.host, 'me@box');
  assert.equal(c.where.length, 24);
  assert.deepEqual(c.agents, {claude: {name: 'Buddy'}, hermes: {name: ''}});
  assert.deepEqual(config.parse('{"chat":{"agents":"x"}}').chat.agents, {});
});

test('exports mirror the backend constants', () => {
  assert.equal(config.COLS, 16); assert.equal(config.ROWS, 8); assert.equal(config.PAGES, 3);
  assert.deepEqual(config.AGENTS, ['claude', 'codex', 'grok', 'hermes']);
  assert.ok(config.BUILTIN.includes('chat-hermes'));
});

// ── Ui ────────────────────────────────────────────────────────────────────────
test('contrast of black on white is about 21 and is symmetric', () => {
  assert.ok(Math.abs(ctx.contrast(black, white) - 21) < 0.01);
  assert.equal(ctx.contrast(black, white), ctx.contrast(white, black));
  assert.ok(Math.abs(ctx.contrast(white, white) - 1) < 1e-9);
});

test('floor reaches the ratio and leaves readable colors alone', () => {
  const gray = rgb(0.25, 0.25, 0.25);
  assert.ok(ctx.contrast(gray, black) < 4.5);
  const lifted = ctx.floor(gray, black, white, 4.5);
  assert.ok(ctx.contrast(lifted, black) >= 4.5);
  assert.ok(lifted.r > gray.r);
  assert.equal(ctx.floor(white, black, white, 4.5), white);
  const stuck = ctx.floor(rgb(0.1, 0.1, 0.1), black, rgb(0.2, 0.2, 0.2), 21);
  assert.deepEqual([stuck.r, stuck.g, stuck.b], [0.2, 0.2, 0.2]);
});

test('ink uses bar.text unless it equals the foreground, and stays readable', () => {
  const orange = rgb(0.95, 0.5, 0.1), cyan = rgb(0.2, 0.8, 0.9), light = rgb(0.9, 0.9, 0.9);
  const C = {bar: {text: orange}, foreground: light, accent: cyan, background: rgb(0.05, 0.05, 0.08), muted: rgb(0.4, 0.4, 0.4)};
  const a = ctx.ink(C);
  assert.deepEqual([a.r, a.g, a.b], [orange.r, orange.g, orange.b]);
  const b = ctx.ink(Object.assign({}, C, {bar: {text: rgb(0.9, 0.9, 0.9)}}));
  assert.deepEqual([b.r, b.g, b.b], [cyan.r, cyan.g, cyan.b]);
  // a near-foreground bar text counts as the foreground
  const near = ctx.ink(Object.assign({}, C, {bar: {text: rgb(0.905, 0.9, 0.9)}}));
  assert.deepEqual([near.r, near.g, near.b], [cyan.r, cyan.g, cyan.b]);
  // dim bar text is lifted to 4.5:1 against the background
  const dim = ctx.ink(Object.assign({}, C, {bar: {text: rgb(0.2, 0.1, 0.05)}}));
  assert.ok(ctx.contrast(dim, C.background) >= 4.5);
  const dimAccent = ctx.ink(Object.assign({}, C, {bar: {text: light}, accent: rgb(0.1, 0.1, 0.2)}));
  assert.ok(ctx.contrast(dimAccent, C.background) >= 4.5);
});

test('muted is lifted to 4.5:1', () => {
  const C = {muted: rgb(0.15, 0.15, 0.15), background: black, foreground: white};
  assert.ok(ctx.contrast(ctx.muted(C), black) >= 4.5);
});

test('ago formats just now, minutes, hours and days', () => {
  const now = 1e12;
  assert.equal(ctx.ago(now - 5000, now), 'just now');
  assert.equal(ctx.ago(now + 5000, now), 'just now');
  assert.equal(ctx.ago(now - 59000, now), 'just now');
  assert.equal(ctx.ago(now - 5 * 60000, now), '5m ago');
  assert.equal(ctx.ago(now - 3 * 3600000 - 1000, now), '3h ago');
  assert.equal(ctx.ago(now - 2 * 86400000 - 1000, now), '2d ago');
  assert.equal(ctx.ago(NaN, now), 'a while ago');
  assert.equal(ctx.ago(undefined, now), 'a while ago');
});

test('nearestTheme picks the closest slug and skips themes without a preview', () => {
  const themes = [
    {slug: 'dark', background: '#000000', swatch: ['#ff0000']},
    {slug: 'darkish', background: '#101010', swatch: ['#00ff00']},
    {slug: 'light', background: '#ffffff', swatch: ['#0000ff']},
    {slug: 'nobg', background: '', swatch: []},
    {slug: 'nopreview', background: '#050505', swatch: ['#ff0000']},
  ];
  const have = {dark: true, darkish: true, light: true, nobg: true};
  assert.equal(ctx.nearestTheme(themes, have, Qt.color('#000000'), Qt.color('#ff0000')), 'dark');
  assert.equal(ctx.nearestTheme(themes, have, Qt.color('#0a0a0a'), Qt.color('#00ff00')), 'darkish');
  assert.equal(ctx.nearestTheme(themes, have, Qt.color('#fefefe'), Qt.color('#ff0000')), 'light');
  // 'nopreview' is closest by colour but has no preview image, 'nobg' has no background
  assert.notEqual(ctx.nearestTheme(themes, have, Qt.color('#050505'), Qt.color('#ff0000')), 'nopreview');
  assert.equal(ctx.nearestTheme(themes, {}, Qt.color('#000000'), Qt.color('#ff0000')), '');
  assert.equal(ctx.nearestTheme([], have, Qt.color('#000000'), Qt.color('#ff0000')), '');
  // a theme without a swatch still matches on background
  assert.equal(ctx.nearestTheme([{slug: 'x', background: '#000000'}], {x: true}, Qt.color('#000000'), Qt.color('#ff0000')), 'x');
});

test('mix and same helpers', () => {
  const m = ctx.mix(black, white, 0.5);
  assert.deepEqual([m.r, m.g, m.b, m.a], [0.5, 0.5, 0.5, 1]);
  assert.ok(ctx.same(black, rgb(0.005, 0, 0)));
  assert.ok(!ctx.same(black, white));
});

// ── Calendar grid ─────────────────────────────────────────────────────────────
test('Monday-first grid, leap year and month rollover', () => {
  assert.equal(calendar.grid(2024, 0).length, 42);
  assert.equal(calendar.grid(2024, 0)[0], 1);           // Mon 1 Jan 2024
  assert.equal(calendar.grid(2023, 9)[6], 1);           // Sun 1 Oct 2023
  assert.equal(calendar.grid(2023, 9)[0], 0);
  assert.equal(calendar.grid(2024, 1).filter(Boolean).length, 29);
  assert.equal(calendar.grid(2023, 1).filter(Boolean).length, 28);
  assert.equal(calendar.grid(2100, 1).filter(Boolean).length, 28);
  assert.equal(calendar.grid(2000, 1).filter(Boolean).length, 29);
  assert.equal(calendar.grid(2025, -1).filter(Boolean).length, 31);   // Dec 2024
  assert.equal(calendar.grid(2025, -1)[6], 1);                         // Sun 1 Dec 2024
  assert.equal(calendar.grid(2025, 12)[3], 1);                         // Thu 1 Jan 2026
  const days = calendar.grid(2026, 9).filter(Boolean);
  assert.deepEqual(days, Array.from({length: 31}, (_, i) => i + 1));
});

test('dayEvents includes multi-day events and respects day edges', () => {
  const at = (d, h) => new Date(2026, 9, d, h || 0).getTime();
  const events = [
    {summary: 'trip', time: at(10, 9), end: at(12, 10)},
    {summary: 'point', time: at(11, 12)},
    {summary: 'allday', time: at(11), end: at(12)},
    {summary: 'late', time: at(11, 23), end: at(12, 1)},
  ];
  const names = d => calendar.dayEvents(events, 2026, 9, d).map(e => e.summary);
  assert.deepEqual(names(9), []);
  assert.deepEqual(names(10), ['trip']);
  assert.deepEqual(names(11), ['trip', 'point', 'allday', 'late']);
  assert.deepEqual(names(12), ['trip', 'late']);   // allday ends at midnight: not on the 12th
  assert.deepEqual(names(13), []);
  assert.ok(calendar.onDay(events, 2026, 9, 11));
  assert.ok(!calendar.onDay(events, 2026, 9, 20));
  assert.deepEqual(calendar.dayEvents([], 2026, 9, 1), []);
});

// ── Glyphs: dock icons as logos or symbols ────────────────────────────────────
const brands = require('../Brands.js').PATHS;
const look = (e, o) => glyphs.look(e, o, brands);
const cp = (m) => m && m.glyph ? 'U+' + m.glyph.codePointAt(0).toString(16).toUpperCase() : '';
const logo = (slug) => ({path: brands[slug]});

test('every logo the rules name is vendored, as one 24x24 path', () => {
  for (const [, , slug] of glyphs.BRANDS) assert.ok(brands[slug], slug);
  for (const d of Object.values(brands)) assert.match(d, /^[Mm][MmLlHhVvCcSsQqTtAaZz\d\s.,+\-eE]+$/);
});

test('apps get their own logo by name, then id or icon', () => {
  assert.deepEqual(look({id: 'chromium', name: 'Chromium'}), logo('googlechrome'));
  assert.deepEqual(look({id: 'com.mitchellh.ghostty', name: 'Ghostty'}), logo('ghostty'));
  assert.deepEqual(look({id: 'org.telegram.desktop', name: 'Telegram Desktop'}), logo('telegram'));
  assert.deepEqual(look({id: 'obsidian', name: 'Obsidian'}), logo('obsidian'));
  assert.deepEqual(look({id: 'X', name: 'X'}), logo('x'));
  assert.deepEqual(look({id: 'yt', name: 'YouTube Music'}), logo('youtubemusic'));
  assert.deepEqual(look({id: 'my-discord', name: 'Chat app', icon: 'omarchy-discord'}), logo('discord'));
});

test('a Chrome web app gets its own logo, never Chromium\'s', () => {
  assert.deepEqual(look({id: 'chrome-fmp-Default', name: 'Claude', icon: 'chrome-fmp-Default'}), logo('claude'));
  const other = look({id: 'chrome-nfaecocciihflaoagabpadoaiidbnfek-Default', name: 'Some Web App', icon: 'chrome-nfaecocciihflaoagabpadoaiidbnfek-Default'});
  assert.equal(other.path, undefined);
  assert.equal(cp(other), 'U+F0C23');
});

test('generic tools and categories get a symbol; the rest their initial', () => {
  assert.equal(cp(look({id: 'org.gnome.Nautilus', name: 'Files'})), 'U+F024B');
  assert.equal(cp(look({id: 'zz', name: 'Zzterm', categories: ['System', 'TerminalEmulator']})), 'U+F018D');
  assert.equal(cp(look({id: 'zz', name: 'Zz', categories: {length: 2, 0: 'Network', 1: 'WebBrowser'}})), 'U+F059F');
  assert.equal(cp(look({id: 'zz', name: 'Gimme'})), 'U+F0BFF');
  assert.equal(cp(look({id: 'zz', name: 'hermes'})), 'U+F0C02');
  assert.equal(cp(look({id: 'zz', name: 'zed'})), 'U+F0C38');
  assert.equal(cp(look({id: 'zz', name: '1Up'})), 'U+F0614');
  assert.equal(cp(look(null)), 'U+F0614');
  // without the logo table a brand app falls through to its initial
  assert.equal(cp(glyphs.look({id: 'chromium', name: 'Chromium'})), 'U+F0BF3');
});

test('overrides take a logo slug, an SVG path, a symbol or its hex code', () => {
  assert.deepEqual(look({id: 'Home Server', name: 'Home Server'}, {'Home Server': 'hp'}), logo('hp'));
  assert.deepEqual(look({id: 'some-bot', name: 'Some Bot'}, {'Some Bot': 'M0 0h24v24H0z'}), {path: 'M0 0h24v24H0z'});
  assert.equal(cp(look({id: 'some-bot', name: 'Some Bot'}, {'some-bot': 'U+F048B'})), 'U+F048B');
  assert.deepEqual(look({id: 'a', name: 'A'}, {a: '\u2605'}), {glyph: '\u2605'});
  // junk, or a path with anything but path commands, is ignored
  for (const bad of ['', 'abc', 'zzzzzzz', '0x1', 'M0 0"/><script>', 5, null])
    assert.deepEqual(look({id: 'chromium', name: 'Chromium'}, {chromium: bad}), logo('googlechrome'), String(bad));
});

test('apps with no logo or tool symbol use the shape traced from their icon', () => {
  const marks = {'some-icon': {path: 'M0 0h24v24H0z'}, empty: {path: ''}};
  assert.deepEqual(glyphs.look({id: 'q', name: 'Qq', icon: 'some-icon'}, {}, brands, marks), {path: 'M0 0h24v24H0z', evenodd: true});
  // a logo or a tool symbol still wins, an empty trace falls through
  assert.deepEqual(glyphs.look({id: 'obsidian', name: 'Obsidian', icon: 'some-icon'}, {}, brands, marks), logo('obsidian'));
  assert.equal(cp(glyphs.look({id: 'q', name: 'Files', icon: 'some-icon'}, {}, brands, marks)), 'U+F024B');
  assert.equal(cp(glyphs.look({id: 'q', name: 'Qq', icon: 'empty'}, {}, brands, marks)), 'U+F0C1D');
});

test('a logo becomes an SVG filled with the given color', () => {
  const url = glyphs.svgUrl('M0 0h24v24H0z', '#ffaa00');
  assert.ok(url.startsWith('data:image/svg+xml;utf8,'));
  const svg = decodeURIComponent(url.slice(24));
  assert.match(svg, /viewBox="0 0 24 24"/);
  assert.match(svg, /<path fill="#ffaa00" d="M0 0h24v24H0z"\/>/);
  assert.match(decodeURIComponent(glyphs.svgUrl('M0 0Z', '#fff', true).slice(24)), /fill-rule="evenodd"/);
});

test('parse keeps icon overrides as strings of a sane length', () => {
  const d = config.parse(JSON.stringify({dockSymbols: {a: 'f048b', b: 7, c: 'M' + '1'.repeat(20000), p: 'M0 0h24v24H0z'}})).dockSymbols;
  assert.deepEqual(d, {a: 'f048b', p: 'M0 0h24v24H0z'});
  assert.deepEqual(config.parse(JSON.stringify({dockSymbols: ['f048b']})).dockSymbols, {});
  assert.deepEqual(config.defaults().dockSymbols, {});
});
