import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react'
import * as THREE from 'three'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { addLakeFinish } from './campusModelDetails.js'
import { refineMaterials, foliageGeometry } from './campusModelStyle.js'
import photoUrl from '../model/central-campus/references/teach6.jpg?url'
import aerialUrl from '../model/central-campus/references/campus-aerial.jpg?url'
import { Buildings, HouseLine, Compass, MapTrifold, Tag, Info } from '@phosphor-icons/react'
import modelUrl from '../model/campus/campus.glb?url'

const centralNames = { B06: '六号教学楼', B07: '湖西庭院建筑', B08: '湖东北建筑群' }

export default forwardRef(function CampusModelPreview(_, ref) {
  const hostRef = useRef(null)
  const api = useRef({})
  const [status, setStatus] = useState('正在加载校园模型…')
  const [failed, setFailed] = useState(false)
  const [items, setItems] = useState([])
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState(null)
  const [hovered, setHovered] = useState('')
  const [plan, setPlan] = useState(false)
  const [filter, setFilter] = useState('all')
  const [labels, setLabels] = useState([])
  const [labelsOn, setLabelsOn] = useState(true)
  const [infoOpen, setInfoOpen] = useState(false)
  const [viewName, setViewName] = useState('中央校区')
  const filterRef = useRef('all')
  const labelsOnRef = useRef(true)
  useImperativeHandle(ref, () => ({
    focusCentral: () => api.current.central?.(),
    zoomIn: () => api.current.zoom?.(1.4),
    zoomOut: () => api.current.zoom?.(1 / 1.4),
    fitCampus: () => api.current.fit?.(),
    locateCampus: () => api.current.fit?.(),
  }), [])

  useEffect(() => {
    const host = hostRef.current
    let renderer, controls, observer, frame = 0, disposed = false, model, disposeFinish
    const decoder = new DRACOLoader().setDecoderPath(`${import.meta.env.BASE_URL}draco/`).setWorkerLimit(2)
    const scene = new THREE.Scene()
    scene.background = new THREE.Color('#c5ceba')
    const camera = new THREE.OrthographicCamera(-1000, 1000, 600, -600, 1, 20000)
    const raycaster = new THREE.Raycaster()
    const pointer = new THREE.Vector2()
    const pickables = [], records = new Map()
    let chosen = null, hoveredObject = null, down = null, isPlan = false, fitHeight = 2000, lastHoverTime = 0
    const center = new THREE.Vector3()
    const centralBox = new THREE.Box3()
    let area = 'central'
    const sun = new THREE.DirectionalLight(0xfff4df, 2.7)
    sun.position.set(-600, 1400, 400)
    scene.add(sun, new THREE.HemisphereLight(0xe9f3ff, 0x6e775e, 1.0))
    const outlineMaterial = new THREE.LineBasicMaterial({ color: 0x1769e0, depthTest: true, transparent: true, opacity: .38 })
    let outline
    function updateLabels() {
      if (!labelsOnRef.current) { setLabels([]); return }
      const w=host.clientWidth,h=host.clientHeight, occupied=[], result=[]
      const candidates=[...records.values()].filter(r => filterRef.current === 'all' || (filterRef.current === 'central' ? r.id.startsWith('B0') : r.kind === filterRef.current)).sort((a,b) => Number(b.id.startsWith('B0'))-Number(a.id.startsWith('B0')) || a.id.localeCompare(b.id))
      for (const r of candidates) {
        if (!r.id.startsWith('B0') && fitHeight/camera.zoom > 700) continue
        const anchor=r.anchor.clone().project(camera),x=(anchor.x+1)*w/2,y=(1-anchor.y)*h/2
        const width=Math.min(170,r.name.length*10+20)
        if (anchor.z < -1 || anchor.z > 1 || x<(w<600 && y>300 ? 60 : 95) || x>w-(w<600 ? 60 : 90) || y<150 || y>h-105) continue
        if (occupied.some(p => Math.abs(p.x-x)<(p.width+width)/2+12 && Math.abs(p.y-y)<38)) continue
        occupied.push({x,y,width}); result.push({id:r.id,name:r.name,x,y,obj:r.obj})
        if(result.length >= (w < 600 ? 5 : 10)) break
      }
      setLabels(result)
    }
    const render = () => { frame = 0; if (!disposed && renderer) { renderer.render(scene, camera); updateLabels() } }
    const invalidate = () => { if (!frame && !disposed) frame = requestAnimationFrame(render) }
    function orient() {
      const offset = isPlan ? new THREE.Vector3(0, 3000, .01) : new THREE.Vector3(1700, 2050, 500)
      camera.up.set(0, 1, 0)
      // North lies to the right in the source render; preserve this in plan view.
      if (isPlan) camera.up.set(-1, 0, 0)
      camera.position.copy(controls.target).add(offset)
      camera.lookAt(controls.target)
      controls.update()
    }
    function resize() {
      const w = host.clientWidth, h = host.clientHeight
      if (!w || !h) return
      renderer.setSize(w, h)
      const aspect = w / h
      camera.left = -fitHeight * aspect / 2; camera.right = fitHeight * aspect / 2
      camera.top = fitHeight / 2; camera.bottom = -fitHeight / 2
      camera.updateProjectionMatrix(); invalidate()
    }
    function fit() {
      if (!model) return
      area = 'all'; setViewName('全校总览')
      controls.target.copy(center); orient()
      camera.updateMatrixWorld()
      const box = new THREE.Box3().setFromObject(model)
      const projected = []
      for (const x of [box.min.x, box.max.x]) for (const y of [box.min.y, box.max.y]) for (const z of [box.min.z, box.max.z]) projected.push(new THREE.Vector3(x,y,z).applyMatrix4(camera.matrixWorldInverse))
      const extent = new THREE.Box3().setFromPoints(projected).getSize(new THREE.Vector3())
      fitHeight = Math.max(extent.y, extent.x / (host.clientWidth / host.clientHeight)) * 1.12
      camera.zoom = 1; resize(); tuneShadow(center, 1600)
    }
    function tuneShadow(target, span) {
      sun.position.copy(target).add(new THREE.Vector3(-800, 1800, 600)); sun.target.position.copy(target)
      sun.shadow.camera.left=-span; sun.shadow.camera.right=span; sun.shadow.camera.top=span; sun.shadow.camera.bottom=-span
      sun.shadow.camera.updateProjectionMatrix(); sun.shadow.needsUpdate=true; invalidate()
    }
    function central() {
      if (!model || centralBox.isEmpty()) return
      area='central'; setViewName('中央校区'); const next=centralBox.getCenter(new THREE.Vector3())
      controls.target.copy(next); orient()
      fitHeight=host.clientWidth < 600 ? 650 : 360
      camera.zoom=1; resize(); tuneShadow(next, 430)
    }
    function highlight(obj) {
      if (outline) { scene.remove(outline); outline.geometry.dispose(); outline = null }
      if (!obj) { invalidate(); return }
      // Draw actual mesh edges; selection follows the building geometry, including courtyards.
      const meshes = []
      obj.traverse(child => { if (child.isMesh) meshes.push(child) })
      outline = new THREE.Group()
      for (const mesh of meshes) {
        const lines = new THREE.LineSegments(new THREE.EdgesGeometry(mesh.geometry, 35), outlineMaterial)
        lines.applyMatrix4(mesh.matrixWorld); lines.renderOrder = 10; outline.add(lines)
      }
      // Group disposal helper used on every selection change.
      outline.geometry = { dispose: () => outline?.traverse(child => { if (child.isLineSegments) child.geometry.dispose() }) }
      scene.add(outline); invalidate()
    }
    function select(obj, focus = false) {
      chosen = obj; setSelected(obj ? records.get(obj) : null); highlight(obj)
      if (obj && focus) {
        area = 'selection'; setViewName(records.get(obj).name)
        const box = new THREE.Box3().setFromObject(obj)
        const next = box.getCenter(new THREE.Vector3())
        const delta = next.clone().sub(controls.target)
        controls.target.copy(next); camera.position.add(delta)
        camera.zoom = Math.min(12, Math.max(2.5, fitHeight / 320))
        camera.updateProjectionMatrix(); controls.update(); tuneShadow(next, 300); invalidate()
      }
    }
    function hit(event) {
      const rect = renderer.domElement.getBoundingClientRect()
      pointer.set((event.clientX - rect.left) / rect.width * 2 - 1, -(event.clientY - rect.top) / rect.height * 2 + 1)
      raycaster.setFromCamera(pointer, camera)
      let obj = raycaster.intersectObjects(pickables, true)[0]?.object
      while (obj && !records.has(obj)) obj = obj.parent
      return obj || null
    }
    function move(event) {
      if (down || event.pointerType === 'touch' || performance.now() - lastHoverTime < 60) return
      lastHoverTime = performance.now()
      const obj = hit(event)
      if (obj === hoveredObject) return
      hoveredObject = obj; setHovered(obj ? records.get(obj).name : '')
      host.style.cursor = obj ? 'pointer' : 'grab'; highlight(obj || chosen)
    }
    const pointerDown = event => { down = { x: event.clientX, y: event.clientY, id: event.pointerId } }
    const pointerUp = event => {
      if (down && down.id === event.pointerId && Math.hypot(event.clientX - down.x, event.clientY - down.y) < 6) select(hit(event))
      down = null
    }
    const cancel = () => { down = null }
    const leave = () => { hoveredObject = null; setHovered(''); highlight(chosen) }
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' })
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5))
      renderer.outputColorSpace = THREE.SRGBColorSpace
      renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.0
      renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFShadowMap
      renderer.domElement.setAttribute('aria-label', '三维校园模型：拖拽平移，滚轮或双指缩放；也可搜索建筑')
      host.appendChild(renderer.domElement)
      controls = new OrbitControls(camera, renderer.domElement)
      controls.enableRotate = false; controls.enableDamping = false
      controls.screenSpacePanning = true; controls.minZoom = .6; controls.maxZoom = 18
      controls.mouseButtons.LEFT = THREE.MOUSE.PAN
      controls.touches.ONE = THREE.TOUCH.PAN; controls.touches.TWO = THREE.TOUCH.DOLLY_PAN
      controls.addEventListener('change', invalidate)
      observer = new ResizeObserver(() => { if (model && camera.zoom === 1 && !chosen) { if (area === 'central') central(); else fit() } else resize() }); observer.observe(host)
      renderer.domElement.addEventListener('pointerdown', pointerDown)
      renderer.domElement.addEventListener('pointerup', pointerUp)
      renderer.domElement.addEventListener('pointercancel', cancel)
      renderer.domElement.addEventListener('pointermove', move)
      renderer.domElement.addEventListener('pointerleave', leave)
      new GLTFLoader().setDRACOLoader(decoder).load(modelUrl, gltf => {
        if (disposed) { release(gltf.scene); return }
        model = gltf.scene
        let authoredSurfaces = false
        model.traverse(obj => { if (obj.userData.refinement_version === 'source-aligned-campus-1') authoredSurfaces = true })
        // Instance shared crowns while preserving the current model's authored leaf geometry.
        const crowns = new Map(), toRemove = []
        model.updateMatrixWorld(true)
        model.traverse(obj => {
          if (obj.parent === model && /^Canopy/.test(obj.name)) {
            // glTF can split a multi-material crown into a group of meshes.
            // Spatial batches allow offscreen campus blocks to be culled when zoomed in.
            obj.traverse(part => {
              if (!part.isMesh) return
              const materials = (Array.isArray(part.material) ? part.material : [part.material]).map(material => material.uuid).join(':')
              const x = Math.floor(part.matrixWorld.elements[12] / 160), z = Math.floor(part.matrixWorld.elements[14] / 160)
              const key = `${part.geometry.uuid}:${materials}:${x}:${z}`
              if (!crowns.has(key)) crowns.set(key, [])
              crowns.get(key).push(part)
            })
            toRemove.push(obj)
          }
          const id = obj.userData.id || (/^B0[678][ _]Central/.test(obj.name) ? obj.name.slice(0, 3) : null)
          if (!id || obj.parent !== model) return
          const data = obj.userData
          const record = { id, name: centralNames[id] || data.name || obj.name, floors: data.floors_estimate, height: data.height_estimate_m, roof: data.roof, kind: data.kind, obj, anchor: new THREE.Box3().setFromObject(obj).getCenter(new THREE.Vector3()) }
          record.anchor.y = new THREE.Box3().setFromObject(obj).max.y + 3
          if (centralNames[id]) centralBox.union(new THREE.Box3().setFromObject(obj))
          records.set(obj, record); pickables.push(obj)
        })
        for (const group of crowns.values()) {
          const geometry = authoredSurfaces ? group[0].geometry : foliageGeometry(crowns.size + group[0].id % 4)
          const instanced = new THREE.InstancedMesh(geometry, group[0].material, group.length)
          group.forEach((obj, index) => instanced.setMatrixAt(index, obj.matrixWorld))
          instanced.computeBoundingSphere()
          model.add(instanced)
        }
        toRemove.forEach(obj => obj.removeFromParent())
        disposeFinish = refineMaterials(model, invalidate, { preserveAuthored: authoredSurfaces })
        // The source image reveals offset in the earlier display-only road ribbons.
        // Keep those meshes in the saved GLB, but use observed imagery pavement in this preview.
        if (!authoredSurfaces) {
          model.traverse(obj => { if (/^(Road_(asphalt|paving)_union|Site_ground_union|north-plaza|north-parking|center-parking|center-west-field|south-field|north-garden)$/.test(obj.name)) obj.visible=false })
          addLakeFinish(model)
        }
        model.traverse(obj => { if (obj.isMesh) {
          obj.receiveShadow = true
          let building=obj; while(building && !records.has(building)) building=building.parent
          obj.castShadow=Boolean(building) || obj.isInstancedMesh
        } })
        sun.castShadow = true; sun.shadow.autoUpdate = false; sun.shadow.needsUpdate = true; sun.shadow.mapSize.set(2048, 2048)
        sun.shadow.camera.left = -1600; sun.shadow.camera.right = 1600
        sun.shadow.camera.top = 1600; sun.shadow.camera.bottom = -1600
        sun.shadow.camera.far = 6000; sun.shadow.bias = -.00008; sun.shadow.normalBias = 1
        scene.add(model)
        new THREE.Box3().setFromObject(model).getCenter(center)
        sun.position.copy(center).add(new THREE.Vector3(-800, 2200, 600)); sun.target.position.copy(center); scene.add(sun.target)
        setItems([...records.values()].sort((a,b) => a.id.localeCompare(b.id)))
        setStatus(''); central()
      }, event => {
        if (!disposed) setStatus(event.total ? `正在加载校园模型 ${Math.round(event.loaded / event.total * 100)}%` : '正在解码建筑与材质…')
      }, () => { if (!disposed) { setFailed(true); setStatus('模型加载失败，请刷新重试或切换卫星影像。') } })
      api.current = {
        fit, select, central, refresh: invalidate,
        zoom: factor => { camera.zoom = THREE.MathUtils.clamp(camera.zoom * factor, .6, 18); camera.updateProjectionMatrix(); invalidate() },
        plan: value => { isPlan = value; if (area === 'selection') { orient(); resize(); tuneShadow(controls.target, 300) } else if (area === 'central') central(); else fit() },
      }
    } catch {
      setFailed(true); setStatus('当前设备无法启动三维预览，请切换卫星影像。')
    }
    function release(root) {
      const geometries = new Set(), materials = new Set()
      root.traverse(obj => { if (obj.geometry?.dispose) geometries.add(obj.geometry); if (obj.material) (Array.isArray(obj.material) ? obj.material : [obj.material]).forEach(m => materials.add(m)) })
      geometries.forEach(g => g.dispose()); materials.forEach(m => { for (const value of Object.values(m)) if (value?.isTexture) value.dispose(); m.dispose() })
    }
    return () => {
      disposed = true; cancelAnimationFrame(frame); observer?.disconnect(); controls?.dispose(); decoder.dispose()
      disposeFinish?.()
      if (model) release(model)
      if (outline) outline.geometry.dispose()
      outlineMaterial.dispose(); renderer?.dispose(); renderer?.domElement.remove(); api.current = {}
    }
  }, [])

  const matches = items.filter(item => (filter === 'all' || (filter === 'central' ? item.id.startsWith('B0') : item.kind === filter)) && (!query.trim() || `${item.id} ${item.name}`.toLowerCase().includes(query.trim().toLowerCase()))).slice(0, 12)
  return <div className="model-preview">
    <div className="model-canvas" ref={hostRef} />
    <nav className="model-category-rail" aria-label="模型区域分类">{[{id:'all',name:'全校',icon:Compass},{id:'central',name:'中央',icon:Buildings},{id:'dorm',name:'公寓',icon:HouseLine},{id:'service',name:'服务',icon:MapTrifold}].map(item => <button key={item.id} type="button" aria-pressed={filter===item.id} onClick={() => { setFilter(item.id); filterRef.current=item.id; api.current.refresh?.(); if(item.id==='central') api.current.central?.(); if(item.id==='all') {setQuery('');api.current.fit?.()} }}><item.icon size={23} /><span>{item.name}</span></button>)}</nav>
    <div className="model-labels">{labels.map(label => <button key={label.id} style={{left:label.x,top:label.y}} type="button" onClick={() => api.current.select?.(label.obj)}>{label.name}</button>)}</div>
    <div className="model-context"><span>{viewName} · 校园外观模型</span><small>卫星轮廓 / 照片参考 / 高度估算</small></div>
    {status && <div className={`model-status${failed ? ' is-error' : ''}`} role="status">{status}</div>}
    <div className="model-search">
      <input aria-label="搜索模型建筑" placeholder="搜索模型建筑 / 编号，如 六号、N01" value={query} onChange={e => setQuery(e.target.value)} />
      {query && <button type="button" aria-label="清空模型搜索" onClick={() => setQuery('')}>×</button>}
      {(query.trim() || filter !== 'all') && <div className="model-results">{matches.length ? matches.map(item => <button key={item.id} type="button" onClick={() => { api.current.select?.(item.obj, true); setQuery(''); setFilter('all'); filterRef.current='all' }}><b>{item.id}</b>{item.name}</button>) : <p>{status ? '模型加载后可搜索' : '未找到建筑，请尝试区域名称或编号'}</p>}</div>}
    </div>
    <div className="model-view-switch"><button type="button" aria-label="显示建筑标签" aria-pressed={labelsOn} onClick={() => {setLabelsOn(!labelsOn);labelsOnRef.current=!labelsOn;api.current.refresh?.()}}><Tag size={17} />楼名</button><button type="button" aria-pressed={plan} onClick={() => { setPlan(!plan); api.current.plan?.(!plan) }}>{plan ? '鸟瞰视角' : '俯视校核'}</button></div>
    {hovered && !selected && <div className="model-hover">{hovered}</div>}
    {selected && <article className="model-building-card" aria-label="模型建筑详情">
      <button className="model-close" type="button" aria-label="关闭建筑详情" onClick={() => api.current.select?.(null)}>×</button>
      {centralNames[selected.id] && <img className="model-source-photo" src={selected.id==='B06' ? photoUrl : aerialUrl} alt={selected.id==='B06' ? '校方六号教学楼照片' : '校方中央校区航拍，展示楼群与湖岸'} />}
      <small>建筑 {selected.id} · 外观模型</small><h3>{selected.name}</h3>
      <p>{selected.height ? `估算 ${selected.floors} 层 · 主体高度 ${selected.height} 米` : '高度及立面依据照片估算'}</p>
      <p>屋顶轮廓依据卫星影像描绘。{selected.id === 'B06' ? '六号教学楼已关联校方照片。' : '区域描述不代表已确认的正式楼号。'}</p>
    </article>}
    <button className="model-info-toggle" type="button" onClick={() => setInfoOpen(!infoOpen)} aria-expanded={infoOpen}><Info size={17} />资料说明</button>
    {infoOpen && <div className="model-info-panel"><strong>本次展示范围</strong><p>全校 127 个建筑部分与中央 3 组细化建筑，按本校卫星轮廓和照片建模。校内显示建筑、道路、铺装与绿化，外围以 Esri 固定影像衔接周边。</p><p>楼高、窗格、阳台及未见立面为估算；未核实名称使用区域描述。影像屋顶轮廓不等于实测落地边界，道路显示尚未验证为可通行导航网络。</p></div>}
    <div className="model-help">拖拽平移 · 滚轮 / 双指缩放 · 点击建筑<span>地表影像 © Esri · 高度估算</span></div>
  </div>
})
