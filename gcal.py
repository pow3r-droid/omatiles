#!/usr/bin/env python3
"""Google Calendar for the desk card, stdlib only.

  gcal.py auth [--print]       browser sign-in (loopback + PKCE), saves the token
  gcal.py sync                 writes every visible calendar's events to the cache
  gcal.py add JSON             creates an event on the primary calendar
  gcal.py remind               desktop notification 10 minutes before an event

Bring your own Google OAuth client (a Desktop app client from Google Cloud):
save it as ~/.config/omarchy/omatiles/google_client.json. The token is kept
beside it (mode 600). Optional settings in ~/.config/omarchy/omatiles.json:
"calendar": {"subscribe": [calendar ids to add to your list], "skip": [calendar names to leave off]}.
"""
import base64
import datetime
import hashlib
import http.server
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

DIR = Path.home() / '.config/omarchy/omatiles'
CLIENT = DIR / 'google_client.json'
TOKEN = DIR / 'google_token.json'
CACHE = Path.home() / '.cache/omatiles'
EVENTS = CACHE / 'gcal-events.json'
SCOPE = 'https://www.googleapis.com/auth/calendar'
API = 'https://www.googleapis.com/calendar/v3'

def calendar_settings():
    try:
        c = json.loads((Path.home() / '.config/omarchy/omatiles.json').read_text()).get('calendar') or {}
    except (OSError, ValueError, AttributeError):
        c = {}
    pick = lambda k: [x for x in c.get(k, []) if isinstance(x, str)] if isinstance(c.get(k), list) else []
    return pick('subscribe'), pick('skip')

def write_private(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, 'w') as out:
        out.write(text)
    os.replace(name, path)

def client():
    return json.loads(CLIENT.read_text())['installed']

def post_form(url, fields):
    data = urllib.parse.urlencode(fields).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=20) as r:
        return json.loads(r.read())

