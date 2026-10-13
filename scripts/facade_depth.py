"""Late, bounded depth correction for estimated peripheral window assemblies.

The retained source scene and photographed facade families are excluded. This
module consumes the existing in-memory expansion state and never saves a scene.
"""
import math


GLASS_NAMES = {'Atlas architecture glass %s.001' % i for i in range(4)}
TRIM_NAME = 'Atlas architecture muted campus stone trim.001'
SHIFT_M = .115
TOL_M = .0005  # Float32 vertex coordinates in the native scene, not survey error.


def _eligible_rows(state):
    rows = {}
    for row in state['D']['buildings']:
        ident = row['id']
        photo = ident.startswith('N') and (row['kind'] == 'dorm' or
            ident in {'N31', 'N32', 'N33', 'N34', 'N35'})
        if not photo and ident not in state['n']['ids'] and ident not in {'N13', 'N15', 'N19'}:
            rows[ident] = row
    assert len(rows) == 98, ('Changed generic facade scope', sorted(rows))
    return rows


def facade_target_objects(state):
    """Read-only target list for the caller's wider scene preservation check."""
    rows = _eligible_rows(state)
    objects = sorted((ob for ob in state['s'].objects if ob.type == 'MESH' and
        not ob.hide_render and ob.name.startswith('Atlas detailed ') and
        ob.get('source_id') in rows), key=lambda ob: ob['source_id'])
    assert len(objects) == len(rows) and {ob['source_id'] for ob in objects} == set(rows)
    for ob in objects:
        assert ob.get('detail_basis') == 'satellite roof trace and estimated facade family', ob.name
        used = {ob.data.materials[f.material_index].name for f in ob.data.polygons}
        assert used.intersection(GLASS_NAMES) and TRIM_NAME in used, ob.name
        assert not ob.name.startswith(('B06', 'B07', 'B08')), ob.name
        assert ob.data.users == 1, ('Shared architecture mesh', ob.name)
    return objects


def _static_mesh(ob):
    me = ob.data
    return {'faces': [[list(f.vertices), f.material_index, f.use_smooth] for f in me.polygons],
        'slots': [m.name if m else None for m in me.materials],
        'uv': {uv.name: [list(v.uv) for v in uv.data] for uv in me.uv_layers},
        'active_uv': me.uv_layers.active_index,
        'render_uv': [uv.name for uv in me.uv_layers if uv.active_render],
        'matrix': [list(row) for row in ob.matrix_world], 'hide_render': ob.hide_render}


def _box(ob, start, material_name=None):
    """Verify the six face / 24 separate vertex contract of refine_north.Mesh.box."""
    from mathutils import Vector
    me = ob.data
    assert start >= 0 and start + 6 <= len(me.polygons), (ob.name, start)
    faces = list(me.polygons[start:start + 6])
    assert all(len(f.vertices) == 4 for f in faces), (ob.name, start, 'non-quad box')
    indices = [i for f in faces for i in f.vertices]
    assert len(set(indices)) == 24, (ob.name, start, 'shared box vertices')
    if material_name is not None:
        assert all(me.materials[f.material_index].name == material_name for f in faces), (ob.name, start)
    else:
        assert len({f.material_index for f in faces}) == 1, (ob.name, start)
    points = [ob.matrix_world @ me.vertices[i].co for i in indices]
    # Accumulating 24 metre-space float32 vectors can add over 0.5 mm of
    # numerical drift on distant campus wings. Sum in Python doubles first.
    centre = Vector(tuple(sum(float(p[a]) for p in points) / 24 for a in range(3)))
    tangent = (points[9] - points[8]).normalized()
    assert abs(tangent.z) < 1e-6, (ob.name, start, 'tilted facade')
    outward = tangent.cross(Vector((0, 0, 1))).normalized()
    axes = (tangent, outward, Vector((0, 0, 1)))
    limits = [(min((p - centre).dot(a) for p in points),
        max((p - centre).dot(a) for p in points)) for a in axes]
    sizes = [hi - lo for lo, hi in limits]
    assert all(s > .001 for s in sizes), (ob.name, start, sizes)
    # Every point must be an envelope corner; eight distinct corners each occur
    # three times. Face planes/normals must match the builder's exact order.
    corners = []
    for p in points:
        key = []
        for a, (lo, hi) in zip(axes, limits):
            value = (p - centre).dot(a)
            assert min(abs(value - lo), abs(value - hi)) < TOL_M, (ob.name, start, 'non-box point')
            key.append(int(abs(value - hi) < abs(value - lo)))
        corners.append(tuple(key))
    assert len(set(corners)) == 8 and all(corners.count(k) == 3 for k in set(corners))
    normals = (-axes[2], axes[2], outward, tangent, -outward, -tangent)
    for i, normal in enumerate(normals):
        face_points = points[i * 4:i * 4 + 4]
        actual = (face_points[1] - face_points[0]).cross(face_points[2] - face_points[0]).normalized()
        assert actual.dot(normal) > .99999, (ob.name, start, i, 'box face orientation')
        assert max(p.dot(normal) for p in face_points) - min(p.dot(normal) for p in face_points) < TOL_M
    return {'indices': indices, 'centre': centre, 'tangent': tangent,
        'outward': outward, 'sizes': sizes}


