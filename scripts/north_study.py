"""Bounded north-block visual study. Retained scene and full atlas remain unchanged.
Blender --background -t 4 --python scripts/north_study.py [-- --final]
Four overlapping tiles reuse the shared cache; the exporter assembles in memory.
"""
from pathlib import Path
import sys,json,hashlib,math,io
ROOT=Path(__file__).resolve().parents[1]; CACHE=Path('/tmp/taihu-full'); OUT=ROOT/'public/assets'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def size(p):return p.stat().st_size if p.exists() else 0
def capacity():return sum(p.stat().st_size for p in CACHE.rglob('*') if p.is_file())
def rotation(e):
 import numpy as np
 x,y,z=e;sx,cx=math.sin(x),math.cos(x);sy,cy=math.sin(y),math.cos(y);sz,cz=math.sin(z),math.cos(z)
 return np.array([[cz,-sz,0],[sz,cz,0],[0,0,1]])@np.array([[cy,0,sy],[0,1,0],[-sy,0,cy]])@np.array([[1,0,0],[0,cx,-sx],[0,sx,cx]])
if '--stream' in sys.argv:
 import numpy as np
 from PIL import Image, ImageEnhance
 sys.path.insert(0,'/tmp/taihu-gis-deps')
 from shapely.geometry import Polygon
 from shapely.ops import unary_union
 meta=json.loads((CACHE/'atlas.json').read_text());tiles=[];seen=set();area=0
 for line in sys.stdin:
  cmd=json.loads(line);act=cmd['action']
  if act=='begin':canvas=Image.new('RGB',(meta['width'],meta['height']))
  elif act=='tile':
   im=Image.open(CACHE/'render-tile.png').convert('RGB');a,b,c,d=cmd['bounds'];x0,y0,x1,y1=cmd['core'];assert im.size==(c-a,d-b)
   assert tuple(cmd['core']) not in seen;seen.add(tuple(cmd['core']));area+=(x1-x0)*(y1-y0);canvas.paste(im.crop((x0-a,y0-b,x1-a,y1-b)),(x0,y0));tiles.append({**cmd,'sha256':sha(CACHE/'render-tile.png')});im.close()
  elif act=='finish':
   assert len(tiles)==4 and area==canvas.width*canvas.height
   w,h=canvas.size;rot=rotation(meta['camera']['rotation_euler']);pos=np.array(meta['camera']['position']);ppm=w/meta['camera']['ortho_scale'];errors=[]
   for rec in meta['records']:
    faces=meta['roof_faces_world'][rec['id']];parts=[]
    for f in faces:
     pp=(np.array(f)-pos)@rot;p=Polygon([(w/2+q[0]*ppm,h/2-q[1]*ppm) for q in pp])
     if p.is_valid and p.area>1e-6:parts.append(p)
    union=unary_union(parts).buffer(.003,join_style=2).buffer(-.003,join_style=2);old=unary_union([Polygon(r[0],r[1:]) for r in rec['polygons']]).buffer(.003,join_style=2).buffer(-.003,join_style=2);errors.append(old.hausdorff_distance(union));parts=list(union.geoms) if hasattr(union,'geoms') else [union]
    rec['polygons']=[[list(p.exterior.coords),*[list(r.coords) for r in p.interiors]] for p in parts];q=union.representative_point();rec['anchor']=[q.x,q.y]
   assert max(errors)<.02,errors
   meta['checks']['independent_projection_max_difference_px']=max(errors);meta['tiles']=tiles
   if meta.get('pilot'):
    canvas=ImageEnhance.Contrast(canvas).enhance(1.07)
    canvas=ImageEnhance.Color(canvas).enhance(1.20)
    meta['color_finish']={'contrast':1.07,'saturation':1.20,'method':'Pillow RGB adjustments after native render'}
   buf=io.BytesIO();canvas.save(buf,format='WEBP',quality=92,method=6);payload=buf.getvalue();meta['image_sha256']=hashlib.sha256(payload).hexdigest();meta['image_bytes']=len(payload)
   # Same camera orientation allows a scale/translation-only aligned baseline crop.
   before=json.loads((OUT/'campus-atlas.json').read_text());same_camera=np.max(np.abs(rotation(before['camera']['rotation_euler'])-rot))<1e-5
   if same_camera:
    center=(pos-np.array(before['camera']['position']))@rot;oldppm=before['width']/before['camera']['ortho_scale'];cx=before['width']/2+center[0]*oldppm;cy=before['height']/2-center[1]*oldppm
    bounds=(cx-w/ppm*oldppm/2,cy-h/ppm*oldppm/2,cx+w/ppm*oldppm/2,cy+h/ppm*oldppm/2)
    old=Image.open(OUT/'campus-atlas.webp');aligned=old.transform((w,h),Image.Transform.EXTENT,bounds,Image.Resampling.BICUBIC)
    baseline={'baseline_image_sha256':sha(OUT/'campus-atlas.webp'),'baseline_crop_pixels':bounds,'baseline_method':'same camera orientation; affine aligned crop resampled for comparison only'}
   else:
    assert meta.get('pilot'), 'Only the local pilot can use a rotated inspection camera'
    lo=np.array(meta['satellite_world_low']);hi=np.array(meta['satellite_world_high']);direction=rot@np.array([0,0,-1])
    def satellite_pixel(x,y):
     q=pos+rot@np.array([(x-w/2)/ppm,(h/2-y)/ppm,0]);q=q+direction*(-q[2]/direction[2])
     return np.array([(q[0]-lo[0])/(hi[0]-lo[0])*2304,(hi[1]-q[1])/(hi[1]-lo[1])*3840])
    p00=satellite_pixel(0,0);px=satellite_pixel(1,0)-p00;py=satellite_pixel(0,1)-p00
    affine=(px[0],py[0],p00[0],px[1],py[1],p00[1])
    old=Image.open(ROOT/'model/campus/references/satellite.jpg')
    aligned=old.transform((w,h),Image.Transform.AFFINE,affine,Image.Resampling.BICUBIC)
    baseline={'baseline_image_sha256':sha(ROOT/'model/campus/references/satellite.jpg'),'baseline_method':'fixed satellite ground-plane rectification; buildings are not a before-render and their roof parallax differs','baseline_affine':affine}
   bb=io.BytesIO();aligned.save(bb,format='WEBP',quality=91,method=6)
   baseline['aligned_image_sha256']=hashlib.sha256(bb.getvalue()).hexdigest()
   baseline['aligned_image_bytes']=len(bb.getvalue())
   meta['comparison']={**baseline,'reference_file':'campus-reference.webp','reference_url':'http://gis.whut.edu.cn/index.shtml','reference_note':'Different campus; visual craft reference only. Saved visible map crop, captured 2026-09-09.','reference_sha256':sha(OUT/'campus-reference.webp')}
   meta['render_status']='generated_needs_visual_review';meta['visual_review']={'status':'pending'};meta['frontend_validation']={'status':'pending'}
   if meta.get('pilot'):
    pilot=ROOT/'output';pilot.mkdir(exist_ok=True)
    meta['comparison']['reference_scope']='Visual craft only; the real campus geometry remains traced from the local satellite.'
    meta['render_status']='generated_needs_visual_review';meta['visual_review']={'status':'pending'}
    assert len(payload)<8*1024**2
    for p,fingerprint in meta['sources'].items():assert sha(ROOT/p)==fingerprint,p
    (pilot/'north-pilot.webp').write_bytes(payload)
    (pilot/'north-pilot-before.webp').write_bytes(bb.getvalue())
    (pilot/'north-pilot.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')
   else:
    encoded=(json.dumps(meta,ensure_ascii=False,indent=2)+'\n').encode();total=sum(size(OUT/p) for p in ['campus-atlas.webp','campus-atlas.json','campus-reference.webp'])+len(payload)+len(bb.getvalue())+len(encoded)
    assert total<8*1024**2
    meta['budget']={'six_asset_total_bytes':total,'limit_bytes':8*1024**2,'cache_limit_bytes':192*1024**2,'source_amplification_limit':256}
    assert total/sum((ROOT/p).stat().st_size for p in ['scripts/north_study.py','scripts/campus_atlas.py','scripts/export_atlas.py','scripts/refine_buildings.py','src/CampusAtlas.jsx','src/campusAtlas.css'])<256
    for p,fingerprint in meta['sources'].items():assert sha(ROOT/p)==fingerprint,p
    (OUT/'campus-north.webp').write_bytes(payload);(OUT/'campus-north-before.webp').write_bytes(bb.getvalue());(OUT/'campus-north.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')
  print(json.dumps({'ok':True,'action':act}),flush=True)
 sys.exit(0)
