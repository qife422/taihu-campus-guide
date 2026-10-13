"""Satellite and photo referenced campus reconstruction; see README for uncertainty."""
import bpy, bmesh, math, json, hashlib, random
from pathlib import Path
from mathutils import Vector
ROOT=Path(__file__).resolve().parent
META=json.loads((ROOT/'references/satellite-export.json').read_text())
EXT=META['extent']; LAT=31.578; SCALE=(EXT['xmax']-EXT['xmin'])/1800*math.cos(math.radians(LAT))
ORIGIN=(780,680)
bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
random.seed(19)
records=[]
def material(name,c,metal=0,rough=.6):
 m=bpy.data.materials.new(name); m.diffuse_color=(*c,1); m.use_nodes=True
 p=m.node_tree.nodes.get('Principled BSDF'); p.inputs['Base Color'].default_value=(*c,1); p.inputs['Roughness'].default_value=rough; p.inputs['Metallic'].default_value=metal
 return m
ivory=material('Warm mineral facade',(.72,.72,.65)); red=material('Photo observed terracotta bands',(.48,.125,.065)); trim=material('Pale facade frame',(.88,.85,.74)); roof=material('Weathered flat roof',(.19,.21,.20)); glass=material('Recessed blue glazing',(.075,.16,.20),.5,.2); metal=material('Metal frames',(.46,.49,.47),.6,.35)
grass=material('Grass',(.25,.36,.16)); asphalt=material('Asphalt',(.25,.27,.26)); paving=material('Walkway pavers',(.62,.60,.52)); stone=material('Lake retaining wall',(.46,.45,.35)); lake=material('Lake surface',(.085,.22,.20),.2,.14); brickroof=material('Red tiled roof',(.39,.10,.07)); solar=material('Photo observed solar array',(.055,.095,.16),.55,.24); bark=material('Tree trunk',(.23,.16,.095)); leaf=[material('Foliage '+str(i),c) for i,c in enumerate([(.12,.24,.075),(.18,.31,.095),(.23,.36,.12),(.11,.27,.105)])]
base=material('Model cut edge',(.20,.24,.20)); white=material('Road markings',(.78,.77,.66)); ink=material('Annotation',(.08,.13,.12))
def pt(p,z=0): return Vector(((p[0]-ORIGIN[0])*SCALE,(ORIGIN[1]-p[1])*SCALE,z))
def mesh(name,verts,faces,mat):
 me=bpy.data.meshes.new(name); me.from_pydata(verts,[],faces); me.update(); bm=bmesh.new(); bm.from_mesh(me); bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces)); bm.to_mesh(me); bm.free()
 ob=bpy.data.objects.new(name,me); bpy.context.collection.objects.link(ob); ob.data.materials.append(mat); return ob

def polygon(name,ps,z,h,mat,record=False):
 n=len(ps); ob=mesh(name,[pt(p,z) for p in ps]+[pt(p,z+h) for p in ps],[tuple(reversed(range(n))),tuple(range(n,2*n))]+[(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)],mat)
 if record:
  ob['source']='references/satellite.jpg'; ob['geometry_status']='manually traced visible roof/surface; not surveyed'; ob['height_status']='photo estimate; not measured'
  records.append(dict(id=name,pixel_outline=ps,height_m_estimate=h,base_z=z,source='satellite.jpg',status='photo_supported_manual_reconstruction'))
 return ob

def box(name,loc,size,mat,rot=0):
 x,y,z=size; vs=[(-x/2,-y/2,-z/2),(x/2,-y/2,-z/2),(x/2,y/2,-z/2),(-x/2,y/2,-z/2),(-x/2,-y/2,z/2),(x/2,-y/2,z/2),(x/2,y/2,z/2),(-x/2,y/2,z/2)]
 ob=mesh(name,vs,[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)],mat); ob.location=loc; ob.rotation_euler.z=rot; return ob

def segment(name,a,b,width,height,z,mat,offset=0):
 a,b=pt(a),pt(b); v=b-a; n=Vector((-v.y,v.x,0)).normalized(); center=(a+b)/2+n*offset; center.z=z+height/2
 return box(name,center,(v.length,width,height),mat,math.atan2(v.y,v.x))

