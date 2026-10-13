"""Estimated component finishes for retained peripheral window assemblies.

Run after facade_depth and the other existing late passes. Only verified face
material assignments and independent shader copies change; no mesh is rebuilt.
The satellite traces support scope and dimensions, not these unseen wall colours.
"""
from collections import Counter


PREFIX = 'Facade finish '
TRIM = 'Atlas architecture muted campus stone trim.001'
PLINTH = 'Atlas architecture muted stone plinth.001'
WALLS = {
    'academic': 'Atlas architecture institutional pale plaster.001',
    'dorm': 'Atlas architecture neutral residential plaster.001',
    'service': 'Atlas architecture weathered campus plaster.001',
}
GLASSES = {'Atlas architecture glass %s.001' % i for i in range(4)}
# These are bounded multipliers of the existing finished pigment, not sampled
# facade colours. Darker storey members reduce the shared bright horizontal grid.
PROFILES = {
    'academic': {
        'wall': (1.075, 1.025, .955),
        'surround': (.94, .945, .915),
        'window bars': (.66, .705, .72),
        'storey band': (.765, .80, .805),
        'vertical member': (.83, .855, .835),
        'sill': (.91, .925, .895),
        'plinth': (.86, .875, .855),
        'glass': (.965, 1.005, 1.03),
    },
    'dorm': {
        'wall': (1.075, 1.025, .95),
        'surround': (.925, .925, .875),
        'window bars': (.715, .725, .70),
        'storey band': (.695, .735, .71),
        'vertical member': (.80, .815, .77),
        'sill': (.89, .905, .855),
        'plinth': (.855, .865, .82),
        'glass': (1.025, 1.015, .985),
    },
    'service': {
        'wall': (.99, 1.01, 1.005),
        'surround': (.855, .885, .875),
        'window bars': (.63, .685, .70),
        'storey band': (.79, .815, .805),
        'vertical member': (.78, .82, .795),
        'sill': (.855, .88, .865),
        'plinth': (.83, .855, .835),
        'glass': (.945, .985, 1.015),
    },
}


def _immutable(ob, digest):
    """All local geometry, topology, loop UV and pose, excluding material indices."""
    me = ob.data
    return digest({'mesh': me.name, 'vertices': [[list(v.co), v.select] for v in me.vertices],
        'faces': [[list(f.vertices), f.use_smooth, f.select] for f in me.polygons],
        'edges': [[list(e.vertices), e.select] for e in me.edges],
        'uv': {uv.name: [list(loop.uv) for loop in uv.data] for uv in me.uv_layers},
        'active_uv': me.uv_layers.active_index,
        'render_uv': [uv.name for uv in me.uv_layers if uv.active_render],
        'attribute_schema': {a.name: [a.data_type, a.domain] for a in me.attributes},
        'matrix': [list(row) for row in ob.matrix_world],
        'hide_render': ob.hide_render, 'hide_viewport': ob.hide_viewport,
        'hide_get': ob.hide_get(), 'colour': list(ob.color)})


def _points(state, row):
    ps = [state['gp'](p, source=row.get('source', 'satellite')) for p in row['outline']]
    if sum(a.x * b.y - b.x * a.y for a, b in zip(ps, ps[1:] + ps[:1])) < 0:
        ps.reverse()
    return ps


