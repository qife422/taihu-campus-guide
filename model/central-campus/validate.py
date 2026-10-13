"""Validate geometry and image-to-WGS84 conversion without optional GIS dependencies."""
import json,math
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def twice_area(points):
 ox,oy=points[0]
 return sum((a[0]-ox)*(b[1]-oy)-(b[0]-ox)*(a[1]-oy) for a,b in zip(points,points[1:]+points[:1]))
def orient(a,b,c): return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
def on(a,b,p): return abs(orient(a,b,p))<1e-8 and min(a[0],b[0])-1e-8<=p[0]<=max(a[0],b[0])+1e-8 and min(a[1],b[1])-1e-8<=p[1]<=max(a[1],b[1])+1e-8
def intersects(a,b,c,d):
 o1,o2,o3,o4=orient(a,b,c),orient(a,b,d),orient(c,d,a),orient(c,d,b)
 return (o1*o2<0 and o3*o4<0) or any([on(a,b,c),on(a,b,d),on(c,d,a),on(c,d,b)])
def check():
 src=json.loads((ROOT/'footprints.json').read_text()); geo=json.loads((ROOT/'footprints.geojson').read_text()); ext=json.loads((ROOT/'references/satellite-export.json').read_text())['extent']; results=[]
 assert len(src['features'])==len(geo['features'])
 for record,feature in zip(src['features'],geo['features']):
  points=record['pixel_outline']; n=len(points); assert n>=3
  assert len(set(map(tuple,points)))==n,record['id']+' duplicated vertices'
  assert abs(twice_area(points))>1e-8
  for i in range(n):
   for j in range(i+1,n):
    if j==i+1 or (i==0 and j==n-1): continue
    assert not intersects(points[i],points[(i+1)%n],points[j],points[(j+1)%n]),f'{record["id"]} intersecting edges {i}/{j}'
  ring=feature['geometry']['coordinates'][0]; assert ring[0]==ring[-1]
  assert twice_area(ring[:-1])>0,record['id']+' exterior must be counterclockwise'
  assert feature['properties']['id']==record['id']
  recovered=[]
  for lon,lat in ring[:-1]:
   assert 120.219<lon<120.227 and 31.575<lat<31.581
   x=6378137*math.radians(lon); y=6378137*math.log(math.tan(math.pi/4+math.radians(lat)/2))
   recovered.append(((x-ext['xmin'])/(ext['xmax']-ext['xmin'])*1800,(ext['ymax']-y)/(ext['ymax']-ext['ymin'])*1400))
  error=max(min(math.dist(p,q) for q in recovered) for p in points)
  assert error<1e-5,record['id']+' coordinate round trip failed'
  results.append({'id':record['id'],'vertices':n,'simple_polygon':True,'ccw_exterior':True,'round_trip_error_pixels':error})
 return {'status':'passed','scope':'geometry consistency only; not physical accuracy or school approval','features':results}
if __name__=='__main__':
 print(json.dumps(check(),ensure_ascii=False,indent=2))
