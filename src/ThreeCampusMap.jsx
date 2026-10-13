import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { allPlaces } from './campusData.js'

const MODEL_WIDTH = 1600
const MODEL_DEPTH = 920
const MAX_INITIAL_VIEW_HEIGHT = 1450

const MODEL_PLACES = {
  gate1: [690, 235], gate2: [-625, 205], gate3: [-650, -185],
  welcome: [42, 118], admin: [-185, -18], library: [105, 45],
  innovation: [-355, 12], teach5: [-42, -88], teach6: [330, 12],
  engineering: [205, -104], scotland: [455, -72], north_dining: [505, -174],
  south_dining: [-62, 22], new_dining: [-300, -64], commerce: [184, 58],
  express: [245, 18], health: [-94, -92], dorm32: [555, 62],
  dorm20: [-430, 28], north_track: [565, -276], central_track: [4, 142],
  south_track: [-555, -246],
}

const MODEL_BUILDINGS = [
  { id: 'admin', x: -185, z: -18, w: 70, d: 54, h: 64, color: 0xd4c7ad, roof: 0xb76d54 },
  { id: 'library', x: 105, z: 45, w: 102, d: 64, h: 78, color: 0xc7cec9, roof: 0x667b76 },
  { id: 'innovation', x: -355, z: 12, w: 82, d: 46, h: 48, color: 0xd2cab8, roof: 0x8f6353 },
  { id: 'teach5', x: -42, z: -88, w: 104, d: 34, h: 56, color: 0xc9c4b8, roof: 0x75817e },
  { id: 'teach6', x: 330, z: 12, w: 112, d: 38, h: 60, color: 0xcac7bb, roof: 0x727b78 },
  { id: 'engineering', x: 205, z: -104, w: 116, d: 46, h: 72, color: 0xc4c9c6, roof: 0x65726f },
  { id: 'scotland', x: 455, z: -72, w: 88, d: 48, h: 62, color: 0xd3c7b8, roof: 0x9c6351 },
  { id: 'north_dining', x: 505, z: -174, w: 92, d: 52, h: 34, color: 0xd7cbbb, roof: 0xa3614a },
  { id: 'south_dining', x: -62, z: 22, w: 76, d: 48, h: 34, color: 0xd6c9b7, roof: 0x9b5f49 },
  { id: 'new_dining', x: -300, z: -64, w: 78, d: 46, h: 34, color: 0xd4c8b7, roof: 0xa96850 },
  { id: 'commerce', x: 184, z: 58, w: 132, d: 28, h: 26, color: 0xd7cdbc, roof: 0x8d5d4a },
  { id: 'dorm32', x: 555, z: 62, w: 74, d: 30, h: 66, color: 0xcac6bb, roof: 0x6d7774 },
  { id: 'dorm20', x: -430, z: 28, w: 76, d: 30, h: 64, color: 0xc9c4b8, roof: 0x727a77 },
]

const EXTRA_BUILDINGS = [
  [-520, -75, 72, 28, 58], [-520, -120, 72, 28, 58], [-520, -165, 72, 28, 58],
  [-438, -82, 68, 28, 58], [-438, -128, 68, 28, 58], [-438, -174, 68, 28, 58],
  [-260, -142, 74, 30, 52], [-170, -142, 74, 30, 52], [-82, -142, 74, 30, 52],
  [70, -120, 76, 30, 54], [70, -168, 76, 30, 54],
  [292, -128, 72, 28, 56], [376, -128, 72, 28, 56], [460, -128, 72, 28, 56],
  [430, 56, 72, 28, 60], [430, 100, 72, 28, 60], [520, 108, 72, 28, 60],
  [600, -28, 72, 28, 60], [600, 16, 72, 28, 60], [600, 108, 72, 28, 60],
  [-600, -92, 58, 24, 48], [-600, -132, 58, 24, 48],
]

const FEATURED_LABELS = new Set(['admin', 'library', 'teach6', 'north_dining', 'dorm32', 'welcome'])

function roundedRectShape(width, height, radius) {
  const shape = new THREE.Shape()
  const x = -width / 2
  const y = -height / 2
  shape.moveTo(x + radius, y)
  shape.lineTo(x + width - radius, y)
  shape.quadraticCurveTo(x + width, y, x + width, y + radius)
  shape.lineTo(x + width, y + height - radius)
  shape.quadraticCurveTo(x + width, y + height, x + width - radius, y + height)
  shape.lineTo(x + radius, y + height)
  shape.quadraticCurveTo(x, y + height, x, y + height - radius)
  shape.lineTo(x, y + radius)
  shape.quadraticCurveTo(x, y, x + radius, y)
  return shape
}