def _surround(ob, start, pane, depth):
    """Verify the depth pass's 16 opaque outer/ring/reveal faces, not a solid box."""
    from mathutils import Vector
    tol = depth['TOL_M']; me = ob.data
    assert start >= 0
    fs = list(me.polygons[start:start + 16])
    assert len(fs) == 16 and all(len(f.vertices) == 4 for f in fs), (ob.name, start)
    assert all(me.materials[f.material_index].name == TRIM for f in fs), (ob.name, start)
    t, out = pane['tangent'], pane['outward']
    centre = pane['centre'] + out * (depth['SHIFT_M'] - .087)
    width, _, height = pane['sizes']
    indices = {i for f in fs for i in f.vertices}
    assert len(indices) == 32, (ob.name, start, 'surround vertex contract')
    xyz = [[(ob.matrix_world @ me.vertices[i].co - centre).dot(axis)
            for axis in (t, out, Vector((0, 0, 1)))] for i in indices]
    for p in xyz:
        assert min(abs(abs(p[0]) - v) for v in (width / 2, (width + .17) / 2)) < tol
        assert abs(abs(p[1]) - .075) < tol
        assert min(abs(abs(p[2]) - v) for v in (height / 2, (height + .18) / 2)) < tol
    normals = [-Vector((0, 0, 1)), Vector((0, 0, 1)), *([out] * 4),
               Vector((0, 0, 1)), -t, -Vector((0, 0, 1)), t,
               t, *([-out] * 4), -t]
    assert len(normals) == len(fs)
    for f, expected in zip(fs, normals):
        ps = [ob.matrix_world @ me.vertices[i].co for i in f.vertices]
        normal = (ps[1] - ps[0]).cross(ps[2] - ps[0]).normalized()
        assert normal.dot(expected) > .99998, (ob.name, f.index, 'surround orientation')
    # Check the front and back strips use both the true outer and inner edges;
    # the four reveals use the inner edges only. A closed/filled cap fails this.
    for offset in (2, 3, 4, 5, 11, 12, 13, 14):
        coords = [ob.matrix_world @ me.vertices[i].co - centre for i in fs[offset].vertices]
        assert any(abs(abs(p.dot(t)) - width / 2) < tol and
                   abs(abs(p.z) - height / 2) < tol for p in coords)
        assert any(abs(abs(p.dot(t)) - (width + .17) / 2) < tol or
                   abs(abs(p.z) - (height + .18) / 2) < tol for p in coords)
    for f in fs[6:10]:
        coords = [ob.matrix_world @ me.vertices[i].co - centre for i in f.vertices]
        assert all(abs(abs(p.dot(t)) - width / 2) < tol and
                   abs(abs(p.z) - height / 2) < tol for p in coords)
    return list(range(start, start + 16))


def _edge_box_role(row, box, points, tol):
    """Match retained whole-edge slabs, fins and base courses to their source edge."""
    from mathutils import Vector
    h = row['height_estimate_m']; floors = row['floors_estimate']; step = h / floors
    kind = row['kind']; width, depth, height = box['sizes']; centre = box['centre']
    matches = []
    for a, b in zip(points, points[1:] + points[:1]):
        delta = b - a; length = delta.length
        if length < .05:
            continue
        t = delta.normalized(); out = Vector((t.y, -t.x, 0))
        if box['tangent'].dot(t) < .99999 or box['outward'].dot(out) < .99999:
            continue
        rel = centre - (a + b) / 2
        along, normal = rel.dot(t), rel.dot(out)
        whole_edge = abs(width - length) < tol and abs(along) < tol
        within_edge = abs(along) + width / 2 <= length / 2 + tol
        if within_edge and abs(depth - .24) < tol and abs(height - .42) < tol and \
                abs(centre.z - .39) < tol and abs(normal) < tol:
            matches.append('plinth')
        if whole_edge and abs(depth - .32) < tol and abs(height - .65) < tol and \
                abs(centre.z - .48) < tol and abs(normal) < tol:
            matches.append('plinth')
        slab_depth, slab_height = (.64, .16) if kind == 'dorm' else (.40, .13)
        floor = round((centre.z - .23) / step)
        if whole_edge and abs(depth - slab_depth) < tol and abs(height - slab_height) < tol and \
                0 <= floor < floors and abs(centre.z - (.23 + floor * step)) < tol and abs(normal) < tol:
            matches.append('storey band')
        # Dorms also have a retained thin dark string course near the floor top.
        floor = round((centre.z - .15 - step + .28) / step)
        if kind == 'dorm' and whole_edge and abs(depth - .38) < tol and abs(height - .18) < tol and \
                0 <= floor < floors and abs(centre.z - (.15 + (floor + 1) * step - .28)) < tol and \
                abs(normal + .02) < tol:
            matches.append('storey band')
        fin_width = .20 if kind == 'academic' else .14
        count = max(1, round(length / (4.0 if kind == 'dorm' else 4.6)))
        bay = length / count; j = round((centre - a).dot(t) / bay)
        valid_j = range(0, count + 1, 2 if kind == 'academic' else count)
        expected = a + t * (j * bay) + out * .025; expected.z = h / 2
        if j in valid_j and abs(width - fin_width) < tol and abs(depth - .24) < tol and \
                abs(height - h) < tol and (centre - expected).length < tol:
            matches.append('vertical member')
    assert len(matches) <= 1, (row['id'], 'ambiguous edge component', matches)
    return matches[0] if matches else None


