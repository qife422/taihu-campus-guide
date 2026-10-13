"""Photo-led lake study; retain the full atlas and north study unchanged.

Blender --background -t 4 --python scripts/lake_study.py [-- --final]
/opt/anaconda3/bin/python scripts/lake_study.py --export
The existing scene builder is evaluated in two explicitly bounded sections.
No source replacement, scene save, full-campus export, or image resizing occurs.
"""
from pathlib import Path
import sys, json, hashlib, io, datetime, runpy

ROOT = Path(__file__).resolve().parents[1]
CACHE = Path('/tmp/taihu-full')
OUT = ROOT / 'public/assets'
ASSETS = ['campus-atlas.webp', 'campus-atlas.json', 'campus-north.webp',
          'campus-north.json', 'campus-north-before.webp', 'campus-reference.webp',
          'campus-lake.webp', 'campus-lake.json']

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def capacity():
    return sum(p.stat().st_size for p in CACHE.rglob('*') if p.is_file())

if '--export' in sys.argv:
    from PIL import Image
    # The existing independent NumPy/source-footprint check also preserves holes.
    sys.dont_write_bytecode = True
    sys.argv = [str(ROOT/'scripts/export_atlas.py'), '--check']
    result = runpy.run_path(str(ROOT/'scripts/export_atlas.py'))
    meta = result['meta']
    assert meta['lake_study']['generator_sha256'] == sha(Path(__file__))
    assert (meta['width'], meta['height']) == (2800, 2400)
    for p, fingerprint in meta['lake_study']['sources'].items():
        assert sha(ROOT/p) == fingerprint, p
    image = Image.open(CACHE/'campus.png').convert('RGB')
    encoded = io.BytesIO()
    image.save(encoded, format='WEBP', quality=92, method=6)
    payload = encoded.getvalue()
    meta['image_sha256'] = hashlib.sha256(payload).hexdigest()
    meta['image_bytes'] = len(payload)
    meta['updated'] = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()
    meta['generation_commands'] = [
        'Blender --background -t 4 --python scripts/lake_study.py -- --final',
        '/opt/anaconda3/bin/python scripts/lake_study.py --export']
    meta['visual_review'] = {'status': 'pending'}
    meta['frontend_validation'] = {'status': 'pending'}
    meta['candidate_path_status'] = 'temporary diagnostic; sealed deliverable is campus-lake.webp'
    meta['budget'] = {'asset_count_limit': 8, 'asset_bytes_limit': 8*1024**2,
                      'cache_bytes_limit': 192*1024**2, 'source_amplification_limit': 256}
    data = (json.dumps(meta, ensure_ascii=False, indent=2)+'\n').encode()
    total = sum((OUT/p).stat().st_size for p in ASSETS[:6]) + len(payload) + len(data)
    assert total < 8*1024**2
    sources = list((ROOT/'scripts').glob('*.py')) + [ROOT/'src/CampusAtlas.jsx', ROOT/'src/campusAtlas.css']
    assert total / sum(p.stat().st_size for p in sources) < 256
    assert capacity() < 192*1024**2
    (OUT/'campus-lake.webp').write_bytes(payload)
    (OUT/'campus-lake.json').write_bytes(data)
    print(json.dumps({'image_bytes': len(payload), 'eight_asset_bytes': total,
                      'projection_max_px': meta['checks']['independent_projection_max_difference_px']}))
    sys.exit(0)

import bpy, math, random
from mathutils import Vector
sys.dont_write_bytecode = True
sys.path.insert(0, '/tmp/taihu-gis-deps')
from shapely.geometry import Polygon, Point, LineString
from shapely.geometry.polygon import orient
from shapely.ops import unary_union
from shapely import constrained_delaunay_triangles

