"""Bake source-aligned road, path and land-cover display meshes.
Fixed images support the hardscape classification; this is not navigation validation.
"""
import sys,json,math,hashlib
from pathlib import Path
sys.path.insert(0,'/tmp/taihu-gis-deps')
from shapely.geometry import Polygon,LineString,box,Point
from shapely.ops import unary_union
from shapely import constrained_delaunay_triangles
from shapely.geometry.polygon import orient
from PIL import Image,ImageDraw,ImageFilter
import numpy as np
ROOT=Path(__file__).resolve().parent;D=json.loads((ROOT/'layout.json').read_text());M=json.loads((ROOT/'references/satellite-export.json').read_text());N=json.loads((ROOT/'references/north-extension.json').read_text());e=M['extent'];COS=math.cos(math.radians(31.578));OX=e['xmin']+600/1152*(e['xmax']-e['xmin']);OY=e['ymax']-850/1920*(e['ymax']-e['ymin']);LAND=D.get('landscape',{})
def pt(p,source='satellite'):
 m=N if source=='north-extension' else M;e=m['extent'];w,h=(1000,900) if source=='north-extension' else (1152,1920)
 return [(e['xmin']+p[0]/w*(e['xmax']-e['xmin'])-OX)*COS,(e['ymax']-p[1]/h*(e['ymax']-e['ymin'])-OY)*COS]
def poly(r):return Polygon([pt(p,r.get('source','satellite')) for p in r['outline']])
raw=[(name,LineString([pt(p) for p in ps]),w) for name,ps,w in D['roads']]+[(name,LineString([pt(p,'north-extension') for p in ps]),w) for name,ps,w in D['north_roads']]
roofpolys=[poly(r) for r in D['buildings']]
old=ROOT.parent/'central-campus';oe=json.loads((old/'references/satellite-export.json').read_text())['extent']
def cp(p):return ((oe['xmin']+p[0]/1800*(oe['xmax']-oe['xmin'])-OX)*COS,(oe['ymax']-p[1]/1400*(oe['ymax']-oe['ymin'])-OY)*COS)
central=[Polygon([cp(p) for p in r['pixel_outline']]) for r in json.loads((old/'footprints.json').read_text())['features']]
mask=unary_union(roofpolys+central+[poly(r) for r in D['surfaces'] if r['kind']=='water']).buffer(.35)
# Study import replaces all geometry in this exact source-pixel patch.
patch=Polygon([cp(p) for p in [(280,140),(1260,140),(1260,720),(1200,1030),(1100,1190),(280,1190)]])
walk_names=LAND.get('road_material_overrides',{});context_roads=set(LAND.get('source_context_road_names',[]))
asphalt_raw=unary_union([line.buffer(w/2,quad_segs=8,join_style='round',cap_style='flat') for name,line,w in raw if walk_names.get(name)!='paving' and name not in context_roads])
road_paving=unary_union([line.buffer(w/2+1.1,quad_segs=8,join_style='round',cap_style='flat') for name,line,w in raw if name not in context_roads])
clipped=asphalt_raw.intersection(mask).area
asphalt=asphalt_raw.difference(mask).difference(patch)
road_paving=road_paving.difference(mask).difference(patch)
grounds=unary_union([poly(r) for r in D['surfaces'] if r['kind']=='ground'])
woodland=unary_union([poly(r) for r in D['surfaces'] if r.get('role','').startswith('satellite-visible surrounding')])
context=grounds.buffer(24)
asphalt=asphalt.intersection(context);road_paving=road_paving.intersection(context)
# Exclude sports extents from automatic concrete detection.
sports=[]
for r in D['tracks']:
 c=r['center'];rad=r['wide']/2;half=(r['long']-r['wide'])/2;ang=math.radians(r['angle']);ps=[]
 for cy,start in [(half,0),(-half,math.pi)]:
  for i in range(49):
   a=start+i*math.pi/48;x=rad*math.cos(a);y=cy+rad*math.sin(a);ps.append(pt((c[0]+x*math.cos(ang)+y*math.sin(ang),c[1]+x*math.sin(ang)-y*math.cos(ang)),r.get('source','satellite')))
 sports.append(Polygon(ps))