def _edge_box_start(ob, start, name, assignments, upper_z, tol):
    """Identify a below-roof Mesh.box start without assuming all stone is a box.

    Roof housings use the same plinth material but Mesh.solid has triangular
    caps. Unmatched primitives keep their original assignments; only a complete
    isolated six-quad, bottom-then-top candidate reaches the strict box verifier.
    """
    me = ob.data
    fs = list(me.polygons[start:start + 6])
    if len(fs) != 6 or any(f.index in assignments or len(f.vertices) != 4 or
            me.materials[f.material_index].name != name for f in fs):
        return False
    indices = [i for f in fs for i in f.vertices]
    if len(set(indices)) != 24:
        return False
    ps = [[ob.matrix_world @ me.vertices[i].co for i in f.vertices] for f in fs]
    if any(p.z >= upper_z + tol for points in ps for p in points):
        return False
    for points, expected_z in zip(ps[:2], (-1, 1)):
        normal = (points[1] - points[0]).cross(points[2] - points[0])
        if normal.length < 1e-10 or normal.normalized().z * expected_z < .99998:
            return False
    return True


def _analyse_object(state, row, ob, depth):
    """Read-only face role map and retained pane records for a post-depth mesh."""
    from mathutils import Vector
    me = ob.data; tol = depth['TOL_M']; plans = []; assignments = {}; seen = set()
    assert row['kind'] in PROFILES and ob.data.users == 1 and len(ob.modifiers) == 0, ob.name
    assert me.shape_keys is None and len(ob.vertex_groups) == 0, ob.name

    def assign(indices, role, expected_name):
        for index in indices:
            assert index not in assignments, (ob.name, index, 'overlapping role')
            assert me.materials[me.polygons[index].material_index].name == expected_name, (ob.name, index, role)
            # All source roof surfaces are above this guard. The whole-height
            # original fins reach h, and the wall core reaches h+.15.
            zs = [(ob.matrix_world @ me.vertices[i].co).z for i in me.polygons[index].vertices]
            assert max(zs) < row['height_estimate_m'] + .15 + tol, (ob.name, index, 'upper-face guard')
            assignments[index] = (role, expected_name)

    face = 0
    while face < len(me.polygons):
        original = me.materials[me.polygons[face].material_index].name
        if original not in GLASSES:
            face += 1; continue
        pane = depth['_box'](ob, face, original)
        before_depth = {**pane, 'centre': pane['centre'] + pane['outward'] * depth['SHIFT_M']}
        edge, floor, bay, out = depth['_source_match'](state, row, before_depth)
        key = (edge, floor, bay)
        assert key not in seen, (ob.name, key); seen.add(key)
        width, _, height = pane['sizes']
        assign(_surround(ob, face - 16, pane, depth), 'surround', TRIM)
        assign(range(face, face + 6), 'glass', original)
        for k in range(3):
            box = depth['_box'](ob, face + 6 + k * 6, TRIM)
            depth['_dimensions'](box, (.045, .09, height + .04), (ob.name, face, k))
            depth['_offset'](box, pane, (-width / 2 + k * width / 2, .048, 0), (ob.name, face, k))
            assign(range(face + 6 + k * 6, face + 12 + k * 6), 'window bars', TRIM)
        transom = depth['_box'](ob, face + 24, TRIM)
        depth['_dimensions'](transom, (width, .10, .045), (ob.name, face, 'transom'))
        depth['_offset'](transom, pane, (0, .053, height * .23), (ob.name, face, 'transom'))
        assign(range(face + 24, face + 30), 'window bars', TRIM)
        sill = depth['_box'](ob, face + 30, TRIM)
        depth['_dimensions'](sill, (width + .20, .27, .12), (ob.name, face, 'sill'))
        depth['_offset'](sill, pane, (0, .093 + depth['SHIFT_M'], -height / 2 - .07), (ob.name, face, 'sill'))
        assign(range(face + 30, face + 36), 'sill', TRIM)
        plans.append({'start': face, 'pane': pane, 'original': original, 'key': key})
        face += 36
    assert plans, (ob.name, 'no retained panes')
    points = _points(state, row)
    face = 0
    while face < len(me.polygons):
        if face in assignments:
            face += 1; continue
        name = me.materials[me.polygons[face].material_index].name
        if name not in (TRIM, PLINTH):
            face += 1; continue
        # Stone material also occurs on triangulated roof housing solids. Walk
        # unmatched faces singly so a non-box does not desynchronise the scan.
        if not _edge_box_start(ob, face, name, assignments,
                row['height_estimate_m'] + .15, tol):
            face += 1; continue
        box = depth['_box'](ob, face, name)
        role = _edge_box_role(row, box, points, tol)
        if role:
            assert (name == TRIM and role in ('plinth', 'storey band', 'vertical member')) or \
                   (name == PLINTH and role in ('plinth', 'storey band')), (ob.name, role, name)
            assign(range(face, face + 6), role, name)
        face += 6
    world_normal = ob.matrix_world.to_3x3().inverted().transposed()
    wall_count = 0
    for f in me.polygons:
        if f.index in assignments or me.materials[f.material_index].name != WALLS[row['kind']]:
            continue
        normal = (world_normal @ f.normal).normalized()
        zs = [(ob.matrix_world @ me.vertices[i].co).z for i in f.vertices]
        if abs(normal.z) < 1e-6 and max(zs) < row['height_estimate_m'] + .15 + tol:
            assign([f.index], 'wall', WALLS[row['kind']]); wall_count += 1
    assert wall_count > 0, (ob.name, 'no verified vertical wall')
    roles = Counter(role for role, name in assignments.values())
    assert roles['surround'] == len(plans) * 16 and roles['glass'] == len(plans) * 6
    assert roles['window bars'] == len(plans) * 24 and roles['sill'] == len(plans) * 6
    assert roles['storey band'] > 0 and roles['vertical member'] > 0 and roles['plinth'] > 0, (ob.name, roles)
    return assignments, plans


