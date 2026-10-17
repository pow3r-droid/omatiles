// Symbol dock icons, like a phone's themed icon pack: each app drawn as one
// symbol from the Nerd Font the bar already uses, in the bar's color. An app is
// matched by its name first, then its desktop id, icon or window class, then
// its menu categories; an app none of those cover shows its initial in a circle.

// [name, ids, code point]. `name` is tested against the app's display name,
// `ids` against its desktop id, icon name and window class (all lower case).
var APPS = [
    [/^(chromium|google chrome)\b/, /^(chromium|chromium-browser|google-chrome.*|com\.google\.chrome)$/, 0xF02AF],
    [/^firefox\b/, /^(firefox|org\.mozilla\.firefox)$/, 0xF0239],
    [/^ghostty$/, /^com\.mitchellh\.ghostty$/, 0xF02A0],
    [/^(alacritty|kitty|foot|wezterm|konsole|terminal|xterm)$/, /^(alacritty|kitty|foot|org\.wezfurlong\.wezterm|org\.kde\.konsole|org\.gnome\.terminal|org\.gnome\.console)$/, 0xF018D],
    [/^(files|nautilus|thunar|dolphin|nemo)$/, /^(org\.gnome\.nautilus|thunar|org\.kde\.dolphin|nemo)$/, 0xF024B],
    [/^obsidian$/, /^(obsidian|md\.obsidian\.obsidian)$/, 0xF01C8],
    [/^spotify$/, /^(spotify|com\.spotify\.client)$/, 0xF04C7],
    [/^signal$/, /^(signal|signal-desktop|org\.signal\.signal)$/, 0xF0B79],
    [/^typora$/, /^typora$/, 0xF0354],
    [/^(calculator|gnome calculator|qalculate)/, /^(org\.gnome\.calculator|qalculate-gtk)$/, 0xF00EC],
    [/^localsend$/, /^(localsend|org\.localsend\.localsend_app)$/, 0xF0497],
    [/^xournal\+\+$/, /^(xournalpp|com\.github\.xournalpp\.xournalpp)$/, 0xF0F49],
    [/^telegram/, /^(org\.telegram\.desktop|telegram-desktop|telegram)$/, 0xF1D8],
    [/^whatsapp$/, /^whatsapp$/, 0xF232],
    [/^youtube( music)?$/, /^youtube$/, 0xF05C3],
    [/^discord$/, /^(discord|com\.discordapp\.discord|omarchy-discord)$/, 0xF1FF],
    [/^(x|twitter)$/, /^(x|twitter)$/, 0xF0B1F],
    [/^instagram$/, /^instagram$/, 0xF02FE],
    [/^facebook$/, /^facebook$/, 0xF020C],
    [/^reddit$/, /^reddit$/, 0xF044D],
    [/^twitch$/, /^twitch$/, 0xF0543],
    [/^github( desktop)?$/, /^(github|github-desktop)$/, 0xF02A4],
    [/^claude\b/, /^claude$/, 0xF06C4],
    [/^chatgpt$/, /^chatgpt$/, 0xF0674],
    [/^docker( desktop)?$/, /^(docker|docker-desktop)$/, 0xF0868],
    [/^(visual studio code|code|vs ?code|vscodium)$/, /^(code|code-oss|visual-studio-code|vscodium|com\.visualstudio\.code)$/, 0xF0A1E],
    [/^n?vim$|^neovim$/, /^(nvim|vim|neovim)$/, 0xF36F],
    [/^steam$/, /^(steam|com\.valvesoftware\.steam)$/, 0xF04D3],
    [/^gimp\b/, /^(gimp|org\.gimp\.gimp)$/, 0xF338],
    [/^libreoffice/, /^libreoffice/, 0xF376],
    [/^thunderbird$/, /^(thunderbird|org\.mozilla\.thunderbird)$/, 0xF370],
    [/^(hey|gmail|mail|geary|evolution)$/, /^(hey|gmail|geary|org\.gnome\.geary)$/, 0xF01EE],
    [/^slack$/, /^(slack|com\.slack\.slack)$/, 0xF04B1],
    [/^(microsoft )?teams/, /^teams/, 0xF02BB],
    [/^1password$/, /^1password$/, 0xF0881],
    [/^vlc\b/, /^(vlc|org\.videolan\.vlc)$/, 0xF057C],
    [/^(mpv|celluloid|videos|totem)$/, /^(mpv|io\.github\.celluloid_player\.celluloid|org\.gnome\.totem)$/, 0xF040C],
    [/^kdenlive$/, /^(kdenlive|org\.kde\.kdenlive)$/, 0xF33C],
    [/^obs\b/, /^(obs|com\.obsproject\.studio)$/, 0xF0567],
    [/^(btop|htop|system monitor)/, /^(btop|htop|gnome-system-monitor)$/, 0xF029A],
    [/^home assistant$/, /^home-?assistant$/, 0xF07D0],
    [/^solar/, /^solar/, 0xF0A72],
    [/^(settings|omarchy settings)$/, /^(org\.gnome\.settings)$/, 0xF0493],
    [/^weather$/, /^org\.gnome\.weather$/, 0xF0595],
    [/^(camera|cheese|snapshot)$/, /^(org\.gnome\.snapshot|org\.gnome\.cheese)$/, 0xF0100],
    [/^(pinta|krita|inkscape)$/, /^(com\.github\.pinta_project\.pinta|org\.kde\.krita|org\.inkscape\.inkscape)$/, 0xF03D8]
];
// Freedesktop menu categories, for apps the list above doesn't name.
var CATEGORIES = [
    ['TerminalEmulator', 0xF018D], ['WebBrowser', 0xF059F], ['FileManager', 0xF024B],
    ['InstantMessaging', 0xF0B79], ['Chat', 0xF0B79], ['Email', 0xF01EE], ['Game', 0xF0297],
    ['TextEditor', 0xF039E], ['IDE', 0xF0A1E], ['Calculator', 0xF00EC], ['Player', 0xF040C],
    ['Music', 0xF075A], ['Audio', 0xF02CB], ['Video', 0xF0567], ['Photography', 0xF0100],
    ['Graphics', 0xF03D8], ['Office', 0xF0219], ['Settings', 0xF0493], ['Monitor', 0xF029A]
];

