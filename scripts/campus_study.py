"""One-camera north/lake integration, retaining the independent studies.
Blender --background -t 4 --python scripts/campus_study.py [-- --final]
python scripts/campus_study.py --export
Reuse bounded construction sections in memory. No saved scene or source edits.
"""
from pathlib import Path
import sys, json, hashlib, math, io, datetime
ROOT=Path(__file__).resolve().parents[1];CACHE=Path('/tmp/taihu-full');OUT=ROOT/'public/assets'
ASSETS=['campus-atlas.webp','campus-atlas.json','campus-north.webp','campus-north.json',
        'campus-north-before.webp','campus-reference.webp','campus-lake.webp','campus-lake.json',
        'campus-study.webp','campus-study.json']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def capacity():return sum(p.stat().st_size for p in CACHE.rglob('*') if p.is_file())
def size(p):return p.stat().st_size if p.exists() else 0
def change(code,old,new):
    assert code.count(old)==1,old
    return code.replace(old,new)

if '--export' in sys.argv:
    import numpy as np
    from PIL import Image
    sys.path.insert(0,'/tmp/taihu-gis-deps')
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    m=json.loads((CACHE/'atlas.json').read_text());assert m['coverage']=='joined-study'
    assert m['generator_sha256']==sha(Path(__file__))
    for p,h in m['sources'].items():assert sha(ROOT/p)==h,p
    im=Image.open(CACHE/'campus.png').convert('RGB');assert im.size==(3200,2200)
    assert sha(CACHE/'campus.png')==m['png_sha256']
    x,y,z=m['camera']['rotation_euler'];sx,cx=math.sin(x),math.cos(x);sy,cy=math.sin(y),math.cos(y);sz,cz=math.sin(z),math.cos(z)
    rot=np.array([[cz,-sz,0],[sz,cz,0],[0,0,1]])@np.array([[cy,0,sy],[0,1,0],[-sy,0,cy]])@np.array([[1,0,0],[0,cx,-sx],[0,sx,cx]])
    w,h=im.size;pos=np.array(m['camera']['position']);ppm=w/m['camera']['ortho_scale'];errors=[]
    for r in m['records']:
        polys=[]
        for f in m['roof_faces_world'][r['id']]:
            pp=(np.array(f)-pos)@rot;p=Polygon([(w/2+q[0]*ppm,h/2-q[1]*ppm) for q in pp])
            if p.is_valid and p.area>1e-6:polys.append(p)
        union=unary_union(polys).buffer(.003,join_style=2).buffer(-.003,join_style=2)
        old=unary_union([Polygon(p[0],p[1:]) for p in r['polygons']]).buffer(.003,join_style=2).buffer(-.003,join_style=2)
        errors.append(union.hausdorff_distance(old));parts=list(union.geoms) if hasattr(union,'geoms') else [union]
        r['polygons']=[[list(p.exterior.coords),*[list(ring.coords) for ring in p.interiors]] for p in parts]
        point=union.representative_point();r['anchor']=[point.x,point.y]
    assert max(errors)<.02 and len(m['records'])==19
    m['checks']['independent_projection_max_difference_px']=max(errors)
    buffer=io.BytesIO();im.save(buffer,format='WEBP',quality=92,method=6);payload=buffer.getvalue()
    m['image_sha256']=hashlib.sha256(payload).hexdigest();m['image_bytes']=len(payload)
    m['updated']=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()
    m['render_status']='generated_needs_visual_review';m['visual_review']={'status':'pending'};m['frontend_validation']={'status':'pending'}
    m['budget']={'asset_count_limit':10,'asset_bytes_limit':8*1024**2,'cache_bytes_limit':192*1024**2,'source_amplification_limit':256}
    encoded=(json.dumps(m,ensure_ascii=False,indent=2)+'\n').encode()
    total=sum((OUT/p).stat().st_size for p in ASSETS[:8])+len(payload)+len(encoded)
    sourcebytes=sum((ROOT/p).stat().st_size for p in ['scripts/campus_study.py','scripts/lake_study.py','scripts/north_study.py','scripts/campus_atlas.py','scripts/export_atlas.py','scripts/refine_buildings.py','src/CampusAtlas.jsx','src/campusAtlas.css'])
    assert total<8*1024**2 and total/sourcebytes<256 and capacity()<192*1024**2
    (OUT/'campus-study.webp').write_bytes(payload);(OUT/'campus-study.json').write_bytes(encoded)
    print(json.dumps({'image_bytes':len(payload),'ten_asset_total_bytes':total,'projection_max_px':max(errors)}));sys.exit(0)