def _copy_material(base, name, gain, graph, digest):
    material = base.copy(); material.name = name
    assert material.name == name
    before = graph(base.node_tree)
    ns, links = material.node_tree.nodes, material.node_tree.links
    bs = ns.get('Principled BSDF')
    assert bs is not None and bs.inputs['Base Color'].is_linked, name
    original = bs.inputs['Base Color'].links[0].from_socket
    tint = ns.new('ShaderNodeMixRGB'); tint.name = PREFIX + 'component pigment'
    tint.blend_type = 'MULTIPLY'; tint.use_clamp = True
    tint.inputs[0].default_value = 1; tint.inputs[2].default_value = (*gain, 1)
    links.new(original, tint.inputs[1]); links.new(tint.outputs[0], bs.inputs['Base Color'])
    after = graph(material.node_tree)
    assert before['nodes'] == [node for node in after['nodes'] if node['name'] != tint.name], name
    omitted = [bs.name, bs.inputs['Base Color'].identifier]
    retained_links = [edge for edge in before['links'] if edge[2:] != omitted]
    assert all(edge in after['links'] for edge in retained_links), name
    assert len(after['links']) == len(before['links']) + 1, name
    assert tint.inputs[1].is_linked and tint.inputs[1].links[0].from_socket == original
    actual = list(tint.inputs[2].default_value)[:3]
    assert all(abs(a - b) < 1e-6 for a, b in zip(actual, gain))
    assert bs.inputs['Alpha'].default_value == 1 and not bs.inputs['Alpha'].is_linked
    assert not any(link.to_socket.name == 'Displacement' for link in links)
    return material, {'material': name, 'source_material': base.name,
        'component_pigment_gain_actual': actual, 'multiply_factor_actual': tint.inputs[0].default_value,
        'output_colour_clamped': tint.use_clamp, 'source_graph_sha256': digest(before),
        'output_graph_sha256': digest(after), 'retained_source_nodes_and_internal_links': True,
        'roughness_default_preserved_actual': bs.inputs['Roughness'].default_value,
        'normal_roughness_and_other_bsdf_inputs_preserved': True}


