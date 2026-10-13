import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { allPlaces, campusBuildings } from './campusData.js'

const CAMPUS_CENTER = [31.5751, 120.2219]
const CAMPUS_BOUNDS = L.latLngBounds([31.5658, 120.2162], [31.5860, 120.2280])
const SURROUNDING_BOUNDS = L.latLngBounds([31.5620, 120.2070], [31.5900, 120.2550])

const ILLUSTRATION_WIDTH = 1567
const ILLUSTRATION_HEIGHT = 1004
const ILLUSTRATION_BOUNDS = L.latLngBounds([0, 0], [ILLUSTRATION_HEIGHT, ILLUSTRATION_WIDTH])
const ILLUSTRATION_FIT_BOUNDS = L.latLngBounds([0, 0], [ILLUSTRATION_HEIGHT, ILLUSTRATION_WIDTH])

// Percentage positions are calibrated directly against the complete v7 HD base
// map and the official campus plan. They stay separate from public-map
// coordinates until the school can provide surveyed CAD/GIS control points.
const ILLUSTRATION_POSITIONS = {
  gate1: [0.84, 0.78], gate2: [0.22, 0.62], gate3: [0.27, 0.41],
  welcome: [0.50, 0.60], admin: [0.40, 0.52], library: [0.52, 0.58],
  innovation: [0.31, 0.52], teach5: [0.47, 0.50], teach6: [0.66, 0.59],
  engineering: [0.59, 0.62], scotland: [0.73, 0.59], north_dining: [0.75, 0.50],
  south_dining: [0.42, 0.48], new_dining: [0.34, 0.47], commerce: [0.54, 0.56],
  express: [0.56, 0.51], health: [0.45, 0.50], dorm32: [0.78, 0.64],
  dorm20: [0.33, 0.49], north_track: [0.83, 0.55], central_track: [0.46, 0.61],
  south_track: [0.25, 0.51],
}

function illustrationPoint(placeOrId) {
  const id = typeof placeOrId === 'string' ? placeOrId : placeOrId?.id
  const [xRatio, yRatio] = ILLUSTRATION_POSITIONS[id] || [0.5, 0.52]
  return illustrationRatioPoint(xRatio, yRatio)
}

function illustrationRatioPoint(xRatio, yRatio) {
  return [ILLUSTRATION_HEIGHT * (1 - yRatio), ILLUSTRATION_WIDTH * xRatio]
}

// Demo navigation follows the curved southern campus avenue visible in the
// illustration. Each endpoint joins its nearest point on this road spine.
const ILLUSTRATION_ROUTE_SPINE = [
  illustrationRatioPoint(0.05, 0.71),
  illustrationRatioPoint(0.22, 0.63),
  illustrationRatioPoint(0.38, 0.61),
  illustrationRatioPoint(0.52, 0.62),
  illustrationRatioPoint(0.65, 0.67),
  illustrationRatioPoint(0.75, 0.72),
  illustrationRatioPoint(0.84, 0.78),
  illustrationRatioPoint(0.94, 0.86),
]

function distanceSquared([latA, lngA], [latB, lngB]) {
  return (latA - latB) ** 2 + (lngA - lngB) ** 2
}

function nearestRouteSpineIndex(point) {
  return ILLUSTRATION_ROUTE_SPINE.reduce((bestIndex, candidate, index) => (
    distanceSquared(point, candidate) < distanceSquared(point, ILLUSTRATION_ROUTE_SPINE[bestIndex])
      ? index
      : bestIndex
  ), 0)
}

function buildIllustratedRoute(origin, destination) {
  const start = illustrationPoint(origin)
  const end = illustrationPoint(destination)
  const startIndex = nearestRouteSpineIndex(start)
  const endIndex = nearestRouteSpineIndex(end)
  const fromIndex = Math.min(startIndex, endIndex)
  const toIndex = Math.max(startIndex, endIndex)
  const roadSection = ILLUSTRATION_ROUTE_SPINE.slice(fromIndex, toIndex + 1)
  if (startIndex > endIndex) roadSection.reverse()
  return [start, ...roadSection, end]
}

const CAMPUS_OUTLINE = [
  [31.585518, 120.223002], [31.585609, 120.226543], [31.581862, 120.227294],
  [31.580217, 120.226436], [31.574732, 120.226221], [31.571076, 120.224504],
  [31.566689, 120.224290], [31.566140, 120.220213], [31.567786, 120.216994],
  [31.571076, 120.218067], [31.574732, 120.218925], [31.579668, 120.219569],
  [31.581496, 120.221286],
]

