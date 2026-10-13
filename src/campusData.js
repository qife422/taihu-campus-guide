export const campusCenter = [31.5751, 120.2219]

export const campusVrUrl = 'https://qj.720pai.cn/tour/6c1b7e69f9f3111b'

const campusVrScene = (sceneId) => `${campusVrUrl}?s=scene_${sceneId}`

const campusAerialImage = 'https://www.wxu.edu.cn/__local/D/32/66/684E8693DC2D9942B6E26C72390_6E6F19AF_C0CBAB.jpg'
const panoramaPhotoBase = 'https://panosoft.cn/media/outputpic/教育_江苏省_无锡太湖学院_20张图片'

const campusMedia = {
  welcome: { image: campusAerialImage, imagePage: 'https://www.wxu.edu.cn/info/1111/57421.htm' },
  admin: { image: campusAerialImage, imagePage: 'https://www.wxu.edu.cn/info/1111/57421.htm', imageLabel: '校方校园航拍' },
  library: { image: campusAerialImage, imagePage: 'https://www.wxu.edu.cn/info/1111/57421.htm', vrUrl: campusVrScene('d7dcce588aace32e') },
  innovation: { image: `${panoramaPhotoBase}/无锡太湖学院_活动中心2..jpg`, imagePage: 'https://panosoft.cn/picture_directory/747/' },
  teach5: { image: `${panoramaPhotoBase}/无锡太湖学院_教学楼5..jpg`, imagePage: 'https://panosoft.cn/picture_directory/747/', vrUrl: campusVrScene('2bc66487fd65feef') },
  teach6: { image: `${panoramaPhotoBase}/无锡太湖学院_教学楼..jpg`, imagePage: 'https://panosoft.cn/picture_directory/747/' },
  engineering: { image: campusAerialImage, imagePage: 'https://www.wxu.edu.cn/xxgk/xygy/3.htm', vrUrl: campusVrScene('497432a65295000f') },
  scotland: { image: `${panoramaPhotoBase}/无锡太湖学院_商学院..jpg`, imagePage: 'https://panosoft.cn/picture_directory/747/', vrUrl: campusVrScene('4c0c9d8b92c9eb51') },
  north_dining: { image: `${panoramaPhotoBase}/无锡太湖学院_食堂门口..jpg`, imagePage: 'https://panosoft.cn/picture_directory/747/' },
  south_dining: { image: `${panoramaPhotoBase}/无锡太湖学院_食堂.jpg`, imagePage: 'https://panosoft.cn/picture_directory/747/', vrUrl: campusVrScene('6c122e453bb2300b') },
  new_dining: { image: `${panoramaPhotoBase}/无锡太湖学院_食堂门口..jpg`, imagePage: 'https://panosoft.cn/picture_directory/747/' },
  commerce: { image: `${panoramaPhotoBase}/无锡太湖学院_商业街..jpg`, imagePage: 'https://panosoft.cn/picture_directory/747/', vrUrl: campusVrScene('65014b87653543d6') },
  express: { vrUrl: campusVrScene('b6650cf5270cbb31') },
  dorm32: { image: `${panoramaPhotoBase}/无锡太湖学院_宿舍.jpg`, imagePage: 'https://panosoft.cn/picture_directory/747/' },
  dorm20: { image: `${panoramaPhotoBase}/无锡太湖学院_宿舍门口..jpg`, imagePage: 'https://panosoft.cn/picture_directory/747/' },
  north_track: { image: `${panoramaPhotoBase}/无锡太湖学院_操场..jpg`, imagePage: 'https://panosoft.cn/picture_directory/747/' },
  central_track: { image: `${panoramaPhotoBase}/无锡太湖学院_足球场..jpg`, imagePage: 'https://panosoft.cn/picture_directory/747/' },
  south_track: { image: `${panoramaPhotoBase}/无锡太湖学院_篮球场..jpg`, imagePage: 'https://panosoft.cn/picture_directory/747/' },
}

