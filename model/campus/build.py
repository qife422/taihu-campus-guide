"""Full-campus architectural interpretation from individually traced roofs.
Run Blender --background --python model/campus/build.py -- --preview
Or omit --preview for editable scene and GLB; render.py produces memory-bounded 8K tiles.
"""
import bpy,math,json,random,sys,hashlib,struct
from pathlib import Path
from mathutils import Vector,Matrix,Quaternion
from mathutils.geometry import tessellate_polygon
sys.path.insert(0,'/tmp/taihu-gis-deps')
from shapely.geometry import Polygon,Point,LineString
from shapely import constrained_delaunay_triangles
def finalize_glb_colors(path):
 # Procedural Blender color nodes cannot be represented by glTF. Preserve their authored base colors.
 raw=path.read_bytes();length=struct.unpack_from('<I',raw,12)[0];data=json.loads(raw[20:20+length]);count=0
 for material in data.get('materials',[]):
  pbr=material.setdefault('pbrMetallicRoughness',{});source=bpy.data.materials.get(material['name'])
  shader=source.node_tree.nodes.get('Principled BSDF') if source and source.use_nodes else None
  color=shader.inputs['Base Color'] if shader else None
  procedural=color and color.is_linked and color.links[0].from_node.bl_idname!='ShaderNodeTexImage'
  if procedural and 'baseColorTexture' in pbr:pbr.pop('baseColorTexture')
  if source and 'baseColorTexture' not in pbr and ('baseColorFactor' not in pbr or material.get('extras',{}).get('base_color_source') or procedural):
   pbr['baseColorFactor']=list(color.default_value if color else source.diffuse_color);material.setdefault('extras',{})['base_color_source']='Blender authored Principled base color; procedural finish approximated';count+=1
 encoded=json.dumps(data,separators=(',',':'),ensure_ascii=False).encode();encoded+=b' '*((-len(encoded))%4);tail=raw[20+length:]
 path.write_bytes(struct.pack('<4sII',b'glTF',2,20+len(encoded)+len(tail))+struct.pack('<II',len(encoded),0x4E4F534A)+encoded+tail)
 print('Preserved authored display colors for',count,'procedural materials',flush=True)
ROOT=Path(__file__).resolve().parent
D=json.loads((ROOT/'layout.json').read_text()); MAIN=json.loads((ROOT/'references/satellite-export.json').read_text()); NORTH=json.loads((ROOT/'references/north-extension.json').read_text())
PREVIEW='--preview' in sys.argv;CANDIDATE='--candidate' in sys.argv; random.seed(31)
EXT=MAIN['extent']; COS=math.cos(math.radians(31.578)); UNIT=(EXT['xmax']-EXT['xmin'])/1152*COS
OX=EXT['xmin']+600/1152*(EXT['xmax']-EXT['xmin']); OY=EXT['ymax']-850/1920*(EXT['ymax']-EXT['ymin'])
# Open the editable study directly: appending 27k independent objects has quadratic library-localization cost.
bpy.ops.wm.open_mainfile(filepath=str(ROOT.parent/'study/campus.blend'))
study_objects=[o for o in bpy.context.scene.objects if o.type in ('MESH','CURVE','EMPTY')]
bpy.data.batch_remove(ids=[o for o in bpy.context.scene.objects if o.type not in ('MESH','CURVE','EMPTY')])
scene=bpy.context.scene;scene.unit_settings.system='METRIC';scene['status']='Photo interpreted architectural model; heights estimated; source chronology unknown'
scene['origin_epsg3857']=f'{OX},{OY}';scene['metric_scale']=COS;scene['refinement_version']='source-aligned-campus-1';scene['central_study_sha256']=hashlib.sha256((ROOT.parent/'study/campus.blend').read_bytes()).hexdigest()

def merc(p,source='satellite'):
 m=NORTH if source=='north-extension' else MAIN; e=m['extent'];w,h=(1000,900) if source=='north-extension' else (1152,1920)
 # Subtract the large map origin before converting to Blender's float32 vectors.
 return (e['xmin']+p[0]/w*(e['xmax']-e['xmin']),e['ymax']-p[1]/h*(e['ymax']-e['ymin']))
def pt(p,z=0,source='satellite'):
 p=merc(p,source);return Vector(((p[0]-OX)*COS,(p[1]-OY)*COS,z))
def points(r):return [pt(p,source=r.get('source','satellite')) for p in r['outline']]
def ccw(ps):
 if sum(a.x*b.y-b.x*a.y for a,b in zip(ps,ps[1:]+ps[:1]))<0: return list(reversed(ps))
 return ps
M=[]
def mat(name,c,rough=.65,metal=0):
 a=bpy.data.materials.new(name);a.diffuse_color=(*c,1);a.use_nodes=True;p=a.node_tree.nodes.get('Principled BSDF');p.inputs['Base Color'].default_value=(*c,1);p.inputs['Roughness'].default_value=rough;p.inputs['Metallic'].default_value=metal;M.append(a);return len(M)-1
