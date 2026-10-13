"""Export source-backed gates and sports locations without rendering or saving a scene.

Blender --background --factory-startup --python-exit-code 1 \
  --python scripts/export_atlas_places.py

The only generated file is /tmp/taihu-full/atlas-services.json. These display
anchors use retained source traces, not the legacy demo POI coordinates.
"""
import hashlib
import json
import math
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
CACHE = Path('/tmp/taihu-full')
OUTPUT = CACHE / 'atlas-services.json'
MAX_OUTPUT = 1024 ** 2
MAX_CACHE = 192 * 1024 ** 2
DISPLAY = {'satellite': (1152, 1920), 'north-extension': (1000, 900)}
# These are browsing groups of the existing source atlas, not official zones.
REGIONS = {'gate1': 'extension', 'gate2': 'middle', 'gate3': 'south',
           'north-track': 'north', 'central-track': 'middle',
           'south-track': 'south', 'far-north-track': 'extension'}


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':')).encode()


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bounds(points):
    return [min(p[0] for p in points), min(p[1] for p in points),
            max(p[0] for p in points), max(p[1] for p in points)]


def box_distance(point, box):
    return math.hypot(max(box[0] - point[0], 0, point[0] - box[2]),
                      max(box[1] - point[1], 0, point[1] - box[3]))