assert not any(arg in sys.argv for arg in ['--campus', '--north', '--region']), 'Lake-only study'
sources = ['scripts/campus_atlas.py', 'scripts/export_atlas.py', 'scripts/lake_study.py',
           'model/campus/campus.blend', 'model/campus/layout.json',
           'model/central-campus/footprints.json',
           'model/central-campus/references/satellite.jpg',
           'model/central-campus/references/satellite-export.json',
           'model/central-campus/references/lake-photo.jpg',
           'model/central-campus/references/campus-aerial.jpg']
fingerprints = {p: sha(ROOT/p) for p in sources}
base = ROOT/'scripts/campus_atlas.py'
marker = '# Simplify lighting into a coherent map-like daylight setup.'
code = base.read_text()
assert code.count(marker) == 1
setup, finish = code.split(marker)
assert 'bpy.ops.render.render' not in setup
context = {'__file__': str(base), '__name__': '__lake_scene__'}
exec(compile(setup, str(base), 'exec'), context)
s = context['s']; lake = context['lake']; pt = context['pt']
material = context['material']; grain = context['grain']; mask = context['mask']
road = context['road']; meadow = context['meadow']

def surface(name, geom, z, mat):
    vertices, faces = [], []
    for triangle in constrained_delaunay_triangles(geom).geoms:
        first = len(vertices)
        vertices.extend((x, y, z) for x, y in list(orient(triangle, 1).exterior.coords)[:-1])
        faces.append((first, first+1, first+2))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces); mesh.materials.append(mat); mesh.update()
    ob = bpy.data.objects.new(name, mesh); s.collection.objects.link(ob)
    return ob

def ribbon(name, inner, outer, z0, z1, mat):
    # Match offset rings by source-normalised arc length for a continuous slope.
    count = max(128, int(outer.length/.35))
    vertices, faces = [], []
    for i in range(count):
        a = inner.interpolate(i/count, normalized=True)
        b = outer.interpolate(i/count, normalized=True)
        vertices.extend([(a.x,a.y,z0), (b.x,b.y,z1)])
    for i in range(count):
        j=(i+1)%count; faces.append((2*i,2*j,2*j+1,2*i+1))
    mesh=bpy.data.meshes.new(name);mesh.from_pydata(vertices,[],faces);mesh.materials.append(mat);mesh.update()
    uv=mesh.uv_layers.new(name='Shore masonry metres')
    for i,poly in enumerate(mesh.polygons):
        width=Vector(vertices[2*i+1])-Vector(vertices[2*i])
        coords=[(i/count*inner.length,0),((i+1)/count*inner.length,0),
                ((i+1)/count*inner.length,width.length),(i/count*inner.length,width.length)]
        for loop,point in zip(poly.loop_indices,coords):uv.data[loop].uv=point
    ob=bpy.data.objects.new(name,mesh);s.collection.objects.link(ob)
    return ob

def line(name, points, radius, mat):
    curve=bpy.data.curves.new(name,'CURVE');curve.dimensions='3D';curve.resolution_u=1
    curve.bevel_depth=radius;curve.bevel_resolution=0
    spline=curve.splines.new('POLY');spline.points.add(len(points)-1)
    for p,q in zip(spline.points,points):p.co=(*q,1)
    ob=bpy.data.objects.new(name,curve);s.collection.objects.link(ob);curve.materials.append(mat)

for ob in s.objects:
    if ob.name.startswith(('Atlas bank tread','Atlas promenade','Atlas shallow water margin',
                           'Atlas shore planting edge','Atlas lake water')):
        ob.hide_render=True

