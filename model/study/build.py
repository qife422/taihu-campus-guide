"""Central-campus offline presentation study. Existing building footprints retained.
Blender --background -t 4 --python model/study/build.py [-- --preview]
Geometry and ornamental finishes are interpretations, see README.md.
"""
import bpy,bmesh,math,random,json,sys
from pathlib import Path
from mathutils import Vector,Quaternion
sys.path.insert(0,'/tmp/taihu-gis-deps')
from shapely.geometry import Polygon,LineString,Point
from shapely.ops import unary_union
import shapely
ROOT=Path(__file__).resolve().parent; PROJECT=ROOT.parent.parent; OLD=ROOT.parent/'central-campus';CACHE=Path('/tmp/taihu-study');CACHE.mkdir(exist_ok=True)
random.seed(204)
preview='--preview' in sys.argv
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
s=bpy.context.scene;s.unit_settings.system='METRIC';s['status']='Central campus source-based exterior presentation, heights and finish dimensions interpreted'
meta=json.loads((OLD/'references/satellite-export.json').read_text())['extent'];cos=math.cos(math.radians(31.578));unit=(meta['xmax']-meta['xmin'])/1800*cos
s['origin_epsg3857']=str(meta['xmin']+780/1800*(meta['xmax']-meta['xmin']))+','+str(meta['ymax']-680/1400*(meta['ymax']-meta['ymin']));s['metric_scale']=cos
def pt(p,z=0):return Vector(((p[0]-780)*unit,(680-p[1])*unit,z))
def shape(ps):return Polygon([(pt(p).x,pt(p).y) for p in ps])
def mat(name,color,rough=.65,metal=0):
 m=bpy.data.materials.new(name);m.diffuse_color=(*color,1);m.use_nodes=True;p=m.node_tree.nodes.get('Principled BSDF');p.inputs['Base Color'].default_value=(*color,1);p.inputs['Roughness'].default_value=rough;p.inputs['Metallic'].default_value=metal;return m
# One shared world-coordinate anchor lets paving courses and grain remain at metre scale.
anchor=bpy.data.objects.new('Texture metric frame',None);s.collection.objects.link(anchor)
def finish(m,kind,scale=1):
 ns=m.node_tree.nodes;ls=m.node_tree.links;bs=ns.get('Principled BSDF');tc=ns.new('ShaderNodeTexCoord');tc.object=anchor
 tex=ns.new('ShaderNodeTexNoise');tex.inputs['Scale'].default_value=scale;tex.inputs['Detail'].default_value=3;ls.new(tc.outputs['Object'],tex.inputs['Vector'])
 ramp=ns.new('ShaderNodeValToRGB');c=bs.inputs['Base Color'].default_value[:3]
 ramp.color_ramp.elements[0].position=.18;ramp.color_ramp.elements[0].color=(*[x*(.86 if kind=='grass' else .72) for x in c],1);ramp.color_ramp.elements[1].position=.83;ramp.color_ramp.elements[1].color=(*[min(1,x*(1.08 if kind=='grass' else 1.15)) for x in c],1);ls.new(tex.outputs['Fac'],ramp.inputs[0]);ls.new(ramp.outputs[0],bs.inputs['Base Color'])
 bump=ns.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.18;bump.inputs['Distance'].default_value=.025;ls.new(tex.outputs['Fac'],bump.inputs['Height']);ls.new(bump.outputs['Normal'],bs.inputs['Normal'])
 if kind=='paver' or kind=='tile':
  brick=ns.new('ShaderNodeTexBrick');ls.new(tc.outputs['Object'],brick.inputs['Vector']);brick.inputs['Scale'].default_value=1
  brick.inputs['Color1'].default_value=(*c,1);brick.inputs['Color2'].default_value=(*[x*.88 for x in c],1);brick.inputs['Mortar'].default_value=(*[x*.7 for x in c],1);brick.inputs['Mortar Size'].default_value=.012 if kind=='paver' else .007
  brick.inputs['Brick Width'].default_value=.65 if kind=='paver' else .33;brick.inputs['Row Height'].default_value=.40 if kind=='paver' else .22
  ls.new(brick.outputs['Color'],bs.inputs['Base Color']);ls.new(brick.outputs['Fac'],bump.inputs['Height']);bump.inputs['Distance'].default_value=.012
 return m
pave=finish(mat('Honed pale granite paving',(.56,.55,.48)),'paver',12);walk=finish(mat('Warm promenade paving',(.59,.45,.33)),'paver',12);asphalt=finish(mat('Fine asphalt',(.105,.12,.115)),'grain',22);curb=mat('Pale granite curbs',(.70,.68,.58));soil=mat('Planting soil',(.085,.07,.045));grass=finish(mat('Living lawn',(.17,.31,.065)),'grass',.7);hedgemat=finish(mat('Clipped low hedge',(.09,.22,.03)),'grass',8);water=mat('Lake reflective water',(.075,.115,.065),.22,.08);bark=finish(mat('Branch bark',(.15,.09,.042)),'bark',15)
# Low-frequency grass variation comes from the registered source image, mixed with fine procedural grain.
# This does not place an aerial picture beneath buildings or make up unseen map detail.
satellite_image=bpy.data.images.load(str(OLD/'references/satellite.jpg'),check_existing=True);satellite_image.pack()
ns=grass.node_tree.nodes;ls=grass.node_tree.links;bs=ns.get('Principled BSDF');old_input=next(l.from_socket for l in ls if l.to_node==bs and l.to_socket.name=='Base Color')
tc=ns.new('ShaderNodeTexCoord');tc.object=anchor;mul=ns.new('ShaderNodeVectorMath');mul.operation='MULTIPLY';mul.inputs[1].default_value=(1/(1800*unit),1/(1400*unit),0);ls.new(tc.outputs['Object'],mul.inputs[0]);add=ns.new('ShaderNodeVectorMath');add.operation='ADD';add.inputs[1].default_value=(780/1800,1-680/1400,0);ls.new(mul.outputs[0],add.inputs[0]);im=ns.new('ShaderNodeTexImage');im.image=satellite_image;im.extension='EXTEND';ls.new(add.outputs[0],im.inputs['Vector']);bw=ns.new('ShaderNodeRGBToBW');ls.new(im.outputs['Color'],bw.inputs[0]);r=ns.new('ShaderNodeValToRGB');r.color_ramp.elements[0].position=.035;r.color_ramp.elements[0].color=(.105,.205,.043,1);r.color_ramp.elements[1].position=.35;r.color_ramp.elements[1].color=(.28,.37,.12,1);ls.new(bw.outputs[0],r.inputs[0]);mix=ns.new('ShaderNodeMixRGB');mix.blend_type='MIX';mix.inputs[0].default_value=.12;ls.new(old_input,mix.inputs[1]);ls.new(r.outputs[0],mix.inputs[2]);ls.new(mix.outputs[0],bs.inputs['Base Color'])
finish(water,'water',2.3)
water.node_tree.nodes.get('Bump').inputs['Distance'].default_value=.004
# Build directly from fixed central source; no dependency on the derived full-campus scene.
with bpy.data.libraries.load(str(OLD/'central-campus.blend'),link=False) as (src,dst):
 dst.objects=[n for n in src.objects if n.startswith(('B06 ','Canopy radial frame','Canopy curved edge')) and not n.startswith(('B06 south-east','B06 Teaching 6 main','B06 terracotta horizontal band','B06 floor slab edge'))]
