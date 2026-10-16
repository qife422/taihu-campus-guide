"""Conservatively finish derived middle-campus paving.

regularize_paving returns only planar geometry before mesh creation.
add_paving_edge_finish copies one existing course material after construction.
Neither function writes sources or changes retained layout or tree centres.
"""
import hashlib
import json


def regularize_paving(paving, *, buildings, roofs, outside, roads,
                      traced_finishes, tree_centres):
    from shapely import normalize, to_wkb
    from shapely.geometry import Point, box
    from shapely.ops import unary_union

    radius = 1.20
    window_margin = 12.0
    contact_width = 2.0
    tree_radius = 1.10
    tolerance = 1e-7
    source_ids = [f'M{i:02}' for i in range(1, 8)]
    assert all(key in buildings for key in source_ids)
    assert not paving.is_empty and paving.is_valid

    def polygons(geometry):
        if geometry.is_empty:
            return []
        if geometry.geom_type == 'Polygon':
            return [geometry]
        return [part for child in getattr(geometry, 'geoms', ())
                for part in polygons(child)]

    def fingerprint(geometry):
        return hashlib.sha256(to_wkb(normalize(geometry), byte_order=1,
                                     output_dimension=2)).hexdigest()

    selected_buildings = unary_union([buildings[key] for key in source_ids])
    x0, y0, x1, y1 = selected_buildings.bounds
    bounds = [x0 - window_margin, y0 - window_margin,
              x1 + window_margin, y1 + window_margin]
    window = box(*bounds).intersection(outside)
    candidate = paving.intersection(window)
    assert candidate.is_valid and candidate.area > 200, candidate.area

    # Only centres whose protective circles can touch this window are relevant.
    # Sorting and deduplication remove object-name / source iteration ordering.
    centres = sorted({(float(point[0]), float(point[1])) for point in tree_centres
                      if x0 - window_margin - tree_radius <= point[0] <= x1 + window_margin + tree_radius
                      and y0 - window_margin - tree_radius <= point[1] <= y1 + window_margin + tree_radius})
    tree_areas = unary_union([Point(point).buffer(tree_radius, quad_segs=12)
                             for point in centres])
    original_hole_edges = unary_union([ring for part in polygons(paving)
                                      for ring in part.interiors])
    protected_regions = {
        'building_contact': roofs.buffer(contact_width),
        'road_contact': roads.buffer(contact_width),
        'traced_finishes': traced_finishes,
        'source_tree_roots': tree_areas,
        'window_seam': window.boundary.buffer(2 * radius),
        'original_hole_edges': original_hole_edges.buffer(radius),
    }
    protection = unary_union(list(protected_regions.values()))
    protected = candidate.intersection(protection)
    opened = candidate.buffer(-radius, quad_segs=8).buffer(radius, quad_segs=8)
    cleaned = opened.intersection(candidate).union(protected)
    result = paving.difference(window).union(cleaned)
    assert result.is_valid and not result.is_empty

    removed = paving.difference(result)
    outside_input = result.difference(paving).area
    outside_window = paving.symmetric_difference(result).difference(window).area
    protected_loss = protected.difference(result).area
    boundary_distance = paving.boundary.hausdorff_distance(result.boundary)
    assert outside_input < tolerance, outside_input
    assert outside_window < tolerance, outside_window
    assert protected_loss < tolerance, protected_loss
    assert boundary_distance <= radius + 1e-6, boundary_distance
    assert 1.0 <= removed.area <= min(candidate.area * .03, 100.0), (
        removed.area, candidate.area)

    before_parts = polygons(paving)
    after_parts = polygons(result)
    holes_before = sum(len(part.interiors) for part in before_parts)
    holes_after = sum(len(part.interiors) for part in after_parts)
    assert len(before_parts) == len(after_parts), (len(before_parts), len(after_parts))
    assert holes_before == holes_after, (holes_before, holes_after)
    # Equal totals alone could hide a split in one part and loss of another.
    # Each original connected polygon must retain exactly one polygon and its
    # own original hole count, including parts outside the selected window.
    for part in before_parts:
        retained = polygons(result.intersection(part))
        assert len(retained) == 1, (part.area, len(retained))
        assert len(retained[0].interiors) == len(part.interiors)

    contact_checks = {}
    for name, region in protected_regions.items():
        source = candidate.intersection(region)
        lost = source.difference(result).area
        assert lost < tolerance, (name, lost)
        contact_checks[name] = {'source_area_m2': source.area,
                                'lost_area_m2': lost,
                                'source_geometry_sha256': fingerprint(source)}
    centres_bytes = json.dumps(centres, separators=(',', ':')).encode()
    checks = {
        'status': 'passed',
        'method': '1.20m planar opening of derived paving, intersected with its original footprint; protected source contact areas restored before mesh generation',
        'source_building_ids': source_ids,
        'candidate_world_bounds': bounds,
        'window_margin_m': window_margin,
        'opening_radius_m': radius,
        'road_building_contact_width_m': contact_width,
        'source_tree_protection_radius_m': tree_radius,
        'window_seam_width_m': 2 * radius,
        'source_hole_edge_protection_width_m': radius,
        'input_area_m2': paving.area,
        'output_area_m2': result.area,
        'candidate_input_area_m2': candidate.area,
        'protected_candidate_area_m2': protected.area,
        'eligible_candidate_area_m2': candidate.difference(protection).area,
        'removed_area_m2': removed.area,
        'removed_candidate_fraction': removed.area / candidate.area,
        'removed_area_limit_m2': min(candidate.area * .03, 100.0),
        'removed_area_minimum_m2': 1.0,
        'output_outside_input_area_m2': outside_input,
        'difference_outside_window_area_m2': outside_window,
        'protected_loss_area_m2': protected_loss,
        'boundary_hausdorff_distance_m': boundary_distance,
        'component_count_before': len(before_parts),
        'component_count_after': len(after_parts),
        'hole_count_before': holes_before,
        'hole_count_after': holes_after,
        'each_component_and_its_holes_preserved': True,
        'protected_source_contacts': contact_checks,
        'relevant_source_tree_count': len(centres),
        'relevant_source_tree_centres_sha256': hashlib.sha256(centres_bytes).hexdigest(),
        'input_geometry_sha256': fingerprint(paving),
        'output_geometry_sha256': fingerprint(result),
        'candidate_geometry_sha256': fingerprint(candidate),
        'removed_geometry_sha256': fingerprint(removed),
        'protected_geometry_sha256': fingerprint(protected),
        'fingerprint_method': 'SHA256 of Shapely normalized 2D little-endian WKB; source tree centres sorted and deduplicated without object names',
        'source_geometry_read_only': True,
        'mesh_generation_stage': 'before source grass, paving and perimeter-course meshes',
        'ground_under_paving_preserved': True,
        'limitations': 'Estimated rounding within existing image-classified paving, not a new traced outline, actual entrance survey, pedestrian clearance or navigation validation. No Blender mesh normals, material or existing-object snapshot is asserted by this pure planar helper.',
    }
    return result, checks


