"""Estimated low foliage confined to eleven retained north/academic bed caps.

Called after the landscape passes with campus_expansion.py globals. No source
plant positions, old object data, visibility, material graph or image is changed.
The small folded faces are display samples, not individual surveyed plants.
"""
import ast
import hashlib
import math
from collections import Counter
from pathlib import Path


PREFIX = 'Planting retained low foliage '
CAPS = ('Study planted bed ground', 'Joined source academic planted strips')
NOMINAL_Z = (.342, .437)
INSET_M = .18
CELL_M = 1.10
LOW_M, HIGH_M = .11, .42
MAX_HEIGHT_M = .60
MAX_TRIANGLES = 100000


def _literal_assignment(tree, name):
    matches = [node.value for node in tree.body if isinstance(node, ast.Assign)
               and any(isinstance(target, ast.Name) and target.id == name
                       for target in node.targets)]
    assert len(matches) == 1, name
    return ast.literal_eval(matches[0])


def _source_recipes(root, joined_record):
    """Read the exact retained recipe outlines; never select by green material."""
    tree = ast.parse((root/'scripts/north_study.py').read_bytes())
    additions = [node.value for node in tree.body if isinstance(node, ast.AugAssign)
                 and isinstance(node.target, ast.Name) and node.target.id == 'beds'
                 and isinstance(node.value, ast.List)]
    assert len(additions) == 1
    seams = ast.literal_eval(additions[0])
    apartment = _literal_assignment(tree, 'apartment_beds')
    joined = _literal_assignment(ast.parse((root/'scripts/campus_study.py').read_bytes()),
                                 'new_bed_pixels')
    assert len(seams) == 5 and len(apartment) == 4 and len(joined) == 2
    assert joined == joined_record
    return [('north-seam-'+str(i), CAPS[0], pixels) for i, pixels in enumerate(seams)] \
        + [('north-apartment-seam-'+str(i), CAPS[0], pixels) for i, pixels in enumerate(apartment)] \
        + [('academic-strip-'+str(i), CAPS[1], pixels) for i, pixels in enumerate(joined)]


def _object_state(objects):
    return {obj.name: [obj.type, obj.data.name if obj.data else None,
        [list(row) for row in obj.matrix_world], obj.hide_render, obj.hide_viewport,
        obj.hide_get(), list(obj.color)] for obj in objects}


