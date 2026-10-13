"""Extend the reviewed study recipes over the retained campus in memory.
Blender --background -t 4 --python scripts/campus_expansion.py [-- --final]
Regional diagnostics: --region north|extension|middle|lake|south. No saved scene.
"""
from pathlib import Path
import sys, json, hashlib, math, subprocess
ROOT=Path(__file__).resolve().parents[1]
CACHE=Path('/tmp/taihu-full');OUT=ROOT/'public/assets'
sys.dont_write_bytecode=True
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def replace(code,a,b):
    assert code.count(a)==1,a
    return code.replace(a,b)

# Consume only the construction section. Independent sample files are immutable.
source=ROOT/'scripts/campus_study.py'
code=source.read_text().split('# One shared sun and the north camera direction')[0]
code=replace(code,"or not roi.covers(Point(p.x,p.y))", "or False")
ctx={'__file__':str(source),'__name__':'__expanded_study__'}
render_args=sys.argv[:]
if '--region' in sys.argv:
    i=sys.argv.index('--region');sys.argv=sys.argv[:i]+sys.argv[i+2:]
exec(compile(code,str(source),'exec'),ctx)
sys.argv=render_args
import bpy
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view
from shapely.geometry import Polygon,Point,LineString,box
from shapely.ops import unary_union
s=ctx['s'];n=ctx['n'];c=ctx['c'];D=ctx['D'];roi=ctx['roi']
main=json.loads((ROOT/'model/campus/references/satellite-export.json').read_text())['extent']
ext=json.loads((ROOT/'model/campus/references/north-extension.json').read_text())['extent']
ox,oy=map(float,s['origin_epsg3857'].split(','));cs=float(s['metric_scale'])
def gp(q,z=0,source='satellite'):
    e,w,h=(ext,1000,900) if source=='north-extension' else (main,1152,1920)
    return Vector(((e['xmin']+q[0]/w*(e['xmax']-e['xmin'])-ox)*cs,(e['ymax']-q[1]/h*(e['ymax']-e['ymin'])-oy)*cs,z))
def shape(row):return Polygon([tuple(gp(p,source=row.get('source','satellite')))[:2] for p in row['outline']])
roofs=unary_union([shape(r) for r in D['buildings']]+[c['bodies']])
water=unary_union([shape(r) for r in D['surfaces'] if r['kind']=='water']+[ctx['lake']])
ground=unary_union([shape(r) for r in D['surfaces'] if r['kind']=='ground'])
surface=n['surface'];lawn=n['lawn'];pave=n['pave'];curb=n['curb']

# Sports meshes retain the source geometry and markings. North sample courts
# supersede only those original courts inside its explicitly traced mask.
sport_polys=[];sport_names=[]
for ob in s.objects:
    if ob.name not in n['original_names'] or ob.type!='MESH':continue
    if any(col.name.startswith('03 Sports') for col in ob.users_collection):
        pts=[ob.matrix_world@v.co for v in ob.data.vertices]
        footprint=Polygon([(p.x,p.y) for p in pts]).convex_hull
        if ctx['n']['sportmask'].intersection(footprint).area>footprint.area*.5:continue
        ob.hide_render=False;sport_names.append(ob.name);sport_polys.append(footprint)
sports=unary_union(sport_polys+[n['sportmask']])
# The original rectangular turf stripes crossed the curved running lanes.
# Keep the traced stadium perimeter and clip only interior finish/marking faces.
track_repairs=[]
for name in [r['name'] for r in D['tracks']]:
    ob=s.objects[name];me=ob.data;inner=[]
    for f in me.polygons:
        pts=[ob.matrix_world@me.vertices[i].co for i in f.vertices]
        if me.materials[f.material_index].name=='Turf dark' and all(abs(p.z-.20)<.001 for p in pts):
            g=Polygon([(p.x,p.y) for p in pts])
            if g.is_valid and g.area>1e-8:inner.append(g)
    field=unary_union(inner);assert not field.is_empty,name
    batch=n['Mesh']('Expansion repaired '+name);removed=0
    for f in me.polygons:
        pts=[ob.matrix_world@me.vertices[i].co for i in f.vertices];mat=me.materials[f.material_index]
        clip=(mat.name in ('Turf light','Turf dark') and min(p.z for p in pts)>.21) or (mat.name=='Court and road lines' and min(p.z for p in pts)>.249 and max(p.z for p in pts)<.30)
        if clip:
            g=Polygon([(p.x,p.y) for p in pts])
            if g.is_valid and g.area>1e-8:
                clean=g.intersection(field);removed+=g.difference(field).area
                batch.plane(clean,max(p.z for p in pts),mat)
        else:batch.face([tuple(p) for p in pts],mat)
    batch.finish();ob.hide_render=True;track_repairs.append({'name':name,'clipped_finish_area_m2':removed,'source_perimeter_preserved':True})
# Rebuild remaining architecture using its existing traced footprint and roof
# family. Fine facade dimensions outside photographic coverage are estimates.
from refine_buildings import refine_north
rest=refine_north(s,{'buildings':[r for r in D['buildings'] if r['id'] not in n['ids']]},gp,n['mat'],ROOT)
faces={**rest['roof_faces_world'],**n['faces']}
for ident in ['B06','B07','B08']:
    faces[ident]=[[list(c['pt'](q,f.get('base_z',0)+f.get('height_m_estimate',0))) for q in f['pixel_outline']] for f in c['F'] if f['id'].startswith(ident)]
assert len(faces)==130

# Extend the fixed union layers; boundaries are clipped, never extrapolated.
rd=json.loads((ROOT/'model/campus/roads.json').read_text())
def layer_polygon(layer):
    v=layer['vertices']
    return unary_union([Polygon([v[i][:2] for i in f]) for f in layer['faces'] if len(f)==3])
layers={r['name']:layer_polygon(r) for r in rd['layers']}
outside=ground.difference(roi)
mask=roofs.buffer(.35).union(water.buffer(.1)).union(sports.buffer(.20))
asphalt=layers['Road asphalt union'].intersection(outside).difference(mask)
paving=layers['Road paving union'].intersection(outside).difference(mask).difference(asphalt)
# The legacy union contains many detached triangles and sub-metre tails which
# read as white shards in the aerial view. Keep its substantial connected
# hardscape, while the separately traced plazas and walks below remain intact.
raw_paving=paving
opened_paving=paving.buffer(-.35).buffer(.35)
pieces=list(opened_paving.geoms) if hasattr(opened_paving,'geoms') else [opened_paving]
paving=unary_union([piece for piece in pieces if piece.area>=250]).intersection(raw_paving)
paving_cleanup={'removed_area_m2':raw_paving.difference(paving).area,
                'outside_original_paving_m2':paving.difference(raw_paving).area,
                'retained_piece_count':sum(piece.area>=250 for piece in pieces),
                'discarded_piece_count':sum(piece.area<250 for piece in pieces)}
assert paving_cleanup['outside_original_paving_m2']<.01
# The coarse union mislabels small garden lawns as disconnected stone shards.
# The satellite-traced garden finish below replaces only this bounded area.
garden_roi=Polygon([tuple(gp(p))[:2] for p in [(248,1375),(535,1375),(535,1662),(248,1662)]])
paving=paving.difference(garden_roi)
# Satellite-guided grass pigment restores the visible dry/green variation of
# this campus without using the image as a substitute for 3-D roofs or paths.
# The northern extension has a separate fixed photograph and coordinate frame.
cut=gp((0,90)).y
lawn_extension=lawn.copy();lawn_extension.name='Expansion north source meadow'
def ground_pigment(material,source):
    ext_source=source=='north-extension'
    width,height=(1000,900) if ext_source else (1152,1920)
    lo=gp((0,height),source=source);hi=gp((width,0),source=source)
    ns=material.node_tree.nodes;links=material.node_tree.links;bs=ns.get('Principled BSDF')
    underlying=bs.inputs['Base Color'].links[0].from_socket
    coord=ns.new('ShaderNodeTexCoord');coord.object=n['anchor']
    mapped=ns.new('ShaderNodeVectorMath');mapped.operation='MULTIPLY_ADD'
    mapped.inputs[1].default_value=(1/(hi.x-lo.x),1/(hi.y-lo.y),1)
    mapped.inputs[2].default_value=(-lo.x/(hi.x-lo.x),-lo.y/(hi.y-lo.y),0)
    photo=ns.new('ShaderNodeTexImage')
    photo.image=bpy.data.images.load(str(ROOT/'model/campus/references'/('north-extension.jpg' if ext_source else 'satellite.jpg')),check_existing=True)
    photo.interpolation='Cubic';photo.extension='EXTEND'
    # The aerial survey shows dry olive lawns around the lake and the middle
    # courts. Give that recorded ground colour priority over the generic study
    # meadow shader, while retaining its fine procedural relief.
    mix=ns.new('ShaderNodeMixRGB');mix.inputs[0].default_value=.82 if not ext_source else .55
    links.new(coord.outputs['Object'],mapped.inputs[0]);links.new(mapped.outputs[0],photo.inputs['Vector'])
    links.new(underlying,mix.inputs[1]);links.new(photo.outputs['Color'],mix.inputs[2])
    links.new(mix.outputs[0],bs.inputs['Base Color'])
ground_pigment(lawn,'satellite');ground_pigment(lawn_extension,'north-extension')
south_ground=outside.intersection(box(-1e4,-1e4,1e4,cut)).difference(water)
north_ground=outside.intersection(box(-1e4,cut,1e4,1e4)).difference(water)
surface('Expansion source ground',south_ground,.05,lawn)
surface('Expansion north source ground',north_ground,.05,lawn_extension)
# One asphalt finish spans the joined study and expanded campus. Lower its
# value to restore the charcoal road/stone contrast visible in the reference.
road_ramp=next(node for node in ctx['roadmat'].node_tree.nodes if node.bl_idname=='ShaderNodeValToRGB')
road_ramp.color_ramp.elements[0].color=(.055,.070,.066,1)
road_ramp.color_ramp.elements[1].color=(.105,.120,.112,1)
surface('Expansion source roads',asphalt,.35,ctx['roadmat'])
# A restrained cartographic centre rhythm makes the three broad, surveyed
# cross-campus roads legible at atlas scale. The paths come from layout.json;
# the faded dash spacing is illustrative, not a traffic survey.
main_route_names={'北区东西联系路','湖区南侧横路','中区东西路'}
markable_roads=asphalt.union(ctx['road']).difference(mask).buffer(-.22)
route_paint=n['mat']('Expansion subdued atlas road dashes',(.56,.59,.53),.94)
route_marks=n['Mesh']('Expansion surveyed broad-road dashes')
route_mark_shapes=[];route_mark_counts={}
for name,pixels,width in D['roads']:
    if name not in main_route_names:continue
    route=LineString([tuple(gp(p))[:2] for p in pixels])
    count=0
    for distance in range(5,int(route.length)-5,11):
        a,b=route.interpolate(distance),route.interpolate(min(distance+2.6,route.length-5))
        dash=LineString([a,b]).buffer(.055,cap_style='flat').intersection(markable_roads)
        if dash.is_empty:continue
        route_marks.plane(dash,.394,route_paint);route_mark_shapes.append(dash);count+=1
    route_mark_counts[name]=count
route_marks.finish()
road_marks=unary_union(route_mark_shapes)
road_mark_checks={'source_routes':route_mark_counts,'dash_count':len(route_mark_shapes),
                  'outside_existing_road_m2':road_marks.difference(asphalt.union(ctx['road'])).area,
                  'roof_overlap_m2':road_marks.intersection(roofs).area,
                  'water_overlap_m2':road_marks.intersection(water).area}
assert all(road_mark_checks[k]<1e-7 for k in ('outside_existing_road_m2','roof_overlap_m2','water_overlap_m2'))
for source,area in [('satellite',box(-1e4,-1e4,1e4,cut)),
                    ('north-extension',box(-1e4,cut,1e4,1e4))]:
    surface('Expansion source paving '+source,paving.intersection(area),.31,pave)
surface('Expansion road margins',asphalt.buffer(.25).difference(asphalt).intersection(outside).difference(mask),.38,curb)
surface('Expansion paving courses',paving.difference(paving.buffer(-.22)),.335,curb)
pond=n['mat']('Expansion source pond water',(.075,.19,.17),.34)
pond_edge=n['mat']('Expansion source pond shallows',(.12,.255,.22),.42)
for material,colors,scale in [(pond,((.045,.13,.12),(.11,.225,.19)),.20),
                              (pond_edge,((.09,.20,.17),(.18,.29,.22)),.48)]:
    n['texture'](material,*colors,scale,.018)
    bs=material.node_tree.nodes.get('Principled BSDF')
    bs.inputs['Metallic'].default_value=.07
for row in D['surfaces']:
    if row['kind']=='water':
        wet=shape(row).difference(roi)
        surface('Expansion water '+row['id'],wet,-.075,pond)
        surface('Expansion shallow edge '+row['id'],wet.difference(wet.buffer(-.75)),-.068,pond_edge)
    elif row['kind']=='parking':surface('Expansion parking '+row['id'],shape(row).intersection(outside).difference(mask),.425,ctx['parking_finish'])
planted_shapes={}
for row in D.get('landscape',{}).get('lawn_polygons',[]):
    g=shape(row).intersection(outside).difference(mask).difference(asphalt)
    planted_shapes[row['id']]=g
    planted_material=lawn_extension if row.get('source')=='north-extension' else lawn
    # Formal beds were previously below the complete plaza at z=.43. Keep
    # their photographed footprint, but make the planted finish visible.
    planted_z=.447 if row['id'].startswith('E formal garden') else .33
    surface('Expansion planting '+row['id'],g,planted_z,planted_material)
    surface('Expansion planting margin '+row['id'],g.buffer(.20).difference(g).intersection(paving),.34,curb)
formal_beds=unary_union([g for ident,g in planted_shapes.items() if ident.startswith('E formal garden')])
planting_mask=unary_union(list(planted_shapes.values()))

# The fixed survey already contains local plazas and garden walks that the
# broad road union did not render. Keep every course inside its traced outline.
landscape=D['landscape']; source_details={'paved_places':[], 'garden_walks':[]}
detail_shapes=[]
detail_exclusion=roofs.buffer(.32).union(water.buffer(.35)).union(sports.buffer(.25))
stone=n['mat']('Expansion garden sandstone',(.63,.59,.51))
bed_edge=n['mat']('Expansion low planting edge',(.42,.43,.34))
def paver_shader(material,first,second,mortar,width,height):
    ns=material.node_tree.nodes;links=material.node_tree.links
    bs=ns.get('Principled BSDF');coord=ns.new('ShaderNodeTexCoord');coord.object=n['anchor']
    brick=ns.new('ShaderNodeTexBrick');brick.offset=.5
    brick.inputs['Scale'].default_value=1
    brick.inputs['Brick Width'].default_value=width
    brick.inputs['Row Height'].default_value=height
    brick.inputs['Mortar Size'].default_value=.025
    brick.inputs['Color1'].default_value=(*first,1)
    brick.inputs['Color2'].default_value=(*second,1)
    brick.inputs['Mortar'].default_value=(*mortar,1)
    links.new(coord.outputs['Object'],brick.inputs['Vector'])
    links.new(brick.outputs['Color'],bs.inputs['Base Color'])
paver_shader(stone,(.67,.63,.57),(.58,.55,.50),(.40,.41,.38),1.15,.75)
# Smaller courses retain the paved surface without an oversized checkerboard.
for material in [pave,ctx['court_finish'],ctx['walk_finish']]:
    paver_shader(material,(.62,.60,.54),(.54,.535,.49),(.37,.39,.37),1.10,.72)
# The inherited paving union has coarse, jagged outlines. Its real source
# photograph supplies local tone, while the separately traced plazas below
# keep the crisp pale sandstone finish. This reduces false white fragments.
for source in ('satellite','north-extension'):
    finish=pave.copy();finish.name='Expansion source-tinted paving '+source
    ns=finish.node_tree.nodes;links=finish.node_tree.links;bs=ns.get('Principled BSDF')
    stone_color=bs.inputs['Base Color'].links[0].from_socket
    lo=gp((0,900 if source=='north-extension' else 1920),source=source)
    hi=gp((1000 if source=='north-extension' else 1152,0),source=source)
    coord=ns.new('ShaderNodeTexCoord');coord.object=n['anchor']
    mapped=ns.new('ShaderNodeVectorMath');mapped.operation='MULTIPLY_ADD'
    mapped.inputs[1].default_value=(1/(hi.x-lo.x),1/(hi.y-lo.y),1)
    mapped.inputs[2].default_value=(-lo.x/(hi.x-lo.x),-lo.y/(hi.y-lo.y),0)
    photo=ns.new('ShaderNodeTexImage')
    photo.image=bpy.data.images.load(str(ROOT/'model/campus/references'/('north-extension.jpg' if source=='north-extension' else 'satellite.jpg')),check_existing=True)
    photo.interpolation='Cubic';photo.extension='EXTEND'
    blend=ns.new('ShaderNodeMixRGB');blend.inputs[0].default_value=.34
    links.new(coord.outputs['Object'],mapped.inputs[0]);links.new(mapped.outputs[0],photo.inputs['Vector'])
    links.new(stone_color,blend.inputs[1]);links.new(photo.outputs['Color'],blend.inputs[2])
    links.new(blend.outputs[0],bs.inputs['Base Color'])
    s.objects['Expansion source paving '+source].data.materials[0]=finish
for row in landscape['paving_polygons']:
    if row['id'].startswith('N'):continue # represented by the north study
    g=shape(row).intersection(outside).difference(detail_exclusion).difference(asphalt)
    g=g.difference(formal_beds)
    if g.is_empty:continue
    surface('Expansion surveyed plaza '+row['id'],g,.43,stone)
    surface('Expansion plaza perimeter '+row['id'],g.difference(g.buffer(-.22)),.445,curb)
    detail_shapes.append(g)
    source_details['paved_places'].append({'id':row['id'],'area_m2':g.area})
for row in landscape['footpaths']:
    if row['id'].startswith('North extension') or row['id'].startswith(('Flower','South')):
        route=LineString([tuple(gp(q,source=row['source']))[:2] for q in row['points']])
        g=route.buffer(row['width_m']/2,join_style='round',cap_style='round').intersection(outside).difference(detail_exclusion).difference(asphalt)
        if g.is_empty:continue
        surface('Expansion surveyed walk '+row['id'],g,.455,stone)
        rim=g.buffer(.16).difference(g).difference(detail_exclusion).difference(asphalt)
        surface('Expansion walk stone edge '+row['id'],rim,.451,curb)
        detail_shapes.append(g)
        source_details['garden_walks'].append({'id':row['id'],'area_m2':g.area})
# The two formal beds are recorded in the same source coordinate frame. Their
# restrained rims distinguish planted ground from the surrounding plaza.
for row in landscape['lawn_polygons']:
    if not row['id'].startswith('E formal garden'):continue
    g=planted_shapes[row['id']]
    rim=g.difference(g.buffer(-.32))
    surface('Expansion formal garden bed rim '+row['id'],rim,.475,bed_edge)
    surface('Expansion formal garden inner stone '+row['id'],g.buffer(.16).difference(g),.46,curb)
detail_union=unary_union(detail_shapes)
source_details['checks']={'detail_outside_ground_m2':detail_union.difference(ground).area,
                          'detail_roof_intersection_m2':detail_union.intersection(roofs).area,
                          'detail_water_intersection_m2':detail_union.intersection(water).area}
assert all(v<1e-7 for v in source_details['checks'].values())
formal_bed_checks={'bed_count':sum(ident.startswith('E formal garden') for ident in planted_shapes),
    'area_m2':formal_beds.area,'plaza_overlap_m2':formal_beds.intersection(detail_union).area,
    'outside_source_beds_m2':formal_beds.difference(unary_union([shape(row) for row in landscape['lawn_polygons'] if row['id'].startswith('E formal garden')])).area,
    'source_frame':'north-extension','planting_z_m':.447,'plaza_z_m':.43}
assert formal_bed_checks['bed_count']==2 and formal_bed_checks['area_m2']>0
assert formal_bed_checks['plaza_overlap_m2']<1e-7 and formal_bed_checks['outside_source_beds_m2']<1e-7

# Paired trunks were built by the joined recipe, including retained surrounding
# crowns. Reject source-sampled crowns on restored sports and roofs, and rebuild
# the one shared trunk batch so hidden crowns cannot leave bare trunks behind.
s.objects['Joined paired tree trunks'].hide_render=True
trunks=n['Mesh']('Expansion paired tree trunks');pairs=[];excluded=[]
for ob in s.objects:
    if ob.hide_render or not ob.name.startswith(('Study source tree ','Lake source branched tree ','Joined source context tree ')):continue
    p=ob.matrix_world.translation
    if ob.name.startswith('Joined source context tree ') and (sports.covers(Point(p.x,p.y)) or roofs.covers(Point(p.x,p.y))):
        ob.hide_render=True;excluded.append(ob.name);continue
    top=ob.matrix_world@Vector((0,0,-.86))
    if top.z>.12:
        radius=min(.19,max(.085,min(ob.scale.x,ob.scale.y)*.032))
        n['branch'](trunks,Vector((p.x,p.y,.02)),top,radius,radius*.62)
        pairs.append([ob.name,list(p),float(top.z)])
trunks.finish()

# Small root finishes use only retained context-tree centres on traced paving.
# Radius and stone-course width are presentation estimates, not new surveyed
# planting locations. Existing north-study and flower-garden basins stay intact.
pit_ground=paving.union(detail_union).difference(planting_mask).difference(asphalt.buffer(.12)).difference(detail_exclusion).difference(roi).difference(garden_roi)
pit_soil=n['mat']('Expansion context tree root soil',(.14,.135,.095),.98)
n['texture'](pit_soil,(.115,.11,.075),(.19,.18,.125),7,.012)
root_soil=n['Mesh']('Expansion retained-tree root finish')
root_rim=n['Mesh']('Expansion retained-tree root stone course')
root_pits=[];root_pit_shapes=[]
for name,centre,top_z in pairs:
    if not name.startswith('Joined source context tree '):continue
    point=Point(centre[:2])
    if not pit_ground.covers(point):continue
    crown=s.objects[name]
    radius=min(.95,max(.55,min(crown.scale.x,crown.scale.y)*.24))
    footprint=point.buffer(radius,resolution=12).intersection(pit_ground)
    if footprint.area<.55:continue
    z=.462 if detail_union.covers(point) else .347
    rim=footprint.difference(point.buffer(max(.35,radius-.13),resolution=12))
    root_soil.plane(footprint,z,pit_soil);root_rim.plane(rim,z+.006,bed_edge)
    root_pit_shapes.append(footprint)
    root_pits.append({'source_tree':name,'centre_world':centre[:2],'radius_m_estimate':radius,'area_m2':footprint.area,'finish_z_m':z})
