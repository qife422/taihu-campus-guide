"""Memory-bounded 8K Blender rendering: overlapping tiles, assembled by assemble.py.
Does not regenerate or alter the saved model. Tiles are bounded temporary outputs.
"""
import bpy,json,math,sys,subprocess,hashlib
from pathlib import Path
from mathutils import Vector,Quaternion
ROOT=Path(__file__).resolve().parent;CACHE=Path('/tmp/taihu-full/detail-tiles' if '--detail' in sys.argv else '/tmp/taihu-full/tiles');CACHE.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(ROOT/'campus.blend'))
s=bpy.context.scene;cam=s.camera;bridge=subprocess.Popen(['/opt/anaconda3/bin/python',str(ROOT/'assemble.py'),'--stream'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,bufsize=1)
def send(command):
 bridge.stdin.write(json.dumps(command)+'\n');bridge.stdin.flush();answer=bridge.stdout.readline();assert answer and json.loads(answer).get('ok'),answer
s.render.threads_mode='FIXED';s.render.threads=2 if '--detail' in sys.argv else 4;s.cycles.samples=24;s.cycles.use_denoising=True;s.render.use_persistent_data=True;s.render.image_settings.compression=100
s.render.use_border=True;s.render.use_crop_to_border=True
bpy.context.view_layer.update();bounds=[o.matrix_world@Vector(c) for o in s.objects if o.type=='MESH' and not o.hide_render for c in o.bound_box]
manifest=[]
views=[('campus',8192,4608),('campus-plan',8192,4096)]
if '--detail' in sys.argv:views=[('campus-detail',3200,2000)]
for name,W,H in views:
 s.render.resolution_x=W;s.render.resolution_y=H;s.render.resolution_percentage=100
 if name=='campus':
  bpy.context.view_layer.update();inv=cam.matrix_world.inverted();ps=[inv@p for p in bounds];xs=[p.x for p in ps];ys=[p.y for p in ps];cam.location+=cam.matrix_world.to_3x3()@Vector(((min(xs)+max(xs))/2,(min(ys)+max(ys))/2,0));cam.data.ortho_scale=max(max(xs)-min(xs),(max(ys)-min(ys))*W/H)*1.10
 if name=='campus-plan':
  minx=min(p.x for p in bounds);maxx=max(p.x for p in bounds);miny=min(p.y for p in bounds);maxy=max(p.y for p in bounds);target=Vector(((minx+maxx)/2,(miny+maxy)/2,0));cam.location=target+Vector((0,0,4000));q=(target-cam.location).to_track_quat('-Z','Y');cam.rotation_euler=(q@Quaternion((0,0,1),math.pi/2)).to_euler();bpy.context.view_layer.update();inv=cam.matrix_world.inverted();ps=[inv@p for p in bounds];xs=[p.x for p in ps];ys=[p.y for p in ps];cam.location+=cam.matrix_world.to_3x3()@Vector(((min(xs)+max(xs))/2,(min(ys)+max(ys))/2,0));cam.data.ortho_scale=max(max(xs)-min(xs),(max(ys)-min(ys))*W/H)*1.10;s.cycles.samples=16
 if name=='campus-detail':
  target=Vector((40,420,10));cam.location=target+Vector((500,-320,470));cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.ortho_scale=450;s.cycles.samples=32
 view={'name':name,'width':W,'height':H,'tiles':[],'samples':s.cycles.samples,'overlap_pixels':32}
 send({'action':'begin','name':name,'width':W,'height':H})
 grid=4 if name!='campus-detail' else 2
 for row in range(grid):
  for col in range(grid):
   core=(col*W//grid,row*H//grid,(col+1)*W//grid,(row+1)*H//grid)
   x0=max(0,core[0]-32);y0=max(0,core[1]-32);x1=min(W,core[2]+32);y1=min(H,core[3]+32)
   # Blender's border coordinates use a bottom-left origin, PNG uses top-left.
   s.render.border_min_x=(x0+.05)/W if x0 else 0;s.render.border_max_x=min(1,(x1+.05)/W)
   s.render.border_min_y=((H-y1)+.05)/H if H-y1 else 0;s.render.border_max_y=min(1,((H-y0)+.05)/H)
   path=Path('/tmp/taihu-full/render-tile.png');s.render.filepath=str(path)
   print('RENDER TILE',name,row,col,flush=True);bpy.ops.render.render(write_still=True)
   send({'action':'tile','file':str(path),'core':core,'render_bounds':[x0,y0,x1,y1]})
   view['tiles'].append({'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'core':core,'render_bounds':[x0,y0,x1,y1]})
   assert path.stat().st_size<8*1024**2,'Single temporary tile budget reached'
 send({'action':'finish'});view['assembly']='streamed into in-memory canvas; tile hashes are generation transcript, individual tiles are not archived';view['output_sha256']=hashlib.sha256((ROOT/(name+'.png')).read_bytes()).hexdigest()
 manifest.append(view);(CACHE/'manifest.json').write_text(json.dumps(manifest,indent=2));print('VIEW FINISHED',name,flush=True)
bridge.stdin.close();assert bridge.wait()==0;print('All requested views rendered and assembled',flush=True)
