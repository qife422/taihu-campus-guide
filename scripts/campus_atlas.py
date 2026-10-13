"""Render the central atlas from the retained full-campus scene, without modifying it.
Blender --background -t 4 --python scripts/campus_atlas.py [-- --final]
Candidates reuse /tmp/taihu-full/campus.png. No saved scene or accumulated tiles.
"""
import bpy,bmesh,json,math,random,sys,hashlib,subprocess
from pathlib import Path
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view
sys.path.insert(0,'/tmp/taihu-gis-deps')
from shapely.geometry import Polygon,LineString,Point
from shapely.ops import unary_union
from shapely import constrained_delaunay_triangles
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'model/campus';OLD=ROOT/'model/central-campus';CACHE=Path('/tmp/taihu-full');FINAL='--final' in sys.argv;NORTH_PREVIEW='--north' in sys.argv;FULL='--campus' in sys.argv or NORTH_PREVIEW
PREVIEW_REGION=sys.argv[sys.argv.index('--region')+1] if '--region' in sys.argv else None
if PREVIEW_REGION:
 assert PREVIEW_REGION in ('north','extension','middle','south')
 assert not FINAL,'Regional cameras are preview-only'
 FULL=True
source=BASE/'campus.blend';sourcehash=hashlib.sha256(source.read_bytes()).hexdigest()
# Preflight the existing shared cache; replace one candidate PNG instead of accumulating images.
cachebytes=sum(p.stat().st_size for p in CACHE.rglob('*') if p.is_file())
oldpng=(CACHE/'campus.png').stat().st_size
oldmeta=(CACHE/'atlas.json').stat().st_size
assert cachebytes-oldpng-oldmeta+8*1024**2 < 192*1024**2,'Shared candidate cache capacity reached'
if FINAL and FULL:
 assert cachebytes-oldmeta-(CACHE/'render-tile.png').stat().st_size+6*1024**2 < 192*1024**2,'Tile and metadata capacity reached'
bpy.ops.wm.open_mainfile(filepath=str(source));s=bpy.context.scene
ox,oy=map(float,s['origin_epsg3857'].split(','));cos=float(s['metric_scale']);ext=json.loads((OLD/'references/satellite-export.json').read_text())['extent'];unit=(ext['xmax']-ext['xmin'])/1800*cos
shift=Vector(((ext['xmin']+780/1800*(ext['xmax']-ext['xmin'])-ox)*cos,(ext['ymax']-680/1400*(ext['ymax']-ext['ymin'])-oy)*cos,0))
def pt(p,z=0):return Vector(((p[0]-780)*unit+shift.x,(680-p[1])*unit+shift.y,z))
def shape(ps):return Polygon([(pt(p).x,pt(p).y) for p in ps])
F=json.loads((OLD/'footprints.json').read_text())['features'];lake=shape(F[0]['pixel_outline']);patch=shape([(270,135),(1250,135),(1250,740),(1200,1060),(1100,1195),(275,1195)])
# Limit expensive geometry to the rendered neighbourhood, retaining surrounding context.
region=shape([(50,-100),(1480,-100),(1480,1440),(50,1440)]).buffer(35)
for ob in s.objects:
 if ob.type in ('MESH','CURVE'):
  corners=[ob.matrix_world@Vector(c) for c in ob.bound_box]
  if not FULL and corners and not region.intersects(Polygon([(min(p.x for p in corners),min(p.y for p in corners)),(max(p.x for p in corners),min(p.y for p in corners)),(max(p.x for p in corners),max(p.y for p in corners)),(min(p.x for p in corners),max(p.y for p in corners))]).buffer(.1)):ob.hide_render=True
 if ob.name.startswith(('Lake stone','Lake warm','Lake retaining','Shore continuous','Shore rail','Lake water','Source-visible entrance basin')):ob.hide_render=True
anchor=bpy.data.objects.new('Atlas metre frame',None);s.collection.objects.link(anchor)
def material(name,c,rough=.8):
 m=bpy.data.materials.new(name);m.use_nodes=True;bs=m.node_tree.nodes.get('Principled BSDF');bs.inputs['Base Color'].default_value=(*c,1);bs.inputs['Roughness'].default_value=rough;return m

def grain(m,colors,scale,detail=3,bumpdist=.008):
 ns=m.node_tree.nodes;ls=m.node_tree.links;bs=ns.get('Principled BSDF');tc=ns.new('ShaderNodeTexCoord');tc.object=anchor;n=ns.new('ShaderNodeTexNoise');n.inputs['Scale'].default_value=scale;n.inputs['Detail'].default_value=detail;ls.new(tc.outputs['Object'],n.inputs['Vector']);r=ns.new('ShaderNodeValToRGB')
 for e,c in zip(r.color_ramp.elements,colors):e.color=(*c,1)
 ls.new(n.outputs['Fac'],r.inputs[0]);ls.new(r.outputs[0],bs.inputs['Base Color']);b=ns.new('ShaderNodeBump');b.inputs['Distance'].default_value=bumpdist;b.inputs['Strength'].default_value=.17;ls.new(n.outputs['Fac'],b.inputs['Height']);ls.new(b.outputs[0],bs.inputs['Normal']);return tc,r
