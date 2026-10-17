import QtQuick
import qs.Commons
import Quickshell
import Quickshell.Io
import Quickshell.Hyprland
import Quickshell.Wayland
import Qt.labs.folderlistmodel
import "Config.js" as Config
import "Ui.js" as Ui
import "calendar/Model.js" as Calendar
import "owl" as Owl
import "owl/Owl.js" as OwlJs
import "Glyphs.js" as Glyphs

// OmaTiles: a home screen on the first workspaces (1, 1-2 or 1-3, picked on first
// run), a 16 x 8 grid of tiles above an app dock, drawn in the active Omarchy theme.
// Later workspaces stay ordinary tiling ones. Right-click opens its menu.
Scope {
    id: root
    readonly property string home: Quickshell.env("HOME")
    readonly property string cache: home + "/.cache/omatiles/"
    readonly property string backend: Qt.resolvedUrl("backend.py").toString().replace(/^file:\/\//, "")
    readonly property string gcal: Qt.resolvedUrl("gcal.py").toString().replace(/^file:\/\//, "")
    readonly property string readme: "https://github.com/pow3r-droid/omatiles#readme"
    property var config: Config.defaults()
    property double now: Date.now()
    property int year: new Date().getFullYear()
    property int month: new Date().getMonth()
    property bool browsed: false

    // ── Where the desk shows ────────────────────────────────────────────────
    // Workspaces 1 to `pages` are desk pages: the desk shows on the monitor showing
    // one of them, with that page's tiles. Until the user picks, all three are.
    readonly property int pages: config.desks || Config.PAGES
    readonly property bool choosing: loaded && !config.desks
    // Tiles kept on desks the user turned off: they come back with those desks.
    readonly property int hiddenTiles: Object.keys(config.tiles).filter(function(k){ var t = config.tiles[k]; return t.enabled && (t.page || 1) > pages; }).length
    readonly property Item deskItem: desk
    readonly property var deskScreen: {
        var screens = Quickshell.screens;
        for (var i=0;i<screens.length;i++) {
            var hm=Hyprland.monitorFor(screens[i]);
            if(hm && hm.activeWorkspace && hm.activeWorkspace.id>=1 && hm.activeWorkspace.id<=pages) return {screen: screens[i], page: hm.activeWorkspace.id};
        }
        return null;
    }
    readonly property var monitor: deskScreen ? deskScreen.screen : null
    property int page: 1
    onDeskScreenChanged: if(deskScreen) page = deskScreen.page
    onPageChanged: { menuOpen = false; dockPick = null; focusKey = ""; }
    readonly property bool shown: monitor !== null
    // Tiled windows cover the desk; it then stops animating and polling widgets.
    readonly property var deskWs: monitor ? Hyprland.monitorFor(monitor).activeWorkspace : null
    readonly property bool covered: !!deskWs && deskWs.toplevels.values.some(function(t){ return t.lastIpcObject && t.lastIpcObject.floating === false; })
    readonly property bool live: shown && !covered
    Connections {
        target: Hyprland
        function onRawEvent(event) {
            if (/^(openwindow|closewindow|movewindow|changefloatingmode|fullscreen)/.test(event.name)) Hyprland.refreshToplevels();
            if (event.name === "openwindow") { var w = event.parse(4); root.noteWindow(w[2] || ""); root.keepOff(w[0] || ""); }
        }
    }
    property bool editing: false
    property bool typing: false
    // Keyboard mode (`omatiles focus`): arrows pick a tile, Enter uses it, Esc leaves.
    property bool focusing: false
    property string focusKey: ""
    onShownChanged: if(!shown) { editing=false; typing=false; focusing=false; }

    // ── Theme ───────────────────────────────────────────────────────────────
    // The desk's accent is the bar's text color when the theme sets one (the
    // shell's own accent), else the theme accent, kept readable on the background.
    readonly property color ink: Ui.ink(Color)
    readonly property color muted: Ui.muted(Color)
    // Red is kept for failure and destruction only.
    readonly property color danger: Ui.danger(Color)
    readonly property bool metric: config.units === "metric" || (config.units === "auto" && Qt.locale().measurementSystem === Locale.MetricSystem)
    readonly property bool h12: /a|AP/i.test(Qt.locale().timeFormat(Locale.ShortFormat))
    // The locale's short date without the year: "M/d", "dd.MM", "MM-dd".
    readonly property string monthDay: Qt.locale().dateFormat(Locale.ShortFormat).replace(/[^dM]*y+[^dM]*/, "")
    property var owlPalette: OwlJs.themeFromToml("")
    property string themeSlug: ""
    property var themeList: []

    component JsonFile: FileView {
        property var value: fallback
        property var fallback: null
        printErrors: false; watchChanges: true
        onFileChanged: reload()
        onLoaded: { try { value = JSON.parse(text()); } catch(e) { value = fallback; } }
        onLoadFailed: value = fallback
    }
    FileView {
        path: root.home + "/.local/state/omarchy/current/theme/colors.toml"; watchChanges: true; printErrors: false
        onFileChanged: reload()
        onLoaded: root.owlPalette = OwlJs.themeFromToml(text())
    }
    FileView {
        path: root.home + "/.local/state/omarchy/current/theme.name"; watchChanges: true; printErrors: false
        onFileChanged: reload()
        onLoaded: root.themeSlug = text().trim()
    }
    Process {
        id: themesProc; command: ["python3",root.backend,"themes"]
        stdout: StdioCollector { waitForEnd: true; onStreamFinished: { try { root.themeList = JSON.parse(text); } catch(e) {} } }
    }
    function loadThemes() { if (!themesProc.running && root.themeList.length === 0) themesProc.running = true; }

    // ── Settings and cached data ────────────────────────────────────────────
    Process {
        id: init
        command: ["python3", root.backend, "init", JSON.stringify(Config.defaults())]
        running: true
        onExited: { settings.reload(); [calendarFile, gcalStatusFile, remoteFile, localFile, weatherFile, agentsFile, recentFile].forEach(function(f){ f.reload(); }); root.refresh(); }
    }
    FileView {
        id: settings; printErrors: false; path: root.home + "/.config/omarchy/omatiles.json"; watchChanges: true
        onFileChanged: reload()
        onLoaded: { root.config=Config.parse(text()); root.loaded=true; }
    }
    // Nothing draws or polls until the settings are read, so the default layout never flashes.
    property bool loaded: false
    JsonFile { id: calendarFile; path: root.cache + "gcal-events.json"; fallback: [] }
    JsonFile { id: gcalStatusFile; path: root.cache + "gcal-status.json"; fallback: ({state: "disconnected"}) }
    JsonFile { id: remoteFile; path: root.cache + "remote.json" }
    JsonFile { id: localFile; path: root.cache + "local.json" }
    JsonFile { id: weatherFile; path: root.cache + "weather.json" }
    JsonFile { id: agentsFile; path: root.cache + "agents.json"; fallback: ({}) }
    JsonFile { id: recentFile; path: root.cache + "recent.json"; fallback: [] }
    readonly property var events: Array.isArray(calendarFile.value) ? calendarFile.value : []
    readonly property string gcalState: gcalStatusFile.value && gcalStatusFile.value.state || "disconnected"
    readonly property var remote: remoteFile.value
    readonly property var local: localFile.value
    readonly property var weather: weatherFile.value && weatherFile.value.days ? weatherFile.value : null
    // A watched file that did not exist yet is not picked up by itself, so each job reloads what it wrote.
    Process { id: remoteFetch; command: ["python3",root.backend,"probe","remote"]; onExited: remoteFile.reload() }
    Process { id: localFetch; command: ["python3",root.backend,"probe","local"]; onExited: localFile.reload() }
    Process { id: weatherFetch; command: ["python3",root.backend,"weather"]; onExited: weatherFile.reload() }
    Process { id: placeProc }
    Process { id: openUrl; property string url; command: ["xdg-open",url] }
    function run(proc, args) { if (proc.running) return false; proc.command = ["python3", root.backend].concat(args); proc.running = true; return true; }
    function setOption(name, value) { Quickshell.execDetached(["python3", root.backend, "set", name, String(value)]); }
    // Links come from chat replies and calendar events, so only web links open.
    function openLink(url) { if (/^https?:\/\//i.test(url || "") && !openUrl.running) { openUrl.url = url; openUrl.running = true; } }

    // The remote card reads its machine only when asked (its refresh link),
    // never on a timer; this machine's card reads every minute while it shows.
    function onScreen(key) { var t = config.tiles[key]; return loaded && !!t && t.enabled && (t.page || 1) === page && live; }
    function onPage(key) { var t = config.tiles[key]; return !!t && t.enabled && (t.page || 1) === page; }
    readonly property bool localShown: onScreen("local")
    function refresh() { if(localShown && !localFetch.running)localFetch.running=true; if(!weatherFetch.running)weatherFetch.running=true; }
    function refreshRemote() { if(!remoteFetch.running)remoteFetch.running=true; }
    onLocalShownChanged: if(localShown) refresh()
    function ago(ms) { return Ui.ago(ms, root.now); }
    // A probe's services as card rows, the state spelled out.
    function serviceRows(m) {
        return (m && m.services || []).map(function(s){
            return {t: s.label, ok: s.running > 0,
                    state: s.units === 0 ? "not found" : s.units === 1 ? (s.running ? "running" : "stopped") : s.running + "/" + s.units + " running"};
        });
    }

    // ── Formatting ──────────────────────────────────────────────────────────
    function weatherIcon(code) {
        if(code===113) return "";
        if(code===116) return "";
        if(code===119 || code===122) return "";
        if([143,248,260].indexOf(code)!==-1) return "";
        if([200,386,389,392,395].indexOf(code)!==-1) return "";
        if([179,182,185,227,230,281,284,311,314,317,320,323,326,329,332,335,338,350,362,365,368,371,374,377].indexOf(code)!==-1) return "";
        if(code===176 || code===353) return "";
        return "";
    }
    // A temperature from the weather cache in the desk's units ("temp", "feels", "hi", "lo").
    function deg(o, key) {
        if (!o) return "—";
        var c = o[key + "C"], f = o[key];
        return (root.metric ? (c !== undefined ? c : Math.round((f - 32) * 5 / 9)) : f) + "°";
    }
    function wind(w) { return root.metric ? (w.windK !== undefined ? w.windK : Math.round(w.wind * 1.609)) + " km/h" : w.wind + " mph"; }
    // "07:27 AM" on today's date, as epoch ms.
    function clockTime(text) {
        var m=/(\d+):(\d+)\s*(AM|PM)/i.exec(text||""); if(!m) return NaN;
        var h=Number(m[1])%12 + (m[3].toUpperCase()==="PM"?12:0), d=new Date(root.now);
        return new Date(d.getFullYear(),d.getMonth(),d.getDate(),h,Number(m[2])).getTime();
    }
    function hm(ms, withAp) { return Qt.formatTime(new Date(ms), root.h12 ? (withAp ? "h:mm AP" : "h:mm") : "HH:mm"); }
    function sunTime(text, withAp) { var t = clockTime(text); return isFinite(t) ? hm(t, withAp) : ""; }
    function span(ms) { var m=Math.max(0,Math.round(ms/60000)); return Math.floor(m/60)+"h "+(m%60)+"m"; }

    // ── Dock: pinned apps, then the ones used recently ──────────────────────
    function launchApp(id) { if(id) Quickshell.execDetached(["uwsm-app","--","gtk-launch",id+".desktop"]); }
    function entry(id) { var e = id ? DesktopEntries.byId(id) : null; return e && !e.noDisplay ? e : null; }
    function icon(e) { var p=e && e.icon ? Quickshell.iconPath(e.icon, true) : ""; return p || Quickshell.iconPath("application-x-executable", true); }
    // The desktop entry behind a new window's class, only when the match is certain.
    function entryForClass(cls) {
        if (!cls || cls.indexOf("org.omarchy.omatiles") === 0) return null;
        var e = DesktopEntries.byId(cls) || DesktopEntries.byId(cls.toLowerCase());
        if (!e) {
            var h = DesktopEntries.heuristicLookup(cls), low = cls.toLowerCase();
            if (h && (h.startupClass === cls || h.id.toLowerCase() === low || h.id.toLowerCase().endsWith("." + low))) e = h;
        }
        return e && !e.noDisplay ? e : null;
    }
    Process { id: recentProc; onExited: recentFile.reload() }
    // Tile desktops are locked, like a phone's home screen: a tiled window that
    // opens on one moves to the first ordinary workspace, and the view follows it.
    // Floating pop-ups (volume, Wi-Fi…) may stay; they don't cover the tiles.
    property var opening: []
    function keepOff(address) {
        if (!config.desks || !/^(0x)?[0-9a-fA-F]+$/.test(address)) return;
        opening = opening.concat([address.replace(/^0x/, "")]);
        Hyprland.refreshToplevels();
        lockTimer.restart();
    }
    Timer {
        id: lockTimer; interval: 150
        onTriggered: {
            var list = root.opening; root.opening = [];
            Hyprland.toplevels.values.forEach(function(t) {
                var o = t.lastIpcObject, a = String(t.address).replace(/^0x/, "");
                if (list.indexOf(a) === -1 || !o || o.floating !== false || !o.workspace) return;
                if (o.workspace.id >= 1 && o.workspace.id <= root.pages)
                    Quickshell.execDetached(["hyprctl", "dispatch", "hl.dsp.window.move({ workspace = \"" + (root.pages + 1) + "\", window = \"address:0x" + a + "\" })"]);
            });
        }
    }
    function noteWindow(cls) {
        var e = entryForClass(cls);
        var list = Array.isArray(recentFile.value) ? recentFile.value : [];
        if (e && list[0] !== e.id) run(recentProc, ["recent", e.id]);
    }
    // App entries load after the desk does; reading the list here rebuilds the dock when they arrive.
    readonly property var pinnedApps: (themeSlug, DesktopEntries.applications.values, config.dock.map(entry).filter(function(e){ return !!e; }))
    readonly property var recentApps: {
        var pinned = config.dock, list = Array.isArray(recentFile.value) ? recentFile.value : [];
        return (themeSlug, DesktopEntries.applications.values, list.filter(function(id){ return pinned.indexOf(id) === -1; }).map(entry).filter(function(e){ return !!e; }));
    }
    property var dockPick: null
    Process { id: pinProc }
    function pin(id, on) { run(pinProc, [on ? "pin" : "unpin", id]); dockPick = null; }

    // ── Widgets from the store, and the ones Claude writes ──────────────────
    readonly property string widgetDir: home + "/.config/omarchy/omatiles/widgets/"
    readonly property string storeUrl: "https://simonschubert.github.io/omarchy-widgets/"
    readonly property var owlKeys: Object.keys(config.tiles).filter(function(k){ return k.indexOf("owl:")===0 && config.tiles[k].enabled; })
    property bool menuOpen: false
    property real menuX: 0
    property real menuY: 0
    property bool storeOpen: false
    property string storeCategory: "all"
    property string storeQuery: ""
    property var storePick: null
    property string storeMessage: ""
    property bool createOpen: false
    property var createResult: null
    // The OWL widget whose own screen (its settings or detail view) is open.
    property var screenWidget: null
    JsonFile { id: storeFile; path: root.cache + "store.json"; fallback: ({widgets: []}) }
    readonly property var storeWidgets: storeFile.value && storeFile.value.widgets || []
    Owl.OwlHost { id: owlHost; monoFamily: Style.font.family; iconFamily: Style.font.family }
    Process { id: storeFetch; property bool force: false; command: ["python3",root.backend,"store"].concat(force?["force"]:[]); onExited: { storeFile.reload(); compatFile.reload(); } }
    // Per widget: {phone: works only on the phone, missing: packages not installed here}.
    JsonFile { id: compatFile; path: root.cache + "compat.json"; fallback: ({}) }
    function compat(id) { return compatFile.value && compatFile.value[id] || {phone: false, missing: []}; }
    function compatLabel(id) { var c = compat(id); return c.phone ? "phone only" : c.missing.length ? "needs " + c.missing.join(", ") : ""; }
    Process {
        id: installProc
        stdout: StdioCollector { waitForEnd: true; onStreamFinished: { root.storeMessage = root.installMessage(text); try { if (JSON.parse(text).overlap) root.showStacked(); } catch(e) {} } }
    }
    Process { id: removeProc }
    Process {
        id: createProc
        stdout: StdioCollector { waitForEnd: true; onStreamFinished: { try { root.createResult = JSON.parse(text); } catch(e) { root.createResult = {ok:false, error:"Claude did not finish"}; } if (root.createResult.overlap) root.showStacked(); } }
    }
    function placedText(r) {
        return (r.overlap ? "No free spot, so it sits on top of the other tiles." : "Added to this desk.")
            + (r.shrunk ? " Sized " + r.w + "x" + r.h + " to fit." : "")
            + (r.missing && r.missing.length ? " It needs " + r.missing.join(", ") + ": run  omarchy pkg add " + r.missing.join(" ") : "");
    }
    function installMessage(text) {
        try {
            var r = JSON.parse(text);
            if (!r.ok) return "Not added: " + r.error;
            return placedText(r);
        } catch(e) { return "Not added."; }
    }
    // A tile landed on top of others: close the panel and open arrange mode on it.
    function showStacked() { storeOpen = false; createOpen = false; typing = false; editing = true; }
    readonly property bool stacked: Object.keys(config.tiles).some(function(k){ var t = config.tiles[k]; return t.top && t.enabled && (t.page || 1) === page; })
    function installed(id) { return !!root.config.tiles["owl:" + id]; }
    readonly property var storeCategories: {
        var counts = {}, out = [{name: "all", n: storeWidgets.length}];
        storeWidgets.forEach(function(w){ var c = w.category || "other"; counts[c] = (counts[c] || 0) + 1; });
        Object.keys(counts).sort().forEach(function(c){ out.push({name: c, n: counts[c]}); });
        return out;
    }
    // Widgets that only work on the phone go last.
    readonly property var storeShown: storeWidgets.filter(function(w){
        var q = storeQuery.trim().toLowerCase();
        return (storeCategory === "all" || (w.category || "other") === storeCategory)
            && (!q || (w.name + " " + w.description + " " + w.author).toLowerCase().indexOf(q) !== -1);
    }).map(function(w, i){ return {w: w, i: i, phone: root.compat(w.id).phone}; })
      .sort(function(a, b){ return a.phone - b.phone || a.i - b.i; }).map(function(x){ return x.w; })
    // Store previews exist for some themes; show this theme's, else the closest one's.
    readonly property string previewTheme: storeOpen ? themeSlug : ""
    function previewUrl(w) {
        var shots = w.themes || {}, rel = shots[root.themeSlug];
        if (!rel) { var near = Ui.nearestTheme(root.themeList, shots, Color.background, Color.accent); rel = near ? shots[near] : ""; }
        rel = rel || w.preview;
        return rel ? root.storeUrl + rel : "";
    }
    function openStore() { menuOpen = false; storeOpen = true; storeMessage = ""; loadThemes(); storeFetch.force = false; if(!storeFetch.running) storeFetch.running = true; }
    function openCreate() { menuOpen = false; createResult = null; createOpen = true; }
    readonly property var builtinNames: {
        var n = {clock: "clock", local: "this machine", remote: (config.remote.name || "remote machine"), calendar: "calendar", weather: "date + weather", sun: "sun & moon"};
        Config.AGENTS.forEach(function(a){ n["chat-" + a] = agentName(a) + " chat"; });
        return n;
    }
    function tileName(key) { return builtinNames[key] || key.replace(/^owl:[^/]+\//, "").replace(/-/g, " "); }

    // ── Undo for the last removal ───────────────────────────────────────────
    property string undoKey: ""
    // A delete waiting for its second click; it lapses after a few seconds.
    property string confirmKey: ""
    Timer { id: confirmTimer; interval: 4000; onTriggered: root.confirmKey = "" }
    Timer { id: undoTimer; interval: 10000; onTriggered: root.undoKey = "" }
    function removeTile(key) { if (run(removeProc, ["remove", key])) { undoKey = key; undoTimer.restart(); } }
    function undoRemove() { if (undoKey && run(removeProc, ["restore", undoKey])) { undoKey = ""; undoTimer.stop(); } }

    // ── Calendar (Google Calendar through gcal.py) ──────────────────────────
    property int selDay: new Date().getDate()
    property int openEvent: -1
    property bool adding: false
    property string addError: ""
    Process { id: calendarFetch; command: ["python3",root.gcal,"sync"]; onExited: { calendarFile.reload(); gcalStatusFile.reload(); } }
    Process { id: gcalAuth; command: ["python3",root.gcal,"auth"]; onExited: if(!calendarFetch.running) calendarFetch.running = true }
    Process { id: gcalRemind; command: ["python3",root.gcal,"remind"] }
    Process {
        id: gcalAdd
        stderr: StdioCollector { waitForEnd: true; onStreamFinished: root.addError=text.trim() ? "Could not save the event. Check the date (YYYY-MM-DD) and times (14:00)." : "" }
        onExited: function(exitCode) { if(exitCode===0) { root.adding=false; root.typing=false; if(!calendarFetch.running) calendarFetch.running=true; } }
    }
    function shiftMonth(delta) {
        var date=new Date(year,month+delta,1); year=date.getFullYear(); month=date.getMonth(); browsed=true; selDay=1; openEvent=-1;
    }
    function timeLabel(e) { return e.allDay ? "All day" : hm(e.time, true); }
    // Monday first, in the locale's narrow day names.
    readonly property var dayLetters: [1,2,3,4,5,6,0].map(function(d){ return Qt.locale().dayName(d, Locale.NarrowFormat); })

    Timer {
        interval: 1000; running: root.live; repeat: true; triggeredOnStart: true
        onTriggered: {
            root.now=Date.now();
            if(!root.browsed) {var d=new Date(root.now);root.year=d.getFullYear();root.month=d.getMonth();}
        }
    }
    Timer { interval: 300000; running: true; repeat: true; triggeredOnStart: true; onTriggered: if(!calendarFetch.running)calendarFetch.running=true }
    Timer { interval: 60000; running: true; repeat: true; onTriggered: { if(!gcalRemind.running)gcalRemind.running=true; root.refresh(); } }

    // ── Chat tiles, one per agent CLI ───────────────────────────────────────
    // Each runs here, or on chat.host over ssh. The backend keeps each thread
    // (session id) and transcript (chat/<agent>/log.json) that the tile shows.
    readonly property var defaultNames: ({claude: "Claude", codex: "Codex", grok: "Grok", hermes: "Hermes"})
    function agentName(a) { var o = config.chat.agents[a]; return o && o.name || defaultNames[a]; }
    readonly property string chatWhere: config.chat.host ? (config.chat.where || config.chat.host) : "this machine"
    function agentHere(a) { return config.chat.host !== "" || !agentsFile.value || agentsFile.value[a] !== false; }
    function proc(a) { return ({claude: askClaude, codex: askCodex, grok: askGrok, hermes: askHermes})[a] || null; }
    function send(agent, text) { var p = proc(agent); if (p && text.trim()) run(p, ["ask", agent, text.trim()]); }
    function retry(agent) { var p = proc(agent); if (p) run(p, ["ask", agent, "--retry"]); }
    function newChat(agent) { if (!proc(agent).running) run(newProc, ["new", agent]); }
    function openTerminal(agent) { run(openAgent, ["open", agent]); }
    // Bumped when a turn or a new chat finishes, so the tiles reread their transcripts.
    property int chatEpoch: 0
    Process { id: askClaude; onRunningChanged: root.chatEpoch++ }
    Process { id: askCodex; onRunningChanged: root.chatEpoch++ }
    Process { id: askGrok; onRunningChanged: root.chatEpoch++ }
    Process { id: askHermes; onRunningChanged: root.chatEpoch++ }
    Process { id: newProc; onExited: root.chatEpoch++ }
    Process { id: openAgent }

    // ── Keyboard mode ───────────────────────────────────────────────────────
    function pageTiles() {
        var t = config.tiles;
        return Object.keys(t).filter(function(k){ return t[k].enabled && (t[k].page || 1) === page; })
            .map(function(k){ return {key: k, col: t[k].col, row: t[k].row, w: t[k].w, h: t[k].h}; })
            .sort(function(a, b){ return a.row - b.row || a.col - b.col; });
    }
    function startFocus() {
        if (!shown) return;
        menuOpen = false; focusing = true;
        var list = pageTiles();
        if (!list.some(function(t){ return t.key === focusKey; })) focusKey = list.length ? list[0].key : "";
    }
    function stopFocus() { focusing = false; typing = false; focusKey = ""; }
    // The nearest tile in a direction, by tile centers.
    function step(dx, dy) {
        var list = pageTiles(), cur = list.filter(function(t){ return t.key === focusKey; })[0];
        if (!cur) { focusKey = list.length ? list[0].key : ""; return; }
        var cx = cur.col + cur.w / 2, cy = cur.row + cur.h / 2, best = null, score = 1e9;
        list.forEach(function(t){
            if (t.key === cur.key) return;
            var x = t.col + t.w / 2 - cx, y = t.row + t.h / 2 - cy;
            var along = dx ? x * dx : y * dy, across = dx ? Math.abs(y) : Math.abs(x);
            if (along <= 0) return;
            if (along + 2 * across < score) { score = along + 2 * across; best = t; }
        });
        if (best) focusKey = best.key;
    }
    function cycle(by) {
        var list = pageTiles(); if (!list.length) return;
        var i = list.map(function(t){ return t.key; }).indexOf(focusKey);
        focusKey = list[(i + by + list.length) % list.length].key;
    }

    // For keybindings: qs ipc -p /usr/share/omarchy/shell call omatiles <function>
    IpcHandler {
        target: "omatiles"
        function menu(): void { desk.openMenu(desk.width/2 - 190, desk.height/3); }
        function store(): void { root.openStore(); }
        function arrange(): void { root.menuOpen = false; root.editing = !root.editing; }
        function create(): void { root.openCreate(); }
        function focus(): void { if (root.focusing) root.stopFocus(); else root.startFocus(); }
        function close(): void {
            root.menuOpen = false; root.storeOpen = false; root.createOpen = false; root.editing = false; root.dockPick = null;
            root.stopFocus();
            if (root.screenWidget) root.screenWidget.closeScreen();
        }
    }

    PanelWindow {
        id: window
        screen: root.monitor
        visible: root.shown && root.loaded
        anchors { top: true; bottom: true; left: true; right: true }
        exclusionMode: ExclusionMode.Normal
        color: "transparent"
        // Keyboard mode lifts the desk above floating windows so it can take the keyboard.
        WlrLayershell.layer: root.focusing ? WlrLayer.Top : WlrLayer.Bottom
        WlrLayershell.namespace: "omatiles"
        WlrLayershell.keyboardFocus: root.focusing ? WlrKeyboardFocus.Exclusive : root.typing ? WlrKeyboardFocus.OnDemand : WlrKeyboardFocus.None

        Item {
            id: desk
            anchors.fill: parent
            focus: true
            property alias editing: root.editing
            property alias typing: root.typing
            readonly property int page: root.page
            readonly property int pages: root.pages
            readonly property color ink: root.ink
            readonly property color muted: root.muted
            readonly property color danger: root.danger
            readonly property string focusKey: root.focusing ? root.focusKey : ""
            readonly property bool focusing: root.focusing
            readonly property real margin: 10
            readonly property real gap: 8
            readonly property real dockH: 58
            readonly property real gridH: height - 2*margin - dockH - gap
            readonly property real cellW: (width - 2*margin - (Config.COLS-1)*gap) / Config.COLS
            readonly property real cellH: (gridH - (Config.ROWS-1)*gap) / Config.ROWS
            function cellX(c) { return margin + c*(cellW+gap); }
            function cellY(r) { return margin + r*(cellH+gap); }
            function spanWidth(n) { return n*cellW + (n-1)*gap; }
            function spanHeight(n) { return n*cellH + (n-1)*gap; }
            function colAt(px, w) { return Math.max(0, Math.min(Config.COLS-w, Math.round((px-margin)/(cellW+gap)))); }
            function rowAt(py, h) { return Math.max(0, Math.min(Config.ROWS-h, Math.round((py-margin)/(cellH+gap)))); }
            function spanAt(len, start, horizontal) {
                var cell=horizontal?cellW:cellH, max=(horizontal?Config.COLS:Config.ROWS)-start;
                return Math.max(1, Math.min(max, Math.round((len+gap)/(cell+gap))));
            }
            function openMenu(x, y) {
                root.menuX = x; root.menuY = y; root.menuOpen = true; root.dockPick = null;
                root.loadThemes();
                if (root.config.menuHint) root.setOption("menuHint", false);
            }
            function move(key, page) { root.run(removeProc, ["move", key, String(page)]); }
            function remove(key) { root.removeTile(key); }
            function place(key, g) { root.run(placeProc, ["place", key, JSON.stringify(g)]); }
            // Tiles by key, so keyboard mode can use the focused one.
            property var tileItems: ({})
            function registerTile(t) { tileItems[t.key] = t; }
            function unregisterTile(t) { if (tileItems[t.key] === t) delete tileItems[t.key]; }

            Connections {
                target: root
                function onFocusingChanged() { if (root.focusing) desk.forceActiveFocus(); }
            }
            Keys.onPressed: function(e) {
                if (!root.focusing) return;
                var k = e.key;
                if (k === Qt.Key_Escape) {
                    if (root.screenWidget) root.screenWidget.closeScreen();
                    else if (root.menuOpen || root.storeOpen || root.createOpen) { root.menuOpen = false; root.storeOpen = false; root.createOpen = false; }
                    else if (root.editing) root.editing = false;
                    else root.stopFocus();
                }
                else if (root.editing && root.focusKey && [Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down].indexOf(k) !== -1) {
                    // Arranging: arrows move the focused tile a cell, Shift+arrows resize it.
                    var dx = k === Qt.Key_Left ? -1 : k === Qt.Key_Right ? 1 : 0, dy = k === Qt.Key_Up ? -1 : k === Qt.Key_Down ? 1 : 0;
                    var t0 = root.config.tiles[root.focusKey], g = {col: t0.col, row: t0.row, w: t0.w, h: t0.h};
                    if (e.modifiers & Qt.ShiftModifier) { g.w = Math.max(1, Math.min(Config.COLS - g.col, g.w + dx)); g.h = Math.max(1, Math.min(Config.ROWS - g.row, g.h + dy)); }
                    else { g.col = Math.max(0, Math.min(Config.COLS - g.w, g.col + dx)); g.row = Math.max(0, Math.min(Config.ROWS - g.h, g.row + dy)); }
                    desk.place(root.focusKey, g);
                }
                else if (k === Qt.Key_Left) root.step(-1, 0);
                else if (k === Qt.Key_Right) root.step(1, 0);
                else if (k === Qt.Key_Up) root.step(0, -1);
                else if (k === Qt.Key_Down) root.step(0, 1);
                else if (k === Qt.Key_Tab) root.cycle(1);
                else if (k === Qt.Key_Backtab) root.cycle(-1);
                else if (k === Qt.Key_Return || k === Qt.Key_Enter || k === Qt.Key_Space) { var t = tileItems[root.focusKey]; if (t) t.activated(); }
                else if (k === Qt.Key_M) desk.openMenu(desk.width/2 - 190, desk.height/3);
                else if (k === Qt.Key_S) root.openStore();
                else if (k === Qt.Key_A) root.editing = !root.editing;
                else return;
                e.accepted = true;
            }

            // Clicking empty desk drops keyboard focus; right-click opens the menu.
            MouseArea {
                anchors.fill: parent
                acceptedButtons: Qt.LeftButton | Qt.RightButton
                onClicked: function(m) {
                    if(m.button===Qt.RightButton) desk.openMenu(m.x, m.y);
                    else { root.typing=false; root.menuOpen=false; root.dockPick=null; if(root.editing) root.editing=false; }
                }
            }
            // Grid cells, shown while arranging.
            Repeater {
                model: root.editing ? Config.COLS*Config.ROWS : 0
                Rectangle {
                    required property int index
                    x: desk.cellX(index%Config.COLS); y: desk.cellY(Math.floor(index/Config.COLS))
                    width: desk.cellW; height: desk.cellH; radius: Style.cornerRadius
                    color: "transparent"; border.width: 1; border.color: Util.alpha(root.ink, 0.25)
                }
            }

            // ── Clock ───────────────────────────────────────────────────────
            Tile {
                id: clockTile; desk: desk; key: "clock"; place: root.config.tiles.clock
                readonly property string hms: Qt.formatTime(new Date(root.now), root.h12 ? "h:mm:ss" : "HH:mm:ss")
                readonly property real units: hms.length*0.1 + hms.replace(/:/g,"").length*0.55 + (hms.split(":").length-1)*0.2
                Column {
                    anchors.centerIn: parent; width: parent.width; spacing: Style.spacing.md
                    Row {
                        anchors.horizontalCenter: parent.horizontalCenter; spacing: Style.spacing.sm; bottomPadding: Style.spacing.lg
                        SevenSeg { color: root.ink; text: clockTile.hms; digitHeight: Math.min(clockTile.body.height*0.32, (clockTile.body.width-28)/clockTile.units) }
                        Text { visible: root.h12; text: Qt.formatTime(new Date(root.now), "AP"); color: root.ink; font.family: Style.font.family; font.pixelSize: Style.font.body }
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: (Qt.formatDate(new Date(root.now), "ddd") + " · " + Qt.formatDate(new Date(root.now), root.monthDay)).toUpperCase()
                        color: root.ink; font.family: Style.font.family; font.pixelSize: Style.font.heading; font.letterSpacing: 1
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        // The weather tile says this already when it is on the same desk.
                        visible: !!root.weather && !root.onPage("weather")
                        text: root.weather ? (root.deg(root.weather, "temp") + (root.metric ? "C " : "F ") + root.weather.desc + " · " + root.wind(root.weather)).toUpperCase() : ""
                        color: Util.alpha(root.ink, 0.85); font.family: Style.font.family; font.pixelSize: Style.font.body
                        width: Math.min(implicitWidth, clockTile.body.width); elide: Text.ElideRight
                    }
                }
            }

            // ── This machine and a remote one, fastfetch style ──────────────
            Tile {
                id: localTile; desk: desk; key: "local"; place: root.config.tiles.local
                readonly property var m: root.local
                readonly property bool live: !!m && m.ok && root.now-m.updatedAt < 180000
                readonly property var bat: m ? m.battery : null
                onActivated: Quickshell.execDetached(["omarchy-launch-or-focus-tui","btop"])
                SysInfo {
                    machine: localTile.m; user: localTile.m && localTile.m.who ? localTile.m.who : "this machine"
                    waiting: "Reading this machine…"; live: localTile.live; ink: root.ink; muted: root.muted; danger: root.danger
                    services: root.serviceRows(localTile.m)
                        .concat(localTile.m && localTile.m.tailscale !== null && localTile.m.tailscale !== undefined
                                ? [{t: "Tailscale", ok: !!localTile.m.tailscale, state: localTile.m.tailscale || "down"}] : [])
                        .concat(localTile.bat ? [{t: "Battery", ok: localTile.bat.level > 20 || localTile.bat.status !== "Discharging",
                                                  state: localTile.bat.level + "% " + localTile.bat.status.toLowerCase()}] : [])
                    status: !localTile.m ? "" : localTile.live ? "updated " + root.ago(localTile.m.updatedAt) : "not updated since " + root.ago(localTile.m.updatedAt)
                    button: "Open btop"
                    onClicked: Quickshell.execDetached(["omarchy-launch-or-focus-tui","btop"])
                }
            }
            Tile {
                id: remoteTile; desk: desk; key: "remote"; place: root.config.tiles.remote
                readonly property var r: root.config.remote
                readonly property var m: root.remote
                readonly property string label: r.name || r.host.replace(/^.*@/, "")
                readonly property bool live: !!m && m.ok
                onActivated: if (r.host) root.refreshRemote()
                SysInfo {
                    visible: remoteTile.r.host !== ""
                    machine: remoteTile.m; user: remoteTile.m && remoteTile.m.who ? remoteTile.m.who : remoteTile.label
                    waiting: remoteFetch.running ? "Checking " + remoteTile.label + "…" : "Not checked yet. Refresh reads " + remoteTile.label + " once over ssh."
                    live: remoteTile.live || remoteFetch.running; ink: root.ink; muted: root.muted; danger: root.danger
                    services: root.serviceRows(remoteTile.m)
                    status: remoteFetch.running ? "checking " + remoteTile.label + "…" : !remoteTile.m ? ""
                          : remoteTile.live ? "checked " + root.ago(remoteTile.m.updatedAt)
                          : "couldn't reach " + remoteTile.label + (remoteTile.m.seenAt ? " · last seen " + root.ago(remoteTile.m.seenAt) : "")
                    refreshable: !remoteFetch.running; onRefresh: root.refreshRemote()
                    button: remoteTile.r.link.url ? (remoteTile.r.link.label || "Open") : ""
                    onClicked: Quickshell.execDetached(["omarchy-launch-webapp", remoteTile.r.link.url])
                }
                // Not set up yet: say how.
                Column {
                    visible: remoteTile.r.host === ""; width: parent.width; spacing: Style.spacing.lg
                    Text { text: "remote machine"; color: root.ink; font.family: Style.font.family; font.pixelSize: Style.font.heading }
                    Label {
                        color: root.muted; font.pixelSize: Style.font.body
                        text: "Shows another machine's facts and services, read over ssh only when you press refresh. Add to ~/.config/omarchy/omatiles.json:"
                    }
                    Rectangle {
                        width: parent.width; height: example.implicitHeight + 2*Style.spacing.lg; radius: Style.cornerRadius; color: Util.alpha(Color.foreground, 0.05)
                        Text {
                            id: example; x: Style.spacing.lg; y: Style.spacing.lg; width: parent.width - 2*Style.spacing.lg; wrapMode: Text.WrapAnywhere
                            text: '"remote": {"host": "me@server", "name": "server",\n  "services": [{"label": "Web", "unit": "nginx.service", "user": false}]}'
                            color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body
                        }
                    }
                }
            }

            // ── Calendar ────────────────────────────────────────────────────
            Tile {
                id: calTile; desk: desk; key: "calendar"; place: root.config.tiles.calendar
                readonly property real dayH: Math.max(16, Math.min(28, (body.height - 120) / 6))
                onActivated: if (root.gcalState === "ok") addLink.start(); else if (root.gcalState !== "noclient" && !gcalAuth.running) gcalAuth.running = true
                Column {
                    id: calHead; width: parent.width; spacing: Style.spacing.sm
                    Row {
                        width: parent.width; spacing: Style.spacing.sm
                        component Glyph: Text {
                            signal hit()
                            width: 24; height: 24; verticalAlignment: Text.AlignVCenter; horizontalAlignment: Text.AlignHCenter
                            Accessible.role: Accessible.Button
                            color: root.ink; font.family: Style.font.family; font.pixelSize: Style.font.body
                            MouseArea { anchors.fill: parent; anchors.margins: -4; cursorShape: Qt.PointingHandCursor; onClicked: parent.hit() }
                        }
                        Glyph { text: ""; onHit: root.shiftMonth(-1) }
                        Text { width: parent.width-84; height: 24; elide: Text.ElideRight; verticalAlignment: Text.AlignVCenter; text: new Date(root.year,root.month,1).toLocaleDateString(Qt.locale(), "MMMM yyyy"); color: root.ink; font.family: Style.font.family; font.pixelSize: Style.font.title }
                        Glyph { text: ""; onHit: root.shiftMonth(1) }
                        Glyph {
                            id: addLink; visible: root.gcalState==="ok"; text: root.adding ? "" : ""
                            function start() {
                                evTitle.text=""; evStart.text=""; evEnd.text=""; evDate.text=Qt.formatDate(new Date(root.year,root.month,root.selDay),"yyyy-MM-dd");
                                root.addError=""; root.adding=true; evTitle.focusIn();
                            }
                            onHit: { if(root.adding){ root.adding=false; root.typing=false; } else start(); }
                        }
                    }
                    Grid {
                        width: parent.width; columns: 7
                        Repeater {
                            model: root.dayLetters
                            Text { required property string modelData; width: parent.width/7; height: 18; text: modelData; color: root.muted; font.family: Style.font.family; font.pixelSize: Style.font.body; horizontalAlignment: Text.AlignHCenter }
                        }
                        Repeater {
                            model: Calendar.grid(root.year,root.month)
                            Rectangle {
                                required property int modelData
                                width: parent.width/7; height: calTile.dayH; radius: Style.cornerRadius
                                readonly property bool today: modelData>0 && modelData===new Date(root.now).getDate() && root.month===new Date(root.now).getMonth() && root.year===new Date(root.now).getFullYear()
                                readonly property bool selected: modelData>0 && modelData===root.selDay
                                color: today ? root.ink : selected ? Util.alpha(root.ink, 0.22) : (dayMouse.containsMouse && modelData>0 ? Util.alpha(root.ink, 0.1) : "transparent")
                                Text { anchors.centerIn: parent; text: modelData || ""; font.family: Style.font.family; font.pixelSize: Style.font.body; color: parent.today ? Color.background : Color.foreground }
                                Rectangle { width: 3; height: 3; radius: 2; color: parent.today ? Color.background : root.ink; anchors.bottom: parent.bottom; anchors.bottomMargin: 1; anchors.horizontalCenter: parent.horizontalCenter; visible: modelData>0 && Calendar.onDay(root.events,root.year,root.month,modelData) }
                                MouseArea { id: dayMouse; anchors.fill: parent; hoverEnabled: true; enabled: modelData>0; cursorShape: Qt.PointingHandCursor; onClicked: { root.selDay=modelData; root.openEvent=-1; root.adding=false; } }
                            }
                        }
                    }
                }
                Flickable {
                    anchors { top: calHead.bottom; topMargin: Style.spacing.xxxl; left: parent.left; right: parent.right; bottom: parent.bottom }
                    contentWidth: width; contentHeight: calList.implicitHeight; clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    Column {
                        id: calList; width: parent.width; spacing: Style.spacing.md
                        // Google Calendar needs the user's own OAuth client first.
                        Column {
                            visible: root.gcalState === "noclient"; width: parent.width; spacing: Style.spacing.md
                            Label { color: root.muted; font.pixelSize: Style.font.body; text: "To show your Google Calendar, save a Google OAuth client (Desktop app) as ~/.config/omarchy/omatiles/google_client.json, then connect." }
                            Action { text: "How to get one"; onClicked: root.openLink(root.readme) }
                        }
                        Action {
                            visible: root.gcalState==="disconnected" || root.gcalState==="reconnect"
                            text: gcalAuth.running ? "Finish signing in in your browser…" : root.gcalState==="reconnect" ? "Reconnect Google Calendar" : "Connect Google Calendar"
                            onClicked: if(!gcalAuth.running)gcalAuth.running=true
                        }
                        Column {
                            visible: root.gcalState === "error"; width: parent.width; spacing: Style.spacing.sm
                            Label { color: root.danger; font.pixelSize: Style.font.body; text: "Couldn't load the calendar" + (gcalStatusFile.value && gcalStatusFile.value.message ? " (" + gcalStatusFile.value.message + ")" : "") + "." }
                            Action { text: calendarFetch.running ? "Trying…" : "Try again"; onClicked: if(!calendarFetch.running) calendarFetch.running = true }
                        }
                        Column {
                            visible: root.adding; width: parent.width; spacing: Style.spacing.md
                            Field { id: evTitle; desk: desk; placeholder: "Title"; onAccepted: root.saveEvent() }
                            Field { id: evDate; desk: desk; placeholder: "Date (YYYY-MM-DD)"; onAccepted: root.saveEvent() }
                            Row {
                                width: parent.width; spacing: Style.spacing.md
                                Field { id: evStart; width: (parent.width-Style.spacing.md)/2; desk: desk; placeholder: "Start 14:00"; onAccepted: root.saveEvent() }
                                Field { id: evEnd; width: (parent.width-Style.spacing.md)/2; desk: desk; placeholder: "End 15:00"; onAccepted: root.saveEvent() }
                            }
                            Action { text: gcalAdd.running ? "Saving…" : "Save to Google Calendar"; enabled: evTitle.text.trim() !== ""; onClicked: root.saveEvent() }
                            Label { visible: root.addError!==""; text: root.addError; color: root.danger; font.pixelSize: Style.font.body }
                        }
                        Label { visible: !root.adding; text: new Date(root.year,root.month,root.selDay).toLocaleDateString(Qt.locale(),"dddd, MMM d"); color: root.ink; font.pixelSize: Style.font.body }
                        Repeater {
                            model: root.adding ? [] : Calendar.dayEvents(root.events,root.year,root.month,root.selDay).slice(0,8)
                            Column {
                                required property var modelData
                                required property int index
                                width: parent.width; spacing: Style.spacing.xs
                                Row {
                                    width: parent.width; spacing: Style.spacing.md
                                    Rectangle { width: 6; height: 6; y: 5; radius: 3; color: modelData.color }
                                    Label {
                                        width: parent.width-12; font.pixelSize: Style.font.body; text: root.timeLabel(modelData) + " · " + modelData.summary
                                        MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: root.openEvent = root.openEvent===index ? -1 : index }
                                    }
                                }
                                Column {
                                    visible: root.openEvent===index; width: parent.width; spacing: Style.spacing.xs; leftPadding: Style.spacing.xxl
                                    Label { width: parent.width-12; color: root.muted; font.pixelSize: Style.font.body; text: modelData.calendar + (modelData.allDay ? "" : " · " + root.hm(modelData.time, true) + " – " + root.hm(modelData.end, true)) }
                                    Label { visible: modelData.location!==""; width: parent.width-12; font.pixelSize: Style.font.body; text: "  " + modelData.location }
                                    Label { visible: modelData.description!==""; width: parent.width-12; font.pixelSize: Style.font.body; color: root.muted; textFormat: Text.PlainText; maximumLineCount: 4; elide: Text.ElideRight; text: modelData.description.replace(/<[^>]+>/g," ").replace(/&nbsp;/g," ").replace(/\s+/g," ").trim() }
                                    Action { width: parent.width-12; visible: modelData.link!==""; text: "Open in Google Calendar"; onClicked: root.openLink(modelData.link) }
                                }
                            }
                        }
                        Label {
                            visible: !root.adding && root.gcalState==="ok" && Calendar.dayEvents(root.events,root.year,root.month,root.selDay).length===0
                            text: "Nothing scheduled"; color: root.muted; font.pixelSize: Style.font.body
                        }
                    }
                }
            }

            // ── Date + weather + forecast ───────────────────────────────────
            Tile {
                id: wxTile; desk: desk; key: "weather"; place: root.config.tiles.weather
                readonly property var w: root.weather
                onActivated: Quickshell.execDetached(["omarchy-launch-webapp", "https://wttr.in/" + (w ? encodeURIComponent(w.location) : "")])
                Column {
                    anchors.fill: parent; spacing: Style.spacing.xxl
                    Row {
                        spacing: Style.spacing.xxxl
                        Text { text: new Date(root.now).getDate(); color: Color.foreground; font.family: Style.font.family; font.pixelSize: 46; font.weight: Font.Light }
                        Column {
                            y: 10; spacing: Style.spacing.xxs
                            Text { text: Qt.formatDate(new Date(root.now),"dddd").toLowerCase(); color: root.ink; font.family: Style.font.family; font.pixelSize: Style.font.heading }
                            Text { text: Qt.formatDate(new Date(root.now),"MMMM yyyy").toLowerCase(); color: root.muted; font.family: Style.font.family; font.pixelSize: Style.font.subtitle }
                        }
                    }
                    Rectangle { width: parent.width; height: 1; color: Util.alpha(Color.foreground, 0.1) }
                    Column {
                        width: parent.width; spacing: 0
                        Item {
                            width: parent.width; height: 50
                            Row {
                                spacing: Style.spacing.xl
                                Text { text: wxTile.w ? root.weatherIcon(wxTile.w.code) : ""; color: Color.foreground; font.family: Style.font.family; font.pixelSize: 26; y: 8 }
                                Text { text: root.deg(wxTile.w, "temp"); color: Color.foreground; font.family: Style.font.family; font.pixelSize: 36 }
                            }
                            Column {
                                anchors.right: parent.right; y: 6; spacing: Style.spacing.xxs; width: parent.width * 0.45
                                Text { anchors.right: parent.right; width: Math.min(implicitWidth, parent.width); elide: Text.ElideRight; text: wxTile.w ? wxTile.w.desc.toLowerCase() : ""; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.subtitle }
                                Text { anchors.right: parent.right; text: wxTile.w && wxTile.w.days.length ? "↑" + root.deg(wxTile.w.days[0], "hi") + "  ↓" + root.deg(wxTile.w.days[0], "lo") : ""; color: root.muted; font.family: Style.font.family; font.pixelSize: Style.font.body }
                            }
                        }
                        Text {
                            width: parent.width; elide: Text.ElideRight
                            text: wxTile.w ? "feels " + root.deg(wxTile.w, "feels") + " · " + wxTile.w.location
                                : weatherFetch.running ? "loading weather…" : "No weather yet. It comes from wttr.in for Omarchy's weather location."
                            color: root.muted; font.family: Style.font.family; font.pixelSize: Style.font.body
                        }
                    }
                    Rectangle { width: parent.width; height: 1; color: Util.alpha(Color.foreground, 0.1) }
                    Row {
                        width: parent.width
                        Repeater {
                            model: wxTile.w ? wxTile.w.days.slice(1,3) : []
                            Column {
                                required property var modelData
                                width: parent.width/3; spacing: Style.spacing.xxs
                                Text { anchors.horizontalCenter: parent.horizontalCenter; text: Qt.formatDate(new Date(modelData.date+"T12:00:00"),"ddd").toLowerCase(); color: root.muted; font.family: Style.font.family; font.pixelSize: Style.font.body }
                                Text { anchors.horizontalCenter: parent.horizontalCenter; text: root.weatherIcon(modelData.code); color: Color.foreground; font.family: Style.font.family; font.pixelSize: 18 }
                                Text { anchors.horizontalCenter: parent.horizontalCenter; text: root.deg(modelData, "hi") + " " + root.deg(modelData, "lo"); color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body }
                            }
                        }
                        Column {
                            visible: !!wxTile.w && wxTile.w.days.length > 0
                            width: parent.width/3; spacing: Style.spacing.md; topPadding: Style.spacing.md
                            Row { spacing: Style.spacing.lg; Text { text: ""; color: root.ink; font.family: Style.font.family; font.pixelSize: 15 } Text { text: wxTile.w && wxTile.w.days.length ? root.sunTime(wxTile.w.days[0].sunrise, false) : ""; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body } }
                            Row { spacing: Style.spacing.lg; Text { text: ""; color: root.ink; font.family: Style.font.family; font.pixelSize: 15 } Text { text: wxTile.w && wxTile.w.days.length ? root.sunTime(wxTile.w.days[0].sunset, false) : ""; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body } }
                        }
                    }
                }
            }

            // ── Sun & moon ──────────────────────────────────────────────────
            Tile {
                id: sunTile; desk: desk; key: "sun"; place: root.config.tiles.sun
                readonly property var today: root.weather && root.weather.days.length ? root.weather.days[0] : null
                readonly property double rise: today ? root.clockTime(today.sunrise) : NaN
                readonly property double set: today ? root.clockTime(today.sunset) : NaN
                readonly property real progress: isFinite(rise) && isFinite(set) ? (root.now-rise)/(set-rise) : -1
                Text { text: "sun & moon"; color: root.muted; font.family: Style.font.family; font.pixelSize: Style.font.title }
                Text { anchors.right: parent.right; width: Math.min(implicitWidth, parent.width / 2); elide: Text.ElideRight; text: root.weather ? root.weather.location : ""; color: root.muted; font.family: Style.font.family; font.pixelSize: Style.font.body }
                Text { visible: !sunTile.today; anchors.centerIn: parent; text: "waiting for the weather…"; color: root.muted; font.family: Style.font.family; font.pixelSize: Style.font.body }
                Canvas {
                    id: arc
                    visible: !!sunTile.today
                    anchors { left: parent.left; right: parent.right; top: parent.top; topMargin: 26; bottom: sunFoot.top; bottomMargin: Style.spacing.md }
                    property real p: sunTile.progress
                    property color lit: root.ink
                    property color dim: Util.alpha(Color.foreground, 0.25)
                    onPChanged: requestPaint()
                    onLitChanged: requestPaint()
                    onWidthChanged: requestPaint()
                    onHeightChanged: requestPaint()
                    onPaint: {
                        var ctx=getContext("2d"); ctx.reset();
                        var r=Math.max(1, Math.min(width*0.42, height-6)), cx=width/2, cy=height-1;
                        ctx.lineWidth=1; ctx.strokeStyle=dim;
                        ctx.beginPath(); ctx.moveTo(4,cy); ctx.lineTo(width-4,cy); ctx.stroke();
                        ctx.lineWidth=3;
                        ctx.beginPath(); ctx.arc(cx,cy,r,Math.PI,2*Math.PI,false); ctx.stroke();
                        if(p<0 || p>1) return;
                        var a=Math.PI+p*Math.PI;
                        ctx.strokeStyle=lit; ctx.beginPath(); ctx.arc(cx,cy,r,Math.PI,a,false); ctx.stroke();
                        ctx.fillStyle=lit; ctx.beginPath(); ctx.arc(cx+r*Math.cos(a),cy+r*Math.sin(a),8,0,2*Math.PI); ctx.fill();
                    }
                }
                Column {
                    id: sunFoot; visible: !!sunTile.today
                    anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
                    spacing: Style.spacing.md
                    Item {
                        width: parent.width; height: 18
                        Text { text: sunTile.today ? "↑ " + root.sunTime(sunTile.today.sunrise, false) : ""; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.title }
                        Text { anchors.right: parent.right; text: sunTile.today ? "↓ " + root.sunTime(sunTile.today.sunset, false) : ""; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.title }
                    }
                    Text {
                        color: root.muted; font.family: Style.font.family; font.pixelSize: Style.font.body
                        text: sunTile.progress<0 ? "" : sunTile.progress>1 ? "sun has set · up at " + root.sunTime(sunTile.today.sunrise, true).toLowerCase()
                              : sunTile.progress<0.0001 ? "" : root.span(sunTile.set-root.now) + " of daylight left"
                    }
                    Row {
                        spacing: Style.spacing.xl
                        Canvas {
                            id: moon; width: 22; height: 22
                            property real k: sunTile.today ? sunTile.today.moonIllum/100 : 0
                            property bool waning: sunTile.today ? /waning|last/i.test(sunTile.today.moonPhase) : false
                            property color lit: Color.foreground
                            property color dark: Util.alpha(Color.foreground, 0.15)
                            onKChanged: requestPaint()
                            onLitChanged: requestPaint()
                            onWaningChanged: requestPaint()
                            onPaint: {
                                var ctx=getContext("2d"), r=width/2-1; ctx.reset(); ctx.translate(width/2,height/2);
                                ctx.fillStyle=dark; ctx.beginPath(); ctx.arc(0,0,r,0,2*Math.PI); ctx.fill();
                                if(waning) ctx.scale(-1,1);
                                // Lit limb on the right, closed by the terminator ellipse.
                                ctx.fillStyle=lit; ctx.beginPath(); ctx.arc(0,0,r,-Math.PI/2,Math.PI/2,false);
                                ctx.save(); ctx.scale(Math.max(0.001,Math.abs(1-2*k)),1);
                                ctx.arc(0,0,r,Math.PI/2,-Math.PI/2,k<0.5); ctx.restore(); ctx.fill();
                            }
                        }
                        Text { y: 2; text: sunTile.today ? sunTile.today.moonPhase.toLowerCase() + " · " + sunTile.today.moonIllum + "%" : ""; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.subtitle }
                    }
                }
            }

            // ── Chat tiles, one per agent CLI ───────────────────────────────
            Repeater {
                model: Config.AGENTS
                Tile {
                    id: chatTile
                    required property string modelData
                    desk: deskItem; key: "chat-" + modelData; place: root.config.tiles["chat-" + modelData]
                    onActivated: chatView.focusInput()
                    ChatTile {
                        id: chatView
                        agent: chatTile.modelData; name: root.agentName(chatTile.modelData); where: root.chatWhere
                        available: root.agentHere(chatTile.modelData); readOnly: chatTile.modelData !== "hermes"
                        busy: root.proc(chatTile.modelData).running; epoch: root.chatEpoch; now: root.now; desk: deskItem; ink: root.ink; muted: root.muted; danger: root.danger
                        onSend: function(text) { root.send(chatTile.modelData, text); }
                        onRetry: root.retry(chatTile.modelData)
                        onFresh: root.newChat(chatTile.modelData)
                        onTerminal: root.openTerminal(chatTile.modelData)
                        onLink: function(url) { root.openLink(url); }
                    }
                }
            }

            // ── Store and Claude-made widgets ───────────────────────────────
            Repeater {
                model: root.owlKeys
                Tile {
                    id: owlTile
                    required property string modelData
                    // `desk: desk` would bind the tile's own property to itself here.
                    desk: deskItem; key: modelData; place: root.config.tiles[modelData]; padded: false
                    onActivated: {
                        if (ow.hasScreen) ow.openScreen();
                        else if (ow.tree && ow.tree.onTap) ow.tree.onTap(ow.width / 2 / ow.dp, ow.height / 2 / ow.dp);
                    }
                    Owl.OwlWidget {
                        id: ow
                        anchors.fill: parent
                        anchors.margins: (ow.program ? ow.program.padding : 12) * ow.dp
                        path: root.widgetDir + owlTile.key.slice(4) + "/widget.owl"
                        host: owlHost; palette: root.owlPalette; active: root.live && owlTile.visible; maxFps: 30
                        cols: owlTile.spanW; rows: owlTile.spanH
                        dp: Math.min(desk.cellW, desk.cellH) / 69
                        screenWidth: screenCard.width - 40; screenHeight: screenCard.height - 80
                        // Tapping most store widgets opens their own screen, as on the tablet.
                        onScreenRequested: { root.screenWidget = ow; root.typing = true; }
                        onScreenClosed: if (root.screenWidget === ow) { root.screenWidget = null; root.typing = false; }
                    }
                    TapHandler {
                        enabled: !root.editing && !!(ow.tree && ow.tree.onTap)
                        onTapped: (p) => ow.tree.onTap(p.position.x / ow.dp, p.position.y / ow.dp)
                    }
                    Owl.OwlNode {
                        anchors.fill: ow
                        visible: !ow.error && !!ow.tree
                        widget: ow
                        node: !ow.tree ? null : ow.tree.children.length === 1 ? ow.tree.children[0]
                            : { kind: "Column", p: { gap: 0 }, h: {}, a: {}, c: ow.tree.children }
                    }
                    Text {
                        anchors.centerIn: parent; visible: !ow.error && !ow.tree
                        text: root.tileName(owlTile.key) + " · loading…"; color: root.muted; font.family: Style.font.family; font.pixelSize: Style.font.body
                    }
                    Column {
                        anchors.fill: ow; visible: !!ow.error; spacing: Style.spacing.sm; clip: true
                        Text { width: parent.width; wrapMode: Text.Wrap; text: root.tileName(owlTile.key) + " didn't load. Arrange tiles to remove it, or reinstall it from the store."; color: root.danger; font.family: Style.font.family; font.pixelSize: Style.font.body }
                        Text { width: parent.width; wrapMode: Text.WrapAnywhere; maximumLineCount: 4; elide: Text.ElideRight; text: ow.error || ""; color: root.muted; font.family: Style.font.family; font.pixelSize: Style.font.body }
                    }
                }
            }

            // ── Hints: first run, arranging, undo ───────────────────────────
            component Chip: Rectangle {
                id: chip
                default property alias content: chipRow.data
                z: 44; height: Style.spacing.controlHeight + 8; width: chipRow.implicitWidth + 2*Style.spacing.xxxl; radius: Style.cornerRadius
                color: Color.background; border.width: 1; border.color: Util.alpha(root.ink, 0.6)
                MouseArea { anchors.fill: parent; acceptedButtons: Qt.LeftButton | Qt.RightButton }
                Row { id: chipRow; anchors.centerIn: parent; spacing: Style.spacing.xxl }
            }
            component ChipText: Text { anchors.verticalCenter: parent ? parent.verticalCenter : undefined; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body }
            component ChipLink: Text {
                signal hit()
                anchors.verticalCenter: parent ? parent.verticalCenter : undefined
                color: chipMouse.containsMouse ? Color.foreground : root.ink; font.family: Style.font.family; font.pixelSize: Style.font.body
                MouseArea { id: chipMouse; anchors.fill: parent; anchors.margins: -6; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: parent.hit() }
            }
            Chip {
                visible: root.config.menuHint && !root.choosing && !root.editing && !root.menuOpen && !root.storeOpen && !root.createOpen && root.undoKey === ""
                anchors { horizontalCenter: parent.horizontalCenter; bottom: dock.top; bottomMargin: desk.gap * 2 }
                ChipText { text: "Right-click the desk for widgets, themes and arranging" }
                ChipLink { text: ""; onHit: root.setOption("menuHint", false) }
            }
            Chip {
                visible: root.editing && !root.menuOpen && !root.storeOpen
                anchors { horizontalCenter: parent.horizontalCenter; bottom: dock.top; bottomMargin: desk.gap * 2 }
                ChipText { text: root.stacked ? "The new tile sits on top: drag it into place, or remove a tile you don't need" : (root.focusing ? "Arrows move the tile · Shift+arrows resize · " : "Drag to move · corner to resize · ") + (root.pages > 1 ? "  N moves it to desk N · " : "") + " remove" }
                ChipLink { text: "done"; onHit: root.editing = false }
            }
            Chip {
                z: 49
                visible: root.undoKey !== "" && !root.editing
                anchors { horizontalCenter: parent.horizontalCenter; bottom: dock.top; bottomMargin: desk.gap * 2 }
                ChipText { text: "Removed " + root.tileName(root.undoKey) }
                ChipLink { text: "undo"; onHit: root.undoRemove() }
            }
            Chip {
                visible: root.editing && root.undoKey !== ""
                anchors { horizontalCenter: parent.horizontalCenter; top: parent.top; topMargin: desk.margin + desk.gap }
                ChipText { text: "Removed " + root.tileName(root.undoKey) }
                ChipLink { text: "undo"; onHit: root.undoRemove() }
            }
            Chip {
                visible: root.focusing && !root.typing && !root.editing
                anchors { horizontalCenter: parent.horizontalCenter; bottom: dock.top; bottomMargin: desk.gap * 2 }
                ChipText { text: "Arrows pick a tile · Enter uses it · M menu · S store · A arrange · Esc leaves" }
            }

            // ── Right-click menu (the tablet's long-press menu) ─────────────
            Rectangle {
                id: menu
                z: 50
                opacity: root.menuOpen ? 1 : 0; visible: opacity > 0
                Behavior on opacity { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }
                width: 380; height: menuCol.implicitHeight + 28
                x: Math.max(desk.margin, Math.min(root.menuX, desk.width - width - 10)); y: Math.max(desk.margin, Math.min(root.menuY, desk.height - height - 10))
                color: Color.background; border.width: 2; border.color: root.ink; radius: Style.cornerRadius
                MouseArea { anchors.fill: parent; acceptedButtons: Qt.LeftButton | Qt.RightButton }
                Column {
                    id: menuCol; x: 16; y: 14; width: parent.width - 32; spacing: Style.spacing.sm
                    Repeater {
                        model: [{t: root.editing ? "done arranging" : "arrange tiles", a: "arrange"},
                                {t: "widget store", a: "store"}, {t: "new widget with claude", a: "create"},
                                {t: root.config.dockMono ? "use full-color dock icons" : "use symbol dock icons", a: "mono"}]
                        Rectangle {
                            required property var modelData
                            width: parent.width; height: 34; radius: Style.cornerRadius
                            color: itemMouse.containsMouse ? Util.alpha(root.ink, 0.14) : "transparent"
                            Text { x: 8; anchors.verticalCenter: parent.verticalCenter; text: modelData.t; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.heading - 1 }
                            MouseArea {
                                id: itemMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    root.menuOpen = false;
                                    if (modelData.a === "arrange") root.editing = !root.editing;
                                    else if (modelData.a === "store") root.openStore();
                                    else if (modelData.a === "mono") root.setOption("dockMono", !root.config.dockMono);
                                    else root.openCreate();
                                }
                            }
                        }
                    }
                    Item {
                        width: parent.width; height: 34
                        Text { x: 8; anchors.verticalCenter: parent.verticalCenter; text: "tile desktops"; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.heading - 1 }
                        Row {
                            anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                            spacing: Style.spacing.sm
                            Repeater {
                                model: [1, 2, 3]
                                Rectangle {
                                    required property int modelData
                                    readonly property bool on: modelData === root.pages
                                    Accessible.role: Accessible.RadioButton; Accessible.name: "tiles on " + (modelData === 1 ? "desktop 1" : "desktops 1 to " + modelData); Accessible.checked: on
                                    width: 46; height: 26; radius: Style.cornerRadius
                                    color: on ? root.ink : (countMouse.containsMouse ? Util.alpha(root.ink, 0.14) : "transparent")
                                    border.width: 1; border.color: on ? root.ink : Util.alpha(root.ink, 0.4)
                                    Text { anchors.centerIn: parent; text: modelData === 1 ? "1" : "1–" + modelData; color: parent.on ? Color.background : root.ink; font.family: Style.font.family; font.pixelSize: Style.font.body }
                                    MouseArea { id: countMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: root.setOption("desks", parent.modelData) }
                                }
                            }
                        }
                    }
                    Text {
                        visible: root.hiddenTiles > 0; x: 8; width: parent.width - 16; wrapMode: Text.Wrap
                        text: root.hiddenTiles + (root.hiddenTiles === 1 ? " tile waits" : " tiles wait") + " on desktops that are off; they come back when you turn them on."
                        color: root.muted; font.family: Style.font.family; font.pixelSize: Style.font.body
                    }
                    Item {
                        width: parent.width; height: 30
                        Text { x: 8; anchors.bottom: parent.bottom; text: "THEME"; color: root.ink; font.family: Style.font.family; font.pixelSize: Style.font.body; font.letterSpacing: 2 }
                        Text { anchors.right: parent.right; anchors.bottom: parent.bottom; text: root.themeSlug.replace(/-/g, " "); color: root.muted; font.family: Style.font.family; font.pixelSize: Style.font.body }
                    }
                    Flickable {
                        width: parent.width; height: 58; contentWidth: themeRow.implicitWidth; clip: true
                        flickableDirection: Flickable.HorizontalFlick
                        Text { visible: root.themeList.length === 0; anchors.verticalCenter: parent.verticalCenter; x: 8; text: "loading themes…"; color: root.muted; font.family: Style.font.family; font.pixelSize: Style.font.body }
                        Row {
                            id: themeRow; spacing: Style.spacing.lg
                            Repeater {
                                model: root.themeList
                                Rectangle {
                                    required property var modelData
                                    width: 118; height: 54; radius: Style.cornerRadius
                                    color: modelData.background || Color.background
                                    border.width: modelData.slug === root.themeSlug ? 2 : 1
                                    border.color: modelData.slug === root.themeSlug ? root.ink : Util.alpha(Color.foreground, 0.2)
                                    Text { x: 8; y: 7; width: parent.width - 12; elide: Text.ElideRight; text: modelData.name.toLowerCase(); color: modelData.swatch[0] || Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body }
                                    Row {
                                        x: 8; y: 34; spacing: Style.spacing.xs
                                        Repeater { model: modelData.swatch; Rectangle { required property string modelData; width: 17; height: 6; color: modelData } }
                                    }
                                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: Quickshell.execDetached(["omarchy", "theme", "set", modelData.name]) }
                                }
                            }
                        }
                    }
                }
            }

            // ── Widget store ────────────────────────────────────────────────
            Rectangle {
                id: storePanel
                z: 45
                opacity: root.storeOpen ? 1 : 0; visible: opacity > 0
                Behavior on opacity { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
                x: desk.margin; y: desk.margin
                width: desk.width - 2*desk.margin; height: desk.gridH + desk.gap + desk.dockH
                color: Color.background; border.width: 2; border.color: root.ink; radius: Style.cornerRadius
                MouseArea { anchors.fill: parent; acceptedButtons: Qt.LeftButton | Qt.RightButton }
                Text { x: 20; y: 14; text: "widget store"; color: root.ink; font.family: Style.font.family; font.pixelSize: Style.font.display - 2 }
                Row {
                    anchors { right: parent.right; rightMargin: 18; top: parent.top; topMargin: 16 } spacing: Style.spacing.huge
                    Text { text: storeFetch.running ? "loading…" : " reload"; color: root.ink; font.family: Style.font.family; font.pixelSize: Style.font.body; anchors.verticalCenter: parent.verticalCenter; MouseArea { anchors.fill: parent; anchors.margins: -6; cursorShape: Qt.PointingHandCursor; onClicked: { storeFetch.force = true; if(!storeFetch.running) storeFetch.running = true; } } }
                    Text { text: " close"; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body; anchors.verticalCenter: parent.verticalCenter; MouseArea { anchors.fill: parent; anchors.margins: -6; cursorShape: Qt.PointingHandCursor; onClicked: { root.storeOpen = false; root.typing = false; } } }
                }
                Item {
                    id: storeLeft
                    x: 20; y: 54; width: parent.width * 0.58; height: parent.height - 70
                    Field { id: storeSearch; width: parent.width; desk: desk; placeholder: "search " + root.storeWidgets.length + " widgets"; onTextChanged: root.storeQuery = text }
                    Flow {
                        id: catRow; anchors.top: storeSearch.bottom; anchors.topMargin: Style.spacing.xl; width: parent.width; spacing: Style.spacing.md
                        Repeater {
                            model: root.storeCategories
                            Rectangle {
                                required property var modelData
                                width: catText.implicitWidth + 18; height: 26; radius: Style.cornerRadius
                                color: root.storeCategory === modelData.name ? Util.alpha(root.ink, 0.14) : "transparent"
                                border.width: 1; border.color: root.storeCategory === modelData.name ? root.ink : Util.alpha(Color.foreground, 0.2)
                                Text { id: catText; anchors.centerIn: parent; text: modelData.name + " " + modelData.n; color: root.storeCategory === modelData.name ? root.ink : Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body }
                                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: root.storeCategory = modelData.name }
                            }
                        }
                    }
                    Flickable {
                        anchors { top: catRow.bottom; topMargin: Style.spacing.xxl; left: parent.left; right: parent.right; bottom: parent.bottom }
                        contentWidth: width; contentHeight: storeList.implicitHeight; clip: true
                        boundsBehavior: Flickable.StopAtBounds
                        Column {
                            id: storeList; width: parent.width; spacing: Style.spacing.lg
                            Text { visible: hiddenBuiltins.count > 0; text: "built in"; color: root.muted; font.family: Style.font.family; font.pixelSize: Style.font.subtitle }
                            Repeater {
                                id: hiddenBuiltins
                                model: Config.BUILTIN.filter(function(k){ return !root.config.tiles[k].enabled; })
                                Rectangle {
                                    required property string modelData
                                    width: parent.width; height: 40; radius: Style.cornerRadius; color: builtinMouse.containsMouse ? Util.alpha(root.ink, 0.08) : "transparent"
                                    border.width: 1; border.color: Util.alpha(Color.foreground, 0.2)
                                    Text { x: 12; anchors.verticalCenter: parent.verticalCenter; text: root.tileName(modelData); color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.title }
                                    Text { anchors { right: parent.right; rightMargin: 12; verticalCenter: parent.verticalCenter } text: " add to desk"; color: root.ink; font.family: Style.font.family; font.pixelSize: Style.font.body }
                                    MouseArea { id: builtinMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: root.run(installProc, ["add", modelData, String(root.page)]) }
                                }
                            }
                            Text { visible: localWidgets.count > 0; text: "yours, made with claude"; color: root.muted; font.family: Style.font.family; font.pixelSize: Style.font.subtitle; topPadding: hiddenBuiltins.count > 0 ? 12 : 0 }
                            Repeater {
                                model: FolderListModel {
                                    id: localWidgets
                                    folder: "file://" + root.widgetDir + "local"
                                    showFiles: false; showDirs: true; showDotAndDotDot: false
                                }
                                Rectangle {
                                    id: localRow
                                    required property string fileName
                                    readonly property string key: "owl:local/" + fileName
                                    width: parent.width; height: 40; radius: Style.cornerRadius; color: "transparent"
                                    border.width: 1; border.color: Util.alpha(Color.foreground, 0.2)
                                    Text { x: 12; anchors.verticalCenter: parent.verticalCenter; text: localRow.fileName.replace(/-/g, " ") + (root.config.tiles[localRow.key] ? "   on a desk" : ""); color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.title }
                                    Row {
                                        anchors { right: parent.right; rightMargin: 12; verticalCenter: parent.verticalCenter }
                                        spacing: Style.spacing.huge
                                        Text {
                                            visible: !root.config.tiles[localRow.key]; text: " add to desk"; color: root.ink; font.family: Style.font.family; font.pixelSize: Style.font.body
                                            MouseArea { anchors.fill: parent; anchors.margins: -6; cursorShape: Qt.PointingHandCursor; onClicked: root.run(installProc, ["add", localRow.key, String(root.page)]) }
                                        }
                                        Text {
                                            // Two clicks: the first asks, the second deletes (undo still follows).
                                            text: root.confirmKey === localRow.key ? "delete it?" : "delete"
                                            font.bold: root.confirmKey === localRow.key
                                            color: root.danger; font.family: Style.font.family; font.pixelSize: Style.font.body
                                            MouseArea {
                                                anchors.fill: parent; anchors.margins: -6; cursorShape: Qt.PointingHandCursor
                                                onClicked: { if (root.confirmKey === localRow.key) { root.confirmKey = ""; root.removeTile(localRow.key); } else { root.confirmKey = localRow.key; confirmTimer.restart(); } }
                                            }
                                        }
                                    }
                                }
                            }
                            Label { visible: root.storeMessage !== "" && !root.storePick; text: root.storeMessage; color: root.ink; font.pixelSize: Style.font.body }
                            Text { text: "reviewed widgets from github.com/SimonSchubert/omarchy-widgets"; color: root.muted; font.family: Style.font.family; font.pixelSize: Style.font.subtitle; topPadding: hiddenBuiltins.count + localWidgets.count > 0 ? 12 : 0 }
                            Text { visible: root.storeWidgets.length === 0; text: storeFetch.running ? "loading the store…" : "The store didn't load. Check the connection, then press reload."; color: root.muted; font.family: Style.font.family; font.pixelSize: Style.font.body }
                            Text { visible: root.storeWidgets.length > 0 && root.storeShown.length === 0; text: "No widgets match. Try another word or category."; color: root.muted; font.family: Style.font.family; font.pixelSize: Style.font.body }
                            Grid {
                                width: parent.width; columns: 3; spacing: Style.spacing.xl
                                Repeater {
                                    model: root.storeShown
                                    Rectangle {
                                        required property var modelData
                                        readonly property bool picked: !!root.storePick && root.storePick.id === modelData.id
                                        width: (parent.width - 20) / 3; height: width * 0.75; radius: Style.cornerRadius
                                        color: cardMouse.containsMouse && !picked ? Util.alpha(root.ink, 0.06) : "transparent"
                                        border.width: picked ? 2 : 1
                                        border.color: picked ? root.ink : Util.alpha(Color.foreground, 0.2)
                                        Image {
                                            x: 10; y: 10; width: parent.width - 20; height: parent.height - 62
                                            fillMode: Image.PreserveAspectFit; asynchronous: true; cache: true
                                            source: root.storeOpen ? (root.previewTheme, root.themeList, root.previewUrl(modelData)) : ""
                                        }
                                        Text { x: 12; anchors.bottom: parent.bottom; anchors.bottomMargin: 26; width: parent.width - 24; elide: Text.ElideRight; text: modelData.name + (root.installed(modelData.id) ? "  " : ""); color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.title }
                                        Text {
                                            x: 12; anchors.bottom: parent.bottom; anchors.bottomMargin: 8; width: parent.width - 24; elide: Text.ElideRight
                                            readonly property string note: root.compatLabel(modelData.id)
                                            text: note || (modelData.category || "other") + " · " + modelData.size[0] + "x" + modelData.size[1]
                                            color: note ? root.danger : root.muted; font.family: Style.font.family; font.pixelSize: Style.font.body
                                        }
                                        MouseArea { id: cardMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: { root.storePick = modelData; root.storeMessage = ""; } }
                                    }
                                }
                            }
                        }
                    }
                }
                Rectangle { x: storeLeft.x + storeLeft.width + 14; y: 54; width: 1; height: parent.height - 70; color: Util.alpha(Color.foreground, 0.15) }
                Flickable {
                    x: storeLeft.x + storeLeft.width + 30; y: 54; width: parent.width - x - 20; height: parent.height - 70
                    contentWidth: width; contentHeight: detail.implicitHeight; clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    Column {
                        id: detail; width: parent.width; spacing: Style.spacing.xl
                        readonly property var w: root.storePick
                        Text { visible: !detail.w; width: parent.width; topPadding: 120; horizontalAlignment: Text.AlignHCenter; text: "Pick a widget to see what it installs and runs before adding it."; color: root.muted; font.family: Style.font.family; font.pixelSize: Style.font.title; wrapMode: Text.Wrap }
                        Text { visible: !!detail.w; width: parent.width; elide: Text.ElideRight; text: detail.w ? detail.w.name : ""; color: root.ink; font.family: Style.font.family; font.pixelSize: Style.font.display - 4 }
                        Text { visible: !!detail.w; width: parent.width; wrapMode: Text.Wrap; text: detail.w ? detail.w.author + " · v" + detail.w.version + " · " + detail.w.license + " · " + (detail.w.category || "other") + " · " + detail.w.size[0] + "x" + detail.w.size[1] : ""; color: root.muted; font.family: Style.font.family; font.pixelSize: Style.font.body }
                        Label { visible: !!detail.w; text: detail.w ? detail.w.description : ""; font.pixelSize: Style.font.subtitle }
                        Label {
                            readonly property var c: detail.w ? root.compat(detail.w.id) : null
                            visible: !!c && (c.phone || c.missing.length > 0); color: root.danger; font.pixelSize: Style.font.body
                            text: !c ? "" : c.phone ? "Made for the phone: it reads Android notifications, which a desktop doesn't have, so it stays empty here."
                                : "Needs " + c.missing.join(", ") + ", not installed here. Install with  omarchy pkg add " + c.missing.join(" ")
                        }
                        Text { visible: !!detail.w; text: "installs"; color: root.ink; font.family: Style.font.family; font.pixelSize: Style.font.subtitle; topPadding: Style.spacing.md }
                        Label {
                            visible: !!detail.w; font.pixelSize: Style.font.body
                            text: { var pk = detail.w && detail.w.requires && detail.w.requires.pacman ? detail.w.requires.pacman : []; return pk.length ? "pacman: " + pk.join(", ") : "nothing"; }
                        }
                        Text { visible: !!detail.w; text: "runs"; color: root.ink; font.family: Style.font.family; font.pixelSize: Style.font.subtitle; topPadding: Style.spacing.md }
                        Repeater {
                            model: detail.w ? (detail.w.commands || []) : []
                            Rectangle {
                                required property string modelData
                                width: parent.width; height: cmdText.implicitHeight + 14; radius: Style.cornerRadius; color: Util.alpha(Color.foreground, 0.05)
                                Text { id: cmdText; x: 8; y: 7; width: parent.width - 16; text: modelData; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body; wrapMode: Text.WrapAnywhere }
                            }
                        }
                        Label { visible: !!detail.w && (!detail.w.commands || detail.w.commands.length === 0); text: "no commands"; color: root.muted; font.pixelSize: Style.font.body }
                        Action {
                            visible: !!detail.w; width: Math.min(parent.width, 220); height: 34
                            text: detail.w && root.installed(detail.w.id) ? "remove from desk" : installProc.running ? "adding…" : "add to desk"
                            onClicked: {
                                if (installProc.running) return;
                                if (root.installed(detail.w.id)) { root.removeTile("owl:" + detail.w.id); root.storeMessage = "Removed. Undo is at the bottom of the desk for a few seconds."; return; }
                                root.run(installProc, ["install", detail.w.id, String(root.page)]);
                            }
                        }
                        Label { visible: root.storeMessage !== ""; text: root.storeMessage; color: root.ink; font.pixelSize: Style.font.body }
                    }
                }
            }

            // ── A widget's own screen ───────────────────────────────────────
            Rectangle {
                anchors.fill: parent; z: 47; visible: !!root.screenWidget
                color: Util.alpha(Color.background, 0.55)
                MouseArea { anchors.fill: parent; acceptedButtons: Qt.LeftButton | Qt.RightButton; onClicked: root.screenWidget.closeScreen() }
            }
            Rectangle {
                id: screenCard
                visible: !!root.screenWidget; z: 48
                width: Math.min(560, desk.width - 80); height: desk.gridH - 40
                anchors.centerIn: parent
                readonly property var tree: root.screenWidget ? root.screenWidget.screenTree : null
                color: tree && tree.background ? OwlJs.hex8(tree.background) : Color.background
                border.width: 2; border.color: root.ink; radius: Style.cornerRadius
                clip: true
                MouseArea { anchors.fill: parent; acceptedButtons: Qt.LeftButton | Qt.RightButton }
                Item {
                    id: screenHead; x: 20; y: 14; width: parent.width - 40; height: 28
                    Text {
                        id: screenBack; anchors.verticalCenter: parent.verticalCenter
                        text: "  back"; color: root.ink; font.family: Style.font.family; font.pixelSize: Style.font.title
                        MouseArea { anchors.fill: parent; anchors.margins: -6; cursorShape: Qt.PointingHandCursor; onClicked: root.screenWidget.closeScreen() }
                    }
                    Text {
                        anchors { left: screenBack.right; leftMargin: 16; right: parent.right; verticalCenter: parent.verticalCenter }
                        text: screenCard.tree ? (screenCard.tree.title || "") : ""; elide: Text.ElideRight
                        color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.heading
                    }
                }
                Item {
                    anchors { fill: parent; topMargin: screenHead.y + screenHead.height + 12; leftMargin: 20; rightMargin: 20; bottomMargin: 20 }
                    TapHandler {
                        enabled: !!(screenCard.tree && screenCard.tree.onTap)
                        onTapped: (p) => screenCard.tree.onTap(p.position.x / root.screenWidget.dp, p.position.y / root.screenWidget.dp)
                    }
                    // Screens are phone-height; longer ones scroll.
                    Flickable {
                        id: screenFlick
                        anchors.fill: parent; clip: true
                        contentWidth: width; contentHeight: screenNode.height
                        boundsBehavior: Flickable.StopAtBounds
                        Owl.OwlNode {
                            id: screenNode
                            width: screenFlick.width; height: Math.max(screenFlick.height, implicitHeight)
                            widget: root.screenWidget
                            node: !screenCard.tree ? null : screenCard.tree.children.length === 1 ? screenCard.tree.children[0]
                                : { kind: "Column", p: { gap: 0 }, h: {}, a: {}, c: screenCard.tree.children }
                        }
                    }
                    Rectangle {
                        anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
                        height: 36; visible: screenFlick.contentY < screenFlick.contentHeight - screenFlick.height - 1
                        gradient: Gradient {
                            GradientStop { position: 0; color: "transparent" }
                            GradientStop { position: 1; color: screenCard.color }
                        }
                    }
                }
                Keys.onEscapePressed: root.screenWidget.closeScreen()
            }

            // ── First run: which desktops get tiles ─────────────────────────
            // Like setting a phone's home screen: the first workspaces become the
            // dashboard, the rest stay ordinary Omarchy workspaces.
            Rectangle {
                anchors.fill: parent; z: 60
                opacity: root.choosing ? 1 : 0; visible: opacity > 0
                Behavior on opacity { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
                color: Util.alpha(Color.background, 0.7)
                MouseArea { anchors.fill: parent; acceptedButtons: Qt.LeftButton | Qt.RightButton }
            }
            Rectangle {
                z: 60
                opacity: root.choosing ? 1 : 0; visible: opacity > 0
                Behavior on opacity { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
                width: Math.min(760, desk.width - 40); height: chooseCol.implicitHeight + 44
                anchors.centerIn: parent
                color: Color.background; border.width: 2; border.color: root.ink; radius: Style.cornerRadius
                MouseArea { anchors.fill: parent; acceptedButtons: Qt.LeftButton | Qt.RightButton }
                Column {
                    id: chooseCol; x: 24; y: 22; width: parent.width - 48; spacing: Style.spacing.xxl
                    Text { text: "which desktops get tiles?"; color: root.ink; font.family: Style.font.family; font.pixelSize: Style.font.heading + 4 }
                    Label {
                        text: "OmaTiles turns your first desktops into a home screen, like a phone's launcher: a dashboard you glance at. Tile desktops stay clear of windows: apps open on the next desktop, which tiles them as Omarchy always does."
                        color: Color.foreground; font.pixelSize: Style.font.body + 1
                    }
                    Row {
                        id: chooseRow; width: parent.width; spacing: Style.spacing.xl
                        property real tallest: 0
                        Repeater {
                            model: [{n: 1, t: "desktop 1", d: "One dashboard; apps open from desktop 2. Good on a laptop beside a main screen."},
                                    {n: 2, t: "desktops 1–2", d: "A dashboard and a page for more widgets or agent chats; apps open from desktop 3."},
                                    {n: 3, t: "desktops 1–3", d: "Three pages of tiles; apps open from desktop 4."}]
                            Rectangle {
                                id: choice
                                required property var modelData
                                Accessible.role: Accessible.Button; Accessible.name: "tiles on " + modelData.t
                                Accessible.onPressAction: root.setOption("desks", modelData.n)
                                readonly property real needs: choiceCol.implicitHeight + 32
                                onNeedsChanged: chooseRow.tallest = Math.max(chooseRow.tallest, needs)
                                Component.onCompleted: chooseRow.tallest = Math.max(chooseRow.tallest, needs)
                                width: (chooseRow.width - 2 * chooseRow.spacing) / 3; height: Math.max(needs, chooseRow.tallest)
                                radius: Style.cornerRadius
                                color: choiceMouse.containsMouse ? Util.alpha(root.ink, 0.14) : Util.alpha(Color.foreground, 0.04)
                                border.width: choiceMouse.containsMouse ? 2 : 1; border.color: choiceMouse.containsMouse ? root.ink : Util.alpha(root.ink, 0.35)
                                Column {
                                    id: choiceCol; x: 16; y: 16; width: parent.width - 32; spacing: Style.spacing.lg
                                    // Workspaces 1-5: the tile ones filled in the bar's color, the rest outlined.
                                    Row {
                                        spacing: Style.spacing.xs
                                        Repeater {
                                            model: 5
                                            Rectangle {
                                                required property int index
                                                width: 26; height: 18; radius: 3
                                                color: index < choice.modelData.n ? root.ink : "transparent"
                                                border.width: 1; border.color: index < choice.modelData.n ? root.ink : Util.alpha(Color.foreground, 0.35)
                                                Text { anchors.centerIn: parent; text: index + 1; color: index < choice.modelData.n ? Color.background : root.muted; font.family: Style.font.family; font.pixelSize: Style.font.body - 2 }
                                            }
                                        }
                                    }
                                    Text { text: choice.modelData.t; color: root.ink; font.family: Style.font.family; font.pixelSize: Style.font.heading }
                                    Label { text: choice.modelData.d; color: root.muted; font.pixelSize: Style.font.body }
                                }
                                MouseArea { id: choiceMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: root.setOption("desks", choice.modelData.n) }
                            }
                        }
                    }
                    Text {
                        width: parent.width; wrapMode: Text.Wrap
                        text: "Change it any time from the right-click menu. Tiles on desktops you turn off are kept for when you turn them back on."
                        color: root.muted; font.family: Style.font.family; font.pixelSize: Style.font.body
                    }
                }
            }

            // ── New widget with Claude ──────────────────────────────────────
            Rectangle {
                anchors.fill: parent; z: 46
                opacity: root.createOpen ? 1 : 0; visible: opacity > 0
                Behavior on opacity { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
                color: Util.alpha(Color.background, 0.55)
                MouseArea { anchors.fill: parent; acceptedButtons: Qt.LeftButton | Qt.RightButton; onClicked: { root.createOpen = false; root.typing = false; } }
            }
            Rectangle {
                z: 46
                opacity: root.createOpen ? 1 : 0; visible: opacity > 0
                Behavior on opacity { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
                width: Math.min(640, desk.width - 40); height: createCol.implicitHeight + 36
                anchors.centerIn: parent
                color: Color.background; border.width: 2; border.color: root.ink; radius: Style.cornerRadius
                MouseArea { anchors.fill: parent; acceptedButtons: Qt.LeftButton | Qt.RightButton }
                Column {
                    id: createCol; x: 20; y: 18; width: parent.width - 40; spacing: Style.spacing.xxl
                    Item {
                        width: parent.width; height: 26
                        Text { text: "new widget with claude"; color: root.ink; font.family: Style.font.family; font.pixelSize: Style.font.heading + 2 }
                        Text { anchors.right: parent.right; text: " close"; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body; MouseArea { anchors.fill: parent; anchors.margins: -6; cursorShape: Qt.PointingHandCursor; onClicked: { root.createOpen = false; root.typing = false; } } }
                    }
                    Label { text: "Describe the widget. Claude Code writes it in OWL, the store's checker reviews it, and it lands on a free spot of this desk. Needs the claude CLI and Java."; color: root.muted; font.pixelSize: Style.font.body }
                    Rectangle {
                        width: parent.width; height: 96; radius: Style.cornerRadius; color: Util.alpha(Color.foreground, 0.06)
                        border.width: 1; border.color: createInput.activeFocus ? Util.alpha(root.ink, 0.7) : "transparent"
                        TextEdit {
                            id: createInput; anchors.fill: parent; anchors.margins: 10; wrapMode: TextEdit.Wrap
                            color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.subtitle; selectByMouse: true
                            enabled: !createProc.running
                            Text { visible: !createInput.text; width: parent.width; wrapMode: Text.Wrap; text: "e.g. a countdown to Friday, or this machine's CPU temperature with a sparkline"; color: root.muted; font: createInput.font }
                            Keys.onEscapePressed: { root.createOpen = false; root.typing = false; }
                        }
                        MouseArea { anchors.fill: parent; enabled: !createInput.activeFocus; cursorShape: Qt.IBeamCursor; onClicked: { root.typing = true; createInput.forceActiveFocus(); } }
                    }
                    Action {
                        width: 200; height: 34; enabled: !createProc.running && createInput.text.trim() !== ""
                        text: createProc.running ? "claude is writing it…" : "create"
                        onClicked: { root.createResult = null; root.run(createProc, ["create", createInput.text.trim(), String(root.page)]); }
                    }
                    Label {
                        visible: !!root.createResult; font.pixelSize: Style.font.body
                        color: root.createResult && root.createResult.ok ? Color.foreground : root.danger
                        text: !root.createResult ? "" : root.createResult.ok
                            ? root.createResult.key.slice(10) + ": " + root.placedText(root.createResult)
                              + "\nIt runs: " + root.createResult.programs.filter(function(l){ return l.indexOf("program ")===0; }).map(function(l){ return l.slice(8); }).join(", ")
                            : "Not added: " + root.createResult.error
                    }
                }
            }

            // ── App dock: pinned apps, a divider, recent ones ───────────────
            Rectangle {
                id: dock
                x: desk.margin; y: desk.margin + desk.gridH + desk.gap
                width: desk.width - 2*desk.margin; height: desk.dockH
                radius: Style.cornerRadius
                color: Util.alpha(Color.background, 0.82); border.width: 1; border.color: Util.alpha(Color.foreground, 0.1)
                property string hovered: ""
                readonly property int slots: Math.max(1, Math.floor((width - 220) / 50))
                readonly property var pinned: root.pinnedApps.slice(0, slots)
                readonly property var recent: root.recentApps.slice(0, Math.max(0, slots - pinned.length))
                component AppIcon: Rectangle {
                    id: app
                    required property var modelData
                    property bool pinned: true
                    width: 44; height: 44; radius: Style.cornerRadius
                    Accessible.role: Accessible.Button; Accessible.name: app.modelData.name
                    color: appMouse.containsMouse || (root.dockPick && root.dockPick.id === modelData.id) ? Util.alpha(root.ink, 0.18) : "transparent"
                    Image { anchors.centerIn: parent; width: 30; height: 30; sourceSize: Qt.size(60,60); source: root.config.dockMono ? "" : root.icon(app.modelData); smooth: true; cache: false; visible: !root.config.dockMono }
                    // Symbol icons, like the tablet's icon pack: one Nerd Font symbol per app in
                    // the bar's color; apps without one show their initial in a circle.
                    Text {
                        anchors.centerIn: parent; visible: root.config.dockMono
                        text: root.config.dockMono ? (Glyphs.symbol(app.modelData, root.config.dockSymbols) || Glyphs.initial(app.modelData)) : ""
                        color: root.ink; font.family: Style.font.family; font.pixelSize: 28
                    }
                    MouseArea {
                        id: appMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                        acceptedButtons: Qt.LeftButton | Qt.RightButton
                        onContainsMouseChanged: dock.hovered = containsMouse ? app.modelData.name : (dock.hovered===app.modelData.name ? "" : dock.hovered)
                        onClicked: function(m) {
                            if (m.button === Qt.RightButton) {
                                var p = app.mapToItem(desk, 0, 0);
                                root.menuOpen = false;
                                root.dockPick = {id: app.modelData.id, name: app.modelData.name, pinned: app.pinned, x: p.x};
                            } else { root.dockPick = null; root.launchApp(app.modelData.id); }
                        }
                    }
                }
                Row {
                    anchors.verticalCenter: parent.verticalCenter; x: 10; spacing: Style.spacing.md
                    Repeater { model: dock.pinned; AppIcon {} }
                    Rectangle { visible: dock.recent.length > 0 && dock.pinned.length > 0; width: 1; height: 28; anchors.verticalCenter: parent.verticalCenter; color: Util.alpha(Color.foreground, 0.2) }
                    Repeater { model: dock.recent; AppIcon { pinned: false } }
                }
                Row {
                    anchors { right: parent.right; rightMargin: 14; verticalCenter: parent.verticalCenter }
                    spacing: Style.spacing.xxl
                    Text { anchors.verticalCenter: parent.verticalCenter; text: dock.hovered; color: root.muted; font.family: Style.font.family; font.pixelSize: Style.font.body }
                    // Which desk page this is, when there is more than one.
                    Row {
                        visible: root.pages > 1
                        anchors.verticalCenter: parent.verticalCenter; spacing: Style.spacing.sm
                        Repeater {
                            model: root.pages
                            Rectangle {
                                required property int index
                                width: index + 1 === root.page ? 18 : 6; height: 6; radius: 3
                                color: index + 1 === root.page ? root.ink : Util.alpha(Color.foreground, 0.3)
                            }
                        }
                    }
                }
            }
            // Right-click on a dock icon: pin or unpin it.
            Rectangle {
                visible: !!root.dockPick; z: 50
                width: pickCol.implicitWidth + 2*Style.spacing.xxl; height: pickCol.implicitHeight + 2*Style.spacing.lg
                x: root.dockPick ? Math.max(desk.margin, Math.min(root.dockPick.x, desk.width - width - desk.margin)) : 0
                y: dock.y - height - desk.gap
                color: Color.background; border.width: 2; border.color: root.ink; radius: Style.cornerRadius
                MouseArea { anchors.fill: parent; acceptedButtons: Qt.LeftButton | Qt.RightButton }
                Column {
                    id: pickCol; x: Style.spacing.xxl; y: Style.spacing.lg; spacing: Style.spacing.sm
                    Text { text: root.dockPick ? root.dockPick.name : ""; color: root.muted; font.family: Style.font.family; font.pixelSize: Style.font.body }
                    Text {
                        text: root.dockPick && root.dockPick.pinned ? "unpin from dock" : "pin to dock"
                        color: pickMouse.containsMouse ? root.ink : Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.title
                        MouseArea { id: pickMouse; anchors.fill: parent; anchors.margins: -6; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: root.pin(root.dockPick.id, !root.dockPick.pinned) }
                    }
                }
            }
        }
    }
    function saveEvent() {
        if(!evTitle.text.trim() || gcalAdd.running) return;
        gcalAdd.command=["python3",root.gcal,"add",JSON.stringify({summary:evTitle.text.trim(),date:evDate.text.trim(),start:evStart.text.trim(),end:evEnd.text.trim()})];
        root.addError=""; gcalAdd.running=true;
    }
}
