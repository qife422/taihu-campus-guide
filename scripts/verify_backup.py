"""Hash-check a project checkout, or refresh its manifest from staged Git files."""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'backup-manifest.json'
MAX_FILES = 250
MAX_BYTES = 320 * 1024**2
MAX_FILE_BYTES = 50 * 1024**2
EXCLUDED = ('node_modules/', 'dist/', '.playwright-cli/', '.git/', '__pycache__/', '.codex/', '.claude/')
REQUIRED = {
    'README.md', '恢复说明.md', '.gitignore', '.gitattributes',
    'package.json', 'package-lock.json', 'vite.config.js', 'index.html',
    'src/App.jsx', 'src/main.jsx', 'src/CampusAtlas.jsx',
    'model/campus/campus.blend', 'model/campus/campus.glb',
    'model/campus/manifest.json', 'model/campus/layout.json',
    'model/central-campus/central-campus.blend', 'model/study/campus.blend',
    'public/assets/campus-atlas.json', 'public/assets/campus-atlas.webp',
    'public/assets/draco/draco_decoder.wasm', 'public/assets/draco/draco_wasm_wrapper.js',
    'output/garden-tree-canopy.png', 'output/playwright/landscape.json',
    'output/playwright/landscape.md', 'scripts/verify_backup.py',
}


def sha(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024**2), b''):
            result.update(block)
    return result.hexdigest()


def safe_path(name):
    parts = PurePosixPath(name)
    if parts.is_absolute() or '..' in parts.parts or not parts.parts:
        raise ValueError(f'Unsafe project path: {name}')
    if any(name.startswith(value) for value in EXCLUDED) or '__pycache__' in parts.parts:
        raise ValueError(f'Cache is not a recovery input: {name}')
    basename = parts.name
    if (basename == '.env' or basename.startswith('.env.')
            or basename in {'.npmrc', '.netrc', '.git-credentials'}
            or parts.suffix.lower() in {'.pem', '.key', '.p12', '.pfx'}):
        if not basename.endswith('.example'):
            raise ValueError(f'Local credential path: {name}')
    path = ROOT / name
    if path.is_symlink() or ROOT not in path.resolve().parents:
        raise ValueError(f'Non-project file: {name}')
    return path


def check_limits(rows):
    if not rows or len(rows) > MAX_FILES or sum(row['bytes'] for row in rows) > MAX_BYTES:
        raise ValueError('Backup scope exceeds declared file/byte budget')
    if any(row['bytes'] > MAX_FILE_BYTES for row in rows):
        raise ValueError('Single file exceeds declared 50 MiB upload budget')
    if len({row['path'] for row in rows}) != len(rows):
        raise ValueError('Duplicate backup paths')


def check_scope(rows):
    names = {row['path'] for row in rows}
    required = set(REQUIRED)
    meta = json.loads((ROOT / 'public/assets/campus-atlas.json').read_text())
    qa = json.loads((ROOT / 'output/playwright/landscape.json').read_text())
    if not meta['sources'] or not qa['captures']:
        raise ValueError('Missing native-source or QA recovery scope')
    required.update(meta['sources'])
    required.update(row['path'] for row in qa['captures'])
    required.update(row['path'] for row in qa['native_comparison']['artifacts'])
    missing = required - names
    if missing:
        raise ValueError('Required recovery inputs absent: ' + ', '.join(sorted(missing)))


def refresh():
    result = subprocess.run(['git', 'ls-files', '-s', '-z'], cwd=ROOT,
                            check=True, capture_output=True).stdout
    records = []
    for item in result.split(b'\0'):
        if not item:
            continue
        header, raw_name = item.split(b'\t', 1)
        mode, object_id, stage = header.decode().split()
        name = raw_name.decode('utf-8')
        if name == MANIFEST.name:
            continue
        if stage != '0' or mode not in {'100644', '100755'}:
            raise ValueError(f'Unsupported index entry: {name}')
        path = safe_path(name)
        current_git_id = subprocess.run(['git', 'hash-object', '--no-filters', '--', name],
            cwd=ROOT, check=True, text=True, capture_output=True).stdout.strip()
        if current_git_id != object_id:
            raise ValueError(f'Staged bytes differ from disk; git add first: {name}')
        records.append({'path': name, 'bytes': path.stat().st_size,
                        'sha256': sha(path), 'git_blob_sha1': object_id})
    records.sort(key=lambda row: row['path'])
    check_limits(records)
    check_scope(records)
    value = {'schema_version': 1, 'project_name': '太湖校园导览 Demo',
        'repository': 'https://github.com/qife422/taihu-campus-guide',
        'branch': 'source', 'method': 'SHA-256 of every staged project file except this self-referential manifest; staged Git blob IDs included',
        'scope': 'Source, original models/imagery, web assets, all retained output records and project documentation; no dependencies, build replicas, browser caches or credentials',
        'excluded_directories': list(EXCLUDED),
        'limits': {'files': MAX_FILES, 'bytes': MAX_BYTES, 'single_file_bytes': MAX_FILE_BYTES},
        'file_count': len(records), 'file_bytes': sum(row['bytes'] for row in records),
        'files': records}
    MANIFEST.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': 'manifest_refreshed', 'files': len(records),
                     'bytes': value['file_bytes']}, ensure_ascii=False))


def verify():
    value = json.loads(MANIFEST.read_text())
    records = value['files']
    check_limits(records)
    check_scope(records)
    if value['file_count'] != len(records) or value['file_bytes'] != sum(row['bytes'] for row in records):
        raise ValueError('Manifest totals differ from file records')
    errors = []
    for record in records:
        path = safe_path(record['path'])
        if not path.is_file() or path.stat().st_size != record['bytes'] or sha(path) != record['sha256']:
            errors.append(record['path'])
    if errors:
        raise ValueError('Missing or changed backup files: ' + ', '.join(errors))
    print(json.dumps({'status': 'passed', 'files': len(records),
                     'bytes': value['file_bytes']}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh', action='store_true', help='Create manifest from staged Git files')
    args = parser.parse_args()
    refresh() if args.refresh else verify()


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