export const entrances = [
  { id: 'gate1', name: '1号门', shortLabel: '1号门', type: '校门', zone: '北区', detail: '靠近惠山国家森林公园（钱荣路）公交站，适合从钱荣路北侧到校。', coords: [31.58105, 120.22665], source: '校方校园地图', image: 'https://www.wxu.edu.cn/u/cms/thxy/201906/07144740a7bl.jpg', imagePage: 'https://www.wxu.edu.cn/wskx/13605.htm' },
  { id: 'gate2', name: '2号门（东南门）', shortLabel: '2号门', type: '校门', zone: '南区', detail: '靠近西山（太湖学院）公交站，是新生集中到校的便捷入口之一。', coords: [31.56935, 120.22265], source: '校方校园地图', image: 'https://www.wxu.edu.cn/u/cms/thxy/201906/07144740a7bl.jpg', imagePage: 'https://www.wxu.edu.cn/wskx/13605.htm' },
  { id: 'gate3', name: '3号门（花卉园门）', shortLabel: '3号门', type: '校门', zone: '南区', detail: '连接花卉园校区与南校区，靠近体育场和南区宿舍。', coords: [31.56835, 120.21635], source: '校方校园地图', image: 'https://www.wxu.edu.cn/u/cms/thxy/201906/07144740a7bl.jpg', imagePage: 'https://www.wxu.edu.cn/wskx/13605.htm' },
]

const campusPlaceRecords = [
  { id: 'welcome', name: '新生报到服务点', shortLabel: '报到处', type: '迎新服务', zone: '中区', detail: '核验材料、领取校园卡和新生资料。首版 Demo 使用示意点位。', coords: [31.5739, 120.2212], source: 'Demo 示意', featured: true },
  { id: 'admin', name: '行政楼', shortLabel: '行政楼', type: '办事服务', zone: '中区', detail: '校级行政与综合办事区域，具体业务窗口以后勤及迎新通知为准。', coords: [31.5747, 120.2189], source: '校方校园地图', featured: true },
  { id: 'library', name: '图书信息中心', shortLabel: '图书馆', type: '学习空间', zone: '中区', detail: '馆藏、阅览和信息服务空间。学校公开资料显示设有图书馆及阅览座位。', coords: [31.5758, 120.2199], source: '校方公开资料', featured: true },
  { id: 'innovation', name: '大学生创新中心', shortLabel: '创新中心', type: '学习空间', zone: '南区', detail: '创新创业活动与学生项目实践空间。', coords: [31.5725, 120.2181], source: '校方校园地图' },
  { id: 'teach5', name: '5号教学楼', shortLabel: '5号楼', type: '教学楼', zone: '中区', detail: '课程教学与新生班会常用区域，教室安排以课表为准。', coords: [31.5751, 120.2216], source: '校方校园地图' },
  { id: 'teach6', name: '6号教学楼', shortLabel: '6号楼', type: '教学楼', zone: '北区', detail: '北区教学区域，支持从宿舍、食堂一键规划步行路线。', coords: [31.5782, 120.2231], source: '校方校园地图', featured: true },
  { id: 'engineering', name: '工科实验实训中心', shortLabel: '工科中心', type: '教学楼', zone: '北区', detail: '工程实践、实验实训与开放日体验场所。', coords: [31.5792, 120.2219], source: '校方公开资料' },
  { id: 'scotland', name: '苏格兰学院', shortLabel: '苏格兰学院', type: '学院单位', zone: '北区', detail: '中外合作办学相关教学与活动区域。', coords: [31.5798, 120.2240], source: '校方校园地图' },
  { id: 'north_dining', name: '北苑餐厅', shortLabel: '北苑餐厅', type: '餐饮', zone: '北区', detail: '北区主要餐饮点，适合北区宿舍与教学区学生就餐。', coords: [31.5802, 120.2190], source: '校方公开资料', featured: true },
  { id: 'south_dining', name: '南苑餐厅', shortLabel: '南苑餐厅', type: '餐饮', zone: '中区', detail: '中南区主要餐饮点，靠近教学楼与学生公寓。', coords: [31.5748, 120.2202], source: '校方公开资料' },
  { id: 'new_dining', name: '新苑餐厅', shortLabel: '新苑餐厅', type: '餐饮', zone: '南区', detail: '校内餐饮服务点之一，具体营业时间以现场公告为准。', coords: [31.5712, 120.2199], source: '校方公开资料' },
  { id: 'commerce', name: '中区商业街', shortLabel: '商业街', type: '生活服务', zone: '中区', detail: '日常采购、通讯和生活服务集中区域。', coords: [31.5750, 120.2229], source: '校方校园地图', featured: true },
  { id: 'express', name: '快递服务点', shortLabel: '快递', type: '生活服务', zone: '中区', detail: '快递收发演示点位，正式版需接入后勤最新站点与营业时间。', coords: [31.5761, 120.2224], source: 'Demo 示意' },
  { id: 'health', name: '校园健康服务点', shortLabel: '医务', type: '医疗', zone: '中区', detail: '校内基础医疗与健康咨询演示点位，紧急情况请拨打 120。', coords: [31.5740, 120.2194], source: 'Demo 示意' },
  { id: 'dorm32', name: '32号宿舍', shortLabel: '32宿舍', type: '宿舍', zone: '北区', detail: '新生入住演示宿舍。正式版可按学院与班级关联实际楼栋。', coords: [31.58145, 120.22595], source: '校方校园地图', featured: true },
  { id: 'dorm20', name: '20号宿舍', shortLabel: '20宿舍', type: '宿舍', zone: '中区', detail: '中区学生公寓，靠近篮球场、食堂与教学区域。', coords: [31.5734, 120.2175], source: '校方校园地图' },
  { id: 'north_track', name: '北区田径场', shortLabel: '北区运动场', type: '运动', zone: '北区', detail: '标准田径与足球活动区域。', coords: [31.5812, 120.2231], source: '校方校园地图' },
  { id: 'central_track', name: '中区运动场', shortLabel: '中区运动场', type: '运动', zone: '中区', detail: '中区主要运动场地，周边分布教学楼与实验楼。', coords: [31.5762, 120.2211], source: '校方校园地图' },
  { id: 'south_track', name: '南区运动场', shortLabel: '南区运动场', type: '运动', zone: '南区', detail: '靠近南区宿舍与3号门的体育活动区域。', coords: [31.5693, 120.2167], source: '校方校园地图' },
]

