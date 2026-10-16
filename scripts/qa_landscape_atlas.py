"""Run the bounded real-browser integration procedure through Playwright CLI.

Open the local app and read a fresh CLI snapshot first. Pass the installed
playwright-cli.js path with --cli; this runner never installs a browser. It
reuses thirteen declared screenshot paths and writes only a staging QA JSON.
Inspect those images before calling seal_landscape_atlas.py.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
STAGE = Path('/tmp/taihu-full')
JS = ROOT / 'scripts/qa_landscape_atlas.js'
SOURCE_PATHS = [
    'src/CampusAtlas.jsx', 'src/campusAtlas.css', 'src/App.jsx', 'src/styles.css',
    'scripts/export_atlas_places.py', 'scripts/campus_expansion.py',
    'scripts/landscape_beds.py', 'scripts/courtyard_finish.py',
    'scripts/landscape_surface.py', 'scripts/facade_finish.py',
    'scripts/hardscape_transition.py', 'scripts/planting_finish.py',
    'scripts/paving_cleanup.py', 'scripts/context_roads.py', 'scripts/campus_expansion_export.py',
    'scripts/promote_full_atlas.py', 'scripts/verify_landscape_atlas.py',
    'scripts/promote_north_pilot.py', 'scripts/seal_landscape_atlas.py',
    'scripts/compare_landscape_atlas.py', 'scripts/qa_landscape_atlas.js',
    'scripts/qa_landscape_atlas.py',
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cli', required=True, type=Path)
    parser.add_argument('--node', default='/usr/local/bin/node')
    parser.add_argument('--session', default='atlas-services')
    args = parser.parse_args()
    assert args.cli.is_file() and STAGE.is_dir()
    evidence = ROOT / 'output/playwright'
    assert sum(path.stat().st_size for path in evidence.rglob('*') if path.is_file()) + 12*1024**2 < 192*1024**2
    assert sum(path.stat().st_size for path in STAGE.rglob('*') if path.is_file()) + 1024**2 < 192*1024**2
    meta = json.loads((ROOT / 'public/assets/campus-atlas.json').read_bytes())
    assert len(meta['sources']) == 33
    for path, expected in meta['sources'].items():
        assert sha(ROOT / path) == expected, path
    source_hashes = {path: sha(ROOT / path) for path in SOURCE_PATHS}
    script = JS.read_text().replace("'__PROJECT_ROOT__'", json.dumps(str(ROOT) + '/'))
    assert '__PROJECT_ROOT__' not in script
    result = subprocess.run([args.node, str(args.cli), '-s=' + args.session,
                             'run-code', script], cwd='/private/tmp',
                            capture_output=True, text=True, timeout=480)
    if result.returncode:
        raise RuntimeError(result.stdout[-8000:] + result.stderr[-2000:])
    assert '### Result\n' in result.stdout, result.stdout[-4000:]
    qa, _ = json.JSONDecoder().raw_decode(result.stdout.split('### Result\n', 1)[1].lstrip())
    assert qa['status'] == 'passed' and not qa['errors']
    assert qa['image_sha256'] == meta['image_sha256'] and qa['source_hashes'] == meta['sources']
    assert len(qa['captures']) == 13
    for record in qa['captures']:
        path = ROOT / record['path']
        assert path.parent == ROOT / 'output/playwright' and path.is_file()
        record.update(sha256=sha(path), bytes=path.stat().st_size)
    assert source_hashes == {path: sha(ROOT / path) for path in SOURCE_PATHS}
    qa.update(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        source_sha256=source_hashes, script_source=script,
        script_sha256=hashlib.sha256(script.encode()).hexdigest(),
        capture_method='Pinned installed Playwright CLI; fresh local app navigation, actual drag and zoom controls; explicit image inspection pending',
        criteria=[record['criterion'] for record in qa['captures']],
        budget={'capture_limit': 14, 'capture_bytes_limit': 12 * 1024**2,
                'source_amplification_limit': 256, 'source_basis': SOURCE_PATHS})
    payload = (json.dumps(qa, ensure_ascii=False, separators=(',', ':')) + '\n').encode()
    assert sum(path.stat().st_size for path in STAGE.rglob('*') if path.is_file()) + len(payload) < 192*1024**2
    (STAGE / 'iteration-qa.json').write_bytes(payload)
    print(json.dumps({'status': qa['status'], 'captures': len(qa['captures']),
        'image_sha256': qa['image_sha256'], 'checks': qa['checks'],
        'note': 'Inspect all captures, then seal; this staging result is not visual approval'}))


if __name__ == '__main__':
    main()
