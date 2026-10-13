"""Add restrained coarse paving courses inside three retained source aprons.

The caller supplies campus_expansion.py globals after its existing craft pass.
Only new overlay meshes and independent material copies are created. Original
source surfaces, buildings, planting, roads and their material graphs remain.
"""
import math


def add_courtyard_finish(context):
    import bpy
    from shapely import constrained_delaunay_triangles
    from shapely.geometry import Polygon, GeometryCollection
    from shapely.ops import unary_union

    scene = context['s']; digest = context['lake_digest']
    snapshot = context['spatial_mesh_snapshot']; graph_state = context['facade_graph_state']
    gp = context['gp']; layout = context['D']
    numeric_inset = .0005
    z_lift = .002
    band_width = 2.6; band_spacing = 12.0
    perimeter_inset = 1.35; perimeter_width = 2.2
    specs = [('Joined source academic hard courtyard', 'N34 academic court', 'north'),
             ('Expansion surveyed plaza E formal garden plaza', 'E formal garden plaza', 'extension'),
             ('Expansion surveyed plaza M field pedestrian wedge', 'M field pedestrian wedge', 'middle')]
    batch_names = ['Courtyard retained source perimeter courses', 'Courtyard retained source cross courses']
    assert not any(name in scene.objects for name in batch_names)
    bpy.context.view_layer.update()

    def parts(shape):
        if shape.is_empty:
            return []
        if shape.geom_type == 'Polygon':
            return [shape]
        if not hasattr(shape, 'geoms'):
            return []
        result = []
        for child in shape.geoms:
            result.extend(parts(child))
        return result

    def ring_values(ring):
        values = [tuple(v) for v in list(ring.coords)[:-1]]
        options = []
        for sequence in (values, values[::-1]):
            start = min(range(len(sequence)), key=lambda i: sequence[i])
            options.append(sequence[start:] + sequence[:start])
        return min(options)

    def shape_values(shape):
        return sorted([[ring_values(part.exterior), sorted(ring_values(ring) for ring in part.interiors)]
                       for part in parts(shape)])

    def flat_shape(ob):
        assert ob.type == 'MESH' and not ob.hide_render and len(ob.modifiers) == 0, ob.name
        vertices = [ob.matrix_world @ vertex.co for vertex in ob.data.vertices]
        caps = []; elevations = []
        for face in ob.data.polygons:
            values = [vertices[i] for i in face.vertices]
            zs = [value.z for value in values]
            assert max(zs) - min(zs) < 1e-6, (ob.name, zs)
            polygon = Polygon([(value.x, value.y) for value in values])
            assert polygon.is_valid and polygon.area > 1e-8, ob.name
            caps.append(polygon); elevations.append(zs[0])
        assert caps and max(elevations) - min(elevations) < 1e-6, ob.name
        return unary_union(caps), elevations[0]

    # Existing exclusions keep their source extents. No new vegetation or
    # navigation outline is inferred from either the screenshot or POI data.
    excluded_shapes = [context['roofs'].buffer(.035), context['water'].buffer(.035),
                       context['asphalt'].buffer(.035), context['ctx']['road'].buffer(.035),
                       context['planting_mask'].buffer(.035),
                       context['ctx']['source_beds'].buffer(.035)]
    root_shapes = context['root_pit_shapes']
    if root_shapes:
        excluded_shapes.append(unary_union(root_shapes).buffer(.035))
    exclusions = unary_union(excluded_shapes)
    source_meshes = [scene.objects[name] for name, _, _ in specs]
    protected_before = snapshot(ob for ob in scene.objects if ob.type == 'MESH' and not ob.hide_render)
    source_before = snapshot(source_meshes)
    material_before = {material.name: digest(graph_state(material.node_tree))
                       for material in bpy.data.materials if material.use_nodes}
    world_before = digest(graph_state(scene.world.node_tree))
    roofs_before = digest(context['faces'])
    original_object_names = {ob.name for ob in scene.objects}
    original_material_names = {material.name for material in bpy.data.materials}
    image_before = sorted((image.name, image.filepath) for image in bpy.data.images)
    material_copy_proofs = {}
    palette = []
    batches = [{'vertices': [], 'faces': [], 'indices': []},
               {'vertices': [], 'faces': [], 'indices': []}]
    sites = []

    def new_material(base, name, multiplier):
        assert name not in bpy.data.materials
        material = base.copy(); material.name = name
        source_graph = graph_state(base.node_tree)
        assert source_graph == graph_state(material.node_tree), name
        ns = material.node_tree.nodes; links = material.node_tree.links
        bsdf = next(node for node in ns if node.bl_idname == 'ShaderNodeBsdfPrincipled')
        original_nodes = {node.name for node in ns}
        assert 'Retained stone coarse course value' not in original_nodes
        previous = bsdf.inputs['Base Color'].links[0].from_socket if bsdf.inputs['Base Color'].is_linked else None
        tint = ns.new('ShaderNodeMixRGB'); tint.name = 'Retained stone coarse course value'
        tint.blend_type = 'MULTIPLY'; tint.inputs[0].default_value = 1
        tint.inputs[2].default_value = (*multiplier, 1)
        if previous:
            links.new(previous, tint.inputs[1])
        else:
            tint.inputs[1].default_value = bsdf.inputs['Base Color'].default_value
        links.new(tint.outputs[0], bsdf.inputs['Base Color'])
        def retained_graph(state):
            return {'nodes': [row for row in state['nodes'] if row['name'] in original_nodes],
                    'links': [row for row in state['links'] if row[0] in original_nodes and row[2] in original_nodes
                              and not (row[2] == bsdf.name and row[3] == bsdf.inputs['Base Color'].identifier)]}
        copied_graph = graph_state(material.node_tree)
        assert {row['name'] for row in copied_graph['nodes']} == original_nodes | {tint.name}, name
        assert retained_graph(source_graph) == retained_graph(copied_graph), name
        material_copy_proofs[name] = {
            'source_material': base.name, 'source_graph_sha256': digest(source_graph),
            'retained_original_nodes_and_internal_links_sha256': digest(retained_graph(source_graph)),
            'original_node_count': len(original_nodes),
            'only_changed_source_connection': 'Principled Base Color receives one added multiply tint'}
        return material

    def add_faces(batch, shape, z, material_index):
        start = len(batch['faces'])
        for part in parts(shape):
            for triangle in constrained_delaunay_triangles(part).geoms:
                values = list(triangle.exterior.coords)[:-1]
                assert len(values) == 3
                a, b, c = values
                cross_z = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
                assert abs(cross_z) > 1e-12
                if cross_z < 0:
                    values = [a, c, b]
                index = len(batch['vertices'])
                batch['vertices'].extend([(x, y, z) for x, y in values])
                batch['faces'].append((index, index + 1, index + 2))
                batch['indices'].append(material_index)
        return [start, len(batch['faces'])]

    for ob, (_, source_id, region) in zip(source_meshes, specs):
        footprint, base_z = flat_shape(ob)
        assert len(ob.data.materials) == 1 and ob.data.materials[0] is not None, ob.name
        base_material = ob.data.materials[0]
        if source_id == 'N34 academic court':
            origin_row = next(row for row in context['ctx']['ground_revision']['areas'] if row['name'] == ob.name)
            source_pixels = origin_row['source_pixels']; source = 'satellite'
        else:
            origin_row = next(row for row in layout['landscape']['paving_polygons'] if row['id'] == source_id)
            source_pixels = origin_row['outline']; source = origin_row.get('source', 'satellite')
        source_points = [gp(point, source=source) for point in source_pixels]
        source_outline = Polygon([(point.x, point.y) for point in source_points])
        assert footprint.difference(source_outline.buffer(.0002)).area < 1e-7, ob.name
        safe = footprint.difference(exclusions).buffer(-numeric_inset)
        assert safe.area > 200, (ob.name, footprint.area, safe.area)
        edges = [(a, b) for a, b in zip(source_points, source_points[1:] + source_points[:1])]
        a, b = max(edges, key=lambda edge: (edge[1] - edge[0]).length_squared)
        length = math.hypot(b.x - a.x, b.y - a.y)
        u = ((b.x - a.x) / length, (b.y - a.y) / length)
        if u[0] < 0 or (abs(u[0]) < 1e-12 and u[1] < 0):
            u = (-u[0], -u[1])
        v = (-u[1], u[0]); origin = (source_points[0].x, source_points[0].y)

        def local(point):
            dx, dy = point[0] - origin[0], point[1] - origin[1]
            return dx * u[0] + dy * u[1], dx * v[0] + dy * v[1]

        def rectangle(x0, y0, x1, y1):
            return Polygon([(origin[0] + x * u[0] + y * v[0], origin[1] + x * u[1] + y * v[1])
                            for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))])

        local_points = [local(value) for part in parts(safe) for value in part.exterior.coords]
        xmin, xmax = min(p[0] for p in local_points), max(p[0] for p in local_points)
        ymin, ymax = min(p[1] for p in local_points), max(p[1] for p in local_points)
        # Both levels are insets of the retained footprint, including its
        # courtyard holes. Outer kerbs and source garden courses stay visible.
        perimeter = safe.buffer(-perimeter_inset).difference(safe.buffer(-(perimeter_inset + perimeter_width)))
        inner = safe.buffer(-(perimeter_inset + perimeter_width + .35))
        bands = []
        for index in range(math.floor(xmin / band_spacing), math.ceil(xmax / band_spacing) + 1):
            x = index * band_spacing
            bands.append(rectangle(x - band_width / 2, ymin - 1, x + band_width / 2, ymax + 1).intersection(inner))
        cross = unary_union(bands)
        assert perimeter.area > 10 and cross.area > 10, (ob.name, perimeter.area, cross.area)
        assert perimeter.intersection(cross).area < 1e-7
        overlay = perimeter.union(cross)
        assert overlay.difference(footprint).area < 1e-7 and overlay.intersection(exclusions).area < 1e-7
        assert overlay.area < footprint.area * .75, (ob.name, overlay.area, footprint.area)
        edge_material = new_material(base_material, 'Courtyard ' + source_id + ' perimeter stone', (.76, .79, .77))
        band_material = new_material(base_material, 'Courtyard ' + source_id + ' cross stone', (.88, .89, .85))
        palette.append((edge_material, band_material))
        indices = len(palette) - 1
        face_ranges = [add_faces(batches[0], perimeter, base_z + z_lift, indices),
                       add_faces(batches[1], cross, base_z + z_lift, indices)]
        sites.append({'source_object': ob.name, 'source_id': source_id, 'region': region, 'source': source,
                      'source_pixels': source_pixels, 'source_paved_area_m2': footprint.area,
                      'source_paved_footprint_sha256': digest(shape_values(footprint)),
                      'safe_paved_area_m2': safe.area, 'base_z_m_estimate': base_z,
                      'overlay_z_m_estimate': base_z + z_lift, 'axis_u_world_xy': u,
                      'source_world_bounds': [*footprint.bounds, base_z],
                      'perimeter_area_m2': perimeter.area, 'cross_course_area_m2': cross.area,
                      'uncovered_source_area_m2': footprint.area - overlay.area,
                      'overlay_footprint_sha256': digest(shape_values(overlay)),
                      'planned_overlay_outside_source_m2': overlay.difference(footprint).area,
                      'planned_overlay_exclusion_intersection_m2': overlay.intersection(exclusions).area,
                      'source_material': base_material.name,
                      'source_material_graph_sha256': digest(graph_state(base_material.node_tree)),
                      'new_materials': [edge_material.name, band_material.name], 'batch_face_ranges': face_ranges})

    created = []
    for style, (name, batch) in enumerate(zip(batch_names, batches)):
        assert batch['faces']
        mesh = bpy.data.meshes.new(name); mesh.from_pydata(batch['vertices'], [], batch['faces'])
        for materials in palette:
            mesh.materials.append(materials[style])
        for face, index in zip(mesh.polygons, batch['indices']):
            face.material_index = index
        mesh.update(); ob = bpy.data.objects.new(name, mesh); scene.collection.objects.link(ob)
        assert all(face.normal.z > .999999 for face in mesh.polygons), name
        created.append(ob)
    bpy.context.view_layer.update()
    for index, site in enumerate(sites):
        rendered = []; zs = []
        for style, ob in enumerate(created):
            start, end = site['batch_face_ranges'][style]
            for face in list(ob.data.polygons)[start:end]:
                values = [ob.matrix_world @ ob.data.vertices[i].co for i in face.vertices]
                rendered.append(Polygon([(point.x, point.y) for point in values]))
                zs.extend(point.z for point in values)
        actual = unary_union(rendered)
        original, actual_base_z = flat_shape(source_meshes[index])
        assert actual.difference(original).area < 1e-7, (site['source_id'], actual.difference(original).area)
        assert actual.intersection(exclusions).area < 1e-7, (site['source_id'], actual.intersection(exclusions).area)
        assert all(abs(z - actual_base_z - z_lift) < 1e-6 for z in zs)
        site.update({'actual_overlay_area_m2': actual.area,
                     'actual_overlay_outside_source_m2': actual.difference(original).area,
                     'actual_overlay_exclusion_intersection_m2': actual.intersection(exclusions).area,
                     'actual_overlay_world_bounds': [*actual.bounds, min(zs), max(zs)],
                     'overlay_triangle_count': len(rendered), 'actual_overlay_footprint_sha256': digest(shape_values(actual))})
    protected_after = snapshot(scene.objects[name] for name in protected_before)
    assert protected_before == protected_after
    assert source_before == snapshot(source_meshes)
    assert material_before == {name: digest(graph_state(bpy.data.materials[name].node_tree)) for name in material_before}
    assert world_before == digest(graph_state(scene.world.node_tree)) and roofs_before == digest(context['faces'])
    assert {ob.name for ob in scene.objects} - original_object_names == set(batch_names)
    new_materials = [material for pair in palette for material in pair]
    assert {m.name for m in bpy.data.materials} - original_material_names == {m.name for m in new_materials}
    assert image_before == sorted((image.name, image.filepath) for image in bpy.data.images)
    return {'site_count': len(sites), 'sites': sites, 'new_mesh_count': len(created),
            'new_material_count': len(new_materials), 'new_image_count': 0,
            'coarse_course_width_m_estimate': band_width, 'coarse_course_spacing_m_estimate': band_spacing,
            'perimeter_inset_m_estimate': perimeter_inset, 'perimeter_width_m_estimate': perimeter_width,
            'overlay_height_above_retained_source_m_estimate': z_lift,
            'numeric_inset_m': numeric_inset, 'numeric_inset_method': 'Inset added overlay before float32 mesh conversion; does not enlarge source containment tolerance',
            'actual_overlay_outside_source_m2': sum(site['actual_overlay_outside_source_m2'] for site in sites),
            'actual_overlay_exclusion_intersection_m2': sum(site['actual_overlay_exclusion_intersection_m2'] for site in sites),
            'original_source_meshes_geometry_uv_slots_transforms_visibility_preserved': True,
            'source_mesh_input_sha256': digest(source_before), 'source_mesh_output_sha256': digest(snapshot(source_meshes)),
            'overlay_mesh_geometry_uv_visibility_sha256': digest(snapshot(created)),
            'other_existing_visible_mesh_count': len(protected_before),
            'other_existing_visible_meshes_preserved': True,
            'other_existing_visible_mesh_sha256': digest(protected_before),
            'existing_material_graphs_preserved': True, 'existing_material_graphs_sha256': digest(material_before),
            'new_material_graph_sha256': {m.name: digest(graph_state(m.node_tree)) for m in new_materials},
            'new_material_source_graph_preservation': material_copy_proofs,
            'original_fine_stone_course_and_normal_graphs_retained': True,
            'existing_image_inventory_preserved': True, 'existing_image_inventory_sha256': digest(image_before),
            'all_overlay_faces_upward': True, 'minimum_overlay_normal_z': min(face.normal.z for ob in created for face in ob.data.polygons),
            'world_and_roof_faces_preserved': True, 'world_graph_sha256': world_before, 'roof_faces_sha256': roofs_before,
            'new_batches': batch_names, 'overlay_triangle_count': sum(len(ob.data.polygons) for ob in created),
            'limitations': 'Estimated finish pattern inside retained source paving, not a photographed exact slab pattern, new route, surveyed facility or reference acceptance. Original mesh/UV/material-slot/pose/visibility snapshot protection does not audit general attributes, modifiers or evaluated geometry. Existing garden concentric/diagonal courses and source perimeter kerbs are outside this three-surface scope; final derived overlay containment is checked with no expanded tolerance.'}