export const campusPlaces = campusPlaceRecords.map((place) => ({
  ...place,
  ...campusMedia[place.id],
}))

// These are deliberately simple massing models, aligned to the public campus
// plan and aerial imagery. They are not presented as surveyed CAD geometry.
export const campusBuildings = [
  { id: 'admin-building', placeId: 'admin', name: '行政楼', center: [31.5747, 120.2189], width: 92, depth: 38, angle: -8, levels: 5, kind: 'civic' },
  { id: 'library-building', placeId: 'library', name: '图书信息中心', center: [31.5758, 120.2199], width: 96, depth: 44, angle: -8, levels: 6, kind: 'civic' },
  { id: 'innovation-building', placeId: 'innovation', name: '大学生创新中心', center: [31.5725, 120.2181], width: 82, depth: 32, angle: -5, levels: 4, kind: 'academic' },
  { id: 'teach5-building', placeId: 'teach5', name: '5号教学楼', center: [31.5751, 120.2216], width: 104, depth: 31, angle: -5, levels: 5, kind: 'academic' },
  { id: 'teach6-building', placeId: 'teach6', name: '6号教学楼', center: [31.5782, 120.2231], width: 105, depth: 34, angle: -4, levels: 5, kind: 'academic' },
  { id: 'engineering-building', placeId: 'engineering', name: '工科实验实训中心', center: [31.5792, 120.2219], width: 115, depth: 43, angle: -6, levels: 6, kind: 'academic' },
  { id: 'scotland-building', placeId: 'scotland', name: '苏格兰学院', center: [31.5798, 120.2240], width: 82, depth: 34, angle: -5, levels: 5, kind: 'academic' },
  { id: 'north-dining-building', placeId: 'north_dining', name: '北苑餐厅', center: [31.5802, 120.2190], width: 85, depth: 36, angle: -6, levels: 3, kind: 'service' },
  { id: 'south-dining-building', placeId: 'south_dining', name: '南苑餐厅', center: [31.5748, 120.2202], width: 76, depth: 34, angle: -4, levels: 3, kind: 'service' },
  { id: 'new-dining-building', placeId: 'new_dining', name: '新苑餐厅', center: [31.5712, 120.2199], width: 77, depth: 35, angle: -7, levels: 3, kind: 'service' },
  { id: 'commerce-building', placeId: 'commerce', name: '中区商业街', center: [31.5750, 120.2229], width: 126, depth: 25, angle: -3, levels: 2, kind: 'service' },
  { id: 'dorm32-building', placeId: 'dorm32', name: '32号宿舍', center: [31.58145, 120.22595], width: 72, depth: 22, angle: -4, levels: 6, kind: 'dorm' },
  { id: 'dorm32-west', placeId: 'dorm32', name: '北区学生公寓', center: [31.58125, 120.22515], width: 70, depth: 21, angle: -4, levels: 6, kind: 'dorm' },
  { id: 'dorm32-north', placeId: 'dorm32', name: '北区学生公寓', center: [31.58205, 120.22555], width: 72, depth: 21, angle: -4, levels: 6, kind: 'dorm' },
  { id: 'dorm20-building', placeId: 'dorm20', name: '20号宿舍', center: [31.5734, 120.2175], width: 70, depth: 22, angle: -6, levels: 6, kind: 'dorm' },
  { id: 'dorm20-north', placeId: 'dorm20', name: '中区学生公寓', center: [31.57405, 120.21735], width: 69, depth: 21, angle: -6, levels: 6, kind: 'dorm' },
  { id: 'dorm20-south', placeId: 'dorm20', name: '中区学生公寓', center: [31.57275, 120.21775], width: 69, depth: 21, angle: -6, levels: 6, kind: 'dorm' },
  { id: 'south-dorm-a', placeId: 'dorm20', name: '南区学生公寓', center: [31.5705, 120.21825], width: 68, depth: 21, angle: -7, levels: 6, kind: 'dorm' },
  { id: 'south-dorm-b', placeId: 'dorm20', name: '南区学生公寓', center: [31.5699, 120.21855], width: 68, depth: 21, angle: -7, levels: 6, kind: 'dorm' },
  { id: 'south-dorm-c', placeId: 'dorm20', name: '南区学生公寓', center: [31.5693, 120.21885], width: 68, depth: 21, angle: -7, levels: 6, kind: 'dorm' },
]

