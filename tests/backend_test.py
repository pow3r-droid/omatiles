import contextlib
import hashlib
import importlib.util
import io
import json
import shutil
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
sys.dont_write_bytecode = True
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
REAL_RUN = subprocess.run  # the tests mock subprocess.run; the CLI tests need the real one
spec = importlib.util.spec_from_file_location('backend', ROOT / 'backend.py')
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)

spec = importlib.util.spec_from_file_location('icontrace', ROOT / 'icontrace.py')
icontrace = importlib.util.module_from_spec(spec)
spec.loader.exec_module(icontrace)

def png(path, w, h, pixel, filt=0):
    """Write an RGBA PNG whose pixel (x, y) is pixel(x, y), every row using filter `filt`."""
    import struct, zlib
    raw = b''
    for y in range(h):
        line = bytes(c for x in range(w) for c in pixel(x, y))
        if filt == 1:
            line = bytes((line[i] - (line[i - 4] if i >= 4 else 0)) & 255 for i in range(len(line)))
        raw += bytes([filt]) + line
    chunk = lambda k, d: struct.pack('>I', len(d)) + k + d + struct.pack('>I', zlib.crc32(k + d) & 0xffffffff)
    Path(path).write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0))
                           + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))

def done(out='', err='', code=0):
    return subprocess.CompletedProcess([], code, out, err)