import bpy
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view
sys.dont_write_bytecode=True;sys.path.insert(0,'/tmp/taihu-gis-deps');sys.path.insert(0,str(ROOT/'scripts'))
from shapely.geometry import Polygon,Point,LineString,box
from shapely.ops import unary_union
sourcepaths=['scripts/campus_study.py','scripts/north_study.py','scripts/lake_study.py','scripts/campus_atlas.py','scripts/export_atlas.py','scripts/refine_buildings.py','model/campus/campus.blend','model/campus/layout.json','model/campus/roads.json','model/campus/references/satellite.jpg','model/campus/references/satellite-export.json','model/central-campus/footprints.json','model/central-campus/references/satellite.jpg','model/central-campus/references/satellite-export.json','model/central-campus/references/campus-aerial.jpg','model/central-campus/references/lake-photo.jpg']
sources={p:sha(ROOT/p) for p in sourcepaths}
CACHE.mkdir(parents=True,exist_ok=True)
assert capacity()-size(CACHE/'campus.png')-size(CACHE/'atlas.json')+9*1024**2<192*1024**2
assert sum(size(OUT/p) for p in ASSETS)<8*1024**2

# Build the complete detailed north block, stopping before its camera/export.
north=ROOT/'scripts/north_study.py';marker='# Lighting and camera keep the baseline orientation exactly'
raw=north.read_text();assert raw.count(marker)==1;code=raw.split(marker)[0]
code=change(code,"s=bpy.context.scene\nD=json.loads", "s=bpy.context.scene\noriginal_names=set(o.name for o in s.objects)\nD=json.loads")
# Joined study architecture pass: retain all source roofs and heights while
# replacing the uniform N31 window grid with its photographed facade family.
window_start="  for floor in range(int(h/3.8)):"
window_end=" # source roof skylight interpreted inside roof perimeter"
assert code.count(window_start)==1 and code.count(window_end)==1
start=code.index(window_start);end=code.index(window_end,start)
code=code[:start]+'''  def facade(d,z,w,hh,depth,material,offset=.10):
   c=av+t*d+out*offset;c.z=z;bm.box(c,(w,depth,hh),material,ang)
  # Wide central glazing and narrow grouped end lights, read from the aerial.
  # Hidden elevations use the same family; counts and dimensions are estimates.
  side=min(5.0,n*.19);middle=n-2*side
  for floor in range(int(h/3.8)):
   z=.42+(floor+.5)*3.8
   if shared and z<19.4:continue
   facade(n/2,z-1.45,n,.38,.40,white)
   facade(n/2,z,middle,1.88,.14,glass,.12)
   panes=max(2,round(middle/1.3))
   for j in range(panes+1):
    facade(side+j*middle/panes,z,.075,1.95,.19,white,.23)
   facade(n/2,z+.40,middle,.065,.18,white,.24)
   facade(n/2,z-.98,middle+.26,.16,.54,white,.22)
   for origin in [side/2,n-side/2]:
    for j in [-1,0,1]:
     d=origin+j*side*.23
     facade(d,z,side*.135,2.13,.13,glass,.10)
     for sign in [-1,1]:facade(d+sign*side*.08,z,.075,2.21,.22,white,.20)
     facade(d,z+.38,side*.135,.055,.18,white,.21)
   for d in [side-.38,n-side+.38]:facade(d,z,.40,3.58,.34,cream,.18)
  # A recessed glazed entrance and shallow canopy on the exposed east front.
  if out.x>.9 and not shared:
   facade(n/2,1.92,min(6.8,middle),2.95,.17,glass,.15)
   for j in [-1,0,1]:facade(n/2+j*1.35,1.90,.09,2.97,.22,white,.27)
   facade(n/2,3.55,min(8.2,n-.5),.24,1.50,white,.65)
''' + code[end:]
# Strong continuous brick piers and recessed jambs distinguish the academic
# facade from the pale dining block without changing roof or courtyard bounds.
code=change(code,"academic.finish()",'''academic.finish()
piers=Mesh('Joined academic masonry piers')
for facade_row in academic_facades:
 a,b=[Vector(p) for p in facade_row['edge_world']];v=b-a;length=v.length
 t=v/length;out=Vector((t.y,-t.x,0));angle=math.atan2(t.y,t.x)
 bays=facade_row['bays_estimate'];step=length/bays
 for j in range(1,bays):
  d=j*step
  if facade_row['photo_east_front'] and abs(d-length*.59)<4.4:continue
  # Recessed wall remains behind each window; piers stop below the glass ribbon.
  top=14.80 if facade_row['photo_east_front'] else 17.95
  c=a+t*d-out*.02;c.z=(.90+top)/2
  piers.box(c,(.25,.25,top-.90),brick,angle)
piers.finish()''')
n={'__file__':str(north),'__name__':'__joined_north__'};exec(compile(code,str(north),'exec'),n)
s=n['s'];D=n['D'];gp=n['gp'];nshape=n['shape']
central_patch=Polygon(json.loads((ROOT/'model/campus/roads.json').read_text())['central_patch_world_xy']).buffer(7)
roi=box(-245,30,275,685)
# Remove north's broad display ground. One shared site ground is built below.
s.objects['Study landscape base'].hide_render=True
north_tree_ids=set()
for ob in s.objects:
    if ob.name.startswith('Study source tree '):
        index=int(ob.name.rsplit(' ',1)[1]);north_tree_ids.add(index)
        if central_patch.covers(Point(ob.location.x,ob.location.y)):ob.hide_render=True
    if ob.name.startswith('Study source understory ') and central_patch.covers(Point(ob.location.x,ob.location.y)):ob.hide_render=True
