"""In-memory, source-positioned leaf volumes for the existing atlas crowns.

The retained photo crowns remain intact and are hidden only after their derived
replacements pass checks. Leaf groups are display proxies, not measured leaves,
species, crown dimensions or additional planting locations.
"""
import hashlib
import json
import math
import random


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def _source_seed(category, xy):
    return hashlib.sha256(json.dumps([category, xy], separators=(',', ':')).encode()).digest()


def _plain(value):
    if hasattr(value, 'to_dict'):
        return {key: _plain(item) for key, item in value.to_dict().items()}
    if hasattr(value, 'to_list'):
        return [_plain(item) for item in value.to_list()]
    return value


def _mesh_state(mesh):
    return {
        'vertices': [list(v.co) for v in mesh.vertices],
        'faces': [[list(f.vertices), f.material_index, f.use_smooth] for f in mesh.polygons],
        'slots': [m.name if m else None for m in mesh.materials],
        'uv': {uv.name: [list(loop.uv) for loop in uv.data] for uv in mesh.uv_layers},
        'uv_active': mesh.uv_layers.active_index,
        'uv_render': [[uv.name, uv.active_render] for uv in mesh.uv_layers],
    }


def _objects_state(objects, digest, include_visibility=True):
    meshes = {}
    rows = []
    for ob in objects:
        pointer = ob.data.as_pointer()
        if pointer not in meshes:
            meshes[pointer] = digest(_mesh_state(ob.data))
        row = [ob.name, meshes[pointer], [list(v) for v in ob.matrix_world],
               list(ob.color), {key: _plain(ob[key]) for key in ob.keys()}]
        if include_visibility:
            row += [ob.hide_render, ob.hide_viewport]
        rows.append(row)
    return sorted(rows, key=_canonical)


def _unit(v):
    length = math.sqrt(sum(q*q for q in v))
    return tuple(q/length for q in v)