export const nearbyPlaces = [
  { id: 'bus_xishan', name: '西山（太湖学院）公交站', shortLabel: '西山公交站', type: '公共交通', zone: '校外', detail: '可乘 26、83、206、608 路等线路；实际班次以公交平台为准。', coords: [31.5690, 120.2245], source: '学校交通出行页', verified: true },
  { id: 'bus_huishan', name: '惠山国家森林公园（钱荣路）站', shortLabel: '森林公园站', type: '公共交通', zone: '校外', detail: '靠近1号门，部分到校公交在此停靠。', coords: [31.5816, 120.2270], source: '学校交通出行页', verified: true },
  { id: 'metro_rongxiang', name: '荣巷地铁站', shortLabel: '荣巷地铁', type: '公共交通', zone: '校外', detail: '无锡地铁2号线站点，距离学校约2公里，可换乘公交或出租车到校。', coords: [31.5685, 120.2530], source: '公共地图信息' },
  { id: 'zoo', name: '无锡动物园', shortLabel: '无锡动物园', type: '周边服务', zone: '校外', detail: '位于钱荣路沿线的城市景点，靠近学校北侧。', coords: [31.5856, 120.2326], source: '公共地图信息' },
  { id: 'forest', name: '惠山国家森林公园', shortLabel: '森林公园', type: '周边服务', zone: '校外', detail: '学校周边重要生态空间，校园位于国家森林公园区域内。', coords: [31.5827, 120.2479], source: '校方公开资料' },
  { id: 'flower', name: '太湖花卉园', shortLabel: '太湖花卉园', type: '周边服务', zone: '校外', detail: '毗邻学校南侧与花卉园校区的周边地点。', coords: [31.5666, 120.2139], source: '公共地图信息' },
]

export const allPlaces = [...entrances, ...campusPlaces, ...nearbyPlaces]

export const categories = [
  { id: 'all', label: '全部', icon: 'compass' },
  { id: '教学楼', label: '教学', icon: 'buildings' },
  { id: '宿舍', label: '宿舍', icon: 'house' },
  { id: '餐饮', label: '餐饮', icon: 'fork' },
  { id: '生活服务', label: '生活', icon: 'store' },
  { id: '学习空间', label: '学习', icon: 'book' },
  { id: '运动', label: '运动', icon: 'ball' },
  { id: '公共交通', label: '交通', icon: 'bus' },
]

export const freshmanSteps = [
  { id: 'welcome', title: '新生报到', meta: '材料核验 · 领取校园卡' },
  { id: 'dorm32', title: '宿舍入住', meta: '演示楼栋 · 32号宿舍' },
  { id: 'north_dining', title: '熟悉餐饮', meta: '北苑餐厅' },
  { id: 'teach6', title: '找到教学楼', meta: '演示集合点 · 6号教学楼' },
]