background_trees=[]
for name in n['original_names']:
    ob=s.objects.get(name)
    if ob is None:continue
    if name.startswith(('B06 Central','B07 Central','B08 Central','Tree trunk ','Tree branch','B08 island understory','Forecourt low hedge')):
        ob.hide_render=False
    elif name.startswith('Canopy ') and name[7:].isdigit():
        ident=int(name[7:]);p=ob.matrix_world.translation
        central=ob.get('origin')=='central-study source-positioned canopy'
        ob.hide_render=not central and (ident in north_tree_ids or n['sportmask'].covers(Point(p.x,p.y)) or not roi.covers(Point(p.x,p.y)))
        if not ob.hide_render and not central:background_trees.append(ob)
    elif any(name.startswith(r['id']+' ') for r in D['buildings'] if r['id'] not in n['ids']):
        ob.hide_render=False

# Lake construction adopts the existing scene, bypassing only the reload and
# central-only display culling. Both original source scripts remain unchanged.
lakepath=ROOT/'scripts/lake_study.py';raw=lakepath.read_text()
stop="exec(compile(camera_marker+render_finish,str(base),'exec'),context)"
assert raw.count(stop)==1;code=raw.split(stop)[0]
replacement="setup=change(setup,'bpy.ops.wm.open_mainfile(filepath=str(source));s=bpy.context.scene','s=bpy.context.scene')\nsetup=change(setup,'if not FULL and corners and not region.intersects','if False and corners and not region.intersects')\nsetup=change(setup,\"oldpng=(CACHE/'campus.png').stat().st_size\",\"oldpng=(CACHE/'campus.png').stat().st_size if (CACHE/'campus.png').exists() else 0\")\nsetup=change(setup,\"oldmeta=(CACHE/'atlas.json').stat().st_size\",\"oldmeta=(CACHE/'atlas.json').stat().st_size if (CACHE/'atlas.json').exists() else 0\")\nexec(compile(setup, str(base), 'exec'), context)"
code=change(code,"exec(compile(setup, str(base), 'exec'), context)",replacement)
l={'__file__':str(lakepath),'__name__':'__joined_lake__','change':change};exec(compile(code,str(lakepath),'exec'),l)
c=l['context'];lake=l['lake'];allroof=unary_union([n['allroof'],c['bodies']])
otherwater=unary_union([nshape(r['outline']) for r in D['surfaces'] if r['kind']=='water' and r.get('source','satellite')=='satellite'])
allwater=lake.union(otherwater)
ground=unary_union([nshape(r['outline']) for r in D['surfaces'] if r['kind']=='ground' and r.get('source','satellite')=='satellite']).intersection(roi)
lawn=n['lawn'];pave=n['pave'];curb=n['curb']
# Use shared material objects: texture coordinates have a single world frame.
for ob in s.objects:
    if ob.type!='MESH' or ob.hide_render:continue
    for slot in ob.material_slots:
        if slot.material and slot.material.name in ['Atlas meadow','Study meadow','Living lawn','Campus grass','Turf light']:slot.material=lawn
        if slot.material and slot.material.name in ['Atlas warm granite','Study pale warm mineral paving','Honed pale granite paving']:slot.material=pave
        if slot.material and slot.material.name in ['Atlas granite edge','Study light stone curb']:slot.material=curb
    if ob.name.startswith(('Atlas meadow surface','Study source woodland ground')):
        for v in ob.data.vertices:v.co.z=.051
ground_display=ground.difference(allwater.buffer(.03))
ground_mesh=n['Mesh']('Joined site ground')
ground_regions=[]
for outer,inner in [(0,3),(3,7),(7,12),(12,18)]:
    band=roi.buffer(-outer).difference(roi.buffer(-inner)).intersection(ground_display)
    ground_mesh.plane(band,.05,lawn);ground_regions.append(band)