function createTrack(width, depth) {
  const group = new THREE.Group()
  const outer = roundedRectShape(width, depth, depth / 2)
  const hole = roundedRectShape(width - 20, depth - 20, (depth - 20) / 2)
  outer.holes.push(hole)
  const track = new THREE.Mesh(
    new THREE.ShapeGeometry(outer, 32),
    new THREE.MeshStandardMaterial({ color: 0xb86650, roughness: 1 }),
  )
  track.rotation.x = -Math.PI / 2
  track.position.y = 1.1
  track.receiveShadow = true
  group.add(track)

  const field = new THREE.Mesh(
    new THREE.PlaneGeometry(width - 35, depth - 32),
    new THREE.MeshStandardMaterial({ color: 0x4c8350, roughness: 1 }),
  )
  field.rotation.x = -Math.PI / 2
  field.position.y = 1.2
  group.add(field)

  const lineMaterial = new THREE.LineBasicMaterial({ color: 0xdde8d5, transparent: true, opacity: 0.82 })
  const linePoints = [
    new THREE.Vector3(-(width - 35) / 2, 1.4, 0),
    new THREE.Vector3((width - 35) / 2, 1.4, 0),
  ]
  group.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(linePoints), lineMaterial))
  const centerCircle = new THREE.Mesh(
    new THREE.RingGeometry(11, 11.7, 40),
    new THREE.MeshBasicMaterial({ color: 0xdde8d5, side: THREE.DoubleSide }),
  )
  centerCircle.rotation.x = -Math.PI / 2
  centerCircle.position.y = 1.4
  group.add(centerCircle)
  return group
}

function createBuilding(definition, clickableMeshes, modelGroups) {
  const group = new THREE.Group()
  group.position.set(definition.x, 0, definition.z)
  group.rotation.y = definition.rotation || 0
  group.userData.placeId = definition.id

  const wallMaterial = new THREE.MeshStandardMaterial({
    color: definition.color,
    roughness: 0.78,
    metalness: 0.03,
  })
  const body = new THREE.Mesh(new THREE.BoxGeometry(definition.w, definition.h, definition.d), wallMaterial)
  body.position.y = definition.h / 2
  body.castShadow = true
  body.receiveShadow = true
  body.userData.placeId = definition.id
  group.add(body)

  const roof = new THREE.Mesh(
    new THREE.BoxGeometry(definition.w + 3, 3.5, definition.d + 3),
    new THREE.MeshStandardMaterial({ color: definition.roof, roughness: 0.9 }),
  )
  roof.position.y = definition.h + 1.75
  roof.castShadow = true
  group.add(roof)

  const windowMaterial = new THREE.MeshStandardMaterial({ color: 0x304a50, roughness: 0.45 })
  const floors = Math.max(2, Math.floor(definition.h / 12))
  for (let index = 1; index < floors; index += 1) {
    const strip = new THREE.Mesh(new THREE.BoxGeometry(definition.w * 0.88, 2.4, 0.8), windowMaterial)
    strip.position.set(0, index * (definition.h / floors), definition.d / 2 + 0.45)
    group.add(strip)
  }

  clickableMeshes.push(body)
  modelGroups.set(definition.id, group)
  return group
}

function createExtraBuilding([x, z, width, depth, height], index) {
  return createBuilding({
    id: `context-${index}`,
    x, z, w: width, d: depth, h: height,
    color: index % 3 === 0 ? 0xd0c8b8 : 0xc4cac6,
    roof: index % 4 === 0 ? 0x9a6550 : 0x697773,
  }, [], new Map())
}

function createRoad(width, depth, x, z, rotation = 0, color = 0x4a5152) {
  const road = new THREE.Mesh(
    new THREE.BoxGeometry(width, 1.6, depth),
    new THREE.MeshStandardMaterial({ color, roughness: 1 }),
  )
  road.position.set(x, 0.8, z)
  road.rotation.y = rotation
  road.receiveShadow = true
  return road
}

