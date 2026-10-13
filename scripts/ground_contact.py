"""Close retained garden bank/root finishes against their existing ground.

Called once from campus_expansion with add_ground_contact(globals()). No input files,
source XY outlines, existing material graphs or root top meshes are rewritten.
Heights and shallow contact walls are display estimates, not a terrain survey.
"""
import bpy
from shapely.geometry import Point, Polygon, LineString
from shapely.geometry.polygon import orient
from shapely.ops import unary_union


def add_ground_contact(state):
    scene, native = state['s'], state['n']
    digest, snapshot = state['lake_digest'], state['spatial_mesh_snapshot']
    graph_state = state['facade_graph_state']
    numeric_xy = 2e-4  # Match original double outlines to retained float32 caps.
    assert scene.objects.get('Ground contact retained bank and root walls') is None
    bpy.context.view_layer.update()

    def polygons(shape):
        if shape.is_empty:
            return []
        parts = list(shape.geoms) if shape.geom_type == 'MultiPolygon' else [shape]
        assert all(part.geom_type == 'Polygon' and part.is_valid for part in parts)
        return sorted((orient(part.normalize(), 1) for part in parts),
                      key=lambda part: tuple(part.bounds))

    def ring_values(ring):
        values = [tuple(value) for value in list(ring.coords)[:-1]]
        start = min(range(len(values)), key=lambda index: values[index])
        return values[start:] + values[:start]

    def shape_values(shape):
        return [[ring_values(part.exterior),
                 sorted(ring_values(ring) for ring in part.interiors)]
                for part in polygons(shape)]

    def cap_faces(obj):
        vertices = [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]
        result = []
        for face in obj.data.polygons:
            values = [vertices[index] for index in face.vertices]
            zs = [value.z for value in values]
            assert max(zs) - min(zs) < 1e-6, obj.name
            footprint = Polygon([(value.x, value.y) for value in values])
            assert footprint.is_valid and footprint.area > 0, obj.name
            result.append((footprint, zs[0]))
        assert result, obj.name
        return result

    def flat_cap(obj):
        caps = cap_faces(obj)
        heights = [row[1] for row in caps]
        assert max(heights) - min(heights) < 1e-6, obj.name
        return unary_union([row[0] for row in caps]), heights[0]

    pond = scene.objects['Garden satellite visible small eastern pond']
    bank = scene.objects['Garden source eastern pond bank']
    soil = scene.objects['Expansion retained-tree root finish']
    rim = scene.objects['Expansion retained-tree root stone course']
    assert all(obj.type == 'MESH' and not obj.hide_render
               for obj in (pond, bank, soil, rim))
    assert pond.parent is None and bank.parent is None
    assert len(pond.data.materials) == len(bank.data.materials) == 1
    assert pond.data.materials[0].name == 'Garden source eastern small pond'
    assert bank.data.materials[0].name == 'Garden eastern pond stone bank'
    assert len(soil.data.materials) == len(rim.data.materials) == 1
    assert soil.data.materials[0].name == 'Expansion context tree root soil'
    assert rim.data.materials[0].name == 'Expansion low planting edge'

    targets = {pond.name, bank.name}
    protected_before = snapshot(obj for obj in scene.objects
        if obj.type == 'MESH' and not obj.hide_render and obj.name not in targets)
    target_before = snapshot([pond, bank])
    material_before = {material.name: digest(graph_state(material.node_tree))
        for material in bpy.data.materials if material.use_nodes}
    world_before = digest(graph_state(scene.world.node_tree))
    roofs_before = digest(state['faces'])
    object_names_before = {obj.name for obj in scene.objects}
    material_names_before = {material.name for material in bpy.data.materials}

    pond_shape, old_pond_z = flat_cap(pond)
    bank_shape, old_bank_z = flat_cap(bank)
    assert abs(old_pond_z - .275) < 1e-6 and abs(old_bank_z - .281) < 1e-6
    # The fixed source supplied the water outline and its .23 m stone ring.
    # Keep those actual caps; only their display elevation changes here.
    assert pond_shape.difference(state['ground'].buffer(numeric_xy)).area < 1e-7
    assert bank_shape.difference(state['ground'].buffer(numeric_xy)).area < 1e-7
    assert pond_shape.intersection(bank_shape).area < 1e-7
    pond_input = digest(shape_values(pond_shape))
    bank_input = digest(shape_values(bank_shape))
    for obj, old_z, target_z in ((pond, old_pond_z, .052), (bank, old_bank_z, .058)):
        obj.location.z += target_z - old_z
    bpy.context.view_layer.update()
    pond_after, pond_z = flat_cap(pond)
    bank_after, bank_z = flat_cap(bank)
    assert abs(pond_z - .052) < 1e-6 and abs(bank_z - .058) < 1e-6
    assert shape_values(pond_shape) == shape_values(pond_after)
    assert shape_values(bank_shape) == shape_values(bank_after)
    target_after = snapshot([pond, bank])
    for name, old in target_before.items():
        new = target_after[name]
        assert old[:2] == new[:2] and old[3:] == new[3:], name
        assert all(old[2][i][j] == new[2][i][j]
                   for i in range(4) for j in range(4) if (i, j) != (2, 3)), name

    root_rows = state['root_pits']
    root_shapes = state['root_pit_shapes']
    assert len(root_rows) == len(root_shapes) == 16
    entries = sorted(zip(root_rows, root_shapes),
        key=lambda row: (*row[0]['centre_world'], row[0]['radius_m_estimate']))
    source_xy_radius = [[*row['centre_world'], row['radius_m_estimate']]
                       for row, _ in entries]
    assert len({tuple(row[:2]) for row in source_xy_radius}) == 16
    source_union = unary_union(root_shapes)
    assert source_union.difference(state['pit_ground']).area < 1e-7
    assert source_union.difference(state['paving'].union(state['detail_union'])).area < 1e-7
    for excluded in ('asphalt', 'roofs', 'water', 'planting_mask'):
        assert source_union.intersection(state[excluded]).area < 1e-7, excluded

    soil_faces, rim_faces = cap_faces(soil), cap_faces(rim)
    claimed_soil, claimed_rim = set(), set()
    root_caps = []
    for row, source_shape in entries:
        point = Point(row['centre_world'])
        assert state['pit_ground'].covers(point)
        assert abs(source_shape.area - row['area_m2']) < 1e-7
        assert source_shape.difference(state['pit_ground']).area < 1e-7
        is_walk = state['detail_union'].covers(point)
        basis = .455 if is_walk else .31
        expected_soil = .462 if is_walk else .347
        expected_rim = expected_soil + .006
        assert abs(row['finish_z_m'] - expected_soil) < 1e-6
        support = state['detail_union'] if is_walk else state['paving']
        assert source_shape.difference(support).area < 1e-7

        def select(caps, claimed, expected_z):
            selected = []
            envelope = source_shape.buffer(numeric_xy)
            for index, (shape, z) in enumerate(caps):
                if abs(z - expected_z) >= 1e-6 or not envelope.covers(shape.representative_point()):
                    continue
                assert index not in claimed
                claimed.add(index)
                selected.append(shape)
            assert selected
            return unary_union(selected)

        soil_cap = select(soil_faces, claimed_soil, expected_soil)
        rim_cap = select(rim_faces, claimed_rim, expected_rim)
        assert soil_cap.boundary.hausdorff_distance(source_shape.boundary) < numeric_xy
        assert soil_cap.difference(source_shape.buffer(numeric_xy)).area < 1e-7
        assert rim_cap.difference(soil_cap.buffer(numeric_xy)).area < 1e-7
        # Use the retained cap Z exactly, including its original float32 value.
        soil_z = next(z for shape, z in soil_faces
            if abs(z - expected_soil) < 1e-6 and soil_cap.covers(shape.representative_point()))
        rim_z = next(z for shape, z in rim_faces
            if abs(z - expected_rim) < 1e-6 and rim_cap.covers(shape.representative_point()))
        root_caps.append((row, source_shape, soil_cap, rim_cap, basis, soil_z, rim_z))
    assert len(claimed_soil) == len(soil_faces) and len(claimed_rim) == len(rim_faces)
    assert sum(row[4] == .31 for row in root_caps) == 15
    assert sum(row[4] == .455 for row in root_caps) == 1

    batch = native['Mesh']('Ground contact retained bank and root walls')
    face_count = {'pond_outer': 0, 'pond_inner': 0,
                  'root_soil': 0, 'root_rim_outer': 0, 'root_rim_inner': 0}
    closed_loops = 0
    wall_lines = []

    def walls(shape, bottom, top, material, category, envelope=None, reference=None):
        nonlocal closed_loops
        assert top > bottom
        for part in polygons(shape):
            for ring in [part.exterior, *part.interiors]:
                values = ring_values(ring)
                assert ring.is_ring and len(values) >= 3
                closed_loops += 1
                for a, b in zip(values, values[1:] + values[:1]):
                    line = LineString([a, b])
                    assert line.length > 0
                    if envelope is not None:
                        assert line.difference(envelope.buffer(numeric_xy)).length < 1e-7
                    selected = category
                    if reference is not None:
                        midpoint = line.interpolate(.5, normalized=True)
                        selected += '_outer' if midpoint.distance(reference.boundary) < numeric_xy else '_inner'
                    batch.face([(a[0], a[1], bottom), (b[0], b[1], bottom),
                                (b[0], b[1], top), (a[0], a[1], top)], material)
                    face_count[selected] += 1
                    wall_lines.append(line)

    # The bank exterior contacts unchanged grass; its inner loops meet water.
    # Separating these walls avoids overlapping top surfaces and duplicate caps.
    for part in polygons(bank_after):
        exterior = Polygon(ring_values(part.exterior))
        walls(exterior, .05, bank_z, bank.data.materials[0], 'pond_outer', bank_after)
        for ring in part.interiors:
            inner = Polygon(ring_values(ring))
            # Reverse the isolated hole so its wall faces towards the water.
            values = list(reversed(ring_values(inner.exterior)))
            assert inner.boundary.difference(pond_after.boundary.buffer(numeric_xy)).length < 1e-7
            closed_loops += 1
            for a, b in zip(values, values[1:] + values[:1]):
                batch.face([(a[0], a[1], pond_z), (b[0], b[1], pond_z),
                            (b[0], b[1], bank_z), (a[0], a[1], bank_z)], bank.data.materials[0])
                face_count['pond_inner'] += 1
                wall_lines.append(LineString([a, b]))

    root_records = []
    for row, source_shape, soil_cap, rim_cap, basis, soil_z, rim_z in root_caps:
        before_count = sum(face_count.values())
        walls(soil_cap, basis, soil_z, soil.data.materials[0], 'root_soil', source_shape)
        walls(rim_cap, soil_z, rim_z, rim.data.materials[0], 'root_rim', source_shape, soil_cap)
        root_records.append({'centre_world': row['centre_world'],
            'radius_m_estimate': row['radius_m_estimate'], 'basis_z_m_estimate': basis,
            'soil_top_z_m': soil_z, 'rim_top_z_m': rim_z,
            'contact_wall_face_count': sum(face_count.values()) - before_count})

    wall_object = batch.finish()
    assert len(wall_object.data.polygons) == sum(face_count.values()) > 0
    assert all(len(face.vertices) == 4 for face in wall_object.data.polygons)
    contact_scope = unary_union([bank_after, source_union]).buffer(numeric_xy)
    walls_outside_scope = unary_union(wall_lines).difference(contact_scope).length
    assert walls_outside_scope < 1e-7
    bpy.context.view_layer.update()
    protected_after = snapshot(scene.objects[name] for name in protected_before)
    assert protected_before == protected_after
    assert material_before == {name: digest(graph_state(bpy.data.materials[name].node_tree))
                               for name in material_before}
    assert material_names_before == {material.name for material in bpy.data.materials}
    assert object_names_before | {wall_object.name} == {obj.name for obj in scene.objects}
    assert world_before == digest(graph_state(scene.world.node_tree))
    assert roofs_before == digest(state['faces'])

    root_geometry = [[shape_values(soil_cap), soil_z, shape_values(rim_cap), rim_z]
                     for _, _, soil_cap, rim_cap, _, soil_z, rim_z in root_caps]
    return {
        'moved_water_bank_object_count': 2,
        'water_bank': [{'object': pond.name, 'old_world_z_m': old_pond_z, 'new_world_z_m': pond_z,
                       'input_xy_geometry_sha256': pond_input,
                       'output_xy_geometry_sha256': digest(shape_values(pond_after))},
                      {'object': bank.name, 'old_world_z_m': old_bank_z, 'new_world_z_m': bank_z,
                       'input_xy_geometry_sha256': bank_input,
                       'output_xy_geometry_sha256': digest(shape_values(bank_after))}],
        'water_bank_local_mesh_uv_topology_materials_and_xy_transforms_preserved': True,
        'water_bank_input_geometry_sha256': digest(target_before),
        'water_bank_output_geometry_sha256': digest(target_after),
        'root_count': 16, 'paving_root_count': 15, 'walk_root_count': 1,
        'root_source_xy_radius_sha256': digest(source_xy_radius),
        'root_source_footprints_sha256': digest([shape_values(shape) for _, shape in entries]),
        'root_top_input_geometry_sha256': digest(root_geometry),
        'root_top_output_geometry_sha256': digest(root_geometry),
        'root_top_geometry_uv_slots_transforms_and_visibility_preserved': True,
        'root_source_area_m2': source_union.area,
        'root_source_outside_original_pit_ground_m2': source_union.difference(state['pit_ground']).area,
        'roots': root_records,
        'wall_batch_count': 1, 'wall_object': wall_object.name,
        'closed_boundary_loop_count': closed_loops,
        'wall_face_count': len(wall_object.data.polygons), 'wall_face_counts': face_count,
        'wall_lines_outside_original_caps_numeric_envelope_m': walls_outside_scope,
        'wall_geometry_sha256': digest(snapshot([wall_object])),
        'original_top_caps_retained_no_duplicate_new_top_faces': True,
        'rendered_boundary_source_numeric_tolerance_m': numeric_xy,
        'other_existing_visible_mesh_count': len(protected_before),
        'other_existing_visible_meshes_preserved': True,
        'other_existing_visible_mesh_sha256': digest(protected_before),
        'existing_material_graphs_preserved': True,
        'existing_material_graphs_sha256': digest(material_before),
        'world_and_roof_faces_preserved': True,
        'world_graph_sha256': world_before, 'roof_faces_sha256': roofs_before,
        'limitations': 'Display contact geometry only. The 200-micrometre envelope matches '
                      'retained float32 caps to their original double XY outlines; source '
                      'footprint containment remains separate and strict. No grass hole, '
                      'surveyed water depth, new tree position or physical route is asserted. '
                      'Other-visible-mesh preservation is within this pass; generic mesh '
                      'attributes and modifiers are outside the snapshot audit.'}