def strip(name,ps,width,z,mat,height=.045):
 for i,(a,b) in enumerate(zip(ps,ps[1:])): segment(name+str(i),a,b,width,height,z+i*.0002,mat)

def rect(name,x1,y1,x2,y2,z,h,mat,record=False): return polygon(name,[(x1,y1),(x2,y1),(x2,y2),(x1,y2)],z,h,mat,record)

def windows(name,a,b,levels,step=3.3,start=1.0,bay=3.1,wallmat=ivory,out=.09,windowh=1.9):
 av,bv=pt(a),pt(b); v=bv-av; length=v.length; tangent=v.normalized(); normal=Vector((-tangent.y,tangent.x,0)); ang=math.atan2(v.y,v.x); count=max(1,round(length/bay)); spacing=length/count
 for floor in range(levels):
  for i in range(count):
   pos=av+tangent*(spacing*(i+.5))+normal*out; pos.z=start+floor*step+windowh/2
   box(name+' frame',pos,(spacing*.71,.18,windowh+.18),trim,ang)
   pp=pos+normal*(.11 if out>=0 else -.11); box(name+' glass',pp,(spacing*.64,.055,windowh),glass,ang)
   box(name+' mullion',pp+normal*(.04 if out>=0 else -.04),(.045,.05,windowh),metal,ang)
   sill=pos+normal*.13; sill.z-=windowh/2+.06; box(name+' sill',sill,(spacing*.75,.32,.10),trim,ang)

def parapet(name,ps,z,mat=trim,h=.6): strip(name,ps+[ps[0]],.23,z,mat,h)
def rooflines(name,ps,z):
 polygon(name+' slab',ps,z,.18,roof); parapet(name,ps,z+.18)
def note(text,p,z=0,size=3):
 cv=bpy.data.curves.new(text,'FONT'); cv.body=text; cv.align_x='CENTER'; cv.size=size; cv.extrude=.006; ob=bpy.data.objects.new(text,cv); bpy.context.collection.objects.link(ob); ob.location=pt(p,z); ob.data.materials.append(ink)

# Study boundary is a cropped review area, never the campus boundary.
rect('Study plinth',300,150,1280,1180,-2,2,base)
rect('Ground',300,150,1280,1180,0,.06,grass)
# Paths and roads digitised from the satellite surface, varying widths are approximations.
roads=[([(342,153),(316,375),(291,604),(275,878),(290,1090),(303,1177)],11), ([(1246,165),(1244,396),(1246,657),(1237,765),(1199,923),(1150,1108),(1080,1150),(520,1115)],12), ([(692,421),(583,421),(404,423),(352,453),(341,780),(324,894)],7), ([(748,155),(755,279),(755,448)],8), ([(786,258),(786,375),(786,479)],5), ([(648,996),(810,1005),(1089,1007)],9)]
for i,(p,w) in enumerate(roads): strip('Road '+str(i),p,w,.07+i*.005,asphalt,.04)
rect('South entrance forecourt',593,981,1110,1142,.11,.04,paving)
polygon('Rear courtyard paving',[(617,799),(1148,716),(1142,983),(614,991)],.07,.025,paving)
rect('West parking pavement',304,905,567,1177,.09,.035,asphalt)
for yy in [927,969,1068,1118,1159]:
 for xx in range(325,552,17): strip('Parking stall',[(xx,yy),(xx,yy+28)],.12,.145,white)

