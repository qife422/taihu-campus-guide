"""Validate a staged native atlas and replace the existing web asset paths."""
from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
STAGE = Path('/tmp/taihu-full')
ASSETS = ROOT / 'public/assets'
LIMIT = 8 * 1024**2
ASSET_NAMES = (
    'campus-north.webp', 'campus-north.json', 'campus-north-before.webp',
    'campus-reference.webp', 'campus-lake.webp', 'campus-lake.json',
    'campus-study.webp', 'campus-study.json', 'campus-atlas.webp',
)
PROOF_EXCLUSIONS = {
    'landscape_detail': (
        'surface.existing_visible_mesh_sha256', 'beds.per_construction_preservation',
        'courtyards.other_existing_visible_mesh_sha256'),
    'site_finish': (
        'facade.other_scene_meshes_sha256',
        'hardscape.all_existing_mesh_geometry_uv_pose_visibility_sha256',
        'hardscape.original_material_slot_assignment_sha256',
        'hardscape.final_material_slot_assignment_sha256',
        'planting.per_construction_preservation'),
    'paving_regularization': ('edge.per_construction_preservation',),
    'context_roads': (),
}


def canonical_digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def construction_core(meta: dict, name: str) -> tuple[dict, dict]:
    """Retain exact recipe/geometry checks; extract only declared per-run guards."""
    value = ({'geometry': meta['checks']['paving_regularization'],
              'edge': meta['checks']['paving_edge_finish']}
             if name == 'paving_regularization' else meta['checks'][name])
    core = json.loads(json.dumps(value, allow_nan=False))
    protection = {}
    for path in PROOF_EXCLUSIONS[name]:
        branch = core
        for key in path.split('.')[:-1]:
            branch = branch[key]
        key = path.split('.')[-1]
        assert key in branch, ('Missing declared construction guard', name, path)
        protection[path] = branch.pop(key)
    return core, protection


def validate_construction_proof(meta: dict, proof: dict, name: str) -> None:
    core, protection = construction_core(meta, name)
    assert proof['status'] == 'passed'
    assert proof['constructions'] == ['middle_diagnostic', 'native_full']
    assert proof['source_collection_sha256'] == canonical_digest(meta['sources'])
    assert proof['excluded_from_cross_construction_equality'] == list(PROOF_EXCLUSIONS[name])
    assert proof['core_sha256']['middle_diagnostic'] == proof['core_sha256']['native_full'] == canonical_digest(core)
    assert proof['per_construction_protection']['native_full'] == protection


def shared_budget(meta: dict) -> bytes:
    """Measure the final compact JSON, including every added proof, before writing."""
    paths = sorted(set(meta['budget'].get('source_amplification_basis', [])) |
        {path for path in meta['sources'] if path.endswith('.py')} |
        {'src/CampusAtlas.jsx', 'src/campusAtlas.css', 'scripts/promote_full_atlas.py',
         'scripts/verify_landscape_atlas.py', 'scripts/seal_landscape_atlas.py'})
    source_bytes = sum((ROOT / path).stat().st_size for path in paths)
    binaries = sum(row['bytes'] for row in meta['artifact_manifest'])
    for _ in range(8):
        total = binaries + len(encoded(meta))
        meta['budget'].update({'asset_count_actual': 10, 'asset_bytes_actual': total,
            'source_amplification_actual': round(total / source_bytes, 2),
            'source_amplification_basis': paths})
    payload = encoded(meta)
    assert binaries + len(payload) == meta['budget']['asset_bytes_actual'] < LIMIT
    assert (binaries + len(payload)) / source_bytes < 256
    return payload


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def encoded(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, separators=(',', ':')) + '\n').encode()


def replace(path: Path, data: bytes) -> None:
    with tempfile.NamedTemporaryFile(prefix='taihu-atlas-', dir='/tmp', delete=False) as item:
        item.write(data)
        temporary = Path(item.name)
    try:
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def historical_validation(value: dict, image_sha256: str) -> dict:
    result = json.loads(json.dumps(value))
    result['status_at_capture'] = value.get('status_at_capture', value.get('status'))
    result['status'] = 'historical_previous_image'
    result['image_sha256'] = value.get('image_sha256', image_sha256)
    result['scope_at_capture'] = value.get('scope', value.get('method'))
    result['scope'] = 'Prior image/interface capture retained for provenance; no current-image or current-website QA claim'
    result['evidence_status'] = 'Historical capture record; external screenshot/report paths are not active evidence for the new image'
    return result


def preserve_website_metadata(candidate: dict, baseline: dict) -> None:
    """Carry website intent and source places, without reusing an old QA pass."""
    for name in ('target_reference_revision', 'website_interaction_revision',
                 'central_roof_source_continuity'):
        assert isinstance(baseline.get(name), dict), ('Missing retained website/source record', name)
        candidate[name] = json.loads(json.dumps(baseline[name]))
    candidate['website_interaction_revision']['promotion_context'] = {
        'implementation_image_sha256': baseline['website_interaction_revision'].get('promotion_context', {}).get('implementation_image_sha256', baseline['image_sha256']),
        'previous_image_sha256': baseline['image_sha256'],
        'current_image_sha256': candidate['image_sha256'],
        'scope_note': 'The original native-image-unchanged statement describes that interface implementation; this later native image requires new browser QA',
    }
    continuity = candidate['central_roof_source_continuity']
    assert candidate['sources'][continuity['source']] == continuity['source_sha256']
    assert sha((ROOT / continuity['source']).read_bytes()) == continuity['source_sha256']
    continuity['promotion_revalidation'] = {
        'retained_source_bytes_match': True,
        'roof_faces_equal_previous_image': candidate['roof_faces_world'] == baseline['roof_faces_world'],
        'current_whole_mesh_confirmation': 'Pending final source/geometry sealing; the original source probe was not rerun by promotion',
    }
    assert continuity['promotion_revalidation']['roof_faces_equal_previous_image']

    places = json.loads(json.dumps(baseline.get('map_places')))
    assert isinstance(places, dict), 'Missing retained seven-point source projection'
    assert places['image_sha256'] == baseline['image_sha256']
    assert places['camera'] == candidate['camera'] == baseline['camera']
    assert (places['width'], places['height']) == (candidate['width'], candidate['height'])
    camera_sha = sha(json.dumps(candidate['camera'], sort_keys=True, separators=(',', ':')).encode())
    assert places['camera_sha256'] == camera_sha
    source_checks = {}
    for name in ('scene', 'layout', 'satellite_export', 'north_export', 'export_script'):
        path = places['source_paths'][name]
        expected = places['source_hashes'][name]
        assert sha((ROOT / path).read_bytes()) == expected, ('Changed source projection input', path)
        if name != 'export_script':
            assert candidate['sources'][path] == expected, ('Projection input absent from native recipe', path)
        source_checks[name] = {'path': path, 'sha256': expected, 'unchanged': True}
    assert places['checks']['all_inputs_preserved']
    assert places['checks']['retained_georef_matches_source_builder']
    assert places['checks']['record_count'] == len(places['records']) == 7
    assert places['checks']['gate_count'] == 3 and places['checks']['sport_count'] == 4
    assert len({row['id'] for row in places['records']}) == 7
    regions = {row['id'] for row in candidate['regions']}
    camera = candidate['camera']; rx, ry, rz = camera['rotation_euler']
    ppm = candidate['width'] / camera['ortho_scale']
    projection_errors = []
    for row in places['records']:
        assert row['region'] in regions
        world = row['source_world_point_m']; anchor = row['anchor']
        assert len(world) == 3 and len(anchor) == 2 and all(math.isfinite(v) for v in [*world, *anchor])
        x, y, z = [world[i] - camera['position'][i] for i in range(3)]
        x, y = math.cos(rz) * x + math.sin(rz) * y, -math.sin(rz) * x + math.cos(rz) * y
        x, z = math.cos(ry) * x - math.sin(ry) * z, math.sin(ry) * x + math.cos(ry) * z
        y, z = math.cos(rx) * y + math.sin(rx) * z, -math.sin(rx) * y + math.cos(rx) * z
        projected = [candidate['width'] / 2 + x * ppm, candidate['height'] / 2 - y * ppm]
        error = max(abs(a - b) for a, b in zip(projected, anchor))
        assert error < .02, (row['id'], 'Retained source point projection differs', error)
        assert 0 <= anchor[0] <= candidate['width'] and 0 <= anchor[1] <= candidate['height']
        projection_errors.append(error)
    places['projection_rebind'] = {
        'method': 'Retain the seven source world points and pixel anchors only after exact camera/size and source-input equality, with independent scalar projection readback',
        'previous_image_sha256': places['image_sha256'],
        'image_sha256': candidate['image_sha256'], 'camera_sha256': camera_sha,
        'source_checks': source_checks,
        'independent_projection_max_difference_px': max(projection_errors),
        'original_export_source_collection_sha256': places['source_collection_sha256'],
        'original_export_input_status': 'The original source_hashes atlas_image/atlas_metadata_input and source collection bind the historical export input, not this new image or self-referential metadata',
        'final_export_validation': 'Pending independent seven-point Blender export; no render, scene save or source export was performed by promotion',
    }
    places['image_sha256'] = candidate['image_sha256']
    candidate['map_places'] = places

    if isinstance(baseline.get('frontend_validation'), dict):
        previous = historical_validation(baseline['frontend_validation'], baseline['image_sha256'])
        earlier = baseline.get('previous_frontend_validation', {})
        previous['earlier_validation_summary'] = {key: earlier[key] for key in
            ('status', 'image_sha256', 'checked_at', 'scope', 'limitations') if key in earlier}
        candidate['previous_frontend_validation'] = previous
    if isinstance(baseline.get('website_frontend_validation'), dict):
        candidate['previous_website_frontend_validation'] = historical_validation(
            baseline['website_frontend_validation'], baseline['image_sha256'])
    candidate['frontend_validation'] = {'status': 'pending_browser_check', 'image_sha256': candidate['image_sha256']}
    candidate['website_frontend_validation'] = {
        'status': 'pending_browser_check', 'image_sha256': candidate['image_sha256'],
        'alignment_status': 'not_met',
        'scope': 'Current native image and retained website interaction need a fresh bounded browser check',
    }