lawn=material('Atlas meadow',(.24,.36,.09));grain(lawn,[(.17,.30,.065),(.33,.43,.14)],.095,5)
pave=material('Atlas warm granite',(.61,.60,.53));grain(pave,[(.55,.54,.48),(.65,.64,.57)],3)
roadmat=material('Atlas asphalt',(.18,.20,.185));grain(roadmat,[(.17,.19,.18),(.21,.23,.215)],18)
curb=material('Atlas granite edge',(.69,.68,.58));soil=material('Atlas planted earth',(.12,.13,.065));joint=material('Atlas paving joints',(.44,.45,.40));paint=material('Atlas parking markings',(.81,.79,.65))
water=material('Atlas lake',(.045,.17,.135),.19);tc,r=grain(water,[(.028,.10,.075),(.043,.145,.12)],.10,2,.007);bs=water.node_tree.nodes.get('Principled BSDF');bs.inputs['Metallic'].default_value=.12;bs.inputs['IOR'].default_value=1.333
# Anisotropic small ripples catch directional light; lake outline remains the traced outline.
ns=water.node_tree.nodes;ls=water.node_tree.links;v=ns.new('ShaderNodeVectorMath');v.operation='MULTIPLY';v.inputs[1].default_value=(.8,6,1);ls.new(tc.outputs['Object'],v.inputs[0]);n=ns.new('ShaderNodeTexNoise');n.inputs['Scale'].default_value=2;n.inputs['Detail'].default_value=2;ls.new(v.outputs[0],n.inputs['Vector']);b=ns.new('ShaderNodeBump');b.inputs['Strength'].default_value=.13;b.inputs['Distance'].default_value=.018;ls.new(n.outputs[0],b.inputs['Height']);ls.new(b.outputs[0],bs.inputs['Normal'])

def surface(name,g,z,m):
 if g.is_empty:return
 vs=[];fs=[]
 for t in constrained_delaunay_triangles(g).geoms:
  k=len(vs);vs.extend([(x,y,z) for x,y in list(t.exterior.coords)[:-1]]);fs.append((k,k+1,k+2))
 me=bpy.data.meshes.new(name);me.from_pydata(vs,[],fs);me.materials.append(m);ob=bpy.data.objects.new(name,me);s.collection.objects.link(ob);return ob

def smooth(g,r=.65):return g.buffer(r).buffer(-r)
roadlines=[([(335,120),(337,401),(315,703),(281,1100),(285,1195)],10), ([(753,120),(758,418),(803,460)],7), ([(1240,120),(1242,610),(1225,771),(1170,1060),(1108,1140),(804,1150),(567,1140)],10), ([(347,440),(578,446),(691,440),(757,430)],5)]
road=unary_union([LineString([(pt(p).x,pt(p).y) for p in ps]).buffer(w/2,cap_style='flat') for ps,w in roadlines]).intersection(patch)
lawnpolys=[[(352,453),(579,445),(624,469),(623,514),(590,602),(569,737),(540,785),(538,871),(500,905),(308,885)],[(435,252),(615,273),(613,337),(434,324)],[(724,183),(760,184),(771,417),(740,435),(713,414)],[(842,351),(914,354),(915,417),(840,414)],[(953,355),(1139,367),(1140,430),(954,425)],[(881,485),(1027,494),(1025,550),(945,548)],[(609,1015),(738,1021),(733,1090),(604,1086)],[(935,1031),(1075,1036),(1067,1106),(938,1101)],[(767,478),(800,478),(840,489),(887,506),(936,516),(944,539),(914,546),(858,542),(819,535),(788,520),(771,507)]]
lawns=[smooth(shape(ps)) for ps in lawnpolys];lawns[-1]=lawns[-1].difference(lake.buffer(4.6))
paving=unary_union([shape(p) for p in [[(354,149),(730,172),(733,425),(698,448),(345,423)],[(790,234),(1242,255),(1225,658),(1090,752),(969,733),(986,556),(803,471)],[(588,789),(800,772),(967,737),(1180,725),(1140,991),(580,986)],[(576,984),(1130,982),(1095,1120),(568,1113)],[(310,905),(572,918),(557,1182),(289,1174)]]])
# Clip every replacement finish against source roof masks; do not bridge a courtyard with a convex hull.
bodies=unary_union([shape(f['pixel_outline']) for f in F if f['id'].startswith(('B06','B07','B08')) and len(f['pixel_outline'])>2]);mask=bodies.buffer(.08)
paved=smooth(paving).difference(unary_union(lawns)).difference(lake.buffer(4.6)).difference(road).difference(mask)
meadow=patch.difference(paved).difference(road).difference(lake.buffer(4.6)).difference(mask)
surface('Atlas meadow surface',meadow,.30,lawn);surface('Atlas unified paving',paved,.31,pave);surface('Atlas road surface',road.difference(mask),.32,roadmat)
surface('Atlas road edge',road.buffer(.26).difference(road).difference(mask).intersection(patch),.34,curb)
surface('Atlas paving border',paved.difference(paved.buffer(-.34)),.335,curb)
for g in lawns:
 surface('Atlas planted edge',g.buffer(.20).difference(g).intersection(paved.buffer(.22)).difference(mask).difference(lake.buffer(4.6)),.35,curb)
