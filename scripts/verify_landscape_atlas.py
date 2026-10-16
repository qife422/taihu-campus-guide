"""Read back the scoped landscape iteration, source points and built assets.

Run with /opt/anaconda3/bin/python scripts/verify_landscape_atlas.py after build.
This verifies provenance/containment and captured integration, not visual parity.
"""
from pathlib import Path
import hashlib
import json
import math

from PIL import Image
from promote_full_atlas import (canonical_digest, validate_construction_proof,
    validate_context_roads, validate_paving_regularization, validate_site_sources)

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_evidence(meta, qa):
    """Read current files and source bindings; never transplant a prior QA pass."""
    assert qa['status'] == 'passed' and not qa['errors'] and len(qa['captures']) == 13
    assert qa['image_sha256'] == meta['image_sha256']
    assert qa['source_hashes'] == meta['sources']
    assert len({row['path'] for row in qa['captures']}) == 13
    for path in ('scripts/promote_full_atlas.py', 'scripts/verify_landscape_atlas.py',
                 'scripts/seal_landscape_atlas.py', 'scripts/paving_cleanup.py',
                 'scripts/context_roads.py'):
        assert path in qa['source_sha256'], ('Unbound current consumer', path)
    for name in ('frontend_validation', 'website_frontend_validation'):
        parent = meta[name]
        assert parent['status'] == 'passed' and parent['image_sha256'] == meta['image_sha256']
        assert parent['alignment_status'] == 'not_met' and parent['captures'] == len(qa['captures'])
        assert parent['source_sha256'] == qa['source_sha256']
        assert parent['evidence_manifest'] == meta['frontend_validation']['evidence_manifest']
    assert hashlib.sha256(qa['script_source'].encode()).hexdigest() == qa['script_sha256']
    for path, fingerprint in qa['source_sha256'].items():
        assert sha(ROOT / path) == fingerprint, path
    for record in qa['captures']:
        path = ROOT / record['path']
        assert sha(path) == record['sha256'] and path.stat().st_size == record['bytes']
        assert record['image_sha256'] == record['formal_image_sha256'] == meta['image_sha256']
        assert record['places_image_sha256'] == meta['image_sha256']
        assert record['natural_size'] == [7168, 3072]
        assert record['roof_hotspots'] == 130 and record['source_points'] == 7 and not record['overflow']
        assert record['context_roads_status'] == 'passed'
        assert record['context_roads_source_sha256'] == meta['sources']['scripts/context_roads.py']
        assert record['context_road_geometry_sha256'] == meta['checks']['context_roads']['output_geometry_sha256']['road']
        assert record['context_curb_geometry_sha256'] == meta['checks']['context_roads']['output_geometry_sha256']['curb']
    road_captures = [row for row in qa['captures']
        if row['path'] == 'output/playwright/landscape-road-seam.jpg']
    assert len(road_captures) == 1
    assert not any(row['path'].startswith('output/playwright/landscape-formal-beds.')
        for row in qa['captures'])
    road_focus = road_captures[0]['focus']
    assert road_focus['context_frame_key'] == 'campus-road-seam'
    source_frames = [row for row in meta['checks']['context_roads']['comparison_frames']
        if row['key'] == 'campus-road-seam']
    assert len(source_frames) == 1
    source_frame = source_frames[0]
    assert road_focus['source_frame_world'] == source_frame['source_world_frame']
    assert road_focus['source_keys'] == source_frame['source_keys']
    assert road_focus['frame_method'] == source_frame['frame_method']
    assert road_focus['interaction_counts']['real_drag_gestures'] > 0
    assert road_focus['interaction_counts']['zoom_button_clicks'] > 0
    assert 0 < road_focus['native_to_screen_scale'] <= 1.6 + 1e-9
    bounds = road_focus['viewport_constraint']['bounds_px']
    assert road_focus['viewport_constraint']['margin_px'] == 24
    assert road_focus['viewport_constraint']['frame_point_count'] == len(road_focus['source_frame_world'])
    assert len(road_focus['final_screen_frame']) == len(road_focus['source_frame_world'])
    assert all(bounds[0] + 24 <= x <= bounds[2] - 24 and
        bounds[1] + 24 <= y <= bounds[3] - 24
        for x, y in road_focus['final_screen_frame'])
    formal_captures = [row for row in qa['captures']
        if row['path'] == 'output/playwright/landscape-formal-court.png']
    assert len(formal_captures) == 1
    formal_beds = [{'source_key': row['source_key'], 'world_bounds_m': row['world_bounds_m']}
        for row in meta['checks']['landscape_detail']['beds']['beds']
        if row['source_key'].startswith('E formal')]
    assert len(formal_beds) == 2
    assert formal_captures[0]['focus']['retained_formal_beds'] == formal_beds
    comparison = qa['native_comparison']
    assert comparison['script'] == 'scripts/compare_landscape_atlas.py'
    assert sha(ROOT / comparison['script']) == comparison['script_sha256']
    assert comparison['input_image_sha256'] == {
        'before': meta['previous_iteration']['image_sha256'], 'current': meta['image_sha256']}
    assert comparison['input_source_collections']['current'] == meta['sources']
    assert canonical_digest(comparison['input_source_collections']['before']) == meta['previous_iteration']['source_collection_sha256']
    assert comparison['camera'] == meta['camera']
    assert comparison['input_sizes'] == {'before': [7168, 3072], 'current': [7168, 3072]}
    assert comparison['samples'] == meta['samples'] == 16
    assert comparison['context_output_geometry_sha256'] == meta['checks']['context_roads']['output_geometry_sha256']
    regions = {row['key']: row for row in comparison['regions']}
    assert len(comparison['regions']) == 3 and set(regions) == {
        'external-grey-band', 'campus-road-seam', 'middle-paving-control'}
    for frame in meta['checks']['context_roads']['comparison_frames']:
        row = regions[frame['key']]
        assert row['source_basis'] == 'checks.context_roads.comparison_frames'
        assert row['source_world_frame'] == frame['source_world_frame']
        assert row['source_keys'] == frame['source_keys']
        assert row['frame_method'] == frame['frame_method']
    assert regions['middle-paving-control']['control_paving_geometry_sha256'] == meta['checks']['paving_regularization']['output_geometry_sha256']
    assert len(comparison['artifacts']) == 1
    for record in comparison['artifacts']:
        path = ROOT / record['path']
        assert sha(path) == record['sha256'] and path.stat().st_size == record['bytes']
    assert not {r['path'] for r in qa['captures']}.intersection(r['path'] for r in comparison['artifacts'])
    artifact_count = len(qa['captures']) + len(comparison['artifacts'])
    artifact_bytes = sum(row['bytes'] for row in [*qa['captures'], *comparison['artifacts']])
    evidence_budget = qa['budget']
    assert artifact_count == evidence_budget['actual_artifact_count'] == 14
    assert evidence_budget['capture_limit'] == 14
    assert artifact_bytes == evidence_budget['actual_artifact_bytes'] < evidence_budget['capture_bytes_limit'] == 12*1024**2
    amplification = round(artifact_bytes / sum((ROOT / name).stat().st_size for name in evidence_budget['source_basis']), 2)
    assert amplification == evidence_budget['source_amplification_actual'] < evidence_budget['source_amplification_limit'] == 256