def validate_site_sources(candidate: dict) -> None:
    """Bind reported finish roles and retained source data to native inputs."""
    site = candidate['checks']['site_finish']
    finish = site['facade']
    kinds = {'academic', 'dorm', 'service'}
    assert set(finish['kind_building_counts']) == set(finish['role_face_counts_by_kind']) == kinds
    assert sum(finish['kind_building_counts'].values()) == finish['eligible_object_count'] == 98
    windows = 0
    faces = 0
    for roles in finish['role_face_counts_by_kind'].values():
        assert roles['glass'] % 6 == 0
        count = roles['glass'] // 6
        assert count > 0
        for role, per_window in [('surround', 16), ('glass', 6), ('window bars', 24), ('sill', 6)]:
            assert roles[role] == per_window * count, (role, roles)
        assert all(roles[role] > 0 for role in ('wall', 'plinth', 'storey band', 'vertical member'))
        windows += count
        faces += sum(roles.values())
    assert windows == finish['window_assembly_count']
    assert faces == finish['changed_material_face_count']
    assert 0 < finish['new_material_count'] == len(finish['material_recipes']) <= 40
    assert len({row['material'] for row in finish['material_recipes']}) == finish['new_material_count']

    transition = site['hardscape']
    assert transition['new_material_count'] == len(transition['recipes']) == 5
    assert len({row['source_material'] for row in transition['recipes']}) == 5
    spatial = candidate['checks']['spatial_continuity_and_scale']
    assert transition['outer_field_rgba_float32_sha256'] == spatial['field_rgba_float32_sha256']
    assert transition['outer_field_size'] == spatial['field_size']
    assert transition['outer_field_cell_m'] == spatial['field_cell_m']
    assert transition['source_group_graph_sha256'] == spatial['source_surface_graph_sha256']
    assert transition['source_coverage_bounds_match_retained_georeference']
    assert transition['source_world_coverage_bounds'] == {
        row['source']: row['world_bounds'] for row in spatial['survey_coverage_checks']}

    planting = site['planting']
    assert planting['retained_support_object_count'] == 2
    assert {row['source_object'] for row in planting['sites']} == {
        'Study planted bed ground', 'Joined source academic planted strips'}
    assert len(planting['source_caps_sha256']) == 64
    assert set(planting['source_caps_sha256']) <= set('0123456789abcdef')
    assert len(planting['source_inputs_sha256']) == 7
    assert set(planting['source_keys']) == {
        *(f'north-seam-{i}' for i in range(5)),
        *(f'north-apartment-seam-{i}' for i in range(4)),
        *(f'academic-strip-{i}' for i in range(2))}
    for path, fingerprint in planting['source_inputs_sha256'].items():
        assert candidate['sources'][path] == fingerprint, path
    for row in planting['sites']:
        assert 0 < row['support_area_m2'] <= row['source_region_area_m2'] + 1e-6
        assert row['support_area_m2'] / row['source_region_area_m2'] > .30
    assert planting['actual_projected_area_m2'] > 0
    assert set(planting['actual_overlap_m2']) == {
        'roof', 'water', 'road', 'hardscape', 'sports',
        'retained_oval_shrub_and_previous_low_foliage_envelope'}
    assert all(0 <= value < 1e-7 for value in planting['actual_overlap_m2'].values())
    assert len(planting['batches']) == 2
    assert planting['total_polygon_triangle_count'] == sum(
        row['polygon_triangle_count'] for row in planting['batches'])