waterpts=[(670,493),(702,497),(739,513),(786,539),(819,551),(859,555),(922,555),(950,570),(971,601),(979,634),(975,678),(960,713),(931,739),(903,748),(872,740),(839,741),(808,753),(777,775),(739,787),(698,785),(660,773),(629,755),(609,732),(600,702),(602,666),(613,622),(626,581),(635,545),(649,516)]
polygon('L01 lake traced shoreline',waterpts,.065,.04,lake,True)
# Retaining wall and promenade follow the visible bank; construction detail is simplified.
strip('Lake retaining wall',waterpts+[waterpts[0]],.7,.085,stone,.58)
# Walkway is on the landward side, scaled around its own center only as a bank offset approximation.
cx,cy=786,642
promenade=[(cx+(x-cx)*1.06,cy+(y-cy)*1.06) for x,y in waterpts]
strip('Lake walk',promenade+[promenade[0]],3.0,.08,paving)
strip('Bank railing top',waterpts+[waterpts[0]],.075,.91,metal,.075)
for a,b in zip(waterpts,waterpts[1:]+waterpts[:1]):
 length=(pt(b)-pt(a)).length
 for k in range(max(1,int(length/2.2))):
  t=k/max(1,int(length/2.2)); p=(a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t); box('Bank baluster',pt(p,.50),(.08,.08,.90),metal)

# B06: main facade and curved eastern end visible in the official Teaching 6 photograph.
main=[(650,907),(778,917),(878,922),(1078,936),(1088,939),(1095,946),(1097,958),(1092,970),(1084,977),(1072,980),(878,971),(778,965),(650,952)]
height=27.0
polygon('B06 Teaching 6 main',main,4.1,height-4.1,ivory,True)
# Seven upper levels and pilotis are photo interpretation, not a surveyed floor schedule.
front=[(650,952),(778,965),(878,971),(1072,980),(1084,977),(1092,970),(1097,958),(1095,946),(1088,939)]
for level in range(8):
 z=4.1+level*3.24
 strip('B06 terracotta horizontal band',front,.75,z,red,1.0 if level<7 else .85)
 strip('B06 floor slab edge',front,1.8,z-.14,trim,.18)
for a,b in zip(front,front[1:]):
 # out is negative because the traced front line runs west-to-east in image space.
 windows('B06 south-east',a,b,7,step=3.24,start=5.2,bay=3.0,out=-.12,windowh=1.90)
# Bottom column arcade visible in source; bay spacing follows the interpreted facade rhythm.
column_positions=set()
for a,b in zip(front[:4],front[1:4]):
 av,bv=pt(a),pt(b); v=bv-av; n=max(1,round(v.length/5.2))
 for j in range(n+1):
  pos=av+v*j/n; pos.z=2.05
  key=tuple(round(c,5) for c in pos)
  if key not in column_positions:
   column_positions.add(key); box('B06 ground column',pos,(.7,.7,4.1),ivory)
rooflines('B06 roof',main,27.0)
# Central raised roof and rooftop service volumes visible in satellite; heights estimated.
center=[(779,916),(878,922),(878,971),(779,965)]
polygon('B06 central raised block',center,27.2,2.7,red,True); rooflines('B06 central cap',center,29.9)
for x,y,w,d in [(670,916,14,12),(754,923,11,13),(920,938,14,11)]: rect('B06 visible roof service volume',x,y,x+w,y+d,27.2,1.3,ivory)
# Rooftop rib rhythm visible in the satellite, construction spacing approximate.
for a,b in [((652,914),(776,923)),((882,930),(1078,944))]:
 count=round((pt(b)-pt(a)).length/3.7)
 for i in range(count):
  t=(i+.5)/count; x=a[0]+(b[0]-a[0])*t; y=a[1]+(b[1]-a[1])*t
  strip('B06 roof rib',[(x,y),(x-2,y+32)],.18,27.4,metal,.16)
# Connected lower wings traced separately, with heights treated as estimates.
west=[(621,857),(646,857),(646,822),(733,824),(733,868),(670,863),(670,911),(649,907),(649,945),(621,941)]
east=[(1014,925),(1017,823),(976,818),(976,774),(1040,773),(1043,779),(1115,780),(1116,823),(1099,825),(1093,934)]
for name,ps,h in [('B06 west lower wing',west,10.2),('B06 east lower wing',east,10.2)]:
 polygon(name,ps,.08,h,red,True); rooflines(name,ps,h+.08)
 for a,b in zip(ps,ps[1:]+ps[:1]):
  if (pt(b)-pt(a)).length>5: windows(name,a,b,3,step=3.2,start=1.1,bay=3.0,out=.12)
