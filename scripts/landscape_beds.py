"""Source-bounded, estimated low foliage for four retained planting surfaces.

This late in-memory pass keeps the original caps and all existing scene objects.
The new continuous volumes and small folded faces are display geometry, not new
tree positions, an inventory of shrubs, species or surveyed planting heights.
"""
import hashlib
import json
import math
import random
from collections import Counter
from pathlib import Path


TARGETS = (
    ('garden-island-centre', 'Garden source island center planting', .516, .22, 1.0, .16, .61),
    ('garden-east-courses', 'Garden source east planted courses', .215, .045, .65, .16, .34),
    ('E formal garden west bed', 'Expansion planting E formal garden west bed', .447, .32, 1.0, .17, .64),
    ('E formal garden east bed', 'Expansion planting E formal garden east bed', .447, .32, 1.0, .17, .64),
)
PALETTE = ((.070, .170, .026), (.125, .255, .045), (.190, .325, .075))
XY_TOL_M = .0002  # Retained metre-space float32 caps, not geographic accuracy.


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _seed(key):
    return int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], 'big')


def _polygons(shape):
    from shapely.geometry.polygon import orient
    if shape.is_empty:
        return []
    if shape.geom_type == 'Polygon':
        return [orient(shape.normalize(), 1)]
    if shape.geom_type in ('MultiPolygon', 'GeometryCollection'):
        parts = [part for item in shape.geoms for part in _polygons(item)]
        return sorted(parts, key=lambda part: (part.bounds, part.wkb_hex))
    return []


def _shape_values(shape):
    return [[list(part.exterior.coords), [list(ring.coords) for ring in part.interiors]]
            for part in _polygons(shape)]