def main():
    meta_path = ROOT / 'public/assets/campus-atlas.json'
    meta = json.loads(meta_path.read_text())
    image_path = ROOT / 'public/assets/campus-atlas.webp'
    assert sha(image_path) == meta['image_sha256'] == meta['presentation_mask']['image_sha256']
    with Image.open(image_path) as image:
        assert image.size == (meta['width'], meta['height']) == (7168, 3072)
    assert len(meta['records']) == len(meta['roof_faces_world']) == 130
    assert len(meta['render_tiles']) == 8 and meta['samples'] == 16
    for path, fingerprint in meta['sources'].items():
        assert sha(ROOT / path) == fingerprint, path
    assert len(meta['sources']) == 33 and 'scripts/paving_cleanup.py' in meta['sources']
    assert 'scripts/context_roads.py' in meta['sources']
    validate_paving_regularization(meta)
    validate_context_roads(meta)
    assert sha(ROOT / 'scripts/campus_expansion_export.py') == meta['exporter_sha256']
    assert sha(ROOT / 'scripts/promote_full_atlas.py') == meta['promotion']['script_sha256']
    manifest_path = ROOT / 'model/campus/manifest.json'
    original = json.loads(manifest_path.read_text())['artifacts_sha256']
    assert len(original) == 23
    for path, fingerprint in original.items():
        assert sha(manifest_path.parent / path) == fingerprint, path
    audit = meta['retained_model_audit']
    central_manifest = ROOT / audit['central_legacy_manifest']
    assert sha(central_manifest.parent / 'central-campus.blend') == audit['central_blend_actual_sha256']
    assert json.loads(central_manifest.read_text())['artifacts']['central-campus.blend'] == audit['central_blend_legacy_manifest_sha256']
    assert audit['central_legacy_manifest_status'] == 'preexisting_hash_mismatch'
    continuity = meta['source_geometry_continuity']
    assert continuity['status'] == 'passed' and continuity['roof_record_count'] == 130 and continuity['source_tree_count'] == 1971
    original_probe = meta['central_roof_source_continuity']
    assert sha(ROOT / original_probe['source']) == original_probe['source_sha256']
    assert hashlib.sha256(original_probe['probe_script_source'].encode()).hexdigest() == original_probe['probe_script_sha256']
    assert {r['source_id']: r['geometry_sha256'] for r in meta['central_roof_finish_revision']['objects']} == original_probe['geometry']
    detail = meta['checks']['landscape_detail']
    assert detail == meta['landscape_detail_revision']['checks']
    assert detail['surface']['material_count'] == 4 and detail['surface']['displacement_link_count'] == 0
    assert detail['beds']['bed_count'] == 4 and detail['beds']['new_tree_centre_count'] == 0
    assert detail['beds']['preserved_source_tree_centre_count'] == 1971 and detail['beds']['preserved_oval_shrub_count'] == 8
    assert detail['courtyards']['site_count'] == 3 and detail['courtyards']['all_overlay_faces_upward']
    assert detail['courtyards']['actual_overlay_outside_source_m2'] < 1e-7
    assert detail['courtyards']['actual_overlay_exclusion_intersection_m2'] < 1e-7
    proof = meta['landscape_construction_consistency']
    validate_construction_proof(meta, proof, 'landscape_detail')
    site = meta['checks']['site_finish']
    validate_site_sources(meta)
    assert site == meta['site_finish_revision']['checks']
    finish = site['facade']
    assert finish['eligible_object_count'] == 98
    assert finish['window_assembly_count'] == finish['verified_glass_first_hit_count'] == 15652
    assert finish['geometry_topology_uv_pose_input_sha256'] == finish['geometry_topology_uv_pose_output_sha256']
    assert finish['upper_faces_above_height_plus_0_2m_materials_preserved']
    assert finish['unassigned_face_material_indices_preserved'] and finish['all_original_material_graphs_preserved']
    transition = site['hardscape']
    assert transition['geometry_preserved'] and transition['only_declared_material_slots_changed']
    assert transition['source_branch_preserved'] and transition['source_weight_zero_outside_2d_coverage']
    assert transition['native_weight_bound'] == [0.0, 1.0] and transition['hardscape_transition_m_estimate'] == 12.0
    assert not transition['interior_road_boundary_used_for_weight']
    planting = site['planting']
    assert planting['source_region_count'] == len(planting['sites']) == 11
    assert planting['new_tree_centre_count'] == planting['new_material_count'] == planting['new_image_count'] == 0
    assert planting['new_object_count'] == planting['new_mesh_count'] == 2
    assert planting['preserved_source_tree_centre_count'] == 1971 and planting['preserved_oval_shrub_count'] == 8
    assert planting['total_polygon_triangle_count'] == sum(row['polygon_triangle_count'] for row in planting['sites']) <= 100000
    assert planting['all_existing_geometry_uv_transforms_visibility_and_material_slots_preserved']
    assert planting['all_existing_material_graphs_world_and_roof_faces_preserved']
    assert all(value < 1e-7 for value in planting['actual_overlap_m2'].values())
    for row in planting['sites']:
        assert 0 < row['maximum_top_above_source_cap_m_estimate'] < .6
        assert row['outside_source_region_m2_at_float32_tolerance'] < 1e-7
        assert row['outside_support_m2_at_float32_tolerance'] < 1e-7
    site_proof = meta['site_construction_consistency']
    validate_construction_proof(meta, site_proof, 'site_finish')
    validate_construction_proof(meta, meta['paving_construction_consistency'], 'paving_regularization')
    validate_construction_proof(meta, meta['context_roads_construction_consistency'], 'context_roads')
    seal = meta['iteration_seal']
    assert seal['status'] == 'passed' and seal['script'] == 'scripts/seal_landscape_atlas.py'
    assert sha(ROOT / seal['script']) == seal['script_sha256']
    assert meta['previous_iteration']['metadata_reference']['git_commit'] == '0e3aee91daf1a114211dd1b65c8bb98bb42c3199'
    assert meta['target_reference_revision']['primary_url'] == 'https://gis.whut.edu.cn/index.shtml'
    assert meta['target_reference_revision']['status'] == 'website_alignment_not_met'
    assert meta['visual_review']['reference_alignment_status'] == 'not_met'
    places = meta['map_places']
    assert places['image_sha256'] == meta['image_sha256'] and places['camera'] == meta['camera']
    assert len(places['records']) == 7 and places['checks']['all_inputs_preserved']
    for path, fingerprint in places['source_hashes'].items():
        if path != 'atlas_metadata_input':
            assert sha(ROOT / places['source_paths'][path]) == fingerprint, path
    x, y, z = meta['camera']['rotation_euler']
    sx, cx, sy, cy, sz, cz = math.sin(x), math.cos(x), math.sin(y), math.cos(y), math.sin(z), math.cos(z)
    for record in places['records']:
        d = [v - p for v, p in zip(record['source_world_point_m'], meta['camera']['position'])]
        px = d[0]*cz*cy + d[1]*sz*cy - d[2]*sy
        py = d[0]*(cz*sy*sx-sz*cx) + d[1]*(sz*sy*sx+cz*cx) + d[2]*cy*sx
        expected = [meta['width']/2 + px*meta['width']/meta['camera']['ortho_scale'], meta['height']/2 - py*meta['width']/meta['camera']['ortho_scale']]
        assert max(abs(v-a) for v, a in zip(expected, record['anchor'])) < .02, record['id']
    qa = json.loads((ROOT / meta['frontend_validation']['evidence_manifest']).read_text())
    validate_evidence(meta, qa)
    for record in meta['artifact_manifest']:
        path = ROOT / record['path']
        assert sha(path) == record['sha256'] and path.stat().st_size == record['bytes']
    total = sum(r['bytes'] for r in meta['artifact_manifest']) + meta_path.stat().st_size
    assert total == meta['budget']['asset_bytes_actual'] < 8*1024**2
    assert meta['budget']['asset_count_actual'] == 10 and meta['budget']['source_amplification_actual'] < 256
    for name in ['campus-atlas.json', 'campus-atlas.webp']:
        assert (ROOT/'public/assets'/name).read_bytes() == (ROOT/'dist'/name).read_bytes()
    sizes = {}
    for directory in [Path('/tmp/taihu-full'), ROOT/'.playwright-cli', ROOT/'output/playwright', ROOT/'dist']:
        files = [p for p in directory.rglob('*') if p.is_file()]
        size = sum(p.stat().st_size for p in files)
        assert size < 192*1024**2
        sizes[str(directory)] = {'files': len(files), 'bytes': size}
    print(json.dumps({'status': 'passed', 'sources': len(meta['sources']), 'original_campus_assets': 23,
        'captures': 13, 'image_sha256': meta['image_sha256'], 'asset_bytes': total,
        'directories': sizes}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
