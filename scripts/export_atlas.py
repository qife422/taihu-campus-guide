"""Export the reviewed central image, or stream native full-campus tiles into the atlas.
/opt/anaconda3/bin/python scripts/export_atlas.py
--stream is called by campus_atlas.py and receives begin/tile/finish JSON messages.
No complete PNG or persistent tile tree is created for a full-campus render.
"""
from pathlib import Path
import json,hashlib,math,datetime,sys,io
import numpy as np
from PIL import Image
sys.path.insert(0,'/tmp/taihu-gis-deps')
from shapely.geometry import Polygon
from shapely.ops import unary_union
ROOT=Path(__file__).resolve().parents[1];CACHE=Path('/tmp/taihu-full');OLD=ROOT/'model/central-campus';DEST=ROOT/'public/assets'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def export(im,meta,tiles=None,check_only=False):
 assert sha(ROOT/'model/campus/campus.blend')==meta['source_scene_sha256']
 assert sha(ROOT/'scripts/campus_atlas.py')==meta['generator_sha256']
 assert sha(OLD/'footprints.json')==meta['source_footprints_sha256']
 assert im.size==(meta['width'],meta['height'])
 full_scope=meta.get('coverage')=='campus'
 if full_scope:
  if not check_only:assert im.size==(7168,3072)
  assert sha(ROOT/'model/campus/layout.json')==meta['checks']['fixed_layout_sha256']
  assert sha(ROOT/'model/campus/roads.json')==meta['checks']['fixed_roads_sha256']
  refinement=meta.get('building_refinement',{})
  if refinement:
   assert sha(ROOT/'scripts/refine_buildings.py')==refinement['module_sha256']
   assert sha(OLD/'references/campus-aerial.jpg')==refinement['photo_sha256']
   for path,fingerprint in refinement.get('satellite_sha256',{}).items():assert sha(ROOT/path)==fingerprint
 elif not check_only:assert im.size==(2800,2400)
 # Reconstruct the camera independently and retain disconnected roofs and courtyard holes.
 rx,ry,rz=meta['camera']['rotation_euler'];sx,cx=math.sin(rx),math.cos(rx);sy,cy=math.sin(ry),math.cos(ry);sz,cz=math.sin(rz),math.cos(rz)
 rot=np.array([[cz,-sz,0],[sz,cz,0],[0,0,1]])@np.array([[cy,0,sy],[0,1,0],[-sy,0,cy]])@np.array([[1,0,0],[0,cx,-sx],[0,sx,cx]])
 position=np.array(meta['camera']['position']);scale=meta['camera']['ortho_scale'];w,h=im.size
 ext=json.loads((OLD/'references/satellite-export.json').read_text())['extent'];main=json.loads((ROOT/'model/campus/references/satellite-export.json').read_text())['extent'];north=json.loads((ROOT/'model/campus/references/north-extension.json').read_text())['extent'];cos=math.cos(math.radians(31.578));ox=main['xmin']+600/1152*(main['xmax']-main['xmin']);oy=main['ymax']-850/1920*(main['ymax']-main['ymin'])
 features=json.loads((OLD/'footprints.json').read_text())['features'];layout=json.loads((ROOT/'model/campus/layout.json').read_text());buildings={r['id']:r for r in layout['buildings']}
 def project_world(point):
  p=rot.T@(np.array(point,dtype=np.float32)-position)
  return [w*.5+p[0]*w/scale,h*.5-p[1]*w/scale]
 def source_world(q,z,source='central'):
  e,iw,ih=(ext,1800,1400) if source=='central' else (north,1000,900) if source=='north-extension' else(main,1152,1920)
  x=(e['xmin']+q[0]/iw*(e['xmax']-e['xmin'])-ox)*cos;y=(e['ymax']-q[1]/ih*(e['ymax']-e['ymin'])-oy)*cos
  return [x,y,z]
 def project(q,z,source='central'):
  return project_world(source_world(q,z,source))
 errors=[]
 for record in meta['records']:
  polys=[]
  roof_faces=meta.get('building_refinement',{}).get('roof_faces_world',{}).get(record['id'])
  if roof_faces:
   row=buildings[record['id']]
   expected=Polygon([source_world(q,0,row.get('source','satellite'))[:2] for q in row['outline']])
   actual=unary_union([Polygon([p[:2] for p in face]) for face in roof_faces])
   assert actual.hausdorff_distance(expected)<.001,record['id']
   for face in roof_faces:
    poly=Polygon([project_world(p) for p in face])
    if poly.is_valid and poly.area>.000001:polys.append(poly)
  elif record['id'] in buildings:
   row=buildings[record['id']];polys=[Polygon([project(q,row['height_estimate_m']+.45,row.get('source','satellite')) for q in row['outline']])]
  else:
   for f in features:
    if f['id'].startswith(record['id']):
     p=Polygon([project(q,f.get('base_z',0)+f.get('height_m_estimate',0)) for q in f['pixel_outline']])
     if p.is_valid:polys.append(p)
  union=unary_union(polys);parts=list(union.geoms) if hasattr(union,'geoms') else [union]
  old=unary_union([Polygon(ring) for ring in record['polygons']]);new=unary_union([Polygon(p.exterior) for p in parts]);errors.append(old.hausdorff_distance(new))
  record['polygons']=[[list(p.exterior.coords),*[list(r.coords) for r in p.interiors]] for p in parts]
  label=union.representative_point();record['anchor']=[label.x,label.y]
 assert max(errors)<.01,errors
 assert len(meta['records'])==(130 if full_scope else 3)
 meta['checks']['independent_projection_max_difference_px']=max(errors)
 meta['checks']['hotspot_geometry']='independently projected source roofs; all refined parts use their 3D roof faces checked against fixed XY outlines; retain courtyards and disconnected wings'
 if check_only:return {'projection_max_px':max(errors),'dimensions':im.size,'records':len(meta['records']),'refined_buildings':len(meta.get('building_refinement',{}).get('building_ids',[])),'web_outputs_modified':False}
 buf=io.BytesIO();im.save(buf,format='WEBP',quality=91,method=6);payload=buf.getvalue()
 meta['image_sha256']=hashlib.sha256(payload).hexdigest();meta['image_bytes']=len(payload);meta['format']='webp';meta['render_status']='generated_needs_visual_review';meta['updated']=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat();meta['exporter_sha256']=sha(Path(__file__))
 meta['generation_commands']=['Blender --background -t 4 --python scripts/campus_atlas.py -- --campus --final' if full_scope else 'Blender --background -t 4 --python scripts/campus_atlas.py -- --final','export_atlas.py --stream' if full_scope else '/opt/anaconda3/bin/python scripts/export_atlas.py']
 meta['visual_review']={'status':'pending','scope':'full-campus map' if full_scope else 'central-region map','remaining':['Native image and browser visual checks required before acceptance']}
 meta['frontend_validation']={'status':'pending'}
 meta['budget']={'output_files':2,'output_bytes_limit':8*1024**2,'source_amplification_limit':256,'model_outputs_modified':False}
 if tiles:
  meta['render_tiles']=tiles;meta['assembly']='8 overlapping native tiles, cropped and assembled in memory; no resized render, no persistent tile tree';meta.pop('candidate_path',None)
 else:meta['candidate_path_status']='temporary diagnostic PNG, not a sealed web deliverable'
 encoded=(json.dumps(meta,ensure_ascii=False,indent=2)+'\n').encode();sources=sum((ROOT/p).stat().st_size for p in ['scripts/campus_atlas.py','scripts/refine_buildings.py','scripts/export_atlas.py','src/CampusAtlas.jsx','src/campusAtlas.css'])
 assert len(payload)+len(encoded)<8*1024**2
 assert (len(payload)+len(encoded))/sources<256
 # All bytes and source checks are complete before replacing the two stable web assets.
 (DEST/'campus-atlas.webp').write_bytes(payload);(DEST/'campus-atlas.json').write_bytes(encoded)
 return {'image_bytes':len(payload),'projection_max_px':max(errors),'source_amplification':(len(payload)+len(encoded))/sources,'dimensions':im.size,'records':len(meta['records'])}

