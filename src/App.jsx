import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react'
import {
  ArrowSquareOut,
  ArrowsDownUp,
  BookOpen,
  Buildings,
  Bus,
  CaretRight,
  Check,
  Clock,
  Compass,
  CornersOut,
  FirstAid,
  ForkKnife,
  HouseLine,
  ImagesSquare,
  Info,
  ListMagnifyingGlass,
  MagnifyingGlass,
  MapPin,
  MapTrifold,
  Minus,
  NavigationArrow,
  Path,
  Plus,
  ShoppingBagOpen,
  SoccerBall,
  StackSimple,
  Student,
  X,
} from '@phosphor-icons/react'
import CampusMap from './CampusMap.jsx'
const CampusModelPreview = lazy(() => import('./CampusModelPreview.jsx'))
const CampusAtlas = lazy(() => import('./CampusAtlas.jsx'))
import { allPlaces, campusPlaces, campusVrUrl, categories, entrances, freshmanSteps, nearbyPlaces } from './campusData.js'

const appBasemaps = new Set(['model', 'satellite', 'street'])
function readAppBasemap() {
  const view = new URLSearchParams(window.location.search).get('view')
  // Legacy standard/illustrated links opened satellite before this navigation
  // pass. Keep that fallback; the current standard-map control uses street.
  return appBasemaps.has(view) ? view : 'satellite'
}
function writeAppView(basemap) {
  const url = new URL(window.location.href)
  url.searchParams.set('view', basemap)
  if (url.href !== window.location.href) window.history.replaceState(window.history.state, '', url)
}

const iconMap = {
  compass: Compass,
  buildings: Buildings,
  house: HouseLine,
  fork: ForkKnife,
  store: ShoppingBagOpen,
  book: BookOpen,
  ball: SoccerBall,
  bus: Bus,
}

const typeIcons = {
  '校门': MapPin,
  '迎新服务': Student,
  '办事服务': Buildings,
  '学习空间': BookOpen,
  '教学楼': Buildings,
  '学院单位': Buildings,
  '餐饮': ForkKnife,
  '生活服务': ShoppingBagOpen,
  '医疗': FirstAid,
  '宿舍': HouseLine,
  '运动': SoccerBall,
  '公共交通': Bus,
  '周边服务': Compass,
}

const tabs = [
  { id: 'explore', label: '找地点', icon: ListMagnifyingGlass },
  { id: 'route', label: '路线', icon: Path },
  { id: 'freshman', label: '新生指引', icon: Student },
]

const searchAliases = [
  { words: ['食堂', '餐厅', '吃饭'], type: '餐饮' },
  { words: ['教室', '教学'], type: '教学楼' },
  { words: ['寝室', '宿舍'], type: '宿舍' },
  { words: ['公交', '地铁', '车站'], type: '公共交通' },
  { words: ['操场', '球场', '体育'], type: '运动' },
  { words: ['图书馆', '自习'], type: '学习空间' },
  { words: ['报到', '迎新'], type: '迎新服务' },
  { words: ['快递', '超市', '商业街'], type: '生活服务' },
  { words: ['医务室', '看病', '医疗'], type: '医疗' },
]

function distanceInKm(start, end) {
  const toRad = (value) => value * Math.PI / 180
  const earthRadius = 6371
  const dLat = toRad(end[0] - start[0])
  const dLon = toRad(end[1] - start[1])
  const lat1 = toRad(start[0])
  const lat2 = toRad(end[0])
  const a = Math.sin(dLat / 2) ** 2 + Math.sin(dLon / 2) ** 2 * Math.cos(lat1) * Math.cos(lat2)
  return earthRadius * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a)) * 1.18
}

function buildDemoRoute(origin, destination) {
  if (!origin || !destination || origin.id === destination.id) return []
  const [startLat, startLng] = origin.coords
  const [endLat, endLng] = destination.coords
  const midLat = (startLat + endLat) / 2
  const midLng = (startLng + endLng) / 2
  return [
    origin.coords,
    [startLat * 0.68 + midLat * 0.32, startLng * 0.76 + midLng * 0.24],
    [midLat, midLng + (endLng - startLng) * 0.035],
    [endLat * 0.72 + midLat * 0.28, endLng * 0.78 + midLng * 0.22],
    destination.coords,
  ]
}

