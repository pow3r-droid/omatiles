// Dock icons as one-color marks, like a phone's themed icon pack: each app drawn
// in the bar's color as its own logo (from Simple Icons, in Brands.js) or, for
// generic tools, a symbol from the Nerd Font the bar already uses. An app is
// matched by its name first, then its desktop id, icon or window class, then its
// menu categories; an app none of those cover shows its initial in a circle.
//
// Apps with no logo and no generic symbol get their own shape, traced from their
// icon by the backend (icontrace.py) into `marks`: {icon name: {path}}.
//
// look() returns {path: "<24 x 24 SVG path>", evenodd?} for a logo or a traced
// shape, or {glyph: "<char>"} for a symbol.

// [name, ids, Simple Icons slug]. `name` is tested against the app's display
// name, `ids` against its desktop id, icon name and window class (lower case).
var BRANDS = [
    [/^(chromium|google chrome)\b/, /^(chromium|chromium-browser|google-chrome.*|com\.google\.chrome)$/, 'googlechrome'],
    [/^firefox\b/, /^(firefox|org\.mozilla\.firefox)$/, 'firefoxbrowser'],
    [/^brave\b/, /^(brave|brave-browser|com\.brave\.browser)$/, 'brave'],
    [/^vivaldi$/, /^vivaldi(-stable)?$/, 'vivaldi'],
    [/^opera$/, /^opera$/, 'opera'],
    [/^zen( browser)?$/, /^(zen|zen-browser|app\.zen_browser\.zen)$/, 'zenbrowser'],
    [/^ghostty$/, /^com\.mitchellh\.ghostty$/, 'ghostty'],
    [/^alacritty$/, /^alacritty$/, 'alacritty'],
    [/^(terminal|console|gnome terminal)$/, /^(org\.gnome\.terminal|org\.gnome\.console)$/, 'gnometerminal'],
    [/^wezterm$/, /^org\.wezfurlong\.wezterm$/, 'wezterm'],
    [/^warp$/, /^dev\.warp\.warp$/, 'warp'],
    [/^tmux$/, /^tmux$/, 'tmux'],
    [/^telegram/, /^(org\.telegram\.desktop|telegram-desktop|telegram)$/, 'telegram'],
    [/^obsidian$/, /^(obsidian|md\.obsidian\.obsidian)$/, 'obsidian'],
    [/^claude\b/, /^claude$/, 'claude'],
    [/^(x|twitter)$/, /^(x|twitter)$/, 'x'],
    [/^youtube music$/, /^youtube-music$/, 'youtubemusic'],
    [/^youtube$/, /^youtube$/, 'youtube'],
    [/^whatsapp$/, /^whatsapp$/, 'whatsapp'],
    [/^discord$/, /^(discord|com\.discordapp\.discord|omarchy-discord)$/, 'discord'],
    [/^spotify$/, /^(spotify|com\.spotify\.client)$/, 'spotify'],
    [/^signal$/, /^(signal|signal-desktop|org\.signal\.signal)$/, 'signal'],
    [/^docker( desktop)?$/, /^(docker|docker-desktop)$/, 'docker'],
    [/^steam$/, /^(steam|com\.valvesoftware\.steam)$/, 'steam'],
    [/^github( desktop)?$/, /^(github|github-desktop)$/, 'github'],
    [/^gitlab$/, /^gitlab$/, 'gitlab'],
    [/^vscodium$/, /^(codium|vscodium|com\.vscodium\.codium)$/, 'vscodium'],
    [/^neovim$|^nvim$/, /^(nvim|neovim)$/, 'neovim'],
    [/^g?vim$/, /^(vim|gvim)$/, 'vim'],
    [/^gimp\b|^gnu image/, /^(gimp|org\.gimp\.gimp)$/, 'gimp'],
    [/^inkscape$/, /^(inkscape|org\.inkscape\.inkscape)$/, 'inkscape'],
    [/^krita$/, /^(krita|org\.kde\.krita)$/, 'krita'],
    [/^blender$/, /^(blender|org\.blender\.blender)$/, 'blender'],
    [/^libreoffice/, /^libreoffice/, 'libreoffice'],
    [/^thunderbird$/, /^(thunderbird|org\.mozilla\.thunderbird)$/, 'thunderbird'],
    [/^zoom( workplace)?$/, /^(zoom|us\.zoom\.zoom)$/, 'zoom'],
    [/^1password$/, /^1password$/, '1password'],
    [/^bitwarden$/, /^(bitwarden|com\.bitwarden\.desktop)$/, 'bitwarden'],
    [/^keepassxc$/, /^(keepassxc|org\.keepassxc\.keepassxc)$/, 'keepassxc'],
    [/^vlc\b/, /^(vlc|org\.videolan\.vlc)$/, 'vlcmediaplayer'],
    [/^mpv\b/, /^(mpv|io\.mpv\.mpv)$/, 'mpv'],
    [/^obs( studio)?$/, /^(obs|com\.obsproject\.studio)$/, 'obsstudio'],
    [/^kdenlive$/, /^(kdenlive|org\.kde\.kdenlive)$/, 'kdenlive'],
    [/^audacity$/, /^(audacity|org\.audacityteam\.audacity)$/, 'audacity'],
    [/^localsend$/, /^(localsend|org\.localsend\.localsend_app)$/, 'localsend'],
    [/^basecamp$/, /^basecamp$/, 'basecamp'],
    [/^hey$/, /^hey$/, 'hey'],
    [/^notion$/, /^notion(-app)?$/, 'notion'],
    [/^figma$/, /^figma(-linux)?$/, 'figma'],
    [/^postman$/, /^postman$/, 'postman'],
    [/^dbeaver/, /^(dbeaver|io\.dbeaver\.dbeavercommunity)$/, 'dbeaver'],
    [/^intellij idea/, /^(intellij-idea.*|jetbrains-idea.*)$/, 'intellijidea'],
    [/^pycharm/, /^(pycharm.*|jetbrains-pycharm.*)$/, 'pycharm'],
    [/^android studio$/, /^(android-studio|jetbrains-studio)$/, 'androidstudio'],
    [/^(google )?gemini$/, /^gemini$/, 'googlegemini'],
    [/^perplexity$/, /^perplexity$/, 'perplexity'],
    [/^ollama$/, /^ollama$/, 'ollama'],
    [/^home assistant$/, /^home-?assistant$/, 'homeassistant'],
    [/^syncthing/, /^syncthing(-gtk)?$/, 'syncthing'],
    [/^nextcloud/, /^(nextcloud|com\.nextcloud\.desktopclient\.nextcloud)$/, 'nextcloud'],
    [/^proton mail$/, /^proton-mail$/, 'protonmail'],
    [/^proton vpn$/, /^(protonvpn|proton\.vpn\.app\.gtk)$/, 'protonvpn'],
    [/^tailscale$/, /^tailscale$/, 'tailscale'],
    [/^reddit$/, /^reddit$/, 'reddit'],
    [/^twitch$/, /^twitch$/, 'twitch'],
    [/^instagram$/, /^instagram$/, 'instagram'],
    [/^facebook$/, /^facebook$/, 'facebook'],
    [/^messenger$/, /^messenger$/, 'messenger'],
    [/^threads$/, /^threads$/, 'threads'],
    [/^bluesky$/, /^bluesky$/, 'bluesky'],
    [/^mastodon$/, /^(mastodon|org\.joinmastodon.*)$/, 'mastodon'],
    [/^element$/, /^(element|element-desktop|im\.riot\.riot)$/, 'element'],
    [/^cursor$/, /^cursor$/, 'cursor'],
    [/^filezilla$/, /^filezilla$/, 'filezilla'],
    [/^transmission/, /^transmission(-gtk|-qt)?$/, 'transmission'],
    [/^qbittorrent$/, /^(qbittorrent|org\.qbittorrent\.qbittorrent)$/, 'qbittorrent'],
    [/^zotero$/, /^(zotero|org\.zotero\.zotero)$/, 'zotero'],
    [/^anki$/, /^(anki|net\.ankiweb\.anki)$/, 'anki']
];