for x in range(-180,230,5):
 cut=LineString([(shift.x+x,shift.y-190),(shift.x+x,shift.y+190)]).buffer(.018).intersection(paved)
 surface('Atlas granite joint',cut,.321,joint)
for y in range(-190,190,5):surface('Atlas granite crossjoint',LineString([(shift.x-180,shift.y+y),(shift.x+230,shift.y+y)]).buffer(.018).intersection(paved),.322,joint)
surface('Atlas lake water',lake,-.08,water)
# Shallow water and stone treads follow source shoreline, dimensions interpreted.
shallow=material('Atlas shallow edge',(.08,.22,.165),.24)
surface('Atlas shallow water margin',lake.difference(lake.buffer(-1.0)), -.075,shallow)
for i in range(5):surface('Atlas bank tread',lake.buffer(.15+(i+1)*.48).difference(lake.buffer(.15+i*.48)),.0+i*.064,curb)
surface('Atlas promenade',lake.buffer(4.6).difference(lake.buffer(2.55)),.32,pave)
surface('Atlas shore planting edge',lake.buffer(4.85).difference(lake.buffer(4.6)).intersection(meadow),.34,soil)
# Restore source-visible parking rows and the semicircular basin, not decorative objects.
for yy in [929,961,1025,1063,1134,1165]:
 for xx in range(320,542,18):surface('Atlas parking bay',LineString([(pt((xx,yy)).x,pt((xx,yy)).y),(pt((xx,yy+25)).x,pt((xx,yy+25)).y)]).buffer(.055).intersection(paved),.34,paint)