def validate_paving_regularization(candidate: dict) -> None:
    """Verify the early planar cleanup without inventing Blender mesh claims."""
    check = candidate['checks']['paving_regularization']
    assert check['status'] == 'passed'
    assert check['source_building_ids'] == [f'M{i:02}' for i in range(1, 8)]
    assert 'scripts/paving_cleanup.py' in candidate['sources']
    assert check['opening_radius_m'] == 1.20 and check['window_margin_m'] == 12.0
    assert check['road_building_contact_width_m'] == 2.0
    assert check['source_tree_protection_radius_m'] == 1.10
    assert check['source_hole_edge_protection_width_m'] == 1.20
    assert check['window_seam_width_m'] == 2.4
    for key in ('input_area_m2', 'output_area_m2', 'candidate_input_area_m2',
                'protected_candidate_area_m2', 'eligible_candidate_area_m2',
                'removed_area_m2', 'removed_candidate_fraction',
                'boundary_hausdorff_distance_m'):
        assert math.isfinite(check[key]) and check[key] >= 0, key
    area = check['candidate_input_area_m2']; removed = check['removed_area_m2']
    assert area > 200 and check['input_area_m2'] >= area
    assert check['removed_area_minimum_m2'] == 1.0
    assert check['removed_area_limit_m2'] == min(area * .03, 100.0)
    assert 1.0 <= removed <= check['removed_area_limit_m2']
    assert abs(check['removed_candidate_fraction'] - removed / area) < 1e-12
    assert check['removed_candidate_fraction'] <= .03
    assert abs(check['input_area_m2'] - check['output_area_m2'] - removed) < 1e-6
    assert check['boundary_hausdorff_distance_m'] <= 1.2 + 1e-6
    for key in ('output_outside_input_area_m2', 'difference_outside_window_area_m2',
                'protected_loss_area_m2'):
        assert math.isfinite(check[key]) and 0 <= check[key] < 1e-7, key
    assert check['component_count_before'] == check['component_count_after'] > 0
    assert check['hole_count_before'] == check['hole_count_after'] >= 0
    assert check['each_component_and_its_holes_preserved']
    assert check['source_geometry_read_only'] and check['ground_under_paving_preserved']
    contacts = check['protected_source_contacts']
    assert set(contacts) == {'building_contact', 'road_contact', 'traced_finishes',
                             'source_tree_roots', 'window_seam', 'original_hole_edges'}
    hashes = [check[key] for key in ('input_geometry_sha256', 'output_geometry_sha256',
        'candidate_geometry_sha256', 'removed_geometry_sha256', 'protected_geometry_sha256',
        'relevant_source_tree_centres_sha256')]
    assert check['input_geometry_sha256'] != check['output_geometry_sha256']
    for contact in contacts.values():
        assert math.isfinite(contact['source_area_m2']) and contact['source_area_m2'] >= 0
        assert math.isfinite(contact['lost_area_m2']) and 0 <= contact['lost_area_m2'] < 1e-7
        hashes.append(contact['source_geometry_sha256'])
    assert all(len(h) == 64 and set(h) <= set('0123456789abcdef') for h in hashes)
    bounds = check['candidate_world_bounds']
    assert len(bounds) == 4 and all(math.isfinite(v) for v in bounds)
    assert bounds[0] < bounds[2] and bounds[1] < bounds[3]
    edge = candidate['checks']['paving_edge_finish']
    assert edge['status'] == 'passed' and edge['target'] == 'Expansion paving courses'
    assert edge['source_material'] == 'Study light stone curb'
    assert edge['finish_material'] == 'Middle source paving subdued edge'
    assert edge['candidate_world_bounds'] == bounds
    assert edge['boundary_fade_m'] == 2.0 and edge['colour_multiplier'] == [.68, .70, .67]
    assert edge['outside_window_weight'] == 0 and edge['interior_weight'] == 1
    assert edge['world_position_mask'] and isinstance(edge['source_colour_link_retained'], bool)
    assert edge['source_nodes_and_other_internal_links_preserved']
    assert edge['shader_parameters_and_links_read_back']
    assert edge['other_bsdf_inputs_preserved']
    assert edge['affected_course_area_m2_estimate'] > 10 and math.isfinite(edge['affected_course_area_m2_estimate'])
    assert edge['course_height_m'] == .335 and edge['material_slot_count'] == 1
    assert edge['new_material_count'] == 1 and edge['added_node_count'] == 14
    assert edge['source_graph_sha256'] != edge['finish_graph_sha256']
    transition = candidate['checks']['site_finish']['hardscape']
    targets = [row for row in transition['targets'] if row['object'] == edge['target']]
    recipes = [row for row in transition['recipes']
               if row['source_material'] == edge['finish_material']]
    assert len(targets) == len(recipes) == 1
    assert targets[0]['source_material'] == edge['finish_material']
    assert targets[0]['copied_material'] == recipes[0]['copied_material']
    assert recipes[0]['source_material_graph_sha256'] == edge['finish_graph_sha256']
    protection = edge['per_construction_preservation']
    for key in ('scene_geometry_preserved', 'other_materials_preserved',
                'other_object_material_slots_preserved', 'world_graph_preserved'):
        assert protection[key], key
    fingerprints = [edge['source_graph_sha256'], edge['finish_graph_sha256'],
        protection['scene_geometry_sha256'], protection['other_material_graphs_sha256']]
    assert all(len(h) == 64 and set(h) <= set('0123456789abcdef') for h in fingerprints)


