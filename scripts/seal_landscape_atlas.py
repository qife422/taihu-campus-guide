"""Seal an inspected, already-promoted atlas without rendering or building.

Inputs in /tmp/taihu-full: iteration-baseline.json (exact prior formal bytes),
iteration-preview.json, iteration-qa.json, iteration-comparison.json and
iteration-method.json. The method supplies generation_commands keyed by
middle_diagnostic/native_full; source_place_export containing the actual fresh
export_atlas_places payload; and visual_inspection with status
inspected_no_blocking_findings, full_image_sha256, preview_png_sha256,
capture_sha256 (all thirteen hashes) and comparison_sha256.

Checks every input before replacing only the stable current QA JSON and atlas
metadata. No screenshot, model, render, backup tree or old evidence is deleted.

With --embed-places, read only iteration-baseline.json, atlas-services.json and
the current public metadata as iteration inputs; validate and embed the fresh
seven-point export before browser QA. This mode replaces metadata only and does
not change QA, visual-review or sealing status.
"""
from pathlib import Path
import argparse
import copy
import datetime
import hashlib
import json
import subprocess

from PIL import Image

from promote_full_atlas import (ASSET_NAMES, PROOF_EXCLUSIONS, ROOT, STAGE,
    canonical_digest, construction_core, encoded, replace, shared_budget,
    validate_construction_proof, validate_paving_regularization, validate_site_sources)
from verify_landscape_atlas import validate_evidence


BASELINE_COMMIT = 'b92632471488d95a43872fe5c2d3c45775ea6561'
META_PATH = ROOT / 'public/assets/campus-atlas.json'
QA_PATH = ROOT / 'output/playwright/landscape.json'
PROOF_NAMES = {'landscape_detail': 'landscape_construction_consistency',
               'site_finish': 'site_construction_consistency',
               'paving_regularization': 'paving_construction_consistency'}


def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_input(name):
    path = STAGE / ('iteration-' + name + '.json')
    data = path.read_bytes()
    return json.loads(data), {'sha256': hashlib.sha256(data).hexdigest(),
                              'bytes': len(data), 'name': path.name}


def construction_proof(preview, current, name, commands):
    cores = {}; protection = {}
    for label, metadata in [('middle_diagnostic', preview), ('native_full', current)]:
        core, protection[label] = construction_core(metadata, name)
        cores[label] = canonical_digest(core)
    assert cores['middle_diagnostic'] == cores['native_full'], ('Different native cores', name)
    return {'status': 'passed', 'constructions': ['middle_diagnostic', 'native_full'],
        'source_collection_sha256': canonical_digest(current['sources']),
        'core_sha256': cores,
        'excluded_from_cross_construction_equality': list(PROOF_EXCLUSIONS[name]),
        'per_construction_protection': protection, 'generation_commands': commands,
        'method': 'Recomputed exact declared core from two actual native metadata inputs; final readback recomputes the native-full core again',
        'limitations': 'Original allocation-dependent scene guards remain per construction. Equal cores are not pixel equality, survey accuracy or reference acceptance.'}


def bind_places(meta, baseline, payload):
    assert payload['status'] == 'candidate_source_projection_checked'
    assert payload['image_sha256'] == meta['image_sha256']
    assert payload['camera'] == meta['camera'] == baseline['camera']
    assert payload['source_collection_sha256'] == canonical_digest(meta['sources'])
    assert (payload['width'], payload['height']) == (7168, 3072)
    assert len(payload['records']) == payload['checks']['record_count'] == 7
    assert payload['checks']['gate_count'] == 3 and payload['checks']['sport_count'] == 4
    assert payload['checks']['all_inputs_preserved']
    assert not payload['checks']['render_called'] and not payload['checks']['scene_saved']
    assert payload['checks']['independent_projection_max_difference_px'] < .02
    assert payload['camera_sha256'] == canonical_digest(meta['camera'])
    assert len({row['id'] for row in payload['records']}) == 7
    for key, expected in payload['source_hashes'].items():
        path = payload['source_paths'][key]
        if key == 'atlas_metadata_input':
            continue  # Historical input snapshot before later enrichment, not a self-hash.
        assert file_sha(ROOT / path) == expected, ('Fresh place source mismatch', key)
    assert payload['source_hashes']['atlas_image'] == meta['image_sha256']
    meta['map_places'] = copy.deepcopy(payload)
    meta['promotion']['source_place_reexport'] = {
        'status': 'passed', 'image_sha256': meta['image_sha256'], 'records': 7,
        'export_payload_sha256': hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True,
                       separators=(',', ':')).encode() + b'\n').hexdigest(),
        'method': 'Actual independent seven-point Blender export embedded without rendering or source scene save'}


