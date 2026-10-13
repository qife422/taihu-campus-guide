# 鸟瞰地图分类与地点联动验收

记录：2026-10-07T02:59:44.714512+00:00

主参考：[武汉理工大学校园地图服务系统](https://gis.whut.edu.cn/index.shtml)整个网站；本轮只完成一个交互切片，整体仍为 `not_met`。原生图片 d45c44fbf9a2、130 屋顶、25 项原生来源及 23 项原模型文件保持。

## 已实现与验证

- 默认完整鸟瞰总览；教学29、公寓63、餐饮5、配套33建筑分部，以及原资料3校门、4运动场。餐饮5项是原service类型中名称已描述餐饮的分部，不等于官方5栋食堂。
- 用途/区域筛选同步列表、屋顶与来源点的交互，高亮支持点击定位、详情、链接、刷新、返回。建筑building与来源点place分开。
- S1、全角Ｍ１、N1与六号补零/归一化；食堂/吃饭/宿舍/操场等用途别名。
- 复制链接保持拖动视角；六号楼参考照片打开/关闭；手机键盘选择后焦点进入详情，选中屋顶不被卡片遮挡。
- 卫星/标准地图回链在1280与390宽度可见；street刷新与同文档跨视图back/forward恢复正常。
- 跨区搜索清空选择；分类/总览提示不重叠；慢元数据加载保留输入；错误投影image SHA阻止显示，重试恢复。

## 数据边界

7个新来源点来自固定layout源像素及保存场景实际georef，经当前正交相机投影；独立标量投影差最大0.000529px。3个校门的浏览器屏幕位置误差均<0.35px，不代表实测地理准确度。校门56m取景窗口、运动场高度/标线仍是显示估算。区域为现有浏览分组，不能证明官方校区边界。旧Demo地点coords与正式鸟瞰无可靠交叉表，未按编号猜绑定。

未完成真实路网导航、所有设施实名核实、全景在线可用性、源站全部功能、真机软键盘及Safari验收。卫星截图只证明返回入口可见，不作为底图/旧POI精度验收。

## 截图

1. Default whole-campus entrance and six source-backed categories（1280×720）

![Default whole-campus entrance and six source-backed categories](/Users/ffq/Documents/aicoding项目/gis校园地图/output/playwright/atlas-services-overview.png)

2. Dining subset: same five records in list and roof hit layers, two regions（1280×720）

![Dining subset: same five records in list and roof hit layers, two regions](/Users/ffq/Documents/aicoding项目/gis校园地图/output/playwright/atlas-services-dining.png)

3. Source 3号门 anchor, independently projected screen position and separate place link（1280×720）

![Source 3号门 anchor, independently projected screen position and separate place link](/Users/ffq/Documents/aicoding项目/gis校园地图/output/playwright/atlas-services-gate.png)

4. Source stadium location/frame, retained original geometry and detail（1280×720）

![Source stadium location/frame, retained original geometry and detail](/Users/ffq/Documents/aicoding项目/gis校园地图/output/playwright/atlas-services-track.png)

5. Keyboard search selection, visible roof, focus and constrained detail（390×844）

![Keyboard search selection, visible roof, focus and constrained detail](/Users/ffq/Documents/aicoding项目/gis校园地图/output/playwright/atlas-services-mobile-390.png)

6. Mobile source stadium detail and readable field above card（390×844）

![Mobile source stadium detail and readable field above card](/Users/ffq/Documents/aicoding项目/gis校园地图/output/playwright/atlas-services-mobile-track.png)

7. Keyboard search selection, visible roof, focus and constrained detail（320×640）

![Keyboard search selection, visible roof, focus and constrained detail](/Users/ffq/Documents/aicoding项目/gis校园地图/output/playwright/atlas-services-mobile-320.png)

8. Narrow mobile source gate location without overflow（320×640）

![Narrow mobile source gate location without overflow](/Users/ffq/Documents/aicoding项目/gis校园地图/output/playwright/atlas-services-mobile-gate.png)

9. Keyboard search selection, visible roof, focus and constrained detail（844×390）

![Keyboard search selection, visible roof, focus and constrained detail](/Users/ffq/Documents/aicoding项目/gis校园地图/output/playwright/atlas-services-mobile-844.png)

10. Satellite return-to-atlas link visible; tile quality not audited（1280×720）

![Satellite return-to-atlas link visible; tile quality not audited](/Users/ffq/Documents/aicoding项目/gis校园地图/output/playwright/atlas-services-satellite-1280.png)

11. Satellite return-to-atlas link visible; tile quality not audited（390×844）

![Satellite return-to-atlas link visible; tile quality not audited](/Users/ffq/Documents/aicoding项目/gis校园地图/output/playwright/atlas-services-satellite-390.png)

## 证据与容量

正式清单 `atlas-services.json` 保存输入/脚本/截图SHA和有限检查。12张截图（含before）共7,593,599字节，当前源码176,547字节，放大43.01倍，均低于14张/12MiB/256倍；输出目录192MiB上限。未渲染、清理、迁移、改名或发布。

主skill `redesign-existing-projects`，辅助 `playwright`。沿用当前设计、数据和浏览器验收，未叠加近似审美/截图还原skill。