def add_planting_finish(state):
    import bpy
    from shapely.geometry import Point, Polygon, box
    from shapely.ops import unary_union

    scene, native, joined = state['s'], state['n'], state['ctx']
    digest, snapshot, graph = state['lake_digest'], state['spatial_mesh_snapshot'], state['facade_graph_state']
    helpers = state['landscape_modules']['landscape_beds']
    flat_cap, volume = helpers['_flat_cap'], helpers['_volume']
    shape_values, polygons = helpers['_shape_values'], helpers['_polygons']
    xy_tol = helpers['XY_TOL_M']
    root = Path(__file__).resolve().parents[1]
    recipes = _source_recipes(root, joined['ground_revision']['academic_planted_strips_source_pixels'])
    assert len(recipes) == 11 and len(recipes) <= 16
    assert not any(obj.name.startswith(PREFIX) for obj in scene.objects)
    bpy.context.view_layer.update()
    old_objects = list(scene.objects)
    old_meshes = snapshot(obj for obj in old_objects if obj.type == 'MESH')
    old_states = _object_state(old_objects)
    old_graphs = {mat.name: digest(graph(mat.node_tree)) for mat in bpy.data.materials if mat.use_nodes}
    old_world, old_roofs = digest(graph(scene.world.node_tree)), digest(state['faces'])
    mesh_count, material_count, image_count = len(bpy.data.meshes), len(bpy.data.materials), len(bpy.data.images)
    pairs = state['pairs']
    assert len(pairs) == 1971
    tree_xy = sorted([[round(float(row[1][0]), 6), round(float(row[1][1]), 6)] for row in pairs])
    shrubs = [obj for obj in old_objects if obj.name.startswith('Garden source oval shrub canopy ')]
    assert len(shrubs) == 8
    shrub_xy = sorted([list(obj['source_position_xy']) for obj in shrubs])

    cap_shapes = {name: flat_cap(scene.objects[name]) for name in CAPS}
    cap_snapshot = snapshot(scene.objects[name] for name in CAPS)
    for name, nominal_z in zip(CAPS, NOMINAL_Z):
        assert abs(cap_shapes[name][1]-nominal_z) < 1e-5, (name, cap_shapes[name][1])
    cap_union = unary_union([shape for shape, z in cap_shapes.values()])
    roof_faces = []
    for faces in state['faces'].values():
        for face in faces:
            shape = Polygon([point[:2] for point in face])
            assert shape.is_valid and shape.area > 0
            roof_faces.append(shape)
    roof = state['roofs'].union(unary_union(roof_faces))
    roads = unary_union([state['asphalt'], native['roads'], joined['road']])
    # Some retained paved underlays predate the academic planting overlay.
    # Exclude their exposed area, while explicitly excluding corrected hard
    # courts even where the obsolete lawn cap survives underneath them.
    underlay_hardscape = unary_union([native['paved'], joined['existing_paved'],
        state['paving'], state['detail_union']]).difference(cap_union.buffer(xy_tol))
    hard_cap_names = ('Pilot N34 photo-visible mineral court',
        'Joined source academic hard courtyard', 'Joined source north parking',
        'Joined paved pedestrian margins', 'Study continuous plazas')
    hard_caps = {name: flat_cap(scene.objects[name])[0] for name in hard_cap_names}
    hardscape = underlay_hardscape.union(unary_union(list(hard_caps.values())))
    retained_foliage_envelopes = []
    for obj in old_objects:
        if obj in shrubs or obj.name.startswith('Landscape low foliage '):
            points = [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]
            assert points
            retained_foliage_envelopes.append(box(min(p.x for p in points), min(p.y for p in points),
                                                 max(p.x for p in points), max(p.y for p in points)))
    exclusions = {'roof': roof, 'water': state['water'], 'road': roads,
        'hardscape': hardscape, 'sports': state['sports'],
        'retained_oval_shrub_and_previous_low_foliage_envelope': unary_union(retained_foliage_envelopes)}
    excluded = unary_union([shape.buffer(.04) for shape in exclusions.values()])

    # Reuse the three already verified opaque pigments without touching nodes.
    materials = [bpy.data.materials['Landscape low foliage pigment '+str(i)] for i in range(3)]
    material_values = []
    for mat, rgb in zip(materials, helpers['PALETTE']):
        bs = mat.node_tree.nodes.get('Principled BSDF')
        assert bs and not any(socket.is_linked for socket in bs.inputs)
        values = {'material': mat.name, 'base_colour': list(bs.inputs['Base Color'].default_value),
            'roughness': float(bs.inputs['Roughness'].default_value),
            'metallic': float(bs.inputs['Metallic'].default_value),
            'alpha': float(bs.inputs['Alpha'].default_value),
            'emission_strength': float(bs.inputs['Emission Strength'].default_value)}
        assert all(abs(a-b) < 1e-6 for a, b in zip(values['base_colour'], (*rgb, 1)))
        assert abs(values['roughness']-.90) < 1e-6 and values['alpha'] == 1
        assert values['metallic'] == values['emission_strength'] == 0
        material_values.append(values)

    batches = {name: {'v': [], 'f': [], 'i': [], 'parts': []} for name in CAPS}
    claimed, entries = Polygon(), []
    for key, source_name, source_pixels in recipes:
        source_shape, cap_z = cap_shapes[source_name]
        trace = native['shape'](source_pixels)
        source_region = trace.intersection(source_shape)
        assert source_region.is_valid and source_region.area > 1, key
        supported = source_region.buffer(-INSET_M).difference(excluded).difference(claimed.buffer(.04))
        supported = unary_union([part for part in polygons(supported) if part.area > .04])
        assert supported.is_valid and supported.area > 1, (key, source_region.area, supported.area)
        assert supported.area/source_region.area > .30, (key, 'Excessively excluded source bed')
        assert supported.difference(trace).area < 1e-7
        assert supported.difference(source_shape).area < 1e-7
        bottom_z = cap_z-.004
        vertices, faces, indices, geometry = volume(supported, cap_z, bottom_z, key, CELL_M, LOW_M, HIGH_M)
        batch = batches[source_name]
        start_v, start_f = len(batch['v']), len(batch['f'])
        batch['v'].extend(vertices)
        batch['f'].extend(tuple(index+start_v for index in face) for face in faces)
        batch['i'].extend(indices)
        batch['parts'].append({'key': key, 'pixels': source_pixels, 'source_region': source_region,
            'supported': supported, 'cap_z': cap_z, 'bottom_z': bottom_z, 'geometry': geometry,
            'vertex_slice': (start_v, len(batch['v'])), 'face_slice': (start_f, len(batch['f']))})
        claimed = claimed.union(supported)

    new_objects, batch_entries, total_triangles, projected_parts = [], [], 0, []
    for batch_index, source_name in enumerate(CAPS):
        batch = batches[source_name]
        assert batch['parts']
        name = PREFIX+('north seams' if batch_index == 0 else 'academic strips')
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(batch['v'], [], batch['f']); mesh.update()
        assert len(mesh.vertices) == len(batch['v']) and len(mesh.polygons) == len(batch['f'])
        for mat in materials:
            mesh.materials.append(mat)
        for face, index in zip(mesh.polygons, batch['i']):
            face.material_index = index; face.use_smooth = False
        obj = bpy.data.objects.new(name, mesh); scene.collection.objects.link(obj)
        obj['source_object'] = source_name
        obj['detail_basis'] = 'Retained source planting cap; low continuous foliage height estimated'
        assert not obj.modifiers and len(mesh.uv_layers) == 0
        assert all(abs(value-(1 if i == j else 0)) < 1e-12
                   for i, row in enumerate(obj.matrix_world) for j, value in enumerate(row))
        new_objects.append(obj)
        actual_vertices = [list(vertex.co) for vertex in mesh.vertices]
        actual_faces = [[list(face.vertices), face.material_index, face.use_smooth] for face in mesh.polygons]
        assert all(math.isfinite(value) for point in actual_vertices for value in point)
        batch_triangles = sum(len(face.vertices)-2 for face in mesh.polygons)
        total_triangles += batch_triangles
        batch_entries.append({'object': name, 'source_object': source_name,
            'source_keys': [part['key'] for part in batch['parts']],
            'geometry_sha256': digest([actual_vertices, actual_faces, [mat.name for mat in mesh.materials]]),
            'vertex_count': len(mesh.vertices), 'face_count': len(mesh.polygons),
            'polygon_triangle_count': batch_triangles})
        for part in batch['parts']:
            v0, v1 = part['vertex_slice']; f0, f1 = part['face_slice']
            points, faces = actual_vertices[v0:v1], mesh.polygons[f0:f1]
            supported, source_region = part['supported'], part['source_region']
            assert all(supported.buffer(xy_tol).covers(Point(point[:2])) for point in points), part['key']
            assert all(source_region.buffer(xy_tol).covers(Point(point[:2])) for point in points), part['key']
            projections = []
            for face in faces:
                polygon = Polygon([actual_vertices[index][:2] for index in face.vertices])
                if polygon.area > 1e-10:
                    assert polygon.is_valid, part['key']
                    projections.append(polygon)
            actual_xy = unary_union(projections)
            assert actual_xy.is_valid and actual_xy.area > 1
            projected_parts.append(actual_xy)
            outside_source = actual_xy.difference(source_region.buffer(xy_tol)).area
            outside_support = actual_xy.difference(supported.buffer(xy_tol)).area
            overlaps = {label+'_overlap_m2': actual_xy.intersection(shape).area
                        for label, shape in exclusions.items()}
            assert outside_source < 1e-7 and outside_support < 1e-7
            assert all(value < 1e-7 for value in overlaps.values()), (part['key'], overlaps)
            body_count = part['geometry']['sealed_body_face_count']
            edges = Counter(tuple(sorted((a, b))) for face in mesh.polygons[f0:f0+body_count]
                for a, b in zip(tuple(face.vertices), tuple(face.vertices)[1:]+tuple(face.vertices)[:1]))
            assert edges and all(count == 2 for count in edges.values())
            bounds = [[min(point[i] for point in points) for i in range(3)],
                      [max(point[i] for point in points) for i in range(3)]]
            height = bounds[1][2]-part['cap_z']
            assert abs(bounds[0][2]-part['bottom_z']) < 1e-6
            assert bounds[0][2] < part['cap_z'] and 0 < height < MAX_HEIGHT_M
            entries.append({'source_key': part['key'], 'source_object': source_name,
                'source_pixels': part['pixels'], 'object': name,
                'source_region_xy_sha256': digest(shape_values(source_region)),
                'source_region_area_m2': source_region.area,
                'source_world_bounds_m': [list(source_region.bounds[:2]), list(source_region.bounds[2:])],
                'source_cap_z_m': part['cap_z'], 'support_xy_sha256': digest(shape_values(supported)),
                'support_area_m2': supported.area, 'support_inset_m_estimate': INSET_M,
                'world_bounds_m': bounds, 'contact_bottom_z_m': bounds[0][2],
                'maximum_top_above_source_cap_m_estimate': height,
                'outside_source_region_m2_at_float32_tolerance': outside_source,
                'outside_support_m2_at_float32_tolerance': outside_support,
                'face_count': f1-f0, 'polygon_triangle_count': sum(len(face.vertices)-2 for face in faces),
                **part['geometry'], **overlaps})

    actual_union = unary_union(projected_parts)
    overlap_between_new_regions = sum(shape.area for shape in projected_parts)-actual_union.area
    assert abs(overlap_between_new_regions) < 1e-7
    assert len(new_objects) == 2 and len(new_objects) <= 4 and len(entries) == 11
    assert total_triangles <= MAX_TRIANGLES
    bpy.context.view_layer.update()
    assert len(scene.objects) == len(old_objects)+2 and len(bpy.data.meshes) == mesh_count+2
    assert len(bpy.data.materials) == material_count and len(bpy.data.images) == image_count
    assert old_meshes == snapshot(scene.objects[name] for name in old_meshes)
    assert old_states == _object_state(old_objects)
    assert old_graphs == {name: digest(graph(bpy.data.materials[name].node_tree)) for name in old_graphs}
    assert old_world == digest(graph(scene.world.node_tree)) and old_roofs == digest(state['faces'])
    assert cap_snapshot == snapshot(scene.objects[name] for name in CAPS)
    assert tree_xy == sorted([[round(float(row[1][0]), 6), round(float(row[1][1]), 6)] for row in state['pairs']])
    assert shrub_xy == sorted([list(obj['source_position_xy']) for obj in shrubs])
    source_paths = ('scripts/north_study.py', 'scripts/campus_study.py', 'scripts/north_pilot_detail.py',
        'scripts/landscape_beds.py', 'model/campus/layout.json', 'model/campus/references/satellite-export.json',
        'model/campus/references/satellite.jpg')
    return {'source_region_count': len(entries), 'retained_support_object_count': len(CAPS),
        'source_keys': [entry['source_key'] for entry in entries], 'sites': entries, 'batches': batch_entries,
        'new_object_count': 2, 'new_mesh_count': 2, 'active_material_count': len(materials),
        'new_material_count': 0, 'new_image_count': 0, 'new_tree_centre_count': 0,
        'preserved_source_tree_centre_count': len(pairs), 'preserved_source_tree_xy_sha256': digest(tree_xy),
        'preserved_oval_shrub_count': len(shrubs), 'preserved_oval_shrub_xy_sha256': digest(shrub_xy),
        'source_caps_sha256': digest(cap_snapshot),
        'source_inputs_sha256': {path: hashlib.sha256((root/path).read_bytes()).hexdigest() for path in source_paths},
        'total_polygon_triangle_count': total_triangles, 'maximum_polygon_triangle_count': MAX_TRIANGLES,
        'triangle_count_method': 'Sum(len(polygon.vertices)-2) for two stored meshes without modifiers; not dependency-graph evaluation',
        'material_values_actual': material_values,
        'material_graph_sha256': {mat.name: digest(graph(mat.node_tree)) for mat in materials},
        'actual_projected_area_m2': actual_union.area,
        'actual_overlap_between_new_regions_m2': max(0, overlap_between_new_regions),
        'actual_overlap_m2': {label: actual_union.intersection(shape).area for label, shape in exclusions.items()},
        'exclusion_xy_sha256': {label: digest(shape_values(shape)) for label, shape in exclusions.items()},
        'hardscape_exclusion_basis': 'Exact existing corrected courts, parking, pedestrian margins and north plaza caps, plus exposed paved underlays outside the two retained planting caps; no claim that academic planting has no original paved underlay',
        'all_existing_geometry_uv_transforms_visibility_and_material_slots_preserved': True,
        'all_existing_material_graphs_world_and_roof_faces_preserved': True,
        'per_construction_preservation': {'existing_mesh_count': len(old_meshes),
            'existing_mesh_state_sha256': digest(old_meshes), 'existing_object_state_sha256': digest(old_states),
            'existing_material_graphs_sha256': digest(old_graphs), 'world_graph_sha256': old_world,
            'roof_faces_sha256': old_roofs},
        'cross_construction_equality_exclude': ['per_construction_preservation'],
        'limitations': 'Low foliage heights, inset and folded-face density are display estimates within eleven source-recipe regions and their actual retained caps. No new planting layout, tree centres, species or shrub inventory is asserted. Eight oval shrubs and the prior four low-foliage beds are excluded. Original paved underlays may remain beneath academic planting. Stored XY checks allow 0.2mm float32 numeric tolerance, not survey accuracy. Native construction and visual acceptance remain separate gates.'}
