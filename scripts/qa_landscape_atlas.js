async (page) => {
  const root='__PROJECT_ROOT__';
  const errors=[],captures=[],checks=[];
  page.on('pageerror',e=>errors.push(String(e)));
  page.on('console',m=>{if(m.type()==='error')errors.push(m.text())});
  await page.emulateMedia({reducedMotion:'reduce'});
  const assert=(a,m)=>{if(!a)throw Error(m)};
  const ready=async()=>{
    await page.waitForFunction(()=>document.querySelector('.atlas-map')?.tabIndex===0 && document.querySelector('.leaflet-image-layer')?.naturalWidth===7168 && document.querySelectorAll('.atlas-building-hotspot').length===130 && document.querySelectorAll('.atlas-source-point').length===7 && !document.querySelector('.atlas-map')?.classList.contains('leaflet-zoom-anim'));
    await page.evaluate(()=>new Promise(r=>{let n=0;function f(){if(++n===15)r();else requestAnimationFrame(f)}requestAnimationFrame(f)}));
  };
  const goto=async(q)=>{await page.goto('http://127.0.0.1:5173/'+q);await ready()};
  await page.setViewportSize({width:1280,height:720});await goto('?view=atlas&area=all');
  const meta=await(await page.request.get('http://127.0.0.1:5173/campus-atlas.json')).json();
  assert(meta.checks.landscape_detail.surface.material_count===4 && meta.checks.landscape_detail.beds.bed_count===4 && meta.checks.landscape_detail.courtyards.site_count===3,'Retained native detail metadata missing');
  assert(meta.checks.site_finish.facade && meta.checks.site_finish.hardscape && meta.checks.site_finish.planting,'Current site finishes missing');
  assert(meta.checks.paving_regularization.status==='passed' && meta.checks.paving_edge_finish.status==='passed','Current middle paving finish missing');
  assert(meta.map_places.image_sha256===meta.image_sha256,'New source points use stale image');
  const shot=async(name,criterion,focus=null,jpeg=false)=>{
    await ready();const state=await page.evaluate(async()=>{
      const img=document.querySelector('.leaflet-image-layer'),m=await(await fetch('/campus-atlas.json',{cache:'no-store'})).json();
      const bytes=await(await fetch(img.src,{cache:'no-store'})).arrayBuffer();
      const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))).map(v=>v.toString(16).padStart(2,'0')).join('');
      return {url:location.href,image_url:img.src,image_sha256:hash,formal_image_sha256:m.image_sha256,places_image_sha256:m.map_places.image_sha256,natural_size:[img.naturalWidth,img.naturalHeight],roof_hotspots:document.querySelectorAll('.atlas-building-hotspot').length,source_points:document.querySelectorAll('.atlas-source-point').length,overflow:document.documentElement.scrollWidth>innerWidth};
    });
    assert(!state.overflow && state.roof_hotspots===130 && state.source_points===7,'Invalid viewport '+name);
    assert(state.image_sha256===meta.image_sha256 && state.formal_image_sha256===meta.image_sha256 && state.places_image_sha256===meta.image_sha256 && state.image_url.includes(meta.image_sha256.slice(0,12)),'Stale image '+name);
    const path='output/playwright/landscape-'+name+(jpeg?'.jpg':'.png');await page.screenshot({path:root+path,...(jpeg?{type:'jpeg',quality:88}:{})});
    captures.push({path,criterion,viewport:page.viewportSize(),...state,focus});
  };
  const projectWorld = (meta, point) => {
    if (point.length !== 3 || !point.every(Number.isFinite)) throw new Error('Invalid retained world point');
    const [x,y,z] = meta.camera.rotation_euler, sx=Math.sin(x),cx=Math.cos(x),sy=Math.sin(y),cy=Math.cos(y),sz=Math.sin(z),cz=Math.cos(z);
    const d=point.map((v,i) => v-meta.camera.position[i]);
    const px=d[0]*cz*cy+d[1]*sz*cy-d[2]*sy;
    const py=d[0]*(cz*sy*sx-sz*cx)+d[1]*(sz*sy*sx+cz*cx)+d[2]*cy*sx;
    const native=[meta.width/2+px*meta.width/meta.camera.ortho_scale,meta.height/2-py*meta.width/meta.camera.ortho_scale];
    if (!native.every(Number.isFinite)) throw new Error('Invalid native projection');
    return native;
  };
  const focusPoint = async (meta, point, zooms, framePoints = []) => {
    const native=projectWorld(meta,point), nativeFrame=framePoints.map(p=>projectWorld(meta,p));
    const boundsNow = () => page.evaluate(({p,frame,w,h}) => {
      const image=document.querySelector('.atlas-map .leaflet-image-layer').getBoundingClientRect();
      const map=document.querySelector('.atlas-map').getBoundingClientRect();
      const screen=q=>[image.left+q[0]*image.width/w,image.top+q[1]*image.height/h];
      const projected=screen(p);
      return {x:projected[0],y:projected[1],cx:map.left+map.width/2,cy:map.top+map.height/2,
        w:map.width,h:map.height,left:map.left,top:map.top,right:map.right,bottom:map.bottom,
        image_width:image.width, native_to_screen_scale:image.width/w, frame:frame.map(screen)};
    },{p:native,frame:nativeFrame,w:meta.width,h:meta.height});
    const recenter = async () => {
      for (let attempt=0;attempt<12;attempt++) {
        const bounds=await boundsNow();
        if (Math.hypot(bounds.cx-bounds.x,bounds.cy-bounds.y)<3) return;
        await page.mouse.move(bounds.cx,bounds.cy);await page.mouse.down();
        await page.mouse.move(bounds.cx+Math.max(-bounds.w*.4,Math.min(bounds.w*.4,bounds.cx-bounds.x)),
          bounds.cy+Math.max(-bounds.h*.4,Math.min(bounds.h*.4,bounds.cy-bounds.y)),{steps:12});
        await page.mouse.up();await ready();
      }
      const bounds=await boundsNow();
      if (Math.hypot(bounds.cx-bounds.x,bounds.cy-bounds.y)>=3) throw new Error('Real map drag did not centre retained point: '+JSON.stringify(bounds));
    };
    await recenter();
    for(let i=0;i<zooms;i++) {
      await ready();
      if (await page.getByRole('button',{name:'放大地图',exact:true}).isDisabled()) break;
      const bounds=await boundsNow();
      // The existing UI zoom button advances by .5. Conservatively keep all
      // verified target centres / pitch corners inside the real map viewport.
      if (bounds.frame.some(([x,y])=>Math.abs(x-bounds.cx)*Math.SQRT2>bounds.w/2-32 || Math.abs(y-bounds.cy)*Math.SQRT2>bounds.h/2-32)) break;
      if(bounds.native_to_screen_scale*Math.SQRT2>1.6)break;
      const oldWidth=await page.locator('.atlas-map .leaflet-image-layer').evaluate(el => el.getBoundingClientRect().width);
      await page.getByRole('button',{name:'放大地图',exact:true}).click();
      await page.waitForFunction(w => document.querySelector('.atlas-map .leaflet-image-layer').getBoundingClientRect().width>w+1,oldWidth);
      await ready();
    }
    await recenter();
    const bounds=await boundsNow();
    if (bounds.frame.some(([x,y])=>x<bounds.left+24 || x>bounds.right-24 || y<bounds.top+24 || y>bounds.bottom-24)) throw new Error('Detail targets clipped by map viewport: '+JSON.stringify(bounds));
    return {source_point_world:point,source_point_native:native,source_frame_world:framePoints,source_frame_native:nativeFrame,
      final_screen_frame:bounds.frame,centre_error_px:Math.hypot(bounds.cx-bounds.x,bounds.cy-bounds.y),
      final_image_width_px:bounds.image_width,native_to_screen_scale:bounds.native_to_screen_scale,
      viewport_constraint:{bounds_px:[bounds.left,bounds.top,bounds.right,bounds.bottom],margin_px:24,frame_point_count:framePoints.length},
      method:'Projected retained source coordinates using formal camera; real map drag and zoom buttons'};
  };
  const frameFromBounds=b=>[b[0],b[1]].flatMap(x=>[b[2],b[3]].flatMap(y=>[b[4],b[5]].map(z=>[x,y,z])));
  const inspect=async(name,region,b,criterion)=>{
    await goto('?view=atlas&area='+region);
    const centre=[(b[0]+b[1])/2,(b[2]+b[3])/2,(b[4]+b[5])/2];
    const focus=await focusPoint(meta,centre,12,frameFromBounds(b));
    await shot(name,criterion,focus);
  };
  await shot('overview','Whole campus: source-mask continuity, 130 original roofs and 7 refreshed source points');
  await goto('?view=atlas&area=south');await shot('south','Southern street-block scale: changed turf with source footprints and original building/tree positions');
  const beds=meta.checks.landscape_detail.beds.beds;
  for(const [key,name] of [['garden-island-centre','island'],['garden-east-courses','east-rows']]){
    const r=beds.find(r=>r.source_key===key),[lo,hi]=r.world_bounds_m;
    await inspect(name,'south',[lo[0]-8,hi[0]+8,lo[1]-8,hi[1]+8,lo[2],hi[2]],'Estimated ground-contact low foliage inside retained '+key+' cap');
  }
  const formal=beds.filter(r=>r.source_key.startsWith('E formal'));
  const lo=[0,1,2].map(i=>Math.min(...formal.map(r=>r.world_bounds_m[0][i]))),hi=[0,1,2].map(i=>Math.max(...formal.map(r=>r.world_bounds_m[1][i])));
  await inspect('formal-beds','extension',[lo[0]-12,hi[0]+12,lo[1]-12,hi[1]+12,lo[2],hi[2]],'Both retained formal beds and coarse courses in their existing surrounding plaza');
  for(const [id,name]of [['N34 academic court','north-court'],['E formal garden plaza','formal-court'],['M field pedestrian wedge','middle-court']]){
    const r=meta.checks.landscape_detail.courtyards.sites.find(r=>r.source_id===id),b=r.source_world_bounds;
    await inspect(name,r.region,[b[0]-5,b[2]+5,b[1]-5,b[3]+5,b[4],b[4]+16],'Original '+id+' footprint, inset perimeter/cross paving courses, retained planting and roof exclusions');
  }
  for(const [ids,name,region] of [[['M01','M02','M03'],'facade-middle','middle'],[['E21','E24','E26','E27'],'facade-extension','extension']]){
    await goto('?view=atlas&area='+region);
    const roof=ids.flatMap(id=>meta.roof_faces_world[id].flat()), lo=[0,1,2].map(i=>Math.min(...roof.map(p=>p[i]))), hi=[0,1,2].map(i=>Math.max(...roof.map(p=>p[i])));
    const frame=frameFromBounds([lo[0]-10,hi[0]+10,lo[1]-10,hi[1]+10,0,hi[2]]), centre=[(lo[0]+hi[0])/2,(lo[1]+hi[1])/2,hi[2]/2];
    const focus=await focusPoint(meta,centre,12,frame);
    await shot(name,name==='facade-middle'?'Retained M01/M02/M03 family and adjacent middle paving edge: source roofs, bounded low-contrast course and conservative rounding':'Retained E21/E24/E26/E27 facade control: role-specific wall, window, sill and structural materials; source outlines',focus,true);
  }
  // New retained planting support bounds are injected after native validation.
  const plantingSites=meta.checks.site_finish.planting.sites;
  assert(plantingSites.length>0,'No retained planting sites');
  const plantingTarget=plantingSites.find(r=>r.source_key?.includes('academic')) || plantingSites[0];
  const pb=plantingTarget.world_bounds_m,[pl,ph]=pb;
  await goto('?view=atlas&area=north');
  const pframe=frameFromBounds([pl[0]-12,ph[0]+12,pl[1]-12,ph[1]+12,pl[2],ph[2]+1]);
  const pfocus=await focusPoint(meta,[(pl[0]+ph[0])/2,(pl[1]+ph[1])/2,(pl[2]+ph[2])/2],12,pframe);
  await shot('planting-north','Low foliage on actual retained narrow source cap, without added tree centres',pfocus,true);
  await goto('?view=atlas&area=all&category=dining');
  assert(await page.locator('.atlas-places button[data-record]').count()===5,'Dining list differs after native promotion');
  const active=await page.locator('[data-atlas-id]').evaluateAll(ns=>ns.filter(n=>getComputedStyle(n).pointerEvents!=='none').map(n=>n.dataset.atlasId));
  assert(active.length===5,'Dining map/list mismatch');
  await shot('dining','Five retained dining records remain synchronized with current native map');
  await page.setViewportSize({width:390,height:844});await goto('?view=atlas&area=lake&building=B06');
  const nonoverlap=await page.evaluate(()=>{
    const roof=document.querySelector('[data-atlas-id="B06"]').getBoundingClientRect(),card=document.querySelector('.atlas-detail').getBoundingClientRect();
    return {roof_bottom:roof.bottom,card_top:card.top,gap:card.top-roof.bottom};
  });assert(nonoverlap.gap>=10,'Mobile B06 roof/card overlap');checks.push({mobile_b06:nonoverlap});
  await shot('mobile','Current native lake/B06 selection above the mobile detail card');
  await goto('?view=atlas&area=all&place=place:gate3');await page.reload();await ready();
  assert(await page.locator('.atlas-detail h2').innerText()==='3号门','Source point refresh');
  const point=await page.evaluate(()=>{
    const p=document.querySelector('[data-atlas-id="place:gate3"]').getBoundingClientRect(),img=document.querySelector('.leaflet-image-layer').getBoundingClientRect();return {actual:[p.x+p.width/2,p.y+p.height/2],image:[img.x,img.y,img.width,img.height]};
  });const record=meta.map_places.records.find(r=>r.id==='place:gate3');
  const projected=[point.image[0]+record.anchor[0]*point.image[2]/meta.width,point.image[1]+record.anchor[1]*point.image[3]/meta.height];
  assert(Math.max(...projected.map((v,i)=>Math.abs(v-point.actual[i])))<1.2,'Re-exported source gate screen position');
  checks.push({point_refresh:'place:gate3',max_error_px:Math.max(...projected.map((v,i)=>Math.abs(v-point.actual[i])))});
  assert(errors.length===0,'Page/console errors: '+errors.join(','));
  return {status:'passed',image_sha256:meta.image_sha256,source_hashes:meta.sources,captures,checks,errors,limits:'Bounded current-image and source-point integration; no claim of entire source website parity, physical device, routing or every historical feature rerun.'};
}