def embed_places():
    """Bind a just-exported source payload without claiming visual acceptance."""
    baseline, _ = read_input('baseline')
    metadata_input = META_PATH.read_bytes()
    meta = json.loads(metadata_input)
    payload = json.loads((STAGE / 'atlas-services.json').read_bytes())
    assert payload['source_paths']['atlas_metadata_input'] == 'public/assets/campus-atlas.json'
    assert payload['source_hashes']['atlas_metadata_input'] == hashlib.sha256(metadata_input).hexdigest(), (
        'Place export must target the exact current metadata input; rerun export_atlas_places.py')
    assert len(meta['sources']) == 32
    for path, expected in meta['sources'].items():
        assert file_sha(ROOT / path) == expected, ('Current native source mismatch', path)
    assert file_sha(ROOT / 'scripts/promote_full_atlas.py') == meta['promotion']['script_sha256']
    bind_places(meta, baseline, payload)
    metadata_payload = shared_budget(meta)
    assert META_PATH.read_bytes() == metadata_input, 'Metadata changed during place binding'
    replace(META_PATH, metadata_payload)
    print(json.dumps({'status': 'source_places_embedded', 'records': 7,
        'image_sha256': meta['image_sha256'], 'asset_bytes': meta['budget']['asset_bytes_actual'],
        'note': 'Current source points rebound only; QA, visual-review and sealing status unchanged'}, ensure_ascii=False))


def original_assets(meta, baseline, checked_at):
    path = ROOT / 'model/campus/manifest.json'
    original = json.loads(path.read_text())['artifacts_sha256']
    assert len(original) == 23
    for name, expected in original.items():
        assert file_sha(path.parent / name) == expected, name
    audit = copy.deepcopy(baseline['retained_model_audit'])
    central = ROOT / audit['central_legacy_manifest']
    assert file_sha(central.parent / 'central-campus.blend') == audit['central_blend_actual_sha256']
    assert json.loads(central.read_text())['artifacts']['central-campus.blend'] == audit['central_blend_legacy_manifest_sha256']
    assert audit['central_legacy_manifest_status'] == 'preexisting_hash_mismatch'
    audit['checked_at'] = checked_at
    meta['retained_model_audit'] = audit


