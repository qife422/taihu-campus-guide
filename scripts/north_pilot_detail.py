"""Source-bound finish for the N31–N35 inspection crop.

All placement is constrained to existing traced roof, forecourt or planted
geometry. The satellite supplies pigmentation; roofs and ground remain 3-D.
"""
from pathlib import Path
import math
import hashlib

import bpy
from mathutils import Vector
from shapely.geometry import Polygon, LineString, Point


def add_pilot_detail(c):
    root = Path(__file__).resolve().parents[1]
    scene, anchor = c['s'], c['anchor']
    gp, shape, surface, Mesh, mat = (c[k] for k in ('gp', 'shape', 'surface', 'Mesh', 'mat'))
    paved, planting, allroof, roads = (c[k] for k in ('paved', 'planting', 'allroof', 'roads'))
    photo = bpy.data.images.load(str(root / 'model/campus/references/satellite.jpg'), check_existing=True)
    low, high = gp((0, 1920)), gp((1152, 0))

    def source_finish(base, name, influence):
        finish = base.copy()
        finish.name = name
        nodes, links = finish.node_tree.nodes, finish.node_tree.links
        shader = nodes.get('Principled BSDF')
        old = shader.inputs['Base Color'].links[0].from_socket
        coord = nodes.new('ShaderNodeTexCoord')
        coord.object = anchor
        uv = nodes.new('ShaderNodeVectorMath')
        uv.operation = 'MULTIPLY_ADD'
        uv.inputs[1].default_value = (1 / (high.x-low.x), 1 / (high.y-low.y), 1)
        uv.inputs[2].default_value = (-low.x/(high.x-low.x), -low.y/(high.y-low.y), 0)
        raster = nodes.new('ShaderNodeTexImage')
        raster.image = photo
        raster.interpolation = 'Cubic'
        mixed = nodes.new('ShaderNodeMixRGB')
        mixed.inputs[0].default_value = influence
        links.new(coord.outputs['Object'], uv.inputs[0])
        links.new(uv.outputs[0], raster.inputs['Vector'])
        links.new(old, mixed.inputs[1])
        links.new(raster.outputs['Color'], mixed.inputs[2])
        links.new(mixed.outputs[0], shader.inputs['Base Color'])
        return finish

    # The model already has correctly traced roof faces. The fixed aerial
    # supplies the observed discoloration and rooftop silhouette within them.
    roof = c['roof']
    roof_finish = source_finish(roof, 'Pilot warm mineral roof courses', .32)
    roof_nodes = roof_finish.node_tree.nodes
    roof_bricks = next(node for node in roof_nodes if node.type == 'TEX_BRICK')
    roof_bricks.inputs['Brick Width'].default_value = 1.48
    roof_bricks.inputs['Row Height'].default_value = 2.25
    roof_bricks.inputs['Mortar Size'].default_value = .034
    roof_bricks.inputs['Color1'].default_value = (.54, .535, .49, 1)
    roof_bricks.inputs['Color2'].default_value = (.66, .63, .57, 1)
    roof_bricks.inputs['Mortar'].default_value = (.34, .35, .33, 1)
    roof_uv = roof_nodes.new('ShaderNodeUVMap')
    roof_uv.uv_map = 'Pilot roof finish frame'
    roof_finish.node_tree.links.new(roof_uv.outputs['UV'], roof_bricks.inputs['Vector'])
    roof_replacements = []
    roof_frame_checks = []
    for name in ('Study N31 stepped dining', 'Study red academic photo facade'):
        ob = scene.objects[name]
        ids = ['N31'] if name == 'Study N31 stepped dining' else ['N34', 'N35']
        frames = []
        before = [tuple(v.co) for v in ob.data.vertices]
        for ident in ids:
            row = next(r for r in c['rows'] if r['id'] == ident)
            traced = [gp(q) for q in row['outline']]
            axis = max((b-a for a,b in zip(traced,traced[1:]+traced[:1])), key=lambda v:v.length).normalized()
            frames.append((shape(row['outline']), traced[0], axis, Vector((-axis.y, axis.x, 0))))
        uv = ob.data.uv_layers.new(name='Pilot roof finish frame')
        for face in ob.data.polygons:
            centre = ob.matrix_world @ face.center
            _, origin, axis, cross = min(frames, key=lambda f:f[0].distance(Point(centre.x, centre.y)))
            for li in face.loop_indices:
                delta = ob.matrix_world @ ob.data.vertices[ob.data.loops[li].vertex_index].co - origin
                uv.data[li].uv = (delta.dot(axis), delta.dot(cross))
        unchanged = before == [tuple(v.co) for v in ob.data.vertices]
        assert unchanged
        roof_frame_checks.append({'source_ids': ids, 'uv_layer': uv.name, 'mesh_positions_preserved': unchanged,
                                  'method': 'Metre-scaled roof courses aligned to the longest fixed traced building edge'})
        for slot in ob.material_slots:
            if slot.material == roof:
                slot.material = roof_finish
                roof_replacements.append(name)
    assert len(roof_replacements) == 2

    # The satellite shows a small grid over N31 and a green glazed roof on
    # the eastern wing of N34. Add their visible mullions at the traced spots.
    frame = mat('Pilot subdued roof frame', (.38, .43, .40), .7)
    glass = mat('Pilot pale rooflight glass', (.28, .43, .40), .31)
    border = mat('Pilot warm rooflight curb', (.68, .66, .57), .73)
    bm = Mesh('Pilot photo traced rooftop lights')
    def glazed_grid(rect, z, nx, ny):
        g = shape(rect)
        a, b, d, e = [gp(q, z) for q in rect]
        # Keep all geometry inside the parent traced building, including its
        # raised roof; this detail does not alter hotspot footprints.
        bm.solid(g, z, .10, border)
        inner = g.buffer(-.18)
        bm.plane(inner, z+.115, glass)
        for i in range(1, nx):
            u = i / nx
            p = a+(b-a)*u
            q = e+(d-e)*u
            bm.plane(LineString([(p.x,p.y),(q.x,q.y)]).buffer(.045).intersection(inner), z+.12, frame)
        for i in range(1, ny):
            u = i / ny
            p = a+(e-a)*u
            q = b+(d-b)*u
            bm.plane(LineString([(p.x,p.y),(q.x,q.y)]).buffer(.045).intersection(inner), z+.12, frame)
        return g
    # N31 skylight is represented in the base model. The N34 rooflight is
    # visible in the fixed source at x=710–718, y=492–510.
    g34 = shape(next(r for r in c['rows'] if r['id']=='N34')['outline'])
    visible = shape([(710,493),(717,494),(717,509),(710,508)])
    assert visible.difference(g34).area < 1e-8
    glazed_grid([(710,493),(717,494),(717,509),(710,508)], 20.77, 5, 11)
    # Low service hoods follow the visible rooftop clusters. Their small
    # height deliberately avoids inventing an additional building storey.
    service = mat('Pilot roof service light metal', (.49, .51, .48), .68)
    service_dark = mat('Pilot roof service recessed metal', (.23, .29, .28), .74)
    rooftop_clusters = [
        ([(682,474),(689,474),(689,478),(682,478)], 18.58, .42),
        ([(682,521),(690,522),(690,527),(682,526)], 18.58, .22),
    ]
    for pixels, z, height in rooftop_clusters:
        g = shape(pixels).intersection(g34.buffer(-.18))
        assert not g.is_empty
        bm.solid(g, z, height, service)
        rim = g.difference(g.buffer(-.22))
        bm.plane(rim, z+height+.012, border)
        bm.plane(g.buffer(-.28), z+height+.014, service_dark)
    bm.finish()

    # The court is a substantial pale paved surface in both source images.
    # World-scale stone courses and restrained photographic discoloration
    # replace the flat mass without inventing extra paths or landscaping.
    paving = c['pave']
    court_finish = source_finish(paving, 'Pilot aerial court paving', .30)
    stone_bricks = next(node for node in court_finish.node_tree.nodes if node.type == 'TEX_BRICK')
    stone_bricks.inputs['Brick Width'].default_value = 1.20
    stone_bricks.inputs['Row Height'].default_value = .78
    stone_bricks.inputs['Color1'].default_value = (.68, .64, .56, 1)
    stone_bricks.inputs['Color2'].default_value = (.51, .53, .48, 1)
    stone_bricks.inputs['Mortar'].default_value = (.34, .35, .32, 1)
    for ob in scene.objects:
        if ob.name in ('Study continuous plazas', 'Study building foot margins'):
            for slot in ob.material_slots:
                if slot.material == paving:
                    slot.material = court_finish
    course = mat('Pilot stone course joints', (.36, .365, .33), .96)
    x0, y0, x1, y1 = paved.bounds
    focus = shape([(636,389),(749,389),(749,533),(636,533)])
    detailed = paved.intersection(focus).difference(roads.buffer(.08))
    batches = Mesh('Pilot source court stone courses')
    for x in range(math.floor(x0/1.25), math.ceil(x1/1.25)+1):
        line = LineString([(x*1.25,y0),(x*1.25,y1)]).buffer(.045)
        batches.plane(line.intersection(detailed), .349, course)
    for y in range(math.floor(y0/1.25), math.ceil(y1/1.25)+1):
        line = LineString([(x0,y*1.25),(x1,y*1.25)]).buffer(.045)
        batches.plane(line.intersection(detailed), .349, course)
    batches.finish()

    # Different finish on the narrow ground lip of the photo-visible red
    # academic block. All added faces are inside the existing paved apron.
    academic = g34.union(shape(next(r for r in c['rows'] if r['id']=='N35')['outline']))
    academic_margin = academic.buffer(1.55, join_style='mitre').difference(academic.buffer(.18)).intersection(detailed)
    edge = mat('Pilot academic entry light stone', (.72, .69, .59), .8)
    surface('Pilot academic entry mineral edge', academic_margin, .355, edge)

    # The inspection image is intentionally closer than the whole block.
    # Give existing grass, leaf and red-masonry materials their photo-observed
    # colour separation while keeping every tree and building in place.
    grass_ramp = next(node for node in c['lawn'].node_tree.nodes if node.type == 'VALTORGB')
    grass_ramp.color_ramp.elements[0].color = (.115, .295, .045, 1)
    grass_ramp.color_ramp.elements[1].color = (.245, .440, .105, 1)
    for i, leaf in enumerate(c['leaves']):
        shader = leaf.node_tree.nodes.get('Principled BSDF')
        rgb = shader.inputs['Base Color'].default_value
        shader.inputs['Base Color'].default_value = (min(.40, rgb[0]*1.16), min(.47, rgb[1]*1.26), min(.21, rgb[2]*1.23), 1)
    brick_ramp = next(node for node in c['brick'].node_tree.nodes if node.type == 'VALTORGB')
    brick_ramp.color_ramp.elements[0].color = (.38, .105, .040, 1)
    brick_ramp.color_ramp.elements[1].color = (.54, .18, .075, 1)

    # The fixed image shows a pale mineral court inside N34, not the grass
    # rectangle recorded in the old landscape layout. Correct this local
    # candidate without changing that input or the published campus scene.
    court_pixels = [(665,486),(701,489),(700,513),(665,509)]
    mineral_court = shape(court_pixels).difference(allroof.buffer(.05)).difference(roads)
    assert not mineral_court.is_empty
    surface('Pilot N34 photo-visible mineral court', mineral_court, .370, court_finish)
    removed_hedges = 0
    for ob in scene.objects:
        if ob.name.startswith('Study courtyard hedge') and mineral_court.buffer(.7).covers(Point(ob.location.x, ob.location.y)):
            ob.hide_render = True
            removed_hedges += 1

    # The reference's leafy reading comes from textured, irregular crowns.
    # Apply one transparent canopy cutout only to fixed satellite tree centres;
    # the procedural branches below still supply depth and cast shadows.
    sprite_path = root / 'output/garden-tree-canopy.png'
    sprite_image = bpy.data.images.load(str(sprite_path), check_existing=True)
    from garden_detail import canopy_material,canopy_mesh
    sprite=canopy_material('Pilot detailed canopy image',sprite_image)
    plane=canopy_mesh('Pilot canopy image plane',sprite,'Canopy UV')
    source_trees = sorted((ob for ob in scene.objects if ob.name.startswith('Study source tree ') and not ob.hide_render),key=lambda ob:tuple(ob.matrix_world.translation)+tuple(ob.scale))
    for i, ob in enumerate(source_trees):
        crown = bpy.data.objects.new('Pilot source-tree canopy '+str(i), plane)
        scene.collection.objects.link(crown)
        radius = max(ob.scale.x, ob.scale.y)
        variation = .86 + .24 * ((i*7)%13) / 12
        crown.location = (ob.location.x, ob.location.y, ob.location.z + ob.scale.z*.72)
        crown['source_tree']=ob.name;crown['source_position_xy']=[ob.location.x,ob.location.y]
        crown.scale = (radius*2.35*variation, radius*2.15*variation, min(2.8,max(.65,radius*.65)))
        crown.rotation_euler.z = (i*2.399963229728653) % math.tau

    # Photo pigment on terrain provides the uneven greens and old-paving
    # colour missing from the otherwise regular model. It cannot invent a
    # building, road or tree, because it changes colour on existing faces.
    for name, material, influence in [
        ('Study landscape base', c['lawn'], .24),
        ('Study source woodland ground', c['woodground'], .38),
        ('Study planted bed ground', c['lawn'], .33),
        ('Study apartment courtyard finish', c['courtfinish'], .34),
        ('Study source grey apron', c['hardgrey'], .38),
    ]:
        finish = source_finish(material, 'Pilot aerial finish '+name, influence)
        matched = [ob for ob in scene.objects if ob.name == name or ob.name.startswith(name+'.')]
        assert matched, name
        for obj in matched:
            for slot in obj.material_slots:
                if slot.material == material:
                    slot.material = finish

    # The original dark roofs have their correct silhouettes but their
    # repeated procedural tiles erase the age and colour breaks seen above.
    # Source-copied roofs already carry one aerial colour layer. Keep that
    # layer single; a second projection hides the procedural tile detail.
    roof_materials = []
    for material in tuple(bpy.data.materials):
        if material.name.startswith('Atlas architecture dark slate tiles') and ' source ' not in material.name:
            finish = source_finish(material, 'Pilot photo-varied dark slate', .26)
            for ob in scene.objects:
                for slot in ob.material_slots:
                    if slot.material == material:
                        slot.material = finish
            roof_materials.append(material.name)

    # Cartographic street captions reproduce the reference's readable map
    # layer. These strings are the existing layout's descriptive path names,
    # not asserted official campus road names.
    road_names = {row[0] for row in c['D']['roads']}
    captions = [
        ('北区西侧南北路', (632,422), (632,480)),
        ('公寓横向路', (515,512), (620,526)),
        ('北区南北联系路', (748,463), (745,521)),
    ]
    assert all(name in road_names for name, _, _ in captions)
    font_path = Path('/System/Library/Fonts/STHeiti Medium.ttc')
    font = bpy.data.fonts.load(str(font_path))
    yellow = mat('Pilot path caption yellow', (.91,.75,.08), .8)
    dark = mat('Pilot path caption dark edge', (.055,.065,.045), .9)
    label_ground_checks = []
    for name, a, b in captions:
        start, end = gp(a), gp(b)
        centre = (start+end)*.5
        label_ground_checks.append(roads.buffer(.15).covers(Point(centre.x, centre.y)))
        direction = end-start
        angle = math.atan2(direction.y, direction.x)
        rotation = scene.camera.rotation_euler.to_matrix()
        screen_x = direction.dot(rotation.col[0])
        screen_y = -direction.dot(rotation.col[1])
        if (abs(screen_x) >= abs(screen_y) and screen_x < 0) or (abs(screen_x) < abs(screen_y) and screen_y < 0):
            angle += math.pi
        for back in (True, False):
            curve = bpy.data.curves.new('Pilot path caption '+name, 'FONT')
            curve.body = name
            curve.font = font
            curve.size = 5.2 if back else 5.0
            curve.align_x = 'CENTER'
            curve.align_y = 'CENTER'
            curve.extrude = .008 if back else 0
            curve.materials.append(dark if back else yellow)
            ob = bpy.data.objects.new('Pilot descriptive road label '+name+(' edge' if back else ''), curve)
            scene.collection.objects.link(ob)
            ob.location = (centre.x, centre.y, .425 if back else .44)
            ob.rotation_euler.z = angle
    assert all(label_ground_checks), label_ground_checks

    checks = {
        'roof_objects_photo_finished': roof_replacements,
        'roof_course_frames': roof_frame_checks,
        'rooflight_outside_source_roof_m2': visible.difference(g34).area,
        'court_courses_outside_traced_paving_m2': detailed.difference(paved).area,
        'academic_margin_outside_paving_m2': academic_margin.difference(paved).area,
        'source_rooflight_pixels': [(710,493),(717,494),(717,509),(710,508)],
        'source_rooftop_clusters_pixels': [p for p,_,_ in rooftop_clusters],
        'source_material': 'model/campus/references/satellite.jpg',
        'tree_centres_preserved': True,
        'source_tree_canopy_count': len(source_trees),
        'corrected_N34_court_pixels': court_pixels,
        'corrected_N34_court_outside_old_planting_m2': mineral_court.difference(planting).area,
        'removed_unsupported_courtyard_hedges': removed_hedges,
        'source_tinted_dark_roof_materials': roof_materials,
        'descriptive_road_labels': [name for name, _, _ in captions],
        'descriptive_label_centres_on_source_roads': label_ground_checks,
        'label_font_sha256': hashlib.sha256(font_path.read_bytes()).hexdigest(),
    }
    assert max(checks[k] for k in checks if k.endswith('_m2')) < 1e-8
    return checks