def validate_context_roads(candidate: dict) -> None:
    """Bind the scoped exterior subtraction and actual generated road meshes."""
    check = candidate['checks']['context_roads']
    assert check['status'] == 'passed'
    assert 'scripts/context_roads.py' in candidate['sources']
    names = {'钱荣路', '外部道路南段'}
    assert set(check['source_road_names']) == names and len(check['source_road_names']) == 2
    assert len(check['source_roads']) == 2
    assert {row['name'] for row in check['source_roads']} == names
    protected = check['protected_connector_source_roads']
    assert protected and not ({row['name'] for row in protected} & names)
    all_sources = [*check['source_roads'], *protected]
    assert len({row['name'] for row in all_sources}) == len(all_sources)
    layout_path = 'model/campus/layout.json'
    layout_bytes = (ROOT / layout_path).read_bytes()
    assert candidate['sources'][layout_path] == sha(layout_bytes)
    traced_sources = {row[0]: row for row in json.loads(layout_bytes)['roads']}
    assert {row['name'] for row in all_sources} == set(traced_sources)
    hashes = []
    for row in all_sources:
        assert math.isfinite(row['width_m']) and row['width_m'] > 0
        traced = traced_sources[row['name']]
        assert row['width_m'] == traced[2] and len(row['points_world']) == len(traced[1])
        assert len(row['points_world']) >= 2
        assert all(len(point) == 2 and all(math.isfinite(v) for v in point)
            for point in row['points_world'])
        assert row['buffer_join_style'] == row['buffer_cap_style'] == 'round'
        assert row['buffer_quad_segs'] == 16
        hashes.append(row['source_geometry_sha256'])
    connectors = check['connector_protection']
    assert connectors['source_noncontext_road_count'] == len(protected)
    assert math.isfinite(connectors['old_external_context_overlap_with_noncontext_roads_m2'])
    assert connectors['old_external_context_overlap_with_noncontext_roads_m2'] >= 0
    for key in ('removed_noncontext_road_area_m2', 'removed_noncontext_curb_area_m2'):
        assert math.isfinite(connectors[key]) and 0 <= connectors[key] < 1e-7
    hashes.extend(connectors[key] for key in ('context_outside_ground_mask_sha256',
        'source_noncontext_road_union_sha256', 'source_noncontext_curb_protection_sha256'))
    assert check['curb_removal_buffer_m'] == .25
    for name in ('road', 'curb'):
        row = check[name]
        for key in ('before_area_m2', 'after_area_m2', 'removed_area_m2',
                    'allowed_removal_mask_area_m2'):
            assert math.isfinite(row[key]) and row[key] > 0, (name, key)
        assert abs(row['before_area_m2'] - row['after_area_m2'] - row['removed_area_m2']) < 1e-6
        assert row['removed_area_m2'] <= row['allowed_removal_mask_area_m2'] + 1e-6
        for key in ('inside_ground_difference_m2', 'outside_allowed_mask_difference_m2',
                    'new_outside_old_area_m2', 'allowed_removal_mask_inside_ground_m2'):
            assert math.isfinite(row[key]) and 0 <= row[key] < 1e-7, (name, key)
        assert row['components_before'] > 0 and row['components_after'] > 0
        hashes.append(row['allowed_removal_mask_sha256'])
    assert check['road']['removed_area_m2'] > 1
    assert 0 <= check['new_transverse_curb_area_m2'] < 1e-7
    connection = check['campus_connectivity']
    assert connection['inside_component_count_before'] == connection['inside_component_count_after'] > 0
    assert connection['inside_hole_count_before'] == connection['inside_hole_count_after'] >= 0
    assert connection['each_inside_component_and_its_holes_preserved']
    for key in ('ground_boundary_contact_length_before_m', 'ground_boundary_contact_length_after_m'):
        assert math.isfinite(connection[key]) and connection[key] >= 0
    for key in ('ground_boundary_contact_lost_length_m', 'ground_boundary_contact_added_length_m'):
        assert math.isfinite(connection[key]) and 0 <= connection[key] < 1e-7
    assert abs(connection['ground_boundary_contact_length_before_m'] -
               connection['ground_boundary_contact_length_after_m']) < 1e-7
    assert len(check['gates']) == 3 and {row['id'] for row in check['gates']} == {'gate1', 'gate2', 'gate3'}
    for row in check['gates']:
        assert row['inspection_radius_m'] == 12
        assert len(row['world_xy']) == 2 and all(math.isfinite(v) for v in row['world_xy'])
        for key in ('nearby_removed_road_area_m2', 'nearby_removed_curb_area_m2'):
            assert math.isfinite(row[key]) and 0 <= row[key] < 1e-7
        for key in ('nearest_joined_road_before_m', 'nearest_joined_road_after_m'):
            assert math.isfinite(row[key]) and row[key] >= 0
        assert row['old_joined_road_covers_gate'] == row['new_joined_road_covers_gate']
    diagnostic = check['diagnostic']
    assert diagnostic['world_xy'] == [249.10, 111.05]
    assert not diagnostic['ground_contains'] and diagnostic['distance_to_ground_m'] > 0
    assert all(diagnostic[key] for key in ('before_road_covers', 'allowed_mask_covers', 'removed_road_covers'))
    assert not diagnostic['after_road_covers']
    frames = check['comparison_frames']
    assert len(frames) == 2 and {row['key'] for row in frames} == {'external-grey-band', 'campus-road-seam'}
    for row in frames:
        assert row['source_keys'] and set(row['source_keys']) <= names
        frame = row['source_world_frame']
        assert len(frame) == 4 and all(len(point) == 3 and all(math.isfinite(v) for v in point) for point in frame)
        assert all(point[2] == .35 for point in frame)
        assert max(point[0] for point in frame) > min(point[0] for point in frame)
        assert max(point[1] for point in frame) > min(point[1] for point in frame)
        assert isinstance(row['frame_method'], str) and row['frame_method']
    assert set(check['input_geometry_sha256']) == {'road', 'curb', 'ground'}
    assert set(check['output_geometry_sha256']) == set(check['removed_geometry_sha256']) == {'road', 'curb'}
    for key in ('input_geometry_sha256', 'output_geometry_sha256', 'removed_geometry_sha256'):
        hashes.extend(check[key].values())
    assert all(check['input_geometry_sha256'][name] != check['output_geometry_sha256'][name]
        for name in ('road', 'curb'))
    assert check['source_inputs_unchanged']
    meshes = check['mesh_verification']
    expected = {'Joined continuous source roads': ('road', .35),
                'Joined continuous road curbs': ('curb', .38)}
    assert set(meshes) == set(expected)
    for name, (role, height) in expected.items():
        row = meshes[name]
        assert row['world_z_m'] == height and row['numeric_planar_buffer_m'] == .0002
        assert 0 <= row['maximum_height_error_m'] < 1e-6 and row['triangle_count'] > 0
        assert math.isfinite(row['actual_area_m2']) and row['actual_area_m2'] > 0
        for key in ('actual_outside_expected_buffer_area_m2', 'expected_missing_from_actual_buffer_area_m2'):
            assert math.isfinite(row[key]) and 0 <= row[key] < 1e-7
        assert row['expected_geometry_sha256'] == check['output_geometry_sha256'][role]
        hashes.extend((row['expected_geometry_sha256'], row['actual_geometry_sha256']))
    assert not meshes['Joined continuous source roads']['actual_covers_grey_band_diagnostic']
    trees = check['tree_preservation']
    assert trees['source_crown_object_count_before'] == trees['source_crown_object_count_after'] > 0
    assert trees['original_crown_objects_pose_and_visibility_preserved']
    assert trees['final_source_tree_pair_count'] == 1971
    hashes.append(trees['pose_visibility_sha256'])
    assert all(len(h) == 64 and set(h) <= set('0123456789abcdef') for h in hashes)