def add_paving_edge_finish(state):
    """Reduce the bright derived-paving outline only in the fixed middle window."""
    import bpy
    from shapely.geometry import Polygon, box
    from shapely.ops import unary_union

    scene = state['s']; digest = state['lake_digest']
    graph = state['facade_graph_state']
    target = scene.objects['Expansion paving courses']
    assert target.type == 'MESH' and not target.hide_render and not target.modifiers
    assert len(target.data.materials) == 1 and target.material_slots[0].link == 'DATA'
    source = target.data.materials[0]
    assert source == state['curb'] and source.use_nodes
    bounds = list(state['paving_regularization_checks']['candidate_world_bounds'])
    x0, y0, x1, y1 = bounds
    fade = 2.0; multiplier = [.68, .70, .67]
    assert x1 - x0 > 2 * fade and y1 - y0 > 2 * fade

    def snapshot():
        return {
            'objects': sorted([ob.name, ob.type, ob.data.name if ob.data else None,
                               [list(row) for row in ob.matrix_world],
                               ob.hide_render, ob.hide_viewport]
                              for ob in scene.objects),
            'meshes': {mesh.name: digest({
                'vertices': [list(v.co) for v in mesh.vertices],
                'faces': [[list(f.vertices), f.material_index, f.use_smooth]
                          for f in mesh.polygons],
                'uv': {uv.name: [list(v.uv) for v in uv.data] for uv in mesh.uv_layers}})
                for mesh in bpy.data.meshes},
        }

    before = snapshot()
    slots = {ob.name: [[slot.link, slot.material.name if slot.material else None]
                      for slot in ob.material_slots]
             for ob in scene.objects if ob.type == 'MESH'}
    materials = {mat.name: digest(graph(mat.node_tree))
                 for mat in bpy.data.materials if mat.use_nodes}
    world = digest(graph(scene.world.node_tree))
    source_graph = graph(source.node_tree)
    vertices = [target.matrix_world @ vertex.co for vertex in target.data.vertices]
    assert vertices and all(abs(point.z - .335) < 1e-6 for point in vertices)
    footprint = unary_union([Polygon([(vertices[i].x, vertices[i].y) for i in face.vertices])
                             for face in target.data.polygons])
    scope = box(*bounds)
    affected_area = footprint.intersection(scope).area
    assert affected_area > 10 and footprint.is_valid

    finish = source.copy(); finish.name = 'Middle source paving subdued edge'
    assert graph(finish.node_tree) == source_graph
    nodes = finish.node_tree.nodes; links = finish.node_tree.links
    bsdf = nodes.get('Principled BSDF'); assert bsdf is not None
    old_socket = bsdf.inputs['Base Color']
    assert len(old_socket.links) <= 1
    old_link = old_socket.links[0].from_socket if old_socket.links else None
    old_default = list(old_socket.default_value)
    retained_names = {node.name for node in nodes}

    def node(kind, label):
        item = nodes.new(kind); item.name = 'Middle paving edge ' + label
        return item

    position = node('ShaderNodeNewGeometry', 'world position')
    separate = node('ShaderNodeSeparateXYZ', 'world XY')
    links.new(position.outputs['Position'], separate.inputs[0])
    weights = []
    for axis, low, high in [('X', x0, x1), ('Y', y0, y1)]:
        for side, limit in [('low', low), ('high', high)]:
            distance = node('ShaderNodeMath', axis + ' ' + side + ' distance')
            distance.operation = 'SUBTRACT'
            if side == 'low':
                links.new(separate.outputs[axis], distance.inputs[0])
                distance.inputs[1].default_value = limit
            else:
                distance.inputs[0].default_value = limit
                links.new(separate.outputs[axis], distance.inputs[1])
            ramp = node('ShaderNodeMapRange', axis + ' ' + side + ' fade')
            ramp.interpolation_type = 'SMOOTHSTEP'; ramp.clamp = True
            ramp.inputs['From Min'].default_value = 0
            ramp.inputs['From Max'].default_value = fade
            ramp.inputs['To Min'].default_value = 0
            ramp.inputs['To Max'].default_value = 1
            links.new(distance.outputs[0], ramp.inputs['Value'])
            weights.append(ramp.outputs['Result'])
    weight = weights[0]
    for i, other in enumerate(weights[1:]):
        product = node('ShaderNodeMath', 'window weight ' + str(i))
        product.operation = 'MULTIPLY'
        links.new(weight, product.inputs[0]); links.new(other, product.inputs[1])
        weight = product.outputs[0]
    tint = node('ShaderNodeMixRGB', 'subdued stone colour'); tint.blend_type = 'MULTIPLY'
    links.new(weight, tint.inputs[0])
    if old_link:
        links.new(old_link, tint.inputs[1])
    else:
        tint.inputs[1].default_value = old_default
    tint.inputs[2].default_value = (*multiplier, 1)
    links.new(tint.outputs[0], old_socket)
    target.data.materials[0] = finish

    assert before == snapshot(), 'Paving edge finish changed scene geometry'
    for name, fingerprint in materials.items():
        assert digest(graph(bpy.data.materials[name].node_tree)) == fingerprint, name
    for ob in scene.objects:
        if ob.type != 'MESH' or ob == target:
            continue
        assert [[slot.link, slot.material.name if slot.material else None]
                for slot in ob.material_slots] == slots[ob.name], ob.name
    assert digest(graph(scene.world.node_tree)) == world
    assert target.data.materials[0] == finish and len(target.data.materials) == 1
    assert len(nodes) == len(retained_names) + 14
    assert set(retained_names) <= {item.name for item in nodes}
    assert old_socket.links[0].from_node == tint
    final_graph = graph(finish.node_tree)
    assert [row for row in final_graph['nodes'] if row['name'] in retained_names] == source_graph['nodes']
    retained_links = lambda rows: [row for row in rows if row[0] in retained_names
        and row[2] in retained_names and not (row[2] == bsdf.name and row[3] == old_socket.identifier)]
    assert retained_links(final_graph['links']) == retained_links(source_graph['links'])
    if old_link:
        assert tint.inputs[1].links[0].from_socket == old_link
    else:
        assert list(tint.inputs[1].default_value) == old_default
    assert all(abs(tint.inputs[2].default_value[i] - multiplier[i]) < 1e-6 for i in range(3))
    assert tint.blend_type == 'MULTIPLY' and tint.inputs[0].links[0].from_socket == weight
    for axis, low, high in [('X', x0, x1), ('Y', y0, y1)]:
        for side, limit in [('low', low), ('high', high)]:
            distance = nodes['Middle paving edge ' + axis + ' ' + side + ' distance']
            ramp = nodes['Middle paving edge ' + axis + ' ' + side + ' fade']
            constant = distance.inputs[1] if side == 'low' else distance.inputs[0]
            position_input = distance.inputs[0] if side == 'low' else distance.inputs[1]
            assert abs(constant.default_value - limit) < 1e-5
            assert distance.operation == 'SUBTRACT'
            assert position_input.links[0].from_socket == separate.outputs[axis]
            assert ramp.interpolation_type == 'SMOOTHSTEP' and ramp.clamp
            assert [ramp.inputs[key].default_value for key in ('From Min', 'From Max', 'To Min', 'To Max')] == [0, fade, 0, 1]
            assert ramp.inputs['Value'].links[0].from_socket == distance.outputs[0]
    assert separate.inputs[0].links[0].from_socket == position.outputs['Position']
    return {
        'status': 'passed', 'target': target.name,
        'source_material': source.name, 'finish_material': finish.name,
        'candidate_world_bounds': bounds, 'boundary_fade_m': fade,
        'colour_multiplier': multiplier, 'world_position_mask': True,
        'outside_window_weight': 0, 'interior_weight': 1,
        'shader_mask_method': 'Product of four clamped smoothstep world-XY distances; zero at and outside the fixed source-building window',
        'affected_course_area_m2_estimate': affected_area,
        'course_height_m': .335, 'material_slot_count': 1,
        'new_material_count': 1,
        'added_node_count': len(nodes) - len(retained_names),
        'source_graph_sha256': digest(source_graph),
        'finish_graph_sha256': digest(graph(finish.node_tree)),
        'source_colour_link_retained': old_link is not None,
        'source_nodes_and_other_internal_links_preserved': True,
        'shader_parameters_and_links_read_back': True,
        'other_bsdf_inputs_preserved': True,
        'per_construction_preservation': {
            'scene_geometry_preserved': True,
            'scene_geometry_sha256': digest(before),
            'other_materials_preserved': True,
            'other_material_graphs_sha256': digest(materials),
            'other_object_material_slots_preserved': True,
            'world_graph_preserved': True,
        },
        'limitations': 'Estimated visual stone-edge finish on the existing derived paving course, not a surveyed pavement material. Road margins, traced-plaza courses and source geometry are retained.',
    }