cream=mat('Warm limestone plaster',(.74,.70,.61));rose=mat('Pale salmon dormitory',(.72,.43,.34));brick=mat('Terracotta brick',(.52,.13,.07));ivory=mat('Window surround ivory',(.85,.83,.74));glass=mat('Recessed glass',(.075,.15,.18),.23,.15)
darkroof=mat('Dark roof tiles',(.12,.16,.15));redroof=mat('Clay roof tiles',(.42,.10,.055));flatroof=mat('Concrete roof',(.42,.44,.40));steel=mat('Metalwork',(.45,.50,.47),.35,.5);blueroof=mat('Observed blue metal roof',(.075,.26,.36),.55,.15);lightroof=mat('Observed light metal roof',(.58,.60,.55),.65,.12)
pave=mat('Pedestrian paving',(.56,.55,.48));roadmat=mat('Road asphalt',(.105,.12,.115));mark=mat('Court and road lines',(.88,.88,.78));grass=mat('Campus grass',(.17,.31,.065));grass2=mat('Turf light',(.19,.36,.085));grass3=mat('Turf dark',(.10,.26,.055));woodmat=mat('Woodland floor',(.09,.19,.035));water=mat('Lake water',(.075,.13,.085),.23,.10);trackmat=mat('Athletics surface',(.47,.115,.075));courtmat=mat('Court green',(.09,.32,.23));bark=mat('Tree bark',(.15,.09,.042));leaves=[mat('Canopy '+str(i),c,.85) for i,c in enumerate([(.085,.18,.035),(.14,.25,.055),(.20,.31,.075),(.075,.18,.055),(.24,.30,.09),(.13,.22,.055)])];edge=mat('Site cut edge',(.30,.36,.24));roofglass=mat('Roof glass',(.10,.23,.27),.25,.20);curbmat=mat('Source road pale curbs',(.70,.68,.58))
anchor=bpy.data.objects.new('Campus texture frame',None);scene.collection.objects.link(anchor)
def finish(mi,scale=1,contrast=.15):
 m=M[mi];ns=m.node_tree.nodes;ls=m.node_tree.links;bs=ns.get('Principled BSDF');tc=ns.new('ShaderNodeTexCoord');tc.object=anchor
 n=ns.new('ShaderNodeTexNoise');n.inputs['Scale'].default_value=scale;n.inputs['Detail'].default_value=3;ls.new(tc.outputs['Object'],n.inputs['Vector']);r=ns.new('ShaderNodeValToRGB');c=bs.inputs['Base Color'].default_value[:3]
 r.color_ramp.elements[0].color=(*[v*(1-contrast) for v in c],1);r.color_ramp.elements[1].color=(*[min(1,v*(1+contrast)) for v in c],1);ls.new(n.outputs['Fac'],r.inputs[0]);ls.new(r.outputs[0],bs.inputs['Base Color']);b=ns.new('ShaderNodeBump');b.inputs['Distance'].default_value=.013;b.inputs['Strength'].default_value=.16;ls.new(n.outputs['Fac'],b.inputs['Height']);ls.new(b.outputs[0],bs.inputs['Normal'])
for mi in [cream,rose,brick,ivory]:finish(mi,30,.075)
for mi in [darkroof,redroof,flatroof,lightroof,blueroof]:finish(mi,10,.12)
for mi in [grass,grass2,grass3,woodmat]:finish(mi,.32,.24)
finish(pave,8,.09);finish(roadmat,24,.10);finish(bark,15,.10)

class Batch:
 def __init__(self,name):self.name=name;self.v=[];self.f=[];self.mi=[]
 def add(self,v,f,m):
  k=len(self.v);self.v.extend([tuple(p) for p in v]);self.f.extend([tuple(k+i for i in face) for face in f]);self.mi.extend([m]*len(f))
 def box(self,c,size,m,angle=0):
  x,y,z=[t/2 for t in size];co,si=math.cos(angle),math.sin(angle)
  vs=[Vector((c[0]+a*co-b*si,c[1]+a*si+b*co,c[2]+d)) for a,b,d in [(-x,-y,-z),(x,-y,-z),(x,y,-z),(-x,y,-z),(-x,-y,z),(x,-y,z),(x,y,z),(-x,y,z)]]
  self.add(vs,[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)],m)
 def poly(self,ps,z,h,m):
  ps=ccw(ps);n=len(ps);vs=[(p.x,p.y,z) for p in ps]+[(p.x,p.y,z+h) for p in ps]
  self.add(vs,[tuple(reversed(range(n))),tuple(range(n,n*2))]+[(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)],m)
 def line(self,ps,w,z,h,m,closed=False):
  pp=ps+[ps[0]] if closed else ps
  for a,b in zip(pp,pp[1:]):
   v=b-a;c=(a+b)/2;c.z=z+h/2
   if v.length>1e-6:self.box(c,(v.length,w,h),m,math.atan2(v.y,v.x))
 def finish(self,col=None,props=None):
  if not self.v:return None
  me=bpy.data.meshes.new(self.name);me.from_pydata(self.v,[],self.f);me.update()
  for m in M:me.materials.append(m)
  for face,i in zip(me.polygons,self.mi):face.material_index=i
  if me.validate(clean_customdata=True):print('Removed degenerate generated mesh elements:',self.name,flush=True)
  ob=bpy.data.objects.new(self.name,me);(col or bpy.context.collection).objects.link(ob)
  if props:
   for k,v in props.items():ob[k]=v if isinstance(v,(str,int,float,bool)) else json.dumps(v,ensure_ascii=False)
  return ob