root_soil.finish();root_rim.finish()
root_pit_union=unary_union(root_pit_shapes)
root_pit_checks={'count':len(root_pits),'area_m2':root_pit_union.area,
    'outside_traced_paving_m2':root_pit_union.difference(paving.union(detail_union)).area,
    'road_overlap_m2':root_pit_union.intersection(asphalt).area,
    'roof_overlap_m2':root_pit_union.intersection(roofs).area,
    'water_overlap_m2':root_pit_union.intersection(water).area,
    'planting_overlap_m2':root_pit_union.intersection(planting_mask).area,
    'source_centres_preserved':all(list(s.objects[r['source_tree']].matrix_world.translation)[:2]==r['centre_world'] for r in root_pits)}
assert root_pit_checks['source_centres_preserved']
assert all(v<1e-7 for k,v in root_pit_checks.items() if k.endswith('_m2') and k!='area_m2')

# Reuse original georeferenced imagery materials only outside modeled ground.
# Each image has its own export extent and UV frame.
s.objects['Joined exterior context'].hide_render=True
for name,e,wh in [('satellite',main,(1152,1920)),('north-extension',ext,(1000,900))]:
    cov=Polygon([tuple(gp(p,source=name))[:2] for p in [(0,0),(wh[0],0),wh,(0,wh[1])]])
    cov=cov.intersection(box(-1e4,cut,1e4,1e4) if name=='north-extension' else box(-1e4,-1e4,1e4,cut))
    original=s.objects.get(name+' outside-campus context');assert original
    ob=surface('Expansion '+name+' context',cov.difference(ground).difference(roofs).difference(water),-.10,original.data.materials[0])
    uv=ob.data.uv_layers.new(name='Source geographic UV')
    for face in ob.data.polygons:
        for li in face.loop_indices:
            p=ob.data.vertices[ob.data.loops[li].vertex_index].co
            uv.data[li].uv=((p.x/cs+ox-e['xmin'])/(e['xmax']-e['xmin']),(p.y/cs+oy-e['ymin'])/(e['ymax']-e['ymin']))
# The full map has no sample-crop colour transition inside the campus.
ctx['ground_ob'].data.materials[0]=lawn
sun=s.objects['Atlas daylight'];sun.data.energy=2.8;sun.data.angle=.07
sun.rotation_euler=(math.radians(27),math.radians(-22),math.radians(-30))
# The construction-only import omits the joined study's lighting block.
# Explicit diffuse fill keeps facades/crowns from inheriting a flat sky.
# The glossy sky and camera background keep their existing ray paths.
diffuse_sky=s.world.node_tree.nodes.get('Background')
assert diffuse_sky and diffuse_sky.bl_idname=='ShaderNodeBackground'
inherited_diffuse_strength=float(diffuse_sky.inputs['Strength'].default_value)
diffuse_sky.inputs['Color'].default_value=(.88,.90,.94,1)
diffuse_sky.inputs['Strength'].default_value=.32

baseline=json.loads((OUT/'campus-atlas.json').read_text())
roof_faces_preserved=json.loads(json.dumps(faces))==baseline['roof_faces_world']
assert roof_faces_preserved, 'Material pass must preserve every source roof face'
final='--final' in sys.argv
region=sys.argv[sys.argv.index('--region')+1] if '--region' in sys.argv else None
assert not (final and region)
W,H=(7168,3072) if final else (2400,1029)
cam=s.camera
for key in ['position','rotation_euler']:
    if key=='position':cam.location=baseline['camera'][key]
    else:cam.rotation_euler=baseline['camera'][key]
cam.data.ortho_scale=baseline['camera']['ortho_scale'];cam.data.type='ORTHO'
if region:
    prefixes={'north':('N',),'extension':('E',),'middle':('M','B'),'lake':('B',),'south':('F','S')}[region]
    points=[Vector(p) for k,fs in faces.items() if k.startswith(prefixes) for f in fs for p in f]
    points += [Vector((p.x,p.y,0)) for p in points]
    W,H=1800,1350;target=sum(points,Vector())/len(points)
    cam.location=target+cam.rotation_euler.to_matrix()@Vector((0,0,2000));bpy.context.view_layer.update()
    pp=[cam.matrix_world.inverted()@p for p in points];xs=[p.x for p in pp];ys=[p.y for p in pp]
    cam.location+=cam.matrix_world.to_3x3()@Vector(((min(xs)+max(xs))/2,(min(ys)+max(ys))/2,0))
    cam.data.ortho_scale=max(max(xs)-min(xs),(max(ys)-min(ys))*W/H)*1.12
# Reuse the reviewed north-block finish in the full atlas. It only touches
# source-traced roof/ground geometry and fixed satellite tree centres.
from north_pilot_detail import add_pilot_detail
extension_roof_slots=[(slot,slot.material) for obj in s.objects for slot in obj.material_slots
                      if slot.material and 'north-extension' in slot.material.name]
north_detail_checks=add_pilot_detail(n)
for slot,source_material in extension_roof_slots:
    slot.material=source_material
north_detail_checks['north_extension_material_slots_preserved']=len(extension_roof_slots)
from garden_detail import add_garden_detail
garden_detail_checks=add_garden_detail(globals())
# The broad pale slab beside the central lake is a marked parking surface in
# the fixed satellite image, not a blank plaza. Restore the visible bay rhythm
# inside that image footprint; stall count and line width are illustrative.
central_parking_pixels=[(489,726),(560,731),(557,809),(489,806)]
central_parking_source=Polygon([tuple(gp(p))[:2] for p in central_parking_pixels])
central_parking=central_parking_source.intersection(ground).difference(roofs.buffer(.15)).difference(water.buffer(.15)).difference(sports.buffer(.15)).difference(ctx['road'].buffer(.12))
parking_concrete=n['mat']('Expansion central lake parking concrete',(.43,.435,.40))
n['texture'](parking_concrete,(.37,.38,.35),(.51,.51,.47),5,.008)
surface('Expansion source central lake parking surface',central_parking,.452,parking_concrete)
parking_paint=n['mat']('Expansion central lake faded parking lines',(.73,.73,.67))
parking_lines=[]
for y0,y1 in [(735,753),(763,780),(790,803)]:
    for x in range(494,557,4):
        a,b=gp((x,y0)),gp((x-.6,y1))
        marking=LineString([(a.x,a.y),(b.x,b.y)]).buffer(.048).intersection(central_parking.buffer(-.18))
        if not marking.is_empty:parking_lines.append(marking)
    for y in (y0,y1):
        a,b=gp((494,y)),gp((556,y))
        marking=LineString([(a.x,a.y),(b.x,b.y)]).buffer(.043).intersection(central_parking.buffer(-.18))
        if not marking.is_empty:parking_lines.append(marking)
parking_markings=unary_union(parking_lines)
surface('Expansion source central lake parking bay markings',parking_markings,.465,parking_paint)
central_parking_checks={'source_pixels':central_parking_pixels,'visible_area_m2':central_parking.area,
    'marking_groups':len(parking_lines),'roof_overlap_m2':central_parking.intersection(roofs).area,
    'water_overlap_m2':central_parking.intersection(water).area,
    'markings_outside_parking_m2':parking_markings.difference(central_parking).area}
assert central_parking.area>100 and all(central_parking_checks[key]<1e-7 for key in ('roof_overlap_m2','water_overlap_m2','markings_outside_parking_m2'))
# The campus aerial shows repeated narrow seams across the pale B08 lakeside
# roof. Keep these on the already traced roof planes; the seam spacing and
# exact module count are a photo interpretation, not a roof survey.
b08_low=next(f for f in c['F'] if f['id']=='B08 lakeside courtyard wings')
b08_roof=Polygon([tuple(c['pt'](p))[:2] for p in b08_low['pixel_outline']])
b08_glass=Polygon([tuple(c['pt'](p))[:2] for p in [(1171,449),(1214,449),(1214,543),(1171,543)]])
b08_seam_limit=b08_roof.buffer(-.85).difference(b08_glass.buffer(.25))
b08_seam_mat=n['mat']('B08 photo-led pale roof joints',(.36,.43,.43),.92)
b08_seams=n['Mesh']('B08 photo-led roof courses')
b08_seam_shapes=[]
for x in list(range(856,1080,12))+list(range(1048,1208,12)):
    segment=LineString([tuple(c['pt']((x,418)))[:2],tuple(c['pt']((x,622)))[:2]])
    seam=segment.buffer(.052,cap_style='flat').intersection(b08_seam_limit)
    if seam.is_empty:continue
    b08_seams.plane(seam,13.485,b08_seam_mat);b08_seam_shapes.append(seam)
for y in range(393,615,12):
    segment=LineString([tuple(c['pt']((1149,y)))[:2],tuple(c['pt']((1220,y)))[:2]])
    seam=segment.buffer(.052,cap_style='flat').intersection(b08_seam_limit)
    if seam.is_empty:continue
    b08_seams.plane(seam,13.485,b08_seam_mat);b08_seam_shapes.append(seam)
b08_seams.finish()
b08_seam_union=unary_union(b08_seam_shapes)
b08_roof_checks={'source_photo':'model/central-campus/references/campus-aerial.jpg',
                 'source_roof_id':b08_low['id'],'seam_count':len(b08_seam_shapes),
                 'seams_outside_source_roof_m2':b08_seam_union.difference(b08_roof).area,
                 'seams_on_glazed_roof_m2':b08_seam_union.intersection(b08_glass).area}
assert b08_roof_checks['seam_count']>25 and all(b08_roof_checks[k]<1e-7 for k in ('seams_outside_source_roof_m2','seams_on_glazed_roof_m2'))
# Surface-only architectural finishing. Contact shading comes from the actual
# scene geometry; no painted shadows, entrances or new building parts are used.
central_photo_facade_prefixes=('B06 ceramic red facade','B06 recessed warm concrete',
    'B07 pale mineral infill','B07 terracotta pilasters','B07 limestone cornice',
    'B08 offwhite facade panels','B08 salmon spandrel','B08 light window frames')
wall_prefixes=('Atlas architecture warm plaster','Atlas architecture pale trim',
    'Atlas architecture salmon wall','Atlas architecture red brick',
    'Atlas architecture neutral residential plaster','Atlas architecture institutional pale plaster',
    'Atlas architecture weathered campus plaster','Atlas architecture muted campus stone trim',
    'Atlas architecture muted stone plinth','Study limestone','Study cream edge',
    'Study red masonry','Study academic pale aluminium','Warm mineral facade',
    'Photo observed terracotta bands','Pale facade frame')+central_photo_facade_prefixes
paving_prefixes=('Study pale warm mineral paving','Joined academic courtyard sandstone',
    'Joined pedestrian edge stone','Expansion source-tinted paving','Expansion garden sandstone')
visible_materials={ob.data.materials[i] for ob in s.objects if not ob.hide_render and ob.type=='MESH'
                   for i in {face.material_index for face in ob.data.polygons}
                   if i<len(ob.data.materials) and ob.data.materials[i]}
wall_finishes=[];paving_finishes=[];brick_finishes=[]
for material in sorted(visible_materials,key=lambda m:m.name):
    wall=material.name.startswith(wall_prefixes)
    paved=material.name.startswith(paving_prefixes)
    if not (wall or paved) or not material.use_nodes:continue
    ns=material.node_tree.nodes;links=material.node_tree.links;bs=ns.get('Principled BSDF')
    if not bs:continue
    current=bs.inputs['Base Color'].links[0].from_socket if bs.inputs['Base Color'].is_linked else None
    if wall:
        coord=ns.new('ShaderNodeTexCoord');coord.object=n['anchor']
        fine=ns.new('ShaderNodeTexNoise');fine.inputs['Scale'].default_value=5.5
        fine.inputs['Detail'].default_value=2.2
        links.new(coord.outputs['Object'],fine.inputs['Vector'])
        tone=ns.new('ShaderNodeValToRGB')
        tone.color_ramp.elements[0].color=(.83,.84,.82,1)
        tone.color_ramp.elements[1].color=(1,1,1,1)
        links.new(fine.outputs['Fac'],tone.inputs[0])
        grain_mix=ns.new('ShaderNodeMixRGB');grain_mix.blend_type='MULTIPLY'
        grain_mix.inputs[0].default_value=.44
        if current:links.new(current,grain_mix.inputs[1])
        else:grain_mix.inputs[1].default_value=bs.inputs['Base Color'].default_value
        links.new(tone.outputs[0],grain_mix.inputs[2]);current=grain_mix.outputs[0]
        relief=ns.new('ShaderNodeBump');relief.inputs['Strength'].default_value=.14
        relief.inputs['Distance'].default_value=.012
        links.new(fine.outputs['Fac'],relief.inputs['Height'])
        if bs.inputs['Normal'].is_linked:links.new(bs.inputs['Normal'].links[0].from_socket,relief.inputs['Normal'])
        links.new(relief.outputs['Normal'],bs.inputs['Normal'])
        if material.name.startswith(('Atlas architecture red brick','Study red masonry')):
            uv=ns.new('ShaderNodeUVMap');uv.uv_map='Facade finish frame'
            courses=ns.new('ShaderNodeTexBrick');courses.inputs['Scale'].default_value=1
            courses.inputs['Brick Width'].default_value=.24;courses.inputs['Row Height'].default_value=.075
            courses.inputs['Mortar Size'].default_value=.004
            courses.inputs['Color1'].default_value=(.82,.85,.82,1)
            courses.inputs['Color2'].default_value=(1,1,1,1)
            courses.inputs['Mortar'].default_value=(.62,.66,.62,1)
            links.new(uv.outputs['UV'],courses.inputs['Vector'])
            masonry=ns.new('ShaderNodeMixRGB');masonry.blend_type='MULTIPLY'
            masonry.inputs[0].default_value=.30
            links.new(current,masonry.inputs[1]);links.new(courses.outputs['Color'],masonry.inputs[2])
            current=masonry.outputs[0];brick_finishes.append(material)
        wall_finishes.append(material.name)
    else:paving_finishes.append(material.name)
    contact=ns.new('ShaderNodeAmbientOcclusion');contact.samples=8
    contact.inputs['Distance'].default_value=.85 if wall else 1.20
    weight=ns.new('ShaderNodeMath');weight.operation='MULTIPLY_ADD'
    weight.inputs[1].default_value=.24 if wall else .15
    weight.inputs[2].default_value=.76 if wall else .85
    links.new(contact.outputs['AO'],weight.inputs[0])
    shade=ns.new('ShaderNodeMixRGB');shade.blend_type='MULTIPLY';shade.inputs[0].default_value=1
    if current:links.new(current,shade.inputs[1])
    else:shade.inputs[1].default_value=bs.inputs['Base Color'].default_value
    links.new(weight.outputs[0],shade.inputs[2]);links.new(shade.outputs[0],bs.inputs['Base Color'])
brick_objects=[]
for ob in s.objects:
    if ob.hide_render or ob.type!='MESH' or not any(ob.data.materials[i] in brick_finishes
        for i in {face.material_index for face in ob.data.polygons} if i<len(ob.data.materials)):continue
    me=ob.data;uv=me.uv_layers.get('Facade finish frame') or me.uv_layers.new(name='Facade finish frame')
    normal_matrix=ob.matrix_world.to_3x3().inverted().transposed()
    for face in me.polygons:
        normal=normal_matrix@face.normal;axis=Vector((-normal.y,normal.x,0))
        if axis.length<.01:axis=Vector((1,0,0))
        else:axis.normalize()
        for li in face.loop_indices:
            p=ob.matrix_world@me.vertices[me.loops[li].vertex_index].co
            uv.data[li].uv=(p.dot(axis),p.z)
    brick_objects.append(ob.name)
# Keep the photographed green lake tone, with broader gloss and fine ripples.
# Pond finishes receive the same physical surface scale within fixed outlines.
lake_bs=c['water'].node_tree.nodes.get('Principled BSDF')
lake_bs.inputs['Roughness'].default_value=.105
# Orthographic rays see almost one sky direction on a flat surface. Add
# restrained metre-based pigment/normal variation to the retained water only.
# These are appearance estimates, not measured waves, depth or water quality.
def lake_digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def lake_mesh_state(ob):
    return {'matrix':[list(row) for row in ob.matrix_world],
        'vertices':[list(ob.matrix_world@v.co) for v in ob.data.vertices],
        'faces':[[list(f.vertices),f.material_index] for f in ob.data.polygons],
        'material_slots':[m.name if m else None for m in ob.data.materials],
        'shore_attribute':{'domain':ob.data.attributes['shore_tint'].domain,'data_type':ob.data.attributes['shore_tint'].data_type} if 'shore_tint' in ob.data.attributes else None,
        'hidden':ob.hide_render,
        'shore_tint':[float(v.value) for v in ob.data.attributes['shore_tint'].data]
            if 'shore_tint' in ob.data.attributes else []}
def lake_graph_state(tree):
    def value(v):
        if isinstance(v,(str,bool,int,float)):return v
        if v is None:return None
        if hasattr(v,'name_full'):return v.name_full
        try:return list(v)
        except TypeError:return str(v)
    properties=('operation','blend_type','noise_dimensions','normalize','clamp','attribute_name',
        'vector_type','uv_map','distribution','is_active_output','target','mute',
        'invert','interpolation_type','data_type','from_instancer')
    rows=[]
    for node in sorted(tree.nodes,key=lambda node:node.name):
        row={'name':node.name,'type':node.bl_idname,
            'properties':{key:value(getattr(node,key)) for key in properties if hasattr(node,key)},
            'inputs':[[socket.identifier,value(socket.default_value)] for socket in node.inputs
                if hasattr(socket,'default_value')]}
        if hasattr(node,'color_ramp'):
            ramp=node.color_ramp;row['ramp']={'interpolation':ramp.interpolation,
                'color_mode':ramp.color_mode,'hue_interpolation':ramp.hue_interpolation,
                'elements':[[e.position,list(e.color)] for e in ramp.elements]}
        if getattr(node,'object',None):
            row['object']=[node.object.name,[list(v) for v in node.object.matrix_world]]
        if getattr(node,'image',None):row['image']=[node.image.name,node.image.filepath]
        rows.append(row)
    links=sorted([link.from_node.name,link.from_socket.identifier,link.to_node.name,link.to_socket.identifier]
        for link in tree.links)
    return {'nodes':rows,'links':links}
lake_material=c['water']
lake_objects=sorted([ob for ob in s.objects if ob.type=='MESH' and
    (ob.name.startswith(('Lake water gradient ','Lake continuous water')) or ob.name in
    ('Lake bounded submerged bed','Lake sloped stone revetment','Lake upper coping',
     'Lake upper promenade','Lake outer coping'))],key=lambda ob:ob.name)
lake_before={ob.name:lake_mesh_state(ob) for ob in lake_objects}
lake_other_before={m.name:lake_digest(lake_graph_state(m.node_tree)) for m in bpy.data.materials
    if m!=lake_material and m.use_nodes}
lake_world_before=lake_digest(lake_graph_state(s.world.node_tree))
lake_light_before=lake_digest([[ob.name,list(ob.location),list(ob.rotation_euler),ob.data.energy,
    ob.data.color[:],getattr(ob.data,'angle',None)] for ob in sorted(s.objects,key=lambda ob:ob.name) if ob.type=='LIGHT'])
ns=lake_material.node_tree.nodes;links=lake_material.node_tree.links
def lake_node(kind,name):
    node=ns.new(kind);node.name='Expansion lake '+name;return node
lake_coord=lake_node('ShaderNodeTexCoord','metre coordinates');lake_coord.object=c['anchor']
lake_broad=lake_node('ShaderNodeTexNoise','broad colour');lake_broad.inputs['Scale'].default_value=.028
lake_broad.inputs['Detail'].default_value=2;lake_broad.inputs['Roughness'].default_value=.62
links.new(lake_coord.outputs['Object'],lake_broad.inputs['Vector'])
lake_tone=lake_node('ShaderNodeValToRGB','cool green variation')
lake_tone.color_ramp.elements[0].position=.20;lake_tone.color_ramp.elements[0].color=(.025,.10,.115,1)
lake_tone.color_ramp.elements[1].position=.80;lake_tone.color_ramp.elements[1].color=(.10,.25,.255,1)
links.new(lake_broad.outputs['Fac'],lake_tone.inputs[0])
lake_original_colour=lake_bs.inputs['Base Color'].links[0].from_socket
lake_colour_mix=lake_node('ShaderNodeMixRGB','retained shore colour');lake_colour_mix.inputs[0].default_value=.55
links.new(lake_original_colour,lake_colour_mix.inputs[1]);links.new(lake_tone.outputs['Color'],lake_colour_mix.inputs[2])
links.new(lake_colour_mix.outputs[0],lake_bs.inputs['Base Color'])
lake_direction=lake_node('ShaderNodeVectorMath','directional frame');lake_direction.operation='MULTIPLY'
lake_direction.inputs[1].default_value=(.7,2.4,1)
links.new(lake_coord.outputs['Object'],lake_direction.inputs[0])
lake_wide=lake_node('ShaderNodeTexNoise','wide ripples');lake_wide.inputs['Scale'].default_value=.70
lake_wide.inputs['Detail'].default_value=2;lake_wide.inputs['Roughness'].default_value=.58
links.new(lake_direction.outputs[0],lake_wide.inputs['Vector'])
# A weak crest tint keeps the directional surface readable when the atlas is
# reduced on screen; it is a stylised highlight, not a recorded reflection.
lake_crest_mask=lake_node('ShaderNodeMapRange','bounded crest tint');lake_crest_mask.clamp=True
lake_crest_mask.inputs['From Min'].default_value=.40;lake_crest_mask.inputs['From Max'].default_value=.70
lake_crest_mask.inputs['To Min'].default_value=0;lake_crest_mask.inputs['To Max'].default_value=.18
links.new(lake_wide.outputs['Fac'],lake_crest_mask.inputs['Value'])
lake_crest=lake_node('ShaderNodeMixRGB','subtle ripple tint')
lake_crest.inputs[2].default_value=(.16,.32,.30,1)
links.new(lake_crest_mask.outputs['Result'],lake_crest.inputs[0])
links.new(lake_colour_mix.outputs[0],lake_crest.inputs[1]);links.new(lake_crest.outputs[0],lake_bs.inputs['Base Color'])
lake_wide_bump=lake_node('ShaderNodeBump','wide normals');lake_wide_bump.inputs['Strength'].default_value=.55
lake_wide_bump.inputs['Distance'].default_value=.09
links.new(lake_wide.outputs['Fac'],lake_wide_bump.inputs['Height'])
lake_fine=lake_node('ShaderNodeTexNoise','fine ripples');lake_fine.inputs['Scale'].default_value=1.7
lake_fine.inputs['Detail'].default_value=2;links.new(lake_direction.outputs[0],lake_fine.inputs['Vector'])
lake_fine_bump=lake_node('ShaderNodeBump','fine normals');lake_fine_bump.inputs['Strength'].default_value=.20
lake_fine_bump.inputs['Distance'].default_value=.012
links.new(lake_fine.outputs['Fac'],lake_fine_bump.inputs['Height'])
links.new(lake_wide_bump.outputs['Normal'],lake_fine_bump.inputs['Normal'])
links.new(lake_fine_bump.outputs['Normal'],lake_bs.inputs['Normal'])
lake_rough=lake_node('ShaderNodeMapRange','bounded roughness');lake_rough.clamp=True
lake_rough.inputs['To Min'].default_value=.075;lake_rough.inputs['To Max'].default_value=.135
links.new(lake_wide.outputs['Fac'],lake_rough.inputs['Value']);links.new(lake_rough.outputs['Result'],lake_bs.inputs['Roughness'])
lake_bs.inputs['Transmission Weight'].default_value=.42
lake_after={ob.name:lake_mesh_state(ob) for ob in lake_objects};assert lake_before==lake_after
lake_other_after={m.name:lake_digest(lake_graph_state(m.node_tree)) for m in bpy.data.materials
    if m!=lake_material and m.use_nodes};assert lake_other_before==lake_other_after