# Semi-circular rear glazed entrance canopy is visible in satellite.
canopy=[(837+54*math.cos(math.pi+i*math.pi/40),915+54*math.sin(math.pi+i*math.pi/40)) for i in range(41)]
polygon('B06 rear fan canopy',canopy,7.6,.18,glass,True)
for i in range(0,41,4): strip('Canopy radial frame',[(837,915),canopy[i]],.13,7.82,metal,.12)
strip('Canopy curved edge',canopy,.18,7.8,metal,.18)
# Footprint-visible entrance apron, fountain basin and two lawns; no invented statue.
for x1,y1,x2,y2 in [(601,1013,738,1090),(934,1030,1075,1110)]:
 rect('Entrance lawn',x1,y1,x2,y2,.17,.10,grass)
ring=[(833+48*math.cos(math.pi+i*math.pi/40),1110+48*math.sin(math.pi+i*math.pi/40)) for i in range(41)]
strip('Visible semicircular entrance basin',ring,1.3,.20,stone,.40)

# West courtyard building: roofs, solar arrays, facade rhythm supported by campus-aerial.jpg.
u=[(381,248),(426,254),(423,339),(630,356),(637,286),(687,290),(683,420),(379,390)]
north=[(387,161),(697,196),(693,248),(380,213)]
for name,ps in [('B07 west courtyard wings',u),('B07 north wing',north)]:
 polygon(name,ps,.08,20.4,red,True)
 for a,b in zip(ps,ps[1:]+ps[:1]):
  windows(name,a,b,6,step=3.3,start=1.3,bay=3.0,out=.12)
  strip('B07 cornice',[a,b],.48,20.5,trim,.45)
# Pitched roof segments fitted to visible roof strips; pitches are photo estimates.
def pitched(name,a,b,width,z,rise):
 av,bv=pt(a,z),pt(b,z); v=(bv-av).normalized(); n=Vector((-v.y,v.x,0))*width/2
 verts=[av+n,av-n,bv-n,bv+n,av+Vector((0,0,rise)),bv+Vector((0,0,rise))]
 mesh(name,verts,[(0,3,5,4),(1,4,5,2),(0,4,1),(3,2,5)],brickroof)
 # Fine eave and ridge geometry supports clear close views without a baked image.
 strip(name+' ridge',[a,b],.14,z+rise,brickroof,.14)
for name,a,b,w in [('north',(391,188),(690,222),15),('west',(402,264),(400,365),14),('south',(397,365),(663,389),14),('east',(662,295),(660,390),14)]: pitched('B07 '+name+' tiled roof',a,b,w,21,2.1)
for x,y,w in [(407,192,28),(496,203,37),(590,213,50),(443,374,30),(502,380,28),(588,388,46),(666,311,14)]:
 ob=rect('B07 observed solar panel group',x,y,x+w,y+12,23.15,.10,solar)
 for xx in range(int(x),int(x+w)+1,5): strip('Solar module seam',[(xx,y),(xx,y+12)],.025,23.27,metal,.02)
for x,y in [(408,174),(477,185),(546,194),(620,202),(407,275),(447,355),(515,362),(606,375),(651,303)]: rect('B07 visible roof housing',x,y,x+16,y+11,22.0,1.4,ivory)

# Northeast academic group: separate tall bar, lower courtyard wings and connecting bridges.
bar=[(838,280),(1218,301),(1219,352),(838,335)]
low=[(845,424),(1086,441),(1084,547),(1154,551),(1158,384),(1216,386),(1210,619),(1040,611),(1040,483),(846,478)]
for name,ps,h,levels in [('B08 north academic bar',bar,23.1,7),('B08 lakeside courtyard wings',low,13.2,4)]:
 polygon(name,ps,.08,h,ivory,True); rooflines(name,ps,h+.08)
 for a,b in zip(ps,ps[1:]+ps[:1]):
  if (pt(b)-pt(a)).length>8: windows(name,a,b,levels,step=3.25,start=1.05,bay=2.8,out=.13,windowh=1.75)
  strip(name+' wall base',[a,b],.2,.25,red,.65)