def main():
    assert CACHE.is_dir(), CACHE
    old_bytes = OUTPUT.stat().st_size if OUTPUT.exists() else 0
    cache_bytes = sum(p.stat().st_size for p in CACHE.rglob('*') if p.is_file())
    assert cache_bytes - old_bytes + MAX_OUTPUT < MAX_CACHE
    paths = {'scene': ROOT / 'model/campus/campus.blend',
             'layout': ROOT / 'model/campus/layout.json',
             'satellite_export': ROOT / 'model/campus/references/satellite-export.json',
             'north_export': ROOT / 'model/campus/references/north-extension.json',
             'atlas_metadata_input': ROOT / 'public/assets/campus-atlas.json',
             'atlas_image': ROOT / 'public/assets/campus-atlas.webp',
             'export_script': Path(__file__).resolve()}
    source_hashes = {key: file_sha(path) for key, path in paths.items()}
    meta = json.loads(paths['atlas_metadata_input'].read_text())
    layout = json.loads(paths['layout'].read_text())
    exports = {'satellite': json.loads(paths['satellite_export'].read_text()),
               'north-extension': json.loads(paths['north_export'].read_text())}
    assert source_hashes['atlas_image'] == meta['image_sha256']
    for key in ('scene', 'layout', 'satellite_export', 'north_export'):
        assert meta['sources'][str(paths[key].relative_to(ROOT))] == source_hashes[key], key
    assert len(layout['gates']) == 3 and len(layout['tracks']) == 4
    assert {row['id'] for row in layout['gates'] + layout['tracks']} == set(REGIONS)
    assert all(len(row['position']) == 2 for row in layout['gates'])
    assert all(len(row['center']) == 2 and row['long'] > 0 and row['wide'] > 0
               for row in layout['tracks'])
    assert len(meta['records']) == len(meta['roof_faces_world']) == 130
    region_rows = {row['id']: row for row in meta['regions']}
    assert set(REGIONS.values()) <= set(region_rows)

    bpy.ops.wm.open_mainfile(filepath=str(paths['scene']))
    scene = bpy.context.scene
    bpy.context.view_layer.update()
    origin = [float(value) for value in scene['origin_epsg3857'].split(',')]
    metric = float(scene['metric_scale'])
    e = exports['satellite']['extent']
    expected_origin = [e['xmin'] + 600 / 1152 * (e['xmax'] - e['xmin']),
                       e['ymax'] - 850 / 1920 * (e['ymax'] - e['ymin'])]
    assert max(abs(a - b) for a, b in zip(origin, expected_origin)) < 1e-8
    assert abs(metric - math.cos(math.radians(31.578))) < 1e-12
    for source, exported in exports.items():
        reference = exported['extent']['spatialReference']
        assert reference.get('latestWkid', reference['wkid']) == 3857
        factor = 2 if source == 'satellite' else 1
        assert (exported['width'], exported['height']) == tuple(v * factor for v in DISPLAY[source])

    def source_world(point, source):
        extent = exports[source]['extent']; width, height = DISPLAY[source]
        return Vector(((extent['xmin'] + point[0] / width * (extent['xmax'] - extent['xmin']) - origin[0]) * metric,
                       (extent['ymax'] - point[1] / height * (extent['ymax'] - extent['ymin']) - origin[1]) * metric,
                       0.0))

    camera_meta = meta['camera']; width, height = meta['width'], meta['height']
    assert width > 0 and height > 0 and camera_meta['ortho_scale'] > 0
    camera_data = bpy.data.cameras.new('Atlas services projection')
    camera_data.type = 'ORTHO'; camera_data.ortho_scale = camera_meta['ortho_scale']
    camera = bpy.data.objects.new('Atlas services projection', camera_data)
    scene.collection.objects.link(camera)
    camera.location = camera_meta['position']; camera.rotation_euler = camera_meta['rotation_euler']
    scene.render.resolution_x = width; scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.pixel_aspect_x = scene.render.pixel_aspect_y = 1
    bpy.context.view_layer.update()
    ppm = width / camera_meta['ortho_scale']
    rx, ry, rz = camera_meta['rotation_euler']
    independent_errors = []

    def independent_project(point):
        # Inverse Rz Ry Rx, evaluated with Python double-precision scalars.
        x, y, z = [float(point[i]) - camera_meta['position'][i] for i in range(3)]
        x, y = math.cos(rz) * x + math.sin(rz) * y, -math.sin(rz) * x + math.cos(rz) * y
        x, z = math.cos(ry) * x - math.sin(ry) * z, math.sin(ry) * x + math.cos(ry) * z
        y, z = math.cos(rx) * y + math.sin(rx) * z, -math.sin(rx) * y + math.cos(rx) * z
        return [width / 2 + x * ppm, height / 2 - y * ppm]

    def project(point):
        projected = world_to_camera_view(scene, camera, Vector(point))
        result = [projected.x * width, (1 - projected.y) * height]
        independent = independent_project(point)
        difference = max(abs(a - b) for a, b in zip(result, independent))
        assert difference < .02, (point, difference)
        independent_errors.append(difference)
        return result

    records = []; source_point_checks = []
    for kind, rows in [('gate', layout['gates']), ('sport', layout['tracks'])]:
        for row in rows:
            ident = row['id']; source = row.get('source', 'satellite')
            point = row['position'] if kind == 'gate' else row['center']
            world = source_world(point, source)
            if kind == 'gate':
                ob = scene.objects[ident + ' ' + row['name']]
                assert ob.type == 'EMPTY' and ob.hide_render
                actual = ob.matrix_world.translation
                source_error = max(abs(world[i] - actual[i]) for i in range(3))
                # A display-only 56m ground-plane window around the retained node.
                frame_points = [Vector((world.x + x, world.y + y, 0))
                                for x in (-28, 28) for y in (-28, 28)]
                focus_basis = 'Estimated 56m ground-plane framing window; not gate width or pedestrian access extent'
                description = row['name'] + '。位置沿用原校园模型中依据校园图和道路开口解释的定位节点；不是实测入口或通行认证。'
                name_status = 'retained source gate label; position interpreted'
            else:
                ob = scene.objects[row['name']]
                assert ob.type == 'MESH' and ob['id'] == ident
                assert len(ob.modifiers) == 0
                vertices = [ob.matrix_world @ vertex.co for vertex in ob.data.vertices]
                xy_bounds = bounds(vertices)
                actual = Vector(((xy_bounds[0] + xy_bounds[2]) / 2,
                                 (xy_bounds[1] + xy_bounds[3]) / 2, 0))
                source_error = max(abs(world[i] - actual[i]) for i in range(2))
                frame_points = vertices
                focus_basis = 'Complete retained source track mesh projected with the current atlas camera; derived surface markings and vertical dimensions are estimated'
                description = row['name'] + '。场地范围沿用固定影像描绘及保留的原运动场网格；运动标线和高度为展示估算，不代表规范场地认证。'
                name_status = 'retained regional sports label; not school-confirmed facility name'
            assert source_error < .001, (ident, source_error)
            anchor = project(world)
            actual_anchor = project(actual)
            actual_projection_error = max(abs(a - b) for a, b in zip(anchor, actual_anchor))
            assert actual_projection_error < .02, (ident, actual_projection_error)
            region = REGIONS[ident]
            distances = {key: box_distance(anchor, value['bounds']) for key, value in region_rows.items()}
            assert min(distances, key=distances.get) == region, (ident, distances)
            assert sum(abs(value - distances[region]) < 1e-7 for value in distances.values()) == 1, (ident, distances)
            focus = bounds([project(value) for value in frame_points])
            assert focus[0] <= anchor[0] <= focus[2] and focus[1] <= anchor[1] <= focus[3]
            assert 0 <= focus[0] < focus[2] <= width and 0 <= focus[1] < focus[3] <= height
            assert all(math.isfinite(value) for value in anchor + focus)
            source_point_checks.append({'source_id': ident, 'retained_object': ob.name,
                                        'world_source_max_difference_m': source_error,
                                        'retained_source_point_projection_max_difference_px': actual_projection_error,
                                        'region_bounds_distance_px': distances})
            records.append({'id': 'place:' + ident, 'kind': kind, 'region': region,
                            'name': row['name'], 'description': description, 'name_status': name_status,
                            'anchor': anchor, 'focus_bounds': focus, 'source': source, 'source_id': ident,
                            'source_pixel_point': point, 'source_world_point_m': list(world),
                            'source_object': ob.name, 'focus_basis': focus_basis,
                            'coordinate_status': 'retained source trace; estimated presentation geometry',
                            'region_basis': 'Existing atlas browsing group, checked against its uniquely nearest regional roof bounds; not official school zoning'})
    assert len(records) == 7 and len({row['id'] for row in records}) == 7
    assert all('polygons' not in row for row in records)
    assert all(source_hashes[key] == file_sha(path) for key, path in paths.items())
    output = {'schema_version': 1, 'status': 'candidate_source_projection_checked',
              'image_sha256': meta['image_sha256'], 'camera_sha256': digest(camera_meta),
              'camera': camera_meta, 'width': width, 'height': height,
              'records': records, 'source_hashes': source_hashes,
              'source_paths': {key: str(path.relative_to(ROOT)) for key, path in paths.items()},
              'source_collection_sha256': digest(meta['sources']),
              'georeference': {'origin_epsg3857_from_retained_scene': origin,
                               'metric_scale_from_retained_scene': metric,
                               'display_pixels': DISPLAY, 'source_extents': {key: value['extent'] for key, value in exports.items()},
                               'anchor_z_m_estimate': 0.0},
              'checks': {'record_count': len(records), 'gate_count': 3, 'sport_count': 4,
                         'roof_record_count_unchanged': len(meta['records']),
                         'retained_georef_matches_source_builder': True,
                         'independent_projection_max_difference_px': max(independent_errors),
                         'source_point_checks': source_point_checks,
                         'all_inputs_preserved': True, 'render_called': False, 'scene_saved': False},
              'generation_command': '/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup --python-exit-code 1 -t 2 --python scripts/export_atlas_places.py',
              'method': 'Read saved campus.blend georeference, transform original gate/track source pixels and project through current formal atlas camera. Independently compare scalar Euler projection and retained scene gate nodes/track centres.',
              'limitations': 'Source trace and presentation estimates, not surveyed POI positions, a routing network, gate access status or official zoning. Existing demo campusData coordinates and building-number guesses are not used. Track framing uses retained source mesh, not an updated pitch inventory. atlas_metadata_input SHA describes the input snapshot before later service embedding, not a self-hash of enriched metadata.'}
    payload = encoded(output) + b'\n'
    assert len(payload) < MAX_OUTPUT
    assert cache_bytes - old_bytes + len(payload) < MAX_CACHE
    OUTPUT.write_bytes(payload)
    print(json.dumps({'status': output['status'], 'path': str(OUTPUT), 'bytes': len(payload),
                      'sha256': file_sha(OUTPUT), 'records': len(records),
                      'independent_projection_max_difference_px': max(independent_errors)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