def main():
    baseline, baseline_input = read_input('baseline')
    preview, preview_input = read_input('preview')
    qa, qa_input = read_input('qa')
    comparison, comparison_input = read_input('comparison')
    method, method_input = read_input('method')
    meta = json.loads(META_PATH.read_bytes())
    assert meta['image_sha256'] != baseline['image_sha256'], 'Cannot reseal the previous image as a new iteration'
    assert meta['sources'] == preview['sources'] and len(meta['sources']) == 32
    assert (meta['width'], meta['height'], meta['samples']) == (7168, 3072, 16)
    assert len(meta['render_tiles']) == 8
    assert (preview['width'], preview['height'], preview['samples']) == (1800, 1350, 8)
    assert meta['camera'] == baseline['camera']
    assert meta['roof_faces_world'] == baseline['roof_faces_world'] == preview['roof_faces_world']
    tree_centres = lambda m: sorted(tuple(row[1]) for row in m['landscape_revision']['tree_pairs'])
    assert tree_centres(meta) == tree_centres(baseline) == tree_centres(preview)
    assert len(tree_centres(meta)) == 1971
    for path, expected in meta['sources'].items():
        assert file_sha(ROOT / path) == expected, path
    assert file_sha(ROOT / 'scripts/promote_full_atlas.py') == meta['promotion']['script_sha256']
    assert file_sha(ROOT / 'scripts/campus_expansion_export.py') == meta['exporter_sha256']
    assert file_sha(ROOT / 'public/assets/campus-atlas.webp') == meta['image_sha256']
    with Image.open(ROOT / 'public/assets/campus-atlas.webp') as image:
        assert image.size == (7168, 3072)
    for metadata in (preview, meta):
        validate_paving_regularization(metadata)
        validate_site_sources(metadata)
        probe = baseline['central_roof_source_continuity']['geometry']
        assert {row['source_id']: row['geometry_sha256'] for row in
            metadata['central_roof_finish_revision']['objects']} == probe
    prior_bytes = subprocess.run(['git', 'show', BASELINE_COMMIT + ':public/assets/campus-atlas.json'],
        cwd=ROOT, check=True, capture_output=True).stdout
    assert hashlib.sha256(prior_bytes).hexdigest() == baseline_input['sha256'], 'Baseline must be exact retained Git bytes'
    commands = method['generation_commands']
    assert set(commands) == {'middle_diagnostic', 'native_full'}
    assert all(isinstance(command, str) and command.strip() for command in commands.values())
    command_list = [commands[label] for label in ('middle_diagnostic', 'native_full')]
    for name, field in PROOF_NAMES.items():
        meta[field] = construction_proof(preview, meta, name, command_list)
        validate_construction_proof(meta, meta[field], name)
    meta['historical_native_proofs'] = copy.deepcopy(baseline['historical_native_proofs'])
    meta['previous_iteration'] = {
        'image_sha256': baseline['image_sha256'],
        'source_collection_sha256': canonical_digest(baseline['sources']),
        'source_count': len(baseline['sources']),
        'status': 'superseded by bounded early middle-campus paving regularization',
        'metadata_reference': {'status': 'historical_previous_image',
            'git_commit': BASELINE_COMMIT, 'path': 'public/assets/campus-atlas.json',
            'sha256': baseline_input['sha256'],
            'scope': 'Immutable previous formal metadata and its historical records; not current-image QA'}}
    bind_places(meta, baseline, method['source_place_export'])
    meta['central_roof_source_continuity']['promotion_revalidation']['current_whole_mesh_confirmation'] = (
        'Both current native constructions match the embedded whole-central-mesh probe; original probe not rerun')
    checked_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    original_assets(meta, baseline, checked_at)
    qa['native_comparison'] = comparison
    assert qa['source_hashes'] == meta['sources']
    assert qa['image_sha256'] == meta['image_sha256']
    inspection = method['visual_inspection']
    assert inspection['status'] == 'inspected_no_blocking_findings'
    assert inspection['full_image_sha256'] == meta['image_sha256']
    assert inspection['preview_png_sha256'] == preview['png_sha256']
    assert len(inspection['capture_sha256']) == 13
    assert sorted(inspection['capture_sha256']) == sorted(row['sha256'] for row in qa['captures'])
    assert len(comparison['artifacts']) == 1
    assert inspection['comparison_sha256'] == comparison['artifacts'][0]['sha256']
    frontend = {'status': 'passed', 'image_sha256': meta['image_sha256'],
        'checked_at': qa['checked_at'], 'evidence_manifest': 'output/playwright/landscape.json',
        'report': 'output/playwright/landscape.md', 'source_sha256': qa['source_sha256'],
        'captures': 13, 'viewports': [{'width': 1280, 'height': 720}, {'width': 390, 'height': 844}],
        'alignment_status': 'not_met',
        'scope': 'Current native paving and retained map integration; earlier exhaustive UI tests remain historical',
        'limitations': 'No complete reference parity, surveyed routing, true-device or Safari acceptance'}
    meta['frontend_validation'] = copy.deepcopy(frontend)
    meta['website_frontend_validation'] = copy.deepcopy(frontend)
    budget = qa['budget']
    assert budget['capture_limit'] == 14 and budget['capture_bytes_limit'] == 12 * 1024**2
    assert budget['source_amplification_limit'] == 256
    assert len(set(budget['source_basis'])) == len(budget['source_basis'])
    artifacts = [*qa['captures'], *comparison['artifacts']]
    budget['actual_artifact_count'] = len(artifacts)
    budget['actual_artifact_bytes'] = sum(row['bytes'] for row in artifacts)
    budget['source_amplification_actual'] = round(budget['actual_artifact_bytes'] /
        sum((ROOT / path).stat().st_size for path in budget['source_basis']), 2)
    validate_evidence(meta, qa)
    meta['visual_review'] = {'status': 'agent_inspected_native_preview_full_comparison_and_thirteen_current_captures',
        'reference_alignment_status': 'not_met', 'user_visual_acceptance': 'pending',
        'comparison_manifest': 'output/playwright/landscape.json',
        'remaining_differences': method.get('remaining_differences', baseline['visual_review']['remaining_differences']),
        'inspection_input_sha256': method_input['sha256']}
    meta['render_status'] = 'integrated_user_visual_acceptance_pending'
    for field in ('landscape_detail_revision', 'site_finish_revision'):
        meta[field]['visual_review'] = {'status': 'inspected_current_image',
            'comparison_manifest': 'output/playwright/landscape.json',
            'reference_alignment_status': 'not_met'}
    meta['artifact_manifest'] = [{'path': 'public/assets/' + name,
        'bytes': (ROOT / 'public/assets' / name).stat().st_size,
        'sha256': file_sha(ROOT / 'public/assets' / name)} for name in ASSET_NAMES]
    meta['iteration_seal'] = {'schema_version': 1, 'status': 'passed', 'checked_at': checked_at,
        'script': 'scripts/seal_landscape_atlas.py', 'script_sha256': file_sha(Path(__file__)),
        'inputs': {'baseline': baseline_input, 'preview': preview_input, 'qa': qa_input,
                   'comparison': comparison_input, 'method': method_input},
        'scope': 'Recomputed native cores, current source/asset hashes, fresh source points, thirteen fresh screenshots and explicit inspected-image hashes; historical block retained once',
        'limitations': 'Inspection input is a session attestation, not automated aesthetic judgment or external acceptance. Temporary input paths are provenance, not active artifact requirements.'}
    metadata_payload = shared_budget(meta)
    qa_payload = encoded(qa)
    cache_bytes = sum(path.stat().st_size for path in STAGE.rglob('*') if path.is_file())
    assert cache_bytes < 192 * 1024**2
    evidence_dir = QA_PATH.parent
    evidence_bytes = sum(path.stat().st_size for path in evidence_dir.rglob('*') if path.is_file())
    assert evidence_bytes - QA_PATH.stat().st_size + len(qa_payload) < 192 * 1024**2
    # All source, budget and current-evidence gates above complete before either write.
    replace(QA_PATH, qa_payload)
    replace(META_PATH, metadata_payload)
    print(json.dumps({'status': 'sealed', 'sources': 32, 'captures': 13,
        'image_sha256': meta['image_sha256'], 'asset_bytes': meta['budget']['asset_bytes_actual'],
        'note': 'Rebuild dist and run verify_landscape_atlas.py for production readback'}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--embed-places', action='store_true',
        help='Embed a fresh atlas-services.json before QA; update public metadata only, without sealing')
    args = parser.parse_args()
    if args.embed_places:
        embed_places()
    else:
        main()