# Fixed lake XY remains untouched. Submerged retaining masonry replaces the
# equal-width concentric treads. Height/width are interpretations of lake-photo.
stone=material('Lake rough pale masonry',(.45,.44,.35))
grain(stone,[(.30,.31,.255),(.63,.61,.50)],4.5,3,.045)
ns=stone.node_tree.nodes;ls=stone.node_tree.links;uv=ns.new('ShaderNodeTexCoord')
courses=ns.new('ShaderNodeTexBrick');courses.inputs['Scale'].default_value=1
courses.inputs['Brick Width'].default_value=.75;courses.inputs['Row Height'].default_value=.33
courses.inputs['Mortar Size'].default_value=.012
courses.inputs['Color1'].default_value=(.39,.40,.33,1);courses.inputs['Color2'].default_value=(.59,.57,.46,1)
courses.inputs['Mortar'].default_value=(.24,.27,.22,1)
ls.new(uv.outputs['UV'],courses.inputs['Vector'])
graincolor=next(n for n in ns if n.bl_idname=='ShaderNodeValToRGB')
finishcolor=ns.new('ShaderNodeMixRGB');finishcolor.inputs[0].default_value=.18
ls.new(courses.outputs['Color'],finishcolor.inputs[1]);ls.new(graincolor.outputs[0],finishcolor.inputs[2])
stonebs=ns.get('Principled BSDF');ls.new(finishcolor.outputs[0],stonebs.inputs['Base Color'])
coursebump=ns.new('ShaderNodeBump');coursebump.inputs['Strength'].default_value=.24;coursebump.inputs['Distance'].default_value=.024
ls.new(courses.outputs['Fac'],coursebump.inputs['Height']);ls.new(coursebump.outputs[0],stonebs.inputs['Normal'])
cap=material('Lake coping sandstone',(.65,.61,.49));grain(cap,[(.52,.50,.40),(.70,.66,.54)],7,2,.018)
pathmat=material('Lake weathered mineral path',(.53,.51,.44));grain(pathmat,[(.44,.45,.39),(.61,.59,.50)],5,2,.012)
railmat=material('Lake muted red railing',(.26,.055,.028),.52)
water=context['water'];bs=water.node_tree.nodes.get('Principled BSDF')
bs.inputs['Metallic'].default_value=0;bs.inputs['Roughness'].default_value=.045
bs.inputs['Specular IOR Level'].default_value=.72
bs.inputs['Transmission Weight'].default_value=.82
ns=water.node_tree.nodes;ls=water.node_tree.links
color=next(n for n in ns if n.bl_idname=='ShaderNodeValToRGB')
color.color_ramp.elements[0].color=(.065,.17,.10,1)
color.color_ramp.elements[1].color=(.08,.19,.12,1)
for n in ns:
    if n.bl_idname=='ShaderNodeBump':n.inputs['Strength'].default_value=.22;n.inputs['Distance'].default_value=.032
waterob=surface('Lake continuous water',lake,-1.1,water)
# Interpolated shore-distance colour avoids a flat, solid-colour water ring.
attrib=waterob.data.attributes.new('shore_tint','FLOAT','POINT')
for v in waterob.data.vertices:attrib.data[v.index].value=max(0,1-Point(v.co.x,v.co.y).distance(lake.boundary)/1.5)
# Add actual narrow bands with shared shader and matching per-vertex field.
waterob.hide_render=True
parts=[lake.buffer(-1.5)]
for a,b in zip([0,.25,.5,.8,1.1],[.25,.5,.8,1.1,1.5]):parts.append(lake.buffer(-a).difference(lake.buffer(-b)))
for i,g in enumerate(parts):
    ob=surface('Lake water gradient '+str(i),g,-1.1,water)
    field=ob.data.attributes.new('shore_tint','FLOAT','POINT')
    for v in ob.data.vertices:field.data[v.index].value=max(0,1-Point(v.co.x,v.co.y).distance(lake.boundary)/1.5)
