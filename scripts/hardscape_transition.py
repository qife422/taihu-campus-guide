"""Continue the retained geographic shader across the actual outer hardscape.

Only declared low, planar road/paving/curb objects receive copied material
slots. Their geometry and hard boundaries remain unchanged. The existing
18 m outer-distance image supplies a 12 m estimated hardscape transition;
internal road edges and woodland do not define this shader's blend weight.
"""


def add_hardscape_transition(state):
    import hashlib
    import bpy
    import numpy as np
    from shapely.geometry import Polygon, box
    from shapely.ops import unary_union

    scene = state['s']; digest = state['lake_digest']
    graph = state['facade_graph_state']; ground = state['ground']
    outer = state['outer_ring']; source_group = state['source_group']
    transition_width = 12.0; field_width = 18.0
    image = bpy.data.images['Expansion ground boundary field']
    assert image.colorspace_settings.name == 'Non-Color' and image.channels == 4
    bpy.context.view_layer.update()

    def rings(shape):
        if hasattr(shape, 'geoms'):
            return sorted(value for part in shape.geoms for value in rings(part))
        values = [tuple(v) for v in shape.coords]
        if values[0] == values[-1]:
            values.pop()
        alternatives = []
        for sequence in (values, values[::-1]):
            i = min(range(len(sequence)), key=lambda j: sequence[j])
            alternatives.append(sequence[i:] + sequence[:i])
        return [min(alternatives)]

    def footprint_values(shape):
        if hasattr(shape, 'geoms'):
            return sorted(value for part in shape.geoms for value in footprint_values(part))
        return [[rings(shape.exterior)[0], sorted(rings(ring)[0] for ring in shape.interiors)]]

    def geometry_snapshot():
        # Slots are audited separately, since the declared target slots change.
        meshes = {}; objects = {}
        for ob in scene.objects:
            if ob.type == 'MESH' and ob.data.name not in meshes:
                mesh = ob.data
                meshes[mesh.name] = digest({
                    'vertices': [list(v.co) for v in mesh.vertices],
                    'faces': [[list(f.vertices), f.material_index, f.use_smooth] for f in mesh.polygons],
                    'uv': {uv.name: [list(v.uv) for v in uv.data] for uv in mesh.uv_layers},
                    'active_uv': mesh.uv_layers.active_index,
                    'render_uv': [uv.name for uv in mesh.uv_layers if uv.active_render]})
            objects[ob.name] = [ob.type, ob.data.name if ob.data else None,
                [list(row) for row in ob.matrix_world], ob.hide_render, ob.hide_viewport]
        return {'meshes': meshes, 'objects': objects}

    def slots_snapshot():
        return {ob.name: [[slot.link, slot.material.name if slot.material else None]
                         for slot in ob.material_slots]
                for ob in scene.objects if ob.type == 'MESH'}

    def planar_footprint(ob, expected_z):
        assert ob.type == 'MESH' and not ob.hide_render and not ob.modifiers, ob.name
        assert len(ob.data.materials) == 1 and ob.data.materials[0], ob.name
        assert ob.material_slots[0].link == 'DATA', ob.name
        vertices = [ob.matrix_world @ vertex.co for vertex in ob.data.vertices]
        assert vertices and all(abs(p.z - expected_z) < 1e-6 for p in vertices), ob.name
        polygons = []; degenerate = 0
        for face in ob.data.polygons:
            assert face.material_index == 0, ob.name
            polygon = Polygon([(vertices[i].x, vertices[i].y) for i in face.vertices])
            if polygon.is_valid and polygon.area > 1e-10:
                polygons.append(polygon)
            else:
                degenerate += 1
        assert polygons, ob.name
        return unary_union(polygons), degenerate

    geometry_before = geometry_snapshot(); slots_before = slots_snapshot()
    material_before = {m.name: digest(graph(m.node_tree)) for m in bpy.data.materials if m.use_nodes}
    original_material_names = {m.name for m in bpy.data.materials}
    original_image_inventory = sorted((im.name, im.filepath) for im in bpy.data.images)
    source_before = digest(graph(source_group))
    world_before = digest(graph(scene.world.node_tree)); roofs_before = digest(state['faces'])
    field_pixels = np.asarray(image.pixels[:], dtype=np.float32).reshape(image.size[1], image.size[0], 4)
    image_sha = hashlib.sha256(field_pixels.tobytes()).hexdigest()
    assert image_sha == state['field_sha']
    x0, y0, x1, y1 = ground.bounds
    x0 -= 24; y0 -= 24; x1 += 24; y1 += 24
    field_cell = [(x1 - x0) / image.size[0], (y1 - y0) / image.size[1]]
    assert max(field_cell) < 1.7
    # The BLUE channel is the outer ring alone. RED includes woodland, which
    # would incorrectly feather an interior road/woodland interface here.
    saturation = np.float32((transition_width / field_width) ** 2 * (3 - 2 * transition_width / field_width))
    t = np.clip(field_pixels[:, :, 2] / saturation, 0, 1)
    weights = t * t * (3 - 2 * t)
    assert np.isfinite(weights).all() and weights.min() >= 0 and weights.max() <= 1
    bounds = state['source_bounds']
    assert set(bounds) == {'satellite', 'north-extension'}
    expected_bounds = {}
    for source, width, height in [('satellite', 1152, 1920), ('north-extension', 1000, 900)]:
        lo = state['gp']((0, height), source=source); hi = state['gp']((width, 0), source=source)
        expected_bounds[source] = (lo.x, lo.y, hi.x, hi.y)
    assert bounds == expected_bounds
    expected_outer = ground.exterior if ground.geom_type == 'Polygon' else unary_union([part.exterior for part in ground.geoms])
    assert outer.equals(expected_outer)
    coverage = unary_union([box(*value) for value in bounds.values()])
    outer_band = outer.buffer(transition_width)
    # These exact meshes come from retained road unions and their bounded
    # curb/paving recipes. No roofs, parking paint, sports or garden courses.
    specs = [('Expansion source roads', .35, state['asphalt']),
             ('Expansion source paving satellite', .31, state['paving'].intersection(box(-1e4, -1e4, 1e4, state['cut']))),
             ('Expansion source paving north-extension', .31, state['paving'].intersection(box(-1e4, state['cut'], 1e4, 1e4))),
             ('Expansion road margins', .38, state['asphalt'].buffer(.25).difference(state['asphalt']).intersection(state['outside']).difference(state['mask'])),
             ('Expansion paving courses', .335, state['paving'].difference(state['paving'].buffer(-.22))),
             ('Joined continuous source roads', .35, state['ctx']['road']),
             ('Joined continuous road curbs', .38, state['ctx']['road'].buffer(.25).difference(state['ctx']['road'])
              .difference(state['ctx']['allroof']).difference(state['ctx']['allwater'].buffer(4.85)).intersection(state['ctx']['roi']))]
    copies = {}; recipes = []; targets = []; inactive = []

    def transition_material(base):
        if base.name in copies:
            return copies[base.name]
        name = 'Hardscape outer transition ' + base.name
        assert name not in bpy.data.materials
        material = base.copy(); material.name = name
        assert material.use_nodes and graph(material.node_tree) == graph(base.node_tree), name
        ns = material.node_tree.nodes; links = material.node_tree.links
        outputs = [node for node in ns if node.bl_idname == 'ShaderNodeOutputMaterial' and node.is_active_output]
        assert len(outputs) == 1 and len(outputs[0].inputs['Surface'].links) == 1, name
        output = outputs[0]; retained = output.inputs['Surface'].links[0].from_socket
        original_nodes = {node.name for node in ns}
        assert not any(n.startswith('Hardscape boundary ') for n in original_nodes)

        def node(kind, label):
            result = ns.new(kind); result.name = 'Hardscape boundary ' + label
            return result

        def math_node(operation, label, *values):
            result = node('ShaderNodeMath', label); result.operation = operation
            for i, value in enumerate(values):
                if isinstance(value, (int, float)):
                    result.inputs[i].default_value = value
                else:
                    links.new(value, result.inputs[i])
            return result.outputs[0]

        position = node('ShaderNodeNewGeometry', 'world metres')
        mapped = node('ShaderNodeVectorMath', 'retained outer field coordinates'); mapped.operation = 'MULTIPLY_ADD'
        mapped.inputs[1].default_value = (1 / (x1 - x0), 1 / (y1 - y0), 1)
        mapped.inputs[2].default_value = (-x0 / (x1 - x0), -y0 / (y1 - y0), 0)
        links.new(position.outputs['Position'], mapped.inputs[0])
        field = node('ShaderNodeTexImage', 'retained outer field'); field.image = image
        field.interpolation = 'Linear'; field.extension = 'EXTEND'
        links.new(mapped.outputs[0], field.inputs['Vector'])
        channels = node('ShaderNodeSeparateColor', 'outer blue channel'); links.new(field.outputs['Color'], channels.inputs['Color'])
        ramp = node('ShaderNodeMapRange', 'twelve metre retained weight')
        ramp.clamp = True; ramp.interpolation_type = 'SMOOTHSTEP'
        ramp.inputs['From Min'].default_value = 0; ramp.inputs['From Max'].default_value = float(saturation)
        links.new(channels.outputs['Blue'], ramp.inputs['Value'])
        axis = node('ShaderNodeSeparateXYZ', 'source coverage axes'); links.new(position.outputs['Position'], axis.inputs[0])
        valid = []
        for source, (lo_x, lo_y, hi_x, hi_y) in sorted(bounds.items()):
            comparisons = [math_node('GREATER_THAN', source + ' xmin', axis.outputs['X'], lo_x),
                           math_node('LESS_THAN', source + ' xmax', axis.outputs['X'], hi_x),
                           math_node('GREATER_THAN', source + ' ymin', axis.outputs['Y'], lo_y),
                           math_node('LESS_THAN', source + ' ymax', axis.outputs['Y'], hi_y)]
            xy = math_node('MULTIPLY', source + ' x coverage', comparisons[0], comparisons[1])
            yy = math_node('MULTIPLY', source + ' y coverage', comparisons[2], comparisons[3])
            valid.append(math_node('MULTIPLY', source + ' xy coverage', xy, yy))
        valid_any = math_node('MAXIMUM', 'valid either source', *valid)
        source_weight = math_node('MULTIPLY', 'valid source contribution', valid_any,
            math_node('SUBTRACT', 'outer source contribution', 1, ramp.outputs['Result']))
        retained_weight = math_node('SUBTRACT', 'retained or outside coverage', 1, source_weight)
        geographic = node('ShaderNodeGroup', 'unchanged geographic surface'); geographic.node_tree = source_group
        blend = node('ShaderNodeMixShader', 'outer geographic to retained hardscape')
        links.new(retained_weight, blend.inputs[0]); links.new(geographic.outputs['Surface'], blend.inputs[1])
        links.new(retained, blend.inputs[2]); links.new(blend.outputs[0], output.inputs['Surface'])
        current = graph(material.node_tree); original = graph(base.node_tree)

        def retained_graph(value):
            return {'nodes': [r for r in value['nodes'] if r['name'] in original_nodes],
                    'links': [edge for edge in value['links'] if edge[0] in original_nodes and edge[2] in original_nodes
                              and not (edge[2] == output.name and edge[3] == output.inputs['Surface'].identifier)]}

        assert retained_graph(original) == retained_graph(current), name
        assert geographic.node_tree is source_group and field.image is image
        recipes.append({'source_material': base.name, 'copied_material': material.name,
            'source_material_graph_sha256': digest(original), 'output_material_graph_sha256': digest(current),
            'retained_nodes_and_internal_links_sha256': digest(retained_graph(original)),
            'original_node_count': len(original_nodes), 'original_nodes_and_internal_links_preserved': True,
            'only_replaced_source_connection': 'Active Material Output Surface',
            'source_group': source_group.name, 'source_group_graph_sha256': source_before,
            'field_image': image.name, 'field_rgba_float32_sha256': image_sha})
        copies[base.name] = material
        return material

    for name, z, expected in specs:
        ob = scene.objects[name]; footprint, degenerate = planar_footprint(ob, z)
        if expected is not None:
            assert footprint.difference(expected.buffer(.0002)).area < 1e-7, name
        active = footprint.intersection(outer_band).intersection(coverage)
        if active.area < .01:
            inactive.append(name)
            continue
        assert len([obj for obj in bpy.data.objects if obj.type == 'MESH' and obj.data is ob.data]) == 1, name
        base = ob.data.materials[0]; copied = transition_material(base)
        ob.data.materials[0] = copied
        targets.append({'object': name, 'slot_index': 0, 'source_material': base.name,
            'copied_material': copied.name, 'flat_world_z_m_estimate': z,
            'retained_source_footprint_sha256': digest(footprint_values(footprint)),
            'retained_source_area_m2': footprint.area, 'outer_coverage_strip_area_m2_estimate': active.area,
            'source_outside_coverage_area_m2': footprint.difference(coverage).area,
            'retained_degenerate_face_count': degenerate})
    assert targets and recipes
    assert geometry_before == geometry_snapshot()
    slots_after = slots_snapshot(); expected_slots = {name: [row[:] for row in rows] for name, rows in slots_before.items()}
    for target in targets:
        expected_slots[target['object']][target['slot_index']][1] = target['copied_material']
    assert slots_after == expected_slots
    assert material_before == {name: digest(graph(bpy.data.materials[name].node_tree)) for name in material_before}
    assert {m.name for m in bpy.data.materials} - original_material_names == {m.name for m in copies.values()}
    assert original_image_inventory == sorted((im.name, im.filepath) for im in bpy.data.images)
    assert source_before == digest(graph(source_group)) and image_sha == hashlib.sha256(np.asarray(image.pixels[:], dtype=np.float32).tobytes()).hexdigest()
    assert world_before == digest(graph(scene.world.node_tree)) and roofs_before == digest(state['faces'])
    return {'candidate_mesh_count': len(specs), 'used_target_count': len(targets), 'targets': targets,
        'inactive_interior_candidates': inactive, 'new_material_count': len(copies), 'recipes': recipes,
        'new_mesh_count': 0, 'new_image_count': 0, 'geometry_preserved': True,
        'all_existing_object_count': len(geometry_before['objects']),
        'all_existing_mesh_geometry_uv_pose_visibility_sha256': digest(geometry_before),
        'only_declared_material_slots_changed': True, 'original_material_slot_assignment_sha256': digest(slots_before),
        'final_material_slot_assignment_sha256': digest(slots_after),
        'all_original_material_graphs_preserved': True, 'all_original_material_graphs_sha256': digest(material_before),
        'source_branch_preserved': True, 'source_group_graph_sha256': source_before,
        'existing_image_inventory_preserved': True, 'outer_ring_sha256': digest(rings(outer)),
        'source_world_coverage_bounds': bounds, 'source_coverage_bounds_match_retained_georeference': True,
        'outer_field_bounds': [x0, y0, x1, y1], 'outer_field_size': list(image.size), 'outer_field_cell_m': field_cell,
        'outer_field_rgba_float32_sha256': image_sha, 'outer_field_distance_m_estimate': field_width,
        'hardscape_transition_m_estimate': transition_width, 'outer_blue_saturation': float(saturation),
        'sampled_retained_weight_bounds': [float(weights.min()), float(weights.max())],
        'native_weight_bound': [0.0, 1.0], 'source_weight_zero_outside_2d_coverage': True,
        'interior_road_boundary_used_for_weight': False, 'woodland_channel_used_for_weight': False,
        'world_and_roof_faces_preserved': True, 'world_graph_sha256': world_before, 'roof_faces_sha256': roofs_before,
        'limitations': 'Display transition on retained low planar source road/curb/paving meshes. The unchanged 18m outer field is smoothstepped to retained at an estimated 12m; linear image filtering and field cells affect the exact width. Geographic source shader selection is unchanged and exact XY coverage guards force source contribution to zero outside both photographs. No alpha, boundary movement, new route, internal road-edge blur or survey claim. Geometry protection includes local vertices/topology/indices/smooth/UV, object pose and visibility; it does not audit general attributes, modifiers or evaluated geometry.'}