class Base(unittest.TestCase):
    """Every path points into a temp dir and subprocess.run is a mock that fails unless set."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name).resolve()
        self.cache, self.config = root / 'cache', root / 'config'
        data = self.config / 'omatiles'
        for name, value in (('CACHE', self.cache), ('CONFIG', self.config), ('DATA', data),
                            ('WIDGETS', data / 'widgets'), ('TRASH', data / 'widgets' / '.trash')):
            p = patch.object(backend, name, value); p.start(); self.addCleanup(p.stop)
        self.widgets, self.trash = data / 'widgets', data / 'widgets' / '.trash'
        self.config.mkdir(parents=True); self.cache.mkdir(parents=True)
        home = patch.object(backend.Path, 'home', return_value=root / 'home'); home.start(); self.addCleanup(home.stop)
        runner = patch.object(backend.subprocess, 'run', side_effect=AssertionError('unmocked subprocess.run'))
        self.run_mock = runner.start(); self.addCleanup(runner.stop)

    def sub(self, result):
        self.run_mock.side_effect = None
        self.run_mock.return_value = result

    def write_config(self, config):
        (self.config / backend.CONFIG_FILE).write_text(json.dumps(config))

    def read_config(self):
        return json.loads((self.config / backend.CONFIG_FILE).read_text())

    def tiles(self):
        return self.read_config()['tiles']

    def call(self, fn, *args, **kwargs):
        """(printed json or None, exit code or None)"""
        out, code = io.StringIO(), None
        with contextlib.redirect_stdout(out):
            try:
                fn(*args, **kwargs)
            except SystemExit as e:
                code = e.code
        text = out.getvalue().strip()
        return (json.loads(text) if text else None), code

class CreateTests(Base):
    """A widget Claude writes goes on a desk only after the store has shown what it runs."""
    SOURCE = b'widget "made" {\n size: 4x2\n}\n'

    def fake_tools(self, source=None):
        source = self.SOURCE if source is None else source
        def fake(args, **kw):
            if args[0] == 'pacman':
                return done(code=1)
            if args[0] == 'claude':
                (Path(kw['cwd']) / 'widget.owl').write_bytes(source)
                return done('{"session_id":"s1"}')
            if args[:3] == ['java', '-jar', str(backend.OWL / 'owl.jar')] and args[3] == 'check':
                return done()
            if args[3] == 'index':
                repo = Path(args[4])
                owl = next(repo.rglob('widget.owl'))
                entry = {'id': 'local/' + owl.parent.name, 'name': owl.parent.name, 'author': 'local',
                         'sha256': hashlib.sha256(owl.read_bytes()).hexdigest(), 'size': [4, 2],
                         'requires': {'pacman': ['missingpkg']}, 'commands': ['echo hi']}
                (repo / 'index.json').write_text(json.dumps({'widgets': [entry]}))
                return done()
            raise AssertionError(args)
        self.run_mock.side_effect = fake

    def create(self, source=None):
        self.write_config({'tiles': {}})
        self.fake_tools(source)
        with patch.object(backend.shutil, 'which', return_value='/usr/bin/x'):
            return self.call(backend.create, 'a made widget', 1)

    def test_create_shows_what_it_runs_and_places_nothing(self):
        out, code = self.create()
        self.assertIsNone(code)
        self.assertTrue(out['ok'])
        self.assertEqual(out['key'], 'owl:local/made')
        self.assertEqual(out['entry']['commands'], ['echo hi'])
        self.assertTrue(out['entry']['local'])
        self.assertEqual(out['entry']['sha256'], hashlib.sha256(self.SOURCE).hexdigest())
        self.assertEqual(self.tiles(), {})
        saved = json.loads((self.widgets / 'local' / 'made' / 'review.json').read_text())
        self.assertEqual(saved, out['entry'])

    def test_claude_may_write_only_in_a_copy_of_the_docs_never_the_plugin(self):
        self.create()
        claude = next(c.args[0] for c in self.run_mock.call_args_list if c.args[0][0] == 'claude')
        given = claude[claude.index('--add-dir') + 1]
        self.assertEqual(given, str(self.cache / 'owl-ref'))
        self.assertNotIn(str(backend.OWL), ' '.join(claude))
        self.assertTrue((self.cache / 'owl-ref' / 'LANGUAGE.md').is_file())

    def test_a_made_widget_goes_on_only_with_the_hash_that_was_shown(self):
        out, _ = self.create()
        key, sha = out['key'], out['entry']['sha256']
        for shown in ['', '0' * 64, sha.upper()]:
            res, code = self.call(backend.add_builtin, key, 1, shown)
            self.assertEqual(code, 1, repr(shown))
            self.assertNotIn(key, self.tiles(), repr(shown))
        # Changed after it was shown: refused too.
        (self.widgets / 'local' / 'made' / 'widget.owl').write_bytes(self.SOURCE + b'# changed\n')
        res, code = self.call(backend.add_builtin, key, 1, sha)
        self.assertEqual(code, 1)
        (self.widgets / 'local' / 'made' / 'widget.owl').write_bytes(self.SOURCE)
        res, code = self.call(backend.add_builtin, key, 1, sha)
        self.assertIsNone(code)
        self.assertEqual(res['missing'], ['missingpkg'])
        self.assertTrue(self.tiles()[key]['enabled'])

    def test_review_lists_only_widgets_made_here(self):
        self.create()
        out, code = self.call(backend.review_local, 'owl:local/made')
        self.assertIsNone(code)
        self.assertEqual(out['commands'], ['echo hi'])
        for key in ['owl:al/clock', 'owl:local/../x', 'owl:local/missing', 'clock']:
            out, code = self.call(backend.review_local, key)
            self.assertEqual(code, 1, key)

    @unittest.skipUnless(shutil.which('java'), 'needs Java for the real checker')
    def test_review_with_the_real_checker_lists_every_command(self):
        folder = self.widgets / 'local' / 'feeds'
        folder.mkdir(parents=True)
        shutil.copyfile(backend.OWL / 'examples' / 'feeds.owl', folder / 'widget.owl')
        self.run_mock.side_effect = REAL_RUN
        entry, why = backend.review(folder)
        self.assertIsNone(why)
        self.assertEqual(entry['id'], 'local/feeds')
        self.assertEqual(entry['sha256'], hashlib.sha256((folder / 'widget.owl').read_bytes()).hexdigest())
        self.assertTrue(entry['commands'] and all(isinstance(c, str) for c in entry['commands']))
        self.assertTrue(any('feeds' in c for c in entry['commands']))

    @unittest.skipUnless(shutil.which('java'), 'needs Java for the real checker')
    def test_review_says_which_marketplace_rule_a_widget_misses(self):
        folder = self.widgets / 'local' / 'bare'
        folder.mkdir(parents=True)
        (folder / 'widget.owl').write_text('widget "bare" {\n  meta { owl: 6 }\n  size: 4x2\n  Text { text: sh("date") }\n}\n')
        self.run_mock.side_effect = REAL_RUN
        entry, why = backend.review(folder)
        self.assertIsNone(entry)
        self.assertIn('description', why)
        self.assertFalse((folder / 'review.json').exists())

    def test_create_sends_the_listing_rule_back_to_claude(self):
        # The first file passes the checker but not the store's listing; Claude gets the reason.
        listed = []
        self.write_config({'tiles': {}})
        self.fake_tools()
        fake = self.run_mock.side_effect
        def first_skipped(args, **kw):
            if args[0] == 'java' and args[3] == 'index' and not listed:
                listed.append(1)
                (Path(args[4]) / 'index.json').write_text('{"widgets": []}')
                return done('skipped widgets/local/made/widget.owl: meta needs a description\n')
            return fake(args, **kw)
        self.run_mock.side_effect = first_skipped
        with patch.object(backend.shutil, 'which', return_value='/usr/bin/x'):
            out, code = self.call(backend.create, 'a made widget', 1)
        self.assertTrue(out['ok'], out)
        claude = [c for c in self.run_mock.call_args_list if c.args[0][0] == 'claude']
        self.assertEqual(len(claude), 2)
        self.assertIn('meta needs a description', claude[1].kwargs['input'])

    def test_the_desk_adds_a_made_widget_only_from_its_review(self):
        qml = (ROOT / 'Service.qml').read_text()
        self.assertNotIn('["add", localRow.key', qml)
        self.assertIn('root.run(reviewProc, ["review", localRow.key])', qml)

def load_gcal():
    spec = importlib.util.spec_from_file_location('gcal_under_test', ROOT / 'gcal.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class ArgvTests(Base):
    """Nothing private goes on a command line, where other local users can read it."""
    def test_no_process_on_the_desk_gets_typed_text_as_an_argument(self):
        # The desk's text fields and chat input reach programs over stdin only. This would
        # have caught the chat turn, the widget request and the calendar event.
        qml = (ROOT / 'Service.qml').read_text()
        pat = r'(command\s*[:=]\s*\[|run\(\w+,\s*\[|execDetached\(\[)[^\]]*\btext\b'
        self.assertNotRegex(qml, pat)
        self.assertNotIn('"wl-copy", "--"', qml)
        self.assertNotIn('notify-send', qml)

    def test_curl_gets_its_url_on_stdin(self):
        self.sub(done('{}'))
        backend.curl('https://wttr.in/Some%20Town?format=j1')
        args, kwargs = self.run_mock.call_args
        self.assertNotIn('Some', ' '.join(args[0]))
        self.assertEqual(args[0][-2:], ['--config', '-'])
        self.assertEqual(kwargs['input'], 'url = "https://wttr.in/Some%20Town?format=j1"\n')

    def test_a_widget_notice_comes_on_stdin(self):
        with patch.object(backend, 'notify') as sent, \
                patch.object(backend.sys, 'stdin', io.StringIO(json.dumps(json.dumps(['title', 'body'])) + '\n')):
            backend.notify_stdin()
        sent.assert_called_once_with('title', 'body')
        for raw in ['"nope"\n', '"[1, 2]"\n', '']:
            with patch.object(backend, 'notify') as sent, patch.object(backend.sys, 'stdin', io.StringIO(raw)):
                backend.notify_stdin()
            sent.assert_not_called()

    def test_calendar_events_come_on_stdin_and_reminders_over_dbus(self):
        gcal = load_gcal()
        src = (ROOT / 'gcal.py').read_text()
        self.assertIn("add(json.loads(sys.stdin.readline()", src)
        self.assertNotIn('notify-send', src)
        posted = []
        with patch.object(gcal, 'call', side_effect=lambda m, path, body=None, params=None: posted.append(body)), \
                patch.object(gcal, 'sync'):
            gcal.add(json.dumps({'summary': 'Dentist', 'date': '2026-10-20', 'start': '14:00'}))
        self.assertEqual(posted[0]['summary'], 'Dentist')
        events = Path(self.tmp.name) / 'events.json'
        soon = int(time.time() * 1000) + 5 * 60000
        events.write_text(json.dumps([{'summary': 'Dentist', 'time': soon, 'allDay': False, 'location': 'Main St'}]))
        with patch.object(gcal, 'EVENTS', events), patch.object(gcal, 'CACHE', Path(self.tmp.name)), \
                patch.object(gcal, 'notify') as shown:
            gcal.remind()
        self.assertEqual(shown.call_args.args[:2], ('Calendar', 'Dentist'))
        self.assertIn('Main St', shown.call_args.args[2])
        self.run_mock.assert_not_called()

class PlaceTests(Base):
    def test_place_updates_one_tile_with_integer_geometry_and_keeps_others(self):
        self.write_config({'tiles': {'clock': {'enabled': True, 'col': 0, 'row': 0, 'w': 5, 'h': 4},
                                     'weather': {'enabled': True, 'col': 0, 'row': 4, 'w': 5, 'h': 4}}})
        backend.place('clock', json.dumps({'col': 2.7, 'row': -1, 'w': 'x', 'h': 3, 'bogus': 9, 'enabled': False}))
        tiles = self.tiles()
        self.assertEqual(tiles['clock'], {'enabled': True, 'col': 2, 'row': 0, 'w': 5, 'h': 3})
        self.assertIsInstance(tiles['clock']['col'], int)
        self.assertEqual(tiles['weather'], {'enabled': True, 'col': 0, 'row': 4, 'w': 5, 'h': 4})

    def test_place_creates_missing_tile_enabled(self):
        backend.place('owl:a/b', json.dumps({'col': 1, 'row': 2, 'w': 3, 'h': 4}))
        self.assertEqual(self.tiles()['owl:a/b'], {'enabled': True, 'col': 1, 'row': 2, 'w': 3, 'h': 4})

    def test_place_clamps_geometry_to_the_grid(self):
        backend.place('clock', json.dumps({'col': 99, 'row': 99, 'w': 99, 'h': 99}))
        t = self.tiles()['clock']
        self.assertLessEqual(t['col'] + t['w'], backend.COLS)
        self.assertLessEqual(t['row'] + t['h'], backend.ROWS)

class DeskTests(Base):
    def fill(self, page):
        return {'enabled': True, 'page': page, 'col': 0, 'row': 0, 'w': 16, 'h': 8}

    def test_default_tiles_are_occupied_and_hidden_ones_are_not(self):
        self.assertIsNone(backend.free_spot({'tiles': {}}, 1, 1))
        self.assertEqual(backend.free_spot({'tiles': {}}, 5, 4, page=2), (0, 0))
        self.assertEqual(backend.free_spot({'tiles': {'clock': {'enabled': False}}}, 5, 4), (0, 0))
        # a hidden tile frees its cells but its neighbour still blocks
        self.assertIsNone(backend.free_spot({'tiles': {'clock': {'enabled': False}}}, 6, 4))
        # default-off built-ins (remote, chat) occupy nothing
        self.assertEqual(backend.DEFAULT_OFF, {'remote', 'chat-claude', 'chat-codex', 'chat-grok', 'chat-hermes'})

    def test_full_page_shrinks_to_least_size(self):
        self.write_config({'tiles': {'owl:a/fill': {'enabled': True, 'page': 2, 'col': 0, 'row': 0, 'w': 16, 'h': 6}}})
        result = backend.put_on_desk('owl:a/new', (4, 4), page=2, least=(2, 2))
        self.assertEqual((result['ok'], result['page'], result['w'], result['h'], result['shrunk']), (True, 2, 4, 2, True))
        self.assertEqual(self.tiles()['owl:a/new'], {'enabled': True, 'col': 0, 'row': 6, 'w': 4, 'h': 2, 'page': 2})

    def test_no_room_even_shrunk_goes_on_top_at_full_size(self):
        self.write_config({'tiles': {'owl:a/fill': {'enabled': True, 'page': 2, 'col': 0, 'row': 0, 'w': 16, 'h': 7}}})
        result = backend.put_on_desk('owl:a/new', (4, 4), page=2, least=(4, 4))
        self.assertEqual((result['ok'], result['page'], result['overlap'], result['shrunk']), (True, 2, True, False))
        self.assertEqual(self.tiles()['owl:a/new'], {'enabled': True, 'col': 6, 'row': 2, 'w': 4, 'h': 4, 'page': 2, 'top': True})


    def test_full_page_stays_on_this_page_and_page_one_has_no_page_key(self):
        self.write_config({'tiles': {'owl:a/fill': self.fill(2)}})
        result = backend.put_on_desk('owl:a/new', (4, 4), page=2)
        self.assertEqual((result['ok'], result['page'], result['overlap']), (True, 2, True))
        self.write_config({'tiles': {k: {'enabled': False} for k in ('clock', 'local', 'calendar', 'weather', 'sun')}})
        result = backend.put_on_desk('owl:a/p1', (4, 4), page=1)
        self.assertEqual((result['page'], result['overlap']), (1, False))
        self.assertNotIn('page', self.tiles()['owl:a/p1'])
        self.assertNotIn('top', self.tiles()['owl:a/p1'])


    def test_a_full_desk_still_takes_the_widget(self):
        self.write_config({'tiles': {'owl:a/f2': self.fill(2), 'owl:a/f3': self.fill(3)}})
        result = backend.put_on_desk('owl:a/new', (4, 4), page=1, missing=['jq'])
        self.assertEqual((result['ok'], result['page'], result['overlap'], result['missing']), (True, 1, True, ['jq']))
        self.assertIs(self.tiles()['owl:a/new']['top'], True)

    def test_dragging_a_stacked_tile_clears_top(self):
        self.write_config({'tiles': {'owl:a/new': {'enabled': True, 'col': 6, 'row': 2, 'w': 4, 'h': 4, 'top': True}}})
        backend.place('owl:a/new', json.dumps({'col': 0, 'row': 0}))
        self.assertNotIn('top', self.tiles()['owl:a/new'])


    def test_desk_count_defaults_to_three_and_clamps(self):
        for value, want in ((None, 3), (0, 3), (1, 1), (2, 2), (9, 3), (-1, 3), (True, 3), ('2', 3)):
            self.assertEqual(backend.desk_count({'desks': value}), want, repr(value))

    def test_one_desk_never_spills_onto_workspace_two(self):
        self.write_config({'desks': 1, 'tiles': {}})
        # the default tiles fill desk 1, and there is no desk 2: it goes on top of desk 1
        result = backend.put_on_desk('owl:a/new', (6, 4), page=3, least=(6, 4))
        self.assertEqual((result['ok'], result['page'], result['overlap']), (True, 1, True))
        self.assertNotIn('page', self.tiles()['owl:a/new'])


    def test_two_desks_use_page_two_but_not_three(self):
        self.write_config({'desks': 2, 'tiles': {}})
        self.assertEqual(backend.put_on_desk('owl:a/new', (4, 4), page=3)['page'], 2)


    def test_move_to_a_full_desk_goes_on_top(self):
        self.write_config({'tiles': {'owl:a/w': {'enabled': True, 'col': 0, 'row': 0, 'w': 4, 'h': 4, 'page': 2}}})
        self.call(backend.move, 'owl:a/w', 1)
        self.assertEqual(self.tiles()['owl:a/w'], {'enabled': True, 'col': 6, 'row': 2, 'w': 4, 'h': 4, 'top': True})

    def test_move_stays_within_the_desks(self):
        self.write_config({'desks': 2, 'tiles': {'owl:a/w': {'enabled': True, 'col': 0, 'row': 0, 'w': 4, 'h': 4, 'page': 2}}})
        self.call(backend.move, 'owl:a/w', 3)
        self.assertEqual(self.tiles()['owl:a/w']['page'], 2)

class InstallTests(Base):
    SOURCE = b'widget "x" {\n size: 4x2\n minSize: 2x1\n}\n'
    SHA = hashlib.sha256(SOURCE).hexdigest()

    def index(self, entries):
        (self.cache / 'store.json').write_text(json.dumps({'widgets': entries}))

    def curl_returns(self, body, code=0):
        def fake(args, **kw):
            if args[0] == 'pacman':
                return done(code=1 if args[-1] == 'missingpkg' else 0)
            return subprocess.CompletedProcess(args, code, body, b'')
        self.run_mock.side_effect = fake

    def test_install_checks_hash_then_places(self):
        entry = {'id': 'al/clock-x', 'path': 'w/clock-x.owl', 'sha256': hashlib.sha256(self.SOURCE).hexdigest(),
                 'requires': {'pacman': ['missingpkg', 'ok', 'Bad Name; x']}}
        self.index([entry])
        self.curl_returns(self.SOURCE)
        out, code = self.call(backend.install, 'al/clock-x', 1, self.SHA)
        self.assertIsNone(code)
        self.assertTrue(out['ok'])
        self.assertEqual(out['missing'], ['missingpkg'])
        folder = self.widgets / 'al' / 'clock-x'
        self.assertEqual((folder / 'widget.owl').read_bytes(), self.SOURCE)
        self.assertEqual(json.loads((folder / 'store.json').read_text())['id'], 'al/clock-x')
        self.assertEqual((out['w'], out['h']), (4, 2))
        self.assertTrue(self.tiles()['owl:al/clock-x']['enabled'])
        curl_call = self.run_mock.call_args_list[0].args[0]
        self.assertEqual(curl_call[0], 'curl')
        self.assertEqual(curl_call[-1], backend.STORE + 'w/clock-x.owl')

    def test_hash_mismatch_installs_nothing(self):
        self.index([{'id': 'al/clock-x', 'path': 'p.owl', 'sha256': '0' * 64}])
        self.curl_returns(self.SOURCE)
        out, code = self.call(backend.install, 'al/clock-x', 1, '0' * 64)
        self.assertEqual(code, 1)
        self.assertFalse(out['ok'])
        self.assertFalse((self.widgets / 'al').exists())
        self.assertFalse((self.config / backend.CONFIG_FILE).exists())

    def test_download_failure_installs_nothing(self):
        self.index([{'id': 'al/clock-x', 'path': 'p.owl', 'sha256': hashlib.sha256(self.SOURCE).hexdigest()}])
        self.curl_returns(self.SOURCE, code=22)
        out, code = self.call(backend.install, 'al/clock-x', 1, self.SHA)
        self.assertEqual(code, 1)
        self.assertFalse((self.widgets / 'al').exists())

    def test_install_runs_only_the_entry_the_user_was_shown(self):
        # The catalog reloaded after the user looked: the cached entry is not the one on screen.
        self.index([{'id': 'al/clock-x', 'path': 'p.owl', 'sha256': self.SHA}])
        self.curl_returns(self.SOURCE)
        for shown in ['', 'f' * 64, self.SHA.upper(), self.SHA + '\n', 'x']:
            out, code = self.call(backend.install, 'al/clock-x', 1, shown)
            self.assertEqual(code, 1, repr(shown))
            self.assertIn('changed this widget', out['error'], repr(shown))
        self.run_mock.assert_not_called()
        self.assertFalse(self.widgets.exists())

    def test_path_traversal_and_unknown_ids_are_rejected(self):
        evil = ['../../evil', 'a/../../x', '/etc/passwd', 'a/b/c', 'A/b', '', 'a/']
        self.index([{'id': i, 'path': 'p.owl', 'sha256': hashlib.sha256(self.SOURCE).hexdigest()} for i in evil + ['al/real']])
        self.curl_returns(self.SOURCE)
        for widget_id in evil + ['al/missing']:
            out, code = self.call(backend.install, widget_id, 1, self.SHA)
            self.assertEqual(code, 1, repr(widget_id))
            self.assertEqual(out['error'], 'unknown widget', repr(widget_id))
        self.run_mock.assert_not_called()
        self.assertFalse(self.widgets.exists())

class WidgetIdTests(Base):
    def test_widget_id_rejects_a_trailing_newline(self):
        self.assertIsNone(backend.WIDGET_ID.match('a/b\n'))
        self.assertIsNone(backend.owl_folder('owl:a/b\n'))

    def test_widget_id_shape(self):
        for good in ('a/b', 'al-1/clock-2'):
            self.assertTrue(backend.WIDGET_ID.match(good), good)
        for bad in ('', 'a', 'a/b/c', '../x', 'a/..', 'A/b', 'a/b c', 'a/b;x', '/a/b'):
            self.assertFalse(backend.WIDGET_ID.match(bad), bad)

class TrashTests(Base):
    def make_widget(self, author='al', name='w1', tile=None):
        folder = self.widgets / author / name
        folder.mkdir(parents=True)
        (folder / 'widget.owl').write_text('widget "w1" {}')
        (folder / 'store.json').write_text('{}')
        self.write_config({'tiles': {'owl:%s/%s' % (author, name): tile or {}, 'clock': {'enabled': True}}})
        return folder

    def test_remove_then_restore_store_widget(self):
        tile = {'enabled': True, 'col': 3, 'row': 1, 'w': 4, 'h': 2, 'page': 2}
        folder = self.make_widget(tile=tile)
        backend.remove('owl:al/w1')
        slot = self.trash / 'al__w1'
        self.assertFalse(folder.exists())
        self.assertFalse(folder.parent.exists())  # the empty author folder goes too
        self.assertEqual(json.loads((slot / '.tile.json').read_text()), tile)
        self.assertTrue((slot / 'widget.owl').exists())
        self.assertNotIn('owl:al/w1', self.tiles())
        self.assertIn('clock', self.tiles())
        backend.restore('owl:al/w1')
        self.assertTrue((folder / 'widget.owl').exists())
        self.assertFalse((folder / '.tile.json').exists())
        self.assertFalse(slot.exists())
        self.assertEqual(self.tiles()['owl:al/w1'], tile)

    def test_remove_keeps_author_folder_with_other_widgets(self):
        self.make_widget()
        (self.widgets / 'al' / 'other').mkdir()
        backend.remove('owl:al/w1')
        self.assertTrue((self.widgets / 'al' / 'other').exists())

    def test_builtin_only_toggles_enabled(self):
        self.write_config({'tiles': {'clock': {'enabled': True, 'col': 1, 'row': 1, 'w': 5, 'h': 4}}})
        backend.remove('clock')
        self.assertEqual(self.tiles()['clock'], {'enabled': False, 'col': 1, 'row': 1, 'w': 5, 'h': 4})
        self.assertFalse(self.trash.exists())
        backend.restore('clock')
        self.assertEqual(self.tiles()['clock']['enabled'], True)
        backend.remove('remote')
        self.assertEqual(self.tiles()['remote'], {'enabled': False})

    def test_restore_without_a_slot_does_nothing(self):
        self.write_config({'tiles': {}})
        backend.restore('owl:al/none')
        self.assertEqual(self.tiles(), {})

    def test_remove_ignores_ids_that_are_not_widgets(self):
        outside = self.widgets.parent / 'keep'
        outside.mkdir(parents=True)
        self.write_config({'tiles': {}})
        backend.remove('owl:../keep')
        self.assertTrue(outside.exists())

    def test_prune_trash_removes_slots_older_than_a_day(self):
        old, new = self.trash / 'a__old', self.trash / 'a__new'
        old.mkdir(parents=True); new.mkdir(parents=True)
        age = time.time() - 2 * 86400
        os.utime(old, (age, age))
        backend.prune_trash()
        self.assertFalse(old.exists())
        self.assertTrue(new.exists())

    def test_prune_trash_without_trash_is_fine(self):
        backend.prune_trash()

class DockTests(Base):
    def test_pin_and_unpin_edit_the_dock(self):
        self.write_config({'tiles': {}, 'dock': ['a', 7, 'b']})
        backend.pin('c', True)
        self.assertEqual(self.read_config()['dock'], ['a', 'b', 'c'])
        backend.pin('a', True)  # moves to the end, no duplicate
        self.assertEqual(self.read_config()['dock'], ['b', 'c', 'a'])
        backend.pin('b', False)
        self.assertEqual(self.read_config()['dock'], ['c', 'a'])

    def test_pin_rejects_slashes_newlines_and_empty(self):
        self.write_config({'tiles': {}, 'dock': ['a']})
        for bad in ('x/y', 'x\ny', 'x\ry', '', None):
            backend.pin(bad, True)
            backend.pin(bad, False)
        self.assertEqual(self.read_config()['dock'], ['a'])

    def test_recent_is_most_recent_first_unique_and_capped(self):
        for i in range(20):
            backend.recent('app%d' % i)
        backend.recent('app5')
        backend.recent('app5')
        apps = json.loads((self.cache / 'recent.json').read_text())
        self.assertEqual(apps[0], 'app5')
        self.assertEqual(len(apps), 16)
        self.assertEqual(len(set(apps)), 16)
        self.assertEqual(apps[1], 'app19')
        backend.recent('bad/id'); backend.recent('bad\nid'); backend.recent('')
        self.assertEqual(json.loads((self.cache / 'recent.json').read_text()), apps)

    def test_recent_survives_a_corrupt_file(self):
        (self.cache / 'recent.json').write_text('{not json')
        backend.recent('a')
        self.assertEqual(json.loads((self.cache / 'recent.json').read_text()), ['a'])

    def test_set_option_only_accepts_known_switches(self):
        self.write_config({'tiles': {}})
        backend.set_option('dockMono', 'true')
        backend.set_option('menuHint', 'false')
        backend.set_option('tiles', 'true')
        backend.set_option('evil', 'true')
        config = self.read_config()
        self.assertIs(config['dockMono'], True)
        self.assertIs(config['menuHint'], False)
        self.assertIsInstance(config['tiles'], dict)
        self.assertNotIn('evil', config)

    def test_set_option_choices_take_only_their_values(self):
        self.write_config({'tiles': {}})
        backend.set_option('clock', '12')
        backend.set_option('units', 'metric')
        self.assertEqual((self.read_config()['clock'], self.read_config()['units']), ('12', 'metric'))
        for name, bad in [('clock', '13'), ('clock', 'true'), ('units', 'kelvin'), ('units', '')]:
            backend.set_option(name, bad)
        self.assertEqual((self.read_config()['clock'], self.read_config()['units']), ('12', 'metric'))

    def test_set_option_desks_is_a_clamped_number(self):
        self.write_config({'tiles': {}})
        backend.set_option('desks', '2')
        self.assertEqual(self.read_config()['desks'], 2)
        backend.set_option('desks', '7')
        self.assertEqual(self.read_config()['desks'], 3)
        for bad in ('0x1', '-1', 'true', ''):
            backend.set_option('desks', bad)
        self.assertEqual(self.read_config()['desks'], 3)
        backend.set_option('desks', '0')
        self.assertEqual(self.read_config()['desks'], 1)

PROBE_OUT = '''os=Arch Linux
who=me@box
host=ACME Laptop
kernel=6.1.0
packages=812
shell=bash 5.2
cpuName=Some CPU
stat1=cpu  100 0 100 800 0 0 0 0
stat2=cpu  200 0 150 850 0 0 0 0
uptime=93784.55
memTotal=8000000000
memAvail=2000000000
disk=1000 250
temp=45000
battery=80 Discharging
tailscale=active 100.64.1.2
@@units
0\tweb.service\tactive\trunning
0\tweb2.service\tfailed\tfailed
1\tgone.service\tinactive\tdead
@@docker
web\trunning\tUp 2 hours
db\texited\tExited (0) 3 days ago
@@failed
bad.service
worse.service
'''

class ProbeParseTests(Base):
    SPEC = [{'label': 'Web', 'unit': 'web*.service', 'user': False}, {'unit': 'gone.service'}, {'unit': 'none.service'}]

    def parse(self, out=PROBE_OUT, spec=SPEC):
        return backend.probe_parse(out, spec)

    def test_numbers(self):
        d = self.parse()
        self.assertTrue(d['ok'])
        self.assertEqual(d['cpu'], 75.0)
        self.assertEqual(d['uptime'], '1 day, 2:03')
        self.assertEqual(d['mem'], 75.0)
        self.assertEqual(d['memTotal'], 8e9)
        self.assertEqual(d['disk'], 25.0)
        self.assertEqual(d['diskSize'], 1000)
        self.assertEqual(d['temp'], 45)
        self.assertEqual(d['battery'], {'level': 80, 'status': 'Discharging'})
        self.assertEqual((d['who'], d['os'], d['host'], d['kernel'], d['packages']), ('me@box', 'Arch Linux', 'ACME Laptop', '6.1.0', '812'))

    def test_uptime_formats(self):
        for secs, text in ((600, '0:10'), (3600, '1:00'), (172800 + 3 * 3600 + 5 * 60, '2 days, 3:05'), (86400, '1 day, 0:00')):
            self.assertEqual(self.parse('uptime=%d\n' % secs)['uptime'], text, secs)

    def test_missing_facts_are_none(self):
        d = self.parse('os=x\n', ())
        for key in ('cpu', 'mem', 'disk', 'temp', 'battery', 'tailscale'):
            self.assertIsNone(d[key], key)
        self.assertEqual((d['services'], d['containers'], d['failed']), ([], [], []))

    def test_tailscale_states(self):
        self.assertIsNone(self.parse('os=x\n')['tailscale'])
        self.assertEqual(self.parse('tailscale=inactive \n')['tailscale'], '')
        self.assertEqual(self.parse('tailscale=active \n')['tailscale'], '')
        self.assertEqual(self.parse('tailscale=active 100.1.2.3\n')['tailscale'], '100.1.2.3')
        self.assertEqual(self.parse(PROBE_OUT)['tailscale'], '100.64.1.2')

    def test_services_counts(self):
        s = self.parse()['services']
        self.assertEqual(s, [{'label': 'Web', 'running': 1, 'units': 2},
                             {'label': 'gone.service', 'running': 0, 'units': 1},
                             {'label': 'none.service', 'running': 0, 'units': 0}])

    def test_containers_and_failed(self):
        d = self.parse()
        self.assertEqual(d['containers'], [{'name': 'web', 'up': True, 'status': 'Up 2 hours'},
                                           {'name': 'db', 'up': False, 'status': 'Exited (0) 3 days ago'}])
        self.assertEqual(d['failed'], ['bad.service', 'worse.service'])

    def test_battery_without_status(self):
        self.assertEqual(self.parse('battery=55\n')['battery'], {'level': 55, 'status': ''})
        self.assertIsNone(self.parse('battery=x y\n')['battery'])

class ServicesTests(Base):
    def test_rejects_bad_units_and_caps_at_six(self):
        spec = [{'unit': 'ok.service'}, {'unit': 'a b'}, {'unit': 'x;y'}, {'unit': '$(id)'}, {'unit': ''}, {'unit': 5},
                'str', None, {'label': 'L' * 60, 'unit': 'a@b.service', 'user': False}]
        out = backend.services(spec)
        self.assertEqual([s['unit'] for s in out], ['ok.service', 'a@b.service'])
        self.assertEqual(out[0], {'label': 'ok.service', 'unit': 'ok.service', 'user': True})
        self.assertEqual(len(out[1]['label']), 40)
        self.assertIs(out[1]['user'], False)
        self.assertEqual(len(backend.services([{'unit': 'u%d' % i} for i in range(10)])), 6)
        self.assertEqual(backend.services('nope'), [])
        self.assertEqual(backend.services(None), [])

    def test_probe_script_quotes_units_and_picks_scope(self):
        script = backend.probe_script([{'unit': 'a*.service', 'user': False}, {'unit': 'b.service'}])
        self.assertIn("systemctl list-units --all --no-legend --plain 'a*.service'", script)
        self.assertIn("systemctl --user list-units --all --no-legend --plain b.service", script)
        self.assertNotIn('x;y', backend.probe_script([{'unit': 'x;y'}]))
        self.assertTrue(script.startswith(backend.PROBE))
        self.assertTrue(script.endswith(backend.PROBE_TAIL))

class SshTests(Base):
    def test_ssh_host_validation(self):
        for good in ('hp', 'me@box.local', 'user@100.64.0.1', 'a_b-c:22'):
            self.assertEqual(backend.ssh_host(good), good)
        for bad in ('-oProxyCommand=x', '-v', 'a b', 'a;b', 'a\nb', '$(x)', '', None, 5, 'a|b', 'a`b`'):
            self.assertEqual(backend.ssh_host(bad), '', repr(bad))

    def test_ssh_base(self):
        base = backend.ssh_base('me@box', 5)
        self.assertEqual(base[0], 'ssh')
        self.assertEqual(base[-1], 'me@box')
        joined = ' '.join(base)
        for needle in ('BatchMode=yes', 'ConnectTimeout=5', 'ControlMaster=auto', 'ControlPersist=6m'):
            self.assertIn(needle, joined)
        self.assertTrue(any(a.startswith('ControlPath=' + str(self.cache)) for a in base))
        self.assertIn('ConnectTimeout=8', backend.ssh_base('h'))

class ProbeTests(Base):
    def test_remote_without_host_keeps_old_fields(self):
        self.write_config({'tiles': {}, 'remote': {'host': '-oBad'}})
        (self.cache / 'remote.json').write_text(json.dumps({'ok': True, 'os': 'Arch', 'cpu': 3.0}))
        backend.probe('remote')
        data = json.loads((self.cache / 'remote.json').read_text())
        self.assertIs(data['ok'], False)
        self.assertEqual((data['os'], data['cpu']), ('Arch', 3.0))
        self.assertIn('error', data)
        self.run_mock.assert_not_called()

    def test_remote_with_host_runs_ssh_with_script_on_stdin(self):
        spec = [{'unit': 'web.service'}]
        self.write_config({'tiles': {}, 'remote': {'host': 'me@box', 'services': spec}})
        self.sub(done(PROBE_OUT))
        backend.probe('remote')
        args, kwargs = self.run_mock.call_args
        self.assertEqual(args[0], backend.ssh_base('me@box', 5) + ['bash -s'])
        self.assertEqual(kwargs['input'], backend.probe_script(spec))
        data = json.loads((self.cache / 'remote.json').read_text())
        self.assertTrue(data['ok'])
        self.assertEqual(data['cpu'], 75.0)
        self.assertEqual(data['updatedAt'], data['seenAt'])
        self.assertEqual(data['services'][0]['units'], 2)

    def test_remote_failure_keeps_cache_and_throttle_blocks_a_second_call(self):
        self.write_config({'tiles': {}, 'remote': {'host': 'box'}})
        (self.cache / 'remote.json').write_text(json.dumps({'ok': True, 'os': 'Arch', 'seenAt': 5}))
        self.sub(done('', 'ssh: Could not resolve hostname box', 255))
        backend.probe('remote')
        data = json.loads((self.cache / 'remote.json').read_text())
        self.assertEqual((data['ok'], data['os'], data['seenAt']), (False, 'Arch', 5))
        self.assertIn('resolve', data['error'])
        backend.probe('remote')
        self.assertEqual(self.run_mock.call_count, 1)  # throttled
        (self.cache / 'remote.attempt').unlink()
        backend.probe('remote')
        self.assertEqual(self.run_mock.call_count, 2)

    def test_remote_timeout_is_handled(self):
        self.write_config({'tiles': {}, 'remote': {'host': 'box'}})
        self.run_mock.side_effect = subprocess.TimeoutExpired('ssh', 25)
        backend.probe('remote')
        self.assertIs(json.loads((self.cache / 'remote.json').read_text())['ok'], False)

    def test_local_probe_uses_bash_stdin(self):
        self.write_config({'tiles': {}, 'local': {'services': [{'unit': 'x.service'}]}})
        self.sub(done(PROBE_OUT))
        backend.probe('local')
        args, kwargs = self.run_mock.call_args
        self.assertEqual(args[0], ['bash', '-s'])
        self.assertIn('x.service', kwargs['input'])
        self.assertTrue(json.loads((self.cache / 'local.json').read_text())['ok'])

AGENT_OUT = {
    'grok': 'hi\n',
    'claude': '{"result":"hi","session_id":"s1"}',
    'codex': '{"type":"thread.started","thread_id":"ab-12"}\n{"type":"item.completed","item":{"type":"agent_message","text":"hi"}}',
    'hermes': '{"type":"result","session_id":"2026_x1","text":"hi"}',
}

class ChatTests(Base):
    def log(self, agent):
        return json.loads((self.cache / 'chat' / agent / 'log.json').read_text())

    def session_file(self, agent):
        return self.cache / 'chat' / agent / 'session'

    def test_ask_local_sends_prompt_on_stdin_only(self):
        secret = '--force "secret"; $(id)'
        for agent, out in AGENT_OUT.items():
            self.write_config({'tiles': {}})
            self.sub(done(out))
            _, code = self.call(backend.ask, agent, secret)
            self.assertIsNone(code, agent)
            args, kwargs = self.run_mock.call_args
            self.assertEqual(args[0][:2], ['bash', '-lc'], agent)
            self.assertEqual(len(args[0]), 3, agent)
            self.assertNotIn('secret', ' '.join(args[0]), agent)
            self.assertEqual(kwargs['input'], secret, agent)
            self.assertIn('exec ', args[0][2], agent)
            self.assertTrue(self.session_file(agent).read_text(), agent)

    def test_the_cli_reads_a_chat_turn_from_stdin_never_argv(self):
        # Other local users can read a running process's arguments, so the prompt is never one.
        home = Path(self.tmp.name) / 'clihome'
        home.mkdir()
        env = {'HOME': str(home), 'PATH': '/usr/bin:/bin', 'XDG_CACHE_HOME': str(home / '.cache'),
               'XDG_CONFIG_HOME': str(home / '.config')}
        result = REAL_RUN([sys.executable, '-I', '-B', str(ROOT / 'backend.py'), 'ask', 'claude', 'from-argv'],
                          input=json.dumps('line one\nfrom "stdin"') + '\n', capture_output=True, text=True,
                          env=env, timeout=60)
        logs = list(home.rglob('log.json'))
        self.assertEqual(len(logs), 1, result.stderr)
        log = json.loads(logs[0].read_text())
        self.assertEqual(log[0]['text'], 'line one\nfrom "stdin"')
        self.assertNotIn('from-argv', logs[0].read_text())

    def test_stdin_text_is_one_json_string_line_capped(self):
        for raw, want in (('"hi\\nthere"\n', 'hi\nthere'), ('not json\n', ''), ('42\n', ''), ('', ''),
                          (json.dumps('x' * (backend.TEXT_MAX + 10)) + '\n', 'x' * backend.TEXT_MAX)):
            with patch.object(backend.sys, 'stdin', io.StringIO(raw)):
                self.assertEqual(backend.stdin_text(), want, repr(raw[:20]))

    def test_an_empty_turn_sends_nothing(self):
        self.write_config({'tiles': {}})
        _, code = self.call(backend.ask, 'claude', '   ')
        self.assertEqual(code, 1)
        self.run_mock.assert_not_called()

    def test_the_desk_sends_private_text_over_stdin(self):
        qml = (ROOT / 'Service.qml').read_text()
        self.assertIn('runWith(p, ["ask", agent], text.trim())', qml)
        self.assertIn('runWith(createProc, ["create", String(root.page)], createInput.text.trim())', qml)
        self.assertNotRegex(qml, r'run\(\w+, \["(ask|create)", [^\]]*(text|createInput)')

    def test_ask_remote_runs_ssh_base_plus_line(self):
        self.write_config({'tiles': {}, 'chat': {'host': 'me@box'}})
        self.sub(done(AGENT_OUT['claude']))
        self.call(backend.ask, 'claude', 'hello')
        args, kwargs = self.run_mock.call_args
        line = backend.wrap('claude', backend.turn_command('claude', '', {}))
        self.assertEqual(args[0], backend.ssh_base('me@box') + [line])
        self.assertEqual(kwargs['input'], 'hello')

    def test_ask_with_unsafe_host_runs_locally(self):
        self.write_config({'tiles': {}, 'chat': {'host': '-oProxyCommand=x'}})
        self.sub(done(AGENT_OUT['claude']))
        self.call(backend.ask, 'claude', 'hello')
        self.assertEqual(self.run_mock.call_args.args[0][:2], ['bash', '-lc'])

    def test_turn_commands_stay_read_only(self):
        c = backend.turn_command('claude', '', {})
        self.assertIn('--tools WebSearch,WebFetch', c)
        self.assertNotIn('--resume', c)
        self.assertIn('--resume s1', backend.turn_command('claude', 's1', {}))
        c = backend.turn_command('codex', '', {})
        self.assertIn('-s read-only', c)
        self.assertTrue(c.endswith(' -'))
        c = backend.turn_command('codex', 'ab-12', {})
        self.assertIn('sandbox_mode="read-only"', c)
        self.assertIn('resume', c)
        self.assertIn('ab-12', c)
        c = backend.turn_command('grok', '', {})
        for flag in ('--tools web_search', '--permission-mode dontAsk', '--disallowed-tools search_tool,use_tool', '--prompt-file /dev/stdin'):
            self.assertIn(flag, c)
        self.assertNotIn(' -c', c)
        self.assertIn(' -c', backend.turn_command('grok', 'continue', {}))
        c = backend.turn_command('hermes', '', {})
        self.assertIn('--query-file /dev/stdin', c)
        self.assertTrue(c.startswith('hermes chat'))
        with self.assertRaises(ValueError):
            backend.turn_command('nope', '', {})

    def test_no_turn_command_has_dangerous_flags(self):
        for agent in backend.AGENTS:
            c = backend.turn_command(agent, 'abc', {'hermes': {'profile': 'x'}})
            for bad in ('--dangerously', 'bypass', 'danger-full-access', '--yolo', 'acceptEdits'):
                self.assertNotIn(bad, c, agent)

    def test_hermes_profile(self):
        self.assertIn('hermes -p x chat', backend.turn_command('hermes', '', {'hermes': {'profile': 'x'}}))
        self.assertNotIn(' -p ', backend.turn_command('hermes', '', {}))
        self.assertNotIn(' -p ', backend.turn_command('hermes', '', {'hermes': {'profile': 'x; y'}}))
        self.assertIn('--resume 2026_x1', backend.turn_command('hermes', '2026_x1', {}))
        self.assertIn(' -p x', backend.app_command('hermes', '', {'hermes': {'profile': 'x'}}))

    def test_success_writes_session_and_log(self):
        self.write_config({'tiles': {}})
        self.sub(done(AGENT_OUT['claude']))
        self.call(backend.ask, 'claude', '  what is up  ')
        self.assertEqual(self.session_file('claude').read_text(), 's1')
        log = self.log('claude')
        self.assertEqual([(e['who'], e['text']) for e in log], [('you', 'what is up'), ('agent', 'hi')])
        self.assertNotIn('error', log[1])
        self.assertIsInstance(log[0]['at'], int)
        # the next turn resumes that session
        self.call(backend.ask, 'claude', 'again')
        self.assertIn('--resume s1', self.run_mock.call_args.args[0][2])
        self.assertEqual(len(self.log('claude')), 4)

    def test_codex_hermes_and_grok_replies_are_parsed(self):
        self.write_config({'tiles': {}})
        for agent, session in (('codex', 'ab-12'), ('hermes', '2026_x1'), ('grok', 'continue')):
            self.sub(done(AGENT_OUT[agent]))
            self.call(backend.ask, agent, 'q')
            self.assertEqual(self.session_file(agent).read_text(), session)
            self.assertEqual(self.log(agent)[-1]['text'], 'hi')

    def test_unsafe_session_id_is_not_stored(self):
        self.write_config({'tiles': {}})
        self.sub(done('{"result":"hi","session_id":"x; reboot"}'))
        self.call(backend.ask, 'claude', 'q')
        self.assertFalse(self.session_file('claude').exists())
        self.assertEqual(self.log('claude')[-1]['text'], 'hi')

    def failure(self, code, stderr, out='', agent='claude', config=None):
        self.write_config(config or {'tiles': {}})
        self.sub(done(out, stderr, code))
        _, exit_code = self.call(backend.ask, agent, 'q')
        self.assertEqual(exit_code, 1)
        entry = self.log(agent)[-1]
        self.assertEqual(entry['who'], 'agent')
        self.assertIs(entry['error'], True)
        self.assertTrue(entry['detail'])
        self.assertFalse(self.session_file(agent).exists())
        return entry['text']

    def test_failures_are_explained(self):
        remote = {'tiles': {}, 'chat': {'host': 'me@box', 'where': 'the box'}}
        self.assertIn("Couldn't reach the box", self.failure(255, 'ssh: connect failed', config=remote))
        self.assertIn('Claude is not installed on the box', self.failure(127, 'bash: claude: not found', config=remote))
        self.assertIn('Claude is not installed here', self.failure(127, 'bash: claude: command not found'))
        self.assertIn('installed incompletely', self.failure(1, 'Error: native binary not installed'))
        self.assertIn('not signed in', self.failure(1, 'Error: please log in first'))
        self.assertIn('rate limited', self.failure(1, 'HTTP 429 too many'))
        self.assertIn('returned no answer', self.failure(1, 'something odd'))
        self.assertTrue(self.failure(1, 'please log in', agent='codex').startswith('Codex'))

    def test_failure_detail_is_the_last_line_and_capped(self):
        self.failure(1, 'first\n' + 'z' * 500)
        entry = self.log('claude')[-1]
        self.assertEqual(len(entry['detail']), 240)
        self.assertTrue(entry['detail'].startswith('z'))

    def test_custom_agent_name_is_used(self):
        text = self.failure(127, 'x: command not found', config={'tiles': {}, 'chat': {'agents': {'claude': {'name': 'Buddy'}}}})
        self.assertTrue(text.startswith('Buddy '))

    def test_timeout_logs_an_error(self):
        self.write_config({'tiles': {}})
        self.run_mock.side_effect = subprocess.TimeoutExpired('x', 300)
        _, code = self.call(backend.ask, 'claude', 'q')
        self.assertEqual(code, 1)
        self.assertIs(self.log('claude')[-1]['error'], True)

    def test_unknown_agent_exits(self):
        _, code = self.call(backend.ask, 'bogus', 'q')
        self.assertEqual(code, 1)
        self.run_mock.assert_not_called()

    def test_retry_drops_agent_entries_and_resends_last_question(self):
        self.write_config({'tiles': {}})
        directory = self.cache / 'chat' / 'claude'
        directory.mkdir(parents=True)
        (directory / 'log.json').write_text(json.dumps([
            {'who': 'you', 'text': 'first', 'at': 1}, {'who': 'agent', 'text': 'ok', 'at': 2},
            {'who': 'you', 'text': 'second', 'at': 3},
            {'who': 'agent', 'text': 'boom', 'at': 4, 'error': True}, {'who': 'agent', 'text': 'boom2', 'at': 5, 'error': True}]))
        self.sub(done(AGENT_OUT['claude']))
        self.call(backend.ask, 'claude', '', retry=True)
        self.assertEqual(self.run_mock.call_args.kwargs['input'], 'second')
        log = self.log('claude')
        self.assertEqual([(e['who'], e['text']) for e in log],
                         [('you', 'first'), ('agent', 'ok'), ('you', 'second'), ('agent', 'hi')])

    def test_retry_with_nothing_to_resend_exits(self):
        self.write_config({'tiles': {}})
        _, code = self.call(backend.ask, 'claude', '', retry=True)
        self.assertEqual(code, 1)
        self.run_mock.assert_not_called()

    def test_log_is_capped(self):
        for i in range(backend.LOG_KEEP + 10):
            backend.log_turn('claude', 'you', str(i))
        log = self.log('claude')
        self.assertEqual(len(log), backend.LOG_KEEP)
        self.assertEqual(log[-1]['text'], str(backend.LOG_KEEP + 9))

class OpenAppTests(Base):
    def launched(self):
        return self.run_mock.call_args.args[0]

    def test_local_uses_bash_lc_in_a_terminal(self):
        self.write_config({'tiles': {}})
        self.sub(done())
        (self.cache / 'chat' / 'codex').mkdir(parents=True)
        (self.cache / 'chat' / 'codex' / 'session').write_text('ab-12')
        backend.open_app('codex')
        c = self.launched()
        self.assertEqual(c[:5], ['setsid', '-f', 'omarchy-launch-tui', '--app-id=org.omarchy.omatiles-codex', 'bash'])
        self.assertEqual(c[5], '-lc')
        self.assertTrue(c[6].endswith('exec codex resume ab-12'))

    def test_remote_uses_ssh_t(self):
        self.write_config({'tiles': {}, 'chat': {'host': 'me@box'}})
        self.sub(done())
        backend.open_app('claude')
        c = self.launched()
        self.assertEqual(c[:7], ['setsid', '-f', 'omarchy-launch-tui', '--app-id=org.omarchy.omatiles-claude', 'ssh', '-t', 'me@box'])
        self.assertTrue(c[7].endswith('exec claude'))
        self.assertEqual(len(c), 8)

    def test_unsafe_session_is_dropped_and_non_grok_continue_marker_too(self):
        self.write_config({'tiles': {}})
        self.sub(done())
        d = self.cache / 'chat' / 'codex'
        d.mkdir(parents=True)
        (d / 'session').write_text('x; reboot')
        backend.open_app('codex')
        self.assertTrue(self.launched()[6].endswith('exec codex'))
        (d / 'session').write_text('continue')
        backend.open_app('codex')
        self.assertTrue(self.launched()[6].endswith('exec codex'))
        (self.cache / 'chat' / 'grok').mkdir(parents=True)
        (self.cache / 'chat' / 'grok' / 'session').write_text('continue')
        backend.open_app('grok')
        self.assertTrue(self.launched()[6].endswith('exec grok -c'))

    def test_open_override(self):
        self.write_config({'tiles': {}, 'chat': {'agents': {'claude': {'open': 'my-claude --fast'},
                                                              'codex': {'open': 'a\nb'}, 'grok': {'open': '  '}}}})
        self.sub(done())
        backend.open_app('claude')
        self.assertTrue(self.launched()[6].endswith('exec my-claude --fast'))
        backend.open_app('codex')
        self.assertTrue(self.launched()[6].endswith('exec codex'))
        backend.open_app('grok')
        self.assertTrue(self.launched()[6].endswith('exec grok'))

    def test_launch_failure_exits_1(self):
        self.write_config({'tiles': {}})
        self.run_mock.side_effect = OSError('no setsid')
        _, code = self.call(backend.open_app, 'claude')
        self.assertEqual(code, 1)

class CompatTests(Base):
    def test_compat_marks_phone_only_widgets_and_missing_packages(self):
        (self.cache / 'store.json').write_text(json.dumps({'widgets': [
            {'id': 'a/notes', 'commands': ['read Android notifications (apps, titles and text)'], 'requires': {}},
            {'id': 'a/feeds', 'commands': ['curl x'], 'requires': {'pacman': ['curl', 'jq']}},
            {'id': 'a/plain', 'commands': [], 'requires': {'pacman': []}}, 'junk']}))
        self.sub(done('curl\nbash\n'))
        backend.compat()
        c = json.loads((self.cache / 'compat.json').read_text())
        self.assertEqual(c, {'a/notes': {'phone': True, 'missing': []}, 'a/feeds': {'phone': False, 'missing': ['jq']},
                             'a/plain': {'phone': False, 'missing': []}})

    def test_store_still_writes_compat_when_the_fetch_is_throttled(self):
        (self.cache / 'store.json').write_text(json.dumps({'widgets': [{'id': 'a/b', 'requires': {}}]}))
        (self.cache / 'store.attempt').touch()
        self.sub(done(''))
        backend.store()
        self.assertEqual(json.loads((self.cache / 'compat.json').read_text()), {'a/b': {'phone': False, 'missing': []}})
        self.assertEqual(self.run_mock.call_args[0][0], ['pacman', '-Qq'])

class TraceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def box(self, d):
        nums = [float(v) for v in __import__('re').findall(r'-?\d+(?:\.\d+)?', d)]
        xs, ys = nums[0::2], nums[1::2]
        return min(xs), max(xs), min(ys), max(ys)

    def test_a_shape_on_nothing_is_traced_from_its_transparency(self):
        f = self.dir / 'dot.png'
        png(f, 64, 64, lambda x, y: (200, 30, 30, 255) if (x - 32) ** 2 + (y - 32) ** 2 < 15 ** 2 else (0, 0, 0, 0), filt=1)
        d = icontrace.trace(f)
        self.assertTrue(d.startswith('M') and d.endswith('Z'), d[:40])
        x0, x1, y0, y1 = self.box(d)
        # centered and filling the 24 x 24 box
        self.assertAlmostEqual(x0, 0, delta=0.6); self.assertAlmostEqual(x1, 24, delta=0.6)
        self.assertAlmostEqual(y0, 0, delta=0.6); self.assertAlmostEqual(y1, 24, delta=0.6)

    def test_a_shape_on_a_tile_is_what_differs_from_the_tile(self):
        f = self.dir / 'tile.png'
        def px(x, y):
            if 22 <= x < 42 and 12 <= y < 52:
                return (20, 20, 20, 255)  # a dark bar on a white tile
            return (250, 250, 250, 255)
        png(f, 64, 64, px)
        x0, x1, y0, y1 = self.box(icontrace.trace(f))
        # the bar is twice as tall as wide: it fills the height, half the width
        self.assertAlmostEqual(y1 - y0, 24, delta=0.6)
        self.assertAlmostEqual(x1 - x0, 12, delta=1.2)

    def test_no_clear_shape_gives_nothing(self):
        empty, full, noise = self.dir / 'e.png', self.dir / 'f.png', self.dir / 'n.png'
        png(empty, 32, 32, lambda x, y: (0, 0, 0, 0))
        png(full, 32, 32, lambda x, y: (90, 90, 90, 255))
        import random
        r = random.Random(4)
        png(noise, 64, 64, lambda x, y: (r.randrange(256), r.randrange(256), r.randrange(256), 255))
        for f in (empty, full, noise):
            self.assertEqual(icontrace.trace(f), '', f.name)

    def test_not_a_png_or_too_big_raises(self):
        bad = self.dir / 'bad.png'
        bad.write_bytes(b'GIF89a')
        with self.assertRaises(ValueError):
            icontrace.read_png(bad)


class MarksTests(Base):
    def test_the_backend_never_writes_bytecode_into_the_plugin(self):
        # Omarchy reloads a plugin when a file in its folder changes; a __pycache__ would do that.
        src = (ROOT / 'backend.py').read_text()
        self.assertLess(src.index('sys.dont_write_bytecode = True'), src.index('def tracer('))

    def test_icon_names_are_looked_up_only_inside_icon_folders(self):
        apps = Path.home() / '.local/share/icons/hicolor/64x64/apps'
        apps.mkdir(parents=True)
        png(apps / 'demo.png', 4, 4, lambda x, y: (0, 0, 0, 255))
        big = Path.home() / '.local/share/icons/hicolor/256x256/apps'
        big.mkdir(parents=True)
        png(big / 'demo.png', 4, 4, lambda x, y: (0, 0, 0, 255))
        with patch.dict(os.environ, {'XDG_DATA_DIRS': str(Path(self.tmp.name) / 'none')}):
            self.assertEqual(backend.icon_png('demo'), big / 'demo.png')
            for bad in ('../demo', 'a/b', 'demo\n', '', '.' * 300):
                self.assertIsNone(backend.icon_png(bad), repr(bad))

    def test_marks_are_cached_by_file_and_skip_unknown_icons(self):
        apps = Path.home() / '.local/share/icons/hicolor/64x64/apps'
        apps.mkdir(parents=True)
        png(apps / 'dot.png', 64, 64, lambda x, y: (9, 9, 9, 255) if (x - 32) ** 2 + (y - 32) ** 2 < 200 else (0, 0, 0, 0))
        with patch.dict(os.environ, {'XDG_DATA_DIRS': str(Path(self.tmp.name) / 'none')}):
            backend.marks(['dot', 'missing', 7])
            first = json.loads((self.cache / 'marks.json').read_text())
            self.assertEqual(list(first), ['dot'])
            self.assertTrue(first['dot']['path'].startswith('M'))
            with patch.object(backend, 'tracer', side_effect=AssertionError('traced again')):
                backend.marks(['dot'])
            self.assertEqual(json.loads((self.cache / 'marks.json').read_text()), first)


class MiscTests(Base):
    def test_new_chat_removes_session_and_log(self):
        d = self.cache / 'chat' / 'claude'
        d.mkdir(parents=True)
        (d / 'session').write_text('s'); (d / 'log.json').write_text('[]')
        other = self.cache / 'chat' / 'codex'
        other.mkdir(parents=True)
        (other / 'session').write_text('s')
        backend.new_chat('claude')
        self.assertFalse((d / 'session').exists())
        self.assertFalse((d / 'log.json').exists())
        self.assertTrue((other / 'session').exists())
        backend.new_chat('claude')  # nothing left: no error
        backend.new_chat('../../etc')

    def test_agents_here_writes_a_bool_per_agent(self):
        with patch.object(backend.shutil, 'which', side_effect=lambda n: '/usr/bin/' + n if n in ('claude', 'grok') else None):
            backend.agents_here()
        found = json.loads((self.cache / 'agents.json').read_text())
        self.assertEqual(found, {'claude': True, 'codex': False, 'grok': True, 'hermes': False})
        for v in found.values():
            self.assertIsInstance(v, bool)

    def test_agents_here_sees_local_bin(self):
        home = backend.Path.home()
        (home / '.local/bin').mkdir(parents=True)
        (home / '.local/bin/codex').write_text('')
        with patch.object(backend.shutil, 'which', return_value=None):
            backend.agents_here()
        self.assertEqual(json.loads((self.cache / 'agents.json').read_text())['codex'], True)

    def test_init_creates_config_once_and_never_overwrites(self):
        with patch.object(backend.shutil, 'which', return_value=None):
            backend.init('{"first": 1}')
            self.assertEqual(self.read_config(), {'first': 1})
            backend.init('{"second": 2}')
            self.assertEqual(self.read_config(), {'first': 1})
        self.assertTrue((self.cache / 'agents.json').exists())

    def test_init_prunes_old_trash(self):
        old = self.trash / 'a__old'
        old.mkdir(parents=True)
        age = time.time() - 3 * 86400
        os.utime(old, (age, age))
        with patch.object(backend.shutil, 'which', return_value=None):
            backend.init('{}')
        self.assertFalse(old.exists())

    def test_load_config_tolerates_garbage(self):
        (self.config / backend.CONFIG_FILE).write_text('[1,2]')
        self.assertEqual(backend.load_config(), {'tiles': {}, 'grid': 16})
        (self.config / backend.CONFIG_FILE).write_text('{"tiles": 5}')
        self.assertEqual(backend.load_config()['tiles'], {})
        (self.config / backend.CONFIG_FILE).unlink()
        self.assertEqual(backend.load_config()['tiles'], {})

    def test_owl_sizes(self):
        self.assertEqual(backend.owl_sizes('size: 6x4\nminSize: 3 x 2'), ((6, 4), (3, 2)))
        self.assertEqual(backend.owl_sizes('  size: 5x3'), ((5, 3), (3, 2)))
        self.assertEqual(backend.owl_sizes('nothing'), ((4, 4), (2, 2)))

PRIVATE_WORDS = ROOT / 'tests' / 'private-words.txt'

class GuardTests(unittest.TestCase):
    """Nothing that ships names a real person, machine, account or network.

    The patterns catch the shapes private data takes, in every text file, this one included.
    Words only you would know (your name, user, hosts, city, projects) go one per line in
    tests/private-words.txt, which git ignores, or comma-separated in OMATILES_PRIVATE_WORDS:
    the guard checks every file for them without the repository ever naming them."""
    # (what, pattern, placeholder the repo may use)
    PATTERNS = [
        # Tailscale's 100.64.0.0/10; 100.64.0.x and 100.64.1.x are the placeholders.
        ('tailnet address', r'\b100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}\b', r'100\.64\.[01]\.\d{1,3}'),
        ('private address', r'\b(?:10\.\d{1,3}|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b', None),
        ('home path', r'/home/[A-Za-z0-9._-]+', r'/home/(?:user|you)'),
        # Systemd units (a@b.service) and ssh hosts (me@box.local) look like addresses too.
        ('email', r'[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}',
         r'.*@(?:[\w-]+\.)*(?:example\.(?:com|org|net)|[\w-]+\.(?:service|socket|timer|target|local|lan|internal))'),
        ('chat id', r'(?i)\b(?:chat|telegram|tg|peer|user)[ _-]?id\b\W{0,6}-?\d{6,}', None),
        ('bot token', r'\b\d{8,10}:[A-Za-z0-9_-]{35}\b', None),
        ('api token', r'\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_\w{22,}|sk-(?:ant-)?[A-Za-z0-9_-]{20,}'
                      r'|xox[abprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{35}|GOCSPX-[A-Za-z0-9_-]{20,})', None),
        # [ ] keeps the phrase itself out of this file (tests/check.sh looks for it).
        ('private key', r'-----BEGIN [A-Z ]*PRIVATE[ ]KEY-----', None),
    ]

    @staticmethod
    def private_words():
        words = [w for w in os.environ.get('OMATILES_PRIVATE_WORDS', '').split(',')]
        try:
            words += PRIVATE_WORDS.read_text().splitlines()
        except OSError:
            pass
        return sorted({w.strip().lower() for w in words if w.strip() and not w.strip().startswith('#')})

    def leaks(self, text):
        out = []
        for what, pattern, placeholder in self.PATTERNS:
            for m in re.finditer(pattern, text):
                if not (placeholder and re.fullmatch(placeholder, m.group(0))):
                    out.append((what, m.group(0)))
        return out

    def test_no_personal_data_in_the_plugin(self):
        words, hits = self.private_words(), []
        for path in sorted(ROOT.rglob('*')):
            parts = path.relative_to(ROOT).parts
            # Everything that ships, vendored files included.
            if not path.is_file() or path == PRIVATE_WORDS or '.git' in parts or '.impeccable' in parts or '__pycache__' in parts:
                continue
            raw = path.read_bytes()
            for n, line in enumerate(raw.decode('utf-8', 'ignore').splitlines(), 1):
                low = line.lower()
                hits += ['%s:%d: [a private word] %s' % ('/'.join(parts), n, line.strip()[:100]) for w in words if w in low]
                # Patterns read text only: compressed bytes in a jar look like addresses by chance.
                if b'\0' not in raw:
                    hits += ['%s:%d: [%s] %s' % ('/'.join(parts), n, what, found) for what, found in self.leaks(line)]
        self.assertEqual(hits, [], '\n' + '\n'.join(hits))

    def test_the_patterns_catch_what_they_are_for(self):
        # Built from pieces, so this file holds none of them whole.
        caught = {
            'tailnet address': '100.' + '101.20.30', 'private address': '192.' + '168.4.20',
            'home path': '/home' + '/someone/.config', 'email': 'someone' + '@' + 'mail.test',
            'chat id': 'chat_' + 'id: 12345678', 'bot token': '12345678' + ':' + 'A' * 35,
            'api token': 'gh' + 'p_' + 'a' * 36, 'private key': '-----BEGIN OPENSSH PRIVATE' + ' KEY-----',
        }
        for what, text in caught.items():
            self.assertIn(what, [w for w, _ in self.leaks(text)], what)
        for placeholder in ['100.64.1.2', '/home/user/x', 'a@b.service', 'me@box.local', 'you@example.com']:
            self.assertEqual(self.leaks(placeholder), [], placeholder)

if __name__ == '__main__':
    unittest.main()