function createLabelSprite(text, featured = false) {
  const canvas = document.createElement('canvas')
  canvas.width = 512
  canvas.height = 144
  const context = canvas.getContext('2d')
  context.scale(2, 2)
  context.font = `${featured ? 700 : 650} ${featured ? 24 : 21}px "PingFang SC", "Microsoft YaHei", sans-serif`
  const measured = Math.min(214, Math.ceil(context.measureText(text).width + 42))
  context.fillStyle = 'rgba(255,255,255,.96)'
  context.strokeStyle = featured ? '#1769e0' : 'rgba(43,58,67,.22)'
  context.lineWidth = featured ? 3 : 2
  context.beginPath()
  context.roundRect(128 - measured / 2, 13, measured, 45, 10)
  context.fill()
  context.stroke()
  context.fillStyle = '#16232d'
  context.textAlign = 'center'
  context.textBaseline = 'middle'
  context.fillText(text, 128, 36)
  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  texture.minFilter = THREE.LinearFilter
  const material = new THREE.SpriteMaterial({ map: texture, transparent: true, depthTest: false })
  const sprite = new THREE.Sprite(material)
  sprite.scale.set(measured * 0.56, 38, 1)
  sprite.renderOrder = 20
  sprite.userData.baseScale = [measured * 0.56, 38]
  sprite.userData.featured = featured
  return sprite
}

function createTrees(scene) {
  const count = 260
  const trunk = new THREE.InstancedMesh(
    new THREE.CylinderGeometry(1.1, 1.5, 9, 6),
    new THREE.MeshStandardMaterial({ color: 0x6d5034, roughness: 1 }),
    count,
  )
  const crown = new THREE.InstancedMesh(
    new THREE.IcosahedronGeometry(6.8, 1),
    new THREE.MeshStandardMaterial({ color: 0x356a42, roughness: 1 }),
    count,
  )
  trunk.castShadow = true
  crown.castShadow = true
  const matrix = new THREE.Matrix4()
  let seed = 19
  const random = () => {
    seed = (seed * 9301 + 49297) % 233280
    return seed / 233280
  }
  for (let index = 0; index < count; index += 1) {
    const edge = index < 170
    const rowIndex = index - 170
    const x = edge
      ? -810 + random() * 1620
      : -700 + (rowIndex % 45) * (1400 / 44) + (random() - 0.5) * 7
    const z = edge
      ? (random() > 0.35 ? -455 + random() * 145 : 270 + random() * 115)
      : rowIndex < 45
        ? (rowIndex % 2 ? 171 : 238) + (random() - 0.5) * 6
        : (rowIndex % 2 ? -196 : -242) + (random() - 0.5) * 6
    const scale = 0.78 + random() * 0.65
    matrix.compose(
      new THREE.Vector3(x, 4.5, z),
      new THREE.Quaternion(),
      new THREE.Vector3(scale, scale, scale),
    )
    trunk.setMatrixAt(index, matrix)
    matrix.compose(
      new THREE.Vector3(x, 13 + scale * 2, z),
      new THREE.Quaternion(),
      new THREE.Vector3(scale, 0.92 * scale, scale),
    )
    crown.setMatrixAt(index, matrix)
  }
  scene.add(trunk, crown)
}