def collection(name):c=bpy.data.collections.new(name);scene.collection.children.link(c);return c
buildcol=collection('01 Buildings | source traced');groundcol=collection('02 Ground roads water');sportcol=collection('03 Sports');treecol=collection('04 Vegetation | illustrative crowns');refcol=collection('05 Hidden source imagery');labelcol=collection('06 Place labels | viewport only')
# Source roof polygons are unchanged. Facade profiles are photo-supported or explicitly typological.
def roof_triangles(batch,g,base,rise,slope,mi,outer):
 if g.is_empty:return
 for tri in constrained_delaunay_triangles(g).geoms:
  coords=list(tri.exterior.coords)[:-1];batch.add([(x,y,base+min(rise,outer.boundary.distance(Point(x,y))*slope)) for x,y in coords],[(0,1,2)],mi)
def model_roof(batch,ps,r):
 height=r['height_estimate_m'];tone=r.get('roof_tone','charcoal');rm={'terracotta':redroof,'blue_metal':blueroof,'light_metal':lightroof,'charcoal':darkroof}[tone];g=Polygon([(p.x,p.y) for p in ps]);base=height+.45
 if r['roof'] in ('hip','gable'):
  if len(ps)==4:
   lengths=[(ps[(i+1)%4]-ps[i]).length for i in range(4)];i=max(range(4),key=lambda j:lengths[j]);a,b,c,d=[ps[(i+j)%4] for j in range(4)];e=(a+d)/2;f=(b+c)/2;axis=(f-e).normalized();dep=((a-d).length+(b-c).length)/2;rise=min(2.5,dep*.17)
   if r['roof']=='hip':e+=axis*min(dep*.4,(f-e).length*.2);f-=axis*min(dep*.4,(f-e).length*.2)
   vs=[(p.x,p.y,base) for p in [a,b,c,d]]+[(e.x,e.y,base+rise),(f.x,f.y,base+rise)]
   batch.add(vs,[(0,1,5,4),(1,2,5),(2,3,4,5),(3,0,4)],rm);batch.line([e,f],.16,base+rise,.10,rm)
  else:
   # Continuous distance-to-eave pitch on concave/courtyard footprints, not a flat bounding box.
   remaining=g;distance=0;rise=2.3;slope=.30
   for j in range(14):
    distance+=.65;inner=g.buffer(-distance,join_style='mitre');band=remaining.difference(inner);roof_triangles(batch,band,base,rise,slope,rm,g);remaining=inner
    if remaining.is_empty:break
   if not remaining.is_empty:roof_triangles(batch,remaining,base,rise,slope,rm,g)
  batch.line(ps,.30,height+.32,.20,brick if r['facade_profile']=='pink_balcony' else ivory,True)
 else:
  rm=lightroof if tone=='light_metal' else blueroof if tone=='blue_metal' else flatroof
  batch.poly(ps,height+.35,.18,rm);batch.line(ps,.26,height+.53,.60,ivory,True);batch.line(ps,.36,height+1.10,.10,ivory,True)
  edges=[(a,b) for a,b in zip(ps,ps[1:]+ps[:1])];a,b=max(edges,key=lambda ab:(ab[1]-ab[0]).length);u=(b-a).normalized();v=Vector((-u.y,u.x,0));c=Vector((g.centroid.x,g.centroid.y,0));span=math.hypot(g.bounds[2]-g.bounds[0],g.bounds[3]-g.bounds[1]);inset=g.buffer(-.48)
  for j in range(-int(span/6),int(span/6)+1):
   q=c+v*j*6;cut=LineString([(q.x-u.x*span,q.y-u.y*span),(q.x+u.x*span,q.y+u.y*span)]).buffer(.025).intersection(inset)
   if not cut.is_empty:
    for tri in constrained_delaunay_triangles(cut).geoms:batch.add([(x,y,height+.552) for x,y in list(tri.exterior.coords)[:-1]],[(0,1,2)],steel)