if '--stream' in sys.argv:
 meta=json.loads((CACHE/'atlas.json').read_text());canvas=None;tiles=[];covered=set();area=0
 for line in sys.stdin:
  command=json.loads(line)
  if command['action']=='begin':canvas=Image.new('RGB',(command['width'],command['height']))
  elif command['action']=='tile':
   path=Path(command['file']);im=Image.open(path).convert('RGB');a,b,c,d=command['render_bounds'];x0,y0,x1,y1=command['core'];assert im.size==(c-a,d-b)
   key=tuple(command['core']);assert key not in covered;covered.add(key);area+=(x1-x0)*(y1-y0);canvas.paste(im.crop((x0-a,y0-b,x1-a,y1-b)),(x0,y0));tiles.append({'core':command['core'],'render_bounds':command['render_bounds'],'sha256':sha(path)});im.close()
  elif command['action']=='finish':
   assert area==canvas.width*canvas.height and len(tiles)==8
   result=export(canvas,meta,tiles);canvas.close()
  print(json.dumps({'ok':True,'action':command['action']}),flush=True)
else:
 meta=json.loads((CACHE/'atlas.json').read_text());png=CACHE/'campus.png';assert meta['render_status']=='generated_needs_visual_review';assert sha(png)==meta['png_sha256'];print(json.dumps(export(Image.open(png),meta,check_only='--check' in sys.argv),ensure_ascii=False))