function App() {
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState('explore')
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('all')
  const [scope, setScope] = useState('campus')
  const [selectedPlace, setSelectedPlace] = useState(null)
  const [originId, setOriginId] = useState('gate2')
  const [destinationId, setDestinationId] = useState('welcome')
  const [routeActive, setRouteActive] = useState(false)
  const [freshmanEntrance, setFreshmanEntrance] = useState('gate2')
  const [completedSteps, setCompletedSteps] = useState([])
  const [layersOpen, setLayersOpen] = useState(false)
  const [campusPlanOpen, setCampusPlanOpen] = useState(false)
  const [campusVrOpen, setCampusVrOpen] = useState(null)
  const [basemap, updateBasemap] = useState(readAppBasemap)
  const [showBuildings, setShowBuildings] = useState(false)
  const [showBoundary, setShowBoundary] = useState(true)
  const [showNearby, setShowNearby] = useState(true)
  const [toast, setToast] = useState('')
  const mapRef = useRef(null)
  const tileErrorShownRef = useRef(false)

  function setBasemap(next) {
    if (!appBasemaps.has(next)) return
    updateBasemap(next)
    if (next === 'model') setScope('campus')
    writeAppView(next)
  }

  useEffect(() => {
    writeAppView(readAppBasemap())
    const restoreBasemap = () => {
      const next = readAppBasemap()
      updateBasemap(next)
      if (next === 'model') setScope('campus')
    }
    window.addEventListener('popstate', restoreBasemap)
    return () => window.removeEventListener('popstate', restoreBasemap)
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(() => setLoading(false), 420)
    return () => window.clearTimeout(timer)
  }, [])

  useEffect(() => {
    if (!toast) return undefined
    const timer = window.setTimeout(() => setToast(''), 2400)
    return () => window.clearTimeout(timer)
  }, [toast])

  useEffect(() => {
    function handleKeyDown(event) {
      if (event.key === '/' && document.activeElement?.tagName !== 'INPUT') {
        event.preventDefault()
        setActiveTab('explore')
        window.setTimeout(() => document.querySelector('.place-search input')?.focus(), 0)
      }
      if (event.key === 'Escape') {
        setSelectedPlace(null)
        setCampusPlanOpen(false)
        setCampusVrOpen(null)
        setLayersOpen(false)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  const origin = allPlaces.find((place) => place.id === originId)
  const destination = allPlaces.find((place) => place.id === destinationId)
  const route = useMemo(() => {
    if (!routeActive) return []
    return buildDemoRoute(origin, destination)
  }, [destination, origin, routeActive])
  const routeDistance = origin && destination ? distanceInKm(origin.coords, destination.coords) : 0
  const routeMinutes = Math.max(1, Math.round(routeDistance / 4.5 * 60))

  const filteredPlaces = useMemo(() => {
    const normalized = query.trim().toLowerCase()
    const pool = scope === 'campus' ? [...entrances, ...campusPlaces] : allPlaces
    return pool.filter((place) => {
      const matchesCategory = category === 'all' || place.type === category
      const haystack = `${place.name}${place.shortLabel}${place.type}${place.zone}`.toLowerCase()
      const aliasType = searchAliases.find((alias) => alias.words.some((word) => normalized.includes(word)))?.type
      const matchesQuery = !normalized || haystack.includes(normalized) || place.type === aliasType
      return matchesCategory && matchesQuery
    })
  }, [category, query, scope])

  const visibleMapPlaces = useMemo(() => {
    if (query.trim() || category !== 'all') return filteredPlaces
    const defaultPlaces = scope === 'campus'
      ? [...entrances, ...campusPlaces]
      : [...entrances, ...campusPlaces.filter((place) => place.featured), ...nearbyPlaces]
    if (selectedPlace && !defaultPlaces.some((place) => place.id === selectedPlace.id)) return [...defaultPlaces, selectedPlace]
    return defaultPlaces
  }, [category, filteredPlaces, query, scope, selectedPlace])

  function switchScope(nextScope) {
    setScope(nextScope)
    setCategory('all')
    setQuery('')
    setSelectedPlace(null)
    if (nextScope === 'campus') mapRef.current?.fitCampus()
    else {
      if (basemap === 'illustrated' || basemap === 'model') setBasemap('satellite')
      mapRef.current?.fitSurroundings()
    }
  }

  function showPlace(place) {
    if (basemap === 'model') setBasemap('satellite')
    setSelectedPlace(place)
    if (place.zone === '校外') setScope('nearby')
  }

  function startRoute(nextOriginId = originId, nextDestinationId = destinationId) {
    if (basemap === 'model') setBasemap('satellite')
    if (nextOriginId === nextDestinationId) {
      setToast('起点和终点不能相同')
      return
    }
    setOriginId(nextOriginId)
    setDestinationId(nextDestinationId)
    const nextOrigin = allPlaces.find((place) => place.id === nextOriginId)
    const nextDestination = allPlaces.find((place) => place.id === nextDestinationId)
    setScope(nextOrigin?.zone === '校外' || nextDestination?.zone === '校外' ? 'nearby' : 'campus')
    setRouteActive(true)
    setActiveTab('route')
    setSelectedPlace(allPlaces.find((place) => place.id === nextDestinationId) || null)
  }

  function beginFreshmanStep(step, index) {
    const previousId = index === 0 ? freshmanEntrance : freshmanSteps[index - 1].id
    startRoute(previousId, step.id)
  }

  function markFreshmanDone(stepId) {
    setCompletedSteps((items) => items.includes(stepId) ? items : [...items, stepId])
    setToast('该站已完成，继续下一项即可')
  }

  if (loading) return <LoadingScreen />

  return (
    <div className={`app-shell${basemap === 'model' ? ' app-shell--model' : ''}`}>
      <header className="topbar">
        <div className="map-brand-navigation">
          <div className="brand" aria-label="无锡太湖学院校园地图">
            <span className="brand-mark"><Compass size={23} weight="bold" /></span>
            <span><strong>太湖校园导览</strong><small>无锡太湖学院 · 校园导览</small></span>
          </div>
          {basemap !== 'model' && <nav className="model-top-nav" aria-label="地图视图"><a className="atlas-entry" href="?view=atlas">鸟瞰地图</a></nav>}
        </div>
        <div className="top-search" role="search">
          <MagnifyingGlass size={19} />
          <input
            value={query}
            onFocus={() => { setActiveTab('explore'); if (basemap === 'model') setBasemap('satellite') }}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索教学楼、宿舍、食堂、公交站"
            aria-label="搜索校园地点"
          />
          {query ? <button type="button" aria-label="清空搜索" onClick={() => setQuery('')}><X size={17} /></button> : <kbd>/</kbd>}
        </div>
        {basemap === 'model' && <nav className="model-top-nav" aria-label="校园模型导航"><a className="atlas-entry" href="?view=atlas">校园地图</a><button type="button" onClick={() => mapRef.current?.focusCentral()}>中央校区</button><button type="button" onClick={() => mapRef.current?.fitCampus()}>全校总览</button><button type="button" onClick={() => setBasemap('satellite')}>卫星与导航 ↗</button></nav>}
        <div className="top-meta"><span>校内 <b>{campusPlaces.length + entrances.length}</b> 个点位</span><i /><span>周边 <b>{nearbyPlaces.length}</b> 个点位</span></div>
      </header>

      <main className="workspace">
        <aside className="tool-panel">
          <nav className="panel-tabs" aria-label="导览功能">
            {tabs.map((tab) => {
              const Icon = tab.icon
              return <button className={activeTab === tab.id ? 'is-active' : ''} type="button" key={tab.id} onClick={() => { setActiveTab(tab.id); if (basemap === 'model') setBasemap('satellite') }}><Icon size={18} /><span>{tab.label}</span></button>
            })}
          </nav>

          <div className="panel-content">
            {basemap === 'model' && <section className="model-intro"><small>校园建筑 · 三维预览</small><h2>走近校园的每一栋楼</h2><p>在卫星屋顶轮廓上建立外观模型，查看庭院、坡屋顶和不同楼层的体积关系。</p><dl><div><dt>新增建筑部分</dt><dd>127</dd></div><div><dt>中央细化楼群</dt><dd>3</dd></div><div><dt>运动场</dt><dd>4</dd></div></dl><p>拖动地图浏览全校，搜索编号或点击建筑查看估算信息。使用右侧按钮可切换俯视。</p><p className="model-intro-note">部分正式楼号、高度和未见立面尚未核实。地点导航继续使用卫星地图。</p><button type="button" onClick={() => setBasemap('satellite')}>返回卫星地图与地点导航</button></section>}
            {basemap !== 'model' && activeTab === 'explore' && (
              <ExplorePanel
                category={category}
                setCategory={setCategory}
                filteredPlaces={filteredPlaces}
                query={query}
                scope={scope}
                onPlaceSelect={showPlace}
              />
            )}
            {basemap !== 'model' && activeTab === 'route' && (
              <RoutePanel
                originId={originId}
                destinationId={destinationId}
                setOriginId={(id) => { setOriginId(id); setRouteActive(false) }}
                setDestinationId={(id) => { setDestinationId(id); setRouteActive(false) }}
                onSwap={() => {
                  setOriginId(destinationId)
                  setDestinationId(originId)
                  setRouteActive(false)
                }}
                onStart={() => startRoute()}
                routeActive={routeActive}
                routeMinutes={routeMinutes}
                routeDistance={routeDistance}
                origin={origin}
                destination={destination}
              />
            )}
            {basemap !== 'model' && activeTab === 'freshman' && (
              <FreshmanPanel
                entranceId={freshmanEntrance}
                setEntranceId={setFreshmanEntrance}
                completed={completedSteps}
                onStepSelect={beginFreshmanStep}
                onStepDone={markFreshmanDone}
              />
            )}
          </div>

          <footer className="data-note"><Info size={15} /><span>{basemap === 'model' ? '模型来自卫星轮廓与照片分析；高度、窗格与隐蔽立面为估算。' : '卫星影像直接呈现真实屋顶；点位与可选轮廓仍需校方复核。'}</span></footer>
        </aside>

        <section className="map-area" aria-label="校园地图">
          {basemap === 'model' && scope === 'campus' ? <Suspense fallback={<div className="model-status">正在启动三维预览…</div>}><CampusModelPreview ref={mapRef} /></Suspense> : <CampusMap
            ref={mapRef}
            mode={scope}
            places={visibleMapPlaces}
            selectedPlace={selectedPlace}
            route={route}
            origin={origin}
            destination={destination}
            basemap={basemap}
            showBuildings={showBuildings}
            showBoundary={showBoundary}
            showNearby={showNearby}
            onPlaceSelect={showPlace}
            onMapPick={() => setToast('已记录地图选点，正式版可设为路线起点')}
            onTileError={() => {
              if (tileErrorShownRef.current) return
              tileErrorShownRef.current = true
              setToast('在线底图暂时未加载，点位图层仍可使用')
            }}
          />}

          <div className="scope-switch" aria-label="地图范围">
            <button className={scope === 'campus' ? 'is-active' : ''} type="button" onClick={() => switchScope('campus')}>校内</button>
            <button className={scope === 'nearby' ? 'is-active' : ''} type="button" onClick={() => switchScope('nearby')}>校园周边</button>
          </div>

          <div className="map-evidence" aria-label="地图数据说明">
            <i />{basemap === 'model' ? '校园三维预览' : basemap === 'satellite' ? '真实卫星影像' : '标准地图'}<span />{basemap === 'model' ? '高度估算 · 建筑可点击' : showBuildings ? '建筑轮廓待复核' : '地理底图'}
          </div>

          {basemap !== 'model' && routeActive && route.length > 1 && (
            <div className="route-banner">
              <span className="route-banner-icon"><NavigationArrow size={18} weight="fill" /></span>
              <span><small>步行前往</small><strong>{destination.name}</strong></span>
              <span><b>{routeMinutes}</b> 分钟<small>{routeDistance.toFixed(1)} 公里 · Demo 路线</small></span>
              <button type="button" aria-label="清除路线" onClick={() => setRouteActive(false)}><X size={18} /></button>
            </div>
          )}

          <div className="map-controls" aria-label="地图控制">
            <button type="button" aria-label="放大地图" onClick={() => mapRef.current?.zoomIn()}><Plus size={20} /></button>
            <button type="button" aria-label="缩小地图" onClick={() => mapRef.current?.zoomOut()}><Minus size={20} /></button>
            <button type="button" aria-label="回到校园" onClick={() => mapRef.current?.locateCampus()}><NavigationArrow size={20} /></button>
          </div>

          <div className="map-actions">
            <button type="button" className="model-entry" onClick={() => { setBasemap(basemap === 'model' ? 'satellite' : 'model'); switchScope('campus'); setLayersOpen(false) }}><Buildings size={19} /><span>{basemap === 'model' ? '卫星地图' : '三维校园'}</span></button>
            <button type="button" aria-label="图层" onClick={() => setLayersOpen((value) => !value)}><StackSimple size={19} /><span>图层</span></button>
            <button className="reality-button" aria-label="校园实景" type="button" onClick={() => setCampusVrOpen(campusVrUrl)}><ImagesSquare size={19} /><span>校园实景</span></button>
            <button type="button" aria-label="看周边" onClick={() => switchScope('nearby')}><CornersOut size={19} /><span>看周边</span></button>
          </div>

          {layersOpen && (
            <div className="layer-menu">
              <div><strong>地图图层</strong><button type="button" aria-label="关闭图层" onClick={() => setLayersOpen(false)}><X size={16} /></button></div>
              <div className="basemap-picker" role="group" aria-label="选择底图">
                <button className={basemap === 'model' ? 'is-active' : ''} type="button" onClick={() => { setBasemap('model'); switchScope('campus'); setLayersOpen(false) }}>三维预览</button>
                <button className={basemap === 'satellite' ? 'is-active' : ''} type="button" onClick={() => setBasemap('satellite')}>卫星影像</button>
                <button className={basemap === 'street' ? 'is-active' : ''} type="button" onClick={() => setBasemap('street')}>标准地图</button>
              </div>
              {basemap !== 'model' && <label><span><i className="layer-swatch layer-swatch--buildings" />建筑轮廓（待校准）</span><input type="checkbox" checked={showBuildings} onChange={(event) => setShowBuildings(event.target.checked)} /></label>}
              {basemap !== 'model' && <label><span><i className="layer-swatch layer-swatch--boundary" />校园范围</span><input type="checkbox" checked={showBoundary} onChange={(event) => setShowBoundary(event.target.checked)} /></label>}
              {basemap !== 'model' && <label><span><i className="layer-swatch layer-swatch--nearby" />周边交通与服务</span><input type="checkbox" checked={showNearby} onChange={(event) => setShowNearby(event.target.checked)} /></label>}
              <button className="plan-entry" type="button" onClick={() => { setCampusPlanOpen(true); setLayersOpen(false) }}><MapTrifold size={17} />查看校方平面图<CaretRight size={15} /></button>
            </div>
          )}

          {basemap !== 'model' && selectedPlace && (
            <PlaceCard place={selectedPlace} onClose={() => setSelectedPlace(null)} onNavigate={() => startRoute(originId, selectedPlace.id)} onOpenVr={() => setCampusVrOpen(selectedPlace.vrUrl)} />
          )}

          {campusPlanOpen && (
            <div className="plan-overlay" role="dialog" aria-modal="true" aria-label="校园平面图">
              <button className="plan-backdrop" type="button" aria-label="关闭平面图" onClick={() => setCampusPlanOpen(false)} />
              <article className="campus-plan-sheet">
                <header><span><MapTrifold size={20} />校园官方示意图</span><button type="button" aria-label="关闭平面图" onClick={() => setCampusPlanOpen(false)}><X size={19} /></button></header>
                <img src="./campus-map.jpg" alt="无锡太湖学院校区平面示意图" />
                <p>用于核对楼栋分区；互动地图点位为首版近似坐标，正式建设前应进行 GIS 实测校准。</p>
              </article>
            </div>
          )}

          {campusVrOpen && (
            <div className="vr-overlay" role="dialog" aria-modal="true" aria-label="校园实景漫游">
              <button className="vr-backdrop" type="button" aria-label="关闭校园实景" onClick={() => setCampusVrOpen(null)} />
              <article className="campus-vr-sheet">
                <header>
                  <span><ImagesSquare size={20} /><span><strong>校园实景漫游</strong><small>学校真实 360° 全景</small></span></span>
                  <button type="button" aria-label="关闭校园实景" onClick={() => setCampusVrOpen(null)}><X size={19} /></button>
                </header>
                <iframe src={campusVrOpen} title="无锡太湖学院校园实景漫游" allowFullScreen loading="eager" />
                <footer><span>实景资料由第三方全景平台加载，不使用合成建筑模型。</span><a href={campusVrOpen} target="_blank" rel="noreferrer">新窗口打开<ArrowSquareOut size={14} /></a></footer>
              </article>
            </div>
          )}
        </section>
      </main>

      {toast && <div className="toast" role="status"><Check size={17} weight="bold" />{toast}</div>}
    </div>
  )
}

function ExplorePanel({ category, setCategory, filteredPlaces, query, scope, onPlaceSelect }) {
  return (
    <>
      <section className="panel-section category-section">
        <div className="section-title"><div><span>地点分类</span><small>{scope === 'campus' ? '校内服务' : '校园与周边'}</small></div></div>
        <div className="category-grid">
          {categories.map((item) => {
            const Icon = iconMap[item.icon]
            return <button className={category === item.id ? 'is-active' : ''} type="button" key={item.id} onClick={() => setCategory(item.id)}><Icon size={20} /><span>{item.label}</span></button>
          })}
        </div>
      </section>
      <section className="panel-section results-section">
        <div className="section-title"><div><span>{query ? `“${query}”的结果` : category === 'all' ? '常用地点' : categories.find((item) => item.id === category)?.label}</span><small>{filteredPlaces.length} 个地点</small></div></div>
        <div className="place-list">
          {filteredPlaces.slice(0, 10).map((place) => <PlaceRow key={place.id} place={place} onClick={() => onPlaceSelect(place)} />)}
          {!filteredPlaces.length && <div className="empty-state"><MagnifyingGlass size={28} /><strong>没有找到相关地点</strong><span>试试更短的关键词或切换到“全部”。</span></div>}
        </div>
      </section>
    </>
  )
}

function PlaceRow({ place, onClick }) {
  const Icon = typeIcons[place.type] || MapPin
  return (
    <button className="place-row" type="button" onClick={onClick}>
      <span className={`place-row-icon ${place.zone === '校外' ? 'is-nearby' : ''}`}><Icon size={19} /></span>
      <span><strong>{place.name}</strong><small>{place.zone} · {place.type}</small></span>
      <CaretRight size={17} />
    </button>
  )
}

function RoutePanel({ originId, destinationId, setOriginId, setDestinationId, onSwap, onStart, routeActive, routeMinutes, routeDistance, origin, destination }) {
  return (
    <section className="route-planner">
      <div className="route-heading"><span className="route-mode"><Path size={18} />步行路线</span><small>首版为连线演示</small></div>
      <div className="route-fields">
        <span className="route-dots"><i /><b /><i /></span>
        <label><small>起点</small><select value={originId} onChange={(event) => setOriginId(event.target.value)}>{allPlaces.map((place) => <option key={place.id} value={place.id}>{place.name}</option>)}</select></label>
        <label><small>终点</small><select value={destinationId} onChange={(event) => setDestinationId(event.target.value)}>{allPlaces.map((place) => <option key={place.id} value={place.id}>{place.name}</option>)}</select></label>
        <button className="swap-route" type="button" aria-label="交换起点和终点" onClick={onSwap}><ArrowsDownUp size={18} /></button>
      </div>
      <button className="route-submit" type="button" onClick={onStart}><NavigationArrow size={18} weight="fill" />规划路线</button>
      {routeActive && (
        <article className="route-result">
          <header><span>推荐路线</span><strong>{routeMinutes} 分钟</strong></header>
          <div><b>{routeDistance.toFixed(1)} km</b><span>步行 · 校园道路优先</span></div>
          <ol>
            <li><i />从 {origin.name} 出发</li>
            <li><i />沿校园主路步行</li>
            <li><i />到达 {destination.name}</li>
          </ol>
          <small><Info size={14} />路线仅用于交互展示，正式版需接入真实路网。</small>
        </article>
      )}
      {!routeActive && <div className="route-tip"><MapTrifold size={27} /><strong>选择任意起点和终点</strong><span>支持校门、教学楼、宿舍及校外公交站。</span></div>}
    </section>
  )
}

function FreshmanPanel({ entranceId, setEntranceId, completed, onStepSelect, onStepDone }) {
  return (
    <section className="freshman-panel">
      <div className="freshman-intro"><span><Student size={21} weight="fill" /></span><div><strong>新生报到路线</strong><small>按任务组织，而不是只给一张地图</small></div><b>{completed.length}/{freshmanSteps.length}</b></div>
      <div className="entry-picker"><span>选择到校入口</span><div>{entrances.map((entrance) => <button className={entranceId === entrance.id ? 'is-active' : ''} type="button" key={entrance.id} onClick={() => setEntranceId(entrance.id)}>{entrance.shortLabel}</button>)}</div></div>
      <div className="freshman-steps">
        {freshmanSteps.map((step, index) => {
          const isDone = completed.includes(step.id)
          return (
            <article className={isDone ? 'is-done' : ''} key={step.id}>
              <span className="step-index">{isDone ? <Check size={16} weight="bold" /> : index + 1}</span>
              <button className="step-main" type="button" onClick={() => onStepSelect(step, index)}><strong>{step.title}</strong><small>{step.meta}</small></button>
              <button className="step-done" type="button" onClick={() => onStepDone(step.id)}>{isDone ? '已完成' : '标记完成'}</button>
            </article>
          )
        })}
      </div>
      <div className="freshman-help"><Info size={17} /><span>正式版可按学院、宿舍楼和报到批次自动生成个人路线。</span></div>
    </section>
  )
}

function PlaceCard({ place, onClose, onNavigate, onOpenVr }) {
  const Icon = typeIcons[place.type] || MapPin
  const [imageFailed, setImageFailed] = useState(false)

  useEffect(() => setImageFailed(false), [place.id])

  return (
    <article className={`place-card ${place.image && !imageFailed ? 'has-photo' : ''}`}>
      <button className="close-card" type="button" aria-label="关闭地点详情" onClick={onClose}><X size={18} /></button>
      <div className="place-card-head"><span><Icon size={23} /></span><div><small>{place.zone} · {place.type}</small><h2>{place.name}</h2></div></div>
      {place.image && !imageFailed && (
        <a className="place-photo" href={place.imagePage || place.image} target="_blank" rel="noreferrer" aria-label={`查看${place.name}实景资料`}>
          <img src={place.image} alt={`${place.name}校园实景`} loading="lazy" onError={() => setImageFailed(true)} />
          <span><ImagesSquare size={15} />{place.imageLabel || '实景资料'}<ArrowSquareOut size={13} /></span>
        </a>
      )}
      <p>{place.detail}</p>
      <div className="place-source"><Info size={14} />信息来源：{place.source}</div>
      <div className="place-actions">
        <button className="navigate-button" type="button" onClick={onNavigate}><NavigationArrow size={18} weight="fill" />到这里</button>
        {place.vrUrl && <button className="vr-button" type="button" onClick={onOpenVr}><ImagesSquare size={18} />VR实景</button>}
      </div>
    </article>
  )
}

function LoadingScreen() {
  return (
    <div className="loading-screen" aria-label="正在加载校园地图">
      <div className="loading-brand"><Compass size={25} /><strong>太湖校园导览</strong></div>
      <div className="loading-layout"><div className="loading-panel"><span /><span /><span /><span /></div><div className="loading-map"><span /><span /><span /></div></div>
    </div>
  )
}

export default function AppRouter() {
  const [view, setView] = useState(() => new URLSearchParams(window.location.search).get('view'))
  useEffect(() => {
    const restoreView = () => setView(new URLSearchParams(window.location.search).get('view'))
    window.addEventListener('popstate', restoreView)
    return () => window.removeEventListener('popstate', restoreView)
  }, [])
  return !view || view === 'atlas'
    ? <Suspense fallback={<LoadingScreen />}><CampusAtlas /></Suspense>
    : <App />
}
