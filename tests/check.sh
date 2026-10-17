#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -I - <<'PY'
import json
from pathlib import Path
m=json.loads(Path('manifest.json').read_text())
assert m['schemaVersion']==1 and m['id']=='io.github.pow3r-droid.omatiles'
assert m['kinds']==['service'] and m['keepLoaded'] is True
assert m['entryPoints']=={'service':'Service.qml'}
for p in ['Service.qml','Tile.qml','SevenSeg.qml','SysInfo.qml','ChatTile.qml','Label.qml','Action.qml','Field.qml','Glyphs.js','Brands.js','icontrace.py','Config.js','Ui.js','backend.py','gcal.py','calendar/Model.js','owl/OwlWidget.qml','owl/Owl.js','owl/LICENSE','README.md','CHANGELOG.md','LICENSE']:
    assert Path(p).is_file(), p
readme=Path('README.md').read_text()
assert 'not affiliated with or endorsed by' in readme
assert 'Removal' in readme
for p in Path('.').rglob('*'):
    if not p.is_file() or 'ref' in p.parts or '.git' in p.parts or '__pycache__' in p.parts: continue
    if p.suffix.lower() in ['.png','.jpg','.jpeg','.svg','.webp','.ico']:
        assert p.as_posix()=='preview.png', p   # one preview at the root, no other binary assets
    if p.suffix in ['.qml','.js','.py']:
        text=p.read_text()
        assert 'ref/' not in text, p
        assert 'calendar.google.com' not in text, p
        assert 'PRIVATE KEY' not in text, p
compile(Path('backend.py').read_text(),'backend.py','exec')
compile(Path('gcal.py').read_text(),'gcal.py','exec')
print('Manifest, sources and safety checks passed')
PY
node --test tests/model.test.cjs
python3 -I tests/backend_test.py
if command -v omarchy >/dev/null 2>&1; then
  omarchy plugin validate .
else
  echo 'Omarchy unavailable: skipped plugin validator (requires installed runtime)'
fi
