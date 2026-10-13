"""Native source-traced flower-garden visual pilot.

Blender --background -t 4 --python scripts/garden_pilot.py [-- --final]
The candidate never replaces the published campus atlas.
"""
from pathlib import Path
import hashlib
import io
import json
import math
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CACHE = Path('/tmp/taihu-full')
OUT = ROOT / 'output'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cache_bytes():
    return sum(p.stat().st_size for p in CACHE.rglob('*') if p.is_file())


if '--export' in sys.argv:
    from PIL import Image
    meta = json.loads((CACHE/'garden.json').read_text())
    assert meta['image_size'] == [2400, 1800]
    assert all(sha(ROOT/p) == h for p, h in meta['sources'].items())
    image = Image.open(CACHE/'garden.png').convert('RGB')
    assert list(image.size) == meta['image_size']
    encoded = io.BytesIO()
    image.save(encoded, format='WEBP', quality=92, method=6)
    payload = encoded.getvalue()
    assert len(payload) < 8*1024**2
    meta['image_sha256'] = hashlib.sha256(payload).hexdigest()
    meta['image_bytes'] = len(payload)
    meta['visual_review'] = {'status': 'pending'}
    assert cache_bytes() < 192*1024**2
    OUT.mkdir(exist_ok=True)
    (OUT/'garden-pilot.webp').write_bytes(payload)
    (OUT/'garden-pilot.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2)+'\n')
    print('GARDEN EXPORTED', len(payload), meta['image_sha256'], flush=True)
    sys.exit(0)

import bpy
from mathutils import Vector
sys.dont_write_bytecode = True
sys.path[:0] = ['/tmp/taihu-gis-deps', str(ROOT/'scripts')]
from shapely.geometry import Point, LineString, Polygon, box
from shapely.ops import unary_union

assert cache_bytes() < 192*1024**2
builder = ROOT/'scripts/campus_expansion.py'
source = builder.read_text()
marker = "baseline=json.loads((OUT/'campus-atlas.json').read_text())"
assert source.count(marker) == 1
construction = source.split(marker)[0]
state = {'__name__': '__garden_construction__', '__file__': str(builder)}
exec(compile(construction, str(builder), 'exec'), state)
scene = state['s']
n = state['n']
gp = state['gp']
surface = n['surface']
material = n['mat']
texture = n['texture']
layout = state['D']
water = state['water']
roofs = state['roofs']
sports = state['sports']
road = state['asphalt']
paving = state['paving']
ground = state['ground']

# The broad original paving union is a coarse classification, which creates
# detached pale shards across this garden. Only this pilot hides it; the fixed
# road geometry and individually traced garden walks stay visible.
hidden_coarse=[]
for name in ('Expansion source paving','Expansion paving courses'):
    obj=scene.objects.get(name)
    if obj:
        obj.hide_render=True
        hidden_coarse.append(name)
for mm in bpy.data.materials:
    if ' source satellite' not in mm.name:continue
    for node in mm.node_tree.nodes:
        if node.type=='MIX_RGB' and any(link.from_node.type=='TEX_IMAGE' for link in node.inputs[2].links):
            node.inputs[0].default_value=.08


def pixel_polygon(points):
    return Polygon([tuple(gp(p))[:2] for p in points])


def pixel_line(points):
    return LineString([tuple(gp(p))[:2] for p in points])


def smooth_pixel_line(points):
    """Densify the source's sparse path controls without moving its junctions."""
    closed=len(points)>2 and points[0]==points[-1]
    source=points[:-1] if closed else points
    drawn=[]
    count=len(source)
    for i in range(count if closed else count-1):
        a=source[(i-1)%count] if closed or i>0 else source[i]
        b=source[i]
        c=source[(i+1)%count]
        d=source[(i+2)%count] if closed or i+2<count else c
        m0=((c[0]-a[0])*.42,(c[1]-a[1])*.42)
        m1=((d[0]-b[0])*.42,(d[1]-b[1])*.42)
        for k in range(8):
            t=k/8
            h00=2*t**3-3*t*t+1
            h10=t**3-2*t*t+t
            h01=-2*t**3+3*t*t
            h11=t**3-t*t
            drawn.append((h00*b[0]+h10*m0[0]+h01*c[0]+h11*m1[0],
                          h00*b[1]+h10*m0[1]+h01*c[1]+h11*m1[1]))
    drawn.append(source[0] if closed else source[-1])
    return pixel_line(drawn)


def ring(center, outer, inner):
    return center.buffer(outer, resolution=128).difference(center.buffer(inner, resolution=128))


# The source shows a pale circular island inside the irregular dark water
# outline. The old layout classified the island as water; this local study
# restores the visually unambiguous hole without modifying that source file.
center_px = (351, 1559)
center = gp(center_px)
point = Point(center.x, center.y)
pixel_m = (gp((352,1559))-center).length
court_radius = 18.0*pixel_m
source_water = next(row for row in layout['surfaces'] if row['id']=='flower-round-water')
water_feature = state['shape'](source_water)
garden_roi = pixel_polygon([(248,1375),(535,1375),(535,1662),(248,1662)])
plaza = point.buffer(court_radius, resolution=128)
detail_mask = ground.intersection(garden_roi).difference(roofs.buffer(.20)).difference(water.buffer(.15)).difference(sports.buffer(.20))
assert plaza.difference(water_feature).area < .01
assert plaza.intersection(roofs).area < .01

# In the fixed source, the diagonal Flower Garden road is pale mineral paving,
# while Meicha First Road along the south edge is darker asphalt. Their line
# controls and widths are already recorded in layout.json; finish only their
# existing road/paving footprint rather than borrowing road geometry from the
# different-campus visual reference.
road_rows={row[0]:row for row in layout['roads']}
light_row=road_rows['花卉园东南路']
light_route=pixel_line(light_row[1])
light_footprint=light_route.buffer(light_row[2]*1.2,cap_style='round',join_style='round').intersection(road).difference(roofs.buffer(.20)).difference(water)
assert light_footprint.area>30
light_road=material('Garden source pale mineral road',(.59,.56,.48),.89)
texture(light_road,(.47,.46,.40),(.66,.63,.55),2.1,.012)
surface('Garden source light diagonal road',light_footprint,.402,light_road)
dark_row=road_rows['梅茶一路']
dark_route=pixel_line(dark_row[1])
dark_footprint=dark_route.buffer(dark_row[2]/2,cap_style='round',join_style='round').intersection(road).difference(roofs.buffer(.20)).difference(water)
assert dark_footprint.area>30
dark_road=material('Garden local charcoal road',(.13,.15,.14),.91)
texture(dark_road,(.045,.052,.048),(.11,.12,.11),11,.010)
surface('Garden darker Meicha First Road',dark_footprint,.403,dark_road)
road_paint=material('Garden subdued road line',(.63,.64,.58),.92)
markings=n['Mesh']('Garden Meicha road centre dashes')
for distance in range(3,int(dark_route.length)-3,10):
    a=dark_route.interpolate(distance)
    b=dark_route.interpolate(min(dark_route.length,distance+3.0))
    markings.plane(LineString([a,b]).buffer(.055,cap_style='flat').intersection(dark_footprint),.414,road_paint)
markings.finish()

# The eastern source photograph contains a narrow planted row plot and a
# separate irregular pond. Neither exists in the old surface classification.
# Bound both directly to visible satellite pixels and the established ground.
row_plot_source=pixel_polygon([(486,1476),(495,1476),(517,1475),(523,1484),(522,1497),(509,1501),(490,1500),(485,1493)])
row_plot=row_plot_source.intersection(ground).difference(roofs.buffer(.20)).difference(road.buffer(.30))
assert row_plot.area>20
plot_soil=material('Garden sourced east row plot earth',(.23,.19,.11),.94)
texture(plot_soil,(.15,.13,.075),(.31,.26,.14),.55,.012)
surface('Garden satellite visible east row plot',row_plot,.205,plot_soil)
plot_green=material('Garden low planted row',(.14,.22,.07),.96)
texture(plot_green,(.085,.16,.04),(.22,.30,.105),1.4,.009)
plot_rows=n['Mesh']('Garden source east planted courses')
for y in range(1479,1502,3):
    row=LineString([tuple(gp((484,y)))[:2],tuple(gp((525,y-1.8)))[:2]]).buffer(.32,cap_style='flat').intersection(row_plot)
    plot_rows.plane(row,.215,plot_green)
plot_rows.finish()
small_pond_source=pixel_polygon([(514,1513),(519,1514),(521,1517),(521,1522),(519,1527),(520,1532),(518,1537),(513,1540),(508,1538),(506,1535),(506,1531),(508,1526),(509,1521)])
small_pond=small_pond_source.intersection(ground).difference(road.buffer(.26)).difference(roofs.buffer(.2))
assert small_pond.area>10
small_water=material('Garden source eastern small pond',(.055,.13,.115),.35)
texture(small_water,(.025,.075,.07),(.095,.19,.165),.7,.006)
surface('Garden satellite visible small eastern pond',small_pond,.275,small_water)
small_pond_coping=small_pond.buffer(.23).difference(small_pond).intersection(ground).difference(road.buffer(.15))
small_coping=material('Garden eastern pond stone bank',(.49,.46,.36),.91)
surface('Garden source eastern pond bank',small_pond_coping,.281,small_coping)
detail_mask=detail_mask.difference(small_pond.buffer(.2))
# The existing scene batches all paired tree trunks into one object. Two of
# those positions were sampled from the dark pond before its water outline was
# traced. Rebuild the same trunks in memory, omitting only those pond points.
original_trunks=scene.objects.get('Expansion paired tree trunks')
assert original_trunks
original_trunks.hide_render=True
repaired_trunks=n['Mesh']('Garden paired trunks excluding eastern pond')
omitted_pond_trunks=0
for tree_name,tree_position,top_z in state['pairs']:
    p=Point(tree_position[0],tree_position[1])
    if small_pond.buffer(.3).covers(p):
        omitted_pond_trunks+=1
        continue
    tree_object=scene.objects.get(tree_name)
    if not tree_object or tree_object.hide_render:continue
    radius=min(.19,max(.085,min(tree_object.scale.x,tree_object.scale.y)*.032))
    n['branch'](repaired_trunks,Vector((p.x,p.y,.02)),Vector((p.x,p.y,top_z)),radius,radius*.62)
repaired_trunks.finish()

warm = material('Garden warm pale stone', (.64,.61,.52), .82)
texture(warm, (.51,.49,.42), (.70,.67,.58), 3.8, .015)
cool = material('Garden cool paving band', (.55,.565,.52), .86)
texture(cool, (.46,.49,.46), (.64,.65,.59), 4.5, .012)
edge = material('Garden sandstone raised edge', (.74,.70,.59), .79)
joint = material('Garden fine paving joints', (.32,.34,.30), .94)
soil = material('Garden circular planting bed', (.17,.18,.10), .92)
texture(soil, (.11,.14,.07), (.24,.26,.13), 2.6, .014)
surface('Garden source circular plaza', plaza, .485, warm)
surface('Garden circular outer band', ring(point, court_radius, court_radius-2.2*pixel_m), .494, cool)
surface('Garden circular inner band', ring(point, 12.6*pixel_m, 11.5*pixel_m), .497, cool)
surface('Garden center paving', point.buffer(7.2*pixel_m, resolution=96), .501, cool)
surface('Garden outer curb', ring(point, court_radius+.20, court_radius-.15), .506, edge)
for i in range(48):
    angle=i*math.tau/48
    ray=LineString([(center.x+math.cos(angle)*7.2*pixel_m,center.y+math.sin(angle)*7.2*pixel_m),
                    (center.x+math.cos(angle)*(court_radius-.35),center.y+math.sin(angle)*(court_radius-.35))])
    surface('Garden radial stone joint', ray.buffer(.045).intersection(plaza), .509, joint)
for radius in [7.2,11.5,12.6,16.9]:
    course=point.buffer(radius*pixel_m, resolution=128).boundary.buffer(.040).intersection(plaza)
    surface('Garden concentric stone joint', course, .510, joint)

routes=[]
route_deviations=[]
for row in layout['landscape']['footpaths']:
    if not row['id'].startswith('Flower garden'):continue
    route=smooth_pixel_line(row['points'])
    route_deviations.append(route.hausdorff_distance(pixel_line(row['points'])))
    if not route.intersects(garden_roi):continue
    width=row['width_m']
    path=route.buffer(width/2, join_style='round', cap_style='round').intersection(detail_mask).difference(plaza)
    if path.is_empty:continue
    routes.append((row['id'], path, route))
    surface('Garden traced winding path '+row['id'], path, .477, warm)
    outside=path.buffer(.17).difference(path).intersection(detail_mask).difference(plaza)
    surface('Garden winding path stone edge '+row['id'], outside, .482, edge)
    for distance in range(2, int(route.length), 2):
        position=route.interpolate(distance)
        forward=route.interpolate(min(route.length,distance+.20))
        backward=route.interpolate(max(0,distance-.20))
        tangent=Vector((forward.x-backward.x,forward.y-backward.y)).normalized()
        normal=Vector((-tangent.y,tangent.x))
        line=LineString([(position.x-normal.x*width,position.y-normal.y*width),
                         (position.x+normal.x*width,position.y+normal.y*width)])
        surface('Garden walk stone joint', line.buffer(.014).intersection(path), .486, joint)

paths=unary_union([g for _,g,_ in routes])
# Three source-traced walks meet at this control point. The individual clipped
# meshes leave a tiny triangular slit, so finish their shared junction as one
# continuous piece of stone at the exact surveyed connection.
junctions=[]
for junction_name,junction_pixel in [('north',(351,1436)),('south',(374,1606))]:
    junction_center=gp(junction_pixel)
    junction=Point(junction_center.x,junction_center.y).buffer(2.05,resolution=48).intersection(detail_mask)
    surface('Garden '+junction_name+' traced path junction',junction,.490,warm)
    surface('Garden '+junction_name+' junction edge',junction.buffer(.12).difference(junction).intersection(detail_mask),.492,edge)
    junctions.append(junction)
planting=point.buffer(5.8*pixel_m, resolution=96)
center_green=material('Garden island deep planted centre',(.10,.19,.045),.96)
texture(center_green,(.055,.14,.027),(.17,.26,.07),.80,.010)
surface('Garden source island center planting', planting, .516, center_green)
surface('Garden island center stone border', ring(point,6.1*pixel_m,5.7*pixel_m), .519, edge)
water_shore=water_feature.buffer(.27).difference(water_feature).intersection(detail_mask)
surface('Garden source water outer coping', water_shore, .487, edge)
deep_water_shape=water_feature.buffer(-.52).difference(plaza.buffer(.65))
deep_water=material('Garden deeper teal water',(.055,.17,.16),.36)
texture(deep_water,(.035,.12,.115),(.10,.235,.215),.75,.007)
surface('Garden sourced deeper water',deep_water_shape,-.060,deep_water)

# The old layout also tagged this source-visible striped forecourt as water.
# The retained polygon is accurate; only its visual classification changes in
# this candidate. The oval tree island is directly visible in the same image.
square_row=next(row for row in layout['surfaces'] if row['id']=='flower-square')
square=state['shape'](square_row)
for name in ('Expansion water flower-square','Expansion shallow edge flower-square'):
    obj=scene.objects.get(name)
    if obj:obj.hide_render=True
assert square.intersection(roofs).area < .01
square= square.difference(roofs.buffer(.20)).difference(road.buffer(.12))
surface('Garden source striped forecourt',square,.488,cool)
from shapely.affinity import scale as geometric_scale
island_center=gp((501,1570))
oval=geometric_scale(Point(island_center.x,island_center.y).buffer(1,resolution=64),9*pixel_m,10.8*pixel_m)
oval=oval.intersection(square.buffer(-.4))
oval_green=material('Garden forecourt dark planted oval',(.09,.14,.04),.96)
texture(oval_green,(.04,.08,.022),(.14,.21,.06),.90,.012)
surface('Garden source oval forecourt planting',oval,.506,oval_green)
surface('Garden oval low mineral edging',oval.buffer(.35).difference(oval),.512,edge)
oval_shrubs=[]
for i,pixel in enumerate([(497,1565),(501,1564),(505,1567),(497,1570),(502,1570),(506,1572),(499,1576),(503,1577)]):
    position=gp(pixel)
    if not oval.buffer(-.35).covers(Point(position.x,position.y)):continue
    shrub=bpy.data.objects.new('Garden photo-visible oval shrub '+str(i),n['protos'][(i*7+2)%12])
    scene.collection.objects.link(shrub)
    shrub.location=(position.x,position.y,1.05)
    radius=2.75 if i%3 else 2.15
    shrub.scale=(radius,radius*.88,.80)
    oval_shrubs.append(pixel)
line_batch=n['Mesh']('Garden source forecourt diagonal courses')
for i in range(-12,48):
    start=gp((455+i*1.55,1540))
    end=gp((475+i*1.55,1600))
    line=LineString([(start.x,start.y),(end.x,end.y)]).buffer(.065)
    line_batch.plane(line.intersection(square).difference(oval.buffer(.4)),.497,joint)
line_batch.finish()

# Garden lawns and tree centres are already sampled from the fixed satellite.
# This greener cartographic finish separates planting from pale stone, while
# keeping every source tree position and existing planting boundary.
lawn = n['lawn']
fresh=material('Garden varied meadow',(.19,.34,.07),.93)
texture(fresh,(.08,.235,.035),(.24,.43,.095),.30,.012)
# Convert the fixed image's light/dark field into a green vegetation palette.
# Keeping hue cartographic avoids pasting aerial brown pixels over 3-D grass.
nodes=fresh.node_tree.nodes
links=fresh.node_tree.links
shader=nodes.get('Principled BSDF')
base_color=shader.inputs['Base Color'].links[0].from_socket
low=gp((0,1920));high=gp((1152,0))
coord=nodes.new('ShaderNodeTexCoord');coord.object=n['anchor']
mapped=nodes.new('ShaderNodeVectorMath');mapped.operation='MULTIPLY_ADD'
mapped.inputs[1].default_value=(1/(high.x-low.x),1/(high.y-low.y),1)
mapped.inputs[2].default_value=(-low.x/(high.x-low.x),-low.y/(high.y-low.y),0)
photo=nodes.new('ShaderNodeTexImage')
photo.image=bpy.data.images.load(str(ROOT/'model/campus/references/satellite.jpg'),check_existing=True)
photo.interpolation='Cubic'
bw=nodes.new('ShaderNodeRGBToBW')
green=nodes.new('ShaderNodeValToRGB')
green.color_ramp.elements[0].position=.12
green.color_ramp.elements[0].color=(.038,.13,.020,1)
green.color_ramp.elements[1].position=.43
green.color_ramp.elements[1].color=(.31,.49,.095,1)
blend=nodes.new('ShaderNodeMixRGB');blend.inputs[0].default_value=.68
links.new(coord.outputs['Object'],mapped.inputs[0])
links.new(mapped.outputs[0],photo.inputs['Vector'])
links.new(photo.outputs['Color'],bw.inputs[0])
links.new(bw.outputs[0],green.inputs[0])
links.new(base_color,blend.inputs[1])
links.new(green.outputs[0],blend.inputs[2])
links.new(blend.outputs[0],shader.inputs['Base Color'])
for obj in scene.objects:
    if obj.type!='MESH':continue
    for slot in obj.material_slots:
        if slot.material == lawn:slot.material=fresh
tree_centres=[]
tree_objects=[]
understory_count=0
hidden_pond_trees=0
for obj in scene.objects:
    if obj.hide_render or not obj.name.startswith('Joined source context tree '):continue
    p=obj.matrix_world.translation
    if small_pond.buffer(.3).covers(Point(p.x,p.y)):
        obj.hide_render=True
        hidden_pond_trees+=1
        continue
    if garden_roi.covers(Point(p.x,p.y)):
        obj.scale*=1.15
        tree_centres.append([p.x,p.y])
        tree_objects.append(obj)
        if len(tree_centres)%3==0 and paths.distance(Point(p.x,p.y))>2.2 and water.union(small_pond).distance(Point(p.x,p.y))>2.0:
            shrub=bpy.data.objects.new('Garden understorey at source tree '+str(understory_count),n['protos'][(len(tree_centres)*5+2)%12])
            scene.collection.objects.link(shrub)
            shrub.location=(p.x+.55,p.y-.48,.70)
            shrub.scale=(1.05,.82,.53)
            understory_count+=1

# A reusable isolated canopy is an appearance layer, never a generated
# campus image. Every plane inherits a fixed satellite-sampled tree centre;
# existing 3-D foliage and trunks remain underneath for depth and shadows.
sprite_path=ROOT/'output/garden-tree-canopy.png'
sprite_image=bpy.data.images.load(str(sprite_path),check_existing=True)
sprite_material=bpy.data.materials.new('Garden detailed canopy sprite')
sprite_material.use_nodes=True
nodes=sprite_material.node_tree.nodes
nodes.clear()
links=sprite_material.node_tree.links
tex=nodes.new('ShaderNodeTexImage');tex.image=sprite_image
info=nodes.new('ShaderNodeObjectInfo')
value=nodes.new('ShaderNodeMapRange')
value.inputs['From Min'].default_value=0
value.inputs['From Max'].default_value=1
value.inputs['To Min'].default_value=.62
value.inputs['To Max'].default_value=.88
hsv=nodes.new('ShaderNodeHueSaturation')
hsv.inputs['Hue'].default_value=.55
hsv.inputs['Saturation'].default_value=1.04
transparent=nodes.new('ShaderNodeBsdfTransparent')
bs=nodes.new('ShaderNodeBsdfPrincipled')
bs.inputs['Roughness'].default_value=.93
mix=nodes.new('ShaderNodeMixShader')
output=nodes.new('ShaderNodeOutputMaterial')
links.new(info.outputs['Random'],value.inputs['Value'])
links.new(value.outputs['Result'],hsv.inputs['Value'])
links.new(tex.outputs['Color'],hsv.inputs['Color'])
links.new(hsv.outputs['Color'],bs.inputs['Base Color'])
links.new(tex.outputs['Alpha'],mix.inputs[0])
links.new(transparent.outputs[0],mix.inputs[1])
links.new(bs.outputs[0],mix.inputs[2])
links.new(mix.outputs[0],output.inputs['Surface'])
plane=bpy.data.meshes.new('Garden canopy sprite plane')
plane.from_pydata([(-.5,-.5,0),(.5,-.5,0),(.5,.5,0),(-.5,.5,0)],[],[(0,1,2,3)])
plane.update();plane.materials.append(sprite_material)
uv=plane.uv_layers.new(name='Canopy image UV')
for loop,coord in zip(plane.polygons[0].loop_indices,[(0,0),(1,0),(1,1),(0,1)]):uv.data[loop].uv=coord
sprite_count=0
for i,obj in enumerate(tree_objects):
    p=obj.matrix_world.translation
    crown=bpy.data.objects.new('Garden source-tree canopy image '+str(i),plane)
    scene.collection.objects.link(crown)
    radius=max(obj.scale.x,obj.scale.y)
    variation=.82+.30*((i*7)%13)/12
    crown.location=(p.x,p.y,p.z+obj.scale.z*.76)
    crown.scale=(radius*2.50*variation,radius*2.34*variation,1)
    crown.rotation_euler.z=(i*2.399963229728653)%math.tau
    sprite_count+=1
oval_canopy_count=0
for i,pixel in enumerate(oval_shrubs):
    position=gp(pixel)
    crown=bpy.data.objects.new('Garden source oval shrub canopy '+str(i),plane)
    scene.collection.objects.link(crown)
    crown.location=(position.x,position.y,3.25)
    crown.scale=(4.1+(i%3)*.55,3.9+(i%2)*.4,1)
    crown.rotation_euler.z=(i*2.399963229728653)%math.tau
    oval_canopy_count+=1
cluster_floor=unary_union([Point(x,y).buffer(2.35) for x,y in tree_centres]).buffer(1.6).buffer(-1.6)
cluster_floor=cluster_floor.intersection(detail_mask).difference(paths.buffer(.35)).difference(water.buffer(.25)).difference(small_pond.buffer(.25)).difference(road.buffer(.25)).difference(plaza).difference(row_plot)
forest_floor=material('Garden source tree cluster floor',(.09,.20,.05),.94)
texture(forest_floor,(.052,.145,.028),(.16,.28,.065),.44,.010)
surface('Garden bounded source-tree understory floor',cluster_floor,.10,forest_floor)
for mm in bpy.data.materials:
    if 'broadleaf' not in mm.name.lower() and 'foliage' not in mm.name.lower():continue
    if not mm.use_nodes:continue
    shader=mm.node_tree.nodes.get('Principled BSDF')
    if not shader or shader.inputs['Base Color'].is_linked:continue
    col=shader.inputs['Base Color'].default_value
    if col[1] <= col[0]:continue
    shader.inputs['Base Color'].default_value=(min(.32,col[0]*.77),min(.40,col[1]*.83),min(.17,col[2]*.84),1)

pond=state['pond']
pond_edge=state['pond_edge']
for mm, first, second in [
    (pond,(.07,.21,.18),(.14,.32,.28)),
    (pond_edge,(.11,.24,.20),(.21,.38,.31))]:
    ramp=next(node for node in mm.node_tree.nodes if node.type=='VALTORGB')
    ramp.color_ramp.elements[0].color=(*first,1)
    ramp.color_ramp.elements[1].color=(*second,1)

# Reference-like near-vertical orthography; the target site's geometry and
# north-up orientation remain its own, never copied from the other school.
camera=scene.camera
camera.data.type='ORTHO'
camera.rotation_euler=(math.radians(38),0,0)
corners=[gp(p,z) for p in [(285,1450),(485,1450),(485,1640),(285,1640)] for z in (0,32)]
target=sum(corners,Vector())/len(corners)
camera.location=target+camera.rotation_euler.to_matrix()@Vector((0,0,1500))
bpy.context.view_layer.update()
projected=[camera.matrix_world.inverted()@p for p in corners]
xs=[p.x for p in projected];ys=[p.y for p in projected]
camera.location+=camera.matrix_world.to_3x3()@Vector(((min(xs)+max(xs))/2,(min(ys)+max(ys))/2,0))
camera.data.ortho_scale=max(max(xs)-min(xs),(max(ys)-min(ys))*4/3)*1.05
camera.location+=camera.matrix_world.to_3x3()@Vector((camera.data.ortho_scale*.10,0,0))
sun=scene.objects['Atlas daylight']
sun.rotation_euler=(math.radians(18),math.radians(-10),math.radians(-25))
sun.data.angle=.10
scene.view_settings.exposure=.21
final='--final' in sys.argv
W,H=(2400,1800) if final else (1400,1050)
scene.render.resolution_x=W
scene.render.resolution_y=H
scene.render.resolution_percentage=100
scene.cycles.samples=26 if final else 10
scene.render.image_settings.file_format='PNG'
scene.render.image_settings.color_mode='RGB'
scene.render.filepath=str(CACHE/'garden.png')
sources={**state['ctx']['sources'],**{p:sha(ROOT/p) for p in ['scripts/garden_pilot.py','scripts/campus_expansion.py','model/campus/references/satellite.jpg','output/garden-tree-canopy.png']}}
checks={
    'island_outside_source_water_m2':plaza.difference(water_feature).area,
    'plaza_roof_overlap_m2':plaza.intersection(roofs).area,
    'paths_outside_ground_m2':paths.difference(ground).area,
    'paths_roof_overlap_m2':paths.intersection(roofs).area,
    'paths_water_overlap_m2':paths.intersection(water).area,
    'junctions_outside_ground_m2':unary_union(junctions).difference(ground).area,
    'planting_roof_overlap_m2':planting.intersection(roofs).area,
    'tree_floor_outside_ground_m2':cluster_floor.difference(ground).area,
    'tree_floor_roof_overlap_m2':cluster_floor.intersection(roofs).area,
    'tree_floor_water_overlap_m2':cluster_floor.intersection(water).area,
    'forecourt_roof_overlap_m2':square.intersection(roofs).area,
    'forecourt_planting_outside_source_m2':oval.difference(square).area,
    'deep_water_outside_source_m2':deep_water_shape.difference(water_feature).area,
    'east_row_plot_outside_source_ground_m2':row_plot.difference(ground).area,
    'east_row_plot_roof_overlap_m2':row_plot.intersection(roofs).area,
    'small_pond_outside_source_ground_m2':small_pond.difference(ground).area,
    'small_pond_roof_overlap_m2':small_pond.intersection(roofs).area,
    'small_pond_road_overlap_m2':small_pond.intersection(road).area,
    'light_road_outside_existing_road_m2':light_footprint.difference(road).area,
    'dark_road_outside_existing_road_m2':dark_footprint.difference(road).area,
}
assert max(checks.values()) < .01, checks
meta={'title':'太湖校园南部花园局部样板','status':'candidate_needs_visual_review',
      'source_pixel_roi':[[255,1378],[529,1654]],'source_plaza_center_pixel':list(center_px),
      'source_path_ids':[name for name,_,_ in routes],
      'source_path_max_smoothing_deviation_m':max(route_deviations),
      'source_tree_centres_preserved':len(tree_centres),
      'understorey_attached_to_source_tree_centres':understory_count,
      'source_tree_centres_reclassified_as_eastern_pond':hidden_pond_trees,
      'source_tree_trunks_reclassified_as_eastern_pond':omitted_pond_trunks,
      'source_tree_sprite_count':sprite_count,
      'oval_canopy_sprite_count':oval_canopy_count,
      'source_road_names':['花卉园东南路','梅茶一路'],
      'oval_shrub_positions_source_pixels':oval_shrubs,
      'pilot_hidden_coarse_paving':hidden_coarse,
      'image_size':[W,H],'samples':scene.cycles.samples,
      'camera':{'position':list(camera.location),'rotation_euler':list(camera.rotation_euler),'ortho_scale':camera.data.ortho_scale},
      'sources':sources,'checks':checks,
      'method':'Native Blender 3-D render; source-traced buildings, roads and tree centres. Satellite-visible central stone island restored inside the formerly solid flower-round-water polygon, and the misclassified flower-square polygon rendered as a striped paved forecourt with planted oval. Existing winding walks were smoothed within their recorded controls. The source-named diagonal road is finished as pale paving and Meicha First Road as charcoal pavement with restrained centre dashes; both finishes are clipped to existing road geometry. Deep water and source-supported planted centres add local material depth. An eastern planted row plot and small separate pond are bounded by visible satellite pixels.',
      'limitations':'Plant species, planted-row spacing, paving dimensions, road paint, hidden facades and water depth are illustrative. Other-campus reference is visual craft only.'}
(CACHE/'garden.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')
print('GARDEN READY',W,H,checks,flush=True)
bpy.ops.render.render(write_still=True)
assert cache_bytes() < 192*1024**2
for p,h in sources.items():assert sha(ROOT/p)==h,p
if final:
    result=subprocess.run(['/opt/anaconda3/bin/python',str(Path(__file__)),'--export'],check=True,text=True,capture_output=True)
    print(result.stdout,flush=True)
print('GARDEN DONE',flush=True)