for idx,r in enumerate(D['buildings']):
 ps=ccw(points(r));h=r['height_estimate_m'];n=r['floors_estimate'];bm=Batch(r['id']+' '+r['name']);kind=r['kind'];profile=r.get('facade_profile','neutral_dorm');wall=rose if profile=='pink_balcony' else brick if profile=='red_academic' else cream
 bm.poly(ps,.12,h,wall);bm.line(ps,.28,.18,.42,brick if profile=='pink_balcony' else ivory,True)
 for a,b in zip(ps,ps[1:]+ps[:1]):
  v=b-a;length=v.length
  if length<3:continue
  t=v.normalized();out=Vector((t.y,-t.x,0));angle=math.atan2(v.y,v.x);target_bay=4.6 if profile=='pink_balcony' else 4.2 if profile in ('red_academic','pale_service') else 3.7;count=max(1,round(length/target_bay));bay=length/count;step=h/n
  balcony=profile=='pink_balcony' and out.y<-.30 and length>12
  for floor in range(n):
   z=.12+floor*step;c=(a+b)/2+out*.08;c.z=z+.08;bm.box(c,(length,.26,.16),ivory,angle)
   if profile=='pink_balcony':c.z=z+step-.22;bm.box(c,(length,.22,.23),brick,angle)
   for j in range(count):
    c=a+t*(bay*(j+.5))+out*.10;c.z=z+step*.54;ww=bay*(.76 if profile=='pale_service' else .69 if profile=='red_academic' else .61);wh=step*(.58 if profile=='red_academic' else .52)
    bm.box(c,(ww+.16,.12,wh+.17),ivory,angle);bm.box(c+out*.075,(ww,.055,wh),glass,angle)
    panes=4 if profile in ('pale_service','red_academic') else 3 if profile=='pink_balcony' else 2
    for k in range(panes+1):bm.box(c+out*.12+t*(-ww/2+k*ww/panes),(.045,.075,wh+.07),ivory,angle)
    top=c+out*.12;top.z+=wh*.22;bm.box(top,(ww,.075,.045),ivory,angle)
    sill=c+out*.15;sill.z-=wh/2+.07;bm.box(sill,(ww+.23,.32,.12),ivory,angle)
    if balcony and floor>0:
     mid=a+t*(bay*(j+.5))+out*.10;w=min(3.0,bay*.78);arc=[mid+t*(w/2*math.cos(k*math.pi/10))+out*(.58*math.sin(k*math.pi/10)) for k in range(11)]
     bm.poly(arc,z+.05,.14,ivory);bm.line(arc,.10,z+.19,.71,rose);bm.line(arc,.14,z+.90,.065,ivory)
  if profile=='red_academic':
   for j in range(count+1):c=a+t*(j*bay)+out*.13;c.z=h/2;bm.box(c,(.16,.25,h),ivory,angle)
  else:
   for j in range(0,count+1,3):c=a+t*min(length,j*bay)+out*.1;c.z=h/2;bm.box(c,(.24,.25,h),ivory,angle)
 bm.line(ps,.43,h,.29,ivory,True);model_roof(bm,ps,r)
 bm.finish(buildcol,{**r,'refinement_version':'source-aligned-campus-1','facade_dimensions_status':'photo/type interpreted, not measured'})
print('Built',len(D['buildings']),'source-profiled buildings',flush=True)
# Import the checked central study in the same geographic frame, including its ground and trees.
OLD=ROOT.parent/'central-campus';STUDY=ROOT.parent/'study';em=json.loads((OLD/'references/satellite-export.json').read_text())['extent'];oldx=em['xmin']+780/1800*(em['xmax']-em['xmin']);oldy=em['ymax']-680/1400*(em['ymax']-em['ymin']);shift=Vector(((oldx-OX)*COS,(oldy-OY)*COS,0))
imported=study_objects;groups={};central_canopies=0
for ob in imported:
 is_building=ob.name.startswith(('B06 Central','B07 Central','B08 Central')) or (ob.parent and ob.parent.name.startswith(('B06 Central','B07 Central','B08 Central')))
 col=buildcol if is_building else treecol if ob.name.startswith(('Observed canopy','Tree trunk','Tree branch','B08 island understory','Forecourt low hedge')) else groundcol
 for previous_collection in list(ob.users_collection):previous_collection.objects.unlink(ob)
 col.objects.link(ob)
 if not ob.parent:ob.location+=shift
 if ob.name.startswith('Observed canopy '):ob.name='Canopy '+str(len(D.get('trees',[]))+central_canopies);ob['origin']='central-study source-positioned canopy';central_canopies+=1
 if ob.type=='EMPTY' and ob.name.startswith(('B06 Central','B07 Central','B08 Central')):groups[ob.name[:3]]=ob