function rotatedRectangle({ center, width, depth, angle = 0 }) {
  const [lat, lng] = center
  const theta = angle * Math.PI / 180
  const metersPerLngDegree = 111320 * Math.cos(lat * Math.PI / 180)
  return [
    [-width / 2, -depth / 2], [width / 2, -depth / 2],
    [width / 2, depth / 2], [-width / 2, depth / 2],
  ].map(([x, y]) => {
    const rotatedX = x * Math.cos(theta) - y * Math.sin(theta)
    const rotatedY = x * Math.sin(theta) + y * Math.cos(theta)
    return [lat + rotatedY / 111320, lng + rotatedX / metersPerLngDegree]
  })
}

const glyphs = {
  '校门': '门', '迎新服务': '新', '办事服务': '办', '学习空间': '阅', '教学楼': '教',
  '学院单位': '院', '餐饮': '餐', '生活服务': '服', '医疗': '医', '宿舍': '宿',
  '运动': '体', '公共交通': '乘', '周边服务': '游',
}

function markerIcon(place, selected = false, compact = false, labelVisible = false) {
  const variant = place.zone === '校外' ? 'nearby' : place.type === '校门' ? 'gate' : 'campus'
  const label = place.shortLabel || place.name
  return L.divIcon({
    className: 'leaflet-marker-reset',
    html: `<span class="map-pin map-pin--${variant}${selected ? ' is-selected' : ''}${compact ? ' is-compact' : ''}${labelVisible ? ' is-label-visible' : ''}"><b>${glyphs[place.type] || '·'}</b><em>${label}</em></span>`,
    iconSize: [1, 1],
    iconAnchor: [0, 0],
  })
}

// Clickable 2.5D overlay shapes. These are deliberately kept in the same
// ratio coordinate system as the image so they stay aligned at every zoom.
// They are interaction zones, not surveyed CAD footprints.
const ILLUSTRATION_HOTSPOTS = [
  { placeId: 'welcome', shape: 'ellipse', width: 0.030, height: 0.034, kind: 'service' },
  { placeId: 'admin', width: 0.028, height: 0.086, angle: -4, kind: 'building' },
  { placeId: 'library', width: 0.032, height: 0.088, angle: -3, kind: 'building' },
  { placeId: 'innovation', width: 0.030, height: 0.076, angle: -5, kind: 'building' },
  { placeId: 'teach5', width: 0.028, height: 0.090, angle: -2, kind: 'building' },
  { placeId: 'teach6', width: 0.030, height: 0.088, angle: -2, kind: 'building' },
  { placeId: 'engineering', width: 0.030, height: 0.090, angle: -3, kind: 'building' },
  { placeId: 'scotland', width: 0.030, height: 0.086, angle: -2, kind: 'building' },
  { placeId: 'north_dining', width: 0.032, height: 0.070, angle: -2, kind: 'service' },
  { placeId: 'south_dining', width: 0.030, height: 0.070, angle: -3, kind: 'service' },
  { placeId: 'new_dining', width: 0.030, height: 0.070, angle: -4, kind: 'service' },
  { placeId: 'commerce', width: 0.055, height: 0.038, angle: -2, kind: 'service' },
  { placeId: 'express', shape: 'ellipse', width: 0.027, height: 0.035, kind: 'service' },
  { placeId: 'health', shape: 'ellipse', width: 0.026, height: 0.034, kind: 'service' },
  { placeId: 'dorm32', width: 0.030, height: 0.092, angle: -2, kind: 'dorm' },
  { placeId: 'dorm20', width: 0.030, height: 0.092, angle: -4, kind: 'dorm' },
  { placeId: 'north_track', shape: 'ellipse', width: 0.073, height: 0.066, kind: 'sports' },
  { placeId: 'central_track', shape: 'ellipse', width: 0.074, height: 0.074, kind: 'sports' },
  { placeId: 'south_track', shape: 'ellipse', width: 0.070, height: 0.066, kind: 'sports' },
]

