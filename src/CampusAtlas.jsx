import { useEffect, useMemo, useRef, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { ArrowUpRight, ArrowClockwise, Buildings, Check, Compass, Copy, CornersOut, CrosshairSimple, ForkKnife, HouseLine, Info, MagnifyingGlass, MapPin, Minus, Plus, ShoppingBagOpen, SoccerBall, Tag, X } from '@phosphor-icons/react'
import { campusVrUrl } from './campusData.js'
import './campusAtlas.css'
import teach6Photo from '../model/central-campus/references/teach6.jpg?url'

const base = import.meta.env.BASE_URL
const sample = new URLSearchParams(window.location.search).get('sample')
const northStudy = sample === 'north'
const lakeStudy = sample === 'lake'
const campusStudy = sample === 'campus'
const study = northStudy || lakeStudy || campusStudy
const studyTitle = campusStudy ? '北区与湖区' : lakeStudy ? '中央湖区样板' : '北区街区样板'
const mapAsset = campusStudy ? 'campus-study' : study ? `campus-${sample}` : 'campus-atlas'
const overviewOrder = ['south', 'middle', 'lake', 'north', 'extension']
const searchText = value => value.normalize('NFKC').trim().toLowerCase().replace(/[\s_-]+/g, '')
const teach6PhotoSource = 'https://www.wxu.edu.cn/info/1111/57381.htm'
const atlasCategories = [
  { id: 'all', name: '全部', icon: Compass },
  { id: 'academic', name: '教学建筑', icon: Buildings },
  { id: 'dorm', name: '公寓建筑', icon: HouseLine },
  { id: 'dining', name: '餐饮建筑', icon: ForkKnife },
  { id: 'service', name: '配套建筑', icon: ShoppingBagOpen },
  { id: 'gate', name: '校门', icon: MapPin },
  { id: 'sport', name: '运动场', icon: SoccerBall },
]
const categoryFor = record => /食堂|餐饮|餐厅/.test(record.name) ? 'dining' : record.kind
const categoryName = record => atlasCategories.find(item => item.id === categoryFor(record))?.name || '建筑'
const recordIcon = record => atlasCategories.find(item => item.id === categoryFor(record))?.icon || Buildings
const searchAliases = { 食堂: 'dining', 餐厅: 'dining', 餐饮: 'dining', 吃饭: 'dining', 教学: 'academic', 教室: 'academic', 教学楼: 'academic', 宿舍: 'dorm', 寝室: 'dorm', 公寓: 'dorm', 配套: 'service', 服务: 'service', 校门: 'gate', 大门: 'gate', 运动: 'sport', 操场: 'sport', 球场: 'sport', 体育: 'sport' }
function filterRecords(records, category, query, area) {
  const raw = searchText(query)
  const code = raw.match(/^([bnmefs])0*(\d{1,3})$/)
  const text = /^(六|6)号(教学楼|楼)?$/.test(raw) ? 'b06' : code ? `${code[1]}${code[2].padStart(2, '0')}` : raw
  const matches = records.filter(record => (category === 'all' || categoryFor(record) === category)
    && (text ? searchText(`${record.id} ${record.source_id || ''} ${record.name} ${categoryName(record)}`).includes(text) || categoryFor(record) === searchAliases[text] : area === 'all' || record.region === area))
  return text ? matches.sort((a, b) => Number(searchText(b.id) === text || searchText(b.name) === text) - Number(searchText(a.id) === text || searchText(a.name) === text)) : matches
}

function ReferencePhoto() {
  const dialog = useRef(null)
  const retryButton = useRef(null)
  const restoreRetryFocus = useRef(false)
  const [photoStatus, setPhotoStatus] = useState('loading')
  const [photoAttempt, setPhotoAttempt] = useState(0)
  const photoUrl = photoAttempt ? `${teach6Photo}${teach6Photo.includes('?') ? '&' : '?'}retry=${photoAttempt}` : teach6Photo
  const retry = () => { setPhotoStatus('loading'); setPhotoAttempt(value => value + 1) }
  const failed = () => {
    const wasOpen = dialog.current?.open
    restoreRetryFocus.current ||= Boolean(wasOpen)
    dialog.current?.close()
    setPhotoStatus('error')
  }
  useEffect(() => {
    if (photoStatus !== 'error' || !restoreRetryFocus.current) return
    restoreRetryFocus.current = false
    retryButton.current?.focus()
  }, [photoStatus])
  const dismissBackdrop = event => {
    if (event.target !== dialog.current) return
    const box = dialog.current.getBoundingClientRect()
    if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) dialog.current.close()
  }
  const photoKeys = event => {
    if (event.key !== 'Tab') return
    const controls = [...dialog.current.querySelectorAll('button:not(:disabled), a[href]')]
    const first = controls[0], last = controls.at(-1)
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
    if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
  }
  return <div className="atlas-reference-photo">
    {photoStatus === 'error' ? <div className="atlas-photo-unavailable" role="status"><p>参考照片暂时无法加载。</p><div><button ref={retryButton} type="button" onClick={retry}><ArrowClockwise size={14} />重新加载照片</button><a href={teach6PhotoSource} target="_blank" rel="noreferrer">查看照片来源<ArrowUpRight size={12} /></a></div></div>
      : <button type="button" className="atlas-photo-preview" disabled={photoStatus !== 'ready'} aria-label="查看六号教学楼参考照片大图" aria-haspopup="dialog" aria-controls="atlas-reference-photo-dialog" onClick={() => dialog.current?.showModal()}><span className="atlas-photo-thumbnail"><img key={photoAttempt} src={photoUrl} alt="六号教学楼参考照片" onLoad={() => setPhotoStatus('ready')} onError={failed} />{photoStatus === 'loading' && <span role="status">照片加载中…</span>}</span><span className="atlas-photo-preview-caption">查看大图 · 校方参考照片<CornersOut size={13} /></span></button>}
    <dialog ref={dialog} id="atlas-reference-photo-dialog" className="atlas-photo-dialog" aria-modal="true" aria-labelledby="atlas-photo-title" onClick={dismissBackdrop} onKeyDown={photoKeys}>
      <header><small>校方资料 · 建筑外观参考</small><h2 id="atlas-photo-title">六号教学楼参考照片</h2><button type="button" className="atlas-photo-close" aria-label="关闭参考照片" autoFocus onClick={() => dialog.current.close()}><X size={20} /></button></header>
      <div className="atlas-photo-canvas"><img className="atlas-photo-image" src={photoStatus === 'ready' ? photoUrl : undefined} alt="六号教学楼参考照片完整画面" onError={failed} /></div>
      <footer><span>查看照片中的建筑外观</span><div><a href={photoUrl} target="_blank" rel="noreferrer">打开原图<ArrowUpRight size={13} /></a><a href={teach6PhotoSource} target="_blank" rel="noreferrer">查看照片来源<ArrowUpRight size={13} /></a></div></footer>
    </dialog>
  </div>
}
function writeLocation(region, building, replace = false, filters) {
  const url = new URL(window.location.href)
  url.searchParams.set('view', 'atlas')
  url.searchParams.set('area', region)
  url.searchParams.delete('building')
  url.searchParams.delete('place')
  if (building) url.searchParams.set(building.startsWith('place:') ? 'place' : 'building', building)
  if (filters) {
    if (filters.category !== 'all') url.searchParams.set('category', filters.category)
    else url.searchParams.delete('category')
    if (filters.query.trim()) url.searchParams.set('q', filters.query.trim())
    else url.searchParams.delete('q')
  }
  if (url.href !== window.location.href) window.history[replace ? 'replaceState' : 'pushState'](null, '', url)
}