assert lake_world_before==lake_digest(lake_graph_state(s.world.node_tree))
assert lake_light_before==lake_digest([[ob.name,list(ob.location),list(ob.rotation_euler),ob.data.energy,
    ob.data.color[:],getattr(ob.data,'angle',None)] for ob in sorted(s.objects,key=lambda ob:ob.name) if ob.type=='LIGHT'])
lake_visible=[ob for ob in lake_objects if not ob.hide_render and lake_material in ob.data.materials[:]]
assert len(lake_visible)==6 and len(lake_objects)==12
lake_footprint=unary_union([Polygon([tuple(ob.matrix_world@ob.data.vertices[i].co)[:2] for i in f.vertices])
    for ob in lake_visible for f in ob.data.polygons])
lake_area_difference=lake_footprint.symmetric_difference(ctx['lake']).area
assert lake_area_difference<1e-6
lake_levels=[(ob.matrix_world@v.co).z for ob in lake_visible for v in ob.data.vertices]
assert max(abs(z+1.1) for z in lake_levels)<1e-6
lake_surface_checks={'material_count':1,'visible_water_mesh_count':len(lake_visible),
    'retained_mesh_count':len(lake_objects),'geometry_sha256':{name:lake_digest(state) for name,state in lake_after.items()},
    'shore_attribute_sha256':lake_digest({name:[state['shore_attribute'],state['shore_tint']] for name,state in lake_after.items()}),
    'material_graph_sha256':lake_digest(lake_graph_state(lake_material.node_tree)),
    'coordinate_anchor_matrix':[list(row) for row in c['anchor'].matrix_world],
    'water_level_m_estimate':lake_levels[0],'source_outline_area_difference_m2':lake_area_difference,
    'world_vertices_topology_material_indices_transforms_and_visibility_preserved':True,
    'shore_tint_preserved':True,'other_material_graphs_preserved':True,'other_material_count':len(lake_other_after),
    'other_material_graphs_sha256':lake_digest(lake_other_after),'world_graph_sha256':lake_world_before,
    'lighting_sha256':lake_light_before,'world_and_lighting_preserved':True,'new_geometry_count':0,
    'displacement_link_count':sum(link.to_socket.name=='Displacement' for link in lake_material.node_tree.links),
    'roughness_range_estimate':[.075,.135],'pigment_mix_estimate':.55,
    'ripple_tint_maximum_estimate':.18,
    'transmission_estimate':float(lake_bs.inputs['Transmission Weight'].default_value),
    'IOR_preserved':abs(lake_bs.inputs['IOR'].default_value-1.333)<1e-6,
    'normal_layer_count':2,'bump_distance_m_estimate':[.09,.012]}
assert lake_surface_checks['displacement_link_count']==0
for material in (pond,pond_edge):
    ns=material.node_tree.nodes;links=material.node_tree.links;bs=ns.get('Principled BSDF')
    coord=ns.new('ShaderNodeTexCoord');coord.object=n['anchor']
    stretch=ns.new('ShaderNodeVectorMath');stretch.operation='MULTIPLY'
    stretch.inputs[1].default_value=(.7,4.5,1)
    ripple=ns.new('ShaderNodeTexNoise');ripple.inputs['Scale'].default_value=2.2;ripple.inputs['Detail'].default_value=2
    bump=ns.new('ShaderNodeBump');bump.inputs['Distance'].default_value=.014;bump.inputs['Strength'].default_value=.13
    links.new(coord.outputs['Object'],stretch.inputs[0]);links.new(stretch.outputs[0],ripple.inputs['Vector'])
    links.new(ripple.outputs['Fac'],bump.inputs['Height'])
    if bs.inputs['Normal'].is_linked:links.new(bs.inputs['Normal'].links[0].from_socket,bump.inputs['Normal'])
    links.new(bump.outputs['Normal'],bs.inputs['Normal'])
    bs.inputs['Roughness'].default_value=.21;bs.inputs['Specular IOR Level'].default_value=.55
photo_supported_central_materials=[name for name in wall_finishes if name.startswith(central_photo_facade_prefixes)]
assert len(photo_supported_central_materials)==8
assert len(wall_finishes)>10 and len(paving_finishes)>=5 and brick_objects
surface_finish_checks={'wall_material_count':len(wall_finishes),'photo_supported_central_material_count':len(photo_supported_central_materials),
    'paving_material_count':len(paving_finishes),
    'brick_object_count':len(brick_objects),'wall_contact_distance_m':.85,
    'paving_contact_distance_m':1.20,'wall_contact_influence':.24,'paving_contact_influence':.15,
    'lake_roughness_unlinked_default':.105,'lake_roughness_range_estimate':[.075,.135],
    'mesh_positions_changed':False}

# Surface relief is shaded within the existing paving/curb meshes. Fine grain
# and mortar depth are presentation parameters; no new path or curb is drawn.
ground_relief_prefixes=paving_prefixes+('Garden warm pale stone','Garden cool paving band',
    'Garden sandstone raised edge','Study light stone curb','Expansion low planting edge')
ground_relief_materials=[];glazing_materials=[]
for material in sorted(visible_materials,key=lambda m:m.name):
    ns=material.node_tree.nodes;links=material.node_tree.links;bs=ns.get('Principled BSDF')
    if not bs:continue
    if material.name.startswith(ground_relief_prefixes):
        coord=ns.new('ShaderNodeTexCoord');coord.object=n['anchor']
        grain=ns.new('ShaderNodeTexNoise');grain.inputs['Scale'].default_value=16
        grain.inputs['Detail'].default_value=2.3;grain.inputs['Roughness'].default_value=.64
        links.new(coord.outputs['Object'],grain.inputs['Vector'])
        pigment=ns.new('ShaderNodeValToRGB')
        pigment.color_ramp.elements[0].color=(.84,.84,.81,1)
        pigment.color_ramp.elements[1].color=(1.03,1.025,1,1)
        links.new(grain.outputs['Fac'],pigment.inputs[0])
        tint=ns.new('ShaderNodeMixRGB');tint.blend_type='MULTIPLY';tint.inputs[0].default_value=.14
        if bs.inputs['Base Color'].is_linked:links.new(bs.inputs['Base Color'].links[0].from_socket,tint.inputs[1])
        else:tint.inputs[1].default_value=bs.inputs['Base Color'].default_value
        links.new(pigment.outputs['Color'],tint.inputs[2]);links.new(tint.outputs[0],bs.inputs['Base Color'])
        brick=next((node for node in ns if node.bl_idname=='ShaderNodeTexBrick'),None)
        relief=grain.outputs['Fac']
        if brick:
            mortar=ns.new('ShaderNodeMath');mortar.operation='SUBTRACT';mortar.inputs[0].default_value=1
            links.new(brick.outputs['Fac'],mortar.inputs[1])
            mix=ns.new('ShaderNodeMixRGB');mix.inputs[0].default_value=.18
            links.new(mortar.outputs[0],mix.inputs[1]);links.new(grain.outputs['Fac'],mix.inputs[2])
            relief=mix.outputs[0]
        bump=ns.new('ShaderNodeBump');bump.inputs['Distance'].default_value=.016
        bump.inputs['Strength'].default_value=.19
        links.new(relief,bump.inputs['Height'])
        if bs.inputs['Normal'].is_linked:links.new(bs.inputs['Normal'].links[0].from_socket,bump.inputs['Normal'])
        links.new(bump.outputs['Normal'],bs.inputs['Normal'])
        ground_relief_materials.append(material.name)
    elif ('glass' in material.name.lower() or 'glazing' in material.name.lower()
          or material.name.startswith(('B06 window reflection ','B07 bluegrey window'))):
        # Camera/normal-derived reflected tone gives existing panes a subtle
        # sky response. It does not paint rooms, blinds or new window openings.
        coord=ns.new('ShaderNodeTexCoord');coord.object=n['anchor']
        axes=ns.new('ShaderNodeSeparateXYZ');links.new(coord.outputs['Reflection'],axes.inputs[0])
        sky=ns.new('ShaderNodeMapRange');sky.clamp=True
        sky.inputs['From Min'].default_value=-.7;sky.inputs['From Max'].default_value=.8
        links.new(axes.outputs['Z'],sky.inputs['Value'])
        sky_color=ns.new('ShaderNodeValToRGB')
        sky_color.color_ramp.elements[0].color=(.10,.14,.145,1)
        sky_color.color_ramp.elements[1].color=(.29,.36,.365,1)
        links.new(sky.outputs['Result'],sky_color.inputs[0])
        facing=ns.new('ShaderNodeLayerWeight');facing.inputs['Blend'].default_value=.30
        weight=ns.new('ShaderNodeMath');weight.operation='MULTIPLY_ADD'
        weight.inputs[1].default_value=.35;weight.inputs[2].default_value=.12
        links.new(facing.outputs['Facing'],weight.inputs[0])
        reflect=ns.new('ShaderNodeMixRGB')
        if bs.inputs['Base Color'].is_linked:links.new(bs.inputs['Base Color'].links[0].from_socket,reflect.inputs[1])
        else:reflect.inputs[1].default_value=bs.inputs['Base Color'].default_value
        links.new(weight.outputs[0],reflect.inputs[0]);links.new(sky_color.outputs['Color'],reflect.inputs[2])
        links.new(reflect.outputs[0],bs.inputs['Base Color'])
        bs.inputs['Roughness'].default_value=.23
        bs.inputs['Specular IOR Level'].default_value=.55
        # The existing surround and sill supply the recess shadow. Keep the
        # pane positions and reflected sky palette, shading only their contact.
        recess=ns.new('ShaderNodeAmbientOcclusion');recess.samples=4
        recess.inputs['Distance'].default_value=.24
        recess_weight=ns.new('ShaderNodeMath');recess_weight.operation='MULTIPLY_ADD'
        recess_weight.inputs[1].default_value=.22;recess_weight.inputs[2].default_value=.78
        links.new(recess.outputs['AO'],recess_weight.inputs[0])
        pane_shade=ns.new('ShaderNodeMixRGB');pane_shade.blend_type='MULTIPLY';pane_shade.inputs[0].default_value=1
        links.new(reflect.outputs[0],pane_shade.inputs[1]);links.new(recess_weight.outputs[0],pane_shade.inputs[2])
        links.new(pane_shade.outputs[0],bs.inputs['Base Color'])
        pane_edge=ns.new('ShaderNodeBevel');pane_edge.samples=2;pane_edge.inputs['Radius'].default_value=.009
        if bs.inputs['Normal'].is_linked:links.new(bs.inputs['Normal'].links[0].from_socket,pane_edge.inputs['Normal'])
        links.new(pane_edge.outputs['Normal'],bs.inputs['Normal'])
        glazing_materials.append(material.name)
assert len(ground_relief_materials)>=8 and len(glazing_materials)>=4
finish_relief_checks={'ground_material_count':len(ground_relief_materials),
    'glazing_material_count':len(glazing_materials),'relief_distance_m_estimate':.016,
    'relief_strength':.19,'glazing_roughness':.23,'mesh_positions_changed':False}

# Finish only retained photo/satellite-backed solar groups. Their original
# vertices, object matrices, counts and source roof footprints remain intact.
solar_materials=sorted((material for material in visible_materials if material.name.startswith(
    ('B07 solar cells','Atlas architecture source visible solar panels'))),key=lambda material:material.name)
solar_objects=[]
for ob in s.objects:
    if ob.hide_render or ob.type!='MESH':continue
    me=ob.data;slots={i for i,material in enumerate(me.materials) if material in solar_materials}
    panel_faces=[face for face in me.polygons if face.material_index in slots]
    if not panel_faces:continue
    before=[tuple(ob.matrix_world@v.co) for v in me.vertices]
    before_faces=[(tuple(face.vertices),face.material_index) for face in me.polygons]
    normal_matrix=ob.matrix_world.to_3x3().inverted().transposed()
    upper=[face for face in panel_faces if abs((normal_matrix@face.normal).z)>.5]
    assert upper,ob.name
    footprint=unary_union([Polygon([before[i][:2] for i in face.vertices]) for face in upper])
    rectangle=list(footprint.minimum_rotated_rectangle.exterior.coords)[:-1]
    a,b=max(zip(rectangle,rectangle[1:]+rectangle[:1]),key=lambda pair:Point(pair[0]).distance(Point(pair[1])))
    axis=Vector((b[0]-a[0],b[1]-a[1],0)).normalized()
    normal=(normal_matrix@max(upper,key=lambda face:face.area).normal).normalized()
    if normal.z<0:normal=-normal
    axis=(axis-normal*axis.dot(normal)).normalized();cross=normal.cross(axis).normalized()
    origin=Vector(before[upper[0].vertices[0]])
    if not ob.name.startswith('B07'):
        # Match E24's retained world-X/Y 2m by 3m geometric seams.
        axis,cross,origin=Vector((1,0,0)),Vector((0,1,0)),Vector((0,0,0))
    uv=me.uv_layers.get('Solar finish frame') or me.uv_layers.new(name='Solar finish frame')
    for face in panel_faces:
        local_axis,local_cross,local_origin=axis,cross,origin
        if ob.name.startswith('B07'):
            # Retained individual modules have their own slope and frame.
            points=[Vector(before[i]) for i in face.vertices]
            edge=max((b-a for a,b in zip(points,points[1:]+points[:1])),key=lambda v:v.length)
            face_normal=(normal_matrix@face.normal).normalized()
            if face_normal.z<0:face_normal=-face_normal
            local_cross=edge.normalized();local_axis=local_cross.cross(face_normal).normalized()
            local_origin=points[0]
        for li in face.loop_indices:
            delta=Vector(before[me.loops[li].vertex_index])-local_origin
            uv.data[li].uv=(delta.dot(local_axis),delta.dot(local_cross))
    positions_preserved=before==[tuple(ob.matrix_world@v.co) for v in me.vertices]
    topology_preserved=before_faces==[(tuple(face.vertices),face.material_index) for face in me.polygons]
    assert positions_preserved and topology_preserved,ob.name
    solar_objects.append({'name':ob.name,'source_id':'B07' if ob.name.startswith('B07') else ob['source_id'],
        'basis':'Retained photo-visible array' if ob.name.startswith('B07') else 'Existing satellite-traced rooftop array',
        'panel_face_count':len(panel_faces),'upper_face_count':len(upper),'source_array_area_m2':footprint.area,
        'geometry_sha256':hashlib.sha256(json.dumps([before,before_faces],separators=(',',':')).encode()).hexdigest(),
        'world_positions_preserved':positions_preserved,'topology_preserved':topology_preserved})
for material in solar_materials:
    ns=material.node_tree.nodes;links=material.node_tree.links;bs=ns.get('Principled BSDF')
    uv=ns.new('ShaderNodeUVMap');uv.uv_map='Solar finish frame'
    cells=ns.new('ShaderNodeTexBrick');cells.offset=0;cells.inputs['Scale'].default_value=1
    cells.inputs['Brick Width'].default_value=.17;cells.inputs['Row Height'].default_value=.17
    cells.inputs['Mortar Size'].default_value=.003
    cells.inputs['Color1'].default_value=(.012,.024,.042,1)
    cells.inputs['Color2'].default_value=(.018,.035,.055,1)
    cells.inputs['Mortar'].default_value=(.055,.070,.080,1)
    links.new(uv.outputs['UV'],cells.inputs['Vector'])
    modules=ns.new('ShaderNodeTexBrick');modules.offset=0;modules.inputs['Scale'].default_value=1
    modules.inputs['Brick Width'].default_value=2;modules.inputs['Row Height'].default_value=3
    modules.inputs['Mortar Size'].default_value=.012
    links.new(uv.outputs['UV'],modules.inputs['Vector'])
    joint=ns.new('ShaderNodeMixRGB');joint.inputs[2].default_value=(.10,.12,.13,1)
    links.new(modules.outputs['Fac'],joint.inputs[0]);links.new(cells.outputs['Color'],joint.inputs[1])
    # B07 already retains a geometric frame around every source module.
    links.new(cells.outputs['Color'] if material.name.startswith('B07') else joint.outputs[0],bs.inputs['Base Color'])
    grain=ns.new('ShaderNodeTexNoise');grain.inputs['Scale'].default_value=18;grain.inputs['Detail'].default_value=1.5
    links.new(uv.outputs['UV'],grain.inputs['Vector'])
    rough=ns.new('ShaderNodeMapRange');rough.inputs['To Min'].default_value=.38;rough.inputs['To Max'].default_value=.50
    links.new(grain.outputs['Fac'],rough.inputs['Value']);links.new(rough.outputs['Result'],bs.inputs['Roughness'])
    bs.inputs['Metallic'].default_value=.08;bs.inputs['Specular IOR Level'].default_value=.30
    bump=ns.new('ShaderNodeBump');bump.inputs['Distance'].default_value=.002;bump.inputs['Strength'].default_value=.12
    links.new(cells.outputs['Fac'],bump.inputs['Height'])
    links.new(bump.outputs['Normal'],bs.inputs['Normal'])
assert len(solar_materials)>=2 and {row['source_id'] for row in solar_objects}=={'B07','E24'}
solar_finish_checks={'material_count':len(solar_materials),'retained_mesh_count':len(solar_objects),
    'source_ids':['B07','E24'],'cell_m_estimate':.17,'E24_retained_module_m_estimate':[2,3],'E24_seams_aligned_to_existing_world_grid':True,
    'world_positions_preserved':all(row['world_positions_preserved'] for row in solar_objects),
    'topology_preserved':all(row['topology_preserved'] for row in solar_objects)}
glazing_recess_checks={'material_count':len(glazing_materials),'contact_distance_m_estimate':.24,
    'contact_influence':.22,'edge_radius_m_estimate':.009,'samples':2,'mesh_positions_changed':False,
    'existing_reflection_palette_preserved':True}
# Small normal-only edge catches on the existing facade/trim meshes soften
# unnaturally sharp paper-like corners without changing a traced roof or wall.
architectural_edge_materials=[]
for material in sorted(visible_materials,key=lambda m:m.name):
    if not material.name.startswith(wall_prefixes):continue
    ns=material.node_tree.nodes;links=material.node_tree.links;bs=ns.get('Principled BSDF')
    bevel=ns.new('ShaderNodeBevel');bevel.samples=2;bevel.inputs['Radius'].default_value=.035
    if bs.inputs['Normal'].is_linked:links.new(bs.inputs['Normal'].links[0].from_socket,bevel.inputs['Normal'])
    links.new(bevel.outputs['Normal'],bs.inputs['Normal']);architectural_edge_materials.append(material.name)
assert len(architectural_edge_materials)==len(wall_finishes)
canopy_prefixes=('Pilot source-tree canopy ','Garden source-tree canopy image ',
    'Garden wider source-tree canopy ','Garden source oval shrub canopy ')
