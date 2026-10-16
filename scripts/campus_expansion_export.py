"""Assemble eight native tiles in memory, verify and replace stable atlas assets."""
from pathlib import Path
import sys,json,hashlib,math,io,datetime
import numpy as np
from PIL import Image
sys.path.insert(0,'/tmp/taihu-gis-deps')
from shapely.geometry import Polygon
from shapely.ops import unary_union
ROOT=Path(__file__).resolve().parents[1];CACHE=Path('/tmp/taihu-full');OUT=ROOT/'public/assets'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
m=json.loads((CACHE/'atlas.json').read_text());W,H=m['width'],m['height']
assert (W,H)==(7168,3072)
tiles=[];cores=[]
candidate_mode='--candidate' in sys.argv
if candidate_mode:
    assert sha(CACHE/'campus.png')==m['png_sha256']
    canvas=Image.open(CACHE/'campus.png').convert('RGB');tiles=m['render_tiles']
    cores=[Polygon([(t['core'][0],t['core'][1]),(t['core'][2],t['core'][1]),(t['core'][2],t['core'][3]),(t['core'][0],t['core'][3])]) for t in tiles]
for line in [json.dumps({'action':'finish'})] if candidate_mode else sys.stdin:
    cmd=json.loads(line);act=cmd['action']
    if act=='begin':canvas=Image.new('RGB',(W,H))
    elif act=='tile':
        path=CACHE/'render-tile.png';im=Image.open(path).convert('RGB')
        a,b,c,d=cmd['bounds'];x0,y0,x1,y1=cmd['core'];assert im.size==(c-a,d-b)
        core=Polygon([(x0,y0),(x1,y0),(x1,y1),(x0,y1)])
        assert all(core.intersection(p).area==0 for p in cores);cores.append(core)
        canvas.paste(im.crop((x0-a,y0-b,x1-a,y1-b)),(x0,y0));tiles.append({**cmd,'sha256':sha(path)});im.close()
    elif act=='finish':
        assert len(tiles)==8 and unary_union(cores).area==W*H
        # Keep one reusable native candidate for recovery/visual inspection.
        # Reserve before writing; no extra tile tree or scene copy is made.
        candidate=CACHE/'campus.png'
        used=sum(p.stat().st_size for p in CACHE.rglob('*') if p.is_file())
        assert used-(candidate.stat().st_size if candidate.exists() else 0)+64*1024**2<192*1024**2
        canvas.save(candidate,format='PNG',compress_level=6)
        m['png_sha256']=sha(candidate)
        m['render_tiles']=tiles
        (CACHE/'atlas.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
        for p,h in m['sources'].items():assert sha(ROOT/p)==h,p
        x,y,z=m['camera']['rotation_euler'];sx,cx=math.sin(x),math.cos(x);sy,cy=math.sin(y),math.cos(y);sz,cz=math.sin(z),math.cos(z)
        rot=np.array([[cz,-sz,0],[sz,cz,0],[0,0,1]])@np.array([[cy,0,sy],[0,1,0],[-sy,0,cy]])@np.array([[1,0,0],[0,cx,-sx],[0,sx,cx]])
        pos=np.array(m['camera']['position']);ppm=W/m['camera']['ortho_scale'];errors=[]
        layout=json.loads((ROOT/'model/campus/layout.json').read_text())
        main=json.loads((ROOT/'model/campus/references/satellite-export.json').read_text())['extent']
        north=json.loads((ROOT/'model/campus/references/north-extension.json').read_text())['extent']
        cs=math.cos(math.radians(31.578));ox=main['xmin']+600/1152*(main['xmax']-main['xmin']);oy=main['ymax']-850/1920*(main['ymax']-main['ymin'])
        # The southern navigation starts on the source-traced flower garden,
        # leaving the complete southern record list and map freely browsable.
        garden_source=[(248,1375),(535,1375),(535,1662),(248,1662)]
        garden_world=np.array([[((main['xmin']+x/1152*(main['xmax']-main['xmin']))-ox)*cs,
                                ((main['ymax']-y/1920*(main['ymax']-main['ymin']))-oy)*cs,0]
                               for x,y in garden_source])
        garden_camera=(garden_world-pos)@rot
        garden_px=np.column_stack((W/2+garden_camera[:,0]*ppm,H/2-garden_camera[:,1]*ppm))
        mobile_source=[(315,1450),(450,1450),(450,1610),(315,1610)]
        mobile_world=np.array([[((main['xmin']+x/1152*(main['xmax']-main['xmin']))-ox)*cs,
                                ((main['ymax']-y/1920*(main['ymax']-main['ymin']))-oy)*cs,0]
                               for x,y in mobile_source])
        mobile_camera=(mobile_world-pos)@rot
        mobile_px=np.column_stack((W/2+mobile_camera[:,0]*ppm,H/2-mobile_camera[:,1]*ppm))
        for region in m['regions']:
            if region['id']=='south':
                region['focus_bounds']=[float(garden_px[:,0].min()-52),float(garden_px[:,1].min()-52),
                                        float(garden_px[:,0].max()+52),float(garden_px[:,1].max()+52)]
                region['focus_bounds_mobile']=[float(mobile_px[:,0].min()-30),float(mobile_px[:,1].min()-30),
                                               float(mobile_px[:,0].max()+30),float(mobile_px[:,1].max()+30)]
                region['focus_source']='Satellite pixel garden boundary, with 52 native-image-pixel margin; building list remains the full south region.'
        focus_errors=[]
        for ident,frame in m.get('region_focus_revision',{}).get('regions',{}).items():
            e,w,h=(north,1000,900) if frame['source']=='north-extension' else (main,1152,1920)
            world=np.array([[((e['xmin']+x/w*(e['xmax']-e['xmin']))-ox)*cs,
                              ((e['ymax']-y/h*(e['ymax']-e['ymin']))-oy)*cs,z]
                             for x,y in frame['pixel_frame'] for z in frame['height_envelope_m_estimate']])
            local=(world-pos)@rot
            pixels=np.column_stack((W/2+local[:,0]*ppm,H/2-local[:,1]*ppm))
            expected=np.array([pixels[:,0].min(),pixels[:,1].min(),pixels[:,0].max(),pixels[:,1].max()])
            region=next(r for r in m['regions'] if r['id']==ident)
            error=float(np.max(np.abs(expected-np.array(region['focus_bounds_mobile']))))
            assert error<.02 and frame['full_record_count']==region['count'],(ident,error)
            assert region['count']==sum(r['region']==ident for r in m['records'])
            assert all(0<=expected[i]<=[W,H,W,H][i] for i in range(4))
            frame['independent_projection_max_difference_px']=error;focus_errors.append(error)
        if focus_errors:
            assert len(focus_errors)==3
            m['checks']['independent_region_focus_max_difference_px']=max(focus_errors)
        roof_errors=[]
        for row in layout['buildings']:
            e,w,h=(north,1000,900) if row.get('source')=='north-extension' else (main,1152,1920)
            expected=Polygon([((e['xmin']+p[0]/w*(e['xmax']-e['xmin'])-ox)*cs,(e['ymax']-p[1]/h*(e['ymax']-e['ymin'])-oy)*cs) for p in row['outline']])
            actual=unary_union([Polygon([p[:2] for p in f]) for f in m['roof_faces_world'][row['id']]])
            roof_errors.append(actual.hausdorff_distance(expected))
        assert max(roof_errors)<.01
        m['checks']['independent_source_roof_max_difference_m']=max(roof_errors)
        for row in m['records']:
            polys=[]
            for f in m['roof_faces_world'][row['id']]:
                pp=(np.array(f)-pos)@rot;g=Polygon([(W/2+p[0]*ppm,H/2-p[1]*ppm) for p in pp])
                if g.is_valid and g.area>1e-6:polys.append(g)
            # Close only subpixel cracks between coplanar roof triangles, as in
            # the reviewed joined-study exporter. Preserve actual courtyards.
            g=unary_union(polys).buffer(.003,join_style=2).buffer(-.003,join_style=2)
            old=unary_union([Polygon(p[0],p[1:]) for p in row['polygons']]).buffer(.003,join_style=2).buffer(-.003,join_style=2)
            errors.append(old.hausdorff_distance(g))
            parts=list(g.geoms) if hasattr(g,'geoms') else [g];p=g.representative_point()
            row['polygons']=[[list(p.exterior.coords),*[list(r.coords) for r in p.interiors]] for p in parts];row['anchor']=[p.x,p.y]
        assert max(errors)<.02 and len(m['records'])==130,max(errors)
        m['checks']['independent_projection_max_difference_px']=max(errors)
        roofs={r['id']:unary_union([Polygon(p[0],p[1:]) for p in r['polygons']]) for r in m['records']}
        for row in m['records']:
            roof=roofs[row['id']]
            others=unary_union([g for key,g in roofs.items() if key!=row['id'] and roof.intersects(g)])
            safe=roof.difference(others.buffer(.8));inset=safe.buffer(-.8)
            if not inset.is_empty:safe=inset
            assert not safe.is_empty,row['id']
            parts=list(safe.geoms) if hasattr(safe,'geoms') else [safe]
            point=max(parts,key=lambda g:g.area).representative_point()
            row['anchor']=[point.x,point.y]
        m['checks']['anchor_method']='Largest exclusive roof area, with 0.8 native pixel separation from other roofs and its own boundary; roof geometry and camera unchanged.'
        m['render_tiles']=tiles;m['assembly']='Eight overlapping native tiles cropped and assembled in memory, no scaling'
        m['updated']=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()
        m['exporter_sha256']=sha(Path(__file__));m['visual_review']={'status':'pending'};m['frontend_validation']={'status':'pending'}
        m['budget']={'asset_count_limit':10,'asset_bytes_limit':8*1024**2,'cache_bytes_limit':192*1024**2,'source_amplification_limit':256}
        baseline=json.loads((OUT/'campus-atlas.json').read_text())
        assert m['camera']==baseline['camera'],'Source-projected UI mask needs reprojection after a camera change'
        m['presentation_mask']=dict(baseline['presentation_mask'])
        m['previous_iteration']={'image_sha256':baseline['image_sha256'],'status':'superseded by source-bounded removal of external context-road overhang; original model inputs retained'}
        other=['campus-north.webp','campus-north.json','campus-north-before.webp','campus-reference.webp','campus-lake.webp','campus-lake.json','campus-study.webp','campus-study.json']
        other_bytes=sum((OUT/p).stat().st_size for p in other)
        source_bytes=sum((ROOT/p).stat().st_size for p in ['scripts/campus_study.py','scripts/lake_study.py','scripts/north_study.py','scripts/campus_atlas.py','scripts/export_atlas.py','scripts/refine_buildings.py','scripts/campus_expansion.py','scripts/canopy_volume.py','scripts/ground_contact.py','scripts/facade_depth.py','scripts/landscape_beds.py','scripts/courtyard_finish.py','scripts/landscape_surface.py','scripts/facade_finish.py','scripts/hardscape_transition.py','scripts/planting_finish.py','scripts/paving_cleanup.py','scripts/context_roads.py','scripts/campus_expansion_export.py','src/CampusAtlas.jsx','src/campusAtlas.css'])
        for quality in (91,89,87,85,83):
            b=io.BytesIO();canvas.save(b,format='WEBP',quality=quality,method=6);payload=b.getvalue()
            m['image_sha256']=hashlib.sha256(payload).hexdigest();m['image_bytes']=len(payload);m['webp_quality']=quality
            m['presentation_mask']['image_sha256']=m['image_sha256']
            # Compact serialization retains every proof/coordinate while
            # reserving capacity for browser and construction evidence.
            encoded=(json.dumps(m,ensure_ascii=False,separators=(',',':'))+'\n').encode()
            total=other_bytes+len(payload)+len(encoded)
            if total+384*1024<8*1024**2:break
        assert total+384*1024<8*1024**2 and total/source_bytes<256,(total,source_bytes)
        assert sum(p.stat().st_size for p in CACHE.rglob('*') if p.is_file())<192*1024**2
        destination=CACHE if '--stage' in sys.argv else OUT
        (destination/'campus-atlas.webp').write_bytes(payload);(destination/'campus-atlas.json').write_bytes(encoded)
    print(json.dumps({'ok':True,'action':act}),flush=True)