interior=roi.buffer(-18).intersection(ground_display)
ground_mesh.plane(interior,.05,lawn);ground_regions.append(interior)
ground_ob=ground_mesh.finish()
edgeweight=ground_ob.data.attributes.new(name='joined_context_blend',type='FLOAT',domain='POINT')
for vertex in ground_ob.data.vertices:
    edgeweight.data[vertex.index].value=min(1,roi.boundary.distance(Point(vertex.co.x,vertex.co.y))/18)
assert unary_union(ground_regions).symmetric_difference(ground_display).area<1e-7
# Consolidate traced road surfaces, clipping sports, roofs, water and site scope.
traced=[LineString([(gp(p).x,gp(p).y) for p in r[1]]).buffer(r[2]/2,join_style='round') for r in D['roads']]
road=unary_union([*traced,n['roads'],c['road']]).intersection(roi).difference(allroof.buffer(.25)).difference(allwater.buffer(4.85)).difference(n['sportmask'].buffer(.4))
roadmat=n['mat']('Joined quiet grey asphalt',(.115,.13,.115));n['texture'](roadmat,(.085,.10,.09),(.15,.165,.145),18,.012)
for ob in s.objects:
    if ob.name.startswith(('Study asphalt','Study road curbs','Atlas road surface','Atlas road edge')):ob.hide_render=True
n['surface']('Joined continuous source roads',road,.35,roadmat)
n['surface']('Joined continuous road curbs',road.buffer(.25).difference(road).difference(allroof).difference(allwater.buffer(4.85)).intersection(roi),.38,curb)
# Ground detail pass. Each new finish is clipped to an observed site area;
# dimensions of paving courses and parking markings remain illustrative.
site_exclusions=allroof.buffer(.30).union(allwater.buffer(4.85)).union(road.buffer(.28)).union(n['sportmask'].buffer(.20))
ground_details=[]
parking_finish=n['mat']('Joined parking mineral concrete',(.40,.395,.36))
n['texture'](parking_finish,(.36,.365,.335),(.46,.45,.405),4,.009)
court_finish=n['mat']('Joined academic courtyard sandstone',(.53,.50,.425))
n['texture'](court_finish,(.48,.465,.405),(.59,.555,.475),5,.01)
walk_finish=n['mat']('Joined pedestrian edge stone',(.57,.565,.515))
n['texture'](walk_finish,(.51,.51,.47),(.63,.615,.55),6,.008)
marking=n['mat']('Joined parking faded markings',(.72,.715,.62))
stone_joint=n['mat']('Joined ground expansion joints',(.34,.345,.305))
def site_finish(name,pixels,material):
    traced=nshape(pixels)
    g=traced.intersection(roi).difference(site_exclusions)
    n['surface'](name,g,.425,material)
    ground_details.append({'name':name,'source_pixels':pixels,'visible_area_m2':g.area,'roof_intersection_m2':g.intersection(allroof).area,'water_intersection_m2':g.intersection(allwater).area})
    return g
parking_row=next(r for r in D['surfaces'] if r['id']=='north-parking')
parking=site_finish('Joined source north parking',parking_row['outline'],parking_finish)
parking_inner=parking.buffer(-.6)
# The fixed image shows repeated parking rows, with access aisles between them.
# Draw only ground markings; no occupancy, vehicle count or real capacity is implied.
u=(gp((813,482))-gp((749,474))).normalized()
v=Vector((u.y,-u.x,0));parking_lines=[]
for px in [757,770,784,799]:
    origin=gp((px,483+(px-749)*.125))
    end=origin+v*(39*2.65)
    parking_lines.append(LineString([(origin.x,origin.y),(end.x,end.y)]).buffer(.045).intersection(parking_inner))
    for j in range(40):
        p=origin+v*(j*2.65);q=p+u*5.1
        line=LineString([(p.x,p.y),(q.x,q.y)]).buffer(.055).intersection(parking_inner)
        if not line.is_empty:parking_lines.append(line)
parking_paint=unary_union(parking_lines)
n['surface']('Joined illustrative parking bay separators',parking_paint,.441,marking)
n['surface']('Joined parking perimeter seam',parking.difference(parking.buffer(-.15)),.438,stone_joint)
# The pale interior in the fixed overhead image is not the uniform lawn used
# by the earlier ground recipe. Keep its traced perimeter and classify finish only.
court_pixels=[(660,483),(707,488),(706,518),(660,513)]
academic_court=site_finish('Joined source academic hard courtyard',court_pixels,court_finish)
hidden_court_hedges=[]
for ob in s.objects:
    if ob.name.startswith('Study courtyard hedge') and academic_court.buffer(.8).covers(Point(ob.location.x,ob.location.y)):
        ob.hide_render=True;hidden_court_hedges.append(ob.name)
