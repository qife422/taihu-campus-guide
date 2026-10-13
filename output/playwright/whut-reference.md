# 武汉理工大学参考网站核对

主参考：https://gis.whut.edu.cn/index.shtml。用户于2026-10-06明确最终例子是整个网站；campus-reference.webp仅保留为地图画面局部参考。

这是限定的桌面参考核对，不是该网站的完整功能或无障碍审计。本次没有修改参考网站，也没有复制地图图块或设施数据。

## 1 · 网站首页总览

截图确认；不表示所有入口已测试。地图占主区域；顶部校区和搜索、左侧服务分类、底部指引入口同时可见。

![网站首页总览](/Users/ffq/Documents/aicoding项目/gis校园地图/output/playwright/whut-reference-overview.png)

## 2 · 地图放大

缩放状态确认；未测所有层级。真实点击放大控件后比例尺从100m变50m；路面、植床及建筑细节继续可见。DOM显示256×256地图图块及lv3资源路径。

![地图放大](/Users/ffq/Documents/aicoding项目/gis校园地图/output/playwright/whut-reference-zoom.png)

## 3 · 餐饮分类

餐饮分类联动确认；未穷举类别。餐饮列表和地图标记同时出现，面板含校区分组。

![餐饮分类](/Users/ffq/Documents/aicoding项目/gis校园地图/output/playwright/whut-reference-category.png)

## 4 · 列表定位与详情

标题和定位确认；弹窗正文、路线计算未完整验证。选择智苑食堂后地图重定位并打开对应标题弹窗，显示线路指引入口。

![列表定位与详情](/Users/ffq/Documents/aicoding项目/gis校园地图/output/playwright/whut-reference-detail.png)

## 5 · 校区切换

该次校区切换确认；左侧列表仍保留原分组，需分别核对列表筛选。点击马房山校区后顶部选中态和地图内容切换，餐饮点随地图变化。

![校区切换](/Users/ffq/Documents/aicoding项目/gis校园地图/output/playwright/whut-reference-campus.png)

## 6 · 建筑搜索

该关键词查询确认；空结果等状态未测试。输入图书馆并回车后显示跨校区查询结果、别名和地图标记。

![建筑搜索](/Users/ffq/Documents/aicoding项目/gis校园地图/output/playwright/whut-reference-search.png)

## 本地当前差距与后续验收

- CampusAtlas具备静态鸟瞰缩放、五个本校区域、建筑名称编号搜索、屋顶点击和详情；分类、VR及新生/路线演示主要在App的卫星入口，两套数据和选择状态尚未整合。
- 原生高清图及十二张本地截图通过只证明该次图像、布局与限定交互，不能证明整个网站已达到参考。
- 继续对照网站在总览、街区和建筑显示尺度上的制作质量，校准植被、铺装、立面与周边影像衔接；把实际地图联动一起列入验收。
- 参考站有三个校区，本校目前只有来源支持的校园/区域；不应因此虚构新校区、设施或实际路线。
- 页面多个图标链接的AX名称为空，显示label不能代替可达性检查；本次未测键盘、对比度、移动端、VR播放和完整路线结果。

六张当前截图及SHA、生成方法、门槛见同目录whut-reference.json。