att=ns.new('ShaderNodeAttribute');att.attribute_name='shore_tint'
mix=ns.new('ShaderNodeMixRGB');mix.blend_type='MIX';mix.inputs[2].default_value=(.12,.23,.13,1)
ls.new(att.outputs['Fac'],mix.inputs[0]);ls.new(color.outputs['Color'],mix.inputs[1]);ls.new(mix.outputs[0],bs.inputs['Base Color'])
# An opaque interpreted bed bounds transmitted rays; no real depth is claimed.
bed=material('Lake interpreted submerged bed',(.09,.12,.06))
grain(bed,[(.065,.085,.045),(.12,.145,.08)],.3,2,.015)
surface('Lake bounded submerged bed',lake,-3.6,bed)
inner=lake.buffer(.10).exterior; outer=lake.buffer(2.8).exterior
ribbon('Lake sloped stone revetment',inner,outer,-1.065,.31,stone)
promenade=lake.buffer(4.6).difference(lake.buffer(2.8)).difference(mask).difference(road)
surface('Lake upper coping',lake.buffer(3.02).difference(lake.buffer(2.76)),.335,cap)
surface('Lake upper promenade',promenade,.32,pathmat)
surface('Lake outer coping',lake.buffer(4.6).difference(lake.buffer(4.40)).difference(mask).difference(road),.335,cap)

# The photo documents the west/north railing. Keep the eastern/southern banks
# unasserted rather than inventing continuous railing around all four sides.
shore=lake.buffer(3.06).exterior; count=max(1,int(shore.length/2.0));posts=0
for i in range(count):
    p=shore.interpolate(i/count,normalized=True)
    source_x=(p.x-context['shift'].x)/context['unit']+780
    source_y=680-(p.y-context['shift'].y)/context['unit']
    if not (source_x<685 or source_y<520):continue
    q=shore.interpolate((i+1)/count,normalized=True)
    line('Lake photo railing post',[(p.x,p.y,.34),(p.x,p.y,1.12)],.055,railmat)
    for z in [.66,1.08]:line('Lake photo railing rail',[(p.x,p.y,z),(q.x,q.y,z)],.036,railmat)
    posts+=1
    # Paving joints are clipped to the existing promenade, not new paths.
    a=Vector((p.x,p.y));b=Vector((q.x,q.y));d=(b-a).normalized();n=Vector((-d.y,d.x))
    joint=LineString([tuple(a-n*5),tuple(a+n*5)]).buffer(.016).intersection(promenade)
    surface('Lake promenade joint',joint,.325,context['joint'])

# Subtler continuous grass colour and irregular tiny foliage volumes retain
# every existing tree centre and all original fine leaves from the source scene.
lawn=context['lawn']
for n in lawn.node_tree.nodes:
    if n.bl_idname=='ShaderNodeValToRGB':
        n.color_ramp.elements[0].color=(.135,.235,.06,1)
        n.color_ramp.elements[1].color=(.275,.355,.115,1)
# Branch/leaf prototypes replace the coarse fill only on the source-positioned
# central trees. Their original world matrices, trunks and planting centres stay.
leafcolors=[(.045,.135,.023),(.075,.20,.035),(.12,.25,.057),
            (.065,.17,.037),(.105,.24,.067),(.165,.31,.092),
            (.09,.20,.045),(.15,.27,.076),(.21,.335,.12)]