bpy.context.view_layer.update()
for key,parent in groups.items():
 name=parent.name;obs=[o for o in parent.children if o.type=='MESH'];props={k:parent[k] for k in parent.keys()};verts=[];faces=[];material_indices=[];smooth=[];slots=[];slotmap={}
 # Read every transform before mutating the dependency graph; per-object reparenting is quadratic.
 for part in obs:
  matrix=part.matrix_world.copy();offset=len(verts);verts.extend([tuple(matrix@v.co) for v in part.data.vertices]);local=[]
  for material in part.data.materials:
   pointer=material.as_pointer() if material else 0
   if pointer not in slotmap:slotmap[pointer]=len(slots);slots.append(material)
   local.append(slotmap[pointer])
  reverse=matrix.to_3x3().determinant()<0
  for polygon in part.data.polygons:
   ids=list(polygon.vertices);faces.append(tuple(offset+i for i in (reversed(ids) if reverse else ids)));material_indices.append(local[polygon.material_index] if local else 0);smooth.append(polygon.use_smooth)
 me=bpy.data.meshes.new(name+' combined geometry');me.from_pydata(verts,[],faces);me.update()
 for material in slots:me.materials.append(material)
 for face,mi,sm in zip(me.polygons,material_indices,smooth):face.material_index=mi;face.use_smooth=sm
 bpy.data.batch_remove(ids=obs+[parent]);ob=bpy.data.objects.new(name,me);buildcol.objects.link(ob)
 for k,v in props.items():ob[k]=v
 ob['source']='study/campus.blend';ob['source_sha256']=scene['central_study_sha256'];ob['refinement_version']='source-aligned-campus-1';ob['source_component_count']=len(obs)
 print('Combined central group',key,len(obs),'parts',len(verts),'vertices',flush=True)
print('Imported central study:',len(imported),'parts;',central_canopies,'source canopies;',len(groups),'selectable building groups',flush=True)
# The all-campus scene uses a lower leaf density with the same source crown positions.
# Keep the untouched high-detail tree geometry in the independent editable study.
for source_mesh in [m for m in bpy.data.meshes if m.name.startswith('Shared broadleaf crown')]:
 users=[o for o in scene.objects if o.type=='MESH' and o.data==source_mesh];vs=[];fs=[];mis=[]
 for polygon in list(source_mesh.polygons)[::4]:
  coords=[source_mesh.vertices[i].co.copy() for i in polygon.vertices];center=sum(coords,Vector())/len(coords);k=len(vs)
  vs.extend([tuple(center+(v-center)*1.8) for v in coords]);fs.append(tuple(range(k,k+len(coords))));mis.append(polygon.material_index)
 me=bpy.data.meshes.new(source_mesh.name+' campus LOD');me.from_pydata(vs,[],fs);me.update()
 for material in source_mesh.materials:me.materials.append(material)
 for polygon,mi in zip(me.polygons,mis):polygon.material_index=mi
 for ob in users:ob.data=me;ob['vegetation_lod']='quarter leaf count; source crown centre and transform retained'
# Separate visible site plots leave the road and garden boundaries legible.
for r in D['surfaces']:
 ps=points(r);bm=Batch(r['id']);k=r['kind'];m={'ground':grass,'water':water,'paving':pave,'parking':roadmat,'grass':grass2}[k]
 bm.poly(ps,-1.8 if k=='ground' else .06,1.8 if k=='ground' else .05,m)
 if k=='water':bm.line(ps,1.8,.12,.3,pave,True)
 bm.finish(groundcol)
# Inner paved island and grass of the source-visible circular flower-garden water feature.
center=pt((351,1556));bm=Batch('Flower garden circular island')
for radius,z,m in [(16*UNIT,.18,pave),(10*UNIT,.25,grass2)]:
 ps=[center+Vector((radius*math.cos(i*math.tau/64),radius*math.sin(i*math.tau/64),0)) for i in range(64)];bm.poly(ps,z,.05,m)
bm.finish(groundcol)
for name,line,w in D['roads']:
 ps=[pt(p) for p in line];bm=Batch(name);bm.line(ps,w+2,.03,.05,pave);bm.line(ps,w,.085,.06,roadmat)
 if w>14:
  for a,b in zip(ps,ps[1:]):
   v=b-a;steps=max(1,int(v.length/12))
   for j in range(steps):bm.line([a+v*j/steps,a+v*min(1,(j+.4)/steps)],.18,.15,.02,mark)
 bm.finish(groundcol)
for name,line,w in D['north_roads']:
 bm=Batch(name);ps=[pt(p,source='north-extension') for p in line];bm.line(ps,w+2,.03,.05,pave);bm.line(ps,w,.09,.06,roadmat);bm.finish(groundcol)
# Replace overlapping segment boxes with validated union surfaces when baked data is present.
if (ROOT/'roads.json').exists():
 road_data=json.loads((ROOT/'roads.json').read_text())
 for name in road_data['replace_objects']:
  ob=bpy.data.objects.get(name)
  if ob:bpy.data.objects.remove(ob,do_unlink=True)
 for layer in road_data['layers']:
  bm=Batch(layer['name']);bm.add(layer['vertices'],layer['faces'],{'grass':grass,'paving':pave,'asphalt':roadmat,'woodland':woodmat,'curb':curbmat}[layer['material']]);bm.finish(groundcol)
