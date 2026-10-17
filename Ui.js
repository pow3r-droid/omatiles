// Theme-derived colors with a readability floor, and small formatting helpers.
// Colors are QML color values (r, g, b, a in 0..1).

function luminance(c) {
    function ch(v) { return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }
    return 0.2126 * ch(c.r) + 0.7152 * ch(c.g) + 0.0722 * ch(c.b);
}
function contrast(a, b) {
    var x = luminance(a), y = luminance(b);
    return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
}
function mix(a, b, t) { return Qt.rgba(a.r + (b.r - a.r) * t, a.g + (b.g - a.g) * t, a.b + (b.b - a.b) * t, 1); }
function same(a, b) { return Math.abs(a.r - b.r) + Math.abs(a.g - b.g) + Math.abs(a.b - b.b) < 0.02; }

// `c`, moved toward `toward` just far enough to reach `ratio` against `bg`.
function floor(c, bg, toward, ratio) {
    if (contrast(c, bg) >= ratio) return c;
    for (var t = 0.05; t < 1; t += 0.05) {
        var m = mix(c, toward, t);
        if (contrast(m, bg) >= ratio) return m;
    }
    return toward;
}

// The desk's accent: the bar's text color when the theme sets one (it is the
// shell's own accent, e.g. Demon's orange), else the theme accent; readable either way.
function ink(C) {
    var pick = same(C.bar.text, C.foreground) ? C.accent : C.bar.text;
    return floor(pick, C.background, C.foreground, 4.5);
}
// Secondary text, lifted to 4.5:1 when the theme's muted color is dimmer.
function muted(C) { return floor(C.muted, C.background, C.foreground, 4.5); }

// "just now", "5m ago", "3h ago", "2d ago" for an epoch-ms time.
function ago(ms, now) {
    var s = Math.floor((now - ms) / 1000);
    if (!isFinite(s)) return "a while ago";
    if (s < 60) return "just now";
    if (s < 3600) return Math.floor(s / 60) + "m ago";
    if (s < 86400) return Math.floor(s / 3600) + "h ago";
    return Math.floor(s / 86400) + "d ago";
}

// Store previews exist for some themes only; pick the one closest to the current
// theme by background, then accent.
function nearestTheme(themes, have, bg, accent) {
    var best = "", score = 1e9;
    for (var i = 0; i < themes.length; i++) {
        var t = themes[i];
        if (!have[t.slug] || !t.background) continue;
        var b = Qt.color(t.background), a = t.swatch && t.swatch.length ? Qt.color(t.swatch[0]) : b;
        var d = 3 * (Math.abs(b.r - bg.r) + Math.abs(b.g - bg.g) + Math.abs(b.b - bg.b))
              + (Math.abs(a.r - accent.r) + Math.abs(a.g - accent.g) + Math.abs(a.b - accent.b));
        if (d < score) { score = d; best = t.slug; }
    }
    return best;
}
