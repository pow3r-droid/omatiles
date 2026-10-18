// The desk config (~/.config/omarchy/omatiles.json): a 16 x 8 grid per page,
// pages are workspaces 1 to `desks` (1-3, chosen on first run; 0 = not chosen yet). Built-in tiles have fixed keys; store and
// Claude-made widgets are "owl:<author>/<name>". Machine and chat settings are
// optional and only the user's own config holds them.
var COLS = 16, ROWS = 8, GRID = 16, PAGES = 3;
var AGENTS = ['claude', 'codex', 'grok', 'hermes'];
var BUILTIN = ['clock', 'local', 'remote', 'calendar', 'weather', 'sun', 'chat-claude', 'chat-codex', 'chat-grok', 'chat-hermes'];
// Apps the dock pins on a fresh desk, when they are installed (Omarchy's defaults first).
var DOCK = ['chromium', 'com.mitchellh.ghostty', 'Alacritty', 'org.gnome.Nautilus', 'obsidian', 'spotify',
            'signal', 'typora', 'org.gnome.Calculator', 'localsend', 'xournalpp'];
function defaults() {return {
    grid:GRID, desks:0, dockMono:false, dockSymbols:{}, menuHint:true, units:'auto', clock:'auto',
    tiles:{
        clock:{enabled:true,col:0,row:0,w:5,h:4},
        local:{enabled:true,col:5,row:0,w:6,h:4},
        calendar:{enabled:true,col:11,row:0,w:5,h:8},
        weather:{enabled:true,col:0,row:4,w:5,h:4},
        sun:{enabled:true,col:5,row:4,w:6,h:4},
        remote:{enabled:false,col:0,row:0,w:8,h:4},
        'chat-claude':{enabled:false,col:0,row:0,w:8,h:4}, 'chat-codex':{enabled:false,col:8,row:0,w:8,h:4},
        'chat-grok':{enabled:false,col:0,row:4,w:8,h:4}, 'chat-hermes':{enabled:false,col:8,row:4,w:8,h:4}
    },
    dock:DOCK.slice(),
    local:{services:[]},
    remote:{host:'', name:'', services:[], link:{label:'', url:''}},
    chat:{host:'', where:'', agents:{}}
};}
function clampInt(v, lo, hi) { return Math.max(lo, Math.min(hi, Math.round(v))); }
function owlKey(k) { return /^owl:[a-z0-9-]+\/[a-z0-9-]+$/.test(k); }
function str(v, max) { return typeof v === 'string' ? v.slice(0, max || 200) : ''; }
function services(list) {
    return Array.isArray(list) ? list.filter(function(s){ return s && typeof s.unit === 'string'; }).slice(0, 6)
        .map(function(s){ return {label: str(s.label, 40) || s.unit, unit: s.unit, user: s.user !== false}; }) : [];
}
function parse(raw) {
    var base=defaults(), input; try {input=JSON.parse(raw);} catch(e){return base;}
    if(!input || typeof input!=='object') return base;
    ['dockMono','menuHint'].forEach(function(k){ if(typeof input[k]==='boolean') base[k]=input[k]; });
    if(typeof input.desks==='number' && isFinite(input.desks)) base.desks=clampInt(input.desks,1,PAGES);
    if(['auto','metric','imperial'].indexOf(input.units)!==-1) base.units=input.units;
    // 12- or 24-hour time; auto follows the locale.
    if(['auto','12','24'].indexOf(input.clock)!==-1) base.clock=input.clock;
    // Per-app icon overrides: desktop id or app name -> a logo slug, an SVG path, a symbol or its hex code.
    if(input.dockSymbols && typeof input.dockSymbols==='object' && !Array.isArray(input.dockSymbols))
        Object.keys(input.dockSymbols).slice(0,64).forEach(function(k){ var v=input.dockSymbols[k]; if(typeof v==='string' && v.length<=12000) base.dockSymbols[k]=v; });
    if(Array.isArray(input.dock)) base.dock=input.dock.filter(function(d){return typeof d==='string' && d.length>0;}).slice(0,24);
    if(input.local && typeof input.local==='object') base.local.services=services(input.local.services);
    var r=input.remote;
    if(r && typeof r==='object') {
        base.remote={host:str(r.host,120), name:str(r.name,24), services:services(r.services),
                     link:{label:str(r.link && r.link.label,32), url:/^https?:\/\//.test(str(r.link && r.link.url)) ? str(r.link.url,300) : ''}};
    }
    var c=input.chat;
    if(c && typeof c==='object') {
        base.chat.host=str(c.host,120); base.chat.where=str(c.where,24);
        if(c.agents && typeof c.agents==='object') AGENTS.forEach(function(a){
            var o=c.agents[a]; if(o && typeof o==='object') base.chat.agents[a]={name:str(o.name,24)};
        });
    }
    var tiles=input.tiles;
    if(tiles && typeof tiles==='object') Object.keys(tiles).forEach(function(k){
        var t=tiles[k]; if(!t || typeof t!=='object') return;
        if(BUILTIN.indexOf(k)===-1 && !owlKey(k)) return;
        var b=base.tiles[k] || (base.tiles[k]={enabled:true,col:0,row:0,w:4,h:4});
        if(typeof t.enabled==='boolean') b.enabled=t.enabled;
        if(t.top===true) b.top=true;
        if(typeof t.page==='number' && isFinite(t.page)) b.page=clampInt(t.page,1,PAGES);
        ['col','row','w','h'].forEach(function(p){if(typeof t[p]==='number' && isFinite(t[p]))b[p]=t[p];});
        b.w=clampInt(b.w,1,COLS); b.h=clampInt(b.h,1,ROWS);
        b.col=clampInt(b.col,0,COLS-b.w); b.row=clampInt(b.row,0,ROWS-b.h);
    });
    return base;
}
if(typeof module!=='undefined')module.exports={defaults:defaults,parse:parse,COLS:COLS,ROWS:ROWS,PAGES:PAGES,BUILTIN:BUILTIN,AGENTS:AGENTS};