crowns=sorted((ob for ob in s.objects if not ob.hide_render and ob.name.startswith(canopy_prefixes)),key=lambda ob:ob.name)
# Twelve shared crown forms break the repeated central mound in the retained
# leaf cutout. Only presentation meshes change: source trees, object XYZ,
# rotation and scale remain untouched. Low forms are reserved for the eight
# existing shrubs, not interpreted as new trees or measured species.
form_peaks=((.54,.56,.52),(.58,.62,.65),(.48,.52,.50),(.38,.42,.40))
form_names=('broad','offset','split','low_lobed')
form_meshes={};form_fingerprints={};form_usage={};assignment_rows=[]
minimum_uv_turn=1;maximum_uv_displacement=0;boundary_uv_preserved=True
def uv_cross(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
def crown_form(base,family,variant):
    global minimum_uv_turn,maximum_uv_displacement,boundary_uv_preserved
    key=(base.as_pointer(),family,variant)
    if key in form_meshes:return form_meshes[key]
    mesh=base.copy();mesh.name='Expansion crown '+form_names[family]+' '+str(variant)
    phase=variant*1.9+family*.7;co,si=math.cos(phase),math.sin(phase)
    heights=[]
    for v in mesh.vertices:
        x,y=v.co.x,v.co.y;edge=max(0,1-2.4*(x*x+y*y))**1.4
        def lobe(a,b,sx,sy):return math.exp(-((x-a)/sx)**2-((y-b)/sy)**2)
        if family==0:h=.25+.72*lobe(.06*co,.05*si,.34,.29)
        elif family==1:h=.18+.90*lobe(.14*co,.12*si,.27,.30)
        elif family==2:h=.20+.72*lobe(.18*co,.18*si,.19,.19)+.68*lobe(-.18*co,-.18*si,.16,.20)
        else:h=.18+.44*sum(lobe(.22*math.cos(phase+k*math.tau/3),.22*math.sin(phase+k*math.tau/3),.15,.15) for k in range(3))
        heights.append(max(0,(h+.022*math.sin(13*x+phase)*math.cos(11*y-phase))*edge))
    height_scale=form_peaks[family][variant]/max(heights)
    for v,h in zip(mesh.vertices,heights):v.co.z=h*height_scale
    uv=mesh.uv_layers.active;original_uv=base.uv_layers.active
    for face in mesh.polygons:
        for li in face.loop_indices:
            old=original_uv.data[li].uv;u,v=float(old.x),float(old.y)
            if u in (0,1) or v in (0,1):mapped=(u,v)
            else:
                w=math.sin(math.pi*u)*math.sin(math.pi*v)
                mapped=(u+.032*w*math.sin(math.tau*v+phase),v+.026*w*math.cos(math.tau*u+phase*.85))
            uv.data[li].uv=mapped;actual=tuple(uv.data[li].uv)
            assert all(math.isfinite(q) and 0<=q<=1 for q in actual)
            maximum_uv_displacement=max(maximum_uv_displacement,math.dist(actual,(u,v)))
            if u in (0,1) or v in (0,1):
                boundary_uv_preserved &= actual==(u,v)
            assert tuple(mesh.vertices[mesh.loops[li].vertex_index].co)[:2]==tuple(base.vertices[base.loops[li].vertex_index].co)[:2]
        q=[tuple(uv.data[li].uv) for li in face.loop_indices]
        turns=[uv_cross(q[i],q[(i+1)%4],q[(i+2)%4]) for i in range(4)]+[uv_cross(q[0],q[1],q[2]),uv_cross(q[0],q[2],q[3])]
        assert min(turns)>.005,turns
        minimum_uv_turn=min(minimum_uv_turn,*turns)
    mesh.update()
    ident=form_names[family]+'_'+str(variant)
    content={'vertices':[list(v.co) for v in mesh.vertices],'faces':[list(f.vertices) for f in mesh.polygons],
             'uv':[list(loop.uv) for loop in uv.data]}
    fingerprint=hashlib.sha256(json.dumps(content,separators=(',',':')).encode()).hexdigest()
    if ident in form_fingerprints:assert form_fingerprints[ident]==fingerprint
    form_fingerprints[ident]=fingerprint;form_meshes[key]=mesh
    return mesh
for ob in crowns:
    category=next(prefix for prefix in canopy_prefixes if ob.name.startswith(prefix)).strip()
    source_xy=[round(float(v),6) for v in ob['source_position_xy']]
    seed=hashlib.sha256(json.dumps([category,source_xy],separators=(',',':')).encode()).digest()
    family=3 if category=='Garden source oval shrub canopy' else int.from_bytes(seed[:4],'big')%3
    variant=int.from_bytes(seed[4:8],'big')%3
    transform=[list(ob.location),list(ob.rotation_euler),list(ob.scale)]
    assert ob.parent is None
    ob.data=crown_form(ob.data,family,variant)
    assert transform==[list(ob.location),list(ob.rotation_euler),list(ob.scale)]
    ident=form_names[family]+'_'+str(variant);ob['canopy_form']=ident
    form_usage[ident]=form_usage.get(ident,0)+1
    assignment_rows.append([category,source_xy,ident,transform])
assert boundary_uv_preserved and maximum_uv_displacement<.055
assert len(form_fingerprints)==12 and sum(form_usage.values())==1858
assert sum(v for k,v in form_usage.items() if k.startswith('low_lobed'))==8
form_assignment_sha256=hashlib.sha256(json.dumps(sorted(assignment_rows,key=lambda r:json.dumps(r,separators=(',',':'))),separators=(',',':')).encode()).hexdigest()
canopy_form_checks={'form_count':12,'shared_mesh_count':len(form_meshes),'crown_count':len(crowns),
    'source_centres_and_object_transforms_preserved':True,'mesh_vertex_xy_preserved':True,
    'boundary_uv_preserved':boundary_uv_preserved,'minimum_uv_triangle_and_corner_cross':minimum_uv_turn,
    'maximum_uv_displacement':maximum_uv_displacement,'uv_displacement_limit':.055,
    'prototype_sha256':form_fingerprints,'assignment_sha256':form_assignment_sha256,'form_usage':form_usage}
canopy_rows=[]
for ob in crowns:
    expected=ob['source_position_xy']
    assert all(abs(ob.location[i]-expected[i])<1e-6 for i in range(2)),ob.name
    if 'source_tree' in ob:
        original=s.objects[ob['source_tree']].matrix_world.translation
        assert all(abs(ob.location[i]-original[i])<1e-6 for i in range(2)),ob.name
    assert len(ob.data.vertices)==121 and len(ob.data.polygons)==100
    assert all(-.500001<=v.co.x<=.500001 and -.500001<=v.co.y<=.500001 for v in ob.data.vertices)
    canopy_rows.append([ob.name,list(ob.location)[:2],list(ob.scale)[:2]])
expected_crowns=north_detail_checks['source_tree_canopy_count']+garden_detail_checks['source_tree_sprite_count']+garden_detail_checks['wider_source_tree_sprite_count']+garden_detail_checks['source_oval_shrubs']
assert len(crowns)==expected_crowns==1858
canopy_relief_checks={'count':len(crowns),'source_xy_centres_preserved':True,
    'xy_footprint_recipe_preserved':True,'stable_source_coordinate_order':True,'mesh_vertices_per_prototype':121,'mesh_faces_per_prototype':100,
    'maximum_local_z_m_estimate':max(v.co.z*ob.scale.z for ob in crowns for v in ob.data.vertices),
    'positions_and_xy_scale_sha256':hashlib.sha256(json.dumps(canopy_rows,separators=(',',':')).encode()).hexdigest()}
# Retained cutouts keep their pigment/alpha. Reduced emission lets existing
# normals respond to daylight. A bounded value range lifts sunlit foliage
# without a costly scattering pass through overlapping alpha cutouts.
canopy_daylight_materials=sorted({m for ob in crowns for m in ob.data.materials if m},key=lambda m:m.name)
for material in canopy_daylight_materials:
    bs=next(node for node in material.node_tree.nodes if node.bl_idname=='ShaderNodeBsdfPrincipled')
    bs.inputs['Emission Strength'].default_value=.015
    bs.inputs['Roughness'].default_value=.78
    hsv=next(node for node in material.node_tree.nodes if node.bl_idname=='ShaderNodeHueSaturation')
    leaf_value=hsv.inputs['Value'].links[0].from_node
    leaf_value.inputs['To Min'].default_value=1.08
    leaf_value.inputs['To Max'].default_value=1.42
# Preserve the established source pigment, adding small surface-scale detail
# rather than the photograph's second set of cast shadows or extra objects.
flat_roof_prefixes=('Atlas architecture mineral flat roof','Atlas architecture weathered dark flat roof',
    'Study roof mineral','Pilot warm mineral roof courses','Weathered flat roof')
meadow_prefixes=('Garden varied meadow','Expansion north source meadow','Atlas meadow',
    'Pilot aerial finish Study landscape base','Pilot aerial finish Study planted bed ground',
    'Pilot aerial finish Study source woodland ground')
fine_roof_materials=[];fine_meadow_materials=[]
for material in sorted(visible_materials,key=lambda m:m.name):
    roof_finish=material.name.startswith(flat_roof_prefixes)
    meadow_finish=material.name.startswith(meadow_prefixes)
    if not (roof_finish or meadow_finish):continue
    ns=material.node_tree.nodes;links=material.node_tree.links;bs=ns.get('Principled BSDF')
    if not bs:continue
    coord=ns.new('ShaderNodeTexCoord');coord.object=n['anchor']
    grain=ns.new('ShaderNodeTexNoise');grain.inputs['Scale'].default_value=12 if roof_finish else 8
    grain.inputs['Detail'].default_value=2.2;grain.inputs['Roughness'].default_value=.62
    links.new(coord.outputs['Object'],grain.inputs['Vector'])
    tone=ns.new('ShaderNodeValToRGB')
    tone.color_ramp.elements[0].color=(.90,.915,.90,1) if roof_finish else (.89,.93,.87,1)
    tone.color_ramp.elements[1].color=(1.035,1.03,1.015,1) if roof_finish else (1.025,1.045,1.015,1)
    links.new(grain.outputs['Fac'],tone.inputs[0])
    tint=ns.new('ShaderNodeMixRGB');tint.blend_type='MULTIPLY'
    tint.inputs[0].default_value=.40 if roof_finish else .28
    if bs.inputs['Base Color'].is_linked:links.new(bs.inputs['Base Color'].links[0].from_socket,tint.inputs[1])
    else:tint.inputs[1].default_value=bs.inputs['Base Color'].default_value
    links.new(tone.outputs[0],tint.inputs[2]);links.new(tint.outputs[0],bs.inputs['Base Color'])
    relief=grain.outputs['Fac']
    if roof_finish:
        courses=next((node for node in ns if node.bl_idname=='ShaderNodeTexBrick'),None)
        if courses:
            recessed=ns.new('ShaderNodeMath');recessed.operation='SUBTRACT';recessed.inputs[0].default_value=1
            links.new(courses.outputs['Fac'],recessed.inputs[1])
            height=ns.new('ShaderNodeMixRGB');height.inputs[0].default_value=.20
            links.new(recessed.outputs[0],height.inputs[1]);links.new(grain.outputs['Fac'],height.inputs[2])
            relief=height.outputs[0]
        rough=ns.new('ShaderNodeMapRange');rough.inputs['To Min'].default_value=.77;rough.inputs['To Max'].default_value=.91
        links.new(grain.outputs['Fac'],rough.inputs['Value']);links.new(rough.outputs['Result'],bs.inputs['Roughness'])
        fine_roof_materials.append(material.name)
    else:fine_meadow_materials.append(material.name)
    bump=ns.new('ShaderNodeBump');bump.inputs['Distance'].default_value=.010 if roof_finish else .022
    bump.inputs['Strength'].default_value=.22 if roof_finish else .18
    links.new(relief,bump.inputs['Height'])
    if bs.inputs['Normal'].is_linked:links.new(bs.inputs['Normal'].links[0].from_socket,bump.inputs['Normal'])
    links.new(bump.outputs['Normal'],bs.inputs['Normal'])
assert len(fine_roof_materials)>=4 and len(fine_meadow_materials)>=3
fine_surface_checks={'flat_roof_material_count':len(fine_roof_materials),'meadow_material_count':len(fine_meadow_materials),
    'roof_relief_m_estimate':.010,'meadow_relief_m_estimate':.022,'mesh_positions_changed':False,
    'existing_meadow_source_palette_preserved':True,'paving_photo_influence':.34,
    'north_courtyard_photo_influence':.34,'north_apron_photo_influence':.38}

# The retained central meshes keep their photo-visible roof ribs, seams and
# fixtures. Only their surface coordinates/normals change here. Tiled slopes
# use metre coordinates along the actual eave and up the actual roof plane;
# the two B08 bars follow the first edge of their fixed photo-traced outlines.
central_roof_names={'B06 warm metal roof','Weathered flat roof',
    'B07 tiled hip roof','B08 standing seam roof'}
central_roof_materials=sorted((m for m in visible_materials if m.name in central_roof_names),key=lambda m:m.name)
assert {m.name for m in central_roof_materials}==central_roof_names
central_roof_objects=[]
z_axis=Vector((0,0,1))
b08_axes={}
for label,a,b in [('low',(845,424),(1086,441)),('high',(838,280),(1218,301))]:
    b08_axes[label]=(c['pt'](b,0)-c['pt'](a,0)).normalized()
for ob in sorted(s.objects,key=lambda ob:ob.name):
    if ob.hide_render or ob.type!='MESH' or not ob.name.startswith(('B06 Central','B07 Central','B08 Central')):continue
    me=ob.data;slots={i for i,m in enumerate(me.materials) if m in central_roof_materials}
    roof_polys=[face for face in me.polygons if face.material_index in slots]
    assert roof_polys,ob.name
    before=[tuple(ob.matrix_world@v.co) for v in me.vertices]
    before_faces=[(tuple(face.vertices),face.material_index) for face in me.polygons]
    uv=me.uv_layers.get('Central roof finish frame') or me.uv_layers.new(name='Central roof finish frame')
    normal_matrix=ob.matrix_world.to_3x3().inverted().transposed()
    checks_uv=[];upper_count=0
    for face in roof_polys:
        normal=(normal_matrix@face.normal).normalized()
        if normal.z<0:normal=-normal
        points=[Vector(before[i]) for i in face.vertices]
        if ob.name.startswith('B08'):
            axis=b08_axes['low' if sum(p.z for p in points)/len(points)<20 else 'high']
        elif ob.name.startswith('B07') and abs(normal.z)<.999:
            axis=z_axis.cross(normal).normalized()
            if axis.x<0 or (abs(axis.x)<1e-8 and axis.y<0):axis=-axis
        else:
            edge=max((b-a for a,b in zip(points,points[1:]+points[:1])),key=lambda v:v.x*v.x+v.y*v.y)
            axis=Vector((edge.x,edge.y,0)).normalized()
            if axis.x<0 or (abs(axis.x)<1e-8 and axis.y<0):axis=-axis
        # Vertical roof fascia still receives a deterministic coordinate frame.
        if abs(normal.z)>.5:
            axis=(axis-normal*axis.dot(normal)).normalized();cross=normal.cross(axis).normalized()
            upper_count+=1
            checks_uv.append(max(abs(axis.dot(normal)),abs(cross.dot(normal)),abs(axis.dot(cross)),abs(axis.length-1),abs(cross.length-1)))
        else:cross=z_axis
        for li in face.loop_indices:
            p=Vector(before[me.loops[li].vertex_index]);uv.data[li].uv=(p.dot(axis),p.dot(cross))
    positions_preserved=before==[tuple(ob.matrix_world@v.co) for v in me.vertices]
    topology_preserved=before_faces==[(tuple(face.vertices),face.material_index) for face in me.polygons]
    assert positions_preserved and topology_preserved and upper_count and max(checks_uv)<1e-5,ob.name
    central_roof_objects.append({'name':ob.name,'source_id':ob.name[:3],
        'roof_materials':sorted({me.materials[p.material_index].name for p in roof_polys}),
        'roof_face_count':len(roof_polys),'upper_face_count':upper_count,
        'geometry_sha256':hashlib.sha256(json.dumps([before,before_faces],separators=(',',':')).encode()).hexdigest(),
        'world_positions_preserved':positions_preserved,'topology_preserved':topology_preserved,
        'maximum_tangent_frame_error':max(checks_uv)})
for material in central_roof_materials:
    ns=material.node_tree.nodes;links=material.node_tree.links;bs=ns.get('Principled BSDF')
    uv=ns.new('ShaderNodeUVMap');uv.uv_map='Central roof finish frame'
    is_tile=material.name.startswith('B07');is_flat=material.name=='Weathered flat roof'
    if is_tile:
        courses=next(node for node in ns if node.bl_idname=='ShaderNodeTexBrick')
        links.new(uv.outputs['UV'],courses.inputs['Vector'])
        # Keep the retained tile size/pigment; mortar is recessed, tile raised.
        raised=ns.new('ShaderNodeMath');raised.operation='SUBTRACT';raised.inputs[0].default_value=1
        links.new(courses.outputs['Fac'],raised.inputs[1])
        bump=next(node for node in ns if node.bl_idname=='ShaderNodeBump')
        links.new(raised.outputs[0],bump.inputs['Height'])
    if not is_flat:
        stretch=ns.new('ShaderNodeVectorMath');stretch.operation='MULTIPLY'
        stretch.inputs[1].default_value=(3,3,1) if is_tile else (.7,14,1)
        links.new(uv.outputs['UV'],stretch.inputs[0])
        grain=ns.new('ShaderNodeTexNoise');grain.inputs['Scale'].default_value=1;grain.inputs['Detail'].default_value=2
        links.new(stretch.outputs[0],grain.inputs['Vector'])
        tone=ns.new('ShaderNodeValToRGB')
        tone.color_ramp.elements[0].color=(.91,.92,.90,1)
        tone.color_ramp.elements[1].color=(1.025,1.02,1.015,1)
        pigment=ns.new('ShaderNodeMixRGB');pigment.blend_type='MULTIPLY';pigment.inputs[0].default_value=.26
        links.new(grain.outputs['Fac'],tone.inputs[0]);links.new(tone.outputs[0],pigment.inputs[2])
        links.new(bs.inputs['Base Color'].links[0].from_socket,pigment.inputs[1])
        links.new(pigment.outputs[0],bs.inputs['Base Color'])
        rough=ns.new('ShaderNodeMapRange')
        rough.inputs['To Min'].default_value=.77 if is_tile else .43
        rough.inputs['To Max'].default_value=.91 if is_tile else .59
        links.new(grain.outputs['Fac'],rough.inputs['Value']);links.new(rough.outputs[0],bs.inputs['Roughness'])
        if not is_tile:
            bump=ns.new('ShaderNodeBump');bump.inputs['Distance'].default_value=.003;bump.inputs['Strength'].default_value=.12
            links.new(grain.outputs['Fac'],bump.inputs['Height'])
            if bs.inputs['Normal'].is_linked:links.new(bs.inputs['Normal'].links[0].from_socket,bump.inputs['Normal'])
            links.new(bump.outputs['Normal'],bs.inputs['Normal'])
    contact=ns.new('ShaderNodeAmbientOcclusion');contact.samples=4;contact.inputs['Distance'].default_value=.45
    weight=ns.new('ShaderNodeMath');weight.operation='MULTIPLY_ADD';weight.inputs[1].default_value=.18;weight.inputs[2].default_value=.82
    links.new(contact.outputs['AO'],weight.inputs[0])
    shade=ns.new('ShaderNodeMixRGB');shade.blend_type='MULTIPLY';shade.inputs[0].default_value=1
    links.new(bs.inputs['Base Color'].links[0].from_socket,shade.inputs[1]);links.new(weight.outputs[0],shade.inputs[2])
    links.new(shade.outputs[0],bs.inputs['Base Color'])
    bevel=ns.new('ShaderNodeBevel');bevel.samples=2;bevel.inputs['Radius'].default_value=.018
    if bs.inputs['Normal'].is_linked:links.new(bs.inputs['Normal'].links[0].from_socket,bevel.inputs['Normal'])
    links.new(bevel.outputs['Normal'],bs.inputs['Normal'])
central_roof_checks={'material_count':len(central_roof_materials),'retained_mesh_count':len(central_roof_objects),
    'source_ids':['B06','B07','B08'],'world_positions_preserved':True,'topology_preserved':True,
    'maximum_tangent_frame_error':max(row['maximum_tangent_frame_error'] for row in central_roof_objects),
    'contact_distance_m_estimate':.45,'contact_influence':.18,'normal_edge_radius_m_estimate':.018,
    'existing_roof_seams_and_fixtures_preserved':True,'new_geometry_count':0}

# Short-range contact on actual used curb/stone-bank materials, including the
# reused central lake treads. Source outlines and water remain unchanged.
stone_contact_prefixes=('Study light stone curb','Atlas granite edge','Garden sandstone raised edge',
    'Expansion low planting edge','Garden eastern pond stone bank')
stone_contact_materials=[]
for material in sorted(visible_materials,key=lambda m:m.name):
    if not material.name.startswith(stone_contact_prefixes):continue
    ns=material.node_tree.nodes;links=material.node_tree.links;bs=ns.get('Principled BSDF')
    contact=ns.new('ShaderNodeAmbientOcclusion');contact.samples=4;contact.inputs['Distance'].default_value=.32
    weight=ns.new('ShaderNodeMath');weight.operation='MULTIPLY_ADD';weight.inputs[1].default_value=.16;weight.inputs[2].default_value=.84
    links.new(contact.outputs['AO'],weight.inputs[0])
    shade=ns.new('ShaderNodeMixRGB');shade.blend_type='MULTIPLY';shade.inputs[0].default_value=1
    if bs.inputs['Base Color'].is_linked:links.new(bs.inputs['Base Color'].links[0].from_socket,shade.inputs[1])
    else:shade.inputs[1].default_value=bs.inputs['Base Color'].default_value
    links.new(weight.outputs[0],shade.inputs[2]);links.new(shade.outputs[0],bs.inputs['Base Color'])
    bevel=ns.new('ShaderNodeBevel');bevel.samples=2;bevel.inputs['Radius'].default_value=.012
    if bs.inputs['Normal'].is_linked:links.new(bs.inputs['Normal'].links[0].from_socket,bevel.inputs['Normal'])
    links.new(bevel.outputs['Normal'],bs.inputs['Normal']);stone_contact_materials.append(material.name)
assert len(stone_contact_materials)>=3
stone_contact_checks={'material_count':len(stone_contact_materials),'contact_distance_m_estimate':.32,
    'contact_influence':.16,'normal_edge_radius_m_estimate':.012,'mesh_positions_changed':False,'new_geometry_count':0}

# Satellite pigment is coarser than the atlas. Keep its original geographic
# colour/dryness branch, adding metre-scale grass detail visible after reduction.
# Warm source patches and woodland receive less green than open green lawns.
meadow_materials=sorted((m for m in visible_materials if m.name in fine_meadow_materials),key=lambda m:m.name)
assert len(meadow_materials)==4
def meadow_graph_state(tree):
    state=lake_graph_state(tree)
    for row in state['nodes']:
        node=tree.nodes[row['name']]
        for key in ('mode','interpolation','projection','extension'):
            if hasattr(node,key):row['properties'][key]=getattr(node,key)
        if getattr(node,'image',None):row['image'].append(node.image.colorspace_settings.name)
    return state
def meadow_mesh_state(ob):
    return {'matrix':[list(row) for row in ob.matrix_world],
        'vertices':[list(ob.matrix_world@v.co) for v in ob.data.vertices],
        'faces':[[list(f.vertices),f.material_index] for f in ob.data.polygons],
        'material_slots':[m.name if m else None for m in ob.data.materials],
        'uv':{uv.name:[list(v.uv) for v in uv.data] for uv in ob.data.uv_layers},
        'hidden':ob.hide_render}
meadow_objects=sorted((ob for ob in s.objects if ob.type=='MESH' and not ob.hide_render and
    any(ob.data.materials[i] in meadow_materials for i in {f.material_index for f in ob.data.polygons}
        if i<len(ob.data.materials))),key=lambda ob:ob.name)
meadow_geometry_before={ob.name:lake_digest(meadow_mesh_state(ob)) for ob in meadow_objects}
meadow_object_names=sorted(ob.name for ob in s.objects)
meadow_other_before={m.name:lake_digest(meadow_graph_state(m.node_tree)) for m in bpy.data.materials
    if m not in meadow_materials and m.use_nodes}
meadow_world_before=lake_digest(meadow_graph_state(s.world.node_tree))
meadow_lights_before=lake_digest([[ob.name,list(ob.location),list(ob.rotation_euler),ob.data.energy,
    ob.data.color[:],getattr(ob.data,'angle',None)] for ob in sorted(s.objects,key=lambda ob:ob.name) if ob.type=='LIGHT'])
meadow_original_graphs={m.name:meadow_graph_state(m.node_tree) for m in meadow_materials}
meadow_recipes=[]
for material in meadow_materials:
    ns=material.node_tree.nodes;links=material.node_tree.links;bs=ns.get('Principled BSDF')
    original_colour=bs.inputs['Base Color'].links[0].from_socket
    def meadow_node(kind,name):
        node=ns.new(kind);node.name='Expansion meadow '+name;return node
    coord=meadow_node('ShaderNodeTexCoord','metre coordinates');coord.object=n['anchor']
    grain=meadow_node('ShaderNodeTexNoise','visible grass variation')
    grain.inputs['Scale'].default_value=1.3;grain.inputs['Detail'].default_value=2.5
    grain.inputs['Roughness'].default_value=.62
    links.new(coord.outputs['Object'],grain.inputs['Vector'])
    rgb=meadow_node('ShaderNodeSeparateColor','retained source channels');rgb.mode='RGB'
    links.new(original_colour,rgb.inputs[0])
    green_floor=meadow_node('ShaderNodeMath','green denominator');green_floor.operation='MAXIMUM'
    green_floor.inputs[1].default_value=1e-5;links.new(rgb.outputs['Green'],green_floor.inputs[0])
    warm_ratio=meadow_node('ShaderNodeMath','warm source ratio');warm_ratio.operation='DIVIDE'
    links.new(rgb.outputs['Red'],warm_ratio.inputs[0]);links.new(green_floor.outputs[0],warm_ratio.inputs[1])
    dry=meadow_node('ShaderNodeMapRange','retained warm patch mask');dry.clamp=True
    dry.interpolation_type='SMOOTHSTEP';dry.inputs['From Min'].default_value=.70
    dry.inputs['From Max'].default_value=.96
    links.new(warm_ratio.outputs[0],dry.inputs['Value'])
    green=meadow_node('ShaderNodeValToRGB','grass green detail')
    green.color_ramp.elements[0].position=.20;green.color_ramp.elements[0].color=(.09,.21,.030,1)
    green.color_ramp.elements[1].position=.80;green.color_ramp.elements[1].color=(.18,.32,.070,1)
    warm=meadow_node('ShaderNodeValToRGB','grass warm detail')
    warm.color_ramp.elements[0].position=.20;warm.color_ramp.elements[0].color=(.115,.145,.070,1)
    warm.color_ramp.elements[1].position=.80;warm.color_ramp.elements[1].color=(.28,.29,.165,1)
    links.new(grain.outputs['Fac'],green.inputs[0]);links.new(grain.outputs['Fac'],warm.inputs[0])
    detail=meadow_node('ShaderNodeMixRGB','source guided grass detail')
    links.new(dry.outputs['Result'],detail.inputs[0]);links.new(green.outputs[0],detail.inputs[1])
    links.new(warm.outputs[0],detail.inputs[2])
    woodland='woodland' in material.name.lower()
    green_weight,warm_weight=(.18,.10) if woodland else (.42,.12)
    influence=meadow_node('ShaderNodeMath','source retention');influence.operation='MULTIPLY_ADD'
    influence.inputs[1].default_value=warm_weight-green_weight;influence.inputs[2].default_value=green_weight
    links.new(dry.outputs['Result'],influence.inputs[0])
    finish=meadow_node('ShaderNodeMixRGB','retained source pigment')
    links.new(influence.outputs[0],finish.inputs[0]);links.new(original_colour,finish.inputs[1])
    links.new(detail.outputs[0],finish.inputs[2])
    fleck=meadow_node('ShaderNodeValToRGB','neutral grass flecks')
    fleck.color_ramp.elements[0].position=.20;fleck.color_ramp.elements[0].color=(.84,.84,.84,1)
    fleck.color_ramp.elements[1].position=.80;fleck.color_ramp.elements[1].color=(1.12,1.12,1.12,1)
    links.new(grain.outputs['Fac'],fleck.inputs[0])
    tint=meadow_node('ShaderNodeMixRGB','grass surface texture');tint.blend_type='MULTIPLY'
    tint.inputs[0].default_value=.40;links.new(finish.outputs[0],tint.inputs[1])
    links.new(fleck.outputs[0],tint.inputs[2]);links.new(tint.outputs[0],bs.inputs['Base Color'])
    bump=meadow_node('ShaderNodeBump','grass normals');bump.inputs['Strength'].default_value=.20
    bump.inputs['Distance'].default_value=.012;links.new(grain.outputs['Fac'],bump.inputs['Height'])
    if bs.inputs['Normal'].is_linked:links.new(bs.inputs['Normal'].links[0].from_socket,bump.inputs['Normal'])
    links.new(bump.outputs['Normal'],bs.inputs['Normal'])
    rough=meadow_node('ShaderNodeMapRange','matte grass roughness');rough.clamp=True
    rough.inputs['To Min'].default_value=.88;rough.inputs['To Max'].default_value=.97
    links.new(grain.outputs['Fac'],rough.inputs['Value']);links.new(rough.outputs['Result'],bs.inputs['Roughness'])
    old=meadow_original_graphs[material.name];current=meadow_graph_state(material.node_tree)
    assert old['nodes']==[row for row in current['nodes'] if not row['name'].startswith('Expansion meadow ')]
    assert all(link in current['links'] for link in old['links'] if not
        (link[2]==bs.name and link[3] in {'Base Color','Normal','Roughness'}))
    meadow_recipes.append({'material':material.name,'green_detail_mix_estimate':green_weight,
        'warm_detail_mix_estimate':warm_weight,'source_branch_nodes_preserved':True})
meadow_geometry_after={ob.name:lake_digest(meadow_mesh_state(ob)) for ob in meadow_objects}
assert meadow_geometry_before==meadow_geometry_after and meadow_object_names==sorted(ob.name for ob in s.objects)
assert meadow_other_before=={m.name:lake_digest(meadow_graph_state(m.node_tree)) for m in bpy.data.materials
    if m not in meadow_materials and m.use_nodes}
assert meadow_world_before==lake_digest(meadow_graph_state(s.world.node_tree))
assert meadow_lights_before==lake_digest([[ob.name,list(ob.location),list(ob.rotation_euler),ob.data.energy,
    ob.data.color[:],getattr(ob.data,'angle',None)] for ob in sorted(s.objects,key=lambda ob:ob.name) if ob.type=='LIGHT'])
meadow_checks={'material_count':len(meadow_materials),'materials':[m.name for m in meadow_materials],
    'retained_mesh_count':len(meadow_objects),'geometry_sha256':meadow_geometry_after,
    'material_graph_sha256':{m.name:lake_digest(meadow_graph_state(m.node_tree)) for m in meadow_materials},
    'source_branch_graph_sha256':{name:lake_digest(graph) for name,graph in meadow_original_graphs.items()},
    'world_vertices_topology_material_indices_transforms_uv_and_visibility_preserved':True,
    'source_branch_nodes_and_internal_links_preserved':True,'other_material_graphs_preserved':True,
    'other_material_count':len(meadow_other_before),'other_material_graphs_sha256':lake_digest(meadow_other_before),
    'world_and_lighting_preserved':True,'world_graph_sha256':meadow_world_before,'lighting_sha256':meadow_lights_before,
    'coordinate_anchor_matrix':[list(row) for row in n['anchor'].matrix_world],
    'new_geometry_count':0,'displacement_link_count':sum(link.to_socket.name=='Displacement'
        for m in meadow_materials for link in m.node_tree.links),'grain_scale_m_inverse_estimate':1.3,
    'grain_detail_estimate':2.5,'warm_ratio_range_estimate':[.70,.96],'roughness_range_estimate':[.88,.97],
    'bump_distance_m_estimate':.012,'bump_strength_estimate':.20,
    'neutral_fleck_effective_range_estimate':[.936,1.048],'recipes':meadow_recipes}
assert meadow_checks['displacement_link_count']==0

# Retain the single leaf cutout and twelve crown forms. Geographic, metre-scale
# colour organisation reduces the repeated baked highlight/dark-centre pattern;
# edge colour is desaturated without changing alpha or adding foliage geometry.
foliage_materials=canopy_daylight_materials
assert [m.name for m in foliage_materials]==['Garden detailed canopy sprite','Pilot detailed canopy image']
def foliage_mesh_state(mesh):
    return {'vertices':[list(v.co) for v in mesh.vertices],
        'faces':[[list(f.vertices),f.material_index,f.use_smooth] for f in mesh.polygons],
        'uv':{uv.name:[list(loop.uv) for loop in uv.data] for uv in mesh.uv_layers},
        'material_slots':[m.name if m else None for m in mesh.materials]}
def foliage_geometry_state():
    meshes={ob.data.as_pointer():ob.data for ob in crowns}
    fingerprints={key:lake_digest(foliage_mesh_state(mesh)) for key,mesh in meshes.items()}
    rows=[]
    for ob in crowns:
        category=next(prefix for prefix in canopy_prefixes if ob.name.startswith(prefix)).strip()
        rows.append([category,[round(float(v),6) for v in ob['source_position_xy']],
            [list(row) for row in ob.matrix_world],ob.hide_render,fingerprints[ob.data.as_pointer()]])
    rows.sort(key=lambda row:json.dumps(row,separators=(',',':')))
    return {'shared_mesh_count':len(meshes),'shared_mesh_sha256':sorted(fingerprints.values()),
        'source_objects_geometry_sha256':lake_digest(rows),'crown_count':len(rows)}
def foliage_alpha_state(material):
    ns=material.node_tree.nodes;links=material.node_tree.links
    tex=next(node for node in ns if node.bl_idname=='ShaderNodeTexImage')
    mixed=next(node for node in ns if node.bl_idname=='ShaderNodeMixShader')
    transparent=next(node for node in ns if node.bl_idname=='ShaderNodeBsdfTransparent')
    bs=next(node for node in ns if node.bl_idname=='ShaderNodeBsdfPrincipled')
    output=next(node for node in ns if node.bl_idname=='ShaderNodeOutputMaterial')
    assert mixed.inputs[0].links[0].from_socket==tex.outputs['Alpha']
    assert mixed.inputs[1].links[0].from_node==transparent and mixed.inputs[2].links[0].from_node==bs
    assert output.inputs['Surface'].links[0].from_node==mixed
    return {'image':[tex.image.name,tex.image.filepath,tex.image.colorspace_settings.name,tex.image.alpha_mode],
        'image_sampling':[tex.interpolation,tex.extension,tex.projection,tex.projection_blend],
        'image_vector_links':[[link.from_node.name,link.from_socket.identifier] for link in tex.inputs['Vector'].links],
        'alpha_surface_links':sorted([link.from_node.name,link.from_socket.identifier,link.to_node.name,link.to_socket.identifier]
            for link in links if link.to_node in (mixed,output) or link.to_node==bs and link.to_socket.name=='Alpha'),
        'transparent_colour':list(transparent.inputs['Color'].default_value),'bsdf_alpha_default':bs.inputs['Alpha'].default_value}
foliage_geometry_before=foliage_geometry_state()
foliage_alpha_before={m.name:foliage_alpha_state(m) for m in foliage_materials}
foliage_other_before={m.name:lake_digest(meadow_graph_state(m.node_tree)) for m in bpy.data.materials
    if m not in foliage_materials and m.use_nodes}
foliage_world_before=lake_digest(meadow_graph_state(s.world.node_tree))
foliage_lights_before=lake_digest([[ob.name,list(ob.location),list(ob.rotation_euler),ob.data.energy,
    ob.data.color[:],getattr(ob.data,'angle',None)] for ob in sorted(s.objects,key=lambda ob:ob.name) if ob.type=='LIGHT'])
foliage_colour_rows=[]
for ob in crowns:
    category=next(prefix for prefix in canopy_prefixes if ob.name.startswith(prefix)).strip()
    xy=[round(float(v),6) for v in ob['source_position_xy']]
    seed=hashlib.sha256(json.dumps([category,xy],separators=(',',':')).encode()).digest()
    ob.color=tuple(int.from_bytes(seed[a:a+4],'big')/4294967295 for a in (8,12,16))+(1,)
    foliage_colour_rows.append([category,xy,list(ob.color)])
foliage_colour_rows.sort(key=lambda row:json.dumps(row,separators=(',',':')))
foliage_hsv_ranges={}
for material in foliage_materials:
    ns=material.node_tree.nodes;links=material.node_tree.links
    bs=next(node for node in ns if node.bl_idname=='ShaderNodeBsdfPrincipled')
    tex=next(node for node in ns if node.bl_idname=='ShaderNodeTexImage')
    hsv=next(node for node in ns if node.bl_idname=='ShaderNodeHueSaturation')
    info=next(node for node in ns if node.bl_idname=='ShaderNodeObjectInfo')
    def foliage_node(kind,name):
        node=ns.new(kind);node.name='Expansion foliage '+name;return node
    channels=foliage_node('ShaderNodeSeparateColor','source colour channels');channels.mode='RGB'
    links.new(info.outputs['Color'],channels.inputs[0])
    for socket,channel in [('Hue','Red'),('Saturation','Green'),('Value','Blue')]:
        mapped=hsv.inputs[socket].links[0].from_node
        assert mapped.bl_idname=='ShaderNodeMapRange'
        bounds=[mapped.inputs[key].default_value for key in ('To Min','To Max')]
        expected={'Hue':[.46,.515],'Saturation':[.96,1.12],'Value':[1.08,1.42]}[socket]
        assert all(abs(a-b)<1e-6 for a,b in zip(bounds,expected))
        foliage_hsv_ranges.setdefault(material.name,{})[socket]=bounds
        links.new(channels.outputs[channel],mapped.inputs['Value'])
    coord=foliage_node('ShaderNodeTexCoord','metre coordinates');coord.object=n['anchor']
    clumps=foliage_node('ShaderNodeTexNoise','leaf group organisation')
    clumps.inputs['Scale'].default_value=.70;clumps.inputs['Detail'].default_value=2
    clumps.inputs['Roughness'].default_value=.60;links.new(coord.outputs['Object'],clumps.inputs['Vector'])
    tone=foliage_node('ShaderNodeValToRGB','leaf group tone')
    tone.color_ramp.elements[0].position=.20;tone.color_ramp.elements[0].color=(.72,.82,.72,1)
    tone.color_ramp.elements[1].position=.80;tone.color_ramp.elements[1].color=(1.19,1.16,1.06,1)
    links.new(clumps.outputs['Fac'],tone.inputs[0])
    luminance=foliage_node('ShaderNodeRGBToBW','retained image lightness');links.new(tex.outputs['Color'],luminance.inputs[0])
    gain=foliage_node('ShaderNodeMapRange','bounded baked-light compensation');gain.clamp=True
    gain.interpolation_type='SMOOTHSTEP';gain.inputs['From Min'].default_value=.015
    gain.inputs['From Max'].default_value=.32;gain.inputs['To Min'].default_value=1.30
    gain.inputs['To Max'].default_value=.85;links.new(luminance.outputs[0],gain.inputs['Value'])
    compensate=foliage_node('ShaderNodeMixRGB','retain leaf pigment');compensate.blend_type='MULTIPLY'
    compensate.inputs[0].default_value=1;links.new(hsv.outputs['Color'],compensate.inputs[1])
    links.new(gain.outputs['Result'],compensate.inputs[2])
    groups=foliage_node('ShaderNodeMixRGB','geographic leaf groups');groups.blend_type='MULTIPLY'
    groups.inputs[0].default_value=.55;links.new(compensate.outputs[0],groups.inputs[1])
    links.new(tone.outputs[0],groups.inputs[2])
    edge=foliage_node('ShaderNodeMapRange','colour-only soft edge');edge.clamp=True
    edge.interpolation_type='SMOOTHSTEP';edge.inputs['To Min'].default_value=.45
    edge.inputs['To Max'].default_value=1;links.new(tex.outputs['Alpha'],edge.inputs['Value'])
    finish=foliage_node('ShaderNodeHueSaturation','retained alpha edge colour')
    links.new(groups.outputs[0],finish.inputs['Color']);links.new(edge.outputs['Result'],finish.inputs['Saturation'])
    links.new(finish.outputs[0],bs.inputs['Base Color']);links.new(finish.outputs[0],bs.inputs['Emission Color'])
    bump=foliage_node('ShaderNodeBump','leaf group normals');bump.inputs['Strength'].default_value=.18
    bump.inputs['Distance'].default_value=.018;links.new(clumps.outputs['Fac'],bump.inputs['Height'])
    if bs.inputs['Normal'].is_linked:links.new(bs.inputs['Normal'].links[0].from_socket,bump.inputs['Normal'])
    links.new(bump.outputs['Normal'],bs.inputs['Normal'])
assert foliage_geometry_before==foliage_geometry_state()
assert foliage_alpha_before=={m.name:foliage_alpha_state(m) for m in foliage_materials}
assert foliage_other_before=={m.name:lake_digest(meadow_graph_state(m.node_tree)) for m in bpy.data.materials
    if m not in foliage_materials and m.use_nodes}
assert foliage_world_before==lake_digest(meadow_graph_state(s.world.node_tree))
assert foliage_lights_before==lake_digest([[ob.name,list(ob.location),list(ob.rotation_euler),ob.data.energy,
    ob.data.color[:],getattr(ob.data,'angle',None)] for ob in sorted(s.objects,key=lambda ob:ob.name) if ob.type=='LIGHT'])
foliage_checks={'material_count':len(foliage_materials),'materials':[m.name for m in foliage_materials],
    **foliage_geometry_before,'image_sha256':sha(ROOT/'output/garden-tree-canopy.png'),
    'material_graph_sha256':{m.name:lake_digest(meadow_graph_state(m.node_tree)) for m in foliage_materials},
    'source_colour_assignment_sha256':lake_digest(foliage_colour_rows),
    'source_colour_allocation':'SHA-256 of category and micron-rounded source XY; big-endian bytes 8:12,12:16,16:20 divided by 4294967295, assigned to Object Color RGB',
    'alpha_surface_chain_sha256':{name:lake_digest(row) for name,row in foliage_alpha_before.items()},
    'all_crown_vertices_topology_material_indices_transforms_uv_and_visibility_preserved':True,
    'original_image_sampling_and_alpha_surface_chain_preserved':True,'other_material_graphs_preserved':True,
    'other_material_count':len(foliage_other_before),'other_material_graphs_sha256':lake_digest(foliage_other_before),
    'world_and_lighting_preserved':True,'world_graph_sha256':foliage_world_before,'lighting_sha256':foliage_lights_before,
    'coordinate_anchor_matrix':[list(row) for row in n['anchor'].matrix_world],
    'new_geometry_count':0,'displacement_link_count':sum(link.to_socket.name=='Displacement'
        for m in foliage_materials for link in m.node_tree.links),
    'leaf_group_scale_m_inverse_estimate':.70,'leaf_group_tone_mix_estimate':.55,
    'baked_light_gain_range_estimate':[.85,1.30],'colour_only_edge_saturation_range_estimate':[.45,1],
    'normal_distance_m_estimate':.018,'normal_strength_estimate':.18,
    'hsv_ranges_preserved':foliage_hsv_ranges}
assert foliage_checks['displacement_link_count']==0

# The second reconstruction batch shares these panes beyond the south campus,
# including some photographed north dorm families. Refine colour separation
# only; retain all openings, facade parts, source pigment, AO and normal chains.
facade_wall_gains={
    'Atlas architecture neutral residential plaster.001':1.10,
    'Atlas architecture institutional pale plaster.001':1.08,
    'Atlas architecture weathered campus plaster.001':1.10,
    'Atlas architecture muted campus stone trim.001':1.20}
facade_glass_names=[f'Atlas architecture glass {i}.001' for i in range(4)]
facade_names=sorted([*facade_wall_gains,*facade_glass_names])
facade_materials=sorted((m for m in visible_materials if m.name in facade_names),key=lambda m:m.name)
assert [m.name for m in facade_materials]==facade_names
facade_objects=sorted((ob for ob in s.objects if ob.type=='MESH' and not ob.hide_render and
    any(ob.data.materials[i] in facade_materials for i in {f.material_index for f in ob.data.polygons}
        if i<len(ob.data.materials))),key=lambda ob:ob.name)
assert all(ob.get('source_id') in {row['id'] for row in D['buildings']} for ob in facade_objects)
assert len(facade_objects)>60
def facade_mesh_state(ob):
    return {**meadow_mesh_state(ob),'smooth':[f.use_smooth for f in ob.data.polygons],
        'active_uv_index':ob.data.uv_layers.active_index,
        'render_uv':[uv.name for uv in ob.data.uv_layers if uv.active_render]}
def facade_geometry_state():
    rows=[[ob['source_id'],lake_digest(facade_mesh_state(ob))] for ob in facade_objects]
    rows.sort()
    assert len({row[0] for row in rows})==len(rows)
    return {'retained_mesh_count':len(rows),'source_ids':[row[0] for row in rows],
        'source_mesh_geometry_uv_sha256':lake_digest(rows)}
def facade_graph_state(tree):
    state=meadow_graph_state(tree)
    for row in state['nodes']:
        node=tree.nodes[row['name']]
        if hasattr(node,'use_clamp'):row['properties']['use_clamp']=node.use_clamp
    return state
def facade_source_graph(material,names):
    state=facade_graph_state(material.node_tree)
    bs=material.node_tree.nodes.get('Principled BSDF')
    state['nodes']=[row for row in state['nodes'] if row['name'] in names]
    state['links']=[row for row in state['links'] if row[0] in names and row[2] in names
        and not (row[2]==bs.name and row[3]==bs.inputs['Base Color'].identifier)]
    return state
facade_geometry_before=facade_geometry_state()
facade_inventory_before=sorted([ob.name,ob.type,ob.data.name if ob.data else None] for ob in s.objects)
facade_mesh_count_before=len(bpy.data.meshes)
facade_node_names={m.name:{node.name for node in m.node_tree.nodes} for m in facade_materials}
facade_branches_before={m.name:facade_source_graph(m,facade_node_names[m.name]) for m in facade_materials}
facade_other_before={m.name:lake_digest(facade_graph_state(m.node_tree)) for m in bpy.data.materials
    if m not in facade_materials and m.use_nodes}
facade_world_before=lake_digest(facade_graph_state(s.world.node_tree))
facade_lights_before=lake_digest([[ob.name,list(ob.location),list(ob.rotation_euler),ob.data.energy,
    ob.data.color[:],getattr(ob.data,'angle',None)] for ob in sorted(s.objects,key=lambda ob:ob.name) if ob.type=='LIGHT'])
facade_recipes=[]
for material in facade_materials:
    ns=material.node_tree.nodes;links=material.node_tree.links;bs=ns.get('Principled BSDF')
    original=bs.inputs['Base Color'].links[0].from_socket
    def facade_node(kind,name):
        node=ns.new(kind);node.name='Expansion facade '+name;return node
    finish=facade_node('ShaderNodeMixRGB','retained colour contrast');finish.blend_type='MULTIPLY'
    finish.use_clamp=True;finish.inputs[0].default_value=1;links.new(original,finish.inputs[1])
    if material.name in facade_wall_gains:
        gain=facade_wall_gains[material.name];finish.inputs[2].default_value=(gain,gain,gain,1)
        facade_recipes.append({'material':material.name,'kind':'retained wall or trim pigment',
            'colour_gain_actual':list(finish.inputs[2].default_value)[:3],'output_colour_clamped':finish.use_clamp})
    else:
        coord=facade_node('ShaderNodeTexCoord','retained building bounds')
        axis=facade_node('ShaderNodeSeparateXYZ','building height')
        links.new(coord.outputs['Generated'],axis.inputs[0])
        gain=facade_node('ShaderNodeMapRange','bounded pane height tone');gain.clamp=True
        gain.interpolation_type='SMOOTHSTEP';gain.inputs['From Min'].default_value=.08
        gain.inputs['From Max'].default_value=.92;gain.inputs['To Min'].default_value=.64
        gain.inputs['To Max'].default_value=1.04
        links.new(axis.outputs['Z'],gain.inputs['Value']);links.new(gain.outputs['Result'],finish.inputs[2])
        facade_recipes.append({'material':material.name,'kind':'retained pane pigment',
            'generated_z_from_range_actual':[gain.inputs[k].default_value for k in ('From Min','From Max')],
            'colour_gain_range_actual':[gain.inputs[k].default_value for k in ('To Min','To Max')],
            'height_interpolation':gain.interpolation_type,'height_clamped':gain.clamp,
            'output_colour_clamped':finish.use_clamp,
            'roughness_preserved_actual':bs.inputs['Roughness'].default_value})
    links.new(finish.outputs[0],bs.inputs['Base Color'])
assert facade_geometry_before==facade_geometry_state()
assert facade_inventory_before==sorted([ob.name,ob.type,ob.data.name if ob.data else None] for ob in s.objects)
assert facade_mesh_count_before==len(bpy.data.meshes)
assert facade_branches_before=={m.name:facade_source_graph(m,facade_node_names[m.name]) for m in facade_materials}
assert facade_other_before=={m.name:lake_digest(facade_graph_state(m.node_tree)) for m in bpy.data.materials
    if m not in facade_materials and m.use_nodes}
assert facade_world_before==lake_digest(facade_graph_state(s.world.node_tree))
assert facade_lights_before==lake_digest([[ob.name,list(ob.location),list(ob.rotation_euler),ob.data.energy,
    ob.data.color[:],getattr(ob.data,'angle',None)] for ob in sorted(s.objects,key=lambda ob:ob.name) if ob.type=='LIGHT'])
facade_checks={'material_count':len(facade_materials),'materials':facade_names,**facade_geometry_before,
    'material_graph_sha256':{m.name:lake_digest(facade_graph_state(m.node_tree)) for m in facade_materials},
    'source_branch_graph_sha256':{name:lake_digest(graph) for name,graph in facade_branches_before.items()},
    'world_vertices_topology_material_indices_slots_transforms_uv_and_visibility_preserved':True,
    'source_colour_nodes_internal_links_and_other_bsdf_links_preserved':True,
    'object_inventory_and_mesh_count_preserved':True,'other_material_graphs_preserved':True,
    'other_material_count':len(facade_other_before),'other_material_graphs_sha256':lake_digest(facade_other_before),
    'world_and_lighting_preserved':True,'world_graph_sha256':facade_world_before,'lighting_sha256':facade_lights_before,
    'new_geometry_count':0,'displacement_link_count':sum(link.to_socket.name=='Displacement'
        for m in facade_materials for link in m.node_tree.links),'recipes':facade_recipes}
assert facade_checks['displacement_link_count']==0

# Spatial pass: retain the survey geometry, replacing oversized illustrative
# parking grids and the hard photographic/modelled ground transition only.
from mathutils import Matrix
import numpy as np
import shapely
bpy.context.view_layer.update()
spatial_grass_before={ob.name:lake_digest(facade_mesh_state(ob)) for ob in meadow_objects}
spatial_material_before={m.name:lake_digest(facade_graph_state(m.node_tree)) for m in bpy.data.materials
    if m.use_nodes and m not in meadow_materials}
spatial_world_before=lake_digest(facade_graph_state(s.world.node_tree))
spatial_lights_before=facade_lights_before
spatial_roofs_before=lake_digest(faces)
spatial_contexts=[s.objects['Expansion '+source+' context'] for source in ('satellite','north-extension')]
assert all(not ob.hide_render for ob in spatial_contexts)
assert all(s.objects[name].hide_render for name in
    ('satellite outside-campus context','north-extension outside-campus context','Joined exterior context'))
context_mesh_before={ob.name:{k:v for k,v in facade_mesh_state(ob).items() if k!='material_slots'} for ob in spatial_contexts}
spatial_paint_prefixes=('Atlas parking bay','Atlas illustrative parking line',
    'Joined illustrative parking bay separators','Expansion source central lake parking bay markings','Parking stall')
def spatial_mesh_snapshot(objects):
    # Many trees instance the same dense mesh. Hash each local mesh once, then
    # retain each object's exact world matrix and render state. Equal local
    # vertices plus equal matrices imply identical world vertices.
    mesh_hashes={};rows={}
    for ob in objects:
        me=ob.data
        if me.name not in mesh_hashes:
            mesh_hashes[me.name]=lake_digest({'v':[list(v.co) for v in me.vertices],
                'f':[[list(f.vertices),f.material_index,f.use_smooth] for f in me.polygons],
                'slots':[m.name if m else None for m in me.materials],
                'uv':{uv.name:[list(v.uv) for v in uv.data] for uv in me.uv_layers},
                'active_uv':me.uv_layers.active_index,'render_uv':[uv.name for uv in me.uv_layers if uv.active_render]})
        rows[ob.name]=[me.name,mesh_hashes[me.name],[list(row) for row in ob.matrix_world],ob.hide_render]
    return rows
spatial_protected_before=spatial_mesh_snapshot(ob for ob in s.objects
    if ob.type=='MESH' and not ob.hide_render and ob not in spatial_contexts
    and ob not in meadow_objects and not ob.name.startswith(spatial_paint_prefixes))

# One source-colour/diffuse path serves both sides of the model boundary.
# The two surveys overlap here; interpolate only inside their common coverage.
source_group=bpy.data.node_groups.new('Expansion geographic ground continuity','ShaderNodeTree')
source_group.interface.new_socket(name='Surface',in_out='OUTPUT',socket_type='NodeSocketShader')
ns=source_group.nodes;links=source_group.links
position=ns.new('ShaderNodeNewGeometry');axis=ns.new('ShaderNodeSeparateXYZ')
links.new(position.outputs['Position'],axis.inputs[0])
source_textures=[];coverage_checks=[];source_bounds={}
for source,width,height in [('satellite',1152,1920),('north-extension',1000,900)]:
    lo=gp((0,height),source=source);hi=gp((width,0),source=source)
    mapped=ns.new('ShaderNodeVectorMath');mapped.operation='MULTIPLY_ADD'
    mapped.inputs[1].default_value=(1/(hi.x-lo.x),1/(hi.y-lo.y),1)
    mapped.inputs[2].default_value=(-lo.x/(hi.x-lo.x),-lo.y/(hi.y-lo.y),0)
    links.new(position.outputs['Position'],mapped.inputs[0])
    photo=ns.new('ShaderNodeTexImage');photo.interpolation='Cubic';photo.extension='EXTEND'
    photo.image=bpy.data.images.load(str(ROOT/'model/campus/references'/
        ('satellite.jpg' if source=='satellite' else 'north-extension.jpg')),check_existing=True)
    links.new(mapped.outputs[0],photo.inputs['Vector']);source_textures.append(photo)
    assert lo.y<cut-12<cut+12<hi.y
    source_bounds[source]=(lo.x,lo.y,hi.x,hi.y)
    coverage_checks.append({'source':source,'world_bounds':[lo.x,lo.y,hi.x,hi.y],
        'blend_y_uv_range':[(cut-12-lo.y)/(hi.y-lo.y),(cut+12-lo.y)/(hi.y-lo.y)]})
survey_mix=ns.new('ShaderNodeMapRange');survey_mix.interpolation_type='SMOOTHSTEP';survey_mix.clamp=True
survey_mix.inputs['From Min'].default_value=cut-12;survey_mix.inputs['From Max'].default_value=cut+12
links.new(axis.outputs['Y'],survey_mix.inputs['Value'])
def spatial_math(operation,*inputs):
    node=ns.new('ShaderNodeMath');node.operation=operation
    for i,value in enumerate(inputs):
        if isinstance(value,(int,float)):node.inputs[i].default_value=value
        else:links.new(value,node.inputs[i])
    return node.outputs[0]
nlo_x,nlo_y,nhi_x,nhi_y=source_bounds['north-extension']
mlo_x,mlo_y,mhi_x,mhi_y=source_bounds['satellite']
def spatial_inside(low,high,socket):
    return spatial_math('MULTIPLY',spatial_math('GREATER_THAN',socket,low),spatial_math('LESS_THAN',socket,high))
north_valid=spatial_math('MULTIPLY',spatial_inside(nlo_x,nhi_x,axis.outputs['X']),
    spatial_inside(nlo_y,nhi_y,axis.outputs['Y']))
main_valid=spatial_math('MULTIPLY',spatial_inside(mlo_x,mhi_x,axis.outputs['X']),
    spatial_inside(mlo_y,mhi_y,axis.outputs['Y']))
x_window=[]
for lo,hi in [(nlo_x,nlo_x+4),(nhi_x,nhi_x-4)]:
    ramp=ns.new('ShaderNodeMapRange');ramp.interpolation_type='SMOOTHSTEP';ramp.clamp=True
    ramp.inputs['From Min'].default_value=lo;ramp.inputs['From Max'].default_value=hi
    links.new(axis.outputs['X'],ramp.inputs['Value']);x_window.append(ramp.outputs['Result'])
overlap_weight=spatial_math('MULTIPLY',survey_mix.outputs['Result'],spatial_math('MULTIPLY',*x_window))
preference=spatial_math('ADD',spatial_math('SUBTRACT',1,main_valid),spatial_math('MULTIPLY',main_valid,overlap_weight))
north_weight=spatial_math('MULTIPLY',north_valid,preference)
colour=ns.new('ShaderNodeMixRGB');links.new(north_weight,colour.inputs[0])
for i,photo in enumerate(source_textures):links.new(photo.outputs['Color'],colour.inputs[i+1])
diffuse=ns.new('ShaderNodeBsdfDiffuse');diffuse.inputs['Roughness'].default_value=.70
links.new(colour.outputs[0],diffuse.inputs['Color'])
output=ns.new('NodeGroupOutput');links.new(diffuse.outputs[0],output.inputs['Surface'])

# A small in-memory world-XY field avoids subdividing or moving source meshes.
# Only the exterior ring is feathered; the six retained survey holes stay holes.
woodland=shape(next(row for row in D['surfaces'] if row['id']=='adjacent-woodland'))
assert next(row for row in D['surfaces'] if row['id']=='adjacent-woodland')['role'].endswith('not campus property boundary')
outer_ring=ground.exterior if ground.geom_type=='Polygon' else unary_union([g.exterior for g in ground.geoms])
x0,y0,x1,y1=ground.bounds;x0-=24;y0-=24;x1+=24;y1+=24
field_w=768;field_h=round(field_w*(y1-y0)/(x1-x0))
xx,yy=np.meshgrid(x0+(np.arange(field_w)+.5)*(x1-x0)/field_w,
    y0+(np.arange(field_h)+.5)*(y1-y0)/field_h)
points=shapely.points(xx,yy)
def spatial_smooth(value):
    value=np.clip(value,0,1);return value*value*(3-2*value)
edge=spatial_smooth(shapely.distance(points,outer_ring)/18)
wood=spatial_smooth(shapely.distance(points,woodland.boundary)/12)*shapely.contains_xy(woodland,xx,yy)
pixels=np.ones((field_h,field_w,4),dtype=np.float32)
pixels[:,:,0]=edge*(1-wood);pixels[:,:,1]=wood;pixels[:,:,2]=edge
field=bpy.data.images.new('Expansion ground boundary field',width=field_w,height=field_h,float_buffer=True)
field.colorspace_settings.name='Non-Color';field.pixels.foreach_set(pixels.ravel());field.update()
field_sha=hashlib.sha256(pixels.tobytes()).hexdigest()
field_cell=[(x1-x0)/field_w,(y1-y0)/field_h]
assert max(field_cell)<1.7
for material in meadow_materials:
    ns=material.node_tree.nodes;links=material.node_tree.links;output=ns.get('Material Output')
    retained=output.inputs['Surface'].links[0].from_socket
    position=ns.new('ShaderNodeNewGeometry');mapped=ns.new('ShaderNodeVectorMath');mapped.operation='MULTIPLY_ADD'
    mapped.inputs[1].default_value=(1/(x1-x0),1/(y1-y0),1)
    mapped.inputs[2].default_value=(-x0/(x1-x0),-y0/(y1-y0),0)
    links.new(position.outputs['Position'],mapped.inputs[0])
    weight=ns.new('ShaderNodeTexImage');weight.image=field;weight.interpolation='Linear';weight.extension='EXTEND'
    links.new(mapped.outputs[0],weight.inputs['Vector'])
    channels=ns.new('ShaderNodeSeparateColor');links.new(weight.outputs['Color'],channels.inputs['Color'])
    source=ns.new('ShaderNodeGroup');source.node_tree=source_group
    blend=ns.new('ShaderNodeMixShader');links.new(channels.outputs['Red'],blend.inputs[0])
    links.new(source.outputs['Surface'],blend.inputs[1]);links.new(retained,blend.inputs[2])
    links.new(blend.outputs[0],output.inputs['Surface'])
for ob in spatial_contexts:
    finish=ob.data.materials[0].copy();finish.name='Expansion continuous context '+ob.name
    ns=finish.node_tree.nodes;links=finish.node_tree.links;source=ns.new('ShaderNodeGroup');source.node_tree=source_group
    links.new(source.outputs['Surface'],ns.get('Material Output').inputs['Surface']);ob.data.materials[0]=finish
assert spatial_grass_before=={ob.name:lake_digest(facade_mesh_state(ob)) for ob in meadow_objects}
# Context material slot is intentionally replaced; all other mesh data is kept.
for ob in spatial_contexts:
    assert context_mesh_before[ob.name]=={k:v for k,v in facade_mesh_state(ob).items() if k!='material_slots'}
    assert ob.data.uv_layers.get('Source geographic UV')

# Remove superseded paint, including inherited central 5.73 x 7.95 m grids.
paint_prefixes=spatial_paint_prefixes
hidden_paint=[]
for ob in s.objects:
    if ob.type=='MESH' and not ob.hide_render and ob.name.startswith(paint_prefixes):
        ob.hide_render=True;hidden_paint.append(ob.name)
parking_width=2.65;parking_depth=5.10;parking_aisle=6.20;parking_margin=.60
parking_rows=[('central-lake',central_parking,.452,(gp((560,731))-gp((489,726))).normalized()),
    ('north-parking',ctx['parking'],.425,Vector((0,0,0))),
    ('center-parking',shape(next(row for row in D['surfaces'] if row['id']=='center-parking')).intersection(ground).difference(mask),.425,
        (gp((722,1183))-gp((696,1180))).normalized())]
north_depth=(gp((813,482))-gp((749,474))).normalized()
parking_rows[1]=(*parking_rows[1][:3],Vector((-north_depth.y,north_depth.x,0)))
bay_batches=[];bay_geometry={};parking_scale_records=[]
for name,area,z,across in parking_rows:
    assert area.area>100,name
    depth=Vector((across.y,-across.x,0))
    area_parts=list(area.geoms) if area.geom_type=='MultiPolygon' else [area]
    coords=[Vector((x,y,0)) for part in area_parts for x,y in part.exterior.coords]
    amin,amax=min(p.dot(across) for p in coords),max(p.dot(across) for p in coords)
    dmin,dmax=min(p.dot(depth) for p in coords),max(p.dot(depth) for p in coords)
    inner=area.buffer(-parking_margin);bays=[];lines=[];row_count=0
    def parking_rectangle(a0,a1,d0,d1):
        return Polygon([(across.x*aa+depth.x*dd,across.y*aa+depth.y*dd) for aa,dd in
            [(a0,d0),(a1,d0),(a1,d1),(a0,d1)]])
    # Keep a continuous side aisle towards an existing road. A complete bay
    # also needs a full-depth front aisle, including the first/last row.
    road_reference=asphalt.union(ctx['road'])
    side_candidates=[('min',parking_rectangle(amin,amin+parking_margin+parking_aisle,dmin,dmax).intersection(inner)),
        ('max',parking_rectangle(amax-parking_margin-parking_aisle,amax,dmin,dmax).intersection(inner))]
    connector_side,connector=min(side_candidates,key=lambda item:
        (item[1].distance(road_reference),-item[1].intersection(road_reference.buffer(3)).area))
    row_origins=list(np.arange(dmin+parking_margin+parking_aisle,dmax-parking_margin-parking_depth,
        2*parking_depth+parking_aisle))
    row_access=[parking_rectangle(amin,amax,float(origin)+offset,float(origin)+offset+parking_aisle).intersection(inner)
        for origin in row_origins for offset in (-parking_aisle,2*parking_depth)]
    access=unary_union([connector,*row_access]).buffer(1e-5).buffer(-1e-5).intersection(inner)
    access_parts=list(access.geoms) if access.geom_type=='MultiPolygon' else [access]
    connected_access=max(access_parts,key=lambda g:g.area)
    assert connected_access.geom_type=='Polygon' and connected_access.area>0
    retained_connector=connector.intersection(connected_access)
    assert retained_connector.area>0
    parking_filter_counts={'outside':0,'in_access':0,'no_front_access':0}
    for row_origin in row_origins:
        for twin in range(2):
            dd=float(row_origin+twin*parking_depth);accepted=0
            for aa in np.arange(amin+parking_margin,amax-parking_width,parking_width):
                bay=parking_rectangle(float(aa),float(aa)+parking_width,dd,dd+parking_depth)
                front_d=float(row_origin-parking_aisle if twin==0 else row_origin+2*parking_depth)
                front_aisle=parking_rectangle(float(aa),float(aa)+parking_width,front_d,front_d+parking_aisle)
                if not inner.covers(bay):parking_filter_counts['outside']+=1;continue
                if bay.intersection(connected_access).area>1e-7:parking_filter_counts['in_access']+=1;continue
                if not connected_access.buffer(2e-5).covers(front_aisle):parking_filter_counts['no_front_access']+=1;continue
                bays.append(bay);lines.append(bay.boundary.buffer(.045,cap_style='flat',join_style='mitre'));accepted+=1
            row_count+=bool(accepted)
    assert bays,(name,parking_filter_counts,connected_access.area)
    marks=unary_union(lines).difference(connected_access);assert marks.difference(area).area<1e-7
    assert marks.intersection(connected_access).area<1e-7
    ob=surface('Expansion metre parking '+name,marks,z+.014,parking_paint);bay_batches.append(ob)
    bay_geometry[name]=(bays,across,depth,z)
    parking_scale_records.append({'id':name,'source_area_m2':area.area,'complete_illustrative_bay_count':len(bays),
        'row_count':row_count,'bay_width_m_estimate':parking_width,'bay_depth_m_estimate':parking_depth,
        'aisle_m_estimate':parking_aisle,'paint_width_m_estimate':.09,
        'markings_outside_source_area_m2':marks.difference(area).area,
        'bay_layout_sha256':lake_digest([list(b.exterior.coords) for b in bays]),
        'connected_side_aisle_m_estimate':parking_aisle,'connector_side':connector_side,
        'connector_existing_road_distance_m':retained_connector.distance(road_reference),
        'connected_access_area_m2':connected_access.area,'connected_access_component_count':1,
        'every_bay_has_complete_front_aisle':True,'markings_in_access_aisles_m2':marks.intersection(connected_access).area,
        'connected_access_sha256':lake_digest(connected_access.wkt)})

# Existing illustrative cars are scale references, not observed occupancy.
# Reuse their three source components and dimensions; align to complete bays
# and raise the body to the new parking surface instead of burying it in paving.
bays,across,depth,parking_z=bay_geometry['central-lake'];available=list(range(len(bays)))
vehicle_records=[]
car_bodies=sorted((ob for ob in s.objects if ob.name.startswith('Parked car body')),key=lambda ob:ob.name)
assert len(car_bodies)==14
for body in car_bodies:
    suffix=body.name[len('Parked car body'):]
    parts=[body,s.objects['Parked car glazing'+suffix],s.objects['Parked car roof'+suffix]]
    old_centre=body.matrix_world.translation.copy();local_meshes={ob.name:lake_digest(
        {'v':[list(v.co) for v in ob.data.vertices],'f':[list(f.vertices) for f in ob.data.polygons]}) for ob in parts}
    index=min(available,key=lambda i:bays[i].centroid.distance(Point(old_centre.x,old_centre.y)));available.remove(index)
    target=bays[index].centroid;angle=math.atan2(across.y,across.x);rot=Matrix.Rotation(angle,3,'Z')
    floor=min((body.matrix_world@v.co).z for v in body.data.vertices)
    lift=parking_z+.16-floor;delta=Vector((target.x-old_centre.x,target.y-old_centre.y,lift))
    for ob in parts:
        assert ob.parent is None and abs(ob.rotation_euler.z)<1e-6
        offset=ob.matrix_world.translation-old_centre
        ob.location=old_centre+delta+rot@offset;ob.rotation_euler.z=angle;ob.hide_render=False
        assert local_meshes[ob.name]==lake_digest({'v':[list(v.co) for v in ob.data.vertices],
            'f':[list(f.vertices) for f in ob.data.polygons]})
    bpy.context.view_layer.update()
    corners=[body.matrix_world@Vector(p) for p in body.bound_box]
    width=max(p.dot(across) for p in corners)-min(p.dot(across) for p in corners)
    length=max(p.dot(depth) for p in corners)-min(p.dot(depth) for p in corners)
    assert abs(width-1.8)<1e-4 and abs(length-4.2)<1e-4
    assert parking_width>width and parking_depth>length
    footprint=Polygon([tuple(body.matrix_world@Vector((x,y,0)))[:2]
        for x,y in [(-.9,-2.1),(.9,-2.1),(.9,2.1),(-.9,2.1)]])
    assert bays[index].buffer(1e-5).covers(footprint)
    vehicle_records.append({'body':body.name,'parts':[ob.name for ob in parts],
        'source_centre_world':list(old_centre),'render_centre_world':list(body.location),
        'width_m':width,'length_m':length,'clearance_above_parking_m':min(p.z for p in corners)-parking_z,
        'placement_shift_xy_m':math.hypot(delta.x,delta.y),'local_meshes_sha256':local_meshes})
assert len(available)==len(bays)-14
spatial_protected_after=spatial_mesh_snapshot(s.objects[name] for name in spatial_protected_before)
assert spatial_protected_before==spatial_protected_after,[(name,[i for i,(a,b) in enumerate(zip(old,spatial_protected_after[name])) if a!=b])
    for name,old in spatial_protected_before.items() if old!=spatial_protected_after[name]][:12]
assert spatial_material_before=={name:lake_digest(facade_graph_state(bpy.data.materials[name].node_tree)) for name in spatial_material_before}
assert spatial_world_before==lake_digest(facade_graph_state(s.world.node_tree))
assert spatial_lights_before==lake_digest([[ob.name,list(ob.location),list(ob.rotation_euler),ob.data.energy,
    ob.data.color[:],getattr(ob.data,'angle',None)] for ob in sorted(s.objects,key=lambda ob:ob.name) if ob.type=='LIGHT'])
assert spatial_roofs_before==lake_digest(faces)
spatial_checks={'grass_material_count':len(meadow_materials),'grass_mesh_count':len(meadow_objects),
    'grass_geometry_uv_sha256':lake_digest(spatial_grass_before),'grass_geometry_uv_preserved':True,
    'field_size':[field_w,field_h],'field_cell_m':field_cell,'field_rgba_float32_sha256':field_sha,
    'boundary_inner_blend_m_estimate':18,'woodland_inner_blend_m_estimate':12,
    'woodland_area_m2':woodland.area,'woodland_role':'surrounding woodland, not campus property boundary',
    'survey_overlap_blend_width_m_estimate':24,'survey_coverage_checks':coverage_checks,
    'north_source_weight_zero_outside_2d_coverage':True,'overlap_x_inner_blend_m_estimate':4,
    'context_mesh_count':len(spatial_contexts),'original_contexts_hidden':True,
    'context_vertices_topology_transforms_uv_and_visibility_preserved':True,
    'context_geometry_uv_sha256':lake_digest(context_mesh_before),
    'source_surface_graph_sha256':lake_digest(facade_graph_state(source_group)),
    'grass_final_graph_sha256':{m.name:lake_digest(facade_graph_state(m.node_tree)) for m in meadow_materials},
    'context_final_graph_sha256':{ob.name:lake_digest(facade_graph_state(ob.data.materials[0].node_tree)) for ob in spatial_contexts},
    'parking_areas':parking_scale_records,'superseded_visible_paint_hidden':len(hidden_paint),
    'illustrative_vehicle_count':len(vehicle_records),'vehicle_part_count':sum(len(row['parts']) for row in vehicle_records),
    'vehicles':vehicle_records,'vehicle_local_meshes_preserved':True,
    'maximum_vehicle_xy_adjustment_m':max(row['placement_shift_xy_m'] for row in vehicle_records),
    'minimum_vehicle_clearance_m':min(row['clearance_above_parking_m'] for row in vehicle_records),
    'new_paint_mesh_count':len(bay_batches),'roof_faces_sha256':spatial_roofs_before,
    'other_existing_materials_preserved':True,'world_and_lighting_preserved':True,
    'other_existing_materials_sha256':lake_digest(spatial_material_before),
    'other_visible_mesh_count':len(spatial_protected_before),'other_visible_meshes_preserved':True,
    'other_visible_mesh_geometry_uv_visibility_sha256':lake_digest(spatial_protected_before)}

# Resolve contact and clipped pitch details without rewriting retained inputs.
# Earlier canopy/spatial checks are construction checkpoints. Final shrub Z,
# derived sports finish and added wheel geometry are recorded separately here.
detail_shrubs=sorted((ob for ob in s.objects if ob.name.startswith('Garden source oval shrub canopy ')),key=lambda ob:ob.name)
detail_tracks=[s.objects['Expansion repaired '+r['name']] for r in D['tracks']]
detail_targets={ob.name for ob in [*detail_shrubs,*detail_tracks]}
detail_protected_before=spatial_mesh_snapshot(ob for ob in s.objects
    if ob.type=='MESH' and not ob.hide_render and ob.name not in detail_targets)
detail_material_before={m.name:lake_digest(facade_graph_state(m.node_tree)) for m in bpy.data.materials if m.use_nodes}
detail_world_before=lake_digest(facade_graph_state(s.world.node_tree))
detail_roofs_before=lake_digest(faces)

def world_height(ob):
    zs=[(ob.matrix_world@v.co).z for v in ob.data.vertices]
    return [min(zs),max(zs)]
def shrub_static_state(ob):
    # World vertices and matrix Z intentionally change; all local geometry,
    # material slots, UV and other transform components must stay identical.
    return spatial_mesh_snapshot([ob])[ob.name][:2],list(ob.location)[:2],list(ob.rotation_euler),list(ob.scale),ob.hide_render

source_shrubs=[ob for ob in s.objects if ob.name.startswith('Garden photo-visible oval shrub ')]
assert len(source_shrubs)==len(detail_shrubs)==8
shrub_records=[];used_shrubs=set()
for crown in detail_shrubs:
    source=min(source_shrubs,key=lambda ob:(ob.location-crown.location).xy.length)
    assert (source.location-crown.location).xy.length<1e-5 and source.name not in used_shrubs
    used_shrubs.add(source.name);static_before=shrub_static_state(crown)
    source_before=spatial_mesh_snapshot([source]);old_height=world_height(crown);source_height=world_height(source)
    assert old_height[1]>old_height[0] and old_height[0]-source_height[1]>1
    delta=source_height[1]+.08-old_height[1];crown.location.z+=delta;bpy.context.view_layer.update()
    new_height=world_height(crown)
    assert abs(new_height[1]-source_height[1]-.08)<1e-5
    assert new_height[0]<=source_height[1] and new_height[0]>.506+.10
    assert static_before==shrub_static_state(crown) and source_before==spatial_mesh_snapshot([source])
    shrub_records.append({'crown':crown.name,'source':source.name,'source_world_z':source_height,
        'old_crown_world_z':old_height,'new_crown_world_z':new_height,'z_adjustment_m':delta,
        'xy_local_mesh_uv_slots_rotation_scale_visibility_preserved':True,'source_shrub_preserved':True,
        'static_sha256':lake_digest(static_before),'source_sha256':lake_digest(source_before)})

# Closed tyre cylinders touch the existing parking plane. Their complete XY
# bounds stay inside the original 1.8 x 4.2 m body footprint and assigned bay.
rubber=n['mat']('Expansion illustrative tyre rubber',(.017,.022,.020),.96)
hub=n['mat']('Expansion illustrative wheel hubs',(.24,.27,.26),.52)
wheels=n['Mesh']('Expansion vehicle ground contact wheels');wheel_records=[]
def detail_cylinder(batch,a,b,radius,material):
    a,b=Vector(a),Vector(b);axis=(b-a).normalized();side=axis.cross(Vector((0,0,1))).normalized()
    up=axis.cross(side).normalized();rings=[]
    for centre in (a,b):
        rings.append([centre+(side*math.cos(k*math.tau/16)+up*math.sin(k*math.tau/16))*radius for k in range(16)])
    for k in range(16):batch.face([rings[0][k],rings[0][(k+1)%16],rings[1][(k+1)%16],rings[1][k]],material)
    batch.face(list(reversed(rings[0])),material);batch.face(rings[1],material)
for row in vehicle_records:
    body=s.objects[row['body']];rot=Matrix.Rotation(body.rotation_euler.z,3,'Z');centre=body.location
    assigned=min(bays,key=lambda bay:bay.centroid.distance(Point(centre.x,centre.y)))
    for side in (-1,1):
        for along in (-1.25,1.25):
            a=Vector((side*.72,along,parking_z+.232));b=Vector((side*.899,along,parking_z+.232))
            a=Vector((centre.x,centre.y,0))+rot@a;b=Vector((centre.x,centre.y,0))+rot@b
            detail_cylinder(wheels,a,b,.23,rubber)
            # A shallow outer hub, also contained by the original body width.
            inset=b-(b-a).normalized()*.012;detail_cylinder(wheels,inset,b,.095,hub)
            footprint=Polygon([tuple(Vector((centre.x,centre.y,0))+rot@Vector((xx,yy,0)))[:2]
                for xx,yy in [(min(side*.72,side*.899),along-.23),(max(side*.72,side*.899),along-.23),
                    (max(side*.72,side*.899),along+.23),(min(side*.72,side*.899),along+.23)]])
            assert assigned.buffer(1e-5).covers(footprint)
            wheel_records.append({'body':body.name,'side':side,'along_m':along,'radius_m_estimate':.23,
                'contact_above_paving_m':.002,'footprint_inside_assigned_bay':True})
wheel_object=wheels.finish();assert len(wheel_records)==56
assert abs(min((wheel_object.matrix_world@v.co).z for v in wheel_object.data.vertices)-parking_z-.002)<1e-5

# Preserve all original base and running-lane faces. Replace only the former
# clipped grass stripes, pitch lines and goals with a fully contained finish.
pitch_records=[]
for track_row,old in zip(D['tracks'],detail_tracks):
    original=s.objects[track_row['name']];inner_faces=[]
    for face in original.data.polygons:
        pts=[original.matrix_world@original.data.vertices[i].co for i in face.vertices]
        if original.data.materials[face.material_index].name=='Turf dark' and all(abs(p.z-.20)<.001 for p in pts):
            g=Polygon([(p.x,p.y) for p in pts])
            if g.is_valid and g.area>1e-8:inner_faces.append(g)
    field=unary_union(inner_faces);safe_field=field.buffer(-.65);assert not safe_field.is_empty
    batch=n['Mesh']('Expansion contained pitch '+track_row['id']);kept=[];removed=0
    for face in old.data.polygons:
        pts=[old.matrix_world@old.data.vertices[i].co for i in face.vertices];material=old.data.materials[face.material_index]
        replace_finish=(material.name in ('Turf light','Turf dark') and min(p.z for p in pts)>.21) or (
            material.name=='Court and road lines' and (max(p.z for p in pts)>.249 or min(p.z for p in pts)<.15))
        if replace_finish:removed+=1;continue
        values=[list(p) for p in pts];batch.face(values,material);kept.append([values,material.name])
    angle=math.radians(track_row['angle']);across=Vector((math.cos(angle),-math.sin(angle),0));depth=Vector((math.sin(angle),math.cos(angle),0))
    centre=gp(track_row['center'],source=track_row.get('source','satellite'))
    def pitch_rectangle(width,length,lo=-.5,hi=.5):
        return Polygon([tuple(centre+across*x+depth*y)[:2] for x,y in
            [(-width/2,length*lo),(width/2,length*lo),(width/2,length*hi),(-width/2,length*hi)]])
    coordinates=[Vector((x,y,0)) for x,y in field.exterior.coords]
    width=(max(p.dot(across) for p in coordinates)-min(p.dot(across) for p in coordinates))*.90
    length=width*1.55;low,high=0.,1.
    for _ in range(40):
        mid=(low+high)/2
        if safe_field.covers(pitch_rectangle(width*mid,length*mid)):low=mid
        else:high=mid
    width*=low;length*=low;pitch=pitch_rectangle(width,length)
    assert safe_field.buffer(1e-7).covers(pitch) and pitch.area>100
    for stripe in range(12):batch.plane(pitch_rectangle(width,length,-.5+stripe/12,-.5+(stripe+1)/12),.225,
        bpy.data.materials['Turf dark' if stripe%2==0 else 'Turf light'])
    def pp(x,y):return centre+across*x+depth*y
    painted=[pitch.boundary.buffer(.05,join_style='mitre'),
        LineString([tuple(pp(-width/2,0))[:2],tuple(pp(width/2,0))[:2]]).buffer(.05,cap_style='flat'),
        Point(centre.x,centre.y).buffer(width*.13,resolution=64).boundary.buffer(.05)]
    line_material=bpy.data.materials['Court and road lines'];goal_width=width*.11;goal_height=2.4
    for end in (-1,1):
        yy=end*length/2;box_depth=length*.14
        painted.append(LineString([tuple(pp(x,y))[:2] for x,y in
            [(-width*.29,yy),(-width*.29,yy-end*box_depth),(width*.29,yy-end*box_depth),(width*.29,yy)]]).buffer(.05,cap_style='flat',join_style='mitre'))
        for side in (-1,1):
            post=pp(side*goal_width/2,yy);post.z=.225+goal_height/2
            batch.box(post,(.08,.08,goal_height),line_material,-angle)
        cross=pp(0,yy);cross.z=.225+goal_height
        batch.box(cross,(goal_width+.08,.08,.08),line_material,-angle)
    paint=unary_union(painted);assert paint.difference(field).area<1e-7
    batch.plane(paint,.255,line_material);new=batch.finish();old.hide_render=True
    actual=[]
    for face in list(new.data.polygons)[:len(kept)]:
        actual.append([[list(new.matrix_world@new.data.vertices[i].co) for i in face.vertices],new.data.materials[face.material_index].name])
    assert lake_digest(actual)==lake_digest(kept)
    pitch_records.append({'id':track_row['id'],'source_track':track_row['name'],'replaced_finish':old.name,
        'field_area_m2':field.area,'pitch_width_m_estimate':width,'pitch_length_m_estimate':length,
        'pitch_area_m2':pitch.area,'paint_outside_inner_field_m2':paint.difference(field).area,
        'closed_rectangle_and_four_corners':pitch.exterior.is_ring and len(pitch.exterior.coords)==5,
        'retained_base_lane_face_count':len(kept),'retained_base_lane_geometry_sha256':lake_digest(kept),
        'running_lane_geometry_materials_preserved':True,'replaced_finish_face_count':removed,
        'finish_geometry_sha256':lake_digest(spatial_mesh_snapshot([new]))})

detail_protected_after=spatial_mesh_snapshot(s.objects[name] for name in detail_protected_before)
assert detail_protected_before==detail_protected_after
assert detail_material_before=={name:lake_digest(facade_graph_state(bpy.data.materials[name].node_tree)) for name in detail_material_before}
assert detail_world_before==lake_digest(facade_graph_state(s.world.node_tree)) and detail_roofs_before==lake_digest(faces)
detail_checks={'shrub_count':8,'shrubs':shrub_records,'vehicle_count':14,'wheel_count':56,
    'body_clearance_m_estimate':.16,'wheel_geometry_sha256':lake_digest(spatial_mesh_snapshot([wheel_object])),
    'wheels':wheel_records,'pitch_count':4,'pitches':pitch_records,
    'other_existing_visible_mesh_count':len(detail_protected_before),'other_existing_visible_meshes_preserved':True,
    'other_existing_visible_mesh_sha256':lake_digest(detail_protected_before),
    'original_material_graphs_preserved':True,'original_material_graphs_sha256':lake_digest(detail_material_before),
    'world_roof_faces_preserved':True,'world_graph_sha256':detail_world_before,'roof_faces_sha256':detail_roofs_before}
# Late native craft pass. Earlier fingerprints are construction checkpoints,
# while every final change below is independently scoped and protected.
craft_modules={};craft_module_sha={}
for key in ('canopy_volume','ground_contact','facade_depth'):
    namespace={'__name__':key,'__file__':str(ROOT/'scripts'/(key+'.py'))}
    craft_module_path=ROOT/'scripts'/(key+'.py');craft_module_bytes=craft_module_path.read_bytes()
    craft_module_sha['scripts/'+key+'.py']=hashlib.sha256(craft_module_bytes).hexdigest()
    exec(compile(craft_module_bytes,namespace['__file__'],'exec'),namespace)
    craft_modules[key]=namespace
craft_changed=[ob for ob in crowns if not ob.name.startswith('Garden source oval shrub canopy')]
craft_changed += [s.objects['Garden satellite visible small eastern pond'],s.objects['Garden source eastern pond bank']]
craft_changed += craft_modules['facade_depth']['facade_target_objects'](globals())
craft_changed_names={ob.name for ob in craft_changed}
craft_protected_before=spatial_mesh_snapshot(ob for ob in s.objects
    if ob.type=='MESH' and not ob.hide_render and ob.name not in craft_changed_names)
craft_material_before={m.name:lake_digest(facade_graph_state(m.node_tree)) for m in bpy.data.materials if m.use_nodes}
craft_world_before=lake_digest(facade_graph_state(s.world.node_tree));craft_roofs_before=lake_digest(faces)
print('NATIVE CHECK: retained canopy and ground contact',flush=True)
craft_canopy=craft_modules['canopy_volume']['add_canopy_volume'](globals())
craft_ground=craft_modules['ground_contact']['add_ground_contact'](globals())
print('NATIVE CHECK: retained window depth and glass first hits',flush=True)
craft_facade=craft_modules['facade_depth']['add_facade_depth'](globals())
print('NATIVE CHECK: retained window depth passed',craft_facade['window_assembly_count'],flush=True)
bpy.context.view_layer.update()
assert craft_protected_before==spatial_mesh_snapshot(s.objects[name] for name in craft_protected_before)
assert craft_material_before=={name:lake_digest(facade_graph_state(bpy.data.materials[name].node_tree)) for name in craft_material_before}
assert craft_world_before==lake_digest(facade_graph_state(s.world.node_tree)) and craft_roofs_before==lake_digest(faces)
craft_checks={'canopy':craft_canopy,'ground':craft_ground,'facade':craft_facade,
    'other_existing_visible_mesh_count':len(craft_protected_before),'other_existing_visible_meshes_preserved':True,
    'other_existing_visible_mesh_sha256':lake_digest(craft_protected_before),
    'existing_material_graphs_preserved':True,'existing_material_graphs_sha256':lake_digest(craft_material_before),
    'world_roof_faces_preserved':True,'world_graph_sha256':craft_world_before,'roof_faces_sha256':craft_roofs_before}

# Source-bounded ground and courtyard detail; original models remain in memory.
# Earlier craft signatures are checkpoints, not the final lawn BSDF outputs.
landscape_modules={}
for key in ('landscape_beds','courtyard_finish','landscape_surface'):
    path=ROOT/'scripts'/(key+'.py')
    namespace={'__name__':key,'__file__':str(path)}
    exec(compile(path.read_bytes(),str(path),'exec'),namespace)
    landscape_modules[key]=namespace
landscape_beds_checks=landscape_modules['landscape_beds']['add_landscape_beds'](globals())
landscape_courtyard_checks=landscape_modules['courtyard_finish']['add_courtyard_finish'](globals())
landscape_surface_checks=landscape_modules['landscape_surface']['add_landscape_surface'](globals())
landscape_checks={'surface':landscape_surface_checks,'beds':landscape_beds_checks,
    'courtyards':landscape_courtyard_checks}

# Finish actual facade components and source-supported planting/outer ground.
# Prior craft/landscape guards are checkpoints before these material slots and
# low planting additions, rather than final whole-scene appearance signatures.
site_modules={}
for key in ('facade_finish','hardscape_transition','planting_finish'):
    path=ROOT/'scripts'/(key+'.py')
    namespace={'__name__':key,'__file__':str(path)}
    exec(compile(path.read_bytes(),str(path),'exec'),namespace)
    site_modules[key]=namespace
print('NATIVE CHECK: facade component finish',flush=True)
site_facade=site_modules['facade_finish']['add_facade_finish'](globals())
print('NATIVE CHECK: facade finish passed',site_facade['window_assembly_count'],flush=True)
site_hardscape=site_modules['hardscape_transition']['add_hardscape_transition'](globals())
print('NATIVE CHECK: outer hardscape passed',site_hardscape['used_target_count'],flush=True)
site_planting=site_modules['planting_finish']['add_planting_finish'](globals())
print('NATIVE CHECK: retained planting passed',site_planting['source_region_count'],site_planting['total_polygon_triangle_count'],flush=True)
site_checks={'facade':site_facade,'hardscape':site_hardscape,'planting':site_planting}
s.view_settings.view_transform='Standard';s.view_settings.look='Medium High Contrast';s.view_settings.exposure=-.1
s.render.resolution_x=W;s.render.resolution_y=H;s.render.resolution_percentage=100
s.cycles.samples=16 if final else 8;s.render.use_border=False;s.render.use_crop_to_border=False
bpy.context.view_layer.update()
records=[]
for row in baseline['records']:
    polys=[]
    for f in faces[row['id']]:
        pp=[world_to_camera_view(s,cam,Vector(p)) for p in f]
        g=Polygon([(p.x*W,(1-p.y)*H) for p in pp])
        if g.is_valid and g.area>1e-6:polys.append(g)
    g=unary_union(polys);parts=list(g.geoms) if hasattr(g,'geoms') else [g];p=g.representative_point()
    records.append({**row,'polygons':[[list(v.exterior.coords),*[list(r.coords) for r in v.interiors]] for v in parts],'anchor':[p.x,p.y]})
regions=[]
for row in baseline['regions']:
    ps=[p for r in records if r['region']==row['id'] for poly in r['polygons'] for ring in poly for p in ring]
    regions.append({**row,'bounds':[min(p[0] for p in ps),min(p[1] for p in ps),max(p[0] for p in ps),max(p[1] for p in ps)]})
# Near frames follow fixed photographed blocks. The full regional building
# lists and whole-campus overview remain available while phones start closer.
region_focus_sources={
    'north':('satellite',[(627,383),(755,383),(755,539),(627,539)]),
    'extension':('north-extension',[(485,425),(747,425),(747,776),(485,776)]),
    'middle':('satellite',[(410,994),(639,994),(639,1210),(410,1210)]),
}
region_focus_records={}
for row in regions:
    if row['id'] not in region_focus_sources:continue
    source,pixels=region_focus_sources[row['id']]
    points=[gp(pixel,z,source=source) for pixel in pixels for z in (0,28)]
    projected=[world_to_camera_view(s,cam,p) for p in points]
    ps=[(p.x*W,(1-p.y)*H) for p in projected]
    frame=[min(p[0] for p in ps),min(p[1] for p in ps),max(p[0] for p in ps),max(p[1] for p in ps)]
    # Other regions may lie outside a diagnostic crop; published whole-campus
    # frames must stay within the native atlas image.
    if not region:assert all(0<=frame[i]<=([W,H,W,H][i]) for i in range(4))
    row['focus_bounds_mobile']=frame;row['mobile_framing']='cover'
    if row['id']=='north':row['focus_bounds']=frame
    region_focus_records[row['id']]={'source':source,'pixel_frame':pixels,'height_envelope_m_estimate':[0,28],
        'projected_frame':frame,'full_record_count':row['count'],'scope':'Initial view only, entire regional list and source geometry retained'}
checks={'road_roof_intersection_m2':asphalt.intersection(roofs).area,'paving_roof_intersection_m2':paving.intersection(roofs).area,'paving_water_intersection_m2':paving.intersection(water).area,'paving_artifact_cleanup':paving_cleanup,'paired_tree_count':len(pairs),'restored_sports_objects':sport_names,'excluded_context_crowns':excluded,'record_count':len(records),'north_detail':north_detail_checks,'garden_detail':garden_detail_checks,'central_parking_detail':central_parking_checks,'road_mark_detail':road_mark_checks,'b08_roof_detail':b08_roof_checks}
checks['track_finish_repairs']=track_repairs
checks['material_pass_roof_faces_preserved']=roof_faces_preserved
checks['surface_finish']=surface_finish_checks
checks['formal_garden_beds']=formal_bed_checks
checks['retained_tree_root_finish']=root_pit_checks
checks['ground_and_glazing_finish']=finish_relief_checks
checks['solar_array_finish']=solar_finish_checks
checks['glazing_recess_finish']=glazing_recess_checks
checks['canopy_relief']=canopy_relief_checks
checks['canopy_forms']=canopy_form_checks
checks['fine_ground_and_roof_finish']=fine_surface_checks
checks['architectural_edge_finish']={'material_count':len(architectural_edge_materials),'radius_m_estimate':.035,'samples':2,'mesh_positions_changed':False}
checks['central_roof_finish']=central_roof_checks
checks['stone_edge_contact']=stone_contact_checks
checks['lake_surface']=lake_surface_checks
checks['meadow_surface']=meadow_checks
checks['foliage_surface']=foliage_checks
checks['facade_contrast']=facade_checks
assert all(v<1e-7 for k,v in checks.items() if k.endswith('_m2'))
checks['landscape_detail']=landscape_checks
checks['site_finish']=site_checks
sources={**ctx['sources'],**{p:sha(ROOT/p) for p in ['scripts/campus_expansion.py','scripts/north_pilot_detail.py','scripts/garden_detail.py','scripts/canopy_volume.py','scripts/ground_contact.py','scripts/facade_depth.py','scripts/landscape_beds.py','scripts/courtyard_finish.py','scripts/landscape_surface.py','scripts/facade_finish.py','scripts/hardscape_transition.py','scripts/planting_finish.py','output/garden-tree-canopy.png','model/campus/references/north-extension.jpg','model/campus/references/north-extension.json']}}
assert all(sources[path]==value for path,value in craft_module_sha.items())
meta={'title':'太湖校园地图','coverage':'campus','width':W,'height':H,'records':records,'regions':regions,'camera':{'position':list(cam.location),'rotation_euler':list(cam.rotation_euler),'ortho_scale':cam.data.ortho_scale},'roof_faces_world':faces,'sources':sources,'checks':checks,'samples':s.cycles.samples,'method':'Native orthographic Blender render of retained roof/road geometry and source tree centres; source-bounded derived architecture/landscape finishes and opaque frame apertures integrated in one scene','limitations':'Heights and unseen facades remain estimated. No surveyed routing network. Names outside B06 remain descriptive.','render_status':'generated_needs_visual_review','generation_commands':['Blender --background -t 4 --python scripts/campus_expansion.py -- --final'],'landscape_revision':{'tree_pairs':pairs,'ground_source':'Fixed roads.json union layers and layout.json; satellite-visible garden island, forecourt, planted row and small pond bounded to their source image','source_ground_details':source_details},'ground_revision':ctx['ground_revision']}
meta['landscape_detail_revision']={'basis':'Retained four geographic lawn materials, four source planting caps and three existing source-traced courtyard finishes',
    'method':'Metre-based lawn patch/tuft/blade shading, ground-contact low foliage inside source beds and sparse perimeter/cross stone courses inside retained paving',
    'checks':landscape_checks,'estimated':['surface colour and noise scales','low foliage forms and heights','paving course sizes and pigment'],
    'preserved':['original input assets','existing mesh geometry and source footprints','source tree positions','roof selection geometry','camera','water and road outlines'],
    'reference_alignment_status':'not_met','user_visual_acceptance':'pending'}
meta['site_finish_revision']={'basis':'Existing estimated peripheral window assemblies, retained low source planting caps and actual ground hardscape at the model exterior',
    'method':'Role-specific facade finish slots, source-bounded low planting and a geographic shader transition on outer hardscape only',
    'checks':site_checks,'estimated':['facade finish hierarchy and pigment','low planting forms and heights','outer hardscape blend width'],
    'preserved':['original input assets','all existing vertices/topology/UV','source planting footprints','tree positions','roof selection geometry','camera','road and water outlines'],
    'checkpoint_note':'Earlier craft, landscape and material-slot hashes describe their construction phases before this finish; site_finish checks describe these later changes.',
    'reference_alignment_status':'not_met','user_visual_acceptance':'pending'}
meta['b08_roof_revision']={'basis':'model/central-campus/references/campus-aerial.jpg','method':'Narrow roof-joint surfaces clipped to the existing B08 lakeside roof, excluding the photographed glazed segment','estimated':['joint spacing','exact module count'],'checks':b08_roof_checks}
meta['material_revision']={'roof_finish':rest['roof_finish'],'paving_course_m':[1.10,.72],
    'canopy_shadow_fill':.045,'basis':'Existing source roof, paving and tree geometry; finish dimensions and shadow fill are presentation estimates',
    'preserved':['roof faces','building heights','tree centres','ground outlines','camera','130 selection records']}
meta['surface_finish_revision']={'basis':'Existing source-bounded meshes and photo-supported red masonry; microtexture, mortar dimensions and shading parameters are presentation estimates',
    'wall_materials':wall_finishes,'photo_supported_central_materials':photo_supported_central_materials,
    'paving_materials':paving_finishes,'masonry_objects':brick_objects,
    'method':'Fine surface grain and metre-scaled masonry pigment; limited ambient occlusion derived from actual scene geometry; lake and pond roughness/ripples only',
    'checks':surface_finish_checks}
meta['planting_finish_revision']={'basis':'Fixed layout.json north-extension lawn outlines and retained joined-context tree centres on existing paving',
    'method':'Correct planting source frame and plaza occlusion; bounded soil/stone root finishes without moving or adding trees',
    'estimated':['root finish radius','stone course width','finish elevations'],
    'formal_beds':formal_bed_checks,'retained_tree_roots':root_pits,'root_checks':root_pit_checks}
meta['ground_and_glazing_revision']={'basis':'Actual used paving/curb meshes and existing window/glass material slots',
    'method':'Metre-scaled grain and shallow mortar normals on existing stone; camera/normal-derived reflected sky pigment on existing glazing',
    'ground_materials':ground_relief_materials,'glazing_materials':glazing_materials,
    'estimated':['grain scale','mortar relief','reflection tint','roughness'],
    'preserved':['all geometry','window groups','paving outlines','curb outlines','camera','selection records'],
    'checks':finish_relief_checks}
meta['solar_array_finish_revision']={'basis':['Retained B07 photo-visible solar array geometry','E24 fixed north-extension satellite rooftop zones'],
    'method':'Metre-scaled cell finish on existing individual B07 modules; E24 module joints aligned to retained world-X/Y geometric seams, with shallow shading normals and restrained reflectance',
    'materials':[material.name for material in solar_materials],'objects':solar_objects,
    'estimated':['cell and module dimensions','mortar width','reflectance','surface roughness'],
    'preserved':['existing array positions','existing array geometry','source roof faces','building heights','camera','130 selection records'],
    'checks':solar_finish_checks}
meta['glazing_recess_revision']={'basis':'Actual existing window surrounds and sills',
    'method':'Short-range geometry-derived contact shading and normal-only edge catches on existing panes',
    'materials':glazing_materials,'estimated':['contact distance','influence','normal edge radius'],
    'preserved':['pane positions','window groups','existing reflected sky palette','all source geometry'],
    'checks':glazing_recess_checks}
meta['canopy_relief_revision']={'basis':'Retained source tree centres and existing output/garden-tree-canopy.png texture',
    'method':'Twelve shared broad/offset/split/low crown forms with bounded interior UV variation; source-coordinate SHA-256 allocation, retained object transforms and mesh XY; existing leaf image and daylight',
    'estimated':['crown vertical profile','leaf colour variation','leaf normal relief'],
    'checks':canopy_relief_checks}
meta['canopy_form_revision']={'basis':'Existing source tree/shrub centres, retained crown outer XY rectangle and output/garden-tree-canopy.png',
    'method':'Four crown families by three forms, allocated by SHA-256 of category and micron-rounded source XY, using big-endian first and second four bytes; low family only for the eight existing shrubs',
    'estimated':['vertical profiles','crown shape families','interior leaf/alpha UV deformation'],
    'preserved':['all source tree centres','crown object XYZ/rotation/scale','mesh vertex XY','outer UV boundary','underlying tree meshes','original leaf image','camera and roof selection geometry'],
    'limitations':'Species and crown dimensions are not surveyed. Interior alpha silhouette changes within retained XY bounds. Twelve forms still share one image and do not establish reference parity.',
    'local_height_peaks_m_estimate':[list(row) for row in form_peaks],'checks':canopy_form_checks}
meta['architectural_edge_revision']={'basis':'Existing facade/trim geometry','method':'Normal-only Cycles bevel, no vertex changes',
    'materials':architectural_edge_materials,'radius_m_estimate':.035,'samples':2}
meta['fine_ground_and_roof_revision']={'basis':'Actual used flat-roof and source-bounded meadow meshes; fixed aerial pigment and existing world-coordinate daylight',
    'method':'Reduced aerial pigment on paving; shallow existing roof-joint/fine-grain normals and roughness; fine meadow surface variation preserves its existing source palette',
    'roof_materials':fine_roof_materials,'meadow_materials':fine_meadow_materials,
    'estimated':['pigment influence','grain scale','relief depth','roof roughness'],
    'preserved':['all source geometry','roof faces','grass outlines','paving outlines','camera','130 selection records'],
    'checks':fine_surface_checks}
meta['central_roof_finish_revision']={'basis':'Retained photo-supported B06/B07/B08 roof meshes and fixed campus-aerial.jpg',
    'method':'Metre tangent-plane UV along B07 eaves/up slopes; B08 first photo-traced bar edges; existing tile courses and metal seam geometry retained; restrained roughness, geometry-derived contact and normal-only edges',
    'materials':[m.name for m in central_roof_materials],'objects':central_roof_objects,
    'estimated':['tile dimensions','grain scale','roughness','contact distance and influence','normal edge radius'],
    'preserved':['whole central meshes world vertices, topology and material indices','roof ribs, seams, ridges and fixtures','all roof selection faces','source building heights','camera'],
    'checks':central_roof_checks}
meta['stone_edge_contact_revision']={'basis':'Actual used source-bounded road/planting curbs and stone water banks',
    'method':'Limited short-range contact shading and normal-only edges on retained stone; no added contact-shadow meshes',
    'materials':stone_contact_materials,'estimated':['contact distance and influence','normal edge radius'],
    'preserved':['curb and bank outlines','water outline and levels','all mesh geometry'],
    'checks':stone_contact_checks}
meta['lake_surface_revision']={'basis':['Retained six water meshes and shore_tint field',
    'model/central-campus/references/lake-photo.jpg','public/assets/campus-reference.webp'],
    'method':'One shared metre-coordinate low-frequency cool-green pigment field, weak bounded crest tint, two directional normal-only ripple layers and bounded roughness; retained shoreline tint, lake bed, water level and sky',
    'estimated':['pigment variation','stylised ripple tint','normal ripple scale and amplitude','roughness','surface transmission'],
    'preserved':['all water/bank/bed vertices and topology','water level','shore_tint','other material graphs during this pass','world and lighting during this pass','IOR','camera and selection records'],
    'limitations':'Water appearance is estimated; not measured water depth, water quality, weather or a recorded reflection. Reference craft parity remains unmet.',
    'checks':lake_surface_checks}
meta['meadow_surface_revision']={'basis':['Four actual used source-bounded meadow materials',
    'model/campus/references/satellite.jpg','model/campus/references/north-extension.jpg','public/assets/campus-reference.webp'],
    'method':'Retain original geographic colour branch; warm ratio bounds green/warm procedural grass detail influence; metre-scale visible flecks, chained normal-only grain and matte roughness. Lower woodland and warm-patch influence.',
    'estimated':['grass grain scale','detail palettes and influence','warm ratio interpretation','normal amplitude','roughness'],
    'preserved':['all existing meadow mesh world vertices/topology/material indices/transforms/UV/visibility',
        'original source pigment nodes and their internal links','other materials/world/lighting during this pass',
        'lake and canopy recipe','camera and roof selection records'],
    'limitations':'Surface detail is stylised, not surveyed grass species, density, health or maintenance. Source colour guides appearance and is not claimed to be pixel-identical. Reference craft parity remains unmet.',
    'checks':meadow_checks}
meta['foliage_surface_revision']={'basis':['Retained output/garden-tree-canopy.png, two canopy materials and 1858 source-positioned crown meshes','public/assets/campus-reference.webp'],
    'method':'Stable source-coordinate Object Color channels replace name-based random HSV drivers within prior ranges; metre-scale leaf group colour/normals and bounded baked-light gain; only colour desaturation at alpha edges',
    'estimated':['per-tree colour allocation','leaf group scale/tone','baked image light compensation','colour-only edge saturation','normal amplitude'],
    'preserved':['all existing crown vertices/faces/material slots/transforms/UV/visibility','original image sampling and alpha surface chain','other materials/world/lighting during this pass','source tree centres','lake and meadow recipes','camera and roof selection records'],
    'limitations':'Still one shared leaf image and twelve shapes. Colour/clump organisation is stylised, not surveyed species, crown structure or leaf health. No new silhouette or real-species diversity; reference craft parity remains unmet.',
    'checks':foliage_checks}
meta['facade_contrast_revision']={'basis':['Eight actual used second-batch peripheral reconstruction wall/trim/pane materials','public/assets/campus-reference.webp'],
    'method':'Retain original pigment, reflected-sky colour, geometry-derived AO and normal chains; bounded wall/trim gains and smooth pane pigment gain by retained building Generated.Z bounds',
    'scope':'Shared second-batch materials include some north photographed dorm families, not a south-only or unphotographed-only pass. Original central B06/B07/B08 and unsuffixed north materials excluded.',
    'estimated':['wall/trim colour gain','building-height pane pigment response'],
    'preserved':['all targeted building world vertices/topology/material slots/indices/transforms/UV/visibility','source colour nodes and internal links except replaced final Base Color edge','all other BSDF input links/defaults including alpha, reflection settings, AO and normal chains','scene object inventory and mesh count','other material/world/light graphs during this pass','source roof faces/tree centres/camera'],
    'limitations':'Pigment contrast only; no new openings, balconies, blinds, facade structure or measured reflection. Existing repetitive facade geometry and estimated unseen details remain; reference parity unmet.',
    'checks':facade_checks}
meta['spatial_revision']={'basis':['Fixed layout.json ground, adjacent-woodland and parking outlines',
    'Two retained georeferenced source images','Fourteen original illustrative vehicles','public/assets/campus-reference.webp'],
    'method':'Shared physically lit geographic source surface; world-XY inner boundary/woodland transition; overlap-only survey blend; complete metre-based parking bays and access aisles; reuse and align original scale-reference cars above paving',
    'preserved':['source scene and GLB files','building/roof and tree source geometry','fixed ground/parking outlines and holes','existing grass world vertices/topology/UV','world and lighting'],
    'estimated':['18m outer and 12m woodland inner blend','24m source overlap blend','2.65x5.10m bays and 6.20m access aisles','illustrative vehicle bay alignment and ground clearance'],
    'limitations':'Source woodland is not a property boundary. Parking layout/vehicle occupancy are illustrative, not surveyed capacity or live availability; original car XY adjusted only for bay alignment. Photographic surroundings and repetitive architecture still differ from reference craft.',
    'checks':spatial_checks}
meta['checks']['spatial_continuity_and_scale']=spatial_checks
meta['detail_contact_revision']={'basis':['Existing source parking polygons and adjacent retained roads',
    'Eight original oval planting shrub meshes and source XY positions','Four original stadium inner fields and running-lane geometry'],
    'method':'Reserve connected side/front parking aisles, align original vehicles with contained contact tyres, lower eight crown cutouts into their retained shrub volumes, and replace only clipped pitch finish with closed inner-field rectangles',
    'estimated':['6.20m parking circulation strips','0.16m body and 0.002m tyre clearance','0.23m tyre radius',
        'Shrub crown top 0.08m above retained underlying leaf volume','1.55 pitch aspect and 2.4m illustrative goals'],
    'limitations':'Display geometry, not surveyed parking capacity/occupancy, certified driving routes, botanical heights or regulation sports facilities. Earlier canopy/spatial checks are pre-detail checkpoints; eight final crown Z values and replaced pitch finish are described here.',
    'checks':detail_checks}
meta['checks']['detail_contact_and_layout']=detail_checks
meta['craft_revision']={'basis':['Retained source tree centres and crown envelopes',
    'Existing eastern garden pond and source-bounded tree-root finishes',
    'Existing estimated peripheral window geometry','public/assets/campus-reference.webp'],
    'method':'Shared folded-leaf volume within retained crown bounds; pond and root-finish contact walls; open opaque surround rings and inner reveals with inward pane/mullion/transom offsets; wall/outer-frame/sill geometry protected',
    'estimated':['Leaf-spray shape and pigment','Pond and tree-root finish elevations','Window recess depths'],
    'preserved':['Original input files','Source tree centres','Roof faces','Camera','130 selection records','Eight source shrub crowns','Existing material graphs'],
    'checks':craft_checks,
    'limitations':'Earlier canopy/foliage/facade/detail hashes are pre-craft construction checkpoints; final appearance-crown visibility, leaf volume, opaque frame apertures and pane normal offsets are recorded here. Layout is source-backed; hidden facades, leaf groups and finish elevations remain estimates. Reference craft alignment remains unmet.'}
meta['checks']['source_craft_and_contact']=craft_checks
meta['daylight_revision']={'basis':'Existing geometry and retained leaf pigment; reference visual clarity, not surveyed weather',
    'method':'Explicit diffuse sky with stronger directional daylight, reduced canopy emission and bounded leaf-value range; original glossy sky retained',
    'sun_energy':sun.data.energy,'sun_angle_radians':sun.data.angle,'sun_rotation_euler':list(sun.rotation_euler),
    'diffuse_strength':.32,'inherited_diffuse_strength':inherited_diffuse_strength,'diffuse_color':[.88,.90,.94,1],
    'exposure':-.1,'canopy_materials':[m.name for m in canopy_daylight_materials],
    'leaf_emission_strength':.015,'leaf_roughness':.78,'leaf_value_range':[1.08,1.42],
    'preserved':['camera','roof faces','tree centres and XY scale','whole source meshes','source pigment and alpha','glossy sky'],
    'estimated':['illumination','leaf value and roughness'],'user_visual_acceptance':'pending'}
meta['region_focus_revision']={'method':'Fixed source pixel rectangles independently projected by the current atlas camera',
    'regions':region_focus_records,'limitations':'Initial view framing is a presentation choice, not a reduced regional inventory'}
print('EXPANSION READY',W,H,checks,flush=True)
(CACHE/'atlas.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')
if final:
    bridge=subprocess.Popen(['/opt/anaconda3/bin/python',str(ROOT/'scripts/campus_expansion_export.py'),'--stage'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,bufsize=1)
    def send(v):
        bridge.stdin.write(json.dumps(v)+'\n');bridge.stdin.flush();answer=bridge.stdout.readline();assert answer and json.loads(answer).get('ok'),answer
    send({'action':'begin'});s.render.use_border=True;s.render.use_crop_to_border=True;s.render.use_persistent_data=True
    for row in range(2):
        for col in range(4):
            core=(col*W//4,row*H//2,(col+1)*W//4,(row+1)*H//2);x0=max(0,core[0]-24);y0=max(0,core[1]-24);x1=min(W,core[2]+24);y1=min(H,core[3]+24)
            s.render.border_min_x=(x0+.05)/W if x0 else 0;s.render.border_max_x=min(1,(x1+.05)/W)
            s.render.border_min_y=(H-y1+.05)/H if H-y1 else 0;s.render.border_max_y=min(1,(H-y0+.05)/H)
            s.render.filepath=str(CACHE/'render-tile.png');print('EXPANSION TILE',row,col,flush=True);bpy.ops.render.render(write_still=True)
            send({'action':'tile','core':core,'bounds':[x0,y0,x1,y1]})
    send({'action':'finish'});bridge.stdin.close();assert bridge.wait()==0
else:
    s.render.filepath=str(CACHE/'campus.png');bpy.ops.render.render(write_still=True)
    meta['png_sha256']=sha(CACHE/'campus.png');(CACHE/'atlas.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')
for p,h in sources.items():assert sha(ROOT/p)==h,p
print('EXPANSION DONE',flush=True)