new_bed_pixels=[[(636,474),(642,475),(642,523),(636,522)],[(645,533),(720,539),(720,545),(645,539)]]
source_beds=unary_union([nshape(p).buffer(-.7).buffer(.7) for p in new_bed_pixels]).intersection(roi).difference(site_exclusions)
n['surface']('Joined source academic planted strips',source_beds,.437,lawn)
n['surface']('Joined planted strip stone margin',source_beds.buffer(.20).difference(source_beds).difference(site_exclusions),.445,curb)
# A narrow change of stone finish follows the edge of existing paved ground;
# it adds no route or paving footprint and leaves photographed open ground alone.
existing_paved=n['paved'].union(c['paved']).intersection(roi)
edge_walk=road.buffer(1.7).difference(road.buffer(.38)).intersection(existing_paved).difference(source_beds.buffer(.25)).difference(site_exclusions)
n['surface']('Joined paved pedestrian margins',edge_walk,.448,walk_finish)
ground_joints=[]
for g,spacing in [(academic_court,4.0),(parking,7.5)]:
    x0,y0,x1,y1=g.bounds
    for xx in range(math.floor(x0/spacing),math.ceil(x1/spacing)+1):
        ground_joints.append(LineString([(xx*spacing,y0),(xx*spacing,y1)]).buffer(.022).intersection(g))
    for yy in range(math.floor(y0/spacing),math.ceil(y1/spacing)+1):
        ground_joints.append(LineString([(x0,yy*spacing),(x1,yy*spacing)]).buffer(.022).intersection(g))
n['surface']('Joined source hardstanding slab joints',unary_union(ground_joints).difference(parking_paint.buffer(.07)),.435,stone_joint)
ground_revision={'source':'Fixed model/campus/references/satellite.jpg, native pixels = recorded display pixels × 2; compare campus-aerial.jpg for material family.','areas':ground_details,'academic_planted_strips_source_pixels':new_bed_pixels,'planting_area_m2':source_beds.area,'pedestrian_margin_area_m2':edge_walk.area,'parking_marking_area_m2':parking_paint.area,'reclassified_courtyard_hedge_objects_hidden':hidden_court_hedges,'checks':{'new_finishes_roof_intersection_m2':unary_union([parking,academic_court,source_beds,edge_walk]).intersection(allroof).area,'new_finishes_water_intersection_m2':unary_union([parking,academic_court,source_beds,edge_walk]).intersection(allwater).area,'pedestrian_margin_outside_existing_paving_m2':edge_walk.difference(existing_paved).area},'limitations':'Ground classification interpreted from fixed imagery, not surveyed. Bay sizes, marking spacing, joint sizes and planted strip edges are estimated; no parking capacity or pedestrian navigation network is asserted.'}
assert all(value<1e-7 for value in ground_revision['checks'].values())
# Eliminate the old merged trunk batches and additive volume fills. Their
# visibility was independent of the replacement crowns at the regional seam.
hidden_trunks=[];hidden_fills=[]
for ob in s.objects:
    if ob.name.startswith(('Tree trunk','Tree branch','Study trunks and branches')):
        if not ob.hide_render:hidden_trunks.append(ob.name)
        ob.hide_render=True
    if ob.name.startswith('Atlas canopy volume '):
        if not ob.hide_render:hidden_fills.append(ob.name)
        ob.hide_render=True
context_centres=[]
for i,ob in enumerate(background_trees):
    matrix=ob.matrix_world.copy();ob.hide_render=True
    crown=bpy.data.objects.new('Joined source context tree '+str(i),n['protos'][(i*5+1)%12])
    s.collection.objects.link(crown);crown.matrix_world=matrix
    context_centres.append([ob.name,list(matrix.translation)])

# Every displayed tree gets exactly one trunk terminating at its prototype's
# branch root. No sampled centre is moved and no decorative trees are added.
bpy.context.view_layer.update()
trunks=n['Mesh']('Joined paired tree trunks');tree_pairs=[]
for ob in s.objects:
    if ob.hide_render or not ob.name.startswith(('Study source tree ','Lake source branched tree ','Joined source context tree ')):continue
    top=ob.matrix_world@Vector((0,0,-.86));p=ob.matrix_world.translation
    if top.z>.12:
        radius=min(.19,max(.085,min(ob.scale.x,ob.scale.y)*.032))
        n['branch'](trunks,Vector((p.x,p.y,.02)),top,radius,radius*.62)
        tree_pairs.append([ob.name,list(p),float(top.z)])
