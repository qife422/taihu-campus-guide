"""Photo-led architectural detail for the atlas; the retained source scene is read-only.

The photographed north batch uses campus-aerial.jpg for visible facade families.
Other groups use their fixed satellite roof traces and conservative facade types.
Openings, projections and heights remain estimates, not a surveyed reconstruction.
This module creates meshes in memory and does not save a scene or modify layout.
"""
import hashlib
import math
import random
from pathlib import Path

import bpy
from mathutils import Vector
from shapely import constrained_delaunay_triangles
from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.polygon import orient
from shapely.ops import unary_union


def refine_north(scene, layout, point, material, root):
    materials = []
    def mat(name, color, rough=.75, metal=0):
        m = material('Atlas architecture ' + name, color, rough)
        m.node_tree.nodes.get('Principled BSDF').inputs['Metallic'].default_value = metal
        materials.append(m)
        return len(materials) - 1

    plaster = mat('warm plaster', (.73, .67, .55))
    pale = mat('pale trim', (.84, .82, .72))
    salmon = mat('salmon wall', (.63, .34, .245))
    brick = mat('red brick', (.48, .135, .068))
    tile = mat('dark slate tiles', (.105, .145, .145))
    terra = mat('terracotta tiles', (.40, .095, .045))
    roof = mat('mineral flat roof', (.61, .60, .52))
    blue = mat('blue standing seam', (.035, .25, .36), .53, .14)
    light_metal = mat('light standing seam', (.58, .62, .59), .53, .12)
    flat_dark = mat('weathered dark flat roof', (.26, .285, .265))
    neutral_wall = mat('neutral residential plaster', (.68, .635, .53))
    academic_wall = mat('institutional pale plaster', (.77, .755, .67))
    field_wall = mat('weathered campus plaster', (.60, .605, .55))
    field_trim = mat('muted campus stone trim', (.69, .705, .665))
    base_stone = mat('muted stone plinth', (.40, .425, .40))
    solar = mat('source visible solar panels', (.075, .12, .17), .38, .2)
    metal = mat('metal frame', (.34, .39, .38), .44, .4)
    shadow = mat('deep balcony recess', (.16, .145, .12))
    glasses = [mat('glass ' + str(i), c, .29, .08) for i, c in enumerate([
        (.068, .135, .16), (.10, .18, .195), (.16, .23, .24), (.21, .28, .28)])]
    # The unphotographed facades are an interpretation. Vary only their surface
    # finish, keeping every source roof trace and the estimated opening layout.
    for mi, low, high in [
        (neutral_wall, (.49,.49,.455), (.65,.63,.57)),
        (academic_wall, (.565,.575,.55), (.72,.725,.68)),
        (field_wall, (.52,.535,.49), (.665,.675,.62)),
        (field_trim, (.63,.65,.615), (.75,.765,.725)),
    ]:
        ns=materials[mi].node_tree.nodes; links=materials[mi].node_tree.links
        tc=ns.new('ShaderNodeTexCoord');tc.object=scene.objects.get('Study world material frame')
        noise=ns.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=.48
        noise.inputs['Detail'].default_value=3.5
        ramp=ns.new('ShaderNodeValToRGB')
        ramp.color_ramp.elements[0].position=.22
        ramp.color_ramp.elements[0].color=(*low,1)
        ramp.color_ramp.elements[1].position=.78
        ramp.color_ramp.elements[1].color=(*high,1)
        links.new(tc.outputs['Object'],noise.inputs['Vector'])
        links.new(noise.outputs['Fac'],ramp.inputs[0])
        links.new(ramp.outputs[0],ns.get('Principled BSDF').inputs['Base Color'])
    # Give each traced roof family a visible, small-scale finish. This changes
    # surface texture only; the satellite roof outlines and heights stay fixed.
    roof_courses = {
        tile: ((.115,.15,.145),(.19,.205,.19),(.095,.12,.115),.55,.34),
        terra: ((.43,.12,.070),(.56,.19,.11),(.34,.095,.060),.60,.36),
        blue: ((.055,.23,.31),(.105,.31,.38),(.055,.20,.26),12,.62),
        light_metal: ((.55,.59,.56),(.71,.72,.67),(.50,.55,.52),12,.62),
        roof: ((.56,.55,.49),(.65,.63,.56),(.47,.48,.43),2.8,2.4),
        flat_dark: ((.25,.27,.25),(.32,.33,.30),(.22,.24,.22),2.8,2.4),
    }
    roof_photo_cache={}
    def source_roof_finish(mi, source):
        if mi not in roof_courses:return materials[mi]
        key=(mi,source)
        if key in roof_photo_cache:return roof_photo_cache[key]
        base=materials[mi];finish=base.copy();finish.name=base.name+' source '+source
        ns=finish.node_tree.nodes;links=finish.node_tree.links;bs=ns.get('Principled BSDF')
        base_color=bs.inputs['Base Color'].links[0].from_socket
        photo_file='north-extension.jpg' if source=='north-extension' else 'satellite.jpg'
        width,height=(1000,900) if source=='north-extension' else (1152,1920)
        lower=point((0,height),source=source);upper=point((width,0),source=source)
        coord=ns.new('ShaderNodeTexCoord');coord.object=scene.objects.get('Study world material frame')
        mapping=ns.new('ShaderNodeVectorMath');mapping.operation='MULTIPLY_ADD'
        mapping.inputs[1].default_value=(1/(upper.x-lower.x),1/(upper.y-lower.y),1)
        mapping.inputs[2].default_value=(-lower.x/(upper.x-lower.x),-lower.y/(upper.y-lower.y),0)
        photo=ns.new('ShaderNodeTexImage')
        photo.image=bpy.data.images.load(str(root/'model/campus/references'/photo_file),check_existing=True)
        photo.interpolation='Cubic';photo.extension='EXTEND'
        mixed=ns.new('ShaderNodeMixRGB');mixed.inputs[0].default_value=.26
        links.new(coord.outputs['Object'],mapping.inputs[0])
        links.new(mapping.outputs[0],photo.inputs['Vector'])
        links.new(base_color,mixed.inputs[1]);links.new(photo.outputs['Color'],mixed.inputs[2])
        links.new(mixed.outputs[0],bs.inputs['Base Color'])
        roof_photo_cache[key]=finish
        return finish
    for mi,(c1,c2,mortar,bw,rh) in roof_courses.items():
        m=materials[mi];ns=m.node_tree.nodes;ls=m.node_tree.links
        bricks=ns.new('ShaderNodeTexBrick');bricks.offset=0 if mi in (blue,light_metal) else .5
        bricks.inputs['Scale'].default_value=1
        bricks.inputs['Brick Width'].default_value=bw
        bricks.inputs['Row Height'].default_value=rh
        bricks.inputs['Mortar Size'].default_value=.018 if mi in (tile,terra) else .025
        bricks.inputs['Color1'].default_value=(*c1,1)
        bricks.inputs['Color2'].default_value=(*c2,1)
        bricks.inputs['Mortar'].default_value=(*mortar,1)
        tc=ns.new('ShaderNodeUVMap');tc.uv_map='Roof finish frame'
        ls.new(tc.outputs['UV'],bricks.inputs['Vector'])
        ls.new(bricks.outputs['Color'],ns.get('Principled BSDF').inputs['Base Color'])
    for mi in [tile, terra, blue, light_metal]:
        m = materials[mi]; ns = m.node_tree.nodes; ls = m.node_tree.links
        tc = ns.new('ShaderNodeUVMap');tc.uv_map='Roof finish frame'
        wave = ns.new('ShaderNodeTexWave')
        wave.wave_type = 'BANDS'; wave.bands_direction = 'Y'
        wave.inputs['Scale'].default_value = .82 if mi in (blue, light_metal) else 1.47
        ls.new(tc.outputs['UV'], wave.inputs['Vector'])
        bump = ns.new('ShaderNodeBump'); bump.inputs['Distance'].default_value = .025
        bump.inputs['Strength'].default_value = .20
        ls.new(wave.outputs['Fac'], bump.inputs['Height'])
        ls.new(bump.outputs['Normal'], ns.get('Principled BSDF').inputs['Normal'])

    def ccw(points):
        return points if sum(a.x*b.y-b.x*a.y for a,b in zip(points, points[1:]+points[:1])) > 0 else list(reversed(points))

    class Mesh:
        def __init__(self, name):
            self.name = name; self.v = []; self.f = []; self.mi = []; self.roof_faces = []
        def face(self, vs, mi, capture=False):
            if capture and sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(vs,vs[1:]+vs[:1]))<0:
                vs=list(reversed(vs))
            k = len(self.v); self.v.extend([tuple(v) for v in vs])
            self.f.append(tuple(range(k, k+len(vs)))); self.mi.append(mi)
            if capture: self.roof_faces.append([list(v) for v in vs])
        def box(self, c, size, mi, angle=0):
            x,y,z = [s/2 for s in size]; co,si = math.cos(angle),math.sin(angle)
            vs = [(c[0]+a*co-b*si,c[1]+a*si+b*co,c[2]+d) for a,b,d in
                  [(-x,-y,-z),(x,-y,-z),(x,y,-z),(-x,y,-z),(-x,-y,z),(x,-y,z),(x,y,z),(-x,y,z)]]
            for f in [(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]:
                self.face([vs[i] for i in f],mi)
        def plane(self, g, z, mi, capture=False, up=True):
            if g.is_empty: return
            for tr in constrained_delaunay_triangles(g).geoms:
                coords=list(orient(tr,sign=1 if up else -1).exterior.coords)[:-1]
                self.face([(x,y,z) for x,y in coords],mi,capture)
        def solid(self, g, z, height, mi):
            if g.is_empty: return
            for poly in (list(g.geoms) if hasattr(g,'geoms') else [g]):
                poly=orient(poly,sign=1)
                self.plane(poly,z,mi,up=False); self.plane(poly,z+height,mi)
                for ring in [poly.exterior,*poly.interiors]:
                    for a,b in zip(ring.coords,list(ring.coords)[1:]):
                        self.face([(a[0],a[1],z),(b[0],b[1],z),(b[0],b[1],z+height),(a[0],a[1],z+height)],mi)
        def line(self, ps, width, z, height, mi, closed=False):
            pp = ps+[ps[0]] if closed else ps
            for a,b in zip(pp,pp[1:]):
                delta = b-a; c=(a+b)/2; c.z=z+height/2
                if delta.length>.01: self.box(c,(delta.length,width,height),mi,math.atan2(delta.y,delta.x))
        def finish(self, row):
            me=bpy.data.meshes.new(self.name); me.from_pydata(self.v,[],self.f); me.update()
            # Metre-scaled UVs follow the longest traced edge. No vertex or
            # roof face moves; the same finish is shared across building sizes.
            traced=[point(q,source=row.get('source','satellite')) for q in row['outline']]
            axis=max((b-a for a,b in zip(traced,traced[1:]+traced[:1])),key=lambda v:v.length).normalized()
            cross=Vector((-axis.y,axis.x,0));origin=traced[0]
            uv=me.uv_layers.new(name='Roof finish frame')
            for loop in me.loops:
                delta=me.vertices[loop.vertex_index].co-origin
                uv.data[loop.index].uv=(delta.dot(axis),delta.dot(cross))
            for i,m in enumerate(materials):me.materials.append(source_roof_finish(i,row.get('source','satellite')))
            for poly,mi in zip(me.polygons,self.mi): poly.material_index=mi
            assert not me.validate(clean_customdata=False), self.name
            ob=bpy.data.objects.new(self.name,me); scene.collection.objects.link(ob)
            ob['source_id']=row['id']; ob['detail_basis']='photo facade family' if row['id'] in photographed else 'satellite roof trace and estimated facade family'
            return ob

    # Each recipe is tied to a visible building group, not a random facade style.
    batch = layout['buildings']
    photographed = {r['id'] for r in batch if r['id'].startswith('N') and
                    (r['kind']=='dorm' or r['id'] in ['N31','N32','N33','N34','N35'])}
    outlines = {r['id']: Polygon([(point(q,source=r.get('source','satellite')).x,
                                  point(q,source=r.get('source','satellite')).y) for q in r['outline']]) for r in batch}
    roofs = {}; checks = []; details = []; mesh_vertices=0
    small_balconies={'N25','N26','N27','N28','N29','N30'}
    towers={'N21':(616,382), 'N22':(599,415), 'N23':(554,404), 'N24':(518,450),
            'N25':(556,475), 'N26':(597,481), 'N27':(557,499), 'N28':(597,506)}
    for row in batch:
        ident=row['id']; ps=ccw([point(q,source=row.get('source','satellite')) for q in row['outline']])
        g=Polygon([(p.x,p.y) for p in ps]); h=row['height_estimate_m']; n=row['floors_estimate']; step=h/n
        bm=Mesh('Atlas detailed '+ident+' '+row['name'])
        dorm=row['kind']=='dorm'; academic=ident in {'N34','N35'}; hall=ident in {'N32','N33'}
        photo=ident in photographed; classroom=row['kind']=='academic'; shed=ident in {'N13','N15','N19'}
        roof_mi={'charcoal':tile,'terracotta':terra,'blue_metal':blue,'light_metal':light_metal}[row['roof_tone']]
        flat_mi={'charcoal':flat_dark,'terracotta':terra,'blue_metal':blue,'light_metal':roof}[row['roof_tone']]
        neighbours=unary_union([geom for other,geom in outlines.items() if other!=ident and
                                ((academic and other in {'N34','N35'}) or (not photo and geom.distance(g)<.05))])
        def exposed(a,b):
            edge=LineString([(a.x,a.y),(b.x,b.y)])
            return neighbours.is_empty or edge.intersection(neighbours.buffer(.04)).length<edge.length*.8
        def perimeter(width,z,height,mi):
            for a,b in zip(ps,ps[1:]+ps[:1]):
                if not photo and not neighbours.is_empty:
                    visible=LineString([(a.x,a.y),(b.x,b.y)]).difference(neighbours.buffer(.12))
                    for segment in (list(visible.geoms) if hasattr(visible,'geoms') else [visible]):
                        if segment.geom_type=='LineString' and segment.length>.05:
                            bm.line([Vector((x,y,0)) for x,y in segment.coords],width,z,height,mi)
                elif exposed(a,b):bm.line([a,b],width,z,height,mi)
        wall=(salmon if dorm else brick if academic else plaster) if photo else neutral_wall if dorm else academic_wall if classroom else field_wall
        trim_mi=pale if photo else field_trim
        # Set back the wall core, with real slab depth and openings in front.
        core=g.buffer(-.68 if dorm and photo else -.28,join_style='mitre')
        if not shed: bm.solid(core,.15,h,wall)
        else: bm.solid(g.buffer(-.20),.15,.24,base_stone)
        perimeter(.24,.18,.42,plaster if photo else field_trim)
        for a,b in zip(ps,ps[1:]+ps[:1]):
            delta=b-a; length=delta.length
            if length<2.6 or not exposed(a,b): continue
            t=delta.normalized(); out=Vector((t.y,-t.x,0)); angle=math.atan2(t.y,t.x)
            long=length>14
            bays=max(1,round(length/(3.55 if academic else 4.0 if dorm else 4.6)))
            bay=length/bays
            if shed:
                for j in range(bays+1):
                    c=a+t*(j*bay)-out*.30; c.z=h/2
                    bm.box(c,(.26,.26,h),pale,angle)
                bm.line([a,b],.24,h-.40,.35,base_stone)
                continue
            # Only broad southern faces receive the photo-visible open balcony family.
            balconies=photo and dorm and long and out.y < -.25
            use_arc=ident in small_balconies or ident=='N22'
            south_academic=academic and long and out.y<-.5
            glass_bays={bays//2-1,bays//2} if south_academic else set()
            for floor in range(n):
                z=.15+floor*step
                slab=(a+b)/2; slab.z=z+.08
                bm.box(slab,(length,.64 if dorm else .40,.16 if dorm else .13),trim_mi,angle)
                if dorm:
                    trim=(a+b)/2-out*.02; trim.z=z+step-.28
                    bm.box(trim,(length,.38,.36 if photo else .18),terra if photo else base_stone,angle)
                for j in range(bays):
                    c=a+t*(bay*(j+.5))-out*(.43 if dorm and photo else .17); c.z=z+step*.53
                    ww=bay*(.48 if academic else .73 if ident=='N31' else .68)
                    wh=step*(.64 if academic or ident=='N31' else .57)
                    rng=random.Random(157+int(ident[1:])*103+floor*19+j)
                    gm=glasses[rng.randrange(len(glasses))]
                    if j in glass_bays:
                        c.z=z+step/2
                        bm.box(c+out*.31,(bay+.015,.12,step-.10),glasses[0],angle)
                        for k in range(3):
                            bm.box(c+out*.40+t*((k-1)*bay/3),(.052,.075,step),metal,angle)
                        r=c+out*.42; r.z=z+.10; bm.box(r,(bay,.10,.11),pale,angle)
                        continue
                    # Recessed panes, separate surround, sill and transom.
                    bm.box(c,(ww+.17,.15,wh+.18),trim_mi,angle)
                    bm.box(c+out*.087,(ww,.075,wh),gm,angle)
                    panes=2 if academic or not photo else 3 if dorm else 4
                    for k in range(panes+1):
                        bm.box(c+out*.135+t*(-ww/2+k*ww/panes),(.045,.09,wh+.04),trim_mi,angle)
                    transom=c+out*.14; transom.z+=wh*.23; bm.box(transom,(ww,.10,.045),trim_mi,angle)
                    sill=c+out*.18; sill.z-=wh/2+.07; bm.box(sill,(ww+.20,.27,.12),trim_mi,angle)
                    if balconies and floor>0:
                        mid=a+t*(bay*(j+.5)); width=bay*.90
                        # Geometry for the recess, floor slab, railing and side fins.
                        recess=mid-out*.53; recess.z=z+step*.47
                        bm.box(recess,(width,.08,step*.79),shadow,angle)
                        bm.box(recess+out*.065,(width*.70,.055,step*.60),gm,angle)
                        if use_arc:
                            arc=[mid+t*(width/2*math.cos(k*math.pi/14))+out*(.76*math.sin(k*math.pi/14)) for k in range(15)]
                            footprint=Polygon([(p.x,p.y) for p in arc])
                            bm.solid(footprint,z+.08,.16,pale)
                            bm.line(arc,.10,z+.26,.62,plaster)
                            bm.line(arc,.13,z+.88,.10,pale)
                            for k in range(1,14,2):
                                q=arc[k].copy(); q.z=z+.60; bm.box(q,(.052,.065,.64),metal,angle)
                        else:
                            floorc=mid+out*.22; floorc.z=z+.12
                            bm.box(floorc,(width,1.40,.20),pale,angle)
                            front=mid+out*.84; front.z=z+.68
                            bm.box(front,(width,.14,.65),salmon,angle)
                            front.z=z+1.035; bm.box(front,(width+.10,.20,.10),pale,angle)
                            for side in [-1,1]:
                                fin=mid+t*side*(width/2)+out*.18; fin.z=z+step*.48
                                bm.box(fin,(.18,1.5,step-.25),pale,angle)
            # Tall side fins and paired windows distinguish institutional blocks from dorms.
            if academic:
                for j in range(bays+1):
                    c=a+t*j*bay+out*.055; c.z=h/2
                    bm.box(c,(.38,.42,h),brick,angle)
                for floor in range(n):
                    c=(a+b)/2; c.z=.15+floor*step+.53
                    bm.box(c,(length,.26,.67),brick,angle)
                c=(a+b)/2+out*.07; c.z=h-step*.38
                bm.box(c,(length,.14,.64),glasses[0],angle)
                for j in range(bays*2+1):
                    c=a+t*j*length/(bays*2)+out*.17; c.z=h-step*.38
                    bm.box(c,(.04,.10,.68),pale,angle)
            elif ident=='N31':
                for j in [0,1,bays-1,bays]:
                    c=a+t*min(length,max(0,j*bay))+out*.035; c.z=h/2
                    bm.box(c,(.34,.39,h),plaster,angle)
            elif not photo:
                # Restrained window group rhythm; no unobserved balcony or entrance locations.
                for j in range(0,bays+1,2 if classroom else bays):
                    c=a+t*(j*bay)+out*.025; c.z=h/2
                    bm.box(c,(.20 if classroom else .14,.24,h),field_trim,angle)
                c=(a+b)/2; c.z=.48
                bm.box(c,(length,.32,.65),base_stone,angle)
            # A visible ground entrance on the photographed public front, no route claim.
            if (south_academic and ident=='N34') or (ident=='N31' and out.y<-.5):
                c=(a+b)/2+out*.33; c.z=1.70
                bw=min(7.5,length*.24)
                bm.box(c,(bw,.14,2.95),glasses[0],angle)
                for k in [-2,-1,0,1,2]:
                    q=c+t*k*bw/5+out*.10; bm.box(q,(.065,.1,2.95),pale,angle)
                canopy=(a+b)/2+out*1.35; canopy.z=3.32
                bm.box(canopy,(bw+1.1,2.5,.24),roof,angle)
                for k in range(3):
                    q=(a+b)/2+out*(.65+k*.42); q.z=.21+(2-k)*.095
                    bm.box(q,(bw+1.5,1.0,.18),pale,angle)

        # Source traces can overlap at adjoining wings. A 2 cm roof step removes
        # coplanar intersections without changing any XY outline or storey height.
        overlaps=[r for r in batch if r['id']<ident and abs(r['height_estimate_m']-h)<.01 and outlines[r['id']].intersection(g).area>.05]
        base=h+.45+(.02*len(overlaps) if not photo else 0)
        perimeter(.40,h,.30,trim_mi)
        # Original source outline forms the outside edge of every roof.
        pitched=(dorm and ident not in small_balconies and row['roof']!='flat') if photo else row['roof'] in {'hip','gable'}
        if pitched and row['roof']!='gable' and len(ps)==4:
            start=max(range(4),key=lambda i:(ps[(i+1)%4]-ps[i]).length)
            a,b,c,d=[ps[(start+i)%4] for i in range(4)]
            e=(a+d)/2; f=(b+c)/2; u=(f-e).normalized()
            depth=((a-d).length+(b-c).length)/2; rise=min(3.25,depth*.19)
            e+=u*min(depth*.30,(f-e).length*.15); f-=u*min(depth*.30,(f-e).length*.15)
            corners=[(p.x,p.y,base) for p in [a,b,c,d]]+[(e.x,e.y,base+rise),(f.x,f.y,base+rise)]
            for face in [(0,1,5,4),(1,2,5),(2,3,4,5),(3,0,4)]:bm.face([corners[i] for i in face],roof_mi,True)
            bm.line([e,f],.17,base+rise,.12,roof_mi)
            perimeter(.23,base-.08,.18,terra if photo or row['roof_tone']=='terracotta' else trim_mi)
        elif pitched and (row['roof']!='gable' or len(ps)>4):
            # Continuous hipped roof, including source-traced concave courtyard wings.
            rise=4.2; slope=.32; remaining=g; distance=0
            for _ in range(18):
                distance+=.60; inner=g.buffer(-distance,join_style='mitre')
                band=remaining.difference(inner)
                for tr in constrained_delaunay_triangles(band).geoms:
                    bm.face([(x,y,base+min(rise,g.boundary.distance(Point(x,y))*slope))
                             for x,y in list(tr.exterior.coords)[:-1]],roof_mi,True)
                remaining=inner
                if remaining.is_empty: break
            if not remaining.is_empty:
                for tr in constrained_delaunay_triangles(remaining).geoms:
                    bm.face([(x,y,base+min(rise,g.boundary.distance(Point(x,y))*slope))
                             for x,y in list(tr.exterior.coords)[:-1]],roof_mi,True)
            perimeter(.23,base-.08,.18,terra if photo or row['roof_tone']=='terracotta' else trim_mi)
        elif hall or (not photo and row['roof']=='gable'):
            # Two photo-visible blue roof planes with a narrow raised ridge.
            rect=ccw([Vector((x,y,0)) for x,y in list(g.minimum_rotated_rectangle.exterior.coords)[:-1]])
            a,b=max(zip(rect,rect[1:]+rect[:1]),key=lambda e:(e[1]-e[0]).length)
            u=(b-a).normalized(); v=Vector((-u.y,u.x,0)); c=Vector((g.centroid.x,g.centroid.y,0))
            depth=max(abs((p-c).dot(v)) for p in ps); rise=min(1.45,depth*.14)
            # Split at the ridge before triangulation to avoid a flat triangular roof.
            cutter=LineString([(c.x-u.x*100,c.y-u.y*100),(c.x+u.x*100,c.y+u.y*100)])
            from shapely.ops import split
            for side in split(g,cutter).geoms:
                for tr in constrained_delaunay_triangles(side).geoms:
                    bm.face([(x,y,base+rise*(1-min(1,abs((Vector((x,y,0))-c).dot(v))/depth)))
                             for x,y in list(tr.exterior.coords)[:-1]],blue if hall else roof_mi,True)
            if not shed:
                for a,b in zip(ps,ps[1:]+ps[:1]):
                    az=base+rise*(1-min(1,abs((a-c).dot(v))/depth));bz=base+rise*(1-min(1,abs((b-c).dot(v))/depth))
                    # Close the gable end without adding a second coplanar roof.
                    top=[(b.x,b.y,bz)]
                    ridge_cross=LineString([(a.x,a.y),(b.x,b.y)]).intersection(cutter)
                    if ridge_cross.geom_type=='Point' and ridge_cross.distance(Point(a.x,a.y))>.01 and ridge_cross.distance(Point(b.x,b.y))>.01:
                        top.append((ridge_cross.x,ridge_cross.y,base+rise))
                    top.append((a.x,a.y,az))
                    bm.face([(a.x,a.y,h),(b.x,b.y,h),*top],wall)
            # The material supplies the fine seams; the ridge is geometric.
            rline=cutter.intersection(g)
            if rline.geom_type=='LineString': bm.line([Vector((x,y,0)) for x,y in rline.coords],.28,base+rise,.12,metal)
        else:
            bm.plane(g,base,(roof if not dorm else tile) if photo else flat_mi,True)
            parapet=.64 if photo else .44 if not shed else .14
            edge_mi=terra if dorm and photo else trim_mi
            perimeter(.30,base,parapet,edge_mi)
            perimeter(.42,base+parapet-.01,.10,edge_mi)
            a,b=max(zip(ps,ps[1:]+ps[:1]),key=lambda e:(e[1]-e[0]).length)
            u=(b-a).normalized(); v=Vector((-u.y,u.x,0)); c=Vector((g.centroid.x,g.centroid.y,0))
            for j in range(-30,31):
                q=c+v*j*4; strip=LineString([(q.x-u.x*100,q.y-u.y*100),(q.x+u.x*100,q.y+u.y*100)]).buffer(.020).intersection(g.buffer(-.6))
                bm.plane(strip,base+.015,metal)
        # Photo-visible stair towers are inside their original source roof envelope.
        if ident in towers:
            q=point(towers[ident]); footprint=Point(q.x,q.y).buffer(2.2,cap_style='square').intersection(g.buffer(-.12))
            if footprint.area>2:
                tower_top=h+4.65
                bm.solid(footprint,.16,tower_top-.16,plaster); bm.plane(footprint,tower_top+.025,roof,True)
                coords=[Vector((x,y,0)) for x,y in list(footprint.exterior.coords)[:-1]]
                for lev in range(n+1):
                    z=lev*step+1.0; bm.line(coords,.17,z,.35,terra,True)
                    for a,b in zip(coords,coords[1:]+coords[:1]):
                        delta=b-a
                        if delta.length<1.4: continue
                        out=Vector((delta.y,-delta.x,0)).normalized(); c=(a+b)/2+out*.065; c.z=z+1.03
                        bm.box(c,(min(1.15,delta.length*.40),.10,.64),glasses[0],math.atan2(delta.y,delta.x))
                bm.line(coords,.26,tower_top,.14,terra,True)
        # Equipment is limited to the explicitly visible roof zones on the two public blocks.
        if ident in {'N31','N34'}:
            q=point((658,416) if ident=='N31' else (684,474)); zone=Point(q.x,q.y).buffer(3.1,cap_style='square').intersection(g.buffer(-1))
            if not zone.is_empty:
                bm.solid(zone,base+.04,.70,metal); bm.plane(zone,base+.765,roof,True)
        # Fixed satellite-visible rooftop zones; no automatic equipment on every roof.
        roof_zones={
            'E21': [('housing',[(506,300),(520,301),(520,308),(506,307)]),('housing',[(487,325),(499,326),(499,334),(487,333)])],
            'E24': [('solar',[(528,539),(564,539),(564,559),(528,559)]),('solar',[(594,538),(629,538),(629,559),(594,559)])],
            'E29': [('housing',[(426,555),(443,555),(443,566),(426,566)])],
        }
        for kind,coords in roof_zones.get(ident,[]):
            zone=Polygon([(point(q,source=row.get('source','satellite')).x,point(q,source=row.get('source','satellite')).y) for q in coords]).intersection(g.buffer(-.35))
            if zone.is_empty:continue
            if kind=='housing':
                bm.solid(zone,base+.03,.65,base_stone);bm.plane(zone,base+.70,roof,True)
            else:
                bm.solid(zone,base+.12,.12,metal);bm.plane(zone,base+.25,solar,True)
                x0,y0,x1,y1=zone.bounds
                for x in range(math.floor(x0),math.ceil(x1),2):
                    bm.plane(LineString([(x,y0),(x,y1)]).buffer(.025).intersection(zone),base+.265,pale)
                for y in range(math.floor(y0),math.ceil(y1),3):
                    bm.plane(LineString([(x0,y),(x1,y)]).buffer(.025).intersection(zone),base+.265,pale)
        out=bm.finish(row); mesh_vertices+=len(bm.v)
        old=next((o for o in scene.objects if o.name.startswith(ident+' ') and o.type=='MESH'),None)
        assert old is not None, ident
        old.hide_render=True
        footprints=unary_union([Polygon([(p[0],p[1]) for p in face]) for face in bm.roof_faces])
        discrepancy=footprints.symmetric_difference(g).area
        assert discrepancy<.01, (ident,discrepancy)
        roofs[ident]=bm.roof_faces
        checks.append({'id':ident,'source_roof_difference_m2':discrepancy,'vertices':len(bm.v),'faces':len(bm.f)})
        details.append({'id':ident,'features':
            'source-traced roof type and tone, recessed window groups, sills, cornices and restrained storey bands' if not photo and not shed else
            'source-traced canopy, slender supports and perimeter beam; dimensions estimated' if shed else
            'recessed balcony bays, storey slabs, tile roofs and photo-supported stair towers' if dorm else
            'red brick piers, grouped windows, glazed entry bay and flat roof edge' if academic else
            'blue standing-seam hall roof and grouped low windows' if hall else
            'pale storey bands, paired side windows, entrance glazing and roof equipment',
            'source':'model/central-campus/references/campus-aerial.jpg' if photo else 'model/campus/references/'+('north-extension.jpg' if row.get('source')=='north-extension' else 'satellite.jpg'),
            'certainty':'visible family and silhouette; bay counts, depth and concealed facades interpreted' if photo else 'roof outline/type/tone from fixed imagery; facade family, openings, height and finish dimensions estimated',
            'photo_facade_supported':photo,'roof_type':row['roof'],'roof_tone':row['roof_tone']})

    return {'region':'all exterior regions','building_ids':[r['id'] for r in batch],
            'photo_facade_building_ids':sorted(photographed),
            'satellite_sha256':{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(root)/'model/campus/references/satellite.jpg',Path(root)/'model/campus/references/north-extension.jpg']},
            'photo_sha256':hashlib.sha256((Path(root)/'model/central-campus/references/campus-aerial.jpg').read_bytes()).hexdigest(),
            'module_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'source_roof_checks':checks,'details':details,'roof_faces_world':roofs,
            'total_vertices':mesh_vertices,'source_scene_file_modified':False,
            'roof_finish':{'coordinates':'metre-scaled UV aligned to longest source edge',
                           'source_colour_influence':.26,'geometry_changed':False}}