const ThreeCampusMap = forwardRef(function ThreeCampusMap({
  selectedPlace,
  route,
  origin,
  destination,
  onPlaceSelect,
  onMapPick,
}, ref) {
  const containerRef = useRef(null)
  const sceneRef = useRef(null)
  const cameraRef = useRef(null)
  const controlsRef = useRef(null)
  const rendererRef = useRef(null)
  const modelGroupsRef = useRef(new Map())
  const routeLineRef = useRef(null)
  const selectionBoxRef = useRef(null)
  const [ready, setReady] = useState(false)
  const [hoveredName, setHoveredName] = useState('')
  const callbackRef = useRef({ onPlaceSelect, onMapPick })
  const selectedPlaceRef = useRef(selectedPlace)
  callbackRef.current = { onPlaceSelect, onMapPick }
  selectedPlaceRef.current = selectedPlace

  useEffect(() => {
    const container = containerRef.current
    if (!container) return undefined

    const scene = new THREE.Scene()
    scene.background = new THREE.Color(0xdde5df)
    scene.fog = new THREE.Fog(0xdde5df, 1250, 2300)
    const camera = new THREE.OrthographicCamera(-800, 800, 480, -480, 1, 3200)
    camera.position.set(760, 980, 940)
    camera.lookAt(0, 0, 0)

    const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.setSize(container.clientWidth, container.clientHeight)
    renderer.outputColorSpace = THREE.SRGBColorSpace
    renderer.toneMapping = THREE.ACESFilmicToneMapping
    renderer.toneMappingExposure = 1.08
    renderer.shadowMap.enabled = true
    renderer.shadowMap.type = THREE.PCFSoftShadowMap
    container.appendChild(renderer.domElement)

    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enableRotate = false
    controls.enableDamping = true
    controls.dampingFactor = 0.08
    controls.screenSpacePanning = true
    controls.minZoom = 0.72
    controls.maxZoom = 3.4
    controls.mouseButtons.LEFT = THREE.MOUSE.PAN
    controls.mouseButtons.RIGHT = THREE.MOUSE.PAN
    controls.touches.ONE = THREE.TOUCH.PAN
    controls.touches.TWO = THREE.TOUCH.DOLLY_PAN
    controls.target.set(0, 0, 0)
    controls.update()

    scene.add(new THREE.HemisphereLight(0xf6fbff, 0x65765b, 2.4))
    const sun = new THREE.DirectionalLight(0xfff4dd, 3.2)
    sun.position.set(-520, 920, 520)
    sun.castShadow = true
    sun.shadow.mapSize.set(2048, 2048)
    sun.shadow.camera.left = -900
    sun.shadow.camera.right = 900
    sun.shadow.camera.top = 700
    sun.shadow.camera.bottom = -700
    scene.add(sun)

    const ground = new THREE.Mesh(
      new THREE.PlaneGeometry(1800, 1080),
      new THREE.MeshStandardMaterial({ color: 0x82a76d, roughness: 1 }),
    )
    ground.rotation.x = -Math.PI / 2
    ground.receiveShadow = true
    scene.add(ground)

    scene.add(createRoad(1580, 42, 0, 205, -0.035))
    scene.add(createRoad(1450, 28, 0, -218, 0.018, 0x535a58))
    scene.add(createRoad(35, 390, -625, 4, -0.12))
    scene.add(createRoad(32, 380, 640, 4, 0.05))
    scene.add(createRoad(29, 370, 175, -15, 0.02, 0x59605e))
    scene.add(createRoad(29, 310, -230, -35, -0.03, 0x59605e))

    const plaza = new THREE.Mesh(
      new THREE.PlaneGeometry(210, 126),
      new THREE.MeshStandardMaterial({ color: 0xc9c8b5, roughness: 1 }),
    )
    plaza.rotation.x = -Math.PI / 2
    plaza.position.set(70, 1.05, -12)
    scene.add(plaza)

    const lake = new THREE.Mesh(
      new THREE.CircleGeometry(62, 64),
      new THREE.MeshPhysicalMaterial({ color: 0x4c8f91, roughness: 0.22, metalness: 0.05, transparent: true, opacity: 0.92 }),
    )
    lake.rotation.x = -Math.PI / 2
    lake.scale.set(0.72, 1.22, 1)
    lake.position.set(385, 1.3, -82)
    scene.add(lake)

    const clickableMeshes = []
    const modelGroups = new Map()
    MODEL_BUILDINGS.forEach((building) => scene.add(createBuilding(building, clickableMeshes, modelGroups)))
    EXTRA_BUILDINGS.forEach((building, index) => scene.add(createExtraBuilding(building, index)))

    const tracks = [
      ['south_track', -555, -246, 128, 82],
      ['central_track', 4, 142, 146, 94],
      ['north_track', 565, -276, 132, 84],
    ]
    tracks.forEach(([id, x, z, width, depth]) => {
      const track = createTrack(width, depth)
      track.position.set(x, 0, z)
      scene.add(track)
      const hit = new THREE.Mesh(
        new THREE.BoxGeometry(width, 5, depth),
        new THREE.MeshBasicMaterial({ transparent: true, opacity: 0 }),
      )
      hit.position.set(x, 3, z)
      hit.userData.placeId = id
      scene.add(hit)
      clickableMeshes.push(hit)
      modelGroups.set(id, track)
    })

    createTrees(scene)

    const boundaryPoints = [
      [-755, 255], [-735, -310], [-560, -385], [610, -390], [760, -278],
      [748, 245], [520, 300], [-520, 298], [-755, 255],
    ].map(([x, z]) => new THREE.Vector3(x, 3, z))
    scene.add(new THREE.Line(
      new THREE.BufferGeometry().setFromPoints(boundaryPoints),
      new THREE.LineBasicMaterial({ color: 0xe8c257, transparent: true, opacity: 0.92 }),
    ))

    const labels = []
    Object.entries(MODEL_PLACES).forEach(([placeId, [x, z]]) => {
      const place = allPlaces.find((item) => item.id === placeId)
      if (!place) return
      const group = modelGroups.get(placeId)
      const height = MODEL_BUILDINGS.find((item) => item.id === placeId)?.h || (place.type === '运动' ? 12 : 20)
      const label = createLabelSprite(place.shortLabel || place.name, FEATURED_LABELS.has(placeId) || place.type === '校门')
      label.position.set(x, height + 22, z)
      label.userData.placeId = placeId
      labels.push(label)
      scene.add(label)
      if (group) group.userData.label = label
    })

    const raycaster = new THREE.Raycaster()
    const pointer = new THREE.Vector2()
    let hoveredMesh = null
    let pointerDown = null

    const raycast = (event) => {
      const rect = renderer.domElement.getBoundingClientRect()
      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1
      pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1
      raycaster.setFromCamera(pointer, camera)
      return raycaster.intersectObjects(clickableMeshes, false)[0]
    }

    const restoreMesh = (mesh) => {
      if (!mesh?.material?.emissive) return
      const selected = mesh.userData.placeId === selectedPlaceRef.current?.id
      mesh.material.emissive.setHex(selected ? 0x173b64 : 0x000000)
      mesh.material.emissiveIntensity = selected ? 0.38 : 0
    }

    const handlePointerMove = (event) => {
      const hit = raycast(event)
      const nextMesh = hit?.object || null
      if (nextMesh === hoveredMesh) return
      restoreMesh(hoveredMesh)
      hoveredMesh = nextMesh
      renderer.domElement.style.cursor = hoveredMesh ? 'pointer' : 'grab'
      if (hoveredMesh?.material?.emissive) {
        hoveredMesh.material.emissive.setHex(0x1769e0)
        hoveredMesh.material.emissiveIntensity = 0.34
      }
      const place = allPlaces.find((item) => item.id === hoveredMesh?.userData.placeId)
      setHoveredName(place?.name || '')
    }

    const handlePointerDown = (event) => { pointerDown = [event.clientX, event.clientY] }
    const handlePointerUp = (event) => {
      if (!pointerDown || Math.hypot(event.clientX - pointerDown[0], event.clientY - pointerDown[1]) > 5) return
      const hit = raycast(event)
      const place = allPlaces.find((item) => item.id === hit?.object?.userData.placeId)
      if (place) callbackRef.current.onPlaceSelect?.(place)
      else callbackRef.current.onMapPick?.({ modelX: pointer.x, modelY: pointer.y })
    }
    renderer.domElement.addEventListener('pointermove', handlePointerMove)
    renderer.domElement.addEventListener('pointerdown', handlePointerDown)
    renderer.domElement.addEventListener('pointerup', handlePointerUp)

    const resize = () => {
      const width = container.clientWidth
      const height = container.clientHeight
      const aspect = width / Math.max(height, 1)
      const fittedViewHeight = Math.min(
        MAX_INITIAL_VIEW_HEIGHT,
        Math.max(MODEL_DEPTH, MODEL_WIDTH / Math.max(aspect, 0.5)),
      )
      camera.userData.fittedViewHeight = fittedViewHeight
      camera.left = -fittedViewHeight * aspect / 2
      camera.right = fittedViewHeight * aspect / 2
      camera.top = fittedViewHeight / 2
      camera.bottom = -fittedViewHeight / 2
      camera.updateProjectionMatrix()
      renderer.setSize(width, height)
    }
    const resizeObserver = new ResizeObserver(resize)
    resizeObserver.observe(container)
    resize()

    let animationFrame
    const animate = () => {
      controls.update()
      const inverseZoom = 1 / camera.zoom
      labels.forEach((label) => {
        label.visible = label.userData.featured || camera.zoom >= 1.45
        label.scale.set(label.userData.baseScale[0] * inverseZoom, label.userData.baseScale[1] * inverseZoom, 1)
      })
      renderer.render(scene, camera)
      animationFrame = window.requestAnimationFrame(animate)
    }
    animate()

    sceneRef.current = scene
    cameraRef.current = camera
    controlsRef.current = controls
    rendererRef.current = renderer
    modelGroupsRef.current = modelGroups
    setReady(true)

    return () => {
      window.cancelAnimationFrame(animationFrame)
      resizeObserver.disconnect()
      renderer.domElement.removeEventListener('pointermove', handlePointerMove)
      renderer.domElement.removeEventListener('pointerdown', handlePointerDown)
      renderer.domElement.removeEventListener('pointerup', handlePointerUp)
      controls.dispose()
      scene.traverse((object) => {
        object.geometry?.dispose?.()
        if (Array.isArray(object.material)) object.material.forEach((material) => material.dispose())
        else object.material?.dispose?.()
      })
      renderer.dispose()
      renderer.domElement.remove()
    }
  }, [])

  useEffect(() => {
    const scene = sceneRef.current
    const camera = cameraRef.current
    const controls = controlsRef.current
    if (!scene || !camera || !controls) return

    if (selectionBoxRef.current) {
      scene.remove(selectionBoxRef.current)
      selectionBoxRef.current.geometry?.dispose?.()
      selectionBoxRef.current.material?.dispose?.()
      selectionBoxRef.current = null
    }
    modelGroupsRef.current.forEach((group, id) => {
      group.traverse((object) => {
        if (!object.material?.emissive) return
        object.material.emissive.setHex(id === selectedPlace?.id ? 0x173b64 : 0x000000)
        object.material.emissiveIntensity = id === selectedPlace?.id ? 0.34 : 0
      })
    })
    const selectedGroup = selectedPlace && modelGroupsRef.current.get(selectedPlace.id)
    if (!selectedGroup) return
    const selectionBox = new THREE.BoxHelper(selectedGroup, 0x1769e0)
    selectionBox.material.depthTest = false
    selectionBox.material.transparent = true
    selectionBox.material.opacity = 0.9
    selectionBox.renderOrder = 18
    scene.add(selectionBox)
    selectionBoxRef.current = selectionBox
    controls.target.set(selectedGroup.position.x, 0, selectedGroup.position.z)
    camera.zoom = Math.max(camera.zoom, 1.55)
    camera.updateProjectionMatrix()
    controls.update()
  }, [selectedPlace])

  useEffect(() => {
    const scene = sceneRef.current
    if (!scene) return
    if (routeLineRef.current) {
      scene.remove(routeLineRef.current)
      routeLineRef.current.geometry.dispose()
      routeLineRef.current.material.dispose()
      routeLineRef.current = null
    }
    if (route.length < 2 || !origin || !destination) return
    const start = MODEL_PLACES[origin.id]
    const end = MODEL_PLACES[destination.id]
    if (!start || !end) return
    const points = [
      new THREE.Vector3(start[0], 8, start[1]),
      new THREE.Vector3(start[0], 8, 205),
      new THREE.Vector3(end[0], 8, 205),
      new THREE.Vector3(end[0], 8, end[1]),
    ]
    const curve = new THREE.CatmullRomCurve3(points, false, 'catmullrom', 0.08)
    const routeMesh = new THREE.Mesh(
      new THREE.TubeGeometry(curve, 72, 4.2, 10, false),
      new THREE.MeshBasicMaterial({ color: 0x1769e0, depthTest: false }),
    )
    routeMesh.renderOrder = 16
    scene.add(routeMesh)
    routeLineRef.current = routeMesh
  }, [destination, origin, route])

  useImperativeHandle(ref, () => ({
    zoomIn: () => {
      const camera = cameraRef.current
      if (!camera) return
      camera.zoom = Math.min(3.4, camera.zoom * 1.28)
      camera.updateProjectionMatrix()
    },
    zoomOut: () => {
      const camera = cameraRef.current
      if (!camera) return
      camera.zoom = Math.max(0.72, camera.zoom / 1.28)
      camera.updateProjectionMatrix()
    },
    fitCampus: () => {
      if (!cameraRef.current || !controlsRef.current) return
      cameraRef.current.zoom = 1
      cameraRef.current.updateProjectionMatrix()
      controlsRef.current.target.set(0, 0, 0)
      controlsRef.current.update()
    },
    fitSurroundings: () => {},
    locateCampus: () => {
      if (!cameraRef.current || !controlsRef.current) return
      cameraRef.current.zoom = 1
      cameraRef.current.updateProjectionMatrix()
      controlsRef.current.target.set(0, 0, 0)
      controlsRef.current.update()
    },
  }), [])

  return (
    <div className="three-campus-map" aria-label="可拖拽、缩放和点击建筑的校园三维模型">
      <div ref={containerRef} className="three-campus-canvas" />
      {!ready && <div className="three-campus-loading"><span />正在构建校园模型</div>}
      <div className="three-campus-badge"><i />程序化几何模型 <span /> 非 AI 生成底图</div>
      {hoveredName && <div className="three-campus-hover">点击查看 <strong>{hoveredName}</strong></div>}
    </div>
  )
})

export default ThreeCampusMap
