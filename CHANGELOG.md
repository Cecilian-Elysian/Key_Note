# 更新日志

本文件记录 KeyNote 的版本变更。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/),版本号遵循[语义化版本](https://semver.org/lang/zh-CN/)。

## [1.0.0] - 2026-10-22

首个 WinUI3(C#)重写版。数据库 schema 与配置格式与历史 Python 版完全兼容,覆盖安装即可迁移。

### 重写

- Python → WinUI3(.NET 8 + Windows App SDK 1.7)全量重写,拆双工程:`src/KeyNote.App`(UI)/ `src/KeyNote.Core`(无 UI)
- 5 页侧边栏界面(统计 / 后台 / 热力图 / 常用按键 / 设置),Win11 Mica 直透整窗,永久暗色 Fluent 主题
- 纯 Win32 托盘(隐藏消息窗口 + Shell_NotifyIconW),图标按 accent 30% tint 渲染
- 图表全部改为 XAML 绘制:趋势图 / 7×24 / QWERTY / GitHub 年度热力图 / Top 10 条形图

### 新增

- 应用内更新检查:GitHub Releases 列表端点 + 组件式版本比较 + 更新说明 + 状态广播
- 应用内静默升级:流式下载 + 大小校验 → 拉起 Inno Setup 静默安装器(自动替换并重启)
- 设置页「高级设置」折叠区(10 项)、搜索过滤、无障碍名称
- 托盘实时统计 / 最近活动 / 保留策略快捷切换
- 备份 / VACUUM / CSV 导出抽为 `MaintenanceService`,托盘与设置页共用
- `Theme/UiColors.cs` 统一色板 + `App.xaml` 字号令牌;公共控件 `ChartTip` / `EmptyStateView` / `PageRefresh`

### 修复

- 钩子:线程内自维护键盘状态(Shift / CapsLock / AltGr 还原);鼠标结构体补 POINT、消息常量改按下语义、侧键按高字判定
- 钩子:安装状态可见 + 监听开关即时生效(修「显示记录中但实际没录」)
- 统计:KPI 跟随时间筛选、年度热力图不再截断、键盘热力图 / Top 10 口径统一
- 数据库:写路径改多行 INSERT、查询避开全表扫;CSV 转义、配置覆盖、迁移事务、批次丢弃、读连接 NRE
- UI:过滤残留、窗口可缩放、图表溢出、无障碍标注、日志 tag;控件不再自改自身高度、切页去双刷新、页头固定
- 托盘:`AddIcon`/`RemoveIcon` 同步 `_visible` 状态,修重复 NIM_ADD 与 hIcon 泄漏
- 发布链:安装包夹带用户数据、唯一备份被删、ISCC 静默失败三处隐患;桌面快捷方式改 `{userdesktop}`、安装包加应用图标
- 更新失败不再静默(给明确文案,不写每日时间戳)

### 统计口径变更

见 README「统计口径变更」一节:长按只计一次、大小写正确还原、鼠标点击精确计数、KPI 跟随时间筛选、两页口径统一、年度热力图按设置天数展开、非 ASCII 归入字母类、修饰键不计入统计。升级后历史数字变小属正常。

### 已知取舍

- `window_alpha`:WinUI3 不支持整窗 alpha,退化为内容区不透明度
- 便携版运行副本无法自动替换自己,更新时改为提示并打开下载页
- 发布体积约 95MB,其中约 88MB 为 Windows App SDK 运行时(瘦身见路线图)