for ps in [[(925,336),(946,337),(942,427),(923,426)],[(1155,352),(1170,353),(1170,391),(1155,390)]]: polygon('B08 bridge',ps,7,.35,trim)
# Glass-roof segment visible along the east side.
rect('B08 glazed roof segment',1171,449,1214,543,13.6,.18,glass)
for yy in range(449,545,8): strip('B08 roof glazing frame',[(1171,yy),(1214,yy)],.12,13.84,metal,.10)

# Canopy locations digitised from visible clusters; individual tree form remains illustrative.
TREE_POINTS=[(578,800),(598,806),(638,793),(736,805),(765,810),(1100,739),(1134,748),(1175,725),(1190,667),(1203,601),(986,632),(988,685),(990,712),(966,773),(773,487),(808,490),(842,500),(879,510),(917,528),(939,783),(934,811),(710,1001),(676,994),(1001,1007),(1053,1005),(1126,953),(1138,904),(1143,853),(618,962),(592,965),(609,889),(1140,566),(1130,627),(357,394),(360,324),(370,220),(728,264),(725,347),(732,397),(788,393),(800,456),(694,445),(626,448),(559,454),(519,457),(707,1138),(745,1140),(790,1143),(851,1145),(900,1148),(939,1148),(986,1147),(1021,1146)]
leaf_meshes=[]
for k in range(4):
 bm=bmesh.new(); bmesh.ops.create_icosphere(bm,subdivisions=2,radius=1.0)
 for v in bm.verts: v.co*=1+random.uniform(-.13,.13)
 me=bpy.data.meshes.new('Shared foliage mesh '+str(k)); bm.to_mesh(me); bm.free(); me.materials.append(leaf[k])
 for face in me.polygons: face.use_smooth=True
 leaf_meshes.append(me)
for idx,p in enumerate(TREE_POINTS):
 h=5.3+(idx%4)*.6; r=2.5+(idx%3)*.35
 box('Observed canopy '+str(idx)+' trunk',pt(p,h*.325),(.35,.35,h*.65),bark)
 for j,(dx,dy,dz,sc) in enumerate([(0,0,0,1),(-.8,.3,-.3,.72),(.7,-.5,.4,.76)]):
  ob=bpy.data.objects.new('Observed canopy '+str(idx),leaf_meshes[idx%4]); bpy.context.collection.objects.link(ob); ob.location=pt(p,h)+Vector((dx,dy,dz)); ob.scale=(r*sc,r*sc,r*sc*1.1)
print('Geometry created',len(bpy.data.objects),flush=True)

# Reference image is georeferenced and packed, toggle collection for visual alignment.
refcol=bpy.data.collections.new('REFERENCES - hidden for render'); bpy.context.scene.collection.children.link(refcol)
image=bpy.data.images.load(str(ROOT/'references/satellite.jpg')); image.pack()
ref=bpy.data.objects.new('Satellite reference 1800x1400',None); refcol.objects.link(ref); ref.empty_display_type='IMAGE'; ref.data=image; ref.empty_display_size=1800*SCALE; ref.location=pt((900,700),-.01); ref.hide_render=True; ref.hide_viewport=True
scene=bpy.context.scene; scene.unit_settings.system='METRIC'; scene.render.engine='CYCLES'; scene.cycles.samples=40; scene.cycles.use_denoising=True
scene.world.use_nodes=True; bg=scene.world.node_tree.nodes['Background']; bg.inputs['Color'].default_value=(.75,.80,.87,1); bg.inputs['Strength'].default_value=.6
bpy.ops.object.light_add(type='SUN',location=(0,0,200)); sun=bpy.context.object; sun.rotation_euler=(.45,-.55,-.5); sun.data.energy=2.1; sun.data.angle=.10
bpy.ops.object.camera_add(); cam=bpy.context.object; scene.camera=cam; cam.name='Campus orthographic camera'; cam.data.type='ORTHO'; cam.data.clip_end=2000
scene.render.resolution_x=3200; scene.render.resolution_y=2400; scene.render.resolution_percentage=100; scene.render.image_settings.file_format='PNG'; scene.view_settings.view_transform='AgX'
def aim(camera,position,target,scale): camera.location=position; camera.rotation_euler=(Vector(target)-camera.location).to_track_quat('-Z','Y').to_euler(); camera.data.ortho_scale=scale
# Slightly southeast: front facade and lakeside relationships are both visible.
aim(cam,(225,-370,350),(0,-5,0),485)
for screen in bpy.data.screens:
 for area in screen.areas:
  if area.type=='VIEW_3D':
   area.spaces.active.region_3d.view_perspective='CAMERA'; area.spaces.active.shading.color_type='MATERIAL'; area.spaces.active.overlay.show_overlays=False