trunks.finish()
assert tree_pairs and len({t[0] for t in tree_pairs})==len(tree_pairs)
visible_tree_count=sum(1 for ob in s.objects if not ob.hide_render and ob.name.startswith(('Study source tree ','Lake source branched tree ','Joined source context tree ')))
assert len(tree_pairs)==visible_tree_count,'A visible crown has no paired trunk'

# Thin leaves transmit a small amount of light. The same material treatment is
# used across the two original prototype families and the retained context.
leaf_material_count=0
for mat in [*n['leaves'],*l['leaves']]:
    ns=mat.node_tree.nodes;ls=mat.node_tree.links;bs=ns.get('Principled BSDF')
    bs.inputs['Roughness'].default_value=.72
    translucent=ns.new('ShaderNodeBsdfTranslucent');translucent.inputs['Color'].default_value=bs.inputs['Base Color'].default_value
    mixleaf=ns.new('ShaderNodeMixShader');mixleaf.inputs[0].default_value=.16
    ls.new(bs.outputs[0],mixleaf.inputs[1]);ls.new(translucent.outputs[0],mixleaf.inputs[2])
    ls.new(mixleaf.outputs[0],ns.get('Material Output').inputs['Surface']);leaf_material_count+=1

# Fixed satellite RGB distinguishes dry ground from green cover. Only this
# subdued colour field is used on modelled grass: buildings and road surfaces
# remain geometry. A shared world-coordinate frame prevents material seams.
source_image=bpy.data.images.load(str(ROOT/'model/campus/references/satellite.jpg'),check_existing=True)
lo=gp((0,1920));hi=gp((1152,0));world_width=hi.x-lo.x;world_height=hi.y-lo.y
ns=lawn.node_tree.nodes;ls=lawn.node_tree.links;bs=ns.get('Principled BSDF')
oldcolor=bs.inputs['Base Color'].links[0].from_socket
coord=ns.new('ShaderNodeTexCoord');coord.object=n['anchor']
uv=ns.new('ShaderNodeVectorMath');uv.operation='MULTIPLY_ADD'
uv.inputs[1].default_value=(1/world_width,1/world_height,1)
uv.inputs[2].default_value=(-lo.x/world_width,-lo.y/world_height,0)
ls.new(coord.outputs['Object'],uv.inputs[0])
photo=ns.new('ShaderNodeTexImage');photo.image=source_image;photo.interpolation='Cubic';photo.extension='EXTEND';ls.new(uv.outputs[0],photo.inputs['Vector'])
rgb=ns.new('ShaderNodeSeparateColor');ls.new(photo.outputs['Color'],rgb.inputs['Color'])
dryness=ns.new('ShaderNodeMath');dryness.operation='SUBTRACT';ls.new(rgb.outputs['Red'],dryness.inputs[0]);ls.new(rgb.outputs['Green'],dryness.inputs[1])
strength=ns.new('ShaderNodeMath');strength.operation='MULTIPLY_ADD';strength.inputs[1].default_value=8;strength.inputs[2].default_value=.05;strength.use_clamp=True;ls.new(dryness.outputs[0],strength.inputs[0])
subtle=ns.new('ShaderNodeMath');subtle.operation='MULTIPLY';subtle.inputs[1].default_value=.55;ls.new(strength.outputs[0],subtle.inputs[0])
drymix=ns.new('ShaderNodeMixRGB');drymix.inputs[2].default_value=(.31,.275,.16,1);ls.new(subtle.outputs[0],drymix.inputs[0]);ls.new(oldcolor,drymix.inputs[1]);ls.new(drymix.outputs[0],bs.inputs['Base Color'])

# Restrained contact shading improves the wall-to-ground relationship without
# adding guessed entrances, planting beds or objects to the source layout.
for mat,distance,minimum in [(pave,2.4,.70),(lawn,1.7,.78)]:
    ns=mat.node_tree.nodes;ls=mat.node_tree.links;bs=ns.get('Principled BSDF')
    color=bs.inputs['Base Color'].links[0].from_socket
    ao=ns.new('ShaderNodeAmbientOcclusion');ao.inputs['Distance'].default_value=distance
    tone=ns.new('ShaderNodeMixRGB');tone.inputs[1].default_value=(minimum,minimum,minimum,1);tone.inputs[2].default_value=(1,1,1,1);ls.new(ao.outputs['AO'],tone.inputs[0])
    multiply=ns.new('ShaderNodeMixRGB');multiply.blend_type='MULTIPLY';multiply.inputs[0].default_value=1;ls.new(color,multiply.inputs[1]);ls.new(tone.outputs[0],multiply.inputs[2]);ls.new(multiply.outputs[0],bs.inputs['Base Color'])