for i in range(9):surface('Atlas source south crossing',shape([(798+i*7,1136),(801+i*7,1136),(801+i*7,1161),(798+i*7,1161)]).intersection(road),.34,paint)
basin=shape([(833+48*math.cos(math.pi+i*math.pi/48),1110+48*math.sin(math.pi+i*math.pi/48)) for i in range(49)])
surface('Atlas forecourt basin',basin,.34,water);surface('Atlas basin coping',basin.buffer(.35).difference(basin),.43,curb)
# Dense organic volume behind the retained leaves makes existing photographed trees legible at map scale.
leafcolors=[(.055,.18,.025),(.11,.27,.04),(.18,.34,.06),(.065,.23,.055),(.21,.32,.05)]
leafm=[material('Atlas foliage '+str(i),c) for i,c in enumerate(leafcolors)]
protos=[]
for seed in range(6):
 rng=random.Random(401+seed);bm=bmesh.new()
 for j in range(27):
  a=rng.random()*math.tau;rad=rng.uniform(.10,.68);loc=Vector((math.cos(a)*rad,math.sin(a)*rad,rng.uniform(-.40,.43)))
  res=bmesh.ops.create_icosphere(bm,subdivisions=2,radius=rng.uniform(.28,.44));newverts=res['verts']
  for vert in newverts:vert.co=Vector((vert.co.x,vert.co.y,vert.co.z*.8))+loc
  for face in {f for v in newverts for f in v.link_faces}:face.material_index=(j//6+seed)%5;face.smooth=True
 me=bpy.data.meshes.new('Atlas crown '+str(seed));bm.to_mesh(me);bm.free()
 for m in leafm:me.materials.append(m)
 protos.append(me)
originaltrees=[o for o in s.objects if o.type=='MESH' and o.name.startswith('Canopy ') and not o.hide_render]
for i,ob in enumerate(originaltrees):
 crown=bpy.data.objects.new('Atlas canopy volume '+str(i),protos[i%6]);s.collection.objects.link(crown);crown.matrix_world=ob.matrix_world.copy();crown.scale*=.90
 # Existing leaves stay as the fine silhouette layer; no source tree centre is moved.
for m in bpy.data.materials:
 if m.name.startswith(('Canopy ','Leaf tone')) and m.use_nodes:
  p=m.node_tree.nodes.get('Principled BSDF')
  if p:p.inputs['Base Color'].default_value=(*leafcolors[sum(map(ord,m.name))%5],1)
# Low planting clusters are limited to source-visible canopy/planting belts.
additional=[(569,800),(589,801),(617,798),(652,805),(715,803),(740,790),(965,757),(983,752),(1020,750),(1080,748),(1147,764),(1148,813),(1158,867),(1145,920),(1133,960),(994,574),(988,614),(986,660),(975,714),(824,513),(850,523),(880,525),(910,530),(710,1136),(749,1140),(780,1142),(822,1144),(865,1147),(913,1148),(956,1148),(1005,1147),(1049,1143)]
for i,p in enumerate(additional):
 v=pt(p);foot=Point(v.x,v.y)
 if mask.buffer(1).covers(foot) or lake.buffer(4.6).covers(foot) or road.covers(foot):continue
 ob=bpy.data.objects.new('Atlas source planting clump '+str(i),protos[i%6]);s.collection.objects.link(ob);ob.location=(v.x,v.y,1.1);ob.scale=(1.6,1.4,1.15)
# A continuous world-coordinate lawn material removes mismatched patch edges.
for ob in s.objects:
 if ob.type=='MESH' and not ob.hide_render:
  for slot in ob.material_slots:
   if slot.material and slot.material.name in ['Living lawn','Campus grass','Turf light'] and not ob.name.startswith(('S0','Track','Athletic','Court')):slot.material=lawn
# Full-campus finishes reuse the fixed union meshes and preserve traced building polygons.
D=json.loads((BASE/'layout.json').read_text());MAIN=json.loads((BASE/'references/satellite-export.json').read_text());NORTH=json.loads((BASE/'references/north-extension.json').read_text())
def gp(q,z=0,source='satellite'):
 e=(NORTH if source=='north-extension' else MAIN)['extent'];w,h=(1000,900) if source=='north-extension' else (1152,1920)
 return Vector(((e['xmin']+q[0]/w*(e['xmax']-e['xmin'])-ox)*cos,(e['ymax']-q[1]/h*(e['ymax']-e['ymin'])-oy)*cos,z))
def gshape(rec):return Polygon([(gp(q,source=rec.get('source','satellite')).x,gp(q,source=rec.get('source','satellite')).y) for q in rec['outline']])
full_checks={}
if FULL:
 road_data=json.loads((BASE/'roads.json').read_text())
 def from_layer(layer):
  verts=layer['vertices'];return unary_union([Polygon([(verts[i][0],verts[i][1]) for i in f]) for f in layer['faces'] if len(f)==3])
 layers={layer['name']:from_layer(layer) for layer in road_data['layers']}
 all_roofs=unary_union([gshape(r) for r in D['buildings']]+[bodies]).buffer(.35)
 all_water=unary_union([gshape(r) for r in D['surfaces'] if r['kind']=='water']+[lake])
 exclusion=all_roofs.union(all_water).union(patch)
 # Bounded smoothing acts only on an existing evidenced paved surface. Narrow traced paths survive.
 asphalt=layers['Road asphalt union'].difference(exclusion)
 old_paving=layers['Road paving union'];clean=smooth(old_paving,1.05).buffer(-.30).buffer(.30).simplify(.45,preserve_topology=True)
 pieces=[g for g in (list(clean.geoms) if hasattr(clean,'geoms') else [clean]) if g.geom_type=='Polygon' and g.area>=8]
 clean=unary_union([Polygon(g.exterior,[ring for ring in g.interiors if Polygon(ring).area>=18]) for g in pieces]).difference(exclusion)
 # Source planting beds and sports retain their original extents after smoothing.
 sourcebeds=unary_union([gshape(r) for r in D.get('landscape',{}).get('lawn_polygons',[])])
 clean=clean.difference(sourcebeds).difference(asphalt)
 for name in ['Road paving union','Road asphalt union','Road mineral curbs']:
  obj=bpy.data.objects.get(name)
  if obj:obj.hide_render=True
 surface('Atlas campus paving',clean,.17,pave);surface('Atlas campus asphalt',asphalt,.20,roadmat)
 surface('Atlas campus curbs',asphalt.buffer(.23).difference(asphalt).difference(exclusion),.25,curb)
 surface('Atlas campus paving course',clean.difference(clean.buffer(-.22)),.18,curb)
 for ob in s.objects:
  if ob.type!='MESH' or ob.hide_render:continue
  for slot in ob.material_slots:
   if slot.material and slot.material.name=='Pedestrian paving':slot.material=pave
   elif slot.material and slot.material.name=='Lake water':slot.material=water
 # Parking lots are continuous paved areas in the imagery, not asphalt patches with white classification islands.
 for rec in D['surfaces']:
  if rec['kind']!='parking':continue
  g=gshape(rec).difference(exclusion);obj=bpy.data.objects.get(rec['id'])
  if obj:obj.hide_render=True
  surface('Atlas '+rec['id'],g,.19,pave)
  rect=list(g.minimum_rotated_rectangle.exterior.coords) if not g.is_empty else []
  if len(rect)<4:continue
  a,b=max(zip(rect,rect[1:]),key=lambda ab:Point(ab[0]).distance(Point(ab[1])));dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy);u=Vector((dx/length,dy/length));v=Vector((-u.y,u.x));c=Vector((g.centroid.x,g.centroid.y));width=g.area/length
  for side in [-1,1]:
   for j in range(int(length/2.8)-1):
    p=c+u*(-length/2+3+j*2.8)+v*side*(width/2-2);q=p-v*side*5
    line=LineString([tuple(p),tuple(q)]).buffer(.045).intersection(g.buffer(-.5));surface('Atlas illustrative parking line',line,.215,paint)
 # The model surrounds are shown with the fixed imagery, rather than an arbitrary blank skirt.
 from shapely.geometry import box
 grounds=unary_union([gshape(r) for r in D['surfaces'] if r['kind']=='ground'])
 cut_y=gp((0,90)).y
 for src in ['satellite','north-extension']:
  e=(NORTH if src=='north-extension' else MAIN)['extent'];w,h=(1000,900) if src=='north-extension' else(1152,1920)
  coverage=Polygon([(gp(q,source=src).x,gp(q,source=src).y) for q in [(0,0),(w,0),(w,h),(0,h)]])
  coverage=coverage.intersection(box(-10000,cut_y,10000,10000)) if src=='north-extension' else coverage.intersection(box(-10000,-10000,10000,cut_y))
  old=bpy.data.objects.get(src+' outside-campus context')
  if old:
   old.hide_render=True;ob=surface('Atlas '+src+' context',coverage.difference(grounds),-.026,old.data.materials[0]);uv=ob.data.uv_layers.new(name='Source geographic UV')
   for face in ob.data.polygons:
    for li in face.loop_indices:
     v=ob.data.vertices[ob.data.loops[li].vertex_index].co;uv.data[li].uv=((v.x/cos+ox-e['xmin'])/(e['xmax']-e['xmin']),(v.y/cos+oy-e['ymin'])/(e['ymax']-e['ymin']))
 full_checks={'full_paving_roof_intersection_m2':clean.intersection(all_roofs).area,'full_paving_water_intersection_m2':clean.intersection(all_water).area,'full_asphalt_roof_intersection_m2':asphalt.intersection(all_roofs).area,'paving_parts':len(pieces),'fixed_layout_sha256':hashlib.sha256((BASE/'layout.json').read_bytes()).hexdigest(),'fixed_roads_sha256':hashlib.sha256((BASE/'roads.json').read_bytes()).hexdigest()}
 assert max(full_checks[k] for k in full_checks if k.endswith('_m2'))<1e-5
 print('Full-campus ground finishes ready',full_checks,flush=True)