function illustratedHotspotPoints(hotspot) {
  const [centerX, centerY] = ILLUSTRATION_POSITIONS[hotspot.placeId]
  if (hotspot.shape === 'ellipse') {
    return Array.from({ length: 36 }, (_, index) => {
      const theta = index / 36 * Math.PI * 2
      return illustrationRatioPoint(
        centerX + Math.cos(theta) * hotspot.width / 2,
        centerY + Math.sin(theta) * hotspot.height / 2,
      )
    })
  }

  const theta = (hotspot.angle || 0) * Math.PI / 180
  return [
    [-hotspot.width / 2, -hotspot.height / 2],
    [hotspot.width / 2, -hotspot.height / 2],
    [hotspot.width / 2, hotspot.height / 2],
    [-hotspot.width / 2, hotspot.height / 2],
  ].map(([x, y]) => illustrationRatioPoint(
    centerX + x * Math.cos(theta) - y * Math.sin(theta),
    centerY + x * Math.sin(theta) + y * Math.cos(theta),
  ))
}

const GeographicCampusMap = forwardRef(function GeographicCampusMap({
  mode,
  places,
  selectedPlace,
  route,
  basemap,
  showBuildings,
  showBoundary,
  showNearby,
  onPlaceSelect,
  onMapPick,
  onTileError,
}, ref) {
  const containerRef = useRef(null)
  const mapRef = useRef(null)
  const baseLayersRef = useRef(null)
  const buildingLayerRef = useRef(null)
  const markerLayerRef = useRef(null)
  const boundaryLayerRef = useRef(null)
  const routeLayersRef = useRef(null)
  const pickMarkerRef = useRef(null)
  const callbacksRef = useRef({ onPlaceSelect, onMapPick, onTileError })
  callbacksRef.current = { onPlaceSelect, onMapPick, onTileError }

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return undefined

    const map = L.map(containerRef.current, {
      zoomControl: false,
      attributionControl: true,
      minZoom: 12,
      maxZoom: 19,
      zoomSnap: 0.5,
      zoomDelta: 0.5,
      wheelPxPerZoomLevel: 90,
      tap: true,
    })

    map.createPane('campusBoundaryPane')
    map.getPane('campusBoundaryPane').style.zIndex = 380
    map.createPane('buildingRoofPane')
    map.getPane('buildingRoofPane').style.zIndex = 420
    map.createPane('routePane')
    map.getPane('routePane').style.zIndex = 450

    const streetLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap contributors',
      maxZoom: 19,
      detectRetina: true,
    }).on('tileerror', () => callbacksRef.current.onTileError?.())

    const satelliteLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
      attribution: 'Tiles &copy; Esri — Source: Esri, Maxar, Earthstar Geographics',
      maxZoom: 19,
      detectRetina: false,
    }).on('tileerror', () => callbacksRef.current.onTileError?.()).addTo(map)
    baseLayersRef.current = { street: streetLayer, satellite: satelliteLayer }

    boundaryLayerRef.current = L.polygon(CAMPUS_OUTLINE, {
      pane: 'campusBoundaryPane',
      color: '#f4c65d',
      weight: 2,
      fillColor: '#f4c65d',
      fillOpacity: 0.045,
      dashArray: '7 6',
      interactive: false,
    }).addTo(map)

    buildingLayerRef.current = L.layerGroup().addTo(map)
    markerLayerRef.current = L.layerGroup().addTo(map)
    const routeCasing = L.polyline([], {
      pane: 'routePane',
      color: '#ffffff', weight: 10, opacity: 0.95, lineCap: 'round', lineJoin: 'round',
    }).addTo(map)
    const routeLine = L.polyline([], {
      pane: 'routePane',
      color: '#1769e0', weight: 6, opacity: 1, lineCap: 'round', lineJoin: 'round',
    }).addTo(map)
    routeLayersRef.current = { routeCasing, routeLine }

    map.on('click', (event) => {
      if (pickMarkerRef.current) map.removeLayer(pickMarkerRef.current)
      pickMarkerRef.current = L.circleMarker(event.latlng, {
        radius: 7, color: '#fff', weight: 3, fillColor: '#1769e0', fillOpacity: 1,
      }).addTo(map)
      pickMarkerRef.current.bindPopup(
        `<strong>地图选点</strong><small>${event.latlng.lat.toFixed(5)}, ${event.latlng.lng.toFixed(5)}</small>`,
        { className: 'campus-popup' },
      ).openPopup()
      callbacksRef.current.onMapPick?.(event.latlng)
    })

    map.fitBounds(CAMPUS_BOUNDS, { padding: [12, 12] })
    mapRef.current = map

    const resizeObserver = new ResizeObserver(() => map.invalidateSize({ animate: false }))
    resizeObserver.observe(containerRef.current)
    return () => {
      resizeObserver.disconnect()
      map.remove()
      mapRef.current = null
    }
  }, [])

  useEffect(() => {
    const map = mapRef.current
    const layers = baseLayersRef.current
    if (!map || !layers) return
    Object.values(layers).forEach((layer) => {
      if (map.hasLayer(layer)) map.removeLayer(layer)
    })
    layers[basemap]?.addTo(map)
  }, [basemap])

  useEffect(() => {
    const layer = buildingLayerRef.current
    if (!layer) return
    layer.clearLayers()
    campusBuildings.forEach((building) => {
      const footprint = rotatedRectangle(building)
      const selected = selectedPlace?.id === building.placeId
      const linkedPlace = allPlaces.find((place) => place.id === building.placeId)
      if (!showBuildings && !selected) return

      const roof = L.polygon(footprint, {
        pane: 'buildingRoofPane',
        className: `campus-building-outline${selected ? ' is-selected' : ''}`,
        color: selected ? '#1769e0' : '#f4c65d',
        weight: selected ? 3 : 1.5,
        opacity: selected ? 1 : 0.9,
        fillColor: selected ? '#1769e0' : '#f4c65d',
        fillOpacity: selected ? 0.1 : 0.025,
        dashArray: selected ? undefined : '5 5',
        interactive: Boolean(linkedPlace),
      }).addTo(layer)

      if (linkedPlace) {
        roof.on('click', (event) => {
          if (event.originalEvent) L.DomEvent.stopPropagation(event.originalEvent)
          callbacksRef.current.onPlaceSelect?.(linkedPlace)
        })
        roof.bindTooltip(`${building.name} · 轮廓待校方复核`, {
          direction: 'top', className: 'building-tooltip', sticky: true,
        })
      }
    })
  }, [basemap, selectedPlace, showBuildings])

  useEffect(() => {
    const layer = markerLayerRef.current
    if (!layer) return
    layer.clearLayers()
    places.filter((place) => mode === 'campus' ? place.zone !== '校外' : (showNearby || place.zone !== '校外')).forEach((place) => {
      L.marker(place.coords, {
        icon: markerIcon(place, selectedPlace?.id === place.id),
        riseOnHover: true,
        riseOffset: 500,
      }).on('click', () => callbacksRef.current.onPlaceSelect?.(place))
        .bindTooltip(`${place.name} · ${place.zone}`, { direction: 'top', offset: [0, -19] })
        .addTo(layer)
    })
  }, [mode, places, selectedPlace, showNearby])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    if (mode === 'campus') {
      if (showBoundary && boundaryLayerRef.current && !map.hasLayer(boundaryLayerRef.current)) boundaryLayerRef.current.addTo(map)
      map.fitBounds(CAMPUS_BOUNDS, { padding: [12, 12], animate: true })
    } else {
      if (showBoundary && boundaryLayerRef.current && !map.hasLayer(boundaryLayerRef.current)) boundaryLayerRef.current.addTo(map)
      map.fitBounds(SURROUNDING_BOUNDS, { padding: [24, 24], animate: true })
    }
  }, [mode, showBoundary])

  useEffect(() => {
    if (!boundaryLayerRef.current) return
    const map = mapRef.current
    if (mode !== 'campus' && showBoundary && !map.hasLayer(boundaryLayerRef.current)) boundaryLayerRef.current.addTo(map)
    if (!showBoundary && map.hasLayer(boundaryLayerRef.current)) map.removeLayer(boundaryLayerRef.current)
  }, [mode, showBoundary])

  useEffect(() => {
    const map = mapRef.current
    const routeLayers = routeLayersRef.current
    if (!map || !routeLayers) return
    routeLayers.routeCasing.setLatLngs(route)
    routeLayers.routeLine.setLatLngs(route)
    if (route.length > 1) {
      map.fitBounds(L.latLngBounds(route), {
        paddingTopLeft: [70, 120], paddingBottomRight: [70, 110], maxZoom: 17, animate: true,
      })
    }
  }, [route])

  useEffect(() => {
    if (!selectedPlace?.coords || !mapRef.current || route.length > 1) return
    mapRef.current.flyTo(selectedPlace.coords, Math.max(mapRef.current.getZoom(), 16), { duration: 0.55 })
  }, [route, selectedPlace])

  useImperativeHandle(ref, () => ({
    zoomIn: () => mapRef.current?.zoomIn(),
    zoomOut: () => mapRef.current?.zoomOut(),
    fitCampus: () => mapRef.current?.fitBounds(CAMPUS_BOUNDS, { padding: [45, 45] }),
    fitSurroundings: () => mapRef.current?.fitBounds(SURROUNDING_BOUNDS, { padding: [25, 25] }),
    locateCampus: () => mapRef.current?.flyTo(CAMPUS_CENTER, 16, { duration: 0.65 }),
  }), [])

  return <div ref={containerRef} className="leaflet-map" aria-label="可拖拽、缩放和点击选点的校园周边地图" />
})