for row in D['courts']:
 _,c,w,h,a=row[:5];src=row[5] if len(row)>5 else 'satellite';a=math.radians(a)
 sports.append(Polygon([pt((c[0]+x*math.cos(a)-y*math.sin(a),c[1]+x*math.sin(a)+y*math.cos(a)),src) for x,y in [(-w/2,-h/2),(w/2,-h/2),(w/2,h/2),(-w/2,h/2)]]))
sportsmask=unary_union(sports).buffer(.5)
# Raster evidence is converted into bounded, simplified surface polygons, not pasted as a ground photo.
# Conservative near-neutral light pixels; bounded closing/opening removes pixel noise before spatial exclusions.
classified=[];classified_stats=[]
for src,size in [('satellite',(1152,1920)),('north-extension',(1000,900))]:
 im=Image.open(ROOT/'references'/(src+'.jpg')).convert('RGB').resize(size);rgb=np.asarray(im,dtype=float);r,g,b=rgb[:,:,0],rgb[:,:,1],rgb[:,:,2];mean=(r+g+b)/3
 roi=Image.new('L',size);rd=ImageDraw.Draw(roi)
 for rec in D['surfaces']:
  if rec['kind']=='ground' and rec.get('source','satellite')==src and rec['id']!='adjacent-woodland':rd.polygon([tuple(p) for p in rec['outline']],fill=255)
 light=(np.abs(r-g)<13)&((g-b)<22)&((r-b)<28)&(mean>110)&(mean<230)&(np.asarray(roi)>0)
 raster=Image.fromarray((light*255).astype('uint8')).filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.MinFilter(7)).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3));binary=np.asarray(raster)>0
 # Coalesce equal horizontal runs across successive rows before union to avoid millions of cell boxes.
 active={};rects=[]
 for y,row in enumerate(binary):
  dif=np.diff(np.r_[False,row,False].astype('int8'));runs=list(zip(np.flatnonzero(dif==1),np.flatnonzero(dif==-1)));now={}
  for run in runs:now[run]=active.pop(run,y)
  for (x0,x1),y0 in active.items():a=pt((x0,y0),src);b=pt((x1,y),src);rects.append(box(a[0],b[1],b[0],a[1]))
  active=now
 for (x0,x1),y0 in active.items():a=pt((x0,y0),src);b=pt((x1,size[1]),src);rects.append(box(a[0],b[1],b[0],a[1]))
 geom=unary_union(rects).buffer(2.0,quad_segs=3).buffer(-2.0,quad_segs=3).buffer(-.8,quad_segs=3).buffer(.8,quad_segs=3).simplify(1.2,preserve_topology=True)
 geom=geom.difference(mask.buffer(1.0)).difference(patch).difference(sportsmask).difference(woodland)
 pieces=[g for g in (list(geom.geoms) if hasattr(geom,'geoms') else [geom]) if g.geom_type=='Polygon' and g.area>=35]
 pieces=[Polygon(g.exterior,[r for r in g.interiors if Polygon(r).area>=25]) for g in pieces];geom=unary_union(pieces).difference(mask.buffer(1.0)).difference(patch).difference(sportsmask).difference(woodland);classified.append(geom);classified_stats.append({'source':src,'neutral_light_pixels':int(binary.sum()),'surface_area_m2':round(geom.area,2),'polygon_parts':len(pieces)})
 print('Classified source-visible paving',classified_stats[-1],flush=True)