curb.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value=(.60,.60,.53,1)

# Surrounding source imagery fills only the exterior of the traced model ground.
# It provides geographic context in the former blank corners, not a replacement
# for modelled campus surfaces or an invented extension of the campus.
source_coverage=box(lo.x,lo.y,hi.x,hi.y)
context_mask=roi.buffer(220).intersection(source_coverage).difference(ground.buffer(.05)).difference(allwater).difference(allroof)
contextmat=n['mat']('Joined exterior source imagery',(.2,.25,.15))
ns=contextmat.node_tree.nodes;ls=contextmat.node_tree.links;bs=ns.get('Principled BSDF')
tex=ns.new('ShaderNodeTexImage');tex.image=source_image;tex.interpolation='Cubic'
tc=ns.new('ShaderNodeTexCoord');tc.object=n['anchor'];mapping=ns.new('ShaderNodeVectorMath');mapping.operation='MULTIPLY_ADD'
mapping.inputs[1].default_value=(1/world_width,1/world_height,1);mapping.inputs[2].default_value=(-lo.x/world_width,-lo.y/world_height,0)
ls.new(tc.outputs['Object'],mapping.inputs[0]);ls.new(mapping.outputs[0],tex.inputs['Vector']);ls.new(tex.outputs['Color'],bs.inputs['Base Color'])
n['surface']('Joined exterior context',context_mask,-.10,contextmat)
# At an arbitrary sample crop only, blend the modelled ground into its exact
# image context. Actual lake, road, courtyard and building boundaries stay sharp.
groundmaterial=lawn.copy();groundmaterial.name='Joined ground context transition'
ns=groundmaterial.node_tree.nodes;ls=groundmaterial.node_tree.links;bs=ns.get('Principled BSDF')
modelcolor=bs.inputs['Base Color'].links[0].from_socket
contextcolor=next(node for node in ns if node.bl_idname=='ShaderNodeTexImage').outputs['Color']
attr=ns.new('ShaderNodeAttribute');attr.attribute_name='joined_context_blend'
blend=ns.new('ShaderNodeMixRGB');ls.new(attr.outputs['Fac'],blend.inputs[0]);ls.new(contextcolor,blend.inputs[1]);ls.new(modelcolor,blend.inputs[2]);ls.new(blend.outputs[0],bs.inputs['Base Color'])
ground_ob.data.materials[0]=groundmaterial
landscape_revision={'paired_tree_count':len(tree_pairs),'tree_pairs':tree_pairs,'hidden_legacy_trunk_objects':hidden_trunks,'hidden_additive_fill_count':len(hidden_fills),'context_tree_source_centres':context_centres,'shared_leaf_material_count':leaf_material_count,'source_ground_color_method':'bounded red-minus-green dryness field from fixed satellite RGB, maximum mix 0.55; illustrative pigment colours','outside_context_area_m2':context_mask.area,'outside_context_ground_intersection_m2':context_mask.intersection(ground).area,'sample_crop_blend_width_estimate_m':18,'ground_footprint_area_difference_m2':unary_union(ground_regions).symmetric_difference(ground_display).area,'tree_shape_note':'All crown centres inherited; heights, leaf transmission and crown species appearance remain estimated'}
# Satellite traces in the shared seam should connect rather than be bridged by
# invented roads. Measure their actual overlap and the road exclusion masks.
overlap=n['roads'].intersection(c['road']).area
assert overlap>0,'Source road sets do not connect; review source alignment'
assert road.intersection(allroof).area<1e-7 and road.intersection(allwater).area<1e-7

# One shared sun and the north camera direction cover all nineteen parts.
sun=s.objects['Atlas daylight'];sun.data.energy=2.5;sun.data.angle=.10
sun.rotation_euler=(math.radians(27),math.radians(-22),math.radians(-30))
flat=next(node for node in s.world.node_tree.nodes if node.bl_idname=='ShaderNodeBackground' and node.name=='Background')
flat.inputs['Color'].default_value=(.78,.83,.90,1);flat.inputs['Strength'].default_value=.52
faces=dict(n['faces'])
for ident in ['B06','B07','B08']:
    faces[ident]=[[list(c['pt'](q,f.get('base_z',0)+f.get('height_m_estimate',0))) for q in f['pixel_outline']] for f in c['F'] if f['id'].startswith(ident)]