def _add_to_objects(state, objects, rows, depth):
    """Private small-fixture entry; production scope comes from the depth selector."""
    import bpy
    from mathutils import Vector
    scene = state['s']; digest = state['lake_digest']; graph = state['facade_graph_state']
    snapshot = state['spatial_mesh_snapshot']
    assert objects and {o['source_id'] for o in objects} == set(rows)
    assert not any(m.name.startswith(PREFIX) for m in bpy.data.materials), 'Finish pass already present'
    target_names = {ob.name for ob in objects}
    others = snapshot(ob for ob in scene.objects if ob.type == 'MESH' and ob.name not in target_names)
    originals = {m.name: digest(graph(m.node_tree)) for m in bpy.data.materials if m.use_nodes}
    world = digest(graph(scene.world.node_tree)); roof = digest(state['faces'])
    inventory = sorted([ob.name, ob.type, ob.data.name if ob.data else None] for ob in scene.objects)
    mesh_count, image_count = len(bpy.data.meshes), len(bpy.data.images)
    original_material_names = {m.name for m in bpy.data.materials}
    source_slots = {}; immutable = {}; cache = {}; recipes = []
    object_summaries = []; input_assignments = []; output_assignments = []
    role_counts = {kind: Counter() for kind in PROFILES}; building_counts = Counter()
    window_count = 0; ray_count = 0; ray_materials = Counter(); changed_faces = 0
    unassigned_proof = []; upper_proof = []
    for ob in objects:
        me = ob.data; row = rows[ob['source_id']]; kind = row['kind']
        immutable[ob['source_id']] = _immutable(ob, digest)
        source_slots[ob['source_id']] = [m.name if m else None for m in me.materials]
        assignments, plans = _analyse_object(state, row, ob, depth)
        before_indices = [f.material_index for f in me.polygons]
        input_assignments.append([ob['source_id'], digest(before_indices)])
        unassigned_before = digest([[f.index, f.material_index] for f in me.polygons if f.index not in assignments])
        upper = [f.index for f in me.polygons if max((ob.matrix_world @ me.vertices[i].co).z
            for i in f.vertices) >= row['height_estimate_m'] + .2]
        assert not set(upper).intersection(assignments), (ob.name, 'upper material assignment')
        upper_before = digest([[i, me.polygons[i].material_index] for i in upper])
        local_slots = {}
        for index, (role, original) in sorted(assignments.items()):
            key = (kind, role, original)
            if key not in cache:
                source_label = ('glass ' + original.split('glass ')[1].split('.')[0]) if role == 'glass' else \
                    'stone' if original == PLINTH else 'trim' if original == TRIM else 'wall'
                name = PREFIX + kind + ' ' + (source_label if role == 'glass' else role + ' ' + source_label)
                assert name not in bpy.data.materials
                copied, recipe = _copy_material(bpy.data.materials[original], name,
                    PROFILES[kind][role], graph, digest)
                cache[key] = copied; recipes.append({**recipe, 'kind': kind, 'role': role})
            material = cache[key]
            if key not in local_slots:
                local_slots[key] = len(me.materials); me.materials.append(material)
            me.polygons[index].material_index = local_slots[key]
            role_counts[kind][role] += 1; changed_faces += 1
        assert all(me.polygons[i].material_index != before_indices[i] for i in assignments)
        assert source_slots[ob['source_id']] == [m.name if m else None for m in me.materials][:len(source_slots[ob['source_id']])]
        assert set(m.name for m in me.materials[len(source_slots[ob['source_id']]):]) == {m.name for m in cache.values()
            if m in [me.materials[index] for index in local_slots.values()]}
        assert unassigned_before == digest([[f.index, f.material_index] for f in me.polygons if f.index not in assignments])
        assert upper_before == digest([[i, me.polygons[i].material_index] for i in upper])
        assert immutable[ob['source_id']] == _immutable(ob, digest), (ob.name, 'immutable mesh changed')
        bpy.context.view_layer.update(); depsgraph = bpy.context.evaluated_depsgraph_get()
        inverse = ob.matrix_world.inverted()
        for plan in plans:
            pane = plan['pane']; width, _, height = pane['sizes']; out = pane['outward']
            sample = pane['centre'] + pane['tangent'] * (width * .25) - Vector((0, 0, height * .22))
            origin = inverse @ (sample + out * .30)
            direction = inverse.to_3x3() @ (-out); maximum = .42 * direction.length
            hit, point, normal, index = ob.ray_cast(origin, direction.normalized(), distance=maximum, depsgraph=depsgraph)
            assert hit and plan['start'] <= index < plan['start'] + 6, (ob.name, plan['key'], 'pane first hit', index)
            current_material = me.materials[me.polygons[index].material_index]
            expected_material = cache[(kind, 'glass', plan['original'])]
            assert current_material == expected_material, (ob.name, plan['key'], current_material.name)
            ray_count += 1; ray_materials[current_material.name] += 1
        window_count += len(plans); building_counts[kind] += 1
        actual_roles = Counter(role for role, name in assignments.values())
        assigned_rows = [[index, role, old, me.materials[me.polygons[index].material_index].name]
                         for index, (role, old) in sorted(assignments.items())]
        object_summaries.append([ob['source_id'], kind, len(plans), dict(actual_roles), digest(assigned_rows)])
        output_assignments.append([ob['source_id'], digest([f.material_index for f in me.polygons])])
        unassigned_proof.append([ob['source_id'], unassigned_before])
        upper_proof.append([ob['source_id'], len(upper), upper_before])
    assert window_count == ray_count and window_count > 0
    assert len(cache) <= 40, ('Unexpected material-copy proliferation', len(cache))
    assert others == snapshot(scene.objects[name] for name in others)
    assert originals == {name: digest(graph(bpy.data.materials[name].node_tree)) for name in originals}
    assert world == digest(graph(scene.world.node_tree)) and roof == digest(state['faces'])
    assert inventory == sorted([ob.name, ob.type, ob.data.name if ob.data else None] for ob in scene.objects)
    assert mesh_count == len(bpy.data.meshes) and image_count == len(bpy.data.images)
    assert {m.name for m in bpy.data.materials} - original_material_names == {m.name for m in cache.values()}
    actual_geometry = {ob['source_id']: _immutable(ob, digest) for ob in objects}
    assert immutable == actual_geometry
    return {'eligible_object_count': len(objects), 'source_ids': sorted(rows),
        'kind_building_counts': dict(sorted(building_counts.items())),
        'window_assembly_count': window_count, 'verified_glass_first_hit_count': ray_count,
        'glass_first_hit_material_counts': dict(sorted(ray_materials.items())),
        'glass_first_hit_method': 'Each retained pane lower-quarter sample, actual individual-object local-space ray; first polygon belongs to the same original six-face pane and uses its assigned glass copy',
        'role_face_counts_by_kind': {kind: dict(sorted(counts.items())) for kind, counts in role_counts.items()},
        'changed_material_face_count': changed_faces,
        'role_assignment_sha256': digest(object_summaries),
        'input_face_material_indices_sha256': digest(input_assignments),
        'output_face_material_indices_sha256': digest(output_assignments),
        'geometry_topology_uv_pose_input_sha256': digest(immutable),
        'geometry_topology_uv_pose_output_sha256': digest(actual_geometry),
        'all_target_geometry_topology_uv_pose_visibility_preserved': True,
        'old_material_slot_prefixes_preserved': True, 'old_material_slots_sha256': digest(source_slots),
        'unassigned_face_material_indices_preserved': True, 'unassigned_face_material_indices_sha256': digest(unassigned_proof),
        'upper_faces_above_height_plus_0_2m_materials_preserved': True,
        'upper_face_material_indices_sha256': digest(upper_proof),
        'source_roof_face_records_preserved': True, 'roof_faces_sha256': roof,
        'other_scene_meshes_preserved': True, 'other_scene_mesh_count': len(others),
        'other_scene_meshes_sha256': digest(others),
        'all_original_material_graphs_preserved': True, 'original_material_graphs_sha256': digest(originals),
        'world_graph_preserved': True, 'world_graph_sha256': world,
        'new_material_count': len(cache), 'material_recipes': sorted(recipes, key=lambda r: r['material']),
        'new_object_count': 0, 'new_mesh_count': 0, 'new_image_count': 0,
        'source_scope_sha256': digest([[ident, rows[ident]['kind'], rows[ident]['outline'],
            rows[ident]['height_estimate_m'], rows[ident]['floors_estimate'], rows[ident].get('source', 'satellite')]
            for ident in sorted(rows)]),
        'estimated': ['Kind-specific retained-pigment multipliers', 'Component finish hierarchy on estimated unseen facades'],
        'limitations': 'Material-only presentation estimates; not photographed peripheral wall colours, measured facade finishes, rooms, new openings or reference acceptance. Window rhythm, all mesh geometry/UV and source roof records remain fixed. Original graph proof is the caller top-level node/link snapshot, not recursive node-group or image-pixel auditing. Other-mesh snapshot does not audit general custom attributes or evaluated modifiers. A pane sample ray does not prove multi-building visibility from the final camera.'}


def add_facade_finish(state):
    """Apply the finite role palette to exactly the depth pass's 98 generic meshes."""
    depth = state['craft_modules']['facade_depth']
    objects = depth['facade_target_objects'](state); rows = depth['_eligible_rows'](state)
    assert len(objects) == len(rows) == 98
    return _add_to_objects(state, objects, rows, depth)