leaves=[material('Lake folded foliage '+str(i),c,.72) for i,c in enumerate(leafcolors)]
bark=material('Lake branch bark',(.15,.10,.052))
prototypes=[]
for seed in range(12):
    rng=random.Random(1180+seed);vertices=[];faces=[];indices=[];family=seed%3
    def face(points,index):
        first=len(vertices);vertices.extend(tuple(p) for p in points)
        faces.append(tuple(range(first,len(vertices))));indices.append(index)
    def branch(a,b,ra,rb):
        a,b=Vector(a),Vector(b);d=(b-a).normalized();u=d.cross(Vector((0,0,1)))
        if u.length<.001:u=Vector((1,0,0))
        u.normalize();v=d.cross(u).normalized();rings=[]
        for origin,radius in [(a,ra),(b,rb)]:
            rings.append([origin+(u*math.cos(k*math.tau/6)+v*math.sin(k*math.tau/6))*radius for k in range(6)])
        for k in range(6):face([rings[0][k],rings[0][(k+1)%6],rings[1][(k+1)%6],rings[1][k]],9)
    centres=[];count=8+seed%4
    for j in range(count):
        angle=j*math.tau/count+rng.uniform(-.30,.30)
        radius=rng.uniform(.32,.77)*(1 if family!=1 else .81)
        c=Vector((math.cos(angle)*radius,math.sin(angle)*radius,rng.uniform(-.25,.32)))
        centres.append(c);fork=Vector((c.x*.33,c.y*.33,-.34))
        branch((0,0,-.86),fork,.030,.017);branch(fork,c,.017,.004)
    centres.append(Vector((-.07,.11,.43)))
    for j in range(4200):
        c=centres[j%len(centres)];angle=rng.random()*math.tau
        radius=math.sqrt(rng.random())*rng.uniform(.20,.37)
        p=c+Vector((math.cos(angle)*radius,math.sin(angle)*radius,rng.uniform(-.25,.25)))
        yaw=rng.random()*math.tau;length=rng.uniform(.035,.067)
        u=Vector((math.cos(yaw),math.sin(yaw),rng.uniform(-.7,.7))).normalized()*length
        v=Vector((-math.sin(yaw),math.cos(yaw),rng.uniform(-.2,.2))).normalized()*length*rng.uniform(.60,.88)
        fold=Vector((0,0,length*.2))
        face([p-u,p-v+fold,p+u,p+v+fold],family*3+rng.choices([0,1,2],[.25,.55,.20])[0])
    mesh=bpy.data.meshes.new('Lake branched crown '+str(seed));mesh.from_pydata(vertices,[],faces);mesh.update()
    for mat in [*leaves,bark]:mesh.materials.append(mat)
    for poly,index in zip(mesh.polygons,indices):poly.material_index=index
    prototypes.append(mesh)

tree_matrices=[];understory_count=0
for i,ob in enumerate(context['originaltrees']):
    if ob.get('origin')!='central-study source-positioned canopy':continue
    matrix=ob.matrix_world.copy();tree_matrices.append((ob.name,list(matrix.translation)))
    ob.hide_render=True
    volume=s.objects.get('Atlas canopy volume '+str(i))
    if volume:volume.hide_render=True
    crown=bpy.data.objects.new('Lake source branched tree '+str(i),prototypes[i%12])
    s.collection.objects.link(crown);crown.matrix_world=matrix;crown.scale*=1.18
    assert (crown.matrix_world.translation-matrix.translation).length<1e-8
for ob in s.objects:
    if ob.name.startswith(('B08 island understory','Atlas source planting clump')):
        ob.data=prototypes[(understory_count*5+2)%12];understory_count+=1

checks={'shore_water_intersection_m2':promenade.intersection(lake).area,
        'shore_roof_intersection_m2':promenade.intersection(mask).area,
        'water_outline_area_difference_m2':lake.symmetric_difference(unary_union(parts)).area,
        'photo_led_railing_posts':posts, 'water_level_estimate_m':-1.1, 'bank_offset_estimate_m':2.8,
        'central_tree_centres_preserved':len(tree_matrices), 'central_tree_world_centres':tree_matrices,
        'shared_branch_leaf_prototypes':len(prototypes),'leaf_faces_per_prototype':4200,
        'existing_understory_centres_preserved':understory_count,
        'underwater_bed_level_estimate_m':-3.6, 'crown_size_multiplier_estimate':1.18}