// [name, ids, code point]: generic tools, which have no logo of their own.
var APPS = [
    [/^(kitty|foot|konsole|xterm)$/, /^(kitty|foot|org\.kde\.konsole|xterm)$/, 0xF018D],
    [/^(files|nautilus|thunar|dolphin|nemo)$/, /^(org\.gnome\.nautilus|thunar|org\.kde\.dolphin|nemo)$/, 0xF024B],
    [/^typora$/, /^typora$/, 0xF0354],
    [/^(calculator|gnome calculator|qalculate)/, /^(org\.gnome\.calculator|qalculate-gtk)$/, 0xF00EC],
    [/^xournal\+\+$/, /^(xournalpp|com\.github\.xournalpp\.xournalpp)$/, 0xF0F49],
    [/^slack$/, /^(slack|com\.slack\.slack)$/, 0xF04B1],
    [/^(visual studio code|code|vs ?code)$/, /^(code|code-oss|visual-studio-code|com\.visualstudio\.code)$/, 0xF0A1E],
    [/^(microsoft )?teams/, /^teams/, 0xF02BB],
    [/^(gmail|mail|geary|evolution)$/, /^(gmail|geary|org\.gnome\.geary)$/, 0xF01EE],
    [/^(celluloid|videos|totem)$/, /^(io\.github\.celluloid_player\.celluloid|org\.gnome\.totem)$/, 0xF040C],
    [/^(btop|htop|system monitor)/, /^(btop|htop|gnome-system-monitor)$/, 0xF029A],
    [/^(settings|omarchy settings)$/, /^(org\.gnome\.settings)$/, 0xF0493],
    [/^weather$/, /^org\.gnome\.weather$/, 0xF0595],
    [/^(camera|cheese|snapshot)$/, /^(org\.gnome\.snapshot|org\.gnome\.cheese)$/, 0xF0100],
    [/^pinta$/, /^com\.github\.pinta_project\.pinta$/, 0xF03D8]
];
// Freedesktop menu categories, for apps neither list names.
var CATEGORIES = [
    ['TerminalEmulator', 0xF018D], ['WebBrowser', 0xF059F], ['FileManager', 0xF024B],
    ['InstantMessaging', 0xF0B79], ['Chat', 0xF0B79], ['Email', 0xF01EE], ['Game', 0xF0297],
    ['TextEditor', 0xF039E], ['IDE', 0xF0A1E], ['Calculator', 0xF00EC], ['Player', 0xF040C],
    ['Music', 0xF075A], ['Audio', 0xF02CB], ['Video', 0xF0567], ['Photography', 0xF0100],
    ['Graphics', 0xF03D8], ['Office', 0xF0219], ['Settings', 0xF0493], ['Monitor', 0xF029A]
];