def _dimensions(box, expected, where):
    assert all(abs(a - b) < TOL_M for a, b in zip(box['sizes'], expected)), (where, box['sizes'], expected)


def _offset(box, pane, expected, where):
    from mathutils import Vector
    assert box['tangent'].dot(pane['tangent']) > .99999, (where, 'tangent')
    assert box['outward'].dot(pane['outward']) > .99999, (where, 'normal')
    delta = box['centre'] - pane['centre']
    actual = [delta.dot(a) for a in (pane['tangent'], pane['outward'], Vector((0, 0, 1)))]
    assert all(abs(a - b) < TOL_M for a, b in zip(actual, expected)), (where, actual, expected)


def _source_match(state, row, pane):
    from mathutils import Vector
    ps = [state['gp'](q, source=row.get('source', 'satellite')) for q in row['outline']]
    if sum(a.x * b.y - b.x * a.y for a, b in zip(ps, ps[1:] + ps[:1])) < 0:
        ps.reverse()
    matches = []
    for edge, (a, b) in enumerate(zip(ps, ps[1:] + ps[:1])):
        length = (b - a).length
        if length < 2.6:
            continue
        tangent = (b - a).normalized(); outward = Vector((tangent.y, -tangent.x, 0))
        if pane['tangent'].dot(tangent) < .99999 or pane['outward'].dot(outward) < .99999:
            continue
        delta = pane['centre'] - a
        if abs(delta.dot(outward) + .083) >= TOL_M:
            continue
        count = max(1, round(length / (4.0 if row['kind'] == 'dorm' else 4.6)))
        bay = length / count
        j = round(delta.dot(tangent) / bay - .5)
        step = row['height_estimate_m'] / row['floors_estimate']
        floor = round((pane['centre'].z - .15 - step * .53) / step)
        if not (0 <= j < count and 0 <= floor < row['floors_estimate']):
            continue
        expected = a + tangent * (bay * (j + .5)) - outward * .083
        expected.z = .15 + floor * step + step * .53
        if (expected - pane['centre']).length < TOL_M:
            _dimensions(pane, (bay * .68, .075, step * .57), (row['id'], edge, floor, j))
            matches.append((edge, floor, j, outward))
    assert len(matches) == 1, (row['id'], 'window source-edge match', len(matches))
    return matches[0]