parts06=[]
for ob in dst.objects:
 s.collection.objects.link(ob);parts06.append(ob)
# Dedicated facade palette and materials; no photograph is pasted onto geometry.
red06=finish(mat('B06 ceramic red facade',(.39,.075,.045)),'grain',36)
reveal06=finish(mat('B06 recessed warm concrete',(.43,.46,.43)),'grain',32)
frame06=mat('B06 slender anodised frames',(.49,.53,.51),.3,.5)
glass06=mat('B06 recessed glazing',(.085,.13,.15),.16,.12)
glass06.node_tree.nodes.get('Principled BSDF').inputs['IOR'].default_value=1.46
glass06.node_tree.nodes.get('Principled BSDF').inputs['Transmission Weight'].default_value=.08
# Reflection variation applies to a complete window module, never random mesh faces.
glass_variants06=[]
for i,(c,r) in enumerate([((.075,.115,.135),.16),((.10,.145,.16),.20),((.12,.17,.19),.13)]):
 m=glass06.copy();m.name='B06 window reflection '+str(i);bs=m.node_tree.nodes.get('Principled BSDF');bs.inputs['Base Color'].default_value=(*c,1);bs.inputs['Roughness'].default_value=r;glass_variants06.append(m)
roof06=finish(mat('B06 mineral roof membrane',(.29,.29,.25)),'grain',14)
cap06=finish(mat('B06 warm metal roof',(.38,.13,.095),.5),'grain',16)
# Small facade tile joints use facade-oriented coordinates, not horizontal paving mapping.
ns=red06.node_tree.nodes;ls=red06.node_tree.links;bs=ns.get('Principled BSDF');tc=ns.new('ShaderNodeTexCoord');tc.object=anchor
sep=ns.new('ShaderNodeSeparateXYZ');ls.new(tc.outputs['Object'],sep.inputs[0]);comb=ns.new('ShaderNodeCombineXYZ');ls.new(sep.outputs['X'],comb.inputs['X']);ls.new(sep.outputs['Z'],comb.inputs['Y'])
br=ns.new('ShaderNodeTexBrick');br.inputs['Scale'].default_value=1;br.inputs['Brick Width'].default_value=.24;br.inputs['Row Height'].default_value=.065;br.inputs['Mortar Size'].default_value=.0018;br.inputs['Color1'].default_value=(.40,.077,.045,1);br.inputs['Color2'].default_value=(.34,.060,.034,1);br.inputs['Mortar'].default_value=(.23,.054,.035,1)
ls.new(comb.outputs[0],br.inputs['Vector']);ls.new(br.outputs['Color'],bs.inputs['Base Color'])
active_parts=parts06
def archmesh(name,vs,fs,m):
 me=bpy.data.meshes.new(name);me.from_pydata(vs,[],fs);me.update();ob=bpy.data.objects.new(name,me);s.collection.objects.link(ob);me.materials.append(m);active_parts.append(ob);return ob
def archbox(name,loc,size,m,angle=0):
 x,y,z=[v/2 for v in size];vs=[(-x,-y,-z),(x,-y,-z),(x,y,-z),(-x,y,-z),(-x,-y,z),(x,-y,z),(x,y,z),(-x,y,z)]
 ob=archmesh(name,vs,[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)],m);ob.location=loc;ob.rotation_euler.z=angle;return ob
def archextrude(name,g,z,h,m):
 vs=[];fs=[]
 for poly in (g.geoms if hasattr(g,'geoms') else [g]):
  for tr in shapely.constrained_delaunay_triangles(poly).geoms:
   coords=list(tr.exterior.coords)[:-1];k=len(vs);vs.extend([(x,y,z+h) for x,y in coords]);fs.append(tuple(range(k,k+len(coords))))
  for ring in [poly.exterior,*poly.interiors]:
   coords=list(ring.coords)
   for aa,bb in zip(coords,coords[1:]):
    k=len(vs);vs.extend([(aa[0],aa[1],z),(bb[0],bb[1],z),(bb[0],bb[1],z+h),(aa[0],aa[1],z+h)]);fs.append((k,k+1,k+2,k+3))
 return archmesh(name,vs,fs,m)
main06=[(650,907),(778,917),(878,922),(1078,936),(1088,939),(1095,946),(1097,958),(1092,970),(1084,977),(1072,980),(878,971),(778,965),(650,952)]
front06=[(650,952),(778,965),(878,971),(1072,980),(1084,977),(1092,970),(1097,958),(1095,946),(1088,939)]
envelope06=shape(main06);frontline=LineString([(pt(p).x,pt(p).y) for p in front06])
# Recessed core and glazing create real depth behind the photo-visible outer red bands.
core06=envelope06.difference(frontline.buffer(1.10,cap_style='flat'))
archextrude('B06 inset facade core',core06,4.1,22.9,reveal06)
for level in range(8):
 z=4.1+level*3.24
 archextrude('B06 continuous ceramic band '+str(level),frontline.buffer(.37,join_style='mitre',cap_style='flat'),z,1.26 if level<7 else .65,red06)
 archextrude('B06 recessed floor soffit '+str(level),envelope06,z-.16,.16,reveal06)
