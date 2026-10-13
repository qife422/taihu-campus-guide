"""Validate source polygons, export WGS84 and sample visible green canopy positions.
Requires Pillow for satellite pixel inspection; validation uses only the standard library.
"""
import json,math,random,hashlib,sys
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parent;D=json.loads((ROOT/'layout.json').read_text())
MAIN=json.loads((ROOT/'references/satellite-export.json').read_text());NORTH=json.loads((ROOT/'references/north-extension.json').read_text());OLD=ROOT.parent/'central-campus';OM=json.loads((OLD/'references/satellite-export.json').read_text())
COS=math.cos(math.radians(31.578))
def merc(p,source='satellite'):
 m=NORTH if source=='north-extension' else (OM if source=='central' else MAIN);e=m['extent'];w,h=(1000,900) if source=='north-extension' else ((1800,1400) if source=='central' else (1152,1920))
 return (e['xmin']+p[0]/w*(e['xmax']-e['xmin']),e['ymax']-p[1]/h*(e['ymax']-e['ymin']))
def mainpixel(m):
 e=MAIN['extent'];return [(m[0]-e['xmin'])/(e['xmax']-e['xmin'])*1152,(e['ymax']-m[1])/(e['ymax']-e['ymin'])*1920]
def ll(p,source='satellite'):
 x,y=merc(p,source);return [math.degrees(x/6378137),math.degrees(2*math.atan(math.exp(y/6378137))-math.pi/2)]
def area(ps):
 ox,oy=ps[0];return sum((a[0]-ox)*(b[1]-oy)-(b[0]-ox)*(a[1]-oy) for a,b in zip(ps,ps[1:]+ps[:1]))/2

def inside(p,ps):
 x,y=p;hit=False
 for a,b in zip(ps,ps[1:]+ps[:1]):
  if (a[1]>y)!=(b[1]>y) and x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:hit=not hit
 return hit