refinement={}
if FULL:
 sys.dont_write_bytecode=True
 sys.path.insert(0,str(ROOT/'scripts'))
 from refine_buildings import refine_north
 refinement=refine_north(s,D,gp,material,ROOT)
 # Hand-reviewed hardscape between the photographed west apartment wings.
 # These boundaries follow the fixed satellite, keeping its surrounding woodland.
 north_courts=[[(559,359),(623,359),(623,439),(560,439)],[(512,396),(560,396),(561,440),(508,440)],[(476,440),(527,440),(527,502),(478,502)],[(529,455),(612,455),(617,513),(529,513)],[(510,438),(623,438),(623,457),(529,457),(529,450),(510,450)]]
 north_ground=unary_union([gshape({'outline':ps}) for ps in north_courts]).difference(all_roofs).difference(all_water).difference(asphalt)
 surface('Atlas north apartment forecourts',north_ground,.215,pave)
 surface('Atlas north forecourt edge',north_ground.difference(north_ground.buffer(-.20)),.222,curb)
 full_checks['north_forecourt_roof_intersection_m2']=north_ground.intersection(all_roofs).area
 full_checks['north_forecourt_water_intersection_m2']=north_ground.intersection(all_water).area
 refinement['forecourt_source_pixels']=north_courts
 # Three source-visible planted beds receive low hedges and a stone margin.
 # Existing building and road masks prevent a planting strip from blocking either.
 from shapely.affinity import scale as scale_geometry
 for rec in D.get('landscape',{}).get('lawn_polygons',[]):
  if not rec['id'].startswith(('N07','N34','E formal')):continue
  g=gshape(rec).difference(all_roofs).difference(asphalt)
  surface('Atlas planting margin '+rec['id'],g.buffer(.28).difference(g).difference(all_roofs).difference(asphalt).difference(all_water),.23,curb)
  belt=g.buffer(-.35).boundary
  if belt.is_empty:continue
  for i in range(max(1,int(belt.length/1.2))):
   q=belt.interpolate(i*1.2)
   ob=bpy.data.objects.new('Atlas low hedge '+rec['id']+' '+str(i),protos[i%6]);s.collection.objects.link(ob);ob.location=(q.x,q.y,.63);ob.scale=(1.0,.82,.64)
 # Oval hardscape is visible in the fixed N07 forecourt; no new route is inferred.
 c=gp((720,366));oval=scale_geometry(Point(c.x,c.y).buffer(1,resolution=48),xfact=7.1,yfact=11.2,origin=(c.x,c.y))
 northpave=clean.intersection(gshape({'outline':[(627,325),(768,331),(766,539),(628,538)]}))
 surface('Atlas north oval court rim',oval.buffer(.20).difference(oval.buffer(-.20)).intersection(northpave),.205,curb)
 for xx in range(-50,80,5):
  line=LineString([(c.x+xx,c.y-210),(c.x+xx,c.y+60)]).buffer(.022).intersection(northpave)
  surface('Atlas north plaza joint',line,.186,joint)
 for xx in range(470,630,4):
  a=gp((xx,350));b=gp((xx,525));line=LineString([(a.x,a.y),(b.x,b.y)]).buffer(.024).intersection(north_ground)
  surface('Atlas apartment paving joint',line,.227,joint)
 for rec in D.get('landscape',{}).get('paving_polygons',[]):
  if not rec['id'].startswith('E formal'):continue
  plaza=gshape(rec).intersection(clean);x0,y0,x1,y1=plaza.bounds
  for xx in range(math.floor(x0),math.ceil(x1),5):
   strip=LineString([(xx,y0),(xx,y1)]).buffer(.022).intersection(plaza)
   surface('Atlas northern plaza joint',strip,.186,joint)
  for yy in range(math.floor(y0),math.ceil(y1),5):
   strip=LineString([(x0,yy),(x1,yy)]).buffer(.022).intersection(plaza)
   surface('Atlas northern plaza joint',strip,.186,joint)
 print('Architectural refinement ready',len(refinement['building_ids']),'buildings',refinement['total_vertices'],'vertices',flush=True)