# Glazing modules are set back 0.92m; narrow mullions and transoms replace white box grids.
for side,(a,b) in enumerate(zip(front06,front06[1:])):
 av,bv=pt(a),pt(b);v=bv-av;length=v.length;tan=v.normalized();inside=Vector((-tan.y,tan.x,0));angle=math.atan2(v.y,v.x);count=max(1,round(length/(3.25 if side<3 else 1.8)));bay=length/count
 for level in range(7):
  z=4.1+level*3.24;mid=z+2.13
  for j in range(count):
   base=av+tan*((j+.5)*bay)+inside*.92;base.z=mid
   archbox('B06 recessed window module',base,(bay-.16,.08,1.74),glass_variants06[(level+j//4+side)%3],angle)
   for dx in [-bay/2+.07,-bay/6,bay/6,bay/2-.07]:
    p=base+tan*dx-inside*.06;archbox('B06 narrow vertical mullion',p,(.048,.08,1.80),frame06,angle)
   for dz in [-.87,.35,.87]:
    p=base-inside*.06;p.z+=dz;archbox('B06 window transom',p,(bay-.12,.08,.05),frame06,angle)
   if side<3 and j%2==0:
    p=av+tan*(j*bay)+inside*.80;p.z=z+2.18;archbox('B06 recessed structural pier',p,(.22,.40,1.86),reveal06,angle)
# Ground-floor enclosure sits behind the retained source columns. Door position is an interpretation.
for side,(a,b) in enumerate(zip(front06[:4],front06[1:4])):
 av,bv=pt(a),pt(b);v=bv-av;tan=v.normalized();inside=Vector((-tan.y,tan.x,0));angle=math.atan2(v.y,v.x);count=max(1,round(v.length/3.2));bay=v.length/count
 for j in range(count):
  p=av+tan*((j+.5)*bay)+inside*2.25;p.z=1.86
  archbox('B06 arcade setback glazing',p,(bay-.10,.12,3.30),glass06,angle)
  for dx in [-bay/2,bay/2]:archbox('B06 arcade door jamb',p+tan*dx-inside*.09,(.10,.14,3.46),frame06,angle)
  q=p-inside*.09;q.z=3.30;archbox('B06 arcade transom',q,(bay,.14,.10),frame06,angle)
  if side==1 and j in [3,4]:
   for dx in [-.12,.12]:
    q=p+tan*dx-inside*.18;q.z=1.15;archbox('B06 entry pull handle',q,(.025,.035,.55),frame06,angle)
# Pale entrance apron/canopy extent is visible immediately south of the central cap.
# Column rhythm and vertical dimensions are interpretations, not a confirmed entrance survey.
entry06=shape([(781,968),(877,974),(877,988),(781,982)])
archextrude('B06 satellite entrance canopy',entry06,3.72,.25,reveal06)
for x in [787,815,843,871]:
 y=982+(x-781)*6/96;p=pt((x,y),1.88);archbox('B06 interpreted entrance pier',p,(.32,.40,3.68),frame06)
for k in range(3):
 g=entry06.buffer((2-k)*.25);archextrude('B06 entry threshold step '+str(k),g,.10+k*.09,.09,reveal06)
# Tall grey end screen beside the curved facade is visible in teach6.jpg.
# Position is fitted within the existing roof end; heights and member sizes are estimates.
a,b=pt((1078,938)),pt((1087,941));v=b-a;ang=math.atan2(v.y,v.x);normal=Vector((-v.y,v.x,0));mid=(a+b)/2
for q in [a,b]:
 q.z=16.3;archbox('B06 photo end-screen upright',q,(.32,.48,25.0),reveal06,ang)
for z in [5.0,8.8,12.0,15.2,18.5,21.7,25.0,28.8]:
 q=mid.copy();q.z=z;archbox('B06 photo end-screen crosspiece',q,(v.length+.35,.48,.24),reveal06,ang)
q=mid+normal*.30;q.z=16.0;archbox('B06 photo end-screen red inset',q,(v.length-.30,.16,23.8),red06,ang)
# Source-visible roof ribs become structural sections, without adding unobserved equipment.
for ob in list(parts06):
 if ob.name.startswith('B06 roof rib'):
  cap=archbox('B06 roof rib cap',ob.location+Vector((0,0,.13)),(ob.dimensions.x,.32,.055),frame06,ob.rotation_euler.z)
# Membrane seams follow the same roof polygon, clipped to avoid drawing outside its traced outline.
roofg=envelope06.difference(shape([(779,916),(878,922),(878,971),(779,965)]).buffer(.2))
for x in range(-45,103,4):
 g=LineString([(x,-100),(x,-65)]).buffer(.02).intersection(roofg)
 if not g.is_empty:archextrude('B06 roof membrane seam',g,27.185,.016,frame06)
# Central raised cap is a warm roof surface in satellite imagery; keep its geometry.
for ob in parts06:
 if ob.name.startswith('B06 central cap slab'):
  ob.data.materials.clear();ob.data.materials.append(cap06)
# A second camera is saved for facade review; the birdseye camera is configured below.
bpy.ops.object.camera_add();detailcam=bpy.context.object;detailcam.name='B06 facade review';detailcam.data.type='ORTHO';detailcam.data.ortho_scale=166
focus=pt((862,941),13);detailcam.location=focus+Vector((65,-180,66));detailcam.rotation_euler=(focus-detailcam.location).to_track_quat('-Z','Y').to_euler()
# Source building parts stay separately editable in Blender under a stable group.
b06=bpy.data.objects.new('B06 Central detailed architecture',None);s.collection.objects.link(b06)
for ob in parts06:ob.parent=b06;ob['source_basis']='teach6.jpg front/curved facade; satellite.jpg roof outlines';ob['dimensions']='interpreted, not measured'
# Other two buildings still use merged source geometry; B06 material assignment is per component.
b06['refinement']='Rebuilt inset window bands, continuous ceramic spandrels, soffits, ground arcade enclosure and roof rib sections; roof perimeter retained'
b06['unverified']='Glazing setback 0.92m, module widths, rear enclosure/door location and component dimensions interpreted; not a measured floor plan'
# Source-specific B07/B08 facades replace the two inherited generic window grids.
# Their body meshes and roof footprints stay at the same source positions.
cream07=finish(mat('B07 pale mineral infill',(.76,.69,.54)),'grain',28)
coral07=finish(mat('B07 terracotta pilasters',(.53,.19,.10)),'grain',32)
white07=mat('B07 limestone cornice',(.86,.83,.72))
window07=mat('B07 bluegrey window',(.105,.18,.19),.22,.18)
roof07=finish(mat('B07 tiled hip roof',(.44,.115,.075)),'tile',16)
pv07=mat('B07 solar cells',(.035,.045,.075),.21,.24)
def facet_frame(a,b,g):
 av,bv=pt(a),pt(b);v=bv-av;tan=v.normalized();n=Vector((-tan.y,tan.x,0));mid=(av+bv)/2
 if g.contains(Point(mid.x+n.x*.3,mid.y+n.y*.3)):n=-n
 return av,bv,tan,n,math.atan2(v.y,v.x)
def oriented_piece(name,a,b,z,h,depth,m,offset=0):
 av,bv=Vector(a),Vector(b);v=bv-av;v.z=0;tan=v.normalized();n=Vector((-tan.y,tan.x,0));p=(av+bv)/2+n*offset;p.z=z+h/2
 return archbox(name,p,(v.length,depth,h),m,math.atan2(v.y,v.x))
def framed_window(name,p,angle,w,h,m,frame,pane_count=4):
 archbox(name+' glass',p,(w,.07,h),m,angle);tan=Vector((math.cos(angle),math.sin(angle),0))
 # Face-depth chosen by caller; window frame is a small physical profile.
 for j in range(pane_count+1):
  archbox(name+' mullion',p+tan*(-w/2+j*w/pane_count),(.05,.14,h+.08),frame,angle)
 for dz in [-h/2,h*.20,h/2]:
  q=p.copy();q.z+=dz;archbox(name+' transom',q,(w+.08,.14,.055),frame,angle)
parts07=[];active_parts=parts07
with bpy.data.libraries.load(str(OLD/'central-campus.blend'),link=False) as (src,dst):
 dst.objects=[n for n in src.objects if n in ['B07 west courtyard wings','B07 north wing'] or n.startswith(('B07 north tiled roof','B07 south tiled roof','B07 west tiled roof','B07 east tiled roof','B07 visible roof housing'))]
for ob in dst.objects:
 s.collection.objects.link(ob);parts07.append(ob)
 if ob.name in ['B07 west courtyard wings','B07 north wing']:ob.data.materials.clear();ob.data.materials.append(coral07)
 if 'tiled roof' in ob.name:ob.data.materials.clear();ob.data.materials.append(roof07)
 if ob.name.startswith('B07 visible roof housing'):
  ob.data.materials.clear();ob.data.materials.append(coral07);ob.data.materials.append(white07)
  for f in ob.data.polygons:f.material_index=1 if f.normal.z>.5 else 0
u07=[(381,248),(426,254),(423,339),(630,356),(637,286),(687,290),(683,420),(379,390)]
n07=[(387,161),(697,196),(693,248),(380,213)]
for wing,ps in [('courtyard',u07),('north',n07)]:
 g=shape(ps)
 # A stone base and two strong cornice lines are visible in the aerial photograph.
 for z,h,w in [(.12,.48,.18),(2.45,.25,.34),(18.65,.28,.34),(20.40,.28,.48)]:
  archextrude('B07 '+wing+' continuous cornice',g.buffer(w).difference(g.buffer(-.04)),z,h,white07)
 for side,(a,b) in enumerate(zip(ps,ps[1:]+ps[:1])):
  av,bv,tan,out,ang=facet_frame(a,b,g);length=(bv-av).length;count=max(1,round(length/3.15));bay=length/count
  # Pale panels between red full-height pilasters are characteristic of this building.
  for j in range(count):
   p=av+tan*(bay*(j+.5))+out*.06;p.z=10.6
   archbox('B07 '+wing+' pale infill panel',p,(bay-.28,.10,15.7),cream07,ang)
   for z,h in [(1.28,.72),(4.0,1.25),(7.1,1.25),(10.2,1.25),(13.3,1.25),(16.4,1.25),(19.55,.72)]:
    q=av+tan*(bay*(j+.5))+out*.17;q.z=z
    framed_window('B07 '+wing+' grouped window',q,ang,bay*.66,h,window07,white07,4)
  for j in range(count+1):
   p=av+tan*(bay*j)+out*.17;p.z=10.6;archbox('B07 '+wing+' red vertical pilaster',p,(.24,.24,16.0),coral07,ang)
   q=p+tan*.17+out*.03;archbox('B07 '+wing+' pilaster light edge',q,(.065,.12,15.8),white07,ang)
# Twin triangular roof gables on each long southern-facing elevation, visible in the photograph.
for label,a,b in [('south',(379,390),(683,420)),('north',(380,213),(693,248))]:
 av,bv=pt(a),pt(b);v=bv-av;tan=v.normalized();inside=Vector((-tan.y,tan.x,0));ang=math.atan2(v.y,v.x)
 for ratio in [.36,.65]:
  c=av+v*ratio;left=c-tan*3.45;right=c+tan*3.45;peak=c.copy();peak.z=22.70;left.z=20.5;right.z=20.5
  archmesh('B07 '+label+' photo gable face',[tuple(left),tuple(right),tuple(peak)],[(0,1,2)],coral07)
  rear=peak+inside*5.5;rear.z=23.12;lr=left+inside*5.5;rr=right+inside*5.5
  archmesh('B07 '+label+' cross gable roof',[tuple(left),tuple(peak),tuple(right),tuple(lr),tuple(rear),tuple(rr)],[(0,3,4,1),(1,4,5,2)],roof07)
  for q1,q2 in [(left,peak),(peak,right)]:
   # Trim is a three-dimensional beam following each diagonal, not a painted triangle.
   vv=q2-q1;ob=archbox('B07 '+label+' gable rake',(q1+q2)/2,(.32,.40,vv.length),white07);ob.rotation_euler=vv.to_track_quat('Z','Y').to_euler()
# Recreate observed PV groups on sloping roof surfaces; module partition counts are estimates.
for x,y,w in [(407,192,28),(496,203,37),(590,213,50),(443,374,30),(502,380,28),(588,388,46),(666,311,14)]:
 def pvpoint(xx,yy):
  if y<250:dist=(yy-(188+(xx-391)*34/299))*unit
  elif y>350:dist=(yy-(365+(xx-397)*24/266))*unit
  else:dist=(xx-(662+(yy-295)*(-2)/95))*unit
  return pt((xx,yy),23.1-abs(dist)*.30+.25)
 n=max(1,round(w*unit/1.15))
 for j in range(n):
  for row in range(2):
   xx=x+j*w/n;yy=y+row*6;coords=[pvpoint(xx,yy),pvpoint(xx+w/n-.35,yy),pvpoint(xx+w/n-.35,yy+5.65),pvpoint(xx,yy+5.65)]
   archmesh('B07 sloped PV module',[tuple(q) for q in coords],[(0,1,2,3)],pv07)
   for q1,q2 in zip(coords,coords[1:]+coords[:1]):
    vv=q2-q1;ob=archbox('B07 solar perimeter frame',(q1+q2)/2,(.045,.045,vv.length),white07);ob.rotation_euler=vv.to_track_quat('Z','Y').to_euler()
b07=bpy.data.objects.new('B07 Central detailed architecture',None);s.collection.objects.link(b07)
for ob in parts07:ob.parent=b07
b07['source_basis']='campus-aerial.jpg: pale infill, red pilasters, grouped windows, twin gables and sloped PV; satellite.jpg: preserved body footprint'
b07['unverified']='Dimensions, module count and gable offsets interpreted; B07 is a working identifier, not a verified official building number'
# B08: retain the traced high bar and low courtyard; use their distinct facade rhythm.
parts08=[];active_parts=parts08
names08=['B08 north academic bar','B08 lakeside courtyard wings']
with bpy.data.libraries.load(str(OLD/'central-campus.blend'),link=False) as (src,dst):
 dst.objects=[n for n in src.objects if n in names08 or n.startswith(('B08 bridge','B08 glazed roof segment','B08 roof glazing frame')) or any(n.startswith(q+' slab') or (n.startswith(q) and n[len(q):len(q)+1].isdigit()) for q in names08)]
white08=finish(mat('B08 offwhite facade panels',(.77,.77,.70)),'grain',30)
red08=finish(mat('B08 salmon spandrel',(.58,.235,.14)),'grain',32)
glass08=mat('B08 grouped glass',(.11,.18,.20),.23,.15)
metal08=finish(mat('B08 standing seam roof',(.48,.50,.46)),'grain',11)
frame08=mat('B08 light window frames',(.80,.83,.79),.35,.20)
for ob in dst.objects:
 s.collection.objects.link(ob);parts08.append(ob)
 if ob.name in names08:ob.data.materials.clear();ob.data.materials.append(white08)
 if ob.name.endswith('slab'):ob.data.materials.clear();ob.data.materials.append(metal08)
bar08=[(838,280),(1218,301),(1219,352),(838,335)]
low08=[(845,424),(1086,441),(1084,547),(1154,551),(1158,384),(1216,386),(1210,619),(1040,611),(1040,483),(846,478)]
for label,ps,height,levels,baywidth in [('bar',bar08,23.1,7,6.15),('lakeside',low08,13.2,4,5.10)]:
 g=shape(ps)
 for level in range(levels):
  z=.24+level*3.25
  archextrude('B08 '+label+' continuous slab edge',g.buffer(.20).difference(g.buffer(-.02)),z,.22,white08)
 for side,(a,b) in enumerate(zip(ps,ps[1:]+ps[:1])):
  av,bv,tan,out,ang=facet_frame(a,b,g);length=(bv-av).length;count=max(1,round(length/baywidth));bay=length/count
  for j in range(count):
   for level in range(levels):
    z=.24+level*3.25;p=av+tan*(j+.5)*bay+out*.06;p.z=z+.61
    archbox('B08 '+label+' salmon spandrel',p,(bay-.30,.12,.76),red08,ang)
    p=av+tan*(j+.5)*bay+out*.16;p.z=z+1.98
    framed_window('B08 '+label+' grouped classroom window',p,ang,bay*.82,1.62,glass08,frame08,5)
   p=av+tan*j*bay+out*.24;p.z=height/2;archbox('B08 '+label+' full-height pier',p,(.22,.32,height),white08,ang)
 # Raised metal seams and cross joints follow the roof's long-axis direction.
 theta=math.atan2((pt(ps[1])-pt(ps[0])).y,(pt(ps[1])-pt(ps[0])).x);along=Vector((math.cos(theta),math.sin(theta),0));across=Vector((-along.y,along.x,0));c=Vector((g.centroid.x,g.centroid.y,0));diag=math.hypot(g.bounds[2]-g.bounds[0],g.bounds[3]-g.bounds[1])
 for k in range(-int(diag/.7),int(diag/.7)+1):
  q=c+across*k*.7;aa=q-along*diag;bb=q+along*diag;cut=LineString([(aa.x,aa.y),(bb.x,bb.y)]).buffer(.025).intersection(g.buffer(-.35))
  if not cut.is_empty:archextrude('B08 '+label+' raised roof seam',cut,height+.27,.04,frame08)
 for k in range(-int(diag/6),int(diag/6)+1):
  q=c+along*k*6;aa=q-across*diag;bb=q+across*diag;cut=LineString([(aa.x,aa.y),(bb.x,bb.y)]).buffer(.018).intersection(g.buffer(-.35))
  if not cut.is_empty:archextrude('B08 '+label+' roof transverse joint',cut,height+.27,.035,metal08)
# Two small grille-like roof fixtures are visible in the north-bar satellite roof.
# Footprint locations are traced; grille height and exact bar count are estimates.
for x,y,w,d in [(948,291,8,14),(1100,313,14,8)]:
 p=pt((x,y),23.65);archbox('B08 observed rooftop grille housing',p,(w*unit,d*unit,.50),white08)
 for axis,count in [('x',4),('y',5)]:
  for j in range(count):
   q=p.copy();q.z=23.94
   if axis=='x':q.x+=(j/(count-1)-.5)*w*unit;size=(.045,d*unit,.045)
   else:q.y+=(j/(count-1)-.5)*d*unit;size=(w*unit,.045,.045)
   archbox('B08 observed rooftop grille bars',q,size,frame08)
b08=bpy.data.objects.new('B08 Central detailed architecture',None);s.collection.objects.link(b08)
for ob in parts08:ob.parent=b08
b08['source_basis']='campus-aerial.jpg: grouped classroom windows, pale piers, salmon spandrels and seamed metal roofs; original traced bar/courtyard envelopes retained'
b08['unverified']='Corner and rear elevation details remain simplified; dimensions and window partitions interpreted; working identifier only'
active_parts=[]
for m in list(bpy.data.materials):
 if not m.use_nodes:continue
 p=m.node_tree.nodes.get('Principled BSDF')
 if not p:continue
 n=m.name.split(".")[0]
 if n=='Photo observed terracotta bands':p.inputs['Base Color'].default_value=(.56,.14,.072,1);finish(m,'grain',28)
 elif n=='Warm mineral facade':p.inputs['Base Color'].default_value=(.79,.76,.65,1);finish(m,'grain',35)
 elif n=='Pale facade frame':p.inputs['Base Color'].default_value=(.88,.85,.74,1)
 elif n=='Weathered flat roof':p.inputs['Base Color'].default_value=(.27,.30,.28,1);finish(m,'paver',12)
 elif n=='Red tiled roof':p.inputs['Base Color'].default_value=(.43,.10,.055,1);finish(m,'tile',14)
 elif n=='Photo observed solar array':p.inputs['Base Color'].default_value=(.025,.065,.10,1);p.inputs['Roughness'].default_value=.18

def mesh(name,vs,fs,m):
 me=bpy.data.meshes.new(name);me.from_pydata(vs,[],fs);me.update();ob=bpy.data.objects.new(name,me);s.collection.objects.link(ob);ob.data.materials.append(m);return ob
def surface(name,g,z,m):
 if g.is_empty:return
 tris=shapely.constrained_delaunay_triangles(g);vs=[];fs=[]
 for t in tris.geoms:
  coords=list(t.exterior.coords)[:-1];k=len(vs);vs += [(x,y,z) for x,y in coords];fs.append(tuple(range(k,k+len(coords))))
 return mesh(name,vs,fs,m)
def ribbon(name,ps,width,z,m):
 g=LineString([(pt(p).x,pt(p).y) for p in ps]).buffer(width/2,join_style='round');return surface(name,g,z,m)
def line3(name,coords,r,m):
 cu=bpy.data.curves.new(name,'CURVE');cu.dimensions='3D';cu.resolution_u=1;cu.bevel_depth=r;cu.bevel_resolution=1;sp=cu.splines.new('POLY');sp.points.add(len(coords)-1)
 for v,p in zip(sp.points,coords):v.co=(*p,1)
 ob=bpy.data.objects.new(name,cu);s.collection.objects.link(ob);ob.data.materials.append(m);return ob
# Digitized hardscape and planted polygons from the same 1800x1400 source.
bound=shape([(280,140),(1260,140),(1260,720),(1200,1030),(1100,1190),(280,1190)])
roads=[([(335,120),(337,401),(315,703),(281,1100),(285,1190)],10), ([(753,120),(758,418),(803,460)],7), ([(1240,120),(1242,610),(1225,771),(1170,1060),(1108,1140),(804,1150),(282,1112)],10), ([(347,440),(578,446),(691,440),(757,430)],5)]
road=unary_union([LineString([(pt(p).x,pt(p).y) for p in ps]).buffer(w/2,join_style='round',cap_style='flat') for ps,w in roads]).intersection(bound);surface('Observed roads',road,.05,asphalt)
for i,g in enumerate(road.geoms if hasattr(road,'geoms') else [road]):
 surface('Road edge '+str(i),g.buffer(.26).difference(g),.12,curb)
paving=unary_union([shape(p) for p in [[(354,149),(730,172),(733,425),(698,448),(345,423)],[(790,234),(1242,255),(1225,658),(1090,752),(969,733),(986,556),(803,471)],[(588,789),(800,772),(967,737),(1180,725),(1140,991),(580,986)],[(576,984),(1130,982),(1095,1120),(568,1113)],[(310,905),(572,918),(557,1182),(289,1174)]]])
F=json.loads((OLD/'footprints.json').read_text())['features'];lake=shape(F[0]['pixel_outline'])
lawns=[shape(p) for p in [[(352,453),(579,445),(624,469),(623,514),(590,602),(569,737),(540,785),(538,871),(500,905),(308,885)],[(435,252),(615,273),(613,337),(434,324)],[(724,183),(760,184),(771,417),(740,435),(713,414)],[(842,351),(914,354),(915,417),(840,414)],[(953,355),(1139,367),(1140,430),(954,425)],[(881,485),(1027,494),(1025,550),(945,548)],[(609,1015),(738,1021),(733,1090),(604,1086)],[(935,1031),(1075,1036),(1067,1106),(938,1101)]]]
# The planted island between B08 and the northeast lake bank is visible in both sources.
island=shape([(767,478),(800,478),(840,489),(887,506),(936,516),(944,539),(914,546),(858,542),(819,535),(788,520),(771,507)])
island=island.difference(lake.buffer(4.6))
lawns.insert(-2,island)
paved=paving.difference(unary_union(lawns)).difference(lake.buffer(4.5));surface('Unified granite forecourts',paved,.10,pave)
base=bound.difference(paving.union(road)).difference(lake.buffer(4.5));surface('Outer lawns',base,0,grass)
for i,g in enumerate(lawns):surface('Traced garden lawn '+str(i),g,.12,grass);surface('Garden stone edge '+str(i),g.buffer(.20).difference(g),.15,curb)
# A clipped planting edge and uneven soil cover preserve the observed island extent.
surface('B08 shore island soil margin',island.difference(island.buffer(-.65)),.145,soil)
# Granite border courses and expansion joints: finish dimensions are interpreted.
# Lines are clipped against the actual paved surface, never drawn across lawns or water.
joint=mat('Granite expansion joints',(.32,.33,.30))
for x in range(-80,141,6):
 cut=LineString([(x,-160),(x,170)]).buffer(.025).intersection(paved)
 surface('Forecourt paving joint',cut,.112,joint)
for y in range(-156,141,6):
 cut=LineString([(-180,y),(180,y)]).buffer(.025).intersection(paved)
 surface('Forecourt paving joint',cut,.113,joint)
surface('Forecourt border course',paved.difference(paved.buffer(-.38)),.116,curb)
# Photo-supported earth margins around lawn edges provide a planted transition.
for i,g in enumerate(lawns[-2:]):
 surface('Forecourt planting earth '+str(i),g.difference(g.buffer(-.8)),.14,soil)
# Bank ring stays outside the measured water outline; width/heights are visual estimates.
surface('Lake water',lake,-1.25,water)
# The aerial photograph shows a terraced bank, not a single flat outline.
# Vertical values are interpreted; the traced water polygon is unchanged.
for i in range(6):
 a=.20+i*.45;b=a+.45;z=-.95+i*.18
 surface('Lake stone tread '+str(i),lake.buffer(b).difference(lake.buffer(a)),z,curb)
 ring=list(lake.buffer(a).exterior.coords)
 mesh('Lake stone riser '+str(i),[(x,y,h) for x,y in ring for h in [z-.18,z]],[(2*j,2*j+1,2*j+3,2*j+2) for j in range(len(ring)-1)],curb)
surface('Lake warm promenade',lake.buffer(4.5).difference(lake.buffer(2.90)),.05,walk)
ring=list(lake.buffer(.20).exterior.coords)
mesh('Lake retaining face',[(x,y,z) for x,y in ring for z in [-1.30,-.95]],[(2*i,2*i+1,2*i+3,2*i+2) for i in range(len(ring)-1)],curb)
railpoly=lake.buffer(2.95);railcoords=list(railpoly.exterior.coords);railm=mat('Bank brushed rail',(.59,.60,.51),.35,.45)
for z in [.57,.99]:line3('Shore continuous rail',[(x,y,z) for x,y in railcoords],.032,railm)
for i in range(int(railpoly.exterior.length/1.8)):
 p=railpoly.exterior.interpolate(i*1.8);line3('Shore rail upright',[(p.x,p.y,.05),(p.x,p.y,.99)],.032,railm)
# Pavement parking paint is retained only in the visible western parking area.
paint=mat('Parking line paint',(.86,.83,.68))
for yy in [929,961,1025,1063,1134,1165]:
 for xx in range(320,542,18):ribbon('Parking stall',[(xx,yy),(xx,yy+25)],.09,.115,paint)
# Visible semicircular forecourt basin: original central source pixels, no sculpture added.
basinpts=[pt((833+48*math.cos(math.pi+i*math.pi/48),1110+48*math.sin(math.pi+i*math.pi/48)),.16) for i in range(49)]
line3('Source-visible entrance basin rim',[tuple(p) for p in basinpts],.42,curb)
# Stationary vehicles are illustrative scale references at visible parking rows, not live parking data.
carpaint=[mat('Parked vehicle '+str(i),c,.3,.35) for i,c in enumerate([(.70,.72,.68),(.12,.15,.17),(.29,.34,.37),(.48,.16,.10)])]
carwindow=mat('Vehicle glass',(.035,.07,.08),.2,.3)
def vehiclebox(name,loc,size,m):
 x,y,z=[v/2 for v in size];v=[(-x,-y,-z),(x,-y,-z),(x,y,-z),(-x,y,-z),(-x,-y,z),(x,-y,z),(x,y,z),(-x,y,z)];ob=mesh(name,v,[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)],m);ob.location=loc
 mod=ob.modifiers.new('Rounded panels','BEVEL');mod.width=.18;mod.segments=3;return ob
for i,(x,y) in enumerate([(335,934),(373,934),(409,934),(464,934),(518,934),(335,1030),(390,1030),(427,1030),(500,1030),(335,1138),(371,1138),(408,1138),(481,1138),(518,1138)]):
 vehiclebox('Parked car body',pt((x,y),.65),(1.8,4.2,.82),carpaint[i%4]);vehiclebox('Parked car glazing',pt((x,y-1),1.21),(1.57,2.20,.60),carwindow);vehiclebox('Parked car roof',pt((x,y-1),1.54),(1.45,1.55,.09),carpaint[i%4])
for i in range(9):ribbon('Observed south crossing',[(798+i*7,1136),(798+i*7,1161)],.43,.075,paint)
print('Architecture, unified ground and shoreline ready',flush=True)
# Organic branch-and-leaf prototypes. Tree centres follow observed canopy clusters.
leafm=[mat('Leaf tone '+str(i),c,.82) for i,c in enumerate([(.085,.18,.035),(.14,.25,.055),(.20,.31,.075),(.075,.18,.055),(.24,.30,.09)])]
def tree_mesh(seed):
 rng=random.Random(seed);vs=[];fs=[];mi=[]
 # Leaves are small crossed tapered blades, grouped into asymmetric branch clusters.
 for branch in range(40):
  angle=rng.random()*math.tau;radius=rng.uniform(.15,.92);cz=rng.uniform(-.55,.65);cl=Vector((math.cos(angle)*radius,math.sin(angle)*radius,cz))
  for j in range(650):
   a=rng.random()*math.tau;u=rng.random()**(1/3);p=cl+Vector((math.cos(a)*u*.36,math.sin(a)*u*.36,rng.uniform(-.28,.28)));size=rng.uniform(.026,.043);d=Vector((math.cos(a)*size,math.sin(a)*size,size*.25));cross=Vector((-math.sin(a)*size*.45,math.cos(a)*size*.45,-size*.1));k=len(vs)
   vs += [tuple(p-d),tuple(p+cross),tuple(p+d),tuple(p-cross)];fs += [(k,k+1,k+2,k+3)];mi.append((seed%3+branch//10+rng.randrange(2))%5)
 me=bpy.data.meshes.new('Shared broadleaf crown '+str(seed));me.from_pydata(vs,[],fs);me.update()
 for m in leafm:me.materials.append(m)
 for f,i in zip(me.polygons,mi):f.material_index=i
 return me
prototypes=[tree_mesh(i) for i in range(6)]
treepoints=[(578,800),(598,806),(638,793),(736,805),(765,810),(1100,739),(1134,748),(1175,725),(1190,667),(1203,601),(986,632),(988,685),(990,712),(966,773),(773,487),(808,490),(842,500),(879,510),(917,528),(939,783),(934,811),(710,1001),(676,994),(1001,1007),(1053,1005),(1126,953),(1138,904),(1143,853),(618,962),(592,965),(609,889),(1140,566),(1130,627),(357,394),(360,324),(370,220),(728,264),(725,347),(732,397),(788,393),(800,456),(694,445),(626,448),(559,454),(519,457),(707,1138),(745,1140),(790,1143),(851,1145),(900,1148),(939,1148),(986,1147),(1021,1146)]
# Visible dense tree belts at the northern and southern limits of the study.
for a,b in [((370,132),(722,159)),((704,1140),(1080,1140))]:
 length=(pt(b)-pt(a)).length
 for i in range(int(length/3.5)):
  t=i/max(1,int(length/3.5)-1);treepoints.append((a[0]+(b[0]-a[0])*t+random.uniform(-5,5),a[1]+(b[1]-a[1])*t+random.uniform(-8,8)))
for idx,p in enumerate(treepoints):
 h=random.uniform(8.5,12.0);r=random.uniform(4.1,5.5);v=pt(p,h*.77)
 ob=bpy.data.objects.new('Observed canopy '+str(idx),prototypes[idx%6]);s.collection.objects.link(ob);ob.location=v;ob.scale=(r,r,r*1.05);ob.rotation_euler.z=random.random()*math.tau
 root=pt(p,.12);top=pt(p,h*.80);line3('Tree trunk '+str(idx),[root,top],.13,bark)
 for b in range(5):
  angle=b*math.tau/5+idx;end=v+Vector((math.cos(angle)*r*.7,math.sin(angle)*r*.7,r*.25));line3('Tree branch',[(root.x,root.y,h*.44),end],.05,bark)
# Small understory clumps sit within the photographed planting island, not on paving.
hedge_line=island.buffer(-.60).boundary
for idx in range(int(hedge_line.length/1.3)):
 p=hedge_line.interpolate(idx*1.3);ob=bpy.data.objects.new('B08 island understory',prototypes[idx%6]);s.collection.objects.link(ob);ob.location=(p.x,p.y,.42);ob.scale=(.55,.55,.35)
# Shared low-hedge mesh avoids repeated UI operators and keeps Blender editing responsive.
hedge_mesh=bpy.data.meshes.new('Shared clipped hedge');bm=bmesh.new();bmesh.ops.create_icosphere(bm,subdivisions=1,radius=.42);bm.to_mesh(hedge_mesh);bm.free();hedge_mesh.materials.append(hedgemat)
for g in lawns[-2:]:
 h=g.buffer(-.5).boundary
 for i in range(int(h.length/.55)):
  p=h.interpolate(i*.55);ob=bpy.data.objects.new('Forecourt low hedge',hedge_mesh);s.collection.objects.link(ob);ob.location=(p.x,p.y,.48);ob.scale.z=.72
print('Vegetation ready',len(treepoints),'canopies',flush=True)
# Bright, directionally lit architectural rendering with soft contact shadows.
s.render.engine='CYCLES';s.cycles.samples=20 if preview else 56;s.cycles.use_denoising=True;s.cycles.max_bounces=6;s.render.threads_mode='FIXED';s.render.threads=4
s.world.use_nodes=True;wn=s.world.node_tree.nodes;wl=s.world.node_tree.links;wn.clear()
bg=wn.new('ShaderNodeBackground');bg.inputs['Color'].default_value=(.65,.75,.88,1);bg.inputs['Strength'].default_value=.65
# A sky-to-horizon gradient lights and reflects in the glazing; background framing stays neutral.
coord=wn.new('ShaderNodeTexCoord');sep=wn.new('ShaderNodeSeparateXYZ');wl.new(coord.outputs['Normal'],sep.inputs[0])
mapper=wn.new('ShaderNodeMapRange');mapper.inputs['From Min'].default_value=-1;mapper.inputs['From Max'].default_value=1;wl.new(sep.outputs['Z'],mapper.inputs['Value'])
sky=wn.new('ShaderNodeValToRGB');sky.color_ramp.elements[0].position=0;sky.color_ramp.elements[0].color=(.24,.28,.21,1);sky.color_ramp.elements[1].position=1;sky.color_ramp.elements[1].color=(.40,.61,.86,1)
e=sky.color_ramp.elements.new(.5);e.color=(.82,.85,.82,1);wl.new(mapper.outputs['Result'],sky.inputs['Fac']);wl.new(sky.outputs['Color'],bg.inputs['Color'])
paper=wn.new('ShaderNodeBackground');paper.inputs['Color'].default_value=(.68,.74,.69,1);paper.inputs['Strength'].default_value=.7
rays=wn.new('ShaderNodeLightPath');mix=wn.new('ShaderNodeMixShader');wl.new(rays.outputs['Is Camera Ray'],mix.inputs[0]);wl.new(bg.outputs[0],mix.inputs[1]);wl.new(paper.outputs[0],mix.inputs[2]);out=wn.new('ShaderNodeOutputWorld');wl.new(mix.outputs[0],out.inputs[0])
bpy.ops.object.light_add(type='SUN',location=(100,-120,200));sun=bpy.context.object;sun.rotation_euler=(.45,-.35,-.20);sun.data.energy=2.1;sun.data.angle=.10
bpy.ops.object.camera_add();cam=bpy.context.object;cam.name='Central architectural birdseye';cam.data.type='ORTHO';cam.data.ortho_scale=410;cam.data.clip_end=2000;target=pt((783,635),7);cam.location=target+Vector((110,-240,300));cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler();s.camera=cam
s.render.resolution_x=1800 if preview else 4000;s.render.resolution_y=1440 if preview else 3200;s.render.resolution_percentage=100;s.render.image_settings.file_format='PNG';s.render.image_settings.compression=65;s.render.film_transparent=False;s.view_settings.view_transform='AgX';s.view_settings.look='AgX - Medium High Contrast';s.view_settings.exposure=0
for screen in bpy.data.screens:
 for area in screen.areas:
  if area.type=='VIEW_3D':area.spaces.active.region_3d.view_perspective='CAMERA';area.spaces.active.overlay.show_overlays=False
bpy.context.preferences.filepaths.save_version=0
s.render.filepath=str((CACHE if preview else ROOT)/'campus.png')
bpy.ops.wm.save_as_mainfile(filepath=str((CACHE if preview else ROOT)/'campus.blend'),compress=True)
if '--scene-only' not in sys.argv:
 print('RENDER',s.render.filepath,flush=True);bpy.ops.render.render(write_still=True)
print('DONE',flush=True)