# Keep off-campus streets at their source positions using a thin geographic image context ring.
for layer in road_data.get('context_layers',[]):
 src=layer['source'];meta=NORTH if src=='north-extension' else MAIN;e=meta['extent'];im=bpy.data.images.load(str(ROOT/'references'/(src+'.jpg')),check_existing=True);im.pack()
 material=bpy.data.materials.new(layer['name']);material.use_nodes=True;bs=material.node_tree.nodes.get('Principled BSDF');tex=material.node_tree.nodes.new('ShaderNodeTexImage');tex.image=im;material.node_tree.links.new(tex.outputs['Color'],bs.inputs['Base Color']);bs.inputs['Roughness'].default_value=1;material.node_tree.links.new(tex.outputs['Color'],bs.inputs['Emission Color']);bs.inputs['Emission Strength'].default_value=.15
 me=bpy.data.meshes.new(layer['name']);me.from_pydata(layer['vertices'],[],layer['faces']);me.update();uv=me.uv_layers.new(name='Source geographic UV')
 for polygon in me.polygons:
  for li in polygon.loop_indices:
   v=me.vertices[me.loops[li].vertex_index].co;uv.data[li].uv=((v.x/COS+OX-e['xmin'])/(e['xmax']-e['xmin']),(v.y/COS+OY-e['ymin'])/(e['ymax']-e['ymin']))
 me.materials.append(material);ob=bpy.data.objects.new(layer['name'],me);groundcol.objects.link(ob);ob['source']=src+'.jpg';ob['scope']=layer['scope'];ob['surface_role']='outside-campus source context'
# Athletics geometry fitted to the visible outer extents. Lane and pitch markings are illustrative.
def stadium(center,length,width,angle,source):
 c=pt(center,source=source);scale=UNIT if source=='satellite' else (NORTH['extent']['xmax']-NORTH['extent']['xmin'])/1000*COS;L=length*scale;W=width*scale;ang=math.radians(angle);u=Vector((math.cos(ang),-math.sin(ang),0));v=Vector((math.sin(ang),math.cos(ang),0))
 def p(x,y):return c+u*x+v*y
 def ring(inset=0):
  rad=W/2-inset;half=max(0,(L-W)/2);out=[]
  for cy,start in [(half,0),(-half,math.pi)]:
   for i in range(49):a=start+i*math.pi/48;out.append(p(rad*math.cos(a),cy+rad*math.sin(a)))
  return out
 return p,ring,L,W
for r in D['tracks']:
 p,ring,L,W=stadium(r['center'],r['long'],r['wide'],r['angle'],r.get('source','satellite'));bm=Batch(r['name']);bm.poly(ring(),.11,.04,trackmat)
 inset=min(8.5,W*.115);bm.poly(ring(inset),.16,.04,grass3)
 for j in range(1,8):bm.line(ring(j*inset/8),.10,.22,.025,mark,True)
 fw=W-2*inset-3;fl=L-W+W*.7
 for j in range(12):
  y1=-fl/2+fl*j/12;y2=y1+fl/12;bm.poly([p(-fw/2,y1),p(fw/2,y1),p(fw/2,y2),p(-fw/2,y2)],.215,.01,grass2 if j%2 else grass3)
 bm.line([p(-fw/2,-fl/2),p(fw/2,-fl/2),p(fw/2,fl/2),p(-fw/2,fl/2)],.12,.25,.025,mark,True);bm.line([p(-fw/2,0),p(fw/2,0)],.12,.25,.025,mark)
 circle=[p(9*math.cos(a*math.tau/64),9*math.sin(a*math.tau/64)) for a in range(64)];bm.line(circle,.12,.25,.025,mark,True)
 for end in [-1,1]:
  yy=end*fl/2;bm.line([p(-fw*.29,yy),p(-fw*.29,yy-end*14),p(fw*.29,yy-end*14),p(fw*.29,yy)],.12,.25,.025,mark)
  bm.line([p(-3.65,yy),p(-3.65,yy)],.1,0,.1,mark);a=p(-3.65,yy);b=p(3.65,yy);bm.line([a,b],.12,2.5,.12,mark)
  for q in [a,b]:q.z=1.3;bm.box(q,(.12,.12,2.6),mark)
 bm.finish(sportcol,{'id':r['id'],'name':r['name'],'source':'satellite traced stadium extent; markings interpreted'})