def main() -> None:
    candidate = json.loads((STAGE / 'campus-atlas.json').read_bytes())
    image = (STAGE / 'campus-atlas.webp').read_bytes()
    assert (candidate['width'], candidate['height'], candidate['samples']) == (7168, 3072, 16)
    assert candidate['image_sha256'] == sha(image)
    assert candidate['image_bytes'] == len(image)
    with Image.open(STAGE / 'campus-atlas.webp') as opened:
        assert opened.size == (7168, 3072)
    assert len(candidate['records']) == 130
    assert len(candidate['render_tiles']) == 8
    assert candidate['checks']['record_count'] == 130
    assert candidate['checks']['garden_detail']['source_path_count'] >= 4
    assert all(candidate['checks']['garden_detail']['label_centres_on_source_roads'])
    assert candidate['checks']['garden_detail']['checks'] and max(candidate['checks']['garden_detail']['checks'].values()) < .01
    parking = candidate['checks']['central_parking_detail']
    assert parking['visible_area_m2'] > 100 and parking['marking_groups'] >= 40
    assert all(parking[key] < .01 for key in ('roof_overlap_m2', 'water_overlap_m2', 'markings_outside_parking_m2'))
    paving = candidate['checks']['paving_artifact_cleanup']
    assert 100 < paving['removed_area_m2'] < 20_000 and paving['retained_piece_count'] > 0
    assert paving['discarded_piece_count'] > 0
    assert paving['outside_original_paving_m2'] < .01
    marks = candidate['checks']['road_mark_detail']
    assert set(marks['source_routes']) == {'北区东西联系路', '湖区南侧横路', '中区东西路'}
    assert marks['dash_count'] >= 80
    assert all(marks[key] < .01 for key in ('outside_existing_road_m2', 'roof_overlap_m2', 'water_overlap_m2'))
    b08 = candidate['checks']['b08_roof_detail']
    assert b08['seam_count'] >= 40
    assert all(b08[key] < .01 for key in ('seams_outside_source_roof_m2', 'seams_on_glazed_roof_m2'))
    assert candidate['checks']['north_detail']['north_extension_material_slots_preserved'] > 0
    solar = candidate['checks']['solar_array_finish']
    assert solar['source_ids'] == ['B07', 'E24']
    assert solar['material_count'] == solar['retained_mesh_count'] == 2
    assert solar['world_positions_preserved'] and solar['topology_preserved']
    solar_objects = candidate['solar_array_finish_revision']['objects']
    assert {row['source_id'] for row in solar_objects} == {'B07', 'E24'}
    assert all(row['world_positions_preserved'] and row['topology_preserved']
               and row['upper_face_count'] > 0 and row['source_array_area_m2'] > 0
               for row in solar_objects)
    glazing = candidate['glazing_recess_revision']
    assert glazing['checks']['material_count'] == len(glazing['materials'])
    assert not glazing['checks']['mesh_positions_changed']
    assert {'B06 window reflection 0', 'B06 window reflection 1',
            'B06 window reflection 2', 'B07 bluegrey window'} <= set(glazing['materials'])
    photo_facades = candidate['surface_finish_revision']['photo_supported_central_materials']
    assert len(photo_facades) == 8
    assert set(photo_facades) <= set(candidate['architectural_edge_revision']['materials'])
    assert solar['E24_seams_aligned_to_existing_world_grid']
    roofs = candidate['central_roof_finish_revision']
    assert roofs['checks'] == candidate['checks']['central_roof_finish']
    assert roofs['checks']['material_count'] == len(roofs['materials']) == 4
    assert roofs['checks']['retained_mesh_count'] == len(roofs['objects']) == 3
    assert {row['source_id'] for row in roofs['objects']} == {'B06', 'B07', 'B08'}
    assert roofs['checks']['new_geometry_count'] == 0
    assert all(row['world_positions_preserved'] and row['topology_preserved']
               and row['upper_face_count'] > 0 and row['maximum_tangent_frame_error'] < 1e-5
               for row in roofs['objects'])
    stone = candidate['stone_edge_contact_revision']
    assert stone['checks'] == candidate['checks']['stone_edge_contact']
    assert stone['checks']['material_count'] == len(stone['materials']) >= 3
    assert not stone['checks']['mesh_positions_changed'] and stone['checks']['new_geometry_count'] == 0
    assert candidate['checks']['independent_source_roof_max_difference_m'] < .01
    assert candidate['checks']['independent_projection_max_difference_px'] < .02
    forms = candidate['checks']['canopy_forms']
    assert forms == candidate['canopy_form_revision']['checks']
    assert forms['form_count'] == len(forms['prototype_sha256']) == 12
    assert set(forms['form_usage']) == set(forms['prototype_sha256'])
    assert forms['shared_mesh_count'] > 0
    assert all(len(h) == 64 and set(h) <= set('0123456789abcdef')
               for h in [forms['assignment_sha256'], *forms['prototype_sha256'].values()])
    assert forms['crown_count'] == sum(forms['form_usage'].values()) == 1858
    assert forms['source_centres_and_object_transforms_preserved']
    assert forms['mesh_vertex_xy_preserved'] and forms['boundary_uv_preserved']
    assert forms['minimum_uv_triangle_and_corner_cross'] > .005
    assert forms['maximum_uv_displacement'] < forms['uv_displacement_limit'] == .055
    assert sum(v for k, v in forms['form_usage'].items() if k.startswith('low_lobed')) == 8
    lake = candidate['checks']['lake_surface']
    assert lake == candidate['lake_surface_revision']['checks']
    assert lake['material_count'] == 1 and lake['visible_water_mesh_count'] == 6
    expected_lake_meshes = {'Lake bounded submerged bed', 'Lake continuous water',
        'Lake outer coping', 'Lake sloped stone revetment', 'Lake upper coping',
        'Lake upper promenade', *(f'Lake water gradient {i}' for i in range(6))}
    assert lake['retained_mesh_count'] == len(lake['geometry_sha256']) == 12
    assert set(lake['geometry_sha256']) == expected_lake_meshes
    assert lake['world_vertices_topology_material_indices_transforms_and_visibility_preserved']
    assert lake['shore_tint_preserved'] and lake['other_material_graphs_preserved']
    assert lake['world_and_lighting_preserved'] and lake['IOR_preserved']
    assert lake['new_geometry_count'] == lake['displacement_link_count'] == 0
    assert abs(lake['water_level_m_estimate'] + 1.1) < 1e-6
    assert lake['source_outline_area_difference_m2'] < 1e-6
    assert lake['normal_layer_count'] == 2 and lake['roughness_range_estimate'] == [.075, .135]
    assert 0 <= lake['ripple_tint_maximum_estimate'] <= .18
    assert abs(lake['transmission_estimate'] - .42) < 1e-6
    assert all(len(h) == 64 and set(h) <= set('0123456789abcdef') for h in
        [*lake['geometry_sha256'].values(), lake['shore_attribute_sha256'], lake['material_graph_sha256'],
         lake['other_material_graphs_sha256'], lake['world_graph_sha256'], lake['lighting_sha256']])
    baseline = json.loads((ASSETS / 'campus-atlas.json').read_bytes())
    assert candidate['checks']['paving_edge_finish']['new_material_count'] == 1
    assert forms == baseline['checks']['canopy_forms']
    if 'lake_surface' in baseline['checks']:
        assert lake == baseline['checks']['lake_surface']
    daylight_notes = {'leaf_material_context', 'checkpoint_context'}
    assert {k: v for k, v in candidate['daylight_revision'].items() if k not in daylight_notes} == {
        k: v for k, v in baseline['daylight_revision'].items() if k not in daylight_notes}
    for key in daylight_notes:
        if key in baseline['daylight_revision']:
            candidate['daylight_revision'][key] = baseline['daylight_revision'][key]
    meadow = candidate['checks']['meadow_surface']
    assert meadow == candidate['meadow_surface_revision']['checks']
    assert meadow == baseline['checks']['meadow_surface']
    assert meadow['material_count'] == 4
    assert meadow['materials'] == sorted(baseline['fine_ground_and_roof_revision']['meadow_materials'])
    assert meadow['retained_mesh_count'] == len(meadow['geometry_sha256']) == 9
    for key in ('world_vertices_topology_material_indices_transforms_uv_and_visibility_preserved',
                'source_branch_nodes_and_internal_links_preserved', 'other_material_graphs_preserved',
                'world_and_lighting_preserved'):
        assert meadow[key], key
    assert meadow['other_material_count'] == 273
    assert meadow['new_geometry_count'] == meadow['displacement_link_count'] == 0
    assert meadow['grain_scale_m_inverse_estimate'] == 1.3 and meadow['grain_detail_estimate'] == 2.5
    assert meadow['warm_ratio_range_estimate'] == [.70, .96]
    assert meadow['roughness_range_estimate'] == [.88, .97]
    assert meadow['neutral_fleck_effective_range_estimate'] == [.936, 1.048]
    assert len(meadow['recipes']) == 4
    for row in meadow['recipes']:
        woodland = 'woodland' in row['material'].lower()
        assert row['green_detail_mix_estimate'] == (.18 if woodland else .42)
        assert row['warm_detail_mix_estimate'] == (.10 if woodland else .12)
        assert row['source_branch_nodes_preserved']
    fingerprints = [*meadow['geometry_sha256'].values(), *meadow['material_graph_sha256'].values(),
        *meadow['source_branch_graph_sha256'].values(), meadow['other_material_graphs_sha256'],
        meadow['world_graph_sha256'], meadow['lighting_sha256']]
    assert all(len(h) == 64 and set(h) <= set('0123456789abcdef') for h in fingerprints)
    foliage = candidate['checks']['foliage_surface']
    assert foliage == candidate['foliage_surface_revision']['checks']
    assert foliage == baseline['checks']['foliage_surface']
    assert foliage['materials'] == ['Garden detailed canopy sprite', 'Pilot detailed canopy image']
    assert foliage['material_count'] == 2 and foliage['other_material_count'] == 275
    assert foliage['crown_count'] == 1858 and foliage['shared_mesh_count'] == len(foliage['shared_mesh_sha256']) == 21
    assert foliage['image_sha256'] == candidate['sources']['output/garden-tree-canopy.png']
    for key in ('all_crown_vertices_topology_material_indices_transforms_uv_and_visibility_preserved',
                'original_image_sampling_and_alpha_surface_chain_preserved',
                'other_material_graphs_preserved', 'world_and_lighting_preserved'):
        assert foliage[key], key
    assert foliage['new_geometry_count'] == foliage['displacement_link_count'] == 0
    assert foliage['leaf_group_scale_m_inverse_estimate'] == .70
    assert foliage['leaf_group_tone_mix_estimate'] == .55
    assert foliage['baked_light_gain_range_estimate'] == [.85, 1.30]
    assert foliage['colour_only_edge_saturation_range_estimate'] == [.45, 1]
    assert foliage['normal_distance_m_estimate'] == .018 and foliage['normal_strength_estimate'] == .18
    assert set(foliage['hsv_ranges_preserved']) == set(foliage['materials'])
    for ranges in foliage['hsv_ranges_preserved'].values():
        assert set(ranges) == {'Hue', 'Saturation', 'Value'}
        for key, expected in {'Hue': [.46, .515], 'Saturation': [.96, 1.12], 'Value': [1.08, 1.42]}.items():
            assert len(ranges[key]) == 2 and all(abs(a-b) < 1e-6 for a,b in zip(ranges[key], expected))
    fingerprints = [*foliage['shared_mesh_sha256'], foliage['source_objects_geometry_sha256'],
        *foliage['material_graph_sha256'].values(), *foliage['alpha_surface_chain_sha256'].values(),
        foliage['source_colour_assignment_sha256'], foliage['other_material_graphs_sha256'],
        foliage['world_graph_sha256'], foliage['lighting_sha256']]
    assert all(len(h) == 64 and set(h) <= set('0123456789abcdef') for h in fingerprints)
    facade = candidate['checks']['facade_contrast']
    assert facade == candidate['facade_contrast_revision']['checks']
    wall_gains = {'Atlas architecture neutral residential plaster.001': 1.10,
        'Atlas architecture institutional pale plaster.001': 1.08,
        'Atlas architecture weathered campus plaster.001': 1.10,
        'Atlas architecture muted campus stone trim.001': 1.20}
    pane_names = {f'Atlas architecture glass {i}.001' for i in range(4)}
    assert set(facade['materials']) == set(wall_gains) | pane_names
    assert facade['material_count'] == 8 and facade['other_material_count'] == 269
    assert facade['retained_mesh_count'] == len(set(facade['source_ids'])) == 111
    assert set(facade['source_ids']) <= {row['id'] for row in candidate['records']}
    for key in ('world_vertices_topology_material_indices_slots_transforms_uv_and_visibility_preserved',
                'source_colour_nodes_internal_links_and_other_bsdf_links_preserved',
                'object_inventory_and_mesh_count_preserved', 'other_material_graphs_preserved',
                'world_and_lighting_preserved'):
        assert facade[key], key
    assert facade['new_geometry_count'] == facade['displacement_link_count'] == 0
    assert len(facade['recipes']) == 8
    assert {row['material'] for row in facade['recipes']} == set(facade['materials'])
    for row in facade['recipes']:
        assert row['output_colour_clamped']
        if row['material'] in wall_gains:
            assert len(row['colour_gain_actual']) == 3
            assert all(abs(value-wall_gains[row['material']]) < 1e-6 for value in row['colour_gain_actual'])
        else:
            assert row['height_interpolation'] == 'SMOOTHSTEP' and row['height_clamped']
            for key, expected in [('generated_z_from_range_actual', [.08, .92]),
                                  ('colour_gain_range_actual', [.64, 1.04])]:
                assert len(row[key]) == 2 and all(abs(a-b) < 1e-6 for a,b in zip(row[key], expected))
            assert abs(row['roughness_preserved_actual']-.23) < 1e-6
    fingerprints = [facade['source_mesh_geometry_uv_sha256'], *facade['material_graph_sha256'].values(),
        *facade['source_branch_graph_sha256'].values(), facade['other_material_graphs_sha256'],
        facade['world_graph_sha256'], facade['lighting_sha256']]
    assert all(len(h) == 64 and set(h) <= set('0123456789abcdef') for h in fingerprints)
    spatial = candidate['checks']['spatial_continuity_and_scale']
    assert spatial == candidate['spatial_revision']['checks']
    assert spatial['grass_material_count'] == 4 and spatial['grass_mesh_count'] == 9
    assert spatial['context_mesh_count'] == 2 and spatial['new_paint_mesh_count'] == 3
    assert spatial['illustrative_vehicle_count'] == 14 and spatial['vehicle_part_count'] == 42
    for key in ('grass_geometry_uv_preserved', 'context_vertices_topology_transforms_uv_and_visibility_preserved',
                'original_contexts_hidden', 'north_source_weight_zero_outside_2d_coverage',
                'vehicle_local_meshes_preserved', 'other_existing_materials_preserved',
                'other_visible_meshes_preserved', 'world_and_lighting_preserved'):
        assert spatial[key], key
    assert spatial['field_size'][0] == 768 and max(spatial['field_cell_m']) < 1.7
    assert spatial['boundary_inner_blend_m_estimate'] == 18 and spatial['woodland_inner_blend_m_estimate'] == 12
    assert spatial['superseded_visible_paint_hidden'] == 80
    assert {row['id'] for row in spatial['parking_areas']} == {'central-lake', 'north-parking', 'center-parking'}
    for row in spatial['parking_areas']:
        assert row['complete_illustrative_bay_count'] > 0 and row['markings_outside_source_area_m2'] < 1e-7
        assert row['bay_width_m_estimate'] == 2.65 and row['bay_depth_m_estimate'] == 5.1
        assert row['aisle_m_estimate'] == 6.2
    for row in spatial['vehicles']:
        assert abs(row['width_m']-1.8) < 1e-4 and abs(row['length_m']-4.2) < 1e-4
        assert len(row['parts']) == len(row['local_meshes_sha256']) == 3
        assert abs(row['clearance_above_parking_m']-.16) < 1e-4
    assert .1599 < spatial['minimum_vehicle_clearance_m'] < .1601
    for row in spatial['parking_areas']:
        assert row['connected_side_aisle_m_estimate'] == 6.2
        assert row['connected_access_component_count'] == 1 and row['every_bay_has_complete_front_aisle']
        assert row['markings_in_access_aisles_m2'] < 1e-7
    detail = candidate['checks']['detail_contact_and_layout']
    assert detail == candidate['detail_contact_revision']['checks']
    assert detail['shrub_count'] == len(detail['shrubs']) == 8
    assert detail['wheel_count'] == len(detail['wheels']) == 56 and detail['vehicle_count'] == 14
    assert detail['pitch_count'] == len(detail['pitches']) == 4
    assert detail['other_existing_visible_meshes_preserved'] and detail['original_material_graphs_preserved']
    assert detail['world_roof_faces_preserved']
    for row in detail['shrubs']:
        assert row['xy_local_mesh_uv_slots_rotation_scale_visibility_preserved'] and row['source_shrub_preserved']
        assert abs(row['new_crown_world_z'][1]-row['source_world_z'][1]-.08) < 1e-5
        assert row['new_crown_world_z'][0] <= row['source_world_z'][1] and row['new_crown_world_z'][0] > .606
    assert all(row['footprint_inside_assigned_bay'] and row['contact_above_paving_m'] == .002 for row in detail['wheels'])
    for row in detail['pitches']:
        assert row['closed_rectangle_and_four_corners'] and row['running_lane_geometry_materials_preserved']
        assert row['paint_outside_inner_field_m2'] < 1e-7 and row['retained_base_lane_face_count'] > 0
    craft = candidate['checks']['source_craft_and_contact']
    assert craft == candidate['craft_revision']['checks']
    assert craft['other_existing_visible_meshes_preserved'] and craft['existing_material_graphs_preserved']
    assert craft['world_roof_faces_preserved']
    canopy = craft['canopy']
    assert canopy['count'] == canopy['original_crowns_hidden_count'] == sum(canopy['prototype_usage'].values()) == 1850
    assert canopy['prototype_count'] == canopy['shared_mesh_count'] == len(canopy['shared_mesh_sha256']) == 24
    assert canopy['preserved_shrub_count'] == 8 and canopy['retained_source_centre_count'] == 1971
    assert canopy['alpha_free'] and canopy['image_node_count'] == 0
    assert canopy['instanced_polygon_triangle_count'] == canopy['additional_evaluated_triangles'] <= 3_000_000
    assert canopy['blades_per_clump_actual'] == 96
    assert canopy['instanced_polygon_triangle_count'] == sum(canopy['prototype_triangle_counts'][key]*value for key,value in canopy['prototype_usage'].items())
    for key in canopy['prototype_usage']:
        assert canopy['prototype_face_counts'][key] == 96*canopy['prototype_clump_counts'][key] <= 864
        assert canopy['prototype_triangle_counts'][key] == 2*canopy['prototype_face_counts'][key]
    for ranges in canopy['material_hsv_ranges_actual'].values():
        for key, expected in [('Hue',(.485,.512)),('Saturation',(.98,1.12)),('Value',(1.04,1.24))]:
            assert ranges[key]['clamped'] and all(abs(x-y)<1e-6 for x,y in zip(ranges[key]['to'],expected))
    for key in ('original_crown_local_mesh_uv_transforms_preserved', 'source_xy_and_bounds_preserved',
                'source_tree_and_trunk_meshes_transforms_visibility_preserved', 'existing_material_graphs_and_world_preserved'):
        assert canopy[key], key
    assert canopy['new_top_above_source_leaf_top_m_range'][1] <= .35001
    assert canopy['minimum_lower_foliage_height_overlap_m'] >= .24999
    for key in ('roof_overlap_outside_retained_crown_envelope_m2', 'water_overlap_outside_retained_crown_envelope_m2'):
        assert canopy[key] < 1e-7
    ground = craft['ground']
    assert ground['moved_water_bank_object_count'] == 2 and ground['root_count'] == 16
    assert ground['paving_root_count'] == 15 and ground['walk_root_count'] == 1
    assert ground['wall_batch_count'] == 1 and ground['wall_face_count'] == sum(ground['wall_face_counts'].values()) > 0
    assert ground['root_source_outside_original_pit_ground_m2'] < 1e-7
    assert ground['root_top_input_geometry_sha256'] == ground['root_top_output_geometry_sha256']
    for key in ('water_bank_local_mesh_uv_topology_materials_and_xy_transforms_preserved',
                'root_top_geometry_uv_slots_transforms_and_visibility_preserved',
                'other_existing_visible_meshes_preserved', 'existing_material_graphs_preserved', 'world_and_roof_faces_preserved'):
        assert ground[key], key
    for row, z in zip(ground['water_bank'], (.052, .058)):
        assert abs(row['new_world_z_m'] - z) < 1e-6
        assert row['input_xy_geometry_sha256'] == row['output_xy_geometry_sha256']
    assert craft['canopy']['per_construction_fields'] == ['original_crown_state_sha256', 'source_tree_and_trunk_sha256', 'contact_height_sha256', 'minimum_lower_foliage_height_overlap_m', 'new_top_above_source_leaf_top_m_range']
    facade_depth = craft['facade']
    assert facade_depth['eligible_object_count'] == len(facade_depth['source_ids']) == 98
    assert facade_depth['window_assembly_count'] > 1000
    assert facade_depth['moved_vertex_count'] == facade_depth['window_assembly_count'] * 120
    assert facade_depth['inward_translation_m_estimate'] == .115
    assert facade_depth['topology_changed']
    assert facade_depth['opened_opaque_surround_count'] == facade_depth['verified_opaque_opening_count'] == facade_depth['window_assembly_count']
    assert sum(facade_depth['opening_ray_first_hit_material_counts'].values()) == facade_depth['window_assembly_count']
    assert facade_depth['added_inner_corner_vertex_count'] == facade_depth['window_assembly_count'] * 8
    assert facade_depth['net_added_face_count'] == facade_depth['window_assembly_count'] * 10
    assert facade_depth['replaced_original_surround_cap_face_count'] == facade_depth['window_assembly_count'] * 2
    assert facade_depth['annular_front_back_face_count'] == facade_depth['window_assembly_count'] * 8
    assert facade_depth['inner_reveal_face_count'] == facade_depth['window_assembly_count'] * 4
    for key in ('all_windows_source_edge_matched', 'all_assembly_box_patterns_verified',
                'non_target_original_vertices_preserved',
                'non_target_original_faces_vertex_indices_materials_smooth_selection_and_loop_uv_preserved',
                'original_surround_24_vertices_and_four_outer_faces_preserved',
                'pane_assembly_original_topology_and_loop_uv_preserved',
                'material_slots_uv_configuration_transforms_and_visibility_preserved',
                'sills_walls_roofs_preserved', 'excluded_architecture_preserved',
                'opaque_trim_alpha_and_zero_transmission_preserved'):
        assert facade_depth[key], key
    assert facade_depth['input_mesh_geometry_uv_visibility_sha256'] != facade_depth['output_mesh_geometry_uv_visibility_sha256']
    assert facade_depth['after_depth_range_m']['recess'][0] > .065 - .0005
    assert facade_depth['after_depth_range_m']['wall_clearance'][0] > .044 - .0005
    landscape = candidate['checks']['landscape_detail']
    revision = candidate['landscape_detail_revision']
    assert revision['checks'] == landscape and revision['reference_alignment_status'] == 'not_met'
    assert {'basis', 'method', 'estimated', 'preserved'} <= set(revision)
    assert set(landscape) == {'surface', 'beds', 'courtyards'}
    assert all(isinstance(value, dict) for value in landscape.values())
    surface = landscape['surface']
    assert surface['material_count'] == len(surface['recipes']) == 4
    assert {row['material'] for row in surface['recipes']} == set(baseline['fine_ground_and_roof_revision']['meadow_materials'])
    assert surface['new_geometry_count'] == surface['displacement_link_count'] == 0
    assert surface['roughness_range_estimate'] == [.90, .98]
    for key in ('source_pigment_and_boundary_shader_preserved',
                'other_existing_material_graphs_preserved', 'existing_visible_meshes_preserved',
                'world_and_roof_faces_preserved'):
        assert surface[key], key
    assert surface['existing_visible_mesh_count'] > 0
    for row in surface['recipes']:
        assert row['input_graph_sha256'] != row['output_graph_sha256']
        assert all(len(h) == 64 and set(h) <= set('0123456789abcdef')
                   for h in (row['input_graph_sha256'], row['output_graph_sha256']))
    assert all(len(surface[key]) == 64 and set(surface[key]) <= set('0123456789abcdef')
               for key in ('existing_visible_mesh_sha256', 'other_existing_material_graphs_sha256',
                           'world_graph_sha256', 'roof_faces_sha256'))
    beds = landscape['beds']
    assert beds['bed_count'] == len(beds['beds']) == beds['new_mesh_count'] == beds['new_object_count'] == 4
    assert beds['new_material_count'] == 3 and beds['new_image_count'] == beds['new_tree_centre_count'] == 0
    assert beds['preserved_source_tree_centre_count'] == 1971 and beds['preserved_oval_shrub_count'] == 8
    assert beds['total_polygon_triangle_count'] == sum(row['polygon_triangle_count'] for row in beds['beds']) <= 120000
    assert beds['all_existing_geometry_uv_transforms_visibility_and_material_slots_preserved']
    assert beds['all_existing_material_graphs_world_and_roof_faces_preserved']
    for row in beds['beds']:
        assert row['support_area_m2'] > 0 and row['world_bounds_m'][0][2] < row['source_cap_z_m']
        assert all(value < 1e-7 for key, value in row.items()
                   if key.endswith('_overlap_m2') or key.startswith('outside_'))
    courts = landscape['courtyards']
    assert courts['site_count'] == len(courts['sites']) == 3
    assert courts['new_mesh_count'] == 2 and courts['new_material_count'] == 6 and courts['new_image_count'] == 0
    assert courts['actual_overlay_outside_source_m2'] < 1e-7 and courts['actual_overlay_exclusion_intersection_m2'] < 1e-7
    assert courts['source_mesh_input_sha256'] == courts['source_mesh_output_sha256']
    assert courts['all_overlay_faces_upward'] and courts['minimum_overlay_normal_z'] > .9999
    assert courts['existing_image_inventory_preserved']
    for key in ('original_source_meshes_geometry_uv_slots_transforms_visibility_preserved',
                'other_existing_visible_meshes_preserved', 'existing_material_graphs_preserved',
                'original_fine_stone_course_and_normal_graphs_retained', 'world_and_roof_faces_preserved'):
        assert courts[key], key
    site = candidate['checks']['site_finish']
    assert site == candidate['site_finish_revision']['checks']
    assert candidate['site_finish_revision']['reference_alignment_status'] == 'not_met'
    assert set(site) == {'facade', 'hardscape', 'planting'}
    finish = site['facade']
    assert finish['eligible_object_count'] == len(finish['source_ids']) == 98
    assert finish['source_ids'] == facade_depth['source_ids']
    assert finish['window_assembly_count'] == finish['verified_glass_first_hit_count'] == facade_depth['window_assembly_count']
    assert sum(finish['glass_first_hit_material_counts'].values()) == finish['window_assembly_count']
    assert finish['geometry_topology_uv_pose_input_sha256'] == finish['geometry_topology_uv_pose_output_sha256']
    assert finish['changed_material_face_count'] > 0 and finish['new_material_count'] <= 40
    assert finish['new_object_count'] == finish['new_mesh_count'] == finish['new_image_count'] == 0
    for key in ('all_target_geometry_topology_uv_pose_visibility_preserved',
                'old_material_slot_prefixes_preserved', 'unassigned_face_material_indices_preserved',
                'upper_faces_above_height_plus_0_2m_materials_preserved', 'source_roof_face_records_preserved',
                'other_scene_meshes_preserved', 'all_original_material_graphs_preserved', 'world_graph_preserved'):
        assert finish[key], key
    transition = site['hardscape']
    assert 0 < transition['used_target_count'] <= transition['candidate_mesh_count'] == 7
    assert transition['new_mesh_count'] == transition['new_image_count'] == 0
    assert transition['native_weight_bound'] == [0.0, 1.0]
    assert not transition['interior_road_boundary_used_for_weight'] and not transition['woodland_channel_used_for_weight']
    assert transition['hardscape_transition_m_estimate'] == 12.0
    for key in ('geometry_preserved', 'only_declared_material_slots_changed',
                'all_original_material_graphs_preserved', 'source_branch_preserved',
                'existing_image_inventory_preserved', 'source_weight_zero_outside_2d_coverage',
                'world_and_roof_faces_preserved'):
        assert transition[key], key
    planting = site['planting']
    assert planting['source_region_count'] == len(planting['sites']) == 11
    assert planting['new_object_count'] == planting['new_mesh_count'] == 2
    assert planting['new_material_count'] == planting['new_image_count'] == planting['new_tree_centre_count'] == 0
    assert planting['preserved_source_tree_centre_count'] == 1971 and planting['preserved_oval_shrub_count'] == 8
    assert planting['total_polygon_triangle_count'] == sum(row['polygon_triangle_count'] for row in planting['sites']) <= 100000
    assert planting['all_existing_geometry_uv_transforms_visibility_and_material_slots_preserved']
    assert planting['all_existing_material_graphs_world_and_roof_faces_preserved']
    assert all(value < 1e-7 for value in planting['actual_overlap_m2'].values())
    assert planting['actual_overlap_between_new_regions_m2'] < 1e-7
    for row in planting['sites']:
        assert row['support_area_m2'] > 0
        assert row['world_bounds_m'][0][2] < row['source_cap_z_m']
        assert 0 < row['maximum_top_above_source_cap_m_estimate'] < .6
        assert row['outside_source_region_m2_at_float32_tolerance'] < 1e-7
        assert row['outside_support_m2_at_float32_tolerance'] < 1e-7
    validate_site_sources(candidate)
    validate_paving_regularization(candidate)
    validate_context_roads(candidate)
    assert len(candidate['sources']) == 33 and 'scripts/paving_cleanup.py' in candidate['sources']
    assert 'scripts/context_roads.py' in candidate['sources']
    assert candidate['camera'] == baseline['camera']
    assert candidate['roof_faces_world'] == baseline['roof_faces_world']
    tree_centres = lambda value: sorted(tuple(row[1]) for row in value['landscape_revision']['tree_pairs'])
    assert tree_centres(candidate) == tree_centres(baseline)
    assert candidate['checks']['canopy_relief']['positions_and_xy_scale_sha256'] == baseline['checks']['canopy_relief']['positions_and_xy_scale_sha256']
    for name, fingerprint in candidate['sources'].items():
        assert sha((ROOT / name).read_bytes()) == fingerprint, name
    for name in ASSET_NAMES[:-1]:
        assert (ASSETS / name).is_file(), name

    candidate['promotion'] = {
        'method': 'Validated native stage, source and unchanged roof geometry checks before stable path replacement',
        'command': '/opt/anaconda3/bin/python scripts/promote_full_atlas.py',
        'script_sha256': sha(Path(__file__).read_bytes()),
    }
    candidate['source_geometry_continuity'] = {
        'status': 'passed',
        'baseline_image_sha256': baseline['image_sha256'],
        'method': 'Exact roof-face and camera comparison; sorted source-tree world XYZ comparison, ignoring temporary object names',
        'roof_record_count': len(candidate['roof_faces_world']),
        'source_tree_count': len(tree_centres(candidate)),
        'roof_faces_sha256': sha(json.dumps(candidate['roof_faces_world'], sort_keys=True, separators=(',', ':')).encode()),
        'tree_world_xyz_sha256': sha(json.dumps(tree_centres(candidate), separators=(',', ':')).encode()),
        'criteria': ['No roof or camera changes', 'No source-tree world XYZ changes'],
    }
    candidate['visual_review'] = {
        'status': 'pending_native_and_browser_visual_review',
        'scope': 'Promotion validates native inputs; visual inspection and current-image browser evidence are sealed separately.',
        'reference_alignment_status': 'not_met',
    }
    preserve_website_metadata(candidate, baseline)
    candidate['render_status'] = 'integrated_user_visual_acceptance_pending'
    candidate['artifact_manifest'] = [
        {'path': f'public/assets/{name}', 'bytes': len(data), 'sha256': sha(data)}
        for name, data in ((name, image if name == 'campus-atlas.webp' else (ASSETS / name).read_bytes()) for name in ASSET_NAMES)
    ]
    candidate['artifact_manifest_policy'] = 'Current nine shared binary/sidecar assets; this metadata JSON has no recursive self-hash.'
    metadata = shared_budget(candidate)
    total = sum(entry['bytes'] for entry in candidate['artifact_manifest']) + len(metadata)
    assert total == candidate['budget']['asset_bytes_actual']
    assert total < LIMIT, (total, LIMIT)
    assert sum(path.stat().st_size for path in STAGE.rglob('*') if path.is_file()) < 192 * 1024**2
    replace(ASSETS / 'campus-atlas.webp', image)
    replace(ASSETS / 'campus-atlas.json', metadata)
    print(f'Atlas ready: {candidate["webp_quality"]} WebP quality; 10 shared assets: {total:,} / {LIMIT:,} bytes')


if __name__ == '__main__':
    main()