def orient(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
def on(a,b,p):return abs(orient(a,b,p))<1e-8 and min(a[0],b[0])-1e-8<=p[0]<=max(a[0],b[0])+1e-8 and min(a[1],b[1])-1e-8<=p[1]<=max(a[1],b[1])+1e-8
def cross(a,b,c,d):return orient(a,b,c)*orient(a,b,d)<0 and orient(c,d,a)*orient(c,d,b)<0 or any([on(a,b,c),on(a,b,d),on(c,d,a),on(c,d,b)])
def ring(ps,src):
 r=[ll(p,src) for p in ps]
 if area(r)<0:r.reverse()
 return r+[r[0]]
features=[];checks=[]
for r in D['buildings']+D['surfaces']:
 ps=r['outline'];n=len(ps);assert n>=3 and abs(area(ps))>.01,r['id'];assert len(set(map(tuple,ps)))==n,r['id']
 for i in range(n):
  for j in range(i+1,n):
   if j==i+1 or i==0 and j==n-1:continue
   assert not cross(ps[i],ps[(i+1)%n],ps[j],ps[(j+1)%n]),(r['id'],i,j)
 src=r.get('source','satellite');rr=ring(ps,src);assert area(rr[:-1])>0
 props={k:v for k,v in r.items() if k!='outline'};props['source']=src
 features.append({'type':'Feature','properties':props,'geometry':{'type':'Polygon','coordinates':[rr]}})
 checks.append({'id':r['id'],'simple_polygon':True,'ccw':True,'vertices':n})
for r in json.loads((OLD/'footprints.json').read_text())['features']:
 features.append({'type':'Feature','properties':{**{k:v for k,v in r.items() if k!='pixel_outline'},'source':'central-campus/footprints.json'},'geometry':{'type':'Polygon','coordinates':[ring(r['pixel_outline'],'central')]}})
for src,paths in [('satellite',D['roads']),('north-extension',D['north_roads'])]:
 for name,ps,w in paths:features.append({'type':'Feature','properties':{'name':name,'kind':'road','source':src,'width_estimate_m':w,'navigation_status':'unverified display alignment; not a routable network','modeled_surface':name not in D.get('landscape',{}).get('source_context_road_names',[]),'alignment_status':'historical approximation; use fixed source imagery' if name in D.get('landscape',{}).get('source_context_road_names',[]) else 'source interpreted, roof-masked display surface'},'geometry':{'type':'LineString','coordinates':[ll(p,src) for p in ps]}})
for rec in D['courts']:
 name,c,w,h,a=rec[:5];src=rec[5] if len(rec)>5 else 'satellite';a=math.radians(a);ps=[]
 for x,y in [(-w/2,-h/2),(w/2,-h/2),(w/2,h/2),(-w/2,h/2)]:ps.append([c[0]+x*math.cos(a)-y*math.sin(a),c[1]+x*math.sin(a)+y*math.cos(a)])
 features.append({'type':'Feature','properties':{'name':name,'kind':'court-group','source':src,'outline_status':'extent fitted from imagery'},'geometry':{'type':'Polygon','coordinates':[ring(ps,src)]}})

for r in D['gates']:features.append({'type':'Feature','properties':{k:v for k,v in r.items() if k!='position'},'geometry':{'type':'Point','coordinates':ll(r['position'],r.get('source','satellite'))}})
# Track rings use the same stadium geometry as Blender, exported in image coordinates.
for r in D['tracks']:
 ps=[];rad=r['wide']/2;half=(r['long']-r['wide'])/2;ang=math.radians(r['angle']);c=r['center']
 for cy,start in [(half,0),(-half,math.pi)]:
  for i in range(49):
   a=start+i*math.pi/48;x=rad*math.cos(a);y=cy+rad*math.sin(a);ps.append([c[0]+x*math.cos(ang)+y*math.sin(ang),c[1]+x*math.sin(ang)-y*math.cos(ang)])
 features.append({'type':'Feature','properties':{**r,'kind':'track','outline_status':'curve fitted to visible extent'},'geometry':{'type':'Polygon','coordinates':[ring(ps,r.get('source','satellite'))]}})
(ROOT/'campus.geojson').write_text(json.dumps({'type':'FeatureCollection','features':features},ensure_ascii=False,indent=2)+'\n')
if '--export-only' in sys.argv:
 report=json.loads((ROOT/'validation.json').read_text());report['polygon_checks']=checks;report['geojson_feature_count']=len(features);report['scene']={'status':'pending current scene validation'};(ROOT/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print('Exported',len(features),'GeoJSON features; refreshed source polygon checks');sys.exit(0)
# Deterministic selection of green pixels, excluded from traced roofs, water, and roads.
all_polys=[[mainpixel(merc(p,r.get('source','satellite'))) for p in r['outline']] for r in D['buildings']]
for r in json.loads((OLD/'footprints.json').read_text())['features']:all_polys.append([mainpixel(merc(p,'central')) for p in r['pixel_outline']])
for r in D['surfaces']:
 if r['kind'] in ('water','parking','paving','grass'):all_polys.append([mainpixel(merc(p,r.get('source','satellite'))) for p in r['outline']])
for feature in features:
 if feature['properties'].get('kind')=='track':
  all_polys.append([mainpixel((6378137*math.radians(lon),6378137*math.log(math.tan(math.pi/4+math.radians(lat)/2)))) for lon,lat in feature['geometry']['coordinates'][0][:-1]])
for rec in D['courts']:
 _,c,w,h,a=rec[:5];src=rec[5] if len(rec)>5 else 'satellite'
 rad=math.radians(a);ps=[]
 for x,y in [(-w/2,-h/2),(w/2,-h/2),(w/2,h/2),(-w/2,h/2)]:ps.append([c[0]+x*math.cos(rad)-y*math.sin(rad),c[1]+x*math.sin(rad)+y*math.cos(rad)])
 all_polys.append([mainpixel(merc(p,src)) for p in ps])
def distance(p,a,b):
 x,y=p;dx=b[0]-a[0];dy=b[1]-a[1];s=dx*dx+dy*dy;t=max(0,min(1,((x-a[0])*dx+(y-a[1])*dy)/s)) if s else 0;return math.hypot(x-a[0]-t*dx,y-a[1]-t*dy)
def excluded(p):
 for ps in all_polys:
  if min(a[0] for a in ps)-5<=p[0]<=max(a[0] for a in ps)+5 and min(a[1] for a in ps)-5<=p[1]<=max(a[1] for a in ps)+5:
   if inside(p,ps) or min(distance(p,a,b) for a,b in zip(ps,ps[1:]+ps[:1]))<4:return True
 for _,ps,w in D['roads']:
  if any(distance(p,a,b)<w/2+2 for a,b in zip(ps,ps[1:])):return True
 return False
random.seed(47);trees=[]
for src,size in [('satellite',(1152,1920)),('north-extension',(1000,900))]:
 im=Image.open(ROOT/'references'/(src+'.jpg')).convert('RGB').resize(size);boundary=[r['outline'] for r in D['surfaces'] if r['kind']=='ground' and r.get('source','satellite')==src]
 spacing=10 if src=='satellite' else 20
 for y in range(8,size[1]-8,spacing):
  for x in range(8,size[0]-8,spacing):
   p=[x+random.randint(-3,3),y+random.randint(-3,3)]
   if not any(inside(p,ps) for ps in boundary):continue
   rgb=im.getpixel(tuple(p));red,green,blue=rgb
   if not (green>red*1.08 and green>blue*1.1 and 25<green<155):continue
   mp=mainpixel(merc(p,src))
   if src=='north-extension' and mp[1]>90:continue
   if excluded(mp):continue
   local=[im.getpixel((p[0]+dx,p[1]+dy))[1] for dx,dy in [(-3,0),(3,0),(0,-3),(0,3),(0,0)]]
   if max(local)-min(local)<12:continue
   trees.append({'position':p,'source':src,'height':round(random.uniform(5,9),1),'radius':round(random.uniform(2.7,4.2),1)})
D['trees']=trees;(ROOT/'layout.json').write_text(json.dumps(D,ensure_ascii=False,indent=2)+'\n')
report={'status':'passed','scope':'polygon topology and source transforms, not surveyed accuracy','buildings':len(D['buildings']),'central_source_features':10,'tracks':len(D['tracks']),'trees':len(trees),'checks':checks}
(ROOT/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
rows=['# 建筑轮廓与高度估算表','','高度由用户授权估算。层数为建模取值，未获得逐栋实测；“北区公寓”等是区域描述，不能当作官方楼号。表中主影像位置是缩至 1152×1920 后的检查坐标，北端影像为原始 1000×900 像素。','','| 编号 | 名称 / 区域描述 | 层数取值 | 檐口高度 m | 估算范围 m | 屋顶 | 影像依据 |','|---|---|---:|---:|---|---|---|']
for r in D['buildings']:rows.append(f"| {r['id']} | {r['name']} | {r['floors_estimate']} | {r['height_estimate_m']} | {r['height_range_m'][0]}–{r['height_range_m'][1]} | {r['roof']} | {r['source']} |")
rows+=['','中央样板复用：B06 六号教学楼主楼 27m、中部屋顶约 30m、低翼 10.2m；B07 湖西庭院约 20.4m；B08 北部长条约 23.1m、湖侧翼约 13.2m。均为照片推断，详见 central-campus/README.md。','', '需要继续人工核对的主要信息是官方楼号/用途对应、不同年代的改扩建；用户已经允许自主确定高度，因此缺少实测高度不作为停工条件。']
(ROOT/'建筑对应表.md').write_text('\n'.join(rows)+'\n')
print('Validated',len(checks),'polygons;',len(features),'GeoJSON features;',len(trees),'canopy samples')