import bpy,bmesh,random,subprocess
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view
sys.dont_write_bytecode=True;sys.path.insert(0,'/tmp/taihu-gis-deps');sys.path.insert(0,str(ROOT/'scripts'))
from shapely.geometry import Polygon,LineString,Point,box
from shapely.geometry.polygon import orient
from shapely.ops import unary_union
from shapely import constrained_delaunay_triangles
from refine_buildings import refine_north
assert capacity()-size(CACHE/'render-tile.png')-size(CACHE/'atlas.json')+int(2.5*1024**2)<192*1024**2,'Cache capacity reached'
sourcefiles=['model/campus/campus.blend','model/campus/layout.json','model/campus/references/satellite.jpg','model/central-campus/references/campus-aerial.jpg','scripts/north_study.py','scripts/refine_buildings.py','scripts/campus_atlas.py','scripts/export_atlas.py']
pilot='--pilot' in sys.argv or '--pilot-preview' in sys.argv
preview='--pilot-preview' in sys.argv
if pilot:sourcefiles.extend(['scripts/north_pilot_detail.py','output/garden-tree-canopy.png'])
sources={p:sha(ROOT/p) for p in sourcefiles}
bpy.ops.wm.open_mainfile(filepath=str(ROOT/'model/campus/campus.blend'));s=bpy.context.scene
D=json.loads((ROOT/'model/campus/layout.json').read_text());ext=json.loads((ROOT/'model/campus/references/satellite-export.json').read_text())['extent'];ox,oy=map(float,s['origin_epsg3857'].split(','));cs=float(s['metric_scale'])
def gp(q,z=0,source='satellite'):return Vector(((ext['xmin']+q[0]/1152*(ext['xmax']-ext['xmin'])-ox)*cs,(ext['ymax']-q[1]/1920*(ext['ymax']-ext['ymin'])-oy)*cs,z))
def shape(ps):return Polygon([(gp(p).x,gp(p).y) for p in ps])
ids=['N07']+['N%02d'%i for i in range(21,36)];rows=[r for r in D['buildings'] if r['id'] in ids];allroof=unary_union([shape(r['outline']) for r in D['buildings'] if r.get('source','satellite')=='satellite']);patch=shape([(455,326),(775,326),(775,548),(455,548)])
# This local study replaces all original render meshes in memory, preserving files.
for ob in s.objects:
 if ob.type in ('MESH','CURVE','LIGHT'):ob.hide_render=True
# Surrounding buildings retain their source meshes to keep the study in context.
for row in D['buildings']:
 if row['id'] not in ids and row.get('source','satellite')=='satellite' and shape(row['outline']).intersects(patch.buffer(100)):
  obj=next((o for o in s.objects if o.type=='MESH' and o.name.startswith(row['id']+' ')),None)
  if obj:obj.hide_render=False
for ob in s.objects:
 if ob.type=='MESH' and (ob.name.startswith(('B06 Central','B07 Central','B08 Central')) or (ob.parent and ob.parent.name.startswith(('B06 Central','B07 Central','B08 Central')))):ob.hide_render=False
anchor=bpy.data.objects.new('Study world material frame',None);s.collection.objects.link(anchor)
def mat(name,c,rough=.8):
 m=bpy.data.materials.new(name);m.use_nodes=True;bs=m.node_tree.nodes.get('Principled BSDF');bs.inputs['Base Color'].default_value=(*c,1);bs.inputs['Roughness'].default_value=rough;return m
def texture(m,a,b,scale,bump=.02):
 ns=m.node_tree.nodes;ls=m.node_tree.links;tc=ns.new('ShaderNodeTexCoord');tc.object=anchor;n=ns.new('ShaderNodeTexNoise');n.inputs['Scale'].default_value=scale;n.inputs['Detail'].default_value=3;ls.new(tc.outputs['Object'],n.inputs['Vector']);r=ns.new('ShaderNodeValToRGB');r.color_ramp.elements[0].color=(*a,1);r.color_ramp.elements[1].color=(*b,1);ls.new(n.outputs['Fac'],r.inputs[0]);bs=ns.get('Principled BSDF');ls.new(r.outputs[0],bs.inputs['Base Color']);bb=ns.new('ShaderNodeBump');bb.inputs['Strength'].default_value=.3;bb.inputs['Distance'].default_value=bump;ls.new(n.outputs[0],bb.inputs['Height']);ls.new(bb.outputs[0],bs.inputs['Normal'])