export default function CampusAtlas() {
  const host = useRef(null)
  const infoDialog = useRef(null)
  const detailCard = useRef(null)
  const mapState = useRef(null)
  const mapRetry = useRef(null)
  const restoreMapFocus = useRef(false)
  const mapReady = useRef(false)
  const searchInput = useRef(null)
  const selectionOrigin = useRef(null)
  const places = useRef(null)
  const shareInput = useRef(null)
  const queryRef = useRef('')
  const queryEdited = useRef(false)
  const filterRef = useRef({ category: 'all', query: '' })
  const shareRequest = useRef(0)
  const api = useRef({})
  const [data, setData] = useState(null)
  const [status, setStatus] = useState('loading')
  const [loadPhase, setLoadPhase] = useState('metadata')
  const [loadSlow, setLoadSlow] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('all')
  const [area, setArea] = useState('all')
  const [overviewVisible, setOverviewVisible] = useState(false)
  const [selected, setSelected] = useState(null)
  const [detailExpanded, setDetailExpanded] = useState(false)
  const [labelsOn, setLabelsOn] = useState(false)
  const [immersive, setImmersive] = useState(false)
  const [info, setInfo] = useState(false)
  const [compare, setCompare] = useState(false)
  const [shareState, setShareState] = useState('idle')
  const [shareUrl, setShareUrl] = useState('')
  const [zoomAvailable, setZoomAvailable] = useState({ in: false, out: false })
  queryRef.current = query
  filterRef.current = { category, query }
  mapReady.current = status === 'ready'
  const comparisonDialog = useRef(null)
  const choose = (record, move = true, saveLocation = true) => {
    if (record) {
      const focused = document.activeElement
      selectionOrigin.current = saveLocation && focused?.closest('.atlas-search, .atlas-places, .atlas-map') ? focused : null
    }
    document.querySelector('.atlas-photo-dialog[open]')?.close()
    const browsing = filterRef.current.category !== 'all' || filterRef.current.query.trim()
    const region = browsing ? api.current.area || 'all' : record?.region || api.current.area || 'all'
    shareRequest.current += 1
    setShareState('idle')
    setShareUrl('')
    setSelected(record)
    setDetailExpanded(false)
    if (record && saveLocation && window.matchMedia('(max-width:700px)').matches) {
      searchInput.current?.blur()
    }
    if (record) { api.current.area = region; setArea(region); setOverviewVisible(false) }
    if (saveLocation) writeLocation(region, record?.id, false, filterRef.current)
    api.current.select?.(record, move)
    if (record && saveLocation && window.matchMedia('(max-width:700px)').matches) requestAnimationFrame(() => detailCard.current?.focus({ preventScroll: true }))
  }
  const closeBuilding = () => {
    const origin = selectionOrigin.current
    choose(null, false)
    requestAnimationFrame(() => {
      if (!mapReady.current || api.current.selected) return
      api.current.refreshLabels?.()
      const compact = window.matchMedia('(max-width:700px)').matches
      const available = origin?.isConnected && origin.getClientRects().length && getComputedStyle(origin).visibility === 'visible' && !origin.closest('[inert]') && !(compact && origin === searchInput.current)
      const target = available ? origin : host.current
      target?.focus({ preventScroll: true })
      if (available && target !== host.current) target.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'instant' })
    })
  }
  const focusRegion = (id, saveLocation = true) => {
    setArea(id)
    setQuery('')
    filterRef.current.query = ''
    choose(null, false, false)
    api.current.area = id
    api.current.region?.(id)
    if (saveLocation) writeLocation(id, undefined, false, filterRef.current)
  }
  const focusCategory = id => {
    filterRef.current = { category: id, query: '' }
    setCategory(id)
    setQuery('')
    choose(null, false, false)
    api.current.area = 'all'
    setArea('all')
    api.current.fitResults?.(filterRecords(api.current.records || [], id, '', 'all'))
    writeLocation('all', undefined, false, filterRef.current)
    places.current?.scrollTo({ top: 0 })
  }
  const overviewRegions = data?.regions
    .slice()
    .sort((a, b) => overviewOrder.indexOf(a.id) - overviewOrder.indexOf(b.id)) || []
  const regionNames = useMemo(() => new Map((data?.regions || []).map(region => [region.id, region.name])), [data])
  const allRecords = useMemo(() => [...(data?.records || []), ...(data?.map_places?.records || [])], [data])
  const filtered = useMemo(() => filterRecords(allRecords, category, query, area), [allRecords, category, query, area])
  const categoryCounts = useMemo(() => new Map(atlasCategories.map(item => [item.id, item.id === 'all' ? allRecords.length : allRecords.filter(record => categoryFor(record) === item.id).length])), [allRecords])
  const searching = Boolean(query.trim())
  const filtering = searching || category !== 'all'
  const matchedRegionCount = new Set(filtered.map(record => record.region)).size
  const clearSearch = () => { queryEdited.current = true; if (api.current.selected) choose(null, false, false); setQuery(''); searchInput.current?.focus() }
  const retryMap = () => {
    restoreMapFocus.current = true
    choose(null, false, false)
    setStatus('loading')
    setLoadPhase('metadata')
    setLoadSlow(false)
    setAttempt(value => value + 1)
  }
  const searchKeys = e => {
    if (e.nativeEvent.isComposing || e.keyCode === 229 || status !== 'ready' || !searching) return
    if (e.key === 'Enter' && filtered.length) { e.preventDefault(); choose(filtered[0]) }
    if (e.key === 'ArrowDown' && filtered.length) { e.preventDefault(); places.current?.querySelector('button:not(:disabled)')?.focus() }
  }
  const resultKeys = e => {
    if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(e.key) || e.nativeEvent.isComposing) return
    const buttons = [...places.current.querySelectorAll('button[data-record]:not(:disabled)')]
    const index = buttons.indexOf(document.activeElement)
    if (index < 0) return
    e.preventDefault()
    if (e.key === 'ArrowUp' && index === 0) { searchInput.current?.focus(); return }
    const next = e.key === 'Home' ? 0 : e.key === 'End' ? buttons.length - 1 : Math.min(buttons.length - 1, index + (e.key === 'ArrowDown' ? 1 : -1))
    buttons[next]?.focus()
  }
  const copyBuildingLink = async () => {
    if (!selected || shareState === 'copying') return
    const record = selected, request = ++shareRequest.current
    const url = new URL(window.location.href)
    url.searchParams.set('view', 'atlas'); url.searchParams.set('area', api.current.area || record.region || 'all')
    url.searchParams.delete('building'); url.searchParams.delete('place')
    url.searchParams.set(record.id.startsWith('place:') ? 'place' : 'building', record.id)
    url.hash = ''
    setShareState('copying')
    try {
      if (!navigator.clipboard?.writeText) throw new Error('Clipboard unavailable')
      await navigator.clipboard.writeText(url.href)
      if (shareRequest.current === request) setShareState('copied')
    } catch {
      if (shareRequest.current === request) { setShareUrl(url.href); setShareState('manual') }
    }
  }

  useEffect(() => {
    const previousTitle = document.title
    document.title = study ? `${studyTitle} · 太湖校园地图` : '太湖校园地图'
    return () => { document.title = previousTitle }
  }, [])

  useEffect(() => {
    const abort = new AbortController()
    let map, observer, dismissOverview, onTouchStart, restoreLocation, loadTimer, active = true
    const beginLoading = phase => {
      clearTimeout(loadTimer)
      setLoadPhase(phase)
      setLoadSlow(false)
      loadTimer = setTimeout(() => { if (active) setLoadSlow(true) }, 8000)
    }
    const finishLoading = next => { clearTimeout(loadTimer); if (active) { setLoadSlow(false); setStatus(next) } }
    // A retry must also bypass a cached failed or invalid resource.
    const retryQuery = attempt ? `?retry=${attempt}` : ''
    setStatus('loading')
    beginLoading('metadata')
    setZoomAvailable({ in: false, out: false })
    fetch(`${base}${mapAsset}.json${retryQuery}`, { signal: abort.signal })
      .then(r => { if (!r.ok) throw new Error('Map metadata unavailable'); return r.json() })
      .then(meta => {
        if (!active) return
        if (!meta.width || !meta.height || !Array.isArray(meta.records)) throw new Error('Invalid map metadata')
        meta.records = meta.records.map(r => ({ ...r, region: r.region || 'lake' }))
        if (meta.map_places && meta.map_places.image_sha256 !== meta.image_sha256) throw new Error('Place projection does not match map image')
        const records = [...meta.records, ...(meta.map_places?.records || [])]
        meta.regions ||= [{ id: 'lake', name: '中央湖区', bounds: [0, 0, meta.width, meta.height], count: 3 }]
        const coverageMask = meta.presentation_mask
        const maskMatchesImage = coverageMask?.image_sha256 === meta.image_sha256 && coverageMask.polygons_image_px?.length
        host.current.style.background = meta.coverage === 'campus' ? (maskMatchesImage ? '#e1e9e4' : '#b5b9bf') : '#d3d8c8'
        if (maskMatchesImage) {
          const paths = coverageMask.polygons_image_px.map(polygon => `<polygon points="${polygon.map(([x, y]) => `${Number(x)},${Number(y)}`).join(' ')}"/>`).join('')
          const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${meta.width} ${meta.height}"><defs><filter id="b" x="-5%" y="-5%" width="110%" height="110%"><feGaussianBlur stdDeviation="${Number(coverageMask.feather_px)}"/></filter></defs><g fill="white" filter="url(#b)">${paths}</g></svg>`
          host.current.style.setProperty('--atlas-coverage-mask', `url("data:image/svg+xml,${encodeURIComponent(svg)}")`)
        } else host.current.style.removeProperty('--atlas-coverage-mask')
        setData(meta)
        const { width: w, height: h } = meta
        const bounds = L.latLngBounds([0, 0], [h, w])
        map = L.map(host.current, { crs: L.CRS.Simple, zoomControl: false, attributionControl: false, minZoom: -5, maxZoom: .35, zoomSnap: .1, zoomDelta: .5, maxBoundsViscosity: 1, scrollWheelZoom: true })
        host.current.tabIndex = -1
        // The cropped study needs room below the image for the mobile detail card.
        map.setMaxBounds(bounds.pad(study ? .35 : .18))
        // Point layers need a projected centre before applying filter styles.
        map.fitBounds(bounds, { padding: [16, 16], animate: false })
        beginLoading('image')
        const image = L.imageOverlay(`${base}${mapAsset}.webp?v=${meta.image_sha256?.slice(0, 12) || '1'}${attempt ? `&retry=${attempt}` : ''}`, bounds, { alt: '无锡太湖学院校园鸟瞰地图，建筑与道路依据影像绘制'  })
        image.on('load', () => finishLoading('ready'))
        image.on('error', () => finishLoading('error'))
        image.addTo(map)
        const overlays = new Map(), labels = new Map(), labelRecords = new Map(), studyBuildingBounds = new Map()
        const xy = ([x, y]) => [h - y, x]
        // Include ground-level corners when fitting any source-backed roof on a phone.
        // Roof hit areas remain unchanged; the extra space exposes the facade.
        const camera = meta.camera
        const projectStudyGround = camera && meta.roof_faces_world ? (() => {
          const [rx, ry, rz] = camera.rotation_euler
          const sx = Math.sin(rx), cx = Math.cos(rx), sy = Math.sin(ry), cy = Math.cos(ry), sz = Math.sin(rz), cz = Math.cos(rz)
          const ppm = w / camera.ortho_scale
          return p => {
            const dx = p[0] - camera.position[0], dy = p[1] - camera.position[1], dz = -camera.position[2]
            return [w / 2 + (cz * cy * dx + sz * cy * dy - sy * dz) * ppm,
              h / 2 - ((cz * sy * sx - sz * cx) * dx + (sz * sy * sx + cz * cx) * dy + cy * sx * dz) * ppm]
          }
        })() : null
        for (const record of meta.records) {
          const poly = L.polygon(record.polygons.map(polygon => polygon.map(ring => ring.map(xy))), { className: 'atlas-building-hotspot', color: '#087e78', weight: 0, fillOpacity: 0, interactive: true, bubblingMouseEvents: false }).addTo(map)
          poly.getElement().dataset.atlasId = record.id
          poly.on('click', () => { if (!api.current.filterActive || api.current.visibleIds?.has(record.id)) choose(record, false) })
          poly.on('mouseover', () => { if (api.current.selected !== record.id) poly.setStyle({ weight: 1.5, fillOpacity: .06 }) })
          poly.on('mouseout', () => { if (api.current.selected !== record.id) poly.setStyle({ weight: api.current.filterActive && api.current.visibleIds?.has(record.id) ? 1.5 : 0, fillOpacity: api.current.filterActive && api.current.visibleIds?.has(record.id) ? .05 : 0 }) })
          overlays.set(record.id, poly)
          if (projectStudyGround && meta.roof_faces_world?.[record.id]?.length) {
            const ground = meta.roof_faces_world[record.id].flat().map(p => xy(projectStudyGround(p)))
            studyBuildingBounds.set(record.id, L.latLngBounds(ground).extend(poly.getBounds()))
          }
        }
        for (const record of meta.map_places?.records || []) {
          const point = L.circleMarker(xy(record.anchor), { className: 'atlas-source-point', radius: 7, color: '#087e78', weight: 2, fillColor: '#fff', fillOpacity: .95, interactive: true, bubblingMouseEvents: false }).addTo(map)
          point.getElement().dataset.atlasId = record.id
          point.on('click', () => { if (!api.current.filterActive || api.current.visibleIds?.has(record.id)) choose(record) })
          overlays.set(record.id, point)
        }
        for (const record of records) {
          const button = document.createElement('button')
          button.type = 'button'; button.className = 'atlas-map-label'; button.textContent = record.name
          button.setAttribute('aria-label', `查看${record.name}`)
          L.DomEvent.disableClickPropagation(button)
          button.addEventListener('click', () => choose(record, false))
          const marker = L.marker(xy(record.anchor), { keyboard: false, icon: L.divIcon({ html: button, className: 'atlas-label-anchor', iconSize: [140, 30], iconAnchor: [70, 15] }), zIndexOffset: 10 }).addTo(map)
          labels.set(record.id, marker); labelRecords.set(record.id, record)
        }
        for (const region of meta.regions) {
          const [x0, y0, x1, y1] = region.bounds
          const button = document.createElement('button')
          button.type = 'button'; button.className = 'atlas-map-label atlas-region-label'; button.textContent = region.name
          button.setAttribute('aria-label', `浏览${region.name}`)
          L.DomEvent.disableClickPropagation(button)
          button.addEventListener('click', () => focusRegion(region.id))
          const marker = L.marker(xy([(x0 + x1) / 2, (y0 + y1) / 2]), { keyboard: false, icon: L.divIcon({ html: button, className: 'atlas-label-anchor', iconSize: [140, 30], iconAnchor: [70, 15] }) }).addTo(map)
          labels.set(`region:${region.id}`, marker); labelRecords.set(`region:${region.id}`, { isRegion: true, priority: 100 })
        }
        function updateLabelVisibility() {
          const size = map.getSize(), occupied = []
          const mapBox = host.current.getBoundingClientRect()
          const actions = host.current.parentElement.querySelector('.atlas-study-actions')?.getBoundingClientRect()
          const filterBanner = host.current.parentElement.querySelector('.atlas-filter-banner')?.getBoundingClientRect()
          const detail = detailCard.current?.getBoundingClientRect()
          const controls = host.current.parentElement.querySelector('.atlas-controls')?.getBoundingClientRect()
          const overview = meta.records.length > 10 && map.getZoom() < -1.6
          const candidates = [...labels.entries()].sort(([a], [b]) => Number(b === api.current.selected) - Number(a === api.current.selected) || (labelRecords.get(b).priority || 0) - (labelRecords.get(a).priority || 0))
          for (const [id, marker] of candidates) {
            const button = marker.getElement()?.querySelector('button')
            if (!button) continue
            const record = labelRecords.get(id)
            const p = map.latLngToContainerPoint(marker.getLatLng()), half = button.offsetWidth / 2
            const fits = p.x > half + 8 && p.x < size.x - half - 8 && p.y > 18 && p.y < size.y - 36
            const underControls = controls && p.x + half > controls.left - mapBox.left - 8 && p.x - half < controls.right - mapBox.left + 8 && p.y + 18 > controls.top - mapBox.top - 8 && p.y - 18 < controls.bottom - mapBox.top + 8
            const underActions = actions?.height > 0 && p.x - half < actions.right - mapBox.left + 8 && p.y < actions.bottom - mapBox.top + 20
            const underFilter = filterBanner && p.x + half > filterBanner.left - mapBox.left - 8 && p.x - half < filterBanner.right - mapBox.left + 8 && p.y - 18 < filterBanner.bottom - mapBox.top + 8
            const collision = occupied.some(o => Math.abs(o.x - p.x) < o.half + half + 8 && Math.abs(o.y - p.y) < 35)
            const underDetail = detail && p.x + half > detail.left - mapBox.left && p.x - half < detail.right - mapBox.left && p.y + 18 > detail.top - mapBox.top && p.y - 18 < detail.bottom - mapBox.top
            const matchesFilter = !api.current.filterActive || api.current.visibleIds?.has(id)
            const layerVisible = record.isRegion ? overview && api.current.labelsOn && !api.current.filterActive
              : matchesFilter && (api.current.labelsOn || api.current.filterActive || id === api.current.selected) && (!overview || api.current.filterActive || id === api.current.selected)
            const visible = fits && !underControls && !underActions && !underFilter && !underDetail && !collision && layerVisible && occupied.length < (size.x < 700 ? 7 : 18)
            button.style.visibility = visible ? 'visible' : 'hidden'
            marker.getElement().style.pointerEvents = visible ? 'auto' : 'none'
            if (visible) occupied.push({ x: p.x, y: p.y, half })
          }
        }
        map.on('moveend zoomend resize', updateLabelVisibility)
        dismissOverview = () => { api.current.overview = false; setOverviewVisible(false) }
        map.on('dragstart', dismissOverview)
        host.current.addEventListener('wheel', dismissOverview, { passive: true })
        onTouchStart = e => { if (e.touches.length > 1) dismissOverview() }
        host.current.addEventListener('touchstart', onTouchStart, { passive: true })
        function updateZoomAvailability() {
          const zoom = map.getZoom()
          if (!active || !Number.isFinite(zoom)) return
          // Leaflet snaps to tenths, so a remaining fraction below half a step
          // cannot produce a useful button action at either bound.
          const next = { in: zoom < map.getMaxZoom() - .05, out: zoom > map.getMinZoom() + .05 }
          setZoomAvailable(previous => previous.in === next.in && previous.out === next.out ? previous : next)
        }
        map.on('zoomend resize', updateZoomAvailability)
        function fitRegion(region, initial = false) {
          const compact = host.current.clientWidth < 700
          const lakeFrame = initial && !study && region.id === 'lake' && !compact
            ? [3300, 1030, 4560, 1910] : null
          const [x0, y0, x1, y1] = lakeFrame || (compact && region.focus_bounds_mobile) || region.focus_bounds || region.bounds
          const animate = !initial && !window.matchMedia('(prefers-reduced-motion: reduce)').matches
          if (compact && region.mobile_framing === 'cover') {
            const size = map.getSize()
            const scale = Math.max((size.x - 24) / (x1 - x0), (size.y - 48) / (y1 - y0))
            map.setView(xy([(x0 + x1) / 2, (y0 + y1) / 2]), Math.min(.35, Math.log2(scale)), { animate })
          } else {
            map.fitBounds([xy([x0, y1]), xy([x1, y0])], { padding: initial ? [24, 50] : [45, 55], maxZoom: .1, animate })
          }
        }
        function fit(full = true, edgeToEdge = false) {
          api.current.area = full ? 'all' : api.current.area || 'all'
          if (full) setArea('all')
          map.setMinZoom(-5)
          map.invalidateSize()
          if (!full && northStudy && host.current.clientWidth >= 700) {
            // The north pilot is one deliberately composed block. Show its
            // complete source-backed frame before the user zooms into roofs.
            map.fitBounds(bounds, { padding: edgeToEdge ? [0, 0] : [16, 16], animate: false })
          } else if (!full && campusStudy && host.current.clientWidth < 700) {
            // Start as a browsable map, filling the phone rather than shrinking
            // the landscape image into a small postcard. Overview remains explicit.
            const cover = Math.max(host.current.clientWidth / w, host.current.clientHeight / h)
            const zoom = Math.min(.35, Math.ceil(Math.log2(cover) * 10) / 10)
            map.setView([h * .5, w * .47], zoom, { animate: false })
          } else if (!full && !campusStudy && (host.current.clientWidth < 700 || meta.records.length > 10)) {
            const requested = new URLSearchParams(window.location.search).get('area')
            const region = meta.regions.find(r => r.id === requested) || meta.regions.find(r => r.id === 'lake')
            if (meta.records.length > 10 && region) {
              api.current.area = region.id
              setArea(region.id)
              fitRegion(region, true)
            } else {
              const zoom = Math.log2(host.current.clientHeight / h)
              map.setView([h * .48, w * .55], Math.min(.35, zoom), { animate: false })
            }
          } else {
            map.fitBounds(bounds, { padding: [16, 16], animate: false })
          }
          map.setMinZoom(map.getBoundsZoom(bounds, false, [32, 32]) - .3)
          updateZoomAvailability()
          api.current.overview = full
          setOverviewVisible(full)
        }
        function fitSelection(record, animate = false) {
          if (!record) return
          const compact = window.matchMedia('(max-width:700px)').matches
          const size = map.getSize()
          const cardHeight = detailCard.current?.getBoundingClientRect().height || 120
          const pointBounds = record.focus_bounds && L.latLngBounds(xy([record.focus_bounds[0], record.focus_bounds[3]]), xy([record.focus_bounds[2], record.focus_bounds[1]]))
          map.fitBounds(pointBounds || (compact && studyBuildingBounds.get(record.id)) || overlays.get(record.id).getBounds(), {
            ...(compact
              ? { paddingTopLeft: [24, 28], paddingBottomRight: [24, Math.min(size.y - 90, cardHeight + 58)] }
              : { paddingTopLeft: [study ? 112 : 72, 36], paddingBottomRight: [Math.min(size.x - 140, (detailCard.current?.getBoundingClientRect().width || 260) + 48), 45] }),
            maxZoom: .2, animate,
          })
        }
        function refreshOverlays() {
          for (const [id, overlay] of overlays) {
            const record = records.find(item => item.id === id)
            const visible = !api.current.filterActive || api.current.visibleIds?.has(id)
            const picked = id === api.current.selected
            const point = Boolean(record.focus_bounds)
            overlay.setStyle({ weight: visible ? picked ? 2.5 : point || api.current.filterActive ? 1.5 : 0 : 0,
              fillOpacity: visible ? point ? .95 : picked ? .13 : api.current.filterActive ? .05 : 0 : 0 })
            if (overlay.getElement()) overlay.getElement().style.pointerEvents = visible ? 'auto' : 'none'
          }
          updateLabelVisibility()
        }
        api.current = {
          area: 'all',
          records,
          labelsOn: false,
          fit,
          dismissOverview,
          region: id => {
            if (id === 'all') { fit(); return }
            const region = meta.regions.find(r => r.id === id)
            if (!region) return
            api.current.overview = false
            setOverviewVisible(false)
            fitRegion(region)
          },
          zoom: delta => map.setZoom(Math.max(map.getMinZoom(), Math.min(.35, map.getZoom() + delta))),
          fitResults: matches => {
            if (!matches.length) return
            if (matches.length === records.length) { fit(); return }
            api.current.overview = false
            setOverviewVisible(false)
            const resultBounds = L.latLngBounds(matches.map(record => xy(record.anchor)))
            map.fitBounds(resultBounds.pad(.15), { padding: [70, 65], maxZoom: -.2, animate: !window.matchMedia('(prefers-reduced-motion: reduce)').matches })
          },
          filters: (ids, activeFilter) => {
            api.current.visibleIds = new Set(ids)
            api.current.filterActive = activeFilter
            refreshOverlays()
          },
          select: (record, move) => {
            api.current.selected = record?.id
            refreshOverlays()
            const compact = window.matchMedia('(max-width:700px)').matches
            if (record && (move || compact)) fitSelection(record, !window.matchMedia('(prefers-reduced-motion: reduce)').matches)
            updateLabelVisibility()
          },
          reframeSelected: () => {
            map.invalidateSize()
            fitSelection(records.find(r => r.id === api.current.selected))
            updateLabelVisibility()
          },
          labels: value => { api.current.labelsOn = value; updateLabelVisibility() },
          refreshLabels: updateLabelVisibility,
        }
        restoreLocation = event => {
          const params = new URLSearchParams(window.location.search)
          if (params.get('view') && params.get('view') !== 'atlas') return
          if (event?.type === 'popstate') {
            queryEdited.current = false
            setQuery('')
            if (window.matchMedia('(max-width:700px)').matches) searchInput.current?.blur()
          }
          const restoredCategory = atlasCategories.some(item => item.id === params.get('category')) ? params.get('category') : 'all'
          const restoredQuery = queryEdited.current ? queryRef.current : params.get('q') || ''
          filterRef.current = { category: restoredCategory, query: restoredQuery }
          setCategory(restoredCategory)
          setQuery(restoredQuery)
          const restoredArea = params.get('area') === 'all' || meta.regions.some(region => region.id === params.get('area')) ? params.get('area') : study ? 'lake' : 'all'
          api.current.area = restoredArea
          setArea(restoredArea)
          const requested = params.get('place') || params.get('building')?.normalize('NFKC').trim().toUpperCase()
          const record = records.find(r => r.id === requested)
          const matches = filterRecords(records, restoredCategory, restoredQuery, restoredArea)
          api.current.filters(matches.map(item => item.id), restoredCategory !== 'all' || Boolean(restoredQuery.trim()))
          if (record) {
            if (!matches.some(item => item.id === record.id)) { filterRef.current = { category: 'all', query: '' }; setCategory('all'); setQuery(''); api.current.filters([], false) }
            choose(record, true, false)
            writeLocation(api.current.area, record.id, true, filterRef.current)
            return
          }
          choose(null, false, false)
          const region = meta.regions.find(r => r.id === params.get('area'))
          if (restoredArea === 'all' && (restoredCategory !== 'all' || restoredQuery.trim())) api.current.fitResults(matches)
          else if (restoredArea === 'all') fit()
          else if (region) {
            api.current.area = region.id
            setArea(region.id)
            api.current.overview = false
            setOverviewVisible(false)
            fitRegion(region, true)
          } else fit(false)
          writeLocation(api.current.area, undefined, true, filterRef.current)
        }
        map.on('click', () => choose(null, false))
        restoreLocation()
        window.addEventListener('popstate', restoreLocation)
        updateLabelVisibility()
        observer = new ResizeObserver(() => { if (api.current.overview) fit(); else { map.invalidateSize(); map.setMinZoom(map.getBoundsZoom(bounds, false, [32, 32]) - .3); if (api.current.selected) api.current.reframeSelected(); updateZoomAvailability() } })
        observer.observe(host.current)
      })
      .catch(error => { if (active && error.name !== 'AbortError') finishLoading('error') })
    return () => { active = false; clearTimeout(loadTimer); abort.abort(); observer?.disconnect(); if (restoreLocation) window.removeEventListener('popstate', restoreLocation); if (dismissOverview) host.current?.removeEventListener('wheel', dismissOverview); if (onTouchStart) host.current?.removeEventListener('touchstart', onTouchStart); map?.remove(); api.current = {} }
  }, [attempt])

  useEffect(() => {
    // Leaflet initializes its own tabindex; keep the hidden canvas out of focus.
    host.current.tabIndex = status === 'ready' ? 0 : -1
    const focus = document.activeElement
    const inState = mapState.current?.contains(focus)
    if (status === 'error' && (focus === document.body || inState || host.current.contains(focus))) mapRetry.current?.focus()
    if (restoreMapFocus.current && (focus === document.body || inState)) {
      if (status === 'loading') mapState.current?.focus()
      if (status === 'ready') host.current?.focus()
    }
    if (status !== 'loading') restoreMapFocus.current = false
  }, [status])
  useEffect(() => { api.current.labels?.(labelsOn) }, [labelsOn, status])
  useEffect(() => {
    if (status !== 'ready') return
    api.current.filters?.(filtered.map(record => record.id), filtering)
    writeLocation(api.current.area || area, api.current.selected, true, filterRef.current)
  }, [filtered, filtering, status])
  useEffect(() => {
    if (status !== 'ready') return undefined
    const frame = requestAnimationFrame(() => selected ? api.current.reframeSelected?.() : api.current.refreshLabels?.())
    return () => cancelAnimationFrame(frame)
  }, [selected, detailExpanded, status])
  useEffect(() => {
    const card = detailCard.current
    if (!selected || !card || status !== 'ready') return undefined
    let height = card.getBoundingClientRect().height, frame
    const observer = new ResizeObserver(() => {
      const next = card.getBoundingClientRect().height
      if (Math.abs(next - height) < 1 || api.current.selected !== selected.id) return
      height = next
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(() => api.current.reframeSelected?.())
    })
    observer.observe(card)
    return () => { observer.disconnect(); cancelAnimationFrame(frame) }
  }, [selected, status])
  useEffect(() => {
    if (shareState !== 'manual') return undefined
    shareInput.current?.focus()
    shareInput.current?.select()
  }, [shareState])
  useEffect(() => {
    if (!northStudy || status !== 'ready') return undefined
    const frame = requestAnimationFrame(() => api.current.fit?.(false, immersive))
    return () => cancelAnimationFrame(frame)
  }, [immersive, status])
  useEffect(() => {
    const close = e => {
      if (e.key !== 'Escape' || e.isComposing || e.keyCode === 229) return
      // Native dialog handles Escape and focus restoration before the map layer.
      if (document.querySelector('.atlas-photo-dialog[open]')) return
      if (document.querySelector('.atlas-info-backdrop')) { setInfo(false); setCompare(false); return }
      if (queryRef.current && e.target.closest?.('.atlas-search, .atlas-places')) { if (mapReady.current && api.current.selected) choose(null, false, false); setQuery(''); searchInput.current?.focus(); return }
      if (!mapReady.current) return
      setImmersive(false)
      if (api.current.selected) closeBuilding()
    }
    window.addEventListener('keydown', close)
    return () => window.removeEventListener('keydown', close)
  }, [])

  useEffect(() => {
    if (!info && !compare) return undefined
    const previous = document.activeElement
    const dialog = compare ? comparisonDialog.current : infoDialog.current
    const trap = e => {
      if (e.key !== 'Tab') return
      const focusable = [...dialog.querySelectorAll('button, a[href]')]
      const first = focusable[0], last = focusable.at(-1)
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
      if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
    }
    dialog.addEventListener('keydown', trap)
    dialog.querySelector('button')?.focus()
    return () => { dialog.removeEventListener('keydown', trap); previous?.focus?.() }
  }, [info, compare])

  return <div className={`atlas-page${selected ? ' atlas-page--has-selection' : ''}${immersive && northStudy ? ' atlas-page--immersive' : ''}`}>
    <a className="atlas-skip" href="#atlas-map">跳到地图</a>
    <header className="atlas-header">
      <a className="atlas-brand" href={base}><Compass size={27} /><span><strong>太湖校园导览</strong><small>无锡太湖学院</small></span></a>
      <nav aria-label="地图视图">{study ? <><a href={`${base}?view=atlas`}>返回全校</a><a href={`${base}?view=atlas&sample=${lakeStudy ? 'north' : 'lake'}`}>{lakeStudy ? '北区样板' : '湖区样板'}</a></> : <span aria-current="page">鸟瞰地图</span>}<a href={campusVrUrl} target="_blank" rel="noreferrer" aria-label="打开校园实景全景，新窗口">校园全景<ArrowUpRight size={14} /></a><a href={`${base}?view=model`}>全校三维<ArrowUpRight size={14} /></a><a href={`${base}?view=satellite`}>卫星地图<ArrowUpRight size={14} /></a></nav>
    </header>
    <main className="atlas-workspace">
      <aside className="atlas-sidebar" aria-label="查找校园建筑与地点">
        <div className="atlas-title"><small>无锡太湖学院 · {study ? '区域鸟瞰' : '全校鸟瞰'}</small><h1>{study ? studyTitle : '太湖校园地图'}</h1><p>按区域或用途，找到校园地点。</p></div>
        <label className="atlas-search"><MagnifyingGlass size={18} /><input ref={searchInput} value={query} onFocus={() => { if (selected && window.matchMedia('(max-width:700px)').matches) choose(null, false) }} onChange={e => { queryEdited.current = true; if (api.current.selected) choose(null, false, false); setQuery(e.target.value) }} onKeyDown={searchKeys} placeholder="搜索名称、编号，如食堂、S1" aria-label="搜索校园建筑" aria-controls="atlas-search-results" aria-describedby={filtering ? 'atlas-search-summary' : undefined} autoComplete="off" enterKeyHint="search" />{query && <button type="button" onClick={clearSearch} aria-label="清空搜索"><X size={15} /></button>}</label>
        <nav className="atlas-regions" aria-label="校园区域">
          {[{ id: 'all', name: study ? '样板总览' : '全校总览' }, ...(data?.regions || [])].map(region => <button type="button" key={region.id} disabled={status !== 'ready'} aria-pressed={area === region.id} onClick={() => focusRegion(region.id)}>{region.name}</button>)}
        </nav>
        <nav className="atlas-categories" aria-label="按用途查找">{atlasCategories.filter(item => item.id === 'all' || categoryCounts.get(item.id)).map(item => { const Icon = item.icon; return <button type="button" key={item.id} disabled={status !== 'ready'} aria-pressed={category === item.id} onClick={() => focusCategory(item.id)}><Icon size={16} /><span>{item.name}</span><small>{categoryCounts.get(item.id) || 0}</small></button> })}</nav>
        <div ref={places} id="atlas-search-results" className={`atlas-places${filtering ? ' atlas-places--search' : ''}`} onKeyDown={resultKeys}>
          {filtering && <p className="atlas-search-summary" id="atlas-search-summary" role="status">{status === 'loading' ? loadPhase === 'metadata' ? '地点信息加载中…' : '地图画面加载中，请稍候…' : status === 'error' ? '地图暂时无法加载，请重试。' : filtered.length ? <><span>{filtered.length} 个结果 · {searching || area === 'all' ? study ? '当前样板' : '全校查找' : regionNames.get(area)}</span><small>{matchedRegionCount > 1 ? `跨 ${matchedRegionCount} 个区域 · ` : ''}点击定位{searching ? '，回车或 ↓ 浏览' : ''}</small></> : '当前条件下没有匹配地点'}</p>}
          {filtered.map(r => { const Icon = recordIcon(r); return <button type="button" key={r.id} data-record={r.id} data-building={!r.id.startsWith('place:') ? r.id : undefined} disabled={status !== 'ready'} aria-label={`定位${r.name}，${r.source_id || r.id}，${regionNames.get(r.region) || '校园'}`} aria-pressed={selected?.id === r.id} onClick={() => choose(r)}><span className="atlas-place-icon"><Icon size={20} /></span><span><strong>{r.name}</strong><small className="atlas-place-meta"><span className="atlas-place-code">{r.id.startsWith('place:') ? categoryName(r) : r.id}</span>{filtering && <span>· {regionNames.get(r.region) || '校园'}</span>}<span>· {r.id === 'B06' ? '照片可识别' : r.id.startsWith('place:') ? '来源点位' : '区域描述'}</span></small></span><ArrowUpRight size={16} /></button> })}
          {status === 'ready' && filtering && !filtered.length && <div className="atlas-empty"><p>当前分类或区域中没有匹配地点。可清空搜索，或查看全部用途。</p><button type="button" onClick={() => { setQuery(''); focusCategory('all'); searchInput.current?.focus() }}>清除筛选，继续浏览<ArrowUpRight size={14} /></button></div>}
        </div>
        <div className="atlas-sidebar-footer"><span className="atlas-preview-dot" />影像参考 · 外观展示<p>建筑高度与细节采用估算，<br />描述名称不代表正式楼号。</p><button type="button" onClick={() => setInfo(true)}><Info size={16} />地图资料与说明</button></div>
      </aside>
      <section className={`atlas-map-area${study ? ' atlas-map-area--study' : ''}${selected ? ' atlas-map-area--selected' : ''}`} aria-label="校园鸟瞰地图">
        <div ref={host} id="atlas-map" className={`atlas-map${!study ? ' atlas-map--campus' : ''}`} inert={status !== 'ready'} aria-hidden={status !== 'ready'} aria-busy={status === 'loading'} tabIndex={status === 'ready' ? 0 : -1} aria-label="可拖动缩放的校园鸟瞰地图；也可用区域和建筑列表选择" />
        {status === 'ready' && <div className="atlas-study-actions">{northStudy && <button type="button" className="atlas-focus-toggle" aria-pressed={immersive} onClick={() => setImmersive(value => !value)}>{immersive ? '退出专注看图' : '专注看图'}<CornersOut size={14} /></button>}{study && !campusStudy && <a href={`${base}?view=atlas&sample=campus`}>北区与湖区连续地图<ArrowUpRight size={14} /></a>}{northStudy && <button type="button" onClick={() => setCompare(true)}>查看卫星图与案例对照<ArrowUpRight size={14} /></button>}</div>}
        {filtering && status === 'ready' && !selected && <div className="atlas-filter-banner"><span><strong>{category === 'all' ? '搜索地点' : atlasCategories.find(item => item.id === category)?.name}</strong><small>{filtered.length} 个匹配 · {searching || area === 'all' ? '全校' : regionNames.get(area)}</small></span><button type="button" disabled={!filtered.length} onClick={() => api.current.fitResults?.(filtered)} aria-label="查看全部匹配地点"><CornersOut size={17} /></button><button type="button" onClick={() => focusCategory('all')} aria-label="清除地图筛选"><X size={17} /></button></div>}
        {!study && status === 'ready' && area === 'all' && overviewVisible && !selected && !filtering && <div className="atlas-overview-intro" aria-live="polite"><small>全校鸟瞰 · 五个区域</small><strong>沿地图浏览整座校园</strong><span>{data?.records.length} 个可选建筑分部。点击区域，放大查看建筑与道路。</span></div>}
        {!study && status === 'ready' && area === 'all' && overviewVisible && !selected && !filtering && <nav className="atlas-overview-nav" aria-label="从全校总览进入区域">{overviewRegions.map((region, index) => <button type="button" key={region.id} onClick={() => focusRegion(region.id)}><small>{String(index + 1).padStart(2, '0')} · {region.count} 处</small><strong>{region.name}</strong><ArrowUpRight size={16} aria-hidden="true" /></button>)}</nav>}
        <div className="atlas-controls" aria-label="地图操作">
          <button type="button" disabled={status !== 'ready' || !zoomAvailable.in} title={status === 'ready' && !zoomAvailable.in ? '已放大到上限' : '放大地图'} onClick={() => { api.current.dismissOverview?.(); api.current.zoom?.(.5) }} aria-label="放大地图"><Plus size={20} /></button>
          <button type="button" disabled={status !== 'ready' || !zoomAvailable.out} title={status === 'ready' && !zoomAvailable.out ? '已缩小到下限' : '缩小地图'} onClick={() => { api.current.dismissOverview?.(); api.current.zoom?.(-.5) }} aria-label="缩小地图"><Minus size={20} /></button>
          <button type="button" disabled={status !== 'ready'} onClick={() => focusRegion('all')} aria-label={study ? '查看街区' : '查看全校'}><CornersOut size={20} /></button>
          <button type="button" disabled={status !== 'ready'} aria-pressed={labelsOn} onClick={() => setLabelsOn(v => !v)} aria-label={labelsOn ? '隐藏建筑名称' : '显示建筑名称'}><Tag size={19} /></button>
        </div>
        {status === 'loading' && <div ref={mapState} className="atlas-state" role="status" tabIndex={-1}><span className="atlas-loading-shape" aria-hidden="true" /><strong>正在展开校园地图</strong><span>{loadPhase === 'metadata' ? '正在获取建筑信息…' : '建筑信息已就绪，正在加载地图画面…'}</span>{loadSlow && <div className="atlas-load-recovery"><p>加载比平时慢，可以继续等待或重新加载。</p><button type="button" onClick={retryMap}><ArrowClockwise size={16} />重新加载</button><a href={`${base}?view=satellite`}>返回卫星地图</a></div>}</div>}
        {status === 'error' && <div ref={mapState} className="atlas-state" role="alert" tabIndex={-1}><strong>校园地图暂时无法加载</strong><span>{loadPhase === 'metadata' ? '建筑信息未能加载，请重试。' : '地图画面未能加载，请重试。'}</span><button ref={mapRetry} type="button" onClick={retryMap}><ArrowClockwise size={16} />重新加载</button><a href={`${base}?view=satellite`}>返回卫星地图</a></div>}
        {selected && status === 'ready' && <article ref={detailCard} tabIndex={-1} aria-labelledby="atlas-detail-title" className={`atlas-detail${detailExpanded ? ' atlas-detail--expanded' : ''}`}>
          <header className="atlas-detail-heading"><small>{selected.id.startsWith('place:') ? categoryName(selected) : selected.id} · {data?.regions.find(r => r.id === selected.region)?.name || '校园'}</small><h2 id="atlas-detail-title">{selected.name}</h2><button className="atlas-close" type="button" aria-label={selected.id.startsWith('place:') ? '关闭地点详情' : '关闭建筑详情'} onClick={closeBuilding}><X size={18} /></button></header>
          <div className="atlas-detail-body" id="atlas-building-details" tabIndex={detailExpanded ? 0 : undefined}><p>{selected.description}</p>{selected.floors_estimate && <dl className="atlas-building-facts"><div><dt>估算层数</dt><dd>{selected.floors_estimate} 层</dd></div><div><dt>估算高度</dt><dd>{selected.height_estimate_m} m</dd></div></dl>}{selected.id === 'B06' && <ReferencePhoto />}<small>{selected.id.startsWith('place:') ? '固定校园资料中的位置，尚不提供经过验证的步行路线。' : '用途与名称按既有资料描述，建筑分部不等于正式楼栋。高度和不可见细节为估算。'}</small></div>
          <div className="atlas-detail-share">
            <button type="button" onClick={copyBuildingLink} disabled={shareState === 'copying'}>{shareState === 'copied' ? <Check size={14} /> : <Copy size={14} />}{shareState === 'copied' ? selected.id.startsWith('place:') ? '已复制地点链接' : '已复制建筑链接' : shareState === 'copying' ? '正在复制…' : selected.id.startsWith('place:') ? '复制地点链接' : '复制建筑链接'}</button>
            <button type="button" disabled={status !== 'ready'} onClick={() => api.current.reframeSelected?.()} aria-label={selected.id.startsWith('place:') ? '重新定位当前地点' : '重新定位当前建筑'}><CrosshairSimple size={14} />重新定位</button>
            <span className="atlas-sr-only" role="status">{shareState === 'copied' ? '链接已复制，打开后会定位到当前地点。' : ''}</span>
            {shareState === 'manual' && <label className="atlas-share-fallback">可选择并复制下方链接<input ref={shareInput} value={shareUrl} readOnly onFocus={e => e.target.select()} aria-label={selected.id.startsWith('place:') ? '地点直达链接' : '建筑直达链接'} /></label>}
          </div>
          <button className="atlas-detail-toggle" type="button" aria-expanded={detailExpanded} aria-controls="atlas-building-details" onClick={() => setDetailExpanded(value => !value)}>{detailExpanded ? '收起详情' : selected.id === 'B06' ? '查看参考照片与详情' : '展开详情'}{detailExpanded ? <Minus size={14} /> : <Plus size={14} />}</button>
        </article>}
        <div className="atlas-bottom"><span>影像参考：Esri · 拖动 / 双指缩放</span><button type="button" onClick={() => setInfo(true)}><Info size={15} />资料说明</button></div>
      </section>
    </main>
    {compare && <div className="atlas-info-backdrop" onClick={() => setCompare(false)}><section ref={comparisonDialog} className="atlas-comparison" role="dialog" aria-modal="true" aria-labelledby="atlas-comparison-title" onClick={e => e.stopPropagation()}><button type="button" className="atlas-close" aria-label="关闭画面对照" onClick={() => setCompare(false)}><X size={20} /></button><small>北区街区 · 影像对照</small><h2 id="atlas-comparison-title">从卫星影像到街区鸟瞰</h2><p>前两图使用同一取景范围；卫星图只按地面投影对齐，屋顶因视差不会逐像素重合。案例来自另一所校园，仅对照画面表现。</p><div className="atlas-comparison-grid">{[{ file: 'campus-north-before.webp', title: '原始卫星图', note: '固定卫星影像的同范围地面投影，不是旧三维图。' }, { file: 'campus-north.webp', title: '北区街区样板', note: '北向取景、影像色差、已有树位与道路描述标注。' }, { file: 'campus-reference.webp', title: '视觉案例', note: '另一所校园；比较画面层次，不复制其地理布局。' }].map(item => <figure key={item.file}><a href={`${base}${item.file}?v=${data?.image_sha256?.slice(0,12) || '1'}`} target="_blank" rel="noreferrer" aria-label={`打开${item.title}原图`}><img src={`${base}${item.file}?v=${data?.image_sha256?.slice(0,12) || '1'}`} alt={item.title} /></a><figcaption><strong>{item.title}</strong><span>{item.note}</span></figcaption></figure>)}</div><p>样板覆盖 N07、N21–N35。道路文字为区域描述名，建筑高度、细部尺寸与植物形态仍为估算。</p></section></div>}
    {info && <div className="atlas-info-backdrop" onClick={() => setInfo(false)}><section ref={infoDialog} className="atlas-info" role="dialog" aria-modal="true" aria-labelledby="atlas-info-title" onClick={e => e.stopPropagation()}><button className="atlas-close" aria-label="关闭资料说明" onClick={() => setInfo(false)}><X size={20} /></button><small>地图资料</small><h2 id="atlas-info-title">依据影像，整理校园</h2><p>建筑位置、湖岸、道路与屋顶参考已有卫星影像；中央湖区和北区部分建筑外观参考校方照片。其他建筑的窗组、檐口与楼层线为类型化推定，尚缺近景照片核实。高度、铺装尺寸与植物形态采用展示性估算。</p><p>“湖西庭院建筑”和“湖东北建筑群”为区域描述，未绑定正式楼号。本画面用于浏览建筑与空间关系，尚不提供经过验证的步行路线。</p><p>{campusStudy ? '本图将北区 16 个建筑分部与中央湖区三组建筑放在同一场景中，周边建筑作为位置背景。' : lakeStudy ? '本样板覆盖中央湖区三组建筑，湖岸与水面按固定照片细化；护坡尺寸、水位和栏杆细部为估算。' : northStudy ? '本样板仅覆盖北区 N07、N21–N35；周围建筑作为位置背景保留。' : '本图覆盖南区与花卉园、中区、中央湖区、北区及北端区域。'}建筑与楼群采用影像中的可见轮廓，未统一核实正式名称、拍摄年代和实地高度。</p>{!study && <p className="atlas-study-links">制作样板：<a href={`${base}?view=atlas&sample=north`}>北区街区</a><a href={`${base}?view=atlas&sample=lake`}>中央湖区</a><a href={`${base}?view=atlas&sample=campus`}>北区与湖区连续图</a></p>}<p><a href="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer" target="_blank" rel="noreferrer">参考影像：Esri World Imagery ↗</a></p><a href="https://www.wxu.edu.cn/info/1111/57381.htm" target="_blank" rel="noreferrer">六号教学楼照片来源 ↗</a></section></div>}
  </div>
}