for rec in D['courts']:
 name,cen,w,h,a=rec[:5];src=rec[5] if len(rec)>5 else 'satellite';unit=UNIT if src=='satellite' else (NORTH['extent']['xmax']-NORTH['extent']['xmin'])/1000*COS
 c=pt(cen,source=src);angle=math.radians(-a);u=Vector((math.cos(angle),math.sin(angle),0));v=Vector((-u.y,u.x,0));W=w*unit;H=h*unit;bm=Batch(name)
 def cp(x,y):return c+u*x+v*y
 bm.poly([cp(-W/2,-H/2),cp(W/2,-H/2),cp(W/2,H/2),cp(-W/2,H/2)],.12,.05,trackmat)
 nx=max(1,round(W/16));ny=max(1,round(H/29))
 for ix in range(nx):
  for iy in range(ny):
   x=-W/2+(ix+.5)*W/nx;y=-H/2+(iy+.5)*H/ny;cw=W/nx*.85;ch=H/ny*.90
   ps=[cp(x-cw/2,y-ch/2),cp(x+cw/2,y-ch/2),cp(x+cw/2,y+ch/2),cp(x-cw/2,y+ch/2)];bm.poly(ps,.18,.015,courtmat);bm.line(ps,.10,.21,.02,mark,True);bm.line([cp(x-cw/2,y),cp(x+cw/2,y)],.10,.21,.02,mark)
   for sg in [-1,1]:
    circle=[cp(x+cw*.13*math.cos(k*math.tau/32),y+sg*ch*.25+cw*.13*math.sin(k*math.tau/32)) for k in range(32)];bm.line(circle,.10,.21,.02,mark,True)
 bm.finish(sportcol)