manual=unary_union([poly(r) for r in LAND.get('paving_polygons',[])])
lawns=unary_union([poly(r) for r in LAND.get('lawn_polygons',[])])
paths=unary_union([LineString([pt(p,r.get('source','satellite')) for p in r['points']]).buffer(r['width_m']/2,quad_segs=6,join_style='round') for r in LAND.get('footpaths',[])])
all_paving=unary_union([road_paving,manual,paths,*classified]).difference(mask).difference(patch).difference(sportsmask).difference(lawns)
curbs=asphalt.buffer(.26).difference(asphalt).difference(mask).difference(patch)
# Aprons are extracted from source surfaces; no uniform guessed plaza is put around every building.
woodland=woodland.difference(patch)
def parts(g):return [p for p in (list(g.geoms) if hasattr(g,'geoms') else [g]) if p.geom_type=='Polygon' and not p.is_empty]
def bake(geom,z,h=0):
 vs=[];fs=[]
 for part in parts(geom):
  part=orient(part,sign=1);assert part.is_valid
  for t in constrained_delaunay_triangles(part).geoms:
   ps=list(t.exterior.coords)[:-1]
   if (ps[1][0]-ps[0][0])*(ps[2][1]-ps[0][1])-(ps[1][1]-ps[0][1])*(ps[2][0]-ps[0][0])<0:ps.reverse()
   k=len(vs);vs.extend([[x,y,z+h] for x,y in ps]);fs.append([k,k+1,k+2])
  if h:
   for ring in [part.exterior]+list(part.interiors):
    pp=list(ring.coords)
    for a,b in zip(pp,pp[1:]):
     k=len(vs);vs.extend([[a[0],a[1],z],[b[0],b[1],z],[b[0],b[1],z+h],[a[0],a[1],z+h]]);fs.append([k,k+1,k+2,k+3])
 # Reuse shared vertices and retain sub-millimetre coordinates; source imagery is metre-scale.
 unique=[];lookup={};remap=[]
 for v in vs:
  key=tuple(round(c,4) for c in v)
  if key not in lookup:lookup[key]=len(unique);unique.append(list(key))
  remap.append(lookup[key])
 clean=[];seen=set()
 for face in fs:
  mapped=[remap[i] for i in face];key=tuple(sorted(mapped))
  if len(set(mapped))<3 or key in seen:continue
  a,b,c=[unique[i] for i in mapped[:3]];u=[b[i]-a[i] for i in range(3)];v=[c[i]-a[i] for i in range(3)]
  cross=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
  if sum(t*t for t in cross)<1e-16:continue
  seen.add(key);clean.append(mapped)
 return dict(vertices=unique,faces=clean)
result={'method':'Fixed-source neutral-pixel paving classification + manually source-traced road corrections and garden paths; Shapely 2.1.2 union and triangulation. This is surface depiction, not a verified navigable graph.','source_hashes':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'layout.json',ROOT/'references/satellite.jpg',ROOT/'references/north-extension.jpg']},'replace_objects':[name for name,_,_ in raw]+[r['id'] for r in D['surfaces'] if r['kind']=='ground'],'clipped_road_surface_m2':clipped,'source_paving_classification':classified_stats,'central_patch_world_xy':[list(p) for p in patch.exterior.coords],'geometry_checks':{'road_roof_water_intersection_m2':asphalt.intersection(mask).area,'road_study_patch_intersection_m2':asphalt.intersection(patch).area,'paving_roof_water_intersection_m2':all_paving.intersection(mask).area},'layers':[]}
for name,g,z,h,m in [('Site ground union',grounds.difference(patch),-.20,.20,'grass'),('Woodland floor',woodland,.012,0,'woodland'),('Road paving union',all_paving,.045,.02,'paving'),('Road asphalt union',asphalt,.105,.025,'asphalt'),('Road mineral curbs',curbs,.14,.10,'curb'),('Source planting beds',lawns.difference(mask),.09,.04,'grass')]:
 result['layers'].append(dict(name=name,material=m,area_m2=round(g.area,2),**bake(g,z,h)))
# Hybrid context follows the observed reference-map approach: source imagery only outside modeled parcels.
ring=grounds.buffer(48,join_style='round').difference(grounds)
north_coverage=Polygon([pt(p,'north-extension') for p in [(0,0),(1000,0),(1000,900),(0,900)]])
main_coverage=Polygon([pt(p) for p in [(0,0),(1152,0),(1152,1920),(0,1920)]])
yjoin=pt((0,90))[1];north_coverage=north_coverage.intersection(box(-10000,yjoin,10000,10000));main_coverage=main_coverage.difference(north_coverage)
result['context_layers']=[]
for src,coverage in [('satellite',main_coverage),('north-extension',north_coverage)]:
 g=ring.intersection(coverage);result['context_layers'].append({'name':src+' outside-campus context','source':src,'scope':'georeferenced photo outside modeled parcels only; not modeled neighboring buildings',**bake(g,-.025,0)})
(ROOT/'roads.json').write_text(json.dumps(result,separators=(',',':'))+'\n')
print('Baked source-aligned surfaces;',sum(len(r['faces']) for r in result['layers']),'faces; road overlap before clipping',round(clipped,1),'m2',flush=True)