def _triangles(shape):
    from shapely import constrained_delaunay_triangles
    result = []
    for part in _polygons(shape):
        for triangle in constrained_delaunay_triangles(part).geoms:
            values = [tuple(p) for p in list(triangle.exterior.coords)[:-1]]
            assert len(values) == 3
            a, b, c = values
            cross = (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
            if abs(cross) < 1e-10:
                continue
            if cross < 0:
                values.reverse()
            start = min(range(3), key=lambda index: values[index])
            result.append(values[start:] + values[:start])
    return sorted(result)


def _flat_cap(obj):
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    assert obj.type == 'MESH' and not obj.hide_render and not obj.modifiers, obj.name
    points = [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]
    assert points and max(p.z for p in points)-min(p.z for p in points) < 1e-6, obj.name
    caps = [Polygon([(points[i].x, points[i].y) for i in face.vertices])
            for face in obj.data.polygons]
    assert caps and all(g.is_valid and g.area > 1e-9 for g in caps), obj.name
    shape = unary_union(caps)
    assert shape.is_valid and shape.area > 1
    return shape, float(points[0].z)


def _volume(shape, cap_z, bottom_z, key, cell_size, low, high):
    """Pure geometry: a sealed wavy base plus small opaque folded leaf faces."""
    from shapely.geometry import Point, Polygon, LineString, box
    assert shape.is_valid and shape.area > 1 and bottom_z < cap_z
    phases = [random.Random(_seed(key+' phase '+str(i))).uniform(0, math.tau) for i in range(3)]
    boundary = shape.boundary
    def height(x, y):
        tone = .50 + .21*math.sin(x*2.35+y*.71+phases[0]) \
            + .17*math.sin(y*2.68-x*.57+phases[1]) \
            + .10*math.cos(x*4.11-y*3.37+phases[2])
        edge = min(1, boundary.distance(Point(x, y))/.58)
        return cap_z+low+(high-low)*(.22+.78*edge)*tone

    vertices, faces, indices, cells = [], [], [], []
    vertex_ids = {}
    def vertex(point):
        value = tuple(round(float(v), 8) for v in point)
        if value not in vertex_ids:
            vertex_ids[value] = len(vertices)
            vertices.append(value)
        return vertex_ids[value]
    def face(points, material):
        ids = tuple(vertex(point) for point in points)
        assert len(set(ids)) == len(ids)
        faces.append(ids); indices.append(material)

    x0, y0, x1, y1 = shape.bounds
    for i in range(math.floor(x0/cell_size), math.ceil(x1/cell_size)):
        for j in range(math.floor(y0/cell_size), math.ceil(y1/cell_size)):
            part = shape.intersection(box(i*cell_size, j*cell_size, (i+1)*cell_size, (j+1)*cell_size))
            if part.area < 1e-8:
                continue
            cells.append((i, j, part))
            for tri in _triangles(part):
                centre = [sum(p[k] for p in tri)/3 for k in (0, 1)]
                material = 1 if _seed(key+' cap '+_canonical(centre)) % 10 < 8 else 0
                face([(x, y, height(x, y)) for x, y in tri], material)
    assert faces
    cap_face_count = len(faces)
    cap_vertex_count = len(vertices)
    edge_count, oriented_edges = Counter(), {}
    for ids in faces:
        for a, b in zip(ids, ids[1:]+ids[:1]):
            pair = tuple(sorted((a, b)))
            edge_count[pair] += 1; oriented_edges[pair] = (a, b)
    assert all(count in (1, 2) for count in edge_count.values())
    top_edge_pairs = sorted(pair for pair, count in edge_count.items() if count == 1)
    # The cut-cell tessellation must not leave internal cracks or T junctions.
    for pair in top_edge_pairs:
        a, b = (vertices[index] for index in pair)
        assert LineString([a[:2], b[:2]]).difference(boundary.buffer(1e-6)).length < 1e-6
    bottom_ids = {i: vertex((*vertices[i][:2], bottom_z)) for i in range(cap_vertex_count)}
    for ids in list(faces):
        faces.append(tuple(bottom_ids[i] for i in reversed(ids))); indices.append(0)
    for pair in top_edge_pairs:
        a, b = oriented_edges[pair]
        faces.append((bottom_ids[a], bottom_ids[b], b, a)); indices.append(0)
    body_face_count = len(faces)
    body_edges = Counter(tuple(sorted((a, b))) for ids in faces
                         for a, b in zip(ids, ids[1:]+ids[:1]))
    assert all(count == 2 for count in body_edges.values()), 'Unsealed planting body'

    leaf_count = 0
    for i, j, part in cells:
        rng = random.Random(_seed(key+' leaves '+str(i)+','+str(j)))
        # Display microgeometry samples do not create or declare plant centres.
        count = max(1, round(part.area*8))
        bx0, by0, bx1, by1 = part.bounds
        for blade in range(count):
            point = None
            for trial in range(20):
                candidate = Point(rng.uniform(bx0, bx1), rng.uniform(by0, by1))
                if part.covers(candidate):
                    point = candidate; break
            if point is None:
                point = part.representative_point()
            yaw = rng.uniform(0, math.tau)
            ux, uy = math.cos(yaw), math.sin(yaw)
            vx, vy = -uy, ux
            length, breadth = rng.uniform(.20, .32), rng.uniform(.105, .185)
            x, y = point.x, point.y
            diamond = Polygon([(x-ux*length, y-uy*length), (x-vx*breadth, y-vy*breadth),
                               (x+ux*length, y+uy*length), (x+vx*breadth, y+vy*breadth)])
            clipped = diamond.intersection(shape)
            material = rng.choices((0, 1, 2), (.13, .57, .30))[0]
            for tri in _triangles(clipped):
                points = []
                for px, py in tri:
                    fold = .025+.040*min(1, abs((px-x)*vx+(py-y)*vy)/breadth)
                    points.append((px, py, height(px, py)+fold))
                face(points, material)
            leaf_count += 1
    assert all(shape.buffer(1e-7).covers(Point(p[:2])) for p in vertices)
    assert min(p[2] for p in vertices) == round(bottom_z, 8)
    assert max(p[2] for p in vertices) <= cap_z+high+.066
    return vertices, faces, indices, {
        'cell_count': len(cells), 'display_folded_leaf_sample_count': leaf_count,
        'body_top_triangle_count': cap_face_count, 'body_closed_edge_count': len(body_edges),
        'contact_wall_quad_count': len(top_edge_pairs), 'sealed_body_face_count': body_face_count,
        'folded_leaf_triangle_count': len(faces)-body_face_count,
        'body_is_closed': True,
    }


def add_landscape_beds(context):
    import bpy
    from shapely.geometry import Point, Polygon
    from shapely.ops import unary_union
    scene, native = context['s'], context['n']
    digest, snapshot = context['lake_digest'], context['spatial_mesh_snapshot']
    graph_state = context['facade_graph_state']
    assert not any(obj.name.startswith('Landscape low foliage ') for obj in scene.objects)
    bpy.context.view_layer.update()
    existing_objects = list(scene.objects)
    shrubs = [obj for obj in existing_objects if obj.name.startswith('Garden source oval shrub canopy ')]
    assert len(shrubs) == 8
    pairs = context['pairs']
    assert len(pairs) == 1971
    tree_xy_before = sorted([[round(float(row[1][0]), 6), round(float(row[1][1]), 6)] for row in pairs])
    shrub_xy_before = sorted([list(obj['source_position_xy']) for obj in shrubs])
    mesh_before = snapshot(obj for obj in existing_objects if obj.type == 'MESH')
    object_before = {obj.name: [obj.type, obj.data.name if obj.data else None,
        [list(row) for row in obj.matrix_world], obj.hide_render, obj.hide_viewport,
        obj.hide_get(), list(obj.color)] for obj in existing_objects}
    material_before = {mat.name: digest(graph_state(mat.node_tree))
                       for mat in bpy.data.materials if mat.use_nodes}
    material_count_before, mesh_count_before = len(bpy.data.materials), len(bpy.data.meshes)
    image_count_before = len(bpy.data.images)
    world_before = digest(graph_state(scene.world.node_tree))
    roofs_before = digest(context['faces'])
    source_caps = {name: _flat_cap(scene.objects[name]) for _, name, *_ in TARGETS}
    island_plaza, _ = _flat_cap(scene.objects['Garden source circular plaza'])
    east_soil, east_soil_z = _flat_cap(scene.objects['Garden satellite visible east row plot'])
    source_union = unary_union([shape for shape, z in source_caps.values()])
    # The retained flower water footprint includes its already constructed dry
    # island. Remove exactly that original dry plaza, not an arbitrary buffer.
    small_pond, _ = _flat_cap(scene.objects['Garden satellite visible small eastern pond'])
    wet_exclusion = context['water'].difference(island_plaza).union(small_pond)
    paved_exclusion = context['paving'].union(context['detail_union']).union(island_plaza).difference(source_union)
    exclusions = {'roof': context['roofs'], 'water': wet_exclusion,
                  'plaza': paved_exclusion, 'road': context['asphalt'], 'sports': context['sports']}
    exclusion_union = unary_union([shape.buffer(.04) for shape in exclusions.values()])
    materials = [native['mat']('Landscape low foliage pigment '+str(i), rgb, .90)
                 for i, rgb in enumerate(PALETTE)]
    material_values = []
    for mat, rgb in zip(materials, PALETTE):
        bs = mat.node_tree.nodes.get('Principled BSDF')
        bs.inputs['Metallic'].default_value = 0
        bs.inputs['Alpha'].default_value = 1
        bs.inputs['Emission Strength'].default_value = 0
        actual = {'material': mat.name, 'base_colour': list(bs.inputs['Base Color'].default_value),
                  'roughness': float(bs.inputs['Roughness'].default_value),
                  'metallic': float(bs.inputs['Metallic'].default_value),
                  'alpha': float(bs.inputs['Alpha'].default_value),
                  'emission_strength': float(bs.inputs['Emission Strength'].default_value)}
        assert all(abs(a-b) < 1e-6 for a, b in zip(actual['base_colour'], (*rgb, 1)))
        assert abs(actual['roughness']-.90) < 1e-6 and actual['alpha'] == 1
        assert actual['metallic'] == actual['emission_strength'] == 0
        assert not any(link.to_socket.name in ('Alpha', 'Displacement') for link in mat.node_tree.links)
        material_values.append(actual)

    entries, new_objects, total_triangles = [], [], 0
    for key, source_name, nominal_z, inset, cell_size, low, high in TARGETS:
        source_shape, cap_z = source_caps[source_name]
        assert abs(cap_z-nominal_z) < 1e-5, (source_name, cap_z)
        if key == 'garden-island-centre':
            assert source_shape.difference(island_plaza.buffer(XY_TOL_M)).area < 1e-7
        if key == 'garden-east-courses':
            assert source_shape.difference(east_soil.buffer(XY_TOL_M)).area < 1e-7
            assert abs(east_soil_z-.205) < 1e-5
        if key.startswith('E formal garden'):
            assert source_shape.difference(context['planted_shapes'][key].buffer(XY_TOL_M)).area < 1e-7
        supported = source_shape.buffer(-inset).difference(exclusion_union)
        supported = unary_union([part for part in _polygons(supported) if part.area > .04])
        assert supported.area > source_shape.area*.45, (key, 'Excessively excluded source bed')
        bottom_z = (east_soil_z-.002) if key == 'garden-east-courses' else cap_z-.004
        vertices, faces, indices, geometry = _volume(supported, cap_z, bottom_z, key, cell_size, low, high)
        name = 'Landscape low foliage '+key
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(vertices, [], faces); mesh.update()
        for mat in materials:
            mesh.materials.append(mat)
        for polygon, index in zip(mesh.polygons, indices):
            polygon.material_index = index
            polygon.use_smooth = False
        obj = bpy.data.objects.new(name, mesh); scene.collection.objects.link(obj)
        obj['source_key'] = key; obj['source_object'] = source_name
        obj['detail_basis'] = 'Retained planting cap; continuous low foliage and height estimated'
        new_objects.append(obj)
        # Check the stored float32 geometry, including leaf faces, not just the
        # double-precision support outline used to construct it.
        actual_vertices = [list(vertex.co) for vertex in mesh.vertices]
        actual_faces = [[list(face.vertices), face.material_index, face.use_smooth] for face in mesh.polygons]
        actual_xy = unary_union([Polygon([(actual_vertices[i][0], actual_vertices[i][1]) for i in face.vertices])
            for face in mesh.polygons if len({tuple(actual_vertices[i][:2]) for i in face.vertices}) >= 3])
        outside_source = actual_xy.difference(source_shape.buffer(XY_TOL_M)).area
        outside_support = actual_xy.difference(supported.buffer(XY_TOL_M)).area
        overlaps = {(('plaza_outside_existing_planting_caps' if label == 'plaza' else label)+'_overlap_m2'):
                    actual_xy.intersection(shape).area for label, shape in exclusions.items()}
        assert outside_source < 1e-7 and outside_support < 1e-7
        assert max(overlaps.values()) < 1e-7, (key, overlaps)
        bounds = [[min(p[i] for p in actual_vertices) for i in range(3)],
                  [max(p[i] for p in actual_vertices) for i in range(3)]]
        assert abs(bounds[0][2]-bottom_z) < 1e-6
        assert bounds[1][2] <= cap_z+high+.066+1e-6
        triangles = sum(len(face.vertices)-2 for face in mesh.polygons)
        total_triangles += triangles
        actual_body_edges = Counter(tuple(sorted((a, b))) for face in mesh.polygons[:geometry['sealed_body_face_count']]
            for a, b in zip(tuple(face.vertices), tuple(face.vertices)[1:]+tuple(face.vertices)[:1]))
        assert all(count == 2 for count in actual_body_edges.values())
        entries.append({'source_key': key, 'source_object': source_name, 'object': name,
            'source_cap_xy_sha256': digest(_shape_values(source_shape)),
            'source_mesh_geometry_uv_transform_sha256': digest(snapshot([scene.objects[source_name]])),
            'source_cap_area_m2': source_shape.area, 'source_cap_z_m': cap_z,
            'support_area_m2': supported.area, 'support_xy_sha256': digest(_shape_values(supported)),
            'support_inset_m_estimate': inset, 'world_bounds_m': bounds,
            'ground_contact_bottom_z_m': bounds[0][2], 'maximum_top_above_source_cap_m_estimate': bounds[1][2]-cap_z,
            'geometry_sha256': digest([actual_vertices, actual_faces, [mat.name for mat in mesh.materials]]),
            'face_count': len(mesh.polygons), 'polygon_triangle_count': triangles,
            'outside_source_cap_m2_at_float32_tolerance': outside_source,
            'outside_supported_envelope_m2_at_float32_tolerance': outside_support,
            **overlaps, **geometry})

    bpy.context.view_layer.update()
    assert len(new_objects) == 4 and len(scene.objects) == len(existing_objects)+4
    assert len(bpy.data.meshes) == mesh_count_before+4 and len(bpy.data.materials) == material_count_before+3
    assert len(bpy.data.images) == image_count_before
    assert mesh_before == snapshot(scene.objects[name] for name in mesh_before)
    assert object_before == {obj.name: [obj.type, obj.data.name if obj.data else None,
        [list(row) for row in obj.matrix_world], obj.hide_render, obj.hide_viewport,
        obj.hide_get(), list(obj.color)] for obj in existing_objects}
    assert material_before == {name: digest(graph_state(bpy.data.materials[name].node_tree)) for name in material_before}
    assert world_before == digest(graph_state(scene.world.node_tree)) and roofs_before == digest(context['faces'])
    assert tree_xy_before == sorted([[round(float(row[1][0]), 6), round(float(row[1][1]), 6)] for row in context['pairs']])
    assert shrub_xy_before == sorted([list(obj['source_position_xy']) for obj in shrubs])
    assert total_triangles <= 120000
    root = Path(__file__).resolve().parents[1]
    inputs = ('model/campus/layout.json', 'scripts/garden_detail.py',
              'model/campus/references/satellite-export.json', 'model/campus/references/north-extension.json')
    return {'source_keys': [entry['source_key'] for entry in entries], 'bed_count': 4,
        'new_object_count': 4, 'new_mesh_count': 4, 'new_material_count': 3, 'new_image_count': 0,
        'new_tree_centre_count': 0, 'preserved_source_tree_centre_count': len(pairs),
        'preserved_source_tree_xy_sha256': digest(tree_xy_before),
        'preserved_oval_shrub_count': len(shrubs), 'preserved_oval_shrub_xy_sha256': digest(shrub_xy_before),
        'source_inputs_sha256': {path: hashlib.sha256((root/path).read_bytes()).hexdigest() for path in inputs},
        'beds': entries, 'total_polygon_triangle_count': total_triangles,
        'triangle_count_method': 'Sum(len(polygon.vertices)-2) for four meshes with no modifiers; not a dependency-graph evaluation',
        'new_material_values': material_values,
        'new_material_graph_sha256': {mat.name: digest(graph_state(mat.node_tree)) for mat in materials},
        'water_exclusion_basis': 'Retained water union minus actual pre-existing dry circular plaza, plus actual small eastern pond',
        'plaza_exclusion_basis': 'Existing paving/detail/dry-island plaza outside the four already layered planting caps; not a no-overlap claim for their underlying original paving',
        'dry_island_plaza_xy_sha256': digest(_shape_values(island_plaza)),
        'all_existing_geometry_uv_transforms_visibility_and_material_slots_preserved': True,
        'all_existing_material_graphs_world_and_roof_faces_preserved': True,
        'per_construction_preservation': {'existing_mesh_count': len(mesh_before),
            'existing_mesh_state_sha256': digest(mesh_before), 'existing_object_state_sha256': digest(object_before),
            'existing_material_graphs_sha256': digest(material_before),
            'world_graph_sha256': world_before, 'roof_faces_sha256': roofs_before},
        'cross_construction_equality_exclude': ['per_construction_preservation'],
        'limitations': 'Continuous foliage is estimated within four retained planting caps. Folded-face samples are not plant locations, measured vegetation, species or inventory. No canopy, oval shrub or original scene object is replaced. Stored XY tests allow 0.2mm float32 numeric tolerance; this is not survey accuracy.'}