const IllustratedCampusMap = forwardRef(function IllustratedCampusMap({
  places,
  selectedPlace,
  route,
  origin,
  destination,
  onPlaceSelect,
  onMapPick,
}, ref) {
  const containerRef = useRef(null)
  const mapRef = useRef(null)
  const hotspotLayerRef = useRef(null)
  const markerLayerRef = useRef(null)
  const routeLayersRef = useRef(null)
  const pickMarkerRef = useRef(null)
  const [zoomLevel, setZoomLevel] = useState(-1.5)
  const callbacksRef = useRef({ onPlaceSelect, onMapPick })
  callbacksRef.current = { onPlaceSelect, onMapPick }

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return undefined

    const map = L.map(containerRef.current, {
      crs: L.CRS.Simple,
      zoomControl: false,
      attributionControl: false,
      minZoom: -1.5,
      maxZoom: 2.25,
      zoomSnap: 0.25,
      zoomDelta: 0.5,
      wheelPxPerZoomLevel: 90,
      maxBounds: L.latLngBounds([-180, -180], [1184, 1747]),
      maxBoundsViscosity: 0.86,
    })

    map.createPane('illustrationHotspotPane')
    map.getPane('illustrationHotspotPane').style.zIndex = 425
    map.createPane('illustrationRoutePane')
    map.getPane('illustrationRoutePane').style.zIndex = 450
    L.imageOverlay('./campus-3d-v7-hd.webp', ILLUSTRATION_BOUNDS, {
      className: 'campus-illustration-image',
      interactive: false,
    }).addTo(map)

    hotspotLayerRef.current = L.layerGroup().addTo(map)
    markerLayerRef.current = L.layerGroup().addTo(map)
    const routeCasing = L.polyline([], {
      pane: 'illustrationRoutePane',
      color: '#ffffff', weight: 10, opacity: 0.94, lineCap: 'round', lineJoin: 'round',
    }).addTo(map)
    const routeLine = L.polyline([], {
      pane: 'illustrationRoutePane',
      color: '#1769e0', weight: 6, opacity: 1, lineCap: 'round', lineJoin: 'round',
      dashArray: '12 8',
    }).addTo(map)
    routeLayersRef.current = { routeCasing, routeLine }

    map.on('click', (event) => {
      if (pickMarkerRef.current) map.removeLayer(pickMarkerRef.current)
      pickMarkerRef.current = L.circleMarker(event.latlng, {
        radius: 7, color: '#fff', weight: 3, fillColor: '#1769e0', fillOpacity: 1,
      }).addTo(map)
      callbacksRef.current.onMapPick?.(event.latlng)
    })

    const syncZoomLevel = () => setZoomLevel(map.getZoom())
    map.on('zoomend', syncZoomLevel)
    map.fitBounds(ILLUSTRATION_FIT_BOUNDS, { padding: [18, 18] })
    syncZoomLevel()
    mapRef.current = map

    const resizeObserver = new ResizeObserver(() => map.invalidateSize({ animate: false }))
    resizeObserver.observe(containerRef.current)
    return () => {
      resizeObserver.disconnect()
      map.off('zoomend', syncZoomLevel)
      map.remove()
      mapRef.current = null
    }
  }, [])

  useEffect(() => {
    const layer = hotspotLayerRef.current
    if (!layer) return
    layer.clearLayers()

    ILLUSTRATION_HOTSPOTS.forEach((hotspot) => {
      const place = allPlaces.find((item) => item.id === hotspot.placeId)
      if (!place || !places.some((item) => item.id === place.id)) return
      const selected = selectedPlace?.id === place.id
      const polygon = L.polygon(illustratedHotspotPoints(hotspot), {
        pane: 'illustrationHotspotPane',
        className: `illustration-hotspot illustration-hotspot--${hotspot.kind}${selected ? ' is-selected' : ''}`,
        color: selected ? '#1769e0' : '#ffffff',
        weight: selected ? 3 : 1.4,
        opacity: selected ? 1 : 0.14,
        fillColor: '#1769e0',
        fillOpacity: selected ? 0.22 : 0.008,
        interactive: true,
      }).addTo(layer)

      const restoreStyle = () => polygon.setStyle({
        color: selected ? '#1769e0' : '#ffffff',
        weight: selected ? 3 : 1.4,
        opacity: selected ? 1 : 0.14,
        fillOpacity: selected ? 0.22 : 0.008,
      })
      polygon.on('mouseover', () => polygon.setStyle({ color: '#1769e0', weight: 2.6, opacity: 1, fillOpacity: 0.16 }))
      polygon.on('mouseout', restoreStyle)
      polygon.on('click', (event) => {
        if (event.originalEvent) L.DomEvent.stopPropagation(event.originalEvent)
        callbacksRef.current.onPlaceSelect?.(place)
      })
      const element = polygon.getElement()
      if (element) {
        element.setAttribute('role', 'button')
        element.setAttribute('tabindex', '0')
        element.setAttribute('aria-label', `打开${place.name}详情`)
        element.addEventListener('keydown', (event) => {
          if (event.key !== 'Enter' && event.key !== ' ') return
          event.preventDefault()
          callbacksRef.current.onPlaceSelect?.(place)
        })
      }
      polygon.bindTooltip(`<strong>${place.name}</strong><small>${place.zone} · ${place.type}</small>`, {
        direction: 'top',
        className: 'building-tooltip illustration-building-tooltip',
        sticky: true,
      })
    })
  }, [places, selectedPlace])

  useEffect(() => {
    const layer = markerLayerRef.current
    if (!layer) return
    layer.clearLayers()
    places.filter((place) => place.zone !== '校外').forEach((place) => {
      const compact = !place.featured && place.type !== '校门'
      const showLabel = selectedPlace?.id === place.id || place.featured || place.type === '校门' || zoomLevel >= 0.75
      L.marker(illustrationPoint(place), {
        icon: markerIcon(place, selectedPlace?.id === place.id, compact, showLabel),
        riseOnHover: true,
        riseOffset: 500,
      }).on('click', () => callbacksRef.current.onPlaceSelect?.(place))
        .bindTooltip(`${place.name} · 2.5D 示意点位`, { direction: 'top', offset: [0, -19] })
        .addTo(layer)
    })
  }, [places, selectedPlace, zoomLevel])

  useEffect(() => {
    const map = mapRef.current
    const layers = routeLayersRef.current
    if (!map || !layers) return
    if (route.length < 2 || !origin || !destination) {
      layers.routeCasing.setLatLngs([])
      layers.routeLine.setLatLngs([])
      return
    }
    const illustratedRoute = buildIllustratedRoute(origin, destination)
    layers.routeCasing.setLatLngs(illustratedRoute)
    layers.routeLine.setLatLngs(illustratedRoute)
    map.fitBounds(L.latLngBounds(illustratedRoute), {
      paddingTopLeft: [90, 115], paddingBottomRight: [90, 105], maxZoom: 0.6, animate: true,
    })
  }, [destination, origin, route])

  useEffect(() => {
    if (!selectedPlace || !mapRef.current || route.length > 1) return
    mapRef.current.flyTo(illustrationPoint(selectedPlace), Math.max(mapRef.current.getZoom(), 0.15), { duration: 0.5 })
  }, [route, selectedPlace])

  useImperativeHandle(ref, () => ({
    zoomIn: () => mapRef.current?.zoomIn(),
    zoomOut: () => mapRef.current?.zoomOut(),
    fitCampus: () => mapRef.current?.fitBounds(ILLUSTRATION_FIT_BOUNDS, { padding: [30, 30] }),
    fitSurroundings: () => mapRef.current?.fitBounds(ILLUSTRATION_FIT_BOUNDS, { padding: [30, 30] }),
    locateCampus: () => mapRef.current?.fitBounds(ILLUSTRATION_FIT_BOUNDS, { padding: [30, 30], animate: true }),
  }), [])

  return <div ref={containerRef} className="leaflet-map leaflet-map--illustrated" aria-label="可拖拽、缩放和点击的 2.5D 校园建筑鸟瞰图" />
})

const CampusMap = forwardRef(function CampusMap(props, ref) {
  if (props.basemap === 'illustrated' && props.mode === 'campus') {
    return <IllustratedCampusMap {...props} ref={ref} />
  }
  return <GeographicCampusMap {...props} basemap={props.basemap === 'illustrated' ? 'satellite' : props.basemap} ref={ref} />
})

export default CampusMap