def add_facade_depth(state):
    """Open verified opaque surrounds and recess only their window assemblies."""
    import bpy
    from mathutils import Vector
    digest = state['lake_digest']; snapshot = state['spatial_mesh_snapshot']
    objects = facade_target_objects(state); targets = set(objects); rows = _eligible_rows(state)
    excluded = sorted((ob for ob in state['s'].objects if ob.type == 'MESH' and
        ob not in targets and (ob.name.startswith('Atlas detailed ') or
        ob.name.startswith(('B06 Central', 'B07 Central', 'B08 Central')))), key=lambda ob: ob.name)
    excluded_before = snapshot(excluded)
    input_sha = digest(snapshot(objects))
    object_rows = []; depths_before = []; depths_after = []
    panes_total = moved_total = added_vertices = added_faces = verified_hits = 0
    hit_materials = {name: 0 for name in sorted(GLASS_NAMES)}
    attribute_schemas = {}; source_schema_assignment = []
    generated_attributes = {'.corner_vert': ('INT', 'CORNER'),
        '.corner_edge': ('INT', 'CORNER'), '.edge_verts': ('INT32_2D', 'EDGE')}
    retained_attributes = {'position': ('FLOAT_VECTOR', 'POINT'),
        '.select_vert': ('BOOLEAN', 'POINT'), '.select_poly': ('BOOLEAN', 'FACE'),
        '.select_edge': ('BOOLEAN', 'EDGE'), 'sharp_face': ('BOOLEAN', 'FACE'),
        'material_index': ('INT', 'FACE')}
    for ob in objects:
        me = ob.data; row = rows[ob['source_id']]
        assert me.shape_keys is None and len(ob.vertex_groups) == 0 and len(ob.modifiers) == 0, ob.name
        assert len(me.color_attributes) == 0, ob.name
        uv_names = [uv.name for uv in me.uv_layers]
        uv_active = me.uv_layers.active_index
        uv_render = [uv.name for uv in me.uv_layers if uv.active_render]
        attrs = {a.name: (a.data_type, a.domain) for a in me.attributes}
        declared = {**generated_attributes, **retained_attributes,
            **{name: ('FLOAT2', 'CORNER') for name in uv_names}}
        assert attrs == declared, (ob['source_id'], ob.name, 'undeclared mesh attributes', attrs, declared)
        schema = {name: list(value) for name, value in sorted(attrs.items())}
        schema_sha = digest(schema)
        entry = attribute_schemas.setdefault(schema_sha, {'attributes': schema, 'object_count': 0})
        entry['object_count'] += 1
        source_schema_assignment.append([ob['source_id'], schema_sha])
        pose_before = digest([[list(r) for r in ob.matrix_world], ob.hide_render,
            me.name, [m.name if m else None for m in me.materials]])
        old_vertices = [list(v.co) for v in me.vertices]
        old_vertex_selection = [v.select for v in me.vertices]
        old_edge_selection = {tuple(sorted(e.vertices)): e.select for e in me.edges}
        old_faces = []
        for face in me.polygons:
            old_faces.append({'vertices': list(face.vertices), 'material': face.material_index,
                'smooth': face.use_smooth, 'selected': face.select,
                'uv': {uv.name: [list(uv.data[i].uv) for i in face.loop_indices] for uv in me.uv_layers}})
        old_vertex_count = len(old_vertices); old_face_count = len(old_faces)
        plans = []; seen_windows = set(); moved = set()
        face = 0
        while face < len(me.polygons):
            material_name = me.materials[me.polygons[face].material_index].name
            if material_name not in GLASS_NAMES:
                face += 1; continue
            pane = _box(ob, face, material_name); width, _, height = pane['sizes']
            source_edge, floor, bay, outward = _source_match(state, row, pane)
            key = (source_edge, floor, bay)
            assert key not in seen_windows, (ob.name, key, 'duplicate assembly')
            seen_windows.add(key)
            surround = _box(ob, face - 6, TRIM_NAME)
            _dimensions(surround, (width + .17, .15, height + .18), (ob.name, face, 'surround'))
            _offset(surround, pane, (0, -.087, 0), (ob.name, face, 'surround'))
            assembly = [pane]
            for k in range(3):
                mullion = _box(ob, face + 6 + k * 6, TRIM_NAME)
                _dimensions(mullion, (.045, .09, height + .04), (ob.name, face, 'mullion'))
                _offset(mullion, pane, (-width / 2 + k * width / 2, .048, 0), (ob.name, face, 'mullion'))
                assembly.append(mullion)
            transom = _box(ob, face + 24, TRIM_NAME)
            _dimensions(transom, (width, .10, .045), (ob.name, face, 'transom'))
            _offset(transom, pane, (0, .053, height * .23), (ob.name, face, 'transom'))
            assembly.append(transom)
            sill = _box(ob, face + 30, TRIM_NAME)
            _dimensions(sill, (width + .20, .27, .12), (ob.name, face, 'sill'))
            _offset(sill, pane, (0, .093, -height / 2 - .07), (ob.name, face, 'sill'))
            indices = [i for part in assembly for i in part['indices']]
            assert len(set(indices)) == 120 and not moved.intersection(indices), (ob.name, 'shared assembly vertices')
            moved.update(indices)
            # Signed metre distances from the fixed source roof-derived edge.
            front = -.083 + pane['sizes'][1] / 2
            back = -.083 - pane['sizes'][1] / 2
            depths_before.append([front, back, -.095, -.28])
            trim = me.materials[me.polygons[face - 6].material_index]
            shader = trim.node_tree.nodes.get('Principled BSDF')
            assert shader is not None and shader.inputs['Alpha'].default_value == 1
            assert not shader.inputs['Alpha'].is_linked and shader.inputs['Transmission Weight'].default_value == 0
            assert not shader.inputs['Transmission Weight'].is_linked
            assert not any(node.bl_idname == 'ShaderNodeBsdfTransparent' for node in trim.node_tree.nodes)
            output = trim.node_tree.nodes.get('Material Output')
            assert output is not None and output.inputs['Surface'].is_linked
            assert output.inputs['Surface'].links[0].from_node == shader
            plans.append({'start': face, 'outward': outward, 'centre': pane['centre'].copy(),
                'indices': indices, 'surround': surround, 'width': width, 'height': height,
                'glass': material_name})
            face += 6
        assert plans, (ob.name, 'no verified generic windows')
        # No selected vertex may be used by an unrelated face. Mesh.face makes
        # isolated vertices, so this also protects the fixed surround and sill.
        moved_faces = {i for plan in plans for i in range(plan['start'], plan['start'] + 30)}
        assert all(not moved.intersection(f.vertices) for f in me.polygons if f.index not in moved_faces)
        fixed_before = digest([[v.index, list(v.co), v.select] for v in me.vertices if v.index not in moved])
        before_moved = {i: ob.matrix_world @ me.vertices[i].co for i in moved}
        vertices = [list(v) for v in old_vertices]
        for plan in plans:
            outward, indices = plan['outward'], plan['indices']
            local_delta = ob.matrix_world.to_3x3().inverted() @ (-outward * SHIFT_M)
            for i in indices:
                vertices[i] = list(Vector(vertices[i]) + local_delta)
        replacements = {}; replaced_faces = set()
        for plan in plans:
            start = plan['start']; surround = plan['surround']
            tangent = surround['tangent']; outward = surround['outward']
            width, height = plan['width'], plan['height']
            centre = surround['centre']; depth = surround['sizes'][1]
            # Keep all original 24 outer-box vertices and all four outer side
            # faces. Only the front/back caps are replaced by annular strips.
            signs = [(-1, -1), (1, -1), (1, 1), (-1, 1)]
            inner_front = []; inner_back = []
            for direction, result in ((1, inner_front), (-1, inner_back)):
                for xsign, zsign in signs:
                    point = centre + tangent * (xsign * width / 2) + outward * (direction * depth / 2)
                    point.z += zsign * height / 2
                    result.append(len(vertices)); vertices.append(list(ob.matrix_world.inverted() @ point))
            front_index, back_index = start - 4, start - 2
            assert front_index not in replacements and back_index not in replacements
            replaced_faces.update((front_index, back_index))
            # Existing metre UVs are affine in tangent/normal XY, independent
            # of height. Interpolate from the retained horizontal bottom face;
            # original loop values are copied on every retained original face.
            bottom = old_faces[start - 6]
            p0, p1, p2 = [ob.matrix_world @ Vector(old_vertices[i]) for i in bottom['vertices'][:3]]
            cross = p1 - p0; along = p2 - p1
            assert abs(cross.dot(tangent)) < TOL_M and abs(along.dot(outward)) < TOL_M
            def new_uv(index, layer):
                point = ob.matrix_world @ Vector(vertices[index]); delta = point - p0
                a = delta.dot(cross) / cross.dot(cross); b = delta.dot(along) / along.dot(along)
                uv0, uv1, uv2 = bottom['uv'][layer][:3]
                return [uv0[k] + a * (uv1[k] - uv0[k]) + b * (uv2[k] - uv1[k]) for k in range(2)]
            def new_face(indices, template):
                return {'vertices': indices, 'material': template['material'], 'smooth': template['smooth'],
                    'selected': template['selected'],
                    'uv': {name: [new_uv(i, name) for i in indices] for name in uv_names}}
            front = old_faces[front_index]; back = old_faces[back_index]
            front_rows = [new_face([front['vertices'][k], front['vertices'][(k + 1) % 4],
                inner_front[(k + 1) % 4], inner_front[k]], front) for k in range(4)]
            # Inner reveals face into the real aperture, connecting the front
            # and back opening edges without any transparent or collapsed face.
            front_rows += [new_face([inner_front[k], inner_front[(k + 1) % 4],
                inner_back[(k + 1) % 4], inner_back[k]], front) for k in range(4)]
            # The old back cap runs right-to-left, opposite the front cap.
            back_order = [inner_back[1], inner_back[0], inner_back[3], inner_back[2]]
            back_rows = [new_face([back['vertices'][k], back['vertices'][(k + 1) % 4],
                back_order[(k + 1) % 4], back_order[k]], back) for k in range(4)]
            replacements[front_index] = front_rows; replacements[back_index] = back_rows
        faces = []; face_map = {}
        for index, face in enumerate(old_faces):
            if index in replacements:
                faces.extend(replacements[index])
            else:
                face_map[index] = len(faces); faces.append(face)
        assert len(vertices) == old_vertex_count + len(plans) * 8
        assert len(faces) == old_face_count + len(plans) * 10
        protected_face_before = digest([[index, old_faces[index]] for index in range(old_face_count) if index not in replaced_faces])
        # No shape keys/groups/custom data exist in this generated family.
        # Rebuild the same datablock, retaining original vertex IDs and explicit
        # original face/loop records; generated edge indices necessarily change.
        pointer = me.as_pointer()
        me.clear_geometry(); me.from_pydata(vertices, [], [face['vertices'] for face in faces]); me.update()
        for name in uv_names:
            me.uv_layers.new(name=name)
        me.uv_layers.active_index = uv_active
        for uv in me.uv_layers:
            uv.active_render = uv.name in uv_render
        for vertex in me.vertices:
            vertex.select = old_vertex_selection[vertex.index] if vertex.index < old_vertex_count else True
        for edge in me.edges:
            edge.select = old_edge_selection.get(tuple(sorted(edge.vertices)), True)
        for poly, recorded in zip(me.polygons, faces):
            poly.material_index = recorded['material']; poly.use_smooth = recorded['smooth']; poly.select = recorded['selected']
            for uv in me.uv_layers:
                for loop, value in zip(poly.loop_indices, recorded['uv'][uv.name]):
                    uv.data[loop].uv = value
        me.update()
        assert me.as_pointer() == pointer and not me.validate(clean_customdata=False), ob.name
        after_attrs = {a.name: (a.data_type, a.domain) for a in me.attributes}
        assert attrs == after_attrs, (ob['source_id'], ob.name, 'attribute schema changed', attrs, after_attrs)
        assert [uv.name for uv in me.uv_layers] == uv_names and me.uv_layers.active_index == uv_active
        assert [uv.name for uv in me.uv_layers if uv.active_render] == uv_render
        assert pose_before == digest([[list(r) for r in ob.matrix_world], ob.hide_render,
            me.name, [m.name if m else None for m in me.materials]])
        assert fixed_before == digest([[v.index, list(v.co), v.select] for v in me.vertices
            if v.index < old_vertex_count and v.index not in moved]), (ob.name, 'unselected vertex changed')
        protected_face_after = []
        for index in range(old_face_count):
            if index in replaced_faces:
                continue
            poly = me.polygons[face_map[index]]
            actual = {'vertices': list(poly.vertices), 'material': poly.material_index,
                'smooth': poly.use_smooth, 'selected': poly.select,
                'uv': {uv.name: [list(uv.data[i].uv) for i in poly.loop_indices] for uv in me.uv_layers}}
            protected_face_after.append([index, actual])
        assert protected_face_before == digest(protected_face_after), (ob.name, 'original non-target face/loop changed')
        assert all(tuple(sorted(e.vertices)) in old_edge_selection or
            any(i >= old_vertex_count for i in e.vertices) for e in me.edges), ob.name
        new_edge_selection = {tuple(sorted(e.vertices)): e.select for e in me.edges}
        assert all(new_edge_selection.get(key) == value for key, value in old_edge_selection.items())
        bpy.context.view_layer.update()
        depsgraph = bpy.context.evaluated_depsgraph_get()
        for plan in plans:
            start, outward, centre, indices = plan['start'], plan['outward'], plan['centre'], plan['indices']
            pane = _box(ob, face_map[start])
            actual_delta = pane['centre'] - centre
            assert abs(actual_delta.dot(outward) + SHIFT_M) < TOL_M
            assert abs(actual_delta.dot(pane['tangent'])) < TOL_M and abs(actual_delta.z) < TOL_M
            for i in indices:
                actual = ob.matrix_world @ me.vertices[i].co - before_moved[i]
                assert (actual + outward * SHIFT_M).length < TOL_M
            front = -.083 + actual_delta.dot(outward) + pane['sizes'][1] / 2
            back = -.083 + actual_delta.dot(outward) - pane['sizes'][1] / 2
            assert -.28 < back < front < -.095, (ob.name, start, 'pane not in reveal')
            depths_after.append([front, back, -.095 - front, back + .28])
            # Shoot through the actual opaque opening, avoiding centre mullion
            # and upper transom. The first local-object hit must be this glass.
            sample = pane['centre'] + pane['tangent'] * (pane['sizes'][0] * .25)
            sample.z -= pane['sizes'][2] * .22
            origin_world = sample + outward * .30
            inverse = ob.matrix_world.inverted()
            direction = inverse.to_3x3() @ (-outward)
            hit, location, normal, hit_face = ob.ray_cast(inverse @ origin_world, direction.normalized(),
                distance=direction.length * .60, depsgraph=depsgraph)
            assert hit and hit_face >= 0, (ob.name, start, 'opening ray missed')
            actual_material = me.materials[me.polygons[hit_face].material_index].name
            assert actual_material == plan['glass'], (ob.name, start, 'opaque opening blocked', actual_material)
            assert hit_face in range(face_map[start], face_map[start] + 6), (ob.name, start, 'different glass module hit')
            hit_world = ob.matrix_world @ location
            assert abs((hit_world - pane['centre']).dot(outward) - pane['sizes'][1] / 2) < TOL_M
            hit_materials[actual_material] += 1; verified_hits += 1
        object_rows.append([ob['source_id'], len(plans), len(moved), fixed_before, protected_face_before, pose_before])
        panes_total += len(plans); moved_total += len(moved)
        added_vertices += len(vertices) - old_vertex_count; added_faces += len(faces) - old_face_count
    bpy.context.view_layer.update()
    assert excluded_before == snapshot(excluded), 'Excluded photographed/central architecture changed'
    output_sha = digest(snapshot(objects))
    assert input_sha != output_sha and moved_total == panes_total * 120
    assert added_vertices == panes_total * 8 and added_faces == panes_total * 10
    assert verified_hits == panes_total == sum(hit_materials.values())
    def ranges(values):
        return [[min(row[i] for row in values), max(row[i] for row in values)] for i in range(4)]
    return {'eligible_object_count': len(objects), 'source_ids': sorted(rows),
        'window_assembly_count': panes_total, 'moved_vertex_count': moved_total,
        'inward_translation_m_estimate': SHIFT_M, 'verification_tolerance_m': TOL_M,
        'before_depth_range_m': dict(zip(('pane_front', 'pane_back', 'surround_front', 'wall_front'), ranges(depths_before))),
        'after_depth_range_m': dict(zip(('pane_front', 'pane_back', 'recess', 'wall_clearance'), ranges(depths_after))),
        'input_mesh_geometry_uv_visibility_sha256': input_sha,
        'output_mesh_geometry_uv_visibility_sha256': output_sha,
        'per_object_validation_sha256': digest(object_rows),
        'all_windows_source_edge_matched': True, 'all_assembly_box_patterns_verified': True,
        'non_target_original_vertices_preserved': True,
        'non_target_original_faces_vertex_indices_materials_smooth_selection_and_loop_uv_preserved': True,
        'original_surround_24_vertices_and_four_outer_faces_preserved': True,
        'pane_assembly_original_topology_and_loop_uv_preserved': True,
        'material_slots_uv_configuration_transforms_and_visibility_preserved': True,
        'sills_walls_roofs_preserved': True,
        'topology_changed': True, 'opened_opaque_surround_count': panes_total,
        'replaced_original_surround_cap_face_count': panes_total * 2,
        'annular_front_back_face_count': panes_total * 8, 'inner_reveal_face_count': panes_total * 4,
        'added_inner_corner_vertex_count': added_vertices, 'net_added_face_count': added_faces,
        'verified_opaque_opening_count': verified_hits, 'opening_ray_first_hit_material_counts': hit_materials,
        'opening_verification': 'Actual object-space ray cast through each offset sample after mesh/dependency-graph update; first hit is the same retained glass module, with world/front distance checked',
        'opaque_trim_alpha_and_zero_transmission_preserved': True,
        'no_shape_keys_vertex_groups_modifiers_or_undeclared_attributes': True,
        'mesh_attribute_schemas': attribute_schemas,
        'source_schema_assignment_sha256': digest(sorted(source_schema_assignment)),
        'excluded_architecture_count': len(excluded), 'excluded_architecture_preserved': True,
        'excluded_architecture_geometry_uv_visibility_sha256': digest(excluded_before),
        'excluded_architecture_scope': 'Other Atlas detailed meshes, including photographed facade families, and whole B06/B07/B08 central meshes; caller separately protects the wider visible scene',
        'new_mesh_count': 0, 'new_material_count': 0,
        'limitations': 'Estimated generic facade correction, not measured wall/opening dimensions. Two opaque surround caps per window are replaced by annular front/back strips and inner reveals; whole-mesh topology changes. Original non-target face vertex IDs/material/smooth/loop UV and fixed original vertices are exact; generated corner/edge topology attributes are reconstructed. Original selection data is retained; new inner vertices/edges/faces inherit selection. Ray casts verify opening visibility within the individual modified target object without modifiers, not occlusion by other buildings. Source roof traces are not measured ground footprints; moved assemblies retain facade-tangent position and height while normal XY changes.'}