# Simplify lighting into a coherent map-like daylight setup.
s.world.use_nodes=True;ns=s.world.node_tree.nodes;ls=s.world.node_tree.links;ns.clear();bg=ns.new('ShaderNodeBackground');bg.inputs['Color'].default_value=(.71,.80,.91,1);bg.inputs['Strength'].default_value=.65;out=ns.new('ShaderNodeOutputWorld');ls.new(bg.outputs[0],out.inputs[0])
for o in s.objects:
 if o.type=='LIGHT':o.hide_render=True
ld=bpy.data.lights.new('Atlas daylight','SUN');ld.energy=2.3;ld.angle=.12;sun=bpy.data.objects.new('Atlas daylight',ld);s.collection.objects.link(sun);sun.rotation_euler=(.38,-.48,-.25)
cam=s.camera;target=pt((785,680),5);cam.location=target+Vector((90,-260,490));cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.type='ORTHO';cam.data.ortho_scale=438;cam.data.clip_end=4000
s.render.engine='CYCLES';s.cycles.samples=36 if FINAL else 12;s.cycles.use_denoising=True;s.cycles.max_bounces=4;s.cycles.transparent_max_bounces=4;s.render.threads_mode='FIXED';s.render.threads=4
s.render.resolution_x=2800 if FINAL else 1400;s.render.resolution_y=2400 if FINAL else 1200;s.render.resolution_percentage=100;s.render.use_border=False;s.render.use_crop_to_border=False;s.render.image_settings.file_format='PNG';s.render.image_settings.compression=100;s.render.filepath=str(CACHE/'campus.png');s.view_settings.view_transform='AgX';s.view_settings.look='AgX - Medium High Contrast';s.view_settings.exposure=.15
if FULL:
 s.render.resolution_x=7168 if FINAL else 2400;s.render.resolution_y=3072 if FINAL else 1029;s.cycles.samples=24 if FINAL else 8
 # Fit the actual modeled site, with north running towards the right in the overview.
 points_world=[gp(q,0,r.get('source','satellite')) for r in D['surfaces'] if r['kind']=='ground' for q in r['outline']]
 target=Vector((sum(p.x for p in points_world)/len(points_world),sum(p.y for p in points_world)/len(points_world),0));cam.location=target+Vector((1700,-500,2300));cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler();bpy.context.view_layer.update()
 inv=cam.matrix_world.inverted();proj=[inv@v for v in points_world];xs=[v.x for v in proj];ys=[v.y for v in proj];cam.location+=cam.matrix_world.to_3x3()@Vector(((min(xs)+max(xs))/2,(min(ys)+max(ys))/2,0));cam.data.ortho_scale=max(max(xs)-min(xs),(max(ys)-min(ys))*s.render.resolution_x/s.render.resolution_y)*1.08
if NORTH_PREVIEW:
 assert not FINAL,'--north is a local preview only; reviewed final export uses --campus --final'
 s.render.resolution_x=1800;s.render.resolution_y=1350;s.cycles.samples=16
 focus=[gp(q,r['height_estimate_m']) for r in D['buildings'] if r['id'].startswith('N') and r['id'] in refinement['photo_facade_building_ids'] and int(r['id'][1:])>=21 for q in r['outline']]
 target=sum(focus,Vector())/len(focus);cam.location=target+Vector((85,-220,310));cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler();bpy.context.view_layer.update()
 inv=cam.matrix_world.inverted();proj=[inv@v for v in focus];xs=[v.x for v in proj];ys=[v.y for v in proj];cam.location+=cam.matrix_world.to_3x3()@Vector(((min(xs)+max(xs))/2,(min(ys)+max(ys))/2,0));cam.data.ortho_scale=max(max(xs)-min(xs),(max(ys)-min(ys))*s.render.resolution_x/s.render.resolution_y)*1.24
