"""Verify source geometry, central-study placement, surface masks and the exported GLB.
Use --candidate to inspect /tmp/taihu-full before replacing the stable deliverables.
"""
import bpy,json,math,sys,hashlib,struct
from pathlib import Path
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view
import numpy as np
ROOT=Path(__file__).resolve().parent;OUT=Path('/tmp/taihu-full') if '--candidate' in sys.argv else ROOT
D=json.loads((ROOT/'layout.json').read_text());MAIN=json.loads((ROOT/'references/satellite-export.json').read_text());NORTH=json.loads((ROOT/'references/north-extension.json').read_text());COS=math.cos(math.radians(31.578));E=MAIN['extent'];OX=E['xmin']+600/1152*(E['xmax']-E['xmin']);OY=E['ymax']-850/1920*(E['ymax']-E['ymin'])
OLD=ROOT.parent/'central-campus';STUDY=ROOT.parent/'study';CE=json.loads((OLD/'references/satellite-export.json').read_text())['extent'];shift=Vector(((CE['xmin']+780/1800*(CE['xmax']-CE['xmin'])-OX)*COS,(CE['ymax']-680/1400*(CE['ymax']-CE['ymin'])-OY)*COS,0))
bpy.ops.wm.open_mainfile(filepath=str(STUDY/'campus.blend'));bpy.context.view_layer.update();expected={}
for key in ['B06','B07','B08']:
 parent=next(o for o in bpy.context.scene.objects if o.type=='EMPTY' and o.name.startswith(key+' Central'))
 verts=[];topology=hashlib.sha256();materials=[];count=0
 for ob in parent.children:
  if ob.type!='MESH':continue
  assert not any(m.show_render for m in ob.modifiers),(ob.name,'unbaked study modifier')
  offset=len(verts);matrix=ob.matrix_world;verts.extend([tuple(matrix@v.co+shift) for v in ob.data.vertices]);reverse=matrix.to_3x3().determinant()<0
  for face in ob.data.polygons:
   indices=list(face.vertices);indices=list(reversed(indices)) if reverse else indices
   topology.update(struct.pack('<'+'I'*(len(indices)+1),len(indices),*[offset+i for i in indices]));materials.append(ob.data.materials[face.material_index].name)
  count+=1
 expected[key]={'vertices':np.asarray(verts),'topology':topology.hexdigest(),'materials':materials,'components':count}
bpy.ops.wm.open_mainfile(filepath=str(OUT/'campus.blend'));scene=bpy.context.scene;bpy.context.view_layer.update();checks=[]
for r in D['buildings']:
 ob=bpy.data.objects.get(r['id']+' '+r['name']);assert ob and ob.type=='MESH',r['id'];src=r.get('source','satellite');m=NORTH if src=='north-extension' else MAIN;e=m['extent'];w,h=(1000,900) if src=='north-extension' else (1152,1920)
 ref=[((e['xmin']+p[0]/w*(e['xmax']-e['xmin'])-OX)*COS,(e['ymax']-p[1]/h*(e['ymax']-e['ymin'])-OY)*COS) for p in r['outline']]
 if sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(ref,ref[1:]+ref[:1]))<0:ref.reverse()
 verts=[ob.matrix_world@v.co for v in ob.data.vertices];n=len(ref)
 body_delta=max(abs(verts[i][a]-ref[i%n][a]) for i in range(n*2) for a in [0,1]);assert body_delta<.001,(r['id'],'body outline',body_delta)
 delta=max(abs(fn(p[a] for p in verts)-fn(p[a] for p in ref)) for a in [0,1] for fn in [min,max]);assert delta<1.0,(r['id'],'architectural projection',delta)
 zmax=max(p.z for p in verts);assert r['height_estimate_m']<=zmax<=r['height_estimate_m']+4,r['id']
 checks.append({'id':r['id'],'source_body_xy_max_difference_m':round(body_delta,7),'architectural_envelope_difference_m':round(delta,4),'top_m':round(zmax,2)})