assert checks['shore_water_intersection_m2']<1e-8 and checks['shore_roof_intersection_m2']<1e-8
assert capacity()<192*1024**2
# Apply a directional sky only to glossy rays after the baseline lighting setup.
# Diffuse daylight stays coherent; reflected sky/soft clouds are procedural
# appearance, not a claim about weather or an HDR panorama of this campus.
camera_marker='bpy.context.view_layer.update()\n# Project roof polygons'
assert finish.count(camera_marker)==1
camera_setup,render_finish=finish.split(camera_marker)
exec(compile(marker+camera_setup,str(base),'exec'),context)
ns=s.world.node_tree.nodes;ls=s.world.node_tree.links
flat=next(n for n in ns if n.bl_idname=='ShaderNodeBackground')
output=next(n for n in ns if n.bl_idname=='ShaderNodeOutputWorld')
coord=ns.new('ShaderNodeTexCoord');sep=ns.new('ShaderNodeSeparateXYZ')
ls.new(coord.outputs['Normal'],sep.inputs[0])
elevation=ns.new('ShaderNodeMath');elevation.operation='ABSOLUTE';ls.new(sep.outputs['Z'],elevation.inputs[0])
ramp=ns.new('ShaderNodeValToRGB')
ramp.color_ramp.elements[0].position=0;ramp.color_ramp.elements[0].color=(.64,.72,.77,1)
ramp.color_ramp.elements[1].position=1;ramp.color_ramp.elements[1].color=(.12,.30,.55,1)
ls.new(elevation.outputs[0],ramp.inputs[0])
cloud=ns.new('ShaderNodeTexNoise');cloud.inputs['Scale'].default_value=3.6;cloud.inputs['Detail'].default_value=2.4
ls.new(coord.outputs['Normal'],cloud.inputs['Vector'])
cloudmask=ns.new('ShaderNodeValToRGB')
cloudmask.color_ramp.elements[0].position=.50;cloudmask.color_ramp.elements[0].color=(0,0,0,1)
cloudmask.color_ramp.elements[1].position=.72;cloudmask.color_ramp.elements[1].color=(.42,.42,.42,1)
ls.new(cloud.outputs['Fac'],cloudmask.inputs[0])
skycolor=ns.new('ShaderNodeMixRGB');skycolor.inputs[2].default_value=(.82,.83,.80,1)
ls.new(cloudmask.outputs[0],skycolor.inputs[0]);ls.new(ramp.outputs[0],skycolor.inputs[1])
sky=ns.new('ShaderNodeBackground');sky.inputs['Strength'].default_value=.8
ls.new(skycolor.outputs[0],sky.inputs['Color'])
path=ns.new('ShaderNodeLightPath');mixsky=ns.new('ShaderNodeMixShader')
ls.new(path.outputs['Is Glossy Ray'],mixsky.inputs[0]);ls.new(flat.outputs[0],mixsky.inputs[1]);ls.new(sky.outputs[0],mixsky.inputs[2]);ls.new(mixsky.outputs[0],output.inputs['Surface'])
sun=s.objects.get('Atlas daylight');sun.data.angle=.07
exec(compile(camera_marker+render_finish,str(base),'exec'),context)
meta=context['meta']
meta['title']='中央湖区样板'
meta['lake_study']={'generator_sha256':sha(Path(__file__)), 'sources':fingerprints,
                   'reference_interpretation':'fixed lake-photo: pale revetment and upper red railing; satellite: shoreline and promenade. Dimensions and water level estimated.',
                   'changes':['continuous shore-distance water tint and directional glossy sky','sloped pale stone revetment','photo-led west/north railing','clipped upper promenade and joints','source-positioned branched trees and folded-leaf understory'],
                   'checks':checks}
meta['roof_faces_world']={}
for ident in ['B06','B07','B08']:
    faces=[]
    for f in context['F']:
        if f['id'].startswith(ident):faces.append([list(pt(q,f.get('base_z',0)+f.get('height_m_estimate',0))) for q in f['pixel_outline']])
    meta['roof_faces_world'][ident]=faces
for p,fingerprint in fingerprints.items():assert sha(ROOT/p)==fingerprint,p
(CACHE/'atlas.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')
print('LAKE STUDY DONE',{k:v for k,v in checks.items() if k!='central_tree_world_centres'},flush=True)