final='--final' in sys.argv;W,H=(3200,2200) if final else (1600,1100)
cam=s.camera;cam.rotation_euler=json.loads((OUT/'campus-north.json').read_text())['camera']['rotation_euler']
points=[Vector(p) for fs in faces.values() for f in fs for p in f];points += [Vector((p.x,p.y,0)) for p in points]
target=sum(points,Vector())/len(points);cam.location=target+cam.rotation_euler.to_matrix()@Vector((0,0,1000));cam.data.type='ORTHO'
bpy.context.view_layer.update();inv=cam.matrix_world.inverted();pp=[inv@p for p in points];xs=[p.x for p in pp];ys=[p.y for p in pp]
cam.location+=cam.matrix_world.to_3x3()@Vector(((min(xs)+max(xs))/2,(min(ys)+max(ys))/2,0));cam.data.ortho_scale=max(max(xs)-min(xs),(max(ys)-min(ys))*W/H)*1.14
s.render.resolution_x=W;s.render.resolution_y=H;s.render.resolution_percentage=100;s.cycles.samples=32 if final else 12
s.render.use_border=False;s.render.use_crop_to_border=False;s.render.filepath=str(CACHE/'campus.png');s.render.image_settings.color_mode='RGB';s.render.image_settings.compression=100
bpy.context.view_layer.update();records=[]
metadata_inputs={path:sha(OUT/path) for path in ['campus-north.json','campus-lake.json']}
old={r['id']:r for path in ['campus-north.json','campus-lake.json'] for r in json.loads((OUT/path).read_text())['records']}
for ident,fs in faces.items():
    polys=[]
    for face in fs:
        projected=[world_to_camera_view(s,cam,Vector(p)) for p in face]
        poly=Polygon([(p.x*W,(1-p.y)*H) for p in projected])
        if poly.is_valid and poly.area>1e-6:polys.append(poly)
    union=unary_union(polys).buffer(.003,join_style=2).buffer(-.003,join_style=2);parts=list(union.geoms) if hasattr(union,'geoms') else [union];p=union.representative_point()
    records.append({**old[ident],'polygons':[[list(g.exterior.coords),*[list(r.coords) for r in g.interiors]] for g in parts],'anchor':[p.x,p.y]})
regions=[]
for ident,name in [('north','北区街区'),('lake','中央湖区')]:
    rows=[r for r in records if r['region']==ident];ps=[p for r in rows for poly in r['polygons'] for ring in poly for p in ring]
    regions.append({'id':ident,'name':name,'count':len(rows),'bounds':[min(p[0] for p in ps),min(p[1] for p in ps),max(p[0] for p in ps),max(p[1] for p in ps)]})
meta={'title':'北区与湖区','coverage':'joined-study','scope':'N07 N21-N35 and B06-B08 in one continuous scene; surrounding buildings are context','width':W,'height':H,'records':records,'regions':regions,'camera':{'position':list(cam.location),'rotation_euler':list(cam.rotation_euler),'ortho_scale':cam.data.ortho_scale},'roof_faces_world':faces,'samples':s.cycles.samples,'sources':sources,'generator_sha256':sha(Path(__file__)),'checks':{'source_road_overlap_m2':overlap,'road_roof_intersection_m2':road.intersection(allroof).area,'road_water_intersection_m2':road.intersection(allwater).area,'shared_ground_water_intersection_m2':ground.difference(allwater.buffer(.03)).intersection(allwater).area,'record_count':len(records)},'metadata_inputs_at_generation':metadata_inputs,'metadata_input_policy':'Historical fingerprints; only record descriptions and north camera direction are consumed and embedded here. Frontend QA resealing does not alter those fields.','generation_commands':['Blender --background -t 4 --python scripts/campus_study.py -- --final','python scripts/campus_study.py --export'],'method':'One native render of both detailed construction layers, shared world-coordinate materials, source-road union and one camera; never a montage of the independent images','limitations':'Dimensions and unseen details are estimated. Background buildings are not part of the 19 selectable parts. User visual acceptance remains pending.'}
assert len(records)==19
meta['landscape_revision']=landscape_revision
meta['ground_revision']=ground_revision
meta['architecture_revision']={'scope':['N31','N34','N35'],'basis':'Fixed campus-aerial.jpg: pale dining block with wide central window bands and grouped narrow end lights; red academic block with continuous masonry piers and glazed east entrance. Existing N32/N33 source-aligned roof bands retained.','method':'In-memory facade replacement before shared scene construction; all roof faces, heights, camera and source footprints retained.','estimated':['window counts and dimensions','hidden elevations','entrance canopy dimensions','pier depth'],'user_acceptance':'pending'}
print('JOINED RENDER',W,H,meta['checks'],flush=True);bpy.ops.render.render(write_still=True)
meta['png_sha256']=sha(CACHE/'campus.png');meta['render_status']='generated_needs_visual_review'
for p,h in sources.items():assert sha(ROOT/p)==h,p
assert capacity()<192*1024**2
(CACHE/'atlas.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')
print('JOINED DONE',flush=True)