central=[]
for key,exp in expected.items():
 ob=next(o for o in scene.objects if o.name.startswith(key+' Central'));arr=np.asarray([tuple(ob.matrix_world@v.co) for v in ob.data.vertices]);assert arr.shape==exp['vertices'].shape
 delta=float(np.max(np.abs(arr-exp['vertices'])));assert delta<.001,(key,delta)
 top=hashlib.sha256()
 for face in ob.data.polygons:top.update(struct.pack('<'+'I'*(len(face.vertices)+1),len(face.vertices),*face.vertices))
 assert top.hexdigest()==exp['topology'],(key,'topology mismatch')
 assert [ob.data.materials[f.material_index].name for f in ob.data.polygons]==exp['materials'],(key,'material assignment mismatch')
 central.append({'id':key,'source_components':exp['components'],'vertices':len(arr),'max_world_coordinate_difference_m':delta,'topology_sha256':top.hexdigest(),'face_material_assignments_preserved':True})
visible=[o for o in scene.objects if o.type=='MESH' and not o.hide_render];projected=[world_to_camera_view(scene,scene.camera,o.matrix_world@Vector(c)) for o in visible for c in o.bound_box];frame=[min(p.x for p in projected),min(p.y for p in projected),max(p.x for p in projected),max(p.y for p in projected)];assert all(0<x<1 for x in frame),frame
roads=json.loads((ROOT/'roads.json').read_text());assert all(abs(v)<1e-5 for v in roads['geometry_checks'].values()),roads['geometry_checks']
assert roads['source_hashes']['layout.json']==hashlib.sha256((ROOT/'layout.json').read_bytes()).hexdigest()
assert scene['central_study_sha256']==hashlib.sha256((STUDY/'campus.blend').read_bytes()).hexdigest()
blob=(OUT/'campus.glb').read_bytes();magic,version,length=struct.unpack_from('<4sII',blob);assert magic==b'glTF' and version==2 and length==len(blob);json_length,json_type=struct.unpack_from('<II',blob,12);assert json_type==0x4E4F534A;gltf=json.loads(blob[20:20+json_length]);ids={n.get('extras',{}).get('id') for n in gltf['nodes']};assert all(r['id'] in ids for r in D['buildings']);assert all(any(n['name'].startswith(key) for n in gltf['nodes']) for key in expected)
preserved_colors=[]
for material in gltf['materials']:
 if material.get('extras',{}).get('base_color_source'):
  source=bpy.data.materials.get(material['name']);assert source is not None
  shader=source.node_tree.nodes.get('Principled BSDF') if source.use_nodes else None;expected_color=shader.inputs['Base Color'].default_value if shader else source.diffuse_color;actual=material['pbrMetallicRoughness']['baseColorFactor'];assert max(abs(a-b) for a,b in zip(actual,expected_color))<1e-6
  preserved_colors.append(material['name'])
assert len(preserved_colors)>=30,'Missing procedural-material display colors'
positions_hash=hashlib.sha256(json.dumps([(r['id'],r['source'],r['outline']) for r in D['buildings']],sort_keys=True).encode()).hexdigest()
report={'status':'passed','scope':'source consistency, exported geometry and display masks; not surveyed accuracy or navigation validation','buildings':len(checks),'central_detailed_groups':len(central),'tracks':len(D['tracks']),'trees':int(scene['source_tree_instances']),'building_trace_sha256':positions_hash,'scene':{'status':'passed','building_geometry_checks':checks,'central_study_checks':central,'overview_frame_normalized':frame,'mesh_objects':len(visible),'unique_mesh_vertices':sum(len(m.vertices) for m in bpy.data.meshes),'total_vertices_with_instances':sum(len(o.data.vertices) for o in visible)},'road_surface':{'method':roads['method'],'clipped_area_before_mask_m2':roads['clipped_road_surface_m2'],'final_mask_intersections_m2':roads['geometry_checks'],'source_paving_classification':roads['source_paving_classification'],'navigation_validated':False},'glb':{'version':version,'bytes':len(blob),'nodes':len(gltf['nodes']),'meshes':len(gltf['meshes']),'all_building_ids_retained':True,'authored_procedural_display_colors_verified':preserved_colors,'required_extensions':gltf.get('extensionsRequired',[])},'render':{'status':'pending final render verification'},'frontend_build':{'status':'pending current viewer validation'}}
prior=json.loads((ROOT/'validation.json').read_text());report['polygon_checks']=prior.get('polygon_checks',prior.get('checks',[]));report['geojson_feature_count']=prior.get('geojson_feature_count');(OUT/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print('PASS',len(checks),'source bodies;',len(central),'central groups; frame',frame,'GLB bytes',len(blob),flush=True)