# Shared leaf geometry replaces the previous sphere crowns; centres stay source based.
tree_data=D.get('trees',[]);shared=[]
for seed in range(6):
 rng=random.Random(73+seed);vs=[];fs=[];mis=[]
 for branch in range(24):
  angle=rng.random()*math.tau;radius=rng.uniform(.12,.87);cz=rng.uniform(-.52,.60);center=Vector((math.cos(angle)*radius,math.sin(angle)*radius,cz))
  for j in range(135):
   a=rng.random()*math.tau;rad=rng.random()**.5;pos=center+Vector((math.cos(a)*rad*.42,math.sin(a)*rad*.42,rng.uniform(-.34,.34)));sz=rng.uniform(.04,.075);u=Vector((math.cos(a)*sz,math.sin(a)*sz,sz*.22));v=Vector((-math.sin(a)*sz*.48,math.cos(a)*sz*.48,-sz*.10));k=len(vs);vs.extend([tuple(pos-u),tuple(pos+v),tuple(pos+u),tuple(pos-v)]);fs.append((k,k+1,k+2,k+3));mis.append((seed%3+branch//8+j%2)%6)
 me=bpy.data.meshes.new('Shared campus leaf crown '+str(seed));me.from_pydata(vs,[],fs);me.update()
 for mi in leaves:me.materials.append(M[mi])
 for face,mi in zip(me.polygons,mis):face.material_index=mi
 shared.append(me)
road_data=json.loads((ROOT/'roads.json').read_text());patch=Polygon(road_data['central_patch_world_xy']).buffer(7)
woodpolys=[Polygon([(p.x,p.y) for p in points(r)]) for r in D['surfaces'] if r['id']=='adjacent-woodland']
trunks=Batch('Tree trunks');kept=0
for idx,r in enumerate(tree_data):
 p=pt(r['position'],source=r.get('source','satellite'))
 if patch.covers(Point(p.x,p.y)):continue
 woodland=any(g.covers(Point(p.x,p.y)) for g in woodpolys);h=r['height']*(1.35 if woodland else 1.10);radius=r['radius']*(1.65 if woodland else 1.14)
 trunks.box((p.x,p.y,h*.34),(.22,.22,h*.68),bark);ob=bpy.data.objects.new('Canopy '+str(idx),shared[idx%6]);treecol.objects.link(ob);ob.location=(p.x,p.y,h*.72);ob.scale=(radius,radius,h*.38);ob.rotation_euler.z=(idx*2.3999632297)%math.tau;ob['source']='layout.json green-pixel sample; height/crown/species interpreted';kept+=1
trunks.finish(treecol);scene['source_tree_instances']=kept+central_canopies
print('Vegetation',kept,'full-campus crowns +',central_canopies,'central crowns',flush=True)
# Text markers are viewport metadata, not tall invented architectural gates.
for r in D['gates']:
 p=pt(r['position'],source=r.get('source','satellite'));ob=bpy.data.objects.new(r['id']+' '+r['name'],None);labelcol.objects.link(ob);ob.location=p;ob.empty_display_type='CIRCLE';ob.empty_display_size=7;ob['position_status']='diagram and road opening interpreted';ob.hide_render=True
# Packed georeferenced reference planes, disabled for normal renders.
for name,m,display in [('satellite',MAIN,(1152,1920)),('north-extension',NORTH,(1000,900))]:
 im=bpy.data.images.load(str(ROOT/'references'/(name+'.jpg')),check_existing=True);im.pack();ob=bpy.data.objects.new(name+' reference',None);refcol.objects.link(ob);ob.empty_display_type='IMAGE';ob.data=im;ob.empty_display_size=(m['extent']['xmax']-m['extent']['xmin'])*COS;ob.location=pt((display[0]/2,display[1]/2),-.05,name);ob.hide_render=True;ob.hide_viewport=True
# Orthographic camera, north toward the right, preserving a long rather than rectangular campus.
scene.world.use_nodes=True;bg=scene.world.node_tree.nodes['Background'];bg.inputs['Color'].default_value=(.65,.75,.88,1);bg.inputs['Strength'].default_value=.65
bpy.ops.object.light_add(type='SUN',location=(0,0,1000));sun=bpy.context.object;sun.rotation_euler=(.45,-.55,-.3);sun.data.energy=2.1;sun.data.angle=.15
bpy.ops.object.camera_add();cam=bpy.context.object;cam.name='Campus orthographic camera';cam.data.type='ORTHO';cam.data.clip_end=10000;scene.camera=cam
scene.render.engine='CYCLES';scene.cycles.samples=24 if PREVIEW else 40;scene.cycles.use_denoising=True;scene.render.image_settings.file_format='PNG';scene.render.image_settings.compression=100;scene.view_settings.view_transform='AgX'
scene.render.resolution_percentage=100;scene.render.film_transparent=False
# Camera sees a light paper background while lighting remains independent.
wn=scene.world.node_tree.nodes;wl=scene.world.node_tree.links;paper=wn.new('ShaderNodeBackground');paper.inputs['Color'].default_value=(.78,.82,.77,1);paper.inputs['Strength'].default_value=.85
lp=wn.new('ShaderNodeLightPath');mix=wn.new('ShaderNodeMixShader');wl.new(lp.outputs['Is Camera Ray'],mix.inputs[0]);wl.new(bg.outputs[0],mix.inputs[1]);wl.new(paper.outputs[0],mix.inputs[2]);wl.new(mix.outputs[0],wn.get('World Output').inputs['Surface'])
scene.view_settings.look='AgX - Medium High Contrast'
from bpy_extras.object_utils import world_to_camera_view
bpy.context.view_layer.update()
visible=[o for o in scene.objects if o.type=='MESH' and not o.hide_render]
bounds=[o.matrix_world@Vector(c) for o in visible for c in o.bound_box]
minx=min(p.x for p in bounds);maxx=max(p.x for p in bounds);miny=min(p.y for p in bounds);maxy=max(p.y for p in bounds);target=Vector(((minx+maxx)/2,(miny+maxy)/2,0))
def aim(pos,roll=0):
 cam.location=Vector(pos)+target;q=(target-cam.location).to_track_quat('-Z','Y');cam.rotation_euler=(q@Quaternion((0,0,1),roll)).to_euler();bpy.context.view_layer.update()
def fit_camera():
 cam.data.ortho_scale=100;scene.camera=cam;bpy.context.view_layer.update();inv=cam.matrix_world.inverted();pts=[inv@p for p in bounds];xs=[p.x for p in pts];ys=[p.y for p in pts];aspect=scene.render.resolution_x/scene.render.resolution_y
 # Camera local X/Y centering and fit, with a 5% margin on each side.
 cam.location+=cam.matrix_world.to_3x3()@Vector(((min(xs)+max(xs))/2,(min(ys)+max(ys))/2,0));cam.data.ortho_scale=max(max(xs)-min(xs),(max(ys)-min(ys))*aspect)*1.10;bpy.context.view_layer.update()
scene.render.resolution_x=2600;scene.render.resolution_y=1300
aim((1700,-500,2050));fit_camera()
for screen in bpy.data.screens:
 for a in screen.areas:
  if a.type=='VIEW_3D':a.spaces.active.region_3d.view_perspective='CAMERA';a.spaces.active.shading.color_type='MATERIAL';a.spaces.active.overlay.show_overlays=False
bpy.ops.object.select_all(action='DESELECT');bpy.context.preferences.filepaths.save_version=0
# Discard only unused in-memory datablocks created during this build, before serialization.
bpy.data.orphans_purge(do_local_ids=True,do_linked_ids=True,do_recursive=True)
scene.render.threads_mode='FIXED';scene.render.threads=4
out=Path('/tmp/taihu-full') if PREVIEW or CANDIDATE else ROOT
scene.render.filepath=str(out/'campus.png')
if PREVIEW:
 bpy.ops.wm.save_as_mainfile(filepath=str(out/'campus.blend'),compress=True)
if not PREVIEW:
 bpy.ops.wm.save_as_mainfile(filepath=str(out/'campus.blend'),compress=True)
 bpy.ops.export_scene.gltf(filepath=str(out/'campus.glb'),export_format='GLB',export_cameras=False,export_lights=False,export_extras=True,use_visible=True,export_yup=True,export_draco_mesh_compression_enable=True,export_draco_mesh_compression_level=6,export_draco_position_quantization=16,export_draco_normal_quantization=12)
 finalize_glb_colors(out/'campus.glb')
if PREVIEW and '--scene-only' not in sys.argv:
 print('Rendering preview',scene.render.resolution_x,flush=True);bpy.ops.render.render(write_still=True)
else:
 print('Model exports complete. Run render.py then assemble.py for memory-bounded 8K output.',flush=True)
print('DONE',len(scene.objects),'objects; source tree instances',scene['source_tree_instances'],flush=True)