if PREVIEW_REGION:
 s.render.resolution_x=1800;s.render.resolution_y=1350;s.cycles.samples=16
 prefixes={'north':('N',),'extension':('E',),'middle':('M',),'south':('F','S')}[PREVIEW_REGION]
 focus=[gp(q,r['height_estimate_m'],r.get('source','satellite')) for r in D['buildings'] if r['id'].startswith(prefixes) for q in r['outline']]
 target=sum(focus,Vector())/len(focus);cam.location=target+Vector((170,-50,230));cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler();bpy.context.view_layer.update()
 inv=cam.matrix_world.inverted();proj=[inv@v for v in focus];xs=[v.x for v in proj];ys=[v.y for v in proj];cam.location+=cam.matrix_world.to_3x3()@Vector(((min(xs)+max(xs))/2,(min(ys)+max(ys))/2,0));cam.data.ortho_scale=max(max(xs)-min(xs),(max(ys)-min(ys))*s.render.resolution_x/s.render.resolution_y)*1.16
bpy.context.view_layer.update()
# Project roof polygons with exactly the render camera. The browser never guesses map positions.
W,H=s.render.resolution_x,s.render.resolution_y
records=[]
for ident,name in [('B06','六号教学楼'),('B07','湖西庭院建筑'),('B08','湖东北建筑群')]:
 polygons=[]
 for f in F:
  if not f['id'].startswith(ident):continue
  p=Polygon([(world_to_camera_view(s,cam,pt(q,f.get('base_z',0)+f.get('height_m_estimate',0))).x*W,(1-world_to_camera_view(s,cam,pt(q,f.get('base_z',0)+f.get('height_m_estimate',0))).y)*H) for q in f['pixel_outline']])
  if p.is_valid:polygons.append(p)
 union=unary_union(polygons);label=union.representative_point();rings=[list(p.exterior.coords) for p in (union.geoms if hasattr(union,'geoms') else [union])]
 records.append({'id':ident,'name':name,'polygons':rings,'anchor':[label.x,label.y],'name_status':'school photo confirmed' if ident=='B06' else 'regional description','description':{'B06':'照片可识别的六号教学楼。弧形端部、红色立面带和入口柱廊按照片表现。','B07':'中央湖西的庭院式建筑。屋顶、庭院和光伏阵列依据影像描绘；此名称为区域描述。','B08':'中央湖东北的组合楼群。浅色立柱与金属屋面按照片表现；此名称为区域描述。'}[ident]})
for record in records:record['region']='lake';record['kind']='academic';record['priority']=100
if FULL:
 for row in D['buildings']:
  z=row['height_estimate_m']+.45;poly=Polygon([(world_to_camera_view(s,cam,gp(q,z,row.get('source','satellite'))).x*W,(1-world_to_camera_view(s,cam,gp(q,z,row.get('source','satellite'))).y)*H) for q in row['outline']]);label=poly.representative_point()
  reg={'N':'north','E':'extension','M':'middle','S':'south','F':'south'}[row['id'][0]]
  records.append({'id':row['id'],'name':row['name'],'region':reg,'kind':row['kind'],'polygons':[list(poly.exterior.coords)],'anchor':[label.x,label.y],'name_status':'regional description','description':row['name']+'。屋顶轮廓依据影像描绘；立面按已有照片可见的建筑类型表现，名称为区域描述。','height_estimate_m':row['height_estimate_m'],'floors_estimate':row['floors_estimate'],'priority':min(80,poly.area/100)})
 for record in records:
  faces=refinement.get('roof_faces_world',{}).get(record['id'])
  if not faces:continue
  polygons=[]
  for face in faces:
   projected=[world_to_camera_view(s,cam,Vector(p)) for p in face]
   p=Polygon([(q.x*W,(1-q.y)*H) for q in projected])
   if p.is_valid and p.area>.000001:polygons.append(p)
  union=unary_union(polygons);parts=list(union.geoms) if hasattr(union,'geoms') else [union];label=union.representative_point()
  record['polygons']=[list(p.exterior.coords) for p in parts];record['anchor']=[label.x,label.y]
  photo=record['id'] in refinement['photo_facade_building_ids']
  record['detail_status']='photo-led north refinement; dimensions interpreted' if photo else 'satellite roof refinement; facade family and dimensions estimated'
  feature='阳台、楼层线和屋顶' if record['kind']=='dorm' else '红砖窗组与玻璃入口' if record['id'] in ('N34','N35') else '蓝色大厅屋顶和低层窗组' if record['id'] in ('N32','N33') else '浅色立面带、窗组和入口'
  record['description']=record['name']+'。'+('依据校方航拍细化'+feature+'；轮廓沿用固定影像，细部尺寸和未见立面采用估算。' if photo else '屋顶轮廓与色调依据固定卫星影像细化；窗组、檐口和楼层线为类型化推定，缺少该楼近景照片核实。')+'名称为区域描述。'
 assert len(records)==len(D['buildings'])+3==130
 assert len({r['id'] for r in records})==130
 assert sum(bool(r.get('detail_status')) for r in records)==len(refinement['building_ids'])