def auth(print_url=False):
    if not CLIENT.exists():
        status('noclient')
        sys.exit('No Google client: save one as ' + str(CLIENT))
    c = client()
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    state = secrets.token_urlsafe(16)
    result = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if query.get('state', [''])[0] == state:
                result.update({k: v[0] for k, v in query.items()})
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write('<h2>Done. You can close this tab.</h2>'.encode())
        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(('127.0.0.1', 0), Handler)
    redirect = 'http://127.0.0.1:%d' % server.server_port
    url = c['auth_uri'] + '?' + urllib.parse.urlencode({
        'client_id': c['client_id'], 'redirect_uri': redirect, 'response_type': 'code',
        'scope': SCOPE, 'state': state, 'code_challenge': challenge,
        'code_challenge_method': 'S256', 'access_type': 'offline', 'prompt': 'consent'})
    if print_url:
        print(url, flush=True)
    else:
        subprocess.Popen(['xdg-open', url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    server.timeout = 600
    deadline = time.time() + 600
    while 'code' not in result and 'error' not in result and time.time() < deadline:
        server.handle_request()
    if 'code' not in result:
        sys.exit('Google sign-in did not complete: ' + result.get('error', 'timed out'))
    token = post_form(c['token_uri'], {
        'client_id': c['client_id'], 'client_secret': c['client_secret'], 'code': result['code'],
        'code_verifier': verifier, 'grant_type': 'authorization_code', 'redirect_uri': redirect})
    token['expires_at'] = time.time() + token.get('expires_in', 3600) - 60
    write_private(TOKEN, json.dumps(token))
    for cal in calendar_settings()[0]:
        try:
            call('POST', '/users/me/calendarList', {'id': cal})
        except urllib.error.HTTPError:
            pass
    sync()

def access_token():
    token = json.loads(TOKEN.read_text())
    if time.time() >= token.get('expires_at', 0):
        c = client()
        fresh = post_form(c['token_uri'], {
            'client_id': c['client_id'], 'client_secret': c['client_secret'],
            'refresh_token': token['refresh_token'], 'grant_type': 'refresh_token'})
        token.update(fresh)
        token['expires_at'] = time.time() + fresh.get('expires_in', 3600) - 60
        write_private(TOKEN, json.dumps(token))
    return token['access_token']

def call(method, path, body=None, params=None):
    url = API + path + ('?' + urllib.parse.urlencode(params) if params else '')
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method, headers={
        'Authorization': 'Bearer ' + access_token(), 'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=20) as r:
        return json.loads(r.read() or b'{}')

def epoch_ms(when):
    if 'dateTime' in when:
        return datetime.datetime.fromisoformat(when['dateTime']).timestamp() * 1000
    return datetime.datetime.fromisoformat(when['date']).timestamp() * 1000  # local midnight

def status(state, message=''):
    write_private(CACHE / 'gcal-status.json', json.dumps({'state': state, 'message': message}))

def sync():
    if not CLIENT.exists():
        status('noclient')
        return
    if not TOKEN.exists():
        status('disconnected')
        return
    try:
        today = datetime.date.today().replace(day=1)
        start = datetime.datetime.combine(today - datetime.timedelta(days=40), datetime.time()).astimezone()
        end = start + datetime.timedelta(days=150)
        events, skip = [], calendar_settings()[1]
        for cal in call('GET', '/users/me/calendarList').get('items', []):
            if cal.get('hidden') or '#holiday@' in cal['id'] or cal.get('summary') in skip:
                continue
            params = {'timeMin': start.isoformat(), 'timeMax': end.isoformat(), 'singleEvents': 'true',
                      'orderBy': 'startTime', 'maxResults': 500}
            for e in call('GET', '/calendars/%s/events' % urllib.parse.quote(cal['id']), params=params).get('items', []):
                if e.get('status') == 'cancelled' or 'start' not in e:
                    continue
                events.append({
                    'time': epoch_ms(e['start']), 'end': epoch_ms(e['end']), 'allDay': 'date' in e['start'],
                    'summary': e.get('summary', '(no title)'), 'calendar': cal.get('summaryOverride') or cal.get('summary', ''),
                    'color': cal.get('backgroundColor', '#4fd1ff'), 'location': e.get('location', ''),
                    'description': e.get('description', ''), 'link': e.get('htmlLink', '')})
        events.sort(key=lambda e: e['time'])
        write_private(EVENTS, json.dumps(events))
        status('ok')
    except urllib.error.HTTPError as error:
        status('reconnect' if error.code in (400, 401) else 'error', 'HTTP %d' % error.code)
    except (OSError, KeyError, ValueError) as error:
        status('error', str(error)[:120])

def add(raw):
    """Add an event. `raw` is its JSON, which the desk sends on stdin: event details on a
    command line could be read by other local users for as long as the request runs."""
    d = json.loads(raw)
    tz = datetime.datetime.now().astimezone().tzinfo
    day = datetime.date.fromisoformat(d['date'])
    if d.get('start'):
        begin = datetime.datetime.combine(day, datetime.time.fromisoformat(d['start']), tz)
        finish = datetime.datetime.combine(day, datetime.time.fromisoformat(d['end']), tz) if d.get('end') else begin + datetime.timedelta(hours=1)
        when = {'start': {'dateTime': begin.isoformat()}, 'end': {'dateTime': finish.isoformat()}}
    else:
        when = {'start': {'date': day.isoformat()}, 'end': {'date': (day + datetime.timedelta(days=1)).isoformat()}}
    body = dict(when, summary=d['summary'])
    if d.get('location'):
        body['location'] = d['location']
    call('POST', '/calendars/primary/events', body)
    sync()

def notify(app, title, body):
    """A desktop notification over D-Bus, so the event never sits on a command line."""
    try:
        import gi
        gi.require_version('Gio', '2.0')
        from gi.repository import Gio, GLib
        Gio.bus_get_sync(Gio.BusType.SESSION, None).call_sync(
            'org.freedesktop.Notifications', '/org/freedesktop/Notifications', 'org.freedesktop.Notifications',
            'Notify', GLib.Variant('(susssasa{sv}i)', (app, 0, '', title, body, [], {}, -1)),
            None, Gio.DBusCallFlags.NONE, 5000, None)
    except Exception:
        pass

def remind():
    try:
        events = json.loads(EVENTS.read_text())
    except (OSError, ValueError):
        return
    sent_path = CACHE / 'gcal-reminded.json'
    try:
        sent = set(json.loads(sent_path.read_text()))
    except (OSError, ValueError):
        sent = set()
    now = time.time() * 1000
    for e in events:
        key = '%s|%d' % (e['summary'], e['time'])
        if not e['allDay'] and 0 <= e['time'] - now <= 10 * 60000 and key not in sent:
            at = datetime.datetime.fromtimestamp(e['time'] / 1000).strftime('%-I:%M %p')
            notify('Calendar', e['summary'], at + (' · ' + e['location'] if e['location'] else ''))
            sent.add(key)
    write_private(sent_path, json.dumps(sorted(sent)[-200:]))

if __name__ == '__main__':
    op = sys.argv[1]
    if op == 'auth':
        auth(sys.argv[2:] == ['--print'])
    elif op == 'sync':
        sync()
    elif op == 'add':
        add(json.loads(sys.stdin.readline() or '""'))
    elif op == 'remind':
        remind()