function hex(code) { return String.fromCodePoint(code); }

// `overrides` maps a desktop id or app name to a symbol: the character itself,
// or its code as hex ("f048b", "U+F048B"). Anything else is ignored.
function fromOverride(v) {
    if (typeof v !== 'string' || !v) return '';
    var m = /^(?:u\+|0x)?([0-9a-f]{4,6})$/i.exec(v.trim());
    if (m) { var c = parseInt(m[1], 16); return c > 0x20 && c <= 0x10FFFF ? hex(c) : ''; }
    return Array.from(v.trim()).length === 1 ? v.trim() : '';
}

function symbol(entry, overrides) {
    if (!entry) return '';
    var id = String(entry.id || ''), name = String(entry.name || '').trim();
    if (overrides && typeof overrides === 'object') {
        var o = fromOverride(overrides[id]) || fromOverride(overrides[name]);
        if (o) return o;
    }
    var low = name.toLowerCase(), i;
    for (i = 0; i < APPS.length; i++) if (APPS[i][0].test(low)) return hex(APPS[i][2]);
    var keys = [id, entry.icon, entry.startupClass].map(function(k){ return String(k || '').toLowerCase(); }).filter(function(k){ return k; });
    for (i = 0; i < APPS.length; i++) if (keys.some(function(k){ return APPS[i][1].test(k); })) return hex(APPS[i][2]);
    // A QML list, not always a real array: compare item by item.
    var cats = [], list = entry.categories || [];
    for (i = 0; i < (list.length || 0); i++) cats.push(String(list[i]));
    for (i = 0; i < CATEGORIES.length; i++) if (cats.indexOf(CATEGORIES[i][0]) !== -1) return hex(CATEGORIES[i][1]);
    return '';
}

// What an app with no symbol shows: its first letter in a circle, drawn like the
// symbols (Material's alpha_<letter>_circle_outline run, three code points apart).
function initial(entry) {
    var c = (Array.from(String(entry && entry.name || '').trim())[0] || '').toLowerCase();
    return c >= 'a' && c <= 'z' ? hex(0xF0BED + 3 * (c.charCodeAt(0) - 97)) : hex(0xF0614);
}

if (typeof module !== 'undefined') module.exports = {symbol: symbol, initial: initial, fromOverride: fromOverride, APPS: APPS, CATEGORIES: CATEGORIES};
