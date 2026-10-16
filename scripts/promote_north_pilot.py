"""Promote the reviewed north pilot into the existing web sample paths.

The shared 10-asset budget is checked before any output is replaced. Run with
--seal after adding browser QA to campus-north.json to refresh the current
shared-asset manifest in campus-atlas.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'public/assets'
PILOT = ROOT / 'output'
LIMIT = 8 * 1024**2
NORTH_FILES = ('campus-north.webp', 'campus-north-before.webp', 'campus-north.json')


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def encoded(value: dict) -> bytes:
    if value.get('coverage') == 'campus':
        return (json.dumps(value, ensure_ascii=False, separators=(',', ':')) + '\n').encode()
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def replace(path: Path, data: bytes) -> None:
    # The temporary file is outside the bounded asset directory.
    with tempfile.NamedTemporaryFile(prefix='taihu-north-', dir='/tmp', delete=False) as item:
        item.write(data)
        temporary = Path(item.name)
    try:
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def validate_pilot() -> tuple[dict, dict[str, bytes]]:
    meta_bytes = (PILOT / 'north-pilot.json').read_bytes()
    meta = json.loads(meta_bytes)
    images = {
        'campus-north.webp': (PILOT / 'north-pilot.webp').read_bytes(),
        'campus-north-before.webp': (PILOT / 'north-pilot-before.webp').read_bytes(),
    }
    assert (meta['width'], meta['height'], meta['samples']) == (2400, 1800, 24)
    assert sha(images['campus-north.webp']) == meta['image_sha256']
    assert sha(images['campus-north-before.webp']) == meta['comparison']['aligned_image_sha256']
    assert meta['checks']['independent_projection_max_difference_px'] < .02
    assert meta['checks']['source_roof_max_difference_m2'] < .01
    assert all(value == 0 for key, value in meta['pilot'].items() if key.endswith('_m2'))
    assert all(meta['pilot']['descriptive_label_centres_on_source_roads'])
    for name, fingerprint in meta['sources'].items():
        assert sha((ROOT / name).read_bytes()) == fingerprint, name
    return meta, {**images, '_pilot_meta': meta_bytes}


def build_north(meta: dict, candidate: dict[str, bytes]) -> bytes:
    result = dict(meta)
    result['title'] = '北区街区样板'
    result['scope'] = 'N07 and N21–N35, apartment courts, dining halls and adjacent woodland'
    result['render_status'] = 'web_sample_integrated_user_visual_acceptance_pending'
    result['frontend_validation'] = {'status': 'pending_browser_check'}
    result['promotion'] = {
        'method': 'validated copy from independent north pilot into existing sample paths',
        'candidate_metadata_sha256': sha(candidate['_pilot_meta']),
        'script_sha256': sha(Path(__file__).read_bytes()),
    }
    result['generation_commands'] = [
        '/Applications/Blender.app/Contents/MacOS/Blender --background -t 4 --python scripts/north_study.py -- --pilot',
        '/opt/anaconda3/bin/python scripts/promote_north_pilot.py',
    ]
    result['artifact_manifest'] = [
        {'path': f'public/assets/{name}', 'bytes': len(candidate[name]), 'sha256': sha(candidate[name]),
         'role': 'native north-block render' if name == 'campus-north.webp' else 'same-frame source satellite ground projection'}
        for name in NORTH_FILES[:2]
    ]
    result['artifact_manifest_policy'] = 'Current north sample images. The JSON has no recursive self-hash; the current shared asset manifest is in campus-atlas.json.'
    result['metadata_integrity_note'] = 'Image and source hashes are validated at promotion. Browser QA is recorded after page checks, then the shared manifest is resealed.'
    result['budget'] = {'asset_count_limit': 10, 'asset_bytes_limit': LIMIT,
                        'cache_bytes_limit': 192 * 1024**2,
                        'source_amplification_limit': 256,
                        'current_shared_budget_record': 'public/assets/campus-atlas.json'}
    return encoded(result)


def build_atlas(north_bytes: bytes | None = None, candidate: dict[str, bytes] | None = None) -> tuple[bytes, int]:
    atlas = json.loads((ASSETS / 'campus-atlas.json').read_bytes())
    manifest = atlas['artifact_manifest']
    for entry in manifest:
        name = Path(entry['path']).name
        if name in NORTH_FILES:
            data = north_bytes if name == 'campus-north.json' and north_bytes is not None else (
                candidate[name] if candidate is not None and name in candidate else (ASSETS / name).read_bytes())
            entry['bytes'] = len(data)
            entry['sha256'] = sha(data)
    atlas['artifact_manifest_policy'] = (
        'Current shared web assets. Source fingerprints elsewhere in this record describe the atlas generation time; '
        'the north study and north sample may have later revisions.'
    )
    source_paths = [
        'scripts/campus_study.py', 'scripts/north_study.py', 'scripts/north_pilot_detail.py',
        'scripts/lake_study.py', 'scripts/campus_atlas.py', 'scripts/export_atlas.py',
        'scripts/refine_buildings.py', 'scripts/campus_expansion.py',
        'scripts/garden_detail.py', 'scripts/canopy_volume.py', 'scripts/ground_contact.py',
        'scripts/facade_depth.py', 'scripts/landscape_beds.py', 'scripts/courtyard_finish.py',
        'scripts/landscape_surface.py', 'scripts/campus_expansion_export.py',
        'scripts/facade_finish.py', 'scripts/hardscape_transition.py', 'scripts/planting_finish.py',
        'scripts/paving_cleanup.py',
        'src/CampusAtlas.jsx', 'src/campusAtlas.css',
    ]
    source_bytes = sum((ROOT / name).stat().st_size for name in source_paths)
    for _ in range(5):
        payload = encoded(atlas)
        total = sum(entry['bytes'] for entry in manifest) + len(payload)
        atlas['budget']['asset_count_actual'] = len(manifest) + 1
        atlas['budget']['asset_bytes_actual'] = total
        atlas['budget']['source_amplification_actual'] = round(total / source_bytes, 2)
        atlas['budget']['source_amplification_basis'] = source_paths
    payload = encoded(atlas)
    total = sum(entry['bytes'] for entry in manifest) + len(payload)
    assert atlas['budget']['asset_count_actual'] == 10
    assert total == atlas['budget']['asset_bytes_actual']
    assert total < LIMIT, (total, LIMIT)
    assert total / source_bytes < 256
    return payload, total


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--seal', action='store_true', help='Only refresh the shared manifest after frontend QA')
    args = parser.parse_args()
    if args.seal:
        atlas_bytes, total = build_atlas()
        replace(ASSETS / 'campus-atlas.json', atlas_bytes)
    else:
        meta, candidate = validate_pilot()
        north_bytes = build_north(meta, candidate)
        atlas_bytes, total = build_atlas(north_bytes, candidate)
        for name in NORTH_FILES[:2]:
            replace(ASSETS / name, candidate[name])
        replace(ASSETS / 'campus-north.json', north_bytes)
        replace(ASSETS / 'campus-atlas.json', atlas_bytes)
    print(f'North sample ready; 10 shared assets: {total:,} / {LIMIT:,} bytes')


if __name__ == '__main__':
    main()