bpy.ops.object.select_all(action='DESELECT'); bpy.context.preferences.filepaths.save_version=0
scene.render.filepath=str(ROOT/'central-campus.png'); bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'central-campus.blend')); bpy.ops.render.render(write_still=True)
aim(cam,(0,0,500),(0,0,0),500); scene.render.filepath=str(ROOT/'central-campus-plan.png'); bpy.ops.render.render(write_still=True)
aim(cam,(175,-235,140),pt((862,922),12),185); scene.render.resolution_x=2800; scene.render.resolution_y=1700; scene.render.filepath=str(ROOT/'teach6-detail.png'); bpy.ops.render.render(write_still=True)
# Export actual WGS84 polygons derived from the authoritative export extent.
def lnglat(p):
 x=EXT['xmin']+p[0]/1800*(EXT['xmax']-EXT['xmin']); y=EXT['ymax']-p[1]/1400*(EXT['ymax']-EXT['ymin'])
 return [math.degrees(x/6378137),math.degrees(2*math.atan(math.exp(y/6378137))-math.pi/2)]
def exterior_ring(points):
 ring=[lnglat(p) for p in points]
 origin=ring[0]
 area=sum((a[0]-origin[0])*(b[1]-origin[1])-(b[0]-origin[0])*(a[1]-origin[1]) for a,b in zip(ring,ring[1:]+ring[:1]))
 if area<0: ring.reverse()
 return ring+[ring[0]]
geo={'type':'FeatureCollection','features':[{'type':'Feature','properties':{k:v for k,v in r.items() if k!='pixel_outline'},'geometry':{'type':'Polygon','coordinates':[exterior_ring(r['pixel_outline'])]}} for r in records]}
(ROOT/'footprints.geojson').write_text(json.dumps(geo,ensure_ascii=False,indent=2))
(ROOT/'footprints.json').write_text(json.dumps({'coordinate_system':'reference image pixels, export extent in references/satellite-export.json','ground_m_per_pixel_approx':SCALE,'geometry_note':'roof edges; parallax not corrected; not surveyed ground footprints','features':records},ensure_ascii=False,indent=2))
manifest={'status':'satellite_and_photo_supported_review_model; not surveyed or school-approved','supersedes':'previous diagram-only massing at same filenames','blender_version':bpy.app.version_string,'method':'manual satellite tracing; photo interpreted facade and roof components; estimated vertical dimensions; procedural meshes rendered by Cycles','source_urls':{'satellite':'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer','teach6':'https://www.wxu.edu.cn/info/1111/57381.htm','aerial':'https://www.wxu.edu.cn/info/1111/57421.htm','lake':'https://zs.wxu.edu.cn/info/1371/3632.htm'},'uncertainties':['Satellite acquisition date unknown','Roof edges have perspective displacement','Floor heights and total heights estimated','Hidden facades use simplified continuation, not verified','Individual window module count estimated from rhythm','Tree positions from visible canopy clusters; species and crown shape illustrative','B07/B08 building names not yet verified','Cross-source chronology not established'],'artifacts':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.rglob('*') if p.is_file() and p.suffix in ['.py','.png','.jpg','.json','.geojson','.blend','.md'] and p.name!='manifest.json'}}
(ROOT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
print('DONE',len(records),'traced features;',len(bpy.data.objects),'objects;',SCALE,'m/pixel')