class Mesh:
 def __init__(self,name):self.name=name;self.v=[];self.f=[];self.mi=[];self.ms=[]
 def face(self,vs,m):
  if m not in self.ms:self.ms.append(m)
  i=len(self.v);self.v.extend([tuple(v) for v in vs]);self.f.append(tuple(range(i,len(self.v))));self.mi.append(self.ms.index(m))
 def plane(self,g,z,m):
  if g.is_empty:return []
  faces=[]
  for t in constrained_delaunay_triangles(g).geoms:
   vs=[(x,y,z) for x,y in list(orient(t,1).exterior.coords)[:-1]];self.face(vs,m);faces.append(vs)
  return faces
 def solid(self,g,z,h,m):
  self.plane(g,z+h,m)
  for p in (list(g.geoms) if hasattr(g,'geoms') else [g]):
   for ring in [p.exterior,*p.interiors]:
    for a,b in zip(ring.coords,list(ring.coords)[1:]):self.face([(a[0],a[1],z),(b[0],b[1],z),(b[0],b[1],z+h),(a[0],a[1],z+h)],m)
 def box(self,c,sz,m,ang=0):
  co,si=math.cos(ang),math.sin(ang);x,y,z=[d/2 for d in sz];vs=[(c[0]+a*co-b*si,c[1]+a*si+b*co,c[2]+d) for a,b,d in [(-x,-y,-z),(x,-y,-z),(x,y,-z),(-x,y,-z),(-x,-y,z),(x,-y,z),(x,y,z),(-x,y,z)]]
  for f in [(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]:self.face([vs[i] for i in f],m)
 def finish(self):
  me=bpy.data.meshes.new(self.name);me.from_pydata(self.v,[],self.f);me.update()
  for m in self.ms:me.materials.append(m)
  for p,i in zip(me.polygons,self.mi):p.material_index=i
  ob=bpy.data.objects.new(self.name,me);s.collection.objects.link(ob);return ob
def surface(name,g,z,m):
 mesh=Mesh(name);mesh.plane(g,z,m);return mesh.finish()
lawn=mat('Study meadow',(.17,.27,.075));texture(lawn,(.12,.225,.045),(.245,.315,.105),.32)
pave=mat('Study pale warm mineral paving',(.62,.59,.52));texture(pave,(.52,.51,.45),(.69,.66,.58),4)
roadmat=mat('Study charcoal asphalt',(.075,.085,.075));texture(roadmat,(.045,.052,.05),(.10,.115,.10),19,.01)
curb=mat('Study light stone curb',(.76,.73,.63));joint=mat('Study stone joints',(.34,.34,.30));soil=mat('Study soil',(.12,.105,.04));glass=mat('Study blue glazing',(.055,.17,.20),.25);cream=mat('Study limestone',(.73,.69,.56));white=mat('Study cream edge',(.84,.81,.69));brick=mat('Study red masonry',(.38,.095,.035));roof=mat('Study roof mineral',(.48,.47,.39));red=mat('Study warm roof bands',(.40,.11,.06));blue=mat('Study blue roof bands',(.05,.25,.36),.6)
for mm in [cream,brick,roof,red]:
 c=tuple(mm.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value)[:3];texture(mm,tuple(v*.82 for v in c),tuple(v*1.06 for v in c),8,.01)
# Fine concrete courses break up flat roofs without adding invented equipment.
ns=roof.node_tree.nodes;ls=roof.node_tree.links;tc=ns.new('ShaderNodeTexCoord');tc.object=anchor;panels=ns.new('ShaderNodeTexBrick');panels.offset=0;panels.inputs['Scale'].default_value=1;panels.inputs['Brick Width'].default_value=3.6;panels.inputs['Row Height'].default_value=8.0;panels.inputs['Mortar Size'].default_value=.018;panels.inputs['Color1'].default_value=(.51,.51,.46,1);panels.inputs['Color2'].default_value=(.58,.565,.505,1);panels.inputs['Mortar'].default_value=(.37,.39,.35,1);ls.new(tc.outputs['Object'],panels.inputs['Vector']);ls.new(panels.outputs['Color'],ns.get('Principled BSDF').inputs['Base Color'])
roadlines=[(r[1],r[2]) for r in D['roads'] if r[0] in ['西侧贯通校道','北区东西联系路','北区南北联系路','北区西侧南北路','公寓横向路']]
roads=unary_union([LineString([(gp(p).x,gp(p).y) for p in ps]).buffer(w/2,join_style='round') for ps,w in roadlines]).intersection(patch.buffer(100)).difference(allroof.buffer(.25))
# Manually traced continuous forecourts, no classification-pixel boundaries.
courts=[[(558,359),(628,359),(628,452),(554,452)],[(510,395),(562,395),(563,454),(506,449)],[(475,439),(530,439),(532,507),(480,503)],[(526,450),(624,450),(624,521),(526,510)],[(640,394),(744,394),(749,453),(739,535),(640,527)],[(643,332),(758,349),(754,395),(638,393)]]
plaza=unary_union([shape(p) for p in courts])
beds=[r['outline'] for r in D['landscape']['lawn_polygons'] if r['id'].startswith(('N07','N34'))]
beds += [[(531,501),(620,510),(620,517),(532,508)],[(561,351),(623,343),(624,355),(562,363)],[(679,388),(748,388),(748,393),(678,394)],[(642,450),(739,454),(738,460),(641,457)],[(612,385),(621,385),(621,399),(612,399)]]
# Narrow planted seams visible between the apartment wings; retain path breaks.
apartment_beds=[[(565,418),(600,418),(600,421),(565,421)],[(565,468),(570,468),(570,483),(565,483)],[(565,489),(571,489),(571,503),(565,502)],[(530,482),(552,482),(552,485),(530,485)]]
beds+=apartment_beds
planting=unary_union([shape(p) for p in beds]).difference(allroof.buffer(.25)).difference(roads)
# Court footprints retraced from the fixed satellite, avoiding the coarse road centreline.
sportpolys=[[(612,400),(631,400),(631,455),(612,455)],[(614,463),(633,463),(633,496),(614,496)]]
sportmask=unary_union([shape(p) for p in sportpolys]);roads=roads.difference(sportmask.buffer(.4))

paved=plaza.difference(planting).difference(roads.buffer(.30)).difference(allroof.buffer(.15)).difference(sportmask)
surface('Study landscape base',patch.buffer(200),.18,lawn);surface('Study continuous plazas',paved,.33,pave);surface('Study asphalt',roads,.35,roadmat);surface('Study road curbs',roads.buffer(.30).difference(roads).difference(allroof),.38,curb);surface('Study planting edge',planting.buffer(.22).difference(planting).intersection(paved),.39,curb)
surface('Study planted bed ground',planting,.342,lawn)
# Metre-scale paver courses, subtle enough to remain material rather than a checkerboard.
for axis in range(2):
 bounds=paved.bounds;start=math.floor(bounds[axis]/3)*3;end=bounds[axis+2]
 for i in range(int((end-start)/3)+1):
  t=start+i*3;line=LineString([(t,bounds[1]),(t,bounds[3])]) if axis==0 else LineString([(bounds[0],t),(bounds[2],t)])
  surface('Study stone course',line.buffer(.018).intersection(paved),.338,joint)
# Fine paver colour variation uses world metre coordinates.
ns=pave.node_tree.nodes;ls=pave.node_tree.links;tc=ns.new('ShaderNodeTexCoord');tc.object=anchor;bt=ns.new('ShaderNodeTexBrick');bt.offset=.5;bt.offset_frequency=2;bt.inputs['Scale'].default_value=1;bt.inputs['Brick Width'].default_value=1.7;bt.inputs['Row Height'].default_value=1.15;bt.inputs['Mortar Size'].default_value=.012;bt.inputs['Color1'].default_value=(.59,.575,.52,1);bt.inputs['Color2'].default_value=(.68,.65,.59,1);bt.inputs['Mortar'].default_value=(.42,.42,.37,1);ls.new(tc.outputs['Object'],bt.inputs['Vector']);ls.new(bt.outputs['Color'],ns.get('Principled BSDF').inputs['Base Color'])
# Satellite shows muted green hardstanding inside three apartment courtyards.
courtfinish=mat('Study green courtyard hardstanding',(.29,.43,.36));texture(courtfinish,(.27,.39,.32),(.37,.46,.39),5,.008)
green_hardstanding=[[(575,389),(592,389),(592,406),(575,406)],[(515,408),(534,401),(534,423),(514,423)],[(482,459),(509,459),(509,478),(488,478),(488,487),(480,487)],[(551,447),(610,447),(610,466),(569,466),(569,460),(548,460)]]
for ps in green_hardstanding:
 g=shape(ps).intersection(paved);surface('Study apartment courtyard finish',g,.344,courtfinish);surface('Study apartment courtyard border',g.difference(g.buffer(-.22)),.35,curb)
grey_hardstanding=[[(553,422),(611,422),(611,444),(551,444),(551,434),(558,434)]]
hardgrey=mat('Study source grey hardstanding',(.29,.325,.30));texture(hardgrey,(.25,.28,.26),(.35,.38,.35),2.3,.013)
for ps in grey_hardstanding:
 g=shape(ps).intersection(paved);surface('Study source grey apron',g,.347,hardgrey);surface('Study grey apron margin',g.difference(g.buffer(-.19)),.352,curb)
# Ground-level mineral margins follow existing walls and source courtyard edges.
apron=allroof.buffer(1.1,join_style='mitre').difference(allroof.buffer(.15)).intersection(paved)
surface('Study building foot margins',apron,.36,pave)
westconcrete=mat('Study west perimeter mineral path',(.41,.415,.36));texture(westconcrete,(.36,.37,.32),(.49,.49,.43),3,.018)
westpath=next(r for r in D['roads'] if r[0]=='西侧贯通校道')
weststrip=LineString([(gp(p).x,gp(p).y) for p in westpath[1]]).buffer(westpath[2]/2,join_style='round').intersection(roads)
surface('Study source pale west path',weststrip,.363,westconcrete)
# Source-visible playing surfaces and their line markings.
sportred=mat('Study court perimeter',(.43,.18,.105));sportgreen=mat('Study court playing surface',(.11,.32,.255));linewhite=mat('Study court markings',(.79,.78,.66))
for idx,ps in enumerate(sportpolys):
 g=shape(ps);surface('Study source court '+str(idx),g,.39,sportred);surface('Study playing surface',g.buffer(-1),.402,sportgreen);minx,miny,maxx,maxy=g.bounds;cx=(minx+maxx)/2;n=2 if idx==0 else 1
 for k in range(n):
  ay=miny+(maxy-miny)*k/n+1.4;by=miny+(maxy-miny)*(k+1)/n-1.4;cy=(ay+by)/2;inner=box(minx+1.4,ay,maxx-1.4,by)
  surface('Study court sideline',inner.boundary.buffer(.055),.415,linewhite);surface('Study court halfway',LineString([(minx+1.4,cy),(maxx-1.4,cy)]).buffer(.055),.415,linewhite);surface('Study centre circle',Point(cx,cy).buffer(1.8,resolution=32).boundary.buffer(.055),.418,linewhite)
  for yy,sign in [(ay,1),(by,-1)]:
   key=box(cx-2.3,min(yy,yy+sign*4.8),cx+2.3,max(yy,yy+sign*4.8));surface('Study basketball key',key,.41,sportred);surface('Study basketball key line',key.boundary.buffer(.055),.42,linewhite)
   hoop=Mesh('Study basketball board');hoop.box((cx,yy+sign*.55,2.9),(1.65,.12,1),white);hoop.box((cx,yy-sign*.55,1.6),(.12,.12,3.2),cream);hoop.finish()
# The source oval is pale hardscape with a warm inset, not another grass bed.
from shapely.affinity import scale as geometry_scale
center=gp((720,366));oval=geometry_scale(Point(center.x,center.y).buffer(1,resolution=64),11,7);ovalstone=mat('Study oval warm stone',(.53,.455,.335));texture(ovalstone,(.47,.405,.30),(.61,.535,.395),4,.009);surface('Study source oval paving',oval,.345,pave);surface('Study oval stone inset',geometry_scale(oval,.56,.72,origin='centroid'),.349,ovalstone);surface('Study oval walking margin',oval.buffer(.6).difference(oval),.36,curb)
refine=refine_north(s,{'buildings':rows},gp,mat,ROOT);faces=refine['roof_faces_world']
# Slate roof courses stay readable at native close-up scale.
for mm in bpy.data.materials:
 if mm.name.startswith('Atlas architecture dark slate tiles'):
  ns=mm.node_tree.nodes;ls=mm.node_tree.links;tc=ns.new('ShaderNodeTexCoord');tc.object=anchor;bt=ns.new('ShaderNodeTexBrick');bt.inputs['Scale'].default_value=1;bt.inputs['Brick Width'].default_value=.52;bt.inputs['Row Height'].default_value=.36;bt.inputs['Mortar Size'].default_value=.016;bt.inputs['Color1'].default_value=(.095,.13,.12,1);bt.inputs['Color2'].default_value=(.16,.19,.17,1);bt.inputs['Mortar'].default_value=(.055,.075,.067,1);ls.new(tc.outputs['Object'],bt.inputs['Vector']);ls.new(bt.outputs['Color'],ns.get('Principled BSDF').inputs['Base Color'])
# N31: stepped dining building, north high block and lower south wing, from aerial silhouette.
for ob in s.objects:
 if ob.get('source_id')=='N31':ob.hide_render=True
r=next(r for r in rows if r['id']=='N31');foot=shape(r['outline']);cut=gp((0,416)).y;zones=[(foot.intersection(box(-1e4,cut,1e4,1e4)),26.6),(foot.intersection(box(-1e4,-1e4,1e4,cut)),19.0)];bm=Mesh('Study N31 stepped dining');faces['N31']=[]
for g,h in zones:
 bm.solid(g,.42,h,cream);faces['N31']+=bm.plane(g,h+.45,roof);bm.solid(g.difference(g.buffer(-.18)),h+.45,.48,white)
 coords=list(orient(g,1).exterior.coords)
 for a,b in zip(coords,coords[1:]):
  av=Vector((*a,0));bv=Vector((*b,0));v=bv-av;n=v.length
  if n<2:continue
  t=v/n;out=Vector((t.y,-t.x,0));ang=math.atan2(t.y,t.x);bays=max(1,int(n/3.2));step=n/bays
  # Skip shared seam walls below the adjacent block height.
  shared=abs(a[1]-cut)<.001 and abs(b[1]-cut)<.001
  for floor in range(int(h/3.8)):
   z=.42+(floor+.5)*3.8
   if shared and z<19.4:continue
   c=(av+bv)/2+out*.09;c.z=.42+floor*3.8;bm.box(c,(n,.26,.16),white,ang)
   for j in range(bays):
    c=av+t*((j+.5)*step)+out*.065;c.z=z
    bm.box(c,(step*.88,.12,1.91),white,ang);bm.box(c+out*.075,(step*.80,.10,1.73),glass,ang);bm.box(c+out*.14,(.065,.08,1.77),white,ang)
 # source roof skylight interpreted inside roof perimeter
 center=g.representative_point();skylength=max(7,min(19,(g.bounds[3]-g.bounds[1])*.65));bm.box((center.x,center.y,h+.8),(1.8,skylength,.5),white);bm.box((center.x,center.y,h+1.07),(1.5,skylength-.3,.10),glass)
 for j in range(1,int(skylength/.85)):
  bm.box((center.x,center.y-skylength/2+j*.85,h+1.135),(1.55,.07,.055),white)
bm.finish()
# Dining roofs: source bands follow their skewed eaves, not horizontal image rows.
# N33's fixed satellite roof is red/weathered oxide; it is not a blue continuation.
roof_red=mat('Study dining weathered oxide roof',(.28,.095,.052),.66)
roof_blue=mat('Study dining muted blue panels',(.085,.22,.31),.59)
annex_red=mat('Study annex red metal north slope',(.37,.055,.037),.62)
annex_oxide=mat('Study annex weathered south slope',(.28,.135,.085),.73)
for mm in [roof_red,roof_blue,annex_red,annex_oxide]:
 c=tuple(mm.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value)[:3]
 texture(mm,tuple(v*.78 for v in c),tuple(v*1.10 for v in c),3,.014)
 # Corrugation is a material-scale finish, with sheet-sized seams added below.
 ns=mm.node_tree.nodes;ls=mm.node_tree.links;tc=ns.new('ShaderNodeTexCoord');tc.object=anchor;wave=ns.new('ShaderNodeTexWave');wave.wave_type='BANDS';wave.bands_direction='X';wave.inputs['Scale'].default_value=3.1;ls.new(tc.outputs['Object'],wave.inputs['Vector']);bb=ns.new('ShaderNodeBump');bb.inputs['Strength'].default_value=.18;bb.inputs['Distance'].default_value=.018;ls.new(wave.outputs['Fac'],bb.inputs['Height']);ls.new(bb.outputs[0],ns.get('Principled BSDF').inputs['Normal'])
dining_bands={}
def dining_roof(ident,quad,edges,materials):
 old=faces[ident];mesh=Mesh('Study '+ident+' source aligned roof finish');new=[];bands=[]
 def at(a,b,t):return [a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t]
 # Quad is north-west, north-east, south-east, south-west in source pixels.
 for idx,(lo,hi) in enumerate(zip(edges,edges[1:])):
  pp=[at(quad[0],quad[3],lo),at(quad[1],quad[2],lo),at(quad[1],quad[2],hi),at(quad[0],quad[3],hi)];strip=shape(pp);bands.append({'source_pixels':pp,'finish':materials[idx].name})
  for f in old:
   g=Polygon([p[:2] for p in f]).intersection(strip)
   if g.is_empty:continue
   a,b,c=[Vector(p) for p in f[:3]];normal=(b-a).cross(c-a)
   if abs(normal.z)<1e-7:continue
   def height(x,y):return a.z-(normal.x*(x-a.x)+normal.y*(y-a.y))/normal.z+.025
   for tr in constrained_delaunay_triangles(g).geoms:
    vs=[(x,y,height(x,y)) for x,y in list(orient(tr,1).exterior.coords)[:-1]];mesh.face(vs,materials[idx]);new.append(vs)
 # A subdued ridge cap replaces the old bright crossing line on each hall.
 darkcap=mat('Study '+ident+' subdued metal ridge',(.13,.16,.15),.62)
 obj=next(o for o in s.objects if o.get('source_id')==ident)
 for slot in obj.material_slots:
  if slot.material and slot.material.name=='Atlas architecture metal frame':slot.material=darkcap
 faces[ident]=new;mesh.finish();dining_bands[ident]=bands
 return old
old32=dining_roof('N32',[[684,399],[713,405],[709,446],[677,441]],[0,.24,.43,.63,.82,1],[roof_red,roof_blue,roof_red,roof_blue,roof_red])
old33=dining_roof('N33',[[710,431],[740,437],[735,451],[708,445]],[0,.50,1],[annex_red,annex_oxide])
# Restrained roof-sheet joints follow the building's long direction and preserve pitch.
seammat=mat('Study dining roof sheet seams',(.21,.29,.29),.6);seams=Mesh('Study dining panel seams')
for ident,old in [('N32',old32),('N33',old33)]:
 g=shape(next(r for r in rows if r['id']==ident)['outline']);rect=list(g.minimum_rotated_rectangle.exterior.coords);a,b=max(zip(rect,rect[1:]),key=lambda e:Point(e[0]).distance(Point(e[1])));u=Vector((b[0]-a[0],b[1]-a[1],0)).normalized();v=Vector((-u.y,u.x,0));center=Vector((g.centroid.x,g.centroid.y,0));extent=max(Point(a).distance(Point(b)) for a,b in zip(rect,rect[1:]))
 for j in range(-int(extent/1.4),int(extent/1.4)+1):
  q=center+u*(j*1.4);line=LineString([(q.x-v.x*100,q.y-v.y*100),(q.x+v.x*100,q.y+v.y*100)]).buffer(.024).intersection(g.buffer(-.10))
  for f in old:
   cut=line.intersection(Polygon([p[:2] for p in f]))
   if cut.is_empty:continue
   a,b,c=[Vector(p) for p in f[:3]];normal=(b-a).cross(c-a)
   if abs(normal.z)<1e-7:continue
   for tr in constrained_delaunay_triangles(cut).geoms:
    seams.face([(x,y,a.z-(normal.x*(x-a.x)+normal.y*(y-a.y))/normal.z+.039) for x,y in list(orient(tr,1).exterior.coords)[:-1]],seammat)
seams.finish()
# N34/N35: rebuild the academic envelope so the photographed glazing is not
# covered by the generic floor bands and brick fins underneath it.
academic_shapes={ident:shape(next(r for r in rows if r['id']==ident)['outline']) for ident in ['N34','N35']}
academic_union=unary_union(list(academic_shapes.values()))
for ob in s.objects:
 if ob.get('source_id') in academic_shapes:ob.hide_render=True
academic=Mesh('Study red academic photo facade')
academic.solid(academic_union.buffer(-.28,join_style='mitre'),.38,17.80,brick)
academic.solid(academic_union.buffer(-.12,join_style='mitre'),.38,.48,cream)
for ident,g in academic_shapes.items():faces[ident]=academic.plane(g,18.20,roof)
academic.solid(academic_union.difference(academic_union.buffer(-.19,join_style='mitre')),18.20,.35,white)
frame=mat('Study academic pale aluminium',(.58,.63,.58),.47)
recess=mat('Study academic window recess',(.035,.060,.055),.85)
pane_variants=[mat('Study academic window '+str(i),c,.34) for i,c in enumerate([(.08,.17,.16),(.16,.24,.22),(.12,.21,.20)])]
academic_facades=[]
# Shapely union orientation is not guaranteed; orient the whole polygon first.
for ring in [orient(academic_union,1).exterior,*orient(academic_union,1).interiors]:
 coords=list(ring.coords)
 for aa,bb in zip(coords,coords[1:]):
  a=Vector((*aa,0));b=Vector((*bb,0));v=b-a;length=v.length
  if length<2:continue
  t=v/length;out=Vector((t.y,-t.x,0));angle=math.atan2(t.y,t.x)
  exterior=LineString([aa,bb]).distance(academic_union.exterior)<.01
  # The aerial shows the east public front with a top ribbon and vertical glass bay.
  front=exterior and out.x>.92 and length>45
  bays=max(1,round(length/3.05));step=length/bays;baycenter=length*.59;baywidth=7.1
  def detail(distance,z,width,height,depth,material,offset=-.13):
   c=a+t*distance+out*offset;c.z=z;academic.box(c,(width,depth,height),material,angle)
  # Thin stone floor edges leave the red spandrels visible.
  for level in range(1,5):
   z=.40+level*3.5
   if front:
    for lo,hi in [(0,baycenter-baywidth/2),(baycenter+baywidth/2,length)]:
     detail((lo+hi)/2,z,hi-lo,.13,.34,white)
   else:detail(length/2,z,length,.13,.34,white)
  for level in range(5):
   z=.40+(level+.5)*3.5
   if front and level==4:continue
   for j in range(bays):
    d=(j+.5)*step
    if front and abs(d-baycenter)<baywidth/2+step*.36:continue
    width=step*.54;height=2.60 if level<2 else 2.30
    detail(d,z,width+.20,height+.16,.12,recess,-.20)
    detail(d,z,width,height,.07,pane_variants[(j*7+level)%3],-.11)
    # Narrow jambs, mullion, raised sill and small lower ventilation louvres.
    for side in [-1,1]:detail(d+side*(width/2+.045),z,.08,height+.18,.19,white,-.09)
    detail(d,z+.02,.055,height,.09,frame,-.055)
    detail(d,z+height*.20,width,.065,.10,frame,-.05)
    detail(d,z-height/2-.045,width+.21,.12,.34,white,-.055)
    detail(d,z+height/2+.045,width+.19,.09,.20,white,-.07)
    if j%4==0 and level>1:
     for k in range(4):detail(d+width*.25,z-height*.39+k*.10,width*.42,.038,.10,frame,-.03)
  if front:
   detail(length/2,16.02,length-.9,2.15,.10,glass,-.12)
   for j in range(1,int(length/.95)):
    detail(j*.95,16.02,.055,2.18,.13,frame,-.025)
   detail(length/2,16.02,length-.9,.060,.14,frame,-.02)
   for z in [14.91,17.14]:detail(length/2,z,length,.16,.40,white,-.06)
   # Continuous central glazing with broad pale floor spandrels as seen in photo.
   detail(baycenter,7.58,baywidth,13.9,.18,glass,.005)
   for side in [-1,1]:detail(baycenter+side*(baywidth/2+.09),7.61,.22,14.05,.45,cream,.03)
   for j in range(1,7):detail(baycenter-baywidth/2+j*baywidth/7,7.58,.065,13.9,.14,frame,.12)
   for level in range(1,4):
    detail(baycenter,.40+level*3.5,baywidth,.62,.24,cream,.15)
    detail(baycenter,1.98+level*3.5,baywidth,.07,.15,frame,.15)
   detail(baycenter,1.45,3.2,2.18,.20,recess,.13)
   for side in [-1,1]:detail(baycenter+side*.78,1.42,1.44,2.05,.12,glass,.26)
   detail(baycenter,2.95,8.0,.23,2.2,white,.9)
   for k in range(3):detail(baycenter,.40+k*.13,7.8-k*.35,.14,1.8-k*.4,cream,1.4-k*.2)
  academic_facades.append({'edge_world':[list(a),list(b)],'bays_estimate':bays,'photo_east_front':front,'window_dimensions_estimated':True})
academic.finish()
# N34: unequal rooftop pavilions within its traced roof. Dimensions interpreted from photo.
pavilionroof=mat('Study academic pavilion green roof',(.10,.22,.21),.48)
ns=pavilionroof.node_tree.nodes;ls=pavilionroof.node_tree.links;tc=ns.new('ShaderNodeTexCoord');tc.object=anchor;grid=ns.new('ShaderNodeTexBrick');grid.offset=0;grid.inputs['Scale'].default_value=1;grid.inputs['Brick Width'].default_value=.95;grid.inputs['Row Height'].default_value=1.35;grid.inputs['Mortar Size'].default_value=.032;grid.inputs['Color1'].default_value=(.10,.205,.19,1);grid.inputs['Color2'].default_value=(.145,.25,.23,1);grid.inputs['Mortar'].default_value=(.42,.48,.44,1);ls.new(tc.outputs['Object'],grid.inputs['Vector']);ls.new(grid.outputs['Color'],ns.get('Principled BSDF').inputs['Base Color'])
bm=Mesh('Study N34 rooftop silhouette');g34=shape(next(r for r in rows if r['id']=='N34')['outline'])
for ps,h in [([(687,469),(701,470),(701,478),(687,477)],3.1), ([(708,495),(718,496),(718,508),(708,507)],2.2)]:
 g=shape(ps).intersection(g34.buffer(-.3));bm.solid(g,18.5,h,brick);faces['N34']+=bm.plane(g,18.5+h+.06,pavilionroof);bm.solid(g.difference(g.buffer(-.15)),18.5+h+.06,.25,white)
 coords=list(orient(g,1).exterior.coords)
 for aa,bb in zip(coords,coords[1:]):
  a=Vector((*aa,0));b=Vector((*bb,0));v=b-a;length=v.length
  if length<2:continue
  t=v/length;out=Vector((t.y,-t.x,0));angle=math.atan2(t.y,t.x);center=(a+b)/2+out*.07;center.z=18.5+h*.53;bm.box(center,(length-.65,.10,h*.47),glass,angle)
  for j in range(1,max(2,int(length/1.4))):
   c=a+t*(j*length/max(2,int(length/1.4)))+out*.14;c.z=center.z;bm.box(c,(.065,.07,h*.49),white,angle)
bm.finish()
# Branch sprays and folded leaf blades create irregular crowns rather than balls.
# Centres remain fixed input samples; shape, colour, leaf scale and crown widths are illustrative.
leafcolors=[(.065,.155,.028),(.105,.215,.046),(.15,.265,.071),(.085,.205,.038),(.135,.265,.066),(.19,.305,.092),(.13,.235,.065),(.18,.285,.095),(.23,.33,.13)]
leaves=[mat('Study broadleaf '+str(i),c,.88) for i,c in enumerate(leafcolors)];bark=mat('Study bark',(.17,.125,.068));protos=[]
def branch(mesh,a,b,ra,rb):
 a,b=Vector(a),Vector(b);v=(b-a).normalized();side=v.cross(Vector((0,0,1)))
 if side.length<.001:side=Vector((1,0,0))
 side.normalize();other=v.cross(side).normalized();ar=[];br=[]
 for k in range(6):
  q=side*math.cos(k*math.tau/6)+other*math.sin(k*math.tau/6);ar.append(a+q*ra);br.append(b+q*rb)
 for k in range(6):mesh.face([ar[k],ar[(k+1)%6],br[(k+1)%6],br[k]],bark)
for seed in range(12):
 rng=random.Random(840+seed);mesh=Mesh('Study broadleaf crown '+str(seed));family=seed%3;centres=[]
 n=6+seed%4
 for j in range(n):
  angle=j*math.tau/n+rng.uniform(-.34,.34);r=rng.uniform(.38,.72);z=rng.uniform(-.21,.26)
  if family==1:r*=.78;z+=.13
  centre=Vector((math.cos(angle)*r,math.sin(angle)*r,z));centres.append(centre)
  root=Vector((0,0,-.86));fork=Vector((centre.x*.38,centre.y*.38,-.34));branch(mesh,root,fork,.029,.019);branch(mesh,fork,centre,.019,.005)
 centres.append(Vector((-.10,.08,.31)))
 for j in range(1900):
  c=centres[j%len(centres)];angle=rng.random()*math.tau;rr=math.sqrt(rng.random())*rng.uniform(.18,.38)
  position=c+Vector((math.cos(angle)*rr,math.sin(angle)*rr,rng.uniform(-.22,.22)))
  # A few open gaps between asymmetrical sprays allow branches and light through.
  lean=rng.uniform(-.7,.7);yaw=rng.random()*math.tau;length=rng.uniform(.055,.105);width=length*rng.uniform(.65,.88)
  u=Vector((math.cos(yaw),math.sin(yaw),lean)).normalized()*length;v=Vector((-math.sin(yaw),math.cos(yaw),rng.uniform(-.25,.25))).normalized()*width;fold=Vector((0,0,length*.17))
  material=leaves[family*3+rng.choices([0,1,2],[.28,.51,.21])[0]]
  mesh.face([position-u,position-v+fold,position+u,position+v+fold],material)
 ob=mesh.finish();ob.hide_render=True;protos.append(ob.data)
woodland_pixels=[(425,240),(670,240),(668,274),(655,300),(627,332),(619,349),(565,365),(522,400),(475,442),(425,442)]
woodland=shape(woodland_pixels)
woodground=mat('Study woodland floor',(.15,.235,.075));texture(woodground,(.105,.175,.05),(.21,.265,.095),.25,.016)
# Interpolated edge weights avoid a hard polygon-colour seam across open grass.
ns=woodground.node_tree.nodes;ls=woodground.node_tree.links;woodramp=next(n for n in ns if n.type=='VALTORGB');tc=ns.new('ShaderNodeTexCoord');tc.object=anchor;grassnoise=ns.new('ShaderNodeTexNoise');grassnoise.inputs['Scale'].default_value=.32;grassnoise.inputs['Detail'].default_value=3;grassramp=ns.new('ShaderNodeValToRGB');grassramp.color_ramp.elements[0].color=(.12,.225,.045,1);grassramp.color_ramp.elements[1].color=(.245,.315,.105,1);ls.new(tc.outputs['Object'],grassnoise.inputs['Vector']);ls.new(grassnoise.outputs['Fac'],grassramp.inputs[0]);attribute=ns.new('ShaderNodeAttribute');attribute.attribute_name='woodland_blend';blend=ns.new('ShaderNodeMixRGB');ls.new(attribute.outputs['Fac'],blend.inputs[0]);ls.new(grassramp.outputs[0],blend.inputs[1]);ls.new(woodramp.outputs[0],blend.inputs[2]);ls.new(blend.outputs[0],ns.get('Principled BSDF').inputs['Base Color'])
woodmesh=Mesh('Study source woodland ground');woodmask=patch.buffer(100).difference(plaza).difference(roads).difference(allroof);woodfield=woodland.intersection(woodmask)
for lo,hi in [(0,2),(2,5),(5,9),(9,14),(14,20)]:woodmesh.plane(woodfield.buffer(-lo).difference(woodfield.buffer(-hi)),.225,woodground)
woodmesh.plane(woodfield.buffer(-20),.225,woodground);woodob=woodmesh.finish();attr=woodob.data.attributes.new(name='woodland_blend',type='FLOAT',domain='POINT')
for v in woodob.data.vertices:attr.data[v.index].value=min(1,woodfield.boundary.distance(Point(v.co.x,v.co.y))/14)
count=0;treegroups={'woodland':0,'street':0,'courtyard':0};trunks=Mesh('Study trunks and branches');treebasins=[]
for i,r in enumerate(D['trees']):
 if r.get('source','satellite')!='satellite':continue
 p=gp(r['position']);point=Point(p.x,p.y)
 if not patch.buffer(100).covers(point) or allroof.buffer(.4).covers(point) or roads.buffer(-.3).covers(point) or sportmask.covers(point):continue
 forest=woodland.covers(point);street=not forest and roads.distance(point)<8
 family=0 if forest else 1 if street else 2;treegroups['woodland' if forest else 'street' if street else 'courtyard']+=1
 rng=random.Random(9100+i);rad=r['radius']*(rng.uniform(1.36,1.70) if forest else rng.uniform(1.02,1.26));h=r['height'];proto=protos[family+3*(i%4)]
 ob=bpy.data.objects.new('Study source tree '+str(i),proto);s.collection.objects.link(ob);ob.location=(p.x,p.y,max(rad*.86,h-rad*.28));ob.scale=(rad*rng.uniform(.90,1.09),rad*rng.uniform(.80,1.05),rad*(.91 if family==1 else .80));ob.rotation_euler.z=i*2.39
 trunks.box((p.x,p.y,h*.34),(.21,.21,h*.68),bark);count+=1
 if paved.covers(point):treebasins.append(point.buffer(min(1.15,max(.65,r['radius']*.24))))
 # Understorey occurs only in traced planting beds and the photographed woodland.
 if planting.covers(point) or forest:
  ob=bpy.data.objects.new('Study source understory '+str(i),protos[(family+3)%12]);s.collection.objects.link(ob);ob.location=(p.x+.35,p.y-.28,.69);ob.scale=(rad*.45,rad*.33,.70)
trunks.finish()
if treebasins:
 basins=unary_union(treebasins).intersection(paved).difference(apron).difference(roads)
 surface('Study existing tree root beds',basins,.371,soil);surface('Study tree bed mineral lips',basins.buffer(.10).difference(basins).intersection(paved),.375,curb)
# Low planting stays subordinate to the trees and follows the fixed bed boundaries.
for k,g in enumerate([shape(p) for p in beds[:3]]+[shape(p) for p in apartment_beds]):
 g=g.difference(allroof.buffer(.4)).difference(roads.buffer(.25))
 if g.is_empty:continue
 path=g.buffer(-.6).boundary
 for i in range(int(path.length/.88)):
  q=path.interpolate(i*.88)
  if allroof.buffer(.2).covers(q):continue
  ob=bpy.data.objects.new('Study courtyard hedge',protos[2+3*(i%4)]);s.collection.objects.link(ob);ob.location=(q.x,q.y,.62);ob.scale=(.79,.63,.60)
# The inspection crop has its own source-bound detail layer and does not mutate
# either the published north sample or the campus atlas.
pilot_detail=None
# Lighting and camera keep the baseline orientation exactly for an honest before/after crop.
ld=bpy.data.lights.new('Study sunlight','SUN');ld.energy=2.5;ld.angle=.065;lo=bpy.data.objects.new('Study sunlight',ld);s.collection.objects.link(lo);lo.rotation_euler=(math.radians(27),math.radians(-22),math.radians(-30))
if pilot:
 ld.angle=.085
 lo.rotation_euler=(math.radians(18),math.radians(-12),math.radians(-30))
s.world.use_nodes=True;s.world.node_tree.nodes.get('Background').inputs[0].default_value=(.78,.83,.90,1);s.world.node_tree.nodes.get('Background').inputs[1].default_value=.65
cam=s.camera;cam.data.type='ORTHO';baseline=json.loads((OUT/'campus-atlas.json').read_text());cam.rotation_euler=baseline['camera']['rotation_euler'];focus=[gp(q,z) for r in rows for q in r['outline'] for z in [0,r['height_estimate_m']+3]]
if pilot:
 # A north-aligned camera matches the source street axes and excludes the
 # unrelated grass corners introduced by the rotated campus-wide camera.
 cam.rotation_euler=(cam.rotation_euler.x,0,0)
 focus=[gp(q,z) for q in [(470,330),(750,330),(750,555),(470,555)] for z in [0,31]]
target=sum(focus,Vector())/len(focus);cam.location=target+cam.rotation_euler.to_matrix()@Vector((0,0,1000));bpy.context.view_layer.update();inv=cam.matrix_world.inverted();pts=[inv@p for p in focus];xs=[p.x for p in pts];ys=[p.y for p in pts]
cam.location+=cam.matrix_world.to_3x3()@Vector(((min(xs)+max(xs))/2,(min(ys)+max(ys))/2,0));cam.data.ortho_scale=max(max(xs)-min(xs),(max(ys)-min(ys))*4/3)*(1.08 if pilot else 1.18)
final='--final' in sys.argv;W,H=(1200,900) if preview else (2400,1800) if final or pilot else (1600,1200);s.render.engine='CYCLES';s.cycles.samples=8 if preview else 24 if pilot else 32 if final else 12;s.cycles.use_denoising=True;s.cycles.max_bounces=4;s.render.threads_mode='FIXED';s.render.threads=4;s.render.resolution_x=W;s.render.resolution_y=H;s.render.resolution_percentage=100;s.render.image_settings.file_format='PNG';s.render.image_settings.color_mode='RGB';s.render.image_settings.compression=100;s.render.film_transparent=False;s.view_settings.view_transform='AgX';s.view_settings.look='AgX - Medium High Contrast';s.view_settings.exposure=.12;bpy.context.view_layer.update()
if pilot:
 s.view_settings.view_transform='Standard';s.view_settings.look='Medium High Contrast';s.view_settings.exposure=-.2
if pilot:
 from north_pilot_detail import add_pilot_detail
 pilot_detail=add_pilot_detail(globals())
records=[];diffs=[]
for r in rows:
 actual=unary_union([Polygon([p[:2] for p in f]) for f in faces[r['id']]]);diffs.append(actual.symmetric_difference(shape(r['outline'])).area);assert diffs[-1]<.01,(r['id'],diffs[-1])
 ps=[]
 for f in faces[r['id']]:
  vv=[world_to_camera_view(s,cam,Vector(p)) for p in f];g=Polygon([(p.x*W,(1-p.y)*H) for p in vv])
  if g.is_valid and g.area>1e-6:ps.append(g)
 union=unary_union(ps).buffer(.003,join_style=2).buffer(-.003,join_style=2);parts=list(union.geoms) if hasattr(union,'geoms') else [union];q=union.representative_point();old=next(v for v in baseline['records'] if v['id']==r['id']);record={**old,'polygons':[[list(p.exterior.coords),*[list(i.coords) for i in p.interiors]] for p in parts],'anchor':[q.x,q.y]};record['description']=r['name']+'。街区样板依据固定影像与航拍表现体量、屋面和场地关系；细部尺寸、窗格、植被形态及未见立面仍为估算。名称为区域描述。';records.append(record)
meta={'title':'北区街区样板','scope':'N07 and N21–N35 local art study, not full-campus replacement','coverage':'north-study','width':W,'height':H,'records':records,'regions':[{'id':'north','name':'北区街区','count':len(records),'bounds':[0,0,W,H]}],'camera':{'position':list(cam.location),'rotation_euler':list(cam.rotation_euler),'ortho_scale':cam.data.ortho_scale},'satellite_world_low':list(gp((0,1920))),'satellite_world_high':list(gp((1152,0))),'sources':sources,'roof_faces_world':faces,'samples':s.cycles.samples,'checks':{'source_roof_max_difference_m2':max(diffs),'paving_roof_intersection_m2':paved.intersection(allroof).area,'source_tree_centres_used':count,'tree_visual_groups':treegroups,'tree_prototype_count':len(protos),'sports_source_pixels':sportpolys,'source_files_unchanged':True},'academic_facade_interpretation':academic_facades,'dining_roof_source_bands':dining_bands,'manual_ground_source_pixels':{'forecourts':courts,'planting':beds,'roads':roadlines,'green_hardstanding':green_hardstanding,'grey_hardstanding':grey_hardstanding,'woodland':woodland_pixels},'features':['continuous traced plazas, grey and green hardstanding, planted seams and mineral margins','fixed-source branched crowns with folded leaf geometry and woodland/street/courtyard forms','subtle concrete roof courses and glazed roof grid','N31 stepped massing and framed longitudinal skylights','N32 source-aligned red/blue roof bands','N33 red and weathered oxide roof; detailed panel finish','N34/N35 slender window groups with separate courtyard elevations','N34 east top glazing ribbon and continuous glazed entrance bay','N34 unequal glazed roof pavilions','photo-led apartment balconies'],'limitations':'Native visual study. Dimensions and hidden details interpreted; reference campus differs; user visual acceptance remains pending.'}
if pilot:meta.update({'title':'北区食堂与教学楼局部样板','scope':'N31–N35 food hall, academic court and immediate surroundings','pilot':pilot_detail,'generation_commands':['/Applications/Blender.app/Contents/MacOS/Blender --background -t 4 --python scripts/north_study.py -- --pilot']})
(CACHE/'atlas.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2));assert size(CACHE/'atlas.json')<.5*1024**2
bridge=subprocess.Popen(['/opt/anaconda3/bin/python',str(Path(__file__)),'--stream'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,bufsize=1)
def send(c):
 bridge.stdin.write(json.dumps(c)+'\n');bridge.stdin.flush();a=bridge.stdout.readline();assert a and json.loads(a).get('ok'),a
send({'action':'begin'});s.render.use_border=True;s.render.use_crop_to_border=True;s.render.use_persistent_data=True
for row in range(2):
 for col in range(2):
  core=(col*W//2,row*H//2,(col+1)*W//2,(row+1)*H//2);x0=max(0,core[0]-20);y0=max(0,core[1]-20);x1=min(W,core[2]+20);y1=min(H,core[3]+20)
  s.render.border_min_x=(x0+.05)/W if x0 else 0;s.render.border_max_x=min(1,(x1+.05)/W);s.render.border_min_y=((H-y1)+.05)/H if H-y1 else 0;s.render.border_max_y=min(1,((H-y0)+.05)/H);s.render.filepath=str(CACHE/'render-tile.png');print('STUDY TILE',row,col,flush=True);bpy.ops.render.render(write_still=True);assert size(CACHE/'render-tile.png')<2*1024**2 and capacity()<192*1024**2;send({'action':'tile','core':core,'bounds':[x0,y0,x1,y1]})
send({'action':'finish'});bridge.stdin.close();assert bridge.wait()==0
for p,fingerprint in sources.items():assert sha(ROOT/p)==fingerprint
print('STUDY DONE',W,H,'trees',count,flush=True)