function hex(code) { return String.fromCodePoint(code); }

// An override names a logo (a Simple Icons slug from Brands.js, or a 24 x 24 SVG
// path starting with M), or a symbol (the character itself, or its hex code
// such as "f048b" or "U+F048B"). Anything else is ignored.
function fromOverride(v, paths) {
    if (typeof v !== 'string' || !(v = v.trim())) return null;
    if (paths && Object.prototype.hasOwnProperty.call(paths, v.toLowerCase())) return {path: paths[v.toLowerCase()]};
    if (/^[Mm][\d\s.,+\-]/.test(v) && /^[MmLlHhVvCcSsQqTtAaZz\d\s.,+\-eE]+$/.test(v)) return {path: v};
    var m = /^(?:u\+|0x)?([0-9a-f]{4,6})$/i.exec(v);
    if (m) { var c = parseInt(m[1], 16); return c > 0x20 && c <= 0x10FFFF ? {glyph: hex(c)} : null; }
    return Array.from(v).length === 1 ? {glyph: v} : null;
}

// The first table entry matching the app: by name, else by desktop id, icon or class.
function byName(table, name) {
    var low = String(name || '').trim().toLowerCase();
    for (var i = 0; i < table.length; i++) if (table[i][0].test(low)) return table[i][2];
    return null;
}
function byIds(table, entry) {
    var keys = [entry.id, entry.icon, entry.startupClass].map(function(k){ return String(k || '').toLowerCase(); }).filter(function(k){ return k; });
    for (var i = 0; i < table.length; i++) if (keys.some(function(k){ return table[i][1].test(k); })) return table[i][2];
    return null;
}

function look(entry, overrides, paths, marks) {
    if (!entry) return {glyph: initial(null)};
    var id = String(entry.id || ''), name = String(entry.name || '').trim(), i;
    if (overrides && typeof overrides === 'object') {
        var o = fromOverride(overrides[id], paths) || fromOverride(overrides[name], paths);
        if (o) return o;
    }
    // Names before ids across both lists, so a web app named "Claude" whose id
    // is chrome-… gets Claude's logo, not Chrome's.
    var slug = byName(BRANDS, name), code = slug ? null : byName(APPS, name);
    if (!slug && !code) slug = byIds(BRANDS, entry);
    if (!slug && !code) code = byIds(APPS, entry);
    if (slug && paths && paths[slug]) return {path: paths[slug]};
    if (code) return {glyph: hex(code)};
    var traced = marks && entry.icon && marks[entry.icon];
    if (traced && typeof traced.path === 'string' && traced.path) return {path: traced.path, evenodd: true};
    // A QML list, not always a real array: compare item by item.
    var cats = [], list = entry.categories || [];
    for (i = 0; i < (list.length || 0); i++) cats.push(String(list[i]));
    for (i = 0; i < CATEGORIES.length; i++) if (cats.indexOf(CATEGORIES[i][0]) !== -1) return {glyph: hex(CATEGORIES[i][1])};
    return {glyph: initial(entry)};
}

// What an app with no logo or symbol shows: its first letter in a circle, drawn
// like the symbols (Material's alpha_<letter>_circle_outline run, three code points apart).
function initial(entry) {
    var c = (Array.from(String(entry && entry.name || '').trim())[0] || '').toLowerCase();
    return c >= 'a' && c <= 'z' ? hex(0xF0BED + 3 * (c.charCodeAt(0) - 97)) : hex(0xF0614);
}

// The SVG for a logo, filled with the bar's color, as an Image source. Traced
// shapes fill even-odd, so their holes stay open whichever way they were traced.
function svgUrl(path, color, evenodd) {
    return 'data:image/svg+xml;utf8,' + encodeURIComponent(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path fill="' + color + '"'
        + (evenodd ? ' fill-rule="evenodd"' : '') + ' d="' + path + '"/></svg>');
}

if (typeof module !== 'undefined') module.exports = {look: look, initial: initial, fromOverride: fromOverride, svgUrl: svgUrl, BRANDS: BRANDS, APPS: APPS, CATEGORIES: CATEGORIES};