def _hull(points):
    points = sorted(set(points))
    def turn(a, b, c):
        return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    lower = []
    for point in points:
        while len(lower) > 1 and turn(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper = []
    for point in reversed(points):
        while len(upper) > 1 and turn(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return lower[:-1]+upper[:-1]


def _leaf_volume(width, variant, bottom, top):
    """Return one opaque folded-leaf prototype; no Blender or image sampling."""
    rng = random.Random(71329+variant*104729)
    count = 6+variant % 4
    vertices, faces, indices, groups = [], [], [], []
    # The lower central spray meets the existing underlying native foliage.
    centres = [(-.022, .017, -.43)]
    phase = rng.uniform(0, math.tau)
    for group in range(1, count):
        angle = phase+group*2.399963229728653+rng.uniform(-.32, .32)
        cloud = .43/width
        radius = min(rng.uniform(.19, .34), .47-cloud-.34/width)
        assert radius > .04
        centres.append((math.cos(angle)*radius, math.sin(angle)*radius,
                        rng.uniform(-.15, .25)))
    for group, centre in enumerate(centres):
        first = len(vertices)
        for blade in range(96):
            angle = rng.uniform(0, math.tau)
            radius = math.sqrt(rng.random())*.43/width
            p = (centre[0]+math.cos(angle)*radius,
                 centre[1]+math.sin(angle)*radius,
                 centre[2]+rng.uniform(-.14, .14))
            yaw = rng.uniform(0, math.tau)
            u = _unit((math.cos(yaw), math.sin(yaw), rng.uniform(-.55, .55)))
            v = _unit((-math.sin(yaw), math.cos(yaw), rng.uniform(-.25, .25)))
            length, breadth = rng.uniform(.225, .335)/width, rng.uniform(.12, .205)/width
            u = tuple(q*length for q in u)
            v = tuple(q*breadth for q in v)
            fold = rng.uniform(.009, .022)
            corners = [tuple(p[k]-u[k] for k in range(3)),
                       tuple(p[k]-v[k]+(fold if k == 2 else 0) for k in range(3)),
                       tuple(p[k]+u[k] for k in range(3)),
                       tuple(p[k]+v[k]+(fold if k == 2 else 0) for k in range(3))]
            assert all(abs(p[0]) <= .5 and abs(p[1]) <= .5 for p in corners)
            offset = len(vertices)
            vertices.extend(corners)
            faces.append((offset, offset+1, offset+2, offset+3))
            # Leaf groups carry different pigment mixes, not a shared baked
            # bright centre, dark hole or illuminated ring from a photograph.
            indices.append(rng.choices((0, 1, 2), (.23, .57, .20))[0])
        groups.append(list(range(first, len(vertices))))
    lo, hi = min(p[2] for p in vertices), max(p[2] for p in vertices)
    vertices = [(x, y, bottom+(z-lo)/(hi-lo)*(top-bottom)) for x, y, z in vertices]
    diameters = []
    for group in groups:
        hull = _hull([(vertices[i][0], vertices[i][1]) for i in group])
        diameters.append(max(math.dist(a, b) for a in hull for b in hull))
    return vertices, faces, indices, diameters, count


def add_canopy_volume(state):
    import bpy
    from mathutils import Vector

    scene, digest = state['s'], state['lake_digest']
    prefixes = state['canopy_prefixes']
    targets = [ob for ob in state['crowns'] if not ob.name.startswith('Garden source oval shrub canopy ')]
    shrubs = [ob for ob in state['crowns'] if ob.name.startswith('Garden source oval shrub canopy ')]
    assert len(targets) == 1850 and len(shrubs) == 8
    assert all(not ob.hide_render and ob.parent is None for ob in targets)
    assert not any(ob.name.startswith('Expansion volume crown ') for ob in scene.objects)
    original_before = _objects_state(targets, digest, include_visibility=False)
    shrubs_before = _objects_state(shrubs, digest)
    # This retained recipe has 1971 source centres, including its earlier
    # exclusion checkpoints. No additional centre is introduced by this pass.
    pairs = state['pairs']
    assert len(pairs) == 1971 and len({row[0] for row in pairs}) == 1971
    source_objects = [scene.objects[row[0]] for row in pairs]
    source_objects += [ob for ob in scene.objects if ob.type == 'MESH' and 'trunk' in ob.name.lower()]
    source_before = _objects_state(source_objects, digest)
    graph_state = state['facade_graph_state']
    material_before = {m.name: digest(graph_state(m.node_tree)) for m in bpy.data.materials if m.use_nodes}
    world_before = digest(graph_state(scene.world.node_tree))

    # Cache leaf vertices by retained mesh, excluding bark and branch faces.
    leaf_vertices = {}
    def retained_leaf_vertices(mesh):
        key = mesh.as_pointer()
        if key not in leaf_vertices:
            slots = {i for i, mat in enumerate(mesh.materials)
                     if mat and mat.name.startswith(('Study broadleaf ', 'Lake folded foliage '))}
            assert slots, mesh.name
            vertex_ids = {i for face in mesh.polygons if face.material_index in slots for i in face.vertices}
            leaf_vertices[key] = [tuple(mesh.vertices[i].co) for i in sorted(vertex_ids)]
        return leaf_vertices[key]
    # Source prototype-to-name assignment may change across Python processes.
    # Use the entire retained north prototype library for a conservative,
    # deterministic top limit, then verify the actual assigned leaf vertices.
    library = state['n']['protos']
    assert len(library) == 12
    library_min_top = min(max(p[2] for p in retained_leaf_vertices(mesh)) for mesh in library)
    descriptions = []
    for old in targets:
        source = scene.objects[old['source_tree']]
        row = source.matrix_world[2]
        zs = [row[0]*p[0]+row[1]*p[1]+row[2]*p[2]+row[3] for p in retained_leaf_vertices(source.data)]
        leaf_lo, leaf_hi = min(zs), max(zs)
        assert abs(row[0]) < 1e-7 and abs(row[1]) < 1e-7 and row[2] > 0
        assert source.data in library
        matrix = old.matrix_world.copy()
        assert abs(matrix[0][2]) < 1e-7 and abs(matrix[1][2]) < 1e-7 and matrix[2][2] > 0
        scales = [math.hypot(matrix[0][i], matrix[1][i]) for i in (0, 1)]
        origin, sz = matrix[2][3], matrix[2][2]
        category = next(prefix for prefix in prefixes if old.name.startswith(prefix)).strip()
        xy = [round(float(v), 6) for v in old['source_position_xy']]
        seed = _source_seed(category, xy)
        expected_colour = [int.from_bytes(seed[a:a+4], 'big')/4294967295 for a in (8, 12, 16)]
        assert all(abs(old.color[i]-expected_colour[i]) < 1e-6 for i in range(3))
        assert all(abs(matrix[i][3]-source.matrix_world[i][3]) < 1e-5 for i in (0, 1))
        descriptions.append({'old': old, 'category': category, 'xy': xy, 'seed': seed, 'matrix': matrix,
            'width': max(scales), 'scales': scales, 'leaf_z': (leaf_lo, leaf_hi),
            'bottom_interval': ((leaf_lo-.05-origin)/sz, (leaf_hi-.25-origin)/sz),
            'conservative_top': (row[3]+row[2]*library_min_top+.35-origin)/sz,
            'peak': max(v.co.z for v in old.data.vertices)})
    descriptions.sort(key=lambda row: _canonical([row['category'], row['xy']]))
    assert len({_canonical([row['category'], row['xy']]) for row in descriptions}) == 1850
    # A common depth makes the 24 meshes shareable while every instance's
    # actual native leaf-height interval still contains its lower foliage.
    # Fixed lower depth and the library-wide top guard avoid allowing the
    # process-specific prototype/name allocation to alter replacement meshes.
    bottom = -.72
    assert all(lo+.001 < bottom < hi-.001 for lo, hi in (row['bottom_interval'] for row in descriptions))
    top = min(min(row['peak']*.90, row['conservative_top']) for row in descriptions)-.001
    assert bottom+.15 < top
    min_width, max_width = min(row['width'] for row in descriptions), max(row['width'] for row in descriptions)
    assert min_width > 1.8 and max_width/min_width < 25
    edges = [min_width*(max_width/min_width)**(i/4) for i in range(5)]
    widths = [math.sqrt(edges[i]*edges[i+1]) for i in range(4)]

    # Read the existing native north palette. New shaders are opaque and do not
    # alter any retained material or sample the shared composite leaf picture.
    palette = []
    for material in state['n']['leaves']:
        bs = next(node for node in material.node_tree.nodes if node.bl_idname == 'ShaderNodeBsdfPrincipled')
        palette.append((material.name, list(bs.inputs['Base Color'].default_value)))
    palette.sort(key=lambda row: sum(row[1][i]*w for i, w in enumerate((.2126, .7152, .0722))))
    selected = [palette[i] for i in (1, len(palette)//2, len(palette)-2)]
    materials = []
    material_hsv_ranges, material_bsdf = {}, {}
    for index, (_, colour) in enumerate(selected):
        material = bpy.data.materials.new('Expansion volume leaf pigment '+str(index))
        material.use_nodes = True
        nodes, links = material.node_tree.nodes, material.node_tree.links
        nodes.clear()
        info = nodes.new('ShaderNodeObjectInfo')
        channels = nodes.new('ShaderNodeSeparateColor'); channels.mode = 'RGB'
        links.new(info.outputs['Color'], channels.inputs[0])
        hsv = nodes.new('ShaderNodeHueSaturation'); hsv.inputs['Color'].default_value = colour
        material_hsv_ranges[material.name] = {}
        for socket, channel, lo, hi in [('Hue', 'Red', .485, .512), ('Saturation', 'Green', .98, 1.12), ('Value', 'Blue', 1.04, 1.24)]:
            mapped = nodes.new('ShaderNodeMapRange'); mapped.clamp = True
            mapped.inputs['To Min'].default_value = lo; mapped.inputs['To Max'].default_value = hi
            links.new(channels.outputs[channel], mapped.inputs['Value']); links.new(mapped.outputs['Result'], hsv.inputs[socket])
            actual = [mapped.inputs[key].default_value for key in ('From Min', 'From Max', 'To Min', 'To Max')]
            assert mapped.clamp and all(abs(a-b) < 1e-6 for a, b in zip(actual, (0, 1, lo, hi)))
            material_hsv_ranges[material.name][socket] = {'from': actual[:2], 'to': actual[2:], 'clamped': mapped.clamp}
        bs = nodes.new('ShaderNodeBsdfPrincipled')
        bs.inputs['Roughness'].default_value = .84
        bs.inputs['Alpha'].default_value = 1
        bs.inputs['Emission Strength'].default_value = 0
        links.new(hsv.outputs['Color'], bs.inputs['Base Color'])
        output = nodes.new('ShaderNodeOutputMaterial'); links.new(bs.outputs[0], output.inputs['Surface'])
        material_bsdf[material.name] = {key: bs.inputs[key].default_value for key in ('Roughness', 'Emission Strength', 'Alpha')}
        assert all(abs(material_bsdf[material.name][key]-value) < 1e-6
                   for key, value in [('Roughness', .84), ('Emission Strength', 0), ('Alpha', 1)])
        materials.append(material)

    prototypes = {}
    for band, width in enumerate(widths):
        for variant in range(6):
            ident = str(band)+'_'+str(variant)
            vertices, faces, indices, diameters, group_count = _leaf_volume(width, variant, bottom, top)
            mesh = bpy.data.meshes.new('Expansion volume foliage '+ident)
            mesh.from_pydata(vertices, [], faces); mesh.update()
            for material in materials:
                mesh.materials.append(material)
            for face, material_index in zip(mesh.polygons, indices):
                face.material_index = material_index
                face.use_smooth = False
            assert len(mesh.polygons) == 96*group_count <= 864 and len(mesh.vertices) == len(mesh.polygons)*4
            assert all(len(face.vertices) == 4 for face in mesh.polygons)
            prototypes[ident] = {'mesh': mesh, 'diameters': diameters, 'groups': group_count,
                                 'triangles': sum(len(face.vertices)-2 for face in mesh.polygons),
                                 'hull': _hull([(v.co.x, v.co.y) for v in mesh.vertices])}
    usage = {key: 0 for key in prototypes}
    assignments, transformations, positions, contacts, created = [], [], [], [], []
    clump_low, clump_high, extra_triangles, extra_roof, extra_water = math.inf, 0, 0, 0., 0.
    Polygon = state['Polygon']
    for ordinal, row in enumerate(descriptions):
        old, matrix = row['old'], row['matrix']
        band = min(3, next((i for i in range(4) if row['width'] <= edges[i+1]), 3))
        variant = int.from_bytes(row['seed'][:8], 'big') % 6
        ident = str(band)+'_'+str(variant); prototype = prototypes[ident]; mesh = prototype['mesh']
        new = bpy.data.objects.new('Expansion volume crown '+str(ordinal), mesh)
        scene.collection.objects.link(new); new.matrix_world = matrix; new.color = old.color
        assert len(new.modifiers) == 0
        # Copy the original transform components too, avoiding a different
        # Euler decomposition on the subsequent dependency-graph update.
        assert old.rotation_mode == 'XYZ'
        new.location = old.location; new.rotation_euler = old.rotation_euler; new.scale = old.scale
        new.delta_location = old.delta_location; new.delta_rotation_euler = old.delta_rotation_euler
        new.delta_scale = old.delta_scale
        new.hide_viewport = old.hide_viewport
        for key in old.keys():
            new[key] = _plain(old[key])
        new['canopy_volume_source_crown'] = old.name
        new['canopy_volume_prototype'] = ident
        assert [list(v) for v in new.matrix_world] == [list(v) for v in matrix]
        assert list(new.color) == list(old.color)
        assert all(-.500001 <= v.co.x <= .500001 and -.500001 <= v.co.y <= .500001 for v in mesh.vertices)
        origin, sz = matrix[2][3], matrix[2][2]
        new_z = [origin+sz*min(v.co.z for v in mesh.vertices), origin+sz*max(v.co.z for v in mesh.vertices)]
        assert new_z[0] >= row['leaf_z'][0]-.05001 and new_z[0] <= row['leaf_z'][1]-.24999
        assert new_z[1] <= row['leaf_z'][1]+.35001
        assert max(v.co.z for v in mesh.vertices) <= row['peak']+1e-6
        old_xy = Polygon([tuple(matrix@Vector((x, y, 0)))[:2] for x, y in [(-.5, -.5), (.5, -.5), (.5, .5), (-.5, .5)]])
        new_xy = Polygon([tuple(matrix@Vector((x, y, 0)))[:2] for x, y in prototype['hull']])
        extra = new_xy.difference(old_xy.buffer(1e-7))
        assert extra.area < 1e-8
        extra_roof += extra.intersection(state['roofs']).area
        extra_water += extra.intersection(state['water']).area
        for diameter in prototype['diameters']:
            clump_low = min(clump_low, diameter*min(row['scales']))
            clump_high = max(clump_high, diameter*max(row['scales']))
        usage[ident] += 1; extra_triangles += prototype['triangles']
        assignments.append([row['category'], row['xy'], ident, list(new.color)])
        transformations.append([row['category'], row['xy'], [list(v) for v in new.matrix_world]])
        positions.append([row['category'], row['xy'], list(new.matrix_world.translation)])
        contacts.append([row['category'], row['xy'], list(row['leaf_z']), new_z])
        created.append((new, matrix))
    bpy.context.view_layer.update()
    assert all([list(v) for v in ob.matrix_world] == [list(v) for v in matrix] for ob, matrix in created)
    assert extra_triangles == sum(prototypes[key]['triangles']*count for key, count in usage.items())
    assert extra_triangles <= 3_000_000 and extra_roof < 1e-7 and extra_water < 1e-7
    assert .8 <= clump_low <= clump_high <= 2.02, (clump_low, clump_high)
    assert original_before == _objects_state(targets, digest, include_visibility=False)
    assert shrubs_before == _objects_state(shrubs, digest)
    assert source_before == _objects_state(source_objects, digest)
    assert material_before == {name: digest(graph_state(bpy.data.materials[name].node_tree)) for name in material_before}
    assert world_before == digest(graph_state(scene.world.node_tree))
    # This is the only mutation to an existing object in the entire module.
    for old in targets:
        old.hide_render = True
    assert all(ob.hide_render for ob in targets)
    return {
        'count': len(targets), 'prototype_count': len(prototypes), 'shared_mesh_count': len(prototypes),
        'prototype_usage': usage,
        'blades_per_clump_actual': next(iter({len(value['mesh'].polygons)//value['groups'] for value in prototypes.values()})),
        'prototype_clump_counts': {key: value['groups'] for key, value in prototypes.items()},
        'prototype_face_counts': {key: len(value['mesh'].polygons) for key, value in prototypes.items()},
        'prototype_triangle_counts': {key: value['triangles'] for key, value in prototypes.items()},
        'shared_mesh_sha256': {key: digest(_mesh_state(value['mesh'])) for key, value in prototypes.items()},
        'assignment_sha256': digest(assignments), 'transform_sha256': digest(transformations),
        'source_position_sha256': digest(positions), 'contact_height_sha256': digest(contacts),
        'original_crown_local_mesh_uv_transforms_preserved': True,
        'original_crown_state_sha256': digest(original_before), 'original_crowns_hidden_count': len(targets),
        'source_xy_and_bounds_preserved': True, 'preserved_shrub_count': len(shrubs),
        'preserved_shrub_sha256': digest(shrubs_before), 'retained_source_centre_count': len(pairs),
        'source_tree_and_trunk_meshes_transforms_visibility_preserved': True,
        'source_tree_and_trunk_sha256': digest(source_before),
        'existing_material_graphs_and_world_preserved': True, 'existing_material_graphs_sha256': digest(material_before),
        'world_graph_sha256': world_before, 'materials': [m.name for m in materials],
        'material_graph_sha256': {m.name: digest(graph_state(m.node_tree)) for m in materials},
        'material_hsv_ranges_actual': material_hsv_ranges, 'material_bsdf_actual': material_bsdf,
        'native_palette_sources': [name for name, _ in selected], 'native_palette_rgb': [colour for _, colour in selected],
        'alpha_free': all(not node.inputs['Alpha'].is_linked and node.inputs['Alpha'].default_value == 1
                          for material in materials for node in material.node_tree.nodes if node.bl_idname == 'ShaderNodeBsdfPrincipled'),
        'image_node_count': sum(node.bl_idname == 'ShaderNodeTexImage' for material in materials for node in material.node_tree.nodes),
        'instanced_polygon_triangle_count': extra_triangles,
        # Keep the existing verifier's field as a compatibility alias. This
        # count is polygon triangulation arithmetic, not depsgraph evaluation.
        'additional_evaluated_triangles': extra_triangles,
        'triangle_count_method': 'Sum of (polygon vertex count - 2) for each prototype, weighted by actual instance usage; all replacements have no modifiers. additional_evaluated_triangles is a legacy alias, not a dependency-graph measurement.',
        'clump_count_range': [6, 9], 'clump_diameter_xy_bounds_m_estimate': [clump_low, clump_high],
        'local_z_range_m_estimate': [bottom, top], 'width_band_edges_m_estimate': edges,
        'minimum_lower_foliage_height_overlap_m': min(row['leaf_z'][1]-contact[3][0] for row, contact in zip(descriptions, contacts)),
        'new_top_above_source_leaf_top_m_range': [min(contact[3][1]-contact[2][1] for contact in contacts),
                                                 max(contact[3][1]-contact[2][1] for contact in contacts)],
        'library_minimum_leaf_top_local_z': library_min_top,
        'roof_overlap_outside_retained_crown_envelope_m2': extra_roof,
        'water_overlap_outside_retained_crown_envelope_m2': extra_water,
        'per_construction_fields': ['original_crown_state_sha256', 'source_tree_and_trunk_sha256',
                                   'contact_height_sha256', 'minimum_lower_foliage_height_overlap_m',
                                   'new_top_above_source_leaf_top_m_range'],
        'allocation': 'SHA-256 of category and micron-rounded source XY; first eight bytes big-endian modulo six; four geometric width bands; inherited independently allocated Object Color',
        'limitations': 'Estimated opaque leaf-group proxies, not measured leaves or species. Lower foliage overlaps the actual retained leaf Z envelope; not a triangle-intersection claim. Roof/water checks measure conflict outside the retained geometric rectangle, not changed occlusion in photo alpha holes. Source mesh/name allocation and actual contact evidence are per construction. Earlier canopy/foliage checks describe the retained hidden appearance crowns.',
    }