regions=[]
for ident,name in [('lake','中央湖区'),('north','北区'),('extension','北端区域'),('middle','中区'),('south','南区与花卉园')]:
 rows=[r for r in records if r['region']==ident]
 if not rows:continue
 ps=[p for r in rows for ring in r['polygons'] for p in ring];xs=[p[0] for p in ps];ys=[p[1] for p in ps];regions.append({'id':ident,'name':name,'bounds':[min(xs),min(ys),max(xs),max(ys)],'count':len(rows)})
meta={'title':'太湖校园地图' if FULL else '中央湖区','scope':'full-campus source-based exterior atlas' if FULL else 'central-region visual development sample','coverage':'campus' if FULL else 'central','regions':regions,'width':W,'height':H,'records':records,'source_scene_sha256':sourcehash,'source_image_sha256':hashlib.sha256((OLD/'references/satellite.jpg').read_bytes()).hexdigest(),'source_footprints_sha256':hashlib.sha256((OLD/'footprints.json').read_bytes()).hexdigest(),'generator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'camera':{'position':list(cam.location),'rotation_euler':list(cam.rotation_euler),'ortho_scale':cam.data.ortho_scale},'method':'Native orthographic Cycles render of retained source scene with source-traced ground refinements; projected roof hotspots use the identical camera','limitations':'Heights, finish dimensions and plant forms interpreted. No surveyed navigation network. B07/B08 are descriptive names.','samples':s.cycles.samples,'render_status':'pending','checks':{'source_building_scene_preserved':True,'paving_water_intersection_m2':paved.intersection(lake).area,'paving_roof_intersection_m2':paved.intersection(mask).area,'original_tree_centres_retained':len(originaltrees),**full_checks},'candidate_path':str(CACHE/'campus.png')}
if refinement:
 meta['building_refinement']=refinement;meta['checks'].pop('source_building_scene_preserved');meta['checks']['source_scene_file_preserved']=True;meta['checks']['source_roof_outlines_preserved']=True
 meta['method']='Native Cycles atlas with source-traced ground, 26 photo-led north parts and 101 satellite-led roof/facade refinements; retained scene is unchanged, all refined roof surfaces independently projected for hotspots'
assert meta['checks']['paving_water_intersection_m2']<1e-6
assert meta['checks']['paving_roof_intersection_m2']<1e-6
(CACHE/'atlas.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2))
if FULL and FINAL:
 # One reused tile PNG and one in-memory image; no full-size PNG or scene backup is written.
 bridge=subprocess.Popen(['/opt/anaconda3/bin/python',str(ROOT/'scripts/export_atlas.py'),'--stream'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,bufsize=1)
 def send(command):
  bridge.stdin.write(json.dumps(command)+'\n');bridge.stdin.flush();answer=bridge.stdout.readline();assert answer and json.loads(answer).get('ok'),answer
 send({'action':'begin','width':W,'height':H});s.render.use_border=True;s.render.use_crop_to_border=True;s.render.use_persistent_data=True
 for row in range(2):
  for col in range(4):
   core=(col*W//4,row*H//2,(col+1)*W//4,(row+1)*H//2);x0=max(0,core[0]-24);y0=max(0,core[1]-24);x1=min(W,core[2]+24);y1=min(H,core[3]+24)
   s.render.border_min_x=(x0+.05)/W if x0 else 0;s.render.border_max_x=min(1,(x1+.05)/W);s.render.border_min_y=((H-y1)+.05)/H if H-y1 else 0;s.render.border_max_y=min(1,((H-y0)+.05)/H)
   tile=CACHE/'render-tile.png';s.render.filepath=str(tile);print('ATLAS TILE',row,col,flush=True);bpy.ops.render.render(write_still=True)
   send({'action':'tile','file':str(tile),'core':core,'render_bounds':[x0,y0,x1,y1]})
 send({'action':'finish'});bridge.stdin.close();assert bridge.wait()==0
else:
 print('ATLAS RENDER',W,H,'trees',len(originaltrees),flush=True);bpy.ops.render.render(write_still=True)
 meta['render_status']='generated_needs_visual_review';meta['png_sha256']=hashlib.sha256((CACHE/'campus.png').read_bytes()).hexdigest();(CACHE/'atlas.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2))
assert sourcehash==hashlib.sha256(source.read_bytes()).hexdigest()
print('ATLAS DONE',flush=True)
